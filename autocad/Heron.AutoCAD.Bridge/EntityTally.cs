using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// One condition of a selection filter: a DXF code and the text or colour
    /// number it must match, exactly as the server's filter_pairs sends it.
    /// </summary>
    public sealed class FilterPair
    {
        public FilterPair(int code, string? text, int? number)
        {
            Code = code;
            Text = text;
            Number = number;
        }

        public int Code { get; }
        /// <summary>The type, layer or block name (AutoCAD's wildcards work).</summary>
        public string? Text { get; }
        /// <summary>The colour number, for code 62.</summary>
        public int? Number { get; }
    }

    /// <summary>
    /// The filter of a read over the whole drawing (D-114). Only what the
    /// server's COM selection filters on is taken (type, layer, block name,
    /// colour), so the plug-in selects exactly the objects COM would.
    /// </summary>
    public static class EntityFilter
    {
        public const int Type = 0;
        public const int BlockName = 2;
        public const int Layer = 8;
        public const int Color = 62;

        private const string Only = "Heron in AutoCAD filters a read only by type, layer, block name and colour.";

        /// <summary>The pairs; none at all selects everything. A refusal for anything else.</summary>
        public static IReadOnlyList<FilterPair> Parse(JsonElement filter)
        {
            var pairs = new List<FilterPair>();
            if (filter.ValueKind == JsonValueKind.Undefined || filter.ValueKind == JsonValueKind.Null) return pairs;
            if (filter.ValueKind != JsonValueKind.Array) throw new RunRefusal(Only);
            foreach (var item in filter.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Array || item.GetArrayLength() != 2) throw new RunRefusal(Only);
                var code = item[0];
                var value = item[1];
                if (code.ValueKind != JsonValueKind.Number || !code.TryGetInt32(out var dxf)) throw new RunRefusal(Only);
                switch (dxf)
                {
                    case Type:
                    case BlockName:
                    case Layer:
                        var text = value.ValueKind == JsonValueKind.String ? (value.GetString() ?? "") : "";
                        if (text.Trim().Length == 0) throw new RunRefusal(Only);
                        pairs.Add(new FilterPair(dxf, text, null));
                        break;
                    case Color:
                        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out var aci) || aci < 0 || aci > 256)
                            throw new RunRefusal("A colour in a filter is an AutoCAD Color Index number from 0 to 256.");
                        pairs.Add(new FilterPair(dxf, null, aci));
                        break;
                    default:
                        throw new RunRefusal(Only);
                }
            }
            return pairs;
        }
    }

    /// <summary>
    /// What a read over the whole drawing found (D-114): how many objects of
    /// each class and on each layer, in the order first met, and the box round
    /// the ones that have extents. The server turns it into the same answer it
    /// gives from COM, so this keeps the raw names and full numbers: AutoCAD's
    /// class name (AcDbLine) as COM's ObjectName gives it, no rounding.
    /// </summary>
    public sealed class EntityTally
    {
        private readonly List<string> _classes = new List<string>();
        private readonly Dictionary<string, int> _byClass = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly List<string> _layers = new List<string>();
        private readonly Dictionary<string, int> _byLayer = new Dictionary<string, int>(StringComparer.Ordinal);
        private readonly double[] _min = { double.PositiveInfinity, double.PositiveInfinity, double.PositiveInfinity };
        private readonly double[] _max = { double.NegativeInfinity, double.NegativeInfinity, double.NegativeInfinity };

        /// <summary>Every object the filter selected.</summary>
        public int Total { get; private set; }

        /// <summary>The objects that had extents.</summary>
        public int Measured { get; private set; }

        /// <summary>One object, by its class and layer.</summary>
        public void Count(string className, string layer)
        {
            Total++;
            Add(_classes, _byClass, className ?? "");
            Add(_layers, _byLayer, layer ?? "");
        }

        /// <summary>One object past a cut-off: in the total, not counted by class or layer.</summary>
        public void Skip() => Total++;

        /// <summary>One object that may have no extents (a ray, a construction line): then box is null.</summary>
        public void Measure(double[]? min, double[]? max)
        {
            Total++;
            if (min == null || max == null || min.Length != 3 || max.Length != 3) return;
            for (var axis = 0; axis < 3; axis++)
                if (!IsFinite(min[axis]) || !IsFinite(max[axis])) return;
            Measured++;
            for (var axis = 0; axis < 3; axis++)
            {
                _min[axis] = Math.Min(_min[axis], min[axis]);
                _max[axis] = Math.Max(_max[axis], max[axis]);
            }
        }

        /// <summary>{"total", "by_class": [[name, n]...], "by_layer": [[name, n]...]}, in the order first met.</summary>
        public void WriteCounts(Utf8JsonWriter w)
        {
            w.WriteNumber("total", Total);
            WritePairs(w, "by_class", _classes, _byClass);
            WritePairs(w, "by_layer", _layers, _byLayer);
        }

        /// <summary>{"total", "measured", "min": [x, y, z] or null, "max": [x, y, z] or null}.</summary>
        public void WriteBox(Utf8JsonWriter w)
        {
            w.WriteNumber("total", Total);
            w.WriteNumber("measured", Measured);
            WritePoint(w, "min", _min);
            WritePoint(w, "max", _max);
        }

        private void WritePoint(Utf8JsonWriter w, string name, double[] point)
        {
            if (Measured == 0)
            {
                w.WriteNull(name);
                return;
            }
            w.WriteStartArray(name);
            foreach (var value in point) w.WriteNumberValue(value);
            w.WriteEndArray();
        }

        private static void Add(List<string> order, Dictionary<string, int> counts, string key)
        {
            if (counts.TryGetValue(key, out var count))
            {
                counts[key] = count + 1;
                return;
            }
            order.Add(key);
            counts[key] = 1;
        }

        private static void WritePairs(Utf8JsonWriter w, string name, List<string> order, Dictionary<string, int> counts)
        {
            w.WriteStartArray(name);
            foreach (var key in order)
            {
                w.WriteStartArray();
                w.WriteStringValue(key);
                w.WriteNumberValue(counts[key]);
                w.WriteEndArray();
            }
            w.WriteEndArray();
        }

        // double.IsFinite is not in .NET Framework 4.8.
        private static bool IsFinite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);
    }
}
