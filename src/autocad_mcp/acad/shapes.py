"""Complex geometry from a few numbers: the shapes a draftsman asks for by name.

"A 200 flange with 8 holes." "A slot 120 long, 40 wide." "A 1200 wide stair,
14 risers." "The flat pattern for that reducer." Each of those is twenty
minutes of construction lines, or one call.

Every generator here is a **pure function** that returns a list of operations in
exactly the shape ``autocad_batch_draw`` takes. Nothing touches AutoCAD, so all
of it is tested without AutoCAD, and the geometry goes into the drawing down
the one path that is already fast and already UCS-aware.

Arcs come out as polyline **bulges** (tan(sweep / 4), positive anticlockwise),
so a rounded corner, a slot end and an elbow each stay one object rather than
becoming a pile of loose arcs.

Angles in and out are **degrees**. Every shape takes an ``origin``; what that
point means is stated per shape, because for a flange it is the centre and for
a stair it is the bottom of the first riser.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

Point = tuple[float, float]
Op = dict[str, Any]

# A quarter-circle arc as a polyline bulge: tan(90 / 4).
BULGE_90 = math.tan(math.radians(90.0) / 4.0)
# A half-circle, for the ends of a slot.
BULGE_180 = 1.0
# How far round a cone development may open before one polyline arc stops being
# able to hold it; see cone_development.
MAX_DEVELOPMENT_SWEEP = 350.0
EPS = 1e-9


# ---------------------------------------------------------------------------
# Operation builders
# ---------------------------------------------------------------------------


def _style(layer: str | None, color: Any) -> Op:
    out: Op = {}
    if layer:
        out["layer"] = layer
    if color is not None:
        out["color"] = color
    return out


def poly(
    points: Sequence[Point],
    closed: bool = False,
    bulges: Sequence[float] | None = None,
    layer: str | None = None,
    color: Any = None,
) -> Op:
    """One polyline operation, arcs included."""
    op: Op = {"type": "polyline", "points": [[round(x, 9), round(y, 9)] for x, y in points]}
    if closed:
        op["closed"] = True
    if bulges and any(abs(b) > EPS for b in bulges):
        op["bulges"] = [round(float(b), 12) for b in bulges]
    op.update(_style(layer, color))
    return op


def circle(centre: Point, radius: float, layer: str | None = None, color: Any = None) -> Op:
    op: Op = {"type": "circle", "center": [round(centre[0], 9), round(centre[1], 9)],
              "radius": round(float(radius), 9)}
    op.update(_style(layer, color))
    return op


def line(start: Point, end: Point, layer: str | None = None, color: Any = None) -> Op:
    op: Op = {"type": "line", "start": [round(start[0], 9), round(start[1], 9)],
              "end": [round(end[0], 9), round(end[1], 9)]}
    op.update(_style(layer, color))
    return op


def text(
    at: Point,
    value: str,
    height: float,
    align: str = "center",
    rotation: float = 0.0,
    layer: str | None = None,
    color: Any = None,
) -> Op:
    """One text operation. ``align='center'`` sits it on its point both ways."""
    op: Op = {"type": "text", "position": [round(at[0], 9), round(at[1], 9)],
              "text": str(value), "height": round(float(height), 9)}
    if align != "left":
        op["align"] = align
    if rotation:
        op["rotation"] = round(float(rotation) % 360.0, 9)
    op.update(_style(layer, color))
    return op


def arc(centre: Point, radius: float, start_angle: float, end_angle: float,
        layer: str | None = None, color: Any = None) -> Op:
    op: Op = {"type": "arc", "center": [round(centre[0], 9), round(centre[1], 9)],
              "radius": round(float(radius), 9),
              "start_angle": round(float(start_angle) % 360.0, 9),
              "end_angle": round(float(end_angle) % 360.0, 9)}
    op.update(_style(layer, color))
    return op


# ---------------------------------------------------------------------------
# Plane helpers
# ---------------------------------------------------------------------------


def turn(point: Point, degrees: float, about: Point = (0.0, 0.0)) -> Point:
    """A point turned about another, anticlockwise."""
    angle = math.radians(float(degrees))
    cos, sin = math.cos(angle), math.sin(angle)
    dx, dy = point[0] - about[0], point[1] - about[1]
    return (about[0] + dx * cos - dy * sin, about[1] + dx * sin + dy * cos)


def shift(points: Sequence[Point], by: Point) -> list[Point]:
    return [(x + by[0], y + by[1]) for x, y in points]


def place(points: Sequence[Point], origin: Point, rotation: float = 0.0) -> list[Point]:
    """A shape built about (0, 0), turned and then moved to where it belongs."""
    if rotation:
        points = [turn(p, rotation) for p in points]
    return shift(points, origin)


def on_circle(centre: Point, radius: float, degrees: float) -> Point:
    angle = math.radians(float(degrees))
    return (centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle))


def bulge_for(sweep_degrees: float) -> float:
    """A polyline bulge for an arc of this sweep: tan(sweep / 4)."""
    return math.tan(math.radians(float(sweep_degrees)) / 4.0)


def _positive(value: Any, name: str) -> float:
    number = float(value)
    if number <= 0.0:
        raise ValueError(f"{name} must be above zero, got {number:g}")
    return number


def _at_least(value: Any, least: int, name: str) -> int:
    number = int(value)
    if number < least:
        raise ValueError(f"{name} must be at least {least}, got {number}")
    return number


def _point(value: Any, name: str = "origin") -> Point:
    if value is None:
        return (0.0, 0.0)
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, IndexError, ValueError):
        raise ValueError(f"{name} must be [x, y], got {value!r}") from None


# ---------------------------------------------------------------------------
# The shapes
# ---------------------------------------------------------------------------


def polygon(sides: int, radius: float, origin: Any = None, inscribed: bool = True,
            rotation: float = 0.0, layer: str | None = None, color: Any = None) -> list[Op]:
    """A regular polygon. origin = the centre.

    ``inscribed`` measures the radius to a corner (AutoCAD's "inscribed in
    circle"); False measures it to the middle of a flat.
    """
    n = _at_least(sides, 3, "sides")
    r = _positive(radius, "radius")
    if not inscribed:
        r = r / math.cos(math.pi / n)
    pts = [on_circle((0.0, 0.0), r, 360.0 * i / n) for i in range(n)]
    return [poly(place(pts, _point(origin), rotation), closed=True, layer=layer, color=color)]


def hexagon(across_flats: float | None = None, across_corners: float | None = None,
            origin: Any = None, rotation: float = 0.0,
            layer: str | None = None, color: Any = None) -> list[Op]:
    """A hexagon sized the way a spanner or a bolt table gives it. origin = the centre.

    Give ``across_flats`` (A/F, what a spanner reads) or ``across_corners``.
    """
    if across_flats is None and across_corners is None:
        raise ValueError("give across_flats (what a spanner reads) or across_corners")
    if across_flats is not None:
        radius = _positive(across_flats, "across_flats") / 2.0 / math.cos(math.pi / 6.0)
    else:
        radius = _positive(across_corners, "across_corners") / 2.0
    # A corner on +X puts a flat top and bottom, so the across-flats dimension
    # reads vertically - how a nut or a bolt head is normally drawn. rotation=30
    # turns it the other way round.
    return polygon(6, radius, origin, inscribed=True, rotation=rotation,
                   layer=layer, color=color)


def star(points: int, outer_radius: float, inner_radius: float | None = None,
         origin: Any = None, rotation: float = 0.0,
         layer: str | None = None, color: Any = None) -> list[Op]:
    """A star. origin = the centre. Without inner_radius a pleasing one is used."""
    n = _at_least(points, 3, "points")
    outer = _positive(outer_radius, "outer_radius")
    inner = _positive(inner_radius, "inner_radius") if inner_radius else outer * 0.382
    if inner >= outer:
        raise ValueError(f"inner_radius ({inner:g}) must be smaller than outer_radius ({outer:g})")
    pts: list[Point] = []
    for i in range(n):
        pts.append(on_circle((0.0, 0.0), outer, 360.0 * i / n + 90.0))
        pts.append(on_circle((0.0, 0.0), inner, 360.0 * (i + 0.5) / n + 90.0))
    return [poly(place(pts, _point(origin), rotation), closed=True, layer=layer, color=color)]


def slot(length: float, width: float, origin: Any = None, rotation: float = 0.0,
         layer: str | None = None, color: Any = None) -> list[Op]:
    """An obround slot: two straights and a half-round each end. origin = the centre.

    ``length`` is the overall length (end to end), ``width`` the diameter of
    the ends - the way a fabrication drawing calls it out.
    """
    total = _positive(length, "length")
    w = _positive(width, "width")
    if total <= w:
        raise ValueError(
            f"length ({total:g}) must be more than width ({w:g}); at or below it the slot is "
            "just a hole, so use a circle"
        )
    half, r = (total - w) / 2.0, w / 2.0
    pts = [(-half, -r), (half, -r), (half, r), (-half, r)]
    # The half-round sits on the segment leaving the right-hand bottom corner,
    # and again leaving the left-hand top one.
    bulges = [0.0, BULGE_180, 0.0, BULGE_180]
    return [poly(place(pts, _point(origin), rotation), closed=True, bulges=bulges,
                 layer=layer, color=color)]


def rounded_rectangle(width: float, height: float, radius: float, origin: Any = None,
                      rotation: float = 0.0, centred: bool = False,
                      layer: str | None = None, color: Any = None) -> list[Op]:
    """A rectangle with filleted corners, as one polyline. origin = bottom-left.

    ``centred`` puts the origin in the middle instead.
    """
    w = _positive(width, "width")
    h = _positive(height, "height")
    r = _positive(radius, "radius")
    if r > min(w, h) / 2.0 + EPS:
        raise ValueError(
            f"a radius of {r:g} will not fit a {w:g} x {h:g} rectangle; the most it takes is "
            f"{min(w, h) / 2.0:g}"
        )
    pts: list[Point] = [
        (r, 0.0), (w - r, 0.0),        # bottom
        (w, r), (w, h - r),            # right
        (w - r, h), (r, h),            # top
        (0.0, h - r), (0.0, r),        # left
    ]
    bulges = [0.0, BULGE_90, 0.0, BULGE_90, 0.0, BULGE_90, 0.0, BULGE_90]
    if centred:
        pts = shift(pts, (-w / 2.0, -h / 2.0))
    return [poly(place(pts, _point(origin), rotation), closed=True, bulges=bulges,
                 layer=layer, color=color)]


def spiral(turns: float, start_radius: float, end_radius: float, origin: Any = None,
           per_turn: int = 72, rotation: float = 0.0,
           layer: str | None = None, color: Any = None) -> list[Op]:
    """A flat spiral, radius growing evenly. origin = the centre."""
    laps = _positive(turns, "turns")
    r0 = float(start_radius)
    r1 = float(end_radius)
    if r0 < 0 or r1 < 0:
        raise ValueError("a spiral's radii cannot be negative")
    if abs(r1 - r0) < EPS:
        raise ValueError("start_radius and end_radius are the same, which is a circle")
    steps = max(8, int(_at_least(per_turn, 8, "per_turn") * laps))
    pts = [
        on_circle((0.0, 0.0), r0 + (r1 - r0) * i / steps, 360.0 * laps * i / steps)
        for i in range(steps + 1)
    ]
    return [poly(place(pts, _point(origin), rotation), layer=layer, color=color)]


def bolt_circle(count: int, pitch_diameter: float, hole_diameter: float, origin: Any = None,
                rotation: float = 0.0, layer: str | None = None, color: Any = None) -> list[Op]:
    """Holes evenly round a pitch circle. origin = the centre."""
    n = _at_least(count, 1, "count")
    pcd = _positive(pitch_diameter, "pitch_diameter")
    hole = _positive(hole_diameter, "hole_diameter")
    centre = _point(origin)
    return [
        circle(on_circle(centre, pcd / 2.0, 360.0 * i / n + rotation), hole / 2.0,
               layer=layer, color=color)
        for i in range(n)
    ]


def flange(outer_diameter: float, bolt_count: int, pitch_diameter: float,
           hole_diameter: float, bore: float | None = None, origin: Any = None,
           rotation: float = 0.0, layer: str | None = None, color: Any = None,
           centreline_layer: str | None = None) -> list[Op]:
    """A flange face: outside, bore, and the bolt holes on their pitch circle.

    origin = the centre. The pitch circle is drawn too, on
    ``centreline_layer`` when one is given - a drafter wants it as a centre
    line, not as solid linework.
    """
    od = _positive(outer_diameter, "outer_diameter")
    pcd = _positive(pitch_diameter, "pitch_diameter")
    hole = _positive(hole_diameter, "hole_diameter")
    if pcd >= od:
        raise ValueError(f"the pitch circle ({pcd:g}) must sit inside the flange ({od:g})")
    centre = _point(origin)
    ops = [circle(centre, od / 2.0, layer=layer, color=color)]
    if bore:
        inner = _positive(bore, "bore")
        if inner >= pcd:
            raise ValueError(f"the bore ({inner:g}) must sit inside the pitch circle ({pcd:g})")
        ops.append(circle(centre, inner / 2.0, layer=layer, color=color))
    ops.append(circle(centre, pcd / 2.0, layer=centreline_layer or layer, color=color))
    ops.extend(bolt_circle(bolt_count, pcd, hole, centre, rotation, layer=layer, color=color))
    return ops


def elbow(centreline_radius: float, angle: float, width: float, origin: Any = None,
          rotation: float = 0.0, layer: str | None = None, color: Any = None,
          centreline_layer: str | None = None) -> list[Op]:
    """A pipe or duct elbow in plan: inside and outside radius, plus the centreline.

    origin = the centre the elbow turns about. The run starts along +X and
    sweeps anticlockwise through ``angle``.
    """
    r = _positive(centreline_radius, "centreline_radius")
    w = _positive(width, "width")
    sweep = float(angle)
    if abs(sweep) < EPS or abs(sweep) >= 360.0:
        raise ValueError(f"an elbow needs an angle between 0 and 360 degrees, got {sweep:g}")
    if w / 2.0 >= r:
        raise ValueError(
            f"a width of {w:g} does not fit a centreline radius of {r:g}; the inside radius "
            "would be zero or negative"
        )
    centre = _point(origin)
    start, end = rotation, rotation + sweep
    lo, hi = sorted((start, end))
    ops = [
        arc(centre, r - w / 2.0, lo, hi, layer=layer, color=color),
        arc(centre, r + w / 2.0, lo, hi, layer=layer, color=color),
        arc(centre, r, lo, hi, layer=centreline_layer or layer, color=color),
    ]
    # Close both ends square across the duct.
    for at in (start, end):
        ops.append(
            line(on_circle(centre, r - w / 2.0, at), on_circle(centre, r + w / 2.0, at),
                 layer=layer, color=color)
        )
    return ops


def duct_transition(width_in: float, width_out: float, length: float, origin: Any = None,
                    rotation: float = 0.0, offset: float = 0.0,
                    layer: str | None = None, color: Any = None,
                    centreline_layer: str | None = None) -> list[Op]:
    """A transition piece in plan: one width to another over a length.

    origin = the middle of the inlet. ``offset`` shifts the outlet sideways for
    an off-centre transition. Returns the two sides, both ends, and the centreline.
    """
    a = _positive(width_in, "width_in")
    b = _positive(width_out, "width_out")
    run = _positive(length, "length")
    pts = [
        (0.0, -a / 2.0), (run, offset - b / 2.0),
        (run, offset + b / 2.0), (0.0, a / 2.0),
    ]
    placed = place(pts, _point(origin), rotation)
    middle = place([(0.0, 0.0), (run, offset)], _point(origin), rotation)
    return [
        poly(placed, closed=True, layer=layer, color=color),
        line(middle[0], middle[1], layer=centreline_layer or layer, color=color),
    ]


def stair(risers: int, rise: float, going: float, width: float, origin: Any = None,
          view: str = "section", rotation: float = 0.0,
          layer: str | None = None, color: Any = None) -> list[Op]:
    """A stair, in section or in plan. origin = the bottom of the first riser.

    ``risers`` is the number of risers; a flight always has one more riser than
    it has treads. ``view='section'`` draws the step profile and the two
    nosing lines; ``view='plan'`` draws the flight outline with a tread line
    per step and an arrow line up the middle.
    """
    n = _at_least(risers, 1, "risers")
    r = _positive(rise, "rise")
    g = _positive(going, "going")
    w = _positive(width, "width")
    start = _point(origin)
    kind = str(view).strip().lower()

    if kind == "section":
        pts: list[Point] = [(0.0, 0.0)]
        for i in range(n):
            pts.append((i * g, (i + 1) * r))          # up the riser
            pts.append(((i + 1) * g, (i + 1) * r))    # along the tread
        profile = [poly(place(pts, start, rotation), layer=layer, color=color)]
        # The line a stair is set out from: nosing to nosing.
        pitch = place([(0.0, 0.0), (n * g, n * r)], start, rotation)
        profile.append(line(pitch[0], pitch[1], layer=layer, color=color))
        return profile

    if kind == "plan":
        total = n * g
        outline = place([(0.0, 0.0), (total, 0.0), (total, w), (0.0, w)], start, rotation)
        ops = [poly(outline, closed=True, layer=layer, color=color)]
        for i in range(1, n):
            edge = place([(i * g, 0.0), (i * g, w)], start, rotation)
            ops.append(line(edge[0], edge[1], layer=layer, color=color))
        walk = place([(0.0, w / 2.0), (total, w / 2.0)], start, rotation)
        ops.append(line(walk[0], walk[1], layer=layer, color=color))
        return ops

    raise ValueError(f"view must be 'section' or 'plan', got {view!r}")


def ladder(height: float, width: float, rungs: int | None = None, spacing: float = 300.0,
           origin: Any = None, rotation: float = 0.0,
           layer: str | None = None, color: Any = None) -> list[Op]:
    """A ladder in elevation: two stiles and the rungs. origin = bottom-left.

    Give ``rungs``, or leave it out and the rungs go in at ``spacing``.
    """
    h = _positive(height, "height")
    w = _positive(width, "width")
    count = int(rungs) if rungs else max(1, int(h // _positive(spacing, "spacing")) - 1)
    if count < 1:
        raise ValueError(f"a {h:g} high ladder at {spacing:g} spacing has no room for a rung")
    start = _point(origin)
    ops = []
    for x in (0.0, w):
        side = place([(x, 0.0), (x, h)], start, rotation)
        ops.append(line(side[0], side[1], layer=layer, color=color))
    step = h / (count + 1)
    for i in range(1, count + 1):
        rung = place([(0.0, i * step), (w, i * step)], start, rotation)
        ops.append(line(rung[0], rung[1], layer=layer, color=color))
    return ops


def grating(width: float, height: float, spacing: float, origin: Any = None,
            direction: str = "x", rotation: float = 0.0,
            layer: str | None = None, color: Any = None) -> list[Op]:
    """A bar grating or louvre panel: an outline and evenly spaced bars. origin = bottom-left."""
    w = _positive(width, "width")
    h = _positive(height, "height")
    gap = _positive(spacing, "spacing")
    start = _point(origin)
    ops = [poly(place([(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)], start, rotation),
                closed=True, layer=layer, color=color)]
    along = str(direction).strip().lower()
    if along not in ("x", "y"):
        raise ValueError("direction must be 'x' (bars running across) or 'y' (bars running up)")
    span = w if along == "y" else h
    count = int(span // gap)
    for i in range(1, count + 1):
        at = i * gap
        if at >= span - EPS:
            break
        pair = [(at, 0.0), (at, h)] if along == "y" else [(0.0, at), (w, at)]
        bar = place(pair, start, rotation)
        ops.append(line(bar[0], bar[1], layer=layer, color=color))
    return ops


def truss(span: float, depth: float, panels: int, origin: Any = None, rotation: float = 0.0,
          layer: str | None = None, color: Any = None) -> list[Op]:
    """A parallel-chord truss: two chords, verticals and diagonals. origin = bottom-left."""
    length = _positive(span, "span")
    d = _positive(depth, "depth")
    n = _at_least(panels, 1, "panels")
    start = _point(origin)
    step = length / n
    bottom = place([(0.0, 0.0), (length, 0.0)], start, rotation)
    top = place([(0.0, d), (length, d)], start, rotation)
    ops = [line(bottom[0], bottom[1], layer=layer, color=color),
           line(top[0], top[1], layer=layer, color=color)]
    for i in range(n + 1):
        post = place([(i * step, 0.0), (i * step, d)], start, rotation)
        ops.append(line(post[0], post[1], layer=layer, color=color))
    for i in range(n):
        # Alternating diagonals, the usual Warren arrangement.
        low, high = (i * step, 0.0), ((i + 1) * step, d)
        if i % 2:
            low, high = (i * step, d), ((i + 1) * step, 0.0)
        brace = place([low, high], start, rotation)
        ops.append(line(brace[0], brace[1], layer=layer, color=color))
    return ops


def zigzag(length: float, amplitude: float, cycles: int, origin: Any = None,
           rotation: float = 0.0, layer: str | None = None, color: Any = None) -> list[Op]:
    """A zigzag: a break line, an insulation symbol, a spring. origin = the left end."""
    run = _positive(length, "length")
    amp = _positive(amplitude, "amplitude")
    n = _at_least(cycles, 1, "cycles")
    step = run / (2.0 * n)
    pts: list[Point] = [(0.0, 0.0)]
    for i in range(2 * n):
        pts.append(((i + 0.5) * step, amp if i % 2 == 0 else -amp))
    pts.append((run, 0.0))
    return [poly(place(pts, _point(origin), rotation), layer=layer, color=color)]


STEEL_SECTIONS = ("i", "h", "c", "l", "t", "shs", "rhs", "chs")


def steel_section(profile: str, depth: float, width: float, web: float = 0.0,
                  flange_thickness: float = 0.0, origin: Any = None, rotation: float = 0.0,
                  layer: str | None = None, color: Any = None) -> list[Op]:
    """A structural steel section's outline, square corners. origin = the middle of the section.

    ``profile``: i / h (universal beam or column), c (channel), l (angle),
    t (tee), shs / rhs (hollow square or rectangle), chs (circular hollow).
    ``web`` is the web or wall thickness, ``flange_thickness`` the flange's.
    """
    kind = str(profile).strip().lower()
    if kind not in STEEL_SECTIONS:
        raise ValueError(f"profile must be one of: {', '.join(STEEL_SECTIONS)}")
    d = _positive(depth, "depth")
    b = _positive(width, "width")
    centre = _point(origin)

    if kind == "chs":
        wall = _positive(web or flange_thickness, "web (the wall thickness)")
        if wall * 2.0 >= d:
            raise ValueError(f"a wall of {wall:g} is too thick for a {d:g} diameter tube")
        return [circle(centre, d / 2.0, layer=layer, color=color),
                circle(centre, d / 2.0 - wall, layer=layer, color=color)]

    if kind in ("shs", "rhs"):
        wall = _positive(web or flange_thickness, "web (the wall thickness)")
        if wall * 2.0 >= min(d, b):
            raise ValueError(f"a wall of {wall:g} is too thick for a {b:g} x {d:g} tube")
        outer = [(-b / 2, -d / 2), (b / 2, -d / 2), (b / 2, d / 2), (-b / 2, d / 2)]
        inner = [(-b / 2 + wall, -d / 2 + wall), (b / 2 - wall, -d / 2 + wall),
                 (b / 2 - wall, d / 2 - wall), (-b / 2 + wall, d / 2 - wall)]
        return [poly(place(outer, centre, rotation), closed=True, layer=layer, color=color),
                poly(place(inner, centre, rotation), closed=True, layer=layer, color=color)]

    tw = _positive(web, "web")
    tf = _positive(flange_thickness, "flange_thickness")
    if tf * 2.0 >= d:
        raise ValueError(f"flanges of {tf:g} are too thick for a {d:g} deep section")
    if tw >= b:
        raise ValueError(f"a web of {tw:g} is wider than the {b:g} flange")

    if kind in ("i", "h"):
        pts = [
            (-b / 2, -d / 2), (b / 2, -d / 2), (b / 2, -d / 2 + tf),
            (tw / 2, -d / 2 + tf), (tw / 2, d / 2 - tf), (b / 2, d / 2 - tf),
            (b / 2, d / 2), (-b / 2, d / 2), (-b / 2, d / 2 - tf),
            (-tw / 2, d / 2 - tf), (-tw / 2, -d / 2 + tf), (-b / 2, -d / 2 + tf),
        ]
    elif kind == "c":
        pts = [
            (-b / 2, -d / 2), (b / 2, -d / 2), (b / 2, -d / 2 + tf),
            (-b / 2 + tw, -d / 2 + tf), (-b / 2 + tw, d / 2 - tf), (b / 2, d / 2 - tf),
            (b / 2, d / 2), (-b / 2, d / 2),
        ]
    elif kind == "t":
        # A tee: the flange across the top, the stem hanging below it.
        pts = [
            (-tw / 2, -d / 2), (tw / 2, -d / 2), (tw / 2, d / 2 - tf), (b / 2, d / 2 - tf),
            (b / 2, d / 2), (-b / 2, d / 2), (-b / 2, d / 2 - tf), (-tw / 2, d / 2 - tf),
        ]
    else:  # l - an angle, its heel at the bottom left
        pts = [
            (-b / 2, -d / 2), (b / 2, -d / 2), (b / 2, -d / 2 + tf),
            (-b / 2 + tw, -d / 2 + tf), (-b / 2 + tw, d / 2), (-b / 2, d / 2),
        ]
    return [poly(place(pts, centre, rotation), closed=True, layer=layer, color=color)]


def cone_development(bottom_diameter: float, top_diameter: float, height: float,
                     origin: Any = None, rotation: float = 0.0, seam_allowance: float = 0.0,
                     layer: str | None = None, color: Any = None,
                     centreline_layer: str | None = None) -> list[Op]:
    """The flat pattern for a round reducer or cone - what the sheet metal is cut from.

    origin = the apex of the development (the point both arcs are struck from);
    for a plain cylinder it is the bottom-left of the rectangle instead.

    A frustum opens out as a ring sector. With a slant length L and radii R1
    (bottom) and R2 (top), the sector runs from radius L*R2/(R1-R2) out to
    L*R1/(R1-R2) and subtends 2*pi*(R1-R2)/L. A top diameter of 0 gives a full
    cone, where the inner radius is 0 and the sector is a pie slice.

    Equal diameters are a cylinder, not a cone: that pattern is a plain
    rectangle 2*pi*R by the height, so use the 'grating' outline or a
    rectangle for it. It is refused here rather than silently dividing by zero.
    """
    r1 = _positive(bottom_diameter, "bottom_diameter") / 2.0
    r2 = _positive(top_diameter, "top_diameter") / 2.0 if top_diameter else 0.0
    h = _positive(height, "height")
    if r2 < 0:
        raise ValueError("top_diameter cannot be negative")
    if r2 >= r1:
        raise ValueError(
            f"the bottom ({r1 * 2:g}) must be wider than the top ({r2 * 2:g}); turn the piece "
            "over, or use the cylinder case with equal diameters"
        )
    start = _point(origin)
    slant = math.hypot(h, r1 - r2)

    outer = slant * r1 / (r1 - r2)
    inner = slant * r2 / (r1 - r2)
    sweep = math.degrees(2.0 * math.pi * (r1 - r2) / slant)
    # A frustum can never open past a full circle, because (R1 - R2) is never
    # longer than the slant. What it can do is come so close to 360 degrees
    # that one polyline bulge - tan(sweep / 4) - runs away: at 359.9 degrees it
    # is already over 3000, and the arc stops being drawable. That only happens
    # on a piece so shallow it is really a flat ring, so it is refused by name.
    if sweep >= MAX_DEVELOPMENT_SWEEP:
        raise ValueError(
            f"that piece is so shallow it opens out to {sweep:.1f} degrees, which one arc "
            "cannot hold. It is nearer a flat ring than a cone: draw it as two circles, or "
            "give it more height"
        )
    half = sweep / 2.0
    a0, a1 = rotation - half, rotation + half
    pts = [
        on_circle((0.0, 0.0), inner, a0), on_circle((0.0, 0.0), outer, a0),
        on_circle((0.0, 0.0), outer, a1), on_circle((0.0, 0.0), inner, a1),
    ]
    bulges = [0.0, bulge_for(sweep), 0.0, bulge_for(-sweep)] if inner > EPS else [0.0, bulge_for(sweep), 0.0, 0.0]
    ops = [poly(shift(pts, start), closed=True, bulges=bulges, layer=layer, color=color)]
    middle = [on_circle((0.0, 0.0), inner, rotation), on_circle((0.0, 0.0), outer, rotation)]
    ops.append(line(shift(middle, start)[0], shift(middle, start)[1],
                    layer=centreline_layer or layer, color=color))
    if seam_allowance:
        lap = _positive(seam_allowance, "seam_allowance")
        extra = math.degrees(lap / outer)
        edge = [on_circle((0.0, 0.0), inner, a1 + extra), on_circle((0.0, 0.0), outer, a1 + extra)]
        ops.append(line(shift(edge, start)[0], shift(edge, start)[1],
                        layer=centreline_layer or layer, color=color))
    return ops


def gear(teeth: int, pitch_diameter: float, origin: Any = None, pressure_angle: float = 20.0,
         show_teeth: bool = False, rotation: float = 0.0,
         layer: str | None = None, color: Any = None,
         centreline_layer: str | None = None, hidden_layer: str | None = None) -> list[Op]:
    """A spur gear. origin = the centre.

    By default it is drawn the way a drawing office draws one: tip circle solid,
    pitch circle as a centre line, root circle hidden, and the tooth count in a
    note beside it. ``show_teeth=True`` adds a tooth outline as well - that
    outline is a **straight-flank representation at the pressure angle, not a
    generated involute**, so it is for reading, not for cutting from.
    """
    n = _at_least(teeth, 6, "teeth")
    pcd = _positive(pitch_diameter, "pitch_diameter")
    module = pcd / n
    tip = pcd + 2.0 * module
    root = pcd - 2.5 * module
    centre = _point(origin)
    ops = [
        circle(centre, tip / 2.0, layer=layer, color=color),
        circle(centre, pcd / 2.0, layer=centreline_layer or layer, color=color),
        circle(centre, root / 2.0, layer=hidden_layer or layer, color=color),
    ]
    if not show_teeth:
        return ops

    angle = float(pressure_angle)
    if not 0.0 < angle < 45.0:
        raise ValueError(f"pressure_angle must be between 0 and 45 degrees, got {angle:g}")
    pitch = 360.0 / n
    # Half the tooth sits each side of its centre at the pitch circle; the
    # flanks lean back by the pressure angle, which narrows the tip.
    half_at_pitch = pitch / 4.0
    lean = math.degrees(math.tan(math.radians(angle)) * module / (pcd / 2.0))
    for i in range(n):
        middle = rotation + i * pitch
        pts = [
            on_circle((0.0, 0.0), root / 2.0, middle - half_at_pitch - lean),
            on_circle((0.0, 0.0), tip / 2.0, middle - half_at_pitch + lean),
            on_circle((0.0, 0.0), tip / 2.0, middle + half_at_pitch - lean),
            on_circle((0.0, 0.0), root / 2.0, middle + half_at_pitch + lean),
        ]
        ops.append(poly(shift(pts, centre), layer=layer, color=color))
    return ops


# ---------------------------------------------------------------------------
# Drafting furniture
# ---------------------------------------------------------------------------
#
# Every office has blocks for these, and a block is better: it carries the
# office's own line weights and its attributes. These are here for the drawing
# that has no block library to hand - use autocad_insert_block when you do.


def detail_bubble(number: Any, radius: float, origin: Any = None, sheet: Any = None,
                  text_height: float | None = None, layer: str | None = None,
                  color: Any = None) -> list[Op]:
    """A detail or section reference bubble. origin = the centre.

    With ``sheet`` it is split across the middle: the detail number above the
    line, the sheet it is drawn on below - the usual convention.
    """
    r = _positive(radius, "radius")
    centre = _point(origin)
    size = float(text_height) if text_height else r * 0.7
    ops = [circle(centre, r, layer=layer, color=color)]
    if sheet in (None, ""):
        ops.append(text(centre, number, size, layer=layer, color=color))
        return ops
    ops.append(line((centre[0] - r, centre[1]), (centre[0] + r, centre[1]),
                    layer=layer, color=color))
    ops.append(text((centre[0], centre[1] + r / 2.0), number, size, layer=layer, color=color))
    ops.append(text((centre[0], centre[1] - r / 2.0), sheet, size, layer=layer, color=color))
    return ops


def _arrowhead(tip: Point, degrees: float, size: float, layer: str | None,
               color: Any) -> Op:
    """A triangular arrowhead pointing along an angle, as a closed polyline.

    An outline, not a filled head: a batch has no solid fill. Hatch it, or use
    the office block, when a filled head matters.
    """
    back = turn((-size, 0.0), degrees)
    wing = size * 0.3
    left = turn((-size, wing), degrees)
    right = turn((-size, -wing), degrees)
    return poly([tip, (tip[0] + left[0], tip[1] + left[1]),
                 (tip[0] + back[0], tip[1] + back[1]),
                 (tip[0] + right[0], tip[1] + right[1])],
                closed=True, layer=layer, color=color)


def section_mark(length: float, origin: Any = None, label: Any = "A", size: float | None = None,
                 rotation: float = 0.0, flip: bool = False, text_height: float | None = None,
                 layer: str | None = None, color: Any = None) -> list[Op]:
    """A section cut mark: the cut line, a tail and an arrow each end, and a bubble each end.

    origin = where the cut line starts. The arrows point the way the section is
    looked at; ``flip`` turns them round.
    """
    run = _positive(length, "length")
    start = _point(origin)
    mark = float(size) if size else run * 0.12
    height = float(text_height) if text_height else mark * 0.8
    side = -1.0 if flip else 1.0
    ops: list[Op] = []

    cut = place([(0.0, 0.0), (run, 0.0)], start, rotation)
    ops.append(line(cut[0], cut[1], layer=layer, color=color))

    for at in (0.0, run):
        # The tail runs off the cut line, then the arrow points along the view.
        tail = place([(at, 0.0), (at, side * mark)], start, rotation)
        ops.append(line(tail[0], tail[1], layer=layer, color=color))
        ops.append(_arrowhead(tail[1], rotation + (90.0 if side > 0 else -90.0), mark * 0.5,
                              layer, color))
        bubble = place([(at, side * (mark + mark * 0.9))], start, rotation)[0]
        ops.extend(detail_bubble(label, mark * 0.9, bubble, text_height=height,
                                 layer=layer, color=color))
    return ops


def north_arrow(size: float, origin: Any = None, rotation: float = 0.0,
                text_height: float | None = None, layer: str | None = None,
                color: Any = None) -> list[Op]:
    """A north point. origin = the base of the arrow; it points up before rotation."""
    s = _positive(size, "size")
    start = _point(origin)
    height = float(text_height) if text_height else s * 0.18
    # A slim kite: the classic half-filled north point, as an outline.
    body = [(0.0, 0.0), (s * 0.18, s * 0.3), (0.0, s), (-s * 0.18, s * 0.3)]
    ops = [poly(place(body, start, rotation), closed=True, layer=layer, color=color)]
    spine = place([(0.0, 0.0), (0.0, s)], start, rotation)
    ops.append(line(spine[0], spine[1], layer=layer, color=color))
    at = place([(0.0, s + height * 1.4)], start, rotation)[0]
    ops.append(text(at, "N", height, rotation=rotation, layer=layer, color=color))
    return ops


def scale_bar(scale: Any, length: float, origin: Any = None, divisions: int = 5,
              height: float | None = None, text_height: float | None = None,
              units: str = "", layer: str | None = None, color: Any = None) -> list[Op]:
    """A graphic scale bar. origin = the bottom-left of the bar.

    ``length`` is the bar's length **on the paper**; the labels are the real
    distances that length stands for at ``scale``. A 100 mm bar at 1:50 reads
    0 to 5000.
    """
    from .sheets import parse_typed_scale, scale_text

    ratio = parse_typed_scale(scale)
    run = _positive(length, "length")
    n = _at_least(divisions, 1, "divisions")
    bar = float(height) if height else run * 0.06
    size = float(text_height) if text_height else bar * 1.1
    start = _point(origin)
    step = run / n
    real = run / ratio / n

    ops: list[Op] = []
    for i in range(n):
        box = [(i * step, 0.0), ((i + 1) * step, 0.0), ((i + 1) * step, bar), (i * step, bar)]
        ops.append(poly(shift(box, start), closed=True, layer=layer, color=color))
        # Every other division gets a diagonal, which reads as the filled
        # alternate box a scale bar is meant to have.
        if i % 2 == 0:
            cross = shift([(i * step, 0.0), ((i + 1) * step, bar)], start)
            ops.append(line(cross[0], cross[1], layer=layer, color=color))
    for i in range(n + 1):
        label = f"{round(i * real, 3):g}"
        if units and i == n:
            label = f"{label} {units}"
        ops.append(text(shift([(i * step, -size * 1.2)], start)[0], label, size,
                        layer=layer, color=color))
    ops.append(text(shift([(run / 2.0, bar + size * 1.2)], start)[0],
                    f"SCALE {scale_text(ratio)}", size, layer=layer, color=color))
    return ops


def level_mark(level: Any, origin: Any = None, size: float = 100.0,
               text_height: float | None = None, below: bool = False,
               layer: str | None = None, color: Any = None) -> list[Op]:
    """A spot level: a triangle on the point, with the level beside it.

    origin = the point the level is taken at. ``below`` puts the triangle and
    the text under the point instead of over it, for a soffit or an invert.
    """
    s = _positive(size, "size")
    at = _point(origin)
    height = float(text_height) if text_height else s * 0.5
    side = -1.0 if below else 1.0
    tip = at
    base = s * 0.5
    pts = [tip, (at[0] - base, at[1] + side * s), (at[0] + base, at[1] + side * s)]
    ops = [poly(pts, closed=True, layer=layer, color=color)]
    bar = (at[0] - base * 2.2, at[1] + side * s), (at[0] + base * 2.2, at[1] + side * s)
    ops.append(line(bar[0], bar[1], layer=layer, color=color))
    ops.append(
        text((at[0], at[1] + side * (s + height * 0.9)), level, height,
             layer=layer, color=color)
    )
    return ops


def revision_tag(number: Any, origin: Any = None, size: float = 100.0,
                 text_height: float | None = None, layer: str | None = None,
                 color: Any = None) -> list[Op]:
    """The triangle with a revision number in it. origin = the centre."""
    s = _positive(size, "size")
    centre = _point(origin)
    height = float(text_height) if text_height else s * 0.55
    pts = [on_circle((0.0, 0.0), s / 2.0, 90.0 + 120.0 * i) for i in range(3)]
    ops = [poly(shift(pts, centre), closed=True, layer=layer, color=color)]
    # The centroid of a triangle sits a third of the way up, so the number goes
    # there rather than at the circle's centre, or it looks high.
    ops.append(text((centre[0], centre[1] - s * 0.06), number, height,
                    layer=layer, color=color))
    return ops


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

SHAPES: dict[str, Callable[..., list[Op]]] = {
    "polygon": polygon,
    "hexagon": hexagon,
    "star": star,
    "slot": slot,
    "rounded_rectangle": rounded_rectangle,
    "spiral": spiral,
    "bolt_circle": bolt_circle,
    "flange": flange,
    "elbow": elbow,
    "duct_transition": duct_transition,
    "stair": stair,
    "ladder": ladder,
    "grating": grating,
    "truss": truss,
    "zigzag": zigzag,
    "steel_section": steel_section,
    "cone_development": cone_development,
    "gear": gear,
    "detail_bubble": detail_bubble,
    "section_mark": section_mark,
    "north_arrow": north_arrow,
    "scale_bar": scale_bar,
    "level_mark": level_mark,
    "revision_tag": revision_tag,
}

# What each shape must be told, for an error that names the gap instead of
# letting Python's TypeError through.
REQUIRED: dict[str, tuple[str, ...]] = {
    "polygon": ("sides", "radius"),
    "hexagon": (),
    "star": ("points", "outer_radius"),
    "slot": ("length", "width"),
    "rounded_rectangle": ("width", "height", "radius"),
    "spiral": ("turns", "start_radius", "end_radius"),
    "bolt_circle": ("count", "pitch_diameter", "hole_diameter"),
    "flange": ("outer_diameter", "bolt_count", "pitch_diameter", "hole_diameter"),
    "elbow": ("centreline_radius", "angle", "width"),
    "duct_transition": ("width_in", "width_out", "length"),
    "stair": ("risers", "rise", "going", "width"),
    "ladder": ("height", "width"),
    "grating": ("width", "height", "spacing"),
    "truss": ("span", "depth", "panels"),
    "zigzag": ("length", "amplitude", "cycles"),
    "steel_section": ("profile", "depth", "width"),
    "cone_development": ("bottom_diameter", "top_diameter", "height"),
    "gear": ("teeth", "pitch_diameter"),
    "detail_bubble": ("number", "radius"),
    "section_mark": ("length",),
    "north_arrow": ("size",),
    "scale_bar": ("scale", "length"),
    "level_mark": ("level",),
    "revision_tag": ("number",),
}


def build(kind: str, params: dict[str, Any]) -> list[Op]:
    """The operations for one named shape.

    Raises ValueError naming the shape and the missing or unknown settings, so
    a bad request is answered rather than becoming a Python traceback.
    """
    name = str(kind).strip().lower().replace("-", "_").replace(" ", "_")
    if name not in SHAPES:
        raise ValueError(
            f"'{kind}' is not a shape this server knows. Shapes: {', '.join(sorted(SHAPES))}. "
            "3D shapes, made as solids: duct_run, pipe_spool"
        )
    maker = SHAPES[name]
    given = {k: v for k, v in (params or {}).items() if v is not None}
    missing = [p for p in REQUIRED[name] if p not in given]
    if missing:
        raise ValueError(f"'{name}' needs {', '.join(missing)}")
    allowed = set(maker.__code__.co_varnames[: maker.__code__.co_argcount])
    unknown = sorted(set(given) - allowed)
    if unknown:
        raise ValueError(
            f"'{name}' does not take {', '.join(unknown)}. It takes: "
            + ", ".join(sorted(allowed))
        )
    return maker(**given)


def settings_of(kind: str) -> dict[str, Any]:
    """What one shape takes: its required settings and its optional ones with defaults."""
    name = str(kind).strip().lower()
    maker = SHAPES[name]
    code = maker.__code__
    names = list(code.co_varnames[: code.co_argcount])
    defaults = list(maker.__defaults__ or ())
    optional = dict(zip(names[len(names) - len(defaults):], defaults, strict=False))
    return {
        "shape": name,
        "required": list(REQUIRED[name]),
        "optional": {k: v for k, v in optional.items() if k not in REQUIRED[name]},
        "about": (maker.__doc__ or "").strip().splitlines()[0],
    }
