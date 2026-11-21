"""Photometric lights: point, spot, web (IES) and distant (D-42).

AutoCAD's COM interface has no light object, and typing the LIGHT commands
means answering prompts that change between releases, so the Heron plug-in
makes the light through AutoCAD's .NET API: one Light object, every setting
written in one transaction.

A light drawn here can be turned into a block with autocad_make_block with the
rest of a fitting (a downlight's can and its light together): that tool copies
whatever objects it is given, lights included, and a light inside a block
still shines when the block is inserted.
"""

from __future__ import annotations

import math
import os
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.render import (
    CONE_MAX_DEGREES,
    EXPOSURE_MAX,
    EXPOSURE_MIN,
    KELVIN_MAX,
    KELVIN_MIN,
    SUN_YEAR_MAX,
    SUN_YEAR_MIN,
    WHITE_BALANCE_MAX,
    WHITE_BALANCE_MIN,
    check_rgb,
    julian_day,
    ms_after_midnight,
    parse_date,
    parse_time,
    timezone_code,
    timezone_offset,
    unit_vector,
)
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import (
    COORDS_OPT,
    LAYER_OPT,
    in_plugin,
    plugin_created,
    plugin_read,
    ucs_for,
    world_coords,
    world_direction,
)

# What each intensity unit is, as the plug-in names AutoCAD's methods.
INTENSITY_METHOD = {"cd": "peak_intensity", "lm": "flux", "lux": "illuminance"}

LIGHTING_UNITS_WORDS = {
    0: "0 (generic lighting: the cd, lm and Kelvin values are ignored)",
    1: "1 (American photometric units, foot-candles)",
    2: "2 (international photometric units, lux)",
}


def lighting_units_warning(value: Any) -> str | None:
    """What to tell the modeller when LIGHTINGUNITS is not 2; None when it is."""
    try:
        units = int(value)
    except (TypeError, ValueError):
        return (
            "LIGHTINGUNITS could not be read, so it is not known whether these photometric "
            "values (cd, lm, Kelvin) will be used. Check it in AutoCAD; 2 is wanted."
        )
    if units == 2:
        return None
    said = LIGHTING_UNITS_WORDS.get(units, str(units))
    return (
        f"LIGHTINGUNITS is {said}. Lights here are set in international photometric units, so set "
        "LIGHTINGUNITS to 2 (type LIGHTINGUNITS in AutoCAD, or autocad_set_variable with the Admin "
        "padlock); until then the render will not light as asked."
    )


