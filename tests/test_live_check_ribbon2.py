"""The AQ live checks (arrays, tiled viewports, hyperlinks, geographic location) judge right from recorded answers."""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from live_fakes import Sequence, load, play, seq

ribbon2 = load("live_check_ribbon2")
lc = load("live_common")

OWN = ("viewport_names",)


def _own_fake(name: str, recorded: Any) -> Any:
    signature = inspect.signature(getattr(ribbon2, name))
    answers = Sequence(list(recorded.items)) if isinstance(recorded, Sequence) else recorded

    async def fake(*args: Any, **kwargs: Any) -> Any:
        signature.bind(*args, **kwargs)
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
    """play(), with this module's own by-hand helpers ("own.<name>") recorded as well."""
    for name in OWN:
        key = f"own.{name}"
        monkeypatch.setattr(ribbon2, name, _own_fake(name, answers[key]) if key in answers else _unexpected(key))
    return play(monkeypatch, CHECKS[row], {k: v for k, v in answers.items() if not k.startswith("own.")})


# ---- AQ5 ------------------------------------------------------------------------

AQ5_SAID = (
    "Error: The objects are in different spaces. Array the ones in model space, or the ones on one layout, at a time. "
    "Nothing was changed.",
    "Error: The path cannot also be one of the objects to array. Nothing was changed.",
    "Error: 9 items 1500 apart need 12000 of path; this one is 10000 long, so at most 7 fit. Nothing was changed.",
)
AQ5 = {
    "autocad_batch_draw": {"created": 3, "handles": ["A1", "A2", "A3"]},
    "autocad_draw_line": {"created": True, "handle": "P1", "type": "line", "layer": "LC-AQ5"},
    "autocad_status": {"active_drawing": {"model_space_entities": 40}},
    "autocad_associative_array": seq(*AQ5_SAID),
}

# ---- AQ6 ------------------------------------------------------------------------


def tile(x1: float, y1: float, x2: float, y2: float) -> dict:
    return {"lower_left": [x1, y1], "upper_right": [x2, y2], "current": False}


TILED = {
    "one": [tile(0, 0, 1, 1)],
    "two_vertical": [tile(0, 0, 0.5, 1), tile(0.5, 0, 1, 1)],
    "four": [tile(0, 0.5, 0.5, 1), tile(0.5, 0.5, 1, 1), tile(0, 0, 0.5, 0.5), tile(0.5, 0, 1, 0.5)],
    "three_right": [tile(0.5, 0, 1, 1), tile(0, 0.5, 0.5, 1), tile(0, 0, 0.5, 0.5)],
}
BIG_ON_THE_LEFT = [tile(0, 0, 0.5, 1), tile(0.5, 0.5, 1, 1), tile(0.5, 0, 1, 0.5)]


def tiled_screen(three: list[dict] | None = None):
    """The Model tab as AutoCAD keeps it: a split changes it, a read gives it back; the answer's words always as asked."""
    state = {"now": "one"}

    def answer(layout: str | None = None) -> dict:
        if layout is not None:
            state["now"] = layout
        now = state["now"]
        tiles = three if (three is not None and now == "three_right") else TILED[now]
        return {"layout": layout, "tiles": len(tiles), "arrangement": ribbon2.WORDS[now], "viewports": tiles}

    return answer


AQ6 = {"autocad_tiled_viewports": tiled_screen(), "own.viewport_names": ["*Active", "Heron"]}

# ---- AQ9 ------------------------------------------------------------------------

URLS = ribbon2.AQ9_LINKS
OLD = {"handle": "OLD", "type": "block", "layer": "0", "links": [{"url": "x.pdf", "description": "", "location": ""}]}


def linked(*pairs: tuple[str, str]) -> dict:
    rows = [OLD] + [{"handle": h, "type": "line", "layer": "LC-AQ9", "links": [{"url": u, "description": "", "location": ""}]}
                    for h, u in pairs]
    return {"count": len(rows), "objects": rows}


def set_answer(handle: str, url: str) -> dict:
    return {"action": "set", "changed": 1, "handles": [handle],
            "objects": [{"handle": handle, "type": "line", "before": [], "after": [{"url": url}]}]}


