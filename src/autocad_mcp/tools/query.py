"""Tools that read the drawing: list, inspect, search, measure, summarise.

These are the tools an agent reaches for before changing anything, so they all
return entity handles — the identity the modify and delete tools accept.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..acad.entities import (
    bounding_box,
    describe,
    resolve_handle,
    short_type,
    short_type_name,
)
from ..acad.selection import (
    ENTITY_TYPE_ALIASES,
    discard_selection_set,
    filter_pairs,
    iter_selection,
    select_filtered,
)
from ..acad.units import unit_name
from ..core.connection import get_doc, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta
from ..core.variants import point_to_list
from ._shared import faster_read
from .takeoff import plugin_lengths
from .text_tools import plugin_texts

# Listing every entity in a large drawing would swamp the agent's context, so
# results are paginated and this is the ceiling on one page.
MAX_PAGE = 500


def entity_summary(
    total: int, classes: Iterable[tuple[str, int]], layers: Iterable[tuple[str, int]]
) -> dict[str, Any]:
    """The summary_only answer, from class and layer counts in the order first met.

    Pure, and the only place that answer is made: COM counts the objects one
    by one, the plug-in counts them in one go (D-114), and both hand their
    counts here, so the two give the same answer, key order and all.
    """
    by_type: Counter[str] = Counter()
    for name, count in classes:
        by_type[short_type_name(str(name))] += int(count)
    by_layer: Counter[str] = Counter()
    for name, count in layers:
        by_layer[str(name)] += int(count)
    return {
        "total_matching": int(total),
        "by_type": dict(by_type.most_common()),
        "by_layer": dict(by_layer.most_common()),
    }


def box_around(boxes: Iterable[dict[str, list[float]] | None]) -> tuple[list[float], list[float]] | None:
    """The box round every box given (None ones skipped), or None when none was given. Pure."""
    lo = [math.inf, math.inf, math.inf]
    hi = [-math.inf, -math.inf, -math.inf]
    measured = False
    for box in boxes:
        if not box:
            continue
        measured = True
        for axis in range(3):
            lo[axis] = min(lo[axis], float(box["min"][axis]))
            hi[axis] = max(hi[axis], float(box["max"][axis]))
    return (lo, hi) if measured else None


def extents_answer(lo: list[float], hi: list[float], units: str, count: int, layer: str | None) -> dict[str, Any]:
    """The autocad_get_extents answer. Pure: the same whoever measured the box."""
    return {
        "min": [round(v, 6) for v in lo],
        "max": [round(v, 6) for v in hi],
        "width": round(hi[0] - lo[0], 6),
        "height": round(hi[1] - lo[1], 6),
        "center": [round((lo[0] + hi[0]) / 2, 6), round((lo[1] + hi[1]) / 2, 6)],
        "units": units,
        "entity_count": count,
        "scope": f"layer '{layer}'" if layer else "whole drawing",
    }


def _filter_args(*args: Any) -> dict[str, Any]:
    """The selection filter as the plug-in takes it: [[code, value], ...] (D-114)."""
    return {"filter": [[code, value] for code, value in filter_pairs(*args)]}


def _layer_empty(layer: str) -> AutocadError:
    return AutocadError(
        f"Layer '{layer}' has no geometry, so it has no extents. "
        "Check the layer name with autocad_list_layers."
    )


def _layer_unmeasured(layer: str, count: int) -> AutocadError:
    return AutocadError(
        f"Layer '{layer}' has {count} object(s), but none with extents (rays and construction "
        "lines run for ever), so it has no extents."
    )


@mcp.tool(
    name="autocad_list_entities",
    **tool_meta("List Drawing Entities", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_list_entities(
    entity_type: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Filter by type: line, circle, arc, polyline, text, mtext, "
                "block, dimension, hatch, ellipse, spline, point, leader, "
                "mleader, viewport, table, image. Omit for all types."
            ),
        ),
    ] = None,
    layer: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Filter by layer name. AutoCAD wildcards work: 'A-*' matches "
                "every layer starting with A-. Omit for all layers."
            ),
        ),
    ] = None,
    block_name: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Filter block references by block name, e.g. 'DOOR-SINGLE'. "
                "Implies entity_type='block'."
            ),
        ),
    ] = None,
    color: Annotated[
        str | StrictInt | None,
        Field(
            default=None,
            description="Filter by colour name or AutoCAD Color Index number.",
        ),
    ] = None,
    summary_only: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Return only counts grouped by type and by layer, with no "
                "per-entity detail. Use this first on an unfamiliar drawing — "
                "it is one small response instead of thousands of entities."
            ),
        ),
    ] = False,
    include_geometry: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "Include coordinates, radii, lengths and text content. Turn "
                "off for a compact handle/type/layer listing."
            ),
        ),
    ] = True,
    limit: Annotated[
        int,
        Field(default=50, description="Maximum entities to return.", ge=1, le=MAX_PAGE),
    ] = 50,
    offset: Annotated[
        int,
        Field(default=0, description="Entities to skip, for paging.", ge=0),
    ] = 0,
) -> str:
    """List entities in the active drawing, filtered by type, layer or colour.

    Filtering happens inside AutoCAD rather than in Python, so this stays fast
    on drawings with tens of thousands of entities.

    On an unfamiliar drawing, call it once with summary_only=true to learn what
    is there, then again with filters to get the entities you actually need.
    The summary is counted by Heron's plug-in inside AutoCAD in one go; with an
    older plug-in it is counted over COM, slower, with the same answer.

    Args:
        entity_type (Optional[str]): Type filter, e.g. "circle".
        layer (Optional[str]): Layer filter, wildcards allowed.
        block_name (Optional[str]): Block-name filter for block references.
        color (Optional[str | int]): Colour name or ACI number filter.
        summary_only (bool): Return counts only, no per-entity detail.
        include_geometry (bool): Include geometric and text properties.
        limit (int): Page size, 1-500.
        offset (int): Entities to skip, for paging.

    Returns:
        str: JSON. With summary_only=false:
        {
          "total_matching": int,      # matches before paging
          "count": int,               # entities in this response
          "offset": int,
          "has_more": bool,
          "next_offset": int | null,
          "filters": {...},           # what was actually applied
          "entities": [
            {"handle": str, "type": str, "layer": str, "color": int, ...}
          ]                           # extra keys depend on the entity type
        }

        With summary_only=true:
        {
          "total_matching": int,
          "by_type": {"line": int, "circle": int, ...},
          "by_layer": {"0": int, "A-WALL": int, ...}
        }

    Examples:
        - Use when: "what's in this drawing?" -> summary_only=true.
        - Use when: "list every circle on layer HOLES" ->
          entity_type="circle", layer="HOLES".
        - Don't use when: you already have a handle (use autocad_get_entity).
    """
    aci = to_aci(color)
    if entity_type:
        key = entity_type.strip().lower()
        if key not in ENTITY_TYPE_ALIASES and not entity_type.isupper():
            raise AutocadError(
                f"'{entity_type}' is not a type this server recognises. Use one "
                "of: " + ", ".join(sorted(ENTITY_TYPE_ALIASES)) + "."
            )
    resolved_type = entity_type or ("block" if block_name else None)

    def work() -> dict[str, Any]:
        if summary_only:
            # Every object in the drawing is looked at: the plug-in counts them
            # in one go; COM, three round trips each, only for an older one.
            counted = faster_read("count_entities", _filter_args(resolved_type, layer, block_name, aci))
            if counted is not None:
                return entity_summary(counted.get("total", 0), counted.get("by_class", []), counted.get("by_layer", []))

        doc = get_doc()
        sel = select_filtered(doc, resolved_type, layer, block_name, aci)
        try:
            total = int(sel.Count)

            if summary_only:
                classes: Counter[str] = Counter()
                layers: Counter[str] = Counter()
                for entity in iter_selection(sel):
                    try:
                        classes[str(entity.ObjectName)] += 1
                    except BaseException as exc:  # noqa: BLE001
                        raise_if_busy(exc)
                        classes[""] += 1
                    try:
                        layers[str(entity.Layer)] += 1
                    except BaseException as exc:  # noqa: BLE001
                        raise_if_busy(exc)
                        layers["<unknown>"] += 1
                return entity_summary(total, classes.items(), layers.items())

            entities = []
            for i in range(offset, min(offset + limit, total)):
                entities.append(
                    describe(sel.Item(i), include_geometry=include_geometry)
                )

            end = offset + len(entities)
            return {
                "total_matching": total,
                "count": len(entities),
                "offset": offset,
                "has_more": end < total,
                "next_offset": end if end < total else None,
                "filters": {
                    "entity_type": resolved_type,
                    "layer": layer,
                    "block_name": block_name,
                    "color": aci,
                },
                "entities": entities,
            }
        finally:
            discard_selection_set(doc)

    return dumps(await run(work))


@mcp.tool(
    name="autocad_get_entity",
    **tool_meta("Inspect Entity", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_get_entity(
    handle: Annotated[
        str,
        Field(
            description=(
                "The entity's handle, e.g. '1A4'. Handles come from "
                "autocad_list_entities, autocad_get_selection, or the tool "
                "that created the entity."
            ),
            min_length=1,
        ),
    ],
) -> str:
    """Read every available property of one entity, including its extents.

    Args:
        handle (str): The entity handle.

    Returns:
        str: JSON with the common properties (handle, type, layer, color,
             linetype), the type-specific geometry (for a circle: center,
             radius, area; for text: text, height, rotation_degrees; for a
             block: block_name, insertion_point, scale, attributes), plus:
        {
          "bounding_box": {"min": [x,y,z], "max": [x,y,z]},
          "size": {"width": float, "height": float}
        }

    Examples:
        - Use when: you have a handle and need its exact coordinates.
        - Don't use when: you want many entities (use autocad_list_entities).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        entity = resolve_handle(doc, handle)
        info = describe(entity, include_geometry=True)
        box = bounding_box(entity)
        if box:
            info["bounding_box"] = box
            info["size"] = {
                "width": round(box["max"][0] - box["min"][0], 6),
                "height": round(box["max"][1] - box["min"][1], 6),
            }
        return info

    return dumps(await run(work))


