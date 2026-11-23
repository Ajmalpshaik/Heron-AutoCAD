"""Live checks for the pyramid, the polysolid and the solid face edits (group AR).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Sizes and volumes are read from the tools' own answers, and the solid's extents
from ``autocad_get_entity``; every number comes from the row's own words. The
plug-in does these operations, so a plug-in older than this change answers
that it cannot, and the row fails with those words: install the current one.
What PLAN and an isometric preview show is not looked at, and Ctrl+Z after each
row is left to a person. AR12 makes its two-piece solid with a union, which erases
the two boxes (Heron asks, D-50); AR13 needs Ask to Keep on, which stops the runner.
"""

from __future__ import annotations

import math
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, parse, refusal

from autocad_mcp.tools import (
    batch,
    coordinates,
    draw,
    primitives,
    query,
    solid_edits,
    solid_faces,
    solids,
)

BOX_VOLUME = 1000 * 600 * 500


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _box(o: tuple[float, float], x: float, y: float, layer: str) -> str:
    made = parse(await solids.autocad_add_solid(shape="box", base=_at(o, x, y), length=1000, width=600, height=500, layer=layer))
    expect(near(made.get("volume"), BOX_VOLUME, BOX_VOLUME * 1e-6), f"the test box has volume {made.get('volume')}, not 300,000,000")
    return made["handle"]


async def _extent(handle: str) -> tuple[list[float], list[float]]:
    box = (await query_entity(handle)).get("bounding_box") or {}
    expect(box.get("min") and box.get("max"), f"{handle} has no extents to read")
    return box["min"], box["max"]


async def query_entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


def _volume_is(got: Any, want: float, what: str, tol: float | None = None) -> None:
    allowed = want * 1e-6 if tol is None else tol
    expect(near(got, want, allowed), f"{what} is {got}, not {want:,.0f}")


async def ar1_a_pyramid_stands_on_z0_with_its_sides_along_x_and_y(ctx: Context) -> str:
    o = lc.origin("AR1")
    made = parse(await primitives.autocad_add_pyramid(base=[*_at(o, 0, 0), 0], radius=300, height=900, layer="LC-AR1"))
    _volume_is(made.get("volume"), 108_000_000, "the volume", 108_000_000 * 1e-4)
    _volume_is(made.get("expected_volume"), 108_000_000, "the expected volume", 108_000_000 * 1e-4)
    expect(made.get("turned") is True, f"turned is {made.get('turned')}, not true")
    lo, hi = await _extent(made["handle"])
    expect(near(lo[2], 0, 1e-3) and near(hi[2], 900, 1e-3), f"it spans z {lo[2]} to {hi[2]}, not 0 to 900")
    expect(near(lo[0], o[0] - 300, 0.01) and near(hi[0], o[0] + 300, 0.01) and near(lo[1], o[1] - 300, 0.01) and near(hi[1], o[1] + 300, 0.01),
           f"its base spans x {lo[0]:.2f} to {hi[0]:.2f}, y {lo[1]:.2f} to {hi[1]:.2f}, not +-300 round the centre")
    return (f"base 600 x 600 on z=0 with corners at +-300 (extents read), height 900, volume {made['volume']:,.0f} = expected "
            f"{made['expected_volume']:,.0f}, turned true. remade_to_size = {made.get('remade_to_size')} (expected false; to note). "
            "The plan and isometric previews were not looked at")


async def ar2_a_hexagon_frustum_has_two_corners_on_x(ctx: Context) -> str:
    o = lc.origin("AR2")
    made = parse(await primitives.autocad_add_pyramid(base=[*_at(o, 0, 0), 0], sides=6, radius=200, radius_to="corner",
                                                      top_radius=100, height=500, layer="LC-AR2"))
    _volume_is(made.get("volume"), 30_310_889, "the volume", 30_310_889 * 1e-4)
    _volume_is(made.get("expected_volume"), 30_310_889, "the expected volume", 30_310_889 * 1e-4)
    lo, hi = await _extent(made["handle"])
    expect(near(hi[0] - lo[0], 400, 0.05) and near(lo[0], o[0] - 200, 0.05), f"it spans x {lo[0]:.2f} to {hi[0]:.2f}: not corners at +-200 on the X axis")
    expect(near(hi[1] - lo[1], 2 * 173.205, 0.05), f"it spans {hi[1] - lo[1]:.3f} in y, not the flats 346.4 apart")
    expect(near(hi[2], 500, 1e-3), f"its top is at z {hi[2]}, not 500")
    return (f"hexagon with corners on x at -200 and +200 and flats 346.4 apart, top at z=500, volume {made['volume']:,.0f} "
            f"= expected {made['expected_volume']:,.0f}. The flat top's 100 corner radius and the look on screen were not looked at")


