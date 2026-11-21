"""autocad_sequence: the pre-flight checks, the level ceiling, and a real run.

The level ceiling is the part that matters. A sequence runs each step's tool
body directly, because going back through the gate would wait on a lock the
sequence already holds — so the ceiling here is the only thing stopping a
Changes padlock from buying a save, a plot or an AutoLISP call.
"""

from __future__ import annotations

import json

import pytest
import pythoncom

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.registry import mcp
from autocad_mcp.core.risk import RISK, Risk, risk_of
from autocad_mcp.tools import draw, register_all, sequence
from autocad_mcp.tools.sequence import ALLOWED, MAX_STEPS, SELF, plan_steps

register_all()

LINE = {"tool": "autocad_draw_line", "args": {"start": [0, 0], "end": [100, 0]}}


class TestPlanSteps:
    def test_a_good_step_comes_back_planned(self):
        planned = plan_steps([LINE])
        assert planned[0]["tool"] == "autocad_draw_line"
        assert planned[0]["level"] == "change"
        assert planned[0]["label"] == "draw line"

    def test_the_prefix_is_added_when_it_is_left_off(self):
        assert plan_steps([{"tool": "draw_line", "args": LINE["args"]}])[0]["tool"] == "autocad_draw_line"

    def test_a_label_is_kept(self):
        assert plan_steps([{**LINE, "label": "wall base"}])[0]["label"] == "wall base"

    def test_arguments_are_validated_before_anything_runs(self):
        with pytest.raises(AutocadError) as exc:
            plan_steps([{"tool": "autocad_draw_line", "args": {"start": [0, 0]}}])
        assert "Step 1" in str(exc.value) and "Nothing was run" in str(exc.value)

    def test_a_bad_step_in_the_middle_stops_the_whole_plan(self):
        with pytest.raises(AutocadError, match="Step 2"):
            plan_steps([LINE, {"tool": "autocad_draw_circle", "args": {"center": [0, 0], "radius": -5}}, LINE])

    def test_an_unknown_tool_suggests_something(self):
        with pytest.raises(AutocadError) as exc:
            plan_steps([{"tool": "autocad_draw_lion", "args": {}}])
        assert "no tool called" in str(exc.value)

    def test_arguments_must_be_an_object(self):
        with pytest.raises(AutocadError, match="must be an object"):
            plan_steps([{"tool": "autocad_draw_line", "args": [1, 2]}])

    def test_a_step_with_no_tool_is_refused(self):
        with pytest.raises(AutocadError, match="no 'tool'"):
            plan_steps([{"args": {}}])
        with pytest.raises(AutocadError, match="must be an object"):
            plan_steps(["autocad_draw_line"])

    def test_no_steps_and_too_many_steps(self):
        with pytest.raises(AutocadError, match="at least one step"):
            plan_steps([])
        with pytest.raises(AutocadError, match=str(MAX_STEPS)):
            plan_steps([{"tool": "autocad_zoom", "args": {}}] * (MAX_STEPS + 1))

    def test_arguments_may_also_be_spelled_arguments(self):
        assert plan_steps([{"tool": "autocad_draw_line", "arguments": LINE["args"]}])[0]["args"] == LINE["args"]


