"""Bulk geometry creation through AutoLISP.

The per-entity tools in draw.py go through COM, which costs a round trip for
the create plus one for each property. That is the right trade for a handful of
entities — the inputs are validated per field and the result comes back typed.

For hundreds of entities it is the wrong trade. This tool sends one AutoLISP
script that runs inside AutoCAD and creates everything with ``entmake``, so a
batch of any size is a single round trip.
"""

from __future__ import annotations

import math
import os
import tempfile
import time
import uuid
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import Field

from ..acad.coords import Ucs
from ..acad.lisp import (
    build_chunks,
    dotted,
    lisp_number,
    lisp_point,
    lisp_string,
    parse_output,
)
from ..acad.tables import ensure_layer
from ..acad.units import rad
from ..core.connection import get_doc, mark_writing, require_idle, run
from ..core.errors import AutocadError
from ..core.gate import quiet_sender
from ..core.quiet import QUIET_FIELD
from ..core.quiet import quiet as quieted
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta
from ._shared import COORDS_OPT, ucs_for

MAX_OPERATIONS = 5000

# How long to wait for the script's output file to appear. SendCommand normally
# blocks until the load completes, so this only covers the versions where it
# does not.
OUTPUT_TIMEOUT = 60.0
OUTPUT_POLL = 0.02


def _require(op: dict[str, Any], key: str, index: int) -> Any:
    if key not in op or op[key] is None:
        raise AutocadError(
            f"Operation {index} ({op.get('type', 'unknown')}) is missing "
            f"required field '{key}'."
        )
    return op[key]


def _common_pairs(op: dict[str, Any], dxf_name: str) -> list[str]:
    """The group codes every entity shares: type, layer, colour."""
    pairs = [dotted(0, lisp_string(dxf_name))]
    if op.get("layer"):
        pairs.append(dotted(8, lisp_string(str(op["layer"]).strip())))
    aci = to_aci(op.get("color"))
    if aci is not None:
        pairs.append(dotted(62, str(aci)))
    return pairs


def _build_line(op: dict[str, Any], i: int) -> list[str]:
    pairs = _common_pairs(op, "LINE")
    pairs.append(dotted(10, lisp_point(_require(op, "start", i))))
    pairs.append(dotted(11, lisp_point(_require(op, "end", i))))
    return pairs


def _build_circle(op: dict[str, Any], i: int) -> list[str]:
    radius = op.get("radius")
    if radius is None and op.get("diameter") is not None:
        radius = float(op["diameter"]) / 2.0
    if radius is None:
        raise AutocadError(f"Operation {i} (circle) needs 'radius' or 'diameter'.")
    if float(radius) <= 0:
        raise AutocadError(
            f"Operation {i} (circle) has radius {radius}; it must be greater "
            "than zero."
        )
    pairs = _common_pairs(op, "CIRCLE")
    pairs.append(dotted(10, lisp_point(_require(op, "center", i))))
    pairs.append(dotted(40, lisp_number(radius)))
    return pairs


def _build_arc(op: dict[str, Any], i: int) -> list[str]:
    radius = _require(op, "radius", i)
    if float(radius) <= 0:
        raise AutocadError(f"Operation {i} (arc) has radius {radius}; must be > 0.")
    pairs = _common_pairs(op, "ARC")
    pairs.append(dotted(10, lisp_point(_require(op, "center", i))))
    pairs.append(dotted(40, lisp_number(radius)))
    pairs.append(dotted(50, lisp_number(rad(_require(op, "start_angle", i)))))
    pairs.append(dotted(51, lisp_number(rad(_require(op, "end_angle", i)))))
    return pairs


def _build_point(op: dict[str, Any], i: int) -> list[str]:
    pairs = _common_pairs(op, "POINT")
    pairs.append(dotted(10, lisp_point(_require(op, "position", i))))
    return pairs


# DXF justification for TEXT: group 72 across, group 73 up and down. Anything
# other than left-baseline also needs group 11, the point that then does the
# positioning. "center" and "right" use middle (73 = 2) as well, because a
# centred annotation wants to sit on its point both ways - which is what a
# detail bubble, a level mark and a revision tag all need.
_TEXT_ALIGN = {
    "left": (0, 0),
    "center": (1, 2),
    "centre": (1, 2),
    "right": (2, 2),
    "baseline_center": (1, 0),
    "baseline_centre": (1, 0),
}


