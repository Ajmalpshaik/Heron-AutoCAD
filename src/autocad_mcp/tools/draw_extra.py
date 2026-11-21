"""The smaller drawing gaps from the ribbon audit (issue #119 part 1, D-108).

* Construction line and ray: COM ``AddXline`` / ``AddRay`` (#173).
* Region from closed outlines: COM ``AddRegion`` (#174).
* Donut: Heron's own maths, the object AutoCAD's DONUT makes, a closed
  polyline of two half-circle arcs with one width (#177).
* Divide / Measure: Heron's own maths for the distances along a run, then
  points or block inserts placed there over COM (#181).

The maths are plain functions at the top, tested without AutoCAD
(tests/test_draw_extra.py). None of this is proven in AutoCAD yet: the live
rows are NEEDS-CHECKING group AP, NOT RUN.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..acad import geometry
from ..acad.curves import read_path
from ..acad.entities import resolve_handle, resolve_handles, short_type
from ..acad.tables import apply_properties
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, double_array, object_array
from ._shared import (
    COLOR_OPT,
    LAYER_OPT,
    LINETYPE_OPT,
    SPACE_OPT,
    created_payload,
)

EPS = 1e-9
MOST_MARKS = 2000  # one call never places more than this many points or blocks
MOST_DONUTS = 1000

# What AddRegion takes: the curves that can close a loop.
REGION_CURVES = {"line", "arc", "circle", "ellipse", "spline", "polyline", "polyline2d"}


# ---- plain functions --------------------------------------------------------

def construction_points(
    base: Sequence[float], through: Sequence[float] | None = None, angle: float | None = None
) -> dict[str, Any]:
    """The two points AddXline / AddRay take, from a second point or an angle.

    Returns {"base", "second", "direction" (a unit vector), "angle"} with the
    angle in degrees, anticlockwise from +X, in the XY plane.
    """
    if (through is None) == (angle is None):
        raise ValueError("give 'through' (a second point) or 'angle', not both and not neither")
    if len(base) < 2:
        raise ValueError("'base' must be at least [x, y]")
    b = [float(c) for c in base[:3]] + [0.0] * (3 - len(base[:3]))
    if through is not None:
        if len(through) < 2:
            raise ValueError("'through' must be at least [x, y]")
        t = [float(c) for c in through[:3]] + [b[2]] * (3 - len(through[:3]))
        d = [t[i] - b[i] for i in range(3)]
    else:
        a = math.radians(float(angle))
        d = [math.cos(a), math.sin(a), 0.0]
    size = math.sqrt(sum(c * c for c in d))
    if size < EPS:
        raise ValueError("'through' is the same point as 'base', so there is no direction")
    unit = [c / size for c in d]
    flat = math.hypot(unit[0], unit[1])
    heading = math.degrees(math.atan2(unit[1], unit[0])) % 360.0 if flat > EPS else None
    return {"base": b, "second": [b[i] + unit[i] for i in range(3)], "direction": unit, "angle": heading}


def donut_shape(inside: float, outside: float) -> dict[str, float]:
    """The polyline a donut is: its centreline radius and its one width.

    AutoCAD's DONUT draws a closed polyline of two half circles. The line runs
    midway between the inside and outside circles, as wide as the gap between
    them. An inside diameter of 0 gives a filled dot.
    """
    inside, outside = float(inside), float(outside)
    if outside <= 0:
        raise ValueError("the outside diameter must be above 0")
    if inside < 0:
        raise ValueError("the inside diameter cannot be below 0")
    if inside >= outside:
        raise ValueError("the inside diameter must be smaller than the outside one")
    return {"radius": (outside + inside) / 4.0, "width": (outside - inside) / 2.0}


def donut_vertices(centre: Sequence[float], radius: float) -> list[float]:
    """The two vertices, left and right of the centre, as AddLightWeightPolyline's flat list."""
    cx, cy = float(centre[0]), float(centre[1])
    return [cx - radius, cy, cx + radius, cy]


def divide_distances(total: float, segments: int, closed: bool) -> list[float]:
    """DIVIDE: N equal parts. An open run gets N - 1 marks (its ends stay free);
    a closed one gets N, the first on its start point."""
    if segments < 2:
        raise ValueError("divide into at least 2 parts")
    if total <= EPS:
        raise ValueError("that run has no length")
    step = total / segments
    first = 0 if closed else 1
    return [i * step for i in range(first, segments)]


