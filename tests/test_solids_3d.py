"""The 3D additions: the arithmetic, the guards, and the padlocks.

Only the pure parts can be checked here. Everything that touches COM -
SliceSolid, CheckInterference, Rotate3D, Mirror3D, AddEllipticalCylinder,
AddExtrudedSolidAlongPath, the Material property - is **NOT RUN**: see
docs/NEEDS-CHECKING group F.
"""

from __future__ import annotations

import math

import pytest

from autocad_mcp.core.errors import AutocadError
from autocad_mcp.core.risk import RISK, Risk
from autocad_mcp.tools.materials import match_name
from autocad_mcp.tools.solids import plane_from


def normal_of(p1, p2, p3) -> tuple[float, float, float]:
    """The plane's own normal, worked out back from its three points."""
    ax, ay, az = (p2[i] - p1[i] for i in range(3))
    bx, by, bz = (p3[i] - p1[i] for i in range(3))
    nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    assert length > 1e-9, "the three points are in a line, so they define no plane"
    return (nx / length, ny / length, nz / length)


class TestTheCuttingPlane:
    def test_horizontal_cuts_at_the_level_given(self):
        p1, p2, p3 = plane_from("horizontal", [1000, 2000, 1500], None)
        assert p1[2] == p2[2] == p3[2] == 1500
        assert normal_of(p1, p2, p3) == pytest.approx((0.0, 0.0, 1.0))

    def test_a_point_without_z_sits_on_zero(self):
        p1, _, _ = plane_from("horizontal", [1000, 2000], None)
        assert p1 == (1000.0, 2000.0, 0.0)

    @pytest.mark.parametrize("kind,want", [
        ("horizontal", (0.0, 0.0, 1.0)),
        ("vertical_x", (0.0, -1.0, 0.0)),
        ("vertical_y", (1.0, 0.0, 0.0)),
    ])
    def test_each_named_plane_faces_the_right_way(self, kind, want):
        p1, p2, p3 = plane_from(kind, [0, 0, 0], None)
        got = normal_of(p1, p2, p3)
        assert [abs(v) for v in got] == pytest.approx([abs(v) for v in want])

    @pytest.mark.parametrize("kind", ["horizontal", "vertical_x", "vertical_y"])
    def test_every_plane_passes_through_the_point(self, kind):
        point = [1234.5, -678.9, 42.0]
        p1, p2, p3 = plane_from(kind, point, None)
        assert p1 == pytest.approx(tuple(point))

    @pytest.mark.parametrize("normal", [
        [0, 0, 1], [1, 0, 0], [0, 1, 0], [1, 1, 0], [1, 1, 1], [0, 0, -1], [-3, 4, 12],
    ])
    def test_a_given_normal_comes_back_as_that_normal(self, normal):
        """The whole point of plane='normal': the plane must face where you said."""
        p1, p2, p3 = plane_from("normal", [100, 200, 300], normal)
        got = normal_of(p1, p2, p3)
        length = math.sqrt(sum(v * v for v in normal))
        wanted = tuple(v / length for v in normal)
        # Either orientation describes the same plane.
        assert (got == pytest.approx(wanted, abs=1e-9)
                or got == pytest.approx(tuple(-v for v in wanted), abs=1e-9))

    @pytest.mark.parametrize("normal", [[0, 0, 1], [1, 1, 1], [-3, 4, 12]])
    def test_the_three_points_are_never_in_a_line(self, normal):
        normal_of(*plane_from("normal", [0, 0, 0], normal))

    def test_a_normal_plane_passes_through_its_point(self):
        p1, _, _ = plane_from("normal", [50, 60, 70], [1, 2, 3])
        assert p1 == pytest.approx((50.0, 60.0, 70.0))

    def test_a_vertical_normal_still_works(self):
        """z was the awkward case: the helper axis has to dodge the normal."""
        normal_of(*plane_from("normal", [0, 0, 0], [0, 0, 1]))
        normal_of(*plane_from("normal", [0, 0, 0], [0, 0, -1]))

    def test_a_missing_normal_is_refused_in_plain_words(self):
        with pytest.raises(AutocadError, match="needs 'normal'"):
            plane_from("normal", [0, 0, 0], None)

    def test_a_zero_normal_is_refused(self):
        with pytest.raises(AutocadError, match="cannot be all zeros"):
            plane_from("normal", [0, 0, 0], [0, 0, 0])

    def test_an_unknown_plane_lists_the_real_ones(self):
        with pytest.raises(AutocadError) as caught:
            plane_from("diagonal", [0, 0, 0], None)
        for kind in ("horizontal", "vertical_x", "vertical_y", "normal"):
            assert kind in str(caught.value)


class TestMaterialNames:
    def test_it_matches_whatever_case_was_typed(self):
        assert match_name("steel", ["Steel", "Concrete"]) == "Steel"
        assert match_name("  CONCRETE ", ["Steel", "Concrete"]) == "Concrete"

    def test_a_name_that_is_not_there_is_not_invented(self):
        assert match_name("Titanium", ["Steel", "Concrete"]) is None

    def test_nothing_matches_an_empty_drawing(self):
        assert match_name("Steel", []) is None


class TestThePadlocks:
    """A level is a property of the tool. These are the ones that could be wrong."""

    def test_a_clash_check_needs_changes_because_it_writes(self):
        """CheckInterference builds the overlap as a real solid to measure it."""
        assert RISK["autocad_check_interference"] == Risk.CHANGE

    def test_listing_materials_only_reads(self):
        assert RISK["autocad_list_materials"] == Risk.READ

    def test_applying_a_material_changes_the_drawing(self):
        assert RISK["autocad_apply_material"] == Risk.CHANGE

    def test_slicing_and_transforming_change_the_drawing(self):
        assert RISK["autocad_slice_solid"] == Risk.CHANGE
        assert RISK["autocad_transform_3d"] == Risk.CHANGE

    def test_there_is_no_render_tool(self):
        """D-87, #158: -render waits on prompts and can stall AutoCAD; the modeller presses Render."""
        assert not any("render" in name and "exposure" not in name for name in RISK), sorted(RISK)

    def test_a_sequence_cannot_reach_an_admin_tool(self):
        """autocad_sequence tops out at Changes, so Admin stays out of reach."""
        from autocad_mcp.tools.sequence import ALLOWED

        assert RISK["autocad_run_lisp"] not in ALLOWED
