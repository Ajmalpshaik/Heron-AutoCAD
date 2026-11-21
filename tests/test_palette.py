"""The Heron palette's Run (D-68): one saved command through the gate, from a request file. No AutoCAD."""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp import palette, server
from autocad_mcp.core import sessions
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import document, register_all, saved_commands

register_all()

REPORT = {"dry_run": False, "ran": 2, "failed": 0, "skipped": 0,
          "steps": [{"index": 1, "ok": True}, {"index": 2, "ok": True}]}  # fmt: skip


@pytest.fixture
def fake(monkeypatch):
    seen: dict = {"calls": [], "released": []}

    async def status():
        seen["calls"].append("status")
        return seen.get("status", json.dumps({"units": "mm", "heron": {"connected": True}}))

    async def saved_command(action, name, inputs):
        seen["calls"].append(("run", action, name, inputs))
        return seen.get("result", json.dumps(REPORT))

    class FakeBridge:
        def __init__(self, pid):
            self.pid = pid

        def call(self, op):
            seen["released"].append((self.pid, op))

    monkeypatch.setattr(document, "autocad_status", status)
    monkeypatch.setattr(saved_commands, "autocad_saved_command", saved_command)
    monkeypatch.setattr(palette, "Bridge", FakeBridge)
    monkeypatch.setattr(sessions, "choose", lambda pid: seen["calls"].append(("choose", pid)) or {"pid": pid})
    return seen


def test_the_palette_calls_the_gated_tools_never_their_bodies():
    # tool_errors wraps every tool in the gate (functools.wraps leaves __wrapped__);
    # run_saved calls these names, so the gate, padlocks and Keep or Discard apply.
    assert hasattr(document.autocad_status, "__wrapped__")
    assert hasattr(saved_commands.autocad_saved_command, "__wrapped__")


def test_status_comes_first_then_the_command_in_that_autocad_then_it_is_freed(fake):
    answer = asyncio.run(palette.run_saved({"name": "Plinth", "inputs": {"width": 1500}}, 4242))
    assert fake["calls"] == [("choose", 4242), "status", ("run", "run", "Plinth", {"width": 1500})]
    assert fake["released"] == [(4242, "release")]
    assert answer == {"ok": True, "message": "Done: 'Plinth', 2 of 2 step(s)."}


def test_not_connected_runs_nothing_and_says_press_heron(fake):
    fake["status"] = json.dumps({"heron": {"connected": False, "message": "Press Heron. Nothing was sent to AutoCAD."}})
    answer = asyncio.run(palette.run_saved({"name": "Plinth", "inputs": {}}, 4242))
    assert answer == {"ok": False, "message": "Press Heron. Nothing was sent to AutoCAD."}
    assert ("run", "run", "Plinth", {}) not in fake["calls"]
    assert fake["released"] == [(4242, "release")]


def test_an_autocad_that_is_not_connected_by_pid_is_refused_before_anything(fake, monkeypatch):
    def choose(pid):
        raise AutocadError("No AutoCAD connected to Heron has process 4242.")

    monkeypatch.setattr(sessions, "choose", choose)
    answer = asyncio.run(palette.run_saved({"name": "Plinth"}, 4242))
    assert answer == {"ok": False, "message": "No AutoCAD connected to Heron has process 4242."}
    assert fake["calls"] == []


def test_a_refusal_from_the_gate_is_passed_on_in_its_own_words(fake):
    fake["result"] = "Error: Changes is off, so Heron may not change this drawing. Nothing was sent to AutoCAD."
    answer = asyncio.run(palette.run_saved({"name": "Plinth"}, 4242))
    assert answer == {"ok": False, "message": "Changes is off, so Heron may not change this drawing. Nothing was sent to AutoCAD."}


@pytest.mark.parametrize("request_", [{}, {"name": "  "}, {"name": "Plinth", "inputs": [1]}])
def test_a_request_without_a_name_or_with_bad_inputs_sends_nothing(fake, request_):
    answer = asyncio.run(palette.run_saved(request_, 4242))
    assert answer["ok"] is False and "Nothing was sent to AutoCAD." in answer["message"]
    assert fake["calls"] == []


def test_a_failed_step_is_named_with_its_error():
    report = {"ran": 1, "failed": 1, "skipped": 1, "hint": "Stopped at step 2.",
              "steps": [{"index": 1, "ok": True}, {"index": 2, "ok": False, "label": "plinth", "result": "Error: layer locked"},
                        {"index": 3, "ok": None, "skipped": True}]}  # fmt: skip
    answer = palette.outcome("Plinth", json.dumps(report))
    assert answer == {"ok": False, "message": "'Plinth' stopped at step 2 (plinth): layer locked Stopped at step 2."}


def test_a_discard_and_a_note_are_said_plainly():
    assert palette.outcome("Plinth", "Discarded: nothing was kept.") == {"ok": False, "message": "Discarded: nothing was kept."}
    noted = palette.outcome("Plinth", json.dumps({**REPORT, "heron_note": "The modeller kept them erased."}))
    assert noted["message"] == "Done: 'Plinth', 2 of 2 step(s). The modeller kept them erased."


def test_main_reads_the_request_file_and_prints_one_json_line(fake, tmp_path, capsys):
    request = tmp_path / "run.json"
    request.write_text(json.dumps({"name": "Plinth", "inputs": {}}), encoding="utf-8")
    assert palette.main(str(request), 4242) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["ok"] is True
    assert palette.main(str(tmp_path / "missing.json"), 4242) == 1
    assert "could not read" in json.loads(capsys.readouterr().out.strip())["message"]


def test_every_server_says_where_it_runs_from(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    palette.write_server_file()
    written = json.loads((tmp_path / "Heron" / "autocad" / "server.json").read_text(encoding="utf-8"))
    assert written["python"] and written["version"]


def test_the_command_line_takes_the_palettes_request():
    args = server.build_parser().parse_args(["--run-saved", "r.json", "--acad-pid", "4242"])
    assert (args.run_saved, args.acad_pid) == ("r.json", 4242)
    assert server.build_parser().parse_args([]).run_saved is None


def test_the_gates_plain_line_first_is_read_not_shown_as_the_answer():
    # D-62: every change answer starts with DONE / NOTHING CHANGED / REFUSED / OUTCOME UNKNOWN.
    done = palette.outcome("Plinth", "DONE - 2 objects added.\n\n" + json.dumps(REPORT))
    assert done == {"ok": True, "message": "Done: 'Plinth', 2 of 2 step(s)."}
    refused = palette.outcome("Plinth", "REFUSED - nothing was sent to AutoCAD.\n\nError: Changes is off. Nothing was sent to AutoCAD.")
    assert refused == {"ok": False, "message": "Changes is off. Nothing was sent to AutoCAD."}
    discarded = palette.outcome("Plinth", "NOTHING CHANGED - the modeller chose Discard.\n\nDiscarded: nothing was kept.")
    assert discarded == {"ok": False, "message": "Discarded: nothing was kept."}
    unknown = palette.outcome("Plinth", "OUTCOME UNKNOWN - look at the drawing.\n\nError: Outcome unknown: AutoCAD went busy.")
    assert unknown["ok"] is False and unknown["message"].startswith("Outcome unknown: look at the drawing.")
