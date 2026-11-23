"""Live checks for the drawing tools on a UCS, batch fills, multilines and splines (group AI).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
What an eye must judge (the view in PLAN, a corner zoomed in, a fill's shape on
screen, one Ctrl+Z taking a whole job back) is not looked at: each row says in its
evidence what was measured and what was left. AI7 would erase the pipe it breaks
(Heron asks, D-50), AI9 needs the server started with --no-bridge, and AI14 is
judged by looking at a fill.
"""

from __future__ import annotations

import math
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, near_point, parse, refusal

from autocad_mcp.tools import (
    batch,
    blocks,
    coordinates,
    drafting,
    draw,
    modify,
    query,
)

TURN = 30.0
AI5_NOTE = ("PIPEWORK TO BE PRESSURE TESTED BEFORE LAGGING. " * 13)[:600]


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


def _world(o: tuple[float, float], x: float, y: float, turn: float = TURN) -> list[float]:
    """A point of the turned UCS (origin ``o``, turned ``turn`` degrees) as the world point it is."""
    a = math.radians(turn)
    return [o[0] + x * math.cos(a) - y * math.sin(a), o[1] + x * math.sin(a) + y * math.cos(a)]


def _side_angle(a: list[float], b: list[float]) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360.0


async def _turned_ucs(o: tuple[float, float], turn: float = TURN) -> None:
    parse(await coordinates.autocad_set_ucs(mode="origin", origin=[o[0], o[1]], rotation=turn))


async def _entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


async def _block_of_two_lines(row: str, o: tuple[float, float]) -> str:
    """A block of an L of two lines, made in the world before a UCS is set. Its name."""
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 500, 0), "layer": f"LC-{row}"},
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 0, 300), "layer": f"LC-{row}"},
    ]))
    name = f"LC-{row}-MARK"
    parse(await blocks.autocad_make_block(name=name, handles=made["handles"], base_point=_at(o, 0, 0)))
    return name


async def ai1_the_draw_tools_come_out_square_to_the_ucs(ctx: Context) -> str:
    o = lc.origin("AI1")
    block = await _block_of_two_lines("AI1", _at(o, -5000, 0))
    await _turned_ucs(o)
    try:
        rect = parse(await draw.autocad_draw_rectangle(corner1=[0, 0], corner2=[2000, 1000], layer="LC-AI1", coords="ucs"))
        arc = parse(await draw.autocad_draw_arc(center=[0, 0], radius=500, start_angle=0, end_angle=90, layer="LC-AI1",
                                                coords="ucs"))
        text = parse(await draw.autocad_add_text(text="A", position=[0, 1500], rotation=0, layer="LC-AI1", coords="ucs"))
        placed = parse(await draw.autocad_insert_block(block_name=block, position=[3000, 0], rotation=0, layer="LC-AI1",
                                                       coords="ucs"))
    finally:
        parse(await coordinates.autocad_set_ucs(mode="world"))
    for what, answer in (("rectangle", rect), ("arc", arc), ("text", text), ("block", placed)):
        said = answer.get("converted_from_ucs") or {}
        expect(near(said.get("rotation_degrees"), TURN, 1e-6), f"the {what}'s answer names the UCS {said.get('rotation_degrees')}, not {TURN:g}")
    verts = (await _entity(rect["handle"]))["vertices"]
    expect(near_point(verts[0], _world(o, 0, 0), 1e-3), f"the rectangle starts at {verts[0]}, not the UCS origin")
    expect(near(_side_angle(verts[0], verts[1]), TURN, 1e-3) and near(math.dist(verts[0], verts[1]), 2000, 1e-3),
           f"the first side is {math.dist(verts[0], verts[1]):.3f} long at {_side_angle(verts[0], verts[1]):.3f} degrees, not 2000 at 30")
    expect(near(math.dist(verts[1], verts[2]), 1000, 1e-3) and near(_side_angle(verts[1], verts[2]), TURN + 90, 1e-3),
           f"the second side is {math.dist(verts[1], verts[2]):.3f} long at {_side_angle(verts[1], verts[2]):.3f} degrees, not 1000 at 120")
    got = await _entity(arc["handle"])
    expect(near(got["start_angle_degrees"], TURN, 1e-3) and near(got["end_angle_degrees"], TURN + 90, 1e-3),
           f"the arc runs {got['start_angle_degrees']} to {got['end_angle_degrees']}, not 30 to 120")
    expect(near_point(got["center"], _world(o, 0, 0), 1e-3), f"the arc's centre is {got['center']}")
    got = await _entity(text["handle"])
    expect(near(got["rotation_degrees"], TURN, 1e-3) and near_point(got["insertion_point"], _world(o, 0, 1500), 1e-3),
           f"the text is at {got['insertion_point']} turned {got['rotation_degrees']}, not on the UCS")
    got = await _entity(placed["handle"])
    expect(near(got["rotation_degrees"], TURN, 1e-3) and near_point(got["insertion_point"], _world(o, 3000, 0), 1e-3),
           f"the block is at {got['insertion_point']} turned {got['rotation_degrees']}, not on the UCS")
    return ("on a UCS turned 30 degrees: the rectangle's sides are 2000 at 30 and 1000 at 120, the arc runs 30 to 120 about the "
            "UCS origin, the text and the block read at 30 degrees on their UCS points, and every answer names the 30 degree "
            "UCS. PLAN, World was not looked at (the numbers are the world's); back to the world UCS")


