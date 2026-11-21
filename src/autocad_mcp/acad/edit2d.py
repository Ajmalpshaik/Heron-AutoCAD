"""The geometry of the everyday 2D edits: trim, extend, fillet, chamfer, break, join,
move a vertex, stretch (issues #103 and #49, D-78).

Plain functions over plain numbers, like acad/geometry.py and the shape library
(D-30): nothing here touches AutoCAD, so every answer is tested offline. The tools
in tools/edit2d.py read the objects, ask these functions for the new shape, and
write it back by setting the object's own points over COM. No command is typed,
so nothing is ever left waiting at a prompt (known limit 21).

A curve is a *path*, the shape acad/curves.read_path gives:
``{"vertices": [(x, y), ...], "bulges": [...], "closed": bool}``. A line is a path
of two vertices, an arc one with a single bulge (positive = anticlockwise, the
way AutoCAD draws every arc). An open path has one bulge per segment (one fewer
than its vertices); a closed one has one per vertex, the last for the closing
segment. Distances are measured along the path from its first vertex.

Everything is in plan (world X and Y), as AutoCAD's own trim works with PROJMODE
at its default. Refusals are ValueError with the reason in a draftsman's words.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from .geometry import Segment, segments

Point = tuple[float, float]
Path = dict[str, Any]
Box = tuple[float, float, float, float]  # min x, min y, max x, max y

TWO_PI = 2.0 * math.pi


# ---- small vector helpers -----------------------------------------------------


def _pt(p: Sequence[float]) -> Point:
    return (float(p[0]), float(p[1]))


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, b: Point, k: float = 1.0) -> Point:
    return (a[0] + b[0] * k, a[1] + b[1] * k)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _norm(a: Point) -> float:
    return math.hypot(a[0], a[1])


def _unit(a: Point) -> Point:
    n = _norm(a)
    return (a[0] / n, a[1] / n)


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _r(p: Point) -> list[float]:
    return [round(p[0], 9), round(p[1], 9)]


def tolerance(*paths: Path, points: Sequence[Sequence[float]] = ()) -> float:
    """How close two numbers must be to count as the same: a billionth of the drawing's size.

    A fixed 1e-9 would be too fine for a site plan in millimetres a kilometre from
    the origin, and too coarse for nothing; scaling by the largest coordinate in
    play keeps it right for both.
    """
    size = 1.0
    for path in paths:
        for v in path["vertices"]:
            size = max(size, abs(float(v[0])), abs(float(v[1])))
    for p in points:
        size = max(size, abs(float(p[0])), abs(float(p[1])))
    return 1e-9 * size


# ---- paths ----------------------------------------------------------------------


def make_path(vertices: Sequence[Sequence[float]], bulges: Sequence[float] | None = None, closed: bool = False) -> Path:
    """A path in the normal shape: points as (x, y), one bulge per segment."""
    verts = [_pt(v) for v in vertices]
    count = len(verts) if closed else max(len(verts) - 1, 0)
    given = list(bulges or [])
    return {
        "vertices": verts,
        "bulges": [float(given[i]) if i < len(given) else 0.0 for i in range(count)],
        "closed": bool(closed),
    }


def line_path(start: Sequence[float], end: Sequence[float]) -> Path:
    return make_path([start, end])


def _segs(path: Path) -> list[Segment]:
    return segments(path["vertices"], path["bulges"], path["closed"])


def length(path: Path) -> float:
    return sum(s.length for s in _segs(path))


def reverse(path: Path) -> Path:
    """The same curve walked the other way: vertices backwards, every arc's bulge negated."""
    verts = list(reversed(path["vertices"]))
    b = list(path["bulges"])
    n = len(path["vertices"])
    if path["closed"]:
        bulges = [-b[n - 2 - j] for j in range(n - 1)] + [-b[n - 1]]
    else:
        bulges = [-x for x in reversed(b)]
    return {"vertices": verts, "bulges": bulges, "closed": path["closed"]}


def _seg_point(seg: Segment, d: float) -> Point:
    if seg.centre is None:
        t = d / seg.length if seg.length > 0 else 0.0
        return (seg.start[0] + (seg.end[0] - seg.start[0]) * t, seg.start[1] + (seg.end[1] - seg.start[1]) * t)
    a = seg.start_angle + seg.sweep * (d / seg.length)
    return (seg.centre[0] + seg.radius * math.cos(a), seg.centre[1] + seg.radius * math.sin(a))


def point_at(path: Path, d: float) -> Point:
    """The point a distance ``d`` along the path."""
    left = d
    segs = _segs(path)
    for seg in segs:
        if left <= seg.length:
            return _seg_point(seg, max(left, 0.0))
        left -= seg.length
    return segs[-1].end


def _arc_delta(seg: Segment, angle: float) -> float:
    """How far round an arc segment, from its start, an angle is (0 .. 2 pi), in its own direction."""
    if seg.sweep > 0:
        return (angle - seg.start_angle) % TWO_PI
    return (seg.start_angle - angle) % TWO_PI


def _seg_project(seg: Segment, p: Point) -> tuple[float, float]:
    """(distance along the segment, distance off it) of the nearest point to ``p``."""
    if seg.centre is None:
        if seg.length <= 0:
            return 0.0, _dist(p, seg.start)
        t = _dot(_sub(p, seg.start), _sub(seg.end, seg.start)) / (seg.length**2)
        t = min(max(t, 0.0), 1.0)
        return t * seg.length, _dist(p, _seg_point(seg, t * seg.length))
    delta = _arc_delta(seg, math.atan2(p[1] - seg.centre[1], p[0] - seg.centre[0]))
    if delta <= abs(seg.sweep):
        d = delta * seg.radius
        return d, abs(_dist(p, seg.centre) - seg.radius)
    to_start, to_end = _dist(p, seg.start), _dist(p, seg.end)
    return (0.0, to_start) if to_start <= to_end else (seg.length, to_end)


