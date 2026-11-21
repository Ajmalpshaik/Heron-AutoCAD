"""3D shapes from a route: a duct run with its bends, a pipe spool with its elbows and flanges.

"A 600 x 400 duct from here, up 3 m, then across." "A 4 inch spool: flange,
two elbows, flange." Each is a run of solids that has to meet end to end, with
every bend tangent to the straights either side of it. That is a page of 3D
construction by hand, and one call here (D-94).

The 2D library (``shapes.py``) generates batch operations. A solid cannot be
sent that way, so a 3D shape is a list of **pieces** instead. Each piece is a
straight, a bend or a flange described in its **own frame**, where AutoCAD
makes it without any doubt: the profile flat in the XY plane at the origin,
the piece running up +Z (a bend turns towards +X, round an axis through
(radius, 0, 0) along +Y). One 4 x 4 matrix then puts it in place. Everything
here is pure, so where every piece lands, that each one meets the next, and
that each bend leaves in the direction the next straight runs, is tested
without AutoCAD.

Units are the drawing's own, angles out are degrees. The route is the
centreline through the corner points, as a services drawing gives it; each
corner gets a bend of ``bend_radius`` on its centreline, so the straights are
shorter than the legs between corners by the bends' tangent lengths.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

Vec = tuple[float, float, float]
Piece = dict[str, Any]

EPS = 1e-9
# A corner turning less than this is a straight run, not a bend.
STRAIGHT_THROUGH_DEGREES = 1e-6
# A corner turning more than this doubles back on itself.
MOST_TURN_DEGREES = 179.0
MOST_POINTS = 100
MOST_BOLTS = 64
# Steps round a circle and along a bend, for the box a piece is expected to fill.
CIRCLE_SAMPLES = 72
BEND_SAMPLES = 24

FLANGE_ENDS = ("both", "start", "end", "none")
DUCT_PROFILES = ("rectangular", "round")


# ---------------------------------------------------------------------------
# Vectors
# ---------------------------------------------------------------------------


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vec) -> Vec:
    length = norm(a)
    if length < EPS:
        raise ValueError("a direction of zero length has no way to point")
    return scale(a, 1.0 / length)


def rotate(v: Vec, axis: Vec, radians: float) -> Vec:
    """``v`` turned about a unit ``axis`` by the right-hand rule (Rodrigues)."""
    cos, sin = math.cos(radians), math.sin(radians)
    return add(add(scale(v, cos), scale(cross(axis, v), sin)), scale(axis, dot(axis, v) * (1.0 - cos)))


def _point(value: Any, name: str) -> Vec:
    try:
        numbers = [float(v) for v in value]
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be [x, y, z], got {value!r}") from None
    if len(numbers) == 2:
        numbers.append(0.0)
    if len(numbers) != 3 or not all(math.isfinite(v) for v in numbers):
        raise ValueError(f"{name} must be [x, y, z], got {value!r}")
    return (numbers[0], numbers[1], numbers[2])


def _positive(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {value!r}") from None
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be above zero, got {value!r}")
    return number


def _r(value: float) -> float:
    return round(float(value), 9)


def _rv(v: Vec) -> list[float]:
    return [_r(v[0]), _r(v[1]), _r(v[2])]


# ---------------------------------------------------------------------------
# Frames and matrices
# ---------------------------------------------------------------------------


def matrix(x: Vec, y: Vec, z: Vec, origin: Vec) -> list[list[float]]:
    """The 4 x 4 matrix taking a piece's own frame to the world.

    Columns are the piece's X, Y and Z axes in world terms, the last column is
    where its origin lands: AutoCAD's TransformBy layout (translation in the
    fourth column, rows of the first index).
    """
    # The axes to 12 places: over a 10 m straight that is a hair, where 9 would be a micron.
    def a(v: float) -> float:
        return round(float(v), 12)

    return [
        [a(x[0]), a(y[0]), a(z[0]), _r(origin[0])],
        [a(x[1]), a(y[1]), a(z[1]), _r(origin[1])],
        [a(x[2]), a(y[2]), a(z[2]), _r(origin[2])],
        [0.0, 0.0, 0.0, 1.0],
    ]


def apply(m: Sequence[Sequence[float]], p: Vec) -> Vec:
    """A point in a piece's own frame, in the world."""
    return (
        m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3],
        m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3],
        m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3],
    )


