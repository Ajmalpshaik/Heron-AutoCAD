"""Annotation that needs more than one object: multileaders, tables, clouds.

Three jobs that each used to be a dozen calls:

* **A multileader with several arrows.** One note, three things it points at.
  ``autocad_add_label`` makes one leader; this makes the real thing, with as
  many leader lines as you give it.
* **A schedule as an AutoCAD table.** ``autocad_extract_attributes`` reads the
  blocks and hands back rows; this puts those rows on the sheet as a table the
  modeller can edit, not as a grid of loose text.
* **A revision cloud.** AutoCAD's own REVCLOUD makes a polyline with bulges,
  and so does this - one object, arcs bulging outward, round any boundary you
  give it or round an object you already have.

The cloud's geometry is a pure function over plain numbers and is tested
without AutoCAD.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any

from pydantic import Field, StrictInt

from ..acad import geometry
from ..acad.entities import bounding_box, resolve_handle, short_type
from ..acad.table_cells import middle_rows
from ..acad.tables import apply_properties, ensure_layer
from ..core.connection import get_doc, get_space, require_idle, run
from ..core.errors import AutocadError, com_message, raise_if_busy
from ..core.registry import dumps, mcp, to_aci, tool_errors, tool_meta, undo_mark
from ..core.variants import double_array
from ._shared import COLOR_OPT, COORDS_OPT, LAYER_OPT, point, ucs_for, world_coords
from .annotation_scales import ANNOTATIVE_OPT, make_new_annotative, require_plugin
from .batch import draw_operations

Point = tuple[float, float]
EPS = 1e-9

# AcMLeaderContentType: 0 none, 1 block, 2 mtext, 3 tolerance.
AC_MTEXT_CONTENT = 2
AC_BLOCK_CONTENT = 1
# A revision cloud's arcs: bulge 0.5 puts the arc's rise at a quarter of its
# chord, which is what AutoCAD's own REVCLOUD looks like.
CLOUD_BULGE = 0.5
MAX_CLOUD_ARCS = 2000


# ---------------------------------------------------------------------------
# The revision cloud (pure: no AutoCAD below this line)
# ---------------------------------------------------------------------------


def resample(
    vertices: Sequence[Sequence[float]], step: float, closed: bool = True
) -> list[Point]:
    """Points evenly spaced along a path, so every cloud arc comes out the same size.

    The spacing is adjusted to divide the path exactly, which is what stops the
    last arc of a cloud being a stub.
    """
    if len(vertices) < 2:
        raise ValueError("a path needs at least two points")
    if step <= 0.0:
        raise ValueError(f"the arc length must be above zero, got {step:g}")
    segs = geometry.segments(vertices, [0.0] * (len(vertices) + 1), closed)
    total = sum(s.length for s in segs)
    if total < EPS:
        raise ValueError("that path has no length")
    count = max(3 if closed else 1, round(total / step))
    if count > MAX_CLOUD_ARCS:
        raise ValueError(
            f"{count} arcs at {step:g} apart is more than one cloud takes "
            f"({MAX_CLOUD_ARCS}). Use a longer arc length."
        )
    spacing = total / count
    stops = count if closed else count + 1
    out: list[Point] = []
    for i in range(stops):
        x, y, _ = geometry.point_at(segs, min(i * spacing, total))
        out.append((x, y))
    return out


def signed_area(points: Sequence[Point]) -> float:
    """Twice the signed area: positive when the points run anticlockwise."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, list(points[1:]) + [points[0]], strict=False):
        total += x1 * y2 - x2 * y1
    return total


