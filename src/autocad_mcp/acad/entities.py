"""Reading and describing AutoCAD entities.

AutoCAD exposes each entity as a late-bound COM object whose useful properties
depend on its type. This module turns those objects into plain dictionaries the
agent can reason about, keyed by the drawing handle — the identity every
modify, query and delete tool accepts.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.variants import group_coordinates, point_to_list
from .units import deg, round_or_none

# ObjectName reported by COM -> the short type name this server reports back.
OBJECT_NAME_MAP = {
    "AcDbLine": "line",
    "AcDbCircle": "circle",
    "AcDbArc": "arc",
    "AcDbPolyline": "polyline",
    "AcDb2dPolyline": "polyline2d",
    "AcDb3dPolyline": "polyline3d",
    "AcDbText": "text",
    "AcDbMText": "mtext",
    "AcDbBlockReference": "block",
    "AcDbMInsertBlock": "block",
    "AcDbEllipse": "ellipse",
    "AcDbSpline": "spline",
    "AcDbPoint": "point",
    "AcDbHatch": "hatch",
    "AcDbSolid": "solid",
    "AcDbRegion": "region",
    "AcDb3dSolid": "3dsolid",
    "AcDbMline": "multiline",
    "AcDbRay": "ray",
    "AcDbXline": "xline",
    "AcDbLeader": "leader",
    "AcDbMLeader": "mleader",
    "AcDbViewport": "viewport",
    "AcDbAttributeDefinition": "attdef",
    "AcDbRasterImage": "image",
    "AcDbWipeout": "wipeout",
    "AcDbTable": "table",
}


def _try(getter, default=None):
    """Read one COM property, tolerating types that do not implement it."""
    try:
        return getter()
    except BaseException as exc:  # noqa: BLE001 - absent properties are expected here
        raise_if_busy(exc)
        return default


def short_type(entity: Any) -> str:
    """Map a COM entity to this server's short type name."""
    name = _try(lambda: str(entity.ObjectName), "")
    if name in OBJECT_NAME_MAP:
        return OBJECT_NAME_MAP[name]
    # Dimensions come in eight concrete classes that all behave the same here.
    if name.startswith("AcDb") and "Dimension" in name:
        return "dimension"
    return name or "unknown"


