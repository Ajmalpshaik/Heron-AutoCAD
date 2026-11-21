using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Sheets made in .NET (#64, #65, D-90): a layout with its page setup, and a
    /// viewport in the layout's own block. Over COM both went through
    /// doc.PaperSpace, which threw a bare Automation error on a sheet made with
    /// Layouts.Add (known limit 23), and the page setup went busy part-way
    /// (#40). Here the sheet is one transaction: it all lands, or none of it.
    ///
    /// The scale, the frame and where the viewport goes are worked out by the
    /// server (acad/sheets.py); the plug-in is handed the numbers.
    /// </summary>
    internal static class Sheets
    {
        private const string Collection = "ACDB_ANNOTATIONSCALES";

        // ---------------------------------------------------------------------
        // A new sheet
        // ---------------------------------------------------------------------

        /// <summary>
        /// A new layout, empty or copied from another one with everything on it, set
        /// to plot the layout at 1:1 on the plotter and sheet asked. Every refusal
        /// comes before the layout is made: AutoCAD's layout manager is not trusted
        /// to take a new layout back out when the transaction is aborted.
        /// </summary>
        public static RunResult CreateLayout(Document doc, Database db, Transaction tr, RunArgs args)
        {
            var name = args.Text("name").Trim();
            var copyFrom = args.Text("copy_from").Trim();
            var plotter = args.Text("plotter").Trim();
            var paper = args.Text("paper_size").Trim();
            var orientation = args.Text("orientation").Trim().ToLowerInvariant();
            var styleSheet = args.Text("plot_style_table").Trim();
            var activate = args.Flag("activate", true);

            if (name.Length == 0) throw new RunRefusal("Give the new sheet a name, e.g. 'E-101'.");
            try
            {
                SymbolUtilityServices.ValidateSymbolName(name, false);
            }
            catch (Autodesk.AutoCAD.Runtime.Exception)
            {
                throw new RunRefusal("'" + name + "' cannot be a layout name.");
            }
            if (string.Equals(name, "Model", StringComparison.OrdinalIgnoreCase))
                throw new RunRefusal("'Model' is model space, not a sheet. Pick another name.");
            var layouts = Layouts(db, tr);
            if (layouts.Keys.Any(k => string.Equals(k, name, StringComparison.OrdinalIgnoreCase)))
                throw new RunRefusal("This drawing already has a layout called '" + name + "'. Pick another name, or change that one with autocad_page_setup.");

            Layout? source = null;
            if (copyFrom.Length > 0)
            {
                var found = layouts.FirstOrDefault(p => string.Equals(p.Key, copyFrom, StringComparison.OrdinalIgnoreCase));
                if (found.Key == null)
                    throw new RunRefusal("This drawing has no layout named '" + copyFrom + "'. Layouts: " + Names(layouts) + ".");
                source = (Layout)tr.GetObject(found.Value, OpenMode.ForRead);
                if (source.ModelType) throw new RunRefusal("'Model' is model space; copy a sheet instead.");
                copyFrom = source.LayoutName;
            }

            var psv = PlotSettingsValidator.Current;
            var plan = Plan(psv, source, plotter, paper, orientation, styleSheet);

            var manager = LayoutManager.Current;
            ObjectId id;
            if (source != null)
            {
                manager.CopyLayout(copyFrom, name);
                id = manager.GetLayoutId(name);
            }
            else
            {
                id = manager.CreateLayout(name);
            }

            Layout layout;
            var written = new List<(string key, string value)>();
            bool centred;
            try
            {
                layout = (Layout)tr.GetObject(id, OpenMode.ForWrite);
                centred = Apply(psv, layout, plan, written);
            }
            catch
            {
                // Never leave a half-made sheet: a second try would only be told the name is taken.
                try
                {
                    manager.DeleteLayout(name);
                }
                catch (System.Exception ex)
                {
                    HeronLog.Error("Remove the half-made layout " + name, ex);
                }
                throw;
            }

            // Making it current waits for the commit: a layout that the transaction
            // could still take back must never be the one on screen.
            if (activate) PluginRunner.AfterCommit(() => MakeCurrent(name));

            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("layout", layout.LayoutName);
                w.WriteNumber("tab_order", layout.TabOrder);
                if (source != null) w.WriteString("copied_from", copyFrom);
                w.WriteBoolean("activated", activate);
                w.WriteStartObject("page_setup");
                foreach (var (key, value) in written) w.WriteString(key, value);
                w.WriteString("plot_area", "layout");
                w.WriteString("scale", "1:1");
                w.WriteBoolean("centred", centred);
                w.WriteEndObject();
                WritePaper(w, layout);
            });
        }

        private sealed class PagePlan
        {
            public string Device = "";
            public string Media = "";
            public string StyleSheet = "";
            public string Orientation = "";
        }

        /// <summary>The plotter, sheet and plot style table, checked against what AutoCAD offers before anything is made.</summary>
        private static PagePlan Plan(PlotSettingsValidator psv, Layout? source, string plotter, string paper, string orientation, string styleSheet)
        {
            var plan = new PagePlan();
            if (orientation.Length > 0 && orientation != "portrait" && orientation != "landscape")
                throw new RunRefusal("orientation must be 'portrait' or 'landscape'.");

            using (var trial = new PlotSettings(false))
            {
                if (source != null) trial.CopyFrom(source);
                if (plotter.Length > 0)
                {
                    var devices = psv.GetPlotDeviceList().Cast<string>().ToList();
                    var device = devices.FirstOrDefault(d => string.Equals(d, plotter, StringComparison.OrdinalIgnoreCase));
                    if (device == null)
                        throw new RunRefusal("AutoCAD has no plotter called '" + plotter + "'. Use the name exactly as Page Setup lists it, e.g. 'DWG To PDF.pc3'.");
                    psv.SetPlotConfigurationName(trial, device, null);
                    psv.RefreshLists(trial);
                    plan.Device = device;
                }
                if (paper.Length > 0)
                {
                    if (plan.Device.Length == 0 && source == null)
                        throw new RunRefusal("A paper size needs the plotter it comes from: pass plotter (e.g. 'DWG To PDF.pc3') as well, or leave paper_size out.");
                    var names = psv.GetCanonicalMediaNameList(trial).Cast<string>().ToList();
                    if (names.Count == 0)
                        throw new RunRefusal("AutoCAD reported no sheet sizes for the plotter '" + trial.PlotConfigurationName + "'. Set a plotter such as 'DWG To PDF.pc3'.");
                    var wanted = paper;
                    var lower = paper.ToLowerInvariant();
                    if (orientation.Length > 0 && !lower.Contains("portrait") && !lower.Contains("landscape")) wanted = paper + " " + orientation;
                    var media = SheetMath.MatchMedia(names, wanted);
                    if (media == null)
                        throw new RunRefusal("'" + paper + "' is not a paper size the " + trial.PlotConfigurationName + " plotter offers. Sizes it has: "
                            + string.Join(", ", SheetMath.MediaSizes(names)) + ". Add 'portrait' for an upright sheet.");
                    plan.Media = media;
                    plan.Orientation = orientation;
                }
                if (styleSheet.Length > 0)
                {
                    var sheets = psv.GetPlotStyleSheetList().Cast<string>().ToList();
                    var sheet = sheets.FirstOrDefault(s => string.Equals(s, styleSheet, StringComparison.OrdinalIgnoreCase));
                    if (sheet == null)
                        throw new RunRefusal("AutoCAD has no plot style table called '" + styleSheet + "'. Tables it has: " + string.Join(", ", sheets.Take(30)) + ".");
                    plan.StyleSheet = sheet;
                }
            }
            return plan;
        }

        /// <summary>The page setup written to the new layout. True when it is centred.</summary>
        private static bool Apply(PlotSettingsValidator psv, Layout layout, PagePlan plan, List<(string key, string value)> written)
        {
            var centred = false;
            using (var ps = new PlotSettings(layout.ModelType))
            {
                ps.CopyFrom(layout);
                if (plan.Device.Length > 0)
                {
                    psv.SetPlotConfigurationName(ps, plan.Device, plan.Media.Length > 0 ? plan.Media : null);
                    psv.RefreshLists(ps);
                    written.Add(("plotter", plan.Device));
                }
                else if (plan.Media.Length > 0)
                {
                    psv.SetCanonicalMediaName(ps, plan.Media);
                }
                if (plan.Media.Length > 0)
                {
                    written.Add(("paper_size", LocaleName(psv, ps, plan.Media)));
                    if (plan.Orientation.Length > 0) written.Add(("orientation", plan.Orientation));
                }
                psv.SetPlotType(ps, Autodesk.AutoCAD.DatabaseServices.PlotType.Layout);
                psv.SetUseStandardScale(ps, true);
                psv.SetStdScaleType(ps, StdScaleType.StdScale1To1);
                try
                {
                    psv.SetPlotCentered(ps, true);
                    centred = true;
                }
                catch (Autodesk.AutoCAD.Runtime.Exception)
                {
                    // A layout plot is placed by its own origin; AutoCAD may not centre it.
                }
                if (plan.StyleSheet.Length > 0)
                {
                    psv.SetCurrentStyleSheet(ps, plan.StyleSheet);
                    ps.PlotPlotStyles = true;
                    written.Add(("plot_style_table", plan.StyleSheet));
                }
                layout.CopyFrom(ps);
            }
            return centred;
        }

        private static string LocaleName(PlotSettingsValidator psv, PlotSettings ps, string media)
        {
            try
            {
                var names = psv.GetCanonicalMediaNameList(ps).Cast<string>().ToList();
                var index = names.FindIndex(n => n == media);
                return index >= 0 ? psv.GetLocaleMediaName(ps, index) : media;
            }
            catch (Autodesk.AutoCAD.Runtime.Exception)
            {
                return media;
            }
        }

        /// <summary>The sheet a layout is set to, the same facts the server reads over COM (tools/sheets.py _paper_of).</summary>
        private static void WritePaper(Utf8JsonWriter w, Layout layout)
        {
            var size = layout.PlotPaperSize;
            var margins = layout.PlotPaperMargins;
            w.WriteStartObject("paper");
            w.WriteString("media", layout.CanonicalMediaName ?? "");
            w.WriteString("plotter", layout.PlotConfigurationName ?? "");
            w.WriteStartArray("size");
            w.WriteNumberValue(Math.Round(size.X, 4));
            w.WriteNumberValue(Math.Round(size.Y, 4));
            w.WriteEndArray();
            w.WriteStartArray("margins");
            w.WriteNumberValue(Math.Round(margins.MinPoint.X, 4));
            w.WriteNumberValue(Math.Round(margins.MinPoint.Y, 4));
            w.WriteNumberValue(Math.Round(margins.MaxPoint.X, 4));
            w.WriteNumberValue(Math.Round(margins.MaxPoint.Y, 4));
            w.WriteEndArray();
            w.WriteNumber("plot_rotation_degrees", Rotation(layout.PlotRotation));
            w.WriteString("paper_units", layout.PlotPaperUnits == PlotPaperUnit.Inches ? "inches" : layout.PlotPaperUnits == PlotPaperUnit.Pixels ? "pixels" : "mm");
            w.WriteEndObject();
        }

        private static int Rotation(PlotRotation rotation)
        {
            switch (rotation)
            {
                case PlotRotation.Degrees090: return 90;
                case PlotRotation.Degrees180: return 180;
                case PlotRotation.Degrees270: return 270;
                default: return 0;
            }
        }

        // ---------------------------------------------------------------------
        // A viewport
        // ---------------------------------------------------------------------

        /// <summary>
        /// A viewport in a layout's own block, aimed, at an exact scale, twisted,
        /// clipped to an outline when asked, with its annotation scale, and locked.
        /// The view is set from numbers (centre, twist, scale), not by zooming
        /// through it, so it needs no model space inside it and nothing on screen.
        /// </summary>
        public static RunResult AddViewport(Document doc, Database db, Transaction tr, RunArgs args)
        {
            var sheetName = args.Text("layout").Trim();
            var centre = args.Numbers("paper_centre");
            var width = args.Number("paper_width");
            var height = args.Number("paper_height");
            var look = args.Numbers("look_at");
            var twist = args.Number("twist", 0.0);
            var ratio = args.Number("scale_ratio");
            var locked = args.Flag("locked", true);
            var clipHandle = args.Text("clip_handle").Trim();
            var clipFlat = args.Numbers("clip_outline");
            var annotation = args.Text("annotation_scale").Trim();

            if (centre.Length < 2) throw new RunRefusal("The operation needs 'paper_centre' as [x, y].");
            if (look.Length < 2) throw new RunRefusal("The operation needs 'look_at' as [x, y].");
            if (!(width > 0) || !(height > 0)) throw new RunRefusal("A viewport needs a width and a height above zero on the paper.");
            if (!(ratio > 0) || double.IsInfinity(ratio)) throw new RunRefusal("A viewport needs a scale above zero.");
            if (clipHandle.Length > 0 && clipFlat.Length > 0) throw new RunRefusal("Clip to an outline or to an object, not both.");

            var layouts = Layouts(db, tr);
            Layout sheet;
            if (sheetName.Length == 0)
            {
                sheetName = LayoutManager.Current.CurrentLayout;
            }
            var entry = layouts.FirstOrDefault(p => string.Equals(p.Key, sheetName, StringComparison.OrdinalIgnoreCase));
            if (entry.Key == null)
                throw new RunRefusal("This drawing has no layout named '" + sheetName + "'. Layouts: " + Names(layouts) + ".");
            sheet = (Layout)tr.GetObject(entry.Value, OpenMode.ForRead);
            if (sheet.ModelType) throw new RunRefusal("Model space is not a sheet. Name the layout the viewport goes on.");
            sheetName = sheet.LayoutName;
            var blockId = sheet.BlockTableRecordId;

            List<(double x, double y)>? outline = null;
            if (clipFlat.Length > 0)
            {
                outline = SheetMath.Outline(clipFlat, out var refusal);
                if (outline == null) throw new RunRefusal(refusal ?? "That clip outline is not a shape.");
            }
            ObjectId clipId = ObjectId.Null;
            if (clipHandle.Length > 0)
            {
                clipId = RunDrawing.IdOf(db, clipHandle);
                var shape = tr.GetObject(clipId, OpenMode.ForRead);
                if (!(shape is Entity owned) || owned.OwnerId != blockId)
                    throw new RunRefusal(clipHandle + " is not on the sheet '" + sheetName + "'. Draw the clip outline on that sheet, in paper space.");
                var closed = shape is Region || (shape is Curve curve && curve.Closed);
                if (!closed || shape is Viewport)
                    throw new RunRefusal(clipHandle + " is " + RunDrawing.Kind(shape) + ". A viewport is clipped to a closed polyline, circle, ellipse, spline or region.");
            }

            // The annotation scale is found now and only made at the end, after every
            // refusal: the drawing's scale list is not trusted to roll back.
            AnnotationScale? annotationScale = null;
            string? scaleToMake = null;
            if (annotation.Length > 0)
            {
                annotationScale = FindScale(db, annotation, ratio);
                if (annotationScale == null)
                {
                    if (!string.Equals(annotation, SheetMath.ScaleName(ratio), StringComparison.OrdinalIgnoreCase))
                        throw new RunRefusal("This drawing has no annotation scale called '" + annotation + "'. Use the viewport's own scale, or one autocad_list_annotation_scales shows.");
                    scaleToMake = SheetMath.ScaleName(ratio);
                }
            }

            // On screen first, before anything in the layout is opened to write:
            // AutoCAD turns a viewport on in the sheet that is current.
            MakeCurrent(sheetName);

            var notes = new List<(string key, string value)>();
            var space = (BlockTableRecord)tr.GetObject(blockId, OpenMode.ForWrite);
            var vp = new Viewport();
            vp.SetDatabaseDefaults(db);
            vp.CenterPoint = new Point3d(centre[0], centre[1], 0.0);
            vp.Width = width;
            vp.Height = height;
            space.AppendEntity(vp);
            tr.AddNewlyCreatedDBObject(vp, true);
            RunDrawing.Style(vp, db, tr, args);

            vp.ViewDirection = Vector3d.ZAxis;
            vp.ViewTarget = Point3d.Origin;
            vp.TwistAngle = twist * Math.PI / 180.0;
            SheetMath.ViewCentre(look[0], look[1], twist, out var dx, out var dy);
            vp.ViewCenter = new Point2d(dx, dy);
            vp.StandardScale = StandardScaleType.CustomScale;
            vp.CustomScale = ratio;

            string clippedTo = "";
            if (outline != null)
            {
                var border = new Polyline();
                border.SetDatabaseDefaults(db);
                for (var i = 0; i < outline.Count; i++) border.AddVertexAt(i, new Point2d(outline[i].x, outline[i].y), 0, 0, 0);
                border.Closed = true;
                border.Layer = vp.Layer;
                space.AppendEntity(border);
                tr.AddNewlyCreatedDBObject(border, true);
                clipId = border.ObjectId;
                clippedTo = border.Handle.ToString();
            }
            else if (!clipId.IsNull)
            {
                clippedTo = clipHandle.ToUpperInvariant();
            }
            if (!clipId.IsNull)
            {
                vp.NonRectClipEntityId = clipId;
                vp.NonRectClipOn = true;
            }

            vp.On = true;
            vp.Locked = locked;

            var scaleAdded = false;
            if (scaleToMake != null)
            {
                SheetMath.ScaleUnits(ratio, out var paperUnits, out var drawingUnits);
                var collection = db.ObjectContextManager.GetContextCollection(Collection);
                collection.AddContext(new AnnotationScale { Name = scaleToMake, PaperUnits = paperUnits, DrawingUnits = drawingUnits });
                annotationScale = FindScale(db, scaleToMake, ratio);
                scaleAdded = annotationScale != null;
                if (annotationScale == null) notes.Add(("annotation_scale_note", "AutoCAD did not add the scale " + scaleToMake + " to the drawing's list, so the viewport keeps its own annotation scale."));
            }
            if (annotationScale != null) vp.AnnotationScale = annotationScale;

            PluginRunner.AfterCommit(() => doc.Editor.Regen());

            var handle = vp.Handle.ToString();
            var layer = vp.Layer;
            var scaleSet = vp.CustomScale;
            var annotationName = annotationScale?.Name ?? "";
            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", handle);
                w.WriteString("layout", sheetName);
                w.WriteString("layer", layer);
                w.WriteNumber("scale_set", Math.Round(scaleSet, 9));
                w.WriteBoolean("locked", locked);
                w.WriteStartArray("view_centre");
                w.WriteNumberValue(Math.Round(dx, 6));
                w.WriteNumberValue(Math.Round(dy, 6));
                w.WriteEndArray();
                w.WriteBoolean("clipped", clippedTo.Length > 0);
                if (clippedTo.Length > 0) w.WriteString("clip_handle", clippedTo);
                if (annotationName.Length > 0) w.WriteString("annotation_scale", annotationName);
                if (scaleAdded) w.WriteBoolean("annotation_scale_added", true);
                foreach (var (key, value) in notes) w.WriteString(key, value);
            });
        }

        /// <summary>An annotation scale of the drawing by name, else one at the same ratio.</summary>
        private static AnnotationScale? FindScale(Database db, string name, double ratio)
        {
            var collection = db.ObjectContextManager.GetContextCollection(Collection);
            AnnotationScale? sameRatio = null;
            foreach (ObjectContext context in collection)
            {
                if (!(context is AnnotationScale scale)) continue;
                if (string.Equals(scale.Name, name, StringComparison.OrdinalIgnoreCase)) return scale;
                if (sameRatio == null && SheetMath.SameScale(scale.PaperUnits, scale.DrawingUnits, ratio)
                    && string.Equals(name, SheetMath.ScaleName(ratio), StringComparison.OrdinalIgnoreCase))
                    sameRatio = scale;
            }
            return sameRatio;
        }

        // ---------------------------------------------------------------------
        // The sheet on screen, for autocad_status (#39)
        // ---------------------------------------------------------------------

        /// <summary>The current layout, how many objects its block holds and how many of them are viewports.</summary>
        public static RunResult ActiveSheet(Database db, Transaction tr)
        {
            var name = LayoutManager.Current.CurrentLayout;
            var id = LayoutManager.Current.GetLayoutId(name);
            var layout = (Layout)tr.GetObject(id, OpenMode.ForRead);
            var block = (BlockTableRecord)tr.GetObject(layout.BlockTableRecordId, OpenMode.ForRead);
            var entities = 0;
            var viewports = 0;
            var viewportClass = Autodesk.AutoCAD.Runtime.RXObject.GetClass(typeof(Viewport));
            foreach (ObjectId item in block)
            {
                entities++;
                if (item.ObjectClass.IsDerivedFrom(viewportClass)) viewports++;
            }
            return RunResult.Done(w =>
            {
                w.WriteString("layout", layout.LayoutName);
                w.WriteBoolean("model", layout.ModelType);
                w.WriteNumber("entities", entities);
                w.WriteNumber("viewports", viewports);
            });
        }

        // ---------------------------------------------------------------------
        // Helpers
        // ---------------------------------------------------------------------

        /// <summary>
        /// Puts a sheet on screen without AutoCAD's own default viewport: Heron cuts the
        /// viewports itself, at a real scale, so LAYOUTCREATEVIEWPORT is off while the
        /// sheet is first opened, and put back straight after.
        /// </summary>
        internal static void MakeCurrent(string name)
        {
            var manager = LayoutManager.Current;
            if (string.Equals(manager.CurrentLayout, name, StringComparison.OrdinalIgnoreCase)) return;
            var was = AcApp.GetSystemVariable("LAYOUTCREATEVIEWPORT");
            try
            {
                AcApp.SetSystemVariable("LAYOUTCREATEVIEWPORT", 0);
                manager.CurrentLayout = name;
            }
            finally
            {
                try
                {
                    AcApp.SetSystemVariable("LAYOUTCREATEVIEWPORT", was);
                }
                catch (System.Exception ex)
                {
                    HeronLog.Error("Put LAYOUTCREATEVIEWPORT back", ex);
                }
            }
        }

        private static Dictionary<string, ObjectId> Layouts(Database db, Transaction tr)
        {
            var found = new Dictionary<string, ObjectId>(StringComparer.OrdinalIgnoreCase);
            var dictionary = (DBDictionary)tr.GetObject(db.LayoutDictionaryId, OpenMode.ForRead);
            foreach (DBDictionaryEntry item in dictionary) found[item.Key] = item.Value;
            return found;
        }

        private static string Names(Dictionary<string, ObjectId> layouts)
        {
            var names = layouts.Keys.Where(k => !string.Equals(k, "Model", StringComparison.OrdinalIgnoreCase)).OrderBy(k => k, StringComparer.OrdinalIgnoreCase).ToList();
            return names.Count == 0 ? "none" : string.Join(", ", names);
        }
    }
}
