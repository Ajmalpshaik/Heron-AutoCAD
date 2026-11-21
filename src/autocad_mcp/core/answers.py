"""The one plain line a change job's answer starts with (D-62).

Heron AI for Revit ends every change with one line the modeller can trust
without reading the rest. Heron for AutoCAD does the same, from the gate, so
no tool has to remember it:

- DONE: the job ran and was kept.
- NOTHING CHANGED: the job ran, or was discarded or rolled back, and the
  drawing is as it was.
- REFUSED: nothing was done. Heron or the plug-in said no before anything was
  sent, or the tool itself turned the job down.
- OUTCOME UNKNOWN: something went wrong after a write began, so part of it may
  be in the drawing. The line says whether Heron's UNDO mark is there to go
  back to.

The facts come from the plug-in's own count of what the job did (D-50) and
from whether a write began at all; never from what the tool says it did. The
counts are drawing objects only: a layer, a style or a setting is not an
object, so a job that wrote and counted nothing is DONE, said with care,
unless the tool itself lists every value it changed (``before_after``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

DONE = "DONE"
NOTHING_CHANGED = "NOTHING CHANGED"
REFUSED = "REFUSED"
OUTCOME_UNKNOWN = "OUTCOME UNKNOWN"
WORDS = (OUTCOME_UNKNOWN, NOTHING_CHANGED, REFUSED, DONE)  # longest first, for split()

MARK_HELD = "Heron put an UNDO mark down before this job: UNDO > Back returns the drawing to before it."
NO_MARK = (
    "Heron put no UNDO mark down before this job (it does with Ask to Keep on, or a dry run): "
    "look at the drawing; Ctrl+Z undoes the last step."
)
NOT_COUNTED_NOTE = "layers, styles and settings are not counted, so read the answer below"


@dataclass
class Facts:
    """What the gate knows about one job when it answers."""

    text: str  # the tool's own answer (after Keep or Discard)
    ok: bool  # the tool did not answer "Error: ..."
    outcome: str  # the gate's outcome: done, failed, unknown, discarded, refused
    counted: dict[str, Any] | None = None  # the plug-in's count (D-50), or None
    wrote: bool = False  # a write began (undo_mark or a plug-in operation)
    marked: bool = False  # Heron's UNDO mark was put down before the job
    can_count: bool = True  # Change level: a job whose effect is drawing objects
    refused_by_heron: bool = False  # refused before anything was sent
    note: str | None = None  # a sentence the gate adds (a dry run, a discard that could not run)
    word: str | None = None  # the gate already knows the word (a dry run, a failed discard)


def _total(counted: dict[str, Any] | None) -> int | None:
    if counted is None:
        return None
    return sum(int(counted.get(key, 0)) for key in ("added", "modified", "erased"))


def counts(counted: dict[str, Any]) -> str:
    """'2 added, 1 changed, 0 erased' from the plug-in's count."""
    return (
        f"{int(counted.get('added', 0))} added, {int(counted.get('modified', 0))} changed, "
        f"{int(counted.get('erased', 0))} erased"
    )


def _payload(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _lists_nothing(text: str) -> bool:
    """The tool listed every value it changed, and the list is empty."""
    payload = _payload(text)
    if not isinstance(payload, dict) or "before_after" not in payload:
        return False
    listed = payload["before_after"]
    return isinstance(listed, list) and not listed and not payload.get("before_after_more")


def _previewed(text: str) -> bool:
    payload = _payload(text)
    return isinstance(payload, dict) and (payload.get("dry_run") is True or payload.get("confirmed") is False)


def _part_failed(text: str) -> bool:
    payload = _payload(text)
    if not isinstance(payload, dict):
        return False
    failed = payload.get("failed")
    return bool(failed) and not isinstance(failed, bool)


def line(facts: Facts) -> str:
    """The first line of the answer: one of WORDS, a dash, one plain sentence."""
    total = _total(facts.counted)
    said = ("Outcome unknown" in facts.text) or facts.outcome == "unknown"

    if facts.word:
        word, why = facts.word, facts.note or ""
    elif facts.refused_by_heron:
        word, why = REFUSED, "nothing was sent to AutoCAD."
    elif facts.outcome == "discarded":
        word, why = NOTHING_CHANGED, "the modeller chose Discard, so the drawing is back as it was."
    elif said:
        word = OUTCOME_UNKNOWN
        why = "AutoCAD did not say how the job ended, so part of it may be in the drawing."
        if total:
            why = f"the job did not finish, and {counts(facts.counted)} so far."
    elif not facts.ok:
        if total:
            word, why = OUTCOME_UNKNOWN, f"the job failed part-way, after {counts(facts.counted)}."
        elif total is None and facts.wrote:
            word = OUTCOME_UNKNOWN
            why = "the job failed after it began to write, and the plug-in could not count what changed."
        else:
            word, why = REFUSED, "the tool turned the job down; nothing was changed."
    elif total:
        word, why = DONE, counts(facts.counted) + "."
        if _part_failed(facts.text):
            why = counts(facts.counted) + "; some parts failed, see 'failed' below."
    elif facts.can_count and (not facts.wrote or (total == 0 and _lists_nothing(facts.text))):
        word = NOTHING_CHANGED
        if _previewed(facts.text):
            why = "a dry run: the drawing is as it was; the answer says what the job would do."
        else:
            why = "the job ran and changed nothing in the drawing."
    elif total == 0:
        word, why = DONE, f"no drawing object was added, changed or erased ({NOT_COUNTED_NOTE})."
    else:
        word, why = DONE, "Heron's plug-in did not count the changes (an older plug-in)."

    if facts.note and not facts.word:
        why = f"{why} {facts.note}"
    if word == OUTCOME_UNKNOWN and not facts.word:
        why = f"{why} {MARK_HELD if facts.marked else NO_MARK}"
    return f"{word} - {why}".strip()


def with_line(result: Any, first: str) -> Any:
    """The answer with its plain line first. Pictures and other content stay as they are."""
    if not isinstance(result, str):
        return result
    return f"{first}\n\n{result}" if result else first


def split(text: str) -> tuple[str | None, str]:
    """(the plain line, the rest) of an answer; (None, text) when it has none."""
    if not isinstance(text, str):
        return None, text
    head, _, rest = text.partition("\n")
    if any(head == word or head.startswith(word + " - ") for word in WORDS):
        return head, rest.removeprefix("\n")
    return None, text


def body(text: Any) -> Any:
    """The answer without its plain line: what scripts and tests parse."""
    return split(text)[1] if isinstance(text, str) else text
