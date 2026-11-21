"""Live checks for Heron's own behaviour: groups M to Z.

The save guard, the preview, project notes, check lists, undoing Heron's last
change, saved commands, the plain first line of every change answer (D-62), dry
runs (D-63), autocad_why and the tool finder, long AutoLISP in pieces and quiet
answers. Run by ``live_check.py``; see ``live_common.py`` for the rules every
check keeps. Most of these groups are about clicks in Heron's own windows, a
second AutoCAD, a restart or the Windows registry: those rows are in BY_EYE,
each with its reason.

Anything a row saves on this PC outside the drawing (a check list, a saved
command, a project note) has a name of its own ("lc-...") and is deleted again
by the same row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, parse, refusal

from autocad_mcp.core.answers import body
from autocad_mcp.tools import (
    activity,
    advanced,
    batch,
    blocks,
    checklists,
    document,
    draw,
    explain,
    layers,
    modify,
    project_notes,
    query,
    resources,
    saved_commands,
    sequence,
    settings,
    solid_edits,
    solids,
    standards,
    text_tools,
)

BEFORE_ISSUE = "before issue"


def _at(o: tuple[float, float], x: float, y: float, z: float | None = None) -> list[float]:
    return [o[0] + x, o[1] + y] + ([z] if z is not None else [])


async def _draw(*operations: dict[str, Any]) -> list[str]:
    made = parse(await batch.autocad_batch_draw(operations=list(operations)))
    expect(made.get("created") == len(operations), f"drew {made.get('created')} of {len(operations)} test objects")
    return list(made["handles"])


async def _drawing_file() -> tuple[str, Any]:
    """The active drawing's file and its (size, time); ('', None) when it was never saved."""
    status = await lc.recheck()
    path = str((status.get("active_drawing") or {}).get("path") or "")
    return path, (lc.file_stamp(Path(path)) if path else None)


def _where_saved(path: str) -> str:
    return f"the file {Path(path).name} kept its size and time" if path else "the scratch drawing is still unsaved"


def _own_folder(ctx: Context) -> Path:
    """The runner's own folder in %TEMP% (made once, removed at the end of the run)."""
    if ctx.folder is None:
        import tempfile

        ctx.folder = Path(tempfile.mkdtemp(prefix="heron-live-check-"))
    return ctx.folder


def _results(out: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """A check list run's lines by catalogue check (nothing_on_layer_0 ...)."""
    return {r["check"]: r for r in out.get("results") or []}


# ---------------------------------------------------------------------------
# Group M - ideas from Heron AI for Revit, batch 1
# ---------------------------------------------------------------------------


async def m3_a_save_typed_as_a_command_or_lisp_is_refused(ctx: Context) -> str:
    before = await _drawing_file()
    sent = refusal(await advanced.autocad_send_command(command="_QSAVE\n"))
    lisp = refusal(await advanced.autocad_run_lisp(expression='(command "_.QSAVE")'))
    for said, how in ((sent, "the command"), (lisp, "the AutoLISP")):
        expect("autocad_save_drawing" in said, f"{how} was refused without pointing at autocad_save_drawing: {said[:140]}")
        expect("Nothing was sent" in said, f"{how}'s refusal does not say nothing was sent: {said[:140]}")
    after = await _drawing_file()
    expect(after == before, f"the drawing's file changed: {before} -> {after}")
    return f"QSAVE as a command and in AutoLISP were both refused at once, naming autocad_save_drawing; {_where_saved(before[0])}"


async def m6_a_preview_still_comes_back_with_publish_off(ctx: Context) -> str:
    o = lc.origin("M6")
    await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 500), "layer": "LC-M6"})
    out = await document.autocad_preview(area="extents", width_px=400)
    expect(isinstance(out, list) and out, f"no picture came back: {str(body(out))[:160]}")
    data = getattr(out[0], "data", b"") or b""
    expect(data[:8] == b"\x89PNG\r\n\x1a\n", "the answer's picture is not a PNG")
    info = parse(out[1]) if len(out) > 1 else {}
    return f"a {len(data):,}-byte PNG came back with Publish off ({info.get('size') or 'size not said'}): the save veto left the preview alone"


# ---------------------------------------------------------------------------
# Group O - ideas from Heron AI for Revit, batch 3
# ---------------------------------------------------------------------------

NOTE_SAID = "the scale is 1:50 for this job"


async def o1_a_projects_note_comes_back_in_status(ctx: Context) -> str:
    path = await lc.save_scratch(ctx)
    parse(await project_notes.autocad_project_notes(action="keep", name="scale", value="1:50", said=NOTE_SAID))
    status = await lc.recheck()
    notes = (status.get("heron") or {}).get("project_notes") or {}
    expect(notes.get("scale") == "1:50", f"autocad_status gave project_notes {notes}, not scale 1:50")
    return (f"kept 'scale 1:50' for the folder of {path.name}; autocad_status handed it back as project_notes. "
            "This run is its own chat; a new Claude chat was not started")


async def o2_another_folder_does_not_see_the_note(ctx: Context) -> str:
    await lc.save_scratch(ctx)
    parse(await project_notes.autocad_project_notes(action="keep", name="scale", value="1:50", said=NOTE_SAID))
    try:
        other = await lc.other_drawing(ctx, "elsewhere", "o2.dwg")
        status = await lc.recheck()
        notes = (status.get("heron") or {}).get("project_notes")
        expect(not notes, f"a drawing in another folder got the first folder's notes: {notes}")
    finally:
        await lc.activate(ctx)
        await project_notes.autocad_project_notes(action="forget", name="scale")
    return f"{other.name}, saved in another folder, got no project_notes; the scale note was forgotten again afterwards"


async def o3_a_check_list_names_the_objects_it_failed(ctx: Context) -> str:
    o = lc.origin("O3")
    await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "0"})
    out = parse(await checklists.autocad_checklist(action="run", name=BEFORE_ISSUE))
    states = {r["state"] for r in out.get("results") or []}
    expect(states and states <= {"PASS", "FAIL", "NO DATA", "NOT RUN"}, f"the lines say {sorted(states)}")
    failing = [r for r in out["results"] if r["state"] == "FAIL"]
    expect(all(r.get("handles") or r.get("names") for r in failing), "a FAIL line names no objects")
    layer0 = _results(out).get("nothing_on_layer_0")
    expect(layer0, "the 'before issue' list on this PC has no nothing_on_layer_0 line, so this row cannot be judged")
    expect(layer0["state"] == "FAIL" and layer0.get("handles"),
           f"nothing_on_layer_0 is {layer0['state']} with handles {layer0.get('handles')}, though a line is on layer 0")
    named = list(layer0["handles"][:5])
    shown = parse(await document.autocad_show(handles=named))
    expect(shown.get("shown") == len(named) and not shown.get("not_found"), f"autocad_show answered {shown}")
    for handle in named:
        info = parse(await query.autocad_get_entity(handle=handle))
        expect(info.get("layer") == "0", f"{handle}, named as on layer 0, is on {info.get('layer')}")
    return (f"{len(out['results'])} lines, each PASS / FAIL / NO DATA / NOT RUN ({out.get('coverage')}); every FAIL "
            f"names its objects; the {len(named)} named for layer 0 are on layer 0 and autocad_show found them all. "
            "Whether they show selected on screen was not looked at")


LIST_O4 = "lc-o4 own sentences"


