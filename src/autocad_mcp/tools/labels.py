"""Labels: MTEXT with a leader, the way Ajmal's TLD command makes them.

Two kinds:

* ``leader`` (default) follows TextLeader_V4.lsp ("TLD"): an MTEXT label and a
  classic LEADER on the text's layer, using the current dimension style for the
  arrow. The leader ends under the text, in the gap between line 1 and line 2
  (just under a one-line text), running the full text width plus an extension
  each side. Shape "L": a square leg from the arrow point, then along under the
  text. Shape "angled": straight to the near end of the text, then along it.
* ``mleader``: one MULTILEADER with the text as its content.

Both are one undo step. The arrow is sized from DIMSCALE: a leader made over COM
does not pick up the DIMSCALE override on its own (seen on dimensions, 2026-10-26).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Field, StrictInt

from ..acad.tables import apply_properties
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import double_array
from ._shared import COLOR_OPT, LAYER_OPT, point

AC_LINE_WITH_ARROW = 2  # AcLeaderType: 0 line, 1 spline, 2 line + arrow, 3 spline + arrow
AC_MTEXT_CONTENT = 2  # AcMLeaderContentType
AC_ATTACH_TOP_RIGHT = 3  # AcAttachmentPoint


@dataclass(frozen=True)
class Frame:
    """An MTEXT's extent (world X/Y, unrotated text)."""

    left: float
    right: float
    top: float
    height: float
    spacing: float = 1.0


def underline_level(frame: Frame) -> float:
    """Where the leader runs under the text: between line 1 and line 2 (TLD rule)."""
    pitch = frame.height * frame.spacing * 5.0 / 3.0
    return frame.top - frame.height - (pitch - frame.height) / 2.0


def leader_points(
    frame: Frame, arrow: tuple[float, float], shape: str, extension: float
) -> list[tuple[float, float]]:
    """TLD leader vertices, from the arrow point to the far end under the text."""
    if shape not in ("L", "angled"):
        raise AutocadError(f"shape must be 'L' or 'angled', got {shape!r}.")
    ext = extension * frame.height
    yu = underline_level(frame)
    ends = (frame.left - ext, frame.right + ext)
    ax, ay = float(arrow[0]), float(arrow[1])
    near, far = sorted(ends, key=lambda x: abs(x - ax))
    if shape == "angled":
        return [(ax, ay), (near, yu), (far, yu)]
    if abs(ay - yu) < 1e-6:
        return [(ax, ay), (far, yu)]
    return [(ax, ay), (ax, yu), (far, yu)]


def _flat(points: list[tuple[float, float]]) -> list[float]:
    return [c for x, y in points for c in (x, y, 0.0)]


def _segments_cross(p1, p2, p3, p4) -> bool:
    """True when segment p1-p2 crosses p3-p4 in their interiors (touching ends do not count)."""

    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = side(p3, p4, p1), side(p3, p4, p2)
    d3, d4 = side(p1, p2, p3), side(p1, p2, p4)
    return d1 * d2 < 0 and d3 * d4 < 0


def leaders_crossing(leaders: list[list[tuple[float, float]]]) -> list[list[int]]:
    """Index pairs of leaders that cross each other (drafting rule 4: none should)."""
    found = []
    for i in range(len(leaders)):
        for j in range(i + 1, len(leaders)):
            a, b = leaders[i], leaders[j]
            if any(
                _segments_cross(a[m], a[m + 1], b[n], b[n + 1])
                for m in range(len(a) - 1)
                for n in range(len(b) - 1)
            ):
                found.append([i, j])
    return found


