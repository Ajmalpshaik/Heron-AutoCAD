"""autocad_why, autocad_gaps and the audit folder (issues #88, #89, #43; D-67). No AutoCAD.

autocad_why says why one job cannot run - no tool, a padlock off, nothing
connected, an old plug-in - from Heron's own files, so it must answer with
AutoCAD closed. autocad_gaps sums up the audit log without ever showing a
drawing's folders or contents. Both are read tools the gate lets through
without looking at AutoCAD.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autocad_mcp.acad import why
from autocad_mcp.core import audit, diagnose, gate
from autocad_mcp.core.registry import mcp
from autocad_mcp.core.risk import RISK, Risk, risk_of
from autocad_mcp.tools import explain, register_all, resources

register_all()

TOOLS = asyncio.run(mcp.list_tools())
ENTRIES = asyncio.run(resources._entries())
DESCRIPTIONS = {tool.name: tool.description or "" for tool in TOOLS}


def report(*, installed="1.5.0", connected=(), checks=()):
    """A diagnose.report() as the PC would give it. It has no padlocks: they live inside AutoCAD (D-59)."""
    return {
        "plugin_installed": installed,
        "autocads_connected": [
            {"pid": pid, "acad_version": "25.1", "plugin_version": plugin, "protocol_version": 1}
            for pid, plugin in connected
        ],
        "checks": list(checks),
    }


def explain_job(job, **overrides):
    args = {
        "entries": ENTRIES,
        "level_of": lambda tool: RISK.get(tool, Risk.ADMIN),
        "descriptions": DESCRIPTIONS,
        "known_tools": set(RISK),
        "report": report(connected=[(4242, "1.5.0")]),
        "bridge_on": True,
        "chosen_pid": None,
        "drawing_checked": True,
    }
    args.update(overrides)
    return why.explain(job, **args)


def reasons(answer):
    return [r["reason"] for r in answer["reasons"]]


class TestWhy:
    def test_nothing_in_the_way_says_it_should_run(self):
        answer = explain_job("draw a 200 flange with 8 bolt holes")
        assert answer["can_run"] is True
        assert answer["tool"]["tool"] == "autocad_make_shape"
        assert "should run" in answer["verdict"]

    def test_the_wrapping_words_are_not_the_job(self):
        assert why.the_job("why can't you save this as PDF?") == "save this as PDF"
        assert why.the_job("Why won't Heron draw the duct") == "draw the duct"
        assert why.the_job("draw the duct") == "draw the duct"

    def test_no_tool_for_it(self):
        answer = explain_job("qqqq zzzz")
        assert answer["can_run"] is False
        assert reasons(answer) == ["no_tool"]
        assert answer["tool"] is None
        assert "by hand" in answer["reasons"][0]["what_to_do"]

    def test_a_read_only_server_is_named_when_nothing_is_found(self):
        answer = explain_job("qqqq zzzz", known_tools=set(RISK) | {"autocad_draw_line_removed"})
        assert "read_only_server" in reasons(answer)

    def test_the_padlocks_a_job_needs_are_named_never_guessed(self):
        """D-59: the padlocks live inside AutoCAD, so Heron names them but cannot say they are off."""
        answer = explain_job("why can't you save this as PDF")
        assert answer["tool"]["tool"] in {"autocad_export", "autocad_publish_pdf"}
        assert {"needs_changes", "needs_publish"} <= set(reasons(answer))
        assert "needs_admin" not in reasons(answer)
        named = next(r for r in answer["reasons"] if r["reason"] == "needs_publish")
        assert named["blocks"] is False
        assert "cannot see" in named["says"] and "is off" not in named["says"]
        assert "HERONPUBLISH" in named["what_to_do"]
        assert answer["can_run"] is True  # nothing Heron can see is in the way
        assert "padlock" in answer["cannot_see"]

    def test_an_admin_job_names_changes_and_admin(self):
        answer = explain_job("run this autolisp")
        assert answer["tool"]["tool"] == "autocad_run_lisp"
        assert {"needs_changes", "needs_admin"} <= set(reasons(answer))
        assert answer["tool"]["needs"] == ["Changes", "Admin"]

    def test_the_real_install_report_has_no_padlocks_to_misread(self, tmp_path, monkeypatch):
        """The report why reads is diagnose's own; it must never make a padlock look off."""
        monkeypatch.setattr(diagnose, "_alive", lambda pid: False)
        real = diagnose.report(plugins=tmp_path / "p", bridges=tmp_path / "b", package=tmp_path)
        assert "padlocks" not in real
        answer = explain_job("draw a line", report=real)
        assert not any(r["reason"].endswith("_off") for r in answer["reasons"])

    def test_a_reading_job_needs_no_padlock(self):
        answer = explain_job("how many diffusers on this floor", report=report(connected=[(4242, "1.5.0")]))
        assert answer["can_run"] is True
        assert answer["tool"]["needs"] == []

    def test_nothing_connected_comes_before_the_padlocks(self):
        answer = explain_job("draw a line from 0,0 to 100,0", report=report(connected=()))
        assert answer["can_run"] is False
        assert reasons(answer)[0] == "not_connected"
        assert "Heron button" in answer["verdict"]

    def test_the_plug_in_not_installed(self):
        answer = explain_job("draw a line", report=report(installed=None, connected=()))
        assert reasons(answer)[:2] == ["plugin_not_installed", "not_connected"]
        assert "Install.bat" in answer["reasons"][0]["what_to_do"]

    def test_two_autocads_and_none_picked(self):
        answer = explain_job("draw a line", report=report(connected=[(1, "1.5.0"), (2, "1.5.0")]))
        assert "which_autocad" in reasons(answer)
        assert "which_autocad" not in reasons(explain_job(
            "draw a line", report=report(connected=[(1, "1.5.0"), (2, "1.5.0")]), chosen_pid=2))

    def test_a_plug_in_older_than_the_tool_needs(self):
        answer = explain_job("undo what you just did", report=report(connected=[(4242, "1.4.2")]))
        assert answer["tool"]["tool"] == "autocad_undo_last"
        assert answer["tool"]["needs_plugin"] == "1.5.0"
        assert "old_plugin" in reasons(answer)
        assert "old_plugin" not in reasons(explain_job(
            "undo what you just did", report=report(connected=[(4242, "1.5.0")])))

    def test_the_version_each_tool_needs_comes_from_its_own_docstring(self):
        assert why.needs_plugin(DESCRIPTIONS["autocad_add_light"]) == "1.4.0"
        assert why.needs_plugin(DESCRIPTIONS["autocad_undo_last"]) == "1.5.0"
        assert why.needs_plugin(DESCRIPTIONS["autocad_draw_line"]) is None

    def test_server_and_plug_in_from_different_releases(self):
        mismatch = {"check": "server and plug-in match", "state": "FAIL", "detail": "protocol 2 against 1."}
        answer = explain_job("draw a line", report=report(connected=[(4242, "1.5.0")], checks=[mismatch]))
        assert "versions_do_not_match" in reasons(answer) and answer["can_run"] is False

    def test_an_update_waiting_is_said_but_does_not_block(self):
        waiting = {"check": "server up to date", "state": "WARN", "detail": "files changed."}
        answer = explain_job("how many diffusers", report=report(connected=[(4242, "1.5.0")], checks=[waiting]))
        assert "update_waiting" in reasons(answer) and answer["can_run"] is True

    def test_a_change_before_any_status_says_status_comes_first(self):
        answer = explain_job("draw a line", drawing_checked=False)
        assert "drawing_not_checked" in reasons(answer)
        assert answer["can_run"] is True  # the chat does that itself

    def test_it_says_what_it_cannot_see(self):
        assert "locked" in explain_job("draw a line")["cannot_see"]


