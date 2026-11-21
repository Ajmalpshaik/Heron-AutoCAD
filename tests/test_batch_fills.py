"""autocad_batch_draw's mtext, solid hatch and linear dimension operations (#51, D-96), without AutoCAD.

entmake is handed DXF group codes as text, so nothing type-checks them: these
tests read the generated pairs back and check each group a drafter would get
wrong - the attachment point, a long text cut into pieces, a hatch loop's
bulges and its closing point, a dimension line placed through the text point -
and the arithmetic behind them. Whether AutoCAD accepts them is a live row
(Group AI in docs/NEEDS-CHECKING.md), NOT RUN here.
"""

from __future__ import annotations

import math
import re

import pytest

from autocad_mcp.acad import shapes
from autocad_mcp.acad.coords import Ucs
from autocad_mcp.acad.lisp import build_chunks
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools.batch import (
    BUILDERS,
    linear_dimension,
    mtext_pieces,
    to_world_ops,
)

TURNED = Ucs.build((1000, 500, 0), (0, 1, 0), (-1, 0, 0))
FLIPPED = Ucs.build((0, 0, 0), (1, 0, 0), (0, -1, 0))
RAISED = Ucs.build((0, 0, 3000), (1, 0, 0), (0, 1, 0))


def groups(pairs):
    """The pairs as (code, value text), in order."""
    out = []
    for pair in pairs:
        found = re.match(r"\(cons (-?\d+) (.*)\)$", pair, re.S)
        out.append((int(found.group(1)), found.group(2)) if found else (None, pair))
    return out


def codes(pairs):
    return [code for code, _ in groups(pairs)]


def value(pairs, code):
    return next(v for c, v in groups(pairs) if c == code)


def build(op):
    return BUILDERS[op["type"]](op, 0)


def balanced(text):
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


# ---------------------------------------------------------------------------
# mtext
# ---------------------------------------------------------------------------


class TestMtext:
    def test_the_groups_an_mtext_needs(self):
        pairs = build({"type": "mtext", "position": [10, 20], "text": "NOTE", "width": 3000, "height": 250,
                       "layer": "A-NOTE", "color": "red"})
        assert codes(pairs) == [0, 100, 8, 62, 100, 10, 40, 41, 71, 1]
        assert value(pairs, 0) == '"MTEXT"' and value(pairs, 40) == "250.0" and value(pairs, 41) == "3000.0"
        assert value(pairs, 71) == "1"  # top left, as autocad_add_mtext places it

    def test_attachment_names(self):
        for name, code in (("middle_center", "5"), ("centre", "5"), ("bottom_right", "9"), ("top_centre", "2")):
            assert value(build({"type": "mtext", "position": [0, 0], "text": "A", "attach": name}), 71) == code

    def test_no_width_means_no_wrapping(self):
        assert value(build({"type": "mtext", "position": [0, 0], "text": "A"}), 41) == "0.0"

    def test_rotation_goes_in_as_radians_and_style_by_name(self):
        pairs = build({"type": "mtext", "position": [0, 0], "text": "A", "rotation": 90, "style": "ISO"})
        assert float(value(pairs, 50)) == pytest.approx(math.pi / 2) and value(pairs, 7) == '"ISO"'

    def test_a_long_text_is_sent_in_250_character_pieces(self):
        text = "x" * 600
        assert [len(p) for p in mtext_pieces(text)] == [250, 250, 100]
        pairs = build({"type": "mtext", "position": [0, 0], "text": text})
        assert codes(pairs).count(3) == 2 and codes(pairs).index(3) < codes(pairs).index(1)
        rebuilt = "".join(v.strip('"') for c, v in groups(pairs) if c in (3, 1))
        assert rebuilt == text

    def test_a_long_mtext_still_fits_the_send_limit(self):
        chunks = build_chunks([build({"type": "mtext", "position": [0, 0], "text": "y" * 2000})], True, "C:/t.txt")
        assert all(len(c) <= 600 for c in chunks) and all(balanced(c) for c in chunks)

    def test_refusals(self):
        with pytest.raises(AutocadError, match="attach"):
            build({"type": "mtext", "position": [0, 0], "text": "A", "attach": "somewhere"})
        with pytest.raises(AutocadError, match="no text"):
            build({"type": "mtext", "position": [0, 0], "text": ""})
        with pytest.raises(AutocadError, match="height"):
            build({"type": "mtext", "position": [0, 0], "text": "A", "height": 0})


