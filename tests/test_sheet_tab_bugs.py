"""A sheet tab on screen, and a new sheet's page setup (issues #39, #40; D-141). No AutoCAD.

#39 (row D33, AutoCAD 2027, 2026-10-28): with a sheet tab active, autocad_status
and autocad_add_table(space="paper") raised a bare "Exception occurred". The
fakes here throw what AutoCAD threw (DISP_E_EXCEPTION) from doc.PaperSpace and
doc.ActiveSpace, and keep COM's ActiveLayout on another tab than CTAB, as it
was seen to lag on 2026-11-22 (D-125).

#40 (row D8): every autocad_create_layout over COM answered "Outcome unknown:
AutoCAD went busy" although the tab was made. The page setup set CustomScale,
which a layout does not have (SetCustomScale sets its scale), and centred a
layout plot, which AutoCAD refuses (row D20). pywin32 answers both "Property
... can not be set", which the retry reads as a busy AutoCAD.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pythoncom
from test_annotate import FakeSpace
from test_export import FakeDoc as PlotDoc
from test_sheets_plugin import A1, Layout, drawing  # noqa: F401 - drawing is a fixture

from autocad_mcp.core import connection, gate
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import _shared, annotate, document, sheets

EXCEPTION = pythoncom.com_error(-2147352567, "Exception occurred.", (0, None, None, None, 0, -2147467259), None)


class Throws:
    """A COM property that throws when read, as AutoCAD 2027 did on the sheet tab."""

    def __get__(self, obj, owner):
        raise EXCEPTION


class Count:
    def __init__(self, n):
        self.Count = n


class Sheet:
    ModelType = False

    def __init__(self, name, objects=0):
        self.Name = name
        self.Block = FakeSpace()
        self.Block.Count = objects


class Tabs:
    def __init__(self, items):
        self.items = items

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]


class SheetTabDoc:
    """E-101 is on screen (CTAB, TILEMODE 0); COM still says Model, and PaperSpace throws."""

    Name = "AC-SLD.dwg"
    FullName = r"C:\jobs\AC-SLD.dwg"
    Saved = True
    ReadOnly = False
    PaperSpace = Throws()
    ActiveSpace = Throws()

    def __init__(self, ctab="E-101", tilemode=0, cvport=1, lagging=True):
        self.model = Sheet("Model", 40)
        self.sheet = Sheet("E-101", 6)
        self.Layouts = Tabs([self.model, Sheet("E-100", 2), self.sheet])
        on_screen = next(t for t in self.Layouts.items if t.Name == ctab)
        self.ActiveLayout = self.model if lagging else on_screen
        self.ModelSpace = Count(40)
        self.Layers = Count(5)
        self.Blocks = Count(9)
        self.ActiveLayer = type("Layer", (), {"Name": "0"})()
        self.vars = {
            "CTAB": ctab, "TILEMODE": tilemode, "CVPORT": cvport, "INSUNITS": 4, "UCSNAME": "",
            "UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0), "CMDACTIVE": 0,
        }  # fmt: skip

    def GetVariable(self, name):
        return self.vars[name]

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


class App:
    Caption = "Autodesk AutoCAD 2027"
    Version = "26.0s"

    def __init__(self, doc):
        self.Documents = Count(1)
        self.ActiveDocument = doc


def status(monkeypatch, doc) -> dict:
    monkeypatch.setattr(document, "get_app", lambda launch_if_needed=False: App(doc))
    answer = asyncio.run(document.autocad_status())
    assert not answer.startswith("Error"), answer
    return json.loads(answer)["active_drawing"]


# ---------------------------------------------------------------------------
# #39: autocad_status on a sheet tab
# ---------------------------------------------------------------------------


class TestStatusOnASheetTab:
    def test_it_answers_paper_for_the_tab_on_screen(self, monkeypatch):
        found = status(monkeypatch, SheetTabDoc())
        assert found["active_space"] == "paper"
        assert found["active_layout"] == "E-101"
        assert found["paper_space_entities"] == 6  # E-101's own block, not Model's
        assert "unreadable" not in found

    def test_the_model_tab_is_model(self, monkeypatch):
        found = status(monkeypatch, SheetTabDoc(ctab="Model", tilemode=1, lagging=False))
        assert found["active_space"] == "model" and found["active_layout"] == "Model"

    def test_a_viewport_made_active_on_the_sheet_is_said(self, monkeypatch):
        found = status(monkeypatch, SheetTabDoc(cvport=2))
        assert found["active_space"] == "paper" and found["viewport_active"] is True

    def test_no_viewport_flag_on_the_sheet_itself(self, monkeypatch):
        assert "viewport_active" not in status(monkeypatch, SheetTabDoc())

    def test_the_caption_and_version_never_sink_it(self, monkeypatch):
        class Quiet(App):
            Caption = Throws()
            Version = Throws()

        doc = SheetTabDoc()
        monkeypatch.setattr(document, "get_app", lambda launch_if_needed=False: Quiet(doc))
        answer = json.loads(asyncio.run(document.autocad_status()))
        assert answer["application"] == "" and answer["active_drawing"]["active_space"] == "paper"
        assert {"application", "version"} <= set(answer["active_drawing"]["unreadable"])

    def test_a_com_error_in_the_gates_first_look_is_an_answer_not_a_bare_exception(self, monkeypatch):
        # The gate's own look at AutoCAD runs outside every tool's handler: a COM error
        # there came out bare. Now it is an AutocadError, which status answers through
        # and other tools turn into a refusal in words.
        def look():
            raise EXCEPTION

        async def run(fn):
            return fn()

        monkeypatch.setattr(gate, "get_app", look)
        monkeypatch.setattr(gate, "run", run)
        with pytest.raises(AutocadError, match="could not tell which drawing"):
            asyncio.run(REAL_PROBE())


# conftest swaps gate._probe out for every test; this is the real one, kept at import.
REAL_PROBE = gate._probe


# ---------------------------------------------------------------------------
# #39: space="paper" lands on the sheet on screen
# ---------------------------------------------------------------------------


class TestPaperSpaceIsTheSheetOnScreen:
    def test_a_lagging_active_layout_gives_the_sheet_ctab_names(self):
        doc = SheetTabDoc()
        assert connection.get_space(doc, "paper") is doc.sheet.Block

    def test_paper_space_throwing_falls_back_to_the_sheet_on_screen(self):
        doc = SheetTabDoc(lagging=False)
        assert connection.get_space(doc, "paper") is doc.sheet.Block

    def test_model_is_never_taken_for_a_sheet(self):
        doc = SheetTabDoc(ctab="Model", tilemode=1, lagging=False)
        with pytest.raises(pythoncom.com_error):
            connection.get_space(doc, "paper")

    def test_a_busy_ctab_goes_up_to_be_asked_again(self):
        busy = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)

        class Busy(SheetTabDoc):
            def GetVariable(self, name):
                raise busy

        with pytest.raises(pythoncom.com_error):
            connection.get_space(Busy(), "paper")

    def test_the_table_lands_on_the_sheet(self, monkeypatch):
        doc = SheetTabDoc()

        async def run(fn):
            return fn()

        monkeypatch.setattr(annotate, "run", run)
        monkeypatch.setattr(annotate, "get_doc", lambda: doc)
        added = []
        real = doc.sheet.Block.AddTable
        doc.sheet.Block.AddTable = lambda *a: added.append(a) or real(*a)
        answer = asyncio.run(annotate.autocad_add_table(position=[700, 50], rows=[["AHU-1", "2.5 kW"]], space="paper"))
        assert not answer.startswith("Error"), answer
        assert len(added) == 1


# ---------------------------------------------------------------------------
# #40: a new sheet's page setup over COM
# ---------------------------------------------------------------------------


class Offered(Layout):
    def GetCanonicalMediaNames(self):
        return (A1,)

    def GetLocaleMediaName(self, name):
        return name.replace("_", " ")

    def RefreshPlotDeviceInfo(self):
        pass


class TestANewSheetOverCom:
    @pytest.fixture
    def com(self, drawing, monkeypatch):  # noqa: F811 - the fixture imported above
        doc, _ = drawing
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)

        def add(name):
            layout = Offered(name)
            doc.Layouts.added.append(name)
            doc.Layouts.items.append(layout)
            return layout

        monkeypatch.setattr(doc.Layouts, "Add", add)
        return doc

    def test_it_answers_with_the_new_sheet_not_busy(self, com):
        answer = asyncio.run(sheets.autocad_create_layout(name="AC-101", paper_size="A1", plot_style_table="monochrome.ctb", activate=False))
        assert not answer.startswith("Error"), answer
        out = json.loads(answer)
        assert out["created"] is True and out["layout"] == "AC-101" and out["made_by"] == "com"
        assert "warning" not in out, out.get("warning")
        page = out["page_setup"]
        assert page["scale"] == "1:1" and page["plot_area"] == "layout"
        # Written after the scale and the centring: these never got there before.
        assert page["plot_style_table"] == "monochrome.ctb"
        assert page["centred"] is False and "origin" in page["centred_note"]
        made = com.Layouts.items[-1]
        assert made.custom_scale == (1.0, 1.0)
        assert made.StyleSheet == "monochrome.ctb"
        assert not hasattr(made, "CenterPlot")

    def test_activate_does_not_change_that(self, com):
        out = json.loads(asyncio.run(sheets.autocad_create_layout(name="AC-102", paper_size="A1")))
        assert "warning" not in out and out["page_setup"]["scale"] == "1:1"


class TestPageSetupScaleAndCentring:
    def test_a_scale_is_set_with_set_custom_scale(self):
        layout = Offered("E-101")
        written = sheets._set_page(layout, None, None, None, None, None, None, "1:50", None, None, None, None, None)
        assert layout.custom_scale == (1.0, 50.0) and written["scale"] == "1:50"

    def test_an_enlargement_too(self):
        layout = Offered("E-101")
        sheets._set_page(layout, None, None, None, None, None, None, "2:1", None, None, None, None, None)
        assert layout.custom_scale == (2.0, 1.0)

    def test_a_window_plot_is_centred(self):
        layout = Offered("E-101")
        layout.SetWindowToPlot = lambda a, b: None
        written = sheets._set_page(layout, None, None, None, "window", ("a", "b"), None, None, True, None, None, None, None)
        assert layout.CenterPlot is True and written["centred"] is True

    def test_a_sheet_already_plotting_its_layout_is_not_centred(self):
        layout = Offered("E-101")
        object.__setattr__(layout, "PlotType", 5)
        written = sheets._set_page(layout, None, None, None, None, None, None, None, True, None, None, None, None)
        assert written["centred"] is False and "centred_note" in written


class TestThePdfScale:
    def test_a_pdf_at_1_50_is_set_with_set_custom_scale(self, tmp_path):
        doc = PlotDoc()
        document._plot_pdf(doc, str(tmp_path / "a.pdf"), None, "extents", None, None, "1:50")
        assert ("call", "SetCustomScale") in doc.events
        assert doc.Plot.calls[0]["layout"]["CustomScale"] == pytest.approx(0.02)