def _build_text(op: dict[str, Any], i: int) -> list[str]:
    pairs = _common_pairs(op, "TEXT")
    position = _require(op, "position", i)
    pairs.append(dotted(10, lisp_point(position)))
    pairs.append(dotted(40, lisp_number(op.get("height", 2.5))))
    pairs.append(dotted(1, lisp_string(_require(op, "text", i))))
    if op.get("rotation"):
        pairs.append(dotted(50, lisp_number(rad(op["rotation"]))))
    align = str(op.get("align", "left")).strip().lower()
    if align not in _TEXT_ALIGN:
        raise AutocadError(
            f"Operation {i} (text) has align '{op.get('align')}'. Use one of: "
            + ", ".join(sorted(set(_TEXT_ALIGN)))
            + "."
        )
    across, updown = _TEXT_ALIGN[align]
    if across or updown:
        pairs.append(dotted(72, str(across)))
        pairs.append(dotted(73, str(updown)))
        # Group 11 is what actually places a justified text; 10 is kept because
        # entmake validates the subclass with it there.
        pairs.append(dotted(11, lisp_point(position)))
    if op.get("style"):
        pairs.append(dotted(7, lisp_string(str(op["style"]).strip())))
    return pairs


def _polyline_pairs(
    op: dict[str, Any],
    vertices: list[list[float]],
    closed: bool,
    bulges: Sequence[float] | None = None,
) -> list[str]:
    """LWPOLYLINE needs its subclass markers, unlike the simpler entities.

    entmake validates against the DXF subclass structure here, so the
    AcDbEntity / AcDbPolyline markers and the vertex count are mandatory, and
    colour has to sit in the AcDbEntity section before the second marker.

    A bulge (group 42) belongs to the segment *leaving* its vertex, so it is
    written straight after that vertex's group 10. Bulge is tan(sweep / 4),
    positive anticlockwise - which is what turns a corner into a fillet, a
    rectangle into a slot and a route into an elbow, all in one object.
    """
    pairs = [dotted(0, lisp_string("LWPOLYLINE")), dotted(100, lisp_string("AcDbEntity"))]
    if op.get("layer"):
        pairs.append(dotted(8, lisp_string(str(op["layer"]).strip())))
    aci = to_aci(op.get("color"))
    if aci is not None:
        pairs.append(dotted(62, str(aci)))
    pairs.append(dotted(100, lisp_string("AcDbPolyline")))
    pairs.append(dotted(90, str(len(vertices))))
    pairs.append(dotted(70, "1" if closed else "0"))
    if op.get("width") is not None:
        pairs.append(dotted(43, lisp_number(op["width"])))
    if op.get("elevation"):
        # A lightweight polyline is flat; its one height is group 38.
        pairs.append(dotted(38, lisp_number(op["elevation"])))
    for index, vertex in enumerate(vertices):
        pairs.append(
            dotted(
                10,
                f"(list {lisp_number(vertex[0])} {lisp_number(vertex[1])})",
            )
        )
        bulge = float(bulges[index]) if bulges and index < len(bulges) else 0.0
        if bulge:
            pairs.append(dotted(42, lisp_number(bulge)))
    return pairs


def _build_polyline(op: dict[str, Any], i: int) -> list[str]:
    points = _require(op, "points", i)
    if len(points) < 2:
        raise AutocadError(
            f"Operation {i} (polyline) has {len(points)} vertices; at least 2 "
            "are required."
        )
    for n, vertex in enumerate(points):
        if len(vertex) < 2:
            raise AutocadError(
                f"Operation {i} (polyline) vertex {n} is {vertex!r}; every "
                "vertex needs at least [x, y]."
            )
    bulges = op.get("bulges")
    if bulges is not None and len(bulges) > len(points):
        raise AutocadError(
            f"Operation {i} (polyline) has {len(bulges)} bulges for {len(points)} "
            "vertices. A bulge belongs to the segment leaving its vertex, so give "
            "one per vertex or fewer."
        )
    return _polyline_pairs(op, points, bool(op.get("closed", False)), bulges)


def _build_rectangle(op: dict[str, Any], i: int) -> list[str]:
    c1 = _require(op, "corner1", i)
    c2 = _require(op, "corner2", i)
    if len(c1) < 2 or len(c2) < 2:
        raise AutocadError(f"Operation {i} (rectangle) needs [x, y] corners.")
    x1, y1, x2, y2 = float(c1[0]), float(c1[1]), float(c2[0]), float(c2[1])
    if x1 == x2 or y1 == y2:
        raise AutocadError(
            f"Operation {i} (rectangle) corners {c1} and {c2} share an X or Y "
            "value, giving a rectangle with no area."
        )
    corners = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    return _polyline_pairs(op, corners, closed=True)


# ---------------------------------------------------------------------------
# mtext, solid hatch and linear dimensions (#51, D-96)
# ---------------------------------------------------------------------------

# DXF group 71 of MTEXT: which point of the text box sits on its position.
MTEXT_ATTACH = {
    "top_left": 1, "top_center": 2, "top_right": 3,
    "middle_left": 4, "middle_center": 5, "middle_right": 6,
    "bottom_left": 7, "bottom_center": 8, "bottom_right": 9,
}
for _name, _code in list(MTEXT_ATTACH.items()):
    MTEXT_ATTACH[_name.replace("center", "centre")] = _code
