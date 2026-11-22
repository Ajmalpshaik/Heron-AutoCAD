"""A multiline closed with a mitred corner (#55), a spline by control points and a spline's
fit points edited (#56) - D-97 - without AutoCAD.

The knots and the fit-point plan are plain arithmetic, checked here by
evaluating the curve itself. The tools run against a fake drawing and a fake
plug-in that records each operation it is asked for. Whether AutoCAD takes
them is Group AI in docs/NEEDS-CHECKING.md, NOT RUN.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from autocad_mcp.acad.geometry import control_spline, spline_point
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, drafting
from autocad_mcp.tools.drafting import plan_fit_edits

# ---------------------------------------------------------------------------
# Knots
# ---------------------------------------------------------------------------


class TestControlSpline:
    def test_an_open_cubic_is_clamped_with_even_knots_between(self):
        pts = [[0, 0], [100, 200], [300, 200], [400, 0], [500, 100]]
        control, knots = control_spline(pts, 3)
        assert knots == [0.0, 0.0, 0.0, 0.0, 1.0, 2.0, 2.0, 2.0, 2.0]
        assert len(knots) == len(control) + 3 + 1
        assert control[1] == [100.0, 200.0, 0.0]

    def test_an_open_one_starts_on_its_first_point_and_ends_on_its_last(self):
        pts = [[0, 0], [100, 200], [300, 200], [400, 0]]
        control, knots = control_spline(pts, 3)
        assert spline_point(control, knots, 3, knots[3]) == pytest.approx([0.0, 0.0, 0.0])
        assert spline_point(control, knots, 3, knots[-4] - 1e-12) == pytest.approx([400.0, 0.0, 0.0], abs=1e-6)

    def test_it_leaves_along_its_first_leg(self):
        pts = [[0, 0], [100, 100], [300, 100], [400, 0]]
        control, knots = control_spline(pts, 3)
        a = spline_point(control, knots, 3, 0.0)
        b = spline_point(control, knots, 3, 1e-6)
        assert math.atan2(b[1] - a[1], b[0] - a[0]) == pytest.approx(math.radians(45), abs=1e-4)

    def test_degree_1_runs_straight_through_its_points(self):
        pts = [[0, 0], [100, 0], [100, 100]]
        control, knots = control_spline(pts, 1)
        assert knots == [0.0, 0.0, 1.0, 2.0, 2.0]
        assert spline_point(control, knots, 1, 1.0) == pytest.approx([100.0, 0.0, 0.0])
        assert spline_point(control, knots, 1, 0.5) == pytest.approx([50.0, 0.0, 0.0])

    def test_a_closed_one_wraps_round_and_meets_itself_smoothly(self):
        square = [[0, 0], [100, 0], [100, 100], [0, 100]]
        control, knots = control_spline(square, 3, closed=True)
        assert len(control) == 7 and control[4:] == control[:3]
        assert knots == [float(i) for i in range(11)]
        lo, hi = knots[3], knots[7]
        start = spline_point(control, knots, 3, lo)
        end = spline_point(control, knots, 3, hi - 1e-12)
        assert start == pytest.approx(end, abs=1e-6)
        # Same direction leaving the seam as arriving at it: no corner.
        after = spline_point(control, knots, 3, lo + 1e-5)
        before = spline_point(control, knots, 3, hi - 1e-5)
        leaving = math.atan2(after[1] - start[1], after[0] - start[0])
        arriving = math.atan2(start[1] - before[1], start[0] - before[0])
        assert leaving == pytest.approx(arriving, abs=1e-3)

    def test_a_closed_frame_given_with_its_first_point_again_is_the_same(self):
        once = control_spline([[0, 0], [100, 0], [50, 80]], 2, closed=True)
        twice = control_spline([[0, 0], [100, 0], [50, 80], [0, 0]], 2, closed=True)
        assert once == twice

    @pytest.mark.parametrize("points, degree, closed, why", [
        ([[0, 0], [10, 0], [20, 0]], 3, False, "at least 4"),
        ([[0, 0], [10, 0]], 1, True, "closed degree 1 spline needs at least 3"),
        ([[0, 0], [10, 0], [10, 0], [20, 5]], 2, False, "at one place"),
        ([[0, 0], [10, 0]], 0, False, "degree must be 1 to 10"),
        ([[0, 0], [10, 0]], 11, False, "degree must be 1 to 10"),
    ])
    def test_refusals(self, points, degree, closed, why):
        with pytest.raises(ValueError, match=why):
            control_spline(points, degree, closed)


# ---------------------------------------------------------------------------
# The fit-point plan
# ---------------------------------------------------------------------------


FIT = [[0, 0, 0], [100, 50, 0], [200, 0, 0], [300, 50, 0]]


class TestFitPlan:
    def test_a_move_is_one_set(self):
        steps, result, rows = plan_fit_edits(FIT, [{"move": 2, "to": [200, -40]}])
        assert steps == [{"kind": "set", "index": 2, "point": [200.0, -40.0, 0.0]}]
        assert result[2] == [200.0, -40.0, 0.0] and len(result) == 4
        assert rows == [{"property": "fit point 2", "from": [200.0, 0.0, 0.0], "to": [200.0, -40.0, 0.0]}]

    def test_insert_numbers_the_new_point_and_the_count_adds_after_the_last(self):
        steps, result, _ = plan_fit_edits(FIT, [{"insert": 1, "point": [50, 40]}, {"insert": 5, "point": [400, 0]}])
        assert [s["kind"] for s in steps] == ["insert", "insert"]
        assert result[1] == [50.0, 40.0, 0.0] and result[-1] == [400.0, 0.0, 0.0] and len(result) == 6

    def test_edits_count_the_points_as_they_stand_when_they_come(self):
        _, result, rows = plan_fit_edits(FIT, [{"remove": 0}, {"move": 0, "to": [110, 60]}])
        assert result == [[110.0, 60.0, 0.0], [200.0, 0.0, 0.0], [300.0, 50.0, 0.0]]
        assert rows[0] == {"property": "fit point 0", "from": [0.0, 0.0, 0.0], "to": None}

    @pytest.mark.parametrize("edits, why", [
        ([{"move": 4, "to": [0, 0]}], "moves point 4, but the spline has 4"),
        ([{"insert": 5, "point": [0, 0]}], "adds point 5"),
        ([{"remove": -1}], "removes point -1"),
        ([{"move": 1}], "needs 'to'"),
        ([{"move": 1, "remove": 2}], "exactly one of"),
        ([{"move": "2", "to": [0, 0]}], "point number"),
        ([{"move": 1, "to": [0, 0]}], "at one place"),
        ([{"remove": 0}, {"remove": 0}, {"remove": 0}], "leaves 1 fit points"),
        (["move 2"], "must be an object"),
    ])
    def test_refusals_name_the_edit(self, edits, why):
        with pytest.raises(ValueError, match=why):
            plan_fit_edits(FIT, edits)

    def test_a_closed_spline_keeps_three_and_its_seam(self):
        with pytest.raises(ValueError, match="closed spline needs 3"):
            plan_fit_edits(FIT[:3], [{"remove": 0}], closed=True)
        with pytest.raises(ValueError, match="at one place"):
            plan_fit_edits(FIT, [{"move": 3, "to": [0, 0]}], closed=True)

    def test_a_spline_with_no_fit_points_is_refused(self):
        with pytest.raises(ValueError, match="control points"):
            plan_fit_edits([], [{"remove": 0}])


# ---------------------------------------------------------------------------
# The tools, with a fake plug-in
# ---------------------------------------------------------------------------


class Made:
    def __init__(self, kind, handle):
        self.ObjectName, self.Handle, self.Layer = kind, handle, "0"
        self.Document = None
        self.written = {}

    def __setattr__(self, name, value):
        if name[0].isupper() and name not in ("ObjectName", "Handle", "Layer", "Document"):
            self.__dict__.setdefault("written", {})[name] = value
        object.__setattr__(self, name, value)


class Space:
    def __init__(self, doc):
        self.doc = doc
        self.calls = []

    def AddMLine(self, points):
        self.calls.append(("AddMLine", tuple(points.value)))
        made = Made("AcDbMline", "3A0")
        made.Document = self.doc
        self.doc.objects["3A0"] = made
        return made


class Doc:
    def __init__(self, ucs=None):
        self.variables = {"UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0),
                          "CMLSTYLE": "Standard"}
        self.variables.update(ucs or {})
        self.ModelSpace = self.PaperSpace = Space(self)
        self.objects = {}

    def GetVariable(self, name):
        return self.variables[name]

    def SetVariable(self, name, value):
        self.variables[name] = value

    def HandleToObject(self, handle):
        return self.objects[handle]

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


class Plugin:
    def __init__(self, doc):
        self.doc = doc
        self.calls = []
        self.answers = {}

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        answer = self.answers.get(operation)
        if isinstance(answer, Exception):
            raise answer
        if operation == "add_cv_spline":
            made = Made("AcDbSpline", "4B0")
            made.Document = self.doc
            self.doc.objects["4B0"] = made
            return answer or {"created": True, "handle": "4B0", "degree": args["degree"],
                              "control_points": len(args["points"]) // 3, "closed": False}
        return answer or {"closed": True, "handle": args.get("handle"), "edited": True}


@pytest.fixture
def cad(monkeypatch):
    state = {}

    def make(ucs=None, plugin=True):
        doc = Doc(ucs)
        state["doc"] = doc
        runner = Plugin(doc) if plugin else None
        monkeypatch.setattr(_shared, "plugin_runner", lambda: runner)
        return doc, runner

    async def run(fn):
        return fn()

    monkeypatch.setattr(drafting, "run", run)
    monkeypatch.setattr(drafting, "get_doc", lambda: state["doc"])
    monkeypatch.setattr(drafting, "require_idle", lambda d: None)
    monkeypatch.setattr(drafting, "apply_properties", lambda *a, **k: {})
    monkeypatch.setattr(drafting, "resolve_handle", lambda doc, handle: doc.objects[handle])
    return make


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


SQUARE = [[0, 0], [4000, 0], [4000, 3000], [0, 3000]]


class TestClosedMultiline:
    def test_the_plug_in_closes_it_and_the_first_point_is_not_repeated(self, cad):
        doc, plugin = cad()
        out = call(drafting.autocad_draw_multiline(points=SQUARE, scale=200, closed=True))
        (_, flat), = doc.ModelSpace.calls
        assert len(flat) == 12  # four corners, not five
        assert plugin.calls == [("close_multiline", {"handle": "3A0"})]
        assert out["closed"] is True and out["mitred"] is True and "warning" not in out
        assert out["vertices"] == 4

    def test_an_open_multiline_never_asks_the_plug_in(self, cad):
        doc, plugin = cad()
        out = call(drafting.autocad_draw_multiline(points=SQUARE, scale=200))
        assert plugin.calls == [] and "mitred" not in out

    def test_if_the_plug_in_cannot_the_first_point_is_added_and_it_says_why(self, cad):
        doc, plugin = cad()
        plugin.answers["close_multiline"] = AutocadError("AutoCAD refused it (eInvalidInput). Nothing was changed.")
        out = call(drafting.autocad_draw_multiline(points=SQUARE, closed=True))
        made = doc.objects["3A0"]
        written = tuple(made.written["Coordinates"].value)
        assert len(written) == 15 and written[-3:] == written[:3]
        assert out["mitred"] is False and "eInvalidInput" in out["warning"] and "overlaps" in out["warning"]

    def test_without_the_plug_in_it_is_drawn_the_old_way_and_says_so(self, cad):
        doc, _ = cad(plugin=False)
        out = call(drafting.autocad_draw_multiline(points=SQUARE, closed=True))
        (_, flat), = doc.ModelSpace.calls
        assert len(flat) == 15 and flat[-3:] == flat[:3]
        assert out["mitred"] is False and "plug-in is not in this job" in out["warning"]


class TestControlPointSpline:
    def test_the_plug_in_is_sent_the_frame_and_the_knots(self, cad):
        doc, plugin = cad()
        out = call(drafting.autocad_draw_spline(points=[[0, 0], [100, 200], [300, 200], [400, 0]],
                                                method="control_points", layer="M-DUCT"))
        (operation, args), = plugin.calls
        assert operation == "add_cv_spline"
        assert args["points"] == [0.0, 0.0, 0.0, 100.0, 200.0, 0.0, 300.0, 200.0, 0.0, 400.0, 0.0, 0.0]
        assert args["knots"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0] and args["degree"] == 3
        assert args["layer"] == "M-DUCT" and args["space"] == "model" and "color" not in args
        assert out["handle"] == "4B0" and out["control_points"] == 4 and out["degree"] == 3
        assert doc.ModelSpace.calls == []  # no AddSpline: that one only takes fit points

    def test_a_closed_one_is_sent_wrapped(self, cad):
        _, plugin = cad()
        call(drafting.autocad_draw_spline(points=SQUARE, method="control_points", closed=True, degree=2))
        (_, args), = plugin.calls
        assert len(args["points"]) == 6 * 3 and args["knots"] == [float(i) for i in range(9)]

    def test_its_points_are_read_in_the_ucs(self, cad):
        _, plugin = cad({"UCSORG": (1000.0, 0.0, 0.0), "UCSXDIR": (0.0, 1.0, 0.0), "UCSYDIR": (-1.0, 0.0, 0.0)})
        out = call(drafting.autocad_draw_spline(points=[[0, 0], [100, 0]], method="control_points", degree=1,
                                                coords="ucs"))
        assert plugin.calls[0][1]["points"] == pytest.approx([1000.0, 0.0, 0.0, 1000.0, 100.0, 0.0])
        assert "converted_from_ucs" in out

    def test_refusals_before_anything_is_sent(self, cad):
        _, plugin = cad()
        assert "fit_points" in error(drafting.autocad_draw_spline(points=SQUARE, method="control_points",
                                                                  start_tangent=[1, 0, 0]))
        assert "at least 4" in error(drafting.autocad_draw_spline(points=SQUARE[:3], method="control_points"))
        assert plugin.calls == []
        cad(plugin=False)
        assert "plug-in" in error(drafting.autocad_draw_spline(points=SQUARE, method="control_points"))

    def test_fit_points_are_still_the_default_and_go_through_addspline(self, cad):
        doc, plugin = cad()

        def add_spline(points, start, end):
            made = Made("AcDbSpline", "5C0")
            made.Document = doc
            doc.objects["5C0"] = made
            return made

        doc.ModelSpace.AddSpline = add_spline
        out = call(drafting.autocad_draw_spline(points=SQUARE))
        assert plugin.calls == [] and out["fit_points"] == 4


class Spline(Made):
    def __init__(self, handle, fit, closed=False):
        super().__init__("AcDbSpline", handle)
        self.FitPoints = [c for p in fit for c in p]
        self.Closed = closed


class TestEditSpline:
    def test_a_move_is_sent_as_a_step_with_the_points_to_expect(self, cad):
        doc, plugin = cad()
        doc.objects["6D0"] = Spline("6D0", FIT)
        plugin.answers["edit_spline_fit_points"] = {"handle": "6D0", "edited": True, "fit_points_before": 4,
                                                     "fit_points": 4, "closed": False}
        out = call(drafting.autocad_edit_spline(handle="6D0", edits=[{"move": 1, "to": [100, 80]}]))
        (operation, args), = plugin.calls
        assert operation == "edit_spline_fit_points"
        assert args["steps"] == [{"kind": "set", "index": 1, "point": [100.0, 80.0, 0.0]}]
        assert args["result"][3:6] == [100.0, 80.0, 0.0] and len(args["result"]) == 12
        assert out["before_after"] == [{"handle": "6D0", "property": "fit point 1",
                                        "from": [100.0, 50.0, 0.0], "to": [100.0, 80.0, 0.0]}]
        assert out["fit_points"] == 4 and out["points"][1] == [100.0, 80.0, 0.0]

    def test_points_are_read_in_the_ucs(self, cad):
        doc, plugin = cad({"UCSORG": (0.0, 0.0, 500.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0)})
        doc.objects["6D0"] = Spline("6D0", FIT)
        call(drafting.autocad_edit_spline(handle="6D0", edits=[{"insert": 4, "point": [400, 0]}], coords="ucs"))
        assert plugin.calls[0][1]["steps"] == [{"kind": "insert", "index": 4, "point": [400.0, 0.0, 500.0]}]

    def test_a_bad_edit_is_refused_and_the_plug_in_never_asked(self, cad):
        doc, plugin = cad()
        doc.objects["6D0"] = Spline("6D0", FIT)
        answer = error(drafting.autocad_edit_spline(handle="6D0", edits=[{"remove": 9}]))
        assert "removes point 9" in answer and "Nothing was changed" in answer and plugin.calls == []

    def test_a_control_point_spline_and_a_line_are_refused(self, cad):
        doc, plugin = cad()
        doc.objects["6D0"] = Spline("6D0", [])
        assert "control points" in error(drafting.autocad_edit_spline(handle="6D0", edits=[{"remove": 0}]))
        doc.objects["7E0"] = Made("AcDbLine", "7E0")
        assert "not a spline" in error(drafting.autocad_edit_spline(handle="7E0", edits=[{"remove": 0}]))
        assert plugin.calls == []

    def test_without_the_plug_in_it_is_refused(self, cad):
        cad(plugin=False)
        assert "plug-in" in error(drafting.autocad_edit_spline(handle="6D0", edits=[{"remove": 0}]))

    def test_a_refusal_from_the_plug_in_is_passed_on(self, cad):
        doc, plugin = cad()
        doc.objects["6D0"] = Spline("6D0", FIT)
        plugin.answers["edit_spline_fit_points"] = AutocadError(
            "AutoCAD did not end up with the fit points asked for on 6D0. Nothing was changed.")
        assert "Nothing was changed" in error(drafting.autocad_edit_spline(handle="6D0", edits=[{"remove": 0}]))


class TestReviewFixes:
    def test_an_unknown_outcome_adds_nothing_and_says_it_may_be_closed(self, cad):
        doc, plugin = cad()
        plugin.answers["close_multiline"] = AutocadError(
            "Outcome unknown: Heron in AutoCAD did not answer within 300 s, so the operation may have run.")
        out = call(drafting.autocad_draw_multiline(points=SQUARE, closed=True))
        assert "Coordinates" not in doc.objects["3A0"].written
        assert out["closed"] is None and out["mitred"] is False and "may or may not be closed" in out["warning"]

    def test_when_nothing_could_close_it_it_does_not_say_closed(self, cad, monkeypatch):
        doc, plugin = cad()
        plugin.answers["close_multiline"] = AutocadError("AutoCAD refused it (eInvalidInput).")
        made = Space.AddMLine

        def stubborn(self, points):
            entity = made(self, points)

            def refuse(name, value):
                if name == "Coordinates":
                    raise RuntimeError("read only here")
                object.__setattr__(entity, name, value)

            entity.__class__ = type("Stubborn", (Made,), {"__setattr__": lambda s, n, v: refuse(n, v)})
            return entity

        monkeypatch.setattr(Space, "AddMLine", stubborn)
        out = call(drafting.autocad_draw_multiline(points=SQUARE, closed=True))
        assert out["closed"] is False and "OPEN" in out["warning"] and "Closed by" not in out["warning"]

    @pytest.mark.parametrize("bad", [[4200, None], ["4200", "1,800"], [1, 2, 3, 4], [True, 5], [float("nan"), 0]])
    def test_a_point_that_is_not_numbers_is_refused_never_read_as_0(self, cad, bad):
        doc, plugin = cad()
        doc.objects["6D0"] = Spline("6D0", FIT)
        answer = error(drafting.autocad_edit_spline(handle="6D0", edits=[{"move": 2, "to": bad}]))
        assert "Nothing was changed" in answer and plugin.calls == []
        with pytest.raises(ValueError):
            plan_fit_edits(FIT, [{"insert": 1, "point": bad}])


def test_a_closed_spline_listed_with_its_seam_can_still_be_edited():
    ring = [[0, 0, 0], [100, 0, 0], [50, 80, 0], [0, 0, 0]]
    steps, result, _ = plan_fit_edits(ring, [{"move": 1, "to": [120, 0]}], closed=True)
    assert steps == [{"kind": "set", "index": 1, "point": [120.0, 0.0, 0.0]}] and result[-1] == [0.0, 0.0, 0.0]
