"""Geometry and placement tools: polyline info, live field labels, connected runs,
segment length labels, blocks along a run, blocks from a CSV, breaks at blocks.

Ideas from Lee Mac's Polyline Information, Length & Area Field, Chain Selection,
Length at Midpoint, Length Between Intersections, Centered Measure, Point Manager
and Automatic Block Break (lee-mac.com). Heron's own code: none of his is used
(D-26). The geometry is plain functions in acad/geometry.py and here, tested
without AutoCAD.
"""

from __future__ import annotations

import csv
import math
import os
from typing import Annotated, Any

from pydantic import Field

from ..acad import geometry
from ..acad.curves import curve_length, read_path
from ..acad.entities import resolve_handle, resolve_handles
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import apply_properties
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, double_array, group_coordinates
from ._shared import LAYER_OPT, point

AC_EXTEND_NONE = 0
AC_ALIGN_BOTTOM_CENTER = 13
AC_ALL_VIEWPORTS = 1


# ---- plain functions --------------------------------------------------------

def readable(angle: float) -> float:
    """A text rotation that reads left to right or bottom to top: (-90, 90]."""
    a = angle % 360.0
    if 90.0 < a <= 270.0:
        a -= 180.0
    elif a > 270.0:
        a -= 360.0
    return a


def describe_path(path: dict) -> dict[str, Any]:
    """Vertices, every segment (arcs with centre, radius, sweep) and the centroid."""
    segs = geometry.segments(path["vertices"], path["bulges"], path["closed"])
    rows = []
    for i, s in enumerate(segs):
        row: dict[str, Any] = {"index": i, "kind": "arc" if s.centre else "line",
                               "start": [round(c, 6) for c in s.start], "end": [round(c, 6) for c in s.end],
                               "length": round(s.length, 6)}
        if s.centre:
            row.update(centre=[round(c, 6) for c in s.centre], radius=round(s.radius, 6),
                       sweep_degrees=round(math.degrees(abs(s.sweep)), 6), bulge=s.bulge)
        rows.append(row)
    out: dict[str, Any] = {"closed": path["closed"], "vertex_count": len(path["vertices"]),
                           "segment_count": len(segs), "total_length": sum(s.length for s in segs),
                           "vertices": [[round(v[0], 6), round(v[1], 6)] for v in path["vertices"]], "segments": rows}
    out["centroid"] = [round(c, 6) for c in geometry.centroid(path["vertices"])[0]] if path["closed"] else None
    return out


def field_code(object_ids: list[str], prop: str, precision: int = 0, factor: float = 1.0) -> str:
    """An AutoCAD field showing an object's Length or Area, or the sum over several."""
    fmt = f"%lu2%pr{precision}" + (f"%ct8[{factor}]" if factor != 1 else "")
    if len(object_ids) == 1:
        return f'%<\\AcObjProp Object(%<\\_ObjId {object_ids[0]}>%).{prop} \\f "{fmt}">%'
    parts = "+".join(f"%<\\AcObjProp Object(%<\\_ObjId {i}>%).{prop}>%" for i in object_ids)
    return f'%<\\AcExpr ({parts}) \\f "{fmt}">%'


def segment_labels(path: dict, offset: float, precision: int = 0, prefix: str = "", suffix: str = "",
                   cuts: list | None = None) -> list[dict[str, Any]]:
    """A length label for each segment (split at the cut points), above it and readable."""
    out = []
    for seg in geometry.segments(path["vertices"], path["bulges"], path["closed"]):
        if seg.centre is None:
            parts = geometry.pieces(seg.start, seg.end, cuts or [])
            spans = [(a, b, math.dist(a, b)) for a, b in parts]
        else:
            spans = [(seg, None, seg.length)]
        for a, b, length in spans:
            if b is None:
                x, y, direction = geometry.point_at([a], a.length / 2)
            else:
                x, y = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                direction = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            rot = readable(direction)
            normal = math.radians(rot + 90.0)
            out.append({"text": f"{prefix}{length:.{precision}f}{suffix}", "length": length, "rotation": rot,
                        "position": [x + offset * math.cos(normal), y + offset * math.sin(normal)]})
    return out


