"""Check lists (D-52), project notes (D-53), activity and undo-last (D-54). No AutoCAD."""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad import checklist
from autocad_mcp.core import gate, project_notes
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import activity, checklists
from autocad_mcp.tools import project_notes as notes_tool

# ---------------------------------------------------------------------------
# Check lists
# ---------------------------------------------------------------------------

DATA = {
    "layers": [{"name": "0"}, {"name": "M-DUCT"}, {"name": "mech pipes"}, {"name": "Defpoints"}],
    "entities": [
        {"handle": "A1", "type": "AcDbLine", "layer": "0", "color": 256, "linetype": "ByLayer"},
        {"handle": "A2", "type": "AcDbLine", "layer": "M-DUCT", "color": 1, "linetype": "ByLayer"},
        {"handle": "A3", "type": "AcDbText", "layer": "M-DUCT", "color": 256, "linetype": "ByLayer", "height": 4.0},
        {"handle": "A4", "type": "AcDbRotatedDimension", "layer": "M-DUCT", "color": 256, "linetype": "ByLayer", "box": (0, 0, 10, 2)},
        {"handle": "A5", "type": "AcDbRotatedDimension", "layer": "M-DUCT", "color": 256, "linetype": "ByLayer", "box": (0, 0, 10, 2)},
        {"handle": "A6", "type": "AcDbLine", "layer": "Defpoints", "color": 256, "linetype": "ByLayer"},
        {"handle": "VP", "type": "AcDbViewport", "layer": "Defpoints", "color": 256, "linetype": "ByLayer"},
    ],
    "blocks": [
        {"handle": "T1", "name": "TITLE-A1", "attributes": {"DWG_NO": "M-101", "DATE": ""}},
        {"handle": "T2", "name": "TITLE-A1", "attributes": {"DWG_NO": "M-102", "DATE": "2026-11-15"}},
    ],
    "xrefs_broken": ["ARCH-BASE"],
}  # fmt: skip


def _result(checks, data=DATA):
    report = checklist.run("test", checklist.validate(checks), data)
    return {row["check"]: row for row in report["results"]}, report


def test_each_check_finds_what_its_sentence_says():
    rows, report = _result([
        {"check": "nothing_on_layer_0"}, {"check": "nothing_on_defpoints"}, {"check": "bylayer_colour"},
        {"check": "no_overlapping_dimensions"}, {"check": "xrefs_found"},
        {"check": "layer_names", "params": {"pattern": "^[A-Z]-"}},
        {"check": "title_block_filled", "params": {"block": "TITLE*"}},
        {"check": "text_heights", "params": {"heights": [2.5, 3.5, 5]}},
    ])  # fmt: skip
    assert rows["nothing_on_layer_0"]["handles"] == ["A1"]
    assert rows["nothing_on_defpoints"]["handles"] == ["A6"]  # a viewport on Defpoints is normal
    assert rows["bylayer_colour"]["handles"] == ["A2"]
    assert rows["no_overlapping_dimensions"]["handles"] == ["A5"]
    assert rows["xrefs_found"]["names"] == ["ARCH-BASE"]
    assert rows["layer_names"]["names"] == ["mech pipes"]
    assert rows["title_block_filled"]["handles"] == ["T1"]
    assert rows["text_heights"]["handles"] == ["A3"]
    assert report["verdict"] == "FAIL"


def test_a_clean_drawing_passes():
    clean = {"layers": [{"name": "0"}], "entities": [{"handle": "B1", "type": "AcDbLine", "layer": "M-X", "color": 256,
             "linetype": "ByLayer"}], "blocks": [], "xrefs_broken": []}  # fmt: skip
    _, report = _result(checklist.STARTER["checks"], clean)
    assert report["verdict"] == "PASS" and report["counts"]["PASS"] == 5


def test_a_check_that_cannot_be_judged_is_no_data_never_a_silent_pass():
    # Was NOT RUN until D-64: a missing title block is missing data (#84).
    rows, report = _result([{"check": "title_block_filled", "params": {"block": "SHEET*"}}])
    assert rows["title_block_filled"]["state"] == "NO DATA"
    assert "no block named SHEET*" in rows["title_block_filled"]["note"]
    assert report["verdict"] == "NO DATA"


def test_failures_come_first_and_carry_the_modellers_advice():
    _, report = _result([
        {"check": "nothing_on_defpoints", "severity": "high", "advice": "Defpoints never plots.", "clause": "Office std 4.2"},
        {"check": "layer_names", "params": {"pattern": "."}, "severity": "low"},
    ])  # fmt: skip
    first = report["results"][0]
    assert first["state"] == "FAIL" and first["advice"] == "Defpoints never plots." and first["clause"] == "Office std 4.2"


@pytest.mark.parametrize(
    "bad, words",
    [
        ({"check": "nothing_on_layer_zero"}, "not a check Heron has"),
        ({"check": "layer_names"}, "needs 'pattern'"),
        ({"check": "layer_names", "params": {"pattern": "("}}, "regular expression"),
        ({"check": "text_heights", "params": {"heights": []}}, "positive numbers"),
        ({"check": "xrefs_found", "severity": "urgent"}, "severity"),
    ],
)
def test_a_wrong_line_is_refused_naming_it(bad, words):
    with pytest.raises(ValueError) as caught:
        checklist.validate([{"check": "xrefs_found"}, bad])
    assert "Check 2" in str(caught.value) and words in str(caught.value)