# ---------------------------------------------------------------------------
# hatch
# ---------------------------------------------------------------------------


class TestHatch:
    def test_a_solid_triangle(self):
        pairs = build({"type": "hatch", "points": [[0, 0], [10, 0], [5, 8]], "color": 1})
        assert value(pairs, 0) == '"HATCH"' and value(pairs, 2) == '"SOLID"'
        assert value(pairs, 70) == "1" and value(pairs, 71) == "0" and value(pairs, 91) == "1"
        # The loop: polyline, external; no arcs so no bulges; closed; three corners.
        assert (value(pairs, 92), value(pairs, 72), value(pairs, 73), value(pairs, 93)) == ("3", "0", "1", "3")
        assert 42 not in codes(pairs)
        assert codes(pairs)[-4:] == [75, 76, 98, 10]

    def test_the_order_entmake_reads_a_hatch_in(self):
        sequence = codes(build({"type": "hatch", "points": [[0, 0], [10, 0], [5, 8]]}))
        head = [0, 100, 100, 10, 210, 2, 70, 71, 91, 92, 72, 73, 93, 10, 10, 10, 97, 75, 76, 98, 10]
        assert sequence == head

    def test_a_repeated_closing_point_is_dropped(self):
        pairs = build({"type": "hatch", "points": [[0, 0], [10, 0], [5, 8], [0, 0]]})
        assert value(pairs, 93) == "3"

    def test_arcs_give_every_vertex_a_bulge(self):
        # A filled half-round: two corners joined by a straight and a half circle.
        pairs = build({"type": "hatch", "points": [[0, 0], [10, 0]], "bulges": [0, 1]})
        assert value(pairs, 72) == "1"
        loop = [c for c in codes(pairs)[codes(pairs).index(93):] if c in (10, 42)][:4]
        assert loop == [10, 42, 10, 42]

    def test_holes_are_their_own_loops(self):
        pairs = build({"type": "hatch", "points": [[0, 0], [100, 0], [100, 100], [0, 100]],
                       "holes": [[[40, 40], [60, 40], [60, 60]], {"points": [[10, 10], [20, 10]], "bulges": [1, 1]}]})
        assert value(pairs, 91) == "3"
        assert [v for c, v in groups(pairs) if c == 92] == ["3", "2", "2"]
        assert [v for c, v in groups(pairs) if c == 97] == ["0", "0", "0"]

    def test_a_raised_outline_keeps_its_height(self):
        moved = to_world_ops([{"type": "hatch", "points": [[0, 0], [10, 0], [5, 8]]}], RAISED)[0]
        assert moved["elevation"] == 3000.0
        assert value(build(moved), 10) == "(list 0.0 0.0 3000.0)"

    def test_a_pattern_is_refused_naming_the_hatch_tool(self):
        with pytest.raises(AutocadError, match="autocad_add_hatch"):
            build({"type": "hatch", "points": [[0, 0], [10, 0], [5, 8]], "pattern": "ANSI31"})

    def test_too_few_corners_are_refused(self):
        with pytest.raises(AutocadError, match="distinct corners"):
            build({"type": "hatch", "points": [[0, 0], [10, 0]]})
        with pytest.raises(AutocadError, match="bulges"):
            build({"type": "hatch", "points": [[0, 0], [10, 0], [5, 5]], "bulges": [0, 0, 0, 1]})

    def test_the_whole_fill_is_one_balanced_expression(self):
        chunks = build_chunks([build({"type": "hatch", "points": [[i, i * i] for i in range(60)]})], True, "C:/t.txt")
        assert all(balanced(c) for c in chunks) and all(len(c) <= 600 for c in chunks)


