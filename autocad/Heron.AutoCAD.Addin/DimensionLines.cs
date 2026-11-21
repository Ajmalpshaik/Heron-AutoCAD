using System;
using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Where a linear dimension's line is, and moving it (DIMSPACE, #116, D-80).
    /// COM has no definition points on a rotated dimension, so it cannot move
    /// the line without moving the extension line origins too. The spacing is
    /// worked out by the server (tools/dimensions_edit.py); this only reads and
    /// writes DimLinePoint.
    /// </summary>
    internal static class DimensionLines
    {
        private const double Flat = 1e-9;

        /// <summary>Each linear or aligned dimension's direction and a point its line passes through.</summary>
        public static RunResult Read(Database db, Transaction tr, RunArgs args)
        {
            var handles = args.Texts("handles");
            if (handles.Length == 0) throw new RunRefusal("Give the dimensions to read, by handle.");
            var found = new List<Action<Utf8JsonWriter>>();
            var skipped = new List<(string handle, string why)>();
            foreach (var handle in handles)
            {
                var obj = tr.GetObject(RunDrawing.IdOf(db, handle), OpenMode.ForRead);
                if (!(obj is Dimension dim))
                {
                    skipped.Add((handle, "it is " + RunDrawing.Kind(obj) + ", not a dimension"));
                    continue;
                }
                if (!dim.Normal.IsParallelTo(Vector3d.ZAxis))
                {
                    skipped.Add((handle, "it is not drawn flat in plan (its normal is not Z)"));
                    continue;
                }
                Vector3d direction;
                Point3d line;
                string kind;
                if (dim is RotatedDimension rotated)
                {
                    // Normal is Z, so the dimension's own X axis is the world X axis.
                    direction = new Vector3d(Math.Cos(rotated.Rotation), Math.Sin(rotated.Rotation), 0);
                    line = rotated.DimLinePoint;
                    kind = "rotated";
                }
                else if (dim is AlignedDimension aligned)
                {
                    direction = aligned.XLine2Point - aligned.XLine1Point;
                    line = aligned.DimLinePoint;
                    kind = "aligned";
                }
                else
                {
                    skipped.Add((handle, "only linear and aligned dimensions are spaced; this is " + RunDrawing.Kind(obj)));
                    continue;
                }
                if (direction.Length < Flat)
                {
                    skipped.Add((handle, "its extension lines start at the same point, so it has no direction"));
                    continue;
                }
                var h = handle;
                var d = direction.GetNormal();
                var p = line;
                var k = kind;
                found.Add(w =>
                {
                    w.WriteStartObject();
                    w.WriteString("handle", h);
                    w.WriteString("kind", k);
                    w.WriteStartArray("direction");
                    w.WriteNumberValue(Math.Round(d.X, 12));
                    w.WriteNumberValue(Math.Round(d.Y, 12));
                    w.WriteEndArray();
                    RunDrawing.WritePoint(w, "line_point", p.X, p.Y, p.Z);
                    w.WriteEndObject();
                });
            }
            return RunResult.Done(w =>
            {
                w.WriteStartArray("dimensions");
                foreach (var write in found) write(w);
                w.WriteEndArray();
                WriteSkipped(w, skipped);
            });
        }

        /// <summary>Each dimension's line moved through the point given; the extension line origins stay.</summary>
        public static RunResult Move(Database db, Transaction tr, RunArgs args)
        {
            var moves = args.Element("moves");
            if (moves.ValueKind != JsonValueKind.Array || moves.GetArrayLength() == 0)
                throw new RunRefusal("Give the dimension lines to move.");
            var moved = new List<string>();
            foreach (var move in moves.EnumerateArray())
            {
                var handle = move.TryGetProperty("handle", out var h) && h.ValueKind == JsonValueKind.String ? h.GetString() ?? "" : "";
                var to = Point(move, handle);
                var dim = RunDrawing.Open<Dimension>(tr, db, handle, OpenMode.ForWrite, "a dimension");
                if (dim is RotatedDimension rotated) rotated.DimLinePoint = to;
                else if (dim is AlignedDimension aligned) aligned.DimLinePoint = to;
                else throw new RunRefusal(handle + " is " + RunDrawing.Kind(dim) + "; only linear and aligned dimensions are spaced.");
                dim.RecomputeDimensionBlock(true);
                moved.Add(handle);
            }
            return RunResult.Done(w =>
            {
                w.WriteNumber("moved", moved.Count);
                w.WriteStartArray("handles");
                foreach (var handle in moved) w.WriteStringValue(handle);
                w.WriteEndArray();
            });
        }

        private static Point3d Point(JsonElement move, string handle)
        {
            if (!move.TryGetProperty("to", out var to) || to.ValueKind != JsonValueKind.Array || to.GetArrayLength() < 2)
                throw new RunRefusal("The move for " + handle + " has no point to go to.");
            var values = new List<double>();
            foreach (var item in to.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Number) throw new RunRefusal("The move for " + handle + " has a point that is not numbers.");
                values.Add(item.GetDouble());
            }
            return new Point3d(values[0], values[1], values.Count > 2 ? values[2] : 0.0);
        }

        internal static void WriteSkipped(Utf8JsonWriter w, List<(string handle, string why)> skipped)
        {
            w.WriteStartArray("skipped");
            foreach (var (handle, why) in skipped)
            {
                w.WriteStartObject();
                w.WriteString("handle", handle);
                w.WriteString("why", why);
                w.WriteEndObject();
            }
            w.WriteEndArray();
        }
    }
}