def measure_distances(total: float, interval: float) -> list[float]:
    """MEASURE: a mark every 'interval' from the start, the rest left at the end.

    No mark on the start point, and none exactly on the end (on a closed run
    that would sit on the start).
    """
    if interval <= 0:
        raise ValueError("the interval must be above 0")
    if total <= EPS:
        raise ValueError("that run has no length")
    count = int(math.floor(total / interval + 1e-9))
    marks = [i * interval for i in range(1, count + 1)]
    if marks and abs(marks[-1] - total) <= 1e-6 * max(1.0, total):
        marks.pop()
    return marks


def marks_along(
    path: dict[str, Any],
    segments: int | None = None,
    interval: float | None = None,
    from_end: bool = False,
) -> dict[str, Any]:
    """Where the marks go on a run: {"total", "step", "left_at_end", "marks": [...]}.

    Each mark is {"position": [x, y], "direction": degrees, "distance"}: the
    distance from where the counting started, and the run's own direction there
    (for a block turned to the run). from_end counts from the run's end back.
    """
    if (segments is None) == (interval is None):
        raise ValueError("give 'segments' (divide) or 'interval' (measure), not both and not neither")
    segs = geometry.segments(path["vertices"], path["bulges"], path["closed"])
    total = sum(s.length for s in segs)
    if segments is not None:
        distances = divide_distances(total, int(segments), bool(path["closed"]))
        step, left = total / int(segments), 0.0
    else:
        distances = measure_distances(total, float(interval))
        step = float(interval)
        # The short rest after the last whole interval; 0 when the run measures out exactly.
        left = total - math.floor(total / step + 1e-9) * step
        if left <= 1e-6 * max(1.0, total):
            left = 0.0
    marks = []
    for d in distances:
        x, y, direction = geometry.point_at(segs, total - d if from_end else d)
        marks.append({"position": [x, y], "direction": direction, "distance": d})
    return {"total": total, "step": step, "left_at_end": left, "marks": marks}


# ---- helpers on AutoCAD objects ---------------------------------------------

def _try(getter: Any, default: Any = None) -> Any:
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - this object has no such property
        return default


def _owner(doc: Any, entity: Any) -> Any:
    """The space (model space or a layout) the object is in."""
    return doc.ObjectIdToObject(entity.OwnerID)


def _flat_z(entity: Any) -> float:
    """The one height of a flat run, or a plain refusal when it is not flat on world XY."""
    handle = str(_try(lambda: entity.Handle, "?"))
    kind = str(_try(lambda: entity.ObjectName, ""))
    if kind == "AcDbLine":
        s, e = entity.StartPoint, entity.EndPoint
        sz = float(s[2]) if len(s) > 2 else 0.0
        ez = float(e[2]) if len(e) > 2 else 0.0
        if abs(sz - ez) > 1e-6:
            raise AutocadError(
                f"{handle} is a line that slopes in Z (from {sz:g} to {ez:g}). Divide and measure "
                "work on runs that are flat; draw a flat line to mark along."
            )
        return sz
    normal = _try(lambda: tuple(float(c) for c in entity.Normal))
    if normal and (abs(normal[0]) > 1e-6 or abs(normal[1]) > 1e-6 or normal[2] < 0):
        raise AutocadError(
            f"{handle} is not flat on the world XY plane (it was drawn in a turned or tilted UCS). "
            "Divide and measure read runs in world plan; draw the run in the world UCS first."
        )
    if kind in ("AcDbArc", "AcDbCircle"):
        c = entity.Center
        return float(c[2]) if len(c) > 2 else 0.0
    return float(_try(lambda: entity.Elevation, 0.0) or 0.0)


def _verified(doc: Any, handles: Sequence[str]) -> bool:
    for h in handles:
        try:
            doc.HandleToObject(h)
        except BaseException:  # noqa: BLE001 - not found is the finding
            return False
    return True


