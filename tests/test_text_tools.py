"""Text tools: plain text from MText, tag numbering, attribute updates, counting, replace, align.

Ideas from Lee Mac's UnFormat String, Incremental Numbering Suite, Batch Attribute
Editor, Text Counter, Batch Find & Replace and Align Text (lee-mac.com),
written fresh for Heron.
"""

from __future__ import annotations

import pytest

from autocad_mcp.acad.text import unformat
from autocad_mcp.tools import text_tools as t


def test_unformat_strips_codes_and_keeps_words():
    raw = r"{\fArial|b1;\H2.5;\C1;PUMP} \LP-01\l\PDN50 \S1^2; \{x\} a\\b\~c"
    assert unformat(raw) == "PUMP P-01 DN50 1/2 {x} a\\b c"
    assert unformat(raw, keep_paragraphs=True) == "PUMP P-01\\PDN50 1/2 {x} a\\b c"


def test_number_labels_with_pad_prefix_suffix():
    assert t.number_labels(3, start=8, step=2, prefix="CAM-", suffix="A", pad=3) == ["CAM-008A", "CAM-010A", "CAM-012A"]


def test_order_by_rows_then_columns_and_by_x():
    pts = {"a": (0, 0), "b": (10, 10), "c": (0, 10), "d": (10, 0)}
    assert t.order_points(pts, "rows") == ["c", "b", "a", "d"]
    assert t.order_points(pts, "columns") == ["c", "a", "b", "d"]


def test_order_along_a_run():
    pts = {"far": (10, 8), "near": (2, -1), "mid": (10, 1)}
    path = {"vertices": [(0, 0), (10, 0), (10, 10)], "bulges": [0, 0], "closed": False}
    assert t.order_points(pts, "path", path) == ["near", "mid", "far"]


REFS = [
    {"handle": "1", "block": "TITLE", "layout": "A-101", "attributes": {"SHEET": "A-101", "TITLE": "", "REV": "0"}},
    {"handle": "2", "block": "TITLE", "layout": "A-102", "attributes": {"SHEET": "A-102", "TITLE": "", "REV": "0"}},
]


def test_attribute_plan_from_values():
    plan = t.plan_attributes(REFS, values={"rev": "1"})
    assert [(c["handle"], c["tag"], c["old"], c["new"]) for c in plan["changes"]] == [("1", "REV", "0", "1"), ("2", "REV", "0", "1")]


def test_attribute_plan_from_rows_by_key_tag_or_layout():
    rows = [{"SHEET": "A-102", "TITLE": "SECOND FLOOR", "NOPE": "x"}]
    plan = t.plan_attributes(REFS, rows=rows, key="SHEET")
    assert [(c["handle"], c["tag"], c["new"]) for c in plan["changes"]] == [("2", "TITLE", "SECOND FLOOR")]
    assert plan["unknown_tags"] == ["NOPE"] and plan["unmatched_rows"] == []
    plan = t.plan_attributes(REFS, rows=[{"layout": "A-101", "TITLE": "GROUND"}, {"layout": "Z", "TITLE": "?"}], key="layout")
    assert [(c["handle"], c["new"]) for c in plan["changes"]] == [("1", "GROUND")]
    assert plan["unmatched_rows"] == ["Z"]



@pytest.mark.parametrize(("content", "title"), [
    ("SHEET;TITLE\r\nA-102;\"FIRST; SECOND FLOOR\"\r\n".encode("utf-8-sig"), "FIRST; SECOND FLOOR"),
    ("SHEET;TITLE\r\nA-102;CAFÉ 1,5\r\n".encode("cp1252"), "CAFÉ 1,5"),  # Excel's CSV on a Western PC
    (b"SHEET\tTITLE\nA-102\tSECOND FLOOR\n", "SECOND FLOOR"),
    (b"SHEET,TITLE\nA-102,SECOND FLOOR\n", "SECOND FLOOR"),
], ids=["semicolon", "cp1252", "tab", "comma"])
def test_set_attributes_csv_reads_a_semicolon_or_cp1252_file_as_the_table_tool_does(tmp_path, content, title):
    """#259: Excel on a European PC saves a semicolon CSV; it was read as one column, so no row matched."""
    path = tmp_path / "sheets.csv"
    path.write_bytes(content)
    rows = t._read_rows(str(path))
    assert rows == [{"SHEET": "A-102", "TITLE": title}]
    plan = t.plan_attributes(REFS, rows=rows, key="SHEET")
    assert [(c["handle"], c["tag"], c["new"]) for c in plan["changes"]] == [("2", "TITLE", title)]
    assert plan["unknown_tags"] == []

def test_tally_counts_and_sums():
    report = t.tally([r"{\H2;DN50}", "dn50", "DN80", "3.5 kW", "2 kW"], normalise=True, sum_numeric=True)
    assert report["counts"] == {"2 KW": 1, "3.5 KW": 1, "DN50": 2, "DN80": 1}
    assert report["sum"] == pytest.approx(5.5 + 50 * 2 + 80)


def test_replace_plain_regex_and_case():
    assert t.replace_text("Pipe pipe PIPE", "pipe", "DUCT", regex=False, case_sensitive=False) == ("DUCT DUCT DUCT", 3)
    assert t.replace_text("Pipe pipe", "pipe", "DUCT", regex=False, case_sensitive=True) == ("Pipe DUCT", 1)
    assert t.replace_text("CAM-1 CAM-22", r"CAM-(\d+)", r"C\1", regex=True, case_sensitive=True) == ("C1 C22", 2)


BOXES = {"a": (0, 0, 10, 2), "b": (3, 10, 20, 12), "c": (-5, 30, 4, 32)}


def test_align_left_right_and_vertical_spacing():
    assert t.align_moves(BOXES, "left") == {"a": (0, 0), "b": (-3, 0), "c": (5, 0)}
    assert t.align_moves(BOXES, "right", reference=25) == {"a": (15, 0), "b": (5, 0), "c": (21, 0)}
    moves = t.align_moves(BOXES, "distribute_vertical")
    assert moves["b"] == pytest.approx((0, 5)) and moves["a"] == (0, 0) and moves["c"] == (0, 0)


def test_levels():
    from autocad_mcp.core.risk import Risk, risk_of

    assert risk_of("autocad_count_text") is Risk.READ
    for name in ("set_attributes", "number_tags", "text_clean", "find_replace_text", "align_text"):
        assert risk_of(f"autocad_{name}") is Risk.CHANGE