async def ar3_a_hopper_and_a_turned_pyramid_on_a_turned_ucs(ctx: Context) -> str:
    o = lc.origin("AR3")
    flat = parse(await primitives.autocad_add_pyramid(base=[*_at(o, 0, 3000), 0], radius=150, top_radius=600, height=900, layer="LC-AR3"))
    lo, hi = await _extent(flat["handle"])
    expect(near(hi[0] - lo[0], 1200, 0.05) and near(hi[1] - lo[1], 1200, 0.05) and near(hi[2], 900, 1e-3) and near(lo[2], 0, 1e-3),
           f"the hopper spans {hi[0] - lo[0]:.2f} x {hi[1] - lo[1]:.2f} x {hi[2] - lo[2]:.2f}, not 1200 x 1200 x 900 from z 0")
    spot = _at(o, 5000, 3000)
    parse(await coordinates.autocad_set_ucs(mode="origin", origin=spot, rotation=30))
    try:
        turned = parse(await primitives.autocad_add_pyramid(base=[0, 0, 0], radius=150, top_radius=600, height=900, rotation=45,
                                                            coords="ucs", layer="LC-AR3"))
    finally:
        parse(await coordinates.autocad_set_ucs(mode="world"))
    lo, hi = await _extent(turned["handle"])
    side = 1200 * (math.cos(math.radians(75)) + math.sin(math.radians(75)))
    expect(near(hi[0] - lo[0], side, 0.5) and near(hi[1] - lo[1], side, 0.5),
           f"the turned one spans {hi[0] - lo[0]:.2f} x {hi[1] - lo[1]:.2f}, not {side:.2f} (a 1200 square turned 75 degrees)")
    expect(near((lo[0] + hi[0]) / 2, spot[0], 0.5) and near((lo[1] + hi[1]) / 2, spot[1], 0.5),
           f"it is centred on {(lo[0] + hi[0]) / 2:.2f}, {(lo[1] + hi[1]) / 2:.2f}, not on the UCS point {spot}")
    return (f"hopper: 1200 x 1200 top at z=900 on a 300 base at z=0, sides along X and Y; with rotation 45 on a UCS turned 30 "
            f"it spans {side:.1f} each way, which a 1200 square turned 75 degrees does (and one turned 15 does too, so the "
            "direction of the turn was not read), about the UCS point; back to the world UCS. The bottom 300 square was not "
            "measured apart from the top")


async def ar4_an_l_wall_has_the_volume_of_its_path(ctx: Context) -> str:
    o = lc.origin("AR4")
    made = parse(await primitives.autocad_add_polysolid(points=[_at(o, 0, 0), _at(o, 5000, 0), _at(o, 5000, 3000)], width=200,
                                                        height=1200, layer="LC-AR4"))
    _volume_is(made.get("volume"), 1_920_000_000, "the volume", 1_920_000_000 * 1e-4)
    lo, hi = await _extent(made["handle"])
    expect(near(lo[2], 0, 1e-3) and near(hi[2], 1200, 1e-3), f"the wall spans z {lo[2]} to {hi[2]}, not 0 to 1200")
    return (f"L wall 200 thick, 1200 high: volume {made['volume']:,.0f} = 8000 x 200 x 1200, from z 0 to 1200. The square outside "
            "corner was not looked at (the volume would be less if it were cut)")


