"""Sheets: paper sizes, scales, frames, and where a viewport goes on the paper.

Laying out a sheet is arithmetic a drafter does in their head and gets right
every time: the paper is 420 x 297, the frame leaves 20 on the binding edge and
10 elsewhere, the title block sits in the bottom right corner, the viewport
fills what is left, and at 1:50 a 15 m room needs 300 mm of paper.

All of that is here as plain functions over plain numbers, so it is tested
without AutoCAD and the tools only have to hand the answers to COM.

Paper is always in **millimetres** in this module, and always listed
**landscape** (width >= height); ``paper_size`` turns it for a portrait sheet.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

Box = tuple[float, float, float, float]  # min x, min y, max x, max y

MM_PER_INCH = 25.4

# Sheet sizes, landscape, in millimetres. ISO A from ISO 216; ANSI and ARCH
# converted from their inch sizes so one table serves both kinds of drawing.
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A0": (1189.0, 841.0),
    "A1": (841.0, 594.0),
    "A2": (594.0, 420.0),
    "A3": (420.0, 297.0),
    "A4": (297.0, 210.0),
    "A5": (210.0, 148.0),
    "ANSI A": (11.0 * MM_PER_INCH, 8.5 * MM_PER_INCH),
    "ANSI B": (17.0 * MM_PER_INCH, 11.0 * MM_PER_INCH),
    "ANSI C": (22.0 * MM_PER_INCH, 17.0 * MM_PER_INCH),
    "ANSI D": (34.0 * MM_PER_INCH, 22.0 * MM_PER_INCH),
    "ANSI E": (44.0 * MM_PER_INCH, 34.0 * MM_PER_INCH),
    "ARCH A": (12.0 * MM_PER_INCH, 9.0 * MM_PER_INCH),
    "ARCH B": (18.0 * MM_PER_INCH, 12.0 * MM_PER_INCH),
    "ARCH C": (24.0 * MM_PER_INCH, 18.0 * MM_PER_INCH),
    "ARCH D": (36.0 * MM_PER_INCH, 24.0 * MM_PER_INCH),
    "ARCH E": (48.0 * MM_PER_INCH, 36.0 * MM_PER_INCH),
    "ARCH E1": (42.0 * MM_PER_INCH, 30.0 * MM_PER_INCH),
}

# ISO 5457: 20 mm on the binding (left) edge, 10 mm on the other three, and the
# title block in the bottom right corner of the drawing space.
ISO_MARGINS_MM = (20.0, 10.0, 10.0, 10.0)  # left, bottom, right, top

# The scales a drafter actually puts on a sheet. Used to snap a fitted scale to
# a real one rather than printing "1:37.4".
STANDARD_SCALES: tuple[str, ...] = (
    "10:1", "5:1", "2:1", "1:1",
    "1:2", "1:2.5", "1:5", "1:10", "1:20", "1:25", "1:50", "1:75", "1:100",
    "1:125", "1:150", "1:200", "1:250", "1:500", "1:750", "1:1000",
    "1:1250", "1:2000", "1:2500", "1:5000",
)

_SCALE_TEXT = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*[:/=]\s*([0-9]*\.?[0-9]+)\s*$")

# AutoCAD's canonical media names carry their own dimensions, e.g.
# ISO_full_bleed_A3_(420.00_x_297.00_MM) or ANSI_A_(11.00_x_8.50_Inches).
_MEDIA_SIZE = re.compile(
    r"\(\s*([0-9]*\.?[0-9]+)\s*[_ ]x[_ ]\s*([0-9]*\.?[0-9]+)\s*[_ ]?([A-Za-z]+)\s*\)"
)


def media_dimensions(media: str) -> tuple[float, float] | None:
    """The sheet size read out of a canonical media name, in that sheet's own units.

    A layout whose plotter cannot be asked for its paper size still knows which
    sheet it is set to, and the name says how big that is. A pixel size (a
    raster preview device) is not a sheet, so it comes back as None.
    """
    match = _MEDIA_SIZE.search(str(media or ""))
    if match is None:
        return None
    if match.group(3).lower().startswith("pixel"):
        return None
    width, height = float(match.group(1)), float(match.group(2))
    if width <= 0.0 or height <= 0.0:
        return None
    return (width, height)


def parse_scale(value: str | float) -> float:
    """A scale as paper units per drawing unit.

    Accepts the way every drafter writes it - "1:50", "1/50", "1=50", "1:1",
    an enlargement "2:1" - and a bare ratio (0.02) for the rare odd scale.
    1:50 comes back as 0.02: multiply a drawing length by it to get paper.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ratio = float(value)
    else:
        text = str(value).strip().lower().removeprefix("scale").strip()
        match = _SCALE_TEXT.match(text)
        if match:
            paper, drawing = float(match.group(1)), float(match.group(2))
            if drawing == 0.0:
                raise ValueError(f"'{value}' divides by zero; a scale needs a number on both sides")
            ratio = paper / drawing
        else:
            try:
                ratio = float(text)
            except ValueError:
                raise ValueError(
                    f"'{value}' is not a scale this server understands. Write it the way it goes "
                    "on the sheet - '1:50', '1:100', '2:1' - or as a plain ratio like 0.02."
                ) from None
    if not math.isfinite(ratio) or ratio <= 0.0:
        raise ValueError(f"'{value}' is not a usable scale; it must come out above zero")
    return ratio


