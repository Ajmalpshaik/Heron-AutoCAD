"""Drawing standards check and block-attribute extraction.

Both only read. The rule checking and the CSV writing are plain functions over
plain data, so they are tested without AutoCAD; the tools only gather that data
over COM.

The standards check also takes a reference drawing (#69, D-92): an office .dws,
a template or any .dwg / .dxf. Its layers, text styles, dimension styles and
linetypes are read with acad/dxf_file.py where it can (a DXF always; a DWG or
DWS when the ODA File Converter is on this PC), else by AutoCAD's own reader
(ObjectDBX, the file not opened on screen); the compare is
acad/standard_compare.py.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import math
import os
import re
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import dxf_file, geometry, standard_compare
from ..acad.checklist import PASS_MEANS
from ..acad.entities import read_attributes
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import describe_layer
from ..core.connection import get_app, get_doc, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from ..core.variants import point_to_list

KNOWN_RULES = {
    "layer_name_pattern",
    "layers",
    "forbid_entities_on_layer_0",
    "require_bylayer_color",
    "require_bylayer_linetype",
    "forbid_overlapping_dimensions",
    "max_findings",
}
_SYSTEM_LAYERS = {"0", "defpoints"}
BYLAYER_COLOR = 256


def check(layers: list[dict], entities: list[dict], rules: dict, more: list[dict] | None = None) -> dict[str, Any]:
    """Check layers and entities against a rules dict. Pure: no AutoCAD here.

    ``more``: findings already made elsewhere (the reference drawing compare),
    counted and capped with these.

    Rules (all optional):
        layer_name_pattern: regex every layer except 0 / Defpoints must match.
        layers: {name: {"color": int, "linetype": str}} - must exist with these.
        forbid_entities_on_layer_0: no geometry on layer 0.
        require_bylayer_color / require_bylayer_linetype: no overrides.
        forbid_overlapping_dimensions: no two dimensions on top of each other (Lee Mac's Dimension Overlap idea).
        max_findings: cap the list (default 200); the summary still counts all.
    """
    findings: list[dict[str, Any]] = []
    by_name = {str(layer["name"]).lower(): layer for layer in layers}

    pattern = rules.get("layer_name_pattern")
    if pattern:
        regex = re.compile(pattern)
        for layer in layers:
            name = str(layer["name"])
            if name.lower() not in _SYSTEM_LAYERS and not regex.search(name):
                findings.append({"rule": "layer_name", "layer": name, "detail": f"does not match {pattern}"})

    for name, wanted in (rules.get("layers") or {}).items():
        layer = by_name.get(name.lower())
        if layer is None:
            findings.append({"rule": "layer_missing", "layer": name, "detail": "required layer does not exist"})
            continue
        if "color" in wanted and layer.get("color") != wanted["color"]:
            findings.append({"rule": "layer_color", "layer": name, "detail": f"colour {layer.get('color')}, wanted {wanted['color']}"})
        if "linetype" in wanted and str(layer.get("linetype", "")).lower() != str(wanted["linetype"]).lower():
            findings.append({"rule": "layer_linetype", "layer": name, "detail": f"linetype {layer.get('linetype')}, wanted {wanted['linetype']}"})

    for entity in entities:
        base = {"handle": entity["handle"], "type": entity.get("type"), "layer": entity.get("layer")}
        if rules.get("forbid_entities_on_layer_0") and str(entity.get("layer")) == "0":
            findings.append({**base, "rule": "entity_on_layer_0", "detail": "geometry on layer 0"})
        if rules.get("require_bylayer_color") and entity.get("color") != BYLAYER_COLOR:
            findings.append({**base, "rule": "bylayer_color", "detail": f"colour {entity.get('color')} instead of ByLayer"})
        if rules.get("require_bylayer_linetype") and str(entity.get("linetype", "")).lower() != "bylayer":
            findings.append({**base, "rule": "bylayer_linetype", "detail": f"linetype {entity.get('linetype')} instead of ByLayer"})

    if rules.get("forbid_overlapping_dimensions"):
        boxes = {e["handle"]: tuple(e["box"]) for e in entities if "Dimension" in str(e.get("type")) and e.get("box")}
        for a, b in geometry.overlapping(boxes):
            findings.append({"handle": a, "other": b, "type": "dimension", "rule": "dimension_overlap",
                             "detail": f"overlaps dimension {b}"})

    findings.extend(more or [])
    summary: dict[str, int] = {}
    for finding in findings:
        summary[finding["rule"]] = summary.get(finding["rule"], 0) + 1
    limit = int(rules.get("max_findings", 200))
    report: dict[str, Any] = {
        "checked": {"layers": len(layers), "entities": len(entities)},
        "passed": not findings,
        "summary": summary,
        "findings": findings[:limit],
        "truncated": len(findings) > limit,
    }
    unknown = sorted(set(rules) - KNOWN_RULES)
    if unknown:
        report["unknown_rules"] = unknown
    return report


def rows_to_csv(rows: list[dict]) -> str:
    """block, handle, layer, x, y, z, then every attribute tag seen, A-Z."""
    tags = sorted({tag for row in rows for tag in row.get("attributes", {})})
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["block", "handle", "layer", "x", "y", "z", *tags])
    for row in rows:
        x, y, z = (list(row.get("insertion") or []) + [None, None, None])[:3]
        attributes = row.get("attributes", {})
        writer.writerow([row["block"], row["handle"], row.get("layer", ""), x, y, z, *(attributes.get(t, "") for t in tags)])
    return out.getvalue()


def _load_rules(rules: dict | None, rules_path: str | None) -> dict:
    if rules:
        return rules
    if not rules_path:
        raise AutocadError(
            "Give the rules, either inline as 'rules' or as a JSON file path in 'rules_path', or a "
            "reference drawing (.dws, .dwg or .dxf) in 'reference'."
        )
    path = os.path.expandvars(os.path.expanduser(rules_path.strip().strip('"')))
    try:
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (OSError, ValueError) as exc:
        raise AutocadError(f"Could not read the rules file {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AutocadError("The rules file must hold one JSON object.")
    return loaded


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr)
    except BaseException:  # noqa: BLE001 - a property this AutoCAD does not give
        return default


def _items(collection: Any, what: str | None = None) -> list[Any]:
    """Every item; with ``what``, a table that cannot be read stops the check, naming it.

    An empty list for a table that failed to read would turn "nothing could
    be read" into "nothing is required", a silent pass (D-64).
    """
    try:
        return [collection.Item(i) for i in range(collection.Count)]
    except BaseException as exc:  # noqa: BLE001
        if what is None:
            return []
        raise AutocadError(f"AutoCAD could not read the {what} ({com_message(exc)}). Nothing was checked.") from exc


def com_tables(doc: Any, layers: list[dict] | None = None) -> dict[str, list[dict]]:
    """Layers, text styles, dimension styles and linetypes over COM, in dxf_file.tables' words.

    ``doc`` is the open drawing or a database ObjectDBX read; both have the
    same four collections. Only reads.
    """
    styles = []
    for style in _items(doc.TextStyles, "text styles"):
        family = ""
        try:
            family = str(style.GetFont()[0] or "")
        except BaseException:  # noqa: BLE001 - a shape font has no typeface
            pass
        oblique = _get(style, "ObliqueAngle", 0.0)
        styles.append({
            "name": str(_get(style, "Name", "") or ""),
            "font": str(_get(style, "FontFile", "") or ""),
            "bigfont": str(_get(style, "BigFontFile", "") or ""),
            "family": family,
            "height": float(_get(style, "Height", 0.0) or 0.0),
            "width": float(_get(style, "Width", 1.0) or 1.0),
            "oblique": round(math.degrees(float(oblique or 0.0)), 6),
        })  # fmt: skip
    return {
        "layers": layers if layers is not None else [describe_layer(layer) for layer in _items(doc.Layers, "layers")],
        "text_styles": styles,
        "dim_styles": [{"name": str(_get(style, "Name", "") or "")} for style in _items(doc.DimStyles, "dimension styles")],
        "linetypes": [
            {"name": str(_get(lt, "Name", "") or ""), "description": str(_get(lt, "Description", "") or "")}
            for lt in _items(doc.Linetypes, "linetypes")
        ],
    }


def _reference_path(reference: str) -> str:
    path = dxf_file.clean_path(reference)
    if not path.is_absolute():
        raise AutocadError(f"Give the reference drawing's full path, with its folder: {path} is not one.")
    if not path.is_file():
        raise AutocadError(f"There is no reference drawing at {path}. Nothing was checked.")
    if path.suffix.lower() not in dxf_file.DXF_KINDS + dxf_file.DWG_KINDS:
        raise AutocadError(f"The reference must be a .dws, .dwg, .dwt or .dxf; {path.name} is not one.")
    return str(path)


async def _reference_from_file(path: str) -> tuple[dict[str, Any] | None, str | None]:
    """(the reference read from disk, or None for AutoCAD to read it; a note why AutoCAD did).

    A DXF is always read here; a DWG or DWS only when the ODA File Converter is
    on this PC. A converter that fails hands the file to AutoCAD's own reader.
    """
    is_dxf = path.lower().endswith(dxf_file.DXF_KINDS)
    if not is_dxf and dxf_file.find_oda_converter() is None:
        return None, None
    try:
        opened = await asyncio.to_thread(dxf_file.open_file, path)
    except AutocadError as exc:
        if is_dxf:
            raise
        return None, f"The ODA File Converter could not read it ({exc}), so AutoCAD read it."
    return {"tables": dxf_file.tables(opened.doc), "read_by": opened.read_by, "recovered": opened.recovered}, None


def _reference_from_autocad(path: str) -> dict[str, Any]:
    """Read a DWG / DWS with the running AutoCAD: the open drawing if it is open, else ObjectDBX."""
    from .drawing_tools import dbx_progid

    app = get_app()
    wanted = os.path.normcase(os.path.abspath(path))
    for doc in _items(app.Documents):
        if os.path.normcase(str(_get(doc, "FullName", "") or "")) == wanted:
            return {"tables": com_tables(doc), "read_by": "AutoCAD: the drawing is open there (what is saved and not saved)"}
    try:
        source = app.GetInterfaceObject(dbx_progid(str(app.Version)))
        source.Open(path)
    except BaseException as exc:  # noqa: BLE001
        raise AutocadError(
            f"AutoCAD could not read the reference {path} ({com_message(exc)}). Open it in AutoCAD once, or "
            "save it as DXF and give that. Nothing was checked."
        ) from exc
    try:
        return {"tables": com_tables(source), "read_by": "AutoCAD's own reader (ObjectDBX); the file was not opened on screen"}
    finally:
        del source


@mcp.tool(
    name="autocad_check_standards",
    **tool_meta("Check Drawing Standards", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_check_standards(
    rules: Annotated[
        dict | None,
        Field(description=(
            "Rules: layer_name_pattern (regex), layers {name: {color, linetype}}, "
            "forbid_entities_on_layer_0, require_bylayer_color, require_bylayer_linetype, "
            "forbid_overlapping_dimensions, max_findings."
        )),
    ] = None,
    rules_path: Annotated[str | None, Field(description="Or a JSON file holding the same rules.")] = None,
    reference: Annotated[
        str | None,
        Field(description=(
            "A reference drawing to compare with: the office standards file (.dws), a template "
            "(.dwt) or any .dwg / .dxf. Its layers, text styles, dimension styles and linetypes are "
            "compared with this drawing's. With or without rules."
        )),
    ] = None,
    flag_extra: Annotated[
        bool,
        Field(description="With a reference: also list layers and styles this drawing has that the reference does not."),
    ] = True,
    max_entities: Annotated[int, Field(ge=1, le=200000, description="Stop reading entities after this many.")] = 20000,
) -> str:
    """Check the drawing's layers and objects against layer standards, or against a reference drawing.

    Rules: a layer name pattern, required layers with colour and linetype,
    nothing on layer 0, ByLayer colours and linetypes, overlapping dimensions.
    A reference drawing (the office .dws, a template, any .dwg or .dxf): every
    layer, text style, dimension style and linetype it has must be in this
    drawing with the same values - layers by colour, linetype, lineweight and
    plot; text styles by font, big font, height, width and oblique angle;
    dimension styles and linetypes by name only. Names this drawing has and
    the reference does not are listed too (flag_extra). A DXF reference is
    read by Heron itself, a DWG or DWS by the ODA File Converter when it is on
    this PC, else by AutoCAD's own reader without opening it on screen; the
    answer says which. Nothing is changed in either drawing.

    "passed": true means every rule given was met for what Heron read,
    against the rules or the reference named in "source"; null means not
    decided, because only part of the objects was read. It never means the
    drawing complies with a code or standard: Heron does not sign drawings
    off, and the answer must not say so (D-64).

    Returns:
        JSON: {"checked", "passed", "source", "pass_means", "summary" {rule: count},
               "findings" [...], "truncated", "reference" {"file", "read_by",
               "compared", "left_out"}}

    Examples:
        - Use when: "does this drawing follow our layer standard" - before
          issuing it, with the findings worst first.
        - Use when: "check this drawing against our office DWS" or "against
          the template S:\\CAD\\MEP.dwt" -> reference; the layers and styles
          that are missing or differ.
        - Use when: after a batch of drawing, to catch objects left on the
          wrong layer.
        - Don't use when: you want it put right rather than reported -
          autocad_remap_layers and autocad_tidy_entities do that, and
          autocad_import_from_drawing brings missing layers and styles in from
          the standard.
        - Don't use when: the modeller's own check list is wanted -
          autocad_checklist.
    """
    has_rules = bool(rules) or bool(rules_path)
    wanted = _load_rules(rules, rules_path) if has_rules or not reference else {}
    reference_path = _reference_path(reference) if reference else None
    found: dict[str, Any] = {}
    if reference_path:
        found["reference"], found["note"] = await _reference_from_file(reference_path)
    needs_entities = any(
        wanted.get(key) for key in ("forbid_entities_on_layer_0", "require_bylayer_color", "require_bylayer_linetype",
                                    "forbid_overlapping_dimensions")
    )

    def work() -> dict[str, Any]:
        doc = get_doc()
        layers = [describe_layer(doc.Layers.Item(i)) for i in range(doc.Layers.Count)]
        entities: list[dict] = []
        capped = False
        if needs_entities:
            sel = select_filtered(doc)
            try:
                for entity in iter_selection(sel):
                    if len(entities) >= max_entities:
                        capped = True
                        break
                    row = {
                        "handle": str(entity.Handle),
                        "type": str(entity.ObjectName),
                        "layer": str(entity.Layer),
                        "color": int(entity.Color),
                        "linetype": str(entity.Linetype),
                    }
                    if "Dimension" in row["type"] and wanted.get("forbid_overlapping_dimensions"):
                        try:
                            lo, hi = entity.GetBoundingBox()
                            row["box"] = (lo[0], lo[1], hi[0], hi[1])
                        except BaseException:  # noqa: BLE001
                            pass
                    entities.append(row)
            finally:
                discard_selection_set(doc)
        more: list[dict[str, Any]] = []
        sources = []
        if has_rules:
            sources.append(f"the rules file {rules_path}" if not rules and rules_path else "the rules given in this chat")
        if reference_path:
            standard = found["reference"] or _reference_from_autocad(reference_path)
            here = com_tables(doc, layers)
            more = standard_compare.compare(here, standard["tables"], flag_extra)
            sources.append(f"the reference drawing {reference_path}")
        report = check(layers, entities, wanted, more)
        report["source"] = " and ".join(sources)
        report["pass_means"] = PASS_MEANS
        if reference_path:
            report["checked"]["reference"] = standard_compare.counted(standard["tables"])
            report["reference"] = {
                "file": reference_path,
                "read_by": standard["read_by"],
                "compared": standard_compare.COMPARED,
                "left_out": standard_compare.LEFT_OUT,
            }
            if found["note"]:
                report["reference"]["note"] = found["note"]
            if found["reference"]:
                report["reference"]["saved_only"] = dxf_file.SAVED_ONLY
            # A reference that was damaged, or holds nothing to compare, never gives a PASS (D-64).
            doubts = []
            if standard.get("recovered"):
                doubts.append(f"The reference file has damage: ezdxf's recover mode put {standard['recovered']} "
                              "problem(s) right while reading it, so part of it may be missing.")  # fmt: skip
            if not any(standard_compare.comparable(standard["tables"]).values()):
                doubts.append("The reference holds no layers, styles or linetypes beyond the ones every drawing has.")
            if doubts:
                report["reference"]["warning"] = " ".join(doubts)
                if report["passed"]:
                    report["passed"] = None
                    report["reference"]["warning"] += " Nothing was found to differ, but that is not decided."
        if capped:
            report["warning"] = f"Only the first {max_entities} objects were read; raise max_entities to read more."
            if report["passed"]:
                # Nothing wrong in the part read is not a pass for the whole drawing (D-64).
                report["passed"] = None
                report["warning"] += " Nothing was found in the part read, so it is not decided."
        return report

    return dumps(await run(work))


@mcp.tool(
    name="autocad_extract_attributes",
    **tool_meta("Extract Block Attributes", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_extract_attributes(
    block_name: Annotated[str | None, Field(description="Only this block (effective name). Default: every block with attributes.")] = None,
    layer: Annotated[str | None, Field(description="Only blocks on this layer.")] = None,
    output: Annotated[Literal["json", "csv"], Field(description="json rows, or CSV text with one column per tag.")] = "json",
) -> str:
    """List every block reference's attributes as rows, for schedules.

    Use for "make a camera schedule", "list all equipment tags", or to check
    tag values. Rows: block, handle, layer, insertion point, attributes.

    Examples:
        - Use when: "give me the camera schedule from the drawing" -> rows of
          tag values you can hand to autocad_add_table.
        - Use when: checking an import: it shows which tags are empty.
    """

    def work() -> list[dict[str, Any]]:
        doc = get_doc()
        sel = select_filtered(doc, entity_type="insert", layer=layer)
        rows: list[dict[str, Any]] = []
        try:
            for ref in iter_selection(sel):
                try:
                    if not ref.HasAttributes:
                        continue
                    name = str(getattr(ref, "EffectiveName", None) or ref.Name)
                except BaseException:  # noqa: BLE001 - not a block reference after all
                    continue
                if block_name and name.lower() != block_name.lower():
                    continue
                rows.append({
                    "block": name,
                    "handle": str(ref.Handle),
                    "layer": str(ref.Layer),
                    "insertion": point_to_list(ref.InsertionPoint),
                    "attributes": read_attributes(ref),
                })
        finally:
            discard_selection_set(doc)
        return rows

    rows = await run(work)
    if output == "csv":
        return rows_to_csv(rows)
    return dumps({"count": len(rows), "rows": rows})
