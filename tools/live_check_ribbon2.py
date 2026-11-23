"""Live checks for the ribbon gaps, part 2 (group AQ): associative and path arrays, tiled viewports,
hyperlinks, DWF and the geographic location (D-110, D-111).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.

What is measured: the array refusals made before anything is built (and the model-space count
unchanged), the tiles AutoCAD built read back with a second call and judged here from their
corners, the linked objects found by the whole-drawing listing, and the geographic location read
back with ``autocad_get_geo_location`` and LATITUDE / LONGITUDE.

What is not: a finished associative array. ARRAY takes the source objects into the array, which
erases them from the drawing (the plug-in lists as ``sources_still_loose`` only the ones not
erased), so Heron's keep-erased box (D-50) would wait for an answer the runner cannot give. The
geographic location rows work in a new drawing of their own, closed again unsaved, so the scratch
drawing is never placed on the Earth and its sun keeps its place.
"""

from __future__ import annotations

from typing import Any

import live_common as lc
from live_common import (
    Check,
    Context,
    Refused,
    expect,
    near,
    near_point,
    parse,
    refusal,
)

from autocad_mcp.tools import (
    arrays,
    batch,
    draw,
    geo_location,
    hyperlinks,
    layers,
    lighting,
    model_viewports,
    settings,
)

SAME_DEGREES = 1e-6
DOHA = (25.29, 51.53)
KOCHI = (9.93, 76.27)


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _draw(*operations: dict[str, Any]) -> list[str]:
    """Draw with autocad_batch_draw; the handles, in order."""
    made = parse(await batch.autocad_batch_draw(operations=list(operations)))
    expect(made.get("created") == len(operations), f"drew {made.get('created')} of {len(operations)} test objects")
    return list(made["handles"])


# ---------------------------------------------------------------------------
# Done in AutoCAD by the runner itself, not through Heron
# ---------------------------------------------------------------------------


async def viewport_names() -> list[str]:
    """The names in the drawing's viewport table, as VPORTS > Named lists them (and *Active), each once."""
    from autocad_mcp.core.connection import get_doc, run

    def read() -> list[str]:
        viewports = get_doc().Viewports
        return sorted({str(viewports.Item(i).Name) for i in range(int(viewports.Count))})

    return await run(read)


# ---------------------------------------------------------------------------
# AQ5 - arrays refused before anything is made
# ---------------------------------------------------------------------------


async def aq5_wrong_arrays_are_refused_before_anything_is_made(ctx: Context) -> str:
    o = lc.origin("AQ5")
    model_line, item, path = await _draw(
        {"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AQ5"},
        {"type": "circle", "center": _at(o, 0, 2000), "radius": 50, "layer": "LC-AQ5"},
        {"type": "line", "start": _at(o, 0, 4000), "end": _at(o, 10000, 4000), "layer": "LC-AQ5-PATH"},
    )
    paper = parse(await draw.autocad_draw_line(start=[10, 10], end=[110, 10], layer="LC-AQ5", space="paper"))["handle"]
    before = await lc.entity_count()
    spaces = refusal(await arrays.autocad_associative_array(
        handles=[model_line, paper], pattern="rectangular", rows=1, columns=2, column_spacing=1500))
    itself = refusal(await arrays.autocad_associative_array(handles=[path], pattern="path", path=path, count=3))
    too_many = refusal(await arrays.autocad_associative_array(
        handles=[item], pattern="path", path=path, spacing=1500, count=9))
    expect("different spaces" in spaces, f"the model and layout lines were answered: {spaces[:160]}")
    expect("cannot also be one of the objects" in itself, f"the path as one of the objects was answered: {itself[:160]}")
    expect("at most 7 fit" in too_many, f"9 at 1500 on a 10 m line was answered: {too_many[:160]}")
    for said in (spaces, itself, too_many):
        expect("Nothing was changed" in said, f"a refusal does not say nothing was changed: {said[:160]}")
    after = await lc.entity_count()
    expect(after == before, f"model space went from {before} to {after} objects across the three refusals")
    return ("refused 'different spaces', 'cannot also be one of the objects' and 'at most 7 fit', each 'Nothing was "
            f"changed'; model space stayed at {before} objects. The one on a layout was drawn there, not picked by hand")


# ---------------------------------------------------------------------------
# AQ6 - tiled viewports on the Model tab
# ---------------------------------------------------------------------------