def parse_typed_scale(value: str | float) -> float:
    """parse_scale for a scale the modeller typed: a bare number above 1 is refused.

    A bare number is a ratio, so 10 reads as 10:1 - but a modeller who types 10
    almost always means 1:10, and the wrong reading makes every dimension ten
    times too small. Rather than guess, it asks for the scale as on the sheet.
    Inside the server a 2:1 detail travels as 2.0, so parse_scale keeps reading it.
    """
    ratio = parse_scale(value)
    bare = isinstance(value, (int, float)) or not _SCALE_TEXT.match(
        str(value).strip().lower().removeprefix("scale").strip()
    )
    if bare and ratio > 1.0:
        size = _tidy(ratio)
        raise ValueError(
            f"'{value}' could mean 1:{size} or {size}:1. Write the scale the way it goes on "
            f"the sheet: '1:{size}', or '{size}:1' for an enlargement."
        )
    return ratio


def scale_text(ratio: float) -> str:
    """A ratio back as the text that belongs on the sheet: 0.02 -> '1:50'."""
    ratio = float(ratio)
    if ratio <= 0.0:
        raise ValueError("a scale must be above zero")
    if ratio >= 1.0:
        enlarge = ratio
        return f"{_tidy(enlarge)}:1"
    return f"1:{_tidy(1.0 / ratio)}"


def _tidy(number: float) -> str:
    rounded = round(number, 4)
    if abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:g}"


def dim_scale(ratio: float) -> float:
    """DIMSCALE for a drawing scale: 1:50 -> 50, so 2.5 mm text plots at 2.5 mm."""
    return 1.0 / parse_scale(ratio)


def text_height(paper_mm: float, ratio: float | str) -> float:
    """Model-space text height for a paper height: 2.5 mm at 1:10 -> 25."""
    return float(paper_mm) / parse_scale(ratio)


def paper_size(name: str, orientation: str = "landscape") -> tuple[float, float]:
    """A named sheet as (width, height) in millimetres, turned for the orientation."""
    key = re.sub(r"[\s_-]+", " ", str(name)).strip().upper()
    key = {"A": "ANSI A", "B": "ANSI B", "C": "ANSI C", "D": "ANSI D", "E": "ANSI E"}.get(key, key)
    if key not in PAPER_SIZES_MM:
        raise ValueError(
            f"'{name}' is not a sheet size this server knows. Use one of: "
            + ", ".join(sorted(PAPER_SIZES_MM))
        )
    wide, tall = PAPER_SIZES_MM[key]
    if str(orientation).strip().lower() == "portrait":
        return (tall, wide)
    return (wide, tall)


def frame(
    width: float,
    height: float,
    margins: Sequence[float] | None = None,
) -> Box:
    """The drawing frame inside a sheet, as (x1, y1, x2, y2) from the paper's corner.

    ``margins`` is (left, bottom, right, top); it defaults to ISO 5457's
    20 mm binding edge and 10 mm elsewhere. One number is used on all four
    sides.
    """
    left, bottom, right, top = _four(margins if margins is not None else ISO_MARGINS_MM)
    if left + right >= width or bottom + top >= height:
        raise ValueError(
            f"margins of {left}/{bottom}/{right}/{top} leave no room on a "
            f"{_tidy(width)} x {_tidy(height)} sheet"
        )
    return (left, bottom, width - right, height - top)


