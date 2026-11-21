r"""Named check lists, saved once and run before every issue (D-52, D-64, D-65).

The checks themselves live in acad/checklist.py (pure, tested offline); this
module keeps the lists on this PC and reads the drawing for them. Reading the
drawing changes nothing, and a list is Heron's own file, never the drawing's,
so autocad_checklist needs no padlock.

Where the lists live (D-64):
  office lists     %LOCALAPPDATA%\Heron\autocad\checklists\<name>.json, one
                   file per list ('save' writes it). An office shares a list by
                   copying that file to each PC. 'before issue' ships with Heron.
  project changes  %LOCALAPPDATA%\Heron\autocad\checklists\projects\<id>.json,
                   one file per project folder (the folder the drawing is saved
                   in, as for the project notes, D-53). Only severity, target and
                   on/off per office check.

autocad_checklist_report saves a run as files next to the drawing, so it is a
Publish tool of its own (D-65): a tool's padlock is a property of the tool,
never of an option the caller passes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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


def lists_dir() -> Path:
    return heron_local() / "checklists"


def _file(name: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise AutocadError("Give the check list a name, e.g. 'before issue' or 'MEP sheets'.")
    return lists_dir() / f"{slug}.json"


def saved_lists() -> list[dict[str, Any]]:
    found = []
    folder = lists_dir()
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            try:
                found.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return found


def load(name: str) -> dict[str, Any]:
    if name.strip().lower() == checklist.STARTER["name"] and not _file(name).is_file():
        return {"name": checklist.STARTER["name"], "checks": checklist.validate(checklist.STARTER["checks"])}
    path = _file(name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        names = [item["name"] for item in saved_lists()] + [checklist.STARTER["name"]]
        raise AutocadError(f"There is no check list called '{name}'. There are: {', '.join(sorted(set(names)))}.") from None
    except ValueError as exc:
        raise AutocadError(f"The check list file {path} could not be read ({exc}).") from None


def save(name: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        clean = checklist.validate(checks)
    except ValueError as exc:
        raise AutocadError(f"{exc} Nothing was saved.") from None
    path = _file(name)
    if not path.is_file() and len(saved_lists()) >= MAX_LISTS:
        raise AutocadError(f"There are already {MAX_LISTS} check lists. Delete one first.")
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"name": name.strip(), "checks": clean}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, indent=2), encoding="utf-8")
    os.replace(temp, path)
    return record


def projects_dir() -> Path:
    return lists_dir() / "projects"


def _project_file(project: str) -> Path:
    return projects_dir() / f"{hashlib.sha256(project.encode('utf-8')).hexdigest()[:16]}.json"


def _list_key(name: str) -> str:
    return _file(name).stem


def project_changes(drawing: str, name: str) -> tuple[str | None, list[dict[str, Any]]]:
    """(the project folder or None when unsaved, this project's changes to the list 'name')."""
    project = project_of(drawing)
    if project is None:
        return None, []
    try:
        stored = json.loads(_project_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return project, []
    if stored.get("project") != project:
        return project, []  # a hash clash never mixes two jobs
    return project, list((stored.get("changes") or {}).get(_list_key(name), []))


def save_project_changes(drawing: str, name: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Check the changes against the office list, then keep them for this project."""
    project = project_of(drawing)
    if project is None:
        raise AutocadError("This drawing is not saved yet, so it has no project folder. Save it first; nothing was kept.")
    office = checklist.validate(load(name).get("checks", []))
    try:
        clean = checklist.validate_changes(office, changes)
    except ValueError as exc:
        raise AutocadError(f"{exc} Nothing was kept.") from None
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
    return {"project": project, "checklist": name, "changes": clean, "file": str(path)}


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


async def run_list(name: str, max_entities: int) -> tuple[dict[str, Any], str]:
    """Run the list 'name' with this project's changes on top. (the answer, the drawing's path)."""
    record = load(name)
    office = checklist.validate(record.get("checks", []))

    def work() -> tuple[str, str | None, list[dict[str, Any]], dict[str, Any]]:
        doc = get_doc()
        drawing = _drawing_of(doc)
        project, changes = project_changes(drawing, record["name"])
        try:
            clean = checklist.validate_changes(office, changes)
        except ValueError as exc:
            raise AutocadError(
                f"This project's changes no longer fit the office list '{record['name']}': {exc} "
                "Set them again with action='project', or clear them with changes=[]."
            ) from None
        used = checklist.layer(office, clean)
        return drawing, project, used, gather(doc, checklist.needs(used), max_entities)

    drawing, project, used, data = await run(work)
    report = checklist.run(record["name"], used, data)
    report["lists"] = {
        "office": "ships with Heron" if not _file(record["name"]).is_file() else str(_file(record["name"])),
        "project": project if any(check["from"] == checklist.PROJECT for check in used) else None,
    }
    if data.get("capped"):
        report["warning"] = f"Only the first {data['capped']} objects were read; raise max_entities to read them all."
    return report, drawing


@mcp.tool(name="autocad_checklist", **tool_meta("Check Lists Before Issue", read_only=True))
@tool_errors
async def autocad_checklist(
    action: Annotated[
        Literal["catalogue", "list", "save", "run", "delete", "project"],
        Field(description=(
            "'catalogue': the checks Heron can do. 'list': the saved check lists, or with 'name' "
            "the checks of one list and their ids. 'save': save 'checks' as the office list 'name'. "
            "'run': run the list 'name' on this drawing. 'delete': remove the list 'name'. "
            "'project': show, or with 'changes' set, this project's changes to the list 'name'."
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
    nothing else (action='project'); each run names every check it used and
    whether it came from the office list or the project's changes.

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
        - Don't use when: a layer table standard with colours and linetypes per
          layer is wanted - autocad_check_standards takes that.

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
    if action == "list" and not name:
        lists = [{"name": item["name"], "checks": len(item.get("checks", []))} for item in saved_lists()]
        return dumps({"lists": lists, "ships_with_heron": checklist.STARTER["name"]})
    if not name:
        raise AutocadError(f"'{action}' needs the check list's name.")
    if action == "list":
        record = load(name)
        office = checklist.validate(record.get("checks", []))
        return dumps({"name": record["name"], "checks": [
            {"id": c["id"], "check": c["check"], "label": c["label"], "severity": c["severity"], "params": c["params"]}
            for c in office]})  # fmt: skip
    if action == "save":
        record = save(name, checks or [])
        return dumps({"saved": record["name"], "checks": len(record["checks"]), "file": str(_file(name)),
                      "ids": [c["id"] for c in record["checks"]]})  # fmt: skip
    if action == "delete":
        path = _file(name)
        if not path.is_file():
            raise AutocadError(f"There is no saved check list called '{name}'.")
        path.unlink()
        return dumps({"deleted": name})
    if action == "project":
        drawing = await run(lambda: _drawing_of(get_doc()))
        if changes is None:
            project, current = project_changes(drawing, load(name)["name"])
            return dumps({"project": project, "checklist": name, "changes": current,
                          "project_may_change": list(checklist.PROJECT_MAY_CHANGE)})  # fmt: skip
        return dumps(save_project_changes(drawing, load(name)["name"], changes))

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
