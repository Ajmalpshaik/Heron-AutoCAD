"""Live checks for setting a render up (group AE): the visual style read back,
camera views, the sun, the lights and the exposure.

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
None of Heron's tools renders (D-87), so no row here presses Render: where the
register says "Ajmal renders", the evidence says that part was not tried. What a
row measures instead is AutoCAD's own read-back: LENSLENGTH, PERSPECTIVE and
VIEWDIR for a camera, LATITUDE, LONGITUDE, TIMEZONE and SUNSTATUS for the sun,
the views AutoCAD lists, and each light's on / off as the plug-in lists it.

"One Ctrl+Z" is tried with Heron's own autocad_undo_last. With Ask to Keep off
there is no UNDO mark, so it sends UNDO 1: the step one Ctrl+Z takes back.

A few things the modeller does by hand (an orbit, VSCURRENT typed at the command
line, VIEW Restore) go through ``by_hand_command`` below, which types straight
into AutoCAD without Heron.
"""

from __future__ import annotations

import math
import re
import time
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near, parse, refusal

from autocad_mcp.tools import (
    activity,
    advanced,
    document,
    layers,
    lighting,
    solids,
    views,
)

# How long a command typed by hand gets to finish before it counts as hanging.
HAND_WAIT_S = 5.0

# The ten styles autocad_set_3d_view takes, in the order AE1 tries them.
STYLES: tuple[str, ...] = tuple(solids.VISUAL_STYLES)

# AutoCAD's own lens maths for a 24 mm lens on a 36 mm frame (D-86).
FIELD_24MM = math.degrees(2 * math.atan(18.0 / 24.0))  # 73.74 degrees


# ---------------------------------------------------------------------------
# Done in AutoCAD by hand, not through Heron
# ---------------------------------------------------------------------------


async def by_hand_command(text: str) -> None:
    """Type a command as the modeller types it at the command line (not through Heron), and wait for it.

    Still in the command after HAND_WAIT_S means it is waiting at a prompt or hung:
    it is cancelled with Esc and the row fails, saying so.
    """
    from autocad_mcp.core.connection import get_doc, run

    def type_it() -> None:
        doc = get_doc()
        doc.SendCommand(text)
        deadline = time.monotonic() + HAND_WAIT_S
        while int(doc.GetVariable("CMDACTIVE") or 0):
            if time.monotonic() >= deadline:
                doc.SendCommand("\x1b\x1b")
                raise lc.Failed(
                    f"AutoCAD was still in '{text.strip()}' after {HAND_WAIT_S:g} s (a prompt open, or hung); "
                    "the runner pressed Esc"
                )
            time.sleep(0.1)

    await run(type_it)


# ---------------------------------------------------------------------------
# Small readers
# ---------------------------------------------------------------------------


def _at(o: tuple[float, float], x: float, y: float, z: float) -> list[float]:
    return [o[0] + x, o[1] + y, z]


def _unit(v: Any) -> list[float]:
    values = [float(c) for c in v[:3]]
    size = math.sqrt(sum(c * c for c in values))
    return [c / size for c in values] if size > 0 else values


def _same_way(a: Any, b: Any, tol: float = 1e-5) -> bool:
    """Two directions the same, whatever their lengths."""
    if not a or not b or len(a) < 3 or len(b) < 3:
        return False
    return all(abs(x - y) <= tol for x, y in zip(_unit(a), _unit(b), strict=True))


def _way(eye: list[float], target: list[float]) -> list[float]:
    """The direction AutoCAD keeps for a view: from the target to the eye."""
    return [e - t for e, t in zip(eye, target, strict=True)]


def _short(v: Any) -> str:
    return ",".join(f"{c:.3f}" for c in _unit(v))


def _same(a: Any, b: Any) -> bool:
    """Two variable values the same: numbers to 1e-6, anything else exactly."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return near(a, b, 1e-6)
    return a == b


def _erased(out: dict[str, Any]) -> int:
    """How many objects the plug-in counted as erased in a change (0 when it did not count)."""
    return int((out.get("heron_changes") or {}).get("erased") or 0)


def _no_erase_box(out: dict[str, Any], what: str) -> None:
    erased = _erased(out)
    expect(erased == 0,
           f"{what} erased {erased} object(s), so Heron showed its 'keep them erased?' box (D-50); "
           "a render set-up should erase nothing")


async def _views() -> dict[str, dict[str, Any]]:
    listed = parse(await views.autocad_list_views())
    return {str(v.get("name", "")).lower(): v for v in listed.get("views") or []}


async def _lights() -> dict[str, Any]:
    return parse(await lighting.autocad_list_lights())


async def _light(handle: str) -> dict[str, Any]:
    listed = await _lights()
    found = [row for row in listed.get("lights") or [] if row.get("handle") == handle]
    expect(found, f"autocad_list_lights does not list the light {handle}")
    return found[0]


async def _sun() -> dict[str, Any]:
    return (await _lights()).get("sun") or {}


async def _undo() -> dict[str, Any]:
    """Heron's undo of its own last change: UNDO 1 here (Ask to Keep is off), the step one Ctrl+Z takes."""
    return parse(await activity.autocad_undo_last())


