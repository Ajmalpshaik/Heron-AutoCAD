"""A 3D model cut and looked at in 2D, for a shop drawing (D-95).

FLATSHOT, SOLPROF and SECTIONPLANE have no Automation call, so the Heron
plug-in does both of these with AutoCAD's own section object and its
"generate 2D section" call:

* ``autocad_flatten_views`` - plan, front and side views of solids as 2D
  linework, hidden lines removed, each view a block set out the way a drawing
  office sets out views (FLATSHOT).
* ``autocad_section_plane`` - a section plane through given points, kept in
  the model, and its 2D section (cut outlines, hatch, what is seen beyond) as
  a block on the sheet.

Both run in one transaction inside AutoCAD: it all lands or none of it does.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta
from ._shared import (
    COLOR_OPT,
    COORDS_OPT,
    LAYER_OPT,
    current_ucs,
    in_plugin,
    plugin_created,
)

VIEWS = ("front", "top", "right", "left", "back", "bottom")
View = Literal["front", "top", "plan", "right", "left", "back", "bottom"]
MOST_SOLIDS = 1000


def _point(value: list[float], name: str) -> list[float]:
    if len(value) not in (2, 3):
        raise AutocadError(f"{name} must be [x, y] or [x, y, z].")
    return [float(v) for v in value] + ([0.0] if len(value) == 2 else [])


def _to_world(points: list[list[float]], coords: str) -> list[list[float]]:
    """The caller's points as world points: a UCS is turned through in full 3D."""
    if str(coords).strip().lower() != "ucs":
        return points
    ucs = current_ucs(get_doc())
    return points if ucs.is_world else [list(ucs.to_world(p)) for p in points]


def _created(operation: str, args: dict[str, Any], what: str) -> dict[str, Any]:
    doc = get_doc()
    require_idle(doc)
    return plugin_created(doc, in_plugin(operation, args, what))


