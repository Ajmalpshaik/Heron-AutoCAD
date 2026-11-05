"""Lights and materials for a render (D-42), no AutoCAD.

AutoCAD's COM has no light object and cannot set a material's colour, maps or
glow, so both tools hand the work to the Heron plug-in ("run", D-40). What is
checked here is everything up to the pipe: what each tool asks the plug-in
for, in which units and directions, what it refuses before asking, and the
LIGHTINGUNITS warning.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.acad.render import kelvin_to_rgb
from autocad_mcp.core import connection
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, lighting, materials


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


class Found:
    def __init__(self, handle, name="AcDbLight"):
        self.Handle, self.ObjectName, self.Layer = handle, name, "0"
        self.Document = self

    def HandleToObject(self, handle):
        return Found(handle, self.ObjectName)


class Items:
    def __init__(self, names):
        self.names = names

    @property
    def Count(self):
        return len(self.names)

    def Item(self, key):
        if isinstance(key, int):
            return Named(self.names[key])
        return Named(next(n for n in self.names if n == key))


class Named:
    def __init__(self, name):
        self.Name, self.Description = name, ""


class Doc:
    def __init__(self, lighting_units=2, ucs=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))):
        self.vars = dict(zip(("UCSORG", "UCSXDIR", "UCSYDIR"), ucs, strict=True))
        self.vars["LIGHTINGUNITS"] = lighting_units
        self.Materials = Items(["Global"])

    def GetVariable(self, name):
        return self.vars[name]

    def HandleToObject(self, handle):
        return Found(handle)


class Plugin:
    """Stands in for the plug-in: records each operation and answers like it."""

    def __init__(self, doc):
        self.calls: list[tuple[str, dict]] = []
        self.doc = doc

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        if operation == "create_material":
            self.doc.Materials.names.append(args["name"])
            return {"created": True, "name": args["name"], "handle": "4C", "set": ["diffuse colour"]}
        return {"created": True, "handle": "3A", "name": args.get("name") or "Pointlight1", "kind": args["kind"]}


@pytest.fixture
def plugin(monkeypatch):
    doc = Doc()
    fake = Plugin(doc)
    for module in (lighting, materials):
        monkeypatch.setattr(module, "run", _now)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# autocad_add_light
# ---------------------------------------------------------------------------


class TestAddLight:
    def test_a_point_light_in_candela_at_warm_white_by_default(self, plugin):
        out = call(lighting.autocad_add_light(position=[1000, 2000, 2950], intensity=1500))
        assert plugin.calls == [("add_light", {
            "kind": "point",
            "position": [1000.0, 2000.0, 2950.0],
            "intensity": 1500.0,
            "intensity_method": "peak_intensity",
            "on": True,
            "shadows": True,
            "kelvin": 3000.0,
        })]
        assert out["created"] is True and out["handle"] == "3A" and out["verified"] is True
        assert out["intensity_unit"] == "cd" and out["lighting_units"] == 2
        assert "warning" not in out

    def test_a_downlight_spot_in_lumens_aims_straight_down_by_default(self, plugin):
        call(lighting.autocad_add_light(
            position=[0, 0, 3000], intensity=800, kind="spot", intensity_unit="lm", kelvin=3000,
            hotspot=40, falloff=60, name="DL-01", layer="E-LIGHT",
        ))
        args = plugin.calls[0][1]
        assert args["intensity_method"] == "flux"
        assert args["target"] == [0.0, 0.0, 2999.0]
        assert args["hotspot"] == pytest.approx(math.radians(40))
        assert args["falloff"] == pytest.approx(math.radians(60))
        assert args["name"] == "DL-01" and args["layer"] == "E-LIGHT"

    def test_an_up_light_by_direction(self, plugin):
        call(lighting.autocad_add_light(position=[0, 0, 1800], intensity=300, kind="spot", direction=[0, 0, 5]))
        assert plugin.calls[0][1]["target"] == [0.0, 0.0, 1801.0]

    def test_a_target_is_passed_as_given(self, plugin):
        call(lighting.autocad_add_light(position=[0, 0, 3000], intensity=500, kind="spot", target=[1000, 0, 0]))
        assert plugin.calls[0][1]["target"] == [1000.0, 0.0, 0.0]

    def test_a_coloured_light_sends_rgb_and_no_kelvin(self, plugin):
        call(lighting.autocad_add_light(position=[0, 0, 0], intensity=100, rgb=[0, 120, 255]))
        args = plugin.calls[0][1]
        assert args["rgb"] == [0, 120, 255] and "kelvin" not in args

    def test_a_web_light_needs_its_ies_file(self, plugin, tmp_path):
        assert ".ies" in error(lighting.autocad_add_light(position=[0, 0, 3000], intensity=800, kind="web"))
        missing = tmp_path / "dl.ies"
        assert "no file" in error(lighting.autocad_add_light(position=[0, 0, 3000], intensity=800, kind="web", web_file=str(missing)))
        missing.write_text("IESNA:LM-63-2002")
        call(lighting.autocad_add_light(position=[0, 0, 3000], intensity=800, kind="web", intensity_unit="lm", web_file=str(missing)))
        assert plugin.calls[0][1]["web_file"] == str(missing)
        assert plugin.calls[0][1]["target"] == [0.0, 0.0, 2999.0]

    def test_a_distant_light_is_in_lux(self, plugin):
        call(lighting.autocad_add_light(position=[0, 0, 10000], intensity=50000, kind="distant", target=[0, 0, 0]))
        args = plugin.calls[0][1]
        assert args["intensity_method"] == "illuminance" and args["target"] == [0.0, 0.0, 0.0]

    def test_a_ucs_position_is_turned_into_world(self, plugin):
        plugin.doc.vars.update(UCSORG=(100.0, 0.0, 0.0), UCSXDIR=(0.0, 1.0, 0.0), UCSYDIR=(-1.0, 0.0, 0.0))
        call(lighting.autocad_add_light(position=[10, 0, 3000], intensity=800, kind="spot", direction=[1, 0, 0], coords="ucs"))
        args = plugin.calls[0][1]
        assert args["position"] == pytest.approx([100.0, 10.0, 3000.0])
        assert args["target"] == pytest.approx([100.0, 11.0, 3000.0])

    @pytest.mark.parametrize("units,words", [(0, "generic"), (1, "American")])
    def test_lighting_units_not_2_is_warned(self, plugin, units, words):
        plugin.doc.vars["LIGHTINGUNITS"] = units
        out = call(lighting.autocad_add_light(position=[0, 0, 3000], intensity=800))
        assert "LIGHTINGUNITS" in out["warning"] and words in out["warning"] and out["lighting_units"] == units
        assert plugin.calls, "the light is still made; only the units are warned about"

    def test_it_counts_as_a_change(self, plugin):
        before = connection.write_count()
        call(lighting.autocad_add_light(position=[0, 0, 3000], intensity=800))
        assert connection.write_count() == before + 1

    @pytest.mark.parametrize("kwargs,words", [
        ({"position": [0, 0]}, "[x, y, z]"),
        ({"kind": "spot", "hotspot": 60, "falloff": 50}, "falloff"),
        ({"kind": "distant", "intensity_unit": "cd"}, "lux"),
        ({"intensity_unit": "lux"}, "lm"),
        ({"target": [0, 0, 0]}, "point light"),
        ({"kind": "spot", "target": [0, 0, 0], "direction": [0, 0, -1]}, "not both"),
        ({"kind": "spot", "target": [0, 0, 3000]}, "no length"),
        ({"kelvin": 3000, "rgb": [255, 0, 0]}, "not both"),
        ({"rgb": [300, 0, 0]}, "0-255"),
        ({"web_file": "C:/x.ies"}, "kind='web'"),
    ])
    def test_refused_before_asking(self, plugin, kwargs, words):
        base = {"position": [0, 0, 3000], "intensity": 800}
        base.update(kwargs)
        assert words in error(lighting.autocad_add_light(**base))
        assert plugin.calls == []

    def test_without_the_plug_in_it_says_why(self, plugin, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        assert "--no-bridge" in error(lighting.autocad_add_light(position=[0, 0, 3000], intensity=800))


class TestLightingUnitsWords:
    def test_2_is_fine(self):
        assert lighting.lighting_units_warning(2) is None

    def test_unreadable_is_said(self):
        assert "could not be read" in lighting.lighting_units_warning(None)


# ---------------------------------------------------------------------------
# autocad_create_material
# ---------------------------------------------------------------------------


class TestCreateMaterial:
    def test_only_what_is_given_is_sent(self, plugin):
        out = call(materials.autocad_create_material(name="Laterite", diffuse_rgb=[178, 84, 52], glossiness=0.1))
        assert plugin.calls == [("create_material", {
            "name": "Laterite",
            "diffuse_rgb": [178, 84, 52],
            "glossiness": 0.1,
            "replace": False,
        })]
        assert out["created"] is True and out["in_drawing"] is True
        assert "autocad_apply_material(material='Laterite'" in out["next"]

    def test_glass(self, plugin):
        call(materials.autocad_create_material(name="Glass", transparency=0.9, refraction_index=1.5, reflectivity=0.1))
        args = plugin.calls[0][1]
        assert args["opacity"] == pytest.approx(0.1) and args["refraction_index"] == 1.5 and args["reflectivity"] == 0.1

    def test_a_warm_led_strip_glows_in_its_kelvin_colour(self, plugin):
        out = call(materials.autocad_create_material(name="LED Strip 3000K", luminance=2000, glow_kelvin=3000))
        args = plugin.calls[0][1]
        assert args["luminance"] == 2000 and args["diffuse_rgb"] == kelvin_to_rgb(3000)
        assert out["glow_rgb"] == kelvin_to_rgb(3000)

    def test_texture_and_bump_must_be_real_images(self, plugin, tmp_path):
        image = tmp_path / "teak.jpg"
        assert "no file" in error(materials.autocad_create_material(name="Teak", texture=str(image)))
        image.write_bytes(b"\xff\xd8")
        (tmp_path / "notes.txt").write_text("x")
        assert "image" in error(materials.autocad_create_material(name="Teak", texture=str(tmp_path / "notes.txt")))
        call(materials.autocad_create_material(name="Teak", texture=str(image), bump=str(image), bump_amount=0.5))
        args = plugin.calls[0][1]
        assert args["texture"] == str(image) and args["bump"] == str(image) and args["bump_amount"] == 0.5

    def test_metallic_is_sent_only_when_asked(self, plugin):
        call(materials.autocad_create_material(name="Brass", diffuse_rgb=[181, 166, 66], metallic=True))
        assert plugin.calls[0][1]["metallic"] is True

    def test_replace_is_passed_on(self, plugin):
        call(materials.autocad_create_material(name="Laterite", diffuse_rgb=[1, 2, 3], replace=True))
        assert plugin.calls[0][1]["replace"] is True

    def test_it_can_be_applied_straight_after(self, plugin):
        """autocad_apply_material looks the name up in the drawing's materials, case aside."""
        call(materials.autocad_create_material(name="Laterite", diffuse_rgb=[178, 84, 52]))
        assert materials.match_name("laterite", materials.material_names(plugin.doc)) == "Laterite"

    def test_not_read_back_is_a_warning_not_an_error(self, plugin, monkeypatch):
        """Made is made: an error would send the chat round to make it twice."""
        monkeypatch.setattr(materials, "material_names", lambda doc: ["Global"])
        out = call(materials.autocad_create_material(name="Laterite", diffuse_rgb=[1, 2, 3]))
        assert out["in_drawing"] is False and "do not make it again" in out["warning"]

    @pytest.mark.parametrize("kwargs,words", [
        ({"name": "ByLayer"}, "own material"),
        ({"name": "Bad:Name"}, "does not allow"),
        ({"diffuse_rgb": [1, 2]}, "0-255"),
        ({"diffuse_rgb": [1, 2, 3], "glow_kelvin": 3000}, "not both"),
        ({"refraction_index": 1.5}, "transparency"),
    ])
    def test_refused_before_asking(self, plugin, kwargs, words):
        base = {"name": "Laterite"}
        base.update(kwargs)
        assert words in error(materials.autocad_create_material(**base))
        assert plugin.calls == []


