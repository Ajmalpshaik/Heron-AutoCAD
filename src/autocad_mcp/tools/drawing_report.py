"""One read-only look at a whole drawing: what a received DWG holds.

The idea is from Autodesk's DumpDwg sample (docs/11-adn-repos-study.md, item 4):
units, layers, blocks, xrefs, styles, layouts and what is drawn, in one call,
so a modeller can check a consultant's drawing before working on it. Written
fresh over COM; no code was copied.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from pydantic import Field

from ..acad.units import unit_name
from ..core.connection import get_doc, run
from ..core.registry import dumps, mcp, tool_errors, tool_meta

# Model space is counted up to this many objects; a 200,000-object survey
# would otherwise hold AutoCAD for minutes over COM.
MOST_TO_COUNT = 50_000

# ObjectName -> the word a draftsman uses.
KINDS = {
    "AcDbLine": "line",
    "AcDbPolyline": "polyline",
    "AcDb2dPolyline": "polyline (old style)",
    "AcDb3dPolyline": "3D polyline",
    "AcDbCircle": "circle",
    "AcDbArc": "arc",
    "AcDbEllipse": "ellipse",
    "AcDbSpline": "spline",
    "AcDbText": "text",
    "AcDbMText": "mtext",
    "AcDbBlockReference": "block reference",
    "AcDbHatch": "hatch",
    "AcDbMLeader": "multileader",
    "AcDbLeader": "leader",
    "AcDbTable": "table",
    "AcDbPoint": "point",
    "AcDb3dSolid": "3D solid",
    "AcDbRegion": "region",
    "AcDbWipeout": "wipeout",
    "AcDbRasterImage": "image",
    "AcDbOle2Frame": "OLE object",
}


def _try(getter, default=None):
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def _items(collection: Any):
    for i in range(int(_try(lambda: collection.Count, 0))):
        item = _try(lambda i=i: collection.Item(i))
        if item is not None:
            yield item


def _names(collection: Any) -> list[str]:
    return sorted((str(_try(lambda x=x: x.Name, "")) for x in _items(collection)), key=str.lower)


def _kind(object_name: str) -> str:
    if object_name in KINDS:
        return KINDS[object_name]
    if "Dimension" in object_name:
        return "dimension"
    return object_name.removeprefix("AcDb") or "unknown"


def _layers(doc: Any) -> dict[str, Any]:
    names, off, frozen, locked = [], [], [], []
    for layer in _items(doc.Layers):
        name = str(_try(lambda x=layer: x.Name, ""))
        names.append(name)
        if not bool(_try(lambda x=layer: x.LayerOn, True)):
            off.append(name)
        if bool(_try(lambda x=layer: x.Freeze, False)):
            frozen.append(name)
        if bool(_try(lambda x=layer: x.Lock, False)):
            locked.append(name)
    key = str.lower
    return {
        "count": len(names),
        "names": sorted(names, key=key),
        "off": sorted(off, key=key),
        "frozen": sorted(frozen, key=key),
        "locked": sorted(locked, key=key),
    }


def _blocks(doc: Any) -> tuple[list[str], list[dict[str, str]]]:
    blocks, xrefs = [], []
    for block in _items(doc.Blocks):
        name = str(_try(lambda b=block: b.Name, ""))
        if not name.strip() or name.startswith("*") or bool(_try(lambda b=block: b.IsLayout, False)):
            continue
        if bool(_try(lambda b=block: b.IsXRef, False)):
            xrefs.append({"name": name, "saved_path": str(_try(lambda b=block: b.Path, ""))})
        else:
            blocks.append(name)
    return sorted(blocks, key=str.lower), sorted(xrefs, key=lambda x: x["name"].lower())


def _count(space: Any, limit: int) -> tuple[int, Counter, bool]:
    kinds: Counter = Counter()
    total = int(_try(lambda: space.Count, 0))
    seen = 0
    for i in range(min(total, limit)):
        item = _try(lambda i=i: space.Item(i))
        if item is None:
            continue
        kinds[_kind(str(_try(lambda x=item: x.ObjectName, "")))] += 1
        seen += 1
    return total, kinds, total > limit


def _layouts(doc: Any) -> list[dict[str, Any]]:
    sheets = []
    for layout in _items(doc.Layouts):
        name = str(_try(lambda x=layout: x.Name, ""))
        if name.lower() == "model":
            continue
        block = _try(lambda x=layout: x.Block)
        sheets.append(
            {
                "name": name,
                "order": int(_try(lambda x=layout: x.TabOrder, 0)),
                "objects": int(_try(lambda b=block: b.Count, 0)) if block is not None else 0,
                "paper": str(_try(lambda x=layout: x.CanonicalMediaName, "")),
            }
        )
    return sorted(sheets, key=lambda s: s["order"])


@mcp.tool(name="autocad_drawing_report", **tool_meta("Drawing Report", read_only=True, idempotent=True))
@tool_errors
async def autocad_drawing_report(
    count_objects: Annotated[
        bool,
        Field(default=True, description="Count what is drawn in model space by type. Off for a quicker answer on a huge drawing."),
    ] = True,
) -> str:
    """Everything a received drawing holds, in one read: units, layers, blocks, xrefs, styles, sheets and what is drawn.

    The check before working on a consultant's or client's DWG: which units
    it is in, which layers are off, frozen or locked, which blocks and xrefs
    it carries, its text and dimension styles and linetypes, its sheets
    (layouts) with their paper, and how many of each kind of object are in
    model space (counted up to 50,000).

    Changes nothing.

    Args:
        count_objects (bool): count model space by type.

    Returns:
        str: JSON: {"drawing": str, "path": str, "units": str,
             "layers": {"count": int, "names": [str], "off": [str],
                        "frozen": [str], "locked": [str]},
             "blocks": {"count": int, "names": [str]},
             "xrefs": [{"name": str, "saved_path": str}],
             "text_styles": [str], "dimension_styles": [str],
             "linetypes": [str],
             "layouts": [{"name": str, "order": int, "objects": int, "paper": str}],
             "model_space": {"total": int, "by_type": {str: int}}}

    Examples:
        - Use when: "what is in this drawing the consultant sent?"
        - Use when: "audit this DWG before I start: units, layers, xrefs".
        - Use when: "how many sheets does this drawing have and on what paper?"
        - Don't use when: you need one list in detail - autocad_list_layers,
          autocad_list_blocks, autocad_list_styles or autocad_list_layouts.
        - Don't use when: you are checking against a rules file -
          autocad_check_standards.

    Error Handling:
        - Model space is counted up to 50,000 objects; past that the answer
          says so and gives the total.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        blocks, xrefs = _blocks(doc)
        result: dict[str, Any] = {
            "drawing": str(_try(lambda: doc.Name, "")),
            "path": str(_try(lambda: doc.FullName, "")),
            "units": _try(lambda: unit_name(int(doc.GetVariable("INSUNITS"))), "unknown"),
            "layers": _layers(doc),
            "blocks": {"count": len(blocks), "names": blocks},
            "xrefs": xrefs,
            "text_styles": _names(doc.TextStyles),
            "dimension_styles": _names(doc.DimStyles),
            "linetypes": _names(doc.Linetypes),
            "layouts": _layouts(doc),
        }
        if count_objects:
            total, kinds, capped = _count(doc.ModelSpace, MOST_TO_COUNT)
            model: dict[str, Any] = {"total": total, "by_type": dict(kinds.most_common())}
            if capped:
                model["note"] = f"Only the first {MOST_TO_COUNT:,} of {total:,} objects were counted by type."
            result["model_space"] = model
        if xrefs:
            result["advice"] = "autocad_xref_tree says which xrefs are loaded and which are broken."
        return result

    return dumps(await run(work))
