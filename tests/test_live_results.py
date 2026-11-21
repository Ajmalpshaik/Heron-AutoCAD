"""Writing results back into NEEDS-CHECKING without damaging it (no AutoCAD).

This is the half of the live-check runner that edits a hand-maintained file, so
it is the half that gets tests: every one of these is about *not* mangling a
register row.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("live_results", ROOT / "tools" / "live_results.py")
lr = importlib.util.module_from_spec(spec)
# A dataclass resolves its annotations through sys.modules, so the module has to
# be registered there before it is executed - not only after.
sys.modules["live_results"] = lr
spec.loader.exec_module(lr)

Outcome = lr.Outcome
WHEN = "2026-10-26"
VERSION = "2027 (26.0s)"

ROW = "| E4 | Measure the two arcs | Outer 628.3, inner 314.2 | NOT RUN |\n"


class TestRowId:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("| E4 | do | pass | NOT RUN |", "E4"),
            ("| D13 | do | pass | NOT RUN |", "D13"),
            ("| A8e | do | pass | **PASS** |", "A8e"),
            ("|E4| do | pass | NOT RUN |", "E4"),
            ("| Row | Do | Pass looks like | Result |", None),
            ("|---|---|---|---|", None),
            ("## Group E - heading", None),
            ("", None),
            ("| not a row | x |", None),
        ],
    )
    def test_only_a_real_register_row_is_recognised(self, line, expected):
        assert lr.row_id(line) == expected


class TestCells:
    def test_a_row_splits_into_its_cells(self):
        assert lr.cells(ROW) == [" E4 ", " Measure the two arcs ", " Outer 628.3, inner 314.2 ", " NOT RUN "]

    def test_a_line_that_is_not_a_row_is_refused(self):
        with pytest.raises(ValueError, match="not a table row"):
            lr.cells("## Group E")


class TestFormatResult:
    def test_a_pass_carries_the_date_the_version_and_the_evidence(self):
        text = lr.format_result(Outcome("E4", True, "outer 628.319, inner 314.159"), WHEN, VERSION)
        assert text == "**PASS** 2026-10-26, AutoCAD 2027 (26.0s): outer 628.319, inner 314.159"

    def test_a_fail_says_fail(self):
        assert lr.format_result(Outcome("E4", False, "outer 600.0"), WHEN, VERSION).startswith("**FAIL**")

    def test_a_skip_keeps_the_register_honest(self):
        text = lr.format_result(Outcome("D12", False, "", skipped=True, reason="needs a title block .dwg"), WHEN, VERSION)
        assert text == "NOT RUN — needs a title block .dwg"

    def test_a_pipe_in_the_evidence_cannot_break_the_table(self):
        text = lr.format_result(Outcome("E1", True, "one polyline | 2 bulges"), WHEN, VERSION)
        assert "|" not in text

    def test_a_newline_in_the_evidence_cannot_break_the_table(self):
        text = lr.format_result(Outcome("E1", True, "line one\nline two"), WHEN, VERSION)
        assert "\n" not in text

    def test_no_evidence_still_reads_properly(self):
        assert lr.format_result(Outcome("E1", True, ""), WHEN, VERSION).endswith("AutoCAD 2027 (26.0s)")


class TestSetResult:
    def test_only_the_last_cell_changes(self):
        out = lr.set_result(ROW, "**PASS** today")
        assert lr.cells(out)[:3] == lr.cells(ROW)[:3]
        assert lr.cells(out)[-1].strip() == "**PASS** today"

    def test_the_trailing_newline_is_kept(self):
        assert lr.set_result(ROW, "x").endswith("|\n")

    def test_a_row_without_a_newline_does_not_gain_one(self):
        assert not lr.set_result(ROW.rstrip("\n"), "x").endswith("\n")

    def test_leading_whitespace_is_kept(self):
        out = lr.set_result("   " + ROW, "x")
        assert out.startswith("   |")

    def test_prose_with_pipes_in_other_cells_is_untouched(self):
        line = "| E7 | Do a thing | **The text sits centred** — see [10](10.md) | NOT RUN |\n"
        out = lr.set_result(line, "**PASS** today")
        assert "**The text sits centred** — see [10](10.md)" in out
        assert out.count("|") == line.count("|")

    def test_a_row_with_too_few_cells_is_refused(self):
        with pytest.raises(ValueError):
            lr.set_result("| E4 |\n", "x")


class TestApplyResults:
    REGISTER = (
        "## Group E - the new tools\n"
        "\n"
        "| Row | Do | Pass looks like | Result |\n"
        "|---|---|---|---|\n"
        "| E1 | A slot | One polyline | NOT RUN |\n"
        "| E4 | A cone | Outer 628.3 | NOT RUN |\n"
        "| E22 | A box | Base on z=0 | NOT RUN |\n"
        "\n"
        "## Group B - no machine\n"
        "\n"
        "Rows B1-B19 = A1-A19. **NO MACHINE.**\n"
    )

    def test_matching_rows_are_written_and_the_rest_left_alone(self):
        outcomes = [Outcome("E1", True, "one polyline, 2 bulges"), Outcome("E4", False, "outer 600")]
        new, written, missing = lr.apply_results(self.REGISTER, outcomes, WHEN, VERSION)
        assert written == ["E1", "E4"] and missing == []
        assert "**PASS** 2026-10-26, AutoCAD 2027 (26.0s): one polyline, 2 bulges" in new
        assert "**FAIL** 2026-10-26, AutoCAD 2027 (26.0s): outer 600" in new
        # Untouched rows and every other line survive verbatim.
        assert "| E22 | A box | Base on z=0 | NOT RUN |" in new
        assert "Rows B1-B19 = A1-A19. **NO MACHINE.**" in new
        assert "| Row | Do | Pass looks like | Result |" in new

    def test_the_line_count_never_changes(self):
        outcomes = [Outcome("E1", True, "x"), Outcome("E4", True, "y"), Outcome("E22", True, "z")]
        new, _, _ = lr.apply_results(self.REGISTER, outcomes, WHEN, VERSION)
        assert len(new.splitlines()) == len(self.REGISTER.splitlines())

    def test_a_row_the_register_does_not_have_is_reported_not_invented(self):
        new, written, missing = lr.apply_results(
            self.REGISTER, [Outcome("E99", True, "x")], WHEN, VERSION
        )
        assert written == [] and missing == ["E99"]
        assert new == self.REGISTER

    def test_nothing_to_write_leaves_the_file_byte_for_byte(self):
        new, written, missing = lr.apply_results(self.REGISTER, [], WHEN, VERSION)
        assert new == self.REGISTER and written == [] and missing == []

    def test_a_row_id_in_the_prose_is_not_mistaken_for_a_row(self):
        register = self.REGISTER + "\nSee E4 for the cone check, and E1 for the slot.\n"
        new, written, _ = lr.apply_results(register, [Outcome("E4", True, "x")], WHEN, VERSION)
        assert written == ["E4"]
        assert "See E4 for the cone check, and E1 for the slot." in new

    def test_the_real_register_can_be_written_without_losing_a_line(self):
        """The one that matters: run it against the file in this repository."""
        register = (ROOT / "docs" / "NEEDS-CHECKING.md").read_text(encoding="utf-8")
        rows = [lr.row_id(line) for line in register.splitlines()]
        present = [r for r in rows if r]
        assert len(present) > 60, "the register should hold the live rows"
        outcomes = [Outcome(r, True, "driven by tools/live_check.py") for r in present]
        new, written, missing = lr.apply_results(register, outcomes, WHEN, VERSION)
        assert missing == []
        assert sorted(written) == sorted(present)
        assert len(new.splitlines()) == len(register.splitlines())
        # Every row now carries a result, and no row lost a cell.
        for old_line, new_line in zip(register.splitlines(), new.splitlines(), strict=True):
            if lr.row_id(old_line):
                assert len(lr.cells(new_line)) == len(lr.cells(old_line))
            else:
                assert new_line == old_line


class TestSummarise:
    def test_it_counts_each_state_apart(self):
        assert lr.summarise(
            [
                Outcome("E1", True, ""),
                Outcome("E2", True, ""),
                Outcome("E3", False, ""),
                Outcome("E4", False, "", skipped=True, reason="needs an eye"),
            ]
        ) == {"checked": 3, "passed": 2, "failed": 1, "skipped": 1}

    def test_nothing_run_counts_as_nothing(self):
        assert lr.summarise([]) == {"checked": 0, "passed": 0, "failed": 0, "skipped": 0}


class TestAHandResultIsNeverWiped:
    REGISTER = (
        "| Row | Do | Pass | Result |\n|---|---|---|---|\n"
        "| D12 | a | b | **PASS** 2026-10-28, AutoCAD 2027: by hand |\n"
        "| X21 | a | b | NO MACHINE |\n"
        "| AA3 | a | b | NOT RUN |\n"
        "| AC5b | a | b | NOT RUN — an older reason |\n"
    )

    def test_a_not_run_reason_leaves_a_pass_alone(self):
        outcomes = [Outcome(r, False, "", skipped=True, reason="needs an eye") for r in ("D12", "X21", "AA3", "AC5b")]
        new, written, missing = lr.apply_results(self.REGISTER, outcomes, WHEN, VERSION)
        assert "**PASS** 2026-10-28" in new and "NO MACHINE" in new
        assert sorted(written) == ["AA3", "AC5b"] and missing == []
        assert lr.kept_by_hand(self.REGISTER, outcomes) == ["D12", "X21"]

    def test_a_measurement_still_replaces_what_was_there(self):
        new, written, _ = lr.apply_results(self.REGISTER, [Outcome("D12", False, "the corner is off")], WHEN, VERSION)
        assert written == ["D12"] and "**FAIL**" in new

    def test_two_letter_rows_are_rows(self):
        assert lr.row_id("| AA12 | x | y | NOT RUN |") == "AA12"
        assert lr.row_id("| AC5b | x | y | NOT RUN |") == "AC5b"