def _four(values: Sequence[float]) -> tuple[float, float, float, float]:
    numbers = [float(v) for v in values]
    if len(numbers) == 1:
        return (numbers[0],) * 4  # type: ignore[return-value]
    if len(numbers) == 2:
        return (numbers[0], numbers[1], numbers[0], numbers[1])
    if len(numbers) == 4:
        return (numbers[0], numbers[1], numbers[2], numbers[3])
    raise ValueError("margins take 1, 2 or 4 numbers: all, (sides, ends), or (left, bottom, right, top)")


CORNERS = ("bottom-right", "bottom-left", "top-right", "top-left", "bottom-centre", "centre")


def corner_point(box: Box, corner: str = "bottom-right") -> tuple[float, float]:
    """A corner of a box, for anchoring a title block or a stamp."""
    x1, y1, x2, y2 = box
    places = {
        "bottom-right": (x2, y1),
        "bottom-left": (x1, y1),
        "top-right": (x2, y2),
        "top-left": (x1, y2),
        "bottom-centre": ((x1 + x2) / 2.0, y1),
        "centre": ((x1 + x2) / 2.0, (y1 + y2) / 2.0),
    }
    key = str(corner).strip().lower().replace("center", "centre").replace("_", "-")
    if key not in places:
        raise ValueError(f"'{corner}' is not a corner. Use one of: {', '.join(CORNERS)}.")
    return places[key]


def inset(box: Box, gap: float | Sequence[float]) -> Box:
    """A box pulled in by a gap, for a viewport that must not touch the frame."""
    left, bottom, right, top = _four([gap] if isinstance(gap, (int, float)) else gap)
    x1, y1, x2, y2 = box
    out = (x1 + left, y1 + bottom, x2 - right, y2 - top)
    if out[2] <= out[0] or out[3] <= out[1]:
        raise ValueError(f"a gap of {_tidy(left)} leaves no room inside the frame")
    return out


def reserve(box: Box, side: str, size: float) -> Box:
    """A box with a strip taken off one side, for the title block or a note column."""
    x1, y1, x2, y2 = box
    size = float(size)
    sides = {
        "right": (x1, y1, x2 - size, y2),
        "left": (x1 + size, y1, x2, y2),
        "bottom": (x1, y1 + size, x2, y2),
        "top": (x1, y1, x2, y2 - size),
    }
    key = str(side).strip().lower()
    if key not in sides:
        raise ValueError(f"'{side}' is not a side. Use right, left, bottom or top.")
    out = sides[key]
    if out[2] <= out[0] or out[3] <= out[1]:
        raise ValueError(f"reserving {_tidy(size)} on the {key} leaves no drawing space")
    return out


def centre_of(box: Box) -> tuple[float, float]:
    """The middle of a box."""
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def size_of(box: Box) -> tuple[float, float]:
    """A box's width and height."""
    x1, y1, x2, y2 = box
    return (x2 - x1, y2 - y1)


def model_window(
    centre: Sequence[float],
    paper_width: float,
    paper_height: float,
    ratio: float | str,
) -> Box:
    """The drawing-space area a viewport shows, from its paper size and scale.

    A 180 x 120 mm viewport at 1:50 looks at 9000 x 6000 drawing units. Getting
    this exactly right is what makes the viewport come out at the scale asked
    rather than near it: the window handed to AutoCAD has the viewport's own
    proportions, so nothing is added to fit.
    """
    scale = parse_scale(ratio)
    half_w = float(paper_width) / scale / 2.0
    half_h = float(paper_height) / scale / 2.0
    cx, cy = float(centre[0]), float(centre[1])
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def fit_scale(
    model_box: Box,
    paper_width: float,
    paper_height: float,
    scales: Sequence[str] = STANDARD_SCALES,
) -> tuple[str, float]:
    """The largest standard scale at which a drawing area still fits the paper.

    Returns (text, ratio) - ('1:50', 0.02) - so the sheet gets a real scale and
    the same number can be stamped under the view title. Raises when even the
    smallest listed scale cannot fit it.
    """
    width, height = size_of(model_box)
    if width <= 0.0 or height <= 0.0:
        raise ValueError("that drawing area has no size, so no scale fits it")
    ordered = sorted(
        ((text, parse_scale(text)) for text in scales), key=lambda pair: pair[1], reverse=True
    )
    for text, ratio in ordered:
        if width * ratio <= float(paper_width) + 1e-9 and height * ratio <= float(paper_height) + 1e-9:
            return text, ratio
    smallest = ordered[-1][0]
    raise ValueError(
        f"a {_tidy(width)} x {_tidy(height)} area does not fit a "
        f"{_tidy(paper_width)} x {_tidy(paper_height)} viewport even at {smallest}. "
        "Use a bigger sheet, a smaller area, or give the scale yourself."
    )


