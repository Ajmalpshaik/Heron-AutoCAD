using System;
using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Multileader styles and table styles (D-104): COM has no call to make
    /// either. The words, defaults and refusals are worked out in the Bridge
    /// (StylePlans.cs); this file only copies a plan onto AutoCAD's objects and
    /// reads back what the style then holds. Built against the AutoCAD 2021
    /// and 2027 reference assemblies; not yet run in AutoCAD (group AN).
    /// </summary>
    internal static class DrawingStyles
    {
        private const int AllRows = (int)(RowType.TitleRow | RowType.HeaderRow | RowType.DataRow);

        public static RunResult Multileader(Database db, Transaction tr, RunArgs args)
        {
            var plan = MultileaderStylePlan.From(args);
            var styles = (DBDictionary)tr.GetObject(db.MLeaderStyleDictionaryId, OpenMode.ForRead);
            var exists = styles.Contains(plan.Name);
            if (exists && !plan.Replace) throw new RunRefusal(StylePlans.AlreadyThere("multileader style", plan.Name));
            var text = TextStyle(db, tr, plan.TextStyle, out var textName);
            // Everything is checked before the arrow block, the one thing that is
            // not undone with the transaction if a later step fails.
            var arrow = Arrow(db, tr, plan.ArrowBlock, out var arrowAdded);

            var style = exists ? (MLeaderStyle)tr.GetObject(styles.GetAt(plan.Name), OpenMode.ForWrite) : new MLeaderStyle();
            var notes = new List<string>();
            style.ContentType = ContentType.MTextContent;
            style.LeaderLineType = LeaderType.StraightLeader;
            style.TextStyleId = text;
            style.TextHeight = plan.TextHeight;
            style.ArrowSymbolId = arrow;
            style.ArrowSize = plan.ArrowSize;
            // The dialog's one "landing" switch is both of these.
            style.EnableLanding = plan.Dogleg;
            style.EnableDogleg = plan.Dogleg;
            style.DoglegLength = plan.DoglegLength;
            if (plan.LandingGap.HasValue) style.LandingGap = plan.LandingGap.Value;
            var attach = (TextAttachmentType)plan.Attachment;
            style.TextAttachmentDirection = TextAttachmentDirection.AttachmentHorizontal;
            style.TextAttachmentType = attach;
            style.SetTextAttachmentType(attach, LeaderDirectionType.LeftLeader);
            style.SetTextAttachmentType(attach, LeaderDirectionType.RightLeader);
            // An annotative style takes its scale from the annotation scale; Heron
            // reads that flag and leaves it alone.
            if (exists && style.Annotative == AnnotativeStates.True)
            {
                if (Math.Abs(plan.Scale - 1.0) > 1e-9)
                    notes.Add("'" + plan.Name + "' is annotative, so its size follows the annotation scale; 'scale' was not set.");
            }
            else
            {
                style.Scale = plan.Scale;
            }

            ObjectId id;
            if (exists)
            {
                id = style.ObjectId;
            }
            else
            {
                id = style.PostMLeaderStyleToDb(db, plan.Name);
                tr.AddNewlyCreatedDBObject(style, true);
            }
            if (plan.Current) db.MLeaderstyle = id;

            return RunResult.Done(w =>
            {
                w.WriteString("name", plan.Name);
                w.WriteBoolean("created", !exists);
                w.WriteBoolean("current", db.MLeaderstyle == id);
                w.WriteString("text_style", textName);
                w.WriteNumber("text_height", Round(style.TextHeight));
                w.WriteString("arrow", StylePlans.ArrowWord(plan.ArrowBlock));
                w.WriteNumber("arrow_size", Round(style.ArrowSize));
                w.WriteBoolean("dogleg", style.EnableDogleg);
                w.WriteNumber("dogleg_length", Round(style.DoglegLength));
                w.WriteNumber("landing_gap", Round(style.LandingGap));
                w.WriteString("attachment", StylePlans.AttachmentWord((int)style.GetTextAttachmentType(LeaderDirectionType.LeftLeader)));
                w.WriteNumber("scale", Round(style.Scale));
                if (arrowAdded) w.WriteString("arrow_block_added", plan.ArrowBlock);
                Notes(w, notes);
            });
        }

        public static RunResult Table(Database db, Transaction tr, RunArgs args)
        {
            var plan = TableStylePlan.From(args);
            var styles = (DBDictionary)tr.GetObject(db.TableStyleDictionaryId, OpenMode.ForRead);
            var exists = styles.Contains(plan.Name);
            if (exists && !plan.Replace) throw new RunRefusal(StylePlans.AlreadyThere("table style", plan.Name));
            var text = TextStyle(db, tr, plan.TextStyle, out var textName);

            var style = exists ? (TableStyle)tr.GetObject(styles.GetAt(plan.Name), OpenMode.ForWrite) : new TableStyle();
            style.SetTextStyle(text, AllRows);
            style.SetTextHeight(plan.TitleHeight, (int)RowType.TitleRow);
            style.SetTextHeight(plan.HeaderHeight, (int)RowType.HeaderRow);
            style.SetTextHeight(plan.DataHeight, (int)RowType.DataRow);
            // Ajmal's rule (D-83): text in the vertical middle of every cell.
            style.SetAlignment((CellAlignment)plan.TitleAlignment, (int)RowType.TitleRow);
            style.SetAlignment((CellAlignment)plan.HeaderAlignment, (int)RowType.HeaderRow);
            style.SetAlignment((CellAlignment)plan.DataAlignment, (int)RowType.DataRow);
            style.HorizontalCellMargin = plan.HorizontalMargin;
            style.VerticalCellMargin = plan.VerticalMargin;
            style.IsTitleSuppressed = !plan.TitleRow;
            style.IsHeaderSuppressed = !plan.HeaderRow;

            ObjectId id;
            if (exists)
            {
                id = style.ObjectId;
            }
            else
            {
                id = style.PostTableStyleToDatabase(db, plan.Name);
                tr.AddNewlyCreatedDBObject(style, true);
            }
            if (plan.Current) db.Tablestyle = id;

            return RunResult.Done(w =>
            {
                w.WriteString("name", plan.Name);
                w.WriteBoolean("created", !exists);
                w.WriteBoolean("current", db.Tablestyle == id);
                w.WriteString("text_style", textName);
                w.WriteNumber("scale", Round(plan.Scale));
                w.WriteStartObject("text_heights");
                w.WriteNumber("title", Round(style.TextHeight(RowType.TitleRow)));
                w.WriteNumber("header", Round(style.TextHeight(RowType.HeaderRow)));
                w.WriteNumber("data", Round(style.TextHeight(RowType.DataRow)));
                w.WriteEndObject();
                w.WriteStartObject("alignment");
                w.WriteString("title", StylePlans.AlignmentWord((int)style.Alignment(RowType.TitleRow)));
                w.WriteString("header", StylePlans.AlignmentWord((int)style.Alignment(RowType.HeaderRow)));
                w.WriteString("data", StylePlans.AlignmentWord((int)style.Alignment(RowType.DataRow)));
                w.WriteEndObject();
                w.WriteStartObject("margins");
                w.WriteNumber("horizontal", Round(style.HorizontalCellMargin));
                w.WriteNumber("vertical", Round(style.VerticalCellMargin));
                w.WriteEndObject();
                w.WriteBoolean("title_row", !style.IsTitleSuppressed);
                w.WriteBoolean("header_row", !style.IsHeaderSuppressed);
            });
        }

        /// <summary>The text style asked for, or the drawing's current one; a missing one is a refusal.</summary>
        private static ObjectId TextStyle(Database db, Transaction tr, string name, out string used)
        {
            ObjectId id;
            if (name.Length == 0)
            {
                id = db.Textstyle;
            }
            else
            {
                var table = (TextStyleTable)tr.GetObject(db.TextStyleTableId, OpenMode.ForRead);
                if (!table.Has(name)) throw new RunRefusal(StylePlans.NoTextStyle(name));
                id = table[name];
                if (id.IsNull || id.IsErased) throw new RunRefusal(StylePlans.NoTextStyle(name));
            }
            used = ((TextStyleTableRecord)tr.GetObject(id, OpenMode.ForRead)).Name;
            return id;
        }

        /// <summary>
        /// The arrow's block, made the way AutoCAD's own dialogs make it when the
        /// drawing has not got it yet: by naming it in DIMBLK, which is put back
        /// straight after. Closed filled has no block (a null id).
        /// </summary>
        private static ObjectId Arrow(Database db, Transaction tr, string block, out bool added)
        {
            added = false;
            if (block.Length == 0) return ObjectId.Null;
            if (!HasBlock(db, block))
            {
                var before = Convert.ToString(AcApp.GetSystemVariable("DIMBLK")) ?? "";
                try
                {
                    AcApp.SetSystemVariable("DIMBLK", block);
                }
                finally
                {
                    // A single period is how closed filled, which reads back empty, is set again.
                    AcApp.SetSystemVariable("DIMBLK", before.Length == 0 ? "." : before);
                }
                if (!HasBlock(db, block))
                    throw new RunRefusal("AutoCAD did not make its arrow block " + block + ". Choose another arrow, or closed_filled.");
                added = true;
            }
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            return blocks[block];
        }

        /// <summary>Looked at in a transaction of its own, closed at once, so DIMBLK may add to the block table after.</summary>
        private static bool HasBlock(Database db, string name)
        {
            using (var look = db.TransactionManager.StartOpenCloseTransaction())
            {
                var blocks = (BlockTable)look.GetObject(db.BlockTableId, OpenMode.ForRead);
                return blocks.Has(name);
            }
        }

        private static double Round(double value) => Math.Round(value, 9);

        private static void Notes(Utf8JsonWriter w, List<string> notes)
        {
            if (notes.Count == 0) return;
            w.WriteStartArray("notes");
            foreach (var note in notes) w.WriteStringValue(note);
            w.WriteEndArray();
        }
    }
}
