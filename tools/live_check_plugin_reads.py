"""Reads the plug-in does in one go: block counts, lengths and texts, block attributes (groups AU, BB, BE).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Nothing here is measured. Every row's pass is that the plug-in's answer is the same
text, to the last digit, as the same call to a second server started with
``--no-bridge``, with the plug-in's log showing the operation; the runner starts no
second server and never switches the plug-in off, and a one-sided check of the
numbers would write PASS over a comparison it did not make. The rest need an older
plug-in installed, a drawing of thousands of objects with both times written down, a
real project plan, Excel, or Ctrl+Z pressed by hand. Their reasons are below.
"""

from __future__ import annotations

from live_common import Check

CHECKS: tuple[Check, ...] = ()

_OVER_COM = (
    "compares the plug-in's answer, character by character, with the same call to a second server started with "
    "--no-bridge, and reads the plug-in's log; the runner starts no second server"
)
_OLD = "needs plug-in 1.8.1 installed instead of the current one, and the add-in log read"
_TIMED = "needs a drawing with thousands of objects and both times written down, and " + _OVER_COM
_UNDO = "needs a line drawn by hand and Ctrl+Z pressed by hand, to see the read left no undo step"

BY_EYE: dict[str, str] = {
    "AU1": "needs a real MEP plan with dynamic valves, and " + _OVER_COM,
    "AU2": "needs a real MEP plan, and " + _OVER_COM,
    "AU3": "needs a drawing with blocks inside blocks, and " + _OVER_COM,
    "AU4": "needs a drawing with an xref and a dynamic block, and " + _OVER_COM,
    "AU5": _OLD,
    "AU6": _TIMED,
    "AU7": "needs a MINSERT, a block on a sheet and an xref, and " + _OVER_COM,
    "AU8": _UNDO,
    "BB1": "needs a real MEP plan, and " + _OVER_COM,
    "BB2": "needs one of each curve type drawn by hand (an old-style 2D polyline among them), and " + _OVER_COM,
    "BB3": "needs fit-point, control-point and rational splines and ellipses drawn by hand, and " + _OVER_COM,
    "BB4": "needs a layer of mixed objects, and " + _OVER_COM,
    "BB5": "needs a surface and a mesh, and " + _OVER_COM,
    "BB6": "needs a plan with formatted mtext and a changed dynamic block, and " + _OVER_COM,
    "BB7": "needs the same plan, and " + _OVER_COM,
    "BB8": "needs blocks with a multiline and a constant attribute, and what COM's GetAttributes gives is written down",
    "BB9": "needs a block whose attribute definitions were deleted after insert, and " + _OVER_COM,
    "BB10": _OLD + "; then a plan with 20,000 texts and 20,000 curves timed both ways, and Ctrl+Z pressed by hand",
    "BE1": "needs a real drawing with title blocks on several layouts, and " + _OVER_COM,
    "BE2": "needs a changed dynamic block and a block name with lower-case letters, and " + _OVER_COM,
    "BE3": "needs the drawing saved and two workbooks compared, and " + _OVER_COM,
    "BE4": "writes attributes on a copy of a real drawing with and without --no-bridge, and Ctrl+Z is pressed by hand",
    "BE5": "needs two cells edited in Excel and saved, and " + _OVER_COM,
    "BE6": "needs blocks with a multiline and a constant attribute, and what COM's GetAttributes gives is written down",
    "BE7": "needs a block with only constant attribute definitions and one whose definitions were deleted, and what COM's HasAttributes says is written down",
    "BE8": "needs a block with an invisible attribute, and " + _OVER_COM,
    "BE9": _OLD + "; then a plan with 2,000 tagged blocks timed both ways, and Ctrl+Z pressed by hand",
    "BE10": "needs a title block whose attributes hold fields, and " + _OVER_COM,
    "BJ1": "needs a real drawing with layers to merge in every place an object can be, and " + _OVER_COM,
    "BJ2": "needs Keep or Discard answered by hand, a second copy of the drawing, and " + _OVER_COM,
    "BJ3": "needs Ctrl+Z pressed by hand and the layers looked at in the layer manager",
    "BJ4": "needs a viewport freeze and a layer filter set up by hand, and which layers stay written down both ways",
    "BJ5": "needs a proxy object from another application, and a second server started with --no-bridge",
    "BJ6": "needs a block whose attribute definitions were deleted by hand, and what COM's read lists written down",
    "BJ7": _OLD + "; then a plan with 20,000 objects on the old layers merged and timed both ways",
}
