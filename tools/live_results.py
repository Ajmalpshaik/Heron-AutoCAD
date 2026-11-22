"""Writing live-check results back into the NEEDS-CHECKING register.

Kept apart from the runner for one reason: this is the part that edits a
hand-maintained file, so it is a set of pure string functions with tests behind
them. The runner that drives AutoCAD cannot be tested without AutoCAD; this
can, and it is the half that could do damage.

A register row looks like:

    | E4 | Do the thing | Pass looks like | NOT RUN |

Only the **last** cell is ever touched, matched by the row id in the first
cell. Everything else on the line - the prose, the bold, the links - is left
exactly as it was.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A table row whose first cell is a row id like D4, E12, A8e, AA12, AC5b.
_ROW = re.compile(r"^\|\s*(?P<id>[A-Z]{1,2}\d+[a-z]?)\s*\|")


@dataclass(frozen=True)
class Outcome:
    """What one check found."""

    row: str
    ok: bool
    detail: str
    skipped: bool = False
    reason: str = ""

    @property
    def state(self) -> str:
        if self.skipped:
            return "NOT RUN"
        return "PASS" if self.ok else "FAIL"


def cells(line: str) -> list[str]:
    """A markdown table row split into its cells, without the outer pipes."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        raise ValueError("not a table row")
    inner = stripped[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return inner.split("|")


def row_id(line: str) -> str | None:
    """The row id a register line carries, or None if it is not such a row."""
    match = _ROW.match(line.strip())
    return match.group("id") if match else None


def format_result(outcome: Outcome, when: str, version: str) -> str:
    """The register's own wording for a result: state, date, version, evidence."""
    if outcome.skipped:
        why = outcome.reason or "not run by the live-check runner"
        return f"NOT RUN — {why}"
    detail = outcome.detail.strip().replace("|", "/").replace("\n", " ")
    head = f"**{outcome.state}** {when}, AutoCAD {version}"
    return f"{head}: {detail}" if detail else head


def set_result(line: str, result: str) -> str:
    """One register line with its last cell replaced, keeping the rest verbatim."""
    parts = cells(line)
    if len(parts) < 2:
        raise ValueError("a register row needs at least an id and a result")
    # Keep the line's own leading whitespace and its trailing newline.
    lead = line[: len(line) - len(line.lstrip())]
    tail = "\n" if line.endswith("\n") else ""
    parts[-1] = f" {result} "
    return f"{lead}|" + "|".join(parts) + f"|{tail}"


def recorded_by_hand(line: str) -> bool:
    """A row whose result is already more than NOT RUN: a PASS, a FAIL, NO MACHINE, a note written by hand."""
    try:
        last = cells(line)[-1].strip()
    except ValueError:
        return False
    return not last.startswith("NOT RUN")


def kept_by_hand(markdown: str, outcomes: list[Outcome]) -> list[str]:
    """The rows a NOT RUN outcome would leave alone, because a result is already recorded there."""
    skipped = {o.row for o in outcomes if o.skipped}
    return sorted({
        found for line in markdown.splitlines()
        if (found := row_id(line)) in skipped and recorded_by_hand(line)
    })


def apply_results(
    markdown: str, outcomes: list[Outcome], when: str, version: str
) -> tuple[str, list[str], list[str]]:
    """The register with every matching row's result replaced.

    Returns (new text, rows written, rows not found). A row id that is not in
    the register is reported rather than invented, and a row that appears twice
    is written both times - the register is the authority on which rows exist.

    A NOT RUN outcome (a row that needs an eye, or a padlock that was not so this
    time) is written only over a row that says NOT RUN already: it never wipes a
    PASS, a FAIL or NO MACHINE someone recorded. Such a row counts as found.
    """
    by_row = {o.row: o for o in outcomes}
    written: list[str] = []
    seen: list[str] = []
    out: list[str] = []
    for line in markdown.splitlines(keepends=True):
        found = row_id(line)
        if found and found in by_row and by_row[found].skipped and recorded_by_hand(line):
            seen.append(found)
            out.append(line)
            continue
        if found and found in by_row:
            try:
                out.append(set_result(line, format_result(by_row[found], when, version)))
                written.append(found)
                continue
            except ValueError:
                pass  # not a row we can rewrite; leave it exactly as it is
        out.append(line)
    missing = sorted(set(by_row) - set(written) - set(seen))
    return "".join(out), written, missing


def summarise(outcomes: list[Outcome]) -> dict[str, int]:
    """How many passed, failed and were skipped."""
    return {
        "checked": sum(1 for o in outcomes if not o.skipped),
        "passed": sum(1 for o in outcomes if o.ok and not o.skipped),
        "failed": sum(1 for o in outcomes if not o.ok and not o.skipped),
        "skipped": sum(1 for o in outcomes if o.skipped),
    }
