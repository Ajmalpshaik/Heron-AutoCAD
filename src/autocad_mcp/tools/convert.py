"""Turning an imported drawing into a shop drawing.

An IFC or Revit export lands in AutoCAD as geometry, not as a drawing. Layers
called ``IfcWallStandardCase`` or nothing but layer 0; colour and linetype set
on every object instead of on the layer; a Z value on work that should be flat;
no lineweights; nothing that plots the way an issued sheet has to.

Two tools cover that:

* ``autocad_remap_layers`` puts everything on the right layer, and makes those
  layers with the colour, linetype, lineweight and plot setting they should
  have. Rules match on the old layer name, the block name, the object type or
  the colour, so the same call handles a well-layered import and one that came
  in on layer 0.
* ``autocad_tidy_entities`` clears the per-object overrides so the layers do
  their job, flattens the work to one level, and clears out the zero-length
  rubbish an export leaves behind.

Both take ``dry_run``, which is how you use them: look at the plan, agree it,
then run it. The planning is pure Python and tested without AutoCAD; only the
writing needs AutoCAD.

The built-in ``ifc`` rules are a **starting point**, not a standard: they map
the usual IFC class words onto AIA-style discipline layers. Pass your own
``rules`` (or ``rules_path``) for an office standard, and
``autocad_check_standards`` afterwards to prove the result.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.entities import resolve_handles, short_type
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import describe_layer, ensure_layer, ensure_linetype, validate_name
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint

BYLAYER_COLOR = 256
BYLAYER = "ByLayer"
# AutoCAD's own "take the lineweight from the layer" value.
LW_BYLAYER = -1

# What an IFC or Revit export usually calls things, mapped onto AIA-style
# discipline layers. Order matters: the first rule that matches wins, so
# cable carrier is listed before cable, and air terminal before duct.
IFC_RULES: tuple[dict[str, Any], ...] = (
    {"name_like": "*cablecarrier*", "layer": "E-CABL-TRAY", "color": 6},
    {"name_like": "*cabletray*", "layer": "E-CABL-TRAY", "color": 6},
    {"name_like": "*cable*", "layer": "E-CABL", "color": 6},
    {"name_like": "*distributionboard*", "layer": "E-POWR-PANL", "color": 6},
    {"name_like": "*light*", "layer": "E-LITE", "color": 2},
    {"name_like": "*electric*", "layer": "E-POWR", "color": 6},
    {"name_like": "*airterminal*", "layer": "M-HVAC-DIFF", "color": 4},
    {"name_like": "*duct*", "layer": "M-HVAC-DUCT", "color": 4},
    {"name_like": "*sprinkler*", "layer": "F-PROT-SPRN", "color": 1},
    {"name_like": "*fire*", "layer": "F-PROT", "color": 1},
    {"name_like": "*valve*", "layer": "P-PIPE-VALV", "color": 1},
    {"name_like": "*sanitary*", "layer": "P-SANR", "color": 5},
    {"name_like": "*pipe*", "layer": "P-PIPE", "color": 5},
    {"name_like": "*reinforc*", "layer": "S-RBAR", "color": 1},
    {"name_like": "*beam*", "layer": "S-BEAM", "color": 2},
    {"name_like": "*column*", "layer": "S-COLS", "color": 2},
    {"name_like": "*footing*", "layer": "S-FNDN", "color": 2},
    {"name_like": "*grid*", "layer": "S-GRID", "color": 9, "linetype": "CENTER"},
    {"name_like": "*member*", "layer": "S-FRAM", "color": 2},
    {"name_like": "*door*", "layer": "A-DOOR", "color": 4},
    {"name_like": "*window*", "layer": "A-GLAZ", "color": 4},
    {"name_like": "*wall*", "layer": "A-WALL", "color": 8},
    {"name_like": "*stair*", "layer": "A-FLOR-STRS", "color": 3},
    {"name_like": "*railing*", "layer": "A-FLOR-HRAL", "color": 3},
    {"name_like": "*slab*", "layer": "A-FLOR", "color": 8},
    {"name_like": "*roof*", "layer": "A-ROOF", "color": 8},
    {"name_like": "*covering*", "layer": "A-FINF", "color": 9},
    {"name_like": "*furnishing*", "layer": "A-FURN", "color": 9},
    {"name_like": "*space*", "layer": "A-AREA", "color": 9, "plot": False},
    {"name_like": "*site*", "layer": "C-SITE", "color": 3},
    {"entity_type": "text", "layer": "G-ANNO-TEXT", "color": 7},
    {"entity_type": "mtext", "layer": "G-ANNO-TEXT", "color": 7},
    {"entity_type": "dimension", "layer": "G-ANNO-DIMS", "color": 7},
    {"entity_type": "mleader", "layer": "G-ANNO-TEXT", "color": 7},
    {"entity_type": "hatch", "layer": "G-ANNO-PATT", "color": 8},
)

PRESETS: dict[str, tuple[dict[str, Any], ...]] = {"ifc": IFC_RULES}

# What a rule may say. The two halves are deliberately spelled differently:
# source_* and the rest of MATCH_KEYS pick the objects, "color" and the rest
# describe the layer they go to. Using one "color" for both would have a rule
# that paints A-WALL grey quietly match only objects that are already grey.
MATCH_KEYS = frozenset(
    {"name_like", "source_layer", "source_color", "entity_type", "block_name", "text_contains"}
)
TARGET_KEYS = frozenset(
    {"layer", "color", "linetype", "lineweight", "description", "plot", "lock", "freeze", "new_color"}
)
RULE_KEYS = MATCH_KEYS | TARGET_KEYS


# ---------------------------------------------------------------------------
# Planning (pure: no AutoCAD below this line)
# ---------------------------------------------------------------------------


def _matches(pattern: str, value: str) -> bool:
    """A wildcard or /regex/ test, case-insensitive, as AutoCAD users expect."""
    text = str(value or "")
    want = str(pattern or "")
    if len(want) > 1 and want.startswith("/") and want.endswith("/"):
        return re.search(want[1:-1], text, re.IGNORECASE) is not None
    return fnmatch.fnmatch(text.lower(), want.lower())


def rule_hits(entity: dict[str, Any], rule: dict[str, Any]) -> bool:
    """Whether one rule applies to one object. Every criterion given must hold.

    ``name_like`` is the one that earns its keep on an import: it matches the
    object's layer name *or* its block name, because an exporter puts the
    element type in one or the other and you rarely know which.
    """
    layer = str(entity.get("layer", ""))
    block = str(entity.get("block_name", "") or "")
    if "name_like" in rule and not (
        _matches(rule["name_like"], layer) or (block and _matches(rule["name_like"], block))
    ):
        return False
    if "source_layer" in rule and not _matches(rule["source_layer"], layer):
        return False
    if "block_name" in rule and not (block and _matches(rule["block_name"], block)):
        return False
    if "entity_type" in rule and str(entity.get("type", "")).lower() != str(rule["entity_type"]).lower():
        return False
    if "source_color" in rule and int(entity.get("color", BYLAYER_COLOR)) != int(rule["source_color"]):
        return False
    if "text_contains" in rule:
        text = str(entity.get("text", "") or "")
        if str(rule["text_contains"]).lower() not in text.lower():
            return False
    return True


def validate_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check a rule list before a single object is touched.

    Every rule needs a target layer and at least one thing to match on;
    a rule that matches everything would sweep the whole drawing onto one
    layer, which is never what was meant.
    """
    if not rules:
        raise ValueError("no rules given: each rule needs something to match and a target layer")
    checked = []
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(f"rule {i} is {rule!r}; each rule must be an object")
        stray = sorted(set(rule) - RULE_KEYS)
        if stray:
            raise ValueError(
                f"rule {i} has unknown keys: {', '.join(stray)}. Known keys: "
                + ", ".join(sorted(RULE_KEYS))
            )
        if not str(rule.get("layer", "")).strip():
            raise ValueError(f"rule {i} has no target 'layer'")
        if not MATCH_KEYS & set(rule):
            raise ValueError(
                f"rule {i} ('{rule['layer']}') matches nothing in particular, so it would move "
                "the whole drawing. Give it one of: " + ", ".join(sorted(MATCH_KEYS)) + ". "
                "('color' sets the target layer's colour; to match an object's own colour "
                "use 'source_color'.)"
            )
        checked.append(dict(rule))
    return checked


