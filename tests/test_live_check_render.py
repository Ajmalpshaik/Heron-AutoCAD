"""The AE live checks judge right: PASS on a good recorded answer, FAIL on a bad one.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py), and the commands the runner types by hand
(``by_hand_command``) are taken as typed. That proves the judging and the
arguments, not AutoCAD; only a live run does that.
"""

from __future__ import annotations

import json
import math

import pytest
from live_fakes import load, play, seq

render = load("live_check_render")
lc = load("live_common")


@pytest.fixture(autouse=True)
def typed(monkeypatch) -> list[str]:
    """What the checks type at AutoCAD's command line by hand: taken, and kept to look at."""
    commands: list[str] = []

    async def fake(text: str) -> None:
        commands.append(text)

    monkeypatch.setattr(render, "by_hand_command", fake)
    return commands


def P(row: str, x: float, y: float, z: float) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y, z]


def way(eye: list[float], target: list[float]) -> list[float]:
    return [e - t for e, t in zip(eye, target, strict=True)]


def done(payload: dict, line: str = "DONE - no drawing object was added, changed or erased.") -> str:
    """A change job's answer as the gate gives it: the plain line, then the JSON."""
    return f"{line}\n\n{json.dumps(payload)}"


def refused(message: str) -> str:
    return f"REFUSED - the tool turned the job down; nothing was changed.\n\nError: {message} Nothing was changed."


class Steps(list):
    """Successive values of one variable, one per read."""


# Recorded answers that keep a place between calls; each test starts them again.
STATEFUL: list = []


def restart() -> None:
    for answer in STATEFUL:
        answer.reset()


@pytest.fixture(autouse=True)
def fresh():
    restart()


class variables:  # noqa: N801 - read as a recording, like seq()
    """autocad_get_variable worked out from the name; a Steps value gives one per read, in order."""

    def __init__(self, **values):
        self.values = values
        self.reset()
        STATEFUL.append(self)

    def reset(self) -> None:
        self.left = {k: list(v) for k, v in self.values.items() if isinstance(v, Steps)}

    def __call__(self, name: str) -> dict:
        if name in self.left:
            assert self.left[name], f"{name} was read more often than the recording has values for"
            return {"name": name, "value": self.left[name].pop(0)}
        return {"name": name, "value": self.values[name]}


NAMES = {
    "2dwireframe": "2dWireframe", "wireframe": "Wireframe", "hidden": "Hidden", "realistic": "Realistic",
    "conceptual": "Conceptual", "shaded": "Shaded", "shaded with edges": "Shaded with edges",
    "shades of gray": "Shades of Gray", "sketchy": "Sketchy", "x-ray": "X-Ray",
}


def view3d(**kw) -> dict:
    """autocad_set_3d_view: the style asked for reads back; a direction alone reads Hidden (AE1's hand change)."""
    style = kw.get("visual_style")
    return {"named": kw.get("direction"), "visual_style": style, "visual_style_found": NAMES.get(style, "Hidden"),
            "zoomed": kw.get("zoom_extents", True)}


class lagging:  # noqa: N801 - read as a recording, like seq()
    """A read-back one style behind the screen: what AE1 must catch."""

    def __init__(self):
        self.reset()
        STATEFUL.append(self)

    def reset(self) -> None:
        self.shown = "2dWireframe"

    def __call__(self, **kw) -> dict:
        style, found = kw.get("visual_style"), self.shown
        if style:
            self.shown = NAMES[style]
        return {"named": kw.get("direction"), "visual_style": style, "visual_style_found": found, "zoomed": False}


def camera(name: str, eye: list[float], target: list[float], *, created: bool = True, on_screen: bool = True,
           warning: str | None = None, erased: int = 0) -> str:
    payload = {
        "created" if created else "replaced": True, "name": name, "handle": "2F1", "eye": eye, "target": target,
        "lens_mm": 24.0, "perspective": True, "field_of_view_degrees": 73.74,
        "distance": round(math.dist(eye, target), 6), "view_width": 9000.0, "view_height": 5400.0,
        "on_screen": on_screen, "in_drawing": True,
        "note": "This does not render: press Render in AutoCAD with this view on screen.",
        "heron_changes": {"added": 0, "modified": 0, "erased": erased},
    }
    if warning:
        payload["warning"] = warning
    return done(payload)


