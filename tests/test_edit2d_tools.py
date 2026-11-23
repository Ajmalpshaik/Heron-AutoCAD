"""The 2D edit tools against fake COM objects (issues #103, #49, #105, #111, #110, #154; D-78, D-79, D-144).

The geometry itself is checked in test_edit2d_geometry.py. Here: that each tool
reads the right objects, writes the shape back through the object's own
properties, makes copies for extra pieces, erases only what it should, opens one
undo step (none when it does nothing), and says plainly what it refused.
No AutoCAD.
"""

from __future__ import annotations

import asyncio
import copy
import json
import math

import pytest

from autocad_mcp.acad import props
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import edit2d, modify


def flat(value):
    return tuple(getattr(value, "value", value))


def pt3(value):
    v = flat(value)
    return (float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0)


class Doc:
    def __init__(self):
        self.objects: dict[str, object] = {}
        self.groups = 0
        self.counter = 0x100
        self.space = Space(self)
        self.Groups = Groups(self)
        self.regens = 0

    def handle(self):
        self.counter += 1
        return f"{self.counter:X}"

    def HandleToObject(self, h):
        try:
            return self.objects[str(h)]
        except KeyError:
            raise KeyError(f"no object {h}") from None

    def ObjectIdToObject(self, _id):
        return self.space

    def StartUndoMark(self):
        self.groups += 1

    def EndUndoMark(self):
        pass

    def GetVariable(self, name):
        return 0

    def Regen(self, which):
        self.regens += 1


class Ent:
    ObjectName = "AcDbEntity"

    def __init__(self, doc, layer="0"):
        self.doc = doc
        self.Handle = doc.handle()
        doc.objects[self.Handle] = self
        self.Layer, self.Color, self.Linetype = layer, 256, "ByLayer"
        self.LinetypeScale, self.Lineweight, self.EntityTransparency = 1.0, -1, "ByLayer"
        self.OwnerID = 1
        self.Normal = (0.0, 0.0, 1.0)
        self.moved = None

    def Delete(self):
        del self.doc.objects[self.Handle]

    def Copy(self):
        twin = copy.copy(self)
        twin.Handle = self.doc.handle()
        self.doc.objects[twin.Handle] = twin
        return twin

    def Move(self, a, b):
        self.moved = (pt3(a), pt3(b))

    def Update(self):
        pass


class Line(Ent):
    ObjectName = "AcDbLine"

    def __init__(self, doc, s, e, **kw):
        super().__init__(doc, **kw)
        self.StartPoint, self.EndPoint = s, e

    @property
    def StartPoint(self):
        return self._s

    @StartPoint.setter
    def StartPoint(self, v):
        self._s = pt3(v)

    @property
    def EndPoint(self):
        return self._e

    @EndPoint.setter
    def EndPoint(self, v):
        self._e = pt3(v)


class Arc(Ent):
    ObjectName = "AcDbArc"

    def __init__(self, doc, c, r, a0, a1, **kw):
        super().__init__(doc, **kw)
        self.Center, self.Radius, self.StartAngle, self.EndAngle = pt3(c), float(r), float(a0), float(a1)

    def _at(self, a):
        return (self.Center[0] + self.Radius * math.cos(a), self.Center[1] + self.Radius * math.sin(a), self.Center[2])

    @property
    def StartPoint(self):
        return self._at(self.StartAngle)

    @property
    def EndPoint(self):
        return self._at(self.EndAngle)


class Circle(Ent):
    ObjectName = "AcDbCircle"

    def __init__(self, doc, c, r, **kw):
        super().__init__(doc, **kw)
        self.Center, self.Radius = pt3(c), float(r)


class Poly(Ent):
    ObjectName = "AcDbPolyline"

    def __init__(self, doc, pts, bulges=None, closed=False, width=0.0, **kw):
        super().__init__(doc, **kw)
        self._coords = tuple(c for p in pts for c in p)
        n = len(pts)
        self.bulges = list(bulges or []) + [0.0] * n
        self.bulges = self.bulges[:n]
        self.Closed = closed
        self.ConstantWidth = width
        self.Elevation = 0.0
        self.widths = None

    @property
    def Coordinates(self):
        return self._coords

    @Coordinates.setter
    def Coordinates(self, v):
        self._coords = tuple(float(c) for c in flat(v))
        n = len(self._coords) // 2
        self.bulges = (self.bulges + [0.0] * n)[:n]

    def GetBulge(self, i):
        return self.bulges[i]

    def SetBulge(self, i, b):
        self.bulges[i] = float(b)

    def GetWidth(self, i):
        if self.widths:
            return self.widths[i]
        return (self.ConstantWidth, self.ConstantWidth)

    def points(self):
        c = self._coords
        return [(round(c[i], 6), round(c[i + 1], 6)) for i in range(0, len(c), 2)]


class Hatch(Ent):
    ObjectName = "AcDbHatch"

    def __init__(self, doc, lo, hi, **kw):
        super().__init__(doc, **kw)
        self.box = (lo, hi)

    def GetBoundingBox(self):
        return self.box


class Text(Ent):
    ObjectName = "AcDbText"

    def __init__(self, doc, at, style="Standard", **kw):
        super().__init__(doc, **kw)
        self.InsertionPoint, self.StyleName, self.TextString = pt3(at), style, "NOTE"


class Attribute:
    def __init__(self, tag, value):
        self.TagString, self.TextString = tag, value


class Block(Ent):
    ObjectName = "AcDbBlockReference"

    def __init__(self, doc, attributes=None, **kw):
        super().__init__(doc, **kw)
        self.attributes = attributes or {}
        self.Name = "VALVE"
        self.InsertionPoint = (0.0, 0.0, 0.0)

    def GetAttributes(self):
        return [Attribute(k, v) for k, v in self.attributes.items()]

    def Explode(self):
        return [Line(self.doc, (0, 0, 0), (1, 0, 0)), Line(self.doc, (1, 0, 0), (1, 1, 0))]


class Sortents:
    def __init__(self):
        self.calls = []

    def MoveToTop(self, objs):
        self.calls.append(("top", [o.Handle for o in flat(objs)]))

    def MoveToBottom(self, objs):
        self.calls.append(("bottom", [o.Handle for o in flat(objs)]))

    def MoveAbove(self, objs, target):
        self.calls.append(("above", [o.Handle for o in flat(objs)], target.Handle))

    def MoveBelow(self, objs, target):
        self.calls.append(("below", [o.Handle for o in flat(objs)], target.Handle))


class XDict:
    def __init__(self):
        self.items = {}

    def GetObject(self, name):
        return self.items[name]

    def AddObject(self, name, kind):
        assert kind == "AcDbSortentsTable"
        self.items[name] = Sortents()
        return self.items[name]


class Space:
    def __init__(self, doc):
        self.doc = doc
        self.xdict = XDict()

    def AddArc(self, c, r, a0, a1):
        return Arc(self.doc, c, r, a0, a1)

    def AddLine(self, a, b):
        return Line(self.doc, a, b)

    def AddLightWeightPolyline(self, coords):
        c = flat(coords)
        return Poly(self.doc, [(c[i], c[i + 1]) for i in range(0, len(c), 2)])

    def GetExtensionDictionary(self):
        return self.xdict


