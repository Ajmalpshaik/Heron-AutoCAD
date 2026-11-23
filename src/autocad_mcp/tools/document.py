"""Session and file tools: connect, list, open, save, export, view, sysvars."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from typing import Annotated, Any, Literal

import pythoncom
import win32com.client
from mcp.server.mcpserver import Image
from pydantic import Field

from ..acad import sheets as sheet_plan
from ..acad.coords import advice as ucs_advice
from ..acad.units import unit_name
from ..core.connection import get_app, get_doc, run, sheet_on_screen
from ..core.errors import AutocadError, com_message, is_retryable, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, double_array, point_to_list
from ._shared import before_after, current_ucs, faster_read, in_plugin, plugin_read

# Formats doc.Export writes directly. PDF goes through the plotter instead.
EXPORT_FORMATS = {"dxf", "wmf", "sat", "bmp", "eps", "stl"}

# PDF plotting: the plotter AutoCAD ships, plus the AcPlotType and
# AcPlotScale values for "plot the extents, fitted to the sheet".
PDF_PLOTTER = "DWG To PDF.pc3"
# DWF goes the same way, through the DWF6 plotter AutoCAD ships (#179, D-111).
DWF_PLOTTER = "DWF6 ePlot.pc3"
# The formats that plot rather than export, and the plotter each one uses.
PLOTTERS = {"pdf": PDF_PLOTTER, "dwf": DWF_PLOTTER}
AC_EXTENTS = 1
AC_SCALE_TO_FIT = 0
# AcPlotRotation: ac0degrees.
AC_0_DEGREES = 0
# Named page setup that holds the layout's own settings while a PDF plots.
SNAPSHOT_NAME = "MCP_EXPORT_RESTORE"

# Media names look like "ISO_full_bleed_A3_(420.00_x_297.00_MM)".
_MEDIA_NAME = re.compile(r"^(?P<label>.*?) ?\((?P<w>[\d.]+) x (?P<h>[\d.]+) \w+\)$")
_ORIENTATIONS = {"portrait", "landscape"}


def _expand(path: str) -> str:
    """Normalize a user-supplied path, stripping the quotes shells leave on."""
    return os.path.expandvars(os.path.expanduser(path.strip().strip('"').strip("'")))


def _mtime(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def _normalize_media(name: str) -> str:
    return re.sub(r"[\s_]+", " ", name).strip().lower()


def _media_sizes(names: list[str] | tuple[str, ...]) -> list[str]:
    """The distinct sheet sizes on offer, e.g. ["ISO A3", "ANSI B"]."""
    sizes = []
    for name in names:
        label = name.split("_(")[0]
        label = label.replace("_full_bleed", "").replace("_expand", "")
        sizes.append(label.replace("_", " "))
    return list(dict.fromkeys(sizes))


def _match_media(names: list[str] | tuple[str, ...], wanted: str, plotter: str = PDF_PLOTTER) -> str:
    """Pick the plotter's canonical media name for a paper size.

    Exact canonical or display names are used as given. Short names such as
    "A3", "ANSI D" or "A1 portrait" match on their size words: the landscape
    sheet unless "portrait" is asked for, and the full-bleed variant first
    because it leaves no unprintable margin round a PDF.
    """
    request = _normalize_media(wanted)
    for name in names:
        if _normalize_media(name) == request:
            return name

    words = set(request.split())
    portrait = "portrait" in words
    words -= _ORIENTATIONS

    ranked = []
    for index, name in enumerate(names):
        match = _MEDIA_NAME.match(_normalize_media(name))
        if match is None:
            continue
        label = match["label"]
        if not words or not words <= set(label.split()):
            continue
        width, height = float(match["w"]), float(match["h"])
        wrong_way = width != height and (width < height) != portrait
        variant = 0 if "full bleed" in label else 2 if "expand" in label else 1
        ranked.append((wrong_way, variant, index, name))

    if not ranked:
        raise AutocadError(
            f"'{wanted}' is not a paper size the {plotter} plotter offers. "
            f"Sizes it has: {', '.join(_media_sizes(names))}. Add 'portrait' "
            "for an upright sheet, or pass an exact name such as "
            "'ISO full bleed A3 (420.00 x 297.00 MM)'."
        )
    return min(ranked)[3]


def set_custom_scale(layout: Any, ratio: float) -> None:
    """Give a layout (or page setup) a custom plot scale, as paper units per drawing unit.

    A layout has no CustomScale property: that is a viewport's. Its scale is set
    with SetCustomScale(paper, drawing), as Autodesk's ActiveX reference says.
    Setting "CustomScale" on a layout is refused by pywin32 as "Property ... can
    not be set", which reads as a busy AutoCAD, so every 1:1 sheet and PDF
    ended in "Outcome unknown" (#40, rows D8 and D20).
    """
    ratio = float(ratio)
    paper, drawing = (ratio, 1.0) if ratio >= 1.0 else (1.0, 1.0 / ratio)
    layout.SetCustomScale(paper, drawing)


def _snapshot_page_setup(doc: Any, layout: Any) -> Any:
    """Copy the layout's page setup into a temporary named page setup."""
    configs = doc.PlotConfigurations
    try:
        configs.Item(SNAPSHOT_NAME).Delete()
    except BaseException as exc:  # noqa: BLE001 - no leftover from an earlier run
        raise_if_busy(exc)
    snapshot = configs.Add(SNAPSHOT_NAME, bool(layout.ModelType))
    snapshot.CopyFrom(layout)
    return snapshot


def _restore_plot_state(
    doc: Any, layout: Any, snapshot: Any, background: Any, quiet: Any
) -> list[str]:
    """Undo what _plot_pdf changed, returning whatever could not be put back.

    Each step runs even if an earlier one fails, and none raises: a failure
    here must neither mask the plot's own error nor turn a written PDF into
    a reported failure.
    """
    steps = (
        ("the plot error mode", lambda: setattr(doc.Plot, "QuietErrorMode", quiet)),
        ("BACKGROUNDPLOT", lambda: doc.SetVariable("BACKGROUNDPLOT", background)),
        ("the layout's page setup", lambda: layout.CopyFrom(snapshot)),
        (f"the temporary '{SNAPSHOT_NAME}' page setup", snapshot.Delete),
    )
    failed = []
    for what, step in steps:
        try:
            step()
        except BaseException as exc:  # noqa: BLE001 - reported to the caller
            failed.append(f"{what} ({com_message(exc)})")
    return failed


# AcPlotType: acDisplay = 0, acExtents = 1, acLimits = 2, acView = 3,
# acWindow = 4, acLayout = 5.
PLOT_AREAS = {"display": 0, "extents": AC_EXTENTS, "limits": 2, "view": 3, "window": 4, "layout": 5}


def _plot_pdf(
    doc: Any,
    target: str,
    paper_size: str | None,
    area: str = "extents",
    window: tuple[Any, Any] | None = None,
    view_name: str | None = None,
    scale: str | float | None = None,
    plotter: str = PDF_PLOTTER,
) -> dict[str, Any]:
    """Plot part of the active layout to a PDF (or a DWF), fitted to the sheet by default.

    PlotToFile(path, "DWG To PDF.pc3") raises a bare "Exception occurred" on
    AutoCAD 2027, so the plotter is chosen on the layout itself and
    PlotToFile gets the path alone. The layout's page setup and the plot
    settings are put back afterwards, so an export never rewrites them.
    """
    layout, resynced = _on_screen_for_plot(doc)
    plot = doc.Plot
    background = doc.GetVariable("BACKGROUNDPLOT")
    quiet = plot.QuietErrorMode
    snapshot = _snapshot_page_setup(doc, layout)
    original_media = str(layout.CanonicalMediaName)
    try:
        try:
            layout.ConfigName = plotter
        except pythoncom.com_error as exc:
            if is_retryable(exc):
                raise
            raise AutocadError(
                f"AutoCAD could not select the '{plotter}' plotter. "
                "Check it is listed in AutoCAD's PLOTTERMANAGER folder. "
                f"(details: {com_message(exc)})"
            ) from exc
        layout.RefreshPlotDeviceInfo()
        names = tuple(layout.GetCanonicalMediaNames())
        if paper_size:
            layout.CanonicalMediaName = _match_media(names, paper_size, plotter)
        elif original_media in names and str(layout.CanonicalMediaName) != original_media:
            # Choosing the plotter drops the sheet to the device default (ANSI A
            # on AutoCAD 2027), even on a layout already set to DWG To PDF A1.
            layout.CanonicalMediaName = original_media
        if area == "window":
            layout.SetWindowToPlot(window[0], window[1])
        if area == "view":
            layout.ViewToPlot = str(view_name).strip()
        layout.PlotType = PLOT_AREAS[area]
        if scale is None:
            layout.UseStandardScale = True
            layout.StandardScale = AC_SCALE_TO_FIT
        else:
            layout.UseStandardScale = False
            set_custom_scale(layout, sheet_plan.parse_typed_scale(scale))
        if area != "layout":
            # A layout plot is the sheet itself: AutoCAD refuses to centre it.
            layout.CenterPlot = True
        paper = str(layout.GetLocaleMediaName(layout.CanonicalMediaName))

        # Foreground, so the file is complete when PlotToFile returns; quiet,
        # so a plot error is logged instead of opening a dialog that would
        # block every later COM call.
        doc.SetVariable("BACKGROUNDPLOT", 0)
        plot.QuietErrorMode = True
        plot.PlotToFile(target)
    finally:
        unrestored = _restore_plot_state(doc, layout, snapshot, background, quiet)

    result = {"layout": str(layout.Name), "paper": paper, "area": area}
    if resynced:
        result["layout_note"] = resynced
    if area == "view":
        result["view"] = str(view_name).strip()
    if scale is not None:
        result["scale"] = sheet_plan.scale_text(sheet_plan.parse_scale(scale))
    if unrestored:
        result["warning"] = (
            "The PDF was plotted, but these could not be put back as they "
            f"were: {'; '.join(unrestored)}. Check them in AutoCAD (PAGESETUP "
            "for the layout, SETVAR for BACKGROUNDPLOT)."
        )
    return result


PNG_PLOTTER = "PublishToWeb PNG.pc3"
# AcPlotType values for the preview areas.
AC_WINDOW = 4
_PREVIEW_AREAS = {"view": 0, "extents": AC_EXTENTS, "window": AC_WINDOW}
_PIXEL_MEDIA = re.compile(r"\(([\d.]+)_x_([\d.]+)_Pixels\)")
# AcRegenType: acAllViewports, as autocad_get_extents regenerates.
AC_ALL_VIEWPORTS = 1
# A letter needs about this many pixels of height to read; smaller turns to specks.
CLEAR_TEXT_PX = 8
# Each close-up reaches this share of its size into its neighbours, so a
# part on a seam shows whole in one of them.
DETAIL_OVERLAP = 0.05
_DETAIL_ROWS = {2: ("top", "bottom"), 3: ("top", "middle", "bottom")}
_DETAIL_COLUMNS = {2: ("left", "right"), 3: ("left", "centre", "right")}


def _point2d(value: Sequence[float], name: str) -> Any:
    if len(value) < 2:
        raise AutocadError(f"{name} needs [x, y], got {list(value)}.")
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, (float(value[0]), float(value[1]))
    )


