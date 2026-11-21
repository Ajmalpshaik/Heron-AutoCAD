"""Splines, multilines and wipeouts: the drafting objects the single-entity tools lack.

A spline and a multiline have their own Automation calls (AddSpline, AddMLine).
A wipeout has none, so it is typed as the WIPEOUT command, with every point in
world coordinates and object snaps off, and the new object is found afterwards.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..acad.coords import as_vec3
from ..acad.curves import curve_length
from ..acad.entities import resolve_handle
from ..acad.geometry import MOST_SPLINE_DEGREE, control_spline
from ..acad.tables import apply_properties
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, double_array, group_coordinates
from . import _shared
from ._shared import (
    COLOR_OPT,
    COORDS_OPT,
    LAYER_OPT,
    LINETYPE_OPT,
    PLUGIN_ONLY,
    SPACE_OPT,
    before_after,
    created_payload,
    in_plugin,
    plugin_created,
    ucs_for,
    ucs_used,
    world_coords,
    world_direction,
)

Vec3 = tuple[float, float, float]


def _try(getter, default=None):
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def _unit(vector: Sequence[float]) -> Vec3 | None:
    x, y, z = as_vec3(vector)
    length = math.sqrt(x * x + y * y + z * z)
    if length < 1e-12:
        return None
    return (x / length, y / length, z / length)


def _drop_closing(points: Sequence[Sequence[float]]) -> list[Sequence[float]]:
    """The points without a last one that repeats the first: a closed shape closes itself."""
    pts = list(points)
    if len(pts) > 1 and math.dist(as_vec3(pts[0]), as_vec3(pts[-1])) <= 1e-9:
        pts.pop()
    return pts


def _first_direction(points: Sequence[Vec3]) -> Vec3 | None:
    for a, b in zip(points, points[1:], strict=False):
        found = _unit((b[0] - a[0], b[1] - a[1], b[2] - a[2]))
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------------
# Spline
# ---------------------------------------------------------------------------


def spline_tangents(
    points: Sequence[Sequence[float]],
    start: Sequence[float] | None = None,
    end: Sequence[float] | None = None,
) -> tuple[Vec3, Vec3]:
    """The start and end tangents AddSpline needs, as unit vectors.

    AddSpline takes both and Autodesk does not say what a zero one does, so a
    zero is never sent: an end left out follows the first (or last) segment
    that has a length.
    """
    pts = [as_vec3(p) for p in points]
    if len(pts) < 2:
        raise ValueError("a spline needs at least two points")
    along = _first_direction(pts)
    back = _first_direction(list(reversed(pts)))
    if along is None or back is None:
        raise ValueError("the points are all at one place, so they give the spline no direction")
    if start is not None:
        along = _unit(start)
        if along is None:
            raise ValueError("start_tangent cannot be all zeros; leave it out to follow the first segment")
    if end is not None:
        back = _unit(end)
        if back is None:
            raise ValueError("end_tangent cannot be all zeros; leave it out to follow the last segment")
        return along, back
    return along, (-back[0], -back[1], -back[2])


@mcp.tool(name="autocad_draw_spline", **tool_meta("Draw A Spline"))
@tool_errors
async def autocad_draw_spline(
    points: Annotated[
        list[list[float]],
        Field(min_length=2, description="In order, as [[x, y], ...] or [[x, y, z], ...]. With method 'fit_points' (the default) the curve passes through every one; with 'control_points' they are the frame the curve is pulled towards."),
    ],
    closed: Annotated[bool, Field(default=False, description="Close the curve back to its first point smoothly, e.g. an irregular planting bed or a kidney-shaped opening.")] = False,
    start_tangent: Annotated[list[float] | None, Field(default=None, description="Which way the curve leaves its first point, as [x, y, z]. Omit to follow the first segment. Fit points only.")] = None,
    end_tangent: Annotated[list[float] | None, Field(default=None, description="Which way the curve arrives at its last point, as [x, y, z]. Omit to follow the last segment. Fit points only.")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    linetype: Annotated[str | None, LINETYPE_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
    coords: Annotated[str, COORDS_OPT] = "world",
    method: Annotated[str, Field(default="fit_points", pattern="^(fit_points|control_points)$", description="'fit_points' (default): through the points, SPLINE's Fit method. 'control_points': the points are the control vertices, SPLINE's CV method - a smoother, fairer curve that touches only the first and last point (made by Heron's plug-in).")] = "fit_points",
    degree: Annotated[int, Field(default=3, ge=1, le=MOST_SPLINE_DEGREE, description="Control points only: 1 draws straight between them, 2 is gentle, 3 (default) is the usual smooth curve. Needs one more point than the degree.")] = 3,
) -> str:
    """Draw a smooth spline through the points given, or pulled by them as control points.

    By fit points (the SPLINE command's default): the curve goes through
    every point, not near them. The ends leave and arrive along the first and
    last segments unless tangents are given.

    By control points (SPLINE's CV method): the points are the frame the
    curve follows; it starts on the first and ends on the last, and leaves
    along the first and last legs. Closed, it comes round smoothly with no
    corner where it started. Made by Heron's plug-in, as COM has no call for it.

    One undo step.

    Args:
        points (list[list[float]]): the fit points, or the control points.
        closed (bool): close it smoothly back to the first point.
        start_tangent / end_tangent (Optional[list[float]]): end directions,
            fit points only.
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour name or ACI number.
        linetype (Optional[str]): linetype name.
        space (str): 'model' or 'paper'.
        coords (str): 'world' or 'ucs'.
        method (str): 'fit_points' or 'control_points'.
        degree (int): 1-10, control points only.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "spline",
             "layer": str, "fit_points": int, "closed": bool,
             "length": float, "not_set": [str]}
             By control points: "control_points" and "degree" in place of
             "fit_points".

    Examples:
        - Use when: "draw a flexible duct from the grille to the diffuser" —
          the route as points.
        - Use when: "draw a curved boundary / contour / landscape edge through
          these points".
        - Use when: "a smooth fair curve using these as control vertices" —
          method='control_points', degree=3.
        - Don't use when: the curve is made of arcs and straights — that is a
          polyline (autocad_draw_polyline or autocad_batch_draw with bulges).
        - Don't use when: the spline is drawn and only its points move —
          autocad_edit_spline.

    Error Handling:
        - Fewer than two points, points all at one place, or a zero tangent are
          refused before anything is drawn.
        - By control points: too few points for the degree, two in a row at one
          place, or tangents given are refused before anything is drawn; so is
          running without the plug-in.
        - A closed spline AutoCAD will not close is drawn open and says so in
          "not_set".
    """
    for i, p in enumerate(points):
        if len(p) < 2:
            raise AutocadError(f"Point {i} must be [x, y] or [x, y, z]; got {p}.")
    if method == "control_points":
        return dumps(await _control_spline(points, closed, start_tangent, end_tangent, degree, layer, color,
                                           linetype, space, coords))
    fit = _drop_closing(points) if closed else list(points)
    if closed and len(fit) < 3:
        raise AutocadError("A closed spline needs at least three points.")
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        world = [tuple(world_coords(p, ucs)) for p in fit]
        try:
            start, end = spline_tangents(
                world,
                world_direction(start_tangent, ucs) if start_tangent else None,
                world_direction(end_tangent, ucs) if end_tangent else None,
            )
        except ValueError as exc:
            raise AutocadError(str(exc)) from exc
        flat = [v for p in world for v in p]
        not_set: list[str] = []

        with undo_mark(doc):
            entity = get_space(doc, space).AddSpline(double_array(flat), apoint(*start), apoint(*end))
            is_closed = False
            if closed:
                try:
                    # Closed2 is the writable one; Closed only reads.
                    entity.Closed2 = True
                    is_closed = True
                except BaseException as exc:  # noqa: BLE001 - drawn open, and said
                    not_set.append(f"closed ({com_message(exc)})")
            notes = apply_properties(doc, entity, layer, aci, linetype)

        length = _try(lambda: curve_length(entity))
        payload = created_payload(
            entity,
            notes,
            fit_points=len(world),
            closed=is_closed,
            length=round(length, 6) if isinstance(length, float) else None,
        )
        if not_set:
            payload["not_set"] = not_set
        return ucs_used(payload, ucs)

    return dumps(await run(work))


async def _control_spline(points: list[list[float]], closed: bool, start_tangent: Any, end_tangent: Any,
                          degree: int, layer: str | None, color: Any, linetype: str | None, space: str,
                          coords: str) -> dict[str, Any]:
    """A spline by its control points, made by the plug-in (D-97): the knots are worked out here."""
    if start_tangent is not None or end_tangent is not None:
        raise AutocadError(
            "Tangents go with method='fit_points'. A control-point spline leaves along its first leg and "
            "arrives along its last: move the second or the second-last point to steer it."
        )
    if _shared.plugin_runner() is None:
        raise AutocadError(PLUGIN_ONLY.format(what="A spline by control points"))
    try:
        control_spline(points, degree, closed)  # refuse a bad frame before AutoCAD is touched
    except ValueError as exc:
        raise AutocadError(f"{exc}.") from exc
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        world = [world_coords(p, ucs) for p in points]
        control, knots = control_spline(world, degree, closed)
        with undo_mark(doc):
            report = in_plugin(
                "add_cv_spline",
                {"points": [v for p in control for v in p], "knots": knots, "degree": int(degree),
                 "space": space, "layer": layer.strip() if layer else None, "color": aci},
                "A spline by control points",
            )
            payload = plugin_created(doc, report)
            if linetype:
                try:
                    payload.update(apply_properties(doc, doc.HandleToObject(payload["handle"]), None, None, linetype))
                except Exception as exc:  # noqa: BLE001 - drawn; the linetype is said, not raised
                    payload["not_set"] = [f"linetype ({com_message(exc)})"]
        payload.setdefault("closed", bool(closed))
        payload.setdefault("degree", int(degree))
        payload.setdefault("control_points", len(control))
        return ucs_used(payload, ucs)

    return await run(work)


# ---------------------------------------------------------------------------
# Editing a spline's fit points
# ---------------------------------------------------------------------------


def plan_fit_edits(
    current: Sequence[Sequence[float]], edits: Sequence[dict[str, Any]], closed: bool = False
) -> tuple[list[dict[str, Any]], list[list[float]], list[dict[str, Any]]]:
    """A spline's fit points after a list of edits, and the steps that get there.

    Each edit is one of {"move": i, "to": point}, {"insert": i, "point": point}
    (the new point becomes number i; the count adds after the last) or
    {"remove": i}, numbered from 0 as the points stand when that edit comes.
    Points are world [x, y, z] by now. Returns (steps for the plug-in, the
    points that should be there after, and one before / after row per point
    moved, added or removed).
    """
    pts = [list(as_vec3(p)) for p in current]
    if not pts:
        raise ValueError("this spline has no fit points: it was drawn by its control points")
    steps: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for n, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise ValueError(f"edit {n} must be an object such as {{\"move\": 2, \"to\": [x, y]}}")
        kinds = [k for k in ("move", "insert", "remove") if k in edit]
        if len(kinds) != 1:
            raise ValueError(f"edit {n} must be exactly one of move, insert or remove")
        kind = kinds[0]
        index = edit[kind]
        if isinstance(index, bool) or not isinstance(index, int):
            raise ValueError(f"edit {n}: '{kind}' takes a point number, counted from 0")
        if kind == "move":
            if not 0 <= index < len(pts):
                raise ValueError(f"edit {n} moves point {index}, but the spline has {len(pts)} (0 to {len(pts) - 1})")
            to = edit.get("to")
            if not isinstance(to, (list, tuple)) or len(to) < 2:
                raise ValueError(f"edit {n} needs 'to' as [x, y] or [x, y, z]")
            new = list(as_vec3(to))
            rows.append({"property": f"fit point {index}", "from": pts[index], "to": new})
            pts[index] = new
            steps.append({"kind": "set", "index": index, "point": new})
        elif kind == "insert":
            if not 0 <= index <= len(pts):
                raise ValueError(f"edit {n} adds point {index}, but the spline has {len(pts)} (0 to {len(pts)} to add)")
            at = edit.get("point")
            if not isinstance(at, (list, tuple)) or len(at) < 2:
                raise ValueError(f"edit {n} needs 'point' as [x, y] or [x, y, z]")
            new = list(as_vec3(at))
            pts.insert(index, new)
            rows.append({"property": f"fit point {index}", "from": None, "to": new})
            steps.append({"kind": "insert", "index": index, "point": new})
        else:
            if not 0 <= index < len(pts):
                raise ValueError(f"edit {n} removes point {index}, but the spline has {len(pts)} (0 to {len(pts) - 1})")
            rows.append({"property": f"fit point {index}", "from": pts.pop(index), "to": None})
            steps.append({"kind": "remove", "index": index})
    least = 3 if closed else 2
    if len(pts) < least:
        raise ValueError(f"that leaves {len(pts)} fit points; a {'closed ' if closed else ''}spline needs {least}")
    ring = pts + ([pts[0]] if closed else [])
    for a, b in zip(ring, ring[1:], strict=False):
        if math.dist(a, b) <= 1e-9:
            raise ValueError(f"two fit points in a row would be at one place ({[round(v, 6) for v in a]})")
    return steps, pts, rows


EDITS_OPT = Field(
    min_length=1,
    max_length=200,
    description=(
        "The changes, in order. Each is one of:\n"
        '{"move": 2, "to": [x, y]} - fit point 2 goes to that place;\n'
        '{"insert": 3, "point": [x, y]} - a new point becomes number 3 (the count adds after the last);\n'
        '{"remove": 4} - fit point 4 goes.\n'
        "Numbered from 0, as the points stand when that edit comes. autocad_get_entity lists them."
    ),
)


@mcp.tool(name="autocad_edit_spline", **tool_meta("Edit A Spline's Fit Points"))
@tool_errors
async def autocad_edit_spline(
    handle: Annotated[str, Field(min_length=1, description="The spline to change.")],
    edits: Annotated[list[dict[str, Any]], EDITS_OPT],
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Move, add or take away the fit points of a spline that is already drawn.

    SPLINEDIT's Fit data: the spline keeps its handle, layer and end tangents
    and is refitted through the new points. Done by Heron's plug-in, which
    checks the points it ends with against the ones asked for; anything else
    and nothing is changed. One undo step.

    Args:
        handle (str): the spline.
        edits (list[dict]): moves, inserts and removes, in order.
        coords (str): 'world' or 'ucs' for the points given.

    Returns:
        str: JSON: {"edited": true, "handle": str, "fit_points_before": int,
             "fit_points": int, "closed": bool, "points": [[x, y, z]],
             "before_after": [{"handle", "property", "from", "to"}]}

    Examples:
        - Use when: "move the third point of that duct spline to 4200,1800" ->
          edits=[{"move": 2, "to": [4200, 1800]}].
        - Use when: "add a point between points 1 and 2 so the curve clears
          the column" -> {"insert": 2, "point": [...]}.
        - Use when: "take out the kink at point 4" -> {"remove": 4}.
        - Don't use when: the spline was drawn by control points - it has no
          fit points; redraw it with autocad_draw_spline.
        - Don't use when: the whole curve moves - autocad_move_entities.

    Error Handling:
        - A point number off the end, two points in a row at one place, or too
          few points left are refused before anything is changed, naming the
          edit.
        - A spline with no fit points (drawn by control points) is refused.
        - Without the plug-in it is refused before anything is read.
    """
    if _shared.plugin_runner() is None:
        raise AutocadError(PLUGIN_ONLY.format(what="Editing a spline's fit points"))

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        spline = resolve_handle(doc, handle)
        if str(_try(lambda: spline.ObjectName, "")) != "AcDbSpline":
            raise AutocadError(f"{handle} is not a spline. Give the handle of a spline (autocad_list_entities type='spline').")
        current = group_coordinates(_try(lambda: spline.FitPoints, []) or [], 3)
        is_closed = bool(_try(lambda: spline.Closed, False))
        given = []
        for edit in edits:
            moved = dict(edit) if isinstance(edit, dict) else edit
            if isinstance(moved, dict):
                for field in ("to", "point"):
                    if isinstance(moved.get(field), (list, tuple)) and len(moved[field]) >= 2:
                        moved[field] = world_coords(moved[field], ucs)
            given.append(moved)
        try:
            steps, result, rows = plan_fit_edits(current, given, is_closed)
        except ValueError as exc:
            raise AutocadError(f"{handle}: {exc}. Nothing was changed.") from exc
        with undo_mark(doc):
            report = in_plugin(
                "edit_spline_fit_points",
                {"handle": str(handle), "steps": steps, "result": [v for p in result for v in p]},
                "Editing a spline's fit points",
            )
        payload: dict[str, Any] = {
            "edited": True,
            "handle": str(report.get("handle") or handle),
            "fit_points_before": int(report.get("fit_points_before", len(current))),
            "fit_points": int(report.get("fit_points", len(result))),
            "closed": bool(report.get("closed", is_closed)),
            "points": [[round(v, 6) for v in p] for p in result],
            **before_after([{"handle": str(handle), **row} for row in rows]),
        }
        return ucs_used(payload, ucs)

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Multiline
# ---------------------------------------------------------------------------

# AcMLineJustification: which side of the points the lines run.
MLINE_JUSTIFICATION = {"top": 0, "zero": 1, "centre": 1, "center": 1, "middle": 1, "bottom": 2}


@mcp.tool(name="autocad_draw_multiline", **tool_meta("Draw A Multiline (MLINE)"))
@tool_errors
async def autocad_draw_multiline(
    points: Annotated[
        list[list[float]],
        Field(min_length=2, description="The vertices, in order, as [[x, y], ...]: a wall's centre line, or its face line with justification 'top' or 'bottom'."),
    ],
    scale: Annotated[float | None, Field(default=None, gt=0, description="Width scale. The STANDARD style is 1 unit wide, so this is the wall or duct thickness: 200 for a 200 mm wall. Omit to keep the drawing's CMLSCALE.")] = None,
    justification: Annotated[str, Field(default="zero", description="'zero' (the points are the centre line), 'top' or 'bottom' (the points are one face).")] = "zero",
    style: Annotated[str | None, Field(default=None, description="Multiline style, already in the drawing (MLSTYLE makes one). Omit for the current one.")] = None,
    closed: Annotated[bool, Field(default=False, description="Come back to the first point, e.g. a room, with the last corner mitred like the rest (MLINE's own Close, done by Heron's plug-in).")] = False,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Draw a multiline (MLINE): parallel lines that turn corners together, like a wall.

    One object for a run of wall, a double-line duct or a road in plan,
    with its style, width and justification - the way MLINE draws it.

    One undo step.

    Args:
        points (list[list[float]]): the vertices, in order.
        scale (Optional[float]): width scale; with STANDARD, the thickness.
        justification (str): 'zero', 'top' or 'bottom'.
        style (Optional[str]): a multiline style already in the drawing.
        closed (bool): come back to the first point.
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour name or ACI number.
        space (str): 'model' or 'paper'.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "multiline",
             "layer": str, "style": str, "scale": float,
             "justification": str, "vertices": int, "not_set": [str]}

    Examples:
        - Use when: "draw a 200 mm wall along these points" — scale=200.
        - Use when: "MLINE a double line along the grid" — the grid points.
        - Use when: "draw a double-line duct 400 wide" — scale=400.
        - Don't use when: you need a solid wall to cut, hatch or quantify —
          a closed polyline (autocad_draw_polyline) or autocad_make_shape.

    Error Handling:
        - A style the drawing does not have is refused before anything is
          drawn, naming MLSTYLE and autocad_import_from_drawing.
        - Automation has no "close" for a multiline, so a closed one is drawn
          open and Heron's plug-in closes it the way MLINE's Close does,
          mitring the last corner ("mitred": true). Without the plug-in, or if
          it cannot, the first point is repeated instead: the last corner
          overlaps, "mitred" is false and the result says so.
        - The drawing's current multiline style is put back afterwards.
    """
    key = str(justification).strip().lower()
    if key not in MLINE_JUSTIFICATION:
        raise AutocadError(f"'{justification}' is not a justification. Use 'zero', 'top' or 'bottom'.")
    for i, p in enumerate(points):
        if len(p) < 2:
            raise AutocadError(f"Point {i} must be [x, y]; got {p}.")
    vertices = _drop_closing(points) if closed else list(points)
    if closed and len(vertices) < 3:
        raise AutocadError("A closed multiline needs at least three points.")
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        world = [world_coords(p, ucs) for p in vertices]
        # The plug-in closes it the way MLINE's Close does, mitring the last
        # corner (D-97). Without the plug-in the first point is repeated, and
        # that corner overlaps.
        by_plugin = closed and _shared.plugin_runner() is not None
        if closed and not by_plugin:
            world.append(list(world[0]))
        flat = [float(v) for p in world for v in p]
        not_set: list[str] = []
        before = None
        if style:
            # Read first: a style that cannot be put back is not changed at all.
            try:
                before = str(doc.GetVariable("CMLSTYLE"))
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(
                    f"The drawing's current multiline style could not be read ({com_message(exc)}), "
                    "so it is not changed. Draw without 'style', or set it with CMLSTYLE first."
                ) from exc
        with undo_mark(doc):
            if style:
                try:
                    doc.SetVariable("CMLSTYLE", str(style).strip())
                except BaseException as exc:  # noqa: BLE001
                    raise AutocadError(
                        f"This drawing has no multiline style called '{style}' ({com_message(exc)}). "
                        "Make it with MLSTYLE, or copy it in with autocad_import_from_drawing."
                    ) from exc
            try:
                entity = get_space(doc, space).AddMLine(double_array(flat))
                for prop, value in (("Justification", MLINE_JUSTIFICATION[key]),
                                    ("MLineScale", float(scale) if scale else None)):
                    if value is None:
                        continue
                    try:
                        setattr(entity, prop, value)
                    except BaseException as exc:  # noqa: BLE001 - drawn, and said
                        not_set.append(f"{prop} ({com_message(exc)})")
                notes = apply_properties(doc, entity, layer, aci, None)
            finally:
                # Inside the undo step, so one Ctrl+Z takes the multiline and the style back.
                if before is not None:
                    _try(lambda: doc.SetVariable("CMLSTYLE", before))
            mitred, why = (close_multiline(entity, flat) if by_plugin else (False, ""))

        payload = created_payload(
            entity,
            notes,
            style=_try(lambda: str(entity.StyleName)) or style,
            scale=_try(lambda: round(float(entity.MLineScale), 6)),
            justification=key,
            vertices=len(vertices),
        )
        if closed:
            payload["closed"] = True
            payload["mitred"] = mitred
        if closed and not mitred:
            mitre = (
                "Closed by repeating the first point" + (f" ({why})" if why else
                ": Heron's plug-in is not in this job, and Automation has no close for a multiline") +
                ", so the last corner overlaps rather than being mitred. Where it shows, close it "
                "with MLINE's Close option."
            )
            payload["warning"] = f"{payload['warning']} {mitre}" if payload.get("warning") else mitre
        if not_set:
            payload["not_set"] = not_set
        return ucs_used(payload, ucs)

    return dumps(await run(work))


def close_multiline(entity: Any, flat: list[float]) -> tuple[bool, str]:
    """Have the plug-in close a multiline just drawn, mitring its last corner; (mitred, why not). Never raises.

    The multiline is drawn already, so an error would send the chat round to
    draw it twice. If the plug-in cannot close it, the first point is added
    again over COM - the old way, overlapped - and why is said.
    """
    handle = str(entity.Handle)
    try:
        report = in_plugin("close_multiline", {"handle": handle}, "Closing a multiline")
        if report.get("closed"):
            return True, ""
        why = "Heron's plug-in did not close it"
    except AutocadError as exc:
        why = f"Heron's plug-in could not close it: {exc}"
    try:
        entity.Coordinates = double_array(list(flat) + list(flat[:3]))
    except BaseException as exc:  # noqa: BLE001 - drawn open; said
        why += f"; adding the first point again failed too ({com_message(exc)}), so it is drawn OPEN"
    return False, why


# ---------------------------------------------------------------------------
# Wipeout
# ---------------------------------------------------------------------------

# WIPEOUTFRAME: whether wipeout edges show. One setting for the whole drawing.
WIPEOUT_FRAMES = {"hide": 0, "show": 1, "show_no_plot": 2}

# How long a typed command gets to finish before a prompt still open means it
# did not take its input. SendCommand normally returns with the command done.
COMMAND_WAIT_S = 2.0
COMMAND_POLL_S = 0.1


def _num(value: float) -> str:
    """A coordinate as typed: fixed point to 8 places, never an exponent, no trailing zeros."""
    text = f"{float(value):.8f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def wipeout_command(points: Sequence[Sequence[float]]) -> str:
    """The WIPEOUT command line for an outline: every point world, unsnapped.

    '*' takes a typed point in world coordinates whatever the UCS (and with
    dynamic input on); '_non' keeps a running object snap off it. A blank line
    closes the outline, which WIPEOUT always does itself.
    """
    pts: list[tuple[float, float]] = []
    for p in points:
        if len(p) < 2:
            raise ValueError(f"every point needs [x, y]; got {list(p)}")
        xy = (float(p[0]), float(p[1]))
        if not pts or math.hypot(xy[0] - pts[-1][0], xy[1] - pts[-1][1]) > 1e-9:
            pts.append(xy)
    if len(pts) > 1 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= 1e-9:
        pts.pop()
    if len(pts) < 3:
        raise ValueError("a wipeout needs at least three distinct corners")
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True)) / 2.0
    if abs(area) < 1e-9:
        raise ValueError("those corners are in a line, so the wipeout would have no area")
    lines = ["_.WIPEOUT"] + [f"_non *{_num(x)},{_num(y)}" for x, y in pts]
    return "\n".join(lines) + "\n\n"


def _outline_of(doc: Any, handle: str) -> tuple[Any, list[list[float]]]:
    """The corners of a closed, straight-sided polyline, and the polyline."""
    outline = resolve_handle(doc, handle)
    if str(_try(lambda: outline.ObjectName, "")) != "AcDbPolyline":
        raise AutocadError(f"{handle} is not a polyline. Give a closed polyline, or the corners as points.")
    if not bool(_try(lambda: outline.Closed, False)):
        raise AutocadError(f"{handle} is an open polyline; a wipeout needs a closed outline.")
    normal = _try(lambda: as_vec3(outline.Normal))
    if normal is not None and abs(normal[2] - 1.0) > 1e-9:
        raise AutocadError(
            f"{handle} is drawn on a flipped or tilted plane (its normal is {list(normal)}), so its "
            "corners are not plain world X and Y. Give the corners as points instead."
        )
    flat = [float(v) for v in outline.Coordinates]
    corners = [flat[i : i + 2] for i in range(0, len(flat) - 1, 2)]
    if any(abs(float(_try(lambda i=i: outline.GetBulge(i), 0.0) or 0.0)) > 1e-9 for i in range(len(corners))):
        raise AutocadError(
            f"{handle} has arcs in it, and wipeout edges are straight. Give a polyline of "
            "straight segments, or the corners as points."
        )
    return outline, corners


def _wait_for_new(doc: Any, target: Any, before: int) -> tuple[Any, bool]:
    """The object a typed command made, once it is there and AutoCAD is back at its prompt.

    Returns (the newest object or None, whether a command was still asking).
    SendCommand normally returns with the command done; the wait covers the
    times it starts late.
    """
    deadline = time.monotonic() + COMMAND_WAIT_S
    while True:
        busy = bool(_try(lambda: int(doc.GetVariable("CMDACTIVE")), 0))
        count = int(_try(lambda: target.Count, before))
        if not busy and count > before:
            return target.Item(count - 1), False
        if time.monotonic() >= deadline:
            return None, busy
        time.sleep(COMMAND_POLL_S)


@mcp.tool(name="autocad_add_wipeout", **tool_meta("Add A Wipeout"))
@tool_errors
async def autocad_add_wipeout(
    points: Annotated[list[list[float]] | None, Field(default=None, description="The corners of the area to mask, as [[x, y], ...] in world coordinates. Or give boundary_handle.")] = None,
    boundary_handle: Annotated[str | None, Field(default=None, description="A closed polyline of straight segments to use as the outline, instead of points.")] = None,
    erase_boundary: Annotated[bool, Field(default=False, description="With boundary_handle: delete that polyline once the wipeout is made, as WIPEOUT's own 'Erase polyline? Yes'.")] = False,
    frames: Annotated[str | None, Field(default=None, description="WIPEOUTFRAME for the whole drawing: 'hide', 'show', or 'show_no_plot' (seen on screen, not plotted). Omit to leave it.")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
) -> str:
    """Mask an area with a wipeout, so what is behind it does not show or plot.

    A WIPEOUT, in the space that is current (model or the active layout).
    Typical: clear the hatch or grid behind a tag, a note or a block.

    Automation has no call that makes a wipeout, so this types the WIPEOUT
    command with every corner in world coordinates and snaps off, then finds
    the object it made. One undo step.

    Args:
        points (Optional[list[list[float]]]): the outline's corners.
        boundary_handle (Optional[str]): or a closed straight-sided polyline.
        erase_boundary (bool): delete that polyline afterwards.
        frames (Optional[str]): 'hide', 'show' or 'show_no_plot', for the drawing.
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour name or ACI number.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "wipeout",
             "layer": str, "corners": int, "boundary_erased": bool,
             "not_set": [str]}

    Examples:
        - Use when: "mask the hatch behind this tag" — the tag's box as points.
        - Use when: "turn this closed outline into a wipeout" — boundary_handle,
          erase_boundary=true.
        - Use when: "hide the wipeout frames" — frames='hide' (or
          'show_no_plot' to see them on screen only).
        - Don't use when: it is only a text background — autocad_add_label
          and MText have a background mask of their own.

    Error Handling:
        - Fewer than three corners, corners in a line, an open polyline or one
          with arcs are refused before anything is typed.
        - If AutoCAD is still asking when the command should be done, it is
          cancelled and the tool says so; nothing is left half made.
    """
    if (points is None) == (boundary_handle is None):
        raise AutocadError("Give the outline either as points or as boundary_handle, not both or neither.")
    if erase_boundary and boundary_handle is None:
        raise AutocadError("erase_boundary goes with boundary_handle.")
    frame_key = str(frames).strip().lower() if frames is not None else None
    if frame_key is not None and frame_key not in WIPEOUT_FRAMES:
        raise AutocadError(f"'{frames}' is not a frames setting. Use 'hide', 'show' or 'show_no_plot'.")
    if points is not None:
        try:
            wipeout_command(points)  # refuse a bad outline before AutoCAD is touched
        except ValueError as exc:
            raise AutocadError(str(exc)) from exc
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        outline, corners = None, points
        if boundary_handle is not None:
            outline, corners = _outline_of(doc, boundary_handle)
        try:
            typed = wipeout_command(corners)
        except ValueError as exc:
            raise AutocadError(f"{boundary_handle}: {exc}" if boundary_handle else str(exc)) from exc
        # WIPEOUT draws where the work is: model space on the Model tab, and also
        # inside a layout viewport that is active (ActiveSpace still says paper).
        in_model = int(_try(lambda: doc.ActiveSpace, 1)) == 1 or bool(_try(lambda: doc.MSpace, False))
        target = doc.ModelSpace if in_model else doc.PaperSpace
        if outline is not None:
            owner, here = _try(lambda: outline.OwnerID), _try(lambda: target.ObjectID)
            if owner is not None and here is not None and owner != here:
                raise AutocadError(
                    f"{boundary_handle} is not in {'model' if in_model else 'paper'} space, where the "
                    "wipeout would be drawn (that is where the work is now). Switch to its space "
                    "first, or give the corners as points."
                )
        before = int(target.Count)
        not_set: list[str] = []

        with undo_mark(doc):
            doc.SendCommand(typed)
            made, busy = _wait_for_new(doc, target, before)
            if made is None or str(_try(lambda: made.ObjectName, "")) != "AcDbWipeout":
                # Cancel whichever way it went, so AutoCAD is never left at the prompt.
                _try(lambda: doc.SendCommand("\x1b\x1b"))
                raise AutocadError(
                    "AutoCAD did not take the WIPEOUT input and was left asking; it has been "
                    "cancelled and no wipeout was kept. Check that no other command was running."
                    if busy else
                    "AutoCAD finished WIPEOUT but no wipeout came out of it; nothing was kept."
                )
            if frame_key is not None:
                try:
                    doc.SetVariable("WIPEOUTFRAME", WIPEOUT_FRAMES[frame_key])
                except BaseException as exc:  # noqa: BLE001 - this release may lack it
                    not_set.append(f"frames ({com_message(exc)})")
            notes = apply_properties(doc, made, layer, aci, None)
            erased = False
            if outline is not None and erase_boundary:
                try:
                    outline.Delete()
                    erased = True
                except BaseException as exc:  # noqa: BLE001 - the wipeout stands either way
                    not_set.append(f"erase_boundary ({com_message(exc)})")

        payload = created_payload(made, notes, corners=len(corners or []), boundary_erased=erased)
        if not_set:
            payload["not_set"] = not_set
        return payload

    return dumps(await run(work))