AQ9 = {
    "autocad_batch_draw": {"created": 7, "handles": ["L1", "L2", "L3", "P1", "P2", "P3", "K"]},
    "autocad_hyperlinks": seq(
        *(set_answer(h, u) for h, u in zip(("L1", "L2", "L3"), URLS, strict=True)),
        {"action": "remove", "changed": 1, "handles": ["L2"],
         "objects": [{"handle": "L2", "type": "line", "before": [{"url": URLS[1]}], "after": []}]},
        {**set_answer("P1", URLS[1]), "failed": [{"handle": "K", "reason": "eOnLockedLayer"}]},
    ),
    "autocad_list_hyperlinks": seq(
        linked(),
        linked(("L1", URLS[0]), ("L2", URLS[1]), ("L3", URLS[2])),
        linked(("L1", URLS[0]), ("L3", URLS[2])),
        {"count": 2, "objects": [{"handle": "K", "type": "line", "layer": "LC-AQ9-LOCKED", "links": []},
                                 {"handle": "P1", "type": "line", "layer": "LC-AQ9", "links": [{"url": URLS[1]}]}]},
    ),
    "autocad_set_layer_state": {"name": "LC-AQ9-LOCKED", "locked": True},
}

# ---- AQ11 to AQ13 ------------------------------------------------------------------


def variables(**values: Any):
    return lambda name: {"name": name, "value": values[name]}


def geo(lat: float, lon: float, **extra: Any) -> dict:
    return {"located": True, "latitude": lat, "longitude": lon, "point": [0.0, 0.0, 0.0], "north_angle": 0.0,
            "coordinate_system": "WORLD-MERCATOR", "units": "Millimeters", "agrees": True,
            "sun_place": {"latitude": lat, "longitude": lon, "autocad_default": False}, **extra}


NEW = {"lc.new_drawing": "Drawing2.dwg", "lc.close_drawing": None, "lc.activate": None,
       "autocad_drawing_setup": {"dry_run": False, "changed": [], "unchanged": ["INSUNITS"], "failed": []}}
NOT_LOCATED = {"located": False, "sun_place": {"latitude": 37.795, "longitude": -122.394, "autocad_default": True}}

AQ11 = {
    **NEW,
    "autocad_get_variable": variables(INSUNITS=4, LATITUDE=25.29, LONGITUDE=51.53),
    "autocad_geo_location": {**geo(25.29, 51.53, north_angle=12.0), "made": True, "reference_form": "grid",
                             "sun_place": {"latitude": 25.29, "longitude": 51.53, "moved": True}},
    "autocad_get_geo_location": geo(25.29, 51.53, north_angle=12.0),
}


def values(*pairs: tuple[str, Any]) -> Sequence:
    return seq(*({"name": n, "value": v} for n, v in pairs))


AQ12 = {
    **NEW,
    "autocad_get_variable": values(("LATITUDE", 37.795), ("LONGITUDE", -122.394), ("LATITUDE", 9.93), ("LONGITUDE", 76.27),
                                   ("LATITUDE", 9.93), ("LONGITUDE", 76.27)),
    "autocad_get_geo_location": seq(NOT_LOCATED, NOT_LOCATED, geo(9.93, 76.27, point=[1000.0, 2000.0, 0.0])),
    "autocad_geo_location": seq(
        "Error: The drawing's place is still AutoCAD's default (San Francisco). Give the site's latitude and longitude. "
        "Nothing was changed.",
        {**geo(9.93, 76.27, point=[1000.0, 2000.0, 0.0]), "made": True, "reference_form": "grid",
         "sun_place": {"latitude": 9.93, "longitude": 76.27, "moved": False}},
    ),
    "autocad_set_sun": {"set": ["LATITUDE", "LONGITUDE"], "sun_made": False, "sun": {"latitude": 9.93, "longitude": 76.27}},
}

UTM = geo(25.29, 51.53, coordinate_system="UTM84-39N")
AQ13 = {
    **NEW,
    "autocad_get_variable": values(("INSUNITS", 0), ("INSUNITS", 4)),
    "autocad_geo_location": seq(
        "Error: The drawing has no units (INSUNITS is 0), so a metre on the ground cannot be matched to the drawing. "
        "Set the units first with autocad_drawing_setup. Nothing was changed.",
        {**UTM, "made": True, "reference_form": "grid"},
        "Error: AutoCAD does not know the coordinate system 'NOT-A-SYSTEM' (eInvalidInput). Leave it out for "
        "WORLD-MERCATOR, or give a code from AutoCAD's GEOGRAPHICLOCATION list. Nothing was changed.",
        {"removed": True, "coordinate_system": "UTM84-39N"},
    ),
    "autocad_get_geo_location": seq(NOT_LOCATED, UTM, UTM, NOT_LOCATED),
}

