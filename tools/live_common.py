"""What every live check shares: reading a tool's answer, judging it, the padlocks
a row needs, and the few things the runner does in AutoCAD itself.

The checks themselves live in ``live_check.py`` (groups D, E, F) and in one file
per later area: ``live_check_edits.py`` (AA), ``live_check_layers.py`` (AB),
``live_check_blocks.py`` (AC, Y), ``live_check_render.py`` (AE), ``live_check_drawing.py`` (AP, AM),
``live_check_mep3d.py`` (AH), ``live_check_styles.py`` (AN, AL), ``live_check_ribbon2.py`` (AQ), ``live_check_cleanup.py`` (AD) and ``live_check_heron.py`` (M to Z, AG, AJ, RV:
Heron's own behaviour). Every check calls Heron's
tools the way a chat does, through the gate, and **measures** the answer: a
count, a size, a refusal's words, a value read back.

Two rules keep the offline tests honest (``tests/live_fakes.py`` plays recorded
answers into the checks):

- A check calls a tool as ``module.autocad_name(...)``, never a function
  imported on its own, so a test can put a recorded answer in its place.
- Anything the runner does in AutoCAD without Heron - its own scratch drawings,
  a line "the modeller" draws by hand, reading a property no tool reports - is a
  function here, called as ``lc.name(...)``, so a test can stand in for it too.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from autocad_mcp.core.answers import body, split  # noqa: E402
from autocad_mcp.tools import document  # noqa: E402

TOLERANCE = 1e-4


class Failed(Exception):
    """A row that did not measure up. The message is the evidence."""


class Refused(Exception):
    """A row the padlocks or the machine would not let run."""


def parse(raw: Any) -> dict[str, Any]:
    """A tool result as data. An 'Error: ...' reply becomes the right exception.

    A change job's answer starts with one plain line (DONE, REFUSED, ...: D-62): it is dropped here.
    """
    if not isinstance(raw, str):
        return raw
    raw = body(raw)
    if raw.startswith("Error:"):
        low = raw.lower()
        if any(word in low for word in ("padlock", "press heron", "not connected", "admin", "publish")):
            raise Refused(raw[7:].strip())
        raise Failed(raw[7:].strip())
    try:
        return json.loads(raw)
    except ValueError:
        return {"text": raw}


def expect(condition: Any, message: str) -> None:
    if not condition:
        raise Failed(message)


def near(got: float | None, want: float, tol: float = TOLERANCE) -> bool:
    return got is not None and abs(float(got) - float(want)) <= tol


def near_point(got: Any, want: Any, tol: float = 1e-6) -> bool:
    """Two points the same to tol, comparing as many coordinates as both have (x, y or x, y, z)."""
    if not got or not want:
        return False
    return all(abs(float(a) - float(b)) <= tol for a, b in zip(got, want, strict=False))


def refusal(raw: Any) -> str:
    """The message from a reply that must be a refusal; raises if it was allowed."""
    raw = body(raw)
    expect(isinstance(raw, str) and raw.startswith("Error:"), f"expected a refusal, got: {str(raw)[:120]}")
    return raw[7:].strip()


def first_line(raw: Any) -> str:
    """The plain first line of a change job's answer (DONE - ..., NOTHING CHANGED - ...), or ''."""
    head, _ = split(raw) if isinstance(raw, str) else (None, raw)
    return head or ""


def dist(a: Any, b: Any) -> float:
    return math.dist([float(v) for v in a[:2]], [float(v) for v in b[:2]])


# ---------------------------------------------------------------------------
# What a row needs, beyond Changes on and Ask to Keep off
# ---------------------------------------------------------------------------

# The runner never moves a padlock (D-59): only the modeller's click does. A row
# that needs one in the other position is reported "not run this time" and the
# result already in the register is left alone.
NEEDS: dict[str, tuple[str, bool, str]] = {
    "admin": ("admin", True, "Admin on (Settings, or type HERONADMIN)"),
    "no_admin": ("admin", False, "Admin off"),
    "publish": ("publish", True, "Publish on (Settings, or type HERONPUBLISH)"),
    "no_publish": ("publish", False, "Publish off"),
}


