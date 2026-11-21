"""3D: solids, profiles turned into solids, booleans, and looking at the result.

What a modeller needs to go from a flat drawing to a model and back:

* **Primitives** - box, wedge, cylinder, cone, sphere, torus. A duct, a pad, a
  bollard, a tank.
* **A profile into a solid** - draw the section flat, then extrude it along Z
  or revolve it about an axis. Every real part starts this way.
* **Booleans** - union, subtract, intersect. A plate with holes in it is a box
  minus some cylinders.
* **Mass properties** - volume, centroid, bounding box. What a weight takes-off
  needs.
* **Looking at it** - a named 3D direction and a visual style, so the modeller
  (and ``autocad_preview``) can actually see the model.
* **3D paths** - a pipe route or a helix as one 3D polyline.

A note on where the geometry lands: AutoCAD's primitive calls place a solid by
the **centre of its bounding box**, with the base on the current XY plane. That
is not where a drafter expects a box to go, so these tools take the base centre
and work the rest out, and report both.
"""

from __future__ import annotations

import math
import time
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..acad.coords import as_vec3
from ..acad.entities import describe, resolve_handle, resolve_handles, short_type
from ..acad.tables import apply_properties, ensure_layer
from ..acad.units import rad
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, double_array, object_array, point_to_list
from ._shared import (
    COLOR_OPT,
    COORDS_OPT,
    LAYER_OPT,
    created_payload,
    plugin_read,
    ucs_for,
    world_coords,
    world_direction,
)

# AcBooleanType: the Boolean method's operation. The first object is the one
# that changes; the second is consumed.
BOOLEAN_OPS = {"union": 0, "intersect": 1, "subtract": 2}

# AcRegenType: acActiveViewport = 0, acAllViewports = 1.
AC_ALL_VIEWPORTS = 1

# Where a named view looks from, as a direction vector. Same names AutoCAD's
# own View panel uses.
VIEW_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "top": (0.0, 0.0, 1.0),
    "plan": (0.0, 0.0, 1.0),
    "bottom": (0.0, 0.0, -1.0),
    "front": (0.0, -1.0, 0.0),
    "back": (0.0, 1.0, 0.0),
    "left": (-1.0, 0.0, 0.0),
    "right": (1.0, 0.0, 0.0),
    "sw_iso": (-1.0, -1.0, 1.0),
    "se_iso": (1.0, -1.0, 1.0),
    "ne_iso": (1.0, 1.0, 1.0),
    "nw_iso": (-1.0, 1.0, 1.0),
}

# VSCURRENT takes the style's name. These are the ones AutoCAD ships.
VISUAL_STYLES = (
    "2dwireframe", "wireframe", "hidden", "realistic", "conceptual",
    "shaded", "shaded with edges", "shades of gray", "sketchy", "x-ray",
)

# What to answer the VSCURRENT command with for each. VSCURRENT is a command,
# not a system variable - SetVariable("VSCURRENT", ...) is refused (AutoCAD
# 2027, 2026-10-28) - and COM has no visual style on a model viewport. The
# leading underscore keeps the English option in any language of AutoCAD; the
# two names with spaces go by their capital letter, as the prompt shows them
# ("shaded with Edges", "shades of Gray").
VISUAL_STYLE_OPTIONS: dict[str, str] = {
    "2dwireframe": "_2dwireframe",
    "wireframe": "_Wireframe",
    "hidden": "_Hidden",
    "realistic": "_Realistic",
    "conceptual": "_Conceptual",
    "shaded": "_Shaded",
    "shaded with edges": "_E",
    "shades of gray": "_G",
    "sketchy": "_SKetchy",
    "x-ray": "_X",
}

# How long VSCURRENT gets to finish before a prompt still open means its answer
# was not taken. SendCommand normally returns with the command done; the wait
# covers the times it does not.
VSCURRENT_WAIT_S = 1.0
VSCURRENT_POLL_S = 0.1

Primitive = Literal[
    "box", "wedge", "cylinder", "cone", "sphere", "torus",
    "elliptical_cylinder", "elliptical_cone",
]


def _try(getter, default=None):
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def _write(target: Any, name: str, value: Any) -> bool:
    try:
        setattr(target, name, value)
        return True
    except BaseException:  # noqa: BLE001 - a refusal is the answer, not a crash
        return False


