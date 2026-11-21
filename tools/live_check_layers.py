"""Live checks for layers and annotation (group AB).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Each row draws its own objects at its own spot (``lc.origin``) on its own
``LC-AB..`` layers, then measures what the tool did: a dimension's style and
scale read back, where its dimension line and text are now, every layer's on /
frozen / locked state read back with autocad_list_layers, an object's annotation
scales read back with autocad_list_annotation_scales.

Global things a row changes are put back where the row allows: the current
layer, the layer states it saved, the current dimension style (never changed).
The rows that need a 1:50 drawing set it with autocad_drawing_setup themselves,
so one row can run on its own; the scratch drawing is left at 1:50, and the 1:25
scale AB11 adds stays in its scale list (no tool takes a scale out of the list).
"""

from __future__ import annotations

import math
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, parse, refusal

from autocad_mcp.tools import (
    annotate,
    annotation_scales,
    batch,
    dimensions,
    dimensions_edit,
    draw,
    layer_states,
    layers,
    query,
    settings,
)


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


async def _one_to_fifty() -> None:
    """The drawing at 1:50 (DIMSCALE 50, CANNOSCALE 1:50), as the rows that need it say."""
    out = parse(await settings.autocad_drawing_setup(scale="1:50"))
    expect(not out.get("failed"), f"the drawing could not be set to 1:50: {out.get('failed')}")


def _layer_table(listed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(layer["name"]): layer for layer in listed.get("layers") or []}


def _states(listed: dict[str, Any]) -> dict[str, tuple[bool, bool, bool]]:
    """Each layer's (on, frozen, locked)."""
    return {name: (bool(la.get("on")), bool(la.get("frozen")), bool(la.get("locked")))
            for name, la in _layer_table(listed).items()}


def _state_names(listed: dict[str, Any]) -> list[str]:
    return [str(s.get("name", "")) for s in listed.get("layer_states") or []]


def _same_states(got: dict[str, Any], want: dict[str, tuple[bool, bool, bool]], when: str) -> None:
    now = _states(got)
    wrong = {name: now.get(name) for name, state in want.items() if now.get(name) != state}
    expect(not wrong, f"{when}, these layers are not as they were (on, frozen, locked): "
                      f"{ {name: (want[name], wrong[name]) for name in list(wrong)[:6]} }")


def _has_scale(names: Any, wanted: str) -> bool:
    return any(str(n).strip().casefold() == wanted.casefold() for n in names or [])


def _ratio_is(scale: dict[str, Any] | None, paper: float, drawing: float) -> bool:
    if not scale or not scale.get("drawing"):
        return False
    return abs(float(scale["paper"]) / float(scale["drawing"]) - paper / drawing) < 1e-9


def _top(info: dict[str, Any]) -> float:
    return float(info["bounding_box"]["max"][1])


def _bottom(info: dict[str, Any]) -> float:
    return float(info["bounding_box"]["min"][1])


# ---------------------------------------------------------------------------
# Group AB - layers and annotation
# ---------------------------------------------------------------------------

AB1_STYLE = "LC-AB1-DIM-1-5"


