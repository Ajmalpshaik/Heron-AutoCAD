"""Tests that run without AutoCAD.

These cover the pure logic — colour parsing, angle conversion, DXF filters,
name validation, the COM-error heuristic — plus the shape of the registered
tool surface. Anything needing a live drawing belongs in test_live.py.
"""

from __future__ import annotations

import math

import pytest

from autocad_mcp.acad.lisp import (
    FAILURE_MARKER,
    SUCCESS_MARKER,
    dotted,
    entmake,
    lisp_number,
    lisp_path,
    lisp_point,
    lisp_string,
    parse_output,
)
from autocad_mcp.acad.selection import (
    DXF_ENTITY_TYPE,
    DXF_LAYER,
    build_filter,
    dxf_type_for,
)
from autocad_mcp.acad.tables import validate_name
from autocad_mcp.acad.units import deg, rad, unit_name
from autocad_mcp.core.errors import (
    AutocadError,
    StaleDispatchError,
    is_dispatch_failure,
)
from autocad_mcp.core.registry import mcp, to_aci
from autocad_mcp.core.variants import group_coordinates, point_to_list
from autocad_mcp.tools import register_all
from autocad_mcp.tools.advanced import DIALOG_COMMANDS, UNDO_STACK_COMMANDS


class TestColorParsing:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("red", 1), ("GREEN", 3), ("Cyan", 4),
            ("bylayer", 256), ("byblock", 0),
            ("gray", 8), ("grey", 8),
            (1, 1), ("7", 7), (256, 256), (0, 0),
            (None, None), ("", None),
        ],
    )
    def test_accepts_names_and_numbers(self, value, expected):
        assert to_aci(value) == expected

    def test_rejects_out_of_range(self):
        with pytest.raises(AutocadError, match="between 0 and 256"):
            to_aci(999)

    def test_rejects_unknown_name_and_lists_the_valid_ones(self):
        with pytest.raises(AutocadError) as exc:
            to_aci("chartreuse")
        assert "chartreuse" in str(exc.value)
        assert "bylayer" in str(exc.value)

    def test_bool_is_not_treated_as_an_index(self):
        # True would otherwise slip through as ACI 1 (red) via int-ness.
        with pytest.raises(AutocadError):
            to_aci(True)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ('"7"', 7), ("'7'", 7), (' "7" ', 7), ('"256"', 256),
            ('"red"', 1), ("'ByLayer'", 256), ('""', None),
        ],
    )
    def test_strips_stray_quotes(self, value, expected):
        # Seen live: a client sent the number 7 as the string '"7"'.
        assert to_aci(value) == expected


# Every tool that takes a 'color' option.
COLOR_TOOLS = (
    "autocad_create_layer",
    "autocad_draw_line",
    "autocad_draw_circle",
    "autocad_draw_arc",
    "autocad_draw_polyline",
    "autocad_draw_rectangle",
    "autocad_draw_ellipse",
    "autocad_draw_point",
    "autocad_add_text",
    "autocad_add_mtext",
    "autocad_add_hatch",
    "autocad_add_label",
    "autocad_batch_labels",
    "autocad_modify_entity",
    "autocad_list_entities",
    "autocad_add_viewport",
    "autocad_add_centre_marks",
    "autocad_add_multileader",
    "autocad_add_revision_cloud",
    "autocad_add_solid",
    "autocad_check_interference",
    "autocad_draw_3d_path",
    "autocad_extrude_profile",
    "autocad_make_shape",
    "autocad_draw_spline",
    "autocad_draw_multiline",
    "autocad_add_wipeout",
    "autocad_loft",
    "autocad_thicken_surface",
    "autocad_super_hatch",
)


