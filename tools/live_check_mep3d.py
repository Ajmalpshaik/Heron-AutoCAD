"""Live checks for 3D for MEP (group AH): duct runs, pipe spools, flat views, sections,
surfaces, meshes and the new super hatch tiles (D-94, D-95), and a flat view's hidden lines
and jogged section lines (D-150).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Each row works at its own spot (``lc.origin``) and measures what came back with
another tool: a solid's volume and box (autocad_solid_properties), a block's
place and size (autocad_get_entity), what a block holds (autocad_list_blocks),
how many section planes the model has (autocad_list_entities).

What erases, and so is left to an eye here (D-50): none of the scripted rows
erases an object that was there before it. A duct or spool joined, a flat view's
temporary planes and union, a section plane not kept, a super hatch's measuring
probe: each is made and erased inside the one job, and the plug-in's count
(JobChanges) leaves an object made and erased in the same job out. The one that
does erase is a refused xref super hatch, which takes the xref it attached off
again (a block record erased): AH13 tries it only as a dry run.
"""

from __future__ import annotations

import math
import re
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, parse, refusal

from autocad_mcp.tools import (
    batch,
    drafting,
    layers,
    query,
    sections,
    shapes,
    solid_edits,
    solids,
    superhatch,
    surfaces,
)

# ---------------------------------------------------------------------------
# The shapes the rows share, with what they should measure (D-94)
# ---------------------------------------------------------------------------

DUCT_POINTS = ((0, 0, 3000), (5000, 0, 3000), (5000, 4000, 3000), (5000, 4000, 6000))
DUCT_AREA = 600.0 * 400.0
# Each piece of the AH1 duct run: its part, its box from the run's spot (x, y; z as it is) and its volume.
# The level bend is R600 (the 600 side lies in its plane), the bend up R400; a bend's volume is
# its section times the path of the section's centre (Pappus).
DUCT_PIECES = (
    ("straight", (0, -300, 2800), (4400, 300, 3200), DUCT_AREA * 4400),
    ("bend", (4400, -300, 2800), (5300, 600, 3200), DUCT_AREA * 600 * math.pi / 2),
    ("straight", (4700, 600, 2800), (5300, 3600, 3200), DUCT_AREA * 3000),
    ("bend", (4700, 3600, 2800), (5300, 4200, 3400), DUCT_AREA * 400 * math.pi / 2),
    ("straight", (4700, 3800, 3400), (5300, 4200, 6000), DUCT_AREA * 2600),
)

SPOOL_SETTINGS = {
    "outside_diameter": 114.3, "wall": 6.02, "flange_diameter": 229, "flange_thickness": 24,
    "bolt_count": 8, "pitch_diameter": 190.5, "hole_diameter": 19,
}
SPOOL_POINTS = ((0, 0, 0), (2000, 0, 0), (2000, 0, 1500))
ELBOW_R = 1.5 * 114.3  # 171.45, the default long-radius elbow
BORE = 114.3 - 2 * 6.02  # 102.26
PIPE_AREA = math.pi / 4 * (114.3**2 - BORE**2)
FLANGE_VOLUME = math.pi / 4 * (229**2 - BORE**2) * 24 - 8 * math.pi / 4 * 19**2 * 24
CUTS = (2000 - 24 - ELBOW_R, 1500 - ELBOW_R - 24)  # 1804.55 and 1304.55
SPOOL_PIECES = (
    ("flange", (0, -114.5, -114.5), (24, 114.5, 114.5), FLANGE_VOLUME),
    ("pipe", (24, -57.15, -57.15), (24 + CUTS[0], 57.15, 57.15), PIPE_AREA * CUTS[0]),
    ("elbow", (2000 - ELBOW_R, -57.15, -57.15), (2000 + 57.15, 57.15, ELBOW_R), PIPE_AREA * ELBOW_R * math.pi / 2),
    ("pipe", (2000 - 57.15, -57.15, ELBOW_R), (2000 + 57.15, 57.15, 1476), PIPE_AREA * CUTS[1]),
    ("flange", (2000 - 114.5, -114.5, 1476), (2000 + 114.5, 114.5, 1500), FLANGE_VOLUME),
)

# AH19-AH21: two 1000 cubes, by the centre of their base, and the jogged lines cut through them (D-150).
CUBES = ((500, 500), (3500, 2500))
OFFSET_LINE = ((-500, 500), (2000, 500), (2000, 2500), (4500, 2500))
# The two squares cut side by side as one straight section: from x=0 to 1000 and 3000 to 4000, seen from -500.
OFFSET_SIZE = (4000.0, 1000.0)
ANGLED_LINE = ((-500, 500), (2000, 500), (4500, 3000))
# The 45 degree leg crosses the second cube from (3500, 2000) to (4000, 2500): 707.1 at true size, laid on
# from the end of the 2500 first leg, so the far edge is 2500 + 2121.3 + 707.1 - 500 across from the first cut.
ANGLED_SIZE = (2500 + math.sqrt(2) * 2000 - 500, 1000.0)
WALKS_BACK_LINE = ((0, 0), (1000, 0), (1000, 1000), (0, 1000))

# The L-shaped outline AH13 and AH14 tile: 3000 x 2400 overall.
L_OUTLINE = ((0, 0), (3000, 0), (3000, 1200), (1200, 1200), (1200, 2400), (0, 2400))


def _at(o: tuple[float, float], x: float, y: float, z: float | None = None) -> list[float]:
    return [o[0] + x, o[1] + y] + ([] if z is None else [float(z)])


def _box(o: tuple[float, float], low: Any, high: Any) -> tuple[list[float], list[float]]:
    return _at(o, low[0], low[1], low[2]), _at(o, high[0], high[1], high[2])


def _box_off(box: dict[str, Any] | None, want: tuple[list[float], list[float]]) -> float:
    """The worst corner coordinate of a box read back against the box wanted; inf when there is none."""
    if not box or not box.get("min") or not box.get("max"):
        return math.inf
    got = list(box["min"])[:3] + list(box["max"])[:3]
    return max(abs(float(a) - float(b)) for a, b in zip(got, want[0] + want[1], strict=True))


def _diag(want: tuple[list[float], list[float]]) -> float:
    return math.dist(want[0], want[1])


def _rel(o: tuple[float, float], box: dict[str, Any] | None) -> str:
    if not box:
        return "no box"
    lo, hi = box["min"], box["max"]
    return (f"{lo[0] - o[0]:g},{lo[1] - o[1]:g},{lo[2]:g} to "
            f"{hi[0] - o[0]:g},{hi[1] - o[1]:g},{hi[2]:g}")


def _n(value: Any) -> str:
    """A number as the evidence shows it: whole, with thousands marked; or what came instead."""
    return f"{float(value):,.0f}" if isinstance(value, (int, float)) else str(value)