async def o4_your_own_sentences_come_back_as_the_labels(ctx: Context) -> str:
    o = lc.origin("O4")
    (frame,) = await _draw({"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 420, 297), "layer": "LC-O4"})
    parse(await blocks.autocad_make_block(
        name="LC-O4-TITLE", handles=[frame], base_point=_at(o, 0, 0), keep_originals=True,
        attributes=[{"tag": "DRAWN", "default": "", "position": _at(o, 300, 20), "height": 2.5},
                    {"tag": "SHEET", "default": "", "position": _at(o, 300, 10), "height": 2.5}],
    ))
    insert = parse(await draw.autocad_insert_block(block_name="LC-O4-TITLE", position=_at(o, 1000, 0),
                                                   attributes={"DRAWN": "AJ"}))["handle"]
    title, heights = "Every LC-O4 title block filled in", "Text 2.5, 3.5 or 5 only"
    parse(await checklists.autocad_checklist(action="save", name=LIST_O4, checks=[
        {"id": "title_blocks", "check": "title_block_filled", "params": {"block": "LC-O4-TITLE*"}, "label": title},
        {"id": "heights", "check": "text_heights", "params": {"heights": [2.5, 3.5, 5]}, "label": heights},
    ]))
    try:
        out = parse(await checklists.autocad_checklist(action="run", name=LIST_O4))
    finally:
        await checklists.autocad_checklist(action="delete", name=LIST_O4)
    by_id = {r["id"]: r for r in out.get("results") or []}
    expect(by_id.get("title_blocks", {}).get("label") == title and by_id.get("heights", {}).get("label") == heights,
           f"the labels came back as {[r.get('label') for r in by_id.values()]}")
    line = by_id["title_blocks"]
    expect(line["state"] == "FAIL" and insert in (line.get("handles") or []),
           f"the title block with SHEET empty is {line['state']}, naming {line.get('handles')}")
    return (f"both sentences came back as the labels; the title block {insert} with SHEET left empty is FAIL and "
            "named. The list was deleted again")


async def o5_undo_last_takes_back_heron_s_circle(ctx: Context) -> str:
    o = lc.origin("O5")
    before = await lc.entity_count()
    made = parse(await draw.autocad_draw_circle(center=_at(o, 0, 0), radius=100, layer="LC-O5"))
    out = parse(await activity.autocad_undo_last())
    expect(made["handle"] in (out.get("removed") or []), f"undo_last removed {out.get('removed')}, not the circle")
    expect(not await lc.exists(made["handle"]), "the circle is still in the drawing")
    after = await lc.entity_count()
    expect(after == before, f"the drawing has {after} objects, not the {before} it had before the circle")
    return f"the circle {made['handle']} is gone and the drawing is back to {before} objects"


async def o6_undo_last_refuses_after_the_modeller_drew(ctx: Context) -> str:
    o = lc.origin("O6")
    made = parse(await draw.autocad_draw_circle(center=_at(o, 0, 0), radius=100, layer="LC-O6"))
    mine = await lc.by_hand_line(_at(o, 200, 0), _at(o, 1200, 0))
    said = refusal(await activity.autocad_undo_last())
    expect("changed after Heron's last change" in said, f"undo_last was refused for another reason: {said[:140]}")
    expect(await lc.exists(made["handle"]) and await lc.exists(mine), "something was undone although it was refused")
    return "refused: 'the drawing changed after Heron's last change'; Heron's circle and the hand-drawn line both stay"


# ---------------------------------------------------------------------------
# Group P - ideas from Heron AI for Revit, batch 4
# ---------------------------------------------------------------------------

PLINTH = "lc-p1 plinth"


async def p1_a_saved_plinth_comes_out_at_the_new_size(ctx: Context) -> str:
    o = lc.origin("P1")
    first = parse(await solids.autocad_add_solid(shape="box", base=_at(o, 0, 0, 0), length=1200, width=600,
                                                 height=150, layer="LC-P1"))
    parse(await saved_commands.autocad_saved_command(
        action="save", name=PLINTH, description="LC P1 plinth",
        steps=[{"tool": "autocad_add_solid", "args": {"shape": "box", "base": _at(o, 3000, 0, 0), "length": "{{width}}",
                                                      "width": "{{depth}}", "height": 150, "layer": "LC-P1"}}],
        inputs={"width": {"description": "plinth width", "example": 1200},
                "depth": {"description": "plinth depth", "example": 600}},
    ))
    try:
        out = parse(await saved_commands.autocad_saved_command(action="run", name=PLINTH,
                                                                inputs={"width": 1500, "depth": 900}))
    finally:
        await saved_commands.autocad_saved_command(action="delete", name=PLINTH)
    expect(out.get("ran") == 1 and not out.get("failed"), f"the saved command ran {out.get('ran')}, failed {out.get('failed')}")
    result = out["steps"][0].get("result") or {}
    expect(isinstance(result, dict) and result.get("handle"), f"the step gave no handle: {str(result)[:120]}")
    again = parse(await query.autocad_get_entity(handle=result["handle"]))
    was = parse(await query.autocad_get_entity(handle=first["handle"]))
    size = again["size"]
    expect(near(size["width"], 1500, 1e-6) and near(size["height"], 900, 1e-6),
           f"the second plinth is {size['width']} x {size['height']}, not 1500 x 900")
    expect(again["layer"] == was["layer"] == "LC-P1" and again["type"] == was["type"],
           f"the second plinth is a {again['type']} on {again['layer']}, the first a {was['type']} on {was['layer']}")
    return ("'plinth' with inputs width and depth, run at 1500 by 900, made the same box 1500 x 900 on LC-P1. "
            "Keep or Discard was not seen (the runner works with Ask to Keep off); the command was deleted again")


# ---------------------------------------------------------------------------
# Group T - how a change job answers and what it keeps
# ---------------------------------------------------------------------------


async def t2_each_answer_starts_with_its_plain_line(ctx: Context) -> str:
    o = lc.origin("T2")
    drew = lc.first_line(await draw.autocad_draw_line(start=_at(o, 0, 0), end=_at(o, 1000, 0), layer="LC-T2"))
    expect(drew == "DONE - 1 added, 0 changed, 0 erased.", f"the line's answer starts {drew!r}")
    found = lc.first_line(await text_tools.autocad_find_replace_text(find="LC-T2 NO SUCH WORD", replace="X"))
    expect(found.startswith("NOTHING CHANGED - "), f"a replace that found nothing starts {found!r}")
    layer = lc.first_line(await layers.autocad_create_layer(name="LC-T2-LAYER"))
    expect(layer.startswith("DONE - no drawing object") and "not counted" in layer, f"a new layer's answer starts {layer!r}")
    return ("DONE - 1 added, 0 changed, 0 erased.; NOTHING CHANGED for a word not there; DONE - no drawing object ... "
            "not counted for a layer. The Changes-off line was not tried: the runner works with Changes on")


async def t4_a_dry_run_leaves_the_drawing_as_it_was(ctx: Context) -> str:
    o = lc.origin("T4")
    before = await lc.entity_count()
    raw = await draw.autocad_draw_circle(center=_at(o, 0, 0), radius=100, layer="LC-T4", dry_run=True)
    expect(lc.first_line(raw).startswith("NOTHING CHANGED - a dry run"), f"the circle's dry run starts {lc.first_line(raw)!r}")
    handle = parse(raw).get("handle")
    expect(not (handle and await lc.exists(handle)), f"the dry-run circle {handle} is in the drawing")
    expect(await lc.entity_count() == before, "the dry-run circle changed the object count")
    (line,) = await _draw({"type": "line", "start": _at(o, 0, 500), "end": _at(o, 1000, 500), "layer": "LC-T4"})
    was = parse(await query.autocad_get_entity(handle=line))
    raw = await modify.autocad_modify_entity(handles=[line], layer="LC-T4-OTHER", color="red", dry_run=True)
    expect(lc.first_line(raw).startswith("NOTHING CHANGED - a dry run"), f"the modify dry run starts {lc.first_line(raw)!r}")
    now = parse(await query.autocad_get_entity(handle=line))
    expect((now["layer"], now.get("color")) == (was["layer"], was.get("color")),
           f"the line went from {was['layer']}/{was.get('color')} to {now['layer']}/{now.get('color')}")
    raw = await layers.autocad_create_layer(name="M-TEST", dry_run=True)
    expect(lc.first_line(raw).startswith("NOTHING CHANGED"), f"the layer dry run starts {lc.first_line(raw)!r}")
    names = [layer["name"] for layer in parse(await layers.autocad_list_layers()).get("layers") or []]
    expect("M-TEST" not in names, "the dry run left layer M-TEST in the drawing")
    return ("each dry run started NOTHING CHANGED - a dry run; no circle, the line kept its layer and colour, no "
            "layer M-TEST. The Ctrl+Z after it was not tried")


async def t5_a_plugin_dry_run_goes_back_and_a_save_is_refused(ctx: Context) -> str:
    o = lc.origin("T5")
    low, high = await _draw(
        {"type": "circle", "center": _at(o, 0, 0, 0), "radius": 300, "layer": "LC-T5"},
        {"type": "circle", "center": _at(o, 0, 0, 1000), "radius": 150, "layer": "LC-T5"},
    )
    current = await lc.variable("CLAYER")
    raw = await solid_edits.autocad_loft(sections=[low, high], layer="LC-T5", dry_run=True)
    expect(lc.first_line(raw).startswith("NOTHING CHANGED - a dry run"), f"the loft's dry run starts {lc.first_line(raw)!r}")
    made = parse(raw).get("handle")
    expect(made and not await lc.exists(made), f"the dry-run loft {made} is in the drawing")
    raw = await layers.autocad_set_current_layer(name="LC-T5-CURRENT", dry_run=True)
    expect(lc.first_line(raw).startswith("NOTHING CHANGED"), f"set_current_layer's dry run starts {lc.first_line(raw)!r}")
    expect(await lc.variable("CLAYER") == current, "the dry run changed the current layer")
    before = await _drawing_file()
    raw = await document.autocad_save_drawing(dry_run=True)
    expect(lc.first_line(raw).startswith("REFUSED - nothing was sent"), f"the save's dry run starts {lc.first_line(raw)!r}")
    expect(await _drawing_file() == before, "the drawing's file changed")
    return (f"the loft came and went (NOTHING CHANGED - a dry run); CLAYER stayed {current}; the save was REFUSED - "
            f"nothing was sent, and {_where_saved(before[0])}")


async def t6_each_change_says_before_and_after(ctx: Context) -> str:
    o = lc.origin("T6")
    parse(await layers.autocad_create_layer(name="M-DUCT"))
    one, two, note = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-T6"},
        {"type": "line", "start": _at(o, 0, 500), "end": _at(o, 1000, 500), "layer": "M-DUCT", "color": "red"},
        {"type": "text", "position": _at(o, 0, 1000), "text": "REV A", "height": 50, "layer": "LC-T6"},
    )
    out = parse(await modify.autocad_modify_entity(handles=[one, two], layer="M-DUCT", color="red"))
    rows = out.get("before_after") or []
    changed = {(r.get("handle"), r.get("property")) for r in rows}
    expect({(one, "layer"), (one, "color")} <= changed, f"before_after does not name both changes of {one}: {rows}")
    expect(two in (out.get("already") or []) and not any(r.get("handle") == two for r in rows),
           f"the line already on M-DUCT is not in 'already': {out.get('already')}")
    first = await layers.autocad_set_layer_state(name="M-*", on=False)
    second = await layers.autocad_set_layer_state(name="M-*", on=False)
    await layers.autocad_set_layer_state(name="M-*", on=True)
    expect(parse(first).get("before_after"), "turning M-* off listed nothing in before_after")
    expect(lc.first_line(second).startswith("NOTHING CHANGED"), f"the second call starts {lc.first_line(second)!r}")
    was = await lc.variable("DIMSCALE")
    target = 75 if near(was, 100, 1e-9) else 100
    var = parse(await document.autocad_set_variable(name="DIMSCALE", value=target))
    await document.autocad_set_variable(name="DIMSCALE", value=was)
    ba = var.get("before_after") or []
    expect(ba and near(ba[0].get("to"), target, 1e-9) and near(ba[0].get("from"), was, 1e-9),
           f"DIMSCALE's before_after is {ba}")
    rep = parse(await text_tools.autocad_find_replace_text(find="REV A", replace="REV B", layer="LC-T6"))
    expect(any(r.get("handle") == note and "REV A" in str(r.get("from")) and "REV B" in str(r.get("to"))
               for r in rep.get("before_after") or []), f"the replace's before_after is {rep.get('before_after')}")
    return (f"before_after named {one}'s layer and colour, {two} was in 'already'; the second M-* off said NOTHING "
            f"CHANGED; DIMSCALE {was} -> {target} (put back); REV A -> REV B on {note}. The Undo drop-down was not looked at")


# ---------------------------------------------------------------------------
# Group U - check lists for QA
# ---------------------------------------------------------------------------

LIST_U1 = "lc-u1 sheets"


async def u1_a_missing_title_block_is_no_data_never_pass(ctx: Context) -> str:
    other = await lc.other_drawing(ctx, "u1", "u1-sheet.dwg")
    parse(await checklists.autocad_checklist(action="save", name=LIST_U1, checks=[
        {"check": "title_block_filled", "params": {"block": "TITLE*"}}, {"check": "nothing_on_layer_0"},
    ]))
    try:
        out = parse(await checklists.autocad_checklist(action="run", name=LIST_U1))
    finally:
        await checklists.autocad_checklist(action="delete", name=LIST_U1)
    title = _results(out).get("title_block_filled") or {}
    expect(title.get("state") == "NO DATA" and "no block named TITLE*" in str(title.get("note")),
           f"the title block line is {title.get('state')} ({title.get('note')})")
    expect(out.get("verdict") == "NO DATA", f"the verdict is {out.get('verdict')}, not NO DATA")
    expect(out.get("coverage") == "1 of 2 decided, 1 no data, 0 not run", f"coverage says {out.get('coverage')!r}")
    return f"in {other.name} (saved, no title block): the title block line NO DATA, verdict NO DATA, '{out['coverage']}'"


async def u2_only_part_read_is_no_data_but_a_failure_is_fail(ctx: Context) -> str:
    await lc.other_drawing(ctx, "u2", "u2-big.dwg")
    o = lc.origin("U2")
    await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "0"},
                *({"type": "line", "start": _at(o, 0, 100 * i), "end": _at(o, 1000, 100 * i), "layer": "LC-U2"}
                  for i in range(1, 30)))
    out = parse(await checklists.autocad_checklist(action="run", name=BEFORE_ISSUE, max_entities=10))
    lines = _results(out)
    layer0 = lines.get("nothing_on_layer_0") or {}
    expect(layer0.get("state") == "FAIL", f"nothing_on_layer_0 is {layer0.get('state')}, though object 1 is on layer 0")
    clean = [lines[k] for k in ("nothing_on_defpoints", "bylayer_colour") if k in lines]
    expect(clean, "the 'before issue' list on this PC has neither nothing_on_defpoints nor bylayer_colour")
    for line in clean:
        expect(line["state"] == "NO DATA" and "only the first 10 objects were read" in str(line.get("note")),
               f"{line['check']} is {line['state']} ({line.get('note')}), not NO DATA for a part read")
    return (f"30 objects, max_entities 10: nothing_on_layer_0 FAIL; {', '.join(c['check'] for c in clean)} NO DATA "
            "('only the first 10 objects were read'), never PASS")


