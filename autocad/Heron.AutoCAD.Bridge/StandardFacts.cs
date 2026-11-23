using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// What autocad_check_standards' entity rules need of one object (#196,
    /// D-143), as the server's COM loop reads it: COM's Handle, ObjectName,
    /// Layer, Color and Linetype, and for the classes asked, the box COM's
    /// GetBoundingBox gives (x and y of its two corners). Raw facts only: the
    /// rules stay in the server. Color null: the object's colour is not an
    /// AutoCAD Color Index (a true colour, a colour book), whose COM Color no
    /// one has looked at yet, so the server reads over COM if it needs it.
    /// Box null: no box was asked for, or the object has none.
    /// </summary>
    public sealed class PropertyFact
    {
        /// <summary>AutoCAD's own colour method numbers (.NET's ColorMethod enum).</summary>
        public const int ByLayer = 192, ByBlock = 193, ByAci = 195;

        /// <summary>COM's Color numbers for ByLayer and ByBlock (acByLayer, acByBlock).</summary>
        public const int ComByLayer = 256, ComByBlock = 0;

        public PropertyFact(string handle, string objectClass, string layer, int? color, string linetype, double[]? box)
        {
            Handle = handle ?? "";
            ObjectClass = objectClass ?? "";
            Layer = layer ?? "";
            Color = color;
            Linetype = linetype ?? "";
            Box = box;
        }

        public string Handle { get; }
        public string ObjectClass { get; }
        public string Layer { get; }
        public int? Color { get; }
        public string Linetype { get; }
        public double[]? Box { get; }

        /// <summary>
        /// COM's Color for a colour method and index: 256 ByLayer, 0 ByBlock, the
        /// index 1-255 for an AutoCAD Color Index; null for anything else.
        /// </summary>
        public static int? ComColor(int method, int index)
        {
            switch (method)
            {
                case ByLayer: return ComByLayer;
                case ByBlock: return ComByBlock;
                case ByAci: return index >= 1 && index <= 255 ? index : (int?)null;
                default: return null;
            }
        }

        /// <summary>[handle, class, layer, color, linetype, [min x, min y, max x, max y] or null].</summary>
        public void Write(Utf8JsonWriter w)
        {
            w.WriteStartArray();
            w.WriteStringValue(Handle);
            w.WriteStringValue(ObjectClass);
            w.WriteStringValue(Layer);
            if (Color.HasValue) w.WriteNumberValue(Color.Value);
            else w.WriteNullValue();
            w.WriteStringValue(Linetype);
            if (Box == null) w.WriteNullValue();
            else FactNumber.WriteAll(w, Box);
            w.WriteEndArray();
        }
    }

    /// <summary>
    /// entity_properties (#196, D-143): the first "limit" selected objects, in
    /// the order selected, and how many were selected in all, so the server
    /// says "only the first n were read" as its COM loop does. A box is read
    /// only for a class whose name holds "box_classes" (the server sends
    /// "Dimension" when forbid_overlapping_dimensions is asked), as the COM
    /// loop's own test is.
    /// </summary>
    public sealed class PropertyFactList
    {
        private readonly List<PropertyFact> _items = new List<PropertyFact>();
        private readonly string _boxClasses;

        public PropertyFactList(long limit, string? boxClasses)
        {
            Limit = limit > 0 ? limit : long.MaxValue;
            _boxClasses = boxClasses ?? "";
        }

        public long Limit { get; }
        public long Total { get; private set; }
        public int Count => _items.Count;

        /// <summary>Counts one selected object; false once the limit is read, and the object is then not opened.</summary>
        public bool Take()
        {
            Total++;
            return Total <= Limit;
        }

        /// <summary>Whether to read this class's box: only when asked, by the COM loop's own test (the name holds the text).</summary>
        public bool WantsBox(string objectClass) =>
            _boxClasses.Length > 0 && (objectClass ?? "").IndexOf(_boxClasses, StringComparison.Ordinal) >= 0;

        public void Add(PropertyFact fact)
        {
            if (fact != null) _items.Add(fact);
        }

        /// <summary>{"entities": [row...], "total": n}.</summary>
        public void Write(Utf8JsonWriter w)
        {
            w.WriteStartArray("entities");
            foreach (var item in _items) item.Write(w);
            w.WriteEndArray();
            w.WriteNumber("total", Total);
        }
    }
}
