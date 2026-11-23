using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>What a select-and-zoom did: the handles sorted (<see cref="ShowPick"/>), and whether AutoCAD took the selection and the zoom.</summary>
    internal sealed class ShowOutcome
    {
        public ShowPicked<ObjectId> Picked { get; set; } = ShowPick.Sort(new ShowLook<ObjectId>[0]);
        public bool Selected { get; set; }
        public bool Zoomed { get; set; }

        /// <summary>How many are really selected now: what the Keep question and the show answer may say.</summary>
        public int Count => ShowPick.SelectedCount(Picked, Selected);

        /// <summary>The palette's line for it.</summary>
        public string Line(bool zoom) => ShowPick.Line(Picked, zoom, Selected, Zoomed);
    }

    /// <summary>
    /// Putting objects in front of the modeller: select them, zoom to them,
    /// and if asked hide everything else for a while (ISOLATEOBJECTS). Used
    /// by Keep or Discard, the palette's Select and Zoom, and the "show"
    /// operation. Main thread only. Nothing here changes what is in the drawing.
    /// </summary>
    internal static class Showing
    {
        public const int MostToHighlight = ShowPick.Most;

        /// <summary>
        /// Select and zoom to these handles (only select, with zoom false).
        /// Only drawing objects in the space in front are selected (#234,
        /// D-132): a style, a layer, an object on another layout or inside a
        /// block definition makes SetImpliedSelection throw eInvalidInput, so
        /// they are left out and counted by reason. Never throws for what is
        /// in the list; a selection AutoCAD still refuses is logged and said.
        /// </summary>
        public static ShowOutcome SelectAndZoom(Document doc, string[] handles, bool zoom = true)
        {
            if (handles.Length > MostToHighlight) return new ShowOutcome { Picked = ShowPick.TooManyOf<ObjectId>(handles.Length) };
            var looks = new List<ShowLook<ObjectId>>();
            Extents3d? box = null;
            using (doc.LockDocument())
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var space = doc.Database.CurrentSpaceId;
                var boxed = new HashSet<ObjectId>();
                foreach (var text in handles)
                {
                    var look = Look(doc.Database, tr, space, text ?? "");
                    looks.Add(look);
                    if (look.Place != ShowPlace.InSpace || !boxed.Add(look.Id)) continue;
                    // Zoom frames only what is selected.
                    try
                    {
                        if (tr.GetObject(look.Id, OpenMode.ForRead, false) is Entity entity)
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
                    }
                    catch (Autodesk.AutoCAD.Runtime.Exception)
                    {
                        // Some objects have no extents; they are still selected.
                    }
                }
                // Read only: nothing to keep, and no undo step.
                tr.Abort();
            }
            var outcome = new ShowOutcome { Picked = ShowPick.Sort(looks) };
            var ids = outcome.Picked.Ids;
            if (outcome.Picked.NotSelectable > 0)
                HeronLog.Write("show: " + outcome.Picked.NotSelectable + " of " + handles.Length + " left out of the selection (" +
                               outcome.Picked.OtherSpace.Count + " other space, " + outcome.Picked.InsideBlock.Count + " inside a block, " +
                               outcome.Picked.NotDrawingObject.Count + " not drawing objects)");
            if (ids.Count == 0) return outcome;
            try
            {
                doc.Editor.SetImpliedSelection(ids.ToArray());
                outcome.Selected = true;
            }
            catch (Autodesk.AutoCAD.Runtime.Exception ex)
            {
                // Even after the sorting; say so, and still zoom (#234).
                HeronLog.Error("Select " + ids.Count + " object(s)", ex);
            }
            if (zoom && box != null) outcome.Zoomed = ZoomTo(box.Value);
            return outcome;
        }

        /// <summary>Where one handle stands: selectable here, elsewhere, not a drawing object, or gone.</summary>
        private static ShowLook<ObjectId> Look(Database db, Transaction tr, ObjectId space, string text)
        {
            if (!ShowPick.TryParseHandle(text, out var value)) return new ShowLook<ObjectId>(text, ShowPlace.Gone, ObjectId.Null);
            try
            {
                if (!db.TryGetObjectId(new Handle(value), out var id) || id.IsNull || id.IsErased)
                    return new ShowLook<ObjectId>(text, ShowPlace.Gone, ObjectId.Null);
                var obj = tr.GetObject(id, OpenMode.ForRead, false);
                if (!(obj is Entity))
                    return new ShowLook<ObjectId>(text, ShowPlace.NotDrawingObject, ObjectId.Null);
                // An attribute or a vertex belongs to its block reference or
                // polyline: select that one. A few steps at most.
                var pick = obj;
                for (var step = 0; step < 4; step++)
                {
                    var owner = pick.OwnerId;
                    if (owner == space) return new ShowLook<ObjectId>(text, ShowPlace.InSpace, pick.ObjectId);
                    if (owner.IsNull || owner.IsErased) break;
                    var holder = tr.GetObject(owner, OpenMode.ForRead, false);
                    if (holder is BlockTableRecord record)
                        return new ShowLook<ObjectId>(text, record.IsLayout ? ShowPlace.OtherSpace : ShowPlace.InsideBlock, ObjectId.Null);
                    if (!(holder is Entity)) break;
                    pick = holder;
                }
                return new ShowLook<ObjectId>(text, ShowPlace.InsideBlock, ObjectId.Null);
            }
            catch (Autodesk.AutoCAD.Runtime.Exception)
            {
                // Erased while we looked, or not readable: not shown.
                return new ShowLook<ObjectId>(text, ShowPlace.Gone, ObjectId.Null);
            }
        }

        private static bool ZoomTo(Extents3d box)
        {
            var dx = Math.Max(box.MaxPoint.X - box.MinPoint.X, 1.0) * 0.15;
            var dy = Math.Max(box.MaxPoint.Y - box.MinPoint.Y, 1.0) * 0.15;
            try
            {
                dynamic acad = AcApp.AcadApplication;
                acad.ZoomWindow(
                    new[] { box.MinPoint.X - dx, box.MinPoint.Y - dy, 0.0 },
                    new[] { box.MaxPoint.X + dx, box.MaxPoint.Y + dy, 0.0 });
                return true;
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Zoom to the objects", ex);
                return false;
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
            var outcome = SelectAndZoom(doc, handles);
            var shown = outcome.Count;
            // ISOLATEOBJECTS takes the pickfirst set without asking only when
            // there is one; with none it would stop at "Select objects".
            var isolate = args.Flag("isolate", false) && shown > 0;
            if (isolate) doc.SendStringToExecute("_.ISOLATEOBJECTS ", true, false, false);
            return RunResult.Done(w =>
            {
                w.WriteNumber("shown", shown);
                w.WriteBoolean("isolated", isolate);
                w.WriteStartArray("not_found");
                foreach (var handle in outcome.Picked.Gone) w.WriteStringValue(handle);
                w.WriteEndArray();
                w.WriteStartArray("not_selectable");
                foreach (var left in outcome.Picked.NotSelectableWithReason())
                {
                    w.WriteStartObject();
                    w.WriteString("handle", left.Key);
                    w.WriteString("reason", left.Value);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                if (outcome.Picked.Ids.Count > 0 && !outcome.Selected) w.WriteBoolean("selection_refused", true);
            });
        }
    }
}