U3_CHANGES = [{"id": "bylayer_colour", "severity": "high"}, {"id": "xrefs_found", "on": False}]


async def u3_a_projects_changes_show_in_the_run(ctx: Context) -> str:
    await lc.save_scratch(ctx)
    office = parse(await checklists.autocad_checklist(action="list", name=BEFORE_ISSUE))
    parse(await checklists.autocad_checklist(action="project", name=BEFORE_ISSUE, changes=U3_CHANGES))
    try:
        out = parse(await checklists.autocad_checklist(action="run", name=BEFORE_ISSUE))
    finally:
        await checklists.autocad_checklist(action="project", name=BEFORE_ISSUE, changes=[])
    by_id = {r["id"]: r for r in out.get("results") or []}
    colour, xrefs = by_id.get("bylayer_colour", {}), by_id.get("xrefs_found", {})
    expect(colour.get("severity") == "high" and colour.get("from") == "project",
           f"bylayer_colour is {colour.get('severity')} from {colour.get('from')}")
    expect(xrefs.get("state") == "NOT RUN", f"xrefs_found is {xrefs.get('state')}, not NOT RUN")
    used = out.get("checks_used") or []
    expect(len(used) == len(office.get("checks") or []) and all(u.get("from") in ("office", "project") for u in used),
           f"checks_used names {len(used)} checks with {[u.get('from') for u in used]}")
    expect(str(out.get("coverage", "")).endswith("1 not run"), f"coverage says {out.get('coverage')!r}")
    return (f"bylayer_colour high from project, xrefs_found NOT RUN, checks_used names all {len(used)} with office / "
            f"project, '{out['coverage']}'. The project's changes were taken off again")