MTEXT_ATTACH.update({"center": 5, "centre": 5, "middle": 5})

# The longest piece of an MTEXT string one DXF group holds. Longer text is
# sent as group 3 pieces ahead of the last piece in group 1.
MTEXT_PIECE = 250


def mtext_pieces(value: str, size: int = MTEXT_PIECE) -> list[str]:
    """A long MTEXT string cut into the pieces DXF holds: every one but the last goes in group 3."""
    text = str(value)
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def _build_mtext(op: dict[str, Any], i: int) -> list[str]:
    text = str(_require(op, "text", i))
    if not text:
        raise AutocadError(f"Operation {i} (mtext) has no text.")
    height = float(op.get("height", 2.5))
    width = float(op.get("width") or 0.0)
    if height <= 0 or width < 0:
        raise AutocadError(f"Operation {i} (mtext) needs a height above 0 and a width of 0 (no wrapping) or more.")
    attach = str(op.get("attach", "top_left")).strip().lower()
    if attach not in MTEXT_ATTACH:
        raise AutocadError(
            f"Operation {i} (mtext) has attach '{op.get('attach')}'. Use one of: "
            + ", ".join(sorted(k for k in MTEXT_ATTACH if "centre" not in k)) + "."
        )
    pairs = [dotted(0, lisp_string("MTEXT")), dotted(100, lisp_string("AcDbEntity"))]
    if op.get("layer"):
        pairs.append(dotted(8, lisp_string(str(op["layer"]).strip())))
    aci = to_aci(op.get("color"))
    if aci is not None:
        pairs.append(dotted(62, str(aci)))
    pairs.append(dotted(100, lisp_string("AcDbMText")))
    pairs.append(dotted(10, lisp_point(_require(op, "position", i))))
    pairs.append(dotted(40, lisp_number(height)))
    pairs.append(dotted(41, lisp_number(width)))
    pairs.append(dotted(71, str(MTEXT_ATTACH[attach])))
    pieces = mtext_pieces(text)
    pairs.extend(dotted(3, lisp_string(piece)) for piece in pieces[:-1])
    pairs.append(dotted(1, lisp_string(pieces[-1])))
    if op.get("style"):
        pairs.append(dotted(7, lisp_string(str(op["style"]).strip())))
    if op.get("rotation"):
        pairs.append(dotted(50, lisp_number(rad(op["rotation"]))))
    return pairs


def _loop(points: Any, bulges: Any, i: int, what: str) -> tuple[list[list[float]], list[float]]:
    """One closed hatch loop: its vertices (a repeated last point dropped) and a bulge for each."""
    if not isinstance(points, (list, tuple)):
        raise AutocadError(f"Operation {i} (hatch) {what} must be a list of [x, y] points.")
    pts = [list(p) for p in points]
    for n, vertex in enumerate(pts):
        if len(vertex) < 2:
            raise AutocadError(f"Operation {i} (hatch) {what} vertex {n} is {vertex!r}; it needs [x, y].")
    curves = [float(b) for b in (bulges or [])]
    if len(curves) > len(pts):
        raise AutocadError(
            f"Operation {i} (hatch) {what} has {len(curves)} bulges for {len(pts)} vertices; "
            "a bulge belongs to the segment leaving its vertex."
        )
    if len(pts) > 1 and math.dist(pts[0][:2], pts[-1][:2]) <= 1e-9:
        pts.pop()
        curves = curves[: len(pts)]
    curves += [0.0] * (len(pts) - len(curves))
    arcs = any(abs(b) > 1e-12 for b in curves)
    if len(pts) < (2 if arcs else 3):
        raise AutocadError(
            f"Operation {i} (hatch) {what} has {len(pts)} distinct corners; a filled area needs "
            "three, or two joined by arcs."
        )
    return pts, curves


def _loop_pairs(pts: list[list[float]], curves: list[float], flag: int) -> list[str]:
    """A polyline boundary path: type flag, bulge flag, closed, the count, then each vertex."""
    arcs = any(abs(b) > 1e-12 for b in curves)
    pairs = [dotted(92, str(flag)), dotted(72, "1" if arcs else "0"), dotted(73, "1"), dotted(93, str(len(pts)))]
    for vertex, bulge in zip(pts, curves, strict=True):
        pairs.append(dotted(10, f"(list {lisp_number(vertex[0])} {lisp_number(vertex[1])})"))
        if arcs:
            pairs.append(dotted(42, lisp_number(bulge)))
    pairs.append(dotted(97, "0"))
    return pairs


# Boundary path type flags (DXF group 92): 1 external, 2 polyline.
OUTER_LOOP = 1 | 2
HOLE_LOOP = 2