Box = tuple[list[float], list[float]]


def _box(corner1: Sequence[float], corner2: Sequence[float]) -> Box | None:
    """The lower-left and upper-right of two corners, or None if it has no area."""
    low = [min(float(corner1[0]), float(corner2[0])), min(float(corner1[1]), float(corner2[1]))]
    high = [max(float(corner1[0]), float(corner2[0])), max(float(corner1[1]), float(corner2[1]))]
    if not all(abs(v) < 1e15 for v in low + high) or high[0] <= low[0] or high[1] <= low[1]:
        return None
    return low, high


def _plan_view(doc: Any) -> bool:
    """True when the screen looks straight down in the world UCS, untwisted."""
    try:
        view = point_to_list(doc.GetVariable("VIEWDIR"))
        return (
            int(doc.GetVariable("WORLDUCS")) == 1
            and abs(float(doc.GetVariable("VIEWTWIST"))) < 1e-9
            and len(view) == 3
            and abs(view[0]) < 1e-9
            and abs(view[1]) < 1e-9
            and view[2] > 0
        )
    except BaseException as exc:  # noqa: BLE001 - not known to be plan
        raise_if_busy(exc)
        return False


# How far in an edge of the plug-in's model-space box must lie from EXTMIN/EXTMAX, as a
# share of the bigger side, before EXTMIN/EXTMAX are taken to be stale (#269, D-148).
STALE_SHARE = 0.01


def _measured_model_box() -> Box | None:
    """Model space's own extents, measured object by object by the plug-in (#269, D-148), or None.

    None, so EXTMIN/EXTMAX are used as before, when the plug-in is not in this
    job, is older than its space filter (DXF 410), or found nothing with extents.
    """
    measured = faster_read("entity_extents", {"filter": [[410, "Model"]]})
    if not measured:
        return None
    low, high = measured.get("min"), measured.get("max")
    if not isinstance(low, (list, tuple)) or not isinstance(high, (list, tuple)) or len(low) < 2 or len(high) < 2:
        return None
    try:
        return _box(low, high)
    except (TypeError, ValueError):
        return None


def _shrunk_inside(fresh: Box, old: Box) -> bool:
    """True when ``fresh`` lies inside ``old`` and at least one of its edges is well in from it."""
    size = max(old[1][0] - old[0][0], old[1][1] - old[0][1])
    slack = size * 1e-9
    inside = all(fresh[0][i] >= old[0][i] - slack and fresh[1][i] <= old[1][i] + slack for i in (0, 1))
    moved = max(max(fresh[0][i] - old[0][i], old[1][i] - fresh[1][i]) for i in (0, 1))
    return inside and moved > size * STALE_SHARE


def _extents_box(doc: Any, layout: Any) -> tuple[Box | None, str | None, str | None]:
    """The area an extents preview covers, or None and the reason it cannot be told; and a note.

    Regenerates first, as autocad_get_extents does. A paper layout plots its
    own extents. In model space the box is a plan box, so it maps onto the
    picture only in a plan view of the world UCS.

    EXTMIN/EXTMAX shrink only on ZOOM Extents or All, not on a regen, so after
    an erase they can still reach where the erased object was (#41, #269). In
    model space the plug-in measures the objects themselves (DXF 410 "Model");
    when its box lies well inside EXTMIN/EXTMAX, that box is the one, and the
    note (third value) says so: the picture is then a window over it. A plug-in
    box that is bigger (an object on a frozen layer, which a plot leaves out)
    is not used. No plug-in, or an older one: EXTMIN/EXTMAX as before (D-114).
    """
    try:
        doc.Regen(AC_ALL_VIEWPORTS)
    except BaseException as exc:  # noqa: BLE001 - the plot regenerates for itself anyway
        raise_if_busy(exc)
    model = bool(layout.ModelType)
    if model and not _plan_view(doc):
        return None, "the screen is not a plan view of the world UCS", None
    try:
        low = point_to_list(doc.GetVariable("EXTMIN" if model else "PEXTMIN"))
        high = point_to_list(doc.GetVariable("EXTMAX" if model else "PEXTMAX"))
        box = _box(low, high)
    except BaseException as exc:  # noqa: BLE001 - no extents to read
        raise_if_busy(exc)
        box = None
    note = None
    if model and box:
        fresh = _measured_model_box()
        if fresh and _shrunk_inside(fresh, box):
            note = (
                f"EXTMIN/EXTMAX still reach {_round_point(box[0])} to {_round_point(box[1])}: AutoCAD "
                "shrinks them only on ZOOM Extents. The picture covers the objects in model space as "
                f"Heron in AutoCAD measured them, {_round_point(fresh[0])} to {_round_point(fresh[1])}."
            )
            box = fresh
    return box, None if box else "the drawing has no extents (nothing drawn)", note


def _clear_text(box: Box, pixels: tuple[float, float]) -> float:
    """The smallest text height, in drawing units, that reads in this picture."""
    per_pixel = max((box[1][0] - box[0][0]) / pixels[0], (box[1][1] - box[0][1]) / pixels[1])
    return float(f"{CLEAR_TEXT_PX * per_pixel:.3g}")


# Sheet sizes (long x short) in millimetres and in inches: ISO A0-A2, ANSI D-E, ARCH D-E1.
_SHEETS_MM = ((1189.0, 841.0), (841.0, 594.0), (594.0, 420.0))
_SHEETS_IN = ((34.0, 22.0), (44.0, 34.0), (36.0, 24.0), (42.0, 30.0), (48.0, 36.0))
# The scales a sheet's frame is drawn at in model space, besides 1:1.
_SHEET_SCALES = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000)
SHEET_FIT = 0.03


