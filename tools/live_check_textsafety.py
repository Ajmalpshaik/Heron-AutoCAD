"""Live checks for text and names that hold control characters, and run_lisp's answers (groups AW, BA, BF).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Measured: a LISP error answered at once with AutoCAD's own words, a long call cut
in pieces, complete ``(command ...)`` calls, a form at and over the size limit, a
real line break inside a LISP string, text with Esc / tab / newline / quotes /
Malayalam / Arabic drawn as sent, a NUL and a U+0085 refused, and names with a
control character refused. Left to a person: any row that leaves a command open on
purpose (AW5, AW6), changes the AutoLISP ``*error*`` handler of the modeller's
session (AW8), could hang AutoCAD on a half-read form (AW7), needs a busy AutoCAD
(BA3), a stopped job (BA4) or a PDF (AW10). Rows that save a view from the screen need
the Model tab in front: the runner never switches tab itself, so with a sheet in front they are said as not run this time.
"""

from __future__ import annotations

import time

import live_common as lc
from live_common import Check, Context, expect, parse, refusal

from autocad_mcp.tools import (
    advanced,
    batch,
    drawing_tools,
    layers,
    query,
    settings,
    views,
)

ADMIN = frozenset({"admin"})
SENT = "A\x1bB\tC\nD 5\" E\\F"
LANGUAGES = "മലയാളം مرحبا café üñ"


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _lisp(expression: str) -> tuple[str, dict]:
    raw = await advanced.autocad_run_lisp(expression=expression)
    return raw, parse(raw)


def _form(total: int) -> str:
    """One ``(setq ...)`` form of exactly ``total`` characters (``total`` must leave an odd count for the numbers)."""
    head, tail = "(setq lc-aw9 (list ", "))"
    count = total - len(head) - len(tail)
    return head + "1" + " 1" * ((count - 1) // 2) + tail


async def aw1_a_lisp_error_is_answered_at_once(ctx: Context) -> str:
    start = time.monotonic()
    raw, out = await _lisp("(+ 1 nil)")
    took = time.monotonic() - start
    expect(out.get("lisp_error"), f"no lisp_error came back: {str(out)[:140]}")
    expect(out.get("result") is None and out.get("timed_out") is False, f"result {out.get('result')!r}, timed_out {out.get('timed_out')!r}")
    expect(lc.first_line(raw).startswith("NOTHING CHANGED"), f"the first line is {lc.first_line(raw)!r}")
    expect(took < 5.0, f"it took {took:.1f} s, not about 1")
    _, again = await _lisp("(+ 1 2)")
    expect(again.get("result") == "3", f"the next call answered {again.get('result')!r}: AutoCAD was not left free")
    return f"back in {took:.1f} s with lisp_error '{out['lisp_error']}', result null, timed_out false, NOTHING CHANGED; the next call answered 3"


async def aw2_a_long_call_stops_at_the_piece_that_failed(ctx: Context) -> str:
    numbers = " ".join(["1"] * 285)
    defuns = "\n".join(f"(defun lc-aw2-f{n} () (list {numbers}))" for n in range(5))
    raw, out = await _lisp(defuns + "\n(car 5)")
    expect(out.get("lisp_error") and out.get("timed_out") is False, f"no lisp_error, or it timed out: {str(out)[:160]}")
    note = str(out.get("note", ""))
    expect("piece" in note.lower() and "ran" in note, f"the note does not name the piece and what ran before it: {note[:160]}")
    expect(int(out.get("chunks") or 0) >= 5 and int(out.get("chunks_finished") or 0) < int(out["chunks"]),
           f"chunks {out.get('chunks')}, finished {out.get('chunks_finished')}")
    expect(not lc.first_line(raw).startswith("DONE"), f"the first line says {lc.first_line(raw)!r}")
    _, exists = await _lisp("(type lc-aw2-f0)")
    expect(exists.get("result") not in (None, "nil"), f"lc-aw2-f0 is not defined: {exists.get('result')!r}")
    return f"lisp_error '{out['lisp_error']}'; {note[-120:]} (first line {lc.first_line(raw)[:30]!r}); the first defun exists (type {exists['result']})"


async def aw3_a_missing_function_is_named(ctx: Context) -> str:
    _, out = await _lisp("(no-such-function 1)")
    expect("no-such-function" in str(out.get("lisp_error", "")).lower(), f"lisp_error is {out.get('lisp_error')!r}: it does not name the function")
    expect(out.get("timed_out") is False, "it timed out")
    return f"lisp_error '{out['lisp_error']}', timed_out false"


async def aw4_complete_commands_inside_the_wrapper_still_draw(ctx: Context) -> str:
    o = lc.origin("AW4")
    before = await lc.entity_count()
    said = []
    for name, expression in (("circle", f'(command "_.CIRCLE" "{o[0]},{o[1]}" "10")'),
                             ("line", f'(command "_.LINE" "{o[0]},{o[1]}" "{o[0] + 10},{o[1] + 10}" "")')):
        _, out = await _lisp(expression)
        expect(not out.get("lisp_error") and not out.get("cancelled_command") and out.get("timed_out") is False,
               f"the {name} came back with {str({k: out.get(k) for k in ('lisp_error', 'cancelled_command', 'timed_out', 'note')})[:200]}")
        now = await lc.entity_count()
        expect(now == before + 1, f"the {name} left {now - before} new objects, not 1")
        before = now
        said.append(name)
    return "a circle and a line each drawn by one complete (command ...), timed_out false, no lisp_error, no cancelled_command. One Ctrl+Z each was not pressed"


async def aw9_a_form_of_1700_runs_and_one_of_1800_is_refused(ctx: Context) -> str:
    first = _form(1700)
    expect(len(first) == 1700, f"the test form is {len(first)} characters")
    _, out = await _lisp(first)
    expect(not out.get("lisp_error") and out.get("timed_out") is False and out.get("result") is not None,
           f"the 1,700 character form came back with {str({k: out.get(k) for k in ('lisp_error', 'timed_out', 'result')})[:160]}")
    said = refusal(await advanced.autocad_run_lisp(expression=_form(1800)))
    expect("split it" in said.lower(), f"the 1,800 character form was refused in other words: {said[:160]}")
    return f"1,700 characters ran and answered at once; 1,800 refused: '{said[:110]}' before anything was sent"


async def aw11_text_with_control_characters_is_drawn_literally(ctx: Context) -> str:
    o = lc.origin("AW11")
    before = await lc.entity_count()
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "text", "position": _at(o, 0, 0), "text": SENT, "height": 250, "layer": "LC-AW11"}]))
    expect(made["created"] == 1 and made["failed"] == 0, f"created {made['created']}, failed {made['failed']}")
    got = parse(await query.autocad_get_entity(handle=made["handles"][0]))
    expect(got.get("type") == "text" and got.get("text") == SENT, f"the object holds {got.get('text')!r}, not {SENT!r}")
    expect(await lc.entity_count() == before + 1, "something besides the one text object was made")
    return "one TEXT holds the Esc, the tab, the newline, 5\" and the backslash exactly as sent; nothing else was made. `Command:` free was not looked at"


