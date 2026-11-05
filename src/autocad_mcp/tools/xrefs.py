"""External references: attach one, and reload, unload, detach or bind it.

Listing them is autocad_list_blocks, which already marks each xref and gives its
path. Detaching and binding follow D-03: they change what the drawing holds for
good, so the first call only says what would happen and confirm=true does it.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.tables import apply_properties, validate_name
from ..acad.units import rad
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import (
    COORDS_OPT,
    LAYER_OPT,
    SPACE_OPT,
    created_payload,
    point,
    ucs_for,
    world_angle,
)
from .draw import dwg_path


def _try(getter, default=None):
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def _block_named(doc: Any, name: str) -> Any:
    wanted = name.strip().lower()
    blocks = doc.Blocks
    for i in range(int(blocks.Count)):
        block = blocks.Item(i)
        if str(_try(lambda b=block: b.Name, "")).strip().lower() == wanted:
            return block
    return None


@mcp.tool(name="autocad_attach_xref", **tool_meta("Attach An Xref"))
@tool_errors
async def autocad_attach_xref(
    path: Annotated[str, Field(min_length=1, description="The .dwg to reference, e.g. 'D:\\\\Project\\\\Arch\\\\A-101.dwg'. Forward slashes are fine.")],
    name: Annotated[str | None, Field(default=None, description="The xref's name in this drawing. Omit to use the file name.")] = None,
    insertion: Annotated[list[float], Field(default=[0.0, 0.0, 0.0], description="Where its origin goes, [x, y] or [x, y, z]. [0, 0] lines up drawings that share a project origin.")] = [0.0, 0.0, 0.0],  # noqa: B006 - pydantic copies it
    scale: Annotated[float, Field(default=1.0, gt=0, description="Uniform scale. 1 for drawings in the same units.")] = 1.0,
    rotation: Annotated[float, Field(default=0.0, description="Rotation in DEGREES counter-clockwise.")] = 0.0,
    overlay: Annotated[bool, Field(default=False, description="Overlay instead of attach: it is not carried into a drawing that references this one. Usual for a background you only trace over.")] = False,
    layer: Annotated[str | None, LAYER_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Reference another drawing into this one as an xref (XATTACH).

    The architect's plan under the services, a survey under the site plan: the
    other drawing shows here and updates when it changes, without being copied
    in.

    One undo step.

    Args:
        path (str): the .dwg file to reference.
        name (Optional[str]): its name here; defaults to the file name.
        insertion (list[float]): where its origin goes.
        scale (float): uniform scale.
        rotation (float): degrees counter-clockwise.
        overlay (bool): overlay rather than attach.
        layer (Optional[str]): layer for the reference, created if missing.
        space (str): 'model' or 'paper'.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "name": str,
             "path": str, "overlay": bool, "layer": str}

    Examples:
        - Use when: "xref the architect's plan in at 0,0" — path, insertion
          [0, 0].
        - Use when: "overlay the survey as a background" — overlay=true.
        - Don't use when: you want the other drawing's objects copied in for
          good - that is autocad_insert_block with the .dwg (or bind the xref
          afterwards with autocad_manage_xref).

    Error Handling:
        - A file that is not there is named before AutoCAD is asked.
        - A name already used by a block or xref in this drawing is refused,
          pointing at autocad_manage_xref to reload the one that is there.
    """
    resolved = dwg_path(path)
    ref_name = validate_name(name if name else os.path.splitext(os.path.basename(resolved))[0], "xref")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if _block_named(doc, ref_name) is not None:
            raise AutocadError(
                f"This drawing already has a block or xref called '{ref_name}'. To bring an xref up "
                "to date use autocad_manage_xref(action='reload'); to attach another copy, give "
                "it a different name."
            )
        ucs = ucs_for(doc, coords)
        with undo_mark(doc):
            try:
                ref = get_space(doc, space).AttachExternalReference(
                    resolved, ref_name, point(insertion, "insertion", ucs),
                    float(scale), float(scale), float(scale), rad(world_angle(rotation, ucs)), bool(overlay),
                )
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(
                    f"AutoCAD would not reference '{resolved}' ({com_message(exc)}). Check the file "
                    "opens in AutoCAD and is not this drawing itself."
                ) from exc
            notes = apply_properties(doc, ref, layer, None, None)
        return created_payload(ref, notes, name=ref_name, path=resolved, overlay=bool(overlay))

    return dumps(await run(work))


