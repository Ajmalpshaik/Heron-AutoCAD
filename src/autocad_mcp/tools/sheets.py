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
from ..core.bridge import OLD_PLUGIN
from ..core.connection import get_doc, require_idle, run
from ..core.errors import (
    AutocadError,
    OutcomeUnknown,
    com_message,
    is_retryable,
    raise_if_busy,
)
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint
from ._shared import COORDS_OPT, current_ucs, in_plugin, ucs_for, world_coords

# The media-name matching is already proven and tested in document.py (the PDF
# export path); a sheet picks its paper the same way rather than a second way.
from .document import _MEDIA_NAME, _match_media, _normalize_media, layout_on_screen  # noqa: PLC2701

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


def _try(getter, default=None, busy_ok=False):
    """Read one COM property, tolerating a layout that does not carry it.

    busy_ok for a restore or a redraw, where a busy refusal must not hide the answer (D-100).
    """
    try:
        return getter()
    except BaseException as exc:  # noqa: BLE001 - absent properties are expected here
        if not busy_ok:
            raise_if_busy(exc)
        return default


def _read(target: Any, name: str, default: Any = None) -> Any:
    """Read one COM property by name, with a default when the type lacks it."""
    try:
        return getattr(target, name)
    except BaseException as exc:  # noqa: BLE001 - absent properties are expected here
        raise_if_busy(exc)
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
    except BaseException as exc:  # noqa: BLE001 - a refusal is the answer, not a crash
        raise_if_busy(exc)
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
        # The tab on screen (CTAB), which COM's ActiveLayout did not always follow (D-125).
        layout = layout_on_screen(doc)
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
    plotter = str(_try(lambda: layout.ConfigName, "") or "")

    size = _try(lambda: tuple(float(v) for v in layout.GetPaperSize()))
    if not size or len(size) < 2 or min(size[:2]) <= 0:
        size = plan.media_dimensions(media)
    if not size:
        raise AutocadError(
            f"Layout '{_try(lambda: layout.Name, '?')}' has no usable paper size. Set one "
            "with autocad_page_setup (paper_size='A3') before placing anything on it."
        )

    margins = _try(lambda: layout.GetPaperMargins())
    low, high = (0.0, 0.0), (0.0, 0.0)
    if margins and len(margins) == 2:
        low = tuple(float(v) for v in margins[0])[:2]
        high = tuple(float(v) for v in margins[1])[:2]
    rotation = int(_try(lambda: layout.PlotRotation, 0) or 0)
    degrees = next((deg for deg, code in PLOT_ROTATIONS.items() if code == rotation), 0)
    # Not swapped for a turned plot, unlike the plug-in's read (SheetMath.PaperInUnits): on
    # 2026-11-22 a sheet at 90 degrees on the 841 x 594 medium was 841 x 594 on screen, as
    # this read said. Which rule AutoCAD follows is row AF21 (D-125); new sheets are not turned.
    return plan.paper_info(size, (low[0], low[1], high[0], high[1]), media, plotter, degrees)


def _paper_from_plugin(paper: dict[str, Any]) -> dict[str, Any]:
    """The same facts from the plug-in's answer (Sheets.WritePaper in the add-in)."""
    size = paper.get("size") or ()
    media = str(paper.get("media") or "")
    if not size or len(size) < 2 or min(float(v) for v in size[:2]) <= 0:
        size = plan.media_dimensions(media) or ()
    if not size:
        raise AutocadError("Heron in AutoCAD made the sheet but reported no paper size for it.")
    info = plan.paper_info(
        size, paper.get("margins") or (0.0, 0.0, 0.0, 0.0), media,
        str(paper.get("plotter") or ""), int(paper.get("plot_rotation_degrees") or 0),
    )  # fmt: skip
    if paper.get("paper_units"):
        info["paper_units"] = str(paper["paper_units"])
    return info


def _area_box(info: dict[str, Any], anchor: str) -> plan.Box:
    """The rectangle to work inside: the printable area, or the whole sheet."""
    return plan.area_box(info, anchor)


def _sheet_of(info: dict[str, Any], margins: Any, title_block_width: float | None) -> dict[str, Any]:
    """A sheet's arithmetic for the answer: frame, drawing space, where the title block goes."""
    width, height = info["paper"]
    sheet: dict[str, Any] = {
        "paper": [width, height],
        "orientation": "portrait" if height > width else "landscape",
    }
    try:
        outline = plan.frame_in(_area_box(info, "printable"), margins)
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
    if int(info.get("plot_rotation_degrees") or 0) % 180 == 90:
        sheet["plot_turned_note"] = (
            "This sheet plots turned 90 degrees (Page Setup > Drawing orientation). Check which way "
            "round its paper is in Page Setup before making a PDF."
        )
    return sheet


