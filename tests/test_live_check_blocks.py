"""The AC and Y live checks judge right: PASS on a good recorded answer, FAIL on a bad one.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py). The check module's own helpers (reading a table's cells or an
insert's attributes over COM, writing the files a row starts from) are recorded too,
under "my.<name>". That proves the judging and the arguments, not AutoCAD; only a
live run does that.
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from live_fakes import Sequence, load, play, seq

blocks = load("live_check_blocks")
lc = load("live_common")

PUMPS = [list(row) for row in blocks.PUMPS]
DRAWING = Path("/tmp/heron-live-check-1/project/live-check.dwg")


def P(row: str, x: float, y: float) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y, 0.0]


def drawn(*handles: str) -> dict:
    return {"created": len(handles), "failed": 0, "requested": len(handles), "handles": list(handles)}


def status(name: str = "Drawing1.dwg", count: int = 12) -> dict:
    return {"active_drawing": {"name": name, "model_space_entities": count}}


def change(body: dict, head: str = "DONE - 1 changed.") -> str:
    """A change job's answer: the plain first line, then the JSON (D-62)."""
    return f"{head}\n\n{json.dumps(body)}"


def dry(body: dict) -> str:
    return change(body, "NOTHING CHANGED - a dry run: it would have made 2 changed; Heron went back to its UNDO mark.")


def table(texts: list[list[str]], *, align: int = 5, types: list[int] | None = None, top: list[int] | None = None) -> dict:
    rows, columns = len(texts), len(texts[0])
    return {
        "rows": rows, "columns": columns, "texts": [list(r) for r in texts],
        "alignment": [[align] * columns for _ in range(rows)], "state": [[0] * columns for _ in range(rows)],
        "row_types": types or [1] * rows, "top_merge": top,
    }


def att(tag: str, text: str, at: list[float], invisible: bool = False, height: float = 2.5) -> dict:
    return {"tag": tag, "text": text, "invisible": invisible, "position": at, "height": height}


MADE = {"created": True, "block": "B", "handle": None, "objects": 1}

# --- AC -----------------------------------------------------------------------------------------

AC2 = {
    "autocad_batch_draw": drawn("C"),
    "autocad_make_block": seq(
        "Error: The tag 'VALVE TAG' has a space in it, which AutoCAD does not allow in a tag. Use '_' instead, "
        "e.g. 'VALVE_TAG'. Nothing was made.",
        "Error: 'MAKE' is constant but has no default value. A constant attribute shows its default on every "
        "insert. Nothing was made.",
    ),
    "autocad_list_blocks": {"count": 1, "blocks": [{"name": "LC-AC6-PUMP", "entity_count": 2, "instances": 2}]},
    "lc.exists": True,
}

AC6_FIRST = {
    "I1": [att("TAG", "P-101", P("AC6", 2000, 100), height=50), att("MAKE", "GRUNDFOS", P("AC6", 2000, -300), True)],
    "I2": [att("TAG", "P-102", P("AC6", 3900, 0), height=50), att("MAKE", "GRUNDFOS", P("AC6", 4300, 0), True)],
}
AC6_AFTER = [*AC6_FIRST["I1"], att("FLOW", "", P("AC6", 2000, -300 - 1.5 * 2.5))]
AC6 = {
    "autocad_batch_draw": drawn("C"),
    "autocad_make_block": MADE,
    "autocad_insert_block": seq({"created": True, "handle": "I1"}, {"created": True, "handle": "I2"}),
    "autocad_sync_attributes": seq(
        change({"block": "LC-AC6-PUMP", "touched": 2, "attributes_added": 2, "attributes_dropped": 0,
                "definitions_added": ["MAKE"], "synced": {"touched": 2}}),
        change({"block": "LC-AC6-PUMP", "touched": 2, "attributes_added": 2, "attributes_dropped": 0,
                "definitions_added": ["FLOW"], "synced": {"touched": 2}}),
    ),
    "my._attributes_of": seq(AC6_FIRST["I1"], AC6_FIRST["I2"], AC6_AFTER),
    "autocad_list_blocks": {"count": 1, "blocks": [{"name": "LC-AC6-PUMP", "attribute_tags": ["TAG", "MAKE", "FLOW"]}]},
}

