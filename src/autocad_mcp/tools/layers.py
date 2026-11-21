"""Tools for layers, blocks and styles — the drawing's organisational tables."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import describe_layer, ensure_layer, ensure_linetype, validate_name
from ..core.connection import get_doc, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ._shared import before_after, same_value


@mcp.tool(
    name="autocad_list_layers",
    **tool_meta("List Layers", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_list_layers(
    include_entity_counts: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Count the entities on each layer. Slower on a large drawing, "
                "since it walks every layer's contents."
            ),
        ),
    ] = False,
) -> str:
    """List every layer with its colour, linetype and visibility state.

    Reading the layer list first is the reliable way to use the drawing's own
    naming convention instead of inventing new layers alongside it.

    Args:
        include_entity_counts (bool): Also count entities per layer.

    Returns:
        str: JSON: {"count": int, "current_layer": str, "layers": [
             {"name": str, "color": int, "linetype": str, "lineweight": int,
              "on": bool, "frozen": bool, "locked": bool, "plottable": bool,
              "entity_count": int}]}
             "entity_count" appears only when include_entity_counts is true.

    Examples:
        - Use when: "what layers does this drawing use?"
        - Use when: before drawing, to match the existing naming convention.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        layers = []
        for i in range(doc.Layers.Count):
            info = describe_layer(doc.Layers.Item(i))
            if include_entity_counts and info["name"]:
                sel = select_filtered(
                    doc, None, info["name"], None, None, name="MCP_LAYER_COUNT"
                )
                try:
                    info["entity_count"] = int(sel.Count)
                finally:
                    discard_selection_set(doc, "MCP_LAYER_COUNT")
            layers.append(info)
        return {
            "count": len(layers),
            "current_layer": str(doc.ActiveLayer.Name),
            "layers": sorted(layers, key=lambda item: item["name"].lower()),
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_create_layer",
    **tool_meta("Create Layer", idempotent=True),
)
@tool_errors
async def autocad_create_layer(
    name: Annotated[
        str,
        Field(
            description=(
                "Layer name, e.g. 'A-WALL' or 'M-DUCT-SUPPLY'. Cannot contain "
                "< > / \\ \" : ; ? * | , = `"
            ),
            min_length=1,
            max_length=255,
        ),
    ],
    color: Annotated[
        str | StrictInt | None,
        Field(
            default=None,
            description="Colour name or AutoCAD Color Index number 0-255.",
        ),
    ] = None,
    linetype: Annotated[
        str | None,
        Field(
            default=None,
            description="Linetype, e.g. 'CONTINUOUS', 'HIDDEN', 'CENTER'.",
        ),
    ] = None,
    lineweight: Annotated[
        int | None,
        Field(
            default=None,
            description=(
                "Lineweight in hundredths of a millimetre: 25 is 0.25 mm, 50 "
                "is 0.50 mm. Use -1 for ByLayer default."
            ),
        ),
    ] = None,
    make_current: Annotated[
        bool,
        Field(
            default=False,
            description="Make this the current layer, so new geometry lands on it.",
        ),
    ] = False,
) -> str:
    """Create a layer, or update one that already exists.

    Safe to call repeatedly: an existing layer is updated with whatever
    properties you pass rather than raising an error.

    Args:
        name (str): Layer name.
        color (Optional[str | int]): Colour name or ACI number.
        linetype (Optional[str]): Linetype name.
        lineweight (Optional[int]): Lineweight in hundredths of a millimetre.
        make_current (bool): Also make it the current layer.

    Returns:
        str: JSON: {"name": str, "created": bool, "current": bool,
             "color": int, "linetype": str, "lineweight": int, ...,
             "before_after": [{layer, property, from, to}]}
             "created" is false when the layer already existed and was updated.

    Examples:
        - Use when: "make a layer M-HVAC-DUCT, cyan, dashed".
        - Don't use when: you are sorting out a whole import - the layers come
          out of autocad_remap_layers already.
    """
    validate_name(name, "layer")
    aci = to_aci(color)

    def work() -> dict[str, Any]:
        doc = get_doc()
        rows: list[dict[str, Any]] = []
        existing = _existing_layer(doc, name)
        now: dict[str, Any] | None = None
        if existing is not None:
            try:
                now = {"color": int(existing.Color), "linetype": str(existing.Linetype),
                       "lineweight": int(existing.Lineweight), "name": str(existing.Name),
                       "current": str(doc.ActiveLayer.Name)}  # fmt: skip
            except BaseException:  # noqa: BLE001 - could not look: write as before, list nothing
                now = None
        if existing is not None and now is not None:
            # First look: what the layer has now. Asked for what it already has,
            # nothing is written and no empty undo step is left (D-62).
            wanted = {"color": aci, "linetype": linetype.strip() if linetype else None, "lineweight": lineweight}
            rows = [{"layer": now["name"], "property": key, "from": now[key], "to": value}
                    for key, value in wanted.items() if value is not None and not same_value(now[key], value)]  # fmt: skip
            current = same_value(now["current"], now["name"])
            if not rows and (not make_current or current):
                info = describe_layer(existing)
                info.update(created=False, current=current, **before_after([]))
                return info
        with undo_mark(doc):
            layer, created = ensure_layer(doc, name)
            if make_current:
                previous = str(doc.ActiveLayer.Name)
            if aci is not None:
                layer.Color = aci
            if linetype:
                ensure_linetype(doc, linetype)
                layer.Linetype = linetype.strip()
            if lineweight is not None:
                try:
                    layer.Lineweight = int(lineweight)
                except BaseException as exc:  # noqa: BLE001
                    raise AutocadError(
                        f"'{lineweight}' is not a lineweight AutoCAD accepts. "
                        "Use one of 0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, "
                        "53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211, "
                        "or -1 for the default. (details: "
                        f"{com_message(exc)})"
                    ) from exc
            if make_current:
                doc.ActiveLayer = layer
                if not same_value(previous, str(layer.Name)):
                    rows.append({"variable": "CLAYER", "property": "current layer", "from": previous, "to": str(layer.Name)})

        info = describe_layer(layer)
        info["created"] = created
        info["current"] = make_current
        info.update(before_after(rows))
        return info

    return dumps(await run(work))


