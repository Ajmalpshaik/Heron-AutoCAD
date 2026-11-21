"""The COM link to a running AutoCAD.

AutoCAD's Automation interface is an out-of-process, single-threaded-apartment
COM server. Two consequences shape this module:

1. Every COM call must happen on one thread that has called CoInitialize.
   FastMCP tools run on asyncio's event loop, so all COM work is marshalled
   onto a single dedicated worker thread via ``run()``.

2. AutoCAD rejects calls while it is busy — a modal dialog is up, the user is
   mid-command, a regen is running. That is transient and must be retried, not
   reported as a failure. It is retried at two levels: one refused COM call is
   asked again by the worker thread's message filter (message_filter.py), and
   a whole tool is re-run by ``_with_retry`` while nothing has been written.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

import pythoncom
import win32com.client

from . import message_filter
from .errors import (
    AutocadError,
    OutcomeUnknown,
    StaleDispatchError,
    com_message,
    is_dispatch_failure,
    is_retryable,
)

T = TypeVar("T")

PROG_ID = "AutoCAD.Application"

RETRY_ATTEMPTS = 40
RETRY_DELAY = 0.25
# The retry also stops at this many seconds: with the message filter one
# refused attempt can itself take a few seconds, and 40 of them would not.
RETRY_WINDOW = 10.0

# Space selector accepted by tools.
MODEL_SPACE = "model"
PAPER_SPACE = "paper"


class _ComWorker:
    """Runs every COM call on one dedicated apartment thread.

    A single thread rather than a pool: AutoCAD's interface is
    apartment-threaded, so marshalling the same document across threads is both
    slower and a source of spurious rejections.
    """

    def __init__(self) -> None:
        self._jobs: queue.Queue[tuple[Callable[[], Any], queue.Queue]] = queue.Queue()
        self._thread = threading.Thread(
            target=self._loop, name="autocad-com", daemon=True
        )
        self._started = False
        self._lock = threading.Lock()

    def _ensure_started(self) -> None:
        with self._lock:
            if not self._started:
                self._thread.start()
                self._started = True

    def _loop(self) -> None:
        pythoncom.CoInitialize()
        # A call AutoCAD turns away while busy is asked again, not failed
        # (2026-11-18). Refused by Windows? Then everything works as before.
        message_filter.install()
        try:
            while True:
                fn, reply = self._jobs.get()
                message_filter.new_job()  # each job gets the filter's whole wait
                try:
                    reply.put((True, fn()))
                except BaseException as exc:  # noqa: BLE001 - relayed to the caller
                    reply.put((False, exc))
        finally:  # pragma: no cover - daemon thread outlives the process
            pythoncom.CoUninitialize()

    def submit(self, fn: Callable[[], T]) -> T:
        self._ensure_started()
        reply: queue.Queue = queue.Queue(maxsize=1)
        self._jobs.put((fn, reply))
        ok, result = reply.get()
        if ok:
            return result
        raise result


_worker = _ComWorker()


_attempt = threading.local()
_writes = 0
_busy = 0


def write_count() -> int:
    """How many writes have started since the server started (the gate compares)."""
    return _writes


def busy_count() -> int:
    """How many calls ended in a busy AutoCAD since the server started (the gate compares, #47)."""
    return _busy


def note_busy() -> None:
    """Record that a call ended because AutoCAD stayed busy, so the gate can say where AutoCAD is (#47).

    ``_with_retry`` calls it for its own two busy endings; a tool that waits
    out a busy AutoCAD itself (autocad_run_lisp's read of the answer) calls it too.
    """
    global _busy
    _busy += 1


def mark_writing(unknown: str | None = None) -> None:
    """Record that the current attempt has started changing the drawing.

    Called by ``undo_mark`` on the worker thread. From then on a busy signal
    is no longer safe to retry: the first try may already have drawn part of
    the work. ``unknown`` is the "Outcome unknown" sentence to give then, for
    a write that is not a drawing (an UNDO sent as a command, #42).
    """
    global _writes
    _attempt.writing = True
    _attempt.unknown = unknown
    _writes += 1


def _with_retry(fn: Callable[[], T]) -> T:
    """Call ``fn``, retrying for as long as AutoCAD reports it is busy.

    Only while nothing has been written: once a write began, a busy signal
    becomes OutcomeUnknown instead of a second run. At most RETRY_ATTEMPTS
    tries and RETRY_WINDOW seconds, whichever comes first.
    """
    last: BaseException | None = None
    started = time.monotonic()
    for _ in range(RETRY_ATTEMPTS):
        _attempt.writing = False
        _attempt.unknown = None
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001
            if not is_retryable(exc):
                raise
            if getattr(_attempt, "writing", False):
                note_busy()
                raise OutcomeUnknown(getattr(_attempt, "unknown", None)) from exc
            last = exc
            if is_dispatch_failure(exc):
                # The cached pointer, or an object reached through it, stopped
                # resolving members. Drop it so the next attempt rebuilds from
                # a fresh dispatch rather than retrying against the same
                # broken one. A plain busy signal needs no such reset.
                invalidate()
            if time.monotonic() - started >= RETRY_WINDOW:
                break
            time.sleep(RETRY_DELAY)

    window = max(time.monotonic() - started, RETRY_DELAY)
    if last is not None and is_dispatch_failure(last):
        raise AutocadError(
            f"Lost the COM connection to AutoCAD and could not re-establish it "
            f"within {window:.0f}s. Check that AutoCAD is still running and has "
            "not shown a crash or recovery dialog. If it was restarted, this "
            f"server will reconnect on the next call. (details: {last})"
        )
    note_busy()
    raise AutocadError(
        f"AutoCAD stayed busy for {window:.0f}s and never accepted the request. "
        "This almost always means a dialog box is open or a command is waiting "
        "for input. Switch to AutoCAD, press Esc to cancel any running command, "
        "close any open dialog, then try again. "
        f"(last COM error: {com_message(last) if last else 'unknown'})"
    )


async def run(fn: Callable[[], T]) -> T:
    """Execute a COM callable on the worker thread without blocking the loop.

    Every tool funnels its COM work through here, so thread affinity and retry
    are handled in exactly one place.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: _worker.submit(lambda: _with_retry(fn))
    )


class _AppCache:
    """Holds the AutoCAD Application object between calls.

    Re-dispatching per call is slow across an out-of-process boundary, so the
    pointer is kept — but it goes stale when AutoCAD closes, and pywin32's
    dynamic dispatch can also stop resolving property names while AutoCAD is
    busy. Both are handled by probing on each access and, when the probe fails
    for any reason other than a plain busy signal, dropping the pointer and
    asking the retry loop for another attempt with a fresh one.
    """

    def __init__(self) -> None:
        self.app: Any = None
        self.pid: int | None = None  # the process self.app belongs to, when known

    def _dispatch(self, launch_if_needed: bool, target: int | None = None) -> Any:
        if target is not None:
            # A particular AutoCAD (D-49): COM's first choice if it is that one,
            # else that AutoCAD reached through one of its open drawings.
            try:
                first = win32com.client.GetActiveObject(PROG_ID)
                if _pid_of(first) == target:
                    return first
            except BaseException:  # noqa: BLE001 - the drawing search below decides
                pass
            found = _app_of_process(target)
            if found is None:
                raise AutocadError(
                    f"Heron could not reach the AutoCAD it works in (process {target}) through "
                    "Windows: Windows lists an AutoCAD by its saved drawings, and that one has "
                    "none open. Open or save a drawing in it, then try again. Nothing was sent to AutoCAD."
                )
            return found
        try:
            return win32com.client.GetActiveObject(PROG_ID)
        except BaseException as exc:  # noqa: BLE001
            if not launch_if_needed:
                raise AutocadError(
                    "No running AutoCAD instance was found. Start AutoCAD and "
                    "open a drawing, then try again. If AutoCAD is already open "
                    "it may still be loading, or it may be running elevated (as "
                    "Administrator) while this server is not — COM cannot "
                    f"connect across that boundary. (details: {com_message(exc)})"
                ) from exc

        try:
            app = win32com.client.Dispatch(PROG_ID)
            app.Visible = True
            return app
        except BaseException as exc:  # noqa: BLE001
            raise AutocadError(
                "Could not start AutoCAD via COM. Verify AutoCAD is installed "
                "and has been run at least once, so its Automation interface is "
                f"registered. (details: {com_message(exc)})"
            ) from exc

    def get(self, launch_if_needed: bool = False) -> Any:
        from . import sessions

        target = sessions.target()
        if self.app is not None and target is not None and self.pid != target:
            self.app = None  # the pointer is to another AutoCAD than the one to work in
        if self.app is None:
            self.app = self._dispatch(launch_if_needed, target)
            self.pid = target if target is not None else None

        # Probe the property callers actually go through, not a cheaper one:
        # Documents is where a stale dispatch shows up first.
        try:
            _ = self.app.Documents.Count
            return self.app
        except BaseException as exc:  # noqa: BLE001
            self.app = None
            if is_retryable(exc):
                raise
            raise StaleDispatchError(
                f"AutoCAD's COM interface stopped answering ({exc})"
            ) from exc


def _pid_of(app: Any) -> int | None:
    try:
        import win32process

        return int(win32process.GetWindowThreadProcessId(int(app.HWND))[1])
    except BaseException:  # noqa: BLE001
        return None


DRAWING_FILES = (".dwg", ".dxf", ".dwt", ".dws")


def _app_of_process(pid: int) -> Any:
    """That AutoCAD's Application, found through a drawing it has open, or None.

    Only the first AutoCAD started answers GetActiveObject. Every AutoCAD puts
    its open drawings in Windows' Running Object Table by file name, and a
    drawing knows its Application: that is the only way COM offers to the
    second one. Worker-thread only.
    """
    try:
        rot = pythoncom.GetRunningObjectTable()
        context = pythoncom.CreateBindCtx(0)
        monikers = list(rot.EnumRunning())
    except BaseException:  # noqa: BLE001
        return None
    for moniker in monikers:
        try:
            name = str(moniker.GetDisplayName(context, None))
            if not name.lower().endswith(DRAWING_FILES):
                continue
            unknown = rot.GetObject(moniker)
            document = win32com.client.Dispatch(unknown.QueryInterface(pythoncom.IID_IDispatch))
            app = document.Application
            if _pid_of(app) == pid:
                return app
        except BaseException:  # noqa: BLE001 - another program's entry, or a drawing closing
            continue
    return None


_cache = _AppCache()


def invalidate() -> None:
    """Drop the cached Application pointer so the next call re-dispatches."""
    _cache.app = None
    _cache.pid = None


def get_app(launch_if_needed: bool = False) -> Any:
    """The AutoCAD Application object. Worker-thread only."""
    return _cache.get(launch_if_needed=launch_if_needed)


def get_doc(launch_if_needed: bool = False) -> Any:
    """The active document, with a guiding error when there is none."""
    app = get_app(launch_if_needed=launch_if_needed)
    try:
        if app.Documents.Count == 0:
            raise AutocadError(
                "AutoCAD is running but has no drawing open. Open or create one "
                "first — autocad_create_drawing will make a new one."
            )
        return app.ActiveDocument
    except AutocadError:
        raise
    except BaseException as exc:  # noqa: BLE001
        # Reaching the document failed after the probe passed, so the pointer
        # went stale between the two. Retry with a fresh one rather than
        # reporting a problem the user cannot act on.
        invalidate()
        if is_retryable(exc):
            raise
        raise StaleDispatchError(
            f"Could not reach the active drawing ({com_message(exc)})"
        ) from exc


def get_space(doc: Any, space: str = MODEL_SPACE) -> Any:
    """ModelSpace or PaperSpace for the given document."""
    return doc.PaperSpace if space == PAPER_SPACE else doc.ModelSpace


def require_idle(doc: Any) -> None:
    """Fail early and clearly when AutoCAD is waiting for user input.

    Writing to a drawing while CMDACTIVE is set produces confusing partial
    results, so that state becomes an explicit instruction instead.
    """
    try:
        active = int(doc.GetVariable("CMDACTIVE"))
    except BaseException:  # noqa: BLE001 - probing CMDACTIVE is best-effort
        return
    if active:
        raise AutocadError(
            "AutoCAD is in the middle of a command and cannot accept new "
            "drawing operations. Switch to AutoCAD, press Esc to cancel it, "
            "then retry."
        )
