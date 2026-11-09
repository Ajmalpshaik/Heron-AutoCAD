"""Fixes from the Luxury Suite 2 interior set (AutoCAD 2027, 2026-11-09).

After a viewport hung on a sheet made with Layouts.Add, ``doc.PaperSpace`` threw
a bare Automation error. autocad_status failed whole on its paper-space count,
and autocad_add_viewport could not add a viewport, though MVIEW typed with two
corners still made one on the same sheet.
"""

from __future__ import annotations

import pytest

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import document, sheets


class Broken:
    """A COM property that throws when read, as doc.PaperSpace did."""

    def __get__(self, obj, owner):
        raise RuntimeError("Automation error")


class Viewport:
    ObjectName = "AcDbViewport"

    def __init__(self, handle):
        self.Handle = handle


class Insert:
    ObjectName = "AcDbBlockReference"
    Handle = "3072"


class Block:
    def __init__(self, items):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index]


class Layout:
    def __init__(self, block):
        self.Block = block


class Doc:
    PaperSpace = Broken()

    def __init__(self, makes_viewport=True):
        self.block = Block([Insert(), Viewport("3064")])
        self.ActiveLayout = Layout(self.block)
        self.sent: list[str] = []
        self.makes_viewport = makes_viewport
        self.variables = {"OSMODE": 675}
        self.osmode_during_send = None

    def GetVariable(self, name):
        return self.variables[name]

    def SetVariable(self, name, value):
        self.variables[name] = value

    def SendCommand(self, text):
        self.sent.append(text)
        self.osmode_during_send = self.variables["OSMODE"]
        if self.makes_viewport:
            self.block.items.append(Viewport("31CB"))


class TestStatusCount:
    def test_a_broken_paper_space_falls_back_to_the_layout_block(self):
        assert document._paper_space_count(Doc()) == 2

    def test_nothing_answers_gives_none_not_an_error(self):
        doc = Doc()
        doc.ActiveLayout = None
        assert document._paper_space_count(doc) is None


class TestViewportFallback:
    def test_mview_is_typed_with_the_two_corners_and_no_extra_enter(self):
        text = sheets.mview_command(338.0, 300.0, 560.0, 420.0)
        assert text == "_.MVIEW 58.0000,90.0000 618.0000,510.0000 "
        assert not text.endswith("  ")

    def test_the_new_viewport_is_the_one_mview_made(self, monkeypatch):
        monkeypatch.setattr(sheets.time, "sleep", lambda s: None)
        doc = Doc()
        viewport = sheets._new_viewport(doc, "ID-101", 338.0, 300.0, 560.0, 420.0)
        assert viewport.Handle == "31CB"
        assert doc.sent == ["_.MVIEW 58.0000,90.0000 618.0000,510.0000 "]

    def test_snaps_are_off_for_mview_and_put_back(self, monkeypatch):
        monkeypatch.setattr(sheets.time, "sleep", lambda s: None)
        doc = Doc()
        sheets._new_viewport(doc, "ID-101", 338.0, 300.0, 560.0, 420.0)
        assert doc.osmode_during_send == 0
        assert doc.variables["OSMODE"] == 675

    def test_no_viewport_from_mview_either_is_a_plain_error(self, monkeypatch):
        monkeypatch.setattr(sheets.time, "sleep", lambda s: None)
        with pytest.raises(AutocadError, match="MVIEW made none either"):
            sheets._new_viewport(Doc(makes_viewport=False), "ID-101", 338.0, 300.0, 560.0, 420.0)
