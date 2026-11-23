"""The AH live checks judge right: PASS on a good recorded answer, FAIL on a bad one.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py). That proves the judging and the arguments, not AutoCAD;
only a live run does that. The answer keys themselves (each piece's box and
volume) are held against the pure plan in acad/shapes3d.py below.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from live_fakes import Sequence, load, play, seq

from autocad_mcp.acad import shapes3d

mep = load("live_check_mep3d")
lc = load("live_common")


def P(o: tuple[float, float], x: float, y: float, z: float = 0.0) -> list[float]:
    return [o[0] + x, o[1] + y, z]


def status(count: int) -> dict:
    return {"active_drawing": {"name": "Drawing1.dwg", "model_space_entities": count}}


def drawn(*handles: str) -> dict:
    return {"created": len(handles), "failed": 0, "requested": len(handles), "handles": list(handles)}


def box(o, low, high) -> dict:
    return {"min": P(o, *low), "max": P(o, *high)}


def solid(handle: str, o, low, high, volume: float) -> dict:
    b = box(o, low, high)
    return {"handle": handle, "type": "3dsolid", "volume": volume, "bounding_box": b,
            "size": [round(h - lo, 6) for h, lo in zip(b["max"], b["min"], strict=True)]}


def props(table: dict) -> callable:
    return lambda handles: {"count": len(handles), "items": [table[h] for h in handles], "unreadable": []}


def table(entities: dict) -> callable:
    return lambda handle: entities[handle]


def made(shape: str, prefix: str, wanted: tuple, **extra) -> dict:
    """make_shape's answer for a duct run or a spool: a row per piece, handles prefix0..prefix4."""
    pieces = [{"index": i, "part": part, "handle": f"{prefix}{i}"} for i, (part, *_rest) in enumerate(wanted)]
    for row in pieces:
        if row["part"] == "bend":
            row["radius"] = 600.0 if row["index"] == 1 else 400.0
    return {"shape": shape, "created": len(pieces), "pieces": pieces, "handles": [r["handle"] for r in pieces],
            "verified": True, **extra}


def pieces_table(o, prefix: str, wanted: tuple, **changed) -> dict:
    out = {f"{prefix}{i}": solid(f"{prefix}{i}", o, low, high, volume) for i, (_, low, high, volume) in enumerate(wanted)}
    out.update(changed)
    return out


def duct_at(row: str):
    o = lc.origin(row)
    return o, made("duct_run", "D", mep.DUCT_PIECES), pieces_table(o, "D", mep.DUCT_PIECES)


def spool_at(o):
    cuts = [{"index": 1, "cut_length": 1804.55}, {"index": 3, "cut_length": 1304.55}]
    return made("pipe_spool", "S", mep.SPOOL_PIECES, pipe_cut_lengths=cuts), pieces_table(o, "S", mep.SPOOL_PIECES)


# --- the answer keys -------------------------------------------------------------------------------


def test_the_answer_keys_are_the_registers_numbers():
    assert mep.DUCT_PIECES[0][3] == 1_056_000_000
    assert mep.CUTS == pytest.approx((1804.55, 1304.55))
    assert mep.BORE == pytest.approx(102.26)
    assert mep._tile_count(3000, 2400, (600, 600), (600, 600)) == 20


@pytest.mark.parametrize(("shape", "settings", "wanted"), [
    ("duct_run", {"points": [list(p) for p in mep.DUCT_POINTS], "width": 600, "height": 400}, mep.DUCT_PIECES),
    ("pipe_spool", {"points": [list(p) for p in mep.SPOOL_POINTS], **mep.SPOOL_SETTINGS}, mep.SPOOL_PIECES),
])
def test_each_pieces_box_is_where_the_plan_puts_it(shape, settings, wanted):
    """The boxes the checks expect, against the pure plan the tool makes its pieces from (D-94)."""
    plan = shapes3d.build_3d(shape, settings)
    assert [p["part"] for p in plan["pieces"]] == [w[0] for w in wanted]
    for piece, (_, low, high, _) in zip(plan["pieces"], wanted, strict=True):
        got_low, got_high = shapes3d.expected_box(piece)
        size = math.dist(low, high)
        assert max(abs(a - b) for a, b in zip(got_low + got_high, list(low) + list(high), strict=True)) < 0.002 * size