def _perpendicular(t: Vec, up: Vec) -> tuple[Vec, Vec]:
    """(width, height) square to ``t``: height as near ``up`` as it can be, width = height x t."""
    h = sub(up, scale(t, dot(up, t)))
    if norm(h) < 1e-6:
        # Running along "up" itself (a riser): the height faces north, +Y.
        fallback = (0.0, 1.0, 0.0) if abs(t[1]) < 0.9 else (1.0, 0.0, 0.0)
        h = sub(fallback, scale(t, dot(fallback, t)))
    h = unit(h)
    return cross(h, t), h


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


def route(points: Any) -> list[Vec]:
    """The corner points, cleaned: repeats dropped, points on a straight line dropped."""
    if not isinstance(points, (list, tuple)):
        raise ValueError("points must be a list of [x, y, z] corner points along the centreline")
    pts = [_point(p, f"points[{i}]") for i, p in enumerate(points)]
    if len(pts) > MOST_POINTS:
        raise ValueError(f"a run takes at most {MOST_POINTS} points, got {len(pts)}; split it in two")
    clean: list[Vec] = []
    for p in pts:
        if not clean or norm(sub(p, clean[-1])) > EPS:
            clean.append(p)
    if len(clean) < 2:
        raise ValueError("a run needs at least two different points")
    kept = [clean[0]]
    for i in range(1, len(clean) - 1):
        before = unit(sub(clean[i], kept[-1]))
        after = unit(sub(clean[i + 1], clean[i]))
        if math.degrees(math.acos(max(-1.0, min(1.0, dot(before, after))))) > STRAIGHT_THROUGH_DEGREES:
            kept.append(clean[i])
    kept.append(clean[-1])
    return kept


def _turn(before: Vec, after: Vec) -> float:
    """The angle a corner turns through, in radians: 0 is straight on."""
    return math.acos(max(-1.0, min(1.0, dot(before, after))))


def legs(points: Sequence[Vec]) -> list[dict[str, Any]]:
    """For each corner: the turn and the directions in and out. Pure, for the shapes below."""
    corners = []
    for i in range(1, len(points) - 1):
        t1 = unit(sub(points[i], points[i - 1]))
        t2 = unit(sub(points[i + 1], points[i]))
        theta = _turn(t1, t2)
        if math.degrees(theta) > MOST_TURN_DEGREES:
            raise ValueError(
                f"the run doubles back on itself at point {i} ({math.degrees(theta):.1f} degrees); "
                "a bend can turn at most 179 degrees. Add a point to take it round in two bends"
            )
        corners.append({"index": i, "corner": points[i], "in": t1, "out": t2, "theta": theta})
    return corners