# ---------------------------------------------------------------------------
# Colour temperature
# ---------------------------------------------------------------------------


class TestKelvin:
    def test_warm_white_is_warm_and_daylight_is_near_white(self):
        warm = kelvin_to_rgb(3000)
        assert warm[0] == 255 and warm[0] > warm[1] > warm[2]
        day = kelvin_to_rgb(6500)
        assert min(day) >= 240

    def test_hotter_is_bluer(self):
        assert kelvin_to_rgb(10000)[2] == 255 and kelvin_to_rgb(10000)[0] < 255

    @pytest.mark.parametrize("kelvin", [500, 30000])
    def test_outside_autocads_range_is_refused(self, kelvin):
        with pytest.raises(AutocadError):
            kelvin_to_rgb(kelvin)


def test_levels():
    assert risk_of("autocad_add_light") is Risk.CHANGE
    assert risk_of("autocad_create_material") is Risk.CHANGE


# ---------------------------------------------------------------------------
# autocad_save_view(from_screen=true): a 3D camera view for the render
# ---------------------------------------------------------------------------


class View:
    def __init__(self, name, direction=(-1.0, -1.0, 1.0)):
        self.Name, self.Direction = name, direction
        self.Center, self.Width, self.Height = (0.0, 0.0, 0.0), 8000.0, 6000.0
        self.deleted = False

    def Delete(self):
        self.deleted = True