class TestLevelCeiling:
    @pytest.mark.parametrize("tool", sorted(n for n, lvl in RISK.items() if lvl is Risk.PUBLISH))
    def test_no_publish_tool_can_be_run_from_a_sequence(self, tool):
        with pytest.raises(AutocadError) as exc:
            plan_steps([{"tool": tool, "args": {}}])
        assert "publish tool" in str(exc.value)
        assert "Changes padlock only" in str(exc.value)

    @pytest.mark.parametrize("tool", sorted(n for n, lvl in RISK.items() if lvl is Risk.ADMIN))
    def test_no_admin_tool_can_be_run_from_a_sequence(self, tool):
        with pytest.raises(AutocadError) as exc:
            plan_steps([{"tool": tool, "args": {}}])
        assert "an admin tool" in str(exc.value)

    @pytest.mark.parametrize("tool", sorted(sequence.NOT_A_STEP))
    def test_a_step_cannot_move_the_work_to_another_drawing_or_undo(self, tool):
        # The gate checked one drawing and put its UNDO mark there; a step that switches
        # drawing (or AutoCAD), or undoes, would leave the rest of the sequence unguarded.
        assert tool in RISK
        with pytest.raises(AutocadError, match="cannot be a step"):
            plan_steps([LINE, {"tool": tool, "args": {}}, LINE])

    def test_every_tool_that_changes_the_active_drawing_is_kept_out(self):
        from autocad_mcp.core import gate

        assert gate.UNDOES <= set(sequence.NOT_A_STEP)
        assert gate.SESSION_TOOLS <= set(sequence.NOT_A_STEP)

    def test_a_sequence_cannot_contain_a_sequence(self):
        with pytest.raises(AutocadError, match="cannot contain a sequence"):
            plan_steps([{"tool": SELF, "args": {"steps": [LINE]}}])

    def test_the_allowed_levels_stop_at_change(self):
        assert set(ALLOWED) == {Risk.READ, Risk.VIEW, Risk.CHANGE}
        assert Risk.PUBLISH not in ALLOWED and Risk.ADMIN not in ALLOWED

    def test_the_sequence_itself_is_a_change_tool(self):
        assert risk_of(SELF) is Risk.CHANGE

    def test_read_and_view_steps_are_allowed(self):
        plan_steps([{"tool": "autocad_list_layers", "args": {}}, {"tool": "autocad_zoom", "args": {}}])


class TestStepBodyIsReachable:
    """A sequence calls each tool's undecorated body; if that stopped working,
    every step would re-enter the gate and deadlock."""

    @pytest.mark.parametrize("name", ["autocad_draw_line", "autocad_create_layout", "autocad_remap_layers"])
    def test_the_body_is_behind___wrapped__(self, name):
        tool = mcp._tool_manager.get_tool(name)
        body = getattr(tool.fn, "__wrapped__", None)
        assert body is not None and body is not tool.fn
        assert body.__name__ == name


# ---- a whole sequence, against a fake AutoCAD -----------------------------


class FakeEntity:
    ObjectName = "AcDbLine"
    Handle = "2F"
    Layer = "A-WALL"
    Color = 256
    Linetype = "ByLayer"
    StartPoint = (0.0, 0.0, 0.0)
    EndPoint = (100.0, 0.0, 0.0)
    Length = 100.0
    Angle = 0.0

    def __init__(self, doc):
        self.Document = doc


def xy(point):
    """A point VARIANT as [x, y].

    The real pywin32 VARIANT is not iterable: it keeps its tuple in `.value`.
    Reading it any other way passes against a stub and fails on Windows.
    """
    return [float(v) for v in getattr(point, "value", point)][:2]


class FakeSpace:
    def __init__(self, doc):
        self.doc = doc

    def AddLine(self, start, end):
        if self.doc.refuse_at is not None and len(self.doc.drawn) == self.doc.refuse_at:
            raise pythoncom.com_error("on a locked layer")
        self.doc.drawn.append((xy(start), xy(end)))
        return FakeEntity(self.doc)


class FakeLayers:
    Count = 0

    def Item(self, name):
        raise KeyError(name)

    def Add(self, name):
        return type("Layer", (), {"Name": name})()


class FakeDoc:
    def __init__(self, refuse_at=None):
        self.drawn = []
        self.open_undo_groups = 0
        self.refuse_at = refuse_at
        self.Layers = FakeLayers()

    def GetVariable(self, name):
        # UNDOCTL bit 1: undo on. Bit 8: a group is open.
        return 1 | (8 if self.open_undo_groups else 0)

    def StartUndoMark(self):
        self.open_undo_groups += 1

    def EndUndoMark(self):
        self.open_undo_groups = max(0, self.open_undo_groups - 1)

    def HandleToObject(self, handle):
        return FakeEntity(self)


