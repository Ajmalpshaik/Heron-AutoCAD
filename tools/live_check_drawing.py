"""Live checks for the smaller draw gaps (group AP) and the full-sheet preview (group AM).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Each AP row draws its own objects at its own spot (``lc.origin``), then reads
back what the tool made: a construction line's base point and direction, a
region's area, a donut's width, where each divide / measure point landed. The
comparison with AutoCAD's own XLINE, REGION, DONUT, DIVIDE and MEASURE typed by
hand is not tried (each row's evidence says so), nor the one Ctrl+Z after it.

The AM rows that need a clean sheet (AM2, AM4) draw it in a new drawing of their
own, so the scratch drawing's far-flung test objects do not stretch the
extents, and close it again unsaved.
"""

from __future__ import annotations

import math
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, near_point, parse, refusal

from autocad_mcp.tools import (
    batch,
    blocks,
    document,
    draw_extra,
    modify,
    query,
    settings,
    solids,
)

PNG = b"\x89PNG\r\n\x1a\n"


def _at(o: tuple[float, float], x: float, y: float, z: float | None = None) -> list[float]:
    return [o[0] + x, o[1] + y] if z is None else [o[0] + x, o[1] + y, z]


def _rel(o: tuple[float, float], p: list[float]) -> str:
    return f"{p[0] - o[0]:g},{p[1] - o[1]:g}"


async def _draw(*operations: dict[str, Any]) -> list[str]:
    """Draw with autocad_batch_draw; the handles, in order."""
    made = parse(await batch.autocad_batch_draw(operations=list(operations)))
    expect(made.get("created") == len(operations), f"drew {made.get('created')} of {len(operations)} test objects")
    return list(made["handles"])


async def _entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


async def _points_at(o: tuple[float, float], handles: list[str]) -> list[list[float]]:
    """Where each point object really is, read back one by one."""
    found = []
    for handle in handles:
        info = await _entity(handle)
        expect(info.get("type") == "point", f"{handle} is a {info.get('type')}, not a point")
        found.append(info["position"])
    return found


def _same_places(o: tuple[float, float], got: list[list[float]], want: list[tuple[float, float]], tol: float = 1e-6) -> bool:
    return len(got) == len(want) and all(near_point(g, _at(o, *w), tol) for g, w in zip(got, want, strict=True))


def _places(o: tuple[float, float], got: list[list[float]]) -> str:
    return "; ".join(_rel(o, p) for p in got) or "none"


# ---------------------------------------------------------------------------
# Done in AutoCAD by the runner itself, not through Heron
# ---------------------------------------------------------------------------


async def by_hand_erase(handle: str) -> None:
    """Erase one object as the modeller does with ERASE, not through Heron (so no keep-erased box)."""
    from autocad_mcp.acad.entities import resolve_handle
    from autocad_mcp.core.connection import get_doc, run

    def erase() -> None:
        resolve_handle(get_doc(), handle).Delete()

    await run(erase)


PAGE_SETUP = ("ConfigName", "CanonicalMediaName", "PlotType", "UseStandardScale", "StandardScale",
              "PlotRotation", "CenterPlot", "StyleSheet")


async def page_setup() -> dict[str, Any]:
    """The active layout's page setup as PAGESETUP shows it: plotter, paper, area, scale, rotation."""
    from autocad_mcp.core.connection import get_doc, run

    def read() -> dict[str, Any]:
        layout = get_doc().ActiveLayout
        out: dict[str, Any] = {"layout": str(layout.Name)}
        for name in PAGE_SETUP:
            try:
                value = getattr(layout, name)
                out[name] = value if isinstance(value, (bool, int, float)) else str(value)
            except BaseException:  # noqa: BLE001 - a property this layout does not give
                out[name] = None
        return out

    return await run(read)


# ---------------------------------------------------------------------------
# Group AP - construction line and ray, region, donut, divide / measure
# ---------------------------------------------------------------------------


