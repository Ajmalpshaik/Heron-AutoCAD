"""The AP and AM live checks judge right: PASS on a good recorded answer, FAIL on a bad one.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py). That proves the judging and the arguments, not AutoCAD;
only a live run does that. The two things the drawing checks do by hand
(erasing a line, reading the page setup) are recorded as "own.<name>".
"""

from __future__ import annotations

import inspect
import json
import math
from dataclasses import dataclass
from typing import Any

import pytest
from live_fakes import Raw, Sequence, load, play, seq

drawing = load("live_check_drawing")
lc = load("live_common")

from autocad_mcp.tools import document  # noqa: E402

OWN = ("by_hand_erase", "page_setup")


def P(row: str, x: float, y: float, z: float | None = None) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y, 0.0 if z is None else z]


def P2(row: str, x: float, y: float) -> list[float]:
    return P(row, x, y)[:2]


def drawn(*handles: str) -> dict:
    return {"created": len(handles), "failed": 0, "requested": len(handles), "handles": list(handles)}


def table(entities: dict) -> callable:
    return lambda handle: entities[handle]


def done(payload: dict) -> str:
    """A change job's answer: its plain first line, then the tool's own words (D-62)."""
    return f"DONE - 1 added.\n\n{json.dumps(payload)}"


def refused(message: str) -> str:
    return f"REFUSED - the tool turned the job down; nothing was changed.\n\nError: {message}"


def point(row: str, handle: str, x: float, y: float) -> dict:
    return {"handle": handle, "type": "point", "layer": "0", "position": P(row, x, y)}


def points(row: str, handles: str, *places: tuple[float, float]) -> dict:
    return {h: point(row, h, x, y) for h, (x, y) in zip(handles.split(), places, strict=True)}


@dataclass
class Picture:
    data: bytes


PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def preview(info: dict, pictures: int = 1) -> Raw:
    return Raw([*(Picture(PNG) for _ in range(pictures)), json.dumps(info)])


STATUS = {"active_drawing": {"name": "Drawing1.dwg", "model_space_entities": 12}}

# --- AP -----------------------------------------------------------------------------------------

AP1_PROPS = {
    "X": {"BasePoint": P("AP1", 1000, 1000), "DirectionVector": [0.0, 1.0, 0.0]},
    "R": {"BasePoint": P("AP1", 0, 0), "DirectionVector": [0.6, 0.8, 0.0]},
}
AP1 = {
    "autocad_add_construction_line": seq(
        done({"created": True, "handle": "X", "type": "xline", "layer": "LC-AP1", "base_point": P("AP1", 1000, 1000),
              "direction": [0.0, 1.0, 0.0], "angle_degrees": 90.0, "verified": True}),
        done({"created": True, "handle": "R", "type": "ray", "layer": "LC-AP1", "base_point": P("AP1", 0, 0),
              "direction": [0.6, 0.8, 0.0], "angle_degrees": 53.130102, "verified": True}),
    ),
    "autocad_get_entity": table({"X": {"handle": "X", "type": "xline"}, "R": {"handle": "R", "type": "ray"}}),
    "lc.read_props": lambda handle, names: AP1_PROPS[handle],
}

AP2 = {
    "autocad_batch_draw": drawn("PL"),
    "autocad_add_region": done({"created": 1, "regions": [{"handle": "RG", "layer": "0", "area": 500000.0,
                                                         "perimeter": 3000.0, "centroid": P2("AP2", 500, 250)}],
                                "verified": True, "outlines_kept": ["PL"]}),
    "autocad_get_entity": {"handle": "RG", "type": "region", "layer": "0", "area": 500000.0},
    "lc.read_props": {"Perimeter": 3000.0, "Centroid": P2("AP2", 500, 250)},
    "lc.exists": True,
    "autocad_get_variable": {"name": "DELOBJ", "value": 3},
}

