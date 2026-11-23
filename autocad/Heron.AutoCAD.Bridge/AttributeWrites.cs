using System;
using System.Collections.Generic;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// write_attributes (#200, D-147): the attribute cells autocad_set_attributes
    /// and autocad_apply_attribute_sheet planned to change, written in one
    /// transaction, all of them or none. The server plans which cells change
    /// (only the ones the modeller changed, D-69); the plug-in writes exactly
    /// those: each [handle, tag, text] sets every attribute with that tag on
    /// that block reference, as the server's COM loop does. A block that is
    /// gone, a tag it no longer has, or an attribute AutoCAD will not take
    /// refuses the whole write. An attribute the plug-in's write is not
    /// trusted for yet (multiline, constant, holding a field) refuses it with
    /// <see cref="UseCom"/>, and the server writes the cells over COM instead.
    /// </summary>
    public sealed class AttributeWritePlan
    {
        public const int MostChanges = 100000;

        /// <summary>The words the server reads as "nothing was written: write these over COM".</summary>
        public const string UseCom = "Heron writes these over COM instead.";

        public AttributeWritePlan(IReadOnlyList<AttributeChange> changes)
        {
            if (changes == null || changes.Count == 0) throw new RunRefusal("Writing attributes needs 'changes': [handle, tag, text] each.");
            if (changes.Count > MostChanges) throw new RunRefusal("More than " + MostChanges + " cells to write in one go. " + UseCom);
            Changes = changes;
        }

        public IReadOnlyList<AttributeChange> Changes { get; }

        /// <summary>The changes from the server: [[handle, tag, text]...], each three pieces of text.</summary>
        public static AttributeWritePlan Parse(JsonElement changes)
        {
            var list = new List<AttributeChange>();
            if (changes.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in changes.EnumerateArray())
                {
                    if (item.ValueKind != JsonValueKind.Array || item.GetArrayLength() != 3
                        || item[0].ValueKind != JsonValueKind.String || item[1].ValueKind != JsonValueKind.String
                        || item[2].ValueKind != JsonValueKind.String)
                        throw new RunRefusal("Writing attributes needs each change as [handle, tag, text].");
                    var handle = item[0].GetString() ?? "";
                    var tag = item[1].GetString() ?? "";
                    if (handle.Trim().Length == 0 || tag.Length == 0)
                        throw new RunRefusal("Writing attributes needs each change as [handle, tag, text].");
                    list.Add(new AttributeChange(handle, tag, item[2].GetString() ?? ""));
                }
            }
            return new AttributeWritePlan(list);
        }

        /// <summary>The tag as the server's COM loop matches it: exactly, the case counting.</summary>
        public static bool SameTag(string? found, string wanted) => string.Equals(found, wanted, StringComparison.Ordinal);

        public static string Gone(string handle) =>
            "Block " + handle + " is not in the drawing any more, so nothing was written. Look at the drawing and ask again.";

        public static string NoTag(string handle, string tag) =>
            "Block " + handle + " no longer has the tag " + tag + ", so nothing was written. Look at the drawing and ask again.";

        public static string WouldNotTake(string handle, string tag, string why) =>
            "Block " + handle + " would not take " + tag + " (" + why + "), so nothing was written: no attribute changed.";

        public static string NotSure(string handle, string tag, string kind) =>
            tag + " on block " + handle + " is " + kind + ". " + UseCom;

        /// <summary>{"written": cells, "attributes": attributes set}; one cell sets two attributes when the tag is there twice.</summary>
        public void Write(Utf8JsonWriter w, int attributes)
        {
            w.WriteNumber("written", Changes.Count);
            w.WriteNumber("attributes", attributes);
        }
    }

    /// <summary>One planned cell: the block reference's handle, the attribute's tag, the new text.</summary>
    public sealed class AttributeChange
    {
        public AttributeChange(string handle, string tag, string text)
        {
            Handle = handle ?? "";
            Tag = tag ?? "";
            Text = text ?? "";
        }

        public string Handle { get; }
        public string Tag { get; }
        public string Text { get; }
    }
}
