"""Escape hatches: raw AutoCAD commands, AutoLISP evaluation, housekeeping.

The typed tools cover the common drafting operations. These cover everything
else — AutoCAD has hundreds of commands and a full LISP interpreter, and an
agent that can reach them is not limited to what this server anticipated.

The hazard is dialogs. A command that opens a modal dialog blocks AutoCAD's
COM interface until a human dismisses it, which hangs every later tool call.
Most such commands have a command-line form prefixed with a hyphen, and the
guards here steer callers to it.
"""

from __future__ import annotations

import re
import time
from typing import Annotated, Any

from pydantic import Field

from ..core import gate
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark

# Commands whose plain form opens a modal dialog. Each maps to the advice that
# gets the caller to a form that will not block AutoCAD.
DIALOG_COMMANDS = {
    "PURGE": "use '-PURGE', or the autocad_purge tool",
    "LAYER": "use '-LAYER', or the autocad_* layer tools",
    "INSERT": "use '-INSERT', or autocad_insert_block",
    "PLOT": "use '-PLOT', or autocad_export for PDF",
    "HATCH": "use '-HATCH', or autocad_add_hatch",
    "BHATCH": "use '-HATCH', or autocad_add_hatch",
    "STYLE": "use '-STYLE'",
    "DIMSTYLE": "use '-DIMSTYLE'",
    "LINETYPE": "use '-LINETYPE'",
    "BLOCK": "use '-BLOCK'",
    "WBLOCK": "use '-WBLOCK'",
    "ATTDEF": "use '-ATTDEF'",
    "ATTEDIT": "use '-ATTEDIT'",
    "TOOLBAR": "use '-TOOLBAR'",
    "VIEW": "use '-VIEW'",
    "UNITS": "use '-UNITS', or set INSUNITS with autocad_set_variable",
    "OPTIONS": "change the setting with autocad_set_variable instead",
    "SAVEAS": "use autocad_save_drawing",
    "OPEN": "use autocad_open_drawing",
    "NEW": "use autocad_create_drawing",
    "QUIT": "closing AutoCAD would end this session",
    "EXIT": "closing AutoCAD would end this session",
    "CLOSE": "closing the drawing may prompt to save and block AutoCAD",
}

# Commands that write the drawing or a file from it. The typed tools for these
# (autocad_save_drawing, autocad_export, autocad_publish_pdf) need the Publish
# padlock; a raw command or LISP must not get round it with Admin alone. The
# plug-in vetoes the same list inside a job (PublishGuard.cs, D-47): this is the
# first line, that is the net under it. tests/test_publish_guard.py keeps the
# two lists the same.
PUBLISH_COMMANDS = frozenset(
    {
        "SAVE", "QSAVE", "SAVEAS", "SAVEALL", "SAVETOWEBMOBILE",
        "PLOT", "PUBLISH", "BATCHPLOT", "EXPORT", "EXPORTPDF", "EXPORTDWF", "EXPORTDWFX",
        "EXPORTLAYOUT", "EXPORTTOAUTOCAD", "ETRANSMIT", "ARCHIVE", "WBLOCK",
        "DXFOUT", "STLOUT", "ACISOUT", "PDFOUT", "JPGOUT", "PNGOUT", "BMPOUT", "TIFOUT", "WMFOUT",
        "3DDWF", "3DPRINT", "SENDTO3DPRINTSERVICE", "IGESEXPORT", "STEPEXPORT",
    }
)  # fmt: skip
# ActiveX calls from LISP that save or plot without any command running.
_LISP_PUBLISH_CALLS = re.compile(
    r"\bvla-(save|saveas|wblock|export|plottofile|plottodevice)\b", re.IGNORECASE
)
_LISP_STRINGS = re.compile(r'"((?:[^"\\]|\\.)*)"')
PUBLISH_REFUSED = (
    "{what} saves, plots or exports, and that needs the Publish padlock, which a raw "
    "command or AutoLISP does not ask for. Use autocad_save_drawing, autocad_export or "
    "autocad_publish_pdf instead. Nothing was sent to AutoCAD."
)