WORDS = {
    "one": "one viewport",
    "two_vertical": "two, side by side",
    "four": "four, two by two",
    "three_right": "three, the big one on the right",
}
TILES = {"one": 1, "two_vertical": 2, "four": 4, "three_right": 3}
EPS = 1e-3


def _box(tile: dict[str, Any]) -> tuple[float, float, float, float]:
    (x1, y1), (x2, y2) = tile["lower_left"][:2], tile["upper_right"][:2]
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _shape(tiles: list[dict[str, Any]]) -> str:
    """What the tiles read back look like, judged here from their corners (fractions of the screen)."""
    boxes = [_box(t) for t in tiles]
    tall = [b[1] <= EPS and b[3] >= 1 - EPS for b in boxes]
    areas = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]
    if len(boxes) == 1 and tall[0] and boxes[0][0] <= EPS and boxes[0][2] >= 1 - EPS:
        return "one"
    if len(boxes) == 2 and all(tall) and abs(areas[0] - areas[1]) <= EPS:
        return "two_vertical"
    if len(boxes) == 4 and all(abs(a - 0.25) <= EPS for a in areas):
        return "four"
    if len(boxes) == 3:
        big = max(range(3), key=lambda i: areas[i])
        rest = [b for i, b in enumerate(boxes) if i != big]
        if tall[big] and areas[big] > max(a for i, a in enumerate(areas) if i != big) + EPS \
                and all(boxes[big][0] >= r[2] - EPS for r in rest):
            return "three_right"
    return f"{len(boxes)} tiles"


def _corners(tiles: list[dict[str, Any]]) -> str:
    return "; ".join(f"{t['lower_left'][0]:g},{t['lower_left'][1]:g}-{t['upper_right'][0]:g},{t['upper_right'][1]:g}"
                     for t in tiles)


async def _tiled(layout: str | None = None) -> dict[str, Any]:
    if layout is None:
        return parse(await model_viewports.autocad_tiled_viewports())
    return parse(await model_viewports.autocad_tiled_viewports(layout=layout))


async def aq6_the_model_tab_splits_and_comes_back_to_one(ctx: Context) -> str:
    seen: dict[str, str] = {}
    restored: dict[str, Any] | None = None
    try:
        for layout in ("two_vertical", "four", "three_right"):
            out = await _tiled(layout)
            expect(not out.get("warning"), f"{layout} answered a warning: {out.get('warning')}")
            expect(not out.get("view_not_copied"), f"{layout} did not copy the view on screen: {out.get('view_not_copied')}")
            expect(out.get("arrangement") == WORDS[layout] and out.get("tiles") == TILES[layout],
                   f"{layout} answered {out.get('tiles')} tiles, '{out.get('arrangement')}'")
            back = await _tiled()
            tiles = back.get("viewports") or []
            expect(len(tiles) == TILES[layout] and back.get("tiles") == TILES[layout],
                   f"after {layout} the Model tab reads {back.get('tiles')} tiles ({len(tiles)} listed)")
            shape = _shape(tiles)
            expect(shape == layout, f"after {layout} the tiles read back as {shape}: {_corners(tiles)}")
            seen[layout] = _corners(tiles)
        names = await viewport_names()
        expect("HERON" in [n.upper() for n in names], f"the viewport table has no 'Heron' configuration: {names}")
    finally:
        restored = await _tiled("one")
    expect(restored.get("tiles") == 1 and restored.get("arrangement") == WORDS["one"] and not restored.get("warning"),
           f"back to one answered {restored.get('tiles')} tiles, '{restored.get('arrangement')}'")
    last = await _tiled()
    expect(last.get("tiles") == 1 and _shape(last.get("viewports") or []) == "one",
           f"read without a layout, the Model tab has {last.get('tiles')} tiles")
    return (f"two_vertical (acViewport2Vertical) came back side by side ({seen['two_vertical']}); four two by two; "
            f"three_right (acViewport3Right) with the big one on the right ({seen['three_right']}); then one, "
            f"read again with no layout; no warning, the view copied each time; 'Heron' is in the viewport table. "
            f"Whether each tile shows the view that was on screen was not looked at")


# ---------------------------------------------------------------------------
# AQ9 - every linked object found, one removed, a locked layer
# ---------------------------------------------------------------------------

AQ9_LINKS = ("C:\\Temp\\LC-AQ9-1.pdf", "https://www.autodesk.com", "C:\\Temp\\LC-AQ9-3.dwg")