def places_along(path: dict, spacing: float | None = None, count: int | None = None,
                 align: bool = False) -> list[dict[str, Any]]:
    """Insertion points along a run with equal ends; turned to the run when align."""
    segs = geometry.segments(path["vertices"], path["bulges"], path["closed"])
    total = sum(s.length for s in segs)
    out = []
    for d in geometry.centred_positions(total, spacing, count):
        x, y, direction = geometry.point_at(segs, d)
        out.append({"position": [x, y], "rotation": direction if align else 0.0, "distance": d})
    return out


def rows_to_places(rows: list[dict], default_block: str | None) -> list[dict[str, Any]]:
    """CSV rows to insertions: x, y, (rotation), (block); every other column is an attribute."""
    places = []
    for i, row in enumerate(rows, start=1):
        low = {str(k).strip().lower(): (k, v) for k, v in row.items() if k is not None}
        try:
            x, y = float(low["x"][1]), float(low["y"][1])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"row {i} needs numeric x and y columns") from None
        rotation = float(low["rotation"][1]) if low.get("rotation") and str(low["rotation"][1]).strip() else 0.0
        block = (str(low["block"][1]).strip() if low.get("block") and str(low["block"][1]).strip() else default_block)
        if not block:
            raise ValueError(f"row {i} has no block: add a 'block' column or give block_name")
        attributes = {k: v for key, (k, v) in low.items() if key not in ("x", "y", "z", "rotation", "block")}
        places.append({"position": [x, y], "rotation": rotation, "block": block, "attributes": attributes})
    return places


def grow(box: tuple[float, float, float, float], gap: float) -> tuple[float, float, float, float]:
    return (box[0] - gap, box[1] - gap, box[2] + gap, box[3] + gap)


# ---- AutoCAD side -----------------------------------------------------------

def _object_id(doc: Any, entity: Any) -> str:
    try:
        return str(doc.Utility.GetObjectIdString(entity, False))
    except BaseException as exc:  # noqa: BLE001 - older releases
        raise_if_busy(exc)
        return str(entity.ObjectID)


