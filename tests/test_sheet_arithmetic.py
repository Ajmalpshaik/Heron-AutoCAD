"""Sheets by the plug-in (#64-#67, D-90, D-91): the arithmetic, no AutoCAD.

A layout's paper from the numbers AutoCAD gives, a viewport's clip outline,
a drawing list checked and planned before anything is made, the title block
values per sheet, and the list of drawings for one PDF.
"""

from __future__ import annotations

import pytest

from autocad_mcp.acad import publish_files
from autocad_mcp.acad import sheets as plan

# ---------------------------------------------------------------------------
# Paper and frame
# ---------------------------------------------------------------------------


class TestPaper:
    def test_the_printable_area_is_the_sheet_less_both_margins(self):
        info = plan.paper_info((420.0, 297.0), (5.0, 7.5, 5.0, 7.5), "ISO_A3_(420.00_x_297.00_MM)", "DWG To PDF.pc3", 0)
        assert info["paper"] == [420.0, 297.0]
        assert info["printable"] == [0.0, 0.0, 410.0, 282.0]
        assert info["margins"] == [5.0, 7.5, 5.0, 7.5]
        assert info["media"].startswith("ISO_A3") and info["plotter"] == "DWG To PDF.pc3"

    def test_a_full_bleed_sheet_prints_to_its_edge(self):
        info = plan.paper_info((841.0, 594.0))
        assert info["printable"] == [0.0, 0.0, 841.0, 594.0]
        assert info["plot_rotation_degrees"] == 0

    def test_an_odd_rotation_reads_as_none(self):
        assert plan.paper_info((420, 297), None, rotation_degrees=45)["plot_rotation_degrees"] == 0
        assert plan.paper_info((420, 297), None, rotation_degrees=90)["plot_rotation_degrees"] == 90

    def test_a_sheet_with_no_size_is_refused(self):
        with pytest.raises(ValueError):
            plan.paper_info((0.0, 297.0))

    def test_the_paper_anchor_starts_at_the_sheet_corner(self):
        info = plan.paper_info((420.0, 297.0), (5.0, 7.5, 5.0, 7.5))
        assert plan.area_box(info, "printable") == (0.0, 0.0, 410.0, 282.0)
        assert plan.area_box(info, "paper") == (-5.0, -7.5, 415.0, 289.5)

    def test_the_frame_sits_in_the_area_it_is_worked_out_for(self):
        area = (-5.0, -7.5, 415.0, 289.5)  # an A3 measured from its edge
        assert plan.frame_in(area) == (15.0, 2.5, 405.0, 279.5)
        # The same frame the tools worked out by hand before (frame + the area's corner).
        x1, y1, x2, y2 = plan.frame(420.0, 297.0)
        assert plan.frame_in((0.0, 0.0, 420.0, 297.0)) == (x1, y1, x2, y2)


# ---------------------------------------------------------------------------
# The viewport's own arithmetic (D-90): the window it shows at its scale
# ---------------------------------------------------------------------------


class TestViewportWindow:
    def test_an_a1_frame_at_1_to_100_shows_its_size_times_100(self):
        info = plan.paper_info((841.0, 594.0))
        space = plan.reserve(plan.frame_in(plan.area_box(info)), "right", 180.0)
        width, height = plan.size_of(space)
        assert (width, height) == (631.0, 574.0)
        window = plan.model_window(plan.centre_of(space), width, height, "1:100")
        assert plan.size_of(window) == pytest.approx((63100.0, 57400.0))

    def test_a_clip_box_is_what_the_window_is_worked_out_from(self):
        outline = plan.clip_outline([[50, 50], [250, 50], [250, 130], [130, 130], [130, 200], [50, 200]])
        width, height = plan.size_of(tuple(outline["box"]))
        window = plan.model_window((10000.0, 5000.0), width, height, "1:50")
        assert window == pytest.approx((5000.0, 1250.0, 15000.0, 8750.0))


# ---------------------------------------------------------------------------
# Clip outlines (#65)
# ---------------------------------------------------------------------------


