"""Dimensioning a run of features, and the centre marks that go with it.

``autocad_add_dimension`` does one dimension at a time, which is right for one
dimension. A real drawing wants a *run*: eight dimensions along a wall, all on
one line, all at the same offset, in order, with an overall above them. Done one
call at a time that is eight calls and eight chances for the offset to drift.

So ``autocad_dimension_run`` takes the feature points and lays the whole run
out: a chain (AutoCAD's Continue), a baseline set stacked clear of each other,
an overall, or ordinates from a datum. The arithmetic - sorting the points,
working out each dimension line's offset, placing the text - is plain functions
at the top of this file and tested without AutoCAD.

``autocad_add_centre_marks`` adds the cross a drawing office expects on every
circle and arc. There is no Automation call for one, so they are drawn as
lines, which also means they come out on whatever layer you ask for.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..acad.entities import resolve_handles, short_type
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import ensure_layer
from ..acad.units import rad
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.quiet import QUIET_FIELD
from ..core.quiet import quiet as quieted
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ._shared import (
    COORDS_OPT,
    LAYER_OPT,
    current_ucs,
    not_flipped,
    point,
    ucs_for,
    world_angle,
    world_coords,
)
from .annotation_scales import make_new_annotative, require_plugin
from .batch import draw_operations

Point = tuple[float, float]
Mode = Literal["chain", "baseline", "overall", "ordinate"]
Axis = Literal["horizontal", "vertical", "aligned"]
EPS = 1e-9
MAX_POINTS = 200


# ---------------------------------------------------------------------------
# Laying the run out (pure: no AutoCAD below this line)
# ---------------------------------------------------------------------------


def _as_points(points: Sequence[Sequence[float]]) -> list[Point]:
    out: list[Point] = []
    for i, p in enumerate(points):
        if p is None or len(p) < 2:
            raise ValueError(f"point {i} is {p!r}; every point needs at least [x, y]")
        out.append((float(p[0]), float(p[1])))
    return out


def order_along(points: Sequence[Point], axis: str) -> list[Point]:
    """The points in the order the dimensions run, which is how a drafter reads them.

    Horizontal runs sort by X, vertical by Y, and an aligned run sorts along
    its own direction - the line from the first point to the farthest one.
    """
    pts = list(points)
    if axis == "horizontal":
        return sorted(pts, key=lambda p: (p[0], p[1]))
    if axis == "vertical":
        return sorted(pts, key=lambda p: (p[1], p[0]))
    if len(pts) < 2:
        return pts
    start = pts[0]
    far = max(pts, key=lambda p: math.dist(start, p))
    vx, vy = far[0] - start[0], far[1] - start[1]
    size = math.hypot(vx, vy)
    if size < EPS:
        return pts
    ux, uy = vx / size, vy / size
    return sorted(pts, key=lambda p: (p[0] - start[0]) * ux + (p[1] - start[1]) * uy)


def _normal(axis: str, points: Sequence[Point]) -> Point:
    """The unit direction the dimension lines are offset along.

    Horizontal dimensions move in Y, vertical ones in X, and an aligned run
    moves perpendicular to its own direction.
    """
    if axis == "horizontal":
        return (0.0, 1.0)
    if axis == "vertical":
        return (1.0, 0.0)
    if len(points) < 2:
        return (0.0, 1.0)
    vx, vy = points[-1][0] - points[0][0], points[-1][1] - points[0][1]
    size = math.hypot(vx, vy)
    if size < EPS:
        return (0.0, 1.0)
    return (-vy / size, vx / size)


def measure(p1: Point, p2: Point, axis: str) -> float:
    """What a dimension between two points will read, before AutoCAD measures it."""
    if axis == "horizontal":
        return abs(p2[0] - p1[0])
    if axis == "vertical":
        return abs(p2[1] - p1[1])
    return math.dist(p1, p2)


def plan_run(
    points: Sequence[Sequence[float]],
    mode: str = "chain",
    axis: str = "horizontal",
    offset: float = 0.0,
    spacing: float | None = None,
    include_overall: bool = False,
    sort: bool = True,
    datum: Sequence[float] | None = None,
) -> list[dict[str, Any]]:
    """Every dimension in a run, with its two points and where its text goes.

    Returns one entry per dimension: ``{"kind", "point1", "point2",
    "text_position", "measurement", "row"}``. ``row`` is which dimension line
    it sits on, counted out from the geometry, so a baseline set never puts two
    dimensions on top of each other.

    Raises ValueError, naming the problem, for anything that cannot be laid out.
    """
    if mode not in ("chain", "baseline", "overall", "ordinate"):
        raise ValueError("mode must be chain, baseline, overall or ordinate")
    if axis not in ("horizontal", "vertical", "aligned"):
        raise ValueError("axis must be horizontal, vertical or aligned")
    pts = _as_points(points)
    if len(pts) > MAX_POINTS:
        raise ValueError(f"{len(pts)} points is more than one run takes ({MAX_POINTS})")
    if mode == "ordinate":
        if not pts:
            raise ValueError("an ordinate run needs at least one point")
    elif len(pts) < 2:
        raise ValueError(f"a {mode} run needs at least two points, got {len(pts)}")

    if sort and mode != "ordinate":
        pts = order_along(pts, axis)
    nx, ny = _normal(axis, pts)
    gap = float(offset)
    step = float(spacing) if spacing is not None else abs(gap) or 1.0

    def text_at(a: Point, b: Point, row: int) -> Point:
        out = gap + row * step * (1.0 if gap >= 0 else -1.0)
        return ((a[0] + b[0]) / 2.0 + nx * out, (a[1] + b[1]) / 2.0 + ny * out)

    plan: list[dict[str, Any]] = []

    if mode == "ordinate":
        base = (float(datum[0]), float(datum[1])) if datum and len(datum) >= 2 else pts[0]
        for i, p in enumerate(pts):
            leader = (p[0] + nx * gap, p[1] + ny * gap)
            plan.append(
                {
                    "kind": "ordinate",
                    "point1": p,
                    "point2": leader,
                    "text_position": leader,
                    "measurement": abs(p[0] - base[0]) if axis != "vertical" else abs(p[1] - base[1]),
                    "row": 0,
                    "index": i,
                    "datum": base,
                }
            )
        return plan

    if mode in ("chain", "baseline"):
        pairs = (
            list(zip(pts, pts[1:], strict=False))
            if mode == "chain"
            else [(pts[0], p) for p in pts[1:]]
        )
        for i, (a, b) in enumerate(pairs):
            if measure(a, b, axis) < EPS:
                continue  # two features at the same place: nothing to dimension
            # A chain sits on one line; a baseline set steps out one line per
            # dimension so the longer ones clear the shorter ones.
            row = 0 if mode == "chain" else i
            plan.append(
                {
                    "kind": mode,
                    "point1": a,
                    "point2": b,
                    "text_position": text_at(a, b, row),
                    "measurement": measure(a, b, axis),
                    "row": row,
                    "index": i,
                }
            )

    if mode == "overall" or include_overall:
        a, b = pts[0], pts[-1]
        if measure(a, b, axis) >= EPS:
            rows = [entry["row"] for entry in plan]
            row = (max(rows) + 1) if rows else 0
            plan.append(
                {
                    "kind": "overall",
                    "point1": a,
                    "point2": b,
                    "text_position": text_at(a, b, row),
                    "measurement": measure(a, b, axis),
                    "row": row,
                    "index": len(plan),
                }
            )

    if not plan:
        raise ValueError(
            "those points give no dimension with a length - they are all at the same "
            "place along this axis"
        )
    return plan


def centre_mark_ops(
    centre: Sequence[float],
    radius: float,
    size: float | None = None,
    extend: float = 0.0,
    layer: str | None = None,
    color: Any = None,
) -> list[dict[str, Any]]:
    """The cross at a circle's centre, as two lines, plus centre lines if asked.

    ``size`` is the half length of the cross (default a tenth of the radius,
    the usual DIMCEN). ``extend`` runs centre lines out past the circle by that
    much, which is what a drawing office wants on a bolt hole.
    """
    cx, cy = float(centre[0]), float(centre[1])
    r = float(radius)
    if r <= 0.0:
        raise ValueError(f"a centre mark needs a radius above zero, got {r:g}")
    half = float(size) if size else max(r * 0.1, EPS)
    style: dict[str, Any] = {}
    if layer:
        style["layer"] = layer
    if color is not None:
        style["color"] = color

    ops = [
        {"type": "line", "start": [cx - half, cy], "end": [cx + half, cy], **style},
        {"type": "line", "start": [cx, cy - half], "end": [cx, cy + half], **style},
    ]
    if extend:
        out = r + float(extend)
        ops.extend(
            [
                {"type": "line", "start": [cx - out, cy], "end": [cx - half, cy], **style},
                {"type": "line", "start": [cx + half, cy], "end": [cx + out, cy], **style},
                {"type": "line", "start": [cx, cy - out], "end": [cx, cy - half], **style},
                {"type": "line", "start": [cx, cy + half], "end": [cx, cy + out], **style},
            ]
        )
    return ops


# ---------------------------------------------------------------------------
# The AutoCAD side
# ---------------------------------------------------------------------------

# A rotated dimension at 0 degrees measures X, at 90 degrees it measures Y.
AXIS_ANGLE = {"horizontal": 0.0, "vertical": 90.0}


def _dim_scale(doc: Any) -> float:
    """The drawing's DIMSCALE. A dimension made over COM does not pick it up itself."""
    try:
        return float(doc.GetVariable("DIMSCALE") or 0.0)
    except BaseException as exc:  # noqa: BLE001 - an old drawing may not carry it
        raise_if_busy(exc)
        return 0.0


