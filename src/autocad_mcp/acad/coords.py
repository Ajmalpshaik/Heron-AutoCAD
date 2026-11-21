"""The current UCS, and points moved between it and the world.

Every coordinate AutoCAD's Automation API takes or returns is in the **World**
Coordinate System. The modeller does not work there. They set a UCS: rotated
onto a wall, moved to a grid intersection, tilted onto a sloping roof. A point
read off that screen, or typed from a dimension on a rotated plan, is not the
point COM wants — the same numbers land somewhere else entirely.

So this module holds the transform AutoLISP's ``trans`` does, built from the
three system variables AutoCAD exposes for the current UCS:

* ``UCSORG`` - the origin, in world coordinates;
* ``UCSXDIR`` - the UCS X axis, as a world vector;
* ``UCSYDIR`` - the UCS Y axis, as a world vector.

All three are read-only and saved with the drawing, so a UCS the modeller set
by hand an hour ago is still readable. There is no AutoCAD in this file, so
all of it is tested without AutoCAD.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

Vec3 = tuple[float, float, float]
EPS = 1e-9

# How far off axis the UCS has to be before it is worth telling the agent.
# 1e-6 degrees is rounding; a tenth of a degree is a rotated UCS.
ANGLE_TOLERANCE = 1e-6
LENGTH_TOLERANCE = 1e-9


def as_vec3(value: Sequence[float] | None, default: Vec3 = (0.0, 0.0, 0.0)) -> Vec3:
    """A COM point, list or tuple as three floats; short input is padded with zeros."""
    if value is None:
        return default
    try:
        numbers = [float(v) for v in value]
    except (TypeError, ValueError):
        return default
    if not numbers:
        return default
    numbers = (numbers + [0.0, 0.0, 0.0])[:3]
    return (numbers[0], numbers[1], numbers[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _length(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: Vec3) -> Vec3:
    size = _length(a)
    if size < LENGTH_TOLERANCE:
        raise ValueError("a direction of zero length cannot define an axis")
    return (a[0] / size, a[1] / size, a[2] / size)


def _minus(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


@dataclass(frozen=True)
class Ucs:
    """One coordinate system: where it starts and which way its axes point.

    Built straight from UCSORG / UCSXDIR / UCSYDIR. The axes are made
    orthonormal on the way in, so a frame that comes back from AutoCAD very
    slightly off square still round-trips a point exactly.
    """

    origin: Vec3 = (0.0, 0.0, 0.0)
    x_axis: Vec3 = (1.0, 0.0, 0.0)
    y_axis: Vec3 = (0.0, 1.0, 0.0)

    @classmethod
    def build(
        cls,
        origin: Sequence[float] | None = None,
        x_axis: Sequence[float] | None = None,
        y_axis: Sequence[float] | None = None,
    ) -> Ucs:
        """A UCS from whatever AutoCAD gave back, squared up and normalized.

        X is taken as given; Y is swung onto the plane X and Y span, so the
        frame is always a right-handed orthonormal one even when the two
        vectors read back a fraction out of square.
        """
        o = as_vec3(origin, (0.0, 0.0, 0.0))
        x = _unit(as_vec3(x_axis, (1.0, 0.0, 0.0)))
        y_raw = as_vec3(y_axis, (0.0, 1.0, 0.0))
        z = _cross(x, y_raw)
        if _length(z) < LENGTH_TOLERANCE:
            raise ValueError("the UCS X and Y directions are parallel, so they define no plane")
        y = _unit(_cross(_unit(z), x))
        return cls(o, x, y)

    @classmethod
    def from_rotation(
        cls, origin: Sequence[float] | None = None, degrees: float = 0.0
    ) -> Ucs:
        """A plan UCS: moved to an origin and turned by an angle about world Z."""
        angle = math.radians(float(degrees))
        cos, sin = math.cos(angle), math.sin(angle)
        return cls.build(origin, (cos, sin, 0.0), (-sin, cos, 0.0))

    @classmethod
    def from_three_points(
        cls,
        origin: Sequence[float],
        on_x: Sequence[float],
        on_y: Sequence[float],
    ) -> Ucs:
        """A UCS the way the UCS command's 3-point option builds one."""
        o = as_vec3(origin)
        return cls.build(o, _minus(as_vec3(on_x), o), _minus(as_vec3(on_y), o))

    # ---- the transform ----------------------------------------------------

    @property
    def z_axis(self) -> Vec3:
        """The UCS Z axis: X crossed with Y, so the frame stays right-handed."""
        return _cross(self.x_axis, self.y_axis)

    def to_world(self, point: Sequence[float]) -> Vec3:
        """A point given in this UCS, as the world point COM wants."""
        x, y, z = as_vec3(point)
        ox, oy, oz = self.origin
        ax, ay, az = self.x_axis
        bx, by, bz = self.y_axis
        cx, cy, cz = self.z_axis
        return (
            ox + x * ax + y * bx + z * cx,
            oy + x * ay + y * by + z * cy,
            oz + x * az + y * bz + z * cz,
        )

    def to_ucs(self, point: Sequence[float]) -> Vec3:
        """A world point, as the numbers the modeller sees in this UCS."""
        d = _minus(as_vec3(point), self.origin)
        return (_dot(d, self.x_axis), _dot(d, self.y_axis), _dot(d, self.z_axis))

    def direction_to_world(self, point: Sequence[float]) -> Vec3:
        """A direction (not a position) in this UCS, as a world direction."""
        x, y, z = as_vec3(point)
        ax, ay, az = self.x_axis
        bx, by, bz = self.y_axis
        cx, cy, cz = self.z_axis
        return (
            x * ax + y * bx + z * cx,
            x * ay + y * by + z * cy,
            x * az + y * bz + z * cz,
        )

    # ---- angles, turns and arcs on the plane (D-96) -----------------------
    #
    # A flipped UCS (its Z pointing down) is a mirror of the world on the XY
    # plane, so anticlockwise in it is clockwise in the world. A turned one is
    # a plain rotation. These four are what every tool needs for its angles;
    # they are only meaningful while ``tilted`` is false, which ucs_for makes
    # sure of before any of them is used.

    def angle_to_world(self, degrees: float) -> float:
        """A direction given as an angle in this UCS, as the world angle of the same direction, 0-360.

        On a turned UCS that is the angle plus the UCS rotation; on a flipped
        one the angle runs the other way, so it is the rotation minus it.
        """
        value = float(degrees)
        if self.tilted:
            a = math.radians(value)
            x, y, _ = self.direction_to_world((math.cos(a), math.sin(a), 0.0))
            return math.degrees(math.atan2(y, x)) % 360.0
        turned = self.rotation_degrees - value if self.flipped else self.rotation_degrees + value
        return turned % 360.0

    def turn_to_world(self, degrees: float) -> float:
        """An amount of turning (ROTATE's angle, a polar array's fill), as the world one.

        Turning is the same amount on any plan UCS; a flipped one only
        reverses which way is anticlockwise.
        """
        return -float(degrees) if self.flipped else float(degrees)

    def arc_to_world(self, start: float, end: float) -> tuple[float, float]:
        """An arc's start and end angles in this UCS, as the world arc's.

        An arc always sweeps anticlockwise from start to end. Seen in a
        flipped UCS the world arc runs the other way, so its ends swap.
        """
        if self.flipped:
            return self.angle_to_world(end), self.angle_to_world(start)
        return self.angle_to_world(start), self.angle_to_world(end)

    def bulge_to_world(self, bulge: float) -> float:
        """A polyline bulge in this UCS, as the world one: its sign turns over in a mirror."""
        return -float(bulge) if self.flipped else float(bulge)

    # ---- what to tell the agent -------------------------------------------

    @property
    def rotation_degrees(self) -> float:
        """How far the UCS X axis is turned from world X, about world Z, 0-360.

        This is the number that matters for a plan: an angle a drafter would
        type into ROTATE. It only describes the whole UCS while ``tilted`` is
        false; on a tilted UCS it is the rotation of the X axis' shadow on the
        world XY plane.
        """
        angle = math.degrees(math.atan2(self.x_axis[1], self.x_axis[0])) % 360.0
        return 0.0 if abs(angle) < ANGLE_TOLERANCE or abs(angle - 360.0) < ANGLE_TOLERANCE else round(angle, 9)

    @property
    def tilted(self) -> bool:
        """True when the UCS plane is not parallel to the world XY plane.

        A tilted UCS means a flat 2D answer is not enough: a Z of 0 in the UCS
        is not a Z of 0 in the world, and an angle measured on screen is not an
        angle in the world.
        """
        return abs(abs(self.z_axis[2]) - 1.0) > 1e-9

    @property
    def flipped(self) -> bool:
        """True when the UCS Z axis points away from world Z (the view is mirrored)."""
        return self.z_axis[2] < 0.0

    @property
    def moved(self) -> bool:
        """True when the UCS origin is not the world origin."""
        return _length(self.origin) > 1e-9

    @property
    def rotated(self) -> bool:
        """True when the UCS axes are turned or tilted away from the world ones."""
        return self.tilted or self.rotation_degrees != 0.0

    @property
    def is_world(self) -> bool:
        """True when this UCS is the World Coordinate System itself."""
        return not self.moved and not self.rotated and not self.flipped

    def describe(self, name: str | None = None) -> dict[str, Any]:
        """The UCS as the flat dict every tool reports it in."""
        return {
            "name": name or ("WORLD" if self.is_world else ""),
            "is_world": self.is_world,
            "origin": [round(v, 9) for v in self.origin],
            "x_axis": [round(v, 9) for v in self.x_axis],
            "y_axis": [round(v, 9) for v in self.y_axis],
            "z_axis": [round(v, 9) for v in self.z_axis],
            "rotation_degrees": self.rotation_degrees,
            "moved": self.moved,
            "rotated": self.rotated,
            "tilted": self.tilted,
            "flipped": self.flipped,
        }


