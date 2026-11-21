"""Ask once, remember per project (D-53).

Every new chat asked the scale, the standard and the text heights again. The
modeller's answers are now kept per project, and autocad_status hands them
to the next chat, so it asks only what is not known yet (the idea is Heron AI
for Revit's design basis, its D-33: never fill in a value the user did not
give, and keep each answer per project).

A project is the folder its drawing is saved in. Heron AI's lesson: an id
copied from the template made every new project reuse the first one's
answers. A folder cannot be copied from a template, and two jobs in two
folders never share answers. An unsaved drawing has no folder, so nothing is
kept for it until it is saved.

The notes are Heron's own file on this PC, never written into the drawing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .folders import heron_local

MAX_NOTES = 40
MAX_VALUE = 500
NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def notes_dir() -> Path:
    return heron_local() / "projects"


def project_of(drawing: str) -> str | None:
    """The project a drawing belongs to: its folder, or None when it is not saved."""
    text = (drawing or "").strip()
    if not text or not os.path.isabs(text):
        return None
    return os.path.normcase(os.path.normpath(os.path.dirname(text)))


def _file(project: str) -> Path:
    digest = hashlib.sha256(project.encode("utf-8")).hexdigest()[:16]
    return notes_dir() / f"{digest}.json"


def read(drawing: str) -> dict[str, Any] | None:
    """{project, notes {name: {value, said, at}}} for this drawing's project, or None when unsaved."""
    project = project_of(drawing)
    if project is None:
        return None
    try:
        stored = json.loads(_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if stored.get("project") not in (None, project):
        stored = {}  # a hash clash, however unlikely, never mixes two jobs
    return {"project": project, "notes": dict(stored.get("notes", {}))}


def write(drawing: str, name: str, value: str | None, said: str = "") -> dict[str, Any]:
    """Keep (or with value None forget) one answer. Raises ValueError with the reason."""
    project = project_of(drawing)
    if project is None:
        raise ValueError(
            "This drawing is not saved yet, so Heron does not know which project it belongs to. "
            "Save it in the project folder first; nothing was kept."
        )
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if not NAME.match(key):
        raise ValueError(f"'{name}' cannot be a note name: use a short word such as scale, standard or text_height.")
    current = read(drawing) or {"notes": {}}
    notes = current["notes"]
    if value is None:
        notes.pop(key, None)
    else:
        text = str(value).strip()
        if not text:
            raise ValueError("Give the value to keep, or forget the note instead.")
        if len(text) > MAX_VALUE:
            raise ValueError(f"Keep a note under {MAX_VALUE} characters.")
        if key not in notes and len(notes) >= MAX_NOTES:
            raise ValueError(f"This project already has {MAX_NOTES} notes; forget one first.")
        notes[key] = {"value": text, "said": said.strip()[:300], "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path = _file(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"project": project, "notes": notes}, indent=2), encoding="utf-8")
    os.replace(temp, path)
    return {"project": project, "notes": notes}


def for_status(drawing: str) -> dict[str, str] | None:
    """The answers to hand the next chat: name -> value. None when there is nothing."""
    current = read(drawing)
    if not current or not current["notes"]:
        return None
    return {name: note["value"] for name, note in sorted(current["notes"].items())}