def helix_points(
    radius: float,
    turns: float,
    height: float,
    top_radius: float | None = None,
    centre: tuple[float, float, float] = (0.0, 0.0, 0.0),
    per_turn: int = 36,
) -> list[list[float]]:
    """The points of a helix, as a 3D path. Pure, so it is tested without AutoCAD.

    ``top_radius`` different from ``radius`` gives a conical coil. A negative
    height winds downward. The last point closes the final turn exactly, so a
    whole number of turns comes back round to its starting angle.
    """
    if radius <= 0.0:
        raise ValueError(f"a helix needs a radius above zero, got {radius:g}")
    if turns <= 0.0:
        raise ValueError(f"a helix needs more than zero turns, got {turns:g}")
    if top_radius is not None and top_radius <= 0.0:
        raise ValueError(f"top_radius must be above zero, got {top_radius:g}")
    steps = max(8, int(round(per_turn * turns)))
    cx, cy, cz = centre
    r1 = radius if top_radius is None else float(top_radius)
    out = []
    for i in range(steps + 1):
        t = i / steps
        angle = 2.0 * math.pi * turns * t
        r = radius + (r1 - radius) * t
        out.append(
            [
                round(cx + r * math.cos(angle), 9),
                round(cy + r * math.sin(angle), 9),
                round(cz + height * t, 9),
            ]
        )
    return out


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_add_solid", **tool_meta("Add A 3D Solid"))
@tool_errors
async def autocad_add_solid(
    shape: Annotated[
        Primitive,
        Field(
            description=(
                "'box' and 'wedge' need length, width and height. 'cylinder' and 'cone' "
                "need radius (or diameter) and height. 'sphere' needs radius. 'torus' "
                "needs radius and tube_radius. 'elliptical_cylinder' and "
                "'elliptical_cone' are the oval ones — an oval duct or a tapered oval "
                "stack — and take length, width and height as the OVERALL sizes."
            )
        ),
    ],
    base: Annotated[
        list[float],
        Field(
            description=(
                "The centre of the solid's **base**, as [x, y] or [x, y, z] — where a "
                "drafter would put it. For a sphere and a torus this is the centre of the "
                "shape itself, since neither has a flat base."
            )
        ),
    ],
    length: Annotated[float | None, Field(default=None, gt=0, description="Box and wedge: size along X. Elliptical shapes: the overall size across X.")] = None,
    width: Annotated[float | None, Field(default=None, gt=0, description="Box and wedge: size along Y. Elliptical shapes: the overall size across Y.")] = None,
    height: Annotated[float | None, Field(default=None, gt=0, description="Box, wedge, cylinder and cone: size along Z.")] = None,
    radius: Annotated[float | None, Field(default=None, gt=0, description="Cylinder, cone, sphere: the radius. Torus: the radius of the ring itself.")] = None,
    diameter: Annotated[float | None, Field(default=None, gt=0, description="Instead of radius — how a pipe or a bollard is normally called out.")] = None,
    tube_radius: Annotated[float | None, Field(default=None, gt=0, description="Torus: the radius of the tube going round the ring.")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Make a 3D solid primitive, placed by the centre of its base.

    AutoCAD's own calls place a solid by the centre of its bounding box, which
    is halfway up it. That is never where you mean, so these take the **base
    centre** and work the rest out — a 300 high cylinder at z=0 sits on z=0.
    Both points come back in the result.

    One undo step.

    Args:
        shape (str): box, wedge, cylinder, cone, sphere, torus,
            elliptical_cylinder or elliptical_cone.
        base (list[float]): centre of the base ([x, y] or [x, y, z]).
        length / width / height (Optional[float]): as the shape needs.
        radius / diameter (Optional[float]): as the shape needs.
        tube_radius (Optional[float]): torus only.
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": str, "shape": str,
             "base": [x, y, z], "centre": [x, y, z], "volume": float,
             "bounding_box": {"min", "max"}}

    Examples:
        - Use when: "a 2400 x 1200 x 200 concrete pad at the origin" —
          shape='box'.
        - Use when: "a 300 diameter column 3000 high" — shape='cylinder',
          diameter=300, height=3000.
        - Use when: "a 400 x 200 oval duct, 2 m long, standing up" —
          shape='elliptical_cylinder', length=400, width=200, height=2000.
          Length and width are the overall sizes, not the half axes.
        - Don't use when: the part is really a 2D section to be extruded —
          draw the profile and use autocad_extrude_profile, which gets the real
          shape rather than a box that is nearly it.

    Error Handling:
        - Each shape names exactly the sizes it needs and which were missing.
        - radius and diameter together are refused rather than one quietly winning.
    """
    if radius is not None and diameter is not None:
        raise AutocadError("Give radius or diameter, not both.")
    r = float(radius) if radius is not None else (float(diameter) / 2.0 if diameter else None)

    needs: dict[str, tuple[str, ...]] = {
        "box": ("length", "width", "height"),
        "wedge": ("length", "width", "height"),
        "cylinder": ("radius", "height"),
        "cone": ("radius", "height"),
        "sphere": ("radius",),
        "torus": ("radius", "tube_radius"),
        "elliptical_cylinder": ("length", "width", "height"),
        "elliptical_cone": ("length", "width", "height"),
    }
    have = {"length": length, "width": width, "height": height, "radius": r,
            "tube_radius": tube_radius}
    missing = [n for n in needs[shape] if have.get(n) is None]
    if missing:
        raise AutocadError(
            f"'{shape}' needs {', '.join(needs[shape])}; missing {', '.join(missing)}."
            + (" radius can be given as diameter instead." if "radius" in missing else "")
        )
    if shape.startswith("elliptical") and float(length) == float(width):
        raise AutocadError(
            f"'{shape}' with length and width both {float(length):g} is a plain "
            f"{shape.split('_')[1]} — use shape='{shape.split('_')[1]}' with "
            "radius instead, which is clearer to read."
        )
    if shape == "torus" and float(tube_radius) >= r:
        raise AutocadError(
            f"the tube radius ({float(tube_radius):g}) must be smaller than the ring radius "
            f"({r:g}), or the torus closes on itself"
        )
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        target = get_space(doc, "model")
        bx, by, bz = world_coords(base, ucs)

        # AutoCAD places these by the centre of the bounding box. A sphere and a
        # torus have no base, so their centre is the point given; everything
        # else rises from its base, so the centre is half a height up.
        lift = 0.0 if shape in ("sphere", "torus") else float(height) / 2.0
        cx, cy, cz = bx, by, bz + lift
        centre = apoint(cx, cy, cz)
        # AutoCAD makes a box, a wedge and an oval square to the world. On a
        # turned UCS they are turned to match, as a batch rectangle is.
        turn = rad(ucs.rotation_degrees) if ucs is not None and shape in (
            "box", "wedge", "elliptical_cylinder", "elliptical_cone") else 0.0

        with undo_mark(doc):
            try:
                if shape == "box":
                    solid = target.AddBox(centre, float(length), float(width), float(height))
                elif shape == "wedge":
                    solid = target.AddWedge(centre, float(length), float(width), float(height))
                elif shape == "cylinder":
                    solid = target.AddCylinder(centre, r, float(height))
                elif shape == "cone":
                    solid = target.AddCone(centre, r, float(height))
                elif shape == "sphere":
                    solid = target.AddSphere(centre, r)
                elif shape in ("elliptical_cylinder", "elliptical_cone"):
                    # AutoCAD takes radii, major one first along X: length and
                    # width are overall sizes, so halve them, and make a shape
                    # wider than long the long way, then turn it 90 degrees.
                    across, deep = float(length) / 2.0, float(width) / 2.0
                    add = (target.AddEllipticalCylinder if shape == "elliptical_cylinder"
                           else target.AddEllipticalCone)
                    solid = add(centre, max(across, deep), min(across, deep), float(height))
                    if deep > across:
                        turn += math.pi / 2.0
                else:
                    solid = target.AddTorus(centre, r, float(tube_radius))
                if abs(turn) > 1e-12:
                    solid.Rotate(centre, turn)
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(
                    f"AutoCAD would not make that {shape} ({com_message(exc)}). Check the sizes "
                    "are above zero and that this drawing is not AutoCAD LT, which has no solids."
                ) from exc
            notes = apply_properties(doc, solid, layer, aci, None)

        payload = created_payload(
            solid,
            notes,
            shape=shape,
            base=[round(bx, 6), round(by, 6), round(bz, 6)],
            centre=[round(cx, 6), round(cy, 6), round(cz, 6)],
            volume=_try(lambda: round(float(solid.Volume), 6)),
        )
        low, high = _try(lambda: solid.GetBoundingBox(), (None, None))
        if low is not None:
            payload["bounding_box"] = {"min": point_to_list(low), "max": point_to_list(high)}
        return payload

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# A profile into a solid
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_extrude_profile", **tool_meta("Extrude Or Revolve A Profile"))
@tool_errors
async def autocad_extrude_profile(
    handles: Annotated[
        list[str],
        Field(
            min_length=1,
            description=(
                "The curves making the closed profile: lines, arcs, circles, polylines, "
                "ellipses or splines, all on one plane and joined end to end. One closed "
                "polyline or circle is the easy case — give just that."
            ),
        ),
    ],
    height: Annotated[
        float | None,
        Field(default=None, description="Extrude: how far along Z, in drawing units. Negative goes the other way. Give this or revolve_angle."),
    ] = None,
    taper: Annotated[
        float,
        Field(default=0.0, description="Extrude: taper angle in degrees. A positive angle draws the sides in as it rises, as a plinth or a footing does."),
    ] = 0.0,
    revolve_angle: Annotated[
        float | None,
        Field(default=None, description="Revolve: the angle in degrees to sweep the profile about the axis. 360 for a full turn. Give this or height."),
    ] = None,
    axis_point: Annotated[
        list[float] | None,
        Field(default=None, description="Revolve: a point on the axis, as [x, y] or [x, y, z]."),
    ] = None,
    axis_direction: Annotated[
        list[float] | None,
        Field(default=None, description="Revolve: which way the axis runs, e.g. [0,1,0] for the Y axis. Rotation follows the right-hand rule about it."),
    ] = None,
    path_handle: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Sweep: the handle of the curve to run the profile along — a polyline, "
                "circle, arc, ellipse or spline. This is how a duct or a pipe follows a "
                "route. Give this instead of height or revolve_angle."
            ),
        ),
    ] = None,
    keep_profile: Annotated[
        bool,
        Field(default=True, description="Keep the original curves. They are kept by default, because they are usually the 2D section you still want on the drawing."),
    ] = True,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Turn a closed 2D profile into a solid: extrude it, revolve it, or sweep it along a path.

    This is how every real part gets modelled — draw the section flat, then
    give it depth. A flange is a profile revolved 360 degrees; a bracket is a
    profile extruded; a footing is a profile extruded with a taper; a duct or
    a cable tray following a route is a profile **swept along** that route.

    The curves are joined into a region first (AutoCAD's own step), the solid
    is made from it, and that intermediate region is then removed — it is
    scaffolding, not something you asked for. Your original curves stay unless
    you say otherwise.

    One undo step.

    Args:
        handles (list[str]): the curves forming the closed profile.
        height (Optional[float]): extrude this far along Z.
        taper (float): extrude taper angle, degrees.
        revolve_angle (Optional[float]): revolve this many degrees instead.
        axis_point / axis_direction (Optional[list[float]]): the axis to revolve about.
        path_handle (Optional[str]): sweep: the route to run the profile along.
        keep_profile (bool): keep the original curves (default true).
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "operation": "extrude" |
             "revolve" | "sweep", "regions_found": int, "volume": float,
             "bounding_box": {...}, "profile_kept": bool, "swept_along": str | null}

    Examples:
        - Use when: "extrude this outline 200 up" — handles the polyline,
          height=200.
        - Use when: "revolve this section round the Y axis to make the flange"
          — revolve_angle=360, axis_point and axis_direction.
        - Use when: "a tapered footing" — height plus taper.
        - Use when: "run that duct section along the route I drew" —
          path_handle=the route polyline. That is a sweep, and it is how a
          duct, a pipe, a cable tray or a handrail follows a path.
        - Don't use when: a plain box or cylinder will do (autocad_add_solid).

    Error Handling:
        - Curves that do not close, or are not all on one plane, come back as
          AutoCAD's own refusal with what to check.
        - A revolve without an axis, or with an angle of zero, is refused before
          anything is made.
        - More than one region from the curves is reported, with the count: that
          means the profile closed more than one loop, which is rarely meant.
    """
    chosen = [name for name, value in (("height", height), ("revolve_angle", revolve_angle),
                                      ("path_handle", path_handle)) if value is not None]
    if len(chosen) != 1:
        raise AutocadError(
            "Give exactly one of: 'height' to extrude straight up, 'revolve_angle' with an "
            "axis to turn it, or 'path_handle' to sweep it along a route"
            + (f" — got {', '.join(chosen)}." if chosen else " — got none.")
        )
    if height is not None and abs(float(height)) < 1e-9:
        raise AutocadError("A height of zero extrudes nothing.")
    if revolve_angle is not None:
        if abs(float(revolve_angle)) < 1e-9:
            raise AutocadError("A revolve angle of zero sweeps nothing.")
        if not axis_point or not axis_direction:
            raise AutocadError(
                "A revolve needs axis_point (a point on the axis) and axis_direction "
                "(which way it runs, e.g. [0,1,0])."
            )
        if len(axis_direction) < 3 or all(abs(float(v)) < 1e-12 for v in axis_direction[:3]):
            raise AutocadError("axis_direction needs [x, y, z] and cannot be all zeros.")
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        target = get_space(doc, "model")
        curves = resolve_handles(doc, handles)
        kinds = {short_type(c) for c in curves}

        with undo_mark(doc):
            try:
                made = target.AddRegion(object_array(curves))
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(
                    f"Those curves would not make a region ({com_message(exc)}). A profile has "
                    "to be closed, flat (all on one plane) and joined end to end, and the "
                    f"curves given are: {', '.join(sorted(kinds))}. Check for gaps with "
                    "autocad_select_connected."
                ) from exc
            regions = list(made) if isinstance(made, tuple) else [made]
            regions = [r for r in regions if r is not None]
            if not regions:
                raise AutocadError(
                    "Those curves closed no region. Check the profile is closed and flat."
                )
            region = regions[0]

            try:
                if height is not None:
                    solid = target.AddExtrudedSolid(region, float(height), rad(taper) or 0.0)
                    operation = "extrude"
                elif path_handle is not None:
                    path = resolve_handle(doc, path_handle)
                    solid = target.AddExtrudedSolidAlongPath(region, path)
                    operation = "sweep"
                else:
                    solid = target.AddRevolvedSolid(
                        region,
                        apoint(*world_coords(axis_point, ucs)),
                        apoint(*world_direction(axis_direction, ucs)),
                        rad(revolve_angle),
                    )
                    operation = "revolve"
            except BaseException as exc:  # noqa: BLE001
                # The region was ours, so it goes whatever happens next.
                _try(lambda: region.Delete())
                raise AutocadError(
                    f"AutoCAD would not {'extrude' if height is not None else 'revolve'} that "
                    f"profile ({com_message(exc)}). For a taper, check the sides do not meet "
                    "before the top; for a revolve, check the axis does not cut through the "
                    "profile."
                ) from exc

            # Tidy up the scaffolding: the region the solid was built from, and
            # any extra regions the curves closed that nothing was built from.
            # Delete returns nothing either way, so there is nothing to count -
            # a region that will not go is harmless, and the warning below
            # already tells the caller when there was more than one.
            for extra in regions:
                _try(lambda e=extra: e.Delete())
            if not keep_profile:
                for curve in curves:
                    _try(lambda c=curve: c.Delete())

            notes = apply_properties(doc, solid, layer, aci, None)

        payload = created_payload(
            solid,
            notes,
            operation=operation,
            regions_found=len(regions),
            swept_along=short_type(resolve_handle(doc, path_handle)) if path_handle else None,
            volume=_try(lambda: round(float(solid.Volume), 6)),
            profile_kept=bool(keep_profile),
        )
        low, high = _try(lambda: solid.GetBoundingBox(), (None, None))
        if low is not None:
            payload["bounding_box"] = {"min": point_to_list(low), "max": point_to_list(high)}
        if len(regions) > 1:
            payload["warning"] = (
                f"Those curves closed {len(regions)} separate loops; the solid was made from "
                "the first. If you meant one profile, check for a stray curve."
            )
        return payload

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Booleans
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_solid_boolean", **tool_meta("Join, Cut Or Intersect Solids", destructive=True))
@tool_errors
async def autocad_solid_boolean(
    operation: Annotated[
        Literal["union", "subtract", "intersect"],
        Field(
            description=(
                "'union' joins them into one. 'subtract' cuts the others out of the first "
                "— a plate with holes is a box minus some cylinders. 'intersect' keeps only "
                "the part they share."
            )
        ),
    ],
    handle: Annotated[
        str,
        Field(description="The solid that stays and is changed. For 'subtract' this is the one being cut."),
    ],
    others: Annotated[
        list[str],
        Field(min_length=1, description="The other solids. **These are consumed** — AutoCAD removes them as it applies the operation."),
    ],
) -> str:
    """Join, cut or intersect 3D solids — the real modelling step.

    The first solid is the one that remains and is modified; the others are
    **consumed by AutoCAD**, which is how its own UNION, SUBTRACT and INTERSECT
    behave. The result's handle is the first solid's, unchanged.

    One undo step, so one Ctrl+Z puts them all back.

    Args:
        operation (str): union, subtract or intersect.
        handle (str): the solid that stays (for subtract, the one being cut).
        others (list[str]): the solids consumed by the operation.

    Returns:
        str: JSON: {"operation", "handle", "consumed": [str], "failed": [...],
             "volume_before": float, "volume_after": float,
             "bounding_box": {...}}

    Examples:
        - Use when: "cut these four bolt holes out of the plate" —
          operation='subtract', handle the plate, others the cylinders.
        - Use when: "join the base and the upstand".
        - Don't use when: the objects are 2D (regions boolean the same way, but
          a 2D outline is usually better edited directly).

    Error Handling:
        - A handle that is not a 3D solid or a region is named before anything
          is changed, so nothing is consumed by mistake.
        - The volume before and after is reported: a subtract that removed
          nothing shows up as an unchanged volume.
    """
    if handle in others:
        raise AutocadError(
            "The first solid is also in 'others'. A solid cannot be combined with itself."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        first = resolve_handle(doc, handle)
        rest = resolve_handles(doc, others)

        # Check every one of them before touching any: the others are consumed,
        # so a failure halfway would leave a mess that cannot be reasoned about.
        for entity, label in [(first, handle)] + list(zip(rest, others, strict=False)):
            kind = short_type(entity)
            if kind not in ("3dsolid", "region"):
                raise AutocadError(
                    f"{label} is a {kind}, not a 3D solid or a region, so it cannot take part "
                    "in a boolean. Make it a solid first with autocad_add_solid or "
                    "autocad_extrude_profile."
                )

        before = _try(lambda: round(float(first.Volume), 6))
        code = BOOLEAN_OPS[operation]
        consumed: list[str] = []
        failed: list[dict[str, Any]] = []

        with undo_mark(doc):
            for label, other in zip(others, rest, strict=False):
                try:
                    first.Boolean(code, other)
                    consumed.append(label)
                except BaseException as exc:  # noqa: BLE001 - report, keep going
                    failed.append({"handle": label, "reason": com_message(exc)})

        after = _try(lambda: round(float(first.Volume), 6))
        result: dict[str, Any] = {
            "operation": operation,
            "handle": str(_try(lambda: first.Handle, handle)),
            "consumed": consumed,
            "failed": failed,
            "volume_before": before,
            "volume_after": after,
        }
        low, high = _try(lambda: first.GetBoundingBox(), (None, None))
        if low is not None:
            result["bounding_box"] = {"min": point_to_list(low), "max": point_to_list(high)}
        if before is not None and after is not None and abs(after - before) < 1e-9 and consumed:
            result["warning"] = (
                "The volume did not change, so the operation did nothing useful — for a "
                "subtract that usually means the solids were not actually overlapping."
            )
        return result

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Mass properties
# ---------------------------------------------------------------------------


@mcp.tool(
    name="autocad_solid_properties",
    **tool_meta("Read A Solid's Volume And Centroid", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_solid_properties(
    handles: Annotated[
        list[str],
        Field(min_length=1, description="The solids or regions to measure, by handle."),
    ],
) -> str:
    """Volume, centroid, bounding box and moments for 3D solids — what a take-off needs.

    Give a density and the volume becomes a weight: that is the number a
    fabricator and a lifting plan both want. Regions report their area and
    perimeter instead of a volume.

    Args:
        handles (list[str]): the solids or regions to measure.

    Returns:
        str: JSON: {
          "count": int, "total_volume": float, "total_area": float,
          "items": [{"handle", "type", "volume", "area", "perimeter",
                     "centroid", "bounding_box", "size",
                     "moment_of_inertia", "radii_of_gyration"}],
          "unreadable": [{"handle", "type"}]
        }

    Examples:
        - Use when: "how much concrete is in these pads" — total_volume, then
          multiply by the density yourself.
        - Use when: "where is the centre of gravity of this frame" — centroid.
        - Don't use when: you want a length or an area of 2D linework
          (autocad_measure, autocad_total_length).

    Error Handling:
        - Anything that reports no volume or area is listed in "unreadable"
          with its type, rather than failing the call.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        items: list[dict[str, Any]] = []
        unreadable: list[dict[str, Any]] = []

        for handle, entity in zip(handles, resolve_handles(doc, handles), strict=False):
            row: dict[str, Any] = {"handle": handle, "type": short_type(entity)}
            volume = _try(lambda e=entity: round(float(e.Volume), 6))
            area = _try(lambda e=entity: round(float(e.Area), 6))
            if volume is None and area is None:
                unreadable.append(row)
                continue
            if volume is not None:
                row["volume"] = volume
            if area is not None:
                row["area"] = area
            for key, prop in (
                ("perimeter", "Perimeter"),
                ("centroid", "Centroid"),
                ("moment_of_inertia", "MomentOfInertia"),
                ("radii_of_gyration", "RadiiOfGyration"),
                ("principal_moments", "PrincipalMoments"),
            ):
                value = _try(lambda e=entity, p=prop: getattr(e, p))
                if value is None:
                    continue
                row[key] = (
                    round(float(value), 6)
                    if isinstance(value, (int, float))
                    else point_to_list(value)
                )
            low, high = _try(lambda e=entity: e.GetBoundingBox(), (None, None))
            if low is not None:
                lo, hi = point_to_list(low), point_to_list(high)
                row["bounding_box"] = {"min": lo, "max": hi}
                row["size"] = [round(h - lo_v, 6) for h, lo_v in zip(hi, lo, strict=False)]
            items.append(row)

        return {
            "count": len(items),
            "total_volume": round(sum(i.get("volume") or 0.0 for i in items), 6),
            "total_area": round(sum(i.get("area") or 0.0 for i in items), 6),
            "items": items,
            "unreadable": unreadable,
        }

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# 3D paths
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_draw_3d_path", **tool_meta("Draw A 3D Path Or Helix"))
@tool_errors
async def autocad_draw_3d_path(
    points: Annotated[
        list[list[float]] | None,
        Field(default=None, description="The path, each [x, y, z] — a pipe or cable route through a building. Give this, or the helix settings below."),
    ] = None,
    helix_radius: Annotated[float | None, Field(default=None, gt=0, description="Helix: the radius. Give with helix_turns and helix_height.")] = None,
    helix_turns: Annotated[float | None, Field(default=None, gt=0, description="Helix: how many turns.")] = None,
    helix_height: Annotated[float | None, Field(default=None, description="Helix: the rise over all the turns. Negative winds the other way down.")] = None,
    helix_top_radius: Annotated[float | None, Field(default=None, gt=0, description="Helix: a different radius at the top, for a conical coil.")] = None,
    helix_centre: Annotated[list[float] | None, Field(default=None, description="Helix: the centre of its base, as [x, y] or [x, y, z]. Default the origin.")] = None,
    per_turn: Annotated[int, Field(default=36, ge=8, le=360, description="Helix: points per turn. More is smoother and heavier.")] = 36,
    closed: Annotated[bool, Field(default=False, description="Close the path back to its start.")] = False,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Draw a 3D polyline: a pipe or cable route through a building, or a helix.

    One object, so it moves and selects as one thing, and it can be used as a
    path later. A helix is generated from its radius, turns and rise —
    a spiral stair's handrail, a coil, a spiral duct, a thread line.

    One undo step.

    Args:
        points (Optional[list[list[float]]]): the path, each [x, y, z].
        helix_radius / helix_turns / helix_height (Optional[float]): a helix instead.
        helix_top_radius (Optional[float]): a different radius at the top.
        helix_centre (Optional[list[float]]): centre of the helix's base.
        per_turn (int): points per turn of the helix.
        closed (bool): close the path.
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "polyline3d",
             "vertex_count": int, "length": float, "shape": "path" | "helix"}

    Examples:
        - Use when: "route this drain from the gully up to the stack" — the
          points it passes through.
        - Use when: "a handrail up the spiral stair" — helix_radius,
          helix_turns, helix_height.
        - Don't use when: the route is flat (autocad_draw_polyline, which can
          carry arcs for the bends).

    Error Handling:
        - Needs either points or the three helix settings, and says which are
          missing.
        - A path of fewer than two points is refused.
    """
    helix = helix_radius is not None or helix_turns is not None or helix_height is not None
    if points is not None and helix:
        raise AutocadError("Give 'points' for a path, or the helix settings — not both.")
    if helix:
        missing = [
            name
            for name, value in (("helix_radius", helix_radius), ("helix_turns", helix_turns),
                                ("helix_height", helix_height))
            if value is None
        ]
        if missing:
            raise AutocadError(f"A helix needs {', '.join(missing)} as well.")
        base = (list(helix_centre or []) + [0.0, 0.0, 0.0])[:3]
        try:
            path = helix_points(
                float(helix_radius), float(helix_turns), float(helix_height),
                float(helix_top_radius) if helix_top_radius else None,
                (float(base[0]), float(base[1]), float(base[2])), per_turn,
            )
        except ValueError as exc:
            raise AutocadError(str(exc)) from exc
        shape = "helix"
    else:
        if not points or len(points) < 2:
            raise AutocadError("A 3D path needs at least two points, each [x, y, z].")
        path = [list((list(p) + [0.0, 0.0, 0.0])[:3]) for p in points]
        shape = "path"
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        target = get_space(doc, "model")
        world = [world_coords(p, ucs) for p in path]
        flat = [c for p in world for c in p]

        with undo_mark(doc):
            if layer:
                ensure_layer(doc, layer)
            try:
                entity = target.Add3DPoly(double_array(flat))
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(
                    f"AutoCAD would not make the 3D polyline ({com_message(exc)})."
                ) from exc
            if closed:
                _write(entity, "Closed", True)
            notes = apply_properties(doc, entity, layer, aci, None)

        info = describe(entity)
        return created_payload(
            entity,
            notes,
            shape=shape,
            vertex_count=len(world),
            length=info.get("length"),
            start=[round(v, 6) for v in world[0]],
            end=[round(v, 6) for v in world[-1]],
        )

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Looking at it
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_set_3d_view", **tool_meta("Set The 3D View And Visual Style", idempotent=True))
@tool_errors
async def autocad_set_3d_view(
    direction: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Where to look from: top (or plan), bottom, front, back, left, right, "
                "sw_iso, se_iso, ne_iso, nw_iso. Omit to leave the direction alone."
            ),
        ),
    ] = None,
    vector: Annotated[
        list[float] | None,
        Field(default=None, description="Instead of a name: the direction to look from, as [x, y, z]."),
    ] = None,
    visual_style: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "2dwireframe, wireframe, hidden, realistic, conceptual, shaded, "
                "'shaded with edges', 'shades of gray', sketchy, x-ray. 'hidden' is the "
                "one a shop drawing wants; 'realistic' is for showing someone."
            ),
        ),
    ] = None,
    zoom_extents: Annotated[
        bool,
        Field(default=True, description="Fit the drawing on screen afterwards, so the new view actually shows the model."),
    ] = True,
) -> str:
    """Look at the model from a named direction, in a chosen visual style.

    What you need before ``autocad_preview`` can show a 3D model usefully: a
    south-west isometric in the hidden style reads like a shop drawing, while
    plan plus 2D wireframe is back to normal drafting.

    This only changes what is on screen, so it needs no padlock — the same
    level as autocad_zoom. It does not move or change a single object.

    Args:
        direction (Optional[str]): a named direction, e.g. 'sw_iso'.
        vector (Optional[list[float]]): or an explicit [x, y, z].
        visual_style (Optional[str]): the visual style to switch to.
        zoom_extents (bool): fit the drawing afterwards.

    After setting it, the style the viewport really has is read back
    through Heron's plug-in and given as "visual_style_found" (AutoCAD's own
    name, e.g. 'Realistic'). If it is not the one asked for, that is said in
    "not_set". Without the plug-in it is null, with the reason.

    Returns:
        str: JSON: {"direction": [x, y, z], "named": str | null,
             "visual_style": str | null, "visual_style_found": str | null,
             "zoomed": bool, "not_set": [str]}

    Examples:
        - Use when: "show me the model in 3D" — direction='sw_iso',
          visual_style='hidden', then autocad_preview.
        - Use when: "back to plan" — direction='top',
          visual_style='2dwireframe'.
        - Don't use when: you want a viewport on a sheet
          (autocad_add_viewport).

    Error Handling:
        - An unknown direction or visual style is named, with the list of real
          ones, before anything changes.
        - The visual style is set by typing the VSCURRENT command (it is a
          command, not a system variable). If AutoCAD does not take the
          option, the command is cancelled and the style is in "not_set".
    """
    if direction and vector:
        raise AutocadError("Give a named 'direction' or a 'vector', not both.")
    if not direction and not vector and not visual_style:
        raise AutocadError(
            "Nothing to do. Give a direction, a vector, or a visual_style."
        )

    aim: tuple[float, float, float] | None = None
    named: str | None = None
    if direction:
        key = str(direction).strip().lower().replace("-", "_").replace(" ", "_")
        if key not in VIEW_DIRECTIONS:
            raise AutocadError(
                f"'{direction}' is not a view direction. Use one of: "
                + ", ".join(sorted(VIEW_DIRECTIONS))
            )
        aim, named = VIEW_DIRECTIONS[key], key
    elif vector:
        if len(vector) < 3 or all(abs(float(v)) < 1e-12 for v in vector[:3]):
            raise AutocadError("vector needs [x, y, z] and cannot be all zeros.")
        aim = (float(vector[0]), float(vector[1]), float(vector[2]))

    style: str | None = None
    if visual_style:
        wanted = str(visual_style).strip().lower()
        if wanted not in VISUAL_STYLES:
            raise AutocadError(
                f"'{visual_style}' is not a visual style this server knows. Use one of: "
                + ", ".join(VISUAL_STYLES)
            )
        style = wanted

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        not_set: list[str] = []
        result: dict[str, Any] = {"named": named, "visual_style": style, "zoomed": False}

        if aim is not None:
            viewport = doc.ActiveViewport
            if not _write(viewport, "Direction", apoint(*aim)):
                not_set.append("direction")
            else:
                # A viewport's changes only take once it is made active again;
                # this reassignment is what applies them.
                if not _write(doc, "ActiveViewport", viewport):
                    not_set.append("direction (the viewport would not reactivate)")
            result["direction"] = [round(v, 6) for v in aim]

        if style is not None:
            option = VISUAL_STYLE_OPTIONS[style]
            try:
                # Over COM, not the plug-in's quiet input: the plug-in takes
                # typed input only inside a Change job, and this is a View tool.
                doc.SendCommand(f"_.VSCURRENT {option}\n")
            except BaseException as exc:  # noqa: BLE001 - say so, change nothing else
                not_set.append(f"visual_style ({com_message(exc)})")
            else:
                # Still asking means the option was not taken: cancel, so the
                # next tool does not find AutoCAD waiting at the prompt.
                if _still_asking(doc):
                    _try(lambda: doc.SendCommand("\x1b\x1b"))
                    not_set.append(
                        f"visual_style (VSCURRENT did not take '{option}'; set it with "
                        "the Visual Styles control at the top left of the drawing)"
                    )

        if zoom_extents:
            try:
                doc.Application.ZoomExtents()
                result["zoomed"] = True
            except BaseException:  # noqa: BLE001 - the view is still set
                not_set.append("zoom_extents")

        _try(lambda: doc.Regen(AC_ALL_VIEWPORTS))
        # Read the style back from the viewport (#59, D-86): only the plug-in
        # can, as COM has no visual style on a model viewport.
        found, why = plugin_read("current_view")
        if found is None:
            result["visual_style_found"] = None
            result["visual_style_note"] = f"The style could not be read back ({why}). autocad_preview shows it."
        else:
            seen = found.get("visual_style")
            result["visual_style_found"] = seen
            if found.get("perspective"):
                result["perspective"] = True
            took = seen is not None and style_key(seen) == style
            if style is not None and not took and not any(item.startswith("visual_style") for item in not_set):
                not_set.append(
                    f"visual_style (asked for '{style}', the viewport reads "
                    + (f"'{seen}')" if seen is not None else "no style)")
                )
        if not_set:
            result["not_set"] = not_set
        return result

    return dumps(await run(work))


