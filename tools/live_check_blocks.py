"""Live checks for blocks, attributes and tables (group AC) and attribute sheets and folder checks (group Y).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Each row draws its own objects at its own spot (``lc.origin``), then measures what
the tool did with a second, independent read: an attribute's value, place and
visibility read off the insert, a table's cell text and alignment read off the
table, a layer's colour from the layer list, a file's size and date.

Rows that would erase something are left to an eye: Heron then asks the modeller
to keep it erased (D-50) and the runner cannot answer. ATTSYNC erases the
attribute an insert loses (``BlockAttributes.SyncOne`` in the plug-in), so only
syncs that add attributes are scripted here.

A few things no tool does are done here, as the runner's own helpers (the tests
put recorded answers in their place): reading a table's cells, an insert's
attributes and the drawing's data links over COM, changing an attribute "by
hand", making a drawing and closing it, and writing the files a row starts from.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import live_common as lc
from live_common import Check, Context, expect, near_point, parse, refusal

from autocad_mcp.acad import xlsx
from autocad_mcp.tools import (
    annotate,
    attribute_sheet,
    batch,
    between_drawings,
    blocks,
    check_folder,
    document,
    draw,
    layers,
    query,
    tables,
)


def _at(o: tuple[float, float], x: float, y: float) -> list[float]:
    return [o[0] + x, o[1] + y]


async def _draw(*operations: dict[str, Any]) -> list[str]:
    """Draw with autocad_batch_draw; the handles, in order."""
    made = parse(await batch.autocad_batch_draw(operations=list(operations)))
    expect(made.get("created") == len(operations), f"drew {made.get('created')} of {len(operations)} test objects")
    return list(made["handles"])


async def _entity(handle: str) -> dict[str, Any]:
    return parse(await query.autocad_get_entity(handle=handle))


async def _active_name() -> str:
    status = parse(await document.autocad_status())
    return str((status.get("active_drawing") or {}).get("name") or "")


def _middle(alignment: Any) -> bool:
    """AcCellAlignment 4, 5, 6: the vertical middle, left / centre / right."""
    try:
        return 4 <= int(alignment) <= 6
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Done by the runner itself, not through Heron
# ---------------------------------------------------------------------------


def _try(read: Any, *args: Any, default: Any = None) -> Any:
    try:
        return read(*args)
    except BaseException:  # noqa: BLE001 - a property this object will not give
        return default


async def _table(handle: str) -> dict[str, Any]:
    """A table as AutoCAD holds it: size, each cell's text, alignment and state, each row's type, the top-left merge."""
    from autocad_mcp.acad.entities import resolve_handle
    from autocad_mcp.core.connection import get_doc, run

    def read() -> dict[str, Any]:
        table = resolve_handle(get_doc(), handle)
        rows, columns = int(table.Rows), int(table.Columns)
        grid = [(r, c) for r in range(rows) for c in range(columns)]
        texts = [[_try(lambda r, c: str(table.GetText(r, c)), r, c, default="") for c in range(columns)] for r in range(rows)]
        aligned = {f"{r},{c}": _try(lambda r, c: int(table.GetCellAlignment(r, c)), r, c) for r, c in grid}
        states = {f"{r},{c}": _try(lambda r, c: int(table.GetCellState(r, c)), r, c) for r, c in grid}
        merged = _try(lambda: table.IsMergedCell(0, 0))
        top = None
        if isinstance(merged, tuple) and len(merged) >= 5 and merged[0]:
            top = [int(v) for v in merged[1:5]]  # first row, last row, first column, last column
        return {
            "rows": rows,
            "columns": columns,
            "texts": texts,
            "alignment": [[aligned[f"{r},{c}"] for c in range(columns)] for r in range(rows)],
            "state": [[states[f"{r},{c}"] for c in range(columns)] for r in range(rows)],
            "row_types": [_try(lambda r: int(table.GetRowType(r)), r) for r in range(rows)],
            "top_merge": top,
        }

    return await run(read)


async def _attributes_of(handle: str) -> list[dict[str, Any]]:
    """An insert's attributes as AutoCAD holds them: tag, text, hidden or not, where, how high."""
    from autocad_mcp.acad.entities import resolve_handle
    from autocad_mcp.core.connection import get_doc, run

    def read() -> list[dict[str, Any]]:
        ref = resolve_handle(get_doc(), handle)
        found = []
        for att in ref.GetAttributes():
            found.append({
                "tag": str(att.TagString),
                "text": str(att.TextString),
                "invisible": bool(att.Invisible),
                "position": [float(v) for v in att.InsertionPoint][:3],
                "height": float(att.Height),
            })
        return found

    return await run(read)


async def _nested_attributes(holder: str, block: str) -> list[dict[str, str]]:
    """The attributes (tag -> text) of each insert of ``block`` inside the definition of ``holder``."""
    from autocad_mcp.core.connection import get_doc, run

    def read() -> list[dict[str, str]]:
        definition = get_doc().Blocks.Item(holder)
        found = []
        for i in range(int(definition.Count)):
            item = definition.Item(i)
            if str(item.ObjectName) != "AcDbBlockReference":
                continue
            name = str(_try(lambda obj: obj.EffectiveName, item, default="") or item.Name)
            if name.lower() == block.lower():
                found.append({str(a.TagString): str(a.TextString) for a in item.GetAttributes()})
        return found

    return await run(read)


async def _data_links() -> list[str] | None:
    """The names in the drawing's Data Link Manager (the ACAD_DATALINK dictionary), or None when it cannot be read."""
    from autocad_mcp.core.connection import get_doc, run

    def read() -> list[str] | None:
        try:
            links = get_doc().Dictionaries.Item("ACAD_DATALINK")
            return [str(links.GetName(links.Item(i))) for i in range(int(links.Count))]
        except BaseException:  # noqa: BLE001 - no links yet, or COM will not list them
            return None

    return await run(read)