def project(path: Path, p: Sequence[float]) -> tuple[float, float]:
    """(distance along the path, distance off it) of the point on the path nearest ``p``."""
    q = _pt(p)
    best = (0.0, math.inf)
    run = 0.0
    for seg in _segs(path):
        d, off = _seg_project(seg, q)
        if off < best[1]:
            best = (run + d, off)
        run += seg.length
    return best


def _piece(seg: Segment, a: float, b: float) -> tuple[Point, Point, float]:
    """The part of one segment between local distances a and b, as (start, end, bulge)."""
    start, end = _seg_point(seg, a), _seg_point(seg, b)
    if seg.centre is None or seg.length <= 0:
        return start, end, 0.0
    sweep = seg.sweep * (b - a) / seg.length
    return start, end, math.tan(sweep / 4.0)


def _span(path: Path, d0: float, d1: float, eps: float) -> Path:
    """The open piece of the path from distance d0 to d1 (d0 < d1)."""
    verts: list[Point] = []
    bulges: list[float] = []
    run = 0.0
    for seg in _segs(path):
        a, b = max(d0 - run, 0.0), min(d1 - run, seg.length)
        if b - a > eps:
            start, end, bulge = _piece(seg, a, b)
            if not verts:
                verts.append(start)
            verts.append(end)
            bulges.append(bulge)
        run += seg.length
    if len(verts) < 2:
        raise ValueError("That piece has no length.")
    return {"vertices": verts, "bulges": bulges, "closed": False}


def _join_two(first: Path, second: Path) -> Path:
    return {
        "vertices": first["vertices"] + second["vertices"][1:],
        "bulges": first["bulges"] + second["bulges"],
        "closed": False,
    }


def sub_path(path: Path, d0: float, d1: float) -> Path:
    """The open piece from d0 to d1. On a closed path d1 <= d0 goes on past the first vertex."""
    eps = tolerance(path)
    total = length(path)
    if path["closed"] and d1 <= d0 + eps:
        if d0 >= total - eps:
            return _span(path, 0.0, d1 if d1 > eps else total, eps)
        if d1 <= eps:
            return _span(path, d0, total, eps)
        return _join_two(_span(path, d0, total, eps), _span(path, 0.0, d1, eps))
    return _span(path, d0, d1, eps)


# ---- where two curves meet --------------------------------------------------------


def _line_params(p: Point, q: Point, a: Point, b: Point) -> tuple[float, float] | None:
    """Fractions (t along p-q, u along a-b) where the two unbounded lines cross; None if parallel."""
    r, s = _sub(q, p), _sub(b, a)
    den = _cross(r, s)
    if abs(den) <= 1e-12 * max(_norm(r) * _norm(s), 1e-300):
        return None
    ap = _sub(a, p)
    return _cross(ap, s) / den, _cross(ap, r) / den


def _line_circle(p: Point, q: Point, c: Point, radius: float, eps: float) -> list[float]:
    """Fractions along the unbounded line p-q where it meets the circle (a touch counts once)."""
    d = _sub(q, p)
    f = _sub(p, c)
    a = _dot(d, d)
    if a <= 0:
        return []
    b = 2.0 * _dot(f, d)
    cc = _dot(f, f) - radius * radius
    disc = b * b - 4.0 * a * cc
    # A line that just touches the circle: within eps of the radius counts as one point.
    closest = abs(_cross(d, f)) / math.sqrt(a)
    if disc < 0:
        if closest - radius <= eps:
            return [-b / (2.0 * a)]
        return []
    root = math.sqrt(disc)
    if root <= 1e-15:
        return [-b / (2.0 * a)]
    return [(-b - root) / (2.0 * a), (-b + root) / (2.0 * a)]


def _circle_circle(c1: Point, r1: float, c2: Point, r2: float, eps: float) -> list[Point]:
    d = _dist(c1, c2)
    if d <= eps or d > r1 + r2 + eps or d < abs(r1 - r2) - eps:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h2 = r1 * r1 - a * a
    h = math.sqrt(h2) if h2 > 0 else 0.0
    u = _unit(_sub(c2, c1))
    mid = _add(c1, u, a)
    if h <= eps:
        return [mid]
    n = (-u[1], u[0])
    return [_add(mid, n, h), _add(mid, n, -h)]


def _on_arc(seg: Segment, p: Point, eps: float) -> float | None:
    """Local distance of a point on an arc segment's circle, or None when it is off the arc."""
    delta = _arc_delta(seg, math.atan2(p[1] - seg.centre[1], p[0] - seg.centre[0]))
    slack = eps / seg.radius
    sweep = abs(seg.sweep)
    if delta <= sweep + slack:
        return min(delta, sweep) * seg.radius
    if delta >= TWO_PI - slack:  # just before the start
        return 0.0
    return None


def _within(t: float, seg_length: float, eps: float) -> bool:
    slack = eps / seg_length if seg_length > 0 else 0.0
    return -slack <= t <= 1.0 + slack


