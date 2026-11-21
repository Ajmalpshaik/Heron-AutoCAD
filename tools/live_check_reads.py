"""Live checks for the reads the plug-in does in one go (group AS) and PDF Import (group AO).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Most AS rows compare the plug-in's answer with the same call to a second server
started with --no-bridge, and read the plug-in's log: the runner starts no
second server and never switches the gate off, so those are left to a person.
The AO rows need the PDFs they name and AutoCAD's prompts typed by hand.
"""

from __future__ import annotations

import live_common as lc
from live_common import Check, Context, expect, parse, refusal

from autocad_mcp.tools import draw_extra, layers, query


async def as5_rays_and_an_empty_layer_say_why_there_are_no_extents(ctx: Context) -> str:
    o = lc.origin("AS5")
    parse(await draw_extra.autocad_add_construction_line(base=[o[0], o[1]], angle=90, layer="LC-AS5"))
    parse(await draw_extra.autocad_add_construction_line(base=[o[0], o[1]], through=[o[0] + 300, o[1] + 400], kind="ray",
                                                         layer="LC-AS5"))
    rays = refusal(await query.autocad_get_extents(layer="LC-AS5"))
    expect("has 2 object(s), but none with extents" in rays, f"the layer of an xline and a ray answered: {rays[:140]}")
    parse(await layers.autocad_create_layer(name="LC-AS5-EMPTY"))
    empty = refusal(await query.autocad_get_extents(layer="LC-AS5-EMPTY"))
    expect("has no geometry" in empty, f"the empty layer answered: {empty[:140]}")
    return ("an xline and a ray: 'has 2 object(s), but none with extents'; an empty layer: 'has no geometry'. "
            "The same call over COM (--no-bridge) was not compared")


CHECKS: tuple[Check, ...] = (
    Check("AS5", "AS", "rays and an empty layer say why no extents", as5_rays_and_an_empty_layer_say_why_there_are_no_extents),
)

_OVER_COM = ("compares the plug-in's answer with a second server started with --no-bridge and reads the plug-in's "
             "log; the runner starts no second server")
_PDF = "needs the PDFs the row names (printed from AutoCAD, two pages, TrueType text; a scan), not made by the runner"

BY_EYE: dict[str, str] = {
    "AS1": "needs a real project drawing with sheets, and " + _OVER_COM,
    "AS2": "needs a real project drawing, and " + _OVER_COM,
    "AS3": "needs a drawing of 20,000 objects and both times written down, and " + _OVER_COM,
    "AS4": _OVER_COM,
    "AS6": "needs a line drawn by hand and Ctrl+Z pressed by hand",
    "AS7": "needs plug-in 1.7.0 or older installed",
    "AS8": "needs objects selected by hand and SELECT P typed",
    "AS9": "needs LINE started by hand and left waiting",
    "AO1": "needs -PDFIMPORT typed by hand and its prompts written down",
    "AO2": _PDF,
    "AO3": _PDF,
    "AO4": _PDF,
    "AO5": "needs Import as block ticked in AutoCAD's PDF Import dialog by hand",
    "AO6": _PDF,
    "AO7": _PDF,
    "AO8": "needs a PDF in a folder with spaces and an accented letter",
    "AO9": "needs a 1:100 A1 PDF of a mm drawing, and the right scale worked out by you",
    "AO10": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
}
