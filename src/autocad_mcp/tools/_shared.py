"""Option definitions and payload helpers shared across tool modules.

The layer / colour / linetype / space options appear on most creation tools.
Defining them once means the wording an agent reads is identical everywhere,
and a change to the guidance lands in every tool at once.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import Field

from ..acad.coords import Ucs, as_vec3
from ..acad.entities import describe
from ..core.connection import mark_writing
from ..core.errors import AutocadError
from ..core.gate import plugin_runner
from ..core.variants import apoint

LAYER_OPT = Field(
    default=None,
    description=(
        "Layer to draw on. Created automatically if it does not exist. "
        "Omit to use the drawing's current layer."
    ),
)

COLOR_OPT = Field(
    default=None,
    description=(
        "Colour as a name ('red', 'green', 'cyan', 'bylayer') or an AutoCAD "
        "Color Index number 0-256. Omit to inherit from the layer."
    ),
)

LINETYPE_OPT = Field(
    default=None,
    description=(
        "Linetype name such as 'CONTINUOUS', 'HIDDEN', 'CENTER', 'DASHED'. "
        "Loaded from AutoCAD's linetype file automatically if needed."
    ),
)

SPACE_OPT = Field(
    default="model",
    description="'model' for model space, or 'paper' for the current layout.",
    pattern="^(model|paper)$",
)

HANDLES_OPT = Field(
    description=(
        "Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from "
        "autocad_list_entities, autocad_get_selection, or from the tool that "
        "created the entity."
    ),
    min_length=1,
)


COORDS_OPT = Field(
    default="world",
    description=(
        "Which coordinate system the points and angles are given in. 'world' "
        "(the default) is AutoCAD's World Coordinate System, what every tool "
        "here has always used. 'ucs' means the drawing's current UCS — use it "
        "when the modeller has set a UCS (moved or turned onto a wall, a grid "
        "or a wing of the building) and is reading coordinates off that screen. "
        "autocad_status and autocad_get_ucs report whether a UCS is set."
    ),
    pattern="^(world|ucs)$",
)

TILTED_UCS = (
    "The drawing's current UCS is tilted out of the world XY plane, so a flat "
    "[x, y] in it has no single world answer and an angle on that plane is not "
    "an angle in the world. Convert the points yourself with "
    "autocad_convert_points (it gives all three numbers), then call this tool "
    "with coords='world'."
)


def current_ucs(doc: Any) -> Ucs:
    """The drawing's current UCS, read from the system variables that hold it.

    UCSORG, UCSXDIR and UCSYDIR are the origin and the two axes, all in world
    coordinates. A drawing with no UCS set reads back as the world one, so this
    never needs a special case.
    """
    try:
        return Ucs.build(
            as_vec3(doc.GetVariable("UCSORG"), (0.0, 0.0, 0.0)),
            as_vec3(doc.GetVariable("UCSXDIR"), (1.0, 0.0, 0.0)),
            as_vec3(doc.GetVariable("UCSYDIR"), (0.0, 1.0, 0.0)),
        )
    except BaseException:  # noqa: BLE001 - unreadable means assume the world one
        return Ucs()


def ucs_for(doc: Any, coords: str | None) -> Ucs | None:
    """The UCS to convert through for a tool call, or None to leave points alone.

    Returns None for coords='world' so the world path costs nothing, and
    refuses a flat 2D request on a tilted UCS rather than guessing a Z.
    """
    if not coords or str(coords).strip().lower() != "ucs":
        return None
    ucs = current_ucs(doc)
    if ucs.is_world:
        return None
    if ucs.tilted:
        raise AutocadError(TILTED_UCS)
    return ucs


def world_coords(value: Sequence[float], ucs: Ucs | None) -> list[float]:
    """A caller's point as plain world [x, y, z], converted when a UCS applies."""
    if ucs is None:
        return list(as_vec3(value))
    return list(ucs.to_world(value))


def world_direction(value: Sequence[float], ucs: Ucs | None) -> list[float]:
    """A caller's direction (not a position) as a world direction, turned when a UCS applies."""
    if ucs is None:
        return list(as_vec3(value))
    return list(ucs.direction_to_world(value))


def world_angle(degrees: float | None, ucs: Ucs | None) -> float | None:
    """A caller's angle as a world angle.

    On a plan UCS every angle is simply turned by the UCS rotation, which is
    what a drafter means by "horizontal" on a rotated grid.
    """
    if degrees is None or ucs is None:
        return degrees
    return (float(degrees) + ucs.rotation_degrees) % 360.0


def point(value: Sequence[float] | None, name: str, ucs: Ucs | None = None) -> Any:
    """Validate a coordinate list and convert it to AutoCAD's point VARIANT.

    ``ucs`` comes from ``ucs_for``: pass it and the point is read as a UCS
    coordinate and handed to COM as the world one it means.
    """
    if not value or len(value) < 2:
        raise AutocadError(
            f"'{name}' must be a coordinate list of at least [x, y], got {value!r}."
        )
    x, y, z = world_coords(value, ucs)
    return apoint(x, y, z)