def unmet(needs: frozenset[str], padlocks: dict[str, Any]) -> str | None:
    """Why a row cannot run with the padlocks as they are, or None when it can."""
    missing = [NEEDS[n][2] for n in sorted(needs) if padlocks.get(NEEDS[n][0]) is not NEEDS[n][1]]
    if not missing:
        return None
    return "not run this time: it needs " + " and ".join(missing)


def describe_needs(needs: frozenset[str]) -> str:
    return " and ".join(NEEDS[n][2].split(" (")[0] for n in sorted(needs))


# ---------------------------------------------------------------------------
# The rows
# ---------------------------------------------------------------------------


@dataclass
class Context:
    """What the checks share: the version, the padlocks, the scratch drawings, a few things passed along."""

    version: str = "unknown"
    store: dict[str, Any] = field(default_factory=dict)
    padlocks: dict[str, Any] = field(default_factory=dict)
    scratch: str | None = None  # the scratch drawing's name, as AutoCAD lists it
    folder: Path | None = None  # the runner's own folder, once a row needed a saved drawing
    extra: list[str] = field(default_factory=list)  # other drawings the runner opened


@dataclass(frozen=True)
class Check:
    row: str
    group: str
    title: str
    run: Callable[[Context], Awaitable[str]]
    needs: frozenset[str] = frozenset()


_GROUP = re.compile(r"^([A-Z]+)\d")


def group_of(row: str) -> str:
    """The group a row id belongs to: 'AA' for AA12, 'E' for E4, 'A' for A8e."""
    match = _GROUP.match(row)
    return match.group(1) if match else row


async def entity_count() -> int:
    """Model-space entities, read from status so it costs no undo step."""
    status = parse(await document.autocad_status())
    return int((status.get("active_drawing") or {}).get("model_space_entities") or 0)


async def variable(name: str) -> Any:
    return parse(await document.autocad_get_variable(name=name)).get("value")


async def recheck() -> dict[str, Any]:
    """autocad_status again: the gate wants the units checked in a drawing it has not seen."""
    return parse(await document.autocad_status())


# ---------------------------------------------------------------------------
# Done in AutoCAD by the runner itself, not through Heron
# ---------------------------------------------------------------------------
#
# Kept to the few things no tool does: the runner's own scratch drawings, a
# change "the modeller" makes by hand, and reading back a property no tool
# reports. None of them goes near the modeller's own drawings.


def _plain(value: Any) -> Any:
    if hasattr(value, "Red") and hasattr(value, "Blue"):
        return [int(value.Red), int(value.Green), int(value.Blue)]
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return str(value)


async def read_padlocks() -> dict[str, Any] | None:
    """The padlocks of the AutoCAD this run works in, read from its plug-in (D-59); None when it cannot tell.

    With the plug-in switched off (HERON_AUTOCAD_BRIDGE=off, a developer's run)
    there are no padlocks: every level is open and nothing asks.
    """
    import asyncio

    from autocad_mcp.core import diagnose, sessions
    from autocad_mcp.core.bridge import bridge_enabled
    from autocad_mcp.tools import explain

    if not bridge_enabled():
        return {"changes": True, "publish": True, "admin": True, "ask_to_keep": False, "held": [], "bridge": "off"}
    return await asyncio.to_thread(explain.padlocks_now, diagnose.report(), sessions.chosen())


def _doc_named(app: Any, name: str) -> Any:
    for i in range(int(app.Documents.Count)):
        doc = app.Documents.Item(i)
        if str(doc.Name) == name:
            return doc
    return None


async def save_scratch(ctx: Context) -> Path:
    """Save the scratch drawing into the runner's own folder (once), for rows that need a drawing on disk.

    The folder is new and empty, in %TEMP%, and is removed at the end of the
    run. Checked again with autocad_status, since the drawing's name changes.
    """
    import tempfile

    from autocad_mcp.core.connection import get_app, run

    if ctx.folder is None:
        ctx.folder = Path(tempfile.mkdtemp(prefix="heron-live-check-"))
    target = ctx.folder / "project" / "live-check.dwg"
    target.parent.mkdir(parents=True, exist_ok=True)
    if ctx.scratch and ctx.scratch.lower() == target.name.lower():
        return target

    def save() -> str:
        app = get_app()
        doc = _doc_named(app, ctx.scratch) if ctx.scratch else app.ActiveDocument
        doc.Activate()
        doc.SaveAs(str(target))
        return str(doc.Name)

    ctx.scratch = await run(save)
    await recheck()
    return target


