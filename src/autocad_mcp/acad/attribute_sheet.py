"""The attribute spreadsheet round trip, as plain functions (D-69).

From Heron AI for Revit's export, edit, compare, apply (its D-182, D-183):
Heron hands the modeller a workbook of every block's attributes, the
modeller edits it in Excel, and Heron compares it back outside AutoCAD and
writes only the cells that really changed. No AutoCAD below this line, so
every rule is tested offline.

The workbook has two sheets. "Attributes" is the one to edit. "As exported"
is the same table, untouched, so Heron can tell three cases apart for each
cell: the modeller changed it; the drawing changed it since the export (kept,
never overwritten); both changed it (a conflict, reported and not written).
A plain CSV has no "As exported" sheet; then the sheet is compared with the
drawing alone.

Rules, the same as Revit's: a blank cell changes nothing (to empty an
attribute, use autocad_set_attributes); the Handle column says which block a
row is, so a row whose block is gone is reported; a value under a tag the
block does not have is reported, never added.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from . import xlsx

EDIT_SHEET = "Attributes"
EXPORTED_SHEET = "As exported"
README_SHEET = "Read me"
FIXED = ("Handle", "Block", "Layout")
_FIXED_NAMES = {name.lower() for name in FIXED}
MOST_CHANGES = 10000
README = [
    ["How to use this workbook"],
    ["Edit the tag columns on the 'Attributes' sheet, save, and ask Heron to apply the sheet."],
    ["Do not change the Handle column: it says which block each row is."],
    ["A blank cell changes nothing. To empty an attribute, ask Heron to set it to nothing."],
    ["You may delete rows you do not want changed, and sort or filter the sheet."],
    ["Leave the 'As exported' sheet as it is: Heron uses it to see what the drawing had at export."],
    ["Heron writes only the cells you changed, in one undo step, and lists each one old -> new."],
]


def tags_in_order(refs: list[dict[str, Any]]) -> list[str]:
    """Every tag, in the order they are first met: the columns after Handle, Block, Layout."""
    seen: dict[str, None] = {}
    for ref in refs:
        for tag in ref["attributes"]:
            seen.setdefault(str(tag), None)
    return list(seen)


def table(refs: list[dict[str, Any]]) -> list[list[str]]:
    """The heading, then one row per block reference."""
    tags = tags_in_order(refs)
    rows = [[*FIXED, *tags]]
    for ref in refs:
        values = {str(k): v for k, v in ref["attributes"].items()}
        rows.append([str(ref["handle"]), str(ref["block"]), str(ref.get("layout") or ""),
                     *[str(values[tag]) if tag in values else "" for tag in tags]])  # fmt: skip
    return rows


def workbook(refs: list[dict[str, Any]]) -> bytes:
    """The workbook to hand the modeller: Attributes, As exported, Read me."""
    rows = table(refs)
    widths = [10, 24, 16, *[18] * (len(rows[0]) - len(FIXED))]
    return xlsx.write([(EDIT_SHEET, rows, widths), (EXPORTED_SHEET, rows, widths), (README_SHEET, README, [100])])


def _records(rows: list[list[str]], where: str) -> list[dict[str, str]]:
    """Rows under their heading, as {column: text}. The heading must have a Handle column."""
    rows = [row for row in rows if any(str(cell).strip() for cell in row)]
    if not rows:
        raise ValueError(f"{where} is empty")
    heading = [str(cell).strip() for cell in rows[0]]
    if not any(name.lower() == "handle" for name in heading):
        raise ValueError(
            f"{where} has no Handle column, so Heron cannot tell which block a row is. Export the sheet "
            "with autocad_export_attribute_sheet, edit that one, and keep its Handle column."
        )
    records = []
    for row in rows[1:]:
        record = {}
        for index, name in enumerate(heading):
            if name:
                record["Handle" if name.lower() == "handle" else name] = str(row[index]) if index < len(row) else ""
        records.append(record)
    return records


def read_workbook(content: bytes) -> tuple[list[dict[str, str]], list[dict[str, str]] | None]:
    """(the edited rows, the rows as exported or None) from an .xlsx Heron exported."""
    sheets = xlsx.read(content)
    edit = next((rows for name, rows in sheets.items() if name.lower() == EDIT_SHEET.lower()), None)
    if edit is None:
        edit = next(iter(sheets.values()))  # a sheet the modeller renamed or rebuilt: the first one
    exported = next((rows for name, rows in sheets.items() if name.lower() == EXPORTED_SHEET.lower()), None)
    return _records(edit, "The sheet"), (_records(exported, "The 'As exported' sheet") if exported else None)


def read_csv(text: str) -> list[dict[str, str]]:
    """The rows of a CSV: comma or semicolon (Excel uses either, by the PC's region)."""
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return _records(list(csv.reader(io.StringIO(text), delimiter=delimiter)), "The CSV")


def _by_handle(records: list[dict[str, str]], where: str) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for record in records:
        handle = record.get("Handle", "").strip().upper()
        if not handle:
            continue
        if handle in found:
            raise ValueError(f"{where} has the handle {handle} twice. Each block may appear once; nothing was changed.")
        found[handle] = record
    return found


def plan(edited: list[dict[str, str]], exported: list[dict[str, str]] | None,
         refs: list[dict[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """What to write: only cells the modeller changed, never over a change made in the drawing since.

    refs are the drawing's blocks now: {handle, block, layout, attributes}.
    """
    now = {str(ref["handle"]).upper(): ref for ref in refs}
    sheet = _by_handle(edited, "The sheet")
    before = _by_handle(exported, "The 'As exported' sheet") if exported is not None else None
    changes: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    kept_drawing: list[dict[str, Any]] = []
    missing: list[str] = []
    unknown: list[dict[str, str]] = []
    blank = unchanged = 0
    for handle, record in sheet.items():
        ref = now.get(handle)
        if ref is None:
            missing.append(handle)
            continue
        tags = {str(tag).upper(): str(tag) for tag in ref["attributes"]}
        for column_name, value in record.items():
            if column_name.strip().lower() in _FIXED_NAMES:
                continue
            new = value
            if new.strip() == "":
                blank += 1
                continue
            tag = tags.get(column_name.strip().upper())
            if tag is None:
                unknown.append({"handle": handle, "column": column_name})
                continue
            current = str(ref["attributes"][tag])
            if new == current:
                unchanged += 1
                continue
            if before is not None:
                was_row = before.get(handle)
                was = was_row.get(column_name) if was_row is not None else None
                if was is not None and new == was:
                    # The modeller left it; the drawing changed it since the export. Keep the drawing.
                    kept_drawing.append({"handle": handle, "tag": tag, "exported": was, "drawing": current})
                    continue
                if was is not None and current != was:
                    conflicts.append({"handle": handle, "block": ref["block"], "tag": tag, "exported": was,
                                      "drawing": current, "sheet": new})  # fmt: skip
                    continue
            changes.append({"handle": ref["handle"], "block": ref["block"], "layout": ref.get("layout"),
                            "tag": tag, "old": current, "new": new})  # fmt: skip
    if len(changes) > MOST_CHANGES:
        raise ValueError(f"The sheet changes {len(changes)} values, more than {MOST_CHANGES} in one go. Split it.")
    return {
        "changes": changes,
        "conflicts": conflicts,
        "kept_drawing": kept_drawing,
        "missing_handles": missing,
        "unknown_tags": unknown,
        "blank_cells": blank,
        "unchanged_cells": unchanged,
        "compared_with": "the sheet as exported and the drawing now" if before is not None else "the drawing now",
    }
