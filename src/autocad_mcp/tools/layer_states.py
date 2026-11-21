"""Layer states, isolating layers, and merging one layer into another (#107, D-81).

* **Layer states** (save, restore, delete; listed by autocad_list_layers):
  the plug-in does them with .NET's LayerStateManager, the API that could be
  checked against Autodesk's reference assemblies.
* **Isolate**: every layer but the ones asked for is turned off, frozen or
  locked, over COM. What the layers were like first is saved as a layer state,
  so un-isolating puts back exactly that, and only that.
* **Merge**: every object on the old layers moves to the new one, in model
  space, on every layout, inside block definitions and in block attributes;
  an old layer is removed only once nothing is left on it.

The rules are plain functions at the top, tested without AutoCAD.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad.entities import resolve_handles
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from . import _shared
from ._shared import before_after, in_plugin

# The bits of a layer state, as LayerStateMasks numbers them (checked in the
# AutoCAD 2021 and 2027 reference assemblies).
MASK_BITS = {
    "on": 1,
    "frozen": 2,
    "locked": 4,
    "plot": 8,
    "new_viewport_frozen": 16,
    "color": 32,
    "linetype": 64,
    "lineweight": 128,
    "plot_style": 256,
    "transparency": 1024,
}
ISOLATE_STATE = "HERON-ISOLATE"
ISOLATE_MASK = MASK_BITS["on"] | MASK_BITS["frozen"] | MASK_BITS["locked"]
CURRENT_WAS = re.compile(r"current layer was (.+?)\s*$")
COM_PROPERTY = {"on": "LayerOn", "frozen": "Freeze", "locked": "Lock"}
Others = Literal["off", "freeze", "lock"]
# A selection filter reads these as wildcards; a backtick makes them plain.
WILDCARDS = set("#@.~[]-")


# ---------------------------------------------------------------------------
# The rules (pure: no AutoCAD below this line)
# ---------------------------------------------------------------------------


def mask_of(words: Iterable[str] | None) -> int | None:
    """The mask for what a layer state should remember; None means everything."""
    if words is None:
        return None
    total = 0
    for word in words:
        key = str(word).strip().lower()
        if key not in MASK_BITS:
            raise ValueError(f"'{word}' is not something a layer state remembers. Use: {', '.join(MASK_BITS)}")
        total |= MASK_BITS[key]
    if not total:
        raise ValueError("say at least one thing for the layer state to remember, or leave 'remembers' out for all of them")
    return total


def isolate_description(current: str) -> str:
    return f"Heron: the layers before autocad_isolate_layers; current layer was {current}"


def current_from(description: str) -> str | None:
    """The current layer an isolate state says there was, or None."""
    found = CURRENT_WAS.search(str(description or ""))
    return found.group(1) if found else None


def isolate_plan(
    layers: Sequence[dict[str, Any]], keep: Sequence[str], current: str, others: str = "off"
) -> dict[str, Any]:
    """What isolating ``keep`` changes: ``{"changes": [{layer, property, from, to}], "make_current"}``.

    ``layers`` are ``{"name", "on", "frozen", "locked"}``. The kept layers are
    turned on and thawed (and unlocked when the others are locked, so they are
    the ones you can edit); every other layer is turned off, frozen or locked.
    A current layer that would be hidden hands over to the first kept layer
    first, since AutoCAD will not freeze the current layer.
    """
    if others not in ("off", "freeze", "lock"):
        raise ValueError("others must be off, freeze or lock")
    by_key = {str(layer["name"]).casefold(): layer for layer in layers}
    kept: list[str] = []
    for name in keep:
        layer = by_key.get(str(name).strip().casefold())
        if layer is None:
            raise ValueError(f"there is no layer called '{name}'")
        if str(layer["name"]) not in kept:
            kept.append(str(layer["name"]))
    if not kept:
        raise ValueError("give the objects or layers to isolate")
    kept_keys = {k.casefold() for k in kept}

    changes: list[dict[str, Any]] = []

    def want(layer: dict[str, Any], prop: str, value: bool) -> None:
        if bool(layer[prop]) != value:
            changes.append({"layer": str(layer["name"]), "property": prop, "from": bool(layer[prop]), "to": value})

    for layer in layers:
        if str(layer["name"]).casefold() in kept_keys:
            want(layer, "on", True)
            want(layer, "frozen", False)
            if others == "lock":
                want(layer, "locked", False)
        elif others == "off":
            want(layer, "on", False)
        elif others == "freeze":
            want(layer, "frozen", True)
        else:
            want(layer, "locked", True)
    hides_current = others in ("off", "freeze") and str(current).casefold() not in kept_keys
    return {"kept": kept, "changes": changes, "make_current": kept[0] if hides_current else None}


def escape_wildcards(name: str) -> str:
    """A layer name as a selection filter reads it literally."""
    return "".join(f"`{c}" if c in WILDCARDS else c for c in str(name).strip())


def check_merge(sources: Sequence[str], into: str, existing: Sequence[str]) -> tuple[list[str], str]:
    """The old layers and the new one, as the drawing names them; ValueError for a merge that cannot be."""
    by_key = {str(n).casefold(): str(n) for n in existing}
    target = by_key.get(str(into).strip().casefold())
    if target is None:
        raise ValueError(f"there is no layer called '{into}' to merge into; make it first with autocad_create_layer")
    found: list[str] = []
    for raw in sources:
        name = by_key.get(str(raw).strip().casefold())
        if name is None:
            raise ValueError(f"there is no layer called '{raw}'")
        if name.casefold() == target.casefold():
            raise ValueError(f"'{name}' is the layer being merged into; it cannot be merged into itself")
        if name == "0":
            raise ValueError("layer 0 is built into every drawing and cannot be removed, so it cannot be merged away")
        if "|" in name:
            raise ValueError(f"'{name}' belongs to an xref; change it in the xref's own drawing")
        if name not in found:
            found.append(name)
    if not found:
        raise ValueError("give at least one layer to merge")
    return found, target


def merge_targets(items: Iterable[dict[str, Any]], sources: Sequence[str]) -> list[dict[str, Any]]:
    """The objects a merge moves: on one of the old layers, exactly (case aside), each once."""
    keys = {str(s).casefold() for s in sources}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        handle = str(item.get("handle", ""))
        if str(item.get("layer", "")).casefold() not in keys or handle in seen:
            continue
        seen.add(handle)
        out.append(item)
    return out


def merge_counts(moving: Sequence[dict[str, Any]], sources: Sequence[str]) -> dict[str, dict[str, int]]:
    """How many objects each old layer holds, and where: the drawing, block definitions, attributes."""
    counts = {s: {"drawing": 0, "blocks": 0, "attributes": 0} for s in sources}
    by_key = {s.casefold(): s for s in sources}
    for item in moving:
        source = by_key[str(item["layer"]).casefold()]
        counts[source][str(item.get("where", "drawing"))] += 1
    return counts


# ---------------------------------------------------------------------------
# The AutoCAD side
# ---------------------------------------------------------------------------


def _try(getter, default=None):
    try:
        return getter()
    except BaseException:  # noqa: BLE001 - absent properties are expected here
        return default


def layer_state_list() -> dict[str, Any]:
    """The drawing's layer states, for autocad_list_layers (on the worker thread, inside its job)."""
    if _shared.plugin_runner() is None:
        return {"layer_states": None, "layer_states_note": "Layer states are read by Heron's plug-in, which is switched off (--no-bridge)."}
    try:
        report = in_plugin("layer_state_names", {}, "Listing layer states", changes=False)
    except AutocadError as exc:
        return {"layer_states": None, "layer_states_note": f"Layer states could not be read: {exc}"}
    return {"layer_states": list(report.get("layer_states") or [])}


