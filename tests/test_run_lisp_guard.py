"""autocad_run_lisp never leaves AutoCAD stuck in a command (bedroom model, 2026-11-05).

A CAMERA or DVIEW left waiting at a prompt swallowed the result write and
every later call waited until someone pressed Esc. Running snaps also caught
the typed camera points. The wrapper now cancels a command left open before it
writes the result, and the server turns snaps off for the call.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.tools import advanced
from autocad_mcp.tools.advanced import (
    LISP_CANCELLED_VAR,
    LISP_RESULT_VAR,
    lisp_wrapper,
)


class Doc:
    """Answers the wrapper the way AutoCAD would."""

    def __init__(self, result="42", cancelled="", fail=False):
        self.variables = {LISP_RESULT_VAR: "mine", LISP_CANCELLED_VAR: "also mine",
                          "OSMODE": 675, "CMDACTIVE": 0}
        self.result, self.cancelled, self.fail = result, cancelled, fail
        self.sent: list[str] = []
        self.osmode_during_send = None

    def GetVariable(self, name):
        return self.variables[name]

    def SetVariable(self, name, value):
        self.variables[name] = value

    def SendCommand(self, text):
        self.sent.append(text)
        self.osmode_during_send = self.variables["OSMODE"]
        if self.fail:
            raise RuntimeError("bad LISP")
        self.variables[LISP_CANCELLED_VAR] = self.cancelled
        self.variables[LISP_RESULT_VAR] = self.result

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def make(monkeypatch):
    def build(**kwargs):
        doc = Doc(**kwargs)

        async def run(fn):
            return fn()

        monkeypatch.setattr(advanced, "run", run)
        monkeypatch.setattr(advanced, "get_doc", lambda: doc)
        monkeypatch.setattr(advanced, "require_idle", lambda d: None)
        return doc

    return build


def call(expression):
    return asyncio.run(advanced.autocad_run_lisp(expression=expression))


class TestWrapper:
    def test_the_command_is_cancelled_before_the_result_is_written(self):
        text = lisp_wrapper('(command "_.CAMERA" "0,0,0" "1,1,1")')
        assert text.index("(command))") < text.index(f'(setvar "{LISP_RESULT_VAR}"')
        assert text.index(f'(setvar "{LISP_CANCELLED_VAR}"') < text.index(f'(setvar "{LISP_RESULT_VAR}"')

    def test_only_a_waiting_command_counts_not_the_lisp_itself(self):
        # Bit 32 (AutoLISP running) is set while the wrapper runs.
        assert '(logand (getvar "CMDACTIVE") 3)' in lisp_wrapper("(+ 1 2)")

    def test_the_cancel_loop_is_bounded(self):
        assert "(repeat 4 " in lisp_wrapper("(+ 1 2)")
        assert "(while" not in lisp_wrapper("(+ 1 2)")

    def test_nothing_is_echoed_into_a_prompt(self):
        assert lisp_wrapper("(+ 1 2)").endswith("(princ)\n")

    def test_the_wrapper_is_balanced(self):
        text = lisp_wrapper('(strcat "a" "b")')
        assert text.count("(") == text.count(")")
        assert text.count('"') % 2 == 0


class TestTool:
    def test_a_plain_expression_returns_its_value_and_no_cancel(self, make):
        doc = make(result="42")
        answer = json.loads(call("(* 6 7)"))
        assert answer["result"] == "42"
        assert answer["timed_out"] is False
        assert "cancelled_command" not in answer
        assert "(* 6 7)" in doc.sent[0]

    def test_a_command_left_open_is_named(self, make):
        make(result="(1 CAMERA)", cancelled="CAMERA")
        answer = json.loads(call('(command "_.CAMERA" "0,0,0" "1,1,1")'))
        assert answer["cancelled_command"] == "CAMERA"
        assert "CAMERA" in answer["note"]

    def test_snaps_are_off_for_the_call_and_put_back(self, make):
        doc = make()
        call("(+ 1 2)")
        assert doc.osmode_during_send == 0
        assert doc.variables["OSMODE"] == 675

    def test_snaps_are_put_back_when_autocad_refuses_the_expression(self, make):
        doc = make(fail=True)
        answer = call("(+ 1 2)")
        assert answer.startswith("Error")
        assert doc.variables["OSMODE"] == 675

    def test_the_modellers_own_variables_are_put_back(self, make):
        doc = make(cancelled="DVIEW")
        call("(+ 1 2)")
        assert doc.variables[LISP_RESULT_VAR] == "mine"
        assert doc.variables[LISP_CANCELLED_VAR] == "also mine"
