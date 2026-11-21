"""Overkill geometry (#112): what is erased, stretched and left, without AutoCAD."""

from __future__ import annotations

import math

import pytest

from autocad_mcp.acad import overkill


def line(handle, x1, y1, x2, y2, layer="0", z=0.0):
    return {"handle": handle, "kind": "line", "layer": layer, "start": [x1, y1, z], "end": [x2, y2, z]}


def arc(handle, cx, cy, r, start_deg, end_deg, layer="0"):
    return {
        "handle": handle, "kind": "arc", "layer": layer, "centre": [cx, cy, 0.0], "radius": r,
        "start_angle": math.radians(start_deg), "end_angle": math.radians(end_deg),
    }


def circle(handle, cx, cy, r, layer="0"):
    return {"handle": handle, "kind": "circle", "layer": layer, "centre": [cx, cy, 0.0], "radius": r}


def pline(handle, vertices, bulges=None, closed=False, layer="0"):
    return {"handle": handle, "kind": "polyline", "layer": layer, "vertices": vertices,
            "bulges": bulges or [0.0] * len(vertices), "closed": closed, "elevation": 0.0}


def erased(result):
    return {row["handle"]: row for row in result["erase"]}


def changed(result):
    return {row["handle"]: row for row in result["change"]}


class TestLines:
    def test_an_exact_copy_goes_and_the_oldest_stays(self):
        out = overkill.plan([line("2B", 0, 0, 1000, 0), line("1A", 0, 0, 1000, 0)])
        assert set(erased(out)) == {"2B"} and erased(out)["2B"]["kept"] == "1A"
        assert "copy" in erased(out)["2B"]["reason"] and out["change"] == []

    def test_a_copy_drawn_the_other_way_is_still_a_copy(self):
        out = overkill.plan([line("A", 0, 0, 1000, 500), line("B", 1000, 500, 0, 0)])
        assert set(erased(out)) == {"B"}

    def test_a_line_inside_a_longer_one_goes_without_stretching_it(self):
        out = overkill.plan([line("A", 0, 0, 1000, 0), line("B", 200, 0, 700, 0)])
        assert set(erased(out)) == {"B"} and "inside" in erased(out)["B"]["reason"]
        assert out["change"] == []

    def test_overlapping_lines_are_merged_into_the_oldest(self):
        out = overkill.plan([line("A", 0, 0, 600, 0), line("B", 400, 0, 1000, 0), line("C", 900, 0, 1500, 0)])
        assert set(erased(out)) == {"B", "C"}
        stretch = changed(out)["A"]
        assert stretch["start"] == pytest.approx([0, 0, 0]) and stretch["end"] == pytest.approx([1500, 0, 0])

    def test_the_kept_line_keeps_its_own_direction(self):
        out = overkill.plan([line("A", 600, 0, 0, 0), line("B", 400, 0, 1000, 0)])
        stretch = changed(out)["A"]
        assert stretch["start"] == pytest.approx([1000, 0, 0]) and stretch["end"] == pytest.approx([0, 0, 0])

    def test_lines_only_touching_end_to_end_stay_unless_asked(self):
        items = [line("A", 0, 0, 500, 0), line("B", 500, 0, 1000, 0)]
        assert overkill.plan(items)["erase"] == []
        out = overkill.plan(items, join_end_to_end=True)
        assert set(erased(out)) == {"B"} and changed(out)["A"]["end"] == pytest.approx([1000, 0, 0])

    def test_parallel_lines_a_little_apart_are_not_touched(self):
        assert overkill.plan([line("A", 0, 0, 1000, 0), line("B", 0, 0.01, 1000, 0.01)])["erase"] == []

    def test_the_tolerance_decides_how_close_is_the_same(self):
        items = [line("A", 0, 0, 1000, 0), line("B", 0, 0.0004, 1000, 0.0004)]
        assert overkill.plan(items)["erase"] == []
        assert set(erased(overkill.plan(items, tolerance=0.001))) == {"B"}

    def test_lines_crossing_are_left_alone(self):
        assert overkill.plan([line("A", 0, 0, 1000, 0), line("B", 500, -500, 500, 500)])["erase"] == []

    def test_a_diagonal_copy_far_from_the_origin_is_found(self):
        x, y = 512_345.678, 2_734_567.891
        out = overkill.plan([line("A", x, y, x + 3000, y + 4000), line("B", x + 1500, y + 2000, x + 6000, y + 8000)])
        assert set(erased(out)) == {"B"} and changed(out)["A"]["end"] == pytest.approx([x + 6000, y + 8000, 0])

    def test_a_vertical_line_and_its_reverse_meet_at_180_degrees(self):
        out = overkill.plan([line("A", 0, 0, 0, 1000), line("B", 0, 1500, 0, 800)])
        assert set(erased(out)) == {"B"} and changed(out)["A"]["end"] == pytest.approx([0, 1500, 0])

    def test_lines_on_other_layers_are_not_duplicates_unless_layers_are_ignored(self):
        items = [line("A", 0, 0, 1000, 0, layer="M-DUCT"), line("B", 0, 0, 1000, 0, layer="A-WALL")]
        assert overkill.plan(items)["erase"] == []
        assert set(erased(overkill.plan(items, ignore_layer=True))) == {"B"}

    def test_lines_at_other_heights_are_not_duplicates(self):
        assert overkill.plan([line("A", 0, 0, 1000, 0), line("B", 0, 0, 1000, 0, z=3000)])["erase"] == []

    def test_a_zero_length_line_goes(self):
        out = overkill.plan([line("A", 5, 5, 5, 5)])
        assert erased(out)["A"]["reason"] == "zero length"

    def test_a_line_with_ends_at_two_heights_is_skipped(self):
        item = {"handle": "A", "kind": "line", "layer": "0", "start": [0, 0, 0], "end": [100, 0, 50]}
        out = overkill.plan([item, line("B", 0, 0, 100, 0)])
        assert out["erase"] == [] and out["skipped"][0]["handle"] == "A"

    def test_lower_handle_wins_by_number_not_by_text(self):
        out = overkill.plan([line("9F", 0, 0, 10, 0), line("1A0", 0, 0, 10, 0)])
        assert set(erased(out)) == {"1A0"}


