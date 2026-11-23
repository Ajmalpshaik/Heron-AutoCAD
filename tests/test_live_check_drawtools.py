"""The AI live checks (the drawing tools on a UCS, batch fills, multilines, splines) judge right from recorded answers."""

from __future__ import annotations

import math

import pytest
from live_fakes import load, play, seq

drawtools = load("live_check_drawtools")
lc = load("live_common")

STATUS = {"active_drawing": {"name": "Drawing1.dwg", "path": "", "model_space_entities": 30}}
UCS = {"rotation_degrees": 30.0, "is_world": False}


def w(row: str, x: float, y: float, turn: float = 30.0) -> list[float]:
    """The world point of a point on the row's UCS turned ``turn`` degrees."""
    o = lc.origin(row)
    a = math.radians(turn)
    return [o[0] + x * math.cos(a) - y * math.sin(a), o[1] + x * math.sin(a) + y * math.cos(a)]


def P(row: str, x: float, y: float) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y]


def entities(table: dict[str, dict]):
    return lambda handle: table[handle]


def created(handle: str, **extra) -> dict:
    return {"created": True, "handle": handle, **extra}


AI1_ENT = {
    "R": {"type": "polyline", "vertices": [w("AI1", 0, 0), w("AI1", 2000, 0), w("AI1", 2000, 1000), w("AI1", 0, 1000)]},
    "A": {"type": "arc", "center": w("AI1", 0, 0), "start_angle_degrees": 30.0, "end_angle_degrees": 120.0},
    "T": {"type": "text", "insertion_point": w("AI1", 0, 1500), "rotation_degrees": 30.0},
    "B": {"type": "block", "insertion_point": w("AI1", 3000, 0), "rotation_degrees": 30.0},
}
AI1 = {
    "autocad_batch_draw": {"created": 2, "failed": 0, "handles": ["L1", "L2"]},
    "autocad_make_block": created("K", block="LC-AI1-MARK"),
    "autocad_set_ucs": {"current": UCS},
    "autocad_draw_rectangle": created("R", converted_from_ucs=UCS),
    "autocad_draw_arc": created("A", converted_from_ucs=UCS),
    "autocad_add_text": created("T", converted_from_ucs=UCS),
    "autocad_insert_block": created("B", converted_from_ucs=UCS),
    "autocad_get_entity": entities(AI1_ENT),
}


def _ai2_rect() -> list[list[float]]:
    a = math.radians(15)
    out = []
    for x, y in ((0, 0), (2000, 0), (2000, 1000), (0, 1000)):
        y += 1200
        out.append(w("AI2", x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)))
    return out


AI2_GRID = [(i, j) for i in range(3) for j in range(2)]
AI2_ENT = {"D": {"type": "dimension", "measurement": 2000.0}, "R": {"type": "polyline", "vertices": _ai2_rect()},
           **{f"C{n}": {"type": "circle", "center": w("AI2", 5000 + 600 * i, 400 * j)} for n, (i, j) in enumerate(AI2_GRID)}}
AI2 = {
    "autocad_set_ucs": {"current": UCS},
    "autocad_add_dimension": created("D", measurement=2000.0, converted_from_ucs=UCS),
    "autocad_draw_rectangle": created("R"),
    "autocad_draw_circle": created("C0"),
    "autocad_move_entities": {"moved": 1},
    "autocad_rotate_entities": {"rotated": 1},
    "autocad_array_entities": {"arrayed": 1, "new_handles": [f"C{n}" for n in range(1, 6)], "items_per_source": 6},
    "autocad_get_entity": entities(AI2_ENT),
}
FLIPPED = "Error: The drawing's current UCS is flipped (its Z points down), so text drawn here would read mirrored in that view."
AI3 = {
    "autocad_set_ucs": {"current": UCS},
    "autocad_draw_polyline": created("P"),
    "lc.read_props": {"Elevation": 3000.0},
    "autocad_add_text": FLIPPED,
    "autocad_status": STATUS,
}
AI4_ENT = {
    "H1": {"type": "hatch", "pattern": "SOLID", "color": 1, "area": 4000.0, "loop_count": 1},
    "H2": {"type": "hatch", "pattern": "SOLID", "area": 7853.9, "loop_count": 1},
    "H3": {"type": "hatch", "pattern": "SOLID", "area": 35000.0, "loop_count": 2},
}
AI4 = {"autocad_batch_draw": {"created": 3, "failed": 0, "handles": ["H1", "H2", "H3"]}, "autocad_get_entity": entities(AI4_ENT)}
AI5_ENT = {
    "M1": {"type": "mtext", "text": "NOTE 1\\PNOTE 2", "insertion_point": P("AI5", 0, 0), "width": 2000.0},
    "M2": {"type": "mtext", "text": drawtools.AI5_NOTE, "insertion_point": P("AI5", 0, -1000), "width": 3000.0},
}
AI5 = {"autocad_batch_draw": {"created": 2, "failed": 0, "handles": ["M1", "M2"]}, "autocad_get_entity": entities(AI5_ENT)}
AI6_ENT = {
    "D1": {"type": "dimension", "measurement": 5000.0, "text_override": ""},
    "D2": {"type": "dimension", "measurement": 3000.0, "text_override": "<> TYP"},
}
AI6 = {
    "autocad_batch_draw": {"created": 2, "failed": 0, "handles": ["D1", "D2"]},
    "autocad_get_entity": entities(AI6_ENT),
}
AI8 = {"autocad_draw_multiline": created("M", mitred=True, closed=True, vertices=4, scale=200.0)}
CV = {"type": "spline", "degree": 3, "control_point_count": 5, "fit_point_count": 0, "closed": False}
AI10 = {"autocad_draw_spline": created("S", control_points=5, degree=3), "autocad_get_entity": CV}
AI11_ENT = {"S1": {**CV, "closed": True, "control_point_count": 8}, "S2": {**CV, "degree": 1}, "S3": {**CV, "degree": 2}}
AI11 = {
    "autocad_draw_spline": seq(created("S1"), created("S2"), created("S3")),
    "autocad_get_entity": entities(AI11_ENT),
}
AI12_START = [P("AI12", *p) + [0.0] for p in ((0, 0), (1000, 500), (2000, 0), (3000, 800))]
AI12_END = [P("AI12", *p) + [0.0] for p in ((1000, 800), (2000, 0), (3000, 800), (4000, 0))]
AI12 = {
    "autocad_draw_spline": created("S", fit_points=4),
    "autocad_get_entity": seq({"type": "spline", "fit_point_count": 4, "fit_points": AI12_START},
                              {"type": "spline", "fit_point_count": 4, "fit_points": AI12_END}),
    "autocad_edit_spline": {"edited": True, "handle": "S", "fit_points_before": 4, "fit_points": 4},
}
AI13_FIT = [P("AI13", *p) + [0.0] for p in ((0, 5000), (1000, 5500), (2000, 5000), (3000, 5800))]
AI13 = {
    "autocad_draw_spline": seq(created("S1", control_points=4), created("S2", fit_points=4)),
    "autocad_edit_spline": seq(
        "Error: S1: this spline has no fit points: it was drawn by its control points. Nothing was changed.",
        "Error: S2: edit 0 moves point 9, but the spline has 4 (0 to 3). Nothing was changed.",
    ),
    "autocad_get_entity": seq({"type": "spline", "fit_points": AI13_FIT}, {"type": "spline", "fit_points": AI13_FIT}),
}

