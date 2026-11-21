"""The geometry of the 2D edits (issues #103 and #49, D-78), checked without AutoCAD.

Each answer is checked against the number a draftsman would measure on the
drawing: where the cut lands, the tangent point of a fillet, the length a
chamfer takes off each line, the order a run joins in, where a stretched
corner ends up.
"""

from __future__ import annotations

import math

import pytest

from autocad_mcp.acad import edit2d as e

B90 = math.tan(math.radians(90) / 4)  # a quarter circle as a bulge


def pts(path):
    return [tuple(round(c, 6) for c in v) for v in path["vertices"]]


def line(a, b):
    return e.line_path(a, b)


def rect(w, h, x=0.0, y=0.0):
    return e.make_path([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], closed=True)


# ---- where things meet ---------------------------------------------------------------


class TestIntersections:
    def test_a_line_crossing_a_line(self):
        assert e.intersections(line((0, 0), (100, 0)), line((40, -10), (40, 10))) == pytest.approx([40.0])

    def test_lines_that_would_meet_only_if_drawn_longer_do_not(self):
        assert e.intersections(line((0, 0), (100, 0)), line((40, 5), (40, 10))) == []

    def test_a_line_through_a_circle_meets_it_twice(self):
        circle = e.make_path([(10, 0), (-10, 0)], [1.0, 1.0], closed=True)
        hits = e.intersections(line((-20, 0), (20, 0)), circle)
        assert hits == pytest.approx([10.0, 30.0])

    def test_a_line_just_touching_a_circle_meets_it_once(self):
        circle = e.make_path([(10, 0), (-10, 0)], [1.0, 1.0], closed=True)
        assert e.intersections(line((-20, 10), (20, 10)), circle) == pytest.approx([20.0])

    def test_a_line_meets_an_arc_only_on_the_drawn_part(self):
        upper = e.make_path([(10, 0), (-10, 0)], [1.0])  # top half, anticlockwise
        assert e.intersections(line((0, -20), (0, 20)), upper) == pytest.approx([30.0])

    def test_two_circles(self):
        a = e.make_path([(10, 0), (-10, 0)], [1.0, 1.0], closed=True)
        b = e.make_path([(20, 0), (0, 0)], [1.0, 1.0], closed=True)
        hits = e.intersections(a, b)
        assert len(hits) == 2


# ---- trim ------------------------------------------------------------------------------


