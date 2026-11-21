"""The attribute spreadsheet round trip (D-69): export, edit, compare, apply only the changes."""

from __future__ import annotations

import asyncio
import io
import json
import zipfile

import pytest

from autocad_mcp.acad import attribute_sheet, xlsx
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import attribute_sheet as tool

REFS = [
    {"handle": "2A", "block": "CAMERA", "layout": "Model", "attributes": {"TAG": "CAM-01", "TYPE": "DOME"}},
    {"handle": "2B", "block": "CAMERA", "layout": "Model", "attributes": {"TAG": "CAM-02", "TYPE": "0050"}},
    {"handle": "3C", "block": "TB", "layout": "E-101", "attributes": {"REV": "A"}},
]


def records(rows):
    heading, *body = rows
    return [dict(zip(heading, row, strict=False)) for row in body]


def edited(changes: dict[tuple[str, str], str]) -> list[dict[str, str]]:
    rows = records(attribute_sheet.table(REFS))
    for row in rows:
        for (handle, tag), value in changes.items():
            if row["Handle"] == handle:
                row[tag] = value
    return rows


# --- the workbook --------------------------------------------------------------------


def test_the_workbook_opens_with_three_sheets_and_reads_back_as_written():
    content = attribute_sheet.workbook(REFS)
    sheets = xlsx.read(content)
    assert list(sheets) == ["Attributes", "As exported", "Read me"]
    rows = sheets["Attributes"]
    assert rows[0] == ["Handle", "Block", "Layout", "TAG", "TYPE", "REV"]
    assert rows[2] == ["2B", "CAMERA", "Model", "CAM-02", "0050", ""]  # "0050" stays text
    assert sheets["As exported"] == rows


def test_excel_shared_strings_and_numbers_are_read_the_way_excel_shows_them():
    sheet = (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>'
        '<row r="3"><c r="A3"><v>100</v></c><c r="B3"><v>1.5</v></c><c r="C3" t="inlineStr"><is><r><t>CA</t></r>'
        '<r><t>M</t></r></is></c></row></sheetData></worksheet>'
    )
    strings = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>Handle</t></si>'
               '<si><r><t>TA</t></r><r><t>G</t></r></si></sst>')  # fmt: skip
    book = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Attributes" sheetId="1" r:id="rId1"/></sheets></workbook>')  # fmt: skip
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="x" Target="/xl/worksheets/sheet1.xml"/></Relationships>')  # fmt: skip
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", book)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    rows = xlsx.read(buffer.getvalue())["Attributes"]
    assert rows == [["Handle", "", "TAG"], [], ["100", "1.5", "CAM"]]


def test_not_a_workbook_is_said_plainly():
    with pytest.raises(xlsx.SheetError, match="not an Excel .xlsx"):
        xlsx.read(b"just text")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook")
        archive.writestr("xl/_rels/workbook.xml.rels", "<x/>")
    with pytest.raises(xlsx.SheetError, match="damaged"):
        xlsx.read(buffer.getvalue())


# --- the compare -------------------------------------------------------------------------


def test_only_the_cells_the_modeller_changed_are_planned():
    sheet = edited({("2A", "TAG"): "CAM-11", ("3C", "REV"): "A"})
    planned = attribute_sheet.plan(sheet, records(attribute_sheet.table(REFS)), REFS)
    assert planned["changes"] == [
        {"handle": "2A", "block": "CAMERA", "layout": "Model", "tag": "TAG", "old": "CAM-01", "new": "CAM-11"}
    ]
    assert planned["unchanged_cells"] == 4 and planned["blank_cells"] == 4  # 2A and 2B REV, 3C TAG and TYPE


def test_a_blank_cell_changes_nothing():
    sheet = edited({("2A", "TAG"): ""})
    assert attribute_sheet.plan(sheet, None, REFS)["changes"] == []


def test_a_value_the_drawing_changed_since_the_export_is_kept():
    exported = records(attribute_sheet.table(REFS))
    now = [dict(REFS[0], attributes={"TAG": "CAM-99", "TYPE": "DOME"}), *REFS[1:]]
    planned = attribute_sheet.plan(edited({}), exported, now)
    assert planned["changes"] == []
    assert planned["kept_drawing"] == [{"handle": "2A", "tag": "TAG", "exported": "CAM-01", "drawing": "CAM-99"}]


