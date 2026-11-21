"""Hyperlinks on objects (Insert > Hyperlink, HYPERLINK): set, remove, list (D-111).

A hyperlink ties an object to a web page, a file (a data sheet, a product
PDF, another drawing) or a named view, and Ctrl+click opens it in AutoCAD.
COM has each object's Hyperlinks collection. AutoCAD keeps the link in the
object's extended data under the application name PE_URL, which is how the
listing finds every linked object in one selection.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from ..acad.entities import resolve_handle, short_type
from ..acad.selection import discard_selection_set, iter_selection, make_selection_set
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import int_array, variant_array
from ._shared import HANDLES_OPT

# Where AutoCAD keeps a hyperlink: extended data of this application.
XDATA_APP = "PE_URL"
DXF_XDATA_APP = 1001
SELECT_ALL = 5  # acSelectionSetAll
MOST_LISTED = 500


def _links(entity: Any) -> list[dict[str, str]]:
    links = entity.Hyperlinks
    found = []
    for index in range(int(links.Count)):
        link = links.Item(index)
        found.append(
            {
                "url": str(link.URL or ""),
                "description": str(link.URLDescription or ""),
                "location": str(link.URLNamedLocation or ""),
            }
        )
    return found


def _clear(entity: Any) -> int:
    links = entity.Hyperlinks
    removed = 0
    # From the end, so the indexes left are still right.
    for index in range(int(links.Count) - 1, -1, -1):
        links.Item(index).Delete()
        removed += 1
    return removed


def _restore(entity: Any, links: list[dict[str, str]]) -> bool:
    """Put an object's links back as they were, after a set that failed half way; True when they are."""
    try:
        _clear(entity)
        for link in links:
            entity.Hyperlinks.Add(link["url"], link["description"], link["location"])
        return _links(entity) == links
    except BaseException as exc:  # noqa: BLE001 - the caller says it could not, and Ctrl+Z can
        raise_if_busy(exc)
        return False


@mcp.tool(name="autocad_hyperlinks", **tool_meta("Hyperlink Objects To A File, Data Sheet Or Web Page"))
@tool_errors
async def autocad_hyperlinks(
    handles: Annotated[list[str], HANDLES_OPT],
    action: Annotated[
        str,
        Field(default="set", description="'set' puts the link on each object (replacing any link it had); 'remove' takes links off.", pattern="^(set|remove)$"),
    ] = "set",
    url: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "What the link opens: a web address ('https://...'), a file ('C:\\\\Data\\\\AHU-01.pdf' or a "
                "drawing), or '' with a location for a view in this drawing. Needed for 'set' unless a location is given."
            ),
        ),
    ] = None,
    description: Annotated[
        str | None,
        Field(default=None, description="Text AutoCAD shows when the cursor is over the object, e.g. 'AHU-01 data sheet'."),
    ] = None,
    location: Annotated[
        str | None,
        Field(default=None, description="A named view or layout to open at, inside the drawing or file the link opens."),
    ] = None,
) -> str:
    """Link objects to a file, a data sheet or a web page with a hyperlink, or take the link off (HYPERLINK).

    In AutoCAD, Ctrl+click on the object opens the link: a supplier's data
    sheet on a piece of equipment, the O&M manual, a detail drawing, a web page.
    One link per object, as AutoCAD's own HYPERLINK command keeps: 'set'
    replaces the link an object had. The answer gives each object's link
    before and after.

    One undo step.

    Args:
        handles (list[str]): the objects.
        action (str): 'set' or 'remove'.
        url (Optional[str]): what the link opens.
        description (Optional[str]): the text shown on hover.
        location (Optional[str]): a named view or layout inside what it opens.

    Returns:
        str: JSON: {"action": str, "changed": int, "handles": [str],
             "objects": [{"handle", "type", "before": [link], "after": [link]}],
             "failed"?: [{"handle", "reason"}]}

    Examples:
        - Use when: "link the AHU block to its data sheet" — handles=[the
          block], url='C:\\\\Project\\\\Submittals\\\\AHU-01.pdf',
          description='AHU-01 data sheet'.
        - Use when: "put the manufacturer's web page on all the fan coil
          units" — the FCU handles, url='https://...'.
        - Use when: "take the old links off these" — action='remove'.
        - Don't use when: you only want to see the links — autocad_list_hyperlinks.
        - Don't use when: the text should show on the drawing — autocad_add_label.

    Error Handling:
        - 'set' with neither a url nor a location is refused before anything changes.
        - An object that refuses (a locked layer) is listed under "failed";
          the rest are still done.
    """
    target = (url or "").strip()
    place = (location or "").strip()
    if action == "set" and not target and not place:
        raise AutocadError("Give the url (a web address or a file) or a location (a named view) for the link.")
    if action == "remove" and (url or description or location):
        raise AutocadError("'remove' takes the links off; leave url, description and location out.")
    wanted = list(dict.fromkeys(handles))

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        rows: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []
        with undo_mark(doc):
            for handle in wanted:
                entity = resolve_handle(doc, handle)
                try:
                    before = _links(entity)
                except BaseException as exc:  # noqa: BLE001 - report it, go on with the rest
                    raise_if_busy(exc)
                    failed.append({"handle": handle, "reason": com_message(exc)})
                    continue
                try:
                    _clear(entity)
                    if action == "set":
                        entity.Hyperlinks.Add(target, (description or "").strip(), place)
                    after = _links(entity)
                except BaseException as exc:  # noqa: BLE001 - report it, put the old link back, go on
                    raise_if_busy(exc)
                    reason = com_message(exc)
                    if not _restore(entity, before):
                        reason += " Its old link could not be put back: one Ctrl+Z does."
                    failed.append({"handle": handle, "reason": reason})
                    continue
                rows.append({"handle": handle, "type": short_type(entity), "before": before, "after": after})
        changed = [row for row in rows if row["before"] != row["after"]]
        result: dict[str, Any] = {
            "action": action,
            "changed": len(changed),
            "handles": [row["handle"] for row in rows],
            "objects": rows,
        }
        if failed:
            result["failed"] = failed
            result["hint"] = "An object refuses a link when its layer is locked. Unlock it with autocad_set_layer_state."
        if action == "set" and rows:
            result["note"] = "In AutoCAD, Ctrl+click the object to open the link."
        return result

    return dumps(await run(work))


