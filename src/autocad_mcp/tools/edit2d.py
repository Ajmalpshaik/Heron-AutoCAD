"""The everyday 2D edits: trim, extend, fillet, chamfer, break, join, move a vertex,
stretch, explode, draw order, match properties and groups.

Issues #103, #49, #105, #111 and #110 (D-78, D-79). The new shape is worked out
in plain Python (acad/edit2d.py, tested without AutoCAD) and written back by
setting each object's own points over COM. Nothing is typed on AutoCAD's command
line, so no command is ever left waiting for a pick (known limit 21). Each call
is one undo step; a call with nothing to do writes nothing and opens no step.
Everything here works in plan, on objects drawn flat: what AutoCAD's own TRIM
does with PROJMODE at its default.
"""

from __future__ import annotations

import fnmatch
import math
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import Field

from ..acad import edit2d as geo
from ..acad import props
from ..acad.curves import read_path
from ..acad.entities import read_attributes, resolve_handle, short_type
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, double_array, object_array
from ._shared import (
    COORDS_OPT,
    HANDLES_OPT,
    before_after,
    same_value,
    ucs_for,
    world_coords,
    world_direction,
)

# The objects whose shape these tools change, and those they cut or reach to.
TARGETS = {"AcDbLine": "line", "AcDbArc": "arc", "AcDbCircle": "circle", "AcDbPolyline": "polyline"}
EDGES = {**TARGETS, "AcDb2dPolyline": "old-style 2D polyline"}

LOCKED_HINT = (
    "An object usually refuses a change because its layer is locked. Unlock it with "
    "autocad_set_layer_state, then try again."
)


# ---- reading and writing a curve ------------------------------------------------------


def _name(entity: Any) -> str:
    try:
        return str(entity.ObjectName)
    except BaseException:  # noqa: BLE001 - an object that cannot say what it is
        return ""


def _flat(entity: Any) -> float:
    """The object's height (Z), after checking it lies flat in plan."""
    name = _name(entity)
    handle = str(entity.Handle)
    if name == "AcDbLine":
        s, e = entity.StartPoint, entity.EndPoint
        if abs(float(s[2]) - float(e[2])) > 1e-9 * max(1.0, abs(float(s[2])), abs(float(e[2]))):
            raise AutocadError(
                f"{handle} is a sloping line (its two ends are at different heights). These edits work "
                "in plan, on flat objects only."
            )
        return float(s[2])
    try:
        n = entity.Normal
        tilted = abs(float(n[0])) > 1e-9 or abs(float(n[1])) > 1e-9 or float(n[2]) <= 0
    except BaseException:  # noqa: BLE001 - no Normal: nothing to check
        tilted = False
    if tilted:
        raise AutocadError(
            f"{handle} is drawn on a tilted or flipped plane, not flat in plan. These edits work on "
            "objects drawn flat in the world XY plane only."
        )
    if name in ("AcDbArc", "AcDbCircle"):
        return float(entity.Center[2])
    try:
        return float(entity.Elevation)
    except BaseException:  # noqa: BLE001 - no elevation means 0
        return 0.0


def _path(entity: Any, allowed: dict[str, str] = TARGETS) -> geo.Path:
    name = _name(entity)
    if name not in allowed:
        kinds = ", ".join(sorted(set(allowed.values())))
        raise AutocadError(f"{entity.Handle} is a {short_type(entity)}; this works on a {kinds}.")
    raw = read_path(entity)
    return geo.make_path(raw["vertices"], raw["bulges"], raw["closed"])


def _width(entity: Any) -> float:
    """A polyline's one width (0 for none); refused when it changes along the polyline."""
    if _name(entity) != "AcDbPolyline":
        return 0.0
    varying = AutocadError(
        f"{entity.Handle} is a polyline whose width changes along it. Heron would lose those widths; "
        "change its shape in AutoCAD instead."
    )
    try:
        width = float(entity.ConstantWidth)
    except BaseException as exc:  # noqa: BLE001 - AutoCAD has no one width to give
        raise varying from exc
    count = len(_path(entity)["bulges"])
    for i in range(count):
        try:
            start, end = entity.GetWidth(i)
        except BaseException:  # noqa: BLE001 - cannot read it: trust ConstantWidth
            break
        if abs(float(start) - width) > 1e-9 or abs(float(end) - width) > 1e-9:
            raise varying
    return width


def _owner(doc: Any, entity: Any) -> Any:
    """The space (model space or a layout) the object is in."""
    return doc.ObjectIdToObject(entity.OwnerID)


def _same_owner(entities: Sequence[Any]) -> None:
    owners = {str(_try(lambda e=e: e.OwnerID)) for e in entities}
    if len(owners) > 1:
        raise AutocadError("Those objects are not all in the same space (model space or one layout).")


def _try(getter: Any, default: Any = None) -> Any:
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - this object has no such property
        return default


def _unlocked(doc: Any, entity: Any) -> None:
    """Refuse an object on a locked layer before anything is written, so no half-made edit is left."""
    try:
        layer = str(entity.Layer)
        locked = bool(doc.Layers.Item(layer).Lock)
    except BaseException:  # noqa: BLE001 - cannot tell: AutoCAD will refuse the write itself
        return
    if locked:
        raise AutocadError(
            f"{entity.Handle} is on the locked layer '{layer}'. Unlock it with autocad_set_layer_state, "
            "then try again."
        )


def _distinct(handles: Sequence[str]) -> None:
    seen = [str(h).strip().upper() for h in handles]
    if len(set(seen)) != len(seen):
        raise AutocadError("The same object is given twice.")


STYLE = ("Layer", "Linetype", "LinetypeScale", "Lineweight", "EntityTransparency")


def _copy_style(source: Any, target: Any) -> None:
    """Give a new piece the look of the object it came from."""
    try:
        target.TrueColor = source.TrueColor
    except BaseException:  # noqa: BLE001 - older object model: the colour number
        try:
            target.Color = source.Color
        except BaseException:  # noqa: BLE001
            pass
    for attr in STYLE:
        try:
            setattr(target, attr, getattr(source, attr))
        except BaseException:  # noqa: BLE001 - not on this kind of object
            pass


def _write_polyline(entity: Any, path: geo.Path, width: float) -> None:
    if bool(entity.Closed) and not path["closed"]:
        entity.Closed = False
    entity.Coordinates = double_array([c for v in path["vertices"] for c in (v[0], v[1])])
    for i in range(len(path["vertices"])):
        entity.SetBulge(i, path["bulges"][i] if i < len(path["bulges"]) else 0.0)
    if path["closed"]:
        entity.Closed = True
    if width:
        entity.ConstantWidth = width


def _write(entity: Any, path: geo.Path, z: float, width: float) -> None:
    """Give an existing line, arc or polyline this shape."""
    name = _name(entity)
    if name == "AcDbLine":
        (x0, y0), (x1, y1) = path["vertices"][0], path["vertices"][-1]
        entity.StartPoint = apoint(x0, y0, z)
        entity.EndPoint = apoint(x1, y1, z)
    elif name == "AcDbArc":
        arc = geo.arc_of(path)
        entity.StartAngle = arc["start_angle"]
        entity.EndAngle = arc["end_angle"]
    elif name == "AcDbPolyline":
        _write_polyline(entity, path, width)
    else:
        raise AutocadError(f"{entity.Handle} is a {short_type(entity)}; its shape cannot be written here.")