# ---------------------------------------------------------------------------
# dimension
# ---------------------------------------------------------------------------


class TestLinearDimensionArithmetic:
    def test_an_aligned_line_is_offset_through_the_text_point(self):
        end, text = linear_dimension((0, 0), (100, 0), (50, -20))
        assert end == pytest.approx((100.0, -20.0)) and text == (50.0, -20.0)

    def test_an_aligned_dimension_on_a_slope(self):
        end, _ = linear_dimension((0, 0), (30, 40), (-40, 30))
        # One unit of offset normal to the 3-4-5 line, 50 long.
        assert end == pytest.approx((-10.0, 70.0))

    def test_a_horizontal_line_runs_level_through_the_text_point(self):
        end, _ = linear_dimension((0, 0), (100, 30), (50, -20), angle=0)
        assert end == pytest.approx((100.0, -20.0))

    def test_a_vertical_line(self):
        end, _ = linear_dimension((0, 0), (30, 100), (-20, 50), angle=90)
        assert end == pytest.approx((-20.0, 100.0))

    def test_nothing_to_measure_is_refused(self):
        with pytest.raises(ValueError, match="one place"):
            linear_dimension((5, 5), (5, 5), (0, 0))
        with pytest.raises(ValueError, match="measures nothing"):
            linear_dimension((0, 0), (0, 100), (0, 0), angle=0)


class TestDimension:
    def test_an_aligned_dimension(self):
        pairs = build({"type": "dimension", "point1": [0, 0], "point2": [100, 0], "text_position": [50, -20]})
        assert codes(pairs)[:6] == [0, 100, 100, 10, 11, 70]
        assert value(pairs, 10) == "(list 100.0 -20.0 0.0)" and value(pairs, 11) == "(list 50.0 -20.0 0.0)"
        assert value(pairs, 70) == str(1 | 32 | 128)
        assert value(pairs, 3) == '(getvar "DIMSTYLE")'
        assert value(pairs, 13) == "(list 0.0 0.0 0.0)" and value(pairs, 14) == "(list 100.0 0.0 0.0)"
        assert 50 not in codes(pairs)

    def test_without_a_text_point_it_sits_on_the_points_and_is_not_user_placed(self):
        pairs = build({"type": "dimension", "point1": [0, 0], "point2": [100, 0]})
        assert value(pairs, 70) == str(1 | 32) and value(pairs, 11) == "(list 50.0 0.0 0.0)"

    def test_horizontal_is_a_rotated_dimension_at_0(self):
        pairs = build({"type": "dimension", "dimension_type": "horizontal", "point1": [0, 0], "point2": [100, 30],
                       "text_position": [50, -20], "style": "ISO-25", "text_override": "<> TYP"})
        assert value(pairs, 70) == str(0 | 32 | 128) and float(value(pairs, 50)) == 0.0
        assert value(pairs, 3) == '"ISO-25"' and value(pairs, 1) == '"<> TYP"'
        subclasses = [v for c, v in groups(pairs) if c == 100]
        assert subclasses[-2:] == ['"AcDbAlignedDimension"', '"AcDbRotatedDimension"']

    def test_the_drawing_s_dimscale_rides_along_as_an_override(self):
        pairs = build({"type": "dimension", "point1": [0, 0], "point2": [100, 0]})
        assert pairs[-1].startswith('(list -3 (list "ACAD"') and '(cons 1070 40)' in pairs[-1]
        assert '(getvar "DIMSCALE")' in pairs[-1] and balanced(pairs[-1])

    def test_refusals(self):
        with pytest.raises(AutocadError, match="autocad_add_dimension"):
            build({"type": "dimension", "dimension_type": "radial", "point1": [0, 0], "point2": [5, 0]})
        with pytest.raises(AutocadError, match="angle"):
            build({"type": "dimension", "dimension_type": "rotated", "point1": [0, 0], "point2": [5, 0]})
        with pytest.raises(AutocadError, match="one place"):
            build({"type": "dimension", "point1": [1, 1], "point2": [1, 1]})


