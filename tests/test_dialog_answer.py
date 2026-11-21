"""A command or expression can name one button for one box it expects (#101, D-74)."""

from __future__ import annotations

import asyncio

import pytest
import test_gate
from test_gate import FakeBridge

from autocad_mcp.core import gate
from autocad_mcp.core.bridge import OLD_EXPECT, Bridge
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import advanced

env = test_gate.env  # the gate with the bridge and COM faked


def test_both_or_neither():
    assert advanced.expectation(None, None) is None
    assert advanced.expectation(" Purge - Confirm Purge ", "Yes") == ("Purge - Confirm Purge", "Yes")
    with pytest.raises(AutocadError, match="both expect_box"):
        advanced.expectation("Purge - Confirm Purge", None)
    with pytest.raises(AutocadError, match="both expect_box"):
        advanced.expectation(None, "Yes")


def test_the_bridge_says_when_the_plug_in_took_it_and_why_not(monkeypatch):
    replies = iter([
        {"ok": True},
        {"ok": False, "refusedBy": "Level", "message": "Only a job that holds the Admin padlock may name a button."},
        {"ok": False, "refusedBy": "BadRequest", "message": "Heron in AutoCAD does not know the request 'expect_dialog'."},
    ])
    monkeypatch.setattr(Bridge, "call", lambda self, op, **fields: next(replies))
    assert Bridge(1).expect_dialog("j1", "Purge - Confirm Purge", "Yes") is None
    assert Bridge(1).expect_dialog("j1", "X", "Yes").endswith("Nothing was sent to AutoCAD.")
    assert Bridge(1).expect_dialog("j1", "X", "Yes") == OLD_EXPECT


def test_a_named_press_reads_as_asked_not_as_cancelled():
    said = gate.dialog_sentence({"title": "Purge - Confirm Purge", "pressed": "Yes", "closed": True, "asked": True})
    assert "pressed Yes on it, as this call asked" in said
    plain = gate.dialog_sentence({"title": "Select File", "pressed": "Cancel", "closed": True, "asked": False})
    assert "closed it with Cancel" in plain


class Doc:
    def __init__(self):
        self.sent: list[str] = []
        self.vars = {"FILEDIA": 1, "ATTDIA": 1, "CMDACTIVE": 0}

    def GetVariable(self, name):
        return self.vars.get(name, 0)

    def SetVariable(self, name, value):
        self.vars[name] = value

    def SendCommand(self, text):
        self.sent.append(text)

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def command(env, monkeypatch):
    doc = Doc()
    asked: list[tuple] = []
    FakeBridge.expect_answer = None

    def expect_dialog(self, job, title, button):
        asked.append((job, title, button))
        return FakeBridge.expect_answer

    async def now(fn):
        return fn()

    monkeypatch.setattr(FakeBridge, "expect_dialog", expect_dialog, raising=False)
    monkeypatch.setattr(FakeBridge, "dialogs", lambda self, job: [], raising=False)
    monkeypatch.setattr(advanced, "run", now)
    monkeypatch.setattr(advanced, "get_doc", lambda: doc)
    monkeypatch.setattr(advanced, "require_idle", lambda d: None)
    return doc, asked


def test_the_answer_is_named_in_the_job_before_the_command_is_sent(command):
    doc, asked = command
    result = asyncio.run(advanced.autocad_send_command(command="_-PURGE _A * _N", expect_box="Purge - Confirm Purge", press="Yes"))
    assert asked == [("job1", "Purge - Confirm Purge", "Yes")]
    assert doc.sent == ["_-PURGE _A * _N\n"]
    assert not result.startswith("REFUSED")


def test_a_refused_answer_sends_nothing(command):
    doc, asked = command
    FakeBridge.expect_answer = OLD_EXPECT
    result = asyncio.run(advanced.autocad_send_command(command="_-PURGE _A * _N", expect_box="Purge - Confirm Purge", press="Yes"))
    assert doc.sent == []
    assert "plug-in 1.7.0 or newer" in result and result.startswith("REFUSED")


def test_without_the_plug_in_naming_a_button_is_refused(command, monkeypatch):
    doc, _ = command
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")
    result = asyncio.run(advanced.autocad_run_lisp(expression="(+ 1 2)", expect_box="AutoCAD Message", press="OK"))
    assert doc.sent == [] and "needs Heron's plug-in" in result


def test_no_answer_named_changes_nothing_about_a_command(command):
    doc, asked = command
    asyncio.run(advanced.autocad_send_command(command="_REGEN"))
    assert asked == [] and doc.sent == ["_REGEN\n"]
