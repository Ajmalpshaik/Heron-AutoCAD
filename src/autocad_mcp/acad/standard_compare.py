"""A drawing's layers and styles against a reference drawing's (#69, D-92).

The reference is an office standards file (.dws), a template or any drawing
(.dwg / .dxf). Both sides arrive as the same plain tables, from ezdxf
(acad/dxf_file.tables) or from COM (tools/standards.com_tables), so the compare
is pure and tested without AutoCAD.

What is compared, per table:
  layers       colour, linetype, lineweight, plot / no plot
  text styles  font, big font, height, width factor, oblique angle
  dim styles   the name only: COM cannot read a dimension style's settings
               without making that style current, which would change the drawing
  linetypes    the name only

Each finding says which: missing (in the standard, not in this drawing),
differs (both have it; the values named), or not in the standard (in this
drawing only; can be left out with flag_extra=False). Xref names (XREF|NAME)
and anonymous names (*U12) are left out on both sides, and the names AutoCAD
makes itself (layer 0, Defpoints, Standard, ByLayer...) are never missing or
extra, only compared when both have them. A finding is a value
that differs from the reference; a clean result means the checked values are
met against that file, never that the drawing complies with anything (D-64).
"""

from __future__ import annotations

import re
from typing import Any

from .dxf_file import ALWAYS_THERE

KINDS = ("layers", "text_styles", "dim_styles", "linetypes")
WORD = {"layers": "layer", "text_styles": "text_style", "dim_styles": "dim_style", "linetypes": "linetype"}
SAID = {"layers": "layer", "text_styles": "text style", "dim_styles": "dimension style", "linetypes": "linetype"}
COMPARED = {
    "layers": "colour, linetype, lineweight and plot / no plot",
    "text_styles": "font, big font, height, width factor and oblique angle",
    "dim_styles": (
        "the name only: AutoCAD's COM cannot read a dimension style's settings without making it "
        "current, which would change the drawing"
    ),
    "linetypes": "the name only",
}
LEFT_OUT = "Xref names (XREF|NAME) and anonymous names (*U12) are left out on both sides."
LINEWEIGHT = {-3: "Default", -2: "ByLayer", -1: "ByBlock"}


def usable(name: Any) -> bool:
    text = str(name or "")
    return bool(text) and not text.startswith("*") and "|" not in text


def font_key(file: Any, family: Any = "") -> str:
    """'C:\\Fonts\\romans.shx', 'romans' and 'ROMANS.SHX' are one font; a TrueType family when no file."""
    base = re.split(r"[\\/]", str(file or "").strip())[-1].lower()
    base = re.sub(r"\.(shx|ttf|ttc|otf)$", "", base)
    return base or str(family or "").strip().lower()


def _weight(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    return LINEWEIGHT.get(number, f"{number / 100:.2f} mm")


def _close(a: Any, b: Any, tolerance: float) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance * max(1.0, abs(float(b)))
    except (TypeError, ValueError):
        return a == b


def layer_differences(here: dict[str, Any], standard: dict[str, Any]) -> list[str]:
    found = []
    if here.get("color") != standard.get("color"):
        found.append(f"colour {here.get('color')} here, {standard.get('color')} in the standard")
    if str(here.get("linetype", "")).lower() != str(standard.get("linetype", "")).lower():
        found.append(f"linetype {here.get('linetype')} here, {standard.get('linetype')} in the standard")
    if here.get("lineweight") != standard.get("lineweight"):
        found.append(f"lineweight {_weight(here.get('lineweight'))} here, {_weight(standard.get('lineweight'))} in the standard")
    if bool(here.get("plottable", True)) != bool(standard.get("plottable", True)):
        found.append(f"{'plots' if here.get('plottable', True) else 'does not plot'} here, "
                     f"{'plots' if standard.get('plottable', True) else 'does not plot'} in the standard")  # fmt: skip
    return found


def text_style_differences(here: dict[str, Any], standard: dict[str, Any]) -> list[str]:
    found = []
    if font_key(here.get("font"), here.get("family")) != font_key(standard.get("font"), standard.get("family")):
        found.append(f"font {here.get('font') or here.get('family') or 'none'} here, "
                     f"{standard.get('font') or standard.get('family') or 'none'} in the standard")  # fmt: skip
    if font_key(here.get("bigfont")) != font_key(standard.get("bigfont")):
        found.append(f"big font {here.get('bigfont') or 'none'} here, {standard.get('bigfont') or 'none'} in the standard")
    if not _close(here.get("height", 0), standard.get("height", 0), 1e-6):
        found.append(f"height {here.get('height')} here, {standard.get('height')} in the standard")
    if not _close(here.get("width", 1), standard.get("width", 1), 1e-4):
        found.append(f"width factor {here.get('width')} here, {standard.get('width')} in the standard")
    if not _close(here.get("oblique", 0), standard.get("oblique", 0), 1e-4):
        found.append(f"oblique angle {here.get('oblique')} degrees here, {standard.get('oblique')} in the standard")
    return found


DIFFERENCES = {"layers": layer_differences, "text_styles": text_style_differences}


def compare(here: dict[str, list[dict]], standard: dict[str, list[dict]], flag_extra: bool = True) -> list[dict[str, Any]]:
    """Every name that is missing, differs or is not in the standard, table by table, A-Z."""
    findings: list[dict[str, Any]] = []
    for kind in KINDS:
        mine = {str(row["name"]).lower(): row for row in here.get(kind) or [] if usable(row.get("name"))}
        theirs = {str(row["name"]).lower(): row for row in standard.get(kind) or [] if usable(row.get("name"))}
        word, said = WORD[kind], SAID[kind]
        for key in sorted(theirs):
            wanted = theirs[key]
            row = mine.get(key)
            if row is None:
                if key in ALWAYS_THERE[kind]:
                    continue  # Defpoints, Standard, ByLayer: AutoCAD makes them when needed
                findings.append({"rule": f"standard_{word}_missing", "table": said, "name": str(wanted["name"]),
                                 "detail": f"the standard has this {said}; this drawing does not"})  # fmt: skip
                continue
            differences = DIFFERENCES.get(kind, lambda a, b: [])(row, wanted)
            if differences:
                findings.append({"rule": f"{word}_differs_from_standard", "table": said, "name": str(row["name"]),
                                 "detail": "; ".join(differences)})  # fmt: skip
        if flag_extra:
            for key in sorted(set(mine) - set(theirs) - ALWAYS_THERE[kind]):
                findings.append({"rule": f"{word}_not_in_standard", "table": said, "name": str(mine[key]["name"]),
                                 "detail": f"this drawing has this {said}; the standard does not"})  # fmt: skip
    return findings


def counted(tables: dict[str, list[dict]]) -> dict[str, int]:
    """How many usable names each table holds: what was compared."""
    return {kind: sum(1 for row in tables.get(kind) or [] if usable(row.get("name"))) for kind in KINDS}