def _is_sheet(box: Box) -> bool:
    """True when the box is an A2-or-bigger sheet (or its frame) at 1:1 or a drawing scale.

    The frame inside the margins counts too: up to about 11 % smaller than the paper.
    """
    long_side = max(box[1][0] - box[0][0], box[1][1] - box[0][1])
    short_side = min(box[1][0] - box[0][0], box[1][1] - box[0][1])
    for sheet_long, sheet_short in _SHEETS_MM + _SHEETS_IN:
        for scale in _SHEET_SCALES:
            fits_long = 0.92 - SHEET_FIT <= long_side / (sheet_long * scale) <= 1.0 + SHEET_FIT
            fits_short = 0.92 - SHEET_FIT <= short_side / (sheet_short * scale) <= 1.0 + SHEET_FIT
            if fits_long and fits_short:
                return True
    return False


def _sheet_too_fine(doc: Any, box: Box, clear: float) -> str | None:
    """Why a whole-sheet extents preview gets its close-ups by itself, or None (#41, D-141).

    On 2026-10-28 an extents picture of an A1 sheet at 1:1 showed only its
    frame, while windows over its parts showed everything. One picture of a
    sheet that big has too few pixels for its text and thin lines, so the
    close-ups (windows, the route that showed everything) come with it.
    """
    if not _is_sheet(box):
        return None
    try:
        text_size = float(doc.GetVariable("TEXTSIZE"))
    except BaseException as exc:  # noqa: BLE001 - not known: the picture alone, as before
        raise_if_busy(exc)
        return None
    if not 0 < text_size < clear:
        return None
    return (
        f"A whole sheet: text under about {clear:g} high does not read in one picture and this "
        f"drawing's text size (TEXTSIZE) is {text_size:g}, so four close-ups were added. Pass "
        "detail=1 for the one picture."
    )


def _detail_parts(box: Box, rows: int) -> list[tuple[str, list[float], list[float]]]:
    """Split a box into rows x rows overlapping windows, top left first."""
    (x0, y0), (x1, y1) = box
    width, height = (x1 - x0) / rows, (y1 - y0) / rows
    pad_x, pad_y = width * DETAIL_OVERLAP, height * DETAIL_OVERLAP
    parts = []
    for row in range(rows):
        top = y1 - row * height
        for column in range(rows):
            left = x0 + column * width
            name = f"{_DETAIL_ROWS[rows][row]} {_DETAIL_COLUMNS[rows][column]}"
            parts.append(
                (
                    "centre" if name == "middle centre" else name,
                    [left - pad_x, top - height - pad_y],
                    [left + width + pad_x, top + pad_y],
                )
            )
    return parts


def _detail_path(target: str, picture: int) -> str:
    stem, extension = os.path.splitext(target)
    return f"{stem}-{picture}{extension}"


def _round_point(point: Sequence[float]) -> list[float]:
    return [round(float(v), 3) for v in point]


def layout_on_screen(doc: Any) -> Any:
    """The layout whose tab is on screen (CTAB), not whatever COM's ActiveLayout last held.

    On 2026-11-22 the plug-in had put SAC2-104 on screen (CTAB said so), but
    doc.ActiveLayout still gave SAC2-102 and the preview plotted that sheet
    (D-125). CTAB is what the modeller sees, so it wins; ActiveLayout is the
    answer only when CTAB cannot be read or names no layout.
    """
    active = doc.ActiveLayout
    try:
        tab = str(doc.GetVariable("CTAB") or "").strip()
    except BaseException as exc:  # noqa: BLE001 - CTAB unreadable: COM's own answer then
        raise_if_busy(exc)
        return active
    if not tab or str(active.Name).strip().lower() == tab.lower():
        return active
    layouts = doc.Layouts
    for i in range(int(layouts.Count)):
        layout = layouts.Item(i)
        if str(layout.Name).strip().lower() == tab.lower():
            return layout
    return active


def _on_screen_for_plot(doc: Any) -> tuple[Any, str | None]:
    """The layout on screen, made COM's active one so PlotToFile plots it; and a note if it had to be."""
    layout = layout_on_screen(doc)
    active = doc.ActiveLayout
    if str(active.Name) == str(layout.Name):
        return active, None
    # PlotToFile plots COM's active layout. Making it the tab already on screen
    # changes nothing the modeller sees.
    doc.ActiveLayout = layout
    return layout, (
        f"AutoCAD's COM side still had '{active.Name}' as the active layout while '{layout.Name}' "
        "was on screen; the preview shows the one on screen."
    )


def _plot_png(
    doc: Any,
    target: str,
    area: str,
    corner1: Sequence[float] | None,
    corner2: Sequence[float] | None,
    width_px: int,
    detail: int | None = 1,
) -> dict[str, Any]:
    """Plot the active layout to a PNG through AutoCAD's own PNG plotter.

    Same order as _plot_pdf (plotter on the layout first, PlotToFile with the
    path alone) and the same restore, so a preview never changes the page setup.
    With detail 2 or 3 the same area is then plotted again as overlapping
    windows (D-102), each beside target as <name>-<picture>.png. With detail
    None (the tool's default) a whole sheet whose text cannot read in one
    picture gets the four close-ups by itself (#41, D-141).
    """
    auto = detail is None
    detail = 1 if detail is None else detail
    layout, resynced = _on_screen_for_plot(doc)
    plot = doc.Plot
    background = doc.GetVariable("BACKGROUNDPLOT")
    quiet = plot.QuietErrorMode
    snapshot = _snapshot_page_setup(doc, layout)
    size = None
    result: dict[str, Any] = {"area": area}
    if resynced:
        result["layout_note"] = resynced
    try:
        layout.ConfigName = PNG_PLOTTER
        layout.RefreshPlotDeviceInfo()
        sizes = []
        for name in tuple(layout.GetCanonicalMediaNames()):
            found = _PIXEL_MEDIA.search(name)
            if found:
                sizes.append((abs(float(found.group(1)) - width_px), name))
        if sizes:
            size = min(sizes)[1]
            layout.CanonicalMediaName = size
        # The picture must read the way the screen does. A layout set to plot
        # turned 90 degrees (an A3 portrait sheet laid landscape, or a template's
        # Model tab) gave a preview on its side (2026-11-05). The snapshot puts
        # the layout's own rotation back afterwards.
        try:
            layout.PlotRotation = AC_0_DEGREES
        except BaseException as exc:  # noqa: BLE001 - a preview on its side beats no preview
            raise_if_busy(exc)

        # Which area the picture covers, so a sheet too big for the pixels, or
        # extents stretched by something far off, can be seen (issue #41).
        box, why_not, measured_note = None, None, None
        if area == "extents":
            box, why_not, measured_note = _extents_box(doc, layout)
            if measured_note:
                result["extents_note"] = measured_note
        elif area == "window":
            box = _box(corner1, corner2)
            why_not = None if box else "the window has no area"
            if box and detail > 1 and bool(layout.ModelType) and not _plan_view(doc):
                # The close-ups split the window in world X and Y; in a 3D view or a
                # turned UCS those parts do not match the picture (D-102, #218).
                why_not = "the screen is not a plan view of the world UCS"
        found = _PIXEL_MEDIA.search(str(layout.CanonicalMediaName))
        pixels = (float(found.group(1)), float(found.group(2))) if found else None
        if box:
            low, high = box
            result["plotted"] = {
                "min": _round_point(low),
                "max": _round_point(high),
                "width": round(high[0] - low[0], 3),
                "height": round(high[1] - low[1], 3),
            }
        if pixels:
            result["pixels"] = [int(pixels[0]), int(pixels[1])]
        if box and pixels:
            result["smallest_clear_text"] = _clear_text(box, pixels)
            if auto and area == "extents" and why_not is None:
                why = _sheet_too_fine(doc, box, result["smallest_clear_text"])
                if why:
                    detail = 2
                    result["detail_added"] = why
        parts = []
        if detail > 1:
            if box and pixels and why_not is None:
                parts = _detail_parts(box, detail)
            else:
                why_not = why_not or "the PNG plotter offers no size in pixels"
                result["detail_skipped"] = (
                    f"No close-ups: {why_not}. This is the one picture; preview "
                    "area='window' over one part to look closer."
                )

        if area == "window":
            layout.SetWindowToPlot(_point2d(corner1, "corner1"), _point2d(corner2, "corner2"))
            layout.PlotType = AC_WINDOW
        elif measured_note and box:
            # AutoCAD's own Extents plot would frame the stale EXTMIN/EXTMAX (#269).
            layout.SetWindowToPlot(_point2d(box[0], "corner1"), _point2d(box[1], "corner2"))
            layout.PlotType = AC_WINDOW
        else:
            layout.PlotType = _PREVIEW_AREAS[area]
        layout.UseStandardScale = True
        layout.StandardScale = AC_SCALE_TO_FIT
        layout.CenterPlot = True
        doc.SetVariable("BACKGROUNDPLOT", 0)
        plot.QuietErrorMode = True
        plot.PlotToFile(target)

        # The close-ups are window plots: on 2026-10-28 windows over an A1
        # sheet's parts showed what its extents picture did not.
        detail_info = []
        for picture, (part, low, high) in enumerate(parts, start=2):
            layout.SetWindowToPlot(_point2d(low, "corner1"), _point2d(high, "corner2"))
            layout.PlotType = AC_WINDOW
            plot.PlotToFile(_detail_path(target, picture))
            detail_info.append(
                {"picture": picture, "part": part, "corner1": _round_point(low), "corner2": _round_point(high)}
            )
        if detail_info:
            result["detail"] = detail_info
            result["detail_smallest_clear_text"] = _clear_text((parts[0][1], parts[0][2]), pixels)
    finally:
        unrestored = _restore_plot_state(doc, layout, snapshot, background, quiet)
    result["layout"] = str(layout.Name)
    if size:
        result["size"] = size.replace("_", " ")
    clear = result.get("detail_smallest_clear_text", result.get("smallest_clear_text"))
    if clear and area != "view":
        try:
            text_size = float(doc.GetVariable("TEXTSIZE"))
        except BaseException:  # noqa: BLE001 - no tip then
            text_size = 0.0
        if 0 < text_size < clear:
            closer = (
                "area='window' over one part"
                if "detail" in result
                else "detail=2 (four close-ups), detail=3, or area='window' over one part"
            )
            result["tip"] = (
                f"Text under about {clear:g} drawing units high does not read in "
                f"{'these close-ups' if 'detail' in result else 'this picture'}, and "
                f"this drawing's text size (TEXTSIZE) is {text_size:g}: small parts "
                "and thin lines may not show. To look closer, call autocad_preview "
                f"again with {closer}."
            )
    if unrestored:
        result["warning"] = "Could not put back: " + "; ".join(unrestored)
    return result


