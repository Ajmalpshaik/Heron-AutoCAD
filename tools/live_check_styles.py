"""Live checks for multileader and table styles made by the plug-in (group AN), and the busy-AutoCAD
rows of group AL (all left to a person: they need AutoCAD kept busy by hand).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
What AutoCAD's style dialogs show is not looked at: each style row comes back as
AutoCAD then holds it (the plug-in reads it back, D-104), and the current style is
read again from CMLEADERSTYLE / CTABLESTYLE.
"""

from __future__ import annotations

from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, parse

from autocad_mcp.core.answers import body
from autocad_mcp.tools import annotate, settings


def _row(out: dict[str, Any], key: str, name: str) -> dict[str, Any]:
    rows = [r for r in out.get(key) or [] if str(r.get("name", "")).upper() == name.upper()]
    expect(rows, f"the answer has no {key} row for {name}: {str(out)[:160]}")
    return rows[0]


def _said(raw: Any, key: str = "") -> str:
    """What a call said: its refusal, or the notes of its style rows."""
    text = body(raw)
    if isinstance(text, str) and text.startswith("Error:"):
        return text[7:]
    out = parse(raw)
    return " ".join(" ".join(r.get("notes") or []) for r in out.get(key) or [])


async def an1_a_tld_label_style_is_made_as_asked(ctx: Context) -> str:
    name = "LC-AN1-LABEL-50"
    row = _row(parse(await settings.autocad_create_styles(multileader_styles=[
        {"name": name, "text_height": 2.5, "scale": "1:50", "current": True}])), "multileader_styles", name)
    want = {"created": True, "attachment": "underline_bottom_line", "arrow": "closed_filled", "current": True}
    wrong = {k: row.get(k) for k, v in want.items() if row.get(k) != v}
    expect(not wrong, f"the style came back with {wrong}")
    expect(near(row.get("arrow_size"), 2.5, 1e-9) and near(row.get("dogleg_length"), 2.5, 1e-9) and near(row.get("scale"), 50, 1e-9),
           f"arrow {row.get('arrow_size')}, landing {row.get('dogleg_length')}, scale {row.get('scale')}")
    current = await lc.variable("CMLEADERSTYLE")
    expect(str(current).upper() == name, f"CMLEADERSTYLE reads {current}, not {name}")
    ctx.store["an1_style"] = name
    return (f"created: underline_bottom_line, closed_filled, arrow and landing 2.5, scale 50, current (CMLEADERSTYLE "
            f"{current}). The MLEADERSTYLE dialog was not opened")


async def an2_a_note_takes_the_current_style(ctx: Context) -> str:
    name = ctx.store.get("an1_style")
    if not name:
        await an1_a_tld_label_style_is_made_as_asked(ctx)
        name = ctx.store["an1_style"]
    o = lc.origin("AN2")
    made = parse(await annotate.autocad_add_multileader(landing=[o[0] + 1000, o[1] + 1000], arrows=[[o[0], o[1]]],
                                                        text="2 NOS FCU"))
    expect(not made.get("not_set"), f"something was not set: {made.get('not_set')}")
    got = await lc.read_props(made["handle"], ["StyleName", "TextHeight"])
    expect(str(got.get("StyleName")).upper() == name, f"the note is in style {got.get('StyleName')}, not {name}")
    expect(near(got.get("TextHeight"), 125.0, 1e-6), f"its text is {got.get('TextHeight')} high, not 125 (2.5 x 50)")
    return f"the note took {name}, text 125 high (2.5 x 50), nothing in not_set. Where the line runs under the text was not looked at"


async def an3_a_dot_style_comes_with_its_text_style(ctx: Context) -> str:
    dimblk = await lc.variable("DIMBLK")
    out = parse(await settings.autocad_create_styles(
        text_styles=[{"name": "LC-AN3-ROMANS", "font": "romans.shx"}],
        multileader_styles=[{"name": "LC-AN3-TAG-DOT", "text_style": "LC-AN3-ROMANS", "text_height": 2.5, "arrow": "dot",
                             "arrow_size": 1.5, "landing_gap": 0.5, "attachment": "middle"}]))
    expect(_row(out, "text_styles", "LC-AN3-ROMANS").get("created") is True, "the text style was not made")
    row = _row(out, "multileader_styles", "LC-AN3-TAG-DOT")
    expect(row.get("created") is True and str(row.get("text_style")).upper() == "LC-AN3-ROMANS", f"the style came back {row}")
    expect(row.get("arrow") == "dot" and near(row.get("arrow_size"), 1.5, 1e-9) and near(row.get("landing_gap"), 0.5, 1e-9),
           f"arrow {row.get('arrow')} {row.get('arrow_size')}, gap {row.get('landing_gap')}")
    expect("middle" in str(row.get("attachment")), f"the attachment is {row.get('attachment')}")
    added = row.get("arrow_block_added")
    expect(added in ("_DOT", None), f"arrow_block_added is {added!r}")
    after = await lc.variable("DIMBLK")
    expect(after == dimblk, f"DIMBLK went from {dimblk!r} to {after!r}")
    return (f"both made in one call; dot 1.5, gap 0.5, attachment {row['attachment']}; arrow_block_added {added!r} "
            f"(None when an earlier row had used the dot); DIMBLK unchanged ({dimblk!r})")