class TestTrim:
    def test_the_picked_end_is_cut_back_to_the_edge(self):
        path = line((0, 0), (100, 0))
        cuts = e.intersections(path, line((40, -10), (40, 10)))
        pieces, removed = e.trim(path, cuts, e.project(path, (20, 0))[0])
        assert [pts(p) for p in pieces] == [[(40, 0), (100, 0)]]
        assert removed == pytest.approx(40)

    def test_the_part_between_two_edges_goes_leaving_two_pieces(self):
        path = line((0, 0), (100, 0))
        cuts = e.intersections(path, line((30, -1), (30, 1))) + e.intersections(path, line((70, -1), (70, 1)))
        pieces, removed = e.trim(path, cuts, 50)
        assert [pts(p) for p in pieces] == [[(0, 0), (30, 0)], [(70, 0), (100, 0)]]
        assert removed == pytest.approx(40)

    def test_past_the_last_edge_it_goes_to_the_end(self):
        path = line((0, 0), (100, 0))
        pieces, _ = e.trim(path, [30, 70], 90)
        assert [pts(p) for p in pieces] == [[(0, 0), (70, 0)]]

    def test_no_edge_crossed_is_refused(self):
        with pytest.raises(ValueError, match="does not cross"):
            e.trim(line((0, 0), (100, 0)), [], 50)

    def test_an_edge_touching_only_the_end_is_not_a_cut(self):
        with pytest.raises(ValueError, match="does not cross"):
            e.trim(line((0, 0), (100, 0)), [100.0], 50)

    def test_a_point_on_the_edge_is_refused(self):
        with pytest.raises(ValueError, match="right on a cutting edge"):
            e.trim(line((0, 0), (100, 0)), [40.0], 40.0)

    def test_an_arc_keeps_its_centre_and_radius(self):
        arc = e.make_path([(10, 0), (-10, 0)], [1.0])  # 0 to 180 degrees, radius 10
        cuts = e.intersections(arc, line((0, -20), (0, 20)))
        pieces, _ = e.trim(arc, cuts, e.project(arc, (7, 7))[0])
        out = e.arc_of(pieces[0])
        assert out["centre"] == pytest.approx([0, 0], abs=1e-9)
        assert out["radius"] == pytest.approx(10)
        assert math.degrees(out["start_angle"]) == pytest.approx(90)
        assert math.degrees(out["end_angle"]) == pytest.approx(180)

    def test_a_closed_outline_opens_where_it_is_cut(self):
        box = rect(100, 50)
        cuts = e.intersections(box, line((60, -10), (60, 60)))
        assert cuts == pytest.approx([60, 190])
        pieces, removed = e.trim(box, cuts, e.project(box, (100, 25))[0])
        assert [pts(p) for p in pieces] == [[(60, 50), (0, 50), (0, 0), (60, 0)]]
        assert pieces[0]["closed"] is False
        assert removed == pytest.approx(130)

    def test_a_closed_outline_cut_round_its_first_corner(self):
        box = rect(100, 50)
        pieces, _ = e.trim(box, [60, 190], e.project(box, (0, 25))[0])
        assert [pts(p) for p in pieces] == [[(60, 0), (100, 0), (100, 50), (60, 50)]]

    def test_a_closed_outline_needs_two_cuts(self):
        with pytest.raises(ValueError, match="at least twice"):
            e.trim(rect(100, 50), [60], 10)

    def test_a_polyline_arc_is_cut_on_its_arc(self):
        # A run: straight 0-100, then a quarter turn left of radius 50.
        run = e.make_path([(0, 0), (100, 0), (150, 50)], [0.0, B90])
        cuts = e.intersections(run, line((50, -1), (50, 1)))
        pieces, _ = e.trim(run, cuts, 10)
        assert pts(pieces[0])[0] == (50, 0)
        assert pieces[0]["bulges"] == pytest.approx([0.0, B90])


# ---- extend ----------------------------------------------------------------------------


class TestExtend:
    def test_a_line_runs_on_to_the_boundary(self):
        out, gain = e.extend(line((0, 0), (50, 0)), True, [line((100, -10), (100, 10))])
        assert pts(out) == [(0, 0), (100, 0)]
        assert gain == pytest.approx(50)

    def test_the_start_end_runs_back(self):
        out, _ = e.extend(line((0, 0), (50, 0)), False, [line((-30, -10), (-30, 10))])
        assert pts(out) == [(-30, 0), (50, 0)]

    def test_the_nearest_boundary_ahead_wins(self):
        out, _ = e.extend(line((0, 0), (50, 0)), True, [line((100, -1), (100, 1)), line((80, -1), (80, 1))])
        assert pts(out)[-1] == (80, 0)

    def test_a_boundary_behind_or_beside_is_no_target(self):
        assert e.extend(line((0, 0), (50, 0)), True, [line((-30, -1), (-30, 1))]) is None
        assert e.extend(line((0, 0), (50, 0)), True, [line((100, 5), (100, 10))]) is None

    def test_an_arc_runs_on_round_its_circle(self):
        quarter = e.make_path([(10, 0), (0, 10)], [B90])
        out, gain = e.extend(quarter, True, [line((-20, 0), (-5, 0))])
        assert pts(out)[-1] == (-10, 0)
        assert out["bulges"][0] == pytest.approx(1.0)  # now a half circle
        assert gain == pytest.approx(math.pi / 2 * 10)

    def test_a_line_extends_to_a_circle(self):
        circle = e.make_path([(110, 0), (90, 0)], [1.0, 1.0], closed=True)
        out, _ = e.extend(line((0, 0), (50, 0)), True, [circle])
        assert pts(out)[-1] == (90, 0)

    def test_a_polyline_end_segment_runs_on(self):
        run = e.make_path([(0, 0), (50, 0), (50, 30)])
        out, _ = e.extend(run, True, [line((0, 100), (100, 100))])
        assert pts(out) == [(0, 0), (50, 0), (50, 100)]

    def test_a_closed_outline_has_no_end(self):
        with pytest.raises(ValueError, match="no end"):
            e.extend(rect(10, 10), True, [line((0, 0), (1, 1))])