def listed_views(*rows: tuple[str, list[float]]) -> dict:
    return {"count": len(rows), "views": [
        {"name": name, "centre": [0.0, 0.0, 0.0], "width": 9000.0, "height": 5400.0, "direction": direction,
         "plan": False} for name, direction in rows
    ]}


def light(handle: str, name: str, on: bool, layer: str) -> dict:
    return {"handle": handle, "name": name, "kind": "point", "on": on, "intensity": 800.0, "intensity_unit": "lm",
            "kelvin": 3000.0, "layer": layer, "position": [0.0, 0.0, 2400.0]}


NO_SUN = {"on": False, "latitude": 37.795, "longitude": -122.394, "timezone": -8000, "utc_offset": -8.0,
          "note": "This viewport has no sun yet (it is made the first time the sun is set or switched on)."}


def sun(date: str, clock: str, *, on: bool = True, lat: float = 25.29, lon: float = 51.53, zone: int = 3000,
        julian: int = 2461213, ms: int = 36000000) -> dict:
    return {"on": on, "latitude": lat, "longitude": lon, "timezone": zone, "utc_offset": zone // 1000,
            "date": date, "time": clock, "daylight_saving": False, "azimuth": 95.4, "altitude": 61.2,
            "dxf": {"91_julian_day": julian, "92_ms_after_midnight": ms}}


def lights(*rows: dict, the_sun: dict | None = None) -> dict:
    lit = sum(1 for r in rows if r["on"])
    return {"count": len(rows), "on": lit, "off": len(rows) - lit, "in_model_space": len(rows), "in_blocks": 0,
            "lights": list(rows), "default_lighting": False, "lighting_units": 2, "sun": the_sun or NO_SUN,
            "exposure": {"exposure": 8.8, "white_balance": 6500.0}}


def sun_set(the_sun: dict, *, made: bool = False, what: list[str] | None = None, erased: int = 0, **extra) -> str:
    payload = {"set": what or ["sun date and time"], "sun_made": made, "sun": the_sun,
               "heron_changes": {"added": 0, "modified": 0, "erased": erased},
               "note": "This does not render: press Render in AutoCAD (Visualize tab) when the view looks right.",
               **extra}
    return done(payload)


UNDONE = {"undone": "Undo Heron's last change", "drawing": "Drawing1.dwg", "removed": []}
WIREFRAME_WARNING = ("The viewport is in the 2D Wireframe style, which does not show perspective. Switch to a 3D "
                     "style: autocad_set_3d_view(visual_style='realistic').")

# --- AE1 ----------------------------------------------------------------------------------------

AE1 = {"autocad_set_3d_view": view3d}

# --- AE2 ----------------------------------------------------------------------------------------

AE2_NAME = "LC-AE2-LIVING-CAM-1"
AE2_EYE, AE2_TARGET = P("AE2", 300, 300, 1600), P("AE2", 6000, 4000, 1200)
AE2 = {
    "autocad_set_3d_view": view3d,
    "autocad_add_camera_view": camera(AE2_NAME, AE2_EYE, AE2_TARGET, warning=WIREFRAME_WARNING),
    "autocad_list_views": seq(listed_views((AE2_NAME, way(AE2_EYE, AE2_TARGET))), listed_views()),
    "autocad_undo_last": UNDONE,
    "autocad_get_variable": variables(PERSPECTIVE=1, LENSLENGTH=24.0, VIEWDIR=way(AE2_EYE, AE2_TARGET)),
}

# --- AE3 ----------------------------------------------------------------------------------------

AE3_EYE, AE3_TARGET = P("AE3", 300, 300, 1600), P("AE3", 6000, 4000, 1200)
AE3 = {
    "autocad_set_3d_view": view3d,
    "autocad_add_camera_view": camera("LC-AE3-CAM-1", AE3_EYE, AE3_TARGET),
    "autocad_zoom": {"zoomed": "extents"},
    "autocad_get_variable": variables(PERSPECTIVE=1, LENSLENGTH=24.0,
                                      VIEWDIR=Steps([[-1.0, -1.0, 1.0], way(AE3_EYE, AE3_TARGET)])),
}

# --- AE4 ----------------------------------------------------------------------------------------