async def _by_hand_attribute(handle: str, tag: str, value: str) -> None:
    """Change one attribute as the modeller does in ATTEDIT: straight in the drawing, not through Heron."""
    from autocad_mcp.acad.entities import resolve_handle
    from autocad_mcp.core.connection import get_doc, run

    def edit() -> None:
        ref = resolve_handle(get_doc(), handle)
        for att in ref.GetAttributes():
            if str(att.TagString).upper() == tag.upper():
                att.TextString = value
        ref.Update()

    await run(edit)


async def _closed_drawing(path: Path) -> str:
    """A new empty drawing saved as ``path`` and closed again, so it is on disk but not open. Its name."""
    from autocad_mcp.core.connection import get_app, run

    def make() -> str:
        doc = get_app().Documents.Add()
        doc.SaveAs(str(path))
        name = str(doc.Name)
        doc.Close(False)
        return name

    return await run(make)


def _write_file(path: Path, content: bytes) -> None:
    """A file the row starts from (a sheet, a .csv, a damaged .dwg), written beside the drawings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _read_workbook(path: Path) -> dict[str, list[list[str]]]:
    """Every sheet of a workbook, as Heron reads it."""
    return xlsx.read(path.read_bytes())


def _write_workbook(path: Path, sheets: dict[str, list[list[str]]]) -> None:
    """A workbook saved again with these sheets, as the modeller saves it from Excel (text cells only)."""
    path.write_bytes(xlsx.write([(name, rows, None) for name, rows in sheets.items()]))


# ---------------------------------------------------------------------------
# Group AC - blocks, attributes and tables
# ---------------------------------------------------------------------------

PUMPS = [
    ["TAG", "FLOW", "HEAD", "TYPE"],
    ["P-01", "12.0", "30", "END SUCTION"],
    ["P-02", "8.5", "22", "INLINE"],
    ["P-03", "15.0", "35", "END SUCTION"],
    ["P-04", "6.0", "18", "INLINE"],
    ["P-05", "40.0", "45", "SPLIT CASE"],
]


async def _pump_sheet(ctx: Context, name: str, rows: list[list[str]] = PUMPS) -> Path:
    """A one-sheet workbook (Sheet1) of pumps beside the saved scratch drawing."""
    drawing = await lc.save_scratch(ctx)
    path = drawing.parent / name
    _write_file(path, xlsx.write([("Sheet1", rows, None)]))
    return path


async def _linked_pumps(ctx: Context, row: str, name: str) -> tuple[dict[str, Any], Path]:
    """A table linked to a pumps sheet, at the row's spot; (the answer, the sheet). Refused when it could not link."""
    sheet = await _pump_sheet(ctx, name)
    out = parse(await tables.autocad_table_from_excel(path=name, position=_at(lc.origin(row), 0, 0), cell_range="A1:D6"))
    if out.get("linked") is not True:
        raise lc.Refused(f"the table could not be linked to {name}, so this was not tried: {out.get('not_linked_because')}")
    return out, sheet


async def ac2_a_bad_tag_and_a_constant_with_no_default_are_refused(ctx: Context) -> str:
    o = lc.origin("AC2")
    (circle,) = await _draw({"type": "circle", "center": _at(o, 0, 0), "radius": 100, "layer": "LC-AC2"})
    spaced = refusal(await blocks.autocad_make_block(
        name="LC-AC2-TAG", handles=[circle], base_point=_at(o, 0, 0), keep_originals=True,
        attributes=[{"tag": "VALVE TAG", "default": "V-101"}],
    ))
    expect("space" in spaced and "VALVE TAG" in spaced, f"the tag with a space was refused without saying why: {spaced[:160]}")
    constant = refusal(await blocks.autocad_make_block(
        name="LC-AC2-TAG", handles=[circle], base_point=_at(o, 0, 0), keep_originals=True,
        attributes=[{"tag": "MAKE", "constant": True}],
    ))
    expect("constant" in constant and "default" in constant,
           f"the constant attribute with no default was refused without saying why: {constant[:160]}")
    listed = parse(await layers.autocad_list_blocks(include_unused=True))
    names = [b.get("name") for b in listed.get("blocks") or []]
    expect("LC-AC2-TAG" not in names, "a block LC-AC2-TAG was made although both were refused")
    expect(await lc.exists(circle), "the circle went although nothing was made")
    return (f"'VALVE TAG' refused: {spaced[:70]}; constant with no default refused: {constant[:70]}; "
            "autocad_list_blocks has no LC-AC2-TAG and the circle is still there")