async def ar5_left_and_right_put_the_wall_on_either_side(ctx: Context) -> str:
    o = lc.origin("AR5")
    want = {"left": (1_872_000_000, 0, 5000), "right": (1_968_000_000, -200, 5200)}
    said = []
    for n, (side, (volume, low_y, high_x)) in enumerate(want.items()):
        spot = (o[0] + 10000 * n, o[1])
        made = parse(await primitives.autocad_add_polysolid(points=[_at(spot, 0, 0), _at(spot, 5000, 0), _at(spot, 5000, 3000)],
                                                            width=200, height=1200, side=side, layer="LC-AR5"))
        _volume_is(made.get("volume"), volume, f"the {side} wall's volume", volume * 1e-4)
        lo, hi = await _extent(made["handle"])
        expect(near(lo[1], spot[1] + low_y, 0.05) and near(hi[0], spot[0] + high_x, 0.05),
               f"the {side} wall reaches y {lo[1] - spot[1]:.2f} low and x {hi[0] - spot[0]:.2f} high, not {low_y} and {high_x}")
        said.append(f"{side}: volume {made['volume']:,.0f}, lowest y {low_y}, furthest x {high_x}")
    return "; ".join(said)


async def ar6_inside_and_outside_a_closed_outline(ctx: Context) -> str:
    o = lc.origin("AR6")
    ring = [[0, 0], [4000, 0], [4000, 3000], [0, 3000]]
    said = []
    for n, (name, points) in enumerate((("anticlockwise", ring), ("clockwise", ring[::-1]))):
        spot = (o[0] + 10000 * n, o[1])
        path = parse(await draw.autocad_draw_polyline(points=[_at(spot, *p) for p in points], closed=True, layer="LC-AR6"))
        for side, want in (("inside", 3_168_000_000), ("outside", 3_552_000_000)):
            made = parse(await primitives.autocad_add_polysolid(path=path["handle"], side=side, width=200, height=1200, layer="LC-AR6"))
            _volume_is(made.get("volume"), want, f"the {side} wall on the {name} outline", want * 1e-4)
        expect((await query_entity(path["handle"]))["type"] == "polyline", f"the {name} polyline was not kept")
        said.append(name)
    return ("both outlines, drawn " + " and ".join(said) + ": inside 3,168,000,000 and outside 3,552,000,000; the polylines kept")


async def ar7_arcs_circles_open_rectangles_and_a_tight_arc(ctx: Context) -> str:
    o = lc.origin("AR7")
    arc = parse(await batch.autocad_batch_draw(operations=[
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 3000, 0), _at(o, 4500, 1500), _at(o, 4500, 3500)],
         "bulges": [0, 0.41421356, 0, 0], "layer": "LC-AR7"}]))
    wall = parse(await primitives.autocad_add_polysolid(path=arc["handles"][0], width=200, height=1000, layer="LC-AR7"))
    circle = parse(await draw.autocad_draw_circle(center=_at(o, 8000, 0), radius=1000, layer="LC-AR7"))
    ring = parse(await primitives.autocad_add_polysolid(path=circle["handle"], width=200, height=1000, layer="LC-AR7"))
    for what, made in (("polyline with an arc", wall), ("circle", ring)):
        want = made["path_length"] * 200 * 1000
        expect(near(made.get("volume"), want, want * 2e-3), f"the {what}'s wall has volume {made.get('volume')}, not its path length x 200 x 1000 = {want:,.0f}")
    open_rect = parse(await batch.autocad_batch_draw(operations=[
        {"type": "polyline", "points": [_at(o, 0, 6000), _at(o, 4000, 6000), _at(o, 4000, 9000), _at(o, 0, 9000), _at(o, 0, 6000)],
         "closed": False, "layer": "LC-AR7"}]))
    box_wall = parse(await primitives.autocad_add_polysolid(path=open_rect["handles"][0], side="inside", width=200, height=1000, layer="LC-AR7"))
    expect(box_wall.get("closed") is True, f"the unclosed rectangle's wall says closed={box_wall.get('closed')}, not a ring")
    expect(((await query_entity(open_rect["handles"][0]))).get("closed") is False, "the polyline was closed by the tool: it must be left as drawn")
    tight = parse(await batch.autocad_batch_draw(operations=[
        {"type": "polyline", "points": [_at(o, 0, 12000), _at(o, 1000, 12000), _at(o, 1100, 12000), _at(o, 2000, 12000)],
         "bulges": [0, 1, 0, 0], "layer": "LC-AR7"}]))
    said = refusal(await primitives.autocad_add_polysolid(path=tight["handles"][0], width=200, height=1000, layer="LC-AR7"))
    expect("turns tighter than the wall is wide" in said and "Nothing was changed" in said, f"the tight arc was refused in other words: {said[:160]}")
    return ("a polyline with an arc and a circle both give a wall whose volume is path length x 200 x 1000; the unclosed rectangle "
            "makes a ring (closed true) with its polyline left as drawn; the radius 50 arc is refused 'turns tighter than the "
            "wall is wide ... Nothing was changed'. That the walls follow the curves smoothly on screen was not looked at")


