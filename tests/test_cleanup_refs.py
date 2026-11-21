"""Overkill, boundary, eTransmit, underlay attach and clip tools (#112, #104, #118, #114), without AutoCAD."""

from __future__ import annotations

import asyncio
import json
import math
import zipfile

import pytest

from autocad_mcp.acad import clip, transmittal
from autocad_mcp.core import gate
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, cleanup, xrefs


def call(coro):
    answer = asyncio.run(coro)
    assert not answer.startswith("Error"), answer
    return json.loads(answer)


def refused(coro) -> str:
    answer = asyncio.run(coro)
    assert answer.startswith("Error"), answer
    return answer


async def _now(fn):
    return fn()


# ---- a small fake drawing ------------------------------------------------------------


class Ent:
    def __init__(self, doc, handle, name, layer="0", **props):
        self.doc, self.Handle, self.ObjectName, self.Layer = doc, handle, name, layer
        self.Document = doc
        for key, value in props.items():
            setattr(self, key, value)
        doc.by_handle[handle] = self

    def Delete(self):
        self.doc.deleted.append(self.Handle)

    def __setattr__(self, key, value):
        if key in ("StartPoint", "EndPoint", "StartAngle", "EndAngle") and hasattr(self, key):
            self.doc.set.append((self.Handle, key, getattr(value, "value", value)))
            value = tuple(value.value) if hasattr(value, "value") else value
        object.__setattr__(self, key, value)


class Space:
    def __init__(self):
        self.items = []

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]


class Layer:
    def __init__(self, lock=False):
        self.Lock = lock


class Layers:
    def __init__(self, locked=()):
        self.locked = set(locked)

    def Item(self, name):
        return Layer(name in self.locked)


class Doc:
    def __init__(self, locked=()):
        self.by_handle = {}
        self.deleted, self.set, self.marks = [], [], []
        self.ModelSpace, self.PaperSpace = Space(), Space()
        self.Layers = Layers(locked)

    def HandleToObject(self, handle):
        return self.by_handle[handle]

    def StartUndoMark(self):
        self.marks.append("start")

    def EndUndoMark(self):
        self.marks.append("end")

    def GetVariable(self, name):
        return {"UCSORG": (0.0, 0.0, 0.0), "UCSXDIR": (1.0, 0.0, 0.0), "UCSYDIR": (0.0, 1.0, 0.0)}[name]

    def line(self, handle, a, b, layer="0"):
        e = Ent(self, handle, "AcDbLine", layer, StartPoint=(*a, 0.0), EndPoint=(*b, 0.0))
        self.ModelSpace.items.append(e)
        return e


def patch(monkeypatch, module, doc):
    monkeypatch.setattr(module, "run", _now)
    monkeypatch.setattr(module, "get_doc", lambda: doc)
    monkeypatch.setattr(module, "require_idle", lambda d: None)
    return doc


class Plugin:
    """The Heron plug-in, answering as asked."""

    def __init__(self, answer=None, error=None):
        self.calls, self.answer, self.error = [], answer or {}, error

    def __call__(self, operation, args, timeout=None):
        self.calls.append((operation, args, timeout))
        if self.error:
            raise self.error
        return dict(self.answer)


def with_plugin(monkeypatch, plugin):
    monkeypatch.setattr(_shared, "plugin_runner", lambda: plugin)
    return plugin


# ---- levels ---------------------------------------------------------------------------


def test_every_new_tool_has_the_level_it_needs():
    for name in ("overkill", "trace_boundary", "attach_underlay", "clip_reference"):
        assert risk_of(f"autocad_{name}") is Risk.CHANGE
    # It writes files, so it needs the Publish padlock.
    assert risk_of("autocad_etransmit") is Risk.PUBLISH


def test_the_plugin_runner_passes_a_shorter_wait_on(monkeypatch):
    calls = []

    class FakeBridge:
        def run(self, job, operation, args, timeout=None):
            calls.append((job, operation, timeout))
            return {}

    monkeypatch.setattr(gate, "_current", gate.Job("t", Risk.CHANGE, "T", "a.dwg", FakeBridge(), "j1", False, 0.0))
    gate.plugin_runner()("trace_boundary", {})
    gate.plugin_runner()("trace_boundary", {}, 30.0)
    assert calls == [("j1", "trace_boundary", None), ("j1", "trace_boundary", 30.0)]