def _layout(
    points: Sequence[Vec],
    radius_at: Callable[[dict[str, Any], Vec, Vec], float],
    up: Vec,
    start_trim: float = 0.0,
    end_trim: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Vec], dict[str, Vec]]:
    """The run as straights and bends, with the width / height frame carried round each bend.

    ``radius_at(corner, width, height)`` gives each bend's centreline radius
    from the frame arriving at it. ``start_trim`` / ``end_trim`` keep that much
    of the first and last leg clear (a flange's thickness). Also returns the
    frame at the start and at the end of the run, for the flanges.
    """
    corners = legs(points)
    first = unit(sub(points[1], points[0]))
    width, height = _perpendicular(first, up)
    start_frame = {"direction": first, "width": width, "height": height}
    # The frame arriving at each corner, then each bend's radius and tangent length.
    for corner in corners:
        corner["width"], corner["height"] = width, height
        corner["radius"] = radius_at(corner, width, height)
        corner["tangent"] = corner["radius"] * math.tan(corner["theta"] / 2.0)
        if corner["theta"] > EPS:
            axis = unit(cross(corner["in"], corner["out"]))
            width, height = rotate(width, axis, corner["theta"]), rotate(height, axis, corner["theta"])
    end_frame = {"direction": unit(sub(points[-1], points[-2])), "width": width, "height": height}
    # Every leg must hold the bends at both its ends, and a flange on an end leg.
    count = len(points) - 1
    for leg in range(count):
        length = norm(sub(points[leg + 1], points[leg]))
        parts = []
        if leg == 0 and start_trim > 0:
            parts.append(("the flange", start_trim))
        if leg > 0:
            parts.append((f"the bend at point {leg}", corners[leg - 1]["tangent"]))
        if leg < count - 1:
            parts.append((f"the bend at point {leg + 1}", corners[leg]["tangent"]))
        if leg == count - 1 and end_trim > 0:
            parts.append(("the flange" if not start_trim or count > 1 else "the other flange", end_trim))
        used = sum(size for _, size in parts)
        if used > length + 1e-7:
            listed = ", ".join(f"{name} {size:g}" for name, size in parts)
            raise ValueError(
                f"the leg from point {leg} to point {leg + 1} is {length:g} long, but {listed} need "
                f"{used:g} of it (a bend takes radius x tan(angle / 2) each side of its corner). "
                "Make the bend radius smaller or the leg longer"
            )
    segments: list[dict[str, Any]] = []
    cursor = add(points[0], scale(first, start_trim)) if start_trim > 0 else points[0]
    for corner in corners:
        t1, t2, theta, radius = corner["in"], corner["out"], corner["theta"], corner["radius"]
        a = sub(corner["corner"], scale(t1, corner["tangent"]))
        b = add(corner["corner"], scale(t2, corner["tangent"]))
        segments.append({"kind": "straight", "start": cursor, "end": a, "direction": t1,
                         "width": corner["width"], "height": corner["height"]})
        u = unit(sub(t2, scale(t1, dot(t2, t1))))
        axis = unit(cross(t1, t2))
        segments.append({"kind": "bend", "start": a, "end": b, "direction": t1, "end_direction": t2,
                         "towards_centre": u, "axis": axis, "radius": radius, "theta": theta,
                         "centre": add(a, scale(u, radius)), "corner": corner["corner"],
                         "width": corner["width"], "height": corner["height"]})
        cursor = b
    end = sub(points[-1], scale(end_frame["direction"], end_trim)) if end_trim > 0 else points[-1]
    segments.append({"kind": "straight", "start": cursor, "end": end, "direction": end_frame["direction"],
                     "width": width, "height": height})
    # A straight with no length (two bends back to back, or a flange the leg
    # just fits) is no piece at all.
    kept = [s for s in segments if s["kind"] == "bend" or norm(sub(s["end"], s["start"])) > 1e-7]
    return kept, start_frame, end_frame


# ---------------------------------------------------------------------------
# Profiles and pieces
# ---------------------------------------------------------------------------


def _rectangle(width: float, height: float) -> dict[str, Any]:
    return {"kind": "rectangle", "width": _r(width), "height": _r(height)}


def _circle(radius: float) -> dict[str, Any]:
    return {"kind": "circle", "radius": _r(radius)}


def profile_outline(profile: dict[str, Any], samples: int = CIRCLE_SAMPLES) -> list[tuple[float, float]]:
    """The profile's outline in its own XY plane, for the expected box."""
    if profile["kind"] == "circle":
        r = profile["radius"]
        return [(r * math.cos(2 * math.pi * k / samples), r * math.sin(2 * math.pi * k / samples)) for k in range(samples)]
    if profile["kind"] == "corners":
        return [(float(x), float(y)) for x, y in profile["corners"]]
    w, h = profile["width"] / 2.0, profile["height"] / 2.0
    return [(-w, -h), (w, -h), (w, h), (-w, h)]


def _bend_profile(kind: str, size: dict[str, float], seg: dict[str, Any], shrink: float = 0.0) -> dict[str, Any]:
    """A bend's profile in the bend's own frame (X towards the centre, Y the bend's axis).

    A round one is the circle. A rectangle is turned to where the duct's
    width and height face as it arrives, so the bend carries the duct round
    without twisting it.
    """
    if kind == "round":
        return _circle(size["radius"] - shrink)
    u, axis = seg["towards_centre"], seg["axis"]
    w, h = size["width"] / 2.0 - shrink, size["height"] / 2.0 - shrink
    wl = (dot(seg["width"], u), dot(seg["width"], axis))
    hl = (dot(seg["height"], u), dot(seg["height"], axis))
    corners = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        corners.append([_r(sx * w * wl[0] + sy * h * hl[0]), _r(sx * w * wl[1] + sy * h * hl[1])])
    return {"kind": "corners", "corners": corners}