def _circle_to_arc(doc: Any, circle: Any, piece: geo.Path, z: float) -> Any:
    """What is left of a circle after a cut, as a new arc with the circle's look; the circle goes."""
    c = circle.Center
    cx, cy = float(c[0]), float(c[1])
    (x0, y0), (x1, y1) = piece["vertices"][0], piece["vertices"][-1]
    start = math.atan2(y0 - cy, x0 - cx) % (2 * math.pi)
    end = math.atan2(y1 - cy, x1 - cx) % (2 * math.pi)
    if abs(start - end) <= 1e-12:
        raise AutocadError("A circle cannot be opened at a single point; give a second point.")
    arc = _owner(doc, circle).AddArc(apoint(cx, cy, z), float(circle.Radius), start, end)
    _copy_style(circle, arc)
    circle.Delete()
    return arc


def _write_pieces(doc: Any, entity: Any, pieces: list[geo.Path], z: float, width: float) -> dict[str, Any]:
    """Write the pieces left: the first into the object itself, each other into a copy of it."""
    handle = str(entity.Handle)  # read now: an erased object may not answer afterwards
    if _name(entity) == "AcDbCircle":
        arc = _circle_to_arc(doc, entity, pieces[0], z)
        return {"handle": handle, "replaced_by": str(arc.Handle),
                "note": "A cut circle is an arc: the circle was replaced by a new arc with its look."}
    copies = [entity.Copy() for _ in pieces[1:]]
    try:
        # The copies first: if one will not take its shape, the object itself is still whole.
        for target, piece in zip(copies, pieces[1:], strict=True):
            _write(target, piece, z, width)
        _write(entity, pieces[0], z, width)
    except BaseException:
        for extra in copies:  # leave no half-made piece behind
            _try(extra.Delete)
        raise
    out: dict[str, Any] = {"handle": handle}
    if copies:
        out["new_handles"] = [str(c.Handle) for c in copies]
    return out


def _flat_point(value: Sequence[float] | None, ucs: Any, name: str) -> tuple[float, float]:
    if not value or len(value) < 2:
        raise AutocadError(f"'{name}' must be a point as [x, y], got {value!r}.")
    x, y, _ = world_coords(value, ucs)
    return (x, y)


def _failure(handle: str, exc: BaseException) -> dict[str, str]:
    if isinstance(exc, (AutocadError, ValueError)):
        return {"handle": handle, "reason": str(exc)}
    return {"handle": handle, "reason": com_message(exc)}


def _finish(result: dict[str, Any], failed: list[dict[str, str]]) -> dict[str, Any]:
    if failed:
        result["failed"] = failed
    return result


# ---- trim and extend ---------------------------------------------------------------------