@mcp.tool(
    name="autocad_get_selection",
    **tool_meta("Get User's Selection", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_get_selection(
    include_geometry: Annotated[
        bool,
        Field(default=True, description="Include coordinates and dimensions."),
    ] = True,
    limit: Annotated[
        int,
        Field(default=100, description="Maximum entities to return.", ge=1, le=MAX_PAGE),
    ] = 100,
) -> str:
    """Read whatever the user currently has selected in AutoCAD.

    This is how a request like "move what I've selected" or "what did I just
    pick?" gets grounded: the user selects in AutoCAD, then this returns the
    handles to act on.

    The selection must be made BEFORE any command runs — AutoCAD clears it once
    a command starts. If it comes back empty, ask the user to select the
    objects and try again.

    Args:
        include_geometry (bool): Include geometric properties.
        limit (int): Maximum entities to return.

    Returns:
        str: JSON: {"count": int, "truncated": bool, "handles": [str],
             "entities": [{...}]}
             A count of 0 means nothing is selected.

    Examples:
        - Use when: "change the colour of what I've selected".
        - Don't use when: you can identify the entities by filter instead
          (use autocad_list_entities).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        sel = doc.PickfirstSelectionSet
        total = int(sel.Count)
        if total == 0:
            return {
                "count": 0,
                "truncated": False,
                "handles": [],
                "entities": [],
                "hint": (
                    "Nothing is selected in AutoCAD. Ask the user to select the "
                    "objects first, then call this again. Note that AutoCAD "
                    "clears the selection whenever a command runs."
                ),
            }
        entities = [
            describe(sel.Item(i), include_geometry=include_geometry)
            for i in range(min(total, limit))
        ]
        return {
            "count": total,
            "truncated": total > len(entities),
            "handles": [e["handle"] for e in entities],
            "entities": entities,
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_find_text",
    **tool_meta("Find Text In Drawing", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_find_text(
    query: Annotated[
        str,
        Field(
            description=(
                "Text to search for, e.g. 'FFL' or 'ROOM 12'. Matching is "
                "case-insensitive and matches any part of the string."
            ),
            min_length=1,
        ),
    ],
    include_attributes: Annotated[
        bool,
        Field(
            default=True,
            description=(
                "Also search block attribute values, where door numbers, room "
                "tags and equipment references usually live."
            ),
        ),
    ] = True,
    limit: Annotated[
        int,
        Field(default=50, description="Maximum matches to return.", ge=1, le=MAX_PAGE),
    ] = 50,
) -> str:
    """Search all text, mtext and block attributes for a string.

    This is the fastest way to locate something described by its label — a room
    name, a level marker, a drawing note, an equipment tag.

    Args:
        query (str): Substring to look for, case-insensitive.
        include_attributes (bool): Also search block attribute values.
        limit (int): Maximum matches to return.

    Returns:
        str: JSON: {"query": str, "count": int, "truncated": bool,
             "matches": [{"handle": str, "type": str, "layer": str,
                          "text": str, "position": [x, y, z],
                          "source": "text" | "mtext" | "attribute",
                          "attribute_tag": str,     # attribute matches only
                          "block_name": str}]}      # attribute matches only

    Examples:
        - Use when: "where does it say FFL on this drawing?"
        - Use when: "find the block tagged D-101".
    """
    needle = query.strip().lower()

    def work() -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        kinds = ["text", "mtext"] + (["block"] if include_attributes else [])
        # Every text and every attribute is looked at: the plug-in reads them in
        # one go, as the COM objects they stand for (D-134), and the same loop
        # below reads them; COM, a round trip per property, only for an older one.
        found = plugin_texts([filter_pairs(kind) for kind in kinds], kinds)

        def scan(type_filter: str, entities: Iterable[Any]) -> None:
            for entity in entities:
                if len(matches) >= limit:
                    return
                if type_filter == "block":
                    try:
                        if not bool(entity.HasAttributes):
                            continue
                        attributes = entity.GetAttributes()
                    except BaseException as exc:  # noqa: BLE001
                        raise_if_busy(exc)
                        continue
                    for att in attributes:
                        value = str(att.TextString)
                        if needle in value.lower():
                            matches.append(
                                {
                                    "handle": str(entity.Handle),
                                    "type": "block",
                                    "layer": str(entity.Layer),
                                    "text": value,
                                    "position": point_to_list(entity.InsertionPoint),
                                    "source": "attribute",
                                    "attribute_tag": str(att.TagString),
                                    "block_name": str(entity.Name),
                                }
                            )
                            break
                else:
                    value = str(entity.TextString)
                    if needle in value.lower():
                        matches.append(
                            {
                                "handle": str(entity.Handle),
                                "type": type_filter,
                                "layer": str(entity.Layer),
                                "text": value,
                                "position": point_to_list(entity.InsertionPoint),
                                "source": type_filter,
                            }
                        )

        if found is not None:
            for kind, entities in zip(kinds, found, strict=True):
                scan(kind, entities)
        else:
            doc = get_doc()
            for kind in kinds:
                sel = select_filtered(doc, kind, name=f"MCP_FIND_{kind}")
                try:
                    scan(kind, iter_selection(sel))
                finally:
                    discard_selection_set(doc, f"MCP_FIND_{kind}")

        return {
            "query": query,
            "count": len(matches),
            "truncated": len(matches) >= limit,
            "matches": matches,
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_get_extents",
    **tool_meta("Get Drawing Extents", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_get_extents(
    layer: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Measure the extents of one layer's geometry only. Omit for "
                "the whole drawing."
            ),
        ),
    ] = None,
) -> str:
    """Find the bounding box of the drawing's geometry.

    Use this to size a sheet, place a title block clear of the drawing, or work
    out where to put new geometry relative to what already exists. One layer's
    objects are measured by Heron's plug-in inside AutoCAD in one go; with an
    older plug-in they are measured over COM, slower, with the same answer.

    Args:
        layer (Optional[str]): Restrict to one layer's geometry.

    Returns:
        str: JSON: {"min": [x, y, z], "max": [x, y, z], "width": float,
             "height": float, "center": [x, y], "units": str,
             "entity_count": int}

    Error Handling:
        - Returns an empty-drawing error when there is no geometry to measure,
          rather than the meaningless extents AutoCAD reports for a blank file.
        - A layer holding only rays or construction lines has no extents
          either, and says so.

    Examples:
        - Use when: "how big is this drawing" before choosing a sheet size or
          a viewport scale.
        - Use when: something plots tiny: a stray object far from the rest
          shows up here.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        try:
            units = unit_name(int(doc.GetVariable("INSUNITS")))
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            units = "unknown"

        if layer:
            # Every object on the layer is measured: the plug-in in one go,
            # COM one round trip each, only for an older plug-in (D-114).
            measured = faster_read("entity_extents", _filter_args(None, layer, None, None))
            if measured is not None:
                count = int(measured.get("total", 0))
                # Rounded as bounding_box rounds COM's corners, so width and centre match to the last digit.
                box = {"min": point_to_list(measured.get("min") or []), "max": point_to_list(measured.get("max") or [])}
                found = box_around([box]) if len(box["min"]) == 3 and len(box["max"]) == 3 else None
            else:
                sel = select_filtered(doc, None, layer, None, None)
                try:
                    count = int(sel.Count)
                    found = box_around(bounding_box(entity) for entity in iter_selection(sel)) if count else None
                finally:
                    discard_selection_set(doc)
            if count == 0:
                raise _layer_empty(layer)
            if found is None:
                raise _layer_unmeasured(layer, count)
            lo, hi = found
        else:
            count = int(doc.ModelSpace.Count)
            if count == 0:
                raise AutocadError(
                    "Model space is empty, so the drawing has no extents. Draw "
                    "something first."
                )
            # EXTMIN/EXTMAX only refresh on a regen, so force one.
            doc.Regen(1)
            lo = point_to_list(doc.GetVariable("EXTMIN"))
            hi = point_to_list(doc.GetVariable("EXTMAX"))

        return extents_answer(lo, hi, units, count, layer)

    return dumps(await run(work))


@mcp.tool(
    name="autocad_measure",
    **tool_meta("Measure Distance Or Totals", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_measure(
    point1: Annotated[
        list[float] | None,
        Field(
            default=None,
            description="First point as [x, y], for a point-to-point measurement.",
        ),
    ] = None,
    point2: Annotated[
        list[float] | None,
        Field(
            default=None,
            description="Second point as [x, y], for a point-to-point measurement.",
        ),
    ] = None,
    handles: Annotated[
        list[str] | None,
        Field(
            default=None,
            description=(
                "Entity handles to total up instead. Returns summed length and "
                "summed area across them."
            ),
        ),
    ] = None,
    layer: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Total the length and area of every entity on this layer. "
                "Useful for quantity take-offs."
            ),
        ),
    ] = None,
) -> str:
    """Measure a distance between points, or total lengths and areas.

    Three modes, picked by which arguments you pass:
      - point1 + point2: straight-line distance and bearing between them.
      - handles: summed length and area of those specific entities.
      - layer: summed length and area of everything on that layer.

    Args:
        point1 (Optional[list[float]]): First point for a distance.
        point2 (Optional[list[float]]): Second point for a distance.
        handles (Optional[list[str]]): Entities to total.
        layer (Optional[str]): Layer whose entities to total.

    Returns:
        str: JSON. Point-to-point mode:
        {"mode": "distance", "distance": float, "dx": float, "dy": float,
         "angle_degrees": float, "units": str}

        Totalling mode:
        {"mode": "totals", "entity_count": int, "total_length": float,
         "total_area": float, "units": str, "by_type": {"line": int, ...},
         "counted_length": int, "counted_area": int}

    Examples:
        - Use when: "how far is it from 0,0 to 3000,4000?" -> point1/point2.
        - Use when: "total length of everything on layer PIPE-CWS" -> layer.

    Error Handling:
        - Returns an error naming the three modes if no usable combination of
          arguments is given.
    """
    if point1 and point2:
        mode = "distance"
    elif handles:
        mode = "handles"
    elif layer:
        mode = "layer"
    else:
        raise AutocadError(
            "Nothing to measure. Pass either point1 and point2 for a distance, "
            "or 'handles' for specific entities, or 'layer' to total a layer."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        try:
            units = unit_name(int(doc.GetVariable("INSUNITS")))
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            units = "unknown"

        if mode == "distance":
            dx = float(point2[0]) - float(point1[0])
            dy = float(point2[1]) - float(point1[1])
            dz = (float(point2[2]) if len(point2) > 2 else 0.0) - (
                float(point1[2]) if len(point1) > 2 else 0.0
            )
            return {
                "mode": "distance",
                "distance": round(math.sqrt(dx * dx + dy * dy + dz * dz), 6),
                "distance_2d": round(math.hypot(dx, dy), 6),
                "dx": round(dx, 6),
                "dy": round(dy, 6),
                "dz": round(dz, 6),
                "angle_degrees": round(math.degrees(math.atan2(dy, dx)) % 360.0, 6),
                "units": units,
            }

        if mode == "handles":
            targets = [resolve_handle(doc, h) for h in handles]
        else:
            # Every object on the layer is read: the plug-in in one go, as the
            # COM objects they stand for (D-134); COM, a few round trips each,
            # only for an older plug-in or a class it cannot stand for.
            targets = plugin_lengths(filter_pairs(None, layer, None, None))
            if targets is None:
                sel = select_filtered(doc, None, layer, None, None)
                try:
                    targets = list(iter_selection(sel))
                finally:
                    discard_selection_set(doc)
            if not targets:
                raise AutocadError(
                    f"Layer '{layer}' has no entities on it. Check the name with "
                    "autocad_list_layers."
                )

        total_length = 0.0
        total_area = 0.0
        counted_length = 0
        counted_area = 0
        by_type: Counter[str] = Counter()

        for entity in targets:
            by_type[short_type(entity)] += 1
            # Curves expose Length; arcs use ArcLength instead. Take whichever
            # the entity has, and only once.
            for prop in ("Length", "ArcLength"):
                try:
                    total_length += float(getattr(entity, prop))
                    counted_length += 1
                    break
                except BaseException as exc:  # noqa: BLE001 - type has no length
                    raise_if_busy(exc)
                    continue
            try:
                total_area += float(entity.Area)
                counted_area += 1
            except BaseException as exc:  # noqa: BLE001 - type has no area
                raise_if_busy(exc)

        return {
            "mode": "totals",
            "scope": f"layer '{layer}'" if mode == "layer" else "given handles",
            "entity_count": len(targets),
            "total_length": round(total_length, 6),
            "total_area": round(total_area, 6),
            "counted_length": counted_length,
            "counted_area": counted_area,
            "by_type": dict(by_type.most_common()),
            "units": units,
            "note": (
                "total_length sums entities that have a length (lines, arcs, "
                "polylines); total_area sums those that enclose one (circles, "
                "closed polylines, hatches). Entities without either are "
                "counted in entity_count but contribute nothing."
            ),
        }

    return dumps(await run(work))
