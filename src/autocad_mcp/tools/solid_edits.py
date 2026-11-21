"""3D modelling COM has no call for, done by the Heron plug-in (D-40).

Loft, rounding and bevelling solid edges, shelling, press-pull and thicken are
AutoCAD commands with no ActiveX method, so these tools ask the plug-in to do
them through AutoCAD's .NET API. Each runs in one transaction inside AutoCAD:
it all lands or none of it does, and a refusal says "Nothing was changed."

Edges and faces are picked by a plain word ('top', 'vertical') that goes by
the solid's box, or by the numbers ``autocad_list_solid_faces_and_edges``
gives. The numbers hold while the solid is unchanged: after any edit, list it
again.
"""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta
from ._shared import COLOR_OPT, LAYER_OPT, in_plugin, plugin_created

EDGE_WORDS = ("all", "vertical", "horizontal", "top", "bottom")
FACE_WORDS = ("top", "bottom", "front", "back", "left", "right")

EdgePick = Literal["all", "vertical", "horizontal", "top", "bottom"] | list[Annotated[int, Field(ge=0)]]
FacePick = Literal["top", "bottom", "front", "back", "left", "right"] | list[Annotated[int, Field(ge=0)]]

EDGES_OPT = Field(
    description=(
        "Which edges: 'all', 'vertical', 'horizontal', 'top' (the flat edges round the top), "
        "'bottom', or edge numbers from autocad_list_solid_faces_and_edges, e.g. [0, 3]."
    )
)
FACES_OPT = Field(
    description=(
        "Which faces: 'top', 'bottom', 'front' (the side the Front view looks at, towards -Y), "
        "'back', 'left', 'right', or face numbers from autocad_list_solid_faces_and_edges."
    )
)
HOW_TO_PICK = (
    "Edges: 'all', 'vertical', 'horizontal', 'top', 'bottom', or these numbers. Faces: 'top', "
    "'bottom', 'front', 'back', 'left', 'right', or these numbers. The numbers hold while the solid "
    "is unchanged: list it again after any edit."
)
LISTING_LIMIT = 200


def _changed(operation: str, args: dict[str, Any], what: str) -> dict[str, Any]:
    """An edit of an existing solid: the plug-in's report, as it gave it."""
    require_idle(get_doc())
    return in_plugin(operation, args, what)


def _created(operation: str, args: dict[str, Any], what: str) -> dict[str, Any]:
    """Something new: the plug-in's report, with the new object read back over COM."""
    doc = get_doc()
    require_idle(doc)
    return plugin_created(doc, in_plugin(operation, args, what))


