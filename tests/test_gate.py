"""The Heron gate every tool passes through, with the bridge and COM faked."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
import pythoncom

from autocad_mcp.core import answers, audit, connection, gate
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

    marked_at_end: list = []

    def end(self, job, ok, outcome, summary, ms, marked=False):
        FakeBridge.calls.append(("end", job, ok, outcome))
        FakeBridge.marked_at_end.append(marked)

    def ask_keep(self, job, summary, handles):
        FakeBridge.calls.append(("ask_keep", job, tuple(handles)))
        return FakeBridge.answer

    counted: dict | None = None
    erase_answer: dict = {"answer": "restored", "restored": 0}

    def changes(self, job):
        FakeBridge.calls.append(("changes", job))
        return FakeBridge.counted

    erase_whole: list = []

    def ask_erase(self, job, summary, *whole):
        # Every other tool asks with exactly (job, summary), as before D-136; a replace job adds True.
        FakeBridge.calls.append(("ask_erase", job, summary))
        FakeBridge.erase_whole.append(whole)
        return FakeBridge.erase_answer

    boxes: list = []
    dialogs_asked: list = []

    def dialogs(self, job):
        FakeBridge.dialogs_asked.append(job)
        return FakeBridge.boxes


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
    FakeBridge.refuse = None
    FakeBridge.ask_to_keep = False
    FakeBridge.answer = "keep"
    FakeBridge.calls = []
    FakeBridge.counted = None
    FakeBridge.erase_answer = {"answer": "restored", "restored": 0}
    FakeBridge.erase_whole = []
    FakeBridge.boxes = []
    FakeBridge.dialogs_asked = []
    FakeBridge.marked_at_end = []
    # "left": new objects a Discard did not take away. "back_on_undo": erased objects that UNDO Back
    # brings back, so they are "there" after a Discard (D-136).
    state = {"drawing": r"C:\a.dwg", "marks": 0, "discards": 0, "undo_on": True, "left": [],
             "there": set(), "back_on_undo": set()}

    async def probe():
        return 1234, state["drawing"]

    async def mark():
        state["marks"] += 1
        return state["undo_on"]

    async def discard():
        state["discards"] += 1
        state["there"] |= state["back_on_undo"]

    async def still_there(handles):
        return [h for h in handles if h in state["left"] or h in state["there"]]

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


def answered(result: str, word: str) -> str:
    """A change job's answer starts with its plain line (D-62): check the word, give the rest."""
    first, rest = answers.split(result)
    assert first is not None and first.startswith(word + " - "), result
    return rest


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
    result = answered(call(tool), "REFUSED")
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
    assert answered(call(tool), "REFUSED").startswith("Error: No running AutoCAD")
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
    result = answered(call(tool), "NOTHING CHANGED")
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
    result = answered(call(tool), "OUTCOME UNKNOWN")
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


def test_reset_forgets_why_an_earlier_job_had_no_mark(monkeypatch):
    # #254: a stale "AutoCAD was in a command" from an earlier job (or test) must not be a later reason.
    monkeypatch.setattr(gate, "_last_drawing", None)
    monkeypatch.setattr(gate, "_checked_mark", None)
    monkeypatch.setattr(gate, "_no_mark", gate.NO_MARK_IN_COMMAND)
    gate.reset()
    assert gate._no_mark == ""
    assert gate._no_mark_reason()[0].startswith("UNDO is off")


def test_discard_when_autocad_was_in_a_command_says_so_not_undo_off(env, monkeypatch):
    # #206: the mark was skipped because AutoCAD was in a command; UNDOCTL was never the reason.
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"
    monkeypatch.setattr(gate, "_no_mark", "")  # put back after the test

    async def in_command():
        env["marks"] += 1
        gate._no_mark = gate.NO_MARK_IN_COMMAND
        return False

    monkeypatch.setattr(gate, "_mark", in_command)
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = call(tool)
    assert env["discards"] == 0
    assert "AutoCAD was in a command" in result and "UNDOCTL" not in result
    assert FakeBridge.marked_at_end == [False]


@pytest.mark.parametrize("ask,undo_on,marked", [(True, True, True), (True, False, False), (False, True, False)])
def test_end_tells_the_plug_in_whether_the_mark_is_really_there(env, ask, undo_on, marked):
    # #206: the palette's Undo goes back to a mark only on the server's word, never on Ask to Keep.
    FakeBridge.ask_to_keep = ask
    env["undo_on"] = undo_on
    tool, _ = make_tool("autocad_draw_line")
    call(tool)
    assert FakeBridge.marked_at_end == [marked]


