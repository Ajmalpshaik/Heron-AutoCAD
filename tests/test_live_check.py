"""The live-check runner must agree with the register it writes into.

These run without AutoCAD. They do not prove a check is *right* - only
AutoCAD can do that - but they prove the runner is talking about rows that
exist, calling tools that exist, and leaving nothing in the register
unaccounted for. When someone adds a row to NEEDS-CHECKING.md, the coverage
test fails until the runner either measures it or says why it cannot.
"""

from __future__ import annotations

import asyncio
import importlib
import re
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import script_env

from autocad_mcp.core.risk import RISK, Risk

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
REGISTER = ROOT / "docs" / "NEEDS-CHECKING.md"
SOURCE = TOOLS / "live_check.py"

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

live_check = importlib.import_module("live_check")
TEXT = SOURCE.read_text(encoding="utf-8")


def register_rows() -> set[str]:
    """Every row id in the register."""
    return set(re.findall(r"^\|\s*([A-Z]{1,2}\d+[a-z]?)\s*\|", REGISTER.read_text(encoding="utf-8"), re.M))


lc = importlib.import_module("live_common")
# The groups the runner is responsible for (live_check.RUNNER_GROUPS). Group A
# is the plug-in in the ribbon, which a person has to click; B and C need
# machines we do not have.
RUNNER_GROUPS = live_check.RUNNER_GROUPS


def live_rows() -> set[str]:
    """The rows the runner must account for: every row of its groups."""
    return {row for row in register_rows() if lc.group_of(row) in RUNNER_GROUPS}


class TestTheRowsAreReal:
    def test_every_measured_row_is_in_the_register(self):
        rows = register_rows()
        missing = sorted(c.row for c in live_check.CHECKS if c.row not in rows)
        assert missing == [], f"the runner measures rows the register does not have: {missing}"

    def test_every_by_eye_row_is_in_the_register(self):
        rows = register_rows()
        missing = sorted(row for row in live_check.BY_EYE if row not in rows)
        assert missing == [], f"the runner excuses rows the register does not have: {missing}"

    def test_no_row_is_both_measured_and_left_to_an_eye(self):
        both = sorted({c.row for c in live_check.CHECKS} & set(live_check.BY_EYE))
        assert both == [], f"these rows are claimed twice: {both}"

    def test_every_live_row_is_accounted_for(self):
        """The point of the runner: no row in D or E is left unexplained."""
        covered = {c.row for c in live_check.CHECKS} | set(live_check.BY_EYE)
        unaccounted = sorted(live_rows() - covered, key=lambda r: (lc.group_of(r), int(re.sub(r"\D", "", r))))
        assert unaccounted == [], (
            "these register rows are neither measured nor given a reason: "
            f"{unaccounted}. Add a check to the group's file in tools/ (live_check*.py), or a line "
            "to its BY_EYE saying why only an eye or a hand can answer it."
        )

    def test_every_group_on_the_register_is_known_to_the_runner(self):
        """A new group is the runner's too, or named here as left to people: never forgotten."""
        on_register = {lc.group_of(row) for row in register_rows()}
        left_to_people = {"A", "B", "C", "G", "H", "I", "J", "K", "L", "S"}
        new = sorted(on_register - set(RUNNER_GROUPS) - left_to_people)
        assert new == [], (
            f"the register has groups the runner does not cover yet: {new}. Add their rows to "
            "tools/live_check*.py (a check, or a BY_EYE reason) and the group to live_check.RUNNER_GROUPS."
        )

    def test_each_reason_says_something(self):
        thin = sorted(row for row, why in live_check.BY_EYE.items() if len(why.split()) < 4)
        assert thin == [], f"these reasons are too thin to be useful: {thin}"


class TestTheChecksAreWellFormed:
    def test_every_row_appears_once(self):
        rows = [c.row for c in live_check.CHECKS]
        assert len(rows) == len(set(rows)), "a row is checked twice"

    def test_every_check_has_its_own_function(self):
        functions = [c.run for c in live_check.CHECKS]
        assert len(functions) == len(set(functions)), "two rows share one check function"

    def test_every_check_is_in_the_group_its_row_says(self):
        wrong = [f"{c.row} is in group {c.group}" for c in live_check.CHECKS if c.group != lc.group_of(c.row)]
        assert wrong == [], wrong

    def test_every_check_has_a_title(self):
        bare = [c.row for c in live_check.CHECKS if len(c.title.split()) < 3]
        assert bare == [], f"these rows have no useful title: {bare}"

    def test_every_check_says_what_it_proves(self):
        """The evidence written into the register comes from the return value."""
        for check in live_check.CHECKS:
            assert check.run.__doc__ or "return" in TEXT, check.row


