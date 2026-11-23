"""Live checks for Lengthen and a fillet or chamfer between a line and an arc (group BH).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Each row draws its own objects at its own spot (``lc.origin``), then measures what
the tool did: a line's ends, an arc's angles, the distance between two centres, a
polyline's total length. AutoCAD's own LENGTHEN and FILLET are not typed here, so
none of these rows proves Heron matches them (BH10 is the person's comparison).
"""

from __future__ import annotations

import math
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, near_point, parse, refusal

from autocad_mcp.tools import batch, edit2d, geometry_tools, layers, query


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _draw(*operations: dict[str, Any]) -> list[str]:
    """Draw with autocad_batch_draw; the handles, in order."""
    made = parse(await batch.autocad_batch_draw(operations=list(operations)))
    expect(made.get("created") == len(operations), f"drew {made.get('created')} of {len(operations)} test objects")
    return list(made["handles"])


async def _entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


def _runs(info: dict[str, Any], a: list[float], b: list[float], tol: float = 1e-6) -> bool:
    """A line runs from a to b, either way round."""
    s, e = info["start"], info["end"]
    return (near_point(s, a, tol) and near_point(e, b, tol)) or (near_point(s, b, tol) and near_point(e, a, tol))


def _rel(o: tuple[float, float], p: Any) -> str:
    return f"{float(p[0]) - o[0]:.4f},{float(p[1]) - o[1]:.4f}"


# ---------------------------------------------------------------------------
# Group BH - Lengthen; fillet and chamfer between a line and an arc
# ---------------------------------------------------------------------------


async def bh1_a_line_is_lengthened_and_shortened_at_the_end_nearest_the_point(ctx: Context) -> str:
    o = lc.origin("BH1")
    (line,) = await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-BH1"})
    out = parse(await edit2d.autocad_lengthen(handles=[line], mode="delta", value=500, points=[_at(o, 900, 0)]))
    expect(out.get("done") == 1, f"lengthen did {out.get('done')}, failed {out.get('failed')}")
    info = await _entity(line)
    expect(_runs(info, _at(o, 0, 0), _at(o, 1500, 0)), f"the line runs {_rel(o, info['start'])} to {_rel(o, info['end'])}, not 0,0 to 1500,0")
    out = parse(await edit2d.autocad_lengthen(handles=[line], mode="delta", value=-200, points=[_at(o, 100, 0)]))
    expect(out.get("done") == 1, f"shortening did {out.get('done')}, failed {out.get('failed')}")
    info = await _entity(line)
    expect(_runs(info, _at(o, 200, 0), _at(o, 1500, 0)), f"the line runs {_rel(o, info['start'])} to {_rel(o, info['end'])}, not 200,0 to 1500,0")
    expect(info["layer"] == "LC-BH1", f"the line is on {info['layer']}, not LC-BH1")
    return "delta +500 at the end near x=900 made 0 to 1500; delta -200 at the end near x=100 made 200 to 1500; same handle, same layer"


async def bh2_total_and_percent_set_the_length(ctx: Context) -> str:
    o = lc.origin("BH2")
    total, percent = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-BH2"},
        {"type": "line", "start": _at(o, 0, 1000), "end": _at(o, 1000, 1000), "layer": "LC-BH2"},
    )
    out = parse(await edit2d.autocad_lengthen(handles=[total], mode="total", value=2400))
    expect(out.get("done") == 1, f"total did {out.get('done')}, failed {out.get('failed')}")
    out = parse(await edit2d.autocad_lengthen(handles=[percent], mode="percent", value=50, end="start"))
    expect(out.get("done") == 1, f"percent did {out.get('done')}, failed {out.get('failed')}")
    a, b = await _entity(total), await _entity(percent)
    expect(_runs(a, _at(o, 0, 0), _at(o, 2400, 0)), f"total 2400 left the line {_rel(o, a['start'])} to {_rel(o, a['end'])}")
    expect(_runs(b, _at(o, 500, 1000), _at(o, 1000, 1000)), f"50 percent from the start left {_rel(o, b['start'])} to {_rel(o, b['end'])}")
    return "total 2400 made the line 0 to 2400; 50 percent at the start end left 500 to 1000"