def _place(doc: Any, space: Any, spec: dict[str, Any], scale: float) -> dict[str, Any]:
    """Draw one label (inside an open undo mark). Shared by the single and batch tools."""
    text, arrow, position, height = spec["text"], spec["arrow"], spec["position"], spec["height"]
    if spec["kind"] == "mleader":
        pts = [(float(arrow[0]), float(arrow[1])), (float(position[0]), float(position[1]))]
        made = space.AddMLeader(double_array(_flat(pts)), 0)
        mleader = made[0] if isinstance(made, tuple) else made
        mleader.ContentType = AC_MTEXT_CONTENT
        mleader.TextString = text
        notes = apply_properties(doc, mleader, spec["layer"], spec["aci"], None)
        for prop, value in (("TextHeight", height), ("ArrowheadSize", height), ("DoglegLength", height)):
            try:
                setattr(mleader, prop, float(value))
            except Exception as exc:  # noqa: BLE001 - a style that locks it keeps its own
                raise_if_busy(exc)
                notes.setdefault("not_set", []).append(prop)
        return {"created": True, "kind": "mleader", "handle": str(mleader.Handle),
                "handles": [str(mleader.Handle)], "points": [list(p) for p in pts], **notes}

    label = space.AddMText(point(position, "position"), float(spec["width"]), text)
    label.Height = float(height)
    if spec["mask"]:
        label.BackgroundFill = True
    if spec["text_align"] == "right":
        label.AttachmentPoint = AC_ATTACH_TOP_RIGHT
        label.InsertionPoint = point(position, "position")
    notes = apply_properties(doc, label, spec["layer"], spec["aci"], None)
    low, high = label.GetBoundingBox()
    frame = Frame(
        left=float(low[0]), right=float(high[0]), top=float(high[1]),
        height=float(height), spacing=float(getattr(label, "LineSpacingFactor", 1.0) or 1.0),
    )
    pts = leader_points(frame, (float(arrow[0]), float(arrow[1])), spec["shape"], spec["extension"])
    lead = space.AddLeader(double_array(_flat(pts)), None, AC_LINE_WITH_ARROW)
    lead.Layer = label.Layer  # TLD: the leader lives on the text's layer
    lead.ScaleFactor = scale
    return {"created": True, "kind": "leader", "shape": spec["shape"],
            "handle": str(label.Handle), "text_handle": str(label.Handle),
            "leader_handle": str(lead.Handle), "handles": [str(label.Handle), str(lead.Handle)],
            "points": [list(p) for p in pts], "arrow_scale": scale, **notes}


def _arrow_scale(doc: Any, arrow_scale: float | None) -> float:
    if arrow_scale:
        return float(arrow_scale)
    return float(doc.GetVariable("DIMSCALE") or 1.0) or 1.0


@mcp.tool(name="autocad_add_label", **tool_meta("Add Label with Leader"))
@tool_errors
async def autocad_add_label(
    text: Annotated[str, Field(description="Label text. Use \\P for a new line (MTEXT).")],
    arrow: Annotated[list[float], Field(description="Arrow point [x, y]: what the label points at.")],
    position: Annotated[list[float], Field(description="Top-left corner of the text [x, y].")],
    height: Annotated[float, Field(gt=0, description="Text height in drawing units.")],
    kind: Annotated[
        Literal["leader", "mleader"],
        Field(description="'leader' = MTEXT + LEADER, Ajmal's TLD style (default); 'mleader' = one MULTILEADER."),
    ] = "leader",
    shape: Annotated[
        Literal["L", "angled"],
        Field(description="For kind='leader': 'L' square leg then under the text (default), 'angled' straight to the text."),
    ] = "L",
    extension: Annotated[
        float, Field(ge=0, le=10, description="How far the line runs past the text each side, x text height (TLD: 0.5).")
    ] = 0.5,
    width: Annotated[float, Field(ge=0, description="MTEXT wrap width; 0 = no wrapping.")] = 0.0,
    text_align: Annotated[
        Literal["left", "right"],
        Field(description="'left': position is the text's top-left (default). 'right': its top-right, for a label column left of the detail."),
    ] = "left",
    mask: Annotated[
        bool, Field(description="Background mask behind the text, so it reads over hatching and lines.")
    ] = False,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
) -> str:
    """Place a label that points at something: text plus a leader with an arrow.

    Use for every label on a drawing. Default is Ajmal's TLD style: MTEXT, and a
    LEADER that ends under the text. 'L' gives a square leg, 'angled' a straight
    one; pick 'angled' when several labels sit in a column. kind='mleader' gives
    one MULTILEADER instead. Put the text where it is easy to read, clear of the
    drawing; the arrow goes on the object.

    Returns:
        JSON: {"created": true, "kind", "handle" (text or mleader), "handles", "points"}

    Examples:
        - Use when: "point a label at that bracket saying 100x100x10 ANGLE".
        - Don't use when: one note serves several parts - one
          autocad_add_multileader with three arrows reads better than three
          labels.
    """
    spec = {"text": text, "arrow": arrow, "position": position, "height": height, "kind": kind,
            "shape": shape, "extension": extension, "width": width, "text_align": text_align,
            "mask": mask, "layer": layer, "aci": to_aci(color)}

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        space = get_space(doc, "model")
        with undo_mark(doc):
            return _place(doc, space, spec, _arrow_scale(doc, None))

    return dumps(await run(work))


LABEL_KEYS = {"text", "arrow", "position", "height", "kind", "shape", "extension", "width",
              "text_align", "mask", "layer", "color"}
CHOICES = {"kind": ("leader", "mleader"), "shape": ("L", "angled"), "text_align": ("left", "right")}


def _is_xy(value: Any) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) >= 2
            and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in value[:2]))