AE4_TARGET = P("AE4", 6000, 4000, 1200)
AE4_FIRST, AE4_MOVED, AE4_THIRD = P("AE4", 300, 300, 1600), P("AE4", 1500, 300, 1600), P("AE4", 300, 3000, 1800)
AE4_SCREEN = way(AE4_MOVED, AE4_TARGET)
AE4 = {
    "autocad_add_camera_view": seq(
        camera("LC-AE4-CAM-1", AE4_FIRST, AE4_TARGET, on_screen=False),
        refused("This drawing already has a view called 'LC-AE4-CAM-1'. Pass replace=true to move it, or give "
                "another name."),
        camera("LC-AE4-CAM-1", AE4_MOVED, AE4_TARGET, created=False),
        camera("LC-AE4-CAM-2", AE4_THIRD, AE4_TARGET, on_screen=False),
    ),
    "autocad_list_views": seq(
        listed_views(("LC-AE4-CAM-1", AE4_SCREEN)),
        listed_views(("LC-AE4-CAM-1", AE4_SCREEN), ("LC-AE4-CAM-2", way(AE4_THIRD, AE4_TARGET))),
    ),
    "autocad_get_variable": variables(VIEWDIR=Steps([AE4_SCREEN, AE4_SCREEN])),
}

# --- AE5 ----------------------------------------------------------------------------------------

DOHA = sun("2026-06-21", "10:00:00")
AE5_PLACE = {
    "LATITUDE": Steps([37.795, 25.29, 37.795]),
    "LONGITUDE": Steps([-122.394, 51.53, -122.394]),
    "TIMEZONE": Steps([-8000, 3000, -8000]),
    "SUNSTATUS": Steps([0, 1, 0]),
}
AE5 = {
    "autocad_get_variable": variables(**AE5_PLACE),
    "autocad_list_lights": seq(lights(), lights(the_sun=DOHA), lights()),
    "autocad_set_sun": sun_set(DOHA, made=True,
                               what=["LATITUDE", "LONGITUDE", "TIMEZONE", "sun date and time", "SUNSTATUS"]),
    "autocad_undo_last": UNDONE,
    "autocad_run_lisp": {"expression": render.SUN_GROUPS, "result": "(2461213 36000000)", "timed_out": False},
}

# --- AE6 ----------------------------------------------------------------------------------------

TURNED = [1.0, -2.0, 0.5]
AE6 = {
    "autocad_set_3d_view": view3d,
    "autocad_set_sun": seq(
        sun_set(DOHA, what=["LATITUDE", "LONGITUDE", "TIMEZONE", "sun date and time", "SUNSTATUS"]),
        sun_set(sun("2026-06-21", "16:30:00")),
    ),
    "autocad_get_variable": variables(VIEWDIR=Steps([TURNED, [2.0, -4.0, 1.0]]), LATITUDE=25.29, LONGITUDE=51.53,
                                      TIMEZONE=3000),
    "autocad_list_lights": lights(the_sun=sun("2026-06-21", "16:30:00")),
}

# --- AE7 ----------------------------------------------------------------------------------------

WINTER = sun("2026-12-21", "09:00:00", on=False, lat=37.795, lon=-122.394, zone=-8000, julian=2461396, ms=32400000)
AE7 = {
    "lc.other_drawing": "C:/Temp/heron-live-check-x/AE7/never-had-a-sun.dwg",
    "autocad_list_lights": seq(lights(), lights(the_sun=WINTER), lights()),
    "autocad_set_sun": sun_set(WINTER, made=True,
                               warning="The sun is off, so the date and time show only once it is on (on=true)."),
    "autocad_undo_last": UNDONE,
    "lc.activate": None,
}

# --- AE8 ----------------------------------------------------------------------------------------

KOCHI = sun("2026-06-21", "10:00:00", lat=9.93, lon=76.27, zone=5030)
AE8 = {
    "autocad_set_sun": seq(sun_set(KOCHI, what=["LATITUDE", "LONGITUDE", "TIMEZONE"]),
                           sun_set({**KOCHI, "timezone": 5045}, what=["TIMEZONE"])),
    "autocad_get_variable": variables(TIMEZONE=Steps([5030, 5045]), LATITUDE=9.93, LONGITUDE=76.27),
}

# --- AE10 ---------------------------------------------------------------------------------------


