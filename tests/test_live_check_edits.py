"""The AA and AB live checks judge right: PASS on a good recorded answer, FAIL on a bad one.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py). That proves the judging and the arguments, not AutoCAD;
only a live run does that.
"""

from __future__ import annotations

import math

import pytest
from live_fakes import load, play, seq

edits = load("live_check_edits")
lc = load("live_common")


def P(row: str, x: float, y: float) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y, 0.0]


def drawn(*handles: str) -> dict:
    return {"created": len(handles), "failed": 0, "requested": len(handles), "handles": list(handles)}


def line(handle: str, a: list[float], b: list[float], layer: str = "LC", **extra) -> dict:
    return {"handle": handle, "type": "line", "layer": layer, "start": a, "end": b, **extra}


def table(entities: dict) -> callable:
    return lambda handle: entities[handle]


STATUS = {"active_drawing": {"name": "Drawing1.dwg", "model_space_entities": 12}}

# --- AA -----------------------------------------------------------------------------------------

AA1 = {
    "autocad_batch_draw": drawn("L1", "W1"),
    "autocad_trim_extend": {"operation": "trim", "done": 1, "objects": [{"handle": "L1", "cut_away": 400.0}]},
    "autocad_get_entity": line("L1", P("AA1", 400, 0), P("AA1", 1000, 0), "LC-AA1"),
}

AA2_ENTITIES = {
    "L": line("L", P("AA2", 0, 0), P("AA2", 300, 0), "LC-AA2", color=3, linetype="HIDDEN"),
    "N": line("N", P("AA2", 700, 0), P("AA2", 1000, 0), "LC-AA2", color=3, linetype="HIDDEN"),
}
AA2 = {
    "autocad_batch_draw": drawn("L", "W1", "W2"),
    "autocad_modify_entity": {"modified": 1},
    "autocad_trim_extend": {"operation": "trim", "done": 1, "objects": [{"handle": "L", "new_handles": ["N"]}]},
    "autocad_get_entity": table(AA2_ENTITIES),
    "lc.read_props": {"Lineweight": 35},
}

END = math.degrees(math.acos(-0.8))
AA4_ENTITIES = {
    "M": line("M", P("AA4", 0, 1000), P("AA4", 3000, 1000)),
    **{h: line(h, P("AA4", x, 0), P("AA4", x, 1000)) for h, x in (("S1", 500), ("S2", 1500), ("S3", 2500))},
    "A": {"handle": "A", "type": "arc", "center": P("AA4", 5000, 0), "radius": 500.0,
          "start_angle_degrees": 0.0, "end_angle_degrees": END},
}
AA4 = {
    "autocad_batch_draw": seq(drawn("M", "S1", "S2", "S3"), drawn("A", "E")),
    "autocad_trim_extend": seq({"done": 3, "objects": []}, {"done": 1, "objects": []}),
    "autocad_get_entity": table(AA4_ENTITIES),
}

AA5_TAPER = {"handle": "T", "type": "polyline", "vertices": [P("AA5", 0, 2000)[:2], P("AA5", 1000, 2000)[:2]]}
AA5 = {
    "autocad_batch_draw": seq(drawn("P", "W1", "W2"), drawn("T", "E")),
    "autocad_trim_extend": seq(
        {"done": 1, "objects": [{"handle": "P", "new_handles": ["Q"]}]},
        {"done": 0, "objects": [], "failed": [{"handle": "T", "reason": "T is a polyline whose width changes along it. Heron would lose those widths"}]},
    ),
    "lc.read_props": {"ConstantWidth": 20.0},
    "lc.by_hand_width": None,
    "autocad_get_entity": AA5_TAPER,
}

AA6_ENTITIES = {
    "R": {"handle": "R", "type": "arc", "layer": "LC-AA6-A", "center": P("AA6", 850, 150), "radius": 150.0},
    "A": line("A", P("AA6", 0, 0), P("AA6", 850, 0)),
    "B": line("B", P("AA6", 1000, 150), P("AA6", 1000, 1000)),
    "C": line("C", P("AA6", 0, 2000), P("AA6", 1000, 2000)),
    "D": line("D", P("AA6", 1000, 2000), P("AA6", 1000, 3000)),
}
AA6 = {
    "autocad_batch_draw": seq(drawn("A", "B"), drawn("C", "D")),
    "autocad_fillet_chamfer": seq({"arc": "R", "lines": ["A", "B"]}, {"arc": None, "lines": ["C", "D"]}),
    "autocad_get_entity": table(AA6_ENTITIES),
    "autocad_status": STATUS,
}

AA7_ENTITIES = {
    "X": line("X", P("AA7", 950, 0), P("AA7", 1000, 30)),
    "Y": line("Y", P("AA7", 950, 3000), P("AA7", 1000, 3000 + 50 * math.tan(math.radians(30)))),
}
AA7 = {
    "autocad_batch_draw": seq(drawn("A", "B"), drawn("C", "D")),
    "autocad_fillet_chamfer": seq({"chamfer_line": "X"}, {"chamfer_line": "Y"}),
    "autocad_get_entity": table(AA7_ENTITIES),
}

