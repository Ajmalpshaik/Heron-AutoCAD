r"""Sharing check lists with the team: the office folder and the project folder (#135, D-93).

autocad_checklist reads the office lists from the office folder and the
project's changes from the project folder; this tool writes them there. That
writes outside Heron's own folder, into folders the whole team reads, so it is
a Publish tool of its own (D-65): its padlock is a property of the tool.

Never a silent overwrite of a teammate's file:
  - a file there that already holds something different is replaced only with
    replace=true, and the refusal says who saved it, when, and what differs;
  - when it is replaced, what was there is kept in the same file as 'previous'
    (who, when and its contents), so one step back is always there;
  - the file is written beside itself and swapped in, and only if nobody
    changed it in between; a file that changed is left alone.
Who may change the office list is decided by the folder's own Windows
permissions: a read-only office folder refuses, saying so. Heron adds no roles.
"""

from __future__ import annotations

import asyncio
import getpass
import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import checklist
from ..core.connection import get_doc, run
from ..core.errors import AutocadError
from ..core.project_notes import project_of
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from . import checklists as store

MOST_PREVIOUS_TEXT = 20000


def who() -> str:
    """The Windows user saving, so a teammate can see who changed the office list."""
    try:
        return getpass.getuser() or "someone"
    except Exception:  # noqa: BLE001 - no user name: say so plainly
        return "someone"


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return info.st_mtime_ns, info.st_size


def read_existing(path: Path) -> tuple[tuple[int, int] | None, dict[str, Any] | None, str]:
    """(its stamp or None when there is no file, its JSON or None when unreadable, its text)."""
    stamp = _stamp(path)
    if stamp is None:
        return None, None, ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AutocadError(f"{path} is there but could not be read ({exc}). Nothing was written.") from None
    try:
        data = json.loads(text)
    except ValueError:
        return stamp, None, text
    return stamp, data if isinstance(data, dict) else None, text


def write_over(path: Path, content: dict[str, Any], before: tuple[int, int] | None) -> None:
    """Write beside the file, then swap it in, only if nobody changed it since it was read."""
    temp = path.with_name(f".{path.name}.{os.getpid()}.heron-tmp")
    try:
        temp.write_text(json.dumps(content, indent=2), encoding="utf-8")
        if _stamp(path) != before:
            raise AutocadError(
                f"{path} changed while Heron was writing (a teammate saved it at the same time?). It was left as "
                "it is and nothing was written. Look at it, then try again."
            )
        os.replace(temp, path)
    except PermissionError:
        raise AutocadError(
            f"{path.parent} is read-only for you, so nothing was written. Whoever keeps the office's lists "
            "can put it there, or give you write access to that folder."
        ) from None
    except OSError as exc:
        raise AutocadError(f"{path} could not be written ({exc}). Nothing was written.") from None
    finally:
        temp.unlink(missing_ok=True)


def _saved(data: dict[str, Any] | None) -> str:
    if not data:
        return "in a form Heron cannot read"
    return f"saved by {data.get('saved_by') or 'someone'} on {data.get('saved_at') or 'an unknown date'}"


def previous_of(data: dict[str, Any] | None, text: str) -> dict[str, Any]:
    """What is being replaced, kept one step back: never its own 'previous'."""
    if data is None:
        return {"unreadable_text": text[:MOST_PREVIOUS_TEXT]}
    return {key: value for key, value in data.items() if key != "previous"}


def check_differences(old: list[Any], new: list[dict[str, Any]]) -> str:
    """'added x; removed y; changed z' between two lists of checks, by id."""
    before = {str(c.get("id")): c for c in old or [] if isinstance(c, dict)}
    after = {c["id"]: c for c in new}
    parts = []
    for word, ids in (
        ("adds", sorted(set(after) - set(before))),
        ("removes", sorted(set(before) - set(after))),
        ("changes", sorted(k for k in set(after) & set(before) if after[k] != before[k])),
    ):
        if ids:
            parts.append(f"yours {word} {', '.join(ids)}")
    if not parts and [c["id"] for c in new] != list(before):
        parts.append("yours puts the checks in another order")
    return "; ".join(parts) or "the name or the layout of the file differs"


