"""Check lists for QA (#84-#87, D-64, D-65). No AutoCAD.

NO DATA is never a PASS, every run carries a coverage line, a project may
only change severity, target and on/off of an office check, a report never
overwrites an earlier one, and no answer says a drawing complies.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path

import pytest

from autocad_mcp.acad import checklist, checklist_report
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import checklists, standards

ROOT = Path(__file__).resolve().parents[1]

CLEAN = {
    "layers": [{"name": "0"}, {"name": "M-DUCT"}],
    "entities": [
        {"handle": "B1", "type": "AcDbLine", "layer": "M-DUCT", "color": 256, "linetype": "ByLayer"},
        {"handle": "B2", "type": "AcDbText", "layer": "M-DUCT", "color": 256, "linetype": "ByLayer", "height": 2.5},
    ],
    "blocks": [{"handle": "T1", "name": "TITLE-A1", "attributes": {"DWG_NO": "M-101"}}],
    "xrefs_broken": [],
}  # fmt: skip

OFFICE = [
    {"check": "nothing_on_layer_0", "label": "Nothing on layer 0", "severity": "medium"},
    {"check": "bylayer_colour", "label": "Colours ByLayer", "severity": "low", "clause": "Office CAD std 3.1"},
    {"check": "title_block_filled", "params": {"block": "TITLE*"}, "severity": "high"},
    {"check": "xrefs_found", "severity": "high"},
    {"check": "text_heights", "params": {"heights": [2.5, 3.5]}},
]  # fmt: skip


def _rows(report):
    return {row["id"]: row for row in report["results"]}


# ---------------------------------------------------------------------------
# #84 NO DATA and the coverage line
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data, check, why",
    [
        ({**CLEAN, "blocks": []}, {"check": "title_block_filled", "params": {"block": "TITLE*"}}, "no block named"),
        ({**CLEAN, "xrefs_broken": None}, {"check": "xrefs_found"}, "could not be read"),
        ({**CLEAN, "entities": None}, {"check": "nothing_on_layer_0"}, "could not be read"),
        ({**CLEAN, "entities": CLEAN["entities"][:1]}, {"check": "text_heights", "params": {"heights": [2.5]}}, "no text"),
        ({**CLEAN, "capped": 1}, {"check": "nothing_on_layer_0"}, "only the first 1 objects"),
    ],
)
def test_missing_data_is_no_data_and_never_a_pass(data, check, why):
    # The second check reads only the layers, so it is decided whatever is missing.
    report = checklist.run("t", checklist.validate([check, {"check": "layer_names", "params": {"pattern": "."}}]), data)
    row = _rows(report)[check["check"]]
    assert row["state"] == checklist.NO_DATA and why in row["note"]
    assert report["counts"]["PASS"] == 1 and report["counts"]["NO DATA"] == 1
    assert report["verdict"] == "NO DATA"  # one PASS beside a NO DATA is not a PASS


def test_a_failure_found_in_part_of_the_drawing_is_still_a_failure():
    data = {**CLEAN, "capped": 2, "entities": [{**CLEAN["entities"][0], "layer": "0"}]}
    report = checklist.run("t", checklist.validate([{"check": "nothing_on_layer_0"}]), data)
    assert report["results"][0]["state"] == "FAIL" and report["verdict"] == "FAIL"


def test_the_coverage_line_counts_each_result():
    office = checklist.validate(OFFICE[:4])
    used = checklist.layer(office, checklist.validate_changes(office, [{"id": "xrefs_found", "on": False}]))
    data = {**CLEAN, "blocks": [], "entities": [{**CLEAN["entities"][0], "layer": "0"}]}
    report = checklist.run("t", used, data)
    assert report["coverage"] == "2 of 4 decided, 1 no data, 1 not run"
    assert report["counts"] == {"PASS": 1, "FAIL": 1, "NO DATA": 1, "NOT RUN": 1}
    assert [r["state"] for r in report["results"]] == ["FAIL", "NO DATA", "NOT RUN", "PASS"]


@pytest.mark.parametrize(
    "counts, line, verdict",
    [
        ({"PASS": 4}, "4 of 4 decided, 0 no data, 0 not run", "PASS"),
        ({"PASS": 3, "NOT RUN": 1}, "3 of 4 decided, 0 no data, 1 not run", "PASS"),
        ({"PASS": 3, "NO DATA": 1}, "3 of 4 decided, 1 no data, 0 not run", "NO DATA"),
        ({"PASS": 1, "FAIL": 1, "NO DATA": 2}, "2 of 4 decided, 2 no data, 0 not run", "FAIL"),
        ({"NOT RUN": 2}, "0 of 2 decided, 0 no data, 2 not run", "NOT RUN"),
        ({"NO DATA": 1}, "0 of 1 decided, 1 no data, 0 not run", "NO DATA"),
    ],
)
def test_coverage_arithmetic_and_the_verdict(counts, line, verdict):
    assert checklist.coverage(counts) == line
    assert checklist.verdict_of(counts) == verdict


def test_a_switched_off_check_reads_nothing_from_the_drawing():
    office = checklist.validate([{"check": "xrefs_found"}, {"check": "title_block_filled", "params": {"block": "T*"}}])
    used = checklist.layer(office, [{"id": "xrefs_found", "on": False}, {"id": "title_block_filled", "on": False}])
    assert checklist.needs(used) == {"layers"}


# ---------------------------------------------------------------------------
# #85 office list, project changes on top
# ---------------------------------------------------------------------------


def test_project_changes_severity_target_and_on_and_says_so():
    office = checklist.validate(OFFICE)
    changes = checklist.validate_changes(office, [
        {"id": "bylayer_colour", "severity": "high"},
        {"id": "text_heights", "target": {"heights": [2.5, 5]}},
        {"id": "xrefs_found", "on": False},
    ])  # fmt: skip
    used = {c["id"]: c for c in checklist.layer(office, changes)}
    assert used["bylayer_colour"]["severity"] == "high" and used["bylayer_colour"]["from"] == "project"
    assert used["bylayer_colour"]["project_changed"] == {"severity": {"office": "low", "project": "high"}}
    assert used["text_heights"]["params"] == {"heights": [2.5, 5]}
    assert used["xrefs_found"]["on"] is False
    assert used["nothing_on_layer_0"]["from"] == "office" and "project_changed" not in used["nothing_on_layer_0"]
    # The office list itself is untouched, and its order is kept.
    assert office[1]["severity"] == "low" and office[4]["params"] == {"heights": [2.5, 3.5]}
    assert [c["id"] for c in checklist.layer(office, changes)] == [c["id"] for c in office]


def test_each_run_names_every_check_and_where_it_came_from():
    office = checklist.validate(OFFICE)
    used = checklist.layer(office, [{"id": "bylayer_colour", "severity": "high"}])
    report = checklist.run("before issue", used, CLEAN)
    named = {c["id"]: c["from"] for c in report["checks_used"]}
    assert set(named) == {c["id"] for c in office}
    assert named["bylayer_colour"] == "project" and named["nothing_on_layer_0"] == "office"


@pytest.mark.parametrize(
    "change, words",
    [
        ({"id": "no_such_check", "severity": "low"}, "cannot add one"),
        ({"id": "nothing_on_layer_0", "check": "bylayer_linetype"}, "may only change"),
        ({"id": "nothing_on_layer_0", "label": "new words"}, "may only change"),
        ({"id": "nothing_on_layer_0", "advice": "ignore it"}, "may only change"),
        ({"id": "nothing_on_layer_0", "clause": "Client 1.1"}, "may only change"),
        ({"id": "text_heights", "params": {"heights": [1]}}, "may only change"),
        ({"id": "text_heights", "target": {"pattern": "^M-"}}, "takes only heights"),
        ({"id": "text_heights", "target": {"heights": []}}, "positive numbers"),
        ({"id": "text_heights", "target": "2.5"}, "must be an object"),
        ({"id": "nothing_on_layer_0", "target": {"x": 1}}, "has no target"),
        ({"id": "nothing_on_layer_0", "severity": "urgent"}, "severity"),
        ({"id": "nothing_on_layer_0", "on": "no"}, "true or false"),
        ({"id": "nothing_on_layer_0"}, "say what changes"),
    ],
)
def test_a_project_may_not_add_or_change_what_a_check_does(change, words):
    office = checklist.validate(OFFICE)
    with pytest.raises(ValueError) as caught:
        checklist.validate_changes(office, [{"id": "xrefs_found", "on": False}, change])
    assert "Project change 2" in str(caught.value) and words in str(caught.value)


def test_a_check_changed_twice_is_refused():
    office = checklist.validate(OFFICE)
    with pytest.raises(ValueError, match="changed twice"):
        checklist.validate_changes(office, [{"id": "xrefs_found", "on": False}, {"id": "xrefs_found", "severity": "low"}])


def test_each_office_check_has_its_own_id():
    office = checklist.validate([
        {"check": "title_block_filled", "params": {"block": "A1*"}},
        {"check": "title_block_filled", "params": {"block": "A3*"}},
        {"check": "nothing_on_layer_0", "id": "No objects on 0"},
    ])  # fmt: skip
    assert [c["id"] for c in office] == ["title_block_filled", "title_block_filled_2", "no_objects_on_0"]
    with pytest.raises(ValueError, match="used twice"):
        checklist.validate([{"check": "xrefs_found", "id": "x"}, {"check": "bylayer_colour", "id": "x"}])


async def _direct(fn):
    return fn()


class _Doc:
    def __init__(self, full_name: str):
        self.FullName = full_name


@pytest.fixture
def drawing(tmp_path, monkeypatch):
    path = tmp_path / "job" / "M-101.dwg"
    path.parent.mkdir()
    path.write_bytes(b"")
    monkeypatch.setattr(checklists, "run", _direct)
    monkeypatch.setattr(checklists, "get_doc", lambda: _Doc(str(path)))
    monkeypatch.setattr(checklists, "gather", lambda doc, wanted, most: CLEAN)
    return path


def _call(**kwargs):
    return asyncio.run(checklists.autocad_checklist(**kwargs))


def test_the_tool_keeps_project_changes_and_runs_with_them(drawing):
    kept = json.loads(_call(action="project", name="before issue", changes=[
        {"id": "bylayer_colour", "severity": "high"}, {"id": "xrefs_found", "on": False}]))  # fmt: skip
    assert kept["project"] and len(kept["changes"]) == 2
    shown = json.loads(_call(action="project", name="before issue"))
    assert shown["changes"] == kept["changes"]
    report = json.loads(_call(action="run", name="before issue"))
    rows = _rows(report)
    assert rows["xrefs_found"]["state"] == "NOT RUN" and rows["xrefs_found"]["from"] == "project"
    assert rows["bylayer_colour"]["severity"] == "high"
    assert report["lists"]["office"] == "ships with Heron" and report["lists"]["project"] == kept["project"]
    assert report["coverage"] == "4 of 5 decided, 0 no data, 1 not run" and report["verdict"] == "PASS"
    # [] clears them: back to the office list alone.
    _call(action="project", name="before issue", changes=[])
    again = json.loads(_call(action="run", name="before issue"))
    assert all(c["from"] == "office" for c in again["checks_used"]) and again["lists"]["project"] is None


def test_another_project_folder_does_not_see_the_changes(drawing, tmp_path, monkeypatch):
    _call(action="project", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    other = tmp_path / "other" / "M-201.dwg"
    other.parent.mkdir()
    monkeypatch.setattr(checklists, "get_doc", lambda: _Doc(str(other)))
    report = json.loads(_call(action="run", name="before issue"))
    assert all(c["from"] == "office" for c in report["checks_used"])


def test_a_wrong_project_change_keeps_nothing(drawing):
    answer = _call(action="project", name="before issue", changes=[{"id": "my_new_check", "on": True}])
    assert answer.startswith("Error:") and "cannot add one" in answer and "Nothing was kept" in answer
    assert json.loads(_call(action="project", name="before issue"))["changes"] == []


def test_an_unsaved_drawing_keeps_no_project_changes(drawing, monkeypatch):
    monkeypatch.setattr(checklists, "get_doc", lambda: _Doc(""))
    answer = _call(action="project", name="before issue", changes=[{"id": "xrefs_found", "on": False}])
    assert answer.startswith("Error:") and "not saved yet" in answer


def test_changes_that_no_longer_fit_the_office_list_stop_the_run(drawing):
    _call(action="save", name="sheets", checks=[{"check": "nothing_on_layer_0"}, {"check": "xrefs_found"}])
    _call(action="project", name="sheets", changes=[{"id": "xrefs_found", "on": False}])
    _call(action="save", name="sheets", checks=[{"check": "nothing_on_layer_0"}])
    answer = _call(action="run", name="sheets")
    assert answer.startswith("Error:") and "no longer fit" in answer and "changes=[]" in answer


def test_list_with_a_name_shows_the_ids_to_change():
    shown = json.loads(_call(action="list", name="before issue"))
    assert "xrefs_found" in [c["id"] for c in shown["checks"]]


# ---------------------------------------------------------------------------
# #86 the report: a new .xlsx and .html, never overwriting
# ---------------------------------------------------------------------------


def test_report_names_are_numbered_and_never_reused(tmp_path):
    stem = checklist_report.stem_for(str(tmp_path / "M-101.dwg"), "Before issue", "2026-11-21")
    assert stem == "M-101 - checklist before-issue - 2026-11-21"
    first = checklist_report.free_names(tmp_path, stem)
    assert first[0].name == f"{stem}.xlsx" and first[1].name == f"{stem}.html"
    first[1].write_text("an earlier page alone")  # either file being there moves the number on
    second = checklist_report.free_names(tmp_path, stem)
    assert second[0].name == f"{stem} (2).xlsx" and second[1].name == f"{stem} (2).html"


def test_write_new_never_replaces_a_file(tmp_path):
    path = tmp_path / "r.xlsx"
    path.write_bytes(b"earlier")
    with pytest.raises(FileExistsError):
        checklist_report.write_new(path, b"later")
    assert path.read_bytes() == b"earlier"


def test_the_report_tool_writes_both_files_next_to_the_drawing_and_never_overwrites(drawing):
    first = json.loads(asyncio.run(checklists.autocad_checklist_report(name="before issue")))
    xlsx, html = Path(first["saved"]["xlsx"]), Path(first["saved"]["html"])
    assert xlsx.parent == drawing.parent and html.parent == drawing.parent
    assert xlsx.is_file() and html.is_file()
    earlier = xlsx.read_bytes()
    second = json.loads(asyncio.run(checklists.autocad_checklist_report(name="before issue")))
    assert Path(second["saved"]["xlsx"]).name.endswith(" (2).xlsx")
    assert xlsx.read_bytes() == earlier  # the first one is untouched
    assert first["coverage"] == "5 of 5 decided, 0 no data, 0 not run"


def test_the_workbook_reads_back_with_a_summary_and_every_check(drawing):
    from autocad_mcp.acad import xlsx

    report = json.loads(_call(action="run", name="before issue"))
    sheets = xlsx.read(checklist_report.workbook(report, str(drawing), "2026-11-21 10:00"))
    summary = {row[0]: row[1] for row in sheets["Summary"][1:]}
    assert summary["Coverage"] == report["coverage"] and summary["What PASS means"] == checklist.PASS_MEANS
    rows = sheets["Check list"]
    assert rows[0] == list(checklist_report.COLUMNS)
    assert [row[3] for row in rows[1:]] == [r["label"] for r in report["results"]]


def test_the_page_escapes_what_the_modeller_wrote(drawing):
    report = checklist.run("<b>x</b>", checklist.validate([{"check": "nothing_on_layer_0", "label": "a < b & c"}]), CLEAN)
    text = checklist_report.page(report, str(drawing), "now")
    assert "a &lt; b &amp; c" in text and "<b>x</b>" not in text and report["coverage"] in text


def test_an_unsaved_drawing_gets_no_report(drawing, monkeypatch, tmp_path):
    monkeypatch.setattr(checklists, "get_doc", lambda: _Doc(""))
    answer = asyncio.run(checklists.autocad_checklist_report(name="before issue"))
    assert answer.startswith("Error:") and "not saved yet" in answer
    assert not list(tmp_path.rglob("*.xlsx"))


def test_saving_a_report_needs_the_publish_padlock_but_running_does_not():
    assert risk_of("autocad_checklist_report") is Risk.PUBLISH
    assert risk_of("autocad_checklist") is Risk.READ


# ---------------------------------------------------------------------------
# #87 PASS means the checked value is met; never "complies"
# ---------------------------------------------------------------------------

NEVER = ("complies", "compliant", "compliance", "certif", "approved")


def _says_no_compliance(text: str) -> None:
    lowered = text.lower()
    for word in NEVER:
        assert word not in lowered, word


def test_pass_means_names_the_source_and_says_it_is_not_a_sign_off():
    assert "checked value is met" in checklist.PASS_MEANS and "source" in checklist.PASS_MEANS
    assert "not a sign-off" in checklist.PASS_MEANS
    _says_no_compliance(checklist.PASS_MEANS)


def test_every_line_names_its_source(drawing):
    _call(action="save", name="sheets", checks=OFFICE)
    report = json.loads(_call(action="run", name="sheets"))
    rows = _rows(report)
    assert rows["bylayer_colour"]["source"] == "Office CAD std 3.1"
    assert rows["nothing_on_layer_0"]["source"] == "office check list 'sheets'"
    assert all(row["source"] for row in report["results"])


def test_no_answer_says_a_drawing_complies(drawing):
    run = _call(action="run", name="before issue")
    report = asyncio.run(checklists.autocad_checklist_report(name="before issue"))
    saved = json.loads(report)["saved"]
    page = Path(saved["html"]).read_text(encoding="utf-8")
    for text in (run, report, page):
        assert checklist.PASS_MEANS in text
        _says_no_compliance(text)


def test_check_standards_says_what_passed_means(monkeypatch):
    class LayerTable:
        Count = 1

        def Item(self, i):
            return object()

    class Doc:
        Layers = LayerTable()

    monkeypatch.setattr(standards, "run", _direct)
    monkeypatch.setattr(standards, "get_doc", lambda: Doc())
    monkeypatch.setattr(standards, "describe_layer", lambda layer: {"name": "M-DUCT"})
    answer = asyncio.run(standards.autocad_check_standards(rules={"layer_name_pattern": "^M-"}))
    report = json.loads(answer)
    assert report["passed"] is True and report["pass_means"] == checklist.PASS_MEANS
    assert report["source"] == "the rules given in this chat"
    _says_no_compliance(answer)


def test_the_tools_say_it_in_their_own_docs():
    for tool in (checklists.autocad_checklist, checklists.autocad_checklist_report, standards.autocad_check_standards):
        doc = " ".join((inspect.getdoc(tool) or "").split())
        assert "never means the drawing complies" in doc or "not a certificate" in doc, tool.__name__


def test_the_disclaimer_is_at_the_root_in_plain_words():
    text = (ROOT / "DISCLAIMER.md").read_text(encoding="utf-8")
    assert "checked value is met" in text
    assert "never says a drawing complies" in text


# ---------------------------------------------------------------------------
# Found in review: a read cut short at max_entities is not a PASS anywhere
# ---------------------------------------------------------------------------


def test_title_blocks_read_from_part_of_the_drawing_are_not_a_pass():
    data = {**CLEAN, "capped": 2}
    report = checklist.run("t", checklist.validate([{"check": "title_block_filled", "params": {"block": "TITLE*"}}]), data)
    row = report["results"][0]
    assert row["state"] == "NO DATA" and "only the first 2 objects" in row["note"]


def test_an_empty_title_block_found_in_part_of_the_drawing_is_still_a_failure():
    data = {**CLEAN, "capped": 2, "blocks": [{"handle": "T9", "name": "TITLE-A1", "attributes": {"DATE": ""}}]}
    report = checklist.run("t", checklist.validate([{"check": "title_block_filled", "params": {"block": "TITLE*"}}]), data)
    assert report["results"][0]["state"] == "FAIL"


def test_check_standards_on_part_of_the_drawing_does_not_say_passed(monkeypatch):
    class Entity:
        Handle, ObjectName, Layer, Color, Linetype = "E1", "AcDbLine", "M-DUCT", 256, "ByLayer"

    class LayerTable:
        Count = 1

        def Item(self, i):
            return object()

    class Doc:
        Layers = LayerTable()

    monkeypatch.setattr(standards, "run", _direct)
    monkeypatch.setattr(standards, "get_doc", lambda: Doc())
    monkeypatch.setattr(standards, "describe_layer", lambda layer: {"name": "M-DUCT"})
    monkeypatch.setattr(standards, "select_filtered", lambda doc: None)
    monkeypatch.setattr(standards, "iter_selection", lambda sel: iter([Entity(), Entity()]))
    monkeypatch.setattr(standards, "discard_selection_set", lambda doc: None)
    answer = asyncio.run(standards.autocad_check_standards(rules={"forbid_entities_on_layer_0": True}, max_entities=1))
    report = json.loads(answer)
    assert report["passed"] is None and "decided" in report["warning"]
    _says_no_compliance(answer)