@mcp.tool(
    name="autocad_set_layer_state",
    **tool_meta("Set Layer Visibility And Lock", idempotent=True),
)
@tool_errors
async def autocad_set_layer_state(
    name: Annotated[
        str,
        Field(
            description=(
                "Layer name, or a wildcard such as 'A-*' to act on every layer "
                "starting with A-."
            ),
            min_length=1,
        ),
    ],
    on: Annotated[
        bool | None,
        Field(
            default=None,
            description="Turn the layer on (visible) or off (hidden).",
        ),
    ] = None,
    frozen: Annotated[
        bool | None,
        Field(
            default=None,
            description=(
                "Freeze or thaw. Freezing hides the layer and excludes it from "
                "regeneration, which is faster than off on a big drawing."
            ),
        ),
    ] = None,
    locked: Annotated[
        bool | None,
        Field(
            default=None,
            description="Lock or unlock. A locked layer is visible but uneditable.",
        ),
    ] = None,
    plottable: Annotated[
        bool | None,
        Field(
            default=None,
            description="Include the layer when plotting, or exclude it.",
        ),
    ] = None,
) -> str:
    """Turn layers on or off, freeze, lock or exclude them from plotting.

    Only the states you pass are changed. Wildcards let one call cover a whole
    discipline prefix.

    Args:
        name (str): Layer name or wildcard pattern.
        on (Optional[bool]): Visible or hidden.
        frozen (Optional[bool]): Frozen or thawed.
        locked (Optional[bool]): Locked or unlocked.
        plottable (Optional[bool]): Plotted or not.

    Returns:
        str: JSON: {"matched": int, "changed": [str], "state": {...},
             "before_after": [{layer, property, from, to}], "already": int,
             "failed": [{"name": str, "reason": str}]}

    Examples:
        - Use when: "hide all the MEP layers" -> name="M-*", on=false.
        - Use when: "unlock A-WALL so I can edit it" -> name="A-WALL",
          locked=false.

    Error Handling:
        - The current layer cannot be frozen or turned off; AutoCAD refuses it
          and the reason is reported per layer rather than failing the call.
    """
    wanted = {"on": on, "frozen": frozen, "locked": locked, "plottable": plottable}
    if all(v is None for v in wanted.values()):
        raise AutocadError(
            "No state change requested. Pass at least one of: on, frozen, "
            "locked, plottable."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        pattern = name.strip()
        wildcard = "*" in pattern or "?" in pattern

        targets = []
        for i in range(doc.Layers.Count):
            layer = doc.Layers.Item(i)
            layer_name = str(layer.Name)
            if wildcard:
                import fnmatch

                if fnmatch.fnmatch(layer_name.lower(), pattern.lower()):
                    targets.append(layer)
            elif layer_name.lower() == pattern.lower():
                targets.append(layer)

        if not targets:
            raise AutocadError(
                f"No layer matches '{name}'. List the drawing's layers with "
                "autocad_list_layers."
            )

        changed: list[str] = []
        failed: list[dict[str, str]] = []
        rows: list[dict[str, Any]] = []
        names = {"on": "LayerOn", "frozen": "Freeze", "locked": "Lock", "plottable": "Plottable"}
        # First look: each layer's state now. Only a state that differs is
        # written; nothing to write opens no undo step (D-62).
        plans = []
        for layer in targets:
            todo = [(key, bool(getattr(layer, names[key])), bool(value))
                    for key, value in wanted.items() if value is not None]  # fmt: skip
            todo = [(key, old, new) for key, old, new in todo if old != new]
            if todo:
                plans.append((layer, todo))
        if plans:
            with undo_mark(doc):
                for layer, todo in plans:
                    layer_name = str(layer.Name)
                    try:
                        for key, old, new in todo:
                            setattr(layer, names[key], new)
                            rows.append({"layer": layer_name, "property": key, "from": old, "to": new})
                        changed.append(layer_name)
                    except BaseException as exc:  # noqa: BLE001
                        failed.append({"name": layer_name, "reason": com_message(exc)})

        result: dict[str, Any] = {
            "matched": len(targets),
            "changed": changed,
            "state": {k: v for k, v in wanted.items() if v is not None},
            **before_after(rows),
        }
        already = len(targets) - len(plans)
        if already:
            result["already"] = already
            result["already_note"] = f"{already} layer(s) were already in that state; nothing was written to them."
        if failed:
            result["failed"] = failed
            result["hint"] = (
                "AutoCAD refuses to freeze or turn off the current layer. "
                "Switch to another layer first with autocad_create_layer "
                "(make_current=true)."
            )
        return result

    return dumps(await run(work))


@mcp.tool(
    name="autocad_set_current_layer",
    **tool_meta("Set Current Layer", idempotent=True),
)
@tool_errors
async def autocad_set_current_layer(
    name: Annotated[
        str,
        Field(
            description="Layer to make current. Created if it does not exist.",
            min_length=1,
        ),
    ],
) -> str:
    """Set the layer that new geometry goes on by default.

    Only needed when drawing several things onto one layer — the drawing tools
    all take a 'layer' argument that overrides this per call.

    Args:
        name (str): Layer name.

    Returns:
        str: JSON: {"current_layer": str, "created": bool, "previous": str}

    Examples:
        - Use when: you are about to draw several things by hand and want them
          on the right layer without saying so each time.
        - Don't use when: you are drawing through these tools - every draw tool
          takes its own layer, which is safer.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        previous = str(doc.ActiveLayer.Name)
        if same_value(previous, name.strip()):
            # Already current (and so not frozen): nothing written, no empty undo step (D-62).
            return {"current_layer": previous, "created": False, "previous": previous, **before_after([])}
        rows: list[dict[str, Any]] = []
        with undo_mark(doc):
            layer, created = ensure_layer(doc, name)
            if bool(layer.Freeze):
                layer.Freeze = False
                rows.append({"layer": str(layer.Name), "property": "frozen", "from": True, "to": False})
            doc.ActiveLayer = layer
        rows.append({"variable": "CLAYER", "property": "current layer", "from": previous, "to": str(doc.ActiveLayer.Name)})
        return {
            "current_layer": str(doc.ActiveLayer.Name),
            "created": created,
            "previous": previous,
            **before_after(rows),
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_delete_layer",
    **tool_meta("Delete Layer", destructive=True),
)
@tool_errors
async def autocad_delete_layer(
    name: Annotated[
        str, Field(description="Layer to delete.", min_length=1)
    ],
    delete_contents: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Delete every entity on the layer first. Without this, a layer "
                "holding geometry cannot be removed."
            ),
        ),
    ] = False,
    confirm: Annotated[
        bool,
        Field(
            default=False,
            description="Must be true for the deletion to run.",
        ),
    ] = False,
) -> str:
    """Delete a layer, optionally deleting the geometry on it.

    AutoCAD will not delete layer 0, the current layer, or a layer that still
    holds entities. Set delete_contents=true to clear it first — that destroys
    the geometry.

    Args:
        name (str): Layer to delete.
        delete_contents (bool): Delete the entities on it first.
        confirm (bool): Must be true to proceed.

    Returns:
        str: JSON: {"deleted": bool, "layer": str, "entities_deleted": int}
             With confirm=false: a preview of what the call would remove.

    Examples:
        - Use when: an import left empty layers behind and you are tidying up.
        - Don't use when: you only want it out of the way - freeze or turn it
          off with autocad_set_layer_state. Deleting takes the geometry too if
          you ask it to.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        target = name.strip()
        try:
            layer = doc.Layers.Item(target)
        except BaseException:  # noqa: BLE001
            raise AutocadError(
                f"No layer named '{target}' exists. List them with "
                "autocad_list_layers."
            ) from None

        if target == "0":
            raise AutocadError(
                "Layer 0 is built into every AutoCAD drawing and cannot be "
                "deleted."
            )
        if target.lower() == str(doc.ActiveLayer.Name).lower():
            raise AutocadError(
                f"'{target}' is the current layer, so AutoCAD will not delete "
                "it. Make another layer current first with "
                "autocad_set_current_layer."
            )

        sel = select_filtered(doc, None, target, None, None, name="MCP_LAYER_DELETE")
        try:
            entity_count = int(sel.Count)
            if not confirm:
                return {
                    "deleted": False,
                    "layer": target,
                    "would_delete_entities": entity_count,
                    "confirmed": False,
                    "next_step": (
                        f"Layer '{target}' holds {entity_count} entities. Nothing "
                        "was changed. Confirm with the user, then call again "
                        "with confirm=true"
                        + (
                            " and delete_contents=true to remove the geometry too."
                            if entity_count
                            else "."
                        )
                    ),
                }

            deleted_entities = 0
            with undo_mark(doc):
                if entity_count and delete_contents:
                    for i in range(entity_count - 1, -1, -1):
                        try:
                            sel.Item(i).Delete()
                            deleted_entities += 1
                        except BaseException:  # noqa: BLE001 - locked entity
                            pass
                elif entity_count:
                    raise AutocadError(
                        f"Layer '{target}' still holds {entity_count} entities, "
                        "so AutoCAD will not delete it. Pass "
                        "delete_contents=true to remove them first, or move "
                        "them with autocad_modify_entity."
                    )
                layer.Delete()

            row = {"layer": target, "property": "layer", "from": f"there, {entity_count} object(s) on it", "to": "deleted"}
            return {
                "deleted": True,
                "layer": target,
                "entities_deleted": deleted_entities,
                "confirmed": True,
                **before_after([row]),
            }
        finally:
            discard_selection_set(doc, "MCP_LAYER_DELETE")

    return dumps(await run(work))


def _existing_layer(doc: Any, name: str) -> Any:
    """The layer of that name, or None when it is not there (or AutoCAD would not say)."""
    try:
        return doc.Layers.Item(name.strip())
    except BaseException:  # noqa: BLE001 - ensure_layer then decides, busy signals included
        return None


def _count_by_effective_name(doc: Any) -> dict[str, int]:
    """Placed references per block, by real name.

    A dynamic block's changed copies are renamed *U.. by AutoCAD, so a
    selection filtered on the block's name misses them; EffectiveName does not.
    One pass over every insert, instead of one selection per definition.
    """
    counts: dict[str, int] = {}
    sel = select_filtered(doc, "block", name="MCP_BLOCK_COUNT")
    try:
        for ref in iter_selection(sel):
            try:
                name = str(getattr(ref, "EffectiveName", None) or ref.Name).lower()
            except BaseException:  # noqa: BLE001 - not a block reference after all
                continue
            counts[name] = counts.get(name, 0) + 1
    finally:
        discard_selection_set(doc, "MCP_BLOCK_COUNT")
    return counts


@mcp.tool(
    name="autocad_list_blocks",
    **tool_meta("List Block Definitions", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_list_blocks(
    include_counts: Annotated[
        bool,
        Field(
            default=True,
            description="Count how many times each block is placed in the drawing.",
        ),
    ] = True,
    include_unused: Annotated[
        bool,
        Field(
            default=False,
            description="Include block definitions that are not placed anywhere.",
        ),
    ] = False,
) -> str:
    """List the block definitions available in the drawing.

    Use this before autocad_insert_block to get exact names, and to see what
    attributes each block expects.

    Anonymous blocks (names starting with *) and layout blocks are always
    excluded — they are AutoCAD internals, not blocks a user would insert.

    Args:
        include_counts (bool): Count placed instances of each block.
        include_unused (bool): Include definitions with no instances.

    Returns:
        str: JSON: {"count": int, "blocks": [{"name": str,
             "entity_count": int,           # entities in the definition
             "instances": int,              # times placed in the drawing
             "is_xref": bool,
             "dynamic": bool,               # a dynamic block
             "attribute_tags": [str],
             "path": str}]}                 # xrefs only

    Examples:
        - Use when: "what blocks can I insert?"
        - Use when: "how many door blocks are in this drawing?"
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        instances = _count_by_effective_name(doc) if include_counts else {}
        blocks = []
        for i in range(doc.Blocks.Count):
            block = doc.Blocks.Item(i)
            name = str(block.Name)
            # Blank names come in with some library drawings; nothing can insert them.
            if not name.strip() or name.startswith("*"):
                continue
            try:
                if bool(block.IsLayout):
                    continue
            except BaseException:  # noqa: BLE001
                pass

            info: dict[str, Any] = {"name": name}
            try:
                info["entity_count"] = int(block.Count)
            except BaseException:  # noqa: BLE001
                info["entity_count"] = None
            try:
                info["is_xref"] = bool(block.IsXRef)
                if info["is_xref"]:
                    info["path"] = str(block.Path)
            except BaseException:  # noqa: BLE001
                info["is_xref"] = False
            try:
                info["dynamic"] = bool(block.IsDynamicBlock)
            except BaseException:  # noqa: BLE001
                info["dynamic"] = False

            # Attribute definitions inside the block tell the caller which tags
            # autocad_insert_block can fill in.
            tags = []
            try:
                for j in range(int(block.Count)):
                    item = block.Item(j)
                    if str(item.ObjectName) == "AcDbAttributeDefinition":
                        tags.append(str(item.TagString))
            except BaseException:  # noqa: BLE001
                pass
            if tags:
                info["attribute_tags"] = tags

            if include_counts:
                info["instances"] = instances.get(name.lower(), 0)
                if not include_unused and info["instances"] == 0:
                    continue

            blocks.append(info)

        return {
            "count": len(blocks),
            "blocks": sorted(blocks, key=lambda item: item["name"].lower()),
        }

    return dumps(await run(work))


@mcp.tool(
    name="autocad_list_styles",
    **tool_meta("List Text And Dimension Styles", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_list_styles() -> str:
    """List the drawing's text styles, dimension styles and loaded linetypes.

    Read this before adding annotation so new text and dimensions match what
    the drawing already uses, rather than defaulting to Standard.

    Returns:
        str: JSON: {"current_text_style": str, "current_dimension_style": str,
             "text_styles": [{"name": str, "font": str, "height": float,
                              "width_factor": float}],
             "dimension_styles": [str],
             "linetypes": [str]}

    Examples:
        - Use when: a text or dimension style is named in a standard and you
          need to know whether this drawing has it.
        - Use when: before autocad_create_styles, so you do not replace one
          that is already right.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()

        text_styles = []
        for i in range(doc.TextStyles.Count):
            style = doc.TextStyles.Item(i)
            entry: dict[str, Any] = {"name": str(style.Name)}
            for key, getter in (
                ("font", lambda s=style: str(s.fontFile)),
                ("height", lambda s=style: round(float(s.Height), 6)),
                ("width_factor", lambda s=style: round(float(s.Width), 6)),
            ):
                try:
                    entry[key] = getter()
                except BaseException:  # noqa: BLE001
                    pass
            text_styles.append(entry)

        dim_styles = [
            str(doc.DimStyles.Item(i).Name) for i in range(doc.DimStyles.Count)
        ]
        linetypes = [
            str(doc.Linetypes.Item(i).Name) for i in range(doc.Linetypes.Count)
        ]

        result = {
            "text_styles": sorted(text_styles, key=lambda s: s["name"].lower()),
            "dimension_styles": sorted(dim_styles, key=str.lower),
            "linetypes": sorted(linetypes, key=str.lower),
        }
        try:
            result["current_text_style"] = str(doc.ActiveTextStyle.Name)
        except BaseException:  # noqa: BLE001
            pass
        try:
            result["current_dimension_style"] = str(doc.ActiveDimStyle.Name)
        except BaseException:  # noqa: BLE001
            pass
        return result

    return dumps(await run(work))
