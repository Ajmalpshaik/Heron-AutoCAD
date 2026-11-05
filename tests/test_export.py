"""autocad_export's PDF path, exercised against fake COM objects.

PlotToFile(path, "DWG To PDF.pc3") raises a bare "Exception occurred" on
AutoCAD 2027. What works is configuring the layout for the plotter first and
then calling PlotToFile with the path alone, so these tests pin that order
down — along with putting the user's page setup back afterwards.
"""

from __future__ import annotations

import json
import os

import pytest
import pythoncom

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import document
from autocad_mcp.tools.document import (
    AC_EXTENTS,
    AC_SCALE_TO_FIT,
    PDF_PLOTTER,
    PLOT_AREAS,
    SNAPSHOT_NAME,
    _match_media,
    _plot_pdf,
)

# A slice of what DWG To PDF.pc3 offers, in AutoCAD's own order.
MEDIA = (
    "ANSI_A_(11.00_x_8.50_Inches)",
    "ANSI_A_(8.50_x_11.00_Inches)",
    "ANSI_expand_B_(17.00_x_11.00_Inches)",
    "ANSI_full_bleed_B_(17.00_x_11.00_Inches)",
    "ARCH_E1_(42.00_x_30.00_Inches)",
    "ARCH_full_bleed_E_(48.00_x_36.00_Inches)",
    "ISO_A1_(841.00_x_594.00_MM)",
    "ISO_A3_(297.00_x_420.00_MM)",
    "ISO_A3_(420.00_x_297.00_MM)",
    "ISO_expand_A3_(420.00_x_297.00_MM)",
    "ISO_full_bleed_A3_(297.00_x_420.00_MM)",
    "ISO_full_bleed_A3_(420.00_x_297.00_MM)",
)

PAGE_SETUP = (
    "ConfigName",
    "CanonicalMediaName",
    "PlotType",
    "UseStandardScale",
    "StandardScale",
    "CustomScale",
    "CenterPlot",
    "PlotRotation",
)


class FakePlotConfiguration:
    def __init__(self, configs, name):
        self.configs = configs
        self.name = name
        self.state = {}

    def CopyFrom(self, other):
        self.state = {key: other.state[key] for key in PAGE_SETUP}

    def Delete(self):
        del self.configs.items[self.name]


class FakePlotConfigurations:
    def __init__(self):
        self.items = {}

    def Item(self, name):
        return self.items[name]

    def Add(self, name, model_type):
        self.items[name] = FakePlotConfiguration(self, name)
        return self.items[name]