LINKED = {"created": True, "linked": True, "handle": "T", "type": "table", "link": "Heron pumps Sheet1 A1:D6",
          "connection": "C:\\Temp\\heron-live-check-1\\project\\pumps.xlsx!Sheet1!A1:D6", "table_rows": 6,
          "table_columns": 4, "rows": 6, "columns": 4, "range": "A1:D6", "sheet": "Sheet1"}
NOT_LINKED = {"created": True, "linked": False, "handle": "T", "type": "table",
              "not_linked_because": "AutoCAD made the link but read nothing from pumps.xlsx (Sheet1 A1:D6). A data "
                                    "link may need Microsoft Excel on this PC; check the file opens in Excel."}

AC7 = {
    "lc.save_scratch": DRAWING,
    "my._write_file": None,
    "autocad_table_from_excel": LINKED,
    "my._table": table(PUMPS),
    "my._data_links": ["Heron pumps Sheet1 A1:D6"],
}

AC8_NEW = [list(r) for r in PUMPS]
AC8_NEW[2][1], AC8_NEW[4][2] = "9.5", "20"
AC8 = {
    "lc.save_scratch": DRAWING,
    "my._write_file": None,
    "autocad_table_from_excel": LINKED,
    "autocad_update_table_links": change({"updated": [{"handle": "T", "source": "pumps.xlsx!Sheet1!A1:D6"}], "not_linked": []}),
    "my._table": table(AC8_NEW),
}

AC9_CSV = {"created": True, "handle": "TC", "linked": False,
           "not_linked_because": "Heron links .xlsx workbooks only; a .csv is filled as it is now", "rows": 6}
AC9_TITLED = {"created": True, "handle": "TT", "linked": False, "not_linked_because": "link=false was asked for", "rows": 6}
AC9 = {
    "lc.save_scratch": DRAWING,
    "my._write_file": None,
    "autocad_table_from_excel": seq(AC9_CSV, AC9_TITLED),
    "my._table": seq(table(PUMPS), table([["PUMP SCHEDULE", "", "", ""], *PUMPS], top=[0, 0, 0, 3])),
}

AC11_DRY = {"handle": "T", "unchanged": [], "refused": [], "added_rows": 0, "added_columns": 0, "would_change": 2,
            "dry_run": True, "before_after": [
                {"handle": "T", "property": "cell B3", "from": "8.5", "to": "12.5"},
                {"handle": "T", "property": "cell B4", "from": "15.0", "to": "8"}]}
AC11_DONE = [list(r) for r in PUMPS]
AC11_DONE[2][1], AC11_DONE[3][1] = "12.5", "8"
AC11 = {
    "lc.save_scratch": DRAWING,
    "my._write_file": None,
    "autocad_table_from_excel": {**AC9_TITLED, "handle": "T"},
    "autocad_set_table_cells": seq(
        dry(AC11_DRY),
        change({"handle": "T", "changed": 2, "refused": [], "dry_run": False}),
        "Error: The table has 6 rows and 4 columns, so A7 is outside it. Pass grow=true to add the rows or columns "
        "it needs, or check the numbering (row 1 is the top row, the title row when there is one). Nothing was changed.",
        change({"handle": "T", "changed": 1, "added_rows": 1, "added_columns": 0, "refused": []}),
    ),
    "my._table": seq(table(PUMPS), table(AC11_DONE), table(AC11_DONE), table([*AC11_DONE, ["P-06", "", "", ""]])),
}

AC12 = {
    "lc.save_scratch": DRAWING,
    "my._write_file": None,
    "autocad_table_from_excel": LINKED,
    "autocad_set_table_cells": {"handle": "T", "changed": 0, "unchanged": [], "dry_run": False, "refused": [
        {"cell": "B3", "why": "it is linked to Excel: change it in the sheet, then autocad_update_table_links"}]},
    "my._table": table(PUMPS),
}

HEAD, ROWS = ["TAG", "TYPE", "FLOW"], [["P-01", "INLINE", "8.5"], ["P-02", "INLINE", "6.0"]]
AC13_TABLES = (
    table([["LC-AC13 PUMPS", "", ""], HEAD, *ROWS], types=[2, 4, 1, 1], top=[0, 0, 0, 2]),
    table([HEAD, *ROWS], types=[4, 1, 1]),
    table(ROWS, types=[1, 1]),
)
AC13 = {
    "autocad_add_table": seq(
        {"created": True, "handle": "A", "rows": 4, "columns": 3, "rows_aligned_middle": 3, "has_title": True},
        {"created": True, "handle": "B", "rows": 3, "rows_aligned_middle": 3, "suppressed": ["TitleSuppressed"]},
        {"created": True, "handle": "C", "rows": 2, "rows_aligned_middle": 3,
         "suppressed": ["TitleSuppressed", "HeaderSuppressed"]},
    ),
    "my._table": seq(*AC13_TABLES),
}