class Group:
    def __init__(self, doc, name):
        self.doc, self.Name, self.items = doc, name, []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]

    def AppendItems(self, objs):
        self.items.extend(flat(objs))

    def RemoveItems(self, objs):
        gone = {o.Handle for o in flat(objs)}
        self.items = [o for o in self.items if o.Handle not in gone]

    def Delete(self):
        self.doc.Groups.groups.remove(self)


class Groups:
    def __init__(self, doc):
        self.doc, self.groups = doc, []

    @property
    def Count(self):
        return len(self.groups)

    def Item(self, i):
        return self.groups[i]

    def Add(self, name):
        group = Group(self.doc, name)
        self.groups.append(group)
        return group


@pytest.fixture
def doc(monkeypatch):
    fake = Doc()

    async def now(fn):
        return fn()

    for module in (edit2d, modify):
        monkeypatch.setattr(module, "run", now)
        monkeypatch.setattr(module, "get_doc", lambda: fake)
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    return fake


def answer(coro) -> dict:
    text = asyncio.run(coro)
    assert not text.startswith("Error"), text
    return json.loads(text)


def refusal(coro) -> str:
    text = asyncio.run(coro)
    assert text.startswith("Error"), text
    return text


def xy(p):
    return (round(p[0], 6), round(p[1], 6))


# ---- levels --------------------------------------------------------------------------------


def test_every_new_tool_has_its_level():
    for name in ("trim_extend", "fillet_chamfer", "break_curve", "join_curves", "edit_vertex", "stretch",
                 "explode", "draw_order", "match_properties", "group"):
        assert risk_of(f"autocad_{name}") is Risk.CHANGE
    assert risk_of("autocad_list_groups") is Risk.READ
    assert risk_of("autocad_lengthen") is Risk.CHANGE


# ---- trim and extend -------------------------------------------------------------------------


def test_trim_cuts_the_picked_end_back_to_the_wall(doc):
    pipe = Line(doc, (0, 0, 5), (100, 0, 5))
    wall = Line(doc, (40, -10, 5), (40, 10, 5))
    out = answer(edit2d.autocad_trim_extend("trim", [pipe.Handle], [wall.Handle], points=[[20, 0]]))
    assert out["done"] == 1 and out["objects"][0]["cut_away"] == pytest.approx(40)
    assert xy(pipe.StartPoint) == (40, 0) and xy(pipe.EndPoint) == (100, 0)
    assert pipe.StartPoint[2] == 5  # its height is kept
    assert doc.groups == 1


def test_trim_between_two_edges_leaves_the_object_and_one_copy(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0), layer="M-PIPE")
    a, b = Line(doc, (30, -1, 0), (30, 1, 0)), Line(doc, (70, -1, 0), (70, 1, 0))
    out = answer(edit2d.autocad_trim_extend("trim", [pipe.Handle], [a.Handle, b.Handle], points=[[50, 0]]))
    copy_handle = out["objects"][0]["new_handles"][0]
    twin = doc.objects[copy_handle]
    assert (xy(pipe.StartPoint), xy(pipe.EndPoint)) == ((0, 0), (30, 0))
    assert (xy(twin.StartPoint), xy(twin.EndPoint)) == ((70, 0), (100, 0))
    assert twin.Layer == "M-PIPE"


def test_trim_needs_a_point_per_object(doc):
    pipe, wall = Line(doc, (0, 0, 0), (100, 0, 0)), Line(doc, (40, -10, 0), (40, 10, 0))
    assert "points" in refusal(edit2d.autocad_trim_extend("trim", [pipe.Handle], [wall.Handle]))
    assert "one point per object" in refusal(
        edit2d.autocad_trim_extend("trim", [pipe.Handle], [wall.Handle], points=[[1, 0], [2, 0]])
    )


def test_an_object_that_crosses_no_edge_is_listed_and_nothing_opens(doc):
    pipe, wall = Line(doc, (0, 0, 0), (100, 0, 0)), Line(doc, (40, 5, 0), (40, 10, 0))
    out = answer(edit2d.autocad_trim_extend("trim", [pipe.Handle], [wall.Handle], points=[[20, 0]]))
    assert out["done"] == 0 and "does not cross" in out["failed"][0]["reason"]
    assert doc.groups == 0


def test_a_trimmed_circle_becomes_an_arc_with_its_look(doc):
    sleeve = Circle(doc, (0, 0, 0), 10, layer="P-SLEEVE")
    cut = Line(doc, (0, -20, 0), (0, 20, 0))
    out = answer(edit2d.autocad_trim_extend("trim", [sleeve.Handle], [cut.Handle], points=[[-10, 0]]))
    row = out["objects"][0]
    assert sleeve.Handle not in doc.objects
    arc = doc.objects[row["replaced_by"]]
    assert arc.Layer == "P-SLEEVE" and arc.Radius == pytest.approx(10)
    assert math.degrees(arc.StartAngle) == pytest.approx(270) and math.degrees(arc.EndAngle) == pytest.approx(90)


def test_extend_with_no_point_reaches_both_walls(doc):
    pipe = Line(doc, (20, 0, 0), (80, 0, 0))
    left, right = Line(doc, (0, -10, 0), (0, 10, 0)), Line(doc, (100, -10, 0), (100, 10, 0))
    out = answer(edit2d.autocad_trim_extend("extend", [pipe.Handle], [left.Handle, right.Handle]))
    assert out["objects"][0]["added"] == pytest.approx(40)
    assert sorted(out["objects"][0]["ends"]) == ["end", "start"]
    assert (xy(pipe.StartPoint), xy(pipe.EndPoint)) == ((0, 0), (100, 0))


def test_extend_with_a_point_does_only_that_end(doc):
    pipe = Line(doc, (20, 0, 0), (80, 0, 0))
    left, right = Line(doc, (0, -10, 0), (0, 10, 0)), Line(doc, (100, -10, 0), (100, 10, 0))
    answer(edit2d.autocad_trim_extend("extend", [pipe.Handle], [left.Handle, right.Handle], points=[[75, 1]]))
    assert (xy(pipe.StartPoint), xy(pipe.EndPoint)) == ((20, 0), (100, 0))


def test_extend_an_arc_round_to_a_line(doc):
    arc = Arc(doc, (0, 0, 0), 10, 0, math.pi / 2)
    floor = Line(doc, (-20, 0, 0), (-5, 0, 0))
    answer(edit2d.autocad_trim_extend("extend", [arc.Handle], [floor.Handle]))
    assert math.degrees(arc.EndAngle) == pytest.approx(180) and arc.StartAngle == pytest.approx(0)


def test_a_sloping_line_is_refused(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 50))
    wall = Line(doc, (40, -10, 0), (40, 10, 0))
    out = answer(edit2d.autocad_trim_extend("trim", [pipe.Handle], [wall.Handle], points=[[20, 0]]))
    assert "sloping" in out["failed"][0]["reason"]


