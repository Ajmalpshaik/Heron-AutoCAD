"""checklists.gather on fake COM (#211): a read that failed is never a silent PASS (D-64). No AutoCAD."""

from __future__ import annotations

import pytest

from autocad_mcp.acad import checklist
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import checklists


class Collection:
    def __init__(self, items):
        self._items = items

    @property
    def Count(self):
        return len(self._items)

    def Item(self, i):
        return self._items[i]


class Layer:
    Name, Color, Linetype, Lineweight, LayerOn, Freeze, Lock, Plottable = "0", 7, "Continuous", -3, True, False, False, True


class Entity:
    def __init__(self, handle, kind, height=2.5, box=((0, 0, 0), (10, 5, 0)), fails=()):
        self.Handle, self.ObjectName, self.Layer, self.Color, self.Linetype = handle, kind, "M-TEXT", 256, "ByLayer"
        self._height, self._box, self._fails = height, box, fails

    @property
    def Height(self):
        if "height" in self._fails:
            raise OSError("cannot read this one")
        return self._height

    def GetBoundingBox(self):
        if "box" in self._fails:
            raise OSError("cannot read this one")
        return self._box


class Block:
    def __init__(self, name, xref=False, fails=False):
        self.Name, self._xref, self._fails, self.Path, self.XRefDatabase = name, xref, fails, "", None

    @property
    def IsXRef(self):
        if self._fails:
            raise OSError("block table damaged")
        return self._xref


class Doc:
    def __init__(self, entities=(), blocks=()):
        self.Layers = Collection([Layer()])
        self.Blocks = Collection(list(blocks))
        self.Path, self.FullName = "C:\\Jobs", "C:\\Jobs\\M-101.dwg"
        self._entities = list(entities)


@pytest.fixture(autouse=True)
def _no_selection_sets(monkeypatch):
    monkeypatch.setattr(checklists, "select_filtered", lambda doc: Collection(doc._entities))
    monkeypatch.setattr(checklists, "discard_selection_set", lambda doc: None)
    monkeypatch.setattr(checklists, "read_attributes", lambda entity: {})


def run(check, doc, wanted):
    data = checklists.gather(doc, wanted, 1000)
    return checklist.run("t", checklist.validate([check]), data)["results"][0], data


def test_text_heights_read_and_judged():
    row, _ = run({"check": "text_heights", "params": {"heights": [2.5]}},
                 Doc([Entity("A", "AcDbText"), Entity("B", "AcDbMText", height=3.5)]), {"entities"})  # fmt: skip
    assert row["state"] == "FAIL" and row["handles"] == ["B"]


def test_a_text_height_that_cannot_be_read_is_no_data_not_pass():
    row, data = run({"check": "text_heights", "params": {"heights": [2.5]}},
                    Doc([Entity("A", "AcDbText"), Entity("B", "AcDbText", fails=("height",))]), {"entities"})  # fmt: skip
    assert data["unread_heights"] == 1
    assert row["state"] == "NO DATA" and "1 text(s) whose height could not be read" in row["note"]


def test_a_wrong_height_found_beside_an_unread_one_is_still_a_failure():
    row, _ = run({"check": "text_heights", "params": {"heights": [2.5]}},
                 Doc([Entity("A", "AcDbText", height=7), Entity("B", "AcDbText", fails=("height",))]), {"entities"})  # fmt: skip
    assert row["state"] == "FAIL"


def test_a_dimension_box_that_cannot_be_read_is_no_data_not_pass():
    row, data = run({"check": "no_overlapping_dimensions"},
                    Doc([Entity("D1", "AcDbRotatedDimension"), Entity("D2", "AcDbRotatedDimension", fails=("box",))]),
                    {"entities"})  # fmt: skip
    assert data["unread_boxes"] == 1 and row["state"] == "NO DATA"


def test_two_dimensions_on_top_of_each_other_fail():
    row, _ = run({"check": "no_overlapping_dimensions"},
                 Doc([Entity("D1", "AcDbRotatedDimension"), Entity("D2", "AcDbRotatedDimension")]), {"entities"})  # fmt: skip
    assert row["state"] == "FAIL" and row["handles"] == ["D2"]


def test_xrefs_all_found_pass():
    row, data = run({"check": "xrefs_found"}, Doc(blocks=[Block("*Model_Space"), Block("TITLE")]), {"xrefs"})
    assert data["xrefs_broken"] == [] and row["state"] == "PASS"


def test_a_block_table_that_cannot_be_read_is_no_data_not_pass():
    row, data = run({"check": "xrefs_found"}, Doc(blocks=[Block("TITLE"), Block("BASE", fails=True)]), {"xrefs"})
    assert data["xrefs_broken"] is None and row["state"] == "NO DATA"


def test_a_busy_autocad_is_raised_for_the_retry_not_judged(monkeypatch):
    class Busy(Exception):
        pass

    def busy(exc):
        if isinstance(exc, Busy):
            raise AutocadError("AutoCAD is busy")

    class BusyBlock(Block):
        @property
        def IsXRef(self):
            raise Busy()

    monkeypatch.setattr(checklists, "raise_if_busy", busy)
    with pytest.raises(AutocadError, match="busy"):
        checklists.gather(Doc(blocks=[BusyBlock("X")]), {"xrefs"}, 10)
