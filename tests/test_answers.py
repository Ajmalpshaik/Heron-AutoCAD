"""The one plain line every change job's answer starts with (D-62), and dry runs (D-63)."""

from __future__ import annotations

import asyncio
import inspect
import json

import test_gate
from test_gate import FakeBridge, make_tool

from autocad_mcp.core import answers, connection
from autocad_mcp.core.answers import Facts, line
from autocad_mcp.core.registry import tool_errors

env = test_gate.env  # the gate with the bridge and COM faked

COUNT = {"added": 2, "modified": 1, "erased": 0, "erased_handles": []}
NONE = {"added": 0, "modified": 0, "erased": 0, "erased_handles": []}


def call(tool, **kwargs) -> str:
    return asyncio.run(tool(**kwargs))


def word(result: str) -> str:
    first, _ = answers.split(result)
    assert first is not None, result
    return next(w for w in answers.WORDS if first == w or first.startswith(w + " - "))


# --- the line on its own -------------------------------------------------------


def test_a_counted_change_is_done_with_its_counts():
    said = line(Facts('{"handle": "2A"}', ok=True, outcome="done", counted=COUNT, wrote=True))
    assert said == "DONE - 2 added, 1 changed, 0 erased."


def test_a_job_that_wrote_nothing_changed_nothing():
    said = line(Facts('{"replaced": 0}', ok=True, outcome="done", counted=NONE, wrote=False))
    assert said.startswith("NOTHING CHANGED - ")


def test_a_preview_says_it_was_a_dry_run():
    said = line(Facts('{"dry_run": true, "hits": []}', ok=True, outcome="done", counted=NONE))
    assert said.startswith("NOTHING CHANGED - a dry run")


def test_a_write_the_plug_in_did_not_count_is_not_called_nothing():
    # A new layer or a variable is not a drawing object: the count is 0, but
    # something did change, so the line must not say NOTHING CHANGED.
    said = line(Facts('{"name": "M-DUCT"}', ok=True, outcome="done", counted=NONE, wrote=True))
    assert said.startswith("DONE - no drawing object")
    assert "not counted" in said


def test_a_tool_that_lists_every_value_and_lists_none_changed_nothing():
    text = json.dumps({"before_after": [], "modified": 0})
    assert line(Facts(text, ok=True, outcome="done", counted=NONE, wrote=True)).startswith("NOTHING CHANGED")


def test_admin_and_publish_jobs_are_never_called_nothing_changed():
    # A save, a command or a variable writes what the count cannot see.
    said = line(Facts('{"saved": true}', ok=True, outcome="done", counted=NONE, wrote=False, can_count=False))
    assert said.startswith("DONE - ")


def test_a_tool_error_with_nothing_changed_is_refused():
    said = line(Facts("Error: That layer is locked.", ok=False, outcome="failed", counted=NONE, wrote=True))
    assert said == "REFUSED - the tool turned the job down; nothing was changed."


def test_an_error_after_objects_changed_is_outcome_unknown_and_says_the_mark():
    with_mark = line(Facts("Error: boom", ok=False, outcome="failed", counted=COUNT, wrote=True, marked=True))
    assert with_mark.startswith("OUTCOME UNKNOWN - the job failed part-way, after 2 added")
    assert answers.MARK_HELD in with_mark
    without = line(Facts("Error: boom", ok=False, outcome="failed", counted=COUNT, wrote=True))
    assert answers.NO_MARK in without


def test_outcome_unknown_from_autocad_is_said():
    text = "Error: Outcome unknown: AutoCAD went busy part-way through"
    said = line(Facts(text, ok=False, outcome="unknown", counted=None, wrote=True))
    assert said.startswith("OUTCOME UNKNOWN - ")


def test_a_discard_is_nothing_changed():
    said = line(Facts("{}", ok=True, outcome="discarded", counted=COUNT, wrote=True))
    assert said.startswith("NOTHING CHANGED - the modeller chose Discard")


def test_split_and_body_give_back_the_tools_own_answer():
    text = answers.with_line('{"a": 1}', "DONE - 1 added, 0 changed, 0 erased.")
    assert answers.split(text) == ("DONE - 1 added, 0 changed, 0 erased.", '{"a": 1}')
    assert answers.body(text) == '{"a": 1}'
    assert answers.body('{"a": 1}') == '{"a": 1}'
    assert answers.body("DONE-ish text") == "DONE-ish text"  # not a line
    assert answers.with_line(["image"], "DONE - x") == ["image"]  # pictures untouched


# --- through the gate ------------------------------------------------------------


def test_every_change_answer_starts_with_its_line(env):
    FakeBridge.counted = COUNT
    draw, _ = make_tool("autocad_draw_line")
    result = call(draw)
    assert result.startswith("DONE - 2 added, 1 changed, 0 erased.\n\n")
    assert json.loads(answers.body(result))["handle"] == "2A"


