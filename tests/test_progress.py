"""'Still working' notes while a long call runs (no AutoCAD).

A chat that hears nothing for two minutes during a PDF set thinks Heron hung.
The gate sends a progress note every few seconds while a tool runs; a host
that did not ask for progress gets nothing, and a note that fails never
touches the call.
"""

from __future__ import annotations

import asyncio

from autocad_mcp.core import gate, progress
from autocad_mcp.core.registry import mcp


class Context:
    def __init__(self, fail: bool = False) -> None:
        self.notes: list[tuple[float, str]] = []
        self.fail = fail

    async def report_progress(self, progress: float, total: float | None = None, message: str | None = None) -> None:
        if self.fail:
            raise RuntimeError("the host went away")
        self.notes.append((progress, message or ""))


def _call(context, monkeypatch, seconds: float = 0.08):
    monkeypatch.setattr(progress, "EVERY", 0.01)
    monkeypatch.setattr(progress.start, "__defaults__", (0.01,))

    async def slow() -> str:
        await asyncio.sleep(seconds)
        return '{"ok": true}'

    async def main() -> str:
        token = progress._request.set(context)
        try:
            return await gate.guarded("autocad_regen", slow)
        finally:
            progress._request.reset(token)

    return asyncio.run(main())


def test_a_long_call_sends_still_working_notes(monkeypatch):
    context = Context()
    assert _call(context, monkeypatch) == '{"ok": true}'
    assert context.notes, "no note was sent during an 80 ms call with a 10 ms beat"
    seconds, message = context.notes[0]
    assert message.startswith("Still working: ") and "s so far" in message
    assert seconds >= 0


def test_notes_stop_when_the_call_ends(monkeypatch):
    context = Context()
    _call(context, monkeypatch)
    sent = len(context.notes)

    async def later():
        await asyncio.sleep(0.05)

    asyncio.run(later())
    assert len(context.notes) == sent


def test_a_note_that_fails_never_touches_the_call(monkeypatch):
    assert _call(Context(fail=True), monkeypatch) == '{"ok": true}'


def test_no_context_no_notes():
    assert progress.current() is None
    assert progress.start(lambda s: "x") is None
    progress.stop(None)


def test_the_server_keeps_each_calls_context():
    assert getattr(mcp.call_tool, "_heron_progress", False)
    seen = []

    async def original(name, arguments, context=None):
        seen.append(progress.current())
        return "done"

    class Server:
        call_tool = staticmethod(original)

    server = Server()
    progress.install(server)
    progress.install(server)  # twice is harmless
    marker = object()
    assert asyncio.run(server.call_tool("autocad_status", {}, marker)) == "done"
    assert seen == [marker]
    assert progress.current() is None