def _r(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_r(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


# ---- construction line and ray (#173) ---------------------------------------

@mcp.tool(name="autocad_add_construction_line", **tool_meta("Add A Construction Line Or Ray"))
@tool_errors
async def autocad_add_construction_line(
    base: Annotated[list[float], Field(description="A point the line runs through, as [x, y] or [x, y, z]. A ray starts here.")],
    through: Annotated[list[float] | None, Field(description="A second point it runs through. Give this or 'angle'.")] = None,
    angle: Annotated[float | None, Field(description="Or its direction in DEGREES anticlockwise from +X: 0 is horizontal, 90 vertical.")] = None,
    kind: Annotated[Literal["xline", "ray"], Field(description="'xline' runs without end both ways (XLINE); 'ray' starts at base and runs without end one way (RAY).")] = "xline",
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    linetype: Annotated[str | None, LINETYPE_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw a construction line (XLINE, endless both ways) or a ray (RAY, endless one way).

    For setting-out: grid and centre references, a line at an angle to work
    from. They plot like lines, so put them on a no-plot layer. Points are
    world coordinates.

    Returns:
        JSON: {"created": true, "handle", "type": "xline" | "ray", "layer",
               "base_point", "direction", "angle_degrees"}

    Examples:
        - Use when: "a vertical setting-out line through the riser at 4500,2200"
          -> base=[4500, 2200], angle=90.
        - Use when: "a ray from the pump outlet towards the tank" -> kind='ray',
          base at the outlet, through at the tank.
        - Don't use when: the line should stop somewhere - autocad_draw_line.
    """
    try:
        geo = construction_points(base, through, angle)
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        target = get_space(doc, space)
        p1, p2 = apoint(*geo["base"]), apoint(*geo["second"])
        with undo_mark(doc):
            entity = target.AddXline(p1, p2) if kind == "xline" else target.AddRay(p1, p2)
            notes = apply_properties(doc, entity, layer, aci, linetype)
        return created_payload(
            entity, notes, base_point=_r(geo["base"]), direction=_r(geo["direction"]),
            angle_degrees=_r(geo["angle"]),
        )

    return dumps(await run(work))


# ---- region (#174) ----------------------------------------------------------

@mcp.tool(name="autocad_add_region", **tool_meta("Make Regions From Closed Outlines"))
@tool_errors
async def autocad_add_region(
    handles: Annotated[list[str], Field(min_length=1, description="The closed outlines: closed polylines, circles, ellipses, closed splines, or lines and arcs that meet end to end in a closed loop.")],
    erase_outlines: Annotated[bool, Field(description="Erase the outlines once the regions are made, as REGION does with DELOBJ on. Off: they stay.")] = False,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
) -> str:
    """Turn closed outlines into regions (REGION), each with its area, perimeter and centre.

    A region is a flat face: its area and centre can be read, it can be
    extruded, and holes can be cut out of it. AutoCAD makes one region per
    closed loop. The regions go in the outlines' own space. One undo step.

    Returns:
        JSON: {"created": n, "regions": [{"handle", "area", "perimeter",
               "centroid"}], "erased_outlines": [...]}

    Examples:
        - Use when: "make that slab outline a region so I can take its area
          and centre" -> handles=[the outline].
        - Use when: "turn the plant room walls (lines meeting end to end) into
          one face" -> handles=all the lines.
        - Don't use when: you only want an area - autocad_polyline_info or
          autocad_measure. To cut shafts out of a region afterwards:
          autocad_solid_boolean subtract (it takes regions). For a hatch:
          autocad_add_hatch.
    """
    if len(set(handles)) != len(handles):
        raise AutocadError("The same handle is in 'handles' twice; give each outline once.")
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        outlines = resolve_handles(doc, handles)
        for entity, label in zip(outlines, handles, strict=False):
            kind = short_type(entity)
            if kind not in REGION_CURVES:
                raise AutocadError(
                    f"{label} is a {kind}. A region is made from lines, arcs, circles, ellipses, "
                    "splines and polylines that close a loop."
                )
        owners = {str(_try(lambda e=e: e.OwnerID)) for e in outlines}
        if len(owners) > 1:
            raise AutocadError("Those outlines are not all in the same space (model space or one layout).")
        target = _owner(doc, outlines[0])
        with undo_mark(doc):
            try:
                made = list(target.AddRegion(object_array(outlines)) or [])
            except BaseException as exc:  # noqa: BLE001 - AutoCAD's reason, said plainly
                raise AutocadError(
                    "AutoCAD made no region from those. Each loop must close exactly (ends meeting), "
                    "lie flat, and not cross itself; open polylines need closing first "
                    f"(autocad_join_curves). AutoCAD said: {com_message(exc)}"
                ) from exc
            if not made:
                raise AutocadError(
                    "AutoCAD made no region from those: they do not close a loop. Check the ends meet "
                    "(autocad_join_curves) and try again."
                )
            notes: dict[str, Any] = {}
            for region in made:
                notes.update(apply_properties(doc, region, layer, aci, None))
            erased = []
            if erase_outlines:
                for entity, label in zip(outlines, handles, strict=False):
                    entity.Delete()
                    erased.append(label)
        rows = []
        for region in made:
            rows.append({
                "handle": str(region.Handle),
                "layer": str(_try(lambda r=region: r.Layer, "")),
                "area": _r(_try(lambda r=region: float(r.Area))),
                "perimeter": _r(_try(lambda r=region: float(r.Perimeter))),
                "centroid": _r(_try(lambda r=region: [float(c) for c in r.Centroid])),
            })
        out: dict[str, Any] = {"created": len(rows), "regions": rows,
                               "verified": _verified(doc, [row["handle"] for row in rows])}
        if erase_outlines:
            out["erased_outlines"] = erased
        else:
            out["outlines_kept"] = list(handles)
        out.update(notes)
        return out

    return dumps(await run(work))


# ---- donut (#177) -----------------------------------------------------------

@mcp.tool(name="autocad_add_donut", **tool_meta("Add Donuts Or Filled Dots"))
@tool_errors
async def autocad_add_donut(
    centers: Annotated[list[list[float]], Field(min_length=1, max_length=MOST_DONUTS, description="One or more centres, each [x, y] or [x, y, z]. DONUT asks for centres again and again; give them all here.")],
    outside_diameter: Annotated[float, Field(gt=0, description="Outside diameter, in drawing units.")],
    inside_diameter: Annotated[float, Field(ge=0, description="Inside diameter. 0 gives a filled dot.")] = 0.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw donuts, or filled dots (inside 0), the same object AutoCAD's DONUT makes.

    Each is a closed polyline of two half circles with one width: the line
    runs midway between the two diameters and is as wide as the gap. All of
    them in one undo step.

    Returns:
        JSON: {"created": n, "handles", "type": "polyline", "width",
               "centreline_radius", "verified"}

    Examples:
        - Use when: "a filled 3 mm dot at every pipe junction on the schematic"
          -> centers=[...], outside_diameter=3.
        - Use when: "a ring 150 outside, 100 inside at each sleeve" ->
          outside_diameter=150, inside_diameter=100.
        - Don't use when: you want a plain unfilled circle -
          autocad_draw_circle; a hatched circle - autocad_add_hatch.
    """
    try:
        shape = donut_shape(inside_diameter, outside_diameter)
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    for i, c in enumerate(centers):
        if len(c) < 2:
            raise AutocadError(f"Centre {i + 1} must be at least [x, y], got {c!r}.")
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        target = get_space(doc, space)
        handles: list[str] = []
        notes: dict[str, Any] = {}
        with undo_mark(doc):
            for c in centers:
                pl = target.AddLightWeightPolyline(double_array(donut_vertices(c, shape["radius"])))
                pl.Closed = True  # first: the second bulge is the closing segment's
                pl.SetBulge(0, 1.0)
                pl.SetBulge(1, 1.0)
                pl.ConstantWidth = shape["width"]
                if len(c) > 2 and float(c[2]):
                    pl.Elevation = float(c[2])
                notes.update(apply_properties(doc, pl, layer, aci, None))
                handles.append(str(pl.Handle))
        out: dict[str, Any] = {
            "created": len(handles), "handles": handles, "type": "polyline",
            "outside_diameter": outside_diameter, "inside_diameter": inside_diameter,
            "width": _r(shape["width"]), "centreline_radius": _r(shape["radius"]),
            "verified": _verified(doc, handles),
        }
        if len(handles) == 1:
            out["handle"] = handles[0]
        if _try(lambda: int(doc.GetVariable("FILLMODE")), 1) == 0:
            out["note"] = (
                "FILLMODE is 0 in this drawing, so donuts show as outlines only, not filled. "
                "Set FILLMODE to 1 and regen to see them filled."
            )
        out.update(notes)
        return out

    return dumps(await run(work))


# ---- divide / measure (#181) ------------------------------------------------

@mcp.tool(name="autocad_divide_curve", **tool_meta("Divide Or Measure A Run"))
@tool_errors
async def autocad_divide_curve(
    path_handle: Annotated[str, Field(min_length=1, description="The line, polyline, arc or circle to mark along.")],
    segments: Annotated[int | None, Field(ge=2, le=MOST_MARKS, description="DIVIDE: split it into this many equal parts.")] = None,
    interval: Annotated[float | None, Field(gt=0, description="Or MEASURE: a mark every this distance from the start; the rest is left at the end.")] = None,
    from_end: Annotated[bool, Field(description="Count from the run's end instead of its start (MEASURE starts from the end you pick near).")] = False,
    block_name: Annotated[str | None, Field(description="Insert this block at each mark (defined in the drawing). Omit for point objects.")] = None,
    align: Annotated[bool, Field(description="With a block: turn each one to the run's direction, as DIVIDE's 'Align block with object? Yes'.")] = True,
    rotation: Annotated[float, Field(description="With a block: extra rotation in degrees, added to each.")] = 0.0,
    scale: Annotated[float, Field(gt=0, description="With a block: its scale.")] = 1.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
) -> str:
    """Mark a run like AutoCAD's DIVIDE (N equal parts) or MEASURE (every X), with points or a block.

    DIVIDE leaves the ends of an open run free (N parts give N - 1 marks); on
    a closed run the first mark is on its start point. MEASURE starts at the
    start (or the end, with from_end) and leaves the short rest at the far
    end; it puts no mark exactly on the end. Circles start at 0 degrees and go
    anticlockwise. The marks go in the run's own space. One undo step.

    Returns:
        JSON: {"placed": n, "kind": "points" | "block", "handles",
               "run_length", "step", "left_at_end", "positions"}

    Examples:
        - Use when: "divide that duct run into 6 equal parts with points so I
          can snap the diffusers" -> segments=6.
        - Use when: "a support block every 1500 from the start of that pipe"
          -> interval=1500, block_name='SUPPORT'.
        - Don't use when: the blocks should be centred with equal ends -
          autocad_place_along; positions from a schedule -
          autocad_place_from_csv.
    """
    if (segments is None) == (interval is None):
        raise AutocadError("Give 'segments' (divide into equal parts) or 'interval' (measure), not both.")
    name = block_name.strip() if block_name else None

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if name:
            try:
                doc.Blocks.Item(name)
            except BaseException:  # noqa: BLE001
                raise AutocadError(f"No block named '{name}' in this drawing; see autocad_list_blocks.") from None
        run_entity = resolve_handle(doc, path_handle)
        path = read_path(run_entity)
        z = _flat_z(run_entity)
        try:
            plan = marks_along(path, segments, interval, from_end)
        except ValueError as exc:
            raise AutocadError(f"{path_handle}: {exc}.") from exc
        marks = plan["marks"]
        if not marks:
            raise AutocadError(
                f"{path_handle} is {plan['total']:.6g} long, shorter than the interval {interval:g}, "
                "so no mark fits. Use a smaller interval."
            )
        if len(marks) > MOST_MARKS:
            raise AutocadError(
                f"That makes {len(marks)} marks; one call places at most {MOST_MARKS}. "
                "Use a larger interval."
            )
        target = _owner(doc, run_entity)
        handles: list[str] = []
        notes: dict[str, Any] = {}
        with undo_mark(doc):
            for m in marks:
                at = apoint(m["position"][0], m["position"][1], z)
                if name:
                    turn = (m["direction"] if align else 0.0) + rotation
                    obj = target.InsertBlock(at, name, scale, scale, scale, math.radians(turn))
                else:
                    obj = target.AddPoint(at)
                notes.update(apply_properties(doc, obj, layer, None, None))
                handles.append(str(obj.Handle))
        out: dict[str, Any] = {
            "placed": len(handles), "kind": "block" if name else "points", "handles": handles,
            "run_length": _r(plan["total"]), "step": _r(plan["step"]),
            "left_at_end": _r(plan["left_at_end"]), "closed": bool(path["closed"]),
            "positions": [_r(m["position"]) for m in marks],
            "verified": _verified(doc, handles),
        }
        if name:
            out["block"] = name
        elif _try(lambda: int(doc.GetVariable("PDMODE")), 0) in (0, 1):
            out["note"] = (
                "Points show as a dot or not at all with this drawing's point style. To see them, "
                "autocad_drawing_setup point_style='x'."
            )
        out.update(notes)
        return out

    return dumps(await run(work))
