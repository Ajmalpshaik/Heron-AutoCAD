"""One JSON line per tool call, kept for good.

The audit is the record of what Heron did to which drawing and when. It sits
apart from any log that gets rotated, it is never pruned, and failing to write
it never fails the tool: the work has already happened by then.

``summary`` reads it back for autocad_gaps (D-67): what ran, what failed and
why, what was slow. A line holds only the tool, its level, the drawing, the
outcome, a reason word from a fixed list and the time taken - never what was
drawn or typed - so the summary cannot leak drawing contents either.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from .folders import heron_local

_lock = threading.Lock()


def audit_dir() -> Path:
    """Where the audit lines go: %LOCALAPPDATA%\\Heron\\autocad\\audit.

    Windows always sets %LOCALAPPDATA%. Where it is unset or not a full path
    (a cloud runner, CI), the folder is the one it normally points at under the
    user's home, never a folder relative to wherever the server was started
    (issue #43, core/folders.py).
    """
    return heron_local() / "audit"


def record(**fields: Any) -> None:
    """Append one line: at, conversation, tool, risk, drawing, ok, outcome, reason, ms."""
    now = datetime.now(timezone.utc)
    line = json.dumps({"at": now.isoformat(timespec="milliseconds"), **fields}, default=str)
    try:
        folder = Path(audit_dir())
        folder.mkdir(parents=True, exist_ok=True)
        with _lock, open(folder / f"audit-{now:%Y%m}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# Why a call did not finish, as one word from this list, worked out from the
# message the chat saw. Only the word is kept, never the message: a message can
# name layers, handles or files. First match wins, so "Outcome unknown" and a
# failed Discard come before "busy": their messages often say AutoCAD was busy,
# and "try again" is the one thing not to do after them (#209).
_REASON_SIGNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("stopped", ("HERONSTOP",)),
    ("not_connected", ("not connected to Heron", "Press the Heron button", "Press Heron in AutoCAD")),
    ("changes_off", ("Changes is off",)),
    ("publish_off", ("Publish is off",)),
    ("admin_off", ("Admin is off",)),
    ("drawing_not_checked", ("has not checked", "since Heron last checked", "call autocad_status on this one")),
    ("in_use", ("in use by another chat",)),
    ("old_plugin", ("or newer in AutoCAD", "plug-in older than", "Update Heron so both sides match",
                    "bridge protocol")),  # fmt: skip
    ("outcome_unknown", ("Outcome unknown",)),
    ("discard_failed", ("Discard not possible", "Discard failed", "Discard did not take")),
    ("autocad_busy", ("did not answer within", "did not get to the request", "Press Esc", "busy",
                      "middle of a command")),
    ("no_autocad", ("No running AutoCAD", "Could not start AutoCAD", "Lost the COM connection",
                    "could not reach the AutoCAD", "has no drawing open", "no AutoCAD")),
    ("bad_input", ("Invalid input",)),
    ("autocad_rejected", ("AutoCAD rejected the operation",)),
    ("no_dry_run", ("A dry run is not possible",)),
)

# Each reason word in plain words, and what the modeller does about it.
REASONS: dict[str, tuple[str, str]] = {
    "stopped": ("The modeller had stopped Heron (HERONSTOP).", "Type HERONSTOP again in AutoCAD to let Heron work."),
    "not_connected": ("AutoCAD was not connected to Heron.", "Press the Heron button on the Heron tab (or type HERON)."),
    "changes_off": ("The Changes padlock was off.", "Turn Changes on in Settings on the Heron tab (or type HERONCHANGES)."),
    "publish_off": ("The Publish padlock was off.", "Turn Publish on in Settings on the Heron tab (or type HERONPUBLISH)."),
    "admin_off": ("The Admin padlock was off.", "Turn Admin on in Settings on the Heron tab (or type HERONADMIN)."),
    "drawing_not_checked": ("Heron had not checked that drawing's units yet.",
                            "Nothing to fix by hand: Heron calls autocad_status first, then tries again."),
    "in_use": ("Another chat was using that AutoCAD.", "Finish or close the other chat, then try again."),
    "old_plugin": ("The plug-in in AutoCAD was older than the job needs.",
                   "Install the latest Heron release (AutoCAD closed), then restart AutoCAD."),
    "autocad_busy": ("AutoCAD was busy: a command or a dialog box was open.", "Press Esc in AutoCAD, then try again."),
    "no_autocad": ("AutoCAD was not running, or Heron could not reach it.", "Start AutoCAD and press Heron."),
    "outcome_unknown": ("Heron could not tell whether the job ran.", "Look at the drawing before trying again."),
    "bad_input": ("The request did not make sense to the tool (a wrong value or a missing one).",
                  "Usually the chat's own mistake: ask it to try again with the values spelled out."),
    "autocad_rejected": ("AutoCAD refused the operation (a locked or frozen layer, a read-only drawing, a command waiting).",
                         "Check the layer is unlocked and thawed and no command is waiting, then try again."),
    "discard_failed": ("Discard could not take the change back.", "Check the drawing and remove what is left by hand."),
    "no_dry_run": ("A dry run was asked of a tool that cannot have one (a save, an export, a command, AutoLISP).",
                   "Call it without dry_run when the modeller is sure."),
    "other": ("It failed for another reason; the chat saw the full message at the time.",
              "If it keeps happening, ask the chat to call autocad_why for that job."),
}  # fmt: skip

# What an outcome means when the line has no reason word (lines older than D-67).
_OUTCOME_REASON = {"refused": "other", "failed": "other", "unknown": "outcome_unknown"}
NOT_COUNTED = frozenset({"autocad_gaps", "autocad_why"})  # reading the log is not work in a drawing


def reason_of(message: str) -> str:
    """The reason word for a refusal or a failure message; "" for a message that is not one."""
    if not message:
        return ""
    for word, signs in _REASON_SIGNS:
        if any(sign.lower() in message.lower() for sign in signs):
            return word
    return "other"


def drawing_name(drawing: str) -> str:
    """Only the file name of a drawing (C:\\Jobs\\A\\plan.dwg -> plan.dwg): never its folders."""
    return PureWindowsPath(drawing).name if drawing else ""


def _lines(folder: Path, since: datetime) -> list[dict[str, Any]]:
    found = []
    for path in sorted(folder.glob("audit-*.jsonl")):
        if path.stem.removeprefix("audit-") < f"{since:%Y%m}":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in text.splitlines():
            try:
                line = json.loads(raw)
                at = datetime.fromisoformat(str(line["at"]))
            except (ValueError, KeyError, TypeError):
                continue
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if at >= since and isinstance(line.get("tool"), str):
                line["_at"] = at
                found.append(line)
    return found


def summary(days: int = 7, *, folder: Path | None = None, now: datetime | None = None, slowest: int = 5) -> dict[str, Any]:
    """What ran in the last ``days`` days, what failed and why, what was slow.

    Counts per tool, failures grouped by their plain reason, and the slowest
    jobs. Drawings appear by file name only.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    where = folder or audit_dir()
    lines = [line for line in _lines(where, since) if line["tool"] not in NOT_COUNTED]

    outcomes = Counter(str(line.get("outcome", "")) for line in lines)
    per_tool: dict[str, dict[str, Any]] = {}
    reasons: dict[str, dict[str, Any]] = {}
    for line in lines:
        outcome = str(line.get("outcome", ""))
        row = per_tool.setdefault(line["tool"], {"tool": line["tool"], "calls": 0, "failed": 0, "refused": 0, "_ms": []})
        row["calls"] += 1
        if outcome in ("failed", "unknown"):
            row["failed"] += 1
        elif outcome == "refused":
            row["refused"] += 1
        if isinstance(line.get("ms"), int | float):
            row["_ms"].append(int(line["ms"]))
        if outcome in _OUTCOME_REASON:
            word = str(line.get("reason") or _OUTCOME_REASON[outcome])
            word = word if word in REASONS else "other"
            group = reasons.setdefault(word, {"reason": word, "count": 0, "tools": Counter()})
            group["count"] += 1
            group["tools"][line["tool"]] += 1

    tools = []
    for row in per_tool.values():
        times = sorted(row.pop("_ms"))
        row["typical_seconds"] = round(times[len(times) // 2] / 1000, 1) if times else None
        row["longest_seconds"] = round(times[-1] / 1000, 1) if times else None
        tools.append(row)
    tools.sort(key=lambda r: (-r["calls"], r["tool"]))

    failures = []
    for group in sorted(reasons.values(), key=lambda g: (-g["count"], g["reason"])):
        says, do = REASONS[group["reason"]]
        failures.append({
            "reason": group["reason"],
            "says": says,
            "what_to_do": do,
            "count": group["count"],
            "tools": [{"tool": tool, "count": count} for tool, count in group["tools"].most_common(5)],
        })

    timed = [line for line in lines if isinstance(line.get("ms"), int | float)]
    timed.sort(key=lambda line: (-line["ms"], line["_at"]))
    slow = [
        {
            "tool": line["tool"],
            "seconds": round(line["ms"] / 1000, 1),
            "outcome": line.get("outcome", ""),
            "drawing": drawing_name(str(line.get("drawing") or "")),
            "at": line["_at"].isoformat(timespec="seconds"),
        }
        for line in timed[:slowest]
    ]

    return {
        "days": days,
        "from": since.isoformat(timespec="seconds"),
        "to": now.isoformat(timespec="seconds"),
        "calls": len(lines),
        "chats": len({line.get("conversation") for line in lines if line.get("conversation")}),
        "drawings": len({drawing_name(str(line.get("drawing") or "")) for line in lines} - {""}),
        "outcomes": dict(sorted(outcomes.items())),
        "by_tool": tools,
        "failures": failures,
        "slowest": slow,
    }
