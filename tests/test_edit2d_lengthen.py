"""Lengthen, and fillet or chamfer between a line, an arc and a polyline's end (issue #154, D-144).

The geometry of acad/edit2d.py checked without AutoCAD. Each answer is checked against a
number a draftsman could measure, worked out here by hand from the drawing's own figures
(a distance between two centres, how far a centre sits from a line, an arc's length),
not by calling the code under test a second time.
"""

from __future__ import annotations

import math

import pytest

from autocad_mcp.acad import edit2d as e

QUARTER = math.tan(math.radians(90) / 4)  # a quarter circle as a bulge


def line(a, b):
    return e.line_path(a, b)


def arc(centre, radius, start_deg, end_deg):
    """An anticlockwise arc as a one-segment path."""
    a0, a1 = math.radians(start_deg), math.radians(end_deg)
    p0 = (centre[0] + radius * math.cos(a0), centre[1] + radius * math.sin(a0))
    p1 = (centre[0] + radius * math.cos(a1), centre[1] + radius * math.sin(a1))
    return e.make_path([p0, p1], [math.tan((a1 - a0) / 4)])


def pts(path):
    return [tuple(round(c, 6) for c in v) for v in path["vertices"]]


def seg(path):
    return e._segs(path)[0]


def degrees_of(path):
    """(start, end) of a one-arc path in degrees, anticlockwise."""
    a = e.arc_of(path)
    return math.degrees(a["start_angle"]), math.degrees(a["end_angle"])


# ---- lengthen -----------------------------------------------------------------------------


class TestLengthenALine:
    def test_delta_grows_the_end(self):
        out, now, change = e.lengthen(line((0, 0), (1000, 0)), True, "delta", 500)
        assert pts(out) == [(0, 0), (1500, 0)] and now == pytest.approx(1500) and change == pytest.approx(500)

    def test_delta_grows_the_start(self):
        out, now, _ = e.lengthen(line((0, 0), (1000, 0)), False, "delta", 500)
        assert pts(out) == [(-500, 0), (1000, 0)] and now == pytest.approx(1500)

    def test_a_negative_delta_cuts_the_end_back(self):
        out, now, change = e.lengthen(line((0, 0), (1000, 0)), True, "delta", -200)
        assert pts(out) == [(0, 0), (800, 0)] and change == pytest.approx(-200)

    def test_a_sloping_line_keeps_its_direction(self):
        out, now, _ = e.lengthen(line((0, 0), (300, 400)), True, "delta", 500)
        assert pts(out) == [(0, 0), (600, 800)] and now == pytest.approx(1000)

    def test_total_sets_the_whole_length(self):
        out, now, change = e.lengthen(line((0, 0), (1000, 0)), False, "total", 2400)
        assert pts(out) == [(-1400, 0), (1000, 0)] and now == 2400 and change == pytest.approx(1400)

    def test_percent_is_of_the_length_now(self):
        out, now, _ = e.lengthen(line((0, 0), (1000, 0)), True, "percent", 150)
        assert pts(out) == [(0, 0), (1500, 0)] and now == pytest.approx(1500)
        out, now, _ = e.lengthen(line((0, 0), (1000, 0)), True, "percent", 25)
        assert pts(out) == [(0, 0), (250, 0)]

    def test_a_hundred_percent_changes_nothing(self):
        path = line((0, 0), (1000, 0))
        out, now, change = e.lengthen(path, True, "percent", 100)
        assert out is path and change == 0

    def test_a_cut_that_leaves_nothing_is_refused(self):
        with pytest.raises(ValueError, match="vanish"):
            e.lengthen(line((0, 0), (1000, 0)), True, "delta", -1000)
        with pytest.raises(ValueError, match="vanish"):
            e.lengthen(line((0, 0), (1000, 0)), True, "total", 0)

    def test_percent_must_be_above_zero(self):
        with pytest.raises(ValueError, match="above 0"):
            e.lengthen(line((0, 0), (1000, 0)), True, "percent", 0)

    def test_an_unknown_mode_is_refused(self):
        with pytest.raises(ValueError, match="delta, total or percent"):
            e.lengthen(line((0, 0), (1000, 0)), True, "dynamic", 5)


