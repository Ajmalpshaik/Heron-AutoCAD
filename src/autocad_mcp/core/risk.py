"""What each tool may do to a drawing, declared once, in code.

The Heron plug-in decides from this level which padlock a call needs. It is
never worked out from the request text: a tool's level is a property of the
tool, so nothing a caller writes can raise it or lower it.
"""

from __future__ import annotations

from enum import Enum


class Risk(str, Enum):
    READ = "read"  # looks at the drawing, changes nothing
    VIEW = "view"  # changes what is on screen or which drawing is active
    CHANGE = "change"  # changes drawing content: needs the Changes padlock
    PUBLISH = "publish"  # writes files: Changes + Publish
    ADMIN = "admin"  # escape hatches that can do anything: Changes + Admin


_LEVELS: dict[Risk, tuple[str, ...]] = {
    Risk.READ: (
        "status",
        "list_drawings",
        "list_entities",
        "get_entity",
        "get_selection",
        "find_text",
        "get_extents",
        "measure",
        "list_layers",
        "list_blocks",
        "list_styles",
        "get_variable",
        "preview",
        "check_standards",
        "extract_attributes",
        "count_blocks",
        "total_length",
        "get_dynamic_properties",
        "count_text",
        "polyline_info",
        "select_connected",
        "list_layouts",
        "get_ucs",
        "convert_points",
        "list_views",
        "solid_properties",
        "list_solid_faces_and_edges",
        "list_materials",
        "xref_tree",
        "drawing_report",
    ),
    Risk.VIEW: (
        "zoom",
        "regen",
        "switch_drawing",
        "open_drawing",
        "create_drawing",
        "set_3d_view",
    ),
    Risk.CHANGE: (
        "draw_spline",
        "draw_multiline",
        "add_wipeout",
        "attach_xref",
        "manage_xref",
        "draw_line",
        "draw_polyline",
        "draw_rectangle",
        "draw_circle",
        "draw_arc",
        "draw_ellipse",
        "draw_point",
        "add_text",
        "add_mtext",
        "add_dimension",
        "add_hatch",
        "add_label",
        "batch_labels",
        "make_block",
        "set_dynamic_properties",
        "set_attributes",
        "number_tags",
        "text_clean",
        "find_replace_text",
        "align_text",
        "add_field_label",
        "label_segment_lengths",
        "place_along",
        "place_from_csv",
        "break_at_blocks",
        "import_from_drawing",
        "manage_layouts",
        "set_ucs",
        "create_layout",
        "page_setup",
        "place_title_block",
        "add_viewport",
        "save_view",
        "drawing_setup",
        "create_styles",
        "remap_layers",
        "tidy_entities",
        "sequence",
        "make_shape",
        "dimension_run",
        "add_centre_marks",
        "add_multileader",
        "add_table",
        "add_revision_cloud",
        "add_solid",
        "extrude_profile",
        "solid_boolean",
        "check_interference",
        "slice_solid",
        # Done by the plug-in, which COM has no call for (D-40).
        "loft",
        "fillet_solid_edges",
        "chamfer_solid_edges",
        "shell_solid",
        "press_pull_faces",
        "thicken_surface",
        "super_hatch",
        "add_light",
        "create_material",
        "transform_3d",
        "apply_material",
        "draw_3d_path",
        "insert_block",
        "batch_draw",
        "move_entities",
        "copy_entities",
        "rotate_entities",
        "scale_entities",
        "mirror_entities",
        "offset_entities",
        "array_entities",
        "modify_entity",
        "delete_entities",
        "create_layer",
        "set_layer_state",
        "set_current_layer",
        "delete_layer",
    ),
    Risk.PUBLISH: (
        "save_drawing",
        "export",
        "create_hatch_pattern",
        "create_linetype",
        "publish_pdf",
    ),
    Risk.ADMIN: (
        "render",
        "send_command",
        "run_lisp",
        "set_variable",
        "purge",
        "audit",
    ),
}

RISK: dict[str, Risk] = {
    f"autocad_{name}": level for level, names in _LEVELS.items() for name in names
}


def risk_of(tool: str) -> Risk:
    """The level of a registered tool. Unknown tools raise KeyError, never a default."""
    return RISK[tool]