@mcp.tool(name="autocad_list_hyperlinks", **tool_meta("List Hyperlinks On Objects", read_only=True))
@tool_errors
async def autocad_list_hyperlinks(
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="Objects to read. Omit to find every object in the drawing that has a link."),
    ] = None,
    limit: Annotated[int, Field(default=200, ge=1, le=MOST_LISTED, description="Most objects to list.")] = 200,
) -> str:
    """List the hyperlinks on objects: on the ones given, or on every linked object in the drawing.

    Each object's handle, type and layer, with its link: the address or file
    it opens, the hover text and the named view. Use it to check the links
    before an issue, or to find which equipment still has no data sheet.

    Reads only.

    Args:
        handles (Optional[list[str]]): the objects; omit for the whole drawing.
        limit (int): most objects to list.

    Returns:
        str: JSON: {"count": int, "objects": [{"handle", "type", "layer",
             "links": [{"url", "description", "location"}]}], "truncated"?: bool}

    Examples:
        - Use when: "which objects have hyperlinks in this drawing?" — no handles.
        - Use when: "what does this fan link to?" — handles=[the fan].
        - Don't use when: you want to add or remove one — autocad_hyperlinks.

    Error Handling:
        - A handle that is not in the drawing points at autocad_list_entities.
        - The whole-drawing search covers model space and every layout, not
          objects nested inside other objects.
    """
    wanted = list(dict.fromkeys(handles or []))

    def row(entity: Any) -> dict[str, Any]:
        return {
            "handle": str(entity.Handle),
            "type": short_type(entity),
            "layer": str(entity.Layer),
            "links": _links(entity),
        }

    def work() -> dict[str, Any]:
        doc = get_doc()
        rows: list[dict[str, Any]] = []
        total = 0
        if wanted:
            for handle in wanted:
                total += 1
                if len(rows) < limit:
                    rows.append(row(resolve_handle(doc, handle)))
        else:
            sel = make_selection_set(doc)
            try:
                try:
                    sel.Select(SELECT_ALL, None, None, int_array([DXF_XDATA_APP]), variant_array([XDATA_APP]))
                except BaseException as exc:  # noqa: BLE001 - say why, do not guess
                    raise_if_busy(exc)
                    raise AutocadError(
                        f"AutoCAD would not search the drawing for linked objects ({com_message(exc)}). "
                        "Give the handles to read instead."
                    ) from exc
                for entity in iter_selection(sel):
                    found = row(entity)
                    if not found["links"]:
                        continue
                    total += 1
                    if len(rows) < limit:
                        rows.append(found)
            finally:
                discard_selection_set(doc)
        result: dict[str, Any] = {"count": total, "objects": rows}
        if total > len(rows):
            result["truncated"] = True
            result["note"] = f"Showing {len(rows)} of {total}. Raise 'limit', or ask about fewer objects."
        return result

    return dumps(await run(work))
