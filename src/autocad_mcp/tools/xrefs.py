"""External references: attach one, and reload, unload, detach or bind it;
attach an image or a PDF / DWF / DGN underlay, and clip any of them (#104).

Listing them is autocad_list_blocks, which already marks each xref and gives its
path. Detaching and binding follow D-03: they change what the drawing holds for
good, so the first call only says what would happen and confirm=true does it.
"""

from __future__ import annotations

import os
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import clip as clip_outline
from ..acad.curves import read_path
from ..acad.entities import resolve_handle
from ..acad.tables import apply_properties, validate_name
from ..acad.units import rad
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import double_array
from ._shared import (
    COORDS_OPT,
    LAYER_OPT,
    SPACE_OPT,
    created_payload,
    in_plugin,
    plugin_created,
    point,
    ucs_for,
    world_angle,
    world_coords,
)
from .draw import dwg_path


def _try(getter, default=None):
    try:
        return getter()
    except BaseException as exc:  # noqa: BLE001 - absent properties are expected here
        raise_if_busy(exc)
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
                raise_if_busy(exc)
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
                raise_if_busy(exc)
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


# ---- images and underlays (#104) -----------------------------------------------------

RASTER_TYPES = {".bmp", ".dib", ".rle", ".gif", ".jpg", ".jpeg", ".jfif", ".png", ".tif", ".tiff", ".tga", ".pcx", ".jp2", ".j2k"}
UNDERLAY_TYPES = {".pdf": "pdf", ".dwf": "dwf", ".dwfx": "dwf", ".dgn": "dgn"}
UNDERLAY_OBJECTS = {"AcDbPdfReference": "pdf", "AcDbDwfReference": "dwf", "AcDbDgnReference": "dgn"}


def reference_file(raw: str) -> tuple[str, str]:
    """(whole path, kind) for an image or underlay file; refused when it is not there or not a kind AutoCAD attaches."""
    resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(raw.strip().strip('"'))))
    ext = os.path.splitext(resolved)[1].lower()
    if ext in RASTER_TYPES:
        kind = "image"
    elif ext in UNDERLAY_TYPES:
        kind = UNDERLAY_TYPES[ext]
    elif ext == ".dwg":
        raise AutocadError("A .dwg is attached as an xref: use autocad_attach_xref.")
    else:
        raise AutocadError(
            f"'{os.path.basename(resolved)}' is not a file AutoCAD attaches as an image or underlay. "
            "Give a PDF, DWF, DWFx or DGN, or an image (PNG, JPG, TIF, BMP, GIF...)."
        )
    if not os.path.isfile(resolved):
        raise AutocadError(f"No file exists at '{resolved}'.")
    return resolved, kind