# Every file of checks: the runner and one per area (live_common.py says which).
CHECK_FILES = sorted(TOOLS.glob("live_check*.py"))


def _tool_imports(text: str) -> set[str]:
    block = re.search(r"^from autocad_mcp\.tools import \((.*?)\)", text, re.M | re.S)
    return set(re.findall(r"(\w+),", block.group(1))) if block else set()


class TestTheToolsItCallsExist:
    @pytest.mark.parametrize("path", CHECK_FILES, ids=lambda p: p.name)
    def test_every_tool_function_it_calls_is_real(self, path):
        text = path.read_text(encoding="utf-8")
        modules = _tool_imports(text)
        missing = []
        for module, attribute in sorted(set(re.findall(r"\b(\w+)\.(autocad_\w+)\(", text))):
            if module not in modules:
                continue
            loaded = importlib.import_module(f"autocad_mcp.tools.{module}")
            if not hasattr(loaded, attribute):
                missing.append(f"{module}.{attribute}")
        assert missing == [], f"{path.name} calls tools that do not exist: {missing}"

    @pytest.mark.parametrize("path", CHECK_FILES, ids=lambda p: p.name)
    def test_it_calls_something_from_every_module_it_imports(self, path):
        text = path.read_text(encoding="utf-8")
        used = {m for m, _ in re.findall(r"\b(\w+)\.(\w+)\(", text)}
        unused = sorted(_tool_imports(text) - used)
        assert unused == [], f"{path.name} imports but never uses: {unused}"

    @pytest.mark.parametrize("path", CHECK_FILES, ids=lambda p: p.name)
    def test_a_tool_is_never_imported_on_its_own(self, path):
        """The offline tests put recorded answers in place of module.autocad_x: a bare import would dodge them."""
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^from autocad_mcp\.tools\.\w+ import", text, re.M), path.name

    def test_every_tool_named_in_a_sequence_step_is_registered(self):
        unknown = sorted({n for n in re.findall(r'"tool": "(\w+)"', TEXT) if n not in RISK})
        assert unknown == [], f"a sequence step names an unregistered tool: {unknown}"

    @pytest.mark.parametrize("name", sorted(set(re.findall(r'"tool": "(\w+)"', TEXT))))
    def test_a_step_is_either_allowed_or_deliberately_not(self, name):
        """D30 proves the ceiling, so the runner must name tools on both sides of it."""
        assert RISK[name] in (Risk.READ, Risk.VIEW, Risk.CHANGE, Risk.PUBLISH, Risk.ADMIN)

    def test_the_ceiling_check_names_a_tool_above_changes(self):
        above = [n for n in re.findall(r'"tool": "(\w+)"', TEXT)
                 if RISK[n] in (Risk.PUBLISH, Risk.ADMIN)]
        assert above, "D30 cannot prove a ceiling without naming a tool above Changes"