# What each action calls on the xref's block. Bind's argument is bPrefixName:
# True keeps the xref's layers and styles apart as NAME$0$LAYER ("Bind"),
# False merges them into the drawing's own ("Insert").
XREF_ACTIONS = {
    "reload": ("Reload", ()),
    "unload": ("Unload", ()),
    "detach": ("Detach", ()),
    "bind": ("Bind", (True,)),
    "insert": ("Bind", (False,)),
}
NEEDS_CONFIRM = {"detach", "bind", "insert"}


@mcp.tool(name="autocad_manage_xref", **tool_meta("Reload, Unload, Detach Or Bind An Xref"))
@tool_errors
async def autocad_manage_xref(
    name: Annotated[str, Field(min_length=1, description="The xref's name, as autocad_list_blocks shows it.")],
    action: Annotated[
        Literal["reload", "unload", "detach", "bind", "insert"],
        Field(description="'reload' brings it up to date; 'unload' hides it but keeps it; 'detach' removes it and every instance; 'bind' makes it part of this drawing with its names kept apart (NAME$0$...); 'insert' binds it with its names merged."),
    ],
    confirm: Annotated[bool, Field(default=False, description="detach, bind and insert change the drawing for good: false (the default) only says what would happen.")] = False,
) -> str:
    """Reload, unload, detach or bind an xref - the External References palette's actions.

    Reload after the other consultant issues a new revision; unload to hide
    one without losing it; detach to remove it; bind (or insert) to make it a
    permanent part of this drawing before issuing it.

    One undo step.

    Args:
        name (str): the xref's name.
        action (str): reload, unload, detach, bind or insert.
        confirm (bool): needed for detach, bind and insert.

    Returns:
        str: JSON: {"name": str, "action": str, "confirmed": bool,
             "path": str, "note": str}

    Examples:
        - Use when: "the architect issued a new plan, update the xref" —
          action='reload'.
        - Use when: "bind the xrefs before we send the drawing out" —
          action='bind', confirm=true.
        - Use when: "remove the old survey xref" — action='detach',
          confirm=true.
        - Don't use when: you want to see which xrefs there are -
          autocad_list_blocks lists them with their paths.
        - Don't use when: the drawing is not referenced in yet - attach it
          with autocad_attach_xref.

    Error Handling:
        - A name that is not in the drawing, or a block that is not an xref,
          is refused before anything changes.
        - Without confirm, detach, bind and insert change nothing and say so.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        block = _block_named(doc, name)
        if block is None:
            raise AutocadError(f"There is no xref called '{name}' in this drawing. autocad_list_blocks lists them.")
        if not bool(_try(lambda: block.IsXRef, False)):
            raise AutocadError(f"'{name}' is a block, not an xref, so it cannot be {action}ed.")
        result: dict[str, Any] = {
            "name": str(_try(lambda: block.Name, name)),
            "action": action,
            "path": str(_try(lambda: block.Path, "")),
        }
        if action in NEEDS_CONFIRM and not confirm:
            result["confirmed"] = False
            result["note"] = (
                f"Nothing changed. {action} changes the drawing for good (one Ctrl+Z still undoes "
                "it straight away); call again with confirm=true to do it."
            )
            return result
        method, args = XREF_ACTIONS[action]
        with undo_mark(doc):
            try:
                getattr(block, method)(*args)
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(f"AutoCAD would not {action} '{name}' ({com_message(exc)}).") from exc
        result["confirmed"] = True
        result["note"] = f"'{result['name']}' {action} done."
        return result

    return dumps(await run(work))


# Nested xrefs deeper than this are not followed: a real project is three or
# four levels at most, and a loop of references must not run forever.
XREF_DEPTH = 8


def _found_file(saved: str, drawing_folder: str) -> str:
    """Where the saved path points on this PC, or '' when nothing is there.

    AutoCAD looks for a full path first, then a relative one ('..\\Arch\\A.dwg')
    from the host drawing's folder, then the bare file name in that folder.
    Its support-path search is not repeated here: an xref found only there
    reads 'loaded' from AutoCAD itself, which wins.
    """
    saved = (saved or "").strip().replace("\\", os.sep).replace("/", os.sep)
    if not saved:
        return ""
    tries = [saved] if os.path.isabs(saved) else []
    if drawing_folder:
        if not os.path.isabs(saved):
            tries.append(os.path.join(drawing_folder, saved))
        tries.append(os.path.join(drawing_folder, os.path.basename(saved)))
    for path in tries:
        if os.path.isfile(path):
            return os.path.normpath(path)
    return ""


def _xref_nodes(blocks: Any, drawing_folder: str, depth: int, seen: set[str]) -> list[dict[str, Any]]:
    """The xrefs in one drawing's block table, each with the xrefs inside it."""
    nodes = []
    for i in range(int(_try(lambda: blocks.Count, 0))):
        block = _try(lambda i=i: blocks.Item(i))
        if block is None or not bool(_try(lambda b=block: b.IsXRef, False)):
            continue
        name = str(_try(lambda b=block: b.Name, ""))
        saved = str(_try(lambda b=block: b.Path, ""))
        found = _found_file(saved, drawing_folder)
        inner = _try(lambda b=block: b.XRefDatabase)
        node: dict[str, Any] = {"name": name, "saved_path": saved, "found_path": found}
        if inner is not None:
            node["status"] = "loaded"
        elif found:
            node["status"] = "unloaded"
        else:
            node["status"] = "not found"
        children: list[dict[str, Any]] = []
        key = (found or saved).lower()
        if inner is not None and key in seen:
            node["note"] = "Refers back to a drawing already above it; not followed again."
        elif inner is not None and depth >= XREF_DEPTH:
            node["note"] = f"Deeper than {XREF_DEPTH} levels; not followed."
        elif inner is not None:
            folder = os.path.dirname(found) if found else drawing_folder
            children = _xref_nodes(_try(lambda d=inner: d.Blocks), folder, depth + 1, seen | {key})
        node["children"] = children
        nodes.append(node)
    return sorted(nodes, key=lambda n: n["name"].lower())


