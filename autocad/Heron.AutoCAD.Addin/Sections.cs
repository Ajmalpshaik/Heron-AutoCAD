using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// A 3D model cut and looked at in 2D, for a shop drawing (D-95). Both
    /// operations use AutoCAD's own section object (SECTIONPLANE) and its
    /// GenerateSectionGeometry, the call behind "Generate Section / Elevation":
    ///
    /// * flat_views: FLATSHOT / SOLPROF. A section plane is put outside the
    ///   solids for each view (front, top, right...), so it cuts nothing and
    ///   the 2D "background" it gives back is the view, hidden lines removed.
    /// * section_plane: a section plane through the modeller's points, kept in
    ///   the drawing, and its 2D section (cut outlines, hatch, what is seen
    ///   beyond) made as a block.
    ///
    /// Main thread, inside PluginRunner's lock and one transaction: the
    /// temporary section planes are erased in the same transaction, and a
    /// refusal leaves nothing.
    /// </summary>
    internal static class Sections
    {
        private const int MostSources = 1000;
        private const string FlatPrefix = "FLATSHOT-";
        private const string SectionPrefix = "SECTION-";
        private const int CurveSamples = 8;

        public static RunResult FlatViews(Database db, Transaction tr, RunArgs args)
        {
            var handles = args.Texts("handles");
            if (handles.Length == 0) throw new RunRefusal("Give the solids to flatten, by handle.");
            if (handles.Length > MostSources) throw new RunRefusal("At most " + MostSources + " solids at once; flatten them in groups.");
            var solids = handles.Select(h => RunDrawing.Open<Solid3d>(tr, db, h, OpenMode.ForRead, "a 3D solid")).ToList();
            var names = args.Texts("views").Select(n => n.Trim().ToLowerInvariant()).ToArray();
            if (names.Length == 0) names = new[] { "front", "top", "right" };
            foreach (var name in names)
                if (!SectionMath.TryView(name, out _, out _))
                    throw new RunRefusal("'" + name + "' is not a view. Views: " + string.Join(", ", SectionMath.ViewNames) + ".");
            names = names.Select(n => n == "plan" ? "top" : n).ToArray();
            if (names.Distinct().Count() != names.Length) throw new RunRefusal("A view is asked for twice.");
            var at = InsertPoint(args);
            var projection = args.Text("projection", "third").Trim().ToLowerInvariant();
            if (projection != "third" && projection != "first") throw new RunRefusal("projection is 'third' or 'first'.");

            var (low, high) = Box(solids);
            var size = Math.Max(high[0] - low[0], Math.Max(high[1] - low[1], high[2] - low[2]));
            var gap = args.Number("gap", -1);
            if (!(gap > 0)) gap = Math.Max(size * 0.25, 1.0);
            var space = ModelSpace(db, tr);
            var tangents = args.Flag("tangent_edges", false);

            // join: one temporary union of copies, so a solid hides what is behind it.
            var temporary = new List<Entity>();
            List<Entity> sources = solids.Cast<Entity>().ToList();
            if (args.Flag("join", false) && solids.Count > 1)
            {
                var union = (Solid3d)solids[0].Clone();
                foreach (var other in solids.Skip(1))
                {
                    var copy = (Solid3d)other.Clone();
                    try
                    {
                        union.BooleanOperation(BooleanOperationType.BoolUnite, copy);
                    }
                    catch (AcException ex)
                    {
                        union.Dispose();
                        throw new RunRefusal("AutoCAD could not join the solids for one view (" + ex.ErrorStatus + "). Flatten them without join.");
                    }
                    finally
                    {
                        copy.Dispose();
                    }
                }
                space.AppendEntity(union);
                tr.AddNewlyCreatedDBObject(union, true);
                temporary.Add(union);
                sources = new List<Entity> { union };
            }

            var lines = new Dictionary<string, List<Entity>>();
            var extents = new Dictionary<string, double[]>();
            var lying = new SortedSet<string>();
            var empty = new List<string>();
            var dropped = 0;
            foreach (var name in names)
            {
                SectionMath.TryView(name, out var forward, out var up);
                var right = SectionMath.Right(forward, up);
                var origin = SectionMath.OutsidePoint(low, high, forward);
                var found = new List<Entity>();
                var section = NewSection(db, space, tr, origin, right, up, forward, size, cut: false, hatch: false, background: true, tangents);
                try
                {
                    foreach (var source in sources) Generate(section, source, found, cut: false, hatch: false, background: true, tangents, out _);
                }
                finally
                {
                    section.Erase();
                }
                var flat = LayFlat(found, origin, right, up, forward, out var where, ref dropped);
                if (flat.Count == 0)
                {
                    empty.Add(name);
                    continue;
                }
                lying.Add(where.ToString().ToLowerInvariant());
                lines[name] = flat;
                extents[name] = Extents(flat);
            }
            foreach (var entity in temporary) entity.Erase();
            if (lines.Count == 0)
                throw new RunRefusal("AutoCAD gave no lines for any view of these solids. Check they are 3D solids with volume (autocad_solid_properties).");

            var places = SectionMath.Layout(extents, projection, gap);
            // insert_at is the front view's lower-left corner (or, with no front view, the point the views are set out from).
            var frontLow = extents.TryGetValue("front", out var fe) ? new[] { fe[0], fe[1] } : new[] { 0.0, 0.0 };
            var origin0 = new[] { at[0] - frontLow[0], at[1] - frontLow[1], at[2] };
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var prefix = BlockPrefix(args.Text("name"), blocks, FlatPrefix);
            var made = new List<(string view, BlockReference reference, string block, double[] box, int count)>();
            foreach (var name in names.Where(lines.ContainsKey))
            {
                var blockName = prefix + "-" + name.ToUpperInvariant();
                if (blocks.Has(blockName)) throw new RunRefusal("There is already a block called '" + blockName + "'. Give another name.");
                var place = places[name];
                var insert = new Point3d(origin0[0] + place[0], origin0[1] + place[1], origin0[2]);
                var reference = Insert(db, tr, space, blockName, lines[name], insert, args);
                var e = extents[name];
                made.Add((name, reference, blockName, new[] { insert.X + e[0], insert.Y + e[1], insert.X + e[2], insert.Y + e[3] }, lines[name].Count));
            }
            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", made[0].reference.Handle.ToString());
                w.WriteStartArray("views");
                foreach (var view in made)
                {
                    w.WriteStartObject();
                    w.WriteString("view", view.view);
                    w.WriteString("block", view.block);
                    w.WriteString("handle", view.reference.Handle.ToString());
                    RunDrawing.WritePoint(w, "insert", view.reference.Position.X, view.reference.Position.Y, view.reference.Position.Z);
                    w.WriteStartArray("box");
                    foreach (var v in view.box) w.WriteNumberValue(Math.Round(v, 6));
                    w.WriteEndArray();
                    w.WriteNumber("lines", view.count);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                if (empty.Count > 0) WriteTexts(w, "no_lines", empty);
                w.WriteString("projection", projection);
                w.WriteNumber("gap", Math.Round(gap, 6));
                w.WriteNumber("solids", solids.Count);
                w.WriteBoolean("joined", temporary.Count > 0);
                WriteTexts(w, "laid_flat_from", lying);
                if (dropped > 0) w.WriteNumber("dropped", dropped);
                StyleNotes(db, tr, args, w);
            });
        }

        public static RunResult SectionPlaneOp(Database db, Transaction tr, RunArgs args)
        {
            var points = Points(args.Element("points"));
            var look = args.Numbers("look_towards");
            var error = SectionMath.Plane(points, look.Length > 0 ? look : null, out var plane);
            if (error != null) throw new RunRefusal(error);
            var at = InsertPoint(args);
            var space = ModelSpace(db, tr);
            var handles = args.Texts("handles");
            List<Entity> sources;
            if (handles.Length > 0)
                sources = handles.Select(h => (Entity)RunDrawing.Open<Solid3d>(tr, db, h, OpenMode.ForRead, "a 3D solid")).ToList();
            else
            {
                sources = new List<Entity>();
                foreach (ObjectId id in space)
                {
                    if (!id.ObjectClass.IsDerivedFrom(RXObject.GetClass(typeof(Solid3d)))) continue;
                    if (sources.Count == MostSources)
                        throw new RunRefusal("Model space has more than " + MostSources + " solids; give the ones to cut by handle.");
                    sources.Add((Entity)tr.GetObject(id, OpenMode.ForRead));
                }
                if (sources.Count == 0) throw new RunRefusal("Model space has no 3D solids to cut.");
            }
            var hatch = args.Flag("hatch", true);
            var background = args.Flag("background", true);
            var keep = args.Flag("keep_plane", true);
            var (low, high) = Box(sources);
            var size = Math.Max(SectionMath.Distance(low, high), 1.0);

            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var name = args.Text("name").Trim();
            if (name.Length == 0) name = FreeName(blocks, SectionPrefix);
            else if (blocks.Has(name)) throw new RunRefusal("There is already a block called '" + name + "'. Give another name, or leave it out.");
            Validate(name);

            var section = NewSection(db, space, tr, plane.Origin, plane.Along, plane.Vertical, plane.Forward, size, cut: true, hatch, background, tangents: false);
            var found = new List<Entity>();
            var cut = 0;
            foreach (var source in sources)
            {
                Generate(section, source, found, cut: true, hatch, background, tangents: false, out var cutThis);
                if (cutThis) cut++;
            }
            var dropped = 0;
            var flat = LayFlat(found, plane.Origin, plane.Right, plane.Up, plane.Forward, out var where, ref dropped);
            if (flat.Count == 0)
                throw new RunRefusal("The plane neither cuts nor sees any of the " + sources.Count + " solid(s). Check the points and the side it looks at (look_towards).");
            var e = Extents(flat);
            // The block's base point is the section's lower-left corner, which goes on insert_at.
            var shift = Matrix3d.Displacement(new Vector3d(-e[0], -e[1], 0));
            foreach (var entity in flat) entity.TransformBy(shift);
            var reference = Insert(db, tr, space, name, flat, new Point3d(at[0], at[1], at[2]), args);
            string? planeHandle = null;
            if (keep)
            {
                try
                {
                    section.Name = name;
                }
                catch (AcException)
                {
                    // A name AutoCAD will not take for a section plane: it keeps its own.
                }
                var planeLayer = args.Text("plane_layer").Trim();
                if (planeLayer.Length > 0) section.Layer = Layer(db, tr, planeLayer);
                planeHandle = section.Handle.ToString();
            }
            else section.Erase();
            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", reference.Handle.ToString());
                w.WriteString("block", name);
                if (planeHandle != null) w.WriteString("section_plane", planeHandle);
                w.WriteNumber("solids", sources.Count);
                w.WriteNumber("cut", cut);
                w.WriteNumber("lines", flat.Count);
                w.WriteStartArray("size");
                w.WriteNumberValue(Math.Round(e[2] - e[0], 6));
                w.WriteNumberValue(Math.Round(e[3] - e[1], 6));
                w.WriteEndArray();
                RunDrawing.WritePoint(w, "looking", plane.Forward[0], plane.Forward[1], plane.Forward[2]);
                RunDrawing.WritePoint(w, "right", plane.Right[0], plane.Right[1], plane.Right[2]);
                RunDrawing.WritePoint(w, "up", plane.Up[0], plane.Up[1], plane.Up[2]);
                w.WriteString("laid_flat_from", where.ToString().ToLowerInvariant());
                if (dropped > 0) w.WriteNumber("dropped", dropped);
                StyleNotes(db, tr, args, w);
            });
        }

        /// <summary>A 2D section plane, resident (its settings live in the drawing), showing only what was asked for.</summary>
        private static Section NewSection(Database db, BlockTableRecord space, Transaction tr, double[] origin, double[] along, double[] vertical,
            double[] forward, double size, bool cut, bool hatch, bool background, bool tangents)
        {
            var start = new Point3d(origin[0], origin[1], origin[2]);
            var line = new Vector3d(along[0], along[1], along[2]) * Math.Max(size, 1.0);
            var section = new Section(new Point3dCollection { start, start + line }, new Vector3d(vertical[0], vertical[1], vertical[2]),
                new Vector3d(forward[0], forward[1], forward[2]));
            section.SetDatabaseDefaults(db);
            section.State = SectionState.Plane;
            space.AppendEntity(section);
            tr.AddNewlyCreatedDBObject(section, true);
            if (section.Settings.IsNull)
                throw new RunRefusal("AutoCAD made the section plane without its settings, so it cannot generate a 2D section here.");
            var settings = (SectionSettings)tr.GetObject(section.Settings, OpenMode.ForWrite);
            const SectionType Flat = SectionType.Section2d;
            settings.CurrentSectionType = Flat;
            settings.SetVisibility(Flat, SectionGeometry.IntersectionBoundary, cut);
            settings.SetVisibility(Flat, SectionGeometry.IntersectionFill, cut && hatch);
            settings.SetHatchVisibility(Flat, SectionGeometry.IntersectionFill, cut && hatch);
            settings.SetVisibility(Flat, SectionGeometry.BackgroundGeometry, background);
            settings.SetHiddenLine(Flat, SectionGeometry.BackgroundGeometry, false);
            settings.SetVisibility(Flat, SectionGeometry.ForegroundGeometry, false);
            settings.SetVisibility(Flat, SectionGeometry.CurveTangencyLines, tangents);
            return section;
        }

        /// <summary>One source's 2D section lines; what was not asked for is thrown away.</summary>
        private static void Generate(Section section, Entity source, List<Entity> into, bool cut, bool hatch, bool background, bool tangents, out bool wasCut)
        {
            Array boundary, fill, behind, front, tangency;
            try
            {
                section.GenerateSectionGeometry(source, out boundary, out fill, out behind, out front, out tangency);
            }
            catch (AcException ex) when (ex.ErrorStatus == ErrorStatus.NotOpenForWrite && !source.IsWriteEnabled)
            {
                source.UpgradeOpen();
                section.GenerateSectionGeometry(source, out boundary, out fill, out behind, out front, out tangency);
            }
            wasCut = Count(boundary) > 0;
            Take(into, boundary, cut);
            Take(into, fill, cut && hatch);
            Take(into, behind, background);
            Take(into, front, false);
            Take(into, tangency, tangents);
        }

        private static int Count(Array? items) => items == null ? 0 : items.Cast<object>().Count(i => i is Entity);

        private static void Take(List<Entity> into, Array? items, bool keep)
        {
            if (items == null) return;
            foreach (var item in items)
                if (item is Entity entity)
                {
                    if (keep) into.Add(entity);
                    else entity.Dispose();
                }
        }

        /// <summary>
        /// The lines turned flat into the sheet's XY plane, as the viewer sees
        /// them (right along X, up along Y), round the plane's origin. Where they
        /// lie decides how (SectionMath.Where): on the plane they are turned; flat
        /// already they are only moved; spread out each curve is projected onto
        /// the plane first, and anything else is dropped and counted.
        /// </summary>
        private static List<Entity> LayFlat(List<Entity> lines, double[] origin, double[] right, double[] up, double[] forward, out Lying where, ref int dropped)
        {
            var o = new Point3d(origin[0], origin[1], origin[2]);
            var r = new Vector3d(right[0], right[1], right[2]);
            var u = new Vector3d(up[0], up[1], up[2]);
            var f = new Vector3d(forward[0], forward[1], forward[2]);
            where = SectionMath.Where(lines.OfType<Curve>().SelectMany(Samples), origin, forward);
            var toSheet = Matrix3d.AlignCoordinateSystem(o, r, u, f.Negate(), Point3d.Origin, Vector3d.XAxis, Vector3d.YAxis, Vector3d.ZAxis);
            var flat = new List<Entity>();
            if (where == Lying.Flat)
            {
                var e = Extents3(lines);
                var move = Matrix3d.Displacement(new Vector3d(-(e[0] + e[3]) / 2, -(e[1] + e[4]) / 2, -e[2]));
                foreach (var entity in lines)
                {
                    entity.TransformBy(move);
                    flat.Add(entity);
                }
                return flat;
            }
            var plane = new Plane(o, f);
            foreach (var entity in lines)
            {
                var piece = entity;
                if (where == Lying.Spread)
                {
                    if (!(entity is Curve curve))
                    {
                        entity.Dispose();
                        dropped++;
                        continue;
                    }
                    try
                    {
                        piece = curve.GetOrthoProjectedCurve(plane);
                    }
                    catch (AcException)
                    {
                        // A curve seen end on projects to a point: nothing to draw.
                        entity.Dispose();
                        dropped++;
                        continue;
                    }
                    entity.Dispose();
                }
                piece.TransformBy(toSheet);
                flat.Add(piece);
            }
            return flat;
        }

        private static IEnumerable<double[]> Samples(Curve curve)
        {
            var points = new List<double[]>();
            try
            {
                double from = curve.StartParam, to = curve.EndParam;
                for (var k = 0; k <= CurveSamples; k++)
                {
                    var p = curve.GetPointAtParameter(from + (to - from) * k / CurveSamples);
                    points.Add(new[] { p.X, p.Y, p.Z });
                }
            }
            catch (AcException)
            {
                // A curve AutoCAD cannot walk still lies where its extents say.
            }
            return points;
        }

        /// <summary>[minX, minY, maxX, maxY] of flat lines.</summary>
        private static double[] Extents(List<Entity> lines)
        {
            var e = Extents3(lines);
            return new[] { e[0], e[1], e[3], e[4] };
        }

        private static double[] Extents3(List<Entity> lines)
        {
            var low = new[] { double.MaxValue, double.MaxValue, double.MaxValue };
            var high = new[] { double.MinValue, double.MinValue, double.MinValue };
            foreach (var entity in lines)
            {
                try
                {
                    var box = entity.GeometricExtents;
                    low[0] = Math.Min(low[0], box.MinPoint.X);
                    low[1] = Math.Min(low[1], box.MinPoint.Y);
                    low[2] = Math.Min(low[2], box.MinPoint.Z);
                    high[0] = Math.Max(high[0], box.MaxPoint.X);
                    high[1] = Math.Max(high[1], box.MaxPoint.Y);
                    high[2] = Math.Max(high[2], box.MaxPoint.Z);
                }
                catch (AcException)
                {
                    // No extents: it is still drawn.
                }
            }
            if (low[0] == double.MaxValue) return new double[6];
            return new[] { low[0], low[1], low[2], high[0], high[1], high[2] };
        }

        private static (double[] low, double[] high) Box(IEnumerable<Entity> entities)
        {
            var low = new[] { double.MaxValue, double.MaxValue, double.MaxValue };
            var high = new[] { double.MinValue, double.MinValue, double.MinValue };
            foreach (var entity in entities)
            {
                Extents3d box;
                try
                {
                    box = entity.GeometricExtents;
                }
                catch (AcException)
                {
                    continue;
                }
                low[0] = Math.Min(low[0], box.MinPoint.X);
                low[1] = Math.Min(low[1], box.MinPoint.Y);
                low[2] = Math.Min(low[2], box.MinPoint.Z);
                high[0] = Math.Max(high[0], box.MaxPoint.X);
                high[1] = Math.Max(high[1], box.MaxPoint.Y);
                high[2] = Math.Max(high[2], box.MaxPoint.Z);
            }
            if (low[0] == double.MaxValue) throw new RunRefusal("AutoCAD gives no extents for these solids, so there is nothing to look at.");
            return (low, high);
        }

        /// <summary>A new block of the lines (layer 0, ByBlock, as a block should be) and one reference to it.</summary>
        private static BlockReference Insert(Database db, Transaction tr, BlockTableRecord space, string name, List<Entity> lines, Point3d at, RunArgs args)
        {
            Validate(name);
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForWrite);
            var holder = new BlockTableRecord { Name = name, Origin = Point3d.Origin };
            var holderId = blocks.Add(holder);
            tr.AddNewlyCreatedDBObject(holder, true);
            foreach (var entity in lines)
            {
                holder.AppendEntity(entity);
                tr.AddNewlyCreatedDBObject(entity, true);
                entity.LayerId = db.LayerZero;
                entity.ColorIndex = 0;
            }
            var reference = new BlockReference(at, holderId);
            reference.SetDatabaseDefaults(db);
            space.AppendEntity(reference);
            tr.AddNewlyCreatedDBObject(reference, true);
            RunDrawing.Style(reference, db, tr, args);
            return reference;
        }

        private static void StyleNotes(Database db, Transaction tr, RunArgs args, Utf8JsonWriter w)
        {
            var layer = args.Text("layer").Trim();
            if (layer.Length > 0) w.WriteString("layer", layer);
        }

        /// <summary>A layer by name, made if missing (as every Heron tool does).</summary>
        private static string Layer(Database db, Transaction tr, string layer)
        {
            var layers = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
            if (layers.Has(layer)) return layer;
            try
            {
                SymbolUtilityServices.ValidateSymbolName(layer, false);
            }
            catch (AcException)
            {
                throw new RunRefusal("'" + layer + "' cannot be a layer name.");
            }
            layers.UpgradeOpen();
            var record = new LayerTableRecord { Name = layer };
            layers.Add(record);
            tr.AddNewlyCreatedDBObject(record, true);
            return layer;
        }

        private static BlockTableRecord ModelSpace(Database db, Transaction tr)
        {
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            return (BlockTableRecord)tr.GetObject(blocks[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
        }

        private static double[] InsertPoint(RunArgs args)
        {
            var at = args.Numbers("insert_at");
            if (at.Length < 2 || at.Length > 3) throw new RunRefusal("insert_at must be [x, y] or [x, y, z]: where the 2D drawing goes.");
            return new[] { at[0], at[1], at.Length == 3 ? at[2] : 0.0 };
        }

        private static List<double[]> Points(JsonElement value)
        {
            var points = new List<double[]>();
            if (value.ValueKind != JsonValueKind.Array) return points;
            foreach (var item in value.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Array) throw new RunRefusal("Every point must be [x, y] or [x, y, z].");
                points.Add(item.EnumerateArray().Where(v => v.ValueKind == JsonValueKind.Number).Select(v => v.GetDouble()).ToArray());
            }
            return points;
        }

        private static string BlockPrefix(string given, BlockTable blocks, string prefix)
        {
            var name = (given ?? "").Trim();
            if (name.Length > 0)
            {
                Validate(name);
                return name;
            }
            for (var n = 1; ; n++)
            {
                var candidate = prefix + n;
                if (!SectionMath.ViewNames.Any(v => blocks.Has(candidate + "-" + v.ToUpperInvariant()))) return candidate;
            }
        }

        private static string FreeName(BlockTable blocks, string prefix)
        {
            for (var n = 1; ; n++)
                if (!blocks.Has(prefix + n)) return prefix + n;
        }

        private static void Validate(string name)
        {
            try
            {
                SymbolUtilityServices.ValidateSymbolName(name, false);
            }
            catch (AcException)
            {
                throw new RunRefusal("'" + name + "' cannot be a block name.");
            }
        }

        private static void WriteTexts(Utf8JsonWriter w, string name, IEnumerable<string> values)
        {
            w.WriteStartArray(name);
            foreach (var value in values) w.WriteStringValue(value);
            w.WriteEndArray();
        }
    }
}