# ---- break -----------------------------------------------------------------------------


class TestBreak:
    def test_at_a_point_makes_two_pieces(self):
        pieces = e.break_at(line((0, 0), (100, 0)), 40)
        assert [pts(p) for p in pieces] == [[(0, 0), (40, 0)], [(40, 0), (100, 0)]]

    def test_at_an_end_is_refused(self):
        with pytest.raises(ValueError, match="at an end"):
            e.break_at(line((0, 0), (100, 0)), 0)

    def test_a_closed_outline_opens_at_the_point(self):
        box = rect(100, 50)
        pieces = e.break_at(box, 40)
        assert len(pieces) == 1 and pieces[0]["closed"] is False
        assert pts(pieces[0])[0] == pts(pieces[0])[-1] == (40, 0)
        assert e.length(pieces[0]) == pytest.approx(300)

    def test_between_two_points_takes_out_the_gap(self):
        pieces = e.break_between(line((0, 0), (100, 0)), 60, 30)
        assert [pts(p) for p in pieces] == [[(0, 0), (30, 0)], [(60, 0), (100, 0)]]

    def test_between_an_end_and_a_point_leaves_one_piece(self):
        pieces = e.break_between(line((0, 0), (100, 0)), 0, 30)
        assert [pts(p) for p in pieces] == [[(30, 0), (100, 0)]]

    def test_between_both_ends_is_refused(self):
        with pytest.raises(ValueError, match="all of it"):
            e.break_between(line((0, 0), (100, 0)), 0, 100)

    def test_a_closed_outline_loses_the_part_from_first_to_second(self):
        pieces = e.break_between(rect(100, 50), 40, 120)
        assert pts(pieces[0])[0] == (100, 20) and pts(pieces[0])[-1] == (40, 0)
        assert e.length(pieces[0]) == pytest.approx(300 - 80)

    def test_an_arc_breaks_into_two_arcs_of_the_same_circle(self):
        arc = e.make_path([(10, 0), (-10, 0)], [1.0])
        first, second = e.break_at(arc, e.project(arc, (0, 10))[0])
        assert e.arc_of(first)["end_angle"] == pytest.approx(math.pi / 2)
        assert e.arc_of(second)["start_angle"] == pytest.approx(math.pi / 2)
        assert e.length(first) + e.length(second) == pytest.approx(10 * math.pi)


# ---- join ------------------------------------------------------------------------------


class TestJoin:
    def test_pieces_in_any_order_and_direction_join_into_one_run(self):
        a = line((10, 0), (0, 0))
        b = line((10, 0), (10, 10))
        c = line((20, 10), (10, 10))
        out = e.join([a, b, c])
        assert out["order"] == [(2, False), (1, True), (0, False)]
        assert pts(out["path"]) == [(20, 10), (10, 10), (10, 0), (0, 0)]
        assert out["kind"] == "polyline" and out["closed"] is False

    def test_lines_in_one_straight_line_join_into_one_line(self):
        out = e.join([line((0, 0), (40, 0)), line((100, 0), (40, 0))])
        assert out["kind"] == "line"
        assert pts(out["path"]) == [(0, 0), (100, 0)]

    def test_arcs_of_one_circle_join_into_one_arc(self):
        first = e.make_path([(10, 0), (0, 10)], [B90])
        second = e.make_path([(0, 10), (-10, 0)], [B90])
        out = e.join([second, first])
        assert out["kind"] == "arc"
        assert out["path"]["bulges"] == pytest.approx([1.0])

    def test_four_lines_round_a_room_close(self):
        sides = [line((0, 0), (100, 0)), line((100, 50), (100, 0)), line((100, 50), (0, 50)), line((0, 0), (0, 50))]
        out = e.join(sides)
        assert out["closed"] is True and out["kind"] == "polyline"
        assert len(out["path"]["vertices"]) == 4
        assert e.length(out["path"]) == pytest.approx(300)

    def test_a_corner_vertex_inside_a_polyline_is_kept(self):
        run = e.make_path([(0, 0), (50, 0), (100, 0)])  # a vertex where a tag sits
        out = e.join([run, line((100, 0), (100, 50))])
        assert pts(out["path"]) == [(0, 0), (50, 0), (100, 0), (100, 50)]

    def test_a_gap_is_refused_with_its_size(self):
        with pytest.raises(ValueError, match="nearest gap is 2"):
            e.join([line((0, 0), (10, 0)), line((12, 0), (20, 5))])

    def test_a_gap_within_the_given_gap_joins(self):
        out = e.join([line((0, 0), (10, 0)), line((10.5, 0), (20, 5))], gap=1.0)
        assert pts(out["path"]) == [(0, 0), (10, 0), (20, 5)]

    def test_a_branch_is_refused(self):
        with pytest.raises(ValueError, match="branch"):
            e.join([line((0, 0), (10, 0)), line((10, 0), (20, 0)), line((10, 0), (10, 10))])

    def test_a_closed_outline_is_refused(self):
        with pytest.raises(ValueError, match="closed"):
            e.join([rect(10, 10), line((0, 0), (-10, 0))])


