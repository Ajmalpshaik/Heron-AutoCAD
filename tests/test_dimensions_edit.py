"""Dimension space and dimension break (#116, D-80), no AutoCAD.

The spacing arithmetic is plain functions; the tools are checked up to the
pipe: what they ask the plug-in for, and what they type for DIMBREAK.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, dimensions_edit
from autocad_mcp.tools.dimensions_edit import dimbreak_command, plan_spacing


def dim(handle, y=None, direction=(1.0, 0.0), point=None):
    return {"handle": handle, "direction": list(direction), "line_point": point or [1000.0, y, 0.0]}


def new_y(plan):
    return {m["handle"]: round(m["to"][1], 6) for m in plan["moves"]}


class TestSpacing:
    def test_a_stack_is_put_at_one_two_three_spacings_off_the_base(self):
        plan = plan_spacing([dim("A", 500), dim("B", 900), dim("C", 1500), dim("D", 700)], 400)
        # Out from the base in the order they were: D (200 off), B (400), C (1000).
        assert new_y(plan) == {"D": 900.0, "B": 1300.0, "C": 1700.0}
        assert plan["base"] == "A" and plan["already"] == [] and plan["skipped"] == []

    def test_the_base_never_moves(self):
        plan = plan_spacing([dim("A", 500), dim("B", 600)], 400)
        assert "A" not in new_y(plan)

    def test_each_dimension_keeps_its_side_of_the_base(self):
        plan = plan_spacing([dim("A", 500), dim("B", 650), dim("C", 450), dim("E", 100)], 300)
        # Above: B at +300. Below, in order out: C (-50) then E (-400) at -300 and -600.
        assert new_y(plan) == {"B": 800.0, "C": 200.0, "E": -100.0}

    def test_one_already_in_place_is_not_written(self):
        plan = plan_spacing([dim("A", 500), dim("B", 900), dim("C", 1000)], 400)
        assert plan["already"] == ["B"] and new_y(plan) == {"C": 1300.0}

    def test_spacing_zero_lines_them_all_up_on_the_base(self):
        plan = plan_spacing([dim("A", 500), dim("B", 900), dim("C", 50)], 0)
        assert new_y(plan) == {"B": 500.0, "C": 500.0}

    def test_only_the_dimension_line_moves_along_its_normal(self):
        plan = plan_spacing([dim("A", 500), dim("B", 700)], 400)
        move = plan["moves"][0]
        assert move["to"][0] == pytest.approx(1000.0) and move["to"][2] == 0.0
        assert move["offset_was"] == 200.0 and move["offset_now"] == 400.0

    def test_vertical_dimensions_move_in_x(self):
        stack = [dim("A", direction=(0, 1), point=[300.0, 0.0, 0.0]),
                 dim("B", direction=(0, -1), point=[100.0, 50.0, 0.0])]
        plan = plan_spacing(stack, 500)
        # Direction (0, 1): its normal points to -X, so B is 200 out on that side.
        assert plan["moves"][0]["to"][:2] == pytest.approx([-200.0, 50.0])

    def test_a_sloping_aligned_stack_moves_perpendicular_to_its_slope(self):
        u = (0.6, 0.8)
        stack = [dim("A", direction=u, point=[0.0, 0.0, 0.0]), dim("B", direction=u, point=[-80.0, 60.0, 0.0])]
        plan = plan_spacing(stack, 250)  # B is 100 off along (-0.8, 0.6)
        assert plan["moves"][0]["to"][:2] == pytest.approx([-200.0, 150.0])

    def test_one_that_is_not_parallel_is_left_and_named(self):
        plan = plan_spacing([dim("A", 500), dim("B", 900, direction=(0.7, 0.7))], 400)
        assert plan["moves"] == [] and plan["skipped"][0]["handle"] == "B"
        assert "not parallel" in plan["skipped"][0]["why"]

    def test_the_base_can_be_named(self):
        plan = plan_spacing([dim("A", 500), dim("B", 900), dim("C", 1000)], 400, base="b")
        # A is already one spacing below B; C goes to one spacing above.
        assert plan["base"] == "B" and new_y(plan) == {"C": 1300.0} and plan["already"] == ["A"]

    @pytest.mark.parametrize(
        ("stack", "spacing", "base", "match"),
        [
            ([dim("A", 0)], 400, None, "at least one more"),
            ([dim("A", 0), dim("B", 9)], -1, None, "negative"),
            ([dim("A", 0), dim("B", 9)], 400, "C", "not one of"),
            ([dim("A", 0), dim("a", 9)], 400, None, "twice"),
            ([dim("A", 0, direction=(0, 0)), dim("B", 9)], 400, None, "no direction"),
        ],
    )
    def test_refusals(self, stack, spacing, base, match):
        with pytest.raises(ValueError, match=match):
            plan_spacing(stack, spacing, base)


class TestDimbreakLine:
    def test_multiple_each_by_handle_then_break(self):
        assert dimbreak_command(["2A", "2B"]) == '_.DIMBREAK\n_M\n(handent "2A")\n(handent "2B")\n\n_B\n'

    def test_remove_takes_the_breaks_off(self):
        assert dimbreak_command(["2A"], remove=True).endswith("\n\n_R\n")

    def test_a_handle_given_twice_is_picked_once(self):
        assert dimbreak_command(["2a", "2A"]).count("handent") == 1

    @pytest.mark.parametrize("bad", ['2A")(command "ERASE"', "", "XYZ", "2A 2B"])
    def test_nothing_but_a_handle_reaches_the_command_line(self, bad):
        with pytest.raises(ValueError):
            dimbreak_command([bad])


# ---------------------------------------------------------------------------
# The tools, up to the pipe
# ---------------------------------------------------------------------------


class FakePlugin:
    def __init__(self):
        self.calls: list = []
        self.lines: list = []
        self.skipped: list = []

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        if operation == "dimension_lines":
            return {"dimensions": self.lines, "skipped": self.skipped}
        if operation == "move_dimension_lines":
            return {"moved": len(args["moves"]), "handles": [m["handle"] for m in args["moves"]]}
        raise AssertionError(operation)


class Entity:
    def __init__(self, handle, name="AcDbRotatedDimension", owner=1):
        self.Handle, self.ObjectName, self.OwnerID = handle, name, owner


class Space:
    ObjectID = 1


class Doc:
    def __init__(self, entities=(), stuck=False):
        self.entities = {e.Handle.upper(): e for e in entities}
        self.typed: list[str] = []
        self.stuck = stuck
        self.ActiveSpace = 1
        self.ModelSpace = Space()
        self.PaperSpace = type("Paper", (), {"ObjectID": 2})()

    def HandleToObject(self, handle):  # noqa: N802 - COM name
        return self.entities[handle.upper()]

    def SendCommand(self, text):  # noqa: N802 - COM name
        self.typed.append(text)

    def GetVariable(self, name):  # noqa: N802 - COM name
        assert name == "CMDACTIVE"
        return 1 if self.stuck else 0

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass


@pytest.fixture
def plugin(monkeypatch):
    fake = FakePlugin()
    holder = {"doc": Doc()}

    async def run(fn):
        return fn()

    monkeypatch.setattr(dimensions_edit, "run", run)
    monkeypatch.setattr(dimensions_edit, "get_doc", lambda: holder["doc"])
    monkeypatch.setattr(dimensions_edit, "require_idle", lambda d: None)
    monkeypatch.setattr(dimensions_edit, "COMMAND_WAIT_S", 0.0)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    fake.holder = holder
    return fake


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


class TestSpaceTool:
    def test_it_reads_the_lines_then_moves_only_those_that_need_it(self, plugin):
        plugin.lines = [dim("2A", 500), dim("2B", 900), dim("2C", 1000)]
        out = call(dimensions_edit.autocad_space_dimensions(handles=["2A", "2B", "2C"], spacing=400))
        assert plugin.calls[0] == ("dimension_lines", {"handles": ["2A", "2B", "2C"]})
        operation, args = plugin.calls[1]
        assert operation == "move_dimension_lines"
        assert [m["handle"] for m in args["moves"]] == ["2C"]
        assert args["moves"][0]["to"][1] == pytest.approx(1300.0)
        assert out["moved"] == 1 and out["already"] == ["2B"]
        assert out["before_after"][0]["property"] == "dimension line"

    def test_a_dry_run_reads_and_moves_nothing(self, plugin):
        plugin.lines = [dim("2A", 500), dim("2B", 700)]
        out = call(dimensions_edit.autocad_space_dimensions(handles=["2A", "2B"], spacing=400, dry_run=True))
        assert [c[0] for c in plugin.calls] == ["dimension_lines"]
        assert out["dry_run"] is True and out["moves"][0]["offset_now"] == 400.0

    def test_nothing_to_move_writes_nothing(self, plugin):
        plugin.lines = [dim("2A", 500), dim("2B", 900)]
        out = call(dimensions_edit.autocad_space_dimensions(handles=["2A", "2B"], spacing=400))
        assert [c[0] for c in plugin.calls] == ["dimension_lines"] and out["moved"] == 0

    def test_what_the_plug_in_could_not_read_is_listed_as_skipped(self, plugin):
        plugin.lines = [dim("2A", 500), dim("2B", 700)]
        plugin.skipped = [{"handle": "2D", "why": "only linear and aligned dimensions are spaced"}]
        out = call(dimensions_edit.autocad_space_dimensions(handles=["2A", "2B", "2D"], spacing=400))
        assert out["skipped"][0]["handle"] == "2D"

    def test_a_base_that_cannot_be_spaced_moves_nothing(self, plugin):
        plugin.lines = [dim("2B", 700)]
        plugin.skipped = [{"handle": "2A", "why": "it is a circle, not a dimension"}]
        text = error(dimensions_edit.autocad_space_dimensions(handles=["2A", "2B"], spacing=400))
        assert "2A" in text and "circle" in text and "Nothing was moved" in text
        assert [c[0] for c in plugin.calls] == ["dimension_lines"]

    def test_a_base_not_in_the_list_is_refused_before_anything_is_read(self, plugin):
        text = error(dimensions_edit.autocad_space_dimensions(handles=["2A", "2B"], spacing=400, base="2C"))
        assert "2C" in text and plugin.calls == []

    def test_without_the_plug_in_it_says_why(self, plugin, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        text = error(dimensions_edit.autocad_space_dimensions(handles=["2A", "2B"], spacing=400))
        assert "plug-in" in text


class TestBreakTool:
    def test_it_types_dimbreak_for_the_dimensions(self, plugin):
        plugin.holder["doc"] = Doc([Entity("2A"), Entity("2B", "AcDbAlignedDimension")])
        out = call(dimensions_edit.autocad_break_dimensions(handles=["2A", "2B"]))
        assert plugin.holder["doc"].typed == ['_.DIMBREAK\n_M\n(handent "2A")\n(handent "2B")\n\n_B\n']
        assert out["broken"] == ["2A", "2B"] and out["space"] == "model"

    def test_remove(self, plugin):
        plugin.holder["doc"] = Doc([Entity("2A")])
        out = call(dimensions_edit.autocad_break_dimensions(handles=["2A"], remove=True))
        assert out["unbroken"] == ["2A"] and plugin.holder["doc"].typed[0].endswith("_R\n")

    def test_something_that_is_not_a_dimension_types_nothing(self, plugin):
        plugin.holder["doc"] = Doc([Entity("2A"), Entity("2B", "AcDbLine")])
        text = error(dimensions_edit.autocad_break_dimensions(handles=["2A", "2B"]))
        assert "2B" in text and "not a dimension" in text and plugin.holder["doc"].typed == []

    def test_a_dimension_in_another_space_types_nothing(self, plugin):
        plugin.holder["doc"] = Doc([Entity("2A", owner=2)])
        text = error(dimensions_edit.autocad_break_dimensions(handles=["2A"]))
        assert "model space" in text and plugin.holder["doc"].typed == []

    def test_a_command_left_asking_is_cancelled_and_said(self, plugin):
        plugin.holder["doc"] = Doc([Entity("2A")], stuck=True)
        text = error(dimensions_edit.autocad_break_dimensions(handles=["2A"]))
        assert "cancelled" in text and plugin.holder["doc"].typed[-1] == "\x1b\x1b"

    def test_a_bad_handle_is_refused_before_autocad_is_touched(self, plugin):
        text = error(dimensions_edit.autocad_break_dimensions(handles=['2A")(command "ERASE"']))
        assert "not a handle" in text and plugin.holder["doc"].typed == []


def test_levels():
    assert risk_of("autocad_space_dimensions") is Risk.CHANGE
    assert risk_of("autocad_break_dimensions") is Risk.CHANGE
