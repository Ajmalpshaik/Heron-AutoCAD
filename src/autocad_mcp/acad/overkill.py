"""Overkill: find doubled and overlapping lines, arcs and circles (#112, D-84).

Plain functions over plain numbers, so all of it is tested without AutoCAD.
The tool reads the curves over COM into the dicts below, asks ``plan`` what to
do, shows that list, and only with confirm=true erases and stretches.

What it does, in the words of AutoCAD's OVERKILL:

- A line, arc or circle lying exactly on another is erased; the oldest one
  (lowest handle) is kept.
- Lines lying on one straight line and overlapping are merged: the oldest is
  stretched to cover them all and the rest are erased. With
  ``join_end_to_end`` lines that only touch end to end are merged too.
- Arcs on one circle are merged the same way; arcs under a circle go.
- Zero-length lines and arcs are erased.
- A polyline that is an exact copy of another (either direction) is erased.
- A loose line or arc lying wholly on a polyline's segments is erased.

What it leaves, and lists under ``left``: polylines are never broken or
changed, so a polyline overlapping another, doubling back on itself, or
partly covered by a loose line stays as it is. Every curve must lie flat in
plan (normal +Z); others are counted as skipped.

Input dicts:
    {"handle", "kind": "line", "layer", "start": [x, y, z], "end": [x, y, z]}
    {"handle", "kind": "arc", "layer", "centre": [x, y, z], "radius",
     "start_angle", "end_angle"}                    # radians, counter-clockwise
    {"handle", "kind": "circle", "layer", "centre": [x, y, z], "radius"}
    {"handle", "kind": "polyline", "layer", "vertices": [[x, y], ...],
     "bulges": [...], "closed": bool, "elevation": z}
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from . import geometry

TAU = 2.0 * math.pi
DEFAULT_TOLERANCE = 1e-6


def handle_order(handle: str) -> int:
    """Handles are hex counters: the lower one was made first."""
    try:
        return int(str(handle), 16)
    except ValueError:
        return 1 << 62


@dataclass
class Piece:
    """One straight or round stretch: a loose curve, or one polyline segment."""

    handle: str
    kind: str  # the entity's kind: line, arc, circle, polyline
    layer: str
    z: float
    free: bool  # a loose line, arc or circle; polyline segments are never changed
    segment: int | None = None
    # straight
    p1: tuple[float, float] = (0.0, 0.0)
    p2: tuple[float, float] = (0.0, 0.0)
    # round
    centre: tuple[float, float] = (0.0, 0.0)
    radius: float = 0.0
    start: float = 0.0  # radians, [0, 2pi)
    sweep: float = 0.0  # radians, > 0, counter-clockwise; 2pi for a circle

    @property
    def straight(self) -> bool:
        return self.radius == 0.0

    @property
    def length(self) -> float:
        if self.straight:
            return math.dist(self.p1, self.p2)
        return self.radius * self.sweep


@dataclass
class Plan:
    erase: list[dict[str, Any]] = field(default_factory=list)
    change: list[dict[str, Any]] = field(default_factory=list)
    left: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    looked_at: int = 0
    _erased: set[str] = field(default_factory=set)
    _left_keys: set[tuple[Any, ...]] = field(default_factory=set)

    def drop(self, handle: str, kind: str, reason: str, kept: str | None = None) -> None:
        if handle in self._erased:
            return
        self._erased.add(handle)
        row: dict[str, Any] = {"handle": handle, "type": kind, "reason": reason}
        if kept:
            row["kept"] = kept
        self.erase.append(row)

    def leave(self, handles: Sequence[str], why: str) -> None:
        names = sorted(set(handles), key=handle_order)
        key = (tuple(names), why)
        if key in self._left_keys:
            return
        self._left_keys.add(key)
        self.left.append({"handles": names, "why": why})

    def as_dict(self) -> dict[str, Any]:
        return {
            "looked_at": self.looked_at,
            "erase": self.erase,
            "change": self.change,
            "left": self.left,
            "skipped": self.skipped,
        }


def _chains(items: list[Any], key: Callable[[Any], float], tol: float) -> list[list[Any]]:
    """Split items into runs whose sorted keys step by no more than tol."""
    ordered = sorted(items, key=key)
    groups: list[list[Any]] = []
    current: list[Any] = []
    last = 0.0
    for item in ordered:
        value = key(item)
        if current and value - last > tol:
            groups.append(current)
            current = []
        current.append(item)
        last = value
    if current:
        groups.append(current)
    return groups


class _Union:
    def __init__(self, count: int) -> None:
        self.parent = list(range(count))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)

    def groups(self) -> list[list[int]]:
        out: dict[int, list[int]] = {}
        for i in range(len(self.parent)):
            out.setdefault(self.find(i), []).append(i)
        return [g for g in out.values() if len(g) > 1]


def _flat(item: dict[str, Any], tol: float) -> bool:
    normal = item.get("normal")
    if normal is None:
        return True
    nx, ny, nz = (float(v) for v in normal)
    return abs(nx) <= 1e-9 and abs(ny) <= 1e-9 and nz > 0


def _pieces(items: Sequence[dict[str, Any]], plan: Plan, tol: float, layer_key: Callable[[str], str]) -> list[Piece]:
    """Every curve as pieces; zero-length ones erased, copies of a polyline erased, the rest skipped with why."""
    pieces: list[Piece] = []
    polylines: list[dict[str, Any]] = []
    for item in items:
        handle, kind, layer = str(item["handle"]), str(item["kind"]), str(item.get("layer", "0"))
        plan.looked_at += 1
        if not _flat(item, tol):
            plan.skipped.append({"handle": handle, "type": kind, "why": "not drawn flat in plan"})
            continue
        if kind == "line":
            (x1, y1, z1), (x2, y2, z2) = (tuple(float(v) for v in item[k][:3]) for k in ("start", "end"))
            if abs(z1 - z2) > tol:
                plan.skipped.append({"handle": handle, "type": kind, "why": "its ends are at different heights"})
                continue
            if math.dist((x1, y1), (x2, y2)) <= tol:
                plan.drop(handle, kind, "zero length")
                continue
            pieces.append(Piece(handle, kind, layer, z1, True, p1=(x1, y1), p2=(x2, y2)))
        elif kind in ("arc", "circle"):
            cx, cy, cz = (float(v) for v in item["centre"][:3])
            radius = float(item["radius"])
            if kind == "circle":
                start, sweep = 0.0, TAU
            else:
                start = float(item["start_angle"]) % TAU
                sweep = (float(item["end_angle"]) - float(item["start_angle"])) % TAU
            if radius <= tol or radius * sweep <= tol:
                plan.drop(handle, kind, "zero length")
                continue
            pieces.append(Piece(handle, kind, layer, cz, True, centre=(cx, cy), radius=radius, start=start, sweep=sweep))
        elif kind == "polyline":
            polylines.append(item)
        else:
            plan.skipped.append({"handle": handle, "type": kind, "why": "not a line, arc, circle or polyline"})
    kept_polylines = _polyline_copies(polylines, plan, tol, layer_key)
    for item in kept_polylines:
        handle, layer = str(item["handle"]), str(item.get("layer", "0"))
        z = float(item.get("elevation", 0.0))
        segs = geometry.segments(item["vertices"], item.get("bulges", []), bool(item.get("closed", False)))
        for index, seg in enumerate(segs):
            if seg.length <= tol:
                continue
            if seg.centre is None:
                pieces.append(Piece(handle, "polyline", layer, z, False, index, p1=seg.start, p2=seg.end))
            else:
                start = seg.start_angle if seg.sweep > 0 else seg.start_angle + seg.sweep
                pieces.append(
                    Piece(handle, "polyline", layer, z, False, index, centre=seg.centre, radius=seg.radius,
                          start=start % TAU, sweep=abs(seg.sweep))
                )
    return pieces


def _polyline_form(item: dict[str, Any]) -> tuple[list[tuple[float, float]], list[float], bool]:
    verts = [(float(v[0]), float(v[1])) for v in item["vertices"]]
    closed = bool(item.get("closed", False))
    count = len(verts) if closed else len(verts) - 1
    bulges = [float(b) for b in item.get("bulges", [])][:count]
    bulges += [0.0] * (count - len(bulges))
    return verts, bulges, closed


def _same_polyline(a: dict[str, Any], b: dict[str, Any], tol: float) -> bool:
    va, ba, ca = _polyline_form(a)
    vb, bb, cb = _polyline_form(b)
    if ca != cb or len(va) != len(vb) or abs(float(a.get("elevation", 0.0)) - float(b.get("elevation", 0.0))) > tol:
        return False
    n = len(va)

    def matches(verts: list[tuple[float, float]], bulges: list[float]) -> bool:
        return all(math.dist(p, q) <= tol for p, q in zip(va, verts, strict=True)) and all(
            abs(x - y) <= 1e-9 for x, y in zip(ba, bulges, strict=True)
        )

    if not ca:
        return matches(vb, bb) or matches(vb[::-1], [-x for x in bb[::-1]])
    for shift in range(n):
        verts = vb[shift:] + vb[:shift]
        if matches(verts, bb[shift:] + bb[:shift]):
            return True
        # The same loop the other way round: vertex order reversed, each bulge
        # moved to the segment before it and turned the other way.
        back = [verts[0]] + verts[1:][::-1]
        back_bulges = [-x for x in (bb[shift:] + bb[:shift])][::-1]
        if matches(back, back_bulges):
            return True
    return False


def _polyline_copies(polylines: list[dict[str, Any]], plan: Plan, tol: float, layer_key: Callable[[str], str]) -> list[dict[str, Any]]:
    """Erase every polyline that is an exact copy of an older one; the polylines kept."""
    ordered = sorted(polylines, key=lambda p: handle_order(str(p["handle"])))
    kept: list[dict[str, Any]] = []
    for item in ordered:
        verts = item["vertices"]
        if len(verts) < 2:
            plan.skipped.append({"handle": str(item["handle"]), "type": "polyline", "why": "fewer than two vertices"})
            continue
        twin = next(
            (
                k for k in kept
                if layer_key(str(k.get("layer", "0"))) == layer_key(str(item.get("layer", "0")))
                and _same_polyline(k, item, tol)
            ),
            None,
        )
        if twin is not None:
            plan.drop(str(item["handle"]), "polyline", f"a copy of polyline {twin['handle']}", str(twin["handle"]))
        else:
            kept.append(item)
    return kept


# ---- straight pieces ---------------------------------------------------------------


def _theta(p: Piece) -> float:
    angle = math.atan2(p.p2[1] - p.p1[1], p.p2[0] - p.p1[0]) % math.pi
    return angle


def _distance_to_line(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    length = math.dist(a, b)
    return abs((b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])) / length


def _along(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    length = math.dist(a, b)
    return ((point[0] - a[0]) * (b[0] - a[0]) + (point[1] - a[1]) * (b[1] - a[1])) / length


def _collinear_overlap(p: Piece, q: Piece, tol: float, join: bool) -> bool:
    """True when q lies on p's line (within tol) and their stretches overlap (or touch, with join)."""
    long_, short = (p, q) if p.length >= q.length else (q, p)
    if any(_distance_to_line(pt, long_.p1, long_.p2) > tol for pt in (short.p1, short.p2)):
        return False
    a, b = sorted(_along(pt, long_.p1, long_.p2) for pt in (short.p1, short.p2))
    overlap = min(b, long_.length) - max(a, 0.0)
    return overlap >= -tol if join else overlap > tol


