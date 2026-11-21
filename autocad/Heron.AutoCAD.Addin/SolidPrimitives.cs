using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.BoundaryRepresentation;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;
using BrepVertex = Autodesk.AutoCAD.BoundaryRepresentation.Vertex;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Two solids COM cannot make (D-112): a pyramid (PYRAMID) and a wall
    /// along a path (POLYSOLID). Main thread, inside PluginRunner's lock and
    /// transaction.
    /// </summary>
    internal static class SolidPrimitives
    {
        private const string PathKinds = "a path (a line, arc, circle, polyline or spline)";
        private const int Samples = 256;

        /// <summary>
        /// A pyramid or a flat-topped frustum, standing on the centre of its
        /// base. AutoCAD's CreatePyramid makes it about the origin, half way up,
        /// turned its own way: the corners it made are read back, and it is
        /// turned so one side faces the front and moved onto the base point.
        /// </summary>
        public static RunResult Pyramid(Database db, Transaction tr, RunArgs args)
        {
            var count = args.Number("sides", 4);
            if (count != Math.Floor(count) || count < PyramidMath.FewestSides || count > PyramidMath.MostSides)
                throw new RunRefusal("A pyramid has " + PyramidMath.FewestSides + " to " + PyramidMath.MostSides
                    + " sides (a whole number), as AutoCAD's PYRAMID allows.");
            var sides = (int)count;
            var toCorner = args.Text("radius_to", "side").Trim().ToLowerInvariant() == "corner";
            var bottom = PyramidMath.ToSide(args.Number("radius"), sides, toCorner);
            var top = PyramidMath.ToSide(args.Number("top_radius", 0.0), sides, toCorner);
            var height = args.Number("height");
            var error = PyramidMath.Check(sides, bottom, top, height);
            if (error != null) throw new RunRefusal(error);
            var at = Point(args, "base");
            var rotation = args.Number("rotation", 0.0);

            // A hopper (wider at the top) is made the usual way up and turned over.
            var flip = top > bottom;
            var wide = Math.Max(bottom, top);
            var narrow = Math.Min(bottom, top);
            var solid = MakePyramid(height, sides, wide, narrow, flip);
            try
            {
                var read = PyramidMath.WideEnd(Corners(solid), out var centre, out var angle, out var cornerRadius, out var low, out _);
                if (read)
                {
                    // AutoCAD's reference says the radius is to the middle of a side. If the
                    // pyramid it made says otherwise, make it again to the size asked for.
                    var made = cornerRadius * Math.Cos(Math.PI / sides);
                    var ratio = wide / made;
                    if (Math.Abs(ratio - 1) > 1e-3)
                    {
                        solid.Dispose();
                        solid = MakePyramid(height, sides, wide * ratio, narrow * ratio, flip);
                        read = PyramidMath.WideEnd(Corners(solid), out centre, out angle, out cornerRadius, out low, out _);
                    }
                }
                Matrix3d place;
                if (read)
                {
                    var axis = new Point3d(centre[0], centre[1], low);
                    var turn = PyramidMath.Turn(angle, sides, rotation);
                    place = Matrix3d.Displacement(at - axis) * Matrix3d.Rotation(turn, Vector3d.ZAxis, axis);
                }
                else
                {
                    // Its corners could not be read: as AutoCAD made it, about the origin half way up.
                    place = Matrix3d.Displacement(new Vector3d(at.X, at.Y, at.Z + height / 2));
                }
                solid.TransformBy(place);
                solid.SetDatabaseDefaults(db);
                var model = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
                model.AppendEntity(solid);
                tr.AddNewlyCreatedDBObject(solid, true);
                var added = solid;
                return RunResult.Done(w =>
                {
                    w.WriteBoolean("created", true);
                    w.WriteString("handle", added.Handle.ToString());
                    w.WriteNumber("sides", sides);
                    RunDrawing.WritePoint(w, "base", at.X, at.Y, at.Z);
                    w.WriteNumber("height", height);
                    w.WriteNumber("radius", Math.Round(bottom, 9));
                    w.WriteNumber("corner_radius", Math.Round(PyramidMath.CornerRadius(bottom, sides), 9));
                    w.WriteNumber("top_radius", Math.Round(top, 9));
                    w.WriteNumber("top_corner_radius", Math.Round(PyramidMath.CornerRadius(top, sides), 9));
                    w.WriteBoolean("turned", read);
                    if (!read)
                        w.WriteString("note", "Heron could not read the corners AutoCAD made, so the pyramid is turned the way AutoCAD made it, "
                            + "not with a side to the front. Look at it in plan.");
                    RunDrawing.Style(added, db, tr, args, w);
                    w.WriteNumber("expected_volume", Math.Round(PyramidMath.Volume(height, sides, bottom, top), 6));
                    SolidOperations.WriteVolume(w, "volume", added);
                });
            }
            catch
            {
                if (solid.ObjectId.IsNull) solid.Dispose();
                throw;
            }
        }

        /// <summary>
        /// A wall of a width and a height along a path (POLYSOLID). AutoCAD's
        /// .NET API has no polysolid call, so it is built the same shape: the
        /// path offset to each face of the wall, closed into one outline, made
        /// a region and extruded straight up. The path is kept.
        /// </summary>
        public static RunResult Polysolid(Database db, Transaction tr, RunArgs args)
        {
            var width = args.Number("width");
            var height = args.Number("height");
            var pathHandle = args.Text("path");
            Curve path;
            BlockTableRecord owner;
            var made = pathHandle.Length == 0;
            if (made)
            {
                path = PathFrom(args.Element("points"), args.Flag("closed", false));
                owner = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
            }
            else
            {
                path = RunDrawing.Open<Curve>(tr, db, pathHandle, OpenMode.ForRead, PathKinds);
                owner = (BlockTableRecord)tr.GetObject(path.OwnerId, OpenMode.ForWrite);
            }
            try
            {
                var along = Sample(path);
                var flat = along[0].Z;
                var size = Size(along);
                if (along.Any(p => Math.Abs(p.Z - flat) > 1e-6 * size))
                    throw new RunRefusal("The path is not flat in plan. A polysolid's wall goes straight up from a path drawn level: "
                        + "draw it flat (all at one Z), or use autocad_extrude_profile to sweep a section along a 3D route.");
                var closed = IsClosed(path);
                var side = PolysolidMath.Resolve(args.Text("side", "center"), closed, SignedArea(along) > 0, out var sideError);
                if (sideError != null) throw new RunRefusal(sideError);
                var error = PolysolidMath.Faces(width, height, side, out var first, out var second);
                if (error != null) throw new RunRefusal(error);

                Solid3d solid;
                using (var outline = Outline(path, first, second, closed))
                {
                    solid = new Solid3d();
                    solid.SetDatabaseDefaults(db);
                    try
                    {
                        solid.CreateExtrudedSolid(outline, new Vector3d(0, 0, height), new SweepOptions());
                    }
                    catch (AcException ex)
                    {
                        solid.Dispose();
                        throw new RunRefusal("AutoCAD could not raise the wall's outline " + height + " (" + ex.ErrorStatus + ").");
                    }
                }
                owner.AppendEntity(solid);
                tr.AddNewlyCreatedDBObject(solid, true);
                var length = Length(path);
                return RunResult.Done(w =>
                {
                    w.WriteBoolean("created", true);
                    w.WriteString("handle", solid.Handle.ToString());
                    if (!made) w.WriteString("path", pathHandle);
                    w.WriteNumber("width", width);
                    w.WriteNumber("height", height);
                    w.WriteString("side", side);
                    w.WriteBoolean("closed", closed);
                    w.WriteNumber("elevation", Math.Round(flat, 9));
                    if (!double.IsNaN(length)) w.WriteNumber("path_length", Math.Round(length, 6));
                    RunDrawing.Style(solid, db, tr, args, w);
                    SolidOperations.WriteVolume(w, "volume", solid);
                });
            }
            finally
            {
                if (made) path.Dispose();
            }
        }

        private static Solid3d MakePyramid(double height, int sides, double wide, double narrow, bool flip)
        {
            var solid = new Solid3d();
            try
            {
                solid.CreatePyramid(height, sides, wide, narrow);
                if (flip) solid.TransformBy(Matrix3d.Rotation(Math.PI, Vector3d.XAxis, Point3d.Origin));
            }
            catch (AcException ex)
            {
                solid.Dispose();
                throw new RunRefusal("AutoCAD could not make that pyramid (" + ex.ErrorStatus + "). Check the sizes are above zero.");
            }
            return solid;
        }

        /// <summary>Every corner of a solid not yet in the drawing, or none when the kernel will not say.</summary>
        private static List<double[]> Corners(Solid3d solid)
        {
            var corners = new List<double[]>();
            try
            {
                // Read before the solid is in the drawing: only the points are needed,
                // not the subentity paths a Brep from the entity alone lacks.
                using (var brep = new Brep(solid))
                    foreach (BrepVertex vertex in brep.Vertices)
                    {
                        var p = vertex.Point;
                        corners.Add(new[] { p.X, p.Y, p.Z });
                    }
            }
            catch (System.Exception)
            {
                corners.Clear();
            }
            return corners;
        }

        private static Point3d Point(RunArgs args, string name)
        {
            var values = args.Numbers(name);
            if (values.Length < 2 || values.Length > 3)
                throw new RunRefusal("The operation needs '" + name + "' as [x, y] or [x, y, z].");
            return new Point3d(values[0], values[1], values.Length == 3 ? values[2] : 0.0);
        }

        /// <summary>A polyline through the points, not added to the drawing: only its shape is used.</summary>
        private static Curve PathFrom(JsonElement points, bool closed)
        {
            if (points.ValueKind != JsonValueKind.Array)
                throw new RunRefusal("Give the wall's path: a curve's handle, or at least two points.");
            var list = new List<Point3d>();
            foreach (var item in points.EnumerateArray())
            {
                var xyz = item.ValueKind == JsonValueKind.Array
                    ? item.EnumerateArray().Where(v => v.ValueKind == JsonValueKind.Number).Select(v => v.GetDouble()).ToArray()
                    : new double[0];
                if (xyz.Length < 2 || xyz.Length > 3) throw new RunRefusal("Each point of the path is [x, y] or [x, y, z].");
                var p = new Point3d(xyz[0], xyz[1], xyz.Length == 3 ? xyz[2] : 0.0);
                if (list.Count > 0 && p.IsEqualTo(list[list.Count - 1])) continue;
                list.Add(p);
            }
            if (closed && list.Count > 2 && list[0].IsEqualTo(list[list.Count - 1])) list.RemoveAt(list.Count - 1);
            if (list.Count < 2) throw new RunRefusal("A wall's path needs at least two different points.");
            if (closed && list.Count < 3) throw new RunRefusal("A closed path needs at least three different points.");
            var level = list[0].Z;
            if (list.Any(p => Math.Abs(p.Z - level) > 1e-9 * Math.Max(1.0, Math.Abs(level))))
                throw new RunRefusal("The path's points are not all at one Z. A polysolid's wall goes straight up from a level path.");
            var polyline = new Polyline();
            for (var i = 0; i < list.Count; i++) polyline.AddVertexAt(i, new Point2d(list[i].X, list[i].Y), 0, 0, 0);
            polyline.Elevation = level;
            polyline.Closed = closed;
            return polyline;
        }

        /// <summary>
        /// The wall's outline as one region: the path offset to each face,
        /// joined at the ends (an open path) or one ring inside the other (a
        /// closed one). Which way AutoCAD's offset goes is read off the path,
        /// never assumed.
        /// </summary>
        private static Region Outline(Curve path, double first, double second, bool closed)
        {
            var left = LeftSign(path, Math.Abs(first) > 0 ? Math.Abs(first) : Math.Abs(second));
            var parts = new DBObjectCollection();
            try
            {
                var a = Offset(path, first * left);
                parts.Add(a);
                var b = Offset(path, second * left);
                parts.Add(b);
                if (closed) return Ring(a, b);
                parts.Add(new Line(a.StartPoint, b.StartPoint));
                parts.Add(new Line(a.EndPoint, b.EndPoint));
                return OneRegion(parts, "The wall's outline");
            }
            finally
            {
                foreach (DBObject part in parts) part.Dispose();
            }
        }

        private static Region Ring(Curve a, Curve b)
        {
            var one = OneRegion(new DBObjectCollection { a }, "One face of the wall");
            var other = OneRegion(new DBObjectCollection { b }, "One face of the wall");
            var outer = one.Area >= other.Area ? one : other;
            var inner = ReferenceEquals(outer, one) ? other : one;
            try
            {
                outer.BooleanOperation(BooleanOperationType.BoolSubtract, inner);
            }
            catch (AcException ex)
            {
                outer.Dispose();
                throw new RunRefusal("AutoCAD could not make the ring between the wall's faces (" + ex.ErrorStatus + ").");
            }
            finally
            {
                inner.Dispose();
            }
            return outer;
        }

        private static Region OneRegion(DBObjectCollection curves, string what)
        {
            DBObjectCollection regions;
            try
            {
                regions = Region.CreateFromCurves(curves);
            }
            catch (AcException ex)
            {
                throw new RunRefusal(what + " does not close into one shape (" + ex.ErrorStatus + "). The path probably turns tighter "
                    + "than the wall is wide, or crosses itself.");
            }
            if (regions.Count == 1) return (Region)regions[0];
            foreach (DBObject region in regions) region.Dispose();
            throw new RunRefusal(what + " makes " + regions.Count + " shapes, not one. The path probably turns tighter than the wall is wide, "
                + "or crosses itself.");
        }

        private static Curve Offset(Curve path, double distance)
        {
            if (distance == 0) return (Curve)path.Clone();
            DBObjectCollection curves;
            try
            {
                curves = path.GetOffsetCurvesGivenPlaneNormal(Vector3d.ZAxis, distance);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not offset the path by " + Math.Abs(distance) + " (" + ex.ErrorStatus + "). An arc tighter "
                    + "than the wall is wide is the usual reason.");
            }
            if (curves.Count == 1 && curves[0] is Curve one) return one;
            foreach (DBObject curve in curves) curve.Dispose();
            throw new RunRefusal("Offsetting the path by " + Math.Abs(distance) + " breaks it into " + curves.Count
                + " pieces: it turns tighter than the wall is wide.");
        }

        /// <summary>+1 when AutoCAD's positive offset of this path goes to its left, -1 when to its right.</summary>
        private static int LeftSign(Curve path, double probe)
        {
            var span = path.EndParam - path.StartParam;
            var at = path.StartParam + Math.Min(0.5, span / 2);
            var on = path.GetPointAtParameter(at);
            var heading = path.GetFirstDerivative(at);
            DBObjectCollection curves;
            try
            {
                curves = path.GetOffsetCurvesGivenPlaneNormal(Vector3d.ZAxis, probe);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not offset the path by " + probe + " (" + ex.ErrorStatus + ").");
            }
            try
            {
                if (curves.Count == 0 || !(curves[0] is Curve offset))
                    throw new RunRefusal("AutoCAD gave no offset of the path by " + probe + ". The path is probably too tight for the wall.");
                var near = offset.GetClosestPointTo(on, false);
                var sign = PolysolidMath.LeftOf(heading.X, heading.Y, near.X - on.X, near.Y - on.Y);
                if (sign == 0) throw new RunRefusal("Heron could not tell which side of the path is its left. Redraw the path without a doubled point.");
                return sign;
            }
            finally
            {
                foreach (DBObject curve in curves) curve.Dispose();
            }
        }

        private static List<Point3d> Sample(Curve path)
        {
            var points = new List<Point3d>();
            double start = path.StartParam, end = path.EndParam;
            for (var k = 0; k <= Samples; k++) points.Add(path.GetPointAtParameter(start + (end - start) * k / Samples));
            return points;
        }

        /// <summary>The path's area in plan, positive when it runs anticlockwise (shoelace, from samples).</summary>
        private static double SignedArea(List<Point3d> points)
        {
            var sum = 0.0;
            for (var i = 0; i < points.Count; i++)
            {
                var p = points[i];
                var q = points[(i + 1) % points.Count];
                sum += p.X * q.Y - q.X * p.Y;
            }
            return sum / 2;
        }

        private static double Size(List<Point3d> points)
        {
            var size = 1.0;
            foreach (var p in points) size = Math.Max(size, Math.Max(Math.Abs(p.X), Math.Max(Math.Abs(p.Y), Math.Abs(p.Z))));
            return size;
        }

        private static bool IsClosed(Curve curve)
        {
            if (curve.Closed) return true;
            try
            {
                return curve.StartPoint.IsEqualTo(curve.EndPoint);
            }
            catch (AcException)
            {
                return false;
            }
        }

        private static double Length(Curve curve)
        {
            try
            {
                return curve.GetDistanceAtParameter(curve.EndParam) - curve.GetDistanceAtParameter(curve.StartParam);
            }
            catch (AcException)
            {
                return double.NaN;
            }
        }
    }
}