async def _linked() -> dict[str, list[dict[str, Any]]]:
    out = parse(await hyperlinks.autocad_list_hyperlinks(limit=500))
    expect(not out.get("truncated"), f"the listing was cut short at {len(out.get('objects') or [])} of {out.get('count')}")
    return {str(r["handle"]): r.get("links") or [] for r in out.get("objects") or []}


async def aq9_the_listing_finds_exactly_the_linked_objects(ctx: Context) -> str:
    o = lc.origin("AQ9")
    baseline = set(await _linked())
    handles = await _draw(
        *({"type": "line", "start": _at(o, 0, 500 * i), "end": _at(o, 1000, 500 * i), "layer": "LC-AQ9"} for i in range(6)),
        {"type": "line", "start": _at(o, 0, 4000), "end": _at(o, 1000, 4000), "layer": "LC-AQ9-LOCKED"},
    )
    linked, plain, locked = handles[:3], handles[3:6], handles[6]
    for handle, url in zip(linked, AQ9_LINKS, strict=True):
        out = parse(await hyperlinks.autocad_hyperlinks(handles=[handle], url=url, description=f"LC-AQ9 {handle}"))
        expect(out.get("changed") == 1 and not out.get("failed"), f"linking {handle} answered {out}")
    found = await _linked()
    new = {h: links for h, links in found.items() if h not in baseline}
    expect(set(new) == set(linked), f"the listing found {sorted(new)} new, not exactly {linked}")
    for handle, url in zip(linked, AQ9_LINKS, strict=True):
        urls = [link.get("url") for link in new[handle]]
        expect(urls == [url], f"{handle} lists the links {urls}, not [{url}]")
    gone = parse(await hyperlinks.autocad_hyperlinks(handles=[linked[1]], action="remove"))
    rows = gone.get("objects") or []
    expect(gone.get("changed") == 1 and rows and rows[0].get("after") == [], f"remove answered {gone}")
    again = await _linked()
    left = {h for h in again if h not in baseline}
    expect(left == {linked[0], linked[2]}, f"after remove the listing finds {sorted(left)}, not {[linked[0], linked[2]]}")
    parse(await layers.autocad_set_layer_state(name="LC-AQ9-LOCKED", locked=True))
    try:
        out = parse(await hyperlinks.autocad_hyperlinks(handles=[locked, plain[0]], url=AQ9_LINKS[1]))
    finally:
        parse(await layers.autocad_set_layer_state(name="LC-AQ9-LOCKED", locked=False))
    failed = [f.get("handle") for f in out.get("failed") or []]
    expect(failed == [locked], f"with a locked layer, failed lists {failed}, not [{locked}]")
    expect(out.get("changed") == 1 and out.get("handles") == [plain[0]], f"the object not locked was not done: {out}")
    read = parse(await hyperlinks.autocad_list_hyperlinks(handles=[locked, plain[0]]))
    links = {str(r["handle"]): [link.get("url") for link in r.get("links") or []] for r in read.get("objects") or []}
    expect(links.get(locked) == [] and links.get(plain[0]) == [AQ9_LINKS[1]], f"read back, the links are {links}")
    reason = (out.get("failed") or [{}])[0].get("reason", "")
    return (f"the whole-drawing listing (PE_URL) found exactly the three new links of six lines ({len(baseline)} "
            f"linked before), with their addresses; after remove, two; the locked-layer line in failed "
            f"('{reason[:60]}'), the other done and read back")


# ---------------------------------------------------------------------------
# AQ11 to AQ13 - the geographic location, each in a new drawing of its own
# ---------------------------------------------------------------------------


async def _place() -> tuple[Any, Any]:
    return await lc.variable("LATITUDE"), await lc.variable("LONGITUDE")


def _at_place(read: dict[str, Any], where: tuple[float, float]) -> bool:
    return near(read.get("latitude"), where[0], SAME_DEGREES) and near(read.get("longitude"), where[1], SAME_DEGREES)


async def _new_drawing(ctx: Context, units: str | int = "millimeters") -> str:
    name = await lc.new_drawing(ctx)
    parse(await settings.autocad_drawing_setup(units=units))
    return name


async def _back(ctx: Context, name: str) -> None:
    await lc.close_drawing(ctx, name)
    await lc.activate(ctx)