@mcp.tool(name="autocad_polyline_info", **tool_meta("Polyline Information", read_only=True, idempotent=True))
@tool_errors
async def autocad_polyline_info(
    handle: Annotated[str, Field(min_length=1, description="A line, polyline, arc or circle.")],
) -> str:
    """Every vertex and segment of a run: lengths, arcs (centre, radius, sweep), total, area, centroid.

    The centroid (closed shapes) is the place for a room or zone tag.

    Returns:
        JSON: {"total_length", "area", "centroid", "segments": [...], "vertices": [...]}

    Examples:
        - Use when: "is that slot one object, and what is its perimeter" ->
          segment count, which are arcs, radii, total length.
        - Use when: checking a flat pattern: each arc must be as long as the
          girth it rolls onto (pi x diameter).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        e = resolve_handle(doc, handle)
        info = describe_path(read_path(e))
        try:
            info["area"] = float(e.Area) if info["closed"] else None
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            info["area"] = None
        info["handle"] = str(e.Handle)
        return info

    return dumps(await run(work))


@mcp.tool(name="autocad_add_field_label", **tool_meta("Add Live Length or Area Label"))
@tool_errors
async def autocad_add_field_label(
    handles: Annotated[list[str], Field(min_length=1, description="The object(s) to measure; several are added up.")],
    prop: Annotated[str, Field(pattern="^(Length|Area)$", description="'Length' or 'Area'.")] = "Length",
    position: Annotated[list[float] | None, Field(description="New text here [x, y]. Or give block_handle + tag.")] = None,
    block_handle: Annotated[str | None, Field(description="Put the field in this block's attribute instead.")] = None,
    tag: Annotated[str | None, Field(description="The attribute tag for block_handle.")] = None,
    prefix: Annotated[str, Field(description="Text before the value, e.g. 'L = '.")] = "",
    suffix: Annotated[str, Field(description="Text after the value, e.g. ' mm' or ' m²'.")] = "",
    precision: Annotated[int, Field(ge=0, le=8, description="Decimal places.")] = 0,
    factor: Annotated[float, Field(gt=0, description="Multiply the value: 0.001 for mm to m, 0.000001 for mm² to m².")] = 1.0,
    height: Annotated[float, Field(gt=0, description="Text height for new text.")] = 2.5,
    layer: Annotated[str | None, LAYER_OPT] = None,
) -> str:
    """A length or area label that stays right: an AutoCAD field linked to the object(s).

    Edit the run and the label updates on the next regen. Several objects give their sum.

    Returns:
        JSON: {"handle", "value" (as shown now), "field_code"}

    Examples:
        - Use when: "label that duct with its length, and keep it right if I
          stretch it" -> handles=[the duct], kind="length".
        - Don't use when: a fixed number is fine -
          autocad_label_segment_lengths does a whole run in one call.
    """
    if position is None and not (block_handle and tag):
        raise AutocadError("Give 'position' for new text, or 'block_handle' and 'tag' for an attribute.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ids = [_object_id(doc, o) for o in resolve_handles(doc, handles)]
        code = field_code(ids, prop, precision, factor)
        content = f"{prefix}{code}{suffix}"
        with undo_mark(doc):
            if position is not None:
                target = get_space(doc, "model").AddMText(point(position, "position"), 0.0, content)
                target.Height = float(height)
                apply_properties(doc, target, layer, None, None)
            else:
                ref = resolve_handle(doc, block_handle)
                atts = [a for a in (ref.GetAttributes() if ref.HasAttributes else []) if str(a.TagString).upper() == tag.upper()]
                if not atts:
                    raise AutocadError(f"Block {block_handle} has no attribute '{tag}'.")
                target = atts[0]
                target.TextString = content
            doc.Regen(AC_ALL_VIEWPORTS)
        return {"handle": str(block_handle or target.Handle), "value": str(target.TextString), "field_code": code}

    return dumps(await run(work))


_CURVES = ("line", "lwpolyline", "arc", "polyline2d")


def _gather_curves(doc: Any, layer: str | None) -> list[Any]:
    out = []
    for kind in ("line", "lwpolyline", "arc"):
        sel = select_filtered(doc, entity_type=kind, layer=layer)
        try:
            out.extend(iter_selection(sel))
        finally:
            discard_selection_set(doc)
    return out


@mcp.tool(name="autocad_select_connected", **tool_meta("Select Connected Run", read_only=True, idempotent=True))
@tool_errors
async def autocad_select_connected(
    handle: Annotated[str, Field(min_length=1, description="Any line, polyline or arc of the run.")],
    tolerance: Annotated[float, Field(gt=0, description="Ends closer than this count as joined.")] = 0.001,
    same_layer: Annotated[bool, Field(description="Only follow objects on the seed's layer.")] = True,
) -> str:
    """Find a whole run: every line, polyline and arc joined end to end with the seed.

    Returns its handles, total length and open ends (where the run stops), e.g.
    one pipe or cable route for a take-off or a check.

    Returns:
        JSON: {"handles", "count", "total_length", "open_ends"}

    Examples:
        - Use when: "select that whole pipe run" from one line you can point
          at, then total it or move it as one.
        - Don't use when: the run is all on its own layer - a layer filter is
          simpler.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        seed = resolve_handle(doc, handle)
        items, lengths = [], {}
        for e in _gather_curves(doc, str(seed.Layer) if same_layer else None):
            try:
                path = read_path(e)
            except AutocadError:
                continue
            ends = [] if path["closed"] else [path["vertices"][0], path["vertices"][-1]]
            items.append({"handle": str(e.Handle), "ends": ends})
            lengths[str(e.Handle)] = curve_length(e) or 0.0
        found = geometry.connected(items, str(seed.Handle), tolerance)
        return {"handles": found["handles"], "count": len(found["handles"]),
                "total_length": sum(lengths[h] for h in found["handles"]),
                "open_ends": [[round(p[0], 6), round(p[1], 6)] for p in found["open_ends"]]}

    return dumps(await run(work))


