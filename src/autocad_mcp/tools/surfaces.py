"""Surfaces and meshes, done by the Heron plug-in (D-95).

PLANESURF, SURFNETWORK and the MESH primitives have no Automation call, so the
plug-in makes them through AutoCAD's .NET API, in one transaction: it all
lands or none of it does. A loft through open outlines is
``autocad_loft(surface=true)``; a surface is given a thickness with
``autocad_thicken_surface``.
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
    in_plugin,
    plugin_created,
    ucs_for,
    world_coords,
)

MeshShape = Literal["box", "wedge", "cylinder", "cone", "sphere", "torus", "pyramid"]
MOST_OUTLINES = 500

# What each mesh shape must be told, as autocad_add_solid names its sizes.
MESH_SIZES: dict[str, tuple[str, ...]] = {
    "box": ("length", "width", "height"),
    "wedge": ("length", "width", "height"),
    "cylinder": ("radius", "height"),
    "cone": ("radius", "height"),
    "sphere": ("radius",),
    "torus": ("radius", "tube_radius"),
    "pyramid": ("radius", "height"),
}


def _created(operation: str, args: dict[str, Any], what: str) -> dict[str, Any]:
    doc = get_doc()
    require_idle(doc)
    return plugin_created(doc, in_plugin(operation, args, what))


@mcp.tool(name="autocad_add_surface", **tool_meta("Make A Planar Or Network Surface"))
@tool_errors
async def autocad_add_surface(
    kind: Annotated[
        Literal["planar", "network"],
        Field(description="'planar' (PLANESURF): flat, from closed outlines or two corners. 'network' (SURFNETWORK): through a net of curves."),
    ],
    outlines: Annotated[
        list[str] | None,
        Field(default=None, max_length=MOST_OUTLINES, description="Planar: closed flat outlines or regions, by handle; one surface each."),
    ] = None,
    corners: Annotated[
        list[list[float]] | None,
        Field(default=None, min_length=2, max_length=2, description="Planar, instead of outlines: two opposite corners of a rectangle, [x, y] or [x, y, z]; flat at the first corner's z."),
    ] = None,
    u_curves: Annotated[
        list[str] | None,
        Field(default=None, description="Network: the curves one way across the surface, by handle, in order (at least two)."),
    ] = None,
    v_curves: Annotated[
        list[str] | None,
        Field(default=None, description="Network: the curves the other way, crossing every u curve, in order (at least two)."),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Make a flat surface (PLANESURF) or a surface through a net of curves (SURFNETWORK).

    Planar: a flat surface filling each closed outline or region, or a
    rectangle from two corners - a ceiling plane, a slab face, a panel to
    thicken. Network: one surface through two sets of curves crossing each
    other, like a fishing net - a curved roof, a car-body-like duct fairing.
    The curves are kept. Give a surface a thickness with
    autocad_thicken_surface.

    One undo step.

    Args:
        kind (str): 'planar' or 'network'.
        outlines (Optional[list[str]]): planar: closed outlines or regions.
        corners (Optional[list[list[float]]]): planar: two corners instead.
        u_curves (Optional[list[str]]): network: one way.
        v_curves (Optional[list[str]]): network: the other way.
        layer (Optional[str]): layer for the surface, created if missing.
        color (Optional[str|int]): its colour.
        coords (str): 'world' or 'ucs' for the corners.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": str,
             "handles": [str] (planar), "surfaces": int (planar),
             "area": float, "verified": bool}

    Examples:
        - Use when: "a flat surface over this closed ceiling outline" —
          kind='planar', outlines=[the polyline].
        - Use when: "a 3000 x 2000 planar surface at 2700" — kind='planar',
          corners=[[0,0,2700],[3000,2000,2700]].
        - Use when: "a roof surface through these three ridge curves and the
          two eaves curves across them" — kind='network'.
        - Don't use when: the outlines are in order along a run (a
          transition, a canopy edge to edge) - autocad_loft(surface=true).
        - Don't use when: you want a solid - autocad_extrude_profile, or
          autocad_thicken_surface on the surface.

    Error Handling:
        - An open outline is refused: a planar surface fills a closed one.
        - Fewer than two curves either way is refused for a network.
        - Curves AutoCAD cannot make a surface of are refused with nothing
          changed.
    """
    if kind == "planar":
        if bool(outlines) == bool(corners):
            raise AutocadError("A planar surface takes outlines, or two corners of a rectangle - one of them.")
        if u_curves or v_curves:
            raise AutocadError("u_curves and v_curves are for a network surface.")
        if corners and any(len(c) not in (2, 3) for c in corners):
            raise AutocadError("corners must be two points, [x, y] or [x, y, z].")
    else:
        if outlines or corners:
            raise AutocadError("outlines and corners are for a planar surface.")
        if not u_curves or not v_curves or len(u_curves) < 2 or len(v_curves) < 2:
            raise AutocadError("A network surface needs at least two u_curves and two v_curves, crossing each other.")

    def work() -> dict[str, Any]:
        if kind == "network":
            args = {"u_curves": list(u_curves or []), "v_curves": list(v_curves or []),
                    "layer": layer, "color": to_aci(color)}
            return _created("network_surface", args, "Making a network surface")
        if corners:
            ucs = ucs_for(get_doc(), coords)
            at = [world_coords(c, ucs) for c in corners]
        else:
            at = None
        args = {"outlines": list(outlines) if outlines else None, "corners": at,
                "layer": layer, "color": to_aci(color)}
        return _created("planar_surface", args, "Making a planar surface")

    return dumps(await run(work))