@mcp.tool(name="autocad_trim_extend", **tool_meta("Trim or Extend"))
@tool_errors
async def autocad_trim_extend(
    operation: Annotated[
        str,
        Field(
            description=(
                "'trim' cuts an object back to the cutting edges, removing the part you point at; "
                "'extend' runs an object's end on until it meets a boundary."
            ),
            pattern="^(trim|extend)$",
        ),
    ],
    handles: Annotated[
        list[str],
        Field(
            min_length=1,
            description="The lines, arcs, circles or polylines to trim or extend (a circle can be trimmed only).",
        ),
    ],
    edges: Annotated[
        list[str],
        Field(
            min_length=1,
            description=(
                "The cutting edges (trim) or boundaries (extend): lines, arcs, circles or polylines, e.g. "
                "the wall line. An object may be both an edge and one to trim; edges are read once, before "
                "anything changes."
            ),
        ),
    ],
    points: Annotated[
        list[list[float]] | None,
        Field(
            default=None,
            description=(
                "One [x, y] per handle, in the same order. Trim: a point on the part to cut away (the "
                "nearest place on the object is used). Extend: a point near the end to extend; leave out "
                "to extend every end that has a boundary ahead of it."
            ),
        ),
    ] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Trim objects back to cutting edges, or extend them to boundaries: AutoCAD's TRIM and EXTEND.

    Works in plan on lines, arcs and polylines (a polyline arc is cut on its
    arc; a closed polyline cut twice opens there; a circle becomes an arc,
    and the circle is erased, so Heron asks the modeller first, D-50). Edges
    count as drawn, not as if they ran on (EDGEMODE 0). Pieces left after a trim
    are the object itself plus copies of it, so layer, colour and data stay.
    An object on a locked layer is refused before anything is written. One undo step.

    Returns:
        JSON: {"operation", "done": n, "objects": [{"handle", "new_handles"?, "cut_away" | "added",
        "ends"?}], "failed": [{"handle", "reason"}]}

    Examples:
        - Use when: "trim the pipe back to the wall" -> operation='trim',
          edges=[the wall line], handles=[the pipe], points=[a point on the
          bit past the wall].
        - Use when: "cut the duct between those two grid lines" -> trim with
          both grid lines as edges and a point between them.
        - Use when: "extend those branch lines to the main" -> operation='extend',
          edges=[the main], handles=[the branches], no points.
        - Don't use when: you want a gap round a valve or symbol on the line -
          use autocad_break_at_blocks; or a gap between two points - use
          autocad_break_curve.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        if points is not None and len(points) != len(handles):
            raise AutocadError(
                f"Give one point per object: {len(handles)} handle(s) but {len(points)} point(s)."
            )
        if operation == "trim" and points is None:
            raise AutocadError("Trim needs 'points': one per object, on the part to cut away.")
        _distinct(handles)
        picks = [_flat_point(p, ucs, "points") for p in points] if points is not None else [None] * len(handles)

        edge_paths: list[tuple[str, geo.Path]] = []
        for h in edges:
            entity = resolve_handle(doc, h)
            _flat(entity)
            edge_paths.append((str(entity.Handle), _path(entity, EDGES)))

        plans: list[tuple[str, Any, list[geo.Path], float, float, dict[str, Any]]] = []
        failed: list[dict[str, str]] = []
        for h, pick in zip(handles, picks, strict=True):
            try:
                entity = resolve_handle(doc, h)
                z = _flat(entity)
                path = _path(entity)
                width = _width(entity)
                _unlocked(doc, entity)
                own = str(entity.Handle)
                others = [p for eh, p in edge_paths if eh != own]
                if not others:
                    raise AutocadError("It is the only edge given; it cannot cut or reach itself.")
                report: dict[str, Any] = {}
                if operation == "trim":
                    cuts = [d for p in others for d in geo.intersections(path, p)]
                    at, _ = geo.project(path, pick)
                    pieces, removed = geo.trim(path, cuts, at)
                    report["cut_away"] = round(removed, 6)
                else:
                    if path["closed"]:
                        raise AutocadError("It is closed, so it has no end to extend.")
                    if pick is not None:
                        first, last = path["vertices"][0], path["vertices"][-1]
                        ends = [math.dist(pick, last) <= math.dist(pick, first)]
                    else:
                        ends = [True, False]
                    added, done_ends = 0.0, []
                    for at_end in ends:
                        grown = geo.extend(path, at_end, others)
                        if grown is not None:
                            path, gain = grown
                            added += gain
                            done_ends.append("end" if at_end else "start")
                    if not done_ends:
                        raise AutocadError("No boundary lies ahead of " + ("that end." if pick else "either end."))
                    pieces = [path]
                    report.update(added=round(added, 6), ends=done_ends)
                if not pieces:
                    raise AutocadError("That would cut all of it away. Delete it instead.")
                plans.append((own, entity, pieces, z, width, report))
            except BaseException as exc:  # noqa: BLE001 - report, carry on with the rest
                failed.append(_failure(h, exc))

        done: list[dict[str, Any]] = []
        if plans:
            with undo_mark(doc):
                for own, entity, pieces, z, width, report in plans:
                    try:
                        done.append({**_write_pieces(doc, entity, pieces, z, width), **report})
                    except BaseException as exc:  # noqa: BLE001
                        failed.append(_failure(own, exc))
        result = {"operation": operation, "done": len(done), "objects": done}
        if failed and not done:
            result["hint"] = LOCKED_HINT
        return _finish(result, failed)

    return dumps(await run(work))


# ---- fillet and chamfer ---------------------------------------------------------------------


@mcp.tool(name="autocad_fillet_chamfer", **tool_meta("Fillet or Chamfer"))
@tool_errors
async def autocad_fillet_chamfer(
    operation: Annotated[
        str,
        Field(description="'fillet' rounds the corner with an arc; 'chamfer' cuts it with a straight line.",
              pattern="^(fillet|chamfer)$"),
    ],
    handles: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=2,
            description=(
                "Two lines that make a corner (they need not touch), or one polyline whose corners to do."
            ),
        ),
    ],
    radius: Annotated[
        float | None,
        Field(default=None, ge=0, description="Fillet radius. 0 joins two lines in a sharp corner."),
    ] = None,
    distance: Annotated[
        float | None,
        Field(
            default=None,
            ge=0,
            description=(
                "Chamfer: how far back from the corner along the first line (or the segment before a "
                "polyline corner). Also the second distance when 'distance2' and 'angle' are left out. "
                "0 with two lines makes a sharp corner."
            ),
        ),
    ] = None,
    distance2: Annotated[
        float | None,
        Field(default=None, ge=0, description="Chamfer: how far back along the second line (or the segment after)."),
    ] = None,
    angle: Annotated[
        float | None,
        Field(
            default=None,
            gt=0,
            lt=180,
            description="Chamfer: the angle in degrees between the first line and the chamfer, instead of 'distance2'.",
        ),
    ] = None,
    vertices: Annotated[
        list[int] | None,
        Field(
            default=None,
            description=(
                "One polyline: the corner numbers to do (0 = its first vertex, as autocad_polyline_info "
                "numbers them). Leave out for every corner."
            ),
        ),
    ] = None,
    keep_points: Annotated[
        list[list[float]] | None,
        Field(
            default=None,
            description=(
                "Two lines that cross: a point on the part of each line to keep, [[x, y], [x, y]]. Left "
                "out, each line keeps its end farther from the corner."
            ),
        ),
    ] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Round a corner with an arc (fillet) or cut it straight (chamfer): two lines, or a polyline's corners.

    Two lines: each is trimmed or extended to the arc's tangent point (or the
    chamfer's end), and the new arc or line takes the first line's layer,
    colour and linetype. A polyline stays one polyline: each corner between two
    straight segments becomes an arc (bulge) or a short straight; a corner next
    to an arc, or on a segment too short, is skipped and said. One undo step.

    Returns:
        JSON: two lines: {"operation", "lines": [h1, h2], "arc" | "chamfer_line": handle | null,
        "corner", "tangent_points"?, "distances"?}; a polyline: {"operation", "handle",
        "corners_done": [n], "skipped": [{"vertex", "reason"}], "vertex_count"}

    Examples:
        - Use when: "put a 150 radius on that duct corner" -> operation='fillet',
          the two lines, radius=150.
        - Use when: "make those two lines meet in a clean corner" ->
          operation='fillet', radius=0.
        - Use when: "round all the corners of the plinth outline at 25" -> one
          polyline, radius=25.
        - Use when: "chamfer that corner 50 by 30" -> operation='chamfer',
          distance=50, distance2=30.
        - Don't use when: the corner is a 3D solid's edge - use
          autocad_fillet_solid_edges or autocad_chamfer_solid_edges.
    """
    if operation == "fillet":
        if radius is None:
            raise AutocadError("A fillet needs 'radius'.")
        if distance is not None or distance2 is not None or angle is not None:
            raise AutocadError("'distance', 'distance2' and 'angle' are for a chamfer; a fillet takes 'radius'.")
    else:
        if distance is None:
            raise AutocadError("A chamfer needs 'distance'.")
        if radius is not None:
            raise AutocadError("'radius' is for a fillet; a chamfer takes 'distance'.")
        if distance2 is not None and angle is not None:
            raise AutocadError("Give 'distance2' or 'angle' for the second side, not both.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        entities = [resolve_handle(doc, h) for h in handles]
        if len(entities) == 1 and keep_points is not None:
            raise AutocadError("'keep_points' is for two lines; for one polyline give 'vertices'.")
        if len(entities) == 2 and vertices is not None:
            raise AutocadError("'vertices' is for one polyline; two lines make one corner.")
        for entity in entities:
            _unlocked(doc, entity)
        if len(entities) == 1:
            return _corners_of_polyline(doc, entities[0])
        return _corner_of_lines(doc, entities, ucs)

    def _corners_of_polyline(doc: Any, entity: Any) -> dict[str, Any]:
        if _name(entity) != "AcDbPolyline":
            raise AutocadError(
                f"{entity.Handle} is a {short_type(entity)}. Give one polyline (its corners are done), or "
                "two lines."
            )
        z = _flat(entity)
        width = _width(entity)
        path = _path(entity)
        if operation == "fillet":
            new, done, skipped = geo.shape_corners(path, radius=radius, vertices=vertices)
        else:
            new, done, skipped = geo.shape_corners(
                path, distance1=distance, distance2=distance2, angle_degrees=angle, vertices=vertices
            )
        if not done:
            reasons = "; ".join(f"vertex {row['vertex']}: {row['reason']}" for row in skipped[:5])
            raise AutocadError(f"No corner could be done, so nothing was changed. {reasons}")
        with undo_mark(doc):
            _write(entity, new, z, width)
        return {
            "operation": operation,
            "handle": str(entity.Handle),
            "corners_done": done,
            "skipped": skipped,
            "vertex_count": len(new["vertices"]),
        }

    def _corner_of_lines(doc: Any, entities: list[Any], ucs: Any) -> dict[str, Any]:
        for entity in entities:
            if _name(entity) != "AcDbLine":
                raise AutocadError(
                    f"{entity.Handle} is a {short_type(entity)}. Heron fillets and chamfers two lines, or the "
                    "corners of one polyline."
                )
        if str(entities[0].Handle) == str(entities[1].Handle):
            raise AutocadError("Give two different lines.")
        _same_owner(entities)
        z1, z2 = _flat(entities[0]), _flat(entities[1])
        if abs(z1 - z2) > 1e-9 * max(1.0, abs(z1), abs(z2)):
            raise AutocadError("The two lines are at different heights, so they do not meet in a corner.")
        lines = [[tuple(e.StartPoint)[:2], tuple(e.EndPoint)[:2]] for e in entities]
        keep = [None, None]
        if keep_points is not None:
            if len(keep_points) != 2:
                raise AutocadError("'keep_points' takes two points, one on each line.")
            keep = [_flat_point(p, ucs, "keep_points") for p in keep_points]
        if operation == "fillet":
            shape = geo.fillet_lines(lines[0], lines[1], float(radius), keep[0], keep[1])
        else:
            shape = geo.chamfer_lines(lines[0], lines[1], float(distance), distance2, angle, keep[0], keep[1])
        result: dict[str, Any] = {"operation": operation, "lines": [str(e.Handle) for e in entities],
                                  "corner": shape["corner"]}
        if operation == "fillet":
            result["arc"] = None
            if shape["arc"]:
                result["tangent_points"] = shape["tangent_points"]
        else:
            result["chamfer_line"] = None
            result["distances"] = shape["distances"]
        new_piece = shape["arc"] if operation == "fillet" else shape["chamfer"]
        eps = geo.tolerance(points=[p for line in lines for p in line])
        moved = [
            any(math.dist(a, b) > eps for a, b in zip(line, shape[key], strict=True))
            for line, key in zip(lines, ("line1", "line2"), strict=True)
        ]
        if not new_piece and not any(moved):
            result["note"] = "NOTHING CHANGED: the two lines already meet in that corner."
            return result
        owner = _owner(doc, entities[0])
        with undo_mark(doc):
            made = None
            if new_piece and operation == "fillet":
                arc = new_piece
                made = owner.AddArc(apoint(arc["centre"][0], arc["centre"][1], z1), arc["radius"],
                                    arc["start_angle"], arc["end_angle"])
            elif new_piece:
                (ax, ay), (bx, by) = new_piece
                made = owner.AddLine(apoint(ax, ay, z1), apoint(bx, by, z1))
            try:
                if made is not None:
                    _copy_style(entities[0], made)
                for entity, key, change in zip(entities, ("line1", "line2"), moved, strict=True):
                    if change:
                        _write(entity, geo.make_path(shape[key]), z1, 0.0)
            except BaseException:
                if made is not None:  # no arc or chamfer line left behind on its own
                    _try(made.Delete)
                raise
            if made is not None:
                result["arc" if operation == "fillet" else "chamfer_line"] = str(made.Handle)
        return result

    return dumps(await run(work))


# ---- break and join ---------------------------------------------------------------------------


@mcp.tool(name="autocad_break_curve", **tool_meta("Break at a Point"))
@tool_errors
async def autocad_break_curve(
    handle: Annotated[str, Field(description="The line, arc, circle or polyline to break.")],
    point: Annotated[
        list[float],
        Field(description="Where to break it, as [x, y]; the nearest place on the object is used."),
    ],
    second_point: Annotated[
        list[float] | None,
        Field(
            default=None,
            description=(
                "Take out the part between 'point' and this one, as [x, y]. Left out, it is cut at 'point' "
                "with no gap. On a closed polyline or circle the part from the first point round to the "
                "second, in the outline's own direction (anticlockwise for a circle), goes."
            ),
        ),
    ] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Break a line, arc, circle or polyline at a point (two pieces, no gap), or take out the part between two points.

    A closed polyline broken at one point opens there; a circle needs two
    points and becomes an arc (the circle is erased, so Heron asks the modeller
    first, D-50). Pieces are the object itself plus copies of it, so layer,
    colour and data stay. One undo step.

    Returns:
        JSON: {"handle", "new_handles"?, "replaced_by"?, "pieces": n, "at": [[x, y], ...]}

    Examples:
        - Use when: "split that pipe at the tee so I can put it on another
          layer" -> point at the tee.
        - Use when: "break this line at a point" / "cut the polyline in two here".
        - Use when: "take 300 out of that line either side of the door" ->
          point and second_point.
        - Don't use when: the gap is round blocks sitting on the line - use
          autocad_break_at_blocks; a dimension crosses it - use
          autocad_break_dimensions; or you want it shorter at an end - use
          autocad_trim_extend.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        entity = resolve_handle(doc, handle)
        z = _flat(entity)
        path = _path(entity)
        width = _width(entity)
        _unlocked(doc, entity)
        first = _flat_point(point, ucs, "point")
        d1, _ = geo.project(path, first)
        at = [geo.point_at(path, d1)]
        if second_point is None:
            if _name(entity) == "AcDbCircle":
                raise AutocadError("A circle cannot be broken at a single point; give 'second_point' as well.")
            pieces = geo.break_at(path, d1)
        else:
            d2, _ = geo.project(path, _flat_point(second_point, ucs, "second_point"))
            at.append(geo.point_at(path, d2))
            pieces = geo.break_between(path, d1, d2)
        with undo_mark(doc):
            out = _write_pieces(doc, entity, pieces, z, width)
        return {**out, "pieces": len(pieces), "at": [[round(p[0], 6), round(p[1], 6)] for p in at]}

    return dumps(await run(work))


@mcp.tool(name="autocad_join_curves", **tool_meta("Join"))
@tool_errors
async def autocad_join_curves(
    handles: Annotated[
        list[str],
        Field(
            min_length=2,
            description=(
                "The lines, arcs and open polylines to join end to end, in any order and direction. The first "
                "one gives the result its layer, colour and linetype."
            ),
        ),
    ],
    gap: Annotated[
        float,
        Field(
            default=0.0,
            ge=0,
            description=(
                "Join ends up to this far apart (the earlier piece's end point is used for the joint). 0 "
                "joins only ends that touch."
            ),
        ),
    ] = 0.0,
) -> str:
    """Join lines, arcs and polylines that meet end to end into one object: AutoCAD's JOIN.

    Lines in one straight line become one line; arcs of one circle one arc;
    anything else one polyline, closed when the run comes back to its start.
    Vertices inside a polyline are kept. The others are erased, so Heron asks
    the modeller to keep them erased (D-50). A branch, a gap or a closed piece is
    refused, saying where. One undo step.

    Returns:
        JSON: {"joined": n, "handle", "kind": "line" | "arc" | "polyline", "closed", "order": [handles],
        "removed": [handles], "vertex_count"}

    Examples:
        - Use when: "make that pipe run one polyline so I can measure it" ->
          all its lines and arcs.
        - Use when: "those two lines are one wall, join them" -> both lines.
        - Use when: "close up the room outline" -> its four lines (comes
          back closed).
        - Don't use when: you only need the total length - use
          autocad_total_length; or the pieces branch - join each branch.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        entities = [resolve_handle(doc, h) for h in handles]
        seen = {str(e.Handle) for e in entities}
        if len(seen) != len(entities):
            raise AutocadError("The same object is given twice.")
        for entity in entities:
            if _name(entity) == "AcDbCircle":
                raise AutocadError(f"{entity.Handle} is a circle: it is closed, so it cannot be joined to anything.")
            _unlocked(doc, entity)
        _same_owner(entities)
        heights = [_flat(e) for e in entities]
        if max(heights) - min(heights) > 1e-9 * max(1.0, *(abs(h) for h in heights)):
            raise AutocadError("Those objects are at different heights (Z), so they do not meet in plan.")
        widths = {round(_width(e), 9) for e in entities if _name(e) == "AcDbPolyline"}
        if len(widths) > 1 or (widths and any(_name(e) != "AcDbPolyline" for e in entities) and widths != {0.0}):
            raise AutocadError("Those objects have different widths; Heron joins pieces of one width only.")
        width = widths.pop() if widths else 0.0
        joined = geo.join([_path(e) for e in entities], gap)
        z = heights[0]
        style = entities[0]
        want = {"line": "AcDbLine", "arc": "AcDbArc", "polyline": "AcDbPolyline"}[joined["kind"]]
        # Keep an object the caller gave wherever one can hold the result, so its handle, data and
        # groups stay: one of the right kind, else a polyline (a polyline holds any shape).
        keeper = next((e for e in entities if _name(e) == want), None) or next(
            (e for e in entities if _name(e) == "AcDbPolyline"), None
        )
        with undo_mark(doc):
            if keeper is None:
                flat = [c for v in joined["path"]["vertices"] for c in v]
                keeper = _owner(doc, style).AddLightWeightPolyline(double_array(flat))
                _copy_style(style, keeper)
                try:
                    keeper.Elevation = z
                except BaseException:  # noqa: BLE001 - stays at 0
                    pass
            elif keeper is not style:
                _copy_style(style, keeper)
            _write(keeper, joined["path"], z, width)
            removed = []
            for entity in entities:
                if entity is not keeper:
                    removed.append(str(entity.Handle))
                    entity.Delete()
        return {
            "joined": len(entities),
            "handle": str(keeper.Handle),
            "kind": TARGETS.get(_name(keeper), joined["kind"]),
            "closed": joined["closed"],
            "order": [handles[i] for i, _ in joined["order"]],
            "removed": removed,
            "vertex_count": len(joined["path"]["vertices"]),
        }

    return dumps(await run(work))