# ---------------------------------------------------------------------------
# coords='ucs' on the new operations, and the flipped UCS
# ---------------------------------------------------------------------------


class TestUcs:
    def test_mtext_moves_and_turns(self):
        moved = to_world_ops([{"type": "mtext", "position": [0, 100], "text": "A", "rotation": 10}], TURNED)[0]
        assert moved["position"] == pytest.approx([900.0, 500.0, 0.0]) and moved["rotation"] == pytest.approx(100.0)

    def test_a_hatch_and_its_holes_move(self):
        moved = to_world_ops([{"type": "hatch", "points": [[0, 0], [10, 0], [5, 8]],
                               "holes": [[[1, 1], [2, 1], [1, 2]], {"points": [[3, 3], [4, 3]], "bulges": [1, 1]}]}],
                             TURNED)[0]
        assert moved["points"][1] == pytest.approx([1000.0, 510.0, 0.0])
        assert moved["holes"][0][0] == pytest.approx([999.0, 501.0, 0.0])
        assert moved["holes"][1]["points"][0] == pytest.approx([997.0, 503.0, 0.0])
        assert moved["holes"][1]["bulges"] == [1, 1]

    def test_a_horizontal_dimension_in_a_turned_ucs_measures_along_its_x(self):
        moved = to_world_ops([{"type": "dimension", "dimension_type": "horizontal", "point1": [0, 0],
                               "point2": [100, 0], "text_position": [50, -20]}], TURNED)[0]
        assert moved["dimension_type"] == "rotated" and moved["angle"] == 90.0
        pairs = build(moved)
        assert value(pairs, 13) == "(list 1000.0 500.0 0.0)"
        assert float(value(pairs, 50)) == pytest.approx(math.pi / 2)
        # The line runs through the converted text point, square to UCS X.
        line_end = [float(n) for n in value(pairs, 10)[6:-1].split()]
        assert line_end == pytest.approx([1020.0, 600.0, 0.0])

    def test_an_aligned_dimension_stays_aligned(self):
        moved = to_world_ops([{"type": "dimension", "point1": [0, 0], "point2": [100, 0]}], TURNED)[0]
        assert moved.get("dimension_type", "aligned") == "aligned" and "angle" not in moved

    def test_a_polyline_in_a_raised_ucs_gets_group_38(self):
        moved = to_world_ops([{"type": "polyline", "points": [[0, 0], [10, 0]]}], RAISED)[0]
        assert value(build(moved), 38) == "3000.0"

    def test_on_a_flipped_ucs_an_arc_swaps_its_ends_and_bulges_turn_over(self):
        arc, poly, fill = to_world_ops([
            {"type": "arc", "center": [0, 0], "radius": 5, "start_angle": 0, "end_angle": 90},
            {"type": "polyline", "points": [[0, 0], [10, 0]], "bulges": [0.5]},
            {"type": "hatch", "points": [[0, 0], [10, 0]], "bulges": [1, 1]},
        ], FLIPPED)
        assert (arc["start_angle"], arc["end_angle"]) == pytest.approx((270.0, 0.0))
        assert poly["bulges"] == [-0.5] and fill["bulges"] == [-1.0, -1.0]

    @pytest.mark.parametrize("op", [
        {"type": "text", "position": [0, 0], "text": "A"},
        {"type": "mtext", "position": [0, 0], "text": "A"},
        {"type": "dimension", "point1": [0, 0], "point2": [1, 0]},
    ])
    def test_on_a_flipped_ucs_text_and_dimensions_are_refused_by_number(self, op):
        with pytest.raises(AutocadError, match=r"Operation 1 .*flipped"):
            to_world_ops([{"type": "point", "position": [0, 0]}, op], FLIPPED)