@mcp.tool(name="autocad_flatten_views", **tool_meta("Flatten Solids To 2D Views"))
@tool_errors
async def autocad_flatten_views(
    handles: Annotated[
        list[str],
        Field(min_length=1, max_length=MOST_SOLIDS, description="The 3D solids to draw, by handle: one part, or a whole spool or assembly."),
    ],
    insert_at: Annotated[
        list[float],
        Field(description="[x, y] where the front view's lower-left corner goes, in clear space beside the model (autocad_get_extents)."),
    ],
    views: Annotated[
        list[View] | None,
        Field(default=None, description="Which views: 'front', 'top' (plan), 'right', 'left', 'back', 'bottom'. Default front, top and right."),
    ] = None,
    projection: Annotated[
        Literal["third", "first"],
        Field(default="third", description="How the views are set out: 'third' angle puts the plan above the front and the right view on its right; 'first' angle puts them below and on the left."),
    ] = "third",
    gap: Annotated[
        float | None,
        Field(default=None, gt=0, description="Space between the views, in drawing units. Default a quarter of the solids' biggest size."),
    ] = None,
    join: Annotated[
        bool,
        Field(default=False, description="Treat the solids as one, so a part hides the lines of what is behind it. It also loses the line where two flush faces meet."),
    ] = False,
    tangent_edges: Annotated[
        bool,
        Field(default=False, description="Also draw the lines where a curved face runs smoothly into a flat one (SOLPROF keeps them off by default)."),
    ] = False,
    name: Annotated[
        str | None,
        Field(default=None, description="Start of the block names, e.g. 'BRACKET' gives BRACKET-FRONT, BRACKET-TOP. Omit for FLATSHOT-1-..."),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Draw plan, front and side views of 3D solids as 2D linework for a shop drawing (FLATSHOT, SOLPROF).

    Each view is the solids seen square on, hidden lines removed, made as a
    block of lines (front, top, right...) and set out beside each other so
    they line up: third angle by default (plan above the front, right view on
    the right). The model is not touched. Dimension the views with
    autocad_dimension_run; the answer gives each view's box on the sheet.

    One undo step.

    Args:
        handles (list[str]): the solids.
        insert_at (list[float]): the front view's lower-left corner.
        views (Optional[list[str]]): which views.
        projection (str): 'third' or 'first'.
        gap (Optional[float]): space between views.
        join (bool): one solid for hiding lines.
        tangent_edges (bool): draw smooth-join lines.
        name (Optional[str]): start of the block names.
        layer (Optional[str]): layer for the views, created if missing.
        color (Optional[str|int]): their colour.
        coords (str): 'world' or 'ucs' for insert_at.

    Returns:
        str: JSON: {"created": true, "handle": str (the first view),
             "views": [{"view", "block", "handle", "insert", "box":
             [minx, miny, maxx, maxy], "lines"}], "no_lines": [view...],
             "projection", "gap", "laid_flat_from", "verified"}

    Examples:
        - Use when: "flatten this bracket to plan, front and side for the
          shop drawing" — handles=[the solid], insert_at beside the model.
        - Use when: "give me a FLATSHOT of the pipe spool, front and top
          only" — views=['front', 'top'].
        - Use when: "SOLPROF the pump skid, first angle" — projection='first'.
        - Don't use when: the drawing should show a cut through the model -
          autocad_section_plane.
        - Don't use when: you only want to look at the model in 3D -
          autocad_set_3d_view.

    Error Handling:
        - A handle that is not a 3D solid is named, with what it is.
        - A view name that is not one of the six is refused, with the list.
        - No lines for any view is refused with nothing changed.
        - Needs the Heron plug-in built from this change; an older one says
          to update.
    """
    if not handles:
        raise AutocadError("Give the solids to flatten, by handle.")
    chosen = [("top" if v == "plan" else v) for v in (views or ["front", "top", "right"])]
    if len(set(chosen)) != len(chosen):
        raise AutocadError("A view is asked for twice.")
    at = _point(insert_at, "insert_at")

    def work() -> dict[str, Any]:
        where = _to_world([at], coords)[0]
        args = {
            "handles": list(handles),
            "views": chosen,
            "insert_at": where,
            "projection": projection,
            "gap": None if gap is None else float(gap),
            "join": join,
            "tangent_edges": tangent_edges,
            "name": name.strip() if name else None,
            "layer": layer,
            "color": to_aci(color),
        }
        return _created("flat_views", args, "Flattening solids to 2D views")

    return dumps(await run(work))


@mcp.tool(name="autocad_section_plane", **tool_meta("Cut A Section Through The Model"))
@tool_errors
async def autocad_section_plane(
    points: Annotated[
        list[list[float]],
        Field(
            min_length=2,
            max_length=3,
            description=(
                "Two points: a vertical cut along the line between them, as a section line on a "
                "plan. Three points: the plane through all three (three points at one level make a "
                "plan cut at that level)."
            ),
        ),
    ],
    insert_at: Annotated[
        list[float],
        Field(description="[x, y] where the 2D section's lower-left corner goes, in clear space (autocad_get_extents)."),
    ],
    look_towards: Annotated[
        list[float] | None,
        Field(
            default=None,
            description=(
                "A point on the side the section looks at. Default: to the left of the line from "
                "the first point to the second (walk along it, look left); a level cut looks down."
            ),
        ),
    ] = None,
    handles: Annotated[
        list[str] | None,
        Field(default=None, max_length=MOST_SOLIDS, description="The solids to cut. Omit for every 3D solid in model space (at most 1000)."),
    ] = None,
    hatch: Annotated[bool, Field(default=True, description="Hatch the cut faces.")] = True,
    background: Annotated[bool, Field(default=True, description="Also draw what is seen beyond the cut, hidden lines removed.")] = True,
    keep_plane: Annotated[bool, Field(default=True, description="Keep the section plane in the model, as SECTIONPLANE leaves it, so the cut can be seen and moved.")] = True,
    name: Annotated[str | None, Field(default=None, description="Name for the section's block (and the plane). Omit for SECTION-1, -2...")] = None,
    plane_layer: Annotated[str | None, Field(default=None, description="Layer for the section plane, created if missing. Omit for the current layer.")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Cut a section through a 3D model and draw the 2D section as a block (SECTIONPLANE, Generate Section).

    A section plane is put through the points and kept in the model; the 2D
    section of the solids it cuts (their cut outlines, hatched, and what is
    seen beyond, hidden lines removed) is made as one block, laid flat on the
    sheet at insert_at, the way AutoCAD's Generate Section / Elevation makes a
    2D section. Right on the section is along the line from the first point to
    the second; up is up.

    One undo step.

    Args:
        points (list[list[float]]): two points (a vertical cut) or three (a plane).
        insert_at (list[float]): the section's lower-left corner on the sheet.
        look_towards (Optional[list[float]]): a point on the side to look at.
        handles (Optional[list[str]]): the solids to cut; omit for all.
        hatch (bool): hatch the cut faces.
        background (bool): draw what is beyond the cut.
        keep_plane (bool): keep the section plane.
        name (Optional[str]): the block's name.
        plane_layer (Optional[str]): the plane's layer.
        layer (Optional[str]): layer for the section block, created if missing.
        color (Optional[str|int]): its colour.
        coords (str): 'world' or 'ucs' for the points.

    Returns:
        str: JSON: {"created": true, "handle": str, "block": str,
             "section_plane": str, "solids": int, "cut": int, "lines": int,
             "size": [w, h], "looking": [x, y, z], "right", "up",
             "laid_flat_from", "verified"}

    Examples:
        - Use when: "cut a section A-A through the plant room along this
          line and put it on the right" — two points, insert_at.
        - Use when: "section through the riser looking north" — two points
          on an east-west line, look_towards a point to the north.
        - Use when: "a plan cut of the services at 2.7 m" — three points at
          z=2700.
        - Don't use when: you want views of a part from outside, not a cut -
          autocad_flatten_views.
        - Don't use when: the solid itself should be cut in two -
          autocad_slice_solid.

    Error Handling:
        - Points that make no line or no plane are refused, with why.
        - A plane that cuts and sees none of the solids is refused with
          nothing changed.
        - A handle that is not a 3D solid is named, with what it is.
    """
    if len(points) not in (2, 3):
        raise AutocadError(
            "A section plane takes two points (a vertical cut along the line between them) or three "
            f"(the plane through them), not {len(points)}."
        )
    cut_points = [_point(p, f"points[{i}]") for i, p in enumerate(points)]
    at = _point(insert_at, "insert_at")
    towards = _point(look_towards, "look_towards") if look_towards is not None else None

    def work() -> dict[str, Any]:
        world = _to_world(cut_points + [at] + ([towards] if towards else []), coords)
        args = {
            "points": world[: len(cut_points)],
            "insert_at": world[len(cut_points)],
            "look_towards": world[len(cut_points) + 1] if towards else None,
            "handles": list(handles) if handles else None,
            "hatch": hatch,
            "background": background,
            "keep_plane": keep_plane,
            "name": name.strip() if name else None,
            "plane_layer": plane_layer,
            "layer": layer,
            "color": to_aci(color),
        }
        return _created("section_plane", args, "Cutting a section")

    return dumps(await run(work))