async def ac6_an_attribute_added_to_a_block_reaches_every_insert(ctx: Context) -> str:
    o = lc.origin("AC6")
    block = "LC-AC6-PUMP"
    (circle,) = await _draw({"type": "circle", "center": _at(o, 0, 0), "radius": 200, "layer": "LC-AC6"})
    parse(await blocks.autocad_make_block(
        name=block, handles=[circle], base_point=_at(o, 0, 0), keep_originals=True,
        attributes=[{"tag": "TAG", "default": "P-100", "position": _at(o, 0, 100), "height": 50}],
    ))
    flat = parse(await draw.autocad_insert_block(block_name=block, position=_at(o, 2000, 0), attributes={"TAG": "P-101"}))
    turned = parse(await draw.autocad_insert_block(block_name=block, position=_at(o, 4000, 0), rotation=90,
                                                    attributes={"TAG": "P-102"}))
    inserts = {flat["handle"]: (_at(o, 2000, 0), [0.0, -300.0], "P-101"), turned["handle"]: (_at(o, 4000, 0), [300.0, 0.0], "P-102")}
    out = parse(await blocks.autocad_sync_attributes(
        block=block, add_attributes=[{"tag": "MAKE", "default": "GRUNDFOS", "position": [0, -300], "invisible": True}],
    ))
    expect(out.get("definitions_added") == ["MAKE"], f"the definition gained {out.get('definitions_added')}, not MAKE")
    expect(out.get("touched") == 2 and out.get("attributes_dropped") == 0,
           f"the sync touched {out.get('touched')} inserts and dropped {out.get('attributes_dropped')}, not 2 and 0")
    for handle, (at, offset, tag) in inserts.items():
        got = {a["tag"]: a for a in await _attributes_of(handle)}
        make = got.get("MAKE")
        expect(make is not None, f"the insert {handle} has no MAKE attribute: it has {sorted(got)}")
        expect(make["text"] == "GRUNDFOS" and make["invisible"] is True,
               f"MAKE on {handle} reads {make['text']!r}, hidden {make['invisible']}, not GRUNDFOS and hidden")
        want = [at[0] + offset[0], at[1] + offset[1]]
        expect(near_point(make["position"], want, 1e-6),
               f"MAKE on {handle} sits at {make['position'][:2]}, not {want} (300 below the base point as the block is drawn)")
        expect(got.get("TAG", {}).get("text") == tag, f"{handle} lost its typed TAG {tag}: it reads {got.get('TAG')}")
    out = parse(await blocks.autocad_sync_attributes(block=block, add_attributes=[{"tag": "FLOW"}]))
    expect(out.get("definitions_added") == ["FLOW"], f"the definition gained {out.get('definitions_added')}, not FLOW")
    got = {a["tag"]: a for a in await _attributes_of(flat["handle"])}
    flow = got.get("FLOW")
    expect(flow is not None, f"the insert {flat['handle']} has no FLOW attribute: it has {sorted(got)}")
    base = _at(o, 2000, 0)
    want = [base[0], base[1] - 300 - 1.5 * flow["height"]]
    expect(near_point(flow["position"], want, 1e-6),
           f"FLOW sits at {flow['position'][:2]}, not {want}: under MAKE, the lowest attribute, by 1.5 text heights")
    others = [a for t, a in got.items() if t != "FLOW"]
    clash = [a["tag"] for a in others if near_point(a["position"], flow["position"], flow["height"] / 2)]
    expect(not clash, f"FLOW sits on top of {clash}")
    listed = parse(await layers.autocad_list_blocks(include_unused=True))
    tags = next((b.get("attribute_tags") or [] for b in listed.get("blocks") or [] if b.get("name") == block), [])
    expect({"TAG", "MAKE", "FLOW"} <= {str(t).upper() for t in tags}, f"the block definition lists the tags {tags}")
    return ("both inserts carry MAKE = GRUNDFOS, hidden, 300 below the base point as the block is drawn (300 to "
            f"the side on the one turned 90), their TAGs kept; FLOW landed {300 + 1.5 * flow['height']:g} below the "
            f"base point, under MAKE; the definition lists {', '.join(tags)}. BATTMAN itself was not opened")


async def ac7_a_table_linked_to_excel_shows_the_sheet(ctx: Context) -> str:
    o = lc.origin("AC7")
    sheet = await _pump_sheet(ctx, "pumps.xlsx")
    out = parse(await tables.autocad_table_from_excel(path="pumps.xlsx", position=_at(o, 0, 0), cell_range="A1:D6"))
    expect(out.get("linked") is True,
           f"the table is not linked; AutoCAD answered: {out.get('not_linked_because')}. Note whether Excel is installed")
    expect(out.get("link") == "Heron pumps Sheet1 A1:D6", f"the data link is called {out.get('link')!r}")
    expect(str(out.get("connection", "")).lower().endswith("pumps.xlsx!sheet1!a1:d6"),
           f"the link points at {out.get('connection')!r}, not pumps.xlsx, Sheet1, A1:D6")
    table = await _table(out["handle"])
    expect((table["rows"], table["columns"]) == (6, 4), f"the table is {table['rows']} x {table['columns']}, not 6 x 4")
    expect(table["texts"] == PUMPS, f"the cells read {table['texts']}, not the sheet")
    off = [f"{r + 1},{c + 1}" for r, row in enumerate(table["alignment"]) for c, a in enumerate(row) if not _middle(a)]
    expect(not off, f"these cells are not in the vertical middle: {off[:10]}")
    links = await _data_links()
    if links is not None:
        expect(out["link"] in links, f"the Data Link Manager lists {links}, not {out['link']}")
    seen = "listed in the Data Link Manager" if links is not None else "the Data Link Manager could not be read here"
    return (f"linked: a 6 x 4 table whose cells read the 6 rows of {sheet.name} as written, every cell in the "
            f"vertical middle; the link 'Heron pumps Sheet1 A1:D6' points at the file and range ({seen})")


async def ac8_a_linked_table_updates_from_the_saved_sheet(ctx: Context) -> str:
    out, sheet = await _linked_pumps(ctx, "AC8", "LC-AC8-pumps.xlsx")
    edited = [list(r) for r in PUMPS]
    edited[2][1], edited[4][2] = "9.5", "20"
    _write_file(sheet, xlsx.write([("Sheet1", edited, None)]))
    done = parse(await tables.autocad_update_table_links())
    updated = [u.get("handle") for u in done.get("updated") or []]
    expect(out["handle"] in updated, f"updated names {updated}, not the table {out['handle']}")
    table = await _table(out["handle"])
    expect(table["texts"][2][1] == "9.5" and table["texts"][4][2] == "20",
           f"B3 reads {table['texts'][2][1]!r} and C5 {table['texts'][4][2]!r}, not the new 9.5 and 20")
    expect(table["texts"] == edited, f"the other cells changed: {table['texts']}")
    off = [f"{r + 1},{c + 1}" for r, row in enumerate(table["alignment"]) for c, a in enumerate(row) if not _middle(a)]
    expect(not off, f"after the update these cells are not in the vertical middle: {off[:10]}")
    return (f"{sheet.name} saved with two new values; update_table_links named the table and B3 reads 9.5, C5 "
            "reads 20 (not the link's cached 8.5 and 18), every cell still in the vertical middle. "
            "The sheet was saved by Heron's writer, not Excel; Ctrl+Z was not tried")