def test_a_marked_job_that_wrote_nothing_leaves_nothing_to_undo(env):
    # #209: its empty mark is the newest one now, so UNDO Back for the older job would stop there.
    FakeBridge.ask_to_keep = True
    draw, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    call(draw)
    assert gate.last_change() is not None and gate.last_change()["marked"] is True
    refused, _ = make_tool("autocad_move_entities", "Error: Invalid input - no handles", writes=False)
    call(refused)
    assert env["marks"] == 2
    assert gate.last_change() is None


def test_a_kept_job_without_a_mark_counts_the_questions_zoom(env):
    # D-130: the Keep question zoomed to the job; with no mark, one UNDO step would be that zoom.
    FakeBridge.ask_to_keep = True
    env["undo_on"] = False
    draw, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    call(draw)
    assert gate.last_change()["marked"] is False and gate.last_change()["views_since"] == 1


def test_a_kept_job_with_a_mark_is_undone_back_to_it(env):
    FakeBridge.ask_to_keep = True
    draw, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    call(draw)
    assert gate.last_change()["marked"] is True


def test_bridge_end_puts_the_mark_on_the_wire(monkeypatch):
    # #206: the palette's Undo reads "marked" from end; the gate tests use a fake bridge, so check the real one.
    from autocad_mcp.core.bridge import Bridge

    sent = []
    monkeypatch.setattr(Bridge, "call", lambda self, op, **fields: sent.append((op, fields)) or {"ok": True})
    Bridge(1).end("j1", True, "done", "Draw Line", 12, True)
    Bridge(1).end("j2", True, "done", "Draw Line", 12)
    assert [(op, fields["job"], fields["marked"]) for op, fields in sent] == [("end", "j1", True), ("end", "j2", False)]


def test_an_unmarked_job_that_wrote_nothing_keeps_the_last_change(env):
    draw, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    call(draw)
    refused, _ = make_tool("autocad_move_entities", "Error: Invalid input - no handles", writes=False)
    call(refused)
    assert env["marks"] == 0
    assert gate.last_change() is not None


def test_discard_error_is_reported_and_end_still_sent(env, monkeypatch):
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "discard"

    async def broken():
        raise AutocadError("AutoCAD stayed busy")

    monkeypatch.setattr(gate, "_discard", broken)
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = answered(call(tool), "OUTCOME UNKNOWN")
    assert result.startswith("Error: Discard failed")
    assert ends()[-1][1] == "job1"


def test_keep_returns_result_unchanged(env):
    FakeBridge.ask_to_keep = True
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    assert answered(call(tool), "DONE") == '{"created": true, "handle": "2A"}'
    assert env["discards"] == 0


def test_unknown_answer_keeps_and_says_so(env):
    # The plug-in could not be asked (pipe broke): never undo on a guess.
    FakeBridge.ask_to_keep = True
    FakeBridge.answer = "unknown"
    tool, _ = make_tool("autocad_draw_line", '{"created": true, "handle": "2A"}')
    result = json.loads(answered(call(tool), "DONE"))
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
    assert answered(call(draw), "REFUSED") == "Error: " + NOT_CONNECTED
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
    assert env["discards"] == 1 and answered(result, "NOTHING CHANGED") == "Discarded: nothing was kept."


# ---------------------------------------------------------------------------
# What the job really did, and the erase question (D-50)
# ---------------------------------------------------------------------------


def test_the_plug_ins_count_is_added_to_the_result(env):
    FakeBridge.counted = {"added": 3, "modified": 1, "erased": 0, "erased_handles": []}
    draw, _ = make_tool("autocad_draw_line")
    result = json.loads(answered(call(draw), "DONE"))
    assert result["heron_changes"] == {"added": 3, "modified": 1, "erased": 0}
    assert not any(c[0] == "ask_erase" for c in FakeBridge.calls)


def test_an_erase_is_asked_even_with_ask_to_keep_off(env):
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 4, "erased_handles": ["A", "B", "C", "D"]}
    FakeBridge.erase_answer = {"answer": "restored", "restored": 4}
    send, _ = make_tool("autocad_send_command", '{"sent": "_ERASE"}')
    whole = call(send)
    result = json.loads(answered(whole, "DONE"))
    assert [c[1] for c in FakeBridge.calls if c[0] == "ask_erase"] == ["job1"]
    assert "brought back (4 restored)" in result["heron_note"]
    # #209: all 4 came back, so neither the line nor the count says "erased". A raw command may
    # still have changed a setting, so it stays DONE with the not-counted note.
    first = answers.split(whole)[0]
    assert "0 added, 0 changed, 4 erased" not in first and "no drawing object was added, changed or erased" in first
    assert "all 4 erased object(s) brought back" in first
    assert result["heron_changes"] == {"added": 0, "modified": 0, "erased": 0}


ERASED_4 = {"added": 0, "modified": 0, "erased": 4, "erased_handles": ["A", "B", "C", "D"]}