def _seg_hits(a: Segment, b: Segment, eps: float) -> list[float]:
    """Local distances along segment a where it meets segment b, both taken as drawn."""
    if a.length <= 0 or b.length <= 0:
        return []
    out: list[float] = []
    if a.centre is None and b.centre is None:
        found = _line_params(a.start, a.end, b.start, b.end)
        if found and _within(found[0], a.length, eps) and _within(found[1], b.length, eps):
            out.append(min(max(found[0], 0.0), 1.0) * a.length)
    elif a.centre is None:
        for t in _line_circle(a.start, a.end, b.centre, b.radius, eps):
            p = _add(a.start, _sub(a.end, a.start), t)
            if _within(t, a.length, eps) and _on_arc(b, p, eps) is not None:
                out.append(min(max(t, 0.0), 1.0) * a.length)
    elif b.centre is None:
        for t in _line_circle(b.start, b.end, a.centre, a.radius, eps):
            p = _add(b.start, _sub(b.end, b.start), t)
            if _within(t, b.length, eps):
                d = _on_arc(a, p, eps)
                if d is not None:
                    out.append(d)
    else:
        for p in _circle_circle(a.centre, a.radius, b.centre, b.radius, eps):
            if _on_arc(b, p, eps) is not None:
                d = _on_arc(a, p, eps)
                if d is not None:
                    out.append(d)
    return out


def _dedupe(values: list[float], eps: float) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > eps:
            out.append(v)
    return out


def intersections(path: Path, other: Path) -> list[float]:
    """Distances along ``path`` where it meets ``other``, both as drawn (sorted, each once)."""
    eps = tolerance(path, other) * 10
    hits: list[float] = []
    run = 0.0
    other_segs = _segs(other)
    for seg in _segs(path):
        for b in other_segs:
            hits.extend(run + d for d in _seg_hits(seg, b, eps))
        run += seg.length
    return _dedupe(hits, eps)


# ---- trim ---------------------------------------------------------------------------


def trim(path: Path, cuts: Sequence[float], pick: float) -> tuple[list[Path], float]:
    """Cut away the part of a path between the two cutting edges either side of ``pick``.

    ``cuts`` are distances along the path where it meets a cutting edge (from
    ``intersections``); ``pick`` is the distance of a point on the part to cut
    away. An open path loses that part, out to its end when no edge lies beyond;
    a closed one loses the part between the two edges round the pick and opens
    there. Returns (the pieces left, the length cut away).
    """
    eps = tolerance(path) * 10
    total = length(path)
    if path["closed"]:
        cs = _dedupe([c % total for c in cuts], eps)
        if len(cs) > 1 and total - cs[-1] <= eps:
            cs.pop()
        if len(cs) < 2:
            raise ValueError(
                "A closed outline has to cross the cutting edges at least twice to be trimmed; "
                f"this one meets them {len(cs)} time(s)."
            )
        p = pick % total
        if any(min(abs(p - c), total - abs(p - c)) <= eps for c in cs):
            raise ValueError("That point is right on a cutting edge; give a point on the part to cut away.")
        before = [c for c in cs if c < p]
        after = [c for c in cs if c > p]
        lo = before[-1] if before else cs[-1]
        hi = after[0] if after else cs[0]
        return [sub_path(path, hi, lo)], (hi - lo) % total
    cs = [c for c in _dedupe(list(cuts), eps) if eps < c < total - eps]
    if not cs:
        raise ValueError("It does not cross any of the cutting edges, so there is nothing to trim.")
    if any(abs(pick - c) <= eps for c in cs):
        raise ValueError("That point is right on a cutting edge; give a point on the part to cut away.")
    lo = max((c for c in cs if c < pick), default=0.0)
    hi = min((c for c in cs if c > pick), default=total)
    pieces = []
    if lo > eps:
        pieces.append(sub_path(path, 0.0, lo))
    if hi < total - eps:
        pieces.append(sub_path(path, hi, total))
    return pieces, hi - lo


# ---- extend -------------------------------------------------------------------------


def _ray_hits(origin: Point, direction: Point, b: Segment, eps: float) -> list[float]:
    """Distances along an unbounded line (origin, unit direction) where it meets segment b as drawn."""
    if b.length <= 0:
        return []
    ahead = _add(origin, direction)
    out: list[float] = []
    if b.centre is None:
        found = _line_params(origin, ahead, b.start, b.end)
        if found and _within(found[1], b.length, eps):
            out.append(found[0])
    else:
        for t in _line_circle(origin, ahead, b.centre, b.radius, eps):
            if _on_arc(b, _add(origin, direction, t), eps) is not None:
                out.append(t)
    return out


def _circle_hits(centre: Point, radius: float, b: Segment, eps: float) -> list[Point]:
    """Points where a full circle meets segment b as drawn."""
    if b.length <= 0:
        return []
    if b.centre is None:
        return [
            _add(b.start, _sub(b.end, b.start), t)
            for t in _line_circle(b.start, b.end, centre, radius, eps)
            if _within(t, b.length, eps)
        ]
    return [p for p in _circle_circle(centre, radius, b.centre, b.radius, eps) if _on_arc(b, p, eps) is not None]


