"""Annotative objects and their annotation scales (#108, D-81), no AutoCAD.

The scale rules are plain functions; the tools are checked up to the pipe:
what they ask the plug-in for, and how the new annotative option on the text,
dimension and multileader tools behaves, including when it cannot be done.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, annotate, annotation_scales, dimensions, draw
from autocad_mcp.tools.annotation_scales import (
    paper_height,
    parse_scale,
    scale_args,
    scale_rows,
    with_paper_heights,
)


class TestParse:
    def test_a_ratio_reads_as_paper_to_drawing_units(self):
        assert parse_scale(" 1 : 50 ") == {"name": "1:50", "paper": 1.0, "drawing": 50.0}
        assert parse_scale("2:1") == {"name": "2:1", "paper": 2.0, "drawing": 1.0}

    def test_any_other_name_is_looked_up_by_name(self):
        assert parse_scale('1/4" = 1\'-0"') == {"name": '1/4" = 1\'-0"', "paper": 0.0, "drawing": 0.0}

    @pytest.mark.parametrize("bad", ["", "0:50", "1:0"])
    def test_refusals(self, bad):
        with pytest.raises(ValueError):
            parse_scale(bad)


class TestRequest:
    def test_scales_go_as_names_with_their_ratios(self):
        assert scale_args(add=["1:50", "1:100"]) == {
            "add": ["1:50", "1:100"], "add_paper": [1.0, 1.0], "add_drawing": [50.0, 100.0],
        }

    def test_remove_and_annotative(self):
        args = scale_args(remove=["1:20"], annotative=True)
        assert args == {"annotative": True, "remove": ["1:20"], "remove_paper": [1.0], "remove_drawing": [20.0]}

    def test_making_an_object_plain_cannot_add_scales(self):
        with pytest.raises(ValueError, match="annotative=false"):
            scale_args(add=["1:50"], annotative=False)

    def test_one_scale_cannot_be_added_and_removed(self):
        with pytest.raises(ValueError, match="both added and removed"):
            scale_args(add=["1:50"], remove=["2:100"])  # the same ratio under another name

    def test_nothing_asked_is_refused(self):
        with pytest.raises(ValueError, match="say what to change"):
            scale_args()

    def test_only_a_ratio_can_be_added_to_the_drawings_list(self):
        assert scale_args(add=["1:25"], create_missing=True)["create_missing"] is True
        with pytest.raises(ValueError, match="paper:drawing"):
            scale_args(add=["HALF"], create_missing=True)


class TestHeights:
    def test_a_model_height_reads_on_paper_through_the_scale(self):
        assert paper_height(125.0, {"paper": 1.0, "drawing": 50.0}) == 2.5
        assert paper_height(125.0, None) is None and paper_height(None, {"paper": 1, "drawing": 50}) is None

    def test_only_an_annotative_object_with_a_height_gets_one(self):
        rows = with_paper_heights(
            [{"handle": "1", "annotative": "yes", "height": 250.0}, {"handle": "2", "annotative": "no", "height": 250.0},
             {"handle": "3", "annotative": "yes"}],
            {"name": "1:100", "paper": 1.0, "drawing": 100.0},
        )
        assert rows[0]["paper_height"] == 2.5 and "paper_height" not in rows[1] and "paper_height" not in rows[2]


class TestBeforeAfter:
    def test_each_change_is_one_row_and_no_change_is_none(self):
        rows = scale_rows([
            {"handle": "1", "annotative": "yes", "annotative_was": "no", "scales": ["1:50"], "scales_were": []},
            {"handle": "2", "annotative": "yes", "annotative_was": "yes", "scales": ["1:50", "1:100"], "scales_were": ["1:50"]},
            {"handle": "3", "annotative": "yes", "annotative_was": "yes", "scales": ["1:50"], "scales_were": ["1:50"]},
        ])
        assert rows == [
            {"handle": "1", "property": "annotative", "from": "no", "to": "yes"},
            {"handle": "1", "property": "annotation scales", "from": "none", "to": "1:50"},
            {"handle": "2", "property": "annotation scales", "from": "1:50", "to": "1:50, 1:100"},
        ]


# ---------------------------------------------------------------------------
# The tools, up to the pipe
# ---------------------------------------------------------------------------


class FakePlugin:
    def __init__(self):
        self.calls: list = []
        self.refuse: str | None = None
        self.skip: set[str] = set()

    def __call__(self, operation, args):
        self.calls.append((operation, dict(args)))
        if self.refuse:
            raise annotation_scales.AutocadError(self.refuse)
        current = {"name": "1:50", "paper": 1.0, "drawing": 50.0}
        if operation == "annotation_scales":
            return {"current": current, "scales": [current], "anno_all_visible": False,
                    "objects": [{"handle": h, "type": "mtext", "annotative": "yes", "scales": ["1:50"], "height": 125.0}
                                for h in args["handles"]]}
        if operation == "set_annotation_scales":
            objects = [{"handle": h, "type": "text", "annotative": "yes", "scales": ["1:50", *args.get("add", [])],
                        "height": 125.0, "annotative_was": "no", "scales_were": []}
                       for h in args["handles"] if h not in self.skip]
            skipped = [{"handle": h, "why": "a line cannot be annotative"} for h in args["handles"] if h in self.skip]
            return {"current": current, "objects": objects, "scales_created": [], "skipped": skipped}
        raise AssertionError(operation)


class Made:
    def __init__(self, handle):
        self.Handle, self.ObjectName, self.Layer, self.Measurement = handle, "AcDbText", "0", 3000.0
        self.written: dict = {}

    def __setattr__(self, name, value):
        if name not in ("Handle", "ObjectName", "Layer", "Measurement", "written"):
            self.written[name] = value
        object.__setattr__(self, name, value)

    def AddLeader(self):  # noqa: N802 - COM name
        return 1

    def AddLeaderLine(self, cluster, points):  # noqa: N802 - COM name
        return 1


class Space:
    def __init__(self):
        self.made: list[Made] = []

    def _make(self, *args):
        made = Made(f"2A{len(self.made)}")
        self.made.append(made)
        return made

    AddText = AddMText = AddDimRotated = AddDimAligned = _make  # noqa: N815 - COM names

    def AddMLeader(self, points, index):  # noqa: N802 - COM name
        return (self._make(), 0)


class Doc:
    def __init__(self):
        self.ModelSpace = self.PaperSpace = Space()

    def GetVariable(self, name):  # noqa: N802 - COM name
        return {"UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0),
                "DIMSCALE": 50.0, "CANNOSCALE": "1:50"}[name]

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass

    def HandleToObject(self, handle):  # noqa: N802 - COM name
        return next(m for m in self.ModelSpace.made if m.Handle == handle)


@pytest.fixture
def cad(monkeypatch):
    fake = FakePlugin()
    doc = Doc()

    async def run(fn):
        return fn()

    for module in (annotation_scales, draw, dimensions, annotate):
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(draw, "apply_properties", lambda *a, **k: {})
    monkeypatch.setattr(annotate, "apply_properties", lambda *a, **k: {})
    monkeypatch.setattr(draw, "created_payload", lambda entity, notes, **extra: {"handle": entity.Handle, **extra})
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    fake.doc = doc
    return fake


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


class TestScalesTools:
    def test_listing_adds_the_paper_height_and_cannoscale(self, cad):
        out = call(annotation_scales.autocad_list_annotation_scales(handles=["2A"]))
        assert cad.calls == [("annotation_scales", {"handles": ["2A"]})]
        assert out["cannoscale"] == "1:50" and out["objects"][0]["paper_height"] == 2.5

    def test_without_the_plug_in_the_listing_still_gives_cannoscale(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        out = call(annotation_scales.autocad_list_annotation_scales())
        assert out["cannoscale"] == "1:50" and "plug-in" in out["note"]

    def test_setting_sends_the_request_and_lists_each_change(self, cad):
        out = call(annotation_scales.autocad_annotation_scales(handles=["2A"], add=["1:100"], add_missing_to_drawing=True))
        assert cad.calls == [("set_annotation_scales", {"handles": ["2A"], "add": ["1:100"], "add_paper": [1.0],
                                                        "add_drawing": [100.0], "create_missing": True})]
        assert {"handle": "2A", "property": "annotative", "from": "no", "to": "yes"} in out["before_after"]

    def test_a_contradiction_is_refused_before_the_plug_in_is_asked(self, cad):
        assert "Nothing was changed" in error(annotation_scales.autocad_annotation_scales(handles=["2A"], annotative=False, add=["1:50"]))
        assert cad.calls == []


class TestAnnotativeOption:
    def test_text_is_made_annotative_after_it_is_drawn(self, cad):
        out = call(draw.autocad_add_text(text="NOTE", position=[0, 0], height=125, annotative=True))
        assert cad.calls == [("set_annotation_scales", {"handles": ["2A0"], "annotative": True})]
        assert out["annotative"] is True and out["annotation_scales"] == ["1:50"] and out["paper_height"] == 2.5

    def test_without_annotative_the_plug_in_is_not_asked(self, cad):
        out = call(draw.autocad_add_text(text="NOTE", position=[0, 0], height=125))
        assert cad.calls == [] and "annotative" not in out

    def test_without_the_plug_in_nothing_is_drawn(self, cad, monkeypatch):
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        assert "plug-in" in error(draw.autocad_add_mtext(text="N", position=[0, 0], width=1000, annotative=True))
        assert cad.doc.ModelSpace.made == []

    def test_a_plug_in_that_fails_after_drawing_warns_and_never_errors(self, cad):
        cad.refuse = "Heron in AutoCAD does not have the operation 'set_annotation_scales'."
        out = call(draw.autocad_add_mtext(text="N", position=[0, 0], width=1000, annotative=True))
        assert out["annotative"] is False and "drawn, but not made annotative" in out["warning"]
        assert len(cad.doc.ModelSpace.made) == 1  # drawn once, not twice

    def test_an_annotative_dimension_keeps_dimscale_off(self, cad):
        call(draw.autocad_add_dimension(dimension_type="horizontal", point1=[0, 0], point2=[3000, 0], annotative=True))
        assert "ScaleFactor" not in cad.doc.ModelSpace.made[0].written

    def test_a_plain_dimension_still_gets_dimscale(self, cad):
        call(draw.autocad_add_dimension(dimension_type="horizontal", point1=[0, 0], point2=[3000, 0]))
        assert cad.doc.ModelSpace.made[0].written["ScaleFactor"] == 50.0

    def test_a_dimension_run_is_made_annotative_in_one_request(self, cad):
        out = call(dimensions.autocad_dimension_run(points=[[0, 0], [3000, 0], [7500, 0]], offset=500, annotative=True))
        assert cad.calls == [("set_annotation_scales", {"handles": ["2A0", "2A1"], "annotative": True})]
        assert all("ScaleFactor" not in d.written for d in cad.doc.ModelSpace.made)
        assert out["annotative"] is True and out["dim_scale"] is None

    def test_one_that_could_not_be_made_annotative_is_named(self, cad):
        cad.skip = {"2A1"}
        out = call(dimensions.autocad_dimension_run(points=[[0, 0], [3000, 0], [7500, 0]], offset=500, annotative=True))
        assert out["annotative"] is False and "2A1" in out["warning"] and "cannot be annotative" in out["warning"]

    def test_a_multileader_can_be_annotative(self, cad):
        out = call(annotate.autocad_add_multileader(landing=[100, 100], arrows=[[0, 0]], text="N", annotative=True))
        assert cad.calls == [("set_annotation_scales", {"handles": ["2A0"], "annotative": True})]
        assert out["annotative"] is True


def test_levels():
    assert risk_of("autocad_list_annotation_scales") is Risk.READ
    assert risk_of("autocad_annotation_scales") is Risk.CHANGE
