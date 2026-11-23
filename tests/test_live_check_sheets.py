"""The AF live checks (sheets made by the plug-in) judge right from recorded answers."""

from __future__ import annotations

import pytest
from live_fakes import load, play, seq

sheets = load("live_check_sheets")


def tabs(*names: str, active: str = "Model") -> dict:
    return {"count": len(names), "active": active, "layouts": [{"name": n, "tab_order": i} for i, n in enumerate(names)]}


BEFORE = tabs("Model", "Layout1", "LC-A1")
FIVE = [f"LC-AF2-{n}" for n in range(102, 107)]
AF2 = {
    "autocad_list_layouts": seq(BEFORE, tabs("Model", "Layout1", "LC-A1", *FIVE)),
    "autocad_create_layout": lambda name, **kw: {"created": True, "layout": name, "made_by": "plugin", "page_setup": {}},
}
AF4 = {
    "autocad_list_layouts": seq(BEFORE, BEFORE),
    "autocad_create_layout": seq(
        "Error: 'A7' is not a paper size the DWG To PDF.pc3 plotter offers. Nothing was changed.",
        "Error: AutoCAD would not set the plotter 'No Such.pc3'. Use the name exactly as it appears in Page Setup.",
        "Error: 'none.ctb' is not a plot style table here. Nothing was changed.",
    ),
}

SAMPLES = {
    "AF2": (AF2, {"autocad_list_layouts": seq(BEFORE, tabs("Model", "Layout1", "LC-A1", *FIVE, active="LC-AF2-106"))}),
    "AF4": (AF4, {"autocad_list_layouts": seq(BEFORE, tabs("Model", "Layout1", "LC-A1", "LC-AF4-STYLE"))}),
}
CHECKS = {c.row: c for c in sheets.CHECKS}


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


def test_a_sheet_that_is_not_made_fails_af2(monkeypatch):
    broken = {**AF2, "autocad_create_layout": lambda name, **kw: {"created": True, "layout": name, "warning": "AutoCAD went busy"}}
    verdict = play(monkeypatch, CHECKS["AF2"], broken)
    assert not verdict.passed and "busy" in verdict.evidence


def test_a_refusal_that_is_allowed_fails_af4(monkeypatch):
    allowed = {**AF4, "autocad_create_layout": {"created": True, "layout": "LC-AF4-A7"}}
    verdict = play(monkeypatch, CHECKS["AF4"], allowed)
    assert not verdict.passed and "expected a refusal" in verdict.evidence


def test_every_af_row_is_measured_or_excused_once():
    assert not set(CHECKS) & set(sheets.BY_EYE)
    assert set(CHECKS) | set(sheets.BY_EYE) == {f"AF{n}" for n in range(1, 25)}
