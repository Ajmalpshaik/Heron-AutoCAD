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
        checklists,
        companion,
        convert,
        coordinates,
        dimensions,
        dimensions_edit,
        document,
        drafting,
        draw,
        drawing_report,
        drawing_tools,
        edit2d,
        explain,
        geometry_tools,
        labels,
        layer_states,
        layers,
        lighting,
        materials,
        modify,
        patterns,
        pdf_import,
        project_notes,
        publish,
        query,
        resources,
        saved_commands,
        sequence,
        settings,
        shapes,
        sheets,
        solid_edits,
        solids,
        standards,
        superhatch,
        tables,
        takeoff,
        text_tools,
        views,
        xrefs,
    )


__all__ = ["register_all"]
