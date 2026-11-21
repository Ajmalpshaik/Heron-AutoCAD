"""The drawing's geographic location (Insert > Location, GEOGRAPHICLOCATION, D-111).

Which drawing point is at which latitude and longitude, and which way north
is: what AutoCAD's map (GEOMAP) and the sun need. COM has no call for it, so
the Heron plug-in writes it with .NET and proves it with AutoCAD's own
transform before it is kept.

The place itself is one place: LATITUDE and LONGITUDE, which autocad_set_sun
already writes for the sun (#61). Without a latitude and longitude this tool
takes that place; with them, it moves the sun's place to the site too, so
the two never disagree. It never sets the sun's date, time or time zone.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from pydantic import Field

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import (
    COORDS_OPT,
    in_plugin,
    plugin_read,
    ucs_for,
    world_angle,
    world_coords,
)
from .lighting import _number, _read_var, _set_var

# AutoCAD's own default place, San Francisco: a drawing nobody has placed yet.
AUTOCAD_DEFAULT_PLACE = (37.795, -122.394)
SAME_PLACE = 1e-6


def is_autocad_default(latitude: float | None, longitude: float | None) -> bool:
    """True when LATITUDE / LONGITUDE still hold AutoCAD's San Francisco default."""
    if latitude is None or longitude is None:
        return False
    return abs(latitude - AUTOCAD_DEFAULT_PLACE[0]) < 1e-3 and abs(longitude - AUTOCAD_DEFAULT_PLACE[1]) < 1e-3


def _sun_place(doc: Any) -> tuple[float | None, float | None]:
    return _number(_read_var(doc, "LATITUDE")), _number(_read_var(doc, "LONGITUDE"))


def _plain(report: dict[str, Any]) -> dict[str, Any]:
    """The plug-in's answer with the north angle in degrees, as the chat reads it."""
    out = dict(report)
    if out.get("north_angle") is not None:
        out["north_angle"] = round(math.degrees(float(out["north_angle"])), 6) % 360.0
    return out


