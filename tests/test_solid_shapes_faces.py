"""Pyramid, polysolid and the rest of SOLIDEDIT, done by the plug-in (no AutoCAD).

COM has no call for a pyramid, a polysolid, or offsetting, tapering, moving
or deleting a solid's faces, imprinting or separating, so these tools hand the
work to the plug-in (D-40, D-112, D-113). What is checked here is everything
up to the pipe: what each tool asks the plug-in for, in which units and
directions, what is refused before AutoCAD is asked, and how the answers come
back to the chat. Whether AutoCAD does it right is NEEDS-CHECKING group AR.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest
from pydantic import ValidationError

from autocad_mcp.core.registry import mcp
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, primitives, register_all, solid_faces

register_all()


class Found:
    def __init__(self, handle, name="AcDb3dSolid"):
        self.Handle, self.ObjectName, self.Layer = handle, name, "0"
        self.Document = self

    def HandleToObject(self, handle):
        return Found(handle, self.ObjectName)


class Doc:
    def __init__(self, ucs=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))):
        self.ucs = ucs

    def GetVariable(self, name):
        return dict(zip(("UCSORG", "UCSXDIR", "UCSYDIR"), self.ucs, strict=True))[name]

    def HandleToObject(self, handle):
        return Found(handle)


class Plugin:
    """Stands in for the plug-in: records each operation, answers by operation."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.replies: dict[str, dict] = {}
        self.failing: set[str] = set()

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        if operation in self.failing:
            raise RuntimeError("AutoCAD is busy")
        return self.replies.get(operation, {"created": True, "handle": "3B", "volume": 1.0})


@pytest.fixture
def plugin(monkeypatch):
    fake = Plugin()
    doc = Doc()

    async def run(fn):
        return fn()

    for module in (primitives, solid_faces):
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


def schema_refuses(tool_name, **given):
    """True when the MCP layer turns these arguments away, before the tool runs at all."""
    model = mcp._tool_manager.get_tool(tool_name).fn_metadata.arg_model
    try:
        model.model_validate(given)
    except ValidationError:
        return True
    return False


# A plan UCS turned 90 degrees and moved to (1000, 0): its X is world Y.
TURNED = ((1000.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))


class TestPyramid:
    def test_a_square_pyramid_by_its_base_centre(self, plugin):
        out = call(primitives.autocad_add_pyramid(base=[100, 200], radius=300, height=900))
        operation, args = plugin.calls[0]
        assert operation == "add_pyramid"
        assert args == {
            "base": [100.0, 200.0, 0.0],
            "radius": 300.0,
            "height": 900.0,
            "sides": 4,
            "top_radius": 0.0,
            "radius_to": "side",
            "rotation": 0.0,
        }
        assert out["created"] is True and out["handle"] == "3B" and out["rotation"] == 0.0

    def test_a_hopper_and_a_turn_in_degrees(self, plugin):
        call(primitives.autocad_add_pyramid(base=[0, 0, 3000], radius=150, top_radius=600, height=900, rotation=30, sides=6, radius_to="corner"))
        args = plugin.calls[0][1]
        assert args["top_radius"] == 600.0 and args["sides"] == 6 and args["radius_to"] == "corner"
        assert args["rotation"] == pytest.approx(math.radians(30))
        assert args["base"] == [0.0, 0.0, 3000.0]

    def test_on_a_turned_ucs_the_base_and_the_turn_follow_it(self, plugin):
        plugin.doc.ucs = TURNED
        out = call(primitives.autocad_add_pyramid(base=[100, 0], radius=300, height=900, coords="ucs"))
        args = plugin.calls[0][1]
        assert args["base"] == pytest.approx([1000.0, 100.0, 0.0])
        assert args["rotation"] == pytest.approx(math.pi / 2)
        assert out["rotation"] == 0.0

    def test_the_layer_and_colour_go_with_it(self, plugin):
        call(primitives.autocad_add_pyramid(base=[0, 0], radius=300, height=900, layer="M-EQPT", color="red"))
        args = plugin.calls[0][1]
        assert args["layer"] == "M-EQPT" and args["color"] == 1

    @pytest.mark.parametrize(
        "bad",
        [
            {"sides": 2},
            {"sides": 33},
            {"radius": 0},
            {"height": -5},
            {"top_radius": -1},
            {"base": [1]},
        ],
    )
    def test_sizes_that_make_no_pyramid_are_refused_before_autocad(self, bad):
        sizes = {"base": [0, 0], "radius": 300, "height": 900}
        assert not schema_refuses("autocad_add_pyramid", **sizes)
        assert schema_refuses("autocad_add_pyramid", **{**sizes, **bad})