class TestTheToolsAnswerWithAutocadClosed:
    @pytest.fixture
    def closed(self, monkeypatch):
        """Bridge on, as for the modeller, and no AutoCAD at all (conftest's _probe raises)."""
        monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "on")
        monkeypatch.setattr(diagnose, "report", lambda: report(installed="1.5.0", connected=()))
        gate.reset()

    def test_they_are_read_tools(self):
        assert risk_of("autocad_why") is Risk.READ
        assert risk_of("autocad_gaps") is Risk.READ
        assert {"autocad_why", "autocad_gaps"} <= gate.NO_AUTOCAD_TOOLS

    def test_a_normal_read_tool_is_refused_but_why_answers(self, closed):
        from autocad_mcp.tools import layers

        assert asyncio.run(layers.autocad_list_layers()).startswith("Error:")
        answer = json.loads(asyncio.run(explain.autocad_why("why can't you save this as PDF")))
        assert answer["can_run"] is False
        assert answer["reasons"][0]["reason"] == "not_connected"

    def test_gaps_answers_and_reads_back_the_refusal(self, closed):
        from autocad_mcp.tools import layers

        asyncio.run(layers.autocad_list_layers())
        summary = json.loads(asyncio.run(explain.autocad_gaps(days=1)))
        assert summary["calls"] >= 1
        row = next(r for r in summary["by_tool"] if r["tool"] == "autocad_list_layers")
        assert row["refused"] >= 1
        assert summary["failures"][0]["reason"] == "no_autocad"
        assert "autocad_gaps" not in {r["tool"] for r in summary["by_tool"]}

    def test_the_audit_line_keeps_a_reason_word_never_the_message(self, closed):
        from autocad_mcp.tools import layers

        asyncio.run(layers.autocad_list_layers())
        lines = [json.loads(x) for f in audit.audit_dir().glob("*.jsonl") for x in f.read_text().splitlines()]
        line = next(x for x in lines if x["tool"] == "autocad_list_layers")
        assert line["reason"] == "no_autocad"
        assert "offline test" not in json.dumps(line)


