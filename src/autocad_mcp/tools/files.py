"""Reading a DXF or DWG file on disk with AutoCAD closed (#71, D-92).

One Read tool, autocad_read_file. It looks at a file, never at AutoCAD, so it
answers with AutoCAD closed or not connected: the gate lets it through without
asking the plug-in (core/gate.py NO_AUTOCAD_TOOLS), as it does autocad_why.
It is still gated and audited like every call, and it is a Read tool, so a
--read-only server offers it too. The reading itself is acad/dxf_file.py.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import dxf_file
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from .standards import rows_to_csv

What = Literal["summary", "layers", "blocks", "text", "attributes", "styles"]


def _capped(rows: list[dict[str, Any]], most: int) -> dict[str, Any]:
    answer: dict[str, Any] = {"count": len(rows), "rows": rows[:most]}
    if len(rows) > most:
        answer["truncated"] = f"The first {most} of {len(rows)}; raise max_items to see more."
    return answer


def read(path: str, what: str, layer: str | None, block_name: str | None, contains: str | None,
         max_items: int, output: str) -> dict[str, Any] | str:
    """The answer for one file, as plain data (or CSV text for attributes). Runs off the event loop."""
    opened = dxf_file.open_file(path)
    doc = opened.doc
    if what == "summary":
        answer: dict[str, Any] = dxf_file.summary(opened)
    elif what == "layers":
        counts = dxf_file.layer_counts(doc)
        rows = [{**row, "objects": counts.get(row["name"], 0)} for row in dxf_file.layer_rows(doc)]
        answer = {**_capped(rows, max_items), "objects_counted": "in model space and the layouts, not inside blocks"}
    elif what == "blocks":
        rows = [r for r in dxf_file.block_rows(doc) if dxf_file.matches(r["name"], block_name)]
        answer = _capped(rows, max_items)
    elif what == "text":
        answer = _capped(dxf_file.text_rows(doc, layer=layer, contains=contains), max_items)
    elif what == "attributes":
        rows = dxf_file.attribute_rows(doc, block_name=block_name, layer=layer)
        if output == "csv":
            return rows_to_csv(rows[:max_items])
        answer = _capped(rows, max_items)
    else:  # styles
        answer = dxf_file.tables(doc)
        answer.pop("layers")
    answer = {"file": str(opened.file), "read_by": opened.read_by, **answer}
    if opened.recovered:
        answer["recovered"] = (
            f"The file has damage: ezdxf's recover mode put {opened.recovered} problem(s) right while "
            "reading it (the file itself was not changed). Check anything that looks wrong in AutoCAD."
        )
    answer["note"] = dxf_file.SAVED_ONLY
    return answer


@mcp.tool(
    name="autocad_read_file",
    **tool_meta("Read a DXF or DWG File Without AutoCAD", read_only=True, idempotent=True),
)
@tool_errors
async def autocad_read_file(
    path: Annotated[
        str,
        Field(min_length=1, description="The file's full path: a .dxf, or a .dwg / .dws / .dwt (those need the ODA File Converter)."),
    ],
    what: Annotated[
        What,
        Field(description=(
            "'summary': version, units, extents, counts, the most placed blocks, layouts, xrefs. "
            "'layers': the layer table with objects per layer. 'blocks': each block, how many are "
            "placed and its attribute tags. 'text': every text and mtext. 'attributes': every placed "
            "block's attribute values. 'styles': text styles, dimension styles and linetypes."
        )),
    ] = "summary",
    layer: Annotated[str | None, Field(description="text / attributes: only on this layer (wildcards, e.g. 'M-*').")] = None,
    block_name: Annotated[str | None, Field(description="blocks / attributes: only this block (wildcards, e.g. 'TITLE*').")] = None,
    contains: Annotated[str | None, Field(description="text: only text containing these words (any case).")] = None,
    max_items: Annotated[int, Field(ge=1, le=20000, description="The most rows in the answer.")] = 500,
    output: Annotated[Literal["json", "csv"], Field(description="attributes: json rows, or CSV with one column per tag.")] = "json",
) -> str:
    """Read a DXF or DWG file on disk without AutoCAD: layers, blocks and counts, text, attributes, extents.

    Works with AutoCAD closed, and never changes the file. A DXF is read
    directly. A DWG (or a .dws standards file, or a .dwt template) is converted
    first, from a temporary copy, by the free ODA File Converter, when it is
    installed on this PC: Heron finds it, it never downloads it. Without it a
    DWG is refused, saying plainly that it needs AutoCAD (open it there) or the
    ODA converter, or a DXF of it. The answer is what was last saved: changes
    not yet saved in AutoCAD are not in the file.

    Args:
        path (str): the file.
        what (str): summary, layers, blocks, text, attributes or styles.
        layer, block_name, contains (str): filters, with wildcards.
        max_items (int): the most rows.
        output (str): json or csv (attributes).

    Returns:
        str: JSON: {"file", "read_by", "note", ...}. summary: {"format",
             "units", "extents" {"min", "max", "from"}, "layers", "objects",
             "model_by_type", "text", "blocks", "most_placed_blocks",
             "layouts", "xrefs"}; layers / blocks / text / attributes:
             {"count", "rows", "truncated"}; styles: {"text_styles",
             "dim_styles", "linetypes"}. CSV text for attributes as csv.

    Examples:
        - Use when: "what's in this DXF the contractor sent?" with AutoCAD
          closed -> the summary.
        - Use when: "which layers does M-101.dwg use?" or "how many valves are
          in that file?" without opening it -> layers / blocks.
        - Use when: "list the title block values of every drawing in this
          folder" -> attributes, one file at a time, block_name='TITLE*'.
        - Use when: "find the text 'FCU-03' in the old DXF".
        - Don't use when: the drawing is open in AutoCAD - autocad_list_layers,
          autocad_list_blocks, autocad_find_text and autocad_extract_attributes
          read it there, with the changes not yet saved.
        - Don't use when: a whole folder should be checked against a check list
          - autocad_check_folder.

    Error Handling:
        - A DWG with no ODA File Converter on this PC is refused with the three
          ways round it; nothing is downloaded.
        - A damaged DXF is read in recover mode and the answer says so; the file
          is never changed.
        - A file over 250 MB, a locked file or a missing one is refused, saying why.
    """
    answer = await asyncio.to_thread(read, path, what, layer, block_name, contains, max_items, output)
    return answer if isinstance(answer, str) else dumps(answer)