FOLDER = Path("/tmp/heron-live-check-1")
AC14_ENTITIES = {
    "N1": {"handle": "N1", "type": "block", "block_name": "LC-AC14-SKID", "layer": "M-EQPT",
           "insertion_point": P("AC14", 5000, 5000)},
    "N2": {"handle": "N2", "type": "line", "layer": "LC-AC14-PIPE"},
    "N3": {"handle": "N3", "type": "line", "layer": "LC-AC14-PIPE"},
}
AC14_LAYERS = {"count": 4, "layers": [{"name": "0", "color": 7}, {"name": "E-MOTOR", "color": 7},
                                      {"name": "LC-AC14-PIPE", "color": 7}, {"name": "M-EQPT", "color": 1}]}
AC14_ALONG = {"from": "pump-room.dwg", "into": "plan.dwg", "objects": 3, "moved_by": [5000.0, 2000.0, 0.0],
              "brought_in": {"layers": ["E-MOTOR", "LC-AC14-PIPE"], "blocks": ["LC-AC14-MOTOR", "LC-AC14-SKID"]},
              "already_here": {"layers": ["M-EQPT"]}}
AC14 = {
    "lc.other_drawing": seq(FOLDER / "LC-AC14" / "pump-room.dwg", FOLDER / "LC-AC14" / "plan.dwg"),
    "autocad_create_layer": {"name": "M-EQPT", "created": True},
    "autocad_batch_draw": seq(drawn("MC"), drawn("F", "P1", "P2")),
    "autocad_make_block": MADE,
    "autocad_insert_block": seq({"created": True, "handle": "MI"}, {"created": True, "handle": "SK"}),
    "autocad_status": seq(status("pump-room.dwg", 7), status("plan.dwg", 0), status("plan.dwg", 0),
                          status("plan.dwg", 3), status("plan.dwg", 3), status("pump-room.dwg", 7)),
    "autocad_copy_from_drawing": seq(
        dry({**AC14_ALONG, "dry_run": True, "would_copy": 3}),
        change({**AC14_ALONG, "dry_run": False, "copied": 3, "handles": ["N1", "N2", "N3"]}, "DONE - 3 added."),
    ),
    "autocad_get_entity": lambda handle: AC14_ENTITIES[handle],
    "autocad_list_layers": AC14_LAYERS,
    "lc.activate": None,
}

AC15 = {
    "lc.other_drawing": seq(FOLDER / "LC-AC15" / "LC-AC15-source.dwg", FOLDER / "LC-AC15" / "LC-AC15-plan.dwg"),
    "autocad_batch_draw": seq(drawn("2A0"), drawn(*[f"2A{i}" for i in range(1, 10)], "2AA")),
    "lc.activate": None,
    "lc.exists": False,
    "autocad_status": status("LC-AC15-plan.dwg", 10),
    "autocad_copy_from_drawing": seq(
        "Error: LC-AC15-source.dwg has nothing with the handle(s) 2AA. Handles belong to one drawing: read them "
        "there (autocad_list_entities while it is active). Nothing was copied.",
        "Error: LC-AC15-plan.dwg is the active drawing. To copy inside one drawing use autocad_copy_entities; to "
        "copy into another, make that one active (autocad_switch_drawing, then autocad_status).",
    ),
}

AC17_FLAT = {"block": "LC-AC17-TAG", "touched": 1, "dry_run": True, "definitions_added": [],
             "inserts": [{"handle": "IN", "keep": {"TAG": "V-201"}, "add": {"FLOW": "10"}, "drop": []}]}
