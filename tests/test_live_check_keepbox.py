"""The AV, AZ and BC live checks (views, show, a width-changing polyline) judge right from recorded answers."""

from __future__ import annotations

import pytest
from live_fakes import load, play, seq

keepbox = load("live_check_keepbox")
lc = load("live_common")

MODEL = {"count": 2, "active": "Model", "layouts": [{"name": "Model"}, {"name": "LC-A1"}]}
SHEET = {"count": 2, "active": "LC-A1", "layouts": [{"name": "Model"}, {"name": "LC-A1"}]}
AV6 = {
    "autocad_list_layouts": MODEL,
    "autocad_save_view": seq({"saved": "LC-AV6-PUMP-AREA", "replaced": False}, {"saved": "LC-AV6-PUMP-AREA", "replaced": True},
                             {"saved": "LC-AV6-PUMP-AREA", "replaced": True}),
}
LAYER_HANDLE = "2F"
AZ6 = {
    "autocad_list_layouts": MODEL,
    "autocad_draw_line": {"created": True, "handle": "L1"},
    "autocad_run_lisp": {"result": LAYER_HANDLE, "timed_out": False},
    "autocad_show": seq(
        {"shown": 1, "isolated": False, "not_found": [keepbox.BOGUS_HANDLE],
         "not_selectable": [{"handle": LAYER_HANDLE, "reason": "not_a_drawing_object"}]},
        {"shown": 1, "isolated": True, "not_found": [], "not_selectable": []},
        {"isolation_ended": True},
        {"shown": 0, "isolated": False, "not_found": [], "not_selectable": [{"handle": LAYER_HANDLE, "reason": "not_a_drawing_object"}]},
    ),
}
ORIGIN = lc.origin("BC13")
VERTS = [[ORIGIN[0], ORIGIN[1]], [ORIGIN[0] + 1000, ORIGIN[1]]]
BC13 = {
    "autocad_batch_draw": {"created": 2, "failed": 0, "handles": ["P", "E"]},
    "lc.by_hand_width": None,
    "autocad_get_entity": seq({"type": "polyline", "vertices": VERTS}, {"type": "polyline", "vertices": VERTS}),
    "autocad_trim_extend": {"operation": "trim", "done": 0, "objects": [],
                            "failed": [{"handle": "P", "reason": "P is a polyline whose width changes along it. Heron would lose those widths."}]},
}

SAMPLES = {
    "AV6": (AV6, {"autocad_save_view": seq({"saved": "x", "replaced": False}, {"saved": "x", "replaced": True}, {"saved": "x", "replaced": False})}),
    "AZ6": (AZ6, {"autocad_show": seq(
        {"shown": 2, "isolated": False, "not_found": [keepbox.BOGUS_HANDLE], "not_selectable": [{"handle": LAYER_HANDLE, "reason": "not_a_drawing_object"}]},
        {"shown": 1, "isolated": True}, {"isolation_ended": True}, {"shown": 0, "isolated": False})}),
    "BC13": (BC13, {"autocad_trim_extend": {"operation": "trim", "done": 1, "objects": [{"handle": "P"}]}}),
}
CHECKS = {c.row: c for c in keepbox.CHECKS}


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


@pytest.mark.parametrize("row", ["AV6", "AZ6"])
def test_a_sheet_in_front_makes_the_row_not_run(monkeypatch, row):
    verdict = play(monkeypatch, CHECKS[row], {**SAMPLES[row][0], "autocad_list_layouts": SHEET})
    assert verdict.refused and "not run this time" in verdict.evidence
    assert not verdict.called("autocad_save_view") and not verdict.called("autocad_show")


def test_the_isolation_is_ended_even_when_isolating_fails_az6(monkeypatch):
    broken = {**AZ6, "autocad_show": seq(
        {"shown": 1, "isolated": False, "not_found": [keepbox.BOGUS_HANDLE], "not_selectable": [{"handle": LAYER_HANDLE, "reason": "not_a_drawing_object"}]},
        {"shown": 0, "isolated": False}, {"isolation_ended": True})}
    verdict = play(monkeypatch, CHECKS["AZ6"], broken)
    assert not verdict.passed
    assert verdict.called("autocad_show")[-1] == {"end_isolation": True}


def test_az6_needs_admin_for_the_layers_handle():
    assert "admin" in CHECKS["AZ6"].needs


def test_every_row_of_the_four_groups_is_measured_or_excused_once():
    assert not set(CHECKS) & set(keepbox.BY_EYE)
    rows = set(CHECKS) | set(keepbox.BY_EYE)
    want = ({f"AV{n}" for n in range(1, 8)} | {f"AX{n}" for n in range(1, 9)} | {f"AZ{n}" for n in range(1, 7)}
            | {f"BC{n}" for n in range(1, 14)})
    assert rows == want
