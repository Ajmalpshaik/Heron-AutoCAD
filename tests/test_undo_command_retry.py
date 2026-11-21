"""A busy retry never sends UNDO, U, REDO, MREDO or OOPS twice (#42, D-15).

autocad_send_command sends those five outside an undo mark, because running
them inside an open undo group does not roll back reliably. Before #42 they
were therefore never marked as a write, so a busy signal after the send let the
retry loop send the UNDO a second time: two steps taken back instead of one.
"""

from __future__ import annotations

import asyncio

import pytest
import pythoncom

from autocad_mcp.core import connection
from autocad_mcp.core.errors import OutcomeUnknown
from autocad_mcp.tools import advanced

BUSY = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)


class Doc:
    """Turns the first ``busy_sends`` SendCommand calls away, after AutoCAD has taken them."""

    def __init__(self, busy_sends: int = 0, busy_looks: int = 0) -> None:
        self.busy_sends, self.busy_looks = busy_sends, busy_looks
        self.sent: list[str] = []
        self.variables = {"CMDACTIVE": 0, "FILEDIA": 1, "ATTDIA": 1}
        self.marks: list[str] = []

    def GetVariable(self, name):
        return self.variables[name]

    def SetVariable(self, name, value):
        self.variables[name] = value

    def SendCommand(self, text):
        self.sent.append(text)
        if len(self.sent) <= self.busy_sends:
            raise BUSY

    def StartUndoMark(self):
        self.marks.append("start")

    def EndUndoMark(self):
        self.marks.append("end")


@pytest.fixture
def send(monkeypatch):
    """autocad_send_command through the real retry loop, on this thread."""
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)
    holder: dict[str, Doc] = {}

    def get_doc():
        doc = holder["doc"]
        if doc.busy_looks:
            doc.busy_looks -= 1
            raise BUSY
        return doc

    async def run(fn):
        return connection._with_retry(fn)

    monkeypatch.setattr(advanced, "run", run)
    monkeypatch.setattr(advanced, "get_doc", get_doc)
    monkeypatch.setattr(advanced, "require_idle", lambda d: None)

    def call(command: str, doc: Doc) -> str:
        holder["doc"] = doc
        return asyncio.run(advanced.autocad_send_command(command=command))

    return call


@pytest.mark.parametrize("command", ["_U", "_.UNDO _Back", "_REDO", "_MREDO 2", "_OOPS"])
def test_a_busy_signal_after_an_undo_command_is_sent_never_sends_it_again(send, command):
    doc = Doc(busy_sends=1)
    answer = send(command, doc)
    assert len(doc.sent) == 1
    assert answer.startswith("Error: Outcome unknown")
    first = command.split()[0].lstrip("_.").upper()
    assert f"as {first} was sent" in answer
    assert "one Ctrl+Z reverses it" not in answer  # after an undo, Ctrl+Z takes back one step more
    assert doc.marks == []  # still sent outside an undo mark


def test_busy_before_the_undo_is_sent_is_still_retried(send):
    # Nothing reached AutoCAD yet: asking again cannot undo anything twice.
    doc = Doc(busy_looks=2)
    answer = send("_U", doc)
    assert not answer.startswith("Error"), answer
    assert len(doc.sent) == 1


def test_an_undo_command_counts_as_a_write_for_the_gate(send):
    before = connection.write_count()
    send("_U", Doc())
    assert connection.write_count() == before + 1


def test_an_ordinary_command_keeps_its_undo_mark_and_its_own_words(send):
    doc = Doc(busy_sends=1)
    answer = send("_LINE 0,0 10,0 ", doc)
    assert len(doc.sent) == 1
    assert doc.marks == ["start", "end"]
    assert OutcomeUnknown.DEFAULT in answer


def test_the_retry_loop_gives_the_writes_own_words_and_forgets_them_on_the_next_attempt(monkeypatch):
    monkeypatch.setattr(connection, "RETRY_DELAY", 0)

    def undo_then_busy():
        connection.mark_writing("Outcome unknown: my own words.")
        raise BUSY

    with pytest.raises(OutcomeUnknown, match="my own words"):
        connection._with_retry(undo_then_busy)

    attempts: list[int] = []

    def busy_then_write():
        attempts.append(1)
        if len(attempts) == 1:
            connection.mark_writing("Outcome unknown: stale words.")
            connection._attempt.writing = False  # as if the busy came before the write
            raise BUSY
        connection.mark_writing()
        raise BUSY

    with pytest.raises(OutcomeUnknown) as err:
        connection._with_retry(busy_then_write)
    assert str(err.value) == OutcomeUnknown.DEFAULT
