"""The AW, BA and BF live checks (control characters, run_lisp answers) judge right from recorded answers."""

from __future__ import annotations

import json

import pytest
from live_fakes import load, play, seq

text = load("live_check_textsafety")

STATUS = {"active_drawing": {"name": "Drawing1.dwg", "path": "", "model_space_entities": 30}}


def counts(*numbers: int):
    return seq(*({"active_drawing": {"name": "Drawing1.dwg", "path": "", "model_space_entities": n}} for n in numbers))


def job(first: str, **data) -> str:
    return f"{first}\n\n{json.dumps(data)}"


LISP_ERROR = job("NOTHING CHANGED - nothing was written", expression="(+ 1 nil)", result=None, timed_out=False,
                 lisp_error="bad argument type: numberp: nil", note="AutoCAD reported a LISP error.")
AW1 = {"autocad_run_lisp": seq(LISP_ERROR, {"result": "3", "timed_out": False})}
AW2_ANSWER = job("NOTHING CHANGED - nothing was written", result=None, timed_out=False, lisp_error="bad argument type: consp 5", chunks=6,
                 chunks_finished=5, note="AutoCAD reported a LISP error. It was the last of 6 pieces: Pieces 1 to 5 ran.")
AW2 = {"autocad_run_lisp": seq(AW2_ANSWER, {"result": "USUBR", "timed_out": False})}
AW3 = {"autocad_run_lisp": {"result": None, "timed_out": False, "lisp_error": "no function definition: NO-SUCH-FUNCTION"}}
AW4 = {"autocad_run_lisp": {"result": "nil", "timed_out": False}, "autocad_status": counts(30, 31, 32)}
TOO_LONG = "Error: One top-level form is 1,800 characters, over the 1,750 AutoCAD takes. Split it: define helpers with defun as separate forms."
AW9 = {"autocad_run_lisp": seq({"result": "(1 1 1", "timed_out": False}, TOO_LONG)}
AW11 = {
    "autocad_status": counts(30, 31),
    "autocad_batch_draw": {"created": 1, "failed": 0, "handles": ["T"]},
    "autocad_get_entity": {"type": "text", "text": text.SENT},
}
AW12 = {
    "autocad_batch_draw": {"created": 1, "failed": 0, "handles": ["T"]},
    "autocad_get_entity": {"type": "text", "text": text.LANGUAGES, "style": "Standard"},
}
AW13 = {
    "autocad_status": counts(30, 30),
    "autocad_batch_draw": seq("Error: The text holds a NUL character, which cannot be sent to AutoCAD. Take it out and try again. Nothing was sent.",
                              "Error: The text holds the control character U+0085, which cannot be sent to AutoCAD. Nothing was sent."),
}
AW14 = {"autocad_run_lisp": {"result": "3", "timed_out": False}}
VIEWS = {"count": 1, "views": [{"name": "WEST"}]}
BA1 = {
    "autocad_list_views": seq(VIEWS, VIEWS),
    "autocad_save_view": seq(
        "Error: The view name holds a line break, which cannot be typed into AutoCAD's command line. Take it out and try again. Nothing was typed.",
        "Error: The view name holds an Esc character, which cannot be typed into AutoCAD's command line. Take it out and try again. Nothing was typed.",
        "Error: The view name holds a tab, which cannot be typed into AutoCAD's command line. Take it out and try again. Nothing was typed.",
    ),
}
MODEL = {"count": 2, "active": "Model", "layouts": [{"name": "Model"}, {"name": "Layout1"}]}
BA2 = {
    "autocad_list_layouts": MODEL,
    "autocad_save_view": seq({"saved": "LC-BA2-LIVING-3D", "replaced": False}, {"saved": "LC-BA2-LIVING-3D", "replaced": True},
                             {"saved": "LC-BA2-Café", "replaced": False}),
    "autocad_list_views": {"count": 2, "views": [{"name": "LC-BA2-LIVING-3D"}, {"name": "LC-BA2-Café"}]},
}
LAYERS = {"count": 3, "layers": []}
BF1 = {
    "autocad_list_layers": seq(LAYERS, LAYERS),
    "autocad_create_layer": seq(
        "Error: The layer name holds a line break, which cannot be typed into AutoCAD's command line. Take it out and try again. Nothing was typed.",
        "Error: The layer name holds a tab, which cannot be typed into AutoCAD's command line. Take it out and try again. Nothing was typed.",
        "Error: The layer name holds an Esc character, which cannot be typed into AutoCAD's command line. Take it out and try again. Nothing was typed.",
    ),
}
BF2 = {
    "autocad_create_layer": {"name": "LC-BF2-A-WALL", "created": True},
    "autocad_create_styles": {"text_styles": [{"name": "LC-BF2-TXT-1", "created": True}]},
}