class TestClipOutline:
    def test_an_l_shape_keeps_its_corners_and_the_box_round_it(self):
        out = plan.clip_outline([[0, 0], [200, 0], [200, 80], [80, 80], [80, 150], [0, 150]])
        assert len(out["points"]) == 6
        assert out["box"] == [0, 0, 200, 150]
        assert out["area"] == pytest.approx(200 * 80 + 80 * 70)

    def test_a_closing_corner_and_a_corner_twice_are_dropped(self):
        out = plan.clip_outline([[0, 0], [100, 0], [100, 0], [100, 50], [0, 50], [0, 0]])
        assert out["points"] == [[0, 0], [100, 0], [100, 50], [0, 50]]

    def test_clockwise_or_anticlockwise_the_area_is_the_same(self):
        square = [[0, 0], [10, 0], [10, 10], [0, 10]]
        assert plan.clip_outline(square)["area"] == plan.clip_outline(square[::-1])["area"] == 100

    @pytest.mark.parametrize(
        ("corners", "words"),
        [
            ([[0, 0], [10, 0]], "three"),
            ([[0, 0], [10, 0], [0, 0]], "three"),
            ([[0, 0], [10, 10], [20, 20]], "no area"),
            ([[0, 0], [10, 10], [10, 0], [0, 10]], "crosses itself"),
            ([[0, 0], [100, 0], [100, 100], [50, -20], [0, 100]], "crosses itself"),
            ([[0, 0], [1]], r"not \[x, y\]"),
            ([[0, 0], [10, float("nan")], [5, 5]], "not a number"),
        ],
    )
    def test_what_is_not_a_clip_shape_is_refused(self, corners, words):
        with pytest.raises(ValueError, match=words):
            plan.clip_outline(corners)

    def test_too_many_corners_is_refused(self):
        many = [[float(i), float(i % 2)] for i in range(plan.MOST_CLIP_CORNERS + 2)]
        with pytest.raises(ValueError, match="at most"):
            plan.clip_outline(many)

    def test_a_side_that_runs_back_along_another_crosses(self):
        with pytest.raises(ValueError, match="crosses itself"):
            plan.clip_outline([[0, 0], [100, 0], [100, 50], [50, 0], [0, 50]])


# ---------------------------------------------------------------------------
# A drawing list (#66)
# ---------------------------------------------------------------------------


ROWS = [
    {"number": "M-101", "title": "GROUND FLOOR HVAC", "scale": "1:100", "view": "gf-hvac"},
    {"number": "M-102", "title": "FIRST FLOOR HVAC", "view": "FF-HVAC"},
    {"number": "M-001", "title": "COVER"},
    {"number": "M-501", "title": "PLANT ROOM", "scale": "1:20", "corner1": [0, 0], "corner2": [8000, 6000]},
]


class TestSheetSetPlan:
    def test_each_row_becomes_one_sheet_plan(self):
        plans = plan.plan_sheet_set(ROWS, ["Model", "Layout1"], ["GF-HVAC", "FF-HVAC"])
        assert [p["number"] for p in plans] == ["M-101", "M-102", "M-001", "M-501"]
        first = plans[0]
        assert first["scale"] == "1:100" and first["scale_ratio"] == pytest.approx(0.01)
        assert first["aim"] == "view" and first["view"] == "GF-HVAC"  # the drawing's own spelling
        assert plans[1]["scale"] is None and plans[1]["aim"] == "view"
        assert plans[2]["aim"] is None  # a cover sheet: no viewport
        assert plans[3]["aim"] == "corner1" and plans[3]["scale"] == "1:20"

    def test_every_problem_is_said_at_once(self):
        rows = [
            {"number": "M-101", "scale": "1:100", "view": "NOWHERE"},
            {"number": "m-101", "scale": "half", "view": "GF"},
            {"number": "Layout1"},
            {"number": "E/101"},
            {"title": "no number"},
            {"number": "M-103", "view": "GF", "corner1": [0, 0], "corner2": [1, 1]},
            {"number": "M-104", "corner1": [0, 0]},
            {"number": "M-105", "centre": [0, 0]},
            {"number": "model"},
            {"number": "M-106", "scale": 50},
        ]
        with pytest.raises(ValueError) as caught:
            plan.plan_sheet_set(rows, ["Layout1"], ["GF"])
        text = str(caught.value)
        for words in (
            "no saved view called 'NOWHERE'",
            "'m-101' is also row 1",
            "not a scale",
            "already has a layout called 'Layout1'",
            "cannot be a layout name",
            "row 5 has no sheet number",
            "not view and corner1",
            "corner1 needs corner2",
            "a centre needs a scale",
            "'Model' is model space",
            "could mean 1:50 or 50:1",
            "nothing was made",
        ):
            assert words in text, words

    def test_views_are_not_checked_when_the_drawing_was_not_asked(self):
        plans = plan.plan_sheet_set([{"number": "A-1", "view": "ANY"}], [], None)
        assert plans[0]["view"] == "ANY"

    def test_an_empty_or_huge_list_is_refused(self):
        with pytest.raises(ValueError, match="empty"):
            plan.plan_sheet_set([], [])
        with pytest.raises(ValueError, match="at most"):
            plan.plan_sheet_set([{"number": f"S-{i}"} for i in range(plan.MOST_SHEETS + 1)], [])

    def test_attributes_must_be_tag_value_pairs(self):
        with pytest.raises(ValueError, match="tag: value"):
            plan.plan_sheet_set([{"number": "A-1", "attributes": ["REV", "P01"]}], [])

    def test_the_title_block_gets_common_values_then_the_rows_own(self):
        row = plan.plan_sheet_set(
            [{"number": "M-102", "title": "FIRST FLOOR", "view": "FF", "attributes": {"rev": "P02"}}], []
        )[0]
        values = plan.title_block_values(row, {"PROJECT": "VILLA", "REV": "P01"}, "DWG_NO", "TITLE", "SCALE", "1:75")
        assert values == {"PROJECT": "VILLA", "REV": "P02", "DWG_NO": "M-102", "TITLE": "FIRST FLOOR", "SCALE": "1:75"}

    def test_a_tag_left_out_is_not_written(self):
        row = plan.plan_sheet_set([{"number": "M-001"}], [])[0]
        assert plan.title_block_values(row, None, "DWG_NO", None, "SCALE") == {"DWG_NO": "M-001"}


