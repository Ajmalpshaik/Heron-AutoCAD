"""eTransmit: the files a drawing needs, packed into one folder or a zip (#114, D-85).

Plain functions over paths, tested without AutoCAD. The tool reads what the
drawing refers to (xrefs over COM, images, underlays, fonts and plot styles
from the plug-in, which finds each file the way AutoCAD does), hands it here
as ``Need`` rows, and this module decides what goes where and writes it.

Everything is put in one folder beside the drawing, as eTransmit's "Put all
files in one folder": AutoCAD looks for an xref, an image or a font by its
bare name in the drawing's own folder when the saved path leads nowhere, so
the pack opens on another PC without its paths being rewritten. Two
different files with one name cannot both go in one folder: the second is
listed as a clash, not packed. Plot styles go in a ``PlotStyles`` folder for
the receiver to copy into their own plot styles folder.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLOT_STYLE_FOLDER = "PlotStyles"
KINDS = ("drawing", "xref", "image", "underlay", "font", "plot style")


@dataclass(frozen=True)
class Need:
    kind: str  # one of KINDS
    name: str  # as the drawing names it: a saved path, a font file, a .ctb
    found: str  # the file on this PC, '' when none was found
    used_by: str = ""  # the xref, text style or layout that needs it


def find_file(name: str, folders: Sequence[str]) -> str:
    """The file a name points at: the name itself if it is a whole path that is there, else the bare name in each folder."""
    name = (name or "").strip().strip('"')
    if not name:
        return ""
    if os.path.isabs(name) and os.path.isfile(name):
        return os.path.normpath(name)
    base = os.path.basename(name.replace("\\", os.sep).replace("/", os.sep))
    for folder in folders:
        if not folder:
            continue
        for candidate in (os.path.join(folder, name), os.path.join(folder, base)):
            if os.path.isfile(candidate):
                return os.path.normpath(candidate)
    return ""


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def plan(needs: Iterable[Need]) -> dict[str, Any]:
    """What goes into the pack, what is missing, and what clashes. Writes nothing.

    The drawing comes first and keeps its name; each other file goes in under
    its own file name, once however many times it is used.
    """
    packed: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    clashes: list[dict[str, Any]] = []
    by_source: dict[str, dict[str, Any]] = {}
    by_target: dict[str, str] = {}
    ordered = sorted(needs, key=lambda n: (KINDS.index(n.kind) if n.kind in KINDS else len(KINDS)))
    for need in ordered:
        if not need.found:
            row = {"kind": need.kind, "name": need.name}
            if need.used_by:
                row["used_by"] = need.used_by
            if row not in missing:
                missing.append(row)
            continue
        source = _key(need.found)
        if source in by_source:
            used = by_source[source]
            if need.used_by and need.used_by not in used["used_by"]:
                used["used_by"].append(need.used_by)
            continue
        file_name = os.path.basename(need.found)
        target = f"{PLOT_STYLE_FOLDER}/{file_name}" if need.kind == "plot style" else file_name
        target_key = target.lower()
        if target_key in by_target:
            clashes.append(
                {
                    "kind": need.kind,
                    "name": need.name,
                    "file": need.found,
                    "same_name_as": by_target[target_key],
                    "why": f"another file called {file_name} is already in the pack",
                }
            )
            continue
        row = {"kind": need.kind, "name": need.name, "from": need.found, "to": target,
               "used_by": [need.used_by] if need.used_by else []}
        by_source[source] = row
        by_target[target_key] = need.found
        packed.append(row)
    return {"packed": packed, "missing": missing, "clashes": clashes}


def free_target(folder: Path, stem: str, as_zip: bool) -> Path:
    """A folder (or .zip) name beside the drawing that is not taken: never written over."""
    suffix = ".zip" if as_zip else ""
    first = folder / f"{stem}{suffix}"
    if not first.exists():
        return first
    for n in range(2, 1000):
        candidate = folder / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Too many earlier transmittals called '{stem}' in {folder}.")


def report_text(drawing: str, when: str, result: dict[str, Any]) -> str:
    """The plain-text list packed with the files, as eTransmit's report is."""
    lines = [f"Transmittal of {drawing}", f"Made {when} by Heron AI for AutoCAD.", ""]
    lines.append(f"Packed ({len(result['packed'])}):")
    for row in result["packed"]:
        lines.append(f"  {row['kind']:<10} {row['to']}    from {row['from']}")
    lines.append("")
    lines.append(f"Missing ({len(result['missing'])}): the drawing names these but they were not found on the PC that packed it.")
    for row in result["missing"]:
        used = f"  (used by {row['used_by']})" if row.get("used_by") else ""
        lines.append(f"  {row['kind']:<10} {row['name']}{used}")
    if result["clashes"]:
        lines.append("")
        lines.append(f"Not packed, same file name as another ({len(result['clashes'])}):")
        for row in result["clashes"]:
            lines.append(f"  {row['kind']:<10} {row['file']}")
    lines.append("")
    lines.append(
        "Xrefs, images and fonts are found by AutoCAD in the drawing's own folder. Copy the "
        f"files in {PLOT_STYLE_FOLDER} into your plot styles folder before plotting."
    )
    return "\n".join(lines) + "\n"


REPORT_NAME = "transmittal report.txt"


def write(result: dict[str, Any], target: Path, as_zip: bool, report: str) -> list[str]:
    """Copy (or zip) every packed file and the report into a new target. Returns what was written, in the pack."""
    if target.exists():
        raise FileExistsError(f"{target} is already there; Heron never writes over an earlier transmittal.")
    written: list[str] = []
    if as_zip:
        target.parent.mkdir(parents=True, exist_ok=True)
        # "x" refuses a file that appeared since free_target; only a zip Heron
        # itself began is ever removed when the packing fails.
        pack = zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED)
        try:
            with pack:
                for row in result["packed"]:
                    pack.write(row["from"], row["to"])
                    written.append(row["to"])
                pack.writestr(REPORT_NAME, report)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    else:
        target.mkdir(parents=True)
        for row in result["packed"]:
            destination = target / row["to"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(row["from"], destination)
            written.append(row["to"])
        (target / REPORT_NAME).write_text(report, encoding="utf-8")
    written.append(REPORT_NAME)
    return written