WORLD = Ucs()


def advice(ucs: Ucs) -> str | None:
    """One plain sentence for the agent when the UCS is not the world one.

    Returned beside the UCS itself so a drawing tool's reply carries the
    warning rather than the agent having to notice the numbers.
    """
    if ucs.is_world:
        return None
    parts = []
    if ucs.rotation_degrees:
        parts.append(f"turned {ucs.rotation_degrees:g} degrees")
    if ucs.moved:
        parts.append("moved off the world origin")
    if ucs.tilted:
        parts.append("tilted out of the world XY plane")
    if ucs.flipped and not ucs.tilted:
        parts.append("flipped, so its Z points down")
    return (
        "This drawing's UCS is " + ", ".join(parts) + ". Every coordinate in this "
        "server is a WORLD coordinate, so points read off the screen in this UCS "
        "will land somewhere else. Pass coords='ucs' on the tools that offer it, "
        "or convert the points first with autocad_convert_points."
    )


def transform_points(
    points: Sequence[Sequence[float]], ucs: Ucs, into: str
) -> list[Vec3]:
    """A list of points moved between the UCS and the world.

    ``into`` is the system the answers come back in: 'world' treats the input
    as UCS coordinates, 'ucs' treats it as world coordinates.
    """
    if into == "world":
        return [ucs.to_world(p) for p in points]
    if into == "ucs":
        return [ucs.to_ucs(p) for p in points]
    raise ValueError("'into' must be 'world' or 'ucs'")