async def ac9_a_csv_and_an_unlinked_sheet_fill_a_table(ctx: Context) -> str:
    o = lc.origin("AC9")
    drawing = await lc.save_scratch(ctx)
    _write_file(drawing.parent / "LC-AC9-pumps.csv", "\r\n".join(",".join(row) for row in PUMPS).encode("utf-8"))
    from_csv = parse(await tables.autocad_table_from_excel(path="LC-AC9-pumps.csv", position=_at(o, 0, 0)))
    expect(from_csv.get("linked") is False and ".csv" in str(from_csv.get("not_linked_because")),
           f"the .csv table answered linked {from_csv.get('linked')}, because {from_csv.get('not_linked_because')!r}")
    plain = await _table(from_csv["handle"])
    expect(plain["rows"] == 6 and plain["texts"][0] == PUMPS[0],
           f"with no title the table has {plain['rows']} rows and its first row reads {plain['texts'][0]}, "
           "not the sheet's header row")
    expect(plain["texts"] == PUMPS, f"the .csv table reads {plain['texts']}")
    await _pump_sheet(ctx, "LC-AC9-pumps.xlsx")
    titled = parse(await tables.autocad_table_from_excel(
        path="LC-AC9-pumps.xlsx", position=_at(o, 0, -3000), link=False, title="PUMP SCHEDULE",
    ))
    expect(titled.get("linked") is False and "link=false" in str(titled.get("not_linked_because")),
           f"link=false answered linked {titled.get('linked')}, because {titled.get('not_linked_because')!r}")
    table = await _table(titled["handle"])
    expect(table["rows"] == 7 and table["texts"][0][0] == "PUMP SCHEDULE",
           f"the titled table has {table['rows']} rows and reads {table['texts'][0][0]!r} at the top")
    expect(table["top_merge"] is not None and table["top_merge"][2:] == [0, 3],
           f"the title row is merged over {table['top_merge']}, not across all 4 columns")
    expect(table["texts"][1:] == PUMPS, "under the title the rows are not the sheet's")
    return ("the .csv filled a 6-row table (linked false: Heron links .xlsx only) whose first row is the header; "
            "link=false with a title filled 7 rows, PUMP SCHEDULE merged across the 4 columns on top")


async def ac11_cells_change_by_address_and_grow_adds_a_row(ctx: Context) -> str:
    o = lc.origin("AC11")
    await _pump_sheet(ctx, "LC-AC11-pumps.xlsx")
    made = parse(await tables.autocad_table_from_excel(path="LC-AC11-pumps.xlsx", position=_at(o, 0, 0), link=False))
    handle = made["handle"]
    cells = [{"cell": "B3", "value": "12.5"}, {"row": 4, "column": 2, "value": "8"}]
    raw = await tables.autocad_set_table_cells(handle=handle, cells=cells, dry_run=True)
    head, dry = lc.first_line(raw), parse(raw)
    rows = {r.get("property"): (r.get("from"), r.get("to")) for r in dry.get("before_after") or []}
    expect(dry.get("would_change") == 2 and rows == {"cell B3": (PUMPS[2][1], "12.5"), "cell B4": (PUMPS[3][1], "8")},
           f"the dry run listed {rows}, would change {dry.get('would_change')}")
    expect(head.startswith("NOTHING CHANGED"), f"the dry run's first line is {head!r}")
    expect((await _table(handle))["texts"] == PUMPS, "the dry run changed the table")
    out = parse(await tables.autocad_set_table_cells(handle=handle, cells=cells))
    expect(out.get("changed") == 2 and not out.get("refused"), f"changed {out.get('changed')}, refused {out.get('refused')}")
    table = await _table(handle)
    expect(table["texts"][2][1] == "12.5" and table["texts"][3][1] == "8",
           f"B3 reads {table['texts'][2][1]!r} and B4 {table['texts'][3][1]!r}, not 12.5 and 8")
    expect(_middle(table["alignment"][2][1]) and _middle(table["alignment"][3][1]), "a changed cell left the vertical middle")
    past = refusal(await tables.autocad_set_table_cells(handle=handle, cells=[{"cell": "A7", "value": "P-06"}]))
    expect("A7" in past and "grow" in past, f"the cell past the end was refused without saying so: {past[:160]}")
    expect((await _table(handle))["rows"] == 6, "the refused cell still added a row")
    grown = parse(await tables.autocad_set_table_cells(handle=handle, cells=[{"cell": "A7", "value": "P-06"}], grow=True))
    expect(grown.get("added_rows") == 1 and grown.get("changed") == 1, f"grow answered {grown}")
    table = await _table(handle)
    expect(table["rows"] == 7 and table["texts"][6][0] == "P-06", f"the table has {table['rows']} rows, A7 reads {table['texts'][-1][0]!r}")
    return (f"the dry run listed B3 {PUMPS[2][1]} -> 12.5 and B4 {PUMPS[3][1]} -> 8 and changed nothing; then both read the new text in the "
            "vertical middle; A7 past the end was refused naming grow, then grow added one row holding P-06. "
            "Ctrl+Z was not tried")


async def ac12_a_cell_of_a_linked_table_is_refused(ctx: Context) -> str:
    out, _ = await _linked_pumps(ctx, "AC12", "LC-AC12-pumps.xlsx")
    done = parse(await tables.autocad_set_table_cells(handle=out["handle"], cells=[{"cell": "B3", "value": "CHANGED"}]))
    why = {r.get("cell"): r.get("why", "") for r in done.get("refused") or []}
    expect("linked to Excel: change it in the sheet" in why.get("B3", ""), f"B3 was not refused as linked: {done}")
    expect(not done.get("changed"), f"changed {done.get('changed')} cells of a linked table")
    table = await _table(out["handle"])
    expect(table["texts"][2][1] == PUMPS[2][1], f"B3 now reads {table['texts'][2][1]!r}")
    return f"B3 of the linked table refused: '{why['B3']}'; it still reads {PUMPS[2][1]}"


