using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// write_attributes (autocad_set_attributes, autocad_apply_attribute_sheet,
    /// #200, D-148). Main thread only, inside PluginRunner's transaction: every
    /// planned cell is written or none is, as one undo step with the job's mark.
    /// </summary>
    internal static class AttributeWrites
    {
        public static RunResult Write(Document doc, Transaction tr, RunArgs args)
        {
            var plan = AttributeWritePlan.Parse(args.Element("changes"));
            var db = doc.Database;
            var attributes = 0;
            foreach (var change in plan.Changes)
            {
                if (!LayerMerging.TryId(db, change.Handle, out var id) || !(tr.GetObject(id, OpenMode.ForRead, false) is BlockReference reference))
                    throw new RunRefusal(AttributeWritePlan.Gone(change.Handle));
                var hit = false;
                foreach (ObjectId attributeId in reference.AttributeCollection)
                {
                    if (attributeId.IsErased) continue;
                    if (!(tr.GetObject(attributeId, OpenMode.ForRead, false) is AttributeReference attribute)) continue;
                    if (!AttributeWritePlan.SameTag(attribute.Tag, change.Tag)) continue;
                    // Not trusted yet: the server writes these over COM, as before (D-148).
                    if (attribute.IsMTextAttribute) throw new RunRefusal(AttributeWritePlan.NotSure(change.Handle, change.Tag, "a multiline attribute"));
                    if (attribute.IsConstant) throw new RunRefusal(AttributeWritePlan.NotSure(change.Handle, change.Tag, "a constant attribute"));
                    if (attribute.HasFields) throw new RunRefusal(AttributeWritePlan.NotSure(change.Handle, change.Tag, "a field"));
                    try
                    {
                        attribute.UpgradeOpen();
                        attribute.TextString = change.Text;
                        // As COM's TextString does: text that is not left-aligned is put back on its alignment point.
                        if (!attribute.IsDefaultAlignment) attribute.AdjustAlignment(db);
                    }
                    catch (AcException ex)
                    {
                        throw new RunRefusal(AttributeWritePlan.WouldNotTake(change.Handle, change.Tag, ex.ErrorStatus.ToString()));
                    }
                    hit = true;
                    attributes++;
                }
                if (!hit) throw new RunRefusal(AttributeWritePlan.NoTag(change.Handle, change.Tag));
            }
            return RunResult.Done(w => plan.Write(w, attributes));
        }
    }
}