@pytest.fixture
def offline(monkeypatch):
    """Route the sequence and the draw tools at a fake document, in-process."""
    fake = FakeDoc()

    async def run(fn):
        return fn()

    for module in (draw, sequence):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: fake)
    monkeypatch.setattr(draw, "require_idle", lambda doc: None)
    monkeypatch.setattr(draw, "get_space", lambda doc, space: FakeSpace(doc))
    return fake


def _run(**kwargs) -> dict:
    import asyncio

    body = sequence.autocad_sequence.__wrapped__
    return json.loads(asyncio.run(body(**kwargs)))


class TestRunning:
    STEPS = [
        {**LINE, "label": "wall base"},
        {"tool": "autocad_draw_line", "args": {"start": [0, 0], "end": [0, 50]}, "label": "wall end"},
        {"tool": "autocad_draw_line", "args": {"start": [5, 5], "end": [6, 6]}, "label": "locked"},
        {"tool": "autocad_draw_line", "args": {"start": [1, 1], "end": [2, 2]}, "label": "after"},
    ]

    def test_steps_run_in_order_and_hand_back_their_own_answers(self, offline):
        out = _run(steps=self.STEPS[:2])
        assert (out["ran"], out["failed"], out["skipped"]) == (2, 0, 0)
        assert offline.drawn == [([0.0, 0.0], [100.0, 0.0]), ([0.0, 0.0], [0.0, 50.0])]
        assert out["steps"][0]["result"]["handle"] == "2F"
        assert out["steps"][0]["label"] == "wall base"

    def test_a_failed_step_stops_the_rest_by_default(self, offline):
        offline.refuse_at = 2
        out = _run(steps=self.STEPS)
        assert (out["ran"], out["failed"], out["skipped"]) == (2, 1, 1)
        assert out["steps"][2]["ok"] is False
        assert "AutoCAD rejected" in out["steps"][2]["result"]
        assert out["steps"][3]["skipped"] is True
        assert "Stopped at step 3" in out["hint"]

    def test_stop_on_error_off_runs_them_all(self, offline):
        offline.refuse_at = 2
        out = _run(steps=self.STEPS, stop_on_error=False)
        assert out["skipped"] == 0
        assert out["ran"] + out["failed"] == 4

    def test_a_dry_run_runs_nothing(self, offline):
        out = _run(steps=self.STEPS[:2], dry_run=True)
        assert (out["ran"], out["skipped"], out["dry_run"]) == (0, 2, True)
        assert offline.drawn == []
        assert "dry_run=false" in out["hint"]
        # a dry run reports the plan without echoing the arguments back
        assert "args" not in out["steps"][0]

    def test_no_undo_group_is_left_open(self, offline):
        _run(steps=self.STEPS[:2])
        assert offline.open_undo_groups == 0

    def test_an_undo_group_left_open_by_a_step_is_closed(self, offline):
        offline.open_undo_groups = 3
        _run(steps=self.STEPS[:1])
        assert offline.open_undo_groups == 0


class TestEmergencyStop:
    """HERONSTOP between steps: not one more step runs (D-51)."""

    def test_a_stop_after_the_first_step_skips_the_rest(self, offline, monkeypatch):
        presses = iter([True])
        monkeypatch.setattr(sequence.gate, "stopped_by_modeller", lambda: next(presses, True))
        out = _run(steps=TestRunning.STEPS[:3])
        assert (out["ran"], out["skipped"]) == (1, 2)
        assert len(offline.drawn) == 1
        assert "HERONSTOP" in out["hint"] and "after step 1" in out["hint"]

    def test_no_stop_runs_them_all(self, offline, monkeypatch):
        monkeypatch.setattr(sequence.gate, "stopped_by_modeller", lambda: False)
        out = _run(steps=TestRunning.STEPS[:2])
        assert out["ran"] == 2 and "hint" not in out