async def ac13_a_table_with_and_without_a_title_and_headings(ctx: Context) -> str:
    o = lc.origin("AC13")
    headers, rows = ["TAG", "TYPE", "FLOW"], [["P-01", "INLINE", "8.5"], ["P-02", "INLINE", "6.0"]]
    full = parse(await annotate.autocad_add_table(position=_at(o, 0, 0), rows=rows, headers=headers, title="LC-AC13 PUMPS"))
    expect(full.get("rows_aligned_middle") == 3 and not full.get("not_set"),
           f"with a title: rows_aligned_middle {full.get('rows_aligned_middle')}, not_set {full.get('not_set')}")
    table = await _table(full["handle"])
    expect(table["texts"][0][0] == "LC-AC13 PUMPS" and table["texts"][1] == headers and table["texts"][2:] == rows,
           f"with a title the cells read {table['texts']}")
    off = [f"{r + 1},{c + 1}" for r, row in enumerate(table["alignment"]) for c, a in enumerate(row) if not _middle(a)]
    expect(not off, f"these cells are not in the vertical middle: {off[:10]}")
    bare = parse(await annotate.autocad_add_table(position=_at(o, 0, -3000), rows=rows, headers=headers))
    expect(bare.get("suppressed") == ["TitleSuppressed"] and not bare.get("not_set"),
           f"with no title: suppressed {bare.get('suppressed')}, not_set {bare.get('not_set')}")
    table = await _table(bare["handle"])
    expect(table["rows"] == 3 and table["texts"][0] == headers and table["top_merge"] is None,
           f"with no title the table has {table['rows']} rows, its first row reads {table['texts'][0]}, "
           f"merged {table['top_merge']}: not the headings one per cell")
    expect(table["row_types"][0] == 4, f"the headings' row is of type {table['row_types'][0]}, not a header row (4)")
    plain = parse(await annotate.autocad_add_table(position=_at(o, 0, -6000), rows=rows))
    expect(set(plain.get("suppressed") or []) == {"TitleSuppressed", "HeaderSuppressed"},
           f"rows only: suppressed {plain.get('suppressed')}")
    table = await _table(plain["handle"])
    expect(table["rows"] == 2 and table["texts"][0] == rows[0] and table["row_types"][0] == 1,
           f"rows only: first row reads {table['texts'][0]} of type {table['row_types'][0]}, not ordinary data (1)")
    return ("with a title: title, headings and data in their own rows, every cell in the vertical middle (3 row "
            "types set); headings and no title: 3 rows, the headings one per cell in row 1, no merged row, "
            "TitleSuppressed; rows only: 2 rows, the first a data row. Bold was not looked at")


async def ac14_objects_copy_in_from_another_open_drawing(ctx: Context) -> str:
    o = lc.origin("AC14")
    await lc.other_drawing(ctx, "LC-AC14", "pump-room.dwg")
    parse(await layers.autocad_create_layer(name="M-EQPT", color=3))
    (motor_part,) = await _draw({"type": "circle", "center": _at(o, 300, 300), "radius": 100, "layer": "E-MOTOR"})
    parse(await blocks.autocad_make_block(name="LC-AC14-MOTOR", handles=[motor_part], base_point=_at(o, 300, 300),
                                          keep_originals=True))
    motor = parse(await draw.autocad_insert_block(block_name="LC-AC14-MOTOR", position=_at(o, 300, 300), layer="E-MOTOR"))
    frame, pipe1, pipe2 = await _draw(
        {"type": "rectangle", "corner1": _at(o, 0, 0), "corner2": _at(o, 1000, 600), "layer": "M-EQPT"},
        {"type": "line", "start": _at(o, 1000, 300), "end": _at(o, 2000, 300), "layer": "LC-AC14-PIPE"},
        {"type": "line", "start": _at(o, -1000, 300), "end": _at(o, 0, 300), "layer": "LC-AC14-PIPE"},
    )
    parse(await blocks.autocad_make_block(name="LC-AC14-SKID", handles=[frame, motor["handle"]], base_point=_at(o, 0, 0),
                                          keep_originals=True))
    skid = parse(await draw.autocad_insert_block(block_name="LC-AC14-SKID", position=_at(o, 0, 3000), layer="M-EQPT"))
    source_count = await lc.entity_count()
    await lc.other_drawing(ctx, "LC-AC14", "plan.dwg")
    parse(await layers.autocad_create_layer(name="M-EQPT", color=1))
    before = await lc.entity_count()
    ask = {"source": "pump-room", "handles": [skid["handle"], pipe1, pipe2], "base_point": _at(o, 0, 0),
           "to_point": _at(o, 5000, 2000)}
    raw = await between_drawings.autocad_copy_from_drawing(**ask, dry_run=True)
    head, dry = lc.first_line(raw), parse(raw)
    brought, here = dry.get("brought_in") or {}, dry.get("already_here") or {}
    expect("E-MOTOR" in (brought.get("layers") or []), f"the dry run does not bring E-MOTOR in: {brought}")
    expect({"LC-AC14-SKID", "LC-AC14-MOTOR"} <= set(brought.get("blocks") or []), f"the dry run brings the blocks {brought.get('blocks')}")
    expect("M-EQPT" in (here.get("layers") or []), f"the dry run does not list M-EQPT as already here: {here}")
    expect(dry.get("would_copy") == 3 and head.startswith("NOTHING CHANGED"), f"the dry run: {head!r}, would copy {dry.get('would_copy')}")
    expect(await lc.entity_count() == before, "the dry run copied something")
    out = parse(await between_drawings.autocad_copy_from_drawing(**ask))
    new = out.get("handles") or []
    expect(out.get("copied") == 3 and len(new) == 3, f"copied {out.get('copied')}, handles {new}")
    expect(await lc.entity_count() == before + 3, "plan.dwg does not have 3 more objects")
    block: dict[str, Any] = {}
    for handle in new:
        info = await _entity(handle)
        if info.get("type") == "block":
            block = info
    expect(block.get("block_name") == "LC-AC14-SKID" and block.get("layer") == "M-EQPT"
           and near_point(block.get("insertion_point"), _at(o, 5000, 5000)),
           f"the skid landed as {block.get('block_name')} on {block.get('layer')} at {block.get('insertion_point')}, "
           "not 5000,2000 from where it was")
    listed = {la["name"]: la for la in parse(await layers.autocad_list_layers()).get("layers") or []}
    expect("E-MOTOR" in listed, "E-MOTOR is not a layer in plan.dwg")
    expect(listed.get("M-EQPT", {}).get("color") == 1, f"M-EQPT is colour {listed.get('M-EQPT', {}).get('color')} in plan.dwg, not its own 1")
    expect(await _active_name() == "plan.dwg", "plan.dwg is not the active drawing after the copy")
    await lc.activate(ctx, "pump-room.dwg")
    expect(await lc.entity_count() == source_count, "pump-room.dwg changed")
    await lc.activate(ctx)
    return ("the dry run listed E-MOTOR and both blocks as brought in, M-EQPT as already here, copying nothing; then "
            "3 objects came in, the skid 5000,2000 away on M-EQPT, E-MOTOR a new layer, M-EQPT kept plan.dwg's red; "
            "plan.dwg stayed active and pump-room.dwg kept its count. Ctrl+Z was not tried")


