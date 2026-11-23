"""Live checks for Overkill, boundary, eTransmit, underlays and clips (group AD).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Overkill is only listed here (its confirm step erases, so Heron asks, D-50),
except its polyline tidy (AD13), whose confirm only rebuilds a polyline;
the underlay and clip rows need files and an eye, and the big-plan rows need
the plan that hung -BOUNDARY, so those are left to a person.
"""

from __future__ import annotations

import live_common as lc
from live_common import Check, Context, expect, near, parse, refusal

from autocad_mcp.tools import batch, cleanup, document, query


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def ad1_overkill_lists_and_changes_nothing(ctx: Context) -> str:
    o = lc.origin("AD1")
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AD1"},
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AD1"},
        {"type": "line", "start": _at(o, 200, 0), "end": _at(o, 600, 0), "layer": "LC-AD1"},
    ]))
    kept, copy, inside = made["handles"]
    before = await lc.entity_count()
    out = parse(await cleanup.autocad_overkill(handles=[kept, copy, inside]))
    expect(out.get("confirmed") is False and out.get("plan_id"), f"the first call did not just list: {str(out)[:140]}")
    listed = {e["handle"]: e for e in out.get("erase") or []}
    expect(set(listed) == {copy, inside}, f"it lists {sorted(listed)} to erase, not the copy and the short line")
    expect(all(e.get("kept") == kept and e.get("reason") for e in listed.values()), f"not every listed line names {kept} as kept: {listed}")
    for handle in listed:
        line = parse(await query.autocad_get_entity(handle=handle))
        on = all(near(p[1], o[1], 1e-6) and o[0] - 1e-6 <= p[0] <= o[0] + 1000 + 1e-6 for p in (line["start"], line["end"]))
        expect(on, f"{handle}, listed as lying on {kept}, is not on it")
    shown = parse(await document.autocad_show(handles=list(listed)))
    expect(shown.get("shown") == len(listed), f"autocad_show answered {shown}")
    expect(await lc.entity_count() == before, "the listing changed the drawing")
    reasons = "; ".join(f"{h}: {e['reason']}" for h, e in listed.items())
    return (f"listed the copy and the short line, both kept on {kept} ({reasons}); both lie on it and autocad_show found "
            "them; the drawing is unchanged. On runner-made lines, not an architect's Revit export")