async def ap1_a_construction_line_and_a_ray_run_where_asked(ctx: Context) -> str:
    o = lc.origin("AP1")
    base = _at(o, 1000, 1000, 0.0)
    xline = parse(await draw_extra.autocad_add_construction_line(base=base, angle=90, layer="LC-AP1"))
    expect(xline.get("verified") is True, f"the xline's answer says verified {xline.get('verified')}")
    info = await _entity(xline["handle"])
    expect(info.get("type") == "xline", f"{xline['handle']} reads back as a {info.get('type')}, not an xline")
    props = await lc.read_props(xline["handle"], ["BasePoint", "DirectionVector"])
    expect(near_point(props.get("BasePoint"), base), f"the xline's base point is {props.get('BasePoint')}, not 1000,1000")
    expect(near_point(props.get("DirectionVector"), [0, 1, 0], 1e-9),
           f"the xline's direction is {props.get('DirectionVector')}, not 0,1,0")
    start, through = _at(o, 0, 0, 0.0), _at(o, 300, 400, 0.0)
    ray = parse(await draw_extra.autocad_add_construction_line(kind="ray", base=start, through=through, layer="LC-AP1"))
    expect(ray.get("verified") is True, f"the ray's answer says verified {ray.get('verified')}")
    info = await _entity(ray["handle"])
    expect(info.get("type") == "ray", f"{ray['handle']} reads back as a {info.get('type')}, not a ray")
    props = await lc.read_props(ray["handle"], ["BasePoint", "DirectionVector"])
    expect(near_point(props.get("BasePoint"), start), f"the ray starts at {props.get('BasePoint')}, not 0,0")
    expect(near_point(props.get("DirectionVector"), [0.6, 0.8, 0], 1e-9),
           f"the ray runs {props.get('DirectionVector')}, not towards 300,400 (0.6,0.8)")
    return ("an xline through 1000,1000 with direction 0,1,0 and a ray from 0,0 towards 300,400 (0.6,0.8), "
            "both read back and verified. Not tried: the paper-space one (it needs a sheet tab made active "
            "by hand), LIST beside it, and the one Ctrl+Z")


async def ap2_a_region_has_the_right_area_and_the_outline_stays(ctx: Context) -> str:
    o = lc.origin("AP2")
    (outline,) = await _draw(
        {"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 1000, 500), "layer": "LC-AP2"})
    out = parse(await draw_extra.autocad_add_region(handles=[outline]))
    regions = out.get("regions") or []
    expect(out.get("created") == 1 and len(regions) == 1, f"made {out.get('created')} regions, not 1")
    handle = regions[0]["handle"]
    info = await _entity(handle)
    expect(info.get("type") == "region", f"{handle} reads back as a {info.get('type')}, not a region")
    expect(near(info.get("area"), 500000.0, 1e-3), f"the region's area reads {info.get('area')}, not 500000")
    props = await lc.read_props(handle, ["Perimeter", "Centroid"])
    expect(near(props.get("Perimeter"), 3000.0, 1e-3), f"its perimeter reads {props.get('Perimeter')}, not 3000")
    expect(near_point(props.get("Centroid"), _at(o, 500, 250), 1e-3),
           f"its centroid reads {props.get('Centroid')}, not 500,250 from the corner")
    expect(await lc.exists(outline), "the polyline is gone: AddRegion did not keep the outline")
    delobj = await lc.variable("DELOBJ")
    return (f"one region, area 500000, perimeter 3000, centroid 500,250, read back; the polyline is still there "
            f"with DELOBJ {delobj}. MASSPROP was not compared")


async def ap4_an_open_outline_and_a_text_are_refused(ctx: Context) -> str:
    o = lc.origin("AP4")
    open_run, note = await _draw(
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 1000, 0), _at(o, 1000, 500)], "layer": "LC-AP4"},
        {"type": "text", "position": _at(o, 0, 1000), "text": "NOT A LOOP", "height": 100, "layer": "LC-AP4"},
    )
    before = await lc.entity_count()
    message = refusal(await draw_extra.autocad_add_region(handles=[open_run]))
    expect("made no region" in message, f"the open polyline was not refused with 'no region': {message[:160]}")
    autocad_words = "AutoCAD said:" in message
    expect(await lc.entity_count() == before, "something was made from the open polyline")
    text_message = refusal(await draw_extra.autocad_add_region(handles=[note]))
    expect("is a text" in text_message and "A region is made from" in text_message,
           f"the text was not refused before AutoCAD was asked: {text_message[:160]}")
    expect(await lc.entity_count() == before, "something was made from the text")
    words = ("with AutoCAD's own words" if autocad_words
             else "without AutoCAD's own words (AddRegion gave back nothing rather than an error)")
    return f"the open polyline refused 'made no region' {words}; the text refused as a text; nothing made"