class FakeLayout:
    """Records every page-setup write and method call, in order."""

    def __init__(self, events, missing_plotter=False, autocad_2027=False):
        self.__dict__.update(
            events=events,
            missing_plotter=missing_plotter,
            autocad_2027=autocad_2027,
            state={
                "Name": "Model",
                "ModelType": True,
                "ConfigName": "Microsoft Print to PDF",
                "CanonicalMediaName": "",
                "PlotType": 0,
                "UseStandardScale": False,
                "StandardScale": 7,
                "CustomScale": 1.0,
                "ViewToPlot": "",
                "CenterPlot": False,
                # A sheet set to plot turned 90 degrees, as the cassette drawing was.
                "PlotRotation": 1,
            },
        )

    def __getattr__(self, name):
        try:
            return self.state[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        if name == "ConfigName" and self.missing_plotter and value == PDF_PLOTTER:
            # What AutoCAD raises when the .pc3 is not installed.
            raise pythoncom.com_error(
                -2147352567,
                "Exception occurred.",
                (0, "AutoCAD.Application", "Invalid input", None, 0, -2147024809),
                None,
            )
        if self.autocad_2027 and name == "CenterPlot" and value and self.state["PlotType"] == 5:
            # Seen live 2026-10-28: centring a layout plot is refused.
            raise pythoncom.com_error(-2147352567, "Exception occurred.", None, None)
        self.events.append(("set", name, value))
        self.state[name] = value
        if self.autocad_2027 and name == "ConfigName":
            # Seen live 2026-10-28: choosing the plotter drops the sheet to its default.
            self.state["CanonicalMediaName"] = MEDIA[0]

    def RefreshPlotDeviceInfo(self):
        self.events.append(("call", "RefreshPlotDeviceInfo"))
        # Like AutoCAD: media the new device lacks falls back to its default.
        if self.state["CanonicalMediaName"] not in MEDIA:
            self.state["CanonicalMediaName"] = MEDIA[0]

    def GetCanonicalMediaNames(self):
        return MEDIA

    def GetLocaleMediaName(self, name):
        return name.replace("_", " ")

    def CopyFrom(self, other):
        self.events.append(("call", "CopyFrom"))
        self.state.update(other.state)


class FakePlot:
    def __init__(self, doc, write=True, fail=False):
        self.doc = doc
        self.write = write
        self.fail = fail
        self.QuietErrorMode = False
        self.calls = []

    def PlotToFile(self, *args):
        self.calls.append(
            {
                "args": args,
                "layout": dict(self.doc.ActiveLayout.state),
                "backgroundplot": self.doc.vars["BACKGROUNDPLOT"],
                "quiet": self.QuietErrorMode,
            }
        )
        self.doc.events.append(("call", "PlotToFile"))
        if self.fail:
            raise OSError("Exception occurred.")
        if self.write:
            with open(args[0], "wb") as fh:
                fh.write(b"%PDF-1.7 fake")
        return True


class FakeDoc:
    def __init__(self, write=True, fail=False, missing_plotter=False, autocad_2027=False):
        self.events = []
        self.vars = {"BACKGROUNDPLOT": 2}
        self.ActiveLayout = FakeLayout(self.events, missing_plotter, autocad_2027)
        self.PlotConfigurations = FakePlotConfigurations()
        self.Plot = FakePlot(self, write=write, fail=fail)

    def GetVariable(self, name):
        return self.vars[name]

    def SetVariable(self, name, value):
        self.vars[name] = value

    def StartUndoMark(self):
        pass

    def EndUndoMark(self):
        pass


@pytest.fixture
def doc():
    return FakeDoc()


@pytest.fixture
def target(tmp_path):
    return str(tmp_path / "plan.pdf")


class TestPlotPdf:
    def test_plot_to_file_gets_only_the_path(self, doc, target):
        _plot_pdf(doc, target, None)
        # The two-argument form is the one that fails on AutoCAD 2027.
        assert doc.Plot.calls[0]["args"] == (target,)

    def test_layout_is_set_up_for_pdf_before_plotting(self, doc, target):
        _plot_pdf(doc, target, None)
        at_plot = doc.Plot.calls[0]["layout"]
        assert at_plot["ConfigName"] == PDF_PLOTTER
        assert at_plot["PlotType"] == AC_EXTENTS
        assert at_plot["UseStandardScale"] is True
        assert at_plot["StandardScale"] == AC_SCALE_TO_FIT
        assert at_plot["CenterPlot"] is True

    def test_device_info_is_refreshed_after_choosing_the_plotter(self, doc, target):
        _plot_pdf(doc, target, None)
        events = doc.events
        chose = events.index(("set", "ConfigName", PDF_PLOTTER))
        refreshed = events.index(("call", "RefreshPlotDeviceInfo"))
        plotted = events.index(("call", "PlotToFile"))
        assert chose < refreshed < plotted

    def test_plots_in_the_foreground_with_quiet_errors(self, doc, target):
        _plot_pdf(doc, target, None)
        assert doc.Plot.calls[0]["backgroundplot"] == 0
        assert doc.Plot.calls[0]["quiet"] is True

    def test_page_setup_and_plot_settings_are_put_back(self, doc, target):
        before = {key: doc.ActiveLayout.state[key] for key in PAGE_SETUP}
        _plot_pdf(doc, target, None)
        after = {key: doc.ActiveLayout.state[key] for key in PAGE_SETUP}
        assert after == before
        assert doc.vars["BACKGROUNDPLOT"] == 2
        assert doc.Plot.QuietErrorMode is False
        assert doc.PlotConfigurations.items == {}

    def test_settings_are_put_back_when_the_plot_fails(self, target):
        doc = FakeDoc(fail=True)
        with pytest.raises(OSError):
            _plot_pdf(doc, target, None)
        assert doc.ActiveLayout.state["ConfigName"] == "Microsoft Print to PDF"
        assert doc.vars["BACKGROUNDPLOT"] == 2
        assert doc.Plot.QuietErrorMode is False
        assert doc.PlotConfigurations.items == {}

    def test_a_failed_restore_after_a_good_plot_is_a_warning(self, doc, target):
        def broken_copy(other):
            raise OSError("restore failed")

        doc.ActiveLayout.__dict__["CopyFrom"] = broken_copy
        result = _plot_pdf(doc, target, None)
        assert "page setup" in result["warning"]
        # the other settings are still put back
        assert doc.vars["BACKGROUNDPLOT"] == 2
        assert doc.PlotConfigurations.items == {}

    def test_a_failed_restore_does_not_hide_the_plot_error(self, target):
        doc = FakeDoc(fail=True)

        def broken_copy(other):
            raise ValueError("restore failed")

        doc.ActiveLayout.__dict__["CopyFrom"] = broken_copy
        with pytest.raises(OSError, match="Exception occurred"):
            _plot_pdf(doc, target, None)

    def test_a_leftover_snapshot_is_replaced(self, doc, target):
        doc.PlotConfigurations.Add(SNAPSHOT_NAME, True)
        _plot_pdf(doc, target, None)
        assert doc.PlotConfigurations.items == {}

    def test_without_paper_size_the_current_media_is_kept(self, doc, target):
        doc.ActiveLayout.state["CanonicalMediaName"] = "ISO_A1_(841.00_x_594.00_MM)"
        result = _plot_pdf(doc, target, None)
        media = doc.Plot.calls[0]["layout"]["CanonicalMediaName"]
        assert media == "ISO_A1_(841.00_x_594.00_MM)"
        assert result["paper"] == "ISO A1 (841.00 x 594.00 MM)"

    def test_paper_size_selects_the_media(self, doc, target):
        result = _plot_pdf(doc, target, "A3")
        media = doc.Plot.calls[0]["layout"]["CanonicalMediaName"]
        assert media == "ISO_full_bleed_A3_(420.00_x_297.00_MM)"
        assert result == {
            "layout": "Model",
            "paper": "ISO full bleed A3 (420.00 x 297.00 MM)",
            "area": "extents",
        }

    def test_unknown_paper_size_fails_before_plotting(self, doc, target):
        with pytest.raises(AutocadError, match="A7"):
            _plot_pdf(doc, target, "A7")
        assert doc.Plot.calls == []
        assert doc.ActiveLayout.state["ConfigName"] == "Microsoft Print to PDF"

    def test_missing_plotter_is_named_in_the_error(self, target):
        doc = FakeDoc(missing_plotter=True)
        with pytest.raises(AutocadError, match="DWG To PDF.pc3"):
            _plot_pdf(doc, target, None)
        assert doc.PlotConfigurations.items == {}


class TestPlotArea:
    """area='window' / 'view' / 'layout': plotting a location rather than the lot."""

    def test_extents_is_still_the_default(self, doc, target):
        _plot_pdf(doc, target, None)
        assert doc.Plot.calls[0]["layout"]["PlotType"] == AC_EXTENTS

    def test_a_window_is_set_before_the_plot_type(self, doc, target):
        corners = []
        doc.ActiveLayout.__dict__["SetWindowToPlot"] = lambda a, b: corners.append((a, b))
        result = _plot_pdf(doc, target, None, "window", ("ll", "ur"))
        assert corners == [("ll", "ur")]
        assert doc.Plot.calls[0]["layout"]["PlotType"] == PLOT_AREAS["window"]
        assert result["area"] == "window"

    def test_a_saved_view_is_named_on_the_layout(self, doc, target):
        result = _plot_pdf(doc, target, None, "view", None, "DETAIL-A")
        assert doc.ActiveLayout.state["ViewToPlot"] == "DETAIL-A"
        assert doc.Plot.calls[0]["layout"]["PlotType"] == PLOT_AREAS["view"]
        assert result["view"] == "DETAIL-A"

    def test_the_sheet_itself_plots_at_a_real_scale(self, doc, target):
        result = _plot_pdf(doc, target, None, "layout", None, None, "1:1")
        at_plot = doc.Plot.calls[0]["layout"]
        assert at_plot["PlotType"] == PLOT_AREAS["layout"]
        assert at_plot["UseStandardScale"] is False
        assert at_plot["CustomScale"] == 1.0
        assert result["scale"] == "1:1"

    def test_a_layout_plot_is_not_centred(self, target):
        doc = FakeDoc(autocad_2027=True)
        _plot_pdf(doc, target, None, "layout", None, None, "1:1")
        assert doc.Plot.calls[0]["layout"]["CenterPlot"] is False
        assert ("set", "CenterPlot", True) not in doc.events

    def test_choosing_the_plotter_keeps_the_layouts_own_sheet(self, target):
        doc = FakeDoc(autocad_2027=True)
        doc.ActiveLayout.state["ConfigName"] = PDF_PLOTTER
        doc.ActiveLayout.state["CanonicalMediaName"] = "ISO_A1_(841.00_x_594.00_MM)"
        result = _plot_pdf(doc, target, None, "layout", None, None, "1:1")
        assert doc.Plot.calls[0]["layout"]["CanonicalMediaName"] == "ISO_A1_(841.00_x_594.00_MM)"
        assert result["paper"] == "ISO A1 (841.00 x 594.00 MM)"

    def test_without_a_scale_it_still_fits_the_sheet(self, doc, target):
        result = _plot_pdf(doc, target, None, "layout")
        assert doc.Plot.calls[0]["layout"]["StandardScale"] == AC_SCALE_TO_FIT
        assert "scale" not in result


class TestMatchMedia:
    @pytest.mark.parametrize(
        ("wanted", "expected"),
        [
            # short names prefer the full-bleed landscape sheet
            ("A3", "ISO_full_bleed_A3_(420.00_x_297.00_MM)"),
            ("iso a3", "ISO_full_bleed_A3_(420.00_x_297.00_MM)"),
            ("A3 portrait", "ISO_full_bleed_A3_(297.00_x_420.00_MM)"),
            ("ANSI B", "ANSI_full_bleed_B_(17.00_x_11.00_Inches)"),
            # with only one variant on offer, that variant is used
            ("A1", "ISO_A1_(841.00_x_594.00_MM)"),
            ("ansi a portrait", "ANSI_A_(8.50_x_11.00_Inches)"),
            # E must not pick up E1, nor E1 pick up E
            ("ARCH E", "ARCH_full_bleed_E_(48.00_x_36.00_Inches)"),
            ("ARCH E1", "ARCH_E1_(42.00_x_30.00_Inches)"),
            # exact canonical and display names are taken as given
            ("ISO_A3_(297.00_x_420.00_MM)", "ISO_A3_(297.00_x_420.00_MM)"),
            (
                "ISO expand A3 (420.00 x 297.00 MM)",
                "ISO_expand_A3_(420.00_x_297.00_MM)",
            ),
        ],
    )
    def test_picks_the_expected_sheet(self, wanted, expected):
        assert _match_media(MEDIA, wanted) == expected

    def test_unknown_size_lists_the_sizes_on_offer(self):
        with pytest.raises(AutocadError) as exc:
            _match_media(MEDIA, "A7")
        message = str(exc.value)
        assert "'A7'" in message
        for size in ("ISO A3", "ANSI B", "ARCH E1"):
            assert size in message
        assert "full_bleed" not in message


@pytest.fixture
def offline(monkeypatch):
    """Route autocad_export's COM work to a fake document, in-process."""
    fake = FakeDoc()

    async def run(fn):
        return fn()

    monkeypatch.setattr(document, "run", run)
    monkeypatch.setattr(document, "get_doc", lambda: fake)
    return fake


class TestExportTool:
    async def test_pdf_export_reports_the_written_file(self, offline, target):
        result = json.loads(await document.autocad_export(path=target))
        assert result["exported"] is True
        assert result["format"] == "pdf"
        assert result["path"] == target
        assert result["size_bytes"] == os.path.getsize(target) > 0
        assert result["paper"] == "ANSI A (11.00 x 8.50 Inches)"

    async def test_paper_size_reaches_the_plotter(self, offline, target):
        result = json.loads(await document.autocad_export(path=target, paper_size="A3"))
        assert result["paper"] == "ISO full bleed A3 (420.00 x 297.00 MM)"

    async def test_no_file_written_is_an_error(self, offline, target):
        offline.Plot.write = False
        result = await document.autocad_export(path=target)
        assert result.startswith("Error:")
        assert "did not write" in result

    async def test_a_stale_file_from_an_earlier_export_is_not_success(
        self, offline, target
    ):
        with open(target, "wb") as fh:
            fh.write(b"%PDF old")
        os.utime(target, (1_000_000_000, 1_000_000_000))
        offline.Plot.write = False
        result = await document.autocad_export(path=target)
        assert result.startswith("Error:")
        assert "earlier export" in result

    async def test_paper_size_is_rejected_for_other_formats(self, offline, tmp_path):
        result = await document.autocad_export(
            path=str(tmp_path / "plan.dxf"), paper_size="A3"
        )
        assert result.startswith("Error:")
        assert "only applies to PDF" in result
