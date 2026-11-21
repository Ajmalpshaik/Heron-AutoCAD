using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.DatabaseServices.Filters;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// References COM has no call for (#104, #114, D-84, D-85): a PDF / DWF /
    /// DGN underlay attached, an xref, block or underlay clipped, and the list
    /// of files a drawing needs for eTransmit, each found the way AutoCAD
    /// finds it. Raster images are attached and clipped over COM by the server.
    /// </summary>
    internal static class References
    {
        private const string FilterDictionary = "ACAD_FILTER";
        private const string SpatialFilterName = "SPATIAL";
        private const double NoClipDepth = 1.0e+300;

        // ---- attach_underlay -----------------------------------------------------

        public static RunResult AttachUnderlay(Database db, Transaction tr, RunArgs args)
        {
            var path = args.Text("path");
            var kind = args.Text("kind");
            if (!File.Exists(path)) throw new RunRefusal("No file exists at '" + path + "'.");
            UnderlayDefinition definition;
            UnderlayReference reference;
            string item;
            switch (kind)
            {
                case "pdf":
                    definition = new PdfDefinition();
                    reference = new PdfReference();
                    item = args.Text("page", "1");
                    break;
                case "dwf":
                    definition = new DwfDefinition();
                    reference = new DwfReference();
                    item = args.Text("page", "");
                    break;
                case "dgn":
                    definition = new DgnDefinition();
                    reference = new DgnReference();
                    item = args.Text("page", "Default");
                    break;
                default:
                    throw new RunRefusal("'" + kind + "' is not an underlay kind: pdf, dwf or dgn.");
            }

            var key = UnderlayDefinition.GetDictionaryKey(definition.GetType());
            var named = (DBDictionary)tr.GetObject(db.NamedObjectsDictionaryId, OpenMode.ForRead);
            DBDictionary definitions;
            if (named.Contains(key))
                definitions = (DBDictionary)tr.GetObject(named.GetAt(key), OpenMode.ForWrite);
            else
            {
                named.UpgradeOpen();
                definitions = new DBDictionary();
                named.SetAt(key, definitions);
                tr.AddNewlyCreatedDBObject(definitions, true);
            }

            definition.SourceFileName = path;
            if (item.Length > 0) definition.ItemName = item;
            var baseName = Path.GetFileNameWithoutExtension(path) + (item.Length > 0 ? " - " + item : "");
            var name = FreeName(definitions, baseName);
            var definitionId = definitions.SetAt(name, definition);
            tr.AddNewlyCreatedDBObject(definition, true);
            try
            {
                definition.Load("");
            }
            catch (AcException ex)
            {
                // The whole transaction is aborted: the definition goes with it.
                throw new RunRefusal("AutoCAD could not open " + (item.Length > 0 ? "'" + item + "' in " : "") + "'" + path + "' (" + ex.ErrorStatus + "). Check the page number or sheet name, and that the file opens.");
            }

            var insertion = args.Numbers("insertion");
            reference.DefinitionId = definitionId;
            reference.Position = new Point3d(At(insertion, 0), At(insertion, 1), At(insertion, 2));
            reference.Rotation = args.Number("rotation", 0.0);
            var scale = args.Number("scale", 1.0);
            reference.ScaleFactors = new Scale3d(scale);
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var space = (BlockTableRecord)tr.GetObject(
                blocks[args.Text("space", "model") == "paper" ? BlockTableRecord.PaperSpace : BlockTableRecord.ModelSpace], OpenMode.ForWrite);
            reference.SetDatabaseDefaults(db);
            space.AppendEntity(reference);
            tr.AddNewlyCreatedDBObject(reference, true);

            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", reference.Handle.ToString());
                w.WriteString("kind", kind);
                w.WriteString("path", path);
                w.WriteString("definition", name);
                if (item.Length > 0) w.WriteString("page", item);
                RunDrawing.Style(reference, db, tr, args, w);
            });
        }

        private static double At(double[] values, int index) => index < values.Length ? values[index] : 0.0;

        private static string FreeName(DBDictionary dictionary, string wanted)
        {
            var clean = wanted.Trim();
            if (clean.Length == 0) clean = "Underlay";
            if (!dictionary.Contains(clean)) return clean;
            for (var n = 2; n < 10000; n++)
            {
                var candidate = clean + " (" + n + ")";
                if (!dictionary.Contains(candidate)) return candidate;
            }
            throw new RunRefusal("Too many underlays called '" + clean + "' in this drawing.");
        }

        // ---- clip_reference -------------------------------------------------------

        public static RunResult Clip(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var remove = args.Flag("remove", false);
            var target = tr.GetObject(RunDrawing.IdOf(db, handle), OpenMode.ForWrite);
            var world = Points(args.Element("points"));
            if (!remove && world.Count < 3) throw new RunRefusal("The clip outline needs at least three corners.");

            if (target is UnderlayReference underlay)
            {
                if (remove) underlay.IsClipped = false;
                else
                {
                    // The clip is held in the underlay's own coordinates.
                    var toUnderlay = underlay.Transform.Inverse();
                    var points = new Point2d[world.Count];
                    for (var i = 0; i < world.Count; i++)
                    {
                        var p = new Point3d(world[i].X, world[i].Y, underlay.Position.Z).TransformBy(toUnderlay);
                        points[i] = new Point2d(p.X, p.Y);
                    }
                    underlay.SetClipBoundary(points);
                    underlay.IsClipped = true;
                }
                return Clipped(handle, "underlay", !remove, world.Count);
            }

            if (target is BlockReference reference)
            {
                RemoveClip(reference, tr);
                if (!remove)
                {
                    // XCLIP's spatial filter holds the outline in the block's own
                    // coordinates, so the world points are taken back through the
                    // reference's insertion, scale and turn.
                    var toBlock = reference.BlockTransform.Inverse();
                    var local = new Point2dCollection();
                    var elevation = 0.0;
                    for (var i = 0; i < world.Count; i++)
                    {
                        var p = new Point3d(world[i].X, world[i].Y, reference.Position.Z).TransformBy(toBlock);
                        local.Add(new Point2d(p.X, p.Y));
                        if (i == 0) elevation = p.Z;
                    }
                    var definition = new SpatialFilterDefinition(local, Vector3d.ZAxis, elevation, NoClipDepth, -NoClipDepth, true);
                    var filter = new SpatialFilter { Definition = definition };
                    if (reference.ExtensionDictionary.IsNull) reference.CreateExtensionDictionary();
                    var extension = (DBDictionary)tr.GetObject(reference.ExtensionDictionary, OpenMode.ForWrite);
                    DBDictionary filters;
                    if (extension.Contains(FilterDictionary))
                        filters = (DBDictionary)tr.GetObject(extension.GetAt(FilterDictionary), OpenMode.ForWrite);
                    else
                    {
                        filters = new DBDictionary();
                        extension.SetAt(FilterDictionary, filters);
                        tr.AddNewlyCreatedDBObject(filters, true);
                    }
                    filters.SetAt(SpatialFilterName, filter);
                    tr.AddNewlyCreatedDBObject(filter, true);
                }
                return Clipped(handle, "block", !remove, world.Count);
            }

            throw new RunRefusal(handle + " is " + RunDrawing.Kind(target) + "; only an xref, a block or a PDF / DWF / DGN underlay is clipped here.");
        }

        /// <summary>Take an XCLIP off: the reference's spatial filter, if it has one.</summary>
        private static void RemoveClip(BlockReference reference, Transaction tr)
        {
            if (reference.ExtensionDictionary.IsNull) return;
            var extension = (DBDictionary)tr.GetObject(reference.ExtensionDictionary, OpenMode.ForRead);
            if (!extension.Contains(FilterDictionary)) return;
            var filters = (DBDictionary)tr.GetObject(extension.GetAt(FilterDictionary), OpenMode.ForWrite);
            if (!filters.Contains(SpatialFilterName)) return;
            var old = tr.GetObject(filters.GetAt(SpatialFilterName), OpenMode.ForWrite);
            filters.Remove(SpatialFilterName);
            old.Erase();
        }

        private static RunResult Clipped(string handle, string kind, bool clipped, int points) => RunResult.Done(w =>
        {
            w.WriteString("handle", handle);
            w.WriteString("clipped_as", kind);
            w.WriteBoolean("clipped", clipped);
            w.WriteNumber("points", clipped ? points : 0);
        });

        private static List<Point2d> Points(JsonElement element)
        {
            var points = new List<Point2d>();
            if (element.ValueKind != JsonValueKind.Array) return points;
            foreach (var pair in element.EnumerateArray())
            {
                if (pair.ValueKind != JsonValueKind.Array || pair.GetArrayLength() < 2) throw new RunRefusal("Each clip point must be [x, y].");
                points.Add(new Point2d(pair[0].GetDouble(), pair[1].GetDouble()));
            }
            return points;
        }

        // ---- list_dependencies (read only) ---------------------------------------

        /// <summary>
        /// What eTransmit needs to pack: images, underlays and fonts of this
        /// drawing and of every loaded xref, the plot style of each layout,
        /// and the file each loaded xref came from. Each file is found with
        /// AutoCAD's own search (HostApplicationServices.FindFile): the saved
        /// path, the drawing's folder, the support path. Changes nothing.
        /// </summary>
        public static RunResult Dependencies(Database db, Transaction tr, RunArgs args)
        {
            var images = new List<string[]>();
            var underlays = new List<string[]>();
            var fonts = new List<string[]>();
            var systemFonts = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
            var xrefs = new List<string[]>();
            var plotStyles = new List<string[]>();

            Read(db, tr, "", images, underlays, fonts, systemFonts);
            using (var graph = db.GetHostDwgXrefGraph(true))
            {
                for (var i = 1; i < graph.NumNodes; i++)
                {
                    var node = graph.GetXrefNode(i);
                    var xdb = node.Database;
                    xrefs.Add(new[] { node.Name, xdb?.Filename ?? "" });
                    if (xdb == null) continue;
                    using (var xtr = xdb.TransactionManager.StartOpenCloseTransaction())
                    {
                        Read(xdb, xtr, node.Name, images, underlays, fonts, systemFonts);
                        xtr.Commit();
                    }
                }
            }

            var layouts = (DBDictionary)tr.GetObject(db.LayoutDictionaryId, OpenMode.ForRead);
            foreach (var entry in layouts)
            {
                if (!(tr.GetObject(entry.Value, OpenMode.ForRead) is Layout layout)) continue;
                var sheet = layout.CurrentStyleSheet ?? "";
                if (sheet.Length > 0) plotStyles.Add(new[] { sheet, layout.LayoutName });
            }

            return RunResult.Done(w =>
            {
                Rows(w, "images", images);
                Rows(w, "underlays", underlays);
                Rows(w, "fonts", fonts);
                w.WriteStartArray("system_fonts");
                foreach (var face in systemFonts) w.WriteStringValue(face);
                w.WriteEndArray();
                w.WriteStartArray("xrefs");
                foreach (var x in xrefs)
                {
                    w.WriteStartObject();
                    w.WriteString("name", x[0]);
                    w.WriteString("file", x[1]);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                w.WriteStartArray("plot_styles");
                foreach (var p in plotStyles)
                {
                    w.WriteStartObject();
                    w.WriteString("name", p[0]);
                    w.WriteString("used_by", "layout " + p[1]);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        private static void Rows(Utf8JsonWriter w, string name, List<string[]> rows)
        {
            w.WriteStartArray(name);
            foreach (var row in rows)
            {
                w.WriteStartObject();
                w.WriteString("name", row[0]);
                w.WriteString("found", row[1]);
                w.WriteString("used_by", row[2]);
                w.WriteEndObject();
            }
            w.WriteEndArray();
        }

        private static void Read(Database db, Transaction tr, string xref, List<string[]> images, List<string[]> underlays, List<string[]> fonts, SortedSet<string> systemFonts)
        {
            var inside = xref.Length > 0 ? " in xref " + xref : "";
            var imageDictionary = RasterImageDef.GetImageDictionary(db);
            if (!imageDictionary.IsNull)
            {
                var dictionary = (DBDictionary)tr.GetObject(imageDictionary, OpenMode.ForRead);
                foreach (var entry in dictionary)
                {
                    if (!(tr.GetObject(entry.Value, OpenMode.ForRead) is RasterImageDef image)) continue;
                    var source = image.SourceFileName ?? "";
                    images.Add(new[] { source, Found(image.ActiveFileName, source, db, FindFileHint.Default), "image " + entry.Key + inside });
                }
            }

            var named = (DBDictionary)tr.GetObject(db.NamedObjectsDictionaryId, OpenMode.ForRead);
            foreach (var type in new[] { typeof(PdfDefinition), typeof(DwfDefinition), typeof(DgnDefinition) })
            {
                var key = UnderlayDefinition.GetDictionaryKey(type);
                if (!named.Contains(key)) continue;
                var dictionary = (DBDictionary)tr.GetObject(named.GetAt(key), OpenMode.ForRead);
                foreach (var entry in dictionary)
                {
                    if (!(tr.GetObject(entry.Value, OpenMode.ForRead) is UnderlayDefinition underlay)) continue;
                    var source = underlay.SourceFileName ?? "";
                    underlays.Add(new[] { source, Found(underlay.ActiveFileName, source, db, FindFileHint.UnderlayFile), "underlay " + entry.Key + inside });
                }
            }

            var styles = (TextStyleTable)tr.GetObject(db.TextStyleTableId, OpenMode.ForRead);
            foreach (ObjectId id in styles)
            {
                var style = (TextStyleTableRecord)tr.GetObject(id, OpenMode.ForRead);
                // A style bound in from an xref (XREF|STYLE) is listed with the xref itself.
                if (style.IsDependent) continue;
                var file = style.FileName ?? "";
                var used = (style.IsShapeFile ? "shape file " : "text style ") + style.Name + inside;
                if (file.Length > 0)
                {
                    var trueType = file.EndsWith(".ttf", StringComparison.OrdinalIgnoreCase) || file.EndsWith(".ttc", StringComparison.OrdinalIgnoreCase);
                    fonts.Add(new[] { file, Found("", file, db, trueType ? FindFileHint.TrueTypeFontFile : FindFileHint.FontFile), used });
                }
                else
                {
                    var face = style.Font.TypeFace ?? "";
                    if (face.Length > 0) systemFonts.Add(face);
                }
                var big = style.BigFontFileName ?? "";
                if (big.Length > 0) fonts.Add(new[] { big, Found("", big, db, FindFileHint.FontFile), "big font of " + used });
            }
        }

        /// <summary>The file AutoCAD uses: the one it already resolved, else its own search; "" when none.</summary>
        private static string Found(string active, string source, Database db, FindFileHint hint)
        {
            if (!string.IsNullOrEmpty(active) && File.Exists(active)) return Path.GetFullPath(active);
            if (string.IsNullOrEmpty(source)) return "";
            try
            {
                var found = HostApplicationServices.Current.FindFile(source, db, hint);
                return !string.IsNullOrEmpty(found) && File.Exists(found) ? Path.GetFullPath(found) : "";
            }
            catch (AcException)
            {
                return "";
            }
        }
    }
}