def test_a_change_whose_erase_was_all_brought_back_is_nothing_changed(env):
    # #209: it used to say "DONE - 0 added, 0 changed, 4 erased." after all 4 were restored.
    FakeBridge.counted = dict(ERASED_4)
    FakeBridge.erase_answer = {"answer": "restored", "restored": 4, "asked": True, "erased": 4}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 4}')
    whole = call(erase)
    first = answers.split(whole)[0]
    assert first.startswith("NOTHING CHANGED - the job erased 4 object(s)"), first
    assert "all of them brought back" in first
    result = json.loads(answered(whole, "NOTHING CHANGED"))
    assert result["heron_changes"] == {"added": 0, "modified": 0, "erased": 0}
    assert "brought back (4 restored)" in result["heron_note"]
    assert gate.activity()[0]["changes"] == {"added": 0, "modified": 0, "erased": 0}


def test_all_brought_back_but_something_was_also_made_is_done_with_none_erased(env):
    FakeBridge.counted = {"added": 2, "modified": 0, "erased": 3, "erased_handles": ["A", "B", "C"]}
    FakeBridge.erase_answer = {"answer": "restored", "restored": 3}
    tool, _ = make_tool("autocad_fillet_chamfer", '{"done": true}')
    assert answers.split(call(tool))[0] == (
        "DONE - 2 added, 0 changed, 0 erased. The modeller had all 3 erased object(s) brought back."
    )


def test_some_brought_back_counts_only_those_still_erased(env):
    FakeBridge.counted = dict(ERASED_4)
    FakeBridge.erase_answer = {"answer": "restored", "restored": 1}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 4}')
    whole = call(erase)
    assert answers.split(whole)[0] == (
        "DONE - 0 added, 0 changed, 3 erased. The modeller had 1 of the 4 erased object(s) brought back."
    )
    assert json.loads(answers.body(whole))["heron_changes"]["erased"] == 3


def test_a_restore_heron_could_only_queue_still_counts_them_erased(env):
    # The plug-in could not ask in time and brings them back later: none restored yet.
    FakeBridge.counted = dict(ERASED_4)
    FakeBridge.erase_answer = {
        "answer": "restored", "restored": 0,
        "message": "Heron could not show the question in time, so it is bringing them back.",
    }  # fmt: skip
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 4}')
    whole = call(erase)
    # The count is what the drawing held when Heron asked; the line says they are on their way back.
    assert answers.split(whole)[0] == (
        "DONE - 0 added, 0 changed, 4 erased. "
        "Heron could not show the question in time, so it is bringing them back."
    )
    assert "bringing them back" in json.loads(answers.body(whole))["heron_note"]


def test_a_restore_that_brought_none_back_says_to_look(env):
    FakeBridge.counted = dict(ERASED_4)
    FakeBridge.erase_answer = {"answer": "restored", "restored": 0}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 4}')
    first = answers.split(call(erase))[0]
    assert first.startswith("DONE - 0 added, 0 changed, 4 erased. The modeller asked for the 4")
    assert "none came back: look at the drawing" in first


def test_a_text_answer_gets_its_count_restated_after_a_restore(env):
    FakeBridge.counted = dict(ERASED_4)
    FakeBridge.erase_answer = {"answer": "restored", "restored": 4}
    erase, _ = make_tool("autocad_delete_entities", "Deleted 4 objects.")
    rest = answered(call(erase), "NOTHING CHANGED")
    assert 'heron_changes: {"added": 0, "modified": 0, "erased": 0}' in rest
    assert '"erased": 4' not in rest


@pytest.mark.parametrize("restored", [4, 0])
def test_after_any_restore_undo_last_has_nothing_to_undo(env, restored):
    # One UNDO step back could be the plug-in's restore, and erase them again (#209).
    FakeBridge.counted = {"added": 1, "modified": 0, "erased": 4, "erased_handles": ["A", "B", "C", "D"]}
    FakeBridge.erase_answer = {"answer": "restored", "restored": restored}
    tool, _ = make_tool("autocad_fillet_chamfer", '{"created": true, "handle": "2A"}')
    call(tool)
    assert gate.last_change() is None


def test_an_erase_kept_erased_stays_undoable(env):
    FakeBridge.counted = dict(ERASED_4)
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 4}')
    call(erase)
    assert gate.last_change() is not None


def test_keeping_them_erased_is_said(env):
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 2, "erased_handles": ["A", "B"]}
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 2}')
    result = json.loads(answered(call(erase), "DONE"))
    assert "keep the 2 erased object(s) erased" in result["heron_note"]


def test_an_erase_kept_without_asking_never_says_the_modeller_chose(env):
    # The modeller turned the erase question off in Settings: the plug-in kept them unasked (D-50).
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 2, "erased_handles": ["A", "B"]}
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0, "asked": False}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 2}')
    result = json.loads(answered(call(erase), "DONE"))
    assert [c[1] for c in FakeBridge.calls if c[0] == "ask_erase"] == ["job1"]  # still the plug-in's call
    note = result["heron_note"]
    assert "chose" not in note
    assert "2 object(s)" in note and "without asking" in note
    assert "Ask before keeping erased objects" in note and "off in Heron's Settings" in note


