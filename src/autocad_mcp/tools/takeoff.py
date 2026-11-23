"""Take-off: count blocks, total lengths and areas, read and set dynamic block properties.

The ideas come from Lee Mac's Block Counter, Total Length & Area and Dynamic
Block Functions (lee-mac.com). This is Heron's own code, written from the
AutoCAD ActiveX reference: none of Lee Mac's code is used or copied (his terms
do not allow redistribution, D-26).

Grouping and type matching are plain functions over plain data, tested
without AutoCAD; the tools only gather that data over COM.
"""

from __future__ import annotations

import fnmatch
import math
from collections.abc import Callable, Iterable
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.curves import curve_length
from ..acad.entities import resolve_handle
from ..acad.selection import (
    discard_selection_set,
    filter_pairs,
    iter_selection,
    select_filtered,
)
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import before_after, faster_read, same_value

BlockGroup = Literal["name", "name_layer", "name_visibility", "name_properties"]
LengthGroup = Literal["layer", "type", "none"]


def count_blocks(refs: list[dict], group_by: BlockGroup) -> dict[str, Any]:
    """Count block references. Pure: refs are {block, layer, visibility, properties}."""
    keys = {
        "name": ("block",),
        "name_layer": ("block", "layer"),
        "name_visibility": ("block", "visibility"),
        "name_properties": ("block", "properties"),
    }[group_by]
    counts: dict[tuple, dict[str, Any]] = {}
    for ref in refs:
        row = {key: ref.get(key) for key in keys}
        marker = tuple(repr(sorted(v.items())) if isinstance(v, dict) else repr(v) for v in row.values())
        counts.setdefault(marker, {**row, "count": 0})["count"] += 1
    rows = sorted(counts.values(), key=lambda r: tuple(str(r.get(k)) for k in keys))
    return {"total": len(refs), "rows": rows}


def total_lengths(items: list[dict], group_by: LengthGroup) -> dict[str, Any]:
    """Sum length and area. Pure: items are {type, layer, length, area}, None when not measurable."""
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        key = "all" if group_by == "none" else str(item.get(group_by))
        row = groups.setdefault(key, {group_by if group_by != "none" else "group": key, "count": 0, "length": 0.0, "area": 0.0, "unmeasured": 0})
        row["count"] += 1
        if item.get("length") is None:
            row["unmeasured"] += 1
        else:
            row["length"] += float(item["length"])
        if item.get("area"):
            row["area"] += float(item["area"])
    rows = [groups[k] for k in sorted(groups)]
    return {
        "total_length": sum(r["length"] for r in rows),
        "total_area": sum(r["area"] for r in rows),
        "rows": rows,
    }


def coerce_value(current: Any, new: Any, allowed: list | None = None) -> Any:
    """Turn a requested value into the type the property already holds.

    A dynamic property refuses a value of the wrong COM type (a string for a
    distance), and agents often send numbers as text, so the current value's
    type decides. A list of allowed values, when the block has one, is enforced.
    """
    if isinstance(current, bool):
        value: Any = str(new).strip().lower() in {"1", "true", "yes", "on"}
    elif isinstance(current, int):
        value = int(float(new))
    elif isinstance(current, float):
        value = float(new)
    else:
        value = str(new)
    if allowed:
        matches = [a for a in allowed if a == value or (isinstance(a, str) and str(a).lower() == str(value).lower())]
        if not matches:
            raise ValueError(f"{new!r} is not one of the allowed values: {list(allowed)}")
        value = matches[0]
    return value


_CURVES = {"AcDbLine", "AcDbPolyline", "AcDb2dPolyline", "AcDb3dPolyline", "AcDbArc", "AcDbCircle",
           "AcDbEllipse", "AcDbSpline"}


def is_curve(object_name: str) -> bool:
    """Only curves have a length; leaders, text, blocks and dimensions are not runs."""
    return object_name in _CURVES


def _length(entity: Any) -> float | None:
    return curve_length(entity)


