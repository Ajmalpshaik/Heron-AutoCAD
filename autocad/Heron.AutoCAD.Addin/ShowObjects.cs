using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Putting objects in front of the modeller: select them, zoom to them,
    /// and if asked hide everything else for a while (ISOLATEOBJECTS). Used
    /// by Keep or Discard and by the "show" operation. Main thread only.
    /// Nothing here changes what is in the drawing.
    /// </summary>
    internal static class Showing
    {
        public const int MostToHighlight = 500;

        /// <summary>Select and zoom to these handles. How many were found (all of them when there are too many to highlight).</summary>
        public static int SelectAndZoom(Document doc, string[] handles, List<string>? missing = null)
        {
            if (handles.Length == 0 || handles.Length > MostToHighlight) return handles.Length;
            var ids = new List<ObjectId>();
            Extents3d? box = null;
            using (doc.LockDocument())
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                foreach (var text in handles)
                {
                    long value;
                    try
                    {
                        value = Convert.ToInt64((text ?? "").Trim(), 16);
                    }
                    catch (System.Exception ex) when (ex is FormatException || ex is OverflowException || ex is ArgumentException)
                    {
                        missing?.Add(text ?? "");
                        continue;
                    }
                    if (!doc.Database.TryGetObjectId(new Handle(value), out var id) || id.IsNull || id.IsErased)
                    {
                        missing?.Add(text ?? "");
                        continue;
                    }
                    ids.Add(id);
                    if (tr.GetObject(id, OpenMode.ForRead) is Entity entity)
                    {
                        try
                        {
                            var e = entity.GeometricExtents;
                            if (box == null) box = e;
                            else
                            {
                                var grow = box.Value;
                                grow.AddExtents(e);
                                box = grow;
                            }
                        }
                        catch (Autodesk.AutoCAD.Runtime.Exception)
                        {
                            // Some objects have no extents; they are still selected.
                        }
                    }
                }
                // Read only: nothing to keep, and no undo step.
                tr.Abort();
            }
            if (ids.Count == 0) return 0;
            doc.Editor.SetImpliedSelection(ids.ToArray());
            if (box != null) ZoomTo(box.Value);
            return ids.Count;
        }

        private static void ZoomTo(Extents3d box)
        {
            var dx = Math.Max(box.MaxPoint.X - box.MinPoint.X, 1.0) * 0.15;
            var dy = Math.Max(box.MaxPoint.Y - box.MinPoint.Y, 1.0) * 0.15;
            try
            {
                dynamic acad = AcApp.AcadApplication;
                acad.ZoomWindow(
                    new[] { box.MinPoint.X - dx, box.MinPoint.Y - dy, 0.0 },
                    new[] { box.MaxPoint.X + dx, box.MaxPoint.Y + dy, 0.0 });
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Zoom to the objects", ex);
            }
        }

        /// <summary>
        /// The "show" operation: select and zoom; with isolate, hide the rest
        /// until UNISOLATEOBJECTS (end_isolation does that). Isolation in
        /// AutoCAD is temporary (OBJECTISOLATIONMODE 0): it is not saved with
        /// the drawing.
        /// </summary>
        public static RunResult Show(Document doc, RunArgs args)
        {
            if (args.Flag("end_isolation", false))
            {
                doc.SendStringToExecute("_.UNISOLATEOBJECTS ", true, false, false);
                return RunResult.Done(w => w.WriteBoolean("isolation_ended", true));
            }
            var handles = args.Texts("handles");
            if (handles.Length == 0) throw new RunRefusal("Give at least one handle to show.");
            if (handles.Length > MostToHighlight)
                throw new RunRefusal("That is " + handles.Length + " objects; Heron shows at most " + MostToHighlight + " at once. Show them in parts, or by layer.");
            var missing = new List<string>();
            var found = SelectAndZoom(doc, handles, missing);
            var isolate = args.Flag("isolate", false) && found > 0;
            // The selection is the pickfirst set, so ISOLATEOBJECTS takes it without asking.
            if (isolate) doc.SendStringToExecute("_.ISOLATEOBJECTS ", true, false, false);
            return RunResult.Done(w =>
            {
                w.WriteNumber("shown", found);
                w.WriteBoolean("isolated", isolate);
                w.WriteStartArray("not_found");
                foreach (var handle in missing) w.WriteStringValue(handle);
                w.WriteEndArray();
            });
        }
    }
}