async def ac15_a_wrong_handle_and_the_active_drawing_as_source_are_refused(ctx: Context) -> str:
    o = lc.origin("AC15")
    await lc.other_drawing(ctx, "LC-AC15", "LC-AC15-source.dwg")
    (theirs,) = await _draw({"type": "line", "start": _at(o, 0, 0), "end": _at(o, 1000, 0), "layer": "LC-AC15"})
    await lc.other_drawing(ctx, "LC-AC15", "LC-AC15-plan.dwg")
    ours = (await _draw(*({"type": "line", "start": _at(o, 0, y), "end": _at(o, 1000, y), "layer": "LC-AC15"}
                          for y in range(0, 1000, 100))))[-1]
    await lc.activate(ctx, "LC-AC15-source.dwg")
    expect(not await lc.exists(ours), f"set-up: the handle {ours} is in the source drawing too; pick another")
    await lc.activate(ctx, "LC-AC15-plan.dwg")
    before = await lc.entity_count()
    wrong = refusal(await between_drawings.autocad_copy_from_drawing(
        source="LC-AC15-source", handles=[theirs, ours], base_point=_at(o, 0, 0),
    ))
    expect(ours.upper() in wrong and "Nothing was copied" in wrong, f"the wrong handle was not named: {wrong[:160]}")
    itself = refusal(await between_drawings.autocad_copy_from_drawing(
        source="LC-AC15-plan", handles=[ours], base_point=_at(o, 0, 0),
    ))
    expect("autocad_copy_entities" in itself, f"the active drawing as source does not point at autocad_copy_entities: {itself[:160]}")
    expect(await lc.entity_count() == before, "something was copied although refused")
    await lc.activate(ctx)
    return (f"the handle {ours} from the plan refused by name, nothing copied; the active drawing as source refused "
            "pointing at autocad_copy_entities. The source was named LC-AC15-plan, not 'plan', so AC14's plan.dwg "
            "could not be taken for it")


async def ac17_nested_inserts_are_synced_only_when_asked(ctx: Context) -> str:
    o = lc.origin("AC17")
    tag, skid_block = "LC-AC17-TAG", "LC-AC17-SKID"
    (circle,) = await _draw({"type": "circle", "center": _at(o, 0, 0), "radius": 100, "layer": "LC-AC17"})
    parse(await blocks.autocad_make_block(name=tag, handles=[circle], base_point=_at(o, 0, 0), keep_originals=True,
                                          attributes=[{"tag": "TAG", "default": "V-200", "position": _at(o, 0, 150),
                                                       "height": 50}]))
    inner = parse(await draw.autocad_insert_block(block_name=tag, position=_at(o, 1000, 0), attributes={"TAG": "V-201"}))
    (frame,) = await _draw({"type": "rectangle", "corner1": _at(o, 500, -500), "corner2": _at(o, 1500, 500), "layer": "LC-AC17"})
    parse(await blocks.autocad_make_block(name=skid_block, handles=[inner["handle"], frame], base_point=_at(o, 1000, 0),
                                          keep_originals=True))
    for x in (0, 3000):
        parse(await draw.autocad_insert_block(block_name=skid_block, position=_at(o, x, 3000)))
    flow = [{"tag": "FLOW", "default": "10"}]
    flat = parse(await blocks.autocad_sync_attributes(block=tag, add_attributes=flow, dry_run=True))
    expect(not [i for i in flat.get("inserts") or [] if i.get("inside")],
           f"without nested the dry run lists inserts inside blocks: {flat.get('inserts')}")
    deep = parse(await blocks.autocad_sync_attributes(block=tag, add_attributes=flow, nested=True, dry_run=True))
    inside = [i for i in deep.get("inserts") or [] if i.get("inside") == skid_block]
    expect(len(inside) == 1, f"with nested the dry run lists {len(inside)} inserts inside {skid_block}, not 1")
    expect(inside[0].get("keep", {}).get("TAG") == "V-201" and "FLOW" in (inside[0].get("add") or {}),
           f"the nested insert would keep {inside[0].get('keep')} and gain {inside[0].get('add')}")
    out = parse(await blocks.autocad_sync_attributes(block=tag, add_attributes=flow, nested=True))
    expect(out.get("touched") == 2 and out.get("attributes_dropped") == 0,
           f"the sync touched {out.get('touched')}, dropped {out.get('attributes_dropped')}: not 2 and 0")
    nested = await _nested_attributes(skid_block, tag)
    expect(nested == [{"TAG": "V-201", "FLOW": "10"}], f"inside {skid_block} the tag reads {nested}")
    top = {a["tag"]: a["text"] for a in await _attributes_of(inner["handle"])}
    expect(top == {"TAG": "V-201", "FLOW": "10"}, f"the loose insert reads {top}")
    return (f"without nested the dry run did not list the tag inside {skid_block}; with nested it did "
            f"(\"inside\": \"{skid_block}\"); after the sync the tag inside the skid (shown by both copies) reads "
            "TAG V-201, FLOW 10. The definition was changed with add_attributes, not in the Block Editor")