async def u4_another_folder_gets_the_office_list(ctx: Context) -> str:
    await lc.save_scratch(ctx)
    parse(await checklists.autocad_checklist(action="project", name=BEFORE_ISSUE, changes=U3_CHANGES))
    try:
        await lc.other_drawing(ctx, "u4", "u4-elsewhere.dwg")
        out = parse(await checklists.autocad_checklist(action="run", name=BEFORE_ISSUE))
    finally:
        await lc.activate(ctx)
        await checklists.autocad_checklist(action="project", name=BEFORE_ISSUE, changes=[])
    froms = {r.get("from") for r in out.get("results") or []}
    expect(froms == {"office"}, f"in another folder the lines come from {sorted(map(str, froms))}")
    states = {r["id"]: r["state"] for r in out["results"]}
    expect(states.get("xrefs_found") != "NOT RUN", "xrefs_found is switched off in a folder that never changed it")
    return f"in another folder every one of the {len(states)} lines is from: office; the first folder's changes did not reach it"


async def u5_a_project_cannot_add_or_reword_a_check(ctx: Context) -> str:
    await lc.save_scratch(ctx)
    added = refusal(await checklists.autocad_checklist(action="project", name=BEFORE_ISSUE,
                                                       changes=[{"id": "my_new_check", "on": True}]))
    reworded = refusal(await checklists.autocad_checklist(action="project", name=BEFORE_ISSUE,
                                                          changes=[{"id": "nothing_on_layer_0", "label": "x"}]))
    expect("cannot add one" in added, f"adding a check was refused for another reason: {added[:140]}")
    expect("may only change severity, target, on" in reworded, f"a new label was refused for another reason: {reworded[:140]}")
    kept = parse(await checklists.autocad_checklist(action="project", name=BEFORE_ISSUE))
    expect(not kept.get("changes"), f"something was kept: {kept.get('changes')}")
    return "both refused in plain words ('cannot add one'; 'may only change severity, target, on'); nothing was kept"


async def u6_with_publish_off_no_report_is_written(ctx: Context) -> str:
    path = await lc.save_scratch(ctx)
    before = lc.files_in(path.parent, "*checklist*")
    said = refusal(await checklists.autocad_checklist_report(name=BEFORE_ISSUE))
    expect("publish" in said.lower(), f"the report was refused, but not naming Publish: {said[:140]}")
    after = lc.files_in(path.parent, "*checklist*")
    expect(after == before, f"files appeared next to the drawing: {sorted(set(after) - set(before))}")
    return "the report was refused naming the Publish padlock; no file was written next to the drawing"


async def u7_two_reports_make_two_pairs(ctx: Context) -> str:
    await lc.save_scratch(ctx)
    first = parse(await checklists.autocad_checklist_report(name=BEFORE_ISSUE))["saved"]
    stamps = {k: lc.file_stamp(Path(v)) for k, v in first.items()}
    second = parse(await checklists.autocad_checklist_report(name=BEFORE_ISSUE))["saved"]
    for kind in ("xlsx", "html"):
        a, b = Path(first[kind]), Path(second[kind])
        expect(" - checklist before-issue - " in a.name and a.suffix == f".{kind}", f"the first {kind} is named {a.name}")
        expect(b.stem == f"{a.stem} (2)", f"the second {kind} is named {b.name}, not '{a.stem} (2).{kind}'")
        expect(lc.file_stamp(b) is not None, f"{b.name} is not there")
        expect(lc.file_stamp(a) == stamps[kind] and stamps[kind] is not None, f"{a.name} changed when the second was written")
    return f"two pairs next to the drawing: {Path(first['xlsx']).stem} and the same with ' (2)'; the first pair unchanged"


async def u10_a_passing_standard_says_what_pass_means(ctx: Context) -> str:
    out = parse(await standards.autocad_check_standards(rules={"layers": {"0": {}}}))
    expect(out.get("passed") is True, f"a drawing that has layer 0 did not pass: {out.get('summary')}")
    expect(out.get("source") and out.get("pass_means"), f"the answer has source {out.get('source')!r}, pass_means {out.get('pass_means')!r}")
    return f"passed: true, with source and pass_means ('{str(out['pass_means'])[:70]}...'). What the chat says was not looked at"


# ---------------------------------------------------------------------------
# Group W - finding and explaining
# ---------------------------------------------------------------------------


async def w2_why_names_publish_and_gaps_counts_the_refusal(ctx: Context) -> str:
    why = parse(await explain.autocad_why(job="save this as PDF"))
    tool = why.get("tool") or {}
    expect("Publish" in (tool.get("needs") or []), f"autocad_why picked {tool.get('tool')}, needing {tool.get('needs')}")
    reasons = {r["reason"]: r for r in why.get("reasons") or []}
    publish = reasons.get("publish_off") or reasons.get("needs_publish")
    expect(publish and "HERONPUBLISH" in publish.get("what_to_do", ""), f"autocad_why gave {list(reasons)}")
    expect("changes_off" not in reasons, "autocad_why says Changes is off, but it is on")
    pdf = _own_folder(ctx) / "lc-w2.pdf"
    said = refusal(await document.autocad_export(path=str(pdf)))
    expect("publish" in said.lower(), f"the PDF was refused, but not naming Publish: {said[:140]}")
    expect(lc.file_stamp(pdf) is None, "a PDF was written")
    gaps = parse(await explain.autocad_gaps(days=1))
    expect(any(f.get("says") == "The Publish padlock was off." for f in gaps.get("failures") or []),
           f"autocad_gaps does not list 'The Publish padlock was off.': {[f.get('says') for f in gaps.get('failures') or []]}")
    how = "it is off in this AutoCAD" if "publish_off" in reasons else "it cannot see whether it is on"
    return (f"autocad_why picked {tool.get('tool')} needing {' and '.join(tool['needs'])} and said {how} (HERONPUBLISH); "
            "the PDF was refused naming Publish, no file; autocad_gaps(days=1) lists 'The Publish padlock was off.'")


