"""Saved views: one location, named once and used everywhere.

The point of this module is a complaint every draftsman has had. You window a
region to plot it. Then you want a viewport on exactly that region. Then you
want to drop a detail bubble on exactly that region. Each time you re-pick the
two corners, and each time they are slightly different.

A named view is AutoCAD's own answer, and it is a first-class location here:
save it once from a window, from a set of objects or from what is on screen,
and then

* plot it - ``autocad_export(area='view', view_name=...)``;
* put a viewport on it - ``autocad_add_viewport(view_name=...)``;
* go back to it - ``autocad_save_view(..., zoom_to=true)`` or AutoCAD's VIEW;
* read it back as numbers - ``autocad_list_views``, which gives the corners.

Windows given in a rotated UCS are converted first, so the saved view is the
area the modeller actually meant.
"""

from __future__ import annotations

import math
import time
from typing import Annotated, Any

from pydantic import Field

from ..acad.coords import corners_box
from ..acad.entities import bounding_box, resolve_handles
from ..acad.tables import validate_name
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint
from ._shared import COORDS_OPT, in_plugin, plugin_read, ucs_for, world_coords

# How long -VIEW gets to finish saving before a prompt still open means it did
# not take the answer.
VIEW_COMMAND_WAIT_S = 2.0
VIEW_COMMAND_POLL_S = 0.1


