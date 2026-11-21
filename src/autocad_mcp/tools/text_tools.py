"""Text and attribute tools: fill attributes, number tags, count, clean, find and replace, align.

Ideas from Lee Mac's Batch Attribute Editor, Update Titleblock Attributes,
Incremental Numbering Suite, Text Counter, Count / Sum Attribute Values,
UnFormat String, Batch Find & Replace and Align Text (lee-mac.com). This is
Heron's own code: none of his is used (D-26). The planning, ordering and
matching are plain functions, tested without AutoCAD.
"""

from __future__ import annotations

import csv
import os
import re
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import geometry
from ..acad.curves import read_path
from ..acad.entities import resolve_handle, resolve_handles
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import apply_properties
from ..acad.text import unformat
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, point_to_list
from ._shared import LAYER_OPT, before_after, point

Order = Literal["rows", "columns", "path", "given"]
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


# ---- plain functions --------------------------------------------------------

def number_labels(count: int, start: int = 1, step: int = 1, prefix: str = "", suffix: str = "", pad: int = 0) -> list[str]:
    """CAM-001, CAM-002 ... : prefix + zero-padded number + suffix."""
    return [f"{prefix}{str(start + i * step).zfill(pad)}{suffix}" for i in range(count)]


def order_points(points: dict[str, tuple[float, float]], by: Order, path: dict | None = None,
                 row_tolerance: float = 0.0) -> list[str]:
    """Keys in reading order: rows (top to bottom, then left to right), columns, or along a path."""
    def band(v: float) -> float:
        return round(v / row_tolerance) if row_tolerance else v

    if by == "given":
        return list(points)
    if by == "rows":
        return sorted(points, key=lambda k: (-band(points[k][1]), points[k][0]))
    if by == "columns":
        return sorted(points, key=lambda k: (band(points[k][0]), -points[k][1]))
    if not path:
        raise AutocadError("sort='path' needs path_handle: the line or polyline to number along.")
    segs = geometry.segments(path["vertices"], path["bulges"], path["closed"])
    return sorted(points, key=lambda k: geometry.distance_along(segs, points[k]))


def plan_attributes(refs: list[dict], values: dict | None = None, rows: list[dict] | None = None,
                    key: str | None = None) -> dict[str, Any]:
    """Which attribute changes to make. refs: {handle, block, layout, attributes {TAG: value}}.

    values: the same {tag: value} for every block. rows + key: per-block values,
    matched on the key column (an attribute tag, or 'layout' for the layout name).
    """
    changes: list[dict] = []
    unknown: set[str] = set()
    unmatched: list[str] = []

    def apply(ref: dict, wanted: dict) -> None:
        tags = {t.upper(): t for t in ref["attributes"]}
        for name, new in wanted.items():
            tag = tags.get(str(name).strip().upper())
            if tag is None:
                unknown.add(str(name).strip().upper())
                continue
            old = ref["attributes"][tag]
            if str(old) != str(new):
                changes.append({"handle": ref["handle"], "block": ref["block"], "layout": ref.get("layout"),
                                "tag": tag, "old": old, "new": str(new)})

    if values:
        for ref in refs:
            apply(ref, values)
    if rows:
        if not key:
            raise AutocadError("Rows need 'key': the column that says which block a row is for (a tag, or 'layout').")
        by_layout = key.strip().lower() == "layout"
        for row in rows:
            row_key = next((v for k, v in row.items() if k.strip().upper() == key.strip().upper()), None)
            hits = [r for r in refs if str(r.get("layout") if by_layout else
                                           {t.upper(): v for t, v in r["attributes"].items()}.get(key.strip().upper())) == str(row_key)]
            if not hits:
                unmatched.append(str(row_key))
            wanted = {k: v for k, v in row.items() if k.strip().upper() != key.strip().upper()}
            for ref in hits:
                apply(ref, wanted)
    return {"changes": changes, "unknown_tags": sorted(unknown), "unmatched_rows": unmatched}


