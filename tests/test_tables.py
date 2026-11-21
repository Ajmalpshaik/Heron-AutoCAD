"""Tables from Excel and table cell edits (D-83, issue #117), without AutoCAD.

What is checked: the cell grid a sheet range gives, the numbering of cell
edits, the vertical-middle rule, what autocad_table_from_excel asks the
plug-in for and how it falls back to a filled table, and what
autocad_set_table_cells writes, skips and refuses.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad import table_cells, xlsx
from autocad_mcp.acad.table_cells import (
    CellError,
    grid_from_sheet,
    locked_reason,
    middle_of,
    middle_rows,
    parse_address,
    parse_range,
    plan_cell_edits,
    table_layout,
    used_range,
)
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import annotate, tables

SHEET = [
    ["PUMP SCHEDULE"],
    [],
    ["TAG", "FLOW", "HEAD", "MOTOR"],
    ["P-01", "12.5", "30", "7.5 kW"],
    ["P-02", "8", "25"],
]


# ---------------------------------------------------------------------------
# Ranges and the grid
# ---------------------------------------------------------------------------


class TestAddresses:
    @pytest.mark.parametrize(("text", "cell"), [("A1", (0, 0)), ("b3", (2, 1)), ("$AA$10", (9, 26))])
    def test_an_address_counts_like_excel(self, text, cell):
        assert parse_address(text) == cell

    @pytest.mark.parametrize("text", ["3B", "B", "B0", "", "B3:"])
    def test_a_bad_address_is_refused_plainly(self, text):
        with pytest.raises(CellError):
            parse_range(text)

    def test_a_range_in_any_corner_order(self):
        assert parse_range("D20:A1") == (0, 0, 19, 3)

    def test_one_cell_is_a_range_of_one(self):
        assert parse_range("C4") == (3, 2, 3, 2)


class TestGridFromSheet:
    def test_with_no_range_the_used_cells_are_taken(self):
        planned = grid_from_sheet(SHEET)
        assert planned["range"] == "A1:D5" and (planned["rows"], planned["columns"]) == (5, 4)

    def test_every_row_has_the_same_number_of_cells(self):
        planned = grid_from_sheet(SHEET, "A3:D5")
        assert planned["grid"] == [
            ["TAG", "FLOW", "HEAD", "MOTOR"],
            ["P-01", "12.5", "30", "7.5 kW"],
            ["P-02", "8", "25", ""],
        ]

    def test_a_range_past_the_data_is_padded_not_refused(self):
        planned = grid_from_sheet(SHEET, "C5:E6")
        assert planned["grid"] == [["25", "", ""], ["", "", ""]]

    def test_a_cell_excel_only_shows_as_a_date_is_left_empty_and_listed(self):
        rows = [["TAG", "INSTALLED"], ["P-01", xlsx.Converted("46000", "date or time")]]
        planned = grid_from_sheet(rows)
        assert planned["grid"][1] == ["P-01", ""]
        assert planned["converted"] == [{"cell": "B2", "shown_as": "date or time", "number": "46000"}]

    def test_an_empty_sheet_or_range_is_refused(self):
        with pytest.raises(CellError, match="empty"):
            grid_from_sheet([[], [""]])
        with pytest.raises(CellError, match="nothing in it"):
            grid_from_sheet(SHEET, "F1:G2")

    def test_a_range_too_big_for_a_drawing_table_is_refused(self):
        with pytest.raises(CellError, match="too big"):
            grid_from_sheet(SHEET, "A1:AZ10")  # 52 columns
        with pytest.raises(CellError, match="too big"):
            grid_from_sheet(SHEET, f"A1:A{table_cells.MOST_ROWS + 1}")

    def test_the_used_range_starts_where_the_data_starts(self):
        assert used_range([[], ["", "", "x"], ["", "y"]]) == (1, 1, 2, 2)


class TestLayout:
    def test_a_title_goes_first_then_the_sheet(self):
        assert table_layout(3, title=True, header=True) == {"title_rows": 1, "header_rows": 1, "total_rows": 4, "first_sheet_row": 1}

    def test_no_title_and_no_header(self):
        assert table_layout(3, title=False, header=False) == {"title_rows": 0, "header_rows": 0, "total_rows": 3, "first_sheet_row": 0}


class TestMiddle:
    @pytest.mark.parametrize(("now", "middle"), [(1, 4), (2, 5), (3, 6), (4, 4), (5, 5), (6, 6), (7, 4), (8, 5), (9, 6)])
    def test_left_centre_right_kept_in_the_vertical_middle(self, now, middle):
        assert middle_of(now) == middle

    @pytest.mark.parametrize("now", [0, 10, None, "x"])
    def test_anything_else_is_middle_centre(self, now):
        assert middle_of(now) == 5

    def test_each_row_type_is_set_once(self):
        class Table:
            def __init__(self):
                self.set = []

            def GetAlignment(self, row_type):
                return {2: 2, 4: 2, 1: 1}[row_type]  # title / header top centre, data top left

            def SetAlignment(self, row_types, alignment):
                self.set.append((row_types, alignment))

        table = Table()
        assert middle_rows(table) == 3
        assert table.set == [(2, 5), (4, 5), (1, 4)]

    def test_a_table_that_refuses_keeps_its_own(self):
        assert middle_rows(object()) == 0


class TestCellEdits:
    def test_cell_and_row_column_count_the_same_way(self):
        plan = plan_cell_edits([{"cell": "B3", "value": "a"}, {"row": 4, "column": 2, "value": "b"}], 5, 4)
        assert [(e["row"], e["column"], e["cell"]) for e in plan["edits"]] == [(2, 1, "B3"), (3, 1, "B4")]

    def test_the_same_cell_twice_is_refused(self):
        with pytest.raises(CellError, match="twice"):
            plan_cell_edits([{"cell": "B3", "value": "a"}, {"row": 3, "column": 2, "value": "b"}], 5, 4)

    def test_outside_the_table_is_refused_without_grow(self):
        with pytest.raises(CellError, match="grow=true"):
            plan_cell_edits([{"cell": "A7", "value": "P-05"}], 5, 4)

    def test_grow_says_how_many_rows_and_columns_to_add(self):
        plan = plan_cell_edits([{"cell": "A7", "value": "P-05"}, {"cell": "F6", "value": "x"}], 5, 4, grow=True)
        assert (plan["add_rows"], plan["add_columns"]) == (2, 2)

    def test_a_value_is_needed_and_none_empties(self):
        with pytest.raises(CellError, match="no value"):
            plan_cell_edits([{"cell": "A1"}], 5, 4)
        assert plan_cell_edits([{"cell": "A1", "value": None}], 5, 4)["edits"][0]["value"] == ""

    @pytest.mark.parametrize("spec", [{"row": 0, "column": 1, "value": "x"}, {"row": "a", "column": 1, "value": "x"}, {"value": "x"}])
    def test_rows_and_columns_count_from_one(self, spec):
        with pytest.raises(CellError):
            plan_cell_edits([spec], 5, 4)

    def test_edits_are_written_top_left_first(self):
        plan = plan_cell_edits([{"cell": "C2", "value": "1"}, {"cell": "A2", "value": "2"}, {"cell": "B1", "value": "3"}], 5, 4)
        assert [e["cell"] for e in plan["edits"]] == ["B1", "A2", "C2"]


class TestLockedCells:
    def test_a_linked_cell_says_to_change_the_sheet(self):
        assert "autocad_update_table_links" in locked_reason(16)

    def test_a_locked_cell_says_so(self):
        assert "locked" in locked_reason(1)

    @pytest.mark.parametrize("state", [0, 4, None])
    def test_other_states_can_be_written(self, state):
        assert locked_reason(state) is None


# ---------------------------------------------------------------------------
# The tools against a fake drawing
# ---------------------------------------------------------------------------


class FakeTable:
    def __init__(self, rows=3, columns=3, texts=None, states=None, merged=None):
        self.Handle, self.Layer, self.ObjectName = "2F", "0", "AcDbTable"
        self.Rows, self.Columns = rows, columns
        self.texts = dict(texts or {})
        self.states = dict(states or {})
        self.merged = dict(merged or {})
        self.calls = []
        self.RegenerateTableSuppressed = False
        self.TitleSuppressed = self.HeaderSuppressed = False
        self.StyleName = "Standard"

    def GetText(self, r, c):
        return self.texts.get((r, c), "")

    def SetText(self, r, c, value):
        self.texts[(r, c)] = value
        self.calls.append(("SetText", r, c, value))

    def GetCellState(self, r, c):
        return self.states.get((r, c), 0)

    def IsMergedCell(self, r, c):
        return self.merged.get((r, c), (False, 0, 0, 0, 0))

    def GetCellAlignment(self, r, c):
        return 1

    def SetCellAlignment(self, r, c, alignment):
        self.calls.append(("SetCellAlignment", r, c, alignment))

    def GetAlignment(self, row_type):
        return 2

    def SetAlignment(self, row_types, alignment):
        self.calls.append(("SetAlignment", row_types, alignment))

    def GetRowHeight(self, r):
        return 10.0

    def GetTextHeight(self, row_type):
        return 100.0  # a 1:40 drawing's table style

    def GetColumnWidth(self, c):
        return 60.0

    def InsertRows(self, at, height, count):
        self.calls.append(("InsertRows", at, height, count))
        self.Rows += count

    def InsertColumns(self, at, width, count):
        self.calls.append(("InsertColumns", at, width, count))
        self.Columns += count

    def SetColumnWidth(self, index, width):
        self.calls.append(("SetColumnWidth", index, width))

    def SetTextHeight(self, row_types, height):
        self.calls.append(("SetTextHeight", row_types, height))


class FakeSpace:
    def __init__(self):
        self.added = []

    def AddTable(self, at, rows, columns, row_height, column_width):
        table = FakeTable(rows, columns)
        self.added.append((rows, columns, row_height, column_width))
        self.table = table
        return table


class FakeDoc:
    def __init__(self, full_name="D:/jobs/plan.dwg", table=None):
        self.FullName = full_name
        self.ModelSpace = self.PaperSpace = FakeSpace()
        self.table = table

    def HandleToObject(self, handle):
        return self.table

    def GetVariable(self, name):
        return (0.0, 0.0, 0.0)

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def env(monkeypatch):
    state = {}

    def make(**kw):
        doc = FakeDoc(**kw)

        async def run(fn):
            return fn()

        monkeypatch.setattr(tables, "run", run)
        monkeypatch.setattr(tables, "get_doc", lambda: doc)
        monkeypatch.setattr(tables, "require_idle", lambda d: None)
        monkeypatch.setattr(tables, "apply_properties", lambda d, e, layer, aci, lt: {})
        monkeypatch.setattr(tables, "ensure_layer", lambda d, name: (None, False))
        monkeypatch.setattr(tables, "resolve_handle", lambda d, h: d.HandleToObject(h))
        state["doc"] = doc
        return doc

    return make


def answer(coroutine) -> dict:
    text = asyncio.run(coroutine)
    assert not text.startswith("Error:"), text
    return json.loads(text)


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "pumps.xlsx"
    path.write_bytes(xlsx.write([("Pumps", [["TAG", "FLOW"], ["P-01", "12.5"], ["P-02", "8"]], None), ("Other", [["x"]], None)]))
    return path


class TestTableFromExcel:
    def test_a_dry_run_reads_the_sheet_and_makes_nothing(self, env, workbook, monkeypatch):
        doc = env()
        sent = []
        monkeypatch.setattr(tables, "in_plugin", lambda *a, **k: sent.append(a))
        result = answer(tables.autocad_table_from_excel(path=str(workbook), position=[0, 0], dry_run=True))
        assert result["dry_run"] is True and result["would"] == "link"
        assert result["sheet"] == "Pumps" and result["range"] == "A1:B3"
        assert result["first_rows"][0] == ["TAG", "FLOW"]
        assert sent == [] and doc.ModelSpace.added == []

    def test_the_link_is_asked_of_the_plug_in_with_the_sheet_and_range(self, env, workbook, monkeypatch):
        env()
        sent = []

        def plugin(operation, args, what, **kw):
            sent.append((operation, args))
            return {"created": True, "handle": "3A", "link": "Heron pumps Pumps A1:B3"}

        monkeypatch.setattr(tables, "in_plugin", plugin)
        result = answer(tables.autocad_table_from_excel(path=str(workbook), position=[100, 200], space="paper", cell_range="A1:B3"))
        ((operation, args),) = sent
        assert operation == "excel_table"
        assert args["sheet"] == "Pumps" and args["range"] == "A1:B3" and args["space"] == "paper"
        assert args["position"] == [100.0, 200.0, 0.0] and args["path"].endswith("pumps.xlsx")
        assert result["linked"] is True and result["handle"] == "3A"

    def test_the_sheet_is_found_by_name_whatever_the_case(self, env, workbook, monkeypatch):
        env()
        monkeypatch.setattr(tables, "in_plugin", lambda *a, **k: {"handle": "3A"})
        assert answer(tables.autocad_table_from_excel(path=str(workbook), position=[0, 0], sheet="other"))["sheet"] == "Other"

    def test_when_the_link_is_refused_the_table_is_filled_and_says_why(self, env, workbook, monkeypatch):
        doc = env()

        def refuse(*a, **k):
            raise AutocadError("Heron in AutoCAD does not have the operation 'excel_table'. Update Heron so both sides match.")

        monkeypatch.setattr(tables, "in_plugin", refuse)
        result = answer(tables.autocad_table_from_excel(path=str(workbook), position=[0, 0], title="PUMPS", text_height=25))
        assert result["linked"] is False and "excel_table" in result["not_linked_because"]
        assert "will not update by itself" in result["note"]
        table = doc.ModelSpace.table
        assert doc.ModelSpace.added[0][:2] == (4, 2)  # the title row and the three sheet rows
        assert table.texts[(0, 0)] == "PUMPS" and table.texts[(1, 0)] == "TAG" and table.texts[(3, 1)] == "8"
        assert ("SetAlignment", 2, 5) in table.calls and ("SetTextHeight", 7, 25.0) in table.calls
        assert table.TitleSuppressed is False

    def test_no_title_suppresses_the_title_row(self, env, workbook, monkeypatch):
        doc = env()
        result = answer(tables.autocad_table_from_excel(path=str(workbook), position=[0, 0], link=False))
        assert result["not_linked_because"] == "link=false was asked for"
        assert doc.ModelSpace.table.TitleSuppressed is True and doc.ModelSpace.table.texts[(0, 0)] == "TAG"

    def test_columns_fit_the_text_at_the_table_styles_own_height(self, env, workbook):
        doc = env()
        answer(tables.autocad_table_from_excel(path=str(workbook), position=[0, 0], link=False))
        widths = [c[2] for c in doc.ModelSpace.table.calls if c[0] == "SetColumnWidth"]
        assert widths == tables.column_widths_for([["TAG", "FLOW"], ["P-01", "12.5"], ["P-02", "8"]], 100.0)
        assert min(widths) > 600  # not sized for a 5-unit text

    def test_outcome_unknown_is_never_followed_by_a_second_table(self, env, workbook, monkeypatch):
        doc = env()

        def unknown(*a, **k):
            raise AutocadError("Outcome unknown: Heron in AutoCAD did not answer within 120 s.")

        monkeypatch.setattr(tables, "in_plugin", unknown)
        text = asyncio.run(tables.autocad_table_from_excel(path=str(workbook), position=[0, 0]))
        assert text.startswith("Error: Outcome unknown") and doc.ModelSpace.added == []

    def test_a_csv_is_filled_not_linked(self, env, tmp_path, monkeypatch):
        doc = env()
        path = tmp_path / "fans.csv"
        path.write_text("TAG,FLOW\nF-01,2.5\n", encoding="utf-8")
        sent = []
        monkeypatch.setattr(tables, "in_plugin", lambda *a, **k: sent.append(a))
        result = answer(tables.autocad_table_from_excel(path=str(path), position=[0, 0]))
        assert sent == [] and result["linked"] is False and ".csv" in result["not_linked_because"]
        assert doc.ModelSpace.table.texts[(1, 0)] == "F-01"

    def test_a_missing_sheet_names_the_ones_there(self, env, workbook):
        env()
        text = asyncio.run(tables.autocad_table_from_excel(path=str(workbook), position=[0, 0], sheet="Fans"))
        assert text.startswith("Error:") and "Pumps, Other" in text

    def test_a_file_name_alone_is_looked_for_beside_the_drawing(self, env, workbook, monkeypatch):
        env(full_name=str(workbook.parent / "plan.dwg"))
        monkeypatch.setattr(tables, "in_plugin", lambda *a, **k: {"handle": "3A"})
        assert answer(tables.autocad_table_from_excel(path="pumps.xlsx", position=[0, 0], dry_run=True))["rows"] == 3


class TestUpdateLinks:
    def test_it_asks_the_plug_in_for_the_tables_given_or_all(self, env, monkeypatch):
        env()
        sent = []
        monkeypatch.setattr(tables, "in_plugin", lambda op, args, what, **k: sent.append((op, args)) or {"updated": []})
        answer(tables.autocad_update_table_links())
        answer(tables.autocad_update_table_links(handles=[" 3A "]))
        assert sent == [("update_table_links", {"handles": None}), ("update_table_links", {"handles": ["3A"]})]


class TestSetTableCells:
    def test_only_changed_cells_are_written_old_to_new_in_the_middle(self, env):
        table = FakeTable(rows=5, columns=4, texts={(2, 1): "12.5", (3, 1): "8"})
        env(table=table)
        result = answer(tables.autocad_set_table_cells(handle="2F", cells=[{"cell": "B3", "value": "14"}, {"cell": "B4", "value": "8"}]))
        assert result["changed"] == 1 and result["unchanged"] == ["B4"]
        assert result["before_after"] == [{"handle": "2F", "property": "cell B3", "from": "12.5", "to": "14"}]
        assert ("SetText", 2, 1, "14") in table.calls and ("SetCellAlignment", 2, 1, 4) in table.calls

    def test_a_case_change_is_a_change(self, env):
        table = FakeTable(texts={(0, 0): "dn50"})
        env(table=table)
        assert answer(tables.autocad_set_table_cells(handle="2F", cells=[{"cell": "A1", "value": "DN50"}]))["changed"] == 1

    def test_linked_locked_and_merged_cells_are_listed_and_left_alone(self, env):
        table = FakeTable(states={(1, 0): 16, (1, 1): 1}, merged={(0, 1): (True, 0, 0, 0, 2)})
        env(table=table)
        result = answer(tables.autocad_set_table_cells(
            handle="2F", cells=[{"cell": "A2", "value": "x"}, {"cell": "B2", "value": "y"}, {"cell": "B1", "value": "z"}],
        ))  # fmt: skip
        why = {r["cell"]: r["why"] for r in result["refused"]}
        assert "Excel" in why["A2"] and "locked" in why["B2"] and "merged" in why["B1"]
        assert result["changed"] == 0 and not [c for c in table.calls if c[0] == "SetText"]

    def test_a_dry_run_lists_the_changes_and_writes_nothing(self, env):
        table = FakeTable(texts={(0, 0): "A"})
        env(table=table)
        result = answer(tables.autocad_set_table_cells(handle="2F", cells=[{"cell": "A1", "value": "B"}], dry_run=True))
        assert result["would_change"] == 1 and result["before_after"][0]["to"] == "B"
        assert table.calls == []

    def test_grow_adds_rows_at_the_end_first(self, env):
        table = FakeTable(rows=3, columns=2)
        env(table=table)
        result = answer(tables.autocad_set_table_cells(handle="2F", cells=[{"cell": "A5", "value": "P-05"}], grow=True))
        assert table.calls[0] == ("InsertRows", 3, 10.0, 2)
        assert result["added_rows"] == 2 and result["changed"] == 1

    def test_outside_without_grow_is_refused_before_anything(self, env):
        table = FakeTable(rows=3, columns=2)
        env(table=table)
        text = asyncio.run(tables.autocad_set_table_cells(handle="2F", cells=[{"cell": "A5", "value": "P-05"}]))
        assert text.startswith("Error:") and "grow=true" in text and table.calls == []

    def test_a_handle_that_is_not_a_table_is_refused(self, env):
        table = FakeTable()
        table.ObjectName = "AcDbLine"
        env(table=table)
        text = asyncio.run(tables.autocad_set_table_cells(handle="2F", cells=[{"cell": "A1", "value": "x"}]))
        assert text.startswith("Error:") and "not a table" in text


class TestAddTableKeepsTheRule:
    def test_add_table_puts_every_row_type_in_the_vertical_middle(self, monkeypatch):
        space = FakeSpace()
        doc = FakeDoc()
        doc.ModelSpace = space

        async def run(fn):
            return fn()

        monkeypatch.setattr(annotate, "run", run)
        monkeypatch.setattr(annotate, "get_doc", lambda: doc)
        monkeypatch.setattr(annotate, "require_idle", lambda d: None)
        result = answer(annotate.autocad_add_table(position=[0, 0], rows=[["A", "B"]], headers=["X", "Y"], title="T"))
        assert result["rows_aligned_middle"] == 3
        assert [c for c in space.table.calls if c[0] == "SetAlignment"] == [("SetAlignment", 2, 5), ("SetAlignment", 4, 5), ("SetAlignment", 1, 5)]


    def test_no_title_makes_the_title_row_an_ordinary_row(self, monkeypatch):
        space = FakeSpace()
        doc = FakeDoc()
        doc.ModelSpace = space

        async def run(fn):
            return fn()

        monkeypatch.setattr(annotate, "run", run)
        monkeypatch.setattr(annotate, "get_doc", lambda: doc)
        monkeypatch.setattr(annotate, "require_idle", lambda d: None)
        result = answer(annotate.autocad_add_table(position=[0, 0], rows=[["P-01", "12"]], headers=["TAG", "FLOW"]))
        assert space.table.TitleSuppressed is True and space.table.HeaderSuppressed is False
        assert result["suppressed"] == ["TitleSuppressed"]
        assert space.table.texts[(0, 0)] == "TAG" and space.table.texts[(0, 1)] == "FLOW"


def test_levels():
    for tool in ("autocad_table_from_excel", "autocad_update_table_links", "autocad_set_table_cells", "autocad_add_table"):
        assert risk_of(tool) is Risk.CHANGE, tool