class TestLengthenAnArc:
    def test_a_quarter_circle_grows_to_a_half_circle(self):
        r = 500
        out, now, _ = e.lengthen(arc((0, 0), r, 0, 90), True, "delta", r * math.pi / 2)
        assert now == pytest.approx(r * math.pi)
        start, end = degrees_of(out)
        assert (round(start, 6) % 360, round(end, 6)) == (0, 180)
        assert seg(out).centre == pytest.approx((0, 0)) and seg(out).radius == pytest.approx(r)

    def test_the_start_end_grows_the_other_way_round(self):
        out, _, _ = e.lengthen(arc((0, 0), 500, 0, 90), False, "delta", 500 * math.pi / 4)
        start, end = degrees_of(out)
        assert round(start, 6) % 360 == 315 and round(end, 6) == 90

    def test_percent_cuts_an_arc_back_on_its_own_circle(self):
        out, now, _ = e.lengthen(arc((0, 0), 500, 0, 90), True, "percent", 50)
        start, end = degrees_of(out)
        assert (round(start, 6) % 360, round(end, 6)) == (0, 45)
        assert now == pytest.approx(500 * math.pi / 4)

    def test_it_cannot_grow_to_a_full_circle(self):
        with pytest.raises(ValueError, match="full circle"):
            e.lengthen(arc((0, 0), 500, 0, 90), True, "delta", 500 * 2 * math.pi)

    def test_a_clockwise_arc_end_grows_clockwise(self):
        path = e.reverse(arc((0, 0), 500, 0, 90))  # drawn from 90 round to 0
        out, now, _ = e.lengthen(path, True, "delta", 500 * math.pi / 4)  # its end is the 0 degree side
        start, end = degrees_of(out)
        assert round(start, 6) % 360 == 315 and round(end, 6) == 90
        assert now == pytest.approx(500 * math.pi * 3 / 4)


class TestLengthenAPolyline:
    def test_a_cut_runs_back_over_a_corner(self):
        path = e.make_path([(0, 0), (1000, 0), (1000, 500)])
        out, now, _ = e.lengthen(path, True, "delta", -700)
        assert pts(out) == [(0, 0), (800, 0)] and now == pytest.approx(800)

    def test_growing_runs_on_along_the_last_segment(self):
        path = e.make_path([(0, 0), (1000, 0), (1000, 500)])
        out, now, _ = e.lengthen(path, True, "delta", 250)
        assert pts(out) == [(0, 0), (1000, 0), (1000, 750)] and now == pytest.approx(1750)

    def test_growing_the_start_runs_on_along_the_first_segment(self):
        path = e.make_path([(0, 0), (1000, 0), (1000, 500)])
        out, _, _ = e.lengthen(path, False, "delta", 100)
        assert pts(out) == [(-100, 0), (1000, 0), (1000, 500)]

    def test_an_arc_in_the_polyline_stays_an_arc(self):
        # a straight run, then a quarter circle r 100 up to the right
        path = e.make_path([(0, 0), (100, 0), (200, 100)], [0, QUARTER])
        out, now, _ = e.lengthen(path, True, "delta", -50)  # cuts 50 round the arc
        assert now == pytest.approx(100 + 100 * math.pi / 2 - 50)
        assert out["bulges"][0] == 0 and out["bulges"][1] > 0
        # the arc's centre is (100, 100); it ran from -90 to 0 degrees and now stops 50 / 100 radians short of 0
        turned = -0.5
        end = out["vertices"][-1]
        assert end == pytest.approx((100 + 100 * math.cos(turned), 100 + 100 * math.sin(turned)), abs=1e-6)

    def test_a_closed_polyline_has_no_end(self):
        path = e.make_path([(0, 0), (10, 0), (10, 10)], closed=True)
        with pytest.raises(ValueError, match="closed"):
            e.lengthen(path, True, "delta", 5)

    def test_a_polyline_cut_back_by_its_whole_length_is_refused(self):
        with pytest.raises(ValueError, match="vanish"):
            e.lengthen(e.make_path([(0, 0), (10, 0), (10, 10)]), True, "delta", -20)


# ---- fillet between a line and an arc ---------------------------------------------------------