async def ab1_a_named_dim_style_keeps_its_own_scale(ctx: Context) -> str:
    o = lc.origin("AB1")
    await _one_to_fifty()
    made = parse(await settings.autocad_create_styles(dim_styles=[{"name": AB1_STYLE, "scale": 5}], replace=True))
    row = (made.get("dim_styles") or [{}])[0]
    expect(near((row.get("variables") or {}).get("DIMSCALE"), 5.0, 1e-9), f"the style was not made with DIMSCALE 5: {row}")
    style_before = await lc.variable("DIMSTYLE")
    expect(near(await lc.variable("DIMSCALE"), 50.0, 1e-9), "DIMSCALE is not 50 after setting the drawing to 1:50")

    styled = parse(await dimensions.autocad_dimension_run(
        points=[_at(o, 0, 0), _at(o, 300, 0), _at(o, 750, 0)], offset=50, dim_style=AB1_STYLE, layer="LC-AB1"))
    expect(styled.get("count") == 2 and not styled.get("failed"),
           f"the styled run made {styled.get('count')} dimensions, failed {styled.get('failed')}")
    expect(styled.get("dim_style") == AB1_STYLE, f"the run says style {styled.get('dim_style')}, not {AB1_STYLE}")
    expect(near(styled.get("style_scale"), 5.0, 1e-9), f"style_scale is {styled.get('style_scale')}, not 5")
    expect(styled.get("dim_scale") is None, f"the styled run wrote DIMSCALE {styled.get('dim_scale')} over the style's")
    for handle in styled["handles"]:
        info = await _entity(handle)
        expect(info.get("style") == AB1_STYLE, f"{handle} reads style {info.get('style')}, not {AB1_STYLE}")
        scale = (await lc.read_props(handle, ["ScaleFactor"]))["ScaleFactor"]
        expect(near(scale, 5.0, 1e-9), f"{handle} has DIMSCALE {scale}, not the style's 5 (an override)")

    plain = parse(await dimensions.autocad_dimension_run(
        points=[_at(o, 0, 1000), _at(o, 300, 1000), _at(o, 750, 1000)], offset=50, layer="LC-AB1"))
    expect(plain.get("count") == 2 and not plain.get("failed"),
           f"the plain run made {plain.get('count')} dimensions, failed {plain.get('failed')}")
    expect(near(plain.get("dim_scale"), 50.0, 1e-9), f"the plain run wrote DIMSCALE {plain.get('dim_scale')}, not 50")
    info = await _entity(plain["handles"][0])
    expect(info.get("style") == style_before, f"the plain run is in style {info.get('style')}, not the current {style_before}")
    big = (await lc.read_props(plain["handles"][0], ["ScaleFactor"]))["ScaleFactor"]
    expect(near(big, 50.0, 1e-9), f"the plain dimension has DIMSCALE {big}, not 50")

    expect(await lc.variable("DIMSTYLE") == style_before, "the current dimension style changed")
    expect(near(await lc.variable("DIMSCALE"), 50.0, 1e-9), "the drawing's DIMSCALE is no longer 50")
    before = await lc.entity_count()
    message = refusal(await dimensions.autocad_dimension_run(
        points=[_at(o, 0, 2000), _at(o, 300, 2000)], offset=50, dim_style="NOPE", layer="LC-AB1"))
    expect("NOPE" in message, f"the unknown style was refused without naming it: {message[:160]}")
    expect(await lc.entity_count() == before, "the refused run still drew something")
    return (f"the {AB1_STYLE} run reads its style with DIMSCALE 5 (style_scale 5, nothing written over it); "
            f"the plain run has DIMSCALE 50, so a tenth the size; DIMSTYLE is still {style_before} and "
            "DIMSCALE 50; NOPE was refused and nothing drawn. The sizes on screen were not looked at")