async def ai2_modify_tools_work_along_the_ucs(ctx: Context) -> str:
    o = lc.origin("AI2")
    await _turned_ucs(o)
    try:
        dim = parse(await draw.autocad_add_dimension(dimension_type="horizontal", point1=[0, 0], point2=[2000, 0],
                                                     text_position=[1000, -300], layer="LC-AI2", coords="ucs"))
        rect = parse(await draw.autocad_draw_rectangle(corner1=[0, 0], corner2=[2000, 1000], layer="LC-AI2", coords="ucs"))
        circle = parse(await draw.autocad_draw_circle(center=[5000, 0], radius=100, layer="LC-AI2", coords="ucs"))
        parse(await modify.autocad_move_entities(handles=[rect["handle"]], displacement=[0, 1200], coords="ucs"))
        parse(await modify.autocad_rotate_entities(handles=[rect["handle"]], base_point=[0, 0], angle=15, coords="ucs"))
        grid = parse(await modify.autocad_array_entities(handles=[circle["handle"]], rows=2, columns=3, row_spacing=400,
                                                         column_spacing=600, coords="ucs"))
    finally:
        parse(await coordinates.autocad_set_ucs(mode="world"))
    expect(near(parse(await query.autocad_get_entity(handle=dim["handle"])).get("measurement"), 2000, 1e-3),
           f"the dimension reads {dim.get('measurement')}, not 2000 along the UCS X")
    verts = (await _entity(rect["handle"]))["vertices"]
    a = math.radians(15)
    want = _world(o, -1200 * math.sin(a), 1200 * math.cos(a))
    expect(near_point(verts[0], want, 1e-3), f"after the move and the turn the rectangle starts at {verts[0]}, not {want}")
    expect(near(_side_angle(verts[0], verts[1]), TURN + 15, 1e-3), f"its first side runs at {_side_angle(verts[0], verts[1]):.3f}, not 45")
    handles = [circle["handle"], *grid["new_handles"]]
    expect(len(handles) == 6, f"the array made {len(handles) - 1} copies, not 5")
    centres: list[list[float]] = []
    for h in handles:
        centres.append([round(c, 2) for c in (await _entity(h))["center"][:2]])
    centres.sort()
    wanted = sorted([round(c, 2) for c in _world(o, 5000 + 600 * i, 400 * j)] for i in range(3) for j in range(2))
    expect(centres == wanted, f"the six circles sit at {centres}, not on the UCS grid {wanted}")
    return ("on a UCS turned 30 degrees: the dimension reads 2000, the rectangle moved 1200 up the UCS and turned 15 about its "
            "origin (first corner and side angle 45 as worked out), the six circles sit on the 600 x 400 grid square to the UCS. "
            "Where the dimension's text sits (300 below) was not looked at; back to the world UCS")


async def ai3_a_raised_ucs_gives_the_elevation_and_a_flipped_one_is_refused(ctx: Context) -> str:
    o = lc.origin("AI3")
    parse(await coordinates.autocad_set_ucs(mode="origin", origin=[o[0], o[1], 3000]))
    try:
        run = parse(await draw.autocad_draw_polyline(points=[[0, 0], [1000, 0], [1000, 1000]], layer="LC-AI3", coords="ucs"))
        height = (await lc.read_props(run["handle"], ["Elevation"])).get("Elevation")
        expect(near(height, 3000, 1e-6), f"the polyline's elevation is {height}, not 3000")
        parse(await coordinates.autocad_set_ucs(mode="3point", origin=[o[0], o[1], 0], point_on_x=[o[0] + 1, o[1], 0],
                                                point_on_y=[o[0], o[1] - 1, 0]))
        before = await lc.entity_count()
        said = refusal(await draw.autocad_add_text(text="FLIPPED", position=[0, 0], layer="LC-AI3", coords="ucs"))
        expect("flipped" in said, f"the refusal does not say the UCS is flipped: {said[:140]}")
        expect(await lc.entity_count() == before, "a refused text still changed the drawing")
    finally:
        parse(await coordinates.autocad_set_ucs(mode="world"))
    return ("UCS raised to 3000: the polyline's elevation reads 3000; a flipped UCS (Y down): add_text refused naming 'flipped', "
            "nothing drawn. The arc drawn on the flipped UCS was not looked at (it is judged by how it reads in that view); "
            "back to the world UCS")