def _build_hatch(op: dict[str, Any], i: int) -> list[str]:
    """A SOLID fill bounded by its own outline, not tied to any object.

    The batch fills only: a pattern needs its line definitions written out,
    which entmake cannot read from acad.pat. autocad_add_hatch does patterns.
    """
    pattern = str(op.get("pattern", "SOLID")).strip().upper()
    if pattern != "SOLID":
        raise AutocadError(
            f"Operation {i} (hatch) asks for pattern '{op.get('pattern')}'. The batch makes solid "
            "fills only; for a pattern draw the outline, then autocad_add_hatch on it."
        )
    outer = _loop(_require(op, "points", i), op.get("bulges"), i, "points")
    holes = []
    for n, hole in enumerate(op.get("holes") or []):
        if isinstance(hole, dict):
            holes.append(_loop(hole.get("points"), hole.get("bulges"), i, f"hole {n}"))
        else:
            holes.append(_loop(hole, None, i, f"hole {n}"))
    pairs = [dotted(0, lisp_string("HATCH")), dotted(100, lisp_string("AcDbEntity"))]
    if op.get("layer"):
        pairs.append(dotted(8, lisp_string(str(op["layer"]).strip())))
    aci = to_aci(op.get("color"))
    if aci is not None:
        pairs.append(dotted(62, str(aci)))
    pairs.append(dotted(100, lisp_string("AcDbHatch")))
    pairs.append(dotted(10, lisp_point([0.0, 0.0, float(op.get("elevation") or 0.0)])))
    pairs.append(dotted(210, lisp_point([0.0, 0.0, 1.0])))
    pairs.append(dotted(2, lisp_string("SOLID")))
    pairs.append(dotted(70, "1"))  # solid fill
    pairs.append(dotted(71, "0"))  # not associative: it has no boundary object to follow
    pairs.append(dotted(91, str(1 + len(holes))))
    pairs.extend(_loop_pairs(*outer, OUTER_LOOP))
    for hole in holes:
        pairs.extend(_loop_pairs(*hole, HOLE_LOOP))
    pairs.append(dotted(75, "0"))  # normal: a hole inside the outline stays empty
    pairs.append(dotted(76, "1"))  # predefined (SOLID)
    pairs.append(dotted(98, "1"))
    first = outer[0][0]
    pairs.append(dotted(10, f"(list {lisp_number(first[0])} {lisp_number(first[1])})"))
    return pairs


# Which way a linear dimension measures: along its two points, or along an angle.
DIMENSION_AXIS = {"horizontal": 0.0, "vertical": 90.0}
LINEAR_DIMENSIONS = ("aligned", "horizontal", "vertical", "rotated")


