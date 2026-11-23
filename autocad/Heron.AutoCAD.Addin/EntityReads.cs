using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Reads over a whole drawing that COM can do, but only one round trip per
    /// object: the plug-in does them in one go (D-114). Main thread only,
    /// inside PluginRunner's transaction, which a read aborts.
    ///
    /// The objects are selected the way the server's COM selection set selects
    /// them (all of the drawing, the same DXF filter), and what is read off each
    /// is what COM reads: the class name (COM's ObjectName), the layer, the
    /// extents (COM's GetBoundingBox). The server builds its answer from these
    /// with the same code it uses for COM, so the answer is the same either way.
    /// </summary>
    internal static class EntityReads
    {
        /// <summary>
        /// count_entities: how many objects of each class and on each layer.
        /// With space "model", model space only, walked in its own order (the
        /// order COM's ModelSpace.Item uses), and with limit, only the first
        /// that many counted by class: autocad_drawing_report's count (#193).
        /// The answer then says "space": "model", so the server knows this
        /// plug-in honoured it.
        /// </summary>
        public static RunResult Count(Document doc, Transaction tr, RunArgs args)
        {
            var tally = new EntityTally();
            var model = args.Text("space").Trim().ToLowerInvariant() == "model";
            if (model)
            {
                var limit = (long)args.Number("limit", 0);
                var space = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(doc.Database), OpenMode.ForRead);
                foreach (ObjectId id in space)
                {
                    if (limit > 0 && tally.Total >= limit)
                    {
                        tally.Skip();
                        continue;
                    }
                    var found = tr.GetObject(id, OpenMode.ForRead, false);
                    tally.Count(found.GetRXClass().Name, found is Entity entity ? entity.Layer : "<unknown>");
                }
            }
            else
            {
                foreach (var id in Select(doc, args))
                {
                    var found = tr.GetObject(id, OpenMode.ForRead, false);
                    tally.Count(found.GetRXClass().Name, found is Entity entity ? entity.Layer : "<unknown>");
                }
            }
            return RunResult.Done(w =>
            {
                if (model) w.WriteString("space", "model");
                tally.WriteCounts(w);
            });
        }

        /// <summary>
        /// entity_extents: the box round every selected object that has extents.
        /// With "leave_out_layout_viewports", each sheet's own overall viewport
        /// (the paper-space view the modeller zooms, whose box is the screen, not
        /// the sheet) is counted but not measured, and the answer says
        /// "layout_viewports": "left out" so the server knows this plug-in did it
        /// (#281, D-154). The floating viewports are measured: they are on the sheet.
        /// </summary>
        public static RunResult Extents(Document doc, Transaction tr, RunArgs args)
        {
            var tally = new EntityTally();
            var leaveOut = args.Flag("leave_out_layout_viewports", false);
            var overall = leaveOut ? OverallViewports(doc, tr) : null;
            foreach (var id in Select(doc, args))
            {
                double[]? min = null, max = null;
                var found = tr.GetObject(id, OpenMode.ForRead, false);
                if (overall != null && found is Viewport viewport && (overall.Contains(id) || viewport.Number == 1))
                {
                    tally.Skip();
                    continue;
                }
                if (found is Entity entity)
                {
                    try
                    {
                        var box = entity.GeometricExtents;
                        min = new[] { box.MinPoint.X, box.MinPoint.Y, box.MinPoint.Z };
                        max = new[] { box.MaxPoint.X, box.MaxPoint.Y, box.MaxPoint.Z };
                    }
                    catch (AcException)
                    {
                        // A ray or a construction line has no extents; COM skips it too.
                    }
                }
                tally.Measure(min, max);
            }
            return RunResult.Done(w =>
            {
                if (leaveOut) w.WriteString("layout_viewports", "left out");
                tally.WriteBox(w);
            });
        }

        /// <summary>
        /// Each sheet's own overall viewport: the first of its layout's viewports
        /// (AutoCAD keeps it first). A sheet never opened has none yet.
        /// </summary>
        private static HashSet<ObjectId> OverallViewports(Document doc, Transaction tr)
        {
            var ids = new HashSet<ObjectId>();
            var layouts = (DBDictionary)tr.GetObject(doc.Database.LayoutDictionaryId, OpenMode.ForRead);
            foreach (DBDictionaryEntry entry in layouts)
            {
                if (!(tr.GetObject(entry.Value, OpenMode.ForRead, false) is Layout layout) || layout.ModelType) continue;
                var viewports = layout.GetViewports();
                if (viewports != null && viewports.Count > 0) ids.Add(viewports[0]);
            }
            return ids;
        }

        /// <summary>
        /// entity_lengths (autocad_total_length, autocad_measure(layer=...), #195):
        /// each selected object's class, layer, length, area and closed flag, and
        /// a spline's or an ellipse's definition, read off the .NET object as COM
        /// reads the same property. The server keeps only what COM gives for
        /// that class (D-134). With "classes", only those classes are read.
        /// </summary>
        public static RunResult Lengths(Document doc, Transaction tr, RunArgs args)
        {
            var list = new CurveFactList(args.Texts("classes"));
            foreach (var id in Select(doc, args))
            {
                // The class is read off the id: an object not asked for is never opened.
                if (!list.Wanted(id.ObjectClass.Name)) continue;
                if (!(tr.GetObject(id, OpenMode.ForRead, false) is Entity entity)) continue;
                list.Add(CurveFacts(entity));
            }
            return RunResult.Done(list.Write);
        }

        /// <summary>
        /// entity_texts (autocad_count_text, autocad_find_text, #197): for each
        /// filter in "filters", the texts, mtexts and block references it
        /// selects, each with what COM reads off it: TextString (an mtext's
        /// contents, formatting codes left in), InsertionPoint, the block's Name
        /// and its attributes' TagString and TextString.
        /// </summary>
        public static RunResult TextContents(Document doc, Transaction tr, RunArgs args)
        {
            var list = new TextFactList();
            foreach (var filter in TextFactList.ParseFilters(args.Element("filters")))
            {
                list.Group();
                foreach (var id in Select(doc, filter))
                {
                    switch (tr.GetObject(id, OpenMode.ForRead, false))
                    {
                        case MText mtext:
                            list.Add(mtext.Handle.ToString(), mtext.Layer, mtext.Contents, Point(mtext.Location), null, null);
                            break;
                        case DBText text:
                            list.Add(text.Handle.ToString(), text.Layer, text.TextString, Point(text.Position), null, null);
                            break;
                        case BlockReference reference:
                            list.Add(reference.Handle.ToString(), reference.Layer, null, Point(reference.Position), reference.Name, Attributes(tr, reference));
                            break;
                        case Entity other:
                            // Not text: the server reads the drawing over COM if it would read this one.
                            list.Add(other.Handle.ToString(), other.Layer, null, null, null, null);
                            break;
                    }
                }
            }
            return RunResult.Done(list.Write);
        }

        /// <summary>
        /// entity_properties (autocad_check_standards' entity rules, #196, D-143):
        /// the first "limit" selected objects, each with what the server's COM
        /// loop reads off it: Handle, ObjectName, Layer, Color, Linetype, and for
        /// a class whose name holds "box_classes", the box GetBoundingBox gives.
        /// The rules stay in the server; "total" says how many were selected.
        /// </summary>
        public static RunResult Properties(Document doc, Transaction tr, RunArgs args)
        {
            var list = new PropertyFactList((long)args.Number("limit", 0), args.Text("box_classes"));
            foreach (var id in Select(doc, args))
            {
                if (!list.Take()) continue; // past the limit: counted, never opened
                if (!(tr.GetObject(id, OpenMode.ForRead, false) is Entity entity))
                    return RunResult.Failed("Heron could not read an object it selected. Nothing was changed.");
                var objectClass = entity.GetRXClass().Name;
                double[]? box = null;
                if (list.WantsBox(objectClass))
                {
                    try
                    {
                        var extents = entity.GeometricExtents;
                        box = new[] { extents.MinPoint.X, extents.MinPoint.Y, extents.MaxPoint.X, extents.MaxPoint.Y };
                    }
                    catch (AcException)
                    {
                        box = null; // no box: COM's GetBoundingBox fails too, and the loop leaves it out
                    }
                }
                list.Add(new PropertyFact(entity.Handle.ToString(), objectClass, entity.Layer,
                    PropertyFact.ComColor((int)entity.Color.ColorMethod, entity.ColorIndex), entity.Linetype, box));
            }
            return RunResult.Done(list.Write);
        }

        /// <summary>What COM's Length (ArcLength, Circumference), Area and Closed would read, and a spline's or an ellipse's definition.</summary>
        private static CurveFact CurveFacts(Entity entity)
        {
            double? length = null;
            double? area = null;
            bool? closed = null;
            try
            {
                switch (entity)
                {
                    case Line line: length = line.Length; break;
                    case Polyline polyline: closed = polyline.Closed; length = polyline.Length; break;
                    case Polyline2d polyline: closed = polyline.Closed; length = polyline.Length; break;
                    case Polyline3d polyline: closed = polyline.Closed; length = polyline.Length; break;
                    case Arc arc: length = arc.Length; break;
                    case Circle circle: length = circle.Circumference; break;
                    case Curve curve: closed = curve.Closed; break;
                }
            }
            catch (AcException)
            {
                length = null; // COM's read of the same property fails too: the server counts it unmeasured
            }
            try
            {
                switch (entity)
                {
                    case Curve curve: area = curve.Area; break;
                    case Hatch hatch: area = hatch.Area; break;
                    case Region region: area = region.Area; break;
                }
            }
            catch (AcException)
            {
                area = null;
            }
            var fact = new CurveFact(entity.GetRXClass().Name, entity.Layer, length, area, closed);
            try
            {
                switch (entity)
                {
                    case Helix _:
                        break; // a Helix is a Spline in .NET; COM gives it no spline definition
                    case Spline spline:
                        var nurbs = spline.NurbsData;
                        var points = new List<double>();
                        foreach (Point3d p in nurbs.GetControlPoints())
                        {
                            points.Add(p.X);
                            points.Add(p.Y);
                            points.Add(p.Z);
                        }
                        var knots = new List<double>();
                        foreach (double knot in nurbs.GetKnots()) knots.Add(knot);
                        var weights = new List<double>();
                        if (nurbs.Rational)
                            foreach (double weight in nurbs.GetWeights()) weights.Add(weight);
                        fact.Spline(nurbs.Degree, nurbs.Rational, points, knots, weights);
                        break;
                    case Ellipse ellipse:
                        fact.Ellipse(ellipse.MajorRadius, ellipse.MinorRadius, ellipse.StartParam, ellipse.EndParam);
                        break;
                }
            }
            catch (AcException)
            {
                // No definition: the server counts it unmeasured, as a failed COM read does.
            }
            return fact;
        }

        /// <summary>The attributes on a block reference in its own order (COM's GetAttributes); erased ones left out.</summary>
        private static List<TextAttribute> Attributes(Transaction tr, BlockReference reference)
        {
            // As over COM: the attributes read so far stay, the rest of this block is not read.
            TryAttributes(tr, reference, out var found);
            return found;
        }

        /// <summary>
        /// The attributes on a block reference in its own order, each with its
        /// invisible, constant and multiline flags; erased ones left out. False
        /// when AutoCAD would not give one: found then holds those read before it.
        /// </summary>
        internal static bool TryAttributes(Transaction tr, BlockReference reference, out List<TextAttribute> found)
        {
            found = new List<TextAttribute>();
            try
            {
                foreach (ObjectId id in reference.AttributeCollection)
                {
                    if (id.IsErased) continue;
                    if (tr.GetObject(id, OpenMode.ForRead, false) is AttributeReference attribute)
                        found.Add(new TextAttribute(attribute.Tag, attribute.TextString, attribute.IsMTextAttribute, attribute.IsConstant, attribute.Invisible));
                }
                return true;
            }
            catch (AcException)
            {
                return false;
            }
        }

        private static double[] Point(Point3d point) => new[] { point.X, point.Y, point.Z };

        /// <summary>Everything in the drawing the filter matches, as ssget "X" (COM's acSelectionSetAll) takes it.</summary>
        internal static ObjectId[] Select(Document doc, RunArgs args) => Select(doc, EntityFilter.Parse(args.Element("filter")));

        internal static ObjectId[] Select(Document doc, IReadOnlyList<FilterPair> pairs)
        {
            var values = new List<TypedValue>();
            foreach (var pair in pairs)
                values.Add(pair.Number.HasValue ? new TypedValue(pair.Code, (short)pair.Number.Value) : new TypedValue(pair.Code, pair.Text));
            var result = values.Count == 0 ? doc.Editor.SelectAll() : doc.Editor.SelectAll(new SelectionFilter(values.ToArray()));
            // Nothing matching is not an error to the chat: it is a count of none.
            if (result.Status != PromptStatus.OK || result.Value == null) return new ObjectId[0];
            return result.Value.GetObjectIds();
        }
    }
}
