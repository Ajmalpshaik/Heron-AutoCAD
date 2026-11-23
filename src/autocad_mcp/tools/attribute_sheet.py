"""Block attributes out to Excel and back: only the changed cells are written (D-69).

The idea is Heron AI for Revit's spreadsheet round trip (its D-182, D-183).
autocad_export_attribute_sheet writes a new workbook next to the drawing;
the modeller edits it in Excel; autocad_apply_attribute_sheet reads it back,
compares it with what the drawing has (acad/attribute_sheet.py, offline) and
writes only the cells that really changed, in one undo step, listing each one
old -> new. Writing a file needs the Publish padlock, so the export is a
Publish tool of its own; applying changes the drawing, so it is a Change tool.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from ..acad import attribute_sheet, xlsx
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import before_after
from .text_tools import _attribute_refs, plugin_write_attributes

MOST_NUMBER = 999
MOST_LISTED = 200


def _drawing_path(doc: Any) -> str:
    try:
        return str(doc.FullName or "")
    except BaseException as exc:  # noqa: BLE001 - an unsaved drawing may not say
        raise_if_busy(exc)
        return ""


def free_name(folder: Path, stem: str) -> Path:
    """The first '<stem>.xlsx', '<stem> (2).xlsx' ... that is not there yet."""
    for number in range(1, MOST_NUMBER + 1):
        path = folder / (f"{stem}.xlsx" if number == 1 else f"{stem} ({number}).xlsx")
        if not path.exists():
            return path
    raise AutocadError(f"There are already {MOST_NUMBER} sheets named {stem} in {folder}. Move some; nothing was written.")


def sheet_path(path: str, drawing: str) -> Path:
    """The workbook to read: as given, or beside the drawing when the name has no folder."""
    given = Path(path.strip().strip('"'))
    if not given.is_absolute():
        if not drawing or not os.path.isabs(drawing):
            raise AutocadError("Give the sheet's full path: this drawing is not saved, so it has no folder to look in.")
        given = Path(drawing).parent / given
    if given.suffix.lower() not in (".xlsx", ".csv"):
        raise AutocadError(f"'{given.name}' is not an .xlsx or .csv file. Save the sheet from Excel as .xlsx.")
    if not given.is_file():
        raise AutocadError(f"There is no file {given}. Check the name; nothing was changed.")
    return given


def read_sheet(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]] | None, str]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise AutocadError(
            f"{path.name} could not be read ({exc}). If it is open in Excel, save it and try again."
        ) from None
    try:
        if path.suffix.lower() == ".csv":
            if len(content) > xlsx.MOST_FILE_BYTES:
                raise ValueError("the file is bigger than 20 MB")
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = content.decode("cp1252", errors="replace")  # Excel's "CSV" on a Western PC
            return attribute_sheet.read_csv(text), None, ""
        edited, exported = attribute_sheet.read_workbook(content)
        return edited, exported, attribute_sheet.source_of(content)
    except (ValueError, xlsx.SheetError) as exc:
        raise AutocadError(f"{path.name} cannot be used: {exc}. Nothing was changed.") from None


@mcp.tool(name="autocad_export_attribute_sheet", **tool_meta("Export Attributes To Excel"))
@tool_errors
async def autocad_export_attribute_sheet(
    block_name: Annotated[str | None, Field(description="Only this block (real name), e.g. 'CAMERA'. Default: every block with attributes.")] = None,
    layer: Annotated[str | None, Field(description="Only blocks on this layer.")] = None,
) -> str:
    """Write every block's attributes to a new Excel workbook next to the drawing, to edit and bring back.

    One row per block reference, one column per tag, with the block's handle,
    name and layout first. The workbook is new: '<drawing> - attributes -
    <date>.xlsx' in the drawing's folder, never over an earlier one (the next
    gets ' (2)'). It also holds an 'As exported' copy, so when the modeller
    brings it back autocad_apply_attribute_sheet can tell their edits from
    changes made in the drawing since. Writing a file needs the Publish
    padlock; the drawing is not changed.

    Returns:
        str: JSON: {"saved": path, "blocks": n, "tags": [...], "next": what to do}

    Examples:
        - Use when: "give me the equipment tags in Excel so I can fill them in".
        - Use when: "export the title block attributes of every sheet, I will
          update the revisions in Excel" -> block_name='TITLEBLOCK'.
        - Don't use when: the modeller only wants to read the values in the
          chat - autocad_extract_attributes needs no padlock.
        - Don't use when: one value goes to every block (REV B everywhere) -
          autocad_set_attributes does it in one call.
        - Don't use when: the sheet is already filled in and must go back into
          the drawing - autocad_apply_attribute_sheet puts the edited values back.

    Error Handling:
        - An unsaved drawing has no folder: it says to save it first.
        - No block with attributes: it says so and writes nothing.
    """

    def work() -> tuple[list[dict[str, Any]], str]:
        doc = get_doc()
        refs, _ = _attribute_refs(doc, block_name, layer)
        return refs, _drawing_path(doc)

    refs, drawing = await run(work)
    if not drawing or not os.path.isabs(drawing):
        raise AutocadError("This drawing is not saved yet, so there is no folder to put the sheet in. Save it first; nothing was written.")
    if not refs:
        raise AutocadError("No block with attributes matches" + (f" '{block_name}'" if block_name else "") + ". Nothing was written.")
    folder = Path(drawing).parent
    path = free_name(folder, f"{Path(drawing).stem} - attributes - {datetime.now():%Y-%m-%d}")
    try:
        with open(path, "xb") as handle:
            handle.write(attribute_sheet.workbook(refs, drawing))
    except FileExistsError:
        raise AutocadError(f"{path.name} appeared while the sheet was written; it was not replaced. Run it again.") from None
    except OSError as exc:
        raise AutocadError(f"The sheet could not be written in {folder} ({exc}). Check the folder is not read-only.") from None
    return dumps({
        "saved": str(path),
        "blocks": len(refs),
        "tags": attribute_sheet.tags_in_order(refs),
        "next": (
            "Edit the tag columns on the 'Attributes' sheet in Excel and save it; keep the Handle column. "
            "Then autocad_apply_attribute_sheet with this path (dry_run=true first shows the changes)."
        ),
    })


@mcp.tool(name="autocad_apply_attribute_sheet", **tool_meta("Apply An Edited Attribute Sheet"))
@tool_errors
async def autocad_apply_attribute_sheet(
    path: Annotated[str, Field(min_length=1, description=(
        "The edited workbook (.xlsx, or a .csv with a Handle column). A bare file name is looked for "
        "next to the drawing."))],
    dry_run: Annotated[bool, Field(description="True: compare and list the changes, write nothing.")] = False,
) -> str:
    """Bring back an edited attribute sheet: compare it with the drawing and write only the cells that changed.

    Each row is matched to its block by the Handle column. A cell is written
    only when the modeller changed it: a blank cell changes nothing, a cell
    equal to the drawing changes nothing. With the 'As exported' sheet
    (autocad_export_attribute_sheet makes it) a value the drawing changed
    since the export is kept, and a value changed in both places is a
    conflict, listed and not written. All the writes are one undo step, and
    the answer lists each one old -> new ('before_after').

    Returns:
        str: JSON: {"changed": n, "changes": [{handle, block, layout, tag, old, new}],
        "conflicts", "kept_drawing", "missing_handles", "unknown_tags", "failed",
        "blank_cells", "unchanged_cells", "before_after"}

    Examples:
        - Use when: "I filled in the tags in the Excel, put them back in the
          drawing" -> path of that workbook, dry_run=true first.
        - Use when: "bring the edited spreadsheet back in, only what I changed".
        - Use when: the modeller edited the revision columns of the title
          block sheet and wants only those written.
        - Don't use when: the values are in the chat, not a file -
          autocad_set_attributes takes them as rows.

    Error Handling:
        - A file with no Handle column, a handle twice, or more than 10000
          changes: refused, nothing written.
        - A row whose block is gone, or a value under a tag the block does not
          have: listed, the rest still applied.
        - A cell AutoCAD would not take (a locked layer): listed in 'failed'.
          Through Heron's plug-in the writes are one transaction: such a cell
          refuses the whole sheet, and nothing is written.
    """

    drawing = await run(lambda: _drawing_path(get_doc()))
    edited, exported, source = read_sheet(sheet_path(path, drawing))

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        refs, objects = _attribute_refs(doc, None, None)
        try:
            planned = attribute_sheet.plan(edited, exported, refs)
        except ValueError as exc:
            raise AutocadError(str(exc)) from None
        failed: list[dict[str, Any]] = []
        written: list[dict[str, Any]] = []
        if planned["changes"] and not dry_run:
            # Only the changed cells, all in one undo step; nothing to write opens no undo step.
            with undo_mark(doc):
                # Through the plug-in every cell in one transaction, all or none (D-148); over COM cell by cell.
                if plugin_write_attributes(planned["changes"], objects):
                    written = list(planned["changes"])
                else:
                    for change in planned["changes"]:
                        ref = objects.get(change["handle"])
                        try:
                            hit = False
                            for att in ref.GetAttributes():
                                if str(att.TagString) == change["tag"]:
                                    att.TextString = change["new"]
                                    hit = True
                            if not hit:
                                raise LookupError("the block no longer has that tag")
                            ref.Update()
                            written.append(change)
                        except BaseException as exc:  # noqa: BLE001 - one cell, not the sheet
                            raise_if_busy(exc)
                            failed.append({"handle": change["handle"], "tag": change["tag"], "reason": str(exc) or type(exc).__name__})
        return {"planned": planned, "written": written, "failed": failed}

    done = await run(work)
    planned = done["planned"]
    shown = {key: (value[:MOST_LISTED] if isinstance(value, list) else value) for key, value in planned.items()}
    rows = [{"handle": c["handle"], "property": f"attribute {c['tag']}", "from": c["old"], "to": c["new"]}
            for c in done["written"]]  # fmt: skip
    if dry_run:
        answer: dict[str, Any] = {"dry_run": True, "changed": 0, "would_change": len(planned["changes"]), **shown}
    else:
        answer = {"dry_run": False, "changed": len(done["written"]), **shown, "failed": done["failed"], **before_after(rows)}
    if source and drawing and source.casefold() != drawing.casefold():
        answer["warning"] = (
            f"This sheet was exported from {source}, not from this drawing ({drawing}). Only rows whose "
            "Block still matches were used; check the changes before keeping them."
        )
    if planned["excel_converted"]:
        answer["excel_converted_note"] = (
            "Excel turned these typed values into numbers (a scale such as 1:100 becomes a time, a date "
            "a day number, 50% becomes 0.5), so they were not written. Type them again in Excel with a "
            "leading ' (for example '1:100), save, and apply the sheet again."
        )
    if planned["other_block"]:
        answer["other_block_note"] = (
            "On these rows the Block column names a different block from the one with that handle in "
            "this drawing, so the rows were not used. Was the sheet exported from another drawing?"
        )
    if planned["rows_without_handle"]:
        answer["rows_without_handle_note"] = (
            "These sheet rows have values but no handle, so Heron cannot tell which block they are for; "
            "they were not used. Rows are numbered as in Excel."
        )
    if planned["conflicts"]:
        answer["conflicts_note"] = (
            "These cells were changed both in the sheet and in the drawing since the export, so neither was "
            "chosen. Ask the modeller which value to keep, then use autocad_set_attributes."
        )
    return dumps(answer)
