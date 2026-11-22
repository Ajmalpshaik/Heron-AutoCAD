"""Tables from Excel, kept up to date, and edits to the cells of a table (D-83).

* ``autocad_table_from_excel`` shows an Excel range as an AutoCAD table. By
  default it is a real AutoCAD **data link** (the Data Link Manager's kind),
  made by the Heron plug-in because COM has no call for it, so the table can
  be updated when the sheet changes. When a link cannot be made (a .csv, an
  older plug-in, AutoCAD refusing it) the table is filled from the sheet as it
  is now, over COM, and the answer says it is not linked.
* ``autocad_update_table_links`` updates linked tables from their sheets.
* ``autocad_set_table_cells`` changes cells of any table by row and column.

Every table Heron writes keeps its text in the vertical middle of each cell
(``table_cells.middle_of``), as ``autocad_add_table`` does. The reading and the
planning are plain functions (``acad/xlsx.py``, ``acad/table_cells.py``),
tested without AutoCAD.
"""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from ..acad import xlsx
from ..acad.entities import resolve_handle
from ..acad.table_cells import (
    DATA_ROW,
    ROW_TYPES,
    CellError,
    grid_from_sheet,
    locked_reason,
    middle_of,
    middle_rows,
    plan_cell_edits,
    table_layout,
)
from ..acad.tables import apply_properties, ensure_layer
from ..core.bridge import OLD_PLUGIN
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import (
    COORDS_OPT,
    LAYER_OPT,
    before_after,
    discard_new,
    in_plugin,
    point,
    ucs_for,
    world_coords,
)
from .attribute_sheet import sheet_path

PREVIEW_ROWS = 5
TABLE_TYPE = "AcDbTable"


def read_rows(path: Path, sheet: str | None) -> tuple[str, list[list[str]]]:
    """(sheet name, rows of cell text) from an .xlsx or a .csv."""
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise AutocadError(f"{path.name} could not be read ({exc}). If it is open in Excel, save it and try again.") from None
    if path.suffix.lower() == ".csv":
        if len(content) > xlsx.MOST_FILE_BYTES:
            raise AutocadError(f"{path.name} is bigger than 20 MB.")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("cp1252", errors="replace")  # Excel's "CSV" on a Western PC
        return path.stem, [list(row) for row in csv.reader(io.StringIO(text))]
    try:
        sheets = xlsx.read(content)
    except xlsx.SheetError as exc:
        raise AutocadError(f"{path.name} cannot be read: {exc}.") from None
    if not sheet:
        name = next(iter(sheets))
        return name, sheets[name]
    for name, rows in sheets.items():
        if name.strip().lower() == sheet.strip().lower():
            return name, rows
    raise AutocadError(f"{path.name} has no sheet called '{sheet}'. Its sheets: {', '.join(sheets)}.")


# Why a link could not be made that a filled table answers: no plug-in to ask
# (--no-bridge), one too old for it, or AutoCAD failing to make or read the link.
# Anything else stops the job: HERONSTOP, a padlock turned off, a refusal the
# modeller has to act on (no sheet tab for space='paper', no such style), or
# "Outcome unknown", when the linked table may already be there.
_CANNOT_LINK = (
    "--no-bridge",
    "does not have the operation",
    "read nothing from",
    "AutoCAD refused it (",
    "Heron in AutoCAD hit an error:",
)


def fill_instead(exc: AutocadError) -> bool:
    """True when the plug-in's answer means "no link possible here", so a filled table is the honest next best."""
    text = str(exc)
    if text.startswith("Outcome unknown"):
        return False
    return text == OLD_PLUGIN or any(marker in text for marker in _CANNOT_LINK)


def column_widths_for(grid: list[list[str]], text_height: float) -> list[float]:
    """A width per column that fits its longest text on one line, roughly, with the cell margins."""
    widths = []
    for col in range(len(grid[0]) if grid else 0):
        longest = max((len(row[col]) for row in grid), default=0)
        widths.append(round(max(8, longest) * 0.75 * text_height + 1.5 * text_height, 3))
    return widths