def write_log(folder: Path, lines: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    by_month: dict[str, list[str]] = {}
    for line in lines:
        by_month.setdefault(line["at"][:7].replace("-", ""), []).append(json.dumps(line))
    for month, rows in by_month.items():
        (folder / f"audit-{month}.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")


NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def at(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat(timespec="milliseconds")


def line(tool, days_ago, outcome="done", ms=100, drawing=r"C:\Jobs\Secret Client\L03 plan.dwg", **extra):
    return {"at": at(days_ago), "conversation": "c1", "tool": tool, "risk": "change", "drawing": drawing,
            "ok": outcome in ("done", "discarded"), "outcome": outcome, "ms": ms, **extra}  # fmt: skip


class TestGaps:
    def test_counts_failures_by_reason_and_the_slowest(self, tmp_path):
        folder = tmp_path / "audit"
        write_log(folder, [
            line("autocad_draw_line", 1),
            line("autocad_draw_line", 1, "refused", reason="changes_off"),
            line("autocad_draw_line", 2, "refused", reason="changes_off"),
            line("autocad_export", 2, "failed", ms=42000, reason="publish_off"),
            line("autocad_super_hatch", 3, ms=91000),
            line("autocad_add_text", 3, "failed"),  # an old line, before reason words
            line("autocad_add_text", 30),  # outside the week
            {"at": "not a time", "tool": "x"},
        ])  # fmt: skip
        (folder / "audit-202611.jsonl").open("a").write("{broken json\n")
        out = audit.summary(7, folder=folder, now=NOW)
        assert out["calls"] == 6
        assert out["outcomes"] == {"done": 2, "failed": 2, "refused": 2}
        draw = next(r for r in out["by_tool"] if r["tool"] == "autocad_draw_line")
        assert (draw["calls"], draw["refused"], draw["failed"]) == (3, 2, 0)
        assert out["by_tool"][0]["tool"] == "autocad_draw_line"  # most used first
        first = out["failures"][0]
        assert first["reason"] == "changes_off" and first["count"] == 2
        assert "HERONCHANGES" in first["what_to_do"]
        assert {f["reason"] for f in out["failures"]} == {"changes_off", "publish_off", "other"}
        assert [s["tool"] for s in out["slowest"][:2]] == ["autocad_super_hatch", "autocad_export"]
        assert out["slowest"][0]["seconds"] == 91.0

    def test_never_a_drawings_folder(self, tmp_path):
        folder = tmp_path / "audit"
        write_log(folder, [line("autocad_draw_line", 1, ms=5000)])
        text = json.dumps(audit.summary(7, folder=folder, now=NOW))
        assert "L03 plan.dwg" in text
        assert "Secret Client" not in text and "Jobs" not in text

    def test_reading_the_log_is_not_counted_as_work(self, tmp_path):
        folder = tmp_path / "audit"
        write_log(folder, [line("autocad_gaps", 1), line("autocad_why", 1), line("autocad_draw_line", 1)])
        assert [r["tool"] for r in audit.summary(7, folder=folder, now=NOW)["by_tool"]] == ["autocad_draw_line"]

    def test_an_empty_or_missing_log(self, tmp_path):
        out = audit.summary(7, folder=tmp_path / "nothing", now=NOW)
        assert out["calls"] == 0 and out["by_tool"] == [] and out["slowest"] == []

    def test_a_month_before_the_window_is_not_read(self, tmp_path):
        folder = tmp_path / "audit"
        write_log(folder, [line("autocad_draw_line", 40)])
        assert audit.summary(7, folder=folder, now=NOW)["calls"] == 0
        assert audit.summary(60, folder=folder, now=NOW)["calls"] == 1

    def test_the_tool_says_when_there_is_nothing(self):
        out = json.loads(asyncio.run(explain.autocad_gaps(days=3)))
        assert out["calls"] == 0 and "Nothing" in out["note"]


class TestReasonWords:
    @pytest.mark.parametrize("message,word", [
        ("AutoCAD is not connected to Heron. Press the Heron button on the Heron tab.", "not_connected"),
        ("Changes is off, so Heron may not change this drawing.", "changes_off"),
        ("Publish is off, so Heron may not save.", "publish_off"),
        ("Admin is off, so Heron may not run AutoCAD commands.", "admin_off"),
        ("Heron has not checked plan.dwg yet. Call autocad_status first.", "drawing_not_checked"),
        ("This AutoCAD is in use by another chat.", "in_use"),
        ("The modeller stopped Heron in AutoCAD (HERONSTOP).", "stopped"),
        ("This needs Heron's plug-in 1.2.0 or newer in AutoCAD", "old_plugin"),
        ("AutoCAD is in the middle of a command and cannot accept new drawing operations.", "autocad_busy"),
        ("No running AutoCAD instance was found.", "no_autocad"),
        ("Error: Invalid input - x must be a number", "bad_input"),
        ("Error: AutoCAD rejected the operation - locked layer", "autocad_rejected"),
        ("Error: Outcome unknown: the undo was sent", "outcome_unknown"),
        ("Error: A dry run is not possible for Export: it writes a file", "no_dry_run"),
        ("Error: layer PIPE-CHW has no objects", "other"),
    ])  # fmt: skip
    def test_each_message_gets_its_word(self, message, word):
        assert audit.reason_of(message) == word

    def test_an_unknown_outcome_or_a_failed_discard_is_never_told_to_try_again(self):
        # #209: these messages say AutoCAD was busy, and a retry is what can do the job twice.
        from autocad_mcp.core import answers, gate

        busy_line = answers.line(answers.Facts(
            "Error: Outcome unknown: AutoCAD went busy part-way through", ok=False, outcome="unknown",
            busy=True, where="it is still in the LINE command",
        ))  # fmt: skip
        said = {
            gate.BACK_UNKNOWN: "outcome_unknown",
            busy_line: "outcome_unknown",
            "Error: Discard failed, the change may still be in the drawing: AutoCAD stayed busy for 10s "
            "and never accepted the request. Press Esc.": "discard_failed",
            "Error: Discard not possible: AutoCAD was in a command when the job began, so Heron put no UNDO "
            "mark down, so the change is still there. Remove it by hand. Press Esc in AutoCAD before the "
            "next job.": "discard_failed",
        }
        for message, word in said.items():
            assert audit.reason_of(message) == word, message
            assert "try again" not in audit.REASONS[word][1]

    def test_every_word_has_plain_words_and_a_fix(self):
        for word, (says, do) in audit.REASONS.items():
            assert says and do, word


class TestAuditFolder:
    """Issue #43: with %LOCALAPPDATA% unset the folder is fixed under the home, never relative."""

    def test_it_uses_localappdata_when_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert audit.audit_dir() == tmp_path / "Heron" / "autocad" / "audit"

    @pytest.mark.parametrize("value", [None, "", "   ", "relative/folder"])
    def test_unset_empty_or_relative_falls_back_under_the_home(self, monkeypatch, tmp_path, value):
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
        if value is None:
            monkeypatch.delenv("LOCALAPPDATA", raising=False)
        else:
            monkeypatch.setenv("LOCALAPPDATA", value)
        folder = audit.audit_dir()
        assert folder.is_absolute()
        assert folder == tmp_path / "home" / "AppData" / "Local" / "Heron" / "autocad" / "audit"

    def test_a_record_lands_in_the_fallback_not_the_working_folder(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.chdir(tmp_path)
        audit.record(tool="autocad_draw_line", ok=True, outcome="done", ms=1)
        assert list((tmp_path / "home").rglob("audit-*.jsonl"))
        assert not (tmp_path / "Heron").exists()
