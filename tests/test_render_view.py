"""Setting a render up from the chat (#59-#63, D-86, D-87), no AutoCAD.

The camera view, the sun's date and time, the light list and switch go to the
Heron plug-in; the place, the sun and default lighting on / off and the
exposure are plain variables over COM. What is checked here: the arithmetic
(Julian day, ms after midnight, TIMEZONE codes), what each tool asks the
plug-in for and in which order the variables are written, the shape of the
light list, and every refusal before anything changes. None of these tools
renders: the modeller presses Render.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad import render
from autocad_mcp.core import connection
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, lighting, solids, views


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


async def _now(fn):
    return fn()


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------


class TestJulianDay:
    @pytest.mark.parametrize("date,day", [
        ((2000, 1, 1), 2451545),
        ((1970, 1, 1), 2440588),
        ((2026, 6, 21), 2461213),
        ((2026, 9, 21), 2461305),  # AutoCAD's default sun date
        ((2024, 2, 29), 2460370),
        ((2024, 3, 1), 2460371),
    ])
    def test_known_dates(self, date, day):
        assert render.julian_day(*date) == day

    def test_it_agrees_with_pythons_own_calendar_for_every_day_of_2026(self):
        import datetime

        first = datetime.date(2026, 1, 1)
        for n in range(365):
            when = first + datetime.timedelta(days=n)
            assert render.julian_day(when.year, when.month, when.day) == when.toordinal() + 1721425


class TestMsAfterMidnight:
    @pytest.mark.parametrize("clock,ms", [
        ((0, 0), 0),
        ((10, 30), 37_800_000),
        ((15, 0), 54_000_000),
        ((23, 59), 86_340_000),
    ])
    def test_known_times(self, clock, ms):
        assert render.ms_after_midnight(*clock) == ms

    def test_seconds_count(self):
        assert render.ms_after_midnight(0, 0, 1) == 1000

    @pytest.mark.parametrize("clock", [(24, 0), (10, 60), (-1, 0)])
    def test_not_a_time_is_refused(self, clock):
        with pytest.raises(AutocadError):
            render.ms_after_midnight(*clock)


class TestTimezone:
    @pytest.mark.parametrize("offset,code", [
        (0, 0),
        (3, 3000),      # Qatar, Saudi Arabia
        (4, 4000),      # UAE, Oman
        (5.5, 5030),    # India
        (5.75, 5045),   # Nepal
        (-3.5, -3030),  # Newfoundland
        (-8, -8000),    # AutoCAD's initial value, US Pacific
        (13, 13000),
        (-12, -12000),
    ])
    def test_a_utc_offset_is_hours_x_1000_plus_minutes(self, offset, code):
        assert render.timezone_code(offset) == code
        assert render.timezone_offset(code) == offset

    @pytest.mark.parametrize("offset", [3.2, 5.6, 14, -13, 0.1])
    def test_an_offset_that_is_not_a_time_zone_is_refused(self, offset):
        with pytest.raises(AutocadError):
            render.timezone_code(offset)

    @pytest.mark.parametrize("code,offset", [(3001, 3.0), (-5002, -5.0), (1003, 1.0), (9031, 9.5), (5046, 5.75)])
    def test_a_named_place_code_keeps_its_offset(self, code, offset):
        assert render.timezone_offset(code) == offset

    @pytest.mark.parametrize("code", [3010, 3020, 3050, 99000, None, "x"])
    def test_a_code_that_cannot_be_told_is_none(self, code):
        assert render.timezone_offset(code) is None


class TestDateAndTimeText:
    def test_a_date(self):
        assert render.parse_date(" 2026-06-21 ") == (2026, 6, 21)

    @pytest.mark.parametrize("text", ["21/06/2026", "2026-02-30", "June 21", ""])
    def test_not_a_date(self, text):
        with pytest.raises(AutocadError, match="year-month-day"):
            render.parse_date(text)

    def test_a_time(self):
        assert render.parse_time("16:45") == (16, 45)
        assert render.parse_time("7:05") == (7, 5)

    @pytest.mark.parametrize("text", ["4pm", "16.45", "16:45:00", "25:00", "10:61", ""])
    def test_not_a_time(self, text):
        with pytest.raises(AutocadError):
            render.parse_time(text)


# ---------------------------------------------------------------------------
# A drawing and a plug-in to stand in for AutoCAD
# ---------------------------------------------------------------------------


SUN = {
    "on": True, "date": "2026-06-21", "time": "10:30:00", "daylight_saving": False,
    "azimuth": 101.5, "altitude": 63.2, "intensity": 1.0,
}

LIGHTS = [
    {"handle": "2A1", "name": "LIVING-DL-01", "kind": "spot", "on": True, "intensity": 800.0,
     "intensity_unit": "lm", "kelvin": 3000.0, "layer": "E-LIGHT", "position": [0.0, 0.0, 2950.0]},
    {"handle": "3F0", "name": "DL", "kind": "web", "on": False, "intensity": 1200.0,
     "intensity_unit": "cd", "kelvin": 3000.0, "layer": "0", "position": [0.0, 0.0, -10.0],
     "block": "DOWNLIGHT", "inserts": 12},
]


class Doc:
    def __init__(self, **variables):
        self.vars = {
            "UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0),
            "TILEMODE": 1, "DEFAULTLIGHTING": 0, "LIGHTINGUNITS": 2, "SUNSTATUS": 1,
            "LATITUDE": 37.795, "LONGITUDE": -122.394, "TIMEZONE": -8000,
            "EXPVALUE": 8.8, "EXPWHITEBALANCE": 6500,
        }
        self.vars.update(variables)
        self.written: list[tuple[str, object]] = []
        self.refuse: set[str] = set()
        self.ignore: set[str] = set()
        self.marks = 0
        self.regens = 0

    def GetVariable(self, name):
        if name not in self.vars:
            raise RuntimeError("Error getting system variable")
        return self.vars[name]

    def SetVariable(self, name, value):
        if name in self.refuse:
            raise RuntimeError("Error setting system variable")
        self.written.append((name, value))
        if name not in self.ignore:
            self.vars[name] = value

    def StartUndoMark(self):
        self.marks += 1

    def EndUndoMark(self):
        pass

    def Regen(self, which):
        self.regens += 1


class Plugin:
    """Answers each operation the way the plug-in does, and records it."""

    def __init__(self, doc):
        self.doc = doc
        self.calls: list[tuple[str, dict]] = []
        self.sun = dict(SUN)
        self.fail: str | None = None
        self.view_style = "Realistic"

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        # When the plug-in is asked, the variables already written are in the drawing.
        self.order = [name for name, _ in self.doc.written]
        if self.fail:
            raise AutocadError(self.fail)
        if operation == "list_lights":
            return {"count": len(LIGHTS), "lights": [dict(r) for r in LIGHTS], "sun": dict(self.sun)}
        if operation == "switch_lights":
            return {"asked_on": 1, "asked_off": 0, "changed": 1, "lights": [dict(LIGHTS[1], on=True)]}
        if operation == "set_sun":
            if "year" in args:
                self.sun["date"] = f"{args['year']}-{args['month']:02d}-{args['day']:02d}"
            if "hour" in args:
                self.sun["time"] = f"{args['hour']:02d}:{args['minute']:02d}:00"
            return {"sun_made": False, "sun": dict(self.sun)}
        if operation == "current_view":
            return {"visual_style": self.view_style, "visual_style_on_screen": self.view_style,
                    "visual_style_saved": self.view_style, "perspective": False, "model_tab": True}
        if operation == "add_camera_view":
            return {"created": True, "name": args["name"], "handle": "5B", "lens_mm": args["lens"],
                    "perspective": True, "field_of_view_degrees": 73.74, "on_screen": args["look_through"]}
        raise AssertionError(operation)


@pytest.fixture
def plugin(monkeypatch):
    doc = Doc()
    fake = Plugin(doc)
    for module in (lighting, views, solids):
        monkeypatch.setattr(module, "run", _now)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    return fake


def ops(plugin):
    return [operation for operation, _ in plugin.calls]


# ---------------------------------------------------------------------------
# autocad_list_lights
# ---------------------------------------------------------------------------


class TestListLights:
    def test_the_lights_the_sun_and_why_a_render_may_be_dark(self, plugin):
        out = call(lighting.autocad_list_lights())
        assert ops(plugin) == ["list_lights"]
        assert out["count"] == 2 and out["on"] == 1 and out["off"] == 1
        assert out["in_model_space"] == 1 and out["in_blocks"] == 1
        assert out["lights"][1]["block"] == "DOWNLIGHT" and out["lights"][1]["inserts"] == 12
        assert out["default_lighting"] is False and out["lighting_units"] == 2
        assert out["exposure"] == {"exposure": 8.8, "white_balance": 6500.0}
        sun = out["sun"]
        assert sun["on"] is True and sun["date"] == "2026-06-21" and sun["time"] == "10:30:00"
        assert sun["timezone"] == -8000 and sun["utc_offset"] == -8.0
        assert sun["dxf"] == {"91_julian_day": 2461213, "92_ms_after_midnight": 37_800_000}
        assert "warning" not in out

    def test_it_is_a_read_and_writes_nothing(self, plugin):
        before = connection.write_count()
        call(lighting.autocad_list_lights())
        assert connection.write_count() == before and plugin.doc.written == []

    def test_default_lighting_on_is_said(self, plugin):
        plugin.doc.vars["DEFAULTLIGHTING"] = 1
        out = call(lighting.autocad_list_lights())
        assert "DEFAULTLIGHTING 1" in out["warning"] and "default_lighting=false" in out["warning"]

    def test_an_exposure_variable_this_autocad_lacks_is_null_with_the_palette_named(self, plugin):
        del plugin.doc.vars["EXPVALUE"]
        out = call(lighting.autocad_list_lights())
        assert out["exposure"]["exposure"] is None and "RENDEREXPOSURE" in out["exposure"]["note"]


class TestLightSummaryShape:
    def test_no_lights_and_no_sun(self):
        out = lighting.light_summary(
            {"lights": [], "sun": None, "sun_note": "This viewport has no sun yet."},
            {"SUNSTATUS": 0, "DEFAULTLIGHTING": 0, "LIGHTINGUNITS": 2},
        )
        assert out["count"] == 0 and out["lights"] == []
        assert out["sun"]["on"] is False and out["sun"]["note"] == "This viewport has no sun yet."
        assert "dxf" not in out["sun"] and "warning" not in out

    def test_every_light_off_and_the_sun_off_warns_of_a_dark_render(self):
        rows = [dict(LIGHTS[0], on=False)]
        out = lighting.light_summary({"lights": rows, "sun": dict(SUN, on=False)}, {"SUNSTATUS": 0, "LIGHTINGUNITS": 2})
        assert "dark" in out["warning"]

    def test_lighting_units_not_2_is_warned_when_there_are_lights(self):
        out = lighting.light_summary({"lights": [LIGHTS[0]]}, {"LIGHTINGUNITS": 0, "SUNSTATUS": 1})
        assert "LIGHTINGUNITS is 0" in out["warning"]

    def test_the_sun_object_and_sunstatus_disagreeing_is_shown(self):
        out = lighting.sun_summary(dict(SUN, on=False), {"SUNSTATUS": 1})
        assert out["on"] is True and out["sun_object_on"] is False

    def test_without_sunstatus_the_sun_object_says(self):
        assert lighting.sun_summary(dict(SUN, on=False), {})["on"] is False


# ---------------------------------------------------------------------------
# autocad_switch_lights
# ---------------------------------------------------------------------------


class TestSwitchLights:
    def test_names_go_to_the_plug_in_and_variables_follow_default_lighting_first(self, plugin):
        plugin.doc.vars.update(DEFAULTLIGHTING=1, SUNSTATUS=1)
        out = call(lighting.autocad_switch_lights(turn_on=["DL"], turn_off=["LIVING-DL-01"], sun=False, default_lighting=False))
        assert plugin.calls == [("switch_lights", {"on": ["DL"], "off": ["LIVING-DL-01"]})]
        assert plugin.doc.written == [("DEFAULTLIGHTING", 0), ("SUNSTATUS", 0)]
        assert out["changed"] == 1 and out["set"] == ["DEFAULTLIGHTING", "SUNSTATUS"]
        assert out["sun"] is False and out["default_lighting"] is False
        assert "not_set" not in out and "warning" not in out
        assert plugin.doc.marks == 1 and plugin.doc.regens == 1
        assert "does not render" in out["note"] and "press Render" in out["note"]

    def test_all_lights(self, plugin):
        call(lighting.autocad_switch_lights(all_lights="off"))
        assert plugin.calls == [("switch_lights", {"all": "off"})]
        assert plugin.doc.written == []

    def test_only_the_sun_asks_the_plug_in_nothing(self, plugin):
        call(lighting.autocad_switch_lights(sun=True))
        assert plugin.calls == [] and plugin.doc.written == [("SUNSTATUS", 1)]

    def test_it_counts_as_a_change(self, plugin):
        before = connection.write_count()
        call(lighting.autocad_switch_lights(sun=True))
        assert connection.write_count() > before

    def test_a_variable_autocad_refuses_is_said_and_the_rest_still_go(self, plugin):
        plugin.doc.refuse.add("DEFAULTLIGHTING")
        out = call(lighting.autocad_switch_lights(sun=True, default_lighting=False))
        assert out["set"] == ["SUNSTATUS"]
        assert any(item.startswith("DEFAULTLIGHTING") for item in out["not_set"])

    def test_a_variable_that_does_not_take_is_said(self, plugin):
        plugin.doc.ignore.add("SUNSTATUS")
        plugin.doc.vars["SUNSTATUS"] = 0
        out = call(lighting.autocad_switch_lights(sun=True))
        assert "SUNSTATUS (it reads 0 after being set to 1)" in out["not_set"]

    def test_default_lighting_left_on_is_warned(self, plugin):
        plugin.doc.vars["DEFAULTLIGHTING"] = 1
        out = call(lighting.autocad_switch_lights(all_lights="on"))
        assert "DEFAULTLIGHTING 1" in out["warning"]

    def test_an_unknown_light_is_the_plug_ins_refusal_and_no_variable_is_written(self, plugin):
        plugin.fail = "No light called 'KITCHEN'. The lights are: LIVING-DL-01, DL. Nothing was changed."
        assert "KITCHEN" in error(lighting.autocad_switch_lights(turn_on=["KITCHEN"], sun=False))
        assert plugin.doc.written == []

    @pytest.mark.parametrize("kwargs,words", [
        ({}, "Nothing to switch"),
        ({"all_lights": "on", "turn_off": ["DL"]}, "not both"),
        ({"turn_on": ["DL"], "turn_off": ["dl "]}, "both on and off"),
    ])
    def test_refused_before_anything(self, plugin, kwargs, words):
        assert words in error(lighting.autocad_switch_lights(**kwargs))
        assert plugin.calls == [] and plugin.doc.written == []


# ---------------------------------------------------------------------------
# autocad_set_sun
# ---------------------------------------------------------------------------


class TestSetSun:
    def test_doha_on_midsummer_morning(self, plugin):
        out = call(lighting.autocad_set_sun(
            date="2026-06-21", time="10:00", latitude=25.29, longitude=51.53, utc_offset=3,
            daylight_saving=False, on=True,
        ))
        # The place first, then the sun's date and time, then on.
        assert plugin.order == ["LATITUDE", "LONGITUDE", "TIMEZONE"]
        assert plugin.calls == [("set_sun", {"year": 2026, "month": 6, "day": 21, "hour": 10, "minute": 0, "daylight_saving": False})]
        assert plugin.doc.written == [("LATITUDE", 25.29), ("LONGITUDE", 51.53), ("TIMEZONE", 3000), ("SUNSTATUS", 1)]
        assert out["set"] == ["LATITUDE", "LONGITUDE", "TIMEZONE", "sun date and time", "SUNSTATUS"]
        sun = out["sun"]
        assert sun["date"] == "2026-06-21" and sun["time"] == "10:00:00"
        assert sun["latitude"] == 25.29 and sun["longitude"] == 51.53
        assert sun["timezone"] == 3000 and sun["utc_offset"] == 3.0
        assert sun["dxf"] == {"91_julian_day": 2461213, "92_ms_after_midnight": 36_000_000}
        assert "not_set" not in out and "warning" not in out
        assert plugin.doc.marks == 1

    def test_a_time_alone_sends_only_the_time(self, plugin):
        call(lighting.autocad_set_sun(time="16:30"))
        assert plugin.calls == [("set_sun", {"hour": 16, "minute": 30})]
        assert plugin.doc.written == []

    def test_only_the_place_reads_the_sun_back_without_setting_it(self, plugin):
        out = call(lighting.autocad_set_sun(latitude=9.93, longitude=76.27, utc_offset=5.5))
        assert ops(plugin) == ["list_lights"]
        assert out["sun"]["timezone"] == 5030 and out["sun"]["date"] == "2026-06-21"

    def test_on_with_default_lighting_on_is_warned(self, plugin):
        plugin.doc.vars["DEFAULTLIGHTING"] = 1
        out = call(lighting.autocad_set_sun(on=True))
        assert "DEFAULTLIGHTING 1" in out["warning"]

    def test_a_date_with_the_sun_off_is_warned(self, plugin):
        plugin.doc.vars["SUNSTATUS"] = 0
        out = call(lighting.autocad_set_sun(date="2026-12-21"))
        assert "sun is off" in out["warning"]

    def test_a_place_that_does_not_take_is_said(self, plugin):
        plugin.doc.ignore.add("LATITUDE")
        out = call(lighting.autocad_set_sun(latitude=25.29))
        assert any(item.startswith("LATITUDE (it reads 37.795") for item in out["not_set"])

    def test_the_sun_refused_after_the_place_was_set_says_ctrl_z(self, plugin):
        plugin.fail = "AutoCAD gave no current model viewport. Nothing was changed."
        answer = error(lighting.autocad_set_sun(time="10:00", latitude=25.29))
        assert "LATITUDE" in answer and "Ctrl+Z" in answer

    def test_the_sun_switched_on_is_not_called_off_by_the_older_reading(self, plugin):
        """Review of PR #152: the plug-in reads the sun before SUNSTATUS is written."""
        plugin.sun["on"] = False
        plugin.doc.vars["SUNSTATUS"] = 0
        out = call(lighting.autocad_set_sun(time="10:00", on=True))
        assert out["sun"]["on"] is True and "sun_object_on" not in out["sun"]
        assert "sun is off" not in out.get("warning", "")

    @pytest.mark.parametrize("date", ["1850-06-21", "2300-01-01"])
    def test_a_year_the_plug_in_would_refuse_is_refused_before_the_place_is_set(self, plugin, date):
        """Review of PR #152: 1850 was refused only after LATITUDE was written."""
        answer = error(lighting.autocad_set_sun(date=date, latitude=25.29))
        assert "1900-2200" in answer and "Nothing was changed" in answer
        assert plugin.calls == [] and plugin.doc.written == []

    def test_the_sun_refused_after_the_place_does_not_also_say_nothing_changed(self, plugin):
        plugin.fail = "AutoCAD gave no current model viewport. Nothing was changed."
        answer = error(lighting.autocad_set_sun(time="10:00", latitude=25.29))
        assert "Nothing was changed" not in answer
        assert "date and time were not changed" in answer and "Ctrl+Z" in answer

    def test_a_layout_is_refused_before_anything(self, plugin):
        plugin.doc.vars["TILEMODE"] = 0
        assert "Model tab" in error(lighting.autocad_set_sun(time="10:00", latitude=25.29))
        assert plugin.calls == [] and plugin.doc.written == []

    @pytest.mark.parametrize("kwargs,words", [
        ({}, "Nothing to set"),
        ({"date": "21/06/2026"}, "year-month-day"),
        ({"time": "10am"}, "24-hour"),
        ({"utc_offset": 3.2}, "not a time zone"),
        ({"latitude": 95}, "latitude"),
        ({"longitude": -181}, "longitude"),
    ])
    def test_refused_before_anything(self, plugin, kwargs, words):
        assert words in error(lighting.autocad_set_sun(**kwargs))
        assert plugin.calls == [] and plugin.doc.written == []


