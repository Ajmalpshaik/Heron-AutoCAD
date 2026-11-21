"""3D shapes: a duct run with bends and a pipe spool, as solids along a route (no AutoCAD).

The test that matters is not that the code agrees with itself but that the
pieces make one continuous run: every piece ends exactly where the next one
starts, every bend leaves in the direction the next straight runs, every bend
is tangent to the legs either side of its corner, the straights are the legs
less the bends' tangent lengths, and a rectangular duct is carried round its
bends without twisting. Then the COM side is driven against a fake AutoCAD
that builds and moves boxes the way the real one does, so the check that each
piece landed where the route puts it is itself checked (D-94).
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.acad import shapes3d as s3
from autocad_mcp.core.errors import AutocadError

DUCT = [[0, 0, 3000], [5000, 0, 3000], [5000, 4000, 3000], [5000, 4000, 6000]]
SPOOL = dict(points=[[0, 0, 0], [2000, 0, 0], [2000, 0, 1500]], outside_diameter=114.3, wall=6.02,
             flange_diameter=229, flange_thickness=24, bolt_count=8, pitch_diameter=190.5, hole_diameter=19)


def _close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


def _det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


class TestRoute:
    def test_repeated_points_and_points_on_a_straight_line_are_dropped(self):
        pts = s3.route([[0, 0, 0], [0, 0, 0], [1000, 0, 0], [2000, 0, 0], [2000, 1000, 0]])
        assert pts == [(0.0, 0.0, 0.0), (2000.0, 0.0, 0.0), (2000.0, 1000.0, 0.0)]

    def test_a_2d_point_sits_at_z_0(self):
        assert s3.route([[0, 0], [100, 0]])[1] == (100.0, 0.0, 0.0)

    def test_one_point_is_not_a_run(self):
        with pytest.raises(ValueError, match="two different points"):
            s3.route([[5, 5, 5], [5, 5, 5]])

    def test_a_route_that_doubles_back_is_refused(self):
        with pytest.raises(ValueError, match="doubles back"):
            s3.legs(s3.route([[0, 0, 0], [1000, 0, 0], [0, 0.001, 0]]))

    def test_too_many_points_is_refused(self):
        with pytest.raises(ValueError, match="at most"):
            s3.route([[i, i % 2, 0] for i in range(s3.MOST_POINTS + 1)])

    def test_a_bad_point_is_named(self):
        with pytest.raises(ValueError, match=r"points\[1\]"):
            s3.route([[0, 0, 0], ["x", 0, 0]])


# ---------------------------------------------------------------------------
# A duct run
# ---------------------------------------------------------------------------


class TestDuctRun:
    def setup_method(self):
        self.plan = s3.duct_run(points=DUCT, width=600, height=400)
        self.pieces = self.plan["pieces"]

    def test_a_straight_per_leg_and_a_bend_per_corner(self):
        assert [p["part"] for p in self.pieces] == ["straight", "bend", "straight", "bend", "straight"]
        assert [p["index"] for p in self.pieces] == [0, 1, 2, 3, 4]

    def test_every_piece_ends_where_the_next_begins(self):
        for here, after in zip(self.pieces, self.pieces[1:], strict=False):
            assert _close(s3.piece_end(here), after["start"], 1e-6)
        assert _close(s3.piece_end(self.pieces[-1]), DUCT[-1], 1e-6)

    def test_the_end_worked_out_from_each_frame_is_the_end_it_reports(self):
        for piece in self.pieces:
            assert _close(s3.piece_end(piece), piece["end"], 1e-6)

    def test_each_bend_leaves_in_the_direction_the_next_straight_runs(self):
        for i, piece in enumerate(self.pieces):
            if piece["part"] == "bend":
                assert _close(piece["end_direction"], self.pieces[i + 1]["direction"])
                # And from the frame: the tangent at the end, (sin a, 0, cos a) turned into place.
                a = math.radians(piece["angle"])
                m = piece["matrix"]
                tangent = [m[r][0] * math.sin(a) + m[r][2] * math.cos(a) for r in range(3)]
                assert _close(tangent, piece["end_direction"], 1e-6)

    def test_each_bend_is_tangent_to_both_legs_at_radius_tan_half_angle(self):
        for piece in self.pieces:
            if piece["part"] != "bend":
                continue
            corner, r, a = piece["corner"], piece["radius"], math.radians(piece["angle"])
            tangent = r * math.tan(a / 2)
            assert math.dist(piece["start"], corner) == pytest.approx(tangent)
            assert math.dist(piece["end"], corner) == pytest.approx(tangent)
            # Its centre is the radius from both tangent points.
            assert math.dist(piece["centre"], piece["start"]) == pytest.approx(r)
            assert math.dist(piece["centre"], piece["end"]) == pytest.approx(r)

    def test_the_default_bend_radius_is_the_ducts_size_in_the_plane_it_bends_in(self):
        """R/W = 1: the level bend turns across the 600 width; the bend up turns across the 400 height."""
        bends = [p for p in self.pieces if p["part"] == "bend"]
        assert [b["radius"] for b in bends] == [600.0, 400.0]

    def test_the_straights_are_the_legs_less_the_tangent_lengths(self):
        straights = [p["length"] for p in self.pieces if p["part"] == "straight"]
        assert straights == pytest.approx([5000 - 600, 4000 - 600 - 400, 3000 - 400])

    def test_the_centreline_length_adds_up(self):
        expected = (5000 - 600) + (4000 - 1000) + (3000 - 400) + 600 * math.pi / 2 + 400 * math.pi / 2
        assert self.plan["centreline_length"] == pytest.approx(expected)

    def test_every_matrix_is_a_rigid_move_not_a_mirror(self):
        for piece in self.pieces:
            m = piece["matrix"]
            cols = [[m[r][c] for r in range(3)] for c in range(3)]
            for i in range(3):
                assert math.hypot(*cols[i]) == pytest.approx(1.0)
                for j in range(i + 1, 3):
                    assert sum(a * b for a, b in zip(cols[i], cols[j], strict=True)) == pytest.approx(0.0, abs=1e-9)
            assert _det3(m) == pytest.approx(1.0)
            assert m[3] == [0.0, 0.0, 0.0, 1.0]

    def test_the_width_stays_level_and_the_height_up_on_a_level_run(self):
        first = self.pieces[0]
        m = first["matrix"]
        width = [m[r][0] for r in range(3)]
        height = [m[r][1] for r in range(3)]
        assert abs(width[2]) == pytest.approx(0.0) and height == pytest.approx([0, 0, 1])

    def test_a_rectangular_duct_is_carried_round_its_bends_without_twisting(self):
        """After the level bend the width is still level; after the bend up, the old height runs across."""
        after_level = self.pieces[2]["matrix"]
        assert [after_level[r][1] for r in range(3)] == pytest.approx([0, 0, 1])
        riser = self.pieces[4]["matrix"]
        height = [riser[r][1] for r in range(3)]
        # Rising, the face that was the top now faces back along the last leg (-Y).
        assert height == pytest.approx([0, -1, 0])

    def test_a_bends_rectangle_is_the_duct_turned_into_the_bends_own_frame(self):
        level_bend = self.pieces[1]["profile"]["corners"]
        xs = sorted({abs(c[0]) for c in level_bend})
        ys = sorted({abs(c[1]) for c in level_bend})
        # Across the bend (towards its centre): the 600 width; along its axis: the 400 height.
        assert xs == [300.0] and ys == [200.0]
        up_bend = self.pieces[3]["profile"]["corners"]
        assert sorted({abs(c[0]) for c in up_bend}) == [200.0] and sorted({abs(c[1]) for c in up_bend}) == [300.0]

    def test_the_expected_box_of_a_straight_is_its_outline_moved(self):
        low, high = s3.expected_box(self.pieces[0])
        assert low == pytest.approx([0, -300, 2800]) and high == pytest.approx([4400, 300, 3200])

    def test_the_expected_box_of_a_level_bend_reaches_its_outside_radius(self):
        low, high = s3.expected_box(self.pieces[1])
        # Centre at (4400, 600); outside radius 900 reaches x = 5300 and y = -300.
        assert high[0] == pytest.approx(5300, abs=1) and low[1] == pytest.approx(-300, abs=1)

    def test_a_round_duct_bends_at_one_and_a_half_diameters(self):
        plan = s3.duct_run(points=DUCT, profile="round", diameter=400)
        assert [p["radius"] for p in plan["pieces"] if p["part"] == "bend"] == [600.0, 600.0]
        assert plan["pieces"][0]["solid"] == "cylinder" and plan["pieces"][0]["profile"] == {"kind": "circle", "radius": 200.0}

    def test_a_wall_makes_it_hollow(self):
        plan = s3.duct_run(points=DUCT, width=600, height=400, wall=1.0)
        assert plan["pieces"][0]["hole"] == {"kind": "rectangle", "width": 598.0, "height": 398.0}
        corners = plan["pieces"][1]["hole"]["corners"]
        assert sorted({abs(c[0]) for c in corners}) == [299.0]

    def test_up_turns_the_rectangle(self):
        plan = s3.duct_run(points=[[0, 0, 0], [1000, 0, 0]], width=600, height=400, up=[0, 1, 0])
        m = plan["pieces"][0]["matrix"]
        assert [m[r][1] for r in range(3)] == pytest.approx([0, 1, 0])

    def test_a_riser_on_its_own_faces_north(self):
        plan = s3.duct_run(points=[[0, 0, 0], [0, 0, 3000]], width=600, height=400)
        m = plan["pieces"][0]["matrix"]
        assert [m[r][1] for r in range(3)] == pytest.approx([0, 1, 0])

    def test_a_bend_too_big_for_its_leg_is_refused_with_the_numbers(self):
        with pytest.raises(ValueError, match="leg from point 1 to point 2 is 4000 long") as caught:
            s3.duct_run(points=DUCT, width=600, height=400, bend_radius=3000)
        assert "radius x tan(angle / 2)" in str(caught.value)

    def test_a_bend_radius_inside_the_duct_is_refused(self):
        with pytest.raises(ValueError, match="no inside"):
            s3.duct_run(points=DUCT, width=600, height=400, bend_radius=250)

    def test_sizes_that_do_not_belong_to_the_profile_are_refused(self):
        with pytest.raises(ValueError, match="needs width and height"):
            s3.duct_run(points=DUCT, diameter=400)
        with pytest.raises(ValueError, match="takes diameter"):
            s3.duct_run(points=DUCT, profile="round", diameter=400, width=600)
        with pytest.raises(ValueError, match="closes the duct"):
            s3.duct_run(points=DUCT, width=600, height=400, wall=200)

    def test_a_skewed_3d_corner_still_joins_up(self):
        plan = s3.duct_run(points=[[0, 0, 0], [3000, 0, 0], [5000, 2000, 1500], [5000, 6000, 1500]],
                           width=500, height=300, bend_radius=500)
        pieces = plan["pieces"]
        for here, after in zip(pieces, pieces[1:], strict=False):
            assert _close(s3.piece_end(here), after["start"], 1e-6)
            if here["part"] == "bend":
                assert _close(here["end_direction"], after["direction"])


# ---------------------------------------------------------------------------
# A pipe spool
# ---------------------------------------------------------------------------


class TestPipeSpool:
    def setup_method(self):
        self.plan = s3.pipe_spool(**SPOOL)
        self.pieces = self.plan["pieces"]

    def test_flange_pipe_elbow_pipe_flange(self):
        assert [p["part"] for p in self.pieces] == ["flange", "pipe", "elbow", "pipe", "flange"]

    def test_the_flange_faces_sit_on_the_end_points(self):
        start, end = self.pieces[0], self.pieces[-1]
        assert start["start"] == [0.0, 0.0, 0.0]
        assert end["end_point"] == pytest.approx(SPOOL["points"][-1])

    def test_every_piece_ends_where_the_next_begins(self):
        for here, after in zip(self.pieces, self.pieces[1:], strict=False):
            assert _close(s3.piece_end(here), after["start"], 1e-6)
        assert _close(s3.piece_end(self.pieces[-1]), SPOOL["points"][-1], 1e-6)

    def test_the_cut_lengths_are_the_legs_less_the_elbow_and_the_flange(self):
        r = 1.5 * 114.3
        assert self.plan["elbow_radius"] == pytest.approx(r)
        assert [c["cut_length"] for c in self.plan["pipe_cut_lengths"]] == pytest.approx([2000 - r - 24, 1500 - r - 24])
        assert self.plan["pipe_total"] == pytest.approx(3500 - 2 * r - 48)
        assert self.plan["elbows"] == 1

    def test_the_wall_bores_the_pipe_and_the_flange_alike(self):
        bore = (114.3 - 2 * 6.02) / 2
        assert self.pieces[1]["hole"]["radius"] == pytest.approx(bore)
        assert self.pieces[0]["hole"]["radius"] == pytest.approx(bore)

    def test_the_bolt_holes_straddle_the_centrelines_on_the_pitch_circle(self):
        holes = self.pieces[0]["bolt_holes"]
        assert len(holes) == 8
        for hole in holes:
            assert math.hypot(hole["x"], hole["y"]) == pytest.approx(190.5 / 2)
            assert hole["radius"] == pytest.approx(9.5)
        angles = sorted(math.degrees(math.atan2(h["y"], h["x"])) % 360 for h in holes)
        assert angles[0] == pytest.approx(22.5)

    def test_plain_ends_take_no_flange_sizes(self):
        plan = s3.pipe_spool(points=SPOOL["points"], outside_diameter=114.3, flanges="none")
        assert [p["part"] for p in plan["pieces"]] == ["pipe", "elbow", "pipe"]
        with pytest.raises(ValueError, match="takes no flange sizes"):
            s3.pipe_spool(points=SPOOL["points"], outside_diameter=114.3, flanges="none", flange_diameter=229)

    def test_one_flanged_end(self):
        plan = s3.pipe_spool(points=SPOOL["points"], outside_diameter=114.3, flanges="end",
                             flange_diameter=229, flange_thickness=24)
        assert [p["part"] for p in plan["pieces"]] == ["pipe", "elbow", "pipe", "flange"]
        assert plan["pieces"][0]["start"] == [0.0, 0.0, 0.0]

    def test_flanges_need_their_sizes(self):
        with pytest.raises(ValueError, match="flange_diameter and flange_thickness"):
            s3.pipe_spool(points=SPOOL["points"], outside_diameter=114.3)

    def test_bolt_holes_need_all_three_and_must_fit(self):
        with pytest.raises(ValueError, match="all three"):
            s3.pipe_spool(**{**SPOOL, "hole_diameter": None})
        with pytest.raises(ValueError, match="between the pipe"):
            s3.pipe_spool(**{**SPOOL, "pitch_diameter": 120})
        with pytest.raises(ValueError, match="whole number"):
            s3.pipe_spool(**{**SPOOL, "bolt_count": 4.5})

    def test_a_flange_that_does_not_fit_its_leg_is_refused(self):
        with pytest.raises(ValueError, match="the flange 24"):
            s3.pipe_spool(**{**SPOOL, "points": [[0, 0, 0], [150, 0, 0], [150, 0, 1500]]})

    def test_a_straight_spool_with_two_flanges(self):
        plan = s3.pipe_spool(points=[[0, 0, 0], [0, 0, 1000]], outside_diameter=60.3,
                             flange_diameter=165, flange_thickness=20)
        assert [p["part"] for p in plan["pieces"]] == ["flange", "pipe", "flange"]
        assert plan["pipe_cut_lengths"][0]["cut_length"] == pytest.approx(960)
        with pytest.raises(ValueError, match="need 40"):
            s3.pipe_spool(points=[[0, 0, 0], [0, 0, 30]], outside_diameter=60.3,
                          flange_diameter=165, flange_thickness=20)


class TestBuild:
    def test_build_3d_names_what_is_missing_and_unknown(self):
        with pytest.raises(ValueError, match="needs outside_diameter"):
            s3.build_3d("pipe_spool", {"points": DUCT})
        with pytest.raises(ValueError, match="does not take size"):
            s3.build_3d("duct_run", {"points": DUCT, "size": 3})

    def test_the_2d_library_names_the_3d_shapes_too(self):
        from autocad_mcp.acad import shapes

        with pytest.raises(ValueError, match="duct_run, pipe_spool"):
            shapes.build("ductrun", {})


# ---------------------------------------------------------------------------
# The COM side, against a fake AutoCAD
# ---------------------------------------------------------------------------


def _apply(m, p):
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))


class FakeSolid:
    """A solid as a cloud of points on its surface: moved, cut and boxed like AutoCAD's."""

    count = 0

    def __init__(self, kind, points):
        FakeSolid.count += 1
        self.Handle = f"S{FakeSolid.count}"
        self.ObjectName = "AcDb3dSolid"
        self.kind, self.points = kind, points
        self.cuts, self.moves, self.deleted, self.unions = [], [], False, []
        self.Layer = "0"

    def Boolean(self, code, other):
        (self.cuts if code == 2 else self.unions).append(other)
        other.deleted = True

    def TransformBy(self, variant):
        rows = variant.value
        assert len(rows) == 4 and all(len(row) == 4 for row in rows)
        self.moves.append(rows)
        if not FakeSpace.ignore_moves:
            self.points = [_apply(rows, p) for p in self.points]

    def GetBoundingBox(self):
        return (tuple(min(p[i] for p in self.points) for i in range(3)),
                tuple(max(p[i] for p in self.points) for i in range(3)))

    def Delete(self):
        self.deleted = True