class Views:
    def __init__(self, *names):
        self.items = [View(n) for n in names]

    @property
    def Count(self):
        return len([v for v in self.items if not v.deleted])

    def Item(self, i):
        return [v for v in self.items if not v.deleted][i]


class ViewDoc:
    """Types -VIEW like AutoCAD: a view of that name appears, unless it stalls."""

    def __init__(self, *names, stalls=False):
        self.Views = Views(*names)
        self.sent: list[str] = []
        self.stalls = stalls

    def SendCommand(self, text):
        self.sent.append(text)
        if text.startswith("_.-VIEW _Save ") and not self.stalls:
            self.Views.items.append(View(text.split()[-1]))

    def GetVariable(self, name):
        assert name == "CMDACTIVE"
        return 1 if self.stalls and self.sent[-1].startswith("_.-VIEW") else 0

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def screen(monkeypatch):
    from autocad_mcp.tools import views

    def make(*names, stalls=False):
        doc = ViewDoc(*names, stalls=stalls)
        monkeypatch.setattr(views, "run", _now)
        monkeypatch.setattr(views, "get_doc", lambda: doc)
        monkeypatch.setattr(views, "require_idle", lambda d: None)
        monkeypatch.setattr(views, "VIEW_COMMAND_WAIT_S", 0.05)
        return doc, views

    return make