# ---- overkill tool --------------------------------------------------------------------


class TestOverkillTool:
    def drawing(self, locked=()):
        doc = Doc(locked)
        doc.line("1A", (0, 0), (600, 0), "A-WALL")
        doc.line("1B", (400, 0), (1000, 0), "A-WALL")
        doc.line("1C", (0, 0), (600, 0), "A-WALL")
        doc.line("1D", (0, 500), (1000, 500), "M-DUCT")
        Ent(doc, "1E", "AcDbText", "A-WALL")
        doc.ModelSpace.items.append(doc.by_handle["1E"])
        return doc

    def test_the_first_call_only_lists(self, monkeypatch):
        doc = patch(monkeypatch, cleanup, self.drawing())
        out = call(cleanup.autocad_overkill())
        assert out["confirmed"] is False and out["erase_count"] == 2 and out["stretch_count"] == 1
        assert {r["handle"] for r in out["erase"]} == {"1B", "1C"}
        assert doc.deleted == [] and doc.set == [] and doc.marks == []
        assert out["objects_read"] == 5 and out["looked_at"] == 4

    def test_confirm_erases_and_stretches_in_one_undo_step(self, monkeypatch):
        doc = patch(monkeypatch, cleanup, self.drawing())
        out = call(cleanup.autocad_overkill(confirm=True))
        assert out["confirmed"] is True and sorted(doc.deleted) == ["1B", "1C"]
        assert ("1A", "EndPoint", (1000.0, 0.0, 0.0)) in doc.set
        assert doc.marks == ["start", "end"] and "keep the erased ones erased" in out["note"]

    def test_a_locked_layer_stops_it_before_anything_changes(self, monkeypatch):
        doc = patch(monkeypatch, cleanup, self.drawing(locked={"A-WALL"}))
        answer = refused(cleanup.autocad_overkill(confirm=True))
        assert "A-WALL" in answer and "locked" in answer and doc.deleted == [] and doc.set == []

    def test_only_the_layers_asked_for(self, monkeypatch):
        patch(monkeypatch, cleanup, self.drawing())
        out = call(cleanup.autocad_overkill(layers=["m-duct"]))
        assert out["erase_count"] == 0 and out["looked_at"] == 1

    def test_only_the_handles_asked_for(self, monkeypatch):
        patch(monkeypatch, cleanup, self.drawing())
        out = call(cleanup.autocad_overkill(handles=["1A", "1C"]))
        assert [r["handle"] for r in out["erase"]] == ["1C"] and out["stretch_count"] == 0

    def test_nothing_doubled_says_so(self, monkeypatch):
        doc = Doc()
        doc.line("1A", (0, 0), (10, 0))
        patch(monkeypatch, cleanup, doc)
        out = call(cleanup.autocad_overkill(confirm=True))
        assert out["erase_count"] == 0 and "Nothing" in out["note"] and doc.marks == []

    def test_too_many_curves_is_refused(self, monkeypatch):
        patch(monkeypatch, cleanup, self.drawing())
        monkeypatch.setattr(cleanup, "MOST_CURVES", 2)
        assert "layers" in refused(cleanup.autocad_overkill())

    def test_a_polyline_and_a_fitted_one_are_read(self):
        doc = Doc()
        lw = Ent(doc, "2A", "AcDbPolyline", Coordinates=(0.0, 0.0, 10.0, 0.0, 10.0, 5.0), Closed=False,
                 Normal=(0.0, 0.0, 1.0), Elevation=3.0)
        lw.GetBulge = lambda i: [0.0, 0.5][i]
        item = cleanup.read_curve(lw)
        assert item["vertices"] == [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0]] and item["bulges"] == [0.0, 0.5]
        assert item["elevation"] == 3.0
        fitted = Ent(doc, "2B", "AcDb2dPolyline", Type=1, Normal=(0.0, 0.0, 1.0))
        assert cleanup.read_curve(fitted)["kind"] == "fitted polyline"
        arc = Ent(doc, "2C", "AcDbArc", Center=(1.0, 2.0, 0.0), Radius=5.0, StartAngle=0.0, EndAngle=1.0,
                  Normal=(0.0, 0.0, 1.0))
        assert cleanup.read_curve(arc)["start_angle"] == 0.0