def grid_boxes(box: Box, columns: int, rows: int, gap: float = 0.0) -> list[Box]:
    """A box split into a grid of equal boxes, reading left to right, top down.

    For a sheet of several views at the same scale: four details on one A1, or
    a plan beside an elevation.
    """
    if columns < 1 or rows < 1:
        raise ValueError("a grid needs at least one column and one row")
    x1, y1, x2, y2 = box
    width = (x2 - x1 - gap * (columns - 1)) / columns
    height = (y2 - y1 - gap * (rows - 1)) / rows
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"{columns} x {rows} with a gap of {_tidy(gap)} leaves no room in that box")
    out = []
    for row in range(rows):
        top = y2 - row * (height + gap)
        for column in range(columns):
            left = x1 + column * (width + gap)
            out.append((left, top - height, left + width, top))
    return out


def sheet_plan(
    size: str = "A3",
    orientation: str = "landscape",
    margins: Sequence[float] | None = None,
    title_block_width: float | None = None,
    gap: float = 0.0,
) -> dict[str, Any]:
    """Everything about one sheet, worked out once: paper, frame, drawing space.

    ``title_block_width`` reserves a strip on the right for the title block, so
    the drawing space a viewport gets never runs under it.
    """
    width, height = paper_size(size, orientation)
    outline = frame(width, height, margins)
    space = outline
    if title_block_width:
        space = reserve(space, "right", float(title_block_width))
    if gap:
        space = inset(space, gap)
    return {
        "paper": [round(width, 4), round(height, 4)],
        "orientation": "portrait" if height > width else "landscape",
        "frame": [round(v, 4) for v in outline],
        "drawing_space": [round(v, 4) for v in space],
        "title_block_at": [round(v, 4) for v in corner_point(outline, "bottom-right")],
        "drawing_space_size": [round(v, 4) for v in size_of(space)],
    }


# ---------------------------------------------------------------------------
# A layout's paper, from the numbers AutoCAD gives (COM or the plug-in)
# ---------------------------------------------------------------------------

PLOT_ROTATIONS_DEGREES = (0, 90, 180, 270)


def paper_info(
    size: Sequence[float],
    margins: Sequence[float] | None = None,
    media: str = "",
    plotter: str = "",
    rotation_degrees: int = 0,
) -> dict[str, Any]:
    """The facts about a layout's sheet, in the one shape every sheet tool reads.

    ``size`` is the sheet (width, height); ``margins`` the unprintable strip on
    each side as (left, bottom, right, top). Paper-space (0, 0) is the lower
    left of the printable area, so the printable rectangle starts there and is
    the sheet less both margins.
    """
    width, height = float(size[0]), float(size[1])
    if width <= 0.0 or height <= 0.0:
        raise ValueError("a sheet with no size")
    left, bottom, right, top = (float(v) for v in (margins or (0.0, 0.0, 0.0, 0.0)))
    return {
        "media": str(media or ""),
        "plotter": str(plotter or ""),
        "paper": [round(width, 4), round(height, 4)],
        "margins": [round(left, 4), round(bottom, 4), round(right, 4), round(top, 4)],
        "printable": [0.0, 0.0, round(width - left - right, 4), round(height - bottom - top, 4)],
        "plot_rotation_degrees": int(rotation_degrees)
        if int(rotation_degrees) in PLOT_ROTATIONS_DEGREES
        else 0,
    }


def area_box(info: dict[str, Any], anchor: str = "printable") -> Box:
    """The rectangle to work inside: the printable area, or the whole sheet."""
    if str(anchor).strip().lower() == "paper":
        low_x, low_y, _, _ = info["margins"]
        width, height = info["paper"]
        # The printable area is inset by the lower-left margin, so the sheet
        # corner is that much below and to the left of paper-space (0, 0).
        return (-low_x, -low_y, width - low_x, height - low_y)
    return tuple(info["printable"])  # type: ignore[return-value]