def test_lists_are_saved_listed_run_and_deleted(monkeypatch):
    saved = json.loads(asyncio.run(checklists.autocad_checklist(
        action="save", name="MEP sheets", checks=[{"check": "nothing_on_layer_0", "label": "nothing on 0"}])))  # fmt: skip
    assert saved["saved"] == "MEP sheets" and saved["checks"] == 1
    listed = json.loads(asyncio.run(checklists.autocad_checklist(action="list")))
    assert {"name": "MEP sheets", "checks": 1} in listed["lists"]

    async def direct(fn):
        return fn()

    monkeypatch.setattr(checklists, "run", direct)
    monkeypatch.setattr(checklists, "get_doc", lambda: object())
    monkeypatch.setattr(checklists, "gather", lambda doc, wanted, most: DATA)
    report = json.loads(asyncio.run(checklists.autocad_checklist(action="run", name="mep sheets")))
    assert report["results"][0]["label"] == "nothing on 0" and report["results"][0]["handles"] == ["A1"]
    asyncio.run(checklists.autocad_checklist(action="delete", name="MEP sheets"))
    assert json.loads(asyncio.run(checklists.autocad_checklist(action="list")))["lists"] == []


def test_the_starter_list_runs_without_being_saved(monkeypatch):
    async def direct(fn):
        return fn()

    monkeypatch.setattr(checklists, "run", direct)
    monkeypatch.setattr(checklists, "get_doc", lambda: object())
    monkeypatch.setattr(checklists, "gather", lambda doc, wanted, most: DATA)
    report = json.loads(asyncio.run(checklists.autocad_checklist(action="run", name="before issue")))
    assert report["checklist"] == "before issue" and len(report["results"]) == 5


def test_saving_a_wrong_list_saves_nothing():
    result = asyncio.run(checklists.autocad_checklist(action="save", name="x", checks=[{"check": "nope"}]))
    assert result.startswith("Error:") and "Nothing was saved" in result
    assert not checklists.lists_dir().exists() or not list(checklists.lists_dir().glob("*.json"))


def test_checklist_and_notes_need_no_padlock():
    for name in ("autocad_checklist", "autocad_project_notes", "autocad_activity"):
        assert risk_of(name) is Risk.READ
    assert risk_of("autocad_undo_last") is Risk.CHANGE


# ---------------------------------------------------------------------------
# Project notes
# ---------------------------------------------------------------------------


def test_a_project_is_its_folder_and_two_folders_never_share():
    project_notes.write(r"C:\Jobs\4355\M-101.dwg", "scale", "1:50", said="it's 1:50 for this job")
    assert project_notes.for_status(r"C:\Jobs\4355\M-102.dwg") == {"scale": "1:50"}
    assert project_notes.for_status(r"C:\Jobs\4400\M-101.dwg") is None
    note = project_notes.read(r"C:\Jobs\4355\X.dwg")["notes"]["scale"]
    assert note["said"] == "it's 1:50 for this job"


def test_an_unsaved_drawing_keeps_nothing():
    assert project_notes.read("Drawing1.dwg") is None
    with pytest.raises(ValueError) as caught:
        project_notes.write("Drawing1.dwg", "scale", "1:50")
    assert "not saved yet" in str(caught.value)


def test_a_note_can_be_forgotten_and_names_are_checked():
    project_notes.write(r"C:\Jobs\1\a.dwg", "Text Height", "2.5")
    assert project_notes.for_status(r"C:\Jobs\1\a.dwg") == {"text_height": "2.5"}
    project_notes.write(r"C:\Jobs\1\a.dwg", "text_height", None)
    assert project_notes.for_status(r"C:\Jobs\1\a.dwg") is None
    with pytest.raises(ValueError):
        project_notes.write(r"C:\Jobs\1\a.dwg", "1:50 scale!", "x")


def test_the_tool_reads_the_active_drawings_project(monkeypatch):
    class Doc:
        FullName = r"C:\Jobs\77\M-01.dwg"
        Name = "M-01.dwg"

    async def direct(fn):
        return fn()

    monkeypatch.setattr(notes_tool, "run", direct)
    monkeypatch.setattr(notes_tool, "get_doc", lambda: Doc())
    kept = json.loads(asyncio.run(notes_tool.autocad_project_notes(action="keep", name="standard", value="ISO 19650")))
    assert kept["notes"]["standard"]["value"] == "ISO 19650"
    listed = json.loads(asyncio.run(notes_tool.autocad_project_notes()))
    assert "standard" in listed["notes"]


