"""The one plain line every change job's answer starts with (D-62), and dry runs (D-63)."""

from __future__ import annotations

import asyncio
import json

import test_gate
from test_gate import FakeBridge, make_tool

from autocad_mcp.core import answers, connection
from autocad_mcp.core.answers import Facts, line

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
