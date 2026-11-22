"""The UCS, and points moved between it and the world.

Why this exists: every coordinate AutoCAD's Automation API takes is a **world**
coordinate, but a modeller sets a UCS and then reads and types coordinates in
it. On a wing of a building turned 23 degrees, "draw a line from 0,0 to 5000,0"
means two different lines depending on which system you meant, and the drawing
gives no hint which one the agent used.

So: ``autocad_get_ucs`` says what is set, ``autocad_set_ucs`` sets it, and
``autocad_convert_points`` moves points between the two. ``autocad_status``
reports the same thing on every drawing, so nothing is drawn blind.

The arithmetic is in ``acad/coords.py`` and tested without AutoCAD.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.coords import Ucs, advice, as_vec3
from ..acad.units import deg
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.gate import quiet_sender
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint
from ._shared import current_ucs

# The one named UCS this server writes, reused every time rather than adding a
# new entry per call: a drawing that has been worked on for an hour should not
# end up with forty leftover coordinate systems. Give save_as to keep one under
# your own name instead.
WORKING_UCS = "HERON-UCS"

SetMode = Literal["world", "named", "origin", "3point", "entity", "view"]


def _named_ucs(doc: Any) -> dict[str, Any]:
    out = {}
    for i in range(int(doc.UserCoordinateSystems.Count)):
        item = doc.UserCoordinateSystems.Item(i)
        out[str(item.Name)] = item
    return out


def _describe_saved(item: Any) -> dict[str, Any]:
    """One saved UCS from the table, as far as it can be read."""
    row: dict[str, Any] = {"name": str(item.Name)}
    try:
        ucs = Ucs.build(
            as_vec3(item.Origin), as_vec3(item.XVector), as_vec3(item.YVector)
        )
        row.update(
            {
                "origin": [round(v, 9) for v in ucs.origin],
                "rotation_degrees": ucs.rotation_degrees,
                "tilted": ucs.tilted,
            }
        )
    except Exception as exc:  # noqa: BLE001 - a listing must not fail on one unreadable row
        raise_if_busy(exc)
        row["readable"] = False
    return row


def _ucs_name(doc: Any) -> str:
    try:
        return str(doc.GetVariable("UCSNAME")).strip()
    except BaseException as exc:  # noqa: BLE001 - unnamed UCS reads back empty anyway
        raise_if_busy(exc)
        return ""


def _send(doc: Any, lines: list[str]) -> None:
    """Type command lines into AutoCAD, with the plug-in's echo off when it is there.

    Same path as autocad_batch_draw: the Heron plug-in types them quietly
    inside this job, and without it they go over COM and show in the command
    history.
    """
    sender = quiet_sender()
    if sender and sender(lines):
        return
    for line in lines:
        doc.SendCommand(line + "\n")


@mcp.tool(
    name="autocad_get_ucs",
    **tool_meta("Read The Coordinate System", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_get_ucs() -> str:
    """Report the drawing's current UCS: is it moved, turned or tilted?

    Call this before giving coordinates read off the modeller's screen. Every
    coordinate in this server is a world coordinate; if the UCS is turned 23
    degrees, "0,0 to 5000,0" draws a different line in each system.

    Returns:
        str: JSON: {
          "current": {
            "name", "is_world", "origin", "x_axis", "y_axis", "z_axis",
            "rotation_degrees", "moved", "rotated", "tilted", "flipped"
          },
          "space": "model" | "paper",
          "elevation": float,          # current ELEVATION in this space
          "advice": str | null,        # what to do about it, when not world
          "saved": [{"name", "origin", "rotation_degrees", "tilted"}]
        }

    Examples:
        - Use when: the modeller says "my UCS is rotated" or a drawn line comes
          out at the wrong angle.
        - Use when: picking up a drawing someone else set up.
        - Don't use when: you only need the units (autocad_status gives both).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        ucs = current_ucs(doc)
        result: dict[str, Any] = {
            "current": ucs.describe(_ucs_name(doc) or None),
            "space": "model" if int(doc.ActiveSpace) == 1 else "paper",
        }
        for key, variable in (("elevation", "ELEVATION"), ("thickness", "THICKNESS")):
            try:
                result[key] = round(float(doc.GetVariable(variable)), 9)
            except BaseException as exc:  # noqa: BLE001 - old drawings may not carry it
                raise_if_busy(exc)
                result[key] = None
        result["advice"] = advice(ucs)
        result["saved"] = [
            _describe_saved(item) for item in _named_ucs(doc).values()
        ]
        return result

    return dumps(await run(work))