async def an5_an_existing_style_needs_replace(ctx: Context) -> str:
    name = "LC-AN5-LABEL"
    parse(await settings.autocad_create_styles(multileader_styles=[{"name": name, "text_height": 2.5, "scale": "1:50"}]))
    again = _row(parse(await settings.autocad_create_styles(multileader_styles=[{"name": name, "text_height": 3.5}])),
                 "multileader_styles", name)
    expect(again.get("created") is False and "replace=true" in " ".join(again.get("notes") or []),
           f"a second call without replace answered {again}")
    expect(again.get("text_height") in (None, 2.5) or near(again.get("text_height"), 2.5, 1e-9), "the refused call changed the height")
    done = _row(parse(await settings.autocad_create_styles(multileader_styles=[{"name": name, "text_height": 3.5}], replace=True)),
                "multileader_styles", name)
    expect(done.get("created") is False and near(done.get("text_height"), 3.5, 1e-9), f"with replace it answered {done}")
    expect(near(done.get("scale"), 1, 1e-9), f"the replaced style's scale is {done.get('scale')}, not back at 1")
    return "without replace: created false, 'Pass replace=true', nothing changed; with replace: height 3.5 and the scale back at 1"


async def an6_a_missing_text_style_stops_only_that_style(ctx: Context) -> str:
    raw = await settings.autocad_create_styles(multileader_styles=[
        {"name": "LC-AN6-BAD", "text_height": 2.5, "text_style": "LC-AN6-NOPE"}, {"name": "LC-AN6-GOOD", "text_height": 2.5}])
    out = parse(raw)
    bad, good = _row(out, "multileader_styles", "LC-AN6-BAD"), _row(out, "multileader_styles", "LC-AN6-GOOD")
    said = " ".join(bad.get("notes") or [])
    expect(bad.get("created") is False and "no text style called 'LC-AN6-NOPE'" in said, f"BAD answered {bad}")
    expect(good.get("created") is True, f"GOOD answered {good}")
    again = _row(parse(await settings.autocad_create_styles(multileader_styles=[{"name": "LC-AN6-BAD", "text_height": 2.5}])),
                 "multileader_styles", "LC-AN6-BAD")
    expect(again.get("created") is True, "BAD was in the drawing after all (making it again found one)")
    return "BAD refused 'no text style called ...', GOOD made; making BAD afterwards found none there. MLEADERSTYLE was not opened"


async def an7_a_schedule_style_is_middle_and_current(ctx: Context) -> str:
    name = "LC-AN7-SCHEDULE-50"
    row = _row(parse(await settings.autocad_create_styles(table_styles=[
        {"name": name, "text_height": 2.5, "scale": "1:50", "alignment": "left", "current": True}])), "table_styles", name)
    heights = row.get("text_heights") or {}
    expect(all(near(heights.get(k), 125, 1e-6) for k in ("title", "header", "data")), f"text heights {heights}")
    margins = row.get("margins") or {}
    expect(near(margins.get("horizontal"), 41.67, 0.01) and near(margins.get("vertical"), 41.67, 0.01), f"margins {margins}")
    align = row.get("alignment") or {}
    expect(align.get("title") == align.get("header") == "middle_centre" and align.get("data") == "middle_left",
           f"alignment {align}")
    current = await lc.variable("CTABLESTYLE")
    expect(row.get("current") is True and str(current).upper() == name, f"CTABLESTYLE reads {current}")
    ctx.store["an7_style"] = name
    return f"text 125 / 125 / 125, margins 41.67, title and header middle_centre, data middle_left, current (CTABLESTYLE {current})"


async def an8_a_table_takes_the_style(ctx: Context) -> str:
    name = ctx.store.get("an7_style")
    if not name:
        await an7_a_schedule_style_is_middle_and_current(ctx)
        name = ctx.store["an7_style"]
    o = lc.origin("AN8")
    made = parse(await annotate.autocad_add_table(position=[o[0], o[1]], title="AHU SCHEDULE", headers=["TAG", "CFM"],
                                                  rows=[["AHU-1", "2000"]], style=name))
    expect(made.get("rows_aligned_middle") == 3, f"rows_aligned_middle is {made.get('rows_aligned_middle')}, not 3")
    got = await lc.read_props(made["handle"], ["StyleName"])
    expect(str(got.get("StyleName")).upper() == name, f"the table is in style {got.get('StyleName')}")
    return f"the table took {name}, rows_aligned_middle 3. The text height and left data were not read cell by cell"