def _in_plane_size(kind: str, size: dict[str, float], seg_width: Vec, seg_height: Vec, towards: Vec) -> float:
    """How deep the duct is in the plane it bends in (the size that sits across the bend)."""
    if kind == "round":
        return 2.0 * size["radius"]
    return abs(dot(towards, seg_width)) * size["width"] + abs(dot(towards, seg_height)) * size["height"]


def _straight_piece(seg: dict[str, Any], kind: str, size: dict[str, float], part: str,
                    wall: float | None) -> Piece:
    length = norm(sub(seg["end"], seg["start"]))
    profile = _circle(size["radius"]) if kind == "round" else _rectangle(size["width"], size["height"])
    piece: Piece = {
        "part": part,
        "solid": "cylinder" if kind == "round" else "box",
        "profile": profile,
        "length": _r(length),
        "start": _rv(seg["start"]),
        "end": _rv(seg["end"]),
        "direction": _rv(seg["direction"]),
        "matrix": matrix(seg["width"], seg["height"], seg["direction"], seg["start"]),
    }
    if wall:
        piece["hole"] = (_circle(size["radius"] - wall) if kind == "round"
                         else _rectangle(size["width"] - 2 * wall, size["height"] - 2 * wall))
    return piece


def _bend_piece(seg: dict[str, Any], kind: str, size: dict[str, float], part: str,
                wall: float | None) -> Piece:
    u, axis, t1 = seg["towards_centre"], seg["axis"], seg["direction"]
    piece: Piece = {
        "part": part,
        "solid": "revolve",
        "profile": _bend_profile(kind, size, seg),
        "radius": _r(seg["radius"]),
        "angle": _r(math.degrees(seg["theta"])),
        "length": _r(seg["radius"] * seg["theta"]),
        "start": _rv(seg["start"]),
        "end": _rv(seg["end"]),
        "corner": _rv(seg["corner"]),
        "centre": _rv(seg["centre"]),
        "direction": _rv(t1),
        "end_direction": _rv(seg["end_direction"]),
        # Own frame: X towards the bend's centre, Y its axis, Z the way in.
        "matrix": matrix(u, axis, t1, seg["start"]),
    }
    if wall:
        piece["hole"] = _bend_profile(kind, size, seg, shrink=wall)
    return piece


def bend_end(piece: Piece) -> Vec:
    """Where a bend ends, in its own frame: (R - R cos a, 0, R sin a)."""
    r, a = piece["radius"], math.radians(piece["angle"])
    return (r - r * math.cos(a), 0.0, r * math.sin(a))


def piece_end(piece: Piece) -> Vec:
    """Where a piece ends in the world, worked out from its own frame and matrix."""
    if piece["solid"] == "revolve":
        local = bend_end(piece)
    else:
        local = (0.0, 0.0, piece["length"])
    return apply(piece["matrix"], local)


def expected_box(piece: Piece) -> tuple[list[float], list[float]]:
    """The world box a piece should fill, from points on its outline, to check AutoCAD's against."""
    outline = profile_outline(piece["profile"])
    local: list[Vec] = []
    if piece["solid"] == "revolve":
        r, a = piece["radius"], math.radians(piece["angle"])
        steps = max(2, int(math.ceil(BEND_SAMPLES * a / (math.pi / 2))))
        for k in range(steps + 1):
            angle = a * k / steps
            for x, y in outline:
                # Turn the profile point about the axis through (r, 0, 0) along +Y.
                dx = x - r
                local.append((r + dx * math.cos(angle), y, -dx * math.sin(angle)))
    else:
        for z in (0.0, piece["length"]):
            local.extend((x, y, z) for x, y in outline)
    world = [apply(piece["matrix"], p) for p in local]
    low = [min(p[i] for p in world) for i in range(3)]
    high = [max(p[i] for p in world) for i in range(3)]
    return [_r(v) for v in low], [_r(v) for v in high]


