"""The AS live check judges right from recorded answers; every AS and AO row is accounted for."""

from __future__ import annotations

import pytest
from live_fakes import load, play, seq

reads = load("live_check_reads")

AS5 = {
    "autocad_add_construction_line": seq({"created": True, "handle": "X1", "type": "xline"},
                                         {"created": True, "handle": "R1", "type": "ray"}),
    "autocad_get_extents": seq(
        "Error: Layer 'LC-AS5' has 2 object(s), but none with extents (rays and construction lines run on for ever).",
        "Error: Layer 'LC-AS5-EMPTY' has no geometry, so it has no extents.",
    ),
    "autocad_create_layer": {"name": "LC-AS5-EMPTY", "created": True},
}
SAMPLES = {
    "AS5": (AS5, {"autocad_get_extents": seq({"min": [0, 0, 0], "max": [1, 1, 0], "entity_count": 2},
                                             "Error: Layer 'LC-AS5-EMPTY' has no geometry.")}),
}
CHECKS = {c.row: c for c in reads.CHECKS}


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
    assert not verdict.passed and not verdict.refused, verdict.evidence


def test_every_as_and_ao_row_is_measured_or_excused_once():
    rows = set(CHECKS) | set(reads.BY_EYE)
    assert not set(CHECKS) & set(reads.BY_EYE)
    assert rows == {f"AS{n}" for n in range(1, 12)} | {f"AO{n}" for n in range(1, 11)}