async def ab2_a_stack_of_dimensions_is_spaced_evenly(ctx: Context) -> str:
    o = lc.origin("AB2")
    dims = []
    for length, line_y in ((1000, 300), (2000, 500), (3000, 750), (4000, 1600)):
        made = parse(await draw.autocad_add_dimension(
            dimension_type="horizontal", point1=_at(o, 0, 0), point2=_at(o, length, 0),
            text_position=_at(o, length / 2, line_y), layer="LC-AB2"))
        dims.append(made["handle"])

    async def read() -> list[dict[str, Any]]:
        return [await _entity(h) for h in dims]

    before = await read()
    dry = parse(await dimensions_edit.autocad_space_dimensions(handles=dims, spacing=400, dry_run=True))
    moves = {m["handle"]: m for m in dry.get("moves") or []}
    expect(dry.get("moved") == 0 and len(moves) == 3, f"the dry run answered moved {dry.get('moved')}, {len(moves)} moves")
    for handle, was, now in zip(dims[1:], (200, 450, 1300), (400, 800, 1200), strict=True):
        move = moves.get(handle) or {}
        expect(near(move.get("offset_was"), was, 1e-6) and near(move.get("offset_now"), now, 1e-6),
               f"the dry run would move {handle} from {move.get('offset_was')} to {move.get('offset_now')}, "
               f"not {was} to {now}")
    after_dry = await read()
    expect([d.get("bounding_box") for d in after_dry] == [d.get("bounding_box") for d in before],
           "the dry run moved a dimension")

    out = parse(await dimensions_edit.autocad_space_dimensions(handles=dims, spacing=400))
    expect(out.get("moved") == 3, f"spacing moved {out.get('moved')} dimensions, not 3")
    spaced = await read()
    steps = [round(_top(d) - _top(spaced[0]), 4) for d in spaced[1:]]
    expect(all(near(s, w, 1e-3) for s, w in zip(steps, (400, 800, 1200), strict=True)),
           f"the dimension lines now sit {steps} off the base, not 400, 800, 1200")
    for was, now in zip(before, spaced, strict=True):
        expect(near(now.get("measurement"), was.get("measurement"), 1e-6),
               f"{now['handle']} now measures {now.get('measurement')}, not {was.get('measurement')}")
        expect(near(_bottom(now), _bottom(was), 1e-6), f"{now['handle']}'s extension lines no longer start on the geometry")

    zero = parse(await dimensions_edit.autocad_space_dimensions(handles=dims, spacing=0))
    expect(zero.get("moved") == 3, f"spacing 0 moved {zero.get('moved')} dimensions, not 3")
    lined = await read()
    tops = [round(_top(d) - _top(lined[0]), 4) for d in lined[1:]]
    expect(all(near(t, 0.0, 1e-3) for t in tops), f"spacing 0 left the lines {tops} off the base, not on it")
    expect(all(near(_bottom(n), _bottom(w), 1e-6) for n, w in zip(lined, before, strict=True)),
           "spacing 0 moved an extension line off the geometry")
    return ("the dry run moved nothing; then the lines sit 400, 800, 1200 off the base with the text, measurements "
            "and extension line starts unchanged; spacing 0 lined them up on the base. Ctrl+Z was not tried")


AB3_TURN = math.radians(30)
AB3_ALONG = (math.cos(AB3_TURN), math.sin(AB3_TURN))
AB3_ACROSS = (-math.sin(AB3_TURN), math.cos(AB3_TURN))


def _slope(o: tuple[float, float], along: float, across: float) -> list[float]:
    """A point on the 30-degree slope: so far along it and so far out square to it."""
    return [o[0] + along * AB3_ALONG[0] + across * AB3_ACROSS[0], o[1] + along * AB3_ALONG[1] + across * AB3_ACROSS[1]]


def _dot(a: list[float], b: list[float], u: tuple[float, float]) -> float:
    return (float(a[0]) - float(b[0])) * u[0] + (float(a[1]) - float(b[1])) * u[1]


