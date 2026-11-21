"""Tiled model viewports (VPORTS on the Model tab), worked out without AutoCAD.

Which AcViewportSplitType number each layout is, and a plain description of
what AutoCAD actually built, read from each tile's corners (fractions of the
drawing area, 0 to 1). The tool compares the two, so a split that came out
another way is said, not hidden (D-111).
"""

from __future__ import annotations

from collections.abc import Sequence

# AcViewportSplitType, read from Autodesk's interop assembly (AutoCAD 2025):
# acViewport2Horizontal = 0 ... acViewport4 = 8. None = one viewport, no split.
LAYOUTS: dict[str, int | None] = {
    "one": None,
    "two_horizontal": 0,
    "two_vertical": 1,
    "three_left": 2,
    "three_right": 3,
    "three_horizontal": 4,
    "three_vertical": 5,
    "three_above": 6,
    "three_below": 7,
    "four": 8,
}

# What each layout looks like on screen, in the words describe() uses.
EXPECTED: dict[str, str] = {
    "one": "one viewport",
    "two_horizontal": "two, one above the other",
    "two_vertical": "two, side by side",
    "three_left": "three, the big one on the left",
    "three_right": "three, the big one on the right",
    "three_horizontal": "three, one above another",
    "three_vertical": "three, side by side",
    "three_above": "three, the big one on top",
    "three_below": "three, the big one at the bottom",
    "four": "four, two by two",
}

_COUNTS = {"one": 1, "two": 2, "three": 3, "four": 4}
TILE_COUNT: dict[str, int] = {name: _COUNTS[name.split("_")[0]] for name in LAYOUTS}

_EPS = 1e-6

Corner = Sequence[float]


def _box(tile: tuple[Corner, Corner]) -> tuple[float, float, float, float]:
    (x1, y1), (x2, y2) = (tile[0][0], tile[0][1]), (tile[1][0], tile[1][1])
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _full_height(box: tuple[float, float, float, float]) -> bool:
    return box[1] <= _EPS and box[3] >= 1 - _EPS


def _full_width(box: tuple[float, float, float, float]) -> bool:
    return box[0] <= _EPS and box[2] >= 1 - _EPS


def _area(box: tuple[float, float, float, float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def describe(tiles: Sequence[tuple[Corner, Corner]]) -> str:
    """The tiles in the words of EXPECTED, or a plain count when it is none of them."""
    boxes = [_box(t) for t in tiles]
    n = len(boxes)
    if n == 1:
        return "one viewport"
    if n == 2:
        if all(_full_height(b) for b in boxes):
            return "two, side by side"
        if all(_full_width(b) for b in boxes):
            return "two, one above the other"
    if n == 3:
        areas = [_area(b) for b in boxes]
        big = max(range(3), key=lambda i: areas[i])
        rest = [b for i, b in enumerate(boxes) if i != big]
        if all(abs(a - areas[0]) <= _EPS for a in areas):
            if all(_full_height(b) for b in boxes):
                return "three, side by side"
            if all(_full_width(b) for b in boxes):
                return "three, one above another"
        else:
            b = boxes[big]
            if _full_height(b):
                return "three, the big one on the left" if all(b[0] < r[0] for r in rest) else "three, the big one on the right"
            if _full_width(b):
                return "three, the big one on top" if all(b[1] > r[1] for r in rest) else "three, the big one at the bottom"
    if n == 4 and all(abs(_area(b) - 0.25) <= _EPS for b in boxes):
        return "four, two by two"
    return f"{n} viewports"