async def w3_why_says_a_flange_should_run(ctx: Context) -> str:
    why = parse(await explain.autocad_why(job="draw a 200 flange with 8 bolt holes"))
    tool = (why.get("tool") or {}).get("tool")
    expect(why.get("can_run") is True, f"can_run is {why.get('can_run')}: {why.get('verdict')}")
    expect(tool == "autocad_make_shape", f"it picked {tool}, not autocad_make_shape")
    expect("should run" in str(why.get("verdict")), f"the verdict is {why.get('verdict')!r}")
    return f"can_run true, tool autocad_make_shape: {why['verdict']}"


async def w4_why_says_there_is_no_tool_for_tea(ctx: Context) -> str:
    why = parse(await explain.autocad_why(job="make me a cup of tea"))
    none = [r for r in why.get("reasons") or [] if "no tool" in str(r.get("says")).lower()]
    expect(none and "by hand" in str(none[0].get("what_to_do")).lower(), f"autocad_why answered {why.get('verdict')!r}")
    expect(why.get("can_run") is False or none[0]["reason"] == "no_sure_tool", f"can_run is {why.get('can_run')}")
    return f"'{none[0]['says']}' with '{str(none[0]['what_to_do'])[:60]}...'"


FIND_ROWS = {
    "W7": (("is that polyline closed", "autocad_polyline_info"), ("how many diffusers on this floor", "autocad_count_blocks")),
}


async def _find(phrase: str) -> dict[str, Any]:
    return json.loads(await resources.find_tool(phrase=phrase))


def _only_reads(matches: list[dict[str, Any]]) -> bool:
    return all(str(m.get("needs", "")).startswith("none") for m in matches)


async def w7_a_question_finds_a_read_tool_first(ctx: Context) -> str:
    said = []
    for phrase, wanted in FIND_ROWS["W7"]:
        out = await _find(phrase)
        matches = out.get("matches") or []
        expect(matches and matches[0]["tool"] == wanted,
               f"'{phrase}': the first match is {matches[0]['tool'] if matches else 'nothing'}, not {wanted}")
        expect(_only_reads(matches), f"'{phrase}': a tool that changes the drawing is in matches")
        said.append(f"'{phrase}' -> {wanted}")
    return "; ".join(said) + "; only tools that read in matches (read through Heron's own finder, as the resource serves it)"


async def w8_a_clash_question_keeps_the_checker_apart(ctx: Context) -> str:
    out = await _find("is there a clash between the duct and the steel")
    matches = out.get("matches") or []
    expect(_only_reads(matches), f"matches holds a tool that changes the drawing: {[m['tool'] for m in matches]}")
    apart = [m["tool"] for m in out.get("would_change_the_drawing") or []]
    expect("autocad_check_interference" in apart, f"autocad_check_interference is not under would_change_the_drawing: {apart}")
    return f"matches only read ({', '.join(m['tool'] for m in matches[:3])}); autocad_check_interference is under would_change_the_drawing"


# ---------------------------------------------------------------------------
# Group Z - undo commands, long AutoLISP, quiet answers, busy answers
# ---------------------------------------------------------------------------


def _defun(name: str, body_forms: int = 19, *, broken: bool = False) -> str:
    """A defun of about 600 characters once compacted, with comments and line breaks."""
    steps = "\n".join(f"  (setq {name}v (+ {name}v {i})) ; step {i}" for i in range(body_forms))
    form = f"(defun {name} ()\n  ; a long function for the live check\n  (setq {name}v 0)\n{steps}\n  {name}v)"
    return f"(progn (lcz-no-such-function) {form})" if broken else form


def z2_text() -> str:
    return "\n\n".join(_defun(f"lcz2f{i}") for i in range(6)) + "\n(lcz2f5)"


def z3_text() -> str:
    return "\n\n".join(_defun(f"lcz3f{i}", broken=(i == 2)) for i in range(6)) + "\n(lcz3f5)"


async def _types(prefix: str) -> list[str]:
    names = " ".join(f"{prefix}{i}" for i in range(6))
    out = parse(await advanced.autocad_run_lisp(expression=f"(mapcar 'type (list {names}))"))
    return str(out.get("result", "")).strip("()").split()


async def _forget(prefix: str) -> None:
    names = " ".join(f"{prefix}{i} nil" for i in range(6))
    parse(await advanced.autocad_run_lisp(expression=f"(setq {names})"))


async def z2_long_lisp_runs_in_six_pieces(ctx: Context) -> str:
    await _forget("lcz2f")
    out = parse(await advanced.autocad_run_lisp(expression=z2_text()))
    expect(out.get("chunks") == 6 and out.get("chunks_finished") == 6,
           f"chunks {out.get('chunks')}, finished {out.get('chunks_finished')}, not 6 and 6")
    expect(out.get("timed_out") is False and str(out.get("result")) == str(sum(range(19))),
           f"the last form gave {out.get('result')!r} (timed_out {out.get('timed_out')})")
    kinds = await _types("lcz2f")
    expect(kinds == ["USUBR"] * 6, f"(type lcz2f0..5) gives {kinds}")
    return (f"{len(z2_text()):,} characters in 6 pieces, all 6 finished, the last form's value {out['result']}, "
            "every function a USUBR. The command history was not looked at")


async def z3_a_mistake_in_piece_3_stops_the_rest(ctx: Context) -> str:
    await _forget("lcz3f")
    out = parse(await advanced.autocad_run_lisp(expression=z3_text()))
    note = str(out.get("note", ""))
    expect(out.get("timed_out") is True, f"timed_out is {out.get('timed_out')}")
    expect("piece 3 of 6" in note and "3 more were not sent" in note, f"the note says {note[-160:]!r}")
    kinds = await _types("lcz3f")
    expect(kinds[:2] == ["USUBR", "USUBR"] and all(k == "nil" for k in kinds[3:]),
           f"(type lcz3f0..5) gives {kinds}: f0 and f1 should exist, f3 to f5 not")
    return "stopped at piece 3 ('piece 3 of 6 ... 3 more were not sent'); f0 and f1 exist, f3 to f5 do not. The Ctrl+Z was not tried"


Z4_PAD = "x" * 400


def z4_text() -> str:
    return (f'(progn (setq lcz4pad "{Z4_PAD}") (command "_LINE" "0,0"))\n'
            f'(progn (setq lcz4pad "{Z4_PAD}") (command "100,0" ""))')


async def z4_an_open_command_is_named_and_the_rest_not_sent(ctx: Context) -> str:
    before = await lc.entity_count()
    out = parse(await advanced.autocad_run_lisp(expression=z4_text()))
    expect(out.get("chunks") == 2, f"the code went in {out.get('chunks')} pieces, not 2")
    expect("LINE" in str(out.get("cancelled_command", "")).upper(), f"cancelled_command is {out.get('cancelled_command')!r}")
    expect(out.get("chunks_finished") == 1, f"{out.get('chunks_finished')} pieces finished, not 1 (the second must not be sent)")
    expect(int(await lc.variable("CMDACTIVE") or 0) == 0, "AutoCAD is not back at Command:")
    expect(await lc.entity_count() == before, "a line was drawn")
    return f"piece 1 left {out['cancelled_command']} open and it was named; piece 2 was not sent; AutoCAD is at Command:, no line"


def z5_steps(o: tuple[float, float], y0: float) -> list[dict[str, Any]]:
    return [{"tool": "autocad_dimension_run", "args": {
        "points": [_at(o, 1000 * i, y0 + 1000 * row) for i in range(5)], "offset": 300, "include_overall": True,
        "layer": "LC-Z5"}} for row in range(8)]


