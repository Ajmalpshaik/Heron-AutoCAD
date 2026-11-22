using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The drafting edits COM has no call for (D-97): MLINE's own Close, a
    /// spline drawn by its control points, and a spline's fit points moved,
    /// added or taken away. Each runs in the one transaction PluginRunner
    /// opens, so a refusal leaves the drawing as it was.
    /// </summary>
    internal static class Drafting
    {
        /// <summary>Close a multiline the way MLINE's Close option does: the last corner mitred, not overlapped.</summary>
        public static RunResult CloseMultiline(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var mline = RunDrawing.Open<Mline>(tr, db, handle, OpenMode.ForWrite, "a multiline");
            var count = mline.NumberOfVertices;
            if (count < 3) throw new RunRefusal(handle + " has " + count + " vertices; a closed multiline needs three.");
            var already = mline.IsClosed;
            if (!already) mline.IsClosed = true;
            if (!mline.IsClosed) throw new RunRefusal("AutoCAD would not close " + handle + ".");
            return RunResult.Done(w =>
            {
                w.WriteString("handle", mline.Handle.ToString());
                w.WriteBoolean("closed", true);
                w.WriteBoolean("already_closed", already);
                w.WriteNumber("vertices", count);
            });
        }

        /// <summary>
        /// A spline from its control points and knots, the SPLINE command's CV
        /// method. The server works the knots out (clamped, or wrapped round for
        /// a closed one); this checks them again and makes it.
        /// </summary>
        public static RunResult AddControlSpline(Database db, Transaction tr, RunArgs args)
        {
            var degree = (int)args.Number("degree");
            var flat = args.Numbers("points");
            var knots = args.Numbers("knots");
            var problem = SplineCheck.ControlProblem(degree, flat, knots);
            if (problem != null) throw new RunRefusal(problem);

            var points = new Point3dCollection();
            for (var i = 0; i < flat.Length; i += 3) points.Add(new Point3d(flat[i], flat[i + 1], flat[i + 2]));
            var knotList = new DoubleCollection();
            foreach (var knot in knots) knotList.Add(knot);
            // Not rational (no weights), and neither closed nor periodic as AutoCAD
            // flags them: a closed one comes with its points wrapped round and
            // uniform knots, so it meets itself smoothly as it is.
            var spline = new Spline(degree, false, false, false, points, knotList, new DoubleCollection(), 0.0, 0.0);
            spline.SetDatabaseDefaults(db);
            var space = Space(db, tr, args.Text("space"));
            space.AppendEntity(spline);
            tr.AddNewlyCreatedDBObject(spline, true);

            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", spline.Handle.ToString());
                w.WriteString("type", "spline");
                w.WriteNumber("degree", spline.Degree);
                w.WriteNumber("control_points", spline.NumControlPoints);
                w.WriteBoolean("closed", spline.Closed);
                RunDrawing.Style(spline, db, tr, args, w);
            });
        }

        /// <summary>
        /// Move, add and take away a spline's fit points, in the order given,
        /// then read them back: anything but the list the server worked out
        /// is refused, and the transaction puts the spline back as it was.
        /// </summary>
        public static RunResult EditFitPoints(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var spline = RunDrawing.Open<Spline>(tr, db, handle, OpenMode.ForWrite, "a spline");
            if (!spline.HasFitData || spline.NumFitPoints == 0)
                throw new RunRefusal(handle + " is drawn by its control points, so it has no fit points to edit. "
                    + "Redraw it through points with autocad_draw_spline, or move its control points with SPLINEDIT.");
            var steps = Steps(args.Element("steps"));
            var before = spline.NumFitPoints;
            var problem = SplineCheck.StepsProblem(before, steps, spline.Closed);
            if (problem != null) throw new RunRefusal(problem);

            foreach (var step in steps)
            {
                var at = new Point3d(step.X, step.Y, step.Z);
                if (step.Kind == "set") spline.SetFitPointAt(step.Index, at);
                else if (step.Kind == "insert") spline.InsertFitPointAt(step.Index, at);
                else spline.RemoveFitPointAt(step.Index);
            }

            var wanted = args.Numbers("result");
            var now = FitPoints(spline);
            if (wanted.Length > 0 && !SplineCheck.SamePoints(now, wanted))
                throw new RunRefusal("AutoCAD did not end up with the fit points asked for on " + handle + ".");
            return RunResult.Done(w =>
            {
                w.WriteString("handle", spline.Handle.ToString());
                w.WriteBoolean("edited", true);
                w.WriteNumber("fit_points_before", before);
                w.WriteNumber("fit_points", spline.NumFitPoints);
                w.WriteBoolean("closed", spline.Closed);
            });
        }

        private static List<SplineCheck.Step> Steps(JsonElement list)
        {
            var steps = new List<SplineCheck.Step>();
            if (list.ValueKind != JsonValueKind.Array) throw new RunRefusal("The edit came with no steps.");
            foreach (var item in list.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object) throw new RunRefusal("Each fit-point edit must be an object.");
                var kind = item.TryGetProperty("kind", out var k) && k.ValueKind == JsonValueKind.String ? k.GetString() ?? "" : "";
                var index = item.TryGetProperty("index", out var n) && n.ValueKind == JsonValueKind.Number ? n.GetInt32() : -1;
                double x = 0, y = 0, z = 0;
                if (item.TryGetProperty("point", out var p) && p.ValueKind == JsonValueKind.Array)
                {
                    var values = new List<double>();
                    foreach (var v in p.EnumerateArray())
                        if (v.ValueKind == JsonValueKind.Number) values.Add(v.GetDouble());
                    if (values.Count < 3 && kind != "remove") throw new RunRefusal("A fit point must come as x, y, z.");
                    if (values.Count >= 3) (x, y, z) = (values[0], values[1], values[2]);
                }
                else if (kind != "remove")
                {
                    throw new RunRefusal("Moving or adding a fit point needs the point.");
                }
                steps.Add(new SplineCheck.Step(kind, index, x, y, z));
            }
            return steps;
        }

        private static double[] FitPoints(Spline spline)
        {
            var values = new List<double>();
            for (var i = 0; i < spline.NumFitPoints; i++)
            {
                var p = spline.GetFitPointAt(i);
                values.Add(p.X);
                values.Add(p.Y);
                values.Add(p.Z);
            }
            return values.ToArray();
        }

        /// <summary>Model space, or the space of the sheet tab that is active.</summary>
        private static BlockTableRecord Space(Database db, Transaction tr, string space)
        {
            if (space != "paper")
                return (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
            var layouts = LayoutManager.Current;
            var current = layouts.CurrentLayout;
            if (string.Equals(current, "Model", System.StringComparison.OrdinalIgnoreCase))
                throw new RunRefusal("The Model tab is active, so there is no sheet to draw on. Click a sheet tab, or use space='model'.");
            var layout = (Layout)tr.GetObject(layouts.GetLayoutId(current), OpenMode.ForRead);
            return (BlockTableRecord)tr.GetObject(layout.BlockTableRecordId, OpenMode.ForWrite);
        }
    }
}