# ---- fillet and chamfer between two lines -----------------------------------------------


class TestFilletLines:
    L1 = [(100, 0), (10, 0)]
    L2 = [(0, 100), (0, 10)]

    def test_tangent_points_and_centre_of_a_square_corner(self):
        out = e.fillet_lines(self.L1, self.L2, 20)
        assert out["line1"] == [[100, 0], [20, 0]]
        assert out["line2"] == [[0, 100], [0, 20]]
        assert out["arc"]["centre"] == pytest.approx([20, 20])
        assert math.degrees(out["arc"]["start_angle"]) == pytest.approx(180)
        assert math.degrees(out["arc"]["end_angle"]) == pytest.approx(270)

    def test_the_arc_is_tangent_to_both_lines(self):
        a = [(0, 0), (100, 0)]
        b = [(0, 0), (100 * math.cos(math.radians(60)), 100 * math.sin(math.radians(60)))]
        out = e.fillet_lines([a[1], (5, 0)], [b[1], (2, 2 * math.sqrt(3))], 10)
        c = out["arc"]["centre"]
        for t, direction in ((out["tangent_points"][0], (1, 0)), (out["tangent_points"][1], b[1])):
            radial = (t[0] - c[0], t[1] - c[1])
            assert math.hypot(*radial) == pytest.approx(10)
            assert radial[0] * direction[0] + radial[1] * direction[1] == pytest.approx(0, abs=1e-6)
        # On a 60 degree corner the tangent point is r / tan(30) from the corner.
        assert math.dist(out["tangent_points"][0], (0, 0)) == pytest.approx(10 / math.tan(math.radians(30)))

    def test_radius_zero_makes_a_sharp_corner(self):
        out = e.fillet_lines(self.L1, self.L2, 0)
        assert out["line1"] == [[100, 0], [0, 0]] and out["line2"] == [[0, 100], [0, 0]]
        assert out["arc"] is None

    def test_a_radius_too_big_says_the_largest_that_fits(self):
        with pytest.raises(ValueError, match="largest that fits is about 100"):
            e.fillet_lines(self.L1, self.L2, 150)

    def test_parallel_lines_are_refused(self):
        with pytest.raises(ValueError, match="parallel"):
            e.fillet_lines([(0, 0), (10, 0)], [(0, 5), (10, 5)], 2)

    def test_crossing_lines_keep_the_picked_parts(self):
        out = e.fillet_lines([(-50, 0), (50, 0)], [(0, -50), (0, 50)], 10, keep1=(40, 0), keep2=(0, -40))
        assert out["line1"] == [[10, 0], [50, 0]]
        assert out["line2"] == [[0, -10], [0, -50]] or out["line2"] == [[0, -50], [0, -10]]
        assert out["arc"]["centre"] == pytest.approx([10, -10])