# --- AH1 ---------------------------------------------------------------------------------------------

O1, DUCT1, TABLE1 = duct_at("AH1")
AH1 = {
    "autocad_make_shape": DUCT1,
    "autocad_solid_properties": props(TABLE1),
    "autocad_list_entities": {"total_matching": 5, "by_type": {"3dsolid": 5}, "by_layer": {"M-DUCT": 5}},
    "autocad_set_3d_view": {"named": "sw_iso", "visual_style_found": "Conceptual"},
}
AH1_BAD = {"autocad_solid_properties": props({**TABLE1, "D0": solid("D0", O1, (0, -300, 2800), (4600, 300, 3200),
                                                                    600 * 400 * 4600)})}

# --- AH2 ---------------------------------------------------------------------------------------------

O2 = lc.origin("AH2")
SPOOL2, TABLE2 = spool_at(O2)
JOINED = {"shape": "pipe_spool", "created": 1, "pieces": SPOOL2["pieces"], "handles": ["J"], "joined_into": "J",
          "verified": True}
TABLE2["J"] = solid("J", (O2[0], O2[1] + 5000), (0, -114.5, -114.5), (2114.5, 114.5, 1500),
                    sum(w[3] for w in mep.SPOOL_PIECES))


def flange_faces(o, start_degrees: float) -> dict:
    holes = [{"index": k, "kind": "cylinder", "area": math.pi * 19 * 24,
              "center": [o[0] + 12, o[1] + 95.25 * math.cos(math.radians(start_degrees + 45 * k)),
                         95.25 * math.sin(math.radians(start_degrees + 45 * k))]} for k in range(8)]
    others = [{"index": 8, "kind": "cylinder", "area": math.pi * 102.26 * 24, "center": [o[0] + 12, o[1], 0.0]},
              {"index": 9, "kind": "cylinder", "area": math.pi * 229 * 24, "center": [o[0] + 12, o[1], 0.0]},
              {"index": 10, "kind": "plane", "area": 30000.0, "center": [o[0], o[1], 0.0]}]
    return {"handle": "S0", "faces": holes + others, "edges": []}


AH2 = {
    "autocad_make_shape": seq(SPOOL2, JOINED),
    "autocad_solid_properties": props(TABLE2),
    "autocad_list_solid_faces_and_edges": flange_faces(O2, 22.5),
    "autocad_list_entities": {"total_matching": 1, "by_type": {"3dsolid": 1}, "by_layer": {"LC-AH2-JOINED": 1}},
}

# --- AH3 ---------------------------------------------------------------------------------------------

O3, DUCT3, TABLE3 = duct_at("AH3")
O3S = (O3[0] + 8000, O3[1])
SPOOL3, SPOOL3_TABLE = spool_at(O3S)
DUCT3["pieces"][1]["revolved_the_other_way"] = True
AH3 = {
    "autocad_make_shape": seq(DUCT3, SPOOL3),
    "autocad_solid_properties": props({**TABLE3, **SPOOL3_TABLE}),
}
AH3_BAD = {"autocad_solid_properties": props({**TABLE3, **SPOOL3_TABLE, "D1": solid(
    "D1", O3, (3500, -300, 2800), (4400, 600, 3200), mep.DUCT_PIECES[1][3])})}

# --- AH4 ---------------------------------------------------------------------------------------------

O4 = lc.origin("AH4")
SPOOL4, TABLE4 = spool_at(O4)
GAP = 528.625


def view_box(x0, y0, w, h) -> dict:
    return {"min": [O4[0] + x0, O4[1] + y0, 0.0], "max": [O4[0] + x0 + w, O4[1] + y0 + h, 0.0]}