def _layers(doc: Any) -> list[dict[str, Any]]:
    out = []
    for i in range(doc.Layers.Count):
        layer = doc.Layers.Item(i)
        out.append({
            "name": str(layer.Name),
            "on": bool(_try(lambda la=layer: la.LayerOn, True)),
            "frozen": bool(_try(lambda la=layer: la.Freeze, False)),
            "locked": bool(_try(lambda la=layer: la.Lock, False)),
        })
    return out


@mcp.tool(name="autocad_layer_states", **tool_meta("Save Or Restore A Layer State"))
@tool_errors
async def autocad_layer_states(
    action: Annotated[
        Literal["save", "restore", "delete"],
        Field(description="'save' the layers as they are now under a name, 'restore' a saved one, or 'delete' one."),
    ],
    name: Annotated[str, Field(min_length=1, max_length=255, description="The layer state's name, e.g. 'M-COORDINATION' or 'ISSUE-PLOT'.")],
    remembers: Annotated[
        list[str] | None,
        Field(
            default=None,
            description=(
                "For 'save': what the state remembers, any of on, frozen, locked, plot, "
                "new_viewport_frozen, color, linetype, lineweight, plot_style, transparency. "
                "Omit for all of them."
            ),
        ),
    ] = None,
    description: Annotated[str | None, Field(default=None, max_length=255, description="For 'save': a line saying what the state is for.")] = None,
    overwrite: Annotated[bool, Field(default=False, description="For 'save': replace a state of that name that is already there.")] = False,
) -> str:
    """Save the drawing's layers as a named layer state, bring one back, or delete one.

    A layer state remembers which layers are on, frozen and locked (and, unless
    you say otherwise, their colour, linetype, lineweight and plotting), so a
    set-up such as "coordination: only the duct and pipe layers" can be put
    back in one call. autocad_list_layers lists the saved states.

    Done by Heron's plug-in (AutoCAD's LayerStateManager). One undo step.

    Args:
        action (str): save, restore or delete.
        name (str): the layer state.
        remembers (Optional[list[str]]): for save, what it remembers.
        description (Optional[str]): for save, what it is for.
        overwrite (bool): for save, replace one already there.

    Returns:
        str: JSON: {"action", "name", "remembers": [str], "layers": int,
             "before_after": [{layer, property, from, to}]}
             A restore lists every layer whose on, frozen or locked state it changed.

    Examples:
        - Use when: "save the layers as they are now as COORDINATION".
        - Use when: "put the layers back to the ISSUE-PLOT state".
        - Use when: "which layer states does this drawing have?" — that is
          autocad_list_layers.
        - Don't use when: you only want to hide a few layers for a moment —
          autocad_isolate_layers, or autocad_set_layer_state for one layer.

    Error Handling:
        - Saving over a state that is there already needs overwrite=true.
        - Restoring or deleting a state the drawing has not got is refused,
          naming autocad_list_layers.
    """
    try:
        mask = mask_of(remembers) if action == "save" else None
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    clean = name.strip()
    if clean.casefold() == ISOLATE_STATE.casefold() and action != "delete":
        raise AutocadError(
            f"'{ISOLATE_STATE}' is the state Heron keeps while layers are isolated. Use "
            "autocad_isolate_layers(action='unisolate') to go back to it, or give another name."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        args: dict[str, Any] = {"action": action, "name": clean}
        if action == "save":
            args.update(mask=mask, description=(description or "").strip() or None, overwrite=overwrite or None)
        with undo_mark(doc):
            report = in_plugin("layer_state", args, "Layer states")
        rows = list(report.pop("changes", []) or [])
        if action == "save":
            rows = [{"layer": clean, "property": "layer state", "from": "replaced" if report.get("replaced") else "not there", "to": "saved"}]
        elif action == "delete":
            rows = [{"layer": clean, "property": "layer state", "from": "there", "to": "deleted"}]
        return {**report, **before_after(rows)}

    return dumps(await run(work))


@mcp.tool(name="autocad_isolate_layers", **tool_meta("Isolate Or Un-isolate Layers"))
@tool_errors
async def autocad_isolate_layers(
    action: Annotated[
        Literal["isolate", "unisolate"],
        Field(default="isolate", description="'isolate' the layers asked for, or 'unisolate' to put every layer back as it was before."),
    ] = "isolate",
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="For 'isolate': objects whose layers stay visible, by handle (AutoCAD's LAYISO picks objects)."),
    ] = None,
    layers: Annotated[
        list[str] | None,
        Field(default=None, description="For 'isolate': layers to keep visible, by name. With handles, both are kept."),
    ] = None,
    others: Annotated[
        Others,
        Field(default="off", description="What happens to every other layer: 'off' (hidden), 'freeze' (hidden and not regenerated, faster on a big drawing), or 'lock' (seen but not editable)."),
    ] = "off",
) -> str:
    """Isolate the layers of some objects (or named layers): every other layer off, frozen or locked.

    AutoCAD's LAYISO and LAYUNISO. Before the first isolate, Heron saves the
    layers as they are in a layer state called HERON-ISOLATE; 'unisolate' puts
    that back, current layer included, and removes it. Isolating again before
    un-isolating keeps the first one, so un-isolating always returns to where
    you started.

    The kept layers are turned on and thawed (and unlocked with others='lock').
    If the current layer would be hidden, the first kept layer becomes current.
    One undo step.

    Args:
        action (str): isolate or unisolate.
        handles (Optional[list[str]]): objects whose layers stay.
        layers (Optional[list[str]]): layers that stay.
        others (str): off, freeze or lock for every other layer.

    Returns:
        str: JSON: {"action", "kept": [str], "others": str, "current_layer": str,
             "already_isolated": bool, "before_after": [{layer, property, from, to}],
             "failed": [{"layer", "reason"}]}

    Examples:
        - Use when: "show me only the duct layers" — handles of a duct, or
          layers=['M-DUCT-SUPPLY','M-DUCT-RETURN'].
        - Use when: "lock everything except the pipework so I can edit it" —
          others='lock'.
        - Use when: "bring all the layers back" — action='unisolate'.
        - Don't use when: you want a named set-up to come back to later —
          save it with autocad_layer_states.

    Error Handling:
        - 'unisolate' with nothing isolated by Heron says so and changes nothing.
        - A layer name the drawing has not got is refused before anything changes.
    """
    if action == "isolate" and not handles and not layers:
        raise AutocadError("Say what to keep: 'handles' of objects on those layers, or 'layers' by name.")

    def isolate() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        keep = list(layers or [])
        if handles:
            keep = [str(e.Layer) for e in resolve_handles(doc, handles)] + keep
        state = _layers(doc)
        current = str(doc.ActiveLayer.Name)
        try:
            plan = isolate_plan(state, keep, current, others)
        except ValueError as exc:
            raise AutocadError(f"{exc}. Nothing was changed.") from exc
        rows: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        with undo_mark(doc):
            saved = in_plugin(
                "layer_state",
                {"action": "save", "name": ISOLATE_STATE, "mask": ISOLATE_MASK,
                 "description": isolate_description(current), "keep_existing": True},
                "Remembering the layers before isolating",
            )
            if plan["make_current"]:
                doc.ActiveLayer = doc.Layers.Item(plan["make_current"])
                rows.append({"variable": "CLAYER", "property": "current layer", "from": current, "to": plan["make_current"]})
            for change in plan["changes"]:
                try:
                    setattr(doc.Layers.Item(change["layer"]), COM_PROPERTY[change["property"]], change["to"])
                    rows.append(change)
                except BaseException as exc:  # noqa: BLE001 - one layer, not the isolate
                    failed.append({"layer": change["layer"], "reason": com_message(exc)})
        result: dict[str, Any] = {
            "action": "isolate",
            "kept": plan["kept"],
            "others": others,
            "current_layer": plan["make_current"] or current,
            "already_isolated": bool(saved.get("kept_existing")),
            **before_after(rows),
        }
        if saved.get("kept_existing"):
            result["note"] = "Layers were already isolated by Heron; un-isolating goes back to how they were before the first isolate."
        if failed:
            result["failed"] = failed
        return result

    def back_to(doc: Any, was: str | None) -> bool:
        """Make the layer that was current before isolating current again, if it can be now."""
        if not was or str(doc.ActiveLayer.Name).casefold() == was.casefold():
            return False
        try:
            target = doc.Layers.Item(was)
            if bool(_try(lambda: target.Freeze, False)):
                return False  # AutoCAD will not make a frozen layer current
            doc.ActiveLayer = target
            return True
        except BaseException:  # noqa: BLE001 - the layer has gone since: keep the current one
            return False

    def unisolate() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        listed = layer_state_list().get("layer_states") or []
        state = next((s for s in listed if str(s.get("name", "")).casefold() == ISOLATE_STATE.casefold()), None)
        if state is None:
            raise AutocadError(
                "Nothing is isolated by Heron in this drawing (there is no HERON-ISOLATE layer state). "
                "If layers were isolated with AutoCAD's own LAYISO, type LAYUNISO. Nothing was changed."
            )
        was = current_from(str(state.get("description", "")))
        before = str(doc.ActiveLayer.Name)
        with undo_mark(doc):
            # The old current layer first where it can be (the restore may freeze the one current
            # now), and again after the restore, which thaws it if it was frozen.
            back_to(doc, was)
            report = in_plugin("layer_state", {"action": "restore", "name": ISOLATE_STATE, "delete_after": True},
                               "Putting the layers back")
            back_to(doc, was)
        rows = list(report.get("changes") or [])
        now = str(doc.ActiveLayer.Name)
        if now.casefold() != before.casefold():
            rows.append({"variable": "CLAYER", "property": "current layer", "from": before, "to": now})
        return {"action": "unisolate", "current_layer": now, **before_after(rows)}

    return dumps(await run(isolate if action == "isolate" else unisolate))


