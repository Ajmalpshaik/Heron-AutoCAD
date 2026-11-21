"""autocad_dimension_run with a named dimension style (#37, D-80), no AutoCAD.

The two traps the issue found are pinned here: the drawing's DIMSCALE must not
be written over the style's own scale, and the style is set on each dimension,
never by making it the current style and putting the old one back.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.tools import dimensions
from autocad_mcp.tools.dimensions import scale_to_write, stored_name


class TestRules:
    def test_without_a_style_each_dimension_gets_the_drawings_dimscale(self):
        assert scale_to_write(None, False, 50.0) == 50.0

    def test_a_named_style_keeps_its_own_scale(self):
        assert scale_to_write("DIM-1-5", False, 50.0) is None

    def test_an_annotative_dimension_is_sized_by_its_scales_not_dimscale(self):
        assert scale_to_write(None, True, 50.0) is None

    def test_no_dimscale_in_the_drawing_writes_nothing(self):
        assert scale_to_write(None, False, 0.0) is None

    def test_a_name_is_matched_without_case_and_given_back_as_stored(self):
        assert stored_name(["Standard", "DIM-1-5"], "dim-1-5") == "DIM-1-5"
        assert stored_name(["Standard"], " standard ") == "Standard"
        assert stored_name(["Standard"], "DIM-1-5") is None


class Dim:
    count = 0

    def __init__(self, style_ok=True):
        Dim.count += 1
        self.Handle = f"2A{Dim.count}"
        self.Measurement = 3000.0
        self.written: dict = {}
        self.deleted = False
        self._style_ok = style_ok
        self._scale = 1.0

    def __setattr__(self, name, value):
        if name == "StyleName":
            if not self._style_ok:
                raise RuntimeError("bad style")
            self._scale = 5.0  # the style's own DIMSCALE
        if name in ("StyleName", "ScaleFactor", "TextOverride", "Layer"):
            self.written[name] = value
        object.__setattr__(self, name, value)

    @property
    def ScaleFactor(self):  # noqa: N802 - COM name
        return self.written.get("ScaleFactor", self._scale)

    def Delete(self):  # noqa: N802 - COM name
        self.deleted = True


class Styles:
    def __init__(self, names):
        self.names = names
        self.Count = len(names)

    def Item(self, i):  # noqa: N802 - COM name
        class Style:
            Name = self.names[i]

        return Style()


class Space:
    def __init__(self, style_ok=True):
        self.made: list[Dim] = []
        self.style_ok = style_ok

    def AddDimRotated(self, p1, p2, text, angle):  # noqa: N802 - COM name
        dim = Dim(self.style_ok)
        self.made.append(dim)
        return dim


class Doc:
    def __init__(self, style_ok=True):
        self.ModelSpace = self.PaperSpace = Space(style_ok)
        self.DimStyles = Styles(["Standard", "DIM-1-5"])
        self.active_style_writes = 0
        self.set_variables: list = []

    def GetVariable(self, name):  # noqa: N802 - COM name
        return {"UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0),
                "UCSYDIR": (0.0, 1.0, 0.0), "DIMSCALE": 50.0}[name]

    def SetVariable(self, name, value):  # noqa: N802 - COM name
        self.set_variables.append((name, value))

    def __setattr__(self, name, value):
        if name == "ActiveDimStyle":
            object.__setattr__(self, "active_style_writes", self.active_style_writes + 1)
        object.__setattr__(self, name, value)

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass


@pytest.fixture
def drawing(monkeypatch):
    holder = {"doc": Doc()}

    async def run(fn):
        return fn()

    monkeypatch.setattr(dimensions, "run", run)
    monkeypatch.setattr(dimensions, "get_doc", lambda: holder["doc"])
    monkeypatch.setattr(dimensions, "require_idle", lambda d: None)
    return holder


def answer(**kwargs):
    return asyncio.run(dimensions.autocad_dimension_run(
        points=[[0, 0], [3000, 0], [7500, 0]], mode="chain", axis="horizontal", offset=300, **kwargs
    ))


class TestTheRun:
    def test_without_a_style_the_drawings_dimscale_is_written_as_before(self, drawing):
        out = json.loads(answer())
        made = drawing["doc"].ModelSpace.made
        assert [d.written.get("ScaleFactor") for d in made] == [50.0, 50.0]
        assert all("StyleName" not in d.written for d in made)
        assert out["dim_scale"] == 50.0 and "dim_style" not in out

    def test_a_style_is_set_on_every_dimension_and_dimscale_is_not_written(self, drawing):
        out = json.loads(answer(dim_style="dim-1-5"))
        made = drawing["doc"].ModelSpace.made
        assert [d.written.get("StyleName") for d in made] == ["DIM-1-5", "DIM-1-5"]
        assert all("ScaleFactor" not in d.written for d in made)
        assert out["dim_style"] == "DIM-1-5" and out["style_scale"] == 5.0 and out["dim_scale"] is None

    def test_the_current_style_and_dimscale_are_never_touched(self, drawing):
        answer(dim_style="DIM-1-5")
        doc = drawing["doc"]
        assert doc.active_style_writes == 0 and doc.set_variables == []

    def test_an_unknown_style_is_refused_before_anything_is_drawn(self, drawing):
        text = answer(dim_style="DIM-1-10")
        assert text.startswith("Error") and "DIM-1-10" in text and "DIM-1-5" in text
        assert "Nothing was drawn" in text
        assert drawing["doc"].ModelSpace.made == []

    def test_a_dimension_that_will_not_take_the_style_is_not_kept(self, drawing):
        drawing["doc"] = Doc(style_ok=False)
        out = json.loads(answer(dim_style="DIM-1-5"))
        made = drawing["doc"].ModelSpace.made
        assert all(d.deleted for d in made) and out["count"] == 0
        assert len(out["failed"]) == 2 and "DIM-1-5" in out["failed"][0]["reason"]