def _plain(word: str) -> str:
    return word.strip().lstrip("#_.-+'").upper()


def publish_command_in(text: str) -> str | None:
    """The first save, plot or export command in a command string, or None."""
    for word in text.split():
        if _plain(word) in PUBLISH_COMMANDS:
            return _plain(word)
    return None


def publish_call_in_lisp(expression: str) -> str | None:
    """A save, plot or export a LISP expression would do: a vla- call, or a command name as a string.

    In LISP a command is a string of its own - (command "_.QSAVE") - so only a
    string that is nothing but the command counts: "save the date" does not.
    """
    found = _LISP_PUBLISH_CALLS.search(expression)
    if found:
        return found.group(0)
    for literal in _LISP_STRINGS.findall(expression):
        if _plain(literal) in PUBLISH_COMMANDS:
            return _plain(literal)
    return None


# Commands that operate on the undo stack itself. Everything else sent through
# autocad_send_command is wrapped in an undo mark so one tool call is one
# Ctrl+Z — but running UNDO inside an open undo group does not roll back
# reliably, and leaves AutoCAD in a state where the next call fails. These are
# sent unwrapped.
UNDO_STACK_COMMANDS = {"UNDO", "U", "REDO", "MREDO", "OOPS"}

# System variables used to smuggle a LISP result back across the COM boundary.
# USERS1-5 are string variables AutoCAD reserves for exactly this purpose.
LISP_RESULT_VAR = "USERS1"
# The command an expression left open, cancelled before the result is written.
LISP_CANCELLED_VAR = "USERS2"
LISP_SENTINEL = "\x01MCP-PENDING\x01"
# CMDACTIVE bits 1 and 2: an ordinary or a transparent command waiting at a
# prompt. Bit 32 (AutoLISP running) is set while the wrapper itself runs, so it
# must not count, or the cancel loop would never see a free AutoCAD.
LISP_OPEN_COMMAND_BITS = 3
# Tries to cancel a command left open: each (command) with no arguments is one
# Esc; a nested transparent command needs two. Bounded so it can never spin.
LISP_CANCEL_TRIES = 4


def lisp_wrapper(expression: str) -> str:
    """The text sent to AutoCAD for autocad_run_lisp.

    The expression is evaluated and its value kept. A command it left waiting
    at a prompt (DVIEW, CAMERA, a ``(command ...)`` short of its last answer)
    is then cancelled and its name kept, and only after that are the value and
    the name written. Before this, the left-open command swallowed the result
    write and every later call waited on AutoCAD (bedroom model, 2026-11-05).
    ``(princ)`` last, so nothing is echoed into a prompt.
    """
    is_open = f'(> (logand (getvar "CMDACTIVE") {LISP_OPEN_COMMAND_BITS}) 0)'
    return (
        "(vl-load-com)"
        f"(setq heron:r (vl-princ-to-string {expression})"
        f' heron:c (if {is_open} (getvar "CMDNAMES") ""))'
        f"(repeat {LISP_CANCEL_TRIES} (if {is_open} (command)))"
        f'(setvar "{LISP_CANCELLED_VAR}" heron:c)'
        f'(setvar "{LISP_RESULT_VAR}" heron:r)'
        "(princ)\n"
    )
# Longest expression autocad_run_lisp accepts. The wrapper adds about 300
# characters, and AutoCAD's command line drops longer text: a ~3,000-character
# defun block arrived as nothing at all (Luxury Suite 2, 2026-11-09), while
# calls under 2,000 worked all day. Refused here, with a plain message, rather
# than failing silently in AutoCAD.
LISP_MAX_CHARS = 2000
# The wait for the result: at most LISP_POLL_ATTEMPTS reads and
# LISP_POLL_ATTEMPTS x LISP_POLL_DELAY seconds. A read AutoCAD refuses while it
# redraws does not end the wait: one refused read after a layer-off or a view
# restore reported "timed out" in half a second for an expression that had run
# (Luxury Suite 3, 2026-11-18).
LISP_POLL_ATTEMPTS = 100
LISP_POLL_DELAY = 0.1
# Tries to put USERS1, USERS2 and OSMODE back while AutoCAD is busy for a moment.
LISP_RESTORE_TRIES = 5