async def ab3_an_aligned_stack_steps_square_and_a_radius_is_skipped(ctx: Context) -> str:
    o = lc.origin("AB3")
    dims, measured = [], []
    for length, out in ((1000, 300), (2000, 500), (3000, 750), (4000, 1600)):
        made = parse(await draw.autocad_add_dimension(
            dimension_type="aligned", point1=_slope(o, 0, 0), point2=_slope(o, length, 0),
            text_position=_slope(o, length / 2, out), layer="LC-AB3"))
        dims.append(made["handle"])
        measured.append(made.get("measurement"))
    (circle,) = parse(await batch.autocad_batch_draw(operations=[
        {"type": "circle", "center": _at(o, 6000, -2000), "radius": 300, "layer": "LC-AB3"},
    ]))["handles"]
    radius = parse(await draw.autocad_add_dimension(
        dimension_type="radial", point1=_at(o, 6000, -2000), point2=_at(o, 6300, -2000), layer="LC-AB3"))["handle"]
    radius_before = (await _entity(radius)).get("bounding_box")
    text_before = [(await lc.read_props(h, ["TextPosition"]))["TextPosition"] for h in dims]

    out = parse(await dimensions_edit.autocad_space_dimensions(handles=[*dims, radius], spacing=400))
    expect(out.get("moved") == 3, f"spacing moved {out.get('moved')} dimensions, not 3")
    expect(radius in [s.get("handle") for s in out.get("skipped") or []], f"the radius dimension is not in skipped: {out.get('skipped')}")
    text_after = [(await lc.read_props(h, ["TextPosition"]))["TextPosition"] for h in dims]
    for handle, was, now in zip(dims, text_before, text_after, strict=True):
        sideways = _dot(now, was, AB3_ALONG)
        expect(near(sideways, 0.0, 1e-3), f"{handle}'s text moved {sideways:.4f} along the slope, not square to it")
    steps = [round(_dot(t, text_after[0], AB3_ACROSS), 4) for t in text_after[1:]]
    expect(all(near(s, w, 1e-3) for s, w in zip(steps, (400, 800, 1200), strict=True)),
           f"square to the slope the dimensions now sit {steps} off the base, not 400, 800, 1200")
    for handle, was in zip(dims, measured, strict=True):
        now = (await _entity(handle)).get("measurement")
        expect(near(now, was, 1e-6), f"{handle} now measures {now}, not {was}: an extension line moved")
    expect((await _entity(radius)).get("bounding_box") == radius_before, "the skipped radius dimension moved")
    return ("the aligned dimensions stepped out square to the 30-degree slope to 400, 800, 1200 off the base, "
            "measurements unchanged; the radius dimension is in skipped and did not move")


AB5 = ("LC-AB5-A", "LC-AB5-B", "LC-AB5-C", "LC-AB5-D")
AB5_STATE = "LC-AB5-COORD"


async def ab5_a_layer_state_is_saved_and_brought_back(ctx: Context) -> str:
    a, b, c, d = AB5
    for name in AB5:
        parse(await layers.autocad_create_layer(name=name))
    parse(await layers.autocad_set_layer_state(name=a, on=False))
    parse(await layers.autocad_set_layer_state(name=b, frozen=True))
    saved = parse(await layer_states.autocad_layer_states(action="save", name=AB5_STATE))
    expect(saved.get("name") == AB5_STATE and not saved.get("replaced"), f"the save answered {saved}")
    expect({"on", "frozen", "locked"} <= set(saved.get("remembers") or []),
           f"the state remembers only {saved.get('remembers')}")
    parse(await layers.autocad_set_layer_state(name=a, on=True))
    parse(await layers.autocad_set_layer_state(name=b, frozen=False))
    parse(await layers.autocad_set_layer_state(name=c, on=False))
    parse(await layers.autocad_set_layer_state(name=d, locked=True))
    back = parse(await layer_states.autocad_layer_states(action="restore", name=AB5_STATE))
    changed = {(str(r.get("layer")), str(r.get("property"))) for r in back.get("before_after") or []}
    want = {(a, "on"), (b, "frozen"), (c, "on"), (d, "locked")}
    expect(changed == want, f"the restore lists {sorted(changed)}, not exactly {sorted(want)}")
    listed = parse(await layers.autocad_list_layers())
    now = _states(listed)
    expected = {a: (False, False, False), b: (True, True, False), c: (True, False, False), d: (True, False, False)}
    wrong = {name: now.get(name) for name, state in expected.items() if now.get(name) != state}
    expect(not wrong, f"after the restore these layers read (on, frozen, locked) {wrong}")
    expect(AB5_STATE in _state_names(listed), f"list_layers does not give {AB5_STATE}: {_state_names(listed)}")
    message = refusal(await layer_states.autocad_layer_states(action="save", name=AB5_STATE))
    expect("already" in message and "overwrite" in message, f"saving it again was not refused for that: {message[:160]}")
    parse(await layer_states.autocad_layer_states(action="delete", name=AB5_STATE))
    return (f"restoring {AB5_STATE} put A off, B frozen, C on and D unlocked again, and before_after listed exactly "
            "those four; list_layers gives the state; saving it again without overwrite was refused. "
            "The LAYERSTATE dialog itself was not opened")


