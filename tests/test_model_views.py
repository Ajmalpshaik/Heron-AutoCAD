"""Flat views, a section plane, surfaces, meshes and super hatch tiles (no AutoCAD).

All of these are the plug-in's own operations (D-95): FLATSHOT, SECTIONPLANE,
PLANESURF, SURFNETWORK, MESH and Express Tools' image / xref / wipeout
SUPERHATCH have no Automation call. What is checked here is everything up to
the pipe: what each tool asks the plug-in for, in world terms, and what is
refused before AutoCAD is asked at all. The geometry the plug-in works out
itself (which way a view looks, how views are set out, where a section plane
runs) is tested in the bridge's own tests (SectionMathTests.cs).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, sections, solid_edits, superhatch, surfaces


class Found:
    def __init__(self, handle, name="AcDbBlockReference"):
        self.Handle, self.ObjectName, self.Layer = handle, name, "0"
        self.Document = self

    def HandleToObject(self, handle):
        return Found(handle, self.ObjectName)


class Doc:
    def __init__(self):
        self.ucs = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))

    def GetVariable(self, name):
        return dict(zip(("UCSORG", "UCSXDIR", "UCSYDIR"), self.ucs, strict=True))[name]

    def HandleToObject(self, handle):
        return Found(handle)


class Plugin:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.reply: dict = {"created": True, "handle": "7A"}

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        return self.reply


@pytest.fixture
def plugin(monkeypatch):
    fake = Plugin()
    doc = Doc()

    async def run(fn):
        return fn()

    for module in (sections, surfaces, solid_edits, superhatch):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    fake.doc = doc
    return fake


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


NEW_TOOLS = ("autocad_flatten_views", "autocad_section_plane", "autocad_add_surface", "autocad_add_mesh")


@pytest.mark.parametrize("name", NEW_TOOLS)
def test_every_new_tool_changes_the_drawing_so_needs_the_changes_padlock(name):
    assert risk_of(name) is Risk.CHANGE


# ---------------------------------------------------------------------------
# Flat views (#54)
# ---------------------------------------------------------------------------


class TestFlattenViews:
    def test_by_default_front_top_and_right_third_angle(self, plugin):
        out = call(sections.autocad_flatten_views(handles=["2A"], insert_at=[5000, 0], layer="M-SHOP"))
        operation, args = plugin.calls[0]
        assert operation == "flat_views"
        assert args == {"handles": ["2A"], "views": ["front", "top", "right"], "insert_at": [5000.0, 0.0, 0.0],
                        "projection": "third", "join": False, "tangent_edges": False, "layer": "M-SHOP"}
        assert out["handle"] == "7A" and out["verified"] is True

    def test_plan_is_the_top_view(self, plugin):
        call(sections.autocad_flatten_views(handles=["2A"], insert_at=[0, 0], views=["plan", "front"], projection="first"))
        args = plugin.calls[0][1]
        assert args["views"] == ["top", "front"] and args["projection"] == "first"

    def test_a_view_twice_is_refused_before_autocad_is_asked(self, plugin):
        assert "twice" in error(sections.autocad_flatten_views(handles=["2A"], insert_at=[0, 0], views=["top", "plan"]))
        assert plugin.calls == []

    def test_an_insert_point_must_be_a_point(self, plugin):
        assert "insert_at" in error(sections.autocad_flatten_views(handles=["2A"], insert_at=[0]))

    def test_the_insert_point_goes_through_the_ucs(self, plugin):
        plugin.doc.ucs = ((1000.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
        call(sections.autocad_flatten_views(handles=["2A"], insert_at=[0, 500], coords="ucs"))
        assert plugin.calls[0][1]["insert_at"] == pytest.approx([500.0, 0.0, 0.0])

    def test_join_gap_and_name_are_passed_on(self, plugin):
        call(sections.autocad_flatten_views(handles=["2A", "2B"], insert_at=[0, 0], join=True, gap=250, name=" SPOOL-1 "))
        args = plugin.calls[0][1]
        assert args["join"] is True and args["gap"] == 250.0 and args["name"] == "SPOOL-1"


    def test_hidden_lines_are_asked_for_only_when_wanted(self, plugin):
        plugin.reply = {"created": True, "handle": "7A", "hidden_layer": "HIDDEN", "hidden_linetype": "ByLayer",
                        "views": [{"view": "front", "lines": 12, "hidden_lines": 4}]}
        out = call(sections.autocad_flatten_views(handles=["2A"], insert_at=[0, 0], hidden_lines=True))
        args = plugin.calls[0][1]
        assert args["hidden_lines"] is True and "hidden_layer" not in args
        assert "warning" not in out

    def test_a_hidden_layer_is_passed_on_trimmed(self, plugin):
        plugin.reply = {"created": True, "handle": "7A", "hidden_layer": "M-SHOP-HID"}
        call(sections.autocad_flatten_views(handles=["2A"], insert_at=[0, 0], hidden_lines=True, hidden_layer=" M-SHOP-HID "))
        assert plugin.calls[0][1]["hidden_layer"] == "M-SHOP-HID"

    def test_a_hidden_layer_without_hidden_lines_is_refused_before_autocad_is_asked(self, plugin):
        assert "hidden_lines=true" in error(sections.autocad_flatten_views(handles=["2A"], insert_at=[0, 0], hidden_layer="HID"))
        assert plugin.calls == []

    def test_an_older_plugin_that_ignored_hidden_lines_is_said(self, plugin):
        # The reply of a plug-in from before hidden lines: no hidden_layer.
        out = call(sections.autocad_flatten_views(handles=["2A"], insert_at=[0, 0], hidden_lines=True))
        assert "without hidden lines" in out["warning"] and "Ctrl+Z" in out["warning"]


# ---------------------------------------------------------------------------
# A section plane (#109)
# ---------------------------------------------------------------------------


class TestSectionPlane:
    def test_two_points_cut_every_solid_by_default(self, plugin):
        call(sections.autocad_section_plane(points=[[0, 0], [10000, 0]], insert_at=[0, -5000]))
        operation, args = plugin.calls[0]
        assert operation == "section_plane"
        assert args == {"points": [[0.0, 0.0, 0.0], [10000.0, 0.0, 0.0]], "insert_at": [0.0, -5000.0, 0.0],
                        "hatch": True, "background": True, "keep_plane": True}

    def test_three_points_a_side_and_the_solids(self, plugin):
        call(sections.autocad_section_plane(points=[[0, 0, 2700], [1, 0, 2700], [0, 1, 2700]], insert_at=[0, 0],
                                            look_towards=[0, 0, 0], handles=["2A", "2B"], hatch=False, name="PLAN-2700",
                                            plane_layer="M-SECT"))
        args = plugin.calls[0][1]
        assert args["look_towards"] == [0.0, 0.0, 0.0] and args["handles"] == ["2A", "2B"]
        assert args["hatch"] is False and args["name"] == "PLAN-2700" and args["plane_layer"] == "M-SECT"

    def test_one_point_or_four_is_refused_before_autocad_is_asked(self, plugin):
        for points in ([[0, 0]], [[0, 0], [1, 0], [0, 1], [1, 1]]):
            error(sections.autocad_section_plane(points=points, insert_at=[0, 0]))
        assert plugin.calls == []

    def test_a_bad_point_is_named(self, plugin):
        assert "points[1]" in error(sections.autocad_section_plane(points=[[0, 0], [1, 2, 3, 4]], insert_at=[0, 0]))

    def test_four_points_say_jogged(self, plugin):
        assert "jogged=true" in error(sections.autocad_section_plane(points=[[0, 0], [1, 0], [1, 1], [2, 1]], insert_at=[0, 0]))

    def test_a_jogged_line_goes_as_its_corners_not_as_points(self, plugin):
        corners = [[-500, 500], [2000, 500], [2000, 2500], [4500, 2500]]
        call(sections.autocad_section_plane(points=corners, insert_at=[0, -5000], jogged=True, look_towards=[0, 9000]))
        operation, args = plugin.calls[0]
        assert operation == "section_plane"
        # Never "points": an older plug-in would cut a plane through the first three corners.
        assert "points" not in args
        assert args["section_line"] == [[-500.0, 500.0, 0.0], [2000.0, 500.0, 0.0], [2000.0, 2500.0, 0.0], [4500.0, 2500.0, 0.0]]
        assert args["look_towards"] == [0.0, 9000.0, 0.0]

    def test_a_jogged_line_of_two_points_is_refused_before_autocad_is_asked(self, plugin):
        assert "leave jogged off" in error(sections.autocad_section_plane(points=[[0, 0], [1, 0]], insert_at=[0, 0], jogged=True))
        assert plugin.calls == []

    def test_a_jogged_lines_corners_go_through_the_ucs(self, plugin):
        plugin.doc.ucs = ((1000.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
        call(sections.autocad_section_plane(points=[[0, 0], [100, 0], [100, 50]], insert_at=[0, 0], jogged=True, coords="ucs"))
        assert plugin.calls[0][1]["section_line"] == [pytest.approx([1000.0, 0.0, 0.0]), pytest.approx([1000.0, 100.0, 0.0]),
                                                      pytest.approx([950.0, 100.0, 0.0])]

    def test_an_older_plugin_that_knows_no_jogs_says_to_update(self, plugin, monkeypatch):
        from autocad_mcp.core.errors import AutocadError

        def old(operation, args):
            raise AutocadError("A section plane needs two points (a vertical cut along the line between them, in plan) "
                               "or three (the plane through them). Nothing was changed.")

        monkeypatch.setattr(_shared, "plugin_runner", lambda: old)
        answer = error(sections.autocad_section_plane(points=[[0, 0], [1, 0], [1, 1]], insert_at=[0, 0], jogged=True))
        assert "older than jogged" in answer and "Nothing was changed" in answer

    def test_a_straight_cut_asks_exactly_what_it_asked_before(self, plugin):
        call(sections.autocad_section_plane(points=[[0, 0], [100, 0]], insert_at=[0, 0]))
        assert "section_line" not in plugin.calls[0][1]

    def test_points_go_through_the_ucs_in_full_3d(self, plugin):
        plugin.doc.ucs = ((0.0, 0.0, 1000.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        call(sections.autocad_section_plane(points=[[0, 0], [100, 0]], insert_at=[0, 0], coords="ucs"))
        args = plugin.calls[0][1]
        assert args["points"][0] == pytest.approx([0.0, 0.0, 1000.0])


# ---------------------------------------------------------------------------
# Surfaces and meshes (#58)
# ---------------------------------------------------------------------------


class TestSurfaces:
    def test_a_loft_surface_through_open_outlines(self, plugin):
        call(solid_edits.autocad_loft(sections=["2A", "2B"], surface=True))
        assert plugin.calls == [("loft_surface", {"sections": ["2A", "2B"], "ruled": False, "closed": False})]

    def test_a_loft_is_still_a_solid_by_default(self, plugin):
        call(solid_edits.autocad_loft(sections=["2A", "2B"]))
        assert plugin.calls[0][0] == "loft"

    def test_planar_from_outlines(self, plugin):
        call(surfaces.autocad_add_surface(kind="planar", outlines=["2A", "2B"], layer="A-CLNG"))
        assert plugin.calls == [("planar_surface", {"outlines": ["2A", "2B"], "layer": "A-CLNG"})]

    def test_planar_from_two_corners_in_world_terms(self, plugin):
        call(surfaces.autocad_add_surface(kind="planar", corners=[[0, 0, 2700], [3000, 2000, 2700]]))
        assert plugin.calls[0][1]["corners"] == [[0.0, 0.0, 2700.0], [3000.0, 2000.0, 2700.0]]

    def test_planar_takes_outlines_or_corners_not_both(self, plugin):
        error(surfaces.autocad_add_surface(kind="planar", outlines=["2A"], corners=[[0, 0], [1, 1]]))
        error(surfaces.autocad_add_surface(kind="planar"))
        assert plugin.calls == []

    def test_network_needs_two_curves_each_way(self, plugin):
        assert "two u_curves" in error(surfaces.autocad_add_surface(kind="network", u_curves=["1"], v_curves=["3", "4"]))
        call(surfaces.autocad_add_surface(kind="network", u_curves=["1", "2"], v_curves=["3", "4"]))
        assert plugin.calls == [("network_surface", {"u_curves": ["1", "2"], "v_curves": ["3", "4"]})]

    def test_network_takes_no_outlines(self, plugin):
        assert "planar" in error(surfaces.autocad_add_surface(kind="network", outlines=["2A"], u_curves=["1", "2"], v_curves=["3", "4"]))


class TestMeshes:
    def test_a_box_mesh_with_its_sizes(self, plugin):
        call(surfaces.autocad_add_mesh(shape="box", base=[0, 0], length=1000, width=600, height=400, smoothness=2))
        operation, args = plugin.calls[0]
        assert operation == "add_mesh"
        assert args == {"smoothness": 2, "shape": "box", "base": [0.0, 0.0, 0.0], "length": 1000.0, "width": 600.0, "height": 400.0}

    def test_a_cone_and_a_pyramid_take_a_top_radius(self, plugin):
        call(surfaces.autocad_add_mesh(shape="pyramid", base=[0, 0, 0], radius=500, height=800, top_radius=100, sides=6))
        args = plugin.calls[0][1]
        assert args["top_radius"] == 100 and args["sides"] == 6

    def test_a_missing_size_is_named(self, plugin):
        assert "missing tube_radius" in error(surfaces.autocad_add_mesh(shape="torus", base=[0, 0], radius=500))

    def test_a_size_the_shape_does_not_take_is_refused(self, plugin):
        assert "does not take" in error(surfaces.autocad_add_mesh(shape="sphere", base=[0, 0], radius=5, height=3))

    def test_a_torus_that_closes_on_itself_is_refused(self, plugin):
        assert "closes on itself" in error(surfaces.autocad_add_mesh(shape="torus", base=[0, 0], radius=5, tube_radius=5))

    def test_a_mesh_of_a_solid(self, plugin):
        call(surfaces.autocad_add_mesh(from_handle="2A", smoothness=1))
        assert plugin.calls == [("add_mesh", {"smoothness": 1, "from_handle": "2A"})]

    def test_a_shape_and_an_object_together_is_refused(self, plugin):
        error(surfaces.autocad_add_mesh(shape="box", from_handle="2A"))
        error(surfaces.autocad_add_mesh(from_handle="2A", radius=4))
        assert plugin.calls == []


# ---------------------------------------------------------------------------
# Super hatch tiles (#57)
# ---------------------------------------------------------------------------


class TestSuperHatchTiles:
    def test_an_image_tile_with_its_width(self, plugin, tmp_path):
        picture = tmp_path / "stone.jpg"
        picture.write_bytes(b"\xff\xd8")
        call(superhatch.autocad_super_hatch(boundary="2A", image=str(picture), image_size=[600]))
        operation, args = plugin.calls[0]
        assert operation == "super_hatch"
        assert args["tile_kind"] == "image" and args["image"] == str(picture) and args["image_size"] == [600.0]
        assert "block" not in args

    def test_an_image_needs_its_size_and_its_file(self, plugin, tmp_path):
        picture = tmp_path / "stone.jpg"
        picture.write_bytes(b"\xff\xd8")
        assert "image_size" in error(superhatch.autocad_super_hatch(boundary="2A", image=str(picture)))
        assert "no image" in error(superhatch.autocad_super_hatch(boundary="2A", image=str(tmp_path / "gone.png"), image_size=[600]))
        assert plugin.calls == []

    def test_an_xref_by_file_or_by_name(self, plugin, tmp_path):
        drawing = tmp_path / "CT-600.dwg"
        drawing.write_bytes(b"AC1032")
        call(superhatch.autocad_super_hatch(boundary="2A", xref=str(drawing)))
        call(superhatch.autocad_super_hatch(boundary="2A", xref="CT-600"))
        assert [c[1]["tile_kind"] for c in plugin.calls] == ["xref", "xref"]
        assert plugin.calls[1][1]["xref"] == "CT-600"

    def test_an_xref_file_that_is_not_there_is_refused(self, plugin, tmp_path):
        assert "no drawing" in error(superhatch.autocad_super_hatch(boundary="2A", xref=str(tmp_path / "gone.dwg")))

    def test_a_wipeout_tile(self, plugin):
        call(superhatch.autocad_super_hatch(boundary="2A", wipeout="3C", spacing=[600, 600]))
        args = plugin.calls[0][1]
        assert args["tile_kind"] == "wipeout" and args["wipeout"] == "3C"

    def test_one_tile_and_only_one(self, plugin):
        assert "got none" in error(superhatch.autocad_super_hatch(boundary="2A"))
        assert "got block, wipeout" in error(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", wipeout="3C"))
        assert "image tile only" in error(superhatch.autocad_super_hatch(boundary="2A", block="PAVER", image_size=[600]))
        assert plugin.calls == []

    def test_a_block_hatch_asks_exactly_as_it_did_before(self, plugin):
        """An older plug-in knows no tile_kind: a block hatch must not send one."""
        call(superhatch.autocad_super_hatch(boundary="2A", block="PAVER"))
        assert "tile_kind" not in plugin.calls[0][1]
