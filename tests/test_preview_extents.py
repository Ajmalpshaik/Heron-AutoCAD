"""autocad_preview on a full sheet (issue #41, D-102).

On 2026-10-28 an extents preview of an A1 schematic drawn at 1:1 showed only
the two frame rectangles, while window previews over its parts showed
everything. AutoCAD's PNG plotter has fixed pixel sizes, so a whole A1 sheet
fitted into about 1600 pixels leaves about half a millimetre per pixel: thin
lines and 2.5 mm text cannot show. Extents bigger than the sheet (a stray or
erased object far off) make it worse. These tests pin what the code can do:
say which area was plotted and how small a text still reads, and plot close-up
windows of the same area (window plots showed everything live).
"""

from __future__ import annotations

import json
import os

import pytest
from mcp.server.mcpserver import Image
from test_export import FakeDoc, FakeLayout

from autocad_mcp.core.registry import mcp
from autocad_mcp.tools import document

# What PublishToWeb PNG.pc3 offers, in its naming style.
PNG_MEDIA = (
    "VGA_(640.00_x_480.00_Pixels)",
    "XGA_(1024.00_x_768.00_Pixels)",
    "Sun_Hi-Res_(1600.00_x_1280.00_Pixels)",
    "UXGA_(1600.00_x_1200.00_Pixels)",
)

A1 = ((0.0, 0.0, 0.0), (841.0, 594.0, 0.0))


class PreviewLayout(FakeLayout):
    """A layout that offers pixel sizes once the PNG plotter is chosen."""

    def __init__(self, events, model=True):
        super().__init__(events)
        self.state.update(Name="Model" if model else "Sheet-01", ModelType=model)
        self.state["windows"] = []

    def GetCanonicalMediaNames(self):
        if self.state["ConfigName"] == document.PNG_PLOTTER:
            return PNG_MEDIA
        return super().GetCanonicalMediaNames()

    def RefreshPlotDeviceInfo(self):
        self.events.append(("call", "RefreshPlotDeviceInfo"))

    def SetWindowToPlot(self, low, high):
        self.events.append(("call", "SetWindowToPlot"))
        self.state["windows"].append((list(low.value), list(high.value)))
        self.state["Window"] = (list(low.value), list(high.value))


class PreviewDoc(FakeDoc):
    def __init__(self, extents=A1, model=True, view_dir=(0.0, 0.0, 1.0), text_size=2.5):
        super().__init__()
        self.ActiveLayout = PreviewLayout(self.events, model)
        self.vars.update(
            EXTMIN=extents[0],
            EXTMAX=extents[1],
            PEXTMIN=(0.0, 0.0, 0.0),
            PEXTMAX=(420.0, 297.0, 0.0),
            VIEWDIR=view_dir,
            WORLDUCS=1,
            VIEWTWIST=0.0,
            TEXTSIZE=text_size,
        )
        self.regens = []

    def Regen(self, which):
        self.regens.append(which)
        self.events.append(("call", "Regen"))


@pytest.fixture
def make_doc(monkeypatch):
    def make(**kwargs):
        fake = PreviewDoc(**kwargs)

        async def run(fn):
            return fn()

        monkeypatch.setattr(document, "run", run)
        monkeypatch.setattr(document, "get_doc", lambda: fake)
        return fake

    return make


def _info(result) -> dict:
    return json.loads(result[-1])


