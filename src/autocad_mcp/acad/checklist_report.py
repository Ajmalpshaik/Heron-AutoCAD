"""A check list run saved as an Excel workbook and an HTML page (D-65).

Pure: it turns the run's answer into file contents and picks file names, so
every rule is tested without AutoCAD. The workbook is written with the
standard library through acad/xlsx.py (an .xlsx is a zip of a few XML
files), so Heron needs no new package for it.

Never overwrite: an earlier report keeps its name. The next one gets a number
(" (2)", " (3)" ...), and the files are opened in exclusive-create mode, so a
file that appeared a moment ago is not replaced either.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from . import xlsx
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


def workbook(report: dict[str, Any], drawing: str, when: str) -> bytes:
    """The run as an .xlsx: a Summary sheet, then one row per check (written by acad/xlsx.py)."""
    summary = [["Item", "Value"], *[[label, value] for label, value in _heading(report, drawing, when)]]
    checks = [list(COLUMNS), *[_cells(result) for result in report["results"]]]
    return xlsx.write([
        ("Summary", summary, [18, 100]),
        ("Check list", checks, [10, 10, 26, 34, 30, 10, 24, 8, 34, 40, 30]),
    ])


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
