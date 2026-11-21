"""Drawing standards check and block-attribute extraction.

Both only read. The rule checking and the CSV writing are plain functions over
plain data, so they are tested without AutoCAD; the tools only gather that data
over COM.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import geometry
from ..acad.checklist import PASS_MEANS
from ..acad.entities import read_attributes
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import describe_layer
from ..core.connection import get_doc, run
from ..core.errors import AutocadError
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


def check(layers: list[dict], entities: list[dict], rules: dict) -> dict[str, Any]:
    """Check layers and entities against a rules dict. Pure: no AutoCAD here.

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
        raise AutocadError("Give the rules, either inline as 'rules' or as a JSON file path in 'rules_path'.")
    path = os.path.expandvars(os.path.expanduser(rules_path.strip().strip('"')))
    try:
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
    except (OSError, ValueError) as exc:
        raise AutocadError(f"Could not read the rules file {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise AutocadError("The rules file must hold one JSON object.")
    return loaded


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
    max_entities: Annotated[int, Field(ge=1, le=200000, description="Stop reading entities after this many.")] = 20000,
) -> str:
    """Check the drawing's layers and objects against layer standards.

    "passed": true means every rule given was met for what Heron read,
    against the rules named in "source" (the file, or the rules given in the
    chat); null means not decided, because only part of the objects was read.
    It never means the drawing complies with a code or standard: Heron does
    not sign drawings off, and the answer must not say so (D-64).

    Returns:
        JSON: {"checked", "passed", "source", "pass_means", "summary" {rule: count},
               "findings" [...], "truncated"}

    Examples:
        - Use when: "does this drawing follow our layer standard" - before
          issuing it, with the findings worst first.
        - Use when: after a batch of drawing, to catch objects left on the
          wrong layer.
        - Don't use when: you want it put right rather than reported -
          autocad_remap_layers and autocad_tidy_entities do that.
    """
    wanted = _load_rules(rules, rules_path)
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
        report = check(layers, entities, wanted)
        report["source"] = f"the rules file {rules_path}" if not rules and rules_path else "the rules given in this chat"
        report["pass_means"] = PASS_MEANS
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
