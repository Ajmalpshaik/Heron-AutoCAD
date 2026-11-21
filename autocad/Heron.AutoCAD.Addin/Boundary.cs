using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// BOUNDARY without typing it (#118, D-84): Editor.TraceBoundary from a
    /// point inside. -BOUNDARY and BPOLY typed through AutoLISP hung AutoCAD
    /// for over 100 s on a big plan, so the trace is kept small: with a
    /// window AutoCAD zooms there first (the trace looks at what is in view)
    /// and zooms back after, and the objects in view are counted first:
    /// over the limit, nothing is traced. The server stops waiting at its
    /// timeout; the trace itself cannot be cut short once it has started.
    /// </summary>
    internal static class Boundary
    {
        public static RunResult Trace(Database db, Transaction tr, RunArgs args)
        {
            var doc = AcApp.DocumentManager.GetDocument(db) ?? throw new RunRefusal("This drawing is not open in AutoCAD.");
            var ed = doc.Editor;
            var seed = args.Numbers("point");
            if (seed.Length < 2) throw new RunRefusal("Give the point inside the outline as [x, y].");
            var world = new Point3d(seed[0], seed[1], seed.Length > 2 ? seed[2] : 0.0);
            var most = (int)args.Number("most_objects", 5000);
            var islands = args.Flag("islands", true);
            var asRegion = args.Text("make", "polyline") == "region";
            var window = args.Element("window");

            var saved = ed.GetCurrentView();
            var zoomed = false;
            DBObjectCollection loops;
            int inView;
            try
            {
                // The window comes as its corners in the world (square to the UCS it was
                // given in, so maybe turned); without one, the view's own four corners.
                var corners = window.ValueKind == System.Text.Json.JsonValueKind.Array ? Corners(window, world.Z) : ViewCorners(saved, world.Z);
                if (window.ValueKind == System.Text.Json.JsonValueKind.Array)
                {
                    ZoomTo(ed, saved, corners);
                    zoomed = true;
                }

                var toUcs = ed.CurrentUserCoordinateSystem.Inverse();
                var polygon = new Point3dCollection();
                foreach (var corner in corners) polygon.Add(corner.TransformBy(toUcs));
                var found = ed.SelectCrossingPolygon(polygon);
                inView = found.Status == PromptStatus.OK && found.Value != null ? found.Value.Count : 0;
                if (inView == 0) throw new RunRefusal("Nothing is drawn in " + (zoomed ? "the window" : "view") + " round that point, so there is no outline to trace.");
                if (inView > most)
                    throw new RunRefusal(inView + " objects are in " + (zoomed ? "the window" : "view") + ", over the limit of " + most +
                        ": a trace over that many can hang AutoCAD. Give a smaller window round the room, freeze layers that do not bound it, or raise most_objects.");

                // TraceBoundary takes its seed point in the UCS.
                loops = ed.TraceBoundary(world.TransformBy(toUcs), islands);
            }
            finally
            {
                if (zoomed) ed.SetCurrentView(saved);
                saved.Dispose();
            }

            var curves = new List<Curve>();
            foreach (DBObject obj in loops)
            {
                if (obj is Curve curve && (curve.Closed || curve.StartPoint.IsEqualTo(curve.EndPoint))) curves.Add(curve);
                else obj.Dispose();
            }
            if (curves.Count == 0)
                throw new RunRefusal("AutoCAD found no closed outline round that point. Check the lines meet with no gap (or the point is inside), then try again.");

            curves.Sort((a, b) => Area(b).CompareTo(Area(a)));
            var space = (BlockTableRecord)tr.GetObject(db.CurrentSpaceId, OpenMode.ForWrite);
            if (asRegion) return AsRegion(db, tr, args, space, curves, inView, zoomed);

            var made = new List<(string handle, double area)>();
            foreach (var curve in curves)
            {
                curve.SetDatabaseDefaults(db);
                space.AppendEntity(curve);
                tr.AddNewlyCreatedDBObject(curve, true);
                made.Add((curve.Handle.ToString(), Area(curve)));
            }
            var outer = made[0];
            return RunResult.Done(w =>
            {
                w.WriteString("handle", outer.handle);
                w.WriteString("type", "polyline");
                w.WriteNumber("area", Math.Round(outer.area, 6));
                var net = outer.area;
                w.WriteStartArray("islands");
                for (var i = 1; i < made.Count; i++)
                {
                    net -= made[i].area;
                    w.WriteStartObject();
                    w.WriteString("handle", made[i].handle);
                    w.WriteNumber("area", Math.Round(made[i].area, 6));
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                w.WriteNumber("net_area", Math.Round(net, 6));
                w.WriteNumber("objects_in_view", inView);
                w.WriteBoolean("window", zoomed);
                foreach (var curve in curves) RunDrawing.Style(curve, db, tr, args, curve == curves[0] ? w : null);
            });
        }

        private static RunResult AsRegion(Database db, Transaction tr, RunArgs args, BlockTableRecord space, List<Curve> curves, int inView, bool zoomed)
        {
            var parts = new List<Region>();
            try
            {
                foreach (var curve in curves)
                {
                    var single = new DBObjectCollection { curve };
                    foreach (DBObject made in Region.CreateFromCurves(single))
                        if (made is Region region) parts.Add(region);
                        else made.Dispose();
                }
            }
            finally
            {
                foreach (var curve in curves) curve.Dispose();
            }
            if (parts.Count == 0) throw new RunRefusal("AutoCAD could not make a region from the outline it found.");
            parts.Sort((a, b) => b.Area.CompareTo(a.Area));
            var outer = parts[0];
            var gross = outer.Area;
            for (var i = 1; i < parts.Count; i++)
            {
                outer.BooleanOperation(BooleanOperationType.BoolSubtract, parts[i]);
                parts[i].Dispose();
            }
            outer.SetDatabaseDefaults(db);
            space.AppendEntity(outer);
            tr.AddNewlyCreatedDBObject(outer, true);
            return RunResult.Done(w =>
            {
                w.WriteString("handle", outer.Handle.ToString());
                w.WriteString("type", "region");
                w.WriteNumber("area", Math.Round(gross, 6));
                w.WriteStartArray("islands");
                w.WriteEndArray();
                w.WriteNumber("islands_cut_out", parts.Count - 1);
                w.WriteNumber("net_area", Math.Round(outer.Area, 6));
                w.WriteNumber("objects_in_view", inView);
                w.WriteBoolean("window", zoomed);
                RunDrawing.Style(outer, db, tr, args, w);
            });
        }

        private static double Area(Curve curve)
        {
            try
            {
                return Math.Abs(curve.Area);
            }
            catch (Autodesk.AutoCAD.Runtime.Exception)
            {
                return 0.0;
            }
        }

        /// <summary>From the view's own coordinates (DCS) to the world, as AutoCAD's zoom code does.</summary>
        private static Matrix3d ViewToWorld(ViewTableRecord view) =>
            Matrix3d.Rotation(-view.ViewTwist, view.ViewDirection, view.Target) *
            Matrix3d.Displacement(view.Target - Point3d.Origin) *
            Matrix3d.PlaneToWorld(view.ViewDirection);

        private static List<Point3d> Corners(System.Text.Json.JsonElement window, double z)
        {
            var points = new List<Point3d>();
            foreach (var pair in window.EnumerateArray())
            {
                if (pair.ValueKind != System.Text.Json.JsonValueKind.Array || pair.GetArrayLength() < 2) throw new RunRefusal("Each window corner must be [x, y].");
                points.Add(new Point3d(pair[0].GetDouble(), pair[1].GetDouble(), z));
            }
            if (points.Count == 2)
            {
                var a = points[0];
                var b = points[1];
                points = new List<Point3d> { a, new Point3d(b.X, a.Y, z), b, new Point3d(a.X, b.Y, z) };
            }
            if (points.Count < 3) throw new RunRefusal("The window needs two opposite corners.");
            return points;
        }

        /// <summary>The four corners of what is on screen, in the world.</summary>
        private static List<Point3d> ViewCorners(ViewTableRecord view, double z)
        {
            var toWorld = ViewToWorld(view);
            var hx = view.Width / 2.0;
            var hy = view.Height / 2.0;
            var c = view.CenterPoint;
            var points = new List<Point3d>();
            foreach (var (dx, dy) in new[] { (-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy) })
            {
                var p = new Point3d(c.X + dx, c.Y + dy, 0.0).TransformBy(toWorld);
                points.Add(new Point3d(p.X, p.Y, z));
            }
            return points;
        }

        /// <summary>Zoom so every corner of the window is in view, with a little room round it, keeping the view's shape.</summary>
        private static void ZoomTo(Editor ed, ViewTableRecord current, List<Point3d> corners)
        {
            var toView = ViewToWorld(current).Inverse();
            double minX = double.MaxValue, minY = double.MaxValue, maxX = double.MinValue, maxY = double.MinValue;
            foreach (var corner in corners)
            {
                var p = corner.TransformBy(toView);
                minX = Math.Min(minX, p.X);
                minY = Math.Min(minY, p.Y);
                maxX = Math.Max(maxX, p.X);
                maxY = Math.Max(maxY, p.Y);
            }
            var width = (maxX - minX) * 1.1;
            var height = (maxY - minY) * 1.1;
            var shape = current.Height > 0 ? current.Width / current.Height : 1.0;
            if (width / Math.Max(height, 1e-12) > shape) height = width / shape;
            else width = height * shape;
            using (var view = (ViewTableRecord)current.Clone())
            {
                view.CenterPoint = new Point2d((minX + maxX) / 2.0, (minY + maxY) / 2.0);
                view.Width = width;
                view.Height = height;
                ed.SetCurrentView(view);
            }
            ed.UpdateScreen();
        }
    }
}
