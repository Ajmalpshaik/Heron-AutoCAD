# Tool catalogue

<!-- Made by tools/make_tool_catalogue.py from the live tool list. Do not edit by hand: run `python tools/make_tool_catalogue.py` instead. tests/test_tool_catalogue.py fails when this file is stale. -->

Every one of Heron's **200** tools, in plain words, grouped by the job it does. For each tool: what it does, the problem it solves, where to find it, how to use it step by step, what it needs from you, the result to expect, its limits, and whether anyone has seen it work in a real AutoCAD.

> **Read this first.** Nothing here claims a tool works in AutoCAD. The *Live proof* line of each tool is copied from [NEEDS-CHECKING](NEEDS-CHECKING.md), the one register of what was run for real. Today: **4** tools PASS, **15** PARTLY, **157** NOT RUN, **0** FAIL, **24** have no row at all. A PASS means a real AutoCAD, in the version named, gave the result the row expects; a build or an offline test is not a proof.

## How Heron's tools work (the same for every tool)

- **You do not click a tool.** There is no ribbon button per tool. You describe the job to Claude in the chat; Claude picks the tool. The Heron tab only holds the connection and the padlocks ([06 - the plug-in](06-heron-plugin.md)).
- **Heron must be pressed first.** AutoCAD starts disconnected. Press **Heron** on the Heron tab (or type `HERON`): the heron turns orange. Until then every tool is refused with the sentence that says so.
- **Padlocks decide what is allowed, and all start OFF** (in **Settings**; each asks before it turns on):

| Level | Padlocks that must be ON | What it covers |
|---|---|---|
| Read (44 tools) | none: reads the drawing | looking, listing, measuring, checking |
| View (9 tools) | none: changes only the screen | zoom, switch or open a drawing, 3D view direction |
| Change (133 tools) | Changes | drawing, editing, text, blocks, layers, sheets, 3D |
| Publish (9 tools) | Changes + Publish | saving, exporting, plotting, reports written to files |
| Admin (5 tools) | Changes + Admin | commands, AutoLISP, system variables, purge, audit |

- **Every change answers with one line first**: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Every change is one undo step.
- **Coordinates are in the drawing's own units**, and angles are degrees. Claude checks the units first with `autocad_status`.
- **AutoCAD versions.** The plug-in is built for AutoCAD **2021 to 2027** (full AutoCAD, not LT): 2021-2024 on .NET Framework 4.8, 2025-2026 on .NET 8, 2027 on .NET 10. It has only ever been run in **2027**, and only the rows marked PASS in [NEEDS-CHECKING](NEEDS-CHECKING.md). For 2021-2026 nothing was run: groups B and C there are NO MACHINE.
- **A tool Claude cannot find or is refused**: ask Claude `why can't you do this?` (the tool `autocad_why`), which names the real reason and what you do about it. The longer fixes are in [TROUBLESHOOTING](TROUBLESHOOTING.md).

## The groups

