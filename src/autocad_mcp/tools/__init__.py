"""MCP tool definitions, grouped by subject.

Importing this package registers every tool onto the shared FastMCP instance in
``core.registry`` — the decorators run at import time, so ``register_all()``
only has to make sure each module is imported once.
"""

from __future__ import annotations


def register_all() -> None:
    """Import every tool module, registering its tools on the shared server."""
    from . import (  # noqa: F401
        activity,
        advanced,
        annotate,
        annotation_scales,
        attribute_sheet,
        batch,
        between_drawings,
        blocks,
        check_folder,
        checklist_share,
        checklists,
        companion,
        convert,
        coordinates,
        dimensions,
        dimensions_edit,
        document,
        drafting,
        draw,
        draw_extra,
        drawing_report,
        drawing_tools,
        edit2d,
        explain,
        files,
        geometry_tools,
        labels,
        layer_states,
        layers,
        lighting,
        materials,
        modify,
        patterns,
        project_notes,
        publish,
        query,
        resources,
        saved_commands,
        sections,
        sequence,
        settings,
        shapes,
        sheet_set,
        sheets,
        solid_edits,
        solids,
        standards,
        superhatch,
        surfaces,
        tables,
        takeoff,
        text_tools,
        views,
        xrefs,
    )


__all__ = ["register_all"]