def _orientation_check(sheet: dict[str, Any], asked: str | None) -> str | None:
    """A warning when the sheet does not come out the way round that was asked (D-125)."""
    key = str(asked or "").strip().lower()
    got = sheet.get("orientation")
    width, height = (sheet.get("paper") or [0, 0])[:2]
    if key not in ("portrait", "landscape") or width == height or got == key:
        return None
    return (
        f"The sheet was asked for {key} but reads {got} ({width:g} x {height:g}). Check Page "
        "Setup's drawing orientation, then set it with autocad_page_setup(orientation=...)."
    )


# What the plug-in answers when it cannot do an operation at all: no plug-in
# in this job (--no-bridge), one too old to do runs, or one without this
# operation. Then the work is done over COM, as before (D-90). Anything else -
# a refusal, a padlock, HERONSTOP, "Outcome unknown" - is the answer.
_NO_PLUGIN = ("--no-bridge", "does not have the operation")


def by_plugin(operation: str, args: dict[str, Any], what: str) -> tuple[dict[str, Any] | None, str | None]:
    """(the plug-in's answer, None), or (None, why it could not be asked) when COM must do it."""
    try:
        return in_plugin(operation, args, what), None
    except AutocadError as exc:
        text = str(exc)
        if text == OLD_PLUGIN or any(marker in text for marker in _NO_PLUGIN):
            return None, text
        raise


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------


def _size_label(media: str) -> str:
    """The size words of a canonical media name: 'iso full bleed a1' for ISO_full_bleed_A1_(841.00_x_594.00_MM)."""
    match = _MEDIA_NAME.match(_normalize_media(media)) if media else None
    return str(match["label"]).strip() if match else ""