def style_key(name: str) -> str:
    """A visual style's name as this server spells it: AutoCAD's 'Shades of Gray' is 'shades of gray'."""
    return str(name).strip().lower()


def _still_asking(doc: Any) -> bool:
    """Whether a command is still waiting once VSCURRENT has had its moment to finish."""
    deadline = time.monotonic() + VSCURRENT_WAIT_S
    while _try(lambda: int(doc.GetVariable("CMDACTIVE")), 0):
        if time.monotonic() >= deadline:
            return True
        time.sleep(VSCURRENT_POLL_S)
    return False


# ---------------------------------------------------------------------------
# Cutting and checking
# ---------------------------------------------------------------------------


def plane_from(
    kind: str,
    through: list[float],
    normal: list[float] | None,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    """Three points on a cutting plane, from a named plane or a normal.

    AutoCAD's ``SliceSolid`` wants three points. Nobody thinks in three points:
    a modeller says "cut it horizontally at this level" or "section it on the
    centre line". This turns those into the three points, keeping the arithmetic
    out of AutoCAD so it can be checked.
    """
    x, y, z = (float(through[0]), float(through[1]),
               float(through[2]) if len(through) > 2 else 0.0)
    if kind == "horizontal":  # cut at a level: the XY plane through the point
        return (x, y, z), (x + 1.0, y, z), (x, y + 1.0, z)
    if kind == "vertical_x":  # a plane containing the X axis: cuts front to back
        return (x, y, z), (x + 1.0, y, z), (x, y, z + 1.0)
    if kind == "vertical_y":  # a plane containing the Y axis: cuts left to right
        return (x, y, z), (x, y + 1.0, z), (x, y, z + 1.0)
    if kind == "normal":
        if not normal or len(normal) < 3:
            raise AutocadError("plane='normal' needs 'normal' as [x, y, z], the direction the plane faces.")
        nx, ny, nz = (float(v) for v in normal[:3])
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length < 1e-12:
            raise AutocadError("'normal' cannot be all zeros — it is the direction the plane faces.")
        nx, ny, nz = nx / length, ny / length, nz / length
        # Any vector not parallel to the normal gives a first in-plane axis.
        other = (0.0, 0.0, 1.0) if abs(nz) < 0.9 else (1.0, 0.0, 0.0)
        ux = ny * other[2] - nz * other[1]
        uy = nz * other[0] - nx * other[2]
        uz = nx * other[1] - ny * other[0]
        scale = math.sqrt(ux * ux + uy * uy + uz * uz)
        ux, uy, uz = ux / scale, uy / scale, uz / scale
        # The second axis is perpendicular to both, so the three points span the plane.
        vx = ny * uz - nz * uy
        vy = nz * ux - nx * uz
        vz = nx * uy - ny * ux
        return (x, y, z), (x + ux, y + uy, z + uz), (x + vx, y + vy, z + vz)
    raise AutocadError(f"Unknown plane '{kind}'. Use horizontal, vertical_x, vertical_y or normal.")


@mcp.tool(name="autocad_slice_solid", **tool_meta("Slice A Solid"))
@tool_errors
async def autocad_slice_solid(
    handles: Annotated[list[str], Field(min_length=1, description="The solids to cut. Each is cut by the same plane.")],
    through: Annotated[list[float], Field(description="A point the cutting plane passes through, as [x, y] or [x, y, z]. For a horizontal cut this is the level.")],
    plane: Annotated[
        Literal["horizontal", "vertical_x", "vertical_y", "normal"],
        Field(
            default="horizontal",
            description=(
                "Which way the plane lies. 'horizontal' cuts at a level (the usual one for "
                "a plan section). 'vertical_x' cuts front to back, 'vertical_y' left to "
                "right. 'normal' lets you give any direction with 'normal'."
            ),
        ),
    ] = "horizontal",
    normal: Annotated[list[float] | None, Field(default=None, description="For plane='normal': the direction the plane faces, as [x, y, z].")] = None,
    keep: Annotated[
        Literal["both", "positive", "negative"],
        Field(
            default="both",
            description=(
                "Which side to keep. 'both' keeps the two halves as separate solids, which "
                "is what you want to look inside something. 'positive' keeps the side the "
                "plane's normal points to; 'negative' keeps the other."
            ),
        ),
    ] = "both",
    layer: Annotated[str | None, LAYER_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Cut a solid with a plane — a real section through a model.

    This is how a 3D model becomes a section drawing: slice it at the level or
    on the line the section mark shows, then look at the cut face. Keeping both
    halves lets you move one aside and see inside.

    The plane is given the way a drafter says it — "horizontally at this level"
    — and the three points AutoCAD actually wants are worked out here.

    One undo step.

    Args:
        handles (list[str]): the solids to cut.
        through (list[float]): a point on the cutting plane.
        plane (str): horizontal, vertical_x, vertical_y or normal.
        normal (Optional[list[float]]): the plane's direction, for plane='normal'.
        keep (str): both, positive or negative.
        layer (Optional[str]): layer for any new half.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"sliced": int, "plane": {"kind", "points"},
             "results": [{"handle", "kept_handle", "new_handle", "volume_before",
             "volume_after", "new_volume"}], "failed": [{"handle", "reason"}]}

    Examples:
        - Use when: "section that model at 1500 above floor level" —
          plane='horizontal', through=[0, 0, 1500].
        - Use when: "cut this fitting in half so I can see the bore" —
          plane='vertical_y', keep='both'.
        - Don't use when: you want a 2D section to dimension — slice it, then
          look at the cut face with autocad_set_3d_view, or take the outline
          off it. SectionSolid is not used here: its ActiveX signature is not
          documented anywhere we could check, and guessing it would risk your
          model.
    """
    points_spec = plane
    with_normal = normal

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        if layer:
            ensure_layer(doc, layer)
        # Worked out in the caller's terms, then each point taken to the world:
        # on a turned UCS 'vertical_x' holds the UCS X axis and 'normal' faces
        # the way the modeller means.
        plane_points = plane_from(points_spec, list(as_vec3(through)), with_normal)
        p1, p2, p3 = (tuple(world_coords(p, ucs)) for p in plane_points)

        results: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        with undo_mark(doc):
            for handle in handles:
                entity = resolve_handle(doc, handle)
                kind = short_type(entity)
                if kind != "3dsolid":
                    failed.append({"handle": handle, "reason": f"{kind} is not a 3D solid"})
                    continue
                before = _try(lambda e=entity: float(e.Volume))
                try:
                    # The fourth argument asks AutoCAD to keep both halves; it
                    # hands back the new one when it does.
                    made = entity.SliceSolid(apoint(*p1), apoint(*p2), apoint(*p3), keep == "both")
                except BaseException as exc:  # noqa: BLE001
                    failed.append({"handle": handle, "reason": com_message(exc)})
                    continue
                row: dict[str, Any] = {
                    "handle": handle,
                    "volume_before": round(before, 6) if before is not None else None,
                    "volume_after": _try(lambda e=entity: round(float(e.Volume), 6)),
                }
                other = made[0] if isinstance(made, tuple) and made else made
                if other is not None and keep == "both":
                    if layer:
                        _write(other, "Layer", layer.strip())
                    row["new_handle"] = _try(lambda o=other: str(o.Handle))
                    row["new_volume"] = _try(lambda o=other: round(float(o.Volume), 6))
                results.append(row)

        payload: dict[str, Any] = {
            "sliced": len(results),
            "plane": {"kind": points_spec, "points": [list(p1), list(p2), list(p3)]},
            "keep": keep,
            "results": results,
        }
        if failed:
            payload["failed"] = failed
        if not results:
            raise AutocadError(
                "Nothing was sliced. "
                + "; ".join(f"{f['handle']}: {f['reason']}" for f in failed)
            )
        return payload

    return dumps(await run(work))


@mcp.tool(name="autocad_check_interference", **tool_meta("Check For Clashes"))
@tool_errors
async def autocad_check_interference(
    handles: Annotated[list[str], Field(min_length=1, description="The first set of solids — say, the ductwork.")],
    against: Annotated[
        list[str] | None,
        Field(
            default=None,
            description=(
                "The second set — say, the structure. Every solid in the first set is "
                "checked against every solid here. Leave it out to check the first set "
                "against itself, which finds things clashing inside one trade."
            ),
        ),
    ] = None,
    create_solids: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Draw the overlap itself as a new solid, so you can see and measure how bad "
                "each clash is. Off by default: on a big model it makes a lot of objects."
            ),
        ),
    ] = False,
    layer: Annotated[str | None, Field(default=None, description="Layer for the clash solids. Give one so they are easy to find and delete — e.g. 'Z-CLASH'.")] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    limit: Annotated[int, Field(default=200, ge=1, le=5000, description="Stop after this many clashes, so a bad model does not run for ever.")] = 200,
) -> str:
    """Find where solids run through each other — a clash check.

    The question every coordination meeting asks: does the duct hit the beam?
    This pairs up the two sets and reports every overlap, with the volume of
    the overlap so the worst ones can be dealt with first. With
    ``create_solids`` it also draws each overlap, which is the quickest way to
    see what is actually fouling.

    Solids only — AutoCAD's own check does not handle surfaces or meshes, and
    anything else in the lists is reported rather than quietly skipped.

    It needs the **Changes** padlock even to report, because AutoCAD builds the
    overlap as a real solid to measure it. With ``create_solids`` off, each one
    is removed again as soon as its volume is read, so nothing is left behind —
    but the drawing was written to, and a tool that can write says so (D-31:
    the level belongs to the tool, not to the call it happens to make).

    One undo step.

    Args:
        handles (list[str]): the first set of solids.
        against (Optional[list[str]]): the second set; omit to check within the first.
        create_solids (bool): draw the overlaps. Default false.
        layer (Optional[str]): layer for the clash solids.
        color (Optional[str | int]): colour for them.
        limit (int): stop after this many clashes.

    Returns:
        str: JSON: {"checked_pairs": int, "clashes": int, "clear": bool,
             "worst": {...} | null,
             "found": [{"a", "b", "volume", "handle", "bounding_box"}],
             "skipped": [{"handle", "reason"}], "stopped_early": bool}

    Examples:
        - Use when: "does this ductwork hit the steel" — handles=the ducts,
          against=the beams.
        - Use when: "show me the clashes" — create_solids=true, layer='Z-CLASH',
          then autocad_set_3d_view and autocad_preview.
        - Use when: before issuing a model: an empty 'found' with "clear": true
          is the answer you want.
        - Don't use when: the parts are 2D lines, not solids — this reads
          nothing from them. Clash checking needs a model.
    """
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if layer:
            ensure_layer(doc, layer)

        skipped: list[dict[str, Any]] = []

        def solids_of(names: list[str]) -> list[tuple[str, Any]]:
            out = []
            for entity in resolve_handles(doc, names):
                handle = str(entity.Handle)
                kind = short_type(entity)
                if kind == "3dsolid":
                    out.append((handle, entity))
                else:
                    skipped.append({"handle": handle, "reason": f"{kind} is not a 3D solid"})
            return out

        first = solids_of(handles)
        second = solids_of(against) if against else first
        if not first or not second:
            raise AutocadError(
                "A clash check needs 3D solids on both sides. "
                + (f"Skipped: {skipped}" if skipped else "Nothing given was a solid.")
            )

        # Against itself, each pair is checked once rather than twice.
        same = against is None
        pairs = []
        for i, (ha, ea) in enumerate(first):
            for j, (hb, eb) in enumerate(second):
                if same and j <= i:
                    continue
                if ha == hb:
                    continue
                pairs.append((ha, ea, hb, eb))

        found: list[dict[str, Any]] = []
        stopped = False
        with undo_mark(doc):
            for ha, ea, hb, eb in pairs:
                if len(found) >= limit:
                    stopped = True
                    break
                try:
                    made = ea.CheckInterference(eb, bool(create_solids))
                except BaseException as exc:  # noqa: BLE001
                    skipped.append({"handle": f"{ha}+{hb}", "reason": com_message(exc)})
                    continue
                # pywin32 hands back the [out] flag alongside the solid when the
                # method declares one, so both shapes have to be understood.
                overlap, interferes = made, None
                if isinstance(made, tuple):
                    overlap = made[0] if made else None
                    interferes = next((v for v in made[1:] if isinstance(v, bool)), None)
                clash = bool(interferes) if interferes is not None else overlap is not None
                if not clash:
                    continue
                row: dict[str, Any] = {"a": ha, "b": hb}
                if overlap is not None:
                    row["volume"] = _try(lambda o=overlap: round(float(o.Volume), 6))
                    if create_solids:
                        if layer:
                            _write(overlap, "Layer", layer.strip())
                        if aci is not None:
                            _write(overlap, "Color", aci)
                        row["handle"] = _try(lambda o=overlap: str(o.Handle))
                        low, high = _try(lambda o=overlap: o.GetBoundingBox(), (None, None))
                        if low is not None:
                            row["bounding_box"] = {"min": point_to_list(low), "max": point_to_list(high)}
                    else:
                        # Not asked for, so it must not be left in the drawing.
                        _try(lambda o=overlap: o.Delete())
                found.append(row)

        with_volume = [r for r in found if r.get("volume")]
        payload: dict[str, Any] = {
            "checked_pairs": len(pairs),
            "clashes": len(found),
            "clear": not found,
            "found": found,
            "worst": max(with_volume, key=lambda r: r["volume"]) if with_volume else None,
            "solids_drawn": bool(create_solids and found),
        }
        if stopped:
            payload["stopped_early"] = True
            payload["hint"] = (
                f"Stopped at {limit} clashes; there are more. Fix these, or raise 'limit'."
            )
        if skipped:
            payload["skipped"] = skipped
        return payload

    return dumps(await run(work))


@mcp.tool(name="autocad_transform_3d", **tool_meta("Move Rotate Or Mirror In 3D"))
@tool_errors
async def autocad_transform_3d(
    handles: Annotated[list[str], Field(min_length=1, description="What to move. Any entities, not only solids.")],
    operation: Annotated[
        Literal["move", "rotate", "mirror", "array"],
        Field(
            description=(
                "'move' shifts by a displacement that can include Z. 'rotate' turns about "
                "any axis in space, not just the Z axis. 'mirror' reflects in a plane. "
                "'array' copies up in levels, for floors of a building."
            )
        ),
    ],
    displacement: Annotated[list[float] | None, Field(default=None, description="Move: [dx, dy, dz].")] = None,
    axis_point: Annotated[list[float] | None, Field(default=None, description="Rotate: a point on the axis, as [x, y, z].")] = None,
    axis_direction: Annotated[list[float] | None, Field(default=None, description="Rotate: which way the axis runs, e.g. [1,0,0] to tip something about the X axis.")] = None,
    angle: Annotated[float | None, Field(default=None, description="Rotate: degrees about the axis, right-hand rule.")] = None,
    plane_point: Annotated[list[float] | None, Field(default=None, description="Mirror: a point the mirror plane passes through.")] = None,
    plane_normal: Annotated[list[float] | None, Field(default=None, description="Mirror: the direction the mirror plane faces, e.g. [0,0,1] to flip upside down.")] = None,
    keep_original: Annotated[bool, Field(default=True, description="Mirror: keep the original as well as the reflection. Default true, as AutoCAD's MIRROR3D does.")] = True,
    levels: Annotated[int | None, Field(default=None, ge=2, le=200, description="Array: how many copies in total, counting the original.")] = None,
    level_spacing: Annotated[float | None, Field(default=None, description="Array: the rise between copies. A floor-to-floor height.")] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Move, rotate, mirror or array in three dimensions.

    The ordinary modify tools work on the flat: they move in XY and rotate
    about Z. A model needs more — tip a brace about the X axis, mirror a
    handed assembly in a vertical plane, stack a floor layout up through a
    building. That is this.

    One undo step, however many objects.

    Args:
        handles (list[str]): what to transform.
        operation (str): move, rotate, mirror or array.
        displacement (Optional[list[float]]): move: [dx, dy, dz].
        axis_point / axis_direction (Optional[list[float]]): rotate: the axis.
        angle (Optional[float]): rotate: degrees.
        plane_point / plane_normal (Optional[list[float]]): mirror: the plane.
        keep_original (bool): mirror: keep the original too. Default true.
        levels (Optional[int]): array: how many in total.
        level_spacing (Optional[float]): array: the rise between them.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"operation", "count": int, "handles": [str],
             "new_handles": [str], "failed": [{"handle", "reason"}]}

    Examples:
        - Use when: "lift that whole frame 3500 up" — move,
          displacement=[0, 0, 3500].
        - Use when: "tip that brace 30 degrees about the X axis" — rotate,
          axis_point, axis_direction=[1,0,0], angle=30.
        - Use when: "mirror this handed bracket about the horizontal plane at
          2000" — mirror, plane_point=[0,0,2000], plane_normal=[0,0,1].
        - Use when: "copy this floor up 12 times at 3600" — array, levels=13,
          level_spacing=3600.
        - Don't use when: everything stays flat — autocad_move_entities,
          autocad_rotate_entities and autocad_mirror_entities are simpler and
          read better for 2D work.
    """
    if operation == "move" and (not displacement or len(displacement) < 3):
        raise AutocadError("A 3D move needs displacement as [dx, dy, dz]. For a flat move use autocad_move_entities.")
    if operation == "rotate":
        if angle is None or not axis_point or not axis_direction:
            raise AutocadError("A 3D rotate needs angle, axis_point and axis_direction (e.g. [1,0,0]).")
        if len(axis_direction) < 3 or all(abs(float(v)) < 1e-12 for v in axis_direction[:3]):
            raise AutocadError("axis_direction needs [x, y, z] and cannot be all zeros.")
    if operation == "mirror":
        if not plane_point or not plane_normal:
            raise AutocadError("A 3D mirror needs plane_point and plane_normal (e.g. [0,0,1] for a horizontal mirror).")
        if len(plane_normal) < 3 or all(abs(float(v)) < 1e-12 for v in plane_normal[:3]):
            raise AutocadError("plane_normal needs [x, y, z] and cannot be all zeros.")
    if operation == "array" and (levels is None or level_spacing is None or abs(float(level_spacing)) < 1e-9):
        raise AutocadError("A 3D array needs levels (2 or more) and a level_spacing that is not zero.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        entities = resolve_handles(doc, handles)
        done: list[str] = []
        new: list[str] = []
        failed: list[dict[str, Any]] = []

        with undo_mark(doc):
            for entity in entities:
                handle = str(entity.Handle)
                try:
                    if operation == "move":
                        dx, dy, dz = world_direction(displacement, ucs)
                        entity.Move(apoint(0.0, 0.0, 0.0), apoint(dx, dy, dz))
                    elif operation == "rotate":
                        ax, ay, az = world_coords(axis_point, ucs)
                        dx, dy, dz = world_direction(axis_direction, ucs)
                        entity.Rotate3D(
                            apoint(ax, ay, az),
                            apoint(ax + dx, ay + dy, az + dz),
                            rad(angle),
                        )
                    elif operation == "mirror":
                        p1, p2, p3 = plane_from(
                            "normal", list(world_coords(plane_point, ucs)), world_direction(plane_normal, ucs)
                        )
                        made = entity.Mirror3D(apoint(*p1), apoint(*p2), apoint(*p3))
                        copy = made[0] if isinstance(made, tuple) and made else made
                        if copy is not None:
                            new.append(str(copy.Handle))
                        if not keep_original:
                            entity.Delete()
                    else:
                        for step in range(1, int(levels)):
                            copy = entity.Copy()
                            copy.Move(apoint(0.0, 0.0, 0.0),
                                      apoint(0.0, 0.0, float(level_spacing) * step))
                            new.append(str(copy.Handle))
                except BaseException as exc:  # noqa: BLE001
                    failed.append({"handle": handle, "reason": com_message(exc)})
                    continue
                done.append(handle)

        if not done:
            raise AutocadError(
                "Nothing was transformed. "
                + "; ".join(f"{f['handle']}: {f['reason']}" for f in failed)
            )
        payload: dict[str, Any] = {
            "operation": operation,
            "count": len(done),
            "handles": done,
        }
        if new:
            payload["new_handles"] = new
            payload["created"] = len(new)
        if failed:
            payload["failed"] = failed
        return payload

    return dumps(await run(work))