def test_a_polyline_on_a_flipped_plane_is_refused(doc):
    run = Poly(doc, [(0, 0), (100, 0)])
    run.Normal = (0.0, 0.0, -1.0)
    wall = Line(doc, (40, -10, 0), (40, 10, 0))
    out = answer(edit2d.autocad_trim_extend("trim", [run.Handle], [wall.Handle], points=[[20, 0]]))
    assert "tilted or flipped" in out["failed"][0]["reason"]


def test_a_polyline_with_changing_widths_is_refused(doc):
    run = Poly(doc, [(0, 0), (100, 0), (100, 50)])
    run.widths = [(0.0, 5.0), (5.0, 5.0)]
    wall = Line(doc, (40, -10, 0), (40, 10, 0))
    out = answer(edit2d.autocad_trim_extend("trim", [run.Handle], [wall.Handle], points=[[20, 0]]))
    assert "width changes" in out["failed"][0]["reason"]


SERVER_FAULT = -2147417851  # RPC_E_SERVERFAULT: retryable, but not the busy refusal itself


class _FailingWidth(Poly):
    """A polyline whose width read fails the way a busy or stuck AutoCAD fails it."""

    fail_with: BaseException | None = None
    fail_on = "ConstantWidth"

    def __getattribute__(self, name):
        if name == type(self).fail_on and type(self).fail_with is not None:
            raise type(self).fail_with
        return super().__getattribute__(name)


@pytest.mark.parametrize("member", ["ConstantWidth", "GetWidth"])
def test_a_retryable_width_read_goes_up_not_as_width_changes(doc, member):
    # #212.3: a busy AutoCAD read as "width changes along it" was a false refusal.
    import pythoncom

    class Stuck(_FailingWidth):
        fail_with = pythoncom.com_error(SERVER_FAULT, "The server threw an exception.", None, None)
        fail_on = member

    run = Stuck(doc, [(0, 0), (100, 0)], width=4.0)
    with pytest.raises(pythoncom.com_error):
        edit2d._width(run)


def test_a_width_read_that_is_not_retryable_still_says_width_changes(doc):
    import pythoncom

    class NoWidth(_FailingWidth):
        fail_with = pythoncom.com_error(-2147024809, "The parameter is incorrect.", None, None)  # E_INVALIDARG

    run = NoWidth(doc, [(0, 0), (100, 0), (100, 50)])
    with pytest.raises(edit2d.AutocadError, match="width changes"):
        edit2d._width(run)


def test_a_polyline_keeps_its_one_width(doc):
    run = Poly(doc, [(0, 0), (100, 0)], width=4.0)
    wall = Line(doc, (40, -10, 0), (40, 10, 0))
    answer(edit2d.autocad_trim_extend("trim", [run.Handle], [wall.Handle], points=[[20, 0]]))
    assert run.points() == [(40, 0), (100, 0)] and run.ConstantWidth == 4.0


# ---- fillet and chamfer ------------------------------------------------------------------------


def test_fillet_two_lines_adds_an_arc_with_the_first_lines_look(doc):
    a = Line(doc, (100, 0, 0), (10, 0, 0), layer="M-DUCT")
    b = Line(doc, (0, 100, 0), (0, 10, 0))
    a.Lineweight = 35
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle], radius=20))
    arc = doc.objects[out["arc"]]
    assert xy(a.EndPoint) == (20, 0) and xy(b.EndPoint) == (0, 20)
    assert xy(arc.Center) == (20, 20) and arc.Radius == 20
    assert arc.Layer == "M-DUCT" and arc.Lineweight == 35
    assert doc.groups == 1


def test_fillet_radius_zero_makes_a_corner_and_no_arc(doc):
    a, b = Line(doc, (100, 0, 0), (10, 0, 0)), Line(doc, (0, 100, 0), (0, 10, 0))
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle], radius=0))
    assert out["arc"] is None and xy(a.EndPoint) == (0, 0) and xy(b.EndPoint) == (0, 0)


def test_chamfer_two_lines_adds_the_cut_line(doc):
    a, b = Line(doc, (100, 0, 0), (10, 0, 0)), Line(doc, (0, 100, 0), (0, 10, 0))
    out = answer(edit2d.autocad_fillet_chamfer("chamfer", [a.Handle, b.Handle], distance=10, distance2=20))
    cut = doc.objects[out["chamfer_line"]]
    assert (xy(cut.StartPoint), xy(cut.EndPoint)) == ((10, 0), (0, 20))
    assert xy(b.EndPoint) == (0, 20)


def test_fillet_every_corner_of_a_polyline(doc):
    plinth = Poly(doc, [(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [plinth.Handle], radius=10))
    assert out["corners_done"] == [0, 1, 2, 3] and out["vertex_count"] == 8
    assert plinth.points()[:2] == [(0, 10), (10, 0)] and plinth.Closed is True
    assert sum(1 for b in plinth.bulges if abs(b) > 0) == 4


def test_a_polyline_with_no_corner_it_can_do_changes_nothing(doc):
    thin = Poly(doc, [(0, 0), (100, 0), (100, 5), (0, 5)], closed=True)
    text = refusal(edit2d.autocad_fillet_chamfer("fillet", [thin.Handle], radius=10))
    assert "too short" in text and doc.groups == 0


def test_fillet_and_chamfer_options_are_checked_first(doc):
    a, b = Line(doc, (100, 0, 0), (10, 0, 0)), Line(doc, (0, 100, 0), (0, 10, 0))
    assert "needs 'radius'" in refusal(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle]))
    assert "needs 'distance'" in refusal(edit2d.autocad_fillet_chamfer("chamfer", [a.Handle, b.Handle]))
    assert "not both" in refusal(
        edit2d.autocad_fillet_chamfer("chamfer", [a.Handle, b.Handle], distance=5, distance2=5, angle=30)
    )


def test_a_circle_and_a_line_are_not_filleted(doc):
    a, c = Line(doc, (100, 0, 0), (10, 0, 0)), Circle(doc, (0, 0, 0), 5)
    assert "two lines" in refusal(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, c.Handle], radius=5))


# ---- break and join -------------------------------------------------------------------------------


