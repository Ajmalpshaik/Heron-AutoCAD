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
                Point3d low, high;
                if (window.ValueKind == System.Text.Json.JsonValueKind.Array)
                {
                    low = new Point3d(window[0][0].GetDouble(), window[0][1].GetDouble(), world.Z);
                    high = new Point3d(window[1][0].GetDouble(), window[1][1].GetDouble(), world.Z);
                    ZoomTo(ed, saved, low, high);
                    zoomed = true;
                }
                else
                {
                    ViewCorners(saved, out low, out high);
                }

                var toUcs = ed.CurrentUserCoordinateSystem.Inverse();
                var found = ed.SelectCrossingWindow(low.TransformBy(toUcs), high.TransformBy(toUcs));
                inView = found.Status == PromptStatus.OK && found.Value != null ? found.Value.Count : 0;
                if (inView == 0) throw new RunRefusal("Nothing is drawn in " + (zoomed ? "the window" : "view") + " round that point, so there is no outline to trace.");
                if (inView > most)
                    throw new RunRefusal(inView + " objects are in " + (zoomed ? "the window" : "view") + ", over the limit of " + most +
                        ": a trace over that many can hang AutoCAD. Give a smaller window round the room, freeze layers that do not bound it, or raise most_objects.");

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

        private static void ViewCorners(ViewTableRecord view, out Point3d low, out Point3d high)
        {
            var toWorld = ViewToWorld(view);
            var half = new Vector2d(view.Width / 2.0, view.Height / 2.0);
            var a = new Point3d(view.CenterPoint.X - half.X, view.CenterPoint.Y - half.Y, 0.0).TransformBy(toWorld);
            var b = new Point3d(view.CenterPoint.X + half.X, view.CenterPoint.Y + half.Y, 0.0).TransformBy(toWorld);
            low = new Point3d(Math.Min(a.X, b.X), Math.Min(a.Y, b.Y), Math.Min(a.Z, b.Z));
            high = new Point3d(Math.Max(a.X, b.X), Math.Max(a.Y, b.Y), Math.Max(a.Z, b.Z));
        }

        /// <summary>Zoom so the window fills the view, with a little room round it, keeping the view's shape.</summary>
        private static void ZoomTo(Editor ed, ViewTableRecord current, Point3d low, Point3d high)
        {
            var toView = ViewToWorld(current).Inverse();
            var a = low.TransformBy(toView);
            var b = high.TransformBy(toView);
            var width = Math.Abs(b.X - a.X) * 1.1;
            var height = Math.Abs(b.Y - a.Y) * 1.1;
            var shape = current.Height > 0 ? current.Width / current.Height : 1.0;
            if (width / Math.Max(height, 1e-12) > shape) height = width / shape;
            else width = height * shape;
            using (var view = (ViewTableRecord)current.Clone())
            {
                view.CenterPoint = new Point2d((a.X + b.X) / 2.0, (a.Y + b.Y) / 2.0);
                view.Width = width;
                view.Height = height;
                ed.SetCurrentView(view);
            }
            ed.UpdateScreen();
        }
    }
}
