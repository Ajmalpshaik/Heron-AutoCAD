"""Plane geometry for the take-off, placement and labelling tools.

Plain functions over plain numbers: no AutoCAD here, so all of it is tested
without AutoCAD. Polylines are a vertex list plus AutoCAD bulges (positive =
counter-clockwise arc, bulge = tan(sweep / 4)).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # min x, min y, max x, max y
EPS = 1e-9


@dataclass(frozen=True)
class Segment:
    start: Point
    end: Point
    bulge: float
    length: float
    centre: Point | None = None
    radius: float = 0.0
    start_angle: float = 0.0  # radians, arcs only
    sweep: float = 0.0  # radians, signed


def _segment(p1: Point, p2: Point, bulge: float) -> Segment:
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    chord = math.hypot(dx, dy)
    if abs(bulge) < EPS or chord < EPS:
        return Segment(p1, p2, 0.0, chord)
    sweep = 4.0 * math.atan(bulge)
    radius = chord / (2.0 * abs(math.sin(sweep / 2.0)))
    s = (1.0 - bulge * bulge) / (4.0 * bulge)
    centre = ((p1[0] + p2[0]) / 2.0 - s * dy, (p1[1] + p2[1]) / 2.0 + s * dx)
    start_angle = math.atan2(p1[1] - centre[1], p1[0] - centre[0])
    return Segment(p1, p2, bulge, abs(sweep) * radius, centre, radius, start_angle, sweep)


def segments(vertices: Sequence[Sequence[float]], bulges: Sequence[float], closed: bool) -> list[Segment]:
    """The segments of a polyline, arcs included; a closed one gets its closing segment."""
    pts = [(float(v[0]), float(v[1])) for v in vertices]
    count = len(pts) if closed else len(pts) - 1
    out = []
    for i in range(max(count, 0)):
        bulge = float(bulges[i]) if i < len(bulges) else 0.0
        out.append(_segment(pts[i], pts[(i + 1) % len(pts)], bulge))
    return out


def _on_segment(seg: Segment, d: float) -> tuple[float, float, float]:
    if seg.centre is None:
        t = d / seg.length if seg.length > EPS else 0.0
        x = seg.start[0] + (seg.end[0] - seg.start[0]) * t
        y = seg.start[1] + (seg.end[1] - seg.start[1]) * t
        angle = math.degrees(math.atan2(seg.end[1] - seg.start[1], seg.end[0] - seg.start[0]))
        return x, y, angle % 360.0
    a = seg.start_angle + seg.sweep * (d / seg.length)
    x, y = seg.centre[0] + seg.radius * math.cos(a), seg.centre[1] + seg.radius * math.sin(a)
    tangent = a + (math.pi / 2.0 if seg.sweep > 0 else -math.pi / 2.0)
    return x, y, math.degrees(tangent) % 360.0


def point_at(segs: Sequence[Segment], distance: float) -> tuple[float, float, float]:
    """(x, y, direction in degrees) at a distance along the path."""
    left = max(0.0, float(distance))
    for seg in segs:
        if left <= seg.length + EPS:
            return _on_segment(seg, min(left, seg.length))
        left -= seg.length
    return _on_segment(segs[-1], segs[-1].length)


def centred_positions(length: float, spacing: float | None = None, count: int | None = None) -> list[float]:
    """Distances for blocks along a run, with equal ends (Lee Mac's Centered Measure idea).

    By spacing: as many as fit at that spacing, the spare length split between
    both ends. By count: equal spacing with half a space at each end.
    """
    if count:
        step = length / count
        return [step / 2.0 + i * step for i in range(count)]
    if not spacing or spacing <= 0:
        raise ValueError("give a spacing above 0, or a count")
    n = max(1, int(math.floor(length / spacing + 1e-9)))
    first = (length - (n - 1) * spacing) / 2.0
    return [first + i * spacing for i in range(n)]


def _sample(segs: Sequence[Segment], per_arc: int = 32) -> list[tuple[Point, float]]:
    """Points along the path with their distance from the start."""
    out: list[tuple[Point, float]] = []
    run = 0.0
    for seg in segs:
        steps = per_arc if seg.centre is not None else 1
        for k in range(steps + 1):
            if out and k == 0:
                continue
            d = seg.length * k / steps
            x, y, _ = _on_segment(seg, d)
            out.append(((x, y), run + d))
        run += seg.length
    return out


def distance_along(segs: Sequence[Segment], p: Sequence[float]) -> float:
    """Distance along the path of the point nearest to p (for sorting by run)."""
    pts = _sample(segs)
    best, best_d = math.inf, 0.0
    for (a, da), (b, db) in zip(pts, pts[1:], strict=False):
        vx, vy = b[0] - a[0], b[1] - a[1]
        seg_len2 = vx * vx + vy * vy
        t = 0.0 if seg_len2 < EPS else max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / seg_len2))
        qx, qy = a[0] + vx * t, a[1] + vy * t
        dist = math.hypot(p[0] - qx, p[1] - qy)
        if dist < best:
            best, best_d = dist, da + (db - da) * t
    return best_d


def _inside_interval(p1: Point, p2: Point, box: Box) -> tuple[float, float] | None:
    """Liang-Barsky: the [t0, t1] part of p1->p2 inside the box, or None."""
    t0, t1 = 0.0, 1.0
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    for p, q in ((-dx, p1[0] - box[0]), (dx, box[2] - p1[0]), (-dy, p1[1] - box[1]), (dy, box[3] - p1[1])):
        if abs(p) < EPS:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return None
    return t0, t1


def _lerp(p1: Point, p2: Point, t: float) -> Point:
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def outside_pieces(p1: Sequence[float], p2: Sequence[float], box: Box) -> list[tuple[Point, Point]]:
    """The parts of a straight segment outside a box (Lee Mac's Automatic Block Break idea)."""
    a, b = (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))
    inside = _inside_interval(a, b, box)
    if inside is None or inside[1] - inside[0] < EPS:
        return [(a, b)]
    out = []
    if inside[0] > EPS:
        out.append((a, _lerp(a, b, inside[0])))
    if inside[1] < 1.0 - EPS:
        out.append((_lerp(a, b, inside[1]), b))
    return out


def path_outside(vertices: Sequence[Sequence[float]], box: Box) -> list[list[Point]]:
    """A straight-segment path cut by a box: the runs left outside it."""
    runs: list[list[Point]] = []
    current: list[Point] = []
    pts = [(float(v[0]), float(v[1])) for v in vertices]
    for a, b in zip(pts, pts[1:], strict=False):
        for piece in outside_pieces(a, b, box):
            if current and math.dist(current[-1], piece[0]) < 1e-7:
                current.append(piece[1])
            else:
                if len(current) > 1:
                    runs.append(current)
                current = [piece[0], piece[1]]
    if len(current) > 1:
        runs.append(current)
    return runs


def _inside(p: Sequence[float], box: Box) -> bool:
    return box[0] + EPS < p[0] < box[2] - EPS and box[1] + EPS < p[1] < box[3] - EPS


def _arc_param(seg: Segment, x: float, y: float) -> float:
    """How far round an arc a point on its circle is, 0 at its start and 1 at its end."""
    assert seg.centre is not None
    turned = math.atan2(y - seg.centre[1], x - seg.centre[0]) - seg.start_angle
    if seg.sweep < 0:
        turned = -turned
    return (turned % (2.0 * math.pi)) / abs(seg.sweep)


def _arc_cuts(seg: Segment, box: Box) -> list[float]:
    """Where an arc crosses the four sides of a box, as fractions of the way round it (0 to 1, ends left out)."""
    assert seg.centre is not None
    cx, cy, r = seg.centre[0], seg.centre[1], seg.radius
    found: list[float] = []
    for fixed, lo, hi, vertical in ((box[0], box[1], box[3], True), (box[2], box[1], box[3], True),
                                    (box[1], box[0], box[2], False), (box[3], box[0], box[2], False)):
        across = fixed - (cx if vertical else cy)
        if abs(across) > r + EPS:
            continue
        half = math.sqrt(max(r * r - across * across, 0.0))
        for along in ((cy if vertical else cx) - half, (cy if vertical else cx) + half):
            if lo - EPS <= along <= hi + EPS:
                x, y = (fixed, along) if vertical else (along, fixed)
                t = _arc_param(seg, x, y)
                if 1e-9 < t < 1.0 - 1e-9 and all(abs(t - u) > 1e-9 for u in found):
                    found.append(t)
    return sorted(found)


def _arc_at(seg: Segment, t: float) -> Point:
    if t <= 0.0:
        return seg.start
    if t >= 1.0:
        return seg.end
    x, y, _ = _on_segment(seg, seg.length * t)
    return (x, y)


def _segment_outside(seg: Segment, box: Box) -> tuple[list[tuple[Point, Point, float]], bool]:
    """The pieces of one segment outside a box, each with its own bulge, and whether any of it was cut."""
    if seg.centre is None:
        parts = outside_pieces(seg.start, seg.end, box)
        whole = len(parts) == 1 and parts[0] == (seg.start, seg.end)
        return [(a, b, 0.0) for a, b in parts], not whole
    marks = [0.0, *_arc_cuts(seg, box), 1.0]
    kept: list[list[float]] = []
    for a, b in zip(marks, marks[1:], strict=False):
        if _inside(_arc_at(seg, (a + b) / 2.0), box):
            continue
        if kept and abs(kept[-1][1] - a) < 1e-12:
            kept[-1][1] = b  # an arc that only touches the box stays one piece
        else:
            kept.append([a, b])
    whole = len(kept) == 1 and kept[0] == [0.0, 1.0]
    if whole:
        return [(seg.start, seg.end, seg.bulge)], False
    return [(_arc_at(seg, a), _arc_at(seg, b), math.tan(seg.sweep * (b - a) / 4.0)) for a, b in kept], True


def bulged_outside(
    vertices: Sequence[Sequence[float]], bulges: Sequence[float], closed: bool, box: Box
) -> tuple[list[dict], bool]:
    """A polyline, arcs included, cut by a box: the runs left outside it, and whether anything was cut.

    Each run is {"points": [...], "bulges": [...]}, one bulge per segment of
    the run. A cut arc keeps its centre and radius: each piece's bulge is
    tan(its own sweep / 4), with the sign of the arc it came from. On a closed
    polyline the piece that ends where the loop started is joined to the one
    that starts there, so a loop cut once is one open run, not two.
    """
    segs = segments(vertices, bulges, closed)
    runs: list[dict] = []
    current: dict | None = None
    cut = False
    for seg in segs:
        pieces, was_cut = _segment_outside(seg, box)
        cut = cut or was_cut
        for a, b, bulge in pieces:
            if current is not None and math.dist(current["points"][-1], a) < 1e-7:
                current["points"].append(b)
                current["bulges"].append(bulge)
            else:
                if current is not None:
                    runs.append(current)
                current = {"points": [a, b], "bulges": [bulge]}
    if current is not None:
        runs.append(current)
    if closed and cut and len(runs) > 1 and segs:
        first, last = runs[0], runs[-1]
        start = segs[0].start
        if math.dist(first["points"][0], start) < 1e-7 and math.dist(last["points"][-1], start) < 1e-7:
            joined = {"points": last["points"] + first["points"][1:], "bulges": last["bulges"] + first["bulges"]}
            runs = [joined, *runs[1:-1]]
    return runs, cut


def connected(items: Sequence[dict], seed: str, tolerance: float = 1e-3) -> dict:
    """Every item joined end to end with the seed (Lee Mac's Chain Selection idea).

    items: {"handle", "ends": [p, q]} (closed shapes have no ends and join nothing).
    """
    def key(p: Sequence[float]) -> tuple[int, int]:
        return (round(p[0] / tolerance), round(p[1] / tolerance))

    by_cell: dict[tuple[int, int], list[int]] = {}
    for i, item in enumerate(items):
        for p in item.get("ends") or []:
            cx, cy = key(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    by_cell.setdefault((cx + dx, cy + dy), []).append(i)

    index = {item["handle"]: i for i, item in enumerate(items)}
    if seed not in index:
        raise ValueError(f"{seed} is not among the curves read")
    seen, todo = {index[seed]}, [index[seed]]
    while todo:
        i = todo.pop()
        for p in items[i].get("ends") or []:
            for j in by_cell.get(key(p), []):
                if j not in seen and any(math.dist(p, q) <= tolerance for q in items[j]["ends"]):
                    seen.add(j)
                    todo.append(j)
    chosen = sorted(seen)
    ends = [tuple(p) for i in chosen for p in items[i].get("ends") or []]
    open_ends = [p for p in ends if sum(1 for q in ends if math.dist(p, q) <= tolerance) == 1]
    return {"handles": [items[i]["handle"] for i in chosen], "open_ends": open_ends}


def centroid(vertices: Sequence[Sequence[float]]) -> tuple[Point, float]:
    """Centroid and area of a straight-sided polygon (shoelace)."""
    pts = [(float(v[0]), float(v[1])) for v in vertices]
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1], strict=False):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a /= 2.0
    if abs(a) < EPS:
        n = len(pts) or 1
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n), 0.0
    return (cx / (6.0 * a), cy / (6.0 * a)), abs(a)


