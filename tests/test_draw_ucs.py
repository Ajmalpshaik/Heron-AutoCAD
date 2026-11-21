"""coords='ucs' on the single-entity draw and modify tools (#50, D-96), without AutoCAD.

Each tool runs against a fake drawing that records exactly what COM would be
handed. The UCS is read from UCSORG / UCSXDIR / UCSYDIR, as the real drawing
gives it, so these check the same transform autocad_batch_draw uses (D-27):
every point, every angle and every vertex list, on a moved, a turned and a
flipped UCS.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.acad.coords import Ucs
from autocad_mcp.tools import draw, modify
from autocad_mcp.tools._shared import world_angle, world_turn
from autocad_mcp.tools.draw import ellipse_axis, plan_vertices
from autocad_mcp.tools.modify import grid_offsets

# A plan UCS turned 90 degrees and moved to (1000, 500): UCS [x, y] is world [1000 - y, 500 + x].
TURNED = {"UCSORG": (1000.0, 500.0, 0.0), "UCSXDIR": (0.0, 1.0, 0.0), "UCSYDIR": (-1.0, 0.0, 0.0)}
# The same plan turned over: X along world X, Y along world -Y, Z pointing down.
FLIPPED = {"UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, -1.0, 0.0)}
# Moved up 3000: a floor level.
RAISED = {"UCSORG": (0.0, 0.0, 3000.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0)}
WORLD = {"UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0)}


def values(variant):
    return tuple(round(v, 9) for v in variant.value)


class Entity:
    def __init__(self, handle="2A0"):
        self.Handle = handle
        self.Name = "TAG"
        self.HasAttributes = False
        self.calls: list[tuple] = []
        self.written: dict = {}

    def __setattr__(self, name, value):
        if name[0].isupper() and name not in ("Handle", "Name", "HasAttributes"):
            self.__dict__.setdefault("written", {})[name] = value
        object.__setattr__(self, name, value)

    # the modify verbs
    def Move(self, a, b):
        self.calls.append(("Move", values(a), values(b)))

    def Rotate(self, base, angle):
        self.calls.append(("Rotate", values(base), round(angle, 9)))

    def ScaleEntity(self, base, factor):
        self.calls.append(("ScaleEntity", values(base), factor))

    def Mirror(self, a, b):
        self.calls.append(("Mirror", values(a), values(b)))
        return Entity("2B0")

    def Copy(self):
        made = Entity(f"C{len(self.calls)}")
        self.calls.append(("Copy", made))
        return made

    def ArrayRectangular(self, *args):
        self.calls.append(("ArrayRectangular", args))
        return [Entity("A1")]

    def ArrayPolar(self, count, angle, centre):
        self.calls.append(("ArrayPolar", count, round(angle, 9), values(centre)))
        return [Entity("P1")]


class Space:
    def __init__(self):
        self.calls: list[tuple] = []
        self.made: list[Entity] = []

    def _made(self, *call):
        self.calls.append(call)
        self.made.append(Entity())
        return self.made[-1]

    def AddLine(self, a, b):
        return self._made("AddLine", values(a), values(b))

    def AddLightWeightPolyline(self, flat):
        return self._made("AddLightWeightPolyline", values(flat))

    def AddCircle(self, c, r):
        return self._made("AddCircle", values(c), r)

    def AddArc(self, c, r, a, b):
        return self._made("AddArc", values(c), r, round(a, 9), round(b, 9))

    def AddEllipse(self, c, axis, ratio):
        return self._made("AddEllipse", values(c), values(axis), ratio)

    def AddPoint(self, p):
        return self._made("AddPoint", values(p))

    def AddText(self, text, p, h):
        return self._made("AddText", text, values(p), h)

    def AddMText(self, p, w, text):
        return self._made("AddMText", values(p), w, text)

    def AddDimAligned(self, a, b, t):
        return self._made("AddDimAligned", values(a), values(b), values(t))

    def AddDimRotated(self, a, b, t, angle):
        return self._made("AddDimRotated", values(a), values(b), values(t), round(angle, 9))

    def AddDimRadial(self, a, b, leader):
        return self._made("AddDimRadial", values(a), values(b))

    def AddDimDiametric(self, a, b, leader):
        return self._made("AddDimDiametric", values(a), values(b))

    def AddDimAngular(self, a, b, c, t):
        return self._made("AddDimAngular", values(a), values(b), values(c), values(t))

    def InsertBlock(self, p, name, sx, sy, sz, angle):
        return self._made("InsertBlock", values(p), name, round(angle, 9))


class Blocks:
    def Item(self, name):
        return name


class Doc:
    def __init__(self, ucs):
        self.variables = dict(ucs)
        self.variables["DIMSCALE"] = 1.0
        self.space = Space()
        self.Blocks = Blocks()
        self.entities: dict[str, Entity] = {}

    def GetVariable(self, name):
        return self.variables[name]

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def cad(monkeypatch):
    state = {"doc": Doc(WORLD)}

    async def run(fn):
        return fn()

    for module in (draw, modify):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: state["doc"])
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(draw, "get_space", lambda doc, space: doc.space)
    monkeypatch.setattr(draw, "apply_properties", lambda *a, **k: {})
    monkeypatch.setattr(draw, "describe", lambda *a, **k: {})
    monkeypatch.setattr(draw, "created_payload", lambda entity, notes, **extra: {"handle": entity.Handle, **extra})

    def resolve(doc, handle):
        return doc.entities.setdefault(handle, Entity(handle))

    monkeypatch.setattr(modify, "resolve_handle", resolve)

    def using(ucs):
        state["doc"] = Doc(ucs)
        return state["doc"]

    return using


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------


class TestAnglesOnThePlane:
    def test_a_turned_ucs_adds_its_rotation(self):
        ucs = Ucs.from_rotation((0, 0), 30)
        assert ucs.angle_to_world(0) == 30.0
        assert ucs.angle_to_world(350) == pytest.approx(20.0)

    def test_a_flipped_ucs_runs_the_other_way(self):
        flipped = Ucs.build((0, 0, 0), (1, 0, 0), (0, -1, 0))
        assert flipped.flipped and not flipped.tilted
        # 90 degrees in it is UCS +Y, which is world -Y: 270.
        assert flipped.angle_to_world(90) == pytest.approx(270.0)
        assert flipped.turn_to_world(30) == -30.0
        assert flipped.bulge_to_world(0.5) == -0.5

    def test_every_angle_lands_on_the_direction_the_transform_gives(self):
        for ucs in (Ucs.from_rotation((5, 5), 37), Ucs.build((0, 0, 0), (0, 1, 0), (1, 0, 0))):
            for degrees in (0, 45, 123, 270):
                a = math.radians(degrees)
                x, y, _ = ucs.direction_to_world((math.cos(a), math.sin(a), 0))
                assert ucs.angle_to_world(degrees) == pytest.approx(math.degrees(math.atan2(y, x)) % 360)

    def test_an_arc_seen_in_a_mirror_swaps_its_ends(self):
        flipped = Ucs.build((0, 0, 0), (1, 0, 0), (0, -1, 0))
        # A quarter arc from UCS +X round to UCS +Y is world 270 round to 0, anticlockwise.
        assert flipped.arc_to_world(0, 90) == pytest.approx((270.0, 0.0))
        assert Ucs.from_rotation((0, 0), 90).arc_to_world(0, 90) == (90.0, 180.0)

    def test_the_world_path_leaves_angles_and_turns_alone(self):
        assert world_angle(45.0, None) == 45.0 and world_turn(45.0, None) == 45.0

    def test_a_polyline_lands_at_the_height_of_a_raised_ucs(self):
        flat, elevation = plan_vertices([[0, 0], [10, 0]], Ucs.build((0, 0, 3000), (1, 0, 0), (0, 1, 0)))
        assert flat == [0.0, 0.0, 10.0, 0.0] and elevation == 3000.0
        assert plan_vertices([[0, 0, 50], [10, 0, 50]], None) == ([0.0, 0.0, 10.0, 0.0], 0.0)

    def test_an_ellipse_axis_turns_with_the_ucs(self):
        x, y, z = ellipse_axis(300, 0, Ucs.from_rotation((0, 0), 90))
        assert (x, y, z) == pytest.approx((0.0, 300.0, 0.0))

    def test_a_grid_follows_the_ucs_axes(self):
        offsets = grid_offsets(2, 3, 100, 200, Ucs.from_rotation((7, 7), 90))
        # Columns along UCS X (world +Y), rows along UCS Y (world -X); the original is not in it.
        assert len(offsets) == 5
        assert offsets[0] == pytest.approx((0.0, 200.0, 0.0))
        assert offsets[2] == pytest.approx((-100.0, 0.0, 0.0))
        assert offsets[-1] == pytest.approx((-100.0, 400.0, 0.0))


# ---------------------------------------------------------------------------
# The draw tools
# ---------------------------------------------------------------------------


class TestDrawTools:
    def test_world_is_still_the_default_and_unchanged(self, cad):
        doc = cad(TURNED)
        out = call(draw.autocad_draw_line(start=[0, 0], end=[100, 0]))
        assert doc.space.calls == [("AddLine", (0.0, 0.0, 0.0), (100.0, 0.0, 0.0))]
        assert "converted_from_ucs" not in out

    def test_a_line_is_read_in_the_ucs(self, cad):
        doc = cad(TURNED)
        out = call(draw.autocad_draw_line(start=[0, 0], end=[100, 0], coords="ucs"))
        assert doc.space.calls == [("AddLine", (1000.0, 500.0, 0.0), (1000.0, 600.0, 0.0))]
        assert out["converted_from_ucs"]["rotation_degrees"] == 90.0

    def test_ucs_on_a_world_drawing_converts_nothing_and_says_nothing(self, cad):
        doc = cad(WORLD)
        out = call(draw.autocad_draw_point(position=[5, 6], coords="ucs"))
        assert doc.space.calls == [("AddPoint", (5.0, 6.0, 0.0))]
        assert "converted_from_ucs" not in out

    def test_a_polyline_converts_every_vertex(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_draw_polyline(points=[[0, 0], [100, 0], [100, 50]], coords="ucs"))
        assert doc.space.calls == [("AddLightWeightPolyline", (1000.0, 500.0, 1000.0, 600.0, 950.0, 600.0))]

    def test_a_polyline_in_a_raised_ucs_gets_its_elevation(self, cad):
        doc = cad(RAISED)
        call(draw.autocad_draw_polyline(points=[[0, 0], [100, 0]], coords="ucs"))
        assert doc.space.calls[0][1] == (0.0, 0.0, 100.0, 0.0)
        assert doc.space.made[0].written["Elevation"] == 3000.0

    def test_a_polyline_in_world_coordinates_gets_no_elevation(self, cad):
        doc = cad(RAISED)
        call(draw.autocad_draw_polyline(points=[[0, 0, 50], [100, 0, 50]]))
        assert "Elevation" not in doc.space.made[0].written

    def test_a_rectangle_comes_out_square_to_the_turned_ucs(self, cad):
        doc = cad(TURNED)
        out = call(draw.autocad_draw_rectangle(corner1=[0, 0], corner2=[100, 50], coords="ucs"))
        (_, flat), = doc.space.calls
        assert flat == (1000.0, 500.0, 1000.0, 600.0, 950.0, 600.0, 950.0, 500.0)
        assert out["width"] == 100 and out["height"] == 50

    def test_a_circle_moves_its_centre(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_draw_circle(center=[10, 0], radius=5, coords="ucs"))
        assert doc.space.calls == [("AddCircle", (1000.0, 510.0, 0.0), 5.0)]

    def test_an_arc_turns_its_angles(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_draw_arc(center=[0, 0], radius=5, start_angle=0, end_angle=90, coords="ucs"))
        assert doc.space.calls == [("AddArc", (1000.0, 500.0, 0.0), 5.0, round(math.pi / 2, 9), round(math.pi, 9))]

    def test_an_arc_in_a_flipped_ucs_swaps_its_ends(self, cad):
        doc = cad(FLIPPED)
        call(draw.autocad_draw_arc(center=[0, 0], radius=5, start_angle=0, end_angle=90, coords="ucs"))
        (_, _, _, start, end), = doc.space.calls
        assert (start, end) == (round(math.radians(270), 9), 0.0)

    def test_an_ellipse_turns_its_major_axis(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_draw_ellipse(center=[0, 0], major_radius=300, minor_radius=200, coords="ucs"))
        (_, centre, axis, ratio), = doc.space.calls
        assert centre == (1000.0, 500.0, 0.0)
        assert axis == pytest.approx((0.0, 300.0, 0.0)) and ratio == pytest.approx(2 / 3)

    def test_text_turns_with_the_ucs(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_add_text(text="A", position=[0, 0], coords="ucs"))
        (made_call,) = doc.space.calls
        assert made_call[2] == (1000.0, 500.0, 0.0)

    def test_text_rotation_is_added_to_the_ucs_rotation(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_add_text(text="A", position=[0, 0], rotation=10, coords="ucs"))
        assert doc.space.made[0].written["Rotation"] == pytest.approx(math.radians(100))

    def test_text_at_rotation_0_in_a_turned_ucs_still_turns(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_add_text(text="A", position=[0, 0], coords="ucs"))
        assert doc.space.made[0].written["Rotation"] == pytest.approx(math.pi / 2)

    def test_mtext_moves_its_corner(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_add_mtext(text="NOTE", position=[0, 100], width=500, coords="ucs"))
        assert doc.space.calls == [("AddMText", (900.0, 500.0, 0.0), 500.0, "NOTE")]

    @pytest.mark.parametrize(
        "tool, kwargs",
        [
            ("autocad_add_text", {"text": "A", "position": [0, 0]}),
            ("autocad_add_mtext", {"text": "A", "position": [0, 0], "width": 10}),
            ("autocad_insert_block", {"block_name": "TAG", "position": [0, 0]}),
            ("autocad_add_dimension", {"point1": [0, 0], "point2": [10, 0]}),
        ],
    )
    def test_on_a_flipped_ucs_text_blocks_and_dimensions_are_refused(self, cad, tool, kwargs):
        doc = cad(FLIPPED)
        answer = error(getattr(draw, tool)(coords="ucs", **kwargs))
        assert "flipped" in answer and "mirrored" in answer and doc.space.calls == []

    def test_a_horizontal_dimension_measures_along_the_ucs_x(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_add_dimension(dimension_type="horizontal", point1=[0, 0], point2=[100, 0],
                                        text_position=[50, -20], coords="ucs"))
        (name, p1, p2, text, angle), = doc.space.calls
        assert name == "AddDimRotated" and angle == round(math.pi / 2, 9)
        assert (p1, p2, text) == ((1000.0, 500.0, 0.0), (1000.0, 600.0, 0.0), (1020.0, 550.0, 0.0))

    def test_a_dimension_s_default_text_point_is_the_midpoint_converted(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_add_dimension(point1=[0, 0], point2=[100, 0], coords="ucs"))
        (name, _, _, text), = doc.space.calls
        assert name == "AddDimAligned" and text == (1000.0, 550.0, 0.0)

    def test_an_angular_dimension_converts_all_four_points(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_add_dimension(dimension_type="angular", point1=[0, 0], point2=[10, 0],
                                        point3=[0, 10], text_position=[5, 5], coords="ucs"))
        (_, *points), = doc.space.calls
        assert points == [(1000.0, 500.0, 0.0), (1000.0, 510.0, 0.0), (990.0, 500.0, 0.0), (995.0, 505.0, 0.0)]

    def test_a_block_turns_with_the_ucs(self, cad):
        doc = cad(TURNED)
        call(draw.autocad_insert_block(block_name="TAG", position=[0, 0], rotation=15, coords="ucs"))
        assert doc.space.calls == [("InsertBlock", (1000.0, 500.0, 0.0), "TAG", round(math.radians(105), 9))]

    def test_a_tilted_ucs_is_refused_for_every_tool(self, cad):
        doc = cad({"UCSORG": (0, 0, 0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 0.0, 1.0)})
        answer = error(draw.autocad_draw_circle(center=[0, 0], radius=1, coords="ucs"))
        assert "tilted" in answer and doc.space.calls == []


# ---------------------------------------------------------------------------
# The modify tools
# ---------------------------------------------------------------------------


class TestModifyTools:
    def test_a_displacement_turns_but_does_not_move(self, cad):
        doc = cad(TURNED)
        out = call(modify.autocad_move_entities(handles=["1A"], displacement=[100, 0], coords="ucs"))
        assert doc.entities["1A"].calls == [("Move", (0.0, 0.0, 0.0), (0.0, 100.0, 0.0))]
        assert out["displacement"] == [0.0, 100.0, 0.0] and "converted_from_ucs" in out

    def test_from_and_to_points_give_the_same_world_move(self, cad):
        doc = cad(TURNED)
        call(modify.autocad_move_entities(handles=["1A"], from_point=[10, 10], to_point=[10, 60], coords="ucs"))
        assert doc.entities["1A"].calls == [("Move", (0.0, 0.0, 0.0), (-50.0, 0.0, 0.0))]

    def test_a_row_of_copies_runs_along_the_ucs(self, cad):
        doc = cad(TURNED)
        out = call(modify.autocad_copy_entities(handles=["1A"], displacement=[100, 0], count=2, coords="ucs"))
        copies = [c[1] for c in doc.entities["1A"].calls if c[0] == "Copy"]
        assert [c.calls for c in copies] == [[("Move", (0.0, 0.0, 0.0), (0.0, 100.0, 0.0))],
                                             [("Move", (0.0, 0.0, 0.0), (0.0, 200.0, 0.0))]]
        assert out["copied"] == 2

    def test_rotate_moves_its_pivot_and_keeps_its_turn(self, cad):
        doc = cad(TURNED)
        call(modify.autocad_rotate_entities(handles=["1A"], base_point=[0, 0], angle=30, coords="ucs"))
        assert doc.entities["1A"].calls == [("Rotate", (1000.0, 500.0, 0.0), round(math.radians(30), 9))]

    def test_rotate_on_a_flipped_ucs_turns_the_other_way(self, cad):
        doc = cad(FLIPPED)
        call(modify.autocad_rotate_entities(handles=["1A"], base_point=[0, 10], angle=30, coords="ucs"))
        assert doc.entities["1A"].calls == [("Rotate", (0.0, -10.0, 0.0), round(math.radians(-30), 9))]

    def test_scale_moves_its_base_point(self, cad):
        doc = cad(TURNED)
        call(modify.autocad_scale_entities(handles=["1A"], base_point=[0, 0], factor=2, coords="ucs"))
        assert doc.entities["1A"].calls == [("ScaleEntity", (1000.0, 500.0, 0.0), 2.0)]

    def test_mirror_moves_its_line(self, cad):
        doc = cad(TURNED)
        call(modify.autocad_mirror_entities(handles=["1A"], axis_point1=[0, 0], axis_point2=[100, 0], coords="ucs"))
        assert doc.entities["1A"].calls == [("Mirror", (1000.0, 500.0, 0.0), (1000.0, 600.0, 0.0))]

    def test_a_rectangular_array_on_a_turned_ucs_is_made_copy_by_copy(self, cad):
        doc = cad(TURNED)
        out = call(modify.autocad_array_entities(handles=["1A"], rows=1, columns=3, column_spacing=100, coords="ucs"))
        calls = doc.entities["1A"].calls
        assert not any(c[0] == "ArrayRectangular" for c in calls)
        moves = [c[1].calls[0][2] for c in calls if c[0] == "Copy"]
        assert moves == [(0.0, 100.0, 0.0), (0.0, 200.0, 0.0)]
        assert out["arrayed"] == 2

    def test_a_rectangular_array_on_a_moved_ucs_still_uses_arrayrectangular(self, cad):
        doc = cad({"UCSORG": (500.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0)})
        call(modify.autocad_array_entities(handles=["1A"], rows=2, columns=1, row_spacing=50, coords="ucs"))
        assert doc.entities["1A"].calls[0][0] == "ArrayRectangular"

    def test_a_polar_array_moves_its_centre_and_runs_the_flipped_way(self, cad):
        doc = cad(FLIPPED)
        call(modify.autocad_array_entities(handles=["1A"], pattern="polar", count=4, center=[0, 10],
                                           fill_angle=90, coords="ucs"))
        assert doc.entities["1A"].calls == [("ArrayPolar", 4, round(math.radians(-90), 9), (0.0, -10.0, 0.0))]
