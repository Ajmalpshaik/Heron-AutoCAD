"""Symbol tables: layers, linetypes, and the shared property application.

Layer, colour and linetype are options on every creation tool, so resolving
them lives here rather than being repeated per tool.
"""

from __future__ import annotations

from typing import Any

from ..core.errors import AutocadError, com_message, is_retryable, raise_if_busy
from .lisp import refuse_control

# Characters AutoCAD rejects in symbol-table names.
INVALID_NAME_CHARS = set('<>/\\":;?*|,=`')


def validate_name(name: str, kind: str = "layer") -> str:
    """Reject names AutoCAD will not accept, before it raises a vague error."""
    # Before the strip: strip() would drop a trailing newline or tab unseen (#249).
    refuse_control(name, f"{kind} name")
    clean = name.strip()
    if not clean:
        raise AutocadError(f"A {kind} name cannot be empty.")
    bad = sorted(set(clean) & INVALID_NAME_CHARS)
    if bad:
        raise AutocadError(
            f"The {kind} name '{name}' contains {' '.join(bad)}, which AutoCAD "
            "does not allow. Avoid < > / \\ \" : ; ? * | , = ` in names."
        )
    return clean


def ensure_layer(doc: Any, name: str) -> tuple[Any, bool]:
    """Fetch a layer, creating it when the drawing does not have one.

    Drafting requests routinely name a layer that is not in the drawing.
    Creating it is what a drafter would do; callers report back whether it
    happened so the change is never silent.

    Returns:
        (layer object, True when it was just created)
    """
    clean = validate_name(name, "layer")
    # A busy AutoCAD is not a missing layer: that refusal goes up to the retry
    # as it is ("Could not create layer 'A-ANNO-TTLE': Call was rejected by
    # callee.", Luxury Suite 3, 2026-11-18).
    try:
        return doc.Layers.Item(clean), False
    except BaseException as exc:  # noqa: BLE001 - not present, create below
        if is_retryable(exc):
            raise
    try:
        return doc.Layers.Add(clean), True
    except BaseException as exc:  # noqa: BLE001
        if is_retryable(exc):
            raise
        raise AutocadError(
            f"Could not create layer '{clean}': {com_message(exc)}"
        ) from exc


def ensure_linetype(doc: Any, name: str) -> None:
    """Load a linetype from AutoCAD's definition files if it is not loaded."""
    clean = validate_name(name, "linetype")
    try:
        doc.Linetypes.Item(clean)
        return
    except BaseException as exc:  # noqa: BLE001 - needs loading
        if is_retryable(exc):
            raise  # AutoCAD busy, not a linetype to load

    for source in ("acadiso.lin", "acad.lin"):
        try:
            doc.Linetypes.Load(clean, source)
            return
        except BaseException as exc:  # noqa: BLE001 - try the next definition file
            raise_if_busy(exc)
            continue
    raise AutocadError(
        f"Linetype '{clean}' is not in the drawing and was not found in "
        "acadiso.lin or acad.lin. Common names are CONTINUOUS, CENTER, HIDDEN, "
        "DASHED, DASHDOT, PHANTOM, DIVIDE."
    )


def apply_properties(
    doc: Any,
    entity: Any,
    layer: str | None = None,
    color: int | None = None,
    linetype: str | None = None,
) -> dict[str, Any]:
    """Apply the shared layer / colour / linetype options to a new entity.

    Returns any notes worth surfacing to the agent, such as a layer that had to
    be created.
    """
    notes: dict[str, Any] = {}
    if layer:
        _, created = ensure_layer(doc, layer)
        entity.Layer = layer.strip()
        if created:
            notes["layer_created"] = layer.strip()
    if color is not None:
        entity.Color = color
    if linetype:
        ensure_linetype(doc, linetype)
        entity.Linetype = linetype.strip()
    return notes


def describe_layer(layer: Any) -> dict[str, Any]:
    """Serialize one layer's state."""

    def _try(getter, default=None):
        try:
            return getter()
        except BaseException as exc:  # noqa: BLE001
            raise_if_busy(exc)
            return default

    return {
        "name": _try(lambda: str(layer.Name), ""),
        "color": _try(lambda: int(layer.Color)),
        "linetype": _try(lambda: str(layer.Linetype), ""),
        "lineweight": _try(lambda: int(layer.Lineweight)),
        "on": bool(_try(lambda: layer.LayerOn, True)),
        "frozen": bool(_try(lambda: layer.Freeze, False)),
        "locked": bool(_try(lambda: layer.Lock, False)),
        "plottable": bool(_try(lambda: layer.Plottable, True)),
    }
