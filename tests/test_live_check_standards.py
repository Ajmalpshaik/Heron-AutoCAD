"""The AT live checks (the office layer standard) judge right from recorded answers."""

from __future__ import annotations

import pytest
from live_fakes import load, play, seq

standards = load("live_check_standards")
lc = load("live_common")

NONE_LOADED = {"in_force": "the generic MEP example", "file": "x", "office_standard": None, "standard": {"counts": {"layers": 20}}}
LOADED = {"in_force": "the office layer standard on this PC", "file": "o.json", "office_standard": "o.json", "standard": {"counts": {"layers": 5}}}
NOT_LOADED = (
    "No office layer standard is loaded on this PC yet. autocad_layer_standard(action='template') puts an empty CSV in F; "
    "fill it, then autocad_layer_standard(action='import')."
)
PROBLEMS = "Error: The layer standard has problems, nothing was kept: row 2: M-A: colour 'reed'; row 3: M-B: lineweight 0.33 is not a lineweight AutoCAD has."

AT3 = {
    "autocad_layer_standard": seq(NONE_LOADED, PROBLEMS, NONE_LOADED),
}
AT5 = {
    "autocad_layer_standard": NONE_LOADED,
    "autocad_check_standards": {"passed": None, "source": "the generic MEP example",
                                "layer_standard": {"example": True, "warning": NOT_LOADED + " Checked against the example instead, so nothing is decided by it."}},
}
AT7 = {
    "autocad_layer_standard": NONE_LOADED,
    "autocad_remap_layers": "Error: " + NOT_LOADED + " Nothing was moved. To try the generic MEP example instead, say layer_standard='example'.",
}
AT8 = {
    "autocad_check_standards": {
        "passed": None,
        "source": "the generic MEP example layer standard that ships with Heron (not an office standard)",
        "layer_standard": {"example": True, "note": "This is the generic MEP example that ships with Heron, not an office's standard: say so in the answer."},
    },
}

SAMPLES = {
    "AT3": (AT3, {"autocad_layer_standard": seq(NONE_LOADED, "Error: row 2: M-A: colour 'reed'", NONE_LOADED)}),
    "AT5": (AT5, {"autocad_check_standards": {"passed": True, "layer_standard": {"example": True, "warning": ""}}}),
    "AT7": (AT7, {"autocad_remap_layers": "Error: the drawing has no layers to move."}),
    "AT8": (AT8, {"autocad_check_standards": {"passed": None, "source": "the office standard",
                                              "layer_standard": {"example": False, "note": ""}}}),
}
CHECKS = {c.row: c for c in standards.CHECKS}


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


def test_a_standard_that_changed_after_a_refused_import_fails_at3(monkeypatch, tmp_path):
    changed = {"autocad_layer_standard": seq(NONE_LOADED, PROBLEMS, LOADED)}
    verdict = play(monkeypatch, CHECKS["AT3"], {**AT3, **changed}, context(tmp_path))
    assert not verdict.passed and "changed" in verdict.evidence


def test_at3_writes_its_csv_in_the_runners_folder_and_imports_that_file(monkeypatch, tmp_path):
    verdict = play(monkeypatch, CHECKS["AT3"], AT3, context(tmp_path))
    sent = verdict.called("autocad_layer_standard")[1]
    assert sent["action"] == "import" and sent["path"].startswith(str(tmp_path))
    assert (tmp_path / "standards" / "lc-at3-bad.csv").is_file()


@pytest.mark.parametrize("row", ["AT5", "AT7"])
def test_with_an_office_standard_loaded_the_row_is_said_not_run(monkeypatch, tmp_path, row):
    loaded = {**SAMPLES[row][0], "autocad_layer_standard": LOADED}
    verdict = play(monkeypatch, CHECKS[row], loaded, context(tmp_path))
    assert verdict.refused and "not run this time" in verdict.evidence
    assert not verdict.called("autocad_check_standards") and not verdict.called("autocad_remap_layers")


def test_nothing_here_imports_or_removes_the_office_standard(monkeypatch, tmp_path):
    for row in CHECKS:
        verdict = play(monkeypatch, CHECKS[row], SAMPLES[row][0], context(tmp_path))
        actions = [c["action"] for c in verdict.called("autocad_layer_standard")]
        assert "remove" not in actions and "template" not in actions
        if row != "AT3":
            assert "import" not in actions


def test_every_at_row_is_measured_or_excused_once():
    assert not set(CHECKS) & set(standards.BY_EYE)
    assert set(CHECKS) | set(standards.BY_EYE) == {f"AT{n}" for n in range(1, 9)}