def plan_remap(
    entities: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    unmatched_layer: str | None = None,
) -> dict[str, Any]:
    """Which object goes to which layer, and what those layers should look like.

    Pure, so the whole decision can be read and checked before anything moves.
    The first matching rule wins, which is why rule order is part of the rules.
    """
    checked = validate_rules(rules)
    moves: list[dict[str, Any]] = []
    layers: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    per_rule: dict[str, int] = {}

    for entity in entities:
        hit = next((r for r in checked if rule_hits(entity, r)), None)
        if hit is None:
            unmatched.append(str(entity.get("handle", "")))
            if not unmatched_layer:
                continue
            hit = {"layer": unmatched_layer}
        target = str(hit["layer"]).strip()
        wanted = {k: v for k, v in hit.items() if k in ("color", "linetype", "lineweight", "description", "plot", "lock", "freeze")}
        if target in layers:
            layers[target].update(wanted)
        else:
            layers[target] = wanted
        label = str(
            hit.get("name_like") or hit.get("source_layer") or hit.get("block_name")
            or hit.get("entity_type") or hit.get("text_contains")
            or (f"colour {hit['source_color']}" if "source_color" in hit else "")
            or "unmatched"
        )
        per_rule[f"{label} -> {target}"] = per_rule.get(f"{label} -> {target}", 0) + 1
        if str(entity.get("layer", "")).strip().lower() == target.lower():
            continue
        moves.append(
            {
                "handle": str(entity.get("handle", "")),
                "type": entity.get("type"),
                "from": entity.get("layer"),
                "to": target,
                "new_color": hit.get("new_color"),
            }
        )

    return {
        "moves": moves,
        "layers": layers,
        "unmatched": unmatched,
        "counts": {
            "read": len(entities),
            "to_move": len(moves),
            "already_right": len(entities) - len(moves) - (0 if unmatched_layer else len(unmatched)),
            "unmatched": len(unmatched),
            "layers_wanted": len(layers),
        },
        "by_rule": dict(sorted(per_rule.items(), key=lambda kv: -kv[1])),
    }


