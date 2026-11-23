using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// One dynamic property of a block reference, as the plug-in read it: its
    /// name, whether it is read-only, and its value as .NET holds it (a double,
    /// a short, a string, or a point as double[]). Failed is set when AutoCAD
    /// would not give the value.
    /// </summary>
    public sealed class DynamicProperty
    {
        public DynamicProperty(string name, bool readOnly, object? value, bool failed = false)
        {
            Name = name ?? "";
            ReadOnly = readOnly;
            Value = value;
            Failed = failed;
        }

        public string Name { get; }
        public bool ReadOnly { get; }
        public object? Value { get; }
        public bool Failed { get; }
    }

    /// <summary>
    /// A dynamic property's value with its type, so the server turns it back
    /// into the type COM gives (D-127). Utf8JsonWriter writes a whole-number
    /// double as 50, which Python reads as an int while COM gives 50.0: a count
    /// by size would then split in two. So every value goes as [kind, value]:
    /// "real" (a distance, an angle), "int" (a flip state), "text" (a list
    /// choice, a visibility state), "point", "none" (no value), "error" (AutoCAD
    /// would not give it) and "other" (a type the server does not know: it
    /// reads the drawing over COM instead, if it needs that value).
    /// </summary>
    public static class DynamicValue
    {
        public static string Kind(object? value, bool failed)
        {
            if (failed) return "error";
            switch (value)
            {
                case null: return "none";
                case double d: return IsFinite(d) ? "real" : "other";
                case float f: return IsFinite(f) ? "real" : "other";
                case short _:
                case int _:
                case long _:
                case byte _:
                case sbyte _:
                case ushort _:
                case uint _:
                    return "int";
                case string _: return "text";
                case double[] point:
                    foreach (var axis in point)
                        if (!IsFinite(axis)) return "other";
                    return "point";
                default: return "other";
            }
        }

        /// <summary>The two items [kind, value] into an array the caller has started.</summary>
        public static void Write(Utf8JsonWriter w, object? value, bool failed)
        {
            var kind = Kind(value, failed);
            w.WriteStringValue(kind);
            switch (kind)
            {
                case "real":
                    w.WriteNumberValue(Convert.ToDouble(value, System.Globalization.CultureInfo.InvariantCulture));
                    break;
                case "int":
                    w.WriteNumberValue(Convert.ToInt64(value, System.Globalization.CultureInfo.InvariantCulture));
                    break;
                case "text":
                    w.WriteStringValue((string)value!);
                    break;
                case "point":
                    w.WriteStartArray();
                    foreach (var axis in (double[])value!) w.WriteNumberValue(axis);
                    w.WriteEndArray();
                    break;
                case "other":
                    // Only for the plug-in's log and a person reading the reply: the server never uses it.
                    w.WriteStringValue(value?.GetType().Name ?? "");
                    break;
                default:
                    w.WriteNullValue();
                    break;
            }
        }

        // double.IsFinite is not in .NET Framework 4.8.
        private static bool IsFinite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);
    }

    /// <summary>
    /// What autocad_count_blocks needs, read in one go (#192, D-127): every
    /// selected block reference, in the order selected, with its real name,
    /// layer and dynamic properties, and, when asked, the block references
    /// inside each block definition. Raw facts only: the server picks the
    /// visibility state and the properties it counts by with the code it uses
    /// for COM, so the answer is the same either way.
    /// </summary>
    public sealed class BlockReferenceList
    {
        private readonly List<(string Block, string Layer, IReadOnlyList<DynamicProperty> Properties)> _refs =
            new List<(string, string, IReadOnlyList<DynamicProperty>)>();
        private readonly List<string> _parents = new List<string>();
        private readonly Dictionary<string, List<(string Block, string Layer)>> _children =
            new Dictionary<string, List<(string, string)>>(StringComparer.Ordinal);

        public int Count => _refs.Count;

        /// <summary>One placed block: its real (effective) name, layer and dynamic properties in AutoCAD's order.</summary>
        public void Add(string block, string layer, IReadOnlyList<DynamicProperty>? properties)
        {
            _refs.Add((block ?? "", layer ?? "", properties ?? Array.Empty<DynamicProperty>()));
        }

        /// <summary>A block reference inside the definition named parent.</summary>
        public void AddChild(string parent, string block, string layer)
        {
            parent ??= "";
            if (!_children.TryGetValue(parent, out var list))
            {
                list = new List<(string, string)>();
                _children[parent] = list;
                _parents.Add(parent);
            }
            list.Add((block ?? "", layer ?? ""));
        }

        /// <summary>
        /// {"refs": [[block, layer, [[name, read_only, kind, value]...]]...]}, and
        /// with nested "children": [[definition, [[block, layer]...]]...] in the
        /// order the block table holds them. "children" is there only when asked
        /// for, so the server knows this plug-in honoured "nested".
        /// </summary>
        public void Write(Utf8JsonWriter w, bool nested)
        {
            w.WriteStartArray("refs");
            foreach (var (block, layer, properties) in _refs)
            {
                w.WriteStartArray();
                w.WriteStringValue(block);
                w.WriteStringValue(layer);
                w.WriteStartArray();
                foreach (var property in properties)
                {
                    w.WriteStartArray();
                    w.WriteStringValue(property.Name);
                    w.WriteBooleanValue(property.ReadOnly);
                    DynamicValue.Write(w, property.Value, property.Failed);
                    w.WriteEndArray();
                }
                w.WriteEndArray();
                w.WriteEndArray();
            }
            w.WriteEndArray();
            if (!nested) return;
            w.WriteStartArray("children");
            foreach (var parent in _parents)
            {
                w.WriteStartArray();
                w.WriteStringValue(parent);
                w.WriteStartArray();
                foreach (var (block, layer) in _children[parent])
                {
                    w.WriteStartArray();
                    w.WriteStringValue(block);
                    w.WriteStringValue(layer);
                    w.WriteEndArray();
                }
                w.WriteEndArray();
                w.WriteEndArray();
            }
            w.WriteEndArray();
        }
    }

    /// <summary>
    /// What autocad_list_blocks needs, read in one go (#194, D-127): the facts
    /// of each block definition (entity count, xref and its path, dynamic,
    /// attribute tags) and, when asked, how many references each real name
    /// has. Names keep their case; the server matches them without it, as it
    /// does for COM.
    /// </summary>
    public sealed class BlockDefinitionList
    {
        private readonly List<Definition> _definitions = new List<Definition>();
        private readonly List<string> _names = new List<string>();
        private readonly Dictionary<string, int> _instances = new Dictionary<string, int>(StringComparer.Ordinal);

        private sealed class Definition
        {
            public string Name = "";
            public int Count;
            public bool Xref;
            public string? Path;
            public bool Dynamic;
            public IReadOnlyList<string> Tags = Array.Empty<string>();
        }

        /// <summary>
        /// False for a name the listing never shows: an anonymous or layout
        /// block (*Model_Space, *U12, *D3). The server leaves these out too;
        /// skipping them here only saves reading them.
        /// </summary>
        public static bool Listed(string? name) => !string.IsNullOrEmpty(name) && name![0] != '*';

        public void Add(string name, int count, bool xref, string? path, bool dynamic, IReadOnlyList<string>? tags)
        {
            _definitions.Add(new Definition
            {
                Name = name ?? "",
                Count = count,
                Xref = xref,
                Path = xref ? path ?? "" : null,
                Dynamic = dynamic,
                Tags = tags ?? Array.Empty<string>(),
            });
        }

        /// <summary>One placed reference of the block with this real (effective) name.</summary>
        public void Instance(string name)
        {
            name ??= "";
            if (_instances.TryGetValue(name, out var count))
            {
                _instances[name] = count + 1;
                return;
            }
            _names.Add(name);
            _instances[name] = 1;
        }

        /// <summary>
        /// {"definitions": [{"name", "count", "xref", "path", "dynamic", "tags"}...]},
        /// and with counts "instances": [[real name, n]...] in the order first met.
        /// </summary>
        public void Write(Utf8JsonWriter w, bool counts)
        {
            w.WriteStartArray("definitions");
            foreach (var definition in _definitions)
            {
                w.WriteStartObject();
                w.WriteString("name", definition.Name);
                w.WriteNumber("count", definition.Count);
                w.WriteBoolean("xref", definition.Xref);
                if (definition.Path == null) w.WriteNull("path");
                else w.WriteString("path", definition.Path);
                w.WriteBoolean("dynamic", definition.Dynamic);
                w.WriteStartArray("tags");
                foreach (var tag in definition.Tags) w.WriteStringValue(tag ?? "");
                w.WriteEndArray();
                w.WriteEndObject();
            }
            w.WriteEndArray();
            if (!counts) return;
            w.WriteStartArray("instances");
            foreach (var name in _names)
            {
                w.WriteStartArray();
                w.WriteStringValue(name);
                w.WriteNumberValue(_instances[name]);
                w.WriteEndArray();
            }
            w.WriteEndArray();
        }
    }
}
