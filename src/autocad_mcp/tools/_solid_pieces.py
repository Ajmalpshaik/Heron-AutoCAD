"""Draw a 3D shape's pieces as solids, over COM (D-94).

``acad/shapes3d.py`` describes every piece of a duct run or a pipe spool in
its own frame, where AutoCAD makes it without doubt, plus the matrix that puts
it in place. This module does the AutoCAD part and nothing else:

1. Make the piece where its frame says: a box or a cylinder standing on the
   origin, or a profile at the origin revolved round an axis through
   (radius, 0, 0) along +Y.
2. Cut its hole (a hollow duct or pipe, a flange's bore and bolt holes).
3. TransformBy the piece's matrix.
4. Check the box AutoCAD gives against the box the piece should fill, so a
   piece that landed anywhere else says so instead of looking finished.

All of it runs inside one undo mark. If AutoCAD refuses any piece, every
piece already made is taken out again, so a refusal leaves nothing behind.
"""

from __future__ import annotations

import math
from typing import Any

import pythoncom
from win32com.client import VARIANT

from ..acad import shapes3d
from ..acad.tables import apply_properties
from ..core.connection import get_doc, get_space, require_idle
from ..core.errors import AutocadError, com_message
from ..core.registry import to_aci, undo_mark
from ..core.variants import apoint, double_array, object_array, point_to_list

# AcBooleanType, as autocad_solid_boolean uses them.
UNION, SUBTRACT = 0, 2
# A piece may sit this share of its own size off the box it should fill:
# enough for AutoCAD's loose box round a curved face, far too little to hide a
# piece that went the wrong way.
BOX_TOLERANCE = 0.05


def matrix_variant(rows: Any) -> VARIANT:
    """A 4 x 4 matrix as the two-dimensional array of doubles TransformBy takes."""
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(tuple(float(v) for v in row) for row in rows))


def own_box(piece: dict[str, Any]) -> tuple[list[float], list[float]]:
    """The box a piece fills in its own frame, before it is moved."""
    return shapes3d.expected_box({**piece, "matrix": [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]})


def box_off(actual: tuple[list[float], list[float]], expected: tuple[list[float], list[float]]) -> float:
    """How far AutoCAD's box is from the expected one, as a share of the expected one's size."""
    low, high = expected
    size = math.dist(low, high) or 1.0
    worst = max(abs(a - e) for a, e in zip(list(actual[0]) + list(actual[1]), list(low) + list(high), strict=True))
    return worst / size


def _try_delete(entity: Any) -> None:
    try:
        entity.Delete()
    except BaseException:  # noqa: BLE001 - scaffolding that will not go is harmless
        pass


def _profile_curve(space: Any, profile: dict[str, Any]) -> Any:
    """The profile as one closed curve, flat at the origin (world XY, where COM draws it)."""
    if profile["kind"] == "circle":
        return space.AddCircle(apoint(0.0, 0.0, 0.0), float(profile["radius"]))
    outline = shapes3d.profile_outline(profile)
    curve = space.AddLightWeightPolyline(double_array([v for point in outline for v in point]))
    curve.Closed = True
    return curve


def _revolve(space: Any, profile: dict[str, Any], piece: dict[str, Any]) -> Any:
    """A bend: the profile revolved round the axis through (R, 0, 0) along +Y, towards +Z."""
    radius, angle = float(piece["radius"]), math.radians(float(piece["angle"]))
    curve = _profile_curve(space, profile)
    try:
        made = space.AddRegion(object_array([curve]))
        regions = [r for r in (list(made) if isinstance(made, tuple) else [made]) if r is not None]
        if not regions:
            raise AutocadError("AutoCAD made no region from a bend's profile.")
        try:
            solid = space.AddRevolvedSolid(regions[0], apoint(radius, 0.0, 0.0), apoint(0.0, 1.0, 0.0), angle)
            # The bend must sweep forward (up +Z, in its own frame). If AutoCAD
            # turned the other way round the axis, make it again the other way.
            low_z = float(solid.GetBoundingBox()[0][2])
            expected_low, expected_high = own_box({**piece, "profile": profile})
            if low_z < expected_low[2] - 0.25 * (expected_high[2] - expected_low[2]) - 1e-6:
                _try_delete(solid)
                solid = space.AddRevolvedSolid(regions[0], apoint(radius, 0.0, 0.0), apoint(0.0, -1.0, 0.0), angle)
        finally:
            for region in regions:
                _try_delete(region)
    finally:
        _try_delete(curve)
    return solid


