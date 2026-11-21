"""The Python end of the Heron bridge to the plug-in inside AutoCAD.

The plug-in (autocad/Heron.AutoCAD.Bridge) owns whether AutoCAD is connected
and which padlocks are open. This module finds the plug-in serving the AutoCAD
we are attached to, and asks it before and after every tool call:

- The plug-in writes an address file per AutoCAD process when the user presses
  Heron, and deletes it on disconnect. No file means not connected.
- Each request is one JSON line over a current-user named pipe, carrying the
  session token from that file, and gets one JSON line back.

Every refusal ends with NOTHING_SENT, and that sentence is true: refusals are
raised before any COM work starts.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any

import pywintypes
import win32api
import win32con
import win32event
import win32file
import win32pipe
import win32process

from .errors import AutocadError
from .folders import heron_local

PROTOCOL_VERSION = 1
NOTHING_SENT = "Nothing was sent to AutoCAD."
NOT_CONNECTED = (
    "AutoCAD is not connected to Heron. Press the Heron button on the Heron tab "
    "in AutoCAD (or type HERON). " + NOTHING_SENT
)

# The host's own id for the chat. Claude Code gives every MCP server it starts
# for a chat this variable, and the same value again when that chat is
# reopened after a restart (D-61).
HOST_CHAT_VARIABLE = "CLAUDE_CODE_SESSION_ID"


def conversation_id(environ: Any = None, *, follow_host_chat: bool = False) -> str:
    """Which chat this process speaks for, to the plug-in's one-chat hold (D-61).

    1. HERON_CONVERSATION_ID, when set: a script or a developer fixes it.
    2. Only for the MCP server itself (follow_host_chat): the host's chat id,
       hashed, so a chat reopened after a restart is the same chat and keeps
       its hold. Two chats have two ids, so they still never share one.
    3. Otherwise a new id, so a command-line script run from inside a chat
       never takes that chat's hold by accident.
    """
    env = os.environ if environ is None else environ
    fixed = str(env.get("HERON_CONVERSATION_ID") or "").strip()
    if fixed:
        return fixed
    if follow_host_chat:
        session = str(env.get(HOST_CHAT_VARIABLE) or "").strip()
        if session:
            return hashlib.sha256(("heron-conversation:" + session).encode("utf-8")).hexdigest()[:32]
    return uuid.uuid4().hex


# A script that imports these modules is its own chat. The server switches to
# the host's chat id at start (follow_host_chat, called from server.main).
CONVERSATION = conversation_id()


def follow_host_chat() -> str:
    """The MCP server, at start: speak for the host's chat when the host names one (D-61)."""
    global CONVERSATION
    CONVERSATION = conversation_id(follow_host_chat=True)
    return CONVERSATION
CLIENT = os.environ.get("HERON_CLIENT_ID") or socket.gethostname()

CALL_TIMEOUT = 5.0
KEEP_TIMEOUT = 600.0
# A fillet or a super hatch on a big model can take a while; the plug-in itself
# gives up only on work AutoCAD never started (30 s).
RUN_TIMEOUT = 300.0

# The first plug-in that does its own operations (D-40).
RUN_SINCE = "1.2.0"
OLD_PLUGIN = (
    f"This needs Heron's plug-in {RUN_SINCE} or newer in AutoCAD, and the one running is older. "
    "Rebuild and reinstall it (tools/build_plugin.py, then tools/install_plugin.py) and restart "
    "AutoCAD. " + NOTHING_SENT
)
# The first plug-in that presses a button a job named for a box it expects (#101).
EXPECT_SINCE = "1.7.0"
OLD_EXPECT = (
    f"Naming a button for a box needs Heron's plug-in {EXPECT_SINCE} or newer in AutoCAD, and the one "
    "running is older. Rebuild and reinstall it, or call without expect_box: the box would then be "
    "cancelled. " + NOTHING_SENT
)
RUN_UNKNOWN = (
    "Outcome unknown: Heron in AutoCAD did not answer within {seconds:.0f} s, so the operation may "
    "still have run (one Ctrl+Z reverses it). Look at the drawing before trying again. (details: {details})"
)


class BridgeRefused(AutocadError):
    """The plug-in said no, or could not be asked. Nothing reached AutoCAD."""


class PipeUnavailable(OSError):
    """The plug-in's pipe could not be opened, so no request went out."""


def bridge_enabled() -> bool:
    """False only when a developer switched the bridge off (HERON_AUTOCAD_BRIDGE=off)."""
    return os.environ.get("HERON_AUTOCAD_BRIDGE", "on").strip().lower() not in {
        "off",
        "0",
        "false",
        "no",
    }


