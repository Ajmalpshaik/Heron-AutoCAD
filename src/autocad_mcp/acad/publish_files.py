"""Which drawings go into one PDF (#67, D-91): a folder of them, or a list.

The plug-in reads each drawing for its layouts and xrefs and publishes them
all into one PDF. What is decided here, without AutoCAD, is the list itself:
only .dwg files that are there, each once, a folder in the order a drafter
reads it (M-2 before M-10), and which of them are open in AutoCAD with
changes not saved, because the PDF is made from the saved file.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

MOST_DRAWINGS = 300
_DIGITS = re.compile(r"(\d+)")


def natural_key(text: str) -> list[object]:
    """Sort key that reads numbers as numbers: 'M-2' before 'M-10'."""
    return [int(part) if part.isdigit() else part.lower() for part in _DIGITS.split(text)]


def _plain(path: str) -> str:
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(path).strip().strip('"').strip("'"))))


def _key(path: str) -> str:
    # Windows paths ignore case, and this server runs on Windows beside AutoCAD.
    return os.path.normcase(os.path.normpath(path)).lower()


def pdf_drawings(
    folder: str | None = None,
    drawings: Sequence[str] | None = None,
    recursive: bool = False,
) -> list[str]:
    """The drawings for one PDF, as full paths in publishing order.

    Give a folder (every .dwg in it, sorted by name the way a drafter reads
    it; ``recursive`` takes the sub-folders too) or a list of drawings (in the
    order given). A file that is not there, or not a .dwg, is refused by name
    rather than left out of the set without a word.
    """
    if folder and drawings:
        raise ValueError("give a folder or a list of drawings, not both")
    if not folder and not drawings:
        raise ValueError("give a folder of drawings or a list of drawing paths")

    found: list[str] = []
    if folder:
        root = Path(_plain(folder))
        if not root.is_dir():
            raise ValueError(f"the folder '{root}' does not exist")
        candidates: Iterable[Path] = root.rglob("*") if recursive else root.iterdir()
        dwgs = [p for p in candidates if p.is_file() and p.suffix.lower() == ".dwg"]
        dwgs.sort(key=lambda p: natural_key(str(p.relative_to(root))))
        found = [str(p) for p in dwgs]
        if not found:
            where = "or its sub-folders " if recursive else ""
            raise ValueError(f"the folder '{root}' {where}has no .dwg files")
    else:
        problems = []
        for given in drawings or ():
            if not str(given or "").strip():
                continue
            path = _plain(given)
            if not path.lower().endswith(".dwg"):
                problems.append(f"'{path}' is not a .dwg")
            elif not os.path.isfile(path):
                problems.append(f"'{path}' is not there")
            else:
                found.append(path)
        if problems:
            raise ValueError("; ".join(problems))
        if not found:
            raise ValueError("the list of drawings is empty")

    unique: dict[str, str] = {}
    for path in found:
        unique.setdefault(_key(path), path)
    out = list(unique.values())
    if len(out) > MOST_DRAWINGS:
        raise ValueError(f"one PDF takes at most {MOST_DRAWINGS} drawings; that is {len(out)}. Split the set.")
    return out


def unsaved_among(paths: Sequence[str], open_drawings: Iterable[tuple[str, bool]]) -> list[str]:
    """The drawings of the set that are open in AutoCAD with changes not saved.

    ``open_drawings`` is (full path, saved) for each drawing AutoCAD has open;
    one never saved has no path and cannot be in the set.
    """
    unsaved = {_key(full) for full, saved in open_drawings if full and not saved}
    return [path for path in paths if _key(path) in unsaved]
