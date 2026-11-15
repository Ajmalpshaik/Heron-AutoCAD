"""'Still working' notes while a long call runs.

A PDF set, a render setup, an audit or a big batch can keep a call busy for
minutes, and a chat that hears nothing looks hung (the idea is from Heron AI
for Revit, its docs/04 section 7.1). While a call runs, a note goes to the
chat every few seconds saying what Heron is on and for how long; while it
waits for Keep or Discard, the note says so.

The notes are MCP progress notifications. They go only to a host that asked
for them (a progressToken on the call): to any other, report_progress does
nothing. A note that cannot be sent is dropped; it never touches the call.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

EVERY = 10.0

_request: ContextVar[Any] = ContextVar("heron_request", default=None)


def install(server: Any) -> None:
    """Remember each tool call's context, so the gate can send notes for it.

    The SDK hands the context only to tools that ask for it by parameter; this
    keeps it for every call without touching the 100-odd tool signatures.
    """
    original = server.call_tool
    if getattr(original, "_heron_progress", False):
        return

    async def call_tool(name: str, arguments: dict[str, Any], context: Any = None) -> Any:
        token = _request.set(context)
        try:
            return await original(name, arguments, context)
        finally:
            _request.reset(token)

    call_tool._heron_progress = True  # type: ignore[attr-defined]
    server.call_tool = call_tool


def current() -> Any:
    """The running call's context, or None (tests, and calls made outside MCP)."""
    return _request.get()


def note(what: str, seconds: float) -> str:
    return f"Still working: {what} ({int(seconds)} s so far)."


async def _beat(context: Any, message: Callable[[float], str], started: float, every: float) -> None:
    while True:
        await asyncio.sleep(every)
        elapsed = time.monotonic() - started
        try:
            await context.report_progress(progress=round(elapsed, 1), total=None, message=message(elapsed))
        except Exception:  # noqa: BLE001 - a note is a courtesy; the call goes on
            return


def start(message: Callable[[float], str], every: float = EVERY) -> asyncio.Task | None:
    """Send ``message(seconds)`` every ``every`` seconds until stopped. None without a context."""
    context = current()
    if context is None:
        return None
    return asyncio.create_task(_beat(context, message, time.monotonic(), every))


def stop(task: asyncio.Task | None) -> None:
    """Stop the notes. Not awaited, so a cancelled call is never held up or its cancel swallowed."""
    if task is not None:
        task.cancel()