# ---------------------------------------------------------------------------
# filled symbols
# ---------------------------------------------------------------------------


def kinds(ops):
    return [op["type"] for op in ops]


class TestFilledShapes:
    def test_section_mark_heads_can_be_filled(self):
        plain = shapes.build("section_mark", {"length": 1000})
        filled = shapes.build("section_mark", {"length": 1000, "filled": True})
        assert "hatch" not in kinds(plain)
        assert kinds(filled).count("hatch") == 2 and len(filled) == len(plain) + 2
        # Each fill is exactly its arrowhead's outline.
        heads = [op for op in filled if op["type"] == "polyline" and op.get("closed")]
        fills = [op for op in filled if op["type"] == "hatch"]
        assert [h["points"] for h in heads] == [f["points"] for f in fills]

    def test_north_arrow_fills_its_right_half(self):
        ops = shapes.build("north_arrow", {"size": 100, "filled": True})
        (fill,) = [op for op in ops if op["type"] == "hatch"]
        assert fill["points"] == [[0.0, 0.0], [18.0, 30.0], [0.0, 100.0]]
        assert "hatch" not in kinds(shapes.build("north_arrow", {"size": 100}))

    def test_a_scale_bar_fills_every_other_division_instead_of_crossing_it(self):
        ops = shapes.build("scale_bar", {"scale": "1:50", "length": 100, "divisions": 5, "filled": True})
        assert kinds(ops).count("hatch") == 3 and kinds(ops).count("line") == 0
        plain = shapes.build("scale_bar", {"scale": "1:50", "length": 100, "divisions": 5})
        assert kinds(plain).count("line") == 3 and "hatch" not in kinds(plain)

    def test_a_level_mark_can_be_solid(self):
        ops = shapes.build("level_mark", {"level": "+3.000", "filled": True})
        assert kinds(ops).count("hatch") == 1

    def test_every_fill_a_shape_makes_is_a_batch_the_engine_can_build(self):
        for name, settings in (("section_mark", {"length": 1000}), ("north_arrow", {"size": 100}),
                               ("scale_bar", {"scale": "1:50", "length": 100}), ("level_mark", {"level": "0"})):
            for op in shapes.build(name, {**settings, "filled": True}):
                BUILDERS[op["type"]](op, 0)


class TestReviewFixes:
    def test_text_and_mtext_with_no_rotation_still_turn_with_the_ucs(self):
        turned = Ucs.from_rotation((0, 0), 30)
        text, mtext = to_world_ops([{"type": "text", "position": [0, 0], "text": "A"},
                                    {"type": "mtext", "position": [0, 0], "text": "A"}], turned)
        assert text["rotation"] == pytest.approx(30.0) and mtext["rotation"] == pytest.approx(30.0)
        assert float(value(build(mtext), 50)) == pytest.approx(math.radians(30))

    def test_a_shape_s_label_turns_with_its_lines(self):
        ops = to_world_ops(shapes.build("north_arrow", {"size": 100}), Ucs.from_rotation((0, 0), 30))
        (label,) = [op for op in ops if op["type"] == "text"]
        assert label["rotation"] == pytest.approx(30.0)

    def test_a_dimension_in_a_turned_ucs_says_which_way_is_horizontal(self):
        moved = to_world_ops([{"type": "dimension", "point1": [0, 0], "point2": [100, 0]}],
                             Ucs.from_rotation((0, 0), 30))[0]
        assert float(value(build(moved), 51)) == pytest.approx(-math.radians(30))
        world = build({"type": "dimension", "point1": [0, 0], "point2": [100, 0]})
        assert 51 not in codes(world)