def test_an_erase_kept_by_the_administrator_key_names_the_key(env):
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 1, "erased_handles": ["A"]}
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0, "asked": False, "off_by": "policy"}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 1}')
    note = json.loads(answered(call(erase), "DONE"))["heron_note"]
    assert "chose" not in note and "without asking" in note
    assert "administrator setting" in note and "AskBeforeErasing" in note
    assert "Settings" not in note


def test_keep_or_discard_covers_an_erase_so_it_is_not_asked_twice(env):
    FakeBridge.ask_to_keep = True
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 1, "erased_handles": ["A"]}
    erase, _ = make_tool("autocad_delete_entities", '{"deleted": 1}')
    call(erase)
    asked = [c[0] for c in FakeBridge.calls]
    assert "ask_keep" in asked and "ask_erase" not in asked


def test_an_erase_that_could_not_be_asked_is_said_plainly(env):
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 1, "erased_handles": ["A"]}
    FakeBridge.erase_answer = {"answer": "unknown", "restored": 0}
    send, _ = make_tool("autocad_run_lisp", '{"result": "nil"}')
    result = json.loads(answered(call(send), "DONE"))
    assert "could not ask the modeller" in result["heron_note"]


def test_reads_are_not_counted(env):
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 9, "erased_handles": []}
    read, _ = make_tool("autocad_list_layers", "[]", writes=False)
    call(read)
    assert not any(c[0] in ("changes", "ask_erase") for c in FakeBridge.calls)


def test_an_older_plug_in_that_cannot_count_changes_nothing(env):
    FakeBridge.counted = None
    draw, _ = make_tool("autocad_draw_line")
    assert json.loads(answered(call(draw), "DONE")) == {"created": True, "handle": "2A"}


# ---------------------------------------------------------------------------
# The dialog watch: a box AutoCAD opened mid-job is named (D-66)
# ---------------------------------------------------------------------------


def test_a_box_the_plug_in_closed_is_named_in_the_result(env):
    FakeBridge.boxes = [{"title": "Select File", "pressed": "Cancel", "closed": True}]
    send, _ = make_tool("autocad_send_command", '{"sent": "_OPEN"}')
    result = json.loads(answered(call(send), "DONE"))
    assert result["sent"] == "_OPEN"
    assert result["heron_dialogs"] == [
        "AutoCAD showed 'Select File'; Heron closed it with Cancel, nothing was kept from that step."
    ]
    assert FakeBridge.dialogs_asked == ["job1"]


def test_every_job_asks_even_a_read(env):
    read, _ = make_tool("autocad_list_layers", "[]", writes=False)
    assert call(read) == "[]"  # no box: the result is untouched
    assert FakeBridge.dialogs_asked == ["job1"]


def test_a_box_named_on_an_error_keeps_the_error_first(env):
    FakeBridge.boxes = [{"title": "AutoCAD Message", "pressed": "Esc", "closed": True}]
    tool, _ = make_tool("autocad_draw_line", "Error: AutoCAD stayed busy.")
    result = answered(call(tool), "OUTCOME UNKNOWN")  # it began to write, and nothing was counted
    assert result.startswith("Error: AutoCAD stayed busy.")
    assert "heron_dialog: AutoCAD showed 'AutoCAD Message'; Heron closed it with Esc" in result


def test_a_box_that_would_not_close_says_what_to_do():
    said = gate.dialog_sentence({"title": "Stubborn", "pressed": "Cancel", "closed": False})
    assert said.startswith("AutoCAD showed 'Stubborn'; Heron pressed Cancel but it is still open.")
    assert "read the drawing back" in said
    many = gate.dialog_sentence({"title": "Again", "pressed": "none", "closed": False})
    assert "Heron stopped closing them" in many


def test_bridge_dialogs_reads_the_plug_ins_answer(monkeypatch):
    from autocad_mcp.core.bridge import Bridge

    reply = {
        "ok": True,
        "dialogs": [
            {"title": "Select File", "pressed": "Cancel", "closed": True},
            {"title": "", "pressed": "No", "closed": None},
            "junk",
        ],
    }
    monkeypatch.setattr(Bridge, "call", lambda self, op, **fields: reply if op == "dialogs" else {})
    assert Bridge(1).dialogs("j1") == [
        {"title": "Select File", "pressed": "Cancel", "closed": True, "asked": False},
        {"title": "a box with no title", "pressed": "No", "closed": None, "asked": False},
    ]