def _flange_piece(at: Vec, direction: Vec, width: Vec, height: Vec, diameter: float,
                  thickness: float, bore: float | None, bolts: dict[str, float] | None, end: str) -> Piece:
    piece: Piece = {
        "part": "flange",
        "end": end,
        "solid": "cylinder",
        "profile": _circle(diameter / 2.0),
        "length": _r(thickness),
        "start": _rv(at),
        "direction": _rv(direction),
        "matrix": matrix(width, height, direction, at),
    }
    piece["end_point"] = _rv(add(at, scale(direction, thickness)))
    if bore:
        piece["hole"] = _circle(bore / 2.0)
    if bolts:
        count, pcd = int(bolts["count"]), bolts["pitch_diameter"]
        # The holes straddle the centrelines, as a flange is drilled.
        piece["bolt_holes"] = [
            {"x": _r(pcd / 2.0 * math.cos(math.pi * (2 * k + 1) / count)),
             "y": _r(pcd / 2.0 * math.sin(math.pi * (2 * k + 1) / count)),
             "radius": _r(bolts["hole_diameter"] / 2.0)}
            for k in range(count)
        ]
    return piece


def _summary(shape: str, points: Sequence[Vec], pieces: list[Piece], extra: dict[str, Any]) -> dict[str, Any]:
    run = [p for p in pieces if p["part"] != "flange"]
    out: dict[str, Any] = {
        "shape": shape,
        "points": [_rv(p) for p in points],
        "pieces": pieces,
        "piece_count": len(pieces),
        "centreline_length": _r(sum(p["length"] for p in run)
                                + sum(p["length"] for p in pieces if p["part"] == "flange")),
        "bends": [{"at": p["corner"], "angle": p["angle"], "radius": p["radius"]}
                  for p in pieces if p["solid"] == "revolve"],
    }
    out.update(extra)
    return out


# ---------------------------------------------------------------------------
# The shapes
# ---------------------------------------------------------------------------


def duct_run(points: Any, profile: str = "rectangular", width: float | None = None,
             height: float | None = None, diameter: float | None = None,
             bend_radius: float | None = None, wall: float | None = None,
             up: Any = None, join: bool = False, layer: str | None = None,
             color: Any = None, centreline_layer: str | None = None) -> dict[str, Any]:
    """A duct run as solids: a straight per leg and a bend at each corner.

    points = the duct's centreline through its corners. Rectangular needs
    width (across, horizontal on a level run) and height; round needs
    diameter. bend_radius is on the centreline: by default 1.0 x the duct's
    size in the plane it bends in for a rectangular duct (R/W = 1), 1.5 x the
    diameter for a round one. A rectangular duct keeps its width level on
    the first leg (``up`` turns it) and is carried round every bend without
    twisting. wall makes it hollow; without it the solid is the duct's outside.
    """
    kind = str(profile).strip().lower()
    if kind not in DUCT_PROFILES:
        raise ValueError(f"profile must be 'rectangular' or 'round', got {profile!r}")
    if kind == "round":
        if diameter is None:
            raise ValueError("a round duct needs diameter")
        if width is not None or height is not None:
            raise ValueError("a round duct takes diameter, not width and height")
        size = {"radius": _positive(diameter, "diameter") / 2.0}
        smallest = 2.0 * size["radius"]
    else:
        if width is None or height is None:
            raise ValueError("a rectangular duct needs width and height (give profile='round' and diameter for a round one)")
        if diameter is not None:
            raise ValueError("a rectangular duct takes width and height, not diameter")
        size = {"width": _positive(width, "width"), "height": _positive(height, "height")}
        smallest = min(size["width"], size["height"])
    thickness = None
    if wall is not None:
        thickness = _positive(wall, "wall")
        if 2 * thickness >= smallest:
            raise ValueError(f"a wall of {thickness:g} closes the duct up (its smallest size is {smallest:g})")
    radius_given = None if bend_radius is None else _positive(bend_radius, "bend_radius")
    up_vec = unit(_point(up, "up")) if up is not None else (0.0, 0.0, 1.0)
    pts = route(points)

    def radius_at(corner: dict[str, Any], w: Vec, h: Vec) -> float:
        towards = unit(sub(corner["out"], scale(corner["in"], dot(corner["out"], corner["in"]))))
        across = _in_plane_size(kind, size, w, h, towards)
        r = radius_given if radius_given is not None else (1.5 * across if kind == "round" else across)
        if r - across / 2.0 <= 1e-9:
            raise ValueError(
                f"a bend radius of {r:g} at point {corner['index']} leaves no inside to the bend: "
                f"the duct is {across:g} across it, so the centreline radius must be over {across / 2.0:g}"
            )
        return r

    segments, _, _ = _layout(pts, radius_at, up_vec)
    pieces = [(_straight_piece(s, kind, size, "straight", thickness) if s["kind"] == "straight"
               else _bend_piece(s, kind, size, "bend", thickness)) for s in segments]
    for i, piece in enumerate(pieces):
        piece["index"] = i
    extra: dict[str, Any] = {"profile": kind, "join": bool(join)}
    extra.update({"diameter": _r(2 * size["radius"])} if kind == "round"
                 else {"width": _r(size["width"]), "height": _r(size["height"])})
    if thickness:
        extra["wall"] = _r(thickness)
    plan = _summary("duct_run", pts, pieces, extra)
    plan["style"] = {"layer": layer, "color": color, "centreline_layer": centreline_layer}
    return plan