SAMPLES = {
    "AI1": (AI1, {"autocad_get_entity": entities({**AI1_ENT, "R": {"type": "polyline", "vertices": [
        P("AI1", 0, 0), P("AI1", 2000, 0), P("AI1", 2000, 1000), P("AI1", 0, 1000)]}})}),
    "AI2": (AI2, {"autocad_get_entity": entities({**AI2_ENT, **{f"C{n}": {"type": "circle", "center": P("AI2", 5000 + 600 * i, 400 * j)}
                                                                for n, (i, j) in enumerate(AI2_GRID)}})}),
    "AI3": (AI3, {"lc.read_props": {"Elevation": 0.0}}),
    "AI4": (AI4, {"autocad_get_entity": entities({**AI4_ENT, "H3": {**AI4_ENT["H3"], "loop_count": 1}})}),
    "AI5": (AI5, {"autocad_get_entity": entities({**AI5_ENT, "M2": {**AI5_ENT["M2"], "text": drawtools.AI5_NOTE[:300]}})}),
    "AI6": (AI6, {"autocad_get_entity": entities({**AI6_ENT, "D2": {**AI6_ENT["D2"], "measurement": 300.0}})}),
    "AI8": (AI8, {"autocad_draw_multiline": created("M", mitred=False, closed=True, vertices=5,
                                                    warning="the last corner overlaps rather than being mitred")}),
    "AI10": (AI10, {"autocad_get_entity": {**CV, "fit_point_count": 5}}),
    "AI11": (AI11, {"autocad_get_entity": entities({**AI11_ENT, "S1": {**CV, "closed": False}})}),
    "AI12": (AI12, {"autocad_get_entity": seq({"type": "spline", "fit_point_count": 4, "fit_points": AI12_START},
                                              {"type": "spline", "fit_point_count": 4, "fit_points": AI12_START})}),
    "AI13": (AI13, {"autocad_get_entity": seq({"type": "spline", "fit_points": AI13_FIT},
                                              {"type": "spline", "fit_points": AI13_FIT[:3]})}),
}
CHECKS = {c.row: c for c in drawtools.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES)


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    verdict = play(monkeypatch, CHECKS[row], SAMPLES[row][0])
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


@pytest.mark.parametrize("row", ["AI1", "AI2", "AI3"])
def test_the_ucs_is_put_back_to_the_world(monkeypatch, row):
    verdict = play(monkeypatch, CHECKS[row], SAMPLES[row][0])
    assert verdict.called("autocad_set_ucs")[-1]["mode"] == "world"


@pytest.mark.parametrize("row", ["AI1", "AI2", "AI3"])
def test_the_ucs_is_put_back_even_when_the_row_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = play(monkeypatch, CHECKS[row], {**good, **bad})
    assert not verdict.passed and verdict.called("autocad_set_ucs")[-1]["mode"] == "world"


def test_ai1_asks_every_tool_for_the_ucs(monkeypatch):
    verdict = play(monkeypatch, CHECKS["AI1"], AI1)
    for tool in ("autocad_draw_rectangle", "autocad_draw_arc", "autocad_add_text", "autocad_insert_block"):
        assert verdict.called(tool)[0]["coords"] == "ucs"


def test_a_flipped_ucs_that_still_draws_fails_ai3(monkeypatch):
    drawn = {**AI3, "autocad_add_text": created("T"), "autocad_status": seq(STATUS, {"active_drawing": {"model_space_entities": 31}})}
    verdict = play(monkeypatch, CHECKS["AI3"], drawn)
    assert not verdict.passed and "expected a refusal" in verdict.evidence


def test_every_ai_row_is_measured_or_excused_once():
    assert not set(CHECKS) & set(drawtools.BY_EYE)
    assert set(CHECKS) | set(drawtools.BY_EYE) == {f"AI{n}" for n in range(1, 15)}