AA8 = {
    "autocad_batch_draw": drawn("R"),
    "autocad_fillet_chamfer": {"operation": "fillet", "handle": "R", "corners_done": [0, 1, 2, 3], "skipped": [], "vertex_count": 8},
    "autocad_polyline_info": {"vertex_count": 8, "area": 500000 - (4 - math.pi) * 2500},
}

AA9_ENTITIES = {
    "A": line("A", P("AA9", 0, 0), P("AA9", 400, 0)),
    "A2": line("A2", P("AA9", 400, 0), P("AA9", 1000, 0)),
    "B": line("B", P("AA9", 0, 1000), P("AA9", 300, 1000)),
    "B2": line("B2", P("AA9", 600, 1000), P("AA9", 1000, 1000)),
}
AA9 = {
    "autocad_batch_draw": drawn("A", "B"),
    "autocad_break_curve": seq({"pieces": 2, "new_handles": ["A2"]}, {"pieces": 2, "new_handles": ["B2"]}),
    "autocad_get_entity": table(AA9_ENTITIES),
}


def _poly(*vertices: tuple[float, float], arc_at: int = 1) -> dict:
    points = [P("AA11", x, y)[:2] for x, y in vertices]
    segments = [{"index": i, "kind": "arc" if i == arc_at else "line"} for i in range(len(points))]
    return {"vertex_count": len(points), "vertices": points, "segments": segments}


AA11 = {
    "autocad_batch_draw": drawn("P", "L"),
    "autocad_edit_vertex": seq({"vertex_count": 4}, {"vertex_count": 5}, {"vertex_count": 4}, {"vertex_count": 2}),
    "autocad_polyline_info": seq(
        _poly((0, 0), (1000, 0), (1000, 800), (0, 1000)),
        _poly((0, 0), (500, 0), (1000, 0), (1000, 800), (0, 1000), arc_at=2),
    ),
    "autocad_get_entity": line("L", P("AA11", 0, 2000), P("AA11", 1234.5, 2345.6)),
}

AA12_ENTITIES = {
    "H": {"handle": "H", "type": "hatch", "bounding_box": {"min": P("AA12", 1200, 100), "max": P("AA12", 2400, 300)}},
    "R": {"handle": "R", "type": "polyline", "size": {"width": 2600.0, "height": 1000.0}},
    "D": {"handle": "D", "type": "block", "insertion_point": P("AA12", 2450, 400)},
}
AA12 = {
    "autocad_batch_draw": drawn("R", "DP", "HE", "C"),
    "autocad_make_block": {"created": True, "block": "LC-AA12-DOOR", "handle": None},
    "autocad_insert_block": {"created": True, "handle": "D"},
    "autocad_add_hatch": {"created": True, "handle": "H"},
    "autocad_get_entity": table(AA12_ENTITIES),
    "autocad_stretch": {"reshaped": [{"handle": "R", "vertices_moved": 2}], "moved_whole": ["D"], "untouched": ["C"],
                        "skipped": [{"handle": "H", "reason": "a hatch moves only when wholly inside"}],
                        "displacement": [600, 0]},
}

AA15_WANT = {"Layer": "M-PIPE", "TrueColor": [200, 100, 50], "Lineweight": 35, "EntityTransparency": "40"}
AA15 = {
    "autocad_create_layer": {"name": "M-PIPE", "created": True},
    "autocad_batch_draw": seq(drawn("S", "L1", "L2"), drawn("N", "OT")),
    "lc.by_hand_true_colour": None,
    "autocad_modify_entity": {"modified": 1},
    "autocad_create_styles": {"text_styles": [{"name": "LC-AA15-NOTE", "created": True}]},
    "autocad_get_entity": seq({"style": "Standard"}, {"style": "Standard"}, {"style": "LC-AA15-NOTE"}),
    "autocad_match_properties": seq(
        {"matched": 3, "not_on_source": ["text_style", "dim_style"], "properties": ["layer", "color"]},
        {"matched": 1},
    ),
    "lc.read_props": lambda handle, names: dict(AA15_WANT),
}

AA16 = {
    "autocad_batch_draw": drawn("L"),
    "autocad_modify_entity": seq(
        {"modified": 1},
        "Error: 0.33 is not a lineweight AutoCAD has. Give a lineweight in millimetres as AutoCAD lists them "
        "(0.13, 0.18, 0.25, 0.35, 0.50, 0.70 ... 2.11)",
    ),
    "lc.read_props": seq({"Lineweight": 35, "EntityTransparency": "50"}, {"Lineweight": 35}),
}