async def aq11_doha_is_placed_with_north_12_degrees_right(ctx: Context) -> str:
    name = await _new_drawing(ctx)
    try:
        units = await lc.variable("INSUNITS")
        expect(units == 4, f"the new drawing's INSUNITS is {units}, not 4 (mm)")
        out = parse(await geo_location.autocad_geo_location(latitude=DOHA[0], longitude=DOHA[1], point=[0, 0], north_angle=12))
        form = out.get("reference_form")
        expect(out.get("located") is True and form in ("grid", "lon_lat"), f"the answer says located {out.get('located')}, form {form!r}")
        expect(not out.get("not_set"), f"something was not set: {out.get('not_set')}")
        read = parse(await geo_location.autocad_get_geo_location())
        expect(read.get("located") is True and _at_place(read, DOHA),
               f"read back: located {read.get('located')} at {read.get('latitude')}, {read.get('longitude')}")
        expect(near_point(read.get("point"), [0, 0, 0], 1e-6), f"the placed drawing point reads {read.get('point')}, not 0,0")
        expect(near(read.get("north_angle"), 12.0, 1e-6), f"north reads {read.get('north_angle')} degrees, not 12")
        expect(read.get("agrees") is True, f"the location and the sun's place agree: {read.get('agrees')}")
        lat, lon = await _place()
        expect(near(lat, DOHA[0], SAME_DEGREES) and near(lon, DOHA[1], SAME_DEGREES), f"LATITUDE / LONGITUDE read {lat} / {lon}")
    finally:
        await _back(ctx, name)
    return (f"located, reference_form '{form}', system {read.get('coordinate_system')}; read back at 25.29, 51.53, "
            f"point 0,0, north 12 degrees, agrees true; LATITUDE / LONGITUDE {lat} / {lon}. Not tried: the "
            f"GEOGRAPHICLOCATION marker, GEOMAP AERIAL (sign-in) and a 10 m line measured on the map")


async def aq12_an_unplaced_drawing_asks_then_takes_the_suns_place(ctx: Context) -> str:
    name = await _new_drawing(ctx)
    try:
        lat, lon = await _place()
        if not geo_location.is_autocad_default(lat, lon):
            raise Refused(f"not run this time: the new drawing is already at {lat}, {lon}, not AutoCAD's San Francisco")
        first = parse(await geo_location.autocad_get_geo_location())
        expect(first.get("located") is False, f"the new drawing reads located {first.get('located')}")
        said = refusal(await geo_location.autocad_geo_location())
        expect("San Francisco" in said and "Nothing was changed" in said, f"with no place it answered: {said[:160]}")
        still = parse(await geo_location.autocad_get_geo_location())
        expect(still.get("located") is False, "the refused call placed the drawing after all")
        parse(await lighting.autocad_set_sun(latitude=KOCHI[0], longitude=KOCHI[1]))
        lat, lon = await _place()
        expect(near(lat, KOCHI[0], SAME_DEGREES) and near(lon, KOCHI[1], SAME_DEGREES), f"after set_sun the place reads {lat} / {lon}")
        out = parse(await geo_location.autocad_geo_location(point=[1000, 2000]))
        sun = out.get("sun_place") or {}
        expect(out.get("located") is True and sun.get("moved") is False, f"located {out.get('located')}, sun moved {sun.get('moved')}")
        read = parse(await geo_location.autocad_get_geo_location())
        expect(read.get("located") is True and _at_place(read, KOCHI),
               f"read back at {read.get('latitude')}, {read.get('longitude')}, not Kochi 9.93, 76.27")
        expect(near_point(read.get("point"), [1000, 2000, 0], 1e-6), f"the placed point reads {read.get('point')}, not 1000,2000")
        expect(read.get("agrees") is True, f"agrees reads {read.get('agrees')}")
        after = await _place()
        expect(near(after[0], KOCHI[0], SAME_DEGREES) and near(after[1], KOCHI[1], SAME_DEGREES),
               f"the sun's place moved to {after[0]} / {after[1]}")
    finally:
        await _back(ctx, name)
    return ("a new drawing (at San Francisco, not located): refused, San Francisco named, still not located; after "
            "set_sun Kochi, located at 9.93, 76.27 with 1000,2000 placed, agrees true, the sun not moved "
            f"(LATITUDE / LONGITUDE {after[0]} / {after[1]})")