def fill_table(
    doc: Any,
    target: Any,
    at: Any,
    grid: list[list[str]],
    *,
    title: str | None,
    header: bool,
    text_height: float | None,
    widths: list[float] | None,
    style: str | None,
) -> tuple[Any, dict[str, Any]]:
    """A new table filled from the grid over COM; (table, what happened)."""
    columns = len(grid[0])
    layout = table_layout(len(grid), bool(title), header)
    height = float(text_height) if text_height else None
    row_h = height * 2.0 if height else 10.0
    not_set: list[str] = []
    try:
        table = target.AddTable(at, layout["total_rows"], columns, row_h, widths[0] if widths else row_h * 6)
    except Exception as exc:  # noqa: BLE001
        raise_if_busy(exc)
        raise AutocadError(f"AutoCAD would not add the table ({com_message(exc)}).") from exc
    if style:
        try:
            table.StyleName = style.strip()
        except Exception as exc:  # noqa: BLE001
            raise_if_busy(exc)
            gone = discard_new(table)
            raise AutocadError(
                f"This drawing has no table style called '{style}' ({com_message(exc)}). Make it with "
                "autocad_create_styles(table_styles=...), copy it in with autocad_import_from_drawing, "
                "or leave style out." + (" Nothing was left in the drawing." if gone else " An empty one was left in the drawing; erase it.")
            ) from exc
    if not widths:
        # Fit each column to its text at the height it will have: the one asked
        # for, else the table style's own (read once the style is set).
        try:
            style_height = float(table.GetTextHeight(DATA_ROW))
        except Exception as exc:  # noqa: BLE001 - a plain guess, AutoCAD wraps what does not fit
            raise_if_busy(exc)
            style_height = 0.0
        widths = column_widths_for(grid, height or style_height or 2.5)
    try:
        table.RegenerateTableSuppressed = True
    except Exception as exc:  # noqa: BLE001 - only a speed-up
        raise_if_busy(exc)
    # A table starts with a title row and a header row; with no title (or no
    # header) asked for, those rows hold the sheet's rows like any other.
    for flag, wanted in (("TitleSuppressed", bool(title)), ("HeaderSuppressed", bool(layout["header_rows"]))):
        if not wanted:
            try:
                setattr(table, flag, True)
            except Exception as exc:  # noqa: BLE001
                raise_if_busy(exc)
                not_set.append(flag)
    for index, width in enumerate(widths[:columns] + [widths[-1]] * (columns - len(widths))):
        try:
            table.SetColumnWidth(index, width)
        except Exception as exc:  # noqa: BLE001 - the column keeps the default width
            raise_if_busy(exc)
            not_set.append(f"width of column {index + 1}")
    written = 0
    if title:
        try:
            table.SetText(0, 0, title)
            written += 1
        except Exception as exc:  # noqa: BLE001
            raise_if_busy(exc)
            not_set.append("title")
    for r, row in enumerate(grid, layout["first_sheet_row"]):
        for c, value in enumerate(row):
            if not value:
                continue
            try:
                table.SetText(r, c, value)
                written += 1
            except Exception as exc:  # noqa: BLE001 - one cell, not the table
                raise_if_busy(exc)
                not_set.append(f"cell {r + 1},{c + 1}")
    if height:
        try:
            table.SetTextHeight(sum(ROW_TYPES), height)
        except Exception as exc:  # noqa: BLE001 - the style keeps its own
            raise_if_busy(exc)
            not_set.append(f"text_height ({com_message(exc)})")
    aligned = middle_rows(table)
    try:
        table.RegenerateTableSuppressed = False
    except Exception:  # noqa: BLE001
        pass
    report: dict[str, Any] = {"rows": layout["total_rows"], "columns": columns, "cells_written": written, "rows_aligned_middle": aligned}
    if not_set:
        report["not_set"] = not_set[:30]
    return table, report