AB6_DUCT, AB6_PIPE, AB6_FROZEN = "LC-AB6-DUCT", "LC-AB6-PIPE", "LC-AB6-FROZEN"


async def _isolate(**kwargs: Any) -> dict[str, Any]:
    return parse(await layer_states.autocad_isolate_layers(**kwargs))


async def _listed() -> dict[str, Any]:
    return parse(await layers.autocad_list_layers())


async def ab6_isolate_and_unisolate_put_every_layer_back(ctx: Context) -> str:
    o = lc.origin("AB6")
    for name in (AB6_DUCT, AB6_PIPE, AB6_FROZEN):
        parse(await layers.autocad_create_layer(name=name))
    duct, pipe = parse(await batch.autocad_batch_draw(operations=[
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": AB6_DUCT},
        {"type": "line", "start": _at(o, 0, 500), "end": _at(o, 1000, 500), "layer": AB6_PIPE},
    ]))["handles"]
    start = await _listed()
    was_current = str(start.get("current_layer"))
    snapshot = _states(start)
    expect(layer_states.ISOLATE_STATE not in _state_names(start), "a HERON-ISOLATE state is already in the drawing")
    parse(await layers.autocad_set_current_layer(name="0"))
    isolated = False
    try:
        first = await _isolate(handles=[duct])
        isolated = True
        expect(first.get("kept") == [AB6_DUCT] and first.get("current_layer") == AB6_DUCT
               and not first.get("already_isolated"), f"the first isolate answered {first}")
        now = await _listed()
        shows = sorted(n for n, (on, frozen, _) in _states(now).items() if on and not frozen)
        expect(shows == [AB6_DUCT], f"after isolating the duct these layers show: {shows}")
        expect(now.get("current_layer") == AB6_DUCT, f"the current layer is {now.get('current_layer')}, not {AB6_DUCT}")
        second = await _isolate(handles=[pipe])
        expect(second.get("already_isolated") is True, "isolating again did not keep the first state (already_isolated)")
        back = await _isolate(action="unisolate")
        isolated = False
        expect(back.get("current_layer") == "0", f"un-isolating left {back.get('current_layer')} current, not 0")
        now = await _listed()
        _same_states(now, snapshot, "after un-isolating")
        expect(layer_states.ISOLATE_STATE not in _state_names(now), "HERON-ISOLATE is still in the layer states")

        await _isolate(handles=[duct], others="lock")
        isolated = True
        now = await _listed()
        wrong = sorted(n for n, (_, _, locked) in _states(now).items() if locked != (n != AB6_DUCT))
        expect(not wrong, f"with others='lock' these layers are not as they should be (others locked, duct not): {wrong}")
        expect(now.get("current_layer") == "0", f"lock mode moved the current layer to {now.get('current_layer')}")
        await _isolate(action="unisolate")
        isolated = False

        frozen = await _isolate(handles=[duct], others="freeze")
        isolated = True
        rows = frozen.get("before_after") or []
        moved = [i for i, r in enumerate(rows) if r.get("variable") == "CLAYER"]
        zero = [i for i, r in enumerate(rows) if r.get("layer") == "0" and r.get("property") == "frozen"]
        expect(moved and frozen.get("current_layer") == AB6_DUCT, f"freeze mode did not move the current layer first: {rows[:4]}")
        expect(not zero or moved[0] < zero[0], "layer 0 was frozen before the current layer was moved off it")
        now = await _listed()
        wrong = sorted(n for n, (_, is_frozen, _) in _states(now).items() if is_frozen != (n != AB6_DUCT))
        expect(not wrong, f"with others='freeze' these layers are not as they should be: {wrong}")
        expect(now.get("current_layer") == AB6_DUCT, f"freeze mode left {now.get('current_layer')} current")
        back = await _isolate(action="unisolate")
        isolated = False
        expect(back.get("current_layer") == "0", f"un-isolating the freeze left {back.get('current_layer')} current")

        parse(await layers.autocad_set_layer_state(name=AB6_FROZEN, frozen=True))
        thawed = await _isolate(layers=[AB6_FROZEN])
        isolated = True
        now = await _listed()
        expect(thawed.get("current_layer") == AB6_FROZEN and now.get("current_layer") == AB6_FROZEN,
               f"isolating the frozen layer left {now.get('current_layer')} current")
        expect(_states(now).get(AB6_FROZEN, (False, True, False))[:2] == (True, False),
               f"the isolated frozen layer reads (on, frozen, locked) {_states(now).get(AB6_FROZEN)}")
        await _isolate(action="unisolate")
        isolated = False
        end = await _listed()
        _same_states(end, {**snapshot, AB6_FROZEN: (snapshot[AB6_FROZEN][0], True, snapshot[AB6_FROZEN][2])},
                     "at the end")
        expect(end.get("current_layer") == "0", f"at the end {end.get('current_layer')} is current, not 0")
    except (lc.Failed, lc.Refused):
        if isolated:  # leave the drawing's layers as they were for the rows after this one; its answer is not judged
            await layer_states.autocad_isolate_layers(action="unisolate")
        raise
    parse(await layers.autocad_set_current_layer(name=was_current))
    return ("isolate showed only the duct's layer and made it current; the second isolate kept the first "
            "(already_isolated); un-isolating put every layer and current layer 0 back and HERON-ISOLATE is gone; "
            "lock locked the others, freeze moved the current layer first, a frozen layer was thawed and made "
            "current. Picking a locked object on screen was not tried")


