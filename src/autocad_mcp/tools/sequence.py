"""One call that runs several tools in order: AutoLISP's ``progn``, as a tool.

Setting up a sheet is five calls that only make sense together — make the
layout, set the page up, place the title block, cut the viewport, fill the
attributes. Sent one at a time they are five round trips, five chances for the
drawing to change underneath, and five places to stop half-finished.

``autocad_sequence`` takes the list. **Every step's arguments are checked
against that tool's own schema before the first one runs**, so a sequence that
cannot be completed changes nothing at all — the same rule
``autocad_batch_draw`` follows.

**It cannot raise what you are allowed to do.** The sequence itself is a
CHANGE tool, and it refuses any step whose level is Publish or Admin. So it can
draw, modify and delete exactly as the Changes padlock already allows, and it
can never save a file, run a command or evaluate AutoLISP on the way. There is
no recursion either: a sequence cannot contain a sequence.

Undo: each step keeps its own undo step, so Ctrl+Z backs them out one at a
time — which is what a drafter wants when step four of five was wrong. With the
**Ask to Keep** padlock on, Discard backs out the whole call at once.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

import pythoncom
from pydantic import Field

from ..core import gate
from ..core.connection import get_doc, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from ..core.risk import Risk, risk_of

MAX_STEPS = 60
SELF = "autocad_sequence"
# The levels a sequence may run. Publish and Admin are deliberately absent:
# the sequence holds the Changes padlock, and that is all it may spend.
ALLOWED = (Risk.READ, Risk.VIEW, Risk.CHANGE)
# AutoCAD's UNDOCTL bit 8: a group is open. A step that nests its own undo mark
# inside another can leave one open, which quietly breaks the user's next
# Ctrl+Z, so any that are still open are closed at the end.
UNDO_GROUP_OPEN = 8
MAX_UNDO_CLOSES = 16


def _tool(name: str) -> Any:
    """The registered tool of that name, or None."""
    return mcp._tool_manager.get_tool(name)


def _tool_names() -> list[str]:
    return sorted(mcp._tool_manager._tools)


def plan_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check every step before any of them runs.

    Each step comes back with its tool, its level and its validated arguments.
    Raises AutocadError naming the step number for anything wrong: an unknown
    tool, a level the sequence may not spend, a sequence inside a sequence, or
    arguments that tool would reject.
    """
    if not steps:
        raise AutocadError("A sequence needs at least one step.")
    if len(steps) > MAX_STEPS:
        raise AutocadError(
            f"{len(steps)} steps is more than a sequence takes ({MAX_STEPS}). Split it, or use "
            "autocad_batch_draw for bulk geometry."
        )

    planned = []
    for index, step in enumerate(steps):
        where = f"Step {index + 1}"
        if not isinstance(step, dict):
            raise AutocadError(f"{where} is {step!r}; every step must be an object with a 'tool'.")
        name = str(step.get("tool", "")).strip()
        if not name:
            raise AutocadError(f"{where} has no 'tool'. Give the tool name, e.g. 'autocad_draw_line'.")
        if not name.startswith("autocad_"):
            name = f"autocad_{name}"
        if name == "autocad_saved_command":
            raise AutocadError(
                f"{where} runs a saved command. A sequence cannot contain one; run the saved "
                "command on its own, or put its steps in this list."
            )
        if name == SELF:
            raise AutocadError(
                f"{where} is {SELF} itself. A sequence cannot contain a sequence; put its steps "
                "in this list instead."
            )
        tool = _tool(name)
        if tool is None:
            close = [n for n in _tool_names() if name.removeprefix("autocad_") in n]
            raise AutocadError(
                f"{where}: there is no tool called '{name}'."
                + (f" Did you mean: {', '.join(close[:5])}?" if close else "")
            )
        try:
            level = risk_of(name)
        except KeyError:  # pragma: no cover - check_structure.py forbids this
            raise AutocadError(f"{where}: '{name}' has no level, so a sequence will not run it.") from None
        if level not in ALLOWED:
            article = "an" if level.value[0] in "aeiou" else "a"
            raise AutocadError(
                f"{where}: '{name}' is {article} {level.value} tool, which a sequence may not run — a "
                f"sequence holds the Changes padlock only. Call '{name}' on its own, so the "
                f"{level.value.title()} padlock is asked for properly."
            )

        args = step.get("args") or step.get("arguments") or {}
        if not isinstance(args, dict):
            raise AutocadError(f"{where} ('{name}'): 'args' must be an object, got {args!r}.")
        try:
            tool.fn_metadata.arg_model.model_validate(args)
        except Exception as exc:  # noqa: BLE001 - pydantic's own message is the useful part
            raise AutocadError(
                f"{where} ('{name}') would be rejected: {exc}. Nothing was run."
            ) from exc

        planned.append(
            {
                "index": index + 1,
                "tool": name,
                "level": level.value,
                "args": args,
                "label": str(step.get("label", "") or "").strip() or name.removeprefix("autocad_").replace("_", " "),
            }
        )
    return planned


