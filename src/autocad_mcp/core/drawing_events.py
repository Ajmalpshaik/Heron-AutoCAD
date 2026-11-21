"""What happened to the drawing Heron checked, from the plug-in's document events (#48, D-98).

The wrong-drawing guard (D-19) compares the drawing in front with the one
``autocad_status`` checked. Comparing names alone misses what happened in
between: the same drawing closed and opened again, AutoCAD restarted with it,
or a Save As that gave the checked drawing a new name. Since #48 the plug-in
records AutoCAD's document events as they happen (opened, came to the front,
saved, closed) with a number and an epoch per AutoCAD session, and the gate
asks for the events since its check. This module judges them; it is pure, so
it is tested offline:

- another AutoCAD session (restarted, or another AutoCAD) -> check again;
- the checked drawing was closed since -> check again, even when the same
  name is in front: it is a new copy in memory, perhaps changed on disk;
- the drawing in front was opened since the check (a Save As, then the old
  file opened again; or a second copy of it) -> check again;
- the checked drawing was saved under a new name and that name is in front
  -> the same drawing, the same units: the guard follows the new name;
- anything else -> the name compare decides, as before.

When the plug-in cannot tell (an older one) nothing here refuses: the guard
is exactly as it was before. When older events dropped off unread, what is
still there is judged, but a Save As is not followed on it. Names are compared
exactly (ignoring case): both sides give a saved drawing's full path and an
unsaved one's bare name, so a bare name never stands for a file elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PureWindowsPath
from typing import Any

from .bridge import NOTHING_SENT


@dataclass(frozen=True)
class Mark:
    """Where the plug-in's drawing log stood when Heron checked a drawing."""

    pid: int
    epoch: str
    seq: int


@dataclass(frozen=True)
class Verdict:
    """refusal: refuse with this sentence. follow: the checked drawing's new name (a Save As).

    seen: every event up to this number was judged and none spoke against the
    checked drawing, so the guard may move its mark here (None: leave it).
    """

    refusal: str | None = None
    follow: str | None = None
    seen: int | None = None


def short(drawing: str) -> str:
    """The file name alone, for a sentence."""
    return PureWindowsPath(str(drawing or "")).name or "no drawing"


def same(a: str, b: str) -> bool:
    """The plug-in's DrawingNames.Same: full paths match, or a bare name matches a file name."""
    a, b = str(a or ""), str(b or "")
    if a.casefold() == b.casefold():
        return True
    if not a or not b:
        return False
    bare = not _has_folder(a) or not _has_folder(b)
    return bare and short(a).casefold() == short(b).casefold()


def _has_folder(name: str) -> bool:
    return "\\" in name or "/" in name


def other_session(checked: str) -> str:
    return (
        f"AutoCAD was started again, or another AutoCAD is in front, since Heron checked {short(checked)}. "
        "Call autocad_status first, so Heron knows the units of the drawing open now. " + NOTHING_SENT
    )


def _eq(a: str, b: str) -> bool:
    return str(a or "").casefold() == str(b or "").casefold()


def opened_since(current: str, at: str) -> str:
    when = f" at {at}" if at else ""
    return (
        f"{short(current)} was opened{when}, after Heron checked a drawing, so it is a new copy in "
        f"memory. Call autocad_status first, so Heron knows its units and the change goes where you "
        f"mean it. {NOTHING_SENT}"
    )


def closed_since(checked: str, at: str, current: str) -> str:
    when = f" at {at}" if at else ""
    if _eq(current, checked):
        what = f"{short(checked)} was closed{when} and opened again since Heron checked it"
    else:
        what = f"{short(checked)} was closed{when} since Heron checked it, and {short(current)} is in front now"
    return (
        f"{what}. Call autocad_status first, so Heron knows the units of the drawing open now and "
        f"the change goes where you mean it. {NOTHING_SENT}"
    )


def judge(checked: str, current: str, mark: Mark | None, pid: int | None, history: dict[str, Any] | None) -> Verdict:
    """What the events since Heron's check say about a change to ``current``."""
    if mark is None or history is None:
        return Verdict()
    if pid != mark.pid or history.get("epoch") != mark.epoch:
        return Verdict(refusal=other_session(checked))
    # Some dropped off unread: what is left is still judged, but nothing is
    # followed on it, and the mark stays, so the name compare decides the rest.
    lost = history.get("lost") is True
    name, renamed = checked, False
    for event in history.get("events") or []:
        if int(event.get("seq") or 0) <= mark.seq:
            continue
        kind, drawing, at = event.get("kind"), str(event.get("drawing") or ""), str(event.get("at") or "")
        if kind == "saved" and event.get("was") and _eq(str(event["was"]), name):
            name, renamed = drawing, True
        elif kind == "closed" and _eq(drawing, name):
            return Verdict(refusal=closed_since(name, at, current))
        elif kind == "opened" and _eq(drawing, current):
            return Verdict(refusal=opened_since(current, at))
    if lost:
        return Verdict()
    seen = int(history.get("seq") or 0) or None
    if renamed and _eq(current, name) and not _eq(current, checked):
        return Verdict(follow=current, seen=seen)
    return Verdict(seen=seen)
