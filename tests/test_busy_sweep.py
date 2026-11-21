"""No ``except`` takes a busy AutoCAD for a failure, a missing name or a default (D-100, #36).

When AutoCAD is busy it turns a COM call away (RPC_E_CALL_REJECTED, "Call was
rejected by callee"). The worker's message filter asks again for up to 3 s per
job (D-57). Past that, the refusal must reach connection._with_retry as it is:
there it is asked again while nothing has been written, or becomes "Outcome
unknown" once a write has begun. An ``except`` that wraps it in a plain
AutocadError reports a false failure; one that takes it for "not there" or
"use the default" quietly carries on with a wrong answer.

So this test reads the source. Every ``except`` that can catch a COM error
(bare, ``BaseException``, ``Exception``, ``com_error``) in the code that talks
to AutoCAD must do one of these:

- call ``raise_if_busy(exc)`` (core/errors.py) before its fallback or its wrap;
- check ``is_busy`` / ``is_retryable`` itself;
- raise the error again as it is (a bare ``raise``);
- or be listed in ALLOWED below, with the reason it must not raise.

An ``except`` directly in an ``async def`` is not swept: COM is called on the
worker thread only, so code there reaches AutoCAD through ``await run(...)``,
and _with_retry has already turned a busy refusal into its own answer.

**A new ``except`` that fails this test:** add ``raise_if_busy(exc)`` as its first
line (or just before its ``raise AutocadError``, after any clean-up). Only when
raising would be wrong, add its function to ALLOWED with the reason, and count
how many such ``except`` blocks that function has.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "autocad_mcp"

# The code that talks to AutoCAD over COM: every module in acad/ and tools/,
# and the three core modules that make COM calls themselves.
SWEPT_FOLDERS = ("acad", "tools")
SWEPT_CORE = ("core/connection.py", "core/gate.py", "core/registry.py")

# Exception names that catch a pythoncom.com_error.
CATCHES_COM = {"BaseException", "Exception", "com_error"}
# Calls that count as the busy check.
BUSY_CHECKS = {"raise_if_busy", "is_busy", "is_retryable"}

# (file under src/autocad_mcp, function) -> (how many except blocks may skip the
# busy check there, why raising would be wrong). Keep the reason in plain words.
ALLOWED: dict[tuple[str, str], tuple[int, str]] = {
    # --- the shared helpers and the core ---
    ("acad/selection.py", "discard_selection_set"): (
        1, "empties the scratch selection set in a finally after a read; a refusal there must not hide the read's own answer"),
    ("acad/dxf_file.py", "effective_name"): (
        1, "reads a DXF file with ezdxf, with AutoCAD closed; no AutoCAD call"),
    ("acad/dxf_file.py", "block_rows"): (
        1, "reads a DXF file with ezdxf, with AutoCAD closed; no AutoCAD call"),
    ("tools/_solid_pieces.py", "_try_delete"): (
        1, "takes scaffolding or a half-made shape out again, on the way to the real answer; a refusal there must not replace it"),
    ("tools/checklist_share.py", "who"): (
        1, "asks Windows for the user name; no AutoCAD call"),
    ("tools/_shared.py", "created_payload"): (
        1, "reads the new object back once it is made; a failed read-back is already said with 'verified: false', and an error would make the chat draw it again"),
    ("tools/_shared.py", "plugin_read"): (
        1, "a read the plug-in does, not COM; the tool's work is done and its failure is said, not raised"),
    ("tools/_shared.py", "plugin_created"): (
        1, "the plug-in has already made it; a failed read-back is said with 'do not make it again', never raised"),
    ("core/connection.py", "_ComWorker._loop"): (
        1, "hands every error to the caller, which raises it there as it is"),
    ("core/connection.py", "_AppCache._dispatch"): (
        1, "starting AutoCAD: asking the whole call again could start a second AutoCAD"),
    ("core/connection.py", "_app_of_process"): (
        2, "walks every program's entries in Windows' list; one busy program, or a drawing closing, must not stop the search for the right AutoCAD"),
    ("tools/sheets.py", "_made_but_busy"): (
        2, "it is the answer to a busy AutoCAD after a sheet is added (#40): it looks for the sheet again while AutoCAD is busy, then says what it found"),
    ("tools/sheet_set.py", "autocad_sheet_set.work"): (
        1, "a sheet refused or busy part-way stops the set and is reported with the sheets made (one undo step); raising it would lose that list"),
    ("tools/sheet_set.py", "autocad_sheet_set._make_one"): (
        1, "the sheet's layout is made: it is listed as unfinished and the run stops, so a retry is never told its name is taken"),
    ("core/gate.py", "_command_of"): (
        1, "asks the plug-in's pipe, not COM; the busy answer stands without it"),
    ("core/registry.py", "undo_mark.__enter__"): (
        1, "the undo group is a nicety and the write is already marked as begun; a refusal would read as 'Outcome unknown' before anything was drawn"),
    ("core/registry.py", "undo_mark.__exit__"): (
        1, "closes the undo group on the way out; a refusal there must not hide the tool's own answer or its error"),
    # --- the tools ---
    ("tools/advanced.py", "_set_patiently"): (
        1, "deliberately asks again while AutoCAD is busy, to put a variable back (D-58)"),
    ("tools/advanced.py", "_get_patiently"): (
        1, "deliberately asks again while AutoCAD is busy, to read a variable after the expression ran (D-58)"),
    ("tools/advanced.py", "_wait_for_result"): (
        1, "deliberately keeps reading while AutoCAD is busy redrawing, up to its bound (D-58)"),
    ("tools/advanced.py", "autocad_send_command.work"): (
        2, "FILEDIA and ATTDIA: raising part-way through turning them off would leave FILEDIA at 0 with nothing to put it back, and the finally that puts them back must not be cut short"),
    ("tools/advanced.py", "autocad_run_lisp.work"): (
        3, "USERS1 already holds the marker, so running the call again would save the marker in place of his own value; a refused send already gives its own 'Outcome unknown' that says which pieces ran"),
    ("tools/annotate.py", "autocad_add_table.work"): (
        1, "turns table redraw back on after the table is filled; the table is made, so a refusal there must not turn the answer into a failure"),
    ("tools/check_folder.py", "_full_name"): (
        1, "a drawing that will not give its name is never taken for the modeller's; raising just after Heron opened a copy would leave that copy open"),
    ("tools/dimensions.py", "_handle_of"): (
        1, "reads the handle only to word a failure message; a refusal there must not hide the real reason"),
    ("tools/dimensions.py", "autocad_dimension_run.work"): (
        1, "deletes a wrongly styled dimension while already reporting a failure; a refusal there must not hide the real error"),
    ("tools/document.py", "_restore_plot_state"): (
        1, "puts the page setup, BACKGROUNDPLOT and the plot error mode back; a refusal there must not hide the plot's own answer or skip the other restores"),
    ("tools/document.py", "_plot_png"): (
        1, "only a tip about text size, after the picture is made; a refusal there must not throw the picture away"),
    ("tools/document.py", "autocad_export.work"): (
        1, "deletes the temporary selection set in a finally; a refusal there must not hide the export's own result"),
    ("tools/edit2d.py", "autocad_draw_order.work"): (
        1, "redraws the screen after the draw order is written; a refusal there must not hide that the change was made"),
    ("tools/lighting.py", "autocad_switch_lights.work"): (
        1, "only redraws the screen after the switch is done; a refusal there must not turn a finished switch into a failure"),
    ("tools/modify.py", "autocad_modify_entity.work"): (
        1, "locks again the layers it unlocked, after the work; a refusal there must not hide the answer"),
    ("tools/patterns.py", "autocad_create_linetype.work"): (
        1, "the .lin file is written just before the load, so the run asked again would find its own file and refuse it; the message already says AutoCAD was busy"),
    ("tools/sequence.py", "plan_steps"): (
        1, "checks a step's arguments with pydantic; no AutoCAD call"),
    ("tools/sequence.py", "_close_undo_groups.close"): (
        1, "closes undo groups a step left open, after the run; tidying up must not hide the sequence's own answer"),
    ("tools/settings.py", "_make_dim_style"): (
        1, "puts the drawing's DIM variables back in a finally; a refusal there must not hide the answer or skip putting the rest back"),
    ("tools/sheets.py", "_write_delete"): (
        1, "deletes a half-made layout after its set-up failed, just before the real error is raised again; a refusal must not replace that error"),
    ("tools/tables.py", "fill_table"): (
        1, "turns table redraw back on after the table is filled; the table is made, so a refusal there must not turn the answer into a failure"),
    ("tools/views.py", "_save_screen"): (
        1, "presses Esc to cancel a VIEW command that did not finish, on the way to raising the real error"),
    ("tools/views.py", "autocad_add_camera_view.work"): (
        1, "the plug-in has already made the view; a failed read-back says 'do not make it again', as plugin_created does"),
}


def swept_files() -> list[Path]:
    files = [path for folder in SWEPT_FOLDERS for path in sorted((PACKAGE / folder).glob("*.py"))]
    return files + [PACKAGE / name for name in SWEPT_CORE]


def _caught(node: ast.expr | None) -> set[str]:
    if node is None:
        return {"<bare>"}
    if isinstance(node, ast.Tuple):
        return set().union(*(_caught(item) for item in node.elts))
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Name):
        return {node.id}
    return set()


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _checks_busy(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Call) and _call_name(node) in BUSY_CHECKS:
            return True
    for statement in handler.body:
        if isinstance(statement, ast.Raise):
            if statement.exc is None:
                return True  # a bare raise: the error goes up as it is
            if isinstance(statement.exc, ast.Name) and statement.exc.id == handler.name:
                return True
    return False


def unchecked(path: Path) -> list[tuple[str, int]]:
    """(function, line) of each except in this file that can swallow a busy refusal."""
    found: list[tuple[str, int]] = []

    def visit(node: ast.AST, scope: tuple[str, ...], in_async: bool) -> None:
        for child in ast.iter_child_nodes(node):
            inner, inner_async = scope, in_async
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = (*scope, child.name)
                inner_async = isinstance(child, ast.AsyncFunctionDef) or (
                    in_async and isinstance(child, ast.ClassDef)
                )
            if isinstance(child, ast.ExceptHandler) and not in_async:
                caught = _caught(child.type)
                if caught & (CATCHES_COM | {"<bare>"}) and not _checks_busy(child):
                    found.append((".".join(scope) or "<module>", child.lineno))
            visit(child, inner, inner_async)

    visit(ast.parse(path.read_text(encoding="utf-8")), (), False)
    return found


def test_every_except_that_can_swallow_a_busy_refusal_checks_for_it():
    problems: list[str] = []
    for path in swept_files():
        relative = path.relative_to(PACKAGE).as_posix()
        per_function = Counter()
        lines: dict[str, list[int]] = {}
        for function, line in unchecked(path):
            per_function[function] += 1
            lines.setdefault(function, []).append(line)
        for function, count in per_function.items():
            allowed = ALLOWED.get((relative, function), (0, ""))[0]
            if count > allowed:
                where = ", ".join(f"{relative}:{line}" for line in lines[function])
                problems.append(
                    f"{relative} {function}: {count} except block(s) can swallow a busy "
                    f"refusal, {allowed} allowed ({where})"
                )
    assert not problems, (
        "These except blocks can take a busy AutoCAD for a failure or for 'not there'. "
        "Add raise_if_busy(exc) (core/errors.py) before the fallback or the wrap, or list "
        "the function in ALLOWED in tests/test_busy_sweep.py with the reason:\n"
        + "\n".join(problems)
    )


def test_every_allowed_entry_has_a_reason():
    for key, (count, reason) in ALLOWED.items():
        assert count > 0 and reason.strip(), key


@pytest.mark.parametrize("name", SWEPT_CORE)
def test_the_core_files_swept_are_still_there(name):
    assert (PACKAGE / name).is_file(), f"{name} moved: update SWEPT_CORE"