AA17_GROUPS = {"count": 3, "groups": [
    {"name": "PUMP-01", "unnamed": False, "member_count": 3},
    {"name": "LC-AA17-HAND", "unnamed": False, "member_count": 1},
    {"name": "*A1", "unnamed": True, "member_count": 1},
]}
AA17 = {
    "autocad_batch_draw": drawn("A", "B", "C", "D", "E"),
    "autocad_group": seq({"made": "PUMP-01", "members": 3}, {"group": "PUMP-01", "members": 4},
                         {"group": "PUMP-01", "members": 3}, {"ungrouped": ["PUMP-01"], "objects_kept": 3}),
    "lc.by_hand_group": seq("LC-AA17-HAND", "*A1"),
    "autocad_list_groups": seq(AA17_GROUPS, {"count": 0, "groups": []}),
    "lc.exists": True,
}

AA18 = {
    "autocad_batch_draw": drawn("K", "E", "F"),
    "autocad_set_layer_state": {"matched": 1},
    "autocad_status": STATUS,
    "autocad_trim_extend": seq(
        {"done": 0, "objects": [], "failed": [{"handle": "K", "reason": "K is on the locked layer 'LC-AA18-LOCKED'."}]},
        'NOTHING CHANGED - a dry run: it would have made 1 changed; Heron went back to its UNDO mark.\n\n'
        '{"operation": "trim", "done": 1, "objects": [{"handle": "F", "cut_away": 500.0}]}',
    ),
    "autocad_get_entity": line("F", P("AA18", 0, 1000), P("AA18", 1000, 1000)),
}


def _ucs(u: float) -> list[float]:
    o, turn = lc.origin("AA19"), math.radians(30)
    return [o[0] + u * math.cos(turn), o[1] + u * math.sin(turn), 0.0]


AA19 = {
    "autocad_set_ucs": {"set": "origin"},
    "autocad_batch_draw": drawn("L", "W"),
    "autocad_trim_extend": {"done": 1, "objects": [{"handle": "L"}]},
    "autocad_get_entity": line("L", _ucs(400), _ucs(1000)),
}

# Each row: the good recording, and what in it goes wrong for the FAIL.
SAMPLES: dict[str, tuple[dict, dict]] = {
    "AA1": (AA1, {"autocad_get_entity": line("L1", P("AA1", 0, 0), P("AA1", 400, 0), "LC-AA1")}),
    "AA2": (AA2, {"autocad_get_entity": table({**AA2_ENTITIES, "N": {**AA2_ENTITIES["N"], "color": 256}})}),
    "AA4": (AA4, {"autocad_get_entity": table({**AA4_ENTITIES, "A": {**AA4_ENTITIES["A"], "end_angle_degrees": 90.0}})}),
    "AA5": (AA5, {"lc.read_props": {"ConstantWidth": 0.0}}),
    "AA6": (AA6, {"autocad_get_entity": table({**AA6_ENTITIES, "R": {**AA6_ENTITIES["R"], "radius": 100.0}})}),
    "AA7": (AA7, {"autocad_get_entity": table({**AA7_ENTITIES, "X": line("X", P("AA7", 950, 0), P("AA7", 1000, 50))})}),
    "AA8": (AA8, {"autocad_polyline_info": {"vertex_count": 8, "area": 500000.0}}),
    "AA9": (AA9, {"autocad_get_entity": table({**AA9_ENTITIES, "B2": line("B2", P("AA9", 500, 1000), P("AA9", 1000, 1000))})}),
    "AA11": (AA11, {"autocad_polyline_info": seq(
        _poly((0, 0), (1000, 0), (1000, 800), (0, 1000), arc_at=-1),
        _poly((0, 0), (500, 0), (1000, 0), (1000, 800), (0, 1000), arc_at=2),
    )}),
    "AA12": (AA12, {"autocad_stretch": {**AA12["autocad_stretch"], "moved_whole": []}}),
    "AA15": (AA15, {"lc.read_props": lambda handle, names: {**AA15_WANT, "Lineweight": -1}}),
    "AA16": (AA16, {"lc.read_props": seq({"Lineweight": 35, "EntityTransparency": "ByLayer"}, {"Lineweight": 35})}),
    "AA17": (AA17, {"autocad_list_groups": seq(
        {**AA17_GROUPS, "groups": [*AA17_GROUPS["groups"][:2], {"name": "*A1", "unnamed": False, "member_count": 1}]},
        {"count": 0, "groups": []},
    )}),
    "AA18": (AA18, {"autocad_trim_extend": seq(
        AA18["autocad_trim_extend"].items[0],
        'DONE - 1 changed.\n\n{"operation": "trim", "done": 1, "objects": [{"handle": "F", "cut_away": 500.0}]}',
    )}),
    "AA19": (AA19, {"autocad_get_entity": line("L", _ucs(0), _ucs(400))}),
}

CHECKS = {c.row: c for c in edits.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each AA / AB check needs a good and a bad recording here"


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