# ---- change the shape: vertices and stretch -------------------------------------------------------


@mcp.tool(name="autocad_edit_vertex", **tool_meta("Edit a Vertex or End Point"))
@tool_errors
async def autocad_edit_vertex(
    handle: Annotated[str, Field(description="The polyline or line to change.")],
    operation: Annotated[
        str,
        Field(
            default="move",
            description=(
                "'move' a vertex (a line's end point), 'add' a vertex on a straight segment, or 'remove' one "
                "(polylines only)."
            ),
            pattern="^(move|add|remove)$",
        ),
    ] = "move",
    vertex: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description=(
                "The vertex number: 0 is the first, as autocad_polyline_info numbers them; a line's start is 0 "
                "and its end 1. For 'add', the new vertex goes after this one."
            ),
        ),
    ] = None,
    near: Annotated[
        list[float] | None,
        Field(default=None, description="Or: the vertex nearest this point, as [x, y] (move and remove)."),
    ] = None,
    to_point: Annotated[
        list[float] | None,
        Field(default=None, description="Move: where the vertex goes. Add: where the new vertex is. As [x, y]."),
    ] = None,
    displacement: Annotated[
        list[float] | None,
        Field(default=None, description="Move: how far to move the vertex, as [dx, dy], instead of 'to_point'."),
    ] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Move one vertex of a polyline or one end of a line; add or remove a polyline vertex.

    An arc next to a moved vertex stays an arc (its bulge is kept, as when you
    drag a grip). Removing a vertex between two arcs makes them one straight
    segment, and says so. One undo step.

    Returns:
        JSON: {"handle", "operation", "vertex", "from"?, "to"?, "vertex_count", "arc_straightened"?}

    Examples:
        - Use when: "that box is drawn 200 too tall, pull its top corners down"
          -> operation='move' on each top vertex, displacement=[0, -200]
          (or autocad_stretch for both at once).
        - Use when: "move the end of that line to the column centre" ->
          vertex=1, to_point=the centre.
        - Use when: "put a kink in the cable tray at x=4500" -> operation='add'.
        - Don't use when: the whole object should move - use
          autocad_move_entities; or several vertices move together - use
          autocad_stretch.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        entity = resolve_handle(doc, handle)
        name = _name(entity)
        if name not in ("AcDbLine", "AcDbPolyline"):
            raise AutocadError(
                f"{entity.Handle} is a {short_type(entity)}; this changes a polyline's vertices or a line's ends."
            )
        if name == "AcDbLine" and operation != "move":
            raise AutocadError("A line has only its two ends: they can be moved, not added or removed.")
        z = _flat(entity)
        width = _width(entity)
        path = _path(entity)
        _unlocked(doc, entity)
        if vertex is None and near is None:
            raise AutocadError("Say which vertex: 'vertex' (its number) or 'near' (a point by it).")
        index = vertex if vertex is not None else geo.nearest_vertex(path, _flat_point(near, ucs, "near"))
        result: dict[str, Any] = {"handle": str(entity.Handle), "operation": operation, "vertex": index}
        straightened = False
        if operation == "move":
            if index >= len(path["vertices"]):
                raise AutocadError(f"There is no vertex {index}: it has {len(path['vertices'])}, numbered from 0.")
            old = path["vertices"][index]
            if to_point is not None and displacement is None:
                new_point = _flat_point(to_point, ucs, "to_point")
            elif displacement is not None and to_point is None:
                dx, dy, _ = world_direction(list(displacement) + [0.0] * (3 - len(displacement)), ucs)
                new_point = (old[0] + dx, old[1] + dy)
            else:
                raise AutocadError("Give 'to_point' or 'displacement' (one of them) for where the vertex goes.")
            result.update({"from": [round(old[0], 6), round(old[1], 6)],
                           "to": [round(new_point[0], 6), round(new_point[1], 6)]})
            if math.dist(old, new_point) <= geo.tolerance(path, points=[new_point]):
                result["vertex_count"] = len(path["vertices"])
                result["note"] = "NOTHING CHANGED: the vertex is already there."
                return result
            new = geo.move_vertex(path, index, new_point)
        elif operation == "add":
            if vertex is None or to_point is None:
                raise AutocadError("Add needs 'vertex' (the new one goes after it) and 'to_point' (where it is).")
            new_point = _flat_point(to_point, ucs, "to_point")
            new = geo.add_vertex(path, index, new_point)
            result["to"] = [round(new_point[0], 6), round(new_point[1], 6)]
        else:
            new, straightened = geo.remove_vertex(path, index)
        with undo_mark(doc):
            _write(entity, new, z, width)
        result["vertex_count"] = len(new["vertices"])
        if straightened:
            result["arc_straightened"] = True
            result["note"] = "An arc met the removed vertex; the new segment there is straight."
        return result

    return dumps(await run(work))