class FakeCurve:
    def __init__(self, outline):
        self.outline, self.Closed, self.deleted = outline, False, False
        self.Handle = "C1"

    def Delete(self):
        self.deleted = True


class FakeSpace:
    left_handed = False
    ignore_moves = False

    def __init__(self):
        self.made, self.revolves = [], []

    def _solid(self, kind, points):
        solid = FakeSolid(kind, points)
        self.made.append(solid)
        return solid

    def AddBox(self, centre, length, width, height):
        cx, cy, cz = centre.value
        return self._solid("box", [(cx + sx * length / 2, cy + sy * width / 2, cz + sz * height / 2)
                                   for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])

    def AddCylinder(self, centre, radius, height):
        cx, cy, cz = centre.value
        return self._solid("cylinder", [(cx + radius * math.cos(k * math.pi / 36), cy + radius * math.sin(k * math.pi / 36), cz + dz)
                                        for k in range(72) for dz in (-height / 2, height / 2)])

    def AddCircle(self, centre, radius):
        return FakeCurve([(radius * math.cos(k * math.pi / 36), radius * math.sin(k * math.pi / 36)) for k in range(72)])

    def AddLightWeightPolyline(self, flat):
        values = list(flat.value)
        return FakeCurve(list(zip(values[::2], values[1::2], strict=True)))

    def AddRegion(self, curves):
        return (FakeCurve(curves.value[0].outline),)

    def AddRevolvedSolid(self, region, axis_point, axis_dir, angle):
        r = axis_point.value[0]
        sign = axis_dir.value[1] * (-1 if FakeSpace.left_handed else 1)
        self.revolves.append(axis_dir.value)
        points = []
        for k in range(25):
            a = sign * angle * k / 24
            for x, y in region.outline:
                dx = x - r
                points.append((r + dx * math.cos(a), y, -dx * math.sin(a)))
        return self._solid("revolve", points)

    def Add3DPoly(self, flat):
        curve = FakeCurve([])
        curve.Handle = "P1"
        curve.Layer = "0"
        return curve