def made_light(handle: str, name: str, layer: str) -> str:
    return done({"created": True, "handle": handle, "type": "light", "layer": layer, "name": name, "kind": "point",
                 "intensity": 800.0, "on": True, "kelvin": 3000.0, "intensity_unit": "lm", "lighting_units": 2,
                 "verified": True}, "DONE - 1 added.")


ON10, OFF10 = light("3A0", "LC-AE10-LIGHT", True, "LC-AE10"), light("3A0", "LC-AE10-LIGHT", False, "LC-AE10")
SWITCHED = {"changed": 1, "lights": [OFF10], "set": [], "sun": False, "default_lighting": False}
AE10 = {
    "autocad_add_light": made_light("3A0", "LC-AE10-LIGHT", "LC-AE10"),
    "autocad_list_lights": seq(lights(ON10), lights(OFF10), lights(ON10), lights(OFF10)),
    "autocad_switch_lights": seq(
        done(SWITCHED, "DONE - 1 changed."),
        done(SWITCHED, "DONE - 1 changed."),
        refused("No light called 'NO-SUCH-LIGHT'. The lights are: LC-AE10-LIGHT (3A0). autocad_list_lights gives "
                "each one's handle."),
    ),
    "autocad_undo_last": UNDONE,
}

# --- AE13 ---------------------------------------------------------------------------------------

ON13 = light("3B0", "LC-AE13-LIGHT", True, "LC-AE13-LIGHTS")
AE13 = {
    "autocad_add_light": made_light("3B0", "LC-AE13-LIGHT", "LC-AE13-LIGHTS"),
    "autocad_set_layer_state": {"matched": 1},
    "autocad_switch_lights": refused("An object this needs is on a locked layer. Unlock the layer first."),
    "autocad_list_lights": lights(ON13),
    "autocad_set_3d_view": view3d,
}

# Each row: the good recording, and what in it goes wrong for the FAIL.
SAMPLES: dict[str, tuple[dict, dict]] = {
    "AE1": (AE1, {"autocad_set_3d_view": lagging()}),
    "AE2": (AE2, {"autocad_get_variable": variables(PERSPECTIVE=1, LENSLENGTH=50.0,
                                                    VIEWDIR=way(AE2_EYE, AE2_TARGET))}),
    "AE3": (AE3, {"autocad_get_variable": variables(PERSPECTIVE=1, LENSLENGTH=50.0,
                                                    VIEWDIR=Steps([[-1.0, -1.0, 1.0], way(AE3_EYE, AE3_TARGET)]))}),
    "AE4": (AE4, {"autocad_list_views": seq(
        listed_views(("LC-AE4-CAM-1", way(AE4_FIRST, AE4_TARGET))),
        listed_views(("LC-AE4-CAM-2", way(AE4_THIRD, AE4_TARGET))),
    )}),
    "AE5": (AE5, {"autocad_list_lights": seq(lights(), lights(the_sun=DOHA), lights(the_sun=DOHA))}),
    "AE6": (AE6, {"autocad_get_variable": variables(VIEWDIR=Steps([TURNED, [0.0, 0.0, 1.0]]), LATITUDE=25.29,
                                                    LONGITUDE=51.53, TIMEZONE=3000)}),
    "AE7": (AE7, {"autocad_set_sun": sun_set(WINTER, made=False)}),
    "AE8": (AE8, {"autocad_get_variable": variables(TIMEZONE=Steps([5030, 5030]), LATITUDE=9.93, LONGITUDE=76.27)}),
    "AE10": (AE10, {"autocad_list_lights": seq(lights(ON10), lights(OFF10), lights(OFF10), lights(OFF10))}),
    "AE13": (AE13, {"autocad_switch_lights": done(SWITCHED, "DONE - 1 changed.")}),
}

CHECKS = {c.row: c for c in render.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each AE check needs a good and a bad recording here"


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    good, _ = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], good)
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


def test_every_ae_row_is_measured_or_has_a_reason():
    rows = {f"AE{n}" for n in range(1, 16)}
    measured = {c.row for c in render.CHECKS}
    assert measured.isdisjoint(render.BY_EYE)
    assert measured | set(render.BY_EYE) == rows
    assert all(len(why.split()) >= 4 for why in render.BY_EYE.values())


def test_ae7_runs_before_ae5_and_ae13_comes_last():
    order = [c.row for c in render.CHECKS]
    assert order.index("AE7") < order.index("AE5")
    assert order[-1] == "AE13"