@mcp.tool(name="autocad_attach_underlay", **tool_meta("Attach An Image Or A PDF / DWF / DGN Underlay"))
@tool_errors
async def autocad_attach_underlay(
    path: Annotated[str, Field(min_length=1, description="The file: a PDF, DWF, DWFx or DGN, or a raster image (PNG, JPG, TIF, BMP, GIF...).")],
    insertion: Annotated[list[float], Field(default=[0.0, 0.0, 0.0], description="Where its lower-left corner goes, [x, y] or [x, y, z].")] = [0.0, 0.0, 0.0],  # noqa: B006 - pydantic copies it
    scale: Annotated[float, Field(default=1.0, gt=0, description="Scale. A PDF at 1 is its true printed size in drawing units; an image at 1 is the size its own resolution gives (1 unit wide if it has none) - give width instead.")] = 1.0,
    width: Annotated[float | None, Field(default=None, gt=0, description="Images only: the width it should have in drawing units, e.g. 42000 for a site photo 42 m wide. Overrides scale.")] = None,
    rotation: Annotated[float, Field(default=0.0, description="Rotation in DEGREES counter-clockwise.")] = 0.0,
    page: Annotated[str | None, Field(default=None, description="Underlays only: the PDF page number ('1', '2'...), the DWF sheet name or the DGN model name. Omit for the first page / sheet / 'Default' model.")] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    space: Annotated[str, SPACE_OPT] = "model",
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Attach a raster image or a PDF / DWF / DGN underlay (IMAGEATTACH, PDFATTACH, DWFATTACH, DGNATTACH).

    The consultant's background as a PDF, a scanned survey, a site photo: it
    shows in the drawing and is not copied in. Placed at a point, scale and
    rotation, on the layer asked for. Clip it afterwards with
    autocad_clip_reference.

    An image is attached over COM; an underlay by the Heron plug-in, which
    COM has no call for.

    One undo step.

    Args:
        path (str): the file.
        insertion (list[float]): lower-left corner.
        scale (float): scale.
        width (Optional[float]): images only, width in drawing units.
        rotation (float): degrees counter-clockwise.
        page (Optional[str]): PDF page, DWF sheet or DGN model.
        layer (Optional[str]): layer, created if missing.
        space (str): 'model' or 'paper'.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "kind": str, "path": str,
             "layer": str, ...}

    Examples:
        - Use when: "attach the architect's PDF as a background at 0,0" —
          path to the .pdf.
        - Use when: "bring in page 3 of the consultant's PDF" — page='3'.
        - Use when: "put the site photo in, 42 m wide" — width=42000.
        - Use when: "attach the DGN from the civil engineer".
        - Don't use when: the file is a .dwg - autocad_attach_xref.
        - Don't use when: you want the PDF's lines as real objects - type
          PDFIMPORT in AutoCAD.

    Error Handling:
        - A file that is not there, or not an image or underlay type, is
          refused before AutoCAD is asked.
        - A PDF page or DWF sheet that is not in the file is refused by the
          plug-in, and nothing is changed.
    """
    resolved, kind = reference_file(path)
    if width is not None and kind != "image":
        raise AutocadError("width is for images; give an underlay its scale.")
    if page is not None and kind == "image":
        raise AutocadError("page is for a PDF, DWF or DGN underlay, not an image.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        if kind == "image":
            with undo_mark(doc):
                try:
                    image = get_space(doc, space).AddRaster(
                        resolved, point(insertion, "insertion", ucs), float(scale), rad(world_angle(rotation, ucs))
                    )
                except BaseException as exc:  # noqa: BLE001
                    raise_if_busy(exc)
                    raise AutocadError(f"AutoCAD would not attach '{resolved}' ({com_message(exc)}).") from exc
                if width is not None:
                    drawn = float(_try(lambda: image.ImageWidth, 0.0) or 0.0)
                    if drawn > 0:
                        image.ScaleFactor = float(_try(lambda: image.ScaleFactor, scale)) * float(width) / drawn
                notes = apply_properties(doc, image, layer, None, None)
            payload = created_payload(image, notes, kind="image", path=resolved)
            payload["width"] = _try(lambda: round(float(image.ImageWidth), 6))
            payload["height"] = _try(lambda: round(float(image.ImageHeight), 6))
            return payload
        args = {
            "path": resolved,
            "kind": kind,
            "page": page,
            "insertion": world_coords(insertion, ucs),
            "scale": float(scale),
            "rotation": rad(world_angle(rotation, ucs) or 0.0),
            "layer": layer,
            "space": "paper" if space == "paper" else "model",
        }
        return plugin_created(doc, in_plugin("attach_underlay", args, "Attaching a PDF, DWF or DGN underlay"))

    return dumps(await run(work))


def _clip_target(doc: Any, entity: Any) -> str:
    """'image', 'xref', 'block' or the underlay kind; refused for anything that cannot be clipped."""
    name = str(_try(lambda: entity.ObjectName, ""))
    if name == "AcDbRasterImage":
        return "image"
    if name in UNDERLAY_OBJECTS:
        return UNDERLAY_OBJECTS[name]
    if name == "AcDbBlockReference":
        block = _block_named(doc, str(_try(lambda: entity.Name, "")))
        return "xref" if block is not None and bool(_try(lambda: block.IsXRef, False)) else "block"
    raise AutocadError(
        f"{entity.Handle} is {name or 'an unknown object'}; only an xref, a block, a raster image or a "
        "PDF / DWF / DGN underlay can be clipped."
    )


@mcp.tool(name="autocad_clip_reference", **tool_meta("Clip An Xref, Image Or Underlay"))
@tool_errors
async def autocad_clip_reference(
    handle: Annotated[str, Field(min_length=1, description="The xref, block, raster image or PDF / DWF / DGN underlay to clip.")],
    corners: Annotated[list[list[float]] | None, Field(default=None, description="Clip to the rectangle between two opposite corners, [[x1, y1], [x2, y2]].")] = None,
    boundary: Annotated[str | None, Field(default=None, description="Clip to this closed polyline (or circle), by handle. Arcs are followed in short straight steps.")] = None,
    remove: Annotated[bool, Field(default=False, description="true: take the clip off, so the whole reference shows again.")] = False,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Clip an xref, a raster image or a PDF / DWF / DGN underlay to a rectangle or a closed polyline (XCLIP, IMAGECLIP, PDFCLIP).

    Show only the part of the architect's plan, the survey or the PDF that
    the sheet needs. Only what is inside the outline shows; nothing is
    erased, and remove=true brings the whole reference back.

    An image is clipped over COM; an xref, a block or an underlay by the
    Heron plug-in, which COM has no call for. A new clip replaces the old one.

    One undo step.

    Args:
        handle (str): the reference to clip.
        corners (Optional[list[list[float]]]): two opposite corners.
        boundary (Optional[str]): a closed polyline or circle, by handle.
        remove (bool): take the clip off.
        coords (str): 'world' or 'ucs' for the corners.

    Returns:
        str: JSON: {"handle": str, "kind": str, "clipped": bool,
             "points": int}

    Examples:
        - Use when: "clip the architect's xref to the plant room area" —
          corners or a boundary polyline.
        - Use when: "crop the PDF background to the north wing" — handle of
          the underlay, boundary polyline.
        - Use when: "unclip the survey image" — remove=true.
        - Don't use when: you want objects cut and erased at a line - that
          is TRIM, not a clip.
        - Don't use when: the reference is not attached yet -
          autocad_attach_xref or autocad_attach_underlay first.

    Error Handling:
        - An object that is not an xref, block, image or underlay is refused.
        - An outline that is open, crosses itself or encloses no area is
          refused before anything changes.
        - Both or neither of corners and boundary (without remove) is refused.
    """
    if not remove and (corners is None) == (boundary is None):
        raise AutocadError("Give either corners (two opposite corners) or boundary (a closed polyline's handle), not both.")
    if remove and (corners is not None or boundary is not None):
        raise AutocadError("remove=true takes the clip off: give no corners or boundary with it.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        entity = resolve_handle(doc, handle)
        kind = _clip_target(doc, entity)
        points: list[tuple[float, float]] = []
        if not remove:
            if corners is not None:
                if len(corners) != 2:
                    raise AutocadError("corners must be two opposite corners, [[x1, y1], [x2, y2]].")
                ucs = ucs_for(doc, coords)
                # The rectangle is square to the axes it is given in; each corner then goes to the world.
                box = clip_outline.rectangle(corners[0], corners[1])
                points = clip_outline.check([world_coords(c, ucs)[:2] for c in box])
            else:
                outline = resolve_handle(doc, str(boundary))
                normal = _try(lambda: outline.Normal)
                if normal is not None and not (abs(float(normal[0])) <= 1e-9 and abs(float(normal[1])) <= 1e-9 and float(normal[2]) > 0):
                    raise AutocadError(
                        f"The outline {outline.Handle} is not drawn flat in plan facing up, so its corners are "
                        "not world points. Draw the outline in the World UCS, or give two corners."
                    )
                path = read_path(outline)
                points = clip_outline.check(clip_outline.from_polyline(path["vertices"], path["bulges"], path["closed"]))
        result: dict[str, Any] = {"handle": str(entity.Handle), "kind": kind, "clipped": not remove, "points": len(points)}
        if kind == "image":
            with undo_mark(doc):
                try:
                    if remove:
                        entity.ClippingEnabled = False
                    else:
                        entity.ClipBoundary(double_array(clip_outline.closed_ring(points)))
                        entity.ClippingEnabled = True
                except BaseException as exc:  # noqa: BLE001
                    raise_if_busy(exc)
                    raise AutocadError(f"AutoCAD would not clip the image ({com_message(exc)}).") from exc
            return result
        args = {"handle": str(entity.Handle), "points": [[x, y] for x, y in points], "remove": bool(remove)}
        report = in_plugin("clip_reference", args, "Clipping an xref, block or underlay")
        result.update({k: v for k, v in report.items() if k not in result})
        return result

    return dumps(await run(work))