def frame_in(area: Box, margins: Sequence[float] | None = None) -> Box:
    """The drawing frame inside an area, in the area's own coordinates."""
    outline = frame(*size_of(area), margins)
    return (outline[0] + area[0], outline[1] + area[1], outline[2] + area[0], outline[3] + area[1])


# ---------------------------------------------------------------------------
# A viewport clipped to an outline (#65)
# ---------------------------------------------------------------------------

MOST_CLIP_CORNERS = 500


def clip_outline(points: Sequence[Sequence[float]]) -> dict[str, Any]:
    """A clip outline checked and closed, with the box round it.

    VPCLIP takes any closed shape that does not cross itself. Corners are
    [x, y] on the paper; a last corner that repeats the first is dropped, and
    so is a corner given twice in a row. Returns {"points", "box", "area"};
    the viewport is made the size of the box and clipped to the outline.
    """
    clean: list[tuple[float, float]] = []
    for index, corner in enumerate(points or ()):
        if not isinstance(corner, (list, tuple)) or len(corner) < 2:
            raise ValueError(f"clip corner {index + 1} is not [x, y]")
        x, y = float(corner[0]), float(corner[1])
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f"clip corner {index + 1} is not a number")
        if clean and _same(clean[-1], (x, y)):
            continue
        clean.append((x, y))
    if len(clean) > 1 and _same(clean[0], clean[-1]):
        clean.pop()
    if len(clean) < 3:
        raise ValueError("a clip outline needs at least three different corners")
    if len(clean) > MOST_CLIP_CORNERS:
        raise ValueError(f"a clip outline takes at most {MOST_CLIP_CORNERS} corners")
    area = _signed_area(clean)
    if abs(area) < 1e-9:
        raise ValueError("that clip outline has no area: its corners are on one line")
    crossing = _first_crossing(clean)
    if crossing is not None:
        a, b = crossing
        raise ValueError(
            f"that clip outline crosses itself (side {a + 1} crosses side {b + 1}); "
            "AutoCAD clips only to an outline that does not"
        )
    box = (
        min(p[0] for p in clean),
        min(p[1] for p in clean),
        max(p[0] for p in clean),
        max(p[1] for p in clean),
    )
    return {
        "points": [[round(x, 6), round(y, 6)] for x, y in clean],
        "box": [round(v, 6) for v in box],
        "area": round(abs(area), 6),
    }


