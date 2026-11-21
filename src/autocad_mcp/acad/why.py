"""Why Heron cannot do a job, in plain words (D-67, issue #88).

The idea is Heron AI for Revit's heron_why: for one job, the real reason it
cannot run and what the modeller does about it. Everything here comes from
Heron's own files - the tool index and the install and connection report of
core/diagnose.py - never from AutoCAD over COM, so it answers with AutoCAD
closed. The padlocks live inside AutoCAD (D-59): when one AutoCAD is connected
for this chat, its plug-in says over the pipe which are on and which a Windows
policy holds (D-60); otherwise it names the ones a job needs and never claims
whether they are on.

What it cannot see from here, it says so: an open command or dialog box, a
locked layer, another chat holding AutoCAD.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from ..core.risk import Risk
from .findtool import Entry, Hit, expand, rank, words

# Words that wrap the job without being part of it: "why can't you draw a ..."
_WRAPPING = re.compile(
    r"^\s*(why\s+)?(can'?t|cannot|can\s+not|won'?t|couldn'?t|didn'?t|doesn'?t|don'?t|isn'?t|is\s+not)?"
    r"(\s+(you|heron|claude|it))?(\s+(be\s+able\s+to|able\s+to|let\s+me|let\s+you))?\s*",
    re.IGNORECASE,
)

# Which padlocks each level needs, with the command that turns each one on.
PADLOCKS: dict[Risk, tuple[str, ...]] = {
    Risk.READ: (),
    Risk.VIEW: (),
    Risk.CHANGE: ("changes",),
    Risk.PUBLISH: ("changes", "publish"),
    Risk.ADMIN: ("changes", "admin"),
}
_PADLOCK_NAME = {"changes": ("Changes", "HERONCHANGES"), "publish": ("Publish", "HERONPUBLISH"),
                 "admin": ("Admin", "HERONADMIN")}  # fmt: skip
_NEEDS_PLUGIN = re.compile(r"plug-in (\d+\.\d+\.\d+) or newer|plug-in older than (\d+\.\d+\.\d+)")
CANNOT_SEE = (
    "Heron cannot see from here whether a padlock is on (unless this chat's AutoCAD answered), "
    "whether a command or a dialog box is open "
    "in AutoCAD, whether a layer is locked or frozen, or whether another chat holds AutoCAD; the "
    "tool's own refusal says so if one of those is the reason."
)


def the_job(phrase: str) -> str:
    """The job without its wrapping: "why can't you draw a duct" -> "draw a duct"."""
    return _WRAPPING.sub("", phrase, count=1).strip(" ?.!") or phrase.strip()


def needs_plugin(description: str) -> str | None:
    """The plug-in version a tool's own docstring says it needs, or None."""
    found = _NEEDS_PLUGIN.search(description)
    return (found.group(1) or found.group(2)) if found else None


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def _reason(key: str, says: str, do: str, blocks: bool = True) -> dict[str, Any]:
    return {"reason": key, "blocks": blocks, "says": says, "what_to_do": do}


def _weak(hit: Hit, phrase: str) -> bool:
    """The best tool matched under half of the job's own words: maybe not this job at all."""
    typed = [word for word in dict.fromkeys(words(phrase)) if not word.isdigit()]
    if len(typed) < 2:
        return False
    found = [word for word in typed if set(expand([word])) & set(hit.matched)]
    return len(found) * 2 < len(typed)


