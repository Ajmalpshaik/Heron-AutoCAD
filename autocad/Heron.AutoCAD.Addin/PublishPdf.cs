using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.PlottingServices;
using Autodesk.AutoCAD.Publishing;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Several sheets of the open drawing published to one PDF, the way
    /// PUBLISH does it: a DSD list and AutoCAD's publisher. COM has no call
    /// for a multi-sheet PDF (docs/11-adn-repos-study.md, item 1).
    ///
    /// Runs outside a transaction and a document lock: the publisher opens the
    /// sheets itself. It reads the drawing as last saved, so a drawing with
    /// unsaved changes is refused rather than published out of date. Nothing
    /// in the drawing changes; BACKGROUNDPLOT is put back as it was.
    /// </summary>
    internal static class PublishPdf
    {
        private const string Plotter = "DWG To PDF.pc3";

        public static RunResult Run(Document doc, RunArgs args)
        {
            var target = args.Text("path").Trim();
            var problem = PublishPlan.CheckTarget(target, args.Flag("overwrite", false), File.Exists, Directory.Exists);
            if (problem != null) throw new RunRefusal(problem);
            if (args.Texts("drawings").Length > 0) return RunMany(doc, args, target);

            var source = doc.Database.Filename;
            if (string.IsNullOrEmpty(source) || !File.Exists(source) || !source.EndsWith(".dwg", StringComparison.OrdinalIgnoreCase))
                throw new RunRefusal("This drawing has not been saved as a .dwg yet. Save it first (autocad_save_drawing); the PDF is made from the saved file.");
            if (Convert.ToInt32(AcApp.GetSystemVariable("DBMOD")) != 0)
                throw new RunRefusal("This drawing has unsaved changes, and the PDF is made from the saved file. Save it first (autocad_save_drawing), then publish.");

            var sheets = PublishPlan.Choose(Layouts(doc.Database), args.Texts("layouts"), args.Flag("include_model", false), out var refusal);
            if (refusal != null) throw new RunRefusal(refusal);

            Publish(sheets.Select(sheet => new PublishPlan.Entry(source, sheet)).ToList(), target);
            return RunResult.Done(w =>
            {
                w.WriteBoolean("published", true);
                w.WriteString("path", target);
                w.WriteNumber("count", sheets.Count);
                w.WriteStartArray("sheets");
                foreach (var sheet in sheets) w.WriteStringValue(sheet);
                w.WriteEndArray();
            });
        }

        /// <summary>
        /// One PDF from several drawings (#67, D-91). Each is read for its layouts and
        /// its xrefs first: one open here with unsaved changes, or attaching an xref
        /// that cannot be found, is refused by name before anything is plotted. The
        /// server checks the other open drawings' unsaved state over COM first.
        /// </summary>
        private static RunResult RunMany(Document doc, RunArgs args, string target)
        {
            var drawings = new List<PublishPlan.Drawing>();
            foreach (var path in args.Texts("drawings").Select(p => (p ?? "").Trim()).Where(p => p.Length > 0))
                drawings.Add(Read(doc, path));
            var entries = PublishPlan.ChooseAcross(drawings, args.Texts("layouts"), args.Flag("include_model", false), out var refusal);
            if (refusal != null) throw new RunRefusal(refusal);

            Publish(entries, target);
            return RunResult.Done(w =>
            {
                w.WriteBoolean("published", true);
                w.WriteString("path", target);
                w.WriteNumber("count", entries.Count);
                w.WriteStartArray("sheets");
                foreach (var entry in entries) w.WriteStringValue(entry.Layout);
                w.WriteEndArray();
                w.WriteStartArray("pages");
                foreach (var entry in entries)
                {
                    w.WriteStartObject();
                    w.WriteString("drawing", entry.Path);
                    w.WriteString("layout", entry.Layout);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                w.WriteNumber("drawings", entries.Select(e => e.Path).Distinct(StringComparer.OrdinalIgnoreCase).Count());
            });
        }

        /// <summary>A drawing's layouts and the xrefs it cannot find, from the open drawing or the file on disk.</summary>
        private static PublishPlan.Drawing Read(Document active, string path)
        {
            if (!path.EndsWith(".dwg", StringComparison.OrdinalIgnoreCase)) return new PublishPlan.Drawing(path, new PublishPlan.Sheet[0], unreadable: "not a .dwg");
            if (!File.Exists(path)) return new PublishPlan.Drawing(path, new PublishPlan.Sheet[0], unreadable: "no such file");

            var open = OpenDocument(path);
            var unsaved = open != null && open == active && Convert.ToInt32(AcApp.GetSystemVariable("DBMOD")) != 0;
            try
            {
                if (open != null) return Facts(open.Database, path, unsaved);
                using (var side = new Database(false, true))
                {
                    side.ReadDwgFile(path, FileOpenMode.OpenForReadAndAllShare, true, "");
                    return Facts(side, path, false);
                }
            }
            catch (Autodesk.AutoCAD.Runtime.Exception ex)
            {
                HeronLog.Error("Read " + path + " for publishing", ex);
                return new PublishPlan.Drawing(path, new PublishPlan.Sheet[0], unreadable: ex.ErrorStatus.ToString());
            }
            catch (System.IO.IOException ex)
            {
                return new PublishPlan.Drawing(path, new PublishPlan.Sheet[0], unreadable: ex.Message);
            }
        }

        private static Document? OpenDocument(string path)
        {
            var full = Path.GetFullPath(path);
            foreach (Document doc in AcApp.DocumentManager)
            {
                var name = doc.Database.Filename;
                if (!string.IsNullOrEmpty(name) && string.Equals(Path.GetFullPath(name), full, StringComparison.OrdinalIgnoreCase)) return doc;
            }
            return null;
        }

        private static PublishPlan.Drawing Facts(Database db, string path, bool unsaved)
        {
            var missing = new List<string>();
            var folder = Path.GetDirectoryName(path) ?? "";
            using (var tr = db.TransactionManager.StartOpenCloseTransaction())
            {
                var table = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                foreach (ObjectId id in table)
                {
                    var record = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
                    if (!record.IsFromExternalReference || record.IsUnloaded) continue;
                    // A nested xref shows as HOST|NAME; it is checked through the xref that holds it.
                    if (record.Name.Contains("|")) continue;
                    if (!PublishPlan.XrefFound(record.PathName, folder, File.Exists) && !Searched(record.PathName, db)) missing.Add(record.Name);
                }
                tr.Abort();
            }
            return new PublishPlan.Drawing(path, Layouts(db), unsaved, missing);
        }

        /// <summary>AutoCAD's own search for an xref file: support paths, project paths.</summary>
        private static bool Searched(string savedPath, Database db)
        {
            if (string.IsNullOrWhiteSpace(savedPath)) return false;
            try
            {
                var found = HostApplicationServices.Current.FindFile(savedPath, db, FindFileHint.XRefDrawing);
                return !string.IsNullOrEmpty(found) && File.Exists(found);
            }
            catch (Autodesk.AutoCAD.Runtime.Exception)
            {
                return false;
            }
        }

        /// <summary>The PDF itself: a DSD list and AutoCAD's publisher, in the foreground.</summary>
        private static void Publish(List<PublishPlan.Entry> entries, string target)
        {
            var background = AcApp.GetSystemVariable("BACKGROUNDPLOT");
            var dsdFile = Path.Combine(Path.GetTempPath(), "heron-publish-" + Guid.NewGuid().ToString("N") + ".dsd");
            HeronLog.Write("publish " + entries.Count + " sheet(s) to " + target);
            try
            {
                // Foreground, so the PDF is finished when PublishExecute returns.
                AcApp.SetSystemVariable("BACKGROUNDPLOT", 0);
                using (var list = new DsdEntryCollection())
                using (var dsd = new DsdData())
                {
                    foreach (var entry in entries)
                    {
                        list.Add(new DsdEntry
                        {
                            DwgName = entry.Path,
                            Layout = entry.Layout,
                            Title = Path.GetFileNameWithoutExtension(entry.Path) + "-" + entry.Layout,
                            Nps = "",
                            NpsSourceDwg = "",
                        });
                    }
                    dsd.SheetType = SheetType.MultiPdf;
                    dsd.ProjectPath = Path.GetDirectoryName(target) ?? "";
                    dsd.DestinationName = target;
                    dsd.NoOfCopies = 1;
                    dsd.SetDsdEntryCollection(list);
                    // No file box, and sheets never opened are set up first, or they print blank.
                    dsd.WriteDsd(dsdFile);
                    File.WriteAllText(dsdFile, PublishPlan.Quiet(File.ReadAllText(dsdFile)));
                    dsd.ReadDsd(dsdFile);

                    var config = PlotConfigManager.SetCurrentConfig(Plotter);
                    AcApp.Publisher.PublishExecute(dsd, config);
                }
            }
            finally
            {
                try
                {
                    AcApp.SetSystemVariable("BACKGROUNDPLOT", background);
                }
                catch (System.Exception ex)
                {
                    HeronLog.Error("Put BACKGROUNDPLOT back", ex);
                }
                try
                {
                    if (File.Exists(dsdFile)) File.Delete(dsdFile);
                }
                catch (System.Exception ex)
                {
                    HeronLog.Error("Remove the publish list", ex);
                }
            }

            if (!File.Exists(target))
                throw new RunRefusal("AutoCAD's publisher finished but wrote no PDF at '" + target + "'. Its log (PUBLISH's details) says why.");
        }

        /// <summary>The drawing's layouts in tab order, Model first.</summary>
        private static List<PublishPlan.Sheet> Layouts(Database db)
        {
            var found = new List<PublishPlan.Sheet>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var dictionary = (DBDictionary)tr.GetObject(db.LayoutDictionaryId, OpenMode.ForRead);
                foreach (DBDictionaryEntry entry in dictionary)
                {
                    var layout = (Layout)tr.GetObject(entry.Value, OpenMode.ForRead);
                    found.Add(new PublishPlan.Sheet(layout.LayoutName, layout.TabOrder, layout.ModelType));
                }
                tr.Abort();
            }
            return found;
        }
    }
}