SAMPLES = {
    "AW1": (AW1, {"autocad_run_lisp": seq(job("DONE - x", result="nil", timed_out=True), {"result": "3"})}),
    "AW2": (AW2, {"autocad_run_lisp": seq(AW2_ANSWER, {"result": "nil", "timed_out": False})}),
    "AW3": (AW3, {"autocad_run_lisp": {"result": None, "timed_out": False, "lisp_error": "bad argument type"}}),
    "AW4": (AW4, {"autocad_status": counts(30, 30, 31)}),
    "AW9": (AW9, {"autocad_run_lisp": seq({"result": "(1 1 1", "timed_out": False}, {"result": "(1 1", "timed_out": False})}),
    "AW11": (AW11, {"autocad_get_entity": {"type": "text", "text": "AB C D 5\" E\\F"}}),
    "AW12": (AW12, {"autocad_get_entity": {"type": "text", "text": "????? ????? café", "style": "Standard"}}),
    "AW13": (AW13, {"autocad_batch_draw": seq("Error: The text holds a NUL character. Nothing was sent.", "Error: bad text. Nothing was sent.")}),
    "AW14": (AW14, {"autocad_run_lisp": {"result": "nil", "timed_out": True}}),
    "BA1": (BA1, {"autocad_list_views": seq(VIEWS, {"count": 2, "views": [{"name": "WEST"}, {"name": "A"}]})}),
    "BA2": (BA2, {"autocad_save_view": seq({"saved": "x", "replaced": False}, {"saved": "x", "replaced": False}, {"saved": "y", "replaced": False})}),
    "BF1": (BF1, {"autocad_list_layers": seq(LAYERS, {"count": 4, "layers": []})}),
    "BF2": (BF2, {"autocad_create_styles": {"text_styles": [{"name": "LC-BF2-TXT-1", "created": False}]}}),
}
CHECKS = {c.row: c for c in text.CHECKS}


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


def test_the_lisp_rows_need_admin_and_the_others_do_not():
    needs_admin = {row for row, check in CHECKS.items() if "admin" in check.needs}
    assert needs_admin == {"AW1", "AW2", "AW3", "AW4", "AW9", "AW14"}


def test_the_control_characters_really_are_in_the_text_sent():
    assert "\x1b" in text.SENT and "\t" in text.SENT and "\n" in text.SENT


def test_the_two_forms_are_the_sizes_the_row_names():
    assert len(text._form(1700)) == 1700 and len(text._form(1800)) == 1800


def test_a_sheet_in_front_makes_ba2_not_run(monkeypatch):
    sheet = {**BA2, "autocad_list_layouts": {"count": 2, "active": "LC-A1", "layouts": []}}
    verdict = play(monkeypatch, CHECKS["BA2"], sheet)
    assert verdict.refused and "not run this time" in verdict.evidence and not verdict.called("autocad_save_view")


def test_aw13_names_each_character(monkeypatch):
    verdict = play(monkeypatch, CHECKS["AW13"], AW13)
    sent = [op["operations"][0]["text"] for op in verdict.called("autocad_batch_draw")]
    assert sent == ["A\x00B", "A\u0085B"]


def test_every_row_of_the_three_groups_is_measured_or_excused_once():
    assert not set(CHECKS) & set(text.BY_EYE)
    rows = set(CHECKS) | set(text.BY_EYE)
    assert rows == {f"AW{n}" for n in range(1, 15)} | {f"BA{n}" for n in range(1, 5)} | {"BF1", "BF2"}
