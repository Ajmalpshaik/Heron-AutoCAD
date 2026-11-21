"""Selection sets and DXF filters.

Scanning ModelSpace item by item is O(n) across an out-of-process COM boundary
and gets slow past a few thousand entities. A filtered selection set pushes the
matching down into AutoCAD, so listing "all doors on A-DOOR" stays fast in a
large drawing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..core.errors import raise_if_busy
from ..core.variants import int_array, variant_array

# DXF group codes used in selection filters.
DXF_ENTITY_TYPE = 0
DXF_TEXT_VALUE = 1
DXF_BLOCK_NAME = 2
DXF_LINETYPE = 6
DXF_LAYER = 8
DXF_COLOR = 62

# AutoCAD AcSelect modes.
SELECT_WINDOW = 0
SELECT_CROSSING = 1
SELECT_PREVIOUS = 3
SELECT_LAST = 4
SELECT_ALL = 5

# Friendly names an agent may use -> the DXF type string AutoCAD filters on.
ENTITY_TYPE_ALIASES = {
    "line": "LINE",
    "circle": "CIRCLE",
    "arc": "ARC",
    "polyline": "LWPOLYLINE",
    "lwpolyline": "LWPOLYLINE",
    "polyline2d": "POLYLINE",
    "polyline3d": "POLYLINE",
    "text": "TEXT",
    "mtext": "MTEXT",
    "block": "INSERT",
    "blockreference": "INSERT",
    "insert": "INSERT",
    "dimension": "DIMENSION",
    "hatch": "HATCH",
    "ellipse": "ELLIPSE",
    "spline": "SPLINE",
    "point": "POINT",
    "solid": "SOLID",
    "region": "REGION",
    "leader": "LEADER",
    "mleader": "MULTILEADER",
    "viewport": "VIEWPORT",
    "attdef": "ATTDEF",
    "ray": "RAY",
    "xline": "XLINE",
    "table": "ACAD_TABLE",
    "wipeout": "WIPEOUT",
    "image": "IMAGE",
}

TEMP_SELSET_NAME = "MCP_TEMP_SELSET"


def dxf_type_for(entity_type: str) -> str:
    """Resolve a friendly type name to the DXF name used in filters."""
    return ENTITY_TYPE_ALIASES.get(
        entity_type.strip().lower(), entity_type.strip().upper()
    )


def build_filter(
    entity_type: str | None = None,
    layer: str | None = None,
    block_name: str | None = None,
    color: int | None = None,
) -> tuple[Any | None, Any | None]:
    """Build the (codes, values) VARIANT pair a selection set filters on.

    Returns (None, None) when nothing was requested, which tells AutoCAD to
    select everything.

    Layer and block-name values pass through unchanged, so AutoCAD's own
    wildcards work: "A-*" matches every layer starting with A-.
    """
    codes: list[int] = []
    values: list[Any] = []

    if entity_type:
        codes.append(DXF_ENTITY_TYPE)
        values.append(dxf_type_for(entity_type))
    if layer:
        codes.append(DXF_LAYER)
        values.append(layer.strip())
    if block_name:
        codes.append(DXF_BLOCK_NAME)
        values.append(block_name.strip())
    if color is not None:
        codes.append(DXF_COLOR)
        values.append(int(color))

    if not codes:
        return None, None
    return int_array(codes), variant_array(values)


def make_selection_set(doc: Any, name: str = TEMP_SELSET_NAME) -> Any:
    """Get the scratch selection set, creating it only if it does not exist.

    Adding or deleting a named selection set changes the drawing database, and
    AutoCAD charges an undo step for it — measured. Creating and deleting one
    per read would mean the user's Ctrl+Z undoes Claude *looking* at the
    drawing instead of their own last edit, which is both baffling and useless.

    So the set is created once per drawing and emptied for reuse afterwards.
    AutoCAD also refuses to add a name that is already taken, which the reuse
    path handles for free.
    """
    try:
        existing = doc.SelectionSets.Item(name)
        existing.Clear()
        return existing
    except BaseException as exc:  # noqa: BLE001 - not created yet, fall through
        raise_if_busy(exc)
    return doc.SelectionSets.Add(name)


def discard_selection_set(doc: Any, name: str = TEMP_SELSET_NAME) -> None:
    """Empty the scratch selection set, keeping the set itself for reuse.

    Deliberately not a Delete: see make_selection_set for why deleting costs
    the user an undo step.
    """
    try:
        doc.SelectionSets.Item(name).Clear()
    except BaseException:  # noqa: BLE001 - nothing to clear
        pass


def select_filtered(
    doc: Any,
    entity_type: str | None = None,
    layer: str | None = None,
    block_name: str | None = None,
    color: int | None = None,
    name: str = TEMP_SELSET_NAME,
) -> Any:
    """Select every entity in the drawing matching the given filter."""
    sel = make_selection_set(doc, name)
    codes, values = build_filter(entity_type, layer, block_name, color)
    if codes is None:
        sel.Select(SELECT_ALL)
    else:
        sel.Select(SELECT_ALL, None, None, codes, values)
    return sel


def iter_selection(sel_set: Any) -> Iterable[Any]:
    """Yield each entity in a selection set."""
    for i in range(sel_set.Count):
        yield sel_set.Item(i)
