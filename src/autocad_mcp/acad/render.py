"""Plain arithmetic for lights and materials: no COM, tested offline.

AutoCAD's photometric lights take a colour temperature in Kelvin directly, but
a material's glow (self-illumination) has no Kelvin setting in the API: it
glows in the material's own colour. So a warm-white LED strip is made by
turning its Kelvin into the RGB of that white, here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

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