class TestPolylines:
    def test_a_copy_of_a_polyline_goes(self):
        a = pline("A", [[0, 0], [1000, 0], [1000, 500]])
        b = pline("B", [[0, 0], [1000, 0], [1000, 500]])
        assert set(erased(overkill.plan([a, b]))) == {"B"}

    def test_a_polyline_drawn_backwards_is_a_copy(self):
        a = pline("A", [[0, 0], [1000, 0], [1000, 500]], [0.5, 0, 0])
        b = pline("B", [[1000, 500], [1000, 0], [0, 0]], [0, -0.5, 0])
        assert set(erased(overkill.plan([a, b]))) == {"B"}

    def test_a_closed_polyline_starting_at_another_corner_is_a_copy(self):
        a = pline("A", [[0, 0], [10, 0], [10, 10], [0, 10]], closed=True)
        b = pline("B", [[10, 10], [0, 10], [0, 0], [10, 0]], closed=True)
        c = pline("C", [[0, 10], [10, 10], [10, 0], [0, 0]], closed=True)  # the other way round
        assert set(erased(overkill.plan([a, b, c]))) == {"B", "C"}

    def test_a_loose_line_on_a_polyline_segment_goes_and_the_polyline_is_never_changed(self):
        out = overkill.plan([pline("A", [[0, 0], [1000, 0], [1000, 500]]), line("B", 100, 0, 900, 0)])
        assert set(erased(out)) == {"B"} and "polyline A" in erased(out)["B"]["reason"]
        assert out["change"] == []

    def test_a_loose_line_over_two_segments_of_a_straight_run_goes(self):
        out = overkill.plan([pline("A", [[0, 0], [500, 0], [1000, 0]]), line("B", 100, 0, 900, 0)])
        assert set(erased(out)) == {"B"}

    def test_a_line_partly_on_a_polyline_is_left_and_listed(self):
        out = overkill.plan([pline("A", [[0, 0], [1000, 0]]), line("B", 500, 0, 1500, 0)])
        assert out["erase"] == []
        assert out["left"] and set(out["left"][0]["handles"]) == {"A", "B"}

    def test_two_overlapping_polylines_are_left_and_listed(self):
        out = overkill.plan([pline("A", [[0, 0], [1000, 0]]), pline("B", [[500, 0], [1500, 0]])])
        assert out["erase"] == [] and "polylines overlap" in out["left"][0]["why"]

    def test_a_polyline_doubling_back_is_listed(self):
        out = overkill.plan([pline("A", [[0, 0], [1000, 0], [400, 0]])])
        assert out["erase"] == [] and "doubles back" in out["left"][0]["why"]


