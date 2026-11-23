"""The BH live checks judge right: PASS on a good recorded answer, FAIL on a bad one.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py). That proves the judging and the arguments, not AutoCAD;
only a live run does that.
"""

from __future__ import annotations

import math

import pytest
from live_fakes import load, play, seq

lengthen = load("live_check_lengthen")
lc = load("live_common")


def P(row: str, x: float, y: float) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y, 0.0]


def drawn(*handles: str) -> dict:
    return {"created": len(handles), "failed": 0, "requested": len(handles), "handles": list(handles)}


def line(handle: str, a: list[float], b: list[float], layer: str = "LC", **extra) -> dict:
    return {"handle": handle, "type": "line", "layer": layer, "start": a, "end": b, **extra}


def arc(handle: str, row: str, centre: tuple[float, float], radius: float, start: float, end: float, layer: str = "LC") -> dict:
    return {"handle": handle, "type": "arc", "layer": layer, "center": P(row, *centre), "radius": radius,
            "start_angle_degrees": start, "end_angle_degrees": end}


def table(entities: dict) -> callable:
    return lambda handle: entities[handle]


def done(n: int = 1) -> dict:
    return {"done": n, "objects": [{"handle": "X"}]}


def count(*n: int) -> object:
    return seq(*({"active_drawing": {"name": "Drawing1.dwg", "model_space_entities": k}} for k in n))


def refused(reason: str) -> dict:
    return {"done": 0, "objects": [], "failed": [{"handle": "X", "reason": reason}]}


# --- BH1 ---------------------------------------------------------------------------------------
BH1 = {
    "autocad_batch_draw": drawn("L"),
    "autocad_lengthen": done(),
    "autocad_get_entity": seq(
        line("L", P("BH1", 0, 0), P("BH1", 1500, 0), "LC-BH1"),
        line("L", P("BH1", 200, 0), P("BH1", 1500, 0), "LC-BH1"),
        line("L", P("BH1", 200, 0), P("BH1", 1500, 0), "LC-BH1"),
    ),
}
# --- BH2 ---------------------------------------------------------------------------------------
BH2 = {
    "autocad_batch_draw": drawn("A", "B"),
    "autocad_lengthen": done(),
    "autocad_get_entity": table({
        "A": line("A", P("BH2", 0, 0), P("BH2", 2400, 0)),
        "B": line("B", P("BH2", 500, 1000), P("BH2", 1000, 1000)),
    }),
}
# --- BH3 ---------------------------------------------------------------------------------------
BH3 = {
    "autocad_batch_draw": drawn("R"),
    "autocad_lengthen": done(),
    "autocad_get_entity": seq(arc("R", "BH3", (0, 0), 500, 0, 135), arc("R", "BH3", (0, 0), 500, 67.5, 135)),
}
# --- BH4 ---------------------------------------------------------------------------------------
BH4 = {
    "autocad_batch_draw": drawn("P"),
    "autocad_lengthen": done(),
    "autocad_polyline_info": seq(
        {"total_length": 800.0, "vertices": [P("BH4", 0, 0)[:2], P("BH4", 800, 0)[:2]]},
        {"total_length": 1000.0, "vertices": [P("BH4", -200, 0)[:2], P("BH4", 800, 0)[:2]]},
    ),
}
# --- BH5 ---------------------------------------------------------------------------------------
X5 = math.sqrt(550**2 - 350**2)
BH5_ENTITIES = {
    "N": {"handle": "N", "type": "arc", "layer": "LC-BH5-LINE", "center": P("BH5", X5, 350), "radius": 50.0},
    "L": line("L", P("BH5", X5, 300), P("BH5", 1500, 300), "LC-BH5-LINE"),
    "R": arc("R", "BH5", (0, 0), 500, 39.5, 90),
}
BH5 = {
    "autocad_batch_draw": drawn("R", "L"),
    "autocad_fillet_chamfer": {"operation": "fillet", "objects": ["L", "R"], "arc": "N"},
    "autocad_get_entity": table(BH5_ENTITIES),
}
# --- BH6 ---------------------------------------------------------------------------------------
BH6 = {
    "autocad_batch_draw": drawn("A", "B"),
    "autocad_fillet_chamfer": {"operation": "fillet", "objects": ["A", "B"], "arc": "N"},
    "autocad_get_entity": {"handle": "N", "type": "arc", "center": P("BH6", 400, math.sqrt(550**2 - 400**2)),
                           "radius": 50.0},
}
# --- BH7 ---------------------------------------------------------------------------------------
def poly(handle: str, row: str, *points: tuple[float, float]) -> dict:
    return {"handle": handle, "type": "polyline", "layer": "LC-BH7", "vertices": [P(row, x, y)[:2] for x, y in points]}