# ---------------------------------------------------------------------------
# The drawings for one PDF (#67)
# ---------------------------------------------------------------------------


def _dwg(folder, name):
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"AC1032")
    return path


class TestPdfDrawings:
    def test_a_folder_is_read_the_way_a_drafter_numbers_sheets(self, tmp_path):
        for name in ("M-10.dwg", "M-2.dwg", "M-1.DWG", "notes.txt", "M-3.bak"):
            _dwg(tmp_path, name)
        found = publish_files.pdf_drawings(folder=str(tmp_path))
        assert [p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for p in found] == ["M-1.DWG", "M-2.dwg", "M-10.dwg"]

    def test_sub_folders_only_when_asked(self, tmp_path):
        _dwg(tmp_path, "A-1.dwg")
        _dwg(tmp_path, "level 2/A-2.dwg")
        assert len(publish_files.pdf_drawings(folder=str(tmp_path))) == 1
        assert len(publish_files.pdf_drawings(folder=str(tmp_path), recursive=True)) == 2

    def test_a_folder_without_drawings_or_not_there_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="no .dwg"):
            publish_files.pdf_drawings(folder=str(tmp_path))
        with pytest.raises(ValueError, match="does not exist"):
            publish_files.pdf_drawings(folder=str(tmp_path / "nowhere"))

    def test_a_list_keeps_its_order_and_each_drawing_once(self, tmp_path):
        b, a = _dwg(tmp_path, "B.dwg"), _dwg(tmp_path, "A.dwg")
        found = publish_files.pdf_drawings(drawings=[str(b), f'"{a}"', str(b), ""])
        assert found == [str(b), str(a)]

    def test_a_missing_file_or_not_a_drawing_is_named(self, tmp_path):
        good = _dwg(tmp_path, "A.dwg")
        with pytest.raises(ValueError) as caught:
            publish_files.pdf_drawings(drawings=[str(good), str(tmp_path / "gone.dwg"), str(tmp_path / "set.pdf")])
        assert "gone.dwg' is not there" in str(caught.value)
        assert "set.pdf' is not a .dwg" in str(caught.value)

    def test_folder_and_list_together_or_neither_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="not both"):
            publish_files.pdf_drawings(folder=str(tmp_path), drawings=["x.dwg"])
        with pytest.raises(ValueError, match="give a folder"):
            publish_files.pdf_drawings()

    def test_too_many_drawings_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(publish_files, "MOST_DRAWINGS", 2)
        for name in ("A.dwg", "B.dwg", "C.dwg"):
            _dwg(tmp_path, name)
        with pytest.raises(ValueError, match="at most 2"):
            publish_files.pdf_drawings(folder=str(tmp_path))

    def test_the_unsaved_ones_are_found_among_the_open_drawings(self, tmp_path):
        a, b = str(tmp_path / "A.dwg"), str(tmp_path / "B.dwg")
        open_ones = [(a.upper() if a[1:2] == ":" else a, False), (b, True), ("", False)]
        assert publish_files.unsaved_among([a, b], open_ones) == [a]

    def test_numbers_sort_as_numbers(self):
        names = ["E-100", "E-20", "e-3", "E-3A"]
        assert sorted(names, key=publish_files.natural_key) == ["e-3", "E-3A", "E-20", "E-100"]