class TestFilletLineAndArc:
    """An arc r 500 at the origin (0 to 90) and the line y = 300: they meet at (400, 300)."""

    def run(self, radius=50, **kw):
        return e.fillet_curves(line((100, 300), (1500, 300)), arc((0, 0), 500, 0, 90), radius, **kw)

    def test_the_new_arc_touches_both_from_outside(self):
        out = self.run()
        centre = out["arc"]["centre"]
        assert out["arc"]["radius"] == 50
        assert math.hypot(*centre) == pytest.approx(550, abs=1e-6)  # outside the big circle: R + r
        assert centre[1] - 300 == pytest.approx(50, abs=1e-6)  # r above the line
        assert centre[0] == pytest.approx(math.sqrt(550**2 - 350**2), abs=1e-6)

    def test_the_line_is_trimmed_to_its_tangent_point_and_keeps_its_far_end(self):
        out = self.run()
        x = math.sqrt(550**2 - 350**2)
        assert pts(out["curve1"]) == [(round(x, 6), 300.0), (1500.0, 300.0)]
        assert out["tangent_points"][0] == pytest.approx([x, 300], abs=1e-6)

    def test_the_arc_keeps_its_far_end_and_is_cut_back_to_the_tangent_point(self):
        out = self.run()
        kept = out["curve2"]
        assert kept["vertices"][-1] == pytest.approx((0, 500), abs=1e-6)  # still ends at 90 degrees
        start = kept["vertices"][0]
        assert math.hypot(*start) == pytest.approx(500, abs=1e-6)  # on the same circle
        # the tangent point is on the line from the origin to the fillet centre
        centre = out["arc"]["centre"]
        assert start == pytest.approx([centre[0] * 500 / 550, centre[1] * 500 / 550], abs=1e-6)

    def test_the_fillet_arc_is_the_short_way_round_and_anticlockwise(self):
        out = self.run()
        a = out["arc"]
        sweep = (a["end_angle"] - a["start_angle"]) % (2 * math.pi)
        assert 0 < sweep < math.pi
        # it ends on the tangent points
        for t, ang in zip(out["tangent_points"], (a["start_angle"], a["end_angle"]), strict=False):
            assert (a["centre"][0] + 50 * math.cos(ang), a["centre"][1] + 50 * math.sin(ang)) in (
                pytest.approx(tuple(out["tangent_points"][0]), abs=1e-6),
                pytest.approx(tuple(out["tangent_points"][1]), abs=1e-6),
            ), t

    def test_two_meeting_points_say_so_and_keep_points_choose(self):
        out = self.run()
        assert "more than one place" in out["note"]
        # the other meeting point is at (-400, 300) of the circle, off the drawn arc and the line
        out2 = self.run(keep1=(1400, 300), keep2=(0, 490))
        assert "note" not in out2 and out2["corner"] == pytest.approx([400, 300], abs=1e-6)

    def test_radius_zero_is_a_sharp_corner_with_no_arc(self):
        out = self.run(radius=0)
        assert out["arc"] is None and out["corner"] == pytest.approx([400, 300], abs=1e-6)
        assert pts(out["curve1"])[0] == (400.0, 300.0)
        assert out["curve2"]["vertices"][0] == pytest.approx((400, 300), abs=1e-6)

    def test_inside_the_circle_the_fillet_is_tangent_from_inside(self):
        # the vertical line x = 200 meets the circle at (200, 458.26); keep the parts below and to the right
        out = e.fillet_curves(line((200, 0), (200, 600)), arc((0, 0), 500, 0, 90), 50,
                              keep1=(200, 50), keep2=(480, 100))
        centre = out["arc"]["centre"]
        assert math.hypot(*centre) == pytest.approx(450, abs=1e-6)  # inside the big circle: R - r
        assert abs(centre[0] - 200) == pytest.approx(50, abs=1e-6)

    def test_an_arc_that_meets_the_line_only_when_run_on_is_extended(self):
        # this arc stops at 20 degrees; the line y = 300 meets the circle at 36.87 degrees
        out = e.fillet_curves(line((100, 300), (1500, 300)), arc((0, 0), 500, 0, 20), 50, keep2=(500, 0))
        fixed, moved = out["curve2"]["vertices"][0], out["curve2"]["vertices"][-1]
        assert fixed == pytest.approx((500, 0), abs=1e-6)  # the end kept does not move
        assert math.hypot(*moved) == pytest.approx(500, abs=1e-6)  # still on the circle
        assert math.degrees(math.atan2(moved[1], moved[0])) > 20  # run on past the old end

    def test_a_radius_too_big_is_refused_with_a_hint(self):
        with pytest.raises(ValueError, match="Try a smaller radius"):
            self.run(radius=50000)

    def test_a_line_and_an_arc_that_never_meet_are_refused(self):
        with pytest.raises(ValueError, match="never meet"):
            e.fillet_curves(line((0, 1000), (100, 1000)), arc((0, 0), 500, 0, 90), 10)

    def test_a_negative_radius_is_refused(self):
        with pytest.raises(ValueError, match="negative"):
            self.run(radius=-1)

    def test_a_point_to_keep_at_the_corner_is_refused(self):
        with pytest.raises(ValueError, match="right at the corner"):
            self.run(keep1=(400, 300))