def check_labels(items: list[dict[str, Any]], defaults: dict[str, Any]) -> list[dict[str, Any]]:
    """Fill each label from the shared settings and check it, before AutoCAD is touched.

    Raises naming the label's index, so a bad batch draws nothing.
    """
    specs = []
    for i, item in enumerate(items):
        where = f"label {i}"
        if not isinstance(item, dict):
            raise AutocadError(f"{where}: must be an object with text, arrow and position.")
        unknown = set(item) - LABEL_KEYS
        if unknown:
            raise AutocadError(f"{where}: unknown field(s) {sorted(unknown)}; allowed: {sorted(LABEL_KEYS)}.")
        spec = {**defaults, **{k: v for k, v in item.items() if k != "color"}}
        if "color" in item:
            spec["aci"] = to_aci(item["color"])
        if not isinstance(spec.get("text"), str) or not spec["text"].strip():
            raise AutocadError(f"{where}: 'text' is missing or empty.")
        for key in ("arrow", "position"):
            if not _is_xy(spec.get(key)):
                raise AutocadError(f"{where}: '{key}' must be [x, y].")
        if not isinstance(spec.get("height"), (int, float)) or spec["height"] <= 0:
            raise AutocadError(f"{where}: 'height' must be a number above 0 (or set the shared height).")
        for key, allowed in CHOICES.items():
            if spec[key] not in allowed:
                raise AutocadError(f"{where}: '{key}' must be one of {list(allowed)}, got {spec[key]!r}.")
        specs.append(spec)
    return specs


@mcp.tool(name="autocad_batch_labels", **tool_meta("Add Many Labels at Once"))
@tool_errors
async def autocad_batch_labels(
    labels: Annotated[
        list[dict[str, Any]],
        Field(min_length=1, max_length=500, description=(
            "The labels, in column order. Each needs text, arrow [x, y] and position [x, y] (top-left, "
            "or top-right with text_align 'right'). Any shared setting below can be overridden per "
            "label: height, shape, text_align, kind, extension, width, mask, layer, color.\n"
            'Example: {"text": "BASE PLATE 350x350x25", "arrow": [172, 142], "position": [1100, 500]}'
        )),
    ],
    height: Annotated[float | None, Field(gt=0, description="Text height for every label that does not set its own.")] = None,
    kind: Annotated[Literal["leader", "mleader"], Field(description="'leader' = TLD MTEXT + LEADER (default); 'mleader' = MULTILEADER.")] = "leader",
    shape: Annotated[Literal["L", "angled"], Field(description="'angled' suits a column (default here); 'L' a square leg.")] = "angled",
    text_align: Annotated[Literal["left", "right"], Field(description="'right' for a column left of the detail.")] = "left",
    extension: Annotated[float, Field(ge=0, le=10, description="Line past the text each side, x text height.")] = 0.5,
    width: Annotated[float, Field(ge=0, description="MTEXT wrap width; 0 = no wrapping.")] = 0.0,
    mask: Annotated[bool, Field(description="Background mask behind every text.")] = False,
    arrow_scale: Annotated[
        float | None,
        Field(gt=0, description="Arrow size factor, normally the view's scale (25 for 1:25). Omit to use DIMSCALE."),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
) -> str:
    """Place many labels in one go: one trip to AutoCAD and one undo step.

    Use instead of calling autocad_add_label again and again — a column of 15
    labels is one call. Same TLD geometry as autocad_add_label. Every label is
    checked first, so a bad one stops the batch with its index and nothing is
    drawn. Afterwards the leaders are checked against each other and any pair
    that crosses is listed in "crossing" (drafting rule 4: fix those).

    Returns:
        JSON: {"created": n, "labels": [per-label result, in order],
               "crossing": [[i, j], ...], "arrow_scale": float}

    Examples:
        - Use when: "label all the parts of this detail in a column on the right".
        - Use when: "put the 15 labels on the pole elevation at 1:25".
        - Don't use when: one or two labels - autocad_add_label is enough.
    """
    defaults = {"height": height, "kind": kind, "shape": shape, "text_align": text_align,
                "extension": extension, "width": width, "mask": mask, "layer": layer,
                "aci": to_aci(color)}
    specs = check_labels(labels, defaults)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        space = get_space(doc, "model")
        scale = _arrow_scale(doc, arrow_scale)
        with undo_mark(doc):
            done = [_place(doc, space, spec, scale) for spec in specs]
        return {"created": len(done), "labels": done, "arrow_scale": scale,
                "crossing": leaders_crossing([[tuple(p) for p in d["points"]] for d in done])}

    return dumps(await run(work))