def revision_cloud(
    vertices: Sequence[Sequence[float]],
    arc_length: float,
    closed: bool = True,
    layer: str | None = None,
    color: Any = None,
) -> list[dict[str, Any]]:
    """A revision cloud round a boundary, as one polyline with bulges.

    The arcs bulge **outward**: the direction the boundary is traced decides
    which way that is, so the traced direction is measured and the bulge signed
    to match. Returns one operation in ``autocad_batch_draw``'s shape.
    """
    pts = resample(vertices, arc_length, closed)
    if len(pts) < 2:
        raise ValueError("that boundary is too small for even one arc")
    # Anticlockwise: an arc bulging outward sweeps clockwise, so its bulge is
    # negative. Clockwise: the other way round.
    outward = -CLOUD_BULGE if signed_area(pts) > 0 else CLOUD_BULGE
    op: dict[str, Any] = {
        "type": "polyline",
        "points": [[round(x, 9), round(y, 9)] for x, y in pts],
        "bulges": [outward] * len(pts),
    }
    if closed:
        op["closed"] = True
    if layer:
        op["layer"] = layer
    if color is not None:
        op["color"] = color
    return [op]


def box_outline(box: Sequence[float], grow: float = 0.0) -> list[Point]:
    """A box as four corners, anticlockwise, optionally pushed out all round."""
    x1, y1, x2, y2 = (float(v) for v in box)
    x1, y1, x2, y2 = x1 - grow, y1 - grow, x2 + grow, y2 + grow
    if x2 - x1 < EPS or y2 - y1 < EPS:
        raise ValueError("that box has no size")
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


# ---------------------------------------------------------------------------
# Multileaders
# ---------------------------------------------------------------------------


def _flat3(points: Sequence[Point]) -> list[float]:
    return [c for x, y in points for c in (float(x), float(y), 0.0)]