def _same_label(names: tuple[str, ...], label: str, orientation: str) -> str | None:
    """The medium with exactly this size label, the way round asked: the sheet turned, its variant kept."""
    for name in names:
        match = _MEDIA_NAME.match(_normalize_media(name))
        if not match or str(match["label"]).strip() != label:
            continue
        width, height = float(match["w"]), float(match["h"])
        if width == height or (width < height) == (orientation == "portrait"):
            return name
    return None


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
                raise_if_busy(exc)
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

    key = str(orientation or "").strip().lower()
    if key and key not in ("portrait", "landscape"):
        raise AutocadError("orientation must be 'portrait' or 'landscape'.")
    size_words = str(paper_size or "").strip()
    if key and not size_words:
        # Orientation alone (D-125): the same sheet size the other way round. It
        # used to be ignored with "needs a paper_size", and the answer then read
        # back the old sheet as if nothing was wrong.
        size_words = _size_label(str(_try(lambda: layout.CanonicalMediaName, "") or ""))
        if not size_words:
            written["orientation_ignored"] = (
                f"'{key}' needs a paper_size with it: this sheet's size could not be read from "
                "its media name. Pass paper_size as well."
            )
            key = ""

    if size_words:
        names = tuple(_try(lambda: layout.GetCanonicalMediaNames(), ()) or ())
        if not names:
            raise AutocadError(
                "AutoCAD reported no sheet sizes for this layout's plotter. Set the plotter "
                f"first (plotter='{PDF_PLOTTER}')."
            )
        wanted = size_words
        if key and not any(w in wanted.lower() for w in ("portrait", "landscape")):
            wanted = f"{wanted} {key}"
        media = (_same_label(names, size_words, key) if not paper_size else None) or _match_media(names, wanted)
        layout.CanonicalMediaName = media
        written["paper_size"] = str(_try(lambda: layout.GetLocaleMediaName(media), wanted))
    if size_words and key:
        written["orientation"] = key
        # The medium is matched the right way round, so the plot is not turned
        # whatever the layout had before; only a medium offered the other way
        # round only is turned (plan.plot_turned, D-125). The 2026-11-22 sheets
        # kept a template's 90 degrees on an 841 x 594 sheet. Written only when
        # an orientation is asked: only the options passed are written.
        turned = plan.plot_turned(media, key)
        if _write(layout, "PlotRotation", PLOT_ROTATIONS[90 if turned else 0]):
            written["plot_rotation"] = 90 if turned else 0
        else:
            written["plot_rotation_note"] = (
                "AutoCAD would not set the drawing orientation; check Page Setup before making a PDF."
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
            raise_if_busy(exc)
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
        Field(default=None, description="Copy an existing layout as the template, title block and all, instead of starting empty. (With a Heron plug-in older than this, over COM, only its page setup is copied.)"),
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
        _free_name(doc, clean)
        if copy_from:
            _pick_layout(doc, copy_from)
        with undo_mark(doc):
            return make_layout(
                doc, clean, paper_size=paper_size, orientation=orientation, plotter=plotter,
                plot_style_table=plot_style_table, copy_from=copy_from, margins=margins,
                title_block_width=title_block_width, activate=activate,
            )  # fmt: skip

    return dumps(await run(work))


def _free_name(doc: Any, clean: str) -> None:
    """Refuse a sheet name the drawing already has, before anything is made."""
    if any(k.lower() == clean.lower() for k in _layouts(doc)):
        raise AutocadError(
            f"This drawing already has a layout called '{clean}'. Pick another name, "
            "or change that one with autocad_page_setup."
        )


def make_layout(
    doc: Any,
    clean: str,
    *,
    paper_size: str | None,
    orientation: str | None,
    plotter: str | None,
    plot_style_table: str | None,
    copy_from: str | None,
    margins: Any,
    title_block_width: float | None,
    activate: bool,
) -> dict[str, Any]:
    """One new sheet, by the plug-in when it can (#64, D-90), else over COM.

    On the worker thread, inside the caller's undo mark: autocad_sheet_set
    makes many sheets in one undo step, so this opens none of its own.
    """
    report, why_not = by_plugin(
        "create_layout",
        {
            "name": clean, "copy_from": copy_from, "plotter": plotter, "paper_size": paper_size,
            "orientation": orientation if paper_size else None,
            "plot_style_table": plot_style_table, "activate": bool(activate),
        },
        "Making the sheet",
    )  # fmt: skip
    if report is not None:
        made = str(report.get("layout") or clean)
        page = dict(report.get("page_setup") or {})
        result: dict[str, Any] = {
            "created": True,
            "layout": made,
            "tab_order": int(report.get("tab_order") or 0),
            "page_setup": page,
            "made_by": "plugin",
        }
        # The sheet is made: from here nothing raises, or a retry would only
        # be told the name is taken. A paper the answer lacks is read over COM.
        try:
            info = _paper_from_plugin(report.get("paper") or {})
        except AutocadError:
            info = _try(lambda: _paper_of(_pick_layout(doc, made)))
        if info and paper_size:
            info = _plot_not_turned(doc, made, info, orientation, page)
        if info:
            result["paper"] = info
            result["sheet"] = _sheet_of(info, margins, title_block_width)
        else:
            result["warning"] = (
                f"The sheet '{made}' is made, but its paper size could not be read back, so the "
                "frame is not worked out. Check it with autocad_list_layouts."
            )
        if report.get("copied_from"):
            result["copied_from"] = report["copied_from"]
        if activate:
            result["activated"] = bool(report.get("activated", True))
        return _say_orientation(result, orientation if paper_size else None)

    # Orientation goes with a paper size only: without one the template's sheet is kept,
    # and orientation alone would turn it (autocad_page_setup's orientation-only rule).
    result = _make_layout_com(
        doc, clean, paper_size, orientation if paper_size else None, plotter, plot_style_table,
        copy_from, margins, title_block_width, activate,
    )  # fmt: skip
    result["made_by"] = "com"
    result["plugin_note"] = why_not
    return _say_orientation(result, orientation if paper_size else None)


def _say_orientation(result: dict[str, Any], asked: str | None) -> dict[str, Any]:
    """Add a warning when the sheet reads the other way round from what was asked (D-125)."""
    sheet = result.get("sheet")
    warning = _orientation_check(sheet, asked) if isinstance(sheet, dict) else None
    if warning:
        result["warning"] = f"{result['warning']} {warning}" if result.get("warning") else warning
    return result


def _plot_not_turned(
    doc: Any, made: str, info: dict[str, Any], orientation: str | None, page: dict[str, Any]
) -> dict[str, Any]:
    """Put a new sheet's plot the right way round when the plug-in left a template's turn on it.

    Plug-in 1.8.0 never set the drawing orientation, so a new layout kept the
    template's 90 degrees on the landscape medium it had just picked, and its
    paper read back upright (594 x 841) on 2026-11-22 (D-125). A newer plug-in
    sets it itself and this does nothing. Never raises: the sheet is made.
    """
    turned = plan.plot_turned(str(info.get("media") or ""), orientation)
    now = int(info.get("plot_rotation_degrees") or 0)
    if (now % 180 == 90) == turned:
        return info
    wanted = 90 if turned else 0
    try:
        layout = _pick_layout(doc, made)
        done = _write(layout, "PlotRotation", PLOT_ROTATIONS[wanted])
    except BaseException:  # noqa: BLE001 - busy (#40) or gone: the sheet is made, so it is said, never raised
        done = False
    if not done:
        page["plot_rotation_note"] = (
            f"The sheet plots turned {now} degrees and AutoCAD would not change that just now. "
            "Set it with autocad_page_setup(orientation=...) or Page Setup's drawing orientation."
        )
        return info
    page["plot_rotation"] = wanted
    page["plot_rotation_was"] = now
    try:
        return _paper_of(layout)
    except BaseException:  # noqa: BLE001 - the turn is written; a busy read-back keeps the plug-in's answer
        return info


BUSY_READBACK_TRIES = 10
BUSY_READBACK_DELAY = 0.3


def _make_layout_com(
    doc: Any,
    clean: str,
    paper_size: str | None,
    orientation: str | None,
    plotter: str | None,
    plot_style_table: str | None,
    copy_from: str | None,
    margins: Any,
    title_block_width: float | None,
    activate: bool,
) -> dict[str, Any]:
    """The sheet over COM, for a plug-in that cannot (older, or --no-bridge).

    AutoCAD can go busy once the layout is added, while the plotter loads
    (#40, row D8): that answer is now a clear one, from the drawing read back,
    instead of "Outcome unknown".
    """
    if copy_from:
        source = _pick_layout(doc, copy_from)
        try:
            layout = doc.Layouts.Add(clean)
            layout.CopyFrom(source)
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            raise AutocadError(
                f"Could not copy layout '{copy_from}' ({com_message(exc)}). Make the "
                "sheet without copy_from, or copy its contents with "
                "autocad_manage_layouts(copy_handles=...)."
            ) from exc
    else:
        try:
            layout = doc.Layouts.Add(clean)
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
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
        if is_retryable(exc):
            return _made_but_busy(doc, clean, "while its page setup was being written", margins, title_block_width)
        # Never leave a half-made sheet: the retry would only be told
        # the name is taken (2026-11-05).
        kept = not _write_delete(layout)
        if isinstance(exc, AutocadError) and not kept:
            raise AutocadError(
                f"{exc} The layout '{clean}' was not kept, so the call can be "
                "repeated as it is."
            ) from exc
        raise

    notes: dict[str, Any] = {}
    if activate:
        try:
            _activate(doc, layout)
        except BaseException as exc:
            if not is_retryable(exc):
                raise
            notes["activate_note"] = (
                f"AutoCAD went busy as '{clean}' was put on screen, so it may not be the tab "
                "showing. The sheet itself is made and set up; click its tab."
            )
    try:
        info = _paper_of(layout)
        tab_order = int(_try(lambda: layout.TabOrder, 0) or 0)
    except BaseException as exc:
        if not is_retryable(exc):
            raise
        return _made_but_busy(doc, clean, "as the new sheet was read back", margins, title_block_width, page)

    result: dict[str, Any] = {
        "created": True,
        "layout": str(_try(lambda: layout.Name, clean) or clean),
        "tab_order": tab_order,
        "page_setup": page,
        "paper": info,
        "sheet": _sheet_of(info, margins, title_block_width),
    }
    result.update(notes)
    return result


def _made_but_busy(
    doc: Any,
    clean: str,
    when: str,
    margins: Any,
    title_block_width: float | None,
    page: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The answer when AutoCAD went busy after the layout was added (#40).

    The layout is looked for again for a moment. Found, the answer says the
    sheet is made and what may not be set; not found, it is "Outcome unknown"
    in words that say exactly what to look at.
    """
    for _ in range(BUSY_READBACK_TRIES):
        try:
            found = next((v for k, v in _layouts(doc).items() if k.lower() == clean.lower()), None)
        except BaseException:  # noqa: BLE001 - still busy; look again
            time.sleep(BUSY_READBACK_DELAY)
            continue
        if found is None:
            break
        result: dict[str, Any] = {
            "created": True,
            "layout": clean,
            "page_setup": page or {},
            "warning": (
                f"The sheet '{clean}' is made, but AutoCAD went busy {when}, so its page setup "
                "may not all be written. Check it, and set what is missing with "
                f"autocad_page_setup(layouts=['{clean}'], ...). Do not make the sheet again."
            ),
        }
        try:
            info = _paper_of(found)
            result["paper"] = info
            result["sheet"] = _sheet_of(info, margins, title_block_width)
        except BaseException:  # noqa: BLE001 - the warning already says to check it
            pass
        return result
    raise OutcomeUnknown(
        f"Outcome unknown: AutoCAD went busy {when}, right after the sheet '{clean}' was added, "
        "and could not be read back. Look at the layout tabs before trying again: if "
        f"'{clean}' is there, finish it with autocad_page_setup(layouts=['{clean}'], ...) "
        "rather than making it again."
    )


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
        block_name = title_block_source(doc, name, source)

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
                wanted = {k.strip().upper(): v for k, v in (attributes or {}).items()}
                for sheet_name, extra in (per_layout_attributes or {}).items():
                    if sheet_name.strip().lower() == label.lower():
                        wanted.update({k.strip().upper(): v for k, v in extra.items()})
                placed.append(
                    put_title_block(
                        layout, block_name, name, corner=corner, anchor=anchor, margins=margins,
                        nudge=nudge, scale=scale, rotation=rotation, values=wanted, layer=layer,
                        replace_existing=replace_existing,
                    )  # fmt: skip
                )
        return {"block": block_name, "count": len(placed), "placed": placed}

    return dumps(await run(work))


def title_block_source(doc: Any, name: str, source: str | None) -> str:
    """The block to insert: a .dwg path as given, or a block the drawing has (else the ones it has)."""
    if source is not None:
        return source
    try:
        doc.Blocks.Item(name)
    except BaseException as exc:  # noqa: BLE001 - say what the drawing does have
        raise_if_busy(exc)
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
    return name


def put_title_block(
    layout: Any,
    block_name: str,
    shown_as: str,
    *,
    corner: str,
    anchor: str,
    margins: Any,
    nudge: tuple[float, float],
    scale: float,
    rotation: float,
    values: dict[str, str],
    layer: str | None,
    replace_existing: bool,
    info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One title block on one sheet, filled in. No undo mark of its own.

    It goes into the layout's own block, not ``doc.PaperSpace``: that threw a
    bare Automation error on a sheet made with Layouts.Add (known limit 23,
    #39), and the layout's block answered. So the sheet need not be the one
    on screen, and none is switched to.
    """
    label = str(layout.Name)
    info = info or _paper_of(layout)
    try:
        outline = plan.frame_in(_area_box(info, anchor), margins)
        at = plan.corner_point(outline, corner)
    except ValueError as exc:
        raise AutocadError(f"Sheet '{label}': {exc}") from exc
    at = (at[0] + nudge[0], at[1] + nudge[1])

    space = layout.Block
    removed = 0
    if replace_existing:
        for existing in list(_references(space, block_name)):
            try:
                existing.Delete()
                removed += 1
            except BaseException as exc:  # noqa: BLE001 - a locked layer, reported by count
                raise_if_busy(exc)

    try:
        reference = space.InsertBlock(
            apoint(at[0], at[1], 0.0), block_name,
            float(scale), float(scale), float(scale), rad(rotation),
        )  # fmt: skip
    except BaseException as exc:  # noqa: BLE001
        raise_if_busy(exc)
        raise AutocadError(
            f"Sheet '{label}': AutoCAD would not insert '{shown_as}' ({com_message(exc)})."
        ) from exc
    if layer:
        reference.Layer = layer.strip()

    applied, missing = _fill_attributes(reference, values)
    return {
        "layout": label,
        "handle": str(reference.Handle),
        "block": str(_read(reference, "EffectiveName", "") or _read(reference, "Name", "") or shown_as),
        "at": [round(at[0], 4), round(at[1], 4)],
        "frame": [round(v, 4) for v in outline],
        "attributes_set": applied,
        "attributes_not_found": missing,
        "replaced": removed,
    }


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
        Field(default=None, description="Turn the view inside the viewport, in degrees anticlockwise on the sheet (AutoCAD's view twist). A wing drawn at 23 degrees reads square with twist=-23 (or 337); align_to_ucs works it out from the UCS."),
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
    clip_outline: Annotated[
        list[list[float]] | None,
        Field(default=None, description="Clip the viewport to this outline instead of a rectangle: its corners on the paper, [[x, y], ...], at least three, not crossing itself. The viewport is made the size of the box round it, and the outline is drawn on the viewport's layer. Done by Heron's plug-in."),
    ] = None,
    clip_handle: Annotated[
        str | None,
        Field(default=None, description="Clip the viewport to a closed polyline, circle, ellipse, spline or region already drawn on that sheet, by handle (what VPCLIP does). Done by Heron's plug-in."),
    ] = None,
    annotation_scale: Annotated[
        str | None,
        Field(default="match", description="The viewport's annotation scale, so annotative text and dimensions inside it show at the right size: 'match' (the default) uses the viewport's own scale, adding it to the drawing's scale list if missing; a scale name such as '1:50' uses that one; 'none' leaves AutoCAD's choice."),
    ] = "match",
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
        clip_outline (Optional[list[list[float]]]): clip to these paper corners.
        clip_handle (Optional[str]): clip to this closed shape on the sheet.
        annotation_scale (Optional[str]): 'match', a scale name, or 'none'.

    Returns:
        str: JSON: {
          "created": true, "handle": str, "layout": str,
          "scale": "1:50", "scale_ratio": float, "fitted": bool,
          "paper_rect": [x1, y1, x2, y2], "model_window": [x1, y1, x2, y2],
          "looking_at": [x, y], "twist_degrees": float, "locked": bool,
          "clipped": bool, "annotation_scale": str, "made_by": "plugin" | "com"
        }

    Examples:
        - Use when: "put the ground floor on this A1 at 1:100".
        - Use when: "same area I just plotted" — autocad_save_view first, then
          view_name here.
        - Use when: the plan is on a 23 degree grid — align_to_ucs=true.
        - Use when: "clip the viewport to this L-shaped polyline" — clip_handle,
          or clip_outline with the corners.
        - Use when: annotative text must show at the viewport's scale — the
          default annotation_scale='match' does it.
        - Don't use when: you want the whole sheet plotted (autocad_export).
        - Don't use when: making a whole drawing list of sheets — autocad_sheet_set.

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
        with undo_mark(doc):
            return make_viewport(
                doc, sheet, scale=scale, centre=centre, corner1=corner1, corner2=corner2,
                view_name=view_name, handles=handles, paper_centre=paper_centre,
                paper_width=paper_width, paper_height=paper_height, margins=margins,
                title_block_width=title_block_width, gap=gap, twist=twist,
                align_to_ucs=align_to_ucs, locked=locked, layer=layer, aci=aci, coords=coords,
                clip_outline=clip_outline, clip_handle=clip_handle,
                annotation_scale=annotation_scale,
            )  # fmt: skip

    return dumps(await run(work))


def _annotation_name(annotation_scale: str | None, scale_name: str) -> str | None:
    """The annotation scale to give a viewport: its own for 'match', none for 'none'."""
    text = str(annotation_scale or "").strip()
    if not text or text.lower() in ("none", "off", "no"):
        return None
    if text.lower() in ("match", "same", "viewport"):
        return scale_name
    return text


def make_viewport(
    doc: Any,
    sheet: Any,
    *,
    scale: str | float | None = None,
    centre: list[float] | None = None,
    corner1: list[float] | None = None,
    corner2: list[float] | None = None,
    view_name: str | None = None,
    handles: list[str] | None = None,
    paper_centre: list[float] | None = None,
    paper_width: float | None = None,
    paper_height: float | None = None,
    margins: Any = None,
    title_block_width: float | None = None,
    gap: float = 0.0,
    twist: float | None = None,
    align_to_ucs: bool = False,
    locked: bool = True,
    layer: str | None = None,
    aci: int | None = None,
    coords: str = "world",
    clip_outline: list[list[float]] | None = None,
    clip_handle: str | None = None,
    annotation_scale: str | None = "match",
    info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One viewport on one sheet, by the plug-in when it can (#64, #65, D-90), else over COM.

    Everything is worked out here first, from reads only: where on the paper,
    where it looks, the twist, the scale. Then one write. No undo mark of its
    own (autocad_sheet_set holds one round many sheets).
    """
    info = info or _paper_of(sheet)
    ucs = ucs_for(doc, coords)
    sheet_name = str(sheet.Name)

    if clip_outline and clip_handle:
        raise AutocadError("Clip to clip_outline or to clip_handle, not both.")
    outline = None
    if clip_outline:
        try:
            outline = plan.clip_outline(clip_outline)
        except ValueError as exc:
            raise AutocadError(f"The clip outline will not do: {exc}.") from exc
    clip_box = None
    if outline is not None:
        clip_box = tuple(outline["box"])
    elif clip_handle:
        shape = resolve_handles(doc, [clip_handle])[0]
        found = bounding_box(shape)
        if not found:
            raise AutocadError(f"{clip_handle} reports no extents, so a viewport cannot be clipped to it.")
        clip_box = (found["min"][0], found["min"][1], found["max"][0], found["max"][1])
    if clip_box is not None and (paper_centre or paper_width or paper_height):
        raise AutocadError(
            "A clipped viewport takes its place on the paper from the clip outline. Leave out "
            "paper_centre, paper_width and paper_height."
        )

    # 1. Where on the paper.
    if clip_box is not None:
        paper_rect = clip_box
        cx, cy = plan.centre_of(paper_rect)
        pw, ph = plan.size_of(paper_rect)
        if pw <= 0 or ph <= 0:
            raise AutocadError("The clip outline has no width or no height on the paper.")
    elif paper_centre and paper_width and paper_height:
        if len(paper_centre) < 2:
            raise AutocadError("paper_centre needs [x, y] in paper units.")
        cx, cy = float(paper_centre[0]), float(paper_centre[1])
        pw, ph = float(paper_width), float(paper_height)
        paper_rect = (cx - pw / 2.0, cy - ph / 2.0, cx + pw / 2.0, cy + ph / 2.0)
    else:
        try:
            outline_box = plan.frame_in(_area_box(info, "printable"), margins)
            if title_block_width:
                outline_box = plan.reserve(outline_box, "right", float(title_block_width))
            paper_rect = plan.inset(outline_box, gap) if gap else outline_box
        except ValueError as exc:
            raise AutocadError(
                f"The viewport could not be fitted to sheet '{sheet_name}': {exc}. Give "
                "paper_centre, paper_width and paper_height instead."
            ) from exc
        cx, cy = plan.centre_of(paper_rect)
        pw, ph = plan.size_of(paper_rect)

    # 2. Where to look, in world coordinates.
    model_box, look_at = _target_area(doc, centre, corner1, corner2, view_name, handles, ucs)

    # 3. The twist, and the area a twisted view has to cover. A viewport's
    #    twist is its view twist (VIEWTWIST): the picture turns anticlockwise
    #    by it on the sheet (display = world turned by +twist, the rule of the
    #    view centre too, SheetMath.ViewCentre). So a plan drawn on a grid
    #    turned 23 degrees reads square at a twist of -23 (337), which is what
    #    PLAN leaves on such a UCS. An explicit twist wins over align_to_ucs.
    if twist is not None:
        angle = float(twist)
    elif align_to_ucs:
        angle = -current_ucs(doc).rotation_degrees
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
    annotation = _annotation_name(annotation_scale, text)

    result: dict[str, Any] = {
        "created": True,
        "layout": sheet_name,
        "scale": text,
        "scale_ratio": round(ratio, 9),
        "fitted": fitted,
        "paper_rect": [round(v, 4) for v in paper_rect],
        "model_window": [round(v, 4) for v in window],
        "looking_at": [round(look_at[0], 4), round(look_at[1], 4)],
        "twist_degrees": round(angle % 360.0, 6),
        "locked": bool(locked),
    }

    report, why_not = _viewport_by_plugin(
        {
            "layout": sheet_name, "paper_centre": [cx, cy], "paper_width": pw, "paper_height": ph,
            "look_at": [look_at[0], look_at[1]], "twist": angle % 360.0, "scale_ratio": ratio,
            "locked": bool(locked), "layer": layer.strip() if layer else None, "color": aci,
            "clip_outline": [v for corner in outline["points"] for v in corner] if outline else None,
            "clip_handle": clip_handle.strip() if clip_handle else None,
            "annotation_scale": annotation,
        },
    )  # fmt: skip
    if report is not None:
        result["handle"] = str(report.get("handle", ""))
        result["layer"] = str(report.get("layer", ""))
        result["scale_set"] = report.get("scale_set", round(ratio, 9))
        result["clipped"] = bool(report.get("clipped", False))
        for key in ("clip_handle", "annotation_scale", "annotation_scale_added", "annotation_scale_note"):
            if key in report:
                result[key] = report[key]
        result["made_by"] = "plugin"
        if not result["handle"]:
            result["warning"] = (
                "Heron in AutoCAD made the viewport but gave no handle back. Look at the sheet "
                "before making it again."
            )
        return result

    if clip_box is not None:
        raise AutocadError(
            "Clipping a viewport to an outline is done by Heron's plug-in in AutoCAD, and it "
            f"could not be asked ({why_not}) Nothing was made: leave the clip out for a "
            "rectangular viewport, or update and connect Heron."
        )
    if layer:
        ensure_layer(doc, layer)
    _activate(doc, sheet)
    viewport = _new_viewport(doc, sheet_name, cx, cy, pw, ph)
    if layer:
        viewport.Layer = layer.strip()
    if aci is not None:
        viewport.Color = aci
    notes = _aim(doc, viewport, window, angle, ratio, locked, annotation)
    result["handle"] = str(viewport.Handle)
    result["layer"] = str(_try(lambda: viewport.Layer, "") or "")
    result["clipped"] = False
    result.update(notes)
    result["made_by"] = "com"
    result["plugin_note"] = why_not
    return result


# The plug-in's words when AutoCAD threw inside the operation: its transaction
# was aborted, so nothing was made (PluginRunner.Run).
_AUTOCAD_REFUSED = "AutoCAD refused it ("


def _viewport_by_plugin(args: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The plug-in's viewport, or (None, why) when COM must make it.

    Besides an older plug-in, AutoCAD itself refusing the plug-in's viewport
    falls back to COM (D-125): plug-in 1.8.0 set StandardScale to
    CustomScale, which AutoCAD refuses with eInvalidInput, so every viewport
    failed on 2026-11-22 while the COM route (row D16, PASS) still works. The
    plug-in aborted its transaction, so nothing is made twice. A refusal of
    Heron's own (a padlock, a bad layer name, HERONSTOP) stays the answer.
    """
    try:
        return in_plugin("add_viewport", args, "Adding the viewport"), None
    except AutocadError as exc:
        text = str(exc)
        if text == OLD_PLUGIN or any(marker in text for marker in _NO_PLUGIN):
            return None, text
        if text.startswith(_AUTOCAD_REFUSED) and not args.get("clip_outline") and not args.get("clip_handle"):
            return None, f"Heron's plug-in could not make it ({text.split('.')[0].strip()}), so it was made over COM."
        raise


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


MVIEW_POLL_ATTEMPTS = 20
MVIEW_POLL_DELAY = 0.1


def _viewports_in(block: Any) -> list[Any]:
    """The viewports a layout's block holds, in the order AutoCAD keeps them."""
    found = []
    for index in range(int(_try(lambda: block.Count, 0) or 0)):
        item = _try(lambda index=index: block.Item(index))
        if item is not None and str(_try(lambda item=item: item.ObjectName, "")) == "AcDbViewport":
            found.append(item)
    return found


def mview_command(cx: float, cy: float, pw: float, ph: float) -> str:
    """MVIEW typed with two corners: the same viewport AddPViewport would make.

    Each space is one Enter. There is none after the second corner's own, or the
    empty prompt would repeat MVIEW.
    """
    x1, y1, x2, y2 = cx - pw / 2.0, cy - ph / 2.0, cx + pw / 2.0, cy + ph / 2.0
    return f"_.MVIEW {x1:.4f},{y1:.4f} {x2:.4f},{y2:.4f} "


def _new_viewport(doc: Any, sheet_name: str, cx: float, cy: float, pw: float, ph: float) -> Any:
    """Add a viewport to the active sheet, through MVIEW when AddPViewport will not.

    ``doc.PaperSpace`` can throw a bare Automation error on a sheet AutoCAD has
    half set up (Luxury Suite 2, 2026-11-09), and with it AddPViewport. MVIEW
    typed with two corners still worked on that sheet, so it is the fallback;
    the new viewport is found as the one the layout's block did not hold before.
    """
    try:
        return doc.PaperSpace.AddPViewport(apoint(cx, cy, 0.0), pw, ph)
    except BaseException as first:  # noqa: BLE001 - MVIEW is tried next
        raise_if_busy(first)
        refusal = com_message(first)

    block = _try(lambda: doc.ActiveLayout.Block)
    if block is None:
        raise AutocadError(
            f"AutoCAD would not add a viewport to '{sheet_name}' ({refusal}). "
            "Check the sheet is a layout and not model space."
        )
    before = {str(_try(lambda v=v: v.Handle, "")) for v in _viewports_in(block)}
    osmode = _try(lambda: doc.GetVariable("OSMODE"))
    _try(lambda: doc.SetVariable("OSMODE", 0))
    try:
        doc.SendCommand(mview_command(cx, cy, pw, ph))
    except BaseException as exc:  # noqa: BLE001
        raise_if_busy(exc)
        raise AutocadError(
            f"AutoCAD would not add a viewport to '{sheet_name}' ({refusal}), and MVIEW was "
            f"refused too ({com_message(exc)}). Press Esc in AutoCAD and try again."
        ) from exc
    finally:
        if osmode is not None:
            _try(lambda: doc.SetVariable("OSMODE", osmode), busy_ok=True)

    for _ in range(MVIEW_POLL_ATTEMPTS):
        fresh = [v for v in _viewports_in(block) if str(_try(lambda v=v: v.Handle, "")) not in before]
        if fresh:
            return fresh[-1]
        time.sleep(MVIEW_POLL_DELAY)
    raise AutocadError(
        f"AutoCAD would not add a viewport to '{sheet_name}' ({refusal}), and MVIEW made "
        "none either. Check the sheet is a layout, not model space, and nothing is "
        "waiting at the command line."
    )


def _aim(
    doc: Any,
    viewport: Any,
    window: plan.Box,
    twist: float,
    ratio: float,
    locked: bool,
    annotation: str | None = None,
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
    _try(lambda: doc.Regen(AC_ALL_VIEWPORTS), busy_ok=True)

    if twist and not _write(viewport, "TwistAngle", rad(twist)):
        notes["twist_note"] = (
            "AutoCAD did not accept the twist angle, so the view is not turned. Turn it "
            "by hand in the viewport, or set the UCS and draw the plan square."
        )

    if _write(doc, "MSpace", True):
        _write(doc, "ActivePViewport", viewport)
        _try(lambda: doc.Application.ZoomWindow(apoint(window[0], window[1]), apoint(window[2], window[3])))
        if annotation:
            # Inside a viewport, CANNOSCALE is that viewport's annotation scale.
            # COM has no other way to it; the scale must be in the drawing's list.
            if _try(lambda: doc.SetVariable("CANNOSCALE", annotation) or True, False):
                notes["annotation_scale"] = annotation
            else:
                notes["annotation_scale_note"] = (
                    f"AutoCAD would not set the viewport's annotation scale to {annotation}: it may "
                    "not be in the drawing's scale list (SCALELISTEDIT). Set it from the status bar."
                )
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
    _try(lambda: doc.Regen(AC_ALL_VIEWPORTS), busy_ok=True)
    return notes