class TestTheAnswerSaysWhatWasPlotted:
    async def test_an_extents_preview_names_the_area_and_the_pixels(self, make_doc):
        make_doc()
        info = _info(await document.autocad_preview())
        assert info["plotted"] == {"min": [0.0, 0.0], "max": [841.0, 594.0], "width": 841.0, "height": 594.0}
        # Two sizes are 1600 wide; either is the one nearest the wanted width.
        assert info["pixels"][0] == 1600
        assert f"{info['pixels'][0]}.00_x_{info['pixels'][1]}.00" in "".join(PNG_MEDIA)

    async def test_it_says_how_small_a_text_still_reads(self, make_doc):
        # An A1 sheet across 1600 pixels: about 0.53 mm a pixel, 8 pixels a letter.
        make_doc()
        info = _info(await document.autocad_preview())
        assert info["smallest_clear_text"] == pytest.approx(8 * 841 / 1600, rel=0.01)

    async def test_text_smaller_than_that_gets_a_tip_to_look_closer(self, make_doc):
        make_doc(text_size=2.5)
        info = _info(await document.autocad_preview())
        assert "detail=2" in info["tip"]

    async def test_a_small_sheet_with_big_text_gets_no_tip(self, make_doc):
        make_doc(extents=((0.0, 0.0, 0.0), (210.0, 148.0, 0.0)), text_size=5.0)
        info = _info(await document.autocad_preview())
        assert "tip" not in info

    async def test_the_extents_are_refreshed_before_they_are_read(self, make_doc):
        # EXTMIN/EXTMAX lag behind erased objects; a regen first, as autocad_get_extents does.
        doc = make_doc()
        await document.autocad_preview()
        assert doc.regens
        assert doc.events.index(("call", "Regen")) < doc.events.index(("call", "PlotToFile"))

    async def test_a_paper_layout_reports_its_paper_extents(self, make_doc):
        make_doc(model=False)
        info = _info(await document.autocad_preview())
        assert info["plotted"]["max"] == [420.0, 297.0]

    async def test_an_empty_drawing_still_previews_without_an_area(self, make_doc):
        # AutoCAD reports EXTMIN 1e20 and EXTMAX -1e20 when nothing is drawn.
        make_doc(extents=((1e20, 1e20, 1e20), (-1e20, -1e20, -1e20)))
        info = _info(await document.autocad_preview())
        assert "plotted" not in info

    async def test_a_3d_view_reports_no_plan_area(self, make_doc):
        # The box is in plan; a south-west view does not map onto the picture.
        make_doc(view_dir=(-1.0, -1.0, 1.0))
        info = _info(await document.autocad_preview())
        assert "plotted" not in info

    async def test_a_window_preview_reports_its_own_corners(self, make_doc):
        make_doc()
        info = _info(await document.autocad_preview(area="window", corner1=[600, 400], corner2=[100, 50]))
        assert info["plotted"]["min"] == [100.0, 50.0]
        assert info["plotted"]["max"] == [600.0, 400.0]