class TestColorArgument:
    """The colour option must reach to_aci as an int or a string.

    A 'str' only type made pydantic reject color=7 before the parser ran.
    """

    @pytest.fixture(autouse=True)
    def registered(self):
        register_all()

    def _validate_color(self, tool_name, value):
        """Validate only the 'color' field, the way the SDK would."""
        from pydantic import TypeAdapter

        tool = mcp._tool_manager.get_tool(tool_name)
        assert tool is not None, tool_name
        field = tool.fn_metadata.arg_model.model_fields["color"]
        return TypeAdapter(field.annotation).validate_python(value)

    def test_list_covers_every_tool_with_a_color_option(self):
        with_color = {
            name
            for name, tool in mcp._tool_manager._tools.items()
            if "color" in tool.parameters.get("properties", {})
        }
        assert with_color == set(COLOR_TOOLS)

    @pytest.mark.parametrize("tool_name", COLOR_TOOLS)
    @pytest.mark.parametrize("value", [7, "7", '"7"', "red", 256])
    def test_accepts_int_and_string(self, tool_name, value):
        passed = self._validate_color(tool_name, value)
        assert to_aci(passed) == to_aci(value)

    @pytest.mark.parametrize("tool_name", COLOR_TOOLS)
    def test_bool_is_still_rejected(self, tool_name):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            self._validate_color(tool_name, True)

    @pytest.mark.parametrize("tool_name", COLOR_TOOLS)
    def test_json_integer_passes_schema(self, tool_name):
        tool = mcp._tool_manager.get_tool(tool_name)
        spec = tool.parameters["properties"]["color"]
        types = {branch.get("type") for branch in spec.get("anyOf", [spec])}
        assert {"string", "integer"} <= types, spec

    def test_batch_draw_accepts_int_color(self):
        from autocad_mcp.tools.batch import _common_pairs

        pairs = _common_pairs({"type": "line", "color": 7}, "LINE")
        assert any("62" in p and "7" in p for p in pairs)


class TestAngles:
    def test_degrees_to_radians(self):
        assert rad(180) == pytest.approx(math.pi)
        assert rad(90) == pytest.approx(math.pi / 2)

    def test_radians_to_degrees(self):
        assert deg(math.pi) == pytest.approx(180.0)
        assert deg(math.pi / 2) == pytest.approx(90.0)

    def test_degrees_are_normalized_to_one_turn(self):
        assert deg(3 * math.pi) == pytest.approx(180.0)
        assert deg(-math.pi / 2) == pytest.approx(270.0)

    def test_round_trip(self):
        for angle in (0, 45, 90, 137.5, 359.9):
            assert deg(rad(angle)) == pytest.approx(angle, abs=1e-6)

    def test_none_passes_through(self):
        assert rad(None) is None and deg(None) is None


class TestUnits:
    def test_known_codes(self):
        assert unit_name(4) == "millimeters"
        assert unit_name(6) == "meters"
        assert unit_name(1) == "inches"
        assert unit_name(0) == "unitless"

    def test_unknown_code_is_reported_not_hidden(self):
        assert unit_name(99) == "code 99"
        assert unit_name(None) == "unknown"


class TestSelectionFilters:
    def test_friendly_names_map_to_dxf_names(self):
        assert dxf_type_for("polyline") == "LWPOLYLINE"
        assert dxf_type_for("block") == "INSERT"
        assert dxf_type_for("text") == "TEXT"
        assert dxf_type_for("mleader") == "MULTILEADER"

    def test_unknown_type_is_passed_through_uppercased(self):
        assert dxf_type_for("acad_proxy_entity") == "ACAD_PROXY_ENTITY"

    def test_no_criteria_means_select_everything(self):
        assert build_filter() == (None, None)

    def test_codes_and_values_line_up(self):
        codes, values = build_filter(entity_type="circle", layer="HOLES")
        assert list(codes.value) == [DXF_ENTITY_TYPE, DXF_LAYER]
        assert list(values.value) == ["CIRCLE", "HOLES"]

    def test_layer_wildcards_survive_untouched(self):
        _, values = build_filter(layer="A-*")
        assert list(values.value) == ["A-*"]


class TestCoordinateHelpers:
    def test_flat_pairs_become_points(self):
        assert group_coordinates([0, 0, 10, 0, 10, 5], 2) == [[0, 0], [10, 0], [10, 5]]

    def test_triples_for_3d(self):
        assert group_coordinates([1, 2, 3, 4, 5, 6], 3) == [[1, 2, 3], [4, 5, 6]]

    def test_trailing_partial_point_is_dropped(self):
        assert group_coordinates([0, 0, 10], 2) == [[0, 0]]

    def test_empty_input(self):
        assert group_coordinates([], 2) == []

    def test_point_to_list_survives_bad_input(self):
        assert point_to_list(None) == []
        assert point_to_list((1.0, 2.0, 3.0)) == [1.0, 2.0, 3.0]


