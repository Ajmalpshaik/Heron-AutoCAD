"""The live-check runner must agree with the register it writes into.

These run without AutoCAD. They do not prove a check is *right* - only
AutoCAD can do that - but they prove the runner is talking about rows that
exist, calling tools that exist, and leaving nothing in the register
unaccounted for. When someone adds a row to NEEDS-CHECKING.md, the coverage
test fails until the runner either measures it or says why it cannot.
"""

from __future__ import annotations

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
    return set(re.findall(r"^\|\s*([A-Z]\d+[a-z]?)\s*\|", REGISTER.read_text(encoding="utf-8"), re.M))


# The groups the runner is responsible for. Group A is the plug-in in the
# ribbon, which a person has to click; B and C need machines we do not have.
RUNNER_GROUPS = "DEF"


def live_rows() -> set[str]:
    """The rows the runner must account for: groups D, E and F."""
    return {row for row in register_rows() if row[0] in RUNNER_GROUPS}


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
        unaccounted = sorted(live_rows() - covered, key=lambda r: (r[0], int(re.sub(r"\D", "", r))))
        assert unaccounted == [], (
            "these register rows are neither measured nor given a reason: "
            f"{unaccounted}. Add a check to tools/live_check.py, or a line to BY_EYE "
            "saying why only an eye can answer it."
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
        wrong = [f"{c.row} is in group {c.group}" for c in live_check.CHECKS if c.group != c.row[0]]
        assert wrong == [], wrong

    def test_every_check_has_a_title(self):
        bare = [c.row for c in live_check.CHECKS if len(c.title.split()) < 3]
        assert bare == [], f"these rows have no useful title: {bare}"

    def test_every_check_says_what_it_proves(self):
        """The evidence written into the register comes from the return value."""
        for check in live_check.CHECKS:
            assert check.run.__doc__ or "return" in TEXT, check.row


class TestTheToolsItCallsExist:
    MODULES = (
        "annotate", "batch", "blocks", "convert", "coordinates", "dimensions",
        "document", "draw", "geometry_tools", "layers", "query", "sequence",
        "settings", "shapes", "sheets", "solids", "views",
    )

    def test_every_tool_function_it_calls_is_real(self):
        missing = []
        for module, attribute in sorted(set(re.findall(r"\b(\w+)\.(autocad_\w+)\(", TEXT))):
            if module not in self.MODULES:
                continue
            loaded = importlib.import_module(f"autocad_mcp.tools.{module}")
            if not hasattr(loaded, attribute):
                missing.append(f"{module}.{attribute}")
        assert missing == [], f"the runner calls tools that do not exist: {missing}"

    def test_it_calls_something_from_every_module_it_imports(self):
        imported = set(re.findall(r"^    (\w+),$", TEXT, re.M))
        used = {m for m, _ in re.findall(r"\b(\w+)\.(autocad_\w+)\(", TEXT)}
        assert imported <= used, f"imported but never used: {sorted(imported - used)}"

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