async def _camera_on_screen(eye: list[float], target: list[float], lens: float, where: str) -> str:
    """The screen is the camera: PERSPECTIVE 1, LENSLENGTH the lens, VIEWDIR from the target to the eye."""
    perspective = await lc.variable("PERSPECTIVE")
    lens_now = await lc.variable("LENSLENGTH")
    viewdir = await lc.variable("VIEWDIR")
    expect(int(perspective or 0) == 1, f"{where}: PERSPECTIVE reads {perspective}, not 1")
    expect(near(lens_now, lens, 1e-3), f"{where}: LENSLENGTH reads {lens_now}, not {lens:g}")
    expect(_same_way(viewdir, _way(eye, target)),
           f"{where}: VIEWDIR points {_short(viewdir)}, not {_short(_way(eye, target))} (target to eye)")
    return f"PERSPECTIVE 1, LENSLENGTH {float(lens_now):g}, VIEWDIR along target-to-eye"


# ---------------------------------------------------------------------------
# Group AE - setting a render up
# ---------------------------------------------------------------------------


async def ae1_each_visual_style_reads_back_as_set(ctx: Context) -> str:
    names: list[str] = []
    before: str | None = None
    for style in STYLES:
        out = parse(await solids.autocad_set_3d_view(visual_style=style, zoom_extents=False))
        found = out.get("visual_style_found")
        expect(not out.get("not_set"), f"'{style}' was not set: {out.get('not_set')}")
        behind = " (that is the style before it: the read lags one behind)" if found and found == before else ""
        expect(found is not None and solids.style_key(found) == style,
               f"asked for '{style}', the viewport reads {found!r}{behind}. "
               f"{out.get('visual_style_note') or ''}".strip())
        expect(not out.get("visual_style_warning"), f"'{style}' came with a warning: {out.get('visual_style_warning')}")
        expect(not out.get("visual_style_found_from"),
               f"'{style}' was read from {out.get('visual_style_found_from')}, not the live view")
        names.append(str(found))
        before = found
    await by_hand_command("_.VSCURRENT _Hidden\n")
    out = parse(await solids.autocad_set_3d_view(direction="sw_iso", zoom_extents=False))
    found = out.get("visual_style_found")
    expect(found is not None and solids.style_key(found) == "hidden",
           f"after VSCURRENT Hidden typed by hand, the next view change reads {found!r}, not Hidden")
    return (f"all ten read back as set, no warning, from the live view; AutoCAD's names: {', '.join(names)}. "
            f"After VSCURRENT Hidden typed by hand, sw_iso reads {found}. The screen itself was not looked at")


async def ae2_a_camera_view_is_saved_in_perspective_at_24mm(ctx: Context) -> str:
    o = lc.origin("AE2")
    name = "LC-AE2-LIVING-CAM-1"
    eye, target = _at(o, 300, 300, 1600), _at(o, 6000, 4000, 1200)
    parse(await solids.autocad_set_3d_view(direction="top", visual_style="2dwireframe", zoom_extents=False))

    async def add() -> dict[str, Any]:
        out = parse(await views.autocad_add_camera_view(name=name, eye=eye, target=target, lens=24))
        expect(out.get("created") is True, f"the camera view was not made: {out}")
        expect(out.get("perspective") is True and near(out.get("lens_mm"), 24.0, 1e-3),
               f"the answer says perspective {out.get('perspective')}, lens {out.get('lens_mm')}")
        expect(out.get("in_drawing") is True, f"the view is not in the drawing's views: {out.get('warning')}")
        expect("2D Wireframe" in str(out.get("warning") or ""),
               f"in 2D Wireframe the answer did not warn that perspective will not show: {out.get('warning')}")
        return out

    out = await add()
    field = out.get("field_of_view_degrees")
    expect(near(field, FIELD_24MM, 0.01), f"field_of_view_degrees is {field}, not {FIELD_24MM:.2f}")
    listed = (await _views()).get(name.lower())
    expect(listed is not None, f"autocad_list_views does not list {name}")
    expect(_same_way(listed.get("direction"), _way(eye, target)),
           f"the saved view looks along {listed.get('direction')}, not from the eye to the target")
    await _undo()
    expect(name.lower() not in await _views(), f"one undo step did not remove {name}")
    await add()
    parse(await solids.autocad_set_3d_view(visual_style="realistic", zoom_extents=False))
    seen = await _camera_on_screen(eye, target, 24.0, "after visual_style='realistic'")
    return (f"{name} saved and listed as a view looking from the corner to the far wall, field_of_view_degrees "
            f"{field}; in 2D Wireframe the answer warned; one undo step removed it, and once made again and "
            f"switched to Realistic the screen reads {seen}. AutoCAD's own Field of view and the room on "
            "screen were not looked at (no room is drawn)")


