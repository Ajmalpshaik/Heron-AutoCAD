"""A busy retry of autocad_run_lisp asks the plug-in for its named box button once, not twice (#210, D-133).

The plug-in takes one named button per job (D-74), and a busy AutoCAD makes the retry loop run
the tool's work again inside the same job. Before, that asked a second time, was refused, and the
chat read "give the box's exact title and one button, once per job" when AutoCAD was only busy.
Offline, with stand-ins for the COM document and the plug-in: not run in AutoCAD.
"""

from __future__ import annotations

import asyncio

import pytest
import pythoncom
import test_gate
from test_gate import FakeBridge

from autocad_mcp.core import connection
from autocad_mcp.tools import advanced
from autocad_mcp.tools.advanced import (
    LISP_CANCELLED_VAR,
    LISP_RESULT_VAR,
    LISP_SENTINEL,
)

env = test_gate.env  # the gate with the bridge and COM faked

BUSY = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)
ONCE_PER_JOB = "Heron takes one named button per job: give the box's exact title and one button, once per job."


class Doc:
    """Turns the first ``busy_sets`` writes of the result variable away, then answers like AutoCAD."""

    def __init__(self, busy_sets: int = 0) -> None:
        self.busy_sets = busy_sets
        self.variables = {LISP_RESULT_VAR: "mine", LISP_CANCELLED_VAR: "", "OSMODE": 675, "CMDACTIVE": 0}
        self.sent: list[str] = []

    def GetVariable(self, name):  # noqa: N802 - COM name
        return self.variables[name]

    def SetVariable(self, name, value):  # noqa: N802 - COM name
        if name == LISP_RESULT_VAR and value == LISP_SENTINEL and self.busy_sets:
            self.busy_sets -= 1
            raise BUSY
        self.variables[name] = value

    def SendCommand(self, text):  # noqa: N802 - COM name
        self.sent.append(text)
        self.variables[LISP_CANCELLED_VAR] = ""
        self.variables[LISP_RESULT_VAR] = "3"

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass


@pytest.fixture
def lisp(env, monkeypatch):
    """autocad_run_lisp through the real retry loop, with a plug-in that takes one named button per job."""
    asked: list[tuple] = []
    refusal: dict[str, str | None] = {"first": None}

    def expect_dialog(self, job, title, button):
        again = any(a[0] == job for a in asked)
        asked.append((job, title, button))
        return ONCE_PER_JOB if again else refusal["first"]

    async def run(fn):
        return connection._with_retry(fn)

    holder: dict[str, Doc] = {}
    monkeypatch.setattr(FakeBridge, "expect_dialog", expect_dialog, raising=False)
    monkeypatch.setattr(FakeBridge, "dialogs", lambda self, job: [], raising=False)
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    monkeypatch.setattr(advanced, "run", run)
    monkeypatch.setattr(advanced, "get_doc", lambda: holder["doc"])
    monkeypatch.setattr(advanced, "require_idle", lambda d: None)

    def call(doc: Doc) -> str:
        holder["doc"] = doc
        return asyncio.run(advanced.autocad_run_lisp(expression="(+ 1 2)", expect_box="AutoCAD Message", press="OK"))

    return call, asked, refusal


def test_a_busy_retry_does_not_ask_the_plug_in_a_second_time(lisp):
    call, asked, _ = lisp
    doc = Doc(busy_sets=1)
    result = call(doc)
    assert asked == [("job1", "AutoCAD Message", "OK")]  # once, though the work ran twice
    assert ONCE_PER_JOB not in result
    assert not result.startswith("Error")
    assert len(doc.sent) == 1  # the busy turn-away sent nothing; the retry sent the code once
    assert '"result": "3"' in result


def test_busy_all_the_way_gives_the_busy_answer_not_the_once_per_job_one(lisp, monkeypatch):
    call, asked, _ = lisp
    monkeypatch.setattr(connection, "RETRY_ATTEMPTS", 3)
    result = call(Doc(busy_sets=99))
    assert "stayed busy" in result
    assert "once per job" not in result
    assert asked == [("job1", "AutoCAD Message", "OK")]


def test_a_real_refusal_of_the_first_ask_still_stops_the_call(lisp):
    # The fix must not hide the plug-in's own refusal: nothing is sent.
    call, asked, refusal = lisp
    refusal["first"] = "Heron cannot press a named button here."
    doc = Doc()
    result = call(doc)
    assert asked == [("job1", "AutoCAD Message", "OK")]
    assert "Heron cannot press a named button here." in result
    assert doc.sent == []