def rotate_about(point: Sequence[float], centre: Sequence[float], degrees: float) -> Vec3:
    """A point turned about a centre in the world XY plane (Z kept)."""
    x, y, z = as_vec3(point)
    cx, cy, _ = as_vec3(centre)
    angle = math.radians(float(degrees))
    cos, sin = math.cos(angle), math.sin(angle)
    dx, dy = x - cx, y - cy
    return (cx + dx * cos - dy * sin, cy + dx * sin + dy * cos, z)


def corners_box(
    corner1: Sequence[float], corner2: Sequence[float]
) -> tuple[float, float, float, float]:
    """Two opposite corners in any order, as (min x, min y, max x, max y)."""
    a, b = as_vec3(corner1), as_vec3(corner2)
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def box_of(points: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    """The box around a set of points, as (min x, min y, max x, max y)."""
    if not points:
        raise ValueError("no points to box")
    xs = [as_vec3(p)[0] for p in points]
    ys = [as_vec3(p)[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def rotated_box(
    box: tuple[float, float, float, float], degrees: float
) -> tuple[float, float, float, float]:
    """The upright box that still contains a box after it is turned.

    What a twisted viewport needs: the view is turned, so the area AutoCAD has
    to be told to fit is the upright box around the turned one.
    """
    x1, y1, x2, y2 = box
    centre = ((x1 + x2) / 2.0, (y1 + y2) / 2.0, 0.0)
    turned = [
        rotate_about(p, centre, degrees)
        for p in ((x1, y1, 0.0), (x2, y1, 0.0), (x2, y2, 0.0), (x1, y2, 0.0))
    ]
    return box_of(turned)
