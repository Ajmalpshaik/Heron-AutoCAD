using System;
using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Annotative objects and their annotation scales (#108, D-81). Only the
    /// .NET API reaches an object's scales (DBObject.Annotative, AddContext,
    /// RemoveContext, HasContext; the drawing's list is the
    /// ACDB_ANNOTATIONSCALES context collection). COM has none of it.
    /// </summary>
    internal static class AnnotationScales
    {
        private const string Collection = "ACDB_ANNOTATIONSCALES";
        private const double SameRatio = 1e-9;

        /// <summary>The drawing's scale list, its current annotation scale, and each object's scales.</summary>
        public static RunResult Read(Database db, Transaction tr, RunArgs args)
        {
            var scales = Scales(db);
            var current = db.Cannoscale;
            var objects = new List<Action<Utf8JsonWriter>>();
            foreach (var handle in args.Texts("handles"))
            {
                var obj = tr.GetObject(RunDrawing.IdOf(db, handle), OpenMode.ForRead);
                var h = handle;
                var state = State(obj);
                var held = Held(obj, scales);
                var height = Height(obj);
                var kind = RunDrawing.Kind(obj);
                objects.Add(w => WriteObject(w, h, kind, state, held, height, null, null));
            }
            return RunResult.Done(w =>
            {
                if (current != null) WriteScale(w, "current", current);
                w.WriteStartArray("scales");
                foreach (var scale in scales)
                {
                    w.WriteStartObject();
                    w.WriteString("name", scale.Name);
                    w.WriteNumber("paper", scale.PaperUnits);
                    w.WriteNumber("drawing", scale.DrawingUnits);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                w.WriteBoolean("anno_all_visible", db.AnnoAllVisible);
                w.WriteStartArray("objects");
                foreach (var write in objects) write(w);
                w.WriteEndArray();
            });
        }

        /// <summary>
        /// Make objects annotative (or not) and add or remove scales on them.
        /// An annotative object always keeps at least one scale: a removal that
        /// would leave none is refused, and nothing is changed.
        /// </summary>
        public static RunResult Set(Database db, Transaction tr, RunArgs args)
        {
            var handles = args.Texts("handles");
            if (handles.Length == 0) throw new RunRefusal("Give the objects, by handle.");
            bool? annotative = args.Has("annotative") ? args.Flag("annotative", true) : (bool?)null;
            // Every refusal comes before anything is written: the scales to remove and add are
            // found first, each object is checked to keep a scale, and only then is a missing
            // scale added to the drawing's list (an aborted transaction is not trusted to take
            // a new scale back out of it).
            var remove = Resolve(db, args.Texts("remove"), args.Numbers("remove_paper"), args.Numbers("remove_drawing"), false, null);
            var missing = new List<(string name, double paper, double drawing)>();
            var add = Resolve(db, args.Texts("add"), args.Numbers("add_paper"), args.Numbers("add_drawing"), args.Flag("create_missing", false), missing);
            var scales = Scales(db);
            var current = db.Cannoscale;
            AnnotationScale? currentScale = current == null ? null : Find(scales, current.Name, current.PaperUnits, current.DrawingUnits);
            foreach (var handle in handles)
            {
                var obj = tr.GetObject(RunDrawing.IdOf(db, handle), OpenMode.ForRead);
                var state = State(obj);
                if (state == "cannot" || annotative == false) continue;
                if (state != "yes" && annotative != true && add.Count == 0 && missing.Count == 0) continue;
                var keeps = new HashSet<string>(Held(obj, scales), StringComparer.OrdinalIgnoreCase);
                foreach (var scale in add) keeps.Add(scale.Name);
                foreach (var scale in missing) keeps.Add(scale.name);
                if (keeps.Count == 0 && currentScale != null) keeps.Add(currentScale.Name);
                foreach (var scale in remove) keeps.Remove(scale.Name);
                if (keeps.Count == 0)
                    throw new RunRefusal(handle + " would be left with no annotation scale; an annotative object keeps at least one. "
                        + "Leave one on it, or make it not annotative with annotative=false.");
            }
            var created = new List<string>();
            if (missing.Count > 0)
            {
                var collection = db.ObjectContextManager.GetContextCollection(Collection);
                foreach (var (name, paper, drawing) in missing)
                {
                    collection.AddContext(new AnnotationScale { Name = name, PaperUnits = paper, DrawingUnits = drawing });
                    var made = Find(Scales(db), name, paper, drawing);
                    if (made == null) throw new RunRefusal("AutoCAD did not add the scale " + name + " to the drawing's list.");
                    add.Add(made);
                    created.Add(name);
                }
                scales = Scales(db);
            }

            var objects = new List<Action<Utf8JsonWriter>>();
            var skipped = new List<(string handle, string why)>();
            foreach (var handle in handles)
            {
                var obj = tr.GetObject(RunDrawing.IdOf(db, handle), OpenMode.ForRead);
                var was = State(obj);
                if (was == "cannot")
                {
                    skipped.Add((handle, RunDrawing.Kind(obj) + " cannot be annotative"));
                    continue;
                }
                var heldBefore = Held(obj, scales);
                // Opened for write only when something changes, so an object already as asked is left untouched.
                void Write()
                {
                    if (!obj.IsWriteEnabled) obj.UpgradeOpen();
                }
                if (annotative == false)
                {
                    if (was == "yes")
                    {
                        Write();
                        obj.Annotative = AnnotativeStates.False;
                    }
                }
                else
                {
                    if ((annotative == true || add.Count > 0) && was != "yes")
                    {
                        Write();
                        obj.Annotative = AnnotativeStates.True;
                    }
                    if (State(obj) == "yes")
                    {
                        foreach (var scale in add)
                            if (!obj.HasContext(scale))
                            {
                                Write();
                                obj.AddContext(scale);
                            }
                        // Made annotative with no scale asked for: the current one, as AutoCAD does.
                        if (Held(obj, scales).Count == 0 && currentScale != null)
                        {
                            Write();
                            obj.AddContext(currentScale);
                        }
                        foreach (var scale in remove)
                            if (obj.HasContext(scale))
                            {
                                Write();
                                obj.RemoveContext(scale);
                            }
                        // Checked before anything was written; kept as a last guard.
                        if (Held(obj, scales).Count == 0)
                            throw new RunRefusal(handle + " would be left with no annotation scale; an annotative object keeps at least one. "
                                + "Leave one on it, or make it not annotative with annotative=false.");
                    }
                    else if (remove.Count > 0)
                    {
                        skipped.Add((handle, "it is not annotative, so it has no scales to remove"));
                    }
                }
                var h = handle;
                var kind = RunDrawing.Kind(obj);
                var state = State(obj);
                var held = Held(obj, scales);
                var height = Height(obj);
                objects.Add(w => WriteObject(w, h, kind, state, held, height, was, heldBefore));
            }
            return RunResult.Done(w =>
            {
                if (current != null) WriteScale(w, "current", current);
                w.WriteStartArray("objects");
                foreach (var write in objects) write(w);
                w.WriteEndArray();
                w.WriteStartArray("scales_created");
                foreach (var name in created) w.WriteStringValue(name);
                w.WriteEndArray();
                DimensionLines.WriteSkipped(w, skipped);
            });
        }

        private static List<AnnotationScale> Scales(Database db)
        {
            var list = new List<AnnotationScale>();
            var collection = db.ObjectContextManager.GetContextCollection(Collection);
            if (collection == null) return list;
            foreach (ObjectContext context in collection)
                if (context is AnnotationScale scale) list.Add(scale);
            return list;
        }

        /// <summary>A scale by name, else by the same paper : drawing ratio; null when the drawing has neither.</summary>
        private static AnnotationScale? Find(List<AnnotationScale> scales, string name, double paper, double drawing)
        {
            var key = (name ?? "").Trim();
            foreach (var scale in scales)
                if (string.Equals(scale.Name.Trim(), key, StringComparison.OrdinalIgnoreCase)) return scale;
            if (paper > 0 && drawing > 0)
            {
                var ratio = paper / drawing;
                foreach (var scale in scales)
                    if (scale.DrawingUnits > 0 && Math.Abs(scale.PaperUnits / scale.DrawingUnits - ratio) <= SameRatio * Math.Max(1.0, ratio))
                        return scale;
            }
            return null;
        }

        /// <summary>
        /// The scales by name or ratio. One the drawing has not got is a refusal, or, when it may be
        /// created, goes into <paramref name="missing"/> to be added once every check has passed.
        /// </summary>
        private static List<AnnotationScale> Resolve(Database db, string[] names, double[] paper, double[] drawing, bool createMissing,
            List<(string name, double paper, double drawing)>? missing)
        {
            var found = new List<AnnotationScale>();
            for (var i = 0; i < names.Length; i++)
            {
                var p = i < paper.Length ? paper[i] : 0.0;
                var d = i < drawing.Length ? drawing[i] : 0.0;
                var scale = Find(Scales(db), names[i], p, d);
                if (scale == null && createMissing && p > 0 && d > 0 && missing != null)
                {
                    missing.Add((names[i].Trim(), p, d));
                    continue;
                }
                if (scale == null)
                    throw new RunRefusal("This drawing has no annotation scale '" + names[i] + "'. autocad_list_annotation_scales lists the drawing's scales; "
                        + "add_missing_to_drawing=true adds a 1:N scale to the list.");
                found.Add(scale);
            }
            return found;
        }

        private static string State(DBObject obj)
        {
            switch (obj.Annotative)
            {
                case AnnotativeStates.True: return "yes";
                case AnnotativeStates.False: return "no";
                default: return "cannot";
            }
        }

        private static List<string> Held(DBObject obj, List<AnnotationScale> scales)
        {
            var held = new List<string>();
            if (obj.Annotative != AnnotativeStates.True) return held;
            foreach (var scale in scales)
                if (obj.HasContext(scale)) held.Add(scale.Name);
            return held;
        }

        /// <summary>The text height the object shows now, at the current annotation scale; NaN when it has none.</summary>
        private static double Height(DBObject obj)
        {
            if (obj is DBText text) return text.Height;
            if (obj is MText mtext) return mtext.TextHeight;
            return double.NaN;
        }

        private static void WriteScale(Utf8JsonWriter w, string name, AnnotationScale scale)
        {
            w.WriteStartObject(name);
            w.WriteString("name", scale.Name);
            w.WriteNumber("paper", scale.PaperUnits);
            w.WriteNumber("drawing", scale.DrawingUnits);
            w.WriteEndObject();
        }

        private static void WriteObject(Utf8JsonWriter w, string handle, string kind, string state, List<string> held, double height,
            string? wasState, List<string>? wasHeld)
        {
            w.WriteStartObject();
            w.WriteString("handle", handle);
            w.WriteString("type", kind.StartsWith("a ", StringComparison.Ordinal) ? kind.Substring(2) : kind);
            w.WriteString("annotative", state);
            w.WriteStartArray("scales");
            foreach (var name in held) w.WriteStringValue(name);
            w.WriteEndArray();
            if (!double.IsNaN(height)) w.WriteNumber("height", Math.Round(height, 9));
            if (wasState != null)
            {
                w.WriteString("annotative_was", wasState);
                w.WriteStartArray("scales_were");
                foreach (var name in wasHeld ?? new List<string>()) w.WriteStringValue(name);
                w.WriteEndArray();
            }
            w.WriteEndObject();
        }
    }
}
