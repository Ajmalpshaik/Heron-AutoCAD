"""A check list run saved as an Excel workbook and an HTML page (D-65).

Pure: it turns the run's answer into file contents and picks file names, so
every rule is tested without AutoCAD. The workbook is written with the
standard library (an .xlsx is a zip of a few XML files), so Heron needs no
new package for it.

Never overwrite: an earlier report keeps its name. The next one gets a number
(" (2)", " (3)" ...), and the files are opened in exclusive-create mode, so a
file that appeared a moment ago is not replaced either.
"""

from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .checklist import FAIL, NO_DATA, NOT_RUN, PASS, PASS_MEANS

MOST_NUMBER = 999
COLUMNS = ("State", "Severity", "Check", "Label", "Source", "From", "Target", "Failing", "Note", "Advice", "Objects")
STATE_COLOURS = {PASS: "#d9f2d9", FAIL: "#f8d0d0", NO_DATA: "#fbe8c0", NOT_RUN: "#e4e4e4"}


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text.strip()).strip("-").lower() or "checklist"


def stem_for(drawing: str, checklist: str, day: str) -> str:
    """'M-101 - checklist before-issue - 2026-11-21': the drawing, the list and the day."""
    return f"{Path(drawing).stem} - checklist {_slug(checklist)} - {day}"


def free_names(folder: Path, stem: str) -> tuple[Path, Path]:
    """The first .xlsx and .html pair where neither file is there yet."""
    for number in range(1, MOST_NUMBER + 1):
        name = stem if number == 1 else f"{stem} ({number})"
        workbook, page = folder / f"{name}.xlsx", folder / f"{name}.html"
        if not workbook.exists() and not page.exists():
            return workbook, page
    raise FileExistsError(f"There are already {MOST_NUMBER} reports named {stem} in {folder}.")


def write_new(path: Path, content: bytes) -> None:
    """Write a file that must not be there yet; FileExistsError if it is."""
    with open(path, "xb") as handle:
        handle.write(content)


def _cells(row: dict[str, Any]) -> list[Any]:
    objects = row.get("handles") or row.get("names") or []
    target = row.get("target")
    return [
        row["state"],
        row["severity"],
        row["check"],
        row["label"],
        row.get("source", ""),
        row.get("from", ""),
        ", ".join(f"{k}={v}" for k, v in target.items()) if target else "",
        row["failing"],
        row.get("note", ""),
        row.get("advice", ""),
        ", ".join(str(item) for item in objects),
    ]


def _heading(report: dict[str, Any], drawing: str, when: str) -> list[tuple[str, str]]:
    return [
        ("Check list", str(report["checklist"])),
        ("Drawing", drawing),
        ("Run at", when),
        ("Result", str(report["verdict"])),
        ("Coverage", str(report["coverage"])),
        ("What PASS means", PASS_MEANS),
    ]


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------


def _column(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _cell(ref: str, value: Any, style: int = 0) -> str:
    styled = f' s="{style}"' if style else ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{styled}><v>{value}</v></c>'
    text = escape(str(value))
    # Excel refuses control characters other than tab and new line.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return f'<c r="{ref}" t="inlineStr"{styled}><is><t xml:space="preserve">{text}</t></is></c>'


def workbook(report: dict[str, Any], drawing: str, when: str) -> bytes:
    """The run as a one-sheet .xlsx: the heading, then one row per check."""
    rows: list[list[tuple[Any, int]]] = [[(label, 1), (value, 0)] for label, value in _heading(report, drawing, when)]
    rows.append([])
    rows.append([(name, 1) for name in COLUMNS])
    rows.extend([(value, 0) for value in _cells(result)] for result in report["results"])
    sheet_rows = []
    for number, row in enumerate(rows, 1):
        cells = "".join(_cell(f"{_column(i)}{number}", value, style) for i, (value, style) in enumerate(row))
        sheet_rows.append(f'<row r="{number}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols><col min="1" max="1" width="18" customWidth="1"/><col min="2" max="11" width="22" customWidth="1"/></cols>'
        f"<sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"
    )
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Check list" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/></Relationships>'
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def page(report: dict[str, Any], drawing: str, when: str) -> str:
    """The run as one HTML page that opens in any browser, nothing fetched."""
    heading = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in _heading(report, drawing, when)
    )
    head = "".join(f"<th>{html.escape(name)}</th>" for name in COLUMNS)
    body = []
    for result in report["results"]:
        colour = STATE_COLOURS.get(result["state"], "#ffffff")
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in _cells(result))
        body.append(f'<tr style="background:{colour}">{cells}</tr>')
    title = html.escape(f"{Path(drawing).name} - check list {report['checklist']}")
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title>"
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#222}"
        "table{border-collapse:collapse;margin-bottom:20px}th,td{border:1px solid #bbb;padding:4px 8px;"
        "text-align:left;vertical-align:top}th{background:#f0f0f0}</style></head><body>"
        f"<h1>{title}</h1><table>{heading}</table>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        "<p>Made by Heron AI for AutoCAD. See DISCLAIMER.md in the Heron repository.</p>"
        "</body></html>\n"
    )
