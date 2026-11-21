"""Annotative text, dimensions and multileaders, and their annotation scales (#108, D-81).

An annotative object is sized by the sheet, not by the model: written once at
2.5 mm, it shows 2.5 mm on a 1:50 viewport and on a 1:100 one, if it carries
both scales. Only AutoCAD's .NET API reaches an object's scales (COM has no
call for them), so the plug-in does the work; the rules - which scales, which
ratio, what changed - are plain functions here, tested without AutoCAD.

The drawing's own annotation scale, CANNOSCALE, is set by
autocad_drawing_setup(scale=...); this module reads it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Annotated, Any

from pydantic import Field

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from . import _shared
from ._shared import PLUGIN_ONLY, before_after, in_plugin

RATIO = re.compile(r"^\s*(\d+(?:\.\d*)?|\.\d+)\s*:\s*(\d+(?:\.\d*)?|\.\d+)\s*$")
MAX_OBJECTS = 500
ANNOTATIVE_OPT = Field(
    default=False,
    description=(
        "Make it annotative, at the drawing's current annotation scale (CANNOSCALE, set by "
        "autocad_drawing_setup). Sizes stay in drawing units at that scale: 125 for 2.5 mm "
        "at 1:50. Add more scales with autocad_annotation_scales. Done by Heron's plug-in."
    ),
)


# ---------------------------------------------------------------------------
# The rules (pure: no AutoCAD below this line)
# ---------------------------------------------------------------------------


def parse_scale(text: str) -> dict[str, Any]:
    """A scale as asked for: ``{"name", "paper", "drawing"}``.

    '1:50' reads as 1 paper unit to 50 drawing units, so the plug-in can find
    it by its ratio when the drawing names it differently, or add it. Any other
    name ('1/4" = 1\\'-0"') is looked up by name only (paper and drawing 0).
    """
    name = str(text).strip()
    if not name:
        raise ValueError("a scale name cannot be empty")
    found = RATIO.match(name)
    if not found:
        return {"name": name, "paper": 0.0, "drawing": 0.0}
    paper, drawing = float(found.group(1)), float(found.group(2))
    if paper <= 0 or drawing <= 0:
        raise ValueError(f"'{name}' has a zero in it; a scale is paper units to drawing units, like 1:50")
    return {"name": f"{found.group(1)}:{found.group(2)}", "paper": paper, "drawing": drawing}


def _same(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a["name"].casefold() == b["name"].casefold():
        return True
    if a["paper"] and b["paper"]:
        return abs(a["paper"] / a["drawing"] - b["paper"] / b["drawing"]) < 1e-12
    return False


def scale_args(
    add: Sequence[str] | None = None,
    remove: Sequence[str] | None = None,
    annotative: bool | None = None,
    create_missing: bool = False,
) -> dict[str, Any]:
    """The plug-in's arguments for set_annotation_scales; ValueError for a request that contradicts itself."""
    adds = [parse_scale(s) for s in add or []]
    removes = [parse_scale(s) for s in remove or []]
    if annotative is False and adds:
        raise ValueError("annotative=false takes every scale off; it cannot add scales at the same time")
    if annotative is None and not adds and not removes:
        raise ValueError("say what to change: annotative, add or remove")
    for a in adds:
        for r in removes:
            if _same(a, r):
                raise ValueError(f"{a['name']} is asked to be both added and removed")
    if create_missing:
        flat = [a["name"] for a in adds if not a["paper"]]
        if flat:
            raise ValueError(f"only a scale written as paper:drawing, like 1:25, can be added to the drawing's list; not {', '.join(flat)}")
    args: dict[str, Any] = {}
    if annotative is not None:
        args["annotative"] = annotative
    if adds:
        args.update(add=[a["name"] for a in adds], add_paper=[a["paper"] for a in adds], add_drawing=[a["drawing"] for a in adds])
    if removes:
        args.update(remove=[r["name"] for r in removes], remove_paper=[r["paper"] for r in removes],
                    remove_drawing=[r["drawing"] for r in removes])
    if create_missing:
        args["create_missing"] = True
    return args


def paper_height(height: float | None, scale: dict[str, Any] | None) -> float | None:
    """What a model-space text height reads on paper at a scale: 125 at 1:50 is 2.5."""
    if height is None or not scale or not scale.get("drawing"):
        return None
    return round(float(height) * float(scale["paper"]) / float(scale["drawing"]), 6)


def with_paper_heights(objects: Iterable[dict[str, Any]], current: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Each object as the plug-in described it, plus its paper height at the current scale when it is annotative."""
    out = []
    for obj in objects:
        row = dict(obj)
        if row.get("annotative") == "yes" and row.get("height") is not None:
            row["paper_height"] = paper_height(row["height"], current)
        out.append(row)
    return out


def scale_rows(objects: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The before / after rows (D-62) for what set_annotation_scales changed."""
    rows: list[dict[str, Any]] = []
    for obj in objects:
        handle = str(obj.get("handle", ""))
        was, now = obj.get("annotative_was"), obj.get("annotative")
        if was is not None and was != now:
            rows.append({"handle": handle, "property": "annotative", "from": was, "to": now})
        before, after = list(obj.get("scales_were") or []), list(obj.get("scales") or [])
        if was is not None and before != after:
            rows.append({"handle": handle, "property": "annotation scales", "from": ", ".join(before) or "none",
                         "to": ", ".join(after) or "none"})
    return rows


# ---------------------------------------------------------------------------
# The AutoCAD side
# ---------------------------------------------------------------------------


def require_plugin(what: str) -> None:
    """Refuse before drawing anything when the plug-in that makes it annotative is not there."""
    if _shared.plugin_runner() is None:
        raise AutocadError(PLUGIN_ONLY.format(what=what))


def make_new_annotative(handles: Sequence[str]) -> dict[str, Any]:
    """Make objects a tool has just drawn annotative, at the current scale (worker thread, in its job).

    One plug-in call for all of them. Never raises: the objects are drawn
    already, and an error would send the chat round to draw them twice. What
    did not happen comes back as a warning.
    """
    wanted = [str(h) for h in handles]
    if not wanted:
        return {}
    try:
        report = in_plugin("set_annotation_scales", {"handles": wanted, "annotative": True}, "Making it annotative")
    except AutocadError as exc:
        return {"annotative": False, "warning": f"{', '.join(wanted)} drawn, but not made annotative: {exc}",
                "not_annotative": wanted}
    objects = with_paper_heights(report.get("objects") or [], report.get("current"))
    yes = [o for o in objects if o.get("annotative") == "yes"]
    done = {str(o.get("handle", "")).upper() for o in yes}
    out: dict[str, Any] = {"annotative": len(done) == len(wanted), "annotation_scales": list(yes[0].get("scales") or []) if yes else []}
    if len(wanted) == 1 and yes and yes[0].get("paper_height") is not None:
        out["paper_height"] = yes[0]["paper_height"]
    missing = [h for h in wanted if h.upper() not in done]
    if missing:
        skipped = report.get("skipped") or []
        why = skipped[0].get("why") if skipped else "the plug-in did not make it annotative"
        out["warning"] = f"{', '.join(missing)} drawn, but not made annotative: {why}"
        out["not_annotative"] = missing
    return out


def _cannoscale(doc: Any) -> str | None:
    try:
        return str(doc.GetVariable("CANNOSCALE"))
    except BaseException as exc:  # noqa: BLE001 - an old drawing may not say
        raise_if_busy(exc)
        return None


@mcp.tool(name="autocad_list_annotation_scales", **tool_meta("List Annotation Scales", read_only=True, idempotent=True))
@tool_errors
async def autocad_list_annotation_scales(
    handles: Annotated[
        list[str] | None,
        Field(default=None, max_length=MAX_OBJECTS, description="Objects to look at, by handle: whether each is annotative and which scales it has. Omit for the drawing's list only."),
    ] = None,
) -> str:
    """The drawing's annotation scales, the current one (CANNOSCALE), and which scales objects carry.

    An annotative object shows only in a viewport whose scale it carries (with
    ANNOALLVISIBLE off). Read this before issuing a sheet, to see that every
    note and dimension carries the viewport's scale.

    Read by Heron's plug-in (COM has no call for object scales); without the
    plug-in only CANNOSCALE comes back.

    Args:
        handles (Optional[list[str]]): objects to look at.

    Returns:
        str: JSON: {"current": {"name", "paper", "drawing"}, "cannoscale": str,
             "scales": [{"name", "paper", "drawing"}], "anno_all_visible": bool,
             "objects": [{"handle", "type", "annotative": "yes"|"no"|"cannot",
                          "scales": [str], "height", "paper_height"}]}

    Examples:
        - Use when: "is this note annotative, and at which scales?"
        - Use when: "which annotation scales does the drawing have?"
        - Use when: "what is the current annotation scale?" — "cannoscale".
        - Don't use when: you want to change an object's scales —
          autocad_annotation_scales; or to set the drawing's scale, DIMSCALE or
          LTSCALE — autocad_drawing_setup(scale=...).
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        cannoscale = _cannoscale(doc)
        if _shared.plugin_runner() is None:
            return {"cannoscale": cannoscale, "note": PLUGIN_ONLY.format(what="Reading annotation scales")}
        report = in_plugin("annotation_scales", {"handles": list(handles or [])}, "Reading annotation scales", changes=False)
        report["objects"] = with_paper_heights(report.get("objects") or [], report.get("current"))
        report["cannoscale"] = cannoscale
        return report

    return dumps(await run(work))


@mcp.tool(name="autocad_annotation_scales", **tool_meta("Annotation Scales On Objects", idempotent=True))
@tool_errors
async def autocad_annotation_scales(
    handles: Annotated[
        list[str],
        Field(min_length=1, max_length=MAX_OBJECTS, description="The text, mtext, dimensions, multileaders, hatches or blocks to change, by handle."),
    ],
    annotative: Annotated[
        bool | None,
        Field(default=None, description="true makes them annotative (at the current scale if none is added); false makes them plain again. Omit to leave that as it is."),
    ] = None,
    add: Annotated[
        list[str] | None,
        Field(default=None, description="Scales to add, e.g. ['1:20', '1:100']. Adding makes a plain object annotative."),
    ] = None,
    remove: Annotated[
        list[str] | None,
        Field(default=None, description="Scales to take off, e.g. ['1:20']. Every annotative object keeps at least one."),
    ] = None,
    add_missing_to_drawing: Annotated[
        bool,
        Field(default=False, description="Add a scale such as '1:25' to the drawing's scale list when it is not there. Without it, a scale the drawing has not got is refused."),
    ] = False,
) -> str:
    """Make objects annotative, add or remove their annotation scales: AutoCAD's OBJECTSCALE.

    An annotative note carries one size per scale: give it 1:50 and 1:100 and
    it reads the same on paper in both viewports. A scale is found by name, or
    else by its ratio, so '1:50' finds the drawing's 1:50 whatever it is called.

    Done by Heron's plug-in (COM has no call for object scales), all or
    nothing: one object it cannot change leaves every object as it was. Objects
    that cannot be annotative (a line, a circle) are skipped and named. One
    undo step.

    Args:
        handles (list[str]): the objects.
        annotative (Optional[bool]): make annotative, or plain.
        add (Optional[list[str]]): scales to add.
        remove (Optional[list[str]]): scales to remove.
        add_missing_to_drawing (bool): add a 1:N scale the drawing lacks.

    Returns:
        str: JSON: {"objects": [{"handle", "type", "annotative", "scales",
             "annotative_was", "scales_were", "paper_height"}],
             "scales_created": [str], "skipped": [{"handle", "why"}],
             "before_after": [{handle, property, from, to}]}

    Examples:
        - Use when: "make these notes annotative" — annotative=true.
        - Use when: "these notes need to show at 1:20 and 1:100 too" —
          add=['1:20','1:100'].
        - Use when: "take 1:5 off these dimensions" — remove=['1:5'].
        - Use when: "this detail is 1:25 and the drawing has no 1:25" —
          add=['1:25'], add_missing_to_drawing=true.
        - Don't use when: you are adding new text or dimensions — give
          annotative=true on autocad_add_text, autocad_add_mtext,
          autocad_add_dimension, autocad_dimension_run or
          autocad_add_multileader. The drawing's own scale, DIMSCALE and
          LTSCALE are autocad_drawing_setup(scale=...).

    Error Handling:
        - A removal that would leave an annotative object with no scale is
          refused, and nothing is changed.
        - A scale the drawing has not got is refused, unless
          add_missing_to_drawing is true and it is written like 1:25.
    """
    try:
        args = scale_args(add, remove, annotative, add_missing_to_drawing)
    except ValueError as exc:
        raise AutocadError(f"{exc}. Nothing was changed.") from exc
    wanted = [str(h).strip() for h in handles]

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        with undo_mark(doc):
            report = in_plugin("set_annotation_scales", {"handles": wanted, **args}, "Setting annotation scales")
        objects = with_paper_heights(report.get("objects") or [], report.get("current"))
        rows = scale_rows(objects)
        rows += [{"variable": "scale list", "property": "annotation scale", "from": "not there", "to": name}
                 for name in report.get("scales_created") or []]
        return {
            "objects": objects,
            "scales_created": list(report.get("scales_created") or []),
            "skipped": list(report.get("skipped") or []),
            "current": report.get("current"),
            **before_after(rows),
        }

    return dumps(await run(work))