def test_a_value_changed_in_both_places_is_a_conflict_not_a_write():
    exported = records(attribute_sheet.table(REFS))
    now = [dict(REFS[0], attributes={"TAG": "CAM-99", "TYPE": "DOME"}), *REFS[1:]]
    planned = attribute_sheet.plan(edited({("2A", "TAG"): "CAM-11"}), exported, now)
    assert planned["changes"] == []
    assert planned["conflicts"][0]["drawing"] == "CAM-99" and planned["conflicts"][0]["sheet"] == "CAM-11"


def test_a_gone_block_and_an_unknown_tag_are_listed_and_the_rest_still_planned():
    sheet = edited({("3C", "TAG"): "X", ("2B", "TYPE"): "BULLET"})
    sheet.append({"Handle": "FF", "Block": "CAMERA", "Layout": "Model", "TAG": "CAM-9"})
    planned = attribute_sheet.plan(sheet, None, REFS)
    assert planned["missing_handles"] == ["FF"]
    assert planned["unknown_tags"] == [{"handle": "3C", "column": "TAG"}]
    assert [c["new"] for c in planned["changes"]] == ["BULLET"]


def test_no_handle_column_or_a_handle_twice_is_refused():
    with pytest.raises(ValueError, match="no Handle column"):
        attribute_sheet.read_csv("TAG,TYPE\nCAM-01,DOME\n")
    twice = edited({}) + [{"Handle": "2a", "TAG": "X"}]
    with pytest.raises(ValueError, match="twice"):
        attribute_sheet.plan(twice, None, REFS)


def test_a_semicolon_csv_from_a_european_excel_is_read():
    rows = attribute_sheet.read_csv("Handle;TAG\n2A;CAM-07\n")
    assert attribute_sheet.plan(rows, None, REFS)["changes"][0]["new"] == "CAM-07"


# --- the tools -----------------------------------------------------------------------------


class Att:
    def __init__(self, tag, text):
        self.TagString, self.TextString = tag, text


class Ref:
    def __init__(self, ref):
        self.atts = [Att(t, v) for t, v in ref["attributes"].items()]

    def GetAttributes(self):
        return self.atts

    def Update(self):
        pass


class Doc:
    def __init__(self, path):
        self.FullName = path
        self.groups = 0

    def StartUndoMark(self):
        self.groups += 1

    def EndUndoMark(self):
        pass


@pytest.fixture
def drawing(monkeypatch, tmp_path):
    doc = Doc(str(tmp_path / "M-101.dwg"))
    objects = {ref["handle"]: Ref(ref) for ref in REFS}

    def refs(d, block_name, layer):
        now = [dict(ref, attributes={a.TagString: a.TextString for a in objects[ref["handle"]].atts}) for ref in REFS]
        return [r for r in now if not block_name or r["block"] == block_name], objects

    async def now(fn):
        return fn()

    monkeypatch.setattr(tool, "run", now)
    monkeypatch.setattr(tool, "get_doc", lambda: doc)
    monkeypatch.setattr(tool, "require_idle", lambda d: None)
    monkeypatch.setattr(tool, "_attribute_refs", refs)
    return doc, objects, tmp_path


def test_export_writes_a_new_workbook_next_to_the_drawing_and_never_over_one(drawing):
    _, _, folder = drawing
    first = json.loads(asyncio.run(tool.autocad_export_attribute_sheet()))
    second = json.loads(asyncio.run(tool.autocad_export_attribute_sheet(block_name="CAMERA")))
    assert first["saved"].startswith(str(folder / "M-101 - attributes - ")) and first["blocks"] == 3
    assert second["saved"].endswith(" (2).xlsx") and second["blocks"] == 2