def _ucs_name_of(doc: Any) -> str:
    """The name of the current UCS; an unnamed one reads back empty."""
    try:
        return str(doc.GetVariable("UCSNAME")).strip()
    except BaseException as exc:  # noqa: BLE001 - absent on a drawing with no UCS set
        raise_if_busy(exc)
        return ""


def _units_of(doc: Any) -> str:
    try:
        return unit_name(int(doc.GetVariable("INSUNITS")))
    except BaseException as exc:  # noqa: BLE001 - drawing may predate INSUNITS
        raise_if_busy(exc)
        return "unknown"


def _paper_space_count(doc: Any) -> int | None:
    """How many objects the active sheet holds, or None when AutoCAD will not say.

    ``doc.PaperSpace`` can throw a bare Automation error on a sheet AutoCAD has
    half set up (Luxury Suite 2, 2026-11-09: after a viewport hung on a sheet
    made with Layouts.Add), and one bad count used to sink the whole status
    report (#39). The sheet on screen (CTAB) is counted from its own block
    first, so COM's ActiveLayout lagging the tab (D-125) cannot give another
    sheet's count; then doc.PaperSpace, then the active layout's block, and
    last the Heron plug-in, which counts the sheet in .NET.
    """
    try:
        sheet = sheet_on_screen(doc)
        if sheet is not None:
            return int(sheet.Block.Count)
    except BaseException as exc:  # noqa: BLE001 - doc.PaperSpace is asked next
        raise_if_busy(exc)
    try:
        return int(doc.PaperSpace.Count)
    except BaseException as exc:  # noqa: BLE001 - see the docstring
        raise_if_busy(exc)
    try:
        return int(doc.ActiveLayout.Block.Count)
    except BaseException as exc:  # noqa: BLE001 - the plug-in is asked next
        raise_if_busy(exc)
    report, _ = plugin_read("active_sheet")
    # On the Model tab the plug-in counts model space, which is not a paper count.
    if report and report.get("model") is False and isinstance(report.get("entities"), int):
        return int(report["entities"])
    return None


def _active_space(doc: Any) -> str:
    """'model' or 'paper': the tab on screen first (TILEMODE, CTAB), then COM's ActiveSpace.

    TILEMODE and CTAB are AutoCAD's own variables and answer on a sheet tab where
    COM's ActiveSpace and ActiveLayout did not (#39) or lagged (D-125). A sheet
    tab is "paper" even with a viewport made active on it: the tab is a sheet.
    """
    try:
        return "model" if int(doc.GetVariable("TILEMODE")) == 1 else "paper"
    except BaseException as exc:  # noqa: BLE001 - CTAB says it too
        raise_if_busy(exc)
    try:
        tab = str(doc.GetVariable("CTAB") or "").strip()
        if tab:
            return "model" if tab.lower() == "model" else "paper"
    except BaseException as exc:  # noqa: BLE001 - COM's own answer next
        raise_if_busy(exc)
    try:
        return "model" if int(doc.ActiveSpace) == 1 else "paper"
    except BaseException as exc:  # noqa: BLE001 - the layout's name says it too
        raise_if_busy(exc)
    try:
        return "model" if str(doc.ActiveLayout.Name) == "Model" else "paper"
    except BaseException as exc:  # noqa: BLE001
        raise_if_busy(exc)
        report, _ = plugin_read("active_sheet")
        if report and "model" in report:
            return "model" if report["model"] else "paper"
        return "unknown"


def _layout_name(doc: Any) -> str:
    """The tab on screen: CTAB, else COM's ActiveLayout (which can lag it, D-125)."""
    try:
        tab = str(doc.GetVariable("CTAB") or "").strip()
        if tab:
            return tab
    except BaseException as exc:  # noqa: BLE001 - COM's own answer next
        raise_if_busy(exc)
    return str(doc.ActiveLayout.Name)


def _viewport_active(doc: Any) -> bool:
    """True on a sheet tab whose viewport is active (MSPACE): CVPORT is then above 1."""
    try:
        return int(doc.GetVariable("TILEMODE")) == 0 and int(doc.GetVariable("CVPORT")) > 1
    except BaseException as exc:  # noqa: BLE001 - not known to be in a viewport
        raise_if_busy(exc)
        return False


def _status_field(unread: list[str], name: str, read: Any, default: Any = None) -> Any:
    """One status fact. A fact AutoCAD will not give is named in "unreadable", never the whole answer (#39)."""
    try:
        return read()
    except BaseException as exc:  # noqa: BLE001 - one bad property must not sink the report
        raise_if_busy(exc)  # a busy AutoCAD is asked again, not reported as unreadable
        unread.append(name)
        return default


