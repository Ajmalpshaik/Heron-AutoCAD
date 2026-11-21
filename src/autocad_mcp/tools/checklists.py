r"""Named check lists, saved once and run before every issue (D-52, D-64, D-65, D-93).

The checks themselves live in acad/checklist.py (pure, tested offline); this
module finds the lists and reads the drawing for them. Reading the drawing
changes nothing, and everything this module writes is Heron's own file in
Heron's own folder, never the drawing's, so autocad_checklist needs no padlock.

Where the lists live (D-64, D-93):
  office lists     the office folder, when one is set on this PC
                   (action='office_folder': a shared drive, e.g. S:\CAD\Heron),
                   one <name>.json per list. Each time one is read, a copy is
                   kept in %LOCALAPPDATA%\Heron\autocad\checklists\office-copies\;
                   when the folder cannot be reached, a run says so plainly and
                   uses that copy, with the date it was read. It never runs a list
                   it could not read.
  this PC's lists  %LOCALAPPDATA%\Heron\autocad\checklists\<name>.json ('save'
                   writes it); used when no office folder is set, or it has no
                   list of that name. 'before issue' ships with Heron.
  project changes  '<the drawing's folder>\Heron check list changes.json' when
                   the team keeps them with the project (autocad_share_checklist
                   writes it); else this PC's own, in
                   %LOCALAPPDATA%\Heron\autocad\checklists\projects\<id>.json, one
                   file per project folder (D-53). Only severity, target and
                   on/off per office check. The project folder's file wins.

Writing into the office folder or the project folder writes outside Heron's
own folder, where the team reads, so that is autocad_share_checklist, a
Publish tool (tools/checklist_share.py), as autocad_checklist_report is
(D-65): a tool's padlock is a property of the tool, never of an option.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import checklist, checklist_report
from ..acad.entities import read_attributes
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import describe_layer
from ..core.connection import get_doc, run
from ..core.errors import AutocadError
from ..core.folders import heron_local
from ..core.project_notes import project_of
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from .xrefs import _try, _walk, _xref_nodes

MAX_LISTS = 50
OFFICE_SETTING = "checklist-office-folder.json"
PROJECT_FILE = "Heron check list changes.json"
OFFICE_WAIT = 10.0  # seconds to wait for a network folder before calling it unreachable
UNREACHABLE_FOR = 60.0  # and how long to believe it, so a folder check does not wait per drawing
OFFICE_FOLDER, OFFICE_COPY, THIS_PC, SHIPS = "office folder", "this PC's copy of the office list", "this PC", "ships with Heron"
_unreachable: dict[str, float] = {}


def lists_dir() -> Path:
    return heron_local() / "checklists"


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    if not slug:
        raise AutocadError("Give the check list a name, e.g. 'before issue' or 'MEP sheets'.")
    return slug


def _file(name: str) -> Path:
    """This PC's own list of that name."""
    return lists_dir() / f"{_slug(name)}.json"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---- the office folder ------------------------------------------------------


def office_setting() -> Path:
    return heron_local() / OFFICE_SETTING


def copies_dir() -> Path:
    return lists_dir() / "office-copies"