def _set_patiently(doc: Any, name: str, value: Any) -> bool:
    """Set a system variable, asking again a few times while AutoCAD is busy. False if it never took."""
    for attempt in range(LISP_RESTORE_TRIES):
        try:
            doc.SetVariable(name, value)
            return True
        except BaseException:  # noqa: BLE001 - busy for a moment: ask again
            if attempt + 1 < LISP_RESTORE_TRIES:
                time.sleep(LISP_POLL_DELAY)
    return False


def _get_patiently(doc: Any, name: str) -> str | None:
    """Read a system variable as text, asking again a few times while AutoCAD is busy. None if it never answered."""
    for attempt in range(LISP_RESTORE_TRIES):
        try:
            return str(doc.GetVariable(name))
        except BaseException:  # noqa: BLE001 - busy for a moment: ask again
            if attempt + 1 < LISP_RESTORE_TRIES:
                time.sleep(LISP_POLL_DELAY)
    return None


# One box a command or expression is expected to open, and the button to press
# on it (#101). Every other box is still cancelled by the dialog watch (D-66).
EXPECT_BOX = Field(description=(
    "The exact title of ONE box this is expected to open, e.g. 'Purge - Confirm Purge'. Heron "
    "presses 'press' on the first box with that title, once; every other box is still cancelled. "
    "Give both or neither. Avoid a title many boxes share, such as 'AutoCAD' or 'AutoCAD Message': "
    "the first box with it gets the button, whatever it asks."
))
PRESS = Field(description="The button to press on that box, as it reads, e.g. 'Yes' or 'OK'.")


def expectation(expect_box: str | None, press: str | None) -> tuple[str, str] | None:
    """(title, button), None for neither; refused when only one is given."""
    box, button = (expect_box or "").strip(), (press or "").strip()
    if not box and not button:
        return None
    if not box or not button:
        raise AutocadError(
            "Give both expect_box (the box's exact title) and press (the button), or neither. Nothing was sent."
        )
    return box, button


def expect(wanted: tuple[str, str] | None) -> None:
    """Before anything is sent: have the plug-in press that button on that box. Raises when it will not."""
    if wanted is None:
        return
    expecter = gate.dialog_expecter()
    if expecter is None:
        raise AutocadError(
            "Naming a button for a box needs Heron's plug-in, which is not in use for this call. "
            "Call without expect_box (the box would be cancelled). Nothing was sent."
        )
    refusal = expecter(*wanted)
    if refusal:
        raise AutocadError(refusal)


