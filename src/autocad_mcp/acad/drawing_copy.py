"""Copying objects from one open drawing into another: what comes with them (D-83).

AutoCAD's CopyObjects, given an owner in another drawing, copies the objects
and everything they need that the other drawing lacks: their layers,
linetypes, text and dimension styles, and the blocks they insert (with the
blocks those blocks insert, and so on). A name the target drawing already
has is **not** brought in: the target's own one is used, so a block called
VALVE in both drawings shows the target's VALVE. These plain functions say
which names come in and which are the target's own, before anything is
copied, so the modeller is told; they are tested without AutoCAD.
"""

from __future__ import annotations

import ntpath
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

KINDS = ("layers", "linetypes", "text_styles", "dim_styles", "blocks")
# Names every drawing has: never news, never worth listing.
ALWAYS_THERE = {
    "layers": {"0"},
    "linetypes": {"bylayer", "byblock", "continuous"},
    "text_styles": {"standard"},
    "dim_styles": {"standard"},
    "blocks": set(),
}
MOST_BLOCK_DEPTH = 20


def empty_uses() -> dict[str, set[str]]:
    return {kind: set() for kind in KINDS}


def _ordinary(kind: str, name: str) -> bool:
    """A name worth reporting: not blank, not one every drawing has, not an anonymous *U / *D block."""
    clean = name.strip()
    if not clean or clean.lower() in ALWAYS_THERE[kind]:
        return False
    return not (kind == "blocks" and clean.startswith("*"))


def find_open(drawings: Sequence[tuple[str, str]], wanted: str) -> int:
    """Which open drawing is meant: by file name (the .dwg optional) or by full path, any case.

    ``drawings`` are (name, full path) in AutoCAD's order. Raises ValueError
    naming the open drawings when none matches, or when the name fits two
    (two open files called PLAN.dwg in different folders: give the path).
    """
    text = wanted.strip().strip('"')
    if not text:
        raise ValueError("Name the drawing to copy from, e.g. 'site-plan.dwg'.")
    # AutoCAD's paths are Windows paths: any case, either slash.
    by_path = ntpath.normcase(ntpath.normpath(text)) if ("\\" in text or "/" in text) else None
    stem = ntpath.splitext(ntpath.basename(text).lower())[0]
    hits = []
    for index, (name, full) in enumerate(drawings):
        if by_path is not None:
            if full and ntpath.normcase(ntpath.normpath(full)) == by_path:
                hits.append(index)
        elif ntpath.splitext(name.lower())[0] == stem:
            hits.append(index)
    if len(hits) == 1:
        return hits[0]
    listed = ", ".join(name for name, _ in drawings) or "none"
    if not hits:
        raise ValueError(f"No open drawing is called '{wanted}'. Open now: {listed}. Open it first with autocad_open_drawing.")
    raise ValueError(f"Two open drawings are called '{wanted}'. Give its full path instead.")


def blocks_needed(top: Iterable[str], inside: Mapping[str, Mapping[str, Iterable[str]]]) -> list[str]:
    """Every block the copy needs: those inserted directly, and those inside them, at any depth.

    ``inside`` maps a block name to what its definition uses ({"blocks":
    [...], ...}). A block that inserts itself, directly or round a loop, is
    followed once.
    """
    seen: dict[str, str] = {}
    todo = [(name, 0) for name in top]
    while todo:
        name, depth = todo.pop()
        key = name.strip().lower()
        if not key or key in seen or depth > MOST_BLOCK_DEPTH:
            continue
        seen[key] = name.strip()
        for nested in (inside.get(name) or inside.get(name.strip()) or {}).get("blocks", ()):
            todo.append((nested, depth + 1))
    return sorted(seen.values(), key=str.lower)


def what_comes_along(
    uses: Mapping[str, Iterable[str]],
    inside: Mapping[str, Mapping[str, Iterable[str]]],
    target_has: Mapping[str, Iterable[str]],
) -> dict[str, Any]:
    """The names a copy brings into the target drawing, and the ones the target already has.

    ``uses`` is what the copied objects use themselves; ``inside`` what each
    block definition uses; ``target_has`` the target drawing's own names per
    kind. Returns {"brought_in": {kind: [names]}, "already_here": {kind:
    [names]}}: brought in are copied with the objects; already here are the
    target's own, used as they are.
    """
    needed = {kind: {str(n).strip() for n in uses.get(kind, ()) if str(n).strip()} for kind in KINDS}
    for block in blocks_needed(needed["blocks"], inside):
        needed["blocks"].add(block)
        definition = inside.get(block) or {}
        for kind in KINDS:
            needed[kind].update(str(n).strip() for n in definition.get(kind, ()) if str(n).strip())
    here = {kind: {str(n).strip().lower() for n in target_has.get(kind, ())} for kind in KINDS}
    brought: dict[str, list[str]] = {}
    already: dict[str, list[str]] = {}
    for kind in KINDS:
        names = {}
        for name in needed[kind]:
            if _ordinary(kind, name):
                names.setdefault(name.lower(), name)
        new = sorted((n for k, n in names.items() if k not in here[kind]), key=str.lower)
        old = sorted((n for k, n in names.items() if k in here[kind]), key=str.lower)
        if new:
            brought[kind] = new
        if old:
            already[kind] = old
    return {"brought_in": brought, "already_here": already}


def offset(base_point: Sequence[float], to_point: Sequence[float] | None) -> list[float]:
    """How far the copies move: from the base point in the source to the point in the target."""
    base = [float(v) for v in base_point] + [0.0] * (3 - len(base_point))
    if to_point is None:
        return [0.0, 0.0, 0.0]
    to = [float(v) for v in to_point] + [0.0] * (3 - len(to_point))
    return [round(to[i] - base[i], 9) for i in range(3)]