def test_break_at_a_point_makes_a_copy_for_the_second_piece(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    out = answer(edit2d.autocad_break_curve(pipe.Handle, [40, 3]))
    twin = doc.objects[out["new_handles"][0]]
    assert xy(pipe.EndPoint) == (40, 0) and xy(twin.StartPoint) == (40, 0) and xy(twin.EndPoint) == (100, 0)
    assert out["at"] == [[40, 0]]


def test_break_between_two_points_leaves_a_gap(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    out = answer(edit2d.autocad_break_curve(pipe.Handle, [30, 0], second_point=[60, 0]))
    twin = doc.objects[out["new_handles"][0]]
    assert xy(pipe.EndPoint) == (30, 0) and xy(twin.StartPoint) == (60, 0)


def test_a_circle_needs_two_points(doc):
    c = Circle(doc, (0, 0, 0), 10)
    assert "second_point" in refusal(edit2d.autocad_break_curve(c.Handle, [10, 0]))
    out = answer(edit2d.autocad_break_curve(c.Handle, [0, 10], second_point=[-10, 0]))
    arc = doc.objects[out["replaced_by"]]
    # The part from the first point anticlockwise to the second goes: 180 round to 90 is left.
    assert math.degrees(arc.StartAngle) == pytest.approx(180) and math.degrees(arc.EndAngle) == pytest.approx(90)


def test_join_two_lines_in_one_straight_line_keeps_the_first(doc):
    a, b = Line(doc, (0, 0, 0), (40, 0, 0), layer="M-PIPE"), Line(doc, (100, 0, 0), (40, 0, 0))
    out = answer(edit2d.autocad_join_curves([a.Handle, b.Handle]))
    assert out["kind"] == "line" and out["handle"] == a.Handle and out["removed"] == [b.Handle]
    assert (xy(a.StartPoint), xy(a.EndPoint)) == ((0, 0), (100, 0))
    assert b.Handle not in doc.objects and doc.groups == 1


def test_join_lines_and_an_arc_into_a_new_polyline(doc):
    a = Line(doc, (0, 0, 0), (100, 0, 0), layer="M-PIPE")
    bend = Arc(doc, (100, 50, 0), 50, -math.pi / 2, 0)
    c = Line(doc, (150, 50, 0), (150, 200, 0))
    out = answer(edit2d.autocad_join_curves([a.Handle, c.Handle, bend.Handle]))
    poly = doc.objects[out["handle"]]
    assert out["kind"] == "polyline" and poly.Layer == "M-PIPE"
    assert poly.points() == [(0, 0), (100, 0), (150, 50), (150, 200)]
    assert poly.bulges[1] == pytest.approx(math.tan(math.pi / 8))
    assert sorted(out["removed"]) == sorted([a.Handle, c.Handle, bend.Handle])


def test_join_onto_a_polyline_keeps_the_polyline(doc):
    run = Poly(doc, [(0, 0), (50, 0), (100, 0)])
    tail = Line(doc, (100, 0, 0), (100, 50, 0))
    out = answer(edit2d.autocad_join_curves([tail.Handle, run.Handle]))
    assert out["handle"] == run.Handle and run.points() == [(0, 0), (50, 0), (100, 0), (100, 50)]


def test_join_with_a_gap_is_refused_and_nothing_is_erased(doc):
    a, b = Line(doc, (0, 0, 0), (10, 0, 0)), Line(doc, (12, 0, 0), (20, 5, 0))
    assert "nearest gap" in refusal(edit2d.autocad_join_curves([a.Handle, b.Handle]))
    assert b.Handle in doc.objects and doc.groups == 0


# ---- vertices and stretch ------------------------------------------------------------------------------


def test_move_a_vertex_by_a_displacement(doc):
    box = Poly(doc, [(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)
    out = answer(edit2d.autocad_edit_vertex(box.Handle, vertex=2, displacement=[0, -20]))
    assert out["from"] == [100, 50] and out["to"] == [100, 30]
    assert box.points()[2] == (100, 30) and box.Closed is True


def test_move_the_nearest_end_of_a_line(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    answer(edit2d.autocad_edit_vertex(pipe.Handle, near=[98, 2], to_point=[120, 0]))
    assert xy(pipe.EndPoint) == (120, 0)


def test_add_and_remove_a_polyline_vertex(doc):
    tray = Poly(doc, [(0, 0), (100, 0)])
    answer(edit2d.autocad_edit_vertex(tray.Handle, operation="add", vertex=0, to_point=[50, 20]))
    assert tray.points() == [(0, 0), (50, 20), (100, 0)]
    out = answer(edit2d.autocad_edit_vertex(tray.Handle, operation="remove", near=[50, 19]))
    assert tray.points() == [(0, 0), (100, 0)] and out["vertex_count"] == 2


def test_a_line_has_no_vertex_to_add(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    assert "two ends" in refusal(edit2d.autocad_edit_vertex(pipe.Handle, operation="add", vertex=0, to_point=[5, 5]))


def test_stretch_reshapes_moves_and_leaves_alone(doc):
    box = Poly(doc, [(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)
    door = Block(doc)
    door.InsertionPoint = (100.0, 25.0, 0.0)
    far = Circle(doc, (500, 500, 0), 5)
    hatch = Hatch(doc, (50, 0, 0), (150, 50, 0))
    out = answer(edit2d.autocad_stretch(
        [box.Handle, door.Handle, far.Handle, hatch.Handle], [90, -10], [110, 60], displacement=[50, 0]
    ))
    assert out["reshaped"] == [{"handle": box.Handle, "vertices_moved": [1, 2]}]
    assert box.points() == [(0, 0), (150, 0), (150, 50), (0, 50)]
    assert out["moved_whole"] == [door.Handle] and door.moved[1][:2] == (50, 0)
    assert out["untouched"] == [far.Handle]
    assert out["skipped"][0]["handle"] == hatch.Handle and hatch.moved is None
    assert doc.groups == 1


def test_stretch_with_nothing_inside_opens_no_step(doc):
    box = Poly(doc, [(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)
    out = answer(edit2d.autocad_stretch([box.Handle], [500, 500], [600, 600], displacement=[50, 0]))
    assert out["untouched"] == [box.Handle] and doc.groups == 0


# ---- explode and draw order -------------------------------------------------------------------------


def test_explode_erases_the_original_when_com_leaves_it(doc):
    valve = Block(doc)
    out = answer(edit2d.autocad_explode([valve.Handle]))
    assert out["exploded"] == 1 and len(out["objects"][0]["new_handles"]) == 2
    assert valve.Handle not in doc.objects


def test_a_block_with_attributes_is_kept_unless_asked(doc):
    tagged = Block(doc, attributes={"TAG": "V-101"})
    out = answer(edit2d.autocad_explode([tagged.Handle]))
    assert out["exploded"] == 0 and "TAG=V-101" in out["skipped"][0]["reason"]
    assert tagged.Handle in doc.objects and doc.groups == 0
    out = answer(edit2d.autocad_explode([tagged.Handle], allow_attribute_loss=True))
    assert out["objects"][0]["attributes"] == {"TAG": "V-101"}


def test_send_a_hatch_to_the_back_makes_the_table_once(doc):
    hatch = Hatch(doc, (0, 0, 0), (1, 1, 0))
    answer(edit2d.autocad_draw_order([hatch.Handle], "back"))
    table = doc.space.xdict.items["ACAD_SORTENTS"]
    assert table.calls == [("bottom", [hatch.Handle])]
    answer(edit2d.autocad_draw_order([hatch.Handle], "front"))
    assert doc.space.xdict.items["ACAD_SORTENTS"] is table and table.calls[-1] == ("top", [hatch.Handle])


def test_above_needs_a_reference_that_is_not_moved(doc):
    a, b = Line(doc, (0, 0, 0), (1, 0, 0)), Line(doc, (0, 1, 0), (1, 1, 0))
    assert "needs 'reference'" in refusal(edit2d.autocad_draw_order([a.Handle], "above"))
    assert "cannot also be" in refusal(edit2d.autocad_draw_order([a.Handle], "above", reference=a.Handle))
    answer(edit2d.autocad_draw_order([a.Handle], "under", reference=b.Handle))
    assert doc.space.xdict.items["ACAD_SORTENTS"].calls == [("below", [a.Handle], b.Handle)]


# ---- match properties and per-object lineweight / transparency ---------------------------------------


def test_match_properties_lists_old_and_new_and_skips_what_does_not_apply(doc):
    src = Text(doc, (0, 0, 0), style="ROMANS", layer="M-TEXT")
    src.Lineweight, src.EntityTransparency = 25, "30"
    note = Text(doc, (5, 5, 0))
    pipe = Line(doc, (0, 0, 0), (1, 0, 0), layer="M-TEXT")
    out = answer(edit2d.autocad_match_properties(src.Handle, [note.Handle, pipe.Handle], ["layer", "lineweight", "text_style"]))
    assert note.Layer == "M-TEXT" and note.StyleName == "ROMANS" and note.Lineweight == 25
    assert {"handle": note.Handle, "property": "lineweight", "from": "ByLayer", "to": "0.25 mm"} in out["before_after"]
    assert {"handle": pipe.Handle, "property": "text_style"} in out["skipped"]
    assert pipe.Lineweight == 25 and out["matched"] == 2
    assert doc.groups == 1


def test_match_properties_that_already_match_opens_no_step(doc):
    src, twin = Line(doc, (0, 0, 0), (1, 0, 0)), Line(doc, (0, 1, 0), (1, 1, 0))
    out = answer(edit2d.autocad_match_properties(src.Handle, [twin.Handle]))
    assert out["already"] == [twin.Handle] and out["before_after"] == [] and doc.groups == 0


def test_modify_entity_sets_lineweight_and_transparency(doc, monkeypatch):
    pipe = Line(doc, (0, 0, 0), (1, 0, 0))
    monkeypatch.setattr(modify, "resolve_handle", lambda d, h: d.objects[h])
    out = answer(modify.autocad_modify_entity(handles=[pipe.Handle], lineweight=0.35, transparency="50%"))
    assert pipe.Lineweight == 35 and pipe.EntityTransparency == "50"
    assert {"handle": pipe.Handle, "property": "transparency", "from": "ByLayer", "to": "50"} in out["before_after"]
    assert "not a lineweight" in refusal(modify.autocad_modify_entity(handles=[pipe.Handle], lineweight=0.33))


class TestPropertyWords:
    @pytest.mark.parametrize(("given", "code"), [
        (0.25, 25), ("0.35 mm", 35), (25, 25), ("ByLayer", -1), ("byblock", -2), ("Default", -3), (2.11, 211),
        (0, 0), (2, 200),
    ])
    def test_lineweights(self, given, code):
        assert props.lineweight_value(given) == code

    @pytest.mark.parametrize("given", [0.33, 3, "thick", True, 250])
    def test_lineweights_autocad_does_not_have(self, given):
        with pytest.raises(ValueError):
            props.lineweight_value(given)

    def test_lineweight_words(self):
        assert props.lineweight_words(-1) == "ByLayer" and props.lineweight_words(50) == "0.50 mm"

    @pytest.mark.parametrize(("given", "text"), [(50, "50"), ("50%", "50"), ("bylayer", "ByLayer"), (0, "0")])
    def test_transparency(self, given, text):
        assert props.transparency_value(given) == text

    @pytest.mark.parametrize("given", [91, -1, 12.5, "see-through"])
    def test_transparency_outside_what_autocad_takes(self, given):
        with pytest.raises(ValueError):
            props.transparency_value(given)

    def test_which_properties_match(self):
        assert props.matched_properties(None) == list(props.GENERAL)
        assert props.matched_properties(["all"]) == list(props.MATCHABLE)
        assert props.matched_properties(["Colour", "LTSCALE"]) == ["color", "linetype_scale"]
        with pytest.raises(ValueError, match="not a property"):
            props.matched_properties(["hatch_pattern"])


# ---- groups ------------------------------------------------------------------------------------------------


def test_make_list_add_remove_and_ungroup_a_group(doc):
    pump, valve, base = Block(doc), Block(doc), Line(doc, (0, 0, 0), (1, 0, 0))
    made = answer(edit2d.autocad_group("make", name="PUMP-01", handles=[pump.Handle, valve.Handle]))
    assert made == {"made": "PUMP-01", "members": 2}
    listed = answer(edit2d.autocad_list_groups(handle=valve.Handle))
    assert listed["count"] == 1 and listed["groups"][0]["member_count"] == 2
    added = answer(edit2d.autocad_group("add", name="pump-01", handles=[base.Handle, pump.Handle]))
    assert added["added"] == 1 and added["already_in"] == [pump.Handle] and added["members"] == 3
    removed = answer(edit2d.autocad_group("remove", name="PUMP-01", handles=[valve.Handle]))
    assert removed["removed"] == 1 and removed["members"] == 2
    gone = answer(edit2d.autocad_group("ungroup", handles=[base.Handle]))
    assert gone == {"ungrouped": ["PUMP-01"], "objects_kept": 2}
    assert answer(edit2d.autocad_list_groups())["count"] == 0
    assert pump.Handle in doc.objects and base.Handle in doc.objects


def test_a_group_name_is_checked_and_one_is_made_up_when_none_is_given(doc):
    a = Line(doc, (0, 0, 0), (1, 0, 0))
    assert answer(edit2d.autocad_group("make", handles=[a.Handle]))["made"] == "GROUP1"
    assert answer(edit2d.autocad_group("make", handles=[a.Handle]))["made"] == "GROUP2"
    assert "already exists" in refusal(edit2d.autocad_group("make", name="group1", handles=[a.Handle]))
    assert "cannot be a group name" in refusal(edit2d.autocad_group("make", name="A/B", handles=[a.Handle]))


def test_ungroup_of_objects_in_no_group_is_refused(doc):
    a = Line(doc, (0, 0, 0), (1, 0, 0))
    assert "not in any group" in refusal(edit2d.autocad_group("ungroup", handles=[a.Handle]))


# ---- guards --------------------------------------------------------------------------------------------------


class Layer:
    def __init__(self, locked):
        self.Lock = locked


class Layers:
    def __init__(self, locked: set[str]):
        self.locked = locked

    def Item(self, name):
        return Layer(name in self.locked)


def test_an_object_on_a_locked_layer_is_refused_before_any_copy_is_made(doc):
    doc.Layers = Layers({"M-LOCKED"})
    pipe = Line(doc, (0, 0, 0), (100, 0, 0), layer="M-LOCKED")
    a, b = Line(doc, (30, -1, 0), (30, 1, 0)), Line(doc, (70, -1, 0), (70, 1, 0))
    before = len(doc.objects)
    out = answer(edit2d.autocad_trim_extend("trim", [pipe.Handle], [a.Handle, b.Handle], points=[[50, 0]]))
    assert "locked layer 'M-LOCKED'" in out["failed"][0]["reason"]
    assert len(doc.objects) == before and doc.groups == 0
    assert "locked layer" in refusal(edit2d.autocad_break_curve(pipe.Handle, [40, 0]))


def test_a_failed_write_takes_its_copies_away(doc, monkeypatch):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    a, b = Line(doc, (30, -1, 0), (30, 1, 0)), Line(doc, (70, -1, 0), (70, 1, 0))
    before = set(doc.objects)

    def refuse(*_args):
        raise RuntimeError("AutoCAD said no")

    monkeypatch.setattr(edit2d, "_write", refuse)
    out = answer(edit2d.autocad_trim_extend("trim", [pipe.Handle], [a.Handle, b.Handle], points=[[50, 0]]))
    assert out["done"] == 0 and out["failed"]
    assert set(doc.objects) == before


def test_the_same_object_twice_is_refused(doc):
    pipe, wall = Line(doc, (0, 0, 0), (100, 0, 0)), Line(doc, (40, -10, 0), (40, 10, 0))
    assert "twice" in refusal(
        edit2d.autocad_trim_extend("trim", [pipe.Handle, pipe.Handle], [wall.Handle], points=[[20, 0], [90, 0]])
    )
    assert "twice" in refusal(edit2d.autocad_explode([pipe.Handle, pipe.Handle.lower()]))


def test_options_for_the_other_kind_of_corner_are_refused(doc):
    a, b = Line(doc, (100, 0, 0), (10, 0, 0)), Line(doc, (0, 100, 0), (0, 10, 0))
    box = Poly(doc, [(0, 0), (100, 0), (100, 50), (0, 50)], closed=True)
    assert "'vertices' is for one polyline" in refusal(
        edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle], radius=5, vertices=[1])
    )
    assert "'keep_points' is for two lines" in refusal(
        edit2d.autocad_fillet_chamfer("fillet", [box.Handle], radius=5, keep_points=[[1, 0], [0, 1]])
    )


# ---- can a draftsman find them? -----------------------------------------------------------------------------

# Kept here, not in test_find_tool.py, so this work and the other sessions' do not
# collide; scored the same way, with its function.
FIND = [
    ("trim the pipe back to the wall", "autocad_trim_extend"),
    ("extend the branch lines to the main", "autocad_trim_extend"),
    ("put a 150 radius on that duct corner", "autocad_fillet_chamfer"),
    ("fillet these two lines", "autocad_fillet_chamfer"),
    ("fillet those two lines with a 50 radius", "autocad_fillet_chamfer"),
    ("chamfer that corner 50 by 30", "autocad_fillet_chamfer"),
    ("round the corner between that line and the bend", "autocad_fillet_chamfer"),
    ("make that pipe 500 longer", "autocad_lengthen"),
    ("lengthen the line by 200", "autocad_lengthen"),
    ("make these lines exactly 2400 long", "autocad_lengthen"),
    ("split that pipe at the tee", "autocad_break_curve"),
    ("break this line at a point", "autocad_break_curve"),
    ("join these lines into one polyline", "autocad_join_curves"),
    ("move the end of that line to the column centre", "autocad_edit_vertex"),
    ("move that polyline vertex", "autocad_edit_vertex"),
    ("that box is drawn 200 too tall, stretch it", "autocad_stretch"),
    ("explode that block", "autocad_explode"),
    ("send the hatch behind the pipes", "autocad_draw_order"),
    ("bring the text to the front", "autocad_draw_order"),
    ("make these pipes look like that one", "autocad_match_properties"),
    ("match properties from that line", "autocad_match_properties"),
    ("group the pump and its valves", "autocad_group"),
    ("ungroup that", "autocad_group"),
    ("what groups are in this drawing", "autocad_list_groups"),
    ("make those lines 0.35 lineweight", "autocad_modify_entity"),
    ("make the existing services 50% transparent", "autocad_modify_entity"),
]


@pytest.mark.parametrize(("phrase", "want"), FIND)
def test_the_new_tools_are_found_first_in_a_draftsmans_words(phrase, want):
    from test_find_tool import found

    assert found(phrase)[:1] == [want], (phrase, found(phrase))


# ---- found by the independent review of PR #153 ------------------------------------------------------------


def test_join_of_two_polylines_keeps_the_first_even_when_the_result_is_straight(doc):
    a, b = Poly(doc, [(0, 0), (5, 0)]), Poly(doc, [(5, 0), (10, 0)])
    out = answer(edit2d.autocad_join_curves([a.Handle, b.Handle]))
    assert out["handle"] == a.Handle and out["kind"] == "polyline" and out["removed"] == [b.Handle]
    assert a.points() == [(0, 0), (10, 0)]


class LockAware(Line):
    """A line that refuses its own properties while it sits on a locked layer, as AutoCAD does."""

    GUARDED = {"Color", "Linetype", "LinetypeScale", "Lineweight", "EntityTransparency", "StyleName"}

    def __setattr__(self, name, value):
        doc = self.__dict__.get("doc")
        if name in self.GUARDED and doc is not None and "_ready" in self.__dict__:
            if self.__dict__.get("Layer") in getattr(doc, "Layers", Layers(set())).locked:
                raise RuntimeError("eOnLockedLayer")
        super().__setattr__(name, value)


def test_matching_a_source_on_a_locked_layer_writes_the_layer_last(doc):
    doc.Layers = Layers({"E-EXISTING"})
    src = Line(doc, (0, 0, 0), (1, 0, 0), layer="E-EXISTING")
    src.Color, src.Lineweight = 8, 18
    target = LockAware(doc, (0, 1, 0), (1, 1, 0))
    target._ready = True
    out = answer(edit2d.autocad_match_properties(src.Handle, [target.Handle]))
    assert target.Layer == "E-EXISTING" and target.Color == 8 and target.Lineweight == 18
    assert "failed" not in out


def test_modify_entity_writes_the_layer_last_but_lists_it_first(doc, monkeypatch):
    doc.Layers = Layers({"E-EXISTING"})
    target = LockAware(doc, (0, 1, 0), (1, 1, 0))
    target._ready = True
    monkeypatch.setattr(modify, "resolve_handle", lambda d, h: d.objects[h])
    monkeypatch.setattr(modify, "ensure_layer", lambda d, name: (None, False))
    out = answer(modify.autocad_modify_entity(handles=[target.Handle], layer="E-EXISTING", color=8))
    assert target.Layer == "E-EXISTING" and target.Color == 8
    assert [row["property"] for row in out["before_after"]] == ["layer", "color"]


class ErasedCircle(Circle):
    """A circle that cannot say its handle once erased, as a COM object may not."""

    @property
    def Handle(self):
        if self.__dict__.get("gone"):
            raise RuntimeError("Object was erased")
        return self.__dict__["_handle"]

    @Handle.setter
    def Handle(self, value):
        self.__dict__["_handle"] = value

    def Delete(self):
        super().Delete()
        self.__dict__["gone"] = True


def test_a_cut_circle_answers_with_its_old_handle_and_the_rest_still_get_cut(doc):
    sleeve = ErasedCircle(doc, (0, 0, 0), 10)
    old = sleeve.Handle
    pipe = Line(doc, (-50, 30, 0), (50, 30, 0))
    cut = Line(doc, (0, -60, 0), (0, 60, 0))
    out = answer(edit2d.autocad_trim_extend("trim", [sleeve.Handle, pipe.Handle], [cut.Handle],
                                            points=[[-10, 0], [-20, 30]]))
    assert out["done"] == 2 and out["objects"][0]["handle"] == old
    assert xy(pipe.StartPoint) == (0, 30)


def test_a_copy_that_will_not_take_its_shape_leaves_the_object_whole(doc, monkeypatch):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    a, b = Line(doc, (30, -1, 0), (30, 1, 0)), Line(doc, (70, -1, 0), (70, 1, 0))
    real = edit2d._write

    def picky(target, *args):
        if target is not pipe:
            raise RuntimeError("AutoCAD said no")
        real(target, *args)

    monkeypatch.setattr(edit2d, "_write", picky)
    out = answer(edit2d.autocad_trim_extend("trim", [pipe.Handle], [a.Handle, b.Handle], points=[[50, 0]]))
    assert out["failed"] and (xy(pipe.StartPoint), xy(pipe.EndPoint)) == ((0, 0), (100, 0))


def test_a_fillet_whose_lines_will_not_change_leaves_no_arc(doc, monkeypatch):
    a, b = Line(doc, (100, 0, 0), (10, 0, 0)), Line(doc, (0, 100, 0), (0, 10, 0))
    before = set(doc.objects)

    def refuse(*_args):
        raise RuntimeError("AutoCAD said no")

    monkeypatch.setattr(edit2d, "_write", refuse)
    refusal(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle], radius=20))
    assert set(doc.objects) == before


def test_nothing_to_do_opens_no_undo_step(doc):
    a, b = Line(doc, (100, 0, 0), (0, 0, 0)), Line(doc, (0, 100, 0), (0, 0, 0))
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle], radius=0))
    assert "NOTHING CHANGED" in out["note"] and doc.groups == 0
    box = Poly(doc, [(0, 0), (100, 0), (100, 50)])
    out = answer(edit2d.autocad_edit_vertex(box.Handle, vertex=1, displacement=[0, 0]))
    assert "NOTHING CHANGED" in out["note"] and doc.groups == 0


def test_a_group_whose_objects_cannot_be_added_is_not_left_empty(doc, monkeypatch):
    a = Line(doc, (0, 0, 0), (1, 0, 0))

    def refuse(self, objs):
        raise RuntimeError("AutoCAD said no")

    monkeypatch.setattr(Group, "AppendItems", refuse)
    refusal(edit2d.autocad_group("make", name="PUMP-01", handles=[a.Handle]))
    assert doc.Groups.groups == []
    assert "twice" in refusal(edit2d.autocad_group("make", name="X", handles=[a.Handle, a.Handle]))


@pytest.mark.parametrize("given", ["inf", "-inf", "nan"])
def test_infinity_is_not_a_lineweight_or_a_transparency(given):
    with pytest.raises(ValueError, match="is not a lineweight"):
        props.lineweight_value(given)
    with pytest.raises(ValueError, match="is not a transparency"):
        props.transparency_value(given)


# ---- lengthen (#154, D-144) -----------------------------------------------------------------------


def test_lengthen_grows_the_end_nearest_the_point_and_keeps_the_handle(doc):
    pipe = Line(doc, (0, 0, 5), (1000, 0, 5), layer="M-PIPE")
    out = answer(edit2d.autocad_lengthen([pipe.Handle], "delta", 500, points=[[900, 0]]))
    assert out["done"] == 1 and out["objects"][0] == {
        "handle": pipe.Handle, "end": "end", "was": 1000.0, "now": 1500.0, "changed_by": 500.0}
    assert (xy(pipe.StartPoint), xy(pipe.EndPoint)) == ((0, 0), (1500, 0))
    assert pipe.StartPoint[2] == 5 and pipe.Layer == "M-PIPE"  # its height and layer are kept
    assert len(doc.objects) == 1 and doc.groups == 1


def test_lengthen_the_start_with_a_negative_delta_cuts_it_back(doc):
    pipe = Line(doc, (0, 0, 0), (1000, 0, 0))
    out = answer(edit2d.autocad_lengthen([pipe.Handle], "delta", -200, end="start"))
    assert out["objects"][0]["end"] == "start" and out["objects"][0]["changed_by"] == -200.0
    assert (xy(pipe.StartPoint), xy(pipe.EndPoint)) == ((200, 0), (1000, 0))


def test_lengthen_total_and_percent_on_several_objects_in_one_undo_step(doc):
    a, b = Line(doc, (0, 0, 0), (1000, 0, 0)), Line(doc, (0, 50, 0), (500, 50, 0))
    answer(edit2d.autocad_lengthen([a.Handle, b.Handle], "total", 2400))
    assert xy(a.EndPoint) == (2400, 0) and xy(b.EndPoint) == (2400, 50)
    assert doc.groups == 1
    answer(edit2d.autocad_lengthen([a.Handle], "percent", 50))
    assert xy(a.EndPoint) == (1200, 0)


def test_lengthen_an_arc_runs_on_round_its_own_circle(doc):
    arc = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2)
    answer(edit2d.autocad_lengthen([arc.Handle], "delta", 500 * math.pi / 4))
    assert arc.StartAngle == pytest.approx(0, abs=1e-9) and arc.EndAngle == pytest.approx(3 * math.pi / 4)
    assert arc.Radius == 500 and arc.Center == (0, 0, 0)
    answer(edit2d.autocad_lengthen([arc.Handle], "percent", 50, end="start"))
    assert arc.EndAngle == pytest.approx(3 * math.pi / 4)
    assert arc.StartAngle == pytest.approx(3 * math.pi / 8)


def test_lengthen_a_polyline_cuts_back_over_a_corner_and_keeps_its_width(doc):
    run = Poly(doc, [(0, 0), (1000, 0), (1000, 500)], width=4.0)
    answer(edit2d.autocad_lengthen([run.Handle], "delta", -700))
    assert run.points() == [(0, 0), (800, 0)] and run.ConstantWidth == 4.0


def test_lengthen_says_what_it_refused_and_still_does_the_rest(doc):
    good = Line(doc, (0, 0, 0), (100, 0, 0))
    box = Poly(doc, [(0, 0), (10, 0), (10, 10)], closed=True)
    circle = Circle(doc, (0, 0, 0), 5)
    out = answer(edit2d.autocad_lengthen([good.Handle, box.Handle, circle.Handle], "delta", 50))
    assert out["done"] == 1 and xy(good.EndPoint) == (150, 0)
    reasons = {row["handle"]: row["reason"] for row in out["failed"]}
    assert "closed" in reasons[box.Handle] and "circle" in reasons[circle.Handle]


def test_lengthen_that_would_leave_nothing_or_change_nothing_writes_nothing(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    out = answer(edit2d.autocad_lengthen([pipe.Handle], "delta", -100))
    assert out["done"] == 0 and "vanish" in out["failed"][0]["reason"]
    out = answer(edit2d.autocad_lengthen([pipe.Handle], "percent", 100))
    assert out["done"] == 0 and "nothing to change" in out["failed"][0]["reason"]
    assert (xy(pipe.StartPoint), xy(pipe.EndPoint)) == ((0, 0), (100, 0)) and doc.groups == 0


def test_lengthen_checks_its_arguments(doc):
    pipe = Line(doc, (0, 0, 0), (100, 0, 0))
    assert "one point per object" in refusal(edit2d.autocad_lengthen([pipe.Handle], "delta", 5, points=[[0, 0], [1, 1]]))
    assert "twice" in refusal(edit2d.autocad_lengthen([pipe.Handle, pipe.Handle.lower()], "delta", 5))


# ---- fillet and chamfer between a line, an arc and a polyline's end (#154, D-144) --------------------


def test_fillet_a_line_and_an_arc_trims_both_and_adds_a_tangent_arc(doc):
    arc = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2, layer="M-BEND")
    line = Line(doc, (100, 300, 0), (1500, 300, 0), layer="M-DUCT")
    line.Lineweight = 35
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [line.Handle, arc.Handle], radius=50))
    fillet = doc.objects[out["arc"]]
    assert out["objects"] == [line.Handle, arc.Handle] and out["ends"] == [None, None]
    assert fillet.Radius == 50 and fillet.Layer == "M-DUCT" and fillet.Lineweight == 35
    assert math.hypot(fillet.Center[0], fillet.Center[1]) == pytest.approx(550)  # tangent from outside
    assert fillet.Center[1] - 300 == pytest.approx(50)  # and 50 above the line
    assert line.StartPoint[0] == pytest.approx(fillet.Center[0]) and xy(line.EndPoint) == (1500, 300)
    assert arc.Radius == 500 and arc.EndAngle == pytest.approx(math.pi / 2)  # still ends at 90 degrees
    assert arc.StartAngle > math.radians(36.87)  # cut back past the old meeting point
    assert doc.groups == 1