@mcp.tool(name="autocad_add_mesh", **tool_meta("Make A Mesh"))
@tool_errors
async def autocad_add_mesh(
    shape: Annotated[
        MeshShape | None,
        Field(default=None, description="A mesh primitive: box, wedge, cylinder, cone, sphere, torus or pyramid. Or give from_handle instead."),
    ] = None,
    base: Annotated[
        list[float] | None,
        Field(default=None, description="The centre of the primitive's base, [x, y] or [x, y, z]; a sphere's or a torus's centre."),
    ] = None,
    length: Annotated[float | None, Field(default=None, gt=0, description="Box and wedge: size along X.")] = None,
    width: Annotated[float | None, Field(default=None, gt=0, description="Box and wedge: size along Y.")] = None,
    height: Annotated[float | None, Field(default=None, gt=0, description="Box, wedge, cylinder, cone, pyramid: size along Z.")] = None,
    radius: Annotated[float | None, Field(default=None, gt=0, description="Cylinder, cone, sphere, pyramid (to a corner): the radius. Torus: the ring's radius.")] = None,
    top_radius: Annotated[float | None, Field(default=None, ge=0, description="Cone and pyramid: radius at the top; 0 (default) comes to a point.")] = None,
    tube_radius: Annotated[float | None, Field(default=None, gt=0, description="Torus: the tube's radius.")] = None,
    sides: Annotated[int | None, Field(default=None, ge=3, le=32, description="Pyramid: how many sides (default 4).")] = None,
    divisions: Annotated[int | None, Field(default=None, ge=1, le=256, description="How many faces round (a cylinder's sides, a sphere's segments); a box's faces each way.")] = None,
    from_handle: Annotated[
        str | None,
        Field(default=None, description="Instead of a primitive: a 3D solid, surface or region to make a mesh of (MESHSMOOTH). It is kept."),
    ] = None,
    smoothness: Annotated[int, Field(default=0, ge=0, le=4, description="Smoothness 0 (faceted, as drawn) to 4 (smoothest).")] = 0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Make a mesh: a MESH primitive (box, cylinder, sphere...) or a mesh made from a solid (MESHSMOOTH).

    A mesh is faces and vertices that can be smoothed, which a render, an
    export to another program, or free-form editing wants. A primitive is
    placed by the centre of its base, like autocad_add_solid. A mesh made
    from a solid, a surface or a region leaves the original where it is.

    One undo step.

    Args:
        shape (Optional[str]): the primitive.
        base (Optional[list[float]]): centre of its base.
        length / width / height / radius / top_radius / tube_radius / sides:
            the sizes the shape needs, as autocad_add_solid names them.
        divisions (Optional[int]): faces round, or each way on a box.
        from_handle (Optional[str]): a solid, surface or region to mesh instead.
        smoothness (int): 0 to 4.
        layer (Optional[str]): layer for the mesh, created if missing.
        color (Optional[str|int]): its colour.
        coords (str): 'world' or 'ucs' for base.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": str, "mesh": str,
             "smoothness": int, "faces": int, "vertices": int,
             "watertight": bool, "volume": float, "verified": bool}

    Examples:
        - Use when: "a mesh box 1000 x 600 x 400 at the origin, smoothness 2"
          — shape='box'.
        - Use when: "make a mesh of this solid for the render" —
          from_handle=the solid.
        - Use when: "a 12-sided mesh cylinder" — shape='cylinder',
          divisions=12.
        - Don't use when: you want a solid to model with (booleans, volume,
          fillets) - autocad_add_solid.

    Error Handling:
        - A shape missing a size names exactly what it needs.
        - A primitive and from_handle together are refused.
        - from_handle that is not a solid, surface or region is named.
    """
    if bool(shape) == bool(from_handle):
        raise AutocadError("Give a shape to make, or from_handle to mesh an object - one of them.")
    sizes = {"length": length, "width": width, "height": height, "radius": radius,
             "tube_radius": tube_radius}
    if shape:
        missing = [n for n in MESH_SIZES[shape] if sizes.get(n) is None]
        if missing:
            raise AutocadError(f"A {shape} mesh needs {', '.join(MESH_SIZES[shape])}; missing {', '.join(missing)}.")
        if base is None or len(base) not in (2, 3):
            raise AutocadError("base must be [x, y] or [x, y, z]: the centre of the mesh's base.")
        extra = {"top_radius": top_radius, "sides": sides}
        stray = [n for n, v in {**sizes, **extra}.items() if v is not None and n not in MESH_SIZES[shape]
                 and not (n == "top_radius" and shape in ("cone", "pyramid"))
                 and not (n == "sides" and shape == "pyramid")]
        if stray:
            raise AutocadError(f"A {shape} mesh does not take {', '.join(stray)}.")
        if shape == "torus" and float(tube_radius) >= float(radius):  # type: ignore[arg-type]
            raise AutocadError("tube_radius must be smaller than the radius, or the torus closes on itself.")
        if top_radius is not None and float(top_radius) >= float(radius):  # type: ignore[arg-type]
            raise AutocadError("top_radius must be smaller than the radius (0 comes to a point).")
    elif any(v is not None for v in (*sizes.values(), top_radius, sides, divisions, base)):
        raise AutocadError("A mesh made from an object takes no sizes: give from_handle and smoothness only.")

    def work() -> dict[str, Any]:
        args: dict[str, Any] = {"smoothness": int(smoothness), "layer": layer, "color": to_aci(color)}
        if from_handle:
            args["from_handle"] = from_handle
        else:
            ucs = ucs_for(get_doc(), coords)
            args.update({"shape": shape, "base": world_coords(base or [], ucs), "divisions": divisions,
                         "top_radius": top_radius, "sides": sides})
            args.update({k: float(v) for k, v in sizes.items() if v is not None})
        return _created("add_mesh", args, "Making a mesh")

    return dumps(await run(work))