async def ab9_annotative_text_is_2_5_on_paper_at_1_50_and_1_100(ctx: Context) -> str:
    o = lc.origin("AB9")
    await _one_to_fifty()
    note = parse(await draw.autocad_add_text(text="NOTE", position=_at(o, 0, 0), height=125, annotative=True,
                                             layer="LC-AB9"))
    handle = note["handle"]
    expect(note.get("annotative") is True and _has_scale(note.get("annotation_scales"), "1:50"),
           f"the text was not made annotative at 1:50: {note.get('annotative')}, {note.get('annotation_scales')}")
    expect(near(note.get("paper_height"), 2.5, 1e-9), f"the answer gives paper_height {note.get('paper_height')}, not 2.5")
    read = parse(await annotation_scales.autocad_list_annotation_scales(handles=[handle]))
    expect(_ratio_is(read.get("current"), 1, 50), f"the current annotation scale is {read.get('current')}, not 1:50")
    obj = (read.get("objects") or [{}])[0]
    expect(obj.get("annotative") == "yes" and _has_scale(obj.get("scales"), "1:50"),
           f"read back, the text is annotative {obj.get('annotative')} with scales {obj.get('scales')}")
    height = obj.get("height")
    expect(near(height, 125.0, 1e-6),
           f"read back, the text is {height} high, not 125: the height rule in D-81 is wrong (record {height})")
    expect(near(obj.get("paper_height"), 2.5, 1e-9), f"read back, paper_height is {obj.get('paper_height')}, not 2.5")
    added = parse(await annotation_scales.autocad_annotation_scales(handles=[handle], add=["1:100"]))
    scales = ((added.get("objects") or [{}])[0]).get("scales")
    expect(_has_scale(scales, "1:100") and _has_scale(scales, "1:50"), f"after the add the text carries {scales}")
    again = (parse(await annotation_scales.autocad_list_annotation_scales(handles=[handle])).get("objects") or [{}])[0]
    expect(_has_scale(again.get("scales"), "1:100") and _has_scale(again.get("scales"), "1:50"),
           f"read back after the add, the text carries {again.get('scales')}")
    return ("the text is annotative at 1:50, 125 high in the model and paper_height 2.5, read back; after the add "
            "it carries 1:50 and 1:100. The annotative icon, Properties and the two viewports were not looked at")