def test_an_older_or_unreachable_plug_in_gives_no_boxes(monkeypatch):
    from autocad_mcp.core.bridge import Bridge

    older = {"ok": False, "refusedBy": "BadRequest", "message": "Heron in AutoCAD does not know the request 'dialogs'."}
    monkeypatch.setattr(Bridge, "call", lambda self, op, **fields: older)
    assert Bridge(1).dialogs("j1") == []

    def unreachable(self, op, **fields):
        raise BridgeRefused("Could not reach Heron in AutoCAD.")

    monkeypatch.setattr(Bridge, "call", unreachable)
    assert Bridge(1).dialogs("j1") == []


# ---------------------------------------------------------------------------
# Tools that replace objects: keep the change, or undo the whole change (D-136, #208)
# ---------------------------------------------------------------------------

JOINED = '{"joined": 2, "handle": "1A", "kind": "line", "removed": ["1B"]}'
JOIN_COUNT = {"added": 0, "modified": 1, "erased": 1, "erased_handles": ["1B"]}
CUT_CIRCLE = '{"operation": "trim", "done": 1, "objects": [{"handle": "C1", "replaced_by": "A9"}]}'
CIRCLE_COUNT = {"added": 1, "modified": 0, "erased": 1, "erased_handles": ["C1"]}
EXPLODED = '{"exploded": 1, "objects": [{"handle": "B1", "type": "block", "new_handles": ["P1", "P2"]}]}'
EXPLODE_COUNT = {"added": 2, "modified": 0, "erased": 1, "erased_handles": ["B1"]}

REPLACE_JOBS = [
    ("autocad_join_curves", JOINED, JOIN_COUNT),
    ("autocad_explode", EXPLODED, EXPLODE_COUNT),
    ("autocad_trim_extend", CUT_CIRCLE, CIRCLE_COUNT),
    ("autocad_break_curve", '{"handle": "C1", "replaced_by": "A9", "pieces": 1}', CIRCLE_COUNT),
]

NOT_KEPT = [
    {"answer": "undo_whole", "restored": 0, "asked": True},  # the box: Undo, Enter, Esc, closed, no answer
    {"answer": "undo_whole", "restored": 0, "asked": True, "message": "Heron could not show the question in time."},
    {"answer": "restored", "restored": 1, "asked": True},  # a plug-in older than D-136 brought them back
    {"answer": "unknown", "restored": 0},  # the plug-in could not be heard
]


def replace_job(env, tool, result, counted):
    FakeBridge.counted = dict(counted)
    env["back_on_undo"] = set(counted["erased_handles"])
    made, _ = make_tool(tool, result)
    return made


@pytest.mark.parametrize("tool, result, counted", REPLACE_JOBS)
@pytest.mark.parametrize("answer", NOT_KEPT)
def test_every_answer_but_keep_undoes_the_whole_replace_job(env, tool, result, counted, answer):
    FakeBridge.erase_answer = dict(answer)
    whole = call(replace_job(env, tool, result, counted))
    # The mark went down with Ask to Keep off, the question was the whole-change one, and the
    # drawing went back to the mark: nothing is left doubled.
    assert env["marks"] == 1 and env["discards"] == 1
    assert FakeBridge.erase_whole == [(True,)]
    first, rest = answers.split(whole)
    assert first.startswith("NOTHING CHANGED - "), first
    assert "Heron undid the whole change" in first and "back exactly as it was" in first
    assert rest.startswith("Undone: ") and "Nothing was kept" in rest
    assert ends()[-1][3] == "discarded" and FakeBridge.marked_at_end == [True]
    assert gate.last_change() is None  # undone already: nothing left for autocad_undo_last
    assert gate.activity()[0]["outcome"] == "discarded"


@pytest.mark.parametrize("tool, result, counted", REPLACE_JOBS)
def test_keep_the_change_keeps_it_and_says_so(env, tool, result, counted):
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0, "asked": True}
    whole = call(replace_job(env, tool, result, counted))
    assert env["discards"] == 0
    first, rest = answers.split(whole)
    assert first.startswith("DONE - "), first
    assert "chose Keep the change" in json.loads(rest)["heron_note"]
    last = gate.last_change()
    assert last is not None and last["marked"] is True  # undo_last goes back to the mark


def test_the_erase_question_off_keeps_a_replace_job_unasked(env):
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0, "asked": False}
    note = json.loads(answered(call(replace_job(env, *REPLACE_JOBS[0])), "DONE"))["heron_note"]
    assert env["discards"] == 0 and "without asking" in note and "chose" not in note