def test_fillet_two_arcs(doc):
    a, b = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2), Arc(doc, (800, 0, 0), 500, math.pi / 2, math.pi)
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle], radius=50))
    fillet = doc.objects[out["arc"]]
    assert math.dist(fillet.Center[:2], (0, 0)) == pytest.approx(550)
    assert math.dist(fillet.Center[:2], (800, 0)) == pytest.approx(550)


def test_fillet_the_ends_of_two_polylines_keeps_each_one_polyline(doc):
    first = Poly(doc, [(0, 0), (1000, 0), (1000, 300)], layer="M-A")
    second = Poly(doc, [(1500, 900), (1500, 600), (1300, 600)])
    before = len(doc.objects)
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [first.Handle, second.Handle], radius=100))
    assert out["ends"] == ["end", "end"]
    assert first.points() == [(0, 0), (1000, 0), (1000, 500)]
    assert second.points() == [(1500, 900), (1500, 600), (1100, 600)]
    fillet = doc.objects[out["arc"]]
    assert fillet.Radius == 100 and xy(fillet.Center) == (1100, 500) and fillet.Layer == "M-A"
    assert len(doc.objects) == before + 1 and doc.groups == 1


def test_chamfer_a_line_and_an_arc_measures_along_the_arc(doc):
    arc = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2)
    line = Line(doc, (100, 300, 0), (1500, 300, 0))
    out = answer(edit2d.autocad_fillet_chamfer("chamfer", [line.Handle, arc.Handle], distance=40, distance2=40,
                                               keep_points=[[1400, 300], [0, 490]]))
    cut = doc.objects[out["chamfer_line"]]
    assert xy(cut.StartPoint) == (440, 300)
    end = cut.EndPoint
    assert math.hypot(end[0], end[1]) == pytest.approx(500)
    assert math.atan2(end[1], end[0]) - math.atan2(300, 400) == pytest.approx(40 / 500)
    assert out["distances"] == [40.0, 40.0]


