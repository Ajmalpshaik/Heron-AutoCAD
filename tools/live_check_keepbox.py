"""Live checks for the palette, the Keep and erase questions, busy refusals and selecting objects (groups AV, AX, AZ, BC).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Almost every row here is a box answered by a person (Keep, Discard, Enter, Esc, a
palette button), needs Ask to Keep on (the runner stops when it is on), UNDO turned
off, the Options dialog held open to keep AutoCAD busy, or HERONSTOP. Those have their
reasons. Measured: a view of the Model tab replaced by name and from the screen (AV6),
what ``autocad_show`` says of a line, a layer's handle and a handle that is not there,
with the isolation always ended (AZ6), and a polyline whose width changes along it
refused by a trim (BC13). AV6 and AZ6 need the Model tab in front: the runner never
switches tab itself, so with a sheet in front they are said as not run this time.
"""

from __future__ import annotations

import live_common as lc
from live_common import Check, Context, expect, near_point, parse

from autocad_mcp.tools import (
    advanced,
    batch,
    document,
    draw,
    drawing_tools,
    edit2d,
    query,
    views,
)

BOGUS_HANDLE = "7FFFFFF0"


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _model_tab_in_front() -> None:
    active = str(parse(await drawing_tools.autocad_list_layouts())["active"])
    if active != "Model":
        raise lc.Refused(f"not run this time: the sheet tab {active} is in front; click the Model tab and run it again")


async def av6_a_model_view_is_replaced_by_name_and_from_the_screen(ctx: Context) -> str:
    await _model_tab_in_front()
    name = "LC-AV6-PUMP-AREA"
    o = lc.origin("AV6")
    first = parse(await views.autocad_save_view(name=name, corner1=_at(o, 0, 0), corner2=_at(o, 100, 50)))
    expect(first.get("saved") and first.get("replaced") is False, f"the first save answered {str(first)[:140]}")
    by_corners = parse(await views.autocad_save_view(name=name, corner1=_at(o, 0, 0), corner2=_at(o, 100, 50), replace=True))
    expect(by_corners.get("replaced") is True, f"replacing by corners answered {str(by_corners)[:160]}")
    from_screen = parse(await views.autocad_save_view(name=name, from_screen=True, replace=True))
    expect(from_screen.get("replaced") is True, f"replacing from the screen answered {str(from_screen)[:160]}")
    return ("a Model tab view was replaced twice, by corners and from the screen, both 'replaced': true (neither was refused as "
            "a layout's view or for not saying which tab). AV5's layout view needs VIEW in paper space by hand")


async def az6_show_names_what_it_cannot_select_and_isolation_ends(ctx: Context) -> str:
    await _model_tab_in_front()
    o = lc.origin("AZ6")
    line = parse(await draw.autocad_draw_line(start=_at(o, 0, 0), end=_at(o, 1000, 0), layer="LC-AZ6"))["handle"]
    layer = (await advanced.autocad_run_lisp(expression='(cdr (assoc 5 (tblsearch "LAYER" "LC-AZ6")))'))
    layer_handle = str(parse(layer).get("result") or "").strip('"')
    expect(layer_handle and layer_handle != "nil", f"the layer's handle could not be read: {layer_handle!r}")
    out = parse(await document.autocad_show(handles=[line, layer_handle, BOGUS_HANDLE]))
    expect(out.get("shown") == 1, f"shown is {out.get('shown')}, not 1")
    reasons = {row.get("handle"): row.get("reason") for row in out.get("not_selectable") or []}
    expect(reasons.get(layer_handle) == "not_a_drawing_object", f"the layer is in not_selectable as {reasons}, not not_a_drawing_object")
    expect(BOGUS_HANDLE in (out.get("not_found") or []), f"the handle that is not there is not in not_found: {out.get('not_found')}")
    try:
        isolated = parse(await document.autocad_show(handles=[line], isolate=True))
        expect(isolated.get("shown") == 1 and isolated.get("isolated") is True, f"isolating the line answered {str(isolated)[:140]}")
    finally:
        ended = parse(await document.autocad_show(end_isolation=True))
    expect(ended.get("isolation_ended") is True, f"ending the isolation answered {str(ended)[:140]}")
    only = parse(await document.autocad_show(handles=[layer_handle], isolate=True))
    expect(only.get("shown") == 0 and only.get("isolated") is False, f"isolating only the layer answered {str(only)[:140]}")
    return ("the line shown (1), the layer in not_selectable as not_a_drawing_object, a handle that is not in the drawing in "
            "not_found (a made-up handle, not an erased object: erasing one brings Heron's erase question); isolating the line "
            "answered isolated true and end_isolation brought it back; the layer alone: shown 0, isolated false. What the screen "
            "shows and that no command was left at 'Select objects' were not looked at")