async def z5_a_quiet_sequence_gives_counts_and_handles(ctx: Context) -> str:
    o = lc.origin("Z5")
    loud_raw = await sequence.autocad_sequence(steps=z5_steps(o, 0))
    quiet_raw = await sequence.autocad_sequence(steps=z5_steps(o, 20000), quiet=True)
    loud, quiet = parse(loud_raw), parse(quiet_raw)
    expect(loud.get("ran") == quiet.get("ran") == 8, f"ran {loud.get('ran')} and {quiet.get('ran')}, not 8 and 8")
    for a, b in zip(loud["steps"], quiet["steps"], strict=True):
        got = b.get("result") or {}
        expect(got.get("count") == 5 and len(got.get("handles") or []) == 5, f"a quiet step answered {str(got)[:120]}")
        expect((got.get("left_out") or {}).get("dimensions") == 5 and "dimensions" not in got,
               f"a quiet step still holds the points: {str(got)[:120]}")
        expect((a.get("result") or {}).get("count") == got.get("count"), "the two runs made different counts")
    sizes = len(body(loud_raw)), len(body(quiet_raw))
    expect(sizes[1] * 2 < sizes[0], f"the quiet answer is {sizes[1]:,} characters against {sizes[0]:,}: not under half")
    return f"8 steps both times, 5 dimensions each; quiet kept count, handles and left_out dimensions 5; {sizes[1]:,} characters against {sizes[0]:,}"


async def z8_a_long_delay_says_how_it_ended(ctx: Context) -> str:
    raw = await advanced.autocad_run_lisp(expression='(command "_.DELAY" 15000)')
    head, out = lc.first_line(raw), parse(raw)
    if out.get("timed_out"):
        expect(head.startswith("OUTCOME UNKNOWN"), f"it timed out but the first line is {head!r}")
        which = "timed out, and the first line is OUTCOME UNKNOWN"
    else:
        expect(head.startswith("DONE"), f"the value came back but the first line is {head!r}")
        which = "the value came back, and the first line is DONE"
    expect(int(await lc.variable("CMDACTIVE") or 0) == 0, "AutoCAD was left inside DELAY")
    return f"AutoCAD 2027 gave: {which} ({head[:90]})"


# ---------------------------------------------------------------------------
# Group AG - standards against a reference drawing
# ---------------------------------------------------------------------------


async def _against_a_reference(ctx: Context, row: str, keep_open: bool) -> tuple[Path, dict[str, Any]]:
    """An office drawing the runner makes (a red wall layer, an Arial and a romans.shx style), and the
    scratch drawing made to differ (the wall blue, the note style in simplex.shx), checked against it."""
    tag = f"LC-{row}"
    office = await lc.other_drawing(ctx, f"{row.lower()}-office", "office.dwg")
    parse(await layers.autocad_create_layer(name=f"{tag}-WALL", color="red"))
    parse(await settings.autocad_create_styles(text_styles=[
        {"name": f"{tag}-ARIAL", "font": "Arial"}, {"name": f"{tag}-NOTE", "font": "romans.shx"}]))
    await lc.save_active(ctx)
    if not keep_open:
        await lc.close_drawing(ctx, office.name)
    await lc.activate(ctx)
    parse(await layers.autocad_create_layer(name=f"{tag}-WALL", color="blue"))
    parse(await settings.autocad_create_styles(text_styles=[
        {"name": f"{tag}-ARIAL", "font": "Arial"}, {"name": f"{tag}-NOTE", "font": "simplex.shx"}], replace=True))
    out = parse(await standards.autocad_check_standards(reference=str(office)))
    return office, out


def _finding(out: dict[str, Any], rule: str, name: str) -> dict[str, Any] | None:
    return next((f for f in out.get("findings") or [] if f.get("rule") == rule and str(f.get("name")).upper() == name), None)


async def ag5_a_reference_drawing_names_what_really_differs(ctx: Context) -> str:
    office, out = await _against_a_reference(ctx, "AG5", keep_open=False)
    read_by = str((out.get("reference") or {}).get("read_by"))
    wall = _finding(out, "layer_differs_from_standard", "LC-AG5-WALL")
    expect(wall and "colour" in str(wall.get("detail")).lower(), f"the blue wall layer was not named as differing: {wall}")
    note = _finding(out, "text_style_differs_from_standard", "LC-AG5-NOTE")
    expect(note and "font" in str(note.get("detail")).lower(), f"the note style's font was not named: {note}")
    expect(office.name not in await lc.drawing_names(), "the reference drawing was opened on screen")
    return (f"read by: {read_by}; the wall layer named for its colour and LC-AG5-NOTE for its font; the reference "
            "did not open on screen. AutoCAD's CHECKSTANDARDS was not compared, and the reference was a .dwg the "
            "runner made, not the office .dws")


async def ag6_a_reference_open_in_autocad_is_read_there(ctx: Context) -> str:
    _, out = await _against_a_reference(ctx, "AG6", keep_open=True)
    read_by = str((out.get("reference") or {}).get("read_by"))
    expect("open there" in read_by, f"read_by says {read_by!r}, not that the drawing is open there")
    expect(_finding(out, "layer_differs_from_standard", "LC-AG6-WALL"), "the same wall layer finding as AG5 is missing")
    return f"read by: {read_by}; the same wall layer finding as AG5"


async def ag8_a_truetype_pair_is_quiet_an_shx_pair_is_said(ctx: Context) -> str:
    _, out = await _against_a_reference(ctx, "AG8", keep_open=False)
    arial = [f for f in out.get("findings") or [] if str(f.get("name")).upper() == "LC-AG8-ARIAL"]
    expect(not arial, f"Arial in both drawings was reported: {arial}")
    note = _finding(out, "text_style_differs_from_standard", "LC-AG8-NOTE")
    detail = str((note or {}).get("detail"))
    expect(note and "here" in detail and "in the standard" in detail, f"romans.shx against simplex.shx gave {note}")
    return f"Arial in both is not reported; the SHX pair is: '{detail[:90]}'"


# ---------------------------------------------------------------------------
# Group AJ - drawing events from the plug-in
# ---------------------------------------------------------------------------


async def aj3_a_drawing_closed_and_opened_again_is_checked_again(ctx: Context) -> str:
    path = await lc.other_drawing(ctx, "aj3", "a.dwg")
    await lc.close_drawing(ctx, path.name)
    await lc.open_drawing(ctx, path)
    o = lc.origin("AJ3")
    said = refusal(await draw.autocad_draw_line(start=_at(o, 0, 0), end=_at(o, 1000, 0), layer="LC-AJ3"))
    expect("was closed" in said and "opened again since Heron checked it" in said and "autocad_status" in said,
           f"the draw was refused for another reason: {said[:160]}")
    await lc.recheck()
    made = parse(await draw.autocad_draw_line(start=_at(o, 0, 0), end=_at(o, 1000, 0), layer="LC-AJ3"))
    expect(await lc.exists(made["handle"]), "after autocad_status the line is not in the drawing")
    return f"refused: '{said[:80]}...'; after autocad_status the line was drawn"


async def aj4_a_save_as_by_hand_is_followed(ctx: Context) -> str:
    await lc.new_drawing(ctx)
    folder = _own_folder(ctx) / "aj4"
    folder.mkdir(parents=True, exist_ok=True)
    now = await lc.save_as(ctx, folder / "plan.dwg")
    o = lc.origin("AJ4")
    made = parse(await draw.autocad_draw_line(start=_at(o, 0, 0), end=_at(o, 1000, 0), layer="LC-AJ4"))
    expect(await lc.exists(made["handle"]), "the line is not in the drawing")
    status = await lc.recheck()
    name = (status.get("active_drawing") or {}).get("name")
    expect(str(name).lower() == now.lower(), f"the line went into {name}, not {now}")
    return f"after a Save As to {now} by hand, the line was drawn there with no new status check. The older plug-in was not tried"