@mcp.tool(
    name="autocad_status",
    **tool_meta("AutoCAD Connection Status", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_status(
    launch_if_needed: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Start AutoCAD if no instance is running. Launching takes "
                "30-60 seconds and opens a blank drawing."
            ),
        ),
    ] = False,
) -> str:
    """Check the AutoCAD connection and report what is currently open.

    Call this first in any AutoCAD session. It confirms the COM link works and
    returns the drawing's units, current layer and entity counts that later
    calls depend on — in particular, coordinates passed to the drawing tools
    are in the drawing's own units, which this reports.

    Args:
        launch_if_needed (bool): Start AutoCAD when nothing is running.

    Returns:
        str: JSON with this schema:
        {
          "connected": bool,
          "application": str,          # window caption, e.g. "Autodesk AutoCAD 2020"
          "version": str,              # e.g. "23.1s (LMS Tech)"
          "open_drawings": int,
          "active_drawing": {
            "name": str,               # e.g. "Drawing1.dwg"
            "path": str,               # full path, "" when never saved
            "saved": bool,             # false when unsaved changes exist
            "read_only": bool,
            "active_space": str,       # "model" or "paper": the tab on screen ("unknown" if AutoCAD will not say)
            "viewport_active": bool,   # only on a sheet tab whose viewport is active (MSPACE)
            "active_layout": str,      # the tab on screen, e.g. "Model" or "E-101"
            "units": str,              # e.g. "millimeters"
            "ucs": {                   # the coordinate system the modeller is working in
              "name": str, "is_world": bool, "origin": [float],
              "rotation_degrees": float, "moved": bool, "rotated": bool,
              "tilted": bool, "flipped": bool
            },
            "ucs_advice": str | null,  # present only when the UCS is not the world one
            "current_layer": str,
            "model_space_entities": int,
            "paper_space_entities": int | null,  # null when AutoCAD will not say
            "layer_count": int,
            "block_definition_count": int,
            "unreadable": [str]        # only when AutoCAD would not give some of the above (null then)
          } | null
        }

        Error response: "Error: <what to do about it>"

    Examples:
        - Use when: starting work, to confirm Claude can reach AutoCAD.
        - Use when: you need the drawing's units before placing geometry.
        - Use when: you are about to draw — "ucs_advice" warns you when the
          modeller's coordinates are not world coordinates.
        - Don't use when: you want the entity list (use autocad_list_entities).
    """

    def work() -> dict[str, Any]:
        app = get_app(launch_if_needed=launch_if_needed)
        skipped: list[str] = []  # the window caption and version are extras, never the answer (#39)
        result: dict[str, Any] = {
            "connected": True,
            "application": _status_field(skipped, "application", lambda: str(app.Caption)[:120], ""),
            "version": _status_field(skipped, "version", lambda: str(app.Version), ""),
            "open_drawings": int(app.Documents.Count),
        }
        if result["open_drawings"] == 0:
            result["active_drawing"] = None
            result["hint"] = (
                "AutoCAD is running with no drawing open. Use "
                "autocad_create_drawing or autocad_open_drawing."
            )
            return result

        doc = app.ActiveDocument
        ucs = current_ucs(doc)
        unread: list[str] = list(skipped)
        name = _status_field(unread, "name", lambda: str(doc.Name), "")
        full = _status_field(unread, "path", lambda: str(doc.FullName), "")
        result["active_drawing"] = {
            "name": name,
            "path": full if full != name else "",
            "saved": _status_field(unread, "saved", lambda: bool(doc.Saved)),
            "read_only": _status_field(unread, "read_only", lambda: bool(doc.ReadOnly)),
            "active_space": _active_space(doc),
            "active_layout": _status_field(unread, "active_layout", lambda: _layout_name(doc)),
            "units": _units_of(doc),
            "ucs": ucs.describe(_ucs_name_of(doc) or None),
            "current_layer": _status_field(unread, "current_layer", lambda: str(doc.ActiveLayer.Name)),
            "model_space_entities": _status_field(unread, "model_space_entities", lambda: int(doc.ModelSpace.Count)),
            "paper_space_entities": _paper_space_count(doc),
            "layer_count": _status_field(unread, "layer_count", lambda: int(doc.Layers.Count)),
            "block_definition_count": _status_field(unread, "block_definition_count", lambda: int(doc.Blocks.Count)),
        }
        if result["active_drawing"]["active_space"] == "paper" and _viewport_active(doc):
            # Drawing tools still draw in model space unless asked for space="paper".
            result["active_drawing"]["viewport_active"] = True
        if unread:
            result["active_drawing"]["unreadable"] = unread
        # Coordinates here are always world ones. When the modeller has set a
        # UCS, say so on the first call of every session rather than letting a
        # line land somewhere nobody meant (autocad_get_ucs has the detail).
        note = ucs_advice(ucs)
        if note:
            result["active_drawing"]["ucs_advice"] = note
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_list_drawings",
    **tool_meta("List Open Drawings", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_list_drawings() -> str:
    """List every drawing currently open in AutoCAD.

    Use before autocad_switch_drawing when more than one file is open, so the
    target can be named exactly.

    Returns:
        str: JSON: {"count": int, "drawings": [{"index": int, "name": str,
             "path": str, "saved": bool, "active": bool}]}

    Examples:
        - Use when: "which drawings are open" before switching between them.
        - Use when: a change was refused because the active drawing is not the
          one you meant.
    """

    def work() -> dict[str, Any]:
        app = get_app()
        active_name = str(app.ActiveDocument.Name) if app.Documents.Count else ""
        drawings = []
        for i in range(app.Documents.Count):
            doc = app.Documents.Item(i)
            drawings.append(
                {
                    "index": i,
                    "name": str(doc.Name),
                    "path": str(doc.FullName)
                    if str(doc.FullName) != str(doc.Name)
                    else "",
                    "saved": bool(doc.Saved),
                    "active": str(doc.Name) == active_name,
                }
            )
        return {"count": len(drawings), "drawings": drawings}

    return dumps(await run(work))


@mcp.tool(
    name="autocad_create_drawing",
    **tool_meta("Create New Drawing"),
)
@tool_errors
async def autocad_create_drawing(
    template: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Template to start from: a .dwt name such as 'acadiso.dwt' "
                "(metric) or 'acad.dwt' (imperial), or a full path to a .dwt "
                "file. Omit for AutoCAD's default template."
            ),
        ),
    ] = None,
) -> str:
    """Create a new drawing and make it active.

    The new drawing becomes active immediately, so later drawing tools target
    it without an extra step.

    Args:
        template (Optional[str]): Template name or full path.

    Returns:
        str: JSON: {"created": true, "name": str, "units": str,
             "template": str}

    Examples:
        - Use when: "start a new metric drawing" -> template="acadiso.dwt".
        - Don't use when: a drawing is already open and you only want to draw
          in it; the drawing tools already target the active drawing.
    """

    def work() -> dict[str, Any]:
        app = get_app(launch_if_needed=True)
        doc = app.Documents.Add(template) if template else app.Documents.Add()
        return {
            "created": True,
            "name": str(doc.Name),
            "units": _units_of(doc),
            "template": template or "default",
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_open_drawing",
    **tool_meta("Open Drawing File", idempotent=True),
)
@tool_errors
async def autocad_open_drawing(
    path: Annotated[
        str,
        Field(
            description=(
                "Full path to a .dwg or .dxf file, e.g. "
                r"'D:\Projects\Site\ground-floor.dwg'."
            ),
            min_length=3,
        ),
    ],
    read_only: Annotated[
        bool,
        Field(
            default=False,
            description="Open without a write lock so others can still edit it.",
        ),
    ] = False,
) -> str:
    """Open an existing drawing file and make it active.

    Args:
        path (str): Full path to a .dwg or .dxf file.
        read_only (bool): Open without taking the write lock.

    Returns:
        str: JSON: {"opened": true, "name": str, "path": str, "units": str,
             "read_only": bool, "model_space_entities": int}

    Error Handling:
        - Returns a path error naming the resolved path if the file does not
          exist, before AutoCAD is contacted at all.

    Examples:
        - Use when: "open the architectural background" so you can reference
          or copy from it.
        - Don't use when: you only want its blocks or layers -
          autocad_import_from_drawing leaves the file closed.
    """
    resolved = _expand(path)
    if not os.path.isfile(resolved):
        raise AutocadError(
            f"No file exists at '{resolved}'. Check the path and drive letter; "
            "it must be reachable from this machine."
        )

    def work() -> dict[str, Any]:
        app = get_app(launch_if_needed=True)
        doc = app.Documents.Open(resolved, read_only)
        return {
            "opened": True,
            "name": str(doc.Name),
            "path": str(doc.FullName),
            "units": _units_of(doc),
            "read_only": bool(doc.ReadOnly),
            "model_space_entities": int(doc.ModelSpace.Count),
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_save_drawing",
    **tool_meta("Save Drawing", idempotent=True),
)
@tool_errors
async def autocad_save_drawing(
    path: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Save to this path instead of the current one (Save As). Omit "
                "to save over the existing file. Include the .dwg extension."
            ),
        ),
    ] = None,
) -> str:
    """Save the active drawing, optionally to a new path.

    Args:
        path (Optional[str]): Target path for a Save As, or None to save in
            place.

    Returns:
        str: JSON: {"saved": true, "path": str}

    Error Handling:
        - A never-saved drawing with no path given returns an error asking for
          one, rather than triggering AutoCAD's blocking Save As dialog.

    Examples:
        - Use when: the work is finished and checked. It needs the Publish
          padlock, because it writes a file.
        - Don't use when: you are mid-job - leave it unsaved so one Ctrl+Z
          still gets you out.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        if path:
            target = _expand(path)
            parent = os.path.dirname(target)
            if parent and not os.path.isdir(parent):
                raise AutocadError(
                    f"The folder '{parent}' does not exist. Create it first or "
                    "choose an existing folder."
                )
            doc.SaveAs(target)
            return {"saved": True, "path": str(doc.FullName)}

        if str(doc.FullName) == str(doc.Name):
            raise AutocadError(
                "This drawing has never been saved, so there is no path to save "
                "over. Call autocad_save_drawing again with an explicit 'path'. "
                "(Saving without one would open AutoCAD's Save As dialog and "
                "block every further command.)"
            )
        doc.Save()
        return {"saved": True, "path": str(doc.FullName)}

    return dumps(await run(work))


@mcp.tool(
    name="autocad_switch_drawing",
    **tool_meta("Switch Active Drawing", idempotent=True),
)
@tool_errors
async def autocad_switch_drawing(
    name: Annotated[
        str,
        Field(
            description=(
                "File name of an already-open drawing, e.g. 'site-plan.dwg'. "
                "Matching is case-insensitive and the .dwg suffix is optional. "
                "Exact names come from autocad_list_drawings."
            ),
            min_length=1,
        ),
    ],
) -> str:
    """Make a different open drawing the active one.

    All other tools act on the active drawing, so switch before working on a
    second file.

    Args:
        name (str): File name of an open drawing.

    Returns:
        str: JSON: {"active_drawing": str, "path": str}

    Error Handling:
        - Lists the drawings that are actually open if the name does not match.

    Examples:
        - Use when: you have the wrong drawing active. Call autocad_status
          afterwards: the gate checks the units of the drawing it is about to
          change.
    """

    def work() -> dict[str, Any]:
        app = get_app()
        wanted = os.path.splitext(name.strip().lower())[0]
        available = []
        for i in range(app.Documents.Count):
            doc = app.Documents.Item(i)
            doc_name = str(doc.Name)
            available.append(doc_name)
            if os.path.splitext(doc_name.lower())[0] == wanted:
                doc.Activate()
                return {"active_drawing": doc_name, "path": str(doc.FullName)}
        raise AutocadError(
            f"No open drawing is named '{name}'. Currently open: "
            + (", ".join(available) if available else "none")
            + ". Use autocad_open_drawing to open a file from disk."
        )

    return dumps(await run(work))


@mcp.tool(
    name="autocad_export",
    **tool_meta("Export Drawing", idempotent=True),
)
@tool_errors
async def autocad_export(
    path: Annotated[
        str,
        Field(
            description=(
                "Output file path including extension, e.g. "
                r"'D:\out\plan.dxf', 'D:\out\plan.pdf' or 'D:\out\plan.dwf'. "
                "The extension selects the format."
            ),
            min_length=4,
        ),
    ],
    paper_size: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "PDF and DWF only: the sheet to plot on, e.g. 'A3', 'A1 portrait', "
                "'ANSI D', or an exact DWG To PDF media name such as "
                "'ISO full bleed A3 (420.00 x 297.00 MM)'. Short names pick "
                "the full-bleed landscape sheet. Omit to keep the layout's "
                "current paper (the plotter's default sheet if the layout is "
                "set up for a different printer)."
            ),
        ),
    ] = None,
    area: Annotated[
        Literal["extents", "layout", "limits", "display", "window", "view"],
        Field(
            default="extents",
            description=(
                "PDF and DWF only: what to plot. 'extents' (the default) plots "
                "everything drawn. 'layout' plots the sheet itself, which is "
                "what a sheet with a title block wants. 'window' plots the "
                "rectangle given by corner1/corner2. 'view' plots a saved view "
                "by name, so the very area saved with autocad_save_view is the "
                "area that comes out."
            ),
        ),
    ] = "extents",
    corner1: Annotated[
        list[float] | None,
        Field(default=None, description="For area='window': one corner, in the units of the space being plotted."),
    ] = None,
    corner2: Annotated[
        list[float] | None,
        Field(default=None, description="For area='window': the opposite corner."),
    ] = None,
    view_name: Annotated[
        str | None,
        Field(default=None, description="For area='view': the saved view to plot. autocad_list_views shows them."),
    ] = None,
    scale: Annotated[
        str | float | None,
        Field(
            default=None,
            description=(
                "PDF and DWF only: plot scale, e.g. '1:1' for a laid-out sheet or "
                "'1:50' for a model-space plot. Omit to scale to fit the sheet."
            ),
        ),
    ] = None,
) -> str:
    """Export the active drawing to DXF, PDF, DWF or another supported format.

    The format comes from the file extension. DXF, WMF, SAT, BMP, EPS and STL
    are written by AutoCAD's exporter. PDF plots the active layout's extents,
    centred and scaled to fit the sheet, through the "DWG To PDF" plotter; DWF
    plots the same way through the "DWF6 ePlot" plotter (Output > Export DWF).
    The layout's own page setup is put back afterwards.

    Args:
        path (str): Output path whose extension selects the format.
        paper_size (Optional[str]): PDF sheet size; None keeps the current.
        area (str): PDF and DWF only — extents, layout, limits, display, window or view.
        corner1 (Optional[list[float]]): PDF window, first corner.
        corner2 (Optional[list[float]]): PDF window, opposite corner.
        view_name (Optional[str]): PDF saved view to plot.
        scale (Optional[str | float]): PDF plot scale; None scales to fit.

    Returns:
        str: JSON: {"exported": true, "path": str, "format": str,
             "size_bytes": int}
             PDF adds "layout" (e.g. "Model"), "paper", the sheet used
             (e.g. "ISO full bleed A3 (420.00 x 297.00 MM)"), "area", and
             "view" / "scale" when those were given.

    Examples:
        - Use when: "give me this drawing as a DXF" -> path ending in .dxf.
        - Use when: "export a PDF of the current layout" -> path ending in .pdf.
        - Use when: "PDF it on A1" -> path ending in .pdf, paper_size="A1".
        - Use when: "the consultant wants a DWF of this sheet" -> path ending
          in .dwf, area="layout", scale="1:1".
        - Use when: "plot the sheet, not the geometry" -> area="layout",
          scale="1:1".
        - Use when: "plot the same area as the viewport" -> autocad_save_view
          once, then area="view", view_name that name.
        - Don't use when: you want to save the .dwg itself (use
          autocad_save_drawing).

    Error Handling:
        - Verifies a new file actually appeared on disk afterwards, since
          AutoCAD's plotter can report success without writing anything —
          for example when the old PDF is open, and locked, in a viewer.
        - An unknown paper_size lists the sizes the plotter does offer.
    """
    target = os.path.abspath(_expand(path))
    ext = os.path.splitext(target)[1].lstrip(".").lower()
    parent = os.path.dirname(target)
    if not os.path.isdir(parent):
        raise AutocadError(f"The output folder '{parent}' does not exist.")
    if ext not in PLOTTERS and ext not in EXPORT_FORMATS:
        raise AutocadError(
            f"'{ext}' is not a supported export format. Use pdf, dwf, "
            + ", ".join(sorted(EXPORT_FORMATS))
            + "."
        )
    # Everything below the format is a plotting option, so none of it means
    # anything to AutoCAD's exporter for DXF, SAT, STL and the rest.
    pdf_only = [
        name
        for name, value in (
            ("paper_size", paper_size),
            ("corner1", corner1),
            ("corner2", corner2),
            ("view_name", view_name),
            ("scale", scale),
        )
        if value is not None
    ]
    if area != "extents":
        pdf_only.append("area")
    if ext not in PLOTTERS and pdf_only:
        raise AutocadError(
            f"{', '.join(sorted(pdf_only))} only applies to PDF and DWF exports, not '{ext}'. "
            "Leave it out, or give a path ending in .pdf or .dwf."
        )

    window = None
    if area == "window":
        if not (corner1 and corner2):
            raise AutocadError("area='window' needs both corner1 and corner2, each as [x, y].")
        window = (_point2d(corner1, "corner1"), _point2d(corner2, "corner2"))
    if area == "view" and not view_name:
        raise AutocadError(
            "area='view' needs view_name. autocad_list_views shows the drawing's saved views."
        )
    if scale is not None:
        try:
            sheet_plan.parse_typed_scale(scale)
        except ValueError as exc:
            raise AutocadError(str(exc)) from exc

    def work() -> dict[str, Any]:
        doc = get_doc()
        result: dict[str, Any] = {"exported": True, "path": target, "format": ext}
        with undo_mark(doc):
            if ext in PLOTTERS:
                result.update(
                    _plot_pdf(doc, target, paper_size, area, window, view_name, scale, PLOTTERS[ext])
                )
            else:
                # Export takes the name without extension plus a format code,
                # and a selection set naming what to write.
                stem = os.path.splitext(target)[0]
                sel_name = "MCP_EXPORT_ALL"
                try:
                    doc.SelectionSets.Item(sel_name).Delete()
                except BaseException as exc:  # noqa: BLE001 - no leftover set
                    raise_if_busy(exc)
                sel = doc.SelectionSets.Add(sel_name)
                try:
                    doc.Export(stem, ext.upper(), sel)
                finally:
                    try:
                        sel.Delete()
                    except BaseException:  # noqa: BLE001
                        pass
        return result

    before = _mtime(target)
    result = await run(work)
    written = _mtime(target)
    if written is None or written == before:
        stale = (
            " The file already there is left over from an earlier export."
            if written is not None
            else ""
        )
        raise AutocadError(
            f"AutoCAD reported success but did not write '{target}'.{stale} "
            "For PDF or DWF, check the file is not open in a viewer (which locks "
            f"it) and that the '{PLOTTERS.get(ext, PDF_PLOTTER)}' plotter is installed; for other "
            "formats, confirm the folder is writable."
        )
    result["size_bytes"] = os.path.getsize(target)
    return dumps(result)


@mcp.tool(
    name="autocad_zoom",
    **tool_meta("Zoom The View", idempotent=True),
)
@tool_errors
async def autocad_zoom(
    mode: Annotated[
        str,
        Field(
            default="extents",
            description=(
                "'extents' fits all drawn geometry, 'all' fits the drawing "
                "limits, 'window' fits the rectangle given by corner1/corner2."
            ),
            pattern="^(extents|all|window)$",
        ),
    ] = "extents",
    corner1: Annotated[
        list[float] | None,
        Field(default=None, description="[x, y] first corner, for mode='window'."),
    ] = None,
    corner2: Annotated[
        list[float] | None,
        Field(default=None, description="[x, y] opposite corner, for mode='window'."),
    ] = None,
) -> str:
    """Change what the AutoCAD window is showing.

    Worth calling after drawing something so the user can see the result, and
    before asking for a screenshot of AutoCAD.

    Args:
        mode (str): "extents", "all" or "window".
        corner1 (Optional[list[float]]): [x, y] for window mode.
        corner2 (Optional[list[float]]): [x, y] for window mode.

    Returns:
        str: JSON: {"zoomed": str}

    Examples:
        - Use when: "show me that corner" before a preview, so the picture is
          of the right thing.
        - Use when: zooming to a saved view or an object's extents.
    """

    def work() -> dict[str, Any]:
        app = get_app()
        if mode == "window":
            if not corner1 or not corner2:
                raise AutocadError(
                    "mode='window' needs both corner1 and corner2 as [x, y] pairs."
                )
            app.ZoomWindow(
                apoint(corner1[0], corner1[1]), apoint(corner2[0], corner2[1])
            )
        elif mode == "all":
            app.ZoomAll()
        else:
            app.ZoomExtents()
        return {"zoomed": mode}

    return dumps(await run(work))


SHOW_MOST = 500


@mcp.tool(
    name="autocad_show",
    **tool_meta("Show Objects In The Drawing", idempotent=True),
)
@tool_errors
async def autocad_show(
    handles: Annotated[
        list[str] | None,
        Field(
            default=None,
            max_length=SHOW_MOST,
            description=(
                "The objects to show, by handle (from any query tool). Not needed with "
                "end_isolation."
            ),
        ),
    ] = None,
    isolate: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Also hide everything else for now (AutoCAD's ISOLATEOBJECTS). Temporary: "
                "not saved with the drawing. End it with end_isolation=true."
            ),
        ),
    ] = False,
    end_isolation: Annotated[
        bool,
        Field(default=False, description="Bring back everything an earlier isolate hid (UNISOLATEOBJECTS)."),
    ] = False,
) -> str:
    """Put objects in front of the modeller: select them and zoom to them.

    The answer to "which ones?" given in the drawing, not as a list of
    handles. The objects are left selected (grips on), so the modeller can
    look at them, move them or press Delete themselves. Changes nothing in
    the drawing and needs no padlock, only the connection.

    Args:
        handles (list[str]): what to show, at most 500.
        isolate (bool): hide the rest for now.
        end_isolation (bool): show everything again.

    Returns:
        str: JSON: {"shown": int, "isolated": bool, "not_found": [str],
             "not_selectable": [{"handle": str, "reason": str}]}
             or {"isolation_ended": true}

    Examples:
        - Use when: "show me the blocks with no tag" - find them, then show
          their handles.
        - Use when: "where are the duplicates?" or "which lines are on layer 0?"
          after a query tool found them.
        - Use when: "show only the sprinkler pipes for now" -> isolate=true;
          "bring everything back" -> end_isolation=true.
        - Don't use when: the whole drawing or a window should fit the screen -
          autocad_zoom.
        - Don't use when: the objects should be changed - use the editing tool;
          this only shows them.

    Error Handling:
        - Handles that are not in the drawing come back in not_found; the rest
          are still shown.
        - Needs Heron's plug-in in AutoCAD (it does the selecting).
        - Only drawing objects in the space in front are selected; "shown"
          counts those. The rest come back in not_selectable: "other_space"
          (switch tabs first), "inside_block", "not_a_drawing_object" (a style
          or layer). "selection_refused": AutoCAD took none.
    """
    if not end_isolation and not handles:
        raise AutocadError("Give the handles to show, or end_isolation=true to show everything again.")

    def work() -> dict[str, Any]:
        args: dict[str, Any] = {"end_isolation": True} if end_isolation else {"handles": list(handles or []), "isolate": isolate}
        return in_plugin("show", args, "Showing objects in the drawing", changes=False)

    return dumps(await run(work))


@mcp.tool(
    name="autocad_use_autocad",
    **tool_meta("Choose Which AutoCAD", idempotent=True),
)
@tool_errors
async def autocad_use_autocad(
    pid: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            description=(
                "The process number of the AutoCAD to work in, from this tool's own list. "
                "Leave it out to list the AutoCADs connected to Heron."
            ),
        ),
    ] = None,
) -> str:
    """List the AutoCADs connected to Heron, or pick the one to work in.

    With one AutoCAD connected, Heron works in it and this is not needed.
    With two or more, nothing is sent until one is picked here: Heron never
    guesses, because a change in the wrong AutoCAD is the worst mistake it
    can make. If the picked one closes, Heron stops and asks again; it never
    moves on to another by itself. After picking, call autocad_status before
    drawing: the other AutoCAD's drawing may be in other units.

    Args:
        pid (int | None): the AutoCAD to work in; leave out to list them.

    Returns:
        str: JSON: {"connected": [{"pid", "acad_version", "plugin_version",
             "connected_since", "in_use"}], "in_use": int | null, "note": str}

    Examples:
        - Use when: a tool says "2 AutoCADs are connected to Heron" - list
          them, ask the modeller which (by version), then pick it.
        - Use when: "work in the AutoCAD 2025 one" or "use the other AutoCAD".
        - Don't use when: only one AutoCAD is connected - Heron already works in it.
        - Don't use when: switching drawings inside one AutoCAD -
          autocad_switch_drawing.

    Error Handling:
        - A process that is not an AutoCAD connected to Heron is refused, with
          the list of those that are.
    """
    from ..core import gate, sessions
    from ..core.connection import invalidate

    if pid is not None:
        picked = sessions.choose(pid)
        invalidate()
        gate.reset()  # another AutoCAD: its drawing's units are checked again
    found = sessions.connected()
    in_use = sessions.chosen() if sessions.chosen() is not None else (found[0]["pid"] if len(found) == 1 else None)
    result: dict[str, Any] = {
        "connected": [{**acad, "in_use": acad["pid"] == in_use} for acad in found],
        "in_use": in_use,
    }
    if pid is not None:
        result["note"] = (
            f"Heron now works in {sessions.describe(picked)}. Call autocad_status before drawing: "
            "it gives this drawing's units."
        )
    elif not found:
        result["note"] = "No AutoCAD is connected to Heron. Press the Heron button on the Heron tab in AutoCAD."
    elif in_use is None:
        result["note"] = "More than one is connected and none is picked: ask the modeller which, then pass its pid."
    return dumps(result)


@mcp.tool(
    name="autocad_get_variable",
    **tool_meta("Read System Variable", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_get_variable(
    name: Annotated[
        str,
        Field(
            description=(
                "System variable name, e.g. 'INSUNITS', 'CLAYER', 'DIMSCALE', "
                "'LTSCALE', 'EXTMIN', 'TEXTSIZE', 'OSMODE', 'PDMODE'."
            ),
            min_length=1,
            max_length=64,
        ),
    ],
) -> str:
    """Read one AutoCAD system variable.

    System variables carry drawing settings no other tool exposes — dimension
    scale, text size, point display mode, linetype scale and so on.

    Args:
        name (str): The variable name, case-insensitive.

    Returns:
        str: JSON: {"name": str, "value": str | float | int | list[float]}

    Examples:
        - Use when: "what is DIMSCALE set to" - or checking that a setting
          really landed.
        - Don't use when: you want the usual drawing settings - autocad_status
          and autocad_drawing_setup report them together.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        var = name.strip().upper()
        try:
            value = doc.GetVariable(var)
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            raise AutocadError(
                f"'{name}' is not a system variable this drawing recognises. "
                "Check the spelling against AutoCAD's SETVAR list."
            ) from exc
        return {
            "name": var,
            "value": point_to_list(value) if isinstance(value, tuple) else value,
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_set_variable",
    **tool_meta("Write System Variable", idempotent=True),
)
@tool_errors
async def autocad_set_variable(
    name: Annotated[
        str,
        Field(description="System variable name, e.g. 'DIMSCALE'.", min_length=1),
    ],
    value: Annotated[
        str,
        Field(
            description=(
                "New value as text. Numeric variables accept '50' or '0.25'; "
                "string variables take the text directly."
            )
        ),
    ],
) -> str:
    """Set one AutoCAD system variable on the active drawing.

    Args:
        name (str): The variable name.
        value (str): New value; converted to the variable's existing type.

    Returns:
        str: JSON: {"name": str, "previous": Any, "value": Any,
             "before_after": [{variable, property, from, to}] (empty when it already had that value)}

    Error Handling:
        - Returns a type error rather than a COM failure when a numeric
          variable is given non-numeric text.
        - A point variable (LIMMAX, UCSORG) takes "x,y" or "x,y,z"; the wrong
          count of numbers is refused before anything is written.

    Examples:
        - Use when: a variable is needed that autocad_drawing_setup does not
          cover. It needs the Admin padlock, because it can set anything.
        - Don't use when: autocad_drawing_setup can do it - that needs only
          Changes, and it works from a fixed list.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        var = name.strip().upper()
        try:
            previous = doc.GetVariable(var)
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            raise AutocadError(
                f"'{name}' is not a system variable this drawing recognises."
            ) from exc

        # Match the variable's existing type so AutoCAD accepts the assignment.
        if isinstance(previous, bool):
            new_value: Any = value.strip().lower() in {"1", "true", "on", "yes"}
        elif isinstance(previous, int):
            try:
                new_value = int(float(value))
            except ValueError:
                raise AutocadError(
                    f"'{var}' holds a whole number, but '{value}' is not numeric."
                ) from None
        elif isinstance(previous, float):
            try:
                new_value = float(value)
            except ValueError:
                raise AutocadError(
                    f"'{var}' holds a number, but '{value}' is not numeric."
                ) from None
        elif isinstance(previous, tuple):
            # A point: "x,y" (or "x,y,z") as an array of doubles, which is the
            # only form AutoCAD takes for one.
            parts = [p for p in value.replace("[", " ").replace("]", " ").replace(",", " ").split() if p]
            try:
                numbers = [float(p) for p in parts]
            except ValueError:
                numbers = []
            if len(numbers) != len(previous):
                raise AutocadError(
                    f"'{var}' is a point of {len(previous)} numbers; give them as "
                    f"'{','.join(['0'] * len(previous))}', not '{value}'."
                )
            new_value = double_array(numbers)
        else:
            new_value = value

        doc.SetVariable(var, new_value)
        current = doc.GetVariable(var)
        before = point_to_list(previous) if isinstance(previous, tuple) else previous
        after = point_to_list(current) if isinstance(current, tuple) else current
        rows = [] if before == after else [{"variable": var, "property": "value", "from": before, "to": after}]
        return {"name": var, "previous": before, "value": after, **before_after(rows)}

    return dumps(await run(work))


@mcp.tool(
    name="autocad_preview",
    # An image is content, not structured data: without this the SDK tries
    # to serialise it as JSON and the call fails.
    structured_output=False,
    **tool_meta("Preview Drawing as Image", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_preview(
    area: Annotated[
        Literal["extents", "view", "window"],
        Field(description="What to show: the whole drawing, the current view, or a window."),
    ] = "extents",
    corner1: Annotated[
        list[float] | None, Field(description="Window corner [x, y] (area='window').")
    ] = None,
    corner2: Annotated[
        list[float] | None, Field(description="Opposite window corner [x, y].")
    ] = None,
    width_px: Annotated[
        int, Field(ge=320, le=4000, description="Wanted image width in pixels.")
    ] = 1600,
    detail: Annotated[
        int | None,
        Field(
            ge=1,
            le=3,
            description=(
                "1 = one picture. 2 or 3 = also close-ups of the same area, "
                "split 2 x 2 or 3 x 3 (area='extents' or 'window'): use it for "
                "a full sheet, whose small text and thin lines cannot show in "
                "one picture. Omit: one picture, or four close-ups as well when "
                "the extents are a whole sheet whose text cannot read in one."
            ),
        ),
    ] = None,
) -> list | str:
    """See the drawing: plot it to a PNG and return the picture.

    Use after drawing something, to check it looks right before reporting it
    done. Plots through AutoCAD's own PNG plotter, so it shows what a plot
    would show; the page setup is put back afterwards and nothing is drawn.

    One picture has a fixed number of pixels (about 1600 across), so a whole
    A1 sheet at 1:1 gets about half a millimetre a pixel: 2.5 mm text and thin
    lines do not show, though the heavy frame does (issue #41). The answer
    says the area plotted and the smallest text that reads
    (`smallest_clear_text`); `detail=2` adds four overlapping close-ups of
    the same area, `detail=3` nine. With `detail` left out, an extents
    preview of a whole sheet (A2 or bigger, at 1:1 or a drawing scale) whose
    text cannot read in one picture gets the four close-ups by itself, and
    `detail_added` says why; `detail=1` keeps it to one picture.

    Returns:
        The PNG image (then one per close-up, top left first), then JSON:
        {"area", "layout", "size", "pixels", "plotted": {"min", "max",
        "width", "height"}, "smallest_clear_text", "detail": [{"picture",
        "part", "corner1", "corner2"}], "detail_smallest_clear_text",
        "detail_added", "extents_note", "tip"}.
        A `plotted` area much bigger than the sheet means something lies far
        off: find it with autocad_get_extents. `extents_note` says the
        picture covers model space as Heron in AutoCAD measured it, because
        EXTMIN/EXTMAX still reached an erased object.

    Examples:
        - Use when: you have drawn something and want to see it before saying
          it is done. Drafting rule: look at the picture, then fix it.
        - Use when: checking crossings, overlaps, text on lines, crowding.
        - Use when: "check the whole sheet": `detail=2` for an A1 or A0, so
          the text can be read.
        - Don't use when: a PDF to keep or send is wanted: autocad_export.
    """
    if area == "window" and (not corner1 or not corner2):
        raise AutocadError("area='window' needs both corner1 and corner2 as [x, y].")
    if detail is not None and detail > 1 and area == "view":
        raise AutocadError(
            "detail works with area='extents' or area='window': the current "
            "view has no corners to split. Give the window's corners instead."
        )

    folder = tempfile.mkdtemp(prefix="heron-preview-")
    target = os.path.join(folder, "preview.png")

    def work() -> dict[str, Any]:
        return _plot_png(get_doc(), target, area, corner1, corner2, width_px, detail)

    try:
        info = await run(work)
        if not os.path.isfile(target) or os.path.getsize(target) == 0:
            raise AutocadError(
                f"AutoCAD did not write the preview. Check that '{PNG_PLOTTER}' "
                "is listed in AutoCAD's PLOTTERMANAGER folder."
            )
        images = [Image(data=_read_png(target), format="png")]
        written = []
        for part in info.get("detail", []):
            path = _detail_path(target, part["picture"])
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                part["picture"] = len(images) + 1
                images.append(Image(data=_read_png(path), format="png"))
                written.append(part)
            else:
                info.setdefault("detail_missing", []).append(part["part"])
        if "detail" in info:
            info["detail"] = written
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return [*images, dumps(info)]


def _read_png(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()