def _handle_of(entity: Any) -> str:
    try:
        return str(entity.Handle)
    except BaseException:  # noqa: BLE001 - only for a message
        return "the dimension"


def stored_name(names: Sequence[str], wanted: str) -> str | None:
    """The name as the drawing stores it, matched without case, or None when it is not there."""
    key = str(wanted).strip().casefold()
    return next((str(n) for n in names if str(n).strip().casefold() == key), None)


def scale_to_write(dim_style: str | None, annotative: bool, drawing_scale: float) -> float | None:
    """The ScaleFactor each new dimension gets, or None to leave it alone (#37, D-80).

    A dimension made over COM does not pick up the drawing's DIMSCALE, so
    without a style it is given that. A named style carries its own DIMSCALE,
    and writing the drawing's over it would hide it; an annotative dimension
    is sized by its annotation scales, not by DIMSCALE. Both are left alone.
    """
    if dim_style or annotative or drawing_scale <= 0:
        return None
    return drawing_scale


def find_dim_style(doc: Any, wanted: str) -> str:
    """The drawing's own name for a dimension style, or a refusal naming what there is."""
    names: list[str] = []
    try:
        for i in range(doc.DimStyles.Count):
            names.append(str(doc.DimStyles.Item(i).Name))
    except BaseException as exc:  # noqa: BLE001 - say so rather than draw with the wrong style
        raise_if_busy(exc)
        raise AutocadError(f"Could not read the drawing's dimension styles ({com_message(exc)}). Nothing was drawn.") from exc
    found = stored_name(names, wanted)
    if found is None:
        listed = ", ".join(sorted(names, key=str.lower)[:20]) or "none"
        raise AutocadError(
            f"This drawing has no dimension style called '{wanted}' (it has: {listed}). "
            "autocad_list_styles lists them, autocad_create_styles makes one, and "
            "autocad_import_from_drawing brings one in. Nothing was drawn."
        )
    return found