AP4 = {
    "autocad_batch_draw": drawn("PL", "T"),
    "autocad_status": STATUS,
    "autocad_add_region": seq(
        refused("AutoCAD made no region from those. Each loop must close exactly (ends meeting), lie flat, and not "
                "cross itself; open polylines need closing first (autocad_join_curves). AutoCAD said: Invalid input"),
        refused("T is a text. A region is made from lines, arcs, circles, ellipses, splines and polylines that "
                "close a loop."),
    ),
}


def donut(row: str, handle: str, x: float, radius: float) -> dict:
    return {"handle": handle, "type": "polyline", "layer": "LC-AP5", "closed": True, "vertex_count": 2,
            "vertices": [P2(row, x - radius, 0), P2(row, x + radius, 0)], "length": 2 * math.pi * radius}


AP5_WIDTHS = {"D1": 25.0, "D2": 25.0, "D3": 15.0}
AP5 = {
    "autocad_get_variable": lambda name: {"name": name, "value": 1},
    "autocad_add_donut": seq(
        done({"created": 2, "handles": ["D1", "D2"], "type": "polyline", "width": 25.0, "centreline_radius": 62.5,
              "verified": True}),
        done({"created": 1, "handles": ["D3"], "handle": "D3", "type": "polyline", "width": 15.0,
              "centreline_radius": 7.5, "verified": True}),
        done({"created": 1, "handles": ["D4"], "handle": "D4", "width": 25.0, "verified": True,
              "note": "FILLMODE is 0 in this drawing, so donuts show as outlines only, not filled. Set FILLMODE "
                      "to 1 and regen to see them filled."}),
    ),
    "autocad_get_entity": table({"D1": donut("AP5", "D1", 0, 62.5), "D2": donut("AP5", "D2", 500, 62.5),
                                 "D3": donut("AP5", "D3", 1000, 7.5)}),
    "lc.read_props": lambda handle, names: {"ConstantWidth": AP5_WIDTHS[handle]},
    "autocad_drawing_setup": seq(
        done({"changed": [{"variable": "FILLMODE", "from": 1, "to": 0}], "unchanged": [], "failed": []}),
        done({"changed": [{"variable": "FILLMODE", "from": 0, "to": 1}], "unchanged": [], "failed": []}),
    ),
}

POINT_NOTE = ("Points show as a dot or not at all with this drawing's point style. To see them, "
              "autocad_drawing_setup point_style='x'.")
AP6 = {
    "autocad_batch_draw": drawn("L"),
    "autocad_get_variable": {"name": "PDMODE", "value": 0},
    "autocad_divide_curve": done({"placed": 3, "kind": "points", "handles": ["P1", "P2", "P3"], "run_length": 1000.0,
                                  "step": 250.0, "left_at_end": 0.0, "closed": False, "note": POINT_NOTE}),
    "autocad_get_entity": table(points("AP6", "P1 P2 P3", (250, 0), (500, 0), (750, 0))),
}

AP7_POINTS = {**points("AP7", "C1 C2 C3 C4", (100, 0), (0, 100), (-100, 0), (0, -100)),
              **points("AP7", "R1 R2 R3 R4", (1000, 0), (1300, 0), (1400, 200), (1100, 200))}
AP7 = {
    "autocad_batch_draw": drawn("C", "R"),
    "autocad_divide_curve": seq(
        done({"placed": 4, "kind": "points", "handles": ["C1", "C2", "C3", "C4"], "closed": True, "left_at_end": 0.0}),
        done({"placed": 4, "kind": "points", "handles": ["R1", "R2", "R3", "R4"], "closed": True, "left_at_end": 0.0}),
    ),
    "autocad_get_entity": table(AP7_POINTS),
}

AP8_POINTS = {**points("AP8", "A1 A2 A3", (300, 0), (600, 0), (900, 0)),
              **points("AP8", "B1 B2 B3", (250, 0), (500, 0), (750, 0)),
              **points("AP8", "C1 C2 C3", (700, 0), (400, 0), (100, 0))}