async def ar8_offset_and_move_a_face(ctx: Context) -> str:
    o = lc.origin("AR8")
    first = await _box(o, 0, 0, "LC-AR8")
    out = parse(await solid_faces.autocad_edit_solid_faces(handle=first, action="offset", faces="top", distance=100))
    _volume_is(out.get("volume_after"), 360_000_000, "the volume after the offset", 360_000_000 * 1e-4)
    lo, hi = await _extent(first)
    expect(near(hi[2] - lo[2], 600, 0.01), f"the box is {hi[2] - lo[2]:.3f} high after the offset, not 600")
    second = await _box(o, 5000, 0, "LC-AR8")
    out = parse(await solid_faces.autocad_edit_solid_faces(handle=second, action="move", faces="right", by=[200, 0, 0]))
    _volume_is(out.get("volume_after"), 360_000_000, "the volume after the move", 360_000_000 * 1e-4)
    lo, hi = await _extent(second)
    expect(near(hi[0] - lo[0], 1200, 0.01), f"the box is {hi[0] - lo[0]:.3f} long after the move, not 1200")
    return "offset top by 100: 600 high, volume 360,000,000; move the right face by 200: 1200 long, volume 360,000,000"


async def ar9_a_tapered_face_changes_the_volume(ctx: Context) -> str:
    o = lc.origin("AR9")
    handle = await _box(o, 0, 0, "LC-AR9")
    out = parse(await solid_faces.autocad_edit_solid_faces(handle=handle, action="taper", faces="front", angle=10))
    before, after = out.get("volume_before"), out.get("volume_after")
    expect(before is not None and after is not None and not near(before, after, 1000), f"the volume went from {before} to {after}: the face did not lean")
    leaned = "in (smaller)" if after < before else "out (larger)"
    return (f"the front face leaned {leaned}: volume {before:,.0f} to {after:,.0f} (the row expects in, about 277,959,000; the tool's "
            "wording says in, to be fixed to match if not). That the bottom edge stays on its line was not looked at")


async def ar10_deleting_a_fillet_face_squares_the_corner(ctx: Context) -> str:
    o = lc.origin("AR10")
    filleted = await _box(o, 0, 0, "LC-AR10")
    parse(await solid_edits.autocad_fillet_solid_edges(handle=filleted, radius=50, edges="vertical"))
    listed = parse(await solid_edits.autocad_list_solid_faces_and_edges(handle=filleted))
    curved = [f["index"] for f in listed["faces"] if "normal" not in f]
    expect(curved, f"none of its {listed['face_count']} faces is curved after the fillet")
    out = parse(await solid_faces.autocad_edit_solid_faces(handle=filleted, action="delete", faces=[curved[0]]))
    gain = out["volume_after"] - out["volume_before"]
    expect(near(gain, 268_000, 1500), f"the volume rose by {gain:,.0f}, not about 268,000")
    plain = await _box(o, 5000, 0, "LC-AR10")
    said = refusal(await solid_faces.autocad_edit_solid_faces(handle=plain, action="delete", faces="top"))
    after = parse(await solid_edits.autocad_list_solid_faces_and_edges(handle=plain))
    expect(near(after.get("volume"), BOX_VOLUME, BOX_VOLUME * 1e-6), f"the refused delete left the box at volume {after.get('volume')}")
    return (f"deleting fillet face {curved[0]} raised the volume by {gain:,.0f} (about 268,000), so that corner is square; deleting "
            f"the top of a plain box is refused ('{said[:80]}') and its volume is unchanged. The look of the corner was not examined")