VIEWS4 = {
    "VF": {"handle": "VF", "type": "block", "layer": "M-SHOP", "block_name": "FLATSHOT-1-FRONT",
           "bounding_box": view_box(4000, 0, 2114.5, 1614.5)},
    "VT": {"handle": "VT", "type": "block", "layer": "M-SHOP", "block_name": "FLATSHOT-1-TOP",
           "bounding_box": view_box(4000, 1614.5 + GAP, 2114.5, 229)},
    "VR": {"handle": "VR", "type": "block", "layer": "M-SHOP", "block_name": "FLATSHOT-1-RIGHT",
           "bounding_box": view_box(4000 + 2114.5 + GAP, 0, 229, 1614.5)},
}
FLAT4 = {"created": True, "handle": "VF", "gap": GAP, "projection": "third", "laid_flat_from": ["plane"],
         "views": [{"view": v, "block": f"FLATSHOT-1-{v.upper()}", "handle": h, "lines": 40}
                   for v, h in (("front", "VF"), ("top", "VT"), ("right", "VR"))]}
AH4 = {
    "autocad_make_shape": SPOOL4,
    "autocad_solid_properties": props(TABLE4),
    "autocad_status": seq(status(10), status(13)),
    "autocad_flatten_views": FLAT4,
    "autocad_list_blocks": {"count": 3, "blocks": [{"name": f"FLATSHOT-1-{v}", "entity_count": 40, "instances": 1}
                                                    for v in ("FRONT", "TOP", "RIGHT")]},
    "autocad_get_entity": table(VIEWS4),
}
AH4_BAD = {"autocad_get_entity": table({**VIEWS4, "VR": {**VIEWS4["VR"], "bounding_box": view_box(
    4000 + 2114.5 + GAP, -114.5, 229, 1614.5)}})}

# --- AH6, AH7, AH8 -----------------------------------------------------------------------------------

O6, DUCT6, _ = duct_at("AH6")
SECTION6 = {"created": True, "handle": "SB", "block": "SECTION-1", "section_plane": "SP", "solids": 5, "cut": 1,
            "lines": 9, "size": [600, 400], "looking": [-1.0, 0.0, 0.0], "right": [0.0, 1.0, 0.0],
            "up": [0.0, 0.0, 1.0], "laid_flat_from": "plane"}


def section_block(o, at, w, h, name="SECTION-1", layer="M-SECT") -> dict:
    return {"handle": "SB", "type": "block", "block_name": name, "layer": layer, "insertion_point": P(o, *at),
            "size": {"width": w, "height": h}}


AH6 = {
    "autocad_make_shape": DUCT6,
    "autocad_section_plane": SECTION6,
    "autocad_get_entity": table({"SP": {"handle": "SP", "type": "AcDbSection"},
                                 "SB": section_block(O6, (8000, 0), 600, 400)}),
}
AH6_BAD = {"autocad_get_entity": table({"SP": {"handle": "SP", "type": "AcDbSection"},
                                        "SB": section_block(O6, (8000, 0), 4500, 3200)})}

O7, DUCT7, _ = duct_at("AH7")
BEND_CUT = math.sqrt(600**2 - 200**2)
SECTION7 = {**SECTION6, "cut": 1, "looking": [0.0, 0.0, -1.0], "right": [1.0, 0.0, 0.0], "up": [0.0, 1.0, 0.0]}
AH7 = {
    "autocad_make_shape": DUCT7,
    "autocad_section_plane": SECTION7,
    "autocad_get_entity": section_block(O7, (0, -6000), 600, BEND_CUT, layer="0"),
}
AH7_BAD = {"autocad_get_entity": section_block(O7, (0, -6000), BEND_CUT, 600, layer="0")}

O8, DUCT8, _ = duct_at("AH8")
PLANES = {"total_matching": 2, "by_type": {"AcDbSection": 2}, "by_layer": {"0": 2}}
AH8 = {
    "autocad_make_shape": DUCT8,
    "autocad_list_entities": seq(PLANES, PLANES, PLANES),
    "autocad_status": seq(status(20), status(20), status(21)),
    "autocad_section_plane": seq(
        "REFUSED - Heron in AutoCAD refused it.\n\nError: The plane neither cuts nor sees any of the 5 solid(s). "
        "Check the points and the side it looks at (look_towards). Nothing was changed.",
        {**SECTION6, "block": "SECTION-2", "section_plane": None},
    ),
    "autocad_get_entity": section_block(O8, (12000, 0), 600, 400, name="SECTION-2", layer="0"),
}
AH8_BAD = {"autocad_list_entities": seq(PLANES, PLANES, {**PLANES, "total_matching": 3})}