def linear_dimension(
    point1: Sequence[float],
    point2: Sequence[float],
    text_at: Sequence[float],
    angle: float | None = None,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Where a linear dimension's line is: DXF group 10 and the text point, group 11.

    Group 10 is where the dimension line meets the second extension line.
    The line runs through ``text_at``: along point1 -> point2 for an aligned
    dimension, along ``angle`` (degrees) for a rotated one. Plain arithmetic,
    so it is tested without AutoCAD.
    """
    x1, y1 = float(point1[0]), float(point1[1])
    x2, y2 = float(point2[0]), float(point2[1])
    tx, ty = float(text_at[0]), float(text_at[1])
    if angle is None:
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 1e-12:
            raise ValueError("the two points are at one place, so there is nothing to measure")
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        nx, ny = -dy, dx
        offset = (tx - x1) * nx + (ty - y1) * ny
        return (x2 + offset * nx, y2 + offset * ny), (tx, ty)
    a = math.radians(float(angle))
    dx, dy = math.cos(a), math.sin(a)
    along = (x2 - tx) * dx + (y2 - ty) * dy
    if abs((x2 - x1) * dx + (y2 - y1) * dy) < 1e-12:
        raise ValueError("the two points are square across that direction, so it measures nothing")
    return (tx + along * dx, ty + along * dy), (tx, ty)


def _build_dimension(op: dict[str, Any], i: int) -> list[str]:
    kind = str(op.get("dimension_type", "aligned")).strip().lower()
    if kind not in LINEAR_DIMENSIONS:
        raise AutocadError(
            f"Operation {i} (dimension) is '{op.get('dimension_type')}'. The batch makes linear "
            "dimensions: " + ", ".join(LINEAR_DIMENSIONS) + ". For radial, diametric or angular "
            "use autocad_add_dimension."
        )
    p1, p2 = _require(op, "point1", i), _require(op, "point2", i)
    if len(p1) < 2 or len(p2) < 2:
        raise AutocadError(f"Operation {i} (dimension) needs [x, y] points.")
    given = op.get("text_position")
    text_at = given if given is not None else [(p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0]
    if len(text_at) < 2:
        raise AutocadError(f"Operation {i} (dimension) text_position must be [x, y].")
    if kind == "rotated" and op.get("angle") is None:
        raise AutocadError(f"Operation {i} (dimension) is 'rotated' and needs 'angle' in degrees.")
    angle = None if kind == "aligned" else float(op["angle"]) if kind == "rotated" else DIMENSION_AXIS[kind]
    try:
        line_end, text_point = linear_dimension(p1, p2, text_at, angle)
    except ValueError as exc:
        raise AutocadError(f"Operation {i} (dimension): {exc}.") from exc
    z = float(p1[2]) if len(p1) > 2 else 0.0
    # 1 aligned / 0 rotated; 32: the block is this dimension's own; 128: the
    # text sits where it was put, not at the middle.
    flags = (1 if angle is None else 0) | 32 | (128 if given is not None else 0)
    pairs = [dotted(0, lisp_string("DIMENSION")), dotted(100, lisp_string("AcDbEntity"))]
    if op.get("layer"):
        pairs.append(dotted(8, lisp_string(str(op["layer"]).strip())))
    aci = to_aci(op.get("color"))
    if aci is not None:
        pairs.append(dotted(62, str(aci)))
    pairs.append(dotted(100, lisp_string("AcDbDimension")))
    pairs.append(dotted(10, lisp_point([line_end[0], line_end[1], z])))
    pairs.append(dotted(11, lisp_point([text_point[0], text_point[1], z])))
    pairs.append(dotted(70, str(flags)))
    if op.get("ucs_rotation"):
        pairs.append(dotted(51, lisp_number(-rad(op["ucs_rotation"]))))
    if op.get("text_override"):
        pairs.append(dotted(1, lisp_string(str(op["text_override"]))))
    style = str(op.get("style") or "").strip()
    # The drawing's current dimension style unless one is named: read inside
    # AutoCAD as the batch runs, so nothing has to be asked first.
    pairs.append(dotted(3, lisp_string(style) if style else '(getvar "DIMSTYLE")'))
    pairs.append(dotted(100, lisp_string("AcDbAlignedDimension")))
    pairs.append(dotted(13, lisp_point(p1)))
    pairs.append(dotted(14, lisp_point(p2)))
    if angle is not None:
        pairs.append(dotted(50, lisp_number(rad(angle))))
        pairs.append(dotted(100, lisp_string("AcDbRotatedDimension")))
    # The drawing's current DIMSCALE as this dimension's own override, as
    # DIMLINEAR would give it (0, scaled to the layout, included): without it a
    # dimension takes the plain style size and comes out tiny in a scaled
    # detail. autocad_add_dimension does the same over COM, where only a
    # value above 0 can be set.
    pairs.append(
        '(list -3 (list "ACAD" (cons 1000 "DSTYLE") (cons 1002 "{") (cons 1070 40)'
        ' (cons 1040 (getvar "DIMSCALE")) (cons 1002 "}")))'
    )
    return pairs


# Which field of an operation holds a point, a run of points, or an angle.
# Used only on the coords='ucs' path, to rewrite a batch before it is built.
_POINT_FIELDS: dict[str, tuple[str, ...]] = {
    "line": ("start", "end"),
    "circle": ("center",),
    "arc": ("center",),
    "point": ("position",),
    "text": ("position",),
    "mtext": ("position",),
    "dimension": ("point1", "point2", "text_position"),
}
_POINT_RUN_FIELDS: dict[str, tuple[str, ...]] = {"polyline": ("points",), "hatch": ("points",)}
# A bulge is the shape of a segment, not a position or a direction, so turning
# the UCS leaves every one of them alone; only a flipped UCS (a mirror) turns
# its sign over. An arc's two angles are converted together (arc_to_world).
_ANGLE_FIELDS: dict[str, tuple[str, ...]] = {
    "text": ("rotation",),
    "mtext": ("rotation",),
}
# What would read mirrored on a flipped UCS, and so is refused there (D-96).
_HANDED = {"text": "text", "mtext": "text", "dimension": "a dimension"}


def _turn_rectangle(op: dict[str, Any], ucs: Ucs) -> dict[str, Any]:
    """A two-corner rectangle in a UCS, as the four-corner polyline it really is.

    Square to the modeller's turned grid is not square to the world, so the
    two corners cannot stay two corners. A degenerate one is handed back
    untouched so _build_rectangle still reports it by operation number.
    """
    c1, c2 = op.get("corner1") or [], op.get("corner2") or []
    if len(c1) < 2 or len(c2) < 2:
        return dict(op)
    x1, y1, x2, y2 = float(c1[0]), float(c1[1]), float(c2[0]), float(c2[1])
    if x1 == x2 or y1 == y2:
        return dict(op)
    turned = {k: v for k, v in op.items() if k not in ("corner1", "corner2")}
    turned["type"] = "polyline"
    turned["closed"] = True
    turned["points"] = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    return turned


def _flat_height(moved: dict[str, Any], field: str) -> None:
    """A flat object's one height (group 38, or a hatch's elevation), taken from its first converted vertex."""
    run_of = moved.get(field) or []
    if run_of and len(run_of[0]) > 2 and abs(float(run_of[0][2])) > 1e-9:
        moved["elevation"] = float(run_of[0][2])


def _turn_dimension(moved: dict[str, Any], ucs: Ucs) -> None:
    """Horizontal and vertical mean the UCS's own X and Y, so in the world they become rotated."""
    kind = str(moved.get("dimension_type", "aligned")).strip().lower()
    if ucs.rotation_degrees:
        # DXF group 51: which way is "horizontal" for the text, as DIMLINEAR
        # writes it in a turned UCS (minus the UCS's angle), so text that is
        # kept horizontal reads along the UCS's X, not the world's.
        moved["ucs_rotation"] = ucs.rotation_degrees
    if kind in DIMENSION_AXIS or (kind == "rotated" and moved.get("angle") is not None):
        base = DIMENSION_AXIS[kind] if kind in DIMENSION_AXIS else float(moved["angle"])
        moved["dimension_type"] = "rotated"
        moved["angle"] = ucs.angle_to_world(base)