def extend(path: Path, at_end: bool, boundaries: Sequence[Path]) -> tuple[Path, float] | None:
    """Lengthen one end of an open path to the nearest boundary that lies ahead of it.

    A straight end runs on along its own line; an arc end runs on round its own
    circle (never past a full circle). Only boundaries as drawn count, as with
    AutoCAD's EDGEMODE at its default. Returns (the new path, the length added),
    or None when no boundary lies ahead.
    """
    if path["closed"]:
        raise ValueError("A closed outline has no end to extend.")
    work = path if at_end else reverse(path)
    eps = tolerance(path, *boundaries) * 10
    last = _segs(work)[-1]
    if last.length <= 0:
        raise ValueError("Its last segment has no length, so it has no direction to extend in.")
    others = [seg for b in boundaries for seg in _segs(b)]
    verts = list(work["vertices"])
    bulges = list(work["bulges"])
    if last.centre is None:
        u = _unit(_sub(last.end, last.start))
        ahead = [s for b in others for s in _ray_hits(last.end, u, b, eps) if s > eps]
        if not ahead:
            return None
        gain = min(ahead)
        verts[-1] = _add(last.end, u, gain)
    else:
        sigma = 1.0 if last.sweep > 0 else -1.0
        end_angle = last.start_angle + last.sweep
        slack = eps / last.radius
        best = None
        for b in others:
            for p in _circle_hits(last.centre, last.radius, b, eps):
                delta = (sigma * (math.atan2(p[1] - last.centre[1], p[0] - last.centre[0]) - end_angle)) % TWO_PI
                if slack < delta and abs(last.sweep) + delta < TWO_PI - slack and (best is None or delta < best):
                    best = delta
        if best is None:
            return None
        gain = best * last.radius
        a = end_angle + sigma * best
        verts[-1] = (last.centre[0] + last.radius * math.cos(a), last.centre[1] + last.radius * math.sin(a))
        bulges[-1] = math.tan((last.sweep + sigma * best) / 4.0)
    out = {"vertices": verts, "bulges": bulges, "closed": False}
    return (out if at_end else reverse(out)), gain


# ---- break --------------------------------------------------------------------------


def break_at(path: Path, d: float) -> list[Path]:
    """Split at one point: an open path into two, a closed one opened there into one."""
    eps = tolerance(path) * 10
    total = length(path)
    if path["closed"]:
        at = 0.0 if d >= total - eps else max(d, 0.0)
        return [sub_path(path, at, at)]
    if d <= eps or d >= total - eps:
        raise ValueError("That point is at an end of it, so there is nothing to break.")
    return [sub_path(path, 0.0, d), sub_path(path, d, total)]


def break_between(path: Path, d1: float, d2: float) -> list[Path]:
    """Take out the part between two points.

    On an open path the part between them goes, leaving up to two pieces. On a
    closed one the part from the first point to the second, in the outline's own
    direction, goes; what is left is one open piece.
    """
    eps = tolerance(path) * 10
    total = length(path)
    if abs(d1 - d2) <= eps:
        return break_at(path, d1)
    if path["closed"]:
        return [sub_path(path, d2 % total, d1 % total)]
    a, b = sorted((d1, d2))
    pieces = []
    if a > eps:
        pieces.append(sub_path(path, 0.0, a))
    if b < total - eps:
        pieces.append(sub_path(path, b, total))
    if not pieces:
        raise ValueError("Those two points are at its two ends: that would take all of it away. Delete it instead.")
    return pieces


# ---- join ---------------------------------------------------------------------------


def join_order(paths: Sequence[Path], gap: float = 0.0) -> tuple[list[tuple[int, bool]], bool]:
    """The order to join open paths end to end: [(index, walked backwards?)], and whether it closes.

    Two ends touch when they are within ``gap`` (or the drawing's own tolerance
    when ``gap`` is 0). A run that branches, or pieces that do not meet the run,
    are refused with where.
    """
    if len(paths) < 2:
        raise ValueError("Give at least two objects to join.")
    for i, p in enumerate(paths):
        if p["closed"]:
            raise ValueError(f"Object {i + 1} is closed; a closed outline cannot be joined to anything.")
    tol = max(gap, tolerance(*paths) * 100)
    ends = [(p["vertices"][0], p["vertices"][-1]) for p in paths]

    def touching(a: Point, b: Point) -> bool:
        return _dist(a, b) <= tol

    for i, (s, e) in enumerate(ends):
        for pt in (s, e):
            meets = [j for j, (s2, e2) in enumerate(ends) if j != i for q in (s2, e2) if touching(pt, q)]
            if len(meets) > 1:
                raise ValueError(
                    f"Three or more of them meet at ({pt[0]:.6g}, {pt[1]:.6g}): a branch. Heron joins one "
                    "run at a time; join each branch separately."
                )

    def free(i: int, pt: Point) -> bool:
        return not any(touching(pt, q) for j, (s2, e2) in enumerate(ends) if j != i for q in (s2, e2))

    start = next((i for i in range(len(paths)) if free(i, ends[i][0])), None)
    first: tuple[int, bool]
    if start is not None:
        first = (start, False)
    else:
        start = next((i for i in range(len(paths)) if free(i, ends[i][1])), None)
        first = (start, True) if start is not None else (0, False)
    chain = [first]
    used = {first[0]}
    tail = ends[first[0]][0] if first[1] else ends[first[0]][1]
    while len(chain) < len(paths):
        step = None
        for j in range(len(paths)):
            if j in used:
                continue
            if touching(tail, ends[j][0]):
                step = (j, False)
                break
            if touching(tail, ends[j][1]):
                step = (j, True)
                break
        if step is None:
            break
        chain.append(step)
        used.add(step[0])
        tail = ends[step[0]][0] if step[1] else ends[step[0]][1]
    if len(chain) < len(paths):
        left = [j for j in range(len(paths)) if j not in used]
        head = ends[first[0]][1] if first[1] else ends[first[0]][0]
        nearest = min(_dist(p, q) for j in left for p in ends[j] for q in (head, tail))
        raise ValueError(
            f"Object(s) {', '.join(str(j + 1) for j in left)} do not touch the run: the nearest gap is "
            f"{nearest:.6g}. Close the gap first, or give a 'gap' at least that big."
        )
    head = ends[first[0]][1] if first[1] else ends[first[0]][0]
    return chain, touching(head, tail)