@mcp.tool(name="autocad_add_multileader", **tool_meta("Add A Multileader"))
@tool_errors
async def autocad_add_multileader(
    landing: Annotated[
        list[float],
        Field(description="Where the note sits, as [x, y]: the end of the first leader line."),
    ],
    arrows: Annotated[
        list[list[float]],
        Field(
            min_length=1,
            description=(
                "Every point the note points at, each [x, y]. Give one for a plain "
                "leader, or several for one note serving several things — which is what "
                "a multileader is for."
            ),
        ),
    ],
    text: Annotated[
        str | None,
        Field(default=None, description="The note. Use \\P for a new line. Leave out and give 'block' instead for a block-content leader (a tag, a detail bubble)."),
    ] = None,
    block: Annotated[
        str | None,
        Field(default=None, description="Instead of text: a block already in the drawing to carry at the end of the leader."),
    ] = None,
    height: Annotated[
        float | None,
        Field(default=None, gt=0, description="Text height in drawing units. Omit to keep the multileader style's own."),
    ] = None,
    arrow_size: Annotated[
        float | None,
        Field(default=None, gt=0, description="Arrowhead size. Omit to keep the style's own."),
    ] = None,
    style: Annotated[
        str | None,
        Field(default=None, description="Multileader style name, already in the drawing: make one with autocad_create_styles(multileader_styles=...), or bring yours in with autocad_import_from_drawing."),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    coords: Annotated[str, COORDS_OPT] = "world",
    annotative: Annotated[bool, ANNOTATIVE_OPT] = False,
) -> str:
    """One note with as many arrows as it needs: a real MULTILEADER.

    Use it when a single note serves several things — "4 No. M16 BOLTS" with an
    arrow to each of four holes — or for one tidy leader that follows the
    office multileader style.

    The first arrow point and the landing make the first leader line; every
    extra arrow point adds another leader line to the same note.

    One undo step. For Ajmal's own TLD label style (MTEXT plus a leader ending
    under the text), use autocad_add_label instead.

    Args:
        landing (list[float]): where the note sits.
        arrows (list[list[float]]): every point it points at.
        text (Optional[str]): the note.
        block (Optional[str]): a block to carry instead of text.
        height (Optional[float]): text height.
        arrow_size (Optional[float]): arrowhead size.
        style (Optional[str]): multileader style, already in the drawing.
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour.
        coords (str): 'world' or 'ucs'.
        annotative (bool): make it annotative at the current annotation scale.

    Returns:
        str: JSON: {"created": true, "handle": str, "leader_lines": int,
             "arrows": [[x, y]], "landing": [x, y], "not_set": [str]}
             With annotative: also "annotative" and "annotation_scales".

    Examples:
        - Use when: "label these four holes with one note".
        - Use when: "tag this pipe with our tag block on a leader" — block=.
        - Don't use when: one label in the TLD house style (autocad_add_label),
          or a dimension (autocad_add_dimension).

    Error Handling:
        - Needs text or block, and says so if neither is given.
        - A style or block the drawing does not have is named; the leader is not
          left half-made.
        - Properties a locked style refuses come back in "not_set" rather than
          failing the call.
    """
    if not text and not block:
        raise AutocadError("Give 'text' for a note, or 'block' for a block-content leader.")
    if text and block:
        raise AutocadError("Give either 'text' or 'block', not both.")
    if len(landing) < 2:
        raise AutocadError("landing needs [x, y].")
    aci = to_aci(color)
    if annotative:
        require_plugin("Making a multileader annotative")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        target = get_space(doc, "model")

        if block:
            try:
                doc.Blocks.Item(str(block).strip())
            except BaseException as exc:  # noqa: BLE001 - name it rather than half-make a leader
                raise_if_busy(exc)
                raise AutocadError(
                    f"No block named '{block}' is in this drawing. autocad_list_blocks shows "
                    "what there is, and autocad_insert_block can bring one in from a .dwg."
                ) from None

        land = tuple(world_coords(landing, ucs)[:2])
        points = [tuple(world_coords(a, ucs)[:2]) for a in arrows]
        not_set: list[str] = []

        with undo_mark(doc):
            # The first arrow and the landing make the first leader line; COM
            # hands back the new leader-line index alongside the object.
            made = target.AddMLeader(double_array(_flat3([points[0], land])), 0)
            mleader = made[0] if isinstance(made, tuple) else made

            if style:
                try:
                    mleader.StyleName = str(style).strip()
                except BaseException as exc:  # noqa: BLE001
                    raise_if_busy(exc)
                    raise AutocadError(
                        f"This drawing has no multileader style called '{style}' "
                        f"({com_message(exc)}). Make it with autocad_create_styles(multileader_styles=...), "
                        "or copy it in with autocad_import_from_drawing."
                    ) from exc

            if block:
                mleader.ContentType = AC_BLOCK_CONTENT
                try:
                    mleader.ContentBlockName = str(block).strip()
                except BaseException as exc:  # noqa: BLE001 - reported, the leader still exists
                    raise_if_busy(exc)
                    not_set.append("ContentBlockName")
            else:
                mleader.ContentType = AC_MTEXT_CONTENT
                mleader.TextString = text

            notes = apply_properties(doc, mleader, layer, aci, None)

            for prop, value in (("TextHeight", height), ("ArrowheadSize", arrow_size),
                                ("DoglegLength", height)):
                if value is None:
                    continue
                try:
                    setattr(mleader, prop, float(value))
                except BaseException as exc:  # noqa: BLE001 - a locked style keeps its own
                    raise_if_busy(exc)
                    not_set.append(prop)

            # Every further arrow is another leader line on the same note.
            extra = 0
            for arrow in points[1:]:
                try:
                    cluster = mleader.AddLeader()
                    mleader.AddLeaderLine(cluster, double_array(_flat3([arrow, land])))
                    extra += 1
                except BaseException as exc:  # noqa: BLE001 - report, keep what worked
                    raise_if_busy(exc)
                    not_set.append(f"leader line to {list(arrow)} ({com_message(exc)})")
            scaled = make_new_annotative([str(mleader.Handle)]) if annotative else {}

        result: dict[str, Any] = {
            "created": True,
            "handle": str(mleader.Handle),
            "type": "mleader",
            "leader_lines": 1 + extra,
            "arrows": [[round(p[0], 6), round(p[1], 6)] for p in points],
            "landing": [round(land[0], 6), round(land[1], 6)],
            "content": "block" if block else "text",
        }
        result.update(notes)
        result.update(scaled)
        if not_set:
            result["not_set"] = not_set
        return result

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

# AcRowType: acDataRow 1 + acTitleRow 2 + acHeaderRow 4. An AcadTable sets text
# height and style per row type with SetTextHeight / SetTextStyle; it has no
# TitleTextHeight-style properties (AutoCAD 2027 refused them, 2026-10-28).
TABLE_ALL_ROWS = 1 + 2 + 4


@mcp.tool(name="autocad_add_table", **tool_meta("Add A Table"))
@tool_errors
async def autocad_add_table(
    position: Annotated[
        list[float],
        Field(description="Top-left corner of the table, as [x, y]. A table grows downward from here."),
    ],
    rows: Annotated[
        list[list[str]],
        Field(
            min_length=1,
            description=(
                'The data rows, e.g. [["CAM-01","Dome","Level 1"],["CAM-02","Bullet","Level 1"]]. '
                "Every row is padded to the widest one, so a short row is not an error. "
                "autocad_extract_attributes hands back rows in this shape."
            ),
        ),
    ],
    headers: Annotated[
        list[str] | None,
        Field(default=None, description='Column headings, e.g. ["TAG","TYPE","LOCATION"]. They go in the table\'s header row.'),
    ] = None,
    title: Annotated[
        str | None,
        Field(default=None, description='A title across the top, e.g. "CAMERA SCHEDULE".'),
    ] = None,
    column_widths: Annotated[
        list[float] | None,
        Field(default=None, description="Width of each column in drawing units. One number is used for all of them. Omit for a sensible default from the text height."),
    ] = None,
    row_height: Annotated[
        float | None,
        Field(default=None, gt=0, description="Row height in drawing units. Must be at least the text height plus the style's cell margins, or AutoCAD grows it anyway."),
    ] = None,
    text_height: Annotated[
        float | None,
        Field(default=None, gt=0, description="Text height in drawing units. Omit to keep the table style's own."),
    ] = None,
    text_style: Annotated[
        str | None,
        Field(default=None, description="Text style for the title, headings and data, already in the drawing, e.g. 'ROMANS'. Omit to keep the table style's own."),
    ] = None,
    style: Annotated[
        str | None,
        Field(default=None, description="Table style name, already in the drawing: make one with autocad_create_styles(table_styles=...), or copy yours in with autocad_import_from_drawing."),
    ] = None,
    layer: Annotated[str | None, LAYER_OPT] = None,
    space: Annotated[str, Field(default="model", description="'model' or 'paper'. A schedule normally belongs on the sheet, so 'paper'.", pattern="^(model|paper)$")] = "model",
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Put a schedule on the drawing as a real AutoCAD table, not a grid of loose text.

    A table the modeller can edit, sort and restyle, with a title and headings.
    Text sits in the vertical middle of each cell, keeping the style's left /
    centre / right. Pair it with autocad_extract_attributes: read the blocks, then put the rows
    on the sheet.

    One undo step.

    Args:
        position (list[float]): top-left corner.
        rows (list[list[str]]): the data rows.
        headers (Optional[list[str]]): column headings.
        title (Optional[str]): a title across the top.
        column_widths (Optional[list[float]]): per column, or one for all.
        row_height (Optional[float]): row height.
        text_height (Optional[float]): text height, on every row.
        text_style (Optional[str]): text style, on every row.
        style (Optional[str]): table style, already in the drawing.
        layer (Optional[str]): target layer, created if missing.
        space (str): 'model' or 'paper'.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": true, "handle": str, "rows": int, "columns": int,
             "data_rows": int, "cells_written": int, "not_set": [str]}

    Examples:
        - Use when: "make a camera schedule from the CAM blocks" —
          autocad_extract_attributes, then this.
        - Use when: "put this door schedule on the sheet".
        - Don't use when: you want the data back as text or CSV
          (autocad_extract_attributes already does that).

    Error Handling:
        - A table style the drawing does not have is named.
        - Cells AutoCAD refuses are counted and the row and column are reported;
          the table itself still lands.
        - A text height or text style AutoCAD refuses is in "not_set" with
          its reason; the table keeps its style's own.
    """
    if len(position) < 2:
        raise AutocadError("position needs [x, y].")
    data = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    columns = max(len(row) for row in data)
    if headers:
        columns = max(columns, len(headers))
    if columns < 1:
        raise AutocadError("That gives a table with no columns. Give at least one value in a row.")
    data = [row + [""] * (columns - len(row)) for row in data]
    head = (list(headers) + [""] * (columns - len(headers))) if headers else None

    # AutoCAD's table rows: the title first when there is one, then the header
    # row when there is one, then the data.
    title_rows = 1 if title else 0
    header_rows = 1 if head else 0
    total_rows = title_rows + header_rows + len(data)

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        target = get_space(doc, space)

        height = float(text_height) if text_height else None
        # A row has to clear the text plus the cell margins, so a default row
        # height of 2x the text height is the smallest that reliably fits.
        row_h = float(row_height) if row_height else (height * 2.0 if height else 10.0)
        if column_widths:
            widths = [float(w) for w in column_widths]
            if len(widths) == 1:
                widths = widths * columns
            if len(widths) < columns:
                widths = widths + [widths[-1]] * (columns - len(widths))
        else:
            widths = [(height * 12.0 if height else 60.0)] * columns

        not_set: list[str] = []
        written = 0

        with undo_mark(doc):
            if layer:
                ensure_layer(doc, layer)
            try:
                table = target.AddTable(
                    point(position, "position", ucs), total_rows, columns, row_h, widths[0]
                )
            except BaseException as exc:  # noqa: BLE001
                raise_if_busy(exc)
                raise AutocadError(
                    f"AutoCAD would not add the table ({com_message(exc)}). Check the row "
                    "height clears the text height plus the cell margins in the table style."
                ) from exc

            if style:
                try:
                    table.StyleName = str(style).strip()
                except BaseException as exc:  # noqa: BLE001
                    raise_if_busy(exc)
                    raise AutocadError(
                        f"This drawing has no table style called '{style}' ({com_message(exc)}). "
                        "Make it with autocad_create_styles(table_styles=...), or copy it in with "
                        "autocad_import_from_drawing."
                    ) from exc

            # A new table starts with a title row (merged across) and a header
            # row. With no title (or no headings) asked for, those rows would
            # hold the rows below as one merged cell: they become ordinary rows
            # (D-83). A table that refuses keeps them, as before.
            suppressed = []
            for flag, wanted in (("TitleSuppressed", bool(title)), ("HeaderSuppressed", bool(head))):
                if not wanted:
                    try:
                        setattr(table, flag, True)
                        suppressed.append(flag)
                    except BaseException as exc:  # noqa: BLE001 - the style's own rows stay
                        raise_if_busy(exc)

            for index, width in enumerate(widths):
                try:
                    table.SetColumnWidth(index, width)
                except BaseException as exc:  # noqa: BLE001 - the column keeps the default width
                    raise_if_busy(exc)
                    not_set.append(f"width of column {index}")

            if height or text_style:
                try:
                    table.RegenerateTableSuppressed = True
                except BaseException as exc:  # noqa: BLE001 - only a speed-up
                    raise_if_busy(exc)

            def put(row: int, column: int, value: str) -> None:
                nonlocal written
                try:
                    table.SetText(row, column, value)
                    written += 1
                except BaseException as exc:  # noqa: BLE001 - one cell, not the table
                    raise_if_busy(exc)
                    not_set.append(f"cell {row},{column}")

            at = 0
            if title:
                put(at, 0, str(title))
                at += 1
            if head:
                for column, value in enumerate(head):
                    put(at, column, value)
                at += 1
            for row in data:
                for column, value in enumerate(row):
                    put(at, column, value)
                at += 1

            if text_style:
                try:
                    table.SetTextStyle(TABLE_ALL_ROWS, str(text_style).strip())
                except BaseException as exc:  # noqa: BLE001 - the style keeps its own
                    raise_if_busy(exc)
                    not_set.append(f"text_style ({com_message(exc)})")
            if height:
                try:
                    table.SetTextHeight(TABLE_ALL_ROWS, height)
                except BaseException as exc:  # noqa: BLE001 - the style keeps its own
                    raise_if_busy(exc)
                    not_set.append(f"text_height ({com_message(exc)})")
            # Heron's tables keep their text in the vertical middle of each cell (D-83).
            aligned = middle_rows(table)
            if height or text_style:
                try:
                    table.RegenerateTableSuppressed = False
                except BaseException:  # noqa: BLE001
                    pass

            notes = apply_properties(doc, table, layer, None, None)

        result: dict[str, Any] = {
            "created": True,
            "handle": str(table.Handle),
            "type": "table",
            "rows": total_rows,
            "columns": columns,
            "data_rows": len(data),
            "cells_written": written,
            "has_title": bool(title),
            "has_header": bool(head),
            "rows_aligned_middle": aligned,
        }
        if suppressed:
            result["suppressed"] = suppressed
        result.update(notes)
        if not_set:
            result["not_set"] = not_set[:30]
        return result

    return dumps(await run(work))


# ---------------------------------------------------------------------------
# Revision clouds
# ---------------------------------------------------------------------------


@mcp.tool(name="autocad_add_revision_cloud", **tool_meta("Add A Revision Cloud"))
@tool_errors
async def autocad_add_revision_cloud(
    points: Annotated[
        list[list[float]] | None,
        Field(default=None, description="The boundary to cloud, each [x, y]. At least three for a closed cloud."),
    ] = None,
    corner1: Annotated[
        list[float] | None,
        Field(default=None, description="Instead of points: one corner of a rectangle to cloud."),
    ] = None,
    corner2: Annotated[
        list[float] | None,
        Field(default=None, description="The opposite corner."),
    ] = None,
    handle: Annotated[
        str | None,
        Field(default=None, description="Instead of either: cloud round what this object occupies — the usual way, when the revision is 'that detail there'."),
    ] = None,
    handles: Annotated[
        list[str] | None,
        Field(default=None, description="Or round everything these objects occupy, as one cloud."),
    ] = None,
    arc_length: Annotated[
        float | None,
        Field(default=None, gt=0, description="Roughly how long each arc is, in drawing units. Omit and a fifteenth of the boundary is used, which reads well at any size."),
    ] = None,
    margin: Annotated[
        float,
        Field(default=0.0, ge=0, description="Push the cloud out clear of the objects by this much, so it does not sit on the linework."),
    ] = 0.0,
    closed: Annotated[
        bool,
        Field(default=True, description="Close the cloud. Turn off to cloud along an open line, for a revision that runs off the sheet."),
    ] = True,
    layer: Annotated[str | None, LAYER_OPT] = None,
    color: Annotated[str | StrictInt | None, COLOR_OPT] = None,
    dry_run: Annotated[bool, Field(default=False, description="Report the cloud it would draw and draw nothing.")] = False,
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Draw a revision cloud, as one polyline with its arcs bulging outward.

    Say what to cloud: a boundary, a rectangle, or an object — clouding round
    an object's own extents is what a revision usually means. The arcs come out
    an even size because the spacing is adjusted to divide the boundary exactly,
    so the last arc is never a stub.

    Same object AutoCAD's own REVCLOUD makes: a polyline with bulges, so it
    selects, moves and plots as one thing. One undo step.

    Args:
        points (Optional[list[list[float]]]): the boundary.
        corner1 / corner2 (Optional[list[float]]): a rectangle to cloud.
        handle / handles (Optional[str] | Optional[list[str]]): objects to cloud round.
        arc_length (Optional[float]): roughly how long each arc is.
        margin (float): clearance from the objects.
        closed (bool): close the cloud (default true).
        layer (Optional[str]): target layer, created if missing.
        color (Optional[str | int]): colour — a cloud is usually red.
        dry_run (bool): report only.
        coords (str): 'world' or 'ucs'.

    Returns:
        str: JSON: {"created": int, "handles": [str], "arcs": int,
             "boundary": [[x, y]], "arc_length": float, "from": str}

    Examples:
        - Use when: "cloud this detail, revision B" — handle=, margin about
          5 mm of paper, colour red.
        - Use when: "cloud the area I just changed" — corner1/corner2.
        - Don't use when: you want the revision note too — add that with
          autocad_add_multileader or the 'revision_tag' shape.

    Error Handling:
        - Says so when the thing named reports no extents to cloud round.
        - An arc length that would need thousands of arcs is refused with the
          count, rather than filling the drawing.
    """
    given = [points is not None, bool(corner1 or corner2), handle is not None, handles is not None]
    if sum(1 for g in given if g) != 1:
        raise AutocadError(
            "Give exactly one of: points, corner1 and corner2, handle, or handles."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        ucs = ucs_for(doc, coords)
        source = ""

        if points is not None:
            if len(points) < (3 if closed else 2):
                raise AutocadError(
                    f"a {'closed' if closed else 'open'} cloud needs at least "
                    f"{3 if closed else 2} points, got {len(points)}"
                )
            boundary = [tuple(world_coords(p, ucs)[:2]) for p in points]
            source = "the points given"
        elif corner1 or corner2:
            if not (corner1 and corner2):
                raise AutocadError("A rectangle needs both corner1 and corner2.")
            a = world_coords(corner1, ucs)
            b = world_coords(corner2, ucs)
            box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
            boundary = box_outline(box, margin)
            source = "a rectangle"
        else:
            wanted = [handle] if handle else list(handles or [])
            boxes, blind = [], []
            for h in wanted:
                entity = resolve_handle(doc, h)
                found = bounding_box(entity)
                if found:
                    boxes.append(found)
                else:
                    blind.append(f"{h} ({short_type(entity)})")
            if not boxes:
                raise AutocadError(
                    "Nothing to cloud round: these report no extents — "
                    + ", ".join(blind)
                    + ". Give points, or corner1 and corner2."
                )
            box = (
                min(b["min"][0] for b in boxes),
                min(b["min"][1] for b in boxes),
                max(b["max"][0] for b in boxes),
                max(b["max"][1] for b in boxes),
            )
            boundary = box_outline(box, margin)
            source = f"{len(boxes)} object(s)"

        # A fifteenth of the way round reads well on an A1 and on an A4 alike.
        segments = geometry.segments(boundary, [0.0] * (len(boundary) + 1), closed)
        perimeter = sum(s.length for s in segments)
        step = float(arc_length) if arc_length else max(perimeter / 15.0, EPS)
        try:
            operations = revision_cloud(boundary, step, closed, layer, to_aci(color))
        except ValueError as exc:
            raise AutocadError(str(exc)) from exc
        return {
            "operations": operations,
            "boundary": [[round(x, 6), round(y, 6)] for x, y in boundary],
            "arc_length": round(step, 6),
            "perimeter": round(perimeter, 6),
            "from": source,
        }

    prepared = await run(work)
    arcs = len(prepared["operations"][0]["points"])
    head = {
        "arcs": arcs,
        "arc_length": prepared["arc_length"],
        "perimeter": prepared["perimeter"],
        "boundary": prepared["boundary"],
        "from": prepared["from"],
        "closed": closed,
    }
    if dry_run:
        return dumps({**head, "dry_run": True,
                      "hint": "Nothing was drawn. Call again with dry_run=false."})

    result = await draw_operations(prepared["operations"], return_handles=True, coords="world")
    result.update(head)
    return dumps(result)
