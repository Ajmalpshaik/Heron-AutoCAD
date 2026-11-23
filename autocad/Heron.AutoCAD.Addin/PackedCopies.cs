using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// eTransmit's packed copy pointed at the files beside it (#160, D-149).
    ///
    /// The server copies each drawing it packs into a folder of its own and
    /// asks for that copy here. It is opened as a side database (never as a
    /// drawing on screen, so the modeller's drawing is never touched), each
    /// xref, raster image and PDF / DWF / DGN underlay path saved in it is set
    /// to the bare file name when that file is in the pack (the rule is
    /// <see cref="PackPaths"/>), and the copy is saved in its own DWG version,
    /// through a new file put in its place. Nothing to change: it is not saved.
    /// Runs outside the drawing's lock and transaction, as publishing does.
    /// </summary>
    internal static class PackedCopies
    {
        public static RunResult Retarget(RunArgs args)
        {
            var file = args.Text("file");
            var open = new List<string>();
            foreach (Document doc in AcApp.DocumentManager) open.Add(doc.Name ?? "");
            var refusal = PackPaths.Refusal(file, open);
            if (refusal != null) throw new RunRefusal(refusal);
            if (!File.Exists(file)) throw new RunRefusal("No packed copy exists at '" + file + "'.");
            var inPack = new HashSet<string>(args.Texts("names"), StringComparer.OrdinalIgnoreCase);
            var clashing = new HashSet<string>(args.Texts("clashing"), StringComparer.OrdinalIgnoreCase);
            var changed = new List<string[]>();
            var kept = new List<string[]>();
            var fresh = Path.Combine(Path.GetDirectoryName(file) ?? "", Path.GetFileNameWithoutExtension(file) + ".heron-new.dwg");

            var working = HostApplicationServices.WorkingDatabase;
            using (var db = new Database(false, true))
            {
                db.ReadDwgFile(file, FileOpenMode.OpenForReadAndAllShare, true, "");
                // Everything read in and the file let go, so the new copy can take its place.
                db.CloseInput(true);
                HostApplicationServices.WorkingDatabase = db;
                try
                {
                    using (var tr = db.TransactionManager.StartTransaction())
                    {
                        var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                        foreach (ObjectId id in blocks)
                        {
                            var block = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
                            if (!block.IsFromExternalReference) continue;
                            Apply("xref", block.Name, block.PathName, path =>
                            {
                                block.UpgradeOpen();
                                block.PathName = path;
                            }, changed, kept, inPack, clashing);
                        }

                        var imageDictionary = RasterImageDef.GetImageDictionary(db);
                        if (!imageDictionary.IsNull)
                        {
                            var images = (DBDictionary)tr.GetObject(imageDictionary, OpenMode.ForRead);
                            foreach (var entry in images)
                            {
                                if (!(tr.GetObject(entry.Value, OpenMode.ForRead) is RasterImageDef image)) continue;
                                Apply("image", entry.Key, image.SourceFileName, path =>
                                {
                                    image.UpgradeOpen();
                                    image.SourceFileName = path;
                                }, changed, kept, inPack, clashing);
                            }
                        }

                        var named = (DBDictionary)tr.GetObject(db.NamedObjectsDictionaryId, OpenMode.ForRead);
                        foreach (var type in new[] { typeof(PdfDefinition), typeof(DwfDefinition), typeof(DgnDefinition) })
                        {
                            var key = UnderlayDefinition.GetDictionaryKey(type);
                            if (!named.Contains(key)) continue;
                            var underlays = (DBDictionary)tr.GetObject(named.GetAt(key), OpenMode.ForRead);
                            foreach (var entry in underlays)
                            {
                                if (!(tr.GetObject(entry.Value, OpenMode.ForRead) is UnderlayDefinition underlay)) continue;
                                Apply("underlay", entry.Key, underlay.SourceFileName, path =>
                                {
                                    underlay.UpgradeOpen();
                                    underlay.SourceFileName = path;
                                }, changed, kept, inPack, clashing);
                            }
                        }
                        tr.Commit();
                    }
                    if (changed.Count > 0) db.SaveAs(fresh, db.OriginalFileVersion);
                }
                finally
                {
                    HostApplicationServices.WorkingDatabase = working;
                }
            }
            if (changed.Count > 0)
            {
                File.Copy(fresh, file, true);
                File.Delete(fresh);
            }

            return RunResult.Done(w =>
            {
                w.WriteString("file", file);
                w.WriteBoolean("saved", changed.Count > 0);
                w.WriteStartArray("changed");
                foreach (var row in changed)
                {
                    w.WriteStartObject();
                    w.WriteString("kind", row[0]);
                    w.WriteString("name", row[1]);
                    w.WriteString("was", row[2]);
                    w.WriteString("now", row[3]);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                w.WriteStartArray("kept");
                foreach (var row in kept)
                {
                    w.WriteStartObject();
                    w.WriteString("kind", row[0]);
                    w.WriteString("name", row[1]);
                    w.WriteString("path", row[2]);
                    w.WriteString("why", row[3]);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        private static void Apply(
            string kind, string name, string? saved, Action<string> write,
            List<string[]> changed, List<string[]> kept, HashSet<string> inPack, HashSet<string> clashing)
        {
            var choice = PackPaths.Decide(saved, inPack, clashing);
            if (choice.NewPath != null)
            {
                write(choice.NewPath);
                changed.Add(new[] { kind, name, saved ?? "", choice.NewPath });
            }
            else if (!choice.Already)
            {
                kept.Add(new[] { kind, name, saved ?? "", choice.Why });
            }
        }
    }
}