class TestFilletTwoArcs:
    def test_the_new_arc_is_550_from_both_centres(self):
        a, b = arc((0, 0), 500, 0, 90), arc((800, 0), 500, 90, 180)
        out = e.fillet_curves(a, b, 50)
        centre = out["arc"]["centre"]
        assert math.dist(centre, (0, 0)) == pytest.approx(550, abs=1e-6)
        assert math.dist(centre, (800, 0)) == pytest.approx(550, abs=1e-6)
        assert centre == pytest.approx([400, math.sqrt(550**2 - 400**2)], abs=1e-6)
        assert out["corner"] == pytest.approx([400, 300], abs=1e-6)

    def test_each_arc_stays_on_its_own_circle(self):
        out = e.fillet_curves(arc((0, 0), 500, 0, 90), arc((800, 0), 500, 90, 180), 50)
        for kept, centre in ((out["curve1"], (0, 0)), (out["curve2"], (800, 0))):
            for v in kept["vertices"]:
                assert math.dist(v, centre) == pytest.approx(500, abs=1e-6)


class TestFilletAgreesWithTheTwoLineMaths:
    @pytest.mark.parametrize("radius", [5, 15, 40])
    def test_two_lines_give_the_same_arc(self, radius):
        l1, l2 = [[0, 0], [100, 0]], [[120, 10], [120, 100]]
        old = e.fillet_lines(l1, l2, radius)
        new = e.fillet_curves(line(*l1), line(*l2), radius)
        assert new["arc"]["centre"] == pytest.approx(old["arc"]["centre"], abs=1e-6)
        for got, want in zip(new["tangent_points"], old["tangent_points"], strict=True):
            assert got == pytest.approx(want, abs=1e-6)
        assert pts(new["curve1"]) == [tuple(p) for p in old["line1"]]
        assert pts(new["curve2"]) == [tuple(p) for p in old["line2"]]

    def test_the_two_line_sharp_corner_agrees_too(self):
        out = e.fillet_curves(line((100, 0), (10, 0)), line((0, 100), (0, 10)), 0)
        assert pts(out["curve1"]) == [(0, 0), (100, 0)] or pts(out["curve1"]) == [(100, 0), (0, 0)]


# ---- chamfer between curves ---------------------------------------------------------------------


class TestChamferCurves:
    def run(self, d1=40, d2=40, **kw):
        return e.chamfer_curves(line((100, 300), (1500, 300)), arc((0, 0), 500, 0, 90), d1, d2, **kw)

    def test_the_line_end_is_d1_along_the_line_from_the_corner(self):
        out = self.run(keep1=(1400, 300), keep2=(0, 490))
        cut = out["chamfer"]
        assert cut[0] == pytest.approx([440, 300], abs=1e-6)

    def test_the_arc_end_is_d2_along_the_arc_from_the_corner(self):
        out = self.run(keep1=(1400, 300), keep2=(0, 490))
        end = out["chamfer"][1]
        assert math.hypot(*end) == pytest.approx(500, abs=1e-6)
        turned = math.atan2(end[1], end[0]) - math.atan2(300, 400)
        assert turned == pytest.approx(40 / 500, abs=1e-9)  # arc length / radius

    def test_the_kept_curves_start_at_the_chamfer_ends(self):
        out = self.run(keep1=(1400, 300), keep2=(0, 490))
        assert out["curve1"]["vertices"][0] == pytest.approx(out["chamfer"][0], abs=1e-6)
        assert out["curve2"]["vertices"][0] == pytest.approx(out["chamfer"][1], abs=1e-6)

    def test_both_zero_is_a_sharp_corner(self):
        out = self.run(0, 0, keep1=(1400, 300), keep2=(0, 490))
        assert out["chamfer"] is None and out["curve1"]["vertices"][0] == pytest.approx((400, 300), abs=1e-6)

    def test_one_zero_is_refused(self):
        with pytest.raises(ValueError, match="both"):
            self.run(0, 10)

    def test_a_chamfer_longer_than_the_line_reaches_is_refused(self):
        with pytest.raises(ValueError, match="does not fit"):
            e.chamfer_curves(line((380, 300), (480, 300)), arc((0, 0), 500, 0, 90), 150, 10, keep1=(470, 300))

    def test_a_distance_is_not_negative(self):
        with pytest.raises(ValueError, match="negative"):
            self.run(-1, 5)

    def test_one_distance_serves_both_sides(self):
        out = self.run(40, None, keep1=(1400, 300), keep2=(0, 490))
        assert out["distances"] == [40.0, 40.0]