async def ae3_a_camera_view_comes_back_at_its_lens(ctx: Context) -> str:
    o = lc.origin("AE3")
    name = "LC-AE3-CAM-1"
    eye, target = _at(o, 300, 300, 1600), _at(o, 6000, 4000, 1200)
    parse(await solids.autocad_set_3d_view(visual_style="realistic", zoom_extents=False))
    out = parse(await views.autocad_add_camera_view(name=name, eye=eye, target=target, lens=24))
    expect(out.get("created") is True, f"the camera view was not made: {out}")
    parse(await solids.autocad_set_3d_view(direction="sw_iso", zoom_extents=False))
    parse(await document.autocad_zoom(mode="extents"))
    away = await lc.variable("VIEWDIR")
    expect(not _same_way(away, _way(eye, target)), "the view did not move away from the camera before the restore")
    await by_hand_command(f"_.-VIEW _Restore {name}\n")
    seen = await _camera_on_screen(eye, target, 24.0, f"after VIEW Restore {name}")
    return (f"zoomed and turned away (VIEWDIR {_short(away)}), then VIEW Restore {name} typed by hand finished "
            f"with no prompt left open: {seen}")


async def ae4_a_camera_name_is_refused_then_moved_then_saved_off_screen(ctx: Context) -> str:
    o = lc.origin("AE4")
    name, other = "LC-AE4-CAM-1", "LC-AE4-CAM-2"
    first, moved, third = _at(o, 300, 300, 1600), _at(o, 1500, 300, 1600), _at(o, 300, 3000, 1800)
    target = _at(o, 6000, 4000, 1200)
    parse(await views.autocad_add_camera_view(name=name, eye=first, target=target, lens=24, look_through=False))
    message = refusal(await views.autocad_add_camera_view(name=name, eye=first, target=target, lens=24))
    expect("replace=true" in message, f"the same name was refused without naming replace: {message[:160]}")
    out = parse(await views.autocad_add_camera_view(name=name, eye=moved, target=target, lens=24, replace=True))
    expect(out.get("replaced") is True, f"replace=true did not say replaced: {out}")
    _no_erase_box(out, "replace=true")
    listed = await _views()
    expect(_same_way((listed.get(name.lower()) or {}).get("direction"), _way(moved, target)),
           f"{name} still looks from the old eye: {(listed.get(name.lower()) or {}).get('direction')}")
    expect(sum(1 for key in listed if key == name.lower()) == 1, f"there are two views called {name}")
    screen = await lc.variable("VIEWDIR")
    out = parse(await views.autocad_add_camera_view(name=other, eye=third, target=target, lens=24, look_through=False))
    expect(out.get("created") is True and out.get("on_screen") is False,
           f"look_through=false answered created {out.get('created')}, on_screen {out.get('on_screen')}")
    expect(other.lower() in await _views(), f"autocad_list_views does not list {other}")
    after = await lc.variable("VIEWDIR")
    expect(_same_way(after, screen), f"look_through=false moved the screen: VIEWDIR {_short(screen)} -> {_short(after)}")
    return (f"the same name was refused naming replace=true; replace=true moved {name} to the new eye with "
            f"nothing erased; {other} was saved with the screen left as it was (VIEWDIR unchanged). "
            "Rendering it from the Render window was not tried: Heron does not render")


