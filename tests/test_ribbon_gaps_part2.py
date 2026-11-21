"""Part 2 of the smaller ribbon gaps (#119): no AutoCAD (D-110, D-111).

Associative arrays and the geographic location go to the Heron plug-in, so
what is checked is what each tool asks it for and every refusal before it is
asked. Tiled model viewports and hyperlinks are COM, checked against fake
COM objects. None of this is a live proof: NEEDS-CHECKING group AQ is.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.acad import tiles
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, arrays, geo_location, hyperlinks, model_viewports


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


class TestLevels:
    @pytest.mark.parametrize("tool,level", [
        ("autocad_associative_array", Risk.CHANGE),
        ("autocad_hyperlinks", Risk.CHANGE),
        ("autocad_geo_location", Risk.CHANGE),
        ("autocad_list_hyperlinks", Risk.READ),
        ("autocad_get_geo_location", Risk.READ),
        # The screen, not the drawing: no Changes padlock.
        ("autocad_model_viewports", Risk.VIEW),
    ])
    def test_each_tool_has_its_level(self, tool, level):
        assert risk_of(tool) is level


# ---------------------------------------------------------------------------
# Fakes shared by the plug-in tools
# ---------------------------------------------------------------------------


class Found:
    def __init__(self, handle):
        self.Handle, self.ObjectName, self.Layer = handle, "AcDbBlockReference", "0"
        self.Document = self

    def HandleToObject(self, handle):
        return Found(handle)


class Doc:
    def __init__(self):
        self.ucs = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        self.vars = {"LATITUDE": 37.795, "LONGITUDE": -122.394, "TILEMODE": 1}
        self.set: list[tuple[str, object]] = []
        self.marks = 0

    def GetVariable(self, name):
        if name in ("UCSORG", "UCSXDIR", "UCSYDIR"):
            return dict(zip(("UCSORG", "UCSXDIR", "UCSYDIR"), self.ucs, strict=True))[name]
        return self.vars[name]

    def SetVariable(self, name, value):
        self.set.append((name, value))
        self.vars[name] = value

    def HandleToObject(self, handle):
        return Found(handle)

    def StartUndoMark(self):
        self.marks += 1

    def EndUndoMark(self):
        pass


class Plugin:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.reply: dict = {"created": True, "handle": "9F"}

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        return self.reply


@pytest.fixture
def plugin(monkeypatch):
    fake = Plugin()
    doc = Doc()
    for module in (arrays, geo_location):
        monkeypatch.setattr(module, "run", _now)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        if hasattr(module, "require_idle"):
            monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    fake.doc = doc
    return fake


# ---------------------------------------------------------------------------
# Associative arrays (#175, D-110)
# ---------------------------------------------------------------------------


class TestAssociativeArray:
    def test_a_path_array_sends_the_path_and_the_spacing(self, plugin):
        plugin.reply = {"created": True, "handle": "9F", "associative": True, "items": 7}
        out = call(arrays.autocad_associative_array(handles=["2A"], pattern="path", path="3B", spacing=1500))
        operation, args = plugin.calls[0]
        assert operation == "associative_array"
        assert args == {"handles": ["2A"], "pattern": "path", "path": "3B", "spacing": 1500.0, "align_items": True}
        assert out["handle"] == "9F" and out["verified"] is True and out["items"] == 7

    def test_a_path_array_by_count_sends_no_spacing(self, plugin):
        call(arrays.autocad_associative_array(handles=["2A"], pattern="path", path="3B", count=6, align_items=False))
        args = plugin.calls[0][1]
        assert args["count"] == 6 and "spacing" not in args and args["align_items"] is False

    def test_a_grid_sends_its_rows_columns_and_spacings(self, plugin):
        call(arrays.autocad_associative_array(handles=["2A", "2A", "2B"], pattern="rectangular", rows=4, columns=6,
                                              row_spacing=1200, column_spacing=1200, layer="M-DIFF"))
        args = plugin.calls[0][1]
        assert args["handles"] == ["2A", "2B"]
        assert (args["rows"], args["columns"], args["row_spacing"], args["column_spacing"]) == (4, 6, 1200.0, 1200.0)
        assert args["layer"] == "M-DIFF"

    def test_a_ring_sends_the_angle_in_radians_and_the_centre_in_world(self, plugin):
        plugin.doc.ucs = ((1000.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
        call(arrays.autocad_associative_array(handles=["2A"], pattern="polar", count=8, center=[0, 0], fill_angle=180, coords="ucs"))
        args = plugin.calls[0][1]
        assert args["count"] == 8 and args["rotate_items"] is True
        assert args["fill_angle"] == pytest.approx(math.pi)
        assert args["center"] == pytest.approx([1000.0, 0.0, 0.0])

    def test_the_base_point_is_turned_into_world_too(self, plugin):
        plugin.doc.ucs = ((0.0, 500.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        call(arrays.autocad_associative_array(handles=["2A"], pattern="path", path="3B", count=3, base_point=[10, 20], coords="ucs"))
        assert plugin.calls[0][1]["base_point"] == pytest.approx([10.0, 520.0, 0.0])

    @pytest.mark.parametrize("kwargs,words", [
        ({"pattern": "path", "count": 3}, "needs 'path'"),
        ({"pattern": "path", "path": "3B"}, "'count'"),
        ({"pattern": "rectangular"}, "1 x 1"),
        ({"pattern": "rectangular", "rows": 3}, "row_spacing"),
        ({"pattern": "rectangular", "columns": 3}, "column_spacing"),
        ({"pattern": "rectangular", "rows": 200, "columns": 200, "row_spacing": 1, "column_spacing": 1}, "at most"),
        ({"pattern": "polar", "count": 4}, "'center'"),
        ({"pattern": "polar", "center": [0, 0]}, "'count'"),
        ({"pattern": "path", "path": "3B", "count": 3, "base_point": [1]}, "base_point"),
    ])
    def test_a_pattern_without_its_numbers_is_refused_before_the_plug_in(self, plugin, kwargs, words):
        assert words in error(arrays.autocad_associative_array(handles=["2A"], **kwargs))
        assert plugin.calls == []

    def test_the_plug_ins_refusal_reaches_the_chat(self, plugin, monkeypatch):
        def refuse(operation, args):
            raise AutocadError("AutoCAD built the array somewhere other than asked. Nothing was changed.")

        monkeypatch.setattr(_shared, "plugin_runner", lambda: refuse)
        text = error(arrays.autocad_associative_array(handles=["2A"], pattern="path", path="3B", count=3))
        assert "somewhere other than asked" in text and "Nothing was changed" in text

    def test_without_the_plug_in_it_says_why(self, plugin, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        assert "plug-in" in error(arrays.autocad_associative_array(handles=["2A"], pattern="path", path="3B", count=3))

    def test_it_is_found_for_a_path_array(self):
        from test_find_tool import found

        assert found("hangers along the duct as a path array")[:1] == ["autocad_associative_array"]
        assert found("an array I can edit later")[:1] == ["autocad_associative_array"]


# ---------------------------------------------------------------------------
# Tiled model viewports (#176, D-111)
# ---------------------------------------------------------------------------


class TestTileWords:
    def test_split_numbers_are_autodesks(self):
        # From Autodesk's interop assembly: AcViewportSplitType.
        assert tiles.LAYOUTS["two_horizontal"] == 0 and tiles.LAYOUTS["two_vertical"] == 1
        assert tiles.LAYOUTS["three_below"] == 7 and tiles.LAYOUTS["four"] == 8
        assert tiles.LAYOUTS["one"] is None
        assert set(tiles.LAYOUTS) == set(tiles.EXPECTED) == set(tiles.TILE_COUNT)

    @pytest.mark.parametrize("corners,words", [
        ([((0, 0), (1, 1))], "one viewport"),
        ([((0, 0), (0.5, 1)), ((0.5, 0), (1, 1))], "two, side by side"),
        ([((0, 0.5), (1, 1)), ((0, 0), (1, 0.5))], "two, one above the other"),
        ([((0, 0), (0.5, 1)), ((0.5, 0.5), (1, 1)), ((0.5, 0), (1, 0.5))], "three, the big one on the left"),
        ([((0.5, 0), (1, 1)), ((0, 0.5), (0.5, 1)), ((0, 0), (0.5, 0.5))], "three, the big one on the right"),
        ([((0, 0.5), (1, 1)), ((0, 0), (0.5, 0.5)), ((0.5, 0), (1, 0.5))], "three, the big one on top"),
        ([((0, 0), (1, 0.5)), ((0, 0.5), (0.5, 1)), ((0.5, 0.5), (1, 1))], "three, the big one at the bottom"),
        ([((0, 0), (1 / 3, 1)), ((1 / 3, 0), (2 / 3, 1)), ((2 / 3, 0), (1, 1))], "three, side by side"),
        ([((0, 0), (1, 1 / 3)), ((0, 1 / 3), (1, 2 / 3)), ((0, 2 / 3), (1, 1))], "three, one above another"),
        ([((0, 0), (0.5, 0.5)), ((0.5, 0), (1, 0.5)), ((0, 0.5), (0.5, 1)), ((0.5, 0.5), (1, 1))], "four, two by two"),
        ([((0, 0), (0.2, 1)), ((0.2, 0), (1, 0.3)), ((0.2, 0.3), (1, 0.6)), ((0.2, 0.6), (1, 0.8)), ((0.2, 0.8), (1, 1))], "5 viewports"),
    ])
    def test_the_tiles_are_described_from_their_corners(self, corners, words):
        assert tiles.describe(corners) == words


class Viewport:
    def __init__(self, store, name, lower=(0.0, 0.0), upper=(1.0, 1.0)):
        self.store, self.Name = store, name
        self.LowerLeftCorner, self.UpperRightCorner = lower, upper
        self.Direction, self.Target, self.Center = (0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (5000.0, 3000.0)
        self.Height, self.Width = 8000.0, 12000.0
        self.splits: list[int] = []

    def Split(self, code):
        self.splits.append(code)
        self.store.split_as[code](self)


class Viewports:
    def __init__(self, doc):
        self.doc = doc
        self.items = [Viewport(self, "*Active")]
        self.deleted: list[str] = []
        self.added: list[Viewport] = []
        # What AutoCAD shows for each split code; a test can make it lie.
        self.split_as = {
            0: lambda vp: self._tile(vp, [((0, 0.5), (1, 1)), ((0, 0), (1, 0.5))]),
            1: lambda vp: self._tile(vp, [((0, 0), (0.5, 1)), ((0.5, 0), (1, 1))]),
            8: lambda vp: self._tile(vp, [((0, 0), (0.5, 0.5)), ((0.5, 0), (1, 0.5)), ((0, 0.5), (0.5, 1)), ((0.5, 0.5), (1, 1))]),
        }

    def _tile(self, vp, boxes):
        vp.tiles = boxes

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index]

    def DeleteConfiguration(self, name):
        self.deleted.append(name)

    def Add(self, name):
        vp = Viewport(self, name)
        vp.tiles = [((0, 0), (1, 1))]
        self.added.append(vp)
        return vp

    def activate(self, vp):
        self.items = [Viewport(self, "*Active", lower, upper) for lower, upper in vp.tiles]
        self.doc._active = self.items[0]


class TileDoc:
    def __init__(self):
        self.Viewports = Viewports(self)
        self._active = self.Viewports.items[0]
        self.vars = {"TILEMODE": 1}

    def GetVariable(self, name):
        return self.vars[name]

    @property
    def ActiveViewport(self):
        return self._active

    @ActiveViewport.setter
    def ActiveViewport(self, vp):
        self.Viewports.activate(vp)


@pytest.fixture
def tile_doc(monkeypatch):
    doc = TileDoc()
    monkeypatch.setattr(model_viewports, "run", _now)
    monkeypatch.setattr(model_viewports, "get_doc", lambda: doc)
    monkeypatch.setattr(model_viewports, "require_idle", lambda d: None)
    return doc


class TestModelViewports:
    def test_two_side_by_side(self, tile_doc):
        out = call(model_viewports.autocad_model_viewports(layout="two_vertical"))
        added = tile_doc.Viewports.added[0]
        assert added.Name == "Heron" and added.splits == [1]
        assert tile_doc.Viewports.deleted == ["Heron"]
        assert out["tiles"] == 2 and out["arrangement"] == "two, side by side" and "warning" not in out
        assert sum(t["current"] for t in out["viewports"]) == 1

    def test_the_view_on_screen_is_carried_into_the_new_viewport(self, tile_doc):
        tile_doc._active.Center = (777.0, 888.0)
        tile_doc._active.Height = 4321.0
        call(model_viewports.autocad_model_viewports(layout="four"))
        added = tile_doc.Viewports.added[0]
        assert tuple(added.Center.value) == (777.0, 888.0) and added.Height == 4321.0

    def test_back_to_one_is_not_split(self, tile_doc):
        out = call(model_viewports.autocad_model_viewports(layout="one"))
        assert tile_doc.Viewports.added[0].splits == []
        assert out["tiles"] == 1 and out["arrangement"] == "one viewport"

    def test_without_a_layout_it_only_reads(self, tile_doc):
        out = call(model_viewports.autocad_model_viewports())
        assert tile_doc.Viewports.added == [] and tile_doc.Viewports.deleted == []
        assert out["tiles"] == 1 and out["layout"] is None

    def test_a_split_that_came_out_another_way_is_a_warning(self, tile_doc):
        tile_doc.Viewports.split_as[1] = tile_doc.Viewports.split_as[0]
        out = call(model_viewports.autocad_model_viewports(layout="two_vertical"))
        assert "side by side" in out["warning"] and "one above the other" in out["warning"]

    def test_a_layout_is_refused_and_nothing_changes(self, tile_doc):
        tile_doc.vars["TILEMODE"] = 0
        text = error(model_viewports.autocad_model_viewports(layout="four"))
        assert "Model tab" in text and "autocad_add_viewport" in text
        assert tile_doc.Viewports.added == []

    def test_an_unknown_layout_is_refused_by_name(self, tile_doc):
        assert "Error" in asyncio.run(model_viewports.autocad_model_viewports(layout="five"))


# ---------------------------------------------------------------------------
# Hyperlinks (#178, D-111)
# ---------------------------------------------------------------------------


class Link:
    def __init__(self, store, url, description="", location=""):
        self.store, self.URL, self.URLDescription, self.URLNamedLocation = store, url, description, location

    def Delete(self):
        self.store.items.remove(self)


class Links:
    def __init__(self, refuse=False):
        self.items: list[Link] = []
        self.refuse = refuse

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index]

    def Add(self, name, description, location):
        if self.refuse:
            raise OSError("On locked layer")
        self.items.append(Link(self, name, description, location))
        return self.items[-1]


class Linked:
    def __init__(self, handle, refuse=False):
        self.Handle, self.ObjectName, self.Layer = handle, "AcDbBlockReference", "M-AHU"
        self.Hyperlinks = Links(refuse)


class Selection:
    def __init__(self, doc):
        self.doc, self.found, self.filters = doc, [], []

    def Clear(self):
        self.found = []

    def Select(self, mode, p1=None, p2=None, codes=None, values=None):
        self.filters.append((mode, codes, values))
        self.found = [e for e in self.doc.objects.values() if e.Hyperlinks.Count]

    @property
    def Count(self):
        return len(self.found)

    def Item(self, index):
        return self.found[index]


class SelectionSets:
    def __init__(self, doc):
        self.sel = Selection(doc)

    def Item(self, name):
        return self.sel

    def Add(self, name):
        return self.sel


class LinkDoc:
    def __init__(self):
        self.objects = {"2A": Linked("2A"), "2B": Linked("2B"), "2C": Linked("2C", refuse=True)}
        self.SelectionSets = SelectionSets(self)
        self.marks = 0

    def HandleToObject(self, handle):
        return self.objects[handle]

    def StartUndoMark(self):
        self.marks += 1

    def EndUndoMark(self):
        pass


@pytest.fixture
def link_doc(monkeypatch):
    doc = LinkDoc()
    monkeypatch.setattr(hyperlinks, "run", _now)
    monkeypatch.setattr(hyperlinks, "get_doc", lambda: doc)
    monkeypatch.setattr(hyperlinks, "require_idle", lambda d: None)
    return doc


class TestHyperlinks:
    def test_set_puts_one_link_on_each_object_in_one_undo_step(self, link_doc):
        out = call(hyperlinks.autocad_hyperlinks(handles=["2A", "2B"], url="C:\\Submittals\\AHU-01.pdf", description="AHU-01 data sheet"))
        assert out["changed"] == 2 and link_doc.marks == 1
        link = link_doc.objects["2A"].Hyperlinks.items
        assert len(link) == 1 and link[0].URL == "C:\\Submittals\\AHU-01.pdf" and link[0].URLDescription == "AHU-01 data sheet"
        assert out["objects"][0]["after"] == [{"url": "C:\\Submittals\\AHU-01.pdf", "description": "AHU-01 data sheet", "location": ""}]

    def test_set_replaces_the_link_an_object_had(self, link_doc):
        links = link_doc.objects["2A"].Hyperlinks
        links.Add("https://old.example", "old", "")
        out = call(hyperlinks.autocad_hyperlinks(handles=["2A"], url="https://new.example"))
        assert [link.URL for link in links.items] == ["https://new.example"]
        assert out["objects"][0]["before"][0]["url"] == "https://old.example"

    def test_a_view_in_the_drawing_needs_only_the_location(self, link_doc):
        call(hyperlinks.autocad_hyperlinks(handles=["2A"], location="PLANT ROOM"))
        assert link_doc.objects["2A"].Hyperlinks.items[0].URLNamedLocation == "PLANT ROOM"

    def test_remove_takes_every_link_off(self, link_doc):
        link_doc.objects["2A"].Hyperlinks.Add("https://a", "", "")
        out = call(hyperlinks.autocad_hyperlinks(handles=["2A", "2B"], action="remove"))
        assert link_doc.objects["2A"].Hyperlinks.Count == 0
        assert out["changed"] == 1

    def test_an_object_that_refuses_is_listed_and_the_rest_are_done(self, link_doc):
        out = call(hyperlinks.autocad_hyperlinks(handles=["2A", "2C"], url="https://a"))
        assert out["handles"] == ["2A"] and out["failed"][0]["handle"] == "2C"
        assert "locked" in out["hint"]

    def test_set_without_a_target_is_refused_before_anything_changes(self, link_doc):
        assert "url" in error(hyperlinks.autocad_hyperlinks(handles=["2A"], description="no target"))
        assert link_doc.marks == 0

    def test_remove_with_a_url_is_refused(self, link_doc):
        assert "leave url" in error(hyperlinks.autocad_hyperlinks(handles=["2A"], action="remove", url="x"))

    def test_the_whole_drawing_is_searched_by_the_hyperlink_extended_data(self, link_doc):
        link_doc.objects["2B"].Hyperlinks.Add("https://b", "B", "")
        out = call(hyperlinks.autocad_list_hyperlinks())
        mode, codes, values = link_doc.SelectionSets.sel.filters[0]
        assert mode == 5 and list(codes.value) == [1001] and list(values.value) == ["PE_URL"]
        assert out["count"] == 1 and out["objects"][0]["handle"] == "2B"
        assert out["objects"][0]["links"] == [{"url": "https://b", "description": "B", "location": ""}]

    def test_listing_given_handles_reads_those_even_without_links(self, link_doc):
        out = call(hyperlinks.autocad_list_hyperlinks(handles=["2A"]))
        assert out["count"] == 1 and out["objects"][0]["links"] == []

    def test_the_listing_is_cut_to_the_limit_and_says_so(self, link_doc):
        for handle in ("2A", "2B"):
            link_doc.objects[handle].Hyperlinks.Add("https://x", "", "")
        out = call(hyperlinks.autocad_list_hyperlinks(limit=1))
        assert out["count"] == 2 and len(out["objects"]) == 1 and out["truncated"] is True


# ---------------------------------------------------------------------------
# Geographic location (#180, D-111)
# ---------------------------------------------------------------------------


GEO_REPLY = {
    "located": True, "made": True, "reference_form": "grid", "latitude": 25.29, "longitude": 51.53,
    "point": [0.0, 0.0, 0.0], "north_angle": math.radians(12), "coordinate_system": "WORLD-MERCATOR",
    "units": "Millimeters",
}


class TestGeoLocation:
    def test_the_site_is_sent_and_the_sun_moves_to_it(self, plugin):
        plugin.reply = dict(GEO_REPLY)
        out = call(geo_location.autocad_geo_location(latitude=25.29, longitude=51.53, north_angle=12))
        operation, args = plugin.calls[0]
        assert operation == "set_geo_location"
        assert args["latitude"] == 25.29 and args["longitude"] == 51.53 and args["point"] == [0.0, 0.0, 0.0]
        assert args["north_angle"] == pytest.approx(math.radians(12))
        assert "coordinate_system" not in args
        assert ("LATITUDE", 25.29) in plugin.doc.set and ("LONGITUDE", 51.53) in plugin.doc.set
        assert out["sun_place"] == {"latitude": 25.29, "longitude": 51.53, "moved": True}
        assert out["north_angle"] == pytest.approx(12)

    def test_without_a_place_it_takes_the_suns(self, plugin):
        plugin.doc.vars.update(LATITUDE=9.93, LONGITUDE=76.27)
        plugin.reply = dict(GEO_REPLY, latitude=9.93, longitude=76.27)
        out = call(geo_location.autocad_geo_location(point=[1000, 2000]))
        args = plugin.calls[0][1]
        assert (args["latitude"], args["longitude"]) == (9.93, 76.27)
        assert args["point"] == [1000.0, 2000.0, 0.0]
        assert plugin.doc.set == [] and out["sun_place"]["moved"] is False

    def test_autocads_san_francisco_default_is_not_taken_for_the_site(self, plugin):
        text = error(geo_location.autocad_geo_location())
        assert "San Francisco" in text and plugin.calls == []

    def test_one_of_latitude_and_longitude_is_refused(self, plugin):
        assert "both" in error(geo_location.autocad_geo_location(latitude=25.29))

    def test_on_a_turned_ucs_north_and_the_point_turn_with_it(self, plugin):
        # A UCS turned 90 degrees counter-clockwise: its +Y is the world's -X.
        plugin.doc.ucs = ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
        plugin.reply = dict(GEO_REPLY)
        call(geo_location.autocad_geo_location(latitude=25.29, longitude=51.53, point=[10, 0], north_angle=0, coords="ucs"))
        args = plugin.calls[0][1]
        assert args["point"] == pytest.approx([0.0, 10.0, 0.0])
        # North up the UCS screen is world -X: 270 degrees clockwise from world +Y.
        assert args["north_angle"] == pytest.approx(math.radians(270))

    def test_a_sun_place_that_will_not_move_is_said(self, plugin, monkeypatch):
        plugin.reply = dict(GEO_REPLY)

        def refuse(name, value):
            raise OSError("read only")

        monkeypatch.setattr(plugin.doc, "SetVariable", refuse)
        out = call(geo_location.autocad_geo_location(latitude=25.29, longitude=51.53))
        assert any("LATITUDE" in item for item in out["not_set"])
        assert out["sun_place"]["moved"] is False

    def test_remove_sends_only_the_action(self, plugin):
        plugin.reply = {"removed": True, "coordinate_system": "WORLD-MERCATOR"}
        out = call(geo_location.autocad_geo_location(action="remove"))
        assert plugin.calls == [("set_geo_location", {"action": "remove"})]
        assert out["removed"] is True

    def test_remove_with_a_place_is_refused(self, plugin):
        assert "leave the place" in error(geo_location.autocad_geo_location(action="remove", latitude=1, longitude=1))

    def test_reading_says_whether_the_sun_agrees(self, plugin):
        plugin.doc.vars.update(LATITUDE=25.29, LONGITUDE=51.53)
        plugin.reply = dict(GEO_REPLY)
        out = call(geo_location.autocad_get_geo_location())
        assert plugin.calls[0][0] == "geo_location"
        assert out["agrees"] is True and out["sun_place"]["autocad_default"] is False

    def test_reading_warns_when_the_sun_is_elsewhere(self, plugin):
        plugin.reply = dict(GEO_REPLY)
        out = call(geo_location.autocad_get_geo_location())
        assert out["agrees"] is False and out["sun_place"]["autocad_default"] is True
        assert "autocad_geo_location" in out["warning"]

    def test_reading_without_the_plug_in_still_gives_the_suns_place(self, plugin, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        out = call(geo_location.autocad_get_geo_location())
        assert out["located"] is None and "no-bridge" in out["location_note"]
        assert out["sun_place"]["latitude"] == 37.795

    def test_the_default_place_test(self):
        assert geo_location.is_autocad_default(37.795, -122.394)
        assert not geo_location.is_autocad_default(25.29, 51.53)
        assert not geo_location.is_autocad_default(None, None)
