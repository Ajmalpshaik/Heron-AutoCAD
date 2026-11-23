using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Numbers as the plug-in's reads write them (D-134). A finite double goes
    /// at full precision; NaN or infinity, which Utf8JsonWriter refuses, goes
    /// as the text "not finite", and the server then reads the drawing over
    /// COM. No value at all goes as null.
    /// </summary>
    public static class FactNumber
    {
        public const string NotFinite = "not finite";

        public static bool IsFinite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);

        public static void Write(Utf8JsonWriter w, double? value)
        {
            if (!value.HasValue) w.WriteNullValue();
            else if (IsFinite(value.Value)) w.WriteNumberValue(value.Value);
            else w.WriteStringValue(NotFinite);
        }

        public static void WriteAll(Utf8JsonWriter w, IEnumerable<double>? values)
        {
            w.WriteStartArray();
            if (values != null)
                foreach (var value in values) Write(w, value);
            w.WriteEndArray();
        }
    }

    /// <summary>
    /// What autocad_total_length and autocad_measure(layer=...) need of one
    /// object (#195, D-134), as the plug-in read it off the .NET object:
    /// its class (COM's ObjectName), layer, length (Length of a line or
    /// polyline, Length of an arc, Circumference of a circle), area, closed
    /// flag, and for a spline or an ellipse its definition, which the server
    /// measures with the code it uses for COM. Raw facts only: .NET gives
    /// more than COM does (an ellipse is Closed, a 3D polyline has an Area),
    /// and the server keeps only what COM would have given, from its table.
    /// </summary>
    public sealed class CurveFact
    {
        public CurveFact(string objectClass, string layer, double? length, double? area, bool? closed)
        {
            ObjectClass = objectClass ?? "";
            Layer = layer ?? "";
            Length = length;
            Area = area;
            Closed = closed;
        }

        public string ObjectClass { get; }
        public string Layer { get; }
        public double? Length { get; }
        public double? Area { get; }
        public bool? Closed { get; }

        /// <summary>A spline's NURBS data: what COM gives as Degree, IsRational, ControlPoints (flat x, y, z), Knots and Weights.</summary>
        public CurveFact Spline(int degree, bool rational, IReadOnlyList<double> controlPoints, IReadOnlyList<double> knots, IReadOnlyList<double>? weights)
        {
            _shape = w =>
            {
                w.WriteStartArray();
                w.WriteStringValue("spline");
                w.WriteNumberValue(degree);
                w.WriteBooleanValue(rational);
                FactNumber.WriteAll(w, controlPoints);
                FactNumber.WriteAll(w, knots);
                FactNumber.WriteAll(w, rational ? weights : null);
                w.WriteEndArray();
            };
            return this;
        }

        /// <summary>An ellipse's MajorRadius, MinorRadius, StartParameter and EndParameter.</summary>
        public CurveFact Ellipse(double major, double minor, double start, double end)
        {
            _shape = w =>
            {
                w.WriteStartArray();
                w.WriteStringValue("ellipse");
                FactNumber.Write(w, major);
                FactNumber.Write(w, minor);
                FactNumber.Write(w, start);
                FactNumber.Write(w, end);
                w.WriteEndArray();
            };
            return this;
        }

        private Action<Utf8JsonWriter>? _shape;

        /// <summary>[class, layer, length, area, closed, shape]; shape null for anything but a spline or an ellipse read.</summary>
        public void Write(Utf8JsonWriter w)
        {
            w.WriteStartArray();
            w.WriteStringValue(ObjectClass);
            w.WriteStringValue(Layer);
            FactNumber.Write(w, Length);
            FactNumber.Write(w, Area);
            if (Closed.HasValue) w.WriteBooleanValue(Closed.Value);
            else w.WriteNullValue();
            if (_shape == null) w.WriteNullValue();
            else _shape(w);
            w.WriteEndArray();
        }
    }

    /// <summary>
    /// entity_lengths (#195, D-134): one row per selected object, in the order
    /// selected. With "classes", only objects of those classes are sent (the
    /// curves autocad_total_length measures); without, every one (autocad_measure
    /// counts every object on the layer).
    /// </summary>
    public sealed class CurveFactList
    {
        private readonly List<CurveFact> _items = new List<CurveFact>();
        private readonly HashSet<string>? _classes;

        public CurveFactList(IEnumerable<string>? classes = null)
        {
            if (classes == null) return;
            _classes = new HashSet<string>(classes, StringComparer.Ordinal);
            if (_classes.Count == 0) _classes = null;
        }

        public int Count => _items.Count;

        /// <summary>False for a class the server did not ask for: it is not read at all.</summary>
        public bool Wanted(string objectClass) => _classes == null || _classes.Contains(objectClass ?? "");

        public void Add(CurveFact fact)
        {
            if (fact != null && Wanted(fact.ObjectClass)) _items.Add(fact);
        }

        /// <summary>{"items": [[class, layer, length, area, closed, shape]...]}.</summary>
        public void Write(Utf8JsonWriter w)
        {
            w.WriteStartArray("items");
            foreach (var item in _items) item.Write(w);
            w.WriteEndArray();
        }
    }

    /// <summary>One attribute on a block reference: COM's TagString and TextString, and the two kinds the server reads over COM.</summary>
    public sealed class TextAttribute
    {
        public TextAttribute(string tag, string text, bool multiline, bool constant)
        {
            Tag = tag ?? "";
            Text = text ?? "";
            Multiline = multiline;
            Constant = constant;
        }

        public string Tag { get; }
        public string Text { get; }
        public bool Multiline { get; }
        public bool Constant { get; }
    }

    /// <summary>
    /// entity_texts (#197, D-134): for each filter asked for, in that order,
    /// the selected objects in the order selected, each as
    /// [handle, layer, text, [x, y, z], block name, attributes]. Text is a
    /// text's TextString or an mtext's contents with every formatting code
    /// left in, as COM's TextString gives it; the point is COM's
    /// InsertionPoint; the block name is COM's Name (the *U name of a changed
    /// dynamic block, not the effective one); attributes are
    /// [[tag, text, multiline, constant]...] in the reference's own order,
    /// null for anything but a block reference.
    /// </summary>
    public sealed class TextFactList
    {
        /// <summary>Most filters one entity_texts takes: text, mtext and block references are three.</summary>
        public const int MostFilters = 8;

        private readonly List<List<Action<Utf8JsonWriter>>> _groups = new List<List<Action<Utf8JsonWriter>>>();

        /// <summary>
        /// "filters": [filter...], each read as count_entities reads its one
        /// filter. A refusal when there is none, or more than MostFilters.
        /// </summary>
        public static IReadOnlyList<IReadOnlyList<FilterPair>> ParseFilters(JsonElement filters)
        {
            if (filters.ValueKind != JsonValueKind.Array || filters.GetArrayLength() == 0 || filters.GetArrayLength() > MostFilters)
                throw new RunRefusal("entity_texts needs 'filters': a list of one to " + MostFilters + " filters.");
            var list = new List<IReadOnlyList<FilterPair>>();
            foreach (var filter in filters.EnumerateArray()) list.Add(EntityFilter.Parse(filter));
            return list;
        }

        public int Groups => _groups.Count;

        /// <summary>Starts the next filter's group; the objects added after it belong to it.</summary>
        public void Group() => _groups.Add(new List<Action<Utf8JsonWriter>>());

        public void Add(string handle, string layer, string? text, double[]? point, string? blockName, IReadOnlyList<TextAttribute>? attributes)
        {
            if (_groups.Count == 0) Group();
            handle ??= "";
            layer ??= "";
            _groups[_groups.Count - 1].Add(w =>
            {
                w.WriteStartArray();
                w.WriteStringValue(handle);
                w.WriteStringValue(layer);
                if (text == null) w.WriteNullValue();
                else w.WriteStringValue(text);
                if (point == null) w.WriteNullValue();
                else FactNumber.WriteAll(w, point);
                if (blockName == null) w.WriteNullValue();
                else w.WriteStringValue(blockName);
                if (attributes == null) w.WriteNullValue();
                else
                {
                    w.WriteStartArray();
                    foreach (var attribute in attributes)
                    {
                        w.WriteStartArray();
                        w.WriteStringValue(attribute.Tag);
                        w.WriteStringValue(attribute.Text);
                        w.WriteBooleanValue(attribute.Multiline);
                        w.WriteBooleanValue(attribute.Constant);
                        w.WriteEndArray();
                    }
                    w.WriteEndArray();
                }
                w.WriteEndArray();
            });
        }

        /// <summary>{"groups": [[row...]...]}, one group per filter, so the server knows every filter was read.</summary>
        public void Write(Utf8JsonWriter w)
        {
            w.WriteStartArray("groups");
            foreach (var group in _groups)
            {
                w.WriteStartArray();
                foreach (var row in group) row(w);
                w.WriteEndArray();
            }
            w.WriteEndArray();
        }
    }
}
