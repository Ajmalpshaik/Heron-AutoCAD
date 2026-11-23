"""The BD live checks (tool bugs the runner found) judge right from recorded answers."""

from __future__ import annotations

import pytest
from live_fakes import load, play, seq

bugfixes = load("live_check_bugfixes")
lc = load("live_common")


def counts(*numbers: int):
    return seq(*({"active_drawing": {"name": "Drawing1.dwg", "path": "", "model_space_entities": n}} for n in numbers))


BAD_LAYER = "Error: The layer name 'L|PAVE' contains |, which AutoCAD does not allow. Avoid < > / \\ \" : ; ? * | , = ` in names."
LINE_BREAK = "Error: The layer name holds a line break, which cannot be typed into AutoCAD's command line. Nothing was typed."
BD4 = {"autocad_table_from_excel": {"created": True, "handle": "T", "linked": False, "rows": 2, "columns": 3}}
BD6 = {
    "autocad_draw_polyline": {"created": True, "handle": "B"},
    "autocad_batch_draw": {"created": 2, "failed": 0, "handles": ["L1", "L2"]},
    "autocad_make_block": {"created": True, "block": "LC-BD6-TILE"},
    "autocad_status": counts(40, 40),
    "autocad_list_layers": seq({"count": 5, "layers": []}, {"count": 5, "layers": []}),
    "autocad_super_hatch": seq(BAD_LAYER, LINE_BREAK),
}
SAMPLES = {
    "BD4": (BD4, {"autocad_table_from_excel": {"created": True, "handle": "T", "rows": 2, "columns": 1}}),
    "BD6": (BD6, {"autocad_super_hatch": seq(BAD_LAYER, "Error: the boundary is not closed.")}),
}
CHECKS = {c.row: c for c in bugfixes.CHECKS}


def context(tmp_path):
    ctx = lc.Context(version="27.0", padlocks={"changes": True})
    ctx.folder = tmp_path
    return ctx


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES)


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, tmp_path, row):
    verdict = play(monkeypatch, CHECKS[row], SAMPLES[row][0], context(tmp_path))
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, tmp_path, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad}, context(tmp_path))
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


def test_bd4_writes_a_semicolon_csv_in_the_runners_folder(monkeypatch, tmp_path):
    verdict = play(monkeypatch, CHECKS["BD4"], BD4, context(tmp_path))
    sent = verdict.called("autocad_table_from_excel")[0]["path"]
    assert sent.startswith(str(tmp_path))
    assert (tmp_path / "lc-bd4-semicolon.csv").read_text(encoding="utf-8").splitlines()[0] == "TAG;FLOW;NOTE"


def test_bd6_fails_when_something_was_made_although_refused(monkeypatch, tmp_path):
    made = {**BD6, "autocad_status": counts(40, 41)}
    verdict = play(monkeypatch, CHECKS["BD6"], made, context(tmp_path))
    assert not verdict.passed and "something was made" in verdict.evidence


def test_bd6_fails_when_a_layer_appeared(monkeypatch, tmp_path):
    made = {**BD6, "autocad_list_layers": seq({"count": 5, "layers": []}, {"count": 6, "layers": []})}
    verdict = play(monkeypatch, CHECKS["BD6"], made, context(tmp_path))
    assert not verdict.passed and "layer appeared" in verdict.evidence


def test_every_bd_row_is_measured_or_excused_once():
    assert not set(CHECKS) & set(bugfixes.BY_EYE)
    assert set(CHECKS) | set(bugfixes.BY_EYE) == {f"BD{n}" for n in range(1, 7)}