class FakeDoc:
    def __init__(self):
        self.ModelSpace = FakeSpace()

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def acad(monkeypatch):
    from autocad_mcp.tools import _solid_pieces, shapes

    FakeSpace.left_handed = False
    FakeSpace.ignore_moves = False
    doc = FakeDoc()

    async def run(fn):
        return fn()

    monkeypatch.setattr(shapes, "run", run)
    monkeypatch.setattr(_solid_pieces, "get_doc", lambda: doc)
    monkeypatch.setattr(_solid_pieces, "require_idle", lambda d: None)
    monkeypatch.setattr(_solid_pieces, "apply_properties", lambda *a, **k: {})
    return doc


def _make(**kwargs):
    from autocad_mcp.tools import shapes

    answer = asyncio.run(shapes.autocad_make_shape(**kwargs))
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


class TestDrawing:
    def test_a_duct_run_lands_where_the_route_puts_it(self, acad):
        result = _make(shape="duct_run", settings={"points": DUCT, "width": 600, "height": 400})
        assert result["created"] == 5 and result["verified"] is True and "warning" not in result
        assert [p["part"] for p in result["pieces"]] == ["straight", "bend", "straight", "bend", "straight"]
        space = acad.ModelSpace
        kept = [s for s in space.made if not s.deleted]
        assert len(kept) == 5 and all(len(s.moves) == 1 for s in kept)

    def test_a_bend_that_swept_the_wrong_way_is_made_again_the_other_way(self, acad):
        FakeSpace.left_handed = True
        result = _make(shape="duct_run", settings={"points": DUCT, "width": 600, "height": 400})
        assert result["verified"] is True
        revolves = acad.ModelSpace.revolves
        assert revolves.count((0.0, 1.0, 0.0)) == 2 and revolves.count((0.0, -1.0, 0.0)) == 2

    def test_a_piece_that_did_not_move_is_said_not_to_have_landed(self, acad):
        FakeSpace.ignore_moves = True
        result = _make(shape="duct_run", settings={"points": DUCT, "width": 600, "height": 400})
        assert result["verified"] is False and "did not land" in result["warning"]

    def test_a_spool_is_bored_and_drilled_and_lists_its_cut_lengths(self, acad):
        result = _make(shape="pipe_spool", settings=SPOOL)
        assert result["created"] == 5 and result["verified"] is True
        assert len(result["pipe_cut_lengths"]) == 2
        flange = next(s for s in acad.ModelSpace.made if s.kind == "cylinder" and len(s.cuts) == 9)
        assert flange.cuts[0].kind == "cylinder"  # the bore, then eight bolt holes

    def test_join_makes_one_solid(self, acad):
        result = _make(shape="pipe_spool", settings={**SPOOL, "join": True})
        assert result["created"] == 1 and result["handles"] == [result["joined_into"]]

    def test_a_centreline_goes_on_its_own_layer(self, acad):
        result = _make(shape="duct_run", settings={"points": DUCT, "width": 600, "height": 400},
                       centreline_layer="M-DUCT-CNTR")
        assert result["centreline"] == "P1"

    def test_a_refusal_half_way_takes_every_piece_out_again(self, acad, monkeypatch):
        calls = {"n": 0}
        original = FakeSpace.AddRevolvedSolid

        def refuse(self, *args):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("Modeling Operation Error")
            return original(self, *args)

        monkeypatch.setattr(FakeSpace, "AddRevolvedSolid", refuse)
        from autocad_mcp.tools import shapes

        answer = asyncio.run(shapes.autocad_make_shape(shape="duct_run", settings={"points": DUCT, "width": 600, "height": 400}))
        assert "nothing was left in the drawing" in answer
        assert all(s.deleted for s in acad.ModelSpace.made)

    def test_a_dry_run_makes_nothing_and_gives_the_pieces(self, acad):
        result = _make(shape="duct_run", settings={"points": DUCT, "width": 600, "height": 400}, dry_run=True)
        assert result["dry_run"] is True and result["piece_count"] == 5 and "style" not in result
        assert acad.ModelSpace.made == []

    def test_a_bad_setting_is_answered_not_raised(self, acad):
        from autocad_mcp.tools import shapes

        answer = asyncio.run(shapes.autocad_make_shape(shape="pipe_spool", settings={"points": DUCT}))
        assert "needs outside_diameter" in answer

    def test_the_matrix_goes_over_as_four_rows_of_four(self):
        from autocad_mcp.tools._solid_pieces import matrix_variant

        variant = matrix_variant(s3.duct_run(points=DUCT, width=600, height=400)["pieces"][0]["matrix"])
        assert len(variant.value) == 4 and all(len(row) == 4 for row in variant.value)

    def test_coords_ucs_turns_the_route_into_world_points(self, acad, monkeypatch):
        from autocad_mcp.acad.coords import Ucs
        from autocad_mcp.tools import shapes

        monkeypatch.setattr(shapes, "get_doc", lambda: acad)
        monkeypatch.setattr(shapes, "current_ucs", lambda doc: Ucs((1000.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))
        result = _make(shape="duct_run", settings={"points": [[0, 0, 0], [2000, 0, 0]], "width": 600, "height": 400},
                       dry_run=True, coords="ucs")
        assert result["points"] == [[1000.0, 0.0, 0.0], [1000.0, 2000.0, 0.0]]


def test_errors_are_autocad_errors():
    from autocad_mcp.tools import _solid_pieces

    assert issubclass(AutocadError, Exception) and _solid_pieces.BOX_TOLERANCE < 0.1