def _merge_items(doc: Any, sources: Sequence[str]) -> list[tuple[dict[str, Any], Any]]:
    """Every object on the old layers: in every space, in block definitions, and attributes."""
    found: list[tuple[dict[str, Any], Any]] = []
    keys = {s.casefold() for s in sources}

    def take(entity: Any, where: str) -> None:
        layer = str(_try(lambda: entity.Layer, ""))
        if layer.casefold() in keys:
            found.append(({"handle": str(_try(lambda: entity.Handle, "")), "layer": layer, "where": where}, entity))

    for source in sources:
        sel = select_filtered(doc, layer=escape_wildcards(source), name="MCP_LAYER_MERGE")
        try:
            for entity in iter_selection(sel):
                take(entity, "drawing")
        finally:
            discard_selection_set(doc, "MCP_LAYER_MERGE")
    for i in range(doc.Blocks.Count):
        block = doc.Blocks.Item(i)
        if bool(_try(lambda b=block: b.IsLayout, False)) or bool(_try(lambda b=block: b.IsXRef, False)):
            continue  # a layout's objects came with the selection; an xref is its own drawing's
        for j in range(int(_try(lambda b=block: b.Count, 0))):
            take(block.Item(j), "blocks")
    sel = select_filtered(doc, "block", name="MCP_LAYER_MERGE")
    try:
        for ref in iter_selection(sel):
            if not bool(_try(lambda r=ref: r.HasAttributes, False)):
                continue
            for attribute in _try(lambda r=ref: r.GetAttributes(), ()) or ():
                take(attribute, "attributes")
    finally:
        discard_selection_set(doc, "MCP_LAYER_MERGE")
    return found


