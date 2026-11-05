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
    KELVIN_MAX,
    KELVIN_MIN,
    check_rgb,
    unit_vector,
)
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from ._shared import (
    COORDS_OPT,
    LAYER_OPT,
    in_plugin,
    plugin_created,
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