| Group | Tools | What is in it |
|---|---|---|
| [Drawing and coordinates](#drawing-and-coordinates) | 26 | Lines, circles, polylines, hatches, standard shapes, and the coordinate system they are drawn in. |
| [Editing and reading objects](#editing-and-reading-objects) | 34 | Move, copy, trim, fillet, change properties, and the tools that find and measure what is drawn. |
| [Text, labels and tables](#text-labels-and-tables) | 21 | Text, leaders, labels, tags, schedules as tables, text styles and annotation scales. |
| [Dimensions](#dimensions) | 5 | Dimensions, dimension runs, centre marks. |
| [Blocks, attributes and references](#blocks-attributes-and-references) | 21 | Blocks and their attributes, dynamic blocks, xrefs, underlays, taking objects from another drawing. |
| [Layers and linetypes](#layers-and-linetypes) | 11 | Layers, layer states, the office layer standard, linetypes. |
| [Sheets and printing](#sheets-and-printing) | 10 | Layouts, viewports, title blocks, drawing lists, page set-up, PDF. |
| [3D, lights and rendering set-up](#3d-lights-and-rendering-set-up) | 36 | Solids, surfaces, meshes, 3D edits, sections, lights, materials, the sun, cameras. Never the render itself. |
| [Checks and reports](#checks-and-reports) | 8 | Check lists, standards checks, drawing reports, audit and purge. |
| [Files and drawings](#files-and-drawings) | 8 | Open, create, save, export, switch drawing, read a file without AutoCAD. |
| [Heron itself, looking, commands and settings](#heron-itself-looking-commands-and-settings) | 20 | The connection, what Heron did, undo, saved commands, looking at the drawing, and the Admin tools (commands, AutoLISP, system variables). |

## Every tool at a glance

| Tool | Group | Padlocks | Live proof |
|---|---|---|---|
| [`autocad_activity`](#autocad_activity) | Heron itself, looking, commands and settings | none: reads the drawing | NOT RUN |
| [`autocad_add_camera_view`](#autocad_add_camera_view) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_add_centre_marks`](#autocad_add_centre_marks) | Dimensions | Changes | NOT RUN |
| [`autocad_add_construction_line`](#autocad_add_construction_line) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_add_dimension`](#autocad_add_dimension) | Dimensions | Changes | NOT RUN |
| [`autocad_add_donut`](#autocad_add_donut) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_add_field_label`](#autocad_add_field_label) | Text, labels and tables | Changes | NO ROW |
| [`autocad_add_hatch`](#autocad_add_hatch) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_add_label`](#autocad_add_label) | Text, labels and tables | Changes | PASS |
| [`autocad_add_light`](#autocad_add_light) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_add_mesh`](#autocad_add_mesh) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_add_mtext`](#autocad_add_mtext) | Text, labels and tables | Changes | NO ROW |
| [`autocad_add_multileader`](#autocad_add_multileader) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_add_polysolid`](#autocad_add_polysolid) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_add_pyramid`](#autocad_add_pyramid) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_add_region`](#autocad_add_region) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_add_revision_cloud`](#autocad_add_revision_cloud) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_add_solid`](#autocad_add_solid) | 3D, lights and rendering set-up | Changes | PARTLY |
| [`autocad_add_surface`](#autocad_add_surface) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_add_table`](#autocad_add_table) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_add_text`](#autocad_add_text) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_add_viewport`](#autocad_add_viewport) | Sheets and printing | Changes | PARTLY |
| [`autocad_add_wipeout`](#autocad_add_wipeout) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_align_text`](#autocad_align_text) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_annotation_scales`](#autocad_annotation_scales) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_apply_attribute_sheet`](#autocad_apply_attribute_sheet) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_apply_material`](#autocad_apply_material) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_array_entities`](#autocad_array_entities) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_associative_array`](#autocad_associative_array) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_attach_underlay`](#autocad_attach_underlay) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_attach_xref`](#autocad_attach_xref) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_audit`](#autocad_audit) | Checks and reports | Changes + Admin | NO ROW |
| [`autocad_batch_draw`](#autocad_batch_draw) | Drawing and coordinates | Changes | PARTLY |
| [`autocad_batch_labels`](#autocad_batch_labels) | Text, labels and tables | Changes | PARTLY |
| [`autocad_break_at_blocks`](#autocad_break_at_blocks) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_break_curve`](#autocad_break_curve) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_break_dimensions`](#autocad_break_dimensions) | Dimensions | Changes | NOT RUN |
| [`autocad_chamfer_solid_edges`](#autocad_chamfer_solid_edges) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_check_folder`](#autocad_check_folder) | Checks and reports | none: changes only what is on screen | NOT RUN |
| [`autocad_check_interference`](#autocad_check_interference) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_check_standards`](#autocad_check_standards) | Checks and reports | none: reads the drawing | NOT RUN |
| [`autocad_checklist`](#autocad_checklist) | Checks and reports | none: reads the drawing | NOT RUN |
| [`autocad_checklist_report`](#autocad_checklist_report) | Checks and reports | Changes + Publish | NOT RUN |
| [`autocad_clip_reference`](#autocad_clip_reference) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_companion`](#autocad_companion) | Heron itself, looking, commands and settings | none: reads the drawing | NOT RUN |
| [`autocad_convert_points`](#autocad_convert_points) | Drawing and coordinates | none: reads the drawing | NOT RUN |
| [`autocad_copy_entities`](#autocad_copy_entities) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_copy_from_drawing`](#autocad_copy_from_drawing) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_count_blocks`](#autocad_count_blocks) | Blocks, attributes and references | none: reads the drawing | PARTLY |
| [`autocad_count_text`](#autocad_count_text) | Text, labels and tables | none: reads the drawing | NOT RUN |
| [`autocad_create_drawing`](#autocad_create_drawing) | Files and drawings | none: changes only what is on screen | NO ROW |
| [`autocad_create_hatch_pattern`](#autocad_create_hatch_pattern) | Drawing and coordinates | Changes + Publish | NOT RUN |
| [`autocad_create_layer`](#autocad_create_layer) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_create_layout`](#autocad_create_layout) | Sheets and printing | Changes | NOT RUN |
| [`autocad_create_linetype`](#autocad_create_linetype) | Layers and linetypes | Changes + Publish | NOT RUN |
| [`autocad_create_material`](#autocad_create_material) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_create_styles`](#autocad_create_styles) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_delete_entities`](#autocad_delete_entities) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_delete_layer`](#autocad_delete_layer) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_dimension_run`](#autocad_dimension_run) | Dimensions | Changes | NOT RUN |
| [`autocad_divide_curve`](#autocad_divide_curve) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_draw_3d_path`](#autocad_draw_3d_path) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_draw_arc`](#autocad_draw_arc) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_draw_circle`](#autocad_draw_circle) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_draw_ellipse`](#autocad_draw_ellipse) | Drawing and coordinates | Changes | NO ROW |
| [`autocad_draw_line`](#autocad_draw_line) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_draw_multiline`](#autocad_draw_multiline) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_draw_order`](#autocad_draw_order) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_draw_point`](#autocad_draw_point) | Drawing and coordinates | Changes | NO ROW |
| [`autocad_draw_polyline`](#autocad_draw_polyline) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_draw_rectangle`](#autocad_draw_rectangle) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_draw_spline`](#autocad_draw_spline) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_drawing_report`](#autocad_drawing_report) | Checks and reports | none: reads the drawing | NOT RUN |
| [`autocad_drawing_setup`](#autocad_drawing_setup) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_edit_solid_faces`](#autocad_edit_solid_faces) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_edit_spline`](#autocad_edit_spline) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_edit_vertex`](#autocad_edit_vertex) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_etransmit`](#autocad_etransmit) | Files and drawings | Changes + Publish | NOT RUN |
| [`autocad_explode`](#autocad_explode) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_export`](#autocad_export) | Files and drawings | Changes + Publish | NOT RUN |
| [`autocad_export_attribute_sheet`](#autocad_export_attribute_sheet) | Blocks, attributes and references | Changes + Publish | NOT RUN |
| [`autocad_extract_attributes`](#autocad_extract_attributes) | Blocks, attributes and references | none: reads the drawing | NOT RUN |
| [`autocad_extrude_profile`](#autocad_extrude_profile) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_fillet_chamfer`](#autocad_fillet_chamfer) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_fillet_solid_edges`](#autocad_fillet_solid_edges) | 3D, lights and rendering set-up | Changes | PARTLY |
| [`autocad_find_replace_text`](#autocad_find_replace_text) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_find_text`](#autocad_find_text) | Text, labels and tables | none: reads the drawing | NOT RUN |
| [`autocad_flatten_views`](#autocad_flatten_views) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_gaps`](#autocad_gaps) | Heron itself, looking, commands and settings | none: reads the drawing | NOT RUN |
| [`autocad_geo_location`](#autocad_geo_location) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_get_dynamic_properties`](#autocad_get_dynamic_properties) | Blocks, attributes and references | none: reads the drawing | PASS |
| [`autocad_get_entity`](#autocad_get_entity) | Editing and reading objects | none: reads the drawing | NOT RUN |
| [`autocad_get_extents`](#autocad_get_extents) | Editing and reading objects | none: reads the drawing | NOT RUN |
| [`autocad_get_geo_location`](#autocad_get_geo_location) | 3D, lights and rendering set-up | none: reads the drawing | NOT RUN |
| [`autocad_get_selection`](#autocad_get_selection) | Heron itself, looking, commands and settings | none: reads the drawing | NO ROW |
| [`autocad_get_ucs`](#autocad_get_ucs) | Drawing and coordinates | none: reads the drawing | NOT RUN |
| [`autocad_get_variable`](#autocad_get_variable) | Heron itself, looking, commands and settings | none: reads the drawing | NOT RUN |
| [`autocad_group`](#autocad_group) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_hyperlinks`](#autocad_hyperlinks) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_import_from_drawing`](#autocad_import_from_drawing) | Blocks, attributes and references | Changes | NO ROW |
| [`autocad_import_pdf`](#autocad_import_pdf) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_imprint_solid`](#autocad_imprint_solid) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_insert_block`](#autocad_insert_block) | Blocks, attributes and references | Changes | PARTLY |
| [`autocad_isolate_layers`](#autocad_isolate_layers) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_join_curves`](#autocad_join_curves) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_label_segment_lengths`](#autocad_label_segment_lengths) | Text, labels and tables | Changes | NO ROW |
| [`autocad_layer_standard`](#autocad_layer_standard) | Layers and linetypes | none: reads the drawing | NOT RUN |
| [`autocad_layer_states`](#autocad_layer_states) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_lengthen`](#autocad_lengthen) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_list_annotation_scales`](#autocad_list_annotation_scales) | Text, labels and tables | none: reads the drawing | NOT RUN |
| [`autocad_list_blocks`](#autocad_list_blocks) | Blocks, attributes and references | none: reads the drawing | PARTLY |
| [`autocad_list_drawings`](#autocad_list_drawings) | Files and drawings | none: reads the drawing | NO ROW |
| [`autocad_list_entities`](#autocad_list_entities) | Editing and reading objects | none: reads the drawing | NOT RUN |
| [`autocad_list_groups`](#autocad_list_groups) | Editing and reading objects | none: reads the drawing | NOT RUN |
| [`autocad_list_hyperlinks`](#autocad_list_hyperlinks) | Editing and reading objects | none: reads the drawing | NOT RUN |
| [`autocad_list_layers`](#autocad_list_layers) | Layers and linetypes | none: reads the drawing | NOT RUN |
| [`autocad_list_layouts`](#autocad_list_layouts) | Sheets and printing | none: reads the drawing | NO ROW |
| [`autocad_list_lights`](#autocad_list_lights) | 3D, lights and rendering set-up | none: reads the drawing | NOT RUN |
| [`autocad_list_materials`](#autocad_list_materials) | 3D, lights and rendering set-up | none: reads the drawing | NOT RUN |
| [`autocad_list_solid_faces_and_edges`](#autocad_list_solid_faces_and_edges) | 3D, lights and rendering set-up | none: reads the drawing | PARTLY |
| [`autocad_list_styles`](#autocad_list_styles) | Text, labels and tables | none: reads the drawing | NO ROW |
| [`autocad_list_views`](#autocad_list_views) | Sheets and printing | none: reads the drawing | NOT RUN |
| [`autocad_loft`](#autocad_loft) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_make_block`](#autocad_make_block) | Blocks, attributes and references | Changes | PARTLY |
| [`autocad_make_shape`](#autocad_make_shape) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_manage_layouts`](#autocad_manage_layouts) | Sheets and printing | Changes | NO ROW |
| [`autocad_manage_xref`](#autocad_manage_xref) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_match_properties`](#autocad_match_properties) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_measure`](#autocad_measure) | Editing and reading objects | none: reads the drawing | NOT RUN |
| [`autocad_merge_layers`](#autocad_merge_layers) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_mirror_entities`](#autocad_mirror_entities) | Editing and reading objects | Changes | NO ROW |
| [`autocad_modify_entity`](#autocad_modify_entity) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_move_entities`](#autocad_move_entities) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_number_tags`](#autocad_number_tags) | Text, labels and tables | Changes | NO ROW |
| [`autocad_offset_entities`](#autocad_offset_entities) | Editing and reading objects | Changes | NO ROW |
| [`autocad_open_drawing`](#autocad_open_drawing) | Files and drawings | none: changes only what is on screen | NO ROW |
| [`autocad_overkill`](#autocad_overkill) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_page_setup`](#autocad_page_setup) | Sheets and printing | Changes | NOT RUN |
| [`autocad_place_along`](#autocad_place_along) | Blocks, attributes and references | Changes | NO ROW |
| [`autocad_place_from_csv`](#autocad_place_from_csv) | Blocks, attributes and references | Changes | NO ROW |
| [`autocad_place_title_block`](#autocad_place_title_block) | Sheets and printing | Changes | PASS |
| [`autocad_polyline_info`](#autocad_polyline_info) | Editing and reading objects | none: reads the drawing | NOT RUN |
| [`autocad_press_pull_faces`](#autocad_press_pull_faces) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_preview`](#autocad_preview) | Heron itself, looking, commands and settings | none: reads the drawing | PARTLY |
| [`autocad_project_notes`](#autocad_project_notes) | Heron itself, looking, commands and settings | none: reads the drawing | NO ROW |
| [`autocad_publish_pdf`](#autocad_publish_pdf) | Sheets and printing | Changes + Publish | NOT RUN |
| [`autocad_purge`](#autocad_purge) | Checks and reports | Changes + Admin | NOT RUN |
| [`autocad_read_file`](#autocad_read_file) | Files and drawings | none: reads the drawing | NOT RUN |
| [`autocad_regen`](#autocad_regen) | Heron itself, looking, commands and settings | none: changes only what is on screen | NO ROW |
| [`autocad_remap_layers`](#autocad_remap_layers) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_rotate_entities`](#autocad_rotate_entities) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_run_lisp`](#autocad_run_lisp) | Heron itself, looking, commands and settings | Changes + Admin | PARTLY |
| [`autocad_save_drawing`](#autocad_save_drawing) | Files and drawings | Changes + Publish | NOT RUN |
| [`autocad_save_view`](#autocad_save_view) | Sheets and printing | Changes | NOT RUN |
| [`autocad_saved_command`](#autocad_saved_command) | Heron itself, looking, commands and settings | Changes | NOT RUN |
| [`autocad_scale_entities`](#autocad_scale_entities) | Editing and reading objects | Changes | NO ROW |
| [`autocad_section_plane`](#autocad_section_plane) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_select_connected`](#autocad_select_connected) | Editing and reading objects | none: reads the drawing | NO ROW |
| [`autocad_send_command`](#autocad_send_command) | Heron itself, looking, commands and settings | Changes + Admin | NOT RUN |
| [`autocad_separate_solid`](#autocad_separate_solid) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_sequence`](#autocad_sequence) | Heron itself, looking, commands and settings | Changes | NOT RUN |
| [`autocad_set_3d_view`](#autocad_set_3d_view) | 3D, lights and rendering set-up | none: changes only what is on screen | NOT RUN |
| [`autocad_set_attributes`](#autocad_set_attributes) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_set_current_layer`](#autocad_set_current_layer) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_set_dynamic_properties`](#autocad_set_dynamic_properties) | Blocks, attributes and references | Changes | PASS |
| [`autocad_set_layer_state`](#autocad_set_layer_state) | Layers and linetypes | Changes | NOT RUN |
| [`autocad_set_render_exposure`](#autocad_set_render_exposure) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_set_sun`](#autocad_set_sun) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_set_table_cells`](#autocad_set_table_cells) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_set_ucs`](#autocad_set_ucs) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_set_variable`](#autocad_set_variable) | Heron itself, looking, commands and settings | Changes + Admin | NOT RUN |
| [`autocad_share_checklist`](#autocad_share_checklist) | Checks and reports | Changes + Publish | NOT RUN |
| [`autocad_sheet_set`](#autocad_sheet_set) | Sheets and printing | Changes | NOT RUN |
| [`autocad_shell_solid`](#autocad_shell_solid) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_show`](#autocad_show) | Heron itself, looking, commands and settings | none: changes only what is on screen | NOT RUN |
| [`autocad_slice_solid`](#autocad_slice_solid) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_solid_boolean`](#autocad_solid_boolean) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_solid_properties`](#autocad_solid_properties) | 3D, lights and rendering set-up | none: reads the drawing | NOT RUN |
| [`autocad_space_dimensions`](#autocad_space_dimensions) | Dimensions | Changes | NOT RUN |
| [`autocad_status`](#autocad_status) | Heron itself, looking, commands and settings | none: reads the drawing | PARTLY |
| [`autocad_stretch`](#autocad_stretch) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_super_hatch`](#autocad_super_hatch) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_switch_drawing`](#autocad_switch_drawing) | Files and drawings | none: changes only what is on screen | NOT RUN |
| [`autocad_switch_lights`](#autocad_switch_lights) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_sync_attributes`](#autocad_sync_attributes) | Blocks, attributes and references | Changes | NOT RUN |
| [`autocad_table_from_excel`](#autocad_table_from_excel) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_text_clean`](#autocad_text_clean) | Text, labels and tables | Changes | NO ROW |
| [`autocad_thicken_surface`](#autocad_thicken_surface) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_tidy_entities`](#autocad_tidy_entities) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_tiled_viewports`](#autocad_tiled_viewports) | Heron itself, looking, commands and settings | none: changes only what is on screen | NOT RUN |
| [`autocad_total_length`](#autocad_total_length) | Editing and reading objects | none: reads the drawing | PARTLY |
| [`autocad_trace_boundary`](#autocad_trace_boundary) | Drawing and coordinates | Changes | NOT RUN |
| [`autocad_transform_3d`](#autocad_transform_3d) | 3D, lights and rendering set-up | Changes | NOT RUN |
| [`autocad_trim_extend`](#autocad_trim_extend) | Editing and reading objects | Changes | NOT RUN |
| [`autocad_undo_last`](#autocad_undo_last) | Heron itself, looking, commands and settings | Changes | NOT RUN |
| [`autocad_update_table_links`](#autocad_update_table_links) | Text, labels and tables | Changes | NOT RUN |
| [`autocad_use_autocad`](#autocad_use_autocad) | Heron itself, looking, commands and settings | none: reads the drawing | NOT RUN |
| [`autocad_why`](#autocad_why) | Heron itself, looking, commands and settings | none: reads the drawing | NOT RUN |
| [`autocad_xref_tree`](#autocad_xref_tree) | Blocks, attributes and references | none: reads the drawing | NOT RUN |
| [`autocad_zoom`](#autocad_zoom) | Heron itself, looking, commands and settings | none: changes only what is on screen | PARTLY |

## Drawing and coordinates

Lines, circles, polylines, hatches, standard shapes, and the coordinate system they are drawn in.

### `autocad_add_construction_line`

**What it does.** Draw a construction line (XLINE, endless both ways) or a ray (RAY, endless one way).
For setting-out: grid and centre references, a line at an angle to work from. They plot like lines, so put them on a no-plot layer. Points are world coordinates.

**The problem it solves.**
- "a vertical setting-out line through the riser at 4500,2200" -> base=[4500, 2200], angle=90.
- "a ray from the pump outlet towards the tank" -> kind='ray', base at the outlet, through at the tank.
- *Not for:* the line should stop somewhere - autocad_draw_line.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a vertical setting-out line through the riser at 4500,2200"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `base`: A point the line runs through, as [x, y] or [x, y, z]. A ray starts here.
- Optional: `through`, `angle`, `kind`, `layer`, `color`, `linetype`, `space`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle", "type": "xline" | "ray", "layer", "base_point", "direction", "angle_degrees"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AP1).

### `autocad_add_donut`

**What it does.** Draw donuts, or filled dots (inside 0), the same object AutoCAD's DONUT makes.
Each is a closed polyline of two half circles with one width: the line runs midway between the two diameters and is as wide as the gap. All of them in one undo step.

**The problem it solves.**
- "a filled 3 mm dot at every pipe junction on the schematic" -> centers=[...], outside_diameter=3.
- "a ring 150 outside, 100 inside at each sleeve" -> outside_diameter=150, inside_diameter=100.
- *Not for:* you want a plain unfilled circle - autocad_draw_circle; a hatched circle - autocad_add_hatch.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a filled 3 mm dot at every pipe junction on the schematic"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `centers`: One or more centres, each [x, y] or [x, y, z]. DONUT asks for centres again and again; give them all here.
- Needs `outside_diameter`: Outside diameter, in drawing units.
- Optional: `inside_diameter`, `layer`, `color`, `space`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": n, "handles", "type": "polyline", "width", "centreline_radius", "verified"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AP5).

### `autocad_add_hatch`

**What it does.** Fill a closed boundary with a solid fill or a hatch pattern.
The boundary must already exist and be closed — draw it first with autocad_draw_polyline (closed=true), autocad_draw_rectangle or autocad_draw_circle, then pass the handle that tool returned.

**The problem it solves.**
- "hatch that slab as concrete" -> pattern="AR-CONC" round the slab's boundary.
- You want a solid fill - pattern="SOLID".

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"hatch that slab as concrete"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `boundary_handles`: Handles of the CLOSED entities forming the hatch boundary — closed polylines, circles or ellipses.
- Optional: `pattern`, `scale`, `angle`, `associative`, `layer`, `color`, `space`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "hatch", "layer": str, "pattern": str, "area": float}`

**Limits and versions.**
- Names the offending handle when a boundary entity is an open shape, which is the usual cause of a failed hatch.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G10, S4).

### `autocad_add_region`

**What it does.** Turn closed outlines into regions (REGION), each with its area, perimeter and centre.
A region is a flat face: its area and centre can be read, it can be extruded, and holes can be cut out of it. AutoCAD makes one region per closed loop. The regions go in the outlines' own space. One undo step.

**The problem it solves.**
- "make that slab outline a region so I can take its area and centre" -> handles=[the outline].
- "turn the plant room walls (lines meeting end to end) into one face" -> handles=all the lines.
- *Not for:* you only want an area - autocad_polyline_info or autocad_measure. To cut shafts out of a region afterwards: autocad_solid_boolean subtract (it takes regions). For a hatch: autocad_add_hatch.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make that slab outline a region so I can take its area and centre"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The closed outlines: closed polylines, circles, ellipses, closed splines, or lines and arcs that meet end to end in a closed loop.
- Optional: `erase_outlines`, `layer`, `color`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": n, "regions": [{"handle", "area", "perimeter", "centroid"}], "erased_outlines": [...]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AP2, AP3, AP4, BG8).

### `autocad_add_revision_cloud`

**What it does.** Draw a revision cloud, as one polyline with its arcs bulging outward.
Say what to cloud: a boundary, a rectangle, or an object — clouding round an object's own extents is what a revision usually means. The arcs come out an even size because the spacing is adjusted to divide the boundary exactly, so the last arc is never a stub. Same object AutoCAD's own REVCLOUD makes: a polyline with bulges, so it selects, moves and plots as one thing. One undo step.

**The problem it solves.**
- "cloud this detail, revision B" — handle=, margin about 5 mm of paper, colour red.
- "cloud the area I just changed" — corner1/corner2.
- *Not for:* you want the revision note too — add that with autocad_add_multileader or the 'revision_tag' shape.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"cloud this detail, revision B"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `points`, `corner1`, `corner2`, `handle`, `handles`, `arc_length`, `margin`, `closed`, `layer`, `color`, and 1 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": int, "handles": [str], "arcs": int, "boundary": [[x, y]], "arc_length": float, "from": str}`

**Limits and versions.**
- Says so when the thing named reports no extents to cloud round.
- An arc length that would need thousands of arcs is refused with the count, rather than filling the drawing.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E20).

### `autocad_add_wipeout`

**What it does.** Mask an area with a wipeout, so what is behind it does not show or plot.
A WIPEOUT, in the space that is current (model or the active layout). Typical: clear the hatch or grid behind a tag, a note or a block. Automation has no call that makes a wipeout, so this types the WIPEOUT command with every corner in world coordinates and snaps off, then finds the object it made. One undo step.

**The problem it solves.**
- "mask the hatch behind this tag" — the tag's box as points.
- "turn this closed outline into a wipeout" — boundary_handle, erase_boundary=true.
- "hide the wipeout frames" — frames='hide' (or 'show_no_plot' to see them on screen only).
- *Not for:* it is only a text background — autocad_add_label and MText have a background mask of their own.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"mask the hatch behind this tag"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `points`, `boundary_handle`, `erase_boundary`, `frames`, `layer`, `color`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "wipeout", "layer": str, "corners": int, "boundary_erased": bool, "not_set": [str]}`

**Limits and versions.**
- Fewer than three corners, corners in a line, an open polyline or one with arcs are refused before anything is typed.
- If AutoCAD is still asking when the command should be done, it is cancelled and the tool says so; nothing is left half made.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G5, G6).

### `autocad_batch_draw`

**What it does.** Create many entities at once, far faster than one call per entity.
Use this whenever you are drawing more than about ten things — a floor plan, a grid, a hatch pattern of lines, a set of labels. It sends a single AutoLISP script that runs inside AutoCAD, instead of one COM round trip per entity, and the whole batch lands as one undo step. Measured on AutoCAD 2020, 200 lines: 20.3s one at a time through the autocad_draw_* tools, 2.2s through this one — about 9x, or 17x with return_handles=false.

**The problem it solves.**
- "draw this 20 x 15 m grid at 1 m spacing" — 36 lines in one call rather than 36.
- Placing a room's worth of walls, doors and labels together.
- A symbol needs a solid head or a filled half - a hatch operation with the outline's points beside its polyline.
- *Not for:* creating one or two entities, or when you need the richer validation and per-entity feedback of autocad_draw_* tools.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"draw this 20 x 15 m grid at 1 m spacing"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `operations`: Entities to create, in order. Each is an object with a 'type' and that type's fields, plus optional 'layer' and 'color'. Angles are DEGREES;
- Optional: `return_handles`, `coords`, `quiet`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "created": int, # entities actually made "failed": int, # operations AutoCAD rejected "requested": int, "handles": [str], # in order;`

**Limits and versions.**
- An unknown operation type, or a missing required field, is reported with its index before the batch runs.
- If AutoCAD rejects individual operations (locked layer, degenerate geometry), "failed" counts them and "created" reflects what did land.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **PARTLY**: rows A8c, A22, A21 passed in AutoCAD 2027; the rest are NOT RUN (rows A8c, A22, A21, D4, D7, E36, N8, AW11, AJ6, AJ7, AJ8, AI4, AI5, AI6, AI7, S1).

### `autocad_convert_points`

**What it does.** Move points between the modeller's UCS and the world coordinates every tool takes.
This is AutoLISP's ``trans``. Use it whenever the modeller gives you coordinates off a drawing with a UCS set: convert first, then draw with the world numbers. Nothing in the drawing changes.

**The problem it solves.**
- "the pump is at 2400,1800 on my rotated plan" — convert, then insert the block at the world point that comes back.
- Reporting a picked world point back in the modeller's own numbers.
- *Not for:* the UCS is the world one; "unchanged" tells you it was.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"the pump is at 2400,1800 on my rotated plan"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `points`: The points to convert, each [x, y] or [x, y, z].
- Optional: `into`, `ucs_name`, `angles`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: { "into": str, "points": [[x, y, z]], "angles": [float] | null, "ucs": {...}, "unchanged": bool # true when the UCS is the world one }`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D3, D7).

### `autocad_create_hatch_pattern`

**What it does.** Make a custom hatch pattern - a .pat file AutoCAD can hatch with.
For a hatch acad.pat does not have: an insulation or sleeve pattern, an office-standard grid, a dashed fill. One NAME.pat per pattern, which is what AutoCAD needs for a custom pattern; then hatch with autocad_add_hatch(pattern='NAME'). Writes a file, so it needs the Publish padlock as well as Changes.

**The problem it solves.**
- "make a hatch of 45 degree lines 3 apart for the insulation" — preset='lines', angle=45, spacing=3.
- "a 5 mm square grid hatch" — preset='cross', angle=0, spacing=5.
- *Not for:* the pattern is a standard one (ANSI31, AR-CONC, EARTH...) — autocad_add_hatch uses those straight away.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make a hatch of 45 degree lines 3 apart for the insulation"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: Pattern name, also the file name: letters, digits, '-' or '_', up to 31, e.g. 'CHW-INS'.
- Optional: `preset`, `angle`, `spacing`, `dashes`, `families`, `description`, `folder`, `add_to_support_path`, `replace`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"file": str, "file_text": str, "support_path_added": bool, "hint": str}`

**Limits and versions.**
- Spacing 0, more than six dashes, a line over 80 characters or a name that cannot be a file name are refused before anything is written.
- An existing file is not written over without replace=true.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G10).

### `autocad_divide_curve`

**What it does.** Mark a run like AutoCAD's DIVIDE (N equal parts) or MEASURE (every X), with points or a block.
DIVIDE leaves the ends of an open run free (N parts give N - 1 marks); on a closed run the first mark is on its start point. MEASURE starts at the start (or the end, with from_end) and leaves the short rest at the far end; it puts no mark exactly on the end. Circles start at 0 degrees and go anticlockwise. The marks go in the run's own space. One undo step.

**The problem it solves.**
- "divide that duct run into 6 equal parts with points so I can snap the diffusers" -> segments=6.
- "a support block every 1500 from the start of that pipe" -> interval=1500, block_name='SUPPORT'.
- *Not for:* the blocks should be centred with equal ends - autocad_place_along; positions from a schedule - autocad_place_from_csv.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"divide that duct run into 6 equal parts with points so I can snap the diffusers"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path_handle`: The line, polyline, arc or circle to mark along.
- Optional: `segments`, `interval`, `from_end`, `block_name`, `align`, `rotation`, `scale`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"placed": n, "kind": "points" | "block", "handles", "run_length", "step", "left_at_end", "positions"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AP6, AP7, AP8, AP9, AP10).

### `autocad_draw_arc`

**What it does.** Draw an arc from a centre, radius and angle range.
Angles are degrees counter-clockwise from East, matching how AutoCAD displays them by default.

**The problem it solves.**
- "the top half of a circle" -> start_angle=0, end_angle=180.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"the top half of a circle"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `center`: Centre point as [x, y].
- Needs `radius`: Radius in drawing units.
- Needs `start_angle`: Start angle in DEGREES, counter-clockwise from the positive X axis. 0 is East, 90 is North.
- Needs `end_angle`: End angle in DEGREES. The arc always sweeps counter-clockwise from start_angle to end_angle.
- Optional: `layer`, `color`, `linetype`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "arc", "layer": str, "radius": float, "start_angle_degrees": float, "end_angle_degrees": float, "arc_length": float}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI1, AI3).

### `autocad_draw_circle`

**What it does.** Draw a circle from a centre point and a radius or diameter.
Taking diameter directly avoids the halving mistakes that arise when a drawing calls out pipe, duct or bolt sizes by diameter.

**The problem it solves.**
- "a 300 dia hole at 2000,1500" -> center=[2000,1500], diameter=300.
- *Not for:* you want the hole and its centre lines - draw it, then autocad_add_centre_marks.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a 300 dia hole at 2000,1500"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `center`: Centre point as [x, y].
- Optional: `radius`, `diameter`, `layer`, `color`, `linetype`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "circle", "layer": str, "radius": float, "diameter": float, "area": float}`

**Limits and versions.**
- Returns an error if neither radius nor diameter is given, or if both are, rather than silently picking one.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T4, AL3).

### `autocad_draw_ellipse`

**What it does.** Draw an ellipse from its centre and its two half-axis lengths.

**The problem it solves.**
- "an oval access panel 600 by 400" -> major_axis=300, minor_axis=200 (they are half-axes).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"an oval access panel 600 by 400"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `center`: Centre point as [x, y].
- Needs `major_radius`: Half the ellipse's longest width, in drawing units.
- Needs `minor_radius`: Half the ellipse's shortest width, in drawing units.
- Optional: `rotation`, `layer`, `color`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "ellipse", "layer": str, "major_radius": float, "minor_radius": float, "area": float}`

**Limits and versions.**
- Returns an error if minor_radius exceeds major_radius, since AutoCAD would otherwise reject the axis ratio with an opaque COM failure.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_draw_line`

**What it does.** Draw a single straight line between two points.
Coordinates are in the drawing's own units — call autocad_status first if you do not know whether the drawing is in millimetres, metres or inches.

**The problem it solves.**
- "draw a 5 m line along X from the origin" -> start=[0,0], end=[5000,0] in a millimetre drawing.
- "a line along the grid" on a turned UCS -> the points as read off the screen, coords="ucs".
- *Not for:* you need several connected segments — use autocad_draw_polyline so they stay one object.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"draw a 5 m line along X from the origin"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `start`: Start point as [x, y] or [x, y, z], e.g. [0, 0].
- Needs `end`: End point as [x, y] or [x, y, z], e.g. [1000, 0].
- Optional: `layer`, `color`, `linetype`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "line", "layer": str, "length": float, "angle_degrees": float} With coords="ucs" on a UCS that is not the world one: also "converted_from_ucs" (the UCS the points were read in).`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows L5, L7, V3, W5, AQ16, RV3, BG1).

### `autocad_draw_multiline`

**What it does.** Draw a multiline (MLINE): parallel lines that turn corners together, like a wall.
One object for a run of wall, a double-line duct or a road in plan, with its style, width and justification - the way MLINE draws it. One undo step.

**The problem it solves.**
- "draw a 200 mm wall along these points" — scale=200.
- "MLINE a double line along the grid" — the grid points.
- "draw a double-line duct 400 wide" — scale=400.
- *Not for:* you need a solid wall to cut, hatch or quantify — a closed polyline (autocad_draw_polyline) or autocad_make_shape.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"draw a 200 mm wall along these points"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `points`: The vertices, in order, as [[x, y], ...]: a wall's centre line, or its face line with justification 'top' or 'bottom'.
- Optional: `scale`, `justification`, `style`, `closed`, `layer`, `color`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "multiline", "layer": str, "style": str, "scale": float, "justification": str, "vertices": int, "not_set": [str]}`

**Limits and versions.**
- A style the drawing does not have is refused before anything is drawn, naming MLSTYLE and autocad_import_from_drawing.
- Automation has no "close" for a multiline, so a closed one is drawn open and Heron's plug-in closes it the way MLINE's Close does, mitring the last corner ("mitred": true).
- The drawing's current multiline style is put back afterwards.
- The plug-in does part of the work (`close_multiline`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G3, AI8).

### `autocad_draw_point`

**What it does.** Place a single point object, useful as a survey or setting-out marker.
Points render as a bare dot by default and can be effectively invisible. Set PDMODE to 3 (an X) or 34 (a circled cross) via autocad_set_variable if the user needs to see them.

**The problem it solves.**
- "mark the survey points from this list" -> one call each, after autocad_drawing_setup sets a point style you can see.
- *Not for:* you want a visible symbol - insert a block instead.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"mark the survey points from this list"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `position`: Location as [x, y] or [x, y, z].
- Optional: `layer`, `color`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "point", "layer": str, "position": [float, float, float]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_draw_polyline`

**What it does.** Draw a connected multi-segment polyline, optionally closed.
A polyline is one object, so it can be offset, filleted and area-measured as a unit. Prefer it over separate lines for outlines, walls, boundaries and site edges.

**The problem it solves.**
- "outline a 10 x 5 m room" -> the four corners, closed=true.
- The room is square to a turned grid UCS -> its corners as read on screen, coords="ucs".
- *Not for:* the shape is a plain rectangle — autocad_draw_rectangle takes just two corners.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"outline a 10 x 5 m room"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `points`: Vertices in order, each [x, y], e.g. [[0,0],[1000,0],[1000,500]]. At least two are required.
- Optional: `closed`, `width`, `layer`, `color`, `linetype`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "polyline", "layer": str, "vertex_count": int, "closed": bool, "length": float, "area": float} "area" appears only when closed is true.`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI3).

### `autocad_draw_rectangle`

**What it does.** Draw an axis-aligned rectangle as a single closed polyline.

**The problem it solves.**
- "draw a 2400 x 1200 panel at the origin" -> corner1=[0,0], corner2=[2400,1200].
- The panel sits square to a turned grid UCS -> coords="ucs", and it comes out turned with the grid.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"draw a 2400 x 1200 panel at the origin"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `corner1`: One corner as [x, y].
- Needs `corner2`: The diagonally opposite corner as [x, y].
- Optional: `layer`, `color`, `linetype`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "polyline", "layer": str, "width": float, "height": float, "area": float, "perimeter": float} With coords="ucs" on a UCS that is not the world one: also "converted_from_ucs".`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI1).

### `autocad_draw_spline`

**What it does.** Draw a smooth spline through the points given, or pulled by them as control points.
By fit points (the SPLINE command's default): the curve goes through every point, not near them. The ends leave and arrive along the first and last segments unless tangents are given. By control points (SPLINE's CV method): the points are the frame the curve follows; it starts on the first and ends on the last, and leaves along the first and last legs. Closed, it comes round smoothly with no corner where it started. Made by Heron's plug-in, as COM has no call for it.

**The problem it solves.**
- "draw a flexible duct from the grille to the diffuser" — the route as points.
- "draw a curved boundary / contour / landscape edge through these points".
- "a smooth fair curve using these as control vertices" — method='control_points', degree=3.
- *Not for:* the curve is made of arcs and straights — that is a polyline (autocad_draw_polyline or autocad_batch_draw with bulges).
- *Not for:* the spline is drawn and only its points move — autocad_edit_spline.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"draw a flexible duct from the grille to the diffuser"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `points`: In order, as [[x, y], ...] or [[x, y, z], ...]. With method 'fit_points' (the default) the curve passes through every one;
- Optional: `closed`, `start_tangent`, `end_tangent`, `layer`, `color`, `linetype`, `space`, `coords`, `method`, `degree`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "spline", "layer": str, "fit_points": int, "closed": bool, "length": float, "not_set": [str]} By control points: "control_points" and "degree" in place of "fit_points".`

**Limits and versions.**
- Fewer than two points, points all at one place, or a zero tangent are refused before anything is drawn.
- By control points: too few points for the degree, two in a row at one place, or tangents given are refused before anything is drawn; so is running without the plug-in.
- A closed spline AutoCAD will not close is drawn open and says so in "not_set".
- The plug-in does part of the work (`add_cv_spline`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G1, AI10).

### `autocad_drawing_setup`

**What it does.** Set the drawing up the way a draftsman does before starting: units, scale, snaps, precision.
Give the drawing scale once and the settings that hang off it follow — DIMSCALE, the annotation scale, LTSCALE, and the model text height for a paper height. Only the options you pass are touched. This writes from a fixed list of drafting system variables and nothing else. Every one comes back with its old value beside its new one; dry_run shows the whole plan and writes nothing.

**The problem it solves.**
- Starting a drawing — units='millimeters', scale='1:50', paper_text_height=2.5, osnaps=['endpoint','midpoint','intersection'].
- Dimensions come out tiny — the drawing scale was never set. One scale sets DIMSCALE, LTSCALE, CANNOSCALE and the text height together, so they cannot disagree.
- "set DIMSCALE and LTSCALE for 1:50" — scale='1:50' does both, and needs only the Changes padlock.
- Dashed lines look solid — scale sets LTSCALE too.
- *Not for:* you need a variable outside the drafting list; that is autocad_set_variable, which needs the Admin padlock.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"set DIMSCALE and LTSCALE for 1:50"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `units`, `scale`, `ltscale_from_scale`, `paper_text_height`, `linear_format`, `linear_precision`, `angle_format`, `angle_precision`, `osnaps`, `point_style`, and 13 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "dry_run": bool, "changed": [{"variable", "from", "to"}], "unchanged": [str], "failed": [{"variable", "to", "reason"}], "osnaps_now": [str], "scale": "1:50" | null }`

**Limits and versions.**
- An unknown unit, snap, format or point style is named, with the values that are accepted, before anything is written.
- A variable this AutoCAD will not accept is reported in "failed"; the rest of the plan still lands.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D21, D22, D32, G11, AB1, S5).

### `autocad_get_ucs`

**What it does.** Report the drawing's current UCS: is it moved, turned or tilted?
Call this before giving coordinates read off the modeller's screen. Every coordinate in this server is a world coordinate; if the UCS is turned 23 degrees, "0,0 to 5000,0" draws a different line in each system.

**The problem it solves.**
- The modeller says "my UCS is rotated" or a drawn line comes out at the wrong angle.
- Picking up a drawing someone else set up.
- *Not for:* you only need the units (autocad_status gives both).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"my UCS is rotated"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: { "current": { "name", "is_world", "origin", "x_axis", "y_axis", "z_axis", "rotation_degrees", "moved", "rotated", "tilted", "flipped" }, "space": "model" | "paper", "elevation": float, # current ELEVATION in this space "advice": str ...`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D2).

### `autocad_import_pdf`

**What it does.** Turn one page of a PDF into real lines, text and hatches in the drawing (PDF Import, -PDFIMPORT).
For the vendor's general arrangement, the consultant's layout or an old drawing only kept as PDF: the page comes in as objects you can snap to, trim and dimension, at a point, scale and rotation, on one layer. A PDF made by a CAD program comes in as clean lines; a scanned PDF is a picture with no lines in it, and nothing comes in. No API can do this, so the tool types AutoCAD's own -PDFIMPORT with every answer at once, after checking this AutoCAD's release.

**The problem it solves.**
- "bring the AHU vendor drawing in as lines at 0,0" — path to the PDF.
- "import page 3 of the consultant's PDF onto layer M-XREF-PDF" — page=3, layer='M-XREF-PDF'.
- "convert this PDF to CAD, just the lines, no text" — what=['lines'].
- "the PDF is at 1:50, bring it in true size" — scale=50, then check one length with autocad_measure.
- *Not for:* you only need to see the PDF behind your drawing — attach it as a PDF underlay (autocad_attach_underlay, or PDFATTACH): nothing is copied in and it stays light.
- *Not for:* the file is a .dwg — autocad_attach_xref or autocad_copy_from_drawing.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"bring the AHU vendor drawing in as lines at 0,0"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: The PDF file, the whole path, e.g. 'D:\Project\Vendor\AHU-01 GA.pdf'.
- Optional: `page`, `insertion`, `scale`, `rotation`, `layer`, `what`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"imported": int, "by_type": {type: count}, "box": {"min", "max"} | null (world), "layer": str | null, "layer_created": bool, "moved_to_layer": int, "layers_added": [str], "page": int, "path": str, "release": int, "space": str ...`

**Limits and versions.**
- A missing file, a file that is not a PDF, or a page past the PDF's last page is refused before AutoCAD is asked.
- An AutoCAD release whose PDFIMPORT questions are not known (not 2021-2027), or a tilted or flipped UCS, is refused, nothing sent.
- If AutoCAD is still asking when every answer is given, the command is cancelled and the answer says so.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AO2, AO4, AO7, AO8, AW10).

### `autocad_make_shape`

**What it does.** Draw a shape from its name and its dimensions: flange, slot, stair, flat pattern, a 3D duct run or pipe spool.
This is the "simple words to complex geometry" path. Give the shape's name and the few numbers that define it, and the whole thing is generated and drawn as one undo step — arcs stay arcs, a slot stays one object, a flat pattern comes out at the right girth. Lengths are in the drawing's own units. ``coords='ucs'`` draws the shape square to the modeller's own grid.

**The problem it solves.**
- "draw a 200 flange with 8 x M16 holes on a 160 PCD" — shape="flange".
- "I need the flat pattern for a 200 to 100 reducer, 150 long" — shape="cone_development".
- "a 1200 wide stair, 14 risers at 175, 280 going, in section".
- "a 120 x 40 slot at 30 degrees" — one object, round ends.
- *Not for:* the thing is a one-off outline you can give as points (autocad_batch_draw), or it is already a block in the drawing (autocad_insert_block).
- *Not for:* one profile runs along a curve you already drew — autocad_extrude_profile with path_handle sweeps it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"draw a 200 flange with 8 x M16 holes on a 160 PCD"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `shape`: Which shape to draw. Each line below is the name and the settings it must be given;
- Needs `settings`: The shape's settings, e.g. {"outer_diameter": 200, "bolt_count": 8, "pitch_diameter": 160, "hole_diameter": 18, "bore": 100}.
- Optional: `layer`, `color`, `centreline_layer`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON. Drawing: {"shape", "created", "failed", "handles", "layers_created", "elapsed_seconds", ...} as autocad_batch_draw reports. With dry_run: {"shape", "operations": [...], "entity_count"}.`

**Limits and versions.**
- An unknown shape name lists every shape there is.
- A missing setting is named; so is a setting the shape does not take, with the full list of what it does take.
- Dimensions that cannot make the shape are refused with the reason and the limit — a fillet bigger than half the side, a slot no longer than it is wide, a cone that opens past a full circle.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E1, E9, E10, W3, AH1, AH2, AI14).

### `autocad_set_ucs`

**What it does.** Set the drawing's UCS: back to world, onto a saved one, or onto a wall or grid.
What the modeller sees: the UCS icon moves and turns, and from then on they type coordinates in the new system. This server still takes world coordinates everywhere — pass coords='ucs' on a tool that offers it, or convert with autocad_convert_points. One undo step. The UCS is saved with the drawing, so it stays set after the call; go back with mode='world'.

**The problem it solves.**
- "put the origin on grid A1 and turn it to the wall" — mode='3point' with three picked points.
- A drawing arrives with a rotated UCS and you want world coordinates back: mode='world'.
- *Not for:* you only need to convert a few points (autocad_convert_points leaves the drawing alone).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put the origin on grid A1 and turn it to the wall"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `mode`: 'world' goes back to the World Coordinate System. 'named' makes a saved UCS current. 'origin' moves to a point and optionally turns by an angle.
- Optional: `name`, `origin`, `rotation`, `point_on_x`, `point_on_y`, `handle`, `save_as`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"set": str, "saved_as": str | null, "ucs": {...as autocad_get_ucs...}}`

**Limits and versions.**
- mode='named' with a name the drawing does not have lists what it has.
- mode='3point' with three points in a line is refused: they define no plane.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D5, D6, E13, AO7, AI3).

### `autocad_super_hatch`

**What it does.** Fill a closed outline with a block, an image, an xref or a wipeout repeated like a hatch (SUPERHATCH).
Paving, cladding panels, a tiled ceiling, a grating: any block, laid in a grid from an origin, turned to an angle, and clipped to the outline the way XCLIP clips. As Express Tools offers, the tile can instead be an image file, an xref (attached from its .dwg if need be) or a wipeout. The result is one block reference: move, copy or erase it as one, and one Ctrl+Z takes it away. The tiles sit on layer 0, ByBlock, so the reference's layer and colour are what shows. One undo step.

**The problem it solves.**
- "fill the terrace outline with the 600 x 300 paver block" — boundary, block='PAVER'.
- "super hatch the ceiling with the 600 tile set out from the room centre" — origin at the centre.
- "lay the grating panels at 45 degrees in this pit".
- "fill the plaza with this stone photo, 600 wide" — image='C:/Textures/stone.jpg', image_size=[600].
- *Not for:* a normal hatch pattern does it - autocad_add_hatch, or make the pattern with autocad_create_hatch_pattern.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"fill the terrace outline with the 600 x 300 paver block"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `boundary`: The closed outline to fill (polyline, circle, ellipse or spline), drawn flat in plan.
- Optional: `block`, `spacing`, `origin`, `angle`, `scale`, `image`, `image_size`, `xref`, `wipeout`, `name`, and 3 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "block": str, "tile": str, "tile_kind": "block" | "image" | "xref" | "wipeout", "tiles": int, "spacing": [float, float], "boundary": str, "tile_block_made": bool, "xref_attached": bool, "verified" ...`

**Limits and versions.**
- An open, tilted or non-curve outline is refused before anything is made.
- A block that is not in the drawing points at autocad_list_blocks.
- More than 10,000 tiles (2,000 image tiles) is refused: make the spacing or scale bigger.
- The plug-in does part of the work (`super_hatch`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows H10, I6, BD1, BD6, AH12, AH13, AH14).

### `autocad_trace_boundary`

**What it does.** Make a closed polyline (or region) from what is drawn round a point - BOUNDARY / BPOLY.
For a room or zone outline to measure its area, hatch it or label it. Done by the Heron plug-in with AutoCAD's own boundary tracer (Editor.TraceBoundary). It never types -BOUNDARY or BPOLY: on a big plan those hung AutoCAD for over 100 seconds. The trace is kept small: with a window AutoCAD zooms to it first and the objects in it are counted, and over most_objects nothing is traced. Heron waits at most timeout seconds. One undo step. Returns the outline's handle and area.

**The problem it solves.**
- "make a boundary round the plant room so I can get its area" — point inside, window round the room.
- "draw a closed outline of this office for the hatch".
- "BPOLY round the point 12500,8000".
- *Not for:* you have the corners - autocad_draw_polyline or autocad_draw_rectangle draw it straight.
- *Not for:* you only want the area of a closed polyline that is already there - autocad_polyline_info gives it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make a boundary round the plant room so I can get its area"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `point_inside`: A point inside the room or zone, [x, y] (or [x, y, z]). Like picking inside it at BOUNDARY's prompt.
- Optional: `window`, `islands`, `make`, `most_objects`, `timeout`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": str, "area": float, "net_area": float, "islands": [{"handle", "area"}], "objects_in_view": int, "window": bool}`

**Limits and versions.**
- A point outside its window, or a window with no size, is refused before AutoCAD is asked.
- More objects in view than most_objects: nothing is traced; give a smaller window or freeze layers.
- No closed outline round the point: nothing is made, and it says so.
- The plug-in does part of the work (`trace_boundary`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AD7).


## Editing and reading objects

Move, copy, trim, fillet, change properties, and the tools that find and measure what is drawn.

### `autocad_array_entities`

**What it does.** Repeat entities in a rectangular grid or a polar ring.

**The problem it solves.**
- "5 columns of holes 200 apart, 3 rows 150 apart" -> rectangular, rows=3, columns=5, row_spacing=150, column_spacing=200.
- "8 bolts evenly round that circle" -> polar, count=8, center=the circle centre.
- "a grid of lights square to the turned wing" -> rectangular with coords="ucs", so the rows follow the wing.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"5 columns of holes 200 apart, 3 rows 150 apart"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Optional: `pattern`, `rows`, `columns`, `row_spacing`, `column_spacing`, `count`, `center`, `fill_angle`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"arrayed": int, "pattern": str, "new_handles": [str], "items_per_source": int} With coords="ucs" on a UCS that is not the world one: also "converted_from_ucs".`

**Limits and versions.**
- Rejects a rectangular array of 1x1, and a polar array with no centre, before AutoCAD is asked to build it.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI2).

### `autocad_associative_array`

**What it does.** Array objects as ONE editable array object (AutoCAD's ARRAY): along a path, in a grid or in a ring.
The array stays associative: in AutoCAD the modeller clicks it and edits the count, the spacing or the path with its grips or ARRAYEDIT, and the items follow. A path array that follows a duct or pipe line moves with the line when the line is stretched. AutoCAD takes the original objects into the array, as ARRAY does; ARRAYCLASSIC / EXPLODE give loose copies. Before it is kept, the plug-in checks where AutoCAD put the items against the asked spacing and centre;

**The problem it solves.**
- "put a hanger every 1500 along this duct line" — pattern='path', handles=[the hanger block], path=the line, spacing=1500.
- "6 sprinklers evenly along that branch pipe, end to end" — pattern='path', count=6.
- "a 4 x 6 grid of ceiling diffusers 1200 apart that I can change later" — pattern='rectangular', rows=4, columns=6, row_spacing=1200, column_spacing=1200.
- "8 bolt holes round the flange, as an array I can edit" — pattern='polar', count=8, center=the flange centre.
- *Not for:* plain loose copies are wanted (each one moved or edited on its own) — autocad_array_entities.
- *Not for:* each copy along a run must stay separate, with its own tag — autocad_place_along.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put a hanger every 1500 along this duct line"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Needs `pattern`: 'path' runs copies along a line, polyline, arc or spline; 'rectangular' makes a grid of rows and columns; 'polar' makes a ring about a centre.
- Optional: `path`, `count`, `spacing`, `align_items`, `rows`, `columns`, `row_spacing`, `column_spacing`, `center`, `fill_angle`, and 5 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "associative": bool, "pattern": str, "items": int, "base_point": [x, y, z], "sources": [str], "sources_still_loose": [str], "extents": {"min", "max"}, "verified": bool, ...the pattern's own numbers ...`

**Limits and versions.**
- A pattern given without its numbers (a path with neither count nor spacing, a ring with no centre, a 1 x 1 grid) is refused before AutoCAD is asked.
- More items than fit on the path names how many do fit.
- An array AutoCAD builds somewhere other than asked is refused, and nothing is changed.
- The plug-in does part of the work (`associative_array`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AQ1, BG7).

### `autocad_break_curve`

**What it does.** Break a line, arc, circle or polyline at a point (two pieces, no gap), or take out the part between two points.
A closed polyline broken at one point opens there; a circle needs two points and becomes an arc (the circle is erased, so Heron asks the modeller "Keep the change, or undo the whole change?": anything but Keep puts the drawing back as it was, D-136). Pieces are the object itself plus copies of it, so layer, colour and data stay. One undo step.

**The problem it solves.**
- "split that pipe at the tee so I can put it on another layer" -> point at the tee.
- "break this line at a point" / "cut the polyline in two here".
- "take 300 out of that line either side of the door" -> point and second_point.
- *Not for:* the gap is round blocks sitting on the line - use autocad_break_at_blocks; a dimension crosses it - use autocad_break_dimensions; or you want it shorter at an end - use autocad_trim_extend.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"split that pipe at the tee so I can put it on another layer"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The line, arc, circle or polyline to break.
- Needs `point`: Where to break it, as [x, y]; the nearest place on the object is used.
- Optional: `second_point`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle", "new_handles"?, "replaced_by"?, "pieces": n, "at": [[x, y], ...]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA9, BC5).

### `autocad_copy_entities`

**What it does.** Copy entities to a new position, optionally repeating in a row.

**The problem it solves.**
- "put a copy 600 below" -> displacement=[0, -600].
- "space 5 of them 1200 apart along X" -> displacement=[1200, 0], count=5.
- *Not for:* you want a grid or a ring — use autocad_array_entities.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put a copy 600 below"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Needs `displacement`: Offset of the copy from the original, as [dx, dy], e.g. [0, -600] to place it 600 units below.
- Optional: `count`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"copied": int, "source_count": int, "count": int, "new_handles": [str]} With coords="ucs" on a UCS that is not the world one: also "converted_from_ucs".`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AC15).

### `autocad_delete_entities`

**What it does.** Delete entities from the drawing.
This removes geometry. The whole call lands as one undo step, so the user can restore it with a single Ctrl+Z in AutoCAD — but nothing else brings it back once the drawing is saved and closed. Confirm what will be deleted with the user before setting confirm=true. If you are unsure which entities the handles refer to, inspect them first with autocad_get_entity.

**The problem it solves.**
- The user has explicitly asked to delete specific objects.
- *Not for:* you only want to hide things — freeze the layer with autocad_set_layer_state instead.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Delete entities from the drawing."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Optional: `confirm`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"deleted": int, "handles": [str]} With confirm=false: a preview of what would be deleted, and no change to the drawing.`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows N6, N11, AX4, BC7).

### `autocad_draw_order`

**What it does.** Put objects in front of or behind the rest (send a hatch or wipeout to the back): AutoCAD's DRAWORDER.
Written to the space's draw order table (ACAD_SORTENTS), as DRAWORDER does. The objects keep their order among themselves. All must be in one space (model space or one layout). One undo step.

**The problem it solves.**
- "send the hatch behind the pipes" -> the hatch, order='back'.
- "the wipeout should hide the lines but not the text" -> the wipeout order='above' a line, or the text order='front'.
- "bring the duct above the grid" -> order='above', reference=the grid line.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"send the hatch behind the pipes"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Needs `order`: 'front' (on top of everything), 'back' (behind everything), 'above' or 'under' the 'reference' object.
- Optional: `reference`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"moved": n, "order", "reference"?, "handles"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA14).

### `autocad_edit_spline`

**What it does.** Move, add or take away the fit points of a spline that is already drawn.
SPLINEDIT's Fit data: the spline keeps its handle, layer and end tangents and is refitted through the new points. Done by Heron's plug-in, which checks the points it ends with against the ones asked for; anything else and nothing is changed. One undo step.

**The problem it solves.**
- "move the third point of that duct spline to 4200,1800" -> edits=[{"move": 2, "to": [4200, 1800]}].
- "add a point between points 1 and 2 so the curve clears the column" -> {"insert": 2, "point": [...]}.
- "take out the kink at point 4" -> {"remove": 4}.
- *Not for:* the spline was drawn by control points - it has no fit points; redraw it with autocad_draw_spline.
- *Not for:* the whole curve moves - autocad_move_entities.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"move the third point of that duct spline to 4200,1800"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The spline to change.
- Needs `edits`: The changes, in order. Each is one of: {"move": 2, "to": [x, y]} - fit point 2 goes to that place;
- Optional: `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"edited": true, "handle": str, "fit_points_before": int, "fit_points": int, "closed": bool, "points": [[x, y, z]], "before_after": [{"handle", "property", "from", "to"}]}`

**Limits and versions.**
- A point number off the end, two points in a row at one place, or too few points left are refused before anything is changed, naming the edit.
- A spline with no fit points (drawn by control points) is refused.
- Without the plug-in it is refused before anything is read.
- The plug-in does part of the work (`edit_spline_fit_points`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI12, AI13).

### `autocad_edit_vertex`

**What it does.** Move one vertex of a polyline or one end of a line; add or remove a polyline vertex.
An arc next to a moved vertex stays an arc (its bulge is kept, as when you drag a grip). Removing a vertex between two arcs makes them one straight segment, and says so. One undo step.

**The problem it solves.**
- "that box is drawn 200 too tall, pull its top corners down" -> operation='move' on each top vertex, displacement=[0, -200] (or autocad_stretch for both at once).
- "move the end of that line to the column centre" -> vertex=1, to_point=the centre.
- "put a kink in the cable tray at x=4500" -> operation='add'.
- *Not for:* the whole object should move - use autocad_move_entities; or several vertices move together - use autocad_stretch.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"that box is drawn 200 too tall, pull its top corners down"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The polyline or line to change.
- Optional: `operation`, `vertex`, `near`, `to_point`, `displacement`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle", "operation", "vertex", "from"?, "to"?, "vertex_count", "arc_straightened"?}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA11).

### `autocad_explode`

**What it does.** Explode blocks, polylines and other compound objects into the pieces they are made of.
The pieces are new objects; the original is erased, so Heron asks the modeller "Keep the change, or undo the whole change?": anything but Keep puts the drawing back as it was (D-136). A block with attributes is skipped unless allow_attribute_loss is true (exploded, AutoCAD shows each attribute's tag, not its value). One undo step.

**The problem it solves.**
- "explode that imported block so I can fix one line in it".
- "break that polyline into separate lines and arcs".
- *Not for:* you want to change one segment's shape - use autocad_edit_vertex or autocad_break_curve, which keep it one object. Parts should stay blocks (drafting rule 2).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"explode that imported block so I can fix one line in it"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Optional: `allow_attribute_loss`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"exploded": n, "objects": [{"handle", "type", "new_handles", "attributes"?}], "skipped": [{"handle", "reason"}], "failed": [...]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA13, BC4).

### `autocad_fillet_chamfer`

**What it does.** Round a corner with an arc (fillet) or cut it straight (chamfer): two objects, or a polyline's corners.
Two lines: each is trimmed or extended to the arc's tangent point (or the chamfer's end), and the new arc or line takes the first line's layer, colour and linetype. A line and an arc, two arcs, or the ends of open polylines are met the same way (the arc is run on round its circle where it has to be; a polyline keeps all but its end segment and stays one polyline). AutoCAD's own CHAMFER takes straight objects only, so a chamfer to an arc is measured along the arc, from the corner (D-144).

**The problem it solves.**
- "put a 150 radius on that duct corner" -> operation='fillet', the two lines, radius=150.
- "make those two lines meet in a clean corner" -> operation='fillet', radius=0.
- "round all the corners of the plinth outline at 25" -> one polyline, radius=25.
- "chamfer that corner 50 by 30" -> operation='chamfer', distance=50, distance2=30.
- *Not for:* the corner is a 3D solid's edge - use autocad_fillet_solid_edges or autocad_chamfer_solid_edges.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put a 150 radius on that duct corner"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `operation`: 'fillet' rounds the corner with an arc; 'chamfer' cuts it with a straight line.
- Needs `handles`: Two objects that make a corner (they need not touch): lines, arcs, or open polylines (a polyline gives its end), in any mix.
- Optional: `radius`, `distance`, `distance2`, `angle`, `vertices`, `keep_points`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: two lines: {"operation", "lines": [h1, h2], "arc" | "chamfer_line": handle | null, "corner", "tangent_points"?, "distances"?};`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA6, BH5).

### `autocad_get_entity`

**What it does.** Read every available property of one entity, including its extents.

**The problem it solves.**
- You have a handle and need its exact coordinates.
- *Not for:* you want many entities (use autocad_list_entities).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"Read every available property of one entity, including its extents."*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `handle`: The entity's handle, e.g. '1A4'. Handles come from autocad_list_entities, autocad_get_selection, or the tool that created the entity.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON with the common properties (handle, type, layer, color, linetype), the type-specific geometry (for a circle: center, radius, area; for text: text, height, rotation_degrees;`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AW11, AI12, AL1).

### `autocad_get_extents`

**What it does.** Find the bounding box of the drawing's geometry.
Use this to size a sheet, place a title block clear of the drawing, or work out where to put new geometry relative to what already exists. One layer's objects are measured by Heron's plug-in inside AutoCAD in one go; with an older plug-in they are measured over COM, slower, with the same answer.

**The problem it solves.**
- "how big is this drawing" before choosing a sheet size or a viewport scale.
- Something plots tiny: a stray object far from the rest shows up here.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"how big is this drawing"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `layer`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"min": [x, y, z], "max": [x, y, z], "width": float, "height": float, "center": [x, y], "units": str, "entity_count": int}`

**Limits and versions.**
- Returns an empty-drawing error when there is no geometry to measure, rather than the meaningless extents AutoCAD reports for a blank file.
- A layer holding only rays or construction lines has no extents either, and says so.
- Uses the plug-in for speed when it can (from plug-in 1.8.0); otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AS4, AS5, AM1).

### `autocad_group`

**What it does.** Make a named group, add or remove objects, or ungroup (the objects stay). AutoCAD's GROUP and UNGROUP.
A group is a set of objects picked together; unlike a block, each stays its own object on its own layer. One undo step.

**The problem it solves.**
- "group the pump, its valves and its base so I can move them together" -> operation='make', name='PUMP-01'.
- "ungroup that" -> operation='ungroup', handles=[one of its objects].
- "add the strainer to the pump group" -> operation='add'.
- *Not for:* the set is a repeated part - make it a block with autocad_make_block (drafting rule 2).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"group the pump, its valves and its base so I can move them together"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `operation`: 'make' a named group from the objects; 'ungroup' (the group goes, its objects stay); 'add' objects to a group; 'remove' objects from it.
- Optional: `name`, `handles`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: make: {"made", "members"}; add / remove: {"group", "added" | "removed", "members", "not_in_group"?}; ungroup: {"ungrouped": [names], "objects_kept": n}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA17).

### `autocad_hyperlinks`

**What it does.** Link objects to a file, a data sheet or a web page with a hyperlink, or take the link off (HYPERLINK).
In AutoCAD, Ctrl+click on the object opens the link: a supplier's data sheet on a piece of equipment, the O&M manual, a detail drawing, a web page. One link per object, as AutoCAD's own HYPERLINK command keeps: 'set' replaces the link an object had. The answer gives each object's link before and after. One undo step.

**The problem it solves.**
- "link the AHU block to its data sheet" — handles=[the block], url='C:\\Project\\Submittals\\AHU-01.pdf', description='AHU-01 data sheet'.
- "put the manufacturer's web page on all the fan coil units" — the FCU handles, url='https://...'.
- "take the old links off these" — action='remove'.
- *Not for:* you only want to see the links — autocad_list_hyperlinks.
- *Not for:* the text should show on the drawing — autocad_add_label.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"link the AHU block to its data sheet"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Optional: `action`, `url`, `description`, `location`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"action": str, "changed": int, "handles": [str], "objects": [{"handle", "type", "before": [link], "after": [link]}], "failed"?: [{"handle", "reason"}]}`

**Limits and versions.**
- 'set' with neither a url nor a location is refused before anything changes.
- An object that refuses (a locked layer) is listed under "failed"; the rest are still done.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AQ8).

### `autocad_join_curves`

**What it does.** Join lines, arcs and polylines that meet end to end into one object: AutoCAD's JOIN.
Lines in one straight line become one line; arcs of one circle one arc; anything else one polyline, closed when the run comes back to its start. Vertices inside a polyline are kept. The others are erased, so Heron asks the modeller "Keep the change, or undo the whole change?": anything but Keep puts the drawing back as it was (D-136). A branch, a gap or a closed piece is refused, saying where. One undo step.

**The problem it solves.**
- "make that pipe run one polyline so I can measure it" -> all its lines and arcs.
- "those two lines are one wall, join them" -> both lines.
- "close up the room outline" -> its four lines (comes back closed).
- *Not for:* you only need the total length - use autocad_total_length; or the pieces branch - join each branch.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make that pipe run one polyline so I can measure it"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The lines, arcs and open polylines to join end to end, in any order and direction. The first one gives the result its layer, colour and linetype.
- Optional: `gap`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"joined": n, "handle", "kind": "line" | "arc" | "polyline", "closed", "order": [handles], "removed": [handles], "vertex_count"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA10, BC1, BC6, BC8, BC9, BG1).

### `autocad_lengthen`

**What it does.** Make a line, an arc or an open polyline longer or shorter at one end: AutoCAD's LENGTHEN Delta, Total and Percent.
The end runs on along its own line (a straight end) or round its own circle (an arc end, never to a full circle); a shorter object is cut back along its own shape, over as many segments as it takes, arcs kept as arcs. The object keeps its handle, layer and look. Works in plan on flat objects. An object on a locked layer, a closed polyline, a circle and a change that would leave nothing are refused. One undo step.

**The problem it solves.**
- "make that pipe 500 longer at the north end" -> mode='delta', value=500, points=[a point near the north end].
- "cut that duct back by 150" -> mode='delta', value=-150.
- "make those branch lines exactly 2400 long" -> mode='total', value=2400, the branch handles.
- "lengthen the arc by 25 percent" -> mode='percent', value=125.
- *Not for:* the end has to reach a wall or another line - use autocad_trim_extend; or to a point - use autocad_edit_vertex.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make that pipe 500 longer at the north end"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The lines, arcs or open polylines to make longer or shorter.
- Needs `mode`: 'delta' adds 'value' to the length (a negative value shortens it); 'total' makes the whole object 'value' long;
- Needs `value`: The distance, the total length or the percent, as 'mode' says.
- Optional: `end`, `points`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"mode", "done": n, "objects": [{"handle", "end", "was", "now", "changed_by"}], "failed": [{"handle", "reason"}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows BH1, BH2, BH3, BH4).

### `autocad_list_entities`

**What it does.** List entities in the active drawing, filtered by type, layer or colour.
Filtering happens inside AutoCAD rather than in Python, so this stays fast on drawings with tens of thousands of entities. On an unfamiliar drawing, call it once with summary_only=true to learn what is there, then again with filters to get the entities you actually need. The summary is counted by Heron's plug-in inside AutoCAD in one go; with an older plug-in it is counted over COM, slower, with the same answer.

**The problem it solves.**
- "what's in this drawing?" -> summary_only=true.
- "list every circle on layer HOLES" -> entity_type="circle", layer="HOLES".
- *Not for:* you already have a handle (use autocad_get_entity).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what's in this drawing?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `entity_type`, `layer`, `block_name`, `color`, `summary_only`, `include_geometry`, `limit`, `offset`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON. With summary_only=false: { "total_matching": int, # matches before paging "count": int, # entities in this response "offset": int, "has_more": bool, "next_offset": int | null, "filters": {...}, # what was actually applied "entities" ...`

**Limits and versions.**
- Uses the plug-in for speed when it can (from plug-in 1.8.0); otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows A31, AF24, AS1, AS3, AN13, AL1).

### `autocad_list_groups`

**What it does.** List the drawing's groups with their members.
Unnamed groups (AutoCAD names them *A1, *A2 ...) are listed too, marked.

**The problem it solves.**
- "what groups are in this drawing?"
- "is that pump in a group?" -> handle=the pump.
- *Not for:* you want blocks - use autocad_list_blocks.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what groups are in this drawing?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `name`, `handle`, `most`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count", "groups": [{"name", "unnamed", "member_count", "members": [{"handle", "type", "layer"}], "members_more"?}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA17).

### `autocad_list_hyperlinks`

**What it does.** List the hyperlinks on objects: on the ones given, or on every linked object in the drawing.
Each object's handle, type and layer, with its link: the address or file it opens, the hover text and the named view. Use it to check the links before an issue, or to find which equipment still has no data sheet. Reads only.

**The problem it solves.**
- "which objects have hyperlinks in this drawing?" — no handles.
- "what does this fan link to?" — handles=[the fan].
- *Not for:* you want to add or remove one — autocad_hyperlinks.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"which objects have hyperlinks in this drawing?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `handles`, `limit`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count": int, "objects": [{"handle", "type", "layer", "links": [{"url", "description", "location"}]}], "truncated"?: bool}`

**Limits and versions.**
- A handle that is not in the drawing points at autocad_list_entities.
- The whole-drawing search covers model space and every layout, not objects nested inside other objects.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AQ9).

### `autocad_match_properties`

**What it does.** Copy layer, colour, linetype, lineweight, transparency (and text or dimension style) from one object to others.
AutoCAD's MATCHPROP, with the properties named. Only values that differ are written; a property a target does not have (a text style on a line) is skipped and said. An object that already matches opens no undo step. One undo step.

**The problem it solves.**
- "make these pipes look like that one" -> source=that pipe, the pipes as handles.
- "put the new text in the same style as the old notes" -> properties=['layer', 'text_style'].
- "these dimensions should match that one" -> properties=['all'].
- *Not for:* you know the values - use autocad_modify_entity.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make these pipes look like that one"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `source`: The handle of the object to copy the properties from.
- Needs `handles`: The objects to give those properties to.
- Optional: `properties`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"matched": n, "handles", "properties", "before_after": [{"handle", "property", "from", "to"}], "already": [handles], "skipped": [{"handle", "property"}], "failed": [...]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA15).

### `autocad_measure`

**What it does.** Measure a distance between points, or total lengths and areas.
Three modes, picked by which arguments you pass: - point1 + point2: straight-line distance and bearing between them. - handles: summed length and area of those specific entities. - layer: summed length and area of everything on that layer.

**The problem it solves.**
- "how far is it from 0,0 to 3000,4000?" -> point1/point2.
- "total length of everything on layer PIPE-CWS" -> layer.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"how far is it from 0,0 to 3000,4000?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `point1`, `point2`, `handles`, `layer`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON. Point-to-point mode: {"mode": "distance", "distance": float, "dx": float, "dy": float, "angle_degrees": float, "units": str} Totalling mode: {"mode": "totals", "entity_count": int, "total_length": float, "total_area": float, "units" ...`

**Limits and versions.**
- Returns an error naming the three modes if no usable combination of arguments is given.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA7, BB4, BB5, AO9, BH3).

### `autocad_mirror_entities`

**What it does.** Mirror entities across a line defined by two points.

**The problem it solves.**
- "mirror this about the vertical centreline at x=5000" -> axis_point1=[5000,0], axis_point2=[5000,1000].

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"mirror this about the vertical centreline at x=5000"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Needs `axis_point1`: First point on the mirror line, as [x, y].
- Needs `axis_point2`: Second point on the mirror line, as [x, y].
- Optional: `delete_original`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"mirrored": int, "new_handles": [str], "originals_deleted": bool}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_modify_entity`

**What it does.** Change properties of existing entities: layer, colour, linetype, lineweight, transparency, text.
Only the arguments you pass are changed; everything else is left alone. Properties that do not apply to an entity's type are skipped for that entity and reported, so a mixed selection does not fail as a whole.

**The problem it solves.**
- "put those on layer A-WALL and make them red" -> layer="A-WALL", color="red".
- "fix that label to say ROOM 12" -> text="ROOM 12".
- "make the existing services 0.18 lineweight and 50% see-through" -> lineweight=0.18, transparency=50.
- *Not for:* the values should come from another object - use autocad_match_properties.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put those on layer A-WALL and make them red"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Optional: `layer`, `color`, `linetype`, `text`, `height`, `radius`, `closed`, `lineweight`, `transparency`, `layer_lock_override`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"modified": int, "handles": [str], "applied": [str], "before_after": [{"handle", "property", "from", "to"}] (first 50), "already": [str], "skipped": [{"handle": str, "type": str, "property": str}]}`

**Limits and versions.**
- Reports a locked layer explicitly, and can work around it when layer_lock_override is true.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T4, T6, AA16, AL6).

### `autocad_move_entities`

**What it does.** Move entities by a displacement, or from one point to another.

**The problem it solves.**
- "shift those 3 m to the right" -> displacement=[3000, 0] in a millimetre drawing.
- "move it from the corner to the centre" -> from_point and to_point.
- "slide it 600 along the grid" on a turned UCS -> displacement=[600, 0], coords="ucs".

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"shift those 3 m to the right"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Optional: `displacement`, `from_point`, `to_point`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"moved": int, "handles": [str], "displacement": [dx, dy, dz]} Plus "failed" listing any entity that refused, with the reason. The displacement reported is the world one; with coords="ucs" also "converted_from_ucs".`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI2).

### `autocad_offset_entities`

**What it does.** Create parallel copies of lines, polylines, arcs and circles.
This is how wall thicknesses, kerbs, setbacks and pipe runs get drawn from a single centreline.

**The problem it solves.**
- "give me the inside face of that wall, 200 in" -> distance=200, side towards the point you name.
- "a kerb line 150 either side" -> both_sides=true.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"give me the inside face of that wall, 200 in"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Needs `distance`: Offset distance. Positive offsets outward or to the left of the direction of travel; negative offsets the other way.
- Optional: `both_sides`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"offset": int, "new_handles": [str], "distance": float}`

**Limits and versions.**
- Text, blocks, hatches and dimensions cannot be offset; each is reported in "failed" with its type rather than aborting the call.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_overkill`

**What it does.** Find and delete doubled and overlapping lines, arcs and circles - AutoCAD's OVERKILL.
An import from Revit or IFC often draws every wall line twice, or in pieces lying over each other. This finds them and says, by handle, what would go and why: an exact copy, a line lying inside a longer one, lines overlapping on one straight line (merged into the oldest one, which is stretched to cover them), arcs on one circle, zero-length lines, a copy of a polyline, a loose line lying on a polyline. The oldest object (lowest handle) is always the one kept.

**The problem it solves.**
- "the architect's import has doubled lines, clean them up" — first call lists them, then confirm=true with its plan_id.
- "run overkill on the A-WALL layer" — layers=['A-WALL'].
- "delete duplicate lines after the Revit export".
- "merge the overlapping duct lines into one".
- *Not for:* you want to delete objects you already picked - autocad_delete_entities.
- *Not for:* you want overlapping objects listed for a check - autocad_checklist's overlap check reports without changing.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"the architect's import has doubled lines, clean them up"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `layers`, `handles`, `tolerance`, `ignore_layer`, `join_end_to_end`, `space`, `confirm`, `plan_id`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"confirmed": bool, "plan_id": str, "looked_at": int, "erase_count": int, "stretch_count": int, "erase": [{"handle", "type", "reason", "kept"}], "change": [{"handle", "type", "start", "end" | "start_angle", "end_angle", "was" ...`

**Limits and versions.**
- Over 20,000 curves (or 200,000 objects in the space) is refused: give layers or handles, or type OVERKILL in AutoCAD.
- A locked layer among the objects to change is named, and nothing is changed.
- confirm=true without the listing's plan_id, or after the drawing changed, does nothing and says to list again.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AD1).

### `autocad_polyline_info`

**What it does.** Every vertex and segment of a run: lengths, arcs (centre, radius, sweep), total, area, centroid.
The centroid (closed shapes) is the place for a room or zone tag.

**The problem it solves.**
- "is that slot one object, and what is its perimeter" -> segment count, which are arcs, radii, total length.
- Checking a flat pattern: each arc must be as long as the girth it rolls onto (pi x diameter).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"is that slot one object, and what is its perimeter"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `handle`: A line, polyline, arc or circle.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"total_length", "area", "centroid", "segments": [...], "vertices": [...]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows W7, AA8, BH4).

### `autocad_rotate_entities`

**What it does.** Rotate entities about a base point.

**The problem it solves.**
- "turn that 90 degrees about the origin" -> base_point=[0,0], angle=90.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"turn that 90 degrees about the origin"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Needs `base_point`: Point to rotate about, as [x, y].
- Needs `angle`: Rotation in DEGREES. Positive is counter-clockwise, negative is clockwise.
- Optional: `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"rotated": int, "handles": [str], "angle_degrees": float, "base_point": [x, y]} base_point and angle_degrees are as given; with coords="ucs" also "converted_from_ucs".`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI2).

### `autocad_scale_entities`

**What it does.** Scale entities uniformly about a base point.

**The problem it solves.**
- "this detail came in at 1:10, make it full size" -> scale_factor=10 about a base point you can check afterwards.
- *Not for:* you only want the plot bigger - that is the viewport scale, autocad_add_viewport.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"this detail came in at 1:10, make it full size"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Handles of the entities to act on, e.g. ['1A4', '1A5']. Get them from autocad_list_entities, autocad_get_selection, or from the tool that created the ...
- Needs `base_point`: The point that stays fixed while everything scales around it, as [x, y].
- Needs `factor`: Scale factor: 2 doubles the size, 0.5 halves it. Must be greater than zero.
- Optional: `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"scaled": int, "handles": [str], "factor": float, "base_point": [x, y]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_select_connected`

**What it does.** Find a whole run: every line, polyline and arc joined end to end with the seed.
Returns its handles, total length and open ends (where the run stops), e.g. one pipe or cable route for a take-off or a check.

**The problem it solves.**
- "select that whole pipe run" from one line you can point at, then total it or move it as one.
- *Not for:* the run is all on its own layer - a layer filter is simpler.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"select that whole pipe run"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `handle`: Any line, polyline or arc of the run.
- Optional: `tolerance`, `same_layer`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"handles", "count", "total_length", "open_ends"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_stretch`

**What it does.** Stretch objects: the vertices and line ends inside a window move, the rest stay. AutoCAD's STRETCH.
Lines and polylines are reshaped (arcs in a polyline keep their bulge). A circle, text, block or point moves whole when its centre or insertion point is inside; an arc, hatch, dimension or anything else moves only when it lies wholly inside, and is otherwise left and listed. One undo step.

**The problem it solves.**
- "that box is drawn 200 too tall" -> a window round its top edge, displacement=[0, -200].
- "stretch the plant room 600 east, walls, door and all" -> the walls and the door, a window round the east side.
- *Not for:* one vertex moves alone - use autocad_edit_vertex; or everything moves - use autocad_move_entities.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"that box is drawn 200 too tall"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The objects to stretch; only their points inside the window move.
- Needs `corner1`: One corner of the stretch window, as [x, y].
- Needs `corner2`: The opposite corner of the window, as [x, y].
- Optional: `displacement`, `from_point`, `to_point`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"reshaped": [{"handle", "vertices_moved"}], "moved_whole": [handles], "untouched": [handles], "skipped": [{"handle", "reason"}], "displacement"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA12).

### `autocad_tidy_entities`

**What it does.** Clean up imported geometry: ByLayer overrides, one flat level, no leftovers.
The second half of turning an export into a shop drawing. An IFC or Revit drawing comes in with colour, linetype and lineweight set on every single object, so changing a layer appears to do nothing; with a real Z on work that should be flat, so trim and hatch misbehave; and with zero-length rubbish nobody can select. **dry_run is on by default.** Read the counts, then run again with dry_run=false. One undo step.

**The problem it solves.**
- "I changed the layer colour and nothing happened" — color_bylayer on its own.
- "the plan will not hatch" — flatten_z=0.
- After autocad_remap_layers, to finish the job.
- *Not for:* the overrides are deliberate; this clears them all within the scope you give, so narrow it with layer or entity_type.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"I changed the layer colour and nothing happened"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `color_bylayer`, `linetype_bylayer`, `lineweight_bylayer`, `flatten_z`, `zero_thickness`, `off_layer_0`, `delete_empty`, `layer`, `entity_type`, `handles`, and 1 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "dry_run": bool, "read": int, "counts": {"color_bylayer": 1240, "flatten_z": 980, ...}, "done": {...}, "failed": [{"handle", "do", "reason"}], "deleted": int, "sample": [{...}] }`

**Limits and versions.**
- A locked or frozen layer is reported per object in "failed"; the rest still lands.
- Nothing is deleted unless delete_empty is passed, and never on a dry run.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D26).

### `autocad_total_length`

**What it does.** Total length (and area of closed shapes) for a run take-off: pipe, duct, cable.
Lengths are in drawing units (check autocad_status). Splines and ellipses are measured from their definition.

**The problem it solves.**
- "how many metres of DN50 pipe on this layer" -> layer="M-PIPE-DN50".
- Cable, duct, kerb, skirting - anything bought by the metre.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"how many metres of DN50 pipe on this layer"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `entity_type`, `layer`, `group_by`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"total_length", "total_area", "rows": [{layer|type, count, length, area, unmeasured}]}`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **PARTLY**: rows A26 passed in AutoCAD 2027; the rest are NOT RUN (rows A26, BB1, BB2, BB3, BB10).

### `autocad_trim_extend`

**What it does.** Trim objects back to cutting edges, or extend them to boundaries: AutoCAD's TRIM and EXTEND.
Works in plan on lines, arcs and polylines (a polyline arc is cut on its arc; a closed polyline cut twice opens there; a circle becomes an arc, and the circle is erased, so Heron asks the modeller "Keep the change, or undo the whole change?": anything but Keep puts the drawing back as it was, D-136). Edges count as drawn, not as if they ran on (EDGEMODE 0). Pieces left after a trim are the object itself plus copies of it, so layer, colour and data stay.

**The problem it solves.**
- "trim the pipe back to the wall" -> operation='trim', edges=[the wall line], handles=[the pipe], points=[a point on the bit past the wall].
- "cut the duct between those two grid lines" -> trim with both grid lines as edges and a point between them.
- "extend those branch lines to the main" -> operation='extend', edges=[the main], handles=[the branches], no points.
- *Not for:* you want a gap round a valve or symbol on the line - use autocad_break_at_blocks; or a gap between two points - use autocad_break_curve.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"trim the pipe back to the wall"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `operation`: 'trim' cuts an object back to the cutting edges, removing the part you point at; 'extend' runs an object's end on until it meets a boundary.
- Needs `handles`: The lines, arcs, circles or polylines to trim or extend (a circle can be trimmed only).
- Needs `edges`: The cutting edges (trim) or boundaries (extend): lines, arcs, circles or polylines, e.g. the wall line.
- Optional: `points`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"operation", "done": n, "objects": [{"handle", "new_handles"?, "cut_away" | "added", "ends"?}], "failed": [{"handle", "reason"}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AA1, AA4, BC5, BC13).


## Text, labels and tables

Text, leaders, labels, tags, schedules as tables, text styles and annotation scales.

### `autocad_add_field_label`

**What it does.** A length or area label that stays right: an AutoCAD field linked to the object(s).
Edit the run and the label updates on the next regen. Several objects give their sum.

**The problem it solves.**
- "label that duct with its length, and keep it right if I stretch it" -> handles=[the duct], kind="length".
- *Not for:* a fixed number is fine - autocad_label_segment_lengths does a whole run in one call.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"label that duct with its length, and keep it right if I stretch it"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The object(s) to measure; several are added up.
- Optional: `prop`, `position`, `block_handle`, `tag`, `prefix`, `suffix`, `precision`, `factor`, `height`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle", "value" (as shown now), "field_code"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_add_label`

**What it does.** Place a label that points at something: text plus a leader with an arrow.
Use for every label on a drawing. Default is Ajmal's TLD style: MTEXT, and a LEADER that ends under the text. 'L' gives a square leg, 'angled' a straight one; pick 'angled' when several labels sit in a column. kind='mleader' gives one MULTILEADER instead. Put the text where it is easy to read, clear of the drawing; the arrow goes on the object.

**The problem it solves.**
- "point a label at that bracket saying 100x100x10 ANGLE".
- *Not for:* one note serves several parts - one autocad_add_multileader with three arrows reads better than three labels.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"point a label at that bracket saying 100x100x10 ANGLE"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `text`: Label text. Use \P for a new line (MTEXT).
- Needs `arrow`: Arrow point [x, y]: what the label points at.
- Needs `position`: Top-left corner of the text [x, y].
- Needs `height`: Text height in drawing units.
- Optional: `kind`, `shape`, `extension`, `width`, `text_align`, `mask`, `layer`, `color`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "kind", "handle" (text or mleader), "handles", "points"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PASS** in AutoCAD 2027 (rows A24).

### `autocad_add_mtext`

**What it does.** Place a wrapping block of multiline text.
Use this for general notes, specification blocks and any text longer than a few words.

**The problem it solves.**
- "put these four notes in a 3000 wide block of text".
- *Not for:* it is one short line - autocad_add_text is lighter.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put these four notes in a 3000 wide block of text"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `text`: Text content. Use \P for a hard line break, e.g. 'NOTE 1\PNOTE 2'.
- Needs `position`: Top-left insertion point as [x, y].
- Needs `width`: Wrapping width of the text box in drawing units.
- Optional: `height`, `rotation`, `layer`, `color`, `space`, `coords`, `annotative`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "mtext", "layer": str, "height": float, "width": float} With annotative: also "annotative", "annotation_scales" and "paper_height".`

**Limits and versions.**
- The plug-in does part of the work (`set_annotation_scales`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_add_multileader`

**What it does.** One note with as many arrows as it needs: a real MULTILEADER.
Use it when a single note serves several things — "4 No. M16 BOLTS" with an arrow to each of four holes — or for one tidy leader that follows the office multileader style. The first arrow point and the landing make the first leader line; every extra arrow point adds another leader line to the same note.

**The problem it solves.**
- "label these four holes with one note".
- "tag this pipe with our tag block on a leader" — block=.
- *Not for:* one label in the TLD house style (autocad_add_label), or a dimension (autocad_add_dimension).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"label these four holes with one note"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `landing`: Where the note sits, as [x, y]: the end of the first leader line.
- Needs `arrows`: Every point the note points at, each [x, y]. Give one for a plain leader, or several for one note serving several things — which is what a ...
- Optional: `text`, `block`, `height`, `arrow_size`, `style`, `layer`, `color`, `coords`, `annotative`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "leader_lines": int, "arrows": [[x, y]], "landing": [x, y], "not_set": [str]} With annotative: also "annotative" and "annotation_scales".`

**Limits and versions.**
- Needs text or block, and says so if neither is given.
- A style or block the drawing does not have is named; the leader is not left half-made.
- Properties a locked style refuses come back in "not_set" rather than failing the call.
- The plug-in does part of the work (`set_annotation_scales`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E16, E17, AB10, AN2, AN13).

### `autocad_add_table`

**What it does.** Put a schedule on the drawing as a real AutoCAD table, not a grid of loose text.
A table the modeller can edit, sort and restyle, with a title and headings. Text sits in the vertical middle of each cell, keeping the style's left / centre / right. Pair it with autocad_extract_attributes: read the blocks, then put the rows on the sheet. One undo step.

**The problem it solves.**
- "make a camera schedule from the CAM blocks" — autocad_extract_attributes, then this.
- "put this door schedule on the sheet".
- *Not for:* you want the data back as text or CSV (autocad_extract_attributes already does that).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make a camera schedule from the CAM blocks"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `position`: Top-left corner of the table, as [x, y]. A table grows downward from here.
- Needs `rows`: The data rows, e.g. [["CAM-01","Dome","Level 1"],["CAM-02","Bullet","Level 1"]].
- Optional: `headers`, `title`, `column_widths`, `row_height`, `text_height`, `text_style`, `style`, `layer`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "rows": int, "columns": int, "data_rows": int, "cells_written": int, "not_set": [str]}`

**Limits and versions.**
- A table style the drawing does not have is named.
- Cells AutoCAD refuses are counted and the row and column are reported; the table itself still lands.
- A text height or text style AutoCAD refuses is in "not_set" with its reason; the table keeps its style's own.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D33, E18, E19, AC13, AF10, AN8, AN9, AN13).

### `autocad_add_text`

**What it does.** Place a single line of text.
Use this for short labels, tags and callouts. For paragraphs, or text that must wrap to a width, use autocad_add_mtext.

**The problem it solves.**
- "write GROUND FLOOR at 0,5000, 200 high".
- *Not for:* the note has to wrap or carry formatting - use autocad_add_mtext.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"write GROUND FLOOR at 0,5000, 200 high"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `text`: The text to place, e.g. 'GROUND FLOOR'.
- Needs `position`: Insertion point as [x, y].
- Optional: `height`, `rotation`, `layer`, `color`, `space`, `coords`, `annotative`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "text", "layer": str, "text": str, "height": float} With annotative: also "annotative", "annotation_scales" and "paper_height" (the height on paper at the current scale).`

**Limits and versions.**
- The plug-in does part of the work (`set_annotation_scales`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB9, AI1, AI3).

### `autocad_align_text`

**What it does.** Line up labels and notes, or space them evenly (by their extents). One undo step.

**The problem it solves.**
- "tidy that column of labels so they line up left" and the leaders stop crossing.
- "space these notes evenly" -> the even-spacing mode.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"tidy that column of labels so they line up left"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Texts, mtexts or any objects to line up.
- Needs `mode`: left / right / centre: line up on X. top / bottom / middle: line up on Y. distribute_vertical / distribute_horizontal: equal spacing, first and last ...
- Optional: `reference`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"moved": n, "moves": {handle: [dx, dy]}}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T7).

### `autocad_annotation_scales`

**What it does.** Make objects annotative, add or remove their annotation scales: AutoCAD's OBJECTSCALE.
An annotative note carries one size per scale: give it 1:50 and 1:100 and it reads the same on paper in both viewports. A scale is found by name, or else by its ratio, so '1:50' finds the drawing's 1:50 whatever it is called. Done by Heron's plug-in (COM has no call for object scales), all or nothing: one object it cannot change leaves every object as it was. Objects that cannot be annotative (a line, a circle) are skipped and named. One undo step.

**The problem it solves.**
- "make these notes annotative" — annotative=true.
- "these notes need to show at 1:20 and 1:100 too" — add=['1:20','1:100'].
- "take 1:5 off these dimensions" — remove=['1:5'].
- "this detail is 1:25 and the drawing has no 1:25" — add=['1:25'], add_missing_to_drawing=true.
- *Not for:* you are adding new text or dimensions — give annotative=true on autocad_add_text, autocad_add_mtext, autocad_add_dimension, autocad_dimension_run or autocad_add_multileader.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make these notes annotative"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The text, mtext, dimensions, multileaders, hatches or blocks to change, by handle.
- Optional: `annotative`, `add`, `remove`, `add_missing_to_drawing`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"objects": [{"handle", "type", "annotative", "scales", "annotative_was", "scales_were", "paper_height"}], "scales_created": [str], "skipped": [{"handle", "why"}], "before_after": [{handle, property, from, to}]}`

**Limits and versions.**
- A removal that would leave an annotative object with no scale is refused, and nothing is changed.
- A scale the drawing has not got is refused, unless add_missing_to_drawing is true and it is written like 1:25.
- The plug-in does part of the work (`set_annotation_scales`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB9, AB11).

### `autocad_batch_labels`

**What it does.** Place many labels in one go: one trip to AutoCAD and one undo step.
Use instead of calling autocad_add_label again and again — a column of 15 labels is one call. Same TLD geometry as autocad_add_label. Every label is checked first, so a bad one stops the batch with its index and nothing is drawn. Afterwards the leaders are checked against each other and any pair that crosses is listed in "crossing" (drafting rule 4: fix those).

**The problem it solves.**
- "label all the parts of this detail in a column on the right".
- "put the 15 labels on the pole elevation at 1:25".
- *Not for:* one or two labels - autocad_add_label is enough.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"label all the parts of this detail in a column on the right"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `labels`: The labels, in column order. Each needs text, arrow [x, y] and position [x, y] (top-left, or top-right with text_align 'right').
- Optional: `height`, `kind`, `shape`, `text_align`, `extension`, `width`, `mask`, `arrow_scale`, `layer`, `color`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": n, "labels": [per-label result, in order], "crossing": [[i, j], ...], "arrow_scale": float}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PARTLY**: rows A30 passed in AutoCAD 2027; the rest are NOT RUN (rows A30, A31).

### `autocad_count_text`

**What it does.** Count text and tag values: how many DN50, how many of each camera type.

**The problem it solves.**
- "how many DN50 on this drawing" -> the tag values counted and grouped.
- *Not for:* you are counting symbols - autocad_count_blocks.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"how many DN50 on this drawing"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `source`, `tag`, `layer`, `pattern`, `normalise`, `sum_numeric`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"total", "distinct", "counts": {value: n}, "sum"?}`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows BB7, BB8, BB9).

### `autocad_create_styles`

**What it does.** Create the text, dimension, multileader and table styles a drawing needs, with real values.
A dimension style is built the way AutoCAD's own API requires: the DIM variables are set, the style is added, the style copies them off the document, and the drawing's variables are then put back — so the style holds the settings and the drawing is left as it was. Multileader and table styles have no Automation call, so Heron's plug-in makes them through AutoCAD's .NET API (D-104), after the text styles of the same call, so a style can use a text style made with it. Each comes back as AutoCAD then holds it.

**The problem it solves.**
- "make our ROMANS text style and a 1:50 dim style".
- Dimension text is the wrong size on every sheet.
- "make a multileader style for 1:50 labels" — multileader_styles=[{"name": "MEP-LABEL-50", "text_height": 2.5, "scale": "1:50", "current": true}].
- "set up a table style for the equipment schedule" — table_styles=[{"name": "SCHEDULE-50", "text_height": 2.5, "scale": "1:50"}], then autocad_add_table with style='SCHEDULE-50'.
- *Not for:* your office standards drawing already has them — autocad_import_from_drawing copies them across as they are.
- *Not for:* you want a plot style table (.ctb / .stb); AutoCAD's .NET API cannot make one. Set an existing one with autocad_page_setup.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make our ROMANS text style and a 1:50 dim style"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `text_styles`, `dim_styles`, `multileader_styles`, `table_styles`, `replace`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "text_styles": [{"name", "created", "font", "height", "current", "notes": [str]}], "dim_styles": [{"name", "created", "variables": {...}, "current", "notes": [str]}], "multileader_styles": [{"name", "created", "current" ...`

**Limits and versions.**
- A style name already in the drawing is refused unless replace=true.
- A font AutoCAD cannot find is reported against that style; the other styles are still made.
- The drawing's own DIM variables are put back even if a style fails.
- The plug-in does part of the work (`multileader_style`, `table_style`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D23, BF2, AN1, AN3, AN5, AN7, AN13, AZ1).

### `autocad_find_replace_text`

**What it does.** Find and replace across text, mtext, attributes, multileaders, dimension overrides and tables.
Use for revisions: a renamed room, a changed size, a new project name. Try dry_run first on a large drawing. One undo step.

**The problem it solves.**
- "change every REV A to REV B across the whole sheet set", including attributes and dimension overrides.
- A client renames a room or a system and it appears in thirty places.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"change every REV A to REV B across the whole sheet set"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `find`: Text (or regular expression) to find.
- Needs `replace`: Replacement. With regex, \1 refers to a group.
- Optional: `regex`, `case_sensitive`, `kinds`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"replaced": n, "hits": [{handle, kind, where, before, after}], "before_after": the first 50 as {handle, property, from, to}}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T2, T6, T7).

### `autocad_find_text`

**What it does.** Search all text, mtext and block attributes for a string.
This is the fastest way to locate something described by its label — a room name, a level marker, a drawing note, an equipment tag.

**The problem it solves.**
- "where does it say FFL on this drawing?"
- "find the block tagged D-101".

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"where does it say FFL on this drawing?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `query`: Text to search for, e.g. 'FFL' or 'ROOM 12'. Matching is case-insensitive and matches any part of the string.
- Optional: `include_attributes`, `limit`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"query": str, "count": int, "truncated": bool, "matches": [{"handle": str, "type": str, "layer": str, "text": str, "position": [x, y, z], "source": "text" | "mtext" | "attribute", "attribute_tag": str, # attribute matches only ...`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows BB6, BB10).

### `autocad_label_segment_lengths`

**What it does.** Write each segment's length at its middle, above the line and readable.
Optionally between crossings with another layer (lengths between tees and branches). The text is plain: re-run after editing the run, or use autocad_add_field_label for a live total.

**The problem it solves.**
- "write the length on every leg of that run", above the line and the right way up.
- *Not for:* the numbers must update if the run is stretched - autocad_add_field_label.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"write the length on every leg of that run"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: Lines, polylines or arcs to label.
- Needs `height`: Text height.
- Optional: `offset`, `precision`, `prefix`, `suffix`, `split_at_layer`, `factor`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"labels": n, "items": [{handle, text, position, rotation}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_list_annotation_scales`

**What it does.** The drawing's annotation scales, the current one (CANNOSCALE), and which scales objects carry.
An annotative object shows only in a viewport whose scale it carries (with ANNOALLVISIBLE off). Read this before issuing a sheet, to see that every note and dimension carries the viewport's scale. Read by Heron's plug-in (COM has no call for object scales); without the plug-in only CANNOSCALE comes back.

**The problem it solves.**
- "is this note annotative, and at which scales?"
- "which annotation scales does the drawing have?"
- "what is the current annotation scale?" — "cannoscale".
- *Not for:* you want to change an object's scales — autocad_annotation_scales; or to set the drawing's scale, DIMSCALE or LTSCALE — autocad_drawing_setup(scale=...).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"is this note annotative, and at which scales?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `handles`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"current": {"name", "paper", "drawing"}, "cannoscale": str, "scales": [{"name", "paper", "drawing"}], "anno_all_visible": bool, "objects": [{"handle", "type", "annotative": "yes"|"no"|"cannot", "scales": [str], "height" ...`

**Limits and versions.**
- The plug-in does part of the work (`annotation_scales`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB9).

### `autocad_list_styles`

**What it does.** List the drawing's text styles, dimension styles and loaded linetypes.
Read this before adding annotation so new text and dimensions match what the drawing already uses, rather than defaulting to Standard.

**The problem it solves.**
- A text or dimension style is named in a standard and you need to know whether this drawing has it.
- Before autocad_create_styles, so you do not replace one that is already right.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"List the drawing's text styles, dimension styles and loaded linetypes."*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"current_text_style": str, "current_dimension_style": str, "text_styles": [{"name": str, "font": str, "height": float, "width_factor": float}], "dimension_styles": [str], "linetypes": [str]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_number_tags`

**What it does.** Number tags in order: CAM-001, CAM-002 ... on blocks, texts, or as new text.
Sorted by rows, columns or along a run, so the numbering follows the drawing. One undo step.

**The problem it solves.**
- "number these cameras CAM-001 upwards, left to right".
- A schedule needs tags that match the drawing: number them here first, then autocad_extract_attributes for the table.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"number these cameras CAM-001 upwards, left to right"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `prefix`, `start`, `step`, `suffix`, `pad`, `handles`, `tag`, `positions`, `height`, `sort`, and 3 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"numbered": n, "assigned": [{handle, number}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_set_table_cells`

**What it does.** Change cells of a table already in the drawing, by row and column, old -> new.
For a schedule on the sheet that needs a few values corrected or a row added, without redrawing it. Only cells whose text really changes are written, in one undo step; each one's text goes in the vertical middle of its cell, keeping its left / centre / right. A cell linked to Excel or locked in AutoCAD is listed and left alone.

**The problem it solves.**
- "in the pump schedule change P-02's flow in C4 to 12.5".
- "add a row for P-05 at the bottom of the table" -> grow=true with the new row's cells.
- *Not for:* the table is linked to Excel - change the sheet, then autocad_update_table_links.
- *Not for:* making a new table - autocad_add_table or autocad_table_from_excel.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"in the pump schedule change P-02's flow in C4 to 12.5"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The table, e.g. from autocad_list_entities (type 'table') or the tool that made it.
- Needs `cells`: The cells to change, e.g. [{"cell": "B3", "value": "DN50"}, {"row": 4, "column": 2, "value": "DN65"}].
- Optional: `grow`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle", "changed": int, "unchanged": [cell], "refused": [{cell, why}], "added_rows", "added_columns", "before_after": [{handle, property, from, to}]}`

**Limits and versions.**
- A handle that is not a table, a cell given twice, or a cell outside the table without grow is refused before anything changes.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AC11, AC12, AV2).

### `autocad_table_from_excel`

**What it does.** Show an Excel range as an AutoCAD table, linked so it can be updated when the sheet changes (Data Link).
The Insert > Data Link job: a schedule kept in Excel (pumps, fans, a door schedule, a cable list) placed on the drawing as a real AutoCAD table. By default it is linked, as AutoCAD's own Data Link Manager links it, so autocad_update_table_links brings later edits in; the link is made by the Heron plug-in. When a link cannot be made, the table is filled with the sheet as it is now and the answer says "linked": false and why. Text sits in the vertical middle of each cell.

**The problem it solves.**
- "put the pump schedule from the Excel file on the sheet as a table" -> path='pumps.xlsx', space='paper'.
- "link the A1:F30 range of the fan sheet as a table, so it updates" -> cell_range='A1:F30'.
- *Not for:* the rows come from the drawing's own blocks - autocad_extract_attributes, then autocad_add_table.
- *Not for:* the table is already there and the sheet changed - autocad_update_table_links.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put the pump schedule from the Excel file on the sheet as a table"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: The .xlsx (or .csv) file: a full path, or a file name in the drawing's folder.
- Needs `position`: Top-left corner of the table, as [x, y]. The table grows downward from here.
- Optional: `sheet`, `cell_range`, `link`, `title`, `header`, `text_height`, `column_widths`, `style`, `layer`, `space`, and 1 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle", "linked": bool, "range", "sheet", "rows", "columns", "excel_converted": [{cell, shown_as, number}], "not_linked_because" when it fell back}`

**Limits and versions.**
- A file, sheet or range that is not there, or a range bigger than 500 rows, 40 columns or 5,000 cells, is refused before anything is made.
- The plug-in does part of the work (`excel_table`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AC5b, AC7, AC9, BD4, AV2).

### `autocad_text_clean`

**What it does.** Remove pasted formatting from MText (fonts, colours, heights, underline) so it follows its style.

**The problem it solves.**
- Text pasted from Word or Excel keeps its own font, colour or height and ignores the drawing's style.
- An import's notes plot the wrong size for no clear reason.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Remove pasted formatting from MText (fonts, colours, heights, underline) so it follows its style."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `handles`, `layer`, `keep_paragraphs`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"cleaned": n, "items": [{handle, before, after}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_update_table_links`

**What it does.** Update tables linked to Excel from their sheets (DATALINKUPDATE), keeping Heron's table formatting.
After the workbook behind a linked table was edited and saved, this reads it again and puts the new values in the table. Text stays in the vertical middle of each cell; the table's own formatting is kept, not Excel's. Done by the Heron plug-in in one transaction. A table that is not linked (one filled from a sheet, or drawn by hand) is listed, not changed.

**The problem it solves.**
- "the sheet changed in Excel, update the linked table".
- "refresh all the Excel tables before we issue".
- *Not for:* the table was filled, not linked - run autocad_table_from_excel again, or autocad_set_table_cells.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"the sheet changed in Excel, update the linked table"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `handles`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"updated": [{handle, source}], "not_linked": [handle], "note": str (only when no table is linked)}. A workbook that cannot be read refuses the whole job and nothing is changed (D-83), so there is no per-table failure list.`

**Limits and versions.**
- The plug-in does part of the work (`update_table_links`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AC8, AQ17).


## Dimensions

Dimensions, dimension runs, centre marks.

### `autocad_add_centre_marks`

**What it does.** Put a centre mark on every circle and arc: the cross a drawing office expects.
Give the handles, or a layer and every circle and arc on it is marked. ``extend`` turns the cross into full centre lines running past the circle. AutoCAD has no Automation call for a centre mark, so these are drawn as lines — which means they go on the layer you ask for and plot the way that layer does. One undo step.

**The problem it solves.**
- "put centre lines on all the holes" — layer_filter the hole layer, extend about 2 mm of paper.
- A fabricator asks for hole centres to be marked.
- *Not for:* you want a radius or diameter dimension (autocad_add_dimension).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put centre lines on all the holes"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `handles`, `layer_filter`, `size`, `extend`, `layer`, `color`, `min_radius`, `quiet`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"marked": int, "skipped": int, "created", "handles", "circles": [{"handle", "centre", "radius"}]}`

**Limits and versions.**
- A handle that is not a circle or an arc is counted in "skipped" and named, rather than failing the call.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E15).

### `autocad_add_dimension`

**What it does.** Add a dimension annotating a distance, radius, diameter or angle.
The dimension takes the drawing's current dimension style, so it follows the sheet's standards for arrowheads, text size and units.

**The problem it solves.**
- "dimension the wall from 0,0 to 5000,0" -> dimension_type="horizontal", point1=[0,0], point2=[5000,0], text_position=[2500,-500].
- "show that circle's diameter" -> dimension_type="diametric" with two opposite points on it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"dimension the wall from 0,0 to 5000,0"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `dimension_type`, `point1`, `point2`, `point3`, `text_position`, `text_override`, `layer`, `space`, `coords`, `annotative`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "dimension", "layer": str, "measurement": float, "dimension_type": str} With annotative: also "annotative" and "annotation_scales".`

**Limits and versions.**
- Names the specific missing argument when a dimension type needs a point that was not supplied.
- The plug-in does part of the work (`set_annotation_scales`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB10, AI2).

### `autocad_break_dimensions`

**What it does.** Break dimensions where other objects cross them: AutoCAD's DIMBREAK, automatic.
Each dimension gets a gap in its dimension and extension lines wherever another object crosses it, the size the dimension style says (DIMBREAK). remove=true takes the breaks off again. The breaks follow the objects: move a duct and the gap moves with it. Neither COM nor the plug-in has a call for a dimension break, so this types DIMBREAK (Multiple, then Break or Remove) with each dimension picked by its handle. The dimensions must be in the space you are working in. One undo step.

**The problem it solves.**
- "break the dimensions where the pipes cross them".
- "take the dimension breaks off" — remove=true.
- *Not for:* you want the dimension text clear of hatch — use a background mask, or autocad_add_wipeout behind it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"break the dimensions where the pipes cross them"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The dimensions to break, by handle. Each is broken wherever another object crosses its dimension or extension lines.
- Optional: `remove`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"broken": [str] | "unbroken": [str], "space": str, "command": str}`

**Limits and versions.**
- Anything that is not a dimension, a dimension in another space, or one on a locked or frozen layer is refused before anything is typed.
- If AutoCAD is still asking when DIMBREAK should be done, it is cancelled and the tool says so.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB4).

### `autocad_dimension_run`

**What it does.** Dimension a whole run of features in one call: a chain, a baseline set, or ordinates.
This is the dimensioning a drawing actually needs. Give the feature points along a wall, a grid or a row of holes and say how you want them read; the points are sorted, every dimension line is placed at the same offset, a baseline set steps clear of itself, and an overall can go above the lot. The measurements are worked out here as well as by AutoCAD, and both are reported — so a run that does not add up shows itself.

**The problem it solves.**
- "dimension the grid lines along this wall" — the grid X values as points, mode='chain', include_overall=true.
- "dimension every hole back to the left edge" — mode='baseline'.
- "ordinate dimensions from the setting-out point" — mode='ordinate', datum the corner.
- "dimension the 1:5 detail with the DIM-1-5 style" — dim_style='DIM-1-5'; no need to change DIMSCALE part-way through.
- *Not for:* it is one dimension (autocad_add_dimension), or a radius, diameter or angle (same tool).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"dimension the grid lines along this wall"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `points`: The feature points to dimension between, each [x, y] — grid lines, wall faces, hole centres, duct branches.
- Optional: `mode`, `axis`, `offset`, `spacing`, `include_overall`, `datum`, `sort`, `text_override`, `layer`, `space`, and 4 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "mode", "axis", "count", "handles": [str], "dimensions": [{"kind", "point1", "point2", "text_position", "expected", "measured", "handle", "row"}], "total": float, # the run end to end "failed": [{"index", "reason"}], "dim_style" ...`

**Limits and versions.**
- A dim_style the drawing does not have is refused before anything is drawn, naming the styles it has.
- Points that land on top of each other along the axis are skipped rather than making a zero dimension; if none are left, that is said.
- A dimension AutoCAD rejects is reported in "failed" with its index; the rest of the run still lands.
- The plug-in does part of the work (`set_annotation_scales`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E11, AB1, AB10, Z5, S7).

### `autocad_space_dimensions`

**What it does.** Space a stack of parallel dimensions evenly off a base dimension: AutoCAD's DIMSPACE.
The base dimension stays put. Every other one keeps the side of it that it is on and its order out from it, and its dimension line is moved to 1, 2, 3 ... times the spacing from the base line. Only the dimension lines move: the extension line origins stay on the geometry. spacing=0 lines them all up on the base line. The plug-in reads where each dimension line is and moves it; the spacing is worked out here. One undo step.

**The problem it solves.**
- "space these baseline dimensions 400 apart" — the handles, the innermost first, spacing=400.
- "the overall and the chain are on top of each other" — the chain as base, the overall with it, spacing about 8 mm of paper.
- "line these dimensions up" — spacing=0.
- *Not for:* you are dimensioning a run from scratch — autocad_dimension_run spaces a baseline set as it draws it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"space these baseline dimensions 400 apart"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The stacked, parallel dimensions to space, by handle — the base first unless you name it in 'base'.
- Needs `spacing`: Distance between one dimension line and the next, in drawing units: about 7 to 10 mm of paper, so 350 to 500 at 1:50.
- Optional: `base`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"base": str, "spacing": float, "moved": int, "moves": [{"handle", "from", "to", "offset_was", "offset_now"}], "already": [str], "skipped": [{"handle", "why"}], "before_after": [{handle, property, from, to}]}`

**Limits and versions.**
- A dimension that is not parallel to the base is left where it is and listed in "skipped"; one that is not linear or aligned is skipped too.
- Fewer than two dimensions, a base that is not in the list, or a negative spacing is refused before anything moves.
- The plug-in does part of the work (`dimension_lines`, `move_dimension_lines`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB2).


## Blocks, attributes and references

Blocks and their attributes, dynamic blocks, xrefs, underlays, taking objects from another drawing.

### `autocad_apply_attribute_sheet`

**What it does.** Bring back an edited attribute sheet: compare it with the drawing and write only the cells that changed.
Each row is matched to its block by the Handle column. A cell is written only when the modeller changed it: a blank cell changes nothing, a cell equal to the drawing changes nothing. With the 'As exported' sheet (autocad_export_attribute_sheet makes it) a value the drawing changed since the export is kept, and a value changed in both places is a conflict, listed and not written. All the writes are one undo step, and the answer lists each one old -> new ('before_after').

**The problem it solves.**
- "I filled in the tags in the Excel, put them back in the drawing" -> path of that workbook, dry_run=true first.
- "bring the edited spreadsheet back in, only what I changed".
- The modeller edited the revision columns of the title block sheet and wants only those written.
- *Not for:* the values are in the chat, not a file - autocad_set_attributes takes them as rows.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"I filled in the tags in the Excel, put them back in the drawing"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: The edited workbook (.xlsx, or a .csv with a Handle column). A bare file name is looked for next to the drawing.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"changed": n, "changes": [{handle, block, layout, tag, old, new}], "conflicts", "kept_drawing", "missing_handles", "unknown_tags", "failed", "blank_cells", "unchanged_cells", "before_after"}`

**Limits and versions.**
- A file with no Handle column, a handle twice, or more than 10000 changes: refused, nothing written.
- A row whose block is gone, or a value under a tag the block does not have: listed, the rest still applied.
- A cell AutoCAD would not take (a locked layer): listed in 'failed'.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows Y2, BE5, RV2).

### `autocad_attach_underlay`

**What it does.** Attach a raster image or a PDF / DWF / DGN underlay (IMAGEATTACH, PDFATTACH, DWFATTACH, DGNATTACH).
The consultant's background as a PDF, a scanned survey, a site photo: it shows in the drawing and is not copied in. Placed at a point, scale and rotation, on the layer asked for. Clip it afterwards with autocad_clip_reference. An image is attached over COM; an underlay by the Heron plug-in, which COM has no call for.

**The problem it solves.**
- "attach the architect's PDF as a background at 0,0" — path to the .pdf.
- "bring in page 3 of the consultant's PDF" — page='3'.
- "put the site photo in, 42 m wide" — width=42000.
- "attach the DGN from the civil engineer".
- *Not for:* the file is a .dwg - autocad_attach_xref.
- *Not for:* you want the PDF's lines as real objects - type PDFIMPORT in AutoCAD.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"attach the architect's PDF as a background at 0,0"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: The file: a PDF, DWF, DWFx or DGN, or a raster image (PNG, JPG, TIF, BMP, GIF...).
- Optional: `insertion`, `scale`, `width`, `rotation`, `page`, `layer`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "kind": str, "path": str, "layer": str, ...}`

**Limits and versions.**
- A file that is not there, or not an image or underlay type, is refused before AutoCAD is asked.
- A PDF page or DWF sheet that is not in the file is refused by the plug-in, and nothing is changed.
- The plug-in does part of the work (`attach_underlay`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AD3).

### `autocad_attach_xref`

**What it does.** Reference another drawing into this one as an xref (XATTACH).
The architect's plan under the services, a survey under the site plan: the other drawing shows here and updates when it changes, without being copied in. One undo step.

**The problem it solves.**
- "xref the architect's plan in at 0,0" — path, insertion [0, 0].
- "overlay the survey as a background" — overlay=true.
- *Not for:* you want the other drawing's objects copied in for good - that is autocad_insert_block with the .dwg (or bind the xref afterwards with autocad_manage_xref).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"xref the architect's plan in at 0,0"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: The .dwg to reference, e.g. 'D:\\Project\\Arch\\A-101.dwg'. Forward slashes are fine.
- Optional: `name`, `insertion`, `scale`, `rotation`, `overlay`, `layer`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "name": str, "path": str, "overlay": bool, "layer": str}`

**Limits and versions.**
- A file that is not there is named before AutoCAD is asked.
- A name already used by a block or xref in this drawing is refused, pointing at autocad_manage_xref to reload the one that is there.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G7).

### `autocad_break_at_blocks`

**What it does.** Cut the lines and polylines that run through blocks, so a symbol sits in a clean gap.
Uses each block's extents (square to the drawing), plus 'gap'. A polyline with arcs is cut too: each arc is cut where it crosses the box and keeps its centre and radius, so a bend stays a bend either side of the gap. A closed polyline cut once comes out as one open run. One undo step.

**The problem it solves.**
- A symbol sits on top of the line it belongs to and the drawing reads badly: cut a clean gap round every block.
- An import has wiring or pipework running straight through its devices.
- The run bends through the fitting on an arc - the arc is cut too, and stays an arc.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Cut the lines and polylines that run through blocks, so a symbol sits in a clean gap."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `block_handles`: The blocks sitting on the lines: valves, fittings, symbols.
- Optional: `layer`, `gap`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"broken": n, "new_handles", "removed", "skipped": [{handle, reason}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AI7).

### `autocad_clip_reference`

**What it does.** Clip an xref, a raster image or a PDF / DWF / DGN underlay to a rectangle or a closed polyline (XCLIP, IMAGECLIP, PDFCLIP).
Show only the part of the architect's plan, the survey or the PDF that the sheet needs. Only what is inside the outline shows; nothing is erased, and remove=true brings the whole reference back. An image is clipped over COM; an xref, a block or an underlay by the Heron plug-in, which COM has no call for. A new clip replaces the old one.

**The problem it solves.**
- "clip the architect's xref to the plant room area" — corners or a boundary polyline.
- "crop the PDF background to the north wing" — handle of the underlay, boundary polyline.
- "unclip the survey image" — remove=true.
- *Not for:* you want objects cut and erased at a line - that is TRIM, not a clip.
- *Not for:* the reference is not attached yet - autocad_attach_xref or autocad_attach_underlay first.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"clip the architect's xref to the plant room area"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The xref, block, raster image or PDF / DWF / DGN underlay to clip.
- Optional: `corners`, `boundary`, `remove`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "kind": str, "clipped": bool, "points": int}`

**Limits and versions.**
- An object that is not an xref, block, image or underlay is refused.
- An outline that is open, crosses itself or encloses no area is refused before anything changes.
- Both or neither of corners and boundary (without remove) is refused.
- The plug-in does part of the work (`clip_reference`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AD4).

### `autocad_copy_from_drawing`

**What it does.** Copy objects from another open drawing into this one, at a base point (Copy with Base Point, then Paste).
The copies land in the active drawing, the one Heron checked with autocad_status; the source drawing is only read and stays open as it was, and neither drawing is switched. Layers, linetypes, text and dimension styles and blocks the copies need that this drawing lacks come with them; a name this drawing already has is used as it is here, so a block called VALVE in both shows this drawing's VALVE (listed in "already_here"). One undo step.

**The problem it solves.**
- "copy the pump skid from pump-room.dwg into this plan at 5000,2000" -> source, handles from that drawing, base_point, to_point=[5000, 2000].
- "bring the AHU and its ducts over from the old layout drawing" (switch to it, autocad_get_selection, switch back, autocad_status, then this).
- *Not for:* only blocks, layers or styles are wanted from a file that is not open - autocad_import_from_drawing.
- *Not for:* copying inside the same drawing - autocad_copy_entities.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"copy the pump skid from pump-room.dwg into this plan at 5000,2000"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `source`: The open drawing to copy from, e.g. 'pump-room.dwg' (or its full path when two open files share a name). autocad_list_drawings names them.
- Needs `handles`: Handles of the objects to copy, in the source drawing. Find them there with autocad_list_entities or autocad_get_selection while it is active.
- Needs `base_point`: The base point in the source drawing, [x, y] (world coordinates there), as Copy with Base Point picks it.
- Optional: `to_point`, `space`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"copied": int, "handles": [new handles], "from", "into", "moved_by": [dx, dy, dz], "source_objects": [{handle, type, layer}] (the first 50;`

**Limits and versions.**
- A source that is not open, is this drawing, or a handle that is not in it is refused before anything is copied; so is a handle that names a layer, a style or anything else that is not a drawn object there.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AC14, BD5, AV4).

### `autocad_count_blocks`

**What it does.** Count block references for a quantity take-off: fittings, valves, devices.
Dynamic blocks are counted by their real name, not the *U names AutoCAD gives their copies. Group by visibility state or property values to count each size or type separately.

**The problem it solves.**
- "how many diffusers on this floor" -> grouped by block name, optionally per layer.
- Pricing or ordering: this is the take-off count.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"how many diffusers on this floor"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `block_name`, `layer`, `group_by`, `include_nested`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"total": n, "rows": [{"block", ..., "count"}]}`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **PARTLY**: rows A26 passed in AutoCAD 2027; the rest are NOT RUN (rows A26, W7, AU1, AU2, AU3, AU6, AU7).

### `autocad_export_attribute_sheet`

**What it does.** Write every block's attributes to a new Excel workbook next to the drawing, to edit and bring back.
One row per block reference, one column per tag, with the block's handle, name and layout first. The workbook is new: '<drawing> - attributes - <date>.xlsx' in the drawing's folder, never over an earlier one (the next gets ' (2)'). It also holds an 'As exported' copy, so when the modeller brings it back autocad_apply_attribute_sheet can tell their edits from changes made in the drawing since. Writing a file needs the Publish padlock; the drawing is not changed.

**The problem it solves.**
- "give me the equipment tags in Excel so I can fill them in".
- "export the title block attributes of every sheet, I will update the revisions in Excel" -> block_name='TITLEBLOCK'.
- *Not for:* the modeller only wants to read the values in the chat - autocad_extract_attributes needs no padlock.
- *Not for:* one value goes to every block (REV B everywhere) - autocad_set_attributes does it in one call.
- *Not for:* the sheet is already filled in and must go back into the drawing - autocad_apply_attribute_sheet puts the edited values back.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"give me the equipment tags in Excel so I can fill them in"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `block_name`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"saved": path, "blocks": n, "tags": [...], "next": what to do}`

**Limits and versions.**
- An unsaved drawing has no folder: it says to save it first.
- No block with attributes: it says so and writes nothing.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows Y1, BE3, BE8, RV2).

### `autocad_extract_attributes`

**What it does.** List every block reference's attributes as rows, for schedules.
Use for "make a camera schedule", "list all equipment tags", or to check tag values. Rows: block, handle, layer, insertion point, attributes.

**The problem it solves.**
- "give me the camera schedule from the drawing" -> rows of tag values you can hand to autocad_add_table.
- Checking an import: it shows which tags are empty.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"give me the camera schedule from the drawing"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `block_name`, `layer`, `output`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E19, BE1, BE2, BE6, BE7, BE8, BE9, BE10, S3).

### `autocad_get_dynamic_properties`

**What it does.** List a dynamic block's properties: value, allowed choices, read-only.
Use before autocad_set_dynamic_properties to see the names and choices (visibility states, lookup sizes, stretch distances).

**The problem it solves.**
- A dynamic block is not showing what you expect and you need its real property names and allowed values first.
- Before autocad_set_dynamic_properties, so you pass a value the block will accept.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"List a dynamic block's properties: value, allowed choices, read-only."*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `handle`: Handle of a dynamic block reference.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"handle", "block", "properties": [{name, value, allowed, read_only, description}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PASS** in AutoCAD 2027 (rows A27).

### `autocad_import_from_drawing`

**What it does.** Copy blocks, layers, linetypes, text or dimension styles from another drawing into this one.
Use to load company standard symbols and layers in one call. The source file is read without opening it on screen. Names that already exist here are skipped, never overwritten.

**The problem it solves.**
- "bring the title block and the layer standard in from our template" -> the blocks, layers and styles, not the geometry.
- Starting a drawing that must match an existing set.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"bring the title block and the layer standard in from our template"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: The standards or library .dwg to copy from.
- Needs `kind`: What to bring in: blocks, layers, linetypes, text_styles or dim_styles.
- Optional: `names`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"imported": [...], "skipped_existing": [...], "not_found": [...]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_insert_block`

**What it does.** Insert a block reference, optionally filling in its attributes.

**The problem it solves.**
- "put a CAM-DOME at 4500,2300 turned 90" -> block_name="CAM-DOME", position=[4500,2300], rotation=90.
- The block is not in the drawing yet: pass the .dwg path as block_name and it is brought in.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put a CAM-DOME at 4500,2300 turned 90"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `block_name`: Name of a block already defined in the drawing, or a full path to an external .dwg to insert as a new block.
- Needs `position`: Insertion point as [x, y].
- Optional: `scale`, `rotation`, `attributes`, `layer`, `space`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "block", "layer": str, "block_name": str, "attributes_set": [str], "attributes_not_found": [str]}`

**Limits and versions.**
- Lists the drawing's available block names when the requested one is not defined, so the next call can use a valid name.
- Reports requested attribute tags the block does not have in "attributes_not_found" rather than failing the whole insertion.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PARTLY**: rows A28 passed in AutoCAD 2027; the rest are NOT RUN (rows A28, AI1).

### `autocad_list_blocks`

**What it does.** List the block definitions available in the drawing.
Use this before autocad_insert_block to get exact names, and to see what attributes each block expects. Anonymous blocks (names starting with *) and layout blocks are always excluded — they are AutoCAD internals, not blocks a user would insert.

**The problem it solves.**
- "what blocks can I insert?"
- "how many door blocks are in this drawing?"

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what blocks can I insert?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `include_counts`, `include_unused`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count": int, "blocks": [{"name": str, "entity_count": int, # entities in the definition "instances": int, # times placed in the drawing "is_xref": bool, "dynamic": bool, # a dynamic block "attribute_tags": [str], "path": str}]} # ...`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **PARTLY**: rows A28 passed in AutoCAD 2027; the rest are NOT RUN (rows A28, AC2, AU4, AU6, AU7).

### `autocad_make_block`

**What it does.** Turn drawn objects into a named block (a tag block with its attributes too), and put it where they were.
Use for every separate part (fitting, elbow, clamp, plate, anchor, support piece) so it can be moved, copied, swapped and counted as one. Draw the part, then call this with its handles. Insert more copies with autocad_insert_block. Pipes and runs can stay as lines or polylines. With ``attributes`` the block gets attribute definitions (ATTDEF): a tag block whose value (tag, size, room number) is typed per insert. The insert put in place of the objects starts with each attribute's default;

**The problem it solves.**
- "make these lines into a block called BASE PLATE 250x250x12" -> handles=[...], base_point=the insertion corner.
- A part repeats. Drafting rule 2: parts are blocks, not loose lines.
- "make a tag block with a TAG attribute": a new block with attribute definitions (ATTDEF), e.g. a valve tag block with a TAG attribute and an invisible SIZE attribute -> attributes=[{"tag": "TAG", ...}, {"tag": "SIZE", "invisible": true}].
- *Not for:* the block is already in the drawing - autocad_insert_block places more of it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make these lines into a block called BASE PLATE 250x250x12"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: New block name, e.g. 'SHS 100x100x5 POST'.
- Needs `handles`: Handles of the objects that make up the part.
- Needs `base_point`: Block base point [x, y]: the point you insert it by.
- Optional: `layer`, `keep_originals`, `attributes`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "block": name, "handle": insert handle (null when keep_originals), "attributes": [{tag, default, invisible, constant, preset}] when given}`

**Limits and versions.**
- A tag with a space, a tag given twice, a constant attribute with no default, or constant and preset together are refused before anything is made.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PARTLY**: rows A25 passed in AutoCAD 2027; the rest are NOT RUN (rows A25, K7, AC1, AC2, AF24, BG6).

### `autocad_manage_xref`

**What it does.** Reload, unload, detach or bind an xref - the External References palette's actions.
Reload after the other consultant issues a new revision; unload to hide one without losing it; detach to remove it; bind (or insert) to make it a permanent part of this drawing before issuing it. One undo step.

**The problem it solves.**
- "the architect issued a new plan, update the xref" — action='reload'.
- "bind the xrefs before we send the drawing out" — action='bind', confirm=true.
- "remove the old survey xref" — action='detach', confirm=true.
- *Not for:* you want to see which xrefs there are - autocad_list_blocks lists them with their paths.
- *Not for:* the drawing is not referenced in yet - attach it with autocad_attach_xref.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"the architect issued a new plan, update the xref"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: The xref's name, as autocad_list_blocks shows it.
- Needs `action`: 'reload' brings it up to date; 'unload' hides it but keeps it; 'detach' removes it and every instance;
- Optional: `confirm`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"name": str, "action": str, "confirmed": bool, "path": str, "note": str}`

**Limits and versions.**
- A name that is not in the drawing, or a block that is not an xref, is refused before anything changes.
- Without confirm, detach, bind and insert change nothing and say so.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G8, G9).

### `autocad_place_along`

**What it does.** Insert a block at equal spacing along a run, centred so both ends match.
For sprinklers, lights, diffusers, supports and cameras along a corridor. Number them afterwards with autocad_number_tags (sort='path').

**The problem it solves.**
- "hangers every 2 m along that duct, ends matching" -> spacing=2000; it centres the run so both ends are equal.
- *Not for:* the positions come from a schedule - autocad_place_from_csv.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"hangers every 2 m along that duct, ends matching"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path_handle`: The line, polyline, arc or circle to place along.
- Needs `block_name`: Block to insert (defined in the drawing).
- Optional: `spacing`, `count`, `align`, `rotation`, `scale`, `attributes`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"placed": n, "handles", "spacing", "run_length"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_place_from_csv`

**What it does.** Insert blocks at coordinates from a schedule and fill their attributes from the same rows.
For device, pole and camera schedules, or setting-out points from a survey.

**The problem it solves.**
- "place all 42 cameras from this schedule, with their tags filled in" -> the csv carries x, y and the attribute columns.
- A surveyor hands you coordinates.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"place all 42 cameras from this schedule, with their tags filled in"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `csv_path`, `rows`, `block_name`, `scale`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"placed": n, "handles", "attributes_not_found"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_set_attributes`

**What it does.** Fill block attributes: title blocks on every layout, equipment tags, schedules.
Same values for all, or one row per block from a list or CSV, matched by a tag or the layout name. Pairs with autocad_extract_attributes (read, edit, write back).

**The problem it solves.**
- "fill the title block on every sheet with this drawing number and date".
- *Not for:* you are placing the title block for the first time - autocad_place_title_block fills it as it goes.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"fill the title block on every sheet with this drawing number and date"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `block_name`, `values`, `rows`, `csv_path`, `key`, `layer`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"changed": n, "changes": [{handle, block, layout, tag, old, new}], "unknown_tags", "unmatched_rows", "before_after": the first 50 changes as {handle, property, from, to}}`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows BE4, BE10, AZ4).

### `autocad_set_dynamic_properties`

**What it does.** Change a dynamic block's properties: visibility state, size, distance, flip.
Names are matched without regard to case. Each value is converted to the property's own type and checked against its allowed values; the ones that cannot be set are listed in 'failed' with the reason. One undo step.

**The problem it solves.**
- "switch those doors to the 900 leaf" -> the width property, or the visibility state.
- *Not for:* you do not know the property names - read them with autocad_get_dynamic_properties first.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"switch those doors to the 900 leaf"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: Handle of a dynamic block reference.
- Needs `values`: {property name: new value}, e.g. {'Visibility1': 'GATE', 'Size': 80}.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle", "changed": {name: value}, "failed": {name: reason}, "before_after": [{handle, property, from, to}], "already": [names already so]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PASS** in AutoCAD 2027 (rows A27).

### `autocad_sync_attributes`

**What it does.** ATTSYNC: give every insert of a block the attributes its definition has now, keeping the values already typed.
After a block's definition changed (an attribute added, removed, moved or resized), the inserts already placed still carry the old attributes. This brings them in step: a value already typed is kept, matched by tag; a tag the definition gained comes in with its default; a tag it lost, or made constant, goes. Each attribute goes back to where the definition puts it (position, height, style). An attribute holding a field, and a multi-line one, keeps its own text and place.

**The problem it solves.**
- "I added a SIZE attribute to the valve tag block, update all the valves" -> block='VALVE TAG'.
- "add an invisible MAKE attribute to the PUMP block and put it on every pump" -> add_attributes=[{"tag": "MAKE", "invisible": true}].
- "ATTSYNC the title block" after it was redefined.
- "the valve tags inside the skid blocks too" -> nested=true.
- *Not for:* only the values change - autocad_set_attributes, or autocad_apply_attribute_sheet from Excel.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"I added a SIZE attribute to the valve tag block, update all the valves"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `block`: The block whose inserts to bring in step, e.g. 'VALVE TAG'. autocad_list_blocks names them.
- Optional: `handles`, `add_attributes`, `nested`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"block", "touched", "changing_tags", "values_kept", "attributes_added", "attributes_dropped", "inserts": [{handle, keep, add, drop}], "skipped": [{handle, why}], "definitions_added": [tag], "synced": what the plug-in did ...`

**Limits and versions.**
- A block that is not in the drawing points at autocad_list_blocks.
- A new tag that the block already has is refused before anything changes.
- The plug-in does part of the work (`sync_attributes`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AC3, AC6, AC17, AV1).

### `autocad_xref_tree`

**What it does.** The whole xref tree of this drawing: each xref, the xrefs inside it, and which ones are broken.
For each xref: its name, the path saved in the drawing, the file it points to on this PC (empty when there is none), and its status - 'loaded', 'unloaded' (the file is there but not loaded) or 'not found' (the path leads nowhere: a broken xref). Nested xrefs are listed under the one that carries them, up to 8 levels. Changes nothing.

**The problem it solves.**
- "which xrefs are broken before I issue this?"
- "show me the xref tree, nested ones too".
- "where is the architect's xref pointing?"
- *Not for:* you only want the names and instance counts - autocad_list_blocks lists every xref with its saved path.
- *Not for:* you want to fix one - autocad_manage_xref reloads, unloads, detaches or binds it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"which xrefs are broken before I issue this?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"drawing": str, "count": int, "broken": [str], "xrefs": [{"name": str, "saved_path": str, "found_path": str, "status": str, "children": [...]}]}`

**Limits and versions.**
- A drawing with no xrefs answers count 0, not an error.
- A nested xref that refers back up the tree is marked, not followed.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows I1).


## Layers and linetypes

Layers, layer states, the office layer standard, linetypes.

### `autocad_create_layer`

**What it does.** Create a layer, or update one that already exists.
Safe to call repeatedly: an existing layer is updated with whatever properties you pass rather than raising an error.

**The problem it solves.**
- "make a layer M-HVAC-DUCT, cyan, dashed".
- *Not for:* you are sorting out a whole import - the layers come out of autocad_remap_layers already.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make a layer M-HVAC-DUCT, cyan, dashed"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: Layer name, e.g. 'A-WALL' or 'M-DUCT-SUPPLY'. Cannot contain < > / \ " : ; ? * | , = `
- Optional: `color`, `linetype`, `lineweight`, `make_current`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"name": str, "created": bool, "current": bool, "color": int, "linetype": str, "lineweight": int, ..., "before_after": [{layer, property, from, to}]} "created" is false when the layer already existed and was updated.`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows Q1, T2, T4, BD2, BF1, BF2, AL5).

### `autocad_create_linetype`

**What it does.** Make a linetype - a plain dashed one, or a service line with its name in it.
---- CHWS ---- CHWS ---- for chilled water, HWS, CW, GAS, FIRE: the MEP convention, as a real linetype the modeller can put on a layer. Writes NAME.lin and loads it into the drawing. Sizes are as they plot when LTSCALE is the drawing scale factor, which autocad_drawing_setup(scale=...) sets.

**The problem it solves.**
- "make a CHWS linetype with the text in the line" — text='CHWS'.
- "a dash-dot line, 12 dash, 3 gap" — dashes=[12, -3, 0, -3].
- *Not for:* the linetype exists in acad.lin / acadiso.lin (HIDDEN, CENTER, DASHED...) — the draw tools load those themselves.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make a CHWS linetype with the text in the line"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: Linetype name, also the file name, e.g. 'CHWS'.
- Optional: `text`, `dashes`, `dash`, `gap`, `height`, `text_style`, `text_width`, `description`, `folder`, `load`, and 1 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"file": str, "file_text": str, "loaded": bool, "hint": str}`

**Limits and versions.**
- Text and dashes together, a quote in the text, a pattern that starts with a gap, more than 12 dashes, or a description over 47 characters are refused before anything is written.
- A linetype already in the drawing, or a text style it lacks, is refused before the file is written.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows G11, G12).

### `autocad_delete_layer`

**What it does.** Delete a layer, optionally deleting the geometry on it.
AutoCAD will not delete layer 0, the current layer, or a layer that still holds entities. Set delete_contents=true to clear it first — that destroys the geometry.

**The problem it solves.**
- An import left empty layers behind and you are tidying up.
- *Not for:* you only want it out of the way - freeze or turn it off with autocad_set_layer_state. Deleting takes the geometry too if you ask it to.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Delete a layer, optionally deleting the geometry on it."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: Layer to delete.
- Optional: `delete_contents`, `confirm`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"deleted": bool, "layer": str, "entities_deleted": int} With confirm=false: a preview of what the call would remove.`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows BD2).

### `autocad_isolate_layers`

**What it does.** Isolate the layers of some objects (or named layers): every other layer off, frozen or locked.
AutoCAD's LAYISO and LAYUNISO. Before the first isolate, Heron saves the layers as they are in a layer state called HERON-ISOLATE; 'unisolate' puts that back, current layer included, and removes it. Isolating again before un-isolating keeps the first one, so un-isolating always returns to where you started. The kept layers are turned on and thawed (and unlocked with others='lock').

**The problem it solves.**
- "show me only the duct layers" — handles of a duct, or layers=['M-DUCT-SUPPLY','M-DUCT-RETURN'].
- "lock everything except the pipework so I can edit it" — others='lock'.
- "bring all the layers back" — action='unisolate'.
- *Not for:* you want a named set-up to come back to later — save it with autocad_layer_states.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"show me only the duct layers"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `action`, `handles`, `layers`, `others`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"action", "kept": [str], "others": str, "current_layer": str, "already_isolated": bool, "before_after": [{layer, property, from, to}], "failed": [{"layer", "reason"}]}`

**Limits and versions.**
- 'unisolate' with nothing isolated by Heron says so and changes nothing.
- A layer name the drawing has not got is refused before anything changes.
- others='freeze' with only xref layers kept, and the current layer among the ones to hide, is refused before anything is saved or changed: AutoCAD can neither make an xref layer current nor freeze the current layer.
- The plug-in does part of the work (`layer_state`, `layer_state_names`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB6, BC10, BC11).

### `autocad_layer_standard`

**What it does.** Load the office's own layer standard from a CSV, or say which standard is in force.
A layer standard is one row per layer: name (or a pattern with * and ?), colour, linetype, lineweight, plot, description, the old names it replaces, and whether every drawing must have it. The office's own list stays on this PC, in %LOCALAPPDATA%\Heron\autocad\standards\, never in Heron's files. Until one is imported, 'office' means the generic MEP example that ships with Heron, and a check against it is not decided. A CSV with any problem imports nothing; the answer lists each problem with its row number.

**The problem it solves.**
- "set up our office layer standard" or "where do I put our layer list" -> action='template', then the modeller fills the CSV.
- "I've filled the layer CSV, load it" -> action='import'.
- "which layer standard are you using" -> action='show'.
- "is my layer CSV right" -> action='show' with path; reads it and lists every problem, importing nothing.
- *Not for:* checking a drawing against the standard - autocad_check_standards(layer_standard='office'); putting objects on its layers - autocad_remap_layers(layer_standard='office').
- *Not for:* the standard is an office .dws or template drawing - autocad_check_standards(reference=...).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"set up our office layer standard"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `action`, `path`, `replace`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: show {"in_force", "file", "folder", "office_standard", "standard" {"name", "example", "counts", "layers"}, "next"}; template {"template", "next"}; import {"imported", "imported_from", "standard", "previous"};`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AT1, AT5).

### `autocad_layer_states`

**What it does.** Save the drawing's layers as a named layer state, bring one back, or delete one.
A layer state remembers which layers are on, frozen and locked (and, unless you say otherwise, their colour, linetype, lineweight and plotting), so a set-up such as "coordination: only the duct and pipe layers" can be put back in one call. autocad_list_layers lists the saved states. Done by Heron's plug-in (AutoCAD's LayerStateManager). One undo step.

**The problem it solves.**
- "save the layers as they are now as COORDINATION".
- "put the layers back to the ISSUE-PLOT state".
- *Not for:* "which layer states does this drawing have?" — that is autocad_list_layers, which lists them.
- *Not for:* you only want to hide a few layers for a moment — autocad_isolate_layers, or autocad_set_layer_state for one layer.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"save the layers as they are now as COORDINATION"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `action`: 'save' the layers as they are now under a name, 'restore' a saved one, or 'delete' one.
- Needs `name`: The layer state's name, e.g. 'M-COORDINATION' or 'ISSUE-PLOT'.
- Optional: `remembers`, `description`, `overwrite`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"action", "name", "remembers": [str], "layers": int, "before_after": [{layer, property, from, to}]} A restore lists every layer whose on, frozen or locked state it changed.`

**Limits and versions.**
- Saving over a state that is there already needs overwrite=true.
- Restoring or deleting a state the drawing has not got is refused, naming autocad_list_layers.
- The plug-in does part of the work (`layer_state`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB5).

### `autocad_list_layers`

**What it does.** List every layer with its colour, linetype and visibility state.
Reading the layer list first is the reliable way to use the drawing's own naming convention instead of inventing new layers alongside it.

**The problem it solves.**
- "what layers does this drawing use?"
- Before drawing, to match the existing naming convention.
- "which layer states are saved in this drawing?" — they come back in "layer_states"; autocad_layer_states saves and restores them.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what layers does this drawing use?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `include_entity_counts`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count": int, "current_layer": str, "layers": [ {"name": str, "color": int, "linetype": str, "lineweight": int, "on": bool, "frozen": bool, "locked": bool, "plottable": bool, "entity_count": int}], "layer_states": [{"name": str ...`

**Limits and versions.**
- The plug-in does part of the work (`layer_state_names`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows Q3, V2, AB5, BD5, AZ6, AL1, BC11).

### `autocad_merge_layers`

**What it does.** Merge layers into one: every object moves to the new layer, then the old layer is removed.
AutoCAD's LAYMERGE. Objects move from the old layers in model space, on every layout, inside block definitions and in block attributes. An old layer is removed only when nothing is left on it; one still in use somewhere (an object that would not move) is kept and named. Call it first without confirm to see what would move. If an old layer is the current layer, the new one becomes current. A locked old layer is unlocked for the move. One undo step.

**The problem it solves.**
- "merge DUCT and M-DUCT-OLD into M-DUCT-SUPPLY".
- An import came with three names for the same layer.
- *Not for:* you are sorting out a whole import by rules — autocad_remap_layers moves objects layer by layer from a table.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"merge DUCT and M-DUCT-OLD into M-DUCT-SUPPLY"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `layers`: The layers to merge away, by exact name, e.g. ['M-DUCT-OLD', 'DUCT'].
- Needs `into`: The layer everything moves to. It must already be in the drawing.
- Optional: `confirm`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"into", "moved": int, "counts": {layer: {"drawing", "blocks", "attributes"}}, "removed": [str], "kept": [{"layer", "why"}], "failed": [{"handle", "reason"}], "before_after": [...]} With confirm=false: the counts and a next step;`

**Limits and versions.**
- Layer 0, an xref's layer, a layer that is not there, or merging a layer into itself is refused before anything changes.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AB7).

### `autocad_remap_layers`

**What it does.** Put an imported drawing's objects on proper layers, and make those layers properly.
This is the first half of turning an IFC or Revit export into a shop drawing. Rules match on the old layer name, the block name, the object type, the colour or the text, and say which layer the object belongs on and what that layer should look like. Missing layers are created with the colour, linetype, lineweight, description and plot setting given. **dry_run is on by default.** Read "by_rule" and "counts", check nothing unexpected is being swept up, then run again with dry_run=false. One undo step.

**The problem it solves.**
- "this IFC came in on IfcWall, IfcDoor... make it a shop drawing" — preset='ifc', read the plan, then dry_run=false.
- "everything is on layer 0" — rules matching block_name.
- "put this drawing on our office layers" — layer_standard='office': the old names each row replaces move to its layer, and the standard's layers get its colours and linetypes.
- An office standard written as rules must be applied — rules_path.
- *Not for:* you only want to know what is wrong (autocad_check_standards reports without changing anything).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"this IFC came in on IfcWall, IfcDoor... make it a shop drawing"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `rules`, `rules_path`, `layer_standard`, `preset`, `layer`, `entity_type`, `handles`, `unmatched_layer`, `set_bylayer`, `max_entities`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "dry_run": bool, "counts": {"read", "to_move", "already_right", "unmatched", "layers_wanted"}, "by_rule": {"*duct* -> M-HVAC-DUCT": 412, ...}, "layers": [{name, color, linetype, lineweight, plottable, created}], "moved": int ...`

**Limits and versions.**
- A rule with no target layer, or with nothing to match on, is refused before any object is touched: a rule that matches everything would sweep the drawing onto one layer.
- A locked or frozen target layer is reported per object in "failed"; the rest of the move still lands.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D24, AT6, AT7).

### `autocad_set_current_layer`

**What it does.** Set the layer that new geometry goes on by default.
Only needed when drawing several things onto one layer — the drawing tools all take a 'layer' argument that overrides this per call.

**The problem it solves.**
- You are about to draw several things by hand and want them on the right layer without saying so each time.
- *Not for:* you are drawing through these tools - every draw tool takes its own layer, which is safer.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Set the layer that new geometry goes on by default."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: Layer to make current. Created if it does not exist.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"current_layer": str, "created": bool, "previous": str}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T5).

### `autocad_set_layer_state`

**What it does.** Turn layers on or off, freeze, lock or exclude them from plotting.
Only the states you pass are changed. Wildcards let one call cover a whole discipline prefix.

**The problem it solves.**
- "hide all the MEP layers" -> name="M-*", on=false.
- "unlock A-WALL so I can edit it" -> name="A-WALL", locked=false.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"hide all the MEP layers"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: Layer name, or a wildcard such as 'A-*' to act on every layer starting with A-.
- Optional: `on`, `frozen`, `locked`, `plottable`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"matched": int, "changed": [str], "state": {...}, "before_after": [{layer, property, from, to}], "already": int, "failed": [{"name": str, "reason": str}]}`

**Limits and versions.**
- The current layer cannot be frozen or turned off; AutoCAD refuses it and the reason is reported per layer rather than failing the call.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T6).


## Sheets and printing

Layouts, viewports, title blocks, drawing lists, page set-up, PDF.

### `autocad_add_viewport`

**What it does.** Cut a viewport in a sheet at a real scale, looking where you tell it.
Say where to look — a point, a window, a saved view, or a set of objects — and at what scale, and the viewport is made, aimed, scaled exactly, twisted if the plan is on a slant, and locked. Omit the scale and the largest standard scale that fits is used and reported, which is what a drafter does when the sheet size is fixed.

**The problem it solves.**
- "put the ground floor on this A1 at 1:100".
- "same area I just plotted" — autocad_save_view first, then view_name here.
- The plan is on a 23 degree grid — align_to_ucs=true.
- "clip the viewport to this L-shaped polyline" — clip_handle, or clip_outline with the corners.
- *Not for:* you want the whole sheet plotted (autocad_export).
- *Not for:* making a whole drawing list of sheets — autocad_sheet_set.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put the ground floor on this A1 at 1:100"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `layout`, `scale`, `centre`, `corner1`, `corner2`, `view_name`, `handles`, `paper_centre`, `paper_width`, `paper_height`, and 12 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "created": true, "handle": str, "layout": str, "scale": "1:50", "scale_ratio": float, "fitted": bool, "paper_rect": [x1, y1, x2, y2], "model_window": [x1, y1, x2, y2], "looking_at": [x, y], "twist_degrees": float, "locked": bool ...`

**Limits and versions.**
- An area that will not fit the viewport at any standard scale says so and names the smallest one tried.
- A saved view the drawing does not have is reported with the ones it has.
- The plug-in does part of the work (`add_viewport`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **PARTLY**: rows D16 passed in AutoCAD 2027; the rest are NOT RUN (rows D13, D14, D15, D16, D19, AF5, AF6, AF7, AF8, AF11, AF19, AQ7, AL7, S9).

### `autocad_create_layout`

**What it does.** Make a new sheet: the layout, its paper and plotter, and the space left to draw in.
Returns the sheet's arithmetic worked out — paper size, frame, the corner a title block goes in, and the rectangle left for viewports — so the next call can place things without measuring. Follow it with autocad_place_title_block and autocad_add_viewport, or put all three in one autocad_sequence. One undo step.

**The problem it solves.**
- "add sheet E-102, A1 landscape, mono".
- "copy sheet E-101 for the next level" — copy_from='E-101'.
- *Not for:* renaming or reordering existing sheets (autocad_manage_layouts).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"add sheet E-102, A1 landscape, mono"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: The new sheet's name, e.g. 'E-101'.
- Optional: `paper_size`, `orientation`, `plotter`, `plot_style_table`, `copy_from`, `margins`, `title_block_width`, `activate`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "created": true, "layout": str, "tab_order": int, "page_setup": {...}, "paper": {...}, "sheet": {"paper", "orientation", "frame", "drawing_space", "title_block_at", "drawing_space_size"} }`

**Limits and versions.**
- A name already in the drawing is refused before anything is made.
- copy_from naming a layout that is not there lists the ones that are.
- The plug-in does part of the work (`create_layout`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D8, D9, J5, AF1, AF3, AF11, AF17, AF19, AF21, AF22).

### `autocad_list_layouts`

**What it does.** The drawing's layouts (sheets) in tab order, with paper size, plotter and object count.

**The problem it solves.**
- "what sheets are in this drawing" -> tab order, paper size, plotter, how much is on each.
- Before a sheet-set job, to see which sheets are set up wrong.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what sheets are in this drawing"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count", "layouts": [{name, tab_order, objects, plotter, paper}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_list_views`

**What it does.** The drawing's saved views, each with its middle, size and two corners.
Use this to find a location someone already named — a detail area, a plotted region, a zone — instead of picking corners again.

**The problem it solves.**
- "plot the same area as last time" — find the view, then autocad_export(area='view', view_name=...).
- *Not for:* you want the sheets (autocad_list_layouts).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"plot the same area as last time"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count": int, "views": [{"name", "centre", "width", "height", "corner1", "corner2", "direction", "plan"}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D18, K13, AV5).

### `autocad_manage_layouts`

**What it does.** Sheet housekeeping: rename layouts, put tabs in order, renumber them, or copy objects onto every sheet.
Order runs first, then renumbering (in the new tab order), then renames, then copies. One undo step.

**The problem it solves.**
- "put the sheets in order and renumber them" across a package.
- "copy this north arrow onto every sheet".

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put the sheets in order and renumber them"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `rename`, `order`, `renumber_prefix`, `renumber_start`, `renumber_pad`, `renumber_suffix`, `copy_handles`, `copy_to`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"renamed": {old: new}, "order": [...], "copied": {layout: [handles]}}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_page_setup`

**What it does.** Set a sheet's plotter, paper size, plot area, scale and plot style table.
This is AutoCAD's Page Setup, done to one sheet or to every sheet at once — the job nobody enjoys doing 42 times by hand. A title-block sheet is normally plot_area='layout', scale='1:1', centred, with the office monochrome.ctb; the viewports inside carry the drawing scales. Only the options you pass are written; everything else on the sheet is left as it was. One undo step.

**The problem it solves.**
- "set all 42 sheets to A1, DWG To PDF, monochrome, 1:1".
- A sheet plots the wrong size because its paper is still A4.
- *Not for:* you want the PDF itself — that is autocad_export.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"set all 42 sheets to A1, DWG To PDF, monochrome, 1:1"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `layouts`, `all_layouts`, `plotter`, `paper_size`, `orientation`, `plot_area`, `corner1`, `corner2`, `view_name`, `scale`, and 5 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"layouts": [{"name", "written": {...}, "paper": {...}}], "count": int}`

**Limits and versions.**
- A plotter or sheet size AutoCAD does not have is named in the error, with the sizes that plotter does offer.
- The plotter is set before the sheet size, because a device only offers its own sizes.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D10, D11, AF20, AF21).

### `autocad_place_title_block`

**What it does.** Drop a title block in the corner of one sheet, or of every sheet, and fill it in.
The corner is worked out from the sheet's own paper size and the frame margins, so the block lands in the same place on an A3 and on an A0. ISO 5457 puts it bottom-right inside a frame of 20 mm on the binding edge and 10 mm elsewhere, which is the default here. One undo step for the whole run.

**The problem it solves.**
- "put our A1 title block on all 42 sheets and number them".
- A sheet came in without a title block.
- *Not for:* only the text needs changing — autocad_set_attributes fills title blocks already on the sheets.
- *Not for:* the title block should only be brought in from the template, not placed yet — autocad_import_from_drawing.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put our A1 title block on all 42 sheets and number them"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `block`: A block already in the drawing, or the full path to a title-block .dwg.
- Optional: `layouts`, `all_layouts`, `corner`, `anchor`, `margins`, `offset`, `scale`, `rotation`, `attributes`, `per_layout_attributes`, and 2 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"count": int, "placed": [{"layout", "handle", "at", "attributes_set": [str], "attributes_not_found": [str], "replaced": int}], "block": str}`

**Limits and versions.**
- A block that is neither in the drawing nor a .dwg on disk is reported with the blocks the drawing does have.
- Attribute tags the block does not carry come back in "attributes_not_found" rather than failing the sheet.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PASS** in AutoCAD 2027 (rows D12).

### `autocad_publish_pdf`

**What it does.** Publish sheets to ONE multi-page PDF, in tab order (AutoCAD's PUBLISH): of the open drawing, or of a folder or a list of drawings.
Each layout is plotted with its own page setup - paper, scale, plot style - as PUBLISH does, and sheets never opened are set up first so they do not come out blank. The PDF is made from the drawings as last saved, so save first: a drawing with unsaved changes is refused rather than published out of date. With folder or drawings, every drawing's sheets go in, drawing by drawing (layouts then picks the same-named sheets from each).

**The problem it solves.**
- "publish all the sheets to one PDF for issue".
- "make a PDF set of M-101 to M-104" — layouts=['M-101', 'M-102', 'M-103', 'M-104'].
- "batch plot the layouts into a single PDF".
- "one PDF of every drawing in the Issue folder" — folder='D:\Job\Issue'.
- *Not for:* you want one area or one layout fitted to a sheet - autocad_export with a .pdf path.
- *Not for:* you only need a picture to check the drawing - autocad_preview.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"publish all the sheets to one PDF for issue"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: Full path of the PDF to write, e.g. 'D:\\Issue\\M-100 set.pdf'.
- Optional: `layouts`, `include_model`, `overwrite`, `folder`, `drawings`, `recursive`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"published": true, "path": str, "count": int, "sheets": [str], "drawings": int, "pages": [{"drawing": str, "layout": str}]} # pages and drawings with folder / drawings`

**Limits and versions.**
- A drawing never saved, or with unsaved changes, is refused: save it with autocad_save_drawing first.
- With folder / drawings: a file that is not there, not a .dwg, open with unsaved changes, or with an xref that cannot be found, is named, and nothing is published.
- A layout name that is not in the drawing(s) is named.
- The plug-in does part of the work (`active_sheet`, `publish_pdf`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows I3, I4, I5, I8, M7, AF12).

### `autocad_save_view`

**What it does.** Name an area of the drawing so the same location can be plotted, viewported and found again.
Give two corners, or the objects the area should cover, and it is saved as an AutoCAD named view. From then on the one name means that exact rectangle — no re-picking, no drift. One undo step. Windows given with coords='ucs' are converted to world coordinates first, so a rotated plan saves the area that was meant.

**The problem it solves.**
- "remember this area, I'll plot it and also want a viewport on it" — then autocad_export(area='view') and autocad_add_viewport(view_name=...).
- "save the area round the pump skid" — handles + pad.
- "save this 3D angle of the villa as a camera view for the render" — from_screen=true.
- *Not for:* you only need the numbers once (autocad_get_extents gives them without saving anything).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"remember this area, I'll plot it and also want a viewport on it"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: What to call the location, e.g. 'DETAIL-A', 'ZONE-3', 'PLOT-AREA-1'.
- Optional: `corner1`, `corner2`, `handles`, `pad`, `replace`, `zoom_to`, `coords`, `from_screen`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"saved": str, "replaced": bool, "view": {"name", "centre", "width", "height", "corner1", "corner2"}, "from": str}`

**Limits and versions.**
- A name already saved is refused unless replace=true; a layout's (paper space) view of that name is refused even then, in plain words, and is never deleted (also when AutoCAD does not say which layout the view belongs to).
- A name holding a line break, Esc, tab or other control character is refused before anything is typed or any view is deleted (#242).
- Objects that report no extents are named rather than silently skipped.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D18, K13, AV5, AV6, AV7, BA1, BA2).

### `autocad_sheet_set`

**What it does.** Make a whole drawing list into sheets in one call: layouts, filled title blocks and viewports at scale.
Each row of the list - sheet number, title, scale, view - becomes a layout named by its number, set up for plotting (paper, plotter, 1:1), a viewport at the row's scale looking at its view and locked, and the title block in the corner with the number, title and scale written in. A row without a scale gets the largest standard scale that fits, and that is the scale written in its title block. The whole list is checked before anything is made, and every problem is said at once.

**The problem it solves.**
- "make sheets M-101 to M-112 from this drawing list, A1, our title block, each viewport on its saved view at 1:100".
- "set up the whole issue package" after the views are saved with autocad_save_view.
- "check this sheet list first" — dry_run=true.
- *Not for:* one sheet — autocad_create_layout, then autocad_add_viewport and autocad_place_title_block.
- *Not for:* the sheets exist and only the title block text needs changing — autocad_set_attributes.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make sheets M-101 to M-112 from this drawing list, A1, our title block, each viewport on its saved view at 1:100"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `sheets`: The drawing list, one row per sheet: {"number": "M-101" (the layout name), "title": "GROUND FLOOR HVAC", "scale": "1:100" (omit to fit), and where ...
- Optional: `paper_size`, `orientation`, `plotter`, `plot_style_table`, `template_layout`, `title_block`, `title_block_width`, `title_block_layer`, `number_tag`, `title_tag`, and 9 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"count": int, "complete": bool, "sheets": [{"number", "layout", "title", "scale", "fitted", "viewport": str | null, "model_window", "title_block": str | null, "attributes_set", "attributes_not_found", "made_by"}], "undo": str ...`

**Limits and versions.**
- A number used twice or already a layout, a scale it cannot read, a view the drawing does not have, a title block it cannot find: all said at once, and nothing is made.
- A sheet AutoCAD refuses part-way stops the run: the answer lists the sheets made and why it stopped; one Ctrl+Z takes them all back.
- The plug-in does part of the work (`add_viewport`, `create_layout`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AF9).


## 3D, lights and rendering set-up

Solids, surfaces, meshes, 3D edits, sections, lights, materials, the sun, cameras. Never the render itself.

### `autocad_add_camera_view`

**What it does.** Make a named perspective camera view at an eye point, looking at a target, through a lens.
The view for a render, as AutoCAD's CAMERA command makes one: perspective on, the lens set (24 mm inside a room), saved under a name so it can be rendered and gone back to (VIEW, or the render window's view list). By default it is also put on screen. Made by Heron's plug-in as one saved view with perspective and the lens set, never by DVIEW (which waits for picks and hangs). The view is sized to the lens's field at the target, so the two agree. No camera glyph is drawn.

**The problem it solves.**
- "a camera in the living room corner looking at the kitchen, wide angle" — eye at 1600 high, lens=24.
- "save three camera views of the villa for the client renders" — one call each, then the modeller renders each.
- "move LIVING-CAM-1 a bit to the left" — the new eye with replace=true.
- *Not for:* you want to save this 3D angle just as it is on screen — autocad_save_view(from_screen=true) keeps exactly that.
- *Not for:* you only want an isometric look — autocad_set_3d_view(direction='sw_iso').
- *Not for:* it is a CCTV camera symbol or camera block to place at a point — autocad_insert_block; this is a view, not a block.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a camera in the living room corner looking at the kitchen, wide angle"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: What to call the camera view, e.g. 'LIVING-CAM-1'. Spaces are fine.
- Needs `eye`: Where the camera stands, [x, y, z]. Give z: eye height inside a room is about 1600.
- Needs `target`: The point it looks at, [x, y, z], e.g. the far wall at 1200 high.
- Optional: `lens`, `look_through`, `replace`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created" | "replaced": true, "name", "handle", "eye", "target", "lens_mm", "perspective": true, "field_of_view_degrees", "distance", "view_width", "view_height", "on_screen": bool (Heron asked AutoCAD to show it), "in_drawing" ...`

**Limits and versions.**
- The same eye and target, or a lens outside 10-600 mm, is refused.
- A name already saved is refused unless replace=true; a layout's (paper space) view of that name is refused even then.
- It works on the Model tab only: a layout is refused.
- The plug-in does part of the work (`add_camera_view`, `current_view`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AE2, AE4).

### `autocad_add_light`

**What it does.** Add a real photometric light (point, spot, web or distant) for a render.
The lamp is set as a lighting designer would: brightness in lumens or candela, colour in Kelvin, the cone of a spot in degrees, or a maker's IES file. Put it inside a block with the fitting's geometry (autocad_make_block) and every insert of the fitting lights up. Lights only show in a render or a realistic visual style with default lighting off, and only as asked when LIGHTINGUNITS is 2: the tool reads LIGHTINGUNITS and warns when it is not.

**The problem it solves.**
- "put a 10 W warm white LED downlight over the dining table" — kind='spot', intensity=800, intensity_unit='lm', kelvin=3000, aimed straight down.
- "add the up and down wall light on the gate pillar" — two spots, direction [0, 0, 1] and [0, 0, -1].
- "use the Philips IES file for the bedroom downlights" — kind='web', web_file='C:/IES/philips-dl.ies'.
- "add a light in the cove for a night render" — a point light every metre or so, or a glowing strip material (autocad_create_material with luminance).
- *Not for:* the strip itself must glow in the picture — make a self-illuminated material with autocad_create_material and apply it.
- *Not for:* the light is already drawn and only needs copying — autocad_copy_entities, or make the fitting a block and autocad_insert_block.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put a 10 W warm white LED downlight over the dining table"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `position`: Where the lamp is, [x, y, z]. Give z: a downlight sits at ceiling height, e.g. [2400, 1800, 2950].
- Needs `intensity`: How bright: a number in intensity_unit. A 10 W LED downlight is about 800 lm; a 1 m cove strip about 400 lm.
- Optional: `kind`, `intensity_unit`, `target`, `direction`, `kelvin`, `rgb`, `hotspot`, `falloff`, `web_file`, `on`, and 4 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "name": str, "kind": str, "intensity": float, "intensity_unit": str, "lighting_units": int, "verified": bool, "warning"?: str}`

**Limits and versions.**
- A web light without a .ies file that exists is refused.
- A falloff smaller than the hotspot is refused.
- lux for a point, spot or web light, or cd / lm for a distant one, is refused: say which unit the number is in.
- The plug-in does part of the work (`add_light`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows K1, K2, K3, K5, K6).

### `autocad_add_mesh`

**What it does.** Make a mesh: a MESH primitive (box, cylinder, sphere...) or a mesh made from a solid (MESHSMOOTH).
A mesh is faces and vertices that can be smoothed, which a render, an export to another program, or free-form editing wants. A primitive is placed by the centre of its base, like autocad_add_solid. A mesh made from a solid, a surface or a region leaves the original where it is. One undo step.

**The problem it solves.**
- "a mesh box 1000 x 600 x 400 at the origin, smoothness 2" — shape='box'.
- "make a mesh of this solid for the render" — from_handle=the solid.
- "a 12-sided mesh cylinder" — shape='cylinder', divisions=12.
- *Not for:* you want a solid to model with (booleans, volume, fillets) - autocad_add_solid.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a mesh box 1000 x 600 x 400 at the origin, smoothness 2"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `shape`, `base`, `length`, `width`, `height`, `radius`, `top_radius`, `tube_radius`, `sides`, `divisions`, and 5 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": str, "mesh": str, "smoothness": int, "faces": int, "vertices": int, "watertight": bool, "volume": float, "verified": bool}`

**Limits and versions.**
- A shape missing a size names exactly what it needs.
- A primitive and from_handle together are refused.
- from_handle that is not a solid, surface or region is named.
- The plug-in does part of the work (`add_mesh`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AH11).

### `autocad_add_polysolid`

**What it does.** Make a wall-like solid of a width and height along a path (POLYSOLID).
Follows a line, arc, circle, polyline or spline drawn flat in plan, or a list of points; the wall goes straight up from the path's level. The path is kept. AutoCAD's .NET API has no polysolid call, so Heron builds the same shape: the path offset to each face of the wall, closed into one outline and raised by the height. One undo step.

**The problem it solves.**
- "a 200 thick, 1200 high bund wall round the tank area" — path=the outline, side='inside', width=200, height=1200.
- "a 150 x 100 kerb along this polyline" — width=150, height=100.
- "a parapet 250 wide 1100 high along the roof edge" — the edge as points.
- *Not for:* the section is not a plain rectangle, or the route climbs — autocad_extrude_profile sweeps any section along any route.
- *Not for:* it is one straight block — autocad_add_solid box.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a 200 thick, 1200 high bund wall round the tank area"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `width`: The wall's thickness.
- Needs `height`: The wall's height, straight up from the path.
- Optional: `path`, `points`, `closed`, `side`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "3dsolid", "path": str, "width": float, "height": float, "side": str, "closed": bool, "elevation": float, "path_length": float, "volume": float, "verified": bool}`

**Limits and versions.**
- Both path and points, or neither, are refused.
- A path not flat in plan is refused: the wall goes straight up.
- A path that turns tighter than the wall is wide, or crosses itself, is refused with nothing changed.
- The plug-in does part of the work (`add_polysolid`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AR4, AR6).

### `autocad_add_pyramid`

**What it does.** Make a solid pyramid or frustum (PYRAMID), standing on the centre of its base.
3 to 32 sides; a point at the top, or a flat top with top_radius. A top wider than the base makes a hopper. One side faces the front unless rotation turns it. The result gives both radii (to a side and to a corner), the volume AutoCAD measured and the volume the sizes should give. One undo step.

**The problem it solves.**
- "a 600 x 600 pyramid 900 high on the roof" — radius=300, height=900.
- "a hopper 1200 square at the top with a 300 square outlet, 900 deep" — radius=150, top_radius=600, height=900.
- "a hexagonal cap, 400 across the corners, 250 high" — sides=6, radius=200, radius_to='corner'.
- *Not for:* the shape is a box, cylinder, cone or wedge — autocad_add_solid.
- *Not for:* the shape changes from one outline to another (square to round) — autocad_loft.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a 600 x 600 pyramid 900 high on the roof"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `base`: The centre of the pyramid's base (where it stands), as [x, y] or [x, y, z].
- Needs `radius`: The base's size from its centre: to the middle of a side by default (300 makes a 600 x 600 square base).
- Needs `height`: Height, straight up.
- Optional: `sides`, `top_radius`, `radius_to`, `rotation`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "3dsolid", "sides": int, "base": [x, y, z], "height": float, "radius": float, "corner_radius": float, "top_radius": float, "top_corner_radius": float, "rotation": float, "turned": bool ...`

**Limits and versions.**
- Sides outside 3 to 32, or sizes not above zero, are refused before AutoCAD is asked.
- Needs the Heron plug-in with this operation; an older one says to update.
- The plug-in does part of the work (`add_pyramid`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AR1, AR2, AR3).

### `autocad_add_solid`

**What it does.** Make a 3D solid primitive, placed by the centre of its base.
AutoCAD's own calls place a solid by the centre of its bounding box, which is halfway up it. That is never where you mean, so these take the **base centre** and work the rest out — a 300 high cylinder at z=0 sits on z=0. Both points come back in the result. One undo step.

**The problem it solves.**
- "a 2400 x 1200 x 200 concrete pad at the origin" — shape='box'.
- "a 300 diameter column 3000 high" — shape='cylinder', diameter=300, height=3000.
- "a 400 x 200 oval duct, 2 m long, standing up" — shape='elliptical_cylinder', length=400, width=200, height=2000. Length and width are the overall sizes, not the half axes.
- *Not for:* the part is really a 2D section to be extruded — draw the profile and use autocad_extrude_profile, which gets the real shape rather than a box that is nearly it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a 2400 x 1200 x 200 concrete pad at the origin"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `shape`: 'box' and 'wedge' need length, width and height. 'cylinder' and 'cone' need radius (or diameter) and height. 'sphere' needs radius.
- Needs `base`: The centre of the solid's **base**, as [x, y] or [x, y, z] — where a drafter would put it.
- Optional: `length`, `width`, `height`, `radius`, `diameter`, `tube_radius`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": str, "shape": str, "base": [x, y, z], "centre": [x, y, z], "volume": float, "bounding_box": {"min", "max"}}`

**Limits and versions.**
- Each shape names exactly the sizes it needs and which were missing.
- radius and diameter together are refused rather than one quietly winning.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PARTLY**: rows J3 passed in AutoCAD 2027; the rest are NOT RUN (rows E22, E23, F1, J3, AL2, S7).

### `autocad_add_surface`

**What it does.** Make a flat surface (PLANESURF) or a surface through a net of curves (SURFNETWORK).
Planar: a flat surface filling each closed outline or region, or a rectangle from two corners - a ceiling plane, a slab face, a panel to thicken. Network: one surface through two sets of curves crossing each other, like a fishing net - a curved roof, a car-body-like duct fairing. The curves are kept. Give a surface a thickness with autocad_thicken_surface. One undo step.

**The problem it solves.**
- "a flat surface over this closed ceiling outline" — kind='planar', outlines=[the polyline].
- "a 3000 x 2000 planar surface at 2700" — kind='planar', corners=[[0,0,2700],[3000,2000,2700]].
- "a roof surface through these three ridge curves and the two eaves curves across them" — kind='network'.
- *Not for:* the outlines are in order along a run (a transition, a canopy edge to edge) - autocad_loft(surface=true).
- *Not for:* you want a solid - autocad_extrude_profile, or autocad_thicken_surface on the surface.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"a flat surface over this closed ceiling outline"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `kind`: 'planar' (PLANESURF): flat, from closed outlines or two corners. 'network' (SURFNETWORK): through a net of curves.
- Optional: `outlines`, `corners`, `u_curves`, `v_curves`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": str, "handles": [str] (planar), "surfaces": int (planar), "area": float, "verified": bool}`

**Limits and versions.**
- An open outline is refused: a planar surface fills a closed one.
- Fewer than two curves either way is refused for a network.
- Curves AutoCAD cannot make a surface of are refused with nothing changed.
- The plug-in does part of the work (`network_surface`, `planar_surface`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AH10).

### `autocad_apply_material`

**What it does.** Apply a material to objects, for rendering and shaded views.
Materials change how a model *looks* — in a shaded or realistic visual style, and in a render. They do not change its geometry and they do not give it a weight. The material must already be in the drawing (autocad_create_material makes one). If it is not, this says so and lists what is, rather than silently doing nothing.

**The problem it solves.**
- "make those beams look like steel" — material='Steel', layer_filter='S-BEAM'.
- "put the concrete material on the slab" before a render or a shaded view.
- *Not for:* the material is not in the drawing yet — make it with autocad_create_material first; autocad_list_materials shows what is available.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make those beams look like steel"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `material`: The material's name, exactly as it is in the drawing — autocad_list_materials gives the spellings.
- Optional: `handles`, `layer_filter`, `solids_only`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"material", "applied": int, "skipped": int, "handles": [str], "failed": [{"handle", "reason"}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows F19, F20, F21, K8).

### `autocad_chamfer_solid_edges`

**What it does.** Bevel edges of a 3D solid (CHAMFEREDGE), measured from one face.
AutoCAD chamfers the edges of one face: name the face, and by default every edge round it is bevelled. One undo step.

**The problem it solves.**
- "chamfer the top edges of the base plate 3 mm" — face='top', distance=3.
- "bevel the front edge only" — face='front' and the edge's number.
- *Not for:* the corner is on a flat 2D outline - draw the bevel into the polyline instead.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"chamfer the top edges of the base plate 3 mm"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.
- Needs `face`: The one face the chamfer is measured from: a word ('top') or its number.
- Needs `distance`: Chamfer distance across that face.
- Optional: `other_distance`, `edges`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "face": int, "edges": [int], "distance": float, "other_distance": float, "volume_before": float, "volume_after": float}`

**Limits and versions.**
- A face word that picks more than one face is refused: give its number.
- An edge that is not on that face is refused, with the face's edges.
- The plug-in does part of the work (`chamfer_edges`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows H5).

### `autocad_check_interference`

**What it does.** Find where solids run through each other — a clash check.
The question every coordination meeting asks: does the duct hit the beam? This pairs up the two sets and reports every overlap, with the volume of the overlap so the worst ones can be dealt with first. With ``create_solids`` it also draws each overlap, which is the quickest way to see what is actually fouling. Solids only — AutoCAD's own check does not handle surfaces or meshes, and anything else in the lists is reported rather than quietly skipped.

**The problem it solves.**
- "does this ductwork hit the steel" — handles=the ducts, against=the beams.
- "show me the clashes" — create_solids=true, layer='Z-CLASH', then autocad_set_3d_view and autocad_preview.
- Before issuing a model: an empty 'found' with "clear": true is the answer you want.
- *Not for:* the parts are 2D lines, not solids — this reads nothing from them. Clash checking needs a model.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"does this ductwork hit the steel"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The first set of solids — say, the ductwork.
- Optional: `against`, `create_solids`, `layer`, `color`, `limit`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"checked_pairs": int, "clashes": int, "clear": bool, "worst": {...} | null, "found": [{"a", "b", "volume", "handle", "bounding_box"}], "skipped": [{"handle", "reason"}], "stopped_early": bool}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows F9, F11, F12, F13, W8).

### `autocad_create_material`

**What it does.** Make a material in this drawing from its look: colour, texture, gloss, glass, glow.
For renders and realistic views: laterite walls, teak doors, granite floors, glass, and glowing LED strips. Once made, autocad_apply_material puts it on objects straight away. Only the settings given are written; everything else keeps AutoCAD's default. Give a texture its real size with texture_size (the width of one image tile in drawing units;

**The problem it solves.**
- "make a laterite stone material for the boundary wall" — diffuse_rgb=[178, 84, 52], glossiness=0.1, and a texture if there is a photo of the stone.
- "make the window glass" — transparency=0.9, refraction_index=1.5, reflectivity=0.1.
- "the cove LED strip must glow warm white in the night render" — luminance=2000, glow_kelvin=3000.
- "make a teak wood material from this image" — texture='D:/Textures/teak.jpg', texture_size=1000.
- *Not for:* the material is already in the drawing — apply it with autocad_apply_material (autocad_list_materials lists them).
- *Not for:* the room must actually be lit — a glowing material lights little around it; add lights with autocad_add_light.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make a laterite stone material for the boundary wall"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: The material's name, e.g. 'Laterite Stone', 'Teak Veneer', 'LED Strip 3000K'.
- Optional: `diffuse_rgb`, `texture`, `texture_size`, `texture_height`, `glossiness`, `reflectivity`, `transparency`, `refraction_index`, `luminance`, `glow_kelvin`, and 5 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created" | "replaced": true, "name": str, "handle": str, "set": [str], "in_drawing": bool, "next": str, "texture_size"?: [width, height], "warning"?: str}`

**Limits and versions.**
- A name already in the drawing is refused unless replace=true.
- An image path that is not there, or not an image, is refused.
- texture_size without a texture or bump image, or texture_height without texture_size, is refused.
- The plug-in does part of the work (`create_material`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows K8, K9, K10, K11, K12, K16, K15).

### `autocad_draw_3d_path`

**What it does.** Draw a 3D polyline: a pipe or cable route through a building, or a helix.
One object, so it moves and selects as one thing, and it can be used as a path later. A helix is generated from its radius, turns and rise — a spiral stair's handrail, a coil, a spiral duct, a thread line. One undo step.

**The problem it solves.**
- "route this drain from the gully up to the stack" — the points it passes through.
- "a handrail up the spiral stair" — helix_radius, helix_turns, helix_height.
- *Not for:* the route is flat (autocad_draw_polyline, which can carry arcs for the bends).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"route this drain from the gully up to the stack"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `points`, `helix_radius`, `helix_turns`, `helix_height`, `helix_top_radius`, `helix_centre`, `per_turn`, `closed`, `layer`, `color`, and 1 more.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "polyline3d", "vertex_count": int, "length": float, "shape": "path" | "helix"}`

**Limits and versions.**
- Needs either points or the three helix settings, and says which are missing.
- A path of fewer than two points is refused.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E32, E33).

### `autocad_edit_solid_faces`

**What it does.** Offset, taper, move or delete faces of a 3D solid (SOLIDEDIT Face).
Faces are picked by a word ('top', 'front'...) or by the numbers autocad_list_solid_faces_and_edges gives. Reports the volume before and after, so the change can be checked. One undo step.

**The problem it solves.**
- "make the 100 hole in the plate 10 bigger all round" — action='offset', the hole's face number, distance=-10 (cutting into the solid makes the hole bigger).
- "taper the sides of the plinth 5 degrees" — action='taper', faces=[side face numbers], angle=5.
- "move the end face of the beam 200 along X" — action='move', faces='right', by=[200, 0, 0].
- "take the fillet off that edge" — action='delete', the fillet's face number.
- *Not for:* pulling a flat face straight out or in — autocad_press_pull_faces.
- *Not for:* hollowing the solid — autocad_shell_solid.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make the 100 hole in the plate 10 bigger all round"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.
- Needs `action`: 'offset': move faces square to themselves by distance (a hole bigger or smaller, a side thicker). 'taper': lean faces by angle.
- Needs `faces`: Which faces: 'top', 'bottom', 'front' (the side the Front view looks at, towards -Y), 'back', 'left', 'right', or face numbers from ...
- Optional: `distance`, `angle`, `direction`, `base_point`, `by`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "action": str, "faces": [int], "volume_before": float, "volume_after": float, ...}`

**Limits and versions.**
- An option the action does not take, or a missing one, is refused before AutoCAD is asked.
- Deleting every face is refused; so is a face AutoCAD cannot close over (a box's side).
- A face word that picks nothing, or a number not there, is refused with the range.
- The plug-in does part of the work (`delete_faces`, `move_faces`, `offset_faces`, `taper_faces`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AR8, AR9).

### `autocad_extrude_profile`

**What it does.** Turn a closed 2D profile into a solid: extrude it, revolve it, or sweep it along a path.
This is how every real part gets modelled — draw the section flat, then give it depth. A flange is a profile revolved 360 degrees; a bracket is a profile extruded; a footing is a profile extruded with a taper; a duct or a cable tray following a route is a profile **swept along** that route. The curves are joined into a region first (AutoCAD's own step), the solid is made from it, and that intermediate region is then removed — it is scaffolding, not something you asked for.

**The problem it solves.**
- "extrude this outline 200 up" — handles the polyline, height=200.
- "revolve this section round the Y axis to make the flange" — revolve_angle=360, axis_point and axis_direction.
- "a tapered footing" — height plus taper.
- "run that duct section along the route I drew" — path_handle=the route polyline. That is a sweep, and it is how a duct, a pipe, a cable tray or a handrail follows a path.
- *Not for:* a plain box or cylinder will do (autocad_add_solid).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"extrude this outline 200 up"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The curves making the closed profile: lines, arcs, circles, polylines, ellipses or splines, all on one plane and joined end to end.
- Optional: `height`, `taper`, `revolve_angle`, `axis_point`, `axis_direction`, `path_handle`, `keep_profile`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "operation": "extrude" | "revolve" | "sweep", "regions_found": int, "volume": float, "bounding_box": {...}, "profile_kept": bool, "swept_along": str | null}`

**Limits and versions.**
- Curves that do not close, or are not all on one plane, come back as AutoCAD's own refusal with what to check.
- A revolve without an axis, or with an angle of zero, is refused before anything is made.
- More than one region from the curves is reported, with the count: that means the profile closed more than one loop, which is rarely meant.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E24, E26, E27, F4, S7).

### `autocad_fillet_solid_edges`

**What it does.** Round edges of a 3D solid (FILLETEDGE).
One undo step.

**The problem it solves.**
- "round the upright corners of this plinth by 25" — edges='vertical'.
- "fillet all edges of the block 5 mm" — edges='all'.
- "round just these two edges" — numbers from autocad_list_solid_faces_and_edges.
- *Not for:* the corner is on a flat 2D outline - draw it rounded (autocad_make_shape's rounded_rectangle, or a polyline with bulges).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"round the upright corners of this plinth by 25"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.
- Needs `radius`: The fillet radius, in drawing units.
- Needs `edges`: Which edges: 'all', 'vertical', 'horizontal', 'top' (the flat edges round the top), 'bottom', or edge numbers from ...

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "radius": float, "edges": [int], "volume_before": float, "volume_after": float}`

**Limits and versions.**
- A word that picks no edge, or a number that is not there, is refused with the range.
- A radius too big for the faces beside an edge is refused with nothing changed.
- The plug-in does part of the work (`fillet_edges`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **PARTLY**: rows J3 passed in AutoCAD 2027; the rest are NOT RUN (rows H1, H3, J3, AR10).

### `autocad_flatten_views`

**What it does.** Draw plan, front and side views of 3D solids as 2D linework for a shop drawing (FLATSHOT, SOLPROF).
Each view is the solids seen square on, hidden lines removed, made as a block of lines (front, top, right...) and set out beside each other so they line up: third angle by default (plan above the front, right view on the right). The model is not touched. Dimension the views with autocad_dimension_run; the answer gives each view's box on the sheet. One undo step.

**The problem it solves.**
- "flatten this bracket to plan, front and side for the shop drawing" — handles=[the solid], insert_at beside the model.
- "give me a FLATSHOT of the pipe spool, front and top only" — views=['front', 'top'].
- "SOLPROF the pump skid, first angle" — projection='first'.
- *Not for:* the drawing should show a cut through the model - autocad_section_plane.
- *Not for:* you only want to look at the model in 3D - autocad_set_3d_view.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"flatten this bracket to plan, front and side for the shop drawing"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The 3D solids to draw, by handle: one part, or a whole spool or assembly.
- Needs `insert_at`: [x, y] where the front view's lower-left corner goes, in clear space beside the model (autocad_get_extents).
- Optional: `views`, `projection`, `gap`, `join`, `tangent_edges`, `name`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str (the first view), "views": [{"view", "block", "handle", "insert", "box": [minx, miny, maxx, maxy], "lines"}], "no_lines": [view...], "projection", "gap", "laid_flat_from", "verified"}`

**Limits and versions.**
- A handle that is not a 3D solid is named, with what it is.
- A view name that is not one of the six is refused, with the list.
- No lines for any view is refused with nothing changed.
- The plug-in does part of the work (`flat_views`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AH4, AH5).

### `autocad_geo_location`

**What it does.** Place the drawing on the Earth (GEOGRAPHICLOCATION): a drawing point at a latitude and longitude, with north.
AutoCAD's online map (GEOMAP) then shows under the drawing, and the sun follows the site. Before it is kept, the plug-in asks AutoCAD's own transform where the drawing point is, and where a point 100 m along the north given is; if either reads wrong, nothing is changed. The place is the same one the sun uses (LATITUDE, LONGITUDE, set by autocad_set_sun): leave latitude and longitude out to use it, or give them and the sun's place moves to the site too. The sun's date, time and time zone are left alone.

**The problem it solves.**
- "the site is in Doha, grid A/1 is at 0,0, north is 12 degrees to the right" — latitude=25.29, longitude=51.53, north_angle=12.
- "geo-locate the drawing where the sun is already set" — no latitude or longitude.
- "take the geographic location off this drawing" — action='remove'.
- *Not for:* you only want to know where it is — autocad_get_geo_location.
- *Not for:* only the sun's date and time are wanted — autocad_set_sun.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"the site is in Doha, grid A/1 is at 0,0, north is 12 degrees to the right"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `action`, `latitude`, `longitude`, `point`, `north_angle`, `elevation`, `coordinate_system`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"located": bool, "made": bool, "latitude", "longitude", "elevation", "point": [x, y, z], "north_angle": degrees, "coordinate_system": str, "units": str, "reference_form": str, "sun_place": {"latitude", "longitude", "moved": bool} ...`

**Limits and versions.**
- Without a latitude and longitude, and with the sun's place still AutoCAD's default (San Francisco), it asks for the place instead of locating the drawing in California.
- A drawing with no units, an unknown coordinate system, or a place AutoCAD reads back wrong is refused, and nothing is changed.
- The plug-in does part of the work (`set_geo_location`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AQ11, AQ12, AQ13, AQ15).

### `autocad_get_geo_location`

**What it does.** Where the drawing is on the Earth: its geographic location, and the place the sun uses.
The drawing point that is placed, its latitude, longitude and height, the north angle (degrees clockwise from up the screen), the coordinate system and units; and LATITUDE / LONGITUDE, the sun's place, with whether the two agree. Reads only.

**The problem it solves.**
- "is this drawing geo-located?" or "where is north set?"
- Before a daylight render, to check the sun's place is the site.
- *Not for:* you want to set or change it — autocad_geo_location.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"is this drawing geo-located?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"located": bool, "latitude"?, "longitude"?, "point"?, "north_angle"?, "coordinate_system"?, "units"?, "sun_place": {"latitude", "longitude", "autocad_default": bool}, "agrees"?: bool}`

**Limits and versions.**
- A drawing with no location answers located=false, not an error.
- Without the plug-in it still gives the sun's place, and says why the location could not be read.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AQ11).

### `autocad_imprint_solid`

**What it does.** Imprint lines or shapes onto a solid's faces (SOLIDEDIT Imprint), splitting the faces along them.
A face split this way can then be pulled, offset or coloured on its own: a plinth's top split for a raised pad, a wall face split for an opening. The objects are kept, as SOLIDEDIT keeps them unless told otherwise. The result counts the faces before and after, so a miss shows. One undo step.

**The problem it solves.**
- "imprint this rectangle on the top of the plinth so I can pull a pad up" — then autocad_press_pull_faces on the new face.
- "split the wall face along this line".
- *Not for:* you want the lines cut right through the solid — autocad_slice_solid or autocad_solid_boolean.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"imprint this rectangle on the top of the plinth so I can pull a pad up"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.
- Needs `objects`: What to imprint, by handle: lines, arcs, circles, polylines, splines, regions or solids that touch or cross the solid's faces. They are kept.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "objects": [str], "faces_before": int, "faces_after": int, "edges_before": int, "edges_after": int, "volume": float}`

**Limits and versions.**
- Anything that cannot be imprinted (text, a block) is named, with what it is.
- An object that does not touch the solid changes nothing: the face count says so.
- The plug-in does part of the work (`imprint_solid`, `solid_topology`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AR11).

### `autocad_list_lights`

**What it does.** Every light in the drawing with on / off and brightness, plus the sun, default lighting and exposure.
Like AutoCAD's Lights in Model palette, from the chat: each light's handle, name, kind (point, spot, web, distant), on or off, intensity and its unit (cd, lm, lux), colour in Kelvin, layer and position. Lights inside a block definition are listed too, with the block's name and how many inserts it has: switching one switches it in every insert. It also says why a render may be dark: default lighting on, every light off, LIGHTINGUNITS not 2, and the sun's on / off, date, time and place.

**The problem it solves.**
- "which lights are on in the villa?" — before a night render.
- "why is my render black?" — it names default lighting, lights off or the sun.
- "what is the sun set to?" — date, time and place.
- *Not for:* you want to switch them — autocad_switch_lights.
- *Not for:* you want a new light — autocad_add_light.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"which lights are on in the villa?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count", "on", "off", "in_model_space", "in_blocks", "lights": [{"handle", "name", "kind", "on", "intensity", "intensity_unit", "kelvin"?, "layer", "position"?, "block"?, "inserts"?}], "default_lighting": bool, "lighting_units" ...`

**Limits and versions.**
- Needs the Heron plug-in with the list_lights operation; an older one says it does not have it.
- A variable this AutoCAD does not have reads as null.
- The plug-in does part of the work (`list_lights`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AE9, AE14, AV3).

### `autocad_list_materials`

**What it does.** List the materials in this drawing, and which objects are using them.
Worth running before you try to apply one: only a material already in the drawing can be applied, and this is the list of those. If what you want is not here, make it with autocad_create_material, or bring it in through AutoCAD's own Materials Browser — there is no automation route into Autodesk's library. Reads only.

**The problem it solves.**
- "what materials does this drawing have" before applying one.
- A material name was refused and you need the real spelling.
- *Not for:* you want the weight of something — a material carries no density. Use autocad_solid_properties for the volume and multiply by a density you state.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what materials does this drawing have"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count": int, "materials": [{"name", "description", "in_use": int}], "note": str}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows F18).

### `autocad_list_solid_faces_and_edges`

**What it does.** Number a solid's faces and edges, so a fillet, chamfer, shell or press-pull can pick them.
Each face: its kind (plane, cylinder...), area, centre, which way a flat one faces, and its edges. Each edge: its kind (line, arc, circle...), ends and length. Changes nothing.

**The problem it solves.**
- "which edges of this plinth are along the top" — then pick them by number in autocad_fillet_solid_edges.
- "number the faces of this solid".
- *Not for:* a word says it already ('top', 'vertical'): the edit tools take the word straight.
- *Not for:* you want the volume or centroid - autocad_solid_properties.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"which edges of this plinth are along the top"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.
- Optional: `limit`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"handle": str, "volume": float, "face_count": int, "edge_count": int, "faces": [...], "edges": [...], "how_to_pick": str}`

**Limits and versions.**
- A handle that is not a 3D solid is named, with what it is.
- Needs the Heron plug-in 1.2.0 or newer; an older one says to update.
- The plug-in does part of the work (`solid_topology`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **PARTLY**: rows J3 passed in AutoCAD 2027; the rest are NOT RUN (rows H2, J3).

### `autocad_loft`

**What it does.** Make a solid through closed outlines in order (LOFT), or a surface through open ones.
A rectangular-to-round duct transition, a tapered column, a hopper: draw each outline at its own height or position, then loft through them. With ``surface=true`` the loft is a surface instead, and the outlines may be open: a canopy through curved edges, a roof sheet between two arcs. The outlines are kept, as with DELOBJ off. One undo step.

**The problem it solves.**
- "make a transition from the rectangular duct to the round duct" (600 x 400 to 450 round) — the rectangle and the circle at their heights, in order.
- "loft these three sections into a tapered column".
- "a canopy surface through these two curved edges" — surface=true; the arcs are open, so it is a surface.
- *Not for:* one outline goes straight up or along a route - autocad_extrude_profile (extrude, revolve or sweep).
- *Not for:* the surface is flat, or spans a net of curves - autocad_add_surface (planar or network).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make a transition from the rectangular duct to the round duct"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `sections`: The closed outlines, by handle, IN ORDER along the loft (bottom to top, start to end).
- Optional: `guides`, `path`, `ruled`, `closed`, `surface`, `layer`, `color`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "3dsolid" (or a surface type), "sections": int, "volume": float (a solid) or "area": float (a surface), "verified": bool}`

**Limits and versions.**
- An open outline is refused for a solid: a loft of open shapes is a surface; give surface=true.
- Guides and a path together are refused: a loft follows one or the other.
- Outlines AutoCAD cannot loft (crossing, out of order) are refused with nothing changed.
- The plug-in does part of the work (`loft`, `loft_surface`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows H8, T5, AH9).

### `autocad_press_pull_faces`

**What it does.** Push or pull flat faces of a 3D solid (PRESSPULL on a face, SOLIDEDIT Extrude).
Raise a plinth, deepen a recess, stretch a box to a new length. One undo step.

**The problem it solves.**
- "pull the top of the plinth up another 150" — faces='top', distance=150.
- "push that face in 20".
- *Not for:* the shape is still a flat outline - autocad_extrude_profile turns it into a solid.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"pull the top of the plinth up another 150"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.
- Needs `faces`: Which faces: 'top', 'bottom', 'front' (the side the Front view looks at, towards -Y), 'back', 'left', 'right', or face numbers from ...
- Needs `distance`: How far: positive pulls the face out of the solid, negative pushes it in.
- Optional: `taper`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "faces": [int], "distance": float, "volume_before": float, "volume_after": float}`

**Limits and versions.**
- A curved face is refused: this moves flat faces.
- A distance of 0 is refused before AutoCAD is asked.
- The plug-in does part of the work (`press_pull`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows H7, AR11).

### `autocad_section_plane`

**What it does.** Cut a section through a 3D model and draw the 2D section as a block (SECTIONPLANE, Generate Section).
A section plane is put through the points and kept in the model; the 2D section of the solids it cuts (their cut outlines, hatched, and what is seen beyond, hidden lines removed) is made as one block, laid flat on the sheet at insert_at, the way AutoCAD's Generate Section / Elevation makes a 2D section. Right on the section is along the line from the first point to the second; up is up. One undo step.

**The problem it solves.**
- "cut a section A-A through the plant room along this line and put it on the right" — two points, insert_at.
- "section through the riser looking north" — two points on an east-west line, look_towards a point to the north.
- "a plan cut of the services at 2.7 m" — three points at z=2700.
- *Not for:* you want views of a part from outside, not a cut - autocad_flatten_views.
- *Not for:* the solid itself should be cut in two - autocad_slice_solid.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"cut a section A-A through the plant room along this line and put it on the right"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `points`: Two points: a vertical cut along the line between them, as a section line on a plan.
- Needs `insert_at`: [x, y] where the 2D section's lower-left corner goes, in clear space (autocad_get_extents).
- Optional: `look_towards`, `handles`, `hatch`, `background`, `keep_plane`, `name`, `plane_layer`, `layer`, `color`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "block": str, "section_plane": str, "solids": int, "cut": int, "lines": int, "size": [w, h], "looking": [x, y, z], "right", "up", "laid_flat_from", "verified"}`

**Limits and versions.**
- Points that make no line or no plane are refused, with why.
- A plane that cuts and sees none of the solids is refused with nothing changed.
- A handle that is not a 3D solid is named, with what it is.
- The plug-in does part of the work (`section_plane`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AH6, AH7, AH8).

### `autocad_separate_solid`

**What it does.** Separate a solid made of pieces that do not touch into one solid per piece (SOLIDEDIT Separate).
The solid keeps one piece; each other piece becomes a new solid on the same layer, with the same colour. Pieces that touch, even along an edge, stay one solid. One undo step.

**The problem it solves.**
- "the union made one solid of the two pump skids, split them apart again".
- "after the slice this is two lumps in one solid, separate them".
- *Not for:* you want to cut a solid in two — autocad_slice_solid.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"the union made one solid of the two pump skids, split them apart again"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "volume_before": float, "piece_count": int, "pieces": [{"handle": str, "volume": float}]}`

**Limits and versions.**
- A solid that is one piece already is refused: there is nothing to separate.
- The plug-in does part of the work (`separate_solid`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AR12).

### `autocad_set_3d_view`

**What it does.** Look at the model from a named direction, in a chosen visual style.
What you need before ``autocad_preview`` can show a 3D model usefully: a south-west isometric in the hidden style reads like a shop drawing, while plan plus 2D wireframe is back to normal drafting. This only changes what is on screen, so it needs no padlock — the same level as autocad_zoom. It does not move or change a single object.

**The problem it solves.**
- "show me the model in 3D" — direction='sw_iso', visual_style='hidden', then autocad_preview.
- "back to plan" — direction='top', visual_style='2dwireframe'.
- *Not for:* you want a viewport on a sheet (autocad_add_viewport).
- *Not for:* the view is for a render for the client — autocad_add_camera_view sets the camera up; Heron does not render, the modeller presses Render.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"show me the model in 3D"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `direction`, `vector`, `visual_style`, `zoom_extents`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"direction": [x, y, z], "named": str | null, "visual_style": str | null, "visual_style_found": str | null, "visual_style_warning"?: str, "zoomed": bool, "not_set": [str]}`

**Limits and versions.**
- An unknown direction or visual style is named, with the list of real ones, before anything changes.
- The visual style is set by typing the VSCURRENT command (it is a command, not a system variable). If AutoCAD does not take the option, the command is cancelled and the style is in "not_set".
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E34, E35, F20, K13, AE1, BD3, AM6, AH1).

### `autocad_set_render_exposure`

**What it does.** Set the render's Exposure and White balance, as in the Render Environment & Exposure palette.
Written to AutoCAD's EXPVALUE and EXPWHITEBALANCE variables, then read back. The old LOGEXP... variables are not used: they are gone in 2027. If this AutoCAD has no EXPVALUE, nothing changes and the answer says to use the palette (RENDEREXPOSURE). One undo step. It does not render: press Render in AutoCAD.

**The problem it solves.**
- "the render is too dark" — exposure one or two lower than it is (autocad_list_lights shows the current one).
- "the night render looks too yellow" — white_balance a little lower than the lamps' Kelvin.
- *Not for:* the lights themselves are wrong — autocad_switch_lights or autocad_add_light.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"the render is too dark"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `exposure`, `white_balance`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"exposure": {"from", "to"}?, "white_balance": {"from", "to"}?, "not_set"?: [str], "note": str}`

**Limits and versions.**
- Values outside the ranges are refused before anything changes.
- A variable this AutoCAD does not have refuses the call, naming the palette instead; nothing is changed.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AE14, AV3).

### `autocad_set_sun`

**What it does.** Set the sun for a daylight render: the date, the clock time and the place, then read them back.
The place is the drawing's LATITUDE, LONGITUDE and TIMEZONE; the date and time live on the current model viewport's sun, which Heron's plug-in sets (AutoCAD has no variable for them). Only what is given changes: a time on its own keeps the sun's date. The answer reads everything back from AutoCAD, with the sun's azimuth and altitude as AutoCAD works them out. One undo step. It does not render: press Render in AutoCAD.

**The problem it solves.**
- "set the sun for Doha, 21 June at 10 in the morning" — date='2026-06-21', time='10:00', latitude=25.29, longitude=51.53, utc_offset=3.
- "make it late afternoon" — time='16:30' only; the date and place stay.
- "turn the sun on for the daylight render" — on=true (and autocad_switch_lights(default_lighting=false)).
- *Not for:* you only want to know what it is set to — autocad_list_lights reads the sun too.
- *Not for:* it is a night render — autocad_switch_lights(sun=false).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"set the sun for Doha, 21 June at 10 in the morning"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `date`, `time`, `latitude`, `longitude`, `utc_offset`, `daylight_saving`, `on`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"set": [str], "sun_made": bool, "sun": {"on", "date", "time", "daylight_saving", "latitude", "longitude", "timezone", "utc_offset", "azimuth", "altitude", "dxf"}, "not_set"?: [str], "warning"?: str}`

**Limits and versions.**
- A date or time that does not exist, or a UTC offset that is not a time zone, is refused before anything changes.
- It works on the Model tab only: a layout is refused.
- If the sun's date cannot be set after the place was, the error says the place was set and Ctrl+Z takes it back.
- The plug-in does part of the work (`list_lights`, `set_sun`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AE5, AE6, AE7, AE8, AQ12).

### `autocad_shell_solid`

**What it does.** Hollow a 3D solid to a wall thickness, leaving chosen faces open (SOLIDEDIT Shell).
A tank, a tray, a sump, a box section: model the outside, then shell it. One undo step.

**The problem it solves.**
- "make this box an open-top tank with 10 mm walls" — thickness=10, remove_faces='top'.
- "hollow the column, 5 mm wall".
- *Not for:* you want a pipe or duct from a route - autocad_extrude_profile sweeps a ring along it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"make this box an open-top tank with 10 mm walls"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The 3D solid, by handle.
- Needs `thickness`: Wall thickness, in drawing units.
- Optional: `remove_faces`, `outward`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"handle": str, "thickness": float, "outward": bool, "removed_faces": [int], "volume_before": float, "volume_after": float}`

**Limits and versions.**
- A wall thicker than the solid allows is refused with nothing changed.
- The plug-in does part of the work (`shell`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows H6).

### `autocad_slice_solid`

**What it does.** Cut a solid with a plane — a real section through a model.
This is how a 3D model becomes a section drawing: slice it at the level or on the line the section mark shows, then look at the cut face. Keeping both halves lets you move one aside and see inside. The plane is given the way a drafter says it — "horizontally at this level" — and the three points AutoCAD actually wants are worked out here.

**The problem it solves.**
- "section that model at 1500 above floor level" — plane='horizontal', through=[0, 0, 1500].
- "cut this fitting in half so I can see the bore" — plane='vertical_y', keep='both'.
- *Not for:* you want a 2D section to dimension — slice it, then look at the cut face with autocad_set_3d_view, or take the outline off it.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"section that model at 1500 above floor level"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: The solids to cut. Each is cut by the same plane.
- Needs `through`: A point the cutting plane passes through, as [x, y] or [x, y, z]. For a horizontal cut this is the level.
- Optional: `plane`, `normal`, `keep`, `layer`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"sliced": int, "plane": {"kind", "points"}, "results": [{"handle", "kept_handle", "new_handle", "volume_before", "volume_after", "new_volume"}], "failed": [{"handle", "reason"}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows F5, F7, F8, S7).

### `autocad_solid_boolean`

**What it does.** Join, cut or intersect 3D solids — the real modelling step.
The first solid is the one that remains and is modified; the others are **consumed by AutoCAD**, which is how its own UNION, SUBTRACT and INTERSECT behave. The result's handle is the first solid's, unchanged. One undo step, so one Ctrl+Z puts them all back.

**The problem it solves.**
- "cut these four bolt holes out of the plate" — operation='subtract', handle the plate, others the cylinders.
- "join the base and the upstand".
- *Not for:* the objects are 2D (regions boolean the same way, but a 2D outline is usually better edited directly).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"cut these four bolt holes out of the plate"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `operation`: 'union' joins them into one. 'subtract' cuts the others out of the first — a plate with holes is a box minus some cylinders.
- Needs `handle`: The solid that stays and is changed. For 'subtract' this is the one being cut.
- Needs `others`: The other solids. **These are consumed** — AutoCAD removes them as it applies the operation.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"operation", "handle", "consumed": [str], "failed": [...], "volume_before": float, "volume_after": float, "bounding_box": {...}}`

**Limits and versions.**
- A handle that is not a 3D solid or a region is named before anything is changed, so nothing is consumed by mistake.
- The volume before and after is reported: a subtract that removed nothing shows up as an unchanged volume.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E28, E29, E30, AR12, BG5).

### `autocad_solid_properties`

**What it does.** Volume, centroid, bounding box and moments for 3D solids — what a take-off needs.
Give a density and the volume becomes a weight: that is the number a fabricator and a lifting plan both want. Regions report their area and perimeter instead of a volume.

**The problem it solves.**
- "how much concrete is in these pads" — total_volume, then multiply by the density yourself.
- "where is the centre of gravity of this frame" — centroid.
- *Not for:* you want a length or an area of 2D linework (autocad_measure, autocad_total_length).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"how much concrete is in these pads"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `handles`: The solids or regions to measure, by handle.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: { "count": int, "total_volume": float, "total_area": float, "items": [{"handle", "type", "volume", "area", "perimeter", "centroid", "bounding_box", "size", "moment_of_inertia", "radii_of_gyration"}], "unreadable": [{"handle" ...`

**Limits and versions.**
- Anything that reports no volume or area is listed in "unreadable" with its type, rather than failing the call.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows E31, AH1).

### `autocad_switch_lights`

**What it does.** Switch lights on or off, and the sun and AutoCAD's default lighting, like the Lights in Model palette.
Name the lights or give their handles (autocad_list_lights lists them), or switch all of them at once. A light inside a block definition switches in every insert of that block. If one name is not found nothing is switched, and the answer lists the lights there are. The sun (SUNSTATUS) and default lighting (DEFAULTLIGHTING) are plain variables of the current viewport; default lighting is switched first, so turning the sun on with default lighting off asks AutoCAD nothing.

**The problem it solves.**
- "night render: sun off, default lighting off, all the downlights on" — sun=false, default_lighting=false, all_lights='on'.
- "turn off the pendant over the dining table" — turn_off=['DINING-PENDANT'].
- "daylight render only" — all_lights='off', sun=true, default_lighting=false.
- *Not for:* the light is too bright or the wrong colour — make it again with autocad_add_light; this only switches.
- *Not for:* you want the sun's date and time — autocad_set_sun.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"night render: sun off, default lighting off, all the downlights on"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `turn_on`, `turn_off`, `all_lights`, `sun`, `default_lighting`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"changed": int, "lights": [{"handle", "name", "on", ...}], "set": [str], "sun": bool, "default_lighting": bool, "not_set"?: [str], "warning"?: str}`

**Limits and versions.**
- A light name that is not in the drawing refuses the whole switch and lists the names there are; nothing is changed.
- A light on a locked layer refuses the switch: unlock the layer.
- A variable AutoCAD refuses is in "not_set"; the rest are set.
- The plug-in does part of the work (`switch_lights`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AE10, AE11, AE12).

### `autocad_thicken_surface`

**What it does.** Make a solid from a surface by giving it a thickness (THICKEN). The surface is kept.
One undo step.

**The problem it solves.**
- "thicken this roof surface 200".
- "give the lofted canopy surface a 3 mm skin".
- *Not for:* the shape is a flat closed outline or a region - autocad_extrude_profile makes it a solid directly.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"thicken this roof surface 200"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handle`: The surface, by handle.
- Needs `thickness`: Thickness, in drawing units.
- Optional: `both_sides`, `layer`, `color`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"created": true, "handle": str, "type": "3dsolid", "surface": str, "thickness": float, "both_sides": bool, "verified": bool}`

**Limits and versions.**
- Anything that is not a surface is named, with what it is.
- A thickness bigger than the surface's tightest curve is refused with nothing changed.
- The plug-in does part of the work (`thicken`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows H9, AH9).

### `autocad_transform_3d`

**What it does.** Move, rotate, mirror or array in three dimensions.
The ordinary modify tools work on the flat: they move in XY and rotate about Z. A model needs more — tip a brace about the X axis, mirror a handed assembly in a vertical plane, stack a floor layout up through a building. That is this. One undo step, however many objects.

**The problem it solves.**
- "lift that whole frame 3500 up" — move, displacement=[0, 0, 3500].
- "tip that brace 30 degrees about the X axis" — rotate, axis_point, axis_direction=[1,0,0], angle=30.
- "mirror this handed bracket about the horizontal plane at 2000" — mirror, plane_point=[0,0,2000], plane_normal=[0,0,1].
- "copy this floor up 12 times at 3600" — array, levels=13, level_spacing=3600.
- *Not for:* everything stays flat — autocad_move_entities, autocad_rotate_entities and autocad_mirror_entities are simpler and read better for 2D work.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"lift that whole frame 3500 up"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `handles`: What to move. Any entities, not only solids.
- Needs `operation`: 'move' shifts by a displacement that can include Z. 'rotate' turns about any axis in space, not just the Z axis. 'mirror' reflects in a plane.
- Optional: `displacement`, `axis_point`, `axis_direction`, `angle`, `plane_point`, `plane_normal`, `keep_original`, `levels`, `level_spacing`, `coords`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"operation", "count": int, "handles": [str], "new_handles": [str], "failed": [{"handle", "reason"}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows F14, F15, F16, F17, S7).


## Checks and reports

Check lists, standards checks, drawing reports, audit and purge.

### `autocad_audit`

**What it does.** Check the drawing database for errors and optionally repair them.
Run this when a drawing behaves oddly — entities that will not select, commands that fail without explanation, a file that crashes on open.

**The problem it solves.**
- A drawing came in from outside and behaves oddly, or AutoCAD has reported an error in it.
- Before handing a cleaned-up import on. It needs Admin, because repairing changes the database itself.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Admin** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Admin** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Check the drawing database for errors and optionally repair them."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `fix_errors`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"audited": true, "fixed": bool, "note": str}`

**Limits and versions.**
- AUDIT writes its findings to AutoCAD's text window rather than returning them over COM, so the counts are not available here. Check the .adt log file beside the drawing for the detail.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_check_folder`

**What it does.** Run a check list over every drawing in a folder: each opened read only, checked, closed unsaved.
The same check list as autocad_checklist, with each drawing's own project changes, one drawing at a time. Each is opened read only and closed without saving; one that was already open is checked where it is and left open. The drawing the modeller was in is active again at the end. Each drawing gets its verdict and coverage line, worst first; one that cannot be opened is NOT RUN with the reason. PASS means the checked value is met for what Heron read, never that a drawing complies.

**The problem it solves.**
- "check every drawing in the issue folder before we send it".
- "which sheets in this folder still have things on layer 0?"
- *Not for:* only the open drawing - autocad_checklist is faster.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"check every drawing in the issue folder before we send it"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `folder`: The folder of drawings, e.g. 'D:\Projects\Tower\MEP\Issue 03'.
- Optional: `name`, `subfolders`, `max_drawings`, `max_entities`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"folder", "checklist", "list" {"file", "from"}, "verdicts" {state: n}, "worst", "drawings": [{drawing, verdict, coverage, failed, no_data, reason, warning, project_changes}], "left_out", "pass_means", "warning"}`

**Limits and versions.**
- A folder that is not there, or holds no .dwg: said, nothing opened.
- A drawing that will not open (newer version, damaged, a box AutoCAD showed): NOT RUN with AutoCAD's reason; the rest go on.
- The modeller's emergency stop (HERONSTOP): the rest are left out.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows Y4).

### `autocad_check_standards`

**What it does.** Check the drawing's layers and objects against layer standards, or against a reference drawing.
Rules: a layer name pattern, required layers with colour and linetype, nothing on layer 0, ByLayer colours and linetypes, overlapping dimensions. A reference drawing (the office .dws, a template, any .dwg or .dxf): every layer, text style, dimension style and linetype it has must be in this drawing with the same values - layers by colour, linetype, lineweight and plot; text styles by font, big font, height, width and oblique angle; dimension styles and linetypes by name only.

**The problem it solves.**
- "does this drawing follow our layer standard" - before issuing it, with the findings worst first.
- "check this drawing against our office DWS" or "against the template S:\CAD\MEP.dwt" -> reference; the layers and styles that are missing or differ.
- "check the layers against our office layer standard" -> layer_standard='office'; "against this CSV" -> its path.
- After a batch of drawing, to catch objects left on the wrong layer.
- *Not for:* you want it put right rather than reported - autocad_remap_layers and autocad_tidy_entities do that, and autocad_import_from_drawing brings missing layers and styles in from the standard.
- *Not for:* the modeller's own check list is wanted - autocad_checklist.
- *Not for:* loading or showing the office layer standard - autocad_layer_standard.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"does this drawing follow our layer standard"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `rules`, `rules_path`, `reference`, `layer_standard`, `flag_extra`, `max_entities`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"checked", "passed", "source", "pass_means", "summary" {rule: count}, "findings" [...], "truncated", "reference" {"file", "read_by", "compared", "left_out"}, "layer_standard" {"source", "file", "example", "layers", "compared" ...`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D31, U10, BI1, BI2, BI3, BI4, AG5, AT4, AT8, S2).

### `autocad_checklist`

**What it does.** Run the modeller's own check list on the drawing: PASS, FAIL, NO DATA or NOT RUN for each line.
The modeller says the checks in their own words ("nothing on layer 0", "every A1 title block filled in", "text 2.5, 3.5 or 5 only"); save them once as a named office list with each sentence mapped to a catalogue check, then run the list before every issue. 'before issue' ships ready to run. Each failed check names its objects, so autocad_show can put them on screen. Running changes nothing in the drawing.

**The problem it solves.**
- "check this drawing before I issue it" -> run 'before issue'.
- "save these as our sheet checks: nothing on 0, title blocks filled, text 2.5 or 3.5" -> save, then run.
- "on this job colours ByLayer is only low, and we don't check xrefs" -> project with changes [{id: bylayer_colour, severity: low}, {id: xrefs_found, on: false}].
- "which of my checks failed?" then autocad_show the handles.
- *Not for:* the run should be saved as Excel and HTML to send with the drawings - autocad_checklist_report.
- *Not for:* the layers should be put right, not reported - autocad_remap_layers / autocad_tidy_entities.
- *Not for:* a layer table standard with colours and linetypes per layer is wanted - autocad_check_standards takes that.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"check this drawing before I issue it"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `action`, `name`, `checks`, `changes`, `folder`, `max_entities`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON. run: {"checklist", "verdict", "coverage", "counts", "pass_means", "lists" {"office", "project"}, "checks_used" [{"id", "label", "from"}], "results": [{"id", "check", "label", "state", "severity", "source", "from", "target" ...`

**Limits and versions.**
- A check that is not in the catalogue, or is missing a parameter, is refused when saving, naming the line; nothing is saved.
- A project change that adds a check, or changes anything but severity, target or on, is refused naming the line; nothing is kept.
- A check that cannot be decided (no such title block, xrefs unreadable, only part of the objects read) is NO DATA with the reason, never a silent PASS.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows O3, U1, U3, AG9).

### `autocad_checklist_report`

**What it does.** Save a check list result as a new Excel workbook and HTML page next to the drawing.
The same run as autocad_checklist (office list plus this project's changes), saved as '<drawing> - checklist <list> - <date>.xlsx' and '.html' in the drawing's own folder, to send with the drawings or keep with an issue. An earlier report is never overwritten: the next one gets a number, ' (2)', ' (3)'. Writing files needs the Publish padlock; the drawing itself is not changed. The files say what PASS means: the checked value is met against the source named on the line.

**The problem it solves.**
- "save the check list results so I can send them with the drawings" -> report 'before issue'.
- "make an Excel of the checks for this issue".
- *Not for:* the modeller only wants to see the results in the chat - autocad_checklist(action='run') changes and writes nothing.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"save the check list results so I can send them with the drawings"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `name`, `max_entities`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"saved" {"xlsx", "html"}, "verdict", "coverage", "pass_means", "checklist"}`

**Limits and versions.**
- An unsaved drawing has no folder: it says to save it first, and writes nothing.
- A file that appeared between choosing the name and writing it is never replaced: the call stops and says so.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows U6, U7).

### `autocad_drawing_report`

**What it does.** Everything a received drawing holds, in one read: units, layers, blocks, xrefs, styles, sheets and what is drawn.
The check before working on a consultant's or client's DWG: which units it is in, which layers are off, frozen or locked, which blocks and xrefs it carries, its text and dimension styles and linetypes, its sheets (layouts) with their paper, and how many of each kind of object are in model space (counted up to 50,000). Changes nothing.

**The problem it solves.**
- "what is in this drawing the consultant sent?"
- "audit this DWG before I start: units, layers, xrefs".
- "how many sheets does this drawing have and on what paper?"
- *Not for:* you need one list in detail - autocad_list_layers, autocad_list_blocks, autocad_list_styles or autocad_list_layouts.
- *Not for:* you are checking against a rules file - autocad_check_standards.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what is in this drawing the consultant sent?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `count_objects`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"drawing": str, "path": str, "units": str, "layers": {"count": int, "names": [str], "off": [str], "frozen": [str], "locked": [str]}, "blocks": {"count": int, "names": [str]}, "xrefs": [{"name": str, "saved_path": str}] ...`

**Limits and versions.**
- Model space is counted up to 50,000 objects; past that the answer says so and gives the total.
- Uses the plug-in for speed when it can (from plug-in 1.8.0); otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows I2, I8, AS10, AS11).

### `autocad_purge`

**What it does.** Remove unused blocks, layers, linetypes and styles from the drawing.
Purging only removes definitions nothing references, so it cannot delete visible geometry. It is the standard cleanup before issuing a drawing, and often shrinks the file substantially.

**The problem it solves.**
- "clean this drawing up before I send it".

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Admin** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Admin** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"clean this drawing up before I send it"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `target`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"purged": str, "layers_before": int, "layers_after": int, "blocks_before": int, "blocks_after": int}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows BD2, S6).

### `autocad_share_checklist`

**What it does.** Share a check list with the team: the office list into the office folder, or a project's changes into its folder.
office_list writes '<office folder>\<list>.json' (the office folder is set once per PC with autocad_checklist(action='office_folder')); every PC that points at that folder runs it from then on. project_changes writes '<the drawing's folder>\Heron check list changes.json', so everyone who opens a drawing from that folder runs the list with the same changes (severity, target, on/off only, as always); it wins over each PC's own.

**The problem it solves.**
- "put our 'before issue' list on the shared drive for everyone" -> office_list (set the office folder first).
- "everyone on this job skips the xref check" -> project_changes with changes [{id: xrefs_found, on: false}].
- After autocad_checklist(action='project') on this PC: "share these changes with the team" -> project_changes with no changes.
- *Not for:* the list is only for this PC - autocad_checklist(action='save').
- *Not for:* the run's results should be sent with the drawings - autocad_checklist_report.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"put our 'before issue' list on the shared drive for everyone"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `share`: 'office_list': put the check list 'name' in the office folder, for every PC. 'project_changes': put this project's changes to the list in the ...
- Optional: `name`, `checks`, `changes`, `replace`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"written", "file", "list", "checks" | "changes", "from", "replaced", "saved_by"}, or {"written": false, "said"} when the file already holds exactly this.`

**Limits and versions.**
- No office folder set, or it cannot be reached: refused; nothing written.
- A different file already there: refused naming who and when, unless replace=true.
- A wrong check or change is refused naming the line; nothing written.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AG9, AG13, AG14).


## Files and drawings

Open, create, save, export, switch drawing, read a file without AutoCAD.

### `autocad_create_drawing`

**What it does.** Create a new drawing and make it active.
The new drawing becomes active immediately, so later drawing tools target it without an extra step.

**The problem it solves.**
- "start a new metric drawing" -> template="acadiso.dwt".
- *Not for:* a drawing is already open and you only want to draw in it; the drawing tools already target the active drawing.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"start a new metric drawing"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `template`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"created": true, "name": str, "units": str, "template": str}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_etransmit`

**What it does.** Pack this drawing with everything it needs - AutoCAD's eTransmit.
For issuing a drawing to a consultant: the saved drawing, its xrefs (nested ones too), raster images, PDF / DWF / DGN underlays, the font files its text styles use and the plot style tables its layouts use, all in one folder (or one .zip) beside the drawing, with a 'transmittal report.txt' listing what was packed and what was missing. Nothing is ever written over: an earlier pack of the same name gets ' (2)'. The drawing is packed as last saved, so an unsaved drawing is refused.

**The problem it solves.**
- "eTransmit this drawing to send to the consultant".
- "zip the drawing with its xrefs and fonts".
- "what files does this drawing need? Is anything missing?" — list_only=true.
- *Not for:* you want a PDF of the sheets - autocad_publish_pdf.
- *Not for:* you only want the xref tree and broken paths - autocad_xref_tree.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"eTransmit this drawing to send to the consultant"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `as_zip`, `folder`, `name`, `list_only`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"pack": str, "packed": [{"kind", "name", "from", "to", "used_by"}], "missing": [{"kind", "name", "used_by"}], "clashes": [...], "system_fonts": [str], "written": [str]}`

**Limits and versions.**
- An unsaved drawing, or one with unsaved changes, is refused: save it first.
- A folder that does not exist is refused before anything is written.
- Files not found are listed under 'missing', never guessed.
- The plug-in does part of the work (`list_dependencies`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AD10, AD11).

### `autocad_export`

**What it does.** Export the active drawing to DXF, PDF, DWF or another supported format.
The format comes from the file extension. DXF, WMF, SAT, BMP, EPS and STL are written by AutoCAD's exporter. PDF plots the active layout's extents, centred and scaled to fit the sheet, through the "DWG To PDF" plotter; DWF plots the same way through the "DWF6 ePlot" plotter (Output > Export DWF). The layout's own page setup is put back afterwards.

**The problem it solves.**
- "give me this drawing as a DXF" -> path ending in .dxf.
- "export a PDF of the current layout" -> path ending in .pdf.
- "PDF it on A1" -> path ending in .pdf, paper_size="A1".
- "the consultant wants a DWF of this sheet" -> path ending in .dwf, area="layout", scale="1:1".
- *Not for:* you want to save the .dwg itself (use autocad_save_drawing).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"give me this drawing as a DXF"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `path`: Output file path including extension, e.g. 'D:\out\plan.dxf', 'D:\out\plan.pdf' or 'D:\out\plan.dwf'. The extension selects the format.
- Optional: `paper_size`, `area`, `corner1`, `corner2`, `view_name`, `scale`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"exported": true, "path": str, "format": str, "size_bytes": int} PDF adds "layout" (e.g. "Model"), "paper", the sheet used (e.g. "ISO full bleed A3 (420.00 x 297.00 MM)"), "area", and "view" / "scale" when those were given.`

**Limits and versions.**
- Verifies a new file actually appeared on disk afterwards, since AutoCAD's plotter can report success without writing anything — for example when the old PDF is open, and locked, in a viewer.
- An unknown paper_size lists the sizes the plotter does offer.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D19, D20, AF22, AQ10).

### `autocad_list_drawings`

**What it does.** List every drawing currently open in AutoCAD.
Use before autocad_switch_drawing when more than one file is open, so the target can be named exactly.

**The problem it solves.**
- "which drawings are open" before switching between them.
- A change was refused because the active drawing is not the one you meant.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"which drawings are open"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count": int, "drawings": [{"index": int, "name": str, "path": str, "saved": bool, "active": bool}]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_open_drawing`

**What it does.** Open an existing drawing file and make it active.

**The problem it solves.**
- "open the architectural background" so you can reference or copy from it.
- *Not for:* you only want its blocks or layers - autocad_import_from_drawing leaves the file closed.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"open the architectural background"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `path`: Full path to a .dwg or .dxf file, e.g. 'D:\Projects\Site\ground-floor.dwg'.
- Optional: `read_only`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"opened": true, "name": str, "path": str, "units": str, "read_only": bool, "model_space_entities": int}`

**Limits and versions.**
- Returns a path error naming the resolved path if the file does not exist, before AutoCAD is contacted at all.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_read_file`

**What it does.** Read a DXF or DWG file on disk without AutoCAD: layers, blocks and counts, text, attributes, extents.
Works with AutoCAD closed, and never changes the file. A DXF is read directly. A DWG (or a .dws standards file, or a .dwt template) is converted first, from a temporary copy, by the free ODA File Converter, when it is installed on this PC: Heron finds it, it never downloads it. Without it a DWG is refused, saying plainly that it needs AutoCAD (open it there) or the ODA converter, or a DXF of it. The answer is what was last saved: changes not yet saved in AutoCAD are not in the file.

**The problem it solves.**
- "what's in this DXF the contractor sent?" with AutoCAD closed -> the summary.
- "which layers does M-101.dwg use?" or "how many valves are in that file?" without opening it -> layers / blocks.
- "list the title block values of every drawing in this folder" -> attributes, one file at a time, block_name='TITLE*'.
- "find the text 'FCU-03' in the old DXF".
- *Not for:* the drawing is open in AutoCAD - autocad_list_layers, autocad_list_blocks, autocad_find_text and autocad_extract_attributes read it there, with the changes not yet saved.
- *Not for:* a whole folder should be checked against a check list - autocad_check_folder.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed, and it answers even with AutoCAD closed.

**How to use it.**
1. Nothing to prepare: AutoCAD may be closed. (With AutoCAD open, the drawing it names is the one Heron reads.)
2. Ask Claude, for example: *"what's in this DXF the contractor sent?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `path`: The file's full path: a .dxf, or a .dwg / .dws / .dwt (those need the ODA File Converter).
- Optional: `what`, `layer`, `block_name`, `contains`, `max_items`, `output`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"file", "read_by", "note", ...}. summary: {"format", "units", "extents" {"min", "max", "from"}, "layers", "objects", "model_by_type", "text", "blocks", "most_placed_blocks", "layouts", "xrefs"};`

**Limits and versions.**
- A DWG with no ODA File Converter on this PC is refused with the three ways round it; nothing is downloaded.
- A damaged DXF is read in recover mode and the answer says so; the file is never changed.
- A file over 250 MB, a locked file or a missing one is refused, saying why.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AG1, AG2, AG4, AG15).

### `autocad_save_drawing`

**What it does.** Save the active drawing, optionally to a new path.

**The problem it solves.**
- The work is finished and checked. It needs the Publish padlock, because it writes a file.
- *Not for:* you are mid-job - leave it unsaved so one Ctrl+Z still gets you out.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Publish** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Publish** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Save the active drawing, optionally to a new path."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `path`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"saved": true, "path": str}`

**Limits and versions.**
- A never-saved drawing with no path given returns an error asking for one, rather than triggering AutoCAD's blocking Save As dialog.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D30, T5, X26).

### `autocad_switch_drawing`

**What it does.** Make a different open drawing the active one.
All other tools act on the active drawing, so switch before working on a second file.

**The problem it solves.**
- You have the wrong drawing active. Call autocad_status afterwards: the gate checks the units of the drawing it is about to change.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"Make a different open drawing the active one."*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `name`: File name of an already-open drawing, e.g. 'site-plan.dwg'. Matching is case-insensitive and the .dwg suffix is optional.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"active_drawing": str, "path": str}`

**Limits and versions.**
- Lists the drawings that are actually open if the name does not match.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows RV3).


## Heron itself, looking, commands and settings

The connection, what Heron did, undo, saved commands, looking at the drawing, and the Admin tools (commands, AutoLISP, system variables).

### `autocad_activity`

**What it does.** List what Heron did in this chat, newest first: each change, its drawing and what it made.
Each entry: when, the tool, what it was, the drawing, the outcome (done, discarded, failed, refused), the handles it created and what the plug-in counted (added, modified, erased). Reads are left out. Pass handles to autocad_show to put a job's objects on screen. Says also whether Heron's last change can still be undone with autocad_undo_last.

**The problem it solves.**
- "what have you done so far?" or "what did that last step make?"
- "show me what you drew ten minutes ago" -> then autocad_show its created handles.
- *Not for:* the modeller wants AutoCAD's own undo history - that is AutoCAD's UNDO list, which includes their own work.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).
On the Heron tab: **Heron tab > Heron > Heron palette > Activity** lists the same changes, newest first, with Select, Zoom and Undo where they can act.

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what have you done so far?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `limit`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"jobs": [...], "undo_last": {"possible": bool, "what": str}}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AX4).

### `autocad_companion`

**What it does.** Open the Heron Companion page: this chat's drawing, view, selection and activity in a browser beside AutoCAD.
The page is one HTML file on this PC (one per chat). This call reads the drawing, its units, the layout, the view and the selection, and puts them on it; after that the page's activity list is rewritten after every Heron job in this chat, and the page reloads itself every few seconds. It runs no script, opens no port and sends nothing to AutoCAD. Call again to read the view and selection afresh.

**The problem it solves.**
- "show me what you are doing in a window beside AutoCAD".
- "open the companion page" or "refresh the companion page".
- *Not for:* the modeller wants the list in the chat - autocad_activity answers there.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"show me what you are doing in a window beside AutoCAD"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `stop`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"page": path, "open": file URL, "updates": ..., "snapshot": {...}}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows Y6).

### `autocad_gaps`

**What it does.** Sum up Heron's own log of recent days: what ran, what failed and why, what was slow.
Works with AutoCAD closed. Reads Heron's audit log on this PC (one line per call, every chat): calls per tool, how many failed or were refused, the failures grouped by their plain reason with what to do (a padlock off, Heron not pressed, AutoCAD busy, an old plug-in), and the slowest jobs. Drawings appear by file name only; the log holds no drawing contents, so neither does this.

**The problem it solves.**
- "what went wrong this week?" / "what keeps failing?" / "which jobs were slow?"
- "how many times was Heron refused today?" - pass days=1.
- Before reporting a problem, to see how often it happens.
- *Not for:* the modeller wants what Heron did in this chat - that is autocad_activity. For one job that cannot run now, use autocad_why.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed, and it answers even with AutoCAD closed.

**How to use it.**
1. Nothing to prepare: AutoCAD may be closed. (With AutoCAD open, the drawing it names is the one Heron reads.)
2. Ask Claude, for example: *"what went wrong this week?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `days`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"days", "calls", "chats", "outcomes", "by_tool": [...], "failures": [{"reason", "says", "what_to_do", "count", "tools"}], "slowest": [{"tool", "seconds", "outcome", "drawing", "at"}], "log"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows W2, W5, W6, AX7).

### `autocad_get_selection`

**What it does.** Read whatever the user currently has selected in AutoCAD.
This is how a request like "move what I've selected" or "what did I just pick?" gets grounded: the user selects in AutoCAD, then this returns the handles to act on. The selection must be made BEFORE any command runs — AutoCAD clears it once a command starts. If it comes back empty, ask the user to select the objects and try again.

**The problem it solves.**
- "change the colour of what I've selected".
- *Not for:* you can identify the entities by filter instead (use autocad_list_entities).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"change the colour of what I've selected"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `include_geometry`, `limit`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"count": int, "truncated": bool, "handles": [str], "entities": [{...}]} A count of 0 means nothing is selected.`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_get_variable`

**What it does.** Read one AutoCAD system variable.
System variables carry drawing settings no other tool exposes — dimension scale, text size, point display mode, linetype scale and so on.

**The problem it solves.**
- "what is DIMSCALE set to" - or checking that a setting really landed.
- *Not for:* you want the usual drawing settings - autocad_status and autocad_drawing_setup report them together.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"what is DIMSCALE set to"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `name`: System variable name, e.g. 'INSUNITS', 'CLAYER', 'DIMSCALE', 'LTSCALE', 'EXTMIN', 'TEXTSIZE', 'OSMODE', 'PDMODE'.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"name": str, "value": str | float | int | list[float]}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows A31, Q4).

### `autocad_preview`

**What it does.** See the drawing: plot it to a PNG and return the picture.
Use after drawing something, to check it looks right before reporting it done. Plots through AutoCAD's own PNG plotter, so it shows what a plot would show; the page setup is put back afterwards and nothing is drawn. One picture has a fixed number of pixels (about 1600 across), so a whole A1 sheet at 1:1 gets about half a millimetre a pixel: 2.5 mm text and thin lines do not show, though the heavy frame does (issue #41). The answer says the area plotted and the smallest text that reads (`smallest_clear_text`);

**The problem it solves.**
- You have drawn something and want to see it before saying it is done. Drafting rule: look at the picture, then fix it.
- Checking crossings, overlaps, text on lines, crowding.
- "check the whole sheet": `detail=2` for an A1 or A0, so the text can be read.
- *Not for:* a PDF to keep or send is wanted: autocad_export.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"check the whole sheet"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `area`, `corner1`, `corner2`, `width_px`, `detail`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `The PNG image (then one per close-up, top left first), then JSON: {"area", "layout", "size", "pixels", "plotted": {"min", "max", "width", "height"}, "smallest_clear_text", "detail": [{"picture", "part", "corner1", "corner2"}] ...`

**Limits and versions.**
- Uses the plug-in for speed when it can (from plug-in 1.8.0); otherwise it does the same job over COM.

**Live proof.** **PARTLY**: rows A13 passed in AutoCAD 2027; the rest are NOT RUN (rows A13, A31, D31, E34, F20, J6, M6, AF22, AF24, BD3, AM1, AM2, AM4, AM5, AM6, AM7, AM8, AH1, AR1).

### `autocad_project_notes`

**What it does.** Keep the modeller's answers for this project, so the next chat does not ask again.
A project is the folder the drawing is saved in: every drawing in that folder shares the notes, and another folder never sees them. autocad_status hands the notes to every chat. Keep ONLY what the modeller said: never a value you guessed or worked out. The notes are Heron's own file on this PC; nothing is written into the drawing.

**The problem it solves.**
- The modeller answers "the scale is 1:50 for this job" -> keep scale = 1:50.
- "we use the client's layer standard here" -> keep layer_standard.
- "what do you remember about this project?" -> list.
- *Not for:* the value is your own estimate - ask the modeller first.
- *Not for:* the answer belongs in the drawing (title block text) - autocad_set_attributes writes that.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"the scale is 1:50 for this job"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `action`, `name`, `value`, `said`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"project": str, "notes": {name: {"value", "said", "at"}}}`

**Limits and versions.**
- An unsaved drawing has no project yet: it says to save it first, and keeps nothing.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_regen`

**What it does.** Regenerate the drawing display.
Worth calling after bulk edits, or when the screen no longer matches the data — new hatches, changed linetype scales and edited text sometimes need a regen to redraw correctly.

**The problem it solves.**
- The screen looks wrong after a settings change - linetypes not showing their pattern, text the wrong size.
- After autocad_drawing_setup changes LTSCALE.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"Regenerate the drawing display."*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `scope`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"regenerated": str}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NO ROW**: no row of the register names this tool, so nothing about it was checked in AutoCAD.

### `autocad_run_lisp`

**What it does.** Evaluate AutoLISP and return the value of its last form.
Unlike autocad_send_command, this gets a value back. AutoCAD's COM interface has no LISP eval, so the expression's result is stashed in the USERS1 system variable and read from there — which means the result comes back as text, and is capped at what that variable holds (a few hundred characters). Return an aggregate rather than a full list when the data is large.

**The problem it solves.**
- "what's the current dimension scale?" -> '(getvar "DIMSCALE")'.
- "how many entities are on layer X?" -> '(sslength (ssget "_X" (list (cons 8 "X"))))'.
- Loading a routine of several defuns and calling it — send them together; they are cut between the defuns.
- *Not for:* a typed tool covers it — those return structured data instead of a string.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Admin** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Admin** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"what's the current dimension scale?"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `expression`: AutoLISP to evaluate, e.g. '(getvar "DIMSCALE")' or '(length (vlax-safearray->list (vla-get-coordinates obj)))'.
- Optional: `expect_box`, `press`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"expression": str, "result": str, "timed_out": bool, "lisp_error": str (only when the code raised a LISP error), "cancelled_command": str (only when one was left open), "note": str, "chunks": int and "chunks_finished": int (only ...`

**Limits and versions.**
- A LISP error is answered at once: "lisp_error" holds AutoCAD's own message, "result" is null and the note names the piece that stopped (#157). The pieces after it are not sent.
- Reports timed_out=true if AutoCAD never wrote a result, which usually means the expression is waiting for input or still running.
- Unbalanced parentheses or quotes, or text outside a ( ... ) form, are rejected before anything is sent, since AutoCAD would otherwise sit waiting for the closing bracket.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **PARTLY**: rows J1 passed in AutoCAD 2027; the rest are NOT RUN (rows D30, F23, J1, J4, Q2, R7, V1, V7, Z2, Z8, AF23, AW1, AW3, AW4, AW5, AW6, AW8, AW14, S10, BA3).

### `autocad_saved_command`

**What it does.** Save a job that worked as a named command with inputs, and run it again the same way.
Once a job is right ("a pipe support at this size"), save its steps with the values that change as {{inputs}}. Running it fills the inputs and runs the same steps through the gate, padlocks and Keep or Discard, exactly as autocad_sequence would: nothing is planned again, so it comes out the same each time. Saved on this PC, never in the drawing. Like a sequence, it holds the Changes padlock only.

**The problem it solves.**
- "save that as 'pipe support' so I can do it again with another size".
- "do the pipe support again, 150 diameter" -> run with inputs.
- "what commands have we saved?" -> list.
- *Not for:* the job is new - work it out with the tools first, then save it.
- *Not for:* a step saves, exports or runs a command - those are refused, call them on their own.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).
On the Heron tab: **Heron tab > Heron > Heron palette > Saved commands** lists the commands saved with this tool.

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"save that as 'pipe support' so I can do it again with another size"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Optional: `action`, `name`, `steps`, `inputs`, `description`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON. run: the sequence's own report, plus "command" and "inputs".`

**Limits and versions.**
- A step a sequence would refuse, an input used but not declared (or declared but not used), or an input without an example is refused when saving; nothing is saved.
- Running with an unknown or missing input names it; nothing is run.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T3, BG4).

### `autocad_send_command`

**What it does.** Run any AutoCAD command by sending it to the command line.
This is the escape hatch for anything the typed tools do not cover — BOUNDARY, MEASUREGEOM, custom LISP commands, third-party add-in commands. TRIM, EXTEND, FILLET, CHAMFER, BREAK, JOIN and STRETCH have their own tools. The command runs as if the user typed it, so it needs every argument the interactive command would ask for, separated by \n. A command left waiting for input will block every later tool call until someone presses Esc in AutoCAD.

**The problem it solves.**
- Running a custom LISP command the office has loaded.
- A command asks a question in a box and the modeller has said the answer - expect_box='Purge - Confirm Purge', press='Yes'.
- *Not for:* a typed tool exists — autocad_draw_circle beats sending '_CIRCLE', and autocad_fillet_chamfer, autocad_trim_extend and autocad_join_curves beat typing FILLET, TRIM or JOIN.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Admin** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Admin** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Run any AutoCAD command by sending it to the command line."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `command`: The command string, exactly as typed at AutoCAD's command line. Use \n for Enter between arguments, e.g. '_CIRCLE\n0,0\n50\n'.
- Optional: `suppress_dialogs`, `expect_box`, `press`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"sent": str, "completed": bool, "command_active": bool, "note": str} "command_active" is true when AutoCAD is still waiting for input, which means the command string was incomplete.`

**Limits and versions.**
- Refuses commands known to open a modal dialog and names the command-line alternative, since a dialog would hang the connection.
- expect_box without press (or the reverse), or a plug-in older than 1.7.0, is refused before anything is sent.
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows N4, V1, V4, V7, Z1, RV1, BA4).

### `autocad_sequence`

**What it does.** Run several AutoCAD tools in one call, in order, checked before any of them starts.
This is AutoLISP's ``progn``: the steps that only make sense together, sent together. A whole sheet in one call — layout, page setup, title block, viewport — or a whole import clean-up — remap the layers, tidy the overrides, flatten, check the standard. Every step's arguments are validated against that tool's own schema first, so a sequence with a mistake in step four changes nothing at all. Each step that runs keeps its own undo step; with the Ask to Keep padlock on, Discard backs out the whole call.

**The problem it solves.**
- "set up sheet E-101 on A1 with our title block and the ground floor at 1:100" — four steps, one call.
- "make this IFC a shop drawing" — remap the layers, tidy the overrides, flatten to zero, then check the standard.
- The drawing must not be left half-changed if an argument is wrong.
- Eight dimension runs or a dozen batches in one go — quiet=true, so the answer is counts and handles, not every point.
- *Not for:* you are drawing hundreds of entities (autocad_batch_draw is far faster), or you need a save, an export, a command or AutoLISP — those are refused here by design.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"set up sheet E-101 on A1 with our title block and the ground floor at 1:100"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `steps`: The steps, in order. Each is an object: {"tool": "autocad_create_layout", "args": {"name": "E-101", "paper_size": "A1"}, "label": "make the sheet"} ...
- Optional: `stop_on_error`, `quiet`.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: { "ran": int, "failed": int, "skipped": int, "dry_run": bool, "steps": [{"index", "tool", "label", "level", "ok", "result": {...} | str, "skipped": bool}] } Each step's "result" is that tool's own answer, so handles from one step can ...`

**Limits and versions.**
- An unknown tool, a Publish or Admin step, a nested sequence, or arguments a tool would reject: all are reported with the step number before anything runs.
- A step that fails while running is reported with its own error text; the steps after it are marked skipped unless stop_on_error=false.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows D27, D28, D29, D30, F23, N7, X24, Z5, AJ8, AX5, AZ1, AZ5, RV3, BG1).

### `autocad_set_variable`

**What it does.** Set one AutoCAD system variable on the active drawing.

**The problem it solves.**
- A variable is needed that autocad_drawing_setup does not cover. It needs the Admin padlock, because it can set anything.
- *Not for:* autocad_drawing_setup can do it - that needs only Changes, and it works from a fixed list.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** and **Admin** padlocks ON (Heron tab > Settings).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** and **Admin** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"Set one AutoCAD system variable on the active drawing."*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Needs `name`: System variable name, e.g. 'DIMSCALE'.
- Needs `value`: New value as text. Numeric variables accept '50' or '0.25'; string variables take the text directly.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- A save, an export, a command or AutoLISP cannot be tried with `dry_run`: a file written or a command run cannot be taken back.
- Technical shape of the answer: `JSON: {"name": str, "previous": Any, "value": Any, "before_after": [{variable, property, from, to}] (empty when it already had that value)}`

**Limits and versions.**
- Returns a type error rather than a COM failure when a numeric variable is given non-numeric text.
- A point variable (LIMMAX, UCSORG) takes "x,y" or "x,y,z"; the wrong count of numbers is refused before anything is written.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows T6, S5).

### `autocad_show`

**What it does.** Put objects in front of the modeller: select them and zoom to them.
The answer to "which ones?" given in the drawing, not as a list of handles. The objects are left selected (grips on), so the modeller can look at them, move them or press Delete themselves. Changes nothing in the drawing and needs no padlock, only the connection.

**The problem it solves.**
- "show me the blocks with no tag" - find them, then show their handles.
- "where are the duplicates?" or "which lines are on layer 0?" after a query tool found them.
- "show only the sprinkler pipes for now" -> isolate=true; "bring everything back" -> end_isolation=true.
- *Not for:* the whole drawing or a window should fit the screen - autocad_zoom.
- *Not for:* the objects should be changed - use the editing tool; this only shows them.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).
On the Heron tab: **Heron tab > Heron > Heron palette > Activity**: Select and Zoom beside a change do the same for that change.

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"show me the blocks with no tag"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `handles`, `isolate`, `end_isolation`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"shown": int, "isolated": bool, "not_found": [str], "not_selectable": [{"handle": str, "reason": str}]} or {"isolation_ended": true}`

**Limits and versions.**
- Handles that are not in the drawing come back in not_found; the rest are still shown.
- Needs Heron's plug-in in AutoCAD (it does the selecting).
- Only drawing objects in the space in front are selected; "shown" counts those. The rest come back in not_selectable: "other_space" (switch tabs first), "inside_block", "not_a_drawing_object" (a style or layer).
- The plug-in does part of the work (`show`); it needs plug-in **1.8.1** or newer. An older plug-in refuses it and nothing is sent.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows M1, O3, AZ6, AD1).

### `autocad_status`

**What it does.** Check the AutoCAD connection and report what is currently open.
Call this first in any AutoCAD session. It confirms the COM link works and returns the drawing's units, current layer and entity counts that later calls depend on — in particular, coordinates passed to the drawing tools are in the drawing's own units, which this reports.

**The problem it solves.**
- Starting work, to confirm Claude can reach AutoCAD.
- You need the drawing's units before placing geometry.
- You are about to draw — "ucs_advice" warns you when the modeller's coordinates are not world coordinates.
- *Not for:* you want the entity list (use autocad_list_entities).

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).
On the Heron tab: **Heron tab > Heron > Bridge Status** shows whether Heron is connected to this AutoCAD, and the padlocks. It is a window for you; this tool is the same check for Claude.

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"ucs_advice"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `launch_if_needed`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON with this schema: { "connected": bool, "application": str, # window caption, e.g. "Autodesk AutoCAD 2020" "version": str, # e.g. "23.1s (LMS Tech)" "open_drawings": int, "active_drawing": { "name": str, # e.g.`

**Limits and versions.**
- Uses the plug-in for speed when it can; otherwise it does the same job over COM.

**Live proof.** **PARTLY**: rows J2 passed in AutoCAD 2027; the rest are NOT RUN (rows D1, D33, J2, L7, N1, N2, O1, O2, R10, AC14, AF10, AJ3, AJ4, AJ5, AJ5b, S8).

### `autocad_tiled_viewports`

**What it does.** Tile the screen into 2, 3 or 4 viewports (VPORTS), back to one, or read the tiles as they are.
Each new viewport starts from the view on screen now; click in one to make it current, then zoom or turn it. The answer reads the tiles back from AutoCAD, with their corners as fractions of the drawing area, and says if AutoCAD split it another way than asked. Model tab only: on a layout, viewports are autocad_add_viewport. This changes the screen, not the drawing: it needs no Changes padlock. AutoCAD keeps the split as the named configuration 'Heron' (VPORTS > Named Viewports); Heron replaces it the next time.

**The problem it solves.**
- "split the screen in two viewports side by side" — layout='two_vertical'.
- "four tiled viewports" — layout='four'.
- "back to one viewport" — layout='one'.
- "how are the viewports tiled?" — no layout.
- *Not for:* the viewport is on a sheet — autocad_add_viewport.
- *Not for:* you only want to look somewhere else — autocad_zoom or autocad_set_3d_view.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"split the screen in two viewports side by side"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `layout`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"layout": str|None, "tiles": int, "arrangement": str, "viewports": [{"lower_left": [x, y], "upper_right": [x, y], "current": bool}], "view_not_copied"?: [str], "warning"?: str}`

**Limits and versions.**
- On a layout it says to switch to the Model tab, and changes nothing.
- A split AutoCAD built another way than asked is a warning with what it did build.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows AQ6, AQ7, AQ16).

### `autocad_undo_last`

**What it does.** Undo Heron's own last change in this chat, only if nothing else changed the drawing since.
The guard is the point: Ctrl+Z undoes whatever came last, which may be the modeller's own work. This undoes Heron's last change only when the plug-in saw no change in the drawing since it (the modeller's, or another program's) and Heron itself did nothing since but look. Otherwise it is refused and says why, and the modeller uses Ctrl+Z themselves. One level only: after it, there is nothing more to undo this way.

**The problem it solves.**
- "undo what you just did" / "take that back".
- "that was wrong, put it back as it was" right after a Heron change.
- *Not for:* the modeller wants their own last step undone - they press Ctrl+Z; Heron does not undo their work.
- *Not for:* one object should go - autocad_delete_entities.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. Needs the **Changes** padlock ON (Heron tab > Settings > Changes).
On the Heron tab: **Heron tab > Heron > Heron palette > Activity**, the Undo button beside a change, does the same for that change.

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. In **Settings**, turn **Changes** ON (each asks first). They are all OFF when AutoCAD starts.
3. Ask Claude, for example: *"undo what you just did"*
4. Read the first line of the answer: DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN. Ask for a preview to look at the result.

**What it needs from you.**
- Nothing: it takes no inputs.

**The result to expect.**
- One line first (DONE, NOTHING CHANGED, REFUSED or OUTCOME UNKNOWN), then what was made or changed.
- It is one undo step. Add `dry_run=true` to try it first: it runs, reports, and Heron goes back to its UNDO mark.
- Technical shape of the answer: `JSON: {"undone": str, "drawing": str, "removed": [handles]}`

**Limits and versions.**
- Refused when Heron made no change in this chat, when the drawing is another one, when anything changed since, when Heron zoomed or ran a command since (with Ask to Keep off), or with a plug-in older than 1.5.0.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows O5, O6, O7, X10, Z1, AQ16, AX4, AX5, AX6, AX8, BC1, BC3, BC12, BG2).

### `autocad_use_autocad`

**What it does.** List the AutoCADs connected to Heron, or pick the one to work in.
With one AutoCAD connected, Heron works in it and this is not needed. With two or more, nothing is sent until one is picked here: Heron never guesses, because a change in the wrong AutoCAD is the worst mistake it can make. If the picked one closes, Heron stops and asks again; it never moves on to another by itself. After picking, call autocad_status before drawing: the other AutoCAD's drawing may be in other units.

**The problem it solves.**
- A tool says "2 AutoCADs are connected to Heron" - list them, ask the modeller which (by version), then pick it.
- "work in the AutoCAD 2025 one" or "use the other AutoCAD".
- *Not for:* only one AutoCAD is connected - Heron already works in it.
- *Not for:* switching drawings inside one AutoCAD - autocad_switch_drawing.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it only reads the drawing. Heron must be pressed (connected).
On the Heron tab: **Heron tab > Heron > Free this AutoCAD** lets another chat use this AutoCAD at once.

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"2 AutoCADs are connected to Heron"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `pid`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"connected": [{"pid", "acad_version", "plugin_version", "connected_since", "in_use"}], "in_use": int | null, "note": str}`

**Limits and versions.**
- A process that is not an AutoCAD connected to Heron is refused, with the list of those that are.
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows N2).

### `autocad_why`

**What it does.** Say why Heron cannot do a job, in plain words, and what the modeller does about it.
Works with AutoCAD closed. Finds the tool for the job, then checks what is in the way, worst first: no tool for it, a server started read-only, the plug-in not installed, AutoCAD not connected (Heron not pressed), two AutoCADs and none picked, server and plug-in from different releases, a plug-in older than the tool needs, an update this chat has not loaded.

**The problem it solves.**
- "why can't you do this?" / "why won't it save the PDF?" / "why was that refused?" about one job.
- Before a job, to check nothing is in the way: "can you plot this sheet?" with the padlocks unknown.
- "is there a tool to draw a cable tray?" and the modeller wants to know what stops it, not only its name.
- *Not for:* Heron as a whole seems broken - read autocad://diagnose. To only find a tool's name, read autocad://tools/find/{phrase}.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed, and it answers even with AutoCAD closed.

**How to use it.**
1. Nothing to prepare: AutoCAD may be closed. (With AutoCAD open, the drawing it names is the one Heron reads.)
2. Ask Claude, for example: *"why can't you do this?"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Needs `job`: The job in plain words, as the modeller said it, e.g. 'save this as PDF' or 'why can't you draw the duct'.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"job", "can_run": bool, "verdict", "tool": {...}, "other_tools": [...], "reasons": [{"reason", "blocks", "says", "what_to_do"}], "cannot_see"}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **NOT RUN**: built and tested offline, never run in AutoCAD (rows R9, W1, W2, W3, W4, AG15).

### `autocad_zoom`

**What it does.** Change what the AutoCAD window is showing.
Worth calling after drawing something so the user can see the result, and before asking for a screenshot of AutoCAD.

**The problem it solves.**
- "show me that corner" before a preview, so the picture is of the right thing.
- Zooming to a saved view or an object's extents.

**Where to find it.** There is no ribbon button for it. Ask Claude in the chat, in plain words. No padlock needed: it changes only what is on your screen, never the drawing. Heron must be pressed (connected).

**How to use it.**
1. Open the drawing in AutoCAD and press **Heron** on the Heron tab (or type `HERON`), so the heron is orange.
2. Ask Claude, for example: *"show me that corner"*
3. Read the answer Claude gives back.

**What it needs from you.**
- Optional: `mode`, `corner1`, `corner2`.

**The result to expect.**
- Claude reads the answer back to you in words; nothing in the drawing changes.
- Technical shape of the answer: `JSON: {"zoomed": str}`

**Limits and versions.**
- The plug-in only guards it (padlocks, Keep or Discard); the work itself is done over COM.

**Live proof.** **PARTLY**: rows J1 passed in AutoCAD 2027; the rest are NOT RUN (rows J1, O7).
