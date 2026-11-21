"""quiet=true: counts and handles only (#44).

On 2026-11-09 an autocad_sequence of eight autocad_dimension_run steps answered
with about 15,000 characters of per-dimension detail. With quiet the same
sequence answers with the counts and the handles, and what failed.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core import gate
from autocad_mcp.core.quiet import LEFT_OUT, MOST_FAILURES, MOST_TEXT, quiet, quiet_text
from autocad_mcp.tools import batch, dimensions, sequence

RUN = {
    "mode": "chain",
    "axis": "horizontal",
    "count": 3,
    "created": 3,
    "handles": ["2A1", "2A2", "2A3"],
    "dimensions": [
        {"kind": "chain", "row": 0, "point1": [0, 0], "point2": [3000, 0], "text_position": [1500, 500],
         "expected": 3000.0, "measured": 3000.0, "handle": h}
        for h in ("2A1", "2A2", "2A3")
    ],
    "total": 9000.0,
    "failed": [{"index": i, "kind": "chain", "reason": "locked layer"} for i in range(7)],
    "dim_scale": 50.0,
    "warning": "1 dimension(s) measure something other than the span asked for.",
}


class TestQuiet:
    def test_counts_handles_and_words_stay_the_detail_goes(self):
        out = quiet(RUN)
        assert out["count"] == 3 and out["created"] == 3 and out["total"] == 9000.0
        assert out["handles"] == ["2A1", "2A2", "2A3"]
        assert out["mode"] == "chain" and out["warning"] == RUN["warning"]
        assert "dimensions" not in out
        assert out[LEFT_OUT]["dimensions"] == 3

    def test_what_failed_is_still_named_its_first_few(self):
        out = quiet(RUN)
        assert len(out["failed"]) == MOST_FAILURES
        assert out["failed"][0]["reason"] == "locked layer"
        assert out[LEFT_OUT]["failed"] == 7

    def test_handles_of_a_list_left_out_are_kept_when_the_answer_had_none(self):
        out = quiet({"count": 2, "items": [{"handle": "1F", "layer": "A"}, {"handle": "20", "layer": "B"}]})
        assert out["handles"] == ["1F", "20"]
        assert "items" not in out

    def test_handles_already_given_are_never_mixed_with_others(self):
        # Centre marks: "handles" are the marks made, "circles" the circles marked. Mixing them
        # would have Discard look for the circles as if they were new.
        out = quiet({"created": 4, "handles": ["M1", "M2"], "circles": [{"handle": "C1", "radius": 5}]})
        assert out["handles"] == ["M1", "M2"]

    def test_what_a_call_created_keeps_its_handle_so_discard_still_finds_it(self):
        made = {"parts": [{"created": True, "handle": "3B", "type": "line", "start": [0, 0]},
                          {"created": True, "handle": "3C", "type": "line", "start": [1, 0]}]}
        out = quiet(made)
        assert out["parts"] == [{"created": True, "handle": "3B"}, {"created": True, "handle": "3C"}]
        assert gate._created(json.dumps(out)) == gate._created(json.dumps(made)) == ["3B", "3C"]

    def test_short_plain_lists_stay(self):
        out = quiet({"layers_created": ["A-DIMS"], "origin": [0.0, 0.0, 0.0]})
        assert out == {"layers_created": ["A-DIMS"], "origin": [0.0, 0.0, 0.0]}

    def test_passing_it_through_twice_changes_nothing(self):
        once = quiet(RUN)
        assert quiet(once) == once
        made = quiet({"parts": [{"created": True, "handle": "3B", "x": 1}] * 3})
        assert quiet(made) == made

    def test_anything_but_an_object_comes_back_as_it_is(self):
        assert quiet("Error: no") == "Error: no"
        assert quiet([1, 2]) == [1, 2]

    def test_a_long_text_answer_is_cut_an_error_never(self):
        long = "| handle | layer |\n" * 100
        assert len(quiet_text(long)) < len(long)
        assert quiet_text(long).startswith(long[:MOST_TEXT])
        error = "Error: " + "x" * 1000
        assert quiet_text(error) == error


# --- the tools -----------------------------------------------------------------------


class Dim:
    count = 0

    def __init__(self):
        Dim.count += 1
        self.Handle = f"D{Dim.count}"
        self.Measurement = 3000.0


class Space:
    def AddDimRotated(self, p1, p2, text, angle):
        return Dim()

    def AddDimAligned(self, p1, p2, text):
        return Dim()


class Doc:
    ModelSpace = PaperSpace = Space()

    def GetVariable(self, name):
        return {"UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0),
                "DIMSCALE": 1.0, "UNDOCTL": 1}[name]

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def offline(monkeypatch):
    async def run(fn):
        return fn()

    for module in (dimensions, sequence):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: Doc())
    monkeypatch.setattr(dimensions, "require_idle", lambda d: None)


GRID = [[0, 0], [3000, 0], [7500, 0], [12000, 0], [15000, 0]]


def dimension_run(**kwargs) -> dict:
    return json.loads(asyncio.run(dimensions.autocad_dimension_run(points=GRID, offset=500, **kwargs)))


class TestDimensionRun:
    def test_quiet_keeps_the_counts_and_the_handles(self, offline):
        loud, hushed = dimension_run(), dimension_run(quiet=True)
        assert hushed["count"] == loud["count"] == 4
        assert len(hushed["handles"]) == 4
        assert "dimensions" not in hushed and hushed[LEFT_OUT] == {"dimensions": 4}
        assert len(json.dumps(hushed)) < len(json.dumps(loud)) / 2

    def test_left_alone_the_answer_is_as_before(self, offline):
        assert len(dimension_run()["dimensions"]) == 4

    def test_a_quiet_dry_run_counts_what_it_would_lay_out(self, offline):
        out = dimension_run(quiet=True, dry_run=True)
        assert out["dry_run"] is True and out["count"] == 4
        assert "dimensions" not in out


class TestSequence:
    STEP = {"tool": "autocad_dimension_run", "args": {"points": GRID, "offset": 500, "include_overall": True}}

    def run(self, **kwargs) -> dict:
        body = sequence.autocad_sequence.__wrapped__
        return json.loads(asyncio.run(body(steps=[self.STEP] * 8, **kwargs)))

    def test_eight_dimension_runs_answer_with_counts_and_handles(self, offline):
        loud, hushed = self.run(), self.run(quiet=True)
        assert hushed["ran"] == loud["ran"] == 8
        for step in hushed["steps"]:
            assert step["ok"] is True
            assert step["result"]["count"] == 5
            assert len(step["result"]["handles"]) == 5
            assert "dimensions" not in step["result"]
        assert len(json.dumps(hushed)) < len(json.dumps(loud)) / 2

    def test_a_failed_step_keeps_its_whole_error(self, offline):
        bad = {"tool": "autocad_dimension_run", "args": {"points": [[0, 0]], "offset": 500}}
        body = sequence.autocad_sequence.__wrapped__
        out = json.loads(asyncio.run(body(steps=[bad], quiet=True)))
        assert out["steps"][0]["ok"] is False
        assert str(out["steps"][0]["result"]).startswith("Error:")


def test_batch_quiet_names_the_ucs_instead_of_describing_it(monkeypatch):
    async def draw(operations, return_handles, coords):
        return {"created": 2, "failed": 0, "requested": 2, "handles": ["A", "B"], "completed": True,
                "layers_created": [], "converted_from_ucs": {"name": "GRID-B", "origin": [1.0, 2.0, 0.0]}}

    monkeypatch.setattr(batch, "draw_operations", draw)
    body = batch.autocad_batch_draw.__wrapped__
    out = json.loads(asyncio.run(body(operations=[{"type": "point", "position": [0, 0]}], quiet=True)))
    assert out["converted_from_ucs"] == "GRID-B"
    assert out["handles"] == ["A", "B"] and out["created"] == 2


@pytest.mark.parametrize("tool", ["autocad_sequence", "autocad_batch_draw", "autocad_dimension_run",
                                  "autocad_add_centre_marks"])
def test_the_long_answer_tools_offer_quiet(tool):
    from autocad_mcp.core.registry import mcp

    props = mcp._tool_manager.get_tool(tool).fn_metadata.arg_model.model_json_schema()["properties"]
    assert "quiet" in props and props["quiet"]["default"] is False


def test_every_list_of_handles_stays_whatever_it_is_called():
    # A copy or an array answers with new_handles (review of PR #149).
    copies = [f"C{i}" for i in range(12)]
    out = quiet({"copied": 12, "handles": ["A"], "new_handles": copies, "missing_handles": ["Z"]})
    assert out["new_handles"] == copies and out["missing_handles"] == ["Z"]
    assert LEFT_OUT not in out
