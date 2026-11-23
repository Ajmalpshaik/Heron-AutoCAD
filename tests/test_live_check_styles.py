"""The AN live checks (multileader and table styles) judge right from recorded answers."""

from __future__ import annotations

import pytest
from live_fakes import load, play, seq

styles = load("live_check_styles")
lc = load("live_common")


def ml(name: str, **extra) -> dict:
    return {"multileader_styles": [{"name": name, **extra}]}


def ts(name: str, **extra) -> dict:
    return {"table_styles": [{"name": name, **extra}]}


AN1_ROW = {"created": True, "current": True, "attachment": "underline_bottom_line", "arrow": "closed_filled",
           "arrow_size": 2.5, "dogleg_length": 2.5, "scale": 50.0, "text_height": 2.5}
AN1 = {
    "autocad_create_styles": ml("LC-AN1-LABEL-50", **AN1_ROW),
    "autocad_get_variable": {"name": "CMLEADERSTYLE", "value": "LC-AN1-LABEL-50"},
}
AN2 = {
    **AN1,
    "autocad_add_multileader": {"created": True, "handle": "M1", "leader_lines": 1, "not_set": []},
    "lc.read_props": {"StyleName": "LC-AN1-LABEL-50", "TextHeight": 125.0},
}
AN3_OUT = {"text_styles": [{"name": "LC-AN3-ROMANS", "created": True}],
           "multileader_styles": [{"name": "LC-AN3-TAG-DOT", "created": True, "text_style": "LC-AN3-ROMANS", "arrow": "dot",
                                   "arrow_size": 1.5, "landing_gap": 0.5, "attachment": "middle_of_text",
                                   "arrow_block_added": "_DOT"}]}
AN3 = {"autocad_get_variable": {"name": "DIMBLK", "value": ""}, "autocad_create_styles": AN3_OUT}
AN5 = {"autocad_create_styles": seq(
    ml("LC-AN5-LABEL", created=True, text_height=2.5, scale=50.0),
    ml("LC-AN5-LABEL", created=False, notes=["'LC-AN5-LABEL' is already in this drawing. Pass replace=true to update it."]),
    ml("LC-AN5-LABEL", created=False, text_height=3.5, scale=1.0),
)}
AN6 = {"autocad_create_styles": seq(
    {"multileader_styles": [
        {"name": "LC-AN6-BAD", "created": False, "notes": ["This drawing has no text style called 'LC-AN6-NOPE'. Make it first."]},
        {"name": "LC-AN6-GOOD", "created": True}]},
    ml("LC-AN6-BAD", created=True),
)}
AN7_ROW = {"created": True, "current": True, "text_heights": {"title": 125.0, "header": 125.0, "data": 125.0},
           "margins": {"horizontal": 41.666667, "vertical": 41.666667},
           "alignment": {"title": "middle_centre", "header": "middle_centre", "data": "middle_left"}}
AN7 = {
    "autocad_create_styles": ts("LC-AN7-SCHEDULE-50", **AN7_ROW),
    "autocad_get_variable": {"name": "CTABLESTYLE", "value": "LC-AN7-SCHEDULE-50"},
}
AN8 = {
    **AN7,
    "autocad_add_table": {"created": True, "handle": "T1", "rows": 3, "columns": 2, "rows_aligned_middle": 3},
    "lc.read_props": {"StyleName": "LC-AN7-SCHEDULE-50"},
}
AN9 = {
    "autocad_create_styles": ts("LC-AN9-NO-TITLE", created=True, title_row=False, header_row=False),
    "autocad_add_table": {"created": True, "handle": "T2", "rows": 2, "columns": 2, "data_rows": 2},
}
AN10 = {"autocad_create_styles": seq(
    ts("LC-AN10-A", created=False, notes=["'top left' is not a table alignment. Heron keeps a table's text in the vertical middle of each cell."]),
    ml("LC-AN10-B", created=False, notes=["'0.02' could be a ratio or a scale factor. Write the scale as on the sheet: '1:50'"]),
    "Error: multileader style 1 ('LC-AN10-C'): arow is not an option. Nothing was changed.",
    {"table_styles": [{"name": "LC-AN10-A", "created": True}],
     "multileader_styles": [{"name": "LC-AN10-B", "created": True}, {"name": "LC-AN10-C", "created": True}]},
)}
AN13 = {
    "autocad_status": seq(*[{"active_drawing": {"model_space_entities": 40}}] * 2),
    "autocad_add_table": "Error: This drawing has no table style called 'LC-AN13-NOPE' (Key not found). Make it with "
                         "autocad_create_styles(table_styles=...), or copy it in with autocad_import_from_drawing. "
                         "Nothing was left in the drawing.",
    "autocad_add_multileader": "Error: This drawing has no multileader style called 'LC-AN13-NOPE' (Key not found). "
                               "Make it with autocad_create_styles(multileader_styles=...), or copy it in with "
                               "autocad_import_from_drawing. Nothing was left in the drawing.",
}