async def bc13_a_polyline_whose_width_changes_is_refused_by_trim(ctx: Context) -> str:
    o = lc.origin("BC13")
    made = parse(await batch.autocad_batch_draw(operations=[
        {"type": "polyline", "points": [_at(o, 0, 0), _at(o, 1000, 0)], "layer": "LC-BC13"},
        {"type": "line", "start": _at(o, 500, -100), "end": _at(o, 500, 100), "layer": "LC-BC13"},
    ]))
    taper, edge = made["handles"]
    await lc.by_hand_width(taper, 0, 0.0, 20.0)
    before = parse(await query.autocad_get_entity(handle=taper))
    out = parse(await edit2d.autocad_trim_extend(operation="trim", handles=[taper], edges=[edge], points=[_at(o, 800, 0)]))
    reasons = " ".join(f.get("reason", "") for f in out.get("failed") or [])
    expect(out.get("done") == 0 and "width changes along it" in reasons,
           f"the tapered polyline was not refused for its width: done {out.get('done')}, failed {reasons[:140]}")
    after = parse(await query.autocad_get_entity(handle=taper))
    expect(all(near_point(a, b, 1e-6) for a, b in zip(after["vertices"], before["vertices"], strict=True)) and len(after["vertices"]) == len(before["vertices"]),
           "the tapered polyline changed although refused")
    return ("a polyline whose width runs 0 to 20 along one segment: the trim is refused 'width changes along it' (done 0) and the "
            "polyline is unchanged. Which error AutoCAD gave in the add-in or server log was not read")


CHECKS: tuple[Check, ...] = (
    Check("AV6", "AV", "a model view is replaced by name and from the screen", av6_a_model_view_is_replaced_by_name_and_from_the_screen),
    Check("AZ6", "AZ", "show names what it cannot select and isolation ends", az6_show_names_what_it_cannot_select_and_isolation_ends,
          frozenset({"admin"})),
    Check("BC13", "BC", "a polyline whose width changes is refused by trim", bc13_a_polyline_whose_width_changes_is_refused_by_trim),
)

_OPTIONS = "needs the Options dialog (OP) held open by hand to keep AutoCAD busy past the 3 s filter"
_PALETTE = "needs Ask to Keep on, a Heron palette button pressed by hand and the add-in log read; the runner stops when Ask to Keep is on"
_BOX = "brings up Heron's Keep or erase question, which a person answers (Enter, Esc, Keep, Discard)"

BY_EYE: dict[str, str] = {
    "AV1": "needs four attribute inserts and " + _OPTIONS,
    "AV2": "needs a .csv, a table and " + _OPTIONS,
    "AV3": _OPTIONS + ", then the render exposure and the lights read",
    "AV4": "needs two drawings open and " + _OPTIONS,
    "AV5": "needs a view saved in a layout tab with VIEW in paper space by hand, then the Model tab",
    "AV7": _OPTIONS + ", and the view then read to see it was not left deleted",
    "AX1": _PALETTE,
    "AX2": _PALETTE + "; a LINE is left at its prompt on purpose",
    "AX3": _PALETTE + "; a LINE is left at its prompt on purpose",
    "AX4": "erases four objects with Heron and answers 'bring them back' to the erase question, which a person answers",
    "AX5": "erases and adds objects, answers 'bring them back' to the erase question and reads the palette card",
    "AX6": _PALETTE,
    "AX7": "needs a job that ended OUTCOME UNKNOWN first (AX3), then autocad_gaps read",
    "AX8": _PALETTE + "; a LINE is left at its prompt on purpose",
    "AZ1": "needs the Heron palette open and its Select and Zoom buttons pressed on a card, and the line under the list read",
    "AZ2": "needs the Heron palette open and its Select and Zoom buttons pressed on a card",
    "AZ3": "needs a layout tab and a viewport entered by hand, and the palette's Select and Zoom buttons pressed",
    "AZ4": "needs the palette's Select button pressed on a card",
    "AZ5": "needs Ask to Keep on and the Keep box answered with Discard it; the runner stops when Ask to Keep is on",
    "BC1": "the join erases a line, so " + _BOX + " (Enter), and the palette card is read",
    "BC2": "the join erases a line, so " + _BOX + " (Esc, the X, or waiting)",
    "BC3": "the join erases a line, so " + _BOX + " (Keep the change), and autocad_undo_last is then called",
    "BC4": "explode erases the block, so " + _BOX + " (Enter, then Keep the change)",
    "BC5": "trimming and breaking a circle erase it, so " + _BOX,
    "BC6": "needs UNDO turned off by hand (UNDO > Control > None) and back on, and the runner never changes UNDO",
    "BC7": "deleting two lines " + _BOX,
    "BC8": "needs the erase question switched off in Settings by hand, then on again",
    "BC9": "needs Ask to Keep on and Discard pressed; the runner stops when Ask to Keep is on",
    "BC10": "needs a drawing with an xref that has a MECH|M-DUCT layer, and layer 0 current",
    "BC11": "needs a drawing with an xref that has a MECH|M-DUCT layer, and the layer states read",
    "BC12": _PALETTE + "; a LINE is left at its prompt on purpose",
}
