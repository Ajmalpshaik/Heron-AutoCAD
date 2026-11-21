"""AutoCAD tables from Excel ranges, and edits to the cells of a table (D-83).

Plain functions over plain values, tested without AutoCAD:

* **A sheet range as a grid of cells**: "A1:D20" read out of a workbook that
  ``acad/xlsx.py`` read, padded square, with the cells Excel only *shows* as
  text (a date, a time, a percent: ``xlsx.Converted``) left empty and listed,
  never written as the number behind them (D-75).
* **Cell edits by row and column**, counted from 1 at the table's top-left
  cell, title and header rows included, the way an Excel address counts
  ("B3" = row 3, column 2).
* **The alignment rule**: Heron's tables keep their text in the vertical
  middle of each cell. ``middle_of`` turns any alignment into the middle one
  with the same left / centre / right.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ..core.errors import raise_if_busy
from .xlsx import Converted, column, column_index

# A table bigger than this is not a drawing table; give a smaller range.
MOST_ROWS = 500
MOST_COLUMNS = 40
MOST_CELLS = 5000
MOST_EDITS = 2000

# AcCellAlignment (COM and .NET use the same numbers): top 1-3, middle 4-6, bottom 7-9.
TOP_LEFT, MIDDLE_LEFT, MIDDLE_CENTER = 1, 4, 5
# AcRowType: data 1, title 2, header 4.
DATA_ROW, TITLE_ROW, HEADER_ROW = 1, 2, 4
ROW_TYPES = (TITLE_ROW, HEADER_ROW, DATA_ROW)
# AcCellState (COM): content locked 1, linked to a data source 16.
STATE_CONTENT_LOCKED = 1
STATE_LINKED = 16

_ADDRESS = re.compile(r"^\$?([A-Za-z]{1,3})\$?([0-9]{1,7})$")


class CellError(ValueError):
    """A range or a cell edit that cannot be used; the message says why in plain words."""


def middle_of(alignment: Any) -> int:
    """The same left / centre / right, in the vertical middle of the cell."""
    try:
        value = int(alignment)
    except (TypeError, ValueError):
        return MIDDLE_CENTER
    if not 1 <= value <= 9:
        return MIDDLE_CENTER
    return MIDDLE_LEFT + (value - 1) % 3


def address(row: int, col: int) -> str:
    """0-based row and column as an Excel address: (2, 1) -> 'B3'."""
    return f"{column(col)}{row + 1}"


def parse_address(text: str) -> tuple[int, int]:
    """'B3' (or '$B$3') as a 0-based (row, column)."""
    found = _ADDRESS.match(str(text).strip())
    if not found:
        raise CellError(f"'{text}' is not a cell address. Give a column letter and a row number, e.g. 'B3'.")
    row = int(found.group(2))
    if row < 1:
        raise CellError(f"'{text}': rows count from 1.")
    return row - 1, column_index(found.group(1))


def parse_range(text: str) -> tuple[int, int, int, int]:
    """'A1:D20' (or one cell 'B3') as 0-based (first row, first column, last row, last column)."""
    parts = [p for p in str(text).replace(" ", "").split(":")]
    if len(parts) == 1:
        row, col = parse_address(parts[0])
        return row, col, row, col
    if len(parts) != 2 or not all(parts):
        raise CellError(f"'{text}' is not a range. Give two corners, e.g. 'A1:D20'.")
    (r1, c1), (r2, c2) = parse_address(parts[0]), parse_address(parts[1])
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)


def range_text(first_row: int, first_col: int, last_row: int, last_col: int) -> str:
    return f"{address(first_row, first_col)}:{address(last_row, last_col)}"


def used_range(rows: Sequence[Sequence[str]]) -> tuple[int, int, int, int] | None:
    """The smallest box holding every cell with something in it, or None for an empty sheet."""
    filled = [(r, c) for r, row in enumerate(rows) for c, value in enumerate(row) if str(value).strip()]
    if not filled:
        return None
    return (
        min(r for r, _ in filled),
        min(c for _, c in filled),
        max(r for r, _ in filled),
        max(c for _, c in filled),
    )


def check_size(rows: int, columns: int) -> None:
    if rows > MOST_ROWS or columns > MOST_COLUMNS or rows * columns > MOST_CELLS:
        raise CellError(
            f"{rows} rows x {columns} columns is too big for one drawing table (at most {MOST_ROWS} rows, "
            f"{MOST_COLUMNS} columns, {MOST_CELLS} cells). Give a smaller cell_range."
        )


def grid_from_sheet(rows: Sequence[Sequence[str]], cell_range: str | None = None) -> dict[str, Any]:
    """The cells of a sheet range, as the table will show them.

    ``rows`` is one sheet from ``xlsx.read``. With no ``cell_range`` the used
    range is taken (every cell with something in it). Each row of the grid
    has the same number of cells. A cell Excel only shows as a date, a time, a
    fraction or a percent is left empty and listed in "converted": the number
    behind it is not what the modeller sees in Excel (D-75).

    Returns {"grid": [[str]], "range": "A1:D20", "rows": int, "columns": int,
    "converted": [{"cell", "shown_as", "number"}]}.
    """
    if cell_range:
        box = parse_range(cell_range)
    else:
        found = used_range(rows)
        if found is None:
            raise CellError("That sheet is empty. Pick the sheet with the schedule on it, or give a cell_range.")
        box = found
    first_row, first_col, last_row, last_col = box
    height, width = last_row - first_row + 1, last_col - first_col + 1
    check_size(height, width)
    grid: list[list[str]] = []
    converted: list[dict[str, str]] = []
    for r in range(first_row, last_row + 1):
        source = rows[r] if r < len(rows) else []
        line: list[str] = []
        for c in range(first_col, last_col + 1):
            value = source[c] if c < len(source) else ""
            if isinstance(value, Converted):
                converted.append({"cell": address(r, c), "shown_as": value.shown_as, "number": str(value)})
                value = ""
            line.append("" if value is None else str(value))
        grid.append(line)
    if not any(cell.strip() for line in grid for cell in line) and not converted:
        raise CellError(f"{range_text(*box)} has nothing in it. Check the sheet and the range.")
    return {
        "grid": grid,
        "range": range_text(*box),
        "rows": height,
        "columns": width,
        "converted": converted,
    }


def table_layout(grid_rows: int, title: bool, header: bool) -> dict[str, int]:
    """Where a filled table's rows go: a title row first when there is one, then the sheet's rows.

    With ``header`` the sheet's first row is the table's header row.
    """
    title_rows = 1 if title else 0
    return {
        "title_rows": title_rows,
        "header_rows": 1 if header and grid_rows else 0,
        "total_rows": title_rows + grid_rows,
        "first_sheet_row": title_rows,
    }


def plan_cell_edits(
    cells: Sequence[dict[str, Any]], rows: int, columns: int, grow: bool = False
) -> dict[str, Any]:
    """Check cell edits against a table of ``rows`` x ``columns`` and put them in order.

    Each edit is {"row": 3, "column": 2, "value": "..."} or {"cell": "B3",
    "value": "..."}; both count from 1 at the top-left cell, title and header
    rows included. A cell past the table's last row or column is refused
    unless ``grow``, which adds the rows and columns it needs at the end.
    The same cell given twice is refused: which value was meant?

    Returns {"edits": [{"row", "column", "cell", "value"}] (0-based row and
    column), "add_rows": int, "add_columns": int}.
    """
    if not cells:
        raise CellError("Give at least one cell to change, e.g. {\"cell\": \"B3\", \"value\": \"DN50\"}.")
    if len(cells) > MOST_EDITS:
        raise CellError(f"{len(cells)} cells is more than {MOST_EDITS} in one call. Split the job.")
    edits: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for number, spec in enumerate(cells, 1):
        if not isinstance(spec, dict):
            raise CellError(f"Cell {number} must be an object such as {{\"cell\": \"B3\", \"value\": \"DN50\"}}.")
        if "value" not in spec:
            raise CellError(f"Cell {number} has no value. Give \"value\": \"\" to empty a cell.")
        if spec.get("cell") is not None:
            row, col = parse_address(str(spec["cell"]))
        else:
            try:
                row, col = int(spec["row"]) - 1, int(spec["column"]) - 1
            except (KeyError, TypeError, ValueError):
                raise CellError(
                    f"Cell {number} needs either \"cell\" (e.g. \"B3\") or \"row\" and \"column\" (counted from 1)."
                ) from None
            if row < 0 or col < 0:
                raise CellError(f"Cell {number}: rows and columns count from 1.")
        if (row, col) in seen:
            raise CellError(f"{address(row, col)} is given twice. Give each cell once.")
        seen.add((row, col))
        value = spec["value"]
        edits.append({"row": row, "column": col, "cell": address(row, col), "value": "" if value is None else str(value)})
    need_rows = max(e["row"] for e in edits) + 1
    need_columns = max(e["column"] for e in edits) + 1
    add_rows, add_columns = max(0, need_rows - rows), max(0, need_columns - columns)
    if (add_rows or add_columns) and not grow:
        outside = [e["cell"] for e in edits if e["row"] >= rows or e["column"] >= columns]
        raise CellError(
            f"The table has {rows} rows and {columns} columns, so {', '.join(outside[:10])} is outside it. "
            "Pass grow=true to add the rows or columns it needs, or check the numbering (row 1 is the top row, "
            "the title row when there is one)."
        )
    check_size(rows + add_rows, columns + add_columns)
    edits.sort(key=lambda e: (e["row"], e["column"]))
    return {"edits": edits, "add_rows": add_rows, "add_columns": add_columns}


def locked_reason(state: Any) -> str | None:
    """Why a cell in this AcCellState cannot be written, or None when it can."""
    try:
        value = int(state)
    except (TypeError, ValueError):
        return None
    if value & STATE_LINKED:
        return "it is linked to Excel: change it in the sheet, then autocad_update_table_links"
    if value & STATE_CONTENT_LOCKED:
        return "its content is locked in AutoCAD (Table Cell > Locking)"
    return None


def middle_rows(table: Any) -> int:
    """Put the text of every row type (title, header, data) in the vertical middle; how many were set.

    One call per row type, not per cell. A table that refuses keeps its
    style's own alignment: this is never worth failing a table for.
    """
    done = 0
    for row_type in ROW_TYPES:
        try:
            table.SetAlignment(row_type, middle_of(table.GetAlignment(row_type)))
            done += 1
        except Exception as exc:  # noqa: BLE001 - only a nicety
            raise_if_busy(exc)
            continue
    return done