def _close(got: float | None, want: float, share: float) -> bool:
    return got is not None and abs(float(got) - want) <= share * abs(want)


async def _draw(*operations: dict[str, Any]) -> list[str]:
    """Draw with autocad_batch_draw; the handles, in order."""
    made = parse(await batch.autocad_batch_draw(operations=list(operations)))
    expect(made.get("created") == len(operations), f"drew {made.get('created')} of {len(operations)} test objects")
    return list(made["handles"])


async def _entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


async def _props(handles: list[str]) -> dict[str, dict[str, Any]]:
    """autocad_solid_properties of each handle, by handle."""
    out = parse(await solids.autocad_solid_properties(handles=list(handles)))
    items = {i["handle"]: i for i in out.get("items") or []}
    missing = [h for h in handles if h not in items]
    expect(not missing, f"autocad_solid_properties could not read {missing}: {out.get('unreadable')}")
    return items


async def _blocks() -> dict[str, dict[str, Any]]:
    listed = parse(await layers.autocad_list_blocks(include_unused=True))
    return {b["name"]: b for b in listed.get("blocks") or []}


async def _section_planes() -> int:
    """How many section planes (SECTIONPLANE's object) model space has."""
    listed = parse(await query.autocad_list_entities(entity_type="SECTIONOBJECT", summary_only=True))
    return int(listed.get("total_matching") or 0)


def _check_pieces(o: tuple[float, float], rows: list[dict[str, Any]], props: dict[str, dict[str, Any]],
                  wanted: tuple[Any, ...], what: str) -> None:
    """Each piece is the part it should be, with its volume and (for a straight) its box, read back."""
    parts = [r.get("part") for r in rows]
    expect(parts == [w[0] for w in wanted], f"the {what}'s pieces are {parts}, not {[w[0] for w in wanted]}")
    for row, (part, low, high, volume) in zip(rows, wanted, strict=True):
        item = props[row["handle"]]
        expect(_close(item.get("volume"), volume, 1e-4),
               f"{what} {part} {row['index']} has volume {_n(item.get('volume'))}, not {volume:,.0f}")
        want = _box(o, low, high)
        # A flat-sided straight's box is exact; round the curve of a pipe, a flange or a bend
        # AutoCAD may draw its box a little loose (the tool itself allows 5%).
        tol = 0.01 if part == "straight" else 0.05 * _diag(want)
        expect(_box_off(item.get("bounding_box"), want) <= tol,
               f"{what} {part} {row['index']} fills {_rel(o, item.get('bounding_box'))}, not "
               f"{low[0]:g},{low[1]:g},{low[2]:g} to {high[0]:g},{high[1]:g},{high[2]:g}")


async def _make_duct(o: tuple[float, float], layer: str) -> dict[str, Any]:
    out = parse(await shapes.autocad_make_shape(
        shape="duct_run",
        settings={"points": [_at(o, x, y, z) for x, y, z in DUCT_POINTS], "width": 600, "height": 400},
        layer=layer,
    ))
    handles = list(out.get("handles") or [])
    expect(out.get("created") == 5 and len(handles) == 5, f"the duct run made {out.get('created')} solids, not 5")
    return {"base": o, "out": out, "handles": handles, "pieces": list(out.get("pieces") or [])}


async def _make_spool(o: tuple[float, float], layer: str, join: bool = False) -> dict[str, Any]:
    settings: dict[str, Any] = {"points": [_at(o, x, y, z) for x, y, z in SPOOL_POINTS], **SPOOL_SETTINGS}
    if join:
        settings["join"] = True
    out = parse(await shapes.autocad_make_shape(shape="pipe_spool", settings=settings, layer=layer))
    handles = list(out.get("handles") or [])
    want = 1 if join else 5
    expect(out.get("created") == want and len(handles) == want,
           f"the spool{' (joined)' if join else ''} made {out.get('created')} solids, not {want}")
    return {"base": o, "out": out, "handles": handles, "pieces": list(out.get("pieces") or [])}


async def _duct(ctx: Context, row: str) -> dict[str, Any]:
    """The AH1 duct run, or (AH1 not run or not passed) one made at this row's own spot."""
    return ctx.store.get("AH1") or await _make_duct(lc.origin(row), f"LC-{row}-DUCT")


async def _spool(ctx: Context, row: str, at: tuple[float, float] = (0.0, 0.0)) -> dict[str, Any]:
    """The AH2 spool (not joined), or one made at this row's own spot."""
    if ctx.store.get("AH2"):
        return ctx.store["AH2"]
    o = lc.origin(row)
    return await _make_spool((o[0] + at[0], o[1] + at[1]), f"LC-{row}-SPOOL")


def _walls(faces: list[dict[str, Any]], area: float, count: int) -> tuple[list[dict[str, Any]], bool]:
    """The cylinder faces of one size: whole ones, or (a kernel that splits a round face in two) the halves.

    Also says whether they are halves, whose centres sit up to half a radius off the hole's.
    """
    whole = [f for f in faces if near(f.get("area"), area, 1.0)]
    halves = [f for f in faces if near(f.get("area"), area / 2, 0.5)]
    if len(whole) >= count or len(halves) < 2 * count:
        return whole, False
    return halves, True


def _tile_count(width: float, height: float, step: tuple[float, float], tile: tuple[float, float]) -> int:
    """How many tiles a super hatch lays over an area's box from its lower-left corner (TileGrid.Positions)."""

    def across(size: float, step_: float, tile_: float) -> int:
        low = math.floor(round(-tile_ / step_, 9)) + 1
        high = math.ceil(round(size / step_, 9)) - 1
        return high - low + 1

    return across(width, step[0], tile[0]) * across(height, step[1], tile[1])


async def _cubes(row: str) -> tuple[tuple[float, float], list[str]]:
    """The two 1000 cubes AH19 and AH20 cut, at this row's own spot."""
    o = lc.origin(row)
    handles = []
    for x, y in CUBES:
        made = parse(await solids.autocad_add_solid(shape="box", base=_at(o, x, y), length=1000, width=1000,
                                                    height=1000, layer=f"LC-{row}-BOX"))
        expect(made.get("handle"), f"the cube at {x},{y} was not made: {made}")
        handles.append(made["handle"])
    return o, handles


async def _layers() -> dict[str, dict[str, Any]]:
    return {la["name"].upper(): la for la in parse(await layers.autocad_list_layers()).get("layers") or []}


