"""The shared MCPServer instance plus the plumbing every tool reuses.

Tool modules import ``mcp`` from here and register onto it with decorators, so
the server keeps one registry while the tools stay grouped by subject.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from enum import Enum
from typing import Any

import pythoncom
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import progress
from .connection import mark_writing
from .errors import AutocadError, com_message

mcp = MCPServer(
    "autocad_mcp",
    title="Heron AI for AutoCAD",
    version="1.7.0",
    instructions=(
        "Controls the AutoCAD instance running on this machine through its COM "
        "Automation interface. Changes appear live in the user's open drawing.\n\n"
        "Call autocad_status first: coordinates are in the drawing's own units, "
        "and that tool reports whether the drawing is in millimetres, metres or "
        "inches. All angles in this server are DEGREES.\n\n"
        "COORDINATES ARE WORLD COORDINATES. autocad_status also reports the "
        "drawing's UCS and adds a 'ucs_advice' line when it is not the world "
        "one. If a UCS is set, the modeller's numbers are not world numbers: "
        "convert them with autocad_convert_points, or pass coords='ucs' on a "
        "tool that offers it (autocad_batch_draw does). Never ignore that "
        "advice — the geometry lands somewhere nobody meant.\n\n"
        "Entities are identified by their drawing 'handle', which every creation "
        "and query tool returns and every modify tool accepts.\n\n"
        "FINDING THE RIGHT TOOL. There are over a hundred. Ask "
        "autocad://tools/find/{phrase} in plain words - 'how many metres of "
        "DN50 pipe on this layer', 'does the ductwork clash with the steel' - "
        "and it answers with the tool, its padlock and why it matched. For the "
        "whole catalogue read autocad://tools: every tool grouped by the "
        "padlock it needs, with a one-line summary and 'Use when' lines in the "
        "words a draftsman would use. Neither needs AutoCAD, so both answer "
        "before anything is connected. "
        "Each tool's own 'Use when' and \"Don't use when\" lines name the "
        "better tool when there is one — follow them rather than forcing the "
        "first tool that looks close.\n\n"
        "Prefer the tool that does the whole job in one call: "
        "autocad_batch_draw over many single draws, autocad_make_shape over "
        "building a standard shape by hand, autocad_dimension_run over "
        "one dimension at a time, autocad_sequence to run a settled list of "
        "steps together (AutoLISP's progn). One call is one undo step for the "
        "user, which matters more than it looks.\n\n"
        "If a tool reports AutoCAD is busy or mid-command, the user needs to "
        "press Esc in AutoCAD — no retry will clear it.\n\n"
        "This is Heron AI for AutoCAD. Nothing reaches AutoCAD until the user "
        "presses the Heron button on the Heron tab (or types HERON), and the "
        "padlocks there decide what is allowed: Changes for drawing and "
        "modifying, Publish for saving and exporting, Admin for commands and "
        "AutoLISP. When a tool is refused, pass the refusal on in plain words; "
        "never try to get round it. If Heron itself seems broken (not connected, "
        "an old plug-in, an update not taking), read autocad://diagnose: it says "
        "what to fix, without AutoCAD. Call autocad_preview to look at what you "
        "drew before saying it is done.\n\n"
        "DRAFTING RULES (draw like a senior draftsman; the user's own standard):\n"
        "1. Units first: autocad_status on every drawing before drawing in it. "
        "Draw in the user's open drawing unless they ask for a new one.\n"
        "2. Every separate part (fitting, elbow, valve, clamp, plate, anchor, support "
        "piece, equipment) becomes a named block with autocad_make_block; reuse it with "
        "autocad_insert_block. Pipes, ducts and runs may stay lines/polylines.\n"
        "3. Every label uses autocad_add_label: the user's TLD style (MTEXT + leader "
        "ending under the text, shape L or angled) or kind='mleader'. Never fake a "
        "leader with a line and a text. For more than two labels use autocad_batch_labels: "
        "the whole column in one call, with arrow_scale set to the view's scale.\n"
        "4. Labels sit in a tidy column beside the detail, evenly spaced, in the same "
        "order as the parts they point at, with short leaders and no leader crossing "
        "another; text_align='right' for a column on the left.\n"
        "5. Dimensions grouped on one side, whole numbers (text_override when needed); "
        "set DIMSCALE to the drawing scale first.\n"
        "6. Views aligned: plan under the elevation on the same centre line; each view "
        "titled, underlined, with a smaller 'SCALE 1:n' line; notes aligned to the top.\n"
        "7. Proper layers per discipline; text heights as paper size x scale.\n"
        "8. Check autocad_preview: fix any overlap or crossing before saying it is done. "
        "The draw_detail prompt has the full checklist.\n\n"
        "SHEET RULES (docs/09):\n"
        "9. Set the drawing up before drawing in it: autocad_drawing_setup with the "
        "units and the scale. The scale sets DIMSCALE, LTSCALE and the annotation "
        "scale together, and paper_text_height gives the model text height.\n"
        "10. Sheets: autocad_create_layout, then autocad_place_title_block (all_layouts "
        "and per_layout_attributes do a whole set), then autocad_add_viewport. All of it "
        "in one autocad_sequence where it belongs together.\n"
        "11. Every viewport gets a real scale and stays locked (the default). A plan on "
        "a rotated grid gets align_to_ucs=true so it reads upright on the sheet.\n"
        "12. Name an area once with autocad_save_view, then use that view_name for the "
        "viewport and for autocad_export(area='view') — one location, not two guesses.\n"
        "13. An import is not a drawing: autocad_remap_layers, then autocad_tidy_entities "
        "(both show a dry run first), then autocad_check_standards to prove it.\n\n"
        "GEOMETRY, ANNOTATION AND 3D (docs/10):\n"
        "14. Never build a named shape out of lines. autocad_make_shape draws 24 of "
        "them from their dimensions - slot, rounded_rectangle, hexagon, flange, "
        "steel_section, elbow, duct_transition, stair, ladder, truss, grating, gear, "
        "cone_development (a reducer's flat pattern), and the furniture (detail_bubble, "
        "section_mark, north_arrow, scale_bar, level_mark, revision_tag). dry_run shows "
        "the geometry first.\n"
        "15. An arc belongs to its object: a slot, a rounded corner or an elbow is one "
        "polyline with bulges, never loose arcs. autocad_batch_draw takes bulges.\n"
        "16. Dimension the run, not the dimension: autocad_dimension_run does a chain, "
        "a baseline set or ordinates in one call, in order, at one offset, with the "
        "overall above. autocad_add_centre_marks puts the cross on every circle.\n"
        "17. One note with several arrows is one autocad_add_multileader. A schedule is "
        "an autocad_add_table, not a grid of loose text. A revision is an "
        "autocad_add_revision_cloud round the object.\n"
        "18. In 3D: draw the section, then autocad_extrude_profile it (extrude or "
        "revolve), then autocad_solid_boolean the holes out, then "
        "autocad_solid_properties for the volume. autocad_add_solid places a primitive "
        "by the centre of its BASE. Before saying a 3D job is done, "
        "autocad_set_3d_view(direction='sw_iso', visual_style='hidden') then "
        "autocad_preview."
    ),
)


# Every call's context is kept, so the gate can send "still working" notes.
progress.install(mcp)


def tool_meta(
    title: str,
    *,
    read_only: bool = False,
    destructive: bool = False,
    idempotent: bool = False,
    open_world: bool = False,
) -> dict[str, Any]:
    """Build the title and annotations kwargs for ``@mcp.tool``.

    Keeping this in one place means every tool declares its hints the same way,
    and the SDK's annotation type is named once rather than 49 times.
    """
    return {
        "title": title,
        "annotations": ToolAnnotations(
            read_only_hint=read_only,
            destructive_hint=destructive,
            idempotent_hint=idempotent,
            open_world_hint=open_world,
        ),
    }


# AutoCAD Color Index values that have common names.
ACI_COLORS = {
    "byblock": 0,
    "red": 1,
    "yellow": 2,
    "green": 3,
    "cyan": 4,
    "blue": 5,
    "magenta": 6,
    "white": 7,
    "black": 7,
    "grey": 8,
    "gray": 8,
    "bylayer": 256,
}


class ResponseFormat(str, Enum):
    """Output format for tools that can render either way."""

    MARKDOWN = "markdown"
    JSON = "json"


def to_aci(color: str | int | None) -> int | None:
    """Resolve a colour name or an AutoCAD Color Index number to an ACI int.

    Agents phrase colours both ways; rejecting one of them only produces a
    retry loop, so both are accepted here. Some clients send a number as a
    JSON-quoted string ('"7"'), so stray quotes around the value are removed.
    """
    if color is None or color == "":
        return None
    if isinstance(color, int) and not isinstance(color, bool):
        value = color
    else:
        text = str(color).strip().strip("\"'").strip().lower()
        if not text:
            return None
        if text in ACI_COLORS:
            return ACI_COLORS[text]
        try:
            value = int(text)
        except ValueError:
            raise AutocadError(
                f"'{color}' is not a colour this server understands. Use an "
                "AutoCAD Color Index number from 0-256, or one of: "
                + ", ".join(sorted(set(ACI_COLORS)))
                + "."
            ) from None
    if not 0 <= value <= 256:
        raise AutocadError(
            f"AutoCAD Color Index must be between 0 and 256, got {value}. "
            "256 means ByLayer, 0 means ByBlock."
        )
    return value


def dumps(payload: Any) -> str:
    """Serialize a tool result as JSON."""
    return json.dumps(payload, indent=2, default=str)


def tool_errors(func: Callable) -> Callable:
    """Turn COM and connection failures into actionable text.

    Every tool wears this, so a busy AutoCAD, a closed drawing or a stale
    handle reads as an instruction to the agent rather than a traceback.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        # Every call goes through the Heron gate: connection, padlocks,
        # wrong-drawing guard, Keep or Discard, audit (core/gate.py).
        from .gate import guarded

        return await guarded(func.__name__, lambda: _run(*args, **kwargs))

    async def _run(*args: Any, **kwargs: Any) -> str:
        try:
            return await func(*args, **kwargs)
        except AutocadError as exc:
            return f"Error: {exc}"
        except pythoncom.com_error as exc:
            return (
                f"Error: AutoCAD rejected the operation — {com_message(exc)}. "
                "Check that the drawing is not read-only, the target layer is "
                "not locked or frozen, and no command is waiting for input."
            )
        except (ValueError, TypeError) as exc:
            return f"Error: Invalid input — {exc}"
        except Exception as exc:  # noqa: BLE001 - last resort, still actionable
            return f"Error: Unexpected {type(exc).__name__} — {exc}"

    return wrapper


class undo_mark:
    """Group everything a write tool does into one AutoCAD undo step.

    Without this, each primitive lands as its own undo record and the user has
    to press Ctrl+Z once per entity to back out a single tool call.
    """

    def __init__(self, doc: Any) -> None:
        self.doc = doc

    def __enter__(self) -> Any:
        # From here on the drawing may change, so a busy signal must not
        # re-run the work (see connection._with_retry).
        mark_writing()
        try:
            self.doc.StartUndoMark()
        except BaseException:  # noqa: BLE001 - grouping is a nicety, not a gate
            pass
        return self.doc

    def __exit__(self, *exc_info: Any) -> None:
        try:
            self.doc.EndUndoMark()
        except BaseException:  # noqa: BLE001
            pass
