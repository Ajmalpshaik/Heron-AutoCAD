using System;
using System.Collections.Generic;
using System.IO;
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

            var source = doc.Database.Filename;
            if (string.IsNullOrEmpty(source) || !File.Exists(source) || !source.EndsWith(".dwg", StringComparison.OrdinalIgnoreCase))
                throw new RunRefusal("This drawing has not been saved as a .dwg yet. Save it first (autocad_save_drawing); the PDF is made from the saved file.");
            if (Convert.ToInt32(AcApp.GetSystemVariable("DBMOD")) != 0)
                throw new RunRefusal("This drawing has unsaved changes, and the PDF is made from the saved file. Save it first (autocad_save_drawing), then publish.");

            var sheets = PublishPlan.Choose(Layouts(doc.Database), args.Texts("layouts"), args.Flag("include_model", false), out var refusal);
            if (refusal != null) throw new RunRefusal(refusal);

            var background = AcApp.GetSystemVariable("BACKGROUNDPLOT");
            var dsdFile = Path.Combine(Path.GetTempPath(), "heron-publish-" + Guid.NewGuid().ToString("N") + ".dsd");
            HeronLog.Write("publish " + sheets.Count + " sheet(s) to " + target);
            try
            {
                // Foreground, so the PDF is finished when PublishExecute returns.
                AcApp.SetSystemVariable("BACKGROUNDPLOT", 0);
                using (var entries = new DsdEntryCollection())
                using (var dsd = new DsdData())
                {
                    foreach (var sheet in sheets)
                    {
                        entries.Add(new DsdEntry
                        {
                            DwgName = source,
                            Layout = sheet,
                            Title = Path.GetFileNameWithoutExtension(source) + "-" + sheet,
                            Nps = "",
                            NpsSourceDwg = "",
                        });
                    }
                    dsd.SheetType = SheetType.MultiPdf;
                    dsd.ProjectPath = Path.GetDirectoryName(target) ?? "";
                    dsd.DestinationName = target;
                    dsd.NoOfCopies = 1;
                    dsd.SetDsdEntryCollection(entries);
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
