"""What went wrong drawing the SAC2 split AC set live on 2026-11-22 (D-125). No AutoCAD.

- The preview plotted SAC2-102 while SAC2-104 was on screen: COM's ActiveLayout
  had not followed the tab (CTAB).
- create_layout's A1 landscape read back as a 594 x 841 portrait sheet: the new
  layout kept a template's 90 degree plot turn.
- autocad_page_setup with orientation alone was ignored.
- dimension_run mode='overall' drew 4400 and said "total": 0.
"""

from __future__ import annotations

import pytest

from autocad_mcp.acad import sheets as plan
from autocad_mcp.tools import document, sheets
from autocad_mcp.tools.dimensions import plan_run, run_total

A1_LANDSCAPE = "ISO_full_bleed_A1_(841.00_x_594.00_MM)"
A1_PORTRAIT = "ISO_full_bleed_A1_(594.00_x_841.00_MM)"
MEDIA = (A1_LANDSCAPE, A1_PORTRAIT, "ISO_A1_(841.00_x_594.00_MM)", "ISO_A1_(594.00_x_841.00_MM)")


class Layout:
    def __init__(self, name, media=A1_LANDSCAPE, rotation=0):
        self.Name = name
        self.CanonicalMediaName = media
        self.ConfigName = "DWG To PDF.pc3"
        self.PlotRotation = rotation

    def GetCanonicalMediaNames(self):
        return MEDIA

    def GetLocaleMediaName(self, name):
        return name.replace("_", " ")

    def GetPaperSize(self):
        size = plan.media_dimensions(self.CanonicalMediaName)
        return size

    def GetPaperMargins(self):
        return ((0.0, 0.0), (0.0, 0.0))


class Layouts:
    def __init__(self, names):
        self.items = [Layout(n) for n in names]

    @property
    def Count(self):
        return len(self.items)

    def Item(self, index):
        return self.items[index]


class Doc:
    def __init__(self, names=("Model", "SAC2-102", "SAC2-104"), active="SAC2-102", ctab="SAC2-104"):
        self.Layouts = Layouts(names)
        self.ActiveLayout = next(layout for layout in self.Layouts.items if layout.Name == active)
        self.ctab = ctab

    def GetVariable(self, name):
        if name == "CTAB":
            if self.ctab is None:
                raise KeyError(name)
            return self.ctab
        raise KeyError(name)


# ---------------------------------------------------------------------------
# The tab on screen (item 3)
# ---------------------------------------------------------------------------


class TestTheTabOnScreen:
    def test_ctab_wins_over_a_stale_active_layout(self):
        doc = Doc()
        assert document.layout_on_screen(doc).Name == "SAC2-104"

    def test_when_they_agree_it_is_the_active_layout_itself(self):
        doc = Doc(active="SAC2-104")
        assert document.layout_on_screen(doc) is doc.ActiveLayout

    def test_an_unreadable_ctab_falls_back_to_the_active_layout(self):
        doc = Doc(ctab=None)
        assert document.layout_on_screen(doc).Name == "SAC2-102"

    def test_a_ctab_naming_no_layout_falls_back_too(self):
        doc = Doc(ctab="Gone")
        assert document.layout_on_screen(doc).Name == "SAC2-102"

    def test_a_plot_makes_the_tab_on_screen_the_active_one_and_says_so(self):
        doc = Doc()
        layout, note = document._on_screen_for_plot(doc)
        assert layout.Name == "SAC2-104" and doc.ActiveLayout.Name == "SAC2-104"
        assert "SAC2-102" in note and "SAC2-104" in note

    def test_nothing_is_changed_or_said_when_com_already_agrees(self):
        doc = Doc(active="SAC2-104")
        before = doc.ActiveLayout
        layout, note = document._on_screen_for_plot(doc)
        assert layout is before and note is None

    def test_sheet_tools_with_no_layout_named_use_the_tab_on_screen(self):
        assert sheets._pick_layout(Doc(), None).Name == "SAC2-104"


# ---------------------------------------------------------------------------
# The sheet's paper and turn (item 2)
# ---------------------------------------------------------------------------


class TestPlotTurned:
    def test_a_medium_matched_the_way_asked_is_not_turned(self):
        assert plan.plot_turned(A1_LANDSCAPE, "landscape") is False
        assert plan.plot_turned(A1_PORTRAIT, "portrait") is False

    def test_a_medium_offered_only_the_other_way_round_is_turned(self):
        assert plan.plot_turned("ISO_A1_(594.00_x_841.00_MM)", "landscape") is True
        assert plan.plot_turned(A1_LANDSCAPE, "Portrait") is True

    def test_no_orientation_a_square_or_a_nameless_sheet_is_not_turned(self):
        assert plan.plot_turned(A1_LANDSCAPE, None) is False
        assert plan.plot_turned("Square_(500.00_x_500.00_MM)", "portrait") is False
        assert plan.plot_turned("Letter", "portrait") is False


