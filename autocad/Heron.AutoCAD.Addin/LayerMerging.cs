using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// autocad_merge_layers in the plug-in (#199, D-147). Main thread only,
    /// inside PluginRunner's transaction: layer_objects is a read (aborted),
    /// merge_layers a change that all lands or none of it does.
    /// </summary>
    internal static class LayerMerging
    {
        /// <summary>
        /// layer_objects: the objects on the old layers, as the server's COM read
        /// finds them, in its order: each old layer's selection (the server sends
        /// the filters it selects with), then every item of every block definition
        /// but layouts and xrefs, then every attribute of every block reference.
        /// </summary>
        public static RunResult Objects(Document doc, Transaction tr, RunArgs args)
        {
            var list = new LayerObjectList(args.Texts("layers"));
            foreach (var filter in LayerObjectList.ParseFilters(args.Element("filters")))
                foreach (var id in EntityReads.Select(doc, filter))
                    if (tr.GetObject(id, OpenMode.ForRead, false) is Entity entity)
                        list.Add(entity.Handle.ToString(), entity.Layer, LayerObjectList.Drawing);
            var table = (BlockTable)tr.GetObject(doc.Database.BlockTableId, OpenMode.ForRead);
            foreach (ObjectId definitionId in table)
            {
                var definition = (BlockTableRecord)tr.GetObject(definitionId, OpenMode.ForRead);
                if (definition.IsLayout || definition.IsFromExternalReference) continue;
                foreach (ObjectId id in definition)
                    if (tr.GetObject(id, OpenMode.ForRead, false) is Entity entity && list.OnOldLayer(entity.Layer))
                        list.Add(entity.Handle.ToString(), entity.Layer, LayerObjectList.Blocks);
            }
            foreach (var id in EntityReads.Select(doc, EntityFilter.Parse(args.Element("inserts"))))
            {
                if (!(tr.GetObject(id, OpenMode.ForRead, false) is BlockReference reference)) continue;
                var found = false;
                foreach (ObjectId attributeId in reference.AttributeCollection)
                {
                    if (attributeId.IsErased) continue;
                    if (tr.GetObject(attributeId, OpenMode.ForRead, false) is AttributeReference attribute && list.OnOldLayer(attribute.Layer))
                    {
                        list.Add(attribute.Handle.ToString(), attribute.Layer, LayerObjectList.Attributes);
                        found = true;
                    }
                }
                if (found && !Defines(tr, reference.BlockTableRecord)) list.MarkUnsure();
            }
            return RunResult.Done(list.Write);
        }

        /// <summary>
        /// merge_layers: the old layers' objects the server planned, moved to the
        /// new layer, then each old layer removed when nothing uses it any more.
        /// An old current layer gives way to the new one first; a locked old layer
        /// is unlocked for the move and locked again if it is kept. One object
        /// that will not move refuses the whole merge, and the transaction is aborted.
        /// </summary>
        public static RunResult Merge(Document doc, Transaction tr, RunArgs args)
        {
            var plan = LayerMergePlan.Parse(args);
            var db = doc.Database;
            var layers = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
            if (!layers.Has(plan.Into)) throw new RunRefusal(LayerMergePlan.NoLayer(plan.Into));
            var intoId = layers[plan.Into];
            var old = new ObjectId[plan.Layers.Count];
            for (var i = 0; i < old.Length; i++)
            {
                if (!layers.Has(plan.Layers[i])) throw new RunRefusal(LayerMergePlan.NoLayer(plan.Layers[i]));
                old[i] = layers[plan.Layers[i]];
            }
            var current = (LayerTableRecord)tr.GetObject(db.Clayer, OpenMode.ForRead);
            if (plan.IsOld(current.Name))
            {
                plan.MadeCurrent(current.Name);
                db.Clayer = intoId;
            }
            var relock = new bool[old.Length];
            for (var i = 0; i < old.Length; i++)
            {
                var record = (LayerTableRecord)tr.GetObject(old[i], OpenMode.ForRead);
                if (!record.IsLocked) continue;
                record.UpgradeOpen();
                record.IsLocked = false;
                relock[i] = true;
            }
            foreach (var handle in plan.Handles)
            {
                if (!TryId(db, handle, out var id)) throw new RunRefusal(LayerMergePlan.Gone(handle));
                try
                {
                    if (!(tr.GetObject(id, OpenMode.ForWrite, false) is Entity entity))
                        throw new RunRefusal(plan.WouldNotMove(handle, "it is not a drawing object"));
                    entity.LayerId = intoId;
                }
                catch (AcException ex)
                {
                    throw new RunRefusal(plan.WouldNotMove(handle, ex.ErrorStatus.ToString()));
                }
            }
            for (var i = 0; i < old.Length; i++)
            {
                var ids = new ObjectIdCollection { old[i] };
                db.Purge(ids); // what is still used somewhere is taken out of the collection
                var record = (LayerTableRecord)tr.GetObject(old[i], OpenMode.ForWrite);
                if (ids.Count == 1)
                {
                    record.Erase();
                    plan.Removed(plan.Layers[i]);
                }
                else
                {
                    plan.Kept(plan.Layers[i], "it is still referenced");
                    if (relock[i]) record.IsLocked = true;
                }
            }
            return RunResult.Done(plan.Write);
        }

        /// <summary>The object a handle names, when it is in the drawing and not erased.</summary>
        internal static bool TryId(Database db, string handle, out ObjectId id)
        {
            id = ObjectId.Null;
            long value;
            try
            {
                value = Convert.ToInt64(handle, 16);
            }
            catch (System.Exception ex) when (ex is FormatException || ex is OverflowException || ex is ArgumentException)
            {
                return false;
            }
            return db.TryGetObjectId(new Handle(value), out id) && !id.IsNull && !id.IsErased;
        }

        private static bool Defines(Transaction tr, ObjectId definitionId)
        {
            try
            {
                return !definitionId.IsNull && ((BlockTableRecord)tr.GetObject(definitionId, OpenMode.ForRead, false)).HasAttributeDefinitions;
            }
            catch (AcException)
            {
                return false;
            }
        }
    }
}