class TestSaveTheScreenView:
    def test_it_types_view_save_and_reads_the_3d_view_back(self, screen):
        doc, views = screen()
        out = call(views.autocad_save_view(name="LIVING-3D", from_screen=True))
        assert doc.sent == ["_.-VIEW _Save LIVING-3D\n"]
        assert out["saved"] == "LIVING-3D" and out["from"] == "the screen"
        assert out["view"]["plan"] is False

    def test_an_existing_name_needs_replace(self, screen):
        doc, views = screen("LIVING-3D")
        assert "replace=true" in error(views.autocad_save_view(name="LIVING-3D", from_screen=True))
        assert doc.sent == []
        out = call(views.autocad_save_view(name="living-3d", from_screen=True, replace=True))
        assert out["replaced"] is True and doc.Views.items[0].deleted

    def test_a_stalled_command_is_cancelled_and_said(self, screen):
        doc, views = screen(stalls=True)
        assert "did not finish" in error(views.autocad_save_view(name="LIVING-3D", from_screen=True))
        assert doc.sent[-1] == "\x1b\x1b"

    @pytest.mark.parametrize("kwargs,words", [
        ({"name": "LIVING 3D"}, "space"),
        ({"name": "A", "corner1": [0, 0], "corner2": [1, 1]}, "no corners"),
        ({"name": "A", "handles": ["2A"]}, "no corners"),
    ])
    def test_refused_before_typing(self, screen, kwargs, words):
        doc, views = screen()
        assert words in error(views.autocad_save_view(from_screen=True, **kwargs))
        assert doc.sent == []
