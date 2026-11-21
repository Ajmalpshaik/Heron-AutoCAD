"""A busy answer names the command AutoCAD is in, and whether the change happened (#47).

Before, only the plug-in's own operations said "it is still in the HATCH
command"; a server-side call answered "Outcome unknown: AutoCAD went busy" and
no more (NEEDS-CHECKING D8, D33). Now the gate asks the plug-in's command
tracker (through ping, on its pipe thread, so it answers while AutoCAD is busy)
and puts the command, with what the plug-in counted so far, in the plain line.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pythoncom

from autocad_mcp.core import answers, connection, gate
from autocad_mcp.core.bridge import Bridge
from autocad_mcp.core.errors import AutocadError, OutcomeUnknown
from autocad_mcp.core.registry import tool_errors

BUSY = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)


# --- what the plug-in says ---------------------------------------------------------------


@pytest.mark.parametrize(
    "reply, expected",
    [
        ({"ok": True, "command": "HATCH"}, (True, "HATCH")),
        ({"ok": True, "command": None}, (True, None)),
        ({"ok": True, "command": "  "}, (True, None)),
        ({"ok": True}, (False, None)),  # a plug-in older than #47 does not say
        ({"ok": False, "message": "wrong session"}, (False, None)),
    ],
)
def test_the_bridge_reads_the_command_from_ping(monkeypatch, reply, expected):
    monkeypatch.setattr(Bridge, "call", lambda self, op, **kw: reply)
    assert Bridge(1).current_command() == expected


def test_a_plugin_that_cannot_be_asked_is_not_known(monkeypatch):
    def refuse(self, op, **kw):
        raise AutocadError("not connected")

    monkeypatch.setattr(Bridge, "call", refuse)
    assert Bridge(1).current_command() == (False, None)


@pytest.mark.parametrize(
    "known, command, words",
    [
        (True, "HATCH", "still in the HATCH command"),
        (True, "AutoLISP", "still evaluating AutoLISP"),
        (True, None, "in no command now"),
        (False, None, ""),
    ],
)
def test_where_a_busy_autocad_is(known, command, words):
    where = answers.busy_where(known, command)
    assert (words in where) if words else where == ""


# --- the plain line ----------------------------------------------------------------------


def facts(text="Error: " + OutcomeUnknown.DEFAULT, ok=False, outcome="unknown", counted=None, **kw):
    return answers.Facts(text, ok=ok, outcome=outcome, counted=counted, wrote=True, **kw)


HATCH = answers.busy_where(True, "HATCH")


class TestLine:
    def test_busy_part_way_names_the_command_and_what_was_counted(self):
        line = answers.line(facts(counted={"added": 2, "modified": 0, "erased": 0}, busy=True, where=HATCH))
        assert line.startswith("OUTCOME UNKNOWN - AutoCAD went busy part-way (it is still in the HATCH command)")
        assert "2 added, 0 changed, 0 erased so far" in line

    def test_busy_with_nothing_counted_says_so(self):
        line = answers.line(facts(counted={"added": 0, "modified": 0, "erased": 0}, busy=True, where=HATCH))
        assert "counted no drawing object added, changed or erased so far" in line

    def test_busy_and_not_counted_says_it_could_not_count(self):
        line = answers.line(facts(busy=True, where=HATCH))
        assert "could not count what changed" in line

    def test_without_the_tracker_the_line_still_says_busy(self):
        line = answers.line(facts(counted={"added": 1, "modified": 0, "erased": 0}, busy=True))
        assert line.startswith("OUTCOME UNKNOWN - AutoCAD went busy part-way, after 1 added")

    def test_busy_before_anything_was_taken_is_refused_and_named(self):
        text = "Error: AutoCAD stayed busy for 10s and never accepted the request."
        line = answers.line(answers.Facts(text, ok=False, outcome="failed", counted={"added": 0, "modified": 0, "erased": 0},
                                          busy=True, where=HATCH))
        assert line == (
            "REFUSED - AutoCAD stayed busy (it is still in the HATCH command) and never took the request; "
            "nothing was changed."
        )

    def test_an_answer_that_never_heard_how_it_ended_is_not_done(self):
        text = json.dumps({"result": None, "timed_out": True})
        line = answers.line(answers.Facts(text, ok=True, outcome="done", counted={"added": 0, "modified": 0, "erased": 0},
                                          wrote=True, can_count=False, busy=True, where=HATCH))
        assert line.startswith("OUTCOME UNKNOWN - AutoCAD stayed busy (it is still in the HATCH command)")

    def test_a_lisp_wait_that_ran_out_is_not_done_either(self):
        text = json.dumps({"result": None, "timed_out": True})
        line = answers.line(answers.Facts(text, ok=True, outcome="done", counted={"added": 3, "modified": 0, "erased": 0},
                                          wrote=True, can_count=False))
        assert line.startswith("OUTCOME UNKNOWN - AutoCAD did not answer within the wait")
        assert "3 added" in line

    def test_a_job_that_was_not_busy_reads_as_before(self):
        line = answers.line(answers.Facts('{"created": true}', ok=True, outcome="done",
                                          counted={"added": 1, "modified": 0, "erased": 0}, wrote=True))
        assert line == "DONE - 1 added, 0 changed, 0 erased."


# --- the gate ----------------------------------------------------------------------------


class FakeBridge:
    command: tuple[bool, str | None] = (True, "HATCH")
    counted: dict | None = None
    asked: list[str] = []

    def __init__(self, pid):
        self.pid = pid

    def begin(self, tool, risk, summary, drawing):
        return "job1", False

    def find(self):
        return {"pipeName": "p", "token": "t"}

    def end(self, *args):
        pass

    def changes(self, job):
        return FakeBridge.counted

    def dialogs(self, job):
        return []

    def current_command(self):
        FakeBridge.asked.append("ping")
        return FakeBridge.command


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    FakeBridge.command, FakeBridge.counted, FakeBridge.asked = (True, "HATCH"), None, []

    async def probe():
        return 1234, r"C:\a.dwg"

    monkeypatch.setattr(gate, "Bridge", FakeBridge)
    monkeypatch.setattr(gate, "_probe", probe)
    gate.reset(looked_at=r"C:\a.dwg")


def tool(name, work):
    """A stand-in tool whose COM work goes through the real retry loop."""

    async def body() -> str:
        return connection._with_retry(work)

    body.__name__ = name
    return tool_errors(body)


def busy_after_a_write():
    connection.mark_writing()
    raise BUSY


def busy_from_the_start():
    raise BUSY


def test_a_change_that_went_busy_names_the_command_and_the_count(env):
    FakeBridge.counted = {"added": 4, "modified": 0, "erased": 0, "erased_handles": []}
    answer = asyncio.run(tool("autocad_draw_line", busy_after_a_write)())
    first, rest = answers.split(answer)
    assert first.startswith("OUTCOME UNKNOWN - AutoCAD went busy part-way (it is still in the HATCH command), "
                            "after 4 added, 0 changed, 0 erased so far.")
    assert rest.startswith("Error: Outcome unknown")
    assert FakeBridge.asked == ["ping"]


def test_a_change_autocad_never_took_is_refused_and_names_the_command(env, monkeypatch):
    monkeypatch.setattr(connection, "RETRY_ATTEMPTS", 2)
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 0, "erased_handles": []}
    answer = asyncio.run(tool("autocad_draw_line", busy_from_the_start)())
    first, _ = answers.split(answer)
    assert first == ("REFUSED - AutoCAD stayed busy (it is still in the HATCH command) and never took the "
                     "request; nothing was changed.")


def test_a_read_that_went_busy_says_where_autocad_is_in_its_answer(env, monkeypatch):
    monkeypatch.setattr(connection, "RETRY_ATTEMPTS", 2)
    FakeBridge.command = (True, None)
    answer = asyncio.run(tool("autocad_get_entity", busy_from_the_start)())
    assert answer.startswith("Error: AutoCAD stayed busy")
    assert "AutoCAD was busy: it is in no command now" in answer


def test_a_call_that_was_not_busy_never_asks(env):
    FakeBridge.counted = {"added": 1, "modified": 0, "erased": 0, "erased_handles": []}

    def draws():
        connection.mark_writing()
        return '{"created": true, "handle": "2A"}'

    answers.split(asyncio.run(tool("autocad_draw_line", draws)()))
    assert FakeBridge.asked == []


def test_an_older_plugin_without_the_tracker_still_answers(env):
    FakeBridge.command = (False, None)
    answer = asyncio.run(tool("autocad_draw_line", busy_after_a_write)())
    assert answers.split(answer)[0].startswith("OUTCOME UNKNOWN - AutoCAD went busy part-way, and the plug-in")


def test_a_fake_bridge_without_the_question_is_not_known():
    class Old:
        pass

    assert gate._command_of(Old()) == (False, None)


def test_the_retry_loop_counts_its_busy_endings(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    monkeypatch.setattr(connection, "RETRY_ATTEMPTS", 2)
    before = connection.busy_count()
    with pytest.raises(OutcomeUnknown):
        connection._with_retry(busy_after_a_write)
    with pytest.raises(AutocadError):
        connection._with_retry(busy_from_the_start)
    assert connection.busy_count() == before + 2
    assert connection._with_retry(lambda: "fine") == "fine"
    assert connection.busy_count() == before + 2


def test_a_lisp_answer_autocad_never_let_heron_read_counts_as_busy(monkeypatch):
    from autocad_mcp.tools import advanced

    class Doc:
        variables = {advanced.LISP_RESULT_VAR: "", advanced.LISP_CANCELLED_VAR: "", "OSMODE": 0}
        sent: list[str] = []

        def GetVariable(self, name):
            if self.sent and name == advanced.LISP_RESULT_VAR:
                raise BUSY
            return self.variables[name]

        def SetVariable(self, name, value):
            self.variables[name] = value

        def SendCommand(self, text):
            self.sent.append(text)

        def StartUndoMark(self):
            pass

        def EndUndoMark(self):
            pass

    async def run(fn):
        return fn()

    monkeypatch.setattr(advanced, "run", run)
    monkeypatch.setattr(advanced, "get_doc", lambda: Doc())
    monkeypatch.setattr(advanced, "require_idle", lambda d: None)
    monkeypatch.setattr(advanced, "LISP_POLL_ATTEMPTS", 2)
    monkeypatch.setattr(advanced.time, "sleep", lambda s: None)
    before = connection.busy_count()
    answer = json.loads(asyncio.run(advanced.autocad_run_lisp(expression="(+ 1 2)")))
    assert answer["timed_out"] is True
    assert connection.busy_count() == before + 1
