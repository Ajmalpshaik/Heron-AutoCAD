"""Which AutoCAD Heron works in, when more than one is connected (D-49).

COM hands this server whichever AutoCAD registered first, which is not
always the one the modeller means: two versions side by side, or Civil and
plain AutoCAD. A change landing in the other one, without a word, is the
worst outcome there is. So (the idea is Heron AI for Revit's session
binding, its docs/25):

- One AutoCAD connected to Heron (its Heron button pressed): Heron works in
  that one, whichever COM would have given.
- Two or more connected and none picked: nothing is sent until the chat picks
  one with autocad_use_autocad.
- The picked one closes or disconnects: Heron stops and says so. It never
  moves on to another AutoCAD by itself.
- None connected: COM's own choice, and the gate says "press Heron".

The answer is read from the address files the Heron button writes, so it
costs no COM call. It is kept for a moment, because a tool asks for the
AutoCAD several times per call.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from .errors import AutocadError

NOTHING_SENT = "Nothing was sent to AutoCAD."
_lock = threading.Lock()
_chosen: int | None = None
_seen: tuple[float, list[dict[str, Any]]] = (0.0, [])
FRESH = 1.0  # seconds a look at the address files is reused


def connected() -> list[dict[str, Any]]:
    """Every AutoCAD whose Heron button is pressed, newest look at most FRESH seconds old."""
    global _seen
    from . import diagnose  # diagnose imports the bridge, which imports nothing of ours

    with _lock:
        stamp, found = _seen
        if time.monotonic() - stamp < FRESH:
            return list(found)
    found = diagnose.connected_autocads()
    with _lock:
        _seen = (time.monotonic(), found)
    return list(found)


def forget() -> None:
    """Drop the pick and the cached look (tests, and a fresh server)."""
    global _chosen, _seen
    with _lock:
        _chosen = None
        _seen = (0.0, [])


def chosen() -> int | None:
    return _chosen


def describe(acad: dict[str, Any]) -> str:
    return f"AutoCAD {acad.get('acad_version') or '?'} (process {acad['pid']})"


def _listing(found: list[dict[str, Any]]) -> str:
    return "; ".join(describe(acad) for acad in found)


def choose(pid: int) -> dict[str, Any]:
    """Pick the AutoCAD to work in. Raises when it is not connected to Heron."""
    global _chosen, _seen
    with _lock:
        _seen = (0.0, [])  # look again, now
    found = connected()
    match = next((acad for acad in found if acad["pid"] == pid), None)
    if match is None:
        raise AutocadError(
            f"No AutoCAD connected to Heron has process {pid}. "
            + (f"Connected: {_listing(found)}." if found else "None is connected: press Heron in AutoCAD first.")
        )
    with _lock:
        _chosen = pid
    return match


def target() -> int | None:
    """The process Heron must work in, or None to take COM's own choice.

    Raises AutocadError, ending "Nothing was sent to AutoCAD.", when it cannot
    say which without asking.
    """
    from .bridge import bridge_enabled

    if not bridge_enabled() and _chosen is None:
        return None
    found = connected()
    pids = [acad["pid"] for acad in found]
    if _chosen is not None:
        if _chosen in pids:
            return _chosen
        raise AutocadError(
            f"The AutoCAD Heron was working in (process {_chosen}) has closed or was disconnected. "
            "Heron never moves on to another AutoCAD by itself. Press Heron in that AutoCAD again, "
            "or pick another with autocad_use_autocad. " + NOTHING_SENT
        )
    if len(pids) > 1:
        raise AutocadError(
            f"{len(pids)} AutoCADs are connected to Heron: {_listing(found)}. Heron will not guess "
            "which one you mean. Ask which, then call autocad_use_autocad with its process number. "
            + NOTHING_SENT
        )
    return pids[0] if pids else None