async def aj5b_the_old_file_opened_again_is_checked_again(ctx: Context) -> str:
    path = await lc.other_drawing(ctx, "aj5b", "a.dwg")
    await lc.save_as(ctx, path.with_name("a-rev2.dwg"))
    await lc.open_drawing(ctx, path)
    o = lc.origin("AJ5")
    said = refusal(await draw.autocad_draw_line(start=_at(o, 0, 5000), end=_at(o, 1000, 5000), layer="LC-AJ5B"))
    expect("a.dwg was opened" in said and "after Heron checked a drawing" in said, f"refused for another reason: {said[:160]}")
    await lc.recheck()
    made = parse(await draw.autocad_draw_line(start=_at(o, 0, 5000), end=_at(o, 1000, 5000), layer="LC-AJ5B"))
    expect(await lc.exists(made["handle"]), "after autocad_status the line is not in the drawing")
    return f"refused: '{said[:80]}...'; after autocad_status the line was drawn"


def _batch_ok(out: dict[str, Any], want: int, what: str) -> None:
    expect(out.get("created") == out.get("requested") == want, f"{what}: created {out.get('created')} of {out.get('requested')}, not {want}")
    expect(not out.get("missing") and out.get("completed") is True, f"{what}: missing {out.get('missing')}, completed {out.get('completed')}")