AC17_DEEP = {**AC17_FLAT, "touched": 2, "inserts": [
    *AC17_FLAT["inserts"],
    {"handle": "NE", "inside": "LC-AC17-SKID", "keep": {"TAG": "V-201"}, "add": {"FLOW": "10"}, "drop": []},
]}
AC17 = {
    "autocad_batch_draw": seq(drawn("C"), drawn("F")),
    "autocad_make_block": MADE,
    "autocad_insert_block": seq(*({"created": True, "handle": h} for h in ("IN", "S1", "S2"))),
    "autocad_sync_attributes": seq(
        AC17_FLAT, AC17_DEEP,
        change({**AC17_DEEP, "dry_run": False, "attributes_dropped": 0, "synced": {"touched": 2}}),
    ),
    "my._nested_attributes": [{"TAG": "V-201", "FLOW": "10"}],
    "my._attributes_of": [att("TAG", "V-201", P("AC17", 1000, 150)), att("FLOW", "10", P("AC17", 1000, -100))],
}

# --- Y ------------------------------------------------------------------------------------------

SHEET = Path("/tmp/heron-live-check-1/project/live-check - attributes - 2026-11-21.xlsx")


def workbook(rows: list[list[str]]) -> dict:
    heading = ["Handle", "Block", "Layout", "TAG", "SIZE"]
    sheet = [heading, *rows]
    return {"Attributes": sheet, "As exported": sheet, "Read me": [["How to use this workbook"]]}


def block(handle: str, **values: str) -> dict:
    return {"handle": handle, "type": "block", "attributes": dict(values)}


Y2_START = {"A": {"TAG": "0050", "SIZE": "S"}, "B": {"TAG": "0051", "SIZE": "M"}, "C": {"TAG": "0052", "SIZE": "L"}}
Y2_BOOK = workbook([[h, "LC-Y2-CAMERA", "Model", v["TAG"], v["SIZE"]] for h, v in Y2_START.items()])
Y2_AFTER = {"A": {"TAG": "0060", "SIZE": "S"}, "B": {"TAG": "0061", "SIZE": "M"}, "C": {"TAG": "0052", "SIZE": "L"}}
Y2 = {
    "lc.save_scratch": DRAWING,
    "autocad_batch_draw": drawn("CIR"),
    "autocad_make_block": MADE,
    "autocad_insert_block": seq(*({"created": True, "handle": h} for h in "ABC")),
    "autocad_export_attribute_sheet": {"saved": str(SHEET), "blocks": 3, "tags": ["TAG", "SIZE"]},
    "my._read_workbook": Y2_BOOK,
    "my._write_workbook": None,
    "autocad_apply_attribute_sheet": seq(
        {"dry_run": True, "changed": 0, "would_change": 2, "blank_cells": 1, "unchanged_cells": 4},
        change({"dry_run": False, "changed": 2, "blank_cells": 1, "before_after": [
            {"handle": "A", "property": "attribute TAG", "from": "0050", "to": "0060"},
            {"handle": "B", "property": "attribute TAG", "from": "0051", "to": "0061"}]}, "DONE - 2 changed."),
    ),
    "autocad_get_entity": seq(*(block(h, **v) for h, v in Y2_START.items()),
                              *(block(h, **v) for h, v in Y2_AFTER.items())),
}

Y3_BOOK = workbook([[h, "LC-Y3-CAMERA", "Model", f"C-0{i}", "S"] for i, h in enumerate("ABC", 1)])
Y3 = {
    "lc.save_scratch": DRAWING,
    "autocad_batch_draw": drawn("CIR"),
    "autocad_make_block": MADE,
    "autocad_insert_block": seq(*({"created": True, "handle": h} for h in "ABC")),
    "autocad_export_attribute_sheet": {"saved": str(SHEET), "blocks": 3},
    "my._by_hand_attribute": None,
    "my._read_workbook": Y3_BOOK,
    "my._write_workbook": None,
    "autocad_apply_attribute_sheet": change({
        "dry_run": False, "changed": 1,
        "changes": [{"handle": "B", "block": "LC-Y3-CAMERA", "tag": "TAG", "old": "C-02", "new": "C-02-XL"}],
        "conflicts": [{"handle": "A", "tag": "TAG", "exported": "C-01", "drawing": "C-01-HAND", "sheet": "C-01-XL"}],
        "kept_drawing": [{"handle": "C", "tag": "TAG", "exported": "C-03", "drawing": "C-03-HAND"}],
    }),
    "autocad_get_entity": seq(block("A", TAG="C-01-HAND", SIZE="S"), block("B", TAG="C-02-XL", SIZE="S"),
                              block("C", TAG="C-03-HAND", SIZE="S")),
}

