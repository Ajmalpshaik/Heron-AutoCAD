using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using AcException = Autodesk.AutoCAD.Runtime.Exception;
using DbSurface = Autodesk.AutoCAD.DatabaseServices.Surface;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Surfaces and meshes with no ActiveX call (D-95): a loft through open
    /// outlines (a surface, where LOFT of closed ones is a solid), PLANESURF
    /// from outlines or two corners, a NETWORK surface from two sets of curves,
    /// and MESH primitives or a mesh made from a solid (MESHSMOOTH). Main
    /// thread, inside PluginRunner's lock and transaction. The curves and
    /// objects they are made from are kept, as with DELOBJ off.
    /// </summary>
    internal static class Surfaces
    {
        private const int MostOutlines = 500;
        private const int MostSmooth = 4;
        private const int MostDivisions = 256;

        /// <summary>A lofted surface through outlines in order, open or closed (LOFT, Mode Surface).</summary>
        public static RunResult LoftSurface(Database db, Transaction tr, RunArgs args)
        {
            var sectionHandles = args.Texts("sections");
            if (sectionHandles.Length < 2) throw new RunRefusal("A loft needs at least two outlines, in order.");
            var sections = sectionHandles.Select(h => (Entity)RunDrawing.Open<Curve>(tr, db, h, OpenMode.ForRead, "an outline (a curve)")).ToArray();
            var guides = args.Texts("guides").Select(h => (Entity)RunDrawing.Open<Curve>(tr, db, h, OpenMode.ForRead, "a guide curve")).ToArray();
            var pathHandle = args.Text("path");
            Entity? path = pathHandle.Length > 0 ? RunDrawing.Open<Curve>(tr, db, pathHandle, OpenMode.ForRead, "a path curve") : null;
            if (path != null && guides.Length > 0) throw new RunRefusal("Give guides or a path, not both: AutoCAD's loft follows one or the other.");
            var builder = new LoftOptionsBuilder { Ruled = args.Flag("ruled", false), Closed = args.Flag("closed", false) };
            var surface = new LoftedSurface();
            surface.SetDatabaseDefaults(db);
            try
            {
                surface.CreateLoftedSurface(sections, guides, path!, builder.ToLoftOptions());
            }
            catch (AcException ex)
            {
                surface.Dispose();
                throw new RunRefusal("AutoCAD could not loft these outlines into a surface (" + ex.ErrorStatus + "). Check they are in order, do not "
                    + "cross each other, are all open or all closed, and that guides touch every outline.");
            }
            var owner = (BlockTableRecord)tr.GetObject(sections[0].OwnerId, OpenMode.ForWrite);
            Add(owner, tr, surface);
            return Made(db, tr, args, surface, w => w.WriteNumber("sections", sections.Length));
        }

        /// <summary>Flat surfaces (PLANESURF): one from each closed outline or region, or one rectangle from two corners.</summary>
        public static RunResult PlanarSurface(Database db, Transaction tr, RunArgs args)
        {
            var outlineHandles = args.Texts("outlines");
            var corners = args.Element("corners");
            var made = new List<DbSurface>();
            BlockTableRecord owner;
            if (outlineHandles.Length > 0)
            {
                if (corners.ValueKind == JsonValueKind.Array) throw new RunRefusal("Give outlines or two corners, not both.");
                if (outlineHandles.Length > MostOutlines) throw new RunRefusal("At most " + MostOutlines + " outlines at once.");
                owner = null!;
                foreach (var handle in outlineHandles)
                {
                    var entity = RunDrawing.Open<Entity>(tr, db, handle, OpenMode.ForRead, "a closed outline or a region");
                    owner ??= (BlockTableRecord)tr.GetObject(entity.OwnerId, OpenMode.ForWrite);
                    foreach (var region in RegionsOf(entity, handle))
                    {
                        made.Add(FromRegion(db, region, handle));
                        if (!ReferenceEquals(region, entity)) region.Dispose();
                    }
                }
            }
            else
            {
                if (corners.ValueKind != JsonValueKind.Array) throw new RunRefusal("Give the outlines to fill, or two opposite corners of a rectangle.");
                var points = corners.EnumerateArray().Select(c => c.EnumerateArray().Select(v => v.GetDouble()).ToArray()).ToArray();
                if (points.Length != 2 || points.Any(p => p.Length < 2 || p.Length > 3))
                    throw new RunRefusal("corners must be two points, [x, y] or [x, y, z]: opposite corners of the rectangle.");
                var z = points[0].Length == 3 ? points[0][2] : 0.0;
                double x0 = Math.Min(points[0][0], points[1][0]), x1 = Math.Max(points[0][0], points[1][0]);
                double y0 = Math.Min(points[0][1], points[1][1]), y1 = Math.Max(points[0][1], points[1][1]);
                if (x1 - x0 < 1e-9 || y1 - y0 < 1e-9) throw new RunRefusal("The two corners make no rectangle: they share an x or a y.");
                using (var outline = new Polyline())
                {
                    outline.AddVertexAt(0, new Point2d(x0, y0), 0, 0, 0);
                    outline.AddVertexAt(1, new Point2d(x1, y0), 0, 0, 0);
                    outline.AddVertexAt(2, new Point2d(x1, y1), 0, 0, 0);
                    outline.AddVertexAt(3, new Point2d(x0, y1), 0, 0, 0);
                    outline.Closed = true;
                    outline.Elevation = z;
                    foreach (var region in RegionsOf(outline, "the rectangle"))
                    {
                        made.Add(FromRegion(db, region, "the rectangle"));
                        region.Dispose();
                    }
                }
                owner = ModelSpace(db, tr);
            }
            foreach (var surface in made) Add(owner, tr, surface);
            foreach (var surface in made) RunDrawing.Style(surface, db, tr, args);
            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", made[0].Handle.ToString());
                w.WriteStartArray("handles");
                foreach (var surface in made) w.WriteStringValue(surface.Handle.ToString());
                w.WriteEndArray();
                w.WriteNumber("surfaces", made.Count);
                w.WriteNumber("area", Math.Round(made.Sum(Area), 6));
            });
        }

        /// <summary>A surface through a net of curves (SURFNETWORK): curves one way, curves the other way across them.</summary>
        public static RunResult NetworkSurface(Database db, Transaction tr, RunArgs args)
        {
            var u = args.Texts("u_curves");
            var v = args.Texts("v_curves");
            if (u.Length < 2 || v.Length < 2) throw new RunRefusal("A network surface needs at least two curves each way: u_curves and v_curves.");
            var uCurves = u.Select(h => RunDrawing.Open<Curve>(tr, db, h, OpenMode.ForRead, "a curve")).ToArray();
            var vCurves = v.Select(h => RunDrawing.Open<Curve>(tr, db, h, OpenMode.ForRead, "a curve")).ToArray();
            var uProfiles = uCurves.Select(c => new Profile3d(c)).ToArray();
            var vProfiles = vCurves.Select(c => new Profile3d(c)).ToArray();
            DbSurface surface;
            try
            {
                surface = DbSurface.CreateNetworkSurface(uProfiles, vProfiles);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD could not make a network surface of these curves (" + ex.ErrorStatus + "). Each u curve must cross "
                    + "every v curve, in order, and the curves of one set must not cross each other.");
            }
            finally
            {
                foreach (var profile in uProfiles.Concat(vProfiles)) profile.Dispose();
            }
            if (surface == null) throw new RunRefusal("AutoCAD made no surface from these curves. Check each u curve crosses every v curve.");
            surface.SetDatabaseDefaults(db);
            var owner = (BlockTableRecord)tr.GetObject(uCurves[0].OwnerId, OpenMode.ForWrite);
            Add(owner, tr, surface);
            return Made(db, tr, args, surface, w =>
            {
                w.WriteNumber("u_curves", u.Length);
                w.WriteNumber("v_curves", v.Length);
            });
        }

        /// <summary>A mesh: a MESH primitive placed by the centre of its base, or a mesh made from a solid, surface or region.</summary>
        public static RunResult Mesh(Database db, Transaction tr, RunArgs args)
        {
            var smooth = (int)args.Number("smoothness", 0);
            if (smooth < 0 || smooth > MostSmooth) throw new RunRefusal("smoothness is 0 to " + MostSmooth + ".");
            var source = args.Text("from_handle");
            var mesh = new SubDMesh();
            mesh.SetDatabaseDefaults(db);
            BlockTableRecord owner;
            string what;
            try
            {
                if (source.Length > 0)
                {
                    var from = RunDrawing.Open<Entity>(tr, db, source, OpenMode.ForRead, "a solid, a surface or a region");
                    if (!(from is Solid3d || from is DbSurface || from is Region))
                        throw new RunRefusal(source + " is " + RunDrawing.Kind(from) + "; a mesh is made from a 3D solid, a surface or a region.");
                    var data = SubDMesh.GetObjectMesh(from, Faceter());
                    if (data.VertexArray == null || data.VertexArray.Count == 0)
                        throw new RunRefusal("AutoCAD made no mesh from " + source + ".");
                    mesh.SetSubDMesh(data.VertexArray, data.FaceArray, smooth);
                    owner = (BlockTableRecord)tr.GetObject(from.OwnerId, OpenMode.ForWrite);
                    what = "from " + RunDrawing.Kind(from).Substring(2);
                }
                else
                {
                    what = Primitive(mesh, args, smooth);
                    owner = ModelSpace(db, tr);
                }
            }
            catch (AcException ex)
            {
                mesh.Dispose();
                throw new RunRefusal("AutoCAD would not make that mesh (" + ex.ErrorStatus + "). Check the sizes and divisions.");
            }
            catch (RunRefusal)
            {
                mesh.Dispose();
                throw;
            }
            if (source.Length == 0)
            {
                // Placed by the centre of its base (a sphere and a torus by their centre), as autocad_add_solid places a solid.
                var at = args.Numbers("base");
                if (at.Length < 2 || at.Length > 3)
                {
                    mesh.Dispose();
                    throw new RunRefusal("base must be [x, y] or [x, y, z]: the centre of the mesh's base.");
                }
                var box = mesh.GeometricExtents;
                var round = what == "sphere" || what == "torus";
                var from = new Point3d((box.MinPoint.X + box.MaxPoint.X) / 2, (box.MinPoint.Y + box.MaxPoint.Y) / 2,
                    round ? (box.MinPoint.Z + box.MaxPoint.Z) / 2 : box.MinPoint.Z);
                mesh.TransformBy(Matrix3d.Displacement(new Point3d(at[0], at[1], at.Length == 3 ? at[2] : 0.0) - from));
            }
            Add(owner, tr, mesh);
            RunDrawing.Style(mesh, db, tr, args);
            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", mesh.Handle.ToString());
                w.WriteString("mesh", what);
                if (source.Length > 0) w.WriteString("from", source);
                w.WriteNumber("smoothness", smooth);
                w.WriteNumber("faces", mesh.NumberOfFaces);
                w.WriteNumber("vertices", mesh.NumberOfVertices);
                try
                {
                    w.WriteBoolean("watertight", mesh.Watertight);
                    if (mesh.Watertight) w.WriteNumber("volume", Math.Round(mesh.ComputeVolume(), 6));
                }
                catch (AcException)
                {
                    // A mesh AutoCAD cannot measure is still made.
                }
            });
        }

        private static string Primitive(SubDMesh mesh, RunArgs args, int smooth)
        {
            var shape = args.Text("shape").Trim().ToLowerInvariant();
            int Div(string name, int fallback)
            {
                var value = (int)args.Number(name, fallback);
                if (value < 1 || value > MostDivisions) throw new RunRefusal(name + " is 1 to " + MostDivisions + ".");
                return value;
            }
            double Size(string name)
            {
                var value = args.Number(name);
                if (!(value > 0)) throw new RunRefusal(name + " must be above zero.");
                return value;
            }
            var round = Div("divisions", shape == "sphere" ? 12 : 8);
            switch (shape)
            {
                case "box":
                    mesh.Setbox(Size("length"), Size("width"), Size("height"), Div("divisions", 3), Div("divisions", 3), Div("divisions", 3), smooth);
                    break;
                case "wedge":
                    mesh.SetWedge(Size("length"), Size("width"), Size("height"), 3, 3, 3, 3, 2, smooth);
                    break;
                case "cylinder":
                    {
                        var r = Size("radius");
                        mesh.SetCylinder(r, r, Size("height"), round, 3, 3, smooth);
                        break;
                    }
                case "cone":
                    {
                        var r = Size("radius");
                        var top = args.Number("top_radius", 0.0);
                        if (top < 0 || top >= r) throw new RunRefusal("top_radius must be 0 (a point) or less than the radius.");
                        mesh.SetCone(r, r, Size("height"), round, 3, 3, top / r, smooth);
                        break;
                    }
                case "sphere":
                    mesh.SetSphere(Size("radius"), round, Math.Max(2, round / 2), smooth);
                    break;
                case "torus":
                    {
                        var r = Size("radius");
                        var tube = Size("tube_radius");
                        if (tube >= r) throw new RunRefusal("tube_radius must be smaller than the radius, or the torus closes on itself.");
                        mesh.SetTorus(r, round, round, tube / r, 0.0, smooth);
                        break;
                    }
                case "pyramid":
                    {
                        var r = Size("radius");
                        var top = args.Number("top_radius", 0.0);
                        if (top < 0 || top >= r) throw new RunRefusal("top_radius must be 0 (a point) or less than the radius.");
                        var sides = (int)args.Number("sides", 4);
                        if (sides < 3 || sides > 32) throw new RunRefusal("sides is 3 to 32.");
                        mesh.SetPyramid(r, Size("height"), 3, 3, 3, sides, top / r, smooth);
                        break;
                    }
                default:
                    throw new RunRefusal("'" + shape + "' is not a mesh shape. Shapes: box, wedge, cylinder, cone, sphere, torus, pyramid.");
            }
            return shape;
        }

        /// <summary>The faceting AutoCAD's own MESHSMOOTH uses, from the drawing's FACETER variables.</summary>
        private static MeshFaceterData Faceter()
        {
            double Number(string name, double fallback)
            {
                try
                {
                    return Convert.ToDouble(AcApp.GetSystemVariable(name));
                }
                catch (System.Exception)
                {
                    return fallback;
                }
            }
            return new MeshFaceterData(
                Number("FACETERDEVSURFACE", 0.001), Number("FACETERDEVNORMAL", 40), Number("FACETERGRIDRATIO", 0),
                Number("FACETERMAXEDGELENGTH", 0), (ushort)Number("FACETERMAXGRID", 4096), (ushort)Number("FACETERMINUGRID", 0),
                (ushort)Number("FACETERMINVGRID", 0), (short)Number("FACETERMESHTYPE", 0));
        }

        /// <summary>The regions a closed outline (or a region itself) makes.</summary>
        private static List<Region> RegionsOf(Entity entity, string handle)
        {
            if (entity is Region region) return new List<Region> { region };
            if (!(entity is Curve curve)) throw new RunRefusal(handle + " is " + RunDrawing.Kind(entity) + ", not a closed outline or a region.");
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
            if (!closed) throw new RunRefusal("Outline " + handle + " is open. A planar surface fills a closed outline: close it, or loft open outlines into a surface.");
            DBObjectCollection made;
            try
            {
                made = Region.CreateFromCurves(new DBObjectCollection { curve });
            }
            catch (AcException ex)
            {
                throw new RunRefusal("Outline " + handle + " makes no flat area (" + ex.ErrorStatus + "). It must be closed, flat, and not cross itself.");
            }
            var regions = made.Cast<DBObject>().OfType<Region>().ToList();
            if (regions.Count == 0) throw new RunRefusal("Outline " + handle + " makes no flat area. It must be closed, flat, and not cross itself.");
            return regions;
        }

        private static DbSurface FromRegion(Database db, Region region, string handle)
        {
            var surface = new PlaneSurface();
            surface.SetDatabaseDefaults(db);
            try
            {
                surface.CreateFromRegion(region);
            }
            catch (AcException ex)
            {
                surface.Dispose();
                throw new RunRefusal("AutoCAD would not make a flat surface of " + handle + " (" + ex.ErrorStatus + ").");
            }
            return surface;
        }

        private static void Add(BlockTableRecord owner, Transaction tr, Entity entity)
        {
            owner.AppendEntity(entity);
            tr.AddNewlyCreatedDBObject(entity, true);
        }

        private static BlockTableRecord ModelSpace(Database db, Transaction tr)
        {
            var blocks = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
            return (BlockTableRecord)tr.GetObject(blocks[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
        }

        private static double Area(DbSurface surface)
        {
            try
            {
                return surface.GetArea();
            }
            catch (AcException)
            {
                return 0.0;
            }
        }

        private static RunResult Made(Database db, Transaction tr, RunArgs args, DbSurface surface, Action<Utf8JsonWriter> more) => RunResult.Done(w =>
        {
            w.WriteBoolean("created", true);
            w.WriteString("handle", surface.Handle.ToString());
            more(w);
            RunDrawing.Style(surface, db, tr, args, w);
            var area = Area(surface);
            if (area > 0) w.WriteNumber("area", Math.Round(area, 6));
        });
    }
}