def pipe_spool(points: Any, outside_diameter: float, flange_diameter: float | None = None,
               flange_thickness: float | None = None, wall: float | None = None,
               bend_radius: float | None = None, flanges: str = "both",
               bolt_count: int | None = None, pitch_diameter: float | None = None,
               hole_diameter: float | None = None, join: bool = False,
               layer: str | None = None, color: Any = None,
               centreline_layer: str | None = None) -> dict[str, Any]:
    """A pipe spool as solids: pipe lengths, an elbow at each corner, flanges on the ends.

    points = the pipe's centreline through its corners, end face to end
    face: a flange's face sits on the end point. bend_radius is the elbow's
    centreline radius, 1.5 x the outside diameter by default (a long-radius
    elbow is 1.5 x the NOMINAL size, a little less: give it from the fitting
    catalogue when it matters). wall makes the pipe hollow and bores the
    flanges to match. bolt_count, pitch_diameter and hole_diameter drill the
    flanges, holes straddling the centrelines. The answer lists each pipe's
    cut length.
    """
    od = _positive(outside_diameter, "outside_diameter")
    ends = str(flanges).strip().lower()
    if ends not in FLANGE_ENDS:
        raise ValueError(f"flanges must be one of {', '.join(FLANGE_ENDS)}, got {flanges!r}")
    bore = None
    if wall is not None:
        thickness = _positive(wall, "wall")
        if 2 * thickness >= od:
            raise ValueError(f"a wall of {thickness:g} closes the pipe up (outside diameter {od:g})")
        bore = od - 2 * thickness
    else:
        thickness = None
    fd = ft = None
    bolts = None
    if ends != "none":
        if flange_diameter is None or flange_thickness is None:
            raise ValueError(
                "flanges need flange_diameter and flange_thickness (from the flange table), "
                "or flanges='none' for plain ends"
            )
        fd = _positive(flange_diameter, "flange_diameter")
        ft = _positive(flange_thickness, "flange_thickness")
        if fd <= od:
            raise ValueError(f"the flange ({fd:g}) must be bigger than the pipe ({od:g})")
        drilled = [v is not None for v in (bolt_count, pitch_diameter, hole_diameter)]
        if any(drilled) and not all(drilled):
            raise ValueError("bolt holes need all three: bolt_count, pitch_diameter and hole_diameter")
        if all(drilled):
            count = int(bolt_count)  # type: ignore[arg-type]
            if count < 1 or count > MOST_BOLTS or count != float(bolt_count):  # type: ignore[arg-type]
                raise ValueError(f"bolt_count must be a whole number from 1 to {MOST_BOLTS}, got {bolt_count!r}")
            pcd = _positive(pitch_diameter, "pitch_diameter")
            hole = _positive(hole_diameter, "hole_diameter")
            if pcd - hole <= od or pcd + hole >= fd:
                raise ValueError(
                    f"the bolt holes ({hole:g} on a {pcd:g} pitch circle) must sit between the pipe "
                    f"({od:g}) and the flange's edge ({fd:g})"
                )
            bolts = {"count": count, "pitch_diameter": pcd, "hole_diameter": hole}
    elif any(v is not None for v in (flange_diameter, flange_thickness, bolt_count, pitch_diameter, hole_diameter)):
        raise ValueError("flanges='none' takes no flange sizes: leave them out, or say which ends have flanges")
    radius_given = None if bend_radius is None else _positive(bend_radius, "bend_radius")
    elbow_radius = radius_given if radius_given is not None else 1.5 * od
    if elbow_radius - od / 2.0 <= 1e-9:
        raise ValueError(
            f"an elbow radius of {elbow_radius:g} leaves no inside to the elbow: the centreline "
            f"radius must be over half the outside diameter ({od / 2.0:g})"
        )
    pts = route(points)
    start_trim = ft if ends in ("both", "start") else 0.0
    end_trim = ft if ends in ("both", "end") else 0.0
    size = {"radius": od / 2.0}
    segments, first, last = _layout(pts, lambda corner, w, h: elbow_radius, (0.0, 0.0, 1.0),
                                    start_trim=start_trim or 0.0, end_trim=end_trim or 0.0)
    pieces: list[Piece] = []
    if start_trim:
        pieces.append(_flange_piece(pts[0], first["direction"], first["width"], first["height"],
                                    fd, ft, bore, bolts, "start"))  # type: ignore[arg-type]
    for seg in segments:
        pieces.append(_straight_piece(seg, "round", size, "pipe", thickness) if seg["kind"] == "straight"
                      else _bend_piece(seg, "round", size, "elbow", thickness))
    if end_trim:
        at = sub(pts[-1], scale(last["direction"], ft))  # type: ignore[arg-type]
        pieces.append(_flange_piece(at, last["direction"], last["width"], last["height"],
                                    fd, ft, bore, bolts, "end"))  # type: ignore[arg-type]
    for i, piece in enumerate(pieces):
        piece["index"] = i
    cut_list = [{"index": p["index"], "cut_length": p["length"]} for p in pieces if p["part"] == "pipe"]
    extra: dict[str, Any] = {
        "outside_diameter": _r(od),
        "elbow_radius": _r(elbow_radius),
        "flanges": ends,
        "pipe_cut_lengths": cut_list,
        "pipe_total": _r(sum(c["cut_length"] for c in cut_list)),
        "elbows": sum(1 for p in pieces if p["part"] == "elbow"),
        "join": bool(join),
    }
    if thickness:
        extra["wall"] = _r(thickness)
    if fd:
        extra["flange_diameter"] = _r(fd)
        extra["flange_thickness"] = _r(ft)  # type: ignore[arg-type]
    plan = _summary("pipe_spool", pts, pieces, extra)
    plan["style"] = {"layer": layer, "color": color, "centreline_layer": centreline_layer}
    return plan