def test_a_replace_job_with_no_mark_possible_is_refused_before_anything_is_sent(env, monkeypatch):
    env["undo_on"] = False
    monkeypatch.setattr(gate, "_no_mark", gate.NO_MARK_UNDO_OFF)
    FakeBridge.counted = dict(JOIN_COUNT)
    join, runs = make_tool("autocad_join_curves", JOINED)
    whole = call(join)
    assert runs == [] and env["discards"] == 0
    first, rest = answers.split(whole)
    assert first.startswith("REFUSED - "), first
    assert "replaces objects" in rest and "Undo the whole change" in rest and "Turn UNDO on" in rest
    assert not any(c[0] == "ask_erase" for c in FakeBridge.calls)
    assert ends()[-1][3] == "refused"


def test_an_undo_whole_that_could_not_go_back_is_outcome_unknown(env, monkeypatch):
    FakeBridge.erase_answer = {"answer": "undo_whole", "restored": 0, "asked": True}

    async def busy():
        raise AutocadError("AutoCAD stayed busy.")

    monkeypatch.setattr(gate, "_discard", busy)
    whole = call(replace_job(env, *REPLACE_JOBS[0]))
    first, rest = answers.split(whole)
    assert first.startswith("OUTCOME UNKNOWN - "), first
    assert "look at it" in first and rest.startswith("Error: Undo the whole change failed")
    assert gate.last_change() is None


def test_a_new_shape_still_there_after_the_undo_is_outcome_unknown(env):
    FakeBridge.erase_answer = {"answer": "undo_whole", "restored": 0, "asked": True}
    env["left"] = ["A9"]
    first = answers.split(call(replace_job(env, *REPLACE_JOBS[2])))[0]
    assert first.startswith("OUTCOME UNKNOWN - ") and "A9" in first


def test_an_erased_object_not_back_after_the_undo_is_outcome_unknown(env):
    FakeBridge.erase_answer = {"answer": "undo_whole", "restored": 0, "asked": True}
    tool = replace_job(env, *REPLACE_JOBS[1])
    env["back_on_undo"] = set()  # UNDO Back did not bring the exploded block back
    first = answers.split(call(tool))[0]
    assert first.startswith("OUTCOME UNKNOWN - ") and "B1" in first


def test_a_replace_job_that_erased_nothing_is_not_asked_and_stays_undoable(env):
    FakeBridge.counted = {"added": 0, "modified": 1, "erased": 0, "erased_handles": []}
    trim, _ = make_tool("autocad_trim_extend", '{"operation": "trim", "done": 1, "objects": [{"handle": "L1"}]}')
    answered(call(trim), "DONE")
    assert env["marks"] == 1 and not any(c[0] == "ask_erase" for c in FakeBridge.calls)
    assert gate.last_change()["marked"] is True


def test_a_replace_job_with_ask_to_keep_on_gets_keep_or_discard_as_before(env):
    FakeBridge.ask_to_keep = True
    FakeBridge.counted = dict(JOIN_COUNT)
    call(make_tool("autocad_join_curves", JOINED)[0])
    asked = [c[0] for c in FakeBridge.calls]
    assert "ask_keep" in asked and "ask_erase" not in asked and env["marks"] == 1


def test_every_other_tools_erase_question_is_unchanged(env):
    # No mark with Ask to Keep off, the usual question, and the plug-in's restore stands.
    FakeBridge.counted = dict(ERASED_4)
    FakeBridge.erase_answer = {"answer": "restored", "restored": 4, "asked": True}
    first = answers.split(call(make_tool("autocad_delete_entities", '{"deleted": 4}')[0]))[0]
    assert env["marks"] == 0 and env["discards"] == 0
    assert FakeBridge.erase_whole == [()]  # asked with (job, summary) only, as before D-136
    assert first.startswith("NOTHING CHANGED - the job erased 4 object(s)")


# ---- replace-shaped edits D-136 did not cover: steps, and four more tools (D-140, #255) ------


def tool_taking(name: str, result: str, **defaults):
    """A stand-in tool with named arguments and their defaults, as a real tool has."""
    import inspect

    calls: list[dict] = []

    async def tool(**kwargs) -> str:
        calls.append(kwargs)
        connection.mark_writing()
        return result

    tool.__name__ = name
    tool.__signature__ = inspect.Signature(
        [inspect.Parameter(k, inspect.Parameter.KEYWORD_ONLY, default=v) for k, v in defaults.items()]
    )
    return tool_errors(tool), calls


JOIN_STEP = {"tool": "autocad_join_curves", "args": {"handles": ["1A", "1B"]}}
LINE_STEP = {"tool": "autocad_draw_line", "args": {"start": [0, 0], "end": [1, 0]}}
SEQUENCE_RAN = json.dumps({"ran": 2, "failed": 0, "skipped": 0, "steps": [
    {"index": 1, "tool": "autocad_draw_line", "ok": True, "result": {"created": True, "handle": "2A"}},
    {"index": 2, "tool": "autocad_join_curves", "ok": True, "result": json.loads(JOINED)},
]})  # fmt: skip