class TestTurnedPaper:
    def test_upright_is_as_kept(self):
        assert plan.turned_paper((420, 297), (5, 7.5, 6, 8), 0) == ((420.0, 297.0), (5.0, 7.5, 6.0, 8.0))

    def test_turned_90_or_270_swaps_like_the_plug_in(self):
        # The same numbers as SheetMathTests.A_sheet_plotted_at_90_degrees_has_its_sides_swapped.
        assert plan.turned_paper((297, 420), (5, 7.5, 6, 8), 90) == ((420.0, 297.0), (7.5, 5.0, 8.0, 6.0))
        assert plan.turned_paper((297, 420), (5, 7.5, 6, 8), 270)[0] == (420.0, 297.0)
        assert plan.turned_paper((297, 420), (5, 7.5, 6, 8), 180)[0] == (297.0, 420.0)

    def test_the_com_read_uses_the_same_rule(self):
        info = sheets._paper_of(Layout("X", media=A1_LANDSCAPE, rotation=1))
        assert info["paper"] == [594.0, 841.0] and info["plot_rotation_degrees"] == 90
        sheet = sheets._sheet_of(info, None, None)
        assert sheet["orientation"] == "portrait" and "turned 90 degrees" in sheet["plot_turned_note"]


def _page(layout, paper_size=None, orientation=None):
    return sheets._set_page(
        layout, None, paper_size, orientation, None, None, None, None, None, None, None, None, None
    )


class TestPageSetupOrientation:
    def test_a_paper_size_puts_a_template_turn_back_to_none(self):
        layout = Layout("SAC2-101", media="ISO_A1_(594.00_x_841.00_MM)", rotation=1)
        written = _page(layout, "A1", "landscape")
        assert layout.CanonicalMediaName == A1_LANDSCAPE
        assert layout.PlotRotation == 0 and written["plot_rotation"] == 0
        assert sheets._paper_of(layout)["paper"] == [841.0, 594.0]

    def test_orientation_alone_turns_the_same_size_round(self):
        # Ignored before ("needs a paper_size"), and the answer read the old sheet back.
        layout = Layout("SAC2-101", media=A1_PORTRAIT, rotation=1)
        written = _page(layout, orientation="landscape")
        assert "orientation_ignored" not in written
        assert layout.CanonicalMediaName == A1_LANDSCAPE and layout.PlotRotation == 0
        assert written["orientation"] == "landscape"
        assert sheets._paper_of(layout)["paper"] == [841.0, 594.0]

    def test_orientation_alone_keeps_the_variant_of_the_sheet(self):
        layout = Layout("SAC2-101", media="ISO_A1_(841.00_x_594.00_MM)")
        _page(layout, orientation="portrait")
        assert layout.CanonicalMediaName == "ISO_A1_(594.00_x_841.00_MM)"

    def test_orientation_alone_on_a_sheet_with_no_size_in_its_name_is_still_said(self):
        layout = Layout("SAC2-101", media="Letter")
        written = _page(layout, orientation="landscape")
        assert "orientation_ignored" in written and layout.CanonicalMediaName == "Letter"

    def test_a_wrong_way_round_sheet_is_warned(self):
        sheet = {"paper": [594.0, 841.0], "orientation": "portrait"}
        assert "asked for landscape but reads portrait" in sheets._orientation_check(sheet, "landscape")
        assert sheets._orientation_check(sheet, "portrait") is None
        assert sheets._orientation_check(sheet, None) is None


# ---------------------------------------------------------------------------
# dimension_run's total (item 5)
# ---------------------------------------------------------------------------


class TestRunTotal:
    def test_an_overall_alone_is_its_own_length(self):
        entries = plan_run([[-200, -200], [4200, -200]], "overall")
        assert run_total([(e["kind"], e["measurement"]) for e in entries]) == pytest.approx(4400.0)

    def test_a_chain_adds_up_and_its_overall_is_not_counted_twice(self):
        entries = plan_run([[0, 0], [3000, 0], [7500, 0]], "chain", include_overall=True)
        assert run_total([(e["kind"], e["measurement"]) for e in entries]) == pytest.approx(7500.0)

    def test_a_baseline_set_is_its_longest_dimension(self):
        entries = plan_run([[0, 0], [3000, 0], [7500, 0]], "baseline")
        assert run_total([(e["kind"], e["measurement"]) for e in entries]) == pytest.approx(7500.0)

    def test_nothing_is_nought(self):
        assert run_total([]) == 0.0