# ---- the ends of polylines -------------------------------------------------------------------------


class TestEndSegments:
    def test_the_last_segment_is_cut_out_with_the_vertex_to_keep(self):
        path = e.make_path([(0, 0), (1000, 0), (1000, 300)])
        curve, keep = e.end_segment(path, True)
        assert pts(curve) == [(1000, 0), (1000, 300)] and keep == (1000, 0)

    def test_the_first_segment_is_read_from_the_start_end(self):
        path = e.make_path([(0, 0), (1000, 0), (1000, 300)])
        curve, keep = e.end_segment(path, False)
        assert pts(curve) == [(1000, 0), (0, 0)] and keep == (1000, 0)

    def test_put_back_it_leaves_the_other_vertices_and_bulges(self):
        path = e.make_path([(0, 0), (100, 0), (200, 100)], [0, QUARTER])
        curve, _ = e.end_segment(path, True)
        again = e.with_end_segment(path, True, curve)
        assert pts(again) == pts(path) and again["bulges"] == pytest.approx(path["bulges"])

    def test_a_closed_polyline_has_no_end(self):
        with pytest.raises(ValueError, match="closed"):
            e.end_segment(e.make_path([(0, 0), (1, 0), (1, 1)], closed=True), True)


class TestShapePair:
    first = e.make_path([(0, 0), (1000, 0), (1000, 300)])
    second = e.make_path([(1500, 900), (1500, 600), (1300, 600)])

    def test_two_polylines_meet_at_the_ends_that_make_the_nearer_corner(self):
        out = e.shape_pair(self.first, self.second, polyline1=True, polyline2=True, radius=100)
        assert out["ends"] == ["end", "end"]
        assert pts(out["path1"]) == [(0, 0), (1000, 0), (1000, 500)]
        assert pts(out["path2"]) == [(1500, 900), (1500, 600), (1100, 600)]
        assert out["arc"]["centre"] == pytest.approx([1100, 500], abs=1e-6)
        assert out["corner"] == pytest.approx([1000, 600], abs=1e-6)

    def test_the_polyline_read_from_its_start_gives_the_same(self):
        out = e.shape_pair(e.reverse(self.first), e.reverse(self.second), polyline1=True, polyline2=True, radius=100)
        assert out["ends"] == ["start", "start"]
        assert pts(out["path1"]) == [(1000, 500), (1000, 0), (0, 0)]
        assert pts(out["path2"]) == [(1100, 600), (1500, 600), (1500, 900)]

    def test_a_polyline_and_an_arc(self):
        out = e.shape_pair(self.first, arc((1500, 600), 600, 90, 180), polyline1=True, radius=50)
        # the arc r 600 at 1500,600 crosses x = 1000 at y = 268.34 and 931.66; a polyline keeps its
        # body, so the corner nearest that body (the first) is the one used
        assert out["ends"][0] == "end" and out["arc"] is not None
        assert out["corner"] == pytest.approx([1000, 600 - math.sqrt(600**2 - 500**2)], abs=1e-6)
        for v in out["path2"]["vertices"]:
            assert math.dist(v, (1500, 600)) == pytest.approx(600, abs=1e-6)

    def test_the_bulge_of_a_polyline_end_arc_is_kept(self):
        curved = e.make_path([(0, 0), (500, 0), (700, 200)], [0, math.tan(math.radians(45) / 4)])
        out = e.shape_pair(curved, line((1000, 100), (1000, 900)), polyline1=True, radius=20)
        assert out["path1"]["bulges"][0] == 0 and len(out["path1"]["vertices"]) == 3

    def test_two_polylines_that_do_not_meet_say_why(self):
        with pytest.raises(ValueError, match="never meet|run in one straight line"):
            e.shape_pair(e.make_path([(0, 0), (10, 0), (10, 10)]), e.make_path([(0, 50), (10, 50), (10, 60)]),
                         polyline1=True, polyline2=True, radius=1)

    def test_a_chamfer_between_two_polyline_ends(self):
        out = e.shape_pair(self.first, self.second, polyline1=True, polyline2=True, distance1=100, distance2=50)
        assert out["chamfer"][0] == pytest.approx([1000, 500], abs=1e-6)
        assert out["chamfer"][1] == pytest.approx([1050, 600], abs=1e-6)
        assert out["distances"] == [100.0, 50.0]