async def other_drawing(ctx: Context, folder: str, name: str = "other.dwg") -> Path:
    """A second scratch drawing, saved in its own folder of the runner's folder, made active and checked."""
    import tempfile

    from autocad_mcp.core.connection import get_app, run

    if ctx.folder is None:
        ctx.folder = Path(tempfile.mkdtemp(prefix="heron-live-check-"))
    target = ctx.folder / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)

    def make() -> str:
        app = get_app()
        doc = app.Documents.Add()
        doc.SaveAs(str(target))
        doc.Activate()
        return str(doc.Name)

    made = await run(make)
    ctx.extra.append(made)
    await recheck()
    return target


async def new_drawing(ctx: Context) -> str:
    """Another new drawing, never saved, made active and checked. Its name (Drawing2.dwg ...)."""
    from autocad_mcp.core.connection import get_app, run

    def make() -> str:
        doc = get_app().Documents.Add()
        doc.Activate()
        return str(doc.Name)

    made = await run(make)
    ctx.extra.append(made)
    await recheck()
    return made


async def save_active(ctx: Context) -> None:
    """Save the active drawing where it is: only ever one of the runner's own, already saved in its folder."""
    from autocad_mcp.core.connection import get_doc, run

    def save() -> None:
        doc = get_doc()
        if str(doc.Name) not in [ctx.scratch, *ctx.extra] or ctx.folder is None or not str(doc.FullName).startswith(str(ctx.folder)):
            raise Failed(f"the runner saves only its own drawings, not {doc.Name}")
        doc.Save()

    await run(save)


async def save_as(ctx: Context, target: Path) -> str:
    """Save As the active drawing, as the modeller does by hand (not through Heron). Its new name. No status check."""
    from autocad_mcp.core.connection import get_doc, run

    def save() -> tuple[str, str]:
        doc = get_doc()
        was = str(doc.Name)
        if was not in [ctx.scratch, *ctx.extra]:
            raise Failed(f"the runner saves only its own drawings, not {was}")
        doc.SaveAs(str(target))
        return was, str(doc.Name)

    was, now = await run(save)
    ctx.extra = [now if n == was else n for n in ctx.extra]
    if ctx.scratch == was:
        ctx.scratch = now
    return now


async def close_drawing(ctx: Context, name: str) -> None:
    """Close one of the runner's own drawings without saving, as the modeller does by hand. No status check."""
    from autocad_mcp.core.connection import get_app, run

    if name not in ctx.extra:
        raise Failed(f"the runner closes only its own drawings, not {name}")

    def close() -> None:
        doc = _doc_named(get_app(), name)
        if doc is not None:
            doc.Close(False)

    await run(close)
    ctx.extra.remove(name)


async def open_drawing(ctx: Context, path: Path) -> str:
    """Open a drawing from the runner's own folder, as the modeller does by hand, and leave it in front. No status check."""
    from autocad_mcp.core.connection import get_app, run

    def open_it() -> str:
        doc = get_app().Documents.Open(str(path))
        doc.Activate()
        return str(doc.Name)

    opened = await run(open_it)
    ctx.extra.append(opened)
    return opened


async def activate(ctx: Context, name: str | None = None) -> None:
    """Make a drawing active (the scratch drawing when no name is given) and check it again."""
    from autocad_mcp.core.connection import get_app, run

    wanted = name or ctx.scratch

    def go() -> None:
        doc = _doc_named(get_app(), str(wanted))
        if doc is None:
            raise Failed(f"the drawing {wanted} is not open any more")
        doc.Activate()

    await run(go)
    await recheck()


async def drawing_names() -> list[str]:
    """The drawings open in AutoCAD, by name."""
    from autocad_mcp.core.connection import get_app, run

    def names() -> list[str]:
        app = get_app()
        return [str(app.Documents.Item(i).Name) for i in range(int(app.Documents.Count))]

    return await run(names)