def describe(entity: Any, include_geometry: bool = True) -> dict[str, Any]:
    """Serialize one entity into a plain dict.

    Common properties are always present so a list of mixed entities is still
    scannable; the type-specific block adds whatever that entity actually has.
    """
    info: dict[str, Any] = {
        "handle": _try(lambda: str(entity.Handle), ""),
        "type": short_type(entity),
        "layer": _try(lambda: str(entity.Layer), ""),
    }

    color = _try(lambda: int(entity.Color))
    if color is not None:
        info["color"] = color
    linetype = _try(lambda: str(entity.Linetype))
    if linetype:
        info["linetype"] = linetype

    if not include_geometry:
        return info

    kind = info["type"]

    if kind == "line":
        info["start"] = point_to_list(_try(lambda: entity.StartPoint, []))
        info["end"] = point_to_list(_try(lambda: entity.EndPoint, []))
        info["length"] = round_or_none(_try(lambda: entity.Length))
        info["angle_degrees"] = deg(_try(lambda: entity.Angle))

    elif kind == "circle":
        info["center"] = point_to_list(_try(lambda: entity.Center, []))
        info["radius"] = round_or_none(_try(lambda: entity.Radius))
        info["area"] = round_or_none(_try(lambda: entity.Area))

    elif kind == "arc":
        info["center"] = point_to_list(_try(lambda: entity.Center, []))
        info["radius"] = round_or_none(_try(lambda: entity.Radius))
        info["start_angle_degrees"] = deg(_try(lambda: entity.StartAngle))
        info["end_angle_degrees"] = deg(_try(lambda: entity.EndAngle))
        info["arc_length"] = round_or_none(_try(lambda: entity.ArcLength))

    elif kind in {"polyline", "polyline2d", "polyline3d"}:
        stride = 3 if kind == "polyline3d" else 2
        coords = _try(lambda: entity.Coordinates, [])
        vertices = group_coordinates(coords, stride)
        info["vertices"] = vertices
        info["vertex_count"] = len(vertices)
        info["closed"] = bool(_try(lambda: entity.Closed, False))
        info["length"] = round_or_none(_try(lambda: entity.Length))
        if info["closed"]:
            info["area"] = round_or_none(_try(lambda: entity.Area))

    elif kind == "text":
        info["text"] = _try(lambda: str(entity.TextString), "")
        info["insertion_point"] = point_to_list(_try(lambda: entity.InsertionPoint, []))
        info["height"] = round_or_none(_try(lambda: entity.Height))
        info["rotation_degrees"] = deg(_try(lambda: entity.Rotation))
        info["style"] = _try(lambda: str(entity.StyleName), "")

    elif kind == "mtext":
        info["text"] = _try(lambda: str(entity.TextString), "")
        info["insertion_point"] = point_to_list(_try(lambda: entity.InsertionPoint, []))
        info["height"] = round_or_none(_try(lambda: entity.Height))
        info["width"] = round_or_none(_try(lambda: entity.Width))
        info["rotation_degrees"] = deg(_try(lambda: entity.Rotation))

    elif kind == "block":
        info["block_name"] = _try(lambda: str(entity.Name), "")
        info["insertion_point"] = point_to_list(_try(lambda: entity.InsertionPoint, []))
        info["rotation_degrees"] = deg(_try(lambda: entity.Rotation))
        info["scale"] = [
            round_or_none(_try(lambda: entity.XScaleFactor, 1.0)),
            round_or_none(_try(lambda: entity.YScaleFactor, 1.0)),
            round_or_none(_try(lambda: entity.ZScaleFactor, 1.0)),
        ]
        if _try(lambda: bool(entity.HasAttributes), False):
            info["attributes"] = read_attributes(entity)

    elif kind == "ellipse":
        info["center"] = point_to_list(_try(lambda: entity.Center, []))
        info["major_radius"] = round_or_none(_try(lambda: entity.MajorRadius))
        info["minor_radius"] = round_or_none(_try(lambda: entity.MinorRadius))
        info["area"] = round_or_none(_try(lambda: entity.Area))

    elif kind == "hatch":
        info["pattern"] = _try(lambda: str(entity.PatternName), "")
        info["area"] = round_or_none(_try(lambda: entity.Area))
        info["loop_count"] = _try(lambda: int(entity.NumberOfLoops))

    elif kind == "point":
        info["position"] = point_to_list(_try(lambda: entity.Coordinates, []))

    elif kind == "dimension":
        info["measurement"] = round_or_none(_try(lambda: entity.Measurement))
        info["text_override"] = _try(lambda: str(entity.TextOverride), "")
        info["style"] = _try(lambda: str(entity.StyleName), "")

    elif kind == "spline":
        info["closed"] = bool(_try(lambda: entity.Closed, False))
        info["control_point_count"] = _try(lambda: int(entity.NumberOfControlPoints))

    elif kind == "region":
        info["area"] = round_or_none(_try(lambda: entity.Area))

    return info


def read_attributes(block_ref: Any) -> dict[str, str]:
    """A block reference's attribute tag/value pairs."""
    result: dict[str, str] = {}
    try:
        for att in block_ref.GetAttributes():
            result[str(att.TagString)] = str(att.TextString)
    except BaseException as exc:  # noqa: BLE001 - block may carry no attributes
        raise_if_busy(exc)
    return result


def bounding_box(entity: Any) -> dict[str, list[float]] | None:
    """An entity's bounding box, or None if it has no extents."""
    try:
        lo, hi = entity.GetBoundingBox()
        return {"min": point_to_list(lo), "max": point_to_list(hi)}
    except BaseException as exc:  # noqa: BLE001
        raise_if_busy(exc)
        return None


def resolve_handle(doc: Any, handle: str) -> Any:
    """Look up one entity by its drawing handle.

    Handles are the stable identity handed back to the agent, so every
    modify/delete tool routes through here.
    """
    try:
        return doc.HandleToObject(str(handle).strip())
    except BaseException as exc:  # noqa: BLE001
        raise_if_busy(exc)
        raise AutocadError(
            f"No entity with handle '{handle}' exists in the active drawing. "
            "Handles are per-drawing and change when a drawing is recreated — "
            "re-run autocad_list_entities for current handles. "
            f"(details: {com_message(exc)})"
        ) from exc


def resolve_handles(doc: Any, handles: Iterable[str]) -> list[Any]:
    """Look up many entities, failing on the first handle that is not valid."""
    return [resolve_handle(doc, h) for h in handles]
