"""Explaining Heron to the modeller: why a job cannot run, and what failed or was slow (D-67).

Both read only Heron's own files - the tool index, the install and padlock
files, the audit log - so both answer with AutoCAD closed (the gate lets them
through without looking at AutoCAD, core/gate.py NO_AUTOCAD_TOOLS). The ideas
are Heron AI for Revit's heron_why and heron_gaps; the code is this project's.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ..acad import why
from ..core import audit, diagnose, gate, sessions
from ..core.bridge import bridge_enabled
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from ..core.risk import RISK, Risk
from .resources import _entries


@mcp.tool(name="autocad_why", **tool_meta("Why Heron Cannot Do It", read_only=True, idempotent=True))
@tool_errors
async def autocad_why(
    job: Annotated[
        str,
        Field(
            min_length=2,
            max_length=300,
            description="The job in plain words, as the modeller said it, e.g. 'save this as PDF' or "
            "'why can't you draw the duct'.",
        ),
    ],
) -> str:
    """Say why Heron cannot do a job, in plain words, and what the modeller does about it.

    Works with AutoCAD closed. Finds the tool for the job, then checks what is
    in the way, worst first: no tool for it, a server started read-only, the
    plug-in not installed, AutoCAD not connected (Heron not pressed), two
    AutoCADs and none picked, server and plug-in from different releases, a
    plug-in older than the tool needs, an update this chat has not loaded. It
    names the padlocks the job needs (Changes, Publish, Admin) but cannot see
    whether they are on: they live inside AutoCAD. Each reason says what to do.
    It cannot see an open command, a locked layer or another chat holding
    AutoCAD either, and says so.

    Returns:
        str: JSON: {"job", "can_run": bool, "verdict", "tool": {...},
        "other_tools": [...], "reasons": [{"reason", "blocks", "says", "what_to_do"}],
        "cannot_see"}

    Examples:
        - Use when: "why can't you do this?" / "why won't it save the PDF?" / "why was
          that refused?" about one job.
        - Use when: before a job, to check nothing is in the way: "can you plot this
          sheet?" with the padlocks unknown.
        - Use when: "is there a tool to draw a cable tray?" and the modeller wants to
          know what stops it, not only its name.
        - Don't use when: Heron as a whole seems broken - read autocad://diagnose. To
          only find a tool's name, read autocad://tools/find/{phrase}.
    """
    tools = await mcp.list_tools()
    entries = await _entries()
    answer = why.explain(
        job,
        entries=entries,
        level_of=lambda tool: RISK.get(tool, Risk.ADMIN),
        descriptions={tool.name: tool.description or "" for tool in tools},
        known_tools=set(RISK),
        report=diagnose.report(),
        bridge_on=bridge_enabled(),
        chosen_pid=sessions.chosen(),
        drawing_checked=gate._last_drawing is not None,
    )
    return dumps(answer)


@mcp.tool(name="autocad_gaps", **tool_meta("What Failed and What Was Slow", read_only=True, idempotent=True))
@tool_errors
async def autocad_gaps(
    days: Annotated[int, Field(ge=1, le=90, description="How many days back to look.")] = 7,
) -> str:
    """Sum up Heron's own log of recent days: what ran, what failed and why, what was slow.

    Works with AutoCAD closed. Reads Heron's audit log on this PC (one line per
    call, every chat): calls per tool, how many failed or were refused, the
    failures grouped by their plain reason with what to do (a padlock off,
    Heron not pressed, AutoCAD busy, an old plug-in), and the slowest jobs.
    Drawings appear by file name only; the log holds no drawing contents, so
    neither does this.

    Returns:
        str: JSON: {"days", "calls", "chats", "outcomes", "by_tool": [...],
        "failures": [{"reason", "says", "what_to_do", "count", "tools"}],
        "slowest": [{"tool", "seconds", "outcome", "drawing", "at"}], "log"}

    Examples:
        - Use when: "what went wrong this week?" / "what keeps failing?" / "which jobs
          were slow?"
        - Use when: "how many times was Heron refused today?" - pass days=1.
        - Use when: before reporting a problem, to see how often it happens.
        - Don't use when: the modeller wants what Heron did in this chat - that is
          autocad_activity. For one job that cannot run now, use autocad_why.
    """
    summary = audit.summary(days)
    summary["log"] = (
        "Heron's own audit log on this PC: one line per call, from every chat. It holds the tool, "
        "the drawing's name, the outcome and the time taken, never what was drawn."
    )
    if not summary["calls"]:
        summary["note"] = f"Nothing in Heron's log for the last {days} day(s)."
    return dumps(summary)
