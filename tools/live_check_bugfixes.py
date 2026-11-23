"""Live checks for the tool bugs the runner found (group BD, D-137).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Measured: a semicolon CSV comes in as three columns (BD4) and a super hatch refuses
a layer name it cannot use, with nothing made (BD6). The rows that open Heron's erase
box, look at pictures, or need a tile drawing or a second drawing are a person's.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import live_common as lc
from live_common import Check, Context, expect, parse, refusal

from autocad_mcp.tools import batch, blocks, draw, layers, superhatch, tables


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def bd4_a_semicolon_csv_comes_in_as_three_columns(ctx: Context) -> str:
    if ctx.folder is None:
        ctx.folder = Path(tempfile.mkdtemp(prefix="heron-live-check-"))
    path = ctx.folder / "lc-bd4-semicolon.csv"
    path.write_text('TAG;FLOW;NOTE\nF-01;2,5;"kitchen; roof"\n', encoding="utf-8")
    o = lc.origin("BD4")
    made = parse(await tables.autocad_table_from_excel(path=str(path), position=_at(o, 0, 0), layer="LC-BD4"))
    expect(made.get("created") is True, f"the table was not made: {str(made)[:160]}")
    expect(made.get("columns") == 3, f"the table has {made.get('columns')} column(s), not 3")
    return ("a CSV typed with ';' as its separator came in as 3 columns, not one. What is in each cell (F-01, 2,5 with its comma, "
            "'kitchen; roof') was not read back")


async def bd6_a_super_hatch_refuses_an_unusable_layer_name(ctx: Context) -> str:
    o = lc.origin("BD6")
    outline = parse(await draw.autocad_draw_polyline(points=[_at(o, 0, 0), _at(o, 3000, 0), _at(o, 3000, 2400), _at(o, 0, 2400)],
                                                    closed=True, layer="LC-BD6"))
    lines = parse(await batch.autocad_batch_draw(operations=[
        {"type": "line", "start": _at(o, 5000, 0), "end": _at(o, 5100, 0), "layer": "LC-BD6"},
        {"type": "line", "start": _at(o, 5000, 0), "end": _at(o, 5000, 100), "layer": "LC-BD6"},
    ]))
    parse(await blocks.autocad_make_block(name="LC-BD6-TILE", handles=lines["handles"], base_point=_at(o, 5000, 0)))
    before_objects = await lc.entity_count()
    before_layers = parse(await layers.autocad_list_layers())["count"]
    said = []
    for what, layer in (("|", "L|PAVE"), ("a line break", "L\nPAVE")):
        words = refusal(await superhatch.autocad_super_hatch(boundary=outline["handle"], block="LC-BD6-TILE", layer=layer))
        expect("layer name" in words.lower(), f"the layer name with {what} was refused without naming the layer name: {words[:160]}")
        said.append(words[:90])
    expect(await lc.entity_count() == before_objects, "something was made although both were refused")
    expect(parse(await layers.autocad_list_layers())["count"] == before_layers, "a layer appeared although both were refused")
    return "both refused naming the layer name (" + " | ".join(said) + "); no object made and no layer added"


CHECKS: tuple[Check, ...] = (
    Check("BD4", "BD", "a semicolon CSV comes in as three columns", bd4_a_semicolon_csv_comes_in_as_three_columns),
    Check("BD6", "BD", "a super hatch refuses an unusable layer name", bd6_a_super_hatch_refuses_an_unusable_layer_name),
)

BY_EYE: dict[str, str] = {
    "BD1": "needs a tile .dwg not yet attached, then External References and Heron's erase box looked at in AutoCAD",
    "BD2": "purging the layer brings up Heron's erase question, which a person answers (Keep them erased)",
    "BD3": "the pictures of the preview, in an isometric view and in plan, are looked at",
    "BD5": "needs the pump-room.dwg of the AC14 drawings open as a second drawing, and a layer's handle read from it",
}
