"""An object's own properties as a draftsman names them: lineweight, transparency,
and the set match properties copies (issue #111, D-79).

Plain functions, tested without AutoCAD. AutoCAD keeps a lineweight as hundredths
of a millimetre from a fixed list, with -1 ByLayer, -2 ByBlock and -3 Default,
and an object's transparency as the text "ByLayer", "ByBlock" or "0" to "90"
(its EntityTransparency property).
"""

from __future__ import annotations

import math
from typing import Any

LW_BYLAYER, LW_BYBLOCK, LW_DEFAULT = -1, -2, -3

# Every lineweight AutoCAD offers, in hundredths of a millimetre.
LINEWEIGHTS = (0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211)

_LW_WORDS = {"bylayer": LW_BYLAYER, "byblock": LW_BYBLOCK, "default": LW_DEFAULT}

LINEWEIGHT_HELP = (
    "Give a lineweight in millimetres as AutoCAD lists them (0.13, 0.18, 0.25, 0.35, 0.50, 0.70 ... 2.11), "
    "the same in hundredths (25 = 0.25 mm), or ByLayer, ByBlock or Default."
)

TRANSPARENCY_HELP = "Give a transparency from 0 (solid) to 90, or ByLayer or ByBlock."


def lineweight_value(value: Any) -> int:
    """A lineweight from 0.25, '0.25 mm', 25, 'ByLayer' ... as AutoCAD's own number.

    A number up to 2.11 is millimetres; 5 or more is hundredths. Nothing valid
    lies between, so the two never clash.
    """
    if isinstance(value, bool):
        raise ValueError(f"'{value}' is not a lineweight. {LINEWEIGHT_HELP}")
    text = str(value).strip().lower().replace("mm", "").strip()
    if text in _LW_WORDS:
        return _LW_WORDS[text]
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"'{value}' is not a lineweight. {LINEWEIGHT_HELP}") from None
    if not math.isfinite(number):
        raise ValueError(f"'{value}' is not a lineweight. {LINEWEIGHT_HELP}")
    hundredths = number * 100.0 if number <= 2.11 + 1e-9 else number
    code = round(hundredths)
    if abs(hundredths - code) > 1e-6 or code not in LINEWEIGHTS:
        raise ValueError(f"{value} is not a lineweight AutoCAD has. {LINEWEIGHT_HELP}")
    return code


def lineweight_words(code: Any) -> str:
    """AutoCAD's lineweight number as the Properties palette shows it."""
    try:
        number = int(code)
    except (TypeError, ValueError):
        return str(code)
    names = {LW_BYLAYER: "ByLayer", LW_BYBLOCK: "ByBlock", LW_DEFAULT: "Default"}
    return names.get(number, f"{number / 100:.2f} mm")


def transparency_value(value: Any) -> str:
    """A transparency from 50, '50%', 'ByLayer' ... as the text AutoCAD's EntityTransparency takes."""
    if isinstance(value, bool):
        raise ValueError(f"'{value}' is not a transparency. {TRANSPARENCY_HELP}")
    text = str(value).strip().rstrip("%").strip()
    low = text.lower()
    if low == "bylayer":
        return "ByLayer"
    if low == "byblock":
        return "ByBlock"
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"'{value}' is not a transparency. {TRANSPARENCY_HELP}") from None
    if not math.isfinite(number):
        raise ValueError(f"'{value}' is not a transparency. {TRANSPARENCY_HELP}")
    if number != int(number):
        raise ValueError(f"A transparency is a whole number; {value} is not. {TRANSPARENCY_HELP}")
    if not 0 <= number <= 90:
        raise ValueError(
            f"{value} is outside 0 to 90. AutoCAD stops at 90 so a see-through object never looks "
            "switched off."
        )
    return str(int(number))


# What match properties can copy, in the order the Properties palette lists them.
GENERAL = ("layer", "color", "linetype", "linetype_scale", "lineweight", "transparency")
MATCHABLE = GENERAL + ("text_style", "dim_style")

# Which kinds of object carry the two style properties.
TEXT_KINDS = frozenset({"text", "mtext", "attdef"})
DIM_KINDS = frozenset({"dimension"})


def matched_properties(asked: list[str] | None) -> list[str]:
    """The properties to copy: the general six when none are named, all eight for 'all'."""
    if not asked:
        return list(GENERAL)
    out: list[str] = []
    for name in asked:
        key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
        key = {"colour": "color", "ltscale": "linetype_scale", "textstyle": "text_style",
               "dimstyle": "dim_style", "style": "text_style"}.get(key, key)
        if key == "all":
            return list(MATCHABLE)
        if key == "general":
            out.extend(p for p in GENERAL if p not in out)
            continue
        if key not in MATCHABLE:
            raise ValueError(
                f"'{name}' is not a property match properties copies. Use any of: {', '.join(MATCHABLE)}, "
                "'general' (the first six) or 'all'."
            )
        if key not in out:
            out.append(key)
    return out


def applies_to(prop: str, kind: str) -> bool:
    """Whether a kind of object has this property at all."""
    if prop == "text_style":
        return kind in TEXT_KINDS
    if prop == "dim_style":
        return kind in DIM_KINDS
    return True