class TestItRunsWithoutAutocad:
    def test_list_works_and_reports_the_whole_register(self):
        done = subprocess.run(
            [sys.executable, str(SOURCE), "--list"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=script_env(),
        )
        assert done.returncode == 0, done.stderr
        measured = len(live_check.CHECKS)
        assert f"{measured} measured rows" in done.stdout
        for check in live_check.CHECKS:
            assert check.row in done.stdout

    def test_an_unknown_row_is_turned_away(self):
        done = subprocess.run(
            [sys.executable, str(SOURCE), "--row", "Z99"],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=script_env(),
        )
        assert done.returncode == 1
        assert "No rows match" in done.stdout


class TestThePadlocksComeFirst:
    """D-59: the padlocks start off, only the modeller's click moves one, and the runner never tries."""

    STATUS = '{"connected": true, "version": "26.0s", "application": "AutoCAD", "heron": {"connected": true}}'

    def _ready(self, monkeypatch, locks):
        from autocad_mcp.tools import document

        async def status(**kwargs):
            return self.STATUS

        async def padlocks():
            return locks

        monkeypatch.setattr(document, "autocad_status", status)
        monkeypatch.setattr(lc, "read_padlocks", padlocks)
        ctx = lc.Context()
        return asyncio.run(live_check.ready(ctx)), ctx

    def test_changes_off_stops_the_run_and_says_what_to_do(self, monkeypatch, capsys):
        code, _ = self._ready(monkeypatch, {"changes": False, "publish": False, "admin": False, "ask_to_keep": False})
        said = capsys.readouterr().out
        assert code == 2
        assert "Turn Changes on in Settings" in said and "Nothing was run" in said

    def test_ask_to_keep_on_stops_the_run(self, monkeypatch, capsys):
        code, _ = self._ready(monkeypatch, {"changes": True, "publish": False, "admin": False, "ask_to_keep": True})
        assert code == 2 and "Turn Ask to Keep off" in capsys.readouterr().out

    def test_padlocks_that_cannot_be_read_stop_the_run(self, monkeypatch, capsys):
        code, _ = self._ready(monkeypatch, None)
        assert code == 2 and "cannot read" in capsys.readouterr().out

    def test_changes_on_goes_on_and_says_the_padlocks(self, monkeypatch, capsys):
        code, ctx = self._ready(monkeypatch, {"changes": True, "publish": False, "admin": True, "ask_to_keep": False})
        assert code is None and ctx.padlocks["admin"] is True
        assert "Changes on, Publish off, Admin on, Ask to Keep off" in capsys.readouterr().out

    def test_the_runner_has_no_way_to_move_a_padlock(self):
        for path in CHECK_FILES + [TOOLS / "live_common.py"]:
            text = path.read_text(encoding="utf-8")
            # Named in what the runner tells you to do, never typed or sent by it.
            sent = re.findall(r"(?:command|expression|SendCommand)\s*[=(]\s*[^\n]*HERON(?:CHANGES|PUBLISH|ADMIN)", text)
            assert sent == [], f"{path.name} would type a padlock command: {sent}"

    def test_a_row_that_needs_another_padlock_is_said_not_failed(self):
        why = lc.unmet(frozenset({"admin", "no_publish"}), {"changes": True, "admin": False, "publish": True})
        assert why.startswith("not run this time") and "Admin on" in why and "Publish off" in why
        assert lc.unmet(frozenset({"admin"}), {"admin": True}) is None

    def test_every_need_a_check_names_is_known(self):
        named = {need for check in live_check.CHECKS for need in check.needs}
        assert named <= set(lc.NEEDS), sorted(named - set(lc.NEEDS))


class TestTwoLetterGroups:
    @pytest.mark.parametrize(("row", "group"), [("E4", "E"), ("A8e", "A"), ("AA12", "AA"), ("AC5b", "AC"), ("Z10", "Z")])
    def test_a_rows_group(self, row, group):
        assert lc.group_of(row) == group

    def test_no_two_rows_share_a_spot(self):
        rows = [c.row for c in live_check.CHECKS if lc.group_of(c.row) not in ("D", "E", "F")]
        spots = [lc.origin(r) for r in rows]
        assert len(set(spots)) == len(spots)
        assert all(x >= 2_000_000 for x, _ in spots), "the later rows stay clear of where D, E and F draw"

    def test_a_group_can_be_run_alone(self):
        import argparse

        picked = live_check.selected(argparse.Namespace(row=None, group="AA"))
        assert picked and all(c.group == "AA" for c in picked)
        eye = live_check.eye_rows(argparse.Namespace(row=None, group="AA,Z"))
        assert eye and {lc.group_of(r) for r in eye} <= {"AA", "Z"}


class TestTheRecordingsCannotLie:
    """The harness itself: a misspelt argument or an unrecorded call fails the test, not AutoCAD."""

    def test_a_misspelt_argument_is_caught(self, monkeypatch):
        from live_fakes import play

        from autocad_mcp.tools import edit2d

        async def check(ctx):
            await edit2d.autocad_trim_extend(operaton="trim", handles=["A"], edges=["B"])

        with pytest.raises(AssertionError, match="would not take"):
            play(monkeypatch, check, {"autocad_trim_extend": {}})

    def test_a_call_nobody_recorded_is_caught(self, monkeypatch):
        from live_fakes import play

        from autocad_mcp.tools import query

        async def check(ctx):
            await query.autocad_get_entity(handle="A")

        with pytest.raises(AssertionError, match="does not cover"):
            play(monkeypatch, check, {})

    def test_a_recording_of_something_that_does_not_exist_is_caught(self, monkeypatch):
        from live_fakes import play

        async def check(ctx):
            return "x"

        with pytest.raises(AssertionError, match="do not exist"):
            play(monkeypatch, check, {"autocad_no_such_tool": {}})