class TestDetailGivesCloseUpsOfTheSameArea:
    async def test_default_is_one_picture_as_before(self, make_doc):
        doc = make_doc()
        result = await document.autocad_preview()
        assert [type(block) for block in result] == [Image, str]
        assert len(doc.Plot.calls) == 1

    async def test_detail_2_adds_four_window_quarters(self, make_doc):
        doc = make_doc()
        result = await document.autocad_preview(detail=2)
        assert [type(block) for block in result] == [Image] * 5 + [str]
        assert len(doc.Plot.calls) == 5
        # The overview is AutoCAD's own extents plot; the quarters are windows.
        assert doc.Plot.calls[0]["layout"]["PlotType"] == document.AC_EXTENTS
        assert all(call["layout"]["PlotType"] == 4 for call in doc.Plot.calls[1:])
        info = _info(result)
        assert [part["part"] for part in info["detail"]] == ["top left", "top right", "bottom left", "bottom right"]
        assert [part["picture"] for part in info["detail"]] == [2, 3, 4, 5]

    async def test_the_quarters_cover_the_sheet_and_overlap(self, make_doc):
        doc = make_doc()
        await document.autocad_preview(detail=2)
        windows = doc.ActiveLayout.state["windows"]
        top_left, top_right, bottom_left, bottom_right = windows
        assert top_left[0][0] < 0 and top_left[1][1] > 594
        assert bottom_right[0][1] < 0 and bottom_right[1][0] > 841
        # Neighbours share a strip, so a part on the seam shows whole in one.
        assert top_left[1][0] > top_right[0][0]
        assert bottom_left[1][1] > top_left[0][1]

    async def test_close_ups_read_text_the_overview_cannot(self, make_doc):
        make_doc()
        info = _info(await document.autocad_preview(detail=2))
        assert info["detail_smallest_clear_text"] < 2.5 < info["smallest_clear_text"]
        assert "tip" not in info

    async def test_detail_3_gives_nine_parts_with_a_centre(self, make_doc):
        make_doc()
        info = _info(await document.autocad_preview(detail=3))
        parts = [part["part"] for part in info["detail"]]
        assert len(parts) == 9
        assert parts[4] == "centre"
        assert parts[0] == "top left" and parts[-1] == "bottom right"

    async def test_detail_on_a_window_splits_that_window(self, make_doc):
        doc = make_doc()
        await document.autocad_preview(area="window", corner1=[0, 0], corner2=[400, 200], detail=2)
        windows = doc.ActiveLayout.state["windows"]
        assert len(windows) == 5  # the window itself, then its four quarters
        assert windows[0] == ([0.0, 0.0], [400.0, 200.0])
        assert max(w[1][0] for w in windows[1:]) < 450

    async def test_detail_on_the_current_view_is_refused(self, make_doc):
        doc = make_doc()
        result = await document.autocad_preview(area="view", detail=2)
        assert isinstance(result, str) and result.startswith("Error:")
        assert "window" in result
        assert not doc.Plot.calls

    async def test_detail_in_a_3d_view_gives_the_overview_and_says_why(self, make_doc):
        doc = make_doc(view_dir=(-1.0, -1.0, 1.0))
        result = await document.autocad_preview(detail=2)
        assert len(doc.Plot.calls) == 1
        assert "plan" in _info(result)["detail_skipped"]

    @pytest.mark.parametrize(
        "view",
        [{"view_dir": (-1.0, -1.0, 1.0)}, {"worlducs": 0}, {"twist": 0.5}],
        ids=["iso view", "turned UCS", "twisted view"],
    )
    async def test_detail_on_a_window_out_of_plan_gives_the_window_alone_and_says_why(self, make_doc, view):
        # #218 item 4: D-102 skips close-ups out of plan; a window was split all the same.
        doc = make_doc(view_dir=view.get("view_dir", (0.0, 0.0, 1.0)))
        doc.vars.update(WORLDUCS=view.get("worlducs", 1), VIEWTWIST=view.get("twist", 0.0))
        result = await document.autocad_preview(area="window", corner1=[0, 0], corner2=[400, 200], detail=2)
        assert len(doc.Plot.calls) == 1
        assert doc.ActiveLayout.state["windows"] == [([0.0, 0.0], [400.0, 200.0])]
        info = _info(result)
        assert "detail" not in info and "plan" in info["detail_skipped"]

    async def test_detail_on_a_sheet_window_still_splits_it_in_any_model_view(self, make_doc):
        # A paper layout is always flat: the 3D view of model space does not matter there.
        doc = make_doc(model=False, view_dir=(-1.0, -1.0, 1.0))
        await document.autocad_preview(area="window", corner1=[0, 0], corner2=[400, 200], detail=2)
        assert len(doc.Plot.calls) == 5

    async def test_the_page_setup_is_put_back_after_the_close_ups(self, make_doc):
        doc = make_doc()
        before = {k: v for k, v in doc.ActiveLayout.state.items() if k != "windows"}
        await document.autocad_preview(detail=2)
        after = {k: v for k, v in doc.ActiveLayout.state.items() if k not in ("windows", "Window")}
        assert after == before
        assert doc.vars["BACKGROUNDPLOT"] == 2

    async def test_no_picture_files_are_left_behind(self, make_doc, monkeypatch, tmp_path):
        made = []
        real = document.tempfile.mkdtemp

        def mkdtemp(prefix=""):
            made.append(real(prefix=prefix, dir=tmp_path))
            return made[-1]

        monkeypatch.setattr(document.tempfile, "mkdtemp", mkdtemp)
        make_doc()
        await document.autocad_preview(detail=2)
        assert made and not os.path.exists(made[0])

    async def test_the_close_ups_survive_the_mcp_layer(self, make_doc):
        make_doc()
        result = await mcp.call_tool("autocad_preview", {"detail": 2})
        kinds = [type(block).__name__ for block in result.content]
        assert kinds == ["ImageContent"] * 5 + ["TextContent"]