def ordinate_refusal(datum_world: Sequence[float], now: Any, coords: str) -> str | None:
    """Why an ordinate run cannot be drawn as asked, or None when it can.

    AddDimOrdinate measures from the current UCS origin along the UCS axes;
    it takes no origin of its own. A datum anywhere else, or world points on a
    turned UCS, would put dimensions on the drawing that read the wrong values.
    """
    gap = math.hypot(float(datum_world[0]) - now.origin[0], float(datum_world[1]) - now.origin[1])
    if gap > 1e-6 * max(1.0, abs(now.origin[0]) + abs(now.origin[1])):
        at = ", ".join(f"{float(v):g}" for v in datum_world[:2])
        origin = ", ".join(f"{v:g}" for v in now.origin[:2])
        return (
            f"AutoCAD measures ordinate dimensions from the UCS origin, which is at "
            f"[{origin}], not from the datum at [{at}]. Move the UCS origin to the datum "
            f"first - autocad_set_ucs(mode='origin', origin=[{at}]) - then run this again."
        )
    if str(coords).strip().lower() != "ucs" and now.rotated:
        return (
            "The UCS is turned, and AutoCAD measures ordinates along the UCS axes. Give the "
            "points in UCS coordinates (coords='ucs'), or set the UCS back to World first."
        )
    return None