async def aj6_the_a22_batch_is_made_whole(ctx: Context) -> str:
    o = lc.origin("AJ6")
    ops = [{"type": "circle", "center": _at(o, 300 * (i % 10), 300 * (i // 10)), "radius": 100, "layer": "LC-AJ6"}
           for i in range(40)]
    ops.append({"type": "polyline", "points": [_at(o, 20 * i, 2000 + (i % 2) * 50) for i in range(150)], "layer": "LC-AJ6"})
    out = parse(await batch.autocad_batch_draw(operations=ops))
    _batch_ok(out, 41, "the 41-object batch")
    return f"all 41 made, nothing missing, completed, in {out.get('elapsed_seconds')} s. The Command: prompts in F2 were not counted"


async def aj7_big_batches_arrive_whole(ctx: Context) -> str:
    o = lc.origin("AJ7")
    lines = [{"type": "line", "start": _at(o, 0, 10 * i), "end": _at(o, 1000, 10 * i), "layer": "LC-AJ7"} for i in range(2000)]
    first = parse(await batch.autocad_batch_draw(operations=lines, return_handles=False))
    _batch_ok(first, 2000, "2,000 lines")
    mixed = [{"type": "polyline", "points": [_at(o, 2000 + 5 * i, (i % 2) * 40) for i in range(800)], "layer": "LC-AJ7"}]
    mixed += [{"type": "text", "position": _at(o, 2000, 200 + 100 * i), "text": f"LC-AJ7 TEXT {i}", "height": 50, "layer": "LC-AJ7"}
              for i in range(50)]
    second = parse(await batch.autocad_batch_draw(operations=mixed, return_handles=False))
    _batch_ok(second, 51, "the 800-vertex polyline and 50 texts")
    return "2,000 lines and then an 800-vertex polyline with 50 texts: every one made, nothing missing, both completed"


# ---------------------------------------------------------------------------
# Group RV - fixes from the review of the 2026-11-21 merges
# ---------------------------------------------------------------------------


async def rv3_a_sequence_cannot_switch_drawings(ctx: Context) -> str:
    before = await lc.entity_count()
    o = lc.origin("RV3")
    said = refusal(await sequence.autocad_sequence(steps=[
        {"tool": "autocad_switch_drawing", "args": {"name": str(ctx.scratch)}},
        {"tool": "autocad_draw_line", "args": {"start": _at(o, 0, 0), "end": _at(o, 1000, 0)}},
    ]))
    expect("Step 1" in said or "step 1" in said, f"the refusal does not name step 1: {said[:140]}")
    expect(await lc.entity_count() == before, "something was drawn")
    return f"refused naming step 1 ('{said[:80]}...'); nothing drawn"


CHECKS: tuple[Check, ...] = (
    Check("M3", "M", "a save typed as a command or AutoLISP is refused",
          m3_a_save_typed_as_a_command_or_lisp_is_refused, frozenset({"admin", "no_publish"})),
    Check("M6", "M", "a preview still comes back with Publish off",
          m6_a_preview_still_comes_back_with_publish_off, frozenset({"no_publish"})),
    Check("O1", "O", "a project's note comes back in status", o1_a_projects_note_comes_back_in_status),
    Check("O2", "O", "another folder does not see the note", o2_another_folder_does_not_see_the_note),
    Check("O3", "O", "a check list names the objects it failed", o3_a_check_list_names_the_objects_it_failed),
    Check("O4", "O", "your own sentences come back as labels", o4_your_own_sentences_come_back_as_the_labels),
    Check("O5", "O", "undo last takes back Heron's circle", o5_undo_last_takes_back_heron_s_circle),
    Check("O6", "O", "undo last refuses after the modeller drew", o6_undo_last_refuses_after_the_modeller_drew),
    Check("P1", "P", "a saved plinth comes out at the new size", p1_a_saved_plinth_comes_out_at_the_new_size),
    Check("T2", "T", "each answer starts with its plain line", t2_each_answer_starts_with_its_plain_line),
    Check("T4", "T", "a dry run leaves the drawing as it was", t4_a_dry_run_leaves_the_drawing_as_it_was),
    Check("T5", "T", "a plug-in dry run goes back, a save is refused",
          t5_a_plugin_dry_run_goes_back_and_a_save_is_refused),
    Check("T6", "T", "each change says before and after", t6_each_change_says_before_and_after, frozenset({"admin"})),
    Check("U1", "U", "a missing title block is NO DATA, never PASS", u1_a_missing_title_block_is_no_data_never_pass),
    Check("U2", "U", "only part read is NO DATA, a failure is FAIL", u2_only_part_read_is_no_data_but_a_failure_is_fail),
    Check("U3", "U", "a project's changes show in the run", u3_a_projects_changes_show_in_the_run),
    Check("U4", "U", "another folder gets the office list", u4_another_folder_gets_the_office_list),
    Check("U5", "U", "a project cannot add or reword a check", u5_a_project_cannot_add_or_reword_a_check),
    Check("U6", "U", "with Publish off no report is written", u6_with_publish_off_no_report_is_written,
          frozenset({"no_publish"})),
    Check("U7", "U", "two reports make two pairs of files", u7_two_reports_make_two_pairs, frozenset({"publish"})),
    Check("U10", "U", "a passing standard says what PASS means", u10_a_passing_standard_says_what_pass_means),
    Check("W2", "W", "why names Publish and gaps counts the refusal",
          w2_why_names_publish_and_gaps_counts_the_refusal, frozenset({"no_publish"})),
    Check("W3", "W", "why says a flange should run", w3_why_says_a_flange_should_run),
    Check("W4", "W", "why says there is no tool for tea", w4_why_says_there_is_no_tool_for_tea),
    Check("W7", "W", "a question finds a read tool first", w7_a_question_finds_a_read_tool_first),
    Check("W8", "W", "a clash question keeps the checker apart", w8_a_clash_question_keeps_the_checker_apart),
    Check("Z2", "Z", "long AutoLISP runs in six pieces", z2_long_lisp_runs_in_six_pieces, frozenset({"admin"})),
    Check("Z3", "Z", "a mistake in piece 3 stops the rest", z3_a_mistake_in_piece_3_stops_the_rest, frozenset({"admin"})),
    Check("Z4", "Z", "an open command is named, the rest not sent",
          z4_an_open_command_is_named_and_the_rest_not_sent, frozenset({"admin"})),
    Check("Z5", "Z", "a quiet sequence gives counts and handles", z5_a_quiet_sequence_gives_counts_and_handles),
    Check("Z8", "Z", "a long DELAY says how it ended", z8_a_long_delay_says_how_it_ended, frozenset({"admin"})),
    Check("AG5", "AG", "a reference drawing names what differs", ag5_a_reference_drawing_names_what_really_differs),
    Check("AG6", "AG", "a reference open in AutoCAD is read there", ag6_a_reference_open_in_autocad_is_read_there),
    Check("AG8", "AG", "a TrueType pair is quiet, an SHX pair said", ag8_a_truetype_pair_is_quiet_an_shx_pair_is_said),
    Check("AJ3", "AJ", "a drawing closed and opened again is checked", aj3_a_drawing_closed_and_opened_again_is_checked_again),
    Check("AJ4", "AJ", "a Save As by hand is followed", aj4_a_save_as_by_hand_is_followed),
    Check("AJ5b", "AJ", "the old file opened again is checked", aj5b_the_old_file_opened_again_is_checked_again),
    Check("AJ6", "AJ", "the A22 batch is made whole", aj6_the_a22_batch_is_made_whole),
    Check("AJ7", "AJ", "big batches arrive whole", aj7_big_batches_arrive_whole),
    Check("RV3", "RV", "a sequence cannot switch drawings", rv3_a_sequence_cannot_switch_drawings),
)

_TWO_AUTOCADS = "needs a second AutoCAD open and connected to Heron"
_CLICK_ERASE = "Heron's 'erased' box needs your answer (D-50), which the runner cannot give"
_ASK_TO_KEEP = "needs Ask to Keep on and your Keep or Discard click; the runner works with it off"
_HERONSTOP = "needs HERONSTOP typed or Stop Heron now pressed while the job runs"
_PALETTE = "needs a button pressed in the Heron palette, and what it shows is read on screen"
_RESTART = "needs AutoCAD closed and started again, which the runner cannot do"
_REGISTRY = "needs the Windows policy key set in an administrator command prompt"
_REFUSED_FIRST = (
    "as written it cannot open its box: autocad_send_command refuses {cmd} before sending anything "
    "(it opens a modal dialog), so the row needs rewriting (issue {issue})"
)
DIALOG_ROWS_ISSUE = "#213"

BY_EYE: dict[str, str] = {
    "M1": "needs Changes off, and the grips and the zoom are seen on screen",
    "M2": "what stays visible is seen on screen, and the save and reopen is done by hand",
    "M4": "the AutoLISP must be typed by hand: Heron refuses to send QSAVE, and the 'Heron stopped QSAVE' line is read on screen",
    "M5": "Ctrl+S is pressed by hand right after M4",
    "M7": "whether Claude Code shows the progress notes is seen in the chat",
    "M8": "the first half needs AutoCAD closed, which the runner cannot do",
    "N1": _TWO_AUTOCADS,
    "N2": _TWO_AUTOCADS,
    "N3": _TWO_AUTOCADS + ", then closed by hand",
    "N4": _CLICK_ERASE,
    "N5": _CLICK_ERASE,
    "N6": _ASK_TO_KEEP,
    "N7": _HERONSTOP,
    "N8": _HERONSTOP,
    "O7": _ASK_TO_KEEP,
    "P2": "runs the installer with AutoCAD closed, outside AutoCAD",
    "P3": "runs Rollback.bat and restarts AutoCAD, outside the runner",
    "P4": "runs CheckForUpdate.bat against GitHub, outside AutoCAD",
    "P5": "pushes a release tag on GitHub, outside AutoCAD",
    "Q1": "needs drawing tabs switched by hand while it runs",
    "Q2": "needs a heavy realistic 3D drawing (Luxury Suite 3), which the scratch drawing is not",
    "Q3": "needs AutoCAD's Options dialog opened by hand and left open",
    "Q4": "follows Q2 in the heavy 3D drawing",
    "Q5": "runs the Luxury Suite 3 player, not the runner",
    "R1": _RESTART,
    "R2": "needs the config file edited with AutoCAD closed, then a restart",
    "R3": "needs the config file edited by hand while AutoCAD is open",
    "R4": _TWO_AUTOCADS,
    "R5": _REGISTRY,
    "R6": _REGISTRY,
    "R7": _REGISTRY,
    "R8": "asks Claude Code itself to write the file; the guard is in Claude Code, not the runner",
    "R9": "its second half needs the AllowAdmin policy key (R7) set by an administrator",
    "R10": _RESTART,
    "T1": "needs Claude Code quit and the same chat resumed with claude --resume",
    "T3": _ASK_TO_KEEP,
    "T7": "what the Undo drop-down shows is read on screen",
    "U8": "Excel opening the file without a repair message is seen in Excel and a browser",
    "U9": "how the chat words its answer is read in the chat",
    "V1": _REFUSED_FIRST.format(cmd="OPEN", issue=DIALOG_ROWS_ISSUE),
    "V2": "needs AutoCAD's Options dialog opened by hand and left open",
    "V3": _ASK_TO_KEEP,
    "V4": _REFUSED_FIRST.format(cmd="CLOSE", issue=DIALOG_ROWS_ISSUE),
    "V5": "the dialog is opened by hand with no Heron job running",
    "V6": "reads the log of V1, which cannot run as written (issue " + DIALOG_ROWS_ISSUE + ")",
    "V7": _REFUSED_FIRST.format(cmd="PURGE", issue=DIALOG_ROWS_ISSUE),
    "V8": "needs a plug-in older than 1.7.0 installed",
    "W1": "needs AutoCAD closed, which the runner cannot do",
    "W5": "needs Changes off; the runner works with Changes on",
    "W6": "needs a week of real work in the audit log, judged by you",
    **{f"X{n}": _PALETTE for n in range(1, 25) if n != 21},
    "X21": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
    "Z1": "needs AutoCAD kept busy by hand (a heavy regen or a tab switch) while it runs",
    "Z6": "needs HATCH started by hand and left at its prompt",
    "Z7": "needs a dialog opened by hand and left open",
    "Z9": "needs a plug-in built before this change installed",
    "Z10": _ASK_TO_KEEP,
    "AG1": "needs AutoCAD closed, which the runner cannot do",
    "AG2": "needs AutoCAD closed and the ODA File Converter not installed",
    "AG3": "needs the ODA File Converter installed by hand, and AutoCAD closed",
    "AG4": "needs AutoCAD closed and a drawing with real dynamic blocks",
    "AG7": "needs a .dxf saved from the office .dws, and that layer's true colour is judged",
    "AG9": "needs a real network share and a second PC",
    "AG10": "needs the network drive disconnected by hand",
    "AG11": "needs a second PC sharing the same list",
    "AG12": "needs a share where this user has read-only rights",
    "AG13": "needs a second PC in the same job folder",
    "AG14": "would point this PC's office check-list folder somewhere; the runner does not change that setting",
    "AG15": "needs AutoCAD closed, which the runner cannot do",
    "AJ1": "what the Heron palette's Activity tab shows is read on screen",
    "AJ2": "needs two minutes untouched with SAVETIME 1, and the palette is read on screen",
    "AJ5": _RESTART,
    "AJ8": "needs Ctrl+Tab pressed by hand while the sequence runs",
    "AJ9": _PALETTE,
    "AJ10": "needs a plug-in built before this change, or the server started with --no-bridge",
    "RV1": "needs the chat closed mid-command and a box opened by hand with no job running",
    "RV2": "needs the values typed in Excel, which converts them; Heron's own writer writes text only",
}