# --- AH9 ---------------------------------------------------------------------------------------------

O9 = lc.origin("AH9")
AREA9 = math.pi * 1000 * 2000
AH9 = {
    "autocad_batch_draw": drawn("A1", "A2"),
    "autocad_status": status(30),
    "autocad_loft": seq(
        "Error: Outline A1 is open, so the loft would be a surface, not a solid. Close it, or loft it as a "
        "surface (surface=true). Nothing was changed.",
        {"created": True, "handle": "LS", "sections": 2, "area": AREA9},
    ),
    "autocad_get_entity": {"handle": "LS", "type": "AcDbLoftedSurface", "bounding_box": box(O9, (-1000, 0, 0), (1000, 1000, 2000))},
    "lc.exists": True,
    "autocad_thicken_surface": {"created": True, "handle": "TS", "surface": "LS", "thickness": 3.0},
    "autocad_solid_properties": props({"TS": solid("TS", O9, (-1003, 0, 0), (1003, 1003, 2000), AREA9 * 3 * 1.0015)}),
}
AH9_BAD = {"autocad_solid_properties": props({"TS": solid("TS", O9, (-1006, 0, 0), (1006, 1006, 2000), AREA9 * 6)})}

# --- AH10 --------------------------------------------------------------------------------------------

O10 = lc.origin("AH10")
L_AREA = 3000 * 2400 - 1800 * 1200
ENT10 = {
    "PF": {"handle": "PF", "type": "AcDbPlaneSurface", "bounding_box": box(O10, (0, 0, 2700), (3000, 2000, 2700))},
    "L": {"handle": "L", "type": "polyline", "closed": True, "area": L_AREA,
          "bounding_box": box(O10, (0, 3000, 0), (3000, 5400, 0))},
    "PL": {"handle": "PL", "type": "AcDbPlaneSurface", "bounding_box": box(O10, (0, 3000, 0), (3000, 5400, 0))},
    "NS": {"handle": "NS", "type": "AcDbNurbSurface", "bounding_box": box(O10, (0, 7000, 0), (2000, 9000, 0))},
}
AH10 = {
    "autocad_add_surface": seq(
        {"created": True, "handle": "PF", "handles": ["PF"], "surfaces": 1, "area": 6_000_000.0},
        {"created": True, "handle": "PL", "handles": ["PL"], "surfaces": 1, "area": float(L_AREA)},
        {"created": True, "handle": "NS", "u_curves": 3, "v_curves": 3, "area": 4_000_000.0},
        "Error: Outline 2B0 is open. A planar surface fills a closed outline: close it, or loft open outlines into "
        "a surface. Nothing was changed.",
    ),
    "autocad_get_entity": table(ENT10),
    "autocad_batch_draw": seq(drawn("L", "2B0"), drawn("U1", "U2", "U3", "V1", "V2", "V3")),
    "autocad_status": status(40),
}
AH10_BAD = {"autocad_add_surface": seq(
    {"created": True, "handle": "PF", "handles": ["PF"], "surfaces": 1, "area": 5_000_000.0},
    *AH10["autocad_add_surface"].items[1:],
)}

# --- AH11 --------------------------------------------------------------------------------------------