@mcp.tool(
    name="autocad_list_solid_faces_and_edges",
    **tool_meta("List A Solid's Faces And Edges", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_list_solid_faces_and_edges(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
    limit: Annotated[int, Field(default=LISTING_LIMIT, ge=1, le=2000, description="Most faces and most edges to list.")] = LISTING_LIMIT,
) -> str:
    """Number a solid's faces and edges, so a fillet, chamfer, shell or press-pull can pick them.

    Each face: its kind (plane, cylinder...), area, centre, which way a flat
    one faces, and its edges. Each edge: its kind (line, arc, circle...), ends
    and length. Changes nothing.

    Args:
        handle (str): the solid.
        limit (int): most faces and most edges listed.

    Returns:
        str: JSON: {"handle": str, "volume": float, "face_count": int,
             "edge_count": int, "faces": [...], "edges": [...],
             "how_to_pick": str}

    Examples:
        - Use when: "which edges of this plinth are along the top" — then pick
          them by number in autocad_fillet_solid_edges.
        - Use when: "number the faces of this solid".
        - Don't use when: a word says it already ('top', 'vertical'): the edit
          tools take the word straight.
        - Don't use when: you want the volume or centroid -
          autocad_solid_properties.

    Error Handling:
        - A handle that is not a 3D solid is named, with what it is.
        - Needs the Heron plug-in 1.2.0 or newer; an older one says to update.
    """

    def work() -> dict[str, Any]:
        require_idle(get_doc())
        return in_plugin("solid_topology", {"handle": handle}, "Listing a solid's faces and edges", changes=False)

    report = await run(work)
    faces, edges = list(report.get("faces", [])), list(report.get("edges", []))
    result: dict[str, Any] = {
        "handle": report.get("handle", handle),
        "volume": report.get("volume"),
        "face_count": len(faces),
        "edge_count": len(edges),
        "faces": faces[:limit],
        "edges": edges[:limit],
        "how_to_pick": HOW_TO_PICK,
    }
    if len(faces) > limit or len(edges) > limit:
        result["note"] = (
            f"Only the first {limit} faces and edges are listed. Pick by word, or call again with a "
            "bigger limit."
        )
    return dumps(result)


@mcp.tool(name="autocad_loft", **tool_meta("Loft A Solid Through Outlines"))
@tool_errors
async def autocad_loft(
    sections: Annotated[
        list[str],
        Field(min_length=2, description="The closed outlines, by handle, IN ORDER along the loft (bottom to top, start to end)."),
    ],
    guides: Annotated[
        list[str] | None,
        Field(default=None, description="Optional guide curves that touch every outline and steer the shape between them."),
    ] = None,
    path: Annotated[str | None, Field(default=None, description="Optional path curve the loft follows instead of guides.")] = None,
    ruled: Annotated[bool, Field(default=False, description="Straight between the outlines (a ruled transition) instead of smooth.")] = False,
    closed: Annotated[bool, Field(default=False, description="Loop back from the last outline to the first (a ring).")] = False,
    surface: Annotated[
        bool,
        Field(default=False, description="Make a surface instead of a solid (LOFT's Surface mode). Open outlines always make a surface: a canopy, a curved roof sheet, a louvre blade."),
    ] = False,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
) -> str:
    """Make a solid through closed outlines in order (LOFT), or a surface through open ones.

    A rectangular-to-round duct transition, a tapered column, a hopper: draw
    each outline at its own height or position, then loft through them. With
    ``surface=true`` the loft is a surface instead, and the outlines may be
    open: a canopy through curved edges, a roof sheet between two arcs. The
    outlines are kept, as with DELOBJ off.

    One undo step.

    Args:
        sections (list[str]): the closed outlines, in order.
        guides (Optional[list[str]]): guide curves.
        path (Optional[str]): a path curve, instead of guides.
        ruled (bool): straight between outlines.
        closed (bool): loop back to the first outline.
        surface (bool): a surface instead of a solid; outlines may be open.
        layer (Optional[str]): layer for the solid, created if missing.
        color (Optional[str|int]): its colour.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "3dsolid" (or a
             surface type), "sections": int, "volume": float (a solid) or
             "area": float (a surface), "verified": bool}

    Examples:
        - Use when: "make a transition from the rectangular duct to the round
          duct" (600 x 400 to 450 round) — the rectangle and the circle at
          their heights, in order.
        - Use when: "loft these three sections into a tapered column".
        - Use when: "a canopy surface through these two curved edges" —
          surface=true; the arcs are open, so it is a surface.
        - Don't use when: one outline goes straight up or along a route -
          autocad_extrude_profile (extrude, revolve or sweep).
        - Don't use when: the surface is flat, or spans a net of curves -
          autocad_add_surface (planar or network).

    Error Handling:
        - An open outline is refused for a solid: a loft of open shapes is a
          surface; give surface=true.
        - Guides and a path together are refused: a loft follows one or the
          other.
        - Outlines AutoCAD cannot loft (crossing, out of order) are refused
          with nothing changed.
    """
    if guides and path:
        raise AutocadError("Give guides or a path, not both: AutoCAD's loft follows one or the other.")
    args = {
        "sections": list(sections),
        "guides": list(guides) if guides else None,
        "path": path,
        "ruled": ruled,
        "closed": closed,
        "layer": layer,
        "color": to_aci(color),
    }
    if surface:
        return dumps(await run(lambda: _created("loft_surface", args, "Lofting a surface")))
    return dumps(await run(lambda: _created("loft", args, "Lofting")))


@mcp.tool(name="autocad_fillet_solid_edges", **tool_meta("Round A Solid's Edges", destructive=True))
@tool_errors
async def autocad_fillet_solid_edges(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
    radius: Annotated[float, Field(gt=0, description="The fillet radius, in drawing units.")],
    edges: Annotated[EdgePick, EDGES_OPT],
) -> str:
    """Round edges of a 3D solid (FILLETEDGE).

    One undo step.

    Args:
        handle (str): the solid.
        radius (float): the radius.
        edges (str|list[int]): a word or edge numbers.

    Returns:
        str: JSON: {"handle": str, "radius": float, "edges": [int],
             "volume_before": float, "volume_after": float}

    Examples:
        - Use when: "round the upright corners of this plinth by 25" —
          edges='vertical'.
        - Use when: "fillet all edges of the block 5 mm" — edges='all'.
        - Use when: "round just these two edges" — numbers from
          autocad_list_solid_faces_and_edges.
        - Don't use when: the corner is on a flat 2D outline - draw it rounded
          (autocad_make_shape's rounded_rectangle, or a polyline with bulges).

    Error Handling:
        - A word that picks no edge, or a number that is not there, is refused
          with the range.
        - A radius too big for the faces beside an edge is refused with
          nothing changed.
    """
    args = {"handle": handle, "radius": float(radius), "edges": edges}
    return dumps(await run(lambda: _changed("fillet_edges", args, "Rounding a solid's edges")))


@mcp.tool(name="autocad_chamfer_solid_edges", **tool_meta("Bevel A Solid's Edges", destructive=True))
@tool_errors
async def autocad_chamfer_solid_edges(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
    face: Annotated[
        Literal["top", "bottom", "front", "back", "left", "right"] | Annotated[int, Field(ge=0)],
        Field(description="The one face the chamfer is measured from: a word ('top') or its number."),
    ],
    distance: Annotated[float, Field(gt=0, description="Chamfer distance across that face.")],
    other_distance: Annotated[
        float | None,
        Field(default=None, gt=0, description="Distance down the other face. Omit for an even 45-degree chamfer."),
    ] = None,
    edges: Annotated[
        EdgePick | None,
        Field(default=None, description="Which of that face's edges. Omit for all of them."),
    ] = None,
) -> str:
    """Bevel edges of a 3D solid (CHAMFEREDGE), measured from one face.

    AutoCAD chamfers the edges of one face: name the face, and by default every
    edge round it is bevelled.

    One undo step.

    Args:
        handle (str): the solid.
        face (str|int): the face it is measured from.
        distance (float): across that face.
        other_distance (Optional[float]): down the other face; same if omitted.
        edges (Optional[str|list[int]]): which of the face's edges.

    Returns:
        str: JSON: {"handle": str, "face": int, "edges": [int],
             "distance": float, "other_distance": float,
             "volume_before": float, "volume_after": float}

    Examples:
        - Use when: "chamfer the top edges of the base plate 3 mm" —
          face='top', distance=3.
        - Use when: "bevel the front edge only" — face='front' and the edge's
          number.
        - Don't use when: the corner is on a flat 2D outline - draw the bevel
          into the polyline instead.

    Error Handling:
        - A face word that picks more than one face is refused: give its
          number.
        - An edge that is not on that face is refused, with the face's edges.
    """
    args = {
        "handle": handle,
        "face": [face] if isinstance(face, int) else face,
        "distance": float(distance),
        "other_distance": None if other_distance is None else float(other_distance),
        "edges": edges,
    }
    return dumps(await run(lambda: _changed("chamfer_edges", args, "Bevelling a solid's edges")))


@mcp.tool(name="autocad_shell_solid", **tool_meta("Hollow A Solid To A Wall Thickness", destructive=True))
@tool_errors
async def autocad_shell_solid(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
    thickness: Annotated[float, Field(gt=0, description="Wall thickness, in drawing units.")],
    remove_faces: Annotated[
        FacePick | None,
        Field(default=None, description="Faces left open, e.g. 'top' for a tank or a tray. Omit for a closed hollow."),
    ] = None,
    outward: Annotated[bool, Field(default=False, description="Grow the wall outside the solid instead of inside it.")] = False,
) -> str:
    """Hollow a 3D solid to a wall thickness, leaving chosen faces open (SOLIDEDIT Shell).

    A tank, a tray, a sump, a box section: model the outside, then shell it.

    One undo step.

    Args:
        handle (str): the solid.
        thickness (float): the wall.
        remove_faces (Optional[str|list[int]]): faces left open.
        outward (bool): wall outside the old faces.

    Returns:
        str: JSON: {"handle": str, "thickness": float, "outward": bool,
             "removed_faces": [int], "volume_before": float,
             "volume_after": float}

    Examples:
        - Use when: "make this box an open-top tank with 10 mm walls" —
          thickness=10, remove_faces='top'.
        - Use when: "hollow the column, 5 mm wall".
        - Don't use when: you want a pipe or duct from a route -
          autocad_extrude_profile sweeps a ring along it.

    Error Handling:
        - A wall thicker than the solid allows is refused with nothing
          changed.
    """
    args = {
        "handle": handle,
        "thickness": float(thickness),
        "outward": outward,
        "remove": remove_faces,
    }
    return dumps(await run(lambda: _changed("shell", args, "Shelling a solid")))


@mcp.tool(name="autocad_press_pull_faces", **tool_meta("Push Or Pull A Solid's Faces", destructive=True))
@tool_errors
async def autocad_press_pull_faces(
    handle: Annotated[str, Field(min_length=1, description="The 3D solid, by handle.")],
    faces: Annotated[FacePick, FACES_OPT],
    distance: Annotated[float, Field(description="How far: positive pulls the face out of the solid, negative pushes it in.")],
    taper: Annotated[
        float,
        Field(default=0.0, gt=-90, lt=90, description="Taper in DEGREES as the face moves; 0 keeps the sides straight."),
    ] = 0.0,
) -> str:
    """Push or pull flat faces of a 3D solid (PRESSPULL on a face, SOLIDEDIT Extrude).

    Raise a plinth, deepen a recess, stretch a box to a new length.

    One undo step.

    Args:
        handle (str): the solid.
        faces (str|list[int]): which flat faces.
        distance (float): positive out, negative in.
        taper (float): degrees.

    Returns:
        str: JSON: {"handle": str, "faces": [int], "distance": float,
             "volume_before": float, "volume_after": float}

    Examples:
        - Use when: "pull the top of the plinth up another 150" —
          faces='top', distance=150.
        - Use when: "push that face in 20".
        - Don't use when: the shape is still a flat outline -
          autocad_extrude_profile turns it into a solid.

    Error Handling:
        - A curved face is refused: this moves flat faces.
        - A distance of 0 is refused before AutoCAD is asked.
    """
    if distance == 0:
        raise AutocadError("The distance cannot be zero: positive pulls the face out, negative pushes it in.")
    args = {"handle": handle, "faces": faces, "distance": float(distance), "taper": math.radians(taper)}
    return dumps(await run(lambda: _changed("press_pull", args, "Press-pull")))


@mcp.tool(name="autocad_thicken_surface", **tool_meta("Thicken A Surface Into A Solid"))
@tool_errors
async def autocad_thicken_surface(
    handle: Annotated[str, Field(min_length=1, description="The surface, by handle.")],
    thickness: Annotated[float, Field(gt=0, description="Thickness, in drawing units.")],
    both_sides: Annotated[
        bool,
        Field(default=False, description="Thicken to both sides of the surface instead of one. Check the reported volume: whether AutoCAD splits the thickness or adds it each side is not proven yet."),
    ] = False,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
) -> str:
    """Make a solid from a surface by giving it a thickness (THICKEN). The surface is kept.

    One undo step.

    Args:
        handle (str): the surface.
        thickness (float): the thickness.
        both_sides (bool): both sides of the surface (see the volume).
        layer (Optional[str]): layer for the solid, created if missing.
        color (Optional[str|int]): its colour.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "3dsolid",
             "surface": str, "thickness": float, "both_sides": bool,
             "verified": bool}

    Examples:
        - Use when: "thicken this roof surface 200".
        - Use when: "give the lofted canopy surface a 3 mm skin".
        - Don't use when: the shape is a flat closed outline or a region -
          autocad_extrude_profile makes it a solid directly.

    Error Handling:
        - Anything that is not a surface is named, with what it is.
        - A thickness bigger than the surface's tightest curve is refused
          with nothing changed.
    """
    args = {
        "handle": handle,
        "thickness": float(thickness),
        "both_sides": both_sides,
        "layer": layer,
        "color": to_aci(color),
    }
    return dumps(await run(lambda: _created("thicken", args, "Thickening a surface")))
