"""MCP tool definitions, grouped by subject.

Importing this package registers every tool onto the shared FastMCP instance in
``core.registry`` — the decorators run at import time, so ``register_all()``
only has to make sure each module is imported once.
"""

from __future__ import annotations


def register_all() -> None:
    """Import every tool module, registering its tools on the shared server."""
    from . import (  # noqa: F401
        advanced,
        annotate,
        batch,
        blocks,
        convert,
        coordinates,
        dimensions,
        document,
        drafting,
        draw,
        drawing_report,
        drawing_tools,
        geometry_tools,
        labels,
        layers,
        lighting,
        materials,
        modify,
        patterns,
        publish,
        query,
        resources,
        sequence,
        settings,
        shapes,
        sheets,
        solid_edits,
        solids,
        standards,
        superhatch,
        takeoff,
        text_tools,
        views,
        xrefs,
    )


__all__ = ["register_all"]
