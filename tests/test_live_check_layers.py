"""The AB live checks judge right: PASS on a good recorded answer, FAIL on a bad one.

No AutoCAD here: each check is played against answers shaped like the real tools'
(tests/live_fakes.py). That proves the judging and the arguments, not AutoCAD;
only a live run does that.
"""

from __future__ import annotations

import json
import math

import pytest
from live_fakes import load, play, seq

checks = load("live_check_layers")
lc = load("live_common")


def P(row: str, x: float, y: float) -> list[float]:
    o = lc.origin(row)
    return [o[0] + x, o[1] + y, 0.0]


def drawn(*handles: str) -> dict:
    return {"created": len(handles), "failed": 0, "requested": len(handles), "handles": list(handles)}


def table(entities: dict) -> callable:
    return lambda handle: entities[handle]


def done(answer: dict, line: str = "DONE - 1 changed.") -> str:
    """A change job's answer as the gate sends it: a plain first line, then the JSON (D-62)."""
    return f"{line}\n\n{json.dumps(answer)}"


STATUS = {"active_drawing": {"name": "Drawing1.dwg", "model_space_entities": 40}}
SETUP = {"dry_run": False, "changed": [{"variable": "DIMSCALE", "from": 1.0, "to": 50.0}], "unchanged": [],
         "failed": [], "scale": "1:50", "before_after": []}
SCALE_50 = {"name": "1:50", "paper": 1.0, "drawing": 50.0}
SCALE_100 = {"name": "1:100", "paper": 1.0, "drawing": 100.0}
SCALE_25 = {"name": "1:25", "paper": 1.0, "drawing": 25.0}
DRAWING_SCALES = [{"name": "1:1", "paper": 1.0, "drawing": 1.0}, {"name": "1:20", "paper": 1.0, "drawing": 20.0},
                  SCALE_50, SCALE_100]


def dimension(handle: str, top: float, bottom: float, measurement: float, style: str = "ISO-25") -> dict:
    return {"handle": handle, "type": "dimension", "layer": "LC", "measurement": measurement, "text_override": "",
            "style": style, "bounding_box": {"min": [0.0, bottom, 0.0], "max": [5000.0, top, 0.0]},
            "size": {"width": 5000.0, "height": top - bottom}}


# --- AB1 ----------------------------------------------------------------------------------------

AB1_STYLE = checks.AB1_STYLE


def run_answer(handles: list[str], **extra) -> dict:
    return {"mode": "chain", "axis": "horizontal", "count": len(handles), "created": len(handles),
            "handles": handles, "dimensions": [], "total": 750.0, "failed": [], **extra}


AB1 = {
    "autocad_drawing_setup": SETUP,
    "autocad_create_styles": {"text_styles": [], "dim_styles": [
        {"name": AB1_STYLE, "created": True, "current": False, "variables": {"DIMSCALE": 5.0}}]},
    "autocad_get_variable": lambda name: {"name": name, "value": {"DIMSTYLE": "ISO-25", "DIMSCALE": 50.0}[name]},
    "autocad_dimension_run": seq(
        done(run_answer(["S1", "S2"], dim_scale=None, dim_style=AB1_STYLE, style_scale=5.0), "DONE - 2 added."),
        done(run_answer(["N1", "N2"], dim_scale=50.0), "DONE - 2 added."),
        "Error: This drawing has no dimension style called 'NOPE' (it has: ISO-25, LC-AB1-DIM-1-5, Standard). "
        "autocad_list_styles lists them, autocad_create_styles makes one, and autocad_import_from_drawing "
        "brings one in. Nothing was drawn.",
    ),
    "autocad_get_entity": table({
        "S1": dimension("S1", 100, 0, 300.0, AB1_STYLE), "S2": dimension("S2", 100, 0, 450.0, AB1_STYLE),
        "N1": dimension("N1", 1100, 1000, 300.0),
    }),
    "lc.read_props": lambda handle, names: {"ScaleFactor": 5.0 if handle.startswith("S") else 50.0},
    "autocad_status": STATUS,
}

# --- AB2 ----------------------------------------------------------------------------------------

AB2_HANDLES = ["K0", "K1", "K2", "K3"]
AB2_ABOVE = 156.25  # text above the dimension line, the same on every one


def ab2_read(lines: tuple[float, ...]) -> list[dict]:
    oy = lc.origin("AB2")[1]
    return [dimension(h, oy + y + AB2_ABOVE, oy + 31.25, 1000.0 * (i + 1))
            for i, (h, y) in enumerate(zip(AB2_HANDLES, lines, strict=True))]