@mcp.tool(name="autocad_label_segment_lengths", **tool_meta("Label Segment Lengths"))
@tool_errors
async def autocad_label_segment_lengths(
    handles: Annotated[list[str], Field(min_length=1, description="Lines, polylines or arcs to label.")],
    height: Annotated[float, Field(gt=0, description="Text height.")],
    offset: Annotated[float | None, Field(description="Gap between line and text. Default: half the text height.")] = None,
    precision: Annotated[int, Field(ge=0, le=8, description="Decimal places.")] = 0,
    prefix: Annotated[str, Field(description="Text before the number.")] = "",
    suffix: Annotated[str, Field(description="Text after the number.")] = "",
    split_at_layer: Annotated[str | None, Field(description="Also split straight segments where they cross objects on this layer (e.g. branches).")] = None,
    factor: Annotated[float, Field(gt=0, description="Multiply lengths: 0.001 for mm to m.")] = 1.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
) -> str:
    """Write each segment's length at its middle, above the line and readable.

    Optionally between crossings with another layer (lengths between tees and
    branches). The text is plain: re-run after editing the run, or use
    autocad_add_field_label for a live total.

    Returns:
        JSON: {"labels": n, "items": [{handle, text, position, rotation}]}

    Examples:
        - Use when: "write the length on every leg of that run", above the
          line and the right way up.
        - Don't use when: the numbers must update if the run is stretched -
          autocad_add_field_label.
    """
    gap = height * 0.5 if offset is None else offset

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        targets = resolve_handles(doc, handles)
        cutters = _gather_curves(doc, split_at_layer) if split_at_layer else []
        space = get_space(doc, "model")
        items = []
        with undo_mark(doc):
            for e in targets:
                cuts = []
                for other in cutters:
                    if str(other.Handle) == str(e.Handle):
                        continue
                    try:
                        hits = e.IntersectWith(other, AC_EXTEND_NONE)
                    except BaseException as exc:  # noqa: BLE001
                        raise_if_busy(exc)
                        continue
                    cuts += [(p[0], p[1]) for p in group_coordinates(hits, 3)]
                for lab in segment_labels(read_path(e), gap, precision, prefix, suffix, cuts):
                    shown = f"{prefix}{lab['length'] * factor:.{precision}f}{suffix}"
                    text = space.AddText(shown, point(lab["position"], "position"), float(height))
                    text.Alignment = AC_ALIGN_BOTTOM_CENTER
                    text.TextAlignmentPoint = point(lab["position"], "position")
                    text.Rotation = math.radians(lab["rotation"])
                    apply_properties(doc, text, layer, None, None)
                    items.append({"handle": str(text.Handle), "of": str(e.Handle), "text": shown,
                                  "position": [round(c, 6) for c in lab["position"]], "rotation": round(lab["rotation"], 6)})
        return {"labels": len(items), "items": items}

    return dumps(await run(work))


def _fill(ref: Any, attributes: dict[str, Any]) -> list[str]:
    missing = []
    if not attributes:
        return missing
    atts = {str(a.TagString).upper(): a for a in (ref.GetAttributes() if ref.HasAttributes else [])}
    for tag, value in attributes.items():
        att = atts.get(str(tag).strip().upper())
        if att is None:
            missing.append(str(tag))
        else:
            att.TextString = str(value)
    return missing