def test_status_hands_the_notes_to_the_next_chat():
    project_notes.write(r"C:\a\x.dwg", "scale", "1:100")

    class Bridge:
        def find(self):
            return {"addinVersion": "1.5.0"}

    job = gate.Job("autocad_status", Risk.READ, "status", r"C:\a\x.dwg", Bridge(), "j1", False, 0.0)
    state = gate._versions({"connected": True}, job)
    assert state["project_notes"] == {"scale": "1:100"} and state["plugin_version"] == "1.5.0"


# ---------------------------------------------------------------------------
# Activity and undo-last
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(gate, "_last_change", None)
    monkeypatch.setattr(gate, "_activity", gate.deque(maxlen=50))


def _job(tool="autocad_draw_line", risk=Risk.CHANGE, drawing=r"C:\a.dwg"):
    return gate.Job(tool, risk, tool.removeprefix("autocad_"), drawing, None, "j", False, 0.0)


def test_a_kept_change_becomes_the_last_change_and_a_zoom_is_counted(fresh):
    gate._remember("autocad_draw_line", Risk.CHANGE, r"C:\a.dwg", True, "done", 0.0, _job(),
                   '{"created": true, "handle": "2A"}', None, True, False)  # fmt: skip
    assert gate.last_change()["created"] == ["2A"]
    gate._remember("autocad_zoom", Risk.VIEW, r"C:\a.dwg", True, "done", 0.0, _job("autocad_zoom", Risk.VIEW), "{}", None, False, False)
    assert gate.last_change()["views_since"] == 1
    assert [job["tool"] for job in gate.activity()] == ["autocad_zoom", "autocad_draw_line"]


def test_a_discard_or_a_raw_command_leaves_nothing_to_undo(fresh):
    gate._remember("autocad_draw_line", Risk.CHANGE, r"C:\a.dwg", True, "discarded", 0.0, _job(), "{}", None, True, True)
    assert gate.last_change() is None
    gate._remember("autocad_draw_line", Risk.CHANGE, r"C:\a.dwg", True, "done", 0.0, _job(), "{}", None, True, False)
    gate._remember("autocad_send_command", Risk.ADMIN, r"C:\a.dwg", True, "done", 0.0, _job("autocad_send_command", Risk.ADMIN), "{}", None, True, False)
    assert gate.last_change() is None


def test_reads_are_not_in_the_activity_list(fresh):
    gate._remember("autocad_list_layers", Risk.READ, r"C:\a.dwg", True, "done", 0.0, _job("autocad_list_layers", Risk.READ), "[]", None, False, False)
    assert gate.activity() == []


@pytest.fixture
def undoable(fresh, monkeypatch):
    class Doc:
        FullName = r"C:\a.dwg"
        Name = "a.dwg"
        sent: list = []
        gone = True

        def SendCommand(self, text):
            Doc.sent.append(text)

        def HandleToObject(self, handle):
            if Doc.gone:
                raise KeyError(handle)
            return object()

    Doc.sent = []
    Doc.gone = True

    async def direct(fn):
        return fn()

    monkeypatch.setattr(activity, "run", direct)
    monkeypatch.setattr(activity, "get_doc", lambda: Doc())
    monkeypatch.setattr(gate, "changed_by_modeller_since", lambda: False)
    gate._remember("autocad_draw_line", Risk.CHANGE, r"C:\a.dwg", True, "done", 0.0, _job(),
                   '{"created": true, "handle": "2A"}', None, True, False)  # fmt: skip
    return Doc


def test_undo_last_takes_back_heron_s_change(undoable):
    result = json.loads(asyncio.run(activity.autocad_undo_last()))
    assert undoable.sent == ["_.UNDO 1 "] and result["removed"] == ["2A"]


def test_undo_last_uses_the_mark_when_there_is_one(undoable):
    gate._last_change["marked"] = True
    gate._last_change["views_since"] = 2
    asyncio.run(activity.autocad_undo_last())
    assert undoable.sent == ["_.UNDO _Back "]


def test_undo_last_refuses_when_the_modeller_changed_something_since(undoable, monkeypatch):
    monkeypatch.setattr(gate, "changed_by_modeller_since", lambda: True)
    result = asyncio.run(activity.autocad_undo_last())
    assert "your own work" in result and undoable.sent == []


def test_undo_last_refuses_after_a_zoom_without_a_mark(undoable):
    gate._last_change["views_since"] = 1
    result = asyncio.run(activity.autocad_undo_last())
    assert "zoomed" in result and undoable.sent == []


def test_undo_last_refuses_with_an_older_plug_in(undoable, monkeypatch):
    monkeypatch.setattr(gate, "changed_by_modeller_since", lambda: None)
    assert "1.5.0" in asyncio.run(activity.autocad_undo_last())


def test_undo_last_in_another_drawing_is_refused(undoable):
    gate._last_change["drawing"] = r"C:\b.dwg"
    assert "Switch back" in asyncio.run(activity.autocad_undo_last())


def test_an_undo_that_did_not_take_says_outcome_unknown(undoable):
    undoable.gone = False
    assert "Outcome unknown" in asyncio.run(activity.autocad_undo_last())


def test_nothing_to_undo_says_so(fresh):
    assert "no change of its own to undo" in asyncio.run(activity.autocad_undo_last())
