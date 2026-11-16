"""Named check lists, saved once and run before every issue (D-52).

The checks themselves live in acad/checklist.py (pure, tested offline); this
module keeps the lists on this PC and reads the drawing for them. Reading the
drawing changes nothing, and a list is Heron's own file, never the drawing's,
so the tool needs no padlock.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import checklist
from ..acad.entities import read_attributes
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import describe_layer
from ..core.connection import get_doc, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from .xrefs import _try, _walk, _xref_nodes

MAX_LISTS = 50


def lists_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Heron" / "autocad" / "checklists"


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


@mcp.tool(name="autocad_checklist", **tool_meta("Check Lists Before Issue", read_only=True))
@tool_errors
async def autocad_checklist(
    action: Annotated[
        Literal["catalogue", "list", "save", "run", "delete"],
        Field(description=(
            "'catalogue': the checks Heron can do. 'list': the saved check lists. 'save': save "
            "'checks' as the list 'name'. 'run': run the list 'name' on this drawing. 'delete': "
            "remove the list 'name'."
        )),
    ] = "run",
    name: Annotated[
        str | None,
        Field(description="The check list's name, e.g. 'before issue' (ships with Heron) or the office's own."),
    ] = None,
    checks: Annotated[
        list[dict] | None,
        Field(description=(
            "For save: each check as {check, label, params, severity, clause, advice}. 'check' is a "
            "catalogue key; 'label' is the modeller's own sentence; severity high/medium/low; clause "
            "and advice are what to quote and what to do when it fails."
        )),
    ] = None,
    max_entities: Annotated[int, Field(ge=1, le=200000, description="Stop reading objects after this many.")] = 20000,
) -> str:
    """Run the modeller's own check list on the drawing: PASS, FAIL or NOT RUN for each line.

    The modeller says the checks in their own words ("nothing on layer 0",
    "every A1 title block filled in", "text 2.5, 3.5 or 5 only"); save them
    once as a named list with each sentence mapped to a catalogue check, then
    run the list before every issue. 'before issue' ships ready to run. Each
    failed check names its objects, so autocad_show can put them on screen.
    Running changes nothing in the drawing.

    Catalogue: nothing_on_layer_0, nothing_on_defpoints, bylayer_colour,
    bylayer_linetype, no_overlapping_dimensions, layer_names {pattern},
    xrefs_found, title_block_filled {block}, text_heights {heights}.

    Args:
        action (str): catalogue, list, save, run or delete.
        name (str): the list.
        checks (list[dict]): for save.
        max_entities (int): most objects read.

    Returns:
        str: JSON. run: {"checklist", "verdict", "counts", "results": [{"check",
             "label", "state", "severity", "failing", "handles" | "names",
             "clause", "advice", "note"}]}

    Examples:
        - Use when: "check this drawing before I issue it" -> run 'before issue'.
        - Use when: "save these as our sheet checks: nothing on 0, title blocks
          filled, text 2.5 or 3.5" -> save, then run.
        - Use when: "which of my checks fail?" then autocad_show the handles.
        - Don't use when: the layers should be put right, not reported -
          autocad_remap_layers / autocad_tidy_entities.
        - Don't use when: a layer table standard with colours and linetypes per
          layer is wanted - autocad_check_standards takes that.

    Error Handling:
        - A check that is not in the catalogue, or is missing a parameter, is
          refused when saving, naming the line; nothing is saved.
        - A check that cannot be judged (no such title block, xrefs unreadable)
          is NOT RUN with the reason, never a silent PASS.
    """
    if action == "catalogue":
        return dumps({"checks": checklist.CATALOGUE, "starter": checklist.STARTER})
    if action == "list":
        lists = [{"name": item["name"], "checks": len(item.get("checks", []))} for item in saved_lists()]
        return dumps({"lists": lists, "ships_with_heron": checklist.STARTER["name"]})
    if not name:
        raise AutocadError(f"'{action}' needs the check list's name.")
    if action == "save":
        record = save(name, checks or [])
        return dumps({"saved": record["name"], "checks": len(record["checks"]), "file": str(_file(name))})
    if action == "delete":
        path = _file(name)
        if not path.is_file():
            raise AutocadError(f"There is no saved check list called '{name}'.")
        path.unlink()
        return dumps({"deleted": name})

    record = load(name)
    checks_to_run = checklist.validate(record.get("checks", []))
    wanted = checklist.needs(checks_to_run)

    def work() -> dict[str, Any]:
        return gather(get_doc(), wanted, max_entities)

    data = await run(work)
    report = checklist.run(record["name"], checks_to_run, data)
    if data.get("capped"):
        report["warning"] = f"Only the first {data['capped']} objects were read; raise max_entities to read them all."
    return dumps(report)