O11, DUCT11, TABLE11 = duct_at("AH11")
ENT11 = {
    "MB": {"handle": "MB", "type": "AcDbSubDMesh", "bounding_box": box(O11, (-480, -280, 0), (480, 280, 380))},
    "MS": {"handle": "MS", "type": "AcDbSubDMesh", "bounding_box": box(O11, (1700, -300, -300), (2300, 300, 300))},
    "MD": {"handle": "MD", "type": "AcDbSubDMesh", "bounding_box": box(O11, (0, -300, 2800), (4400, 300, 3200))},
}
AH11 = {
    "autocad_add_mesh": seq(
        {"created": True, "handle": "MB", "mesh": "box", "smoothness": 2, "faces": 864, "vertices": 866},
        {"created": True, "handle": "MS", "mesh": "sphere", "smoothness": 0, "faces": 72, "vertices": 62},
        {"created": True, "handle": "MD", "mesh": "from 3D solid", "from": "D0", "faces": 12, "vertices": 8},
    ),
    "autocad_get_entity": table(ENT11),
    "autocad_make_shape": DUCT11,
    "autocad_solid_properties": props(TABLE11),
    "lc.exists": True,
}
AH11_BAD = {"autocad_get_entity": table({**ENT11, "MB": {**ENT11["MB"], "bounding_box": box(
    O11, (-480, -280, -190), (480, 280, 190))}})}

# --- AH13 --------------------------------------------------------------------------------------------

FOLDER = Path("C:/Temp/heron-live-check-x/AH13")
XREF = {"name": "LC-AH13-TILE", "entity_count": 0, "instances": 0, "is_xref": True,
        "path": str(FOLDER / "LC-AH13-TILE.dwg")}
HATCH1 = {"name": "SUPERHATCH-1", "entity_count": 20, "instances": 1, "is_xref": False}
HATCH2 = {"name": "SUPERHATCH-2", "entity_count": 20, "instances": 1, "is_xref": False}
TOO_MANY = (
    "REFUSED - the job failed in the dry run; Heron went back to its UNDO mark, so the drawing is as it was.\n\n"
    "Error: Covering this area takes 26671 tiles; one super hatch places at most 10000. Make the spacing or the "
    "scale bigger, or hatch a smaller area. Nothing was changed."
)
AH13 = {
    "lc.other_drawing": FOLDER / "LC-AH13-TILE.dwg",
    "autocad_batch_draw": seq(drawn("R"), drawn("L")),
    "lc.save_active": None,
    "lc.save_as": "LC-AH13-BIG.dwg",
    "lc.close_drawing": None,
    "lc.activate": None,
    "autocad_super_hatch": seq(
        {"created": True, "handle": "H1", "block": "SUPERHATCH-1", "tile": "LC-AH13-TILE", "tile_kind": "xref",
         "xref_attached": True, "tiles": 20, "spacing": [600, 600]},
        {"created": True, "handle": "H2", "block": "SUPERHATCH-2", "tile": "LC-AH13-TILE", "tile_kind": "xref",
         "tiles": 20, "spacing": [600, 600]},
        TOO_MANY,
    ),
    "autocad_list_blocks": seq(
        {"count": 2, "blocks": [XREF, HATCH1]},
        {"count": 3, "blocks": [XREF, HATCH1, HATCH2]},
        {"count": 3, "blocks": [XREF, HATCH1, HATCH2]},
    ),
}
AH13_BAD = {"autocad_list_blocks": seq(
    {"count": 2, "blocks": [XREF, HATCH1]},
    {"count": 3, "blocks": [XREF, HATCH1, HATCH2]},
    {"count": 4, "blocks": [XREF, HATCH1, HATCH2, {"name": "LC-AH13-BIG", "is_xref": True, "entity_count": 0}]},
)}

# --- AH14 --------------------------------------------------------------------------------------------

O14 = lc.origin("AH14")
WIPE = {"handle": "W", "type": "wipeout", "bounding_box": box(O14, (3500, 0, 0), (3800, 300, 0))}
AH14 = {
    "autocad_batch_draw": seq(drawn("L"), drawn("X1", "X2", "X3", "X4")),
    "autocad_add_wipeout": {"created": True, "handle": "W", "type": "wipeout", "corners": 4},
    "autocad_get_entity": WIPE,
    "autocad_super_hatch": {"created": True, "handle": "H", "block": "SUPERHATCH-3", "tile": "SUPERHATCH-3-TILE",
                            "tile_kind": "wipeout", "tile_block_made": True, "tiles": 20, "spacing": [600, 600]},
    "autocad_list_blocks": {"count": 2, "blocks": [{"name": "SUPERHATCH-3", "entity_count": 20},
                                                    {"name": "SUPERHATCH-3-TILE", "entity_count": 1}]},
    "lc.exists": True,
}
AH14_BAD = {"autocad_get_entity": seq(WIPE, {**WIPE, "bounding_box": box(O14, (0, 0, 0), (300, 300, 0))})}