@mcp.tool(name="autocad_table_from_excel", **tool_meta("Table From Excel (Data Link)"))
@tool_errors
async def autocad_table_from_excel(
    path: Annotated[str, Field(min_length=1, description="The .xlsx (or .csv) file: a full path, or a file name in the drawing's folder.")],
    position: Annotated[list[float], Field(description="Top-left corner of the table, as [x, y]. The table grows downward from here.")],
    sheet: Annotated[str | None, Field(default=None, description="The sheet (tab) to read, e.g. 'Pumps'. Omit for the first sheet.")] = None,
    cell_range: Annotated[
        str | None,
        Field(default=None, description="The Excel range, e.g. 'A1:F25'. Omit for every cell with something in it."),
    ] = None,
    link: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "True: a real AutoCAD data link, so the table can be updated from the sheet later "
                "(autocad_update_table_links); made by the Heron plug-in. False, or when a link cannot be "
                "made: the table is filled with the sheet as it is now and will not update by itself."
            ),
        ),
    ] = True,
    title: Annotated[
        str | None,
        Field(default=None, description="A title row across the top, e.g. 'PUMP SCHEDULE'. Only for a table that is not linked: a linked table shows the range exactly; put the title in the sheet."),
    ] = None,
    header: Annotated[bool, Field(default=True, description="True: the range's first row is the table's header row (bold, the headings).")] = True,
    text_height: Annotated[float | None, Field(default=None, gt=0, description="Text height in drawing units on every row. Omit to keep the table style's own.")] = None,
    column_widths: Annotated[
        list[float] | None,
        Field(default=None, description="Width of each column in drawing units, for a table that is not linked. Omit to fit each column's longest text."),
    ] = None,
    style: Annotated[str | None, Field(default=None, description="Table style name, already in the drawing. Omit for the current one.")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    space: Annotated[str, Field(default="model", description="'model' or 'paper'. A schedule normally belongs on the sheet, so 'paper'.", pattern="^(model|paper)$")] = "model",
    coords: Annotated[str, COORDS_OPT] = "world",
    dry_run: Annotated[
        bool,
        Field(default=False, description="True: read the sheet and say what the table would hold (size, first rows, cells left out); make nothing."),
    ] = False,
) -> str:
    """Show an Excel range as an AutoCAD table, linked so it can be updated when the sheet changes (Data Link).

    The Insert > Data Link job: a schedule kept in Excel (pumps, fans, a door
    schedule, a cable list) placed on the drawing as a real AutoCAD table. By
    default it is linked, as AutoCAD's own Data Link Manager links it, so
    autocad_update_table_links brings later edits in; the link is made by the
    Heron plug-in. When a link cannot be made, the table is filled with the
    sheet as it is now and the answer says "linked": false and why. Text sits
    in the vertical middle of each cell. A cell Excel only shows as a date, a
    time or a percent is left empty in a filled table and listed (type it with
    a leading ' in Excel). One undo step.

    Returns:
        JSON: {"created": true, "handle", "linked": bool, "range", "sheet", "rows", "columns",
        "excel_converted": [{cell, shown_as, number}], "not_linked_because" when it fell back}

    Examples:
        - Use when: "put the pump schedule from the Excel file on the sheet
          as a table" -> path='pumps.xlsx', space='paper'.
        - Use when: "link the A1:F30 range of the fan sheet as a table, so it
          updates" -> cell_range='A1:F30'.
        - Don't use when: the rows come from the drawing's own blocks -
          autocad_extract_attributes, then autocad_add_table.
        - Don't use when: the table is already there and the sheet changed -
          autocad_update_table_links.

    Error Handling:
        - A file, sheet or range that is not there, or a range bigger than
          500 rows, 40 columns or 5,000 cells, is refused before anything is made.
    """
    if len(position) < 2:
        raise AutocadError("position needs [x, y].")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        source = sheet_path(path, str(doc.FullName))
        sheet_name, rows = read_rows(source, sheet)
        try:
            planned = grid_from_sheet(rows, cell_range)
        except CellError as exc:
            raise AutocadError(f"{exc} Nothing was made.") from None
        facts: dict[str, Any] = {
            "path": str(source),
            "sheet": sheet_name,
            "range": planned["range"],
            "rows": planned["rows"],
            "columns": planned["columns"],
        }
        if planned["converted"]:
            facts["excel_converted"] = planned["converted"][:30]
        if dry_run:
            return {
                **facts,
                "dry_run": True,
                "would": "link" if link and source.suffix.lower() == ".xlsx" else "fill",
                "first_rows": planned["grid"][:PREVIEW_ROWS],
            }
        ucs = ucs_for(doc, coords)
        at_world = world_coords(position, ucs)
        why_not = None
        if not link:
            why_not = "link=false was asked for"
        elif source.suffix.lower() != ".xlsx":
            why_not = "Heron links .xlsx workbooks only; a .csv is filled as it is now"
        else:
            args = {
                "path": os.path.abspath(str(source)),
                "sheet": sheet_name,
                "range": planned["range"],
                "position": at_world,
                "space": space,
                "layer": layer,
                "style": style.strip() if style else None,
                "text_height": float(text_height) if text_height else None,
            }
            try:
                report = in_plugin("excel_table", args, "A table linked to Excel")
            except AutocadError as exc:
                if not fill_instead(exc):
                    raise  # stopped, a padlock, a refusal to act on, or maybe made: never a table over COM
                why_not = str(exc)
            else:
                result = {"created": True, "linked": True, **facts, **report}
                if title:
                    result["title_not_added"] = "A linked table shows the Excel range exactly; put the title in the sheet."
                return result
        target = get_space(doc, space)
        with undo_mark(doc):
            if layer:
                ensure_layer(doc, layer)
            table, report = fill_table(
                doc, target, point(position, "position", ucs), planned["grid"],
                title=title, header=header, text_height=text_height,
                widths=[float(w) for w in column_widths] if column_widths else None, style=style,
            )  # fmt: skip
            notes = apply_properties(doc, table, layer, None, None)
        return {
            "created": True,
            "handle": str(table.Handle),
            "type": "table",
            "linked": False,
            "not_linked_because": why_not,
            **facts,
            **report,
            **notes,
            "note": "Filled with the sheet as it is now: it will not update by itself. Run this again after the sheet changes, or with link=true once Heron can link it.",
        }

    return dumps(await run(work))


