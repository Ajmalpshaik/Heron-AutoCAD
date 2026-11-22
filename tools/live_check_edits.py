"""Live checks for the everyday 2D edits (group AA).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Each row draws its own objects at its own spot (``lc.origin``), then measures what
the tool did: a line's ends, an arc's radius and centre, a polyline's area, a
layer's state read back.
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
    draw,
    edit2d,
    geometry_tools,
    layers,
    modify,
    query,
    settings,
)


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _draw(*operations: dict[str, Any]) -> list[str]:
    """Draw with autocad_batch_draw; the handles, in order."""
    made = parse(await batch.autocad_batch_draw(operations=list(operations)))
    expect(made.get("created") == len(operations), f"drew {made.get('created')} of {len(operations)} test objects")
    return list(made["handles"])


async def _entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


def _ends(info: dict[str, Any]) -> list[list[float]]:
    return [info["start"][:2], info["end"][:2]]


def _runs(info: dict[str, Any], a: list[float], b: list[float], tol: float = 1e-6) -> bool:
    """A line runs from a to b, either way round."""
    s, e = info["start"], info["end"]
    return (near_point(s, a, tol) and near_point(e, b, tol)) or (near_point(s, b, tol) and near_point(e, a, tol))


def _rel(o: tuple[float, float], p: list[float]) -> str:
    return f"{p[0] - o[0]:g},{p[1] - o[1]:g}"


# ---------------------------------------------------------------------------
# Group AA - the everyday 2D edits
# ---------------------------------------------------------------------------


async def aa1_trim_cuts_back_to_the_wall(ctx: Context) -> str:
    o = lc.origin("AA1")
    line, wall = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AA1"},
        {"type": "line", "start": _at(o, 400, -100), "end": _at(o, 400, 100), "layer": "LC-AA1-WALL"},
    )
    out = parse(await edit2d.autocad_trim_extend(
        operation="trim", handles=[line], edges=[wall], points=[_at(o, 200, 0)]
    ))
    expect(out.get("done") == 1 and not out.get("failed"), f"trim did {out.get('done')}, failed {out.get('failed')}")
    piece = out["objects"][0]
    expect(piece["handle"] == line and not piece.get("new_handles"), f"trim answered {piece}")
    info = await _entity(line)
    expect(_runs(info, _at(o, 400, 0), _at(o, 1000, 0)),
           f"the line runs {_rel(o, info['start'])} to {_rel(o, info['end'])}, not 400,0 to 1000,0")
    expect(info["layer"] == "LC-AA1", f"the line is on {info['layer']}, not LC-AA1")
    return (f"same handle {line} now runs 400,0 to 1000,0 on LC-AA1, cut_away {piece.get('cut_away')}; "
            "the one Ctrl+Z was not tried")


async def aa2_two_walls_leave_two_lines_that_look_alike(ctx: Context) -> str:
    o = lc.origin("AA2")
    line, wall1, wall2 = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AA2", "color": "green"},
        {"type": "line", "start": _at(o, 300, -100), "end": _at(o, 300, 100), "layer": "LC-AA2-WALL"},
        {"type": "line", "start": _at(o, 700, -100), "end": _at(o, 700, 100), "layer": "LC-AA2-WALL"},
    )
    parse(await modify.autocad_modify_entity(handles=[line], lineweight=0.35, linetype="HIDDEN"))
    out = parse(await edit2d.autocad_trim_extend(
        operation="trim", handles=[line], edges=[wall1, wall2], points=[_at(o, 500, 0)]
    ))
    expect(out.get("done") == 1, f"trim did {out.get('done')}, failed {out.get('failed')}")
    new = out["objects"][0].get("new_handles") or []
    expect(len(new) == 1, f"trim made {len(new)} new pieces, not 1")
    first, second = await _entity(line), await _entity(new[0])
    left, right = (_at(o, 0, 0), _at(o, 300, 0)), (_at(o, 700, 0), _at(o, 1000, 0))
    expect((_runs(first, *left) and _runs(second, *right)) or (_runs(first, *right) and _runs(second, *left)),
           f"the pieces run {_rel(o, first['start'])}-{_rel(o, first['end'])} and "
           f"{_rel(o, second['start'])}-{_rel(o, second['end'])}, not 0-300 and 700-1000")
    for key in ("layer", "color", "linetype"):
        expect(first.get(key) == second.get(key), f"the new piece's {key} is {second.get(key)}, not {first.get(key)}")
    weights = [(await lc.read_props(h, ["Lineweight"]))["Lineweight"] for h in (line, new[0])]
    expect(weights[0] == weights[1] == 35, f"lineweights are {weights}, not 35 and 35")
    return (f"two lines 0-300 and 700-1000; the new one {new[0]} has the first's layer {first['layer']}, "
            f"colour {first.get('color')}, linetype {first.get('linetype')} and lineweight 0.35")


async def aa4_extend_reaches_the_main_and_an_arc_runs_on(ctx: Context) -> str:
    o = lc.origin("AA4")
    main, *shorts = await _draw(
        {"type": "line", "start": _at(o, 0, 1000), "end": _at(o, 3000, 1000), "layer": "LC-AA4"},
        *({"type": "line", "start": _at(o, x, 0), "end": _at(o, x, 500), "layer": "LC-AA4"} for x in (500, 1500, 2500)),
    )
    out = parse(await edit2d.autocad_trim_extend(operation="extend", handles=shorts, edges=[main]))
    expect(out.get("done") == 3, f"extend did {out.get('done')} of 3, failed {out.get('failed')}")
    for handle, x in zip(shorts, (500, 1500, 2500), strict=True):
        info = await _entity(handle)
        expect(_runs(info, _at(o, x, 0), _at(o, x, 1000)),
               f"{handle} runs {_rel(o, info['start'])} to {_rel(o, info['end'])}, not up to the main at y=1000")
    main_now = await _entity(main)
    expect(_runs(main_now, _at(o, 0, 1000), _at(o, 3000, 1000)), "the main line moved")
    # An arc 0-90 degrees round (5000, 0), r 500; a boundary at x=4600 above the axis.
    arc, edge = await _draw(
        {"type": "arc", "center": _at(o, 5000, 0), "radius": 500, "start_angle": 0, "end_angle": 90, "layer": "LC-AA4"},
        {"type": "line", "start": _at(o, 4600, 0), "end": _at(o, 4600, 1000), "layer": "LC-AA4"},
    )
    out = parse(await edit2d.autocad_trim_extend(
        operation="extend", handles=[arc], edges=[edge], points=[_at(o, 5000, 500)]
    ))
    expect(out.get("done") == 1, f"extending the arc did {out.get('done')}, failed {out.get('failed')}")
    info = await _entity(arc)
    want = math.degrees(math.acos(-0.8))  # where the circle meets x = 4600
    expect(near(info["radius"], 500.0, 1e-6) and near_point(info["center"], _at(o, 5000, 0)),
           f"the arc's circle changed: r {info['radius']}, centre {info['center']}")
    expect(near(info["end_angle_degrees"], want, 1e-3) and near(info["start_angle_degrees"] % 360, 0.0, 1e-3),
           f"the arc now runs {info['start_angle_degrees']} to {info['end_angle_degrees']} degrees, "
           f"not 0 to {want:.3f}")
    return (f"the three short lines end on the main at y=1000, the main unmoved; the arc runs on round "
            f"its circle to {info['end_angle_degrees']:.3f} degrees, where it meets the line")


async def aa5_a_wide_polyline_keeps_its_width_a_tapered_one_is_refused(ctx: Context) -> str:
    o = lc.origin("AA5")
    poly, wall1, wall2 = await _draw(
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 1000, 0), _at(o, 1000, 500)], "width": 20,
         "layer": "LC-AA5"},
        {"type": "line", "start": _at(o, 300, -100), "end": _at(o, 300, 100), "layer": "LC-AA5"},
        {"type": "line", "start": _at(o, 700, -100), "end": _at(o, 700, 100), "layer": "LC-AA5"},
    )
    out = parse(await edit2d.autocad_trim_extend(
        operation="trim", handles=[poly], edges=[wall1, wall2], points=[_at(o, 500, 0)]
    ))
    expect(out.get("done") == 1, f"trim did {out.get('done')}, failed {out.get('failed')}")
    pieces = [poly, *(out["objects"][0].get("new_handles") or [])]
    expect(len(pieces) == 2, f"the trim left {len(pieces)} pieces, not 2")
    widths = [(await lc.read_props(h, ["ConstantWidth"]))["ConstantWidth"] for h in pieces]
    expect(all(near(w, 20.0, 1e-9) for w in widths), f"the pieces' widths are {widths}, not 20")
    taper, edge = await _draw(
        {"type": "polyline", "points": [_at(o, 0, 2000), _at(o, 1000, 2000)], "layer": "LC-AA5"},
        {"type": "line", "start": _at(o, 500, 1900), "end": _at(o, 500, 2100), "layer": "LC-AA5"},
    )
    await lc.by_hand_width(taper, 0, 0.0, 20.0)
    before = await _entity(taper)
    out = parse(await edit2d.autocad_trim_extend(
        operation="trim", handles=[taper], edges=[edge], points=[_at(o, 800, 2000)]
    ))
    reasons = " ".join(f.get("reason", "") for f in out.get("failed") or [])
    expect(out.get("done") == 0 and "width changes along it" in reasons,
           f"the tapered polyline was not refused: done {out.get('done')}, failed {reasons[:120]}")
    after = await _entity(taper)
    expect(after.get("vertices") == before.get("vertices"), "the tapered polyline changed although refused")
    return "both pieces keep width 20; the tapered one (0 to 20) is refused 'width changes along it' and unchanged"


async def aa6_a_fillet_is_tangent_and_radius_0_makes_a_corner(ctx: Context) -> str:
    o = lc.origin("AA6")
    first, second = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 900, 0), "layer": "LC-AA6-A"},
        {"type": "line", "start": _at(o, 1000, 100), "end": _at(o, 1000, 1000), "layer": "LC-AA6-B"},
    )
    out = parse(await edit2d.autocad_fillet_chamfer(operation="fillet", handles=[first, second], radius=150))
    expect(out.get("arc"), f"no arc came back: {out}")
    arc = await _entity(out["arc"])
    expect(arc["type"] == "arc" and near(arc["radius"], 150.0, 1e-6), f"the arc has radius {arc.get('radius')}")
    expect(near_point(arc["center"], _at(o, 850, 150), 1e-6), f"the arc's centre is {_rel(o, arc['center'])}, not 850,150")
    expect(arc["layer"] == "LC-AA6-A", f"the arc is on {arc['layer']}, not the first line's layer")
    a, b = await _entity(first), await _entity(second)
    expect(_runs(a, _at(o, 0, 0), _at(o, 850, 0)), f"the first line now runs {_rel(o, a['start'])}-{_rel(o, a['end'])}")
    expect(_runs(b, _at(o, 1000, 150), _at(o, 1000, 1000)),
           f"the second line now runs {_rel(o, b['start'])}-{_rel(o, b['end'])}")
    third, fourth = await _draw(
        {"type": "line", "start": _at(o, 0, 2000), "end": _at(o, 900, 2000), "layer": "LC-AA6-A"},
        {"type": "line", "start": _at(o, 1000, 2100), "end": _at(o, 1000, 3000), "layer": "LC-AA6-B"},
    )
    before = await lc.entity_count()
    sharp = parse(await edit2d.autocad_fillet_chamfer(operation="fillet", handles=[third, fourth], radius=0))
    expect(not sharp.get("arc"), f"radius 0 made an arc: {sharp.get('arc')}")
    c, d = await _entity(third), await _entity(fourth)
    corner = _at(o, 1000, 2000)
    expect(_runs(c, _at(o, 0, 2000), corner) and _runs(d, corner, _at(o, 1000, 3000)),
           "radius 0 did not meet the lines at the corner 1000,2000")
    expect(await lc.entity_count() == before, "radius 0 added an object")
    return ("arc r 150 centred 850,150, tangent at 850,0 and 1000,150, on the first line's layer; radius 0 "
            "met both lines at the corner with no arc. AutoCAD's own FILLET was not compared")


async def aa7_a_chamfer_cuts_where_its_distances_say(ctx: Context) -> str:
    o = lc.origin("AA7")
    found: list[tuple[float, float]] = []
    for y, kwargs in ((0, {"distance": 50, "distance2": 30}), (3000, {"distance": 50, "angle": 30})):
        first, second = await _draw(
            {"type": "line", "start": _at(o, 0, y), "end": _at(o, 1000, y), "layer": "LC-AA7"},
            {"type": "line", "start": _at(o, 1000, y), "end": _at(o, 1000, y + 1000), "layer": "LC-AA7"},
        )
        out = parse(await edit2d.autocad_fillet_chamfer(operation="chamfer", handles=[first, second], **kwargs))
        expect(out.get("chamfer_line"), f"no chamfer line came back: {out}")
        cut = await _entity(out["chamfer_line"])
        corner = _at(o, 1000, y)
        along_first = min(lc.dist(p, corner) for p in _ends(cut) if near(p[1], o[1] + y, 1e-6))
        along_second = min(lc.dist(p, corner) for p in _ends(cut) if near(p[0], o[0] + 1000, 1e-6))
        found.append((along_first, along_second))
    (a1, a2), (b1, b2) = found
    expect(near(a1, 50, 1e-6) and near(a2, 30, 1e-6), f"distances 50/30 cut {a1:.4f} and {a2:.4f} back")
    want = 50 * math.tan(math.radians(30))
    expect(near(b1, 50, 1e-6) and near(b2, want, 1e-3), f"distance 50 angle 30 cut {b1:.4f} and {b2:.4f}, not 50 and {want:.2f}")
    return (f"50/30 cut 50.000 and 30.000 back from the corner; 50 at 30 degrees cut 50.000 and {b2:.2f}. "
            "AutoCAD's CHAMFER Angle was not compared")


async def aa8_a_polyline_filleted_all_round_has_the_right_area(ctx: Context) -> str:
    o = lc.origin("AA8")
    (rect,) = await _draw({"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 1000, 500), "layer": "LC-AA8"})
    out = parse(await edit2d.autocad_fillet_chamfer(operation="fillet", handles=[rect], radius=50))
    expect(len(out.get("corners_done") or []) == 4 and not out.get("skipped"),
           f"corners done {out.get('corners_done')}, skipped {out.get('skipped')}")
    info = parse(await geometry_tools.autocad_polyline_info(handle=rect))
    want = 500000 - (4 - math.pi) * 50**2
    expect(info.get("vertex_count") == 8, f"the polyline has {info.get('vertex_count')} vertices, not 8")
    expect(near(info.get("area"), want, 0.01), f"its area is {info.get('area')}, not {want:.2f}")
    return f"one polyline, 8 vertices, area {info['area']:.2f} = 500000 - (4 - pi) x 50^2"


async def aa9_a_line_breaks_at_a_point_and_between_two(ctx: Context) -> str:
    o = lc.origin("AA9")
    at_point, between = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AA9"},
        {"type": "line", "start": _at(o, 0, 1000), "end": _at(o, 1000, 1000), "layer": "LC-AA9"},
    )
    out = parse(await edit2d.autocad_break_curve(handle=at_point, point=_at(o, 400, 0)))
    new = out.get("new_handles") or []
    expect(out.get("pieces") == 2 and len(new) == 1, f"breaking at a point gave {out}")
    one, two = await _entity(at_point), await _entity(new[0])
    pieces = {(round(min(p[0] for p in _ends(x)) - o[0], 6), round(max(p[0] for p in _ends(x)) - o[0], 6)) for x in (one, two)}
    expect(pieces == {(0.0, 400.0), (400.0, 1000.0)}, f"the two pieces run {sorted(pieces)}, not 0-400 and 400-1000")
    out = parse(await edit2d.autocad_break_curve(handle=between, point=_at(o, 300, 1000), second_point=_at(o, 600, 1000)))
    new = out.get("new_handles") or []
    expect(len(new) == 1, f"breaking between two points gave {out}")
    one, two = await _entity(between), await _entity(new[0])
    pieces = {(round(min(p[0] for p in _ends(x)) - o[0], 6), round(max(p[0] for p in _ends(x)) - o[0], 6)) for x in (one, two)}
    expect(pieces == {(0.0, 300.0), (600.0, 1000.0)}, f"the two pieces run {sorted(pieces)}, not 0-300 and 600-1000")
    return ("at a point: two touching lines 0-400 and 400-1000; between two points: 0-300 and 600-1000. "
            "The circle was not tried: it is erased and replaced, so Heron asks you (D-50)")


async def aa11_a_vertex_moves_is_added_and_removed(ctx: Context) -> str:
    o = lc.origin("AA11")
    poly, line = await _draw(
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 1000, 0), _at(o, 1000, 1000), _at(o, 0, 1000)],
         "bulges": [0, 0.4142135624, 0, 0], "layer": "LC-AA11"},
        {"type": "line", "start": _at(o, 0, 2000), "end": _at(o, 1000, 2000), "layer": "LC-AA11"},
    )
    parse(await edit2d.autocad_edit_vertex(handle=poly, operation="move", vertex=2, displacement=[0, -200]))
    info = parse(await geometry_tools.autocad_polyline_info(handle=poly))
    expect(near_point(info["vertices"][2], _at(o, 1000, 800)), f"vertex 2 is at {_rel(o, info['vertices'][2])}, not 1000,800")
    expect(info["segments"][1]["kind"] == "arc", "the arc next to the moved vertex is no longer an arc")
    added = parse(await edit2d.autocad_edit_vertex(handle=poly, operation="add", vertex=0, to_point=_at(o, 500, 0)))
    expect(added.get("vertex_count") == 5, f"after adding, {added.get('vertex_count')} vertices, not 5")
    info = parse(await geometry_tools.autocad_polyline_info(handle=poly))
    expect(near_point(info["vertices"][1], _at(o, 500, 0)), f"the new vertex is at {_rel(o, info['vertices'][1])}")
    removed = parse(await edit2d.autocad_edit_vertex(handle=poly, operation="remove", vertex=1))
    expect(removed.get("vertex_count") == 4, f"after removing, {removed.get('vertex_count')} vertices, not 4")
    target = _at(o, 1234.5, 2345.6)
    parse(await edit2d.autocad_edit_vertex(handle=line, operation="move", near=_at(o, 1000, 2000), to_point=target))
    end = await _entity(line)
    expect(near_point(end["end"], target, 1e-9) and near_point(end["start"], _at(o, 0, 2000), 1e-9),
           f"the line runs {_rel(o, end['start'])} to {_rel(o, end['end'])}, not to {_rel(o, target)}")
    return ("vertex 2 moved to 1000,800 with its arc kept; a vertex added at 500,0 (5) and removed (4); "
            "the line's end went exactly to 1234.5,2345.6")


async def aa12_stretch_moves_what_is_inside_and_says_what_it_left(ctx: Context) -> str:
    o = lc.origin("AA12")
    rect, door_part, hatch_edge, circle = await _draw(
        {"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 2000, 1000), "layer": "LC-AA12"},
        {"type": "rectangle", "corner1": _at(o, 8000, 0), "corner2": _at(o, 8100, 200), "layer": "LC-AA12"},
        {"type": "rectangle", "corner1": _at(o, 1200, 100), "corner2": _at(o, 2400, 300), "layer": "LC-AA12"},
        {"type": "circle", "center": _at(o, 5000, 5000), "radius": 100, "layer": "LC-AA12"},
    )
    parse(await blocks.autocad_make_block(name="LC-AA12-DOOR", handles=[door_part], base_point=_at(o, 8000, 0),
                                          keep_originals=True))
    door = parse(await draw.autocad_insert_block(block_name="LC-AA12-DOOR", position=_at(o, 1850, 400)))["handle"]
    hatch = parse(await draw.autocad_add_hatch(boundary_handles=[hatch_edge], pattern="ANSI31", associative=False))["handle"]
    hatch_before = await _entity(hatch)
    out = parse(await edit2d.autocad_stretch(
        handles=[rect, door, hatch, circle], corner1=_at(o, 1500, -200), corner2=_at(o, 2600, 1200),
        displacement=[600, 0],
    ))
    reshaped = {r["handle"]: r.get("vertices_moved") for r in out.get("reshaped") or []}
    expect(reshaped.get(rect) == 2, f"the rectangle had {reshaped.get(rect)} vertices moved, not 2")
    expect(door in (out.get("moved_whole") or []), f"the door is not in moved_whole: {out.get('moved_whole')}")
    expect(hatch in [s.get("handle") for s in out.get("skipped") or []], f"the hatch is not in skipped: {out.get('skipped')}")
    expect(circle in (out.get("untouched") or []), f"the circle is not in untouched: {out.get('untouched')}")
    box = (await _entity(rect))["size"]
    expect(near(box["width"], 2600.0, 1e-6) and near(box["height"], 1000.0, 1e-6),
           f"the rectangle is {box['width']} x {box['height']}, not 2600 x 1000")
    moved = await _entity(door)
    expect(near_point(moved["insertion_point"], _at(o, 2450, 400)), f"the door is at {_rel(o, moved['insertion_point'])}, not 2450,400")
    hatch_after = await _entity(hatch)
    expect(hatch_after.get("bounding_box") == hatch_before.get("bounding_box"), "the skipped hatch moved")
    return ("the rectangle is 600 longer (2600 x 1000), the door moved whole to 2450,400, the hatch skipped "
            "and unmoved, the circle untouched. Widths per segment were not tried")


async def aa15_match_properties_copies_the_six_and_the_styles(ctx: Context) -> str:
    o = lc.origin("AA15")
    parse(await layers.autocad_create_layer(name="M-PIPE"))
    source, line1, line2 = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "M-PIPE"},
        {"type": "line", "start": _at(o, 0, 500), "end": _at(o, 1000, 500), "layer": "LC-AA15"},
        {"type": "line", "start": _at(o, 0, 1000), "end": _at(o, 1000, 1000), "layer": "LC-AA15"},
    )
    await lc.by_hand_true_colour(source, [200, 100, 50])
    parse(await modify.autocad_modify_entity(handles=[source], lineweight=0.35, transparency=40))
    parse(await settings.autocad_create_styles(text_styles=[{"name": "LC-AA15-NOTE", "font": "romans.shx"}]))
    note, other = await _draw(
        {"type": "text", "position": _at(o, 0, 1500), "text": "NOTE", "height": 50, "layer": "LC-AA15"},
        {"type": "text", "position": _at(o, 0, 1700), "text": "OTHER", "height": 50, "layer": "LC-AA15",
         "style": "LC-AA15-NOTE"},
    )
    style_before = (await _entity(note)).get("style")
    out = parse(await edit2d.autocad_match_properties(source=source, handles=[line1, line2, note], properties=["all"]))
    want = {"Layer": "M-PIPE", "TrueColor": [200, 100, 50], "Lineweight": 35, "EntityTransparency": "40"}
    for handle in (line1, line2, note):
        got = await lc.read_props(handle, list(want))
        wrong = {k: got.get(k) for k, v in want.items() if str(got.get(k)) != str(v)}
        expect(not wrong, f"{handle} did not take {wrong}")
    expect((await _entity(note)).get("style") == style_before, "the text's own text style changed")
    # A line has no text style, so the answer says so: under the source (not_on_source) or the text (skipped).
    listed = "not_on_source" if "text_style" in (out.get("not_on_source") or []) else (
        "skipped" if any(s.get("property") == "text_style" for s in out.get("skipped") or []) else "")
    expect(listed, f"the answer does not say the text style was left: {out}")
    parse(await edit2d.autocad_match_properties(source=other, handles=[note], properties=["text_style"]))
    expect((await _entity(note)).get("style") == "LC-AA15-NOTE", "the text style did not copy when asked")
    return ("both lines and the text took layer M-PIPE, true colour 200,100,50, lineweight 0.35, transparency "
            f"40; the text kept its style (said in {listed}), then took LC-AA15-NOTE when asked. "
            "Dimension styles were not tried")


async def aa16_lineweight_and_transparency_and_a_wrong_weight(ctx: Context) -> str:
    o = lc.origin("AA16")
    (line,) = await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AA16"})
    parse(await modify.autocad_modify_entity(handles=[line], lineweight=0.35, transparency=50))
    got = await lc.read_props(line, ["Lineweight", "EntityTransparency"])
    expect(got["Lineweight"] == 35 and str(got["EntityTransparency"]) == "50", f"the line reads {got}")
    message = refusal(await modify.autocad_modify_entity(handles=[line], lineweight=0.33))
    expect("0.33" in message and "0.35" in message, f"0.33 was refused without the list: {message[:160]}")
    expect((await lc.read_props(line, ["Lineweight"]))["Lineweight"] == 35, "the refused 0.33 still changed it")
    return f"the line reads lineweight 35 (0.35 mm) and transparency 50; 0.33 refused: {message[:90]}"


async def aa17_a_group_is_made_listed_changed_and_ungrouped(ctx: Context) -> str:
    o = lc.origin("AA17")
    a, b, c, d, e = await _draw(
        *({"type": "circle", "center": _at(o, x, 0), "radius": 50, "layer": "LC-AA17"} for x in (0, 200, 400, 600, 800)),
    )
    parse(await edit2d.autocad_group(operation="make", name="PUMP-01", handles=[a, b, c]))
    await lc.by_hand_group([d], "LC-AA17-HAND")
    unnamed = await lc.by_hand_group([e], "*")
    listed = parse(await edit2d.autocad_list_groups())
    groups = {g["name"]: g for g in listed.get("groups") or []}
    expect(groups.get("PUMP-01", {}).get("member_count") == 3, f"PUMP-01 lists {groups.get('PUMP-01')}")
    expect("LC-AA17-HAND" in groups, "the group made by hand is not listed")
    expect(groups.get(unnamed, {}).get("unnamed") is True, f"the unnamed group {unnamed} is not marked unnamed")
    added = parse(await edit2d.autocad_group(operation="add", name="PUMP-01", handles=[d]))
    expect(added.get("members") == 4, f"after adding, {added.get('members')} members")
    gone = parse(await edit2d.autocad_group(operation="remove", name="PUMP-01", handles=[a]))
    expect(gone.get("members") == 3, f"after removing, {gone.get('members')} members")
    out = parse(await edit2d.autocad_group(operation="ungroup", name="PUMP-01"))
    expect(out.get("ungrouped") == ["PUMP-01"] and out.get("objects_kept") == 3, f"ungroup answered {out}")
    left = parse(await edit2d.autocad_list_groups(name="PUMP-01"))
    expect(not left.get("groups"), "PUMP-01 is still listed after ungroup")
    expect(all([await lc.exists(h) for h in (a, b, c, d)]), "an object went with the group")
    return (f"PUMP-01 made with 3, listed with the hand group and the unnamed {unnamed} (marked); add 4, "
            "remove 3, ungroup kept the 3 objects. Ctrl+Z was not tried")


async def aa18_a_locked_layer_is_refused_and_a_dry_run_cuts_nothing(ctx: Context) -> str:
    o = lc.origin("AA18")
    locked, edge, free = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AA18-LOCKED"},
        {"type": "line", "start": _at(o, 500, -100), "end": _at(o, 500, 1100), "layer": "LC-AA18"},
        {"type": "line", "start": _at(o, 0, 1000), "end": _at(o, 1000, 1000), "layer": "LC-AA18"},
    )
    parse(await layers.autocad_set_layer_state(name="LC-AA18-LOCKED", locked=True))
    before = await lc.entity_count()
    out = parse(await edit2d.autocad_trim_extend(operation="trim", handles=[locked], edges=[edge], points=[_at(o, 800, 0)]))
    reason = " ".join(f.get("reason", "") for f in out.get("failed") or [])
    expect(out.get("done") == 0 and "LC-AA18-LOCKED" in reason, f"the locked line was not refused by name: {out}")
    expect(await lc.entity_count() == before, "a copy was made of the locked line")
    raw = await edit2d.autocad_trim_extend(operation="trim", handles=[free], edges=[edge], points=[_at(o, 800, 1000)],
                                           dry_run=True)
    head = lc.first_line(raw)
    out = parse(raw)
    expect(head.startswith("NOTHING CHANGED - a dry run"), f"the dry run's first line is {head!r}")
    expect(near((out.get("objects") or [{}])[0].get("cut_away"), 500.0, 1e-6), f"the dry run said it would cut {out}")
    info = await _entity(free)
    expect(_runs(info, _at(o, 0, 1000), _at(o, 1000, 1000)), "the dry run changed the line")
    await layers.autocad_set_layer_state(name="LC-AA18-LOCKED", locked=False)
    return "the locked line refused naming LC-AA18-LOCKED, no copy; the dry run said it would cut 500 and the line is whole"


async def aa19_a_trim_point_in_a_turned_ucs_cuts_the_part_there(ctx: Context) -> str:
    o = lc.origin("AA19")
    parse(await coordinates.autocad_set_ucs(mode="origin", origin=[o[0], o[1]], rotation=30))
    try:
        made = parse(await batch.autocad_batch_draw(operations=[
            {"type": "line", "start": [0, 0], "end": [1000, 0], "layer": "LC-AA19"},
            {"type": "line", "start": [400, -100], "end": [400, 100], "layer": "LC-AA19"},
        ], coords="ucs"))
        line, wall = made["handles"]
        out = parse(await edit2d.autocad_trim_extend(operation="trim", handles=[line], edges=[wall],
                                                     points=[[200, 0]], coords="ucs"))
        expect(out.get("done") == 1, f"trim did {out.get('done')}, failed {out.get('failed')}")
    finally:
        parse(await coordinates.autocad_set_ucs(mode="world"))
    info = await _entity(line)
    turn = math.radians(30)

    def world(u: float) -> list[float]:
        return [o[0] + u * math.cos(turn), o[1] + u * math.sin(turn)]

    expect(_runs(info, world(400), world(1000)), "the part left is not UCS 400,0 to 1000,0")
    return "on a UCS turned 30 degrees, the point UCS 200,0 cut away UCS 0-400; UCS 400-1000 is left"


EDITS_AA: tuple[Check, ...] = (
    Check("AA1", "AA", "trim cuts back to the wall", aa1_trim_cuts_back_to_the_wall),
    Check("AA2", "AA", "two walls leave two lines that look alike", aa2_two_walls_leave_two_lines_that_look_alike),
    Check("AA4", "AA", "extend reaches the main, an arc runs on", aa4_extend_reaches_the_main_and_an_arc_runs_on),
    Check("AA5", "AA", "a wide polyline keeps its width, a taper is refused",
          aa5_a_wide_polyline_keeps_its_width_a_tapered_one_is_refused),
    Check("AA6", "AA", "a fillet is tangent, radius 0 is a corner", aa6_a_fillet_is_tangent_and_radius_0_makes_a_corner),
    Check("AA7", "AA", "a chamfer cuts where its distances say", aa7_a_chamfer_cuts_where_its_distances_say),
    Check("AA8", "AA", "a filleted polyline has the right area", aa8_a_polyline_filleted_all_round_has_the_right_area),
    Check("AA9", "AA", "a line breaks at a point and between two", aa9_a_line_breaks_at_a_point_and_between_two),
    Check("AA11", "AA", "a vertex moves, is added and removed", aa11_a_vertex_moves_is_added_and_removed),
    Check("AA12", "AA", "stretch moves what is inside, says what it left",
          aa12_stretch_moves_what_is_inside_and_says_what_it_left),
    Check("AA15", "AA", "match properties copies the six and the styles", aa15_match_properties_copies_the_six_and_the_styles),
    Check("AA16", "AA", "lineweight and transparency, a wrong weight refused",
          aa16_lineweight_and_transparency_and_a_wrong_weight),
    Check("AA17", "AA", "a group is made, listed, changed, ungrouped", aa17_a_group_is_made_listed_changed_and_ungrouped),
    Check("AA18", "AA", "a locked layer is refused, a dry run cuts nothing",
          aa18_a_locked_layer_is_refused_and_a_dry_run_cuts_nothing),
    Check("AA19", "AA", "a trim point in a turned UCS cuts the part there",
          aa19_a_trim_point_in_a_turned_ucs_cuts_the_part_there),
)

EYE_AA: dict[str, str] = {
    "AA3": "trimming the circle erases it, so Heron asks you to keep it erased (D-50) and the runner cannot answer",
    "AA10": "join erases the joined pieces, so Heron asks you to keep them erased (D-50)",
    "AA13": "explode erases the block, so Heron asks you to keep it erased (D-50)",
    "AA14": "which object shows in front is seen on screen; no tool reads the draw order back",
    "AA20": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
}


CHECKS: tuple[Check, ...] = EDITS_AA
BY_EYE: dict[str, str] = {**EYE_AA}