def plan_tidy(entities: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, Any]:
    """What tidying would do to each object, worked out before anything is written."""
    jobs: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    def note(handle: str, kind: str, detail: Any = None) -> None:
        jobs.append({"handle": handle, "do": kind, "detail": detail})
        counts[kind] = counts.get(kind, 0) + 1

    flat_to = options.get("flatten_z")
    layer_0_to = str(options.get("off_layer_0") or "").strip()

    for entity in entities:
        handle = str(entity.get("handle", ""))
        if options.get("color_bylayer") and int(entity.get("color", BYLAYER_COLOR)) != BYLAYER_COLOR:
            note(handle, "color_bylayer", entity.get("color"))
        if options.get("linetype_bylayer") and str(entity.get("linetype", "")).lower() != BYLAYER.lower():
            note(handle, "linetype_bylayer", entity.get("linetype"))
        if options.get("lineweight_bylayer") and entity.get("lineweight") not in (None, LW_BYLAYER):
            note(handle, "lineweight_bylayer", entity.get("lineweight"))
        if options.get("zero_thickness") and float(entity.get("thickness") or 0.0) != 0.0:
            note(handle, "zero_thickness", entity.get("thickness"))
        if flat_to is not None:
            level = entity.get("elevation")
            if level is not None and abs(float(level) - float(flat_to)) > 1e-9:
                note(handle, "flatten_z", round(float(level), 6))
        if layer_0_to and str(entity.get("layer", "")).strip() == "0":
            note(handle, "off_layer_0", layer_0_to)
        if options.get("delete_empty") and entity.get("empty"):
            note(handle, "delete_empty", entity.get("type"))

    return {"jobs": jobs, "counts": counts, "read": len(entities)}


