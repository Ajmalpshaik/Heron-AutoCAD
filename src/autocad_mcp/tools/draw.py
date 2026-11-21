"""Tools that create geometry, text, dimensions, blocks and hatches.

Every creation tool shares the same layer / colour / linetype options and the
same return shape, so results chain: each returns the handle of what it made,
which the modify, query and hatch tools accept directly.
"""

from __future__ import annotations

import math
import os
from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..acad.entities import describe, resolve_handle
from ..acad.tables import apply_properties
from ..acad.units import rad
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import (
    AutocadError,
    com_message,
    is_dispatch_failure,
    is_retryable,
    raise_if_busy,
)
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, double_array, object_array
from ._shared import (
    COLOR_OPT,
    LAYER_OPT,
    LINETYPE_OPT,
    SPACE_OPT,
    created_payload,
    point,
)
from .annotation_scales import ANNOTATIVE_OPT, make_new_annotative, require_plugin

# ---------------------------------------------------------------------------
# Linework
# ---------------------------------------------------------------------------


@mcp.tool(
    name="autocad_draw_line",
    **tool_meta("Draw Line"),
)
@tool_errors
async def autocad_draw_line(
    start: Annotated[
        list[float],
        Field(description="Start point as [x, y] or [x, y, z], e.g. [0, 0]."),
    ],
    end: Annotated[
        list[float],
        Field(description="End point as [x, y] or [x, y, z], e.g. [1000, 0]."),
    ],
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    linetype: Annotated[str | None, LINETYPE_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw a single straight line between two points.

    Coordinates are in the drawing's own units — call autocad_status first if
    you do not know whether the drawing is in millimetres, metres or inches.

    Args:
        start (list[float]): [x, y] or [x, y, z] start point.
        end (list[float]): [x, y] or [x, y, z] end point.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number 0-256.
        linetype (Optional[str]): Linetype name.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "line",
             "layer": str, "length": float, "angle_degrees": float}

    Examples:
        - Use when: "draw a 5 m line along X from the origin" ->
          start=[0,0], end=[5000,0] in a millimetre drawing.
        - Don't use when: you need several connected segments — use
          autocad_draw_polyline so they stay one object.
    """
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddLine(
                point(start, "start"), point(end, "end")
            )
            notes = apply_properties(doc, entity, layer, aci, linetype)
        info = describe(entity)
        return created_payload(
            entity,
            notes,
            length=info.get("length"),
            angle_degrees=info.get("angle_degrees"),
        )

    return dumps(await run(work))


@mcp.tool(
    name="autocad_draw_polyline",
    **tool_meta("Draw Polyline"),
)
@tool_errors
async def autocad_draw_polyline(
    points: Annotated[
        list[list[float]],
        Field(
            description=(
                "Vertices in order, each [x, y], e.g. "
                "[[0,0],[1000,0],[1000,500]]. At least two are required."
            ),
            min_length=2,
        ),
    ],
    closed: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Join the last vertex back to the first, making a closed shape "
                "that has an area and can bound a hatch."
            ),
        ),
    ] = False,
    width: Annotated[
        float | None,
        Field(
            default=None,
            description="Constant line width in drawing units, e.g. 0.5.",
            ge=0,
        ),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    linetype: Annotated[str | None, LINETYPE_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw a connected multi-segment polyline, optionally closed.

    A polyline is one object, so it can be offset, filleted and area-measured
    as a unit. Prefer it over separate lines for outlines, walls, boundaries
    and site edges.

    Args:
        points (list[list[float]]): Ordered [x, y] vertices, two or more.
        closed (bool): Close the loop back to the first vertex.
        width (Optional[float]): Constant width for all segments.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        linetype (Optional[str]): Linetype name.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "polyline",
             "layer": str, "vertex_count": int, "closed": bool,
             "length": float, "area": float}
        "area" appears only when closed is true.

    Examples:
        - Use when: "outline a 10 x 5 m room" -> the four corners, closed=true.
        - Don't use when: the shape is a plain rectangle —
          autocad_draw_rectangle takes just two corners.
    """
    aci = to_aci(color)
    flat: list[float] = []
    for i, vertex in enumerate(points):
        if len(vertex) < 2:
            raise AutocadError(
                f"Vertex {i} is {vertex!r}; every vertex needs at least [x, y]."
            )
        flat.extend([float(vertex[0]), float(vertex[1])])

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddLightWeightPolyline(double_array(flat))
            if closed:
                entity.Closed = True
            if width is not None:
                entity.ConstantWidth = float(width)
            notes = apply_properties(doc, entity, layer, aci, linetype)
        info = describe(entity)
        return created_payload(
            entity,
            notes,
            vertex_count=info.get("vertex_count"),
            closed=info.get("closed"),
            length=info.get("length"),
            area=info.get("area"),
        )

    return dumps(await run(work))


@mcp.tool(
    name="autocad_draw_rectangle",
    **tool_meta("Draw Rectangle"),
)
@tool_errors
async def autocad_draw_rectangle(
    corner1: Annotated[list[float], Field(description="One corner as [x, y].")],
    corner2: Annotated[
        list[float],
        Field(description="The diagonally opposite corner as [x, y]."),
    ],
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    linetype: Annotated[str | None, LINETYPE_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw an axis-aligned rectangle as a single closed polyline.

    Args:
        corner1 (list[float]): [x, y] of one corner.
        corner2 (list[float]): [x, y] of the opposite corner.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        linetype (Optional[str]): Linetype name.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "polyline",
             "layer": str, "width": float, "height": float, "area": float,
             "perimeter": float}

    Examples:
        - Use when: "draw a 2400 x 1200 panel at the origin" ->
          corner1=[0,0], corner2=[2400,1200].
    """
    aci = to_aci(color)
    if len(corner1) < 2 or len(corner2) < 2:
        raise AutocadError("Both corners must be coordinate lists of [x, y].")
    x1, y1 = float(corner1[0]), float(corner1[1])
    x2, y2 = float(corner2[0]), float(corner2[1])
    if x1 == x2 or y1 == y2:
        raise AutocadError(
            f"The corners {corner1} and {corner2} share an X or Y value, which "
            "gives a rectangle with no area. Use autocad_draw_line for a single "
            "straight segment."
        )
    flat = [x1, y1, x2, y1, x2, y2, x1, y2]

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddLightWeightPolyline(double_array(flat))
            entity.Closed = True
            notes = apply_properties(doc, entity, layer, aci, linetype)
        info = describe(entity)
        return created_payload(
            entity,
            notes,
            width=round(abs(x2 - x1), 6),
            height=round(abs(y2 - y1), 6),
            area=info.get("area"),
            perimeter=info.get("length"),
        )

    return dumps(await run(work))


@mcp.tool(
    name="autocad_draw_circle",
    **tool_meta("Draw Circle"),
)
@tool_errors
async def autocad_draw_circle(
    center: Annotated[list[float], Field(description="Centre point as [x, y].")],
    radius: Annotated[
        float | None,
        Field(default=None, description="Radius in drawing units.", gt=0),
    ] = None,
    diameter: Annotated[
        float | None,
        Field(
            default=None,
            description="Diameter in drawing units. Give this or radius, not both.",
            gt=0,
        ),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    linetype: Annotated[str | None, LINETYPE_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw a circle from a centre point and a radius or diameter.

    Taking diameter directly avoids the halving mistakes that arise when a
    drawing calls out pipe, duct or bolt sizes by diameter.

    Args:
        center (list[float]): [x, y] centre.
        radius (Optional[float]): Radius, if specifying radius.
        diameter (Optional[float]): Diameter, if specifying diameter.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        linetype (Optional[str]): Linetype name.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "circle",
             "layer": str, "radius": float, "diameter": float, "area": float}

    Error Handling:
        - Returns an error if neither radius nor diameter is given, or if both
          are, rather than silently picking one.

    Examples:
        - Use when: "a 300 dia hole at 2000,1500" -> center=[2000,1500],
          diameter=300.
        - Don't use when: you want the hole and its centre lines - draw it,
          then autocad_add_centre_marks.
    """
    if radius is None and diameter is None:
        raise AutocadError("Give either 'radius' or 'diameter'.")
    if radius is not None and diameter is not None:
        raise AutocadError(
            f"Both radius ({radius}) and diameter ({diameter}) were given. "
            "Provide only one."
        )
    resolved = float(radius) if radius is not None else float(diameter) / 2.0
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddCircle(point(center, "center"), resolved)
            notes = apply_properties(doc, entity, layer, aci, linetype)
        info = describe(entity)
        return created_payload(
            entity,
            notes,
            radius=resolved,
            diameter=round(resolved * 2, 6),
            area=info.get("area"),
        )

    return dumps(await run(work))


@mcp.tool(
    name="autocad_draw_arc",
    **tool_meta("Draw Arc"),
)
@tool_errors
async def autocad_draw_arc(
    center: Annotated[list[float], Field(description="Centre point as [x, y].")],
    radius: Annotated[float, Field(description="Radius in drawing units.", gt=0)],
    start_angle: Annotated[
        float,
        Field(
            description=(
                "Start angle in DEGREES, counter-clockwise from the positive X "
                "axis. 0 is East, 90 is North."
            )
        ),
    ],
    end_angle: Annotated[
        float,
        Field(
            description=(
                "End angle in DEGREES. The arc always sweeps counter-clockwise "
                "from start_angle to end_angle."
            )
        ),
    ],
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    linetype: Annotated[str | None, LINETYPE_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw an arc from a centre, radius and angle range.

    Angles are degrees counter-clockwise from East, matching how AutoCAD
    displays them by default.

    Args:
        center (list[float]): [x, y] centre.
        radius (float): Arc radius.
        start_angle (float): Start angle in degrees.
        end_angle (float): End angle in degrees, swept counter-clockwise.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        linetype (Optional[str]): Linetype name.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "arc",
             "layer": str, "radius": float, "start_angle_degrees": float,
             "end_angle_degrees": float, "arc_length": float}

    Examples:
        - Use when: "the top half of a circle" -> start_angle=0, end_angle=180.
    """
    if start_angle % 360 == end_angle % 360:
        raise AutocadError(
            f"start_angle ({start_angle}) and end_angle ({end_angle}) point the "
            "same way, giving a zero-length arc. For a full circle use "
            "autocad_draw_circle."
        )
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddArc(
                point(center, "center"),
                float(radius),
                rad(start_angle),
                rad(end_angle),
            )
            notes = apply_properties(doc, entity, layer, aci, linetype)
        info = describe(entity)
        return created_payload(
            entity,
            notes,
            radius=info.get("radius"),
            start_angle_degrees=info.get("start_angle_degrees"),
            end_angle_degrees=info.get("end_angle_degrees"),
            arc_length=info.get("arc_length"),
        )

    return dumps(await run(work))


@mcp.tool(
    name="autocad_draw_ellipse",
    **tool_meta("Draw Ellipse"),
)
@tool_errors
async def autocad_draw_ellipse(
    center: Annotated[list[float], Field(description="Centre point as [x, y].")],
    major_radius: Annotated[
        float,
        Field(description="Half the ellipse's longest width, in drawing units.", gt=0),
    ],
    minor_radius: Annotated[
        float,
        Field(description="Half the ellipse's shortest width, in drawing units.", gt=0),
    ],
    rotation: Annotated[
        float,
        Field(
            default=0.0,
            description="Rotation of the major axis in DEGREES counter-clockwise.",
        ),
    ] = 0.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Draw an ellipse from its centre and its two half-axis lengths.

    Args:
        center (list[float]): [x, y] centre.
        major_radius (float): Half the long axis.
        minor_radius (float): Half the short axis.
        rotation (float): Major-axis rotation in degrees.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "ellipse",
             "layer": str, "major_radius": float, "minor_radius": float,
             "area": float}

    Error Handling:
        - Returns an error if minor_radius exceeds major_radius, since AutoCAD
          would otherwise reject the axis ratio with an opaque COM failure.

    Examples:
        - Use when: "an oval access panel 600 by 400" -> major_axis=300,
          minor_axis=200 (they are half-axes).
    """
    if minor_radius > major_radius:
        raise AutocadError(
            f"minor_radius ({minor_radius}) is larger than major_radius "
            f"({major_radius}). Swap them, or add 90 to 'rotation' instead."
        )
    aci = to_aci(color)
    angle = math.radians(rotation)
    # AddEllipse takes the major-axis endpoint as a vector from the centre.
    major_vector = (
        major_radius * math.cos(angle),
        major_radius * math.sin(angle),
        0.0,
    )
    ratio = minor_radius / major_radius

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddEllipse(
                point(center, "center"), apoint(*major_vector), ratio
            )
            notes = apply_properties(doc, entity, layer, aci, None)
        info = describe(entity)
        return created_payload(
            entity,
            notes,
            major_radius=info.get("major_radius"),
            minor_radius=info.get("minor_radius"),
            area=info.get("area"),
        )

    return dumps(await run(work))


@mcp.tool(
    name="autocad_draw_point",
    **tool_meta("Draw Point"),
)
@tool_errors
async def autocad_draw_point(
    position: Annotated[
        list[float], Field(description="Location as [x, y] or [x, y, z].")
    ],
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Place a single point object, useful as a survey or setting-out marker.

    Points render as a bare dot by default and can be effectively invisible.
    Set PDMODE to 3 (an X) or 34 (a circled cross) via autocad_set_variable if
    the user needs to see them.

    Args:
        position (list[float]): [x, y] or [x, y, z] location.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "point",
             "layer": str, "position": [float, float, float]}

    Examples:
        - Use when: "mark the survey points from this list" -> one call each,
          after autocad_drawing_setup sets a point style you can see.
        - Don't use when: you want a visible symbol - insert a block instead.
    """
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddPoint(point(position, "position"))
            notes = apply_properties(doc, entity, layer, aci, None)
        return created_payload(
            entity, notes, position=describe(entity).get("position")
        )

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------


@mcp.tool(
    name="autocad_add_text",
    **tool_meta("Add Single-Line Text"),
)
@tool_errors
async def autocad_add_text(
    text: Annotated[
        str,
        Field(description="The text to place, e.g. 'GROUND FLOOR'.", min_length=1),
    ],
    position: Annotated[list[float], Field(description="Insertion point as [x, y].")],
    height: Annotated[
        float,
        Field(
            default=2.5,
            description=(
                "Text height in drawing units. In a millimetre drawing 2.5 and "
                "3.5 are the usual ISO annotation sizes; scale up for a metre "
                "drawing."
            ),
            gt=0,
        ),
    ] = 2.5,
    rotation: Annotated[
        float,
        Field(default=0.0, description="Rotation in DEGREES counter-clockwise."),
    ] = 0.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
    annotative: Annotated[bool, ANNOTATIVE_OPT] = False,
) -> str:
    """Place a single line of text.

    Use this for short labels, tags and callouts. For paragraphs, or text that
    must wrap to a width, use autocad_add_mtext.

    Args:
        text (str): The string to place.
        position (list[float]): [x, y] insertion point.
        height (float): Character height in drawing units.
        rotation (float): Rotation in degrees.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        space (str): "model" or "paper".
        annotative (bool): make it annotative at the current annotation scale.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "text",
             "layer": str, "text": str, "height": float}
             With annotative: also "annotative", "annotation_scales" and
             "paper_height" (the height on paper at the current scale).

    Examples:
        - Use when: "write GROUND FLOOR at 0,5000, 200 high".
        - Don't use when: the note has to wrap or carry formatting - use
          autocad_add_mtext.
    """
    aci = to_aci(color)

    if annotative:
        require_plugin("Making text annotative")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddText(
                text, point(position, "position"), float(height)
            )
            if rotation:
                entity.Rotation = rad(rotation)
            notes = apply_properties(doc, entity, layer, aci, None)
            extra = make_new_annotative([str(entity.Handle)]) if annotative else {}
        return created_payload(entity, notes, text=text, height=float(height), **extra)

    return dumps(await run(work))


@mcp.tool(
    name="autocad_add_mtext",
    **tool_meta("Add Multiline Text"),
)
@tool_errors
async def autocad_add_mtext(
    text: Annotated[
        str,
        Field(
            description=(
                r"Text content. Use \P for a hard line break, e.g. "
                r"'NOTE 1\PNOTE 2'."
            ),
            min_length=1,
        ),
    ],
    position: Annotated[
        list[float], Field(description="Top-left insertion point as [x, y].")
    ],
    width: Annotated[
        float,
        Field(description="Wrapping width of the text box in drawing units.", gt=0),
    ],
    height: Annotated[
        float,
        Field(default=2.5, description="Character height in drawing units.", gt=0),
    ] = 2.5,
    rotation: Annotated[
        float, Field(default=0.0, description="Rotation in DEGREES.")
    ] = 0.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
    annotative: Annotated[bool, ANNOTATIVE_OPT] = False,
) -> str:
    """Place a wrapping block of multiline text.

    Use this for general notes, specification blocks and any text longer than a
    few words.

    Args:
        text (str): Content; "\\P" inserts a line break.
        position (list[float]): [x, y] top-left corner.
        width (float): Wrap width in drawing units.
        height (float): Character height.
        rotation (float): Rotation in degrees.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        space (str): "model" or "paper".
        annotative (bool): make it annotative at the current annotation scale.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "mtext",
             "layer": str, "height": float, "width": float}
             With annotative: also "annotative", "annotation_scales" and
             "paper_height".

    Examples:
        - Use when: "put these four notes in a 3000 wide block of text".
        - Don't use when: it is one short line - autocad_add_text is lighter.
    """
    aci = to_aci(color)

    if annotative:
        require_plugin("Making text annotative")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            entity = get_space(doc, space).AddMText(
                point(position, "position"), float(width), text
            )
            entity.Height = float(height)
            if rotation:
                entity.Rotation = rad(rotation)
            notes = apply_properties(doc, entity, layer, aci, None)
            extra = make_new_annotative([str(entity.Handle)]) if annotative else {}
        return created_payload(entity, notes, height=float(height), width=float(width), **extra)

    return dumps(await run(work))


@mcp.tool(
    name="autocad_add_dimension",
    **tool_meta("Add Dimension"),
)
@tool_errors
async def autocad_add_dimension(
    dimension_type: Annotated[
        str,
        Field(
            default="aligned",
            description=(
                "'aligned' measures the true distance between two points; "
                "'horizontal' and 'vertical' measure only that axis; 'radial' "
                "and 'diametric' annotate a circle or arc; 'angular' measures "
                "the angle at a vertex between two points."
            ),
            pattern="^(aligned|horizontal|vertical|radial|diametric|angular)$",
        ),
    ] = "aligned",
    point1: Annotated[
        list[float] | None,
        Field(
            default=None,
            description=(
                "First measured point as [x, y]. For radial/diametric this is "
                "the circle centre; for angular it is the vertex."
            ),
        ),
    ] = None,
    point2: Annotated[
        list[float] | None,
        Field(
            default=None,
            description=(
                "Second measured point as [x, y]. For radial/diametric this is "
                "a point on the circle."
            ),
        ),
    ] = None,
    point3: Annotated[
        list[float] | None,
        Field(
            default=None,
            description="Third point, required only for 'angular' dimensions.",
        ),
    ] = None,
    text_position: Annotated[
        list[float] | None,
        Field(
            default=None,
            description=(
                "Where the dimension text sits, as [x, y]. Offset it clear of "
                "the geometry, e.g. 500 units below a horizontal dimension. "
                "Defaults to the midpoint of the measured span."
            ),
        ),
    ] = None,
    text_override: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Replace the measured value with this text. Use '<>' inside it "
                "to keep the measurement, e.g. '<> TYP'."
            ),
        ),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
    annotative: Annotated[bool, ANNOTATIVE_OPT] = False,
) -> str:
    """Add a dimension annotating a distance, radius, diameter or angle.

    The dimension takes the drawing's current dimension style, so it follows
    the sheet's standards for arrowheads, text size and units.

    Args:
        dimension_type (str): aligned, horizontal, vertical, radial, diametric
            or angular.
        point1 (Optional[list[float]]): First point / centre / vertex.
        point2 (Optional[list[float]]): Second point / point on circle.
        point3 (Optional[list[float]]): Third point, angular only.
        text_position (Optional[list[float]]): Where the text sits.
        text_override (Optional[str]): Custom text; "<>" embeds the value.
        layer (Optional[str]): Target layer, created if missing.
        space (str): "model" or "paper".
        annotative (bool): make it annotative at the current annotation scale;
            its size then comes from the scale, not from DIMSCALE.

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "dimension",
             "layer": str, "measurement": float, "dimension_type": str}
             With annotative: also "annotative" and "annotation_scales".

    Examples:
        - Use when: "dimension the wall from 0,0 to 5000,0" ->
          dimension_type="horizontal", point1=[0,0], point2=[5000,0],
          text_position=[2500,-500].
        - Use when: "show that circle's diameter" -> dimension_type="diametric"
          with two opposite points on it.

    Error Handling:
        - Names the specific missing argument when a dimension type needs a
          point that was not supplied.
    """

    if annotative:
        require_plugin("Making a dimension annotative")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        target = get_space(doc, space)

        def need(value: Any, label: str) -> Any:
            if value is None:
                raise AutocadError(
                    f"dimension_type='{dimension_type}' requires '{label}'."
                )
            return value

        with undo_mark(doc):
            if dimension_type in {"aligned", "horizontal", "vertical"}:
                need(point1, "point1")
                need(point2, "point2")
                p1 = point(point1, "point1")
                p2 = point(point2, "point2")
                midpoint = [
                    (point1[0] + point2[0]) / 2.0,
                    (point1[1] + point2[1]) / 2.0,
                ]
                text_pt = point(text_position or midpoint, "text_position")
                if dimension_type == "aligned":
                    entity = target.AddDimAligned(p1, p2, text_pt)
                else:
                    # A rotated dimension at 0 deg measures X, at 90 deg measures Y.
                    axis = 0.0 if dimension_type == "horizontal" else 90.0
                    entity = target.AddDimRotated(p1, p2, text_pt, rad(axis))

            elif dimension_type in {"radial", "diametric"}:
                need(point1, "point1")
                need(point2, "point2")
                p1 = point(point1, "point1")
                p2 = point(point2, "point2")
                leader_length = 0.0
                if dimension_type == "radial":
                    entity = target.AddDimRadial(p1, p2, leader_length)
                else:
                    entity = target.AddDimDiametric(p1, p2, leader_length)

            else:  # angular
                need(point1, "point1")
                need(point2, "point2")
                need(point3, "point3")
                entity = target.AddDimAngular(
                    point(point1, "point1"),
                    point(point2, "point2"),
                    point(point3, "point3"),
                    point(text_position or point2, "text_position"),
                )

            if text_override:
                entity.TextOverride = text_override
            # A dimension made over COM ignores the DIMSCALE override, so its
            # text and arrows come out at plain style size (tiny in a 1:10 mm
            # detail, seen live 2026-10-26). Give it the drawing's DIMSCALE,
            # unless it is annotative: its scales size it then (D-81).
            def give_dimscale() -> bool:
                try:
                    scale = float(doc.GetVariable("DIMSCALE") or 0.0)
                    if scale > 0:
                        entity.ScaleFactor = scale
                        return True
                except Exception as exc:  # noqa: BLE001 - keep the dimension at its style size
                    raise_if_busy(exc)
                return False

            if not annotative:
                give_dimscale()
            notes = apply_properties(doc, entity, layer, None, None)
            extra = make_new_annotative([str(entity.Handle)]) if annotative else {}
            if extra.get("not_annotative") and give_dimscale():
                # Not annotative after all: sized by DIMSCALE as any other, never left tiny.
                extra["warning"] += " It was given the drawing's DIMSCALE instead."

        info = describe(entity)
        return created_payload(
            entity,
            notes,
            measurement=info.get("measurement"),
            dimension_type=dimension_type,
            **extra,
        )

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Blocks and hatching
# ---------------------------------------------------------------------------


def dwg_path(raw: str) -> str:
    """A .dwg path as AutoCAD's InsertBlock accepts it.

    InsertBlock answers "Key not found" to forward slashes (measured on
    AutoCAD 2027), so the path is normalised to backslashes.
    """
    # Whole, because AutoCAD would read a relative path from its own folder, not ours.
    resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(raw.strip().strip('"'))))
    if not os.path.isfile(resolved):
        raise AutocadError(f"No .dwg file exists at '{resolved}'.")
    return resolved


@mcp.tool(
    name="autocad_insert_block",
    **tool_meta("Insert Block"),
)
@tool_errors
async def autocad_insert_block(
    block_name: Annotated[
        str,
        Field(
            description=(
                "Name of a block already defined in the drawing, or a full "
                "path to an external .dwg to insert as a new block. "
                "autocad_list_blocks shows what is available."
            ),
            min_length=1,
        ),
    ],
    position: Annotated[list[float], Field(description="Insertion point as [x, y].")],
    scale: Annotated[
        float,
        Field(default=1.0, description="Uniform scale factor, e.g. 1.0 or 0.5.", gt=0),
    ] = 1.0,
    rotation: Annotated[
        float,
        Field(default=0.0, description="Rotation in DEGREES counter-clockwise."),
    ] = 0.0,
    attributes: Annotated[
        dict[str, str] | None,
        Field(
            default=None,
            description=(
                "Attribute values to fill in, keyed by tag, e.g. "
                '{"DOOR_NO": "D-101", "TYPE": "FD60"}. Tags match '
                "case-insensitively."
            ),
        ),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Insert a block reference, optionally filling in its attributes.

    Args:
        block_name (str): Block name, or path to an external .dwg.
        position (list[float]): [x, y] insertion point.
        scale (float): Uniform scale factor.
        rotation (float): Rotation in degrees.
        attributes (Optional[dict[str, str]]): Attribute values by tag.
        layer (Optional[str]): Target layer, created if missing.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "block",
             "layer": str, "block_name": str, "attributes_set": [str],
             "attributes_not_found": [str]}

    Error Handling:
        - Lists the drawing's available block names when the requested one is
          not defined, so the next call can use a valid name.
        - Reports requested attribute tags the block does not have in
          "attributes_not_found" rather than failing the whole insertion.

    Examples:
        - Use when: "put a CAM-DOME at 4500,2300 turned 90" ->
          block_name="CAM-DOME", position=[4500,2300], rotation=90.
        - Use when: the block is not in the drawing yet: pass the .dwg path as
          block_name and it is brought in.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)

        name = block_name.strip().strip('"')
        if name.lower().endswith(".dwg"):
            name = dwg_path(name)
        else:
            try:
                doc.Blocks.Item(name)
            except BaseException as exc:  # noqa: BLE001 - report what does exist
                raise_if_busy(exc)
                available = []
                for i in range(doc.Blocks.Count):
                    block = doc.Blocks.Item(i)
                    block_label = str(block.Name)
                    if not block_label.startswith("*") and not bool(block.IsLayout):
                        available.append(block_label)
                raise AutocadError(
                    f"No block named '{block_name}' is defined in this drawing. "
                    "Available blocks: "
                    + (", ".join(sorted(available)[:40]) if available else "none")
                    + ". To insert from a file, pass the full .dwg path instead."
                ) from None

        with undo_mark(doc):
            entity = get_space(doc, space).InsertBlock(
                point(position, "position"),
                name,
                float(scale),
                float(scale),
                float(scale),
                rad(rotation),
            )
            notes = apply_properties(doc, entity, layer, None, None)

            applied: list[str] = []
            missing: list[str] = []
            if attributes:
                wanted = {k.strip().upper(): v for k, v in attributes.items()}
                found: set[str] = set()
                if bool(entity.HasAttributes):
                    for att in entity.GetAttributes():
                        tag = str(att.TagString).upper()
                        if tag in wanted:
                            att.TextString = str(wanted[tag])
                            applied.append(tag)
                            found.add(tag)
                missing = sorted(set(wanted) - found)

        return created_payload(
            entity,
            notes,
            block_name=str(entity.Name),
            attributes_set=applied,
            attributes_not_found=missing,
        )

    return dumps(await run(work))


AC_HATCH_PREDEFINED = 1
AC_HATCH_CUSTOM = 2


@mcp.tool(
    name="autocad_add_hatch",
    **tool_meta("Add Hatch"),
)
@tool_errors
async def autocad_add_hatch(
    boundary_handles: Annotated[
        list[str],
        Field(
            description=(
                "Handles of the CLOSED entities forming the hatch boundary — "
                "closed polylines, circles or ellipses. Get handles from "
                "autocad_list_entities or from the tool that drew them."
            ),
            min_length=1,
        ),
    ],
    pattern: Annotated[
        str,
        Field(
            default="SOLID",
            description=(
                "Pattern name: 'SOLID' for a filled region, a predefined "
                "pattern such as 'ANSI31' (diagonal), 'AR-CONC' (concrete), "
                "'EARTH', 'BRICK', 'STEEL', 'NET', or a custom one made with "
                "autocad_create_hatch_pattern."
            ),
        ),
    ] = "SOLID",
    scale: Annotated[
        float,
        Field(
            default=1.0,
            description=(
                "Pattern scale, ignored for SOLID. Increase it when the pattern "
                "renders as a dense smudge in a large-unit drawing."
            ),
            gt=0,
        ),
    ] = 1.0,
    angle: Annotated[
        float, Field(default=0.0, description="Pattern rotation in DEGREES.")
    ] = 0.0,
    associative: Annotated[
        bool,
        Field(
            default=True,
            description="Update the hatch automatically when its boundary moves.",
        ),
    ] = True,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
) -> str:
    """Fill a closed boundary with a solid fill or a hatch pattern.

    The boundary must already exist and be closed — draw it first with
    autocad_draw_polyline (closed=true), autocad_draw_rectangle or
    autocad_draw_circle, then pass the handle that tool returned.

    Args:
        boundary_handles (list[str]): Handles of closed boundary entities.
        pattern (str): "SOLID" or a predefined pattern name.
        scale (float): Pattern scale.
        angle (float): Pattern angle in degrees.
        associative (bool): Keep the hatch linked to its boundary.
        layer (Optional[str]): Target layer, created if missing.
        color (Optional[str | int]): Colour name or ACI number.
        space (str): "model" or "paper".

    Returns:
        str: JSON: {"created": true, "handle": str, "type": "hatch",
             "layer": str, "pattern": str, "area": float}

    Error Handling:
        - Names the offending handle when a boundary entity is an open shape,
          which is the usual cause of a failed hatch.

    Examples:
        - Use when: "hatch that slab as concrete" -> pattern="AR-CONC" round
          the slab's boundary.
        - Use when: you want a solid fill - pattern="SOLID".
    """
    aci = to_aci(color)
    pattern_name = pattern.strip().upper()

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)

        boundaries = []
        for handle in boundary_handles:
            obj = resolve_handle(doc, handle)
            is_closed = True
            try:
                if str(obj.ObjectName) in {"AcDbPolyline", "AcDb2dPolyline"}:
                    is_closed = bool(obj.Closed)
            except BaseException as exc:  # noqa: BLE001 - circles/ellipses are always closed
                raise_if_busy(exc)
            if not is_closed:
                raise AutocadError(
                    f"Entity {handle} is an open polyline, so it cannot bound a "
                    "hatch. Close it with autocad_modify_entity (closed=true), "
                    "or pass a closed boundary."
                )
            boundaries.append(obj)

        with undo_mark(doc):
            # AcPatternType: 0 user-defined, 1 predefined (a name from acad.pat,
            # SOLID included), 2 custom (its own NAME.pat on the support path,
            # as autocad_create_hatch_pattern writes). Type 0 with 'ANSI31' is
            # refused as a bad name, so it is never sent.
            target = get_space(doc, space)
            try:
                entity = target.AddHatch(AC_HATCH_PREDEFINED, pattern_name, associative)
            except BaseException as first:  # noqa: BLE001 - not in acad.pat: try its own file
                if is_retryable(first) or is_dispatch_failure(first):
                    raise  # busy or disconnected, not a missing pattern
                try:
                    entity = target.AddHatch(AC_HATCH_CUSTOM, pattern_name, associative)
                except BaseException as exc:  # noqa: BLE001
                    raise_if_busy(exc)
                    raise AutocadError(
                        f"There is no hatch pattern called '{pattern_name}' in acad.pat, nor a "
                        f"{pattern_name}.pat on the support path ({com_message(first)}). Check the "
                        "name, or make it with autocad_create_hatch_pattern."
                    ) from first
            entity.AppendOuterLoop(object_array(boundaries))
            if pattern_name != "SOLID":
                entity.PatternScale = float(scale)
                entity.PatternAngle = rad(angle)
            notes = apply_properties(doc, entity, layer, aci, None)
            entity.Evaluate()

        info = describe(entity)
        return created_payload(
            entity, notes, pattern=info.get("pattern"), area=info.get("area")
        )

    return dumps(await run(work))