@mcp.tool(name="autocad_geo_location", **tool_meta("Set Or Remove The Geographic Location"))
@tool_errors
async def autocad_geo_location(
    action: Annotated[
        str,
        Field(default="set", description="'set' places the drawing on the Earth; 'remove' takes the location off.", pattern="^(set|remove)$"),
    ] = "set",
    latitude: Annotated[
        float | None,
        Field(default=None, ge=-85, le=85, description="Degrees, north positive: Doha 25.29, Dubai 25.20, Kochi 9.93. Omit to use the place the sun already has (autocad_set_sun)."),
    ] = None,
    longitude: Annotated[
        float | None,
        Field(default=None, ge=-180, le=180, description="Degrees, east of Greenwich positive: Doha 51.53, Dubai 55.27, Kochi 76.27. Omit with latitude."),
    ] = None,
    point: Annotated[
        list[float] | None,
        Field(default=None, description="The drawing point that sits at that latitude and longitude, as [x, y] — a site datum, a gridline crossing. Omit for 0,0."),
    ] = None,
    north_angle: Annotated[
        float,
        Field(default=0.0, ge=-360, le=360, description="Where true north is, in DEGREES clockwise from up the screen (the drawing's +Y), as a compass reads: 0 = north is up, 15 = 15 degrees to the right of up."),
    ] = 0.0,
    elevation: Annotated[
        float,
        Field(default=0.0, description="Height of that point above sea level, in metres."),
    ] = 0.0,
    coordinate_system: Annotated[
        str | None,
        Field(default=None, description="A coordinate system code from AutoCAD's library, e.g. 'UTM84-39N' for Qatar. Omit for WORLD-MERCATOR, which suits the map and the sun anywhere."),
    ] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Place the drawing on the Earth (GEOGRAPHICLOCATION): a drawing point at a latitude and longitude, with north.

    AutoCAD's online map (GEOMAP) then shows under the drawing, and the sun
    follows the site. Before it is kept, the plug-in asks AutoCAD's own
    transform where the drawing point is, and where a point 100 m along the
    north given is; if either reads wrong, nothing is changed.

    The place is the same one the sun uses (LATITUDE, LONGITUDE, set by
    autocad_set_sun): leave latitude and longitude out to use it, or give
    them and the sun's place moves to the site too. The sun's date, time and
    time zone are left alone. The drawing needs its units set (INSUNITS), so
    a metre on the ground is a metre in the drawing.

    One undo step.

    Args:
        action (str): 'set' or 'remove'.
        latitude / longitude (Optional[float]): the site, in degrees.
        point (Optional[list[float]]): the drawing point at the site.
        north_angle (float): degrees clockwise from up to true north.
        elevation (float): metres above sea level.
        coordinate_system (Optional[str]): a coordinate system code.
        coords (str): 'world' or 'ucs' for the point and the north angle.

    Returns:
        str: JSON: {"located": bool, "made": bool, "latitude", "longitude",
             "elevation", "point": [x, y, z], "north_angle": degrees,
             "coordinate_system": str, "units": str, "reference_form": str,
             "sun_place": {"latitude", "longitude", "moved": bool}, "not_set"?: [str]}
             or, for 'remove': {"removed": true, "coordinate_system": str}

    Examples:
        - Use when: "the site is in Doha, grid A/1 is at 0,0, north is 12
          degrees to the right" — latitude=25.29, longitude=51.53,
          north_angle=12.
        - Use when: "geo-locate the drawing where the sun is already set" —
          no latitude or longitude.
        - Use when: "take the geographic location off this drawing" —
          action='remove'.
        - Don't use when: you only want to know where it is —
          autocad_get_geo_location.
        - Don't use when: only the sun's date and time are wanted —
          autocad_set_sun.

    Error Handling:
        - Without a latitude and longitude, and with the sun's place still
          AutoCAD's default (San Francisco), it asks for the place instead of
          locating the drawing in California.
        - A drawing with no units, an unknown coordinate system, or a place
          AutoCAD reads back wrong is refused, and nothing is changed.
    """
    if action == "remove":
        if any(v is not None for v in (latitude, longitude, point, coordinate_system)):
            raise AutocadError("'remove' takes the location off; leave the place, point and coordinate system out.")
    elif (latitude is None) != (longitude is None):
        raise AutocadError("Give both latitude and longitude, or neither to use the sun's place.")
    if point is not None and len(point) < 2:
        raise AutocadError("point must be [x, y].")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if action == "remove":
            with undo_mark(doc):
                return in_plugin("set_geo_location", {"action": "remove"}, "Removing the geographic location")

        sun_lat, sun_lon = _sun_place(doc)
        lat, lon = latitude, longitude
        if lat is None:
            if sun_lat is None or sun_lon is None:
                raise AutocadError("AutoCAD did not give the sun's place (LATITUDE, LONGITUDE). Give latitude and longitude.")
            if is_autocad_default(sun_lat, sun_lon):
                raise AutocadError(
                    "The drawing's place is still AutoCAD's default (San Francisco). Give the site's latitude and "
                    "longitude. Nothing was changed."
                )
            lat, lon = sun_lat, sun_lon
        ucs = ucs_for(doc, coords)
        at = world_coords(point, ucs) if point is not None else [0.0, 0.0, 0.0]
        # North clockwise from +Y in the UCS -> a counter-clockwise world angle -> clockwise from world +Y.
        north_world = (90.0 - float(world_angle(90.0 - float(north_angle), ucs) or 0.0)) % 360.0
        args = {
            "action": "set",
            "latitude": float(lat),
            "longitude": float(lon),
            "elevation": float(elevation),
            "point": at,
            "north_angle": math.radians(north_world),
            "coordinate_system": coordinate_system.strip() if coordinate_system else None,
        }
        not_set: list[str] = []
        moved = False
        with undo_mark(doc):
            report = in_plugin("set_geo_location", args, "Setting the geographic location")
            # One place: the sun follows the site (D-111).
            if sun_lat is None or abs(sun_lat - lat) > SAME_PLACE or sun_lon is None or abs(sun_lon - lon) > SAME_PLACE:
                done: list[str] = []
                _set_var(doc, "LATITUDE", float(lat), done, not_set)
                _set_var(doc, "LONGITUDE", float(lon), done, not_set)
                moved = bool(done)
        now_lat, now_lon = _sun_place(doc)
        payload = _plain(report)
        payload["sun_place"] = {"latitude": now_lat, "longitude": now_lon, "moved": moved}
        if now_lat is not None and now_lon is not None and (abs(now_lat - lat) > SAME_PLACE or abs(now_lon - lon) > SAME_PLACE):
            not_set.append(f"the sun's place (it reads {now_lat:g}, {now_lon:g}; the site is {lat:g}, {lon:g})")
        if not_set:
            payload["not_set"] = not_set
        payload["note"] = "In AutoCAD, GEOMAP AERIAL shows the map under the drawing (it needs an Autodesk sign-in)."
        return payload

    return dumps(await run(work))


@mcp.tool(name="autocad_get_geo_location", **tool_meta("Read The Geographic Location", read_only=True, idempotent=True))
@tool_errors
async def autocad_get_geo_location() -> str:
    """Where the drawing is on the Earth: its geographic location, and the place the sun uses.

    The drawing point that is placed, its latitude, longitude and height, the
    north angle (degrees clockwise from up the screen), the coordinate
    system and units; and LATITUDE / LONGITUDE, the sun's place, with whether
    the two agree.

    Reads only.

    Returns:
        str: JSON: {"located": bool, "latitude"?, "longitude"?, "point"?,
             "north_angle"?, "coordinate_system"?, "units"?,
             "sun_place": {"latitude", "longitude", "autocad_default": bool},
             "agrees"?: bool}

    Examples:
        - Use when: "is this drawing geo-located?" or "where is north set?"
        - Use when: before a daylight render, to check the sun's place is the site.
        - Don't use when: you want to set or change it — autocad_geo_location.

    Error Handling:
        - A drawing with no location answers located=false, not an error.
        - Without the plug-in it still gives the sun's place, and says why
          the location could not be read.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        found, why = plugin_read("geo_location")
        sun_lat, sun_lon = _sun_place(doc)
        payload: dict[str, Any] = _plain(found) if found is not None else {"located": None, "location_note": why}
        payload["sun_place"] = {
            "latitude": sun_lat,
            "longitude": sun_lon,
            "autocad_default": is_autocad_default(sun_lat, sun_lon),
        }
        if payload.get("located") and payload.get("latitude") is not None and sun_lat is not None and sun_lon is not None:
            payload["agrees"] = abs(payload["latitude"] - sun_lat) <= SAME_PLACE and abs(payload["longitude"] - sun_lon) <= SAME_PLACE
            if not payload["agrees"]:
                payload["warning"] = (
                    "The sun's place is not the drawing's location. autocad_geo_location with no latitude and "
                    "longitude moves the location to the sun's place; with them, it moves the sun to the site."
                )
        return payload

    return dumps(await run(work))