def test_edit_and_apply_writes_only_the_changed_cells_in_one_undo_step(drawing):
    doc, objects, folder = drawing
    saved = json.loads(asyncio.run(tool.autocad_export_attribute_sheet()))["saved"]
    sheets = xlsx.read(open(saved, "rb").read())
    rows = sheets["Attributes"]
    rows[1][3] = "CAM-11"  # 2A TAG
    edited_book = xlsx.write([("Attributes", rows, None), ("As exported", sheets["As exported"], None)])
    (folder / "edited.xlsx").write_bytes(edited_book)

    preview = json.loads(asyncio.run(tool.autocad_apply_attribute_sheet(path="edited.xlsx", dry_run=True)))
    assert preview["would_change"] == 1 and doc.groups == 0
    assert objects["2A"].atts[0].TextString == "CAM-01"

    done = json.loads(asyncio.run(tool.autocad_apply_attribute_sheet(path="edited.xlsx")))
    assert done["changed"] == 1 and doc.groups == 1
    assert done["before_after"] == [{"handle": "2A", "property": "attribute TAG", "from": "CAM-01", "to": "CAM-11"}]
    assert objects["2A"].atts[0].TextString == "CAM-11"

    again = json.loads(asyncio.run(tool.autocad_apply_attribute_sheet(path="edited.xlsx")))
    assert again["changed"] == 0 and again["before_after"] == [] and doc.groups == 1  # no empty undo step


def test_a_wrong_file_is_refused_before_anything_is_read(drawing):
    _, _, folder = drawing
    (folder / "notes.txt").write_text("x")
    with pytest.raises(AutocadError, match="not an .xlsx or .csv"):
        tool.sheet_path("notes.txt", str(folder / "M-101.dwg"))
    with pytest.raises(AutocadError, match="There is no file"):
        tool.sheet_path("missing.xlsx", str(folder / "M-101.dwg"))
    result = asyncio.run(tool.autocad_apply_attribute_sheet(path="missing.xlsx"))
    assert result.startswith("Error: There is no file")


def test_levels():
    from autocad_mcp.core.risk import Risk, risk_of

    assert risk_of("autocad_export_attribute_sheet") is Risk.PUBLISH
    assert risk_of("autocad_apply_attribute_sheet") is Risk.CHANGE


# --- found in review (2026-11-21) -------------------------------------------------------


def _excel_edit(refs, edits):
    """The exported workbook re-saved by a spreadsheet program after these typed edits."""
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.load_workbook(io.BytesIO(attribute_sheet.workbook(refs)))
    sheet = book["Attributes"]
    for cell, value, number_format in edits:
        sheet[cell] = value
        if number_format:
            sheet[cell].number_format = number_format
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_a_value_excel_turned_into_a_date_time_or_percent_is_never_written():
    import datetime

    refs = [{"handle": "2A", "block": "TB", "layout": "E-101", "attributes": {"SCALE": "1:50", "DATE": "05.01.2026", "FILL": "x"}}]
    content = _excel_edit(refs, [("D2", datetime.time(1, 0), "h:mm"), ("E2", datetime.date(2026, 3, 15), None),
                                 ("F2", 0.5, "0%")])  # fmt: skip
    edited, exported = attribute_sheet.read_workbook(content)
    planned = attribute_sheet.plan(edited, exported, refs)
    assert planned["changes"] == []
    assert {c["tag"]: c["excel_made_it"] for c in planned["excel_converted"]} == {
        "SCALE": "date or time", "DATE": "date or time", "FILL": "percent"}


def test_a_plain_typed_number_is_still_written():
    refs = [{"handle": "2A", "block": "PUMP", "layout": "Model", "attributes": {"FLOW": "10"}}]
    edited, exported = attribute_sheet.read_workbook(_excel_edit(refs, [("D2", 12, None)]))
    assert attribute_sheet.plan(edited, exported, refs)["changes"][0]["new"] == "12"


def test_a_tag_named_handle_block_or_layout_keeps_its_own_column():
    refs = [{"handle": "2A", "block": "TB", "layout": "E-101", "attributes": {"BLOCK": "A", "HANDLE": "H1"}},
            {"handle": "2B", "block": "TB", "layout": "E-102", "attributes": {"BLOCK": "B"}}]  # fmt: skip
    rows = attribute_sheet.table(refs)
    assert rows[0] == ["Handle", "Block", "Layout", "BLOCK (tag)", "HANDLE (tag)"]
    sheets = xlsx.read(attribute_sheet.workbook(refs))
    sheets["Attributes"][1][3] = "C"  # 2A's BLOCK tag
    edited, exported = attribute_sheet.read_workbook(
        xlsx.write([("Attributes", sheets["Attributes"], None), ("As exported", sheets["As exported"], None)])
    )
    planned = attribute_sheet.plan(edited, exported, refs)
    assert planned["changes"] == [{"handle": "2A", "block": "TB", "layout": "E-101", "tag": "BLOCK", "old": "A", "new": "C"}]
    assert planned["missing_handles"] == [] and planned["rows_without_handle"] == []