class TestPolysolid:
    def test_along_a_curve_by_handle(self, plugin):
        out = call(primitives.autocad_add_polysolid(path="2A", width=200, height=1200, side="inside"))
        assert plugin.calls == [("add_polysolid", {"width": 200.0, "height": 1200.0, "side": "inside", "path": "2A"})]
        assert out["handle"] == "3B"

    def test_along_points_closed(self, plugin):
        call(primitives.autocad_add_polysolid(points=[[0, 0], [5000, 0], [5000, 3000]], closed=True, width=250, height=1100, side="left"))
        args = plugin.calls[0][1]
        assert args["points"] == [[0.0, 0.0, 0.0], [5000.0, 0.0, 0.0], [5000.0, 3000.0, 0.0]]
        assert args["closed"] is True and args["side"] == "left" and "path" not in args

    def test_points_on_a_turned_ucs_are_sent_in_the_world(self, plugin):
        plugin.doc.ucs = TURNED
        call(primitives.autocad_add_polysolid(points=[[0, 0], [100, 0]], width=200, height=1000, coords="ucs"))
        first, second = plugin.calls[0][1]["points"]
        assert first == pytest.approx([1000.0, 0.0, 0.0]) and second == pytest.approx([1000.0, 100.0, 0.0])

    def test_points_at_two_levels_are_refused(self, plugin):
        assert "one Z" in error(primitives.autocad_add_polysolid(points=[[0, 0, 0], [100, 0, 50]], width=200, height=1000))
        assert plugin.calls == []

    @pytest.mark.parametrize(
        ("given", "words"),
        [
            ({"path": "2A", "points": [[0, 0], [1, 0]]}, "not both"),
            ({}, "not both and not neither"),
            ({"path": "2A", "closed": True}, "closed is for points"),
            ({"points": [[0, 0], [1]]}, "[x, y]"),
        ],
    )
    def test_the_path_is_one_thing_or_the_other(self, plugin, given, words):
        assert words in error(primitives.autocad_add_polysolid(width=200, height=1000, **given))
        assert plugin.calls == []

    def test_an_unknown_side_or_no_size_is_refused(self):
        assert schema_refuses("autocad_add_polysolid", path="2A", width=200, height=1000, side="middle")
        assert schema_refuses("autocad_add_polysolid", path="2A", width=0, height=1000)
        assert schema_refuses("autocad_add_polysolid", points=[[0, 0]], width=200, height=1000)
        assert not schema_refuses("autocad_add_polysolid", path="2A", width=200, height=1000, side="outside")


class TestFaceEdits:
    def test_offset_by_a_distance(self, plugin):
        plugin.replies["offset_faces"] = {"handle": "2A", "faces": [6], "volume_before": 10.0, "volume_after": 12.0}
        out = call(solid_faces.autocad_edit_solid_faces(handle="2A", action="offset", faces=[6], distance=-10))
        assert plugin.calls == [("offset_faces", {"handle": "2A", "faces": [6], "distance": -10.0})]
        assert out["action"] == "offset" and out["volume_after"] == 12.0

    def test_taper_goes_in_radians_with_its_direction_and_base(self, plugin):
        call(solid_faces.autocad_edit_solid_faces(handle="2A", action="taper", faces="front", angle=5))
        call(solid_faces.autocad_edit_solid_faces(handle="2A", action="taper", faces=[1, 2], angle=-3, direction=[0, 0, -1], base_point=[0, 0, 500]))
        assert plugin.calls[0] == ("taper_faces", {"handle": "2A", "faces": "front", "angle": pytest.approx(math.radians(5))})
        operation, args = plugin.calls[1]
        assert args["direction"] == [0.0, 0.0, -1.0] and args["base"] == [0.0, 0.0, 500.0]
        assert args["angle"] == pytest.approx(math.radians(-3))

    def test_move_by_a_vector(self, plugin):
        call(solid_faces.autocad_edit_solid_faces(handle="2A", action="move", faces="right", by=[200, 0, 0]))
        assert plugin.calls == [("move_faces", {"handle": "2A", "faces": "right", "by": [200.0, 0.0, 0.0]})]

    def test_a_move_on_a_turned_ucs_is_turned_into_the_world(self, plugin):
        plugin.doc.ucs = TURNED
        call(solid_faces.autocad_edit_solid_faces(handle="2A", action="move", faces=[3], by=[200, 0, 0], coords="ucs"))
        # A direction turns with the UCS but does not move with its origin.
        assert plugin.calls[0][1]["by"] == pytest.approx([0.0, 200.0, 0.0])

    def test_delete_takes_only_the_faces(self, plugin):
        call(solid_faces.autocad_edit_solid_faces(handle="2A", action="delete", faces=[7, 8]))
        assert plugin.calls == [("delete_faces", {"handle": "2A", "faces": [7, 8]})]

    @pytest.mark.parametrize(
        ("given", "words"),
        [
            ({"action": "offset"}, "needs distance"),
            ({"action": "offset", "distance": 0}, "cannot be zero"),
            ({"action": "offset", "distance": 5, "by": [1, 0, 0]}, "does not take by"),
            ({"action": "taper"}, "needs angle"),
            ({"action": "taper", "angle": 0}, "changes nothing"),
            ({"action": "taper", "angle": 5, "distance": 3}, "does not take distance"),
            ({"action": "move"}, "needs by"),
            ({"action": "move", "by": [0, 0, 0]}, "changes nothing"),
            ({"action": "delete", "distance": 5}, "takes only the faces"),
        ],
    )
    def test_the_wrong_options_are_refused_before_autocad(self, plugin, given, words):
        assert words in error(solid_faces.autocad_edit_solid_faces(handle="2A", faces="top", **given))
        assert plugin.calls == []

    @pytest.mark.parametrize(
        "given",
        [
            {"action": "taper", "angle": 95},
            {"action": "move", "by": [1, 0]},
            {"action": "offset", "distance": 5, "faces": "sideways"},
            {"action": "twist"},
        ],
    )
    def test_out_of_range_values_never_reach_the_tool(self, given):
        assert schema_refuses("autocad_edit_solid_faces", **{"handle": "2A", "faces": "top", **given})


