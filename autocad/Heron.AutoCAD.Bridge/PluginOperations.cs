using System.Collections.Generic;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The operations the plug-in does itself, because COM has no call for
    /// them, and the level a job needs for each. Anything not listed here is
    /// refused before AutoCAD is touched (D-40 in docs/DECISIONS.md).
    /// </summary>
    public static class PluginOperations
    {
        private static readonly Dictionary<string, Risk> Levels = new Dictionary<string, Risk>
        {
            ["solid_topology"] = Risk.Read,
            // Where dimension lines are, the drawing's and objects' annotation scales,
            // and the drawing's layer states (D-80, D-81).
            ["dimension_lines"] = Risk.Read,
            ["annotation_scales"] = Risk.Read,
            ["layer_state_names"] = Risk.Read,
            // Selects, zooms and isolates what was asked for: on screen only.
            ["show"] = Risk.View,
            ["loft"] = Risk.Change,
            ["fillet_edges"] = Risk.Change,
            ["chamfer_edges"] = Risk.Change,
            ["shell"] = Risk.Change,
            ["press_pull"] = Risk.Change,
            ["thicken"] = Risk.Change,
            ["super_hatch"] = Risk.Change,
            ["add_light"] = Risk.Change,
            ["create_material"] = Risk.Change,
            ["move_dimension_lines"] = Risk.Change,
            ["set_annotation_scales"] = Risk.Change,
            ["layer_state"] = Risk.Change,
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
            ["publish_pdf"] = Risk.Publish,
        };

        public static IEnumerable<string> Names => Levels.Keys;

        public static bool TryLevel(string operation, out Risk level) => Levels.TryGetValue(operation ?? "", out level);
    }
}