class TestArcsAndCircles:
    def test_a_copy_of_an_arc_goes(self):
        out = overkill.plan([arc("A", 0, 0, 500, 0, 90), arc("B", 0, 0, 500, 0, 90)])
        assert set(erased(out)) == {"B"}

    def test_overlapping_arcs_are_merged(self):
        out = overkill.plan([arc("A", 0, 0, 500, 0, 90), arc("B", 0, 0, 500, 60, 150)])
        assert set(erased(out)) == {"B"}
        assert math.degrees(changed(out)["A"]["end_angle"]) == pytest.approx(150)

    def test_arcs_across_zero_degrees_are_merged(self):
        out = overkill.plan([arc("A", 0, 0, 500, 300, 20), arc("B", 0, 0, 500, 10, 60)])
        stretch = changed(out)["A"]
        assert math.degrees(stretch["start_angle"]) == pytest.approx(300)
        assert math.degrees(stretch["end_angle"]) == pytest.approx(60)

    def test_arcs_on_a_circle_go_and_copies_of_the_circle_go(self):
        out = overkill.plan([circle("A", 0, 0, 500), circle("B", 0, 0, 500), arc("C", 0, 0, 500, 10, 80)])
        assert set(erased(out)) == {"B", "C"}

    def test_arcs_making_a_whole_circle_are_left_not_made_one_arc(self):
        out = overkill.plan([arc("A", 0, 0, 500, 0, 200), arc("B", 0, 0, 500, 180, 10)])
        assert out["change"] == []
        assert any("whole circle" in row["why"] for row in out["left"])

    def test_an_arc_on_a_polyline_arc_goes(self):
        # A bulge of 1 is a half circle, counter-clockwise: (1000,0) over the top to (0,0).
        half = pline("P", [[1000, 0], [0, 0]], [1.0, 0.0])
        out = overkill.plan([half, arc("A", 500, 0, 500, 30, 150), arc("B", 500, 0, 500, 200, 300)])
        assert set(erased(out)) == {"A"}

    def test_concentric_arcs_of_other_sizes_stay(self):
        assert overkill.plan([arc("A", 0, 0, 500, 0, 90), arc("B", 0, 0, 510, 0, 90)])["erase"] == []

    def test_a_circle_and_a_polyline_circle_the_same(self):
        ring = pline("P", [[500, 0], [-500, 0]], [1.0, 1.0], closed=True)
        out = overkill.plan([ring, circle("C", 0, 0, 500)])
        assert set(erased(out)) == {"C"}


class TestPlan:
    def test_it_changes_nothing_and_counts_what_it_looked_at(self):
        items = [line("A", 0, 0, 1, 0), {"handle": "T", "kind": "text", "layer": "0"}]
        out = overkill.plan(items)
        assert out["looked_at"] == 2 and out["skipped"][0]["handle"] == "T"

    def test_a_curve_not_flat_in_plan_is_skipped(self):
        item = circle("A", 0, 0, 5) | {"normal": [0, 0, -1]}
        out = overkill.plan([item, circle("B", 0, 0, 5)])
        assert out["erase"] == [] and out["skipped"][0]["why"] == "not drawn flat in plan"

    def test_a_tolerance_of_zero_is_refused(self):
        with pytest.raises(ValueError):
            overkill.plan([], tolerance=0)

    def test_a_large_imported_plan_is_quick(self):
        import time

        items = []
        for i in range(3000):
            items.append(line(f"{i * 2 + 16:X}", 0, i * 100, 5000, i * 100))
            items.append(line(f"{i * 2 + 17:X}", 2500, i * 100, 7500, i * 100))
        began = time.perf_counter()
        out = overkill.plan(items)
        assert len(out["erase"]) == 3000 and len(out["change"]) == 3000
        assert time.perf_counter() - began < 10