def _walk(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


@mcp.tool(name="autocad_xref_tree", **tool_meta("Xref Tree And Broken Paths", read_only=True, idempotent=True))
@tool_errors
async def autocad_xref_tree() -> str:
    """The whole xref tree of this drawing: each xref, the xrefs inside it, and which ones are broken.

    For each xref: its name, the path saved in the drawing, the file it points
    to on this PC (empty when there is none), and its status - 'loaded',
    'unloaded' (the file is there but not loaded) or 'not found' (the path
    leads nowhere: a broken xref). Nested xrefs are listed under the one that
    carries them, up to 8 levels.

    Changes nothing.

    Returns:
        str: JSON: {"drawing": str, "count": int, "broken": [str],
             "xrefs": [{"name": str, "saved_path": str, "found_path": str,
                        "status": str, "children": [...]}]}

    Examples:
        - Use when: "which xrefs are broken before I issue this?"
        - Use when: "show me the xref tree, nested ones too".
        - Use when: "where is the architect's xref pointing?"
        - Don't use when: you only want the names and instance counts -
          autocad_list_blocks lists every xref with its saved path.
        - Don't use when: you want to fix one - autocad_manage_xref reloads,
          unloads, detaches or binds it.

    Error Handling:
        - A drawing with no xrefs answers count 0, not an error.
        - A nested xref that refers back up the tree is marked, not followed.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        folder = str(_try(lambda: doc.Path, "") or "")
        tree = _xref_nodes(doc.Blocks, folder, 1, {str(_try(lambda: doc.FullName, "")).lower()})
        every = list(_walk(tree))
        broken = sorted({n["name"] for n in every if n["status"] == "not found"}, key=str.lower)
        result: dict[str, Any] = {
            "drawing": str(_try(lambda: doc.Name, "")),
            "count": len(every),
            "broken": broken,
            "xrefs": tree,
        }
        if broken:
            result["advice"] = (
                "Broken xrefs point at a file that is not there. Find the file, then re-path it in "
                "AutoCAD's External References palette, or detach it with autocad_manage_xref."
            )
        return result

    return dumps(await run(work))