# --- AH17: hidden lines (D-152) ---------------------------------------------------------------------

O17 = lc.origin("AH17")
SPOOL17, _ = spool_at(O17)
LAYERS_BEFORE = {"count": 1, "layers": [{"name": "0", "linetype": "Continuous"}]}
LAYERS_AFTER = {"count": 2, "layers": [{"name": "0", "linetype": "Continuous"}, {"name": "HIDDEN", "linetype": "HIDDEN"}]}
FRONT17 = {"handle": "VH", "type": "block", "layer": "0", "block_name": "FLATSHOT-2-FRONT",
           "bounding_box": {"min": P(O17, 4000, -3000), "max": P(O17, 4000 + 2114.5, -3000 + 1614.5)}}
FLAT17 = {"created": True, "handle": "VH", "projection": "third", "laid_flat_from": ["plane"], "hidden_layer": "HIDDEN",
          "hidden_linetype": "ByLayer", "hidden_layer_made": True,
          "views": [{"view": "front", "block": "FLATSHOT-2-FRONT", "handle": "VH", "lines": 40, "hidden_lines": 14}]}
AH17 = {
    "autocad_make_shape": SPOOL17,
    "autocad_list_layers": seq(LAYERS_BEFORE, LAYERS_AFTER),
    "autocad_flatten_views": FLAT17,
    "autocad_get_entity": FRONT17,
}
# An older plug-in: no hidden lines, and the server's warning.
AH17_BAD = {"autocad_flatten_views": {**FLAT17, "views": [{**FLAT17["views"][0], "hidden_lines": 0}]}}

# --- AH19, AH20, AH21: jogged section lines (D-152) ---------------------------------------------------


def cubes(prefix: str) -> Sequence:
    return seq(*({"created": True, "handle": f"{prefix}{i}"} for i in (1, 2)))


def jogged_at(row: str, at, size, legs: int, jogs: int):
    o = lc.origin(row)
    out = {"created": True, "handle": "JB", "block": "SECTION-3", "section_plane": "JP", "solids": 2, "cut": 2,
           "lines": 10, "size": list(size), "looking": [0.0, 1.0, 0.0], "right": [1.0, 0.0, 0.0],
           "up": [0.0, 0.0, 1.0], "laid_flat_from": "plane", "legs": legs, "jogs": jogs}
    block = {"handle": "JB", "type": "block", "block_name": "SECTION-3", "layer": "0", "insertion_point": P(o, *at),
             "size": {"width": size[0], "height": size[1]}}
    good = {
        "autocad_add_solid": cubes("C"),
        "autocad_list_entities": seq(PLANES, {**PLANES, "total_matching": 3}),
        "autocad_section_plane": out,
        "autocad_get_entity": block,
    }
    return good, out, block


AH19, OUT19, BLOCK19 = jogged_at("AH19", (0, -4000), mep.OFFSET_SIZE, 3, 1)
# The jog drawn as a strip: the section wider than the two cuts side by side.
AH19_BAD = {"autocad_get_entity": {**BLOCK19, "size": {"width": 4000.0 + 2000.0, "height": 1000.0}}}
AH20, OUT20, BLOCK20 = jogged_at("AH20", (0, -7000), mep.ANGLED_SIZE, 2, 0)
# The angled leg projected, not turned flat: the second cut 500 wide, not 707.1.
AH20_BAD = {"autocad_get_entity": {**BLOCK20, "size": {"width": mep.ANGLED_SIZE[0] - (707.107 - 500), "height": 1000.0}}}
AH21 = {
    "autocad_list_entities": seq(PLANES, PLANES),
    "autocad_status": seq(status(30), status(30)),
    "autocad_section_plane": (
        "REFUSED - Heron in AutoCAD refused it.\n\nError: Leg 3 walks back across the view, so the section would draw "
        "over itself. Make it two sections, or turn that leg so it carries on the way the first goes. Nothing was changed."
    ),
}
# An older plug-in cut a plane through the first three corners instead.
AH21_BAD = {"autocad_section_plane": {**OUT19, "legs": None}}