def pieces(p1: Sequence[float], p2: Sequence[float], cuts: Sequence[Sequence[float]]) -> list[tuple[Point, Point]]:
    """A straight segment split at the cut points that lie on it, in order."""
    a, b = (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))
    length = math.dist(a, b)
    ts = []
    for c in cuts:
        t = ((c[0] - a[0]) * (b[0] - a[0]) + (c[1] - a[1]) * (b[1] - a[1])) / (length * length) if length else 0
        if EPS < t < 1 - EPS and math.dist(_lerp(a, b, t), (c[0], c[1])) < 1e-6 * max(1.0, length):
            ts.append(t)
    marks = [0.0, *sorted(set(ts)), 1.0]
    return [(_lerp(a, b, s), _lerp(a, b, e)) for s, e in zip(marks, marks[1:], strict=False)]


def _de_boor(u: float, degree: int, knots: Sequence[float], ctrl: list[list[float]]) -> list[float]:
    n = len(ctrl) - 1
    k = degree
    for i in range(degree, n + 1):
        if knots[i] <= u < knots[i + 1]:
            k = i
            break
    else:
        k = n
    d = [list(ctrl[j + k - degree]) for j in range(degree + 1)]
    for r in range(1, degree + 1):
        for j in range(degree, r - 1, -1):
            i = j + k - degree
            den = knots[i + degree - r + 1] - knots[i]
            alpha = 0.0 if abs(den) < EPS else (u - knots[i]) / den
            d[j] = [(1 - alpha) * a + alpha * b for a, b in zip(d[j - 1], d[j], strict=False)]
    return d[degree]