async def read_props(handle: str, names: list[str]) -> dict[str, Any]:
    """Read properties no tool reports (Lineweight, ConstantWidth, TrueColor ...); None for one it lacks."""
    from autocad_mcp.acad.entities import resolve_handle
    from autocad_mcp.core.connection import get_doc, run

    def read() -> dict[str, Any]:
        entity = resolve_handle(get_doc(), handle)
        out: dict[str, Any] = {}
        for name in names:
            try:
                out[name] = _plain(getattr(entity, name))
            except BaseException:  # noqa: BLE001 - a property this object does not have
                out[name] = None
        return out

    return await run(read)


async def exists(handle: str) -> bool:
    """Whether an object with this handle is in the active drawing (not erased)."""
    from autocad_mcp.core.connection import get_doc, run

    def look() -> bool:
        try:
            entity = get_doc().HandleToObject(handle)
        except BaseException:  # noqa: BLE001 - no such handle, or erased
            return False
        return entity is not None

    return await run(look)


async def by_hand_line(start: list[float], end: list[float]) -> str:
    """A line drawn as the modeller draws one: straight into model space, not through Heron. Its handle."""
    from autocad_mcp.core.connection import get_doc, run
    from autocad_mcp.core.variants import apoint

    def draw() -> str:
        doc = get_doc()
        line = doc.ModelSpace.AddLine(apoint(*start), apoint(*end))
        return str(line.Handle)

    return await run(draw)


async def by_hand_group(handles: list[str], name: str) -> str:
    """A group made as the modeller makes one with GROUP (name '*' for an unnamed one), not through Heron."""
    from autocad_mcp.core.connection import get_doc, run
    from autocad_mcp.core.variants import object_array

    def make() -> str:
        doc = get_doc()
        group = doc.Groups.Add(name)
        group.AppendItems(object_array([doc.HandleToObject(h) for h in handles]))
        return str(group.Name)

    return await run(make)


async def by_hand_width(handle: str, segment: int, start: float, end: float) -> None:
    """Give one polyline segment a tapering width, as the modeller does in Properties (no tool sets one)."""
    from autocad_mcp.acad.entities import resolve_handle
    from autocad_mcp.core.connection import get_doc, run

    def taper() -> None:
        resolve_handle(get_doc(), handle).SetWidth(segment, float(start), float(end))

    await run(taper)


async def by_hand_true_colour(handle: str, rgb: list[int]) -> None:
    """Give an object a true colour (RGB), as the modeller does in Properties (no tool sets one)."""
    from autocad_mcp.acad.entities import resolve_handle
    from autocad_mcp.core.connection import get_app, get_doc, run

    def paint() -> None:
        entity = resolve_handle(get_doc(), handle)
        version = str(get_app().Version).split(".")[0]
        colour = get_app().GetInterfaceObject(f"AutoCAD.AcCmColor.{version}")
        colour.SetRGB(int(rgb[0]), int(rgb[1]), int(rgb[2]))
        entity.TrueColor = colour

    await run(paint)


def origin(row: str) -> tuple[float, float]:
    """A spot in the scratch drawing that belongs to one row, so no two rows' objects meet.

    Far from where groups D, E and F draw (x below 100,000): x from 2,000,000
    by group, y by row number.
    """
    group = group_of(row)
    rank = sum((ord(c) - 64) * 27**i for i, c in enumerate(reversed(group)))
    tail = row[len(group):]
    number = int(re.sub(r"\D", "", tail) or 0)
    extra = 5000.0 if tail and tail[-1].isalpha() else 0.0
    return 2_000_000.0 + 100_000.0 * rank, 10_000.0 * number + extra


def files_in(folder: Path, pattern: str = "*") -> list[str]:
    """The names of the files in a folder that match a pattern, sorted; [] when there is no folder."""
    try:
        return sorted(p.name for p in Path(folder).glob(pattern) if p.is_file())
    except OSError:
        return []


def file_stamp(path: Path) -> tuple[int, float] | None:
    """(size, modified time) of a file, or None when there is none."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime
