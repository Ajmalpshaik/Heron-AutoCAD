"""Checking a folder of drawings, as plain functions (D-70).

From Heron AI for Revit's accepted idea (its D-181): open each file of a
folder in turn, read only, run the checks, close it unsaved. Which files, in
what order, and how the answers add up are decided here, without AutoCAD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .checklist import FAIL, NO_DATA, NOT_RUN, PASS

MOST_DRAWINGS = 200
WORST_FIRST = (NOT_RUN, FAIL, NO_DATA, PASS)


def drawings_in(folder: Path, subfolders: bool, most: int) -> tuple[list[Path], int]:
    """(the drawings to check, how many more were left out), in name order.

    Only real drawings: '.dwg' in any case. AutoCAD's backups and autosaves
    (.bak, .sv$, .dwl) are not drawings, and a name starting '~' is a file
    being saved.
    """
    found = folder.rglob("*") if subfolders else folder.glob("*")
    drawings = sorted(
        (path for path in found if path.is_file() and path.suffix.lower() == ".dwg" and not path.name.startswith("~")),
        key=lambda path: str(path).lower(),
    )
    return drawings[:most], max(0, len(drawings) - most)


def short(report: dict[str, Any], drawing: str) -> dict[str, Any]:
    """One drawing's line: its verdict, coverage, the checks that did not pass, and any warning.

    The warning is never dropped (D-93): an office folder that could not be
    reached, a copy used, or project changes that differ from this PC's own.
    """
    line = {
        "drawing": drawing,
        "verdict": report["verdict"],
        "coverage": report["coverage"],
        "failed": [
            {"label": r["label"], "failing": r["failing"], "severity": r["severity"]}
            for r in report["results"] if r["state"] == FAIL
        ],
        "no_data": [r["label"] for r in report["results"] if r["state"] == NO_DATA],
    }
    if report.get("warning"):
        line["warning"] = report["warning"]
    project_file = (report.get("lists") or {}).get("project_file")
    if project_file:
        line["project_changes"] = project_file
    return line


def summary(lines: list[dict[str, Any]]) -> dict[str, Any]:
    """How many drawings came out each way, and the lines worst first (then by name)."""
    counts = {state: sum(1 for line in lines if line["verdict"] == state) for state in WORST_FIRST}
    order = {state: i for i, state in enumerate(WORST_FIRST)}
    ordered = sorted(lines, key=lambda line: (order.get(line["verdict"], 0), line["drawing"].lower()))
    worst = next((state for state in WORST_FIRST if counts[state]), PASS)
    return {"verdicts": counts, "worst": worst, "drawings": ordered}