def test_fillet_with_an_arc_says_where_the_other_corner_is(doc):
    arc = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2)
    line = Line(doc, (100, 300, 0), (1500, 300, 0))
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [line.Handle, arc.Handle], radius=50))
    assert "more than one place" in out["note"]


def test_what_a_fillet_with_an_arc_refuses_it_refuses_before_anything_changes(doc):
    arc = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2)
    line = Line(doc, (100, 300, 0), (1500, 300, 0))
    box = Poly(doc, [(0, 0), (100, 0), (100, 50)], closed=True)
    far = Line(doc, (0, 5000, 0), (50, 5000, 0))
    before = (len(doc.objects), doc.groups)
    assert "angle method" in refusal(
        edit2d.autocad_fillet_chamfer("chamfer", [line.Handle, arc.Handle], distance=10, angle=30))
    assert "closed polyline" in refusal(edit2d.autocad_fillet_chamfer("fillet", [box.Handle, line.Handle], radius=5))
    assert "never meet" in refusal(edit2d.autocad_fillet_chamfer("fillet", [far.Handle, arc.Handle], radius=5))
    assert "different objects" in refusal(
        edit2d.autocad_fillet_chamfer("fillet", [arc.Handle, arc.Handle.lower()], radius=5))
    assert "Try a smaller radius" in refusal(
        edit2d.autocad_fillet_chamfer("fillet", [line.Handle, arc.Handle], radius=50000))
    run = Poly(doc, [(0, 0), (10, 0), (10, 10)])
    assert "all but its end" in refusal(edit2d.autocad_fillet_chamfer(
        "fillet", [run.Handle, line.Handle], radius=5, keep_points=[[1, 0], [1500, 300]]))
    assert (len(doc.objects) - 1, doc.groups) == before  # only the polyline made for the last call is new