def ab2_moves(was: tuple[float, ...], now: tuple[float, ...]) -> list[dict]:
    return [{"handle": h, "from": [0, w], "to": [0, n], "offset_was": w, "offset_now": n}
            for h, w, n in zip(AB2_HANDLES[1:], was, now, strict=True)]


BEFORE = (300, 500, 750, 1600)
SPACED = (300, 700, 1100, 1500)
LINED = (300, 300, 300, 300)
AB2 = {
    "autocad_add_dimension": seq(*({"created": True, "handle": h, "type": "dimension", "measurement": 1000.0 * (i + 1)}
                                   for i, h in enumerate(AB2_HANDLES))),
    "autocad_get_entity": seq(*ab2_read(BEFORE), *ab2_read(BEFORE), *ab2_read(SPACED), *ab2_read(LINED)),
    "autocad_space_dimensions": seq(
        {"base": "K0", "spacing": 400.0, "moves": ab2_moves((200, 450, 1300), (400, 800, 1200)), "already": [],
         "skipped": [], "dry_run": True, "moved": 0, "hint": "Nothing was moved. Call again with dry_run=false."},
        done({"base": "K0", "spacing": 400.0, "moves": ab2_moves((200, 450, 1300), (400, 800, 1200)), "already": [],
              "skipped": [], "moved": 3, "before_after": []}, "DONE - 3 changed."),
        done({"base": "K0", "spacing": 0.0, "moves": ab2_moves((400, 800, 1200), (0, 0, 0)), "already": [],
              "skipped": [], "moved": 3, "before_after": []}, "DONE - 3 changed."),
    ),
}

# --- AB3 ----------------------------------------------------------------------------------------

AB3_HANDLES = ["G0", "G1", "G2", "G3"]
AB3_LENGTHS = (1000, 2000, 3000, 4000)


def ab3_text(outs: tuple[float, ...], drift: float = 0.0) -> list[dict]:
    o = lc.origin("AB3")
    return [{"TextPosition": [*checks._slope(o, length / 2 + drift, out + 40), 0.0]}
            for length, out in zip(AB3_LENGTHS, outs, strict=True)]


AB3_ENTITIES = {
    **{h: dimension(h, 0, 0, float(length)) for h, length in zip(AB3_HANDLES, AB3_LENGTHS, strict=True)},
    "R": dimension("R", 9000, 8000, 300.0),
}
AB3 = {
    "autocad_add_dimension": seq(
        *({"created": True, "handle": h, "type": "dimension", "measurement": float(length)}
          for h, length in zip(AB3_HANDLES, AB3_LENGTHS, strict=True)),
        {"created": True, "handle": "R", "type": "dimension", "measurement": 300.0},
    ),
    "autocad_batch_draw": drawn("CI"),
    "autocad_get_entity": table(AB3_ENTITIES),
    "lc.read_props": seq(*ab3_text((300, 500, 750, 1600)), *ab3_text((300, 700, 1100, 1500))),
    "autocad_space_dimensions": {
        "base": "G0", "spacing": 400.0, "moves": [], "already": [], "moved": 3, "before_after": [],
        "skipped": [{"handle": "R", "why": "only linear and aligned dimensions are spaced; this is a radial dimension"}],
    },
}

# --- AB5 ----------------------------------------------------------------------------------------

A5, B5, C5, D5 = checks.AB5


def layer(name: str, on: bool = True, frozen: bool = False, locked: bool = False) -> dict:
    return {"name": name, "color": 7, "linetype": "Continuous", "lineweight": -3, "on": on, "frozen": frozen,
            "locked": locked, "plottable": True}


def listing(current: str, states: dict, layer_states: list | None = None) -> dict:
    return {"count": len(states), "current_layer": current,
            "layers": [layer(name, *state) for name, state in sorted(states.items())],
            "layer_states": [{"name": n, "remembers": ["on", "frozen", "locked"], "description": ""}
                             for n in layer_states or []]}


AB5_RESTORED = [
    {"layer": A5, "property": "on", "from": True, "to": False},
    {"layer": B5, "property": "frozen", "from": False, "to": True},
    {"layer": C5, "property": "on", "from": False, "to": True},
    {"layer": D5, "property": "locked", "from": True, "to": False},
]
AB5_LAYERS = {"0": (True, False, False), A5: (False, False, False), B5: (True, True, False),
              C5: (True, False, False), D5: (True, False, False)}
