using System;
using System.Collections.Generic;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;
using DbLight = Autodesk.AutoCAD.DatabaseServices.Light;
using Gi = Autodesk.AutoCAD.GraphicsInterface;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Setting a render up from the chat (D-86, D-87): the visual style read
    /// back, a named perspective camera, the sun's date and time, and the
    /// lights listed and switched. Heron never renders: the modeller presses
    /// Render. COM has no call for any of these.
    /// </summary>
    internal static class RenderView
    {
        /// <summary>Read: the active viewport's visual style, and whether it looks in perspective.</summary>
        public static RunResult CurrentView(Document doc, Transaction tr)
        {
            var db = doc.Database;
            var styles = StyleNames(db, tr);
            string? onScreen = null, saved = null;
            bool perspective;
            double lens;
            using (var view = doc.Editor.GetCurrentView())
            {
                onScreen = StyleName(styles, view.VisualStyleId);
                perspective = view.PerspectiveEnabled;
                lens = view.LensLength;
            }
            var active = doc.Editor.ActiveViewportId;
            if (!active.IsNull && !active.IsErased)
            {
                var record = tr.GetObject(active, OpenMode.ForRead);
                if (record is AbstractViewTableRecord tile) saved = StyleName(styles, tile.VisualStyleId);
                else if (record is Viewport viewport) saved = StyleName(styles, viewport.VisualStyleId);
            }
            return RunResult.Done(w =>
            {
                WriteText(w, "visual_style", onScreen ?? saved);
                WriteText(w, "visual_style_on_screen", onScreen);
                WriteText(w, "visual_style_saved", saved);
                w.WriteBoolean("model_tab", db.TileMode);
                w.WriteBoolean("perspective", perspective);
                if (perspective) w.WriteNumber("lens_mm", Math.Round(lens, 3));
            });
        }

        /// <summary>
        /// Change: a named perspective view at an eye point, looking at a
        /// target, through a lens. Written as a view record with perspective on
        /// and the lens set (never DVIEW, which waits for picks). It can also be
        /// put on screen, so the modeller sees it and presses Render.
        /// </summary>
        public static RunResult AddCameraView(Document doc, Transaction tr, RunArgs args)
        {
            var db = doc.Database;
            if (!db.TileMode) throw new RunRefusal("A camera view looks at the model: switch to the Model tab first.");
            var name = args.Text("name").Trim();
            if (name.Length == 0) throw new RunRefusal("A camera view needs a name.");
            try
            {
                SymbolUtilityServices.ValidateSymbolName(name, false);
            }
            catch (AcException)
            {
                throw new RunRefusal("'" + name + "' cannot be a view name.");
            }

            var eye = Point(args, "eye");
            var target = Point(args, "target");
            var toEye = eye - target;
            if (toEye.Length < 1e-9) throw new RunRefusal("The eye and the target are the same point, so the camera looks nowhere.");
            var lens = args.Number("lens", 50.0);
            var why = CameraLens.Check(lens);
            if (why != null) throw new RunRefusal(why);

            double aspect;
            using (var current = doc.Editor.GetCurrentView())
                aspect = current.Height > 0 ? current.Width / current.Height : double.NaN;
            aspect = CameraLens.Aspect(aspect);
            CameraLens.Field(toEye.Length, lens, aspect, out var width, out var height);

            var views = (ViewTable)tr.GetObject(db.ViewTableId, OpenMode.ForRead);
            ViewTableRecord? record = null;
            foreach (ObjectId id in views)
            {
                if (id.IsErased) continue;
                var found = (ViewTableRecord)tr.GetObject(id, OpenMode.ForRead);
                if (!string.Equals(found.Name, name, StringComparison.OrdinalIgnoreCase)) continue;
                record = found;
                break;
            }
            var replaced = record != null;
            if (record != null)
            {
                if (record.IsPaperspaceView)
                    throw new RunRefusal("'" + record.Name + "' is a layout's view (paper space), not a camera. Give the camera another name.");
                if (!args.Flag("replace", false))
                    throw new RunRefusal("This drawing already has a view called '" + record.Name + "'. Pass replace=true to move it, or give another name.");
                record.UpgradeOpen();
            }
            else
            {
                record = new ViewTableRecord { Name = name };
                views.UpgradeOpen();
                views.Add(record);
                tr.AddNewlyCreatedDBObject(record, true);
            }
            Aim(record, eye, target, lens, width, height);

            var shown = false;
            if (args.Flag("look_through", true))
            {
                // A copy that is not in the drawing: the record itself is still open in the transaction.
                using (var look = new ViewTableRecord())
                {
                    Aim(look, eye, target, lens, width, height);
                    doc.Editor.SetCurrentView(look);
                }
                shown = true;
            }

            var saved = record;
            return RunResult.Done(w =>
            {
                w.WriteBoolean(replaced ? "replaced" : "created", true);
                w.WriteString("name", saved.Name);
                w.WriteString("handle", saved.Handle.ToString());
                RunDrawing.WritePoint(w, "eye", eye.X, eye.Y, eye.Z);
                RunDrawing.WritePoint(w, "target", target.X, target.Y, target.Z);
                w.WriteNumber("lens_mm", Math.Round(saved.LensLength, 3));
                w.WriteBoolean("perspective", saved.PerspectiveEnabled);
                w.WriteNumber("field_of_view_degrees", Math.Round(CameraLens.FieldOfViewDegrees(lens), 2));
                w.WriteNumber("distance", Math.Round(toEye.Length, 6));
                w.WriteNumber("view_width", Math.Round(saved.Width, 6));
                w.WriteNumber("view_height", Math.Round(saved.Height, 6));
                w.WriteBoolean("on_screen", shown);
            });
        }

        /// <summary>Change: the active viewport's sun gets a date, a clock time and daylight saving. Made if it has none.</summary>
        public static RunResult SetSun(Document doc, Transaction tr, RunArgs args)
        {
            var vport = ActiveTile(doc, tr);
            Sun sun;
            var made = false;
            if (vport.SunId.IsNull)
            {
                vport.UpgradeOpen();
                sun = new Sun();
                vport.SetSun(sun);
                tr.AddNewlyCreatedDBObject(sun, true);
                made = true;
            }
            else
            {
                sun = (Sun)tr.GetObject(vport.SunId, OpenMode.ForWrite);
            }

            var why = SunClock.Compose(sun.DateTime, Whole(args, "year"), Whole(args, "month"), Whole(args, "day"),
                Whole(args, "hour"), Whole(args, "minute"), out var when);
            if (why != null) throw new RunRefusal(why);
            if (args.Has("year") || args.Has("hour")) sun.DateTime = when;
            if (args.Has("daylight_saving")) sun.IsDaylightSavingsOn = args.Flag("daylight_saving", false);

            return RunResult.Done(w =>
            {
                w.WriteBoolean("sun_made", made);
                w.WritePropertyName("sun");
                WriteSun(w, sun);
            });
        }

        /// <summary>Read: every light in model space and inside block definitions, and the sun of the active viewport.</summary>
        public static RunResult ListLights(Document doc, Transaction tr)
        {
            var found = Lights(doc.Database, tr);
            Sun? sun = null;
            string? noSun = null;
            if (!doc.Database.TileMode) noSun = "The sun is read on the Model tab; this is a layout.";
            else
            {
                var vport = ActiveTile(doc, tr);
                if (vport.SunId.IsNull) noSun = "This viewport has no sun yet (it is made the first time the sun is set or switched on).";
                else sun = (Sun)tr.GetObject(vport.SunId, OpenMode.ForRead);
            }
            return RunResult.Done(w =>
            {
                w.WriteNumber("count", found.Count);
                w.WriteStartArray("lights");
                foreach (var light in found) WriteLight(w, light, tr);
                w.WriteEndArray();
                if (sun != null)
                {
                    w.WritePropertyName("sun");
                    WriteSun(w, sun);
                }
                else
                {
                    w.WriteNull("sun");
                    w.WriteString("sun_note", noSun);
                }
            });
        }

        /// <summary>Change: lights switched on or off, by handle or name; all of them, or none if one is not found.</summary>
        public static RunResult SwitchLights(Database db, Transaction tr, RunArgs args)
        {
            var found = Lights(db, tr);
            var tags = new List<LightTag>();
            foreach (var light in found) tags.Add(new LightTag(light.Light.Handle.ToString(), light.Light.Name));

            var all = args.Text("all").Trim().ToLowerInvariant();
            var on = new List<int>();
            var off = new List<int>();
            if (all.Length > 0)
            {
                if (all != "on" && all != "off") throw new RunRefusal("all must be 'on' or 'off'.");
                if (found.Count == 0) throw new RunRefusal(LightPick.Available(tags));
                for (var i = 0; i < found.Count; i++) (all == "on" ? on : off).Add(i);
            }
            else
            {
                var why = LightPick.Resolve(tags, args.Texts("on"), out on) ?? LightPick.Resolve(tags, args.Texts("off"), out off);
                if (why != null) throw new RunRefusal(why);
                foreach (var index in on)
                    if (off.Contains(index))
                        throw new RunRefusal("'" + tags[index].Name + "' (" + tags[index].Handle + ") is asked to go both on and off.");
                if (on.Count == 0 && off.Count == 0) throw new RunRefusal("Say which lights to switch on or off.");
            }

            var changed = new List<FoundLight>();
            foreach (var (indexes, state) in new[] { (on, true), (off, false) })
            {
                foreach (var index in indexes)
                {
                    var light = found[index].Light;
                    if (light.IsOn == state) continue;
                    light.UpgradeOpen();
                    light.IsOn = state;
                    changed.Add(found[index]);
                }
            }

            return RunResult.Done(w =>
            {
                w.WriteNumber("asked_on", on.Count);
                w.WriteNumber("asked_off", off.Count);
                w.WriteNumber("changed", changed.Count);
                w.WriteStartArray("lights");
                foreach (var light in changed) WriteLight(w, light, tr);
                w.WriteEndArray();
            });
        }

        private sealed class FoundLight
        {
            public FoundLight(DbLight light, string block, int inserts)
            {
                Light = light;
                Block = block;
                Inserts = inserts;
            }

            public DbLight Light { get; }

            /// <summary>Empty for model space, else the block definition it is in.</summary>
            public string Block { get; }

            public int Inserts { get; }
        }

        /// <summary>Model space first, then every block definition that holds a light (not layouts, not xrefs).</summary>
        private static List<FoundLight> Lights(Database db, Transaction tr)
        {
            var found = new List<FoundLight>();
            var lightClass = RXObject.GetClass(typeof(DbLight));
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var modelId = SymbolUtilityServices.GetBlockModelSpaceId(db);
            Collect(found, (BlockTableRecord)tr.GetObject(modelId, OpenMode.ForRead), "", 0, tr, lightClass);
            foreach (ObjectId id in blocks)
            {
                if (id == modelId || id.IsErased) continue;
                var block = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
                if (block.IsLayout || block.IsFromExternalReference || block.IsDependent) continue;
                Collect(found, block, block.Name, -1, tr, lightClass);
            }
            return found;
        }

        private static void Collect(List<FoundLight> found, BlockTableRecord space, string name, int inserts, Transaction tr, RXClass lightClass)
        {
            var count = inserts;
            foreach (ObjectId id in space)
            {
                if (id.IsErased || !id.ObjectClass.IsDerivedFrom(lightClass)) continue;
                if (count < 0) count = space.GetBlockReferenceIds(true, false).Count;
                found.Add(new FoundLight((DbLight)tr.GetObject(id, OpenMode.ForRead), name, count));
            }
        }

        private static void WriteLight(Utf8JsonWriter w, FoundLight found, Transaction tr)
        {
            var light = found.Light;
            w.WriteStartObject();
            w.WriteString("handle", light.Handle.ToString());
            w.WriteString("name", light.Name);
            w.WriteString("kind", Kind(light.LightType));
            w.WriteBoolean("on", light.IsOn);
            w.WriteNumber("intensity", Math.Round(light.PhysicalIntensity, 6));
            w.WriteString("intensity_unit", Unit(light.PhysicalIntensityMethod));
            if (light.LampColorType == LampColorType.Kelvin) w.WriteNumber("kelvin", Math.Round(light.LampColorTemp, 3));
            w.WriteString("layer", light.Layer);
            if (light.LightType != Gi.DrawableType.DistantLight)
                RunDrawing.WritePoint(w, "position", light.Position.X, light.Position.Y, light.Position.Z);
            if (found.Block.Length > 0)
            {
                w.WriteString("block", found.Block);
                w.WriteNumber("inserts", found.Inserts);
            }
            w.WriteEndObject();
        }

        private static void WriteSun(Utf8JsonWriter w, Sun sun)
        {
            var when = sun.DateTime;
            w.WriteStartObject();
            w.WriteBoolean("on", sun.IsOn);
            w.WriteString("date", when.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture));
            w.WriteString("time", when.ToString("HH:mm:ss", System.Globalization.CultureInfo.InvariantCulture));
            w.WriteBoolean("daylight_saving", sun.IsDaylightSavingsOn);
            // As AutoCAD gives them; their unit is checked live (NEEDS-CHECKING group AE).
            w.WriteNumber("azimuth", Math.Round(sun.Azimuth, 6));
            w.WriteNumber("altitude", Math.Round(sun.Altitude, 6));
            w.WriteNumber("intensity", Math.Round(sun.Intensity, 6));
            w.WriteEndObject();
        }

        /// <summary>The model tab's current viewport, for its sun; a refusal on a layout.</summary>
        private static ViewportTableRecord ActiveTile(Document doc, Transaction tr)
        {
            if (!doc.Database.TileMode) throw new RunRefusal("The sun belongs to a model viewport: switch to the Model tab first.");
            var id = doc.Editor.ActiveViewportId;
            if (id.IsNull) id = doc.Database.CurrentViewportTableRecordId;
            if (id.IsNull || !(tr.GetObject(id, OpenMode.ForRead) is ViewportTableRecord vport))
                throw new RunRefusal("AutoCAD gave no current model viewport. Click in the drawing once, then ask again.");
            return vport;
        }

        private static void Aim(AbstractViewTableRecord view, Point3d eye, Point3d target, double lens, double width, double height)
        {
            view.Target = target;
            view.ViewDirection = eye - target;
            view.CenterPoint = Point2d.Origin;
            view.ViewTwist = 0.0;
            view.Height = height;
            view.Width = width;
            view.LensLength = lens;
            view.PerspectiveEnabled = true;
            view.FrontClipEnabled = false;
            view.BackClipEnabled = false;
        }

        /// <summary>Each visual style's name in the drawing, by its id (the dictionary key is the name AutoCAD shows).</summary>
        private static Dictionary<ObjectId, string> StyleNames(Database db, Transaction tr)
        {
            var names = new Dictionary<ObjectId, string>();
            if (db.VisualStyleDictionaryId.IsNull) return names;
            var styles = (DBDictionary)tr.GetObject(db.VisualStyleDictionaryId, OpenMode.ForRead);
            foreach (DBDictionaryEntry entry in styles) names[entry.Value] = entry.Key;
            return names;
        }

        private static string? StyleName(Dictionary<ObjectId, string> names, ObjectId id) =>
            !id.IsNull && names.TryGetValue(id, out var name) ? name : null;

        private static string Kind(Gi.DrawableType type)
        {
            switch (type)
            {
                case Gi.DrawableType.PointLight: return "point";
                case Gi.DrawableType.SpotLight: return "spot";
                case Gi.DrawableType.WebLight: return "web";
                case Gi.DrawableType.DistantLight: return "distant";
                default: return type.ToString();
            }
        }

        private static string Unit(PhysicalIntensityMethod method)
        {
            switch (method)
            {
                case PhysicalIntensityMethod.Flux: return "lm";
                case PhysicalIntensityMethod.Illuminance: return "lux";
                default: return "cd";
            }
        }

        private static Point3d Point(RunArgs args, string name)
        {
            var values = args.Numbers(name);
            if (values.Length != 3) throw new RunRefusal("The operation needs '" + name + "' as [x, y, z].");
            return new Point3d(values[0], values[1], values[2]);
        }

        private static int? Whole(RunArgs args, string name) => args.Has(name) ? (int?)(int)Math.Round(args.Number(name)) : null;

        private static void WriteText(Utf8JsonWriter w, string name, string? value)
        {
            if (value == null) w.WriteNull(name);
            else w.WriteString(name, value);
        }
    }
}
