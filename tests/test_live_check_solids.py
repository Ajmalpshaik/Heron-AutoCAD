"""The AR live checks (pyramid, polysolid, solid face edits) judge right from recorded answers."""

from __future__ import annotations

import math

import pytest
from live_fakes import load, play, seq

solids = load("live_check_solids")
lc = load("live_common")

BOX = {"created": True, "handle": "X", "volume": 300_000_000.0}


def box(row: str, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, dx: float = 0, dy: float = 0) -> dict:
    o = lc.origin(row)
    return {"type": "3dsolid", "bounding_box": {"min": [o[0] + dx + x0, o[1] + dy + y0, z0], "max": [o[0] + dx + x1, o[1] + dy + y1, z1]}}


AR1 = {
    "autocad_add_pyramid": {"created": True, "handle": "P", "volume": 108_000_000.0, "expected_volume": 108_000_000.0,
                            "turned": True, "remade_to_size": False},
    "autocad_get_entity": box("AR1", -300, 300, -300, 300, 0, 900),
}
AR2 = {
    "autocad_add_pyramid": {"created": True, "handle": "P", "volume": 30_310_889.0, "expected_volume": 30_310_889.0, "turned": True},
    "autocad_get_entity": box("AR2", -200, 200, -173.205, 173.205, 0, 500),
}
SIDE = 1200 * (math.cos(math.radians(75)) + math.sin(math.radians(75)))
AR3 = {
    "autocad_add_pyramid": seq({"created": True, "handle": "H1"}, {"created": True, "handle": "H2"}),
    "autocad_set_ucs": {"current": {"rotation_degrees": 30}},
    "autocad_get_entity": seq(box("AR3", -600, 600, -600, 600, 0, 900, dy=3000),
                              box("AR3", -SIDE / 2, SIDE / 2, -SIDE / 2, SIDE / 2, 0, 900, dx=5000, dy=3000)),
}
AR4 = {
    "autocad_add_polysolid": {"created": True, "handle": "W", "volume": 1_920_000_000.0, "path_length": 8000.0},
    "autocad_get_entity": box("AR4", 0, 5000, 0, 3000, 0, 1200),
}
AR5 = {
    "autocad_add_polysolid": seq({"created": True, "handle": "L", "volume": 1_872_000_000.0}, {"created": True, "handle": "R", "volume": 1_968_000_000.0}),
    "autocad_get_entity": seq(box("AR5", 0, 5000, 0, 3000, 0, 1200), box("AR5", 0, 5200, -200, 3000, 0, 1200, dy=10000)),
}
AR6 = {
    "autocad_draw_polyline": seq({"created": True, "handle": "P1"}, {"created": True, "handle": "P2"}),
    "autocad_add_polysolid": seq(*({"created": True, "handle": f"W{n}", "volume": v} for n, v in
                                   enumerate((3_168_000_000.0, 3_552_000_000.0, 3_168_000_000.0, 3_552_000_000.0)))),
    "autocad_get_entity": {"type": "polyline", "closed": True},
}
TIGHT = "Error: The wall's path turns tighter than the wall is wide at 1 place(s). Nothing was changed."
AR7 = {
    "autocad_batch_draw": seq({"created": 1, "handles": ["PA"]}, {"created": 1, "handles": ["PR"]}, {"created": 1, "handles": ["PT"]}),
    "autocad_draw_circle": {"created": True, "handle": "C"},
    "autocad_add_polysolid": seq(
        {"created": True, "handle": "W1", "volume": 4000.0 * 200 * 1000, "path_length": 4000.0},
        {"created": True, "handle": "W2", "volume": 2 * math.pi * 1000 * 200 * 1000, "path_length": 2 * math.pi * 1000},
        {"created": True, "handle": "W3", "closed": True},
        TIGHT,
    ),
    "autocad_get_entity": {"type": "polyline", "closed": False},
}
AR8 = {
    "autocad_add_solid": seq({**BOX, "handle": "B1"}, {**BOX, "handle": "B2"}),
    "autocad_edit_solid_faces": seq({"action": "offset", "volume_before": 3e8, "volume_after": 360_000_000.0},
                                    {"action": "move", "volume_before": 3e8, "volume_after": 360_000_000.0}),
    "autocad_get_entity": seq(box("AR8", -500, 500, -300, 300, 0, 600), box("AR8", -500, 700, -300, 300, 0, 500, dx=5000)),
}
AR9 = {
    "autocad_add_solid": BOX,
    "autocad_edit_solid_faces": {"action": "taper", "volume_before": 3e8, "volume_after": 277_959_000.0},
}
FACES = {"handle": "X", "volume": 298_927_000.0, "face_count": 10,
         "faces": [{"index": 0, "kind": "plane", "area": 1.0, "normal": [0, 0, 1]}, {"index": 4, "kind": "cylinder", "area": 25000.0}]}