async def ap5_donuts_and_a_dot_are_wide_closed_polylines(ctx: Context) -> str:
    o = lc.origin("AP5")
    fill = await lc.variable("FILLMODE")
    rings = parse(await draw_extra.autocad_add_donut(
        centers=[_at(o, 0, 0), _at(o, 500, 0)], outside_diameter=150, inside_diameter=100, layer="LC-AP5"))
    expect(rings.get("created") == 2 and len(rings.get("handles") or []) == 2, f"made {rings.get('created')} rings, not 2")
    dot = parse(await draw_extra.autocad_add_donut(centers=[_at(o, 1000, 0)], outside_diameter=30, layer="LC-AP5"))
    expect(dot.get("created") == 1, f"made {dot.get('created')} dots, not 1")
    want = [(rings["handles"][0], (0, 0), 62.5, 25.0), (rings["handles"][1], (500, 0), 62.5, 25.0),
            (dot["handles"][0], (1000, 0), 7.5, 15.0)]
    for handle, (x, y), radius, width in want:
        info = await _entity(handle)
        expect(info.get("type") == "polyline" and info.get("closed") is True and info.get("vertex_count") == 2,
               f"{handle} is a {info.get('type')}, closed {info.get('closed')}, {info.get('vertex_count')} vertices")
        ends = info.get("vertices") or []
        expect(len(ends) == 2 and near_point(ends[0], _at(o, x - radius, y)) and near_point(ends[1], _at(o, x + radius, y)),
               f"{handle}'s vertices are {[_rel(o, p) for p in ends]}, not {x - radius:g},{y:g} and {x + radius:g},{y:g}")
        expect(near(info.get("length"), 2 * math.pi * radius, 1e-3),
               f"{handle} is {info.get('length')} long, not a full circle of radius {radius:g}")
        got = (await lc.read_props(handle, ["ConstantWidth"])).get("ConstantWidth")
        expect(near(got, width, 1e-9), f"{handle}'s width reads {got}, not {width:g}")
    if int(fill or 0) == 0:
        expect("FILLMODE" in str(rings.get("note")), "FILLMODE is 0 here but the answer has no note")
        said = "FILLMODE was already 0 and the answer said so"
    else:
        expect(not rings.get("note"), f"FILLMODE is {fill} but the answer has a note: {rings.get('note')}")
        parse(await settings.autocad_drawing_setup(fill=False))
        try:
            outline = parse(await draw_extra.autocad_add_donut(
                centers=[_at(o, 1500, 0)], outside_diameter=150, inside_diameter=100, layer="LC-AP5"))
        finally:
            parse(await settings.autocad_drawing_setup(fill=True))
        expect("FILLMODE" in str(outline.get("note")), f"with FILLMODE 0 the answer has no note: {outline}")
        said = "with FILLMODE set to 0 the answer had the note (FILLMODE put back to 1)"
    return ("two rings and a dot: closed polylines of 2 vertices, a full circle round, widths 25 and 15, read "
            f"back; {said}. Not tried: AutoCAD's own DONUT beside them, and how they look on screen")


async def ap6_divide_a_line_in_four(ctx: Context) -> str:
    o = lc.origin("AP6")
    (line,) = await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AP6"})
    pdmode = await lc.variable("PDMODE")
    out = parse(await draw_extra.autocad_divide_curve(path_handle=line, segments=4))
    expect(out.get("placed") == 3 and out.get("kind") == "points", f"placed {out.get('placed')} {out.get('kind')}, not 3 points")
    got = await _points_at(o, out["handles"])
    expect(_same_places(o, got, [(250, 0), (500, 0), (750, 0)]), f"the points are at {_places(o, got)}, not 250, 500, 750")
    if int(pdmode or 0) in (0, 1):
        expect("autocad_drawing_setup" in str(out.get("note")), f"PDMODE is {pdmode} but there is no point-style note")
    else:
        expect(not out.get("note"), f"PDMODE is {pdmode} but the answer still has the note")
    return (f"3 points at 250, 500, 750, none on the ends, read back; PDMODE {pdmode} and the note "
            f"{'given' if out.get('note') else 'not given'}. AutoCAD's own DIVIDE was not compared")


