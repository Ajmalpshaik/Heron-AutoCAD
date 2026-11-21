using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.DatabaseServices.Filters;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// A block repeated as a hatch inside a closed outline (Express Tools'
    /// SUPERHATCH): paving, cladding, a tiled ceiling, a grating.
    ///
    /// Made as one object the modeller can move or erase: a new block holding
    /// the grid of tiles (TileGrid), inserted once at 0,0 and clipped to the
    /// outline the way XCLIP clips, with a spatial filter on the reference.
    /// </summary>
    internal static class SuperHatch
    {
        // Where XCLIP keeps a reference's clip: extension dictionary -> ACAD_FILTER -> SPATIAL.
        private const string FilterDictionary = "ACAD_FILTER";
        private const string SpatialFilterName = "SPATIAL";
        // ObjectARX's ACDB_INFINITE_XCLIP_DEPTH: no front or back clipping plane.
        private const double NoClipDepth = 1.0e+300;
        // Steps along a heavy polyline's segment, and along a spline: fixed.
        private const int SegmentSteps = 16;
        private const int CurveSteps = 128;
        // An arc is followed to within this share of the outline's size (2 mm in a 20 m room).
        private const double ArcTolerance = 1e-4;
        private const string NamePrefix = "SUPERHATCH-";

        public static RunResult Make(Database db, Transaction tr, RunArgs args)
        {
            var boundaryHandle = args.Text("boundary");
            var boundary = RunDrawing.Open<Curve>(tr, db, boundaryHandle, OpenMode.ForRead, "a closed outline (polyline, circle, ellipse or spline)");
            var outline = Outline(boundary, boundaryHandle);
            var elevation = boundary.StartPoint.Z;

            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            var scale = args.Number("scale", 1.0);
            if (!(scale > 0)) throw new RunRefusal("The scale must be above zero.");
            var angle = args.Number("angle", 0.0);

            var name = args.Text("name").Trim();
            if (name.Length == 0) name = FreeName(blocks);
            else if (blocks.Has(name)) throw new RunRefusal("There is already a block called '" + name + "'. Give another name, or leave it out.");
            ValidateName(name);

            // The tile: a block, or one made here from an image or a wipeout, or an xref (D-95).
            var kind = args.Text("tile_kind", "block").Trim().ToLowerInvariant();
            var tile = kind switch
            {
                "block" => FromBlock(blocks, tr, args.Text("block").Trim(), scale),
                "xref" => FromXref(db, tr, blocks, args.Text("xref").Trim(), scale, boundary),
                "image" => FromImage(db, tr, blocks, args, name + "-TILE", scale),
                "wipeout" => FromWipeout(db, tr, blocks, args.Text("wipeout").Trim(), name + "-TILE", scale),
                _ => throw new RunRefusal("The tile is a block, an image, an xref or a wipeout; '" + kind + "' is none of them."),
            };
            var tileId = tile.Id;
            var tileName = tile.Name;
            var tileMin = tile.Min;
            var tileMax = tile.Max;

            var spacing = args.Numbers("spacing");
            double stepX = spacing.Length >= 2 ? spacing[0] : tileMax[0] - tileMin[0];
            double stepY = spacing.Length >= 2 ? spacing[1] : tileMax[1] - tileMin[1];
            if (!(stepX > 0) || !(stepY > 0))
                tile.Fail(db, "'" + tileName + "' has no width or height to space the tiles by. Give the spacing.");

            var areaMin = new[] { double.MaxValue, double.MaxValue };
            var areaMax = new[] { double.MinValue, double.MinValue };
            foreach (var p in outline)
            {
                areaMin[0] = Math.Min(areaMin[0], p.X);
                areaMin[1] = Math.Min(areaMin[1], p.Y);
                areaMax[0] = Math.Max(areaMax[0], p.X);
                areaMax[1] = Math.Max(areaMax[1], p.Y);
            }
            var origin = args.Numbers("origin");
            var gridOrigin = origin.Length >= 2 ? new[] { origin[0], origin[1] } : new[] { areaMin[0], areaMin[1] };
            var error = TileGrid.Positions(areaMin, areaMax, gridOrigin, stepX, stepY, angle, tileMin, tileMax, out var positions,
                kind == "image" ? TileGrid.MostImageTiles : TileGrid.MostTiles);
            if (error != null) tile.Fail(db, error);

            // The tiles live in their own block, on layer 0 and colour ByBlock, so
            // the one reference's layer and colour are what the modeller sees.
            if (!blocks.IsWriteEnabled) blocks.UpgradeOpen();
            var holder = new BlockTableRecord { Name = name, Origin = Point3d.Origin };
            var holderId = blocks.Add(holder);
            tr.AddNewlyCreatedDBObject(holder, true);
            foreach (var p in positions)
            {
                var piece = new BlockReference(new Point3d(p[0], p[1], elevation), tileId)
                {
                    ScaleFactors = new Scale3d(scale),
                    Rotation = angle,
                };
                holder.AppendEntity(piece);
                tr.AddNewlyCreatedDBObject(piece, true);
                piece.LayerId = db.LayerZero;
                piece.ColorIndex = 0;
            }

            var owner = (BlockTableRecord)tr.GetObject(boundary.OwnerId, OpenMode.ForWrite);
            var reference = new BlockReference(Point3d.Origin, holderId);
            reference.SetDatabaseDefaults(db);
            owner.AppendEntity(reference);
            tr.AddNewlyCreatedDBObject(reference, true);
            Clip(reference, outline, elevation, tr);

            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", reference.Handle.ToString());
                w.WriteString("block", name);
                w.WriteString("tile", tileName);
                w.WriteString("tile_kind", kind);
                if (tile.Made) w.WriteBoolean("tile_block_made", true);
                if (tile.Attached) w.WriteBoolean("xref_attached", true);
                w.WriteNumber("tiles", positions.Count);
                w.WriteStartArray("spacing");
                w.WriteNumberValue(Math.Round(stepX, 9));
                w.WriteNumberValue(Math.Round(stepY, 9));
                w.WriteEndArray();
                w.WriteString("boundary", boundaryHandle);
                w.WriteNumber("outline_points", outline.Count);
                RunDrawing.Style(reference, db, tr, args, w);
            });
        }

        /// <summary>What is repeated, and its size from its base point at the scale asked for, unturned.</summary>
        private sealed class Tile
        {
            public ObjectId Id;
            public string Name = "";
            public double[] Min = new double[2];
            public double[] Max = new double[2];
            /// <summary>A tile block made here, from an image or a wipeout.</summary>
            public bool Made;
            /// <summary>An xref this call attached, taken off again if the hatch is refused.</summary>
            public bool Attached;

            /// <summary>Refuse, first detaching an xref this call attached (attaching is not undone by the transaction alone).</summary>
            public void Fail(Database db, string message)
            {
                if (Attached)
                {
                    try
                    {
                        db.DetachXref(Id);
                    }
                    catch (AcException)
                    {
                        // The transaction's abort is the second line.
                    }
                }
                throw new RunRefusal(message);
            }
        }

        private static Tile FromBlock(BlockTable blocks, Transaction tr, string tileName, double scale)
        {
            if (tileName.Length == 0 || !blocks.Has(tileName))
                throw new RunRefusal("There is no block called '" + tileName + "' in this drawing. autocad_list_blocks lists them; "
                    + "autocad_insert_block brings one in from a .dwg.");
            var id = blocks[tileName];
            var record = (BlockTableRecord)tr.GetObject(id, OpenMode.ForRead);
            if (record.IsFromExternalReference) throw new RunRefusal("'" + tileName + "' is an xref: give it as the xref tile instead of the block.");
            if (record.IsLayout || record.IsAnonymous)
                throw new RunRefusal("'" + tileName + "' is a layout or an unnamed block; a super hatch repeats an ordinary block.");
            var (min, max) = TileExtents(record, tr, scale);
            return new Tile { Id = id, Name = tileName, Min = min, Max = max };
        }

        /// <summary>
        /// An xref as the tile: one already attached, by name, or a .dwg
        /// attached now. Its size is read from a reference to it put in and
        /// erased again, because an xref's own record holds no objects to measure.
        /// </summary>
        private static Tile FromXref(Database db, Transaction tr, BlockTable blocks, string xref, double scale, Curve boundary)
        {
            if (xref.Length == 0) throw new RunRefusal("Give the xref: the name of one attached, or the .dwg file to attach.");
            var isFile = xref.EndsWith(".dwg", StringComparison.OrdinalIgnoreCase) || xref.IndexOfAny(new[] { '\\', '/' }) >= 0;
            var tile = new Tile();
            if (isFile)
            {
                if (!System.IO.File.Exists(xref)) throw new RunRefusal("There is no drawing at '" + xref + "'.");
                var name = System.IO.Path.GetFileNameWithoutExtension(xref);
                if (blocks.Has(name))
                {
                    var existing = (BlockTableRecord)tr.GetObject(blocks[name], OpenMode.ForRead);
                    if (!existing.IsFromExternalReference)
                        throw new RunRefusal("This drawing already has a block called '" + name + "', so the xref cannot take that name. Rename the file or the block.");
                    // Already attached under that name: the one in the drawing is used, as XATTACH would.
                    tile.Id = existing.ObjectId;
                }
                else
                {
                    try
                    {
                        tile.Id = db.AttachXref(xref, name);
                    }
                    catch (AcException ex)
                    {
                        throw new RunRefusal("AutoCAD would not attach '" + xref + "' (" + ex.ErrorStatus + ").");
                    }
                    if (tile.Id.IsNull) throw new RunRefusal("AutoCAD would not attach '" + xref + "'.");
                    tile.Attached = true;
                }
                tile.Name = name;
            }
            else
            {
                if (!blocks.Has(xref)) throw new RunRefusal("No xref called '" + xref + "' is attached. autocad_xref_tree lists them, or give the .dwg file.");
                tile.Id = blocks[xref];
                tile.Name = xref;
            }
            var record = (BlockTableRecord)tr.GetObject(tile.Id, OpenMode.ForRead);
            if (!record.IsFromExternalReference) tile.Fail(db, "'" + tile.Name + "' is a block, not an xref: give it as the block tile.");
            if (record.XrefStatus != XrefStatus.Resolved)
                tile.Fail(db, "The xref '" + tile.Name + "' is not loaded (" + record.XrefStatus + "). Reload it in the External References palette first.");
            // Measure it from a reference at the origin, put in and erased again.
            var owner = (BlockTableRecord)tr.GetObject(boundary.OwnerId, OpenMode.ForWrite);
            var probe = new BlockReference(Point3d.Origin, tile.Id) { ScaleFactors = new Scale3d(scale) };
            owner.AppendEntity(probe);
            tr.AddNewlyCreatedDBObject(probe, true);
            try
            {
                var box = probe.GeometricExtents;
                tile.Min = new[] { box.MinPoint.X, box.MinPoint.Y };
                tile.Max = new[] { box.MaxPoint.X, box.MaxPoint.Y };
            }
            catch (AcException)
            {
                tile.Fail(db, "The xref '" + tile.Name + "' draws nothing AutoCAD can measure, so it cannot be a hatch tile.");
            }
            finally
            {
                probe.Erase();
            }
            return tile;
        }

        /// <summary>A tile block holding one raster image, its lower-left corner on the block's base point.</summary>
        private static Tile FromImage(Database db, Transaction tr, BlockTable blocks, RunArgs args, string tileName, double scale)
        {
            var path = args.Text("image").Trim();
            if (path.Length == 0) throw new RunRefusal("Give the image file to repeat.");
            if (!System.IO.File.Exists(path)) throw new RunRefusal("There is no image at '" + path + "'.");
            if (blocks.Has(tileName)) throw new RunRefusal("There is already a block called '" + tileName + "'. Give the hatch another name.");
            var dictionaryId = RasterImageDef.GetImageDictionary(db);
            if (dictionaryId.IsNull) dictionaryId = RasterImageDef.CreateImageDictionary(db);
            var dictionary = (DBDictionary)tr.GetObject(dictionaryId, OpenMode.ForWrite);
            RasterImageDef? definition = null;
            ObjectId definitionId = ObjectId.Null;
            foreach (DBDictionaryEntry entry in dictionary)
            {
                if (tr.GetObject(entry.Value, OpenMode.ForRead) is RasterImageDef existing
                    && string.Equals(existing.SourceFileName, path, StringComparison.OrdinalIgnoreCase))
                {
                    definition = existing;
                    definitionId = entry.Value;
                    break;
                }
            }
            if (definition == null)
            {
                definition = new RasterImageDef { SourceFileName = path };
                try
                {
                    definition.Load();
                }
                catch (AcException ex)
                {
                    definition.Dispose();
                    throw new RunRefusal("AutoCAD could not load the image '" + path + "' (" + ex.ErrorStatus + "). Use a .png, .jpg, .tif or .bmp.");
                }
                definitionId = dictionary.SetAt(RasterImageDef.SuggestName(dictionary, path), definition);
                tr.AddNewlyCreatedDBObject(definition, true);
            }
            else if (!definition.IsLoaded)
            {
                definition.UpgradeOpen();
                definition.Load();
            }
            var pixels = definition.Size;
            var size = args.Numbers("image_size");
            if (size.Length < 1 || !(size[0] > 0)) throw new RunRefusal("Give image_size: the tile's width in drawing units, and its height if not in proportion.");
            var width = size[0];
            var height = size.Length >= 2 && size[1] > 0 ? size[1] : (pixels.X > 0 ? width * pixels.Y / pixels.X : width);

            var holder = NewTileBlock(blocks, tr, tileName);
            var image = new RasterImage { ImageDefId = definitionId };
            image.SetDatabaseDefaults(db);
            image.Orientation = new CoordinateSystem3d(Point3d.Origin, new Vector3d(width, 0, 0), new Vector3d(0, height, 0));
            image.ShowImage = true;
            holder.AppendEntity(image);
            tr.AddNewlyCreatedDBObject(image, true);
            RasterImage.EnableReactors(true);
            image.AssociateRasterDef(definition);
            image.LayerId = db.LayerZero;
            return new Tile { Id = holder.ObjectId, Name = tileName, Min = new[] { 0.0, 0.0 }, Max = new[] { width * scale, height * scale }, Made = true };
        }

        /// <summary>A tile block holding a copy of a wipeout, its box's lower-left corner on the block's base point.</summary>
        private static Tile FromWipeout(Database db, Transaction tr, BlockTable blocks, string handle, string tileName, double scale)
        {
            if (handle.Length == 0) throw new RunRefusal("Give the wipeout to repeat, by handle (autocad_add_wipeout makes one).");
            var wipeout = RunDrawing.Open<Wipeout>(tr, db, handle, OpenMode.ForRead, "a wipeout");
            if (blocks.Has(tileName)) throw new RunRefusal("There is already a block called '" + tileName + "'. Give the hatch another name.");
            Extents3d box;
            try
            {
                box = wipeout.GeometricExtents;
            }
            catch (AcException)
            {
                throw new RunRefusal("Wipeout " + handle + " has no size AutoCAD can measure.");
            }
            if (Math.Abs(box.MaxPoint.Z - box.MinPoint.Z) > 1e-6 * Math.Max(1.0, box.MinPoint.DistanceTo(box.MaxPoint)))
                throw new RunRefusal("Wipeout " + handle + " is not flat in plan; a super hatch repeats a wipeout drawn in plan.");
            var holder = NewTileBlock(blocks, tr, tileName);
            var copy = (Wipeout)wipeout.Clone();
            copy.TransformBy(Matrix3d.Displacement(Point3d.Origin - new Point3d(box.MinPoint.X, box.MinPoint.Y, box.MinPoint.Z)));
            holder.AppendEntity(copy);
            tr.AddNewlyCreatedDBObject(copy, true);
            copy.LayerId = db.LayerZero;
            var width = (box.MaxPoint.X - box.MinPoint.X) * scale;
            var height = (box.MaxPoint.Y - box.MinPoint.Y) * scale;
            return new Tile { Id = holder.ObjectId, Name = tileName, Min = new[] { 0.0, 0.0 }, Max = new[] { width, height }, Made = true };
        }

        private static BlockTableRecord NewTileBlock(BlockTable blocks, Transaction tr, string name)
        {
            ValidateName(name);
            if (!blocks.IsWriteEnabled) blocks.UpgradeOpen();
            var record = new BlockTableRecord { Name = name, Origin = Point3d.Origin };
            blocks.Add(record);
            tr.AddNewlyCreatedDBObject(record, true);
            return record;
        }

        private static void ValidateName(string name)
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

        /// <summary>
        /// The outline as points in plan. Arcs are followed in short straight
        /// steps, as XCLIP itself stores a boundary: a clip is a polygon.
        /// </summary>
        private static List<Point2d> Outline(Curve curve, string handle)
        {
            var closed = curve.Closed;
            if (!closed)
            {
                try
                {
                    closed = curve.StartPoint.IsEqualTo(curve.EndPoint);
                }
                catch (AcException)
                {
                }
            }
            if (!closed) throw new RunRefusal("Outline " + handle + " is open. A super hatch fills a closed outline: close it first.");
            Plane plane;
            try
            {
                plane = curve.GetPlane();
            }
            catch (AcException)
            {
                throw new RunRefusal("Outline " + handle + " does not lie flat. A super hatch fills an outline drawn flat in plan.");
            }
            if (!plane.Normal.IsParallelTo(Vector3d.ZAxis))
                throw new RunRefusal("Outline " + handle + " is tilted. A super hatch fills an outline drawn flat in plan (world XY).");

            var tolerance = Size(curve) * ArcTolerance;
            var points = new List<Point2d>();
            if (curve is Polyline polyline)
            {
                var count = polyline.NumberOfVertices;
                var segments = polyline.Closed ? count : count - 1;
                for (var i = 0; i < segments; i++)
                {
                    var bulge = polyline.GetBulgeAt(i);
                    var steps = 1;
                    if (Math.Abs(bulge) >= 1e-12)
                    {
                        // A bulge is tan(sweep / 4); the chord and the sweep give the radius.
                        var sweep = 4 * Math.Atan(Math.Abs(bulge));
                        var chord = polyline.GetPoint2dAt(i).GetDistanceTo(polyline.GetPoint2dAt((i + 1) % count));
                        steps = TileGrid.ArcSteps(sweep, chord / (2 * Math.Sin(sweep / 2)), tolerance);
                    }
                    for (var k = 0; k < steps; k++) Add(points, polyline.GetPointAtParameter(i + (double)k / steps));
                }
            }
            else if (curve is Polyline2d || curve is Polyline3d)
            {
                // Whole parameters are the vertices: keep every corner.
                for (var i = (int)Math.Round(curve.StartParam); i < (int)Math.Round(curve.EndParam); i++)
                    for (var k = 0; k < SegmentSteps; k++) Add(points, curve.GetPointAtParameter(i + (double)k / SegmentSteps));
            }
            else
            {
                var steps = CurveSteps;
                if (curve is Circle circle) steps = TileGrid.ArcSteps(2 * Math.PI, circle.Radius, tolerance);
                else if (curve is Ellipse ellipse) steps = TileGrid.ArcSteps(2 * Math.PI, ellipse.MajorRadius, tolerance);
                double from = curve.StartParam, to = curve.EndParam;
                for (var k = 0; k < steps; k++) Add(points, curve.GetPointAtParameter(from + (to - from) * k / steps));
            }
            while (points.Count > 1 && points[points.Count - 1].IsEqualTo(points[0])) points.RemoveAt(points.Count - 1);
            if (points.Count < 3) throw new RunRefusal("Outline " + handle + " encloses no area.");
            return points;
        }

        /// <summary>The outline's size across, for the arc tolerance.</summary>
        private static double Size(Curve curve)
        {
            try
            {
                var box = curve.GeometricExtents;
                return box.MinPoint.DistanceTo(box.MaxPoint);
            }
            catch (AcException)
            {
                return 0;
            }
        }

        private static void Add(List<Point2d> points, Point3d p)
        {
            var flat = new Point2d(p.X, p.Y);
            if (points.Count == 0 || !points[points.Count - 1].IsEqualTo(flat)) points.Add(flat);
        }

        /// <summary>The tile's extents from its base point, at the scale asked for, unturned.</summary>
        private static (double[] min, double[] max) TileExtents(BlockTableRecord tile, Transaction tr, double scale)
        {
            Extents3d? box = null;
            foreach (ObjectId id in tile)
            {
                if (!(tr.GetObject(id, OpenMode.ForRead) is Entity entity) || entity is AttributeDefinition || !entity.Visible) continue;
                try
                {
                    var extents = entity.GeometricExtents;
                    if (box == null) box = extents;
                    else
                    {
                        var grow = box.Value;
                        grow.AddExtents(extents);
                        box = grow;
                    }
                }
                catch (AcException)
                {
                    // Some objects have no extents; they still go in the tile.
                }
            }
            if (box == null) throw new RunRefusal("Block '" + tile.Name + "' draws nothing, so it cannot be a hatch tile.");
            var origin = tile.Origin;
            return (
                new[] { (box.Value.MinPoint.X - origin.X) * scale, (box.Value.MinPoint.Y - origin.Y) * scale },
                new[] { (box.Value.MaxPoint.X - origin.X) * scale, (box.Value.MaxPoint.Y - origin.Y) * scale });
        }

        private static string FreeName(BlockTable blocks)
        {
            for (var n = 1; ; n++)
                if (!blocks.Has(NamePrefix + n)) return NamePrefix + n;
        }

        /// <summary>
        /// What XCLIP does: a spatial filter on the reference. The reference sits
        /// at 0,0 unscaled and unturned, so the outline's world points are also
        /// the block's own points.
        /// </summary>
        private static void Clip(BlockReference reference, List<Point2d> outline, double elevation, Transaction tr)
        {
            var definition = new SpatialFilterDefinition(new Point2dCollection(outline.ToArray()), Vector3d.ZAxis, elevation, NoClipDepth, -NoClipDepth, true);
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
    }
}
