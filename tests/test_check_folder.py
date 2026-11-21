"""Checking a folder of drawings, read only (D-70)."""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad import checklist, folder_check
from autocad_mcp.tools import check_folder, checklists


def report(verdict: str, failed: int = 0) -> dict:
    results = [{"label": "nothing on layer 0", "state": checklist.FAIL, "failing": failed, "severity": "high"}] if failed else []
    return {"verdict": verdict, "coverage": "1 of 1 decided, 0 no data, 0 not run", "results": results}


def test_only_drawings_in_name_order_and_the_rest_counted(tmp_path):
    for name in ("B.dwg", "a.DWG", "a.bak", "~saving.dwg", "c.dwg", "plot.pdf"):
        (tmp_path / name).write_text("x")
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "d.dwg").write_text("x")
    found, left = folder_check.drawings_in(tmp_path, False, 2)
    assert [p.name for p in found] == ["a.DWG", "B.dwg"] and left == 1
    deep, _ = folder_check.drawings_in(tmp_path, True, 10)
    assert [p.name for p in deep] == ["a.DWG", "B.dwg", "c.dwg", "d.dwg"]


def test_the_summary_puts_the_worst_first():
    lines = [{"drawing": "b", "verdict": checklist.PASS}, {"drawing": "a", "verdict": checklist.FAIL},
             {"drawing": "c", "verdict": checklist.NOT_RUN}]  # fmt: skip
    summary = folder_check.summary(lines)
    assert [line["drawing"] for line in summary["drawings"]] == ["c", "a", "b"]
    assert summary["worst"] == checklist.NOT_RUN and summary["verdicts"][checklist.PASS] == 1


class Doc:
    def __init__(self, path, app):
        self.FullName, self.app = path, app
        self.closed = self.saved = False

    def Activate(self):
        self.app.active = self

    def Close(self, save):
        self.closed, self.saved = True, save
        self.app.open.remove(self)


class Documents:
    def __init__(self, app):
        self.app = app

    @property
    def Count(self):
        return len(self.app.open)

    def Item(self, index):
        return self.app.open[index]

    def Open(self, path, read_only):
        if path.endswith("broken.dwg"):
            raise RuntimeError("Drawing file is not valid.")
        doc = Doc(path, self.app)
        doc.read_only = read_only
        self.app.open.append(doc)
        self.app.active = doc
        self.app.opened.append((path, read_only))
        return doc


class App:
    def __init__(self):
        self.open, self.opened = [], []
        self.Documents = Documents(self)
        self.active = None

    @property
    def ActiveDocument(self):
        return self.active


@pytest.fixture
def folder(monkeypatch, tmp_path):
    app = App()
    mine = Doc(str(tmp_path / "Working.dwg"), app)
    app.open.append(mine)
    app.active = mine
    for name in ("A-101.dwg", "A-102.dwg", "Working.dwg", "broken.dwg"):
        (tmp_path / name).write_text("x")
    seen = []

    async def run_list(name, max_entities, doc_of=None):
        doc = doc_of()
        seen.append(doc.FullName)
        return report(checklist.FAIL, 3) if doc.FullName.endswith("A-102.dwg") else report(checklist.PASS), doc.FullName

    async def now(fn):
        return fn()

    monkeypatch.setattr(check_folder, "run", now)
    monkeypatch.setattr(check_folder, "get_app", lambda: app)
    monkeypatch.setattr(checklists, "run_list", run_list)
    monkeypatch.setattr(checklists, "load", lambda name: {"name": name, "checks": []})
    return app, mine, tmp_path, seen


def test_each_drawing_is_opened_read_only_checked_and_closed_unsaved(folder):
    app, mine, where, seen = folder
    result = json.loads(asyncio.run(check_folder.autocad_check_folder(folder=str(where))))
    assert all(read_only for _, read_only in app.opened)
    assert app.open == [mine]  # the ones Heron opened are closed; the modeller's own stays open
    assert app.active is mine  # and is active again
    assert result["verdicts"] == {checklist.NOT_RUN: 1, checklist.FAIL: 1, checklist.NO_DATA: 0, checklist.PASS: 2}
    worst, failed, *_ = result["drawings"]
    assert worst["drawing"] == "broken.dwg" and "would not open" in worst["reason"]
    assert failed["drawing"] == "A-102.dwg" and failed["failed"][0]["failing"] == 3
    assert str(where / "Working.dwg") in seen  # an open drawing is checked where it is


def test_a_folder_that_is_not_there_or_has_no_drawings_opens_nothing(folder, tmp_path):
    app = folder[0]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert asyncio.run(check_folder.autocad_check_folder(folder=str(empty))).startswith("Error: There is no .dwg")
    assert asyncio.run(check_folder.autocad_check_folder(folder="not a folder")).startswith("Error: 'not a folder' is not")
    assert app.opened == []


def test_the_emergency_stop_leaves_the_rest_out(folder, monkeypatch):
    from autocad_mcp.core import gate

    app, mine, where, seen = folder
    monkeypatch.setattr(gate, "stopped_by_modeller", lambda: True)
    result = json.loads(asyncio.run(check_folder.autocad_check_folder(folder=str(where))))
    assert len(result["drawings"]) == 1 and "HERONSTOP" in result["hint"]
    assert app.open == [mine] and app.active is mine


def test_it_is_a_view_tool_that_writes_nothing():
    from autocad_mcp.core.risk import Risk, risk_of

    assert risk_of("autocad_check_folder") is Risk.VIEW


def test_a_drawing_autocad_already_had_open_under_another_name_is_never_closed(folder, monkeypatch):
    """Found in review: a mapped drive and its UNC path name the same file; Open hands back the open one."""
    app, mine, where, seen = folder
    other = Doc(r"\\server\share\Working.dwg", app)
    app.open.append(other)

    def open_returns_the_open_one(path, read_only):
        if path.endswith("Working.dwg"):
            return other  # AutoCAD hands back the drawing it already has open
        return Documents.Open(app.Documents, path, read_only)

    monkeypatch.setattr(app.Documents, "Open", open_returns_the_open_one)
    monkeypatch.setattr(check_folder, "_full_name", lambda doc: "" if doc is other else doc.FullName)
    asyncio.run(check_folder.autocad_check_folder(folder=str(where)))
    assert other in app.open and not other.closed
