using System;
using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Named layer states: save, bring back, delete, list (#107, D-81). Done
    /// with .NET's LayerStateManager, whose calls were checked against
    /// Autodesk's reference assemblies (2021 and 2027); COM's own manager is
    /// reached only through a versioned ProgID and has no list call.
    /// </summary>
    internal static class LayerStates
    {
        /// <summary>Everything a layer state can remember except the per-viewport settings.</summary>
        internal const LayerStateMasks Everything =
            LayerStateMasks.On | LayerStateMasks.Frozen | LayerStateMasks.Locked | LayerStateMasks.Plot
            | LayerStateMasks.NewViewport | LayerStateMasks.Color | LayerStateMasks.LineType
            | LayerStateMasks.LineWeight | LayerStateMasks.PlotStyle | LayerStateMasks.Transparency;

        private static readonly (LayerStateMasks mask, string word)[] Words =
        {
            (LayerStateMasks.On, "on"), (LayerStateMasks.Frozen, "frozen"), (LayerStateMasks.Locked, "locked"),
            (LayerStateMasks.Plot, "plot"), (LayerStateMasks.NewViewport, "new_viewport_frozen"),
            (LayerStateMasks.Color, "color"), (LayerStateMasks.LineType, "linetype"),
            (LayerStateMasks.LineWeight, "lineweight"), (LayerStateMasks.PlotStyle, "plot_style"),
            (LayerStateMasks.Transparency, "transparency"),
        };

        /// <summary>The drawing's layer states, each with what it remembers and its description.</summary>
        public static RunResult Names(Database db, Transaction tr, RunArgs args)
        {
            var lsm = db.LayerStateManager;
            var names = new List<string>();
            foreach (var item in lsm.GetLayerStateNames(false, false))
                if (item is string name) names.Add(name);
            names.Sort(StringComparer.OrdinalIgnoreCase);
            return RunResult.Done(w =>
            {
                w.WriteStartArray("layer_states");
                foreach (var name in names)
                {
                    w.WriteStartObject();
                    w.WriteString("name", name);
                    WriteMask(w, lsm.GetLayerStateMask(name));
                    w.WriteString("description", lsm.GetLayerStateDescription(name) ?? "");
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        /// <summary>
        /// action save | restore | delete. A restore reports every layer whose
        /// on, frozen or locked state it changed; a save that would replace a
        /// state needs overwrite, or keep_existing to leave the old one be.
        /// </summary>
        public static RunResult Change(Database db, Transaction tr, RunArgs args)
        {
            var lsm = db.LayerStateManager;
            var action = args.Text("action").Trim().ToLowerInvariant();
            var name = args.Text("name").Trim();
            if (name.Length == 0) throw new RunRefusal("Give the layer state's name.");
            var exists = lsm.HasLayerState(name);
            switch (action)
            {
                case "save":
                {
                    if (exists && args.Flag("keep_existing", false))
                        return RunResult.Done(w =>
                        {
                            w.WriteString("action", "save");
                            w.WriteString("name", name);
                            w.WriteBoolean("kept_existing", true);
                            w.WriteString("description", lsm.GetLayerStateDescription(name) ?? "");
                        });
                    if (exists && !args.Flag("overwrite", false))
                        throw new RunRefusal("There is already a layer state called '" + name + "'. Pass overwrite=true to replace it, or give another name.");
                    try
                    {
                        SymbolUtilityServices.ValidateSymbolName(name, false);
                    }
                    catch (Autodesk.AutoCAD.Runtime.Exception)
                    {
                        throw new RunRefusal("'" + name + "' cannot be a layer state name.");
                    }
                    var mask = args.Has("mask") ? (LayerStateMasks)(int)args.Number("mask") : Everything;
                    if (exists) lsm.DeleteLayerState(name);
                    lsm.SaveLayerState(name, mask, ObjectId.Null);
                    var description = args.Text("description").Trim();
                    if (description.Length > 0) lsm.SetLayerStateDescription(name, description);
                    var layers = CountLayers(db, tr);
                    return RunResult.Done(w =>
                    {
                        w.WriteString("action", "save");
                        w.WriteString("name", name);
                        w.WriteBoolean("replaced", exists);
                        WriteMask(w, mask);
                        w.WriteNumber("layers", layers);
                    });
                }
                case "restore":
                {
                    if (!exists) throw new RunRefusal("There is no layer state called '" + name + "'. autocad_list_layers lists the drawing's layer states.");
                    var before = Snapshot(db, tr);
                    var mask = lsm.GetLayerStateMask(name);
                    var description = lsm.GetLayerStateDescription(name) ?? "";
                    lsm.RestoreLayerState(name, ObjectId.Null, 0, mask);
                    var after = Snapshot(db, tr);
                    if (args.Flag("delete_after", false)) lsm.DeleteLayerState(name);
                    return RunResult.Done(w =>
                    {
                        w.WriteString("action", "restore");
                        w.WriteString("name", name);
                        WriteMask(w, mask);
                        w.WriteString("description", description);
                        w.WriteBoolean("deleted_after", args.Flag("delete_after", false));
                        WriteChanges(w, before, after);
                    });
                }
                case "delete":
                {
                    if (!exists) throw new RunRefusal("There is no layer state called '" + name + "'. autocad_list_layers lists the drawing's layer states.");
                    lsm.DeleteLayerState(name);
                    return RunResult.Done(w =>
                    {
                        w.WriteString("action", "delete");
                        w.WriteString("name", name);
                    });
                }
                default:
                    throw new RunRefusal("The action must be save, restore or delete.");
            }
        }

        private static int CountLayers(Database db, Transaction tr)
        {
            var count = 0;
            foreach (ObjectId _ in (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead)) count++;
            return count;
        }

        private static Dictionary<string, (bool on, bool frozen, bool locked)> Snapshot(Database db, Transaction tr)
        {
            var states = new Dictionary<string, (bool, bool, bool)>(StringComparer.OrdinalIgnoreCase);
            foreach (ObjectId id in (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead))
            {
                var layer = (LayerTableRecord)tr.GetObject(id, OpenMode.ForRead);
                states[layer.Name] = (!layer.IsOff, layer.IsFrozen, layer.IsLocked);
            }
            return states;
        }

        private static void WriteChanges(Utf8JsonWriter w, Dictionary<string, (bool on, bool frozen, bool locked)> before,
            Dictionary<string, (bool on, bool frozen, bool locked)> after)
        {
            w.WriteStartArray("changes");
            foreach (var pair in after)
            {
                if (!before.TryGetValue(pair.Key, out var was)) continue;
                Row(w, pair.Key, "on", was.on, pair.Value.on);
                Row(w, pair.Key, "frozen", was.frozen, pair.Value.frozen);
                Row(w, pair.Key, "locked", was.locked, pair.Value.locked);
            }
            w.WriteEndArray();
        }

        private static void Row(Utf8JsonWriter w, string layer, string property, bool from, bool to)
        {
            if (from == to) return;
            w.WriteStartObject();
            w.WriteString("layer", layer);
            w.WriteString("property", property);
            w.WriteBoolean("from", from);
            w.WriteBoolean("to", to);
            w.WriteEndObject();
        }

        private static void WriteMask(Utf8JsonWriter w, LayerStateMasks mask)
        {
            w.WriteStartArray("remembers");
            foreach (var (bit, word) in Words)
                if ((mask & bit) == bit) w.WriteStringValue(word);
            w.WriteEndArray();
        }
    }
}