@pytest.fixture
def steps_read(monkeypatch):
    """The sequence's own step reader, as tools/sequence.py registers it, without the real tools."""
    monkeypatch.setitem(
        gate.STEPS_OF, "autocad_sequence",
        lambda args: [] if args.get("dry_run") else [(s["tool"], s["args"]) for s in args["steps"]],
    )  # fmt: skip


def a_sequence(env, steps, counted=JOIN_COUNT):
    FakeBridge.counted = dict(counted)
    env["back_on_undo"] = set(counted["erased_handles"])
    return tool_taking("autocad_sequence", SEQUENCE_RAN, steps=steps, stop_on_error=True, dry_run=False)


@pytest.mark.parametrize("answer", NOT_KEPT)
def test_a_sequence_with_a_replace_step_undoes_the_whole_sequence(env, steps_read, answer):
    FakeBridge.erase_answer = dict(answer)
    tool, runs = a_sequence(env, [LINE_STEP, JOIN_STEP])
    first, rest = answers.split(call(tool))
    # Ask to Keep off, and still the mark first, the whole-change question, and back to the mark:
    # the line of step 1 goes too, so nothing of the sequence is left (D-140).
    assert runs and env["marks"] == 1 and env["discards"] == 1
    assert FakeBridge.erase_whole == [(True,)]
    assert first.startswith("NOTHING CHANGED - ") and "Heron undid the whole change" in first
    assert rest.startswith("Undone: ") and ends()[-1][3] == "discarded" and FakeBridge.marked_at_end == [True]


def test_undoing_a_sequence_checks_every_steps_new_objects_are_gone(env, steps_read):
    FakeBridge.erase_answer = {"answer": "undo_whole", "restored": 0, "asked": True}
    env["left"] = ["2A"]  # the line of step 1 is still there after UNDO Back
    first = answers.split(call(a_sequence(env, [LINE_STEP, JOIN_STEP])[0]))[0]
    assert first.startswith("OUTCOME UNKNOWN - ") and "2A" in first


def test_keep_the_change_keeps_the_whole_sequence(env, steps_read):
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0, "asked": True}
    first = answers.split(call(a_sequence(env, [LINE_STEP, JOIN_STEP])[0]))[0]
    assert first.startswith("DONE - ") and env["discards"] == 0
    assert gate.last_change()["marked"] is True


def test_a_sequence_with_a_replace_step_and_no_mark_is_refused_and_runs_nothing(env, steps_read, monkeypatch):
    env["undo_on"] = False
    monkeypatch.setattr(gate, "_no_mark", gate.NO_MARK_UNDO_OFF)
    tool, runs = a_sequence(env, [LINE_STEP, JOIN_STEP])
    first, rest = answers.split(call(tool))
    assert runs == [] and first.startswith("REFUSED - ")
    assert "(its step " in rest and "replaces objects" in rest and "Turn UNDO on" in rest


def test_a_sequence_without_a_replace_step_keeps_the_usual_question(env, steps_read):
    FakeBridge.erase_answer = {"answer": "restored", "restored": 1, "asked": True}
    call(a_sequence(env, [LINE_STEP, {"tool": "autocad_delete_entities", "args": {"handles": ["1B"]}}])[0])
    assert env["marks"] == 0 and env["discards"] == 0 and FakeBridge.erase_whole == [()]


def test_a_sequence_checked_only_needs_no_mark(env, steps_read):
    env["undo_on"] = False
    FakeBridge.counted = {"added": 0, "modified": 0, "erased": 0, "erased_handles": []}
    tool, runs = tool_taking("autocad_sequence", '{"dry_run": true}', steps=[JOIN_STEP], dry_run=False)
    asyncio.run(tool(dry_run=True))
    assert runs and env["marks"] == 0


def test_steps_that_cannot_be_read_are_left_to_the_tool(env, monkeypatch):
    def broken(args):
        raise AutocadError("Step 1: there is no tool called 'autocad_draw_lion'.")

    monkeypatch.setitem(gate.STEPS_OF, "autocad_sequence", broken)
    assert gate.replacing("autocad_sequence", {"steps": []}) is None


BOOLEAN = '{"operation": "union", "handle": "S1", "consumed": ["S2"], "failed": []}'
SOLID_COUNT = {"added": 0, "modified": 1, "erased": 1, "erased_handles": ["S2"]}
ARRAY = '{"created": true, "handle": "AR1", "associative": true, "sources": ["H1"]}'
BLOCK = '{"created": true, "block": "PLATE", "handle": "IN1", "objects": 1}'
REGION = '{"created": 1, "regions": [{"handle": "R1", "area": 4.0}], "erased_outlines": ["P1"]}'
NEW_COUNT = {"added": 1, "modified": 0, "erased": 1, "erased_handles": ["H1"]}

