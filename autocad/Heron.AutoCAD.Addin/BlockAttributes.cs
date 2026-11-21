using System;
using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// ATTSYNC (D-82): after a block's definition changed, give each chosen
    /// insert the attributes the definition has now. COM can read and set an
    /// insert's attributes but cannot add one, so this is the plug-in's job.
    ///
    /// The rule matches the server's plan (acad/block_attributes.py):
    /// a value already typed is kept, matched by tag in order; a tag the
    /// definition gained comes in with its default; a tag it lost, or made
    /// constant, goes. A kept attribute goes back to the definition's place,
    /// height and style, unless it holds a field or is multi-line: those are
    /// left exactly as they were, so nothing typed is lost.
    /// </summary>
    internal static class BlockAttributes
    {
        public static RunResult Sync(Database db, Transaction tr, RunArgs args)
        {
            var name = args.Text("block").Trim();
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            if (name.Length == 0 || !blocks.Has(name))
                throw new RunRefusal("There is no block called '" + name + "' in this drawing. autocad_list_blocks lists them.");
            var blockId = blocks[name];
            var block = (BlockTableRecord)tr.GetObject(blockId, OpenMode.ForRead);
            if (block.IsLayout || block.IsFromExternalReference || block.IsAnonymous)
                throw new RunRefusal("'" + name + "' is a layout, an xref or an unnamed block, not a block whose inserts carry attributes.");

            var added = AddDefinitions(block, db, tr, args.Element("add"));
            var definitions = new List<AttributeDefinition>();
            foreach (ObjectId id in block)
                if (tr.GetObject(id, OpenMode.ForRead) is AttributeDefinition definition && !definition.IsErased)
                    definitions.Add(definition);

            var counts = new Counts();
            foreach (var handle in args.Texts("handles"))
            {
                var reference = RunDrawing.Open<BlockReference>(tr, db, handle, OpenMode.ForWrite, "a block insert");
                var real = reference.IsDynamicBlock ? reference.DynamicBlockTableRecord : reference.BlockTableRecord;
                if (real != blockId) throw new RunRefusal(handle + " is not an insert of '" + name + "'.");
                SyncOne(reference, definitions, db, tr, counts);
                counts.Touched++;
            }

            return RunResult.Done(w =>
            {
                w.WriteString("block", name);
                w.WriteNumber("touched", counts.Touched);
                w.WriteNumber("values_kept", counts.Kept);
                w.WriteNumber("attributes_added", counts.Added);
                w.WriteNumber("attributes_dropped", counts.Dropped);
                w.WriteNumber("kept_as_they_were", counts.AsTheyWere);
                w.WriteStartArray("definitions_added");
                foreach (var tag in added) w.WriteStringValue(tag);
                w.WriteEndArray();
            });
        }

        private sealed class Counts
        {
            public int Touched, Kept, Added, Dropped, AsTheyWere;
        }

        private static void SyncOne(BlockReference reference, List<AttributeDefinition> definitions, Database db, Transaction tr, Counts counts)
        {
            var existing = new Dictionary<string, Queue<AttributeReference>>(StringComparer.OrdinalIgnoreCase);
            foreach (ObjectId id in reference.AttributeCollection)
            {
                if (!(tr.GetObject(id, OpenMode.ForRead) is AttributeReference attribute) || attribute.IsErased) continue;
                var tag = attribute.Tag.Trim().ToUpperInvariant();
                if (!existing.TryGetValue(tag, out var queue)) existing[tag] = queue = new Queue<AttributeReference>();
                queue.Enqueue(attribute);
            }

            var transform = reference.BlockTransform;
            foreach (var definition in definitions)
            {
                if (definition.Constant) continue; // shown by the definition, never on the insert
                var tag = definition.Tag.Trim().ToUpperInvariant();
                if (existing.TryGetValue(tag, out var queue) && queue.Count > 0)
                {
                    var attribute = queue.Dequeue();
                    counts.Kept++;
                    if (attribute.HasFields || attribute.IsMTextAttribute)
                    {
                        counts.AsTheyWere++;
                        continue;
                    }
                    var text = attribute.TextString;
                    attribute.UpgradeOpen();
                    attribute.SetAttributeFromBlock(definition, transform);
                    attribute.TextString = text;
                    Align(attribute, db);
                }
                else
                {
                    var attribute = new AttributeReference();
                    attribute.SetAttributeFromBlock(definition, transform);
                    attribute.TextString = definition.TextString;
                    reference.AttributeCollection.AppendAttribute(attribute);
                    tr.AddNewlyCreatedDBObject(attribute, true);
                    Align(attribute, db);
                    counts.Added++;
                }
            }
            foreach (var queue in existing.Values)
                while (queue.Count > 0)
                {
                    var attribute = queue.Dequeue();
                    attribute.UpgradeOpen();
                    attribute.Erase();
                    counts.Dropped++;
                }
        }

        /// <summary>Text that is not left-aligned is placed from its alignment point, which AutoCAD works out here.</summary>
        private static void Align(AttributeReference attribute, Database db)
        {
            if (attribute.Justify != AttachmentPoint.BaseLeft) attribute.AdjustAlignment(db);
        }

        /// <summary>New attribute definitions from the server's checked plan; their tags, in order.</summary>
        private static List<string> AddDefinitions(BlockTableRecord block, Database db, Transaction tr, JsonElement add)
        {
            var tags = new List<string>();
            if (add.ValueKind != JsonValueKind.Array || add.GetArrayLength() == 0) return tags;
            var have = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (ObjectId id in block)
                if (tr.GetObject(id, OpenMode.ForRead) is AttributeDefinition definition && !definition.IsErased)
                    have.Add(definition.Tag.Trim());
            block.UpgradeOpen();
            foreach (var item in add.EnumerateArray())
            {
                var tag = Text(item, "tag").Trim().ToUpperInvariant();
                if (tag.Length == 0 || tag.IndexOf(' ') >= 0) throw new RunRefusal("'" + tag + "' cannot be an attribute tag.");
                if (!have.Add(tag)) throw new RunRefusal("The block already has an attribute tagged " + tag + ".");
                var height = Number(item, "height");
                if (!(height > 0)) throw new RunRefusal("The attribute " + tag + " needs a height above zero.");
                var definition = new AttributeDefinition();
                definition.SetDatabaseDefaults(db);
                definition.Position = Point(item, "position");
                definition.Tag = tag;
                definition.Prompt = Text(item, "prompt");
                definition.TextString = Text(item, "default");
                definition.Height = height;
                definition.TextStyleId = db.Textstyle;
                definition.Invisible = Flag(item, "invisible");
                definition.Constant = Flag(item, "constant");
                definition.Preset = Flag(item, "preset");
                block.AppendEntity(definition);
                tr.AddNewlyCreatedDBObject(definition, true);
                tags.Add(tag);
            }
            return tags;
        }

        private static string Text(JsonElement item, string name) =>
            item.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";

        private static double Number(JsonElement item, string name) =>
            item.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Number ? value.GetDouble() : 0.0;

        private static bool Flag(JsonElement item, string name) =>
            item.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.True;

        private static Point3d Point(JsonElement item, string name)
        {
            var xyz = new double[3];
            if (item.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.Array)
            {
                var i = 0;
                foreach (var number in value.EnumerateArray())
                {
                    if (i > 2) break;
                    if (number.ValueKind == JsonValueKind.Number) xyz[i] = number.GetDouble();
                    i++;
                }
            }
            return new Point3d(xyz[0], xyz[1], xyz[2]);
        }
    }
}