def test_a_fillet_with_an_arc_whose_write_fails_leaves_no_new_arc(doc, monkeypatch):
    arc = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2)
    line = Line(doc, (100, 300, 0), (1500, 300, 0))
    before = set(doc.objects)

    def refuse(*_args):
        raise RuntimeError("AutoCAD said no")

    monkeypatch.setattr(edit2d, "_write", refuse)
    refusal(edit2d.autocad_fillet_chamfer("fillet", [line.Handle, arc.Handle], radius=50))
    assert set(doc.objects) == before


def test_two_lines_still_go_through_the_old_answer_shape(doc):
    a, b = Line(doc, (100, 0, 0), (10, 0, 0)), Line(doc, (0, 100, 0), (0, 10, 0))
    out = answer(edit2d.autocad_fillet_chamfer("fillet", [a.Handle, b.Handle], radius=20))
    assert out["lines"] == [a.Handle, b.Handle] and "objects" not in out


def test_lengthen_and_a_fillet_with_an_arc_refuse_a_locked_layer(doc):
    doc.Layers = Layers({"M-LOCKED"})
    pipe = Line(doc, (0, 0, 0), (100, 0, 0), layer="M-LOCKED")
    out = answer(edit2d.autocad_lengthen([pipe.Handle], "delta", 50))
    assert out["done"] == 0 and "locked layer 'M-LOCKED'" in out["failed"][0]["reason"]
    assert xy(pipe.EndPoint) == (100, 0) and doc.groups == 0
    arc = Arc(doc, (0, 0, 0), 500, 0, math.pi / 2)
    before = len(doc.objects)
    assert "locked layer" in refusal(edit2d.autocad_fillet_chamfer("fillet", [pipe.Handle, arc.Handle], radius=5))
    assert len(doc.objects) == before and doc.groups == 0