# ---------------------------------------------------------------------------
# autocad_set_render_exposure
# ---------------------------------------------------------------------------


class TestRenderExposure:
    def test_both_are_written_in_the_type_autocad_keeps_and_read_back(self, plugin):
        out = call(lighting.autocad_set_render_exposure(exposure=7.5, white_balance=4200.4))
        assert plugin.doc.written == [("EXPVALUE", 7.5), ("EXPWHITEBALANCE", 4200)]
        assert out["exposure"] == {"from": 8.8, "to": 7.5}
        assert out["white_balance"] == {"from": 6500.0, "to": 4200.0}
        assert "not_set" not in out and plugin.calls == []

    def test_a_real_white_balance_stays_real(self, plugin):
        plugin.doc.vars["EXPWHITEBALANCE"] = 6500.0
        call(lighting.autocad_set_render_exposure(white_balance=4200.4))
        assert plugin.doc.written == [("EXPWHITEBALANCE", 4200.4)]

    def test_an_autocad_without_the_variable_changes_nothing_and_names_the_palette(self, plugin):
        del plugin.doc.vars["EXPVALUE"]
        answer = error(lighting.autocad_set_render_exposure(exposure=7, white_balance=5000))
        assert "RENDEREXPOSURE" in answer and "Nothing was changed" in answer
        assert plugin.doc.written == []

    def test_a_value_that_does_not_take_is_said(self, plugin):
        plugin.doc.ignore.add("EXPVALUE")
        out = call(lighting.autocad_set_render_exposure(exposure=12))
        assert "EXPVALUE (it reads 8.8 after being set to 12)" in out["not_set"]

    @pytest.mark.parametrize("kwargs,words", [
        ({}, "Nothing to set"),
        ({"exposure": -7}, "-6 to 21"),
        ({"exposure": 22}, "-6 to 21"),
        ({"white_balance": 900}, "1000-20000"),
    ])
    def test_refused_before_anything(self, plugin, kwargs, words):
        assert words in error(lighting.autocad_set_render_exposure(**kwargs))
        assert plugin.doc.written == []