async def ap7_divide_a_circle_and_a_rectangle_in_four(ctx: Context) -> str:
    o = lc.origin("AP7")
    circle, rect = await _draw(
        {"type": "circle", "center": _at(o, 0, 0), "radius": 100, "layer": "LC-AP7"},
        {"type": "rectangle", "corner1": _at(o, 1000, 0), "corner2": _at(o, 1400, 200), "layer": "LC-AP7"},
    )
    out = parse(await draw_extra.autocad_divide_curve(path_handle=circle, segments=4))
    expect(out.get("placed") == 4 and out.get("closed") is True, f"the circle got {out.get('placed')} points, not 4")
    got = await _points_at(o, out["handles"])
    expect(_same_places(o, got, [(100, 0), (0, 100), (-100, 0), (0, -100)]),
           f"the circle's points are at {_places(o, got)}, not 0, 90, 180, 270 degrees from 100,0")
    out = parse(await draw_extra.autocad_divide_curve(path_handle=rect, segments=4))
    expect(out.get("placed") == 4, f"the rectangle got {out.get('placed')} points, not 4")
    got = await _points_at(o, out["handles"])
    expect(_same_places(o, got, [(1000, 0), (1300, 0), (1400, 200), (1100, 200)]),
           f"the rectangle's points are at {_places(o, got)}, not 1000,0 (its first vertex), 1300,0, 1400,200, 1100,200")
    return ("the circle: 4 points at 0, 90, 180, 270 degrees, 100,0 first; the rectangle: 4 points, the first on "
            "its first vertex, read back. Not recorded: where AutoCAD's own DIVIDE starts (not compared)")


async def ap8_measure_a_line_from_either_end(ctx: Context) -> str:
    o = lc.origin("AP8")
    (line,) = await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AP8"})
    runs = (
        ({"interval": 300}, [(300, 0), (600, 0), (900, 0)], 100.0),
        ({"interval": 250}, [(250, 0), (500, 0), (750, 0)], 0.0),
        ({"interval": 300, "from_end": True}, [(700, 0), (400, 0), (100, 0)], 100.0),
    )
    for kwargs, want, left in runs:
        out = parse(await draw_extra.autocad_divide_curve(path_handle=line, **kwargs))
        got = await _points_at(o, out.get("handles") or [])
        expect(_same_places(o, got, want),
               f"measure {kwargs} put points at {_places(o, got)}, not {', '.join(f'{x:g}' for x, _ in want)}")
        expect(near(out.get("left_at_end"), left, 1e-6), f"measure {kwargs} says left_at_end {out.get('left_at_end')}, not {left:g}")
    return ("300: 300, 600, 900 (left 100); 250: 250, 500, 750 (left 0, none on the end); 300 from the end: 700, "
            "400, 100 - all read back. AutoCAD's own MEASURE was not compared, so whether it puts a point on the "
            "end at 250 is not recorded")


async def ap9_measure_places_turned_supports_at_the_runs_height(ctx: Context) -> str:
    o = lc.origin("AP9")
    run, arrow = await _draw(
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 600, 0), _at(o, 600, 600)], "layer": "LC-AP9"},
        {"type": "polyline", "points": [_at(o, 5000, 0), _at(o, 5100, 0), _at(o, 5080, 20)], "layer": "LC-AP9"},
    )
    parse(await modify.autocad_move_entities(handles=[run], displacement=[0, 0, 2700]))
    elevation = (await lc.read_props(run, ["Elevation"])).get("Elevation")
    expect(near(elevation, 2700.0, 1e-9), f"the run's elevation reads {elevation}, not 2700")
    parse(await blocks.autocad_make_block(name="LC-AP9-SUPPORT", handles=[arrow], base_point=_at(o, 5000, 0),
                                          keep_originals=True))
    layer = "LC-AP9-M-SUPPORT"
    seen = []
    for from_end, want in ((False, [((500, 0), 0.0), ((600, 400), 90.0)]),
                           (True, [((600, 100), 90.0), ((200, 0), 0.0)])):
        out = parse(await draw_extra.autocad_divide_curve(path_handle=run, interval=500, block_name="LC-AP9-SUPPORT",
                                                          layer=layer, from_end=from_end))
        handles = out.get("handles") or []
        expect(out.get("kind") == "block" and len(handles) == 2, f"placed {len(handles)} {out.get('kind')}, not 2 blocks")
        expect(near(out.get("left_at_end"), 200.0, 1e-6), f"left_at_end is {out.get('left_at_end')}, not 200")
        for handle, ((x, y), turn) in zip(handles, want, strict=True):
            info = await _entity(handle)
            at = info.get("insertion_point") or []
            expect(info.get("block_name") == "LC-AP9-SUPPORT" and info.get("layer") == layer,
                   f"{handle} is {info.get('block_name')} on {info.get('layer')}, not LC-AP9-SUPPORT on {layer}")
            expect(near_point(at, _at(o, x, y, 2700.0), 1e-6),
                   f"{handle} is at {_rel(o, at) if at else '?'} z {at[2] if len(at) > 2 else '?'}, not {x:g},{y:g} z 2700")
            got = float(info.get("rotation_degrees") or 0.0) % 360.0
            expect(near(got, turn, 1e-6) or near(got, turn + 360.0, 1e-6), f"{handle} is turned {got:g}, not {turn:g} degrees")
        seen.append(", ".join(f"{x:g},{y:g} at {t:g}" for (x, y), t in want))
    return (f"two supports at {seen[0]} degrees, z 2700, on {layer}; from the end {seen[1]} degrees (Heron does "
            "not turn them round). AutoCAD's own MEASURE Block was not compared, so whether it turns blocks "
            "round from the far end is not recorded")