def _canonical(space: Any, piece: dict[str, Any], profile: dict[str, Any]) -> Any:
    """One solid of the piece, standing in its own frame."""
    length = float(piece.get("length", 0.0))
    if piece["solid"] == "revolve":
        return _revolve(space, profile, piece)
    centre = apoint(0.0, 0.0, length / 2.0)
    if piece["solid"] == "box" or profile["kind"] == "rectangle":
        return space.AddBox(centre, float(profile["width"]), float(profile["height"]), length)
    return space.AddCylinder(centre, float(profile["radius"]), length)


def _piece(space: Any, piece: dict[str, Any]) -> Any:
    """One piece made, hollowed, drilled and put in place."""
    solid = _canonical(space, piece, piece["profile"])
    try:
        if piece.get("hole"):
            solid.Boolean(SUBTRACT, _canonical(space, piece, piece["hole"]))
        thickness = float(piece.get("length", 0.0))
        for hole in piece.get("bolt_holes", []):
            drill = space.AddCylinder(apoint(float(hole["x"]), float(hole["y"]), thickness / 2.0),
                                      float(hole["radius"]), thickness)
            solid.Boolean(SUBTRACT, drill)
        solid.TransformBy(matrix_variant(piece["matrix"]))
    except BaseException:
        _try_delete(solid)
        raise
    return solid


def draw_pieces(plan: dict[str, Any]) -> dict[str, Any]:
    """Every piece of a 3D shape into model space, on the COM worker thread."""
    style = plan.get("style") or {}
    layer, centre_layer = style.get("layer"), style.get("centreline_layer")
    aci = to_aci(style.get("color"))
    doc = get_doc()
    require_idle(doc)
    space = get_space(doc, "model")
    made: list[tuple[dict[str, Any], Any]] = []
    notes: dict[str, Any] = {}
    with undo_mark(doc):
        try:
            for piece in plan["pieces"]:
                made.append((piece, _piece(space, piece)))
        except BaseException as exc:  # noqa: BLE001 - every refusal is answered the same way
            for _, solid in made:
                _try_delete(solid)
            where = len(made)
            part = plan["pieces"][where]["part"] if where < len(plan["pieces"]) else "piece"
            raise AutocadError(
                f"AutoCAD would not make {part} {where} of the {plan['shape']} ({com_message(exc)}). "
                "The pieces already made were taken out again, so nothing was left in the drawing. "
                "Check this is not AutoCAD LT, which has no solids."
            ) from exc
        rows: list[dict[str, Any]] = []
        off: list[str] = []
        for piece, solid in made:
            notes.update(apply_properties(doc, solid, layer, aci, None))
            row: dict[str, Any] = {"index": piece["index"], "part": piece["part"], "handle": str(solid.Handle)}
            for key in ("length", "angle", "radius"):
                if key in piece:
                    row[key] = piece[key]
            try:
                low, high = solid.GetBoundingBox()
                actual = (point_to_list(low), point_to_list(high))
                if box_off(actual, shapes3d.expected_box(piece)) > BOX_TOLERANCE:
                    off.append(f"{piece['part']} {piece['index']}")
            except BaseException:  # noqa: BLE001 - an unread box is not a wrong one
                pass
            rows.append(row)
        handles = [r["handle"] for r in rows]
        joined = None
        if plan.get("join") and len(made) > 1:
            first = made[0][1]
            try:
                for _, other in made[1:]:
                    first.Boolean(UNION, other)
                joined = str(first.Handle)
            except BaseException as exc:  # noqa: BLE001 - the pieces stay; say the join failed
                notes["join_warning"] = (
                    f"The pieces were made but AutoCAD would not join them all into one ({com_message(exc)}); "
                    "they are separate solids. autocad_solid_boolean(operation='union') can try again."
                )
        centreline = None
        if centre_layer:
            flat = [v for point in plan["points"] for v in point]
            line = space.Add3DPoly(double_array(flat))
            notes.update(apply_properties(doc, line, centre_layer, aci, None))
            centreline = str(line.Handle)

    result: dict[str, Any] = {
        "shape": plan["shape"],
        "created": len(rows) if joined is None else 1,
        "pieces": rows,
        "handles": [joined] if joined else handles,
        "centreline_length": plan["centreline_length"],
        "verified": not off,
    }
    for key in ("pipe_cut_lengths", "pipe_total", "elbows", "bends", "elbow_radius"):
        if key in plan:
            result[key] = plan[key]
    if joined:
        result["joined_into"] = joined
    if centreline:
        result["centreline"] = centreline
    result.update(notes)
    if off:
        result["warning"] = (
            f"{', '.join(off)} did not land where the route puts it (its box is more than "
            f"{BOX_TOLERANCE:.0%} off). Look at it with autocad_set_3d_view and autocad_preview before using it."
        )
    return result
