"""Sheets: layouts, page setup, title blocks and viewports.

What a draftsman does at the end of a job, and what this server could not do
before: make the sheet, set the paper and the plotter, drop the title block in
the corner, cut a viewport at a real scale, lock it, and move on to the next
sheet.

Three things make the difference between a sheet and a mess, and all three are
handled here rather than left to the agent:

* **A real scale.** The model window handed to AutoCAD has the viewport's own
  proportions, worked out in ``acad/sheets.py``, so 1:50 comes out 1:50 and not
  1:48.7. The scale is then pinned with the viewport's own CustomScale.
* **A rotated plan.** A wing of a building drawn at 23 degrees reads upright on
  the sheet when the viewport is twisted to match, so ``twist`` and
  ``align_to_ucs`` are first-class options, not an afterthought.
* **Locked viewports.** A viewport left unlocked gets scrolled by the next
  person who zooms inside it, and the scale on the title block becomes a lie.
  These lock by default.

Paper is in the layout's own paper units (millimetres for an ISO sheet).
Paper-space (0, 0) is the lower-left corner of the **printable area**, which is
where AutoCAD puts it for a layout plotted from its own origin; ``anchor`` moves
off that when a title block wants the sheet corner instead.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..acad import sheets as plan
from ..acad.coords import corners_box, rotated_box
from ..acad.entities import bounding_box, resolve_handles
from ..acad.tables import ensure_layer, validate_name
from ..acad.units import rad
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint
from ._shared import COORDS_OPT, current_ucs, ucs_for, world_coords

# The media-name matching is already proven and tested in document.py (the PDF
# export path); a sheet picks its paper the same way rather than a second way.
from .document import _match_media  # noqa: PLC2701

# AcActiveSpace: acPaperSpace = 0, acModelSpace = 1 (document.py reads it too).
AC_PAPER_SPACE = 0
# AcRegenType: acActiveViewport = 0, acAllViewports = 1.
AC_ALL_VIEWPORTS = 1
# AcViewportScale: acVpScaleToFit = 0, acVpCustomScale = 1. CustomScale is only
# read once StandardScale says the scale is a custom one.
AC_VP_CUSTOM_SCALE = 1
# AcPlotType: acDisplay = 0, acExtents = 1, acLimits = 2, acView = 3,
# acWindow = 4, acLayout = 5.
PLOT_AREAS = {"display": 0, "extents": 1, "limits": 2, "view": 3, "window": 4, "layout": 5}
# AcPlotScale: acScaleToFit = 0.
AC_SCALE_TO_FIT = 0
# AcPlotRotation: ac0degrees = 0, ac90degrees = 1, ac180degrees = 2, ac270degrees = 3.
PLOT_ROTATIONS = {0: 0, 90: 1, 180: 2, 270: 3}
# AcPlotPaperUnits: acInches = 0, acMillimeters = 1, acPixels = 2.
PAPER_UNITS = {"inches": 0, "mm": 1, "millimeters": 1}

PDF_PLOTTER = "DWG To PDF.pc3"
# Setting a plotter on a sheet AutoCAD is still building: tries, and the wait between.
PLOTTER_TRIES = 3
PLOTTER_RETRY_DELAY = 0.4
Anchor = Literal["printable", "paper"]


# ---------------------------------------------------------------------------
# Reading the layout
# ---------------------------------------------------------------------------


def _try(getter, default=None):
    """Read one COM property, tolerating a layout that does not carry it."""
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def _read(target: Any, name: str, default: Any = None) -> Any:
    """Read one COM property by name, with a default when the type lacks it."""
    try:
        return getattr(target, name)
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def _is_layout_block(block: Any) -> bool:
    """True for the hidden block behind a layout, which is never insertable."""
    return bool(_read(block, "IsLayout", False))


def _write(target: Any, name: str, value: Any) -> bool:
    """Set one COM property. True when it took, False when AutoCAD refused it.

    Needed because ``setattr`` returns None: a refusal and a success look the
    same through ``_try``, and a viewport that quietly failed to lock is worse
    than one that says so.
    """
    try:
        setattr(target, name, value)
        return True
    except BaseException:  # noqa: BLE001 - a refusal is the answer, not a crash
        return False


def _write_delete(target: Any) -> bool:
    """Delete one COM object. True when it went."""
    try:
        target.Delete()
        return True
    except BaseException:  # noqa: BLE001 - reported by the caller
        return False


def _layouts(doc: Any) -> dict[str, Any]:
    return {
        str(doc.Layouts.Item(i).Name): doc.Layouts.Item(i)
        for i in range(int(doc.Layouts.Count))
    }


def _pick_layout(doc: Any, name: str | None) -> Any:
    """One layout by name, or the active one. 'Model' is refused for sheet work."""
    if not name:
        layout = doc.ActiveLayout
        if str(layout.Name) == "Model":
            raise AutocadError(
                "Model space is active, not a sheet. Name the layout, or switch to one "
                "first — autocad_list_layouts shows what the drawing has."
            )
        return layout
    found = _layouts(doc)
    match = next((v for k, v in found.items() if k.lower() == str(name).strip().lower()), None)
    if match is None:
        have = ", ".join(sorted(k for k in found if k != "Model")) or "none"
        raise AutocadError(f"This drawing has no layout named '{name}'. Layouts: {have}.")
    if str(match.Name) == "Model":
        raise AutocadError("'Model' is model space, not a sheet. Name a layout instead.")
    return match


def _activate(doc: Any, layout: Any) -> None:
    """Make a layout current and put paper space in front, which AddPViewport needs."""
    if str(doc.ActiveLayout.Name) != str(layout.Name):
        doc.ActiveLayout = layout
    if int(_read(doc, "ActiveSpace", AC_PAPER_SPACE)) != AC_PAPER_SPACE:
        _write(doc, "ActiveSpace", AC_PAPER_SPACE)
    if bool(_read(doc, "MSpace", False)):
        _write(doc, "MSpace", False)


def _paper_of(layout: Any) -> dict[str, Any]:
    """The sheet a layout is set to: size, printable area and margins.

    GetPaperSize and GetPaperMargins are the layout's own answers and are used
    first. When a device is not configured they are unavailable, so the size is
    read out of the canonical media name instead — it carries the dimensions,
    e.g. ISO_full_bleed_A3_(420.00_x_297.00_MM).
    """
    media = str(_try(lambda: layout.CanonicalMediaName, "") or "")
    info: dict[str, Any] = {"media": media, "plotter": str(_try(lambda: layout.ConfigName, "") or "")}

    size = _try(lambda: tuple(float(v) for v in layout.GetPaperSize()))
    if not size or len(size) < 2 or min(size[:2]) <= 0:
        size = plan.media_dimensions(media)
    if not size:
        raise AutocadError(
            f"Layout '{_try(lambda: layout.Name, '?')}' has no usable paper size. Set one "
            "with autocad_page_setup (paper_size='A3') before placing anything on it."
        )
    info["paper"] = [round(size[0], 4), round(size[1], 4)]

    margins = _try(lambda: layout.GetPaperMargins())
    low, high = (0.0, 0.0), (0.0, 0.0)
    if margins and len(margins) == 2:
        low = tuple(float(v) for v in margins[0])[:2]
        high = tuple(float(v) for v in margins[1])[:2]
    info["margins"] = [round(low[0], 4), round(low[1], 4), round(high[0], 4), round(high[1], 4)]
    # Paper space (0, 0) sits at the lower-left of the printable area, so the
    # printable rectangle starts there and is the sheet less both margins.
    info["printable"] = [
        0.0,
        0.0,
        round(size[0] - low[0] - high[0], 4),
        round(size[1] - low[1] - high[1], 4),
    ]
    rotation = int(_try(lambda: layout.PlotRotation, 0) or 0)
    info["plot_rotation_degrees"] = next(
        (deg for deg, code in PLOT_ROTATIONS.items() if code == rotation), 0
    )
    return info


def _area_box(info: dict[str, Any], anchor: str) -> plan.Box:
    """The rectangle to work inside: the printable area, or the whole sheet."""
    if str(anchor).strip().lower() == "paper":
        low_x, low_y, _, _ = info["margins"]
        width, height = info["paper"]
        # The sheet, in paper-space coordinates: the printable area is inset by
        # the lower-left margin, so the sheet corner is that much below it.
        return (-low_x, -low_y, width - low_x, height - low_y)
    return tuple(info["printable"])  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------


def _set_page(
    layout: Any,
    plotter: str | None,
    paper_size: str | None,
    orientation: str | None,
    plot_area: str | None,
    window: tuple[Any, Any] | None,
    view_name: str | None,
    scale: str | float | None,
    centre: bool | None,
    style_sheet: str | None,
    lineweights: bool | None,
    plot_styles: bool | None,
    paper_units: str | None,
) -> dict[str, Any]:
    """Apply a page setup to one layout. Returns what was actually written."""
    written: dict[str, Any] = {}

    if plotter:
        # Right after Layouts.Add AutoCAD is still building the sheet, and
        # pywin32 reports that busy moment as "Property 'Add.ConfigName' can
        # not be set" (2026-11-05). A short retry gets past it; a plotter that
        # really is missing fails every time.
        failure: BaseException | None = None
        for attempt in range(PLOTTER_TRIES):
            try:
                layout.ConfigName = str(plotter).strip()
                failure = None
                break
            except BaseException as exc:  # noqa: BLE001
                failure = exc
                if attempt < PLOTTER_TRIES - 1:
                    time.sleep(PLOTTER_RETRY_DELAY)
        if failure is not None:
            raise AutocadError(
                f"AutoCAD would not set the plotter '{plotter}' ({com_message(failure)}). "
                "Use the name exactly as it appears in Page Setup, e.g. 'DWG To PDF.pc3'."
            ) from failure
        # The new device may not offer the sheet that was set, so AutoCAD has
        # to be asked what it does offer before the media name is chosen.
        _try(lambda: layout.RefreshPlotDeviceInfo())
        written["plotter"] = str(plotter).strip()

    if paper_size:
        names = tuple(_try(lambda: layout.GetCanonicalMediaNames(), ()) or ())
        if not names:
            raise AutocadError(
                "AutoCAD reported no sheet sizes for this layout's plotter. Set the plotter "
                f"first (plotter='{PDF_PLOTTER}')."
            )
        wanted = str(paper_size).strip()
        if orientation and not any(w in wanted.lower() for w in ("portrait", "landscape")):
            wanted = f"{wanted} {str(orientation).strip().lower()}"
        layout.CanonicalMediaName = _match_media(names, wanted)
        written["paper_size"] = str(_try(lambda: layout.GetLocaleMediaName(layout.CanonicalMediaName), wanted))

    if orientation:
        key = str(orientation).strip().lower()
        if key not in ("portrait", "landscape"):
            raise AutocadError("orientation must be 'portrait' or 'landscape'.")
        # An ISO sheet comes in both ways round and the media name says which,
        # so the orientation is chosen with the paper size above - it is not a
        # setting of its own. PlotRotation only turns the drawing on the sheet,
        # so it is left alone. On its own, orientation therefore does nothing,
        # and saying so beats reporting a change that did not happen.
        if paper_size:
            written["orientation"] = key
        else:
            written["orientation_ignored"] = (
                f"'{key}' needs a paper_size with it: the sheet itself carries which way round "
                "it goes. Pass paper_size as well."
            )

    if plot_area:
        key = str(plot_area).strip().lower()
        if key not in PLOT_AREAS:
            raise AutocadError(
                f"'{plot_area}' is not a plot area. Use one of: {', '.join(sorted(PLOT_AREAS))}."
            )
        if key == "window":
            if not window:
                raise AutocadError("plot_area='window' needs corner1 and corner2.")
            layout.SetWindowToPlot(window[0], window[1])
        if key == "view":
            if not view_name:
                raise AutocadError("plot_area='view' needs view_name, a saved view in this drawing.")
            layout.ViewToPlot = str(view_name).strip()
        layout.PlotType = PLOT_AREAS[key]
        written["plot_area"] = key

    if scale is not None:
        if str(scale).strip().lower() in ("fit", "scaletofit", "scale to fit"):
            layout.UseStandardScale = True
            layout.StandardScale = AC_SCALE_TO_FIT
            written["scale"] = "fit"
        else:
            ratio = plan.parse_typed_scale(scale)
            layout.UseStandardScale = False
            layout.CustomScale = ratio
            written["scale"] = plan.scale_text(ratio)

    if centre is not None:
        layout.CenterPlot = bool(centre)
        written["centred"] = bool(centre)

    if style_sheet is not None:
        name = str(style_sheet).strip()
        try:
            layout.StyleSheet = name
        except BaseException as exc:  # noqa: BLE001
            raise AutocadError(
                f"AutoCAD would not use the plot style table '{name}' ({com_message(exc)}). "
                "Give the file name as it appears in Page Setup, e.g. 'monochrome.ctb', and "
                "check the drawing is in the matching (colour-dependent or named) plot mode."
            ) from exc
        written["plot_style_table"] = name
        if plot_styles is None and name:
            _write(layout, "PlotWithPlotStyles", True)

    if lineweights is not None:
        _write(layout, "PlotWithLineweights", bool(lineweights))
        written["plot_with_lineweights"] = bool(lineweights)
    if plot_styles is not None:
        _write(layout, "PlotWithPlotStyles", bool(plot_styles))
        written["plot_with_plot_styles"] = bool(plot_styles)

    if paper_units:
        key = str(paper_units).strip().lower()
        if key not in PAPER_UNITS:
            raise AutocadError("paper_units must be 'mm' or 'inches'.")
        _write(layout, "PaperUnits", PAPER_UNITS[key])
        written["paper_units"] = "mm" if PAPER_UNITS[key] == 1 else "inches"

    return written


@mcp.tool(name="autocad_page_setup", **tool_meta("Set Up The Sheet For Plotting"))
@tool_errors
async def autocad_page_setup(
    layouts: Annotated[
        list[str] | None,
        Field(default=None, description="Layouts to set up. Omit for the active one; use all_layouts for every sheet."),
    ] = None,
    all_layouts: Annotated[
        bool,
        Field(default=False, description="Set every layout in the drawing the same way."),
    ] = False,
    plotter: Annotated[
        str | None,
        Field(default=None, description=f"Plotter or .pc3 name, e.g. '{PDF_PLOTTER}'. Exactly as Page Setup spells it."),
    ] = None,
    paper_size: Annotated[
        str | None,
        Field(default=None, description="Sheet size, e.g. 'A3', 'A1', 'ANSI D', 'ARCH E1'."),
    ] = None,
    orientation: Annotated[
        Literal["portrait", "landscape"] | None,
        Field(default=None, description="Which way round the sheet goes."),
    ] = None,
    plot_area: Annotated[
        str | None,
        Field(default=None, description="What to plot: 'layout' (the sheet, normal for a title-block sheet), 'extents', 'limits', 'display', 'window' or 'view'."),
    ] = None,
    corner1: Annotated[list[float] | None, Field(default=None, description="For plot_area='window': one corner, in paper units.")] = None,
    corner2: Annotated[list[float] | None, Field(default=None, description="For plot_area='window': the opposite corner.")] = None,
    view_name: Annotated[str | None, Field(default=None, description="For plot_area='view': a saved view's name.")] = None,
    scale: Annotated[
        str | float | None,
        Field(default=None, description="Plot scale: '1:1' for a sheet laid out at full size, or 'fit'."),
    ] = None,
    centred: Annotated[bool | None, Field(default=None, description="Centre the plot on the sheet.")] = None,
    plot_style_table: Annotated[
        str | None,
        Field(default=None, description="Plot style table, e.g. 'monochrome.ctb' for a black-and-white set."),
    ] = None,
    plot_with_lineweights: Annotated[bool | None, Field(default=None, description="Plot the lineweights as drawn.")] = None,
    plot_with_plot_styles: Annotated[bool | None, Field(default=None, description="Apply the plot style table when plotting.")] = None,
    paper_units: Annotated[Literal["mm", "inches"] | None, Field(default=None, description="The layout's paper units.")] = None,
) -> str:
    """Set a sheet's plotter, paper size, plot area, scale and plot style table.

    This is AutoCAD's Page Setup, done to one sheet or to every sheet at once —
    the job nobody enjoys doing 42 times by hand. A title-block sheet is
    normally plot_area='layout', scale='1:1', centred, with the office
    monochrome.ctb; the viewports inside carry the drawing scales.

    Only the options you pass are written; everything else on the sheet is left
    as it was. One undo step.

    Args:
        layouts (Optional[list[str]]): the sheets to set up.
        all_layouts (bool): every sheet in the drawing.
        plotter (Optional[str]): plotter / .pc3 name.
        paper_size (Optional[str]): 'A3', 'ANSI D', ...
        orientation (Optional[str]): portrait or landscape.
        plot_area (Optional[str]): layout, extents, limits, display, window, view.
        corner1 / corner2 (Optional[list[float]]): the window, in paper units.
        view_name (Optional[str]): the saved view, for plot_area='view'.
        scale (Optional[str | float]): '1:1', '1:50' or 'fit'.
        centred (Optional[bool]): centre it on the sheet.
        plot_style_table (Optional[str]): e.g. 'monochrome.ctb'.
        plot_with_lineweights / plot_with_plot_styles (Optional[bool]).
        paper_units (Optional[str]): 'mm' or 'inches'.

    Returns:
        str: JSON: {"layouts": [{"name", "written": {...}, "paper": {...}}],
             "count": int}

    Examples:
        - Use when: "set all 42 sheets to A1, DWG To PDF, monochrome, 1:1".
        - Use when: a sheet plots the wrong size because its paper is still A4.
        - Don't use when: you want the PDF itself — that is autocad_export.

    Error Handling:
        - A plotter or sheet size AutoCAD does not have is named in the error,
          with the sizes that plotter does offer.
        - The plotter is set before the sheet size, because a device only
          offers its own sizes.
    """
    window = None
    if corner1 and corner2:
        if len(corner1) < 2 or len(corner2) < 2:
            raise AutocadError("corner1 and corner2 each need [x, y] in paper units.")
        window = (apoint(float(corner1[0]), float(corner1[1])), apoint(float(corner2[0]), float(corner2[1])))

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        found = _layouts(doc)
        if all_layouts:
            targets = [v for k, v in sorted(found.items()) if k != "Model"]
            if not targets:
                raise AutocadError("This drawing has no layouts, only model space.")
        elif layouts:
            targets = [_pick_layout(doc, name) for name in layouts]
        else:
            targets = [_pick_layout(doc, None)]

        rows = []
        with undo_mark(doc):
            for layout in targets:
                written = _set_page(
                    layout, plotter, paper_size, orientation, plot_area, window,
                    view_name, scale, centred, plot_style_table,
                    plot_with_lineweights, plot_with_plot_styles, paper_units,
                )
                rows.append({"name": str(layout.Name), "written": written, "paper": _paper_of(layout)})
        return {"count": len(rows), "layouts": rows}

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Creating a sheet
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_create_layout", **tool_meta("Create A Sheet"))
@tool_errors
async def autocad_create_layout(
    name: Annotated[str, Field(min_length=1, description="The new sheet's name, e.g. 'E-101'.")],
    paper_size: Annotated[
        str | None,
        Field(default=None, description="Sheet size, e.g. 'A3', 'A1', 'ANSI D'. Omit to keep the template's."),
    ] = None,
    orientation: Annotated[
        Literal["portrait", "landscape"],
        Field(default="landscape", description="Which way round the sheet goes."),
    ] = "landscape",
    plotter: Annotated[
        str | None,
        Field(default=PDF_PLOTTER, description=f"Plotter for the sheet. Defaults to '{PDF_PLOTTER}'; pass null to leave it."),
    ] = PDF_PLOTTER,
    plot_style_table: Annotated[
        str | None,
        Field(default=None, description="Plot style table, e.g. 'monochrome.ctb'."),
    ] = None,
    copy_from: Annotated[
        str | None,
        Field(default=None, description="Copy an existing layout as the template, title block and all, instead of starting empty."),
    ] = None,
    margins: Annotated[
        list[float] | None,
        Field(default=None, description="Frame margins as [left, bottom, right, top], or one number for all four. Default: ISO 5457's 20 / 10 / 10 / 10."),
    ] = None,
    title_block_width: Annotated[
        float | None,
        Field(default=None, description="Width of the strip on the right the title block occupies, so the drawing space stops clear of it."),
    ] = None,
    activate: Annotated[bool, Field(default=True, description="Switch to the new sheet when it is made.")] = True,
) -> str:
    """Make a new sheet: the layout, its paper and plotter, and the space left to draw in.

    Returns the sheet's arithmetic worked out — paper size, frame, the corner a
    title block goes in, and the rectangle left for viewports — so the next
    call can place things without measuring. Follow it with
    autocad_place_title_block and autocad_add_viewport, or put all three in one
    autocad_sequence.

    One undo step.

    Args:
        name (str): the sheet name.
        paper_size (Optional[str]): 'A3', 'A1', 'ANSI D', ...
        orientation (str): portrait or landscape.
        plotter (Optional[str]): plotter name, or null to leave it alone.
        plot_style_table (Optional[str]): e.g. 'monochrome.ctb'.
        copy_from (Optional[str]): an existing layout to copy.
        margins (Optional[list[float]]): frame margins.
        title_block_width (Optional[float]): strip reserved on the right.
        activate (bool): switch to it.

    Returns:
        str: JSON: {
          "created": true, "layout": str, "tab_order": int,
          "page_setup": {...}, "paper": {...},
          "sheet": {"paper", "orientation", "frame", "drawing_space",
                    "title_block_at", "drawing_space_size"}
        }

    Examples:
        - Use when: "add sheet E-102, A1 landscape, mono".
        - Use when: "copy sheet E-101 for the next level" — copy_from='E-101'.
        - Don't use when: renaming or reordering existing sheets
          (autocad_manage_layouts).

    Error Handling:
        - A name already in the drawing is refused before anything is made.
        - copy_from naming a layout that is not there lists the ones that are.
    """
    clean = validate_name(name, "layout")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        found = _layouts(doc)
        if any(k.lower() == clean.lower() for k in found):
            raise AutocadError(
                f"This drawing already has a layout called '{clean}'. Pick another name, "
                "or change that one with autocad_page_setup."
            )

        with undo_mark(doc):
            if copy_from:
                source = _pick_layout(doc, copy_from)
                try:
                    layout = doc.Layouts.Add(clean)
                    layout.CopyFrom(source)
                except BaseException as exc:  # noqa: BLE001
                    raise AutocadError(
                        f"Could not copy layout '{copy_from}' ({com_message(exc)}). Make the "
                        "sheet without copy_from, or copy its contents with "
                        "autocad_manage_layouts(copy_handles=...)."
                    ) from exc
            else:
                try:
                    layout = doc.Layouts.Add(clean)
                except BaseException as exc:  # noqa: BLE001
                    raise AutocadError(f"AutoCAD would not add the layout '{clean}': {com_message(exc)}") from exc

            try:
                # Fetched again from the collection: the object Add returned is
                # the one pywin32 could not set the plotter on.
                layout = _pick_layout(doc, clean)
                page = _set_page(
                    layout, plotter, paper_size, orientation, "layout", None, None,
                    "1:1", True, plot_style_table, None, None, None,
                )
            except BaseException as exc:
                # Never leave a half-made sheet: the retry would only be told
                # the name is taken (2026-11-05).
                kept = not _write_delete(layout)
                if isinstance(exc, AutocadError) and not kept:
                    raise AutocadError(
                        f"{exc} The layout '{clean}' was not kept, so the call can be "
                        "repeated as it is."
                    ) from exc
                raise
            if activate:
                _activate(doc, layout)

        info = _paper_of(layout)
        width, height = info["paper"]
        sheet = {
            "paper": [width, height],
            "orientation": "portrait" if height > width else "landscape",
        }
        try:
            area = _area_box(info, "printable")
            outline = plan.frame(*plan.size_of(area), margins)
            outline = (outline[0] + area[0], outline[1] + area[1], outline[2] + area[0], outline[3] + area[1])
            space = outline
            if title_block_width:
                space = plan.reserve(space, "right", float(title_block_width))
            sheet.update(
                {
                    "printable": info["printable"],
                    "frame": [round(v, 4) for v in outline],
                    "drawing_space": [round(v, 4) for v in space],
                    "drawing_space_size": [round(v, 4) for v in plan.size_of(space)],
                    "title_block_at": [round(v, 4) for v in plan.corner_point(outline, "bottom-right")],
                }
            )
        except ValueError as exc:
            sheet["frame_note"] = f"The frame could not be worked out: {exc}"

        return {
            "created": True,
            "layout": str(layout.Name),
            "tab_order": int(_try(lambda: layout.TabOrder, 0) or 0),
            "page_setup": page,
            "paper": info,
            "sheet": sheet,
        }

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Title blocks
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_place_title_block", **tool_meta("Place The Title Block"))
@tool_errors
async def autocad_place_title_block(
    block: Annotated[
        str,
        Field(min_length=1, description="A block already in the drawing, or the full path to a title-block .dwg."),
    ],
    layouts: Annotated[
        list[str] | None,
        Field(default=None, description="Sheets to place it on. Omit for the active sheet."),
    ] = None,
    all_layouts: Annotated[
        bool,
        Field(default=False, description="Place it on every sheet in the drawing — the 42-sheet job in one call."),
    ] = False,
    corner: Annotated[
        str,
        Field(default="bottom-right", description="Which corner of the sheet the block's own insertion point goes in: bottom-right (the ISO 5457 place), bottom-left, top-right, top-left, bottom-centre or centre."),
    ] = "bottom-right",
    anchor: Annotated[
        Anchor,
        Field(default="printable", description="Measure from the 'printable' area (paper space 0,0 — right for most title blocks) or from the 'paper' edge."),
    ] = "printable",
    margins: Annotated[
        list[float] | None,
        Field(default=None, description="Frame margins as [left, bottom, right, top] or one number. Default: ISO 5457's 20 / 10 / 10 / 10. Pass [0] to sit on the sheet edge."),
    ] = None,
    offset: Annotated[
        list[float] | None,
        Field(default=None, description="Nudge from that corner as [dx, dy] in paper units, for a block whose insertion point is not on its own corner."),
    ] = None,
    scale: Annotated[float, Field(default=1.0, gt=0, description="Scale of the block on the paper. A title block drawn at 1:1 in millimetres wants 1.0.")] = 1.0,
    rotation: Annotated[float, Field(default=0.0, description="Rotation in degrees.")] = 0.0,
    attributes: Annotated[
        dict[str, str] | None,
        Field(default=None, description='Attributes to fill, by tag: {"DWG_NO": "E-101", "SCALE": "1:50", "DATE": "2026-10-26"}. Tags match case-insensitively.'),
    ] = None,
    per_layout_attributes: Annotated[
        dict[str, dict[str, str]] | None,
        Field(default=None, description='Attributes per sheet: {"E-101": {"DWG_NO": "E-101"}, "E-102": {...}}. Merged over "attributes".'),
    ] = None,
    layer: Annotated[
        str | None,
        Field(default=None, description="Layer for the title block, created if missing. A drafter keeps it on its own non-plotting-free layer, e.g. 'G-TTLB'."),
    ] = None,
    replace_existing: Annotated[
        bool,
        Field(default=False, description="Delete any reference to the same block already on the sheet first, instead of stacking a second one on top."),
    ] = False,
) -> str:
    """Drop a title block in the corner of one sheet, or of every sheet, and fill it in.

    The corner is worked out from the sheet's own paper size and the frame
    margins, so the block lands in the same place on an A3 and on an A0. ISO
    5457 puts it bottom-right inside a frame of 20 mm on the binding edge and
    10 mm elsewhere, which is the default here.

    One undo step for the whole run.

    Args:
        block (str): block name or .dwg path.
        layouts (Optional[list[str]]): the sheets.
        all_layouts (bool): every sheet.
        corner (str): which corner.
        anchor (str): measure from the printable area or the paper edge.
        margins (Optional[list[float]]): frame margins.
        offset (Optional[list[float]]): nudge from the corner.
        scale (float): block scale on paper.
        rotation (float): degrees.
        attributes (Optional[dict[str, str]]): values for every sheet.
        per_layout_attributes (Optional[dict]): values per sheet.
        layer (Optional[str]): target layer.
        replace_existing (bool): remove an existing one first.

    Returns:
        str: JSON: {"count": int, "placed": [{"layout", "handle", "at",
             "attributes_set": [str], "attributes_not_found": [str],
             "replaced": int}], "block": str}

    Examples:
        - Use when: "put our A1 title block on all 42 sheets and number them".
        - Use when: a sheet came in without a title block.
        - Don't use when: only the text needs changing — autocad_set_attributes
          fills title blocks already on the sheets.
        - Don't use when: the title block should only be brought in from the
          template, not placed yet — autocad_import_from_drawing.

    Error Handling:
        - A block that is neither in the drawing nor a .dwg on disk is reported
          with the blocks the drawing does have.
        - Attribute tags the block does not carry come back in
          "attributes_not_found" rather than failing the sheet.
    """
    from .draw import dwg_path  # the proven path normaliser for InsertBlock

    name = block.strip().strip('"')
    source = dwg_path(name) if name.lower().endswith(".dwg") else None
    nudge = (float(offset[0]), float(offset[1])) if offset and len(offset) >= 2 else (0.0, 0.0)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)

        block_name = source
        if block_name is None:
            try:
                doc.Blocks.Item(name)
            except BaseException:  # noqa: BLE001 - say what the drawing does have
                have = []
                for i in range(int(doc.Blocks.Count)):
                    item = doc.Blocks.Item(i)
                    label = str(item.Name)
                    if label and not label.startswith("*") and not _is_layout_block(item):
                        have.append(label)
                raise AutocadError(
                    f"No block named '{name}' is in this drawing. Blocks: "
                    + (", ".join(sorted(have)[:40]) if have else "none")
                    + ". To bring one in from a file, pass the full .dwg path."
                ) from None
            block_name = name

        found = _layouts(doc)
        if all_layouts:
            targets = [v for k, v in sorted(found.items()) if k != "Model"]
            if not targets:
                raise AutocadError("This drawing has no layouts, only model space.")
        elif layouts:
            targets = [_pick_layout(doc, label) for label in layouts]
        else:
            targets = [_pick_layout(doc, None)]

        placed = []
        with undo_mark(doc):
            if layer:
                ensure_layer(doc, layer)
            for layout in targets:
                label = str(layout.Name)
                info = _paper_of(layout)
                try:
                    area = _area_box(info, anchor)
                    outline = plan.frame(*plan.size_of(area), margins)
                    outline = (outline[0] + area[0], outline[1] + area[1], outline[2] + area[0], outline[3] + area[1])
                    at = plan.corner_point(outline, corner)
                except ValueError as exc:
                    raise AutocadError(f"Sheet '{label}': {exc}") from exc
                at = (at[0] + nudge[0], at[1] + nudge[1])

                _activate(doc, layout)
                space = doc.PaperSpace
                removed = 0
                if replace_existing:
                    for existing in list(_references(space, block_name)):
                        try:
                            existing.Delete()
                            removed += 1
                        except BaseException:  # noqa: BLE001 - a locked layer, reported by count
                            pass

                try:
                    reference = space.InsertBlock(
                        apoint(at[0], at[1], 0.0), block_name,
                        float(scale), float(scale), float(scale), rad(rotation),
                    )
                except BaseException as exc:  # noqa: BLE001
                    raise AutocadError(
                        f"Sheet '{label}': AutoCAD would not insert '{name}' ({com_message(exc)})."
                    ) from exc
                if layer:
                    reference.Layer = layer.strip()

                wanted = {k.strip().upper(): v for k, v in (attributes or {}).items()}
                for sheet_name, extra in (per_layout_attributes or {}).items():
                    if sheet_name.strip().lower() == label.lower():
                        wanted.update({k.strip().upper(): v for k, v in extra.items()})
                applied, missing = _fill_attributes(reference, wanted)

                placed.append(
                    {
                        "layout": label,
                        "handle": str(reference.Handle),
                        "at": [round(at[0], 4), round(at[1], 4)],
                        "frame": [round(v, 4) for v in outline],
                        "attributes_set": applied,
                        "attributes_not_found": missing,
                        "replaced": removed,
                    }
                )
        return {"block": block_name, "count": len(placed), "placed": placed}

    return dumps(await run(work))


def _references(space: Any, block_name: str) -> list[Any]:
    """Every reference to one block in a space, by its effective name."""
    wanted = str(block_name).rsplit("\\", 1)[-1].removesuffix(".dwg").lower()
    out = []
    for i in range(int(space.Count)):
        item = space.Item(i)
        if _read(item, "ObjectName", "") != "AcDbBlockReference":
            continue
        label = str(_read(item, "EffectiveName", "") or _read(item, "Name", ""))
        if label.lower() == wanted:
            out.append(item)
    return out


def _fill_attributes(reference: Any, wanted: dict[str, str]) -> tuple[list[str], list[str]]:
    """Fill a block reference's attributes by tag. Returns (set, not found)."""
    if not wanted:
        return [], []
    applied: list[str] = []
    seen: set[str] = set()
    if _try(lambda: bool(reference.HasAttributes), False):
        for att in reference.GetAttributes():
            tag = str(att.TagString).upper()
            if tag in wanted:
                att.TextString = str(wanted[tag])
                applied.append(tag)
                seen.add(tag)
    return applied, sorted(set(wanted) - seen)


