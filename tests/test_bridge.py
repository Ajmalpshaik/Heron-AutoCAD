"""The Python side of the Heron bridge, against a fake plug-in pipe.

The fake stands in for Heron.AutoCAD.Bridge: it serves one named pipe,
reads one JSON line and answers with whatever the test hands it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid

import pytest
import pywintypes
import win32file
import win32pipe

from autocad_mcp.core import bridge
from autocad_mcp.core.bridge import (
    NOT_CONNECTED,
    NOTHING_SENT,
    Bridge,
    BridgeRefused,
)

needs_pipes = pytest.mark.skipif(sys.platform != "win32", reason="a real Windows named pipe to a fake plug-in")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return tmp_path


class FakePlugin:
    """One-connection pipe server; records the request, sends ``reply``."""

    def __init__(self, reply: dict | None, *, answer: bool = True) -> None:
        self.name = f"heron.autocad.test.{uuid.uuid4().hex[:8]}"
        self.reply = reply
        self.answer = answer
        self.requests: list[dict] = []
        self._ready = threading.Event()
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def __enter__(self) -> FakePlugin:
        self._thread.start()
        self._ready.wait(5)
        return self

    def __exit__(self, *exc) -> None:
        self._release.set()
        self._thread.join(5)

    def _serve(self) -> None:
        handle = win32pipe.CreateNamedPipe(
            rf"\\.\pipe\{self.name}",
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
            1,
            65536,
            65536,
            0,
            None,
        )
        self._ready.set()
        try:
            win32pipe.ConnectNamedPipe(handle, None)
            data = b""
            while not data.endswith(b"\n"):
                _, chunk = win32file.ReadFile(handle, 65536)
                data += chunk
            self.requests.append(json.loads(data))
            if self.answer:
                win32file.WriteFile(handle, (json.dumps(self.reply) + "\n").encode())
                win32file.FlushFileBuffers(handle)
            self._release.wait(10)
        except pywintypes.error:
            pass
        finally:
            win32file.CloseHandle(handle)


def write_address(home, pid: int, pipe_name: str, token: str = "tok") -> None:
    folder = home / "Heron" / "autocad" / "bridges"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{pid}.json").write_text(
        json.dumps(
            {
                "pid": pid,
                "pipeName": pipe_name,
                "acadVersion": "26.0",
                "addinVersion": "1.0.0",
                "protocolVersion": 1,
                "token": token,
                "startedAt": "2026-10-26T00:00:00Z",
            }
        )
    )


def test_no_address_file_means_not_connected(home):
    with pytest.raises(BridgeRefused) as err:
        Bridge(os.getpid()).begin("autocad_status", "read", "Checking", "a.dwg")
    assert str(err.value) == NOT_CONNECTED


def test_dead_pid_file_is_deleted(home):
    dead = 4_000_000  # far above any live Windows pid
    write_address(home, dead, "nobody")
    assert Bridge(dead).find() is None
    assert not (home / "Heron" / "autocad" / "bridges" / f"{dead}.json").exists()


@needs_pipes
def test_begin_sends_token_client_conversation(home):
    with FakePlugin({"ok": True}) as plugin:
        write_address(home, os.getpid(), plugin.name, token="secret")
        job, ask = Bridge(os.getpid()).begin("autocad_draw_line", "change", "Drawing a line", "a.dwg")
    request = plugin.requests[0]
    assert request["op"] == "begin"
    assert request["token"] == "secret"
    assert request["client"] == bridge.CLIENT
    assert request["conversation"] == bridge.CONVERSATION
    assert request["tool"] == "autocad_draw_line"
    assert request["risk"] == "change"
    assert request["job"] == job
    assert ask is False


@needs_pipes
def test_begin_reports_when_the_plugin_will_ask(home):
    with FakePlugin({"ok": True, "askToKeep": True}) as plugin:
        write_address(home, os.getpid(), plugin.name)
        _, ask = Bridge(os.getpid()).begin("autocad_draw_line", "change", "Drawing", "a.dwg")
    assert ask is True


@needs_pipes
def test_refusal_message_passed_through(home):
    reply = {"ok": False, "refusedBy": "Changes", "message": "Changes is off. Turn it on with the Changes padlock."}
    with FakePlugin(reply) as plugin:
        write_address(home, os.getpid(), plugin.name)
        with pytest.raises(BridgeRefused) as err:
            Bridge(os.getpid()).begin("autocad_draw_line", "change", "Drawing", "a.dwg")
    assert str(err.value).startswith("Changes is off.")
    assert str(err.value).endswith(NOTHING_SENT)


@needs_pipes
def test_hung_pipe_times_out(home):
    with FakePlugin(None, answer=False) as plugin:
        write_address(home, os.getpid(), plugin.name)
        started = time.monotonic()
        with pytest.raises(BridgeRefused) as err:
            Bridge(os.getpid()).begin("autocad_status", "read", "Checking", "a.dwg", timeout=1.0)
        assert time.monotonic() - started < 6
    assert str(err.value).endswith(NOTHING_SENT)


def test_end_never_raises_when_not_connected(home):
    Bridge(os.getpid()).end("job", ok=True, outcome="done", summary="x", ms=1)


def test_ask_keep_failure_is_unknown_not_discard(home):
    # A plug-in that cannot be reached is not the modeller saying "discard":
    # undoing on a broken pipe would remove work nobody chose to remove.
    assert Bridge(os.getpid()).ask_keep("job", "Drew a line", ["2A"]) == "unknown"


def test_bridge_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")
    assert bridge.bridge_enabled() is False
    monkeypatch.delenv("HERON_AUTOCAD_BRIDGE")
    assert bridge.bridge_enabled() is True


def test_conversation_id_can_be_fixed(monkeypatch):
    # Scripts that start one server per call (live checks) can
    # say they are one chat, so the one-chat hold does not lock them out.
    import importlib

    monkeypatch.setenv("HERON_CONVERSATION_ID", "live-checks")
    try:
        assert importlib.reload(bridge).CONVERSATION == "live-checks"
    finally:
        monkeypatch.delenv("HERON_CONVERSATION_ID")
        importlib.reload(bridge)


# --- a resumed chat keeps its hold (D-61) ---------------------------------------


def test_a_resumed_chat_is_the_same_chat():
    # Claude Code gives the reopened chat the same session id: same hold.
    first = bridge.conversation_id({"CLAUDE_CODE_SESSION_ID": "chat-1"}, follow_host_chat=True)
    again = bridge.conversation_id({"CLAUDE_CODE_SESSION_ID": "chat-1"}, follow_host_chat=True)
    assert first == again
    assert len(first) == 32 and int(first, 16) >= 0
    assert "chat-1" not in first  # the host's id is not sent as it is


def test_two_chats_never_share_an_id():
    one = bridge.conversation_id({"CLAUDE_CODE_SESSION_ID": "chat-1"}, follow_host_chat=True)
    two = bridge.conversation_id({"CLAUDE_CODE_SESSION_ID": "chat-2"}, follow_host_chat=True)
    assert one != two


def test_a_fixed_id_still_wins_over_the_host_chat():
    env = {"HERON_CONVERSATION_ID": "live-checks", "CLAUDE_CODE_SESSION_ID": "chat-1"}
    assert bridge.conversation_id(env, follow_host_chat=True) == "live-checks"


def test_without_a_host_chat_every_server_is_a_new_chat():
    assert bridge.conversation_id({}, follow_host_chat=True) != bridge.conversation_id({}, follow_host_chat=True)
    assert bridge.conversation_id({"CLAUDE_CODE_SESSION_ID": "  "}, follow_host_chat=True) != ""


def test_a_script_run_inside_a_chat_does_not_take_that_chats_hold():
    # A command-line script (tools/live_check.py) imports the modules but is
    # not the chat's server: it must not speak for the chat it was run from.
    chat = bridge.conversation_id({"CLAUDE_CODE_SESSION_ID": "chat-1"}, follow_host_chat=True)
    script = bridge.conversation_id({"CLAUDE_CODE_SESSION_ID": "chat-1"})
    assert script != chat


def test_the_server_follows_the_host_chat_at_start(monkeypatch):
    import inspect

    from autocad_mcp import server

    before = bridge.CONVERSATION
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "chat-9")
    monkeypatch.delenv("HERON_CONVERSATION_ID", raising=False)
    try:
        assert bridge.follow_host_chat() == bridge.conversation_id(
            {"CLAUDE_CODE_SESSION_ID": "chat-9"}, follow_host_chat=True
        )
        assert bridge.CONVERSATION == bridge.follow_host_chat()
    finally:
        bridge.CONVERSATION = before
    assert "follow_host_chat()" in inspect.getsource(server.main)


def test_the_gate_audits_the_chat_id_in_use_now(monkeypatch):
    import inspect

    from autocad_mcp.core import gate

    # Read at call time, so the id the server switched to is the one recorded.
    assert "bridge_module.CONVERSATION" in inspect.getsource(gate._record)


def test_the_protocol_check_never_speaks_for_the_chat_it_runs_in():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "tools" / "protocol_check.py").read_text(encoding="utf-8")
    assert '!= "CLAUDE_CODE_SESSION_ID"' in text


@needs_pipes
def test_send_quiet_sends_the_lines_for_the_job(home):
    with FakePlugin({"ok": True}) as plugin:
        write_address(home, os.getpid(), plugin.name)
        assert Bridge(os.getpid()).send_quiet("j1", ["(progn 1)", "(progn 2)"]) is True
    request = plugin.requests[0]
    assert (request["op"], request["job"], request["lines"]) == ("send_quiet", "j1", ["(progn 1)", "(progn 2)"])


@needs_pipes
def test_send_quiet_refused_or_unreachable_is_false_not_an_error(home):
    with FakePlugin({"ok": False, "message": "no job"}) as plugin:
        write_address(home, os.getpid(), plugin.name)
        assert Bridge(os.getpid()).send_quiet("j1", ["x"]) is False
    assert Bridge(os.getpid()).send_quiet("j1", ["x"]) is False  # no plug-in at all


@needs_pipes
def test_a_stopped_plug_in_ends_a_batch_instead_of_letting_com_type_it(home):
    words = "The modeller stopped Heron in AutoCAD (HERONSTOP). Nothing more is done until they type HERONSTOP again."
    with FakePlugin({"ok": False, "refusedBy": "Stopped", "message": words}) as plugin:
        write_address(home, os.getpid(), plugin.name)
        with pytest.raises(bridge.BridgeRefused) as caught:
            Bridge(os.getpid()).send_quiet("j1", ["x"])
    assert "HERONSTOP" in str(caught.value) and str(caught.value).endswith(bridge.NOTHING_SENT)


@needs_pipes
def test_stopped_reads_the_ping(home):
    with FakePlugin({"ok": True, "protocolVersion": 1, "stopped": True}) as plugin:
        write_address(home, os.getpid(), plugin.name)
        assert Bridge(os.getpid()).stopped() is True
    assert Bridge(os.getpid()).stopped() is False  # cannot tell: not stopped
