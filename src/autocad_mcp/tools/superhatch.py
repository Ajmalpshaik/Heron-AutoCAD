"""Super hatch: a block repeated as a hatch inside a closed outline (D-40).

Express Tools' SUPERHATCH has no COM call, so the Heron plug-in builds it:
a new block holding the grid of tiles, inserted once and clipped to the
outline the way XCLIP clips. One object to move, erase or Ctrl+Z.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..acad.tables import validate_name
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta
from ._shared import (
    COLOR_OPT,
    COORDS_OPT,
    LAYER_OPT,
    in_plugin,
    not_flipped,
    plugin_created,
    ucs_for,
    world_angle,
    world_coords,
)


@mcp.tool(name="autocad_super_hatch", **tool_meta("Super Hatch With A Block"))
@tool_errors
async def autocad_super_hatch(
    boundary: Annotated[str, Field(min_length=1, description="The closed outline to fill (polyline, circle, ellipse or spline), drawn flat in plan.")],
    block: Annotated[str, Field(min_length=1, description="The block to repeat, as autocad_list_blocks names it: a paver, a ceiling tile, a grating panel.")],
    spacing: Annotated[
        list[float] | None,
        Field(default=None, description="[along, across] distance between tiles. Omit to butt them up by the block's own size."),
    ] = None,
    origin: Annotated[
        list[float] | None,
        Field(default=None, description="[x, y] where one tile's base point sits, to set out the grid. Omit to start at the outline's lower-left corner."),
    ] = None,
    angle: Annotated[float, Field(default=0.0, description="Turn of the grid and the tiles, in DEGREES counter-clockwise.")] = 0.0,
    scale: Annotated[float, Field(default=1.0, gt=0, description="Size of each tile against the block as drawn.")] = 1.0,
    name: Annotated[str | None, Field(default=None, description="Name for the new block that holds the tiles. Omit for SUPERHATCH-1, -2...")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Fill a closed outline with a block repeated like a hatch (Express Tools' SUPERHATCH).

    Paving, cladding panels, a tiled ceiling, a grating: any block, laid in a
    grid from an origin, turned to an angle, and clipped to the outline the
    way XCLIP clips. The result is one block reference: move, copy or erase it
    as one, and one Ctrl+Z takes it away. The tiles sit on layer 0, ByBlock,
    so the reference's layer and colour are what shows.

    One undo step.

    Args:
        boundary (str): the closed outline, flat in plan.
        block (str): the block to repeat.
        spacing (Optional[list[float]]): [along, across].
        origin (Optional[list[float]]): where the grid is set out from.
        angle (float): degrees counter-clockwise.
        scale (float): tile size against the block as drawn.
        name (Optional[str]): name of the block that holds the tiles.
        layer (Optional[str]): layer for the result, created if missing.
        color (Optional[str|int]): its colour.
        coords (str): 'world' or 'ucs' for origin and angle.

    Returns:
        str: JSON: {"created": true, "handle": str, "block": str, "tile": str,
             "tiles": int, "spacing": [float, float], "boundary": str,
             "verified": bool}

    Examples:
        - Use when: "fill the terrace outline with the 600 x 300 paver block"
          — boundary, block='PAVER'.
        - Use when: "super hatch the ceiling with the 600 tile set out from
          the room centre" — origin at the centre.
        - Use when: "lay the grating panels at 45 degrees in this pit".
        - Don't use when: a normal hatch pattern does it - autocad_add_hatch,
          or make the pattern with autocad_create_hatch_pattern.

    Error Handling:
        - An open, tilted or non-curve outline is refused before anything is
          made.
        - A block that is not in the drawing points at autocad_list_blocks.
        - More than 10,000 tiles is refused: make the spacing or scale bigger.
    """
    if spacing is not None and (len(spacing) != 2 or min(spacing) <= 0):
        raise AutocadError("spacing must be two sizes above zero, [along, across], e.g. [600, 300].")
    if origin is not None and len(origin) < 2:
        raise AutocadError("origin must be [x, y].")
    holder = validate_name(name, "block") if name else None

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = not_flipped(ucs_for(doc, coords), "a super hatch's tiles")
        args = {
            "boundary": boundary,
            "block": block,
            "spacing": [float(v) for v in spacing] if spacing else None,
            "origin": world_coords(origin, ucs)[:2] if origin else None,
            "angle": math.radians(world_angle(angle, ucs) or 0.0),
            "scale": float(scale),
            "name": holder,
            "layer": layer,
            "color": to_aci(color),
        }
        return plugin_created(doc, in_plugin("super_hatch", args, "Super hatch"))

    return dumps(await run(work))