# ---------------------------------------------------------------------------
# Viewports
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_add_viewport", **tool_meta("Add A Viewport To The Sheet"))
@tool_errors
async def autocad_add_viewport(
    layout: Annotated[str | None, Field(default=None, description="The sheet. Omit for the active one.")] = None,
    scale: Annotated[
        str | float | None,
        Field(default=None, description="Drawing scale for the viewport: '1:50', '1:100', '1:5'. Omit and the largest standard scale that fits the area is chosen and reported."),
    ] = None,
    centre: Annotated[
        list[float] | None,
        Field(default=None, description="The drawing-space point the viewport looks at, as [x, y]."),
    ] = None,
    corner1: Annotated[list[float] | None, Field(default=None, description="Instead of centre: one corner of the drawing-space area to show.")] = None,
    corner2: Annotated[list[float] | None, Field(default=None, description="The opposite corner of that area.")] = None,
    view_name: Annotated[str | None, Field(default=None, description="Instead of a point or a window: a saved view (autocad_save_view), so a plotted area and a viewport use the very same location.")] = None,
    handles: Annotated[list[str] | None, Field(default=None, description="Instead of the above: show exactly these objects, by their own extents.")] = None,
    paper_centre: Annotated[list[float] | None, Field(default=None, description="Where the viewport sits on the paper, as [x, y]. Omit to fill the sheet's frame.")] = None,
    paper_width: Annotated[float | None, Field(default=None, gt=0, description="Viewport width on the paper. Omit to fill the frame.")] = None,
    paper_height: Annotated[float | None, Field(default=None, gt=0, description="Viewport height on the paper. Omit to fill the frame.")] = None,
    margins: Annotated[list[float] | None, Field(default=None, description="Frame margins used when filling the sheet: [left, bottom, right, top] or one number. Default ISO 5457.")] = None,
    title_block_width: Annotated[float | None, Field(default=None, description="Strip on the right the title block takes, kept clear when filling the frame.")] = None,
    gap: Annotated[float, Field(default=0.0, ge=0, description="Extra clearance inside the frame, in paper units.")] = 0.0,
    twist: Annotated[
        float | None,
        Field(default=None, description="Turn the view inside the viewport, in degrees, so a wing drawn on a slant reads upright on the sheet."),
    ] = None,
    align_to_ucs: Annotated[
        bool,
        Field(default=False, description="Take the twist from the drawing's current UCS, so a plan set up on a rotated grid comes out square on the sheet."),
    ] = False,
    locked: Annotated[
        bool,
        Field(default=True, description="Lock the viewport once it is set. On by default: an unlocked viewport gets scrolled and the scale on the title block stops being true."),
    ] = True,
    layer: Annotated[str | None, Field(default=None, description="Layer for the viewport border, created if missing. A drafter puts it on a non-plotting layer such as 'G-VPRT'.")] = None,
    color: Annotated[str | StrictInt | None, Field(default=None, description="Colour of the viewport border.")] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Cut a viewport in a sheet at a real scale, looking where you tell it.

    Say where to look — a point, a window, a saved view, or a set of objects —
    and at what scale, and the viewport is made, aimed, scaled exactly, twisted
    if the plan is on a slant, and locked.

    Omit the scale and the largest standard scale that fits is used and
    reported, which is what a drafter does when the sheet size is fixed.

    One undo step.

    Args:
        layout (Optional[str]): the sheet.
        scale (Optional[str | float]): '1:50', or omit to fit.
        centre (Optional[list[float]]): the drawing point to look at.
        corner1 / corner2 (Optional[list[float]]): the area to show.
        view_name (Optional[str]): a saved view to show.
        handles (Optional[list[str]]): show these objects.
        paper_centre / paper_width / paper_height (Optional[float]): the
            viewport's own place on the paper; omit to fill the frame.
        margins (Optional[list[float]]), title_block_width (Optional[float]),
            gap (float): how the frame is filled.
        twist (Optional[float]): turn the view, in degrees.
        align_to_ucs (bool): take the twist from the current UCS.
        locked (bool): lock it (default true).
        layer (Optional[str]), color (Optional[str | int]): the border.
        coords (str): 'world' or 'ucs' for the drawing-space points.

    Returns:
        str: JSON: {
          "created": true, "handle": str, "layout": str,
          "scale": "1:50", "scale_ratio": float, "fitted": bool,
          "paper_rect": [x1, y1, x2, y2], "model_window": [x1, y1, x2, y2],
          "looking_at": [x, y], "twist_degrees": float, "locked": bool
        }

    Examples:
        - Use when: "put the ground floor on this A1 at 1:100".
        - Use when: "same area I just plotted" — autocad_save_view first, then
          view_name here.
        - Use when: the plan is on a 23 degree grid — align_to_ucs=true.
        - Don't use when: you want the whole sheet plotted (autocad_export).

    Error Handling:
        - An area that will not fit the viewport at any standard scale says so
          and names the smallest one tried.
        - A saved view the drawing does not have is reported with the ones it has.
    """
    aci = to_aci(color)
    if sum(v is not None for v in (centre, corner1, view_name, handles)) > 1:
        raise AutocadError(
            "Give only one of centre, corner1/corner2, view_name or handles — they are "
            "four ways of saying the same thing."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        sheet = _pick_layout(doc, layout)
        info = _paper_of(sheet)
        ucs = ucs_for(doc, coords)

        # 1. Where on the paper.
        if paper_centre and paper_width and paper_height:
            if len(paper_centre) < 2:
                raise AutocadError("paper_centre needs [x, y] in paper units.")
            cx, cy = float(paper_centre[0]), float(paper_centre[1])
            pw, ph = float(paper_width), float(paper_height)
            paper_rect = (cx - pw / 2.0, cy - ph / 2.0, cx + pw / 2.0, cy + ph / 2.0)
        else:
            try:
                area = _area_box(info, "printable")
                outline = plan.frame(*plan.size_of(area), margins)
                outline = (outline[0] + area[0], outline[1] + area[1], outline[2] + area[0], outline[3] + area[1])
                if title_block_width:
                    outline = plan.reserve(outline, "right", float(title_block_width))
                paper_rect = plan.inset(outline, gap) if gap else outline
            except ValueError as exc:
                raise AutocadError(
                    f"The viewport could not be fitted to sheet '{sheet.Name}': {exc}. Give "
                    "paper_centre, paper_width and paper_height instead."
                ) from exc
            cx, cy = plan.centre_of(paper_rect)
            pw, ph = plan.size_of(paper_rect)

        # 2. Where to look, in world coordinates.
        model_box, look_at = _target_area(doc, centre, corner1, corner2, view_name, handles, ucs)

        # 3. The twist, and the area a twisted view has to cover. A viewport's
        #    twist is its view rotation against the world (VIEWTWIST), and a
        #    plan view of a UCS turned 23 degrees carries a twist of 23 - which
        #    is what makes a plan drawn on that grid read upright. An explicit
        #    twist wins over align_to_ucs.
        if twist is not None:
            angle = float(twist)
        elif align_to_ucs:
            angle = current_ucs(doc).rotation_degrees
        else:
            angle = 0.0
        fitting_box = rotated_box(model_box, angle) if angle and model_box else model_box

        # 4. The scale.
        fitted = scale is None
        if fitted:
            if not fitting_box:
                raise AutocadError(
                    "Without a scale there has to be an area to fit: give corner1/corner2, "
                    "view_name or handles, or name the scale."
                )
            try:
                text, ratio = plan.fit_scale(fitting_box, pw, ph)
            except ValueError as exc:
                raise AutocadError(str(exc)) from exc
        else:
            ratio = plan.parse_typed_scale(scale)
            text = plan.scale_text(ratio)

        window = plan.model_window(look_at, pw, ph, ratio)

        with undo_mark(doc):
            if layer:
                ensure_layer(doc, layer)
            _activate(doc, sheet)
            try:
                viewport = doc.PaperSpace.AddPViewport(apoint(cx, cy, 0.0), pw, ph)
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(
                    f"AutoCAD would not add a viewport to '{sheet.Name}' ({com_message(exc)}). "
                    "Check the sheet is a layout and not model space."
                ) from exc
            if layer:
                viewport.Layer = layer.strip()
            if aci is not None:
                viewport.Color = aci

            notes = _aim(doc, viewport, window, angle, ratio, locked)

        result: dict[str, Any] = {
            "created": True,
            "handle": str(viewport.Handle),
            "layout": str(sheet.Name),
            "scale": text,
            "scale_ratio": round(ratio, 9),
            "fitted": fitted,
            "paper_rect": [round(v, 4) for v in paper_rect],
            "model_window": [round(v, 4) for v in window],
            "looking_at": [round(look_at[0], 4), round(look_at[1], 4)],
            "twist_degrees": round(angle % 360.0, 6),
            "locked": bool(locked),
            "layer": str(_try(lambda: viewport.Layer, "") or ""),
        }
        result.update(notes)
        return result

    return dumps(await run(work))


def _target_area(
    doc: Any,
    centre: list[float] | None,
    corner1: list[float] | None,
    corner2: list[float] | None,
    view_name: str | None,
    handles: list[str] | None,
    ucs: Any,
) -> tuple[plan.Box | None, tuple[float, float]]:
    """What the viewport should show, as (area or None, the point to centre on).

    Four ways in, one answer out: a point gives no area (the scale must then be
    given), the other three give an area whose middle is the point.
    """
    if centre:
        if len(centre) < 2:
            raise AutocadError("centre needs [x, y] in drawing units.")
        x, y, _ = world_coords(centre, ucs)
        return None, (x, y)

    if corner1 or corner2:
        if not (corner1 and corner2):
            raise AutocadError("An area needs both corner1 and corner2.")
        a = world_coords(corner1, ucs)
        b = world_coords(corner2, ucs)
        box = corners_box(a, b)
        return box, plan.centre_of(box)

    if view_name:
        return _view_area(doc, view_name)

    if handles:
        boxes = []
        for entity in resolve_handles(doc, handles):
            found = bounding_box(entity)
            if found:
                boxes.append(found)
        if not boxes:
            raise AutocadError(
                "None of those objects reported extents, so there is nothing to aim at. "
                "Give centre, or corner1/corner2."
            )
        box = (
            min(b["min"][0] for b in boxes),
            min(b["min"][1] for b in boxes),
            max(b["max"][0] for b in boxes),
            max(b["max"][1] for b in boxes),
        )
        return box, plan.centre_of(box)

    raise AutocadError(
        "Say where the viewport should look: centre, corner1/corner2, view_name or handles."
    )


def _view_area(doc: Any, view_name: str) -> tuple[plan.Box, tuple[float, float]]:
    """A saved view's area: its own centre, width and height."""
    views = {}
    for i in range(int(doc.Views.Count)):
        item = doc.Views.Item(i)
        views[str(item.Name)] = item
    match = next((v for k, v in views.items() if k.lower() == str(view_name).strip().lower()), None)
    if match is None:
        have = ", ".join(sorted(views)) or "none"
        raise AutocadError(f"This drawing has no saved view called '{view_name}'. Views: {have}.")
    middle = tuple(float(v) for v in _try(lambda: match.Center, (0.0, 0.0, 0.0)))[:2]
    width = float(_try(lambda: match.Width, 0.0) or 0.0)
    height = float(_try(lambda: match.Height, 0.0) or 0.0)
    if width <= 0.0 or height <= 0.0:
        raise AutocadError(
            f"The saved view '{view_name}' reports no size, so it cannot be fitted. "
            "Save it again with autocad_save_view from a window."
        )
    return (
        middle[0] - width / 2.0,
        middle[1] - height / 2.0,
        middle[0] + width / 2.0,
        middle[1] + height / 2.0,
    ), (middle[0], middle[1])


def _aim(
    doc: Any, viewport: Any, window: plan.Box, twist: float, ratio: float, locked: bool
) -> dict[str, Any]:
    """Point a viewport at a drawing area, pin its scale, and lock it.

    The order matters and is the documented one: the viewport has to be on and
    regenerated before model space can be entered through it, the twist has to
    be set before the zoom so the zoom happens in the turned frame, and the
    lock has to come last or it refuses the zoom.

    The zoom puts the centre right; CustomScale then pins the scale exactly,
    because a zoom to a window can only ever land near a round scale.
    """
    notes: dict[str, Any] = {}
    viewport.ViewportOn = True
    _try(lambda: doc.Regen(AC_ALL_VIEWPORTS))

    if twist and not _write(viewport, "TwistAngle", rad(twist)):
        notes["twist_note"] = (
            "AutoCAD did not accept the twist angle, so the view is not turned. Turn it "
            "by hand in the viewport, or set the UCS and draw the plan square."
        )

    if _write(doc, "MSpace", True):
        _write(doc, "ActivePViewport", viewport)
        _try(lambda: doc.Application.ZoomWindow(apoint(window[0], window[1]), apoint(window[2], window[3])))
        _write(doc, "MSpace", False)
    else:
        notes["aim_note"] = (
            "AutoCAD would not let model space be entered through the new viewport, so it "
            "is at the scale asked but may not be centred. Check it with autocad_preview."
        )

    # StandardScale has to say "custom" before CustomScale is read at all.
    if _write(viewport, "StandardScale", AC_VP_CUSTOM_SCALE):
        _write(viewport, "CustomScale", float(ratio))
    notes["scale_set"] = round(float(_read(viewport, "CustomScale", ratio) or ratio), 9)

    if locked and not _write(viewport, "DisplayLocked", True):
        notes["lock_note"] = (
            "AutoCAD would not lock the viewport. Lock it from its properties, or the next "
            "zoom inside it will change the scale."
        )
    _try(lambda: doc.Regen(AC_ALL_VIEWPORTS))
    return notes