class TestChamferLines:
    L1 = [(100, 0), (10, 0)]
    L2 = [(0, 100), (0, 10)]

    def test_two_distances_take_that_much_off_each_line(self):
        out = e.chamfer_lines(self.L1, self.L2, 10, 20)
        assert out["line1"] == [[100, 0], [10, 0]]
        assert out["line2"] == [[0, 100], [0, 20]]
        assert out["chamfer"] == [[10, 0], [0, 20]]

    def test_one_distance_is_both(self):
        assert e.chamfer_lines(self.L1, self.L2, 15)["chamfer"] == [[15, 0], [0, 15]]

    def test_distance_and_angle(self):
        out = e.chamfer_lines(self.L1, self.L2, 10, angle_degrees=30)
        assert out["distances"][1] == pytest.approx(10 * math.tan(math.radians(30)))
        assert e.chamfer_second(10, 45, math.pi / 2) == pytest.approx(10)

    def test_an_angle_that_never_reaches_is_refused(self):
        with pytest.raises(ValueError, match="does not reach"):
            e.chamfer_lines(self.L1, self.L2, 10, angle_degrees=95)

    def test_longer_than_the_line_is_refused(self):
        with pytest.raises(ValueError, match="longer than that line"):
            e.chamfer_lines(self.L1, self.L2, 200)

    def test_both_zero_is_a_sharp_corner(self):
        out = e.chamfer_lines(self.L1, self.L2, 0, 0)
        assert out["chamfer"] is None and out["line1"] == [[100, 0], [0, 0]]


# ---- a polyline's corners -----------------------------------------------------------------


class TestPolylineCorners:
    def test_a_left_turn_gets_an_anticlockwise_arc(self):
        path = e.make_path([(0, 0), (100, 0), (100, 100)])
        out, done, skipped = e.shape_corners(path, radius=10, vertices=[1])
        assert pts(out) == [(0, 0), (90, 0), (100, 10), (100, 100)]
        assert out["bulges"] == pytest.approx([0, B90, 0])
        assert done == [1] and skipped == []

    def test_a_right_turn_gets_a_clockwise_arc(self):
        out, _, _ = e.shape_corners(e.make_path([(0, 0), (100, 0), (100, -100)]), radius=10)
        assert out["bulges"][1] == pytest.approx(-B90)

    def test_every_corner_of_a_rectangle(self):
        out, done, _ = e.shape_corners(rect(100, 50), radius=10)
        assert done == [0, 1, 2, 3] and len(out["vertices"]) == 8
        assert e.length(out) == pytest.approx(300 - 80 + 2 * math.pi * 10)

    def test_a_square_rounded_by_half_its_side_is_a_circle(self):
        out, done, _ = e.shape_corners(rect(100, 100), radius=50)
        assert done == [0, 1, 2, 3] and len(out["vertices"]) == 4
        assert e.length(out) == pytest.approx(2 * math.pi * 50)

    def test_a_segment_too_short_for_the_radius_is_skipped_and_said(self):
        out, done, skipped = e.shape_corners(rect(100, 10), radius=10)
        assert done == []
        assert {row["vertex"] for row in skipped} == {0, 1, 2, 3}
        assert "too short" in skipped[0]["reason"]
        assert pts(out) == pts(rect(100, 10))

    def test_an_end_and_an_arc_corner_are_skipped(self):
        path = e.make_path([(0, 0), (100, 0), (150, 50), (150, 100)], [0, B90, 0])
        _, done, skipped = e.shape_corners(path, radius=5, vertices=[0, 1, 2])
        assert done == []
        reasons = {row["vertex"]: row["reason"] for row in skipped}
        assert "end" in reasons[0] and "arc" in reasons[1] and "arc" in reasons[2]

    def test_chamfer_every_corner_of_a_square(self):
        out, done, _ = e.shape_corners(rect(100, 100), distance1=10)
        assert len(out["vertices"]) == 8 and all(b == 0 for b in out["bulges"])
        assert e.length(out) == pytest.approx(4 * 80 + 4 * 10 * math.sqrt(2))

    def test_chamfer_two_distances_run_along_the_segment_before_then_after(self):
        out, _, _ = e.shape_corners(e.make_path([(0, 0), (100, 0), (100, 100)]), distance1=10, distance2=30)
        assert pts(out) == [(0, 0), (90, 0), (100, 30), (100, 100)]

    def test_a_vertex_that_does_not_exist(self):
        _, _, skipped = e.shape_corners(rect(10, 10), radius=1, vertices=[7])
        assert "no vertex 7" in skipped[0]["reason"]


