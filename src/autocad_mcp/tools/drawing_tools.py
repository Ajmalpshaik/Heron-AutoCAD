"""Bring standards in from another drawing, and work with layouts.

Ideas from Lee Mac's Steal from Drawing, Import Block, TabSort, Renumber
Layouts and Copy to Layouts (lee-mac.com). Heron's own code: none of his is
used (D-26). Name picking and the layout plans are plain functions, tested
without AutoCAD.
"""

from __future__ import annotations

import fnmatch
import os
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.entities import resolve_handles
from ..core.connection import get_app, get_doc, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import object_array

Kind = Literal["blocks", "layers", "linetypes", "text_styles", "dim_styles"]
_COLLECTION = {"blocks": "Blocks", "layers": "Layers", "linetypes": "Linetypes",
               "text_styles": "TextStyles", "dim_styles": "DimStyles"}


# ---- plain functions --------------------------------------------------------

def pick_names(available: list[str], patterns: list[str]) -> list[str]:
    """Names matching any wildcard, A-Z; AutoCAD internals (*, |, $) left out."""
    usable = [n for n in available if n and not n.startswith("*") and "|" not in n and "$" not in n]
    hits = {n for n in usable for p in patterns if fnmatch.fnmatch(n.lower(), p.lower())}
    return sorted(hits, key=str.lower)


def renumber_plan(names_in_order: list[str], prefix: str = "", start: int = 1, pad: int = 0,
                  suffix: str = "", step: int = 1) -> dict[str, str]:
    """New layout names in tab order: E-101, E-102 ..."""
    return {n: f"{prefix}{str(start + i * step).zfill(pad)}{suffix}" for i, n in enumerate(names_in_order)}


def check_names(existing: list[str], plan: dict[str, str]) -> None:
    """Refuse a rename that would leave two layouts with one name."""
    final = [plan.get(n, n).lower() for n in existing]
    dupes = sorted({plan.get(n, n) for n in existing if final.count(plan.get(n, n).lower()) > 1})
    if dupes:
        raise ValueError(f"these names would be used twice: {', '.join(dupes)}")


def order_plan(current: list[str], wanted: list[str]) -> list[str]:
    """Tab order: the named layouts first, in that order, then the rest as they were."""
    low = {n.lower(): n for n in current}
    missing = [w for w in wanted if w.lower() not in low]
    if missing:
        raise ValueError(f"no layout named: {', '.join(missing)}")
    first = [low[w.lower()] for w in wanted]
    return first + [n for n in current if n not in first]


def dbx_progid(version: str) -> str:
    """ObjectDBX reads a closed drawing; its ProgID carries AutoCAD's major version."""
    return f"ObjectDBX.AxDbDocument.{int(str(version).split('.')[0])}"


# ---- AutoCAD side -----------------------------------------------------------

def _names(collection: Any, kind: str) -> dict[str, Any]:
    out = {}
    for i in range(collection.Count):
        item = collection.Item(i)
        if kind == "blocks":
            try:
                if item.IsLayout or item.IsXRef:
                    continue
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
        out[str(item.Name)] = item
    return out


@mcp.tool(name="autocad_import_from_drawing", **tool_meta("Import from Another Drawing"))
@tool_errors
async def autocad_import_from_drawing(
    path: Annotated[str, Field(min_length=1, description="The standards or library .dwg to copy from.")],
    kind: Annotated[Kind, Field(description="What to bring in: blocks, layers, linetypes, text_styles or dim_styles.")],
    names: Annotated[list[str] | None, Field(description="Names or wildcards, e.g. ['VALVE*', 'PUMP']. Default: all.")] = None,
) -> str:
    """Copy blocks, layers, linetypes, text or dimension styles from another drawing into this one.

    Use to load company standard symbols and layers in one call. The source
    file is read without opening it on screen. Names that already exist here
    are skipped, never overwritten.

    Returns:
        JSON: {"imported": [...], "skipped_existing": [...], "not_found": [...]}

    Examples:
        - Use when: "bring the title block and the layer standard in from our
          template" -> the blocks, layers and styles, not the geometry.
        - Use when: starting a drawing that must match an existing set.
    """
    patterns = names or ["*"]

    def work() -> dict[str, Any]:
        app = get_app()
        doc = get_doc()
        require_idle(doc)
        source_path = os.path.normcase(os.path.abspath(os.path.expandvars(path.strip().strip('"'))))
        if not os.path.isfile(source_path):
            raise AutocadError(f"No drawing at {source_path}.")
        source = None
        for i in range(app.Documents.Count):
            open_doc = app.Documents.Item(i)
            if os.path.normcase(str(open_doc.FullName)) == source_path:
                source = open_doc
        if source is None:
            try:
                source = app.GetInterfaceObject(dbx_progid(str(app.Version)))
                source.Open(source_path)
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AutocadError(f"Could not read {source_path} ({com_message(exc)}). "
                                   "Open it in AutoCAD once and try again.") from exc
        attr = _COLLECTION[kind]
        available = _names(getattr(source, attr), kind)
        here = {n.lower() for n in _names(getattr(doc, attr), kind)}
        wanted = pick_names(list(available), patterns)
        new = [n for n in wanted if n.lower() not in here]
        skipped = [n for n in wanted if n.lower() in here]
        not_found = [p for p in patterns if not pick_names(list(available), [p])]
        if new:
            with undo_mark(doc):
                source.CopyObjects(object_array([available[n] for n in new]), getattr(doc, attr))
        return {"kind": kind, "source": source_path, "imported": new, "skipped_existing": skipped, "not_found": not_found}

    return dumps(await run(work))