def _make_one(space: Any, entry: dict[str, Any], axis: str, ucs: Any) -> Any:
    """One dimension from a planned entry."""
    p1 = point(entry["point1"], "point1", ucs)
    p2 = point(entry["point2"], "point2", ucs)
    text = point(entry["text_position"], "text_position", ucs)
    if entry["kind"] == "ordinate":
        # True = an X-datum ordinate, False = a Y-datum one.
        return space.AddDimOrdinate(p1, text, axis != "vertical")
    if axis == "aligned":
        return space.AddDimAligned(p1, p2, text)
    # 'Horizontal' on a turned UCS is along its X axis, as the points are.
    return space.AddDimRotated(p1, p2, text, rad(world_angle(AXIS_ANGLE[axis], ucs)))


@mcp.tool(name="autocad_dimension_run", **tool_meta("Dimension A Run Of Features"))
@tool_errors
async def autocad_dimension_run(
    points: Annotated[
        list[list[float]],
        Field(
            min_length=1,
            max_length=MAX_POINTS,
            description=(
                "The feature points to dimension between, each [x, y] — grid lines, wall "
                "faces, hole centres, duct branches. They are put in order along the run "
                "for you unless you turn sort off."
            ),
        ),
    ],
    mode: Annotated[
        Mode,
        Field(
            default="chain",
            description=(
                "'chain' dimensions each gap to the next, all on one line (AutoCAD's "
                "Continue). 'baseline' dimensions every point back to the first, each on "
                "its own line stepped clear of the last. 'overall' is one dimension end to "
                "end. 'ordinate' labels each point's distance from a datum with a leader."
            ),
        ),
    ] = "chain",
    axis: Annotated[
        Axis,
        Field(
            default="horizontal",
            description=(
                "What each dimension measures: 'horizontal' (X only), 'vertical' (Y only), "
                "or 'aligned' (the true distance, for a sloping run)."
            ),
        ),
    ] = "horizontal",
    offset: Annotated[
        float,
        Field(
            default=0.0,
            description=(
                "How far the dimension line sits off the geometry, in drawing units. "
                "Negative puts it the other side. A drafter uses about 10 mm of paper, so "
                "10 x the drawing scale factor — 500 at 1:50."
            ),
        ),
    ] = 0.0,
    spacing: Annotated[
        float | None,
        Field(
            default=None,
            description=(
                "For 'baseline': the gap between one dimension line and the next. "
                "Defaults to the offset, which keeps them evenly stepped."
            ),
        ),
    ] = None,
    include_overall: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Add one overall dimension on a line beyond the rest — what a drawing "
                "nearly always wants above a chain."
            ),
        ),
    ] = False,
    datum: Annotated[
        list[float] | None,
        Field(default=None, description="For 'ordinate': the origin to measure from. Defaults to the first point. AutoCAD measures ordinates from the UCS origin, so the datum must be there: move it first with autocad_set_ucs(mode='origin')."),
    ] = None,
    sort: Annotated[
        bool,
        Field(default=True, description="Put the points in order along the run first. Turn off to dimension them exactly as given."),
    ] = True,
    text_override: Annotated[
        str | None,
        Field(default=None, description="Replace every measured value with this text. '<>' keeps the measurement, e.g. '<> TYP'."),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    space: Annotated[str, Field(default="model", description="'model' or 'paper'.", pattern="^(model|paper)$")] = "model",
    dry_run: Annotated[
        bool,
        Field(default=False, description="Report the run it would lay out — every dimension's points, text position and value — and draw nothing."),
    ] = False,
    coords: Annotated[str, COORDS_OPT] = "world",
    annotative: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Make every dimension in the run annotative, at the drawing's current annotation "
                "scale (CANNOSCALE); its size then comes from the scale, not DIMSCALE. Done by "
                "Heron's plug-in."
            ),
        ),
    ] = False,
    dim_style: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "A dimension style already in the drawing, by name, e.g. 'DIM-1-5' for a 1:5 "
                "detail on a 1:50 sheet. Every dimension in the run takes it, with the style's "
                "own scale. Omit to use the current style and the drawing's DIMSCALE."
            ),
        ),
    ] = None,
    quiet: Annotated[bool, QUIET_FIELD] = False,
) -> str:
    """Dimension a whole run of features in one call: a chain, a baseline set, or ordinates.

    This is the dimensioning a drawing actually needs. Give the feature points
    along a wall, a grid or a row of holes and say how you want them read; the
    points are sorted, every dimension line is placed at the same offset, a
    baseline set steps clear of itself, and an overall can go above the lot.

    The measurements are worked out here as well as by AutoCAD, and both are
    reported — so a run that does not add up shows itself.

    One undo step. Each dimension takes the drawing's current dimension style
    and its DIMSCALE, or, with dim_style, that style and the style's own scale:
    the drawing's current style and DIMSCALE are not touched either way.

    Args:
        points (list[list[float]]): the feature points.
        mode (str): chain, baseline, overall or ordinate.
        axis (str): horizontal, vertical or aligned.
        offset (float): distance from the geometry to the dimension line.
        spacing (Optional[float]): gap between baseline dimension lines.
        include_overall (bool): add an overall dimension above the run.
        datum (Optional[list[float]]): ordinate origin.
        sort (bool): order the points along the run first.
        text_override (Optional[str]): custom text; '<>' keeps the value.
        layer (Optional[str]): target layer, created if missing.
        space (str): 'model' or 'paper'.
        dry_run (bool): report the layout, draw nothing.
        coords (str): 'world' or 'ucs'.
        dim_style (Optional[str]): a dimension style in the drawing, for this run.
        annotative (bool): make the run annotative at the current annotation scale.
        quiet (bool): counts and handles only; "dimensions" is left out and
            "left_out" says how many there were (#44).

    Returns:
        str: JSON: {
          "mode", "axis", "count", "handles": [str],
          "dimensions": [{"kind", "point1", "point2", "text_position",
                          "expected", "measured", "handle", "row"}],
          "total": float,          # the run end to end
          "failed": [{"index", "reason"}],
          "dim_style": str,        # with dim_style: the style, as the drawing names it
          "style_scale": float,    # with dim_style: the scale the first dimension took from it
          "annotative": bool, "annotation_scales": [str]   # with annotative
        }

    Examples:
        - Use when: "dimension the grid lines along this wall" — the grid X
          values as points, mode='chain', include_overall=true.
        - Use when: "dimension every hole back to the left edge" —
          mode='baseline'.
        - Use when: "ordinate dimensions from the setting-out point" —
          mode='ordinate', datum the corner.
        - Use when: "dimension the 1:5 detail with the DIM-1-5 style" —
          dim_style='DIM-1-5'; no need to change DIMSCALE part-way through.
        - Use when: many runs in one autocad_sequence — quiet=true keeps the
          answer to counts and handles.
        - Don't use when: it is one dimension (autocad_add_dimension), or a
          radius, diameter or angle (same tool).

    Error Handling:
        - A dim_style the drawing does not have is refused before anything is
          drawn, naming the styles it has.
        - Points that land on top of each other along the axis are skipped
          rather than making a zero dimension; if none are left, that is said.
        - A dimension AutoCAD rejects is reported in "failed" with its index;
          the rest of the run still lands.
        - An ordinate run whose datum is not the UCS origin is refused before
          anything is drawn, naming the autocad_set_ucs call that fixes it.
    """
    try:
        plan = plan_run(points, mode, axis, offset, spacing, include_overall, sort, datum)
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    if annotative and not dry_run:
        require_plugin("Making dimensions annotative")

    shaped = quieted if quiet else (lambda result: result)
    if dry_run:
        return dumps(
            shaped(
                {
                    "mode": mode,
                    "axis": axis,
                    "dry_run": True,
                    "count": len(plan),
                    "dimensions": [
                        {**entry, "expected": round(entry["measurement"], 6)} for entry in plan
                    ],
                    "total": round(sum(e["measurement"] for e in plan if e["kind"] == "chain"), 6),
                    **({"dim_style": dim_style} if dim_style else {}),
                    "hint": "Nothing was drawn. Call again with dry_run=false.",
                }
            )
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = not_flipped(ucs_for(doc, coords), "dimensions")
        if mode == "ordinate":
            refusal = ordinate_refusal(world_coords(plan[0]["datum"], ucs), current_ucs(doc), coords)
            if refusal:
                raise AutocadError(refusal)
        # Checked before anything is drawn: an unknown style is a refusal, not
        # a run of wrongly sized dimensions (#37).
        style_name = find_dim_style(doc, dim_style) if dim_style else None
        target = get_space(doc, space)
        drawing_scale = _dim_scale(doc)
        scale = scale_to_write(style_name, annotative, drawing_scale)
        style_scale: float | None = None
        made: dict[str, Any] = {}
        rows: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        with undo_mark(doc):
            if layer:
                ensure_layer(doc, layer)
            for entry in plan:
                try:
                    dim = _make_one(target, entry, axis, ucs)
                except BaseException as exc:  # noqa: BLE001 - one dimension, not the run
                    raise_if_busy(exc)
                    failed.append({"index": entry["index"], "kind": entry["kind"],
                                   "reason": com_message(exc)})
                    continue
                if style_name:
                    # Per dimension, never by making the style current: putting the old
                    # style back afterwards would wipe the DIMSCALE overrides that
                    # autocad_drawing_setup left on it (#37).
                    try:
                        dim.StyleName = style_name
                    except BaseException as exc:  # noqa: BLE001 - a wrongly styled dimension is not kept
                        why = f"it would not take the style {style_name} ({com_message(exc)})"
                        try:
                            dim.Delete()
                            why += ", so it was not kept"
                        except BaseException:  # noqa: BLE001 - say it is still there
                            why += (f", and it could not be deleted: {_handle_of(dim)} is still in the drawing "
                                    "in the current style; delete it by hand")
                        raise_if_busy(exc)
                        failed.append({"index": entry["index"], "kind": entry["kind"], "reason": why})
                        continue
                    if style_scale is None:
                        try:
                            style_scale = round(float(dim.ScaleFactor), 6)
                        except BaseException as exc:  # noqa: BLE001 - only a report
                            raise_if_busy(exc)
                if text_override:
                    try:
                        dim.TextOverride = text_override
                    except BaseException as exc:  # noqa: BLE001 - the value still reads correctly
                        raise_if_busy(exc)
                if scale is not None:
                    try:
                        dim.ScaleFactor = scale
                    except BaseException as exc:  # noqa: BLE001 - keep the style's own size
                        raise_if_busy(exc)
                if layer:
                    try:
                        dim.Layer = layer.strip()
                    except BaseException as exc:  # noqa: BLE001 - reported by the layer being wrong
                        raise_if_busy(exc)
                measured = None
                try:
                    measured = round(float(dim.Measurement), 6)
                except BaseException as exc:  # noqa: BLE001 - not every type reports it
                    raise_if_busy(exc)
                rows.append(
                    {
                        "kind": entry["kind"],
                        "row": entry["row"],
                        "point1": [round(v, 6) for v in entry["point1"]],
                        "point2": [round(v, 6) for v in entry["point2"]],
                        "text_position": [round(v, 6) for v in entry["text_position"]],
                        "expected": round(entry["measurement"], 6),
                        "measured": measured,
                        "handle": str(dim.Handle),
                    }
                )
                made[str(dim.Handle)] = dim
            scaled = make_new_annotative([r["handle"] for r in rows]) if annotative and rows else {}
            plain = {h.upper() for h in scaled.get("not_annotative", [])}
            if plain and drawing_scale > 0 and not style_name:
                # Not annotative after all: sized by DIMSCALE as any other, never left tiny.
                # (With dim_style they keep the style's own scale, which already sizes them.)
                for handle, dim in made.items():
                    if handle.upper() in plain:
                        try:
                            dim.ScaleFactor = drawing_scale
                        except BaseException as exc:  # noqa: BLE001 - the warning already names it
                            raise_if_busy(exc)
                scaled["warning"] += " Those were given the drawing's DIMSCALE instead."

        result: dict[str, Any] = {
            "mode": mode,
            "axis": axis,
            "count": len(rows),
            "created": len(rows),
            "handles": [r["handle"] for r in rows],
            "dimensions": rows,
            "total": round(sum(r["expected"] for r in rows if r["kind"] == "chain"), 6),
            "failed": failed,
            "dim_scale": scale,
        }
        if style_name:
            result["dim_style"] = style_name
            result["style_scale"] = style_scale
        result.update(scaled)
        off = [r for r in rows if r["measured"] is not None and abs(r["measured"] - r["expected"]) > 1e-6]
        if off:
            measured_off = (
                f"{len(off)} dimension(s) measure something other than the span asked for. "
                "The usual cause is a UCS or an elevation difference; check them before issuing."
            )
            # Kept beside a warning already there (one that says the run is not annotative).
            result["warning"] = f"{result['warning']} {measured_off}" if result.get("warning") else measured_off
        return result

    return dumps(shaped(await run(work)))


@mcp.tool(name="autocad_add_centre_marks", **tool_meta("Add Centre Marks"))
@tool_errors
async def autocad_add_centre_marks(
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="The circles and arcs to mark, by handle. Omit to take them from a layer."),
    ] = None,
    layer_filter: Annotated[
        str | None,
        Field(default=None, description="Instead of handles: mark every circle and arc on this layer. Wildcards work, e.g. 'M-PIPE*'."),
    ] = None,
    size: Annotated[
        float | None,
        Field(default=None, gt=0, description="Half length of the cross, in drawing units. Default: a tenth of each radius, which is AutoCAD's own DIMCEN."),
    ] = None,
    extend: Annotated[
        float,
        Field(default=0.0, ge=0, description="Run centre lines out past the circle by this much. What a drawing office wants on a bolt hole."),
    ] = 0.0,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, Field(default=None, description="Colour for the marks; omit to inherit from the layer.")] = None,
    min_radius: Annotated[
        float,
        Field(default=0.0, ge=0, description="Skip anything smaller than this, so a drawing full of tiny arcs does not fill up with marks."),
    ] = 0.0,
    dry_run: Annotated[bool, Field(default=False, description="Report what would be marked and draw nothing.")] = False,
    quiet: Annotated[bool, QUIET_FIELD] = False,
) -> str:
    """Put a centre mark on every circle and arc: the cross a drawing office expects.

    Give the handles, or a layer and every circle and arc on it is marked.
    ``extend`` turns the cross into full centre lines running past the circle.

    AutoCAD has no Automation call for a centre mark, so these are drawn as
    lines — which means they go on the layer you ask for and plot the way that
    layer does. One undo step.

    Args:
        handles (Optional[list[str]]): the circles and arcs to mark.
        layer_filter (Optional[str]): or every circle and arc on this layer.
        size (Optional[float]): half length of the cross.
        extend (float): how far centre lines run past the circle.
        layer (Optional[str]): layer for the marks, created if missing.
        color (Optional[str | int]): colour for the marks.
        min_radius (float): skip anything smaller than this.
        dry_run (bool): report only.
        quiet (bool): counts and the marks' handles only; "circles" is left
            out and "left_out" says how many there were (#44).

    Returns:
        str: JSON: {"marked": int, "skipped": int, "created", "handles",
             "circles": [{"handle", "centre", "radius"}]}

    Examples:
        - Use when: "put centre lines on all the holes" — layer_filter the hole
          layer, extend about 2 mm of paper.
        - Use when: a fabricator asks for hole centres to be marked.
        - Don't use when: you want a radius or diameter dimension
          (autocad_add_dimension).

    Error Handling:
        - A handle that is not a circle or an arc is counted in "skipped" and
          named, rather than failing the call.
    """
    if not handles and not layer_filter:
        raise AutocadError(
            "Say what to mark: 'handles' for particular circles, or 'layer_filter' for "
            "every circle and arc on a layer."
        )
    aci = to_aci(color)

    def read() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        found: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        def look(entity: Any) -> None:
            kind = short_type(entity)
            handle = str(getattr(entity, "Handle", ""))
            if kind not in ("circle", "arc"):
                skipped.append({"handle": handle, "type": kind, "why": "not a circle or an arc"})
                return
            try:
                centre = [float(v) for v in entity.Center][:2]
                radius = float(entity.Radius)
            except BaseException as exc:  # noqa: BLE001 - unreadable, say so rather than guess
                raise_if_busy(exc)
                skipped.append({"handle": handle, "type": kind, "why": "centre or radius unreadable"})
                return
            if radius < min_radius:
                skipped.append({"handle": handle, "type": kind, "why": f"radius {radius:g} below min_radius"})
                return
            found.append({"handle": handle, "type": kind, "centre": centre, "radius": radius})

        if handles:
            for entity in resolve_handles(doc, handles):
                look(entity)
        else:
            for kind in ("circle", "arc"):
                sel = select_filtered(doc, entity_type=kind, layer=layer_filter)
                try:
                    for entity in iter_selection(sel):
                        look(entity)
                finally:
                    discard_selection_set(doc)
        return {"found": found, "skipped": skipped}

    scan = await run(read)
    found, skipped = scan["found"], scan["skipped"]
    if not found:
        return dumps(
            {
                "marked": 0,
                "skipped": len(skipped),
                "detail": skipped[:25],
                "hint": "Nothing to mark. Check the layer name, or min_radius.",
            }
        )

    shaped = quieted if quiet else (lambda result: result)
    operations: list[dict[str, Any]] = []
    for item in found:
        operations.extend(
            centre_mark_ops(item["centre"], item["radius"], size, extend, layer, aci)
        )

    if dry_run:
        return dumps(
            shaped(
                {
                    "dry_run": True,
                    "marked": len(found),
                    "skipped": len(skipped),
                    "entity_count": len(operations),
                    "circles": found[:50],
                    "hint": "Nothing was drawn. Call again with dry_run=false.",
                }
            )
        )

    result = await draw_operations(operations, return_handles=True, coords="world")
    result["marked"] = len(found)
    result["skipped"] = len(skipped)
    result["circles"] = found[:50]
    if skipped:
        result["skipped_detail"] = skipped[:25]
    return dumps(shaped(result))