EVERYTHING = ["on", "frozen", "locked", "plot", "new_viewport_frozen", "color", "linetype", "lineweight",
              "plot_style", "transparency"]
AB5 = {
    "autocad_create_layer": lambda name: {"name": name, "created": True, "current": False, "before_after": []},
    "autocad_set_layer_state": lambda name, **state: {"matched": 1, "changed": [name], "state": state, "before_after": []},
    "autocad_layer_states": seq(
        done({"action": "save", "name": checks.AB5_STATE, "replaced": False, "remembers": EVERYTHING, "layers": 5,
              "before_after": [{"layer": checks.AB5_STATE, "property": "layer state", "from": "not there", "to": "saved"}]}),
        done({"action": "restore", "name": checks.AB5_STATE, "remembers": EVERYTHING, "description": "",
              "deleted_after": False, "before_after": AB5_RESTORED}, "DONE - 4 changed."),
        f"Error: There is already a layer state called '{checks.AB5_STATE}'. Pass overwrite=true to replace it, "
        "or give another name.",
        done({"action": "delete", "name": checks.AB5_STATE, "before_after": []}),
    ),
    "autocad_list_layers": listing("0", AB5_LAYERS, [checks.AB5_STATE]),
}

# --- AB6 ----------------------------------------------------------------------------------------

DUCT, PIPE, FROZEN = checks.AB6_DUCT, checks.AB6_PIPE, checks.AB6_FROZEN
OTHER = "LC-AB5-B"  # a layer another row left frozen
AB6_START = {"0": (True, False, False), DUCT: (True, False, False), PIPE: (True, False, False),
             FROZEN: (True, False, False), OTHER: (True, True, False)}


def only(kept: str, how: str, start: dict = AB6_START) -> dict:
    out = {}
    for name, (on, frozen, locked) in start.items():
        if name == kept:
            out[name] = (True, False, False)
        elif how == "off":
            out[name] = (False, frozen, locked)
        elif how == "freeze":
            out[name] = (on, True, locked)
        else:
            out[name] = (on, frozen, True)
    return out


def ab6_isolate(action="isolate", handles=None, layers=None, others="off"):
    if action == "unisolate":
        return done({"action": "unisolate", "current_layer": "0", "before_after": []}, "DONE - 5 changed.")
    if handles == ["PL"]:
        return {"action": "isolate", "kept": [PIPE], "others": others, "current_layer": PIPE,
                "already_isolated": True, "before_after": []}
    if layers == [FROZEN]:
        return {"action": "isolate", "kept": [FROZEN], "others": others, "current_layer": FROZEN,
                "already_isolated": False, "before_after": [
                    {"layer": FROZEN, "property": "frozen", "from": True, "to": False},
                    {"variable": "CLAYER", "property": "current layer", "from": "0", "to": FROZEN}]}
    if others == "freeze":
        return {"action": "isolate", "kept": [DUCT], "others": "freeze", "current_layer": DUCT,
                "already_isolated": False, "before_after": [
                    {"variable": "CLAYER", "property": "current layer", "from": "0", "to": DUCT},
                    {"layer": "0", "property": "frozen", "from": False, "to": True},
                    {"layer": PIPE, "property": "frozen", "from": False, "to": True}]}
    current = "0" if others == "lock" else DUCT
    return {"action": "isolate", "kept": [DUCT], "others": others, "current_layer": current,
            "already_isolated": False, "before_after": []}


AB6_END = {**AB6_START, FROZEN: (True, True, False)}
AB6_LISTS = [
    listing("M-PIPE", AB6_START),
    listing(DUCT, only(DUCT, "off")),
    listing("0", AB6_START),
    listing("0", only(DUCT, "lock")),
    listing(DUCT, only(DUCT, "freeze")),
    listing(FROZEN, only(FROZEN, "off", AB6_END)),
    listing("0", AB6_END),
]
AB6 = {
    "autocad_create_layer": lambda name: {"name": name, "created": True, "current": False, "before_after": []},
    "autocad_batch_draw": drawn("DL", "PL"),
    "autocad_set_current_layer": lambda name: {"current_layer": name, "created": False, "previous": "x",
                                               "before_after": []},
    "autocad_isolate_layers": ab6_isolate,
    "autocad_set_layer_state": lambda name, **state: {"matched": 1, "changed": [name], "state": state, "before_after": []},
    "autocad_list_layers": seq(*AB6_LISTS),
}

# --- AB9 ----------------------------------------------------------------------------------------


