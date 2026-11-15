"""The Heron gate every tool call passes through.

Order for one call:

1. Look at AutoCAD (which process, which drawing). Nothing is changed.
2. Wrong-drawing guard: a change to a drawing other than the one Heron last
   looked at (with autocad_status, or by switching) is refused.
3. Ask the plug-in to ``begin``: it checks connection, the chat's turn and
   the padlock this tool's level needs, raises the banner, and says whether
   it will ask Keep or Discard afterwards.
4. If it will ask, put an UNDO mark down first, so Discard can go back to
   exactly here: the job, the zoom to it, layers a batch made, all of it.
5. Run the tool.
6. If the call really wrote and the plug-in asks, Discard means UNDO Back to
   the mark, then check the new objects are gone before saying so.
7. ``end`` and the audit line, whatever happened, cancellation included.

Calls run one at a time (one banner, one COM worker). Pipe calls run off the
event loop, so a slow plug-in never stalls the server.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .. import __version__
from . import audit, connection, diagnose, progress
from .bridge import (
    CONVERSATION,
    NOT_CONNECTED,
    NOTHING_SENT,
    Bridge,
    BridgeRefused,
    acad_pid,
    bridge_enabled,
)
from .connection import get_app, run
from .errors import AutocadError
from .risk import Risk, risk_of

DISCARDED = "Discarded: nothing was kept."
STATUS_TOOL = "autocad_status"
# The calls that tell Heron a drawing's units. Nothing is changed in a drawing
# until one of them has run on it (Ajmal, 2026-10-26: "the first time in a
# drawing, you have to understand the unit").
_CHECKS_DRAWING = {STATUS_TOOL, "autocad_create_drawing"}
BRIDGE_OFF = (
    "Heron's plug-in checks are switched off for this server (--no-bridge, "
    "developer use): no padlocks, banner or Keep or Discard apply."
)
DIAGNOSE_HINT = "Read the resource autocad://diagnose: it checks the install, the connection and the versions."
KEEP_WAITING = "Waiting for the answer in AutoCAD: keep or discard '{what}'? ({seconds} s so far)."
COULD_NOT_ASK = (
    "Heron could not ask whether to keep this change, so it was kept. "
    "One Ctrl+Z in AutoCAD reverses it."
)

_lock = asyncio.Lock()
_last_drawing: str | None = None
_current: Job | None = None  # the job whose tool is running right now


@dataclass
class Job:
    tool: str
    risk: Risk
    title: str
    drawing: str
    bridge: Bridge | None
    id: str | None
    ask_to_keep: bool
    started: float


def quiet_sender() -> Callable[[list[str]], bool] | None:
    """While a job runs with the plug-in: a way to send drawing input with echo off.

    None outside a job or with the bridge off. The plug-in itself only accepts
    the lines inside this chat's running change job.
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None
    return lambda lines: job.bridge.send_quiet(job.id, lines)


def plugin_runner() -> Callable[[str, dict[str, Any]], dict[str, Any]] | None:
    """While a job runs with the plug-in: a way to have it do one of its own operations.

    For what COM has no call for (D-40). None outside a job or with the bridge
    off. The plug-in itself only runs an operation inside this chat's running
    job, and only one the job's level covers.
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None
    return lambda operation, args: job.bridge.run(job.id, operation, args)


def reset(looked_at: str | None = None) -> None:
    """Forget which drawing Heron checked (tests, and a fresh server start)."""
    global _last_drawing
    _last_drawing = looked_at


def _title(tool: str) -> str:
    from .registry import mcp  # registry imports this module

    found = mcp._tool_manager.get_tool(tool)
    return (found.title if found and found.title else tool.removeprefix("autocad_").replace("_", " ")).strip()


async def _probe() -> tuple[int, str]:
    """The AutoCAD process id and the active drawing's full path (or name)."""

    def look() -> tuple[int, str]:
        app = get_app()
        pid = acad_pid(app)
        if int(app.Documents.Count) == 0:
            return pid, ""
        doc = app.ActiveDocument
        return pid, str(doc.FullName) or str(doc.Name)

    return await run(look)


