"""What Heron did in this chat, and undoing its last change (D-54).

The idea is Heron AI for Revit's activity pane and guarded "undo Heron's last
change" (its D-157): the undo is sent only when nothing else changed the
drawing since Heron's change, so the modeller's own work is never undone by
it. The plug-in says whether anything changed in between; the gate knows
what Heron itself did since.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from pydantic import Field

from ..core import gate
from ..core.connection import get_doc, mark_writing, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta


@mcp.tool(name="autocad_activity", **tool_meta("What Heron Did", read_only=True, idempotent=True))
@tool_errors
async def autocad_activity(
    limit: Annotated[int, Field(ge=1, le=50, description="How many of the latest jobs to list.")] = 10,
) -> str:
    """List what Heron did in this chat, newest first: each change, its drawing and what it made.

    Each entry: when, the tool, what it was, the drawing, the outcome (done,
    discarded, failed, refused), the handles it created and what the plug-in
    counted (added, modified, erased). Reads are left out. Pass handles to
    autocad_show to put a job's objects on screen. Says also whether Heron's
    last change can still be undone with autocad_undo_last.

    Returns:
        str: JSON: {"jobs": [...], "undo_last": {"possible": bool, "what": str}}

    Examples:
        - Use when: "what have you done so far?" or "what did that last step make?"
        - Use when: "show me what you drew ten minutes ago" -> then autocad_show
          its created handles.
        - Don't use when: the modeller wants AutoCAD's own undo history - that is
          AutoCAD's UNDO list, which includes their own work.
    """
    last = gate.last_change()
    undo = {"possible": last is not None}
    if last:
        undo["what"] = f"{last['what']} ({last['at']}, {last['drawing']})"
    return dumps({"jobs": gate.activity(limit), "undo_last": undo})


@mcp.tool(name="autocad_undo_last", **tool_meta("Undo Heron's Last Change", destructive=True))
@tool_errors
async def autocad_undo_last() -> str:
    """Undo Heron's own last change in this chat, only if nothing else changed the drawing since.

    The guard is the point: Ctrl+Z undoes whatever came last, which may be the
    modeller's own work. This undoes Heron's last change only when the plug-in
    saw no change in the drawing since it (the modeller's, or another
    program's) and Heron itself did nothing since but look. Otherwise it is
    refused and says why, and the modeller uses Ctrl+Z themselves. One level
    only: after it, there is nothing more to undo this way.

    Returns:
        str: JSON: {"undone": str, "drawing": str, "removed": [handles]}

    Examples:
        - Use when: "undo what you just did" / "take that back".
        - Use when: "that was wrong, put it back as it was" right after a Heron change.
        - Don't use when: the modeller wants their own last step undone - they press
          Ctrl+Z; Heron does not undo their work.
        - Don't use when: one object should go - autocad_delete_entities.

    Error Handling:
        - Refused when Heron made no change in this chat, when the drawing is
          another one, when anything changed since, when Heron zoomed or ran a
          command since (with Ask to Keep off), or with a plug-in older than 1.5.0.
    """
    last = gate.last_change()
    if last is None:
        raise AutocadError(
            "Heron has no change of its own to undo in this chat (none yet, or it was already "
            "undone, discarded, or followed by a raw command or a save). Nothing was changed."
        )

    def look() -> str:
        doc = get_doc()
        return str(doc.FullName) or str(doc.Name)

    drawing = await run(look)
    if drawing != last["drawing"]:
        raise AutocadError(
            f"Heron's last change was in {last['drawing']}, and the active drawing is {drawing}. "
            "Switch back to it first. Nothing was changed."
        )
    since = await asyncio.to_thread(gate.changed_by_modeller_since)
    if since is None:
        raise AutocadError(
            "Heron's plug-in in AutoCAD cannot say whether the drawing changed since (it needs plug-in "
            "1.5.0 or newer). Undo by hand with Ctrl+Z if you are sure. Nothing was changed."
        )
    if since:
        raise AutocadError(
            "The drawing changed after Heron's last change (your own work, or another program), so "
            "undoing it could take your work with it. Use Ctrl+Z yourself if you want it gone. "
            "Nothing was changed."
        )
    if not last["marked"] and last["views_since"]:
        raise AutocadError(
            "Heron zoomed or showed objects since its last change, and with Ask to Keep off there is no "
            "UNDO mark to go back to exactly, so one step back would undo the zoom instead. Use Ctrl+Z "
            "until it is gone. Nothing was changed."
        )

    def undo() -> dict[str, Any]:
        doc = get_doc()
        mark_writing()
        doc.SendCommand("_.UNDO _Back " if last["marked"] else "_.UNDO 1 ")
        left = []
        for handle in last.get("created", []):
            try:
                doc.HandleToObject(handle)
                left.append(handle)
            except Exception as exc:  # noqa: BLE001 - gone is what we want
                raise_if_busy(exc)
        return {"left": left}

    done = await run(undo)
    if done["left"]:
        raise AutocadError(
            "Outcome unknown: the undo was sent, but these objects Heron made are still there: "
            + ", ".join(done["left"][:20])
            + ". Look at the drawing before doing anything else."
        )
    return dumps({"undone": last["what"], "drawing": drawing, "removed": last.get("created", [])})