async def ap10_a_run_out_of_plan_is_refused(ctx: Context) -> str:
    o = lc.origin("AP10")
    tilt = math.radians(30)
    # Up the Y axis of a UCS tilted 30 degrees about X, and a line climbing 500 over 1000.
    tilted = await lc.by_hand_line(_at(o, 0, 0, 0.0), _at(o, 0, 1000 * math.cos(tilt), 1000 * math.sin(tilt)))
    sloping = await lc.by_hand_line(_at(o, 0, 2000, 0.0), _at(o, 1000, 2000, 500.0))
    before = await lc.entity_count()
    said = []
    for handle in (tilted, sloping):
        message = refusal(await draw_extra.autocad_divide_curve(path_handle=handle, segments=2))
        expect("slopes in Z" in message or "not flat" in message, f"{handle} was not refused plainly: {message[:160]}")
        said.append(message[:70])
    expect(await lc.entity_count() == before, "points were placed on a run that is not flat")
    return (f"both refused, nothing placed: '{said[0]}...'. Not tried: a line along the tilted UCS's own X axis "
            "(flat in world, so Heron would mark it: it reads a line's ends, not its normal), and the paper-space "
            "polyline (it needs a sheet tab made active by hand)")


DRAWING_AP: tuple[Check, ...] = (
    Check("AP1", "AP", "a construction line and a ray run where asked", ap1_a_construction_line_and_a_ray_run_where_asked),
    Check("AP2", "AP", "a region has the right area, the outline stays",
          ap2_a_region_has_the_right_area_and_the_outline_stays),
    Check("AP4", "AP", "an open outline and a text are refused", ap4_an_open_outline_and_a_text_are_refused),
    Check("AP5", "AP", "donuts and a dot are wide closed polylines", ap5_donuts_and_a_dot_are_wide_closed_polylines),
    Check("AP6", "AP", "divide a line in four", ap6_divide_a_line_in_four),
    Check("AP7", "AP", "divide a circle and a rectangle in four", ap7_divide_a_circle_and_a_rectangle_in_four),
    Check("AP8", "AP", "measure a line from either end", ap8_measure_a_line_from_either_end),
    Check("AP9", "AP", "measure places turned supports at the run's height",
          ap9_measure_places_turned_supports_at_the_runs_height),
    Check("AP10", "AP", "a run out of plan is refused", ap10_a_run_out_of_plan_is_refused),
)

EYE_AP: dict[str, str] = {
    "AP3": "erase_outlines erases the lines and the circle, so Heron asks you to keep them erased (D-50) "
           "and the runner cannot answer",
    "AP11": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
}


# ---------------------------------------------------------------------------
# Group AM - a preview of a full sheet: what it covered, and close-ups
# ---------------------------------------------------------------------------


async def _preview(**kwargs: Any) -> tuple[list[Any], dict[str, Any]]:
    """autocad_preview: its pictures (each checked to be a PNG) and its JSON."""
    out = await document.autocad_preview(**kwargs)
    if not isinstance(out, list):
        parse(out)  # an error becomes Failed or Refused
        raise lc.Failed(f"no picture came back: {str(out)[:160]}")
    expect(len(out) >= 2, f"the preview gave {len(out)} parts, not pictures and an answer")
    pictures, info = out[:-1], parse(out[-1])
    for n, picture in enumerate(pictures, start=1):
        expect((getattr(picture, "data", b"") or b"")[:8] == PNG, f"picture {n} is not a PNG")
    return pictures, info