def _dist_to_line(p, a, b):
    length = math.dist(a, b)
    return abs((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / length


class TestTheToleranceNeverChains:
    """From the review of PR #150: a pair-by-pair check let a whole curve become one line."""

    def kept_line(self, items, out, handle):
        row = changed(out).get(handle)
        if row:
            return row["start"][:2], row["end"][:2]
        item = next(i for i in items if i["handle"] == handle)
        return item["start"][:2], item["end"][:2]

    def check_within(self, items, out, tol):
        by_handle = {i["handle"]: i for i in items}
        for row in out["erase"]:
            if "kept" not in row or by_handle[row["kept"]]["kind"] != "line":
                continue
            a, b = self.kept_line(items, out, row["kept"])
            gone = by_handle[row["handle"]]
            for end in (gone["start"], gone["end"]):
                assert _dist_to_line(end[:2], a, b) <= tol * (1 + 1e-9), (row, end)

    def curve(self, radius, count, step_length, piece_length):
        items = []
        for i in range(count):
            a0 = i * step_length / radius
            a1 = a0 + piece_length / radius
            p = (radius * math.sin(a0), radius - radius * math.cos(a0))
            q = (radius * math.sin(a1), radius - radius * math.cos(a1))
            items.append(line(f"{0x100 + i:X}", *p, *q))
        return items

    def test_a_curve_drawn_as_short_lines_end_to_end_is_not_straightened(self):
        items = self.curve(3000.0, 60, 5.0, 5.0)
        out = overkill.plan(items, tolerance=0.01, join_end_to_end=True)
        self.check_within(items, out, 0.01)
        assert len(out["erase"]) < 59

    def test_kinked_overlapping_pieces_are_not_straightened(self):
        items = self.curve(3000.0, 40, 5.0, 10.0)
        out = overkill.plan(items, tolerance=0.05)
        self.check_within(items, out, 0.05)

    def test_parallel_lines_each_within_tolerance_of_the_next_are_not_all_one(self):
        items = [line("10", 0, 0, 100, 0), line("11", 0, 0.9, 50, 0.9), line("12", 0, 1.8, 25, 1.8), line("13", 0, 2.7, 12, 2.7)]
        out = overkill.plan(items, tolerance=1.0)
        self.check_within(items, out, 1.0)
        assert {h: r["kept"] for h, r in erased(out).items()} == {"11": "10", "13": "12"}

    def test_concentric_arcs_creeping_out_are_not_all_one(self):
        items = [arc(f"{0x20 + i:X}", 0, 0, 500 + 0.9 * i, 0, 90) for i in range(4)]
        out = overkill.plan(items, tolerance=1.0)
        for row in out["erase"]:
            kept = next(i for i in items if i["handle"] == row["kept"])
            gone = next(i for i in items if i["handle"] == row["handle"])
            assert abs(kept["radius"] - gone["radius"]) <= 1.0

    def test_a_stretched_line_stays_on_its_own_line(self):
        out = overkill.plan([line("A", 0, 0, 1000, 0.0004), line("B", 500, 0.0002, 2000, 0.0009)], tolerance=0.001)
        stretch = changed(out)["A"]
        # Along A's own direction, not through B's far end.
        assert stretch["end"][1] == pytest.approx(2000 * 0.0004 / 1000, abs=1e-9)

    def test_an_arc_whose_ends_meet_is_left_alone(self):
        item = arc("A", 0, 0, 500, 0, 360)
        out = overkill.plan([item])
        assert out["erase"] == [] and out["skipped"][0]["handle"] == "A"