# ---------------------------------------------------------------------------
# autocad_add_camera_view
# ---------------------------------------------------------------------------


class ViewItem:
    def __init__(self, name):
        self.Name = name


class ViewList:
    def __init__(self, names):
        self.names = names

    @property
    def Count(self):
        return len(self.names)

    def Item(self, i):
        return ViewItem(self.names[i])


class TestCameraView:
    def test_a_24_mm_camera_in_the_living_room(self, plugin):
        plugin.doc.Views = ViewList(["LIVING-CAM-1"])
        out = call(views.autocad_add_camera_view(
            name="LIVING-CAM-1", eye=[1000, 1000, 1600], target=[5000, 4000, 1200], lens=24,
        ))
        assert plugin.calls[0] == ("add_camera_view", {
            "name": "LIVING-CAM-1", "eye": [1000.0, 1000.0, 1600.0], "target": [5000.0, 4000.0, 1200.0],
            "lens": 24.0, "look_through": True, "replace": False,
        })
        # Then the style is read: perspective does not show in 2D Wireframe.
        assert ops(plugin) == ["add_camera_view", "current_view"]
        assert out["created"] is True and out["perspective"] is True and out["in_drawing"] is True
        assert "does not render" in out["note"] and "warning" not in out

    def test_a_ucs_eye_is_turned_into_world(self, plugin):
        plugin.doc.vars.update(UCSORG=(100.0, 0.0, 0.0), UCSXDIR=(0.0, 1.0, 0.0), UCSYDIR=(-1.0, 0.0, 0.0))
        plugin.doc.Views = ViewList(["CAM"])
        call(views.autocad_add_camera_view(name="CAM", eye=[10, 0, 1600], target=[20, 0, 1600], coords="ucs"))
        args = plugin.calls[0][1]
        assert args["eye"] == pytest.approx([100.0, 10.0, 1600.0])
        assert args["target"] == pytest.approx([100.0, 20.0, 1600.0])
        assert args["lens"] == 50.0

    def test_a_2d_wireframe_viewport_is_warned_that_perspective_will_not_show(self, plugin):
        plugin.doc.Views = ViewList(["CAM"])
        plugin.view_style = "2dWireframe"
        out = call(views.autocad_add_camera_view(name="CAM", eye=[0, 0, 1600], target=[1000, 0, 1600]))
        assert "2D Wireframe" in out["warning"] and "visual_style='realistic'" in out["warning"]

    def test_not_shown_asks_nothing_about_the_style(self, plugin):
        plugin.doc.Views = ViewList(["CAM"])
        plugin.view_style = "2dWireframe"
        out = call(views.autocad_add_camera_view(name="CAM", eye=[0, 0, 1600], target=[1000, 0, 1600], look_through=False))
        assert ops(plugin) == ["add_camera_view"] and "warning" not in out

    def test_not_read_back_is_a_warning_not_an_error(self, plugin):
        plugin.doc.Views = ViewList([])
        out = call(views.autocad_add_camera_view(name="CAM", eye=[0, 0, 1600], target=[1000, 0, 1600]))
        assert out["in_drawing"] is False and "do not make it again" in out["warning"]

    def test_it_counts_as_a_change(self, plugin):
        plugin.doc.Views = ViewList(["CAM"])
        before = connection.write_count()
        call(views.autocad_add_camera_view(name="CAM", eye=[0, 0, 1600], target=[1000, 0, 1600]))
        assert connection.write_count() == before + 1

    @pytest.mark.parametrize("kwargs,words", [
        ({"eye": [0, 0]}, "[x, y, z]"),
        ({"target": [0, 0, 1600]}, "same point"),
        ({"lens": 5}, "10-600 mm"),
        ({"lens": 700}, "10-600 mm"),
        ({"name": "A:B"}, "does not allow"),
    ])
    def test_refused_before_asking(self, plugin, kwargs, words):
        base = {"name": "CAM", "eye": [0, 0, 1600], "target": [1000, 0, 1600]}
        base.update(kwargs)
        assert words in error(views.autocad_add_camera_view(**base))
        assert plugin.calls == []

    def test_without_the_plug_in_it_says_why(self, plugin, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        assert "--no-bridge" in error(views.autocad_add_camera_view(name="CAM", eye=[0, 0, 1600], target=[1, 0, 1600]))


# ---------------------------------------------------------------------------
# autocad_set_3d_view reads the visual style back (#59)
# ---------------------------------------------------------------------------


class Viewport:
    Direction = (0.0, 0.0, 1.0)


class StyleDoc(Doc):
    def __init__(self):
        super().__init__(CMDACTIVE=0)
        self.sent: list[str] = []
        self.ActiveViewport = Viewport()

    def SendCommand(self, text):
        self.sent.append(text)


@pytest.fixture
def styled(monkeypatch, plugin):
    doc = StyleDoc()
    plugin.doc = doc
    monkeypatch.setattr(solids, "get_doc", lambda: doc)
    return plugin


class TestVisualStyleReadBack:
    def test_the_style_found_is_reported(self, styled):
        out = call(solids.autocad_set_3d_view(visual_style="realistic", zoom_extents=False))
        assert styled.doc.sent == ["_.VSCURRENT _Realistic\n"]
        assert ops(styled) == ["current_view"]
        assert out["visual_style_found"] == "Realistic" and "not_set" not in out
        assert "visual_style_found_from" not in out and "visual_style_warning" not in out

    def test_a_different_style_is_a_warning_not_a_failure(self, styled):
        """Review of PR #152: the reading may be the viewport's record from before VSCURRENT."""
        styled.view_style = "2dWireframe"
        out = call(solids.autocad_set_3d_view(visual_style="hidden", zoom_extents=False))
        assert out["visual_style_found"] == "2dWireframe"
        assert "'hidden'" in out["visual_style_warning"] and "'2dWireframe'" in out["visual_style_warning"]
        assert "autocad_preview" in out["visual_style_warning"]
        assert "not_set" not in out

    def test_two_word_styles_match_whatever_their_case(self, styled):
        styled.view_style = "Shades of Gray"
        out = call(solids.autocad_set_3d_view(visual_style="shades of gray", zoom_extents=False))
        assert "not_set" not in out and "visual_style_warning" not in out

    def test_a_style_read_from_the_saved_record_says_so(self, styled, monkeypatch):
        real = styled.__call__

        def saved_only(operation, args):
            answer = real(operation, args)
            if operation == "current_view":
                answer["visual_style_on_screen"] = None
            return answer

        monkeypatch.setattr(_shared, "plugin_runner", lambda: saved_only)
        out = call(solids.autocad_set_3d_view(visual_style="realistic", zoom_extents=False))
        assert out["visual_style_found_from"] == "the viewport's saved record"

    def test_a_direction_alone_still_reports_the_style(self, styled):
        out = call(solids.autocad_set_3d_view(direction="sw_iso", zoom_extents=False))
        assert out["visual_style_found"] == "Realistic" and "not_set" not in out
        assert "visual_style_found_from" not in out and "visual_style_warning" not in out

    def test_without_the_plug_in_it_is_null_with_the_reason(self, styled, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        out = call(solids.autocad_set_3d_view(visual_style="realistic", zoom_extents=False))
        assert out["visual_style_found"] is None and "--no-bridge" in out["visual_style_note"]
        assert "not_set" not in out

    def test_an_older_plug_in_is_null_with_its_words(self, styled):
        styled.fail = "Heron in AutoCAD does not have the operation 'current_view'. Update Heron so both sides match."
        out = call(solids.autocad_set_3d_view(visual_style="realistic", zoom_extents=False))
        assert out["visual_style_found"] is None and "current_view" in out["visual_style_note"]

    def test_the_read_back_writes_nothing(self, styled):
        before = connection.write_count()
        call(solids.autocad_set_3d_view(visual_style="realistic", zoom_extents=False))
        assert connection.write_count() == before


def test_levels():
    assert risk_of("autocad_list_lights") is Risk.READ
    for tool in ("autocad_switch_lights", "autocad_set_sun", "autocad_set_render_exposure", "autocad_add_camera_view"):
        assert risk_of(tool) is Risk.CHANGE, tool
    assert risk_of("autocad_set_3d_view") is Risk.VIEW
    # The owner's rule: Heron sets a render up and never runs one (D-87, #158).
    with pytest.raises(KeyError):
        risk_of("autocad_render")
