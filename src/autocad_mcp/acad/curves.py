"""Read curves from AutoCAD as plain paths and lengths for acad/geometry.py."""

from __future__ import annotations

import math
from typing import Any

from ..core.errors import AutocadError, raise_if_busy
from ..core.variants import group_coordinates
from . import geometry


def read_path(entity: Any) -> dict[str, Any]:
    """A line, polyline, arc or circle as {"vertices", "bulges", "closed"} (2D, WCS)."""
    kind = str(entity.ObjectName)
    if kind == "AcDbLine":
        s, e = entity.StartPoint, entity.EndPoint
        return {"vertices": [(s[0], s[1]), (e[0], e[1])], "bulges": [0.0], "closed": False}
    if kind in ("AcDbPolyline", "AcDb2dPolyline"):
        stride = 2 if kind == "AcDbPolyline" else 3
        verts = [(p[0], p[1]) for p in group_coordinates(entity.Coordinates, stride)]
        closed = bool(entity.Closed)
        count = len(verts) if closed else len(verts) - 1
        return {"vertices": verts, "bulges": [float(entity.GetBulge(i)) for i in range(count)], "closed": closed}
    if kind == "AcDbArc":
        s, e = entity.StartPoint, entity.EndPoint
        sweep = (float(entity.EndAngle) - float(entity.StartAngle)) % (2 * math.pi)
        return {"vertices": [(s[0], s[1]), (e[0], e[1])], "bulges": [math.tan(sweep / 4)], "closed": False}
    if kind == "AcDbCircle":
        c, r = entity.Center, float(entity.Radius)
        return {"vertices": [(c[0] + r, c[1]), (c[0] - r, c[1])], "bulges": [1.0, 1.0], "closed": True}
    raise AutocadError(f"{entity.Handle} is a {kind}; give a line, polyline, arc or circle.")


def path_segments(entity: Any) -> list[geometry.Segment]:
    path = read_path(entity)
    return geometry.segments(path["vertices"], path["bulges"], path["closed"])


def curve_length(entity: Any) -> float | None:
    """Length of any curve; splines and ellipses are measured from their definition."""
    kind = str(entity.ObjectName)
    for attr in ("Length", "ArcLength", "Circumference"):
        try:
            return float(getattr(entity, attr))
        except BaseException as exc:  # noqa: BLE001 - this type has no such property
            raise_if_busy(exc)
            continue
    try:
        if kind == "AcDbSpline":
            return geometry.nurbs_length(list(entity.ControlPoints), list(entity.Knots), int(entity.Degree),
                                         list(entity.Weights) if entity.IsRational else [])
        if kind == "AcDbEllipse":
            return geometry.ellipse_length(float(entity.MajorRadius), float(entity.MinorRadius),
                                           float(entity.StartParameter), float(entity.EndParameter))
    except BaseException as exc:  # noqa: BLE001 - leave it unmeasured
        raise_if_busy(exc)
        return None
    return None
