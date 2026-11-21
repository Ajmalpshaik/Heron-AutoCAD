"""Block attributes: planning attribute definitions, and what ATTSYNC does (D-82).

Two jobs, both plain functions over plain values, tested without AutoCAD:

* **Attribute definitions** for ``autocad_make_block`` (and for adding one to
  a block that already exists): the tag, prompt, default value, position and
  height, and the AutoCAD mode flags (invisible, constant, preset) checked the
  way ATTDEF checks them, before anything is sent.
* **ATTSYNC**: after a block's definition changed, which inserts get which
  attributes. A value the modeller already typed is kept, matched by tag; a
  tag the definition gained comes in with its default; a tag the definition
  lost, or one it made constant, goes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# AcAttributeMode: the flags AutoCAD keeps in one number.
MODE_INVISIBLE = 1
MODE_CONSTANT = 2
MODE_VERIFY = 4
MODE_PRESET = 8
FLAGS = (("invisible", MODE_INVISIBLE), ("constant", MODE_CONSTANT), ("preset", MODE_PRESET))
# An attribute stacked under the base point is this many text heights below the one above it.
STACK_GAP = 1.5
MOST_ATTRIBUTES = 50
MOST_TAG = 255
KNOWN_KEYS = {"tag", "prompt", "default", "value", "position", "height", *(name for name, _ in FLAGS)}


class AttributeSpecError(ValueError):
    """An attribute definition that cannot be made; the message says why in plain words."""


def _flag(spec: dict[str, Any], name: str, number: int) -> bool:
    value = spec.get(name, False)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise AttributeSpecError(f"Attribute {number}: '{name}' must be true or false, not {value!r}.")
    return value


def clean_tag(tag: Any, number: int = 1) -> str:
    """A tag as AutoCAD stores it: no spaces, capitals (ATTDEF makes them capitals itself)."""
    text = "" if tag is None else str(tag).strip()
    if not text:
        raise AttributeSpecError(f"Attribute {number} has no tag. Give each one a tag, e.g. 'TAG' or 'SIZE'.")
    if any(ch.isspace() for ch in text):
        raise AttributeSpecError(
            f"The tag '{text}' has a space in it, which AutoCAD does not allow in a tag. Use '_' instead, "
            f"e.g. '{'_'.join(text.split())}'."
        )
    if "!" in text:
        raise AttributeSpecError(f"The tag '{text}' has a '!', which AutoCAD does not allow in a tag.")
    if len(text) > MOST_TAG:
        raise AttributeSpecError(f"The tag '{text[:20]}...' is longer than {MOST_TAG} characters.")
    return text.upper()


def mode_of(invisible: bool = False, constant: bool = False, preset: bool = False) -> int:
    """The AcAttributeMode number for these flags."""
    return (MODE_INVISIBLE if invisible else 0) | (MODE_CONSTANT if constant else 0) | (MODE_PRESET if preset else 0)


def flags_of(mode: int) -> dict[str, bool]:
    """The flags a mode number holds, by name."""
    return {name: bool(int(mode) & bit) for name, bit in FLAGS}


def plan_definitions(
    specs: Sequence[dict[str, Any]],
    base_point: Sequence[float],
    default_height: float,
    taken: Sequence[str] = (),
    taken_at: Sequence[Sequence[float]] = (),
) -> list[dict[str, Any]]:
    """Check attribute definitions and fill in what was left out, in the order given.

    ``base_point`` is where an attribute with no position goes: under it, one
    below the other, so none sits on top of another. ``taken`` are tags the
    block already has, and ``taken_at`` where they sit (for adding to an
    existing block): then the stack starts under the lowest of them instead.
    Every problem is a refusal before anything is made.

    Returns one dict per attribute: tag, prompt, default, position [x, y, z],
    height, mode, and the three flags.
    """
    if not specs:
        return []
    if len(specs) > MOST_ATTRIBUTES:
        raise AttributeSpecError(f"{len(specs)} attributes is more than {MOST_ATTRIBUTES} on one block.")
    if not default_height or default_height <= 0:
        default_height = 2.5
    base = [float(v) for v in base_point] + [0.0] * (3 - len(base_point))
    there = [[float(v) for v in at] + [0.0] * (3 - len(at)) for at in taken_at if len(at) >= 2]
    if there:
        base = min(there, key=lambda at: at[1])  # the lowest one already in the block
    seen = {str(t).strip().upper() for t in taken}
    planned: list[dict[str, Any]] = []
    stacked = 0
    for number, spec in enumerate(specs, 1):
        if not isinstance(spec, dict):
            raise AttributeSpecError(f"Attribute {number} must be an object such as {{\"tag\": \"TAG\"}}, not {spec!r}.")
        unknown = sorted(set(spec) - KNOWN_KEYS)
        if unknown:
            raise AttributeSpecError(
                f"Attribute {number} has {', '.join(unknown)}, which Heron does not know. An attribute takes "
                "tag, prompt, default, position, height, invisible, constant and preset."
            )
        tag = clean_tag(spec.get("tag"), number)
        if tag in seen:
            raise AttributeSpecError(f"The tag '{tag}' is given twice. Each attribute of a block needs its own tag.")
        seen.add(tag)
        invisible = _flag(spec, "invisible", number)
        constant = _flag(spec, "constant", number)
        preset = _flag(spec, "preset", number)
        raw = spec.get("default", spec.get("value", ""))
        default = "" if raw is None else str(raw)
        if constant and preset:
            raise AttributeSpecError(
                f"'{tag}' is both constant and preset. Constant means the value is fixed in the block and "
                "never asked for; preset means it is filled in but can still be changed. Pick one."
            )
        if constant and not default.strip():
            raise AttributeSpecError(f"'{tag}' is constant but has no default value. A constant attribute shows its default on every insert.")
        height = spec.get("height")
        if height is None:
            height = float(default_height)
        else:
            try:
                height = float(height)
            except (TypeError, ValueError):
                raise AttributeSpecError(f"'{tag}': the height must be a number, not {height!r}.") from None
            if height <= 0:
                raise AttributeSpecError(f"'{tag}': the height must be above zero.")
        position = spec.get("position")
        if position is None:
            stacked += 1
            position = [base[0], base[1] - stacked * STACK_GAP * height, base[2]]
        else:
            try:
                position = [float(v) for v in position]
            except (TypeError, ValueError):
                raise AttributeSpecError(f"'{tag}': the position must be [x, y], not {position!r}.") from None
            if len(position) < 2:
                raise AttributeSpecError(f"'{tag}': the position must be [x, y].")
            position = (position + [base[2]])[:3]
        prompt = spec.get("prompt")
        prompt = tag if prompt is None or not str(prompt).strip() else str(prompt).strip()
        planned.append(
            {
                "tag": tag,
                "prompt": prompt,
                "default": default,
                "position": [round(v, 9) for v in position],
                "height": height,
                "mode": mode_of(invisible, constant, preset),
                "invisible": invisible,
                "constant": constant,
                "preset": preset,
            }
        )
    return planned


# ---------------------------------------------------------------------------
# ATTSYNC
# ---------------------------------------------------------------------------


def sync_one(definition: Sequence[dict[str, Any]], existing: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """What ATTSYNC does to one insert, exactly as the plug-in does it.

    ``definition`` is the block's attribute definitions in order ({tag,
    default, constant}); ``existing`` the insert's attributes now, as
    (tag, value) in order. A tag that appears twice is matched in order: the
    first definition of it takes the first value of it.

    The attributes kept stay where they are in the insert's list; the new ones
    follow, in the definition's order; the lost ones go.

    Returns {"keep": {tag: value}, "add": {tag: default}, "drop": [tag],
    "kept": [(tag, value)], "added": [(tag, default)], "dropped": [(tag, value
    it had)], "attributes": [(tag, value)] as the insert will have them,
    "changes_tags": bool}. ``keep`` and ``add`` show a tag given twice once;
    the lists have every one.
    """
    waiting: dict[str, list[int]] = {}
    tags = [str(tag).strip().upper() for tag, _ in existing]
    values = ["" if value is None else str(value) for _, value in existing]
    for index, tag in enumerate(tags):
        waiting.setdefault(tag, []).append(index)
    kept_at: list[int] = []
    added: list[tuple[str, str]] = []
    for item in definition:
        tag = str(item.get("tag", "")).strip().upper()
        if not tag or item.get("constant"):
            continue  # a constant attribute lives in the definition, not on the insert
        if waiting.get(tag):
            kept_at.append(waiting[tag].pop(0))
        else:
            added.append((tag, "" if item.get("default") is None else str(item.get("default"))))
    kept = [(tags[i], values[i]) for i in sorted(kept_at)]
    dropped = [(tags[i], values[i]) for i in range(len(tags)) if i not in set(kept_at)]
    after = kept + added
    keep: dict[str, str] = {}
    add: dict[str, str] = {}
    for tag, value in kept:
        keep.setdefault(tag, value)
    for tag, value in added:
        add.setdefault(tag, value)
    return {
        "keep": keep,
        "add": add,
        "drop": [tag for tag, _ in dropped],
        "kept": kept,
        "added": added,
        "dropped": dropped,
        "attributes": after,
        "changes_tags": bool(added or dropped),
    }


def plan_sync(
    block: str,
    definition: Sequence[dict[str, Any]],
    inserts: Sequence[dict[str, Any]],
    only: Sequence[str] | None = None,
    locked_layers: Sequence[str] = (),
) -> dict[str, Any]:
    """Which inserts ATTSYNC touches, and what each keeps, gains and loses.

    ``inserts`` are {"handle", "block" (its effective name), "layer",
    "attributes": [(tag, value)]}, and "inside" (the block whose definition
    holds it) for a nested one. Only inserts of ``block`` (by effective
    name, so a dynamic block's changed copies count) are touched; ``only``
    narrows them to some handles. An insert on a locked layer is left out and
    listed: AutoCAD would refuse the whole job for it.

    Every insert of the block is touched, because ATTSYNC also puts each
    attribute back where the definition has it (position, height, style),
    even when no tag changed; ``changes_tags`` says which ones gain or lose one.
    """
    wanted = block.strip().lower()
    chosen = {str(h).strip().upper() for h in only} if only else None
    locked = {str(name).strip().lower() for name in locked_layers}
    touched: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    found: set[str] = set()
    for insert in inserts:
        handle = str(insert.get("handle", "")).strip().upper()
        if str(insert.get("block", "")).strip().lower() != wanted:
            if chosen is not None and handle in chosen:
                skipped.append({"handle": handle, "why": f"it is an insert of '{insert.get('block')}', not '{block}'"})
                found.add(handle)
            continue
        if chosen is not None and handle not in chosen:
            continue
        found.add(handle)
        layer = str(insert.get("layer", ""))
        if layer.strip().lower() in locked:
            skipped.append({"handle": handle, "why": f"its layer '{layer}' is locked: unlock it first"})
            continue
        plan = sync_one(definition, insert.get("attributes") or [])
        where = {"inside": insert["inside"]} if insert.get("inside") else {}
        touched.append({"handle": handle, **where, **plan})
    if chosen is not None:
        skipped.extend({"handle": h, "why": f"no insert of '{block}' has that handle"} for h in sorted(chosen - found))
    return {
        "block": block,
        "inserts": touched,
        "skipped": skipped,
        "touched": len(touched),
        "changing_tags": sum(1 for item in touched if item["changes_tags"]),
        "values_kept": sum(len(item["kept"]) for item in touched),
        "attributes_added": sum(len(item["added"]) for item in touched),
        "attributes_dropped": sum(len(item["dropped"]) for item in touched),
    }
