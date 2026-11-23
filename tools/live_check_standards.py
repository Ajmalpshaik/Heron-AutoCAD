"""Live checks for the office layer standard (group AT).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Importing, replacing and removing the office standard write the modeller's own
``office-layers.json`` in %LOCALAPPDATA%\\Heron\\autocad\\standards, which a check
cannot give an ``lc-`` name, so those rows are left to a person. What is measured is
read-only or refused before anything is written: a bad CSV is refused (nothing is
written, and ``show`` is compared before and after), and the two checks and the
remap that need *no* office standard run only on a PC that has none, otherwise they
are said as not run this time.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import live_common as lc
from live_common import Check, Context, expect, parse, refusal

from autocad_mcp.tools import convert, layer_standard, standards

BAD_CSV = (
    "layer,color,linetype,lineweight,plot,description,replaces,required\n"
    "M-A,reed,,,,,,\n"
    "M-B,1,,0.33,,,,\n"
)
NO_OFFICE = "an office layer standard is loaded on this PC, and the row needs none; removing it is the modeller's choice"


async def _no_office_standard() -> None:
    """Say 'not run this time' when this PC has an office standard loaded: the runner never removes one."""
    shown = parse(await layer_standard.autocad_layer_standard(action="show"))
    if shown.get("office_standard"):
        raise lc.Refused(f"not run this time: {NO_OFFICE}")


async def at3_a_csv_with_wrong_cells_is_refused_and_nothing_changes(ctx: Context) -> str:
    if ctx.folder is None:
        ctx.folder = Path(tempfile.mkdtemp(prefix="heron-live-check-"))
    path = ctx.folder / "standards" / "lc-at3-bad.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BAD_CSV, encoding="utf-8")
    before = parse(await layer_standard.autocad_layer_standard(action="show"))
    said = refusal(await layer_standard.autocad_layer_standard(action="import", path=str(path)))
    expect("row 2" in said and "reed" in said, f"the wrong colour is not named with its row: {said[:200]}")
    expect("row 3" in said and "0.33" in said, f"the wrong lineweight is not named with its row: {said[:200]}")
    after = parse(await layer_standard.autocad_layer_standard(action="show"))
    expect(after == before, f"the office standard changed: {str(before)[:120]} then {str(after)[:120]}")
    return (f"imported nothing; both problems named with Excel's row numbers ({said[:150]}); show reads the same before and "
            "after. The import of a good CSV (AT1) was not tried, so the standard on this PC was never written")


async def at5_an_unloaded_office_standard_is_not_a_pass(ctx: Context) -> str:
    await _no_office_standard()
    out = parse(await standards.autocad_check_standards(layer_standard="office"))
    expect(out.get("passed") is None, f"passed is {out.get('passed')!r}, not null")
    warning = str((out.get("layer_standard") or {}).get("warning", ""))
    expect("No office layer standard is loaded" in warning and "example" in warning,
           f"the warning does not say no office standard is loaded and the example was used: {warning[:160]}")
    return "no office standard on this PC: passed is null and the warning says it was checked against the generic MEP example"


async def at7_a_remap_with_no_office_standard_is_refused(ctx: Context) -> str:
    await _no_office_standard()
    said = refusal(await convert.autocad_remap_layers(layer_standard="office"))
    expect("No office layer standard is loaded" in said and "Nothing was moved" in said,
           f"the remap was refused in other words: {said[:160]}")
    return "no office standard on this PC: the remap was refused ('No office layer standard is loaded ... Nothing was moved'), before anything was read"


async def at8_the_example_says_it_is_the_example(ctx: Context) -> str:
    out = parse(await standards.autocad_check_standards(layer_standard="example"))
    info = out.get("layer_standard") or {}
    expect(info.get("example") is True, f"layer_standard.example is {info.get('example')!r}")
    expect("generic MEP example" in str(info.get("note", "")) and "not an office" in str(info.get("note", "")),
           f"the note does not say it is the generic example: {str(info.get('note'))[:160]}")
    expect("generic MEP example" in str(out.get("source", "")), f"the source reads {out.get('source')!r}")
    return "checked against the example: layer_standard.example is true and the note and the source both say it is the generic MEP example, not an office's"


CHECKS: tuple[Check, ...] = (
    Check("AT3", "AT", "a CSV with wrong cells is refused and nothing changes", at3_a_csv_with_wrong_cells_is_refused_and_nothing_changes),
    Check("AT5", "AT", "an unloaded office standard is not a pass", at5_an_unloaded_office_standard_is_not_a_pass),
    Check("AT7", "AT", "a remap with no office standard is refused", at7_a_remap_with_no_office_standard_is_refused),
    Check("AT8", "AT", "the example says it is the example", at8_the_example_says_it_is_the_example),
)

_WRITES = "a standard imported or removed here is the modeller's own office-layers.json, which the runner never writes"

BY_EYE: dict[str, str] = {
    "AT1": "needs the CSV filled in Excel with the office's real layers, and " + _WRITES,
    "AT2": "needs a CSV saved from Excel with an accented letter, and " + _WRITES,
    "AT4": "needs an office standard loaded first, and two layers compared by hand in the Layer Properties Manager; " + _WRITES,
    "AT6": "moves objects between layers of a real MEP drawing, and needs an office standard loaded first; " + _WRITES,
}