Y4_LINES = [
    {"drawing": "c-bad.dwg", "verdict": "NOT RUN", "coverage": "",
     "reason": "AutoCAD would not open it read only: Drawing file is not valid."},
    {"drawing": "a-closed.dwg", "verdict": "NO DATA", "coverage": "0 of 3 checks had something to check"},
    {"drawing": "b-open.dwg", "verdict": "PASS", "coverage": "3 of 3"},
]
Y4 = {
    "lc.other_drawing": FOLDER / "LC-Y4" / "b-open.dwg",
    "my._closed_drawing": "a-closed.dwg",
    "my._write_file": None,
    "lc.activate": None,
    "lc.file_stamp": lambda path: (1000, 1.5),
    "autocad_check_folder": {"folder": str(FOLDER / "LC-Y4"), "worst": "NOT RUN", "drawings": Y4_LINES},
    "lc.drawing_names": ["Drawing1.dwg", "b-open.dwg"],
    "autocad_status": status(),
}

# Each row: the good recording, and what in it goes wrong for the FAIL.
SAMPLES: dict[str, tuple[dict, dict]] = {
    "AC2": (AC2, {"autocad_list_blocks": {"count": 1, "blocks": [{"name": "LC-AC2-TAG"}]}}),
    "AC6": (AC6, {"my._attributes_of": seq(
        [AC6_FIRST["I1"][0], att("MAKE", "GRUNDFOS", P("AC6", 2000, -200), True)], AC6_FIRST["I2"], AC6_AFTER,
    )}),
    "AC7": (AC7, {"my._table": table(PUMPS, align=2)}),
    "AC8": (AC8, {"my._table": table(PUMPS)}),
    "AC9": (AC9, {"my._table": seq(table([["", "", "", ""], *PUMPS]), table([["PUMP SCHEDULE", "", "", ""], *PUMPS], top=[0, 0, 0, 3]))}),
    "AC11": (AC11, {"autocad_set_table_cells": seq(change(AC11_DRY, "DONE - 2 changed."), *AC11["autocad_set_table_cells"].items[1:])}),
    "AC12": (AC12, {"autocad_set_table_cells": {"handle": "T", "changed": 1, "refused": []}}),
    "AC13": (AC13, {"my._table": seq(AC13_TABLES[0], table([["TAG", "", ""], *ROWS], types=[2, 1, 1], top=[0, 0, 0, 2]),
                                     AC13_TABLES[2])}),
    "AC14": (AC14, {"autocad_list_layers": {**AC14_LAYERS, "layers": [{"name": "E-MOTOR", "color": 7}, {"name": "M-EQPT", "color": 3}]}}),
    "AC15": (AC15, {"autocad_copy_from_drawing": seq(
        AC15["autocad_copy_from_drawing"].items[0], change({"copied": 1, "handles": ["2AB"]}, "DONE - 1 added."),
    )}),
    "AC17": (AC17, {"autocad_sync_attributes": seq(AC17_DEEP, AC17_DEEP, AC17["autocad_sync_attributes"].items[2])}),
    "Y2": (Y2, {"autocad_get_entity": seq(*(block(h, **v) for h, v in Y2_START.items()),
                                          *(block(h, **v) for h, v in {**Y2_AFTER, "C": {"TAG": "0052", "SIZE": ""}}.items()))}),
    "Y3": (Y3, {"autocad_get_entity": seq(block("A", TAG="C-01-XL", SIZE="S"), block("B", TAG="C-02-XL", SIZE="S"),
                                          block("C", TAG="C-03-HAND", SIZE="S"))}),
    "Y4": (Y4, {"lc.drawing_names": ["Drawing1.dwg", "b-open.dwg", "a-closed.dwg"]}),
}

CHECKS = {c.row: c for c in blocks.CHECKS}