# Objects a stretch moves whole when their base point is inside the window.
BASE_POINT = {
    "AcDbCircle": "Center",
    "AcDbEllipse": "Center",
    "AcDbText": "InsertionPoint",
    "AcDbMText": "InsertionPoint",
    "AcDbBlockReference": "InsertionPoint",
    "AcDbAttributeDefinition": "InsertionPoint",
    "AcDbPoint": "Coordinates",
}


@mcp.tool(name="autocad_stretch", **tool_meta("Stretch"))
@tool_errors
async def autocad_stretch(
    handles: Annotated[
        list[str],
        Field(min_length=1, description="The objects to stretch; only their points inside the window move."),
    ],
    corner1: Annotated[list[float], Field(description="One corner of the stretch window, as [x, y].")],
    corner2: Annotated[list[float], Field(description="The opposite corner of the window, as [x, y].")],
    displacement: Annotated[
        list[float] | None,
        Field(default=None, description="How far the points inside move, as [dx, dy]. Or give from_point and to_point."),
    ] = None,
    from_point: Annotated[list[float] | None, Field(default=None, description="Base point as [x, y], with to_point.")] = None,
    to_point: Annotated[list[float] | None, Field(default=None, description="Where the base point goes, as [x, y].")] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Stretch objects: the vertices and line ends inside a window move, the rest stay. AutoCAD's STRETCH.

    Lines and polylines are reshaped (arcs in a polyline keep their bulge). A
    circle, text, block or point moves whole when its centre or insertion
    point is inside; an arc, hatch, dimension or anything else moves only
    when it lies wholly inside, and is otherwise left and listed. One undo step.

    Returns:
        JSON: {"reshaped": [{"handle", "vertices_moved"}], "moved_whole": [handles],
        "untouched": [handles], "skipped": [{"handle", "reason"}], "displacement"}

    Examples:
        - Use when: "that box is drawn 200 too tall" -> a window round its top
          edge, displacement=[0, -200].
        - Use when: "stretch the plant room 600 east, walls, door and all" ->
          the walls and the door, a window round the east side.
        - Don't use when: one vertex moves alone - use autocad_edit_vertex; or
          everything moves - use autocad_move_entities.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        box = geo.window(_flat_point(corner1, ucs, "corner1"), _flat_point(corner2, ucs, "corner2"))
        if displacement is not None and from_point is None and to_point is None:
            dx, dy, _ = world_direction(list(displacement) + [0.0] * (3 - len(displacement)), ucs)
        elif displacement is None and from_point is not None and to_point is not None:
            a, b = _flat_point(from_point, ucs, "from_point"), _flat_point(to_point, ucs, "to_point")
            dx, dy = b[0] - a[0], b[1] - a[1]
        else:
            raise AutocadError("Give 'displacement', or both 'from_point' and 'to_point'.")
        if abs(dx) <= 0 and abs(dy) <= 0:
            raise AutocadError("A displacement of 0 moves nothing.")
        eps = 1e-9 * max(1.0, *(abs(v) for v in box))
        _distinct(handles)

        plans: list[tuple[str, Any, Any]] = []
        untouched: list[str] = []
        skipped: list[dict[str, str]] = []
        for h in handles:
            try:
                entity = resolve_handle(doc, h)
                _unlocked(doc, entity)
                name = _name(entity)
                if name in ("AcDbLine", "AcDbPolyline"):
                    z = _flat(entity)
                    new, moved = geo.stretch_path(_path(entity), box, (dx, dy))
                    if not moved:
                        untouched.append(h)
                    elif len(moved) == len(new["vertices"]):
                        plans.append(("whole", entity, None))
                    else:
                        plans.append(("reshape", entity, (new, z, moved)))
                elif name in BASE_POINT:
                    base = getattr(entity, BASE_POINT[name])
                    if geo.inside((float(base[0]), float(base[1])), box, eps):
                        plans.append(("whole", entity, None))
                    else:
                        untouched.append(h)
                else:
                    lo, hi = entity.GetBoundingBox()
                    extent = (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))
                    if geo.box_within(extent, box, eps):
                        plans.append(("whole", entity, None))
                    elif extent[0] > box[2] or extent[2] < box[0] or extent[1] > box[3] or extent[3] < box[1]:
                        untouched.append(h)
                    else:
                        skipped.append({
                            "handle": h,
                            "reason": f"a {short_type(entity)} is moved only when it lies wholly inside the window; "
                            "Heron does not reshape it",
                        })
            except BaseException as exc:  # noqa: BLE001 - report, carry on
                skipped.append(_failure(h, exc))

        reshaped: list[dict[str, Any]] = []
        moved_whole: list[str] = []
        failed: list[dict[str, str]] = []
        if plans:
            origin, target = apoint(0, 0, 0), apoint(dx, dy, 0)
            with undo_mark(doc):
                for kind, entity, data in plans:
                    try:
                        if kind == "whole":
                            entity.Move(origin, target)
                            moved_whole.append(str(entity.Handle))
                        else:
                            new, z, moved = data
                            # Same vertex count, so a polyline keeps its widths.
                            _write(entity, new, z, 0.0)
                            reshaped.append({"handle": str(entity.Handle), "vertices_moved": moved})
                    except BaseException as exc:  # noqa: BLE001
                        failed.append(_failure(str(entity.Handle), exc))
        result: dict[str, Any] = {
            "reshaped": reshaped,
            "moved_whole": moved_whole,
            "untouched": untouched,
            "skipped": skipped,
            "displacement": [round(dx, 6), round(dy, 6)],
        }
        if not plans:
            result["note"] = "Nothing had a point inside the window, so nothing changed."
        return _finish(result, failed)

    return dumps(await run(work))


