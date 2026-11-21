"""The Heron Companion page: what this chat knows, in a browser beside AutoCAD (D-71).

Heron AI for Revit has a local page beside Revit (its docs/40, D-108). This is
AutoCAD's first one, kept deliberately small and safe:

- **A file, not a server.** The page is one HTML file in
  %LOCALAPPDATA%\\Heron\\autocad\\companion, one per chat, rewritten after
  every Heron job once the chat has asked for it (autocad_companion). No port
  is opened, nothing listens, and the page runs no script: it reloads itself
  every few seconds and fetches nothing.
- **No COM outside a job.** Writing the page reads only what the gate already
  holds: the chat's activity, the drawing Heron last checked, the change
  autocad_undo_last could take back. The drawing, view and selection come from
  autocad_companion's own READ job, and the page says when they were read.

Writing the page must never fail a job: every error is swallowed here.
"""

from __future__ import annotations

import html
import os
import time
from pathlib import Path
from typing import Any

REFRESH_SECONDS = 5
KEEP_DAYS = 7
MOST_ROWS = 50

_enabled = False
_snapshot: dict[str, Any] | None = None


def folder() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Heron" / "autocad" / "companion"


def page_path(conversation: str) -> Path:
    safe = "".join(ch for ch in conversation if ch.isalnum())[:16] or "chat"
    return folder() / f"heron-companion-{safe}.html"


def enabled() -> bool:
    return _enabled


def start(snapshot: dict[str, Any] | None) -> None:
    """The chat asked for the page: keep it up to date after every job from now on."""
    global _enabled, _snapshot
    _enabled = True
    if snapshot is not None:
        _snapshot = {**snapshot, "read_at": time.strftime("%H:%M:%S")}


def stop() -> None:
    global _enabled
    _enabled = False


def reset() -> None:
    """Tests, and a fresh server start."""
    global _enabled, _snapshot
    _enabled, _snapshot = False, None


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _changes(entry: dict[str, Any]) -> str:
    changes = entry.get("changes")
    if not changes:
        return ""
    return f"+{changes.get('added', 0)} ~{changes.get('modified', 0)} -{changes.get('erased', 0)}"


def render(state: dict[str, Any], snapshot: dict[str, Any] | None = None) -> str:
    """The page. state: version, conversation, drawing, activity (newest first), last_change, written_at."""
    snap = snapshot or {}
    selection = snap.get("selection") or {}
    kinds = ", ".join(f"{count} {kind}" for kind, count in (selection.get("types") or {}).items())
    rows = []
    for entry in (state.get("activity") or [])[:MOST_ROWS]:
        outcome = str(entry.get("outcome", ""))
        colour = {"done": "#e6f4e6", "refused": "#f4e6e6", "failed": "#f8d7d7", "discarded": "#ececec",
                  "dry_run": "#e8eef8", "unknown": "#fbeccb"}.get(outcome, "#ffffff")  # fmt: skip
        rows.append(
            f'<tr style="background:{colour}"><td>{_e(entry.get("at"))}</td><td>{_e(entry.get("what"))}</td>'
            f"<td>{_e(entry.get('risk'))}</td><td>{_e(outcome)}</td><td>{_e(_changes(entry))}</td>"
            f"<td>{_e(entry.get('seconds'))} s</td><td>{_e(Path(str(entry.get('drawing') or '')).name)}</td></tr>"
        )
    activity = "".join(rows) or '<tr><td colspan="7">Nothing yet in this chat.</td></tr>'
    last = state.get("last_change")
    undo = (
        f"{_e(last.get('what'))} at {_e(last.get('at'))}: Heron can take it back (autocad_undo_last)."
        if last else "Nothing Heron could take back on its own."
    )
    if snap:
        view = snap.get("view") or {}
        drawing_rows = (
            f"<tr><th>Drawing</th><td>{_e(snap.get('drawing'))}</td></tr>"
            f"<tr><th>Units</th><td>{_e(snap.get('units'))}</td></tr>"
            f"<tr><th>Layout</th><td>{_e(snap.get('layout'))}</td></tr>"
            f"<tr><th>View</th><td>centre {_e(view.get('centre'))}, height {_e(view.get('height'))}</td></tr>"
            f"<tr><th>Selection</th><td>{_e(selection.get('count', 0))} object(s){(': ' + _e(kinds)) if kinds else ''}</td></tr>"
            f"<tr><th>Read at</th><td>{_e(snap.get('read_at'))} - ask the chat to refresh the companion page to read them again</td></tr>"
        )
    else:
        drawing_rows = (
            f"<tr><th>Drawing</th><td>{_e(state.get('drawing') or 'not checked yet: ask for autocad_status')}</td></tr>"
        )
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
        "<title>Heron Companion</title><style>"
        "body{font-family:Segoe UI,Arial,sans-serif;margin:16px;color:#1d2a36;background:#f7f9fb}"
        "h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:18px 0 6px}"
        "table{border-collapse:collapse;width:100%;background:#fff}"
        "th,td{border:1px solid #d5dde5;padding:4px 8px;text-align:left;font-size:13px;vertical-align:top}"
        "th{background:#eef2f6;width:140px}.note{font-size:12px;color:#5a6b7b}"
        "</style></head><body>"
        "<h1>Heron Companion</h1>"
        f'<p class="note">Heron AI for AutoCAD {_e(state.get("version"))} - this chat - written {_e(state.get("written_at"))}. '
        f"It reloads every {REFRESH_SECONDS} s and only shows what the chat knows: it sends nothing to AutoCAD.</p>"
        f"<h2>Drawing</h2><table>{drawing_rows}</table>"
        f"<h2>Last change</h2><p>{undo}</p>"
        "<h2>What Heron did in this chat</h2><table>"
        "<tr><th>At</th><th>What</th><th>Level</th><th>Outcome</th><th>Objects</th><th>Took</th><th>Drawing</th></tr>"
        f"{activity}</table></body></html>"
    )


def write(state: dict[str, Any]) -> Path | None:
    """Write the page now, whole or not at all. None when it could not be written."""
    try:
        path = page_path(str(state.get("conversation") or ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(render({**state, "written_at": time.strftime("%H:%M:%S")}, _snapshot), encoding="utf-8")
        os.replace(temp, path)
        _tidy(path)
        return path
    except Exception:  # noqa: BLE001 - a page that cannot be written never fails a job
        return None


def _tidy(keep: Path) -> None:
    """Pages of chats that ended a week ago are removed; this chat's page stays."""
    cutoff = time.time() - KEEP_DAYS * 86400
    for old in keep.parent.glob("heron-companion-*.html"):
        try:
            if old != keep and old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