def expand_nested(refs: list[dict], children: dict[str, list[tuple[str, str]]], limit: int = 20) -> list[dict]:
    """Top-level refs plus every block nested inside them, once per placed copy.

    children: block name -> [(nested block name, layer)] as defined. A block
    that contains itself stops at 'limit' levels instead of looping forever.
    """
    out = list(refs)

    def walk(name: str, depth: int) -> None:
        if depth >= limit:
            return
        for child, layer in children.get(name, []):
            out.append({"block": child, "layer": layer, "visibility": None, "properties": {}, "nested": True})
            walk(child, depth + 1)

    for ref in refs:
        walk(ref["block"], 1)
    return out


def _children(doc: Any) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for i in range(doc.Blocks.Count):
        block = doc.Blocks.Item(i)
        try:
            if block.IsLayout or block.IsXRef:
                continue
            name = str(block.Name)
            for j in range(int(block.Count)):
                item = block.Item(j)
                if str(item.ObjectName) == "AcDbBlockReference":
                    out.setdefault(name, []).append((str(getattr(item, "EffectiveName", None) or item.Name), str(item.Layer)))
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            continue
    return out


_ALWAYS_CLOSED = {"AcDbCircle", "AcDbRegion"}


def _area(entity: Any) -> float | None:
    """Area of a closed shape only: COM also gives open polylines and arcs an area."""
    try:
        if str(entity.ObjectName) not in _ALWAYS_CLOSED and not bool(getattr(entity, "Closed", False)):
            return None
        return float(entity.Area)
    except BaseException as exc:  # noqa: BLE001
        raise_if_busy(exc)
        return None


# ---- lengths and areas read by the plug-in in one go (#195, D-134) -------------

# Which COM property gives each class its length, and whether COM gives it an
# Area and a Closed flag, as AutoCAD's own type libraries list them (axdb24enu,
# axdb25enu and axdb26enu.tlb: the same in all three). The plug-in reads more
# off the .NET object than COM gives (an ellipse is Closed, a 3D polyline has an
# Area); only what is listed here is kept. A class not listed is read over COM
# whenever a tool would read it.
_NO_LENGTH_OR_AREA = (
    "AcDbText", "AcDbMText", "AcDbBlockReference", "AcDbMInsertBlock", "AcDbAttributeDefinition",
    "AcDbPoint", "AcDbXline", "AcDbRay", "AcDbLeader", "AcDbMLeader", "AcDbTable", "AcDbFace",
    "AcDbSolid", "AcDbTrace", "AcDb3dSolid", "AcDbMline", "AcDbWipeout", "AcDbRasterImage",
    "AcDbViewport", "AcDbHelix", "AcDbFcf", "AcDbShape", "AcDbPolyFaceMesh", "AcDbPolygonMesh",
    "AcDbRotatedDimension", "AcDbAlignedDimension", "AcDb2LineAngularDimension",
    "AcDb3PointAngularDimension", "AcDbDiametricDimension", "AcDbRadialDimension",
    "AcDbRadialDimensionLarge", "AcDbOrdinateDimension", "AcDbArcDimension",
)
COM_FACTS: dict[str, tuple[str | None, bool, bool]] = {
    "AcDbLine": ("Length", False, False),
    "AcDbPolyline": ("Length", True, True),
    "AcDb2dPolyline": ("Length", True, True),
    "AcDb3dPolyline": ("Length", False, True),
    "AcDbArc": ("ArcLength", True, False),
    "AcDbCircle": ("Circumference", True, False),
    "AcDbEllipse": (None, True, False),
    "AcDbSpline": (None, True, True),
    "AcDbHatch": (None, True, False),
    "AcDbRegion": (None, True, False),
    **dict.fromkeys(_NO_LENGTH_OR_AREA, (None, False, False)),
}


