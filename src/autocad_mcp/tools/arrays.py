"""Associative arrays: ARRAY's editable grid, ring and path array (D-110).

COM's ArrayRectangular / ArrayPolar make loose copies (autocad_array_entities
keeps doing that). An associative array is one object that stays editable in
AutoCAD (ARRAYEDIT, its grips, the Properties palette), and the path array
runs copies along a line, polyline, arc or spline. COM has no call for
either, so the Heron plug-in builds it with .NET and checks where AutoCAD put
the items before it keeps the array.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta
from ._shared import (
    COLOR_OPT,
    COORDS_OPT,
    HANDLES_OPT,
    LAYER_OPT,
    in_plugin,
    plugin_created,
    ucs_for,
    world_coords,
)

# One array holds at most this many items (ArrayPlan.MostItems in the plug-in).
MOST_ITEMS = 10000


@mcp.tool(name="autocad_associative_array", **tool_meta("Associative Array (Grid, Ring Or Along A Path)"))
@tool_errors
async def autocad_associative_array(
    handles: Annotated[list[str], HANDLES_OPT],
    pattern: Annotated[
        str,
        Field(
            description=(
                "'path' runs copies along a line, polyline, arc or spline; 'rectangular' makes a grid "
                "of rows and columns; 'polar' makes a ring about a centre."
            ),
            pattern="^(rectangular|polar|path)$",
        ),
    ],
    path: Annotated[
        str | None,
        Field(default=None, description="Path array: handle of the line, polyline, arc, circle or spline to run along."),
    ] = None,
    count: Annotated[
        int | None,
        Field(
            default=None,
            ge=2,
            le=MOST_ITEMS,
            description=(
                "Polar: items round the ring, the original included. Path: items along the path, spread "
                "evenly end to end; with a spacing, how many to place (omit to fill the path)."
            ),
        ),
    ] = None,
    spacing: Annotated[
        float | None,
        Field(default=None, gt=0, description="Path array: distance between items along the path, e.g. 1500 for a hanger every 1.5 m."),
    ] = None,
    align_items: Annotated[
        bool,
        Field(default=True, description="Path array: turn each item to follow the path's direction (false keeps them all square)."),
    ] = True,
    rows: Annotated[int, Field(default=1, ge=1, le=MOST_ITEMS, description="Rectangular: rows (along Y).")] = 1,
    columns: Annotated[int, Field(default=1, ge=1, le=MOST_ITEMS, description="Rectangular: columns (along X).")] = 1,
    row_spacing: Annotated[float, Field(default=0.0, description="Rectangular: distance between rows; negative builds downward.")] = 0.0,
    column_spacing: Annotated[float, Field(default=0.0, description="Rectangular: distance between columns; negative builds leftward.")] = 0.0,
    center: Annotated[
        list[float] | None,
        Field(default=None, description="Polar: centre of the ring, as [x, y]."),
    ] = None,
    fill_angle: Annotated[
        float,
        Field(default=360.0, gt=0, le=360, description="Polar: DEGREES the ring spans, counter-clockwise. 360 spreads the items evenly; 90 fills a quarter."),
    ] = 360.0,
    rotate_items: Annotated[
        bool,
        Field(default=True, description="Polar: turn each item as it goes round (false keeps them all square)."),
    ] = True,
    base_point: Annotated[
        list[float] | None,
        Field(
            default=None,
            description=(
                "The point of the objects that lands on each item's place, as [x, y]. Omit for a block's "
                "insertion point (one block), else the start of the path (path) or the middle of the objects."
            ),
        ),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Array objects as ONE editable array object (AutoCAD's ARRAY): along a path, in a grid or in a ring.

    The array stays associative: in AutoCAD the modeller clicks it and edits
    the count, the spacing or the path with its grips or ARRAYEDIT, and the
    items follow. A path array that follows a duct or pipe line moves with
    the line when the line is stretched. AutoCAD takes the original objects
    into the array, as ARRAY does; ARRAYCLASSIC / EXPLODE give loose copies.

    Before it is kept, the plug-in checks where AutoCAD put the items against
    the asked spacing and centre; an array anywhere else is refused and
    nothing is changed. Grids run along the world X and Y axes.

    One undo step.

    Args:
        handles (list[str]): the objects to repeat.
        pattern (str): 'path', 'rectangular' or 'polar'.
        path (Optional[str]): path array: the curve to run along.
        count (Optional[int]): polar: items round the ring; path: items along it.
        spacing (Optional[float]): path array: distance between items.
        align_items (bool): path array: items follow the path's direction.
        rows / columns (int): rectangular grid.
        row_spacing / column_spacing (float): rectangular grid.
        center (Optional[list[float]]): polar: [x, y].
        fill_angle (float): polar: degrees the ring spans.
        rotate_items (bool): polar: items turn as they go round.
        base_point (Optional[list[float]]): the point of the objects placed on each item's spot.
        layer / color: for the array object.
        coords (str): 'world' or 'ucs' for base_point and center.

    Returns:
        str: JSON: {"created": true, "handle": str, "associative": bool,
             "pattern": str, "items": int, "base_point": [x, y, z],
             "sources": [str], "sources_still_loose": [str],
             "extents": {"min", "max"}, "verified": bool, ...the pattern's
             own numbers (rows, columns / count, center / path, method, spacing)}

    Examples:
        - Use when: "put a hanger every 1500 along this duct line" — pattern='path',
          handles=[the hanger block], path=the line, spacing=1500.
        - Use when: "6 sprinklers evenly along that branch pipe, end to end" —
          pattern='path', count=6.
        - Use when: "a 4 x 6 grid of ceiling diffusers 1200 apart that I can
          change later" — pattern='rectangular', rows=4, columns=6,
          row_spacing=1200, column_spacing=1200.
        - Use when: "8 bolt holes round the flange, as an array I can edit" —
          pattern='polar', count=8, center=the flange centre.
        - Don't use when: plain loose copies are wanted (each one moved or
          edited on its own) — autocad_array_entities.
        - Don't use when: blocks should sit at even steps along a run and stay
          separate blocks with their own attributes — autocad_place_along.

    Error Handling:
        - A pattern given without its numbers (a path with neither count nor
          spacing, a ring with no centre, a 1 x 1 grid) is refused before
          AutoCAD is asked.
        - More items than fit on the path names how many do fit.
        - An array AutoCAD builds somewhere other than asked is refused, and
          nothing is changed.
    """
    args: dict[str, Any] = {"handles": list(dict.fromkeys(handles)), "pattern": pattern}
    if pattern == "path":
        if not path:
            raise AutocadError("A path array needs 'path': the handle of the line, polyline, arc or spline to run along.")
        if count is None and spacing is None:
            raise AutocadError("A path array needs 'count' (spread end to end) or 'spacing' (every so far), or both.")
        args.update(path=path, count=count, spacing=float(spacing) if spacing is not None else None, align_items=bool(align_items))
    elif pattern == "rectangular":
        if rows * columns < 2:
            raise AutocadError("A 1 x 1 grid makes no copies. Give more 'rows' or 'columns'.")
        if rows * columns > MOST_ITEMS:
            raise AutocadError(f"{rows} x {columns} is {rows * columns} items; one array holds at most {MOST_ITEMS}.")
        if rows > 1 and row_spacing == 0:
            raise AutocadError(f"rows={rows} needs a 'row_spacing' other than zero, or every row lands on the first.")
        if columns > 1 and column_spacing == 0:
            raise AutocadError(f"columns={columns} needs a 'column_spacing' other than zero, or every column lands on the first.")
        args.update(rows=rows, columns=columns, row_spacing=float(row_spacing), column_spacing=float(column_spacing))
    else:
        if not center or len(center) < 2:
            raise AutocadError("A ring needs 'center' as [x, y].")
        if count is None:
            raise AutocadError("A ring needs 'count': how many items round it, the original included.")
        args.update(count=count, fill_angle=math.radians(fill_angle), rotate_items=bool(rotate_items))
    if base_point is not None and len(base_point) < 2:
        raise AutocadError("base_point must be [x, y].")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        if center is not None and pattern == "polar":
            args["center"] = world_coords(center, ucs)
        if base_point is not None:
            args["base_point"] = world_coords(base_point, ucs)
        args.update(layer=layer, color=to_aci(color))
        return plugin_created(doc, in_plugin("associative_array", args, "An associative array"))

    return dumps(await run(work))