def share_office_list(name: str, checks: list[dict[str, Any]] | None, replace: bool) -> dict[str, Any]:
    """Put a list in the office folder: the checks given, else this PC's own list of that name."""
    folder = store.office_folder()
    if folder is None:
        raise AutocadError(
            "No office folder is set on this PC. Set it first with "
            "autocad_checklist(action='office_folder', folder='S:\\...'). Nothing was written."
        )
    if not store.reachable(folder):
        raise AutocadError(f"The office folder {folder} could not be reached from this PC. Nothing was written.")
    if checks:
        try:
            clean = checklist.validate(checks)
        except ValueError as exc:
            raise AutocadError(f"{exc} Nothing was written.") from None
        title, came = name.strip(), "the checks given in this chat"
    else:
        own = store._file(name)
        if own.is_file():
            try:
                record = store._read_record(own)
            except (OSError, ValueError) as exc:
                raise AutocadError(f"This PC's list {own} could not be read ({exc}). Nothing was written.") from None
            clean, title, came = checklist.validate(record["checks"]), str(record["name"]), f"this PC's list {own}"
        elif store._slug(name) == store._slug(checklist.STARTER["name"]):
            clean = checklist.validate(checklist.STARTER["checks"])
            title, came = checklist.STARTER["name"], "the 'before issue' list that ships with Heron"
        else:
            raise AutocadError(
                f"This PC has no list called '{name}' to share. Give the checks in 'checks', or save the list "
                "first with autocad_checklist(action='save'). Nothing was written."
            )
    target = folder / f"{store._slug(title)}.json"
    stamp, old, text = read_existing(target)
    if stamp is not None and old is not None and old.get("checks") == clean and old.get("name") == title:
        return {"written": False, "file": str(target), "said": f"The office folder already holds exactly this list '{title}'; nothing was written."}
    content: dict[str, Any] = {"name": title, "checks": clean, "saved_by": who(), "saved_at": store.now()}
    if stamp is not None:
        if not replace:
            differs = check_differences((old or {}).get("checks") or [], clean) if old else "it cannot be read as a check list"
            raise AutocadError(
                f"The office folder already has the list '{title}' ({target}), {_saved(old)}, and it is different: "
                f"{differs}. Nothing was written: it may be a teammate's. Look at it first "
                f"(autocad_checklist(action='list', name='{title}')); to replace it, call again with replace=true, "
                "and the list there now is kept in the file as 'previous'."
            )
        content["previous"] = previous_of(old, text)
    write_over(target, content, stamp)
    return {"written": True, "file": str(target), "list": title, "checks": len(clean), "from": came,
            "replaced": stamp is not None, "saved_by": content["saved_by"]}  # fmt: skip


def share_project_changes(drawing: str, name: str, changes: list[dict[str, Any]] | None, replace: bool) -> dict[str, Any]:
    """Put this project's changes to the list 'name' in the project folder, for the team."""
    target = store.shared_project_file(drawing)
    if target is None:
        raise AutocadError("This drawing is not saved yet, so it has no project folder. Save it first; nothing was written.")
    record = store.load(name)
    office = checklist.validate(record.get("checks", []))
    key = store._list_key(record["name"])
    project = project_of(drawing)
    if changes is None:
        changes = store._own_project_changes(project, record["name"]) if project else []
        came = "this PC's own changes for this project"
        if not changes:
            raise AutocadError(
                f"This PC keeps no changes to '{record['name']}' for this project, so there is nothing to share. "
                "Give them in 'changes' ([] removes the project's). Nothing was written."
            )
    else:
        came = "the changes given in this chat"
    try:
        clean = checklist.validate_changes(office, changes)
    except ValueError as exc:
        raise AutocadError(f"{exc} Nothing was written.") from None
    stamp, old, text = read_existing(target)
    if stamp is not None and old is None:
        raise AutocadError(
            f"{target} is there but is not a file Heron can read, so it was left as it is. Put it right or move "
            "it away first. Nothing was written."
        )
    held = ((old or {}).get("changes") or {}).get(key)
    if (held or []) == clean:
        return {"written": False, "file": str(target), "said": f"The project folder already holds exactly these changes to '{record['name']}'; nothing was written."}
    if held is not None and not replace:
        raise AutocadError(
            f"The project folder already holds changes to '{record['name']}' ({target}), {_saved(old)}: "
            f"{json.dumps(held)}. Yours are different, and nothing was written: they may be a teammate's. "
            "To replace them, call again with replace=true; what is there now is kept in the file as 'previous'."
        )
    content: dict[str, Any] = {
        "heron": "Check list changes for the drawings in this folder, shared by the team (Heron AI for AutoCAD).",
        "changes": dict((old or {}).get("changes") or {}),
        "saved_by": who(),
        "saved_at": store.now(),
    }
    if clean:
        content["changes"][key] = clean
    else:
        content["changes"].pop(key, None)
    if old is not None:
        content["previous"] = previous_of(old, text)
    write_over(target, content, stamp)
    return {"written": True, "file": str(target), "list": record["name"], "changes": clean, "from": came,
            "replaced": held is not None, "saved_by": content["saved_by"]}  # fmt: skip


