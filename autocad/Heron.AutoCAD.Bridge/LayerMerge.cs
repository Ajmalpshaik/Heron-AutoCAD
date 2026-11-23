using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// layer_objects (#199, D-147): the objects on the old layers of
    /// autocad_merge_layers, in the order the server's COM read finds them
    /// (each old layer's selection, then every block definition but layouts
    /// and xrefs, then the attributes of every block reference), each as
    /// [handle, layer, where]. The server plans the merge from these with the
    /// code it plans the COM read with.
    /// </summary>
    public sealed class LayerObjectList
    {
        public const string Drawing = "drawing";
        public const string Blocks = "blocks";
        public const string Attributes = "attributes";
        public const int MostLayers = 100;

        private readonly HashSet<string> _layers;
        private readonly List<(string Handle, string Layer, string Where)> _items = new List<(string, string, string)>();

        public LayerObjectList(IEnumerable<string>? layers)
        {
            _layers = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (layers != null)
                foreach (var layer in layers)
                    if (!string.IsNullOrWhiteSpace(layer)) _layers.Add(layer);
            if (_layers.Count == 0 || _layers.Count > MostLayers)
                throw new RunRefusal("Merging layers needs 'layers': one to " + MostLayers + " layer names.");
        }

        public int Count => _items.Count;

        /// <summary>The selection filters, one per old layer, as the server's COM read selects with.</summary>
        public static IReadOnlyList<IReadOnlyList<FilterPair>> ParseFilters(JsonElement filters)
        {
            if (filters.ValueKind != JsonValueKind.Array || filters.GetArrayLength() == 0 || filters.GetArrayLength() > MostLayers)
                throw new RunRefusal("layer_objects needs 'filters': one filter per old layer, one to " + MostLayers + ".");
            var list = new List<IReadOnlyList<FilterPair>>();
            foreach (var filter in filters.EnumerateArray()) list.Add(EntityFilter.Parse(filter));
            return list;
        }

        /// <summary>
        /// True once a block reference with an attribute on an old layer has a
        /// definition that holds no attribute definitions: whether COM's
        /// HasAttributes lets the server's COM read see it is not looked at yet
        /// (D-138), so the server reads over COM.
        /// </summary>
        public bool Unsure { get; private set; }

        /// <summary>Whether an object on this layer is one the merge moves (AutoCAD's own names: the case does not count).</summary>
        public bool OnOldLayer(string? layer) => layer != null && _layers.Contains(layer);

        public void Add(string handle, string layer, string where)
        {
            if (where != Drawing && where != Blocks && where != Attributes)
                throw new ArgumentException("where: drawing, blocks or attributes", nameof(where));
            _items.Add((handle ?? "", layer ?? "", where));
        }

        public void MarkUnsure() => Unsure = true;

        /// <summary>{"items": [[handle, layer, where]...], "unsure": bool}.</summary>
        public void Write(Utf8JsonWriter w)
        {
            w.WriteStartArray("items");
            foreach (var item in _items)
            {
                w.WriteStartArray();
                w.WriteStringValue(item.Handle);
                w.WriteStringValue(item.Layer);
                w.WriteStringValue(item.Where);
                w.WriteEndArray();
            }
            w.WriteEndArray();
            w.WriteBoolean("unsure", Unsure);
        }
    }

    /// <summary>
    /// merge_layers (#199, D-147): what autocad_merge_layers asks the plug-in
    /// to do in one transaction, and what it did. The old layers, the layer
    /// they merge into, and the handles the server planned to move (it plans
    /// them; the plug-in moves exactly those). Every object moves, or none
    /// does: an object that will not move is a refusal, and the transaction
    /// is aborted. An old layer is removed only when AutoCAD's purge says
    /// nothing uses it any more; otherwise it is kept, locked again if it was.
    /// </summary>
    public sealed class LayerMergePlan
    {
        public const int MostHandles = 500000;

        private readonly List<string> _removed = new List<string>();
        private readonly List<(string Layer, string Reason)> _kept = new List<(string, string)>();

        public LayerMergePlan(IReadOnlyList<string> layers, string into, IReadOnlyList<string> handles)
        {
            var old = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var layer in layers ?? new string[0])
                if (!string.IsNullOrWhiteSpace(layer) && seen.Add(layer)) old.Add(layer);
            if (old.Count == 0 || old.Count > LayerObjectList.MostLayers)
                throw new RunRefusal("Merging layers needs 'layers': one to " + LayerObjectList.MostLayers + " layer names.");
            if (string.IsNullOrWhiteSpace(into)) throw new RunRefusal("Merging layers needs 'into': the layer to merge into.");
            if (seen.Contains(into)) throw new RunRefusal("'" + into + "' is the layer being merged into; it cannot be merged into itself.");
            foreach (var layer in old)
                if (layer == "0") throw new RunRefusal("Layer 0 is built into every drawing and cannot be merged away.");
            if ((handles ?? new string[0]).Count > MostHandles)
                throw new RunRefusal("Merging layers moves at most " + MostHandles + " objects in one go.");
            Layers = old;
            Into = into;
            Handles = handles ?? new string[0];
        }

        public static LayerMergePlan Parse(RunArgs args) => new LayerMergePlan(args.Texts("layers"), args.Text("into"), args.Texts("handles"));

        public IReadOnlyList<string> Layers { get; }
        public string Into { get; }
        public IReadOnlyList<string> Handles { get; }

        /// <summary>The current layer's name when it was an old layer and the merged-into one became current.</summary>
        public string? WasCurrent { get; private set; }

        public bool IsOld(string? layer)
        {
            if (layer == null) return false;
            foreach (var old in Layers)
                if (string.Equals(old, layer, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        public void MadeCurrent(string was) => WasCurrent = was;

        public void Removed(string layer) => _removed.Add(layer);

        public void Kept(string layer, string reason) => _kept.Add((layer, reason ?? ""));

        /// <summary>Why the whole merge is refused: one object would not move, and nothing was merged.</summary>
        public string WouldNotMove(string handle, string why) =>
            "Object " + handle + " would not move to " + Into + " (" + why + "), so nothing was merged: no object moved and no layer was removed.";

        /// <summary>Why the whole merge is refused: a planned object is not in the drawing any more.</summary>
        public static string Gone(string handle) =>
            "Object " + handle + " is not in the drawing any more, so nothing was merged. Look at the drawing and ask again.";

        public static string NoLayer(string layer) => "There is no layer called '" + layer + "' any more, so nothing was merged.";

        /// <summary>{"moved": n, "current": was or null, "removed": [layer...], "kept": [[layer, reason]...]}.</summary>
        public void Write(Utf8JsonWriter w)
        {
            w.WriteNumber("moved", Handles.Count);
            if (WasCurrent == null) w.WriteNull("current");
            else w.WriteString("current", WasCurrent);
            w.WriteStartArray("removed");
            foreach (var layer in _removed) w.WriteStringValue(layer);
            w.WriteEndArray();
            w.WriteStartArray("kept");
            foreach (var (layer, reason) in _kept)
            {
                w.WriteStartArray();
                w.WriteStringValue(layer);
                w.WriteStringValue(reason);
                w.WriteEndArray();
            }
            w.WriteEndArray();
        }
    }
}
