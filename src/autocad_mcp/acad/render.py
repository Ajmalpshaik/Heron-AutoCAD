"""Plain arithmetic for lights and materials: no COM, tested offline.

AutoCAD's photometric lights take a colour temperature in Kelvin directly, but
a material's glow (self-illumination) has no Kelvin setting in the API: it
glows in the material's own colour. So a warm-white LED strip is made by
turning its Kelvin into the RGB of that white, here.
"""

from __future__ import annotations

import datetime
import math
from collections.abc import Sequence
from typing import Any

from ..core.errors import AutocadError

# AutoCAD's own limits for a lamp's colour temperature.
KELVIN_MIN = 1000.0
KELVIN_MAX = 20000.0

# AutoCAD refuses a spotlight cone wider than this.
CONE_MAX_DEGREES = 160.0

# The image files AutoCAD takes as a texture or bump map.
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".tga", ".gif")


def kelvin_to_rgb(kelvin: float) -> list[int]:
    """The RGB (0-255) of a white light at this colour temperature.

    The usual curve fitted to the black-body colours (Tanner Helland's): close
    enough to pick a warm or a cool white, not a colour-science result.
    2700 K is a warm lamp, 4000 K a neutral one, 6500 K daylight.
    """
    if not KELVIN_MIN <= kelvin <= KELVIN_MAX:
        raise AutocadError(
            f"A colour temperature of {kelvin:g} K is outside {KELVIN_MIN:g}-{KELVIN_MAX:g} K. "
            "Warm white is 2700-3000 K, neutral 4000 K, daylight 6500 K."
        )
    t = kelvin / 100.0
    if t <= 66:
        red = 255.0
        green = 99.4708025861 * math.log(t) - 161.1195681661
        blue = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        red = 329.698727446 * ((t - 60) ** -0.1332047592)
        green = 288.1221695283 * ((t - 60) ** -0.0755148492)
        blue = 255.0
    return [int(round(min(255.0, max(0.0, v)))) for v in (red, green, blue)]


def check_rgb(value: Sequence[int] | None, name: str) -> list[int] | None:
    """Three whole numbers 0-255, or a refusal that names the option."""
    if value is None:
        return None
    if len(value) != 3 or any(isinstance(v, bool) or not 0 <= int(v) <= 255 for v in value):
        raise AutocadError(f"'{name}' must be three numbers 0-255, [red, green, blue], e.g. [255, 214, 170].")
    return [int(v) for v in value]


def unit_vector(vector: Sequence[float], name: str) -> list[float]:
    """A direction scaled to length 1, or a refusal when it has no length."""
    length = math.sqrt(sum(float(v) ** 2 for v in vector[:3]))
    if length < 1e-12:
        raise AutocadError(f"'{name}' has no length, so it points nowhere.")
    return [float(v) / length for v in vector[:3]]


# ---------------------------------------------------------------------------
# The sun and the render exposure (D-86, D-87)
# ---------------------------------------------------------------------------

# The render's Exposure (EV) and White balance (Kelvin), as Autodesk's help gives
# the EXPVALUE and EXPWHITEBALANCE variables (2016-2023): a lower exposure is a
# brighter picture.
EXPOSURE_MIN = -6.0
EXPOSURE_MAX = 21.0
WHITE_BALANCE_MIN = 1000.0
WHITE_BALANCE_MAX = 20000.0

# The whole-hour UTC offsets AutoCAD's TIMEZONE table runs between.
UTC_OFFSET_MIN = -12.0
UTC_OFFSET_MAX = 13.0

MS_PER_DAY = 24 * 60 * 60 * 1000

# The years the plug-in takes for the sun's date (SunClock in the Bridge).
SUN_YEAR_MIN = 1900
SUN_YEAR_MAX = 2200


def parse_date(text: str) -> tuple[int, int, int]:
    """'2026-06-21' as (year, month, day), or a refusal that shows the form."""
    try:
        when = datetime.date.fromisoformat(str(text).strip())
    except ValueError:
        raise AutocadError(
            f"'{text}' is not a date Heron can read. Give it as year-month-day, e.g. '2026-06-21'."
        ) from None
    return when.year, when.month, when.day


def parse_time(text: str) -> tuple[int, int]:
    """'10:30' (24-hour clock, at the site) as (hour, minute), or a refusal."""
    parts = str(text).strip().split(":")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise AutocadError(
            f"'{text}' is not a time Heron can read. Give the clock time at the site as "
            "hours:minutes on a 24-hour clock, e.g. '10:30' or '16:45'."
        )
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise AutocadError(f"'{text}' is not a time of day: hours 0-23, minutes 0-59.")
    return hour, minute


def julian_day(year: int, month: int, day: int) -> int:
    """The Julian day number of a calendar date (Gregorian): 2000-01-01 is 2451545.

    What the sun object of a viewport keeps as its date (DXF group 91 of the
    SUN object). The usual integer formula; no time of day in it.
    """
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def ms_after_midnight(hour: int, minute: int, second: int = 0) -> int:
    """The clock time as milliseconds after midnight (DXF group 92 of the SUN object)."""
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise AutocadError(f"{hour}:{minute:02d}:{second:02d} is not a time of day.")
    return ((hour * 60 + minute) * 60 + second) * 1000


def timezone_code(utc_offset: float) -> int:
    """AutoCAD's TIMEZONE code for a UTC offset in hours: hours x 1000 plus minutes.

    +3 (Doha, Riyadh) is 3000, +4 (Dubai) 4000, +5.5 (India) 5030, +5.75
    (Nepal) 5045, -3.5 (Newfoundland) -3030. AutoCAD keeps a few codes per
    offset for named places (e.g. 3001); this gives the first of them. The
    minutes must be 0, 30 or 45, as every real time zone's are.
    """
    if not UTC_OFFSET_MIN <= utc_offset <= UTC_OFFSET_MAX:
        raise AutocadError(
            f"A UTC offset of {utc_offset:g} hours is outside {UTC_OFFSET_MIN:g} to +{UTC_OFFSET_MAX:g}."
        )
    sign = -1 if utc_offset < 0 else 1
    whole_minutes = round(abs(utc_offset) * 60)
    if abs(abs(utc_offset) * 60 - whole_minutes) > 1e-6 or whole_minutes % 60 not in (0, 30, 45):
        raise AutocadError(
            f"A UTC offset of {utc_offset:g} hours is not a time zone: give whole hours, or "
            "half and three-quarter hours such as 5.5 (India) or 5.75 (Nepal)."
        )
    hours, minutes = divmod(whole_minutes, 60)
    return sign * (hours * 1000 + minutes)


def timezone_offset(code: Any) -> float | None:
    """The UTC offset in hours a TIMEZONE code means, or None when it cannot be told.

    The last three digits are the minutes (30 or 45), with a last digit that
    can name one place of several at that offset (9031 is still +9:30), or,
    below 10, only that place (3001 is still +3).
    """
    try:
        value = int(code)
    except (TypeError, ValueError):
        return None
    sign = -1 if value < 0 else 1
    hours, rest = divmod(abs(value), 1000)
    if 30 <= rest < 40:
        minutes = 30
    elif 45 <= rest < 50:
        minutes = 45
    elif rest < 10:
        minutes = 0
    else:
        return None
    offset = sign * (hours + minutes / 60.0)
    return offset if UTC_OFFSET_MIN <= offset <= UTC_OFFSET_MAX else None