async def ai4_batch_fills_are_solid_with_a_hole(ctx: Context) -> str:
    o = lc.origin("AI4")
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "hatch", "points": [_at(o, 0, 0), _at(o, 100, 0), _at(o, 50, 80)], "color": 1, "layer": "LC-AI4"},
        {"type": "hatch", "points": [_at(o, 200, 0), _at(o, 300, 0)], "bulges": [0, 1], "layer": "LC-AI4"},
        {"type": "hatch", "points": [_at(o, 400, 0), _at(o, 600, 0), _at(o, 600, 200), _at(o, 400, 200)], "layer": "LC-AI4",
         "holes": [[_at(o, 450, 50), _at(o, 550, 50), _at(o, 500, 150)]]},
    ]))
    expect(made["created"] == 3 and made["failed"] == 0, f"created {made['created']}, failed {made['failed']}, not 3 and 0")
    rows = [await _entity(h) for h in made["handles"]]
    for handle, row in zip(made["handles"], rows, strict=True):
        expect(row["type"] == "hatch" and str(row["pattern"]).upper() == "SOLID", f"{handle} is a {row['type']} {row.get('pattern')}, not a SOLID hatch")
    expect(rows[0].get("color") == 1, f"the triangle's colour is {rows[0].get('color')}, not 1 (red)")
    expect(near(rows[0]["area"], 100 * 80 / 2, 0.5), f"the triangle's area is {rows[0]['area']}, not 4000")
    expect(rows[0].get("loop_count") == 1 and rows[2].get("loop_count") == 2,
           f"the loops are {rows[0].get('loop_count')} and {rows[2].get('loop_count')}, not 1 (the triangle) and 2 (the square and its hole)")
    return ("3 solid hatches created, 0 failed: the triangle red with area 4000 and one loop, a half-round, and the square with "
            "two loops (its outline and the triangular hole). Not associative, the shapes on screen and one Ctrl+Z were not "
            "looked at")


async def ai5_batch_mtext_holds_the_whole_note(ctx: Context) -> str:
    o = lc.origin("AI5")
    note = AI5_NOTE
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "mtext", "position": _at(o, 0, 0), "text": "NOTE 1\\PNOTE 2", "width": 2000, "height": 250,
         "attach": "middle_center", "layer": "LC-AI5"},
        {"type": "mtext", "position": _at(o, 0, -1000), "text": note, "width": 3000, "layer": "LC-AI5"},
    ]))
    expect(made["created"] == 2 and made["failed"] == 0, f"created {made['created']}, failed {made['failed']}, not 2 and 0")
    first, second = [await _entity(h) for h in made["handles"]]
    expect(first["type"] == "mtext" and "NOTE 1" in first["text"] and "NOTE 2" in first["text"], f"the first note reads {first.get('text')!r}")
    expect(near_point(first["insertion_point"], _at(o, 0, 0), 1e-3), f"the first note is attached at {first['insertion_point']}, not the middle at 0,0")
    expect(second["text"] == note, f"the second note holds {len(second['text'])} characters, not all {len(note)}")
    expect(near(second["width"], 3000, 1e-3), f"the second note is {second['width']} wide, not 3000")
    return "2 mtexts: the first holds NOTE 1 and NOTE 2, attached at its middle on 0,0; the second holds all 600 characters, 3000 wide"


