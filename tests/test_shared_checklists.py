"""Sharing check lists with the team (#135, D-93). No AutoCAD.

The office folder is set once per PC and read first; when it cannot be
reached a run says so and uses this PC's copy; a list Heron could not read is
never run. A project's changes kept in the project folder are the team's and
win. Writing either place is autocad_share_checklist (Publish), which never
overwrites a teammate's file silently.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from autocad_mcp.acad import checklist
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import checklist_share as share
from autocad_mcp.tools import checklists

CLEAN = {
    "layers": [{"name": "0"}, {"name": "M-DUCT"}],
    "entities": [{"handle": "B1", "type": "AcDbLine", "layer": "M-DUCT", "color": 256, "linetype": "ByLayer"}],
    "blocks": [{"handle": "T1", "name": "TITLE-A1", "attributes": {"DWG_NO": "M-101"}}],
    "xrefs_broken": [],
}  # fmt: skip
OFFICE_CHECKS = [{"check": "nothing_on_layer_0", "label": "Nothing on 0"}, {"check": "xrefs_found", "severity": "high"}]


async def _direct(fn):
    return fn()


class _Doc:
    def __init__(self, full_name: str):
        self.FullName = full_name


@pytest.fixture(autouse=True)
def _fresh_reach():
    checklists._unreachable.clear()
    yield
    checklists._unreachable.clear()


@pytest.fixture
def office(tmp_path):
    folder = tmp_path / "S-drive" / "CAD" / "Heron"
    folder.mkdir(parents=True)
    checklists.set_office_folder(str(folder))
    return folder


@pytest.fixture
def drawing(tmp_path, monkeypatch):
    path = tmp_path / "job" / "M-101.dwg"
    path.parent.mkdir()
    path.write_bytes(b"")
    for module in (checklists, share):
        monkeypatch.setattr(module, "run", _direct)
        monkeypatch.setattr(module, "get_doc", lambda: _Doc(str(path)))
    monkeypatch.setattr(checklists, "gather", lambda doc, wanted, most: CLEAN)
    return path


def put(folder: Path, name: str, checks, **extra):
    (folder / f"{checklists._slug(name)}.json").write_text(json.dumps({"name": name, "checks": checks, **extra}), encoding="utf-8")


def call(**kwargs):
    return asyncio.run(checklists.autocad_checklist(**kwargs))


def shared(**kwargs):
    return asyncio.run(share.autocad_share_checklist(**kwargs))


# ---- the office folder setting ----------------------------------------------


def test_the_office_folder_is_kept_per_pc_and_cleared_with_nothing(office):
    assert checklists.office_folder() == office
    shown = json.loads(call(action="office_folder"))
    assert shown["office_folder"] == str(office) and shown["reachable"] is True
    assert json.loads(call(action="office_folder", folder=""))["office_folder"] is None
    assert checklists.office_folder() is None


@pytest.mark.parametrize("folder, words", [("CAD\\Heron", "full path"), (None, "could not be reached")])
def test_a_wrong_office_folder_is_not_kept(folder, words, tmp_path):
    # None: a full path on this system (C:\... on Windows, /... elsewhere) to a folder that is not there.
    answer = call(action="office_folder", folder=folder or str(tmp_path / "no-such-share"))
    assert answer.startswith("Error:") and words in answer and "Nothing was kept" in answer
    assert checklists.office_folder() is None


def test_a_folder_that_hangs_is_called_unreachable_and_not_asked_again(monkeypatch, tmp_path):
    asked = []

    class Hanging(type(tmp_path)):
        def is_dir(self):
            asked.append(1)
            time.sleep(1)
            return True

    slow = Hanging(tmp_path)
    started = time.monotonic()
    assert checklists.reachable(slow, wait=0.05) is False and time.monotonic() - started < 0.9
    assert checklists.reachable(slow, wait=0.05) is False and len(asked) == 1  # believed for a minute


# ---- which list a run uses ---------------------------------------------------


def test_the_office_folder_list_wins_and_each_check_names_its_file(office, drawing):
    put(office, "before issue", OFFICE_CHECKS, saved_by="ravi", saved_at="2026-11-20 09:00")
    checklists.save("site", [{"check": "bylayer_colour"}])
    report = json.loads(call(action="run", name="before issue"))
    assert report["lists"]["office"] == str(office / "before-issue.json") and report["lists"]["office_from"] == "office folder"
    assert {row["file"] for row in report["results"]} == {str(office / "before-issue.json")}
    assert {c["id"] for c in report["checks_used"]} == {"nothing_on_layer_0", "xrefs_found"}  # not the shipped five
    assert "warning" not in report
    # A list the office folder does not have is this PC's own.
    assert json.loads(call(action="list", name="site"))["where"] == "this PC"


def test_without_an_office_folder_nothing_changes(drawing):
    report = json.loads(call(action="run", name="before issue"))
    assert report["lists"]["office"] == "ships with Heron" and report["lists"]["office_from"] == "ships with Heron"


def test_an_unreachable_office_folder_uses_this_pcs_copy_and_says_so(office, drawing, monkeypatch):
    put(office, "before issue", OFFICE_CHECKS)
    call(action="run", name="before issue")  # read once: a copy is kept
    monkeypatch.setattr(checklists, "reachable", lambda folder, wait=0: False)
    report = json.loads(call(action="run", name="before issue"))
    assert report["lists"]["office_from"] == "this PC's copy of the office list"
    assert "could not be reached" in report["warning"] and f"read from {office / 'before-issue.json'} on" in report["warning"]
    assert {c["id"] for c in report["checks_used"]} == {"nothing_on_layer_0", "xrefs_found"}


def test_a_copy_from_an_office_folder_set_before_is_never_run(office, drawing, monkeypatch, tmp_path):
    # Found in review: folder A's copy must not stand in for folder B's list.
    put(office, "mep", OFFICE_CHECKS)
    call(action="run", name="mep")  # a copy of A's list is kept
    other = tmp_path / "T-drive" / "Heron"
    other.mkdir(parents=True)
    checklists.set_office_folder(str(other))
    monkeypatch.setattr(checklists, "reachable", lambda folder, wait=0: False)
    answer = call(action="run", name="mep")
    assert answer.startswith("Error:") and "no check list called 'mep'" in answer


def test_a_folder_check_keeps_each_runs_warning_and_names_the_list():
    from autocad_mcp.acad import folder_check

    report = {"verdict": "PASS", "coverage": "1 of 1 decided, 0 no data, 0 not run", "results": [],
              "warning": "The office folder S:\\Heron could not be reached.",
              "lists": {"project_file": "D:\\Job\\Heron check list changes.json"}}  # fmt: skip
    line = folder_check.short(report, "M-101.dwg")
    assert line["warning"] == report["warning"] and line["project_changes"].endswith("changes.json")
    assert "warning" not in folder_check.short({**report, "warning": None}, "M-101.dwg")


def test_the_folder_check_answer_says_which_list_ran(office, monkeypatch, tmp_path):
    from autocad_mcp.tools import check_folder

    jobs = tmp_path / "issue"
    jobs.mkdir()
    (jobs / "A-101.dwg").write_bytes(b"x")
    monkeypatch.setattr(checklists, "reachable", lambda folder, wait=0: False)
    warning = "The office folder could not be reached. This PC's own list of that name was used."

    async def run_list(name, most, doc_of=None):
        return {"verdict": "PASS", "coverage": "1 of 1 decided", "results": [], "warning": warning}, "A-101.dwg"

    async def now(fn):
        return fn()

    monkeypatch.setattr(check_folder, "run", now)
    monkeypatch.setattr(check_folder, "_active", lambda: None)
    monkeypatch.setattr(check_folder, "_open_read_only", lambda path: (object(), False))
    monkeypatch.setattr(check_folder, "_back_to", lambda original: None)
    monkeypatch.setattr(checklists, "run_list", run_list)
    answer = json.loads(asyncio.run(check_folder.autocad_check_folder(folder=str(jobs))))
    assert answer["worst"] == "PASS" and answer["drawings"][0]["warning"] == warning
    assert answer["list"] == {"file": "ships with Heron", "from": "ships with Heron"}
    assert "could not be reached" in answer["warning"]


def test_project_changes_are_not_shared_against_a_stand_in_list(office, drawing, monkeypatch):
    # Found in review: with the office folder unreachable the changes cannot be checked against its list.
    monkeypatch.setattr(checklists, "reachable", lambda folder, wait=0: False)
    answer = shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    assert answer.startswith("Error:") and "cannot check these changes against the office list" in answer
    assert not (drawing.parent / checklists.PROJECT_FILE).exists()


def test_an_unreachable_office_folder_with_no_copy_says_which_list_ran(office, drawing, monkeypatch):
    monkeypatch.setattr(checklists, "reachable", lambda folder, wait=0: False)
    checklists.save("sheets", [{"check": "nothing_on_layer_0"}])
    report = json.loads(call(action="run", name="sheets"))
    assert report["lists"]["office_from"] == "this PC" and "This PC's own list of that name was used" in report["warning"]
    answer = call(action="run", name="pipework")
    assert answer.startswith("Error:") and "could not be reached" in answer and "nothing was run" in answer


def test_an_office_list_that_cannot_be_read_is_never_run(office, drawing):
    (office / "before-issue.json").write_text("{ half written", encoding="utf-8")
    answer = call(action="run", name="before issue")
    assert answer.startswith("Error:") and "could not be read" in answer and "nothing was run" in answer


def test_an_office_list_that_cannot_be_read_falls_back_to_the_copy(office, drawing):
    put(office, "before issue", OFFICE_CHECKS)
    call(action="run", name="before issue")
    put(office, "before issue", [{"check": "a_check_heron_does_not_have"}])
    report = json.loads(call(action="run", name="before issue"))
    assert report["lists"]["office_from"] == "this PC's copy of the office list"
    assert "could not be read" in report["warning"]


def test_the_list_shows_where_each_list_lives(office, drawing):
    put(office, "before issue", OFFICE_CHECKS)
    checklists.save("mine", [{"check": "bylayer_colour"}])
    listed = json.loads(call(action="list"))
    assert {"name": "before issue", "checks": 2} in listed["lists"] and listed["office_folder"] == str(office)
    assert listed["where"]["before issue"]["where"] == "office folder" and listed["where"]["mine"]["where"] == "this PC"


def test_saving_on_this_pc_under_an_office_name_is_refused(office):
    put(office, "before issue", OFFICE_CHECKS)
    answer = call(action="save", name="before issue", checks=[{"check": "bylayer_colour"}])
    assert answer.startswith("Error:") and "autocad_share_checklist" in answer and "Nothing was saved" in answer
    saved = json.loads(call(action="save", name="my checks", checks=[{"check": "bylayer_colour"}]))
    assert saved["where"] == "this PC" and "autocad_share_checklist" in saved["share"]


def test_delete_removes_only_this_pcs_list(office):
    put(office, "before issue", OFFICE_CHECKS)
    answer = call(action="delete", name="before issue")
    assert answer.startswith("Error:") and "Heron does not delete it" in answer
    assert (office / "before-issue.json").is_file()


# ---- sharing the office list ---------------------------------------------------


def test_share_needs_an_office_folder():
    answer = shared(share="office_list", name="before issue")
    assert answer.startswith("Error:") and "No office folder is set" in answer and "Nothing was written" in answer


def test_a_pcs_own_list_goes_to_the_office_folder_with_who_and_when(office, monkeypatch):
    monkeypatch.setattr(share, "who", lambda: "ajmal")
    checklists._file("mep").parent.mkdir(parents=True, exist_ok=True)
    checklists._file("mep").write_text(json.dumps({"name": "MEP", "checks": checklist.validate(OFFICE_CHECKS)}))
    answer = json.loads(shared(share="office_list", name="MEP"))
    assert answer["written"] is True and answer["replaced"] is False and answer["from"].startswith("this PC's list")
    held = json.loads((office / "mep.json").read_text())
    assert held["saved_by"] == "ajmal" and held["saved_at"] and [c["id"] for c in held["checks"]] == ["nothing_on_layer_0", "xrefs_found"]
    again = json.loads(shared(share="office_list", name="MEP"))
    assert again["written"] is False and "already holds exactly" in again["said"]


def test_the_shipped_list_can_be_shared_as_it_is(office):
    answer = json.loads(shared(share="office_list"))
    assert answer["list"] == "before issue" and (office / "before-issue.json").is_file()


def test_a_teammates_different_list_is_never_overwritten_silently(office, monkeypatch):
    put(office, "before issue", checklist.validate(OFFICE_CHECKS), saved_by="ravi", saved_at="2026-11-20 09:00")
    before = (office / "before-issue.json").read_text()
    answer = shared(share="office_list", name="before issue", checks=[{"check": "nothing_on_layer_0"}, {"check": "bylayer_colour"}])
    assert answer.startswith("Error:") and "saved by ravi on 2026-11-20 09:00" in answer
    assert "yours adds bylayer_colour" in answer and "yours removes xrefs_found" in answer and "replace=true" in answer
    assert (office / "before-issue.json").read_text() == before
    monkeypatch.setattr(share, "who", lambda: "ajmal")
    done = json.loads(shared(share="office_list", name="before issue", checks=[{"check": "bylayer_colour"}], replace=True))
    held = json.loads((office / "before-issue.json").read_text())
    assert done["replaced"] is True and held["saved_by"] == "ajmal"
    assert held["previous"]["saved_by"] == "ravi" and [c["id"] for c in held["previous"]["checks"]] == ["nothing_on_layer_0", "xrefs_found"]
    # One step back only: the previous never piles up inside itself.
    shared(share="office_list", name="before issue", checks=[{"check": "xrefs_found"}], replace=True)
    assert "previous" not in json.loads((office / "before-issue.json").read_text())["previous"]


def test_an_unreadable_file_there_is_kept_word_for_word_when_replaced(office):
    (office / "before-issue.json").write_text("not json at all", encoding="utf-8")
    refused = shared(share="office_list", name="before issue")
    assert refused.startswith("Error:") and "cannot be read as a check list" in refused
    shared(share="office_list", name="before issue", replace=True)
    assert json.loads((office / "before-issue.json").read_text())["previous"] == {"unreadable_text": "not json at all"}


def test_a_file_a_teammate_saves_while_writing_is_left_alone(office, monkeypatch):
    stamps = iter([(1, 10), (2, 11)])  # read once, then changed before the swap
    monkeypatch.setattr(share, "_stamp", lambda path: next(stamps))
    put(office, "before issue", checklist.validate(OFFICE_CHECKS))
    answer = shared(share="office_list", name="before issue", checks=[{"check": "bylayer_colour"}], replace=True)
    assert answer.startswith("Error:") and "changed while Heron was writing" in answer
    assert [c["id"] for c in json.loads((office / "before-issue.json").read_text())["checks"]] == ["nothing_on_layer_0", "xrefs_found"]
    assert not list(office.glob(".*heron-tmp"))


def test_a_read_only_office_folder_says_who_can_change_it(office, monkeypatch):
    def refuse(src, dst):
        raise PermissionError("read-only")

    monkeypatch.setattr(share.os, "replace", refuse)
    answer = shared(share="office_list", name="before issue")
    assert answer.startswith("Error:") and "read-only for you, or the file is open in another program" in answer
    assert not list(office.glob("*.json"))
    assert not list(office.glob(".*heron-tmp"))


def test_an_unreachable_office_folder_writes_nothing(office, monkeypatch):
    monkeypatch.setattr(checklists, "reachable", lambda folder, wait=0: False)
    answer = shared(share="office_list", name="before issue")
    assert answer.startswith("Error:") and "could not be reached" in answer


def test_a_wrong_check_is_refused_naming_it(office):
    answer = shared(share="office_list", name="x", checks=[{"check": "nope"}])
    assert answer.startswith("Error:") and "'nope' is not a check Heron has" in answer and not list(office.glob("*.json"))


# ---- a project's changes, kept with the project -----------------------------


def test_project_changes_go_to_the_drawing_folder_and_every_run_uses_them(drawing):
    answer = json.loads(shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}]))
    target = drawing.parent / checklists.PROJECT_FILE
    assert answer["file"] == str(target) and answer["written"] is True
    report = json.loads(call(action="run", name="before issue"))
    row = next(r for r in report["results"] if r["id"] == "xrefs_found")
    assert row["state"] == "NOT RUN" and row["from"] == "project" and row["file"] == str(target)
    assert report["lists"]["project_file"] == str(target) and report["lists"]["project_from"] == "the project folder"
    shown = json.loads(call(action="project", name="before issue"))
    assert shown["from"] == "the project folder" and shown["file"] == str(target)


def test_this_pcs_own_changes_can_be_shared_as_they_are(drawing):
    call(action="project", name="before issue", changes=[{"id": "bylayer_colour", "severity": "high"}])
    answer = json.loads(shared(share="project_changes", name="before issue"))
    assert answer["from"] == "this PC's own changes for this project" and answer["changes"] == [{"id": "bylayer_colour", "severity": "high"}]


def test_nothing_to_share_says_so(drawing):
    answer = shared(share="project_changes", name="before issue")
    assert answer.startswith("Error:") and "nothing to share" in answer


def test_the_project_folder_wins_over_this_pc_and_says_when_they_differ(drawing):
    call(action="project", name="before issue", changes=[{"id": "bylayer_colour", "severity": "high"}])
    shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    report = json.loads(call(action="run", name="before issue"))
    assert next(r for r in report["results"] if r["id"] == "bylayer_colour")["severity"] == "low"
    assert "the project folder's file" in report["warning"]


def test_a_change_kept_on_this_pc_only_is_refused_once_the_team_has_one(drawing):
    shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    answer = call(action="project", name="before issue", changes=[{"id": "xrefs_found", "on": True}])
    assert answer.startswith("Error:") and "for the whole team" in answer and "Nothing was kept" in answer


def test_a_teammates_project_changes_are_replaced_only_when_asked(drawing, monkeypatch):
    monkeypatch.setattr(share, "who", lambda: "ravi")
    shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    monkeypatch.setattr(share, "who", lambda: "ajmal")
    answer = shared(share="project_changes", name="before issue", changes=[{"id": "bylayer_colour", "severity": "high"}])
    assert answer.startswith("Error:") and "saved by ravi" in answer and '"xrefs_found"' in answer
    shared(share="project_changes", name="before issue", changes=[{"id": "bylayer_colour", "severity": "high"}], replace=True)
    held = json.loads((drawing.parent / checklists.PROJECT_FILE).read_text())
    assert held["changes"]["before-issue"] == [{"id": "bylayer_colour", "severity": "high"}]
    assert held["previous"]["saved_by"] == "ravi"
    # [] removes the project's changes to that list, other lists stay.
    shared(share="project_changes", name="before issue", changes=[], replace=True)
    assert "before-issue" not in json.loads((drawing.parent / checklists.PROJECT_FILE).read_text())["changes"]


def test_changes_to_another_list_in_the_same_file_are_kept(drawing):
    checklists.save("sheets", [{"check": "nothing_on_layer_0"}])
    shared(share="project_changes", name="sheets", changes=[{"id": "nothing_on_layer_0", "severity": "high"}])
    shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    held = json.loads((drawing.parent / checklists.PROJECT_FILE).read_text())
    assert set(held["changes"]) == {"sheets", "before-issue"}


def test_a_project_file_that_cannot_be_read_stops_the_run(drawing):
    (drawing.parent / checklists.PROJECT_FILE).write_text("{ broken", encoding="utf-8")
    answer = call(action="run", name="before issue")
    assert answer.startswith("Error:") and "could not be read" in answer and "Nothing was run" in answer
    refused = shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    assert refused.startswith("Error:") and "left as it is" in refused


def test_a_project_change_that_adds_a_check_is_refused(drawing):
    answer = shared(share="project_changes", name="before issue", changes=[{"id": "my_new_check", "on": True}])
    assert answer.startswith("Error:") and "cannot add one" in answer and "Nothing was written" in answer
    assert not (drawing.parent / checklists.PROJECT_FILE).exists()


def test_an_unsaved_drawing_has_no_project_folder_to_share_to(drawing, monkeypatch):
    monkeypatch.setattr(share, "get_doc", lambda: _Doc(""))
    answer = shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    assert answer.startswith("Error:") and "not saved yet" in answer


def test_the_saved_report_names_the_files_the_checks_came_from(office, drawing):
    from autocad_mcp.acad import checklist_report, xlsx

    put(office, "before issue", OFFICE_CHECKS)
    shared(share="project_changes", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    report = json.loads(call(action="run", name="before issue"))
    sheets = xlsx.read(checklist_report.workbook(report, str(drawing), "2026-11-21 10:00"))
    summary = {row[0]: row[1] for row in sheets["Summary"][1:]}
    assert summary["Office list"] == f"{office / 'before-issue.json'} (office folder)"
    assert summary["Project changes"] == str(drawing.parent / checklists.PROJECT_FILE)
    assert str(office / "before-issue.json") in checklist_report.page(report, str(drawing), "now")


# ---- padlocks -------------------------------------------------------------------


def test_sharing_needs_the_publish_padlock_and_reading_needs_none():
    assert risk_of("autocad_share_checklist") is Risk.PUBLISH
    assert risk_of("autocad_checklist") is Risk.READ


def test_the_errors_are_plain_autocad_errors():
    with pytest.raises(AutocadError):
        checklists.set_office_folder("relative\\folder")