def plugin_number(value: Any) -> float:
    """A number from the plug-in as COM gives it (a float); NotTheSame for anything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise NotTheSame(f"a number that is not one: {value!r}")  # "not finite" among them
    return float(value)


def _numbers(values: Any) -> tuple[float, ...]:
    if not isinstance(values, list):
        raise NotTheSame("a list of numbers that is not one")
    return tuple(plugin_number(v) for v in values)


def _shape(kind: str, shape: Any) -> dict[str, Any]:
    """A spline's or an ellipse's definition under COM's property names, for curve_length."""
    if not isinstance(shape, list) or not shape:
        raise NotTheSame("a definition of the wrong shape")
    if shape[0] == "spline" and kind == "AcDbSpline" and len(shape) == 6:
        _, degree, rational, points, knots, weights = shape
        if isinstance(degree, bool) or not isinstance(degree, int) or not isinstance(rational, bool):
            raise NotTheSame("a spline's degree or rational flag")
        found: dict[str, Any] = {
            "Degree": degree, "IsRational": rational, "ControlPoints": _numbers(points), "Knots": _numbers(knots),
        }
        if rational:
            found["Weights"] = _numbers(weights)
        return found
    if shape[0] == "ellipse" and kind == "AcDbEllipse" and len(shape) == 5:
        major, minor, start, end = (plugin_number(v) for v in shape[1:])
        return {"MajorRadius": major, "MinorRadius": minor, "StartParameter": start, "EndParameter": end}
    raise NotTheSame(f"a definition {shape[0]!r} for a {kind}")


class PluginEntity:
    """One object of the plug-in's entity_lengths, as the COM object it stands for (D-134).

    It has only the properties COM has for its class (COM_FACTS); reading any
    other raises AttributeError, as COM does. So curve_length, _area and
    autocad_measure's loop read it with the code they read COM with, and the
    answer is the same either way. A length or area the plug-in could not
    read is missing too: COM's read of it fails the same way.
    """

    def __init__(self, row: Any) -> None:
        if not isinstance(row, list) or len(row) != 6:
            raise NotTheSame("a row of the wrong shape")
        kind, layer, length, area, closed, shape = row
        if not isinstance(kind, str) or not isinstance(layer, str):
            raise NotTheSame("a class or layer that is not text")
        if kind not in COM_FACTS:
            raise NotTheSame(f"a {kind}: which length and area COM gives it is not known here")
        prop, has_area, has_closed = COM_FACTS[kind]
        facts: dict[str, Any] = {}
        length = None if length is None else plugin_number(length)
        area = None if area is None else plugin_number(area)
        if prop and length is not None:
            facts[prop] = length
        if has_area and area is not None:
            facts["Area"] = area
        if has_closed:
            if not isinstance(closed, bool):
                raise NotTheSame(f"a {kind} without its Closed flag")
            facts["Closed"] = closed
        # .NET's Helix is a Spline, so a helix may come with a spline's definition: COM gives it none.
        if shape is not None and kind in ("AcDbSpline", "AcDbEllipse"):
            facts.update(_shape(kind, shape))
        self.ObjectName = kind
        self.Layer = layer
        self._facts = facts

    def __getattr__(self, name: str) -> Any:
        facts = self.__dict__.get("_facts", {})
        if name in facts:
            return facts[name]
        raise AttributeError(name)


def plugin_entities(read: dict[str, Any]) -> list[PluginEntity]:
    """The objects of the plug-in's entity_lengths answer; NotTheSame when it is not one this server reads as COM."""
    items = read.get("items")
    if not isinstance(items, list):
        raise NotTheSame("an answer without its items")
    return [PluginEntity(row) for row in items]


def plugin_lengths(pairs: Iterable[tuple[int, Any]], classes: Iterable[str] | None = None) -> list[PluginEntity] | None:
    """The selected objects' lengths and areas, read by the plug-in in one go (#195); None: read them over COM."""
    args: dict[str, Any] = {"filter": [[code, value] for code, value in pairs]}
    if classes is not None:
        args["classes"] = sorted(classes)
    read = faster_read("entity_lengths", args)
    if read is None:
        return None
    try:
        return plugin_entities(read)
    except (TypeError, ValueError, KeyError):  # NotTheSame, or an answer of the wrong shape
        return None


def _length_items(entities: Iterable[Any]) -> list[dict[str, Any]]:
    """The curves autocad_total_length sums, read off COM objects or the plug-in's (the same code)."""
    items: list[dict[str, Any]] = []
    for entity in entities:
        kind = str(entity.ObjectName)
        if not is_curve(kind):
            continue
        items.append({"type": kind, "layer": str(entity.Layer), "length": _length(entity), "area": _area(entity)})
    return items