def _read(target: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(target, name)
    except BaseException as exc:  # noqa: BLE001 - absent properties are expected here
        raise_if_busy(exc)
        return default


def _views(doc: Any) -> dict[str, Any]:
    return {
        str(doc.Views.Item(i).Name): doc.Views.Item(i)
        for i in range(int(doc.Views.Count))
    }


def _refuse_a_layouts_view(doc: Any, existing: Any, name: str) -> None:
    """Refuse to replace a view that is not provably the Model tab's, plainly (#190, D-128).

    A sheet's saved view ("DETAIL-A") is not a model view: deleting it to
    make a model view of the same name would break whatever on the sheet uses
    it. A view is the Model tab's only when its LayoutId is the Model layout's
    own ObjectID. Three cases, and the view is deleted only in the first:
    - equal to the Model layout's id: replaced;
    - a different, real id: "is a view of a layout (a sheet)";
    - 0, missing or unreadable: AutoCAD did not say, so nothing proves it is a
      model view and it is not deleted either.
    A busy AutoCAD is not "cannot be read": it goes up as it is (D-100).
    """
    try:
        layout = doc.Layouts.Item("Model")
    except BaseException as exc:  # noqa: BLE001 - no Model layout to compare with: nothing is deleted
        raise_if_busy(exc)
        layout = None
    model = _read(layout, "ObjectID") if layout is not None else None
    model_32 = _read(layout, "ObjectID32") if layout is not None else None
    belongs = _read(existing, "LayoutId")
    try:
        ids = {int(v) for v in (model, model_32) if v is not None}
        which = int(belongs) if belongs is not None else 0
    except (TypeError, ValueError):
        ids, which = set(), 0
    if which and which in ids:
        return
    if which and ids:
        raise AutocadError(
            f"'{name}' is a view of a layout (a sheet), not of the model, so replace=true does not replace it "
            "and nothing was changed. Give the new view another name."
        )
    raise AutocadError(
        f"AutoCAD did not say which tab the view '{name}' belongs to, so replace=true did not replace it "
        "and nothing was changed. Give the new view another name."
    )


def _describe(view: Any) -> dict[str, Any]:
    """One saved view as a location: its middle, its size and its corners."""
    centre = [float(v) for v in (_read(view, "Center", (0.0, 0.0, 0.0)) or (0.0, 0.0, 0.0))][:3]
    width = float(_read(view, "Width", 0.0) or 0.0)
    height = float(_read(view, "Height", 0.0) or 0.0)
    row: dict[str, Any] = {
        "name": str(_read(view, "Name", "")),
        "centre": [round(v, 6) for v in centre],
        "width": round(width, 6),
        "height": round(height, 6),
    }
    if width > 0.0 and height > 0.0:
        row["corner1"] = [round(centre[0] - width / 2.0, 6), round(centre[1] - height / 2.0, 6)]
        row["corner2"] = [round(centre[0] + width / 2.0, 6), round(centre[1] + height / 2.0, 6)]
    direction = _read(view, "Direction")
    if direction is not None:
        flat = [round(float(v), 6) for v in direction]
        row["direction"] = flat
        row["plan"] = flat == [0.0, 0.0, 1.0]
    return row


@mcp.tool(
    name="autocad_list_views",
    **tool_meta("List Saved Views", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_list_views() -> str:
    """The drawing's saved views, each with its middle, size and two corners.

    Use this to find a location someone already named — a detail area, a
    plotted region, a zone — instead of picking corners again.

    Returns:
        str: JSON: {"count": int, "views": [{"name", "centre", "width",
             "height", "corner1", "corner2", "direction", "plan"}]}

    Examples:
        - Use when: "plot the same area as last time" — find the view, then
          autocad_export(area='view', view_name=...).
        - Don't use when: you want the sheets (autocad_list_layouts).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        rows = [_describe(view) for view in _views(doc).values()]
        return {"count": len(rows), "views": rows}

    return dumps(await run(work))


@mcp.tool(name="autocad_save_view", **tool_meta("Save A Named View"))
@tool_errors
async def autocad_save_view(
    name: Annotated[
        str,
        Field(min_length=1, description="What to call the location, e.g. 'DETAIL-A', 'ZONE-3', 'PLOT-AREA-1'."),
    ],
    corner1: Annotated[
        list[float] | None,
        Field(default=None, description="One corner of the area to save, as [x, y]."),
    ] = None,
    corner2: Annotated[
        list[float] | None,
        Field(default=None, description="The opposite corner."),
    ] = None,
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="Instead of corners: save the area these objects occupy."),
    ] = None,
    pad: Annotated[
        float,
        Field(default=0.0, ge=0, description="Breathing room added all round, in drawing units. Useful with handles so the objects are not against the edge."),
    ] = 0.0,
    replace: Annotated[
        bool,
        Field(default=False, description="Overwrite a view of this name that is already saved."),
    ] = False,
    zoom_to: Annotated[
        bool,
        Field(default=False, description="Also put that area on screen, so the modeller sees what was saved."),
    ] = False,
    coords: Annotated[str, COORDS_OPT] = "world",
    from_screen: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Save exactly what is on screen now, 3D angle and all (a camera view for a "
                "render), instead of a plan area. Give no corners or handles."
            ),
        ),
    ] = False,
) -> str:
    """Name an area of the drawing so the same location can be plotted, viewported and found again.

    Give two corners, or the objects the area should cover, and it is saved as
    an AutoCAD named view. From then on the one name means that exact
    rectangle — no re-picking, no drift.

    One undo step. Windows given with coords='ucs' are converted to world
    coordinates first, so a rotated plan saves the area that was meant.

    With from_screen=true it saves the view on screen as it is, a 3D angle
    included, the way AutoCAD's VIEW command does (it types -VIEW Save), so a
    render angle set with autocad_set_3d_view can be gone back to.

    Args:
        name (str): the location's name.
        corner1 / corner2 (Optional[list[float]]): the area.
        handles (Optional[list[str]]): objects whose extents define the area.
        pad (float): breathing room all round.
        replace (bool): overwrite a view already saved under this name.
        zoom_to (bool): put it on screen as well.
        coords (str): 'world' or 'ucs' for the corners.
        from_screen (bool): save what is on screen, 3D angle included.

    Returns:
        str: JSON: {"saved": str, "replaced": bool, "view": {"name", "centre",
             "width", "height", "corner1", "corner2"}, "from": str}

    Examples:
        - Use when: "remember this area, I'll plot it and also want a viewport
          on it" — then autocad_export(area='view') and
          autocad_add_viewport(view_name=...).
        - Use when: "save the area round the pump skid" — handles + pad.
        - Use when: "save this 3D angle of the villa as a camera view for the
          render" — from_screen=true.
        - Don't use when: you only need the numbers once
          (autocad_get_extents gives them without saving anything).

    Error Handling:
        - A name already saved is refused unless replace=true; a layout's
          (paper space) view of that name is refused even then, in plain
          words, and is never deleted (also when AutoCAD does not say which
          layout the view belongs to).
        - Objects that report no extents are named rather than silently skipped.
    """
    clean = validate_name(name, "view")
    if from_screen:
        if corner1 or corner2 or handles:
            raise AutocadError("from_screen saves what is on screen: give no corners or handles with it.")
        if " " in clean:
            raise AutocadError(
                f"'{clean}' has a space, which the typed VIEW command would take as the end of "
                "the name. Use a name without spaces, e.g. 'LIVING-3D'."
            )
    elif (corner1 or corner2) and handles:
        raise AutocadError("Give either the two corners or the handles, not both.")
    elif not handles and not (corner1 and corner2):
        raise AutocadError("Say which area to save: corner1 and corner2, or handles.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if from_screen:
            return _save_screen(doc, clean, replace)
        ucs = ucs_for(doc, coords)

        if handles:
            boxes, blind = [], []
            for handle, entity in zip(handles, resolve_handles(doc, handles), strict=False):
                found = bounding_box(entity)
                if found:
                    boxes.append(found)
                else:
                    blind.append(handle)
            if not boxes:
                raise AutocadError(
                    "None of those objects report extents, so there is no area to save: "
                    + ", ".join(blind)
                    + ". Give corner1 and corner2 instead."
                )
            box = (
                min(b["min"][0] for b in boxes),
                min(b["min"][1] for b in boxes),
                max(b["max"][0] for b in boxes),
                max(b["max"][1] for b in boxes),
            )
            source = f"{len(boxes)} object(s)"
        else:
            box = corners_box(world_coords(corner1, ucs), world_coords(corner2, ucs))
            source = "a window" + (" in the current UCS" if ucs else "")

        if pad:
            box = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
        width, height = box[2] - box[0], box[3] - box[1]
        if width <= 0.0 or height <= 0.0:
            raise AutocadError(
                f"That area is {width:g} x {height:g} — it has no size. Give two corners that "
                "are properly apart, or add some pad."
            )
        middle = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

        saved = _views(doc)
        existing = next((v for k, v in saved.items() if k.lower() == clean.lower()), None)
        if existing is not None and not replace:
            raise AutocadError(
                f"This drawing already has a view called '{clean}'. Pass replace=true to "
                "overwrite it, or pick another name."
            )

        if existing is not None:
            _refuse_a_layouts_view(doc, existing, clean)
        with undo_mark(doc):
            if existing is not None:
                try:
                    existing.Delete()
                except BaseException as exc:  # noqa: BLE001
                    raise_if_busy(exc)
                    raise AutocadError(
                        f"The view '{clean}' could not be replaced ({com_message(exc)}). "
                        "Save under another name."
                    ) from exc
            try:
                view = doc.Views.Add(clean)
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AutocadError(f"AutoCAD would not save the view '{clean}': {com_message(exc)}") from exc
            # Views.Add copies whatever is on screen, so the area asked for is
            # written over it: a plan view of exactly this rectangle.
            for prop, value in (
                ("Direction", apoint(0.0, 0.0, 1.0)),
                ("Center", apoint(middle[0], middle[1], 0.0)),
                ("Target", apoint(middle[0], middle[1], 0.0)),
                ("Width", width),
                ("Height", height),
            ):
                try:
                    setattr(view, prop, value)
                except BaseException as exc:  # noqa: BLE001 - reported by reading it back below
                    raise_if_busy(exc)
            if zoom_to:
                try:
                    doc.Application.ZoomWindow(
                        apoint(box[0], box[1], 0.0), apoint(box[2], box[3], 0.0)
                    )
                except BaseException as exc:  # noqa: BLE001 - the view is saved either way
                    raise_if_busy(exc)

        written = _describe(view)
        result: dict[str, Any] = {
            "saved": clean,
            "replaced": existing is not None,
            "from": source,
            "view": written,
        }
        if written["width"] <= 0.0 or written["height"] <= 0.0:
            result["warning"] = (
                f"The view '{clean}' was created but AutoCAD did not keep its size, so it "
                "cannot be fitted to a viewport. Save it from AutoCAD's own VIEW command, "
                "or pass the corners straight to autocad_add_viewport instead."
            )
        return result

    return dumps(await run(work))


def _command_done(doc: Any) -> bool:
    """Whether the typed command has finished, given a moment to do so."""
    def busy() -> bool:
        try:
            return bool(int(doc.GetVariable("CMDACTIVE")))
        except BaseException as exc:  # noqa: BLE001 - unreadable: assume it finished
            raise_if_busy(exc)
            return False

    deadline = time.monotonic() + VIEW_COMMAND_WAIT_S
    while busy():
        if time.monotonic() >= deadline:
            return False
        time.sleep(VIEW_COMMAND_POLL_S)
    return True


def _save_screen(doc: Any, clean: str, replace: bool) -> dict[str, Any]:
    """Save the view on screen as it is, 3D angle included, with AutoCAD's own -VIEW Save.

    COM's Views.Add makes a view, but its direction and target have to be
    written by hand and their meaning differs for a 3D view; -VIEW Save takes
    everything AutoCAD itself keeps for the view on screen.
    """
    saved = _views(doc)
    existing = next((v for k, v in saved.items() if k.lower() == clean.lower()), None)
    if existing is not None and not replace:
        raise AutocadError(
            f"This drawing already has a view called '{clean}'. Pass replace=true to "
            "overwrite it, or pick another name."
        )
    if existing is not None:
        _refuse_a_layouts_view(doc, existing, clean)
    with undo_mark(doc):
        if existing is not None:
            try:
                existing.Delete()
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AutocadError(
                    f"The view '{clean}' could not be replaced ({com_message(exc)}). "
                    "Save under another name."
                ) from exc
        try:
            doc.SendCommand(f"_.-VIEW _Save {clean}\n")
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            raise AutocadError(f"AutoCAD would not take the VIEW command: {com_message(exc)}") from exc
        if not _command_done(doc):
            try:
                doc.SendCommand("\x1b\x1b")
            except BaseException:  # noqa: BLE001 - the refusal below says what matters
                pass
            raise AutocadError(
                f"AutoCAD's VIEW command did not finish saving '{clean}' and was cancelled. "
                "Save it by hand: VIEW, New."
                + (" The old view of that name was already removed." if existing is not None else "")
            )
    view = next((v for k, v in _views(doc).items() if k.lower() == clean.lower()), None)
    if view is None:
        raise AutocadError(
            f"AutoCAD's VIEW command ran, but no view called '{clean}' is in the drawing. "
            "Save it by hand: VIEW, New."
        )
    return {
        "saved": clean,
        "replaced": existing is not None,
        "from": "the screen",
        "view": _describe(view),
    }


# ---------------------------------------------------------------------------
# A camera view for a render (D-86)
# ---------------------------------------------------------------------------

# AutoCAD's own default lens (LENSLENGTH), a normal eye on a 35 mm camera.
DEFAULT_LENS_MM = 50.0


@mcp.tool(name="autocad_add_camera_view", **tool_meta("Add A Camera View For A Render"))
@tool_errors
async def autocad_add_camera_view(
    name: Annotated[
        str,
        Field(min_length=1, description="What to call the camera view, e.g. 'LIVING-CAM-1'. Spaces are fine."),
    ],
    eye: Annotated[
        list[float],
        Field(description="Where the camera stands, [x, y, z]. Give z: eye height inside a room is about 1600."),
    ],
    target: Annotated[
        list[float],
        Field(description="The point it looks at, [x, y, z], e.g. the far wall at 1200 high."),
    ],
    lens: Annotated[
        float,
        Field(
            default=DEFAULT_LENS_MM, ge=10, le=600,
            description="Lens length in mm on a 35 mm camera: 24 for a whole room, 35 a wide view, 50 a normal eye (AutoCAD's default), 85 and up a close detail.",
        ),
    ] = DEFAULT_LENS_MM,
    look_through: Annotated[
        bool,
        Field(default=True, description="Also put the camera's view on screen, so the modeller sees it and can press Render."),
    ] = True,
    replace: Annotated[
        bool,
        Field(default=False, description="Move a view of this name that is already saved."),
    ] = False,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Make a named perspective camera view at an eye point, looking at a target, through a lens.

    The view for a render, as AutoCAD's CAMERA command makes one: perspective
    on, the lens set (24 mm inside a room), saved under a name so it can be
    rendered and gone back to (VIEW, or the render window's view list). By
    default it is also put on screen.

    Made by Heron's plug-in as one saved view with perspective and the lens
    set, never by DVIEW (which waits for picks and hangs). The view is sized
    to the lens's field at the target, so the two agree. No camera glyph is
    drawn.

    One undo step. It does not render: press Render in AutoCAD.

    Args:
        name (str): the view's name.
        eye (list[float]): the camera, [x, y, z].
        target (list[float]): what it looks at, [x, y, z].
        lens (float): mm, 10 to 600.
        look_through (bool): put it on screen too.
        replace (bool): move a view of this name.
        coords (str): 'world' or 'ucs' for eye and target.

    Returns:
        str: JSON: {"created" | "replaced": true, "name", "handle", "eye",
             "target", "lens_mm", "perspective": true,
             "field_of_view_degrees", "distance", "view_width",
             "view_height", "on_screen": bool (Heron asked AutoCAD to show
             it), "in_drawing": bool, "warning"?: str}

    Examples:
        - Use when: "a camera in the living room corner looking at the
          kitchen, wide angle" — eye at 1600 high, lens=24.
        - Use when: "save three camera views of the villa for the client
          renders" — one call each, then the modeller renders each.
        - Use when: "move LIVING-CAM-1 a bit to the left" — the new eye with
          replace=true.
        - Don't use when: you want to save this 3D angle just as it is on
          screen — autocad_save_view(from_screen=true) keeps exactly that.
        - Don't use when: you only want an isometric look —
          autocad_set_3d_view(direction='sw_iso').
        - Don't use when: it is a CCTV camera symbol or camera block to
          place at a point — autocad_insert_block; this is a view, not a block.

    Error Handling:
        - The same eye and target, or a lens outside 10-600 mm, is refused.
        - A name already saved is refused unless replace=true; a layout's
          (paper space) view of that name is refused even then.
        - It works on the Model tab only: a layout is refused.
        - Needs the Heron plug-in with the add_camera_view operation.
    """
    clean = validate_name(name, "view")
    if not 10 <= lens <= 600:
        raise AutocadError("The lens must be 10-600 mm (24 mm is a wide room shot, 50 mm a normal eye).")
    for label, point in (("eye", eye), ("target", target)):
        if len(point) != 3:
            raise AutocadError(f"{label} must be [x, y, z]: a camera needs its height.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        at = list(world_coords(eye, ucs))
        aim = list(world_coords(target, ucs))
        if math.dist(at, aim) < 1e-9:
            raise AutocadError("The eye and the target are the same point, so the camera looks nowhere.")
        report = in_plugin(
            "add_camera_view",
            {
                "name": clean,
                "eye": at,
                "target": aim,
                "lens": float(lens),
                "look_through": bool(look_through),
                "replace": bool(replace),
            },
            "A camera view",
        )
        payload: dict[str, Any] = dict(report)
        try:
            there = any(k.lower() == clean.lower() for k in _views(doc))
        except BaseException:  # noqa: BLE001 - made is made; only the read-back failed
            there = False
        payload["in_drawing"] = there
        if not there:
            payload["warning"] = (
                f"Heron in AutoCAD saved '{clean}', but it could not be read back from the drawing's "
                "views straight away. Check autocad_list_views; do not make it again."
            )
        warnings = [payload["warning"]] if payload.get("warning") else []
        if look_through:
            # AutoCAD draws perspective only in a 3D visual style, not in 2D Wireframe.
            seen, _why = plugin_read("current_view")
            style = str((seen or {}).get("visual_style") or "")
            if style.strip().lower() == "2dwireframe":
                warnings.append(
                    "The viewport is in the 2D Wireframe style, which does not show perspective. "
                    "Switch to a 3D style: autocad_set_3d_view(visual_style='realistic')."
                )
        if warnings:
            payload["warning"] = " ".join(warnings)
        payload["note"] = (
            "This does not render: press Render in AutoCAD with this view on screen. "
            "Set the sun with autocad_set_sun and the lights with autocad_switch_lights first."
        )
        return payload

    return dumps(await run(work))