class TestNameValidation:
    def test_accepts_normal_layer_names(self):
        assert validate_name("A-WALL") == "A-WALL"
        assert validate_name("  M-DUCT  ") == "M-DUCT"

    def test_rejects_empty(self):
        with pytest.raises(AutocadError, match="cannot be empty"):
            validate_name("   ")

    @pytest.mark.parametrize("bad", ["A/B", "A<B", 'A"B', "A|B", "A*B", "A,B"])
    def test_rejects_characters_autocad_forbids(self, bad):
        with pytest.raises(AutocadError, match="does not allow"):
            validate_name(bad)


class TestDispatchFailureHeuristic:
    """The AttributeError heuristic decides retry vs. hard failure, so it has
    to separate pywin32's COM errors from ordinary Python ones exactly."""

    @pytest.mark.parametrize(
        "message",
        [
            # pywin32 dynamic.CDispatch.__getattr__ format
            "AutoCAD.Application.Documents",
            "<unknown>.SendCommand",
            "AutoCAD.Application.ActiveDocument",
            # pywin32 dynamic.CDispatch.__setattr__ format
            "Property 'AddLine.Layer' can not be set.",
            "Property 'AddCircle.Color' cannot be set.",
        ],
    )
    def test_com_member_failures_are_retryable(self, message):
        assert is_dispatch_failure(AttributeError(message))

    @pytest.mark.parametrize(
        "message",
        [
            "'dict' object has no attribute 'foo'",
            "'NoneType' object has no attribute 'Handle'",
            "module 'autocad_mcp' has no attribute 'nope'",
        ],
    )
    def test_ordinary_python_errors_are_not_retryable(self, message):
        assert not is_dispatch_failure(AttributeError(message))

    def test_stale_dispatch_is_retryable(self):
        assert is_dispatch_failure(StaleDispatchError("pointer died"))

    def test_unrelated_exceptions_are_not(self):
        assert not is_dispatch_failure(ValueError("nope"))
        assert not is_dispatch_failure(AutocadError("nope"))


@pytest.fixture(scope="module")
async def tools():
    """Every registered tool, as the client would see them."""
    register_all()
    return await mcp.list_tools()


class TestToolSurface:
    """The tool surface is the contract with the agent, so its shape is
    asserted rather than assumed."""

    async def test_all_tools_registered(self, tools):
        assert len(tools) == 128

    async def test_every_name_is_namespaced(self, tools):
        assert all(tool.name.startswith("autocad_") for tool in tools)

    async def test_names_are_unique(self, tools):
        names = [tool.name for tool in tools]
        assert len(names) == len(set(names))

    async def test_every_tool_documents_itself(self, tools):
        for tool in tools:
            assert tool.description, f"{tool.name} has no description"
            assert tool.title, f"{tool.name} has no title"
            assert len(tool.description) > 80, f"{tool.name} description is thin"

    async def test_every_tool_declares_its_hints(self, tools):
        for tool in tools:
            assert tool.annotations is not None, f"{tool.name} has no annotations"
            assert tool.annotations.read_only_hint is not None
            assert tool.annotations.destructive_hint is not None

    async def test_destructive_tools_are_flagged(self, tools):
        by_name = {tool.name: tool for tool in tools}
        for name in (
            "autocad_delete_entities",
            "autocad_delete_layer",
            "autocad_send_command",
            "autocad_run_lisp",
        ):
            assert by_name[name].annotations.destructive_hint is True, name

    async def test_read_only_tools_are_flagged(self, tools):
        by_name = {tool.name: tool for tool in tools}
        for name in (
            "autocad_status",
            "autocad_list_entities",
            "autocad_get_entity",
            "autocad_measure",
            "autocad_find_text",
        ):
            assert by_name[name].annotations.read_only_hint is True, name

    async def test_schemas_are_flat_objects_with_described_parameters(self, tools):
        for tool in tools:
            schema = tool.input_schema
            assert schema["type"] == "object", tool.name
            for param, spec in schema.get("properties", {}).items():
                assert spec.get("description"), (
                    f"{tool.name}.{param} has no description"
                )

    async def test_drawing_tools_share_the_same_option_names(self, tools):
        """Consistent option naming is what lets an agent generalize from one
        drawing tool to the rest."""
        by_name = {tool.name: tool for tool in tools}
        for name in (
            "autocad_draw_line",
            "autocad_draw_circle",
            "autocad_draw_polyline",
            "autocad_draw_rectangle",
            "autocad_draw_arc",
        ):
            props = by_name[name].input_schema["properties"]
            assert {"layer", "color", "space"} <= set(props), name