def test_a_row_whose_block_is_another_block_here_is_not_used():
    sheet = edited({("2A", "TAG"): "CAM-11"})
    sheet[0]["Block"] = "VALVE"
    planned = attribute_sheet.plan(sheet, None, REFS)
    assert planned["changes"] == []
    assert planned["other_block"] == [{"handle": "2A", "sheet": "VALVE", "drawing": "CAMERA"}]


def test_a_row_with_values_but_no_handle_is_said():
    sheet = edited({})
    sheet.append({"Handle": "", "Block": "CAMERA", "TAG": "CAM-77"})
    assert attribute_sheet.plan(sheet, None, REFS)["rows_without_handle"] == [5]


def test_the_workbook_names_its_drawing_and_a_cell_without_a_column_letter_is_read():
    content = attribute_sheet.workbook(REFS, r"C:\Jobs\M-101.dwg")
    assert attribute_sheet.source_of(content) == r"C:\Jobs\M-101.dwg"
    assert attribute_sheet.source_of(attribute_sheet.workbook(REFS)) == ""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                         '<sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')  # fmt: skip
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/></Relationships>')  # fmt: skip
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                         '<sheetData><row r="1"><c r="1" t="inlineStr"><is><t>x</t></is></c></row>'
                         '<row r="999999999"><c r="A999999999"><v>1</v></c></row></sheetData></worksheet>')  # fmt: skip
    with pytest.raises(xlsx.SheetError, match="more than"):
        xlsx.read(buffer.getvalue())


def test_apply_warns_when_the_sheet_came_from_another_drawing(drawing):
    doc, objects, folder = drawing
    rows = attribute_sheet.table(REFS)
    rows[1][3] = "CAM-11"
    book = xlsx.write([("Attributes", rows, None), ("As exported", attribute_sheet.table(REFS), None),
                       ("Read me", [["Exported from", r"C:\Other\X-200.dwg"]], None)])  # fmt: skip
    (folder / "other.xlsx").write_bytes(book)
    done = json.loads(asyncio.run(tool.autocad_apply_attribute_sheet(path="other.xlsx", dry_run=True)))
    assert "X-200.dwg" in done["warning"]


def test_excel_number_formats_are_read_without_any_package():
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    styles = (f'<styleSheet xmlns="{main}"><numFmts count="2"><numFmt numFmtId="164" formatCode="h:mm"/>'
              '<numFmt numFmtId="165" formatCode="0.00 &quot;mm&quot;"/></numFmts>'
              '<cellXfs count="5"><xf numFmtId="0"/><xf numFmtId="14"/><xf numFmtId="164"/><xf numFmtId="9"/>'
              '<xf numFmtId="165"/></cellXfs></styleSheet>')  # fmt: skip
    sheet = (f'<worksheet xmlns="{main}"><sheetData><row r="1">'
             '<c r="A1"><v>12</v></c><c r="B1" s="1"><v>46096</v></c><c r="C1" s="2"><v>0.0416666666666667</v></c>'
             '<c r="D1" s="3"><v>0.5</v></c><c r="E1" s="4"><v>25</v></c></row></sheetData></worksheet>')  # fmt: skip
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{main}" xmlns:r="http://schemas.openxmlformats.org/'
                         'officeDocument/2006/relationships"><sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')  # fmt: skip
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                         'relationships"><Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/></Relationships>')  # fmt: skip
        archive.writestr("xl/styles.xml", styles)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    plain, date, time, percent, millimetres = xlsx.read(buffer.getvalue())["S"][0]
    assert not isinstance(plain, xlsx.Converted) and plain == "12"
    assert date.shown_as == "date or time" and time.shown_as == "date or time" and percent.shown_as == "percent"
    assert not isinstance(millimetres, xlsx.Converted)  # "mm" in quotes is a label, not minutes