def office_folder() -> Path | None:
    """The office folder set on this PC, or None."""
    try:
        data = json.loads(office_setting().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    folder = str(data.get("folder") or "").strip() if isinstance(data, dict) else ""
    return Path(folder) if folder else None


def reachable(folder: Path, wait: float = OFFICE_WAIT) -> bool:
    """True when the folder answers within ``wait`` seconds. A lost network drive can hang for a minute."""
    key = str(folder)
    if time.monotonic() - _unreachable.get(key, -UNREACHABLE_FOR) < UNREACHABLE_FOR:
        return False
    answer: dict[str, bool] = {}

    def look() -> None:
        try:
            answer["ok"] = folder.is_dir()
        except OSError:
            answer["ok"] = False

    probe = threading.Thread(target=look, daemon=True)
    probe.start()
    probe.join(wait)
    if answer.get("ok"):
        _unreachable.pop(key, None)
        return True
    _unreachable[key] = time.monotonic()
    return False


def set_office_folder(text: str) -> dict[str, Any]:
    """Keep the office folder for this PC; '' clears it. The folder must answer now."""
    cleaned = os.path.expandvars(os.path.expanduser(str(text or "").strip().strip('"')))
    setting = office_setting()
    if not cleaned:
        setting.unlink(missing_ok=True)
        return {"office_folder": None, "lists": "this PC's own lists only, as before"}
    folder = Path(cleaned)
    if not folder.is_absolute():
        raise AutocadError(f"Give the office folder's full path, e.g. S:\\CAD\\Heron: {folder} is not one. Nothing was kept.")
    _unreachable.pop(str(folder), None)
    if not reachable(folder):
        raise AutocadError(f"{folder} could not be reached from this PC, or is not a folder. Nothing was kept.")
    setting.parent.mkdir(parents=True, exist_ok=True)
    temp = setting.with_suffix(".tmp")
    temp.write_text(json.dumps({"folder": str(folder), "set": now()}, indent=2), encoding="utf-8")
    os.replace(temp, setting)
    there = sorted(p.stem for p in folder.glob("*.json"))
    return {"office_folder": str(folder), "lists_there": there,
            "lists": "the office folder's lists first; this PC's own when it has none of that name"}  # fmt: skip


def _read_record(path: Path) -> dict[str, Any]:
    """A saved list, or ValueError / OSError: never a list Heron could not read."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list):
        raise ValueError("it holds no list of checks")
    checklist.validate(data["checks"])
    data.setdefault("name", path.stem)
    return data


def _keep_copy(slug: str, record: dict[str, Any], source: Path) -> None:
    """This PC's copy of an office list, for when the office folder cannot be reached."""
    try:
        copies_dir().mkdir(parents=True, exist_ok=True)
        path = copies_dir() / f"{slug}.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"record": record, "from": str(source), "read": now()}, indent=2), encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        pass  # a copy not kept is no reason to stop a run


def _same_folder(a: Any, b: Any) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _copy(slug: str, folder: Path) -> dict[str, Any] | None:
    """This PC's copy of the office list, only if it was read from this office folder.

    A copy kept from an office folder set before is another office's list: never run as this one's.
    """
    path = copies_dir() / f"{slug}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data["record"]
        checklist.validate(record["checks"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not data.get("from") or not _same_folder(os.path.dirname(str(data["from"])), folder):
        return None
    return {"record": record, "where": OFFICE_COPY, "file": str(path), "read": data.get("read", "an unknown date"),
            "from_file": data.get("from")}  # fmt: skip


def find(name: str) -> dict[str, Any]:
    """Where the list 'name' comes from: {"record", "where", "file", "warning"}.

    The office folder first, when set; when it cannot be reached (or its file
    cannot be read), this PC's copy of the office list, saying so; then this
    PC's own list; then 'before issue', which ships with Heron. A list Heron
    could not read is never run.
    """
    slug = _slug(name)
    folder = office_folder()
    warning = None
    if folder is not None:
        trouble, office_has_it = None, False
        if not reachable(folder):
            trouble = f"The office folder {folder} could not be reached."
        else:
            shared = folder / f"{slug}.json"
            if shared.is_file():
                office_has_it = True
                try:
                    record = _read_record(shared)
                except (OSError, ValueError) as exc:
                    trouble = f"The office list {shared} could not be read ({exc})."
                else:
                    _keep_copy(slug, record, shared)
                    return {"record": record, "where": OFFICE_FOLDER, "file": str(shared), "warning": None}
        if trouble:
            copy = _copy(slug, folder)
            if copy:
                copy["warning"] = (f"{trouble} This run used this PC's copy of the office list '{name}', "
                                   f"read from {copy['from_file']} on {copy['read']}.")  # fmt: skip
                return copy
            if office_has_it:
                # The office has its own list of that name: never run another one in its place.
                raise AutocadError(f"{trouble} This PC has no copy of it, so nothing was run. Put the file right in "
                                   "the office folder (or ask whoever keeps the office's lists).")  # fmt: skip
            warning = f"{trouble} This PC has no copy of an office list '{name}'."
    local = _file(name)
    if local.is_file():
        try:
            record = _read_record(local)
        except (OSError, ValueError) as exc:
            raise AutocadError(f"The check list file {local} could not be read ({exc}). Nothing was run.") from None
        return {"record": record, "where": THIS_PC, "file": str(local),
                "warning": f"{warning} This PC's own list of that name was used." if warning else None}  # fmt: skip
    if slug == _slug(checklist.STARTER["name"]):
        return {"record": {"name": checklist.STARTER["name"], "checks": checklist.validate(checklist.STARTER["checks"])},
                "where": SHIPS, "file": None,
                "warning": f"{warning} The 'before issue' list that ships with Heron was used." if warning else None}  # fmt: skip
    names = [item["name"] for item in all_lists()["lists"]] + [checklist.STARTER["name"]]
    raise AutocadError(
        (f"{warning} So nothing was run. " if warning else "")
        + f"There is no check list called '{name}'. There are: {', '.join(sorted(set(names), key=str.lower))}."
    )


def load(name: str) -> dict[str, Any]:
    return find(name)["record"]


def saved_lists() -> list[dict[str, Any]]:
    """This PC's own lists."""
    found = []
    folder = lists_dir()
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                found.append(_read_record(path))
            except (OSError, ValueError):
                continue
    return found


def all_lists() -> dict[str, Any]:
    """Every list a run can use, and where each lives."""
    rows: dict[str, dict[str, Any]] = {}
    answer: dict[str, Any] = {"office_folder": None}
    folder = office_folder()
    if folder is not None:
        answer["office_folder"] = str(folder)
        if reachable(folder):
            for path in sorted(folder.glob("*.json")):
                try:
                    record = _read_record(path)
                except (OSError, ValueError):
                    rows.setdefault(path.stem, {"name": path.stem, "where": OFFICE_FOLDER, "file": str(path),
                                                "warning": "this file could not be read"})  # fmt: skip
                    continue
                rows[path.stem] = {"name": record["name"], "checks": len(record["checks"]), "where": OFFICE_FOLDER,
                                   "file": str(path)}  # fmt: skip
        else:
            answer["warning"] = f"The office folder {folder} could not be reached: the office lists below are this PC's copies."
            for path in sorted(copies_dir().glob("*.json")) if copies_dir().is_dir() else []:
                copy = _copy(path.stem, folder)
                if copy:
                    rows[path.stem] = {"name": copy["record"]["name"], "checks": len(copy["record"]["checks"]),
                                       "where": OFFICE_COPY, "file": copy["file"], "read": copy["read"]}  # fmt: skip
    for record in saved_lists():
        slug = _slug(record["name"])
        if slug not in rows:
            rows[slug] = {"name": record["name"], "checks": len(record["checks"]), "where": THIS_PC, "file": str(_file(record["name"]))}
    answer["lists"] = sorted(rows.values(), key=lambda r: str(r["name"]).lower())
    return answer


def save(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Save the list on this PC. Refused when the office folder has a list of that name."""
    try:
        clean = checklist.validate(checks)
    except ValueError as exc:
        raise AutocadError(f"{exc} Nothing was saved.") from None
    folder = office_folder()
    if folder is not None and reachable(folder) and (folder / f"{_slug(name)}.json").is_file():
        raise AutocadError(
            f"The office folder {folder} already has a list called '{name}', and that one is what every run "
            "uses. Change the office list with autocad_share_checklist (Publish padlock), or save yours under "
            "another name. Nothing was saved."
        )
    path = _file(name)
    if not path.is_file() and len(saved_lists()) >= MAX_LISTS:
        raise AutocadError(f"There are already {MAX_LISTS} check lists. Delete one first.")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"name": name.strip(), "checks": clean}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.replace(temp, path)
    return record


# ---- project changes --------------------------------------------------------


def projects_dir() -> Path:
    return lists_dir() / "projects"


def _project_file(project: str) -> Path:
    return projects_dir() / f"{hashlib.sha256(project.encode('utf-8')).hexdigest()[:16]}.json"


def _list_key(name: str) -> str:
    return _slug(name)


def shared_project_file(drawing: str) -> Path | None:
    """'<the drawing's folder>\\Heron check list changes.json', or None for an unsaved drawing."""
    if project_of(drawing) is None:
        return None
    return Path(os.path.dirname(drawing.strip())) / PROJECT_FILE


def read_shared_project(path: Path) -> dict[str, Any]:
    """The team's file of project changes, or AutocadError naming it: never half read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("changes", {}), dict):
            raise ValueError("it holds no changes")
    except (OSError, ValueError) as exc:
        raise AutocadError(
            f"This project's shared check list changes, {path}, could not be read ({exc}). Nothing was run: "
            "Heron never runs a list with changes it could not read. Put the file right, or remove it."
        ) from None
    return data


def _own_project_changes(project: str, name: str) -> list[dict[str, Any]]:
    try:
        stored = json.loads(_project_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if stored.get("project") != project:
        return []  # a hash clash never mixes two jobs
    return list((stored.get("changes") or {}).get(_list_key(name), []))


def project_changes(drawing: str, name: str) -> dict[str, Any]:
    """This project's changes to the list 'name': {"project", "changes", "file", "from", "warning"}.

    The project folder's file first (the team's); else this PC's own. None for
    "project" when the drawing is not saved.
    """
    project = project_of(drawing)
    if project is None:
        return {"project": None, "changes": [], "file": None, "from": None}
    own = _own_project_changes(project, name)
    shared = shared_project_file(drawing)
    if shared is not None and shared.is_file():
        entry = read_shared_project(shared).get("changes", {}).get(_list_key(name))
        if entry is not None:
            answer = {"project": project, "changes": list(entry), "file": str(shared), "from": "the project folder"}
            if own and own != list(entry):
                answer["warning"] = (f"This PC keeps its own changes to '{name}' for this project too, and they "
                                     f"differ; the project folder's file {shared} was used (the team's).")  # fmt: skip
            return answer
    return {"project": project, "changes": own, "file": str(_project_file(project)) if own else None,
            "from": "this PC" if own else None}  # fmt: skip


def save_project_changes(drawing: str, name: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Check the changes against the office list, then keep them for this project on this PC."""
    project = project_of(drawing)
    if project is None:
        raise AutocadError("This drawing is not saved yet, so it has no project folder. Save it first; nothing was kept.")
    office = checklist.validate(load(name).get("checks", []))
    try:
        clean = checklist.validate_changes(office, changes)
    except ValueError as exc:
        raise AutocadError(f"{exc} Nothing was kept.") from None
    shared = shared_project_file(drawing)
    if shared is not None and shared.is_file() and _list_key(name) in read_shared_project(shared).get("changes", {}):
        raise AutocadError(
            f"This project's changes to '{name}' are kept with the project, in {shared}, for the whole team, "
            "and that file is what every run uses. Change them there with "
            "autocad_share_checklist(share='project_changes', replace=true) (Publish padlock). Nothing was kept."
        )
    path = _project_file(project)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if stored.get("project") != project:
        stored = {"project": project, "changes": {}}
    stored.setdefault("changes", {})
    if clean:
        stored["changes"][_list_key(name)] = clean
    else:
        stored["changes"].pop(_list_key(name), None)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(stored, indent=2), encoding="utf-8")
    os.replace(temp, path)
    return {"project": project, "checklist": name, "changes": clean, "file": str(path), "where": THIS_PC}


def _drawing_of(doc: Any) -> str:
    return str(_try(lambda: doc.FullName, "") or "")


def gather(doc: Any, wanted: set[str], max_entities: int) -> dict[str, Any]:
    """Read what the checks need from the drawing, once. Changes nothing."""
    data: dict[str, Any] = {"layers": [describe_layer(doc.Layers.Item(i)) for i in range(doc.Layers.Count)]}
    if "xrefs" in wanted:
        try:
            folder = str(_try(lambda: doc.Path, "") or "")
            tree = _xref_nodes(doc.Blocks, folder, 1, {str(_try(lambda: doc.FullName, "")).lower()})
            data["xrefs_broken"] = sorted({n["name"] for n in _walk(tree) if n["status"] == "not found"}, key=str.lower)
        except BaseException:  # noqa: BLE001 - that one check says NOT RUN
            data["xrefs_broken"] = None
    if "entities" in wanted or "blocks" in wanted:
        entities: list[dict[str, Any]] = []
        blocks: list[dict[str, Any]] = []
        capped = False
        sel = select_filtered(doc)
        try:
            for entity in iter_selection(sel):
                if len(entities) >= max_entities:
                    capped = True
                    break
                kind = str(entity.ObjectName)
                row: dict[str, Any] = {
                    "handle": str(entity.Handle),
                    "type": kind,
                    "layer": str(entity.Layer),
                    "color": int(entity.Color),
                    "linetype": str(entity.Linetype),
                }
                if "Dimension" in kind:
                    try:
                        lo, hi = entity.GetBoundingBox()
                        row["box"] = (lo[0], lo[1], hi[0], hi[1])
                    except BaseException:  # noqa: BLE001
                        pass
                if kind in ("AcDbText", "AcDbMText"):
                    try:
                        row["height"] = float(entity.Height)
                    except BaseException:  # noqa: BLE001
                        pass
                if kind == "AcDbBlockReference" and "blocks" in wanted:
                    name = str(_try(lambda e=entity: e.EffectiveName, "") or _try(lambda e=entity: e.Name, ""))
                    blocks.append({"handle": row["handle"], "name": name, "attributes": read_attributes(entity)})
                entities.append(row)
        finally:
            discard_selection_set(doc)
        data["entities"] = entities
        data["blocks"] = blocks
        if capped:
            data["capped"] = max_entities
    return data


async def run_list(name: str, max_entities: int, doc_of: Any = None) -> tuple[dict[str, Any], str]:
    """Run the list 'name' with this project's changes on top. (the answer, the drawing's path).

    doc_of: which open drawing to read (a function giving it); the active one by
    default. autocad_check_folder passes each drawing it opened (D-70). The
    answer names the file every check came from (D-93).
    """
    found = await asyncio.to_thread(find, name)  # a network folder can be slow to answer
    record = found["record"]
    office = checklist.validate(record.get("checks", []))
    pick = doc_of or get_doc

    def work() -> tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        doc = pick()
        drawing = _drawing_of(doc)
        info = project_changes(drawing, record["name"])
        try:
            clean = checklist.validate_changes(office, info["changes"])
        except ValueError as exc:
            how = (
                "Set them again with autocad_share_checklist(share='project_changes', replace=true), or clear "
                "them there with changes=[]."
                if info["from"] == "the project folder"
                else "Set them again with action='project', or clear them with changes=[]."
            )
            raise AutocadError(f"This project's changes no longer fit the office list '{record['name']}': {exc} {how}") from None
        used = checklist.layer(office, clean)
        return drawing, info, used, gather(doc, checklist.needs(used), max_entities)

    drawing, info, used, data = await run(work)
    report = checklist.run(record["name"], used, data)
    changed = any(check["from"] == checklist.PROJECT for check in used)
    office_file = found["file"] or SHIPS
    report["lists"] = {
        "office": office_file,
        "office_from": found["where"],
        "project": info["project"] if changed else None,
        "project_file": info["file"] if changed else None,
        "project_from": info["from"] if changed else None,
    }
    for row in report["results"]:
        row["file"] = info["file"] if row["from"] == checklist.PROJECT else office_file
    warnings = [w for w in (found.get("warning"), info.get("warning")) if w]
    if data.get("capped"):
        warnings.append(f"Only the first {data['capped']} objects were read; raise max_entities to read them all.")
    if warnings:
        report["warning"] = " ".join(warnings)
    return report, drawing


@mcp.tool(name="autocad_checklist", **tool_meta("Check Lists Before Issue", read_only=True))
@tool_errors
async def autocad_checklist(
    action: Annotated[
        Literal["catalogue", "list", "save", "run", "delete", "project", "office_folder"],
        Field(description=(
            "'catalogue': the checks Heron can do. 'list': the check lists and where each lives, or "
            "with 'name' the checks of one list and their ids. 'save': save 'checks' as the list "
            "'name' on this PC. 'run': run the list 'name' on this drawing. 'delete': remove this "
            "PC's list 'name'. 'project': show, or with 'changes' set, this project's changes to "
            "the list 'name'. 'office_folder': show, or with 'folder' set, the office folder this "
            "PC reads the office lists from."
        )),
    ] = "run",
    name: Annotated[
        str | None,
        Field(description="The check list's name, e.g. 'before issue' (ships with Heron) or the office's own."),
    ] = None,
    checks: Annotated[
        list[dict] | None,
        Field(description=(
            "For save: each check as {check, id, label, params, severity, clause, advice}. 'check' is a "
            "catalogue key; 'id' names it for project changes (default: the key); 'label' is the "
            "modeller's own sentence; severity high/medium/low; clause is the source the check "
            "measures against; advice is what to do when it fails."
        )),
    ] = None,
    changes: Annotated[
        list[dict] | None,
        Field(description=(
            "For project: each change as {id, severity, target, on}. 'id' is an office check's id; "
            "'target' gives new values for that check's own params (e.g. {'heights': [2.5, 3.5]}); "
            "'on': false switches it off for this project. Nothing else is allowed. [] clears them."
        )),
    ] = None,
    folder: Annotated[
        str | None,
        Field(description=(
            "For office_folder: the shared folder the office's lists live in, e.g. 'S:\\CAD\\Heron' "
            "(set once per PC); '' clears it."
        )),
    ] = None,
    max_entities: Annotated[int, Field(ge=1, le=200000, description="Stop reading objects after this many.")] = 20000,
) -> str:
    """Run the modeller's own check list on the drawing: PASS, FAIL, NO DATA or NOT RUN for each line.

    The modeller says the checks in their own words ("nothing on layer 0",
    "every A1 title block filled in", "text 2.5, 3.5 or 5 only"); save them
    once as a named office list with each sentence mapped to a catalogue
    check, then run the list before every issue. 'before issue' ships ready to
    run. Each failed check names its objects, so autocad_show can put them on
    screen. Running changes nothing in the drawing.

    PASS means the checked value is met, for what Heron read, against the
    source named on the line (the clause, or the list). It never means the
    drawing complies with a code or standard: Heron does not sign drawings
    off, and the answer must not say so. NO DATA means Heron could not decide
    (the data is missing) and is never counted as a PASS. NOT RUN means the
    project switched the check off. Every run gives a coverage line, e.g.
    "2 of 4 decided, 1 no data, 1 not run": say it with the verdict.

    A project may change an office check's severity, target and on/off, and
    nothing else (action='project'); each run names every check it used,
    whether it came from the office list or the project's changes, and the
    file it was read from.

    Shared with the team (D-93): action='office_folder' names a shared folder
    (a network drive) once per PC; runs then read the office lists from it.
    If it cannot be reached, the run says so plainly and uses this PC's copy
    of the list, with the date it was read; a list Heron could not read is
    never run. A project's changes kept in the project folder (written by
    autocad_share_checklist) are the whole team's and win over this PC's own.
    Putting a list or changes there is autocad_share_checklist (Publish
    padlock): it never overwrites a teammate's file silently.

    Catalogue: nothing_on_layer_0, nothing_on_defpoints, bylayer_colour,
    bylayer_linetype, no_overlapping_dimensions, layer_names {pattern},
    xrefs_found, title_block_filled {block}, text_heights {heights}.

    Args:
        action (str): catalogue, list, save, run, delete or project.
        name (str): the list.
        checks (list[dict]): for save.
        changes (list[dict]): for project.
        max_entities (int): most objects read.

    Returns:
        str: JSON. run: {"checklist", "verdict", "coverage", "counts",
             "pass_means", "lists" {"office", "project"}, "checks_used"
             [{"id", "label", "from"}], "results": [{"id", "check", "label",
             "state", "severity", "source", "from", "target",
             "project_changed", "failing", "handles" | "names", "clause",
             "advice", "note"}]}

    Examples:
        - Use when: "check this drawing before I issue it" -> run 'before issue'.
        - Use when: "save these as our sheet checks: nothing on 0, title blocks
          filled, text 2.5 or 3.5" -> save, then run.
        - Use when: "on this job colours ByLayer is only low, and we don't
          check xrefs" -> project with changes [{id: bylayer_colour, severity:
          low}, {id: xrefs_found, on: false}].
        - Use when: "which of my checks failed?" then autocad_show the handles.
        - Use when: "run our office check list".
        - Don't use when: the run should be saved as Excel and HTML to send
          with the drawings - autocad_checklist_report.
        - Don't use when: the layers should be put right, not reported -
          autocad_remap_layers / autocad_tidy_entities.
        - Use when: "our check lists are on S:\\CAD\\Heron" -> office_folder with
          folder='S:\\CAD\\Heron', once on each PC.
        - Don't use when: a layer table standard with colours and linetypes per
          layer is wanted - autocad_check_standards takes that.
        - Don't use when: the list or this project's changes should go to the
          office folder or the project folder for the team -
          autocad_share_checklist.

    Error Handling:
        - A check that is not in the catalogue, or is missing a parameter, is
          refused when saving, naming the line; nothing is saved.
        - A project change that adds a check, or changes anything but
          severity, target or on, is refused naming the line; nothing is kept.
        - A check that cannot be decided (no such title block, xrefs
          unreadable, only part of the objects read) is NO DATA with the
          reason, never a silent PASS.
    """
    if action == "catalogue":
        return dumps({"checks": checklist.CATALOGUE, "starter": checklist.STARTER,
                      "project_may_change": list(checklist.PROJECT_MAY_CHANGE)})  # fmt: skip
    if action == "office_folder":
        if folder is None:
            where = office_folder()
            shown: dict[str, Any] = {"office_folder": str(where) if where else None}
            if where is not None:
                shown["reachable"] = await asyncio.to_thread(reachable, where)
            shown["how"] = "Set it with folder='S:\\...'; folder='' clears it. Lists are put there with autocad_share_checklist."
            return dumps(shown)
        return dumps(await asyncio.to_thread(set_office_folder, folder))
    if action == "list" and not name:
        listed = await asyncio.to_thread(all_lists)
        rows = [{"name": row["name"], "checks": row.get("checks", 0)} for row in listed["lists"]]
        where = {row["name"]: {k: v for k, v in row.items() if k not in ("name", "checks")} for row in listed["lists"]}
        shown = {"lists": rows, "where": where, "office_folder": listed["office_folder"],
                 "ships_with_heron": checklist.STARTER["name"]}  # fmt: skip
        if listed.get("warning"):
            shown["warning"] = listed["warning"]
        return dumps(shown)
    if not name:
        raise AutocadError(f"'{action}' needs the check list's name.")
    if action == "list":
        found = await asyncio.to_thread(find, name)
        office = checklist.validate(found["record"].get("checks", []))
        shown = {"name": found["record"]["name"], "where": found["where"], "file": found["file"] or SHIPS, "checks": [
            {"id": c["id"], "check": c["check"], "label": c["label"], "severity": c["severity"], "params": c["params"]}
            for c in office]}  # fmt: skip
        if found.get("warning"):
            shown["warning"] = found["warning"]
        return dumps(shown)
    if action == "save":
        record = await asyncio.to_thread(save, name, checks or [])
        return dumps({"saved": record["name"], "checks": len(record["checks"]), "file": str(_file(name)),
                      "where": THIS_PC, "ids": [c["id"] for c in record["checks"]],
                      "share": "autocad_share_checklist(share='office_list') puts it in the office folder for the team."})  # fmt: skip
    if action == "delete":
        path = _file(name)
        if not path.is_file():
            raise AutocadError(
                f"This PC has no saved check list called '{name}'. A list in the office folder is removed there, "
                "by whoever keeps the office's lists; Heron does not delete it."
            )
        path.unlink()
        return dumps({"deleted": name, "where": THIS_PC})
    if action == "project":
        drawing = await run(lambda: _drawing_of(get_doc()))
        record = await asyncio.to_thread(load, name)  # the office folder and the project folder can be slow
        if changes is None:
            info = await asyncio.to_thread(project_changes, drawing, record["name"])
            return dumps({"project": info["project"], "checklist": name, "changes": info["changes"],
                          "file": info["file"], "from": info["from"], **({"warning": info["warning"]} if info.get("warning") else {}),
                          "project_may_change": list(checklist.PROJECT_MAY_CHANGE)})  # fmt: skip
        return dumps(await asyncio.to_thread(save_project_changes, drawing, record["name"], changes))

    report, _drawing = await run_list(name, max_entities)
    report["save_report"] = "autocad_checklist_report saves this run as Excel and HTML next to the drawing (Publish padlock)."
    return dumps(report)


@mcp.tool(name="autocad_checklist_report", **tool_meta("Save A Check List Report"))
@tool_errors
async def autocad_checklist_report(
    name: Annotated[
        str,
        Field(description="The check list to run and save, e.g. 'before issue'."),
    ] = checklist.STARTER["name"],
    max_entities: Annotated[int, Field(ge=1, le=200000, description="Stop reading objects after this many.")] = 20000,
) -> str:
    """Save a check list result as a new Excel workbook and HTML page next to the drawing.

    The same run as autocad_checklist (office list plus this project's
    changes), saved as '<drawing> - checklist <list> - <date>.xlsx' and
    '.html' in the drawing's own folder, to send with the drawings or keep
    with an issue. An earlier report is never overwritten: the next one gets a
    number, ' (2)', ' (3)'. Writing files needs the Publish padlock; the
    drawing itself is not changed.

    The files say what PASS means: the checked value is met against the
    source named on the line. They are not a certificate that the drawing
    complies with anything, and the answer must not say so.

    Args:
        name (str): the check list.
        max_entities (int): most objects read.

    Returns:
        str: JSON: {"saved" {"xlsx", "html"}, "verdict", "coverage",
             "pass_means", "checklist"}

    Examples:
        - Use when: "save the check list results so I can send them with the
          drawings" -> report 'before issue'.
        - Use when: "make an Excel of the checks for this issue".
        - Don't use when: the modeller only wants to see the results in the
          chat - autocad_checklist(action='run') changes and writes nothing.

    Error Handling:
        - An unsaved drawing has no folder: it says to save it first, and
          writes nothing.
        - A file that appeared between choosing the name and writing it is
          never replaced: the call stops and says so.
    """
    report, drawing = await run_list(name, max_entities)
    if not drawing or not os.path.isabs(drawing):
        raise AutocadError("This drawing is not saved yet, so there is no folder to put the report in. Save it first; nothing was written.")
    folder = Path(drawing).parent
    now = datetime.now()
    stem = checklist_report.stem_for(drawing, report["checklist"], now.strftime("%Y-%m-%d"))
    try:
        xlsx, page = checklist_report.free_names(folder, stem)
    except FileExistsError as exc:
        raise AutocadError(f"{exc} Move some of them; nothing was written.") from None
    when = now.strftime("%Y-%m-%d %H:%M")
    try:
        checklist_report.write_new(xlsx, checklist_report.workbook(report, drawing, when))
        try:
            checklist_report.write_new(page, checklist_report.page(report, drawing, when).encode("utf-8"))
        except OSError:
            xlsx.unlink(missing_ok=True)  # the workbook this call just made; never a half report
            raise
    except FileExistsError as exc:
        raise AutocadError(f"{exc.filename} appeared while the report was written; it was not replaced. Run it again.") from None
    except OSError as exc:
        raise AutocadError(f"The report could not be written in {folder} ({exc}). Check the folder is not read-only.") from None
    return dumps({"saved": {"xlsx": str(xlsx), "html": str(page)}, "checklist": report["checklist"],
                  "verdict": report["verdict"], "coverage": report["coverage"],
                  "pass_means": checklist.PASS_MEANS})  # fmt: skip
