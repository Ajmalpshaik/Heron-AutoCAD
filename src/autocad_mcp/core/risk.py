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
        "use_autocad",
        "checklist",
        "project_notes",
        "activity",
        "companion",
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
        "list_lights",
        "xref_tree",
        "drawing_report",
        "why",
        "gaps",
        "read_file",
        "list_groups",
        "list_annotation_scales",
        # Hyperlinks and the geographic location, read (D-111).
        "list_hyperlinks",
        "get_geo_location",
    ),
    Risk.VIEW: (
        "check_folder",
        "zoom",
        "show",
        "regen",
        "switch_drawing",
        "open_drawing",
        "create_drawing",
        "set_3d_view",
        # Tiled viewports on the Model tab: the screen, not the drawing (D-111).
        "tiled_viewports",
    ),
    Risk.CHANGE: (
        "undo_last",
        "saved_command",
        "draw_spline",
        "draw_multiline",
        "edit_spline",
        "add_wipeout",
        "attach_xref",
        "manage_xref",
        # Cleaning up and referencing (#104, #112, #118; D-84).
        "attach_underlay",
        "clip_reference",
        "overkill",
        "trace_boundary",
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
        # Blocks, attributes and tables (D-82, D-83); ATTSYNC and the Excel link are done by the plug-in.
        "sync_attributes",
        "table_from_excel",
        "update_table_links",
        "set_table_cells",
        "copy_from_drawing",
        "set_dynamic_properties",
        "set_attributes",
        "apply_attribute_sheet",
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
        "sheet_set",
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
        # Pyramid, polysolid and the rest of SOLIDEDIT, by the plug-in (D-112, D-113).
        "add_pyramid",
        "add_polysolid",
        "edit_solid_faces",
        "imprint_solid",
        "separate_solid",
        # Done by the plug-in, which COM has no call for (D-40).
        "loft",
        "fillet_solid_edges",
        "chamfer_solid_edges",
        "shell_solid",
        "press_pull_faces",
        "thicken_surface",
        "super_hatch",
        # A model cut and flattened to 2D, surfaces and meshes, by the plug-in (D-95).
        "flatten_views",
        "section_plane",
        "add_surface",
        "add_mesh",
        "add_light",
        "create_material",
        # Setting a render up, by the plug-in (D-86, D-87); none of them renders.
        "add_camera_view",
        "set_sun",
        "switch_lights",
        "set_render_exposure",
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
        # The everyday 2D edits (D-78, D-79): geometry worked out in Python, written over COM.
        "trim_extend",
        "fillet_chamfer",
        "break_curve",
        "join_curves",
        "edit_vertex",
        "stretch",
        "explode",
        "draw_order",
        "match_properties",
        "group",
        # Layers and annotation (D-80, D-81).
        "layer_states",
        "isolate_layers",
        "merge_layers",
        "space_dimensions",
        "break_dimensions",
        "annotation_scales",
        # PDF Import: a PDF page as lines, -PDFIMPORT typed in one form (D-106).
        "import_pdf",
        # The smaller draw gaps from the ribbon audit (D-108): COM, and Heron's own maths.
        "add_construction_line",
        "add_region",
        "add_donut",
        "divide_curve",
        # The smaller ribbon gaps, part 2 of #119 (D-110, D-111).
        "associative_array",
        "hyperlinks",
        "geo_location",
    ),
    Risk.PUBLISH: (
        "export_attribute_sheet",
        "save_drawing",
        "export",
        "create_hatch_pattern",
        "create_linetype",
        "publish_pdf",
        "checklist_report",  # writes an .xlsx and an .html next to the drawing (D-65)
        "share_checklist",  # writes the office folder or the project folder, where the team reads (D-93)
        "etransmit",  # writes a folder or a .zip of the drawing and its files (D-85)
    ),
    Risk.ADMIN: (
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