@mcp.tool(name="autocad_merge_layers", **tool_meta("Merge Layers", destructive=True))
@tool_errors
async def autocad_merge_layers(
    layers: Annotated[
        list[str],
        Field(min_length=1, description="The layers to merge away, by exact name, e.g. ['M-DUCT-OLD', 'DUCT']."),
    ],
    into: Annotated[str, Field(min_length=1, description="The layer everything moves to. It must already be in the drawing.")],
    confirm: Annotated[bool, Field(default=False, description="Must be true for the merge to run. Without it, the call says what would move and changes nothing.")] = False,
) -> str:
    """Merge layers into one: every object moves to the new layer, then the old layer is removed.

    AutoCAD's LAYMERGE. Objects move from the old layers in model space, on
    every layout, inside block definitions and in block attributes. An old
    layer is removed only when nothing is left on it; one still in use
    somewhere (an object that would not move) is kept and named.

    Call it first without confirm to see what would move. If an old layer is
    the current layer, the new one becomes current. A locked old layer is
    unlocked for the move. One undo step.

    Args:
        layers (list[str]): the layers to merge away.
        into (str): the layer they merge into.
        confirm (bool): must be true to run.

    Returns:
        str: JSON: {"into", "moved": int, "counts": {layer: {"drawing",
             "blocks", "attributes"}}, "removed": [str],
             "kept": [{"layer", "why"}], "failed": [{"handle", "reason"}],
             "before_after": [...]}
             With confirm=false: the counts and a next step; nothing changed.

    Examples:
        - Use when: "merge DUCT and M-DUCT-OLD into M-DUCT-SUPPLY".
        - Use when: an import came with three names for the same layer.
        - Don't use when: you are sorting out a whole import by rules —
          autocad_remap_layers moves objects layer by layer from a table.

    Error Handling:
        - Layer 0, an xref's layer, a layer that is not there, or merging a
          layer into itself is refused before anything changes.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        existing = [str(doc.Layers.Item(i).Name) for i in range(doc.Layers.Count)]
        try:
            sources, target = check_merge(layers, into, existing)
        except ValueError as exc:
            raise AutocadError(f"{exc}. Nothing was changed.") from exc
        pairs = _merge_items(doc, sources)
        moving = merge_targets([item for item, _ in pairs], sources)
        objects = {item["handle"]: entity for item, entity in pairs}
        counts = merge_counts(moving, sources)
        if not confirm:
            return {
                "into": target,
                "layers": sources,
                "would_move": len(moving),
                "counts": counts,
                "confirmed": False,
                "next_step": (
                    f"{len(moving)} object(s) would move to {target}, and then "
                    f"{', '.join(sources)} would be removed. Nothing was changed. Confirm with the "
                    "user, then call again with confirm=true."
                ),
            }

        rows: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        removed: list[str] = []
        kept: list[dict[str, str]] = []
        with undo_mark(doc):
            current = str(doc.ActiveLayer.Name)
            if current.casefold() in {s.casefold() for s in sources}:
                doc.ActiveLayer = doc.Layers.Item(target)
                rows.append({"variable": "CLAYER", "property": "current layer", "from": current, "to": target})
            relock = []
            for source in sources:
                layer = doc.Layers.Item(source)
                if bool(_try(lambda la=layer: la.Lock, False)):
                    layer.Lock = False
                    relock.append(source)
            left = {s.casefold(): 0 for s in sources}
            for item in moving:
                try:
                    objects[item["handle"]].Layer = target
                    rows.append({"handle": item["handle"], "property": "layer", "from": item["layer"], "to": target})
                except BaseException as exc:  # noqa: BLE001 - one object, not the merge
                    failed.append({"handle": item["handle"], "reason": com_message(exc)})
                    left[item["layer"].casefold()] += 1
            for source in sources:
                if left[source.casefold()]:
                    kept.append({"layer": source, "why": f"{left[source.casefold()]} object(s) on it would not move"})
                else:
                    try:
                        doc.Layers.Item(source).Delete()
                        removed.append(source)
                        rows.append({"layer": source, "property": "layer", "from": "there", "to": "merged and removed"})
                        continue
                    except BaseException as exc:  # noqa: BLE001 - still referenced somewhere
                        kept.append({"layer": source, "why": f"AutoCAD would not remove it ({com_message(exc)}); it is still used somewhere, for example by a viewport or a layer filter"})
                if source in relock:
                    _try(lambda s=source: setattr(doc.Layers.Item(s), "Lock", True))
        result: dict[str, Any] = {
            "into": target,
            "moved": len(moving) - len(failed),
            "counts": counts,
            "removed": removed,
            "kept": kept,
            "confirmed": True,
            **before_after(rows),
        }
        if failed:
            result["failed"] = failed[:50]
        return result

    return dumps(await run(work))