# ---- boundary -------------------------------------------------------------------------


class TestBoundaryRequest:
    def test_a_window_is_put_corner_low_then_high(self):
        args = cleanup.boundary_request([5, 5], [[10, 10], [0, 0]], True, "polyline", 100, 30)
        assert args["window"] == [[0, 0], [10, 10]] and args["point"] == [5.0, 5.0, 0.0]

    def test_a_point_outside_its_window_is_refused(self):
        with pytest.raises(AutocadError, match="outside the window"):
            cleanup.boundary_request([50, 5], [[0, 0], [10, 10]], True, "polyline", 100, 30)

    def test_a_window_with_no_size_is_refused(self):
        with pytest.raises(AutocadError, match="no width"):
            cleanup.boundary_request([5, 5], [[0, 0], [10, 0]], True, "polyline", 100, 30)

    @pytest.mark.parametrize("most, timeout", [(0, 30), (60_000, 30), (100, 0), (100, 900)])
    def test_limits_out_of_range_are_refused(self, most, timeout):
        with pytest.raises(AutocadError):
            cleanup.boundary_request([5, 5], None, True, "polyline", most, timeout)

    def test_no_window_traces_what_is_in_view(self):
        assert "window" not in cleanup.boundary_request([5, 5], None, False, "region", 10, 5)


class TestBoundaryTool:
    def test_it_asks_the_plugin_with_the_limits_and_a_shorter_wait(self, monkeypatch):
        doc = patch(monkeypatch, cleanup, Doc())
        Ent(doc, "3F", "AcDbPolyline")
        plugin = with_plugin(monkeypatch, Plugin({"handle": "3F", "type": "polyline", "area": 12.0e6, "net_area": 11.5e6}))
        out = call(cleanup.autocad_trace_boundary(point_inside=[5000, 3000], window=[[0, 0], [10000, 6000]],
                                                   most_objects=800, timeout=20, layer="A-AREA"))
        (operation, args, timeout), = plugin.calls
        assert operation == "trace_boundary" and timeout == 25.0
        assert args["window"] == [[0.0, 0.0], [10000.0, 6000.0]] and args["most_objects"] == 800
        assert args["layer"] == "A-AREA" and args["islands"] is True and args["make"] == "polyline"
        assert out["handle"] == "3F" and out["area"] == 12.0e6 and out["verified"] is True

    def test_no_answer_in_time_says_what_to_do(self, monkeypatch):
        patch(monkeypatch, cleanup, Doc())
        with_plugin(monkeypatch, Plugin(error=AutocadError("Outcome unknown: no answer")))
        answer = refused(cleanup.autocad_trace_boundary(point_inside=[5, 5], timeout=10))
        assert "longer than 10 s" in answer and "smaller window" in answer

    def test_without_the_plugin_it_cannot_run(self, monkeypatch):
        patch(monkeypatch, cleanup, Doc())
        monkeypatch.setattr(_shared, "plugin_runner", lambda: None)
        assert "plug-in" in refused(cleanup.autocad_trace_boundary(point_inside=[5, 5])).lower()

    def test_it_never_types_boundary_or_bpoly(self):
        import inspect

        source = inspect.getsource(cleanup)
        assert "SendCommand" not in source and "run_lisp" not in source


# ---- clip outlines --------------------------------------------------------------------