def bridges_dir() -> Path:
    return heron_local() / "bridges"


def acad_pid(app: Any) -> int:
    """The process id behind a COM AutoCAD.Application, from its main window."""
    _, pid = win32process.GetWindowThreadProcessId(int(app.HWND))
    return pid


def _alive(pid: int) -> bool:
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except pywintypes.error:
        return False
    try:
        return win32process.GetExitCodeProcess(handle) == 259  # STILL_ACTIVE
    finally:
        win32api.CloseHandle(handle)


def _ensure_sentence(message: str) -> str:
    message = (message or "Heron in AutoCAD refused the request.").strip()
    return message if message.endswith(NOTHING_SENT) else f"{message} {NOTHING_SENT}"


class Bridge:
    """The plug-in of one AutoCAD process."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def find(self) -> dict | None:
        """The address file, or None when this AutoCAD is not connected.

        A file whose process is gone is left over from a crash: it is deleted,
        so the next AutoCAD to reuse nothing of it starts clean.
        """
        path = bridges_dir() / f"{self.pid}.json"
        if not path.is_file():
            return None
        if not _alive(self.pid):
            try:
                path.unlink()
            except OSError:
                pass
            return None
        try:
            address = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return None
        return address if address.get("pipeName") and address.get("token") else None

    def _request(self, op: str, fields: dict[str, Any]) -> tuple[str, dict]:
        address = self.find()
        if address is None:
            raise BridgeRefused(NOT_CONNECTED)
        request = {
            "op": op,
            "token": address["token"],
            "client": CLIENT,
            "conversation": CONVERSATION,
            "protocolVersion": PROTOCOL_VERSION,
            **fields,
        }
        return address["pipeName"], request

    def call(self, op: str, timeout: float = CALL_TIMEOUT, **fields: Any) -> dict:
        pipe, request = self._request(op, fields)
        try:
            return _exchange(pipe, request, timeout)
        except TimeoutError:
            raise BridgeRefused(
                f"Heron in AutoCAD did not answer within {timeout:.0f} s. AutoCAD may "
                "be busy: press Esc in AutoCAD and try again. " + NOTHING_SENT
            ) from None
        except (pywintypes.error, OSError, ValueError) as exc:
            raise BridgeRefused(
                "Could not reach Heron in AutoCAD. Press the Heron button to "
                f"connect again. (details: {exc}) " + NOTHING_SENT
            ) from exc

    def begin(
        self, tool: str, risk: str, summary: str, drawing: str, timeout: float = CALL_TIMEOUT
    ) -> tuple[str, bool]:
        """Ask to start a job: (job id, will the plug-in ask Keep or Discard). Raises BridgeRefused."""
        job = uuid.uuid4().hex[:12]
        reply = self.call(
            "begin",
            timeout=timeout,
            job=job,
            tool=tool,
            risk=risk,
            summary=summary,
            drawing=drawing,
        )
        if not reply.get("ok"):
            raise BridgeRefused(_ensure_sentence(str(reply.get("message", ""))))
        return job, reply.get("askToKeep") is True

    def end(self, job: str, ok: bool, outcome: str, summary: str, ms: int) -> None:
        """Tell the plug-in the job finished. Never raises: the work is already done."""
        try:
            self.call("end", job=job, ok=ok, outcome=outcome, summary=summary, ms=ms)
        except AutocadError:
            pass

    def send_quiet(self, job: str, lines: list[str]) -> bool:
        """Have the plug-in type these lines into AutoCAD with echo off.

        True when the plug-in took them. False when it refused (no running
        change job, or an older plug-in without this op) or could not be
        reached: the caller then sends them itself. Raises BridgeRefused only
        for the modeller's emergency stop (D-51), so a stopped batch is never
        typed over COM instead.
        """
        try:
            reply = self.call("send_quiet", job=job, lines=lines)
        except AutocadError:
            return False
        if reply.get("refusedBy") == "Stopped":
            raise BridgeRefused(_ensure_sentence(str(reply.get("message", ""))))
        return reply.get("ok") is True

    def since_last(self, job: str) -> bool | None:
        """Did anything change in the drawing between Heron's previous change job and this one (D-54)?

        None when the plug-in cannot tell (older plug-in, not reachable).
        """
        try:
            reply = self.call("since_last", job=job)
        except AutocadError:
            return None
        if reply.get("ok") is not True or reply.get("known") is not True:
            return None
        return reply.get("changedSince") is True

    def padlocks(self) -> dict[str, Any] | None:
        """The padlocks as this AutoCAD holds them in memory (D-59), or None when it cannot tell.

        None too for a plug-in older than 1.6.0, whose ping does not say. "held"
        lists the padlocks a Windows policy holds off (D-60).
        """
        try:
            reply = self.call("ping")
        except AutocadError:
            return None
        locks, held = reply.get("padlocks"), reply.get("held")
        if not isinstance(locks, dict):
            return None
        held = held if isinstance(held, dict) else {}
        return {
            "changes": locks.get("changes") is True,
            "publish": locks.get("publish") is True,
            "admin": locks.get("admin") is True,
            "ask_to_keep": locks.get("askToKeep") is True,
            "held": [name for name in ("changes", "publish", "admin") if held.get(name) is True],
        }

    def stopped(self) -> bool:
        """True when the modeller pressed the emergency stop (HERONSTOP). False if it cannot tell."""
        try:
            return self.call("ping").get("stopped") is True
        except AutocadError:
            return False

    def run(self, job: str, operation: str, args: dict[str, Any], timeout: float = RUN_TIMEOUT) -> dict:
        """Have the plug-in do one of its own operations (D-40); what it did.

        Three ways it can go wrong, each said differently:

        - Not tried (no job, an older plug-in, not connected, the pipe would not
          open): BridgeRefused, ending "Nothing was sent to AutoCAD."
        - Tried and refused by AutoCAD: AutocadError in the plug-in's words,
          which end "Nothing was changed." (it keeps nothing of a failed one).
        - No answer in time, or the pipe broke: the work may still have run, so
          it is "Outcome unknown", never "nothing was sent".
        """
        pipe, request = self._request("run", {"job": job, "operation": operation, "args": args})
        try:
            reply = _exchange(pipe, request, timeout)
        except TimeoutError:
            raise AutocadError(RUN_UNKNOWN.format(seconds=timeout, details="no answer")) from None
        except PipeUnavailable as exc:
            raise BridgeRefused(
                f"Could not reach Heron in AutoCAD. Press the Heron button to connect again. (details: {exc}) "
                + NOTHING_SENT
            ) from exc
        except (pywintypes.error, OSError, ValueError) as exc:
            raise AutocadError(RUN_UNKNOWN.format(seconds=timeout, details=exc)) from exc
        if reply.get("ok") is True:
            result = reply.get("result")
            return result if isinstance(result, dict) else {}
        message = str(reply.get("message", ""))
        if reply.get("refusedBy") == "Operation":
            raise AutocadError(message or "AutoCAD refused the operation. Nothing was changed.")
        if reply.get("refusedBy") == "BadRequest" and "does not know the request 'run'" in message:
            raise BridgeRefused(OLD_PLUGIN)
        raise BridgeRefused(_ensure_sentence(message))

    def changes(self, job: str) -> dict | None:
        """What the job really did, counted by the plug-in from AutoCAD's events (D-50).

        None when it was not counted, the plug-in is older, or it could not be
        asked. Never raises: the work is already done.
        """
        try:
            reply = self.call("changes", job=job)
        except AutocadError:
            return None
        if reply.get("ok") is not True or reply.get("counted") is not True:
            return None
        return {
            "added": int(reply.get("added", 0)),
            "modified": int(reply.get("modified", 0)),
            "erased": int(reply.get("erased", 0)),
            "erased_handles": [str(h) for h in reply.get("erasedHandles", [])],
        }

    def expect_dialog(self, job: str, title: str, button: str) -> str | None:
        """Tell the plug-in this job expects one box: press ``button`` on a box titled exactly ``title``, once (#101).

        None when the plug-in took it; otherwise why not, ending "Nothing was
        sent to AutoCAD." (the caller sends nothing then). Only an Admin job is
        allowed: the plug-in refuses any other level.
        """
        try:
            reply = self.call("expect_dialog", job=job, title=title, button=button)
        except AutocadError as exc:
            return str(exc)
        if reply.get("ok") is True:
            return None
        message = str(reply.get("message", ""))
        if reply.get("refusedBy") == "BadRequest" and "does not know the request" in message:
            return OLD_EXPECT
        return _ensure_sentence(message)

    def dialogs(self, job: str) -> list[dict]:
        """The boxes AutoCAD showed during this job that the plug-in closed (D-66).

        Each is {"title", "pressed" ("Cancel" | "No" | "Esc" | "none"), "closed"
        (True, False, or None when not known yet)}. Empty when there were none,
        the plug-in is older, or it could not be asked. Never raises.
        """
        try:
            reply = self.call("dialogs", job=job)
        except AutocadError:
            return []
        boxes = reply.get("dialogs") if reply.get("ok") is True else None
        if not isinstance(boxes, list):
            return []
        found = []
        for box in boxes:
            if not isinstance(box, dict):
                continue
            closed = box.get("closed")
            found.append(
                {
                    "title": str(box.get("title") or "a box with no title"),
                    "pressed": str(box.get("pressed") or "Esc"),
                    "closed": closed if isinstance(closed, bool) else None,
                    "asked": box.get("asked") is True,
                }
            )
        return found

    def ask_erase(self, job: str, summary: str) -> dict:
        """Ask the modeller about what the job erased; the plug-in brings them back unless kept.

        {"answer": "keep_erased" | "restored" | "nothing_erased" | "unknown", "restored": int}.
        "unknown" means the plug-in could not be asked: the objects may still be erased.
        """
        try:
            reply = self.call("ask_erase", timeout=KEEP_TIMEOUT, job=job, summary=summary)
        except AutocadError:
            return {"answer": "unknown", "restored": 0}
        if reply.get("ok") is not True:
            return {"answer": "unknown", "restored": 0}
        answer = reply.get("answer")
        result = {
            "answer": answer if answer in {"keep_erased", "restored", "nothing_erased"} else "unknown",
            "restored": int(reply.get("restored", 0)),
        }
        if reply.get("message"):
            result["message"] = str(reply["message"])
        return result

    def ask_keep(self, job: str, summary: str, handles: list[str]) -> str:
        """keep | discard | keep_rest, or "unknown" when the plug-in could not answer.

        Only a clear "discard" may undo anything: a broken pipe is not the
        modeller saying no, so it comes back as "unknown" and the change stays.
        """
        try:
            reply = self.call(
                "ask_keep", timeout=KEEP_TIMEOUT, job=job, summary=summary, handles=handles
            )
        except AutocadError:
            return "unknown"
        answer = reply.get("answer")
        return answer if answer in {"keep", "discard", "keep_rest"} else "unknown"


def _exchange(pipe_name: str, request: dict, timeout: float) -> dict:
    """Send one JSON line, read one JSON line, all within ``timeout`` seconds."""
    path = rf"\\.\pipe\{pipe_name}"
    ms = max(1, int(timeout * 1000))
    try:
        handle = _open(path, ms)
    except pywintypes.error as exc:
        # Nothing has gone out yet: the caller may say "nothing was sent".
        raise PipeUnavailable(str(exc)) from exc
    event = win32event.CreateEvent(None, True, False, None)
    try:
        _overlapped_write(handle, event, (json.dumps(request) + "\n").encode("utf-8"), ms)
        data = b""
        while not data.endswith(b"\n"):
            data += _overlapped_read(handle, event, ms)
        return json.loads(data.decode("utf-8"))
    finally:
        win32api.CloseHandle(event)
        win32file.CloseHandle(handle)


def _open(path: str, ms: int) -> Any:
    def create() -> Any:
        return win32file.CreateFile(
            path,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0,
            None,
            win32file.OPEN_EXISTING,
            win32file.FILE_FLAG_OVERLAPPED,
            None,
        )

    try:
        return create()
    except pywintypes.error as exc:
        if exc.winerror != 231:  # ERROR_PIPE_BUSY
            raise
        win32pipe.WaitNamedPipe(path, ms)
        return create()


def _wait(handle: Any, overlapped: Any, ms: int) -> int:
    if win32event.WaitForSingleObject(overlapped.hEvent, ms) == win32event.WAIT_TIMEOUT:
        win32file.CancelIo(handle)
        raise TimeoutError
    return win32file.GetOverlappedResult(handle, overlapped, False)


def _overlapped_write(handle: Any, event: Any, payload: bytes, ms: int) -> None:
    overlapped = pywintypes.OVERLAPPED()
    overlapped.hEvent = event
    win32event.ResetEvent(event)
    win32file.WriteFile(handle, payload, overlapped)
    _wait(handle, overlapped, ms)


def _overlapped_read(handle: Any, event: Any, ms: int) -> bytes:
    overlapped = pywintypes.OVERLAPPED()
    overlapped.hEvent = event
    win32event.ResetEvent(event)
    buffer = win32file.AllocateReadBuffer(65536)
    win32file.ReadFile(handle, buffer, overlapped)
    count = _wait(handle, overlapped, ms)
    if count == 0:
        raise OSError("Heron in AutoCAD closed the connection")
    return bytes(buffer[:count])