# ---- explode and draw order --------------------------------------------------------------------------


@mcp.tool(name="autocad_explode", **tool_meta("Explode", destructive=True))
@tool_errors
async def autocad_explode(
    handles: Annotated[list[str], HANDLES_OPT],
    allow_attribute_loss: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Explode blocks that carry attributes too. Exploded, an attribute shows its tag name (e.g. "
                "TAG), not its value: the value is lost. The answer lists the values. Off by default."
            ),
        ),
    ] = False,
) -> str:
    """Explode blocks, polylines and other compound objects into the pieces they are made of.

    The pieces are new objects; the original is erased, so Heron asks the
    modeller to keep it erased (D-50). A block with attributes is skipped
    unless allow_attribute_loss is true (exploded, AutoCAD shows each
    attribute's tag, not its value). One undo step.

    Returns:
        JSON: {"exploded": n, "objects": [{"handle", "type", "new_handles", "attributes"?}],
        "skipped": [{"handle", "reason"}], "failed": [...]}

    Examples:
        - Use when: "explode that imported block so I can fix one line in it".
        - Use when: "break that polyline into separate lines and arcs".
        - Don't use when: you want to change one segment's shape - use
          autocad_edit_vertex or autocad_break_curve, which keep it one
          object. Parts should stay blocks (drafting rule 2).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        _distinct(handles)
        plans: list[tuple[Any, dict[str, str]]] = []
        skipped: list[dict[str, str]] = []
        for h in handles:
            try:
                entity = resolve_handle(doc, h)
                _unlocked(doc, entity)
            except BaseException as exc:  # noqa: BLE001
                skipped.append(_failure(h, exc))
                continue
            name = _name(entity)
            if name == "AcDbMInsertBlock":
                skipped.append({"handle": h, "reason": "a block array (MINSERT) cannot be exploded"})
                continue
            values = read_attributes(entity) if name == "AcDbBlockReference" else {}
            if values and not allow_attribute_loss:
                shown = ", ".join(f"{k}={v}" for k, v in list(values.items())[:6])
                skipped.append({
                    "handle": h,
                    "reason": f"it has attributes ({shown}); exploded, they would show their tag names, not "
                    "their values. Give allow_attribute_loss=true to explode it anyway",
                })
                continue
            plans.append((entity, values))

        done: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        if plans:
            with undo_mark(doc):
                for entity, values in plans:
                    handle = str(entity.Handle)
                    kind = short_type(entity)
                    try:
                        pieces = list(entity.Explode())
                    except BaseException as exc:  # noqa: BLE001
                        failed.append(_failure(handle, exc))
                        continue
                    row: dict[str, Any] = {"handle": handle, "type": kind,
                                           "new_handles": [str(p.Handle) for p in pieces]}
                    if values:
                        row["attributes"] = values
                    # COM's Explode leaves the original in some releases; erase it if it is still there.
                    if _still_there(doc, handle):
                        try:
                            entity.Delete()
                        except BaseException as exc:  # noqa: BLE001
                            row["warning"] = (
                                f"The original could not be erased (it may already be gone): {com_message(exc)}. "
                                "Look before exploding again."
                            )
                    done.append(row)
        result: dict[str, Any] = {"exploded": len(done), "objects": done, "skipped": skipped}
        return _finish(result, failed)

    return dumps(await run(work))


def _still_there(doc: Any, handle: str) -> bool:
    try:
        found = doc.HandleToObject(handle)
    except BaseException:  # noqa: BLE001 - gone
        return False
    erased = _try(lambda: bool(found.Erased), False)
    return not erased


AC_ACTIVE_VIEWPORT = 0
ORDERS = {"front": "MoveToTop", "back": "MoveToBottom", "above": "MoveAbove", "under": "MoveBelow"}


def _sortents(owner: Any) -> Any:
    """The space's draw order table, made if the drawing has none yet."""
    xdict = owner.GetExtensionDictionary()
    try:
        return xdict.GetObject("ACAD_SORTENTS")
    except BaseException:  # noqa: BLE001 - not made yet
        return xdict.AddObject("ACAD_SORTENTS", "AcDbSortentsTable")