MOST_SPLINE_DEGREE = 10


def control_spline(
    points: Sequence[Sequence[float]], degree: int = 3, closed: bool = False
) -> tuple[list[list[float]], list[float]]:
    """The control points and knots of a spline drawn by its control points (the SPLINE command's CV method).

    Open: the knots are clamped (the curve starts on the first control point
    and ends on the last, leaving along the first and last legs of the
    frame) and evenly spaced between. Closed: the first ``degree`` points are
    repeated at the end and the knots are evenly spaced all the way, so the
    curve comes round and meets itself smoothly, with no corner where it
    started. Returns (control points as [x, y, z], knots).
    """
    p = int(degree)
    if p < 1 or p > MOST_SPLINE_DEGREE:
        raise ValueError(f"the degree must be 1 to {MOST_SPLINE_DEGREE}; 3 is the usual smooth curve")
    pts = [[float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0] for v in points]
    if closed and len(pts) > 1 and math.dist(pts[0], pts[-1]) <= EPS:
        pts.pop()
    for a, b in zip(pts, pts[1:], strict=False):
        if math.dist(a, b) <= EPS:
            raise ValueError("two control points in a row are at one place; take one of them out")
    least = max(p + 1, 3 if closed else 2)
    if len(pts) < least:
        raise ValueError(
            f"a {'closed ' if closed else ''}degree {p} spline needs at least {least} control points; "
            f"there are {len(pts)}"
        )
    if closed:
        wrapped = pts + [list(v) for v in pts[:p]]
        return wrapped, [float(i) for i in range(len(wrapped) + p + 1)]
    inner = len(pts) - p - 1
    knots = [0.0] * (p + 1) + [float(i) for i in range(1, inner + 1)] + [float(inner + 1)] * (p + 1)
    return pts, knots


