using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
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

        /// <summary>entity_extents: the box round every selected object that has extents.</summary>
        public static RunResult Extents(Document doc, Transaction tr, RunArgs args)
        {
            var tally = new EntityTally();
            foreach (var id in Select(doc, args))
            {
                double[]? min = null, max = null;
                if (tr.GetObject(id, OpenMode.ForRead, false) is Entity entity)
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
            return RunResult.Done(tally.WriteBox);
        }

        /// <summary>Everything in the drawing the filter matches, as ssget "X" (COM's acSelectionSetAll) takes it.</summary>
        internal static ObjectId[] Select(Document doc, RunArgs args)
        {
            var pairs = EntityFilter.Parse(args.Element("filter"));
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