BH7_ENTITIES = {
    "A": poly("A", "BH7", (0, 0), (1000, 0), (1000, 500)),
    "B": poly("B", "BH7", (1500, 900), (1500, 600), (1100, 600)),
    "N": {"handle": "N", "type": "arc", "center": P("BH7", 1100, 500), "radius": 100.0},
}
BH7 = {
    "autocad_batch_draw": drawn("A", "B"),
    "autocad_fillet_chamfer": {"operation": "fillet", "objects": ["A", "B"], "ends": ["end", "end"], "arc": "N"},
    "autocad_get_entity": table(BH7_ENTITIES),
    "autocad_status": count(10, 11),
}
# --- BH8 ---------------------------------------------------------------------------------------
turn = math.atan2(300, 400) + 40 / 500
BH8 = {
    "autocad_batch_draw": drawn("R", "L"),
    "autocad_fillet_chamfer": {"operation": "chamfer", "objects": ["L", "R"], "chamfer_line": "C"},
    "autocad_get_entity": line("C", P("BH8", 440, 300), P("BH8", 500 * math.cos(turn), 500 * math.sin(turn))),
}
# --- BH9 ---------------------------------------------------------------------------------------
BH9 = {
    "autocad_batch_draw": drawn("C", "O", "L", "K", "T"),
    "autocad_lengthen": seq(
        refused("X is a closed outline: it has no end to lengthen."),
        refused("X is a circle; this works on a line, arc, polyline."),
        refused("That leaves 0 of it (400 long now): it would vanish."),
        refused("K is on the locked layer 'LC-BH9-LOCKED'. Unlock it with autocad_set_layer_state."),
    ),
    "autocad_get_entity": line("L", P("BH9", 0, 1000), P("BH9", 400, 1000)),
    "autocad_set_layer_state": {"matched": 1},
    "autocad_fillet_chamfer": "Error: O is a circle. Heron fillets and chamfers two lines, a line and an arc, ...",
    "autocad_status": count(20, 20),
}

SAMPLES: dict[str, tuple[dict, dict]] = {
    "BH1": (BH1, {"autocad_get_entity": seq(
        line("L", P("BH1", 0, 0), P("BH1", 1000, 0), "LC-BH1"),
        line("L", P("BH1", 200, 0), P("BH1", 1500, 0), "LC-BH1"),
        line("L", P("BH1", 200, 0), P("BH1", 1500, 0), "LC-BH1"))}),
    "BH2": (BH2, {"autocad_get_entity": table({
        "A": line("A", P("BH2", 0, 0), P("BH2", 2400, 0)),
        "B": line("B", P("BH2", 0, 1000), P("BH2", 500, 1000))})}),
    "BH3": (BH3, {"autocad_get_entity": seq(arc("R", "BH3", (0, 0), 500, 0, 90), arc("R", "BH3", (0, 0), 500, 67.5, 135))}),
    "BH4": (BH4, {"autocad_polyline_info": seq(
        {"total_length": 800.0, "vertices": [P("BH4", 0, 0)[:2], P("BH4", 800, 0)[:2], P("BH4", 800, 100)[:2]]},
        {"total_length": 1000.0, "vertices": [P("BH4", 0, 0)[:2], P("BH4", 1000, 0)[:2]]})}),
    "BH5": (BH5, {"autocad_get_entity": table({**BH5_ENTITIES,
                                               "N": {**BH5_ENTITIES["N"], "center": P("BH5", 400, 350)}})}),
    "BH6": (BH6, {"autocad_get_entity": {"handle": "N", "type": "arc", "center": P("BH6", 400, 300), "radius": 50.0}}),
    "BH7": (BH7, {"autocad_status": count(10, 12)}),
    "BH8": (BH8, {"autocad_get_entity": line("C", P("BH8", 440, 300), P("BH8", 500 * math.cos(math.atan2(300, 400)),
                                                                          500 * math.sin(math.atan2(300, 400))))}),
    "BH9": (BH9, {"autocad_status": count(20, 21)}),
}

CHECKS = {c.row: c for c in lengthen.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each BH check needs a good and a bad recording here"


def test_the_rows_with_no_check_have_their_reason():
    assert sorted(lengthen.BY_EYE) == ["BH10", "BH11"]
    assert all(lengthen.BY_EYE.values())


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    good, _ = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], good)
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"