def text_answer(handle: str, layer_name: str) -> dict:
    return {"created": True, "handle": handle, "type": "text", "layer": layer_name, "text": "NOTE", "height": 125.0,
            "annotative": True, "annotation_scales": ["1:50"], "paper_height": 2.5, "verified": True}


def scales_read(objects: list[dict], scales: list[dict] = DRAWING_SCALES) -> dict:
    return {"current": SCALE_50, "scales": scales, "anno_all_visible": False, "objects": objects, "cannoscale": "1:50"}


def text_object(handle: str, scales: list[str], height: float = 125.0, **extra) -> dict:
    return {"handle": handle, "type": "text", "annotative": "yes", "scales": scales, "height": height,
            "paper_height": round(height / 50, 6), **extra}


AB9 = {
    "autocad_drawing_setup": SETUP,
    "autocad_add_text": text_answer("T", "LC-AB9"),
    "autocad_list_annotation_scales": seq(scales_read([text_object("T", ["1:50"])]),
                                          scales_read([text_object("T", ["1:50", "1:100"])])),
    "autocad_annotation_scales": done({
        "objects": [text_object("T", ["1:50", "1:100"], annotative_was="yes", scales_were=["1:50"])],
        "scales_created": [], "skipped": [], "current": SCALE_50,
        "before_after": [{"handle": "T", "property": "annotation scales", "from": "1:50", "to": "1:50, 1:100"}]}),
}

# --- AB10 ---------------------------------------------------------------------------------------

AB10_ABOVE = (0.625 + 2.5) * 50
ANNOTATIVE = {"annotative": True, "annotation_scales": ["1:50"]}


def ab10_entities(above: float = AB10_ABOVE) -> dict:
    oy = lc.origin("AB10")[1]
    return {"AD": dimension("AD", oy + 500 + above, oy, 1000.0),
            "R1": dimension("R1", oy + 2500 + AB10_ABOVE, oy + 2000, 1000.0)}


AB10 = {
    "autocad_drawing_setup": SETUP,
    "autocad_get_variable": lambda name: {"name": name, "value": {"DIMTXT": 2.5, "DIMGAP": 0.625, "DIMEXE": 1.25}[name]},
    "autocad_add_dimension": {"created": True, "handle": "AD", "type": "dimension", "measurement": 1000.0,
                              "dimension_type": "horizontal", **ANNOTATIVE},
    "autocad_dimension_run": run_answer(["R1", "R2"], dim_scale=None, **ANNOTATIVE),
    "autocad_add_multileader": {"created": True, "handle": "ML", "type": "mleader", "leader_lines": 1,
                                "content": "text", **ANNOTATIVE},
    "autocad_list_annotation_scales": scales_read([
        {"handle": h, "type": kind, "annotative": "yes", "scales": ["1:50"]}
        for h, kind in (("AD", "dimension"), ("R1", "dimension"), ("R2", "dimension"), ("ML", "multileader"))
    ]),
    "autocad_get_entity": table(ab10_entities()),
}

# --- AB11 ---------------------------------------------------------------------------------------

WITH_25 = [*DRAWING_SCALES, SCALE_25]
AB11 = {
    "autocad_drawing_setup": SETUP,
    "autocad_add_text": text_answer("N", "LC-AB11"),
    "autocad_list_annotation_scales": seq(
        scales_read([]),
        scales_read([text_object("N", ["1:50"])]),
        scales_read([text_object("N", ["1:50", "1:25"])], WITH_25),
        scales_read([text_object("N", ["1:50", "1:25"])], WITH_25),
    ),
    "autocad_annotation_scales": seq(
        "Error: This drawing has no annotation scale '1:25'. autocad_list_annotation_scales lists the drawing's "
        "scales; add_missing_to_drawing=true adds a 1:N scale to the list.",
        done({"objects": [text_object("N", ["1:50", "1:25"], annotative_was="yes", scales_were=["1:50"])],
              "scales_created": ["1:25"], "skipped": [], "current": SCALE_50, "before_after": []}),
        "Error: N would be left with no annotation scale; an annotative object keeps at least one. Leave one on it, "
        "or make it not annotative with annotative=false.",
    ),
}