AP8 = {
    "autocad_batch_draw": drawn("L"),
    "autocad_divide_curve": seq(
        done({"placed": 3, "kind": "points", "handles": ["A1", "A2", "A3"], "left_at_end": 100.0}),
        done({"placed": 3, "kind": "points", "handles": ["B1", "B2", "B3"], "left_at_end": 0.0}),
        done({"placed": 3, "kind": "points", "handles": ["C1", "C2", "C3"], "left_at_end": 100.0}),
    ),
    "autocad_get_entity": table(AP8_POINTS),
}


def support(handle: str, x: float, y: float, turn: float) -> dict:
    return {"handle": handle, "type": "block", "layer": "LC-AP9-M-SUPPORT", "block_name": "LC-AP9-SUPPORT",
            "insertion_point": P("AP9", x, y, 2700.0), "rotation_degrees": turn, "scale": [1.0, 1.0, 1.0]}


AP9_BLOCKS = {"S1": support("S1", 500, 0, 0.0), "S2": support("S2", 600, 400, 90.0),
              "S3": support("S3", 600, 100, 90.0), "S4": support("S4", 200, 0, 0.0)}
AP9 = {
    "autocad_batch_draw": drawn("PL", "AR"),
    "autocad_move_entities": done({"moved": 1, "handles": ["PL"], "displacement": [0, 0, 2700]}),
    "lc.read_props": {"Elevation": 2700.0},
    "autocad_make_block": done({"created": True, "block": "LC-AP9-SUPPORT", "handle": None}),
    "autocad_divide_curve": seq(
        done({"placed": 2, "kind": "block", "handles": ["S1", "S2"], "left_at_end": 200.0, "block": "LC-AP9-SUPPORT"}),
        done({"placed": 2, "kind": "block", "handles": ["S3", "S4"], "left_at_end": 200.0, "block": "LC-AP9-SUPPORT"}),
    ),
    "autocad_get_entity": table(AP9_BLOCKS),
}

AP10 = {
    "lc.by_hand_line": seq("T", "S"),
    "autocad_status": STATUS,
    "autocad_divide_curve": seq(
        refused("T is a line that slopes in Z (from 0 to 500). Divide and measure work on runs that are flat; "
                "draw a flat line to mark along."),
        refused("S is a line that slopes in Z (from 0 to 500). Divide and measure work on runs that are flat; "
                "draw a flat line to mark along."),
    ),
}

# --- AM -----------------------------------------------------------------------------------------


def sheet_preview(row: str, detail: int, whole: float = 4.21, close: float | None = None) -> Raw:
    box = (P2(row, 0, 0), P2(row, 841, 594))
    info: dict[str, Any] = {"area": "extents", "layout": "Model", "size": "Sun Hi-Res (1600.00 x 1280.00 Pixels)",
                            "pixels": [1600, 1280], "smallest_clear_text": whole,
                            "plotted": {"min": box[0], "max": box[1], "width": 841.0, "height": 594.0}}
    parts = document._detail_parts(box, detail)
    info["detail"] = [{"picture": n, "part": name, "corner1": low, "corner2": high}
                      for n, (name, low, high) in enumerate(parts, start=2)]
    info["detail_smallest_clear_text"] = close if close is not None else document._clear_text(parts[0][1:], (1600, 1280))
    return preview(info, 1 + detail * detail)


SHEET = {"lc.new_drawing": "Drawing2.dwg", "lc.close_drawing": None, "lc.activate": None}

AM2 = {
    **SHEET,
    "autocad_batch_draw": drawn("F", "T1", "T2", "T3", "T4"),
    "autocad_preview": seq(sheet_preview("AM2", 2), sheet_preview("AM2", 3)),
}

SETUP = {"layout": "Model", "ConfigName": "None", "CanonicalMediaName": "ISO_A4_(210.00_x_297.00_MM)", "PlotType": 0,
         "UseStandardScale": True, "StandardScale": 0, "PlotRotation": 1, "CenterPlot": False, "StyleSheet": ""}
AM3_INFO = {"area": "window", "layout": "Model", "size": "Sun Hi-Res (1600.00 x 1280.00 Pixels)", "pixels": [1600, 1280],
            "detail": [{"picture": n, "part": "x"} for n in range(2, 6)]}