class TestClipOutline:
    def test_a_rectangle_from_any_two_corners(self):
        assert clip.rectangle([10, 0], [0, 5]) == [(0, 0), (10, 0), (10, 5), (0, 5)]
        with pytest.raises(AutocadError):
            clip.rectangle([0, 0], [10, 0])

    def test_a_clockwise_outline_is_turned_round(self):
        pts = clip.check([(0, 0), (0, 5), (10, 5), (10, 0)])
        assert clip._area(pts) > 0

    def test_a_repeated_closing_point_is_dropped(self):
        assert len(clip.check([(0, 0), (10, 0), (10, 5), (0, 0)])) == 3

    def test_a_crossing_outline_is_refused(self):
        with pytest.raises(AutocadError, match="crosses itself"):
            clip.check([(0, 0), (10, 10), (10, 0), (0, 10)])

    def test_too_few_or_no_area_is_refused(self):
        with pytest.raises(AutocadError):
            clip.check([(0, 0), (10, 0)])
        with pytest.raises(AutocadError, match="no area"):
            clip.check([(0, 0), (5, 0), (10, 0)])

    def test_an_open_polyline_is_refused(self):
        with pytest.raises(AutocadError, match="open"):
            clip.from_polyline([(0, 0), (10, 0), (10, 5)], [0, 0], False)

    def test_arcs_are_followed_in_short_steps(self):
        # A 1 m half-round end on a 2 m room: every step stays within 1/10,000 of its size.
        pts = clip.from_polyline([(0, 0), (2000, 0), (2000, 1000), (0, 1000)], [0, 1.0, 0, 0], True)
        assert len(pts) > 10
        centre, radius = (2000, 500), 500
        far = [p for p in pts if p[0] > 2000]
        assert far and all(math.dist(p, centre) == pytest.approx(radius) for p in far)
        clip.check(pts)

    def test_the_ring_com_takes_repeats_the_first_corner(self):
        assert clip.closed_ring([(0, 0), (1, 0), (1, 1)]) == [0, 0, 1, 0, 1, 1, 0, 0]


# ---- attach and clip tools ------------------------------------------------------------


class RasterSpace(Space):
    def __init__(self, doc):
        super().__init__()
        self.doc, self.calls = doc, []

    def AddRaster(self, path, insertion, scale, rotation):
        self.calls.append((path, tuple(insertion.value), scale, rotation))
        return Ent(self.doc, "4A", "AcDbRasterImage", ImageWidth=640.0 * scale, ImageHeight=480.0 * scale, ScaleFactor=scale)


class TestAttachUnderlay:
    def setup(self, monkeypatch):
        doc = patch(monkeypatch, xrefs, Doc())
        doc.ModelSpace = RasterSpace(doc)
        monkeypatch.setattr(xrefs, "apply_properties", lambda *a, **k: {})
        return doc

    def test_an_image_is_attached_over_com(self, monkeypatch, tmp_path):
        doc = self.setup(monkeypatch)
        photo = tmp_path / "site.jpg"
        photo.write_bytes(b"\xff\xd8")
        out = call(xrefs.autocad_attach_underlay(path=str(photo), insertion=[100, 200], rotation=90))
        (path, point, scale, rotation), = doc.ModelSpace.calls
        assert path == str(photo) and point == (100.0, 200.0, 0.0) and rotation == pytest.approx(math.pi / 2)
        assert out["kind"] == "image" and out["handle"] == "4A"

    def test_an_image_width_sets_its_scale(self, monkeypatch, tmp_path):
        doc = self.setup(monkeypatch)
        photo = tmp_path / "site.png"
        photo.write_bytes(b"\x89PNG")
        call(xrefs.autocad_attach_underlay(path=str(photo), width=42000))
        assert doc.by_handle["4A"].ScaleFactor == pytest.approx(42000 / 640)

    def test_a_pdf_goes_to_the_plugin_with_its_page(self, monkeypatch, tmp_path):
        doc = self.setup(monkeypatch)
        pdf = tmp_path / "A-101.pdf"
        pdf.write_bytes(b"%PDF")
        Ent(doc, "4B", "AcDbPdfReference")
        plugin = with_plugin(monkeypatch, Plugin({"created": True, "handle": "4B", "kind": "pdf"}))
        out = call(xrefs.autocad_attach_underlay(path=str(pdf), page="3", scale=2, rotation=180, layer="X-BG"))
        (operation, args, _), = plugin.calls
        assert operation == "attach_underlay" and args["kind"] == "pdf" and args["page"] == "3"
        assert args["scale"] == 2.0 and args["rotation"] == pytest.approx(math.pi) and args["layer"] == "X-BG"
        assert out["handle"] == "4B"

    def test_wrong_files_and_options_are_refused_first(self, monkeypatch, tmp_path):
        self.setup(monkeypatch)
        assert "No file" in refused(xrefs.autocad_attach_underlay(path=str(tmp_path / "gone.pdf")))
        dwg = tmp_path / "plan.dwg"
        dwg.write_bytes(b"AC1032")
        assert "autocad_attach_xref" in refused(xrefs.autocad_attach_underlay(path=str(dwg)))
        doc = tmp_path / "spec.docx"
        doc.write_bytes(b"PK")
        assert "not a file AutoCAD attaches" in refused(xrefs.autocad_attach_underlay(path=str(doc)))
        pdf = tmp_path / "a.pdf"
        pdf.write_bytes(b"%PDF")
        assert "width is for images" in refused(xrefs.autocad_attach_underlay(path=str(pdf), width=10))
        jpg = tmp_path / "a.jpg"
        jpg.write_bytes(b"\xff")
        assert "page is for" in refused(xrefs.autocad_attach_underlay(path=str(jpg), page="2"))


