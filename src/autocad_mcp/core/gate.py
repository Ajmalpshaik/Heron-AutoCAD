"""The Heron gate every tool call passes through.

Order for one call:

1. Look at AutoCAD (which process, which drawing). Nothing is changed.
2. Wrong-drawing guard: a change to a drawing other than the one Heron last
   looked at (with autocad_status, or by switching) is refused. The plug-in's
   document events say what happened since (#48): the drawing closed and
   opened again, or AutoCAD restarted, is refused too; a Save As is followed.
3. Ask the plug-in to ``begin``: it checks connection, the chat's turn and
   the padlock this tool's level needs, raises the banner, and says whether
   it will ask Keep or Discard afterwards.
4. If it will ask, put an UNDO mark down first, so Discard can go back to
   exactly here: the job, the zoom to it, layers a batch made, all of it.
   A tool that replaces objects (join, explode, trim, break, a solid boolean,
   an associative array, a block made in place, regions with their outlines
   erased), or a sequence with one among its steps, always gets the mark, and
   is refused when it cannot: its erase question undoes the whole job back to
   it (D-136, D-140).
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
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .. import __version__
from . import answers, audit, companion, connection, diagnose, progress, project_notes
from . import bridge as bridge_module
from .bridge import (
    NOT_CONNECTED,
    NOTHING_SENT,
    Bridge,
    BridgeRefused,
    acad_pid,
    bridge_enabled,
)
from .connection import get_app, run
from .drawing_events import Mark, Verdict, front_moved, judge
from .errors import AutocadError, is_retryable, raise_if_busy
from .risk import Risk, risk_of

DISCARDED = "Discarded: nothing was kept."
STATUS_TOOL = "autocad_status"
# Says which AutoCAD to work in: needs no drawing, and no plug-in job (D-49).
SESSION_TOOLS = {"autocad_use_autocad"}
# Read only Heron's own files (the tool index, the audit log, the install), or a
# DXF / DWG file on disk (D-92), or keep the office layer standard in Heron's own
# folder (D-120), never AutoCAD: they must answer exactly when AutoCAD is closed
# or not connected (D-67).
NO_AUTOCAD_TOOLS = {"autocad_why", "autocad_gaps", "autocad_read_file", "autocad_layer_standard"}
# The calls that tell Heron a drawing's units. Nothing is changed in a drawing
# until one of them has run on it (Ajmal, 2026-10-26: "the first time in a
# drawing, you have to understand the unit").
_CHECKS_DRAWING = {STATUS_TOOL, "autocad_create_drawing"}
BRIDGE_OFF = (
    "Heron's plug-in checks are switched off for this server (--no-bridge, "
    "developer use): no padlocks, banner or Keep or Discard apply."
)
DIAGNOSE_HINT = "Read the resource autocad://diagnose: it checks the install, the connection and the versions."
ERASE_QUESTION_NAME = "Ask before keeping erased objects"
ERASE_WAITING = "Waiting for the answer in AutoCAD: the job erased {count} object(s), keep them erased? ({seconds} s so far)."
# Jobs whose real effect the plug-in counts (D-50).
WATCHED = (Risk.CHANGE, Risk.ADMIN, Risk.PUBLISH)
KEEP_WAITING = "Waiting for the answer in AutoCAD: keep or discard '{what}'? ({seconds} s so far)."
# A dry run runs the job for real inside Heron's UNDO mark, then goes back to it (D-63).
NO_DRY_RUN = (
    "A dry run is not possible for {what}: it {why}, which going back to an UNDO mark cannot take "
    "back. Call it without dry_run when the modeller is sure. Nothing was sent to AutoCAD."
)
DRY_RUN_NEEDS_UNDO = (
    "A dry run needs UNDO on in this drawing (UNDOCTL) and AutoCAD at its Command: prompt, so Heron "
    "can put a mark down and go back to it afterwards. Nothing was run. Press Esc in AutoCAD, turn "
    "UNDO on (UNDO > All) if it is off, or call it without dry_run."
)
DRY_RUN_HANDLES = "A dry run: the handles above were taken back with it and no longer exist."
BACK_UNKNOWN = (
    "Outcome unknown: AutoCAD went busy as UNDO Back was sent, so the drawing may or may not be back at "
    "Heron's mark. Heron did not send it again: a second Back would go past the mark, into earlier work."
)
COULD_NOT_ASK = (
    "Heron could not ask whether to keep this change, so it was kept. "
    "One Ctrl+Z in AutoCAD reverses it."
)

_lock = asyncio.Lock()
# What Heron did in this chat, for autocad_activity, and its last change for autocad_undo_last (D-54).
_activity: deque[dict[str, Any]] = deque(maxlen=50)
_last_change: dict[str, Any] | None = None
MOST_HANDLES = 200
# Undoes Heron's own last change: no UNDO mark, no Keep or Discard, no erase question about it.
UNDOES = {"autocad_undo_last"}
# Replace objects: they write the new shape, then erase the old one (D-136, #208). Bringing back
# only the erased object would leave the old and the new shape on top of each other, so their
# erase question is "Keep the change, or undo the whole change?", and anything but a clear keep
# goes back to Heron's UNDO mark. So they always get a mark first, Ask to Keep on or off.
REPLACES = {
    "autocad_join_curves", "autocad_explode", "autocad_trim_extend", "autocad_break_curve",
    # The same shape (D-140, #255): the first solid already holds the union or the cut when the
    # others are erased; the array already holds copies of the objects it takes in.
    "autocad_solid_boolean", "autocad_associative_array",
}  # fmt: skip
# Replace objects only with some arguments (D-140): a block put in place of its objects, regions
# made with their outlines erased. Each is given the call's arguments with their defaults.
REPLACES_WHEN: dict[str, Callable[[dict[str, Any]], bool]] = {
    "autocad_make_block": lambda args: not args.get("keep_originals", False),
    "autocad_add_region": lambda args: bool(args.get("erase_outlines", False)),
}
# Run other tools as steps, inside this one job (D-140): for each, the steps a call will run, as
# (tool, arguments with their defaults). The tool registers it (tools/sequence.py, saved_commands.py).
STEPS_OF: dict[str, Callable[[dict[str, Any]], list[tuple[str, dict[str, Any]]]]] = {}
REPLACE_NEEDS_UNDO = (
    "{what} replaces objects: it writes the new shape, then erases the old one. Heron puts an UNDO "
    "mark down first, so that 'Undo the whole change' can put the drawing back exactly as it was, "
    "and here it could not: {why}. Nothing was sent to AutoCAD. {fix}, then try again."
)
WHOLE_UNDONE = (
    "Undone: {why}, so Heron undid the whole change. The drawing is back exactly as it was before "
    "'{what}': the new shape is gone and what it replaced is back. Nothing was kept."
)
_last_drawing: str | None = None
# Where the plug-in's drawing log stood when Heron checked _last_drawing (#48), or None.
_checked_mark: Mark | None = None
_current: Job | None = None  # the job whose tool is running right now
# Why the last _mark() put no mark down, for the words of a Discard that cannot run (#206).
NO_MARK_UNDO_OFF = "undo_off"
NO_MARK_IN_COMMAND = "in_command"
NO_MARK_UNREAD = "unread"
_no_mark: str = ""


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


def quiet_limit() -> int | None:
    """While a job runs with the plug-in: the longest line its quiet input types (#45), or None.

    None outside a job, with the bridge off, or from a plug-in that does not
    say: the batch then keeps the pieces measured for COM. Asks the plug-in
    (one ping), so call it from the COM worker, not the event loop.
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None
    ask = getattr(job.bridge, "quiet_limit", None)
    return ask() if ask else None


def plugin_runner() -> Callable[..., dict[str, Any]] | None:
    """While a job runs with the plug-in: a way to have it do one of its own operations.

    For what COM has no call for (D-40). None outside a job or with the bridge
    off. The plug-in itself only runs an operation inside this chat's running
    job, and only one the job's level covers.
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None

    def runner(operation: str, args: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        if timeout is None:
            return job.bridge.run(job.id, operation, args)
        return job.bridge.run(job.id, operation, args, timeout)

    return runner


def plugin_version() -> str | None:
    """The version of the plug-in in this running job, from its address file; None if not known.

    For a tool that has a faster way through a newer plug-in and keeps COM
    for an older one (D-114).
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None
    version = (job.bridge.find() or {}).get("addinVersion")
    return str(version) if version else None


def dialog_expecter() -> Callable[[str, str], str | None] | None:
    """While a job runs with the plug-in: a way to name one button for one box it expects (#101).

    The callable returns None when the plug-in took it, else why not. None
    outside a job or with the bridge off. The plug-in itself takes it only from
    an Admin job of this chat, once.
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None
    return lambda title, button: job.bridge.expect_dialog(job.id, title, button)


def stopped_by_modeller() -> bool:
    """True when the modeller pressed HERONSTOP during this job (D-51). Any thread.

    Long tools ask between their steps; the plug-in itself refuses every
    request of a stopped job, so a tool that never asks still stops at its
    next request to the plug-in.
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return False
    return job.bridge.stopped()


def front_changed_in_job() -> tuple[str, str] | None:
    """(the job's drawing, the drawing in front now) when another came to the front during this job (#165).

    For long tools, between their steps: from the plug-in's drawing events
    since begin. None when nothing moved, outside a job, or when the plug-in
    cannot tell (an older one). Any thread; one pipe call.
    """
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None
    seq = getattr(job.bridge, "drawing_seq_at_begin", None)
    ask = getattr(job.bridge, "drawing_events", None)
    if seq is None or ask is None:
        return None
    front = front_moved(job.drawing, ask(seq))
    return None if front is None else (job.drawing, front)


def reset(looked_at: str | None = None, mark: Mark | None = None) -> None:
    """Forget which drawing Heron checked (tests, and a fresh server start).

    The reason the last ``_mark()`` gave for no mark is forgotten too: it
    belongs to one job, and a stale "AutoCAD was in a command" must never be
    the reason a later Discard gives (#254).
    """
    global _last_drawing, _checked_mark, _no_mark
    _last_drawing = looked_at
    _checked_mark = mark
    _no_mark = ""


async def _since_checked(pid: int | None, drawing: str) -> Verdict:
    """What the plug-in's document events say happened since Heron checked its drawing (#48).

    When nothing spoke against it, the mark moves up to what was judged, so a
    long session never lets the events since the check drop off unread.
    """
    global _checked_mark
    mark = _checked_mark
    if mark is None or pid is None or _last_drawing is None or not bridge_enabled():
        return Verdict()
    ask = getattr(Bridge(pid), "drawing_events", None)
    history = await asyncio.to_thread(ask, mark.seq) if ask else None
    seen = judge(_last_drawing, drawing, mark, pid, history)
    if seen.refusal is None and seen.seen is not None and seen.seen > mark.seq:
        _checked_mark = Mark(mark.pid, mark.epoch, seen.seen)
    return seen


async def _mark_now(job: Job | None, pid: int | None) -> Mark | None:
    """Where the plug-in's drawing log stands now, for the drawing just checked (#48)."""
    if job is None or job.bridge is None or pid is None:
        return None
    ask = getattr(job.bridge, "drawing_mark", None)
    found = await asyncio.to_thread(ask) if ask else None
    return Mark(pid, found[0], found[1]) if found else None


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
    """Put an UNDO mark down before a job. False when UNDO is off, or AutoCAD is in a command.

    In a command, "_.UNDO _Mark " would be typed into that command's prompt and
    no mark made; a later UNDO Back would then go past the job, into the
    modeller's own work. So no mark, and nothing that needs one. Why there is
    none is kept in ``_no_mark``, so a Discard says the real reason. A busy
    AutoCAD (any retryable error) goes up, never "no mark": the retry asks
    again, and a busy AutoCAD past it ends the call before anything is sent
    (#206). The plug-in is told at ``end`` whether the mark is there.
    """
    global _no_mark
    _no_mark = ""

    def mark() -> bool:
        global _no_mark
        doc = get_app().ActiveDocument
        try:
            control = int(doc.GetVariable("UNDOCTL"))
            if int(doc.GetVariable("CMDACTIVE")) != 0:
                _no_mark = NO_MARK_IN_COMMAND
                return False
        except Exception as exc:  # noqa: BLE001 - cannot tell: no mark, never guess
            if is_retryable(exc):
                raise
            _no_mark = NO_MARK_UNREAD
            return False
        # Bit 1: undo on. Bit 2: only one step kept, so a mark means nothing.
        if not control & 1 or control & 2:
            _no_mark = NO_MARK_UNDO_OFF
            return False
        doc.SendCommand("_.UNDO _Mark ")
        return True

    return await run(mark)


def _no_mark_reason() -> tuple[str, str]:
    """Why there was no UNDO mark for this job, in the words of a Discard that cannot run (#206)."""
    if _no_mark == NO_MARK_IN_COMMAND:
        return (
            "AutoCAD was in a command when the job began, so Heron put no UNDO mark down",
            "Press Esc in AutoCAD before the next job",
        )
    if _no_mark == NO_MARK_UNREAD:
        return (
            "Heron could not read UNDOCTL before the job, so it put no UNDO mark down",
            "Look at the drawing",
        )
    return "UNDO is off in this drawing (UNDOCTL)", "Turn UNDO on (UNDO > All)"


async def _discard() -> None:
    """Undo back to the mark put down before the job."""

    def back() -> None:
        doc = get_app().ActiveDocument
        # A second Back would go past Heron's mark into the modeller's own work, so a
        # busy AutoCAD after this is Outcome unknown, never a second send (D-76).
        connection.mark_writing(BACK_UNKNOWN)
        doc.SendCommand("_.UNDO _Back ")

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
            except Exception as exc:  # noqa: BLE001 - gone is what we hope for
                raise_if_busy(exc)  # busy is not gone: never a false "Discard took"
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
        notes = project_notes.for_status(job.drawing)
        if notes:
            # The modeller's own answers for this project (D-53): use them, do not ask again.
            state["project_notes"] = notes
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


def replacing(tool: str, args: dict[str, Any] | None = None) -> str | None:
    """The tool in this call that replaces objects (D-136, D-140), or None.

    The tool itself when it is in REPLACES, or in REPLACES_WHEN with these
    arguments; for a sequence or a saved command, the first of its steps that
    is. A call whose steps cannot be read (a step list the tool will refuse, a
    saved command that is not there) is None: the tool refuses it itself, and
    nothing is run.
    """
    args = args or {}
    if tool in REPLACES:
        return tool
    when = REPLACES_WHEN.get(tool)
    if when is not None:
        return tool if when(args) else None
    steps_of = STEPS_OF.get(tool)
    if steps_of is None:
        return None
    try:
        steps = steps_of(args)
    except (AutocadError, KeyError, TypeError, ValueError):
        # Reading the steps touches no AutoCAD: the tool says what is wrong with them, and runs none.
        return None
    for step, step_args in steps:
        if step not in STEPS_OF and replacing(step, step_args):
            return step
    return None


def _replace_title(job: Job, replacer: str) -> str:
    """The job's name in a replace refusal: a sequence names its step that replaces objects."""
    return job.title if replacer == job.tool else f"{job.title} (its step {_title(replacer)})"


async def guarded(
    tool: str, work: Callable[[], Awaitable[Any]], dry_run: bool = False, args: dict[str, Any] | None = None
) -> Any:
    """Run one tool call through the gate. Returns the tool's result.

    dry_run: run the job inside Heron's UNDO mark, report, then go back to the
    mark (D-63). Only a Change tool can; the rest are refused before anything
    is sent.
    args: the call's arguments, with their defaults, so the gate can tell a
    call that replaces objects: a block made in place, or a sequence with a
    join among its steps (D-140).
    """
    global _last_drawing, _checked_mark, _current
    async with _lock:
        risk = risk_of(tool)
        started = time.monotonic()
        drawing = ""
        refusal: str | None = None
        probed = False

        if dry_run and (risk is not Risk.CHANGE or tool in UNDOES):
            why = (
                "undoes Heron's last change, which is itself an undo"
                if tool in UNDOES
                else "writes a file, or runs a command or AutoLISP"
            )
            refused = "Error: " + NO_DRY_RUN.format(what=_title(tool), why=why)
            _record(tool, risk, drawing, False, "refused", started, refused)
            if risk in WATCHED and bridge_enabled():
                facts = answers.Facts(refused, ok=False, outcome="refused", refused_by_heron=True)
                return answers.with_line(refused, answers.line(facts))
            return refused

        if tool in SESSION_TOOLS or tool in NO_AUTOCAD_TOOLS:
            # Picking which AutoCAD to work in touches no drawing, and must
            # answer exactly when the gate cannot tell which AutoCAD is meant
            # (D-49); explaining why a job cannot run must answer when AutoCAD
            # is closed (D-67). Audited like any call.
            ok, outcome, message = False, "failed", ""
            try:
                result = await work()
                ok = not (isinstance(result, str) and result.startswith("Error:"))
                outcome = "done" if ok else "failed"
                message = "" if ok else str(result)
                return result
            finally:
                _record(tool, risk, "", ok, outcome, started, message)

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
            seen = Verdict()
            if _last_drawing is not None:
                seen = await _since_checked(pid, drawing)
                if seen.follow:
                    # A Save As gave the checked drawing a new name: the same drawing, the same units.
                    _last_drawing = seen.follow
            if _last_drawing is None:
                refusal = (
                    f"Heron has not checked {drawing or 'this drawing'} yet. Call autocad_status "
                    "first: it gives the drawing's units, and every coordinate depends on them. "
                    + NOTHING_SENT
                )
            elif seen.refusal:
                refusal = seen.refusal
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
            title = ("Dry run: " if dry_run else "") + _title(tool)
            try:
                job_id, ask = await asyncio.to_thread(bridge.begin, tool, risk.value, title, drawing)
                job = Job(tool, risk, title, drawing, bridge, job_id, ask, started)
            except BridgeRefused as exc:
                refusal = str(exc)

        if refusal is not None:
            _record(tool, risk, drawing, False, "refused", started, refusal)
            if tool == STATUS_TOOL:
                # Status still answers, but says nothing about a drawing in
                # an AutoCAD that is not connected.
                return _status_heron(
                    _versions({"connected": False, "message": refusal, "diagnose": DIAGNOSE_HINT}, None)
                )
            refused = f"Error: {refusal}"
            if risk in WATCHED and bridge_enabled():
                facts = answers.Facts(refused, ok=False, outcome="refused", refused_by_heron=True)
                return answers.with_line(refused, answers.line(facts))
            return refused

        ok, outcome, result = False, "failed", None
        counted: dict[str, Any] | None = None
        wrote = marked = brought_back = asked_keep = keep_zoomed = False
        # Status reads the drawing found above: where the drawing log stood
        # then is its mark, so a close during the call is not swallowed (#48).
        mark_before = await _mark_now(job, pid) if tool == STATUS_TOOL else None
        # A replace job, or a sequence with one among its steps: the mark always, the whole-change
        # question, and refused with no mark (D-136, D-140).
        replacer = replacing(tool, args) if job and risk is Risk.CHANGE and not dry_run else None
        try:
            if dry_run:
                try:
                    marked = await _mark()
                except AutocadError:
                    marked = False
                if not marked:
                    outcome, result = "refused", "Error: " + DRY_RUN_NEEDS_UNDO
                    if job:
                        facts = answers.Facts(result, ok=False, outcome=outcome, refused_by_heron=True)
                        result = answers.with_line(result, answers.line(facts))
                    return result
            elif job and (job.ask_to_keep or replacer) and risk is Risk.CHANGE and tool not in UNDOES:
                try:
                    marked = await _mark()
                except AutocadError as exc:
                    # AutoCAD stayed busy before the job began: nothing was sent (D-100).
                    result = f"Error: {exc}"
                    facts = answers.Facts(result, ok=False, outcome="failed", busy=True)
                    return answers.with_line(result, answers.line(facts))
                if not marked and replacer:
                    # With no mark, "Undo the whole change" could not put the drawing back, and
                    # bringing back only the erased objects would leave both shapes (D-136).
                    why, fix = _no_mark_reason()
                    outcome = "refused"
                    what = _replace_title(job, replacer)
                    result = "Error: " + REPLACE_NEEDS_UNDO.format(what=what, why=why, fix=fix)
                    facts = answers.Facts(result, ok=False, outcome=outcome, refused_by_heron=True)
                    return answers.with_line(result, answers.line(facts))

            writes_before = connection.write_count()
            busy_before = connection.busy_count()
            _current = job
            what = job.title if job else _title(tool)
            beat = progress.start(lambda seconds: progress.note(what, seconds))
            try:
                result = await work()
            except asyncio.CancelledError:
                outcome = "cancelled"
                if dry_run and marked:
                    # The work may still finish on the COM thread; going back is queued after it,
                    # so a cancelled dry run keeps nothing either (D-63).
                    try:
                        await asyncio.shield(_discard())
                    except Exception:  # noqa: BLE001 - cancelled already; the drawing is said below
                        outcome = "cancelled_dry_run_not_undone"
                raise
            finally:
                _current = None
                progress.stop(beat)
            text = result if isinstance(result, str) else ""
            ok = not text.startswith("Error:")
            outcome = "done" if ok else ("unknown" if "Outcome unknown" in text else "failed")
            wrote = connection.write_count() > writes_before
            busy = connection.busy_count() > busy_before
            where = ""
            if busy and job and job.bridge:
                # Which command AutoCAD is in, from the plug-in's tracker, asked on its
                # pipe thread, so it answers while AutoCAD is busy (#47).
                known, command = await asyncio.to_thread(_command_of, job.bridge)
                where = answers.busy_where(known, command)
                if where and risk not in WATCHED:
                    result = _with_note(result, answers.busy_note(known, command)) if isinstance(result, str) else result

            if tool == STATUS_TOOL and ok:
                state: dict[str, Any] = (
                    {"connected": True} if job else {"connected": False, "bridge": "off", "message": BRIDGE_OFF}
                )
                result = _with_heron(result, _versions(state, job))

            if job and job.bridge and risk in WATCHED:
                counted = await asyncio.to_thread(job.bridge.changes, job.id)
                if counted is not None:
                    result = _with_changes(result, counted)

            if job and job.bridge:
                # A box AutoCAD opened mid-job was closed by the plug-in (D-66): say so.
                boxes = await asyncio.to_thread(job.bridge.dialogs, job.id)
                if boxes:
                    result = _with_dialogs(result, boxes)

            asked_keep = bool(ok and wrote and job and job.ask_to_keep and risk is Risk.CHANGE and tool not in UNDOES)
            said: tuple[str | None, str] | None = None
            if dry_run:
                # No question: whatever it did is taken back now (D-63).
                result, outcome, said = await _roll_back(result, text, ok, counted, wrote)
                ok = ok and outcome == "dry_run"
            elif tool in UNDOES:
                pass  # the modeller asked for exactly this undo: no question about it
            elif asked_keep:
                result, outcome, said = await _keep_or_discard(
                    job, result if isinstance(result, str) else text, marked
                )
                ok = outcome != "failed"
                # The question's zoom is an undo step after the job, only if it really ran (D-136).
                keep_zoomed = getattr(job.bridge, "keep_zoomed", True) is not False
            elif counted and counted["erased"] > 0 and replacer and marked:
                # A replace job: keep the change, or undo the whole of it back to the mark (D-136);
                # for a sequence, the whole sequence (D-140).
                result, whole, counted, said = await _ask_whole(job, result, text, counted, ok)
                if whole:
                    outcome, ok = whole, whole != "failed"
            elif counted and counted["erased"] > 0:
                # Anything erased gets a human yes, whatever Ask to Keep says (D-50),
                # unless the modeller turned the erase question off in Settings:
                # the plug-in decides that and says so, never the server.
                result, counted, said, brought_back = await _ask_erase(job, result, counted, risk)

            if job and risk in WATCHED:
                # One plain line first: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN (D-62).
                facts = answers.Facts(
                    text, ok=ok, outcome=outcome, counted=counted, wrote=wrote, marked=marked,
                    can_count=risk is Risk.CHANGE,
                    word=said[0] if said else None, note=said[1] if said else None,
                    busy=busy, where=where,
                )  # fmt: skip
                result = answers.with_line(result, answers.line(facts))

            if ok and tool in _CHECKS_DRAWING:
                if risk is Risk.VIEW:
                    try:
                        _, drawing = await _probe()
                    except AutocadError:
                        pass
                _last_drawing = drawing
                # A new drawing: after the work, so the drawing it opened is not news (#48).
                _checked_mark = mark_before if tool == STATUS_TOOL else await _mark_now(job, pid)
            return result
        finally:
            if job and job.bridge:
                # Whether Heron's UNDO mark is really there: the palette's Undo goes back to it only then (#206).
                await asyncio.to_thread(job.bridge.end, job.id, ok, outcome, job.title, _ms(started), marked)
            # The audit keeps the tool's own words, without the plain line (D-62).
            message = "" if ok or not isinstance(result, str) else answers.body(result)
            _record(tool, risk, drawing, ok, outcome, started, message)
            _remember(
                tool, risk, drawing, ok, outcome, started, job, result, counted, wrote, marked, dry_run,
                brought_back=brought_back, zoomed=asked_keep and keep_zoomed,
            )
            if companion.enabled():
                companion.write(companion_state())  # the Companion page, once the chat asked for it (D-71)


def _command_of(bridge: Bridge) -> tuple[bool, str | None]:
    """(known, command) from the plug-in's command tracker; (False, None) when it cannot tell (#47)."""
    ask = getattr(bridge, "current_command", None)
    if ask is None:
        return False, None
    try:
        return ask()
    except Exception:  # noqa: BLE001 - the busy answer stands without it
        return False, None


async def _roll_back(
    result: Any, text: str, ok: bool, counted: dict[str, Any] | None, wrote: bool = True
) -> tuple[Any, str, tuple[str, str]]:
    """The end of a dry run: back to Heron's UNDO mark, then check the new objects are gone (D-63).

    A job that began no write, and of which the plug-in counted nothing, has
    nothing to take back: no UNDO Back is sent, as Keep or Discard sends none.
    Returns (result, outcome, the plain line's word and reason).
    """
    if not wrote and not (counted and any(int(counted.get(k, 0)) for k in ("added", "modified", "erased"))):
        if not ok:
            return result, "dry_run", (answers.REFUSED, "the job failed in the dry run before it wrote anything.")
        return result, "dry_run", (answers.NOTHING_CHANGED, "a dry run that wrote nothing, so there was nothing to take back.")
    try:
        await _discard()
        left = await _still_there(_created(text))
    except AutocadError:
        return result, "failed", (
            answers.OUTCOME_UNKNOWN,
            "the dry run could not go back to Heron's UNDO mark, so the job may still be in the "
            "drawing: look at it before anything else.",
        )
    if left:
        return result, "failed", (
            answers.OUTCOME_UNKNOWN,
            "the dry run went back to Heron's UNDO mark, but these new objects are still in the "
            f"drawing, so the mark did not hold: {', '.join(left)}. Remove them by hand.",
        )
    back = "Heron went back to its UNDO mark, so the drawing is as it was."
    if not ok:
        return result, "dry_run", (answers.REFUSED, f"the job failed in the dry run; {back}")
    would = f"it would have made {answers.counts(counted)}; " if counted else ""
    shown = result
    if isinstance(result, str) and _handles(text):
        shown = _with_note(result, DRY_RUN_HANDLES)
    return shown, "dry_run", (answers.NOTHING_CHANGED, f"a dry run: {would}{back}")


async def _keep_or_discard(job: Job, text: str, marked: bool) -> tuple[str, str, tuple[str, str] | None]:
    """Ask the plug-in; act only on a clear answer.

    Returns (result, outcome, and the plain line's word and reason when the
    gate knows better than the tool's answer: a Discard that could not run).
    """
    beat = progress.start(lambda seconds: KEEP_WAITING.format(what=job.title, seconds=int(seconds)))
    try:
        answer = await asyncio.to_thread(job.bridge.ask_keep, job.id, job.title, _handles(text))
    finally:
        progress.stop(beat)
    if answer in ("keep", "keep_rest"):
        return text, "done", None
    if answer != "discard":
        return _with_note(text, COULD_NOT_ASK), "done", None
    if not marked:
        why, fix = _no_mark_reason()
        return (
            f"Error: Discard not possible: {why}, so the change is still there. Remove it by hand. {fix}.",
            "failed",
            (answers.DONE, f"the change is still in the drawing: Discard was not possible, because {why}."),
        )
    try:
        await _discard()
        left = await _still_there(_created(text))
    except AutocadError as exc:
        return (
            f"Error: Discard failed, the change may still be in the drawing: {exc}",
            "failed",
            (
                answers.OUTCOME_UNKNOWN,
                "Discard failed, so the change may still be in the drawing: look at it before anything else.",
            ),
        )
    if left:
        return (
            "Error: Discard did not take: these new objects are still in the drawing: "
            + ", ".join(left)
            + ". Check the drawing and remove them by hand if needed.",
            "failed",
            (
                answers.OUTCOME_UNKNOWN,
                "Discard went back to Heron's UNDO mark, but some new objects are still in the drawing, "
                "so the mark did not hold: remove them by hand.",
            ),
        )
    return DISCARDED, "discarded", None


def _with_changes(result: Any, counted: dict[str, Any]) -> Any:
    """Add what the plug-in counted, so the chat knows what really happened."""
    if not isinstance(result, str):
        return result
    shown = {key: counted[key] for key in ("added", "modified", "erased")}
    payload = _payload(result)
    if isinstance(payload, dict):
        payload["heron_changes"] = shown
        return json.dumps(payload, indent=2, default=str)
    if result.startswith("Error:") and not any(shown.values()):
        return result
    return f"{result}\n\nheron_changes: {json.dumps(shown)}"


def dialog_sentence(box: dict[str, Any]) -> str:
    """One box the plug-in answered, in the words the chat passes on (D-66)."""
    title, pressed, closed = box.get("title", ""), box.get("pressed", "Esc"), box.get("closed")
    if pressed == "none":
        return (
            f"AutoCAD kept opening boxes ('{title}' and more); Heron stopped closing them. Close "
            "what is open in AutoCAD (Esc), then read the drawing back before trying again."
        )
    if closed is False:
        return (
            f"AutoCAD showed '{title}'; Heron pressed {pressed} but it is still open. Close it in "
            "AutoCAD (Esc), then read the drawing back before trying again."
        )
    if box.get("asked"):
        return f"AutoCAD showed '{title}'; Heron pressed {pressed} on it, as this call asked (#101)."
    return f"AutoCAD showed '{title}'; Heron closed it with {pressed}, nothing was kept from that step."


def _with_dialogs(result: Any, boxes: list[dict[str, Any]]) -> Any:
    """Add a plain sentence per box the plug-in closed, so the chat knows the step did not finish."""
    if not isinstance(result, str):
        return result
    said = [dialog_sentence(box) for box in boxes]
    payload = _payload(result)
    if isinstance(payload, dict):
        payload["heron_dialogs"] = said
        return json.dumps(payload, indent=2, default=str)
    return result + "".join(f"\n\nheron_dialog: {line}" for line in said)


def _restate_changes(result: Any, before: dict[str, Any], now: dict[str, Any]) -> Any:
    """The heron_changes _with_changes added, said again with the counts as they are now."""
    if not isinstance(result, str):
        return result
    keys = ("added", "modified", "erased")
    payload = _payload(result)
    if isinstance(payload, dict):
        if "heron_changes" in payload:
            payload["heron_changes"] = {key: now[key] for key in keys}
            return json.dumps(payload, indent=2, default=str)
        return result
    old = f"heron_changes: {json.dumps({key: before[key] for key in keys})}"
    return result.replace(old, f"heron_changes: {json.dumps({key: now[key] for key in keys})}", 1)


async def _ask_erase(
    job: Job, result: Any, counted: dict[str, Any], risk: Risk
) -> tuple[Any, dict[str, Any], tuple[str | None, str] | None, bool]:
    """The erase question (D-50), and what the drawing holds after its answer (#209).

    Returns (result, the counts as they are now, the plain line's word and
    reason when the gate knows better than the counts, and whether anything
    was or is being brought back). Objects the modeller had brought back are
    no longer erased: the line, heron_changes and the activity list say so.
    """
    erased = int(counted["erased"])
    beat = progress.start(lambda seconds: ERASE_WAITING.format(count=erased, seconds=int(seconds)))
    try:
        answer = await asyncio.to_thread(job.bridge.ask_erase, job.id, job.title)
    finally:
        progress.stop(beat)
    said = answer.get("answer")
    now, brought_back = counted, False
    line: tuple[str | None, str] | None = None
    if said == "keep_erased" and answer.get("asked") is False:
        note = _not_asked_note(erased, answer)
    elif said == "keep_erased":
        note = f"The modeller chose to keep the {erased} erased object(s) erased."
    elif said == "restored":
        note = (
            f"The job erased {erased} object(s), and the modeller had them brought back "
            f"({answer.get('restored', 0)} restored). Do not erase them again without asking."
        )
        if answer.get("message"):
            note += " " + answer["message"]
        # The plug-in un-erased them after the job: one UNDO step back may be that, not the job.
        brought_back = True
        restored = min(max(int(answer.get("restored", 0) or 0), 0), erased)
        if restored:
            now = {**counted, "erased": erased - restored}
            result = _restate_changes(result, counted, now)
        others = int(now.get("added", 0)) + int(now.get("modified", 0))
        if restored == erased and not others and risk is Risk.CHANGE:
            line = (
                answers.NOTHING_CHANGED,
                f"the job erased {erased} object(s) and the modeller had all of them brought back, "
                "so no drawing object is added, changed or erased now.",
            )
        elif restored == erased:
            line = (None, f"The modeller had all {erased} erased object(s) brought back.")
        elif restored:
            line = (None, f"The modeller had {restored} of the {erased} erased object(s) brought back.")
        elif answer.get("message"):
            # Not back yet (or never): the count is what the drawing held when Heron asked.
            line = (None, str(answer["message"]))
        else:
            line = (None, f"The modeller asked for the {erased} erased object(s) back, but none came back: look at the drawing.")
    elif said == "nothing_erased":
        return result, counted, None, False
    else:
        note = (
            f"The job erased {erased} object(s) and Heron could not ask the modeller about it. "
            "Tell the modeller, and look at the drawing."
        )
    return (_with_note(result, note) if isinstance(result, str) else result), now, line, brought_back


def _not_asked_note(erased: int, answer: dict[str, Any]) -> str:
    """The erase question is off: the objects stay erased, and nobody was asked (D-50, D-62, D-123)."""
    # Never "the modeller chose": nobody was asked.
    where = (
        "off on this PC by the administrator setting (AskBeforeErasing = 0, D-123)"
        if answer.get("off_by") == "policy"
        else "off in Heron's Settings"
    )
    return (
        f"The job erased {erased} object(s) and they stay erased without asking: "
        f"the erase question ({ERASE_QUESTION_NAME}) is {where}. "
        "Tell the modeller what was erased; Ctrl+Z in AutoCAD brings them back."
    )


def _made(text: str) -> list[str]:
    """Every handle a replace job says it made: what undoing the whole change must take away (D-136)."""
    found = _created(text)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "new_handles" and isinstance(value, list):
                    found.extend(str(h) for h in value)
                elif key == "replaced_by" and isinstance(value, str):
                    found.append(value)
                elif key == "regions" and isinstance(value, list):
                    # autocad_add_region's new regions, each with its handle (D-140).
                    found.extend(str(r["handle"]) for r in value if isinstance(r, dict) and r.get("handle"))
                    walk(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(_payload(text))
    return list(dict.fromkeys(found))


async def _ask_whole(
    job: Job, result: Any, text: str, counted: dict[str, Any], ok: bool
) -> tuple[Any, str | None, dict[str, Any], tuple[str | None, str] | None]:
    """The erase question for a job that replaced objects, which holds Heron's UNDO mark (D-136, #208).

    Join, explode, and a circle trimmed or broken into an arc write the new
    shape, then erase the old one; so do a solid boolean, an associative
    array, a block made in place and regions made with their outlines erased,
    and a sequence with any of them among its steps (D-140), whose undo takes
    back the whole sequence. Bringing back only what was erased would
    leave both shapes on top of each other, so the modeller is asked "Keep the
    change, or undo the whole change?". Only a clear keep keeps. Every other
    answer (Enter, Esc, the box closed, no answer in time, an older plug-in
    that brought the objects back, a plug-in that could not be heard) goes back
    to the mark with UNDO Back, as Discard and autocad_undo_last do, and then
    checks that what the job made is gone and what it erased is back.
    Returns (result, the outcome, or None to leave the job's own, the counts,
    and the plain line's word and reason).
    """
    erased = int(counted["erased"])
    beat = progress.start(lambda seconds: ERASE_WAITING.format(count=erased, seconds=int(seconds)))
    try:
        answer = await asyncio.to_thread(job.bridge.ask_erase, job.id, job.title, True)
    finally:
        progress.stop(beat)
    said = answer.get("answer")
    if said == "nothing_erased":
        return result, None, counted, None
    if said == "keep_erased":
        note = (
            _not_asked_note(erased, answer)
            if answer.get("asked") is False
            else f"The modeller chose Keep the change: the new shape stays and the {erased} object(s) it replaced stay erased."
        )
        return (_with_note(result, note) if isinstance(result, str) else result), None, counted, None
    if said == "undo_whole" and answer.get("message"):
        why = str(answer["message"]).strip().rstrip(".")
    elif said in ("undo_whole", "restored"):
        # "restored": a plug-in older than D-136 brought them back; UNDO Back goes past that too.
        why = "the modeller did not choose Keep the change"
    else:
        why = "Heron could not hear the modeller's answer, and only a clear keep keeps"
    try:
        await _discard()
        left = await _still_there(_made(text))
        wanted = [str(h) for h in counted.get("erased_handles", [])]
        back = await _still_there(wanted)
    except AutocadError as exc:
        return (
            f"Error: Undo the whole change failed, so the change may still be in the drawing: {exc}",
            "failed",
            counted,
            (
                answers.OUTCOME_UNKNOWN,
                f"{why}, but going back to Heron's UNDO mark failed, so the change may still be in the "
                "drawing: look at it before anything else.",
            ),
        )
    missing = [h for h in wanted if h not in back]
    if left or missing:
        parts = []
        if left:
            parts.append(f"these new objects are still there: {', '.join(left)}")
        if missing:
            parts.append(f"these erased ones are not back: {', '.join(missing)}")
        found = "; ".join(parts)
        return (
            f"Error: Undo the whole change did not take: {found}. Look at the drawing and fix it by hand if needed.",
            "failed",
            counted,
            (
                answers.OUTCOME_UNKNOWN,
                f"{why}, and Heron went back to its UNDO mark, but the drawing is not as it was ({found}): "
                "look at it before anything else.",
            ),
        )
    undone = WHOLE_UNDONE.format(why=why, what=job.title)
    line = (
        answers.NOTHING_CHANGED,
        f"{why}, so Heron undid the whole change: the drawing is back exactly as it was before the job.",
    )
    if not ok:
        # The tool failed part-way after it erased: its own error stays, the job stays failed.
        return (_with_note(result, undone) if isinstance(result, str) else result), None, counted, line
    return undone, "discarded", counted, line


def _remember(
    tool: str, risk: Risk, drawing: str, ok: bool, outcome: str, started: float, job: Job | None,
    result: Any, counted: dict[str, Any] | None, wrote: bool, marked: bool, dry_run: bool = False,
    brought_back: bool = False, zoomed: bool = False,
) -> None:
    """The activity list, and what "undo Heron's last change" may undo (D-54).

    brought_back: the erase question put erased objects back after the job, so
    the last UNDO step may be that restore and not the job (#209).
    zoomed: the Keep or Discard question zoomed to the job, an undo step of its
    own: with no mark, one step back would be that zoom (D-130).
    """
    global _last_change
    text = result if isinstance(result, str) else ""
    created = _created(text) if ok else []
    entry = {
        "at": time.strftime("%H:%M:%S"),
        "tool": tool,
        "what": job.title if job else _title(tool),
        "risk": risk.value,
        "drawing": drawing,
        "outcome": outcome,
        "seconds": round(_ms(started) / 1000, 1),
    }
    if created:
        entry["created"] = created[:MOST_HANDLES]
    if counted:
        entry["changes"] = {key: counted[key] for key in ("added", "modified", "erased")}
    if risk is not Risk.READ:
        _activity.append(entry)
    if dry_run:
        # The undo history moved (a mark, then back to it): undo nothing older on a guess.
        _last_change = None
        return
    if tool in UNDOES:
        if ok:
            _last_change = None
        return
    if brought_back:
        # One UNDO step back could erase again what the modeller had brought back: undo nothing on a guess.
        _last_change = None
        return
    if risk is Risk.VIEW and _last_change is not None:
        _last_change["views_since"] += 1
    elif risk is Risk.CHANGE and wrote:
        _last_change = (
            {**entry, "created": created, "marked": marked, "views_since": 1 if zoomed else 0}
            if ok and outcome == "done" else None
        )  # fmt: skip
    elif risk is Risk.CHANGE and marked:
        # A mark with nothing after it (#209): it is now the newest UNDO mark, so UNDO Back for an
        # older job would stop at it and undo nothing, and with no new handles to check say "undone".
        _last_change = None
    elif risk in (Risk.ADMIN, Risk.PUBLISH) and wrote:
        _last_change = None  # a raw command or a save in between: no safe undo of what came before


def companion_state() -> dict[str, Any]:
    """What the Companion page shows, from what the gate already holds: no COM (D-71)."""
    return {
        "version": __version__,
        "conversation": bridge_module.CONVERSATION,
        "drawing": _last_drawing,
        "activity": activity(companion.MOST_ROWS),
        "last_change": last_change(),
    }


def activity(limit: int = 20) -> list[dict[str, Any]]:
    """What Heron did in this chat, newest first (reads are left out)."""
    return list(reversed(list(_activity)))[:limit]


def last_change() -> dict[str, Any] | None:
    """Heron's last change in this chat that is still safe to undo, or None."""
    return dict(_last_change) if _last_change else None


def changed_by_modeller_since() -> bool | None:
    """Inside a job: did anything change between Heron's last change and now? None when the plug-in cannot tell."""
    job = _current
    if job is None or job.bridge is None or job.id is None:
        return None
    return job.bridge.since_last(job.id)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _record(tool: str, risk: Risk, drawing: str, ok: bool, outcome: str, started: float, message: str = "") -> None:
    """One audit line. A failure keeps only a reason word from a fixed list, never its message (D-67)."""
    fields: dict[str, Any] = {}
    if not ok and outcome != "cancelled":
        fields["reason"] = audit.reason_of(message) or "other"
    audit.record(
        conversation=bridge_module.CONVERSATION,
        tool=tool,
        risk=risk.value,
        drawing=drawing,
        ok=ok,
        outcome=outcome,
        ms=_ms(started),
        **fields,
    )
