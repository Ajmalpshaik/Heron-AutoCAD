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
            // ATTSYNC and the Excel data link: COM can add neither (D-82, D-83).
            ["sync_attributes"] = Risk.Change,
            ["excel_table"] = Risk.Change,
            ["update_table_links"] = Risk.Change,
            ["publish_pdf"] = Risk.Publish,
        };

        public static IEnumerable<string> Names => Levels.Keys;

        public static bool TryLevel(string operation, out Risk level) => Levels.TryGetValue(operation ?? "", out level);
    }
}