@mcp.tool(name="autocad_add_light", **tool_meta("Add A Light"))
@tool_errors
async def autocad_add_light(
    position: Annotated[
        list[float],
        Field(description="Where the lamp is, [x, y, z]. Give z: a downlight sits at ceiling height, e.g. [2400, 1800, 2950]."),
    ],
    intensity: Annotated[
        float,
        Field(gt=0, description="How bright: a number in intensity_unit. A 10 W LED downlight is about 800 lm; a 1 m cove strip about 400 lm."),
    ],
    kind: Annotated[
        Literal["point", "spot", "web", "distant"],
        Field(
            default="point",
            description=(
                "'point' shines all round (a bulb, a pendant), 'spot' a cone (a downlight, an "
                "up or down wall light), 'web' follows a maker's IES file (the most real "
                "downlight), 'distant' parallel rays from far off (sun, moonlight)."
            ),
        ),
    ] = "point",
    intensity_unit: Annotated[
        Literal["cd", "lm", "lux"] | None,
        Field(
            default=None,
            description="'lm' (lumens, as on the lamp box) or 'cd' (candela) for point, spot and web; 'lux' for distant. Omit: cd, or lux for distant.",
        ),
    ] = None,
    target: Annotated[
        list[float] | None,
        Field(default=None, description="The point a spot, web or distant light aims at, [x, y, z]. Give this or direction; omit both to aim straight down."),
    ] = None,
    direction: Annotated[
        list[float] | None,
        Field(default=None, description="Instead of target: the way it shines, e.g. [0, 0, 1] for an up-light, [0, 0, -1] down."),
    ] = None,
    kelvin: Annotated[
        float | None,
        Field(default=None, ge=KELVIN_MIN, le=KELVIN_MAX, description="Lamp colour temperature: 2700-3000 warm white, 4000 neutral, 6500 daylight. Omit for 3000 K unless rgb is given."),
    ] = None,
    rgb: Annotated[
        list[int] | None,
        Field(default=None, description="Instead of kelvin: a coloured light, [red, green, blue] 0-255, laid as a filter over a 6500 K daylight lamp."),
    ] = None,
    hotspot: Annotated[
        float,
        Field(default=44.0, gt=0, le=CONE_MAX_DEGREES, description="Spot only: the bright inner cone, in DEGREES across."),
    ] = 44.0,
    falloff: Annotated[
        float,
        Field(default=50.0, gt=0, le=CONE_MAX_DEGREES, description="Spot only: the outer cone where the light fades to nothing, in DEGREES across. At least the hotspot."),
    ] = 50.0,
    web_file: Annotated[
        str | None,
        Field(default=None, description="Web only: the maker's .ies photometric file, a full path on this PC."),
    ] = None,
    on: Annotated[bool, Field(default=True, description="Switched on. False keeps the light but dark.")] = True,
    shadows: Annotated[bool, Field(default=True, description="Casts shadows in a render.")] = True,
    name: Annotated[
        str | None,
        Field(default=None, description="The light's name as AutoCAD's light list shows it, e.g. 'LIVING-DL-01'. Omit for Pointlight1, Spotlight2..."),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Add a real photometric light (point, spot, web or distant) for a render.

    The lamp is set as a lighting designer would: brightness in lumens or
    candela, colour in Kelvin, the cone of a spot in degrees, or a maker's IES
    file. Put it inside a block with the fitting's geometry
    (autocad_make_block) and every insert of the fitting lights up.

    Lights only show in a render or a realistic visual style with default
    lighting off, and only as asked when LIGHTINGUNITS is 2: the tool reads
    LIGHTINGUNITS and warns when it is not.

    One undo step. Done by Heron's plug-in in AutoCAD (COM has no light).

    Args:
        position (list[float]): the lamp, [x, y, z].
        intensity (float): brightness in intensity_unit.
        kind (str): point, spot, web or distant.
        intensity_unit (Optional[str]): cd, lm or lux.
        target / direction (Optional[list[float]]): where it aims.
        kelvin / rgb: the light's colour.
        hotspot / falloff (float): a spot's cones, in degrees.
        web_file (Optional[str]): the .ies file for a web light.
        on (bool): switched on.
        shadows (bool): casts shadows.
        name (Optional[str]): the light's name.
        layer (Optional[str]): layer for the light, created if missing.
        coords (str): 'world' or 'ucs' for position, target and direction.

    Returns:
        str: JSON: {"created": true, "handle": str, "name": str, "kind": str,
             "intensity": float, "intensity_unit": str, "lighting_units": int,
             "verified": bool, "warning"?: str}

    Examples:
        - Use when: "put a 10 W warm white LED downlight over the dining
          table" — kind='spot', intensity=800, intensity_unit='lm',
          kelvin=3000, aimed straight down.
        - Use when: "add the up and down wall light on the gate pillar" — two
          spots, direction [0, 0, 1] and [0, 0, -1].
        - Use when: "use the Philips IES file for the bedroom downlights" —
          kind='web', web_file='C:/IES/philips-dl.ies'.
        - Use when: "add a light in the cove for a night render" — a point
          light every metre or so, or a glowing strip material
          (autocad_create_material with luminance).
        - Don't use when: the strip itself must glow in the picture — make a
          self-illuminated material with autocad_create_material and apply it.
        - Don't use when: the light is already drawn and only needs copying —
          autocad_copy_entities, or make the fitting a block and
          autocad_insert_block.

    Error Handling:
        - A web light without a .ies file that exists is refused.
        - A falloff smaller than the hotspot is refused.
        - lux for a point, spot or web light, or cd / lm for a distant one, is
          refused: say which unit the number is in.
        - Needs the Heron plug-in 1.4.0 or newer in AutoCAD.
    """
    if len(position) != 3:
        raise AutocadError("position must be [x, y, z]: a light needs its height.")
    if target is not None and direction is not None:
        raise AutocadError("Give target or direction, not both.")
    for label, value in (("target", target), ("direction", direction)):
        if value is not None and len(value) != 3:
            raise AutocadError(f"{label} must be [x, y, z].")
    if kind == "point" and (target is not None or direction is not None):
        raise AutocadError("A point light shines all round and has no aim. Leave out target and direction, or use kind='spot'.")
    if kelvin is not None and rgb is not None:
        raise AutocadError("Give kelvin or rgb, not both.")
    colour = check_rgb(rgb, "rgb")

    unit = intensity_unit or ("lux" if kind == "distant" else "cd")
    if kind == "distant" and unit != "lux":
        raise AutocadError("A distant light is set in lux. Give intensity_unit='lux'.")
    if kind != "distant" and unit == "lux":
        raise AutocadError("A point, spot or web light is set in lm (lumens) or cd (candela), not lux.")

    if kind == "spot" and falloff < hotspot:
        raise AutocadError(
            f"The falloff ({falloff:g} degrees) must be at least the hotspot ({hotspot:g} degrees): "
            "the light fades out beyond the bright cone, not inside it."
        )

    web = None
    if kind == "web":
        if not web_file:
            raise AutocadError("A web light needs the maker's .ies file: give web_file.")
        web = os.path.normpath(os.path.abspath(os.path.expanduser(web_file.strip())))
        if not web.lower().endswith(".ies"):
            raise AutocadError(f"'{web}' is not an .ies file.")
        if not os.path.isfile(web):
            raise AutocadError(f"There is no file at '{web}'.")
    elif web_file:
        raise AutocadError("web_file is for kind='web' only.")

    label = name.strip() if name and name.strip() else None

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        at = world_coords(position, ucs)
        args: dict[str, Any] = {
            "kind": kind,
            "position": at,
            "intensity": float(intensity),
            "intensity_method": INTENSITY_METHOD[unit],
            "on": bool(on),
            "shadows": bool(shadows),
            "name": label,
            "layer": layer,
        }
        if colour is not None:
            args["rgb"] = colour
        else:
            args["kelvin"] = float(kelvin if kelvin is not None else 3000.0)
        if kind != "point":
            if target is not None:
                aim = world_coords(target, ucs)
                unit_vector([a - b for a, b in zip(aim, at, strict=True)], "target - position")
            else:
                way = unit_vector(world_direction(direction or [0.0, 0.0, -1.0], ucs), "direction")
                aim = [a + b for a, b in zip(at, way, strict=True)]
            args["target"] = aim
        if kind == "spot":
            args["hotspot"] = math.radians(hotspot)
            args["falloff"] = math.radians(falloff)
        if web:
            args["web_file"] = web

        try:
            units = doc.GetVariable("LIGHTINGUNITS")
        except BaseException:  # noqa: BLE001 - reported as unknown below
            units = None
        payload = plugin_created(doc, in_plugin("add_light", args, "A light"))
        payload["intensity_unit"] = unit
        try:
            payload["lighting_units"] = int(units)
        except (TypeError, ValueError):
            payload["lighting_units"] = None
        warning = lighting_units_warning(units)
        if warning:
            payload["warning"] = (payload["warning"] + " " + warning) if payload.get("warning") else warning
        payload["note"] = (
            "Lights show in a render, or in the realistic visual style with default lighting "
            "off (DEFAULTLIGHTING 0). To light every fitting, make the light and the fitting "
            "one block with autocad_make_block."
        )
        return payload

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# The lights in the drawing, the sun and the exposure (D-86, D-87)
#
# These tools set a render up; none of them renders. The modeller presses Render
# (Ajmal's rule; autocad_render, Admin, is the one exception: issue #158).
# ---------------------------------------------------------------------------

# Read with the lights, so one answer says why a render is dark.
LIGHTING_VARIABLES = (
    "DEFAULTLIGHTING",
    "LIGHTINGUNITS",
    "SUNSTATUS",
    "LATITUDE",
    "LONGITUDE",
    "TIMEZONE",
    "EXPVALUE",
    "EXPWHITEBALANCE",
)

DEFAULT_LIGHTING_ON = (
    "Default lighting is on (DEFAULTLIGHTING 1), so the viewport shows AutoCAD's own two lights, "
    "not these lights or the sun. Turn it off with autocad_switch_lights(default_lighting=false)."
)

NO_EXPOSURE_VARIABLE = (
    "This AutoCAD did not answer for {name}, so the exposure cannot be set from the chat here. "
    "Set it in the Render Environment & Exposure palette (type RENDEREXPOSURE). Nothing was changed."
)

PRESS_RENDER = "This does not render: press Render in AutoCAD (Visualize tab) when the view looks right."


def _read_var(doc: Any, name: str) -> Any:
    try:
        return doc.GetVariable(name)
    except BaseException:  # noqa: BLE001 - a variable this AutoCAD lacks reads as None
        return None


def _number(value: Any) -> float | None:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _whole(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _flag(value: Any) -> bool | None:
    whole = _whole(value)
    return None if whole is None else bool(whole)


def _clock(text: Any) -> tuple[int, int, int] | None:
    """'10:30:00' as (hour, minute, second), or None."""
    try:
        parts = [int(p) for p in str(text).split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        parts.append(0)
    return (parts[0], parts[1], parts[2]) if len(parts) == 3 else None


def sun_summary(sun: dict[str, Any] | None, variables: dict[str, Any]) -> dict[str, Any]:
    """The sun as one answer: on or off and the place from the variables, the date and time from its object.

    ``dxf`` is what the SUN object's groups 91 (Julian day) and 92 (ms after
    midnight) should hold for that date and time, so a live check can compare.
    """
    out: dict[str, Any] = {
        "on": _flag(variables.get("SUNSTATUS")),
        "latitude": _number(variables.get("LATITUDE")),
        "longitude": _number(variables.get("LONGITUDE")),
        "timezone": _whole(variables.get("TIMEZONE")),
        "utc_offset": timezone_offset(variables.get("TIMEZONE")),
    }
    if not sun:
        return out
    if out["on"] is None:
        out["on"] = sun.get("on")
    elif sun.get("on") is not None and bool(sun["on"]) != out["on"]:
        out["sun_object_on"] = bool(sun["on"])
    for key in ("date", "time", "daylight_saving", "azimuth", "altitude"):
        if key in sun:
            out[key] = sun[key]
    clock = _clock(sun.get("time"))
    try:
        year, month, day = parse_date(str(sun.get("date")))
        if clock is not None:
            out["dxf"] = {
                "91_julian_day": julian_day(year, month, day),
                "92_ms_after_midnight": ms_after_midnight(*clock),
            }
    except AutocadError:
        pass
    return out


def light_summary(report: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """What autocad_list_lights answers: the lights, the sun, default lighting and the exposure."""
    lights = [dict(row) for row in (report.get("lights") or [])]
    lit = sum(1 for row in lights if row.get("on"))
    in_blocks = sum(1 for row in lights if row.get("block"))
    payload: dict[str, Any] = {
        "count": len(lights),
        "on": lit,
        "off": len(lights) - lit,
        "in_model_space": len(lights) - in_blocks,
        "in_blocks": in_blocks,
        "lights": lights,
        "default_lighting": _flag(variables.get("DEFAULTLIGHTING")),
        "lighting_units": _whole(variables.get("LIGHTINGUNITS")),
        "sun": sun_summary(report.get("sun"), variables),
        "exposure": {
            "exposure": _number(variables.get("EXPVALUE")),
            "white_balance": _number(variables.get("EXPWHITEBALANCE")),
        },
    }
    if not report.get("sun") and report.get("sun_note"):
        payload["sun"]["note"] = report["sun_note"]
    if payload["exposure"]["exposure"] is None:
        payload["exposure"]["note"] = (
            "EXPVALUE did not answer: this AutoCAD may keep the exposure only in the Render "
            "Environment & Exposure palette (RENDEREXPOSURE)."
        )
    warnings: list[str] = []
    if payload["default_lighting"]:
        warnings.append(DEFAULT_LIGHTING_ON)
    if lights:
        units = lighting_units_warning(variables.get("LIGHTINGUNITS"))
        if units:
            warnings.append(units)
        if lit == 0 and not payload["sun"].get("on"):
            warnings.append("Every light is off and so is the sun: a render will be dark.")
    if warnings:
        payload["warning"] = " ".join(warnings)
    return payload


def _set_var(doc: Any, name: str, value: Any, done: list[str], not_set: list[str]) -> None:
    try:
        doc.SetVariable(name, value)
    except BaseException as exc:  # noqa: BLE001 - one refusal is said, the rest still go
        not_set.append(f"{name} ({com_message(exc)})")
    else:
        done.append(name)


def _like(before: Any, value: float) -> Any:
    """A number in the type the variable already holds: AutoCAD keeps some as whole numbers."""
    if isinstance(before, int) and not isinstance(before, bool):
        return int(round(value))
    return float(value)


@mcp.tool(name="autocad_list_lights", **tool_meta("List The Lights", read_only=True, idempotent=True))
@tool_errors
async def autocad_list_lights() -> str:
    """Every light in the drawing with on / off and brightness, plus the sun, default lighting and exposure.

    Like AutoCAD's Lights in Model palette, from the chat: each light's
    handle, name, kind (point, spot, web, distant), on or off, intensity and
    its unit (cd, lm, lux), colour in Kelvin, layer and position. Lights
    inside a block definition are listed too, with the block's name and how
    many inserts it has: switching one switches it in every insert.

    It also says why a render may be dark: default lighting on, every light
    off, LIGHTINGUNITS not 2, and the sun's on / off, date, time and place.

    Changes nothing. Done by Heron's plug-in (COM has no light object).

    Returns:
        str: JSON: {"count", "on", "off", "in_model_space", "in_blocks",
             "lights": [{"handle", "name", "kind", "on", "intensity",
             "intensity_unit", "kelvin"?, "layer", "position"?, "block"?,
             "inserts"?}], "default_lighting": bool, "lighting_units": int,
             "sun": {"on", "date", "time", "daylight_saving", "latitude",
             "longitude", "timezone", "utc_offset", "azimuth", "altitude",
             "dxf"}, "exposure": {"exposure", "white_balance"},
             "warning"?: str}

    Examples:
        - Use when: "which lights are on in the villa?" — before a night render.
        - Use when: "why is my render black?" — it names default lighting,
          lights off or the sun.
        - Use when: "what is the sun set to?" — date, time and place.
        - Don't use when: you want to switch them — autocad_switch_lights.
        - Don't use when: you want a new light — autocad_add_light.

    Error Handling:
        - Needs the Heron plug-in with the list_lights operation; an older one
          says it does not have it.
        - A variable this AutoCAD does not have reads as null.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        report = in_plugin("list_lights", {}, "Listing the lights", changes=False)
        variables = {name: _read_var(doc, name) for name in LIGHTING_VARIABLES}
        return light_summary(report, variables)

    return dumps(await run(work))


@mcp.tool(name="autocad_switch_lights", **tool_meta("Switch Lights, Sun And Default Lighting", idempotent=True))
@tool_errors
async def autocad_switch_lights(
    turn_on: Annotated[
        list[str] | None,
        Field(default=None, description="Lights to switch on, by name or handle from autocad_list_lights. A name that is in several blocks switches all of them."),
    ] = None,
    turn_off: Annotated[
        list[str] | None,
        Field(default=None, description="Lights to switch off, by name or handle."),
    ] = None,
    all_lights: Annotated[
        Literal["on", "off"] | None,
        Field(default=None, description="Every light in the drawing on, or every one off. Instead of turn_on / turn_off."),
    ] = None,
    sun: Annotated[
        bool | None,
        Field(default=None, description="The sun on (true) or off (false), as SUNSTATUS. Off for a night render."),
    ] = None,
    default_lighting: Annotated[
        bool | None,
        Field(default=None, description="AutoCAD's default lighting on or off (DEFAULTLIGHTING). Off, so the viewport shows your lights and the sun."),
    ] = None,
) -> str:
    """Switch lights on or off, and the sun and AutoCAD's default lighting, like the Lights in Model palette.

    Name the lights or give their handles (autocad_list_lights lists them), or
    switch all of them at once. A light inside a block definition switches in
    every insert of that block. If one name is not found nothing is switched,
    and the answer lists the lights there are.

    The sun (SUNSTATUS) and default lighting (DEFAULTLIGHTING) are plain
    variables of the current viewport; default lighting is switched first, so
    turning the sun on with default lighting off asks AutoCAD nothing.

    One undo step. It does not render: press Render in AutoCAD.

    Args:
        turn_on / turn_off (Optional[list[str]]): lights by name or handle.
        all_lights (Optional[str]): 'on' or 'off' for every light.
        sun (Optional[bool]): the sun on or off.
        default_lighting (Optional[bool]): default lighting on or off.

    Returns:
        str: JSON: {"changed": int, "lights": [{"handle", "name", "on", ...}],
             "set": [str], "sun": bool, "default_lighting": bool,
             "not_set"?: [str], "warning"?: str}

    Examples:
        - Use when: "night render: sun off, default lighting off, all the
          downlights on" — sun=false, default_lighting=false, all_lights='on'.
        - Use when: "turn off the pendant over the dining table" —
          turn_off=['DINING-PENDANT'].
        - Use when: "daylight render only" — all_lights='off', sun=true,
          default_lighting=false.
        - Don't use when: the light is too bright or the wrong colour — make
          it again with autocad_add_light; this only switches.
        - Don't use when: you want the sun's date and time — autocad_set_sun.

    Error Handling:
        - A light name that is not in the drawing refuses the whole switch and
          lists the names there are; nothing is changed.
        - A light on a locked layer refuses the switch: unlock the layer.
        - A variable AutoCAD refuses is in "not_set"; the rest are set.
    """
    lights_asked = bool(turn_on or turn_off or all_lights)
    if not lights_asked and sun is None and default_lighting is None:
        raise AutocadError("Nothing to switch. Give turn_on, turn_off, all_lights, sun or default_lighting.")
    if all_lights and (turn_on or turn_off):
        raise AutocadError("Give all_lights or the lights by name, not both.")
    both = sorted({w.strip().lower() for w in turn_on or []} & {w.strip().lower() for w in turn_off or []} - {""})
    if both:
        raise AutocadError(f"{', '.join(both)} cannot be switched both on and off. Say which.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        done: list[str] = []
        not_set: list[str] = []
        report: dict[str, Any] = {}
        with undo_mark(doc):
            if lights_asked:
                args: dict[str, Any] = {"all": all_lights}
                if turn_on:
                    args["on"] = [str(w) for w in turn_on]
                if turn_off:
                    args["off"] = [str(w) for w in turn_off]
                report = in_plugin("switch_lights", args, "Switching lights")
            # Default lighting first: the sun is then switched on in a viewport
            # that already shows user lighting.
            if default_lighting is not None:
                _set_var(doc, "DEFAULTLIGHTING", 1 if default_lighting else 0, done, not_set)
            if sun is not None:
                _set_var(doc, "SUNSTATUS", 1 if sun else 0, done, not_set)
        try:
            doc.Regen(1)  # acAllViewports: a light inside a block shows its new state in every insert
        except BaseException:  # noqa: BLE001 - the switch is done either way
            pass

        payload: dict[str, Any] = {
            "changed": int(report.get("changed", 0)),
            "lights": report.get("lights", []),
            "set": done,
            "sun": _flag(_read_var(doc, "SUNSTATUS")),
            "default_lighting": _flag(_read_var(doc, "DEFAULTLIGHTING")),
        }
        for name, asked, now in (("SUNSTATUS", sun, payload["sun"]), ("DEFAULTLIGHTING", default_lighting, payload["default_lighting"])):
            if asked is not None and name in done and now is not None and now != asked:
                not_set.append(f"{name} (it reads {int(now)} after being set to {int(asked)})")
        if not_set:
            payload["not_set"] = not_set
        if payload["default_lighting"]:
            payload["warning"] = DEFAULT_LIGHTING_ON
        payload["note"] = PRESS_RENDER
        return payload

    return dumps(await run(work))


@mcp.tool(name="autocad_set_sun", **tool_meta("Set The Sun's Date, Time And Place"))
@tool_errors
async def autocad_set_sun(
    date: Annotated[
        str | None,
        Field(default=None, description="The day, as year-month-day, e.g. '2026-06-21' (midsummer) or '2026-12-21'."),
    ] = None,
    time: Annotated[
        str | None,
        Field(default=None, description="The clock time at the site, 24-hour, e.g. '10:30' or '16:45'."),
    ] = None,
    latitude: Annotated[
        float | None,
        Field(default=None, ge=-90, le=90, description="Degrees, north positive: Doha 25.29, Dubai 25.20, Kochi 9.93."),
    ] = None,
    longitude: Annotated[
        float | None,
        Field(default=None, ge=-180, le=180, description="Degrees, east of Greenwich positive: Doha 51.53, Dubai 55.27, Kochi 76.27."),
    ] = None,
    utc_offset: Annotated[
        float | None,
        Field(default=None, description="The site's time zone in hours from UTC: Qatar 3, UAE 4, India 5.5. Sets TIMEZONE."),
    ] = None,
    daylight_saving: Annotated[
        bool | None,
        Field(default=None, description="Whether the clock time is summer time. The Gulf and India have none: false."),
    ] = None,
    on: Annotated[
        bool | None,
        Field(default=None, description="Switch the sun on (true) or off (false) too, as SUNSTATUS."),
    ] = None,
) -> str:
    """Set the sun for a daylight render: the date, the clock time and the place, then read them back.

    The place is the drawing's LATITUDE, LONGITUDE and TIMEZONE; the date and
    time live on the current model viewport's sun, which Heron's plug-in sets
    (AutoCAD has no variable for them). Only what is given changes: a time on
    its own keeps the sun's date. The answer reads everything back from
    AutoCAD, with the sun's azimuth and altitude as AutoCAD works them out.

    One undo step. It does not render: press Render in AutoCAD.

    Args:
        date (Optional[str]): 'YYYY-MM-DD'.
        time (Optional[str]): 'HH:MM', 24-hour, at the site.
        latitude / longitude (Optional[float]): the site, in degrees.
        utc_offset (Optional[float]): the time zone, hours from UTC.
        daylight_saving (Optional[bool]): summer time.
        on (Optional[bool]): the sun on or off.

    Returns:
        str: JSON: {"set": [str], "sun_made": bool, "sun": {"on", "date",
             "time", "daylight_saving", "latitude", "longitude", "timezone",
             "utc_offset", "azimuth", "altitude", "dxf"}, "not_set"?: [str],
             "warning"?: str}

    Examples:
        - Use when: "set the sun for Doha, 21 June at 10 in the morning" —
          date='2026-06-21', time='10:00', latitude=25.29, longitude=51.53,
          utc_offset=3.
        - Use when: "make it late afternoon" — time='16:30' only; the date
          and place stay.
        - Use when: "turn the sun on for the daylight render" — on=true (and
          autocad_switch_lights(default_lighting=false)).
        - Don't use when: you only want to know what it is set to —
          autocad_list_lights reads the sun too.
        - Don't use when: it is a night render — autocad_switch_lights(sun=false).

    Error Handling:
        - A date or time that does not exist, or a UTC offset that is not a
          time zone, is refused before anything changes.
        - It works on the Model tab only: a layout is refused.
        - If the sun's date cannot be set after the place was, the error says
          the place was set and Ctrl+Z takes it back.
    """
    if latitude is not None and not -90 <= latitude <= 90:
        raise AutocadError("The latitude must be -90 to 90 degrees, north positive.")
    if longitude is not None and not -180 <= longitude <= 180:
        raise AutocadError("The longitude must be -180 to 180 degrees, east positive.")
    dated = parse_date(date) if date is not None else None
    if dated and not SUN_YEAR_MIN <= dated[0] <= SUN_YEAR_MAX:
        raise AutocadError(f"The sun's year must be {SUN_YEAR_MIN}-{SUN_YEAR_MAX}. Nothing was changed.")
    timed = parse_time(time) if time is not None else None
    zone = timezone_code(float(utc_offset)) if utc_offset is not None else None
    if all(v is None for v in (dated, timed, latitude, longitude, zone, daylight_saving, on)):
        raise AutocadError("Nothing to set. Give a date, time, latitude, longitude, utc_offset, daylight_saving or on.")

    sun_args: dict[str, Any] = {}
    if dated:
        sun_args.update(year=dated[0], month=dated[1], day=dated[2])
    if timed:
        sun_args.update(hour=timed[0], minute=timed[1])
    if daylight_saving is not None:
        sun_args["daylight_saving"] = bool(daylight_saving)
    place: dict[str, Any] = {}
    if latitude is not None:
        place["LATITUDE"] = float(latitude)
    if longitude is not None:
        place["LONGITUDE"] = float(longitude)
    if zone is not None:
        place["TIMEZONE"] = zone

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if _whole(_read_var(doc, "TILEMODE")) == 0:
            raise AutocadError("The sun belongs to the model: switch to the Model tab, then ask again. Nothing was changed.")
        done: list[str] = []
        not_set: list[str] = []
        report: dict[str, Any] = {}
        with undo_mark(doc):
            for name, value in place.items():
                _set_var(doc, name, value, done, not_set)
            if sun_args:
                try:
                    report = in_plugin("set_sun", sun_args, "Setting the sun's date and time")
                except AutocadError as exc:
                    if done:
                        words = str(exc).replace("Nothing was changed.", "").strip()
                        raise AutocadError(
                            f"{words} The sun's date and time were not changed, but the place was "
                            f"already set ({', '.join(done)}); one Ctrl+Z takes it back."
                        ) from exc
                    raise
                done.append("sun date and time" if (dated or timed) else "daylight saving")
            if on is not None:
                _set_var(doc, "SUNSTATUS", 1 if on else 0, done, not_set)

        variables = {name: _read_var(doc, name) for name in LIGHTING_VARIABLES}
        sun_object = report.get("sun")
        if sun_object is None:
            read, _why = plugin_read("list_lights")
            sun_object = (read or {}).get("sun")
        elif "SUNSTATUS" in done:
            # The plug-in read the sun before SUNSTATUS was written: its on / off is old.
            sun_object = {key: value for key, value in sun_object.items() if key != "on"}
        summary = sun_summary(sun_object, variables)
        for name, key in (("LATITUDE", "latitude"), ("LONGITUDE", "longitude")):
            if name in done and summary[key] is not None and abs(summary[key] - place[name]) > 1e-6:
                not_set.append(f"{name} (it reads {summary[key]:g} after being set to {place[name]:g})")
        if "TIMEZONE" in done and summary["timezone"] is not None and summary["timezone"] != zone:
            not_set.append(f"TIMEZONE (it reads {summary['timezone']} after being set to {zone})")
        if on is not None and "SUNSTATUS" in done and summary["on"] is not None and summary["on"] != on:
            not_set.append(f"SUNSTATUS (it reads {int(summary['on'])} after being set to {int(on)})")

        payload: dict[str, Any] = {"set": done, "sun_made": bool(report.get("sun_made", False)), "sun": summary}
        if not_set:
            payload["not_set"] = not_set
        warnings: list[str] = []
        if summary.get("on") and _flag(variables.get("DEFAULTLIGHTING")):
            warnings.append(DEFAULT_LIGHTING_ON)
        if summary.get("on") is False and (dated or timed):
            warnings.append("The sun is off, so the date and time show only once it is on (on=true).")
        if warnings:
            payload["warning"] = " ".join(warnings)
        payload["note"] = PRESS_RENDER
        return payload

    return dumps(await run(work))


@mcp.tool(name="autocad_set_render_exposure", **tool_meta("Set The Render Exposure", idempotent=True))
@tool_errors
async def autocad_set_render_exposure(
    exposure: Annotated[
        float | None,
        Field(
            default=None, ge=EXPOSURE_MIN, le=EXPOSURE_MAX,
            description="Exposure (EV), -6 to 21. LOWER is BRIGHTER: try 7 or 8 for a dark interior, 12 to 14 for a sunny exterior.",
        ),
    ] = None,
    white_balance: Annotated[
        float | None,
        Field(
            default=None, ge=WHITE_BALANCE_MIN, le=WHITE_BALANCE_MAX,
            description="White balance in Kelvin, 1000-20000 (6500 neutral). Lower cools the picture, higher warms it.",
        ),
    ] = None,
) -> str:
    """Set the render's Exposure and White balance, as in the Render Environment & Exposure palette.

    Written to AutoCAD's EXPVALUE and EXPWHITEBALANCE variables, then read
    back. The old LOGEXP... variables are not used: they are gone in 2027. If
    this AutoCAD has no EXPVALUE, nothing changes and the answer says to use
    the palette (RENDEREXPOSURE).

    One undo step. It does not render: press Render in AutoCAD.

    Args:
        exposure (Optional[float]): EV, -6 to 21; lower is brighter.
        white_balance (Optional[float]): Kelvin, 1000-20000.

    Returns:
        str: JSON: {"exposure": {"from", "to"}?, "white_balance": {"from",
             "to"}?, "not_set"?: [str], "note": str}

    Examples:
        - Use when: "the render is too dark" — exposure one or two lower than
          it is (autocad_list_lights shows the current one).
        - Use when: "the night render looks too yellow" — white_balance a
          little lower than the lamps' Kelvin.
        - Don't use when: the lights themselves are wrong — autocad_switch_lights
          or autocad_add_light.

    Error Handling:
        - Values outside the ranges are refused before anything changes.
        - A variable this AutoCAD does not have refuses the call, naming the
          palette instead; nothing is changed.
    """
    wanted = {name: value for name, value in (("EXPVALUE", exposure), ("EXPWHITEBALANCE", white_balance)) if value is not None}
    if not wanted:
        raise AutocadError("Nothing to set. Give exposure, white_balance or both.")
    if exposure is not None and not EXPOSURE_MIN <= exposure <= EXPOSURE_MAX:
        raise AutocadError(f"The exposure must be {EXPOSURE_MIN:g} to {EXPOSURE_MAX:g} (lower is brighter).")
    if white_balance is not None and not WHITE_BALANCE_MIN <= white_balance <= WHITE_BALANCE_MAX:
        raise AutocadError(f"The white balance must be {WHITE_BALANCE_MIN:g}-{WHITE_BALANCE_MAX:g} K (6500 is neutral).")
    keys = {"EXPVALUE": "exposure", "EXPWHITEBALANCE": "white_balance"}

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        before = {name: _read_var(doc, name) for name in wanted}
        for name, value in before.items():
            if value is None:
                raise AutocadError(NO_EXPOSURE_VARIABLE.format(name=name))
        done: list[str] = []
        not_set: list[str] = []
        with undo_mark(doc):
            for name, value in wanted.items():
                _set_var(doc, name, _like(before[name], float(value)), done, not_set)
        payload: dict[str, Any] = {}
        for name in wanted:
            now = _number(_read_var(doc, name))
            payload[keys[name]] = {"from": _number(before[name]), "to": now}
            if name in done and now is not None and abs(now - float(wanted[name])) > 0.5:
                not_set.append(f"{name} (it reads {now:g} after being set to {float(wanted[name]):g})")
        if not_set:
            payload["not_set"] = not_set
        payload["note"] = PRESS_RENDER
        return payload

    return dumps(await run(work))
