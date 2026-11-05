"""The tools from the ADN-DevTech study (docs/11-adn-repos-study.md), no AutoCAD.

The xref tree and the drawing report are reads over COM, checked against fake
COM objects. The multi-sheet PDF is the plug-in's (D-40): what is checked here
is what the tool asks the plug-in for and what it refuses before asking.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core import connection
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, drawing_report, publish, xrefs


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


async def _now(fn):
    return fn()


class Items:
    def __init__(self, *items):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]


# ---------------------------------------------------------------------------
# autocad_xref_tree
# ---------------------------------------------------------------------------


class XBlock:
    def __init__(self, name, path="", inner=None, is_xref=True):
        self.Name, self.Path, self.IsXRef = name, path, is_xref
        self._inner = inner

    @property
    def XRefDatabase(self):
        if self._inner is None:
            raise RuntimeError("not loaded")
        return self._inner


class XDb:
    def __init__(self, *blocks):
        self.Blocks = Items(*blocks)


class XDoc:
    def __init__(self, folder, *blocks):
        self.Name, self.Path = "M-100.dwg", str(folder)
        self.FullName = str(folder / "M-100.dwg")
        self.Blocks = Items(XBlock("*Model_Space", is_xref=False), *blocks)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "Arch").mkdir()
    (tmp_path / "Arch" / "A-101.dwg").write_bytes(b"AC1032")
    (tmp_path / "Grid.dwg").write_bytes(b"AC1032")
    monkeypatch.setattr(xrefs, "run", _now)
    return tmp_path


def tree_of(monkeypatch, doc):
    monkeypatch.setattr(xrefs, "get_doc", lambda: doc)
    return call(xrefs.autocad_xref_tree())


class TestXrefTree:
    def test_nested_xrefs_are_listed_under_their_parent(self, project, monkeypatch):
        grid = XBlock("GRID", "..\\Grid.dwg", XDb())
        arch = XBlock("ARCH", str(project / "Arch" / "A-101.dwg"), XDb(grid))
        out = tree_of(monkeypatch, XDoc(project, arch))
        assert out["count"] == 2 and out["broken"] == []
        (top,) = out["xrefs"]
        assert top["name"] == "ARCH" and top["status"] == "loaded"
        (child,) = top["children"]
        assert child["name"] == "GRID" and child["status"] == "loaded"
        # A relative path is found from the folder of the drawing that carries it.
        assert child["found_path"].endswith("Grid.dwg")

    def test_a_path_that_leads_nowhere_is_broken(self, project, monkeypatch):
        out = tree_of(monkeypatch, XDoc(project, XBlock("SURVEY", "D:\\Gone\\Survey.dwg")))
        assert out["broken"] == ["SURVEY"] and out["xrefs"][0]["status"] == "not found"
        assert out["xrefs"][0]["found_path"] == "" and "advice" in out

    def test_a_file_that_is_there_but_not_loaded_is_unloaded(self, project, monkeypatch):
        out = tree_of(monkeypatch, XDoc(project, XBlock("ARCH", "Arch\\A-101.dwg")))
        assert out["xrefs"][0]["status"] == "unloaded" and out["broken"] == []

    def test_a_bare_file_name_is_looked_for_beside_the_drawing(self, project, monkeypatch):
        out = tree_of(monkeypatch, XDoc(project, XBlock("GRID", "C:\\Old\\Place\\Grid.dwg")))
        assert out["xrefs"][0]["found_path"].endswith("Grid.dwg")

    def test_a_loop_of_references_is_marked_not_followed(self, project, monkeypatch):
        loop_db = XDb()
        arch = XBlock("ARCH", str(project / "Arch" / "A-101.dwg"), loop_db)
        loop_db.Blocks.items.append(XBlock("ARCH-AGAIN", str(project / "Arch" / "A-101.dwg"), XDb()))
        out = tree_of(monkeypatch, XDoc(project, arch))
        (again,) = out["xrefs"][0]["children"]
        assert again["children"] == [] and "already above" in again["note"]

    def test_blocks_that_are_not_xrefs_are_left_out(self, project, monkeypatch):
        out = tree_of(monkeypatch, XDoc(project, XBlock("DOOR", is_xref=False)))
        assert out == {"drawing": "M-100.dwg", "count": 0, "broken": [], "xrefs": []}


# ---------------------------------------------------------------------------
# autocad_drawing_report
# ---------------------------------------------------------------------------


class Named:
    def __init__(self, name, **extra):
        self.Name = name
        for key, value in extra.items():
            setattr(self, key, value)


class Thing:
    def __init__(self, object_name):
        self.ObjectName = object_name


class Layout:
    def __init__(self, name, order, count, paper=""):
        self.Name, self.TabOrder, self.CanonicalMediaName = name, order, paper
        self.Block = Items(*[Thing("AcDbViewport")] * count)


class RDoc:
    def __init__(self, things=()):
        self.Name, self.FullName = "Consultant.dwg", "D:\\In\\Consultant.dwg"
        self.Layers = Items(
            Named("0", LayerOn=True, Freeze=False, Lock=False),
            Named("M-DUCT", LayerOn=False, Freeze=False, Lock=False),
            Named("A-WALL", LayerOn=True, Freeze=True, Lock=True),
        )
        self.Blocks = Items(
            Named("*Model_Space", IsLayout=True, IsXRef=False),
            Named("*U12", IsLayout=False, IsXRef=False),
            Named("VAV", IsLayout=False, IsXRef=False),
            Named("ARCH", IsLayout=False, IsXRef=True, Path="..\\Arch\\A.dwg"),
        )
        self.TextStyles = Items(Named("Standard"), Named("ROMANS"))
        self.DimStyles = Items(Named("ISO-25"))
        self.Linetypes = Items(Named("Continuous"), Named("HIDDEN"))
        self.Layouts = Items(Layout("Model", 0, 0), Layout("M-102", 2, 3, "ISO_A1"), Layout("M-101", 1, 2, "ISO_A1"))
        self.ModelSpace = Items(*things)

    def GetVariable(self, name):
        assert name == "INSUNITS"
        return 4


@pytest.fixture
def report(monkeypatch):
    def go(doc, **kwargs):
        monkeypatch.setattr(drawing_report, "run", _now)
        monkeypatch.setattr(drawing_report, "get_doc", lambda: doc)
        return call(drawing_report.autocad_drawing_report(**kwargs))

    return go


class TestDrawingReport:
    def test_it_says_what_a_received_drawing_holds(self, report):
        out = report(RDoc([Thing("AcDbLine"), Thing("AcDbLine"), Thing("AcDbRotatedDimension"), Thing("AcDbMText")]))
        assert out["units"] == "millimeters"
        assert out["layers"]["count"] == 3 and out["layers"]["off"] == ["M-DUCT"]
        assert out["layers"]["frozen"] == ["A-WALL"] and out["layers"]["locked"] == ["A-WALL"]
        assert out["blocks"] == {"count": 1, "names": ["VAV"]}
        assert out["xrefs"] == [{"name": "ARCH", "saved_path": "..\\Arch\\A.dwg"}] and "xref_tree" in out["advice"]
        assert out["text_styles"] == ["ROMANS", "Standard"] and out["linetypes"] == ["Continuous", "HIDDEN"]
        assert [s["name"] for s in out["layouts"]] == ["M-101", "M-102"]
        assert out["layouts"][0] == {"name": "M-101", "order": 1, "objects": 2, "paper": "ISO_A1"}
        assert out["model_space"] == {"total": 4, "by_type": {"line": 2, "dimension": 1, "mtext": 1}}

    def test_a_huge_model_space_is_counted_only_so_far(self, report, monkeypatch):
        monkeypatch.setattr(drawing_report, "MOST_TO_COUNT", 3)
        out = report(RDoc([Thing("AcDbCircle")] * 5))
        assert out["model_space"]["total"] == 5 and out["model_space"]["by_type"] == {"circle": 3}
        assert "first 3 of 5" in out["model_space"]["note"]

    def test_counting_can_be_skipped(self, report):
        assert "model_space" not in report(RDoc([Thing("AcDbLine")]), count_objects=False)


# ---------------------------------------------------------------------------
# autocad_publish_pdf
# ---------------------------------------------------------------------------


class Plugin:
    def __init__(self, target=None):
        self.calls: list[tuple[str, dict]] = []
        self.target = target

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        if self.target is not None:
            self.target.write_bytes(b"%PDF-1.7")
        return {"published": True, "path": args["path"], "count": 2, "sheets": ["M-101", "M-102"]}


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    fake = Plugin(tmp_path / "set.pdf")
    monkeypatch.setattr(publish, "run", _now)
    monkeypatch.setattr(publish, "get_doc", lambda: object())
    monkeypatch.setattr(publish, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    return fake


class TestPublishPdf:
    def test_every_sheet_by_default(self, plugin, tmp_path):
        out = call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf")))
        assert plugin.calls == [("publish_pdf", {"path": str(tmp_path / "set.pdf"), "include_model": False, "overwrite": False})]
        assert out["count"] == 2 and "warning" not in out

    def test_named_sheets_are_passed_trimmed(self, plugin, tmp_path):
        call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), layouts=[" M-101 ", "", "M-102"]))
        assert plugin.calls[0][1]["layouts"] == ["M-101", "M-102"]

    def test_it_is_not_a_drawing_change(self, plugin, tmp_path):
        before = connection.write_count()
        call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf")))
        assert connection.write_count() == before

    @pytest.mark.parametrize("name", ["set.dwf", "nowhere/set.pdf"])
    def test_a_bad_path_is_refused_before_asking(self, plugin, tmp_path, name):
        error(publish.autocad_publish_pdf(path=str(tmp_path / name)))
        assert plugin.calls == []

    def test_an_existing_pdf_needs_overwrite(self, plugin, tmp_path):
        (tmp_path / "set.pdf").write_bytes(b"old")
        assert "overwrite" in error(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf")))
        call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), overwrite=True))
        assert plugin.calls[0][1]["overwrite"] is True

    def test_no_file_afterwards_is_said(self, plugin, tmp_path):
        plugin.target = None
        out = call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf")))
        assert "no file" in out["warning"]

    def test_without_the_plug_in_it_says_why(self, plugin, tmp_path, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        assert "--no-bridge" in error(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf")))


def test_levels():
    assert risk_of("autocad_xref_tree") is Risk.READ
    assert risk_of("autocad_drawing_report") is Risk.READ
    assert risk_of("autocad_publish_pdf") is Risk.PUBLISH