def _annotative_at_50(answer: dict[str, Any], what: str) -> None:
    expect(answer.get("annotative") is True and _has_scale(answer.get("annotation_scales"), "1:50"),
           f"the {what} was not made annotative at 1:50: {answer.get('annotative')}, {answer.get('annotation_scales')}"
           f"{' - ' + answer['warning'] if answer.get('warning') else ''}")


async def ab10_annotative_dimensions_and_leaders_are_sized_by_the_scale(ctx: Context) -> str:
    o = lc.origin("AB10")
    await _one_to_fifty()
    text, gap, beyond = [float(await lc.variable(n) or 0.0) for n in ("DIMTXT", "DIMGAP", "DIMEXE")]
    one = parse(await draw.autocad_add_dimension(
        dimension_type="horizontal", point1=_at(o, 0, 0), point2=_at(o, 1000, 0), text_position=_at(o, 500, 500),
        layer="LC-AB10", annotative=True))
    _annotative_at_50(one, "dimension")
    run = parse(await dimensions.autocad_dimension_run(
        points=[_at(o, 0, 2000), _at(o, 1000, 2000), _at(o, 2000, 2000)], offset=500, layer="LC-AB10",
        annotative=True))
    expect(run.get("count") == 2, f"the run made {run.get('count')} dimensions, not 2")
    _annotative_at_50(run, "dimension run")
    leader = parse(await annotate.autocad_add_multileader(
        landing=_at(o, 1500, 5000), arrows=[_at(o, 1000, 4000)], text="LC-AB10", layer="LC-AB10", annotative=True))
    _annotative_at_50(leader, "multileader")
    handles = [one["handle"], *run["handles"], leader["handle"]]
    read = parse(await annotation_scales.autocad_list_annotation_scales(handles=handles))
    objects = {str(obj.get("handle")): obj for obj in read.get("objects") or []}
    for handle in handles:
        obj = objects.get(handle) or {}
        expect(obj.get("annotative") == "yes" and _has_scale(obj.get("scales"), "1:50"),
               f"read back, {handle} is annotative {obj.get('annotative')} with scales {obj.get('scales')}")
    # Above its dimension line a dimension carries its text and extension lines: about (gap + text) x 50
    # at 1:50. Plain style size would be 50 times smaller; DIMSCALE on top of the scale, 50 times bigger.
    low, high = 0.4 * text * 50, 3 * (text + gap + beyond) * 50
    sizes = []
    for handle, line_y in ((one["handle"], 500), (run["handles"][0], 2500)):
        above = round(_top(await _entity(handle)) - (o[1] + line_y), 4)
        expect(low <= above <= high, f"{handle} reaches {above} above its dimension line, not between {low:g} and "
                                     f"{high:g} (DIMTXT {text:g} at 1:50): not sized by the scale")
        sizes.append(above)
    return (f"the dimension, the run and the multileader are annotative at 1:50, read back; the dimensions reach "
            f"{sizes[0]:g} and {sizes[1]:g} above their lines (DIMTXT {text:g} x 50), not doubled. Ctrl+Z was not "
            "tried and the leader's size was not measured")