def test_ae1_tries_all_ten_styles_then_hidden_by_hand(monkeypatch, typed):
    verdict = play(monkeypatch, CHECKS["AE1"], AE1)
    asked = [kw.get("visual_style") for kw in verdict.called("autocad_set_3d_view")]
    assert asked[:10] == list(NAMES) and asked[10] is None
    assert typed == ["_.VSCURRENT _Hidden\n"]
    assert "Shades of Gray" in verdict.evidence


def test_ae1_says_when_the_read_lags_one_behind(monkeypatch):
    verdict = play(monkeypatch, CHECKS["AE1"], {"autocad_set_3d_view": lagging()})
    assert "lags one behind" in verdict.evidence


def test_ae3_restores_the_view_by_hand(monkeypatch, typed):
    assert play(monkeypatch, CHECKS["AE3"], AE3).passed
    assert typed == ["_.-VIEW _Restore LC-AE3-CAM-1\n"]


def test_ae4_fails_when_replace_erases_the_old_view(monkeypatch):
    calls = AE4["autocad_add_camera_view"].items
    erasing = seq(calls[0], calls[1], camera("LC-AE4-CAM-1", AE4_MOVED, AE4_TARGET, created=False, erased=1), calls[3])
    verdict = play(monkeypatch, CHECKS["AE4"], {**AE4, "autocad_add_camera_view": erasing})
    assert not verdict.passed and "erased 1" in verdict.evidence


def test_ae5_without_admin_says_the_entget_was_not_tried(monkeypatch):
    no_lisp = {k: v for k, v in AE5.items() if k != "autocad_run_lisp"}
    ctx = lc.Context(version="27.0", padlocks={"changes": True, "admin": False, "publish": False})
    verdict = play(monkeypatch, CHECKS["AE5"], no_lisp, ctx=ctx)
    assert verdict.passed, verdict.evidence
    assert "not tried: it needs Admin" in verdict.evidence


def test_ae5_with_admin_compares_groups_91_and_92(monkeypatch):
    wrong = {**AE5, "autocad_run_lisp": {"expression": render.SUN_GROUPS, "result": "(2461212 0)", "timed_out": False}}
    verdict = play(monkeypatch, CHECKS["AE5"], wrong)
    assert not verdict.passed and "2461212" in verdict.evidence
    restart()
    right = play(monkeypatch, CHECKS["AE5"], AE5)
    assert right.passed and "dxf 2461213 / 36000000" in right.evidence and "look like degrees" in right.evidence


def test_ae6_orbits_by_hand(monkeypatch, typed):
    assert play(monkeypatch, CHECKS["AE6"], AE6).passed
    assert typed == ["PERSPECTIVE 0\n", "_.VPOINT 1,-2,0.5\n"]


def test_ae7_fails_when_set_sun_erases(monkeypatch):
    verdict = play(monkeypatch, CHECKS["AE7"], {**AE7, "autocad_set_sun": sun_set(WINTER, made=True, erased=2)})
    assert not verdict.passed and "erased 2" in verdict.evidence


def test_ae8_a_code_autocad_refuses_passes_when_not_set_says_so(monkeypatch):
    refusing = {
        **AE8,
        "autocad_set_sun": seq(sun_set(KOCHI, what=["LATITUDE", "LONGITUDE", "TIMEZONE"]),
                               sun_set(KOCHI, what=[], not_set=["TIMEZONE (AutoCAD refused 5045)"])),
        "autocad_get_variable": variables(TIMEZONE=Steps([5030, 5030]), LATITUDE=9.93, LONGITUDE=76.27),
    }
    verdict = play(monkeypatch, CHECKS["AE8"], refusing)
    assert verdict.passed, verdict.evidence
    assert "5045 refused" in verdict.evidence


def test_ae13_unlocks_and_puts_the_view_back_even_when_it_fails(monkeypatch):
    good, bad = SAMPLES["AE13"]
    verdict = play(monkeypatch, CHECKS["AE13"], {**good, **bad})
    assert [kw.get("locked") for kw in verdict.called("autocad_set_layer_state")] == [True, False]
    assert verdict.called("autocad_set_3d_view") == [{"direction": "top", "visual_style": "2dwireframe"}]
