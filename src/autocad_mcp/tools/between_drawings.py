"""Copy objects from another open drawing into this one (Copy with Base Point, Paste) (D-83).

``autocad_import_from_drawing`` brings definitions (blocks, layers, styles)
from a closed file; this brings drawn objects from a drawing that is open in
AutoCAD, at a base point, the way Ctrl+Shift+C and Ctrl+V do. The copies land
in the drawing Heron checked (the active one), so the gate's guard, its UNDO
mark and Keep or Discard all apply to where the change is; the drawing they
come from is only read, and neither drawing is switched.

What comes along (the layers, styles and blocks the target lacks) and what is
the target's own is worked out first by ``acad/drawing_copy.py``, tested
without AutoCAD.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Annotated, Any

from pydantic import Field

from ..acad.drawing_copy import empty_uses, find_open, offset, what_comes_along
from ..core.connection import get_app, get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, object_array

TEXT_TYPES = {"AcDbText", "AcDbMText", "AcDbAttributeDefinition"}
INSERT_TYPES = {"AcDbBlockReference", "AcDbMInsertBlock"}
_COLLECTIONS = {"layers": "Layers", "linetypes": "Linetypes", "text_styles": "TextStyles", "dim_styles": "DimStyles", "blocks": "Blocks"}
MOST_HANDLES = 5000
# Objects read inside block definitions to find what they need; a library block is rarely near this.
MOST_SCANNED = 20000


def _read(obj: Any, name: str) -> str:
    try:
        return str(getattr(obj, name) or "")
    except Exception:  # noqa: BLE001 - an object without that property
        return ""


def _note_uses(obj: Any, uses: dict[str, set[str]]) -> str | None:
    """Add what one object needs to ``uses``; the block it inserts, if it is an insert."""
    kind = _read(obj, "ObjectName")
    uses["layers"].add(_read(obj, "Layer"))
    uses["linetypes"].add(_read(obj, "Linetype"))
    if kind in TEXT_TYPES:
        uses["text_styles"].add(_read(obj, "StyleName"))
    elif "Dimension" in kind:
        uses["dim_styles"].add(_read(obj, "StyleName"))
    elif kind in INSERT_TYPES:
        block = _read(obj, "EffectiveName") or _read(obj, "Name")
        uses["blocks"].add(block)
        return block
    return None


def _definitions(source: Any, top: set[str]) -> tuple[dict[str, dict[str, set[str]]], bool]:
    """What each block definition the copy needs uses, following blocks inside blocks; (map, cut short)."""
    inside: dict[str, dict[str, set[str]]] = {}
    todo = [name for name in top if name]
    scanned = 0
    while todo:
        name = todo.pop()
        if name in inside or name.startswith("*"):
            continue
        uses = empty_uses()
        inside[name] = uses
        try:
            block = source.Blocks.Item(name)
            count = int(block.Count)
        except Exception:  # noqa: BLE001 - CopyObjects still brings it; only the list is shorter
            continue
        for i in range(count):
            scanned += 1
            if scanned > MOST_SCANNED:
                return inside, True
            nested = _note_uses(block.Item(i), uses)
            if nested and nested not in inside:
                todo.append(nested)
    return inside, False


def _names(doc: Any) -> dict[str, list[str]]:
    names: dict[str, list[str]] = {}
    for kind, attr in _COLLECTIONS.items():
        collection = getattr(doc, attr)
        names[kind] = [str(collection.Item(i).Name) for i in range(int(collection.Count))]
    return names


def _copied(result: Any) -> list[Any]:
    """The new objects CopyObjects hands back, with or without the ID pairs alongside."""
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], (tuple, list)):
        result = result[0]
    if result is None:
        return []
    if isinstance(result, (tuple, list)):
        return list(result)
    return [result]


@mcp.tool(name="autocad_copy_from_drawing", **tool_meta("Copy From Another Open Drawing"))
@tool_errors
async def autocad_copy_from_drawing(
    source: Annotated[
        str,
        Field(min_length=1, description="The open drawing to copy from, e.g. 'pump-room.dwg' (or its full path when two open files share a name). autocad_list_drawings names them."),
    ],
    handles: Annotated[
        list[str],
        Field(min_length=1, description="Handles of the objects to copy, in the source drawing. Find them there with autocad_list_entities or autocad_get_selection while it is active."),
    ],
    base_point: Annotated[
        list[float],
        Field(description="The base point in the source drawing, [x, y] (world coordinates there), as Copy with Base Point picks it."),
    ],
    to_point: Annotated[
        list[float] | None,
        Field(default=None, description="Where the base point lands in this drawing, [x, y] (world). Omit to keep the same coordinates."),
    ] = None,
    space: Annotated[
        str,
        Field(default="model", description="'model' for model space, or 'paper' for the current layout of this drawing.", pattern="^(model|paper)$"),
    ] = "model",
    dry_run: Annotated[
        bool,
        Field(default=False, description="True: say what would be copied and which layers, styles and blocks would come with it; copy nothing."),
    ] = False,
) -> str:
    """Copy objects from another open drawing into this one, at a base point (Copy with Base Point, then Paste).

    The copies land in the active drawing, the one Heron checked with
    autocad_status; the source drawing is only read and stays open as it was,
    and neither drawing is switched. Layers, linetypes, text and dimension
    styles and blocks the copies need that this drawing lacks come with them;
    a name this drawing already has is used as it is here, so a block called
    VALVE in both shows this drawing's VALVE (listed in "already_here"). One
    undo step.

    Returns:
        JSON: {"copied": int, "handles": [new handles], "from", "into", "moved_by": [dx, dy, dz],
        "brought_in": {layers, blocks, ...}, "already_here": {...}}

    Examples:
        - Use when: "copy the pump skid from pump-room.dwg into this plan at
          5000,2000" -> source, handles from that drawing, base_point,
          to_point=[5000, 2000].
        - Use when: "bring the AHU and its ducts over from the old layout
          drawing" (switch to it, autocad_get_selection, switch back,
          autocad_status, then this).
        - Don't use when: only blocks, layers or styles are wanted from a file
          that is not open - autocad_import_from_drawing.
        - Don't use when: copying inside the same drawing - autocad_copy_entities.

    Error Handling:
        - A source that is not open, is this drawing, or a handle that is not in
          it is refused before anything is copied.
    """
    if len(base_point) < 2:
        raise AutocadError("base_point must be [x, y].")
    if to_point is not None and len(to_point) < 2:
        raise AutocadError("to_point must be [x, y].")
    wanted = list(dict.fromkeys(str(h).strip().upper() for h in handles if str(h).strip()))
    if len(wanted) > MOST_HANDLES:
        raise AutocadError(f"{len(wanted)} handles is more than {MOST_HANDLES} in one copy. Split it.")

    def work() -> dict[str, Any]:
        app = get_app()
        target = get_doc()
        require_idle(target)
        open_docs = [app.Documents.Item(i) for i in range(int(app.Documents.Count))]
        try:
            index = find_open([(str(d.Name), str(d.FullName)) for d in open_docs], source)
        except ValueError as exc:
            raise AutocadError(f"{exc} Nothing was copied.") from None
        from_doc = open_docs[index]
        if str(from_doc.FullName) == str(target.FullName) and str(from_doc.Name) == str(target.Name):
            raise AutocadError(
                f"{from_doc.Name} is the active drawing. To copy inside one drawing use autocad_copy_entities; "
                "to copy into another, make that one active (autocad_switch_drawing, then autocad_status)."
            )
        objects, missing = [], []
        for handle in wanted:
            try:
                objects.append(from_doc.HandleToObject(handle))
            except Exception:  # noqa: BLE001 - listed below
                missing.append(handle)
        if missing:
            raise AutocadError(
                f"{from_doc.Name} has nothing with the handle(s) {', '.join(missing[:20])}. Handles belong to one "
                "drawing: read them there (autocad_list_entities while it is active). Nothing was copied."
            )
        uses = empty_uses()
        top_blocks: set[str] = set()
        groups: dict[Any, list[Any]] = defaultdict(list)
        for obj in objects:
            block = _note_uses(obj, uses)
            if block:
                top_blocks.add(block)
            try:
                owner = obj.OwnerID
            except Exception:  # noqa: BLE001 - one group then
                owner = None
            groups[owner].append(obj)
        inside, cut_short = _definitions(from_doc, top_blocks)
        along = what_comes_along(uses, inside, _names(target))
        move = offset(base_point, to_point)
        result: dict[str, Any] = {
            "from": str(from_doc.Name),
            "into": str(target.Name),
            "objects": len(objects),
            "moved_by": move,
            **along,
        }
        if along["already_here"]:
            result["already_here_note"] = (
                "These names are already in this drawing, so the copies use this drawing's own: a block of the "
                "same name shows this drawing's version, a layer keeps this drawing's colour."
            )
        if cut_short:
            result["list_cut_short"] = f"More than {MOST_SCANNED} objects inside the blocks: the lists above may miss some; the copy brings them all the same."
        if dry_run:
            return {**result, "dry_run": True, "would_copy": len(objects)}
        owner_space = get_space(target, space)
        new: list[Any] = []
        with undo_mark(target):
            for group in groups.values():
                try:
                    made = source_copy(from_doc, group, owner_space)
                except Exception as exc:  # noqa: BLE001
                    raise AutocadError(f"AutoCAD would not copy them ({com_message(exc)}).") from exc
                new.extend(made)
            if any(abs(v) > 1e-12 for v in move):
                base = [float(v) for v in (list(base_point) + [0.0, 0.0])[:3]]
                start, end = apoint(*base), apoint(*[base[i] + move[i] for i in range(3)])
                for obj in new:
                    obj.Move(start, end)
        handles_new = [str(obj.Handle) for obj in new]
        return {**result, "dry_run": False, "copied": len(new), "handles": handles_new}

    return dumps(await run(work))


def source_copy(from_doc: Any, objects: list[Any], owner: Any) -> list[Any]:
    """One CopyObjects call: objects that share an owner, into ``owner`` (another drawing's space)."""
    return _copied(from_doc.CopyObjects(object_array(objects), owner))