def _straight_groups(pieces: list[Piece], tol: float, join: bool, layer_key: Callable[[str], str]) -> list[list[Piece]]:
    """Groups of straight pieces that lie on one line and overlap, step to step."""
    if not pieces:
        return []
    # Two pieces on one line point the same way to within about 2 x tol over
    # their length. The step is set from a typical length: a very short piece
    # a little more askew than that is not merged (it stays, which is safe).
    lengths = sorted(p.length for p in pieces)
    typical = lengths[len(lengths) // 2]
    angle_tol = min(0.01, max(1e-12, 4.0 * tol / typical))
    out: list[list[Piece]] = []
    by_layer: dict[str, list[Piece]] = {}
    for p in pieces:
        by_layer.setdefault(layer_key(p.layer), []).append(p)
    for layer_pieces in by_layer.values():
        for level in _chains(layer_pieces, lambda p: p.z, tol):
            # Directions near 180 degrees are the same line as those near 0.
            keyed = []
            for p in level:
                t = _theta(p)
                keyed.append((t - math.pi if t > math.pi - angle_tol else t, p))
            for run in _chains(keyed, lambda kp: kp[0], angle_tol):
                run_pieces = [kp[1] for kp in run]
                spread = max(kp[0] for kp in run) - min(kp[0] for kp in run)
                ref = max(run_pieces, key=lambda p: p.length)
                ux, uy = (ref.p2[0] - ref.p1[0]) / ref.length, (ref.p2[1] - ref.p1[1]) / ref.length

                def offset(p: Piece, ux: float = ux, uy: float = uy, o: tuple[float, float] = ref.p1) -> float:
                    mx, my = (p.p1[0] + p.p2[0]) / 2 - o[0], (p.p1[1] + p.p2[1]) / 2 - o[1]
                    return ux * my - uy * mx

                def along(p: Piece, ux: float = ux, uy: float = uy, o: tuple[float, float] = ref.p1) -> tuple[float, float]:
                    a = (p.p1[0] - o[0]) * ux + (p.p1[1] - o[1]) * uy
                    b = (p.p2[0] - o[0]) * ux + (p.p2[1] - o[1]) * uy
                    return (a, b) if a <= b else (b, a)

                reach = max(max(abs(v) for v in along(p)) for p in run_pieces)
                for band in _chains(run_pieces, offset, 2 * tol + reach * math.sin(spread)):
                    if len(band) < 2:
                        continue
                    spans = sorted(((along(p), i) for i, p in enumerate(band)), key=lambda s: s[0][0])
                    union = _Union(len(band))
                    active: list[tuple[tuple[float, float], int]] = []
                    for (a, b), i in spans:
                        active = [s for s in active if s[0][1] >= a - 2 * tol]
                        for _, j in active:
                            if _collinear_overlap(band[i], band[j], tol, join):
                                union.join(i, j)
                        active.append(((a, b), i))
                    out.extend([band[i] for i in g] for g in union.groups())
    return out


def _covered(span: tuple[float, float], cover: list[tuple[float, float]], tol: float) -> bool:
    return any(c[0] <= span[0] + tol and c[1] >= span[1] - tol for c in cover)


def _overlaps(span: tuple[float, float], cover: list[tuple[float, float]], tol: float) -> bool:
    return any(min(span[1], c[1]) - max(span[0], c[0]) > tol for c in cover)


def _merge_spans(spans: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _straight(group: list[Piece], plan: Plan, tol: float, join: bool) -> None:
    ref = max(group, key=lambda p: p.length)

    def span(p: Piece) -> tuple[tuple[float, float], tuple[tuple[float, float], tuple[float, float]]]:
        a, b = _along(p.p1, ref.p1, ref.p2), _along(p.p2, ref.p1, ref.p2)
        return ((a, b), (p.p1, p.p2)) if a <= b else ((b, a), (p.p2, p.p1))

    fixed = [p for p in group if not p.free]
    loose = [p for p in group if p.free]
    cover = _merge_spans([span(p)[0] for p in fixed], tol)
    for i, p in enumerate(fixed):
        for q in fixed[i + 1:]:
            (sa, _), (sb, _) = span(p), span(q)
            if min(sa[1], sb[1]) - max(sa[0], sb[0]) > tol:
                why = (
                    f"polyline {p.handle} doubles back over itself"
                    if p.handle == q.handle
                    else "two polylines overlap here; Heron does not break polylines"
                )
                plan.leave([p.handle, q.handle], why)
    # Loose lines, in runs that overlap (or touch, with join), each run in order along the line.
    rows = sorted(((span(p), p) for p in loose), key=lambda r: r[0][0][0])
    runs: list[list[Any]] = []
    for row in rows:
        (a, b), _ = row[0]
        if runs:
            end = max(r[0][0][1] for r in runs[-1])
            if (a <= end + tol) if join else (a < end - tol):
                runs[-1].append(row)
                continue
        runs.append([row])
    for run in runs:
        members = [r[1] for r in run]
        low = min(run, key=lambda r: r[0][0][0])
        high = max(run, key=lambda r: r[0][0][1])
        extent = (low[0][0][0], high[0][0][1])
        if cover and _covered(extent, cover, tol):
            owner = next((p.handle for p in fixed if _overlaps(extent, [span(p)[0]], tol)), fixed[0].handle)
            for p in members:
                plan.drop(p.handle, p.kind, f"lies on polyline {owner}", owner)
            continue
        if cover and _overlaps(extent, cover, tol):
            owners = [p.handle for p in fixed if _overlaps(extent, [span(p)[0]], tol)]
            plan.leave([p.handle for p in members] + owners, "a line partly overlaps a polyline; Heron does not break polylines")
        if len(members) < 2:
            continue
        keeper = min(members, key=lambda p: handle_order(p.handle))
        (ka, kb), _ = span(keeper)
        for p in members:
            if p is keeper:
                continue
            (pa, pb), _ = span(p)
            if abs(pa - ka) <= tol and abs(pb - kb) <= tol:
                reason = f"a copy of line {keeper.handle}"
            elif pa >= ka - tol and pb <= kb + tol:
                reason = f"lies inside line {keeper.handle}"
            else:
                reason = f"merged into line {keeper.handle}"
            plan.drop(p.handle, p.kind, reason, keeper.handle)
        if extent[0] < ka - tol or extent[1] > kb + tol:
            first, last = low[0][1][0], high[0][1][1]
            # Keep the keeper's own direction.
            forwards = _along(keeper.p2, ref.p1, ref.p2) >= _along(keeper.p1, ref.p1, ref.p2)
            start, end = (first, last) if forwards else (last, first)
            plan.change.append(
                {
                    "handle": keeper.handle,
                    "type": "line",
                    "start": [start[0], start[1], keeper.z],
                    "end": [end[0], end[1], keeper.z],
                    "was": {"start": [*keeper.p1, keeper.z], "end": [*keeper.p2, keeper.z]},
                    "why": f"stretched over the {len(members) - 1} line(s) merged into it",
                }
            )


# ---- round pieces ------------------------------------------------------------------


def _round_groups(pieces: list[Piece], tol: float, layer_key: Callable[[str], str]) -> list[list[Piece]]:
    out: list[list[Piece]] = []
    by_layer: dict[str, list[Piece]] = {}
    for p in pieces:
        by_layer.setdefault(layer_key(p.layer), []).append(p)
    for layer_pieces in by_layer.values():
        for level in _chains(layer_pieces, lambda p: p.z, tol):
            for xs in _chains(level, lambda p: p.centre[0], tol):
                for ys in _chains(xs, lambda p: p.centre[1], tol):
                    for rs in _chains(ys, lambda p: p.radius, tol):
                        if len(rs) < 2:
                            continue
                        union = _Union(len(rs))
                        for i, p in enumerate(rs):
                            for j in range(i + 1, len(rs)):
                                q = rs[j]
                                if math.dist(p.centre, q.centre) <= tol and abs(p.radius - q.radius) <= tol:
                                    union.join(i, j)
                        out.extend([rs[i] for i in g] for g in union.groups())
    return out


def _ahead(a: float, b: float) -> float:
    """How far b is round from a, counter-clockwise, in [0, 2pi)."""
    return (b - a) % TAU


def _arc_runs(items: list[tuple[float, float, Any]], step: float) -> list[list[Any]]:
    """Circular runs of (start, sweep, payload) that overlap or touch within step: [start, sweep, payloads]."""
    rows = sorted(items, key=lambda r: r[0])
    runs: list[list[Any]] = []
    for start, sweep, payload in rows:
        if runs and start <= runs[-1][0] + runs[-1][1] + step:
            runs[-1][1] = max(runs[-1][1], start + sweep - runs[-1][0])
            runs[-1][2].append(payload)
        else:
            runs.append([start, sweep, [payload]])
    # The last run may reach round past 0 into the first.
    while len(runs) > 1 and runs[0][0] + TAU <= runs[-1][0] + runs[-1][1] + step:
        first = runs.pop(0)
        last = runs[-1]
        last[1] = max(last[1], first[0] + TAU + first[1] - last[0])
        last[2].extend(first[2])
    for run in runs:
        run[1] = min(run[1], TAU)
    return runs


def _arc_covered(start: float, sweep: float, cover: list[list[Any]], step: float) -> bool:
    for c_start, c_sweep, _ in cover:
        if c_sweep >= TAU - step:
            return True
        d = _ahead(c_start, start)
        if d > TAU - step:
            d -= TAU
        if d >= -step and d + sweep <= c_sweep + step:
            return True
    return False


def _arc_overlaps(start: float, sweep: float, other_start: float, other_sweep: float, step: float) -> bool:
    return _ahead(start, other_start) < sweep - step or _ahead(other_start, start) < other_sweep - step


def _round(group: list[Piece], plan: Plan, tol: float, join: bool) -> None:
    radius = max(p.radius for p in group)
    step = tol / radius
    fixed = [p for p in group if not p.free]
    circles = sorted((p for p in group if p.free and p.kind == "circle"), key=lambda p: handle_order(p.handle))
    arcs = [p for p in group if p.free and p.kind == "arc"]
    cover = _arc_runs([(p.start, p.sweep, p) for p in fixed], step)
    for i, p in enumerate(fixed):
        for q in fixed[i + 1:]:
            if _arc_overlaps(p.start, p.sweep, q.start, q.sweep, step):
                why = (
                    f"polyline {p.handle} doubles back over itself"
                    if p.handle == q.handle
                    else "two polylines overlap here; Heron does not break polylines"
                )
                plan.leave([p.handle, q.handle], why)
    if circles:
        keeper = circles[0]
        for c in circles[1:]:
            plan.drop(c.handle, "circle", f"a copy of circle {keeper.handle}", keeper.handle)
        for a in arcs:
            plan.drop(a.handle, "arc", f"lies on circle {keeper.handle}", keeper.handle)
        if fixed and _arc_covered(0.0, TAU, cover, step):
            owner = fixed[0].handle
            plan.drop(keeper.handle, "circle", f"lies on polyline {owner}", owner)
        elif fixed:
            plan.leave([keeper.handle] + [p.handle for p in fixed], "a circle overlaps a polyline's arcs; Heron does not break polylines")
        return
    loose_step = step if join else -step
    for start, sweep, members in _arc_runs([(p.start, p.sweep, p) for p in arcs], loose_step):
        if cover and _arc_covered(start, sweep, cover, step):
            owner = next((p.handle for p in fixed if _arc_overlaps(start, sweep, p.start, p.sweep, step)), fixed[0].handle)
            for p in members:
                plan.drop(p.handle, "arc", f"lies on polyline {owner}", owner)
            continue
        if cover and any(_arc_overlaps(start, sweep, p.start, p.sweep, step) for p in fixed):
            owners = [p.handle for p in fixed if _arc_overlaps(start, sweep, p.start, p.sweep, step)]
            plan.leave([p.handle for p in members] + owners, "an arc partly overlaps a polyline; Heron does not break polylines")
        if len(members) < 2:
            continue
        keeper = min(members, key=lambda p: handle_order(p.handle))
        if sweep >= TAU - step:
            # Together they go all the way round: one arc cannot be a whole
            # circle, so only arcs wholly inside another one go.
            for p in members:
                host = next(
                    (q for q in members if q is not p and q.handle not in plan._erased
                     and _arc_covered(p.start, p.sweep, [[q.start, q.sweep, q]], step)),
                    None,
                )
                if host is not None:
                    plan.drop(p.handle, "arc", f"lies inside arc {host.handle}", host.handle)
            plan.leave([p.handle for p in members if p.handle not in plan._erased],
                       "these arcs together make a whole circle; draw a circle instead")
            continue
        for p in members:
            if p is keeper:
                continue
            same = abs(_ahead(keeper.start, p.start)) <= step or abs(_ahead(keeper.start, p.start) - TAU) <= step
            if same and abs(p.sweep - keeper.sweep) <= step:
                reason = f"a copy of arc {keeper.handle}"
            elif _arc_covered(p.start, p.sweep, [[keeper.start, keeper.sweep, keeper]], step):
                reason = f"lies inside arc {keeper.handle}"
            else:
                reason = f"merged into arc {keeper.handle}"
            plan.drop(p.handle, "arc", reason, keeper.handle)
        if not _arc_covered(start, sweep, [[keeper.start, keeper.sweep, keeper]], step):
            plan.change.append(
                {
                    "handle": keeper.handle,
                    "type": "arc",
                    "start_angle": start % TAU,
                    "end_angle": (start + sweep) % TAU,
                    "was": {"start_angle": keeper.start, "end_angle": (keeper.start + keeper.sweep) % TAU},
                    "why": f"stretched over the {len(members) - 1} arc(s) merged into it",
                }
            )


def plan(
    items: Sequence[dict[str, Any]],
    tolerance: float = DEFAULT_TOLERANCE,
    ignore_layer: bool = False,
    join_end_to_end: bool = False,
) -> dict[str, Any]:
    """What Overkill would erase, stretch and leave, for these curves. Changes nothing."""
    if tolerance <= 0:
        raise ValueError("tolerance must be above zero")
    tol = float(tolerance)
    out = Plan()

    def layer_key(layer: str) -> str:
        return "" if ignore_layer else layer.strip().lower()

    pieces = _pieces(items, out, tol, layer_key)
    straight = [p for p in pieces if p.straight]
    round_ = [p for p in pieces if not p.straight]
    for group in _straight_groups(straight, tol, join_end_to_end, layer_key):
        _straight(group, out, tol, join_end_to_end)
    for group in _round_groups(round_, tol, layer_key):
        _round(group, out, tol, join_end_to_end)
    # A curve erased must not also be stretched.
    out.change = [c for c in out.change if c["handle"] not in out._erased]
    out.erase.sort(key=lambda r: handle_order(r["handle"]))
    out.change.sort(key=lambda r: handle_order(r["handle"]))
    return out.as_dict()