SAMPLES = {
    # The 9-at-1500 call was not refused: AutoCAD built an array.
    "AQ5": (AQ5, {"autocad_associative_array": seq(*AQ5_SAID[:2], {"created": True, "handle": "AR1", "items": 7})}),
    # acViewport3Right built with the big one on the left, though the answer's words say right.
    "AQ6": (AQ6, {"autocad_tiled_viewports": tiled_screen(BIG_ON_THE_LEFT)}),
    # The removed link is still listed.
    "AQ9": (AQ9, {"autocad_list_hyperlinks": seq(
        *AQ9["autocad_list_hyperlinks"].items[:2],
        AQ9["autocad_list_hyperlinks"].items[1],
        AQ9["autocad_list_hyperlinks"].items[3],
    )}),
    # North read back the wrong way round.
    "AQ11": (AQ11, {"autocad_get_geo_location": geo(25.29, 51.53, north_angle=348.0)}),
    # The location moved the sun's place.
    "AQ12": (AQ12, {"autocad_geo_location": seq(
        AQ12["autocad_geo_location"].items[0],
        {**AQ12["autocad_geo_location"].items[1], "sun_place": {"latitude": 9.93, "longitude": 76.27, "moved": True}},
    )}),
    # The refused coordinate system was kept after all.
    "AQ13": (AQ13, {"autocad_get_geo_location": seq(NOT_LOCATED, UTM, {**UTM, "coordinate_system": "NOT-A-SYSTEM"},
                                                    NOT_LOCATED)}),
}

CHECKS = {c.row: c for c in ribbon2.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each AQ check needs a good and a bad recording here"


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_good_answer_passes(monkeypatch, row):
    verdict = run_row(monkeypatch, row, SAMPLES[row][0])
    assert verdict.passed, verdict.evidence


@pytest.mark.parametrize("row", sorted(SAMPLES))
def test_a_bad_answer_fails(monkeypatch, row):
    good, bad = SAMPLES[row]
    verdict = run_row(monkeypatch, row, {**good, **bad})
    assert not verdict.passed and not verdict.refused, f"{row} passed a bad answer: {verdict.evidence}"


def test_every_aq_row_is_measured_or_excused_once():
    assert not set(CHECKS) & set(ribbon2.BY_EYE)
    assert set(CHECKS) | set(ribbon2.BY_EYE) == {f"AQ{n}" for n in range(1, 18)}


def test_titles_and_reasons_are_plain_enough():
    for check in ribbon2.CHECKS:
        assert check.group == "AQ" and len(check.title.split()) >= 3, check
    for row, reason in ribbon2.BY_EYE.items():
        assert len(reason.split()) >= 4, row


def test_the_array_rows_are_left_to_a_person_because_they_erase():
    for row in ("AQ1", "AQ2", "AQ3", "AQ4"):
        assert "erase" in ribbon2.BY_EYE[row]


def test_a_tiled_split_puts_the_model_tab_back_to_one_even_when_it_fails(monkeypatch):
    calls = []
    screen = tiled_screen(BIG_ON_THE_LEFT)

    def answer(**kwargs):
        calls.append(kwargs.get("layout"))
        return screen(**kwargs)

    verdict = run_row(monkeypatch, "AQ6", {**AQ6, "autocad_tiled_viewports": answer})
    assert not verdict.passed
    assert "one" in calls, calls


def test_no_heron_configuration_fails(monkeypatch):
    verdict = run_row(monkeypatch, "AQ6", {**AQ6, "own.viewport_names": ["*Active"]})
    assert not verdict.passed and "Heron" in verdict.evidence


def test_a_locked_object_done_after_all_fails(monkeypatch):
    items = list(AQ9["autocad_hyperlinks"].items)
    items[4] = {"action": "set", "changed": 2, "handles": ["K", "P1"], "objects": []}
    verdict = run_row(monkeypatch, "AQ9", {**AQ9, "autocad_hyperlinks": seq(*items)})
    assert not verdict.passed and not verdict.refused


def test_a_drawing_placed_by_its_template_is_not_run(monkeypatch):
    verdict = run_row(monkeypatch, "AQ12", {**AQ12, "autocad_get_variable": values(("LATITUDE", 25.29), ("LONGITUDE", 51.53))})
    assert verdict.refused and "San Francisco" in verdict.evidence


@pytest.mark.parametrize("row", ["AQ11", "AQ12", "AQ13"])
def test_the_geo_rows_close_their_own_drawing(monkeypatch, row):
    verdict = run_row(monkeypatch, row, SAMPLES[row][0])
    assert verdict.called("lc.close_drawing") == [{"name": "Drawing2.dwg"}]
    assert verdict.called("lc.activate")