def created_payload(
    entity: Any, notes: dict[str, Any], **extra: Any
) -> dict[str, Any]:
    """Uniform success payload for every creation tool.

    Each creation tool returns the new entity's handle in the same field, so
    results chain directly into the modify, query and hatch tools.
    """
    payload: dict[str, Any] = {
        "created": True,
        "handle": str(entity.Handle),
        "type": describe(entity, include_geometry=False)["type"],
        "layer": str(entity.Layer),
    }
    payload.update({k: v for k, v in extra.items() if v is not None})
    payload.update(notes)
    # Read the new object back by its handle: a reply that says "created" is
    # only trusted once the drawing agrees.
    try:
        found = entity.Document.HandleToObject(payload["handle"])
        payload["verified"] = str(found.ObjectName) == str(entity.ObjectName)
    except Exception:  # noqa: BLE001 - any failure to read back is the finding
        payload["verified"] = False
    if not payload["verified"]:
        unread = (
            f"The new object {payload['handle']} could not be read back from the "
            "drawing. Check it with autocad_get_entity before building on it."
        )
        # Beside a warning the tool already gave (one saying it is not annotative), not over it.
        payload["warning"] = f"{payload['warning']} {unread}" if payload.get("warning") else unread
    return payload


PLUGIN_ONLY = (
    "{what} is done by Heron's plug-in inside AutoCAD, because AutoCAD's COM interface has no "
    "call for it, and this server is running with the plug-in switched off (--no-bridge). "
    "Start it with the bridge on and press Heron in AutoCAD."
)


def in_plugin(
    operation: str, args: dict[str, Any], what: str, *, changes: bool = True, timeout: float | None = None
) -> dict[str, Any]:
    """Have the Heron plug-in do one of its own operations (D-40); what it did.

    On the worker thread, inside the tool's job. Options left as None are not
    sent. A change counts as a write before it is asked for, so a busy signal
    after it is never retried into a second run (D-15) and Keep or Discard
    asks about it. ``timeout`` is how long to wait for the answer, when it
    should be shorter than the bridge's usual 300 s (the boundary trace, D-84).
    """
    runner = plugin_runner()
    if runner is None:
        raise AutocadError(PLUGIN_ONLY.format(what=what))
    if changes:
        mark_writing()
    sent = {key: value for key, value in args.items() if value is not None}
    if timeout is None:
        return runner(operation, sent)
    return runner(operation, sent, timeout)


def plugin_read(operation: str, args: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    """A read the plug-in does (D-40), or None and why it could not be had. Never raises.

    For a tool whose own work is done, that only wants to report what it
    found (the visual style after setting it, D-86).
    """
    if plugin_runner() is None:
        return None, "Heron's plug-in is not in this job (the server runs with --no-bridge)."
    try:
        return in_plugin(operation, args or {}, "Reading it", changes=False), None
    except Exception as exc:  # noqa: BLE001 - the read is extra; its failure is said, not raised
        return None, str(exc)


def plugin_created(doc: Any, report: dict[str, Any]) -> dict[str, Any]:
    """The payload for something the plug-in made, read back over COM.

    Once the plug-in has said it made it, nothing here raises: an error would
    send the chat round to make it a second time. A read-back that fails
    (AutoCAD still busy redrawing) is ``verified: false`` with a warning.
    """
    handle = str(report.get("handle", ""))
    if not handle:
        raise AutocadError(
            "Outcome unknown: Heron in AutoCAD did it but gave no handle back. Look at the drawing "
            "before trying again."
        )
    extra = {key: value for key, value in report.items() if key not in ("created", "handle")}
    try:
        return created_payload(doc.HandleToObject(handle), {}, **extra)
    except Exception:  # noqa: BLE001 - made is made; only the read-back failed
        return {
            "created": True,
            "handle": handle,
            **extra,
            "verified": False,
            "warning": (
                f"Heron in AutoCAD made {handle}, but it could not be read back straight away "
                "(AutoCAD may still be busy). Look at the drawing; do not make it again."
            ),
        }


# ---- before / after (D-62) -----------------------------------------------------

MOST_BEFORE_AFTER = 50


def plain_value(value: Any) -> Any:
    """A COM value as the chat reads it: a point as a list, a float without noise."""
    if isinstance(value, tuple):
        return [plain_value(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def same_value(before: Any, after: Any) -> bool:
    """True when writing ``after`` would change nothing: names ignore case, numbers a hair's width."""
    if isinstance(before, bool) or isinstance(after, bool):
        numbers = (bool, int)
        return isinstance(before, numbers) and isinstance(after, numbers) and bool(before) == bool(after)
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return abs(float(before) - float(after)) < 1e-9
    if isinstance(before, str) and isinstance(after, str):
        return before.strip().casefold() == after.strip().casefold()
    return before == after


def before_after(rows: list[dict[str, Any]], most: int = MOST_BEFORE_AFTER) -> dict[str, Any]:
    """Every value a job changed, old -> new, one row each (Heron for Revit's D-156).

    Each row names the object ("handle", or "layer" / "variable" for a table
    entry or a setting), the "property", and "from" and "to". The first
    ``most`` rows are listed; "before_after_more" counts the rest, so a big job
    stays short. An empty list means the job changed nothing.
    """
    shown = [
        {**row, "from": plain_value(row.get("from")), "to": plain_value(row.get("to"))} for row in rows[:most]
    ]
    result: dict[str, Any] = {"before_after": shown}
    if len(rows) > most:
        result["before_after_more"] = len(rows) - most
    return result