async def ae5_the_sun_is_set_for_doha_and_reads_back(ctx: Context) -> str:
    place = ("LATITUDE", "LONGITUDE", "TIMEZONE", "SUNSTATUS")
    before = {n: await lc.variable(n) for n in place}
    sun_before = (await _sun()).get("date")
    asked = {"date": "2026-06-21", "time": "10:00", "latitude": 25.29, "longitude": 51.53,
             "utc_offset": 3, "daylight_saving": False, "on": True}
    out = parse(await lighting.autocad_set_sun(**asked))
    _no_erase_box(out, "set_sun")
    expect(not out.get("not_set"), f"AutoCAD did not take {out.get('not_set')}")
    sun = out.get("sun") or {}
    expect(sun.get("date") == "2026-06-21" and str(sun.get("time", "")).startswith("10:00"),
           f"the sun reads {sun.get('date')} {sun.get('time')}, not 2026-06-21 10:00")
    expect(sun.get("daylight_saving") is False, f"daylight saving reads {sun.get('daylight_saving')}")
    dxf = sun.get("dxf") or {}
    expect(dxf.get("91_julian_day") == 2461213 and dxf.get("92_ms_after_midnight") == 36000000,
           f"the answer's dxf is {dxf}, not 91 = 2461213 and 92 = 36000000")
    now = {n: await lc.variable(n) for n in place}
    want = {"LATITUDE": 25.29, "LONGITUDE": 51.53, "TIMEZONE": 3000, "SUNSTATUS": 1}
    wrong = {n: now[n] for n, v in want.items() if not _same(now[n], v)}
    expect(not wrong, f"AutoCAD reads {wrong} after set_sun, not {want}")
    listed = await _sun()
    expect(listed.get("date") == "2026-06-21" and str(listed.get("time", "")).startswith("10:00"),
           f"autocad_list_lights reads the sun as {listed.get('date')} {listed.get('time')}")
    azimuth, altitude = float(sun.get("azimuth") or 0.0), float(sun.get("altitude") or 0.0)
    # At 10:00 in Doha on 21 June the sun is about 60 degrees up: under 1.6 can only be radians.
    unit = "degrees" if abs(altitude) > math.pi / 2 or abs(azimuth) > 2 * math.pi else "radians"
    await _undo()
    back = {n: await lc.variable(n) for n in place}
    stuck = {n: back[n] for n in place if not _same(back[n], before[n])}
    expect(not stuck, f"after one undo step {stuck} did not go back to {({n: before[n] for n in stuck})}")
    sun_back = (await _sun()).get("date")
    expect(sun_back == sun_before, f"after one undo step the sun's date is {sun_back or 'no sun'}, not "
           f"{sun_before or 'no sun'} as before")
    said = (f"21/06/2026 10:00, no daylight saving, LATITUDE 25.29, LONGITUDE 51.53, TIMEZONE 3000, SUNSTATUS 1, "
            f"read back by AutoCAD and the plug-in; dxf 2461213 / 36000000; azimuth {azimuth:g} and altitude "
            f"{altitude:g} look like {unit}; one undo step took back the date, the place and SUNSTATUS together")
    if ctx.padlocks.get("admin") is not True:
        return said + ". The (entget) of groups 91 / 92 was not tried: it needs Admin. Sun Properties was not looked at"
    parse(await lighting.autocad_set_sun(**asked))
    groups = await _sun_groups()
    expect(groups == [2461213, 36000000], f"(entget) of the viewport's sun gives 91 / 92 = {groups}, not 2461213 / 36000000")
    return said + "; set again, (entget) of the viewport's sun gives 91 = 2461213, 92 = 36000000. Sun Properties was not looked at"


SUN_GROUPS = (
    '((lambda (e) (list (cdr (assoc 91 e)) (cdr (assoc 92 e)))) '
    '(entget (cdr (assoc 361 (entget (tblobjname "VPORT" "*Active"))))))'
)


async def _sun_groups() -> list[int]:
    """Groups 91 and 92 of the active viewport's SUN object, read with AutoLISP (Admin)."""
    out = parse(await advanced.autocad_run_lisp(expression=SUN_GROUPS))
    expect(not out.get("timed_out"), f"the (entget) of the sun did not answer: {out}")
    return [int(v) for v in re.findall(r"-?\d+", str(out.get("result", "")))]