def to_world_ops(
    operations: Sequence[dict[str, Any]], ucs: Ucs | None
) -> list[dict[str, Any]]:
    """Operations given in a UCS, rewritten as the world ones entmake needs.

    ``entmake`` writes straight into the drawing database, which holds world
    coordinates only: unlike the command line, it never applies the current
    UCS. So the conversion happens here, in plain Python, before one
    expression is built - and is therefore tested without AutoCAD.

    ``ucs`` of None (coords='world', or a drawing with no UCS set) hands the
    batch back unchanged, so the world path costs nothing.
    """
    if ucs is None:
        return [dict(op) if isinstance(op, dict) else op for op in operations]
    out: list[dict[str, Any]] = []
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            out.append(op)
            continue
        kind = str(op.get("type", "")).strip().lower()
        if ucs.flipped and kind in _HANDED:
            raise AutocadError(
                f"Operation {index} ({kind}): the drawing's current UCS is flipped (its Z points "
                f"down), so {_HANDED[kind]} drawn here would read mirrored in that view. Set a UCS "
                "that is not flipped, or draw it with coords='world'."
            )
        moved = dict(op)
        if kind == "rectangle":
            moved = _turn_rectangle(op, ucs)
            kind = str(moved.get("type", "")).strip().lower()
        for field in _POINT_FIELDS.get(kind, ()):
            value = moved.get(field)
            if value is not None and len(value) >= 2:
                moved[field] = list(ucs.to_world(value))
        for field in _POINT_RUN_FIELDS.get(kind, ()):
            run_of = moved.get(field)
            if run_of:
                moved[field] = [
                    list(ucs.to_world(v)) if len(v) >= 2 else v for v in run_of
                ]
        for field in _ANGLE_FIELDS.get(kind, ()):
            # Left out means 0, which on a turned UCS is the UCS's own X: it turns too.
            moved[field] = ucs.angle_to_world(moved.get(field) or 0.0)
        if kind == "arc" and moved.get("start_angle") is not None and moved.get("end_angle") is not None:
            moved["start_angle"], moved["end_angle"] = ucs.arc_to_world(moved["start_angle"], moved["end_angle"])
        if kind in ("polyline", "hatch"):
            if ucs.flipped and moved.get("bulges"):
                moved["bulges"] = [ucs.bulge_to_world(b) for b in moved["bulges"]]
            _flat_height(moved, "points")
        if kind == "hatch" and moved.get("holes"):
            moved["holes"] = [_turn_hole(hole, ucs) for hole in moved["holes"]]
        if kind == "dimension":
            _turn_dimension(moved, ucs)
        out.append(moved)
    return out


def _turn_hole(hole: Any, ucs: Ucs) -> Any:
    """One hole of a hatch, given as points or as {"points", "bulges"}, in the world."""
    if isinstance(hole, dict):
        turned = dict(hole)
        if hole.get("points"):
            turned["points"] = [list(ucs.to_world(v)) if len(v) >= 2 else v for v in hole["points"]]
        if ucs.flipped and hole.get("bulges"):
            turned["bulges"] = [ucs.bulge_to_world(b) for b in hole["bulges"]]
        return turned
    if isinstance(hole, (list, tuple)):
        return [list(ucs.to_world(v)) if isinstance(v, (list, tuple)) and len(v) >= 2 else v for v in hole]
    return hole


BUILDERS = {
    "line": _build_line,
    "circle": _build_circle,
    "arc": _build_arc,
    "point": _build_point,
    "text": _build_text,
    "polyline": _build_polyline,
    "rectangle": _build_rectangle,
    "mtext": _build_mtext,
    "hatch": _build_hatch,
    "dimension": _build_dimension,
}