AR10 = {
    "autocad_add_solid": seq({**BOX, "handle": "F"}, {**BOX, "handle": "G"}),
    "autocad_fillet_solid_edges": {"handle": "F", "volume_before": 3e8, "volume_after": 298_927_000.0},
    "autocad_list_solid_faces_and_edges": seq(FACES, {"handle": "G", "volume": 300_000_000.0, "face_count": 6, "faces": []}),
    "autocad_edit_solid_faces": seq({"action": "delete", "volume_before": 298_927_000.0, "volume_after": 299_195_000.0},
                                    "Error: A box's top cannot be closed over, so it cannot be deleted. Nothing was changed."),
}
AR11 = {
    "autocad_add_solid": BOX,
    "autocad_draw_rectangle": {"created": True, "handle": "RC"},
    "autocad_draw_line": {"created": True, "handle": "LN"},
    "autocad_imprint_solid": seq({"handle": "X", "faces_before": 6, "faces_after": 7},
                                 {"handle": "X", "faces_before": 7, "faces_after": 7, "note": "Nothing new was imprinted: the face and edge counts did not change."}),
    "autocad_get_entity": {"type": "polyline"},
    "autocad_list_solid_faces_and_edges": {"handle": "X", "volume": 3e8, "faces": [{"index": 0, "area": 600000.0}, {"index": 6, "area": 80000.0}]},
    "autocad_press_pull_faces": {"handle": "X", "volume_before": 3e8, "volume_after": 308_000_000.0},
}

SAMPLES = {
    "AR1": (AR1, {"autocad_get_entity": box("AR1", -300, 300, -300, 300, 0, 450)}),
    "AR2": (AR2, {"autocad_add_pyramid": {"created": True, "handle": "P", "volume": 20_000_000.0, "expected_volume": 30_310_889.0}}),
    "AR3": (AR3, {"autocad_get_entity": seq(box("AR3", -600, 600, -600, 600, 0, 900, dy=3000),
                                            box("AR3", -600, 600, -600, 600, 0, 900, dx=5000, dy=3000))}),
    "AR4": (AR4, {"autocad_add_polysolid": {"created": True, "handle": "W", "volume": 1_900_000_000.0}}),
    "AR5": (AR5, {"autocad_add_polysolid": seq({"created": True, "handle": "L", "volume": 1_968_000_000.0},
                                               {"created": True, "handle": "R", "volume": 1_872_000_000.0})}),
    "AR6": (AR6, {"autocad_add_polysolid": seq(*({"created": True, "handle": f"W{n}", "volume": 3_168_000_000.0} for n in range(4)))}),
    "AR7": (AR7, {"autocad_add_polysolid": seq(
        {"created": True, "handle": "W1", "volume": 1.0, "path_length": 4000.0},
        {"created": True, "handle": "W2", "volume": 2 * math.pi * 1000 * 200 * 1000, "path_length": 2 * math.pi * 1000},
        {"created": True, "handle": "W3", "closed": True}, TIGHT)}),
    "AR8": (AR8, {"autocad_edit_solid_faces": seq({"action": "offset", "volume_after": 330_000_000.0},
                                                  {"action": "move", "volume_after": 360_000_000.0})}),
    "AR9": (AR9, {"autocad_edit_solid_faces": {"action": "taper", "volume_before": 3e8, "volume_after": 3e8}}),
    "AR10": (AR10, {"autocad_edit_solid_faces": seq({"action": "delete", "volume_before": 298_927_000.0, "volume_after": 298_927_000.0},
                                                    "Error: not allowed")}),
    "AR11": (AR11, {"autocad_imprint_solid": seq({"handle": "X", "faces_before": 6, "faces_after": 6},
                                                 {"handle": "X", "faces_before": 7, "faces_after": 7, "note": "Nothing new was imprinted"})}),
}
CHECKS = {c.row: c for c in solids.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES)


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    verdict = play(monkeypatch, CHECKS[row], SAMPLES[row][0])
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


def test_ar3_puts_the_ucs_back_to_the_world(monkeypatch):
    verdict = play(monkeypatch, CHECKS["AR3"], AR3)
    assert verdict.called("autocad_set_ucs")[-1]["mode"] == "world"


def test_a_tight_arc_that_is_allowed_fails_ar7(monkeypatch):
    allowed = {**AR7, "autocad_add_polysolid": seq(
        {"created": True, "handle": "W1", "volume": 4000.0 * 200 * 1000, "path_length": 4000.0},
        {"created": True, "handle": "W2", "volume": 2 * math.pi * 1000 * 200 * 1000, "path_length": 2 * math.pi * 1000},
        {"created": True, "handle": "W3", "closed": True}, {"created": True, "handle": "W4"})}
    verdict = play(monkeypatch, CHECKS["AR7"], allowed)
    assert not verdict.passed and "expected a refusal" in verdict.evidence


def test_ar9_says_which_way_the_face_leaned(monkeypatch):
    assert "in (smaller)" in play(monkeypatch, CHECKS["AR9"], AR9).evidence
    out = play(monkeypatch, CHECKS["AR9"], {**AR9, "autocad_edit_solid_faces": {"volume_before": 3e8, "volume_after": 3.2e8}})
    assert out.passed and "out (larger)" in out.evidence


def test_every_ar_row_is_measured_or_excused_once():
    assert not set(CHECKS) & set(solids.BY_EYE)
    assert set(CHECKS) | set(solids.BY_EYE) == {f"AR{n}" for n in range(1, 15)}