def tally(values: list[str], normalise: bool = True, sum_numeric: bool = False) -> dict[str, Any]:
    """Count each distinct value; optionally add up the first number in each."""
    counts: dict[str, int] = {}
    total = 0.0
    for raw in values:
        value = unformat(raw).upper().strip() if normalise else str(raw)
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
        if sum_numeric:
            found = _NUMBER.search(value)
            if found:
                total += float(found.group())
    report: dict[str, Any] = {"total": sum(counts.values()), "distinct": len(counts),
                              "counts": dict(sorted(counts.items()))}
    if sum_numeric:
        report["sum"] = total
    return report


def replace_text(text: str, find: str, replace: str, regex: bool, case_sensitive: bool) -> tuple[str, int]:
    """The text with every match replaced, and how many there were."""
    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        return re.subn(find, replace, text, flags=flags)
    return re.subn(re.escape(find), lambda _m: replace, text, flags=flags)


AlignMode = Literal["left", "right", "centre", "top", "bottom", "middle", "distribute_vertical", "distribute_horizontal"]


def align_moves(boxes: dict[str, tuple[float, float, float, float]], mode: AlignMode,
                reference: float | None = None) -> dict[str, tuple[float, float]]:
    """How far to move each box (min x, min y, max x, max y) to line them up."""
    def cx(b):
        return (b[0] + b[2]) / 2

    def cy(b):
        return (b[1] + b[3]) / 2

    if mode in ("distribute_vertical", "distribute_horizontal"):
        centre = cy if mode == "distribute_vertical" else cx
        order = sorted(boxes, key=lambda k: centre(boxes[k]))
        first, last = centre(boxes[order[0]]), centre(boxes[order[-1]])
        step = (last - first) / (len(order) - 1) if len(order) > 1 else 0
        out = {}
        for i, k in enumerate(order):
            d = first + i * step - centre(boxes[k])
            out[k] = (0, d) if mode == "distribute_vertical" else (d, 0)
        return {k: out[k] for k in boxes}
    edge = {"left": lambda b: b[0], "right": lambda b: b[2], "centre": cx,
            "top": lambda b: b[3], "bottom": lambda b: b[1], "middle": cy}[mode]
    if reference is None:
        reference = edge(next(iter(boxes.values())))  # the first object stays put
    horizontal = mode in ("left", "right", "centre")
    return {k: ((reference - edge(b), 0) if horizontal else (0, reference - edge(b))) for k, b in boxes.items()}


def _read_rows(csv_path: str) -> list[dict]:
    path = os.path.expandvars(os.path.expanduser(csv_path.strip().strip('"')))
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError as exc:
        raise AutocadError(f"Could not read the CSV file {path}: {exc}") from exc


# ---- AutoCAD side -----------------------------------------------------------

def _layout_of(doc: Any, entity: Any) -> str | None:
    try:
        owner = doc.ObjectIdToObject(entity.OwnerID)
        return str(owner.Layout.Name) if owner.IsLayout else None
    except BaseException:  # noqa: BLE001
        return None


def _attribute_refs(doc: Any, block_name: str | None, layer: str | None) -> tuple[list[dict], dict[str, Any]]:
    refs, objects = [], {}
    sel = select_filtered(doc, entity_type="insert", layer=layer)
    try:
        for ref in iter_selection(sel):
            try:
                if not ref.HasAttributes:
                    continue
                name = str(getattr(ref, "EffectiveName", None) or ref.Name)
            except BaseException:  # noqa: BLE001
                continue
            if block_name and name.lower() != block_name.lower():
                continue
            attributes = {str(a.TagString): str(a.TextString) for a in ref.GetAttributes()}
            refs.append({"handle": str(ref.Handle), "block": name, "layout": _layout_of(doc, ref), "attributes": attributes})
            objects[str(ref.Handle)] = ref
    finally:
        discard_selection_set(doc)
    return refs, objects