async def _call(tool: Any, args: dict[str, Any]) -> str:
    """Run one step's tool body, without a second trip through the gate.

    The gate runs once, for the sequence. Going through it again from inside
    would wait on a lock this call already holds, so the tool's own body is
    called directly — which is safe only because plan_steps has already refused
    every level above Changes.

    The error handling ``tool_errors`` would have done is repeated here, so one
    bad step reads as a message rather than ending the sequence in a traceback.
    """
    body = getattr(tool.fn, "__wrapped__", tool.fn)
    try:
        return await body(**args)
    except AutocadError as exc:
        return f"Error: {exc}"
    except pythoncom.com_error as exc:
        return (
            f"Error: AutoCAD rejected the operation — {com_message(exc)}. Check that the "
            "drawing is not read-only, the target layer is not locked or frozen, and no "
            "command is waiting for input."
        )
    except (ValueError, TypeError) as exc:
        return f"Error: Invalid input — {exc}"
    except Exception as exc:  # noqa: BLE001 - last resort, still actionable
        return f"Error: Unexpected {type(exc).__name__} — {exc}"


@mcp.tool(name=SELF, **tool_meta("Run Several Tools In Order"))
@tool_errors
async def autocad_sequence(
    steps: Annotated[
        list[dict[str, Any]],
        Field(
            min_length=1,
            max_length=MAX_STEPS,
            description=(
                "The steps, in order. Each is an object:\n"
                '{"tool": "autocad_create_layout", "args": {"name": "E-101", '
                '"paper_size": "A1"}, "label": "make the sheet"}\n'
                "'tool' is any read, view or change tool — the save, export, "
                "command, AutoLISP and system-variable tools are refused, "
                "because a sequence holds the Changes padlock only. 'args' is "
                "that tool's own arguments. 'label' is optional and only makes "
                "the report easier to read."
            ),
        ),
    ],
    stop_on_error: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "Stop at the first step that fails, leaving the rest unrun. On by "
                "default: in a sheet set-up, a viewport is no use once the layout "
                "failed. Turn off for independent steps, such as tidying ten layers."
            ),
        ),
    ] = True,
    dry_run: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Check every step — the tool exists, its level is allowed, its "
                "arguments validate — and run none of them. Worth doing once for a "
                "long sequence you are about to run on a live drawing."
            ),
        ),
    ] = False,
) -> str:
    """Run several AutoCAD tools in one call, in order, checked before any of them starts.

    This is AutoLISP's ``progn``: the steps that only make sense together, sent
    together. A whole sheet in one call — layout, page setup, title block,
    viewport — or a whole import clean-up — remap the layers, tidy the
    overrides, flatten, check the standard.

    Every step's arguments are validated against that tool's own schema first,
    so a sequence with a mistake in step four changes nothing at all. Each step
    that runs keeps its own undo step; with the Ask to Keep padlock on, Discard
    backs out the whole call.

    It cannot do more than the Changes padlock already allows: steps at the
    Publish or Admin level, and a sequence inside a sequence, are refused
    before anything runs.

    Args:
        steps (list[dict]): the steps; see the field description.
        stop_on_error (bool): stop at the first failure (default true).
        dry_run (bool): check everything, run nothing.

    Returns:
        str: JSON: {
          "ran": int, "failed": int, "skipped": int, "dry_run": bool,
          "steps": [{"index", "tool", "label", "level", "ok",
                     "result": {...} | str, "skipped": bool}]
        }
        Each step's "result" is that tool's own answer, so handles from one
        step can be read out and used in the next call.

    Examples:
        - Use when: "set up sheet E-101 on A1 with our title block and the
          ground floor at 1:100" — four steps, one call.
        - Use when: "make this IFC a shop drawing" — remap the layers, tidy the
          overrides, flatten to zero, then check the standard.
        - Use when: the drawing must not be left half-changed if an argument is
          wrong.
        - Don't use when: you are drawing hundreds of entities
          (autocad_batch_draw is far faster), or you need a save, an export, a
          command or AutoLISP — those are refused here by design.

    Error Handling:
        - An unknown tool, a Publish or Admin step, a nested sequence, or
          arguments a tool would reject: all are reported with the step number
          before anything runs.
        - A step that fails while running is reported with its own error text;
          the steps after it are marked skipped unless stop_on_error=false.
    """
    planned = plan_steps(steps)

    if dry_run:
        return dumps(
            {
                "dry_run": True,
                "ran": 0,
                "failed": 0,
                "skipped": len(planned),
                "steps": [
                    {**{k: v for k, v in step.items() if k != "args"}, "ok": None, "skipped": True}
                    for step in planned
                ],
                "hint": "Every step checks out. Call again with dry_run=false to run them.",
            }
        )

    rows: list[dict[str, Any]] = []
    ran = failed = 0
    stopped = halted = False
    for step in planned:
        if not stopped and rows and await asyncio.to_thread(gate.stopped_by_modeller):
            # The modeller pressed HERONSTOP (D-51): not one more step.
            stopped = halted = True
        if stopped:
            rows.append({**_head(step), "ok": None, "skipped": True})
            continue
        text = await _call(_tool(step["tool"]), step["args"])
        ok = not str(text).startswith("Error:")
        rows.append({**_head(step), "ok": ok, "skipped": False, "result": _payload(text)})
        if ok:
            ran += 1
        else:
            failed += 1
            if stop_on_error:
                stopped = True

    await _close_undo_groups()

    result: dict[str, Any] = {
        "dry_run": False,
        "ran": ran,
        "failed": failed,
        "skipped": sum(1 for r in rows if r.get("skipped")),
        "steps": rows,
    }
    if halted:
        done = sum(1 for row in rows if row.get("ok") is not None)
        result["hint"] = (
            f"The modeller stopped Heron in AutoCAD (HERONSTOP) after step {done}. The steps before "
            "it are in the drawing; the rest were not run. Do nothing more until the modeller says so."
        )
    elif failed and stop_on_error and result["skipped"]:
        stopped_at = next(row["index"] for row in rows if row.get("ok") is False)
        result["hint"] = (
            f"Stopped at step {stopped_at}. The steps before it are in the drawing; the ones "
            "after were not run. Fix that step and run the rest."
        )
    return dumps(result)


def _head(step: dict[str, Any]) -> dict[str, Any]:
    return {"index": step["index"], "tool": step["tool"], "label": step["label"], "level": step["level"]}


def _payload(text: str) -> Any:
    """A step's answer as data when it is JSON, as text when it is a message."""
    try:
        return json.loads(text)
    except ValueError:
        return text


async def _close_undo_groups() -> None:
    """Close any undo group a step left open, so the user's next Ctrl+Z behaves.

    Steps nest their own undo marks inside one another; one EndUndoMark can
    leave an outer group open. autocad_batch_draw does the same thing in
    AutoLISP for the same reason.
    """

    def close() -> None:
        doc = get_doc()
        for _ in range(MAX_UNDO_CLOSES):
            try:
                if not int(doc.GetVariable("UNDOCTL")) & UNDO_GROUP_OPEN:
                    return
                doc.EndUndoMark()
            except BaseException:  # noqa: BLE001 - tidying up, never the headline
                return

    try:
        await run(close)
    except AutocadError:  # pragma: no cover - the sequence's own result matters more
        pass
