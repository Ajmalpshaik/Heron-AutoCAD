"""The AD live checks (Overkill, boundary, eTransmit) judge right from recorded answers."""

from __future__ import annotations

from pathlib import Path

import pytest
from live_fakes import load, play, seq

cleanup = load("live_check_cleanup")
lc = load("live_common")

STATUS = {"active_drawing": {"name": "Drawing1.dwg", "path": "", "model_space_entities": 30}}


def P(row: str, x: float, y: float) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y, 0.0]


AD1_LINES = {"B": {"handle": "B", "type": "line", "start": P("AD1", 0, 0), "end": P("AD1", 1000, 0)},
             "C": {"handle": "C", "type": "line", "start": P("AD1", 200, 0), "end": P("AD1", 600, 0)}}
AD1 = {
    "autocad_batch_draw": {"created": 3, "handles": ["A", "B", "C"]},
    "autocad_status": STATUS,
    "autocad_overkill": {"confirmed": False, "plan_id": "p1", "looked_at": 3, "erase_count": 2, "erase": [
        {"handle": "B", "type": "line", "reason": "an exact copy", "kept": "A"},
        {"handle": "C", "type": "line", "reason": "lies inside a longer line", "kept": "A"}]},
    "autocad_get_entity": lambda handle: AD1_LINES[handle],
    "autocad_show": {"shown": 2, "isolated": False, "not_found": []},
}
AD8 = {
    "autocad_batch_draw": {"created": 2, "handles": ["R", "K"]},
    "autocad_trace_boundary": seq(
        {"created": True, "handle": "O1", "type": "polyline", "area": 12_000_000.0, "net_area": 11_840_000.0,
         "islands": [{"handle": "I1", "area": 160_000.0}], "window": True},
        {"created": True, "handle": "G1", "type": "region", "area": 11_840_000.0, "net_area": 11_840_000.0,
         "islands": [{"handle": "I2", "area": 160_000.0}], "window": True},
    ),
    "autocad_get_entity": {"handle": "G1", "type": "region", "area": 11_840_000.0},
}
SAVED = Path("C:/Temp/x/project/live-check.dwg")
AD11 = {
    "lc.new_drawing": "Drawing4.dwg",
    "autocad_etransmit": seq(
        "Error: This drawing has never been saved, so there is no file to pack. Save it first (autocad_save_drawing).",
        {"pack": "live-check - transmittal", "packed": [{"kind": "drawing", "name": "live-check.dwg"}], "missing": [],
         "note": "Nothing was written (list_only)."},
    ),
    "lc.activate": None,
    "lc.save_scratch": SAVED,
    "lc.files_in": seq(["live-check.dwg"], ["live-check.dwg"]),
}

SAMPLES = {
    "AD1": (AD1, {"autocad_overkill": {"confirmed": False, "plan_id": "p1", "erase": [
        {"handle": "B", "type": "line", "reason": "an exact copy", "kept": "A"}]}}),
    "AD8": (AD8, {"autocad_get_entity": {"handle": "G1", "type": "region", "area": 12_000_000.0}}),
    "AD11": (AD11, {"lc.files_in": seq(["live-check.dwg"], ["live-check.dwg", "live-check - transmittal.zip"])}),
}

CHECKS = {c.row: c for c in cleanup.CHECKS}


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


def test_every_ad_row_is_measured_or_excused_once():
    rows = set(CHECKS) | set(cleanup.BY_EYE)
    assert not set(CHECKS) & set(cleanup.BY_EYE)
    assert rows == {f"AD{n}" for n in range(1, 13)}
