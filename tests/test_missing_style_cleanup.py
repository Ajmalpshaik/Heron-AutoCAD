"""A missing table or multileader style leaves nothing behind (#191, item 1).

COM makes the object first and sets its style after, so a style the drawing
lacks used to leave an empty table (or a bare leader) in model space, and the
refusal's advice ("leave style out") then made a second one.
"""

from __future__ import annotations

import asyncio

import pytest

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, annotate, tables


class NoSuchStyle:
    """A new table or multileader whose style AutoCAD refuses, as COM does."""

    def __init__(self, delete_fails=False):
        self.deleted = False
        self.delete_fails = delete_fails
        self.Handle = "2F"

    def __setattr__(self, name, value):
        if name == "StyleName":
            raise RuntimeError("Key not found")
        object.__setattr__(self, name, value)

    def Delete(self):
        if self.delete_fails:
            raise RuntimeError("eWasOpenForWrite")
        self.deleted = True


class Space:
    def __init__(self, made):
        self.made = made

    def AddTable(self, *args):
        return self.made

    def AddMLeader(self, *args):
        return (self.made, 0)


class Doc:
    def __init__(self, space):
        self.ModelSpace = self.PaperSpace = space

    def GetVariable(self, name):
        return (0.0, 0.0, 0.0) if name.startswith("UCS") else 0

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def drawing(monkeypatch):
    made = NoSuchStyle()
    doc = Doc(Space(made))

    async def run(fn):
        return fn()

    monkeypatch.setattr(annotate, "run", run)
    monkeypatch.setattr(annotate, "get_doc", lambda: doc)
    monkeypatch.setattr(annotate, "require_idle", lambda d: None)
    return made


def answer(coro) -> str:
    text = asyncio.run(coro)
    assert text.startswith("Error"), text
    return text


def test_fill_table_erases_the_table_it_made(monkeypatch):
    made = NoSuchStyle()
    with pytest.raises(AutocadError) as caught:
        tables.fill_table(Doc(Space(made)), Space(made), (0, 0, 0), [["A"]], title=None, header=False,
                          text_height=None, widths=None, style="SCHED")
    assert made.deleted
    assert "no table style called 'SCHED'" in str(caught.value)
    assert "Nothing was left in the drawing" in str(caught.value)


def test_add_table_erases_the_table_it_made(drawing):
    text = answer(annotate.autocad_add_table(position=[0, 0], rows=[["A", "B"]], style="SCHED"))
    assert drawing.deleted
    assert "autocad_create_styles(table_styles=...)" in text and "Nothing was left" in text


def test_add_multileader_erases_the_leader_it_made(drawing):
    text = answer(annotate.autocad_add_multileader(landing=[10, 10], arrows=[[0, 0]], text="FCU", style="TAG"))
    assert drawing.deleted
    assert "autocad_create_styles(multileader_styles=...)" in text and "Nothing was left" in text


def test_an_erase_that_fails_is_said(monkeypatch):
    made = NoSuchStyle(delete_fails=True)
    with pytest.raises(AutocadError) as caught:
        tables.fill_table(Doc(Space(made)), Space(made), (0, 0, 0), [["A"]], title=None, header=False,
                          text_height=None, widths=None, style="SCHED")
    assert "An empty one was left in the drawing; erase it." in str(caught.value)


def test_discard_new_says_whether_it_went():
    assert _shared.discard_new(NoSuchStyle()) is True
    assert _shared.discard_new(NoSuchStyle(delete_fails=True)) is False