def _dynamic_properties(ref: Any) -> list[Any]:
    try:
        if not ref.IsDynamicBlock:
            return []
        return list(ref.GetDynamicBlockProperties())
    except BaseException as exc:  # noqa: BLE001 - not a block reference
        raise_if_busy(exc)
        return []


def _plain(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


Property = tuple[str, Callable[[], Any], Callable[[], Any]]


def block_ref(block: str, layer: str, properties: Iterable[Property]) -> dict[str, Any]:
    """One placed block as count_blocks takes it, read over COM or by the plug-in (D-127).

    properties are (name, read_only, value) in AutoCAD's order, the last two
    as calls, so COM reads a flag or a value only when it is needed. The
    visibility state is the property whose name starts Visibility; the others
    kept are those the modeller can change, except Origin.
    """
    visibility = None
    found: dict[str, Any] = {}
    for name, read_only, value in properties:
        if name.lower().startswith("visibility"):
            visibility = _plain(value())
        elif not read_only() and name.lower() != "origin":
            found[name] = _plain(value())
    return {"block": block, "layer": layer, "visibility": visibility, "properties": found}


def _describe_ref(ref: Any) -> dict[str, Any]:
    properties = (
        (str(prop.PropertyName), lambda prop=prop: prop.ReadOnly, lambda prop=prop: prop.Value)
        for prop in _dynamic_properties(ref)
    )
    return block_ref(str(getattr(ref, "EffectiveName", None) or ref.Name), str(ref.Layer), properties)


class NotTheSame(ValueError):
    """The plug-in's answer cannot give the same count as COM: read it over COM instead."""


class _NoValue(Exception):
    """AutoCAD would not give this value; over COM the reference is then skipped."""


def plugin_value(kind: Any, value: Any) -> Any:
    """A dynamic property's value as COM gives it, from the plug-in's [kind, value] (D-127).

    The plug-in's JSON writes a whole-number distance as 50, which reads back
    as an int while COM gives 50.0; the kind turns it back, so a count by size
    does not split in two.
    """
    if kind == "real" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if kind == "int" and isinstance(value, int) and not isinstance(value, bool):
        return value
    if kind == "text" and isinstance(value, str):
        return value
    if kind == "point" and isinstance(value, list):
        return [plugin_value("real", axis) for axis in value]
    if kind == "none":
        return None
    if kind == "error":
        raise _NoValue
    raise NotTheSame(f"a dynamic property value of kind {kind!r}")  # "other": only COM gives it the same way


def refs_from_plugin(read: dict[str, Any], nested: bool) -> list[dict[str, Any]]:
    """The references count_blocks counts, from the plug-in's block_references (#192).

    Built with block_ref, as the COM path builds them, then expand_nested over
    the plug-in's children. NotTheSame when the answer is not one this server
    reads the same way as COM.
    """
    refs = read.get("refs")
    if not isinstance(refs, list) or (nested and not isinstance(read.get("children"), list)):
        raise NotTheSame("an answer without its refs, or without the children asked for")
    out: list[dict[str, Any]] = []
    for block, layer, properties in refs:
        given = (
            (str(name), lambda flag=read_only: bool(flag), lambda kind=kind, value=value: plugin_value(kind, value))
            for name, read_only, kind, value in properties
        )
        try:
            out.append(block_ref(str(block), str(layer), given))
        except _NoValue:
            continue  # over COM, a value AutoCAD would not give skips the reference
    if nested:
        children: dict[str, list[tuple[str, str]]] = {}
        for parent, inside in read["children"]:
            children.setdefault(str(parent), []).extend((str(block), str(layer)) for block, layer in inside)
        out = expand_nested(out, children)
    return out


def _plugin_refs(layer: str | None, nested: bool) -> list[dict[str, Any]] | None:
    """Every placed block, read by the plug-in in one go (#192); None: read them over COM."""
    args: dict[str, Any] = {"filter": [[code, value] for code, value in filter_pairs("insert", layer)]}
    if nested:
        args["nested"] = True
    read = faster_read("block_references", args)
    if read is None:
        return None
    try:
        return refs_from_plugin(read, nested)
    except (TypeError, ValueError, KeyError):  # NotTheSame, or an answer of the wrong shape
        return None


def _com_refs(layer: str | None, nested: bool) -> list[dict[str, Any]]:
    """Every placed block over COM: about five round trips each, and three per dynamic property."""
    doc = get_doc()
    sel = select_filtered(doc, entity_type="insert", layer=layer)
    refs: list[dict[str, Any]] = []
    try:
        for ref in iter_selection(sel):
            try:
                row = _describe_ref(ref)
            except BaseException as exc:  # noqa: BLE001 - not a block reference after all
                raise_if_busy(exc)
                continue
            refs.append(row)
    finally:
        discard_selection_set(doc)
    if nested:  # walk every top-level block: a DESK can sit inside a ROOM
        refs = expand_nested(refs, _children(doc))
    return refs


@mcp.tool(name="autocad_count_blocks", **tool_meta("Count Blocks", read_only=True, idempotent=True))
@tool_errors
async def autocad_count_blocks(
    block_name: Annotated[str | None, Field(description="Only blocks whose real name matches, wildcards allowed: 'VALVE*'.")] = None,
    layer: Annotated[str | None, Field(description="Only blocks on this layer (wildcards allowed).")] = None,
    group_by: Annotated[BlockGroup, Field(description=(
        "name; name_layer; name_visibility (dynamic block visibility state); "
        "name_properties (dynamic property values such as size)."
    ))] = "name",
    include_nested: Annotated[bool, Field(description="Also count blocks inside blocks (e.g. fixtures inside a room block).")] = False,
) -> str:
    """Count block references for a quantity take-off: fittings, valves, devices.

    Dynamic blocks are counted by their real name, not the *U names AutoCAD
    gives their copies. Group by visibility state or property values to count
    each size or type separately.

    Returns:
        JSON: {"total": n, "rows": [{"block", ..., "count"}]}

    Examples:
        - Use when: "how many diffusers on this floor" -> grouped by block
          name, optionally per layer.
        - Use when: pricing or ordering: this is the take-off count.
    """

    def work() -> list[dict[str, Any]]:
        refs = _plugin_refs(layer, include_nested)
        if refs is None:
            refs = _com_refs(layer, include_nested)
        if block_name:
            refs = [r for r in refs if fnmatch.fnmatch(r["block"].lower(), block_name.lower())]
        return refs

    return dumps(count_blocks(await run(work), group_by))


@mcp.tool(name="autocad_total_length", **tool_meta("Total Length and Area", read_only=True, idempotent=True))
@tool_errors
async def autocad_total_length(
    entity_type: Annotated[str | None, Field(description="Only this type: line, polyline, arc, circle...")] = None,
    layer: Annotated[str | None, Field(description="Only this layer (wildcards allowed: 'P-*').")] = None,
    group_by: Annotated[LengthGroup, Field(description="layer, type, or none for one total.")] = "layer",
) -> str:
    """Total length (and area of closed shapes) for a run take-off: pipe, duct, cable.

    Lengths are in drawing units (check autocad_status). Splines and ellipses
    are measured from their definition.

    Returns:
        JSON: {"total_length", "total_area", "rows": [{layer|type, count, length, area, unmeasured}]}

    Examples:
        - Use when: "how many metres of DN50 pipe on this layer" ->
          layer="M-PIPE-DN50".
        - Use when: cable, duct, kerb, skirting - anything bought by the
          metre.
    """

    def work() -> list[dict[str, Any]]:
        # Every curve is read: the plug-in in one go, COM 7-10 round trips each, only for an older one.
        entities = plugin_lengths(filter_pairs(entity_type, layer), _CURVES)
        if entities is not None:
            return _length_items(entities)
        doc = get_doc()
        sel = select_filtered(doc, entity_type=entity_type, layer=layer)
        try:
            return _length_items(iter_selection(sel))
        finally:
            discard_selection_set(doc)

    return dumps(total_lengths(await run(work), group_by))


@mcp.tool(name="autocad_get_dynamic_properties", **tool_meta("Get Dynamic Block Properties", read_only=True, idempotent=True))
@tool_errors
async def autocad_get_dynamic_properties(
    handle: Annotated[str, Field(min_length=1, description="Handle of a dynamic block reference.")],
) -> str:
    """List a dynamic block's properties: value, allowed choices, read-only.

    Use before autocad_set_dynamic_properties to see the names and choices
    (visibility states, lookup sizes, stretch distances).

    Returns:
        JSON: {"handle", "block", "properties": [{name, value, allowed, read_only, description}]}

    Examples:
        - Use when: a dynamic block is not showing what you expect and you
          need its real property names and allowed values first.
        - Use when: before autocad_set_dynamic_properties, so you pass a value
          the block will accept.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        ref = resolve_handle(doc, handle)
        props = _dynamic_properties(ref)
        if not props:
            raise AutocadError(f"'{handle}' is not a dynamic block reference.")
        return {
            "handle": str(ref.Handle),
            "block": str(getattr(ref, "EffectiveName", None) or ref.Name),
            "properties": [
                {
                    "name": str(p.PropertyName),
                    "value": _plain(p.Value),
                    "allowed": _plain(list(p.AllowedValues or ())),
                    "read_only": bool(p.ReadOnly),
                    "description": str(p.Description),
                }
                for p in props
            ],
        }

    return dumps(await run(work))


@mcp.tool(name="autocad_set_dynamic_properties", **tool_meta("Set Dynamic Block Properties"))
@tool_errors
async def autocad_set_dynamic_properties(
    handle: Annotated[str, Field(min_length=1, description="Handle of a dynamic block reference.")],
    values: Annotated[dict[str, Any], Field(description="{property name: new value}, e.g. {'Visibility1': 'GATE', 'Size': 80}.")],
) -> str:
    """Change a dynamic block's properties: visibility state, size, distance, flip.

    Names are matched without regard to case. Each value is converted to the
    property's own type and checked against its allowed values; the ones that
    cannot be set are listed in 'failed' with the reason. One undo step.

    Returns:
        JSON: {"handle", "changed": {name: value}, "failed": {name: reason},
        "before_after": [{handle, property, from, to}], "already": [names already so]}

    Examples:
        - Use when: "switch those doors to the 900 leaf" -> the width
          property, or the visibility state.
        - Don't use when: you do not know the property names - read them with
          autocad_get_dynamic_properties first.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ref = resolve_handle(doc, handle)
        props = {str(p.PropertyName).lower(): p for p in _dynamic_properties(ref)}
        if not props:
            raise AutocadError(f"'{handle}' is not a dynamic block reference.")
        changed: dict[str, Any] = {}
        failed: dict[str, str] = {}
        already: list[str] = []
        rows: list[dict[str, Any]] = []
        # First look: the value now. Only what differs is written; nothing to
        # write opens no undo step (D-62).
        planned: list[tuple[str, Any, Any, Any]] = []
        for name, new in values.items():
            prop = props.get(str(name).lower())
            if prop is None:
                failed[name] = "no such property; see autocad_get_dynamic_properties"
                continue
            label = str(prop.PropertyName)
            if prop.ReadOnly:
                failed[label] = "read-only"
                continue
            try:
                old = _plain(prop.Value)
                value = coerce_value(prop.Value, new, _plain(list(prop.AllowedValues or ())))
            except BaseException as exc:  # noqa: BLE001 - report and carry on
                raise_if_busy(exc)
                failed[label] = str(exc)
                continue
            if same_value(old, _plain(value)):
                already.append(label)
            else:
                planned.append((label, prop, old, value))
        if planned:
            with undo_mark(doc):
                for label, prop, old, value in planned:
                    try:
                        prop.Value = value
                        changed[label] = value
                        rows.append({"handle": str(ref.Handle), "property": label, "from": old, "to": _plain(value)})
                    except BaseException as exc:  # noqa: BLE001 - report and carry on
                        raise_if_busy(exc)
                        failed[label] = str(exc)
        result = {"handle": str(ref.Handle), "changed": changed, "failed": failed, **before_after(rows)}
        if already:
            result["already"] = already
        return result

    return dumps(await run(work))
