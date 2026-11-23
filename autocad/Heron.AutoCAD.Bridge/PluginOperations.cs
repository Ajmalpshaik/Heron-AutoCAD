using System.Collections.Generic;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The operations the plug-in does itself, because COM has no call for
    /// them (D-40) or would take a round trip per object (D-114), and the
    /// level a job needs for each. Anything not listed here is refused before
    /// AutoCAD is touched (docs/DECISIONS.md).
    /// </summary>
    public static class PluginOperations
    {
        private static readonly Dictionary<string, Risk> Levels = new Dictionary<string, Risk>
        {
            // Reads over the whole drawing that COM can do, but one round trip
            // per object: the plug-in does them in one go (D-114).
            ["count_entities"] = Risk.Read,
            ["entity_extents"] = Risk.Read,
            // Block counts for autocad_count_blocks and autocad_list_blocks (D-127).
            ["block_references"] = Risk.Read,
            ["block_definitions"] = Risk.Read,
            // Lengths and areas for autocad_total_length and autocad_measure, texts and
            // attributes for autocad_count_text and autocad_find_text (D-134).
            ["entity_lengths"] = Risk.Read,
            ["entity_texts"] = Risk.Read,
            // Every block reference's attributes for autocad_extract_attributes,
            // autocad_export_attribute_sheet and the reads of autocad_set_attributes and
            // autocad_apply_attribute_sheet (D-138); asked inside a Change or Publish job too.
            ["block_attributes"] = Risk.Read,
            // Each object's layer, colour, linetype and a dimension's box for
            // autocad_check_standards' entity rules (D-145); the rules stay in the server.
            ["entity_properties"] = Risk.Read,
            // The objects on the layers autocad_merge_layers merges away (D-147).
            ["layer_objects"] = Risk.Read,
            ["solid_topology"] = Risk.Read,
            // Where dimension lines are, the drawing's and objects' annotation scales,
            // and the drawing's layer states (D-80, D-81).
            ["dimension_lines"] = Risk.Read,
            ["annotation_scales"] = Risk.Read,
            ["layer_state_names"] = Risk.Read,
            // The files a drawing needs, for eTransmit (D-85): reads only.
            ["list_dependencies"] = Risk.Read,
            // Selects, zooms and isolates what was asked for: on screen only.
            ["show"] = Risk.View,
            ["loft"] = Risk.Change,
            ["fillet_edges"] = Risk.Change,
            ["chamfer_edges"] = Risk.Change,
            ["shell"] = Risk.Change,
            ["press_pull"] = Risk.Change,
            ["thicken"] = Risk.Change,
            // Pyramid and polysolid, and the rest of SOLIDEDIT (D-112, D-113).
            ["add_pyramid"] = Risk.Change,
            ["add_polysolid"] = Risk.Change,
            ["offset_faces"] = Risk.Change,
            ["taper_faces"] = Risk.Change,
            ["move_faces"] = Risk.Change,
            ["delete_faces"] = Risk.Change,
            ["imprint_solid"] = Risk.Change,
            ["separate_solid"] = Risk.Change,
            ["super_hatch"] = Risk.Change,
            ["add_light"] = Risk.Change,
            ["create_material"] = Risk.Change,
            ["move_dimension_lines"] = Risk.Change,
            ["set_annotation_scales"] = Risk.Change,
            ["layer_state"] = Risk.Change,
            // autocad_merge_layers' move and removal in one transaction: all or none (D-147).
            ["merge_layers"] = Risk.Change,
            // The attribute cells autocad_set_attributes and autocad_apply_attribute_sheet
            // planned, written in one transaction: all or none (D-147).
            ["write_attributes"] = Risk.Change,
            // Setting a render up (D-86, D-87). None of them renders.
            ["current_view"] = Risk.Read,
            ["list_lights"] = Risk.Read,
            ["switch_lights"] = Risk.Change,
            ["set_sun"] = Risk.Change,
            ["add_camera_view"] = Risk.Change,
            // ATTSYNC and the Excel data link: COM can add neither (D-82, D-83).
            ["sync_attributes"] = Risk.Change,
            ["excel_table"] = Risk.Change,
            ["update_table_links"] = Risk.Change,
            // Sheets made in .NET, so neither needs doc.PaperSpace (#64, D-90); the
            // active sheet's own count for autocad_status (#39).
            ["active_sheet"] = Risk.Read,
            ["create_layout"] = Risk.Change,
            ["add_viewport"] = Risk.Change,
            // MLINE's own Close, a spline by control points, and a spline's fit
            // points moved, added or taken away: COM has no call for any (D-97).
            ["close_multiline"] = Risk.Change,
            ["add_cv_spline"] = Risk.Change,
            ["edit_spline_fit_points"] = Risk.Change,
            // A model cut and looked at in 2D, surfaces and meshes (D-95).
            ["flat_views"] = Risk.Change,
            ["section_plane"] = Risk.Change,
            ["loft_surface"] = Risk.Change,
            ["planar_surface"] = Risk.Change,
            ["network_surface"] = Risk.Change,
            ["add_mesh"] = Risk.Change,
            // Multileader and table styles: COM can make neither (D-104).
            ["multileader_style"] = Risk.Change,
            ["table_style"] = Risk.Change,
            // An associative array (ARRAY) and the drawing's geographic location
            // (GEOGRAPHICLOCATION): COM has a call for neither (D-110, D-111).
            ["associative_array"] = Risk.Change,
            ["geo_location"] = Risk.Read,
            ["set_geo_location"] = Risk.Change,
            // References and clean-up (D-84).
            ["attach_underlay"] = Risk.Change,
            ["clip_reference"] = Risk.Change,
            ["trace_boundary"] = Risk.Change,
            ["publish_pdf"] = Risk.Publish,
        };

        public static IEnumerable<string> Names => Levels.Keys;

        public static bool TryLevel(string operation, out Risk level) => Levels.TryGetValue(operation ?? "", out level);
    }
}