def _fake_mine(monkeypatch: Any, recorded: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Put recorded answers in the place of the check module's own helpers ("my.<name>"); the calls made."""
    calls: list[tuple[str, dict[str, Any]]] = []
    for key, answer in recorded.items():
        name = key.removeprefix("my.")
        real = getattr(blocks, name)
        signature = inspect.signature(real)
        pending = list(answer.items) if isinstance(answer, Sequence) else None

        def call(*args: Any, _name: str = name, _sig: Any = signature, _answer: Any = answer,
                 _pending: list | None = pending, **kwargs: Any) -> Any:
            bound = _sig.bind(*args, **kwargs).arguments
            calls.append((_name, dict(bound)))
            if _pending is not None:
                assert _pending, f"{_name} was called more often than the recording has answers for"
                return copy.deepcopy(_pending.pop(0))
            # A copy: a check may change what it was given, and the recording is played again.
            return _answer(**bound) if callable(_answer) else copy.deepcopy(_answer)

        if inspect.iscoroutinefunction(real):
            async def fake(*args: Any, _call: Any = call, **kwargs: Any) -> Any:
                return _call(*args, **kwargs)

            monkeypatch.setattr(blocks, name, fake)
        else:
            monkeypatch.setattr(blocks, name, call)
    return calls


# The module's own helpers that touch AutoCAD or the disk: never the real ones in a test.
OWN = ("_table", "_attributes_of", "_nested_attributes", "_data_links", "_by_hand_attribute", "_closed_drawing",
       "_write_file", "_read_workbook", "_write_workbook")


def run(monkeypatch: Any, row: str, answers: dict[str, Any]):
    mine = {k: v for k, v in answers.items() if k.startswith("my.")}
    unknown = [k for k in mine if k[3:] not in OWN]
    assert not unknown, f"the recording names helpers the module does not have: {unknown}"
    for name in OWN:
        if f"my.{name}" not in mine:
            def refuse(*args: Any, _name: str = name, **kwargs: Any) -> Any:
                raise AssertionError(f"the check called {_name}, which the recording does not cover")

            monkeypatch.setattr(blocks, name, refuse)
    _fake_mine(monkeypatch, mine)
    return play(monkeypatch, CHECKS[row], {k: v for k, v in answers.items() if not k.startswith("my.")})


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each AC / Y check needs a good and a bad recording here"


def test_every_ac_and_y_row_is_measured_or_excused():
    text = (Path(__file__).resolve().parent.parent / "docs" / "NEEDS-CHECKING.md").read_text(encoding="utf-8")
    import re

    rows = set(re.findall(r"^\|\s*((?:AC|Y)\d+[a-z]?)\s*\|", text, re.M))
    measured, excused = set(CHECKS), set(blocks.BY_EYE)
    assert not measured & excused, f"claimed twice: {sorted(measured & excused)}"
    assert measured | excused == rows, f"not accounted for: {sorted(rows - measured - excused)}; " \
                                       f"not in the register: {sorted((measured | excused) - rows)}"
    assert all(len(why.split()) >= 4 for why in blocks.BY_EYE.values())
    assert all(len(c.title.split()) >= 3 and c.group == lc.group_of(c.row) for c in blocks.CHECKS)


def test_rows_that_write_a_file_need_publish():
    assert CHECKS["Y2"].needs == frozenset({"publish"}) and CHECKS["Y3"].needs == frozenset({"publish"})


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    good, _ = SAMPLES[row]
    verdict = run(monkeypatch, row, good)
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = run(monkeypatch, row, {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


@pytest.mark.parametrize("row", ["AC8", "AC12"])
def test_a_table_that_could_not_link_is_not_run_rather_than_failed(monkeypatch, row):
    good, _ = SAMPLES[row]
    verdict = run(monkeypatch, row, {**good, "autocad_table_from_excel": NOT_LINKED})
    assert verdict.refused and "Microsoft Excel" in verdict.evidence


def test_ac7_without_a_link_fails_saying_what_autocad_answered(monkeypatch):
    verdict = run(monkeypatch, "AC7", {**AC7, "autocad_table_from_excel": NOT_LINKED})
    assert not verdict.passed and not verdict.refused and "Microsoft Excel" in verdict.evidence


def test_y2_edits_the_cells_it_says(monkeypatch):
    written: list[dict] = []
    answers = {**Y2, "my._write_workbook": lambda path, sheets: written.append(sheets)}
    verdict = run(monkeypatch, "Y2", answers)
    assert verdict.passed, verdict.evidence
    rows = {r[0]: r for r in written[0]["Attributes"][1:]}
    assert (rows["A"][3], rows["B"][3], rows["C"][4]) == ("0060", "0061", "")
    assert written[0]["As exported"] == Y2_BOOK["As exported"], "the 'As exported' sheet must be left alone"
