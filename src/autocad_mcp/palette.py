"""The Heron palette's Run: one saved command, started from AutoCAD (D-68).

The Saved commands tab of the plug-in's palette lets the modeller fill a
command's inputs and press Run with no chat. The server lives with the chat,
so the palette starts a copy of it for that one run:

    python -m autocad_mcp --run-saved request.json --acad-pid 4242

That copy is a chat of its own to the plug-in: it runs autocad_status (the
units come first, D-19) and then the saved command through the very same
gate, hold, padlocks, Keep or Discard and HERONSTOP as any chat. Nothing here
goes round them. It prints one JSON line, {"ok", "message"}, for the palette,
and frees the AutoCAD when it is done, so the modeller's chat is not kept
waiting for three minutes.

Every server also writes where it runs from to server.json when it starts:
that is how the palette finds a Python with Heron installed.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .core import sessions
from .core.bridge import NOT_CONNECTED, Bridge
from .core.errors import AutocadError


def server_file() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Heron" / "autocad" / "server.json"


def write_server_file() -> None:
    """Say where this server runs from, for the palette. Never stops the server."""
    path = server_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        record = {"python": sys.executable, "version": __version__, "written": time.strftime("%Y-%m-%dT%H:%M:%S")}
        temp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        pass


def _no(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message.strip()}


def _error_text(text: str) -> str:
    return text[len("Error:"):].strip() if text.startswith("Error:") else text.strip()


def outcome(name: str, text: str) -> dict[str, Any]:
    """The saved command's answer, said for the palette in one or two sentences."""
    if text.startswith("Error:"):
        return _no(_error_text(text))
    try:
        report = json.loads(text)
    except ValueError:
        # "Discarded: nothing was kept." and other plain answers from the gate.
        return {"ok": not text.startswith("Discarded"), "message": text.strip()}
    if not isinstance(report, dict):
        return {"ok": True, "message": f"Done: '{name}'."}
    steps = report.get("steps") or []
    ran, failed = int(report.get("ran", 0)), int(report.get("failed", 0))
    note = report.get("heron_note")
    if failed:
        row = next((r for r in steps if r.get("ok") is False), {})
        result = row.get("result")
        why = _error_text(result) if isinstance(result, str) else json.dumps(result)[:300]
        message = f"'{name}' stopped at step {row.get('index', '?')} ({row.get('label') or row.get('tool')}): {why}"
        if report.get("hint"):
            message += f" {report['hint']}"
        return _no(message)
    message = f"Done: '{name}', {ran} of {len(steps)} step(s)."
    if report.get("hint") and ran < len(steps):
        message += f" {report['hint']}"
    if note:
        message += f" {note}"
    return {"ok": ran == len(steps), "message": message}


async def run_saved(request: dict[str, Any], acad_pid: int | None) -> dict[str, Any]:
    """Status, then the saved command, both through the gate. Never raises."""
    from .tools import document, saved_commands

    name = request.get("name")
    inputs = request.get("inputs") or {}
    if not isinstance(name, str) or not name.strip():
        return _no("The palette's request names no saved command. Nothing was sent to AutoCAD.")
    if not isinstance(inputs, dict):
        return _no("The palette's request has no inputs Heron can read. Nothing was sent to AutoCAD.")
    if acad_pid:
        try:
            sessions.choose(acad_pid)
        except AutocadError as exc:
            return _no(str(exc))
    try:
        status = await document.autocad_status()
        if status.startswith("Error:"):
            return _no(_error_text(status))
        try:
            heron = json.loads(status).get("heron", {})
        except (ValueError, AttributeError):
            heron = {}
        if isinstance(heron, dict) and heron.get("connected") is False and heron.get("bridge") != "off":
            return _no(heron.get("message") or NOT_CONNECTED)
        text = await saved_commands.autocad_saved_command(action="run", name=name, inputs=inputs)
        return outcome(name, text)
    finally:
        _free(acad_pid)


def _free(acad_pid: int | None) -> None:
    """Let the modeller's chat in at once, not after three quiet minutes."""
    pid = acad_pid or sessions.chosen()
    if not pid:
        return
    try:
        Bridge(pid).call("release")
    except Exception:  # noqa: BLE001 - the hold frees itself in 3 minutes anyway
        pass


def main(request_file: str, acad_pid: int | None) -> int:
    """For server.py's --run-saved. Prints one JSON line; exit 0 when it ran."""
    import asyncio

    try:
        request = json.loads(Path(request_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        answer = _no(f"Heron could not read the palette's request ({exc}). Nothing was sent to AutoCAD.")
    else:
        try:
            answer = asyncio.run(run_saved(request if isinstance(request, dict) else {}, acad_pid))
        except Exception as exc:  # noqa: BLE001 - the palette must always get an answer
            answer = _no(f"Heron's server hit an error: {type(exc).__name__}: {exc}. Look at the drawing.")
    print(json.dumps(answer), flush=True)
    return 0 if answer.get("ok") else 1