async def ae6_a_new_time_keeps_the_date_the_place_and_the_view(ctx: Context) -> str:
    turned = [1.0, -2.0, 0.5]
    parse(await solids.autocad_set_3d_view(direction="top", visual_style="realistic", zoom_extents=False))
    await by_hand_command("PERSPECTIVE 0\n")
    parse(await lighting.autocad_set_sun(date="2026-06-21", time="10:00", latitude=25.29, longitude=51.53,
                                         utc_offset=3, on=True))
    await by_hand_command("_.VPOINT 1,-2,0.5\n")
    orbit = await lc.variable("VIEWDIR")
    expect(_same_way(orbit, turned), f"the orbit by hand did not take: VIEWDIR {_short(orbit)}")
    out = parse(await lighting.autocad_set_sun(time="16:30"))
    _no_erase_box(out, "set_sun")
    expect(out.get("set") == ["sun date and time"], f"set_sun(time) set {out.get('set')}, not only the time")
    after = await lc.variable("VIEWDIR")
    expect(_same_way(after, turned), f"the view jumped: VIEWDIR {_short(orbit)} before, {_short(after)} after")
    sun = await _sun()
    expect(sun.get("date") == "2026-06-21" and str(sun.get("time", "")).startswith("16:30"),
           f"the sun reads {sun.get('date')} {sun.get('time')}, not 2026-06-21 16:30")
    place = {n: await lc.variable(n) for n in ("LATITUDE", "LONGITUDE", "TIMEZONE")}
    expect(near(place["LATITUDE"], 25.29, 1e-6) and near(place["LONGITUDE"], 51.53, 1e-6) and place["TIMEZONE"] == 3000,
           f"the place moved: {place}")
    return ("after an orbit by hand (VPOINT 1,-2,0.5), time 16:30 changed only the time: the date stays "
            "2026-06-21, the place 25.29 / 51.53 / 3000, and VIEWDIR is still the orbit's. The shadows were "
            "not looked at")


async def ae7_a_drawing_with_no_sun_gets_one(ctx: Context) -> str:
    await lc.other_drawing(ctx, "AE7", "never-had-a-sun.dwg")
    first = await _sun()
    expect("date" not in first, f"the new drawing already has a sun dated {first.get('date')}")
    out = parse(await lighting.autocad_set_sun(date="2026-12-21", time="09:00"))
    _no_erase_box(out, "set_sun")
    expect(out.get("sun_made") is True, f"sun_made is {out.get('sun_made')}, not true")
    dxf = (out.get("sun") or {}).get("dxf") or {}
    expect(dxf.get("91_julian_day") == 2461396 and dxf.get("92_ms_after_midnight") == 32400000,
           f"the answer's dxf is {dxf}, not 2461396 / 32400000")
    sun = await _sun()
    expect(sun.get("date") == "2026-12-21" and str(sun.get("time", "")).startswith("09:00"),
           f"autocad_list_lights reads the sun as {sun.get('date')} {sun.get('time')}")
    await _undo()
    gone = await _sun()
    expect(gone.get("date") != "2026-12-21", f"after one undo step the sun is still dated {gone.get('date')}")
    await lc.activate(ctx)
    return ("in a new drawing with no sun: sun_made true, 21/12/2026 09:00 read back (dxf 2461396 / 32400000); "
            f"one undo step took the date back ({gone.get('date') or 'no sun'}). No place was set in that call. "
            "Sun Properties was not looked at")


async def ae8_india_and_nepal_time_zones(ctx: Context) -> str:
    found: list[str] = []
    for offset, code, extra in ((5.5, 5030, {"latitude": 9.93, "longitude": 76.27}), (5.75, 5045, {})):
        out = parse(await lighting.autocad_set_sun(utc_offset=offset, **extra))
        _no_erase_box(out, "set_sun")
        zone = await lc.variable("TIMEZONE")
        listed = any(str(item).startswith("TIMEZONE") for item in out.get("not_set") or [])
        if listed:
            expect(zone != code, f"TIMEZONE is in not_set, yet it reads {zone}")
            found.append(f"{code} refused by AutoCAD, in not_set ({zone} kept)")
        else:
            expect(zone == code, f"utc_offset {offset:g} reads TIMEZONE {zone}, not {code}, and not_set says nothing")
            found.append(f"{offset:g} reads {code}")
    lat, lon = await lc.variable("LATITUDE"), await lc.variable("LONGITUDE")
    expect(near(lat, 9.93, 1e-6) and near(lon, 76.27, 1e-6), f"Kochi reads {lat}, {lon}, not 9.93, 76.27")
    return (f"Kochi 9.93 / 76.27; {'; '.join(found)}. Which time zone Geographic Location names was not looked at")