AM3 = {
    "autocad_batch_draw": drawn("R"),
    "own.page_setup": seq(SETUP, dict(SETUP)),
    "autocad_get_variable": {"name": "BACKGROUNDPLOT", "value": 2},
    "autocad_preview": preview(AM3_INFO, 5),
}


def plotted(row: str, x: float, y: float) -> dict:
    return {"area": "extents", "layout": "Model", "size": "Sun Hi-Res (1600.00 x 1280.00 Pixels)", "pixels": [1600, 1280],
            "smallest_clear_text": round(8 * max(x / 1600, y / 1280), 3),
            "plotted": {"min": P2(row, 0, 0), "max": P2(row, x, y), "width": float(x), "height": float(y)}}


AM4 = {
    **SHEET,
    "autocad_batch_draw": seq(drawn("F", "T1", "T2", "T3", "T4"), drawn("FAR")),
    "autocad_preview": seq(preview(plotted("AM4", 100010, 100000)), preview(plotted("AM4", 841, 594))),
    "own.by_hand_erase": None,
}


AM8 = {
    **SHEET,
    "autocad_batch_draw": seq(drawn("F", "T1", "T2", "T3", "T4"), drawn("FAR")),
    "autocad_preview": preview({**plotted("AM8", 841, 594), "extents_note": "EXTMIN/EXTMAX still reach ... ZOOM Extents."}),
    "own.by_hand_erase": None,
}

def sized(width: int, height: int) -> Raw:
    return preview({"area": "window", "layout": "Model", "size": f"Sun Hi-Res ({width}.00 x {height}.00 Pixels)",
                    "pixels": [width, height]})


AM5 = {
    "autocad_batch_draw": drawn("R"),
    "autocad_preview": seq(sized(3200, 2400), sized(640, 480)),
}

SKIPPED = ("No close-ups: the screen is not a plan view of the world UCS. This is the one picture; preview "
           "area='window' over one part to look closer.")
AM6 = {
    "autocad_set_3d_view": seq({"direction": [-1, -1, 1], "named": "sw_iso", "zoomed": True},
                               {"direction": [0, 0, 1], "named": "top", "zoomed": True}),
    "autocad_preview": seq(
        preview({"area": "extents", "layout": "Model", "pixels": [1600, 1280], "detail_skipped": SKIPPED}),
        "Error: detail works with area='extents' or area='window': the current view has no corners to split. "
        "Give the window's corners instead.",
    ),
}

# Each row: the good recording, and what in it goes wrong for the FAIL.
SAMPLES: dict[str, tuple[dict, dict]] = {
    "AP1": (AP1, {"lc.read_props": lambda handle, names: {
        **AP1_PROPS, "R": {**AP1_PROPS["R"], "DirectionVector": [-0.6, -0.8, 0.0]}}[handle]}),
    "AP2": (AP2, {"lc.exists": False}),
    "AP4": (AP4, {"autocad_add_region": seq(
        AP4["autocad_add_region"].items[0],
        done({"created": 1, "regions": [{"handle": "RG"}], "verified": True}),
    )}),
    "AP5": (AP5, {"lc.read_props": lambda handle, names: {"ConstantWidth": {**AP5_WIDTHS, "D3": 30.0}[handle]}}),
    "AP6": (AP6, {"autocad_get_entity": table(points("AP6", "P1 P2 P3", (0, 0), (500, 0), (1000, 0)))}),
    "AP7": (AP7, {"autocad_get_entity": table(
        {**AP7_POINTS, **points("AP7", "C1 C2 C3 C4", (0, 100), (-100, 0), (0, -100), (100, 0))})}),
    "AP8": (AP8, {"autocad_get_entity": table(
        {**AP8_POINTS, **points("AP8", "C1 C2 C3", (300, 0), (600, 0), (900, 0))})}),
    "AP9": (AP9, {"autocad_get_entity": table({**AP9_BLOCKS, "S3": support("S3", 600, 100, 270.0)})}),
    "AP10": (AP10, {"autocad_divide_curve": seq(
        AP10["autocad_divide_curve"].items[0],
        done({"placed": 1, "kind": "points", "handles": ["Q"], "left_at_end": 0.0}),
    )}),
    "AM2": (AM2, {"autocad_preview": seq(sheet_preview("AM2", 2), sheet_preview("AM2", 3, close=2.6))}),
    "AM3": (AM3, {"own.page_setup": seq(SETUP, {**SETUP, "PlotRotation": 0})}),
    "AM4": (AM4, {"autocad_preview": seq(preview(plotted("AM4", 841, 594)), preview(plotted("AM4", 841, 594)))}),
    "AM5": (AM5, {"autocad_preview": seq(sized(640, 480), sized(3200, 2400))}),
    "AM8": (AM8, {"autocad_preview": preview(plotted("AM8", 100010, 100000))}),
    "AM6": (AM6, {"autocad_preview": seq(
        sheet_preview("AM6", 2),
        AM6["autocad_preview"].items[1],
    )}),
}