def _remove_vertex(verts: list[Point], bulges: list[float], closed: bool, j: int, bulge: float) -> None:
    """Drop vertex j, the segments either side becoming one with ``bulge`` (lists change in place)."""
    if closed and j == 0:
        del verts[0]
        del bulges[0]
        bulges[-1] = bulge
        return
    del verts[j]
    del bulges[j]
    bulges[j - 1] = bulge


def _merge_at(verts: list[Point], bulges: list[float], closed: bool, j: int, eps: float) -> bool:
    """Make the two segments meeting at vertex j one, when they are one line or one arc."""
    n = len(verts)
    if n < 3:
        return False
    prev = (j - 1) % n
    nxt = (j + 1) % n
    b_in, b_out = bulges[prev], bulges[j]
    a, v, c = verts[prev], verts[j], verts[nxt]
    if abs(b_in) <= 1e-12 and abs(b_out) <= 1e-12:
        d_in, d_out = _sub(v, a), _sub(c, v)
        if _norm(d_in) <= 0 or _norm(d_out) <= 0:
            return False
        if abs(_cross(_unit(d_in), _unit(d_out))) * max(_norm(d_in), _norm(d_out)) <= eps and _dot(d_in, d_out) > 0:
            _remove_vertex(verts, bulges, closed, j, 0.0)
            return True
        return False
    if abs(b_in) <= 1e-12 or abs(b_out) <= 1e-12 or (b_in > 0) != (b_out > 0):
        return False
    s_in = segments([a, v], [b_in], False)[0]
    s_out = segments([v, c], [b_out], False)[0]
    if _dist(s_in.centre, s_out.centre) > eps or abs(s_in.radius - s_out.radius) > eps:
        return False
    total = s_in.sweep + s_out.sweep
    if abs(total) >= TWO_PI - 1e-6:
        return False
    _remove_vertex(verts, bulges, closed, j, math.tan(total / 4.0))
    return True


def join(paths: Sequence[Path], gap: float = 0.0) -> dict[str, Any]:
    """Join open paths end to end into one.

    Returns {"path", "order": [(index, reversed)], "closed", "kind"}: kind is
    "line" when the result is one straight piece, "arc" when it is one arc, else
    "polyline". Where two pieces meet in one straight line, or round one circle,
    the joint vertex goes; vertices inside a piece are kept. Within ``gap`` the
    earlier piece's end point is used for the joint.
    """
    order, closed = join_order(paths, gap)
    pieces = [reverse(paths[i]) if back else paths[i] for i, back in order]
    verts = list(pieces[0]["vertices"])
    bulges = list(pieces[0]["bulges"])
    joints: list[int] = []
    for piece in pieces[1:]:
        joints.append(len(verts) - 1)
        verts.extend(piece["vertices"][1:])
        bulges.extend(piece["bulges"])
    if closed and len(verts) > 2:
        verts.pop()
        joints.append(0)
    elif closed:
        closed = False
    eps = tolerance(*paths) * 100
    for j in sorted(joints, reverse=True):
        _merge_at(verts, bulges, closed, j, eps)
    path = {"vertices": verts, "bulges": bulges, "closed": closed}
    if not closed and len(verts) == 2:
        kind = "line" if abs(bulges[0]) <= 1e-12 else "arc"
    else:
        kind = "polyline"
    return {"path": path, "order": order, "closed": closed, "kind": kind}


# ---- fillet and chamfer between two lines ---------------------------------------------


def _corner(
    l1: Sequence[Sequence[float]],
    l2: Sequence[Sequence[float]],
    keep1: Sequence[float] | None,
    keep2: Sequence[float] | None,
) -> dict[str, Any]:
    """Where two lines meet, which way each is kept, and how far each reaches from the corner."""
    a1, b1 = _pt(l1[0]), _pt(l1[1])
    a2, b2 = _pt(l2[0]), _pt(l2[1])
    for name, (a, b) in (("first", (a1, b1)), ("second", (a2, b2))):
        if _dist(a, b) <= 0:
            raise ValueError(f"The {name} line has no length.")
    found = _line_params(a1, b1, a2, b2)
    if found is None:
        raise ValueError("The two lines are parallel: they never meet, so there is no corner to make.")
    x = _add(a1, _sub(b1, a1), found[0])
    eps = tolerance(points=[a1, b1, a2, b2, x]) * 10
    sides = []
    for name, (a, b), keep in (("first", (a1, b1), keep1), ("second", (a2, b2), keep2)):
        d = _unit(_sub(b, a))
        if keep is not None:
            s = _dot(_sub(_pt(keep), x), d)
            if abs(s) <= eps:
                raise ValueError(f"The point to keep on the {name} line is right at the corner; give one along it.")
            u = d if s > 0 else (-d[0], -d[1])
        else:
            far = a if _dist(a, x) >= _dist(b, x) else b
            u = _unit(_sub(far, x)) if _dist(far, x) > eps else d
        reach = [_dot(_sub(a, x), u), _dot(_sub(b, x), u)]
        if max(reach) <= eps:
            raise ValueError(f"Nothing of the {name} line lies on that side of the corner.")
        sides.append({"u": u, "near": 0 if reach[0] < reach[1] else 1, "reach": max(reach), "ends": [a, b]})
    theta = math.acos(min(1.0, max(-1.0, _dot(sides[0]["u"], sides[1]["u"]))))
    if theta <= 1e-9 or math.pi - theta <= 1e-9:
        raise ValueError("The two lines run in one straight line, so there is no corner to make.")
    return {"x": x, "theta": theta, "sides": sides, "eps": eps}


def _moved_line(side: dict[str, Any], new_point: Point) -> list[list[float]]:
    ends = list(side["ends"])
    ends[side["near"]] = new_point
    return [_r(ends[0]), _r(ends[1])]