# Each row: the good recording, and what in it goes wrong for the FAIL.
SAMPLES: dict[str, tuple[dict, dict]] = {
    "AB1": (AB1, {"lc.read_props": lambda handle, names: {"ScaleFactor": 50.0}}),
    "AB2": (AB2, {"autocad_get_entity": seq(*ab2_read(BEFORE), *ab2_read(BEFORE), *ab2_read((300, 690, 1100, 1500)),
                                            *ab2_read(LINED))}),
    "AB3": (AB3, {"lc.read_props": seq(*ab3_text((300, 500, 750, 1600)), *ab3_text((300, 700, 1100, 1500), drift=50))}),
    "AB5": (AB5, {"autocad_layer_states": seq(
        AB5["autocad_layer_states"].items[0],
        done({"action": "restore", "name": checks.AB5_STATE, "remembers": EVERYTHING, "description": "",
              "deleted_after": False, "before_after": AB5_RESTORED[:3]}),
        *AB5["autocad_layer_states"].items[2:],
    )}),
    "AB6": (AB6, {"autocad_list_layers": seq(*AB6_LISTS[:2], listing("0", {**AB6_START, OTHER: (True, False, False)}),
                                             *AB6_LISTS[3:])}),
    "AB9": (AB9, {"autocad_list_annotation_scales": seq(scales_read([text_object("T", ["1:50"], height=6250.0)]),
                                                        scales_read([text_object("T", ["1:50", "1:100"])]))}),
    "AB10": (AB10, {"autocad_get_entity": table(ab10_entities(AB10_ABOVE * 50))}),
    "AB11": (AB11, {"autocad_annotation_scales": seq(
        AB11["autocad_annotation_scales"].items[0],
        done({"objects": [text_object("N", ["1:50", "1:25"])], "scales_created": [], "skipped": [],
              "current": SCALE_50, "before_after": []}),
        AB11["autocad_annotation_scales"].items[2],
    )}),
}

CHECKS = {c.row: c for c in checks.CHECKS}


def test_every_check_has_a_recording():
    assert sorted(CHECKS) == sorted(SAMPLES), "each AB check needs a good and a bad recording here"


def test_every_ab_row_is_checked_or_has_a_reason():
    assert sorted(set(CHECKS) | set(checks.BY_EYE)) == [f"AB{n}" for n in sorted(range(1, 12), key=str)]
    assert not set(CHECKS) & set(checks.BY_EYE)
    assert all(len(why.split()) >= 4 for why in checks.BY_EYE.values())


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


def test_ab1_draws_nothing_with_an_unknown_style(monkeypatch):
    drew = {**AB1, "autocad_status": seq(STATUS, {"active_drawing": {"model_space_entities": 41}})}
    verdict = play(monkeypatch, CHECKS["AB1"], drew)
    assert not verdict.passed and "drew something" in verdict.evidence


def test_ab3_square_to_the_slope_is_measured_across_it():
    o = lc.origin("AB3")
    a, b = checks._slope(o, 100, 0), checks._slope(o, 100, 400)
    assert math.isclose(checks._dot(b, a, checks.AB3_ACROSS), 400.0)
    assert abs(checks._dot(b, a, checks.AB3_ALONG)) < 1e-9


def test_ab6_a_failure_puts_the_layers_back(monkeypatch):
    good, bad = SAMPLES["AB6"]
    verdict = play(monkeypatch, CHECKS["AB6"], {**good, **bad})
    assert not verdict.passed
    assert verdict.called("autocad_isolate_layers")[-1] == {"action": "unisolate"}


def test_ab6_a_clean_run_puts_the_current_layer_back(monkeypatch):
    verdict = play(monkeypatch, CHECKS["AB6"], AB6)
    assert verdict.passed, verdict.evidence
    assert verdict.called("autocad_set_current_layer") == [{"name": "0"}, {"name": "M-PIPE"}]


def test_ab11_says_when_the_drawing_already_had_1_25(monkeypatch):
    had = {
        **AB11,
        "autocad_list_annotation_scales": seq(
            scales_read([], WITH_25),
            scales_read([text_object("N", ["1:50", "1:25"])], WITH_25),
            scales_read([text_object("N", ["1:50", "1:25"])], WITH_25),
        ),
        "autocad_annotation_scales": seq(
            done({"objects": [text_object("N", ["1:50", "1:25"])], "scales_created": [], "skipped": [],
                  "current": SCALE_50, "before_after": []}),
            AB11["autocad_annotation_scales"].items[2],
        ),
    }
    verdict = play(monkeypatch, CHECKS["AB11"], had)
    assert verdict.passed, verdict.evidence
    assert "already had 1:25" in verdict.evidence
    assert len(verdict.called("autocad_annotation_scales")) == 2
