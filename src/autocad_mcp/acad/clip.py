"""Clip outlines for xrefs, images and underlays (#104).

Plain functions over plain numbers, tested without AutoCAD. A clip is a
polygon: arcs in a polyline are followed in short straight steps, as XCLIP
stores any boundary (the same rule as the super hatch, 05 section 19).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..core.errors import AutocadError
from . import geometry

Point = tuple[float, float]

# An arc is stepped so no chord strays more than this share of the outline's
# size from it: 2 mm in a 20 m room.
ARC_DEVIATION = 1e-4
STEPS_PER_ARC = 128
MOST_POINTS = 2000


def rectangle(corner1: Sequence[float], corner2: Sequence[float]) -> list[Point]:
    """The four corners of the box between two opposite corners, counter-clockwise."""
    if len(corner1) < 2 or len(corner2) < 2:
        raise AutocadError("Give the clip rectangle as two opposite corners, [[x1, y1], [x2, y2]].")
    x1, x2 = sorted((float(corner1[0]), float(corner2[0])))
    y1, y2 = sorted((float(corner1[1]), float(corner2[1])))
    if x2 - x1 <= 0 or y2 - y1 <= 0:
        raise AutocadError("The clip rectangle has no width or no height: give two opposite corners.")
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def from_polyline(vertices: Sequence[Sequence[float]], bulges: Sequence[float], closed: bool) -> list[Point]:
    """A closed polyline (arcs included) as the polygon a clip stores."""
    pts = [(float(v[0]), float(v[1])) for v in vertices]
    if len(pts) < 2:
        raise AutocadError("The clip outline needs at least three corners.")
    if not closed:
        if math.dist(pts[0], pts[-1]) > 1e-9 * max(1.0, _size(pts)):
            raise AutocadError("The clip outline is open. Close the polyline first, or give two corners.")
        pts = pts[:-1]
        bulges = list(bulges)[: len(pts)]
    size = _size(pts)
    out: list[Point] = []
    for seg in geometry.segments(pts, bulges, True):
        out.append(seg.start)
        if seg.centre is None or seg.radius <= 0:
            continue
        deviation = max(size * ARC_DEVIATION, 1e-12)
        step = 2.0 * math.acos(max(-1.0, 1.0 - deviation / seg.radius)) if deviation < seg.radius else math.pi / 2
        count = min(STEPS_PER_ARC, max(2, math.ceil(abs(seg.sweep) / max(step, 1e-9))))
        for i in range(1, count):
            angle = seg.start_angle + seg.sweep * i / count
            out.append((seg.centre[0] + seg.radius * math.cos(angle), seg.centre[1] + seg.radius * math.sin(angle)))
    return out


def _size(pts: Sequence[Point]) -> float:
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def _area(pts: Sequence[Point]) -> float:
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(p1: Point, p2: Point, q1: Point, q2: Point, eps: float) -> bool:
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps)) and ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps))


def check(points: Sequence[Sequence[float]]) -> list[Point]:
    """The outline cleaned for AutoCAD: no repeats, at least three corners, an area, no crossing, counter-clockwise.

    The closing point is not repeated; ``closed_ring`` adds it where COM wants it.
    """
    pts: list[Point] = []
    for p in points:
        q = (float(p[0]), float(p[1]))
        if not pts or math.dist(pts[-1], q) > 1e-12:
            pts.append(q)
    while len(pts) > 1 and math.dist(pts[0], pts[-1]) <= 1e-12:
        pts.pop()
    if len(pts) < 3:
        raise AutocadError("The clip outline needs at least three different corners.")
    if len(pts) > MOST_POINTS:
        raise AutocadError(
            f"The clip outline has {len(pts)} corners; Heron clips with at most {MOST_POINTS}. "
            "Simplify the polyline, or clip to a rectangle."
        )
    size = _size(pts)
    area = _area(pts)
    if abs(area) <= (size * 1e-9) ** 2:
        raise AutocadError("The clip outline encloses no area.")
    eps = (size * 1e-12) ** 2
    n = len(pts)
    for i in range(n):
        a1, a2 = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _segments_cross(a1, a2, pts[j], pts[(j + 1) % n], eps):
                raise AutocadError("The clip outline crosses itself. AutoCAD clips only to an outline that does not.")
    return pts if area > 0 else pts[::-1]


def closed_ring(points: Sequence[Point]) -> list[float]:
    """x, y, x, y ... with the first corner repeated at the end, as COM's ClipBoundary takes it."""
    ring = list(points) + [points[0]]
    return [v for p in ring for v in (float(p[0]), float(p[1]))]