async def bh3_an_arc_is_lengthened_round_its_own_circle(ctx: Context) -> str:
    o = lc.origin("BH3")
    (arc,) = await _draw({"type": "arc", "center": _at(o, 0, 0), "radius": 500, "start_angle": 0, "end_angle": 90, "layer": "LC-BH3"})
    out = parse(await edit2d.autocad_lengthen(handles=[arc], mode="delta", value=500 * math.pi / 4))
    expect(out.get("done") == 1, f"lengthen did {out.get('done')}, failed {out.get('failed')}")
    info = await _entity(arc)
    expect(near(info["radius"], 500.0, 1e-6) and near_point(info["center"], _at(o, 0, 0)),
           f"the arc's circle changed: r {info['radius']}, centre {info['center']}")
    expect(near(info["start_angle_degrees"] % 360, 0.0, 1e-3) and near(info["end_angle_degrees"], 135.0, 1e-3),
           f"the arc runs {info['start_angle_degrees']} to {info['end_angle_degrees']} degrees, not 0 to 135")
    out = parse(await edit2d.autocad_lengthen(handles=[arc], mode="percent", value=50, end="start"))
    expect(out.get("done") == 1, f"percent did {out.get('done')}, failed {out.get('failed')}")
    info = await _entity(arc)
    want = 135.0 - 67.5
    expect(near(info["end_angle_degrees"], 135.0, 1e-3) and near(info["start_angle_degrees"], want, 1e-3),
           f"the arc runs {info['start_angle_degrees']} to {info['end_angle_degrees']} degrees, not {want} to 135")
    return "delta r x pi/4 took the arc from 0-90 to 0-135 on the same circle; 50 percent at the start end left 67.5 to 135"


async def bh4_a_polyline_is_cut_back_over_a_corner_and_grown_at_its_start(ctx: Context) -> str:
    o = lc.origin("BH4")
    (poly,) = await _draw({"type": "polyline", "points": [_at(o, 0, 0), _at(o, 1000, 0), _at(o, 1000, 500)], "layer": "LC-BH4"})
    out = parse(await edit2d.autocad_lengthen(handles=[poly], mode="delta", value=-700))
    expect(out.get("done") == 1, f"shortening did {out.get('done')}, failed {out.get('failed')}")
    info = parse(await geometry_tools.autocad_polyline_info(handle=poly))
    expect(near(info.get("total_length"), 800.0, 1e-6) and len(info.get("vertices") or []) == 2,
           f"after cutting 700 back: length {info.get('total_length')}, {len(info.get('vertices') or [])} vertices, not 800 and 2")
    out = parse(await edit2d.autocad_lengthen(handles=[poly], mode="delta", value=200, end="start"))
    expect(out.get("done") == 1, f"lengthening did {out.get('done')}, failed {out.get('failed')}")
    info = parse(await geometry_tools.autocad_polyline_info(handle=poly))
    first = info["vertices"][0]
    expect(near(info.get("total_length"), 1000.0, 1e-6) and near_point(first, _at(o, -200, 0)),
           f"after growing the start by 200: length {info.get('total_length')}, first vertex {_rel(o, first)}, not 1000 and -200,0")
    return "delta -700 cut the polyline back over its corner to 800 long (2 vertices); delta +200 at the start made it 1000 long from -200,0"


async def bh5_a_fillet_between_a_line_and_an_arc_is_tangent_to_both(ctx: Context) -> str:
    o = lc.origin("BH5")
    arc, line = await _draw(
        {"type": "arc", "center": _at(o, 0, 0), "radius": 500, "start_angle": 0, "end_angle": 90, "layer": "LC-BH5-ARC"},
        {"type": "line", "start": _at(o, 100, 300), "end": _at(o, 1500, 300), "layer": "LC-BH5-LINE"},
    )
    out = parse(await edit2d.autocad_fillet_chamfer(operation="fillet", handles=[line, arc], radius=50))
    expect(out.get("arc"), f"no arc came back: {out}")
    new = await _entity(out["arc"])
    expect(near(new["radius"], 50.0, 1e-6), f"the new arc has radius {new.get('radius')}, not 50")
    gap = lc.dist(new["center"], _at(o, 0, 0))
    expect(near(gap, 550.0, 1e-4), f"the new arc's centre is {gap:.4f} from the big arc's centre, not 550 (tangent from outside)")
    expect(near(new["center"][1] - (o[1] + 300), 50.0, 1e-4), f"the new arc's centre is {new['center'][1] - (o[1] + 300):.4f} above the line, not 50")
    expect(new["layer"] == "LC-BH5-LINE", f"the new arc is on {new['layer']}, not the first object's layer")
    now = await _entity(line)
    foot = _at(o, new["center"][0] - o[0], 300)
    expect(_runs(now, foot, _at(o, 1500, 300), 1e-4), f"the line now runs {_rel(o, now['start'])} to {_rel(o, now['end'])}, not from the tangent point {_rel(o, foot)}")
    big = await _entity(arc)
    expect(near(big["radius"], 500.0, 1e-6) and near(big["end_angle_degrees"], 90.0, 1e-3),
           f"the big arc changed: r {big['radius']}, end {big['end_angle_degrees']}")
    return (f"r 50 arc centred {_rel(o, new['center'])}: 550 from the big arc's centre, 50 above the line; the line now starts at "
            f"its tangent point, the big arc still ends at 90 degrees. AutoCAD's own FILLET was not compared")