async def _jogged_section(row: str, line: tuple[tuple[float, float], ...], at: tuple[float, float],
                          legs: int, jogs: int, size: tuple[float, float]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cut the AH19 / AH20 cubes along a jogged line, background off; the answer and the block, checked."""
    o, cubes = await _cubes(row)
    planes = await _section_planes()
    out = parse(await sections.autocad_section_plane(
        points=[_at(o, x, y) for x, y in line], jogged=True, background=False, insert_at=_at(o, *at), handles=cubes,
    ))
    expect(out.get("legs") == legs and out.get("jogs") == jogs,
           f"the line has {out.get('legs')} legs and {out.get('jogs')} jogs, not {legs} and {jogs}"
           + ("" if "legs" in out else " (no legs said: is the plug-in older than jogged lines?)"))
    expect(out.get("cut") == 2, f"it cut {out.get('cut')} of the 2 cubes")
    looking = out.get("looking") or []
    expect(len(looking) == 3 and all(near(a, b, 1e-9) for a, b in zip(looking, (0, 1, 0), strict=True)),
           f"it looks {looking}, not [0, 1, 0] (north, left of the first leg)")
    expect(await _section_planes() == planes + 1, "the section plane was not kept in the model")
    block = await _entity(out["handle"])
    expect(lc.near_point(block.get("insertion_point"), _at(o, *at), 1e-6), f"the section is not at {at[0]:g},{at[1]:g}")
    got = block["size"]
    expect(near(got["width"], size[0], 1.0) and near(got["height"], size[1], 1.0),
           f"the section is {got['width']:.1f} x {got['height']:.1f}, not {size[0]:.1f} x {size[1]:.1f}")
    return out, block


async def _l_outline(o: tuple[float, float], layer: str) -> str:
    (outline,) = await _draw({"type": "polyline", "points": [_at(o, x, y) for x, y in L_OUTLINE], "closed": True,
                              "layer": layer})
    return outline


# ---------------------------------------------------------------------------
# Group AH - 3D for MEP
# ---------------------------------------------------------------------------


async def ah1_a_duct_run_is_five_solids_end_to_end(ctx: Context) -> str:
    o = lc.origin("AH1")
    duct = await _make_duct(o, "M-DUCT")
    out = duct["out"]
    expect(out.get("verified") is True and not out.get("warning"),
           f"the duct run says verified {out.get('verified')}, warning {str(out.get('warning'))[:120]}")
    radii = [r.get("radius") for r in duct["pieces"] if r.get("part") == "bend"]
    expect(len(radii) == 2 and near(radii[0], 600, 1e-6) and near(radii[1], 400, 1e-6),
           f"the bends are R{radii}, not R600 (level) and R400 (up)")
    props = await _props(duct["handles"])
    _check_pieces(o, duct["pieces"], props, DUCT_PIECES, "duct")
    on_layer = parse(await query.autocad_list_entities(layer="M-DUCT", summary_only=True))
    solids_there = (on_layer.get("by_type") or {}).get("3dsolid")
    expect(solids_there == 5, f"M-DUCT holds {solids_there} 3D solids, not 5")
    first = props[duct["handles"][0]]
    try:
        view = parse(await solids.autocad_set_3d_view(direction="sw_iso", visual_style="conceptual"))
    finally:
        parse(await solids.autocad_set_3d_view(direction="top", visual_style="2dwireframe"))
    ctx.store["AH1"] = duct
    return (f"5 solids on M-DUCT, verified, no warning: bends R600 level and R400 up; the first straight "
            f"{first['volume']:,.0f} = 600 x 400 x 4400, 600 side level; every piece's volume and the straights' "
            f"boxes read back where the route puts them. SW iso conceptual set (style found "
            f"{view.get('visual_style_found')}), then back to plan, 2D wireframe. The picture and one Ctrl+Z "
            "were not tried")


async def ah2_a_pipe_spool_is_flanged_bored_drilled_and_cut_to_length(ctx: Context) -> str:
    o = lc.origin("AH2")
    spool = await _make_spool(o, "LC-AH2")
    out = spool["out"]
    expect(out.get("verified") is True and not out.get("warning"),
           f"the spool says verified {out.get('verified')}, warning {str(out.get('warning'))[:120]}")
    cuts = [c.get("cut_length") for c in out.get("pipe_cut_lengths") or []]
    expect(len(cuts) == 2 and near(cuts[0], CUTS[0], 0.005) and near(cuts[1], CUTS[1], 0.005),
           f"pipe_cut_lengths are {cuts}, not 1804.55 and 1304.55")
    props = await _props(spool["handles"])
    _check_pieces(o, spool["pieces"], props, SPOOL_PIECES, "spool")
    # Along each piece's axis its box is exact (flat end faces): the pipes measured end to end, as DIST
    # would, and the flange faces on the run's two end points.
    pipe1, pipe2 = (props[spool["pieces"][i]["handle"]]["size"] for i in (1, 3))
    expect(near(pipe1[0], CUTS[0], 0.01) and near(pipe2[2], CUTS[1], 0.01),
           f"the pipes measure {pipe1[0]} and {pipe2[2]} end to end, not their cut lengths {cuts}")
    start, end = (props[spool["pieces"][i]["handle"]]["bounding_box"] for i in (0, 4))
    expect(near(start["min"][0], o[0], 0.01) and near(end["max"][2], 1500, 0.01),
           f"the flange faces are at x {start['min'][0] - o[0]:g} and z {end['max'][2]:g}, not on 0,0,0 and 2000,0,1500")
    # The start flange: bored 102.26, eight 19 holes on the 190.5 circle, none on a centreline.
    flange = parse(await solid_edits.autocad_list_solid_faces_and_edges(handle=spool["pieces"][0]["handle"]))
    walls = [f for f in flange.get("faces") or [] if f.get("kind") == "cylinder"]
    holes, loose = _walls(walls, math.pi * 19 * 24, 8)
    bores, _ = _walls(walls, math.pi * BORE * 24, 1)
    expect(len(holes) == (16 if loose else 8),
           f"the flange has {len(holes) // (2 if loose else 1)} hole walls of 19 x 24, not 8")
    expect(len(bores) in (1, 2), f"the flange has no bore of {BORE:.2f} through it")
    offsets = []
    for hole in holes:
        y, z = hole["center"][1] - o[1], hole["center"][2]
        expect(near(math.hypot(y, z), 190.5 / 2, 6.0 if loose else 1.0),
               f"a hole sits {math.hypot(y, z):.2f} from the axis, not 95.25 (on the 190.5 circle)")
        past = math.degrees(math.atan2(z, y)) % 45
        offsets.append(min(past, 45 - past))  # how far round from the nearest centreline
    expect(all(near(a, 22.5, 5.0 if loose else 3.0) for a in offsets),
           f"the holes are {sorted(round(a, 1) for a in offsets)} degrees from a centreline, not 22.5 (straddling)")
    ctx.store["AH2"] = spool
    joined = await _make_spool((o[0], o[1] + 5000), "LC-AH2-JOINED", join=True)
    one = await _props(joined["handles"])
    total = sum(w[3] for w in SPOOL_PIECES)
    volume = one[joined["handles"][0]].get("volume")
    expect(_close(volume, total, 1e-4), f"the joined spool has volume {_n(volume)}, not the five pieces' {total:,.0f}")
    on_layer = parse(await query.autocad_list_entities(layer="LC-AH2-JOINED", summary_only=True))
    expect(on_layer.get("total_matching") == 1, f"the joined spool is {on_layer.get('total_matching')} objects, not 1")
    return (f"flange, pipe, elbow, pipe, flange: faces on 0,0,0 and 2000,0,1500; pipes cut {cuts[0]:.2f} and "
            f"{cuts[1]:.2f}, measured the same end to end; the flange bored {BORE:.2f} with 8 x 19 holes "
            f"{sum(offsets) / 8:.1f} degrees off the centrelines; every piece's volume read back. With join: one "
            f"solid of {volume:,.0f}, the five together. DIST by hand was not used: the boxes were read instead")


async def ah3_every_bend_continues_the_run(ctx: Context) -> str:
    duct, spool = await _duct(ctx, "AH3"), await _spool(ctx, "AH3", at=(8000.0, 0.0))
    found: list[str] = []
    turned: list[str] = []
    for shape, wanted in ((duct, DUCT_PIECES), (spool, SPOOL_PIECES)):
        o = shape["base"]
        parts = [r.get("part") for r in shape["pieces"]]
        expect(parts == [w[0] for w in wanted], f"the {shape['out'].get('shape')}'s pieces are {parts}")
        bends = [(r, w) for r, w in zip(shape["pieces"], wanted, strict=True) if w[0] in ("bend", "elbow")]
        props = await _props([r["handle"] for r, _ in bends])
        for row, (part, low, high, _) in bends:
            want = _box(o, low, high)
            box = props[row["handle"]].get("bounding_box")
            expect(_box_off(box, want) <= 0.05 * _diag(want),
                   f"{shape['out'].get('shape')} {part} {row['index']} fills {_rel(o, box)}, not "
                   f"{low[0]:g},{low[1]:g},{low[2]:g} to {high[0]:g},{high[1]:g},{high[2]:g}: it folds back")
            name = f"{shape['out'].get('shape')} {part} {row['index']}"
            found.append(name)
            if row.get("revolved_the_other_way"):
                turned.append(name)
    said = (f"revolved_the_other_way on {', '.join(turned)}" if turned
            else "no bend says revolved_the_other_way (AutoCAD turned each the way first asked)")
    return f"{said}; all {len(found)} bends ({', '.join(found)}) fill the box that continues the run"


async def ah4_a_spool_flattened_to_three_lined_up_views(ctx: Context) -> str:
    spool = await _spool(ctx, "AH4")
    o = spool["base"]
    before = await _props(spool["handles"])
    count = await lc.entity_count()
    at = _at(o, 4000, 0)
    out = parse(await sections.autocad_flatten_views(handles=spool["handles"], insert_at=at, layer="M-SHOP"))
    views = {v.get("view"): v for v in out.get("views") or []}
    expect(sorted(views) == ["front", "right", "top"], f"the views made are {sorted(views)}, not front, top and right")
    names = {view: v.get("block", "") for view, v in views.items()}
    match = {view: re.fullmatch(r"FLATSHOT-(\d+)-" + view.upper(), name) for view, name in names.items()}
    expect(all(match.values()) and len({m.group(1) for m in match.values() if m}) == 1,
           f"the blocks are {sorted(names.values())}, not FLATSHOT-n-FRONT, -TOP and -RIGHT")
    listed = await _blocks()
    for name in names.values():
        expect(name in listed and (listed[name].get("entity_count") or 0) > 0,
               f"{name} is not listed with lines in it: {listed.get(name)}")
    boxes = {}
    for view, v in views.items():
        info = await _entity(v["handle"])
        expect(info.get("layer") == "M-SHOP", f"the {view} view is on {info.get('layer')}, not M-SHOP")
        boxes[view] = info["bounding_box"]
    front, top, right = boxes["front"], boxes["top"], boxes["right"]
    width, tall, deep = 2114.5, 1614.5, 229.0  # the spool's size along X, up Z and across Y

    def size(box: dict[str, Any]) -> tuple[float, float]:
        return box["max"][0] - box["min"][0], box["max"][1] - box["min"][1]

    expect(near(front["min"][0], at[0], 0.5) and near(front["min"][1], at[1], 0.5),
           f"the front view's lower-left is {front['min'][0] - o[0]:g},{front['min'][1] - o[1]:g}, not 4000,0")
    for view, want in (("front", (width, tall)), ("top", (width, deep)), ("right", (deep, tall))):
        got = size(boxes[view])
        expect(near(got[0], want[0], 1.0) and near(got[1], want[1], 1.0),
               f"the {view} view is {got[0]:.1f} x {got[1]:.1f}, not {want[0]} x {want[1]}")
    gap = float(out.get("gap") or 0)
    expect(near(top["min"][1] - front["max"][1], gap, 1.0) and near(top["min"][0], front["min"][0], 1.0),
           "the plan is not straight above the front view, one gap up")
    expect(near(right["min"][0] - front["max"][0], gap, 1.0) and near(right["min"][1], front["min"][1], 1.0)
           and near(right["max"][1], front["max"][1], 1.0),
           "the right view is not level with the front view, one gap to its right")
    after = await _props(spool["handles"])
    moved = [h for h in spool["handles"] if after[h].get("volume") != before[h].get("volume")
             or after[h].get("bounding_box") != before[h].get("bounding_box")]
    expect(not moved, f"the spool's solids {moved} changed")
    added = await lc.entity_count() - count
    expect(added == 3, f"model space gained {added} objects, not the 3 views (a temporary plane was left?)")
    return (f"{', '.join(sorted(names.values()))} on M-SHOP; front {width} x {tall} at 4000,0, the plan above it and "
            f"the right view to its right, each one gap ({gap:g}) away and lined up; the spool unchanged and only "
            f"the 3 views added. laid_flat_from {out.get('laid_flat_from')}. Hidden lines and FLATSHOT by hand "
            "were not compared: that is by eye")


async def ah6_a_section_through_the_duct_looks_left(ctx: Context) -> str:
    duct = await _duct(ctx, "AH6")
    o = duct["base"]
    at = _at(o, 8000, 0)
    out = parse(await sections.autocad_section_plane(
        points=[_at(o, 2500, -1000), _at(o, 2500, 5000)], insert_at=at, handles=duct["handles"], layer="M-SECT",
    ))
    expect(re.fullmatch(r"SECTION-\d+", out.get("block", "")), f"the block is called {out.get('block')}, not SECTION-n")
    looking = out.get("looking") or []
    expect(len(looking) == 3 and all(near(a, b, 1e-9) for a, b in zip(looking, (-1, 0, 0), strict=True)),
           f"it looks {looking}, not [-1, 0, 0]")
    expect(out.get("cut") == 1 and out.get("solids") == 5, f"it cut {out.get('cut')} of {out.get('solids')} solids, "
           "not 1 of 5 (only the first straight crosses x=2500)")
    expect(out.get("section_plane"), "no section plane was kept in the model")
    plane = await _entity(out["section_plane"])
    expect(plane.get("type") == "AcDbSection", f"the plane {out.get('section_plane')} is a {plane.get('type')}, not a section plane")
    block = await _entity(out["handle"])
    expect(block.get("block_name") == out["block"] and block.get("layer") == "M-SECT",
           f"the section is {block.get('block_name')} on {block.get('layer')}, not {out['block']} on M-SECT")
    expect(lc.near_point(block.get("insertion_point"), at, 1e-6), "the section is not at 8000,0")
    got = block["size"]
    expect(near(got["width"], 600, 1.0) and near(got["height"], 400, 1.0),
           f"the section is {got['width']:.1f} x {got['height']:.1f}, not the duct's 600 x 400: something on the +X "
           "side (the bend, the riser) was drawn, so it does not look only towards -X")
    return (f"plane {out['section_plane']} kept in the model, {out['block']} at 8000,0 on M-SECT: the duct cut 600 x "
            f"400, looking [-1,0,0]; nothing from the +X side (the bend and riser are behind it). laid_flat_from "
            f"{out.get('laid_flat_from')}. The hatch was not looked at")


async def ah7_a_level_cut_looks_down_with_north_up(ctx: Context) -> str:
    duct = await _duct(ctx, "AH7")
    o = duct["base"]
    at = _at(o, 0, -6000)
    out = parse(await sections.autocad_section_plane(
        points=[_at(o, 0, 0, 3200), _at(o, 1000, 0, 3200), _at(o, 0, 1000, 3200)], insert_at=at,
        handles=duct["handles"], background=False,
    ))
    for key, want in (("looking", (0, 0, -1)), ("up", (0, 1, 0)), ("right", (1, 0, 0))):
        got = out.get(key) or []
        expect(len(got) == 3 and all(near(a, b, 1e-9) for a, b in zip(got, want, strict=True)),
               f"{key} is {got}, not {list(want)}")
    expect((out.get("cut") or 0) >= 1, f"the level cut at 3200 cut {out.get('cut')} solids")
    block = await _entity(out["handle"])
    expect(lc.near_point(block.get("insertion_point"), at, 1e-6), "the section is not at 0,-6000")
    w, h = block["size"]["width"], block["size"]["height"]
    # The bend up is cut at 3200 for sure: 600 along X by 565.69 along Y (radius 400, 200 to 600 round its centre).
    bend = (600.0, math.sqrt(600**2 - 200**2))
    expect(w >= bend[0] - 1 and h >= bend[1] - 1, f"the section is {w:.1f} x {h:.1f}, too small for the bend up's cut")
    if out.get("cut") == 1:
        expect(near(w, bend[0], 1.0) and near(h, bend[1], 1.0),
               f"one solid cut, but the section is {w:.1f} x {h:.1f}, not the bend up's 600 x 565.7 with north up")
    return (f"looking down, north up, right +X; {out.get('cut')} solid(s) cut, the section {w:.1f} x {h:.1f} at "
            f"0,-6000, {out.get('lines')} lines; laid_flat_from {out.get('laid_flat_from')}. 3200 is the top face of "
            "the level legs (2800-3200), so whether they show as cut is AutoCAD's call; the riser starts at 3400, "
            "so the cut there is the bend up. The hatch was not looked at")


async def ah8_a_plane_that_misses_is_refused_and_one_not_kept_leaves_no_plane(ctx: Context) -> str:
    duct = await _duct(ctx, "AH8")
    o = duct["base"]
    planes, count = await _section_planes(), await lc.entity_count()
    # Walking -Y along x=20000 looks left, towards +X: the duct is behind the plane.
    message = refusal(await sections.autocad_section_plane(
        points=[_at(o, 20000, 30000), _at(o, 20000, 20000)], insert_at=_at(o, 12000, 0), handles=duct["handles"],
    ))
    expect("neither cuts nor sees" in message and "Nothing was changed" in message,
           f"the plane that misses was refused without saying so: {message[:160]}")
    expect(await _section_planes() == planes and await lc.entity_count() == count,
           "the refused section left a plane or a block in the model")
    out = parse(await sections.autocad_section_plane(
        points=[_at(o, 2500, -1000), _at(o, 2500, 5000)], insert_at=_at(o, 12000, 0), handles=duct["handles"],
        keep_plane=False,
    ))
    expect(not out.get("section_plane"), f"keep_plane=false still answered a plane {out.get('section_plane')}")
    expect(await _section_planes() == planes, "keep_plane=false left a section plane in the model")
    expect(await lc.entity_count() == count + 1, "keep_plane=false added more than the section block")
    block = await _entity(out["handle"])
    expect(block.get("type") == "block", f"the section is a {block.get('type')}, not a block")
    return (f"far points refused: '{message[:70]}...', no plane and nothing added; keep_plane=false made "
            f"{out.get('block')} only, the model's section planes still {planes}")


async def ah9_a_loft_through_open_arcs_is_a_surface_that_thickens(ctx: Context) -> str:
    o = lc.origin("AH9")
    low, high = await _draw(
        *({"type": "arc", "center": _at(o, 0, 0, z), "radius": 1000, "start_angle": 0, "end_angle": 180,
           "layer": "LC-AH9"} for z in (0, 2000)),
    )
    count = await lc.entity_count()
    message = refusal(await solid_edits.autocad_loft(sections=[low, high]))
    expect("surface=true" in message, f"the loft of open arcs was refused without naming surface=true: {message[:160]}")
    expect(await lc.entity_count() == count, "the refused loft left something")
    out = parse(await solid_edits.autocad_loft(sections=[low, high], surface=True, layer="LC-AH9"))
    want = math.pi * 1000 * 2000  # half a cylinder, r 1000, 2000 high
    expect(_close(out.get("area"), want, 0.005), f"the surface's area is {out.get('area')}, not {want:,.0f}")
    box = (await _entity(out["handle"])).get("bounding_box")
    expect(_box_off(box, _box(o, (-1000, 0, 0), (1000, 1000, 2000))) <= 50.0,
           f"the surface fills {_rel(o, box)}, not -1000,0,0 to 1000,1000,2000")
    expect(await lc.exists(low) and await lc.exists(high), "an arc was not kept")
    solid = parse(await solid_edits.autocad_thicken_surface(handle=out["handle"], thickness=3, layer="LC-AH9"))
    volume = (await _props([solid["handle"]]))[solid["handle"]].get("volume")
    expect(_close(volume, float(out["area"]) * 3, 0.005),
           f"the thickened solid has volume {_n(volume)}, not the area x 3 = {float(out['area']) * 3:,.0f}")
    expect(await lc.exists(out["handle"]), "thickening consumed the surface")
    return (f"open arcs without surface=true refused naming it; the lofted surface {out['area']:,.0f} "
            f"(pi x 1000 x 2000), half a cylinder where it should be, the arcs kept; thickened 3 it is a solid of "
            f"{volume:,.0f}, the surface kept")


async def ah10_planar_and_network_surfaces_and_an_open_outline(ctx: Context) -> str:
    o = lc.origin("AH10")
    flat = parse(await surfaces.autocad_add_surface(kind="planar", corners=[_at(o, 0, 0, 2700), _at(o, 3000, 2000, 2700)],
                                                    layer="LC-AH10"))
    expect(near(flat.get("area"), 6_000_000, 1.0) and flat.get("surfaces") == 1,
           f"the corners made {flat.get('surfaces')} surface(s) of area {flat.get('area')}, not one of 6,000,000")
    box = (await _entity(flat["handle"])).get("bounding_box")
    expect(_box_off(box, _box(o, (0, 0, 2700), (3000, 2000, 2700))) <= 0.01,
           f"the plane surface fills {_rel(o, box)}, not 0,0,2700 to 3000,2000,2700")
    outline, opened = await _draw(
        {"type": "polyline", "points": [_at(o, x, y + 3000) for x, y in L_OUTLINE], "closed": True, "layer": "LC-AH10"},
        {"type": "polyline", "points": [_at(o, 4000, 3000), _at(o, 5000, 3000), _at(o, 5000, 4000)], "layer": "LC-AH10"},
    )
    edge = await _entity(outline)
    filled = parse(await surfaces.autocad_add_surface(kind="planar", outlines=[outline], layer="LC-AH10"))
    expect(filled.get("surfaces") == 1 and near(filled.get("area"), edge.get("area"), 1.0),
           f"the outline made {filled.get('surfaces')} surface(s) of area {filled.get('area')}, "
           f"not one of the outline's {edge.get('area')}")
    over = (await _entity(filled["handle"])).get("bounding_box")
    expect(_box_off(over, (edge["bounding_box"]["min"], edge["bounding_box"]["max"])) <= 0.01,
           f"the surface over the outline fills {_rel(o, over)}, not the outline's box")
    grid = await _draw(
        *({"type": "line", "start": _at(o, 0, 7000 + y), "end": _at(o, 2000, 7000 + y), "layer": "LC-AH10"} for y in (0, 1000, 2000)),
        *({"type": "line", "start": _at(o, x, 7000), "end": _at(o, x, 9000), "layer": "LC-AH10"} for x in (0, 1000, 2000)),
    )
    net = parse(await surfaces.autocad_add_surface(kind="network", u_curves=grid[:3], v_curves=grid[3:], layer="LC-AH10"))
    expect(_close(net.get("area"), 4_000_000, 0.005), f"the network surface's area is {net.get('area')}, not 4,000,000")
    box = (await _entity(net["handle"])).get("bounding_box")
    expect(_box_off(box, _box(o, (0, 7000, 0), (2000, 9000, 0))) <= 1.0,
           f"the network surface fills {_rel(o, box)}, not the six curves' 2000 x 2000")
    count = await lc.entity_count()
    message = refusal(await surfaces.autocad_add_surface(kind="planar", outlines=[opened]))
    expect("is open" in message and opened.upper() in message.upper(), f"the open outline was not refused by name: {message[:160]}")
    expect(await lc.entity_count() == count, "the refused open outline left a surface")
    return (f"3000 x 2000 plane at 2700, area {flat['area']:,.0f}; one surface over the L outline, area "
            f"{filled['area']:,.0f} as the outline's; a network surface through the 3 + 3 lines, area "
            f"{net['area']:,.0f}, over their 2000 x 2000; the open outline refused: {message[:60]}")


async def ah11_mesh_box_sphere_and_a_mesh_of_a_duct_straight(ctx: Context) -> str:
    o = lc.origin("AH11")
    box_mesh = parse(await surfaces.autocad_add_mesh(shape="box", base=_at(o, 0, 0, 0), length=1000, width=600,
                                                     height=400, smoothness=2, layer="LC-AH11"))
    b = (await _entity(box_mesh["handle"]))["bounding_box"]
    centre = [(b["min"][i] + b["max"][i]) / 2 for i in (0, 1)]
    expect(near(b["min"][2], 0.0, 0.01) and lc.near_point(centre, o, 1.0),
           f"the mesh box sits at z {b['min'][2]} round {centre[0] - o[0]:g},{centre[1] - o[1]:g}, not on z=0 round 0,0")
    ball = parse(await surfaces.autocad_add_mesh(shape="sphere", base=_at(o, 2000, 0, 0), radius=300, layer="LC-AH11"))
    s = (await _entity(ball["handle"]))["bounding_box"]
    middle = [(s["min"][i] + s["max"][i]) / 2 for i in range(3)]
    expect(lc.near_point(middle, _at(o, 2000, 0, 0), 1.0),
           f"the mesh sphere is centred {middle[0] - o[0]:g},{middle[1] - o[1]:g},{middle[2]:g}, not 2000,0,0")
    duct = await _duct(ctx, "AH11")
    straight = duct["handles"][0]
    want = _box(duct["base"], DUCT_PIECES[0][1], DUCT_PIECES[0][2])
    copy = parse(await surfaces.autocad_add_mesh(from_handle=straight, layer="LC-AH11"))
    m = (await _entity(copy["handle"])).get("bounding_box")
    expect(_box_off(m, want) <= 1.0, "the mesh of the straight is not where the straight is")
    still = await _props([straight])
    expect(await lc.exists(straight) and _close(still[straight].get("volume"), DUCT_PIECES[0][3], 1e-6),
           "the straight was not kept as it was")
    size = [round(b["max"][i] - b["min"][i], 1) for i in range(3)]
    return (f"box mesh on z=0 round 0,0, {size[0]:g} x {size[1]:g} x {size[2]:g} smoothed, faces {box_mesh.get('faces')} "
            f"vertices {box_mesh.get('vertices')}; sphere centred 2000,0,0, faces {ball.get('faces')} vertices "
            f"{ball.get('vertices')}; the straight's mesh in its place, faces {copy.get('faces')} vertices "
            f"{copy.get('vertices')}, the solid kept ({still[straight]['volume']:,.0f})")


async def ah13_an_xref_tile_is_attached_reused_and_a_refusal_leaves_none(ctx: Context) -> str:
    o = lc.origin("AH13")
    tile_file = await lc.other_drawing(ctx, "AH13", "LC-AH13-TILE.dwg")
    await _draw({"type": "rectangle", "corner1": [0, 0], "corner2": [600, 600], "layer": "LC-AH13-TILE"})
    await lc.save_active(ctx)
    big_file = tile_file.parent / "LC-AH13-BIG.dwg"
    big = await lc.save_as(ctx, big_file)  # the same tile under a second name, never attached
    await lc.close_drawing(ctx, big)
    await lc.activate(ctx)
    outline = await _l_outline(o, "LC-AH13")
    want = _tile_count(3000, 2400, (600, 600), (600, 600))
    first = parse(await superhatch.autocad_super_hatch(boundary=outline, xref=str(tile_file), layer="LC-AH13"))
    expect(first.get("tile_kind") == "xref" and first.get("xref_attached") is True and first.get("tile") == "LC-AH13-TILE",
           f"the .dwg tile answered kind {first.get('tile_kind')}, attached {first.get('xref_attached')}, tile {first.get('tile')}")
    expect(first.get("tiles") == want, f"{first.get('tiles')} tiles, not {want} of 600 x 600 over 3000 x 2400")
    listed = await _blocks()
    xref = listed.get("LC-AH13-TILE") or {}
    expect(xref.get("is_xref") is True and str(xref.get("path", "")).lower().endswith("lc-ah13-tile.dwg"),
           f"LC-AH13-TILE is not listed as an xref of the tile drawing: {xref}")
    expect((listed.get(first.get("block", "")) or {}).get("entity_count") == want,
           f"{first.get('block')} holds {(listed.get(first.get('block', '')) or {}).get('entity_count')} tiles, not {want}")
    again = parse(await superhatch.autocad_super_hatch(boundary=outline, xref="LC-AH13-TILE", layer="LC-AH13"))
    expect(again.get("tile_kind") == "xref" and not again.get("xref_attached") and again.get("tiles") == want,
           f"the second call answered attached {again.get('xref_attached')}, tiles {again.get('tiles')}")
    listed = await _blocks()
    xrefs = [n for n, b in listed.items() if b.get("is_xref") and str(b.get("path", "")).lower().endswith("lc-ah13-tile.dwg")]
    expect(xrefs == ["LC-AH13-TILE"] and again.get("block") != first.get("block"),
           f"the second call did not reuse the one xref: xrefs {xrefs}, blocks {first.get('block')} and {again.get('block')}")
    # Too many tiles from a .dwg not yet attached. Its refusal takes the new xref off again, an erase the
    # runner could not answer, so it is a dry run: refused, and nothing of LC-AH13-BIG left.
    many = _tile_count(3000, 2400, (20, 20), (600, 600))
    raw = await superhatch.autocad_super_hatch(boundary=outline, xref=str(big_file), spacing=[20, 20], dry_run=True)
    message = refusal(raw)
    expect(f"takes {many} tiles" in message and "at most 10000" in message,
           f"the {many}-tile hatch was not refused with the count and the limit: {message[:160]}")
    left = await _blocks()
    expect("LC-AH13-BIG" not in left, f"LC-AH13-BIG is still attached after the refusal: {left.get('LC-AH13-BIG')}")
    return (f"the tile .dwg attached as LC-AH13-TILE (listed as an xref of its file) and tiled {want} times in "
            f"{first.get('block')}; the second call by name reused it ({again.get('block')}, no second xref); "
            f"{many} tiles from LC-AH13-BIG.dwg refused ('{message[:50]}...', first line "
            f"'{lc.first_line(raw)[:40]}') and LC-AH13-BIG not left. That refusal was a dry run, so the undo would "
            "have taken the xref off too: whether Heron itself detaches it was not proven. The clip was not looked at")


async def ah14_a_wipeout_tile_masks_in_a_grid_and_the_original_stays(ctx: Context) -> str:
    o = lc.origin("AH14")
    outline = await _l_outline(o, "LC-AH14")
    await _draw(*({"type": "line", "start": _at(o, -200, y), "end": _at(o, 4200, y), "layer": "LC-AH14"}
                  for y in (100, 700, 1300, 1900)))
    mask = parse(await drafting.autocad_add_wipeout(
        points=[_at(o, 3500, 0), _at(o, 3800, 0), _at(o, 3800, 300), _at(o, 3500, 300)], layer="LC-AH14",
    ))["handle"]
    before = (await _entity(mask)).get("bounding_box")
    out = parse(await superhatch.autocad_super_hatch(boundary=outline, wipeout=mask, spacing=[600, 600], layer="LC-AH14"))
    want = _tile_count(3000, 2400, (600, 600), (300, 300))
    expect(out.get("tile_kind") == "wipeout" and out.get("tile_block_made") is True,
           f"the wipeout tile answered kind {out.get('tile_kind')}, tile block made {out.get('tile_block_made')}")
    expect(out.get("tiles") == want, f"{out.get('tiles')} masks, not {want} at 600 x 600 over 3000 x 2400")
    listed = await _blocks()
    holder, tile = listed.get(out.get("block", "")) or {}, listed.get(out.get("tile", "")) or {}
    expect(holder.get("entity_count") == want and tile.get("entity_count") == 1,
           f"{out.get('block')} holds {holder.get('entity_count')} and {out.get('tile')} holds {tile.get('entity_count')}, "
           f"not {want} and 1")
    after = (await _entity(mask)).get("bounding_box") if await lc.exists(mask) else None
    expect(after is not None and after == before, f"the original wipeout moved or went: {before} then {after}")
    return (f"{want} masks 600 apart in {out.get('block')}, from the tile block {out.get('tile')} (one wipeout); the "
            "original wipeout unchanged. Whether the masks hide the lines, and the clip to the L, was not looked at")


async def ah17_hidden_lines_go_dashed_on_their_own_layer(ctx: Context) -> str:
    spool = await _spool(ctx, "AH17")
    o = spool["base"]
    before = await _layers()
    at = _at(o, 4000, -3000)
    out = parse(await sections.autocad_flatten_views(handles=spool["handles"], views=["front"], insert_at=at,
                                                     hidden_lines=True))
    expect(not out.get("warning"), f"the answer warns: {out.get('warning')}")
    views = out.get("views") or []
    expect(len(views) == 1 and views[0].get("view") == "front", f"the views made are {[v.get('view') for v in views]}")
    front = views[0]
    expect((front.get("hidden_lines") or 0) > 0 and (front.get("lines") or 0) > 0,
           f"the front view has {front.get('lines')} visible and {front.get('hidden_lines')} hidden lines; the bores "
           "should be hidden")
    expect(out.get("hidden_layer") == "HIDDEN", f"the hidden lines are on {out.get('hidden_layer')}, not HIDDEN")
    after = await _layers()
    layer = after.get("HIDDEN") or {}
    if "HIDDEN" in before:
        made = "was there already"
        continuous = str(before["HIDDEN"].get("linetype", "")).upper() == "CONTINUOUS"
        want = "HIDDEN" if continuous else "ByLayer"
        expect(out.get("hidden_linetype") == want,
               f"layer HIDDEN is {before['HIDDEN'].get('linetype')}, so the lines should be {want}, not "
               f"{out.get('hidden_linetype')}")
    else:
        made = "was made"
        expect(out.get("hidden_layer_made") is True, "layer HIDDEN was not there, but the answer does not say it made it")
        expect(str(layer.get("linetype", "")).upper() == "HIDDEN",
               f"the new layer HIDDEN has linetype {layer.get('linetype')}, not HIDDEN")
    info = await _entity(front["handle"])
    box = info["bounding_box"]
    w, h = box["max"][0] - box["min"][0], box["max"][1] - box["min"][1]
    expect(near(w, 2114.5, 1.0) and near(h, 1614.5, 1.0),
           f"the front view is {w:.1f} x {h:.1f}, not AH4's 2114.5 x 1614.5 (a hidden line outside the outline?)")
    return (f"{front.get('block')}: {front.get('lines')} visible and {front.get('hidden_lines')} hidden lines, on layer "
            f"HIDDEN (it {made}, linetype {layer.get('linetype')}; the lines {out.get('hidden_linetype')}), the view "
            f"{w:.1f} x {h:.1f}. Whether they are the bores, dashed, and match FLATSHOT's obscured lines is by eye")


async def ah19_an_offset_section_reads_as_one_straight_section(ctx: Context) -> str:
    out, _ = await _jogged_section("AH19", OFFSET_LINE, (0, -4000), legs=3, jogs=1, size=OFFSET_SIZE)
    return (f"{out.get('block')}: 3 legs, 1 jog, both cubes cut, looking north; {OFFSET_SIZE[0]:g} x "
            f"{OFFSET_SIZE[1]:g} as one straight section. laid_flat_from {out.get('laid_flat_from')}, "
            f"left_out_on_jogs {out.get('left_out_on_jogs', 0)}. The squares 2000 apart and the plane's legs against "
            "SECTIONPLANE by hand are by eye")


async def ah20_an_angled_leg_is_laid_flat_at_true_size(ctx: Context) -> str:
    out, _ = await _jogged_section("AH20", ANGLED_LINE, (0, -7000), legs=2, jogs=0, size=ANGLED_SIZE)
    return (f"{out.get('block')}: 2 legs, no jog, both cubes cut; {ANGLED_SIZE[0]:.1f} x {ANGLED_SIZE[1]:g}, so the "
            f"second cube's cut is at its true 707.1 along the 45 degree leg. laid_flat_from "
            f"{out.get('laid_flat_from')}. With background on: by eye")


async def ah21_a_line_that_walks_back_is_refused(ctx: Context) -> str:
    o = lc.origin("AH21")
    planes, count = await _section_planes(), await lc.entity_count()
    message = refusal(await sections.autocad_section_plane(
        points=[_at(o, x, y) for x, y in WALKS_BACK_LINE], jogged=True, insert_at=_at(o, 0, -9000),
    ))
    expect("walks back" in message and "Nothing was changed" in message,
           f"the line that walks back was refused without saying so: {message[:160]}")
    expect(await _section_planes() == planes and await lc.entity_count() == count,
           "the refused section left a plane or a block in the model")
    return f"refused: '{message[:90]}...'; no plane and nothing added"


CHECKS: tuple[Check, ...] = (
    Check("AH1", "AH", "a duct run is five solids end to end", ah1_a_duct_run_is_five_solids_end_to_end),
    Check("AH2", "AH", "a pipe spool is flanged, bored, drilled and cut",
          ah2_a_pipe_spool_is_flanged_bored_drilled_and_cut_to_length),
    Check("AH3", "AH", "every bend continues the run", ah3_every_bend_continues_the_run),
    Check("AH4", "AH", "a spool flattened to three lined-up views", ah4_a_spool_flattened_to_three_lined_up_views),
    Check("AH6", "AH", "a section through the duct looks left", ah6_a_section_through_the_duct_looks_left),
    Check("AH7", "AH", "a level cut looks down, north up", ah7_a_level_cut_looks_down_with_north_up),
    Check("AH8", "AH", "a plane that misses is refused, one not kept leaves none",
          ah8_a_plane_that_misses_is_refused_and_one_not_kept_leaves_no_plane),
    Check("AH9", "AH", "a loft through open arcs is a surface that thickens",
          ah9_a_loft_through_open_arcs_is_a_surface_that_thickens),
    Check("AH10", "AH", "planar and network surfaces, an open outline refused",
          ah10_planar_and_network_surfaces_and_an_open_outline),
    Check("AH11", "AH", "mesh box, sphere and a mesh of a straight", ah11_mesh_box_sphere_and_a_mesh_of_a_duct_straight),
    Check("AH13", "AH", "an xref tile is attached, reused, a refusal leaves none",
          ah13_an_xref_tile_is_attached_reused_and_a_refusal_leaves_none),
    Check("AH14", "AH", "a wipeout tile masks in a grid, the original stays",
          ah14_a_wipeout_tile_masks_in_a_grid_and_the_original_stays),
    Check("AH17", "AH", "hidden lines go dashed on their own layer", ah17_hidden_lines_go_dashed_on_their_own_layer),
    Check("AH19", "AH", "an offset section reads as one straight section",
          ah19_an_offset_section_reads_as_one_straight_section),
    Check("AH20", "AH", "an angled leg is laid flat at true size", ah20_an_angled_leg_is_laid_flat_at_true_size),
    Check("AH21", "AH", "a section line that walks back is refused", ah21_a_line_that_walks_back_is_refused),
)

BY_EYE: dict[str, str] = {
    "AH5": "whether the back box's lines show through, and the flush line goes with join, is seen on screen",
    "AH12": "whether XCLIP clips the images inside the block is the reason for this row, and it is seen on "
            "screen; it also needs an image file on disk",
    "AH15": "needs Ask to Keep on and Discard pressed each time, which the runner cannot do",
    "AH16": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
    "AH18": "freezing and thawing a layer and seeing the dashes go and come back is seen on screen, and it "
            "needs a layer made by hand with linetype Continuous first",
}