async def ab11_a_missing_scale_is_refused_then_added_and_the_last_kept(ctx: Context) -> str:
    o = lc.origin("AB11")
    await _one_to_fifty()
    note = parse(await draw.autocad_add_text(text="LC-AB11", position=_at(o, 0, 0), height=125, annotative=True,
                                             layer="LC-AB11"))
    handle = note["handle"]
    _annotative_at_50(note, "text")
    drawing = parse(await annotation_scales.autocad_list_annotation_scales())
    had = any(_ratio_is(s, 1, 25) or _has_scale([s.get("name")], "1:25") for s in drawing.get("scales") or [])
    if not had:
        message = refusal(await annotation_scales.autocad_annotation_scales(handles=[handle], add=["1:25"]))
        expect("1:25" in message and "add_missing_to_drawing" in message, f"1:25 was not refused for that: {message[:160]}")
        kept = (parse(await annotation_scales.autocad_list_annotation_scales(handles=[handle])).get("objects") or [{}])[0]
        expect(not _has_scale(kept.get("scales"), "1:25"), f"the refused add still put 1:25 on it: {kept.get('scales')}")
    out = parse(await annotation_scales.autocad_annotation_scales(handles=[handle], add=["1:25"],
                                                                  add_missing_to_drawing=True))
    want_created = [] if had else ["1:25"]
    expect(out.get("scales_created") == want_created, f"scales_created is {out.get('scales_created')}, not {want_created}")
    read = parse(await annotation_scales.autocad_list_annotation_scales(handles=[handle]))
    held = ((read.get("objects") or [{}])[0]).get("scales") or []
    expect(any(_ratio_is(s, 1, 25) for s in read.get("scales") or []), "the drawing's scale list has no 1:25")
    expect(_has_scale(held, "1:25"), f"the text carries {held}, not 1:25")
    message = refusal(await annotation_scales.autocad_annotation_scales(handles=[handle], remove=["1:25", "1:50", "1:100"]))
    expect("at least one" in message, f"removing every scale was not refused for leaving none: {message[:160]}")
    after = ((parse(await annotation_scales.autocad_list_annotation_scales(handles=[handle])).get("objects")
              or [{}])[0]).get("scales")
    expect(after == held, f"the refused removal still changed the scales: {held} -> {after}")
    first = ("the drawing had no 1:25, so the plain add was refused naming add_missing_to_drawing; "
             if not had else "the drawing already had 1:25, so the plain add's refusal was not tried; ")
    return (first + f"with add_missing_to_drawing the text took 1:25 (scales_created {want_created}); removing "
            f"1:25, 1:50 and 1:100 was refused and the text still carries {', '.join(held)}")


LAYERS_AB: tuple[Check, ...] = (
    Check("AB1", "AB", "a named dim style keeps its own scale", ab1_a_named_dim_style_keeps_its_own_scale),
    Check("AB2", "AB", "a stack of dimensions is spaced evenly", ab2_a_stack_of_dimensions_is_spaced_evenly),
    Check("AB3", "AB", "an aligned stack steps square, a radius is skipped",
          ab3_an_aligned_stack_steps_square_and_a_radius_is_skipped),
    Check("AB5", "AB", "a layer state is saved and brought back", ab5_a_layer_state_is_saved_and_brought_back),
    Check("AB6", "AB", "isolate and un-isolate put every layer back", ab6_isolate_and_unisolate_put_every_layer_back),
    Check("AB9", "AB", "annotative text is 2.5 on paper", ab9_annotative_text_is_2_5_on_paper_at_1_50_and_1_100),
    Check("AB10", "AB", "annotative dimensions and leaders are sized by the scale",
          ab10_annotative_dimensions_and_leaders_are_sized_by_the_scale),
    Check("AB11", "AB", "a missing scale is refused, then added, the last kept",
          ab11_a_missing_scale_is_refused_then_added_and_the_last_kept),
)

EYE_AB: dict[str, str] = {
    "AB4": "the gap where a pipe crosses a dimension is drawn by AutoCAD and seen on screen; no tool reads it back",
    "AB7": ("merging with confirm removes DUCT, and a removed layer counts as an erased object (the plug-in counts "
            "layer records), so Heron asks you to keep it erased (D-50) and the runner cannot answer"),
    "AB8": ("needs DUCT frozen in one layout viewport by hand (VP freeze), and the merge asks you about the "
            "removed layer (D-50)"),
}


CHECKS: tuple[Check, ...] = LAYERS_AB
BY_EYE: dict[str, str] = {**EYE_AB}