def _same(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9


def _signed_area(points: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for i, (x1, y1) in enumerate(points):
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _on_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> bool:
    return (
        min(a[0], b[0]) - 1e-9 <= p[0] <= max(a[0], b[0]) + 1e-9
        and min(a[1], b[1]) - 1e-9 <= p[1] <= max(a[1], b[1]) + 1e-9
    )


def _segments_meet(
    p1: tuple[float, float], p2: tuple[float, float], q1: tuple[float, float], q2: tuple[float, float]
) -> bool:
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    if ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and (
        (d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9)
    ):
        return True
    return (
        (abs(d1) <= 1e-9 and _on_segment(p1, q1, q2))
        or (abs(d2) <= 1e-9 and _on_segment(p2, q1, q2))
        or (abs(d3) <= 1e-9 and _on_segment(q1, p1, p2))
        or (abs(d4) <= 1e-9 and _on_segment(q2, p1, p2))
    )


def _first_crossing(points: Sequence[tuple[float, float]]) -> tuple[int, int] | None:
    """The first two sides of a closed outline that meet, other than neighbours at their shared corner."""
    count = len(points)
    for i in range(count):
        a1, a2 = points[i], points[(i + 1) % count]
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue  # neighbours share a corner
            b1, b2 = points[j], points[(j + 1) % count]
            if _segments_meet(a1, a2, b1, b2):
                return i, j
    return None


# ---------------------------------------------------------------------------
# A drawing list made into sheets (#66)
# ---------------------------------------------------------------------------

MOST_SHEETS = 200
_LAYOUT_BAD = set('<>/\\":;?*|,=`')


def plan_sheet_set(
    rows: Sequence[dict[str, Any]],
    existing_layouts: Sequence[str] = (),
    saved_views: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """A drawing list checked and turned into one plan per sheet.

    Each row is a sheet: ``number`` (the layout name, e.g. 'M-101'), an
    optional ``title``, ``scale`` and where its viewport looks — a saved
    ``view``, ``corner1``/``corner2``, ``handles`` or a ``centre`` (which needs
    a scale). A row with none of those gets a sheet and a title block but no
    viewport (a cover or a legend sheet). Every problem in the list is said at
    once, before anything is made: a name used twice or already in the drawing,
    a scale nobody can read, a view the drawing does not have.
    """
    if not rows:
        raise ValueError("the drawing list is empty: give one row per sheet")
    if len(rows) > MOST_SHEETS:
        raise ValueError(f"one call makes at most {MOST_SHEETS} sheets; split the list")
    taken = {str(name).strip().lower() for name in existing_layouts}
    views = None if saved_views is None else {str(v).strip().lower(): str(v) for v in saved_views}
    problems: list[str] = []
    seen: dict[str, int] = {}
    plans: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        number = str(row.get("number") or "").strip()
        label = f"row {index}" + (f" ({number})" if number else "")
        if not number:
            problems.append(f"{label} has no sheet number")
            continue
        if any(ch in _LAYOUT_BAD for ch in number) or len(number) > 255:
            problems.append(f"{label}: '{number}' cannot be a layout name (no < > / \\ \" : ; ? * | , = `)")
        if number.lower() == "model":
            problems.append(f"{label}: 'Model' is model space, not a sheet")
        key = number.lower()
        if key in seen:
            problems.append(f"{label}: sheet number '{number}' is also row {seen[key]}")
        else:
            seen[key] = index
        if key in taken:
            problems.append(f"{label}: the drawing already has a layout called '{number}'")

        ratio: float | None = None
        scale = row.get("scale")
        if scale not in (None, ""):
            try:
                ratio = parse_typed_scale(scale)
            except ValueError as exc:
                problems.append(f"{label}: {exc}")

        aims = [k for k in ("view", "corner1", "handles", "centre") if row.get(k) not in (None, "", [])]
        if len(aims) > 1:
            problems.append(f"{label}: give one of view, corner1/corner2, handles or centre, not {' and '.join(aims)}")
        aim = aims[0] if aims else None
        if aim == "corner1" and not row.get("corner2"):
            problems.append(f"{label}: corner1 needs corner2")
        if row.get("corner2") and not row.get("corner1"):
            problems.append(f"{label}: corner2 needs corner1")
        if aim == "centre" and ratio is None:
            problems.append(f"{label}: a centre needs a scale, or give an area to fit instead")
        view = None
        if aim == "view":
            view = str(row["view"]).strip()
            if views is not None and view.lower() not in views:
                problems.append(f"{label}: this drawing has no saved view called '{view}'")
            elif views is not None:
                view = views[view.lower()]

        attributes = row.get("attributes") or {}
        if not isinstance(attributes, dict):
            problems.append(f"{label}: attributes must be tag: value pairs")
            attributes = {}
        plans.append(
            {
                "number": number,
                "title": str(row.get("title") or "").strip(),
                "scale": scale_text(ratio) if ratio is not None else None,
                "scale_ratio": ratio,
                "aim": aim,
                "view": view,
                "corner1": row.get("corner1"),
                "corner2": row.get("corner2"),
                "handles": row.get("handles"),
                "centre": row.get("centre"),
                "twist": row.get("twist"),
                "paper_size": row.get("paper_size"),
                "orientation": row.get("orientation"),
                "attributes": {str(k): str(v) for k, v in attributes.items()},
            }
        )
    if problems:
        raise ValueError("the drawing list has problems, nothing was made: " + "; ".join(problems) + ".")
    return plans


def title_block_values(
    plan_row: dict[str, Any],
    common: dict[str, str] | None,
    number_tag: str | None,
    title_tag: str | None,
    scale_tag: str | None,
    fitted_scale: str | None = None,
) -> dict[str, str]:
    """The attributes one sheet's title block gets: the common ones, then its number, title and scale, then its own."""
    values = {str(k).strip().upper(): str(v) for k, v in (common or {}).items()}
    if number_tag:
        values[number_tag.strip().upper()] = plan_row["number"]
    if title_tag and plan_row.get("title"):
        values[title_tag.strip().upper()] = plan_row["title"]
    scale = plan_row.get("scale") or fitted_scale
    if scale_tag and scale:
        values[scale_tag.strip().upper()] = scale
    values.update({str(k).strip().upper(): str(v) for k, v in (plan_row.get("attributes") or {}).items()})
    return values