async def _sheet(ctx: Context, row: str) -> tuple[str, tuple[float, float]]:
    """A new drawing holding an A1 frame (841 x 594) with 2.5 high text in each quarter. Its name."""
    name = await lc.new_drawing(ctx)
    o = lc.origin(row)
    await _draw(
        {"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 841, 594), "layer": f"LC-{row}-FRAME"},
        *({"type": "text", "position": _at(o, x, y), "text": f"{row} {x},{y}", "height": 2.5, "layer": f"LC-{row}"}
          for x, y in ((100, 450), (600, 450), (100, 150), (600, 150))),
    )
    return name, o


async def _back(ctx: Context, name: str) -> None:
    await lc.close_drawing(ctx, name)
    await lc.activate(ctx)


def _overlap(parts: dict[str, dict[str, Any]], left: str, right: str, upper: str, lower: str) -> bool:
    """The neighbours reach a little into each other, across and up and down."""
    a, b, c, d = parts[left], parts[right], parts[upper], parts[lower]
    return a["corner2"][0] > b["corner1"][0] and d["corner2"][1] > c["corner1"][1]


async def am2_close_ups_come_in_parts_top_left_first(ctx: Context) -> str:
    name, _ = await _sheet(ctx, "AM2")
    try:
        seen = []
        for detail, names in ((2, ["top left", "top right", "bottom left", "bottom right"]),
                              (3, ["top left", "top centre", "top right", "middle left", "centre",
                                   "middle right", "bottom left", "bottom centre", "bottom right"])):
            pictures, info = await _preview(detail=detail)
            parts = info.get("detail") or []
            expect(len(pictures) == 1 + detail * detail, f"detail={detail} gave {len(pictures)} pictures, not {1 + detail * detail}")
            expect([p.get("part") for p in parts] == names, f"detail={detail} parts are {[p.get('part') for p in parts]}")
            expect([p.get("picture") for p in parts] == list(range(2, 2 + len(names))),
                   f"detail={detail} pictures are numbered {[p.get('picture') for p in parts]}")
            by = {p["part"]: p for p in parts}
            last = names[detail - 1]
            expect(_overlap(by, "top left", names[1], "top left", names[detail]),
                   f"detail={detail}: the top left part does not overlap its neighbours ({by['top left']}, {by[last]})")
            whole, close = info.get("smallest_clear_text"), info.get("detail_smallest_clear_text")
            expect(whole and close and float(close) < float(whole),
                   f"detail={detail}: the close-ups read {close}, the whole sheet {whole}: not smaller")
            seen.append((detail, whole, close))
        (_, whole, two), (_, _, three) = seen
        expect(float(three) <= 2.5, f"detail=3 close-ups read text down to {three} only, so 2.5 mm text does not show")
        return (f"5 then 10 pictures, parts named top left first with corners, overlapping at the seams; the "
                f"smallest clear text {whole} for the sheet, {two} at detail=2, {three} at detail=3. Whether the "
                "2.5 mm text really reads was not looked at")
    finally:
        await _back(ctx, name)


async def am3_a_preview_leaves_the_page_setup_alone(ctx: Context) -> str:
    o = lc.origin("AM3")
    await _draw({"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 841, 594), "layer": "LC-AM3"})
    setup, background = await page_setup(), await lc.variable("BACKGROUNDPLOT")
    pictures, info = await _preview(area="window", corner1=_at(o, -10, -10), corner2=_at(o, 851, 604), detail=2)
    expect(len(pictures) == 5, f"the preview gave {len(pictures)} pictures, not 5")
    expect(not info.get("warning"), f"the preview could not put something back: {info.get('warning')}")
    after, background_after = await page_setup(), await lc.variable("BACKGROUNDPLOT")
    changed = {k: (setup.get(k), after.get(k)) for k in setup if setup.get(k) != after.get(k)}
    expect(not changed, f"the page setup changed: {changed}")
    expect(background_after == background, f"BACKGROUNDPLOT went from {background} to {background_after}")
    return (f"after 5 pictures the {setup.get('layout')} page setup is as before ({setup.get('ConfigName')}, "
            f"{setup.get('CanonicalMediaName')}, plot type {setup.get('PlotType')}, rotation "
            f"{setup.get('PlotRotation')}) and BACKGROUNDPLOT is still {background}. The one U was not tried")


async def am4_a_far_off_line_stretches_the_picture(ctx: Context) -> str:
    name, o = await _sheet(ctx, "AM4")
    try:
        (far,) = await _draw({"type": "line", "start": _at(o, 100000, 100000), "end": _at(o, 100010, 100000),
                              "layer": "LC-AM4"})
        _, first = await _preview()
        box = first.get("plotted") or {}
        top = box.get("max") or [0, 0]
        expect(near_point(top, _at(o, 100010, 100000), 1.0),
               f"with the far line the preview plotted up to {_rel(o, top) if box else 'nothing said'}, not 100010,100000")
        expect(float(box.get("width") or 0) >= 100000, f"the plotted width is {box.get('width')}: the sheet is not small")
        await by_hand_erase(far)
        _, second = await _preview()
        again = second.get("plotted") or {}
        expect(again.get("max"), f"the second preview says nothing of what it plotted: {second}")
        shrank = float(again["max"][0]) - o[0] < 1000
        said = ("shrank back to the sheet (the regen refreshed the extents)" if shrank
                else f"still reaches {_rel(o, again['max'])} (stale until ZOOM E: the code should do more)")
        return (f"with the line, plotted reached 100010,100000 ({box.get('width'):g} wide, smallest clear text "
                f"{first.get('smallest_clear_text')}); after erasing it by hand, plotted {said}")
    finally:
        await _back(ctx, name)


async def am5_the_png_plotter_sizes_for_big_and_small(ctx: Context) -> str:
    o = lc.origin("AM5")
    await _draw({"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 841, 594), "layer": "LC-AM5"})
    found = []
    for width in (4000, 640):
        _, info = await _preview(area="window", corner1=_at(o, 0, 0), corner2=_at(o, 841, 594), width_px=width)
        expect(info.get("size") and info.get("pixels"), f"width_px={width} says size {info.get('size')}, pixels {info.get('pixels')}")
        found.append((width, info["size"], info["pixels"]))
    (_, big_size, big), (_, small_size, small) = found
    expect(big[0] >= small[0], f"asking 4000 gave {big}, asking 640 gave {small}: the bigger ask got fewer pixels")
    return (f"width_px=4000: '{big_size}', pixels {big[0]} x {big[1]}; width_px=640: '{small_size}', pixels "
            f"{small[0]} x {small[1]}{' (the same size: the plotter may offer only one)' if big == small else ''}")


async def am6_no_close_ups_in_a_3d_view_and_none_of_the_view(ctx: Context) -> str:
    parse(await solids.autocad_set_3d_view(direction="sw_iso"))
    try:
        pictures, info = await _preview(detail=2)
        skipped = str(info.get("detail_skipped") or "")
        expect(len(pictures) == 1 and not info.get("detail"), f"in sw_iso the preview gave {len(pictures)} pictures, not 1")
        expect("plan view" in skipped, f"detail_skipped does not name the plan view: {skipped[:160] or 'none'}")
        message = refusal(await document.autocad_preview(area="view", detail=2))
        expect("area='extents'" in message and "'window'" in message,
               f"area='view' with detail was not refused naming extents or window: {message[:160]}")
    finally:
        parse(await solids.autocad_set_3d_view(direction="top"))
    return f"in sw_iso one picture and detail_skipped: '{skipped[:80]}'; area='view' with detail refused: '{message[:80]}'"


DRAWING_AM: tuple[Check, ...] = (
    Check("AM2", "AM", "close-ups come in parts, top left first", am2_close_ups_come_in_parts_top_left_first),
    Check("AM3", "AM", "a preview leaves the page setup alone", am3_a_preview_leaves_the_page_setup_alone),
    Check("AM4", "AM", "a far-off line stretches the picture", am4_a_far_off_line_stretches_the_picture),
    Check("AM5", "AM", "the PNG plotter sizes for big and small", am5_the_png_plotter_sizes_for_big_and_small),
    Check("AM6", "AM", "no close-ups in a 3D view, none of the view",
          am6_no_close_ups_in_a_3d_view_and_none_of_the_view),
)

EYE_AM: dict[str, str] = {
    "AM1": "needs the A1 automation room SLD from 2026-10-28 and an eye on what the picture shows",
}


CHECKS: tuple[Check, ...] = DRAWING_AP + DRAWING_AM
BY_EYE: dict[str, str] = {**EYE_AP, **EYE_AM}
