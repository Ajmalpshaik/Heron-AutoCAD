"""Tools that change or remove existing entities.

All of these address entities by handle and wrap their work in a single undo
mark, so any one call can be reversed with one Ctrl+Z in AutoCAD.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..acad import props
from ..acad.entities import describe, resolve_handle, short_type
from ..acad.tables import ensure_layer, ensure_linetype
from ..acad.units import rad
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ._shared import HANDLES_OPT, before_after, point, same_value


# Applying one operation across many entities should not abort everything
# because one entity refused it, so failures are collected and reported.
def _apply_each(
    doc: Any, handles: list[str], action: Callable[[Any], None], verb: str
) -> dict[str, Any]:
    """Run ``action`` on each handle, collecting per-entity failures."""
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    for handle in handles:
        entity = resolve_handle(doc, handle)
        try:
            action(entity)
            succeeded.append(handle)
        except AutocadError as exc:
            failed.append({"handle": handle, "reason": str(exc)})
        except BaseException as exc:  # noqa: BLE001 - report, do not abort
            failed.append(
                {
                    "handle": handle,
                    "type": short_type(entity),
                    "reason": com_message(exc),
                }
            )
    result: dict[str, Any] = {
        verb: len(succeeded),
        "handles": succeeded,
    }
    if failed:
        result["failed"] = failed
        result["hint"] = (
            "Entities usually refuse a change because their layer is locked or "
            "frozen. Unlock it with autocad_set_layer_state, then retry."
        )
    return result


@mcp.tool(
    name="autocad_move_entities",
    **tool_meta("Move Entities"),
)
@tool_errors
async def autocad_move_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    displacement: Annotated[
        list[float] | None,
        Field(
            default=None,
            description=(
                "How far to move, as [dx, dy] or [dx, dy, dz], e.g. [1000, 0] "
                "to shift 1000 units right. Give this or from_point/to_point."
            ),
        ),
    ] = None,
    from_point: Annotated[
        list[float] | None,
        Field(
            default=None,
            description="Base point as [x, y], used with to_point.",
        ),
    ] = None,
    to_point: Annotated[
        list[float] | None,
        Field(
            default=None,
            description="Destination point as [x, y], used with from_point.",
        ),
    ] = None,
) -> str:
    """Move entities by a displacement, or from one point to another.

    Args:
        handles (list[str]): Handles of entities to move.
        displacement (Optional[list[float]]): [dx, dy] offset.
        from_point (Optional[list[float]]): Base point, with to_point.
        to_point (Optional[list[float]]): Destination, with from_point.

    Returns:
        str: JSON: {"moved": int, "handles": [str], "displacement": [dx, dy, dz]}
             Plus "failed" listing any entity that refused, with the reason.

    Examples:
        - Use when: "shift those 3 m to the right" -> displacement=[3000, 0]
          in a millimetre drawing.
        - Use when: "move it from the corner to the centre" -> from_point and
          to_point.
    """
    if displacement:
        dx = float(displacement[0])
        dy = float(displacement[1]) if len(displacement) > 1 else 0.0
        dz = float(displacement[2]) if len(displacement) > 2 else 0.0
    elif from_point and to_point:
        dx = float(to_point[0]) - float(from_point[0])
        dy = float(to_point[1]) - float(from_point[1])
        dz = (float(to_point[2]) if len(to_point) > 2 else 0.0) - (
            float(from_point[2]) if len(from_point) > 2 else 0.0
        )
    else:
        raise AutocadError(
            "Give either 'displacement' as [dx, dy], or both 'from_point' and "
            "'to_point'."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        origin = point([0, 0, 0], "origin")
        target = point([dx, dy, dz], "displacement")
        with undo_mark(doc):
            result = _apply_each(
                doc, handles, lambda e: e.Move(origin, target), "moved"
            )
        result["displacement"] = [round(dx, 6), round(dy, 6), round(dz, 6)]
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_copy_entities",
    **tool_meta("Copy Entities"),
)
@tool_errors
async def autocad_copy_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    displacement: Annotated[
        list[float],
        Field(
            description=(
                "Offset of the copy from the original, as [dx, dy], e.g. "
                "[0, -600] to place it 600 units below."
            )
        ),
    ],
    count: Annotated[
        int,
        Field(
            default=1,
            description=(
                "How many copies to make. Each is offset a further "
                "'displacement' from the last, giving an evenly spaced row."
            ),
            ge=1,
            le=500,
        ),
    ] = 1,
) -> str:
    """Copy entities to a new position, optionally repeating in a row.

    Args:
        handles (list[str]): Handles of entities to copy.
        displacement (list[float]): [dx, dy] offset per copy.
        count (int): Number of copies, 1-500.

    Returns:
        str: JSON: {"copied": int, "source_count": int, "count": int,
             "new_handles": [str]}

    Examples:
        - Use when: "put a copy 600 below" -> displacement=[0, -600].
        - Use when: "space 5 of them 1200 apart along X" ->
          displacement=[1200, 0], count=5.
        - Don't use when: you want a grid or a ring — use
          autocad_array_entities.
    """
    dx = float(displacement[0])
    dy = float(displacement[1]) if len(displacement) > 1 else 0.0
    dz = float(displacement[2]) if len(displacement) > 2 else 0.0

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        new_handles: list[str] = []
        failed: list[dict[str, str]] = []
        origin = point([0, 0, 0], "origin")

        with undo_mark(doc):
            for handle in handles:
                source = resolve_handle(doc, handle)
                for step in range(1, count + 1):
                    try:
                        duplicate = source.Copy()
                        duplicate.Move(
                            origin, point([dx * step, dy * step, dz * step], "offset")
                        )
                        new_handles.append(str(duplicate.Handle))
                    except BaseException as exc:  # noqa: BLE001
                        failed.append({"handle": handle, "reason": com_message(exc)})
                        break

        result: dict[str, Any] = {
            "copied": len(new_handles),
            "source_count": len(handles),
            "count": count,
            "new_handles": new_handles,
        }
        if failed:
            result["failed"] = failed
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_rotate_entities",
    **tool_meta("Rotate Entities"),
)
@tool_errors
async def autocad_rotate_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    base_point: Annotated[
        list[float],
        Field(description="Point to rotate about, as [x, y]."),
    ],
    angle: Annotated[
        float,
        Field(
            description=(
                "Rotation in DEGREES. Positive is counter-clockwise, negative "
                "is clockwise."
            )
        ),
    ],
) -> str:
    """Rotate entities about a base point.

    Args:
        handles (list[str]): Handles of entities to rotate.
        base_point (list[float]): [x, y] pivot.
        angle (float): Rotation in degrees, counter-clockwise positive.

    Returns:
        str: JSON: {"rotated": int, "handles": [str], "angle_degrees": float,
             "base_point": [x, y]}

    Examples:
        - Use when: "turn that 90 degrees about the origin" ->
          base_point=[0,0], angle=90.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        pivot = point(base_point, "base_point")
        radians = rad(angle)
        with undo_mark(doc):
            result = _apply_each(
                doc, handles, lambda e: e.Rotate(pivot, radians), "rotated"
            )
        result["angle_degrees"] = angle
        result["base_point"] = [float(base_point[0]), float(base_point[1])]
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_scale_entities",
    **tool_meta("Scale Entities"),
)
@tool_errors
async def autocad_scale_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    base_point: Annotated[
        list[float],
        Field(
            description=(
                "The point that stays fixed while everything scales around it, "
                "as [x, y]."
            )
        ),
    ],
    factor: Annotated[
        float,
        Field(
            description=(
                "Scale factor: 2 doubles the size, 0.5 halves it. Must be "
                "greater than zero."
            ),
            gt=0,
        ),
    ],
) -> str:
    """Scale entities uniformly about a base point.

    Args:
        handles (list[str]): Handles of entities to scale.
        base_point (list[float]): [x, y] fixed point.
        factor (float): Uniform scale factor, greater than zero.

    Returns:
        str: JSON: {"scaled": int, "handles": [str], "factor": float,
             "base_point": [x, y]}

    Examples:
        - Use when: "this detail came in at 1:10, make it full size" ->
          scale_factor=10 about a base point you can check afterwards.
        - Don't use when: you only want the plot bigger - that is the
          viewport scale, autocad_add_viewport.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        anchor = point(base_point, "base_point")
        with undo_mark(doc):
            result = _apply_each(
                doc, handles, lambda e: e.ScaleEntity(anchor, float(factor)), "scaled"
            )
        result["factor"] = float(factor)
        result["base_point"] = [float(base_point[0]), float(base_point[1])]
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_mirror_entities",
    **tool_meta("Mirror Entities"),
)
@tool_errors
async def autocad_mirror_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    axis_point1: Annotated[
        list[float],
        Field(description="First point on the mirror line, as [x, y]."),
    ],
    axis_point2: Annotated[
        list[float],
        Field(description="Second point on the mirror line, as [x, y]."),
    ],
    delete_original: Annotated[
        bool,
        Field(
            default=False,
            description="Remove the originals, leaving only the mirrored copies.",
        ),
    ] = False,
) -> str:
    """Mirror entities across a line defined by two points.

    Args:
        handles (list[str]): Handles of entities to mirror.
        axis_point1 (list[float]): [x, y] first point on the mirror line.
        axis_point2 (list[float]): [x, y] second point on the mirror line.
        delete_original (bool): Delete the source entities afterwards.

    Returns:
        str: JSON: {"mirrored": int, "new_handles": [str],
             "originals_deleted": bool}

    Examples:
        - Use when: "mirror this about the vertical centreline at x=5000" ->
          axis_point1=[5000,0], axis_point2=[5000,1000].
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        p1 = point(axis_point1, "axis_point1")
        p2 = point(axis_point2, "axis_point2")
        new_handles: list[str] = []
        failed: list[dict[str, str]] = []

        with undo_mark(doc):
            for handle in handles:
                source = resolve_handle(doc, handle)
                try:
                    mirrored = source.Mirror(p1, p2)
                    new_handles.append(str(mirrored.Handle))
                    if delete_original:
                        source.Delete()
                except BaseException as exc:  # noqa: BLE001
                    failed.append({"handle": handle, "reason": com_message(exc)})

        result: dict[str, Any] = {
            "mirrored": len(new_handles),
            "new_handles": new_handles,
            "originals_deleted": delete_original,
        }
        if failed:
            result["failed"] = failed
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_offset_entities",
    **tool_meta("Offset Entities"),
)
@tool_errors
async def autocad_offset_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    distance: Annotated[
        float,
        Field(
            description=(
                "Offset distance. Positive offsets outward or to the left of "
                "the direction of travel; negative offsets the other way. For a "
                "circle, positive grows the radius."
            )
        ),
    ],
    both_sides: Annotated[
        bool,
        Field(description="Offset to both sides at once, e.g. a duct or pipe's two edges from its centreline."),
    ] = False,
) -> str:
    """Create parallel copies of lines, polylines, arcs and circles.

    This is how wall thicknesses, kerbs, setbacks and pipe runs get drawn from
    a single centreline.

    Args:
        handles (list[str]): Handles of entities to offset.
        distance (float): Offset distance; sign sets the side.

    Returns:
        str: JSON: {"offset": int, "new_handles": [str], "distance": float}

    Error Handling:
        - Text, blocks, hatches and dimensions cannot be offset; each is
          reported in "failed" with its type rather than aborting the call.

    Examples:
        - Use when: "give me the inside face of that wall, 200 in" ->
          distance=200, side towards the point you name.
        - Use when: "a kerb line 150 either side" -> both_sides=true.
    """
    if distance == 0:
        raise AutocadError("An offset distance of 0 would just duplicate in place.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        new_handles: list[str] = []
        failed: list[dict[str, str]] = []

        with undo_mark(doc):
            for handle in handles:
                source = resolve_handle(doc, handle)
                try:
                    # Offset returns an array of results: a closed shape can
                    # yield more than one curve.
                    for d in (float(distance), -float(distance)) if both_sides else (float(distance),):
                        for result in source.Offset(d):
                            new_handles.append(str(result.Handle))
                except BaseException as exc:  # noqa: BLE001
                    failed.append(
                        {
                            "handle": handle,
                            "type": short_type(source),
                            "reason": com_message(exc),
                        }
                    )

        result: dict[str, Any] = {
            "offset": len(new_handles),
            "new_handles": new_handles,
            "distance": float(distance),
        }
        if failed:
            result["failed"] = failed
            result["hint"] = (
                "Only curves can be offset — lines, polylines, arcs, circles, "
                "ellipses and splines. Text, blocks, hatches and dimensions "
                "cannot; copy those with autocad_copy_entities instead."
            )
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_array_entities",
    **tool_meta("Array Entities"),
)
@tool_errors
async def autocad_array_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    pattern: Annotated[
        str,
        Field(
            default="rectangular",
            description=(
                "'rectangular' makes a grid of rows and columns; 'polar' makes "
                "a ring about a centre point."
            ),
            pattern="^(rectangular|polar)$",
        ),
    ] = "rectangular",
    rows: Annotated[
        int,
        Field(default=1, description="Rows, for a rectangular array.", ge=1, le=200),
    ] = 1,
    columns: Annotated[
        int,
        Field(default=1, description="Columns, for a rectangular array.", ge=1, le=200),
    ] = 1,
    row_spacing: Annotated[
        float,
        Field(
            default=0.0,
            description=(
                "Distance between rows. Negative builds the grid downward."
            ),
        ),
    ] = 0.0,
    column_spacing: Annotated[
        float,
        Field(
            default=0.0,
            description="Distance between columns. Negative builds it leftward.",
        ),
    ] = 0.0,
    count: Annotated[
        int,
        Field(
            default=4,
            description=(
                "Total items in a polar array, including the original."
            ),
            ge=2,
            le=500,
        ),
    ] = 4,
    center: Annotated[
        list[float] | None,
        Field(
            default=None,
            description="Centre of a polar array, as [x, y]. Required for polar.",
        ),
    ] = None,
    fill_angle: Annotated[
        float,
        Field(
            default=360.0,
            description=(
                "Total angle a polar array spans, in DEGREES. 360 spreads the "
                "items evenly around a full circle; 90 fills a quarter."
            ),
        ),
    ] = 360.0,
) -> str:
    """Repeat entities in a rectangular grid or a polar ring.

    Args:
        handles (list[str]): Handles of entities to array.
        pattern (str): "rectangular" or "polar".
        rows (int): Rows, rectangular only.
        columns (int): Columns, rectangular only.
        row_spacing (float): Distance between rows.
        column_spacing (float): Distance between columns.
        count (int): Total items, polar only.
        center (Optional[list[float]]): [x, y] centre, polar only.
        fill_angle (float): Degrees the polar array spans.

    Returns:
        str: JSON: {"arrayed": int, "pattern": str, "new_handles": [str],
             "items_per_source": int}

    Examples:
        - Use when: "5 columns of holes 200 apart, 3 rows 150 apart" ->
          rectangular, rows=3, columns=5, row_spacing=150, column_spacing=200.
        - Use when: "8 bolts evenly round that circle" -> polar, count=8,
          center=the circle centre.

    Error Handling:
        - Rejects a rectangular array of 1x1, and a polar array with no centre,
          before AutoCAD is asked to build it.
    """
    if pattern == "rectangular":
        if rows == 1 and columns == 1:
            raise AutocadError(
                "A 1x1 rectangular array makes no copies. Increase 'rows' or "
                "'columns'."
            )
        if rows > 1 and row_spacing == 0:
            raise AutocadError(
                f"rows={rows} needs a non-zero 'row_spacing', or every copy "
                "lands on top of the original."
            )
        if columns > 1 and column_spacing == 0:
            raise AutocadError(
                f"columns={columns} needs a non-zero 'column_spacing', or every "
                "copy lands on top of the original."
            )
    elif not center:
        raise AutocadError("A polar array needs 'center' as [x, y].")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        new_handles: list[str] = []
        failed: list[dict[str, str]] = []

        with undo_mark(doc):
            for handle in handles:
                source = resolve_handle(doc, handle)
                try:
                    if pattern == "rectangular":
                        results = source.ArrayRectangular(
                            int(rows),
                            int(columns),
                            1,
                            float(row_spacing),
                            float(column_spacing),
                            0.0,
                        )
                    else:
                        results = source.ArrayPolar(
                            int(count), rad(fill_angle), point(center, "center")
                        )
                    for item in results:
                        new_handles.append(str(item.Handle))
                except BaseException as exc:  # noqa: BLE001
                    failed.append({"handle": handle, "reason": com_message(exc)})

        per_source = (rows * columns) if pattern == "rectangular" else count
        result: dict[str, Any] = {
            "arrayed": len(new_handles),
            "pattern": pattern,
            "items_per_source": per_source,
            "new_handles": new_handles,
            "note": (
                "AutoCAD's array includes the original position in the count, "
                "so new_handles holds the copies it created."
            ),
        }
        if failed:
            result["failed"] = failed
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_modify_entity",
    **tool_meta("Modify Entity Properties", idempotent=True),
)
@tool_errors
async def autocad_modify_entity(
    handles: Annotated[list[str], HANDLES_OPT],
    layer: Annotated[
        str | None,
        Field(
            default=None,
            description="Move the entities to this layer, creating it if needed.",
        ),
    ] = None,
    color: Annotated[
        str | StrictInt | None,
        Field(
            default=None,
            description=(
                "New colour: a name ('red', 'bylayer') or an ACI number 0-256."
            ),
        ),
    ] = None,
    linetype: Annotated[
        str | None,
        Field(default=None, description="New linetype, e.g. 'HIDDEN', 'CENTER'."),
    ] = None,
    text: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Replace the content of text and mtext entities. Ignored for "
                "other types."
            ),
        ),
    ] = None,
    height: Annotated[
        float | None,
        Field(
            default=None,
            description="New character height for text and mtext entities.",
            gt=0,
        ),
    ] = None,
    radius: Annotated[
        float | None,
        Field(
            default=None,
            description="New radius for circles and arcs.",
            gt=0,
        ),
    ] = None,
    closed: Annotated[
        bool | None,
        Field(
            default=None,
            description=(
                "Open or close a polyline. Closing one lets it bound a hatch "
                "and gives it an area."
            ),
        ),
    ] = None,
    lineweight: Annotated[
        str | float | None,
        Field(
            default=None,
            description=(
                "New lineweight: millimetres as AutoCAD lists them (0.25, 0.35, 0.50 ...), "
                "hundredths (25), or 'ByLayer', 'ByBlock', 'Default'."
            ),
        ),
    ] = None,
    transparency: Annotated[
        str | int | None,
        Field(
            default=None,
            description="New transparency: 0 (solid) to 90, or 'ByLayer', 'ByBlock'.",
        ),
    ] = None,
    layer_lock_override: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Temporarily unlock a locked layer to make the change, then "
                "lock it again. Off by default, since a locked layer is "
                "usually locked deliberately."
            ),
        ),
    ] = False,
) -> str:
    """Change properties of existing entities.

    Only the arguments you pass are changed; everything else is left alone.
    Properties that do not apply to an entity's type are skipped for that
    entity and reported, so a mixed selection does not fail as a whole.

    Args:
        handles (list[str]): Handles of entities to modify.
        layer (Optional[str]): New layer.
        color (Optional[str | int]): New colour.
        linetype (Optional[str]): New linetype.
        text (Optional[str]): New content for text/mtext.
        height (Optional[float]): New height for text/mtext.
        radius (Optional[float]): New radius for circles/arcs.
        closed (Optional[bool]): Open or close a polyline.
        lineweight (Optional[str | float]): New lineweight, mm or ByLayer.
        transparency (Optional[str | int]): New transparency, 0-90 or ByLayer.
        layer_lock_override (bool): Unlock locked layers for the change.

    Returns:
        str: JSON: {"modified": int, "handles": [str], "applied": [str],
             "before_after": [{"handle", "property", "from", "to"}] (first 50),
             "already": [str], "skipped": [{"handle": str, "type": str, "property": str}]}

    Examples:
        - Use when: "put those on layer A-WALL and make them red" ->
          layer="A-WALL", color="red".
        - Use when: "fix that label to say ROOM 12" -> text="ROOM 12".
        - Use when: "make the existing services 0.18 and 50% see-through" ->
          lineweight=0.18, transparency=50.
        - Don't use when: the values should come from another object - use
          autocad_match_properties.

    Error Handling:
        - Reports a locked layer explicitly, and can work around it when
          layer_lock_override is true.
    """
    aci = to_aci(color)
    requested = {
        "layer": layer,
        "color": aci,
        "linetype": linetype,
        "text": text,
        "height": height,
        "radius": radius,
        "closed": closed,
        "lineweight": props.lineweight_value(lineweight) if lineweight is not None else None,
        "transparency": props.transparency_value(transparency) if transparency is not None else None,
    }
    if all(v is None for v in requested.values()):
        raise AutocadError(
            "No changes requested. Pass at least one of: layer, color, "
            "linetype, text, height, radius, closed, lineweight, transparency."
        )

    def read(entity: Any, kind: str, prop: str) -> Any:
        """The value now, so only what differs is written and old -> new is reported."""
        if prop == "layer":
            return str(entity.Layer)
        if prop == "color":
            return int(entity.Color)
        if prop == "linetype":
            return str(entity.Linetype)
        if prop == "text":
            if kind not in {"text", "mtext"}:
                raise TypeError("not a text entity")
            return str(entity.TextString)
        if prop == "height":
            return float(entity.Height)
        if prop == "radius":
            if kind not in {"circle", "arc"}:
                raise TypeError("has no radius")
            return float(entity.Radius)
        if prop == "lineweight":
            return int(entity.Lineweight)
        if prop == "transparency":
            return str(entity.EntityTransparency)
        return bool(entity.Closed)

    def write(entity: Any, prop: str, value: Any) -> None:
        if prop == "layer":
            entity.Layer = str(value).strip()
        elif prop == "color":
            entity.Color = value
        elif prop == "linetype":
            entity.Linetype = str(value).strip()
        elif prop == "text":
            entity.TextString = str(value)
        elif prop == "height":
            entity.Height = float(value)
        elif prop == "radius":
            entity.Radius = float(value)
        elif prop == "closed":
            entity.Closed = bool(value)
        elif prop == "lineweight":
            entity.Lineweight = int(value)
        elif prop == "transparency":
            entity.EntityTransparency = str(value)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        applied: set[str] = set()
        skipped: list[dict[str, str]] = []
        succeeded: list[str] = []
        failed: list[dict[str, str]] = []
        already: list[str] = []
        rows: list[dict[str, Any]] = []
        unlocked: list[Any] = []

        # First look: what each entity has now. Only a value that differs is
        # written, and an entity with nothing to change opens no undo step.
        plans: list[tuple[str, Any, list[tuple[str, Any, Any]]]] = []
        for handle in handles:
            entity = resolve_handle(doc, handle)
            kind = short_type(entity)
            changes: list[tuple[str, Any, Any]] = []
            for prop, value in requested.items():
                if value is None:
                    continue
                try:
                    old = read(entity, kind, prop)
                except BaseException:  # noqa: BLE001 - wrong type for this prop
                    skipped.append({"handle": handle, "type": kind, "property": prop})
                    continue
                if not same_value(old, str(value).strip() if prop in ("layer", "linetype") else value):
                    changes.append((prop, old, value))
            if changes:
                plans.append((handle, entity, changes))
            elif not any(row["handle"] == handle for row in skipped):
                already.append(handle)

        if plans:
            with undo_mark(doc):
                if layer and any(prop == "layer" for _, _, changes in plans for prop, _, _ in changes):
                    ensure_layer(doc, layer)
                if linetype and any(prop == "linetype" for _, _, changes in plans for prop, _, _ in changes):
                    ensure_linetype(doc, linetype)

                for handle, entity, changes in plans:
                    if layer_lock_override:
                        try:
                            entity_layer = doc.Layers.Item(str(entity.Layer))
                            if bool(entity_layer.Lock):
                                entity_layer.Lock = False
                                unlocked.append(entity_layer)
                        except BaseException:  # noqa: BLE001 - best effort
                            pass

                    changed_any = False
                    for prop, old, value in changes:
                        try:
                            write(entity, prop, value)
                            applied.add(prop)
                            changed_any = True
                            rows.append({"handle": handle, "property": prop, "from": old, "to": value})
                        except BaseException:  # noqa: BLE001 - AutoCAD would not take it
                            skipped.append({"handle": handle, "type": short_type(entity), "property": prop})

                    if changed_any:
                        try:
                            entity.Update()
                            succeeded.append(handle)
                        except BaseException as exc:  # noqa: BLE001
                            failed.append({"handle": handle, "reason": com_message(exc)})

                for entity_layer in unlocked:
                    try:
                        entity_layer.Lock = True
                    except BaseException:  # noqa: BLE001
                        pass

        result: dict[str, Any] = {
            "modified": len(succeeded),
            "handles": succeeded,
            "applied": sorted(applied),
            **before_after(rows),
        }
        if already:
            result["already"] = already
            result["already_note"] = "These already had the values asked for; nothing was written to them."
        if skipped:
            result["skipped"] = skipped
            result["skipped_note"] = (
                "Those properties do not exist on those entity types and were "
                "left unchanged."
            )
        if failed:
            result["failed"] = failed
            result["hint"] = (
                "A failure here usually means the entity's layer is locked. "
                "Retry with layer_lock_override=true, or unlock the layer with "
                "autocad_set_layer_state."
            )
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_delete_entities",
    **tool_meta("Delete Entities", destructive=True),
)
@tool_errors
async def autocad_delete_entities(
    handles: Annotated[list[str], HANDLES_OPT],
    confirm: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Must be true for the deletion to run. Set it only after the "
                "user has confirmed which entities to remove."
            ),
        ),
    ] = False,
) -> str:
    """Delete entities from the drawing.

    This removes geometry. The whole call lands as one undo step, so the user
    can restore it with a single Ctrl+Z in AutoCAD — but nothing else brings it
    back once the drawing is saved and closed.

    Confirm what will be deleted with the user before setting confirm=true. If
    you are unsure which entities the handles refer to, inspect them first with
    autocad_get_entity.

    Args:
        handles (list[str]): Handles of entities to delete.
        confirm (bool): Must be true to proceed.

    Returns:
        str: JSON: {"deleted": int, "handles": [str]}
             With confirm=false: a preview of what would be deleted, and no
             change to the drawing.

    Examples:
        - Use when: the user has explicitly asked to delete specific objects.
        - Don't use when: you only want to hide things — freeze the layer with
          autocad_set_layer_state instead.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)

        if not confirm:
            preview = []
            for handle in handles:
                entity = resolve_handle(doc, handle)
                preview.append(describe(entity, include_geometry=False))
            return {
                "deleted": 0,
                "would_delete": len(preview),
                "entities": preview,
                "confirmed": False,
                "next_step": (
                    "Nothing was deleted. Show this list to the user, and call "
                    "again with confirm=true once they agree."
                ),
            }

        with undo_mark(doc):
            result = _apply_each(doc, handles, lambda e: e.Delete(), "deleted")
        result["confirmed"] = True
        return result

    return dumps(await run(work))