async def _mark() -> bool:
    """Put an UNDO mark down before a job. False when UNDO is off in this drawing."""

    def mark() -> bool:
        doc = get_app().ActiveDocument
        try:
            control = int(doc.GetVariable("UNDOCTL"))
        except Exception:  # noqa: BLE001 - cannot tell: treat as off, never guess
            return False
        # Bit 1: undo on. Bit 2: only one step kept, so a mark means nothing.
        if not control & 1 or control & 2:
            return False
        doc.SendCommand("_.UNDO _Mark ")
        return True

    return await run(mark)


async def _discard() -> None:
    """Undo back to the mark put down before the job."""

    def back() -> None:
        get_app().ActiveDocument.SendCommand("_.UNDO _Back ")

    await run(back)


async def _still_there(handles: list[str]) -> list[str]:
    """Which of these handles still resolve in the active drawing."""

    def look() -> list[str]:
        doc = get_app().ActiveDocument
        left = []
        for handle in handles:
            try:
                doc.HandleToObject(handle)
                left.append(handle)
            except Exception:  # noqa: BLE001 - gone is what we hope for
                pass
        return left

    return await run(look)


def _payload(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _handles(text: str) -> list[str]:
    """Every handle in a result: what the plug-in selects and zooms to."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "handle" and isinstance(value, str):
                    found.append(value)
                elif key == "handles" and isinstance(value, list):
                    found.extend(str(h) for h in value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(_payload(text))
    return list(dict.fromkeys(found))


def _created(text: str) -> list[str]:
    """Handles of objects the call created: the ones a Discard must remove."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("created") is True and isinstance(node.get("handle"), str):
                found.append(node["handle"])
            if isinstance(node.get("created"), int) and isinstance(node.get("handles"), list):
                found.extend(str(h) for h in node["handles"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(_payload(text))
    return list(dict.fromkeys(found))


def _versions(state: dict[str, Any], job: Job | None) -> dict[str, Any]:
    """What autocad_status adds about Heron itself: versions, and an update the chat has not loaded."""
    state["server_version"] = __version__
    if job and job.bridge:
        address = job.bridge.find() or {}
        if address.get("addinVersion"):
            state["plugin_version"] = address["addinVersion"]
    if diagnose.changed_since_start():
        state["update_waiting"] = (
            "Heron's server files were updated after this chat started it, so it still runs the old "
            "code. Close and reopen the chat (or restart Claude) to load the update."
        )
    return state


def _status_heron(state: dict[str, Any]) -> str:
    return json.dumps({"heron": state}, indent=2)


def _with_heron(result: str, state: dict[str, Any]) -> str:
    payload = _payload(result)
    if not isinstance(payload, dict):
        return result
    payload["heron"] = state
    return json.dumps(payload, indent=2, default=str)


def _with_note(result: str, note: str) -> str:
    payload = _payload(result)
    if isinstance(payload, dict):
        payload["heron_note"] = note
        return json.dumps(payload, indent=2, default=str)
    return f"{result}\n\n{note}"


async def guarded(tool: str, work: Callable[[], Awaitable[Any]]) -> Any:
    """Run one tool call through the gate. Returns the tool's result."""
    global _last_drawing, _current
    async with _lock:
        risk = risk_of(tool)
        started = time.monotonic()
        drawing = ""
        refusal: str | None = None
        probed = False

        try:
            pid, drawing = await _probe()
            probed = True
        except AutocadError as exc:
            pid = None
            # With the bridge on, no reachable AutoCAD means no plug-in to ask.
            # With it off (developer mode) the tool reports its own error.
            if bridge_enabled() and tool != STATUS_TOOL:
                refusal = str(exc)

        if refusal is None and probed and risk not in (Risk.READ, Risk.VIEW):
            if _last_drawing is None:
                refusal = (
                    f"Heron has not checked {drawing or 'this drawing'} yet. Call autocad_status "
                    "first: it gives the drawing's units, and every coordinate depends on them. "
                    + NOTHING_SENT
                )
            elif drawing != _last_drawing:
                refusal = (
                    f"The active drawing changed from {_last_drawing} to {drawing} since "
                    "Heron last checked. Call autocad_status first, so you know this drawing's "
                    f"units and the change goes where you mean it. {NOTHING_SENT}"
                )

        if refusal is not None and probed and bridge_enabled() and Bridge(pid).find() is None:
            # Not connected at all: "press Heron" is the first thing to fix.
            refusal = NOT_CONNECTED

        job: Job | None = None
        if refusal is None and probed and bridge_enabled():
            bridge = Bridge(pid)
            title = _title(tool)
            try:
                job_id, ask = await asyncio.to_thread(bridge.begin, tool, risk.value, title, drawing)
                job = Job(tool, risk, title, drawing, bridge, job_id, ask, started)
            except BridgeRefused as exc:
                refusal = str(exc)

        if refusal is not None:
            _record(tool, risk, drawing, False, "refused", started)
            if tool == STATUS_TOOL:
                # Status still answers, but says nothing about a drawing in
                # an AutoCAD that is not connected.
                return _status_heron(
                    _versions({"connected": False, "message": refusal, "diagnose": DIAGNOSE_HINT}, None)
                )
            return f"Error: {refusal}"

        ok, outcome, result = False, "failed", None
        try:
            marked = False
            if job and job.ask_to_keep and risk is Risk.CHANGE:
                marked = await _mark()

            writes_before = connection.write_count()
            _current = job
            what = job.title if job else _title(tool)
            beat = progress.start(lambda seconds: progress.note(what, seconds))
            try:
                result = await work()
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            finally:
                _current = None
                progress.stop(beat)
            text = result if isinstance(result, str) else ""
            ok = not text.startswith("Error:")
            outcome = "done" if ok else ("unknown" if "Outcome unknown" in text else "failed")
            wrote = connection.write_count() > writes_before

            if tool == STATUS_TOOL and ok:
                state: dict[str, Any] = (
                    {"connected": True} if job else {"connected": False, "bridge": "off", "message": BRIDGE_OFF}
                )
                result = _with_heron(result, _versions(state, job))

            if ok and wrote and job and job.ask_to_keep and risk is Risk.CHANGE:
                result, outcome = await _keep_or_discard(job, text, marked)
                ok = outcome != "failed"

            if ok and tool in _CHECKS_DRAWING:
                if risk is Risk.VIEW:
                    try:
                        _, drawing = await _probe()
                    except AutocadError:
                        pass
                _last_drawing = drawing
            return result
        finally:
            if job and job.bridge:
                await asyncio.to_thread(job.bridge.end, job.id, ok, outcome, job.title, _ms(started))
            _record(tool, risk, drawing, ok, outcome, started)


async def _keep_or_discard(job: Job, text: str, marked: bool) -> tuple[str, str]:
    """Ask the plug-in; act only on a clear answer. Returns (result, outcome)."""
    beat = progress.start(lambda seconds: KEEP_WAITING.format(what=job.title, seconds=int(seconds)))
    try:
        answer = await asyncio.to_thread(job.bridge.ask_keep, job.id, job.title, _handles(text))
    finally:
        progress.stop(beat)
    if answer in ("keep", "keep_rest"):
        return text, "done"
    if answer != "discard":
        return _with_note(text, COULD_NOT_ASK), "done"
    if not marked:
        return (
            "Error: Discard not possible: UNDO is off in this drawing (UNDOCTL), so the change "
            "is still there. Remove it by hand, or turn UNDO on (UNDO > All).",
            "failed",
        )
    try:
        await _discard()
        left = await _still_there(_created(text))
    except AutocadError as exc:
        return f"Error: Discard failed, the change may still be in the drawing: {exc}", "failed"
    if left:
        return (
            "Error: Discard did not take: these new objects are still in the drawing: "
            + ", ".join(left)
            + ". Check the drawing and remove them by hand if needed.",
            "failed",
        )
    return DISCARDED, "discarded"


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _record(tool: str, risk: Risk, drawing: str, ok: bool, outcome: str, started: float) -> None:
    audit.record(
        conversation=CONVERSATION,
        tool=tool,
        risk=risk.value,
        drawing=drawing,
        ok=ok,
        outcome=outcome,
        ms=_ms(started),
    )