@mcp.tool(
    name="autocad_batch_draw",
    **tool_meta("Batch Draw Geometry"),
)
@tool_errors
async def autocad_batch_draw(
    operations: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "Entities to create, in order. Each is an object with a 'type' "
                "and that type's fields, plus optional 'layer' and 'color'. "
                "Angles are DEGREES; coordinates are in the drawing's units.\n\n"
                'line: {"type":"line","start":[0,0],"end":[100,0]}\n'
                'polyline: {"type":"polyline","points":[[0,0],[10,0],[10,5]],'
                '"closed":true}\n'
                '  arcs: add "bulges":[0,0.4142,0] - one per vertex, for the '
                "segment leaving it. Bulge is tan(sweep/4), positive "
                "anticlockwise; 0.4142 is a 90 degree arc. This is how a "
                "fillet, a slot or an elbow stays one object.\n"
                'rectangle: {"type":"rectangle","corner1":[0,0],'
                '"corner2":[100,50]}\n'
                'circle: {"type":"circle","center":[0,0],"radius":25} '
                "(or \"diameter\")\n"
                'arc: {"type":"arc","center":[0,0],"radius":25,'
                '"start_angle":0,"end_angle":90}\n'
                'text: {"type":"text","position":[0,0],"text":"ROOM 1",'
                '"height":2.5,"rotation":0}\n'
                '  justification: add "align":"center" (or "right") to sit the '
                'text on its point instead of starting from it - what a bubble '
                'or a tag needs. "style" picks a text style by name.\n'
                'point: {"type":"point","position":[0,0]}\n'
                'mtext: {"type":"mtext","position":[0,0],"text":"NOTE 1\\\\PNOTE 2",'
                '"width":3000,"height":2.5} - width 0 for no wrapping; "attach" '
                '(top_left default, middle_center, bottom_right ...), "rotation", '
                '"style"\n'
                'hatch: {"type":"hatch","points":[[0,0],[10,0],[5,8]]} - a SOLID '
                'fill of that closed outline: an arrowhead, a north point, a '
                'filled symbol. "bulges" as for a polyline; "holes": [[...], ...] '
                'or [{"points":[...],"bulges":[...]}] stay empty. Solid only - a '
                'pattern needs autocad_add_hatch.\n'
                'dimension: {"type":"dimension","point1":[0,0],"point2":[5000,0],'
                '"text_position":[2500,-500]} - "dimension_type" aligned '
                '(default), horizontal, vertical or rotated (with "angle"); the '
                'dimension line runs through text_position. "text_override", '
                '"style" (else the current one). Radial, diametric and angular: '
                'autocad_add_dimension.\n\n'
                'Example with styling: {"type":"line","start":[0,0],'
                '"end":[5000,0],"layer":"A-WALL","color":"red"}'
            ),
            min_length=1,
            max_length=MAX_OPERATIONS,
        ),
    ],
    return_handles: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "Return the handle of every entity created, so the batch can "
                "be modified or hatched afterwards. Capturing handles roughly "
                "doubles the run time, so turn it off for large batches you "
                "will not need to touch again — the created and failed counts "
                "are reported either way."
            ),
        ),
    ] = True,
    coords: Annotated[str, COORDS_OPT] = "world",
    quiet: Annotated[bool, QUIET_FIELD] = False,
) -> str:
    """Create many entities at once, far faster than one call per entity.

    Use this whenever you are drawing more than about ten things — a floor
    plan, a grid, a hatch pattern of lines, a set of labels. It sends a single
    AutoLISP script that runs inside AutoCAD, instead of one COM round trip per
    entity, and the whole batch lands as one undo step.

    Measured on AutoCAD 2020, 200 lines: 20.3s one at a time through the
    autocad_draw_* tools, 2.2s through this one — about 9x, or 17x with
    return_handles=false.

    Every operation is validated in Python before anything is sent, so a
    malformed batch fails naming the offending operation index and changes
    nothing in the drawing.

    Layers named by any operation are created automatically if they do not
    exist.

    Args:
        operations (list[dict]): The entities to create. See the field
            description for the shape of each type.
        return_handles (bool): Return each new entity's handle. Roughly doubles
            the run time; turn off for large batches you will not modify.
        coords (str): "world" (default) or "ucs" to read every point and angle
            in the drawing's current UCS. A rectangle given in a turned UCS
            comes out turned, as a drafter would expect.
        quiet (bool): counts and handles only (#44): the UCS it converted
            from is named, not described. The answer is short already.

    Returns:
        str: JSON: {
          "created": int,          # entities actually made
          "failed": int,           # operations AutoCAD rejected
          "requested": int,
          "handles": [str],        # in order; empty if return_handles=false
          "completed": bool,       # false if the script died partway
          "layers_created": [str],
          "elapsed_seconds": float,
          "entities_per_second": float
        }

    Examples:
        - Use when: "draw this 20 x 15 m grid at 1 m spacing" — 36 lines in one
          call rather than 36.
        - Use when: placing a room's worth of walls, doors and labels together.
        - Use when: a symbol needs a solid head or a filled half - a hatch
          operation with the outline's points beside its polyline.
        - Don't use when: creating one or two entities, or when you need the
          richer validation and per-entity feedback of autocad_draw_* tools.

    Error Handling:
        - An unknown operation type, or a missing required field, is reported
          with its index before the batch runs.
        - If AutoCAD rejects individual operations (locked layer, degenerate
          geometry), "failed" counts them and "created" reflects what did land.
    """
    result = await draw_operations(operations, return_handles, coords)
    if quiet:
        result = quieted(result)
        ucs = result.get("converted_from_ucs")
        if isinstance(ucs, dict):
            result["converted_from_ucs"] = ucs.get("name") or "an unnamed UCS"
    return dumps(result)