class TestGeneratedLisp:
    """The batch tool generates AutoLISP as text, so nothing type-checks it.

    The batch's own structure (one undo group, the UNDOCTL close loop, errors
    caught and recorded, never a loaded file) is tested in test_batch_chunks.py.
    """

    def test_string_escaping(self):
        assert lisp_string('5" pipe') == '"5\\" pipe"'
        assert lisp_string(r"C:\temp") == '"C:\\\\temp"'

    def test_paths_use_forward_slashes_not_escapes(self):
        assert lisp_path(r"C:\temp\a.lsp") == '"C:/temp/a.lsp"'

    def test_numbers_are_emitted_as_reals(self):
        # entmake rejects an integer where a real is expected.
        assert "." in lisp_number(5)
        assert "." in lisp_number(0)

    def test_non_finite_coordinates_are_rejected(self):
        for bad in (float("inf"), float("nan")):
            with pytest.raises(AutocadError, match="finite"):
                lisp_number(bad)

    def test_point_requires_at_least_two_ordinates(self):
        with pytest.raises(AutocadError, match=r"\[x, y\]"):
            lisp_point([5.0])

    def test_point_defaults_z_to_zero(self):
        assert lisp_point([1.0, 2.0]) == "(list 1.0 2.0 0.0)"

    def test_entmake_records_handle_or_failure(self):
        with_handle = entmake([dotted(0, lisp_string("POINT"))], capture_handle=True)
        assert "entget (entlast)" in with_handle
        assert FAILURE_MARKER in with_handle

        without = entmake([dotted(0, lisp_string("POINT"))], capture_handle=False)
        assert "entget" not in without
        assert SUCCESS_MARKER in without


class TestBatchOutputParsing:
    """parse_output turns the LISP result file into the tool's response."""

    def test_all_succeeded(self):
        out = parse_output("1A\n1B\n1C\nDONE\n", expected=3)
        assert out["created"] == 3
        assert out["failed"] == 0
        assert out["handles"] == ["1A", "1B", "1C"]
        assert out["completed"] is True

    def test_partial_failure_is_reported_not_hidden(self):
        out = parse_output(f"1A\n{FAILURE_MARKER}\n1C\nDONE\n", expected=3)
        assert out["created"] == 2
        assert out["failed"] == 1
        assert out["handles"] == ["1A", "1C"]
        assert "hint" in out

    def test_success_markers_are_not_mistaken_for_handles(self):
        out = parse_output(f"{SUCCESS_MARKER}\n{SUCCESS_MARKER}\nDONE\n", expected=2)
        assert out["created"] == 2
        assert out["handles"] == []

    def test_lisp_error_surfaces(self):
        out = parse_output("1A\nERROR bad argument type\n", expected=5)
        assert out["error"] == "bad argument type"
        assert out["completed"] is False

    def test_missing_sentinel_means_incomplete(self):
        out = parse_output("1A\n1B\n", expected=5)
        assert out["completed"] is False
        assert "hint" in out


class TestDialogGuard:
    def test_blocking_commands_are_listed_with_an_alternative(self):
        for command, advice in DIALOG_COMMANDS.items():
            assert command.isupper(), command
            assert advice, f"{command} has no suggested alternative"

    def test_the_worst_offenders_are_covered(self):
        # Each of these opens a modal dialog that would hang the COM link.
        for command in ("PURGE", "LAYER", "PLOT", "SAVEAS", "OPEN", "QUIT"):
            assert command in DIALOG_COMMANDS

    def test_undo_stack_commands_are_exempt_from_undo_wrapping(self):
        # Running UNDO inside an open undo mark does not roll back reliably.
        for command in ("UNDO", "U", "REDO", "MREDO", "OOPS"):
            assert command in UNDO_STACK_COMMANDS

    def test_undo_commands_are_not_also_blocked_as_dialogs(self):
        assert not (UNDO_STACK_COMMANDS & set(DIALOG_COMMANDS))


def test_selection_modes_are_autocads_acselect_values():
    """AcSelect: Window 0, Crossing 1, Fence 2, Previous 3, Last 4, All 5. Previous and Last were swapped."""
    from autocad_mcp.acad import selection

    assert (selection.SELECT_WINDOW, selection.SELECT_CROSSING, selection.SELECT_PREVIOUS,
            selection.SELECT_LAST, selection.SELECT_ALL) == (0, 1, 3, 4, 5)