async def aw12_malayalam_arabic_and_accents_are_drawn_as_sent(ctx: Context) -> str:
    o = lc.origin("AW12")
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "text", "position": _at(o, 0, 0), "text": LANGUAGES, "height": 250, "layer": "LC-AW12"}]))
    expect(made["created"] == 1 and made["failed"] == 0, f"created {made['created']}, failed {made['failed']}")
    got = parse(await query.autocad_get_entity(handle=made["handles"][0]))
    expect(got.get("text") == LANGUAGES, f"the text reads back {got.get('text')!r}, not what was sent")
    return f"Malayalam, Arabic and accented text read back exactly as sent (style {got.get('style')}). Whether the letters show in a font that has them was not looked at"


async def aw13_a_nul_and_u0085_are_refused_before_anything_is_sent(ctx: Context) -> str:
    o = lc.origin("AW13")
    before = await lc.entity_count()
    said = []
    for name, text in (("NUL", "A\x00B"), ("U+0085", "A\u0085B")):
        words = refusal(await batch.autocad_batch_draw(operations=[
            {"type": "text", "position": _at(o, 0, 0), "text": text, "height": 250, "layer": "LC-AW13"}]))
        expect(name in words, f"the refusal of {name} does not name it: {words[:140]}")
        said.append(words[:90])
    expect(await lc.entity_count() == before, "something was drawn although both were refused")
    return "both refused naming the character (" + " | ".join(said) + "); nothing drawn"


async def aw14_a_real_line_break_inside_a_lisp_string(ctx: Context) -> str:
    _, out = await _lisp('(strlen "a\nb")')
    expect(out.get("result") == "3", f"it answered {out.get('result')!r} (timed_out {out.get('timed_out')!r}), not 3")
    return "(strlen \"a<newline>b\") answered 3, not a stuck prompt"


async def ba1_a_view_name_with_a_control_character_is_refused(ctx: Context) -> str:
    before = sorted(v["name"] for v in parse(await views.autocad_list_views())["views"])
    said = []
    for word, name in (("a line break", "A\nB"), ("an Esc character", "A\x1bB"), ("a tab", "A\tB")):
        words = refusal(await views.autocad_save_view(name=name, from_screen=True))
        expect(f"holds {word}" in words and "Nothing was typed" in words, f"the name with {word} was refused in other words: {words[:160]}")
        said.append(word)
    after = sorted(v["name"] for v in parse(await views.autocad_list_views())["views"])
    expect(after == before, f"the views changed from {before} to {after}")
    return "a line break, an Esc and a tab in a view name were each refused ('holds ..., which cannot be typed ... Nothing was typed'); no view made or deleted. `Command:` free was not looked at"


async def _model_tab_in_front() -> None:
    """Say 'not run this time' when a sheet tab is in front: a view saved from the screen is the Model tab's.

    The runner does not switch tabs itself: a tab switch by LISP is what AF23 asks about, and
    would bring up Heron's erase question on a plug-in that still counts it.
    """
    active = str(parse(await drawing_tools.autocad_list_layouts())["active"])
    if active != "Model":
        raise lc.Refused(f"not run this time: the sheet tab {active} is in front; click the Model tab and run it again")


