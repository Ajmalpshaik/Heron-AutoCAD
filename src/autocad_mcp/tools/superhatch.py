"""Super hatch: a block, an image, an xref or a wipeout repeated inside a closed outline (D-40, D-95).

Express Tools' SUPERHATCH has no COM call, so the Heron plug-in builds it:
a new block holding the grid of tiles, inserted once and clipped to the
outline the way XCLIP clips. One object to move, erase or Ctrl+Z. An image or
a wipeout is first made into a tile block of its own; an xref is the tile as
it is (attached first when a .dwg is given).
"""

from __future__ import annotations

import math
from pathlib import Path
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
    block: Annotated[
        str | None,
        Field(default=None, description="The block to repeat, as autocad_list_blocks names it: a paver, a ceiling tile, a grating panel. Give one tile: block, image, xref or wipeout."),
    ] = None,
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
    image: Annotated[
        str | None,
        Field(default=None, description="An image file to repeat instead (.png, .jpg, .tif, .bmp): a stone, a grating photo. Needs image_size."),
    ] = None,
    image_size: Annotated[
        list[float] | None,
        Field(default=None, description="The image tile's [width] or [width, height] in drawing units. With the width alone the height keeps the image's proportions."),
    ] = None,
    xref: Annotated[
        str | None,
        Field(default=None, description="An xref to repeat instead: the name of one attached, or a .dwg file to attach (a standard tile drawing kept in its own file)."),
    ] = None,
    wipeout: Annotated[
        str | None,
        Field(default=None, description="A wipeout to repeat instead, by handle (autocad_add_wipeout makes one): a pattern of masks over what is under it."),
    ] = None,
    name: Annotated[str | None, Field(default=None, description="Name for the new block that holds the tiles. Omit for SUPERHATCH-1, -2...")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Fill a closed outline with a block, an image, an xref or a wipeout repeated like a hatch (SUPERHATCH).

    Paving, cladding panels, a tiled ceiling, a grating: any block, laid in a
    grid from an origin, turned to an angle, and clipped to the outline the
    way XCLIP clips. As Express Tools offers, the tile can instead be an image
    file, an xref (attached from its .dwg if need be) or a wipeout. The result
    is one block reference: move, copy or erase it as one, and one Ctrl+Z
    takes it away. The tiles sit on layer 0, ByBlock, so the reference's layer
    and colour are what shows.

    One undo step.

    Args:
        boundary (str): the closed outline, flat in plan.
        block (Optional[str]): the block to repeat.
        image (Optional[str]): or an image file, with image_size.
        image_size (Optional[list[float]]): [width] or [width, height].
        xref (Optional[str]): or an xref, by name or .dwg file.
        wipeout (Optional[str]): or a wipeout, by handle.
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
             "tile_kind": "block" | "image" | "xref" | "wipeout",
             "tiles": int, "spacing": [float, float], "boundary": str,
             "tile_block_made": bool, "xref_attached": bool, "verified": bool}

    Examples:
        - Use when: "fill the terrace outline with the 600 x 300 paver block"
          — boundary, block='PAVER'.
        - Use when: "super hatch the ceiling with the 600 tile set out from
          the room centre" — origin at the centre.
        - Use when: "lay the grating panels at 45 degrees in this pit".
        - Use when: "fill the plaza with this stone photo, 600 wide" —
          image='C:/Textures/stone.jpg', image_size=[600].
        - Use when: "super hatch the ceiling with the tile drawing
          CT-600.dwg" — xref='C:/Standards/CT-600.dwg'.
        - Use when: "mask a grid of openings with this wipeout" — wipeout=the
          wipeout's handle, spacing=[...].
        - Don't use when: a normal hatch pattern does it - autocad_add_hatch,
          or make the pattern with autocad_create_hatch_pattern.

    Error Handling:
        - An open, tilted or non-curve outline is refused before anything is
          made.
        - A block that is not in the drawing points at autocad_list_blocks.
        - More than 10,000 tiles (2,000 image tiles) is refused: make the
          spacing or scale bigger.
        - No tile, or more than one of block / image / xref / wipeout, is
          refused; so is an image or .dwg file that is not there.
    """
    tiles = {k: v for k, v in (("block", block), ("image", image), ("xref", xref), ("wipeout", wipeout)) if v}
    if len(tiles) != 1:
        raise AutocadError(
            "Give one tile to repeat: block, image, xref or wipeout"
            + (f" - got {', '.join(tiles)}." if tiles else " - got none.")
        )
    kind, tile = next(iter(tiles.items()))
    tile = str(tile).strip()
    if kind == "image":
        if not image_size or len(image_size) > 2 or min(image_size) <= 0:
            raise AutocadError("An image tile needs image_size: [width] or [width, height], above zero, in drawing units.")
        if not Path(tile).is_file():
            raise AutocadError(f"There is no image at '{tile}'. Give the full path to a .png, .jpg, .tif or .bmp.")
    elif image_size is not None:
        raise AutocadError("image_size is for an image tile only.")
    if kind == "xref" and (tile.lower().endswith(".dwg") or "/" in tile or "\\" in tile) and not Path(tile).is_file():
        raise AutocadError(f"There is no drawing at '{tile}'. Give the full path to the .dwg, or the name of an attached xref.")
    if spacing is not None and (len(spacing) != 2 or min(spacing) <= 0):
        raise AutocadError("spacing must be two sizes above zero, [along, across], e.g. [600, 300].")
    if origin is not None and len(origin) < 2:
        raise AutocadError("origin must be [x, y].")
    holder = validate_name(name, "block") if name else None
    # The layer goes to the plug-in as a name it will make: checked here first, so a
    # line break or a '|' is refused before anything is sent (D-139).
    layer = validate_name(layer, "layer") if layer else None

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = not_flipped(ucs_for(doc, coords), "a super hatch's tiles")
        args = {
            "boundary": boundary,
            # A block is the plug-in's default, so a block hatch asks exactly as before.
            "tile_kind": None if kind == "block" else kind,
            kind: tile,
            "image_size": [float(v) for v in image_size] if image_size else None,
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
