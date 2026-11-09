using System;
using System.Collections.Generic;
using System.IO;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;
using DbLight = Autodesk.AutoCAD.DatabaseServices.Light;
using DbMaterial = Autodesk.AutoCAD.DatabaseServices.Material;
using Gi = Autodesk.AutoCAD.GraphicsInterface;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Lights and materials for a render (D-42). COM has no light object and
    /// cannot set a material's colour, maps or glow, so both are made here
    /// through the .NET API: one object, every setting, one transaction.
    /// </summary>
    internal static class RenderSetup
    {
        // AutoCAD refuses a spotlight cone wider than this.
        private const double ConeMax = 160.0 * Math.PI / 180.0;

        public static RunResult AddLight(Database db, Transaction tr, RunArgs args)
        {
            var kind = args.Text("kind", "point").Trim().ToLowerInvariant();
            Gi.DrawableType type;
            string prefix;
            switch (kind)
            {
                case "point": type = Gi.DrawableType.PointLight; prefix = "Pointlight"; break;
                case "spot": type = Gi.DrawableType.SpotLight; prefix = "Spotlight"; break;
                case "web": type = Gi.DrawableType.WebLight; prefix = "Weblight"; break;
                case "distant": type = Gi.DrawableType.DistantLight; prefix = "Distantlight"; break;
                default: throw new RunRefusal("'" + kind + "' is not a kind of light: point, spot, web or distant.");
            }

            var position = Point(args, "position");
            var intensity = args.Number("intensity");
            if (!(intensity > 0)) throw new RunRefusal("The intensity must be above zero.");
            PhysicalIntensityMethod method;
            switch (args.Text("intensity_method", "peak_intensity"))
            {
                case "peak_intensity": method = PhysicalIntensityMethod.PeakIntensity; break;
                case "flux": method = PhysicalIntensityMethod.Flux; break;
                case "illuminance": method = PhysicalIntensityMethod.Illuminance; break;
                default: throw new RunRefusal("The intensity unit must be cd, lm or lux.");
            }

            var target = position;
            var aim = -Vector3d.ZAxis;
            if (type != Gi.DrawableType.PointLight)
            {
                target = Point(args, "target");
                aim = target - position;
                if (aim.Length < 1e-12) throw new RunRefusal("The light's target is on the light itself, so it points nowhere.");
                aim = aim.GetNormal();
            }

            double hotspot = 0, falloff = 0;
            if (type == Gi.DrawableType.SpotLight)
            {
                hotspot = args.Number("hotspot", 44.0 * Math.PI / 180.0);
                falloff = args.Number("falloff", 50.0 * Math.PI / 180.0);
                if (!(hotspot > 0) || falloff < hotspot || falloff > ConeMax)
                    throw new RunRefusal("A spot's hotspot must be above zero and its falloff between the hotspot and 160 degrees.");
            }

            var web = args.Text("web_file").Trim();
            if (type == Gi.DrawableType.WebLight && (web.Length == 0 || !File.Exists(web)))
                throw new RunRefusal("A web light needs its .ies file, and there is none at '" + web + "'.");

            double[] rgb = args.Numbers("rgb");
            if (args.Has("rgb") && (rgb.Length != 3 || Array.Exists(rgb, v => v < 0 || v > 255)))
                throw new RunRefusal("The light's rgb must be three numbers 0-255.");
            var kelvin = args.Number("kelvin", 3000.0);
            if (kelvin < 1000 || kelvin > 20000) throw new RunRefusal("The colour temperature must be 1000-20000 K.");

            var space = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
            var used = LightNames(space, tr);
            var name = args.Text("name").Trim();
            if (name.Length == 0) name = FreeName(prefix, used);
            else if (used.Contains(name))
                throw new RunRefusal("There is already a light called '" + name + "' in model space. Give another name, or leave it out.");

            var light = new DbLight();
            light.SetDatabaseDefaults(db);
            space.AppendEntity(light);
            tr.AddNewlyCreatedDBObject(light, true);
            light.LightType = type;
            light.Name = name;
            light.Position = position;
            if (type == Gi.DrawableType.SpotLight || type == Gi.DrawableType.WebLight)
            {
                light.TargetLocation = target;
                light.HasTarget = true;
            }
            if (type == Gi.DrawableType.DistantLight) light.Direction = aim;
            if (type == Gi.DrawableType.SpotLight) light.SetHotspotAndFalloff(hotspot, falloff);
            if (type == Gi.DrawableType.WebLight) light.WebFile = web;

            light.PhysicalIntensityMethod = method;
            light.PhysicalIntensity = intensity;
            light.LampColorType = LampColorType.Kelvin;
            if (rgb.Length == 3)
            {
                // A coloured light: a daylight-white lamp behind a filter of that colour.
                light.LampColorTemp = 6500.0;
                light.LightColor = Color.FromRgb((byte)rgb[0], (byte)rgb[1], (byte)rgb[2]);
            }
            else
            {
                light.LampColorTemp = kelvin;
            }
            light.IsOn = args.Flag("on", true);
            var shadow = light.Shadow;
            if (shadow != null)
            {
                shadow.ShadowsOn = args.Flag("shadows", true);
                light.Shadow = shadow;
            }

            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", light.Handle.ToString());
                w.WriteString("name", light.Name);
                w.WriteString("kind", kind);
                w.WriteNumber("intensity", Math.Round(light.PhysicalIntensity, 6));
                w.WriteBoolean("on", light.IsOn);
                if (rgb.Length == 3) RunDrawing.WriteNumbers(w, "rgb", new[] { (int)rgb[0], (int)rgb[1], (int)rgb[2] });
                else w.WriteNumber("kelvin", Math.Round(light.LampColorTemp, 3));
                if (type == Gi.DrawableType.SpotLight)
                {
                    w.WriteNumber("hotspot_degrees", Math.Round(light.HotspotAngle * 180.0 / Math.PI, 3));
                    w.WriteNumber("falloff_degrees", Math.Round(light.FalloffAngle * 180.0 / Math.PI, 3));
                }
                if (type != Gi.DrawableType.PointLight) RunDrawing.WritePoint(w, "target", target.X, target.Y, target.Z);
                if (web.Length > 0) w.WriteString("web_file", light.WebFile);
                RunDrawing.Style(light, db, tr, args, w);
            });
        }

        public static RunResult CreateMaterial(Database db, Transaction tr, RunArgs args)
        {
            var name = args.Text("name").Trim();
            if (name.Length == 0) throw new RunRefusal("A material needs a name.");
            try
            {
                SymbolUtilityServices.ValidateSymbolName(name, false);
            }
            catch (AcException)
            {
                throw new RunRefusal("'" + name + "' cannot be a material name.");
            }

            var texture = ImageArg(args, "texture");
            var bump = ImageArg(args, "bump");
            var tile = TileSize(args, texture.Length > 0 || bump.Length > 0);

            var materials = (DBDictionary)tr.GetObject(db.MaterialDictionaryId, OpenMode.ForRead);
            var existing = ObjectId.Null;
            foreach (DBDictionaryEntry entry in materials)
            {
                if (!string.Equals(entry.Key, name, StringComparison.OrdinalIgnoreCase)) continue;
                existing = entry.Value;
                name = entry.Key;
                break;
            }

            DbMaterial material;
            var replaced = !existing.IsNull;
            if (replaced)
            {
                if (!args.Flag("replace", false))
                    throw new RunRefusal("There is already a material called '" + name + "'. Pass replace=true to change it "
                        + "(everything using it changes too), or give another name.");
                material = (DbMaterial)tr.GetObject(existing, OpenMode.ForWrite);
            }
            else
            {
                material = new DbMaterial { Name = name, Mode = Gi.Mode.Realistic };
                materials.UpgradeOpen();
                materials.SetAt(name, material);
                tr.AddNewlyCreatedDBObject(material, true);
            }

            // Only what was asked for is written, and only those channels switched on:
            // a channel switched on with nothing set could, say, make it see-through.
            var set = new List<string>();
            var channels = material.ChannelFlags;
            if (args.Has("description"))
            {
                material.Description = args.Text("description");
                set.Add("description");
            }
            if (args.Flag("metallic", false))
            {
                material.IlluminationModel = Gi.IlluminationModel.MetalShader;
                set.Add("metallic");
            }

            var rgb = args.Numbers("diffuse_rgb");
            if (args.Has("diffuse_rgb") && (rgb.Length != 3 || Array.Exists(rgb, v => v < 0 || v > 255)))
                throw new RunRefusal("diffuse_rgb must be three numbers 0-255.");
            if (rgb.Length == 3 || texture.Length > 0)
            {
                var diffuse = material.Diffuse;
                var colour = diffuse.Color ?? new Gi.MaterialColor();
                var map = diffuse.Map ?? new Gi.MaterialMap();
                if (rgb.Length == 3)
                {
                    colour = new Gi.MaterialColor(Gi.Method.Override, 1.0, new EntityColor((byte)rgb[0], (byte)rgb[1], (byte)rgb[2]));
                    set.Add("diffuse colour");
                }
                if (texture.Length > 0)
                {
                    map = ImageMap(texture, 1.0, tile);
                    set.Add("texture");
                }
                else if (replaced && diffuse.Map != null && diffuse.Map.Texture != null)
                {
                    // A colour with no image is a plain colour. The old image would
                    // otherwise stay and cover the new colour completely (Luxury
                    // Suite 2, 2026-11-09: ivory asked, terracotta plaster image kept).
                    map = new Gi.MaterialMap();
                    set.Add("texture cleared");
                }
                material.Diffuse = new Gi.MaterialDiffuseComponent(colour, map);
                channels |= Gi.ChannelFlags.UseDiffuse;
            }
            if (args.Has("glossiness"))
            {
                var specular = material.Specular;
                material.Specular = new Gi.MaterialSpecularComponent(
                    specular.Color ?? new Gi.MaterialColor(), specular.Map ?? new Gi.MaterialMap(), Share(args, "glossiness"));
                channels |= Gi.ChannelFlags.UseSpecular;
                set.Add("glossiness");
            }
            if (args.Has("reflectivity"))
            {
                material.Reflectivity = Share(args, "reflectivity");
                channels |= Gi.ChannelFlags.UseReflection;
                set.Add("reflectivity");
            }
            if (args.Has("opacity"))
            {
                var opacity = material.Opacity;
                material.Opacity = new Gi.MaterialOpacityComponent(Share(args, "opacity"), opacity.Map ?? new Gi.MaterialMap());
                channels |= Gi.ChannelFlags.UseOpacity;
                set.Add("transparency");
            }
            if (args.Has("refraction_index"))
            {
                var index = args.Number("refraction_index");
                if (index < 1 || index > 5) throw new RunRefusal("The refraction index must be 1-5 (glass 1.5).");
                var refraction = material.Refraction;
                material.Refraction = new Gi.MaterialRefractionComponent(index, refraction.Map ?? new Gi.MaterialMap());
                channels |= Gi.ChannelFlags.UseRefraction;
                set.Add("refraction");
            }
            if (args.Has("luminance"))
            {
                var luminance = args.Number("luminance");
                if (luminance < 0) throw new RunRefusal("The luminance cannot be below zero.");
                material.LuminanceMode = Gi.LuminanceMode.Luminance;
                material.Luminance = luminance;
                set.Add("luminance");
            }
            if (bump.Length > 0)
            {
                material.Bump = ImageMap(bump, Share(args, "bump_amount", 0.3), tile);
                channels |= Gi.ChannelFlags.UseBump;
                set.Add("bump");
            }
            if (tile != null) set.Add("texture size");
            material.ChannelFlags = channels;

            return RunResult.Done(w =>
            {
                w.WriteBoolean(replaced ? "replaced" : "created", true);
                w.WriteString("name", material.Name);
                w.WriteString("handle", material.Handle.ToString());
                w.WriteStartArray("set");
                foreach (var item in set) w.WriteStringValue(item);
                w.WriteEndArray();
                if (tile != null)
                {
                    w.WriteStartArray("texture_size");
                    w.WriteNumberValue(1.0 / tile[0]);
                    w.WriteNumberValue(1.0 / tile[5]);
                    w.WriteEndArray();
                }
            });
        }

        private static Point3d Point(RunArgs args, string name)
        {
            var values = args.Numbers(name);
            if (values.Length != 3) throw new RunRefusal("The operation needs '" + name + "' as [x, y, z].");
            return new Point3d(values[0], values[1], values[2]);
        }

        /// <summary>A 0-1 share, refused outside that range.</summary>
        private static double Share(RunArgs args, string name, double? fallback = null)
        {
            var value = args.Number(name, fallback);
            if (value < 0 || value > 1) throw new RunRefusal("'" + name + "' must be between 0 and 1.");
            return value;
        }

        /// <summary>An image path that is there, or empty when none was given.</summary>
        private static string ImageArg(RunArgs args, string name)
        {
            var path = args.Text(name).Trim();
            if (path.Length > 0 && !File.Exists(path))
                throw new RunRefusal("There is no image at '" + path + "' for the " + name + ".");
            return path;
        }

        /// <summary>
        /// The map transform for texture_size / texture_height, or null when no
        /// size was given (AutoCAD's identity: one tile per drawing unit).
        /// </summary>
        private static double[]? TileSize(RunArgs args, bool hasImage)
        {
            if (!args.Has("texture_size"))
            {
                if (args.Has("texture_height")) throw new RunRefusal("texture_height needs texture_size (the tile's width) too.");
                return null;
            }
            if (!hasImage) throw new RunRefusal("texture_size sizes a texture or bump image: give one.");
            double? height = args.Has("texture_height") ? args.Number("texture_height") : (double?)null;
            var why = TextureScale.Matrix(args.Number("texture_size"), height, out var values);
            if (why != null) throw new RunRefusal(why);
            return values;
        }

        /// <summary>
        /// An image map. Projection, tiling and auto-transform keep AutoCAD's
        /// defaults, so the texture follows the object's own mapping
        /// (MATERIALMAP). With a tile size, the map transform is scaled so one
        /// image covers that many drawing units (TextureScale); without one it
        /// stays the identity, one image per drawing unit.
        /// </summary>
        private static Gi.MaterialMap ImageMap(string path, double blend, double[]? tile)
        {
            var image = new Gi.ImageFileTexture { SourceFileName = path };
            var mapper = new Gi.Mapper();
            if (tile != null)
                mapper = new Gi.Mapper(mapper.Projection, mapper.UTiling, mapper.VTiling, mapper.AutoTransform, new Matrix3d(tile));
            return new Gi.MaterialMap(Gi.Source.File, image, blend, mapper);
        }

        private static HashSet<string> LightNames(BlockTableRecord space, Transaction tr)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var lightClass = RXObject.GetClass(typeof(DbLight));
            foreach (ObjectId id in space)
            {
                if (!id.ObjectClass.IsDerivedFrom(lightClass)) continue;
                if (tr.GetObject(id, OpenMode.ForRead) is DbLight light && !string.IsNullOrEmpty(light.Name)) names.Add(light.Name);
            }
            return names;
        }

        private static string FreeName(string prefix, HashSet<string> used)
        {
            for (var i = 1; ; i++)
            {
                var name = prefix + i;
                if (!used.Contains(name)) return name;
            }
        }
    }
}