def fillet_lines(
    l1: Sequence[Sequence[float]],
    l2: Sequence[Sequence[float]],
    radius: float,
    keep1: Sequence[float] | None = None,
    keep2: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Round the corner of two lines with an arc of ``radius`` (0: a sharp corner).

    Each line keeps its end farther from the corner (or the side of ``keep``);
    its other end is trimmed or extended to the arc's tangent point. Returns
    {"line1": [p, q], "line2": [p, q]} (each in its own direction), "corner",
    and "arc": {"centre", "radius", "start_angle", "end_angle"} (radians,
    anticlockwise from start to end, as AutoCAD keeps an arc) or None.
    """
    if radius < 0:
        raise ValueError("A fillet radius cannot be negative.")
    c = _corner(l1, l2, keep1, keep2)
    x, theta, (s1, s2), eps = c["x"], c["theta"], c["sides"], c["eps"]
    if radius <= 0:
        return {"line1": _moved_line(s1, x), "line2": _moved_line(s2, x), "corner": _r(x), "arc": None}
    t = radius / math.tan(theta / 2.0)
    if t >= min(s1["reach"], s2["reach"]) - eps:
        biggest = min(s1["reach"], s2["reach"]) * math.tan(theta / 2.0)
        raise ValueError(
            f"A radius of {radius:g} is too big for these lines: the arc would need {t:.6g} of each, "
            f"and the shorter has {min(s1['reach'], s2['reach']):.6g}. The largest that fits is about {biggest:.6g}."
        )
    t1, t2 = _add(x, s1["u"], t), _add(x, s2["u"], t)
    bis = _unit(_add(s1["u"], s2["u"]))
    centre = _add(x, bis, radius / math.sin(theta / 2.0))
    a1 = math.atan2(t1[1] - centre[1], t1[0] - centre[0])
    a2 = math.atan2(t2[1] - centre[1], t2[0] - centre[0])
    sweep = math.pi - theta
    start, end = (a1, a2) if abs((a2 - a1) % TWO_PI - sweep) <= 1e-6 else (a2, a1)
    return {
        "line1": _moved_line(s1, t1),
        "line2": _moved_line(s2, t2),
        "corner": _r(x),
        "tangent_points": [_r(t1), _r(t2)],
        "arc": {"centre": _r(centre), "radius": float(radius), "start_angle": start % TWO_PI, "end_angle": end % TWO_PI},
    }


def chamfer_second(first: float, angle_degrees: float, corner_angle: float) -> float:
    """The distance along the second line for a chamfer ``first`` along the first at ``angle_degrees``.

    The angle is the one between the first line and the chamfer, as AutoCAD's
    angle method asks for it; ``corner_angle`` is the angle between the two
    kept lines (radians). By the sine rule in the triangle the cut makes.
    """
    a = math.radians(angle_degrees)
    far = math.pi - corner_angle - a
    if a <= 0 or far <= 1e-9:
        raise ValueError(
            f"A chamfer at {angle_degrees:g} degrees does not reach the second line from this corner "
            f"({math.degrees(corner_angle):.6g} degrees): give an angle between 0 and "
            f"{180.0 - math.degrees(corner_angle):.6g}."
        )
    return first * math.sin(a) / math.sin(far)


def chamfer_lines(
    l1: Sequence[Sequence[float]],
    l2: Sequence[Sequence[float]],
    distance1: float,
    distance2: float | None = None,
    angle_degrees: float | None = None,
    keep1: Sequence[float] | None = None,
    keep2: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Cut the corner of two lines: ``distance1`` back along the first, ``distance2`` (or the angle) along the second.

    Both 0 makes a sharp corner. Returns {"line1", "line2", "corner", "chamfer": [p, q] or None,
    "distances": [d1, d2]}.
    """
    c = _corner(l1, l2, keep1, keep2)
    x, theta, (s1, s2), eps = c["x"], c["theta"], c["sides"], c["eps"]
    if distance1 < 0 or (distance2 is not None and distance2 < 0):
        raise ValueError("A chamfer distance cannot be negative.")
    if angle_degrees is not None:
        d2 = chamfer_second(distance1, angle_degrees, theta)
    else:
        d2 = distance1 if distance2 is None else distance2
    d1 = distance1
    if d1 <= 0 and d2 <= 0:
        return {"line1": _moved_line(s1, x), "line2": _moved_line(s2, x), "corner": _r(x), "chamfer": None,
                "distances": [0.0, 0.0]}
    if d1 <= 0 or d2 <= 0:
        raise ValueError("Give both chamfer distances above 0, or both 0 for a sharp corner.")
    for name, d, side in (("first", d1, s1), ("second", d2, s2)):
        if d >= side["reach"] - eps:
            raise ValueError(
                f"A chamfer of {d:.6g} along the {name} line is longer than that line reaches from the corner "
                f"({side['reach']:.6g})."
            )
    p1, p2 = _add(x, s1["u"], d1), _add(x, s2["u"], d2)
    return {
        "line1": _moved_line(s1, p1),
        "line2": _moved_line(s2, p2),
        "corner": _r(x),
        "chamfer": [_r(p1), _r(p2)],
        "distances": [round(d1, 9), round(d2, 9)],
    }


# ---- fillet and chamfer at a polyline's corners ------------------------------------------


def _all_bulges(path: Path) -> list[float]:
    """One bulge per vertex: an open path's last vertex gets a 0 that is never used."""
    b = list(path["bulges"])
    return b if path["closed"] else b + [0.0]


def corner_vertices(path: Path) -> list[int]:
    """The vertex numbers that can be corners: not the two ends of an open path."""
    n = len(path["vertices"])
    return list(range(n)) if path["closed"] else list(range(1, n - 1))


def shape_corners(
    path: Path,
    *,
    radius: float | None = None,
    distance1: float | None = None,
    distance2: float | None = None,
    angle_degrees: float | None = None,
    vertices: Sequence[int] | None = None,
) -> tuple[Path, list[int], list[dict[str, Any]]]:
    """Fillet (``radius``) or chamfer (``distance1`` ...) a polyline's corners; it stays one polyline.

    ``vertices`` are the corner numbers (0 = first vertex, as autocad_polyline_info
    counts them); None means every corner. A corner is done only between two
    straight segments, and only where each segment is long enough for the
    corners at both its ends; the rest are listed with the reason.
    Returns (the new path, the corners done, [{"vertex", "reason"}] skipped).
    """
    fillet = radius is not None
    if fillet and radius < 0:
        raise ValueError("A fillet radius cannot be negative.")
    if not fillet and (distance1 is None or distance1 < 0 or (distance2 is not None and distance2 < 0)):
        raise ValueError("A chamfer needs a distance of 0 or more.")
    verts = [_pt(v) for v in path["vertices"]]
    n = len(verts)
    closed = path["closed"]
    bulges = _all_bulges(path)
    eps = tolerance(path) * 10
    allowed = set(corner_vertices(path))
    wanted = list(dict.fromkeys(vertices)) if vertices is not None else sorted(allowed)
    skipped: list[dict[str, Any]] = []
    plan: dict[int, tuple[float, float, float, Point, Point]] = {}
    for i in wanted:
        if not 0 <= i < n:
            skipped.append({"vertex": i, "reason": f"there is no vertex {i}: it has {n} (0 to {n - 1})"})
            continue
        if i not in allowed:
            skipped.append({"vertex": i, "reason": "an end of an open polyline is not a corner"})
            continue
        prev, nxt = (i - 1) % n, (i + 1) % n
        if abs(bulges[prev]) > 1e-12 or abs(bulges[i]) > 1e-12:
            skipped.append({"vertex": i, "reason": "an arc meets this corner; Heron rounds corners between straights only"})
            continue
        len_in, len_out = _dist(verts[prev], verts[i]), _dist(verts[i], verts[nxt])
        if len_in <= eps or len_out <= eps:
            skipped.append({"vertex": i, "reason": "a segment here has no length"})
            continue
        u_in = _unit(_sub(verts[prev], verts[i]))
        u_out = _unit(_sub(verts[nxt], verts[i]))
        theta = math.acos(min(1.0, max(-1.0, _dot(u_in, u_out))))
        if math.pi - theta <= 1e-9:
            skipped.append({"vertex": i, "reason": "no corner here: the polyline runs straight on"})
            continue
        if theta <= 1e-9:
            skipped.append({"vertex": i, "reason": "the polyline doubles back on itself here"})
            continue
        if fillet:
            if radius <= 0:
                skipped.append({"vertex": i, "reason": "a radius of 0 leaves the corner as it is"})
                continue
            t_in = t_out = radius / math.tan(theta / 2.0)
            turn = _cross((-u_in[0], -u_in[1]), u_out)
            bulge = math.copysign(math.tan((math.pi - theta) / 4.0), turn)
        else:
            t_in = float(distance1)
            if angle_degrees is not None:
                t_out = chamfer_second(t_in, angle_degrees, theta)
            else:
                t_out = t_in if distance2 is None else float(distance2)
            if t_in <= 0 and t_out <= 0:
                skipped.append({"vertex": i, "reason": "a chamfer of 0 leaves the corner as it is"})
                continue
            if t_in <= 0 or t_out <= 0:
                raise ValueError("Give both chamfer distances above 0.")
            bulge = 0.0
        plan[i] = (t_in, t_out, bulge, u_in, u_out)

    # Each segment has to hold the corners at both its ends.
    changed = True
    while changed:
        changed = False
        for k in range(n if closed else n - 1):
            k2 = (k + 1) % n
            used = (plan[k][1] if k in plan else 0.0) + (plan[k2][0] if k2 in plan else 0.0)
            seg_len = _dist(verts[k], verts[k2])
            if used > seg_len + eps:
                for v in (k, k2):
                    if v in plan:
                        del plan[v]
                        skipped.append({
                            "vertex": v,
                            "reason": f"segment {k} ({seg_len:.6g} long) is too short for that "
                            + ("radius" if fillet else "distance") + f" (it needs {used:.6g})",
                        })
                changed = True

    out_v: list[Point] = []
    out_b: list[float] = []
    for i in range(n):
        if i in plan:
            t_in, t_out, bulge, u_in, u_out = plan[i]
            out_v += [_add(verts[i], u_in, t_in), _add(verts[i], u_out, t_out)]
            out_b += [bulge, bulges[i]]
        else:
            out_v.append(verts[i])
            out_b.append(bulges[i])
    # Two corners that use the whole of the segment between them meet in one point.
    k = 0
    while k < len(out_v):
        k2 = k + 1
        if k2 == len(out_v):
            if not closed or len(out_v) < 3:
                break
            if _dist(out_v[k], out_v[0]) <= eps:
                out_v.pop()
                out_b.pop()
            break
        if _dist(out_v[k], out_v[k2]) <= eps:
            del out_v[k2]
            out_b[k] = out_b.pop(k2)
            continue
        k += 1
    if not closed:
        out_b = out_b[: len(out_v) - 1]
    skipped.sort(key=lambda row: row["vertex"])
    return {"vertices": out_v, "bulges": out_b, "closed": closed}, sorted(plan), skipped


# ---- vertices -------------------------------------------------------------------------


def nearest_vertex(path: Path, p: Sequence[float]) -> int:
    q = _pt(p)
    return min(range(len(path["vertices"])), key=lambda i: _dist(path["vertices"][i], q))


def _check_index(path: Path, index: int) -> None:
    n = len(path["vertices"])
    if not 0 <= index < n:
        raise ValueError(f"There is no vertex {index}: it has {n}, numbered 0 to {n - 1}.")


def move_vertex(path: Path, index: int, to: Sequence[float]) -> Path:
    """The path with one vertex moved; every bulge kept, so an arc next to it stays an arc."""
    _check_index(path, index)
    verts = list(path["vertices"])
    verts[index] = _pt(to)
    out = {"vertices": verts, "bulges": list(path["bulges"]), "closed": path["closed"]}
    _check_no_zero_segment(out)
    return out


def _check_no_zero_segment(path: Path) -> None:
    eps = tolerance(path)
    for i, seg in enumerate(_segs(path)):
        if _dist(seg.start, seg.end) <= eps:
            raise ValueError(f"That puts two vertices on top of each other (segment {i} would have no length).")


def add_vertex(path: Path, after: int, at: Sequence[float]) -> Path:
    """A new vertex after vertex ``after``, on a straight segment; both halves stay straight."""
    n = len(path["vertices"])
    last = n - 1 if path["closed"] else n - 2
    if not 0 <= after <= last:
        raise ValueError(f"There is no segment after vertex {after}: the segments start at vertices 0 to {last}.")
    if abs(path["bulges"][after]) > 1e-12:
        raise ValueError(f"Segment {after} is an arc; Heron adds a vertex on a straight segment only.")
    verts = list(path["vertices"])
    bulges = list(path["bulges"])
    verts.insert(after + 1, _pt(at))
    bulges.insert(after + 1, 0.0)
    out = {"vertices": verts, "bulges": bulges, "closed": path["closed"]}
    _check_no_zero_segment(out)
    return out


def remove_vertex(path: Path, index: int) -> tuple[Path, bool]:
    """The path without one vertex. Returns (path, an arc was made straight)."""
    _check_index(path, index)
    n = len(path["vertices"])
    closed = path["closed"]
    if n <= (3 if closed else 2):
        raise ValueError(
            "That would leave too few vertices: a closed polyline keeps at least 3, an open one 2."
        )
    verts = list(path["vertices"])
    bulges = list(path["bulges"])
    if not closed and index in (0, n - 1):
        del verts[index]
        del bulges[0 if index == 0 else -1]
        return {"vertices": verts, "bulges": bulges, "closed": False}, False
    prev = (index - 1) % n
    straightened = abs(bulges[prev]) > 1e-12 or abs(bulges[index]) > 1e-12
    _remove_vertex(verts, bulges, closed, index, 0.0)
    return {"vertices": verts, "bulges": bulges, "closed": closed}, straightened


# ---- stretch --------------------------------------------------------------------------


def window(corner1: Sequence[float], corner2: Sequence[float]) -> Box:
    """A window from any two opposite corners."""
    x1, y1 = _pt(corner1)
    x2, y2 = _pt(corner2)
    if abs(x1 - x2) <= 0 or abs(y1 - y2) <= 0:
        raise ValueError("The stretch window has no area: give two opposite corners.")
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def inside(p: Sequence[float], box: Box, eps: float = 0.0) -> bool:
    return box[0] - eps <= p[0] <= box[2] + eps and box[1] - eps <= p[1] <= box[3] + eps


def box_within(inner: Box, outer: Box, eps: float = 0.0) -> bool:
    return inside((inner[0], inner[1]), outer, eps) and inside((inner[2], inner[3]), outer, eps)


def stretch_path(path: Path, box: Box, displacement: Sequence[float]) -> tuple[Path, list[int]]:
    """Move the vertices inside the window; the rest stay. Bulges are kept, as AutoCAD's STRETCH keeps them.

    Returns (the new path, the vertex numbers that moved).
    """
    eps = tolerance(path)
    dx, dy = float(displacement[0]), float(displacement[1])
    verts = []
    moved = []
    for i, v in enumerate(path["vertices"]):
        if inside(v, box, eps):
            verts.append((v[0] + dx, v[1] + dy))
            moved.append(i)
        else:
            verts.append(_pt(v))
    out = {"vertices": verts, "bulges": list(path["bulges"]), "closed": path["closed"]}
    if moved:
        _check_no_zero_segment(out)
    return out, moved


# ---- writing an arc back ------------------------------------------------------------------


def arc_of(path: Path) -> dict[str, Any]:
    """An open one-arc path as an AutoCAD arc: centre, radius, start and end angle (radians, anticlockwise)."""
    seg = _segs(path)[0]
    if seg.centre is None:
        raise ValueError("That piece is straight, not an arc.")
    start = math.atan2(seg.start[1] - seg.centre[1], seg.start[0] - seg.centre[0])
    end = math.atan2(seg.end[1] - seg.centre[1], seg.end[0] - seg.centre[0])
    if seg.sweep < 0:
        start, end = end, start
    return {"centre": _r(seg.centre), "radius": seg.radius, "start_angle": start % TWO_PI, "end_angle": end % TWO_PI}


def rounded(path: Path) -> dict[str, Any]:
    """A path as the chat reads it: points rounded, bulges as they are."""
    return {
        "vertices": [_r(v) for v in path["vertices"]],
        "bulges": [round(b, 12) for b in path["bulges"]],
        "closed": path["closed"],
    }
