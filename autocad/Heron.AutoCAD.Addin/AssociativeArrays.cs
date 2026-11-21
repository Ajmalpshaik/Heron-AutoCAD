using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Associative arrays, as AutoCAD's ARRAY makes them (D-110): one array
    /// object that stays editable (ARRAYEDIT, grips, the Properties palette),
    /// in a grid, a ring or a run along a path. COM has no call for them; its
    /// ArrayRectangular / ArrayPolar make loose copies (autocad_array_entities).
    ///
    /// Where AutoCAD puts the items is checked against ArrayPlan before the
    /// transaction commits: an array built somewhere else is refused, and the
    /// abort leaves the drawing as it was.
    /// </summary>
    internal static class AssociativeArrays
    {
        public static RunResult Make(Database db, Transaction tr, RunArgs args)
        {
            var handles = args.Texts("handles");
            if (handles.Length == 0) throw new RunRefusal("Give the handles of the objects to array.");
            var sources = new ObjectIdCollection();
            var owner = ObjectId.Null;
            var sourceMin = new[] { double.MaxValue, double.MaxValue, double.MaxValue };
            var sourceMax = new[] { double.MinValue, double.MinValue, double.MinValue };
            Entity? only = null;
            foreach (var handle in handles)
            {
                var entity = RunDrawing.Open<Entity>(tr, db, handle, OpenMode.ForRead, "a drawn object");
                if (sources.Contains(entity.ObjectId)) continue;
                if (owner.IsNull) owner = entity.OwnerId;
                else if (entity.OwnerId != owner)
                    throw new RunRefusal("The objects are in different spaces. Array the ones in model space, or the ones on one layout, at a time.");
                var bounds = entity.Bounds;
                if (!bounds.HasValue) throw new RunRefusal(handle + " has no size to array (an empty text or block?).");
                Grow(sourceMin, sourceMax, bounds.Value);
                sources.Add(entity.ObjectId);
                only = entity;
            }
            if (sources.Count != 1) only = null;

            var pattern = args.Text("pattern").Trim().ToLowerInvariant();
            var given = args.Numbers("base_point");
            Point3d? asked = given.Length >= 2 ? new Point3d(given[0], given[1], given.Length > 2 ? given[2] : 0) : (Point3d?)null;
            Point3d Centre() => new Point3d((sourceMin[0] + sourceMax[0]) / 2, (sourceMin[1] + sourceMax[1]) / 2, (sourceMin[2] + sourceMax[2]) / 2);
            Point3d BlockOr(Point3d fallback) => asked ?? (only is BlockReference block ? block.Position : fallback);

            AssocArrayParameters parameters;
            Point3d basePoint;
            VertexRef origin;
            List<double[]> points;
            bool turns;
            string? why;
            var report = new List<Action<System.Text.Json.Utf8JsonWriter>>();

            switch (pattern)
            {
                case "rectangular":
                {
                    basePoint = BlockOr(Centre());
                    int rows = Whole(args, "rows", 1), columns = Whole(args, "columns", 1);
                    double rowSpacing = args.Number("row_spacing", 0), columnSpacing = args.Number("column_spacing", 0);
                    why = ArrayPlan.Rectangular(new[] { basePoint.X, basePoint.Y }, rows, columns, rowSpacing, columnSpacing, out points);
                    if (why != null) throw new RunRefusal(why);
                    // The parameterless constructor keeps AutoCAD's own axes (90 degrees apart);
                    // only the counts and spacings are set.
                    var grid = new AssocArrayRectangularParameters
                    {
                        ColumnCount = columns,
                        RowCount = rows,
                        LevelCount = 1,
                    };
                    if (columns > 1) grid.ColumnSpacing = columnSpacing;
                    if (rows > 1) grid.RowSpacing = rowSpacing;
                    parameters = grid;
                    origin = new VertexRef(basePoint);
                    turns = false;
                    report.Add(w =>
                    {
                        w.WriteNumber("rows", rows);
                        w.WriteNumber("columns", columns);
                        w.WriteNumber("row_spacing", rowSpacing);
                        w.WriteNumber("column_spacing", columnSpacing);
                    });
                    break;
                }
                case "polar":
                {
                    var c = args.Numbers("center");
                    if (c.Length < 2) throw new RunRefusal("A ring needs its centre as [x, y].");
                    var center = new Point3d(c[0], c[1], c.Length > 2 ? c[2] : sourceMin[2]);
                    basePoint = BlockOr(Centre());
                    var count = Whole(args, "count", 0);
                    var fill = args.Number("fill_angle", 2 * Math.PI);
                    var rotate = args.Flag("rotate_items", true);
                    why = ArrayPlan.Polar(new[] { center.X, center.Y }, new[] { basePoint.X, basePoint.Y }, count, fill, rotate,
                        out var step, out var radius, out var start, out points);
                    if (why != null) throw new RunRefusal(why);
                    // The array's own angles are in degrees, as ARRAY's Properties show them
                    // (ObjectARX's defaults are 15 between items and 90 between axes).
                    parameters = new AssocArrayPolarParameters
                    {
                        ItemCount = count,
                        AngleBetweenItems = Degrees(step),
                        FillAngle = Degrees(Math.Min(fill, 2 * Math.PI)),
                        StartAngle = Degrees(start),
                        Radius = radius,
                        RotateItems = rotate,
                        Direction = AssocArrayPolarParameters.ArcDirection.CounterClockwise,
                        RowCount = 1,
                        LevelCount = 1,
                    };
                    origin = new VertexRef(center);
                    turns = rotate;
                    report.Add(w =>
                    {
                        w.WriteNumber("count", count);
                        RunDrawing.WritePoint(w, "center", center.X, center.Y, center.Z);
                        w.WriteNumber("fill_angle", Math.Round(Degrees(Math.Min(fill, 2 * Math.PI)), 9));
                        w.WriteNumber("angle_between", Math.Round(Degrees(step), 9));
                        w.WriteBoolean("rotate_items", rotate);
                    });
                    break;
                }
                case "path":
                {
                    var pathHandle = args.Text("path");
                    var path = RunDrawing.Open<Curve>(tr, db, pathHandle, OpenMode.ForRead, "a line, polyline, arc, circle or spline to run along");
                    if (sources.Contains(path.ObjectId)) throw new RunRefusal("The path cannot also be one of the objects to array.");
                    double length;
                    try
                    {
                        length = path.GetDistanceAtParameter(path.EndParam);
                    }
                    catch (AcException)
                    {
                        throw new RunRefusal(pathHandle + " has no length AutoCAD can measure along.");
                    }
                    var closed = path.Closed;
                    var spacing = args.Number("spacing", 0);
                    var count = Whole(args, "count", 0);
                    var align = args.Flag("align_items", true);
                    why = ArrayPlan.Path(length, closed, count, spacing, out var items, out var step);
                    if (why != null) throw new RunRefusal(why);
                    basePoint = BlockOr(path.StartPoint);
                    points = new List<double[]>();
                    for (var i = 0; i < items; i++)
                    {
                        var at = path.GetPointAtDist(Math.Min(i * step, length));
                        points.Add(new[] { at.X, at.Y });
                    }
                    var run = new AssocArrayPathParameters(step, 1, 1, items, 1, 1, 0)
                    {
                        Path = new EdgeRef(path),
                        Method = spacing > 0 ? AssocArrayPathParameters.MethodType.Measure : AssocArrayPathParameters.MethodType.Divide,
                        AlignItems = align,
                        ItemCount = items,
                        ItemSpacing = step,
                    };
                    parameters = run;
                    origin = new VertexRef(basePoint);
                    turns = align;
                    var method = spacing > 0 ? "measure" : "divide";
                    report.Add(w =>
                    {
                        w.WriteString("path", pathHandle);
                        w.WriteNumber("path_length", Math.Round(length, 9));
                        w.WriteBoolean("path_closed", closed);
                        w.WriteString("method", method);
                        w.WriteNumber("count", items);
                        w.WriteNumber("spacing", Math.Round(step, 9));
                        w.WriteBoolean("align_items", align);
                    });
                    break;
                }
                default:
                    throw new RunRefusal("The pattern must be 'rectangular', 'polar' or 'path'.");
            }

            var array = AssocArray.CreateArray(sources, origin, parameters);
            // Have AutoCAD place the items now, so the array has its real extents.
            AssocManager.EvaluateTopLevelNetwork(db, null, 0);
            var made = (Entity)tr.GetObject(array.EntityId, OpenMode.ForWrite);
            var built = made.Bounds;
            if (!built.HasValue) throw new RunRefusal("AutoCAD made the array but it has no extents yet, so where it went cannot be checked.");
            var actual = built.Value;
            why = ArrayPlan.Check(
                new[] { actual.MinPoint.X, actual.MinPoint.Y }, new[] { actual.MaxPoint.X, actual.MaxPoint.Y }, points,
                new[] { sourceMin[0], sourceMin[1] }, new[] { sourceMax[0], sourceMax[1] }, new[] { basePoint.X, basePoint.Y }, turns);
            if (why != null) throw new RunRefusal(why);

            var kept = new List<string>();
            foreach (ObjectId id in sources)
                if (!id.IsErased) kept.Add(id.Handle.ToString());

            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", made.Handle.ToString());
                w.WriteBoolean("associative", AssocArray.IsAssociativeArray(made.ObjectId));
                w.WriteString("pattern", pattern);
                w.WriteNumber("items", points.Count);
                foreach (var write in report) write(w);
                RunDrawing.WritePoint(w, "base_point", basePoint.X, basePoint.Y, basePoint.Z);
                w.WriteStartArray("sources");
                foreach (ObjectId id in sources) w.WriteStringValue(id.Handle.ToString());
                w.WriteEndArray();
                // ARRAY takes the originals into the array; any still in the drawing are listed.
                w.WriteStartArray("sources_still_loose");
                foreach (var handle in kept) w.WriteStringValue(handle);
                w.WriteEndArray();
                w.WriteStartObject("extents");
                RunDrawing.WritePoint(w, "min", actual.MinPoint.X, actual.MinPoint.Y, actual.MinPoint.Z);
                RunDrawing.WritePoint(w, "max", actual.MaxPoint.X, actual.MaxPoint.Y, actual.MaxPoint.Z);
                w.WriteEndObject();
                RunDrawing.Style(made, db, tr, args, w);
            });
        }

        private static int Whole(RunArgs args, string name, int fallback)
        {
            var value = args.Number(name, fallback);
            if (value != Math.Floor(value) || value < int.MinValue || value > int.MaxValue)
                throw new RunRefusal("'" + name + "' must be a whole number.");
            return (int)value;
        }

        private static double Degrees(double radians) => radians * 180.0 / Math.PI;

        private static void Grow(double[] min, double[] max, Extents3d box)
        {
            min[0] = Math.Min(min[0], box.MinPoint.X);
            min[1] = Math.Min(min[1], box.MinPoint.Y);
            min[2] = Math.Min(min[2], box.MinPoint.Z);
            max[0] = Math.Max(max[0], box.MaxPoint.X);
            max[1] = Math.Max(max[1], box.MaxPoint.Y);
            max[2] = Math.Max(max[2], box.MaxPoint.Z);
        }
    }
}
