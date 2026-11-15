"""The Heron gate every tool passes through, with the bridge and COM faked."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
import pythoncom

from autocad_mcp.core import audit, connection, gate
from autocad_mcp.core.bridge import NOT_CONNECTED, NOTHING_SENT, BridgeRefused
from autocad_mcp.core.errors import AutocadError, OutcomeUnknown
from autocad_mcp.core.registry import tool_errors

BUSY = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)


class FakeBridge:
    refuse: str | None = None
    ask_to_keep = False
    answer = "keep"
    calls: list[tuple] = []

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def begin(self, tool, risk, summary, drawing):
        FakeBridge.calls.append(("begin", tool, risk, summary, drawing))
        if FakeBridge.refuse:
            raise BridgeRefused(FakeBridge.refuse)
        return "job1", FakeBridge.ask_to_keep

    def find(self):
        return None if FakeBridge.refuse == NOT_CONNECTED else {"pipeName": "p", "token": "t"}

    def end(self, job, ok, outcome, summary, ms):
        FakeBridge.calls.append(("end", job, ok, outcome))

    def ask_keep(self, job, summary, handles):
        FakeBridge.calls.append(("ask_keep", job, tuple(handles)))
        return FakeBridge.answer


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    FakeBridge.refuse = None
    FakeBridge.ask_to_keep = False
    FakeBridge.answer = "keep"
    FakeBridge.calls = []
    state = {"drawing": r"C:\a.dwg", "marks": 0, "discards": 0, "undo_on": True, "left": []}

    async def probe():
        return 1234, state["drawing"]

    async def mark():
        state["marks"] += 1
        return state["undo_on"]

    async def discard():
        state["discards"] += 1

    async def still_there(handles):
        return [h for h in handles if h in state["left"]]

    monkeypatch.setattr(gate, "Bridge", FakeBridge)
    monkeypatch.setattr(gate, "_probe", probe)
    monkeypatch.setattr(gate, "_mark", mark)
    monkeypatch.setattr(gate, "_discard", discard)
    monkeypatch.setattr(gate, "_still_there", still_there)
    gate.reset(looked_at=state["drawing"])  # as if autocad_status had run on it
    return state


def make_tool(name: str, result: str = '{"created": true, "handle": "2A"}', writes: bool = True, raises=None):
    """A stand-in tool. ``writes`` is what undo_mark records for a real write."""
    calls: list[int] = []

    async def tool() -> str:
        calls.append(1)
        if writes:
            connection.mark_writing()
        if raises is not None:
            raise raises
        return result

    tool.__name__ = name
    return tool_errors(tool), calls


def call(tool) -> str:
    return asyncio.run(tool())


def audit_lines() -> list[dict]:
    lines = []
    for path in audit.audit_dir().glob("audit-*.jsonl"):
        lines += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return lines


def ends() -> list[tuple]:
    return [c for c in FakeBridge.calls if c[0] == "end"]


# --- refusals --------------------------------------------------------------


def test_refused_tool_never_runs_work(env):
    FakeBridge.refuse = "Changes is off. " + NOTHING_SENT
    tool, calls = make_tool("autocad_draw_line")
    result = call(tool)
    assert calls == []
    assert result.startswith("Error: Changes is off.")
    assert result.endswith(NOTHING_SENT)


def test_not_connected_status_answers_without_drawing_data(env):
    FakeBridge.refuse = NOT_CONNECTED
    tool, calls = make_tool("autocad_status", '{"connected": true, "active_drawing": {"name": "secret.dwg"}}', writes=False)
    result = json.loads(call(tool))
    assert calls == []  # a private AutoCAD's drawing is not read out
    heron = result["heron"]
    assert heron["connected"] is False and heron["message"] == NOT_CONNECTED
    # Only Heron's own facts are added: its version and where to look next.
    assert set(heron) <= {"connected", "message", "diagnose", "server_version", "update_waiting"}
    assert "autocad://diagnose" in heron["diagnose"]
    assert "active_drawing" not in result


def test_no_bridge_status_says_heron_is_off(env, monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")
    tool, _ = make_tool("autocad_status", '{"connected": true}', writes=False)
    heron = json.loads(call(tool))["heron"]
    assert heron["connected"] is False
    assert heron["bridge"] == "off"


def test_no_autocad_with_bridge_off_lets_the_tool_answer(env, monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")

    async def no_autocad():
        raise AutocadError("No running AutoCAD instance was found.")

    monkeypatch.setattr(gate, "_probe", no_autocad)
    tool, calls = make_tool("autocad_draw_line")
    call(tool)
    assert calls == [1]


def test_no_autocad_with_bridge_on_refuses(env, monkeypatch):
    async def no_autocad():
        raise AutocadError("No running AutoCAD instance was found.")

    monkeypatch.setattr(gate, "_probe", no_autocad)
    tool, calls = make_tool("autocad_draw_line")
    assert call(tool).startswith("Error: No running AutoCAD")
    assert calls == []


# --- end and audit always happen -----------------------------------------


def test_end_called_on_success_and_failure(env):
    ok_tool, _ = make_tool("autocad_list_layers", "[]", writes=False)
    bad_tool, _ = make_tool("autocad_list_layers", "Error: something broke", writes=False)
    call(ok_tool)
    call(bad_tool)
    assert [e[2] for e in ends()] == [True, False]


def test_cancelled_tool_still_sends_end_and_audit(env):
    tool, _ = make_tool("autocad_draw_line", raises=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        call(tool)
    assert ends()[-1][3] == "cancelled"
    assert audit_lines()[-1]["outcome"] == "cancelled"


def test_audit_line_fields(env):
    tool, _ = make_tool("autocad_list_layers", "[]", writes=False)
    call(tool)
    line = audit_lines()[-1]
    assert set(line) == {"at", "conversation", "tool", "risk", "drawing", "ok", "outcome", "ms"}
    assert (line["tool"], line["risk"], line["drawing"], line["ok"], line["outcome"]) == (
        "autocad_list_layers", "read", r"C:\a.dwg", True, "done"
    )


def test_audit_write_failure_does_not_fail_tool(env, monkeypatch):
    monkeypatch.setattr(audit, "audit_dir", lambda: os.devnull + r"\nope")
    tool, _ = make_tool("autocad_list_layers", "[]", writes=False)
    assert call(tool) == "[]"


# --- wrong-drawing guard -----------------------------------------------------


def test_change_before_any_status_is_refused(env):
    # Units come from autocad_status: nothing is drawn in a drawing Heron has
    # not checked, so a fresh chat cannot draw in inches thinking millimetres.
    gate.reset()
    draw, calls = make_tool("autocad_draw_line")
    result = call(draw)
    assert calls == []
    assert "autocad_status" in result and "units" in result
    assert result.endswith(NOTHING_SENT)
    status, _ = make_tool("autocad_status", '{"connected": true}', writes=False)
    call(status)
    call(draw)
    assert calls == [1]


def test_reading_does_not_count_as_checking_units(env):
    gate.reset()
    read, _ = make_tool("autocad_list_layers", "[]", writes=False)
    call(read)
    draw, calls = make_tool("autocad_draw_line")
    call(draw)
    assert calls == []


def test_wrong_drawing_refused_for_change(env):
    look, _ = make_tool("autocad_list_layers", "[]", writes=False)
    call(look)
    env["drawing"] = r"C:\b.dwg"
    tool, calls = make_tool("autocad_draw_line")
    result = call(tool)
    assert calls == []
    assert r"C:\a.dwg" in result and r"C:\b.dwg" in result
    assert result.endswith(NOTHING_SENT)


def test_guard_is_re_armed_only_by_status(env):
    look, _ = make_tool("autocad_list_layers", "[]", writes=False)
    call(look)
    env["drawing"] = r"C:\b.dwg"
    read, read_calls = make_tool("autocad_list_entities", "[]", writes=False)
    call(read)
    assert read_calls == [1]  # reading the other drawing is fine...
    draw, draw_calls = make_tool("autocad_draw_line")
    call(draw)
    assert draw_calls == []  # ...but it does not move changes there
    status, _ = make_tool("autocad_status", '{"connected": true}', writes=False)
    call(status)
    call(draw)
    assert draw_calls == [1]


# --- Keep or Discard -----------------------------------------------------------


def test_ask_to_keep_off_never_asks_or_marks(env):
    tool, _ = make_tool("autocad_draw_line")
    call(tool)
    assert not [c for c in FakeBridge.calls if c[0] == "ask_keep"]
    assert env["marks"] == 0


def test_dry_run_change_is_not_asked(env):
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"
    tool, _ = make_tool("autocad_delete_entities", '{"confirmed": false, "would_delete": [{"handle": "2A"}]}', writes=False)
    result = call(tool)
    assert not [c for c in FakeBridge.calls if c[0] == "ask_keep"]
    assert env["discards"] == 0
    assert "would_delete" in result


def test_discard_goes_back_to_the_mark(env):
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = call(tool)
    assert env["marks"] == 1
    assert ("ask_keep", "job1", ("2A",)) in FakeBridge.calls
    assert env["discards"] == 1
    assert result == "Discarded: nothing was kept."
    assert audit_lines()[-1]["outcome"] == "discarded"


def test_discard_that_did_not_take_is_reported(env):
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"
    env["left"] = ["2A"]
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = call(tool)
    assert result.startswith("Error: Discard did not take")
    assert "2A" in result


def test_discard_with_undo_off_says_so(env):
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"
    env["undo_on"] = False
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = call(tool)
    assert env["discards"] == 0
    assert "UNDO is off" in result


def test_discard_error_is_reported_and_end_still_sent(env, monkeypatch):
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"

    async def broken():
        raise AutocadError("AutoCAD stayed busy")

    monkeypatch.setattr(gate, "_discard", broken)
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = call(tool)
    assert result.startswith("Error: Discard failed")
    assert ends()[-1][1] == "job1"


def test_keep_returns_result_unchanged(env):
    FakeBridge.ask_to_keep = True
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    assert call(tool) == '{"created": true, "handle": "2A"}'
    assert env["discards"] == 0


def test_unknown_answer_keeps_and_says_so(env):
    # The plug-in could not be asked (pipe broke): never undo on a guess.
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "unknown"
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = json.loads(call(tool))
    assert env["discards"] == 0
    assert result["handle"] == "2A"
    assert "could not ask" in result["heron_note"]


def test_read_tools_are_never_asked_to_keep(env):
    FakeBridge.ask_to_keep = True
    tool, _ = make_tool("autocad_get_entity", '{"handle": "2A"}', writes=False)
    call(tool)
    assert not [c for c in FakeBridge.calls if c[0] == "ask_keep"]


# --- retry, bridge off, read-back, flags ---------------------------------------


def test_no_retry_after_write_began(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    attempts: list[int] = []

    def work():
        attempts.append(1)
        connection.mark_writing()
        raise BUSY

    with pytest.raises(OutcomeUnknown) as err:
        connection._with_retry(work)
    assert attempts == [1]
    assert "Read the drawing back before retrying" in str(err.value)


def test_retry_still_happens_before_write(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    attempts: list[int] = []

    def work():
        attempts.append(1)
        if len(attempts) < 3:
            raise BUSY
        connection.mark_writing()
        return "drawn"

    assert connection._with_retry(work) == "drawn"
    assert len(attempts) == 3


def test_bridge_off_skips_plugin_but_keeps_audit(env, monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")
    tool, calls = make_tool("autocad_draw_line")
    call(tool)
    assert calls == [1]
    assert FakeBridge.calls == []
    assert audit_lines()[-1]["tool"] == "autocad_draw_line"


class _Obj:
    def __init__(self, name, handle="2A", doc=None):
        self.ObjectName = name
        self.Handle = handle
        self.Layer = "0"
        self.Document = doc


class _Doc:
    def __init__(self, found):
        self.found = found

    def HandleToObject(self, handle):
        if self.found is None:
            raise RuntimeError("no such handle")
        return self.found


def test_created_payload_reads_back(monkeypatch):
    from autocad_mcp.tools import _shared

    monkeypatch.setattr(_shared, "describe", lambda e, include_geometry=False: {"type": "line"})
    good = _Obj("AcDbLine", doc=_Doc(_Obj("AcDbLine")))
    assert _shared.created_payload(good, {})["verified"] is True
    missing = _Obj("AcDbLine", doc=_Doc(None))
    payload = _shared.created_payload(missing, {})
    assert payload["verified"] is False
    assert "could not be read back" in payload["warning"]


def test_no_bridge_flag_switches_bridge_off(monkeypatch):
    from autocad_mcp import server

    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    server.apply_options(server.build_parser().parse_args(["--no-bridge"]))
    assert os.environ["HERON_AUTOCAD_BRIDGE"] == "off"


def test_batch_draw_marks_the_write():
    # batch_draw writes through LISP, not undo_mark: it must still count as a write.
    import inspect

    from autocad_mcp.tools import batch

    assert "mark_writing()" in inspect.getsource(batch)


def test_not_connected_is_said_before_the_units_rule(env):
    # Disconnected and not yet checked: "press Heron" is the useful message.
    gate.reset()
    FakeBridge.refuse = NOT_CONNECTED
    draw, calls = make_tool("autocad_draw_line")
    assert call(draw) == "Error: " + NOT_CONNECTED
    assert calls == []


def test_quiet_sender_exists_only_inside_a_job(env):
    seen = []

    class Quiet(FakeBridge):
        def send_quiet(self, job, lines):
            seen.append((job, list(lines)))
            return True

    gate.Bridge = Quiet
    assert gate.quiet_sender() is None
    captured = {}

    async def tool() -> str:
        captured["sender"] = gate.quiet_sender()
        return captured["sender"](["(a)", "(b)"]) and '{"ok": true}'

    tool.__name__ = "autocad_batch_draw"
    call(tool_errors(tool))
    assert seen == [("job1", ["(a)", "(b)"])]
    assert gate.quiet_sender() is None


def test_a_plugin_operation_runs_in_its_job_and_keep_or_discard_covers_it(env, monkeypatch):
    """The plug-in's own operations (D-40), through the real gate: the operation goes
    to this call's job, counts as a write, and Discard takes away what it made."""
    from autocad_mcp.tools import superhatch

    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"
    runs = []

    def run(self, job, operation, args):
        runs.append((job, operation, args["block"]))
        return {"created": True, "handle": "5D", "block": "SUPERHATCH-1", "tiles": 4}

    class Made:
        Handle, ObjectName, Layer = "5D", "AcDbBlockReference", "0"

        @property
        def Document(self):
            return self

        def HandleToObject(self, handle):
            return Made()

    async def now(fn):
        return fn()

    monkeypatch.setattr(FakeBridge, "run", run, raising=False)
    monkeypatch.setattr(superhatch, "run", now)
    monkeypatch.setattr(superhatch, "get_doc", Made)
    monkeypatch.setattr(superhatch, "require_idle", lambda doc: None)

    result = asyncio.run(superhatch.autocad_super_hatch(boundary="2A", block="PAVER"))
    assert runs == [("job1", "super_hatch", "PAVER")]
    assert env["marks"] == 1
    assert ("ask_keep", "job1", ("5D",)) in FakeBridge.calls
    assert env["discards"] == 1 and result == "Discarded: nothing was kept."
