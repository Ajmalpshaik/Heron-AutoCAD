"""A pyramid and a wall along a path, made by the Heron plug-in (D-40, D-112).

COM's ``Add*`` calls have no pyramid and no polysolid, so these ask the plug-in
to make them through AutoCAD's .NET API: the pyramid with ``CreatePyramid``,
the polysolid by offsetting the path to each face of the wall and raising the
outline (AutoCAD's .NET API has no polysolid call). Each is one transaction
inside AutoCAD: it all lands or none of it does.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta
from ._shared import (
    COLOR_OPT,
    COORDS_OPT,
    LAYER_OPT,
    in_plugin,
    plugin_created,
    ucs_for,
    world_angle,
    world_coords,
)

# A wall's path is "level" when its points are this close in Z: a hair, not a slope.
LEVEL = 1e-6


@mcp.tool(name="autocad_add_pyramid", **tool_meta("Add A Solid Pyramid"))
@tool_errors
async def autocad_add_pyramid(
    base: Annotated[
        list[float],
        Field(min_length=2, max_length=3, description="The centre of the pyramid's base (where it stands), as [x, y] or [x, y, z]."),
    ],
    radius: Annotated[
        float,
        Field(gt=0, description="The base's size from its centre: to the middle of a side by default (300 makes a 600 x 600 square base)."),
    ],
    height: Annotated[float, Field(gt=0, description="Height, straight up.")],
    sides: Annotated[int, Field(default=4, ge=3, le=32, description="Number of sides, 3 to 32 as PYRAMID allows. 4 is a square base.")] = 4,
    top_radius: Annotated[
        float,
        Field(
            default=0.0,
            ge=0,
            description=(
                "0 for a point at the top. Above 0 cuts it flat there (a frustum), measured like radius. "
                "Bigger than radius makes a hopper: wide at the top, narrow at the bottom."
            ),
        ),
    ] = 0.0,
    radius_to: Annotated[
        Literal["side", "corner"],
        Field(default="side", description="'side' (default): radius is to the middle of a side, as PYRAMID's default. 'corner': to a corner."),
    ] = "side",
    rotation: Annotated[
        float,
        Field(default=0.0, description="Turn about its axis in degrees, anticlockwise. 0 puts one side square to the front, as a box sits."),
    ] = 0.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Make a solid pyramid or frustum (PYRAMID), standing on the centre of its base.

    3 to 32 sides; a point at the top, or a flat top with top_radius. A top
    wider than the base makes a hopper. One side faces the front unless
    rotation turns it. The result gives both radii (to a side and to a
    corner), the volume AutoCAD measured and the volume the sizes should give.

    One undo step.

    Args:
        base (list[float]): centre of the base.
        radius (float): base size, to a side (or a corner with radius_to).
        height (float): height.
        sides (int): 3 to 32.
        top_radius (float): 0 for a point; above 0 for a flat top.
        radius_to (str): 'side' or 'corner'.
        rotation (float): degrees about the axis.
        layer (Optional[str]): layer, created if missing.
        color (Optional[str|int]): colour.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "3dsolid",
             "sides": int, "base": [x, y, z], "height": float, "radius": float,
             "corner_radius": float, "top_radius": float,
             "top_corner_radius": float, "rotation": float,
             "volume": float, "expected_volume": float, "verified": bool}

    Examples:
        - Use when: "a 600 x 600 pyramid 900 high on the roof" — radius=300,
          height=900.
        - Use when: "a hopper 1200 square at the top with a 300 square outlet,
          900 deep" — radius=150, top_radius=600, height=900.
        - Use when: "a hexagonal cap, 400 across the corners, 250 high" —
          sides=6, radius=200, radius_to='corner'.
        - Don't use when: the shape is a box, cylinder, cone or wedge —
          autocad_add_solid.
        - Don't use when: the shape changes from one outline to another (square
          to round) — autocad_loft.

    Error Handling:
        - Sides outside 3 to 32, or sizes not above zero, are refused before
          AutoCAD is asked.
        - Needs the Heron plug-in with this operation; an older one says to
          update.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        turn = world_angle(float(rotation), ucs) or 0.0
        args = {
            "base": world_coords(base, ucs),
            "radius": float(radius),
            "height": float(height),
            "sides": int(sides),
            "top_radius": float(top_radius),
            "radius_to": radius_to,
            "rotation": math.radians(turn),
            "layer": layer,
            "color": to_aci(color),
        }
        payload = plugin_created(doc, in_plugin("add_pyramid", args, "Making a pyramid"))
        payload["rotation"] = float(rotation)
        return payload

    return dumps(await run(work))


@mcp.tool(name="autocad_add_polysolid", **tool_meta("Add A Wall Solid Along A Path (Polysolid)"))
@tool_errors
async def autocad_add_polysolid(
    width: Annotated[float, Field(gt=0, description="The wall's thickness.")],
    height: Annotated[float, Field(gt=0, description="The wall's height, straight up from the path.")],
    path: Annotated[
        str | None,
        Field(default=None, description="A line, arc, circle, polyline or spline drawn flat in plan, by handle. It is kept."),
    ] = None,
    points: Annotated[
        list[list[float]] | None,
        Field(default=None, min_length=2, description="Instead of path: the wall's line as points [[x, y], ...], all at one Z. Straight runs only."),
    ] = None,
    closed: Annotated[bool, Field(default=False, description="With points: close the wall back to the first point (a ring).")] = False,
    side: Annotated[
        Literal["center", "left", "right", "inside", "outside"],
        Field(
            default="center",
            description=(
                "Where the wall sits on the path: 'center' (down its middle), 'left' or 'right' (looking along the path "
                "from its start), or for a closed path 'inside' or 'outside' it."
            ),
        ),
    ] = "center",
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Make a wall-like solid of a width and height along a path (POLYSOLID).

    Follows a line, arc, circle, polyline or spline drawn flat in plan, or a
    list of points; the wall goes straight up from the path's level. The path
    is kept. AutoCAD's .NET API has no polysolid call, so Heron builds the same
    shape: the path offset to each face of the wall, closed into one outline
    and raised by the height.

    One undo step.

    Args:
        width (float): wall thickness.
        height (float): wall height.
        path (Optional[str]): the path curve, by handle.
        points (Optional[list[list[float]]]): or the path as points.
        closed (bool): with points, close the ring.
        side (str): center, left, right, inside or outside.
        layer (Optional[str]): layer, created if missing.
        color (Optional[str|int]): colour.
        coords (str): 'world' or 'ucs' for points.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "3dsolid",
             "path": str, "width": float, "height": float, "side": str,
             "closed": bool, "elevation": float, "path_length": float,
             "volume": float, "verified": bool}

    Examples:
        - Use when: "a 200 thick, 1200 high bund wall round the tank area" —
          path=the outline, side='inside', width=200, height=1200.
        - Use when: "a 150 x 100 kerb along this polyline" — width=150,
          height=100.
        - Use when: "a parapet 250 wide 1100 high along the roof edge" — the
          edge as points.
        - Don't use when: the section is not a plain rectangle, or the route
          climbs — autocad_extrude_profile sweeps any section along any route.
        - Don't use when: it is one straight block — autocad_add_solid box.

    Error Handling:
        - Both path and points, or neither, are refused.
        - A path not flat in plan is refused: the wall goes straight up.
        - A path that turns tighter than the wall is wide, or crosses itself,
          is refused with nothing changed.
        - 'inside' or 'outside' on an open path is refused.
    """
    if (path is None) == (points is None):
        raise AutocadError("Give the wall's path as a curve's handle (path) or as points, not both and not neither.")
    if path is not None and closed:
        raise AutocadError("closed is for points. A path curve is closed or open as drawn: close the polyline itself.")
    if any(len(p) not in (2, 3) for p in points or []):
        raise AutocadError("Each point of the wall's path is [x, y] or [x, y, z].")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        args: dict[str, Any] = {"width": float(width), "height": float(height), "side": side, "layer": layer, "color": to_aci(color)}
        if path is not None:
            args["path"] = path
        else:
            ucs = ucs_for(doc, coords)
            world = [world_coords(p, ucs) for p in points or []]
            level = world[0][2]
            if any(abs(p[2] - level) > LEVEL * max(1.0, abs(level)) for p in world):
                raise AutocadError(
                    "The wall's points are not all at one Z. A polysolid goes straight up from a level path; for a "
                    "route that climbs, sweep a section with autocad_extrude_profile."
                )
            args["points"] = world
            args["closed"] = closed
        return plugin_created(doc, in_plugin("add_polysolid", args, "Making a polysolid"))

    return dumps(await run(work))