@mcp.tool(name="autocad_share_checklist", **tool_meta("Share A Check List With The Team"))
@tool_errors
async def autocad_share_checklist(
    share: Annotated[
        Literal["office_list", "project_changes"],
        Field(description=(
            "'office_list': put the check list 'name' in the office folder, for every PC. "
            "'project_changes': put this project's changes to the list in the drawing's folder, for "
            "everyone on the job."
        )),
    ],
    name: Annotated[str, Field(min_length=1, description="The check list, e.g. 'before issue'.")] = checklist.STARTER["name"],
    checks: Annotated[
        list[dict] | None,
        Field(description="office_list: the checks, as for autocad_checklist(action='save'). Default: this PC's own list of that name."),
    ] = None,
    changes: Annotated[
        list[dict] | None,
        Field(description=(
            "project_changes: {id, severity, target, on} per office check, as for "
            "autocad_checklist(action='project'). Default: this PC's own changes for this project. [] removes them."
        )),
    ] = None,
    replace: Annotated[
        bool,
        Field(description="True only when the modeller has seen what is there and wants it replaced; it is kept as 'previous'."),
    ] = False,
) -> str:
    """Share a check list with the team: the office list into the office folder, or a project's changes into its folder.

    office_list writes '<office folder>\\<list>.json' (the office folder is set
    once per PC with autocad_checklist(action='office_folder')); every PC that
    points at that folder runs it from then on. project_changes writes
    '<the drawing's folder>\\Heron check list changes.json', so everyone who
    opens a drawing from that folder runs the list with the same changes
    (severity, target, on/off only, as always); it wins over each PC's own.

    It never overwrites a teammate's file silently: a file that already holds
    something different is refused, saying who saved it, when, and what
    differs, unless replace=true - and then what was there is kept in the file
    as 'previous'. A file a teammate saves while this one is written is left
    alone. Who may change the office list is the folder's own Windows
    permissions: a read-only folder is refused, saying so. The drawing is not
    changed; writing these files needs the Publish padlock.

    Returns:
        str: JSON: {"written", "file", "list", "checks" | "changes", "from",
             "replaced", "saved_by"}, or {"written": false, "said"} when the
             file already holds exactly this.

    Examples:
        - Use when: "put our 'before issue' list on the shared drive for
          everyone" -> office_list (set the office folder first).
        - Use when: "everyone on this job skips the xref check" ->
          project_changes with changes [{id: xrefs_found, on: false}].
        - Use when: after autocad_checklist(action='project') on this PC: "share
          these changes with the team" -> project_changes with no changes.
        - Don't use when: the list is only for this PC -
          autocad_checklist(action='save').
        - Don't use when: the run's results should be sent with the drawings -
          autocad_checklist_report.

    Error Handling:
        - No office folder set, or it cannot be reached: refused; nothing written.
        - A different file already there: refused naming who and when, unless
          replace=true.
        - A wrong check or change is refused naming the line; nothing written.
        - An unsaved drawing has no project folder: refused.
    """
    if share == "office_list":
        return dumps(await asyncio.to_thread(share_office_list, name, checks, replace))
    drawing = await run(lambda: store._drawing_of(get_doc()))
    return dumps(await asyncio.to_thread(share_project_changes, drawing, name, changes, replace))
