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
from whether a write began at all; never from what the tool says it did. When
AutoCAD went busy, the line also says which command it is in, from the
plug-in's command tracker (#47), and what the plug-in counted so far. The
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
    busy: bool = False  # the job ended on a busy AutoCAD (#47)
    where: str = ""  # where that busy AutoCAD is, from busy_where(); "" when not known


LISP = "AUTOLISP"  # the name the plug-in's command tracker gives a LISP evaluation


def busy_where(known: bool, command: str | None) -> str:
    """Where a busy AutoCAD is, in a few words, from the plug-in's command tracker (#47).

    "" when the plug-in cannot tell (an older plug-in, or not reachable).
    """
    if not known:
        return ""
    if not command:
        return "it is in no command now, so a redraw or a box held it"
    if command.strip().upper() == LISP:
        return "it is still evaluating AutoLISP"
    return f"it is still in the {command.strip().upper()} command"


def busy_note(known: bool, command: str | None) -> str:
    """The sentence a read's answer gets when AutoCAD was busy (a change says it in the plain line)."""
    where = busy_where(known, command)
    if not where:
        return ""
    if not command:
        return f"AutoCAD was busy: {where}. Close any box open in AutoCAD, then try again."
    return f"AutoCAD was busy: {where}. Let it finish, or press Esc in AutoCAD, then try again."


def _in(facts: Facts) -> str:
    return f" ({facts.where})" if facts.where else ""


def _so_far(facts: Facts, total: int | None, unknown: str) -> str:
    """What the plug-in counted so far, after a busy or unanswered job; ``unknown`` when it could not count."""
    if total:
        return f", after {counts(facts.counted)} so far."
    if total == 0:
        return f"; the plug-in counted no drawing object added, changed or erased so far ({NOT_COUNTED_NOTE})."
    return f", {unknown}"


def _timed_out(text: str) -> bool:
    """The tool answered, but says it never heard how the job ended (autocad_run_lisp's wait)."""
    payload = _payload(text)
    return isinstance(payload, dict) and payload.get("timed_out") is True


def _lisp_error(text: str) -> bool:
    """The tool answered with AutoCAD's own LISP error message (autocad_run_lisp, #157)."""
    payload = _payload(text)
    return isinstance(payload, dict) and bool(payload.get("lisp_error"))


def _stopped_part_way(text: str) -> str:
    """For code sent in pieces (autocad_run_lisp, D-76): "piece 2 of 5" when it stopped early, else ""."""
    payload = _payload(text)
    if not isinstance(payload, dict):
        return ""
    total, finished = payload.get("chunks"), payload.get("chunks_finished")
    if not isinstance(total, int) or not isinstance(finished, int) or finished >= total:
        return ""
    return f"piece {min(finished + 1, total)} of {total}"


def _says_busy(facts: Facts) -> bool:
    """A busy spell ended this job, and the answer itself says so (not one step of many that went on)."""
    return facts.busy and "busy" in facts.text


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
        if _says_busy(facts):
            why = f"AutoCAD went busy part-way{_in(facts)}" + _so_far(
                facts, total, "and the plug-in could not count what changed, so part of it may be in the drawing."
            )
        else:
            why = "AutoCAD did not say how the job ended, so part of it may be in the drawing."
            if total:
                why = f"the job did not finish, and {counts(facts.counted)} so far."
    elif not facts.ok:
        if total:
            word, why = OUTCOME_UNKNOWN, f"the job failed part-way{_in(facts)}, after {counts(facts.counted)}."
        elif total is None and facts.wrote:
            word = OUTCOME_UNKNOWN
            why = "the job failed after it began to write, and the plug-in could not count what changed."
        elif _says_busy(facts) and "stayed busy" in facts.text:
            word, why = REFUSED, f"AutoCAD stayed busy{_in(facts)} and never took the request; nothing was changed."
        else:
            word, why = REFUSED, "the tool turned the job down; nothing was changed."
    elif _timed_out(facts.text):
        # The tool answered, but never heard how the job ended: not DONE.
        word = OUTCOME_UNKNOWN
        opening = (
            f"AutoCAD stayed busy{_in(facts)} and never let Heron read how the job ended"
            if facts.busy
            else "AutoCAD did not answer within the wait, so the job may still have run"
        )
        why = opening + _so_far(facts, total, "and the plug-in could not count what changed.")
    elif _lisp_error(facts.text):
        # AutoCAD raised a LISP error and the code stopped there: never DONE. Pieces before it ran.
        if total == 0 and facts.can_count:
            word = NOTHING_CHANGED
            why = "AutoCAD reported a LISP error, and no drawing object was added, changed or erased."
        else:
            word = OUTCOME_UNKNOWN
            why = "AutoCAD reported a LISP error and the code stopped there; what ran before it is in the drawing" + _so_far(
                facts, total, "and the plug-in could not count what changed."
            )
    elif _stopped_part_way(facts.text):
        # Code sent in pieces that stopped early: the pieces before it ran, the rest never did.
        word = OUTCOME_UNKNOWN
        why = f"the code stopped at {_stopped_part_way(facts.text)}; the pieces before it ran" + _so_far(
            facts, total, "and the plug-in could not count what changed."
        )
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