def load_rules(
    rules: list[dict[str, Any]] | None, rules_path: str | None, preset: str | None
) -> list[dict[str, Any]]:
    """The rules to use: given inline, read from a JSON file, or a built-in preset."""
    if rules:
        return [dict(r) for r in rules]
    if rules_path:
        path = os.path.expandvars(os.path.expanduser(str(rules_path).strip().strip('"')))
        try:
            with open(path, encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, ValueError) as exc:
            raise AutocadError(f"Could not read the rules file {path}: {exc}") from exc
        if isinstance(loaded, dict):
            loaded = loaded.get("rules")
        if not isinstance(loaded, list):
            raise AutocadError(
                f"{path} must hold a JSON list of rules, or an object with a 'rules' list."
            )
        return [dict(r) for r in loaded]
    if preset:
        key = str(preset).strip().lower()
        if key not in PRESETS:
            raise AutocadError(
                f"'{preset}' is not a built-in rule set. Available: {', '.join(sorted(PRESETS))}."
            )
        return [dict(r) for r in PRESETS[key]]
    raise AutocadError(
        "Say which rules to use: 'rules' inline, 'rules_path' to a JSON file, or "
        f"preset='ifc' for the built-in starting point ({len(IFC_RULES)} rules)."
    )


# ---------------------------------------------------------------------------
# The AutoCAD side
# ---------------------------------------------------------------------------