@mcp.tool(name="autocad_set_attributes", **tool_meta("Set Block Attributes"))
@tool_errors
async def autocad_set_attributes(
    block_name: Annotated[str | None, Field(description="Only this block (real name), e.g. the title block. Default: every block with attributes.")] = None,
    values: Annotated[dict[str, str] | None, Field(description="{TAG: value} written to every matching block, e.g. {'REV': 'B'}.")] = None,
    rows: Annotated[list[dict[str, str]] | None, Field(description="Per-block values: one dict per block, with the 'key' column saying which block.")] = None,
    csv_path: Annotated[str | None, Field(description="Or a CSV file holding the rows (first line = column names).")] = None,
    key: Annotated[str | None, Field(description="Column that picks the block: an attribute tag (e.g. 'SHEET_NO') or 'layout' for the layout name.")] = None,
    layer: Annotated[str | None, Field(description="Only blocks on this layer.")] = None,
    dry_run: Annotated[bool, Field(description="True: list the changes without making them.")] = False,
) -> str:
    """Fill block attributes: title blocks on every layout, equipment tags, schedules.

    Same values for all, or one row per block from a list or CSV, matched by a
    tag or the layout name. Pairs with autocad_extract_attributes (read, edit, write back).

    Returns:
        JSON: {"changed": n, "changes": [{handle, block, layout, tag, old, new}], "unknown_tags", "unmatched_rows",
        "before_after": the first 50 changes as {handle, property, from, to}}

    Examples:
        - Use when: "fill the title block on every sheet with this drawing
          number and date".
        - Don't use when: you are placing the title block for the first time -
          autocad_place_title_block fills it as it goes.
    """
    if csv_path:
        rows = (rows or []) + _read_rows(csv_path)
    if not values and not rows:
        raise AutocadError("Give 'values', 'rows' or 'csv_path'.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        refs, objects = _attribute_refs(doc, block_name, layer)
        plan = plan_attributes(refs, values, rows, key)
        if dry_run:
            return {"changed": 0, "dry_run": dry_run, "blocks_read": len(refs), **plan}
        if not plan["changes"]:
            # Nothing differs: no write, so no empty undo step (D-62).
            return {"changed": 0, "dry_run": False, "blocks_read": len(refs), **plan, **before_after([])}
        with undo_mark(doc):
            for change in plan["changes"]:
                ref = objects[change["handle"]]
                for att in ref.GetAttributes():
                    if str(att.TagString) == change["tag"]:
                        att.TextString = change["new"]
                ref.Update()
        listed = [{"handle": c["handle"], "property": f"attribute {c['tag']}", "from": c["old"], "to": c["new"]}
                  for c in plan["changes"]]  # fmt: skip
        return {"changed": len(plan["changes"]), "blocks_read": len(refs), **plan, **before_after(listed)}

    return dumps(await run(work))


@mcp.tool(name="autocad_number_tags", **tool_meta("Number Tags"))
@tool_errors
async def autocad_number_tags(
    prefix: Annotated[str, Field(description="Text before the number, e.g. 'CAM-'.")] = "",
    start: Annotated[int, Field(description="First number.")] = 1,
    step: Annotated[int, Field(description="Step between numbers.")] = 1,
    suffix: Annotated[str, Field(description="Text after the number.")] = "",
    pad: Annotated[int, Field(ge=0, le=6, description="Zero-pad to this many digits: 3 gives 001.")] = 0,
    handles: Annotated[list[str] | None, Field(description="Existing blocks (with 'tag') or texts to number.")] = None,
    tag: Annotated[str | None, Field(description="For blocks: the attribute tag that takes the number.")] = None,
    positions: Annotated[list[list[float]] | None, Field(description="Or new text at these points [[x, y], ...].")] = None,
    height: Annotated[float, Field(gt=0, description="Text height for new text.")] = 2.5,
    sort: Annotated[Order, Field(description="rows (top to bottom, left to right), columns, path (along path_handle), or given order.")] = "rows",
    path_handle: Annotated[str | None, Field(description="For sort='path': the run to number along.")] = None,
    row_tolerance: Annotated[float, Field(ge=0, description="Points within this height count as one row.")] = 0.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    dry_run: Annotated[bool, Field(description="True: show the numbers without writing them.")] = False,
) -> str:
    """Number tags in order: CAM-001, CAM-002 ... on blocks, texts, or as new text.

    Sorted by rows, columns or along a run, so the numbering follows the
    drawing. One undo step.

    Returns:
        JSON: {"numbered": n, "assigned": [{handle, number}]}

    Examples:
        - Use when: "number these cameras CAM-001 upwards, left to right".
        - Use when: a schedule needs tags that match the drawing: number them
          here first, then autocad_extract_attributes for the table.
    """
    if not handles and not positions:
        raise AutocadError("Give 'handles' (existing blocks or texts) or 'positions' (new text).")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        path = read_path(resolve_handle(doc, path_handle)) if path_handle else None
        if positions:
            pts = {str(i): (float(p[0]), float(p[1])) for i, p in enumerate(positions)}
            order = order_points(pts, sort, path, row_tolerance)
            labels = number_labels(len(order), start, step, prefix, suffix, pad)
            if dry_run:
                return {"numbered": 0, "dry_run": True, "assigned": [{"position": list(pts[k]), "number": n} for k, n in zip(order, labels, strict=False)]}
            space = get_space(doc, "model")
            assigned = []
            with undo_mark(doc):
                for k, number in zip(order, labels, strict=False):
                    text = space.AddText(number, point(list(pts[k]), "position"), float(height))
                    apply_properties(doc, text, layer, None, None)
                    assigned.append({"handle": str(text.Handle), "number": number})
            return {"numbered": len(assigned), "assigned": assigned}

        objects = {h: o for h, o in zip(handles, resolve_handles(doc, handles), strict=False)}
        pts = {}
        for h, o in objects.items():
            p = point_to_list(o.InsertionPoint)
            pts[h] = (p[0], p[1])
        order = order_points(pts, sort, path, row_tolerance)
        labels = number_labels(len(order), start, step, prefix, suffix, pad)
        if dry_run:
            return {"numbered": 0, "dry_run": True, "assigned": [{"handle": h, "number": n} for h, n in zip(order, labels, strict=False)]}
        assigned, missing = [], []
        with undo_mark(doc):
            for h, number in zip(order, labels, strict=False):
                o = objects[h]
                if str(o.ObjectName) == "AcDbBlockReference":
                    atts = [a for a in (o.GetAttributes() if o.HasAttributes else []) if tag and str(a.TagString).upper() == tag.upper()]
                    if not atts:
                        missing.append(h)
                        continue
                    atts[0].TextString = number
                    o.Update()
                else:
                    o.TextString = number
                assigned.append({"handle": h, "number": number})
        out: dict[str, Any] = {"numbered": len(assigned), "assigned": assigned}
        if missing:
            out["not_numbered"] = missing
            out["hint"] = "These blocks have no attribute with that 'tag'; see autocad_extract_attributes."
        return out

    return dumps(await run(work))


@mcp.tool(name="autocad_count_text", **tool_meta("Count Text Values", read_only=True, idempotent=True))
@tool_errors
async def autocad_count_text(
    source: Annotated[Literal["all", "text", "attributes"], Field(description="Text and mtext, block attributes, or both.")] = "all",
    tag: Annotated[str | None, Field(description="For attributes: only this tag, e.g. 'SIZE'.")] = None,
    layer: Annotated[str | None, Field(description="Only this layer (wildcards allowed).")] = None,
    pattern: Annotated[str | None, Field(description="Only values matching this regular expression, e.g. '^DN'.")] = None,
    normalise: Annotated[bool, Field(description="Strip MText formatting and ignore case.")] = True,
    sum_numeric: Annotated[bool, Field(description="Also add up the first number in each value.")] = False,
) -> str:
    """Count text and tag values: how many DN50, how many of each camera type.

    Returns:
        JSON: {"total", "distinct", "counts": {value: n}, "sum"?}

    Examples:
        - Use when: "how many DN50 on this drawing" -> the tag values counted
          and grouped.
        - Don't use when: you are counting symbols - autocad_count_blocks.
    """
    regex = re.compile(pattern, re.IGNORECASE) if pattern else None

    def work() -> list[str]:
        doc = get_doc()
        values: list[str] = []
        kinds = (["text", "mtext"] if source in ("all", "text") else []) + (["insert"] if source in ("all", "attributes") else [])
        for kind in kinds:
            sel = select_filtered(doc, entity_type=kind, layer=layer)
            try:
                for e in iter_selection(sel):
                    if kind != "insert":
                        values.append(str(e.TextString))
                        continue
                    try:
                        if not e.HasAttributes:
                            continue
                        for a in e.GetAttributes():
                            if not tag or str(a.TagString).upper() == tag.upper():
                                values.append(str(a.TextString))
                    except BaseException:  # noqa: BLE001
                        continue
            finally:
                discard_selection_set(doc)
        return values

    values = await run(work)
    if regex:
        values = [v for v in values if regex.search(unformat(v))]
    return dumps(tally(values, normalise, sum_numeric))


@mcp.tool(name="autocad_text_clean", **tool_meta("Clean MText Formatting"))
@tool_errors
async def autocad_text_clean(
    handles: Annotated[list[str] | None, Field(description="MText or multileaders to clean. Default: all on 'layer'.")] = None,
    layer: Annotated[str | None, Field(description="With no handles: every MText on this layer (required then).")] = None,
    keep_paragraphs: Annotated[bool, Field(description="Keep line breaks.")] = True,
    dry_run: Annotated[bool, Field(description="True: show before/after without changing.")] = False,
) -> str:
    """Remove pasted formatting from MText (fonts, colours, heights, underline) so it follows its style.

    Returns:
        JSON: {"cleaned": n, "items": [{handle, before, after}]}

    Examples:
        - Use when: text pasted from Word or Excel keeps its own font, colour
          or height and ignores the drawing's style.
        - Use when: an import's notes plot the wrong size for no clear reason.
    """
    if not handles and not layer:
        raise AutocadError("Give 'handles', or a 'layer' to clean every MText on it.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if handles:
            targets = resolve_handles(doc, handles)
        else:
            sel = select_filtered(doc, entity_type="mtext", layer=layer)
            try:
                targets = list(iter_selection(sel))
            finally:
                discard_selection_set(doc)
        items = []
        for e in targets:
            before = str(e.TextString)
            after = unformat(before, keep_paragraphs=keep_paragraphs)
            if after != before:
                items.append({"handle": str(e.Handle), "before": before, "after": after, "_e": e})
        if not dry_run and items:
            with undo_mark(doc):
                for item in items:
                    item["_e"].TextString = item["after"]
        for item in items:
            item.pop("_e")
        return {"cleaned": 0 if dry_run else len(items), "dry_run": dry_run, "items": items}

    return dumps(await run(work))


Kind = Literal["text", "mtext", "attribute", "mleader", "dimension", "table"]


@mcp.tool(name="autocad_find_replace_text", **tool_meta("Find and Replace Text"))
@tool_errors
async def autocad_find_replace_text(
    find: Annotated[str, Field(min_length=1, description="Text (or regular expression) to find.")],
    replace: Annotated[str, Field(description="Replacement. With regex, \\1 refers to a group.")],
    regex: Annotated[bool, Field(description="Treat 'find' as a regular expression.")] = False,
    case_sensitive: Annotated[bool, Field(description="Match case exactly.")] = False,
    kinds: Annotated[list[Kind] | None, Field(description="Where to look; default all: text, mtext, attribute, mleader, dimension (override text), table.")] = None,
    layer: Annotated[str | None, Field(description="Only this layer (wildcards allowed).")] = None,
    dry_run: Annotated[bool, Field(description="True: list the hits without changing anything.")] = False,
) -> str:
    """Find and replace across text, mtext, attributes, multileaders, dimension overrides and tables.

    Use for revisions: a renamed room, a changed size, a new project name.
    Try dry_run first on a large drawing. One undo step.

    Returns:
        JSON: {"replaced": n, "hits": [{handle, kind, where, before, after}],
        "before_after": the first 50 as {handle, property, from, to}}

    Examples:
        - Use when: "change every REV A to REV B across the whole sheet set",
          including attributes and dimension overrides.
        - Use when: a client renames a room or a system and it appears in
          thirty places.
    """
    wanted = set(kinds or ["text", "mtext", "attribute", "mleader", "dimension", "table"])
    try:
        re.compile(find if regex else re.escape(find))
    except re.error as exc:
        raise AutocadError(f"'find' is not a valid regular expression: {exc}") from exc

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        hits: list[dict[str, Any]] = []
        setters: list[Any] = []

        def check(handle: str, kind: str, where: str, before: str, setter: Any) -> None:
            after, n = replace_text(before, find, replace, regex, case_sensitive)
            if n:
                hits.append({"handle": handle, "kind": kind, "where": where, "before": before, "after": after, "count": n})
                setters.append((setter, after))

        plan = [("text", "text"), ("mtext", "mtext"), ("insert", "attribute"), ("mleader", "mleader"),
                ("dimension", "dimension"), ("table", "table")]
        for dxf, kind in plan:
            if kind not in wanted:
                continue
            sel = select_filtered(doc, entity_type=dxf, layer=layer)
            try:
                for e in iter_selection(sel):
                    h = str(e.Handle)
                    try:
                        if kind in ("text", "mtext", "mleader"):
                            check(h, kind, "text", str(e.TextString), lambda v, e=e: setattr(e, "TextString", v))
                        elif kind == "dimension":
                            check(h, kind, "override", str(e.TextOverride), lambda v, e=e: setattr(e, "TextOverride", v))
                        elif kind == "attribute" and e.HasAttributes:
                            for a in e.GetAttributes():
                                check(h, kind, str(a.TagString), str(a.TextString), lambda v, a=a: setattr(a, "TextString", v))
                        elif kind == "table":
                            for r in range(int(e.Rows)):
                                for c in range(int(e.Columns)):
                                    check(h, kind, f"cell {r},{c}", str(e.GetText(r, c)),
                                          lambda v, e=e, r=r, c=c: e.SetText(r, c, v))
                    except BaseException:  # noqa: BLE001 - one odd object does not stop the search
                        continue
            finally:
                discard_selection_set(doc)
        if not dry_run and setters:
            with undo_mark(doc):
                for setter, value in setters:
                    setter(value)
        answer = {"replaced": 0 if dry_run else sum(h["count"] for h in hits), "dry_run": dry_run,
                  "objects": len({h["handle"] for h in hits}), "hits": hits[:500], "truncated": len(hits) > 500}
        if not dry_run:
            answer.update(before_after([{"handle": h["handle"], "property": f"{h['kind']} {h['where']}",
                                         "from": h["before"], "to": h["after"]} for h in hits]))  # fmt: skip
        return answer

    return dumps(await run(work))


@mcp.tool(name="autocad_align_text", **tool_meta("Align Text and Labels"))
@tool_errors
async def autocad_align_text(
    handles: Annotated[list[str], Field(min_length=2, description="Texts, mtexts or any objects to line up.")],
    mode: Annotated[AlignMode, Field(description=(
        "left / right / centre: line up on X. top / bottom / middle: line up on Y. "
        "distribute_vertical / distribute_horizontal: equal spacing, first and last stay."))],
    reference: Annotated[float | None, Field(description="The X or Y to line up on. Default: the first object's edge, so it stays put.")] = None,
) -> str:
    """Line up labels and notes, or space them evenly (by their extents). One undo step.

    Returns:
        JSON: {"moved": n, "moves": {handle: [dx, dy]}}

    Examples:
        - Use when: "tidy that column of labels so they line up left" and the
          leaders stop crossing.
        - Use when: "space these notes evenly" -> the even-spacing mode.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        objects = {h: o for h, o in zip(handles, resolve_handles(doc, handles), strict=False)}
        boxes = {}
        for h, o in objects.items():
            lo, hi = o.GetBoundingBox()
            boxes[h] = (float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1]))
        moves = align_moves(boxes, mode, reference)
        moved = 0
        with undo_mark(doc):
            for h, (dx, dy) in moves.items():
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    objects[h].Move(apoint(0, 0), apoint(dx, dy))
                    moved += 1
        return {"moved": moved, "moves": {h: [round(dx, 6), round(dy, 6)] for h, (dx, dy) in moves.items()}}

    return dumps(await run(work))



