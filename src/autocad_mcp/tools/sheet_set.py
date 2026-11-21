"""A drawing list made into sheets in one call (#66, D-90).

The drawing list a coordinator keeps - sheet number, title, scale, which view -
becomes the sheets themselves: a layout per row, its title block filled in
with the number, title and scale, and a viewport at that scale looking at that
view, locked. One call, one undo step, one Keep or Discard.

The list is checked whole before anything is made (``acad/sheets.py``
``plan_sheet_set``): a number used twice or already in the drawing, a scale
nobody can read, a saved view the drawing does not have - all of them are
said at once, and nothing is made. Each sheet is then made with the same code
as autocad_create_layout, autocad_add_viewport and autocad_place_title_block,
so it is the same sheet those tools would make.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import sheets as plan
from ..acad.tables import ensure_layer
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ._shared import COORDS_OPT
from .sheets import (
    PDF_PLOTTER,
    _fill_attributes,
    _layouts,
    _paper_of,
    _pick_layout,
    _references,
    make_layout,
    make_viewport,
    put_title_block,
    title_block_source,
)

DEFAULT_PAPER = "A1"
ROW_KEYS = (
    "number", "title", "scale", "view", "corner1", "corner2", "handles", "centre",
    "twist", "paper_size", "orientation", "attributes",
)  # fmt: skip


def _views_of(doc: Any) -> list[str]:
    return [str(doc.Views.Item(i).Name) for i in range(int(doc.Views.Count))]


@mcp.tool(name="autocad_sheet_set", **tool_meta("Make Sheets From A Drawing List"))
@tool_errors
async def autocad_sheet_set(
    sheets: Annotated[
        list[dict[str, Any]],
        Field(
            min_length=1,
            description=(
                "The drawing list, one row per sheet: {\"number\": \"M-101\" (the layout name), "
                "\"title\": \"GROUND FLOOR HVAC\", \"scale\": \"1:100\" (omit to fit), and where "
                "its viewport looks - \"view\": a saved view (autocad_save_view), or "
                "\"corner1\"/\"corner2\", or \"handles\", or \"centre\" with a scale. A row with "
                "none of those gets a sheet and title block but no viewport (a cover sheet). "
                "Optional per row: \"twist\", \"paper_size\", \"orientation\", \"attributes\" "
                "({tag: value} for that sheet's title block)."
            ),
        ),
    ],
    paper_size: Annotated[
        str | None,
        Field(default=None, description="Sheet size for every row that does not give its own: 'A1', 'A3', 'ANSI D'... Omit for A1, or for the template_layout's own sheet."),
    ] = None,
    orientation: Annotated[Literal["portrait", "landscape"], Field(default="landscape", description="Which way round the sheets go.")] = "landscape",
    plotter: Annotated[
        str | None,
        Field(default=None, description=f"Plotter for every sheet. Omit for '{PDF_PLOTTER}', or for the template_layout's own plotter."),
    ] = None,
    plot_style_table: Annotated[str | None, Field(default=None, description="Plot style table for every sheet, e.g. 'monochrome.ctb'.")] = None,
    template_layout: Annotated[
        str | None,
        Field(default=None, description="An existing sheet to copy for every new one, title block and all. Its title block (named by title_block) is then filled in instead of a second one being placed."),
    ] = None,
    title_block: Annotated[
        str | None,
        Field(default=None, description="The title block: a block in the drawing or the full path to a .dwg. Omit for sheets without one."),
    ] = None,
    title_block_width: Annotated[float | None, Field(default=None, description="Width of the strip on the right the title block takes, kept clear of the viewports.")] = None,
    title_block_layer: Annotated[str | None, Field(default=None, description="Layer for the title blocks, created if missing, e.g. 'G-TTLB'.")] = None,
    number_tag: Annotated[str | None, Field(default="DWG_NO", description="The title block's attribute tag that takes the sheet number. null to leave it.")] = "DWG_NO",
    title_tag: Annotated[str | None, Field(default="TITLE", description="The tag that takes the sheet title. null to leave it.")] = "TITLE",
    scale_tag: Annotated[str | None, Field(default="SCALE", description="The tag that takes the scale (the fitted one when a row gives none). null to leave it.")] = "SCALE",
    attributes: Annotated[dict[str, str] | None, Field(default=None, description='Title block values for every sheet: {"PROJECT": "...", "DATE": "2026-11-21", "REV": "P01"}.')] = None,
    margins: Annotated[list[float] | None, Field(default=None, description="Frame margins as [left, bottom, right, top] or one number. Default ISO 5457's 20 / 10 / 10 / 10.")] = None,
    gap: Annotated[float, Field(default=0.0, ge=0, description="Clearance between the frame and the viewport, in paper units.")] = 0.0,
    viewport_layer: Annotated[str | None, Field(default=None, description="Layer for the viewports, created if missing; a non-plotting one such as 'G-VPRT'.")] = None,
    locked: Annotated[bool, Field(default=True, description="Lock every viewport once it is aimed (the default).")] = True,
    annotation_scale: Annotated[str | None, Field(default="match", description="Each viewport's annotation scale: 'match' its own scale (default), a scale name, or 'none'.")] = "match",
    align_to_ucs: Annotated[bool, Field(default=False, description="Twist every viewport to the current UCS (a row's own twist wins).")] = False,
    coords: Annotated[str, COORDS_OPT] = "world",
    dry_run: Annotated[bool, Field(default=False, description="Check the list and show what would be made - names, scales, views - without making anything.")] = False,
) -> str:
    """Make a whole drawing list into sheets in one call: layouts, filled title blocks and viewports at scale.

    Each row of the list - sheet number, title, scale, view - becomes a layout
    named by its number, set up for plotting (paper, plotter, 1:1), a viewport
    at the row's scale looking at its view and locked, and the title block in
    the corner with the number, title and scale written in. A row without a
    scale gets the largest standard scale that fits, and that is the scale
    written in its title block.

    The whole list is checked before anything is made, and every problem is
    said at once. One undo step for the whole set: one Ctrl+Z, or Discard,
    takes every sheet back.

    Args:
        sheets (list[dict]): the drawing list, one row per sheet.
        paper_size (Optional[str]), orientation (str), plotter (Optional[str]),
            plot_style_table (Optional[str]): the page setup of every sheet
            (A1 on DWG To PDF unless named, or the template's own).
        template_layout (Optional[str]): a sheet to copy for each new one,
            with everything on it (by the plug-in; over COM its page setup).
        title_block (Optional[str]): block name or .dwg path.
        title_block_width (Optional[float]), title_block_layer (Optional[str]).
        number_tag / title_tag / scale_tag (Optional[str]): which attributes
            take the number, title and scale.
        attributes (Optional[dict[str, str]]): values for every sheet.
        margins (Optional[list[float]]), gap (float): how the frame is filled.
        viewport_layer (Optional[str]), locked (bool), annotation_scale
            (Optional[str]), align_to_ucs (bool), coords (str): the viewports.
        dry_run (bool): check and show the plan only.

    Returns:
        str: JSON: {"count": int, "complete": bool, "sheets": [{"number",
             "layout", "title", "scale", "fitted", "viewport": str | null,
             "model_window", "title_block": str | null, "attributes_set",
             "attributes_not_found", "made_by"}], "undo": str,
             "stopped": {...}}  # "stopped" only when a sheet could not be made

    Examples:
        - Use when: "make sheets M-101 to M-112 from this drawing list, A1, our
          title block, each viewport on its saved view at 1:100".
        - Use when: "set up the whole issue package" after the views are saved
          with autocad_save_view.
        - Use when: "check this sheet list first" — dry_run=true.
        - Don't use when: one sheet — autocad_create_layout, then
          autocad_add_viewport and autocad_place_title_block.
        - Don't use when: the sheets exist and only the title block text needs
          changing — autocad_set_attributes.

    Error Handling:
        - A number used twice or already a layout, a scale it cannot read, a
          view the drawing does not have, a title block it cannot find: all
          said at once, and nothing is made.
        - A sheet AutoCAD refuses part-way stops the run: the answer lists the
          sheets made and why it stopped; one Ctrl+Z takes them all back.
    """
    for index, row in enumerate(sheets, start=1):
        if not isinstance(row, dict):
            raise AutocadError(f"Row {index} of the drawing list is not a {{\"number\": ...}} row.")
        extra = sorted(set(row) - set(ROW_KEYS))
        if extra:
            raise AutocadError(
                f"Row {index} has {', '.join(repr(k) for k in extra)}, which a sheet row does not take. "
                f"A row takes: {', '.join(ROW_KEYS)}."
            )
    block_path = None
    block_name = title_block.strip().strip('"') if title_block else None
    if block_name and block_name.lower().endswith(".dwg"):
        from .draw import dwg_path  # the proven path normaliser for InsertBlock

        block_path = dwg_path(block_name)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        wants_views = any(row.get("view") for row in sheets)
        try:
            plans = plan.plan_sheet_set(sheets, list(_layouts(doc)), _views_of(doc) if wants_views else None)
        except ValueError as exc:
            raise AutocadError(str(exc)) from None
        template = _pick_layout(doc, template_layout).Name if template_layout else None
        block = title_block_source(doc, block_name, block_path) if block_name else None

        if dry_run:
            return {
                "dry_run": True,
                "count": len(plans),
                "would_make": [
                    {
                        "number": row["number"], "title": row["title"],
                        "scale": row["scale"] or ("fit" if row["aim"] else None),
                        "looks_at": _aim_text(row),
                        "paper_size": row["paper_size"] or paper_size or ("the template's" if template else DEFAULT_PAPER),
                        "orientation": row["orientation"] or orientation,
                    }
                    for row in plans
                ],
                "title_block": block,
                "template_layout": str(template) if template else None,
                "note": "Nothing was made. Call again without dry_run to make these sheets.",
            }  # fmt: skip

        made: list[dict[str, Any]] = []
        stopped: dict[str, Any] | None = None
        with undo_mark(doc):
            if title_block_layer and block:
                ensure_layer(doc, title_block_layer)
            current_block = block
            for index, row in enumerate(plans, start=1):
                try:
                    entry, current_block = _make_one(doc, row, current_block, template)
                except Exception as exc:  # noqa: BLE001 - the set so far is reported, not lost
                    stopped = {
                        "row": index,
                        "number": row["number"],
                        "error": str(exc) if isinstance(exc, AutocadError) else com_message(exc),
                    }
                    break
                made.append(entry)

        if not made and stopped is not None:
            raise AutocadError(f"No sheet was made: sheet {stopped['number']}: {stopped['error']}")
        result: dict[str, Any] = {
            "count": len(made),
            "complete": stopped is None,
            "sheets": made,
            "undo": "One Ctrl+Z takes back every sheet this call made.",
        }
        if stopped is not None:
            result["stopped"] = stopped
            result["warning"] = (
                f"Made {len(made)} of {len(plans)} sheets, then stopped at {stopped['number']}: "
                f"{stopped['error']} The sheets made are kept; one Ctrl+Z takes them all back, or fix "
                "the row and call again with only the rows not made."
            )
        return result

    def _make_one(doc: Any, row: dict[str, Any], block: str | None, template: Any) -> tuple[dict[str, Any], str | None]:
        number = row["number"]
        # A template keeps its own page setup unless the call names one.
        made = make_layout(
            doc, number, paper_size=row["paper_size"] or paper_size or (None if template else DEFAULT_PAPER),
            orientation=row["orientation"] or orientation,
            plotter=plotter or (None if template else PDF_PLOTTER),
            plot_style_table=plot_style_table, copy_from=str(template) if template else None,
            margins=margins, title_block_width=title_block_width, activate=False,
        )  # fmt: skip
        if made.get("warning"):
            raise AutocadError(made["warning"])
        layout = _pick_layout(doc, made["layout"])
        info = made.get("paper") or _paper_of(layout)
        entry: dict[str, Any] = {
            "number": number,
            "layout": made["layout"],
            "title": row["title"],
            "made_by": made.get("made_by"),
        }

        scale = row["scale"]
        if row["aim"]:
            viewport = make_viewport(
                doc, layout, scale=row["scale"], centre=row["centre"], corner1=row["corner1"],
                corner2=row["corner2"], view_name=row["view"], handles=row["handles"],
                margins=margins, title_block_width=title_block_width, gap=gap,
                twist=row["twist"], align_to_ucs=align_to_ucs, locked=locked,
                layer=viewport_layer, coords=coords, annotation_scale=annotation_scale, info=info,
            )  # fmt: skip
            scale = viewport["scale"]
            entry.update(
                {
                    "scale": scale,
                    "fitted": viewport["fitted"],
                    "viewport": viewport.get("handle"),
                    "model_window": viewport["model_window"],
                }
            )
            for key in ("annotation_scale", "annotation_scale_note", "lock_note", "aim_note", "warning"):
                if viewport.get(key):
                    entry[f"viewport_{key}" if not key.startswith("annotation") else key] = viewport[key]
        else:
            entry.update({"scale": scale, "fitted": False, "viewport": None})

        if block:
            values = plan.title_block_values(row, attributes, number_tag, title_tag, scale_tag, scale)
            existing = _references(layout.Block, block) if template else []
            if existing:
                applied, missing = _fill_attributes(existing[0], {k.upper(): v for k, v in values.items()})
                entry.update({"title_block": str(existing[0].Handle), "title_block_from": "template"})
            else:
                placed = put_title_block(
                    layout, block, title_block or block, corner="bottom-right", anchor="printable",
                    margins=margins, nudge=(0.0, 0.0), scale=1.0, rotation=0.0, values=values,
                    layer=title_block_layer, replace_existing=False, info=info,
                )  # fmt: skip
                applied, missing = placed["attributes_set"], placed["attributes_not_found"]
                entry["title_block"] = placed["handle"]
                # A .dwg is brought in once; the next sheets insert the block it made.
                block = placed.get("block") or block
            entry["attributes_set"] = applied
            entry["attributes_not_found"] = missing
        else:
            entry["title_block"] = None
        return entry, block

    return dumps(await run(work))


def _aim_text(row: dict[str, Any]) -> str:
    """Where a planned sheet's viewport looks, in words for the dry run."""
    if row["aim"] == "view":
        return f"saved view {row['view']}"
    if row["aim"] == "corner1":
        return f"the area {row['corner1']} to {row['corner2']}"
    if row["aim"] == "handles":
        return f"{len(row['handles'])} object(s)"
    if row["aim"] == "centre":
        return f"centred on {row['centre']}"
    return "no viewport"