def test_a_kept_job_that_changed_nothing_says_so(env):
    FakeBridge.counted = NONE
    find, _ = make_tool("autocad_find_replace_text", '{"replaced": 0, "hits": []}', writes=False)
    assert word(call(find)) == "NOTHING CHANGED"


def test_a_tool_that_turned_the_job_down_is_refused(env):
    FakeBridge.counted = NONE
    tool, _ = make_tool("autocad_modify_entity", "Error: No changes requested.", writes=False)
    assert word(call(tool)) == "REFUSED"


def test_a_padlock_refusal_is_refused(env):
    FakeBridge.refuse = "Changes is off. Nothing was sent to AutoCAD."
    tool, calls = make_tool("autocad_draw_line")
    result = call(tool)
    assert calls == []
    assert result.startswith("REFUSED - nothing was sent to AutoCAD.\n\nError: Changes is off.")


def test_reads_and_views_get_no_line(env):
    read, _ = make_tool("autocad_list_layers", "[]", writes=False)
    view, _ = make_tool("autocad_zoom", '{"zoomed": true}', writes=False)
    assert call(read) == "[]"
    assert call(view) == '{"zoomed": true}'


def test_with_the_bridge_off_there_is_no_line(env, monkeypatch):
    # Developer mode: no plug-in, so no count to answer from.
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")
    draw, _ = make_tool("autocad_draw_line")
    assert call(draw) == '{"created": true, "handle": "2A"}'


def test_a_saved_command_run_answers_with_the_same_line(env, monkeypatch):
    FakeBridge.counted = COUNT
    from autocad_mcp.tools import saved_commands, sequence

    async def report(**kwargs):
        connection.mark_writing()
        return json.dumps({"dry_run": False, "ran": 1, "failed": 0, "skipped": 0, "steps": []})

    monkeypatch.setattr(sequence.autocad_sequence, "__wrapped__", report, raising=False)
    monkeypatch.setattr(saved_commands, "load", lambda name: {"name": name, "inputs": {}, "steps": [{"tool": "draw_line"}]})
    result = asyncio.run(saved_commands.autocad_saved_command(action="run", name="pipe support"))
    assert word(result) == "DONE"
    assert json.loads(answers.body(result))["command"] == "pipe support"


def test_the_line_is_not_sent_to_the_plug_in_or_the_audit(env):
    FakeBridge.counted = NONE
    find, _ = make_tool("autocad_find_replace_text", '{"replaced": 0}', writes=False)
    call(find)
    assert [c for c in FakeBridge.calls if c[0] == "end"][-1][2:] == (True, "done")


# --- dry run for any change tool (D-63) -----------------------------------------


def test_a_dry_run_runs_reports_and_goes_back_to_the_mark(env):
    FakeBridge.counted = COUNT
    FakeBridge.ask_to_keep = True  # no question in a dry run, even with Ask to Keep on
    draw, calls = make_tool("autocad_draw_line")
    result = call(draw, dry_run=True)
    assert calls == [1]
    assert env["marks"] == 1 and env["discards"] == 1
    assert result.startswith("NOTHING CHANGED - a dry run: it would have made 2 added, 1 changed, 0 erased;")
    body = json.loads(answers.body(result))
    assert body["handle"] == "2A" and "no longer exist" in body["heron_note"]
    assert not [c for c in FakeBridge.calls if c[0] in ("ask_keep", "ask_erase")]
    begin = next(c for c in FakeBridge.calls if c[0] == "begin")
    assert begin[3].startswith("Dry run: ")  # the banner says so


def test_a_dry_run_never_passes_dry_run_to_the_tool(env):
    seen = {}

    async def autocad_draw_line(start=None) -> str:
        seen["start"] = start
        return '{"created": true, "handle": "2A"}'

    tool = tool_errors(autocad_draw_line)
    assert "dry_run" in inspect.signature(tool).parameters
    call(tool, start=[0, 0], dry_run=True)
    assert seen == {"start": [0, 0]}


def test_a_dry_run_whose_objects_stay_is_outcome_unknown(env):
    env["left"] = ["2A"]
    draw, _ = make_tool("autocad_draw_line")
    result = call(draw, dry_run=True)
    assert result.startswith("OUTCOME UNKNOWN - the dry run went back to Heron's UNDO mark, but these new objects")
    assert "2A" in result.splitlines()[0]


def test_a_dry_run_that_cannot_go_back_is_outcome_unknown(env, monkeypatch):
    async def broken():
        raise test_gate.AutocadError("AutoCAD stayed busy")

    monkeypatch.setattr(test_gate.gate, "_discard", broken)
    draw, _ = make_tool("autocad_draw_line")
    assert word(call(draw, dry_run=True)) == "OUTCOME UNKNOWN"


