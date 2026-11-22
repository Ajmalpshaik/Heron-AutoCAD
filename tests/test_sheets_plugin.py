"""Sheets by the plug-in, the drawing list, status on a sheet tab and the PDF
of several drawings (#64-#67, #39, #40; D-90, D-91). No AutoCAD.

What is checked is everything up to the pipe: what each tool asks the plug-in
for, what it works out first, when it falls back to COM, and how a busy or
broken AutoCAD is answered.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest
import pythoncom

from autocad_mcp.core import connection
from autocad_mcp.core.bridge import OLD_PLUGIN
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, document, publish, sheet_set, sheets

BUSY = pythoncom.com_error(-2147418111, "Call was rejected by callee.", None, None)
A1 = "ISO_full_bleed_A1_(841.00_x_594.00_MM)"


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def error(coro):
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


async def _now(fn):
    return fn()


class Broken:
    """A COM property that throws when read, as doc.PaperSpace did on a sheet tab."""

    def __get__(self, obj, owner):
        raise RuntimeError("Exception occurred.")


class Attribute:
    def __init__(self, tag):
        self.TagString = tag
        self.TextString = ""


class Reference:
    ObjectName = "AcDbBlockReference"

    def __init__(self, handle, name, tags):
        self.Handle = handle
        self.EffectiveName = name
        self.Name = name
        self.Layer = "0"
        self.HasAttributes = True
        self._attributes = [Attribute(t) for t in tags]

    def GetAttributes(self):
        return self._attributes

    def values(self):
        return {a.TagString: a.TextString for a in self._attributes}


class Block:
    def __init__(self):
        self.items: list = []
        self.inserted: list = []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index]

    def InsertBlock(self, at, name, sx, sy, sz, rotation):
        reference = Reference(f"7{len(self.items):02X}", name.rsplit("\\", 1)[-1].removesuffix(".dwg"), ["DWG_NO", "TITLE", "SCALE", "PROJECT"])
        self.items.append(reference)
        self.inserted.append((tuple(getattr(at, "value", at))[:2], name))
        return reference


class Layout:
    def __init__(self, name, media=A1, size=(841.0, 594.0)):
        self.Name = name
        self.CanonicalMediaName = media
        self.ConfigName = "DWG To PDF.pc3"
        self.PlotRotation = 0
        self.TabOrder = 1
        self.Block = Block()
        self.size = size

    def GetPaperSize(self):
        return self.size

    def GetPaperMargins(self):
        return ((0.0, 0.0), (0.0, 0.0))


class Layouts:
    def __init__(self, doc, names):
        self.doc = doc
        self.items = [Layout(n) for n in names]
        self.added: list[str] = []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index]

    def Add(self, name):
        self.added.append(name)
        layout = Layout(name)
        self.items.append(layout)
        return layout


class View:
    def __init__(self, name, centre, width, height):
        self.Name = name
        self.Center = (centre[0], centre[1], 0.0)
        self.Width = width
        self.Height = height


class Items:
    def __init__(self, items):
        self.items = list(items)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        if isinstance(index, str):
            for item in self.items:
                if item.Name.lower() == index.lower():
                    return item
            raise KeyError(index)
        return self.items[index]


class Named:
    def __init__(self, name):
        self.Name = name
        self.IsLayout = False


class Doc:
    PaperSpace = Broken()

    def __init__(self, layouts=("Model", "Layout1")):
        self.Layouts = Layouts(self, layouts)
        self.ActiveLayout = self.Layouts.items[0]
        self.Views = Items([View("GF-HVAC", (25000.0, 15000.0), 50000.0, 30000.0), View("FF-HVAC", (25000.0, 45000.0), 20000.0, 10000.0)])
        self.Blocks = Items([Named("TTLB-A1")])
        self.undo_marks = 0

    def GetVariable(self, name):
        if name == "CMDACTIVE":
            return 0
        raise KeyError(name)

    def StartUndoMark(self):
        self.undo_marks += 1

    def EndUndoMark(self):
        pass


class Plugin:
    """The plug-in in AutoCAD: makes what it is asked for in the fake drawing."""

    def __init__(self, doc):
        self.doc = doc
        self.calls: list[tuple[str, dict]] = []
        self.refuse: dict[str, str] = {}
        self.viewports = 0

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        if operation in self.refuse:
            raise AutocadError(self.refuse[operation])
        if operation == "create_layout":
            layout = Layout(args["name"])
            self.doc.Layouts.items.append(layout)
            return {
                "created": True, "layout": args["name"], "tab_order": len(self.doc.Layouts.items) - 1,
                "activated": args.get("activate", True),
                "page_setup": {"plotter": "DWG To PDF.pc3", "paper_size": "ISO full bleed A1 (841.00 x 594.00 MM)", "plot_area": "layout", "scale": "1:1", "centred": True},
                "paper": {"media": A1, "plotter": "DWG To PDF.pc3", "size": [841.0, 594.0], "margins": [0, 0, 0, 0], "plot_rotation_degrees": 0, "paper_units": "mm"},
            }  # fmt: skip
        if operation == "add_viewport":
            self.viewports += 1
            report = {"created": True, "handle": f"9{self.viewports:02X}", "layout": args["layout"], "layer": args.get("layer") or "0", "scale_set": args["scale_ratio"], "locked": args["locked"], "clipped": bool(args.get("clip_outline") or args.get("clip_handle"))}
            if args.get("annotation_scale"):
                report["annotation_scale"] = args["annotation_scale"]
            return report
        return {}


@pytest.fixture
def drawing(monkeypatch):
    doc = Doc()
    fake = Plugin(doc)
    for module in (sheets, sheet_set):
        monkeypatch.setattr(module, "run", _now)
        monkeypatch.setattr(module, "get_doc", lambda: doc)
        monkeypatch.setattr(module, "require_idle", lambda d: None)
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    monkeypatch.setattr(sheets.time, "sleep", lambda s: None)
    return doc, fake


# ---------------------------------------------------------------------------
# autocad_create_layout (#64, #40)
# ---------------------------------------------------------------------------


class TestCreateLayout:
    def test_the_plug_in_makes_the_sheet_and_com_adds_nothing(self, drawing):
        doc, plugin = drawing
        out = call(sheets.autocad_create_layout(name="M-101", paper_size="A1", plot_style_table="monochrome.ctb", title_block_width=180))
        operation, args = plugin.calls[0]
        assert operation == "create_layout"
        assert args == {"name": "M-101", "plotter": "DWG To PDF.pc3", "paper_size": "A1", "orientation": "landscape", "plot_style_table": "monochrome.ctb", "activate": True}
        assert doc.Layouts.added == []
        assert out["made_by"] == "plugin" and out["created"] and out["layout"] == "M-101"
        # The sheet's arithmetic comes from the plug-in's paper: ISO 5457 on a full-bleed A1.
        assert out["sheet"]["frame"] == [20.0, 10.0, 831.0, 584.0]
        assert out["sheet"]["drawing_space"] == [20.0, 10.0, 651.0, 584.0]
        assert out["sheet"]["title_block_at"] == [831.0, 10.0]
        assert out["activated"] is True

    def test_a_name_the_drawing_has_is_refused_before_asking(self, drawing):
        _, plugin = drawing
        assert "already has a layout" in error(sheets.autocad_create_layout(name="layout1"))
        assert plugin.calls == []

    def test_the_plug_ins_refusal_is_the_answer_and_com_is_not_tried(self, drawing):
        doc, plugin = drawing
        plugin.refuse["create_layout"] = "'A7' is not a paper size the DWG To PDF.pc3 plotter offers. Nothing was changed."
        assert "A7" in error(sheets.autocad_create_layout(name="M-101", paper_size="A7"))
        assert doc.Layouts.added == []

    def test_an_older_plug_in_falls_back_to_com(self, drawing):
        doc, plugin = drawing
        plugin.refuse["create_layout"] = OLD_PLUGIN
        out = call(sheets.autocad_create_layout(name="M-101", plotter=None))
        assert doc.Layouts.added == ["M-101"]
        assert out["made_by"] == "com" and "older" in out["plugin_note"]

    def test_a_plug_in_without_the_operation_falls_back_to_com(self, drawing):
        doc, plugin = drawing
        plugin.refuse["create_layout"] = "Heron in AutoCAD does not have the operation 'create_layout'. Update Heron so both sides match."
        assert call(sheets.autocad_create_layout(name="M-101", plotter=None))["made_by"] == "com"

    def test_without_the_plug_in_com_makes_it(self, drawing, monkeypatch):
        doc, _ = drawing
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        out = call(sheets.autocad_create_layout(name="M-101", plotter=None))
        assert out["made_by"] == "com" and "--no-bridge" in out["plugin_note"]

    def test_busy_while_the_page_setup_is_written_is_answered_from_the_drawing(self, drawing, monkeypatch):
        # Row D8, 2026-10-28: the tabs were made, but every call said "Outcome unknown".
        doc, _ = drawing
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)

        class BusyMedia(Layout):
            def GetCanonicalMediaNames(self):
                return (A1,)

            def __setattr__(self, name, value):
                if name == "CanonicalMediaName" and getattr(self, "armed", False):
                    raise BUSY
                object.__setattr__(self, name, value)

        def add(name):
            layout = BusyMedia(name)
            layout.armed = True
            doc.Layouts.items.append(layout)
            return layout

        monkeypatch.setattr(doc.Layouts, "Add", add)
        out = call(sheets.autocad_create_layout(name="M-101", paper_size="A1", plotter=None))
        assert out["created"] is True and out["layout"] == "M-101"
        assert "went busy" in out["warning"] and "Do not make the sheet again" in out["warning"]
        assert out["sheet"]["frame"] == [20.0, 10.0, 831.0, 584.0]

    def test_busy_and_not_found_is_outcome_unknown_in_words_that_say_where_to_look(self, drawing, monkeypatch):
        doc, _ = drawing
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        monkeypatch.setattr(sheets, "_set_page", lambda *a, **k: (_ for _ in ()).throw(BUSY))
        real = sheets._layouts
        calls = {"n": 0}

        def layouts(d):
            calls["n"] += 1
            if calls["n"] > 2:  # the name check and the fetch after Add answer; the read-back does not
                raise BUSY
            return real(d)

        monkeypatch.setattr(sheets, "_layouts", layouts)
        answer = error(sheets.autocad_create_layout(name="M-101", plotter=None))
        assert "Outcome unknown" in answer and "'M-101'" in answer and "autocad_page_setup" in answer


# ---------------------------------------------------------------------------
# autocad_add_viewport (#64, #65)
# ---------------------------------------------------------------------------


class TestAddViewport:
    def test_the_plug_in_gets_the_numbers_worked_out_here(self, drawing):
        doc, plugin = drawing
        out = call(sheets.autocad_add_viewport(layout="Layout1", view_name="GF-HVAC", scale="1:100", title_block_width=180, layer="G-VPRT"))
        operation, args = plugin.calls[0]
        assert operation == "add_viewport"
        assert args["layout"] == "Layout1"
        assert args["paper_centre"] == [335.5, 297.0] and args["paper_width"] == 631.0 and args["paper_height"] == 574.0
        assert args["look_at"] == [25000.0, 15000.0]
        assert args["scale_ratio"] == pytest.approx(0.01)
        assert args["annotation_scale"] == "1:100"  # 'match' is the viewport's own scale
        assert args["locked"] is True and args["layer"] == "G-VPRT" and args["twist"] == 0.0
        assert "clip_outline" not in args and "clip_handle" not in args
        assert out["made_by"] == "plugin" and out["handle"] == "901"
        assert out["model_window"] == [-6550.0, -13700.0, 56550.0, 43700.0]

    def test_a_fitted_scale_is_the_largest_standard_one(self, drawing):
        _, plugin = drawing
        out = call(sheets.autocad_add_viewport(layout="Layout1", view_name="GF-HVAC"))
        # 50 x 30 m on 811 x 574 mm: 1:50 needs 1000 mm across, 1:75 needs 667.
        assert out["fitted"] is True and out["scale"] == "1:75"
        assert plugin.calls[0][1]["annotation_scale"] == "1:75"

    def test_annotation_scale_none_is_not_sent_and_a_name_is_sent_as_given(self, drawing):
        _, plugin = drawing
        call(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50", annotation_scale="none"))
        assert "annotation_scale" not in plugin.calls[0][1]
        call(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50", annotation_scale="1:100"))
        assert plugin.calls[1][1]["annotation_scale"] == "1:100"

    def test_a_clip_outline_places_the_viewport_and_goes_flat(self, drawing):
        _, plugin = drawing
        corners = [[50, 50], [250, 50], [250, 130], [130, 130], [130, 200], [50, 200], [50, 50]]
        out = call(sheets.autocad_add_viewport(layout="Layout1", centre=[10000, 5000], scale="1:50", clip_outline=corners))
        args = plugin.calls[0][1]
        assert args["clip_outline"] == [50, 50, 250, 50, 250, 130, 130, 130, 130, 200, 50, 200]
        assert args["paper_centre"] == [150.0, 125.0] and args["paper_width"] == 200.0 and args["paper_height"] == 150.0
        assert out["clipped"] is True and out["paper_rect"] == [50.0, 50.0, 250.0, 200.0]

    def test_a_clip_with_a_paper_place_too_is_refused(self, drawing):
        _, plugin = drawing
        answer = error(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50", clip_outline=[[0, 0], [10, 0], [10, 10]], paper_centre=[5, 5], paper_width=10, paper_height=10))
        assert "takes its place on the paper from the clip" in answer and plugin.calls == []

    def test_a_crossing_clip_outline_is_refused_before_asking(self, drawing):
        _, plugin = drawing
        answer = error(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50", clip_outline=[[0, 0], [10, 10], [10, 0], [0, 10]]))
        assert "crosses itself" in answer and plugin.calls == []

    def test_a_clip_without_the_plug_in_is_refused_and_nothing_made(self, drawing, monkeypatch):
        doc, _ = drawing
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        made = []
        monkeypatch.setattr(sheets, "_new_viewport", lambda *a: made.append(a))
        answer = error(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50", clip_outline=[[0, 0], [10, 0], [10, 10]]))
        assert "plug-in" in answer and "Nothing was made" in answer and made == []

    def test_a_clip_object_is_measured_for_the_viewports_place(self, drawing, monkeypatch):
        doc, plugin = drawing

        class Outline:
            def GetBoundingBox(self):
                return ((100.0, 60.0, 0.0), (300.0, 260.0, 0.0))

        doc.HandleToObject = lambda handle: Outline()
        out = call(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:20", clip_handle="2F1"))
        args = plugin.calls[0][1]
        assert args["clip_handle"] == "2F1" and args["paper_centre"] == [200.0, 160.0]
        assert out["clipped"] is True

    def test_align_to_ucs_turns_the_view_back_by_the_ucs_angle(self, drawing, monkeypatch):
        # A plan on a grid turned +23 reads square at a view twist of -23 (337), as PLAN leaves it.
        _, plugin = drawing
        monkeypatch.setattr(sheets, "current_ucs", lambda doc: type("U", (), {"rotation_degrees": 23.0})())
        out = call(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50", align_to_ucs=True))
        assert plugin.calls[0][1]["twist"] == pytest.approx(337.0)
        assert out["twist_degrees"] == pytest.approx(337.0)

    def test_an_explicit_twist_is_the_view_twist_as_given(self, drawing):
        _, plugin = drawing
        call(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50", twist=-23, align_to_ucs=True))
        assert plugin.calls[0][1]["twist"] == pytest.approx(337.0)

    def test_an_older_plug_in_falls_back_to_com_with_the_scale_by_cannoscale(self, drawing, monkeypatch):
        doc, plugin = drawing
        plugin.refuse["add_viewport"] = OLD_PLUGIN
        aimed = {}

        class Viewport:
            Handle = "3A0"
            Layer = "0"

        monkeypatch.setattr(sheets, "_activate", lambda d, s: None)
        monkeypatch.setattr(sheets, "_new_viewport", lambda d, name, cx, cy, pw, ph: Viewport())
        monkeypatch.setattr(sheets, "_aim", lambda d, v, w, a, r, locked, annotation: aimed.update(annotation=annotation) or {"scale_set": r})
        out = call(sheets.autocad_add_viewport(layout="Layout1", centre=[0, 0], scale="1:50"))
        assert out["made_by"] == "com" and out["handle"] == "3A0" and aimed["annotation"] == "1:50"


# ---------------------------------------------------------------------------
# autocad_place_title_block: into the layout's own block (#39, limit 23)
# ---------------------------------------------------------------------------


def test_a_title_block_goes_into_the_layouts_block_without_switching_tabs(drawing):
    doc, _ = drawing
    out = call(sheets.autocad_place_title_block(block="TTLB-A1", layouts=["Layout1"], attributes={"dwg_no": "M-101"}))
    layout = doc.Layouts.items[1]
    assert layout.Block.inserted == [((831.0, 10.0), "TTLB-A1")]
    assert out["placed"][0]["attributes_set"] == ["DWG_NO"]
    assert doc.ActiveLayout.Name == "Model"  # nothing was switched; doc.PaperSpace never read


# ---------------------------------------------------------------------------
# autocad_status and paper space on a sheet tab (#39)
# ---------------------------------------------------------------------------


class SheetTab:
    PaperSpace = Broken()
    ActiveSpace = Broken()

    def __init__(self, block_count=None):
        class Active:
            Name = "E-101"

        self.ActiveLayout = Active()
        if block_count is not None:
            self.ActiveLayout.Block = type("B", (), {"Count": block_count})()


class TestStatusOnASheet:
    def test_one_fact_that_will_not_read_is_named_not_fatal(self):
        unread: list[str] = []
        assert document._status_field(unread, "layer_count", lambda: 1 / 0, None) is None
        assert document._status_field(unread, "saved", lambda: True) is True
        assert unread == ["layer_count"]

    def test_the_space_comes_from_the_layout_when_active_space_will_not_say(self):
        assert document._active_space(SheetTab()) == "paper"

    def test_the_sheets_count_comes_from_its_block(self):
        assert document._paper_space_count(SheetTab(block_count=7)) == 7

    def test_last_of_all_the_plug_in_counts_the_sheet(self, monkeypatch):
        monkeypatch.setattr(document, "plugin_read", lambda op, args=None: ({"layout": "E-101", "model": False, "entities": 12, "viewports": 2}, None))
        assert document._paper_space_count(SheetTab()) == 12

    def test_the_plug_ins_count_of_model_space_is_not_a_paper_count(self, monkeypatch):
        monkeypatch.setattr(document, "plugin_read", lambda op, args=None: ({"layout": "Model", "model": True, "entities": 900, "viewports": 0}, None))
        assert document._paper_space_count(SheetTab()) is None

    def test_nothing_answers_gives_none(self, monkeypatch):
        monkeypatch.setattr(document, "plugin_read", lambda op, args=None: (None, "no plug-in"))
        assert document._paper_space_count(SheetTab()) is None


def test_paper_space_falls_back_to_the_active_layouts_block():
    tab = SheetTab(block_count=3)
    assert connection.get_space(tab, "paper") is tab.ActiveLayout.Block


def test_a_busy_paper_space_is_not_replaced_but_retried():
    class BusyTab(SheetTab):
        @property
        def PaperSpace(self):
            raise BUSY

    with pytest.raises(pythoncom.com_error):
        connection.get_space(BusyTab(block_count=3), "paper")


# ---------------------------------------------------------------------------
# autocad_sheet_set (#66)
# ---------------------------------------------------------------------------

LIST = [
    {"number": "M-101", "title": "GROUND FLOOR HVAC", "scale": "1:100", "view": "GF-HVAC"},
    {"number": "M-102", "title": "FIRST FLOOR HVAC", "view": "FF-HVAC"},
    {"number": "M-001", "title": "COVER"},
]


class TestSheetSet:
    def test_a_drawing_list_becomes_sheets_in_one_undo_step(self, drawing):
        doc, plugin = drawing
        out = call(sheet_set.autocad_sheet_set(sheets=LIST, title_block="TTLB-A1", title_block_width=180, attributes={"PROJECT": "VILLA"}, viewport_layer="G-VPRT"))
        assert out["complete"] is True and out["count"] == 3
        assert [c[0] for c in plugin.calls] == ["create_layout", "add_viewport", "create_layout", "add_viewport", "create_layout"]
        assert all(args["activate"] is False for op, args in plugin.calls if op == "create_layout")
        assert plugin.calls[0][1]["paper_size"] == "A1" and plugin.calls[0][1]["plotter"] == "DWG To PDF.pc3"
        assert doc.undo_marks == 1
        first, second, cover = out["sheets"]
        assert first["scale"] == "1:100" and first["viewport"] == "901" and first["fitted"] is False
        # 20 x 10 m on 631 x 574 mm: 1:25 needs 800 mm across, 1:50 needs 400.
        assert second["fitted"] is True and second["scale"] == "1:50"
        assert cover["viewport"] is None and cover["title_block"]
        sheets_made = {layout.Name: layout for layout in doc.Layouts.items}
        assert sheets_made["M-102"].Block.items[0].values() == {"DWG_NO": "M-102", "TITLE": "FIRST FLOOR HVAC", "SCALE": "1:50", "PROJECT": "VILLA"}
        assert "SCALE" not in [k for k, v in sheets_made["M-001"].Block.items[0].values().items() if v]

    def test_a_dry_run_shows_the_plan_and_makes_nothing(self, drawing):
        doc, plugin = drawing
        out = call(sheet_set.autocad_sheet_set(sheets=LIST, dry_run=True))
        assert out["dry_run"] is True and plugin.calls == [] and doc.undo_marks == 0
        assert [s["scale"] for s in out["would_make"]] == ["1:100", "fit", None]
        assert out["would_make"][0]["looks_at"] == "saved view GF-HVAC"
        assert out["would_make"][2]["looks_at"] == "no viewport"

    def test_problems_are_said_before_anything_is_made(self, drawing):
        doc, plugin = drawing
        rows = [{"number": "Layout1", "view": "NOWHERE"}, {"number": "M-1", "scale": "big"}]
        answer = error(sheet_set.autocad_sheet_set(sheets=rows))
        assert "already has a layout called 'Layout1'" in answer and "NOWHERE" in answer and "not a scale" in answer
        assert plugin.calls == [] and doc.undo_marks == 0

    def test_a_key_a_row_does_not_take_is_named(self, drawing):
        assert "'sheet_no'" in error(sheet_set.autocad_sheet_set(sheets=[{"number": "M-1", "sheet_no": "x"}]))

    def test_a_title_block_the_drawing_does_not_have_is_refused_first(self, drawing):
        _, plugin = drawing
        assert "No block named 'TTLB-A0'" in error(sheet_set.autocad_sheet_set(sheets=LIST, title_block="TTLB-A0"))
        assert plugin.calls == []

    def test_a_refusal_part_way_keeps_the_sheets_made_and_says_where_it_stopped(self, drawing, monkeypatch):
        _, plugin = drawing

        def second_layout_refused(operation, args):
            if operation == "create_layout" and args["name"] == "M-102":
                raise AutocadError("AutoCAD refused it (eInvalidInput). Nothing was changed.")
            return plugin(operation, args)

        monkeypatch.setattr(_shared, "plugin_runner", lambda: second_layout_refused)
        out = call(sheet_set.autocad_sheet_set(sheets=LIST))
        assert out["complete"] is False and out["count"] == 1
        assert out["stopped"]["number"] == "M-102" and "eInvalidInput" in out["stopped"]["error"]
        assert "one Ctrl+Z takes them all back" in out["warning"] and "M-102, M-001" in out["warning"]

    def test_a_sheet_whose_viewport_is_refused_is_listed_as_made_but_unfinished(self, drawing, monkeypatch):
        # Review: its layout is there, so a retry of that row would be told the name is taken.
        doc, plugin = drawing
        plugin.refuse["add_viewport"] = "This drawing has no annotation scale called 'XL'. Nothing was changed."
        out = call(sheet_set.autocad_sheet_set(sheets=LIST, annotation_scale="XL"))
        assert out["complete"] is False and out["count"] == 0
        first = out["sheets"][0]
        assert first["layout"] == "M-101" and first["unfinished"] is True and "annotation scale" in first["error"]
        assert "M-101" in [layout.Name for layout in doc.Layouts.items]
        assert "made but not finished" in out["warning"] and "M-102, M-001" in out["warning"]

    def test_a_template_sheets_own_title_block_is_filled_not_doubled(self, drawing, monkeypatch):
        doc, plugin = drawing
        doc.Layouts.items[1].Block.items.append(Reference("5A", "TTLB-A1", ["DWG_NO", "TITLE", "SCALE"]))

        def copying(operation, args):
            report = plugin(operation, args)
            if operation == "create_layout" and args.get("copy_from"):
                doc.Layouts.items[-1].Block.items.append(Reference("6B", "TTLB-A1", ["DWG_NO", "TITLE", "SCALE"]))
            return report

        monkeypatch.setattr(_shared, "plugin_runner", lambda: copying)
        out = call(sheet_set.autocad_sheet_set(sheets=[LIST[0]], template_layout="Layout1", title_block="TTLB-A1"))
        made = doc.Layouts.items[-1]
        assert len(made.Block.items) == 1 and made.Block.inserted == []
        assert out["sheets"][0]["title_block"] == "6B" and out["sheets"][0]["title_block_from"] == "template"
        assert made.Block.items[0].values()["DWG_NO"] == "M-101"
        assert plugin.calls[0][1]["copy_from"] == "Layout1"
        # The template keeps its own sheet and plotter.
        assert "paper_size" not in plugin.calls[0][1] and "plotter" not in plugin.calls[0][1]


def test_the_sheet_set_is_a_change():
    assert risk_of("autocad_sheet_set") is Risk.CHANGE


# ---------------------------------------------------------------------------
# autocad_publish_pdf over several drawings (#67)
# ---------------------------------------------------------------------------


class PdfPlugin:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.old = False

    def __call__(self, operation, args):
        self.calls.append((operation, args))
        if operation == "active_sheet":
            if self.old:
                raise AutocadError("Heron in AutoCAD does not have the operation 'active_sheet'. Update Heron so both sides match. Nothing was sent to AutoCAD.")
            return {"layout": "Model", "model": True, "entities": 5, "viewports": 0}
        answer = {"published": True, "path": args["path"], "count": 3, "sheets": ["M-101", "M-102", "M-201"]}
        if args.get("drawings"):
            answer.update({"drawings": 2, "pages": [{"drawing": d, "layout": "M-101"} for d in args["drawings"]]})
        return answer

    def published(self):
        return [args for op, args in self.calls if op == "publish_pdf"]


class Documents:
    def __init__(self, entries):
        self.entries = entries

    @property
    def Count(self):
        return len(self.entries)

    def Item(self, index):
        full, saved = self.entries[index]
        # As AutoCAD gives them: Name is the file's own name, FullName the whole path (any slashes).
        name = os.path.basename(full) or "Drawing1.dwg"
        return type("D", (), {"Name": name, "FullName": full or name, "Saved": saved})()


@pytest.fixture
def pdf(monkeypatch, tmp_path):
    fake = PdfPlugin()
    opened: list[tuple[str, bool]] = []
    monkeypatch.setattr(publish, "run", _now)
    monkeypatch.setattr(publish, "get_doc", lambda: object())
    monkeypatch.setattr(publish, "require_idle", lambda d: None)
    monkeypatch.setattr(publish, "get_app", lambda: type("A", (), {"Documents": Documents(opened)})())
    monkeypatch.setattr(_shared, "plugin_runner", lambda: fake)
    folder = tmp_path / "Issue"
    folder.mkdir()
    for name in ("M-200 first.dwg", "M-100 ground.dwg", "readme.txt"):
        (folder / name).write_bytes(b"AC1032")
    return fake, folder, opened, tmp_path


class TestPublishSeveralDrawings:
    def test_a_folder_sends_its_drawings_in_order(self, pdf):
        plugin, folder, _, tmp_path = pdf
        call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), folder=str(folder)))
        args = plugin.published()[0]
        assert [os.path.basename(name) for name in args["drawings"]] == ["M-100 ground.dwg", "M-200 first.dwg"]

    def test_an_open_drawing_with_unsaved_changes_is_refused_before_asking(self, pdf):
        plugin, folder, opened, tmp_path = pdf
        opened.append((str(folder / "M-200 first.dwg"), False))
        answer = error(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), folder=str(folder)))
        assert "M-200 first.dwg" in answer and "unsaved changes" in answer and plugin.published() == []

    def test_a_saved_open_drawing_is_fine(self, pdf):
        plugin, folder, opened, tmp_path = pdf
        opened.append((str(folder / "M-200 first.dwg"), True))
        call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), folder=str(folder)))
        assert len(plugin.published()) == 1

    def test_a_list_with_a_missing_drawing_is_refused_before_asking(self, pdf):
        plugin, folder, _, tmp_path = pdf
        answer = error(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), drawings=[str(folder / "M-100 ground.dwg"), str(folder / "gone.dwg")]))
        assert "gone.dwg' is not there" in answer and plugin.published() == []

    def test_folder_and_drawings_together_are_refused(self, pdf):
        _, folder, _, tmp_path = pdf
        assert "not both" in error(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), folder=str(folder), drawings=[str(folder / "M-100 ground.dwg")]))

    def test_without_a_folder_the_open_drawing_is_published_as_before(self, pdf):
        plugin, _, _, tmp_path = pdf
        call(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf")))
        assert "drawings" not in plugin.published()[0]
        assert [op for op, _ in plugin.calls] == ["publish_pdf"]  # no probe for the open drawing

    def test_an_older_plug_in_is_refused_before_it_publishes_the_wrong_drawing(self, pdf):
        # It would drop "drawings" and publish the open drawing in their place (review, #67).
        plugin, folder, _, tmp_path = pdf
        plugin.old = True
        answer = error(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), folder=str(folder)))
        assert "older" in answer and "Nothing was published" in answer and plugin.published() == []

    def test_an_answer_without_the_pages_is_not_taken_for_the_set(self, pdf, monkeypatch):
        plugin, folder, _, tmp_path = pdf
        answer_of = plugin.__call__

        def no_pages(operation, args):
            answer = answer_of(operation, args)
            answer.pop("pages", None)
            return answer

        monkeypatch.setattr(_shared, "plugin_runner", lambda: no_pages)
        assert "not the drawings asked" in error(publish.autocad_publish_pdf(path=str(tmp_path / "set.pdf"), folder=str(folder)))


def test_a_dimension_edit_on_a_sheet_tab_uses_the_layouts_block():
    # #169: dimensions_edit picked doc.PaperSpace itself.
    from autocad_mcp.tools import dimensions_edit

    class PaperTab(SheetTab):
        ActiveSpace = 0
        MSpace = False

    tab = PaperTab(block_count=4)
    space, label = dimensions_edit._space_of(tab)
    assert label == "paper" and space is tab.ActiveLayout.Block


def test_a_sheet_made_but_not_as_asked_is_listed_and_stops_the_set(drawing, monkeypatch):
    # AutoCAD busy over COM after the layout was added: the sheet is there, so it counts as made.
    doc, _ = drawing
    monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
    monkeypatch.setattr(sheets, "_set_page", lambda *a, **k: (_ for _ in ()).throw(BUSY))
    out = call(sheet_set.autocad_sheet_set(sheets=LIST))
    assert out["complete"] is False and out["count"] == 0
    assert out["sheets"][0]["layout"] == "M-101" and "went busy" in out["sheets"][0]["warning"]
    assert out["sheets"][0]["unfinished"] is True
    assert out["stopped"]["number"] == "M-101"