SHAPES_3D: dict[str, Callable[..., dict[str, Any]]] = {
    "duct_run": duct_run,
    "pipe_spool": pipe_spool,
}

REQUIRED_3D: dict[str, tuple[str, ...]] = {
    "duct_run": ("points",),
    "pipe_spool": ("points", "outside_diameter"),
}


def is_3d(kind: str) -> bool:
    return str(kind).strip().lower().replace("-", "_").replace(" ", "_") in SHAPES_3D


def build_3d(kind: str, params: dict[str, Any]) -> dict[str, Any]:
    """The pieces for one named 3D shape, or ValueError naming what is wrong."""
    name = str(kind).strip().lower().replace("-", "_").replace(" ", "_")
    if name not in SHAPES_3D:
        raise ValueError(f"'{kind}' is not a 3D shape. 3D shapes: {', '.join(sorted(SHAPES_3D))}")
    maker = SHAPES_3D[name]
    given = {k: v for k, v in (params or {}).items() if v is not None}
    missing = [p for p in REQUIRED_3D[name] if p not in given]
    if missing:
        raise ValueError(f"'{name}' needs {', '.join(missing)}")
    allowed = set(maker.__code__.co_varnames[: maker.__code__.co_argcount])
    unknown = sorted(set(given) - allowed)
    if unknown:
        raise ValueError(f"'{name}' does not take {', '.join(unknown)}. It takes: " + ", ".join(sorted(allowed)))
    return maker(**given)