async def aq13_no_units_and_an_unknown_system_are_refused_and_remove_works(ctx: Context) -> str:
    name = await _new_drawing(ctx, units=0)
    try:
        units = await lc.variable("INSUNITS")
        expect(units == 0, f"INSUNITS reads {units}, not 0")
        no_units = refusal(await geo_location.autocad_geo_location(latitude=DOHA[0], longitude=DOHA[1]))
        expect("no units" in no_units and "Nothing was changed" in no_units, f"with INSUNITS 0 it answered: {no_units[:160]}")
        expect(parse(await geo_location.autocad_get_geo_location()).get("located") is False, "the refused call placed the drawing")
        parse(await settings.autocad_drawing_setup(units="millimeters"))
        units = await lc.variable("INSUNITS")
        expect(units == 4, f"INSUNITS reads {units} after setting mm")
        out = parse(await geo_location.autocad_geo_location(latitude=DOHA[0], longitude=DOHA[1], coordinate_system="UTM84-39N"))
        expect(out.get("located") is True, f"UTM84-39N answered located {out.get('located')}")
        utm = parse(await geo_location.autocad_get_geo_location())
        expect(utm.get("located") is True and _at_place(utm, DOHA) and str(utm.get("coordinate_system")).upper() == "UTM84-39N",
               f"read back: {utm.get('coordinate_system')} at {utm.get('latitude')}, {utm.get('longitude')}")
        unknown = refusal(await geo_location.autocad_geo_location(latitude=DOHA[0], longitude=DOHA[1],
                                                                  coordinate_system="NOT-A-SYSTEM"))
        expect("NOT-A-SYSTEM" in unknown and "Nothing was changed" in unknown, f"the unknown code was answered: {unknown[:160]}")
        kept = parse(await geo_location.autocad_get_geo_location())
        same = {k: (utm.get(k), kept.get(k)) for k in ("coordinate_system", "latitude", "longitude", "point", "north_angle")
                if utm.get(k) != kept.get(k)}
        expect(not same, f"the refused code changed the location: {same}")
        gone = parse(await geo_location.autocad_geo_location(action="remove"))
        expect(gone.get("removed") is True, f"remove answered {gone}")
        final = parse(await geo_location.autocad_get_geo_location())
        expect(final.get("located") is False, f"after remove the drawing reads located {final.get('located')}")
    finally:
        await _back(ctx, name)
    return (f"INSUNITS 0 refused 'no units'; mm with UTM84-39N located at 25.29, 51.53 (form {out.get('reference_form')}); "
            "'NOT-A-SYSTEM' refused with the location unchanged; remove left it not located. Not tried: the "
            "GEOGRAPHICLOCATION dialog and the one Ctrl+Z that brings it back")


CHECKS: tuple[Check, ...] = (
    Check("AQ5", "AQ", "wrong arrays are refused before anything is made",
          aq5_wrong_arrays_are_refused_before_anything_is_made),
    Check("AQ6", "AQ", "the Model tab splits and comes back to one", aq6_the_model_tab_splits_and_comes_back_to_one),
    Check("AQ9", "AQ", "the listing finds exactly the linked objects", aq9_the_listing_finds_exactly_the_linked_objects),
    Check("AQ11", "AQ", "Doha is placed with north 12 degrees right", aq11_doha_is_placed_with_north_12_degrees_right),
    Check("AQ12", "AQ", "an unplaced drawing asks, then takes the sun's place",
          aq12_an_unplaced_drawing_asks_then_takes_the_suns_place),
    Check("AQ13", "AQ", "no units and an unknown system are refused, remove works",
          aq13_no_units_and_an_unknown_system_are_refused_and_remove_works),
)

_ARRAY_ERASES = ("making the array takes the source objects into it, which erases them, so Heron asks you to keep "
                 "the change or undo the whole change (D-140) and the runner cannot answer")

BY_EYE: dict[str, str] = {
    "AQ1": _ARRAY_ERASES + "; the ARRAY tab and a stretched path are seen on screen too",
    "AQ2": _ARRAY_ERASES + "; the comparison with ARRAYPATH is by hand",
    "AQ3": _ARRAY_ERASES + "; ARRAYEDIT is used by hand",
    "AQ4": _ARRAY_ERASES,
    "AQ7": "needs a sheet tab made active by hand, and Changes off, which the runner never sets",
    "AQ8": "the hover text and Ctrl+click opening the PDF are seen and clicked on screen",
    "AQ10": "the DWF is opened in Autodesk Viewer and compared with the PDF by eye, on a sheet tab made active "
            "by hand; the refusal half needs Publish off",
    "AQ14": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
    "AQ15": "a line drawn by hand, then Ctrl+Z pressed by hand twice and GEOGRAPHICLOCATION looked at (D-143)",
    "AQ16": "the palette's Undo is clicked by hand, and the split is seen on screen (D-143)",
    "AQ17": "a line drawn by hand and the Quick Access Undo drop-down read by eye (D-143)",
}