CHECKS = {c.row: c for c in drawing.CHECKS}


def _own_fake(name: str, recorded: Any, calls: list) -> Any:
    signature = inspect.signature(getattr(drawing, name))
    answers = Sequence(list(recorded.items)) if isinstance(recorded, Sequence) else recorded

    async def fake(*args: Any, **kwargs: Any) -> Any:
        signature.bind(*args, **kwargs)
        calls.append(name)
        if isinstance(answers, Sequence):
            assert answers.items, f"{name} was called more often than the recording has answers for"
            return answers.items.pop(0)
        return answers

    return fake


def _unexpected(name: str) -> Any:
    async def fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"the check called {name}, which the recording does not cover")

    return fail


def run_row(monkeypatch: Any, row: str, answers: dict):
    """play(), with the drawing module's own by-hand helpers ("own.<name>") recorded as well."""
    calls: list[str] = []
    rest = {k: v for k, v in answers.items() if not k.startswith("own.")}
    for name in OWN:
        key = f"own.{name}"
        fake = _own_fake(name, answers[key], calls) if key in answers else _unexpected(key)
        monkeypatch.setattr(drawing, name, fake)
    return play(monkeypatch, CHECKS[row], rest)


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each AP / AM check needs a good and a bad recording here"


def test_every_row_is_scripted_or_by_eye_once():
    rows = [*CHECKS, *drawing.BY_EYE]
    assert len(rows) == len(set(rows))
    want = {f"AP{n}" for n in range(1, 12)} | {f"AM{n}" for n in range(1, 9)}  # AM7: D-141; AM8: D-150
    assert set(rows) == want
    assert all(len(why.split()) >= 4 for why in drawing.BY_EYE.values())


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    good, _ = SAMPLES[row]
    verdict = run_row(monkeypatch, row, good)
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = run_row(monkeypatch, row, {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


def test_am5_records_a_plotter_with_one_size(monkeypatch):
    verdict = run_row(monkeypatch, "AM5", {**AM5, "autocad_preview": seq(sized(1600, 1280), sized(1600, 1280))})
    assert verdict.passed and "the same size" in verdict.evidence, verdict.evidence


def test_am4_records_extents_that_stay_stale(monkeypatch):
    stale = {**AM4, "autocad_preview": seq(preview(plotted("AM4", 100010, 100000)),
                                           preview(plotted("AM4", 100010, 100000)))}
    verdict = run_row(monkeypatch, "AM4", stale)
    assert verdict.passed and "stale" in verdict.evidence, verdict.evidence


def test_ap5_with_fill_already_off_needs_the_note(monkeypatch):
    off = {**AP5, "autocad_get_variable": lambda name: {"name": name, "value": 0}}
    off.pop("autocad_drawing_setup")
    verdict = run_row(monkeypatch, "AP5", off)
    assert not verdict.passed and "no note" in verdict.evidence, verdict.evidence