async def an9_a_style_without_title_or_header_rows(ctx: Context) -> str:
    name = "LC-AN9-NO-TITLE"
    row = _row(parse(await settings.autocad_create_styles(table_styles=[
        {"name": name, "text_height": 2.5, "title_row": False, "header_row": False}])), "table_styles", name)
    expect(row.get("title_row") is False and row.get("header_row") is False, f"title_row {row.get('title_row')}, header_row {row.get('header_row')}")
    o = lc.origin("AN9")
    made = parse(await annotate.autocad_add_table(position=[o[0], o[1]], rows=[["A", "1"], ["B", "2"]], style=name))
    expect(not made.get("headers") and made.get("data_rows") == made.get("rows") == 2,
           f"the table has {made.get('rows')} rows, {made.get('data_rows')} of data")
    return "title_row false, header_row false; the table starts with a data row (2 rows, both data). The dialog was not opened"


async def an10_wrong_options_are_said_and_nothing_kept(ctx: Context) -> str:
    a = _said(await settings.autocad_create_styles(table_styles=[{"name": "LC-AN10-A", "text_height": 2.5, "alignment": "top left"}]),
              "table_styles")
    b = _said(await settings.autocad_create_styles(multileader_styles=[{"name": "LC-AN10-B", "text_height": 2.5, "scale": 0.02}]),
              "multileader_styles")
    c = _said(await settings.autocad_create_styles(multileader_styles=[{"name": "LC-AN10-C", "text_height": 2.5, "arow": "dot"}]),
              "multileader_styles")
    expect("vertical middle" in a, f"A was answered: {a[:140]}")
    expect("could be a ratio or a scale factor" in b and "1:50" in b, f"B was answered: {b[:140]}")
    expect("arow" in c and "not an option" in c, f"C was answered: {c[:140]}")
    again = parse(await settings.autocad_create_styles(
        table_styles=[{"name": "LC-AN10-A", "text_height": 2.5}],
        multileader_styles=[{"name": "LC-AN10-B", "text_height": 2.5}, {"name": "LC-AN10-C", "text_height": 2.5}]))
    kept = [r["name"] for key in ("table_styles", "multileader_styles") for r in again.get(key) or [] if r.get("created") is not True]
    expect(not kept, f"these were in the drawing after all: {kept}")
    return "A: 'vertical middle'; B: 'could be a ratio or a scale factor ... 1:50'; C: 'arow is not an option'; none of the three was kept"


async def an13_a_missing_style_leaves_nothing_behind(ctx: Context) -> str:
    o = lc.origin("AN13")
    before = await lc.entity_count()
    table = lc.refusal(await annotate.autocad_add_table(position=[o[0], o[1]], rows=[["A"]], style="LC-AN13-NOPE"))
    leader = lc.refusal(await annotate.autocad_add_multileader(landing=[o[0] + 500, o[1] + 500], arrows=[[o[0], o[1]]],
                                                               text="X", style="LC-AN13-NOPE"))
    after = await lc.entity_count()
    for what, said in (("the table", table), ("the multileader", leader)):
        expect("LC-AN13-NOPE" in said and "Nothing was left in the drawing" in said, f"{what} was answered: {said[:160]}")
    expect(after == before, f"{after - before} objects were left behind")
    return f"both refused with 'Nothing was left in the drawing'; the drawing still has {after} objects, as before"


CHECKS: tuple[Check, ...] = (
    Check("AN1", "AN", "a TLD label style is made as asked", an1_a_tld_label_style_is_made_as_asked),
    Check("AN2", "AN", "a note takes the current style", an2_a_note_takes_the_current_style),
    Check("AN3", "AN", "a dot style comes with its text style", an3_a_dot_style_comes_with_its_text_style),
    Check("AN5", "AN", "an existing style needs replace", an5_an_existing_style_needs_replace),
    Check("AN6", "AN", "a missing text style stops only that style", an6_a_missing_text_style_stops_only_that_style),
    Check("AN7", "AN", "a schedule style is middle and current", an7_a_schedule_style_is_middle_and_current),
    Check("AN8", "AN", "a table takes the style", an8_a_table_takes_the_style),
    Check("AN9", "AN", "a style without title or header rows", an9_a_style_without_title_or_header_rows),
    Check("AN10", "AN", "wrong options are said and nothing kept", an10_wrong_options_are_said_and_nothing_kept),
    Check("AN13", "AN", "a missing style leaves nothing behind", an13_a_missing_style_leaves_nothing_behind),
)

_BUSY = "needs AutoCAD kept busy by hand (the Options dialog open, or a heavy REGEN) while it runs"

BY_EYE: dict[str, str] = {
    "AN4": "whether one Ctrl+Z takes the text style, the multileader style and the _DOT block together is read in the dialogs",
    "AN11": "needs Changes off; the runner works with Changes on",
    "AN12": "needs a plug-in built before this change installed",
    **{f"AL{n}": _BUSY for n in range(1, 8)},
    "AL4": "needs Ask to Keep on, your Discard click, and a heavy REGEN started by hand",
}
