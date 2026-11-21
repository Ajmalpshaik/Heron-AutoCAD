using System.Collections.Generic;
using System.IO;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Tables linked to an Excel range (D-83): AutoCAD's Data Link, which COM
    /// has no call for. A link is a DataLink in the drawing's Data Link
    /// Manager, with the connection string "file!sheet!range", set on a new
    /// table, which AutoCAD then fills from the sheet itself.
    ///
    /// The link keeps the table's own formatting (SkipFormat), so Heron's
    /// rule holds after every update: text in the vertical middle of each cell.
    /// Built against AutoCAD's Cell API, current in 2021 to 2027.
    /// </summary>
    internal static class ExcelTables
    {
        private const string ExcelAdapter = "AcExcel";
        private const string NamePrefix = "Heron ";

        public static RunResult Make(Database db, Transaction tr, RunArgs args)
        {
            var path = args.Text("path").Trim();
            if (path.Length == 0 || !File.Exists(path)) throw new RunRefusal("There is no file " + path + ".");
            var sheet = args.Text("sheet").Trim();
            var range = args.Text("range").Trim();
            var connection = path + (sheet.Length > 0 ? "!" + sheet : "") + (range.Length > 0 ? "!" + range : "");

            var links = db.DataLinkManager;
            var link = new DataLink
            {
                DataAdapterId = ExcelAdapter,
                Name = FreeName(links, NamePrefix + Path.GetFileNameWithoutExtension(path) + " " + sheet + " " + range),
                Description = "Made by Heron AI for AutoCAD",
                ToolTip = connection,
                ConnectionString = connection,
                DataLinkOption = DataLinkOption.PersistCache,
            };
            link.UpdateOption |= (int)UpdateOption.SkipFormat;
            var linkId = links.AddDataLink(link);
            tr.AddNewlyCreatedDBObject(link, true);

            var table = new Table();
            table.SetDatabaseDefaults(db);
            table.TableStyle = Style(db, tr, args.Text("style").Trim());
            var at = args.Numbers("position");
            table.Position = new Point3d(at.Length > 0 ? at[0] : 0, at.Length > 1 ? at[1] : 0, at.Length > 2 ? at[2] : 0);
            table.Cells[0, 0].SetDataLink(linkId, true);
            table.GenerateLayout();
            if (table.Rows.Count <= 1 && table.Columns.Count <= 1 && string.IsNullOrEmpty(table.Cells[0, 0].TextString))
                throw new RunRefusal("AutoCAD made the link but read nothing from " + Path.GetFileName(path) + " (" + sheet + " " + range
                    + "). A data link may need Microsoft Excel on this PC; check the file opens in Excel.");

            var space = Space(db, tr, args.Text("space"));
            space.AppendEntity(table);
            tr.AddNewlyCreatedDBObject(table, true);
            if (args.Has("text_height")) table.Cells.TextHeight = args.Number("text_height");
            MiddleCells(table);

            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", table.Handle.ToString());
                w.WriteString("type", "table");
                w.WriteString("link", link.Name);
                w.WriteString("connection", connection);
                w.WriteNumber("table_rows", table.Rows.Count);
                w.WriteNumber("table_columns", table.Columns.Count);
                RunDrawing.Style(table, db, tr, args, w);
            });
        }

        public static RunResult Update(Database db, Transaction tr, RunArgs args)
        {
            var tables = new List<Table>();
            var seen = new HashSet<ObjectId>();
            var notLinked = new List<string>();
            var handles = args.Texts("handles");
            if (handles.Length > 0)
            {
                foreach (var handle in handles)
                {
                    var table = RunDrawing.Open<Table>(tr, db, handle, OpenMode.ForRead, "a table");
                    if (seen.Add(table.ObjectId)) tables.Add(table);
                }
            }
            else
            {
                foreach (ObjectId linkId in db.DataLinkManager.GetDataLink())
                {
                    if (!(tr.GetObject(linkId, OpenMode.ForRead) is DataLink link)) continue;
                    foreach (ObjectId target in link.GetTargets())
                        if (!target.IsErased && tr.GetObject(target, OpenMode.ForRead) is Table table && seen.Add(table.ObjectId))
                            tables.Add(table);
                }
            }

            var updated = new List<(string Handle, string Source)>();
            foreach (var table in tables)
            {
                var ids = table.GetDataLink();
                if (ids == null || ids.Count == 0)
                {
                    notLinked.Add(table.Handle.ToString());
                    continue;
                }
                var source = tr.GetObject(ids[0], OpenMode.ForRead) is DataLink first ? first.ConnectionString : "";
                try
                {
                    // Two steps, as DATALINKUPDATE does them: each link reads its
                    // workbook again (a link keeps a cached copy, PersistCache),
                    // then the table takes the link's new values.
                    foreach (ObjectId id in ids)
                        if (tr.GetObject(id, OpenMode.ForWrite) is DataLink link)
                            link.Update(UpdateDirection.SourceToData, UpdateOption.None);
                    table.UpgradeOpen();
                    table.UpdateDataLink(UpdateDirection.SourceToData, UpdateOption.SkipFormat);
                }
                catch (AcException ex)
                {
                    throw new RunRefusal("AutoCAD could not read " + source + " for table " + table.Handle + " (" + ex.ErrorStatus
                        + "). Check the file is there and saved; a data link may need Microsoft Excel on this PC.");
                }
                MiddleCells(table);
                updated.Add((table.Handle.ToString(), source));
            }

            return RunResult.Done(w =>
            {
                w.WriteStartArray("updated");
                foreach (var (handle, source) in updated)
                {
                    w.WriteStartObject();
                    w.WriteString("handle", handle);
                    w.WriteString("source", source);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                w.WriteStartArray("not_linked");
                foreach (var handle in notLinked) w.WriteStringValue(handle);
                w.WriteEndArray();
                if (updated.Count == 0 && notLinked.Count == 0) w.WriteString("note", "No table in this drawing is linked to Excel.");
            });
        }

        /// <summary>Every cell keeps its left / centre / right, in the vertical middle; a cell AutoCAD will not format keeps its own.</summary>
        private static void MiddleCells(Table table)
        {
            for (var row = 0; row < table.Rows.Count; row++)
                for (var column = 0; column < table.Columns.Count; column++)
                {
                    var cell = table.Cells[row, column];
                    var now = (int)(cell.Alignment ?? CellAlignment.MiddleCenter);
                    var middle = (CellAlignment)(now >= 1 && now <= 9 ? 4 + (now - 1) % 3 : (int)CellAlignment.MiddleCenter);
                    if (middle == cell.Alignment) continue;
                    try
                    {
                        cell.Alignment = middle;
                    }
                    catch (AcException)
                    {
                        // a format-locked cell: its alignment is the modeller's
                    }
                }
        }

        private static ObjectId Style(Database db, Transaction tr, string name)
        {
            if (name.Length == 0) return db.Tablestyle;
            var styles = (DBDictionary)tr.GetObject(db.TableStyleDictionaryId, OpenMode.ForRead);
            if (!styles.Contains(name))
                throw new RunRefusal("This drawing has no table style called '" + name + "'. Make it with autocad_create_styles(table_styles=...), copy it in with autocad_import_from_drawing, or leave style out.");
            return styles.GetAt(name);
        }

        /// <summary>Model space, or the space of the sheet tab that is active.</summary>
        private static BlockTableRecord Space(Database db, Transaction tr, string space)
        {
            if (space != "paper")
                return (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
            var layouts = LayoutManager.Current;
            var current = layouts.CurrentLayout;
            if (string.Equals(current, "Model", System.StringComparison.OrdinalIgnoreCase))
                throw new RunRefusal("The Model tab is active, so there is no sheet to put the table on. Click a sheet tab, or use space='model'.");
            var layout = (Layout)tr.GetObject(layouts.GetLayoutId(current), OpenMode.ForRead);
            return (BlockTableRecord)tr.GetObject(layout.BlockTableRecordId, OpenMode.ForWrite);
        }

        private static string FreeName(DataLinkManager links, string wanted)
        {
            var clean = wanted.Trim();
            if (links.GetDataLink(clean).IsNull) return clean;
            for (var number = 2; number < 1000; number++)
            {
                var name = clean + " (" + number + ")";
                if (links.GetDataLink(name).IsNull) return name;
            }
            throw new RunRefusal("This drawing already has 1,000 data links named " + clean + ". Remove some in the Data Link Manager.");
        }
    }
}