async def ae10_a_light_switches_off_back_on_and_a_wrong_name_is_refused(ctx: Context) -> str:
    o = lc.origin("AE10")
    name = "LC-AE10-LIGHT"
    made = parse(await lighting.autocad_add_light(position=_at(o, 0, 0, 2400), intensity=800, intensity_unit="lm",
                                                  name=name, layer="LC-AE10"))
    handle = made["handle"]
    expect((await _light(handle)).get("on") is True, f"{name} is not on once made")
    out = parse(await lighting.autocad_switch_lights(turn_off=[name]))
    expect(out.get("changed") == 1, f"the switch changed {out.get('changed')} lights, not 1")
    expect((await _light(handle)).get("on") is False, f"{name} still lists as on after turn_off")
    await _undo()
    expect((await _light(handle)).get("on") is True, f"one undo step did not switch {name} back on")
    parse(await lighting.autocad_switch_lights(turn_off=[name]))
    message = refusal(await lighting.autocad_switch_lights(turn_on=["NO-SUCH-LIGHT", name]))
    expect("NO-SUCH-LIGHT" in message and "The lights are" in message,
           f"the wrong name was not refused with the list of lights: {message[:160]}")
    expect((await _light(handle)).get("on") is False, f"{name} came on although the switch was refused")
    return (f"{name} lists off after turn_off, and on again after one undo step; turn_on with NO-SUCH-LIGHT was "
            f"refused listing the lights, and {name} stayed off. The room going darker was not looked at")


async def ae13_a_light_on_a_locked_layer_is_not_switched(ctx: Context) -> str:
    o = lc.origin("AE13")
    name, layer = "LC-AE13-LIGHT", "LC-AE13-LIGHTS"
    made = parse(await lighting.autocad_add_light(position=_at(o, 0, 0, 2400), intensity=800, intensity_unit="lm",
                                                  name=name, layer=layer))
    handle = made["handle"]
    parse(await layers.autocad_set_layer_state(name=layer, locked=True))
    try:
        message = refusal(await lighting.autocad_switch_lights(turn_off=[name]))
        expect("locked layer" in message, f"the switch was refused for another reason: {message[:160]}")
        expect((await _light(handle)).get("on") is True, f"{name} went off although the switch was refused")
    finally:
        await layers.autocad_set_layer_state(name=layer, locked=False)
        # The last row of the group: back to plan and 2D Wireframe for the rows after it.
        await solids.autocad_set_3d_view(direction="top", visual_style="2dwireframe")
    return f"with {layer} locked, switching {name} off was refused (locked layer) and it stays on"


RENDER_AE: tuple[Check, ...] = (
    Check("AE1", "AE", "each visual style reads back as set", ae1_each_visual_style_reads_back_as_set),
    Check("AE2", "AE", "a camera view is saved in perspective at 24 mm",
          ae2_a_camera_view_is_saved_in_perspective_at_24mm),
    Check("AE3", "AE", "a camera view comes back at its lens", ae3_a_camera_view_comes_back_at_its_lens),
    Check("AE4", "AE", "a camera name is refused, moved, saved off screen",
          ae4_a_camera_name_is_refused_then_moved_then_saved_off_screen),
    # AE7 makes its own new drawing; it runs before AE5, the first row to give the scratch drawing a sun.
    Check("AE7", "AE", "a drawing with no sun gets one", ae7_a_drawing_with_no_sun_gets_one),
    Check("AE5", "AE", "the sun is set for Doha and reads back", ae5_the_sun_is_set_for_doha_and_reads_back),
    Check("AE6", "AE", "a new time keeps the date, place and view",
          ae6_a_new_time_keeps_the_date_the_place_and_the_view),
    Check("AE8", "AE", "India and Nepal time zones read back", ae8_india_and_nepal_time_zones),
    Check("AE10", "AE", "a light switches off, back on, a wrong name is refused",
          ae10_a_light_switches_off_back_on_and_a_wrong_name_is_refused),
    Check("AE13", "AE", "a light on a locked layer is not switched", ae13_a_light_on_a_locked_layer_is_not_switched),
)

EYE_AE: dict[str, str] = {
    "AE9": "needs the villa model with its light block, compared by eye with the Lights in Model palette",
    "AE11": "needs a light block, and every insert going dark is seen on screen and in BEDIT",
    "AE12": "records which viewport lighting question AutoCAD shows; a person must watch for it, and may have to answer it",
    "AE14": "whether a render comes out brighter and cooler is judged by eye after Ajmal presses Render",
    "AE15": "needs AutoCAD 2025 / 2026 and 2021-2024 machines, which are not here",
}


CHECKS: tuple[Check, ...] = RENDER_AE
BY_EYE: dict[str, str] = {**EYE_AE}