class Image(Ent):
    def ClipBoundary(self, points):
        self.doc.set.append((self.Handle, "ClipBoundary", list(points.value)))


class XrefBlock:
    def __init__(self, name, is_xref):
        self.Name, self.IsXRef = name, is_xref


class TestClipReference:
    def drawing(self, monkeypatch):
        doc = patch(monkeypatch, xrefs, Doc())
        doc.Blocks = type("B", (), {"items": [XrefBlock("ARCH", True), XrefBlock("DOOR", False)]})()
        doc.Blocks.Count = 2
        doc.Blocks.Item = lambda i: doc.Blocks.items[i]
        Image(doc, "5A", "AcDbRasterImage", ClippingEnabled=False)
        Ent(doc, "5B", "AcDbBlockReference", Name="ARCH")
        Ent(doc, "5C", "AcDbPdfReference")
        Ent(doc, "5D", "AcDbCircle")
        outline = Ent(doc, "5E", "AcDbPolyline", Coordinates=(0.0, 0.0, 10.0, 0.0, 10.0, 5.0, 0.0, 5.0), Closed=True)
        outline.GetBulge = lambda i: 0.0
        return doc

    def test_an_image_is_clipped_over_com_with_a_closed_ring(self, monkeypatch):
        doc = self.drawing(monkeypatch)
        out = call(xrefs.autocad_clip_reference(handle="5A", corners=[[10, 5], [0, 0]]))
        (handle, what, ring), = [s for s in doc.set if s[1] == "ClipBoundary"]
        assert ring == [0, 0, 10, 0, 10, 5, 0, 5, 0, 0] and doc.by_handle["5A"].ClippingEnabled is True
        assert out["kind"] == "image" and out["points"] == 4 and doc.marks == ["start", "end"]

    def test_an_image_clip_comes_off(self, monkeypatch):
        doc = self.drawing(monkeypatch)
        doc.by_handle["5A"].ClippingEnabled = True
        call(xrefs.autocad_clip_reference(handle="5A", remove=True))
        assert doc.by_handle["5A"].ClippingEnabled is False

    def test_an_xref_goes_to_the_plugin_with_a_polyline_outline(self, monkeypatch):
        self.drawing(monkeypatch)
        plugin = with_plugin(monkeypatch, Plugin({"clipped_as": "block", "clipped": True}))
        out = call(xrefs.autocad_clip_reference(handle="5B", boundary="5E"))
        (operation, args, _), = plugin.calls
        assert operation == "clip_reference" and args["handle"] == "5B" and len(args["points"]) == 4
        assert out["kind"] == "xref" and out["clipped"] is True

    def test_an_underlay_goes_to_the_plugin(self, monkeypatch):
        self.drawing(monkeypatch)
        plugin = with_plugin(monkeypatch, Plugin({}))
        out = call(xrefs.autocad_clip_reference(handle="5C", remove=True))
        assert plugin.calls[0][1] == {"handle": "5C", "points": [], "remove": True} and out["kind"] == "pdf"

    def test_what_cannot_be_clipped_is_refused(self, monkeypatch):
        self.drawing(monkeypatch)
        assert "only an xref" in refused(xrefs.autocad_clip_reference(handle="5D", corners=[[0, 0], [1, 1]]))
        assert "not both" in refused(xrefs.autocad_clip_reference(handle="5A"))
        assert "not both" in refused(xrefs.autocad_clip_reference(handle="5A", corners=[[0, 0], [1, 1]], boundary="5E"))
        assert "give no corners" in refused(xrefs.autocad_clip_reference(handle="5A", remove=True, corners=[[0, 0], [1, 1]]))