async def draw_operations(
    operations: Sequence[dict[str, Any]],
    return_handles: bool = True,
    coords: str = "world",
) -> dict[str, Any]:
    """Validate, build and send a run of operations. The engine behind two tools.

    ``autocad_batch_draw`` takes the operations from the caller;
    ``autocad_make_shape`` generates them from a shape's settings. Both end up
    here, so there is one place that validates a batch, one that converts a UCS
    and one that talks to AutoCAD.
    """
    # coords='ucs': read the UCS before validating, so the whole batch is still
    # checked and built before anything is sent. One extra read, and only on
    # this path.
    ucs = None
    if str(coords).strip().lower() == "ucs":

        def read_ucs() -> Any:
            return ucs_for(get_doc(), "ucs")

        ucs = await run(read_ucs)
    operations = to_world_ops(operations, ucs)

    # Validate and generate everything up front: a batch that cannot be fully
    # built should not half-draw itself.
    entities: list[list[str]] = []
    layers_needed: set[str] = set()

    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            raise AutocadError(
                f"Operation {index} is {type(op).__name__}, but each operation "
                "must be an object with a 'type' field."
            )
        kind = str(op.get("type", "")).strip().lower()
        if kind not in BUILDERS:
            raise AutocadError(
                f"Operation {index} has type '{op.get('type')}', which this "
                "tool cannot create. Supported types: "
                + ", ".join(sorted(BUILDERS))
                + ". For blocks use autocad_insert_block; for a hatch pattern "
                "(the batch fills solid only) autocad_add_hatch; for radial, "
                "diametric or angular dimensions autocad_add_dimension."
            )
        entities.append(BUILDERS[kind](op, index))
        if op.get("layer"):
            layers_needed.add(str(op["layer"]).strip())

    token = uuid.uuid4().hex[:12]
    output_path = os.path.join(tempfile.gettempdir(), f"mcp_batch_{token}.txt")
    # Built before anything is sent, so an operation too long to send fails
    # with its index and nothing half-drawn.
    chunks = build_chunks(entities, return_handles, output_path)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        # From here the drawing changes (layers, then the LISP batch): a busy
        # signal must not re-run it, and the gate must know it wrote.
        mark_writing()

        # entmake will not create a layer, so any that are missing are made
        # over COM first. This is a handful of calls, not one per entity.
        created_layers = []
        for layer_name in sorted(layers_needed):
            _, was_created = ensure_layer(doc, layer_name)
            if was_created:
                created_layers.append(layer_name)

        started = time.monotonic()
        # Short expressions, never a loaded file: a .lsp loaded from %TEMP%
        # makes AutoCAD's SECURELOAD ask about an unsigned executable. The
        # Heron plug-in types them with echo off; without it (or an older
        # plug-in) they go over COM and show in the command history.
        sender = quiet_sender()
        if not (sender and sender(chunks)):
            for chunk in chunks:
                doc.SendCommand(chunk + "\n")

        text = ""
        while time.monotonic() - started < OUTPUT_TIMEOUT:
            if os.path.isfile(output_path):
                with open(output_path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                if "DONE" in text or "ERROR " in text:
                    break
            time.sleep(OUTPUT_POLL)
        elapsed = time.monotonic() - started

        if not text:
            raise AutocadError(
                "The batch produced no output within "
                f"{OUTPUT_TIMEOUT:.0f}s. Check AutoCAD's command line (F2) for a "
                "prompt or an error waiting there, press Esc, and read the drawing "
                "back before retrying: part of the batch may already be drawn."
            )

        result = parse_output(text, expected=len(entities))
        result["layers_created"] = created_layers
        if ucs is not None:
            result["converted_from_ucs"] = ucs.describe()
        result["elapsed_seconds"] = round(elapsed, 3)
        if elapsed > 0:
            result["entities_per_second"] = round(result["created"] / elapsed, 1)
        return result

    try:
        return await run(work)
    finally:
        try:
            os.remove(output_path)
        except OSError:
            pass