def explain(
    phrase: str,
    *,
    entries: list[Entry],
    level_of: Callable[[str], Risk],
    descriptions: dict[str, str],
    known_tools: set[str],
    report: dict[str, Any],
    bridge_on: bool,
    chosen_pid: int | None,
    drawing_checked: bool,
) -> dict[str, Any]:
    """The reasons one job cannot run, worst first, each with what to do.

    ``entries`` are the tools this server offers; ``known_tools`` every tool
    Heron has (a --read-only server offers fewer). ``report`` is
    diagnose.report().
    """
    job = the_job(phrase)
    hits = rank(entries, job, limit=3, reads=lambda tool: level_of(tool) is Risk.READ)
    reasons: list[dict[str, Any]] = []
    read_only_server = bool(known_tools - {entry.tool for entry in entries})

    best = hits[0] if hits else None
    if best is None:
        reasons.append(_reason(
            "no_tool", "Heron has no tool for this job.",
            "Do it by hand in AutoCAD, or describe it in other words (read autocad://tools for the whole "
            "list). With the Admin padlock on, autocad_send_command can run an AutoCAD command Heron has "
            "no tool for: only if the modeller agrees.",
        ))  # fmt: skip
        if read_only_server:
            reasons.append(_reason(
                "read_only_server",
                "This chat's Heron server was started read-only (--read-only), so no tool that changes a "
                "drawing is offered at all.",
                "If the job changes the drawing, restart the server without --read-only (the chat's MCP "
                "settings), then reopen the chat.",
            ))  # fmt: skip
    elif _weak(best, job):
        reasons.append(_reason(
            "no_sure_tool",
            f"Heron has no tool clearly for this job; the closest is {best.tool}, which matched only "
            f"{', '.join(best.matched) or 'a few words'}.",
            "Check its summary below is the job. If not, do it by hand in AutoCAD or describe it in other "
            "words.",
            blocks=False,
        ))  # fmt: skip

    level = level_of(best.tool) if best else None
    needs_autocad = best is not None
    connected = report.get("autocads_connected") or []

    if needs_autocad and bridge_on:
        if report.get("plugin_installed") is None and not connected:
            reasons.append(_reason(
                "plugin_not_installed", "Heron's plug-in is not installed for AutoCAD.",
                "Run Install.bat from the Heron release with AutoCAD closed, then start AutoCAD.",
            ))  # fmt: skip
        if not connected:
            reasons.append(_reason(
                "not_connected", "No AutoCAD is connected to Heron (or AutoCAD is closed).",
                "Start AutoCAD, open the drawing, and press the Heron button on the Heron tab (or type HERON).",
            ))  # fmt: skip
        elif len(connected) > 1 and chosen_pid is None:
            reasons.append(_reason(
                "which_autocad", f"{len(connected)} AutoCADs are connected to Heron, and none is picked for this chat.",
                "Say which one; the chat picks it with autocad_use_autocad.",
            ))  # fmt: skip

    for check in report.get("checks", []):
        if check.get("check") == "server and plug-in match" and check.get("state") == "FAIL":
            reasons.append(_reason("versions_do_not_match", check["detail"],
                                   "Install the server and the plug-in from the same Heron release."))  # fmt: skip

    wanted = needs_plugin(descriptions.get(best.tool, "")) if best else None
    if wanted and connected:
        running = [a for a in connected if chosen_pid in (None, a.get("pid"))]
        old = [a for a in running if a.get("plugin_version") and _version(a["plugin_version"]) < _version(wanted)]
        if old:
            reasons.append(_reason(
                "old_plugin",
                f"{best.tool} needs Heron's plug-in {wanted} or newer, and AutoCAD runs {old[0]['plugin_version']}.",
                "Install the latest Heron release (AutoCAD closed), then restart AutoCAD.",
            ))  # fmt: skip
    for check in report.get("checks", []):
        if check.get("check") == "AutoCAD runs the installed plug-in" and check.get("state") != "PASS":
            reasons.append(_reason("restart_autocad", check["detail"], "Close and restart AutoCAD.", blocks=False))

    if level is not None and bridge_on:
        locks = report.get("padlocks")
        held = set((locks or {}).get("held") or ())
        for padlock in PADLOCKS[level]:
            name, command = _PADLOCK_NAME[padlock]
            if locks is None:
                # Nothing answered for this chat's AutoCAD (none, several and none picked, an
                # older plug-in): the padlocks live inside AutoCAD (D-59), so never guess.
                reasons.append(_reason(
                    f"needs_{padlock}",
                    f"{best.tool} needs the {name} padlock. Heron cannot see from here whether it is on: "
                    "the padlocks live inside AutoCAD, and are off each time AutoCAD starts.",
                    f"If {name} is off, turn it on in Settings on the Heron tab in AutoCAD (or type {command}). "
                    "If the job is then refused, the refusal names the padlock.",
                    blocks=False,
                ))  # fmt: skip
            elif padlock in held:
                reasons.append(_reason(
                    f"{padlock}_held",
                    f"{best.tool} needs the {name} padlock, and a Windows policy on this PC holds it off.",
                    "Only the PC's administrator can lift it (HKLM\\SOFTWARE\\Policies\\Heron\\AutoCAD): "
                    "ask whoever looks after this PC.",
                ))  # fmt: skip
            elif not locks.get(padlock):
                # This AutoCAD's plug-in said so (its ping).
                reasons.append(_reason(
                    f"{padlock}_off",
                    f"{best.tool} needs the {name} padlock, and it is off in this AutoCAD.",
                    f"Turn {name} on in Settings on the Heron tab in AutoCAD (or type {command}).",
                ))  # fmt: skip

    if level is not None and level not in (Risk.READ, Risk.VIEW) and not drawing_checked:
        reasons.append(_reason(
            "drawing_not_checked", "Heron has not checked a drawing's units in this chat yet.",
            "Nothing to do by hand: the chat calls autocad_status first, then the job.", blocks=False,
        ))  # fmt: skip

    for check in report.get("checks", []):
        if check.get("check") == "server up to date" and check.get("state") != "PASS":
            reasons.append(_reason("update_waiting", check["detail"],
                                   "Close and reopen the chat (or restart Claude).", blocks=False))  # fmt: skip

    if not bridge_on:
        reasons.append(_reason(
            "bridge_off", "This server runs with Heron's plug-in checks off (--no-bridge, developer use): "
            "the padlocks are not checked.", "Nothing, unless this was not meant: restart without --no-bridge.",
            blocks=False,
        ))  # fmt: skip

    blocking = [r for r in reasons if r["blocks"]]
    if blocking:
        verdict = f"Cannot run yet: {blocking[0]['says']} {blocking[0]['what_to_do']}"
    elif best is not None:
        verdict = f"Nothing Heron can see is in the way: {best.tool} should run."
    else:
        verdict = "Heron has no tool for this job."
    by_name = {entry.tool: entry for entry in entries}
    return {
        "job": job,
        "can_run": not blocking,
        "verdict": verdict,
        "tool": None if best is None else {
            "tool": best.tool,
            "level": level.value if level else None,
            "needs": [_PADLOCK_NAME[p][0] for p in PADLOCKS[level]] if level else [],
            "summary": by_name[best.tool].summary if best.tool in by_name else "",
            "needs_plugin": wanted,
        },
        "other_tools": [hit.tool for hit in hits[1:]],
        "reasons": reasons,
        "cannot_see": CANNOT_SEE,
    }
