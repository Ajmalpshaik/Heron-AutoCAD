"""autocad_break_at_blocks on polylines with arcs (#52, D-97), without AutoCAD.

The cut is plain arithmetic in acad/geometry.py: where an arc crosses the
sides of a block's box, and the bulge each piece keeps. Each test rebuilds the
pieces from their own bulges and checks they lie on the arc they came from -
the same centre, the same radius, the length that is left.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.acad import geometry as g
from autocad_mcp.tools import geometry_tools


def rebuilt(run):
    """The segments of one run, made again from its points and bulges."""
    return g.segments(run["points"], run["bulges"], False)


def length(runs):
    return sum(s.length for run in runs for s in rebuilt(run))


class TestStraightRuns:
    def test_a_straight_path_cuts_as_it_always_did(self):
        runs, cut = g.bulged_outside([(0, 0), (10, 0), (10, 10)], [0, 0], False, (4, -1, 6, 1))
        assert cut and [r["points"] for r in runs] == g.path_outside([(0, 0), (10, 0), (10, 10)], (4, -1, 6, 1))
        assert all(b == 0.0 for r in runs for b in r["bulges"])

    def test_a_path_clear_of_the_box_is_not_cut(self):
        runs, cut = g.bulged_outside([(0, 0), (10, 0)], [0], False, (20, 20, 30, 30))
        assert not cut and runs == [{"points": [(0.0, 0.0), (10.0, 0.0)], "bulges": [0.0]}]


class TestArcs:
    # A half round from (0, 0) to (20, 0), anticlockwise about (10, 0): it dips to (10, -10).
    HALF = ([(0, 0), (20, 0)], [1.0])

    def test_an_arc_is_cut_where_it_crosses_the_box(self):
        box = (8, -12, 12, -8)
        runs, cut = g.bulged_outside(*self.HALF, False, box)
        assert cut and len(runs) == 2
        y = -math.sqrt(100 - 4)
        assert runs[0]["points"][0] == (0.0, 0.0) and runs[0]["points"][1] == pytest.approx((8.0, y))
        assert runs[1]["points"][0] == pytest.approx((12.0, y)) and runs[1]["points"][1] == (20.0, 0.0)

    def test_every_piece_stays_on_the_arc_it_came_from(self):
        runs, _ = g.bulged_outside(*self.HALF, False, (8, -12, 12, -8))
        for seg in (s for run in runs for s in rebuilt(run)):
            assert seg.centre == pytest.approx((10.0, 0.0)) and seg.radius == pytest.approx(10.0)
            assert seg.bulge > 0  # still anticlockwise

    def test_the_length_left_is_the_arc_less_the_part_in_the_box(self):
        runs, _ = g.bulged_outside(*self.HALF, False, (8, -12, 12, -8))
        inside = 10 * 2 * math.asin(2 / 10)
        assert length(runs) == pytest.approx(math.pi * 10 - inside)

    def test_a_clockwise_arc_keeps_its_sign(self):
        runs, _ = g.bulged_outside([(20, 0), (0, 0)], [-1.0], False, (8, -12, 12, -8))
        assert len(runs) == 2 and all(s.bulge < 0 for run in runs for s in rebuilt(run))
        assert all(s.centre == pytest.approx((10.0, 0.0)) for run in runs for s in rebuilt(run))

    def test_an_arc_that_only_touches_the_box_is_left_whole(self):
        runs, cut = g.bulged_outside(*self.HALF, False, (5, -15, 15, -10))
        assert not cut and len(runs) == 1 and runs[0]["bulges"] == [1.0]

    def test_an_arc_wholly_inside_the_box_goes(self):
        runs, cut = g.bulged_outside([(0, 0), (10, 0), (20, 0)], [0, 1.0], False, (9, -12, 21, 1))
        assert cut and runs == [{"points": [(0.0, 0.0), (9.0, 0.0)], "bulges": [0.0]}]

    def test_a_box_over_a_whole_bend_and_its_straights(self):
        runs, cut = g.bulged_outside(*self.HALF, False, (-1, -11, 21, 1))
        assert cut and runs == []

    def test_a_bend_cut_in_the_middle_of_a_route(self):
        # Straight in, a quarter bend, straight out; the box sits on the bend.
        quarter = math.tan(math.radians(90) / 4)
        verts = [(0, 0), (100, 0), (150, 50), (150, 150)]
        runs, cut = g.bulged_outside(verts, [0, quarter, 0], False, (130, 0, 160, 30))
        assert cut and len(runs) == 2
        assert runs[0]["points"][0] == (0.0, 0.0) and runs[1]["points"][-1] == (150.0, 150.0)
        bend = [s for run in runs for s in rebuilt(run) if s.centre]
        assert len(bend) == 2 and all(s.centre == pytest.approx((100.0, 50.0)) for s in bend)
        assert all(s.radius == pytest.approx(50.0) for s in bend)


class TestClosed:
    def test_a_loop_cut_once_is_one_open_run(self):
        square = [(0, 0), (100, 0), (100, 100), (0, 100)]
        runs, cut = g.bulged_outside(square, [0, 0, 0, 0], True, (40, 90, 60, 110))
        assert cut and len(runs) == 1
        assert runs[0]["points"] == [(40.0, 100.0), (0.0, 100.0), (0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (60.0, 100.0)]
        assert len(runs[0]["bulges"]) == 5

    def test_a_round_loop_keeps_its_arcs(self):
        # A closed polyline circle: two half rounds about (0, 0), radius 10. The box sits on its start.
        runs, cut = g.bulged_outside([(10, 0), (-10, 0)], [1.0, 1.0], True, (8, -2, 12, 2))
        assert cut and len(runs) == 1
        segs = rebuilt(runs[0])
        assert len(segs) == 2 and all(s.centre == pytest.approx((0.0, 0.0)) for s in segs)
        assert runs[0]["points"][0] == pytest.approx((math.sqrt(96), 2.0))
        assert runs[0]["points"][-1] == pytest.approx((math.sqrt(96), -2.0))


# ---------------------------------------------------------------------------
# The tool, against a fake drawing
# ---------------------------------------------------------------------------


class Polyline:
    ObjectName = "AcDbPolyline"

    def __init__(self, handle, vertices, bulges, closed=False):
        self.Handle = handle
        self.Coordinates = [c for v in vertices for c in v]
        self.bulges = list(bulges) + [0.0] * (len(vertices) - len(bulges))
        self.Closed = closed
        self.copies = []
        self.deleted = False

    def GetBulge(self, i):
        return self.bulges[i]

    def SetBulge(self, i, b):
        while len(self.bulges) <= i:
            self.bulges.append(0.0)
        self.bulges[i] = b

    def GetBoundingBox(self):
        xs, ys = self.Coordinates[0::2], self.Coordinates[1::2]
        return (min(xs) - 10, min(ys) - 10, 0), (max(xs) + 10, max(ys) + 10, 0)

    def Copy(self):
        twin = Polyline(f"{self.Handle}C{len(self.copies)}", [(0, 0), (1, 1)], [])
        self.copies.append(twin)
        return twin

    def Delete(self):
        self.deleted = True

    def __setattr__(self, name, value):
        if name == "Coordinates" and hasattr(value, "value"):
            value = list(value.value)
        object.__setattr__(self, name, value)


class Block:
    def __init__(self, lo, hi):
        self.box = (lo, hi)

    def GetBoundingBox(self):
        return self.box


def test_the_tool_cuts_a_bend_and_writes_each_piece_s_bulges(monkeypatch):
    quarter = math.tan(math.radians(90) / 4)
    pipe = Polyline("P1", [(0, 0), (100, 0), (150, 50), (150, 150)], [0, quarter, 0])
    valve = Block((130, 0, 0), (160, 30, 0))

    async def run(fn):
        return fn()

    monkeypatch.setattr(geometry_tools, "run", run)
    monkeypatch.setattr(geometry_tools, "get_doc", lambda: object())
    monkeypatch.setattr(geometry_tools, "require_idle", lambda d: None)
    monkeypatch.setattr(geometry_tools, "resolve_handles", lambda doc, handles: [valve])
    monkeypatch.setattr(geometry_tools, "select_filtered", lambda doc, entity_type, layer: entity_type)
    monkeypatch.setattr(geometry_tools, "iter_selection", lambda kind: [pipe] if kind == "lwpolyline" else [])
    monkeypatch.setattr(geometry_tools, "discard_selection_set", lambda doc: None)

    class Mark:
        def __init__(self, doc):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(geometry_tools, "undo_mark", Mark)
    out = json.loads(asyncio.run(geometry_tools.autocad_break_at_blocks(block_handles=["B1"])))
    assert out["broken"] == 1 and out["skipped"] == [] and out["new_handles"] == ["P1C0"]
    first, second = pipe, pipe.copies[0]
    # Straight in, then the bend as far as the box; the rest of the bend, then straight out.
    assert first.Coordinates[:4] == [0.0, 0.0, 100.0, 0.0]
    assert first.bulges[0] == 0.0 and first.bulges[1] > 0 and first.bulges[2] == 0.0
    assert second.Coordinates[-2:] == [150.0, 150.0]
    assert second.bulges[0] > 0 and second.bulges[1] == 0.0
    # Both halves of the bend are still on the bend: centre (100, 50), radius 50.
    for piece in (first, second):
        points = list(zip(piece.Coordinates[0::2], piece.Coordinates[1::2], strict=True))
        bend = [s for s in g.segments(points, piece.bulges, False) if s.centre]
        assert len(bend) == 1
        assert bend[0].centre == pytest.approx((100.0, 50.0)) and bend[0].radius == pytest.approx(50.0)


def test_a_line_with_no_block_on_it_is_left_alone():
    runs, cut = g.bulged_outside([(0, 0), (20, 0)], [1.0], False, (100, 100, 110, 110))
    assert not cut and runs[0]["bulges"] == [1.0]