async def ai6_batch_dimensions_read_what_they_measure(ctx: Context) -> str:
    o = lc.origin("AI6")
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "dimension", "point1": _at(o, 0, 0), "point2": _at(o, 5000, 0), "text_position": _at(o, 2500, -800), "layer": "LC-AI6"},
        {"type": "dimension", "dimension_type": "vertical", "point1": _at(o, 0, 0), "point2": _at(o, 300, 3000),
         "text_position": _at(o, -800, 1500), "text_override": "<> TYP", "layer": "LC-AI6"},
    ]))
    expect(made["created"] == 2 and made["failed"] == 0, f"created {made['created']}, failed {made['failed']}: a dimension with no block name was not accepted")
    first, second = [await _entity(h) for h in made["handles"]]
    expect(first["type"] == "dimension" and near(first["measurement"], 5000, 1e-3), f"the aligned dimension reads {first.get('measurement')}, not 5000")
    expect(second["type"] == "dimension" and near(second["measurement"], 3000, 1e-3) and second["text_override"] == "<> TYP",
           f"the vertical one reads {second.get('measurement')} with {second.get('text_override')!r}, not 3000 and '<> TYP'")
    return ("both dimensions made (so AutoCAD took a DIMENSION entmade with no block name); the aligned one reads 5000, the "
            "vertical one 3000 with the text '<> TYP'. DIMSCALE was left as it is (setting it is an Admin step), so their size "
            "on screen, DIMEDIT, grips, and the same on the turned UCS with DIMTIH on were not looked at")


async def ai8_a_closed_multiline_is_mitred(ctx: Context) -> str:
    o = lc.origin("AI8")
    pts = [_at(o, 0, 0), _at(o, 4000, 0), _at(o, 4000, 3000), _at(o, 0, 3000)]
    made = parse(await drafting.autocad_draw_multiline(points=pts, scale=200, closed=True, layer="LC-AI8"))
    expect(made.get("mitred") is True, f"mitred is {made.get('mitred')}, not true")
    expect(not made.get("warning"), f"it warned: {str(made.get('warning'))[:140]}")
    expect(made.get("closed") is True, f"closed is {made.get('closed')}")
    expect(made["vertices"] == 4, f"it has {made['vertices']} vertices, not 4")
    return ("closed 4000 x 3000 multiline, scale 200: mitred true, closed true, 4 vertices, no warning. The last corner zoomed in "
            "and one Ctrl+Z were not looked at")


async def ai10_a_control_point_spline_has_no_fit_points(ctx: Context) -> str:
    o = lc.origin("AI10")
    pts = [_at(o, 0, 0), _at(o, 1000, 1500), _at(o, 3000, 1500), _at(o, 4000, 0), _at(o, 5000, 800)]
    made = parse(await drafting.autocad_draw_spline(points=pts, method="control_points", degree=3, layer="LC-AI10"))
    expect(made.get("control_points") == 5 and made.get("degree") == 3, f"it answers {made.get('control_points')} control points of degree {made.get('degree')}, not 5 and 3")
    got = await _entity(made["handle"])
    expect(got["type"] == "spline" and got["degree"] == 3 and got["control_point_count"] == 5,
           f"AutoCAD holds a {got['type']} of degree {got.get('degree')} with {got.get('control_point_count')} control points")
    expect(got["fit_point_count"] == 0, f"it has {got['fit_point_count']} fit points, not none")
    return ("one SPLINE, degree 3, 5 control points, no fit points. That it starts at 0,0 and ends at 5000,800 with only the ends "
            "on the curve (SPLINEDIT) was not looked at")


async def ai11_a_closed_spline_and_degrees_one_and_two(ctx: Context) -> str:
    o = lc.origin("AI11")
    pts = [_at(o, 0, 0), _at(o, 1000, 1500), _at(o, 3000, 1500), _at(o, 4000, 0), _at(o, 5000, 800)]
    said = []
    closed = parse(await drafting.autocad_draw_spline(points=pts, method="control_points", degree=3, closed=True, layer="LC-AI11"))
    got = await _entity(closed["handle"])
    expect(got["closed"] is True, f"the closed spline reads closed={got['closed']}")
    said.append(f"closed: {got['control_point_count']} control points, degree {got['degree']}")
    for degree in (1, 2):
        made = parse(await drafting.autocad_draw_spline(points=pts, method="control_points", degree=degree, layer="LC-AI11"))
        got = await _entity(made["handle"])
        expect(got["degree"] == degree, f"degree {degree} came out as degree {got['degree']}")
        said.append(f"degree {degree}: {got['control_point_count']} control points")
    return ("closed: LIST says closed; degrees 1 and 2 come out as asked (" + "; ".join(said) + "). Whether the closed curve has "
            "no corner at 0,0 (zoomed in) and what it says about periodic were not looked at")