def test_a_dry_run_needs_undo_on_and_runs_nothing_without_it(env):
    env["undo_on"] = False
    draw, calls = make_tool("autocad_draw_line")
    result = call(draw, dry_run=True)
    assert calls == [] and env["discards"] == 0
    assert word(result) == "REFUSED" and "UNDO on" in result


def test_save_export_command_and_lisp_refuse_a_dry_run(env):
    for name in ("autocad_save_drawing", "autocad_export", "autocad_publish_pdf", "autocad_send_command",
                 "autocad_run_lisp", "autocad_set_variable", "autocad_undo_last"):  # fmt: skip
        tool, calls = make_tool(name, '{"saved": true}')
        result = call(tool, dry_run=True)
        assert calls == [], name
        assert word(result) == "REFUSED" and "dry run is not possible" in result, name
    assert env["marks"] == 0 and not any(c[0] == "begin" for c in FakeBridge.calls)


def test_a_failed_job_in_a_dry_run_is_refused_and_still_goes_back(env):
    FakeBridge.counted = NONE
    tool, _ = make_tool("autocad_modify_entity", "Error: That layer is locked.")
    result = call(tool, dry_run=True)
    assert env["discards"] == 1
    assert result.startswith("REFUSED - the job failed in the dry run; Heron went back to its UNDO mark")


def test_a_dry_run_leaves_nothing_for_undo_last(env):
    draw, _ = make_tool("autocad_draw_line")
    call(draw)
    assert test_gate.gate.last_change() is not None
    call(draw, dry_run=True)
    assert test_gate.gate.last_change() is None


def test_every_change_tool_takes_dry_run_and_the_ones_with_their_own_keep_it():
    from autocad_mcp.core.registry import GATE_DRY_RUN, mcp
    from autocad_mcp.core.risk import RISK, Risk
    from autocad_mcp.server import register_all

    register_all()
    own = {"autocad_add_revision_cloud", "autocad_remap_layers", "autocad_tidy_entities",
           "autocad_dimension_run", "autocad_add_centre_marks", "autocad_create_hatch_pattern",
           "autocad_create_linetype", "autocad_saved_command", "autocad_sequence",
           "autocad_drawing_setup", "autocad_make_shape", "autocad_set_attributes",
           "autocad_number_tags", "autocad_text_clean", "autocad_find_replace_text",
           "autocad_apply_attribute_sheet", "autocad_space_dimensions"}  # fmt: skip
    for tool in asyncio.run(mcp.list_tools()):
        level = RISK[tool.name]
        fn = mcp._tool_manager.get_tool(tool.name).fn
        if level in (Risk.READ, Risk.VIEW):
            assert "dry_run" not in tool.input_schema["properties"], tool.name
            continue
        assert "dry_run" in tool.input_schema["properties"], tool.name
        given = getattr(fn, "heron_dry_run", None) == GATE_DRY_RUN
        assert given == (tool.name not in own), tool.name


def test_a_sequence_step_cannot_be_a_dry_run_on_its_own():
    import pytest

    from autocad_mcp.core.errors import AutocadError
    from autocad_mcp.server import register_all
    from autocad_mcp.tools import sequence

    register_all()
    with pytest.raises(AutocadError, match="cannot be a dry run on its own"):
        sequence.plan_steps([{"tool": "autocad_draw_line", "args": {"start": [0, 0], "end": [1, 0], "dry_run": True}}])


# --- found in review (2026-11-21) -------------------------------------------------------


def test_a_dry_run_that_wrote_nothing_sends_no_undo_back(env):
    FakeBridge.counted = NONE
    tool, _ = make_tool("autocad_modify_entity", "Error: AutoCAD is in the middle of a command.", writes=False)
    result = call(tool, dry_run=True)
    assert env["marks"] == 1 and env["discards"] == 0
    assert result.startswith("REFUSED - the job failed in the dry run before it wrote anything.")
    quiet, _ = make_tool("autocad_modify_entity", '{"modified": 0, "before_after": []}', writes=False)
    assert call(quiet, dry_run=True).startswith("NOTHING CHANGED - a dry run that wrote nothing")
    assert env["discards"] == 0


def test_a_cancelled_dry_run_still_goes_back_to_its_mark(env):
    import pytest

    tool, _ = make_tool("autocad_draw_line", raises=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        call(tool, dry_run=True)
    assert env["marks"] == 1 and env["discards"] == 1


def test_no_mark_is_put_down_while_autocad_is_in_a_command(monkeypatch):
    from autocad_mcp.core import gate

    class Doc:
        sent: list[str] = []

        def GetVariable(self, name):
            return {"UNDOCTL": 5, "CMDACTIVE": 1}[name]

        def SendCommand(self, text):
            Doc.sent.append(text)

    class App:
        ActiveDocument = Doc()

    async def now(fn):
        return fn()

    monkeypatch.setattr(gate, "get_app", App)
    monkeypatch.setattr(gate, "run", now)
    assert asyncio.run(gate._mark()) is False and Doc.sent == []