NEW_REPLACES = [
    ("autocad_solid_boolean", BOOLEAN, SOLID_COUNT, {}),
    ("autocad_associative_array", ARRAY, NEW_COUNT, {}),
    ("autocad_make_block", BLOCK, NEW_COUNT, {"keep_originals": False}),
    ("autocad_add_region", REGION, NEW_COUNT, {"erase_outlines": True}),
]


@pytest.mark.parametrize("tool, result, counted, args", NEW_REPLACES)
def test_the_other_write_then_erase_tools_undo_the_whole_change(env, tool, result, counted, args):
    # Bringing back only the erased objects would leave them under the union, the array, the
    # insert or the region: so the whole change is undone instead (D-140).
    FakeBridge.erase_answer = {"answer": "undo_whole", "restored": 0, "asked": True}
    FakeBridge.counted = dict(counted)
    env["back_on_undo"] = set(counted["erased_handles"])
    made, _ = tool_taking(tool, result, **args)
    first = answers.split(call(made))[0]
    assert env["marks"] == 1 and env["discards"] == 1 and FakeBridge.erase_whole == [(True,)]
    assert first.startswith("NOTHING CHANGED - "), first


@pytest.mark.parametrize("tool, args", [
    ("autocad_make_block", {"keep_originals": True}),
    ("autocad_add_region", {"erase_outlines": False}),
])  # fmt: skip
def test_a_block_that_keeps_its_objects_or_regions_that_keep_their_outlines_are_no_replace(env, tool, args):
    assert gate.replacing(tool, args) is None
    call(tool_taking(tool, BLOCK, **args)[0])
    assert env["marks"] == 0


def test_a_make_block_left_at_its_default_replaces_in_place(env):
    # The default puts the insert in place of the objects: tool_errors hands the gate the defaults.
    FakeBridge.counted = dict(NEW_COUNT)
    FakeBridge.erase_answer = {"answer": "keep_erased", "restored": 0, "asked": True}
    call(tool_taking("autocad_make_block", BLOCK, block="PLATE", keep_originals=False)[0])
    assert env["marks"] == 1 and FakeBridge.erase_whole == [(True,)]


def test_undoing_regions_checks_the_regions_are_gone(env):
    FakeBridge.erase_answer = {"answer": "undo_whole", "restored": 0, "asked": True}
    FakeBridge.counted = dict(NEW_COUNT)
    env["back_on_undo"] = {"H1"}
    env["left"] = ["R1"]
    first = answers.split(call(tool_taking("autocad_add_region", REGION, erase_outlines=True)[0]))[0]
    assert first.startswith("OUTCOME UNKNOWN - ") and "R1" in first


# ---- the Keep question's zoom, only when it ran (D-136, refines D-130) -----------------------


@pytest.mark.parametrize("zoomed, views", [(False, 0), (True, 1)])
def test_an_unmarked_keep_question_counts_its_zoom_only_when_it_ran(env, monkeypatch, zoomed, views):
    FakeBridge.ask_to_keep = True
    env["undo_on"] = False  # no mark: UNDO 1 would undo the question's zoom, if there was one
    monkeypatch.setattr(FakeBridge, "keep_zoomed", zoomed, raising=False)
    call(make_tool("autocad_draw_line")[0])
    assert gate.last_change()["views_since"] == views


def test_a_plug_in_that_does_not_say_is_taken_as_having_zoomed(env):
    FakeBridge.ask_to_keep = True
    env["undo_on"] = False
    call(make_tool("autocad_draw_line")[0])
    assert gate.last_change()["views_since"] == 1


# ---- the bridge's side of it ---------------------------------------------------------------


def test_bridge_ask_erase_sends_whole_only_when_asked(monkeypatch):
    from autocad_mcp.core.bridge import Bridge

    sent: list[dict] = []

    def fake(self, op, **fields):
        sent.append(fields)
        return {"ok": True, "answer": "undo_whole", "asked": True, "erased": 1, "restored": 0}

    monkeypatch.setattr(Bridge, "call", fake)
    assert Bridge(1).ask_erase("j1", "Join", True)["answer"] == "undo_whole"
    assert sent[-1]["whole"] is True
    Bridge(1).ask_erase("j1", "Delete")
    assert "whole" not in sent[-1]  # every other tool's request is as it was


def test_bridge_ask_keep_reads_whether_the_question_zoomed(monkeypatch):
    from autocad_mcp.core.bridge import Bridge

    bridge = Bridge(1)
    monkeypatch.setattr(Bridge, "call", lambda self, op, **fields: {"ok": True, "answer": "keep", "zoomed": False})
    assert bridge.ask_keep("j1", "x", []) == "keep" and bridge.keep_zoomed is False
    monkeypatch.setattr(Bridge, "call", lambda self, op, **fields: {"ok": True, "answer": "keep"})
    assert bridge.ask_keep("j1", "x", []) == "keep" and bridge.keep_zoomed is True  # an older plug-in