# ---- eTransmit ------------------------------------------------------------------------


class TestTransmittalPlan:
    def test_each_file_goes_in_once_by_its_own_name(self, tmp_path):
        a = tmp_path / "Arch" / "A-101.dwg"
        a.parent.mkdir()
        a.write_bytes(b"x")
        needs = [
            transmittal.Need("xref", "..\\Arch\\A-101.dwg", str(a), "ARCH"),
            transmittal.Need("xref", "A-101.dwg", str(a), "ARCH2"),
            transmittal.Need("drawing", "M-101.dwg", str(tmp_path / "M-101.dwg")),
        ]
        out = transmittal.plan(needs)
        assert [r["to"] for r in out["packed"]] == ["M-101.dwg", "A-101.dwg"]
        assert out["packed"][1]["used_by"] == ["ARCH", "ARCH2"]

    def test_missing_files_are_listed_not_guessed(self):
        out = transmittal.plan([transmittal.Need("font", "gothic.shx", "", "text style TITLE")])
        assert out["packed"] == [] and out["missing"] == [{"kind": "font", "name": "gothic.shx", "used_by": "text style TITLE"}]

    def test_two_files_with_one_name_clash(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        one, two = tmp_path / "a" / "logo.png", tmp_path / "b" / "logo.png"
        one.write_bytes(b"1")
        two.write_bytes(b"2")
        out = transmittal.plan([transmittal.Need("image", "logo.png", str(one)), transmittal.Need("image", "logo.png", str(two))])
        assert len(out["packed"]) == 1 and out["clashes"][0]["file"] == str(two)

    def test_plot_styles_go_in_their_own_folder(self, tmp_path):
        ctb = tmp_path / "monochrome.ctb"
        ctb.write_bytes(b"x")
        out = transmittal.plan([transmittal.Need("plot style", "monochrome.ctb", str(ctb), "layout M-101")])
        assert out["packed"][0]["to"] == "PlotStyles/monochrome.ctb"

    def test_find_file_tries_the_whole_path_then_the_bare_name(self, tmp_path):
        f = tmp_path / "romans.shx"
        f.write_bytes(b"x")
        assert transmittal.find_file(str(f), []) == str(f)
        assert transmittal.find_file("C:\\Old\\Fonts\\romans.shx", [str(tmp_path)]) == str(f)
        assert transmittal.find_file("nothere.shx", [str(tmp_path)]) == ""

    def test_an_earlier_pack_is_never_written_over(self, tmp_path):
        (tmp_path / "M-101 - Transmittal.zip").write_bytes(b"old")
        assert transmittal.free_target(tmp_path, "M-101 - Transmittal", True).name == "M-101 - Transmittal (2).zip"
        with pytest.raises(FileExistsError):
            transmittal.write({"packed": []}, tmp_path / "M-101 - Transmittal.zip", True, "")


class XrefBlocks:
    def __init__(self, *blocks):
        self.items = list(blocks)

    @property
    def Count(self):
        return len(self.items)

    def Item(self, i):
        return self.items[i]


class XrefNode:
    def __init__(self, name, path, loaded=True):
        self.Name, self.Path, self.IsXRef = name, path, True
        self.XRefDatabase = object() if loaded else None


class TransmitDoc:
    def __init__(self, full, saved=True, blocks=()):
        self.FullName, self.Saved = str(full), saved
        self.Path = str(full.parent) if full else ""
        self.Name = full.name if full else "Drawing1.dwg"
        self.Blocks = XrefBlocks(*blocks)
        files = type("F", (), {"PrinterStyleSheetPath": ""})()
        self.Application = type("A", (), {"Preferences": type("P", (), {"Files": files})()})()


class TestETransmitTool:
    def project(self, tmp_path):
        (tmp_path / "Arch").mkdir()
        (tmp_path / "Styles").mkdir()
        drawing = tmp_path / "M-101.dwg"
        drawing.write_bytes(b"AC1032 host")
        (tmp_path / "Arch" / "A-101.dwg").write_bytes(b"AC1032 arch")
        (tmp_path / "romans.shx").write_bytes(b"shx")
        (tmp_path / "Styles" / "Heron.ctb").write_bytes(b"ctb")
        doc = TransmitDoc(drawing, blocks=[XrefNode("ARCH", "Arch\\A-101.dwg"), XrefNode("SURVEY", "D:\\Gone\\S.dwg", loaded=False)])
        doc.Application.Preferences.Files.PrinterStyleSheetPath = str(tmp_path / "Styles")
        deps = {
            "fonts": [{"name": "romans.shx", "found": str(tmp_path / "romans.shx"), "used_by": "text style STANDARD"}],
            "images": [{"name": "D:\\Photos\\site.jpg", "found": "", "used_by": "image site"}],
            "underlays": [],
            "system_fonts": ["Arial"],
            "plot_styles": [{"name": "Heron.ctb", "used_by": "layout M-101"}],
            "xrefs": [],
        }
        return doc, deps

    def test_it_packs_a_zip_and_lists_what_is_missing(self, monkeypatch, tmp_path):
        doc, deps = self.project(tmp_path)
        monkeypatch.setattr(cleanup, "run", _now)
        monkeypatch.setattr(cleanup, "get_doc", lambda: doc)
        plugin = with_plugin(monkeypatch, Plugin(deps))
        out = call(cleanup.autocad_etransmit(name="Issue 1"))
        assert plugin.calls[0][0] == "list_dependencies"
        assert out["pack"].endswith("Issue 1.zip")
        with zipfile.ZipFile(out["pack"]) as pack:
            names = set(pack.namelist())
        assert names == {"M-101.dwg", "A-101.dwg", "romans.shx", "PlotStyles/Heron.ctb", "transmittal report.txt"}
        missing = {(m["kind"], m["name"]) for m in out["missing"]}
        assert missing == {("xref", "D:\\Gone\\S.dwg"), ("image", "D:\\Photos\\site.jpg")}
        assert out["system_fonts"] == ["Arial"] and "warning" in out

    def test_list_only_writes_nothing(self, monkeypatch, tmp_path):
        doc, deps = self.project(tmp_path)
        monkeypatch.setattr(cleanup, "run", _now)
        monkeypatch.setattr(cleanup, "get_doc", lambda: doc)
        with_plugin(monkeypatch, Plugin(deps))
        out = call(cleanup.autocad_etransmit(list_only=True, as_zip=False))
        assert out["written"] == [] and not any(p.name.startswith("M-101 - Transmittal") for p in tmp_path.iterdir())
        assert len(out["packed"]) == 4

    def test_a_folder_pack_has_the_report(self, monkeypatch, tmp_path):
        doc, deps = self.project(tmp_path)
        monkeypatch.setattr(cleanup, "run", _now)
        monkeypatch.setattr(cleanup, "get_doc", lambda: doc)
        with_plugin(monkeypatch, Plugin(deps))
        out = call(cleanup.autocad_etransmit(as_zip=False))
        report = (tmp_path / out["pack"].split("/")[-1].split("\\")[-1] / "transmittal report.txt").read_text()
        assert "Missing (2)" in report and "PlotStyles" in report

    def test_an_unsaved_drawing_is_refused(self, monkeypatch, tmp_path):
        doc, deps = self.project(tmp_path)
        doc.Saved = False
        monkeypatch.setattr(cleanup, "run", _now)
        monkeypatch.setattr(cleanup, "get_doc", lambda: doc)
        plugin = with_plugin(monkeypatch, Plugin(deps))
        assert "not saved" in refused(cleanup.autocad_etransmit())
        assert plugin.calls == []

    def test_a_drawing_never_saved_is_refused(self, monkeypatch, tmp_path):
        doc = TransmitDoc(tmp_path / "Drawing1.dwg")
        monkeypatch.setattr(cleanup, "run", _now)
        monkeypatch.setattr(cleanup, "get_doc", lambda: doc)
        assert "never been saved" in refused(cleanup.autocad_etransmit())

    def test_a_folder_that_is_not_there_is_refused(self, tmp_path):
        assert "does not exist" in refused(cleanup.autocad_etransmit(folder=str(tmp_path / "nope")))