def spline_point(control: Sequence[Sequence[float]], knots: Sequence[float], degree: int, u: float) -> list[float]:
    """The point on a (non-rational) spline at parameter u, by de Boor's algorithm."""
    return _de_boor(u, int(degree), knots, [list(map(float, c)) for c in control])


def nurbs_length(control: Sequence[float], knots: Sequence[float], degree: int, weights: Sequence[float],
                 samples: int = 2000) -> float:
    """Length of a spline from its control points, knots and weights (no COM length exists)."""
    pts = [list(control[i:i + 3]) for i in range(0, len(control), 3)]
    w = list(weights) if weights else [1.0] * len(pts)
    homo = [[p[0] * wi, p[1] * wi, p[2] * wi, wi] for p, wi in zip(pts, w, strict=False)]
    lo, hi = knots[degree], knots[len(knots) - degree - 1]
    total, prev = 0.0, None
    for s in range(samples + 1):
        u = lo + (hi - lo) * s / samples
        x, y, z, wt = _de_boor(min(u, hi - 1e-12) if s < samples else hi - 1e-12, degree, knots, homo)
        cur = (x / wt, y / wt, z / wt)
        if prev is not None:
            total += math.dist(prev, cur)
        prev = cur
    return total


def ellipse_length(major: float, minor: float, start: float, end: float, steps: int = 4000) -> float:
    """Arc length of an ellipse between two parameters (radians), by Simpson's rule."""
    if end < start:
        end += 2 * math.pi
    h = (end - start) / steps
    f = [math.hypot(major * math.sin(start + i * h), minor * math.cos(start + i * h)) for i in range(steps + 1)]
    return h / 3 * (f[0] + f[-1] + 4 * sum(f[1:-1:2]) + 2 * sum(f[2:-1:2]))


def overlapping(boxes: dict[str, Box], min_share: float = 0.01) -> list[tuple[str, str]]:
    """Pairs whose boxes overlap by more than min_share of the smaller box (Dimension Overlap idea)."""
    names = sorted(boxes)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            p, q = boxes[a], boxes[b]
            w, h = min(p[2], q[2]) - max(p[0], q[0]), min(p[3], q[3]) - max(p[1], q[1])
            if w <= 0 or h <= 0:
                continue
            smaller = min((p[2] - p[0]) * (p[3] - p[1]), (q[2] - q[0]) * (q[3] - q[1])) or EPS
            if w * h / smaller > min_share:
                out.append((a, b))
    return out