class TestImprint:
    def test_the_faces_are_counted_after(self, plugin):
        plugin.replies["imprint_solid"] = {"handle": "2A", "objects": ["4C"], "faces_before": 6, "edges_before": 12, "volume": 1.0}
        plugin.replies["solid_topology"] = {"faces": [{}] * 7, "edges": [{}] * 16}
        out = call(solid_faces.autocad_imprint_solid(handle="2A", objects=["4C"]))
        assert plugin.calls[0] == ("imprint_solid", {"handle": "2A", "objects": ["4C"]})
        assert plugin.calls[1] == ("solid_topology", {"handle": "2A"})
        assert out["faces_after"] == 7 and out["edges_after"] == 16 and "note" not in out

    def test_a_miss_is_said(self, plugin):
        plugin.replies["imprint_solid"] = {"handle": "2A", "objects": ["4C"], "faces_before": 6, "edges_before": 12}
        plugin.replies["solid_topology"] = {"faces": [{}] * 6, "edges": [{}] * 12}
        out = call(solid_faces.autocad_imprint_solid(handle="2A", objects=["4C"]))
        assert "Nothing new was imprinted" in out["note"]

    def test_a_count_that_fails_is_not_an_error(self, plugin):
        """The imprint is done: reporting an error would send the chat round to do it twice."""
        plugin.replies["imprint_solid"] = {"handle": "2A", "objects": ["4C"], "faces_before": 6, "edges_before": 12}
        plugin.failing.add("solid_topology")
        out = call(solid_faces.autocad_imprint_solid(handle="2A", objects=["4C"]))
        assert "could not be counted" in out["note"] and "faces_after" not in out

    def test_it_needs_something_to_imprint(self):
        assert schema_refuses("autocad_imprint_solid", handle="2A", objects=[])
        assert not schema_refuses("autocad_imprint_solid", handle="2A", objects=["4C"])


def test_separate_hands_back_the_pieces(plugin):
    plugin.replies["separate_solid"] = {"handle": "2A", "piece_count": 2, "pieces": [{"handle": "2A"}, {"handle": "5D"}]}
    out = call(solid_faces.autocad_separate_solid(handle="2A"))
    assert plugin.calls == [("separate_solid", {"handle": "2A"})]
    assert out["piece_count"] == 2 and out["pieces"][1]["handle"] == "5D"


def test_with_the_bridge_off_they_say_they_need_the_plug_in(monkeypatch):
    async def run(fn):
        return fn()

    for module in (primitives, solid_faces):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: Doc())
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
    assert "plug-in" in error(primitives.autocad_add_pyramid(base=[0, 0], radius=300, height=900)).lower()
    assert "plug-in" in error(solid_faces.autocad_separate_solid(handle="2A")).lower()


def test_levels():
    for tool in (
        "autocad_add_pyramid",
        "autocad_add_polysolid",
        "autocad_edit_solid_faces",
        "autocad_imprint_solid",
        "autocad_separate_solid",
    ):
        assert risk_of(tool) is Risk.CHANGE, tool