async def bh6_a_fillet_between_two_arcs_is_tangent_to_both(ctx: Context) -> str:
    o = lc.origin("BH6")
    left, right = await _draw(
        {"type": "arc", "center": _at(o, 0, 0), "radius": 500, "start_angle": 0, "end_angle": 90, "layer": "LC-BH6"},
        {"type": "arc", "center": _at(o, 800, 0), "radius": 500, "start_angle": 90, "end_angle": 180, "layer": "LC-BH6"},
    )
    out = parse(await edit2d.autocad_fillet_chamfer(operation="fillet", handles=[left, right], radius=50))
    expect(out.get("arc"), f"no arc came back: {out}")
    new = await _entity(out["arc"])
    for name, centre in (("first", _at(o, 0, 0)), ("second", _at(o, 800, 0))):
        gap = lc.dist(new["center"], centre)
        expect(near(gap, 550.0, 1e-4), f"the new arc's centre is {gap:.4f} from the {name} arc's centre, not 550")
    expect(near(new["radius"], 50.0, 1e-6), f"the new arc has radius {new.get('radius')}, not 50")
    return f"r 50 arc centred {_rel(o, new['center'])}, 550 from both centres (tangent from outside to both)"


async def bh7_a_fillet_between_the_ends_of_two_polylines_keeps_both_whole(ctx: Context) -> str:
    o = lc.origin("BH7")
    first, second = await _draw(
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 1000, 0), _at(o, 1000, 300)], "layer": "LC-BH7"},
        {"type": "polyline", "points": [_at(o, 1500, 900), _at(o, 1500, 600), _at(o, 1300, 600)], "layer": "LC-BH7"},
    )
    before = await lc.entity_count()
    out = parse(await edit2d.autocad_fillet_chamfer(operation="fillet", handles=[first, second], radius=100))
    expect(out.get("arc") and out.get("ends") == ["end", "end"], f"the fillet answered {out}")
    a, b = await _entity(first), await _entity(second)
    expect(len(a["vertices"]) == 3 and len(b["vertices"]) == 3, f"a polyline lost or gained a vertex: {len(a['vertices'])}, {len(b['vertices'])}")
    expect(near_point(a["vertices"][-1][:2], _at(o, 1000, 500), 1e-4), f"the first polyline now ends {_rel(o, a['vertices'][-1])}, not 1000,500")
    expect(near_point(b["vertices"][-1][:2], _at(o, 1100, 600), 1e-4), f"the second polyline now ends {_rel(o, b['vertices'][-1])}, not 1100,600")
    new = await _entity(out["arc"])
    expect(near(new["radius"], 100.0, 1e-6) and near_point(new["center"], _at(o, 1100, 500), 1e-4),
           f"the new arc is r {new.get('radius')} centred {_rel(o, new['center'])}, not r 100 at 1100,500")
    expect(await lc.entity_count() == before + 1, "the fillet added more than the one arc")
    return "each polyline kept its 3 vertices and was trimmed or extended at its end (to 1000,500 and 1100,600); one r 100 arc centred 1100,500 was added"


async def bh8_a_chamfer_to_an_arc_is_measured_along_the_arc(ctx: Context) -> str:
    o = lc.origin("BH8")
    arc, line = await _draw(
        {"type": "arc", "center": _at(o, 0, 0), "radius": 500, "start_angle": 0, "end_angle": 90, "layer": "LC-BH8"},
        {"type": "line", "start": _at(o, 100, 300), "end": _at(o, 1500, 300), "layer": "LC-BH8"},
    )
    out = parse(await edit2d.autocad_fillet_chamfer(operation="chamfer", handles=[line, arc], distance=40, distance2=40))
    expect(out.get("chamfer_line"), f"no chamfer line came back: {out}")
    cut = await _entity(out["chamfer_line"])
    ends = [cut["start"], cut["end"]]
    on_line = [p for p in ends if near(p[1], o[1] + 300, 1e-4)]
    on_arc = [p for p in ends if near(lc.dist(p, _at(o, 0, 0)), 500.0, 1e-4)]
    expect(len(on_line) == 1 and len(on_arc) == 1, f"the chamfer line runs {_rel(o, ends[0])} to {_rel(o, ends[1])}: one end should be on the line, one on the arc")
    expect(near(on_line[0][0] - (o[0] + 400), 40.0, 1e-4), f"the chamfer meets the line {on_line[0][0] - (o[0] + 400):.4f} from the corner, not 40")
    turned = math.degrees(math.atan2(on_arc[0][1] - o[1], on_arc[0][0] - o[0])) - math.degrees(math.atan2(300, 400))
    want = math.degrees(40 / 500)
    expect(near(turned, want, 1e-3), f"the chamfer meets the arc {turned:.4f} degrees past the corner, not {want:.4f} (40 along it)")
    return f"chamfer 40 / 40: the line end 40 along the line from the corner, the arc end {turned:.3f} degrees (40 along the arc) past it. AutoCAD's CHAMFER takes no arcs, so there is nothing to compare"


