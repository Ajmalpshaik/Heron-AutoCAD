using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Block reads over a whole drawing that COM does one round trip per
    /// object, done in one go (D-114, D-127). Main thread only, inside
    /// PluginRunner's transaction, which a read aborts.
    ///
    /// What is read off each object is what the server reads over COM: the
    /// real name (COM's EffectiveName), the layer, each dynamic property's
    /// name, read-only flag and value, a definition's entity count, xref
    /// path and attribute tags. The server builds its answer from these with
    /// the code it uses for COM, so the answer is the same either way.
    /// </summary>
    internal static class BlockReads
    {
        // COM's ObjectName of a plain block reference; a MINSERT is AcDbMInsertBlock.
        private const string BlockReferenceClass = "AcDbBlockReference";
        private const string AttributeDefinitionClass = "AcDbAttributeDefinition";

        /// <summary>
        /// block_references (autocad_count_blocks, #192): each selected block
        /// reference, and with "nested" the block references inside every block
        /// definition that is not a layout or an xref.
        /// </summary>
        public static RunResult References(Document doc, Transaction tr, RunArgs args)
        {
            var list = new BlockReferenceList();
            var names = new Dictionary<ObjectId, string>();
            foreach (var id in EntityReads.Select(doc, args))
            {
                if (!(tr.GetObject(id, OpenMode.ForRead, false) is BlockReference reference)) continue;
                list.Add(RealName(tr, reference, names), reference.Layer, Properties(reference));
            }
            var nested = args.Flag("nested", false);
            if (nested)
            {
                var table = (BlockTable)tr.GetObject(doc.Database.BlockTableId, OpenMode.ForRead);
                foreach (ObjectId definitionId in table)
                {
                    var definition = (BlockTableRecord)tr.GetObject(definitionId, OpenMode.ForRead);
                    if (definition.IsLayout || definition.IsFromExternalReference) continue;
                    foreach (ObjectId itemId in definition)
                    {
                        // The class is read off the id: only block references are opened.
                        if (itemId.ObjectClass.Name != BlockReferenceClass) continue;
                        var inner = (BlockReference)tr.GetObject(itemId, OpenMode.ForRead, false);
                        list.AddChild(definition.Name, RealName(tr, inner, names), inner.Layer);
                    }
                }
            }
            return RunResult.Done(w => list.Write(w, nested));
        }

        /// <summary>
        /// block_definitions (autocad_list_blocks, #194): the facts of every
        /// named block definition, and with "counts" how many selected block
        /// references each real name has.
        /// </summary>
        public static RunResult Definitions(Document doc, Transaction tr, RunArgs args)
        {
            var list = new BlockDefinitionList();
            var table = (BlockTable)tr.GetObject(doc.Database.BlockTableId, OpenMode.ForRead);
            foreach (ObjectId definitionId in table)
            {
                var definition = (BlockTableRecord)tr.GetObject(definitionId, OpenMode.ForRead);
                if (definition.IsLayout || !BlockDefinitionList.Listed(definition.Name)) continue;
                var count = 0;
                var tags = new List<string>();
                foreach (ObjectId itemId in definition)
                {
                    count++;
                    if (itemId.ObjectClass.Name != AttributeDefinitionClass) continue;
                    if (tr.GetObject(itemId, OpenMode.ForRead, false) is AttributeDefinition attribute) tags.Add(attribute.Tag);
                }
                var xref = definition.IsFromExternalReference;
                list.Add(definition.Name, count, xref, xref ? definition.PathName : null, definition.IsDynamicBlock, tags);
            }
            var counts = args.Flag("counts", false);
            if (counts)
            {
                var names = new Dictionary<ObjectId, string>();
                foreach (var id in EntityReads.Select(doc, args))
                    if (tr.GetObject(id, OpenMode.ForRead, false) is BlockReference reference)
                        list.Instance(RealName(tr, reference, names));
            }
            return RunResult.Done(w => list.Write(w, counts));
        }

        /// <summary>
        /// block_attributes (autocad_extract_attributes, autocad_export_attribute_sheet,
        /// and the reads of autocad_set_attributes and autocad_apply_attribute_sheet,
        /// #198, D-138): each selected block reference as the server's COM loop reads
        /// it, every one sent; the server skips, names and matches them itself.
        /// </summary>
        public static RunResult Attributes(Document doc, Transaction tr, RunArgs args)
        {
            var list = new BlockAttributeList();
            var names = new Dictionary<ObjectId, string>();
            var layouts = new Dictionary<ObjectId, string?>();
            var defines = new Dictionary<ObjectId, bool>();
            foreach (var id in EntityReads.Select(doc, args))
            {
                if (!(tr.GetObject(id, OpenMode.ForRead, false) is BlockReference reference)) continue;
                string? effective;
                try
                {
                    effective = RealName(tr, reference, names);
                }
                catch (AcException)
                {
                    effective = null; // the server reads the drawing over COM
                }
                var read = EntityReads.TryAttributes(tr, reference, out var attributes);
                var position = reference.Position;
                list.Add(new BlockAttributeFact(
                    reference.Handle.ToString(), reference.Name, effective, reference.Layer,
                    new[] { position.X, position.Y, position.Z }, LayoutOf(tr, reference.OwnerId, layouts),
                    Defines(tr, reference.BlockTableRecord, defines), read ? attributes : null));
            }
            return RunResult.Done(list.Write);
        }

        /// <summary>COM's owner.Layout.Name when the owner is a layout's block; null otherwise, or when it cannot be read.</summary>
        private static string? LayoutOf(Transaction tr, ObjectId ownerId, Dictionary<ObjectId, string?> layouts)
        {
            if (layouts.TryGetValue(ownerId, out var known)) return known;
            string? name = null;
            try
            {
                if (tr.GetObject(ownerId, OpenMode.ForRead, false) is BlockTableRecord owner && owner.IsLayout && !owner.LayoutId.IsNull)
                    name = ((Layout)tr.GetObject(owner.LayoutId, OpenMode.ForRead, false)).LayoutName;
            }
            catch (AcException)
            {
                name = null;
            }
            layouts[ownerId] = name;
            return name;
        }

        /// <summary>Whether the block definition a reference points at holds attribute definitions (constant ones too).</summary>
        private static bool Defines(Transaction tr, ObjectId definitionId, Dictionary<ObjectId, bool> defines)
        {
            if (defines.TryGetValue(definitionId, out var known)) return known;
            var found = false;
            try
            {
                if (!definitionId.IsNull)
                    found = ((BlockTableRecord)tr.GetObject(definitionId, OpenMode.ForRead, false)).HasAttributeDefinitions;
            }
            catch (AcException)
            {
                found = false;
            }
            defines[definitionId] = found;
            return found;
        }

        /// <summary>
        /// COM's EffectiveName: the dynamic block's own name for a *U copy, the
        /// block's name otherwise; the reference's name when that is empty, as
        /// the server's "EffectiveName or Name" takes it.
        /// </summary>
        private static string RealName(Transaction tr, BlockReference reference, Dictionary<ObjectId, string> names)
        {
            var id = reference.IsDynamicBlock ? reference.DynamicBlockTableRecord : reference.BlockTableRecord;
            if (id.IsNull) return reference.Name;
            if (!names.TryGetValue(id, out var name))
            {
                name = ((BlockTableRecord)tr.GetObject(id, OpenMode.ForRead, false)).Name;
                names[id] = name;
            }
            return string.IsNullOrEmpty(name) ? reference.Name : name;
        }

        /// <summary>A dynamic block's properties in AutoCAD's order; none for a plain block.</summary>
        private static List<DynamicProperty> Properties(BlockReference reference)
        {
            var found = new List<DynamicProperty>();
            if (!reference.IsDynamicBlock) return found;
            foreach (DynamicBlockReferenceProperty property in reference.DynamicBlockReferencePropertyCollection)
            {
                object? value;
                try
                {
                    value = Plain(property.Value);
                }
                catch (AcException)
                {
                    // Over COM this reference would be skipped if the server needs the value: it decides.
                    found.Add(new DynamicProperty(property.PropertyName, property.ReadOnly, null, failed: true));
                    continue;
                }
                found.Add(new DynamicProperty(property.PropertyName, property.ReadOnly, value));
            }
            return found;
        }

        /// <summary>A point as the numbers COM gives for it; any other value as it is.</summary>
        private static object? Plain(object? value)
        {
            switch (value)
            {
                case Point3d p: return new[] { p.X, p.Y, p.Z };
                case Point2d p: return new[] { p.X, p.Y };
                default: return value;
            }
        }
    }
}
