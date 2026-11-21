"""Make a named block from drawn objects, and keep its attributes in step.

Ajmal (2026-10-26): parts must be blocks, "otherwise the manual drawing person
cannot do anything". Draw the part's geometry, then turn it into a block: the
objects are copied into a new block definition (their world positions kept,
relative to ``base_point``), removed, and one insert of the block takes their
place, so the drawing looks the same but the part now moves, copies and counts
as one piece. One undo step.

A tag block (a valve tag, a room number, an equipment label) needs attributes:
``attributes`` on ``autocad_make_block`` adds attribute definitions (ATTDEF)
to the new block. When a block's definition changes afterwards,
``autocad_sync_attributes`` is ATTSYNC: every insert gets the definition's
attributes again, keeping the values already typed (D-82). COM cannot add an
attribute to an insert that is already placed, so the plug-in does that part.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from ..acad.block_attributes import AttributeSpecError, plan_definitions, plan_sync
from ..acad.entities import resolve_handles
from ..acad.selection import discard_selection_set, iter_selection, select_filtered
from ..acad.tables import apply_properties
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import apoint, object_array
from ._shared import LAYER_OPT, before_after, in_plugin, point

ATTRIBUTES_FIELD = Field(
    default=None,
    description=(
        "Attribute definitions (ATTDEF) for the block, in order, e.g. "
        '[{"tag": "TAG", "prompt": "Valve tag", "default": "V-101", "position": [120, -40], "height": 25}, '
        '{"tag": "SIZE", "default": "DN50", "invisible": true}]. Each takes tag (no spaces), prompt '
        "(default: the tag), default (the value it starts with), position [x, y] in drawing coordinates "
        "like the objects (default: stacked under the base point), height (default: the drawing's "
        "TEXTSIZE), and the flags invisible, constant (fixed in the block, never asked for; needs a "
        "default) and preset (filled in, can still be changed). Omit for a block with no attributes."
    ),
)
# AutoCAD wildcard characters: a block name is matched as text, not as a pattern.
_WILDCARDS = set("#@.*?~[]-`,")
MOST_LISTED = 50


def escape_wildcards(name: str) -> str:
    """A block name as a selection filter that matches only that name (` escapes a wildcard)."""
    return "".join(f"`{ch}" if ch in _WILDCARDS else ch for ch in name)


def _text_height(doc: Any) -> float:
    try:
        return float(doc.GetVariable("TEXTSIZE"))
    except Exception:  # noqa: BLE001 - the planner falls back to a plain height
        return 0.0


@mcp.tool(name="autocad_make_block", **tool_meta("Make Block from Objects"))
@tool_errors
async def autocad_make_block(
    name: Annotated[str, Field(min_length=1, description="New block name, e.g. 'SHS 100x100x5 POST'.")],
    handles: Annotated[list[str], Field(min_length=1, description="Handles of the objects that make up the part.")],
    base_point: Annotated[list[float], Field(description="Block base point [x, y]: the point you insert it by.")],
    layer: Annotated[str | None, LAYER_OPT] = None,
    keep_originals: Annotated[
        bool, Field(description="True: only define the block; leave the objects and insert nothing.")
    ] = False,
    attributes: Annotated[list[dict[str, Any]] | None, ATTRIBUTES_FIELD] = None,
) -> str:
    """Turn drawn objects into a named block, and put the block where they were.

    Use for every separate part (fitting, elbow, clamp, plate, anchor, support
    piece) so it can be moved, copied, swapped and counted as one. Draw the part,
    then call this with its handles. Insert more copies with autocad_insert_block.
    Pipes and runs can stay as lines or polylines.

    With ``attributes`` the block gets attribute definitions (ATTDEF): a tag
    block whose value (tag, size, room number) is typed per insert. The insert
    put in place of the objects starts with each attribute's default; set them
    with autocad_set_attributes or autocad_insert_block's ``attributes``.
    To add an attribute to a block that already exists, and to every insert
    of it, use autocad_sync_attributes with add_attributes.

    Returns:
        JSON: {"created": true, "block": name, "handle": insert handle (null when keep_originals),
        "attributes": [{tag, default, invisible, constant, preset}] when given}

    Examples:
        - Use when: "make these lines into a block called BASE PLATE
          250x250x12" -> handles=[...], base_point=the insertion corner.
        - Use when: a part repeats. Drafting rule 2: parts are blocks, not
          loose lines.
        - Use when: "make a tag block with attributes": a valve tag block
          with a TAG attribute and an invisible SIZE attribute (ATTDEF) ->
          attributes=[{"tag": "TAG", ...}, {"tag": "SIZE", "invisible": true}].
        - Don't use when: the block is already in the drawing -
          autocad_insert_block places more of it.

    Error Handling:
        - A tag with a space, a tag given twice, a constant attribute with no
          default, or constant and preset together are refused before
          anything is made.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        try:
            doc.Blocks.Item(name)
        except Exception:  # noqa: BLE001 - not found is what we want
            pass
        else:
            raise AutocadError(
                f"A block named '{name}' already exists in this drawing. Insert it with "
                "autocad_insert_block, or choose another name."
            )
        planned: list[dict[str, Any]] = []
        if attributes:
            if len(base_point) < 2:
                raise AutocadError("base_point must be [x, y].")
            try:
                planned = plan_definitions(attributes, base_point, _text_height(doc))
            except AttributeSpecError as exc:
                raise AutocadError(f"{exc} Nothing was made.") from None
        objects = resolve_handles(doc, handles)
        with undo_mark(doc):
            definition = doc.Blocks.Add(point(base_point, "base_point"), name)
            doc.CopyObjects(object_array(objects), definition)
            for attribute in planned:
                definition.AddAttribute(
                    attribute["height"],
                    attribute["mode"],
                    attribute["prompt"],
                    apoint(*attribute["position"]),
                    attribute["tag"],
                    attribute["default"],
                )
            made = (
                {
                    "attributes": [
                        {key: a[key] for key in ("tag", "default", "invisible", "constant", "preset")} for a in planned
                    ]
                }
                if planned
                else {}
            )
            if keep_originals:
                return {"created": True, "block": name, "handle": None, "objects": len(objects), **made}
            for obj in objects:
                obj.Delete()
            ref = get_space(doc, "model").InsertBlock(point(base_point, "base_point"), name, 1.0, 1.0, 1.0, 0.0)
            notes = apply_properties(doc, ref, layer, None, None)
        return {"created": True, "block": name, "handle": str(ref.Handle), "objects": len(objects), **made, **notes}

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# ATTSYNC
# ---------------------------------------------------------------------------


def _block_definition(doc: Any, name: str) -> tuple[Any, list[dict[str, Any]]]:
    """The block and its attribute definitions in order, or a refusal naming the problem."""
    try:
        block = doc.Blocks.Item(name.strip())
    except Exception:  # noqa: BLE001
        raise AutocadError(f"This drawing has no block called '{name}'. autocad_list_blocks lists them.") from None
    for flag, what in (("IsLayout", "a layout"), ("IsXRef", "an xref")):
        try:
            if getattr(block, flag):
                raise AutocadError(f"'{name}' is {what}, not a block whose inserts carry attributes.")
        except AutocadError:
            raise
        except Exception:  # noqa: BLE001 - an older AutoCAD without the property
            pass
    definitions: list[dict[str, Any]] = []
    for i in range(int(block.Count)):
        item = block.Item(i)
        if str(item.ObjectName) != "AcDbAttributeDefinition":
            continue
        try:
            at = [float(v) for v in item.InsertionPoint]
        except Exception:  # noqa: BLE001 - only used to stack new ones under it
            at = []
        definitions.append(
            {
                "tag": str(item.TagString).upper(),
                "default": str(item.TextString),
                "constant": bool(item.Constant),
                "prompt": str(item.PromptString),
                "at": at,
            }
        )
    return block, definitions


def _inserts(doc: Any, name: str) -> list[dict[str, Any]]:
    """Every insert of the block in model and paper space, a dynamic block's changed copies included.

    A dynamic block's changed copies are named *U..., so the selection takes
    those too and keeps only the ones whose real (effective) name is the block.
    """
    found: list[dict[str, Any]] = []
    wanted = name.strip().lower()
    # The shared scratch set: adding a named set of its own would cost the
    # modeller an undo step the first time (selection.make_selection_set).
    sel = select_filtered(doc, "insert", block_name=f"{escape_wildcards(name.strip())},`*U*")
    try:
        for ref in iter_selection(sel):
            try:
                effective = str(getattr(ref, "EffectiveName", None) or ref.Name)
                if effective.strip().lower() != wanted:
                    continue
                values: list[tuple[str, str]] = []
                if ref.HasAttributes:
                    values = [(str(a.TagString), str(a.TextString)) for a in ref.GetAttributes()]
                found.append(
                    {"handle": str(ref.Handle), "block": effective, "layer": str(ref.Layer), "attributes": values}
                )
            except AutocadError:
                raise
            except Exception:  # noqa: BLE001 - not a block reference after all
                continue
    finally:
        discard_selection_set(doc)
    return found


def _locked(doc: Any, layers: set[str]) -> list[str]:
    locked = []
    for layer in sorted(layers):
        try:
            if doc.Layers.Item(layer).Lock:
                locked.append(layer)
        except Exception:  # noqa: BLE001 - unreadable: let AutoCAD decide
            continue
    return locked


@mcp.tool(name="autocad_sync_attributes", **tool_meta("Sync Block Attributes (ATTSYNC)"))
@tool_errors
async def autocad_sync_attributes(
    block: Annotated[str, Field(min_length=1, description="The block whose inserts to bring in step, e.g. 'VALVE TAG'. autocad_list_blocks names them.")],
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="Only these inserts of the block. Omit for every insert in model space and on every sheet."),
    ] = None,
    add_attributes: Annotated[
        list[dict[str, Any]] | None,
        Field(
            default=None,
            description=(
                "New attribute definitions to add to the block first, then sync, e.g. "
                '[{"tag": "SIZE", "default": "DN50", "position": [0, -60], "invisible": true}]. Same keys as '
                "autocad_make_block's attributes, except position: here it is measured from the block's base "
                "point, as the block is drawn (not scaled or turned). Omit when the definition was already "
                "changed (in the Block Editor, or by redefining the block)."
            ),
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(default=False, description="True: say which inserts would change and what each keeps, gains and loses; change nothing."),
    ] = False,
) -> str:
    """ATTSYNC: give every insert of a block the attributes its definition has now, keeping the values already typed.

    After a block's definition changed (an attribute added, removed, moved or
    resized), the inserts already placed still carry the old attributes.
    This brings them in step: a value already typed is kept, matched by tag;
    a tag the definition gained comes in with its default; a tag it lost, or
    made constant, goes. Each attribute goes back to where the definition puts
    it (position, height, style). An attribute holding a field, and a
    multi-line one, keeps its own text and place. Inserts on a locked layer are
    left out and listed. Done by the Heron plug-in in one transaction: all of
    it or none; one undo step.

    Returns:
        JSON: {"block", "touched", "changing_tags", "values_kept", "attributes_added",
        "attributes_dropped", "inserts": [{handle, keep, add, drop}], "skipped": [{handle, why}],
        "definitions_added": [tag], "synced": what the plug-in did, "before_after"}

    Examples:
        - Use when: "I added a SIZE attribute to the valve tag block, update
          all the valves" -> block='VALVE TAG'.
        - Use when: "add an invisible MAKE attribute to the PUMP block and put
          it on every pump" -> add_attributes=[{"tag": "MAKE", "invisible": true}].
        - Use when: "ATTSYNC the title block" after it was redefined.
        - Don't use when: only the values change - autocad_set_attributes,
          or autocad_apply_attribute_sheet from Excel.

    Error Handling:
        - A block that is not in the drawing points at autocad_list_blocks.
        - A new tag that the block already has is refused before anything changes.
    """

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        definition_block, definitions = _block_definition(doc, block)
        added: list[dict[str, Any]] = []
        if add_attributes:
            try:
                origin = [float(v) for v in definition_block.Origin]
            except Exception:  # noqa: BLE001 - a block drawn at 0,0
                origin = [0.0, 0.0, 0.0]
            shifted = []
            for number, spec in enumerate(add_attributes, 1):
                if isinstance(spec, dict) and spec.get("position") is not None:
                    given = spec["position"]
                    try:
                        offset = [float(v) for v in given]
                    except (TypeError, ValueError):
                        offset = []
                    if not 2 <= len(offset) <= 3:
                        raise AutocadError(f"Attribute {number}: the position must be [x, y] from the base point, not {given!r}. Nothing was changed.")
                    offset = (offset + [0.0])[:3]
                    spec = {**spec, "position": [origin[i] + offset[i] for i in range(3)]}
                shifted.append(spec)
            try:
                added = plan_definitions(
                    shifted, origin, _text_height(doc),
                    taken=[d["tag"] for d in definitions], taken_at=[d["at"] for d in definitions if d["at"]],
                )  # fmt: skip
            except AttributeSpecError as exc:
                raise AutocadError(f"{exc} Nothing was changed.") from None
        inserts = _inserts(doc, block)
        locked = _locked(doc, {i["layer"] for i in inserts if i["block"].strip().lower() == block.strip().lower()})
        plan = plan_sync(block.strip(), definitions + added, inserts, only=handles, locked_layers=locked)
        listed = [
            {"handle": item["handle"], "keep": item["keep"], "add": item["add"], "drop": item["drop"]}
            for item in plan["inserts"][:MOST_LISTED]
        ]
        result: dict[str, Any] = {
            **{key: value for key, value in plan.items() if key != "inserts"},
            "inserts": listed,
            "definitions_added": [a["tag"] for a in added],
        }
        if len(plan["inserts"]) > MOST_LISTED:
            result["inserts_more"] = len(plan["inserts"]) - MOST_LISTED
        if dry_run:
            return {**result, "dry_run": True}
        if not plan["inserts"] and not added:
            return {**result, "dry_run": False, "synced": None, "note": "Nothing to sync: no insert of the block was chosen. Nothing was changed."}
        args = {
            "block": block.strip(),
            "handles": [item["handle"] for item in plan["inserts"]],
            "add": [
                {key: a[key] for key in ("tag", "prompt", "default", "position", "height", "invisible", "constant", "preset")}
                for a in added
            ],
        }
        report = in_plugin("sync_attributes", args, "Syncing block attributes (ATTSYNC)")
        changes = [
            {"handle": item["handle"], "property": f"attribute {tag}", "from": None, "to": value}
            for item in plan["inserts"]
            for tag, value in item["added"]
        ] + [
            {"handle": item["handle"], "property": f"attribute {tag}", "from": value, "to": None}
            for item in plan["inserts"]
            for tag, value in item["dropped"]
        ]
        return {**result, "dry_run": False, "synced": report, **before_after(changes)}

    return dumps(await run(work))