AL8_REFUSED = ("PropertyRefused: AutoCAD has no property 'Radius' on this object (AddLine), so it could not be set. "
               "AutoCAD was not busy, so it was not asked again.")
AL8 = {"lc.by_hand_line": "L8", "lc.by_hand_set": {"error": AL8_REFUSED, "seconds": 0.05}}

AL10_MISSING = ("MemberMissing: AutoCAD has no property or method 'Radius' on this object (IAcadLine), so it could "
                "not be read. AutoCAD was not busy, so it was not asked again.")
AL10 = {"lc.by_hand_line": "L10", "lc.by_hand_get": {"error": AL10_MISSING, "seconds": 0.04}}

SAMPLES = {
    "AL10": (AL10, {"lc.by_hand_get": {"error": "AutocadError: Lost the COM connection to AutoCAD and could not "
                                       "re-establish it within 10s.", "seconds": 10.1}}),
    "AL8": (AL8, {"lc.by_hand_set": {"error": "OutcomeUnknown: Outcome unknown: AutoCAD went busy part-way through",
                                     "seconds": 10.2}}),
    "AN1": (AN1, {"autocad_create_styles": ml("LC-AN1-LABEL-50", **{**AN1_ROW, "attachment": "middle"})}),
    "AN2": (AN2, {"lc.read_props": {"StyleName": "LC-AN1-LABEL-50", "TextHeight": 6250.0}}),
    "AN3": (AN3, {"autocad_get_variable": seq({"value": ""}, {"value": "_DOT"})}),
    "AN5": (AN5, {"autocad_create_styles": seq(
        ml("LC-AN5-LABEL", created=True), ml("LC-AN5-LABEL", created=True),
        ml("LC-AN5-LABEL", created=False, text_height=3.5, scale=1.0))}),
    "AN6": (AN6, {"autocad_create_styles": seq(AN6["autocad_create_styles"].items[0], ml("LC-AN6-BAD", created=False))}),
    "AN7": (AN7, {"autocad_create_styles": ts("LC-AN7-SCHEDULE-50", **{**AN7_ROW, "alignment": {
        "title": "middle_centre", "header": "middle_centre", "data": "top_left"}})}),
    "AN8": (AN8, {"autocad_add_table": {"created": True, "handle": "T1", "rows_aligned_middle": 2}}),
    "AN9": (AN9, {"autocad_create_styles": ts("LC-AN9-NO-TITLE", created=True, title_row=True, header_row=False)}),
    "AN10": (AN10, {"autocad_create_styles": seq(*AN10["autocad_create_styles"].items[:3], {
        "table_styles": [{"name": "LC-AN10-A", "created": False}], "multileader_styles": []})}),
    "AN13": (AN13, {"autocad_status": seq({"active_drawing": {"model_space_entities": 40}},
                                             {"active_drawing": {"model_space_entities": 41}})}),
}

CHECKS = {c.row: c for c in styles.CHECKS}


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


def test_every_an_and_al_row_is_measured_or_excused_once():
    rows = set(CHECKS) | set(styles.BY_EYE)
    assert not set(CHECKS) & set(styles.BY_EYE)
    assert {f"AN{n}" for n in range(1, 14)} | {f"AL{n}" for n in range(1, 12)} == rows