async def ar11_imprint_a_rectangle_and_pull_its_pad(ctx: Context) -> str:
    o = lc.origin("AR11")
    handle = await _box(o, 0, 0, "LC-AR11")
    rect = parse(await draw.autocad_draw_rectangle(corner1=[o[0] - 200, o[1] - 100, 500], corner2=[o[0] + 200, o[1] + 100, 500], layer="LC-AR11"))
    out = parse(await solid_faces.autocad_imprint_solid(handle=handle, objects=[rect["handle"]]))
    expect(out.get("faces_before") == 6 and out.get("faces_after") == 7, f"the faces went from {out.get('faces_before')} to {out.get('faces_after')}, not 6 to 7")
    expect((await query_entity(rect["handle"]))["type"] == "polyline", "the rectangle was not kept")
    listed = parse(await solid_edits.autocad_list_solid_faces_and_edges(handle=handle))
    pad = [f["index"] for f in listed["faces"] if near(f.get("area"), 400 * 200, 1.0)]
    expect(len(pad) == 1, f"{len(pad)} faces have the pad's area of 80,000")
    pulled = parse(await solid_edits.autocad_press_pull_faces(handle=handle, faces=[pad[0]], distance=100))
    gain = pulled["volume_after"] - pulled["volume_before"]
    expect(near(gain, 400 * 200 * 100, 8000), f"the pull added {gain:,.0f}, not 8,000,000 (the 400 x 200 pad, 100 high)")
    far = parse(await draw.autocad_draw_line(start=[o[0] + 5000, o[1], 500], end=[o[0] + 6000, o[1], 500], layer="LC-AR11"))
    nothing = parse(await solid_faces.autocad_imprint_solid(handle=handle, objects=[far["handle"]]))
    expect("Nothing new was imprinted" in str(nothing.get("note")), f"a line 5 m away gave the note {nothing.get('note')!r}")
    return ("imprint: faces 6 to 7 and the rectangle kept; pulling the new face 100 raised the volume by 8,000,000 (only the "
            "400 x 200 pad); a line 5 m away: 'Nothing new was imprinted'")


CHECKS: tuple[Check, ...] = (
    Check("AR1", "AR", "a pyramid stands on z=0 with its sides along X and Y", ar1_a_pyramid_stands_on_z0_with_its_sides_along_x_and_y),
    Check("AR2", "AR", "a hexagon frustum has two corners on X", ar2_a_hexagon_frustum_has_two_corners_on_x),
    Check("AR3", "AR", "a hopper and a turned pyramid on a turned UCS", ar3_a_hopper_and_a_turned_pyramid_on_a_turned_ucs),
    Check("AR4", "AR", "an L wall has the volume of its path", ar4_an_l_wall_has_the_volume_of_its_path),
    Check("AR5", "AR", "left and right put the wall on either side", ar5_left_and_right_put_the_wall_on_either_side),
    Check("AR6", "AR", "inside and outside a closed outline", ar6_inside_and_outside_a_closed_outline),
    Check("AR7", "AR", "arcs, circles, open rectangles and a tight arc", ar7_arcs_circles_open_rectangles_and_a_tight_arc),
    Check("AR8", "AR", "offset and move a face", ar8_offset_and_move_a_face),
    Check("AR9", "AR", "a tapered face changes the volume", ar9_a_tapered_face_changes_the_volume),
    Check("AR10", "AR", "deleting a fillet face squares the corner", ar10_deleting_a_fillet_face_squares_the_corner),
    Check("AR11", "AR", "imprint a rectangle and pull its pad", ar11_imprint_a_rectangle_and_pull_its_pad),
)

BY_EYE: dict[str, str] = {
    "AR12": "the two-piece solid comes from a union, which erases the two boxes, so Heron asks to keep the change or undo the whole change (D-140)",
    "AR13": "needs Ask to Keep on and Discard answered by hand each time, and the runner stops when Ask to Keep is on",
    "AR14": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
}
