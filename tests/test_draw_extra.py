"""The smaller draw gaps (issue #119 part 1, D-108): construction line and ray,
region, donut, divide / measure.

The maths first (plain functions, no AutoCAD), then each tool against fake COM
objects: that it calls the right COM method with the right points, writes the
right shape, puts what it makes in the run's own space, opens one undo step,
and refuses plainly before it touches the drawing. No AutoCAD: the live rows
are NEEDS-CHECKING group AP, NOT RUN.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import draw_extra as dx


def flat(value):
    return tuple(float(c) for c in getattr(value, "value", value))


def close(a, b, tol=1e-6):
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


# ---- the maths ---------------------------------------------------------------

class TestConstructionPoints:
    def test_angle_gives_a_unit_direction(self):
        geo = dx.construction_points([100, 200], angle=90)
        assert close(geo["base"], [100, 200, 0])
        assert close(geo["direction"], [0, 1, 0])
        assert close(geo["second"], [100, 201, 0])
        assert geo["angle"] == pytest.approx(90)

    def test_through_point(self):
        geo = dx.construction_points([0, 0], through=[300, 400])
        assert close(geo["direction"], [0.6, 0.8, 0])
        assert geo["angle"] == pytest.approx(math.degrees(math.atan2(4, 3)))

    def test_through_keeps_the_base_height_when_flat(self):
        geo = dx.construction_points([0, 0, 50], through=[10, 0])
        assert close(geo["second"], [1, 0, 50])

    def test_negative_angle_reads_back_in_0_to_360(self):
        assert dx.construction_points([0, 0], angle=-45)["angle"] == pytest.approx(315)

    @pytest.mark.parametrize("kwargs", [{}, {"through": [1, 1], "angle": 0}])
    def test_one_of_through_or_angle(self, kwargs):
        with pytest.raises(ValueError, match="not both"):
            dx.construction_points([0, 0], **kwargs)

    def test_same_point_twice_is_refused(self):
        with pytest.raises(ValueError, match="same point"):
            dx.construction_points([5, 5], through=[5, 5])

    def test_short_base_is_refused(self):
        with pytest.raises(ValueError, match="at least"):
            dx.construction_points([5], angle=0)


class TestDonutShape:
    def test_ring(self):
        s = dx.donut_shape(100, 150)
        # The line runs midway: inside edge r - w/2 = 50, outside r + w/2 = 75.
        assert s["radius"] == pytest.approx(62.5)
        assert s["width"] == pytest.approx(25)
        assert s["radius"] - s["width"] / 2 == pytest.approx(50)
        assert s["radius"] + s["width"] / 2 == pytest.approx(75)

    def test_filled_dot(self):
        s = dx.donut_shape(0, 3)
        assert s["radius"] == pytest.approx(0.75)
        assert s["width"] == pytest.approx(1.5)
        assert s["radius"] - s["width"] / 2 == pytest.approx(0)

    @pytest.mark.parametrize("inside, outside", [(10, 10), (20, 10), (-1, 10), (0, 0)])
    def test_bad_sizes(self, inside, outside):
        with pytest.raises(ValueError):
            dx.donut_shape(inside, outside)

    def test_vertices_either_side_of_the_centre(self):
        assert dx.donut_vertices([10, 20], 5) == [5, 20, 15, 20]


class TestDivideAndMeasure:
    def test_divide_open_leaves_the_ends_free(self):
        assert dx.divide_distances(1000, 4, closed=False) == pytest.approx([250, 500, 750])

    def test_divide_closed_starts_on_the_start(self):
        assert dx.divide_distances(1200, 3, closed=True) == pytest.approx([0, 400, 800])

    def test_divide_needs_two_parts(self):
        with pytest.raises(ValueError):
            dx.divide_distances(100, 1, closed=False)

    def test_measure_leaves_the_rest_at_the_end(self):
        assert dx.measure_distances(1000, 300) == pytest.approx([300, 600, 900])

    def test_measure_puts_no_mark_on_the_end(self):
        assert dx.measure_distances(1000, 250) == pytest.approx([250, 500, 750])

    def test_measure_end_tolerance_does_not_grow_with_length(self):
        # 0.9 short of the end on a 1 km run is a real mark, not "on the end".
        marks = dx.measure_distances(1_000_000.9, 1000)
        assert marks[-1] == pytest.approx(1_000_000)
        plan = dx.marks_along({"vertices": [(0, 0), (1_000_000.9, 0)], "bulges": [0.0], "closed": False},
                              interval=1000)
        assert plan["left_at_end"] == pytest.approx(0.9)

    @pytest.mark.parametrize("interval", [0.1, 1e-310])
    def test_too_many_marks_refused_before_any_work(self, interval):
        with pytest.raises(ValueError, match="at most"):
            dx.measure_distances(1_000_000, interval)

    def test_zero_length_segment_does_not_turn_the_block(self):
        path = {"vertices": [(0, 0), (0, 0), (0, 100), (100, 100), (100, 0)], "bulges": [0.0] * 5,
                "closed": True}
        plan = dx.marks_along(path, segments=4)
        assert plan["marks"][0]["position"] == [0, 0]
        assert plan["marks"][0]["direction"] == pytest.approx(90)

    def test_measure_longer_than_the_run(self):
        assert dx.measure_distances(100, 300) == []

    def test_zero_length_run(self):
        with pytest.raises(ValueError, match="no length"):
            dx.measure_distances(0, 10)

    def line(self, length=1000):
        return {"vertices": [(0, 0), (length, 0)], "bulges": [0.0], "closed": False}

    def test_marks_on_a_line(self):
        plan = dx.marks_along(self.line(), interval=300)
        assert [m["position"] for m in plan["marks"]] == [[300, 0], [600, 0], [900, 0]]
        assert plan["left_at_end"] == pytest.approx(100)
        assert plan["step"] == 300
        assert all(m["direction"] == pytest.approx(0) for m in plan["marks"])

    def test_exact_measure_has_nothing_left(self):
        assert dx.marks_along(self.line(), interval=250)["left_at_end"] == 0

    def test_from_end_counts_back(self):
        plan = dx.marks_along(self.line(), interval=300, from_end=True)
        assert [m["position"][0] for m in plan["marks"]] == pytest.approx([700, 400, 100])
        # The run's own direction, not reversed: AutoCAD turns a block to the object.
        assert all(m["direction"] == pytest.approx(0) for m in plan["marks"])

    def test_divide_a_circle_from_0_degrees_anticlockwise(self):
        r = 100.0
        circle = {"vertices": [(r, 0), (-r, 0)], "bulges": [1.0, 1.0], "closed": True}
        plan = dx.marks_along(circle, segments=4)
        got = [tuple(round(c, 6) for c in m["position"]) for m in plan["marks"]]
        assert got == [(100, 0), (0, 100), (-100, 0), (0, -100)]
        # Tangent at 0 degrees, going anticlockwise, points up.
        assert plan["marks"][0]["direction"] == pytest.approx(90)
        assert plan["total"] == pytest.approx(2 * math.pi * r)

    def test_divide_an_l_shaped_polyline(self):
        path = {"vertices": [(0, 0), (600, 0), (600, 600)], "bulges": [0.0, 0.0], "closed": False}
        plan = dx.marks_along(path, segments=3)
        assert [m["position"] for m in plan["marks"]] == [[400, 0], [600, 200]]
        assert plan["marks"][1]["direction"] == pytest.approx(90)

    def test_one_of_segments_or_interval(self):
        with pytest.raises(ValueError, match="not both"):
            dx.marks_along(self.line(), segments=2, interval=100)


def test_all_four_are_change_tools():
    for name in ("autocad_add_construction_line", "autocad_add_region", "autocad_add_donut",
                 "autocad_divide_curve"):
        assert risk_of(name) is Risk.CHANGE


# ---- fake COM ------------------------------------------------------------------

class Doc:
    def __init__(self):
        self.objects: dict[str, object] = {}
        self.counter = 0x200
        self.undo_marks = 0
        self.variables = {"FILLMODE": 1, "PDMODE": 3, "CMDACTIVE": 0}
        self.ModelSpace = Space(self, "model")
        self.PaperSpace = Space(self, "paper")
        self.Blocks = Blocks({"SUPPORT"})
        self.Layers = Layers()

    def handle(self):
        self.counter += 1
        return f"{self.counter:X}"

    def HandleToObject(self, h):
        try:
            return self.objects[str(h)]
        except KeyError:
            raise KeyError(f"no object {h}") from None

    def ObjectIdToObject(self, owner):
        return self.PaperSpace if owner == "paper" else self.ModelSpace

    def StartUndoMark(self):
        self.undo_marks += 1

    def EndUndoMark(self):
        pass

    def GetVariable(self, name):
        return self.variables[name]


class Blocks:
    def __init__(self, names):
        self.names = names

    def Item(self, name):
        if name not in self.names:
            raise KeyError(name)
        return name


class Layer:
    def __init__(self, name, locked=False):
        self.Name, self.Lock = name, locked


class Layers:
    def __init__(self):
        self.names = {"0"}
        self.locked: set[str] = set()

    def Item(self, name):
        if name not in self.names:
            raise KeyError(name)
        return Layer(name, name in self.locked)

    def Add(self, name):
        self.names.add(name)
        return name


class Ent:
    ObjectName = "AcDbEntity"

    def __init__(self, doc, owner="model"):
        self.doc = self.Document = doc
        self.Handle = doc.handle()
        doc.objects[self.Handle] = self
        self.Layer, self.Color, self.Linetype = "0", 256, "ByLayer"
        self.OwnerID = owner
        self.Normal = (0.0, 0.0, 1.0)
        self.deleted = False

    def Delete(self):
        self.deleted = True
        del self.doc.objects[self.Handle]


class Xline(Ent):
    ObjectName = "AcDbXline"

    def __init__(self, doc, p1, p2, owner):
        super().__init__(doc, owner)
        self.BasePoint, self.SecondPoint = flat(p1), flat(p2)


class Ray(Xline):
    ObjectName = "AcDbRay"


class Region(Ent):
    ObjectName = "AcDbRegion"

    def __init__(self, doc, owner, area, perimeter, centroid):
        super().__init__(doc, owner)
        self.Area, self.Perimeter, self.Centroid = area, perimeter, centroid


class Polyline(Ent):
    ObjectName = "AcDbPolyline"

    def __init__(self, doc, coords, owner, closed=False, elevation=0.0):
        super().__init__(doc, owner)
        self.Coordinates = flat(coords)
        self.bulges: dict[int, float] = {}
        self.Closed = closed
        self.ConstantWidth = 0.0
        self.Elevation = elevation

    def SetBulge(self, i, b):
        self.bulges[i] = b

    def GetBulge(self, i):
        return self.bulges.get(i, 0.0)


class Line(Ent):
    ObjectName = "AcDbLine"

    def __init__(self, doc, s, e, owner="model"):
        super().__init__(doc, owner)
        self.StartPoint, self.EndPoint = s, e


class Circle(Ent):
    ObjectName = "AcDbCircle"

    def __init__(self, doc, c, r, owner="model"):
        super().__init__(doc, owner)
        self.Center, self.Radius = c, r


class Text(Ent):
    ObjectName = "AcDbText"


class Point(Ent):
    ObjectName = "AcDbPoint"

    def __init__(self, doc, at, owner):
        super().__init__(doc, owner)
        self.Coordinates = flat(at)


class Insert(Ent):
    ObjectName = "AcDbBlockReference"

    def __init__(self, doc, at, name, sx, rot, owner):
        super().__init__(doc, owner)
        self.InsertionPoint, self.Name, self.XScaleFactor, self.Rotation = flat(at), name, sx, rot


class Space:
    def __init__(self, doc, name):
        self.doc, self.name = doc, name
        self.region_calls: list[list[str]] = []
        self.region_answer = None  # None: one region per given outline

    def AddXline(self, p1, p2):
        return Xline(self.doc, p1, p2, self.name)

    def AddRay(self, p1, p2):
        return Ray(self.doc, p1, p2, self.name)

    def AddRegion(self, objects):
        given = list(getattr(objects, "value", objects))
        self.region_calls.append([o.Handle for o in given])
        if isinstance(self.region_answer, Exception):
            raise self.region_answer
        if self.region_answer == "none":
            return ()
        return tuple(Region(self.doc, self.name, 5000.0, 300.0, (50.0, 25.0)) for _ in given)

    def AddLightWeightPolyline(self, coords):
        return Polyline(self.doc, coords, self.name)

    def AddPoint(self, at):
        return Point(self.doc, at, self.name)

    def InsertBlock(self, at, name, sx, sy, sz, rot):
        return Insert(self.doc, at, name, sx, rot, self.name)


@pytest.fixture
def doc(monkeypatch):
    fake = Doc()

    async def now(fn):
        return fn()

    monkeypatch.setattr(dx, "run", now)
    monkeypatch.setattr(dx, "get_doc", lambda: fake)
    monkeypatch.setattr(dx, "require_idle", lambda d: None)
    return fake


def answer(coro) -> dict:
    text = asyncio.run(coro)
    assert not text.startswith("Error"), text
    return json.loads(text)


def refusal(coro) -> str:
    text = asyncio.run(coro)
    assert text.startswith("Error"), text
    return text


def made(doc, kind):
    return [o for o in doc.objects.values() if isinstance(o, kind)]


# ---- construction line and ray -------------------------------------------------

class TestConstructionLineTool:
    def test_vertical_xline(self, doc):
        out = answer(dx.autocad_add_construction_line(base=[4500, 2200], angle=90, layer="A-SETOUT"))
        x = doc.objects[out["handle"]]
        assert x.ObjectName == "AcDbXline"
        assert close(x.BasePoint, (4500, 2200, 0)) and close(x.SecondPoint, (4500, 2201, 0))
        assert out["type"] == "xline" and out["verified"] is True
        assert x.Layer == "A-SETOUT" and out["layer_created"] == "A-SETOUT"
        assert doc.undo_marks == 1

    def test_ray_through_a_point_in_paper_space(self, doc):
        out = answer(dx.autocad_add_construction_line(base=[0, 0], through=[0, -50], kind="ray", space="paper"))
        r = doc.objects[out["handle"]]
        assert r.ObjectName == "AcDbRay" and r.OwnerID == "paper"
        assert out["angle_degrees"] == pytest.approx(270)

    def test_neither_is_refused_before_autocad(self, doc):
        text = refusal(dx.autocad_add_construction_line(base=[0, 0]))
        assert "through" in text
        assert doc.objects == {} and doc.undo_marks == 0


# ---- region ----------------------------------------------------------------------

class TestRegionTool:
    def outline(self, doc, owner="model"):
        return Polyline(doc, (0, 0, 100, 0, 100, 50, 0, 50), owner, closed=True)

    def test_one_closed_outline(self, doc):
        pl = self.outline(doc)
        out = answer(dx.autocad_add_region(handles=[pl.Handle]))
        assert out["created"] == 1 and out["verified"] is True
        row = out["regions"][0]
        assert row["area"] == 5000 and row["perimeter"] == 300 and row["centroid"] == [50, 25]
        assert doc.ModelSpace.region_calls == [[pl.Handle]]
        assert out["outlines_kept"] == [pl.Handle] and not pl.deleted
        assert doc.undo_marks == 1

    def test_erase_outlines(self, doc):
        pl = self.outline(doc)
        out = answer(dx.autocad_add_region(handles=[pl.Handle], erase_outlines=True))
        assert out["erased_outlines"] == [pl.Handle] and pl.deleted

    def test_goes_in_the_outlines_own_layout(self, doc):
        pl = self.outline(doc, owner="paper")
        answer(dx.autocad_add_region(handles=[pl.Handle]))
        assert doc.PaperSpace.region_calls and not doc.ModelSpace.region_calls

    def test_text_is_refused(self, doc):
        t = Text(doc)
        text = refusal(dx.autocad_add_region(handles=[t.Handle]))
        assert "AcDbText" in text or "text" in text
        assert doc.ModelSpace.region_calls == []

    def test_mixed_spaces_are_refused(self, doc):
        a, b = self.outline(doc), self.outline(doc, owner="paper")
        assert "same space" in refusal(dx.autocad_add_region(handles=[a.Handle, b.Handle]))

    def test_autocad_refusal_is_said_plainly(self, doc):
        pl = self.outline(doc)
        doc.ModelSpace.region_answer = RuntimeError("Invalid input")
        text = refusal(dx.autocad_add_region(handles=[pl.Handle], erase_outlines=True))
        assert "no region" in text and "Invalid input" in text
        assert not pl.deleted

    def test_no_loop_is_refused_and_nothing_erased(self, doc):
        pl = self.outline(doc)
        doc.ModelSpace.region_answer = "none"
        assert "close a loop" in refusal(dx.autocad_add_region(handles=[pl.Handle], erase_outlines=True))
        assert not pl.deleted

    def test_same_handle_twice(self, doc):
        pl = self.outline(doc)
        assert "twice" in refusal(dx.autocad_add_region(handles=[pl.Handle, pl.Handle]))
        assert "twice" in refusal(dx.autocad_add_region(handles=[pl.Handle, f"{pl.Handle} ".lower()]))
        assert doc.ModelSpace.region_calls == []

    def test_locked_outline_with_erase_is_refused_before_anything_is_made(self, doc):
        a, b = self.outline(doc), self.outline(doc)
        b.Layer = "M-LOCKED"
        doc.Layers.names.add("M-LOCKED")
        doc.Layers.locked.add("M-LOCKED")
        assert "locked" in refusal(dx.autocad_add_region(handles=[a.Handle, b.Handle], erase_outlines=True))
        assert doc.ModelSpace.region_calls == [] and not a.deleted and not made(doc, Region)
        # Kept outlines on a locked layer are fine: nothing is erased.
        assert answer(dx.autocad_add_region(handles=[b.Handle]))["created"] == 1


# ---- donut -------------------------------------------------------------------------

class TestDonutTool:
    def test_two_rings(self, doc):
        out = answer(dx.autocad_add_donut(centers=[[0, 0], [1000, 0, 300]], outside_diameter=150,
                                          inside_diameter=100))
        assert out["created"] == 2 and out["verified"] is True
        a, b = (doc.objects[h] for h in out["handles"])
        assert close(a.Coordinates, (-62.5, 0, 62.5, 0))
        assert a.bulges == {0: 1.0, 1: 1.0} and a.Closed is True
        assert a.ConstantWidth == pytest.approx(25)
        assert b.Elevation == 300 and a.Elevation == 0
        assert doc.undo_marks == 1  # both in one undo step
        assert "note" not in out

    def test_filled_dot_and_fillmode_note(self, doc):
        doc.variables["FILLMODE"] = 0
        out = answer(dx.autocad_add_donut(centers=[[5, 5]], outside_diameter=3))
        pl = doc.objects[out["handle"]]
        assert pl.ConstantWidth == pytest.approx(1.5)
        assert "FILLMODE" in out["note"]

    def test_inside_not_smaller_is_refused(self, doc):
        assert "smaller" in refusal(dx.autocad_add_donut(centers=[[0, 0]], outside_diameter=10,
                                                          inside_diameter=10))
        assert doc.objects == {}

    def test_short_centre_is_refused(self, doc):
        assert "Centre 2" in refusal(dx.autocad_add_donut(centers=[[0, 0], [1]], outside_diameter=10))
        assert doc.objects == {}


# ---- divide / measure ----------------------------------------------------------------

class TestDivideTool:
    def test_divide_a_line_with_points(self, doc):
        ln = Line(doc, (0, 0, 0), (1000, 0, 0))
        out = answer(dx.autocad_divide_curve(path_handle=ln.Handle, segments=4))
        pts = [doc.objects[h] for h in out["handles"]]
        assert [p.Coordinates for p in pts] == [(250, 0, 0), (500, 0, 0), (750, 0, 0)]
        assert out["kind"] == "points" and out["placed"] == 3 and out["step"] == 250
        assert doc.undo_marks == 1
        assert "note" not in out  # PDMODE 3 shows them

    def test_points_note_when_they_will_not_show(self, doc):
        doc.variables["PDMODE"] = 0
        ln = Line(doc, (0, 0, 0), (1000, 0, 0))
        out = answer(dx.autocad_divide_curve(path_handle=ln.Handle, segments=2))
        assert "point_style" in out["note"]

    def test_measure_a_polyline_with_an_aligned_block(self, doc):
        pl = Polyline(doc, (0, 0, 600, 0, 600, 600), "model", elevation=2700)
        out = answer(dx.autocad_divide_curve(path_handle=pl.Handle, interval=500, block_name="SUPPORT",
                                             layer="M-SUPPORT"))
        ins = [doc.objects[h] for h in out["handles"]]
        assert [i.InsertionPoint for i in ins] == [(500, 0, 2700), (600, 400, 2700)]
        assert [round(math.degrees(i.Rotation), 6) for i in ins] == [0, 90]
        assert all(i.Name == "SUPPORT" and i.Layer == "M-SUPPORT" for i in ins)
        assert out["left_at_end"] == pytest.approx(200)
        assert out["kind"] == "block"

    def test_block_not_aligned_takes_only_the_extra_rotation(self, doc):
        ln = Line(doc, (0, 0, 0), (0, 1000, 0))
        out = answer(dx.autocad_divide_curve(path_handle=ln.Handle, segments=2, block_name="SUPPORT",
                                             align=False, rotation=45))
        assert math.degrees(doc.objects[out["handles"][0]].Rotation) == pytest.approx(45)

    def test_marks_go_in_the_runs_own_layout(self, doc):
        c = Circle(doc, (0, 0, 0), 100.0, owner="paper")
        out = answer(dx.autocad_divide_curve(path_handle=c.Handle, segments=4))
        assert out["placed"] == 4 and out["closed"] is True
        assert all(doc.objects[h].OwnerID == "paper" for h in out["handles"])

    def test_unknown_block_is_refused_first(self, doc):
        ln = Line(doc, (0, 0, 0), (1000, 0, 0))
        assert "No block named 'VALVE'" in refusal(
            dx.autocad_divide_curve(path_handle=ln.Handle, segments=2, block_name="VALVE"))
        assert doc.undo_marks == 0

    def test_sloping_line_is_refused(self, doc):
        ln = Line(doc, (0, 0, 0), (1000, 0, 200))
        assert "slopes" in refusal(dx.autocad_divide_curve(path_handle=ln.Handle, segments=2))
        assert doc.undo_marks == 0

    def test_tilted_run_is_refused(self, doc):
        c = Circle(doc, (0, 0, 0), 100.0)
        c.Normal = (1.0, 0.0, 0.0)
        assert "not flat" in refusal(dx.autocad_divide_curve(path_handle=c.Handle, segments=3))

    def test_interval_longer_than_the_run(self, doc):
        ln = Line(doc, (0, 0, 0), (100, 0, 0))
        assert "no mark fits" in refusal(dx.autocad_divide_curve(path_handle=ln.Handle, interval=300))
        assert doc.undo_marks == 0

    def test_too_many_marks(self, doc):
        ln = Line(doc, (0, 0, 0), (1_000_000, 0, 0))
        assert "at most" in refusal(dx.autocad_divide_curve(path_handle=ln.Handle, interval=1))
        assert doc.undo_marks == 0

    def test_bad_layer_name_refused_before_anything_is_drawn(self, doc):
        ln = Line(doc, (0, 0, 0), (1000, 0, 0))
        before = set(doc.objects)
        assert "does not allow" in refusal(dx.autocad_divide_curve(path_handle=ln.Handle, segments=4,
                                                                  layer="P;MARKS"))
        assert "does not allow" in refusal(dx.autocad_add_donut(centers=[[0, 0]], outside_diameter=3,
                                                               layer="E|DOTS"))
        assert "does not allow" in refusal(dx.autocad_add_region(handles=[ln.Handle], layer="A/B"))
        assert "does not allow" in refusal(dx.autocad_add_construction_line(base=[0, 0], angle=0,
                                                                           layer="A:B"))
        assert set(doc.objects) == before and doc.undo_marks == 0

    def test_both_or_neither(self, doc):
        ln = Line(doc, (0, 0, 0), (100, 0, 0))
        assert "not both" in refusal(dx.autocad_divide_curve(path_handle=ln.Handle))
        assert "not both" in refusal(dx.autocad_divide_curve(path_handle=ln.Handle, segments=2, interval=10))

    def test_text_is_not_a_run(self, doc):
        t = Text(doc)
        assert "line, polyline, arc or circle" in refusal(dx.autocad_divide_curve(path_handle=t.Handle, segments=2))