async def bh9_what_cannot_be_done_is_refused_and_nothing_changes(ctx: Context) -> str:
    o = lc.origin("BH9")
    closed, circle, line, locked, other = await _draw(
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 400, 0), _at(o, 400, 300)], "closed": True, "layer": "LC-BH9"},
        {"type": "circle", "center": _at(o, 1000, 0), "radius": 100, "layer": "LC-BH9"},
        {"type": "line", "start": _at(o, 0, 1000), "end": _at(o, 400, 1000), "layer": "LC-BH9"},
        {"type": "line", "start": _at(o, 0, 2000), "end": _at(o, 400, 2000), "layer": "LC-BH9-LOCKED"},
        {"type": "line", "start": _at(o, 100, 1500), "end": _at(o, 100, 1800), "layer": "LC-BH9"},
    )
    before = await lc.entity_count()
    reasons: dict[str, str] = {}
    for name, handle, kwargs in (
        ("closed", closed, {"mode": "delta", "value": 50}),
        ("circle", circle, {"mode": "delta", "value": 50}),
        ("vanish", line, {"mode": "delta", "value": -400}),
    ):
        out = parse(await edit2d.autocad_lengthen(handles=[handle], **kwargs))
        reasons[name] = " ".join(f.get("reason", "") for f in out.get("failed") or [])
        expect(out.get("done") == 0 and reasons[name], f"lengthen of the {name} case was not refused: {out}")
    expect("closed" in reasons["closed"].lower(), f"the closed polyline's reason is {reasons['closed']!r}")
    expect("vanish" in reasons["vanish"].lower(), f"the vanishing change's reason is {reasons['vanish']!r}")
    info = await _entity(line)
    expect(_runs(info, _at(o, 0, 1000), _at(o, 400, 1000)), "a refused lengthen changed the line")
    parse(await layers.autocad_set_layer_state(name="LC-BH9-LOCKED", locked=True))
    try:
        out = parse(await edit2d.autocad_lengthen(handles=[locked], mode="delta", value=100))
        reason = " ".join(f.get("reason", "") for f in out.get("failed") or [])
        expect(out.get("done") == 0 and "LC-BH9-LOCKED" in reason, f"the locked line was not refused by name: {out}")
    finally:
        await layers.autocad_set_layer_state(name="LC-BH9-LOCKED", locked=False)
    text = refusal(await edit2d.autocad_fillet_chamfer(operation="fillet", handles=[circle, other], radius=20))
    expect("two lines" in text, f"a circle in a fillet was not refused as expected: {text[:120]}")
    expect(await lc.entity_count() == before, "a refused call added or erased an object")
    return "closed polyline, circle and a cut that would leave nothing refused with their reasons; a locked line refused naming its layer; a circle in a fillet refused; nothing changed"


CHECKS: tuple[Check, ...] = (
    Check("BH1", "BH", "a line is lengthened and shortened at the end near the point",
          bh1_a_line_is_lengthened_and_shortened_at_the_end_nearest_the_point),
    Check("BH2", "BH", "total and percent set the length", bh2_total_and_percent_set_the_length),
    Check("BH3", "BH", "an arc is lengthened round its own circle", bh3_an_arc_is_lengthened_round_its_own_circle),
    Check("BH4", "BH", "a polyline is cut back over a corner and grown at its start",
          bh4_a_polyline_is_cut_back_over_a_corner_and_grown_at_its_start),
    Check("BH5", "BH", "a fillet between a line and an arc is tangent to both",
          bh5_a_fillet_between_a_line_and_an_arc_is_tangent_to_both),
    Check("BH6", "BH", "a fillet between two arcs is tangent to both", bh6_a_fillet_between_two_arcs_is_tangent_to_both),
    Check("BH7", "BH", "a fillet between two polyline ends keeps both whole",
          bh7_a_fillet_between_the_ends_of_two_polylines_keeps_both_whole),
    Check("BH8", "BH", "a chamfer to an arc is measured along the arc", bh8_a_chamfer_to_an_arc_is_measured_along_the_arc),
    Check("BH9", "BH", "what cannot be done is refused and nothing changes",
          bh9_what_cannot_be_done_is_refused_and_nothing_changes),
)

BY_EYE: dict[str, str] = {
    "BH10": "the comparison is AutoCAD's own LENGTHEN and FILLET typed by a person on the same objects; the runner types neither",
    "BH11": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
}