@mcp.tool(name="autocad_place_along", **tool_meta("Place Blocks Along a Run"))
@tool_errors
async def autocad_place_along(
    path_handle: Annotated[str, Field(min_length=1, description="The line, polyline, arc or circle to place along.")],
    block_name: Annotated[str, Field(min_length=1, description="Block to insert (defined in the drawing).")],
    spacing: Annotated[float | None, Field(gt=0, description="Distance between blocks; the spare length is split equally at both ends.")] = None,
    count: Annotated[int | None, Field(ge=1, le=2000, description="Or this many blocks, equally spaced with half a space at each end.")] = None,
    align: Annotated[bool, Field(description="Turn each block to the run's direction.")] = False,
    rotation: Annotated[float, Field(description="Extra rotation in degrees, added to each block.")] = 0.0,
    scale: Annotated[float, Field(gt=0, description="Block scale.")] = 1.0,
    attributes: Annotated[dict[str, str] | None, Field(description="Attribute values for every block.")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
) -> str:
    """Insert a block at equal spacing along a run, centred so both ends match.

    For sprinklers, lights, diffusers, supports and cameras along a corridor.
    Number them afterwards with autocad_number_tags (sort='path').

    Returns:
        JSON: {"placed": n, "handles", "spacing", "run_length"}

    Examples:
        - Use when: "hangers every 2 m along that duct, ends matching" ->
          spacing=2000; it centres the run so both ends are equal.
        - Don't use when: the positions come from a schedule -
          autocad_place_from_csv.
    """
    if not spacing and not count:
        raise AutocadError("Give 'spacing' or 'count'.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        try:
            doc.Blocks.Item(block_name)
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            raise AutocadError(f"No block named '{block_name}' in this drawing; see autocad_list_blocks.") from None
        path = read_path(resolve_handle(doc, path_handle))
        spots = places_along(path, spacing, count, align)
        space = get_space(doc, "model")
        handles, missing = [], set()
        with undo_mark(doc):
            for s in spots:
                ref = space.InsertBlock(point(s["position"], "position"), block_name, scale, scale, scale,
                                        math.radians(s["rotation"] + rotation))
                apply_properties(doc, ref, layer, None, None)
                missing.update(_fill(ref, attributes or {}))
                handles.append(str(ref.Handle))
        total = sum(seg.length for seg in geometry.segments(path["vertices"], path["bulges"], path["closed"]))
        out: dict[str, Any] = {"placed": len(handles), "handles": handles, "run_length": total,
                               "spacing": spacing or (total / count if count else None)}
        if missing:
            out["attributes_not_found"] = sorted(missing)
        return out

    return dumps(await run(work))


@mcp.tool(name="autocad_place_from_csv", **tool_meta("Place Blocks from a CSV"))
@tool_errors
async def autocad_place_from_csv(
    csv_path: Annotated[str | None, Field(description="CSV with columns x, y, optional rotation and block; other columns fill attributes by tag.")] = None,
    rows: Annotated[list[dict[str, Any]] | None, Field(description="Or the rows inline, same columns.")] = None,
    block_name: Annotated[str | None, Field(description="Block for rows without a 'block' column.")] = None,
    scale: Annotated[float, Field(gt=0, description="Block scale.")] = 1.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
) -> str:
    """Insert blocks at coordinates from a schedule and fill their attributes from the same rows.

    For device, pole and camera schedules, or setting-out points from a survey.

    Returns:
        JSON: {"placed": n, "handles", "attributes_not_found"}

    Examples:
        - Use when: "place all 42 cameras from this schedule, with their tags
          filled in" -> the csv carries x, y and the attribute columns.
        - Use when: a surveyor hands you coordinates.
    """
    data = list(rows or [])
    if csv_path:
        path = os.path.expandvars(os.path.expanduser(csv_path.strip().strip('"')))
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                data += list(csv.DictReader(fh))
        except OSError as exc:
            raise AutocadError(f"Could not read {path}: {exc}") from exc
    if not data:
        raise AutocadError("Give 'csv_path' or 'rows'.")
    try:
        places = rows_to_places(data, block_name)
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        for name in {p["block"] for p in places}:
            try:
                doc.Blocks.Item(name)
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AutocadError(f"No block named '{name}' in this drawing; see autocad_list_blocks.") from None
        space = get_space(doc, "model")
        handles, missing = [], set()
        with undo_mark(doc):
            for p in places:
                ref = space.InsertBlock(point(p["position"], "position"), p["block"], scale, scale, scale,
                                        math.radians(p["rotation"]))
                apply_properties(doc, ref, layer, None, None)
                missing.update(_fill(ref, p["attributes"]))
                handles.append(str(ref.Handle))
        return {"placed": len(handles), "handles": handles, "attributes_not_found": sorted(missing)}

    return dumps(await run(work))


@mcp.tool(name="autocad_break_at_blocks", **tool_meta("Break Lines at Blocks"))
@tool_errors
async def autocad_break_at_blocks(
    block_handles: Annotated[list[str], Field(min_length=1, description="The blocks sitting on the lines: valves, fittings, symbols.")],
    layer: Annotated[str | None, Field(description="Only break lines and polylines on this layer (e.g. the pipe layer).")] = None,
    gap: Annotated[float, Field(ge=0, description="Extra clearance round each block's extents.")] = 0.0,
) -> str:
    """Cut the lines and polylines that run through blocks, so a symbol sits in a clean gap.

    Uses each block's extents (square to the drawing), plus 'gap'. Straight
    segments only: a polyline with arcs is left alone and listed. One undo step.

    Returns:
        JSON: {"broken": n, "new_handles", "removed", "skipped": [{handle, reason}]}

    Examples:
        - Use when: a symbol sits on top of the line it belongs to and the
          drawing reads badly: cut a clean gap round every block.
        - Use when: an import has wiring or pipework running straight through
          its devices.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        blocks = resolve_handles(doc, block_handles)
        broken, new_handles, removed, skipped = set(), [], [], []
        with undo_mark(doc):
            for blk in blocks:
                lo, hi = blk.GetBoundingBox()
                box = grow((lo[0], lo[1], hi[0], hi[1]), gap)
                for kind in ("line", "lwpolyline"):
                    sel = select_filtered(doc, entity_type=kind, layer=layer)
                    try:
                        curves = list(iter_selection(sel))
                    finally:
                        discard_selection_set(doc)
                    for c in curves:
                        try:
                            clo, chi = c.GetBoundingBox()
                        except BaseException as exc:  # noqa: BLE001
                            raise_if_busy(exc)
                            continue
                        if clo[0] > box[2] or chi[0] < box[0] or clo[1] > box[3] or chi[1] < box[1]:
                            continue
                        h = str(c.Handle)
                        if kind == "line":
                            s, e = c.StartPoint, c.EndPoint
                            parts = geometry.outside_pieces((s[0], s[1]), (e[0], e[1]), box)
                            if parts == [((s[0], s[1]), (e[0], e[1]))]:
                                continue
                            runs = [[a, b] for a, b in parts]
                        else:
                            path = read_path(c)
                            if any(abs(b) > 1e-12 for b in path["bulges"]):
                                skipped.append({"handle": h, "reason": "polyline has arcs"})
                                continue
                            verts = path["vertices"] + ([path["vertices"][0]] if path["closed"] else [])
                            runs = geometry.path_outside(verts, box)
                            if len(runs) == 1 and len(runs[0]) == len(verts):
                                continue
                        broken.add(h)
                        if not runs:
                            c.Delete()
                            removed.append(h)
                            continue
                        for i, run_pts in enumerate(runs):
                            target = c if i == 0 else c.Copy()
                            if kind == "line":
                                target.StartPoint = apoint(*run_pts[0])
                                target.EndPoint = apoint(*run_pts[1])
                            else:
                                if path["closed"]:
                                    target.Closed = False
                                target.Coordinates = double_array([v for p in run_pts for v in p])
                            if i:
                                new_handles.append(str(target.Handle))
        return {"broken": len(broken), "new_handles": new_handles, "removed": removed, "skipped": skipped}

    return dumps(await run(work))