async def ai12_edit_spline_moves_adds_and_removes_fit_points(ctx: Context) -> str:
    o = lc.origin("AI12")
    start = [_at(o, 0, 0), _at(o, 1000, 500), _at(o, 2000, 0), _at(o, 3000, 800)]
    made = parse(await drafting.autocad_draw_spline(points=start, layer="LC-AI12"))
    handle = made["handle"]
    before = await _entity(handle)
    expect(before["fit_point_count"] == 4, f"the fit spline has {before['fit_point_count']} fit points, not 4")
    out = parse(await drafting.autocad_edit_spline(handle=handle, edits=[
        {"move": 1, "to": _at(o, 1000, 800)}, {"insert": 4, "point": _at(o, 4000, 0)}, {"remove": 0}]))
    expect(out.get("handle") == handle, f"the handle changed from {handle} to {out.get('handle')}")
    want = [_at(o, 1000, 800), _at(o, 2000, 0), _at(o, 3000, 800), _at(o, 4000, 0)]
    after = await _entity(handle)
    got = [p[:2] for p in after.get("fit_points") or []]
    expect(len(got) == 4 and all(near_point(a, b, 1e-3) for a, b in zip(got, want, strict=True)),
           f"the fit points are {got}, not {want}")
    expect(out.get("fit_points_before") == 4 and out.get("fit_points") == 4, f"the answer counts {out.get('fit_points_before')} before and {out.get('fit_points')} after")
    return ("same handle; the fit points read back as the second moved, one added after the last (`insert` at the count did "
            "add after the last point, as the row asks to note) and the first gone. One Ctrl+Z and a closed fit spline's "
            "seam were not tried")


async def ai13_edit_spline_refuses_before_changing_anything(ctx: Context) -> str:
    o = lc.origin("AI13")
    cv = parse(await drafting.autocad_draw_spline(points=[_at(o, 0, 0), _at(o, 1000, 1500), _at(o, 3000, 1500), _at(o, 4000, 0)],
                                                  method="control_points", degree=3, layer="LC-AI13"))
    said_cv = refusal(await drafting.autocad_edit_spline(handle=cv["handle"], edits=[{"move": 0, "to": _at(o, 10, 10)}]))
    expect("no fit points" in said_cv, f"the control-point spline was refused for another reason: {said_cv[:140]}")
    fit = parse(await drafting.autocad_draw_spline(points=[_at(o, 0, 5000), _at(o, 1000, 5500), _at(o, 2000, 5000), _at(o, 3000, 5800)],
                                                   layer="LC-AI13"))
    before = (await _entity(fit["handle"]))["fit_points"]
    said_far = refusal(await drafting.autocad_edit_spline(handle=fit["handle"], edits=[{"move": 9, "to": _at(o, 10, 10)}]))
    expect("9" in said_far and "Nothing was changed" in said_far, f"point 9 was refused in other words: {said_far[:140]}")
    expect((await _entity(fit["handle"]))["fit_points"] == before, "the refused edit still changed the spline")
    return f"both refused before anything changed: '{said_cv[:70]}' and '{said_far[:90]}'; the fit points are as they were"


CHECKS: tuple[Check, ...] = (
    Check("AI1", "AI", "the draw tools come out square to the UCS", ai1_the_draw_tools_come_out_square_to_the_ucs),
    Check("AI2", "AI", "the modify tools work along the UCS", ai2_modify_tools_work_along_the_ucs),
    Check("AI3", "AI", "a raised UCS gives the elevation, a flipped one is refused",
          ai3_a_raised_ucs_gives_the_elevation_and_a_flipped_one_is_refused),
    Check("AI4", "AI", "batch fills are solid, one with a hole", ai4_batch_fills_are_solid_with_a_hole),
    Check("AI5", "AI", "batch mtext holds the whole note", ai5_batch_mtext_holds_the_whole_note),
    Check("AI6", "AI", "batch dimensions read what they measure", ai6_batch_dimensions_read_what_they_measure),
    Check("AI8", "AI", "a closed multiline is mitred", ai8_a_closed_multiline_is_mitred),
    Check("AI10", "AI", "a control-point spline has no fit points", ai10_a_control_point_spline_has_no_fit_points),
    Check("AI11", "AI", "a closed spline and degrees one and two", ai11_a_closed_spline_and_degrees_one_and_two),
    Check("AI12", "AI", "edit_spline moves, adds and removes fit points", ai12_edit_spline_moves_adds_and_removes_fit_points),
    Check("AI13", "AI", "edit_spline refuses before changing anything", ai13_edit_spline_refuses_before_changing_anything),
)

BY_EYE: dict[str, str] = {
    "AI7": "autocad_break_at_blocks replaces the pipe with its pieces, so Heron asks to keep the original erased (D-50), and the gap and the arc are judged on screen",
    "AI9": "needs the server started with --no-bridge, which the runner does not do",
    "AI14": "the fills of the section mark, north arrow, scale bar and level mark are judged by looking at them",
}