def _layouts(doc: Any) -> list[Any]:
    items = [doc.Layouts.Item(i) for i in range(doc.Layouts.Count)]
    return sorted((lay for lay in items if str(lay.Name) != "Model"), key=lambda lay: int(lay.TabOrder))


@mcp.tool(name="autocad_list_layouts", **tool_meta("List Layouts", read_only=True, idempotent=True))
@tool_errors
async def autocad_list_layouts() -> str:
    """The drawing's layouts (sheets) in tab order, with paper size, plotter and object count.

    Returns:
        JSON: {"count", "layouts": [{name, tab_order, objects, plotter, paper}]}

    Examples:
        - Use when: "what sheets are in this drawing" -> tab order, paper
          size, plotter, how much is on each.
        - Use when: before a sheet-set job, to see which sheets are set up
          wrong.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        rows = []
        for lay in _layouts(doc):
            row: dict[str, Any] = {"name": str(lay.Name), "tab_order": int(lay.TabOrder)}
            for key, attr in (("objects", "Block"), ("plotter", "ConfigName"), ("paper", "CanonicalMediaName")):
                try:
                    value = getattr(lay, attr)
                    row[key] = int(value.Count) if key == "objects" else str(value)
                except BaseException as exc:  # noqa: BLE001
                    raise_if_busy(exc)
                    row[key] = None
            rows.append(row)
        return {"count": len(rows), "active": str(doc.ActiveLayout.Name), "layouts": rows}

    return dumps(await run(work))


@mcp.tool(name="autocad_manage_layouts", **tool_meta("Rename, Order, Renumber or Copy to Layouts"))
@tool_errors
async def autocad_manage_layouts(
    rename: Annotated[dict[str, str] | None, Field(description="{old name: new name}.")] = None,
    order: Annotated[list[str] | None, Field(description="Tab order: these first, in this order; the rest follow.")] = None,
    renumber_prefix: Annotated[str | None, Field(description="Renumber every layout in tab order: prefix, e.g. 'E-'.")] = None,
    renumber_start: Annotated[int, Field(description="First number when renumbering.")] = 1,
    renumber_pad: Annotated[int, Field(ge=0, le=6, description="Zero-pad digits when renumbering.")] = 0,
    renumber_suffix: Annotated[str, Field(description="Text after the number when renumbering.")] = "",
    copy_handles: Annotated[list[str] | None, Field(description="Paper-space objects (stamp, note, key plan) to copy to other layouts.")] = None,
    copy_to: Annotated[list[str] | None, Field(description="Layouts to copy to. Default: every other layout.")] = None,
) -> str:
    """Sheet housekeeping: rename layouts, put tabs in order, renumber them, or copy objects onto every sheet.

    Order runs first, then renumbering (in the new tab order), then renames,
    then copies. One undo step.

    Returns:
        JSON: {"renamed": {old: new}, "order": [...], "copied": {layout: [handles]}}

    Examples:
        - Use when: "put the sheets in order and renumber them" across a
          package.
        - Use when: "copy this north arrow onto every sheet".
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        layouts = {str(lay.Name): lay for lay in _layouts(doc)}
        names = list(layouts)
        result: dict[str, Any] = {}
        try:
            final_order = order_plan(names, order) if order else names
            plan: dict[str, str] = {}
            if renumber_prefix is not None:
                plan.update(renumber_plan(final_order, renumber_prefix, renumber_start, renumber_pad, renumber_suffix))
            if rename:
                low = {n.lower(): n for n in names}
                for old, new in rename.items():
                    if old.lower() not in low:
                        raise ValueError(f"no layout named: {old}")
                    plan[low[old.lower()]] = new
            plan = {k: v for k, v in plan.items() if k != v}
            check_names(names, plan)
        except ValueError as exc:
            raise AutocadError(str(exc)) from exc

        with undo_mark(doc):
            if order:
                for i, name in enumerate(final_order, start=1):
                    layouts[name].TabOrder = i
                result["order"] = final_order
            if plan:
                for i, old in enumerate(plan):  # two passes, so swapped names never clash
                    layouts[old].Name = f"__heron_tmp_{i}"
                for old, new in plan.items():
                    layouts[old].Name = new
                result["renamed"] = plan
            if copy_handles:
                objects = resolve_handles(doc, copy_handles)
                targets = copy_to or [plan.get(n, n) for n in names]
                by_name = {str(lay.Name).lower(): lay for lay in _layouts(doc)}
                copied: dict[str, list[str]] = {}
                for target in targets:
                    lay = by_name.get(target.lower())
                    if lay is None:
                        raise AutocadError(f"No layout named '{target}'.")
                    own = [o for o in objects if str(doc.ObjectIdToObject(o.OwnerID).ObjectID) != str(lay.Block.ObjectID)]
                    if own:
                        made = doc.CopyObjects(object_array(own), lay.Block)
                        copied[str(lay.Name)] = [str(m.Handle) for m in made]
                result["copied"] = copied
        return result

    return dumps(await run(work))
