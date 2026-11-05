"""autocad_create_layout never leaves a half-made sheet (bedroom model, 2026-11-05).

Setting the default plotter failed with "Property 'Add.ConfigName' can not be
set", the layout stayed, and the retry was told the name was taken.
"""

from __future__ import annotations

import asyncio

import pytest

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import sheets


class Layout:
    def __init__(self, name, refusals=0):
        self.Name = name
        self.refusals = refusals
        self.deleted = False
        self._config = ""

    @property
    def ConfigName(self):
        return self._config

    @ConfigName.setter
    def ConfigName(self, value):
        if self.refusals:
            self.refusals -= 1
            raise AttributeError("Property 'Add.ConfigName' can not be set.")
        self._config = value

    def RefreshPlotDeviceInfo(self):
        pass

    def Delete(self):
        self.deleted = True


class Layouts:
    def __init__(self, refusals):
        self.items = [Layout("Model"), Layout("Layout1")]
        self.refusals = refusals

    @property
    def Count(self):
        return len([x for x in self.items if not x.deleted])

    def Item(self, i):
        return [x for x in self.items if not x.deleted][i]

    def Add(self, name):
        layout = Layout(name, self.refusals)
        self.items.append(layout)
        return layout


class Doc:
    def __init__(self, refusals):
        self.Layouts = Layouts(refusals)

    def GetVariable(self, name):
        return 0

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def no_wait(monkeypatch):
    monkeypatch.setattr(sheets, "PLOTTER_RETRY_DELAY", 0)


def test_a_busy_moment_is_retried_and_the_plotter_set(no_wait):
    layout = Layout("E-101", refusals=2)
    written = sheets._set_page(layout, "DWG To PDF.pc3", None, None, None, None, None,
                               None, None, None, None, None, None)
    assert written["plotter"] == "DWG To PDF.pc3"
    assert layout.ConfigName == "DWG To PDF.pc3"


def test_a_plotter_refused_every_time_is_reported(no_wait):
    layout = Layout("E-101", refusals=99)
    with pytest.raises(AutocadError, match="would not set the plotter"):
        sheets._set_page(layout, "No Such.pc3", None, None, None, None, None,
                         None, None, None, None, None, None)


def test_a_failed_page_setup_removes_the_new_layout(monkeypatch, no_wait):
    doc = Doc(refusals=99)

    async def run(fn):
        return fn()

    monkeypatch.setattr(sheets, "run", run)
    monkeypatch.setattr(sheets, "get_doc", lambda: doc)
    monkeypatch.setattr(sheets, "require_idle", lambda d: None)
    answer = asyncio.run(sheets.autocad_create_layout(name="PARTS LIST", paper_size="A3"))
    assert answer.startswith("Error")
    assert "was not kept" in answer
    added = doc.Layouts.items[-1]
    assert added.Name == "PARTS LIST" and added.deleted
    assert "PARTS LIST" not in sheets._layouts(doc)
