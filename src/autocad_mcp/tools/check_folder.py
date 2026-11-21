"""Run a check list over every drawing in a folder, read only, saving none (D-70).

Each drawing is opened read only, checked with the same list and project
changes as autocad_checklist, and closed without saving; a drawing that was
already open is checked where it is and left open. The drawing the modeller
was in is made active again at the end. Nothing is written to any drawing,
so it needs no Changes padlock; it opens and closes drawings, so it is a View
tool, like autocad_open_drawing.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from ..acad import checklist, folder_check
from ..core import gate
from ..core.connection import get_app, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from . import checklists


def _full_name(doc: Any) -> str:
    try:
        return str(doc.FullName or "")
    except BaseException:  # noqa: BLE001 - a drawing that cannot say is not the one we want
        return ""


def _open_read_only(path: Path) -> tuple[Any, bool]:
    """(the drawing, whether this call opened it). An open drawing is used where it is.

    "Opened it" is decided by what AutoCAD has open before and after, never by
    the path alone: the same file can be named two ways (a mapped drive and its
    UNC path), and a drawing the modeller had open must never be closed unsaved.
    """
    app = get_app()
    documents = app.Documents
    wanted = os.path.normcase(os.path.abspath(str(path)))
    before: list[str] = []
    for index in range(int(documents.Count)):
        doc = documents.Item(index)
        name = _full_name(doc)
        before.append(os.path.normcase(os.path.abspath(name)) if name else "")
        if name and before[-1] == wanted:
            doc.Activate()
            return doc, False
    count = int(documents.Count)
    doc = documents.Open(str(path), True)  # True: read only
    returned = os.path.normcase(os.path.abspath(_full_name(doc))) if _full_name(doc) else ""
    # AutoCAD handed back a drawing it already had open: the modeller's, never closed by Heron.
    ours = int(documents.Count) > count and returned not in before
    return doc, ours


def _close(doc: Any) -> None:
    doc.Close(False)  # never saved


def _active() -> Any:
    app = get_app()
    return app.ActiveDocument if int(app.Documents.Count) else None


def _back_to(doc: Any) -> None:
    if doc is not None:
        doc.Activate()


@mcp.tool(name="autocad_check_folder", **tool_meta("Check A Folder Of Drawings", read_only=True))
@tool_errors
async def autocad_check_folder(
    folder: Annotated[str, Field(min_length=1, description="The folder of drawings, e.g. 'D:\\Projects\\Tower\\MEP\\Issue 03'.")],
    name: Annotated[str, Field(description="The check list to run on each, e.g. 'before issue'.")] = checklist.STARTER["name"],
    subfolders: Annotated[bool, Field(description="Also check drawings in the folders inside it.")] = False,
    max_drawings: Annotated[int, Field(ge=1, le=folder_check.MOST_DRAWINGS, description="Check at most this many drawings, in name order.")] = 50,
    max_entities: Annotated[int, Field(ge=1, le=200000, description="Per drawing: stop reading objects after this many.")] = 20000,
) -> str:
    """Run a check list over every drawing in a folder: each opened read only, checked, closed unsaved.

    The same check list as autocad_checklist, with each drawing's own project
    changes, one drawing at a time. Each is opened read only and closed
    without saving; one that was already open is checked where it is and left
    open. The drawing the modeller was in is active again at the end. Each
    drawing gets its verdict and coverage line, worst first; one that cannot
    be opened is NOT RUN with the reason. PASS means the checked value is met
    for what Heron read, never that a drawing complies.

    Returns:
        str: JSON: {"folder", "checklist", "verdicts" {state: n}, "worst",
        "drawings": [{drawing, verdict, coverage, failed, no_data, reason}],
        "left_out", "pass_means"}

    Examples:
        - Use when: "check every drawing in the issue folder before we send it".
        - Use when: "which sheets in this folder still have things on layer 0?"
        - Don't use when: only the open drawing - autocad_checklist is faster.

    Error Handling:
        - A folder that is not there, or holds no .dwg: said, nothing opened.
        - A drawing that will not open (newer version, damaged, a box AutoCAD
          showed): NOT RUN with AutoCAD's reason; the rest go on.
        - The modeller's emergency stop (HERONSTOP): the rest are left out.
    """
    where = Path(folder.strip().strip('"'))
    if not where.is_absolute() or not where.is_dir():
        raise AutocadError(f"'{folder}' is not a folder on this PC. Give its full path, e.g. D:\\Projects\\Issue 03.")
    paths, left_out = folder_check.drawings_in(where, subfolders, max_drawings)
    if not paths:
        raise AutocadError(f"There is no .dwg drawing in {where}" + ("" if subfolders else " (subfolders=true looks inside its folders)") + ". Nothing was opened.")
    checklists.load(name)  # an unknown list is said before any drawing is opened

    original = await run(_active)
    lines: list[dict[str, Any]] = []
    stopped = False
    try:
        for path in paths:
            if lines and await asyncio.to_thread(gate.stopped_by_modeller):
                stopped = True
                break
            label = os.path.relpath(path, where)
            try:
                doc, ours = await run(lambda path=path: _open_read_only(path))
            except AutocadError as exc:
                lines.append({"drawing": label, "verdict": checklist.NOT_RUN, "coverage": "", "reason": str(exc)})
                continue
            except Exception as exc:  # noqa: BLE001 - COM said no: that drawing is NOT RUN
                lines.append({"drawing": label, "verdict": checklist.NOT_RUN, "coverage": "",
                              "reason": f"AutoCAD would not open it read only: {com_message(exc)}"})  # fmt: skip
                continue
            try:
                report, _ = await checklists.run_list(name, max_entities, doc_of=lambda doc=doc: doc)
                lines.append(folder_check.short(report, label))
            except Exception as exc:  # noqa: BLE001 - one drawing, not the folder
                lines.append({"drawing": label, "verdict": checklist.NOT_RUN, "coverage": "", "reason": str(exc)})
            finally:
                if ours:
                    try:
                        await run(lambda doc=doc: _close(doc))
                    except Exception:  # noqa: BLE001 - it was read only; say so, go on
                        lines[-1]["note"] = "Heron could not close it; it is still open, read only, unsaved."
    finally:
        try:
            await run(lambda: _back_to(original))
        except Exception:  # noqa: BLE001 - the wrong-drawing guard catches a different active drawing
            pass

    answer = {"folder": str(where), "checklist": name, **folder_check.summary(lines), "pass_means": checklist.PASS_MEANS}
    if left_out:
        answer["left_out"] = f"{left_out} more drawing(s) were not checked; raise max_drawings (up to {folder_check.MOST_DRAWINGS})."
    if stopped:
        answer["hint"] = "The modeller stopped Heron (HERONSTOP); the drawings after the last one listed were not checked."
    return dumps(answer)
