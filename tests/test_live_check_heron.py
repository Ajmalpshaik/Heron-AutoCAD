"""The Heron-behaviour live checks (groups M to Z) judge right from recorded answers.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py): PASS on a good recording, FAIL on a bad one. W7 and W8 run
Heron's real tool finder on the good side: it needs no AutoCAD.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from live_fakes import Raw, load, play, seq

heron = load("live_check_heron")
lc = load("live_common")

from autocad_mcp.tools import advanced  # noqa: E402

STATUS = {"active_drawing": {"name": "Drawing1.dwg", "path": "", "model_space_entities": 12}, "heron": {"connected": True}}
SAVED = Path("C:/Temp/heron-live-check-x/project/live-check.dwg")


def drawn(*handles: str) -> dict:
    return {"created": len(handles), "failed": 0, "requested": len(handles), "handles": list(handles)}


def answer(line: str, payload: dict | str) -> str:
    """A change job's answer: its plain first line, then the tool's own words."""
    return f"{line}\n\n{payload if isinstance(payload, str) else json.dumps(payload)}"


def refused(message: str) -> str:
    return answer("REFUSED - the tool turned the job down; nothing was changed.", f"Error: {message}")


@dataclass
class Picture:
    data: bytes


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
SAVE_REFUSAL = ("QSAVE saves, plots or exports, and that needs the Publish padlock, which a raw command or AutoLISP "
                "does not ask for. Use autocad_save_drawing, autocad_export or autocad_publish_pdf instead. "
                "Nothing was sent to AutoCAD.")


def run_of(*results: dict, coverage: str = "", verdict: str = "FAIL") -> dict:
    return {"checklist": "x", "verdict": verdict, "coverage": coverage, "results": list(results),
            "checks_used": [{"id": r["id"], "label": r.get("label", ""), "from": r.get("from", "office")} for r in results]}


def line_of(check: str, state: str, **extra) -> dict:
    return {"id": extra.pop("id", check), "check": check, "state": state, "severity": "medium", "from": "office",
            "label": check, **extra}


# --- M -----------------------------------------------------------------------------------------

M3 = {
    "autocad_status": STATUS,
    "autocad_send_command": refused(SAVE_REFUSAL),
    "autocad_run_lisp": refused(SAVE_REFUSAL.replace("QSAVE", "QSAVE")),
}
M6 = {
    "autocad_batch_draw": drawn("L"),
    "autocad_preview": Raw([Picture(PNG), json.dumps({"area": "extents", "layout": "Model", "size": [400, 283]})]),
}

# --- O -----------------------------------------------------------------------------------------

O1 = {
    "lc.save_scratch": SAVED,
    "autocad_project_notes": {"project": "C:/Temp/heron-live-check-x/project", "notes": {}},
    "autocad_status": {**STATUS, "heron": {"connected": True, "project_notes": {"scale": "1:50"}}},
}
O2 = {
    "lc.save_scratch": SAVED,
    "autocad_project_notes": {"project": "x", "notes": {}},
    "lc.other_drawing": Path("C:/Temp/heron-live-check-x/elsewhere/o2.dwg"),
    "autocad_status": STATUS,
    "lc.activate": None,
}
O3_RUN = run_of(
    line_of("nothing_on_layer_0", "FAIL", handles=["A1", "A2"]),
    line_of("bylayer_colour", "FAIL", handles=["B1"]),
    line_of("xrefs_found", "PASS"),
    coverage="3 of 3 decided, 0 no data, 0 not run",
)
O3 = {
    "autocad_batch_draw": drawn("A1"),
    "autocad_checklist": O3_RUN,
    "autocad_show": {"shown": 2, "isolated": False, "not_found": []},
    "autocad_get_entity": {"handle": "A1", "layer": "0"},
}
O4_RUN = run_of(
    line_of("title_block_filled", "FAIL", id="title_blocks", label="Every LC-O4 title block filled in", handles=["T1"]),
    line_of("text_heights", "FAIL", id="heights", label="Text 2.5, 3.5 or 5 only", handles=["X"]),
)
O4 = {
    "autocad_batch_draw": drawn("F"),
    "autocad_make_block": {"created": True, "block": "LC-O4-TITLE", "handle": None},
    "autocad_insert_block": {"created": True, "handle": "T1"},
    "autocad_checklist": seq({"saved": "lc-o4 own sentences"}, O4_RUN, {"deleted": "lc-o4 own sentences"}),
}
O5 = {
    "autocad_status": STATUS,
    "autocad_draw_circle": {"created": True, "handle": "C1"},
    "autocad_undo_last": {"undone": "Draw Circle", "drawing": "x", "removed": ["C1"]},
    "lc.exists": False,
}
O6 = {
    "autocad_draw_circle": {"created": True, "handle": "C1"},
    "lc.by_hand_line": "L9",
    "autocad_undo_last": refused("The drawing changed after Heron's last change (your own work, or another program), "
                                 "so undoing it could take your work with it. Nothing was changed."),
    "lc.exists": True,
}

# --- P -----------------------------------------------------------------------------------------

P1_ENTITIES = {
    "B1": {"handle": "B1", "type": "3dsolid", "layer": "LC-P1", "size": {"width": 1200.0, "height": 600.0}},
    "B2": {"handle": "B2", "type": "3dsolid", "layer": "LC-P1", "size": {"width": 1500.0, "height": 900.0}},
}
P1 = {
    "autocad_add_solid": {"created": True, "handle": "B1"},
    "autocad_saved_command": seq(
        {"saved": "lc-p1 plinth", "inputs": ["depth", "width"], "steps": 1},
        {"command": "lc-p1 plinth", "ran": 1, "failed": 0, "skipped": 0, "steps": [{"index": 0, "ok": True, "result": {"handle": "B2"}}]},
        {"deleted": "lc-p1 plinth"},
    ),
    "autocad_get_entity": lambda handle: P1_ENTITIES[handle],
}

# --- T -----------------------------------------------------------------------------------------

NOT_COUNTED = ("DONE - no drawing object was added, changed or erased (layers, styles and settings are not counted, "
               "so read the answer below).")
DRY = "NOTHING CHANGED - a dry run: it would have made 1 added, 0 changed, 0 erased; Heron went back to its UNDO mark."
T2 = {
    "autocad_draw_line": answer("DONE - 1 added, 0 changed, 0 erased.", {"created": True, "handle": "L"}),
    "autocad_find_replace_text": answer("NOTHING CHANGED - the job ran and changed nothing in the drawing.", {"replaced": 0}),
    "autocad_create_layer": answer(NOT_COUNTED, {"name": "LC-T2-LAYER", "created": True}),
}
T4 = {
    "autocad_status": STATUS,
    "autocad_draw_circle": answer(DRY, {"created": True, "handle": "C1"}),
    "lc.exists": False,
    "autocad_batch_draw": drawn("L"),
    "autocad_get_entity": {"handle": "L", "layer": "LC-T4", "color": 256},
    "autocad_modify_entity": answer(DRY, {"modified": 1}),
    "autocad_create_layer": answer("NOTHING CHANGED - a dry run: Heron went back to its UNDO mark.", {"name": "M-TEST"}),
    "autocad_list_layers": {"count": 2, "layers": [{"name": "0"}, {"name": "LC-T4"}]},
}
T5 = {
    "autocad_batch_draw": drawn("A", "B"),
    "autocad_get_variable": {"name": "CLAYER", "value": "0"},
    "autocad_loft": answer(DRY, {"created": True, "handle": "S1"}),
    "lc.exists": False,
    "autocad_set_current_layer": answer("NOTHING CHANGED - a dry run: Heron went back to its UNDO mark.", {"current_layer": "LC-T5-CURRENT"}),
    "autocad_status": STATUS,
    "autocad_save_drawing": answer("REFUSED - nothing was sent to AutoCAD.", "Error: Dry run not possible for Save Drawing."),
}
T6_MODIFY = {"modified": 1, "before_after": [
    {"handle": "ONE", "property": "layer", "from": "LC-T6", "to": "M-DUCT"},
    {"handle": "ONE", "property": "color", "from": 256, "to": 1},
], "already": ["TWO"]}
T6 = {
    "autocad_create_layer": {"name": "M-DUCT", "created": True},
    "autocad_batch_draw": drawn("ONE", "TWO", "NOTE"),
    "autocad_modify_entity": T6_MODIFY,
    "autocad_set_layer_state": seq(
        answer("DONE - no drawing object was added, changed or erased.", {"matched": 2, "before_after": [{"layer": "M-DUCT", "property": "on", "from": True, "to": False}]}),
        answer("NOTHING CHANGED - the job ran and changed nothing in the drawing.", {"matched": 2, "before_after": []}),
        {"matched": 2},
    ),
    "autocad_get_variable": {"name": "DIMSCALE", "value": 1.0},
    "autocad_set_variable": seq({"name": "DIMSCALE", "before_after": [{"variable": "DIMSCALE", "from": 1.0, "to": 100}]}, {}),
    "autocad_find_replace_text": {"replaced": 1, "before_after": [{"handle": "NOTE", "property": "text", "from": "REV A", "to": "REV B"}]},
}

# --- U -----------------------------------------------------------------------------------------

U1 = {
    "lc.other_drawing": Path("C:/Temp/x/u1/u1-sheet.dwg"),
    "autocad_checklist": seq({"saved": "lc-u1 sheets"}, run_of(
        line_of("title_block_filled", "NO DATA", note="no block named TITLE* is in the drawing"),
        line_of("nothing_on_layer_0", "PASS"),
        coverage="1 of 2 decided, 1 no data, 0 not run", verdict="NO DATA",
    ), {"deleted": "lc-u1 sheets"}),
}
CAPPED = "only the first 10 objects were read; the rest were not checked"
U2 = {
    "lc.other_drawing": Path("C:/Temp/x/u2/u2-big.dwg"),
    "autocad_batch_draw": drawn(*[f"H{i}" for i in range(30)]),
    "autocad_checklist": run_of(
        line_of("nothing_on_layer_0", "FAIL", handles=["H0"]),
        line_of("nothing_on_defpoints", "NO DATA", note=CAPPED),
        line_of("bylayer_colour", "NO DATA", note=CAPPED),
    ),
}
U3_LIST = {"name": "before issue", "checks": [{"id": i} for i in (
    "nothing_on_layer_0", "nothing_on_defpoints", "bylayer_colour", "xrefs_found", "no_overlapping_dimensions")]}
U3_RUN = run_of(
    line_of("bylayer_colour", "FAIL", severity="high", **{"from": "project"}, handles=["X"]),
    line_of("xrefs_found", "NOT RUN", **{"from": "project"}),
    line_of("nothing_on_layer_0", "PASS"), line_of("nothing_on_defpoints", "PASS"), line_of("no_overlapping_dimensions", "PASS"),
    coverage="4 of 5 decided, 0 no data, 1 not run",
)
U3 = {
    "lc.save_scratch": SAVED,
    "autocad_checklist": seq(U3_LIST, {"project": "x", "changes": []}, U3_RUN, {"project": "x", "changes": []}),
}
U4_RUN = run_of(*(line_of(i["id"], "PASS") for i in U3_LIST["checks"]))
U4 = {
    "lc.save_scratch": SAVED,
    "lc.other_drawing": Path("C:/Temp/x/u4/u4-elsewhere.dwg"),
    "lc.activate": None,
    "autocad_checklist": seq({"changes": []}, U4_RUN, {"changes": []}),
}
U5 = {
    "lc.save_scratch": SAVED,
    "autocad_checklist": seq(
        "Error: Project change 1: the office list has no check 'my_new_check', and a project cannot add one. Nothing was kept.",
        "Error: Project change 1 ('nothing_on_layer_0'): a project may only change severity, target, on; not label. Nothing was kept.",
        {"project": "x", "checklist": "before issue", "changes": []},
    ),
}
U6 = {
    "lc.save_scratch": SAVED,
    "lc.files_in": seq([], []),
    "autocad_checklist_report": refused("The Publish padlock is off. Turn it on in Settings (HERONPUBLISH)."),
}
U7_FIRST = {"xlsx": "C:/T/project/live-check - checklist before-issue - 2026-11-21.xlsx",
            "html": "C:/T/project/live-check - checklist before-issue - 2026-11-21.html"}
U7_SECOND = {k: v.replace("2026-11-21.", "2026-11-21 (2).") for k, v in U7_FIRST.items()}
U7 = {
    "lc.save_scratch": SAVED,
    "autocad_checklist_report": seq({"saved": U7_FIRST, "verdict": "FAIL"}, {"saved": U7_SECOND, "verdict": "FAIL"}),
    "lc.file_stamp": lambda path: (1200, 1.0) if "(2)" not in str(path) else (1210, 2.0),
}
U10 = {"autocad_check_standards": {"checked": 10, "passed": True, "source": "rules given inline",
                                   "pass_means": "PASS means the checked value is met ...", "findings": []}}

# --- W -----------------------------------------------------------------------------------------

W2_WHY = {"job": "save this as PDF", "can_run": False, "tool": {"tool": "autocad_export", "needs": ["Changes", "Publish"]},
          "reasons": [{"reason": "publish_off", "says": "autocad_export needs the Publish padlock, and it is off.",
                       "what_to_do": "Turn Publish on in Settings on the Heron tab in AutoCAD (or type HERONPUBLISH)."}]}
W2 = {
    "autocad_why": W2_WHY,
    "autocad_export": refused("Publish is off: turn it on in Settings (HERONPUBLISH)."),
    "lc.file_stamp": None,
    "autocad_gaps": {"failures": [{"reason": "publish_off", "says": "The Publish padlock was off.", "count": 1}]},
}
W3 = {"autocad_why": {"can_run": True, "tool": {"tool": "autocad_make_shape"}, "reasons": [],
                      "verdict": "Nothing Heron can see is in the way: autocad_make_shape should run."}}
W4 = {"autocad_why": {"can_run": False, "tool": None, "verdict": "Heron has no tool for this job.",
                      "reasons": [{"reason": "no_tool", "says": "Heron has no tool for this job.",
                                   "what_to_do": "Do it by hand in AutoCAD, or describe it in other words."}]}}
WRONG_FIND = json.dumps({"question": True, "matches": [{"tool": "autocad_draw_line", "needs": "Changes"}],
                         "would_change_the_drawing": []})

# --- Z -----------------------------------------------------------------------------------------

Z2 = {"autocad_run_lisp": seq({"result": "nil"}, {"chunks": 6, "chunks_finished": 6, "timed_out": False, "result": "171"},
                              {"result": "(USUBR USUBR USUBR USUBR USUBR USUBR)"})}
Z3_NOTE = "AutoCAD never wrote a result within the wait. It was piece 3 of 6: pieces 1 to 2 ran, and 3 more were not sent."
Z3 = {"autocad_run_lisp": seq({"result": "nil"}, {"timed_out": True, "result": None, "note": Z3_NOTE, "chunks": 6, "chunks_finished": 2},
                              {"result": "(USUBR USUBR nil nil nil nil)"})}
Z4 = {
    "autocad_status": STATUS,
    "autocad_run_lisp": {"chunks": 2, "chunks_finished": 1, "timed_out": False, "result": "nil", "cancelled_command": "LINE"},
    "autocad_get_variable": {"name": "CMDACTIVE", "value": 0},
}


def _z5(quiet: bool) -> str:
    def step(i: int) -> dict:
        if quiet:
            return {"index": i, "ok": True, "result": {"count": 5, "handles": [f"D{i}{j}" for j in range(5)], "left_out": {"dimensions": 5}}}
        dims = [{"kind": "linear", "point1": [0, 0], "point2": [1000, 0], "text_position": [500, 300], "measured": 1000.0}] * 5
        return {"index": i, "ok": True, "result": {"count": 5, "handles": [f"D{i}{j}" for j in range(5)], "dimensions": dims}}
    return json.dumps({"ran": 8, "failed": 0, "skipped": 0, "steps": [step(i) for i in range(8)]})


Z5 = {"autocad_sequence": seq(_z5(False), _z5(True))}
Z8 = {
    "autocad_run_lisp": answer("OUTCOME UNKNOWN - AutoCAD did not answer within the wait, so the job may still have run.",
                               {"timed_out": True, "result": None, "note": "AutoCAD never wrote a result within the wait."}),
    "autocad_get_variable": {"name": "CMDACTIVE", "value": 0},
}

# --- V: the dialog watch, with AutoLISP's alert box as the way in (D-141) ------------------------

BOX_ESC = "AutoCAD showed 'AutoCAD'; Heron closed it with Esc, nothing was kept from that step."
BOX_OK = "AutoCAD showed 'AutoCAD'; Heron closed it with OK, nothing was kept from that step."
BOX_ASKED = "AutoCAD showed 'AutoCAD'; Heron pressed OK on it, as this call asked (#101)."
LOG_OLD = ["10:00:00.000 [1] connected", "10:00:01.000 [4] request ok"]
LOG_WATCH = "10:05:00.100 [7] dialog watch: 'AutoCAD' -> Esc"


def alerted(*boxes: str, timed_out: bool = False) -> str:
    """What autocad_run_lisp answers for the alert, with the boxes the watch named."""
    payload = {"expression": '(alert "Heron live check")', "result": "nil", "timed_out": timed_out}
    if boxes:
        payload["heron_dialogs"] = list(boxes)
    return answer("DONE - no drawing object was added, changed or erased.", payload)


STATUS_SAME = {"active_drawing": {"name": "Drawing1.dwg", "path": "", "model_space_entities": 12}, "heron": {"connected": True}}
V1 = {"autocad_status": STATUS_SAME, "autocad_run_lisp": alerted(BOX_ESC), "autocad_get_variable": {"name": "CMDACTIVE", "value": 0}}
V4 = {"autocad_batch_draw": drawn("4A"), "autocad_status": STATUS_SAME, "autocad_run_lisp": alerted(BOX_ESC), "lc.exists": True}
V6 = {"autocad_run_lisp": alerted(BOX_ESC), "lc.addin_log_lines": seq(LOG_OLD, LOG_OLD, [*LOG_OLD, LOG_WATCH])}
V7 = {"autocad_run_lisp": seq(alerted(BOX_ESC), alerted(BOX_ASKED), alerted(BOX_ESC))}

# --- AG, AJ, RV ---------------------------------------------------------------------------------

OFFICE = Path("C:/Temp/x/ag5-office/office.dwg")


def standard_answer(row: str, read_by: str = "AutoCAD's own reader (ObjectDBX); the file was not opened on screen") -> dict:
    return {"checked": 40, "passed": False, "source": f"reference drawing {OFFICE.name}", "pass_means": "x",
            "reference": {"file": str(OFFICE), "read_by": read_by}, "findings": [
                {"rule": "layer_differs_from_standard", "table": "layer", "name": f"LC-{row}-WALL",
                 "detail": "colour 5 here, 1 in the standard"},
                {"rule": "text_style_differs_from_standard", "table": "text style", "name": f"LC-{row}-NOTE",
                 "detail": "font simplex.shx here, romans.shx in the standard"},
                {"rule": "layer_not_in_standard", "table": "layer", "name": "LC-AA1", "detail": "x"},
            ]}


def reference_rows(row: str, **answer) -> dict:
    return {
        "lc.other_drawing": OFFICE,
        "autocad_create_layer": {"created": True},
        "autocad_create_styles": {"text_styles": []},
        "lc.save_active": None,
        "lc.close_drawing": None,
        "lc.activate": None,
        "autocad_check_standards": standard_answer(row, **answer),
        "lc.drawing_names": ["live-check.dwg"],
    }


AG5 = reference_rows("AG5")
AG6 = reference_rows("AG6", read_by="AutoCAD: the drawing is open there (what is saved and not saved)")
AG8 = reference_rows("AG8")
A_DWG = Path("C:/Temp/x/aj3/a.dwg")
DRAWN_LINE = answer("DONE - 1 added, 0 changed, 0 erased.", {"created": True, "handle": "L1"})
AJ3 = {
    "lc.other_drawing": A_DWG, "lc.close_drawing": None, "lc.open_drawing": "a.dwg",
    "autocad_draw_line": seq(refused("a.dwg was closed at 10:02:03 and opened again since Heron checked it. Call "
                                     "autocad_status first, so Heron knows the units."), DRAWN_LINE),
    "autocad_status": STATUS, "lc.exists": True,
}
AJ4 = {
    "lc.new_drawing": "Drawing3.dwg", "lc.save_as": "plan.dwg",
    "autocad_draw_line": DRAWN_LINE, "lc.exists": True,
    "autocad_status": {**STATUS, "active_drawing": {**STATUS["active_drawing"], "name": "plan.dwg"}},
}
AJ5B = {
    "lc.other_drawing": A_DWG.with_name("a.dwg"), "lc.save_as": "a-rev2.dwg", "lc.open_drawing": "a.dwg",
    "autocad_draw_line": seq(refused("a.dwg was opened at 10:04:00, after Heron checked a drawing, so it is a new copy "
                                     "in memory. Call autocad_status first."), DRAWN_LINE),
    "autocad_status": STATUS, "lc.exists": True,
}
AJ6 = {"autocad_batch_draw": {"created": 41, "requested": 41, "failed": 0, "completed": True, "handles": [], "elapsed_seconds": 0.2}}
AJ7 = {"autocad_batch_draw": seq({"created": 2000, "requested": 2000, "completed": True},
                                 {"created": 51, "requested": 51, "completed": True})}
RV3 = {
    "autocad_status": STATUS,
    "autocad_sequence": "Error: Step 1: 'autocad_switch_drawing' makes another drawing active, so it cannot be a step.",
}

SAMPLES: dict[str, tuple[dict, dict]] = {
    "AG5": (AG5, {"lc.drawing_names": ["live-check.dwg", "office.dwg"]}),
    "AG6": (AG6, {"autocad_check_standards": standard_answer("AG6")}),
    "AG8": (AG8, {"autocad_check_standards": {**standard_answer("AG8"), "findings": [
        {"rule": "text_style_differs_from_standard", "name": "LC-AG8-ARIAL", "detail": "font Arial here, Arial in the standard"},
        *standard_answer("AG8")["findings"]]}}),
    "AJ3": (AJ3, {"autocad_draw_line": seq(refused("The active drawing changed from a.dwg to a.dwg since Heron last checked."), DRAWN_LINE)}),
    "AJ4": (AJ4, {"autocad_status": STATUS}),
    "AJ5b": (AJ5B, {"autocad_draw_line": seq(DRAWN_LINE, DRAWN_LINE)}),
    "AJ6": (AJ6, {"autocad_batch_draw": {**AJ6["autocad_batch_draw"], "created": 40, "missing": 1}}),
    "AJ7": (AJ7, {"autocad_batch_draw": seq({"created": 2000, "requested": 2000, "completed": True},
                                            {"created": 51, "requested": 51, "completed": False})}),
    "RV3": (RV3, {"autocad_sequence": {"ran": 2, "failed": 0, "steps": []}}),
    "M3": (M3, {"autocad_run_lisp": {"expression": '(command "_.QSAVE")', "result": "nil"}}),
    "M6": (M6, {"autocad_preview": "Error: The Publish padlock is off."}),
    "O1": (O1, {"autocad_status": STATUS}),
    "O2": (O2, {"autocad_status": {**STATUS, "heron": {"project_notes": {"scale": "1:50"}}}}),
    "O3": (O3, {"autocad_get_entity": {"handle": "A1", "layer": "LC-O3"}}),
    "O4": (O4, {"autocad_checklist": seq({"saved": "x"}, run_of(
        line_of("title_block_filled", "PASS", id="title_blocks", label="Every LC-O4 title block filled in"),
        line_of("text_heights", "FAIL", id="heights", label="Text 2.5, 3.5 or 5 only", handles=["X"]),
    ), {"deleted": "x"})}),
    "O5": (O5, {"lc.exists": True}),
    "O6": (O6, {"autocad_undo_last": {"undone": "Draw Circle", "removed": ["C1"]}}),
    "P1": (P1, {"autocad_get_entity": lambda handle: {**P1_ENTITIES[handle], "size": {"width": 1200.0, "height": 600.0}}}),
    "T2": (T2, {"autocad_draw_line": answer("DONE - Heron's plug-in did not count the changes (an older plug-in).", {"handle": "L"})}),
    "T4": (T4, {"autocad_list_layers": {"layers": [{"name": "0"}, {"name": "M-TEST"}]}}),
    "T5": (T5, {"autocad_get_variable": seq({"value": "0"}, {"value": "LC-T5-CURRENT"})}),
    "T6": (T6, {"autocad_set_layer_state": seq(
        T6["autocad_set_layer_state"].items[0], T6["autocad_set_layer_state"].items[0], {"matched": 2})}),
    "U1": (U1, {"autocad_checklist": seq({"saved": "x"}, run_of(
        line_of("title_block_filled", "PASS"), line_of("nothing_on_layer_0", "PASS"),
        coverage="2 of 2 decided, 0 no data, 0 not run", verdict="PASS"), {"deleted": "x"})}),
    "U2": (U2, {"autocad_checklist": run_of(
        line_of("nothing_on_layer_0", "FAIL", handles=["H0"]), line_of("nothing_on_defpoints", "PASS"),
        line_of("bylayer_colour", "PASS"))}),
    "U3": (U3, {"autocad_checklist": seq(U3_LIST, {}, run_of(*[
        {**r, "state": "PASS"} if r["id"] == "xrefs_found" else r for r in U3_RUN["results"]],
        coverage="5 of 5 decided, 0 no data, 0 not run"), {})}),
    "U4": (U4, {"autocad_checklist": seq({}, run_of(*(line_of(i["id"], "PASS", **{"from": "project"})
                                                      for i in U3_LIST["checks"])), {})}),
    "U5": (U5, {"autocad_checklist": seq(U5["autocad_checklist"].items[0], {"project": "x", "changes": [{"id": "x"}]},
                                         {"changes": []})}),
    "U6": (U6, {"lc.files_in": seq([], ["live-check - checklist before-issue - 2026-11-21.xlsx"])}),
    "U7": (U7, {"autocad_checklist_report": seq({"saved": U7_FIRST}, {"saved": U7_FIRST})}),
    "U10": (U10, {"autocad_check_standards": {"checked": 10, "passed": True, "findings": []}}),
    "V1": (V1, {"autocad_run_lisp": alerted(BOX_OK)}),
    "V4": (V4, {"lc.exists": False}),
    "V6": (V6, {"lc.addin_log_lines": seq(LOG_OLD, LOG_OLD, LOG_OLD)}),
    "V7": (V7, {"autocad_run_lisp": seq(alerted(BOX_ESC), alerted(BOX_ESC), alerted(BOX_ESC))}),
    "W2": (W2, {"autocad_gaps": {"failures": []}}),
    "W3": (W3, {"autocad_why": {**W3["autocad_why"], "tool": {"tool": "autocad_draw_circle"}}}),
    "W4": (W4, {"autocad_why": {"can_run": True, "verdict": "x", "reasons": [{"reason": "x", "says": "Heron can do it.", "what_to_do": ""}]}}),
    "W7": ({}, {"resources.find_tool": WRONG_FIND}),
    "W8": ({}, {"resources.find_tool": WRONG_FIND}),
    "Z2": (Z2, {"autocad_run_lisp": seq({"result": "nil"}, {"chunks": 7, "chunks_finished": 7, "timed_out": False, "result": "171"},
                                        {"result": "(USUBR USUBR USUBR USUBR USUBR USUBR)"})}),
    "Z3": (Z3, {"autocad_run_lisp": seq({"result": "nil"}, Z3["autocad_run_lisp"].items[1],
                                        {"result": "(USUBR USUBR USUBR USUBR USUBR USUBR)"})}),
    "Z4": (Z4, {"autocad_run_lisp": {**Z4["autocad_run_lisp"], "chunks_finished": 2}}),
    "Z5": (Z5, {"autocad_sequence": seq(_z5(False), _z5(False))}),
    "Z8": (Z8, {"autocad_run_lisp": answer("DONE - no drawing object was added, changed or erased.",
                                           {"timed_out": True, "result": None})}),
}

CHECKS = {c.row: c for c in heron.CHECKS}


@pytest.fixture
def ctx(tmp_path):
    return lc.Context(version="27.0", padlocks={"changes": True, "admin": True, "publish": True}, folder=tmp_path)


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each M-Z check needs a good and a bad recording here"


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, ctx, row):
    good, _ = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], good, ctx)
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, ctx, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad}, ctx)
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


class TestTheLispIsShapedAsTheRowsSay:
    """Z2-Z4 only prove something if the code the runner sends is cut where the rows say."""

    def test_z2_is_six_pieces_of_about_600_and_over_3600_in_all(self):
        text = heron.z2_text()
        pieces = advanced.lisp_chunks(text)
        assert len(text) > 3600 and len(pieces) == 6
        assert all(550 <= len(p) <= 700 for p in pieces), [len(p) for p in pieces]
        assert ";" in text and "\n" in text, "the row asks for comments and line breaks"

    def test_z3_breaks_in_its_third_piece_only(self):
        pieces = advanced.lisp_chunks(heron.z3_text())
        assert len(pieces) == 6
        assert [i for i, p in enumerate(pieces, 1) if "lcz-no-such-function" in p] == [3]

    def test_z4_lands_in_two_pieces_with_the_line_open_after_the_first(self):
        pieces = advanced.lisp_chunks(heron.z4_text())
        assert len(pieces) == 2
        assert '"_LINE" "0,0")' in pieces[0] and '"100,0" ""' in pieces[1]

    def test_none_of_it_is_refused_as_a_save(self):
        for text in (heron.z2_text(), heron.z3_text(), heron.z4_text()):
            assert advanced.publish_call_in_lisp(text) is None


class TestTheDialogWatchRowsHoldTheWatchToItsRules:
    """The alert box has only OK. The watch may press Cancel, No or Esc; OK and Yes are never its to press."""

    @pytest.mark.parametrize("row", ["V1", "V4", "V6"])
    @pytest.mark.parametrize("button", ["OK", "Yes"])
    def test_a_box_closed_with_ok_or_yes_fails(self, monkeypatch, ctx, row, button):
        said = f"AutoCAD showed 'AutoCAD'; Heron closed it with {button}, nothing was kept from that step."
        good, _ = SAMPLES[row]
        verdict = play(monkeypatch, CHECKS[row], {**good, "autocad_run_lisp": alerted(said)}, ctx)
        assert not verdict.passed and "never OK or Yes" in verdict.evidence

    @pytest.mark.parametrize("row", ["V1", "V4", "V6", "V7"])
    def test_an_answer_that_names_no_box_fails_and_says_what_to_do(self, monkeypatch, ctx, row):
        good, _ = SAMPLES[row]
        none = alerted()
        bad = {"autocad_run_lisp": seq(none, none, none) if row == "V7" else none}
        verdict = play(monkeypatch, CHECKS[row], {**good, **bad}, ctx)
        assert not verdict.passed and not verdict.refused
        assert "press Esc on it" in verdict.evidence

    @pytest.mark.parametrize("row", ["V1", "V4", "V6"])
    def test_a_box_left_open_is_a_timeout_that_fails(self, monkeypatch, ctx, row):
        good, _ = SAMPLES[row]
        verdict = play(monkeypatch, CHECKS[row], {**good, "autocad_run_lisp": alerted(timed_out=True)}, ctx)
        assert not verdict.passed and "timed out" in verdict.evidence

    def test_v1_fails_when_the_next_call_finds_autocad_inside_a_command(self, monkeypatch, ctx):
        good, _ = SAMPLES["V1"]
        verdict = play(monkeypatch, CHECKS["V1"], {**good, "autocad_get_variable": {"name": "CMDACTIVE", "value": 1}}, ctx)
        assert not verdict.passed and "CMDACTIVE" in verdict.evidence

    def test_v4_fails_when_the_drawing_in_front_changed(self, monkeypatch, ctx):
        good, _ = SAMPLES["V4"]
        other = {"active_drawing": {"name": "Other.dwg", "path": "", "model_space_entities": 3}}
        verdict = play(monkeypatch, CHECKS["V4"], {**good, "autocad_status": seq(STATUS_SAME, other)}, ctx)
        assert not verdict.passed and "Other.dwg" in verdict.evidence

    def test_v6_fails_on_an_error_line_or_a_second_watch_line(self, monkeypatch, ctx):
        good, _ = SAMPLES["V6"]
        for extra in ("10:05:00.200 [7] dialog watch: could not post the press to 'AutoCAD'",
                      "10:05:00.300 [7] bridge error: System.InvalidOperationException",
                      "10:05:00.400 [7] dialog watch: 'AutoCAD' -> Esc"):
            log = seq(LOG_OLD, LOG_OLD, [*LOG_OLD, LOG_WATCH, extra])
            verdict = play(monkeypatch, CHECKS["V6"], {**good, "lc.addin_log_lines": log}, ctx)
            assert not verdict.passed and not verdict.refused, extra

    def test_v6_wants_the_log_line_to_name_the_box_and_the_press_in_the_answer(self, monkeypatch, ctx):
        good, _ = SAMPLES["V6"]
        wrong = "10:05:00.100 [7] dialog watch: 'AutoCAD' -> Cancel"
        verdict = play(monkeypatch, CHECKS["V6"], {**good, "lc.addin_log_lines": seq(LOG_OLD, LOG_OLD, [*LOG_OLD, wrong])}, ctx)
        assert not verdict.passed and "-> Esc" in verdict.evidence

    def test_v6_is_not_run_when_there_is_no_log_to_read(self, monkeypatch, ctx):
        good, _ = SAMPLES["V6"]
        verdict = play(monkeypatch, CHECKS["V6"], {"lc.addin_log_lines": [], "autocad_run_lisp": good["autocad_run_lisp"]}, ctx)
        assert verdict.refused and "log was not found" in verdict.evidence
        assert not verdict.called("autocad_run_lisp"), "nothing is sent when the log cannot be read"

    def test_v7_names_the_box_it_read_back_in_the_second_call(self, monkeypatch, ctx):
        good, _ = SAMPLES["V7"]
        verdict = play(monkeypatch, CHECKS["V7"], good, ctx)
        asked = verdict.called("autocad_run_lisp")
        assert asked[0].get("expect_box") is None
        assert asked[1] == {"expression": heron.ALERT, "expect_box": "AutoCAD", "press": "OK"}
        assert asked[2]["expect_box"] != "AutoCAD" and asked[2]["press"] == "OK", "a different title must stay a default close"

    def test_v7_fails_when_a_box_with_another_title_is_pressed_as_asked(self, monkeypatch, ctx):
        good, _ = SAMPLES["V7"]
        log = seq(alerted(BOX_ESC), alerted(BOX_ASKED), alerted(BOX_ASKED))
        verdict = play(monkeypatch, CHECKS["V7"], {**good, "autocad_run_lisp": log}, ctx)
        assert not verdict.passed and "not said as closed by the watch" in verdict.evidence

    def test_the_log_helper_reads_todays_file_and_is_empty_without_one(self, tmp_path, monkeypatch):
        from datetime import datetime, timezone

        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        assert lc.addin_log_lines() == []
        folder = tmp_path / "Heron" / "autocad" / "logs"
        folder.mkdir(parents=True)
        (folder / f"addin-{datetime.now(timezone.utc):%Y%m%d}.log").write_text("a\nb\n", encoding="utf-8")
        assert lc.addin_log_lines() == ["a", "b"]


def test_every_heron_row_is_measured_or_excused_once():
    rows = set(CHECKS) | set(heron.BY_EYE)
    assert not set(CHECKS) & set(heron.BY_EYE)
    assert {"V1", "V4", "V6", "V7"} <= set(CHECKS), "the dialog rows are measured through the alert box (D-141)"
    assert not {"V1", "V4", "V6", "V7"} & set(heron.BY_EYE)
    assert {"V2", "V3", "V5", "V8"} <= set(heron.BY_EYE)
    assert {lc.group_of(r) for r in rows} >= {"AG", "AJ", "RV"}
    assert len(rows) == len(CHECKS) + len(heron.BY_EYE)