def test_the_jogged_sizes_are_the_registers_numbers():
    assert mep.OFFSET_SIZE == (4000.0, 1000.0)
    assert mep.ANGLED_SIZE[0] == pytest.approx(4828.43, abs=0.01)


# Each row: the good recording, and what in it goes wrong for the FAIL.
SAMPLES: dict[str, tuple[dict, dict]] = {
    "AH1": (AH1, AH1_BAD),
    "AH2": (AH2, {"autocad_list_solid_faces_and_edges": flange_faces(O2, 0.0)}),
    "AH3": (AH3, AH3_BAD),
    "AH4": (AH4, AH4_BAD),
    "AH6": (AH6, AH6_BAD),
    "AH7": (AH7, AH7_BAD),
    "AH8": (AH8, AH8_BAD),
    "AH9": (AH9, AH9_BAD),
    "AH10": (AH10, AH10_BAD),
    "AH11": (AH11, AH11_BAD),
    "AH13": (AH13, AH13_BAD),
    "AH14": (AH14, AH14_BAD),
    "AH17": (AH17, AH17_BAD),
    "AH19": (AH19, AH19_BAD),
    "AH20": (AH20, AH20_BAD),
    "AH21": (AH21, AH21_BAD),
}

CHECKS = {c.row: c for c in mep.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each AH check needs a good and a bad recording here"


def test_every_ah_row_is_measured_or_left_to_an_eye_once():
    rows = {f"AH{n}" for n in range(1, 22)}
    assert set(CHECKS) | set(mep.BY_EYE) == rows
    assert not set(CHECKS) & set(mep.BY_EYE)


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    good, _ = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], good)
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


def test_the_later_rows_use_the_ah1_duct_once_it_is_made(monkeypatch):
    """With AH1 run, AH6 cuts that duct and makes none of its own."""
    ctx = lc.Context(version="27.0", padlocks={"changes": True})
    ctx.store["AH1"] = {"base": O6, "out": DUCT6, "handles": DUCT6["handles"], "pieces": DUCT6["pieces"]}
    good = {k: v for k, v in AH6.items() if k != "autocad_make_shape"}
    verdict = play(monkeypatch, CHECKS["AH6"], good, ctx=ctx)
    assert verdict.passed, verdict.evidence
    assert not verdict.called("autocad_make_shape")
    assert verdict.called("autocad_section_plane")[0]["handles"] == DUCT6["handles"]


def test_the_refused_xref_hatch_is_only_ever_a_dry_run(monkeypatch):
    """Its refusal detaches the xref it attached: counted as an erase, so Heron would ask (D-50)."""
    verdict = play(monkeypatch, CHECKS["AH13"], AH13)
    calls = verdict.called("autocad_super_hatch")
    assert [c.get("dry_run", False) for c in calls] == [False, False, True]


def test_a_flange_whose_round_faces_come_in_halves_still_passes(monkeypatch):
    """Some kernels split a hole's wall in two: sixteen half walls, their centres a little off the hole's."""
    whole = flange_faces(O2, 22.5)
    halves = []
    for face in whole["faces"]:
        if face["kind"] != "cylinder":
            halves.append(face)
            continue
        for side in (-1, 1):
            centre = list(face["center"])
            centre[1] += side * 3.0
            halves.append({**face, "area": face["area"] / 2, "center": centre})
    verdict = play(monkeypatch, CHECKS["AH2"], {**AH2, "autocad_list_solid_faces_and_edges": {**whole, "faces": halves}})
    assert verdict.passed, verdict.evidence