@mcp.tool(name="autocad_set_ucs", **tool_meta("Set The Coordinate System"))
@tool_errors
async def autocad_set_ucs(
    mode: Annotated[
        SetMode,
        Field(
            description=(
                "'world' goes back to the World Coordinate System. "
                "'named' makes a saved UCS current. "
                "'origin' moves to a point and optionally turns by an angle. "
                "'3point' sets origin, a point on the new X and a point on the new Y. "
                "'entity' lines the UCS up with one object's own plane and direction. "
                "'view' lays it flat on the screen, for reading text off a tilted view."
            )
        ),
    ],
    name: Annotated[
        str | None,
        Field(default=None, description="For mode='named': the saved UCS to make current."),
    ] = None,
    origin: Annotated[
        list[float] | None,
        Field(default=None, description="World [x, y] or [x, y, z] for the new origin."),
    ] = None,
    rotation: Annotated[
        float,
        Field(default=0.0, description="For mode='origin': degrees to turn about Z, anticlockwise."),
    ] = 0.0,
    point_on_x: Annotated[
        list[float] | None,
        Field(default=None, description="For mode='3point': a world point on the new X axis."),
    ] = None,
    point_on_y: Annotated[
        list[float] | None,
        Field(default=None, description="For mode='3point': a world point on the new Y axis."),
    ] = None,
    handle: Annotated[
        str | None,
        Field(default=None, description="For mode='entity': the object to line up with."),
    ] = None,
    save_as: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Save this UCS under a name you can come back to, e.g. 'WING-B'. "
                f"Without it the UCS is stored as '{WORKING_UCS}', which this "
                "server reuses and overwrites each time."
            ),
        ),
    ] = None,
) -> str:
    """Set the drawing's UCS: back to world, onto a saved one, or onto a wall or grid.

    What the modeller sees: the UCS icon moves and turns, and from then on they
    type coordinates in the new system. This server still takes world
    coordinates everywhere — pass coords='ucs' on a tool that offers it, or
    convert with autocad_convert_points.

    One undo step. The UCS is saved with the drawing, so it stays set after the
    call; go back with mode='world'.

    Args:
        mode (str): world, named, origin, 3point, entity or view.
        name (Optional[str]): the saved UCS for mode='named'.
        origin (Optional[list[float]]): new origin, for 'origin' and '3point'.
        rotation (float): degrees about Z, for mode='origin'.
        point_on_x / point_on_y (Optional[list[float]]): for mode='3point'.
        handle (Optional[str]): the object, for mode='entity'.
        save_as (Optional[str]): keep this UCS under a name.

    Returns:
        str: JSON: {"set": str, "saved_as": str | null, "ucs": {...as autocad_get_ucs...}}

    Examples:
        - Use when: "put the origin on grid A1 and turn it to the wall" —
          mode='3point' with three picked points.
        - Use when: a drawing arrives with a rotated UCS and you want world
          coordinates back: mode='world'.
        - Don't use when: you only need to convert a few points
          (autocad_convert_points leaves the drawing alone).

    Error Handling:
        - mode='named' with a name the drawing does not have lists what it has.
        - mode='3point' with three points in a line is refused: they define no plane.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        target: Ucs | None = None
        existing: Any = None

        if mode == "named":
            if not name:
                raise AutocadError("mode='named' needs the name of a saved UCS.")
            saved = _named_ucs(doc)
            match = next((v for k, v in saved.items() if k.lower() == name.strip().lower()), None)
            if match is None:
                have = ", ".join(sorted(saved)) or "none"
                raise AutocadError(f"This drawing has no UCS named '{name}'. Saved: {have}.")
            existing = match
        elif mode == "origin":
            try:
                target = Ucs.from_rotation(as_vec3(origin or (0.0, 0.0, 0.0)), rotation)
            except ValueError as exc:
                raise AutocadError(str(exc)) from exc
        elif mode == "3point":
            if not origin or not point_on_x or not point_on_y:
                raise AutocadError(
                    "mode='3point' needs origin, point_on_x and point_on_y, each as [x, y] or [x, y, z]."
                )
            try:
                target = Ucs.from_three_points(origin, point_on_x, point_on_y)
            except ValueError as exc:
                raise AutocadError(
                    f"Those three points do not define a plane ({exc}). Pick an origin, "
                    "a point along the new X axis, and a point off that line for Y."
                ) from exc
        elif mode == "entity":
            if not handle:
                raise AutocadError("mode='entity' needs the handle of the object to line up with.")
            target = _ucs_from_entity(doc, handle)

        with undo_mark(doc):
            if mode in ("world", "view"):
                # _.UCS _World / _.UCS _View: the two the API cannot set directly.
                _send(doc, [f"_.UCS _{mode.title()}"])
            elif existing is not None:
                doc.ActiveUCS = existing
            elif target is not None:
                existing = _store(doc, target, save_as or WORKING_UCS)
                doc.ActiveUCS = existing
            if save_as and mode in ("world", "view", "named"):
                existing = _store(doc, current_ucs(doc), save_as)

        now = current_ucs(doc)
        return {
            "set": mode,
            "saved_as": save_as or (WORKING_UCS if target is not None else None),
            "ucs": now.describe(_ucs_name(doc) or None),
            "advice": advice(now),
        }

    return dumps(await run(work))


def _store(doc: Any, ucs: Ucs, name: str) -> Any:
    """Put a UCS in the drawing's table under a name, replacing one already there.

    Replaced rather than edited: AcadUCS exposes its vectors, but deleting and
    adding is the one path that behaves the same on every version checked.
    """
    clean = str(name).strip()
    if not clean:
        raise AutocadError("A UCS name cannot be empty.")
    for existing_name, item in _named_ucs(doc).items():
        if existing_name.lower() == clean.lower():
            try:
                item.Delete()
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AutocadError(
                    f"'{existing_name}' is already in this drawing and could not be "
                    f"replaced ({com_message(exc)}). Save under another name."
                ) from exc
            break
    on_x = ucs.to_world((1.0, 0.0, 0.0))
    on_y = ucs.to_world((0.0, 1.0, 0.0))
    try:
        return doc.UserCoordinateSystems.Add(
            apoint(*ucs.origin), apoint(*on_x), apoint(*on_y), clean
        )
    except BaseException as exc:  # noqa: BLE001
        raise_if_busy(exc)
        raise AutocadError(f"AutoCAD would not store the UCS '{clean}': {com_message(exc)}") from exc


def _ucs_from_entity(doc: Any, handle: str) -> Ucs:
    """A UCS lined up with one object: its own plane, turned to its own direction."""
    from ..acad.entities import resolve_handle

    entity = resolve_handle(doc, handle)

    def _read(getter, default=None):
        try:
            return getter()
        except BaseException as exc:  # noqa: BLE001 - not every type carries these
            raise_if_busy(exc)
            return default

    normal = as_vec3(_read(lambda: entity.Normal), (0.0, 0.0, 1.0))
    rotation = _read(lambda: deg(entity.Rotation))
    if rotation is None:
        rotation = _read(lambda: deg(entity.Angle), 0.0) or 0.0
    origin = as_vec3(
        _read(lambda: entity.InsertionPoint)
        or _read(lambda: entity.Center)
        or _read(lambda: entity.StartPoint)
        or (0.0, 0.0, 0.0)
    )
    if abs(abs(normal[2]) - 1.0) > 1e-9:
        raise AutocadError(
            f"Object {handle} sits on a plane tilted out of the world XY plane "
            f"(its normal is {[round(v, 4) for v in normal]}). Line the UCS up by hand "
            "with mode='3point', using three points on that object."
        )
    # A flipped normal means the object's own X runs the other way round.
    return Ucs.from_rotation(origin, rotation if normal[2] > 0 else -rotation)


@mcp.tool(
    name="autocad_convert_points",
    **tool_meta("Convert Coordinates", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_convert_points(
    points: Annotated[
        list[list[float]],
        Field(description="The points to convert, each [x, y] or [x, y, z].", min_length=1),
    ],
    into: Annotated[
        Literal["world", "ucs"],
        Field(
            default="world",
            description=(
                "'world' reads the points as UCS coordinates and gives world ones "
                "(what every drawing tool here needs). 'ucs' does the opposite: "
                "world in, the modeller's own numbers out."
            ),
        ),
    ] = "world",
    ucs_name: Annotated[
        str | None,
        Field(
            default=None,
            description="Convert through a saved UCS instead of the current one.",
        ),
    ] = None,
    angles: Annotated[
        list[float] | None,
        Field(default=None, description="Angles in degrees to convert alongside the points."),
    ] = None,
) -> str:
    """Move points between the modeller's UCS and the world coordinates every tool takes.

    This is AutoLISP's ``trans``. Use it whenever the modeller gives you
    coordinates off a drawing with a UCS set: convert first, then draw with the
    world numbers. Nothing in the drawing changes.

    Args:
        points (list[list[float]]): the points to convert.
        into (str): 'world' (UCS in, world out) or 'ucs' (the other way).
        ucs_name (Optional[str]): a saved UCS to use instead of the current one.
        angles (Optional[list[float]]): degrees to turn along with the points.

    Returns:
        str: JSON: {
          "into": str,
          "points": [[x, y, z]],
          "angles": [float] | null,
          "ucs": {...},
          "unchanged": bool    # true when the UCS is the world one
        }

    Examples:
        - Use when: "the pump is at 2400,1800 on my rotated plan" — convert,
          then insert the block at the world point that comes back.
        - Use when: reporting a picked world point back in the modeller's own numbers.
        - Don't use when: the UCS is the world one; "unchanged" tells you it was.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        if ucs_name:
            saved = _named_ucs(doc)
            match = next((v for k, v in saved.items() if k.lower() == ucs_name.strip().lower()), None)
            if match is None:
                have = ", ".join(sorted(saved)) or "none"
                raise AutocadError(f"This drawing has no UCS named '{ucs_name}'. Saved: {have}.")
            try:
                ucs = Ucs.build(as_vec3(match.Origin), as_vec3(match.XVector), as_vec3(match.YVector))
            except Exception as exc:  # noqa: BLE001 - a corrupt table entry, reported as such
                raise_if_busy(exc)
                raise AutocadError(f"The saved UCS '{ucs_name}' could not be read: {exc}") from exc
            label = str(match.Name)
        else:
            ucs = current_ucs(doc)
            label = _ucs_name(doc) or None

        move = ucs.to_world if into == "world" else ucs.to_ucs
        result: dict[str, Any] = {
            "into": into,
            "points": [[round(v, 9) for v in move(p)] for p in points],
            "ucs": ucs.describe(label),
            "unchanged": ucs.is_world,
        }
        if angles is not None:
            if ucs.tilted:
                raise AutocadError(
                    "That UCS is tilted out of the world XY plane, so a flat angle has no "
                    "single world answer. Convert the points instead and measure from those."
                )
            # The same direction, measured the other way: on a flipped UCS the
            # angle also runs the other way round (D-96).
            convert = ucs.angle_to_world if into == "world" else ucs.angle_from_world
            result["angles"] = [round(convert(a), 9) for a in angles]
        else:
            result["angles"] = None
        return result

    return dumps(await run(work))
