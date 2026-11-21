"""autocad_companion: open the Heron Companion page beside AutoCAD (D-71).

The page itself is core/companion.py: one HTML file per chat, rewritten after
every Heron job, no server and no script. This tool reads the drawing, view
and selection once, in its own read job, puts them on the page, and from then
on the gate keeps the page's activity up to date.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from pydantic import Field

from ..acad.units import unit_name
from ..core import companion, gate
from ..core.connection import get_doc, run
from ..core.errors import raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta

MOST_SELECTION = 2000


def _snapshot() -> dict[str, Any]:
    """The drawing, its units, the layout, the view and the selection, read once. Changes nothing."""
    doc = get_doc()

    def ask(read: Any, default: Any = None) -> Any:
        try:
            return read()
        except BaseException as exc:  # noqa: BLE001 - one value the page leaves out
            raise_if_busy(exc)
            return default

    centre = ask(lambda: doc.GetVariable("VIEWCTR"))
    selection = ask(lambda: doc.PickfirstSelectionSet)
    count = int(ask(lambda: selection.Count, 0) or 0) if selection is not None else 0
    types = Counter(
        str(ask(lambda i=i: selection.Item(i).ObjectName, "?")).removeprefix("AcDb") for i in range(min(count, MOST_SELECTION))
    )
    return {
        "drawing": str(ask(lambda: doc.FullName, "") or ask(lambda: doc.Name, "")),
        "units": unit_name(ask(lambda: int(doc.GetVariable("INSUNITS")))),
        "layout": str(ask(lambda: doc.ActiveLayout.Name, "")),
        "view": {
            "centre": [round(float(v), 3) for v in list(centre)[:2]] if centre is not None else None,
            "height": ask(lambda: round(float(doc.GetVariable("VIEWSIZE")), 3)),
        },
        "selection": {"count": count, "types": dict(types.most_common())},
    }


@mcp.tool(name="autocad_companion", **tool_meta("Open The Companion Page", read_only=True))
@tool_errors
async def autocad_companion(
    stop: Annotated[bool, Field(description="True: stop updating the page for this chat (the file stays).")] = False,
) -> str:
    """Open the Heron Companion page: this chat's drawing, view, selection and activity in a browser beside AutoCAD.

    The page is one HTML file on this PC (one per chat). This call reads the
    drawing, its units, the layout, the view and the selection, and puts them
    on it; after that the page's activity list is rewritten after every Heron
    job in this chat, and the page reloads itself every few seconds. It runs
    no script, opens no port and sends nothing to AutoCAD. Call again to read
    the view and selection afresh.

    Returns:
        str: JSON: {"page": path, "open": file URL, "updates": ..., "snapshot": {...}}

    Examples:
        - Use when: "show me what you are doing in a window beside AutoCAD".
        - Use when: "open the companion page" or "refresh the companion page".
        - Don't use when: the modeller wants the list in the chat -
          autocad_activity answers there.
    """
    if stop:
        companion.stop()
        return dumps({"stopped": True, "page": str(companion.page_path(gate.companion_state()["conversation"])),
                      "note": "The page is no longer updated for this chat; the file stays as it was."})  # fmt: skip
    snapshot = await run(_snapshot)
    companion.start(snapshot)
    path = companion.write(gate.companion_state())
    if path is None:
        return dumps({"page": None, "snapshot": snapshot,
                      "note": f"The page could not be written in {companion.folder()}. Check that folder can be written."})  # fmt: skip
    return dumps({
        "page": str(path),
        "open": path.resolve().as_uri(),
        "updates": "After every Heron job in this chat; the page reloads itself every few seconds.",
        "snapshot": snapshot,
        "tell_the_modeller": f"Open {path} in a browser and keep it beside AutoCAD.",
    })
