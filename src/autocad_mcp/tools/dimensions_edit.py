"""Tidying dimensions already on the drawing: even spacing, and breaks at crossings (#116, D-80).

``autocad_space_dimensions`` is AutoCAD's DIMSPACE: a stack of parallel
dimensions, each dimension line moved so they sit an even distance apart off a
base dimension. COM cannot move a rotated dimension's line (it has no
definition points), so the plug-in reads where each line is and moves it
(DimLinePoint, D-40); the spacing itself is worked out here, in plain
functions tested without AutoCAD.

``autocad_break_dimensions`` is AutoCAD's DIMBREAK: neither COM nor .NET has a
call for a dimension break, so it is typed, with each dimension picked by its
handle and the automatic break at every crossing.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import Field

from ..acad.entities import resolve_handles, short_type
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import before_after, in_plugin

EPS = 1e-9
PARALLEL = 1e-6  # sine of the largest angle still called parallel
MAX_DIMENSIONS = 200
HANDLE = re.compile(r"[0-9A-Fa-f]{1,16}")

# How long a typed DIMBREAK gets before a prompt still open means it did not
# take its input. SendCommand normally returns with the command done.
COMMAND_WAIT_S = 2.0
COMMAND_POLL_S = 0.1


# ---------------------------------------------------------------------------
# The spacing (pure: no AutoCAD below this line)
# ---------------------------------------------------------------------------


def _unit2(vector: Sequence[float]) -> tuple[float, float] | None:
    x, y = float(vector[0]), float(vector[1])
    size = math.hypot(x, y)
    return None if size < EPS else (x / size, y / size)


def plan_spacing(
    dims: Sequence[dict[str, Any]], spacing: float, base: str | None = None
) -> dict[str, Any]:
    """Where each dimension line goes so the stack is evenly spaced off the base.

    ``dims`` are the dimensions as the plug-in reads them: ``{"handle",
    "direction": [ux, uy], "line_point": [x, y, z]}`` — the direction the
    dimension line runs and a point it passes through. The base dimension stays
    where it is. Every other one keeps the side of the base it is on and its
    order out from it, and is put at 1, 2, 3 ... times ``spacing`` from the base
    line. ``spacing=0`` lines them all up on the base line, as DIMSPACE does.

    Returns ``{"base", "moves": [{"handle", "from", "to", "offset_was",
    "offset_now"}], "already": [handle], "skipped": [{"handle", "why"}]}``.
    Raises ValueError, naming the problem, for a set that cannot be spaced.
    """
    if spacing < 0:
        raise ValueError(f"the spacing cannot be negative, got {spacing:g}; the side each dimension is on is kept for you")
    rows = list(dims)
    if len(rows) < 2:
        raise ValueError("spacing needs the base dimension and at least one more")
    handles = [str(d["handle"]).upper() for d in rows]
    if len(set(handles)) != len(handles):
        raise ValueError("a dimension is given twice")
    base_key = str(base).upper() if base else handles[0]
    if base_key not in handles:
        raise ValueError(f"the base dimension {base} is not one of the dimensions given")
    first = rows[handles.index(base_key)]
    u = _unit2(first["direction"])
    if u is None:
        raise ValueError(f"the base dimension {first['handle']} has no direction (its extension lines meet)")
    n = (-u[1], u[0])
    bx, by = float(first["line_point"][0]), float(first["line_point"][1])

    skipped: list[dict[str, str]] = []
    sides: dict[int, list[tuple[float, int, dict[str, Any]]]] = {1: [], -1: []}
    for order, dim in enumerate(rows):
        if str(dim["handle"]).upper() == base_key:
            continue
        v = _unit2(dim["direction"])
        if v is None or abs(u[0] * v[1] - u[1] * v[0]) > PARALLEL:
            skipped.append({"handle": str(dim["handle"]), "why": "not parallel to the base dimension, so it was left where it is"})
            continue
        px, py = float(dim["line_point"][0]), float(dim["line_point"][1])
        offset = (px - bx) * n[0] + (py - by) * n[1]
        sides[1 if offset >= 0 else -1].append((abs(offset), order, dim))

    moves: list[dict[str, Any]] = []
    already: list[str] = []
    for sign, members in sides.items():
        for k, (_, _, dim) in enumerate(sorted(members, key=lambda m: (m[0], m[1])), start=1):
            point = [float(v) for v in dim["line_point"]]
            was = (point[0] - bx) * n[0] + (point[1] - by) * n[1]
            target = sign * k * float(spacing)
            shift = target - was
            if abs(shift) < 1e-6:
                already.append(str(dim["handle"]))
                continue
            moved = [point[0] + shift * n[0], point[1] + shift * n[1], *point[2:3]]
            moves.append({
                "handle": str(dim["handle"]),
                "from": [round(v, 6) for v in point],
                "to": [round(v, 9) for v in moved],
                "offset_was": round(was, 6),
                "offset_now": round(target, 6),
            })
    return {"base": str(first["handle"]), "moves": moves, "already": already, "skipped": skipped}


def dimbreak_command(handles: Sequence[str], remove: bool = False) -> str:
    """The DIMBREAK command line: Multiple, each dimension picked by handle, then Break or Remove.

    Break with Multiple puts a break wherever each dimension crosses another
    object, which is DIMBREAK's Auto. Handles are checked as hex, so nothing
    but a handle reaches the command line.
    """
    picked: list[str] = []
    for h in handles:
        text = str(h).strip()
        if not HANDLE.fullmatch(text):
            raise ValueError(f"'{h}' is not a handle")
        if text.upper() not in (p.upper() for p in picked):
            picked.append(text)
    if not picked:
        raise ValueError("give at least one dimension")
    lines = ["_.DIMBREAK", "_M", *[f'(handent "{h}")' for h in picked], "", "_R" if remove else "_B"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# The AutoCAD side
# ---------------------------------------------------------------------------


def _try(getter, default=None, busy_ok=False):
    """One COM read or call that may fail; busy_ok for a restore, a cancel or a redraw (D-100)."""
    try:
        return getter()
    except BaseException as exc:  # noqa: BLE001 - absent properties are expected here
        if not busy_ok:
            raise_if_busy(exc)
        return default


def _check_handles(handles: Sequence[str]) -> list[str]:
    out: list[str] = []
    for h in handles:
        text = str(h).strip()
        if not HANDLE.fullmatch(text):
            raise AutocadError(f"'{h}' is not a handle. autocad_list_entities gives current handles.")
        if text.upper() in (o.upper() for o in out):
            raise AutocadError(f"The dimension {text} is given twice.")
        out.append(text)
    return out


@mcp.tool(name="autocad_space_dimensions", **tool_meta("Space Dimensions Evenly", idempotent=True))
@tool_errors
async def autocad_space_dimensions(
    handles: Annotated[
        list[str],
        Field(
            min_length=2,
            max_length=MAX_DIMENSIONS,
            description=(
                "The stacked, parallel dimensions to space, by handle — the base first unless you "
                "name it in 'base'. Linear (horizontal, vertical, rotated) and aligned dimensions."
            ),
        ),
    ],
    spacing: Annotated[
        float,
        Field(
            ge=0,
            description=(
                "Distance between one dimension line and the next, in drawing units: about 7 to "
                "10 mm of paper, so 350 to 500 at 1:50. 0 lines them all up on the base line."
            ),
        ),
    ],
    base: Annotated[
        str | None,
        Field(default=None, description="The dimension that stays put, by handle. Defaults to the first one given."),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(default=False, description="Report where each dimension line would go and move nothing."),
    ] = False,
) -> str:
    """Space a stack of parallel dimensions evenly off a base dimension: AutoCAD's DIMSPACE.

    The base dimension stays put. Every other one keeps the side of it that it
    is on and its order out from it, and its dimension line is moved to 1, 2,
    3 ... times the spacing from the base line. Only the dimension lines move:
    the extension line origins stay on the geometry. spacing=0 lines them all
    up on the base line.

    The plug-in reads where each dimension line is and moves it; the spacing
    is worked out here. One undo step.

    Args:
        handles (list[str]): the dimensions, base first unless 'base' says.
        spacing (float): gap between dimension lines; 0 lines them up.
        base (Optional[str]): the dimension that stays put.
        dry_run (bool): report only.

    Returns:
        str: JSON: {"base": str, "spacing": float, "moved": int,
             "moves": [{"handle", "from", "to", "offset_was", "offset_now"}],
             "already": [str], "skipped": [{"handle", "why"}],
             "before_after": [{handle, property, from, to}]}

    Examples:
        - Use when: "space these baseline dimensions 400 apart" — the handles,
          the innermost first, spacing=400.
        - Use when: "the overall and the chain are on top of each other" —
          the chain as base, the overall with it, spacing about 8 mm of paper.
        - Use when: "line these dimensions up" — spacing=0.
        - Don't use when: you are dimensioning a run from scratch —
          autocad_dimension_run spaces a baseline set as it draws it.

    Error Handling:
        - A dimension that is not parallel to the base is left where it is and
          listed in "skipped"; one that is not linear or aligned is skipped too.
        - Fewer than two dimensions, a base that is not in the list, or a
          negative spacing is refused before anything moves.
    """
    wanted = _check_handles(handles)
    if base is not None and str(base).strip().upper() not in (h.upper() for h in wanted):
        raise AutocadError(f"The base dimension {base} is not one of the handles given.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        read = in_plugin("dimension_lines", {"handles": wanted}, "Reading where dimension lines are", changes=False)
        found = list(read.get("dimensions") or [])
        unread = list(read.get("skipped") or [])
        if not any(str(d.get("handle", "")).upper() == str(base or wanted[0]).strip().upper() for d in found):
            why = next((s.get("why") for s in unread if str(s.get("handle", "")).upper() == str(base or wanted[0]).strip().upper()), None)
            raise AutocadError(
                f"The base dimension {base or wanted[0]} cannot be spaced from"
                + (f": {why}" if why else "")
                + ". Give a linear or aligned dimension as the base. Nothing was moved."
            )
        try:
            plan = plan_spacing(found, float(spacing), base.strip() if base else wanted[0])
        except ValueError as exc:
            raise AutocadError(f"{exc}. Nothing was moved.") from exc
        skipped = unread + plan["skipped"]
        result: dict[str, Any] = {
            "base": plan["base"],
            "spacing": float(spacing),
            "moves": plan["moves"],
            "already": plan["already"],
            "skipped": skipped,
        }
        if dry_run:
            result.update(dry_run=True, moved=0, hint="Nothing was moved. Call again with dry_run=false.")
            return result
        if not plan["moves"]:
            result.update(moved=0, **before_after([]))
            result["note"] = "Every dimension was already at its place; nothing was written."
            return result
        moves = [{"handle": m["handle"], "to": m["to"]} for m in plan["moves"]]
        with undo_mark(doc):
            done = in_plugin("move_dimension_lines", {"moves": moves}, "Moving dimension lines")
        rows = [{"handle": m["handle"], "property": "dimension line", "from": m["from"], "to": m["to"]} for m in plan["moves"]]
        result.update(moved=int(done.get("moved", len(moves))), **before_after(rows))
        return result

    return dumps(await run(work))


def _space_of(doc: Any) -> tuple[Any, str]:
    """Where a typed command picks objects: model space on the Model tab or in an active viewport."""
    in_model = int(_try(lambda: doc.ActiveSpace, 1)) == 1 or bool(_try(lambda: doc.MSpace, False))
    return (doc.ModelSpace, "model") if in_model else (doc.PaperSpace, "paper")


def _wait_done(doc: Any) -> bool:
    """True once AutoCAD is back at its prompt; False if a command is still asking."""
    deadline = time.monotonic() + COMMAND_WAIT_S
    while True:
        if not bool(_try(lambda: int(doc.GetVariable("CMDACTIVE")), 0)):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(COMMAND_POLL_S)


@mcp.tool(name="autocad_break_dimensions", **tool_meta("Break Dimensions At Crossings"))
@tool_errors
async def autocad_break_dimensions(
    handles: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=MAX_DIMENSIONS,
            description="The dimensions to break, by handle. Each is broken wherever another object crosses its dimension or extension lines.",
        ),
    ],
    remove: Annotated[
        bool,
        Field(default=False, description="Take the breaks off these dimensions instead of adding them."),
    ] = False,
) -> str:
    """Break dimensions where other objects cross them: AutoCAD's DIMBREAK, automatic.

    Each dimension gets a gap in its dimension and extension lines wherever
    another object crosses it, the size the dimension style says (DIMBREAK).
    remove=true takes the breaks off again. The breaks follow the objects: move
    a duct and the gap moves with it.

    Neither COM nor the plug-in has a call for a dimension break, so this types
    DIMBREAK (Multiple, then Break or Remove) with each dimension picked by its
    handle. The dimensions must be in the space you are working in. One undo
    step. Look at it with autocad_preview afterwards.

    Args:
        handles (list[str]): the dimensions.
        remove (bool): remove breaks instead of adding them.

    Returns:
        str: JSON: {"broken": [str] | "unbroken": [str], "space": str,
             "command": str}

    Examples:
        - Use when: "break the dimensions where the pipes cross them".
        - Use when: "take the dimension breaks off" — remove=true.
        - Don't use when: you want the dimension text clear of hatch — use a
          background mask, or autocad_add_wipeout behind it.

    Error Handling:
        - Anything that is not a dimension, a dimension in another space, or
          one on a locked or frozen layer is refused before anything is typed.
        - If AutoCAD is still asking when DIMBREAK should be done, it is
          cancelled and the tool says so.
    """
    wanted = _check_handles(handles)
    try:
        typed = dimbreak_command(wanted, remove)
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        target, space = _space_of(doc)
        here = _try(lambda: target.ObjectID)
        for handle, entity in zip(wanted, resolve_handles(doc, wanted), strict=True):
            kind = short_type(entity)
            if kind != "dimension":
                raise AutocadError(f"{handle} is a {kind}, not a dimension. Nothing was typed.")
            owner = _try(lambda e=entity: e.OwnerID)
            if owner is not None and here is not None and owner != here:
                raise AutocadError(
                    f"The dimension {handle} is not in {space} space, where DIMBREAK picks from now. "
                    "Switch to its space first. Nothing was typed."
                )
            # DIMBREAK drops a dimension it cannot pick; with none left it ends early and the
            # typed Break / Remove would land at the Command prompt as a command of its own.
            name = str(_try(lambda e=entity: e.Layer, ""))
            layer = _try(lambda n=name: doc.Layers.Item(n))
            locked = bool(_try(lambda la=layer: la.Lock, False)) if layer is not None else False
            frozen = bool(_try(lambda la=layer: la.Freeze, False)) if layer is not None else False
            if locked or frozen:
                state = "locked" if locked else "frozen"
                raise AutocadError(
                    f"The dimension {handle} is on the {state} layer {name}, and DIMBREAK cannot pick it. "
                    f"{'Unlock' if state == 'locked' else 'Thaw'} the layer first with autocad_set_layer_state. "
                    "Nothing was typed."
                )
        with undo_mark(doc):
            doc.SendCommand(typed)
            if not _wait_done(doc):
                _try(lambda: doc.SendCommand("\x1b\x1b"), busy_ok=True)
                raise AutocadError(
                    "AutoCAD did not finish DIMBREAK and was left asking; it has been cancelled. "
                    "Check that no other command was running, then look at the dimensions with "
                    "autocad_preview before trying again."
                )
        return {
            ("unbroken" if remove else "broken"): wanted,
            "space": space,
            "command": typed.strip().replace("\n", " | "),
            "next_step": "Look at the dimensions with autocad_preview: the breaks are drawn by AutoCAD and are not read back.",
        }

    return dumps(await run(work))