CHECKS_AC: tuple[Check, ...] = (
    Check("AC2", "AC", "a bad tag and a bare constant are refused",
          ac2_a_bad_tag_and_a_constant_with_no_default_are_refused),
    Check("AC6", "AC", "an added attribute reaches every insert", ac6_an_attribute_added_to_a_block_reaches_every_insert),
    Check("AC7", "AC", "a linked Excel table shows the sheet", ac7_a_table_linked_to_excel_shows_the_sheet),
    Check("AC8", "AC", "a linked table updates from the sheet", ac8_a_linked_table_updates_from_the_saved_sheet),
    Check("AC9", "AC", "a csv and an unlinked sheet fill tables", ac9_a_csv_and_an_unlinked_sheet_fill_a_table),
    Check("AC11", "AC", "cells change by address, grow adds a row", ac11_cells_change_by_address_and_grow_adds_a_row),
    Check("AC12", "AC", "a linked table's cell is refused", ac12_a_cell_of_a_linked_table_is_refused),
    Check("AC13", "AC", "a table with and without a title", ac13_a_table_with_and_without_a_title_and_headings),
    Check("AC14", "AC", "objects copy in from another drawing", ac14_objects_copy_in_from_another_open_drawing),
    Check("AC15", "AC", "a wrong handle or source is refused",
          ac15_a_wrong_handle_and_the_active_drawing_as_source_are_refused),
    Check("AC17", "AC", "nested inserts sync only when asked", ac17_nested_inserts_are_synced_only_when_asked),
)

EYE_AC: dict[str, str] = {
    "AC1": "making the block in place of the circle erases the circle, so Heron asks you to keep it erased "
           "(D-50); BATTMAN, ATTDISP and the INSERT prompts are also read by eye",
    "AC3": "needs the Block Editor to add FLOW and delete SIZE, and the sync then erases each insert's SIZE "
           "(the plug-in erases a dropped attribute), so Heron asks you to keep it erased (D-50)",
    "AC4": "needs a dynamic block with its grips dragged by hand and an attribute moved in the Block Editor",
    "AC5": "needs a field put into an attribute by hand (Insert Field), which no tool can make",
    "AC5b": "needs HERONSTOP typed while the table is linked; the Model-tab refusal is only half the row",
    "AC10": "needs a date typed in Excel itself: Heron's own sheet writer writes text cells only, never a date",
    "AC16": "needs a sheet tab made active in plan.dwg by hand before the copy, and the result looked at",
}


# ---------------------------------------------------------------------------
# Group Y - attribute sheets, folder checks
# ---------------------------------------------------------------------------


async def _tagged_blocks(row: str, values: list[dict[str, str]]) -> tuple[str, list[str]]:
    """A camera block with TAG and SIZE, inserted once per set of values; (block name, insert handles)."""
    o = lc.origin(row)
    block = f"LC-{row}-CAMERA"
    (circle,) = await _draw({"type": "circle", "center": _at(o, 0, 0), "radius": 100, "layer": f"LC-{row}"})
    parse(await blocks.autocad_make_block(
        name=block, handles=[circle], base_point=_at(o, 0, 0), keep_originals=True,
        attributes=[{"tag": "TAG", "default": "C-00", "position": _at(o, 0, 150), "height": 50},
                    {"tag": "SIZE", "default": "S", "position": _at(o, 0, -150), "height": 50}],
    ))
    handles = []
    for number, given in enumerate(values, 1):
        made = parse(await draw.autocad_insert_block(block_name=block, position=_at(o, 1000 * number, 0), attributes=given))
        handles.append(made["handle"])
    return block, handles


async def _values(handles: list[str]) -> dict[str, dict[str, str]]:
    return {h: (await _entity(h)).get("attributes") or {} for h in handles}


def _edit(rows: list[list[str]], changes: dict[tuple[str, str], str]) -> list[list[str]]:
    """The Attributes sheet with these cells changed, found by (handle, column heading)."""
    heading = rows[0]
    edited = [list(rows[0])]
    for row in rows[1:]:
        row = list(row) + [""] * (len(heading) - len(row))
        for (handle, column), value in changes.items():
            if row[0].upper() == handle.upper():
                row[heading.index(column)] = value
        edited.append(row)
    return edited


async def y2_an_edited_sheet_writes_only_what_changed(ctx: Context) -> str:
    drawing = await lc.save_scratch(ctx)
    start = [{"TAG": "0050", "SIZE": "S"}, {"TAG": "0051", "SIZE": "M"}, {"TAG": "0052", "SIZE": "L"}]
    block, (a, b, c) = await _tagged_blocks("Y2", start)
    sheet = parse(await attribute_sheet.autocad_export_attribute_sheet(block_name=block))
    path = Path(sheet["saved"])
    expect(str(path.parent).lower() == str(drawing.parent).lower() and path.name.startswith(f"{drawing.stem} - attributes - ")
           and path.suffix == ".xlsx", f"the sheet was saved as {path}, not '<drawing> - attributes - <date>.xlsx' beside it")
    book = _read_workbook(path)
    expect(list(book) == ["Attributes", "As exported", "Read me"], f"the workbook's sheets are {list(book)}")
    column = book["Attributes"][0].index("TAG")
    tags = [r[column] for r in book["Attributes"][1:]]
    expect(sorted(tags) == ["0050", "0051", "0052"], f"the TAG column reads {tags}: the leading zeros were lost")
    book["Attributes"] = _edit(book["Attributes"], {(a, "TAG"): "0060", (b, "TAG"): "0061", (c, "SIZE"): ""})
    _write_workbook(path, book)
    dry = parse(await attribute_sheet.autocad_apply_attribute_sheet(path=str(path), dry_run=True))
    expect(dry.get("would_change") == 2 and dry.get("blank_cells") == 1,
           f"the dry run would change {dry.get('would_change')} with {dry.get('blank_cells')} blank cells, not 2 and 1")
    expect(await _values([a, b, c]) == dict(zip((a, b, c), start, strict=True)), "the dry run changed the drawing")
    out = parse(await attribute_sheet.autocad_apply_attribute_sheet(path=str(path)))
    pairs = {(r.get("handle", "").upper(), r.get("from"), r.get("to")) for r in out.get("before_after") or []}
    expect(out.get("changed") == 2 and pairs == {(a.upper(), "0050", "0060"), (b.upper(), "0051", "0061")},
           f"changed {out.get('changed')}, before_after {sorted(pairs)}")
    now = await _values([a, b, c])
    expect(now[a].get("TAG") == "0060" and now[b].get("TAG") == "0061", f"the TAGs read {now[a]} and {now[b]}")
    expect(now[c] == start[2], f"the emptied SIZE cell changed the third block: it reads {now[c]}")
    return (f"exported {path.name} beside the drawing (Attributes, As exported, Read me; 0050 still 0050); with two "
            "TAGs changed and a SIZE emptied, the dry run would change 2 and changed nothing; then the two TAGs read "
            "0060 and 0061, before_after lists both, the emptied cell's SIZE is still L. The sheet was edited with "
            "Heron's writer, not Excel; Ctrl+Z was not tried")