def _read(target: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(target, name)
    except BaseException as exc:  # noqa: BLE001 - absent properties are expected here
        raise_if_busy(exc)
        return default


def _snapshot(entity: Any, deep: bool = False) -> dict[str, Any]:
    """One object as the flat dict the planners read."""
    row: dict[str, Any] = {
        "handle": str(_read(entity, "Handle", "")),
        "type": short_type(entity),
        "layer": str(_read(entity, "Layer", "")),
        "color": int(_read(entity, "Color", BYLAYER_COLOR) or BYLAYER_COLOR),
        "linetype": str(_read(entity, "Linetype", "") or ""),
    }
    if row["type"] == "block":
        row["block_name"] = str(_read(entity, "EffectiveName", "") or _read(entity, "Name", "") or "")
    if row["type"] in ("text", "mtext"):
        row["text"] = str(_read(entity, "TextString", "") or "")
    if not deep:
        return row
    row["lineweight"] = _read(entity, "Lineweight")
    row["thickness"] = _read(entity, "Thickness")
    row["elevation"] = _level_of(entity)
    row["empty"] = _is_empty(entity, row)
    return row


def _level_of(entity: Any) -> float | None:
    """The Z an object sits at, however its type spells it."""
    for name in ("Elevation",):
        value = _read(entity, name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    for name in ("InsertionPoint", "Center", "StartPoint", "Coordinates"):
        value = _read(entity, name)
        if value is None:
            continue
        try:
            flat = [float(v) for v in value]
        except (TypeError, ValueError):
            continue
        if len(flat) >= 3:
            return flat[2]
    return None


def _is_empty(entity: Any, row: dict[str, Any]) -> bool:
    """Zero-length lines, zero-radius circles and blank text: export leftovers."""
    kind = row["type"]
    if kind in ("line", "polyline", "polyline2d", "polyline3d", "arc", "spline"):
        length = _read(entity, "Length") or _read(entity, "ArcLength")
        return length is not None and abs(float(length)) < 1e-9
    if kind == "circle":
        radius = _read(entity, "Radius")
        return radius is not None and abs(float(radius)) < 1e-9
    if kind in ("text", "mtext"):
        return not str(row.get("text", "")).strip()
    return False


def _gather(doc: Any, layer: str | None, entity_type: str | None, handles: list[str] | None,
            limit: int, deep: bool) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    """Read the objects in scope, as plain dicts plus the COM objects by handle."""
    rows: list[dict[str, Any]] = []
    objects: dict[str, Any] = {}
    capped = False
    if handles:
        for entity in resolve_handles(doc, handles):
            row = _snapshot(entity, deep)
            rows.append(row)
            objects[row["handle"]] = entity
        return rows, objects, capped
    sel = select_filtered(doc, entity_type=entity_type, layer=layer)
    try:
        for entity in iter_selection(sel):
            if len(rows) >= limit:
                capped = True
                break
            row = _snapshot(entity, deep)
            rows.append(row)
            objects[row["handle"]] = entity
    finally:
        discard_selection_set(doc)
    return rows, objects, capped


def _apply_layer_properties(doc: Any, name: str, wanted: dict[str, Any]) -> dict[str, Any]:
    """Create a layer if needed and set the properties a rule asked for."""
    layer, created = ensure_layer(doc, name)
    notes: list[str] = []
    aci = to_aci(wanted.get("color")) if wanted.get("color") is not None else None
    if aci is not None and not _set(layer, "Color", aci):
        notes.append("the colour was refused")
    if wanted.get("linetype"):
        try:
            ensure_linetype(doc, str(wanted["linetype"]))
            if not _set(layer, "Linetype", str(wanted["linetype"]).strip()):
                notes.append("the linetype was refused")
        except AutocadError as exc:
            notes.append(str(exc))
    if wanted.get("lineweight") is not None and not _set(layer, "Lineweight", int(wanted["lineweight"])):
        notes.append("the lineweight was refused")
    if wanted.get("description") and not _set(layer, "Description", str(wanted["description"])):
        notes.append("the description was refused")
    if wanted.get("plot") is not None and not _set(layer, "Plottable", bool(wanted["plot"])):
        notes.append("the plot setting was refused")
    if wanted.get("freeze") is not None:
        _set(layer, "Freeze", bool(wanted["freeze"]))
    if wanted.get("lock") is not None:
        _set(layer, "Lock", bool(wanted["lock"]))
    row = describe_layer(layer)
    row["created"] = created
    if notes:
        row["notes"] = notes
    return row


def _set(target: Any, name: str, value: Any) -> bool:
    """Set one COM property; False when AutoCAD refused it."""
    try:
        setattr(target, name, value)
        return True
    except BaseException as exc:  # noqa: BLE001 - a refusal is the answer
        raise_if_busy(exc)
        return False


@mcp.tool(name="autocad_remap_layers", **tool_meta("Put Everything On The Right Layers"))
@tool_errors
async def autocad_remap_layers(
    rules: Annotated[
        list[dict[str, Any]] | None,
        Field(
            default=None,
            description=(
                "Rules in order; the first that matches an object wins. Each is an object:\n"
                '{"name_like": "*duct*", "layer": "M-HVAC-DUCT", "color": 4, '
                '"linetype": "CONTINUOUS", "lineweight": 25, "plot": true, '
                '"description": "Supply ductwork"}\n'
                "Match on any of: name_like (the object's layer OR block name), "
                "source_layer, block_name, entity_type, source_color, text_contains. "
                "Wildcards work (*duct*), and /regex/ between slashes. Every rule "
                "needs a target 'layer' and at least one thing to match on.\n"
                "'color' is the TARGET layer's colour; to match an object's own "
                "colour use 'source_color'. 'new_color' overrides the moved "
                "objects themselves, which a shop drawing rarely wants."
            ),
        ),
    ] = None,
    rules_path: Annotated[str | None, Field(default=None, description="Or a JSON file holding the same list — your office layer standard, kept in one place.")] = None,
    preset: Annotated[
        Literal["ifc"] | None,
        Field(default=None, description="Or the built-in starting point: 'ifc' maps the usual IFC and Revit class words onto AIA-style discipline layers. Read the result and refine it; it is a head start, not a standard."),
    ] = None,
    layer: Annotated[str | None, Field(default=None, description="Only look at objects on this layer; AutoCAD wildcards work, e.g. 'Ifc*'.")] = None,
    entity_type: Annotated[str | None, Field(default=None, description="Only look at this type: line, polyline, text, block, hatch, dimension ...")] = None,
    handles: Annotated[list[str] | None, Field(default=None, description="Or only these objects, by handle.")] = None,
    unmatched_layer: Annotated[str | None, Field(default=None, description="Put anything no rule matched on this layer, e.g. 'X-REVIEW', so nothing is quietly left behind. Omit to leave them where they are.")] = None,
    set_bylayer: Annotated[bool, Field(default=False, description="Also clear each moved object's own colour and linetype, so the new layer actually decides how it looks. This is what makes an import plot correctly.")] = False,
    dry_run: Annotated[bool, Field(default=True, description="Report the plan and change nothing. On by default: look at the counts first, then run it again with dry_run=false.")] = True,
    max_entities: Annotated[int, Field(default=20000, ge=1, le=200000, description="Stop reading after this many objects.")] = 20000,
) -> str:
    """Put an imported drawing's objects on proper layers, and make those layers properly.

    This is the first half of turning an IFC or Revit export into a shop
    drawing. Rules match on the old layer name, the block name, the object
    type, the colour or the text, and say which layer the object belongs on and
    what that layer should look like. Missing layers are created with the
    colour, linetype, lineweight, description and plot setting given.

    **dry_run is on by default.** Read "by_rule" and "counts", check nothing
    unexpected is being swept up, then run again with dry_run=false. One undo
    step.

    Args:
        rules (Optional[list[dict]]): the rules; see the field description.
        rules_path (Optional[str]): or a JSON file of the same.
        preset (Optional[str]): or 'ifc' for the built-in starting point.
        layer / entity_type / handles: narrow what is looked at.
        unmatched_layer (Optional[str]): where to put the leftovers.
        set_bylayer (bool): clear the objects' own colour and linetype too.
        dry_run (bool): report only (default true).
        max_entities (int): read no more than this many.

    Returns:
        str: JSON: {
          "dry_run": bool,
          "counts": {"read", "to_move", "already_right", "unmatched", "layers_wanted"},
          "by_rule": {"*duct* -> M-HVAC-DUCT": 412, ...},
          "layers": [{name, color, linetype, lineweight, plottable, created}],
          "moved": int, "failed": [{"handle", "to", "reason"}],
          "unmatched_sample": [str], "moves_sample": [{...}]
        }

    Examples:
        - Use when: "this IFC came in on IfcWall, IfcDoor... make it a shop
          drawing" — preset='ifc', read the plan, then dry_run=false.
        - Use when: "everything is on layer 0" — rules matching block_name.
        - Use when: an office standard must be applied — rules_path.
        - Don't use when: you only want to know what is wrong
          (autocad_check_standards reports without changing anything).

    Error Handling:
        - A rule with no target layer, or with nothing to match on, is refused
          before any object is touched: a rule that matches everything would
          sweep the drawing onto one layer.
        - A locked or frozen target layer is reported per object in "failed";
          the rest of the move still lands.
    """
    wanted = load_rules(rules, rules_path, preset)
    try:
        wanted = validate_rules(wanted)
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    if unmatched_layer:
        validate_name(unmatched_layer, "layer")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        rows, objects, capped = _gather(doc, layer, entity_type, handles, max_entities, deep=False)
        report = plan_remap(rows, wanted, unmatched_layer)

        result: dict[str, Any] = {
            "dry_run": dry_run,
            "counts": report["counts"],
            "by_rule": report["by_rule"],
            "moves_sample": report["moves"][:25],
            "unmatched_sample": report["unmatched"][:25],
        }
        if capped:
            result["warning"] = (
                f"Only the first {max_entities} objects were read; raise max_entities to cover "
                "the whole drawing."
            )
        if dry_run:
            result["layers"] = [{"name": name, **props} for name, props in sorted(report["layers"].items())]
            result["hint"] = (
                "Nothing was changed. Check the counts and by_rule above, then call again with "
                "dry_run=false."
            )
            return result

        moved, failed = 0, []
        with undo_mark(doc):
            result["layers"] = [
                _apply_layer_properties(doc, name, props)
                for name, props in sorted(report["layers"].items())
            ]
            for move in report["moves"]:
                entity = objects.get(move["handle"])
                if entity is None:  # pragma: no cover - handle vanished mid-call
                    failed.append({"handle": move["handle"], "to": move["to"], "reason": "no longer in the drawing"})
                    continue
                try:
                    entity.Layer = move["to"]
                except BaseException as exc:  # noqa: BLE001 - usually a locked layer
                    raise_if_busy(exc)
                    failed.append({"handle": move["handle"], "to": move["to"], "reason": com_message(exc)})
                    continue
                moved += 1
                if move.get("new_color") is not None:
                    _set(entity, "Color", to_aci(move["new_color"]))
                elif set_bylayer:
                    _set(entity, "Color", BYLAYER_COLOR)
                    _set(entity, "Linetype", BYLAYER)
                    _set(entity, "Lineweight", LW_BYLAYER)
        result["moved"] = moved
        result["failed"] = failed
        return result

    return dumps(await run(work))


@mcp.tool(name="autocad_tidy_entities", **tool_meta("Tidy Up Imported Geometry"))
@tool_errors
async def autocad_tidy_entities(
    color_bylayer: Annotated[bool, Field(default=True, description="Clear each object's own colour so its layer decides. An import sets colour per object, which is why layer changes seem to do nothing.")] = True,
    linetype_bylayer: Annotated[bool, Field(default=True, description="Clear each object's own linetype so its layer decides.")] = True,
    lineweight_bylayer: Annotated[bool, Field(default=True, description="Clear each object's own lineweight so its layer decides, and the sheet plots with real line weights.")] = True,
    flatten_z: Annotated[float | None, Field(default=None, description="Bring everything to one level, usually 0. A plan exported from a model carries the real Z and will not trim, fillet or hatch properly.")] = None,
    zero_thickness: Annotated[bool, Field(default=False, description="Set extruded thickness back to zero, so 2D work stops casting a 3D shadow.")] = False,
    off_layer_0: Annotated[str | None, Field(default=None, description="Move anything on layer 0 to this layer, e.g. 'X-REVIEW'. Geometry on layer 0 is the single most common reason an issued drawing plots wrong.")] = None,
    delete_empty: Annotated[bool, Field(default=False, description="Delete zero-length lines, zero-radius circles and blank text — the rubbish an export leaves behind.")] = False,
    layer: Annotated[str | None, Field(default=None, description="Only tidy objects on this layer; wildcards work.")] = None,
    entity_type: Annotated[str | None, Field(default=None, description="Only tidy this type.")] = None,
    handles: Annotated[list[str] | None, Field(default=None, description="Or only these objects, by handle.")] = None,
    dry_run: Annotated[bool, Field(default=True, description="Report what would be done and change nothing. On by default.")] = True,
    max_entities: Annotated[int, Field(default=20000, ge=1, le=200000, description="Stop reading after this many objects.")] = 20000,
) -> str:
    """Clean up imported geometry: ByLayer overrides, one flat level, no leftovers.

    The second half of turning an export into a shop drawing. An IFC or Revit
    drawing comes in with colour, linetype and lineweight set on every single
    object, so changing a layer appears to do nothing; with a real Z on work
    that should be flat, so trim and hatch misbehave; and with zero-length
    rubbish nobody can select.

    **dry_run is on by default.** Read the counts, then run again with
    dry_run=false. One undo step.

    Args:
        color_bylayer / linetype_bylayer / lineweight_bylayer (bool): clear the
            per-object overrides (all on by default).
        flatten_z (Optional[float]): bring everything to one level.
        zero_thickness (bool): clear extruded thickness.
        off_layer_0 (Optional[str]): move layer-0 geometry here.
        delete_empty (bool): delete zero-length and blank objects.
        layer / entity_type / handles: narrow what is tidied.
        dry_run (bool): report only (default true).
        max_entities (int): read no more than this many.

    Returns:
        str: JSON: {
          "dry_run": bool, "read": int,
          "counts": {"color_bylayer": 1240, "flatten_z": 980, ...},
          "done": {...}, "failed": [{"handle", "do", "reason"}],
          "deleted": int, "sample": [{...}]
        }

    Examples:
        - Use when: "I changed the layer colour and nothing happened" —
          color_bylayer on its own.
        - Use when: "the plan will not hatch" — flatten_z=0.
        - Use when: after autocad_remap_layers, to finish the job.
        - Don't use when: the overrides are deliberate; this clears them all
          within the scope you give, so narrow it with layer or entity_type.

    Error Handling:
        - A locked or frozen layer is reported per object in "failed"; the rest
          still lands.
        - Nothing is deleted unless delete_empty is passed, and never on a
          dry run.
    """
    options = {
        "color_bylayer": color_bylayer,
        "linetype_bylayer": linetype_bylayer,
        "lineweight_bylayer": lineweight_bylayer,
        "flatten_z": flatten_z,
        "zero_thickness": zero_thickness,
        "off_layer_0": off_layer_0,
        "delete_empty": delete_empty,
    }
    if not any(v for v in options.values() if v is not None and v is not False):
        raise AutocadError(
            "Nothing to tidy. Turn on at least one of: color_bylayer, linetype_bylayer, "
            "lineweight_bylayer, flatten_z, zero_thickness, off_layer_0, delete_empty."
        )
    if off_layer_0:
        validate_name(off_layer_0, "layer")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        rows, objects, capped = _gather(doc, layer, entity_type, handles, max_entities, deep=True)
        report = plan_tidy(rows, options)

        result: dict[str, Any] = {
            "dry_run": dry_run,
            "read": report["read"],
            "counts": report["counts"],
            "sample": report["jobs"][:25],
        }
        if capped:
            result["warning"] = (
                f"Only the first {max_entities} objects were read; raise max_entities to cover "
                "the whole drawing."
            )
        if dry_run:
            result["hint"] = "Nothing was changed. Call again with dry_run=false to do it."
            return result

        done: dict[str, int] = {}
        failed: list[dict[str, Any]] = []
        deleted = 0
        with undo_mark(doc):
            if off_layer_0:
                ensure_layer(doc, off_layer_0)
            for job in report["jobs"]:
                entity = objects.get(job["handle"])
                if entity is None:  # pragma: no cover - handle vanished mid-call
                    continue
                kind = job["do"]
                if kind == "delete_empty":
                    try:
                        entity.Delete()
                        deleted += 1
                        done[kind] = done.get(kind, 0) + 1
                    except BaseException as exc:  # noqa: BLE001
                        raise_if_busy(exc)
                        failed.append({"handle": job["handle"], "do": kind, "reason": com_message(exc)})
                    continue
                ok = {
                    "color_bylayer": lambda e: _set(e, "Color", BYLAYER_COLOR),
                    "linetype_bylayer": lambda e: _set(e, "Linetype", BYLAYER),
                    "lineweight_bylayer": lambda e: _set(e, "Lineweight", LW_BYLAYER),
                    "zero_thickness": lambda e: _set(e, "Thickness", 0.0),
                    "flatten_z": lambda e: _flatten(e, float(flatten_z)),
                    "off_layer_0": lambda e: _set(e, "Layer", str(off_layer_0).strip()),
                }[kind](entity)
                if ok:
                    done[kind] = done.get(kind, 0) + 1
                else:
                    failed.append(
                        {"handle": job["handle"], "do": kind,
                         "reason": "AutoCAD refused it — usually a locked or frozen layer"}
                    )
        result["done"] = done
        result["failed"] = failed
        result["deleted"] = deleted
        return result

    return dumps(await run(work))


def _flatten(entity: Any, level: float) -> bool:
    """Bring one object to a level, however its type holds its Z."""
    if _set(entity, "Elevation", level):
        return True
    for name in ("InsertionPoint", "Center", "StartPoint"):
        value = _read(entity, name)
        if value is None:
            continue
        try:
            flat = [float(v) for v in value]
        except (TypeError, ValueError):
            continue
        if len(flat) < 3:
            continue
        if _set(entity, name, apoint(flat[0], flat[1], level)):
            return True
    return False