@mcp.tool(
    name="autocad_send_command",
    **tool_meta("Send AutoCAD Command", destructive=True),
)
@tool_errors
async def autocad_send_command(
    command: Annotated[
        str,
        Field(
            description=(
                "The command string, exactly as typed at AutoCAD's command "
                r"line. Use \n for Enter between arguments, e.g. "
                r"'_CIRCLE\n0,0\n50\n'. Prefix built-in commands with an "
                "underscore ('_LINE') so they work on non-English AutoCAD."
            ),
            min_length=1,
            max_length=4000,
        ),
    ],
    suppress_dialogs: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "Set FILEDIA and ATTDIA to 0 for the call, so commands that "
                "would pop a file or attribute dialog use the command line "
                "instead. Restored afterwards."
            ),
        ),
    ] = True,
    expect_box: Annotated[str | None, EXPECT_BOX] = None,
    press: Annotated[str | None, PRESS] = None,
) -> str:
    """Run any AutoCAD command by sending it to the command line.

    This is the escape hatch for anything the typed tools do not cover —
    TRIM, EXTEND, FILLET, JOIN, BOUNDARY, MEASUREGEOM, custom LISP commands,
    third-party add-in commands.

    The command runs as if the user typed it, so it needs every argument the
    interactive command would ask for, separated by \\n. A command left waiting
    for input will block every later tool call until someone presses Esc in
    AutoCAD.

    Prefer a typed tool when one exists: those validate their inputs, return
    the handles of what they made, and cannot leave AutoCAD mid-command.

    The command is wrapped in an undo mark so one call is one Ctrl+Z. UNDO,
    REDO, U, MREDO and OOPS are sent unwrapped, since running those inside an
    open undo group does not roll back reliably.

    Args:
        command (str): Command string with \\n between arguments.
        suppress_dialogs (bool): Force command-line prompts for the call.

    Returns:
        str: JSON: {"sent": str, "completed": bool, "command_active": bool,
             "note": str}
             "command_active" is true when AutoCAD is still waiting for input,
             which means the command string was incomplete.

    Examples:
        - Use when: "fillet those two lines with a 50 radius" ->
          '_FILLET\\n_R\\n50\\n' then select.
        - Use when: running a custom LISP command the office has loaded.
        - Use when: a command asks a question in a box and the modeller has
          said the answer - expect_box='Purge - Confirm Purge', press='Yes'.
        - Don't use when: a typed tool exists — autocad_draw_circle beats
          sending '_CIRCLE'.

    Error Handling:
        - Refuses commands known to open a modal dialog and names the
          command-line alternative, since a dialog would hang the connection.
        - expect_box without press (or the reverse), or a plug-in older than
          1.7.0, is refused before anything is sent.
    """
    text = command.strip()
    # Look at the first token only; arguments after it are data, not commands.
    first = text.split()[0].lstrip("_-.").upper() if text.split() else ""
    if first in DIALOG_COMMANDS and not text.lstrip().startswith(("-", "_-")):
        raise AutocadError(
            f"'{first}' opens a modal dialog, which would block AutoCAD's COM "
            "connection until someone closes it by hand. Instead, "
            f"{DIALOG_COMMANDS[first]}."
        )
    named = publish_command_in(text)
    if named:
        raise AutocadError(PUBLISH_REFUSED.format(what=named))

    payload = text if text.endswith("\n") else text + "\n"
    wanted = expectation(expect_box, press)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        expect(wanted)

        manages_undo = first in UNDO_STACK_COMMANDS

        # Writing a system variable lands on the undo stack. For UNDO and REDO
        # that means the suppression would be the thing undone, not the user's
        # edit — and those commands never open a file or attribute dialog, so
        # there is nothing to suppress for them anyway.
        saved: dict[str, Any] = {}
        if suppress_dialogs and not manages_undo:
            for var in ("FILEDIA", "ATTDIA"):
                try:
                    saved[var] = doc.GetVariable(var)
                    doc.SetVariable(var, 0)
                except BaseException:  # noqa: BLE001 - variable may not exist
                    pass

        try:
            if manages_undo:
                doc.SendCommand(payload)
            else:
                with undo_mark(doc):
                    doc.SendCommand(payload)
        finally:
            for var, value in saved.items():
                try:
                    doc.SetVariable(var, value)
                except BaseException:  # noqa: BLE001
                    pass

        try:
            still_active = int(doc.GetVariable("CMDACTIVE")) != 0
        except BaseException:  # noqa: BLE001
            still_active = False

        result = {
            "sent": text,
            "completed": not still_active,
            "command_active": still_active,
        }
        if still_active:
            result["note"] = (
                "AutoCAD is still waiting for input, so the command string was "
                "incomplete. Send the remaining arguments, or send '\\x1b' to "
                "cancel. Until it finishes, other tools will report AutoCAD as "
                "busy."
            )
        else:
            result["note"] = (
                "AutoCAD does not report command output over COM. Verify the "
                "result with autocad_list_entities or autocad_get_entity."
            )
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_run_lisp",
    **tool_meta("Evaluate AutoLISP", destructive=True),
)
@tool_errors
async def autocad_run_lisp(
    expression: Annotated[
        str,
        Field(
            description=(
                "One AutoLISP expression to evaluate, e.g. "
                "'(getvar \"DIMSCALE\")' or "
                "'(length (vlax-safearray->list (vla-get-coordinates obj)))'. "
                "Its value is returned as text. At most "
                f"{LISP_MAX_CHARS} characters: split longer code into several "
                "calls (define helpers with defun in one call, use them in the "
                "next)."
            ),
            min_length=1,
            max_length=LISP_MAX_CHARS,
        ),
    ],
    expect_box: Annotated[str | None, EXPECT_BOX] = None,
    press: Annotated[str | None, PRESS] = None,
) -> str:
    """Evaluate an AutoLISP expression and return its result.

    Unlike autocad_send_command, this gets a value back. AutoCAD's COM
    interface has no LISP eval, so the expression's result is stashed in the
    USERS1 system variable and read from there — which means the result comes
    back as text, and is capped at what that variable holds (a few hundred
    characters). Return an aggregate rather than a full list when the data is
    large.

    This reaches parts of the drawing database COM does not expose: extended
    entity data, dictionaries, xrecords, layer filters, custom object
    properties, and anything a loaded office LISP routine defines.

    Args:
        expression (str): A single AutoLISP expression.

    Returns:
        str: JSON: {"expression": str, "result": str, "timed_out": bool,
             "cancelled_command": str (only when one was left open), "note": str}
             "result" is the expression's value rendered as a string; "nil" is
             LISP's empty/false value, not an error.

    Running object snaps are off while the expression runs (and put back
    afterwards), so points typed into ``(command ...)`` land where given. A
    command the expression leaves waiting at a prompt is cancelled before the
    result is written, and named in "cancelled_command", so AutoCAD is never
    left stuck in it.

    Examples:
        - Use when: "what's the current dimension scale?" ->
          '(getvar "DIMSCALE")'.
        - Use when: "how many entities are on layer X?" ->
          '(sslength (ssget "_X" (list (cons 8 "X"))))'.
        - Don't use when: a typed tool covers it — those return structured
          data instead of a string.

    Error Handling:
        - Reports timed_out=true if AutoCAD never wrote a result, which usually
          means the expression raised a LISP error or is waiting for input.
        - Unbalanced parentheses are rejected before the expression is sent,
          since AutoCAD would otherwise sit waiting for the closing bracket.
        - An expression over LISP_MAX_CHARS (2,000) characters is refused:
          AutoCAD drops longer command-line text without a word.
        - expect_box without press (or the reverse), or a plug-in older than
          1.7.0, is refused before anything is sent. Every box but the one
          named is still cancelled (D-66).
    """
    text = expression.strip()
    if len(text) > LISP_MAX_CHARS:
        raise AutocadError(
            f"The expression is {len(text)} characters; AutoCAD drops command-line "
            f"text much past {LISP_MAX_CHARS} without a word. Split it into several "
            "calls: define helpers with defun in one call, then use them in the next."
        )
    if not text.startswith("("):
        raise AutocadError(
            f"An AutoLISP expression must start with '('. Got: {text[:60]}"
        )
    if text.count("(") != text.count(")"):
        raise AutocadError(
            f"Unbalanced parentheses: {text.count('(')} opening, "
            f"{text.count(')')} closing. AutoCAD would wait for the rest of the "
            "expression and block the connection."
        )
    if '"' in text and text.count('"') % 2:
        raise AutocadError(
            "Unbalanced double quotes in the expression. AutoCAD would wait for "
            "the closing quote and block the connection."
        )
    named = publish_call_in_lisp(text)
    if named:
        raise AutocadError(PUBLISH_REFUSED.format(what=named))
    wanted = expectation(expect_box, press)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        expect(wanted)

        previous: dict[str, str] = {}
        for var in (LISP_RESULT_VAR, LISP_CANCELLED_VAR):
            try:
                previous[var] = str(doc.GetVariable(var))
            except BaseException:  # noqa: BLE001
                previous[var] = ""

        doc.SetVariable(LISP_RESULT_VAR, LISP_SENTINEL)
        try:
            doc.SetVariable(LISP_CANCELLED_VAR, "")
        except BaseException:  # noqa: BLE001
            pass
        # Running object snaps catch the points an expression types into
        # (command ...) ("Too many objects selected for INTERSECT", 2026-11-05).
        # Off for the call, and put back through COM even if the LISP fails.
        not_put_back: list[str] = []
        osmode = None
        try:
            osmode = doc.GetVariable("OSMODE")
            doc.SetVariable("OSMODE", 0)
        except BaseException:  # noqa: BLE001
            osmode = None
        try:
            with undo_mark(doc):
                doc.SendCommand(lisp_wrapper(text))
        except BaseException as exc:  # noqa: BLE001
            raise AutocadError(
                f"AutoCAD refused the expression: {com_message(exc)}. Check the "
                "LISP syntax."
            ) from exc
        finally:
            if osmode is not None and not _set_patiently(doc, "OSMODE", osmode):
                not_put_back.append(f"OSMODE (it was {osmode})")

        # SendCommand usually blocks until the expression finishes, but polling
        # covers the versions where it does not. A refused read is AutoCAD busy
        # redrawing, not an answer: the wait goes on to its bound.
        value = LISP_SENTINEL
        answered = False
        deadline = time.monotonic() + LISP_POLL_ATTEMPTS * LISP_POLL_DELAY
        for _ in range(LISP_POLL_ATTEMPTS):
            try:
                value = str(doc.GetVariable(LISP_RESULT_VAR))
                answered = True
            except BaseException:  # noqa: BLE001 - busy for a moment: keep waiting
                pass
            if value != LISP_SENTINEL or time.monotonic() >= deadline:
                break
            time.sleep(LISP_POLL_DELAY)

        timed_out = value == LISP_SENTINEL
        cancelled = _get_patiently(doc, LISP_CANCELLED_VAR) or ""
        for var, old in previous.items():
            if not _set_patiently(doc, var, old):
                not_put_back.append(var)
        restore_note = (
            f" AutoCAD stayed too busy to put back {', '.join(not_put_back)}: "
            "check them with autocad_get_variable." if not_put_back else ""
        )

        if timed_out:
            if not answered:
                note = (
                    "AutoCAD stayed busy (redrawing, or a dialog open) for the "
                    "whole wait and never let Heron read the answer. The "
                    "expression was sent and has probably run: look at the "
                    "drawing before sending it again, or it may be done twice."
                )
            else:
                note = (
                    "AutoCAD never wrote a result within the wait. The "
                    "expression probably raised a LISP error, referenced an "
                    "undefined symbol, or is waiting for input. But a long "
                    "expression can still have run and finished after the wait: "
                    "count what landed before sending it again, or it is drawn "
                    "twice. Check AutoCAD's command line, and press Esc there if "
                    "a prompt is showing."
                )
            return {
                "expression": text,
                "result": None,
                "timed_out": True,
                "note": note + restore_note,
            }
        answer: dict[str, Any] = {"expression": text, "result": value, "timed_out": False}
        if cancelled:
            answer["cancelled_command"] = cancelled
            answer["note"] = (
                f"The expression left AutoCAD inside {cancelled}, waiting at a "
                "prompt; it was cancelled so the drawing is free again. Answer "
                "every prompt of a (command ...) call, including the last one, "
                "in the same expression."
            )
        if restore_note:
            answer["note"] = (answer.get("note", "") + restore_note).strip()
        return answer

    return dumps(await run(work))