async def y3_a_drawing_edit_is_kept_and_a_cell_changed_twice_is_a_conflict(ctx: Context) -> str:
    await lc.save_scratch(ctx)
    start = [{"TAG": "C-01", "SIZE": "S"}, {"TAG": "C-02", "SIZE": "S"}, {"TAG": "C-03", "SIZE": "S"}]
    block, (a, b, c) = await _tagged_blocks("Y3", start)
    path = Path(parse(await attribute_sheet.autocad_export_attribute_sheet(block_name=block))["saved"])
    await _by_hand_attribute(a, "TAG", "C-01-HAND")
    await _by_hand_attribute(c, "TAG", "C-03-HAND")
    book = _read_workbook(path)
    book["Attributes"] = _edit(book["Attributes"], {(b, "TAG"): "C-02-XL", (a, "TAG"): "C-01-XL"})
    _write_workbook(path, book)
    out = parse(await attribute_sheet.autocad_apply_attribute_sheet(path=str(path)))
    changed = {(x.get("handle", "").upper(), x.get("tag")) for x in out.get("changes") or []}
    conflicts = {(x.get("handle", "").upper(), x.get("tag")) for x in out.get("conflicts") or []}
    kept = {(x.get("handle", "").upper(), x.get("tag")) for x in out.get("kept_drawing") or []}
    expect(changed == {(b.upper(), "TAG")}, f"the changes are {sorted(changed)}, not only the second block's TAG")
    expect((a.upper(), "TAG") in conflicts, f"the TAG changed in both places is not a conflict: {sorted(conflicts)}")
    expect((c.upper(), "TAG") in kept, f"the hand change Excel left is not in kept_drawing: {sorted(kept)}")
    now = await _values([a, b, c])
    tags = [now[h].get("TAG") for h in (a, b, c)]
    expect(tags == ["C-01-HAND", "C-02-XL", "C-03-HAND"], f"the TAGs read {tags}")
    return ("the hand change Excel left stayed (kept_drawing), the TAG changed in both places is in conflicts and "
            "kept its hand value, the other block took C-02-XL")


async def y4_a_folder_is_checked_read_only_and_left_as_it_was(ctx: Context) -> str:
    opened = await lc.other_drawing(ctx, "LC-Y4", "b-open.dwg")
    folder = opened.parent
    closed = folder / "a-closed.dwg"
    bad = folder / "c-bad.dwg"
    closed_name = await _closed_drawing(closed)
    _write_file(bad, b"This is not a drawing: a damaged file for the folder check.\r\n" * 8)
    await lc.activate(ctx)
    paths = (closed, opened, bad)
    before = {p.name: lc.file_stamp(p) for p in paths}
    expect(all(before.values()), f"set-up: not every file is there: {before}")
    out = parse(await check_folder.autocad_check_folder(folder=str(folder)))
    lines = {d.get("drawing"): d for d in out.get("drawings") or []}
    expect(sorted(lines) == sorted(p.name for p in paths), f"the answer lists {sorted(lines)}, not the three drawings")
    expect(lines[bad.name].get("verdict") == "NOT RUN" and lines[bad.name].get("reason"),
           f"the damaged file is {lines[bad.name].get('verdict')} with reason {lines[bad.name].get('reason')!r}")
    good = [n for n in (closed.name, opened.name) if lines[n].get("verdict") == "NOT RUN"]
    expect(not good, f"these drawings were not checked: {[(n, lines[n].get('reason')) for n in good]}")
    names = [n.lower() for n in await lc.drawing_names()]
    expect(opened.name.lower() in names, f"{opened.name}, open before, was closed")
    expect(closed_name.lower() not in names and bad.name.lower() not in names,
           f"a drawing Heron opened is still open: {names}")
    active = await _active_name()
    expect(active == ctx.scratch, f"{active} is active at the end, not the drawing the check started in")
    after = {p.name: lc.file_stamp(p) for p in paths}
    moved = [n for n in before if before[n] != after[n]]
    expect(not moved, f"these files changed size or date: {moved}")
    return (f"three drawings listed; the damaged one NOT RUN: {str(lines[bad.name]['reason'])[:80]}; the closed one "
            "was opened and closed again, the open one left open, the start drawing active at the end, no file's "
            "size or date changed. The read-only title bar was not looked at")


CHECKS_Y: tuple[Check, ...] = (
    Check("Y2", "Y", "an edited sheet writes what changed", y2_an_edited_sheet_writes_only_what_changed,
          frozenset({"publish"})),
    Check("Y3", "Y", "a drawing edit kept, a conflict listed",
          y3_a_drawing_edit_is_kept_and_a_cell_changed_twice_is_a_conflict, frozenset({"publish"})),
    Check("Y4", "Y", "a folder is checked read only", y4_a_folder_is_checked_read_only_and_left_as_it_was),
)

EYE_Y: dict[str, str] = {
    "Y1": "needs Publish off and then on within one row, and the runner never moves a padlock; Excel opening "
          "the file is seen by eye (Y2 measures the file name and sheets)",
    "Y5": "needs HERONSTOP typed during the folder check, after the first drawing",
    "Y6": "needs the companion page opened in a browser and its dev tools read by eye",
    "Y7": "needs 1:100 and a date typed in Excel itself, so Excel converts them; Heron's writer writes text only",
}


CHECKS: tuple[Check, ...] = CHECKS_AC + CHECKS_Y
BY_EYE: dict[str, str] = {**EYE_AC, **EYE_Y}