async def ad8_a_room_round_a_column_has_its_net_area(ctx: Context) -> str:
    o = lc.origin("AD8")
    parse(await batch.autocad_batch_draw(operations=[
        {"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 4000, 3000), "layer": "LC-AD8"},
        {"type": "rectangle", "corner1": _at(o, 1800, 1300), "corner2": _at(o, 2200, 1700), "layer": "LC-AD8"},
    ]))
    window = [_at(o, -500, -500), _at(o, 4500, 3500)]
    line = parse(await cleanup.autocad_trace_boundary(point_inside=_at(o, 500, 500), window=window, islands=True,
                                                      layer="LC-AD8-ROOM"))
    want_net = 4000 * 3000 - 400 * 400
    expect(near(line.get("area"), 4000 * 3000, 0.5), f"the outline's area is {line.get('area')}, not 12,000,000")
    expect(len(line.get("islands") or []) == 1 and near(line["islands"][0].get("area"), 160000, 0.5),
           f"the islands are {line.get('islands')}, not one column of 160,000")
    expect(near(line.get("net_area"), want_net, 0.5), f"net_area is {line.get('net_area')}, not {want_net:,}")
    region = parse(await cleanup.autocad_trace_boundary(point_inside=_at(o, 500, 500), window=window, islands=True,
                                                        make="region", layer="LC-AD8-ROOM"))
    got = parse(await query.autocad_get_entity(handle=region["handle"]))
    expect(got.get("type") == "region" and near(got.get("area"), want_net, 0.5),
           f"the region is a {got.get('type')} of area {got.get('area')}, not the net {want_net:,}")
    return (f"outline 12,000,000, one island 160,000, net_area {line['net_area']:,.0f}; the region read back has the "
            "hole, area = net_area")


async def ad11_etransmit_refuses_unsaved_and_lists_without_writing(ctx: Context) -> str:
    await lc.new_drawing(ctx)
    said = refusal(await cleanup.autocad_etransmit())
    expect("never been saved" in said and "Save it first" in said, f"the unsaved drawing was refused for another reason: {said[:140]}")
    await lc.activate(ctx)
    path = await lc.save_scratch(ctx)
    before = lc.files_in(path.parent)
    out = parse(await cleanup.autocad_etransmit(list_only=True))
    expect(any(p.get("kind") == "drawing" or str(p.get("name", "")).lower().endswith(".dwg") for p in out.get("packed") or []),
           f"the list does not hold the drawing itself: {str(out.get('packed'))[:140]}")
    expect(not out.get("written"), f"list_only wrote {out.get('written')}")
    expect(lc.files_in(path.parent) == before, "a file appeared next to the drawing")
    return ("unsaved: refused, 'Save it first'; list_only: the list (the drawing in it), nothing written. "
            "The Publish-off refusal was not tried: it needs Publish off, this row Publish on")


async def ad13_overkill_rebuilds_a_polyline_going_back_over_itself(ctx: Context) -> str:
    o = lc.origin("AD13")
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "polyline", "points": [_at(o, 0, 500), _at(o, 0, 0), _at(o, 1000, 0), _at(o, 400, 0)], "layer": "LC-AD13"},
    ]))
    (handle,) = made["handles"]
    listed = parse(await cleanup.autocad_overkill(handles=[handle], tidy_polylines=True))
    rows = listed.get("rebuild") or []
    expect(listed.get("confirmed") is False and len(rows) == 1 and rows[0].get("handle") == handle,
           f"the dry run did not list {handle} to rebuild: {str(listed)[:160]}")
    going = [g.get("segment") for g in rows[0].get("segments_going") or []]
    expect(going == [2], f"it lists segments {going} going, not segment 2 (the tail going back)")
    before = parse(await query.autocad_get_entity(handle=handle))
    expect(before.get("vertex_count") == 4, f"the dry run changed the polyline: {before.get('vertex_count')} vertices")
    done = parse(await cleanup.autocad_overkill(handles=[handle], tidy_polylines=True, confirm=True,
                                                plan_id=listed["plan_id"]))
    expect(done.get("confirmed") is True and not done.get("erase_count"), f"the confirm answered {str(done)[:160]}")
    after = parse(await query.autocad_get_entity(handle=handle))
    want = [_at(o, 0, 500), _at(o, 0, 0), _at(o, 1000, 0)]
    got = after.get("vertices") or []
    same = len(got) == 3 and all(near(p[0], q[0], 1e-6) and near(p[1], q[1], 1e-6) for p, q in zip(got, want, strict=False))
    expect(same, f"after the confirm {handle} has vertices {got}, not {want}")
    expect(near(after.get("length"), 1500.0, 1e-6), f"its length is {after.get('length')}, not 1500")
    return (f"the dry run listed segment 2 of {handle} going and left it at 4 vertices; the confirm rebuilt the same "
            "handle to 3 vertices, length 1500, nothing erased. Ctrl+Z (one step back) was not tried by the runner")


CHECKS: tuple[Check, ...] = (
    Check("AD1", "AD", "Overkill lists and changes nothing", ad1_overkill_lists_and_changes_nothing),
    Check("AD8", "AD", "a room round a column has its net area", ad8_a_room_round_a_column_has_its_net_area),
    Check("AD11", "AD", "eTransmit refuses unsaved, lists without writing",
          ad11_etransmit_refuses_unsaved_and_lists_without_writing, frozenset({"publish"})),
    Check("AD13", "AD", "Overkill rebuilds a polyline going back over itself",
          ad13_overkill_rebuilds_a_polyline_going_back_over_itself),
)

BY_EYE: dict[str, str] = {
    "AD2": "confirm=true erases the doubled lines, so Heron asks you to keep them erased (D-50)",
    "AD3": "needs a PDF, a DWF and a DGN file, and which sheet shows is seen on screen",
    "AD4": "what shows inside the clip is seen on screen",
    "AD5": "needs XCLIP > Generate polyline typed by hand, and the outline compared by eye",
    "AD6": "where the clip lies on the turned PDF is seen on screen",
    "AD7": "needs the big plan that hung -BOUNDARY, and the time taken on it",
    "AD9": "needs the big plan that hung -BOUNDARY, and AutoCAD finishing after Heron stops waiting",
    "AD10": "the pack is unzipped and opened on another PC",
    "AD12": "needs the 1.7.0 plug-in installed instead of the current one",
}