# ---- vertices and stretch -----------------------------------------------------------------


class TestVertices:
    def test_move_one_corner_keeps_the_arcs(self):
        path = e.make_path([(0, 0), (100, 0), (100, 50)], [B90, 0])
        out = e.move_vertex(path, 2, (100, 80))
        assert pts(out) == [(0, 0), (100, 0), (100, 80)] and out["bulges"] == path["bulges"]

    def test_a_line_end(self):
        assert pts(e.move_vertex(line((0, 0), (10, 0)), 1, (25, 0))) == [(0, 0), (25, 0)]

    def test_onto_the_next_vertex_is_refused(self):
        with pytest.raises(ValueError, match="on top of each other"):
            e.move_vertex(line((0, 0), (10, 0)), 1, (0, 0))

    def test_nearest_vertex(self):
        assert e.nearest_vertex(rect(100, 50), (95, 48)) == 2

    def test_add_a_vertex_on_a_straight(self):
        out = e.add_vertex(rect(100, 50), 0, (50, -10))
        assert pts(out)[:3] == [(0, 0), (50, -10), (100, 0)] and len(out["bulges"]) == 5

    def test_add_a_vertex_on_an_arc_is_refused(self):
        with pytest.raises(ValueError, match="arc"):
            e.add_vertex(e.make_path([(0, 0), (10, 0)], [1.0]), 0, (5, 5))

    def test_remove_a_vertex_and_say_when_an_arc_went_straight(self):
        path = e.make_path([(0, 0), (50, 0), (100, 0), (100, 50)], [0, B90, 0])
        out, straightened = e.remove_vertex(path, 1)
        assert pts(out) == [(0, 0), (100, 0), (100, 50)] and straightened is True
        out, straightened = e.remove_vertex(path, 0)
        assert pts(out)[0] == (50, 0) and out["bulges"] == pytest.approx([B90, 0]) and straightened is False

    def test_too_few_vertices_left_is_refused(self):
        with pytest.raises(ValueError, match="too few"):
            e.remove_vertex(line((0, 0), (10, 0)), 0)


class TestStretch:
    def test_the_corners_inside_the_window_move(self):
        out, moved = e.stretch_path(rect(100, 50), e.window((110, 60), (90, -10)), (50, 0))
        assert moved == [1, 2]
        assert pts(out) == [(0, 0), (150, 0), (150, 50), (0, 50)]

    def test_nothing_inside_moves_nothing(self):
        out, moved = e.stretch_path(rect(100, 50), e.window((200, 200), (300, 300)), (50, 0))
        assert moved == [] and pts(out) == pts(rect(100, 50))

    def test_a_window_with_no_area_is_refused(self):
        with pytest.raises(ValueError, match="no area"):
            e.window((0, 0), (0, 10))

    def test_box_within(self):
        assert e.box_within((1, 1, 2, 2), (0, 0, 3, 3))
        assert not e.box_within((1, 1, 4, 2), (0, 0, 3, 3))


def test_reverse_twice_is_the_same_path():
    path = e.make_path([(0, 0), (10, 0), (10, 10), (0, 10)], [0.2, 0, -0.4, 0.1], closed=True)
    back = e.reverse(path)
    assert e.length(back) == pytest.approx(e.length(path))
    again = e.reverse(back)
    assert pts(again) == pts(path) and again["bulges"] == pytest.approx(path["bulges"])


def test_a_bulge_too_small_to_be_an_arc_joins_as_a_straight():
    """Found in review: a bulge under the straight limit crashed the joint merge."""
    a = e.make_path([(0, 0), (5, 0)], [5e-10])
    b = e.make_path([(5, 0), (10, 0)], [5e-10])
    out = e.join([a, b])
    assert out["kind"] == "line" and pts(out["path"]) == [(0, 0), (10, 0)]