@mcp.tool(name="autocad_update_table_links", **tool_meta("Update Tables From Excel"))
@tool_errors
async def autocad_update_table_links(
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="The linked tables to update. Omit for every table in the drawing that is linked to Excel."),
    ] = None,
) -> str:
    """Update tables linked to Excel from their sheets (DATALINKUPDATE), keeping Heron's table formatting.

    After the workbook behind a linked table was edited and saved, this reads
    it again and puts the new values in the table. Text stays in the vertical
    middle of each cell; the table's own formatting is kept, not Excel's. Done
    by the Heron plug-in in one transaction. A table that is not linked (one
    filled from a sheet, or drawn by hand) is listed, not changed.

    Returns:
        JSON: {"updated": [{handle, source}], "not_linked": [handle], "note": str (only when no
        table is linked)}. A workbook that cannot be read refuses the whole job and nothing
        is changed (D-83), so there is no per-table failure list.

    Examples:
        - Use when: "the sheet changed in Excel, update the linked table".
        - Use when: "refresh all the Excel tables before we issue".
        - Don't use when: the table was filled, not linked - run
          autocad_table_from_excel again, or autocad_set_table_cells.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        wanted = [str(h).strip() for h in handles] if handles else None
        return in_plugin("update_table_links", {"handles": wanted}, "Updating tables from Excel")

    return dumps(await run(work))


def _cell_text(table: Any, row: int, col: int) -> str:
    try:
        return str(table.GetText(row, col))
    except Exception as exc:  # noqa: BLE001 - an empty cell AutoCAD will not read
        raise_if_busy(exc)
        return ""


def _blocked(table: Any, row: int, col: int) -> str | None:
    try:
        reason = locked_reason(table.GetCellState(row, col))
    except Exception as exc:  # noqa: BLE001 - an older AutoCAD without cell states
        raise_if_busy(exc)
        reason = None
    if reason:
        return reason
    try:
        merged = table.IsMergedCell(row, col)
    except Exception as exc:  # noqa: BLE001 - AutoCAD would not say; SetText decides
        raise_if_busy(exc)
        return None
    if isinstance(merged, tuple) and merged and merged[0] and len(merged) >= 5:
        first_row, first_col = int(merged[1]), int(merged[3])
        if (first_row, first_col) != (row, col):
            return f"it is inside a merged cell that starts at row {first_row + 1}, column {first_col + 1}: write that one"
    return None


@mcp.tool(name="autocad_set_table_cells", **tool_meta("Set Table Cells"))
@tool_errors
async def autocad_set_table_cells(
    handle: Annotated[str, Field(min_length=1, description="The table, e.g. from autocad_list_entities (type 'table') or the tool that made it.")],
    cells: Annotated[
        list[dict[str, Any]],
        Field(
            min_length=1,
            description=(
                'The cells to change, e.g. [{"cell": "B3", "value": "DN50"}, {"row": 4, "column": 2, "value": "DN65"}]. '
                "Rows and columns count from 1 at the table's top-left cell, title and header rows included, as an "
                'Excel address does ("B3" = row 3, column 2). "value": "" empties a cell.'
            ),
        ),
    ],
    grow: Annotated[
        bool,
        Field(default=False, description="True: a cell past the last row or column adds the rows or columns it needs at the end."),
    ] = False,
    dry_run: Annotated[
        bool,
        Field(default=False, description="True: list each cell's old and new text and the cells that cannot be written; change nothing."),
    ] = False,
) -> str:
    """Change cells of a table already in the drawing, by row and column, old -> new.

    For a schedule on the sheet that needs a few values corrected or a row
    added, without redrawing it. Only cells whose text really changes are
    written, in one undo step; each one's text goes in the vertical middle of
    its cell, keeping its left / centre / right. A cell linked to Excel or
    locked in AutoCAD is listed and left alone.

    Returns:
        JSON: {"handle", "changed": int, "unchanged": [cell], "refused": [{cell, why}],
        "added_rows", "added_columns", "before_after": [{handle, property, from, to}]}

    Examples:
        - Use when: "in the pump schedule change P-02's flow in C4 to 12.5".
        - Use when: "add a row for P-05 at the bottom of the table" ->
          grow=true with the new row's cells.
        - Don't use when: the table is linked to Excel - change the sheet,
          then autocad_update_table_links.
        - Don't use when: making a new table - autocad_add_table or
          autocad_table_from_excel.

    Error Handling:
        - A handle that is not a table, a cell given twice, or a cell outside
          the table without grow is refused before anything changes.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        table = resolve_handle(doc, handle)
        if str(table.ObjectName) != TABLE_TYPE:
            raise AutocadError(f"{handle} is a {table.ObjectName}, not a table. autocad_list_entities(entity_type='table') lists the tables.")
        rows, columns = int(table.Rows), int(table.Columns)
        try:
            plan = plan_cell_edits(cells, rows, columns, grow)
        except CellError as exc:
            raise AutocadError(f"{exc} Nothing was changed.") from None
        to_write: list[dict[str, Any]] = []
        unchanged: list[str] = []
        refused: list[dict[str, str]] = []
        for edit in plan["edits"]:
            inside = edit["row"] < rows and edit["column"] < columns
            old = _cell_text(table, edit["row"], edit["column"]) if inside else ""
            if inside:
                why = _blocked(table, edit["row"], edit["column"])
                if why:
                    refused.append({"cell": edit["cell"], "why": why})
                    continue
            if old == edit["value"]:
                unchanged.append(edit["cell"])
                continue
            to_write.append({**edit, "old": old})
        listed = [{"handle": str(table.Handle), "property": f"cell {e['cell']}", "from": e["old"], "to": e["value"]} for e in to_write]
        result: dict[str, Any] = {
            "handle": str(table.Handle),
            "unchanged": unchanged,
            "refused": refused,
            "added_rows": plan["add_rows"],
            "added_columns": plan["add_columns"],
        }
        if dry_run or not to_write:
            word = "would_change" if dry_run else "changed"
            return {**result, word: len(to_write), "dry_run": dry_run, **before_after(listed if dry_run else [])}
        written: list[dict[str, Any]] = []
        with undo_mark(doc):
            if plan["add_rows"]:
                table.InsertRows(rows, float(table.GetRowHeight(rows - 1)), plan["add_rows"])
            if plan["add_columns"]:
                table.InsertColumns(columns, float(table.GetColumnWidth(columns - 1)), plan["add_columns"])
            for edit in to_write:
                try:
                    table.SetText(edit["row"], edit["column"], edit["value"])
                except Exception as exc:  # noqa: BLE001 - one cell, not the job
                    raise_if_busy(exc)
                    refused.append({"cell": edit["cell"], "why": f"AutoCAD refused it ({com_message(exc)})"})
                    continue
                try:
                    alignment = table.GetCellAlignment(edit["row"], edit["column"])
                    table.SetCellAlignment(edit["row"], edit["column"], middle_of(alignment))
                except Exception as exc:  # noqa: BLE001 - the text is written; the alignment is a nicety
                    raise_if_busy(exc)
                written.append(edit)
        done = [row for row in listed if row["property"] in {f"cell {e['cell']}" for e in written}]
        return {**result, "changed": len(written), "dry_run": False, **before_after(done)}

    return dumps(await run(work))