# What to answer -PURGE's "Enter type of unused objects to purge" with. The
# leading underscore keeps the English option in any language of AutoCAD. Text
# styles are "textSTyles" on the prompt, so the answer is its capitals, ST.
PURGE_OPTIONS: dict[str, str] = {
    "all": "_All",
    "blocks": "_Blocks",
    "layers": "_LAyers",
    "linetypes": "_LTypes",
    "text_styles": "_ST",
    "dim_styles": "_DImstyles",
}


@mcp.tool(
    name="autocad_purge",
    **tool_meta("Purge Unused Items", destructive=True, idempotent=True),
)
@tool_errors
async def autocad_purge(
    target: Annotated[
        str,
        Field(
            default="all",
            description=(
                "What to purge: 'all', 'blocks', 'layers', 'linetypes', "
                "'text_styles', 'dim_styles'."
            ),
            pattern="^(all|blocks|layers|linetypes|text_styles|dim_styles)$",
        ),
    ] = "all",
) -> str:
    """Remove unused blocks, layers, linetypes and styles from the drawing.

    Purging only removes definitions nothing references, so it cannot delete
    visible geometry. It is the standard cleanup before issuing a drawing, and
    often shrinks the file substantially.

    Args:
        target (str): What to purge.

    Returns:
        str: JSON: {"purged": str, "layers_before": int, "layers_after": int,
             "blocks_before": int, "blocks_after": int}

    Examples:
        - Use when: "clean this drawing up before I send it".
    """
    keyword = PURGE_OPTIONS[target]

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        before = {"layers": int(doc.Layers.Count), "blocks": int(doc.Blocks.Count)}
        with undo_mark(doc):
            # -PURGE is the command-line form; _N answers "verify each?" with No.
            doc.SendCommand(f"_.-PURGE\n{keyword}\n*\n_N\n")
        return {
            "purged": target,
            "layers_before": before["layers"],
            "layers_after": int(doc.Layers.Count),
            "blocks_before": before["blocks"],
            "blocks_after": int(doc.Blocks.Count),
            "note": (
                "Purging is not always complete in one pass — nested "
                "definitions can need a second run."
            ),
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_regen",
    **tool_meta("Regenerate Drawing", idempotent=True),
)
@tool_errors
async def autocad_regen(
    scope: Annotated[
        str,
        Field(
            default="active",
            description="'active' regenerates the current viewport, 'all' does every one.",
            pattern="^(active|all)$",
        ),
    ] = "active",
) -> str:
    """Regenerate the drawing display.

    Worth calling after bulk edits, or when the screen no longer matches the
    data — new hatches, changed linetype scales and edited text sometimes need
    a regen to redraw correctly.

    Args:
        scope (str): "active" or "all".

    Returns:
        str: JSON: {"regenerated": str}

    Examples:
        - Use when: the screen looks wrong after a settings change - linetypes
          not showing their pattern, text the wrong size.
        - Use when: after autocad_drawing_setup changes LTSCALE.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        # acActiveViewport == 0, acAllViewports == 1
        doc.Regen(0 if scope == "active" else 1)
        return {"regenerated": scope}

    return dumps(await run(work))


@mcp.tool(
    name="autocad_audit",
    **tool_meta("Audit And Repair Drawing", idempotent=True),
)
@tool_errors
async def autocad_audit(
    fix_errors: Annotated[
        bool,
        Field(
            default=True,
            description="Repair the problems found, rather than only reporting them.",
        ),
    ] = True,
) -> str:
    """Check the drawing database for errors and optionally repair them.

    Run this when a drawing behaves oddly — entities that will not select,
    commands that fail without explanation, a file that crashes on open.

    Args:
        fix_errors (bool): Repair what the audit finds.

    Returns:
        str: JSON: {"audited": true, "fixed": bool, "note": str}

    Error Handling:
        - AUDIT writes its findings to AutoCAD's text window rather than
          returning them over COM, so the counts are not available here. Check
          the .adt log file beside the drawing for the detail.

    Examples:
        - Use when: a drawing came in from outside and behaves oddly, or
          AutoCAD has reported an error in it.
        - Use when: before handing a cleaned-up import on. It needs Admin,
          because repairing changes the database itself.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        doc.SendCommand(f"_.AUDIT\n{'_Y' if fix_errors else '_N'}\n")
        return {
            "audited": True,
            "fixed": fix_errors,
            "note": (
                "AutoCAD reports audit findings in its text window (press F2) "
                "and, when AUDITCTL is on, in an .adt log file beside the "
                "drawing. Those details are not available over COM."
            ),
        }

    return dumps(await run(work))