async def ba2_a_view_is_saved_and_replaced_from_the_screen(ctx: Context) -> str:
    await _model_tab_in_front()
    first = parse(await views.autocad_save_view(name="LC-BA2-LIVING-3D", from_screen=True))
    expect(first.get("saved") and first.get("replaced") is False, f"the first save answered {str(first)[:140]}")
    second = parse(await views.autocad_save_view(name="LC-BA2-LIVING-3D", from_screen=True, replace=True))
    expect(second.get("replaced") is True, f"the second save answered {str(second)[:140]}")
    parse(await views.autocad_save_view(name="LC-BA2-Café", from_screen=True))
    names = [v["name"] for v in parse(await views.autocad_list_views())["views"]]
    expect("LC-BA2-Café" in names, f"the accented view is not listed: {names}")
    return "saved from the screen, replaced with replace=true, and an accented name saved too. An Arabic name was not tried"


async def bf1_a_layer_name_with_a_control_character_is_refused(ctx: Context) -> str:
    before = parse(await layers.autocad_list_layers())["count"]
    for word, name in (("a line break", "A\nB"), ("a tab", "A\tB"), ("an Esc character", "A\x1bB")):
        words = refusal(await layers.autocad_create_layer(name=name))
        expect(f"layer name holds {word}" in words and "Nothing was typed" in words, f"the name with {word} was refused in other words: {words[:160]}")
    after = parse(await layers.autocad_list_layers())["count"]
    expect(after == before, f"the layers went from {before} to {after}")
    return "a line break, a tab and an Esc in a layer name were each refused at once ('The layer name holds ... Nothing was typed'); no layer made"


async def bf2_ordinary_names_are_made_as_before(ctx: Context) -> str:
    layer = parse(await layers.autocad_create_layer(name="LC-BF2-A-WALL"))
    expect(layer.get("created") is True, f"the layer answered {layer}")
    styles = parse(await settings.autocad_create_styles(text_styles=[{"name": "LC-BF2-TXT-1", "font": "romans.shx"}]))
    rows = [r for r in styles.get("text_styles") or [] if str(r.get("name", "")).upper() == "LC-BF2-TXT-1"]
    expect(rows and rows[0].get("created") is True, f"the text style answered {str(styles)[:160]}")
    return "a layer and a text style with ordinary names (LC-BF2-A-WALL, LC-BF2-TXT-1) were made as before"


CHECKS: tuple[Check, ...] = (
    Check("AW1", "AW", "a LISP error is answered at once", aw1_a_lisp_error_is_answered_at_once, ADMIN),
    Check("AW2", "AW", "a long call stops at the piece that failed", aw2_a_long_call_stops_at_the_piece_that_failed, ADMIN),
    Check("AW3", "AW", "a missing function is named", aw3_a_missing_function_is_named, ADMIN),
    Check("AW4", "AW", "complete commands inside the wrapper still draw", aw4_complete_commands_inside_the_wrapper_still_draw, ADMIN),
    Check("AW9", "AW", "a form of 1,700 runs and one of 1,800 is refused", aw9_a_form_of_1700_runs_and_one_of_1800_is_refused, ADMIN),
    Check("AW11", "AW", "text with control characters is drawn literally", aw11_text_with_control_characters_is_drawn_literally),
    Check("AW12", "AW", "Malayalam, Arabic and accents are drawn as sent", aw12_malayalam_arabic_and_accents_are_drawn_as_sent),
    Check("AW13", "AW", "a NUL and U+0085 are refused before sending", aw13_a_nul_and_u0085_are_refused_before_anything_is_sent),
    Check("AW14", "AW", "a real line break inside a LISP string", aw14_a_real_line_break_inside_a_lisp_string, ADMIN),
    Check("BA1", "BA", "a view name with a control character is refused", ba1_a_view_name_with_a_control_character_is_refused),
    Check("BA2", "BA", "a view is saved and replaced from the screen", ba2_a_view_is_saved_and_replaced_from_the_screen),
    Check("BF1", "BF", "a layer name with a control character is refused", bf1_a_layer_name_with_a_control_character_is_refused),
    Check("BF2", "BF", "ordinary names are made as before", bf2_ordinary_names_are_made_as_before),
)

BY_EYE: dict[str, str] = {
    "AW5": "(command \"_.CAMERA\" ...) leaves a command open on purpose, and a miss would leave AutoCAD stuck for every later row",
    "AW6": "leaves a LINE command open on purpose before the error, and a miss would leave AutoCAD stuck for every later row",
    "AW7": "a form AutoLISP cannot read although its brackets balance may leave AutoCAD waiting, and what comes back is for you to record",
    "AW8": "sets AutoLISP's *error* handler in the modeller's session, where it would stay after the run",
    "AW10": "needs the PDF of row AO2 (two pages, TrueType text), which the runner does not make",
    "BA3": "needs AutoCAD kept busy by hand (orbiting a heavy 3D drawing or a long REGEN) while the calls run",
    "BA4": "needs HERONSTOP typed in AutoCAD by hand, in the middle of a call and again after it",
}