@mcp.tool(name="autocad_draw_order", **tool_meta("Draw Order"))
@tool_errors
async def autocad_draw_order(
    handles: Annotated[list[str], HANDLES_OPT],
    order: Annotated[
        str,
        Field(
            description=(
                "'front' (on top of everything), 'back' (behind everything), 'above' or 'under' the "
                "'reference' object."
            ),
            pattern="^(front|back|above|under)$",
        ),
    ],
    reference: Annotated[
        str | None,
        Field(default=None, description="For 'above' and 'under': the handle of the object to go above or under."),
    ] = None,
) -> str:
    """Put objects in front of or behind the rest (send a hatch or wipeout to the back): AutoCAD's DRAWORDER.

    Written to the space's draw order table (ACAD_SORTENTS), as DRAWORDER
    does. The objects keep their order among themselves. All must be in one
    space (model space or one layout). One undo step.

    Returns:
        JSON: {"moved": n, "order", "reference"?, "handles"}

    Examples:
        - Use when: "send the hatch behind the pipes" -> the hatch, order='back'.
        - Use when: "the wipeout should hide the lines but not the text" -> the
          wipeout order='above' a line, or the text order='front'.
        - Use when: "bring the duct above the grid" -> order='above', reference=the grid line.
    """
    if order in ("above", "under") and not reference:
        raise AutocadError(f"'{order}' needs 'reference': the object to go {order}.")
    if order in ("front", "back") and reference:
        raise AutocadError(f"'{order}' takes no 'reference'; use 'above' or 'under' to go next to one object.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        entities = [resolve_handle(doc, h) for h in handles]
        if len({str(e.Handle) for e in entities}) != len(entities):
            raise AutocadError("The same object is given twice.")
        target = resolve_handle(doc, reference) if reference else None
        if target is not None and str(target.Handle) in {str(e.Handle) for e in entities}:
            raise AutocadError("The reference cannot also be one of the objects moved.")
        _same_owner(entities + ([target] if target is not None else []))
        with undo_mark(doc):
            table = _sortents(_owner(doc, entities[0]))
            method = getattr(table, ORDERS[order])
            if target is None:
                method(object_array(entities))
            else:
                method(object_array(entities), target)
        try:
            doc.Regen(AC_ACTIVE_VIEWPORT)
        except BaseException:  # noqa: BLE001 - only the screen; the order is written
            pass
        result: dict[str, Any] = {"moved": len(entities), "order": order, "handles": [str(e.Handle) for e in entities]}
        if target is not None:
            result["reference"] = str(target.Handle)
        return result

    return dumps(await run(work))


# ---- match properties --------------------------------------------------------------------------------

AC_COLOR_BY_RGB = 194


def _color(entity: Any) -> Any:
    """The colour as the chat reads it: an AutoCAD colour number, or 'RGB r,g,b' for a true colour."""
    try:
        tc = entity.TrueColor
        if int(tc.ColorMethod) == AC_COLOR_BY_RGB:
            return f"RGB {int(tc.Red)},{int(tc.Green)},{int(tc.Blue)}"
    except BaseException:  # noqa: BLE001 - no true colour: the number
        pass
    return int(entity.Color)


READERS = {
    "layer": lambda e: str(e.Layer),
    "color": _color,
    "linetype": lambda e: str(e.Linetype),
    "linetype_scale": lambda e: float(e.LinetypeScale),
    "lineweight": lambda e: int(e.Lineweight),
    "transparency": lambda e: str(e.EntityTransparency),
    "text_style": lambda e: str(e.StyleName),
    "dim_style": lambda e: str(e.StyleName),
}

ATTRS = {"layer": "Layer", "linetype": "Linetype", "linetype_scale": "LinetypeScale", "lineweight": "Lineweight",
         "transparency": "EntityTransparency", "text_style": "StyleName", "dim_style": "StyleName"}


def _shown(prop: str, value: Any) -> Any:
    return props.lineweight_words(value) if prop == "lineweight" else value


@mcp.tool(name="autocad_match_properties", **tool_meta("Match Properties", idempotent=True))
@tool_errors
async def autocad_match_properties(
    source: Annotated[str, Field(description="The handle of the object to copy the properties from.")],
    handles: Annotated[list[str], Field(min_length=1, description="The objects to give those properties to.")],
    properties: Annotated[
        list[str] | None,
        Field(
            default=None,
            description=(
                "Which to copy: any of layer, color, linetype, linetype_scale, lineweight, transparency, "
                "text_style (text and mtext), dim_style (dimensions), or 'all'. Left out: the first six."
            ),
        ),
    ] = None,
) -> str:
    """Copy layer, colour, linetype, lineweight, transparency (and text or dimension style) from one object to others.

    AutoCAD's MATCHPROP, with the properties named. Only values that differ are
    written; a property a target does not have (a text style on a line) is
    skipped and said. An object that already matches opens no undo step. One
    undo step.

    Returns:
        JSON: {"matched": n, "handles", "properties", "before_after": [{"handle", "property", "from", "to"}],
        "already": [handles], "skipped": [{"handle", "property"}], "failed": [...]}

    Examples:
        - Use when: "make these pipes look like that one" -> source=that pipe,
          the pipes as handles.
        - Use when: "put the new text in the same style as the old notes" ->
          properties=['layer', 'text_style'].
        - Use when: "these dimensions should match that one" ->
          properties=['all'].
        - Don't use when: you know the values - use autocad_modify_entity.
    """
    wanted = props.matched_properties(properties)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        src = resolve_handle(doc, source)
        src_kind = short_type(src)
        values: dict[str, Any] = {}
        not_on_source: list[str] = []
        for prop in wanted:
            if not props.applies_to(prop, src_kind):
                not_on_source.append(prop)
                continue
            try:
                values[prop] = READERS[prop](src)
            except BaseException:  # noqa: BLE001 - this source has no such property
                not_on_source.append(prop)
        if not values:
            raise AutocadError(f"The source, a {src_kind}, has none of: {', '.join(wanted)}.")

        plans: list[tuple[Any, list[tuple[str, Any]]]] = []
        skipped: list[dict[str, str]] = []
        already: list[str] = []
        failed: list[dict[str, str]] = []
        for h in handles:
            try:
                target = resolve_handle(doc, h)
            except BaseException as exc:  # noqa: BLE001
                failed.append(_failure(h, exc))
                continue
            kind = short_type(target)
            changes: list[tuple[str, Any]] = []
            for prop, value in values.items():
                if not props.applies_to(prop, kind):
                    skipped.append({"handle": h, "property": prop})
                    continue
                try:
                    old = READERS[prop](target)
                except BaseException:  # noqa: BLE001
                    skipped.append({"handle": h, "property": prop})
                    continue
                if not same_value(old, value):
                    changes.append((prop, old))
            if changes:
                plans.append((target, changes))
            else:
                already.append(h)

        rows: list[dict[str, Any]] = []
        matched: list[str] = []
        if plans:
            with undo_mark(doc):
                for target, changes in plans:
                    h = str(target.Handle)
                    wrote = False
                    # The layer last: moved first onto a locked layer, the object would refuse the rest.
                    for prop, old in sorted(changes, key=lambda change: change[0] == "layer"):
                        try:
                            if prop == "color":
                                if isinstance(values["color"], str):
                                    target.TrueColor = src.TrueColor
                                else:
                                    target.Color = values["color"]
                            else:
                                setattr(target, ATTRS[prop], values[prop])
                            rows.append({"handle": h, "property": prop, "from": _shown(prop, old),
                                         "to": _shown(prop, values[prop])})
                            wrote = True
                        except BaseException as exc:  # noqa: BLE001
                            failed.append({"handle": h, "property": prop, "reason": com_message(exc)})
                    if wrote:
                        matched.append(h)
        result: dict[str, Any] = {
            "matched": len(matched),
            "handles": matched,
            "source": str(src.Handle),
            "properties": list(values),
            **before_after(rows),
        }
        if not_on_source:
            result["not_on_source"] = not_on_source
        if already:
            result["already"] = already
        if skipped:
            result["skipped"] = skipped
            result["skipped_note"] = "Those objects do not have that property, so it was left alone."
        if failed:
            result["hint"] = LOCKED_HINT
        return _finish(result, failed)

    return dumps(await run(work))


# ---- groups --------------------------------------------------------------------------------------------

BAD_NAME = set('<>/\\":;?*|,=`')


def _groups(doc: Any) -> list[Any]:
    table = doc.Groups
    return [table.Item(i) for i in range(int(table.Count))]


def _members(group: Any) -> list[Any]:
    return [group.Item(i) for i in range(int(group.Count))]


def _find_group(doc: Any, name: str) -> Any:
    for group in _groups(doc):
        if str(group.Name).casefold() == name.strip().casefold():
            return group
    raise AutocadError(f"There is no group named '{name}'. autocad_list_groups lists them.")


@mcp.tool(name="autocad_list_groups", **tool_meta("List Groups", read_only=True, idempotent=True))
@tool_errors
async def autocad_list_groups(
    name: Annotated[
        str | None,
        Field(default=None, description="Only groups whose name matches, e.g. 'PUMP*' (* and ? work, any case)."),
    ] = None,
    handle: Annotated[
        str | None,
        Field(default=None, description="Only the groups this object is in."),
    ] = None,
    most: Annotated[
        int,
        Field(default=100, ge=0, le=5000, description="List at most this many members per group (0: counts only)."),
    ] = 100,
) -> str:
    """List the drawing's groups with their members.

    Unnamed groups (AutoCAD names them *A1, *A2 ...) are listed too, marked.

    Returns:
        JSON: {"count", "groups": [{"name", "unnamed", "member_count",
        "members": [{"handle", "type", "layer"}], "members_more"?}]}

    Examples:
        - Use when: "what groups are in this drawing?"
        - Use when: "is that pump in a group?" -> handle=the pump.
        - Don't use when: you want blocks - use autocad_list_blocks.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        want = str(resolve_handle(doc, handle).Handle) if handle else None
        rows = []
        for group in _groups(doc):
            gname = str(group.Name)
            if name and not fnmatch.fnmatch(gname.casefold(), name.strip().casefold()):
                continue
            members = _members(group)
            if want and want not in {str(_try(lambda m=m: m.Handle, "")) for m in members}:
                continue
            row: dict[str, Any] = {"name": gname, "unnamed": gname.startswith("*"), "member_count": len(members)}
            if most:
                row["members"] = [
                    {"handle": str(_try(lambda m=m: m.Handle, "")), "type": short_type(m),
                     "layer": str(_try(lambda m=m: m.Layer, ""))}
                    for m in members[:most]
                ]
                if len(members) > most:
                    row["members_more"] = len(members) - most
            rows.append(row)
        return {"count": len(rows), "groups": rows}

    return dumps(await run(work))


@mcp.tool(name="autocad_group", **tool_meta("Group or Ungroup"))
@tool_errors
async def autocad_group(
    operation: Annotated[
        str,
        Field(
            description=(
                "'make' a named group from the objects; 'ungroup' (the group goes, its objects stay); 'add' "
                "objects to a group; 'remove' objects from it."
            ),
            pattern="^(make|ungroup|add|remove)$",
        ),
    ],
    name: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "The group's name. For 'make', left out, Heron names it GROUP1, GROUP2 ... For 'ungroup', left "
                "out, every group the 'handles' objects are in goes."
            ),
        ),
    ] = None,
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="The objects: to group, to add or remove, or whose groups to ungroup."),
    ] = None,
) -> str:
    """Make a named group, add or remove objects, or ungroup (the objects stay). AutoCAD's GROUP and UNGROUP.

    A group is a set of objects picked together; unlike a block, each stays its
    own object on its own layer. One undo step.

    Returns:
        JSON: make: {"made", "members"}; add / remove: {"group", "added" | "removed", "members",
        "not_in_group"?}; ungroup: {"ungrouped": [names], "objects_kept": n}

    Examples:
        - Use when: "group the pump, its valves and its base so I can move
          them together" -> operation='make', name='PUMP-01'.
        - Use when: "ungroup that" -> operation='ungroup', handles=[one of its objects].
        - Use when: "add the strainer to the pump group" -> operation='add'.
        - Don't use when: the set is a repeated part - make it a block with
          autocad_make_block (drafting rule 2).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        _distinct(handles or [])
        objects = [resolve_handle(doc, h) for h in handles or []]
        if operation == "make":
            if not objects:
                raise AutocadError("Give 'handles': the objects to group.")
            existing = {str(g.Name).casefold() for g in _groups(doc)}
            new_name = (name or "").strip()
            if not new_name:
                n = 1
                while f"group{n}" in existing:
                    n += 1
                new_name = f"GROUP{n}"
            if len(new_name) > 255 or BAD_NAME & set(new_name):
                raise AutocadError(
                    f"'{new_name}' cannot be a group name: up to 255 characters, none of < > / \\ \" : ; ? * | , = `."
                )
            if new_name.casefold() in existing:
                raise AutocadError(f"A group named '{new_name}' already exists. Use operation='add' to add to it.")
            with undo_mark(doc):
                group = doc.Groups.Add(new_name)
                try:
                    group.AppendItems(object_array(objects))
                except BaseException:
                    _try(group.Delete)  # no empty group left behind
                    raise
            return {"made": str(group.Name), "members": int(group.Count)}

        if operation in ("add", "remove"):
            if not name or not objects:
                raise AutocadError(f"'{operation}' needs the group's 'name' and the 'handles' to {operation}.")
            group = _find_group(doc, name)
            inside = {str(m.Handle) for m in _members(group)}
            if operation == "add":
                todo = [o for o in objects if str(o.Handle) not in inside]
                if todo:
                    with undo_mark(doc):
                        group.AppendItems(object_array(todo))
                out = {"group": str(group.Name), "added": len(todo), "members": int(group.Count)}
                if len(todo) < len(objects):
                    out["already_in"] = [str(o.Handle) for o in objects if str(o.Handle) in inside]
                return out
            todo = [o for o in objects if str(o.Handle) in inside]
            if todo:
                with undo_mark(doc):
                    group.RemoveItems(object_array(todo))
            out = {"group": str(group.Name), "removed": len(todo), "members": int(group.Count)}
            if len(todo) < len(objects):
                out["not_in_group"] = [str(o.Handle) for o in objects if str(o.Handle) not in inside]
            if int(group.Count) == 0:
                out["note"] = "The group is empty now; ungroup it if it is no longer wanted."
            return out

        # ungroup
        if name:
            targets = [_find_group(doc, name)]
        elif objects:
            wanted = {str(o.Handle) for o in objects}
            targets = [g for g in _groups(doc) if wanted & {str(m.Handle) for m in _members(g)}]
            if not targets:
                raise AutocadError("Those objects are not in any group.")
        else:
            raise AutocadError("Say which group: 'name', or 'handles' of objects in it.")
        kept_handles = [str(m.Handle) for g in targets for m in _members(g)]
        names = [str(g.Name) for g in targets]
        with undo_mark(doc):
            for group in targets:
                group.Delete()
        missing = [h for h in kept_handles if not _still_there(doc, h)]
        out = {"ungrouped": names, "objects_kept": len(kept_handles) - len(missing)}
        if missing:
            out["warning"] = (
                f"{len(missing)} of the group's objects cannot be found after the ungroup: press Ctrl+Z in "
                "AutoCAD to bring them back, and say so."
            )
            out["missing"] = missing
        return out

    return dumps(await run(work))
