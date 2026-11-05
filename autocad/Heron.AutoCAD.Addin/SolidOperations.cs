using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.BoundaryRepresentation;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;
using BrepFace = Autodesk.AutoCAD.BoundaryRepresentation.Face;
using DbSurface = Autodesk.AutoCAD.DatabaseServices.Surface;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// 3D modelling with no ActiveX call: loft, fillet and chamfer edges, shell,
    /// press-pull and thicken, plus the list of a solid's faces and edges they
    /// pick from. Main thread, inside PluginRunner's lock and transaction.
    /// </summary>
    internal static class SolidOperations
    {
        private const string Lister = "autocad_list_solid_faces_and_edges";

        public static RunResult Topology(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForRead, "a 3D solid");
            var topology = SolidTopology.Of(solid);
            return RunResult.Done(w =>
            {
                w.WriteString("handle", handle);
                WriteVolume(w, "volume", solid);
                w.WriteStartArray("faces");
                for (var i = 0; i < topology.Faces.Count; i++)
                {
                    var face = topology.Faces[i];
                    w.WriteStartObject();
                    w.WriteNumber("index", i);
                    w.WriteString("kind", face.Kind);
                    if (!double.IsNaN(topology.FaceAreas[i])) w.WriteNumber("area", Math.Round(topology.FaceAreas[i], 6));
                    RunDrawing.WritePoint(w, "center", (face.Min[0] + face.Max[0]) / 2, (face.Min[1] + face.Max[1]) / 2, (face.Min[2] + face.Max[2]) / 2);
                    var normal = topology.FaceNormals[i];
                    if (normal != null) RunDrawing.WritePoint(w, "normal", normal[0], normal[1], normal[2]);
                    RunDrawing.WriteNumbers(w, "edges", topology.FaceEdges[i]);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
                w.WriteStartArray("edges");
                for (var i = 0; i < topology.Edges.Count; i++)
                {
                    var edge = topology.Edges[i];
                    w.WriteStartObject();
                    w.WriteNumber("index", i);
                    w.WriteString("kind", edge.Kind);
                    var start = topology.EdgeEnds[i][0];
                    var end = topology.EdgeEnds[i][1];
                    RunDrawing.WritePoint(w, "start", start.X, start.Y, start.Z);
                    RunDrawing.WritePoint(w, "end", end.X, end.Y, end.Z);
                    if (!double.IsNaN(topology.EdgeLengths[i])) w.WriteNumber("length", Math.Round(topology.EdgeLengths[i], 6));
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        /// <summary>A solid through closed outlines in order (LOFT): a duct transition, a tapered column.</summary>
        public static RunResult Loft(Database db, Transaction tr, RunArgs args)
        {
            var sectionHandles = args.Texts("sections");
            if (sectionHandles.Length < 2) throw new RunRefusal("A loft needs at least two outlines, in order.");
            var sections = sectionHandles.Select(h => RunDrawing.Open<Curve>(tr, db, h, OpenMode.ForRead, "an outline (a curve)")).ToArray();
            for (var i = 0; i < sections.Length; i++)
                if (!IsClosed(sections[i]))
                    throw new RunRefusal("Outline " + sectionHandles[i] + " is open, so the loft would be a surface, not a solid. Close it first.");
            var guides = args.Texts("guides").Select(h => (Entity)RunDrawing.Open<Curve>(tr, db, h, OpenMode.ForRead, "a guide curve")).ToArray();
            var pathHandle = args.Text("path");
            Entity? path = pathHandle.Length > 0 ? RunDrawing.Open<Curve>(tr, db, pathHandle, OpenMode.ForRead, "a path curve") : null;
            if (path != null && guides.Length > 0) throw new RunRefusal("Give guides or a path, not both: AutoCAD's loft follows one or the other.");

            var builder = new LoftOptionsBuilder { Ruled = args.Flag("ruled", false), Closed = args.Flag("closed", false) };
            var solid = new Solid3d();
            solid.SetDatabaseDefaults(db);
            try
            {
                solid.CreateLoftedSolid(sections.Cast<Entity>().ToArray(), guides, path!, builder.ToLoftOptions());
            }
            catch (AcException ex)
            {
                solid.Dispose();
                throw new RunRefusal("AutoCAD could not loft these outlines (" + ex.ErrorStatus + "). Check they are in order, do not cross each other, "
                    + "and that guides touch every outline.");
            }
            var owner = (BlockTableRecord)tr.GetObject(sections[0].OwnerId, OpenMode.ForWrite);
            owner.AppendEntity(solid);
            tr.AddNewlyCreatedDBObject(solid, true);
            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", solid.Handle.ToString());
                w.WriteNumber("sections", sections.Length);
                RunDrawing.Style(solid, db, tr, args, w);
                WriteVolume(w, "volume", solid);
            });
        }

        /// <summary>Round edges of a solid (FILLETEDGE).</summary>
        public static RunResult Fillet(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var radius = args.Number("radius");
            if (!(radius > 0)) throw new RunRefusal("The radius must be above zero.");
            // Read first: the topology's Brep opens the solid itself, and it must be
            // let go before the solid is opened for write.
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForRead, "a 3D solid");
            var topology = SolidTopology.Of(solid);
            solid.UpgradeOpen();
            var picked = Pick(topology, PartKind.Edge, args.Element("edges"));
            var before = Volume(solid);
            var radii = new DoubleCollection();
            var setbacks = new DoubleCollection();
            foreach (var _ in picked)
            {
                radii.Add(radius);
                setbacks.Add(0.0);
            }
            try
            {
                solid.FilletEdges(picked.Select(i => topology.EdgeIds[i]).ToArray(), radii, setbacks, setbacks);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not round " + picked.Length + " edge(s) at radius " + radius + " (" + ex.ErrorStatus
                    + "). A radius bigger than the faces beside an edge allow is the usual reason.");
            }
            return Changed(handle, solid, before, w =>
            {
                w.WriteNumber("radius", radius);
                RunDrawing.WriteNumbers(w, "edges", picked);
            });
        }

        /// <summary>Bevel edges of a solid (CHAMFEREDGE), measured from one face.</summary>
        public static RunResult Chamfer(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var distance = args.Number("distance");
            var other = args.Number("other_distance", distance);
            if (!(distance > 0) || !(other > 0)) throw new RunRefusal("Both chamfer distances must be above zero.");
            // Read first: the topology's Brep opens the solid itself, and it must be
            // let go before the solid is opened for write.
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForRead, "a 3D solid");
            var topology = SolidTopology.Of(solid);
            solid.UpgradeOpen();
            var faces = Pick(topology, PartKind.Face, args.Element("face"));
            if (faces.Length != 1)
                throw new RunRefusal("A chamfer is measured from one face, and that picks " + faces.Length + ". Give the face's number from " + Lister + ".");
            var face = faces[0];
            var onFace = topology.FaceEdges[face];
            int[] picked;
            if (args.Has("edges"))
            {
                picked = Pick(topology, PartKind.Edge, args.Element("edges"));
                var stray = picked.Where(e => !onFace.Contains(e)).ToArray();
                if (stray.Length > 0)
                    throw new RunRefusal("Edge " + string.Join(", ", stray) + " is not on face " + face + ". A chamfer's edges must be on the face it is "
                        + "measured from; face " + face + " has edges " + string.Join(", ", onFace) + ".");
            }
            else picked = onFace;
            if (picked.Length == 0) throw new RunRefusal("Face " + face + " has no edges to chamfer.");
            var before = Volume(solid);
            try
            {
                solid.ChamferEdges(picked.Select(i => topology.EdgeIds[i]).ToArray(), topology.FaceIds[face], distance, other);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not chamfer " + picked.Length + " edge(s) by " + distance + " x " + other + " (" + ex.ErrorStatus
                    + "). Distances bigger than the faces beside an edge allow are the usual reason.");
            }
            return Changed(handle, solid, before, w =>
            {
                w.WriteNumber("face", face);
                RunDrawing.WriteNumbers(w, "edges", picked);
                w.WriteNumber("distance", distance);
                w.WriteNumber("other_distance", other);
            });
        }

        /// <summary>Hollow a solid to a wall thickness, leaving chosen faces open (SOLIDEDIT Shell).</summary>
        public static RunResult Shell(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var thickness = args.Number("thickness");
            if (!(thickness > 0)) throw new RunRefusal("The wall thickness must be above zero.");
            var outward = args.Flag("outward", false);
            // Read first: the topology's Brep opens the solid itself, and it must be
            // let go before the solid is opened for write.
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForRead, "a 3D solid");
            var topology = SolidTopology.Of(solid);
            solid.UpgradeOpen();
            var removed = args.Has("remove") ? Pick(topology, PartKind.Face, args.Element("remove")) : new int[0];
            if (removed.Length >= topology.Faces.Count) throw new RunRefusal("Removing every face would leave nothing to shell.");
            var before = Volume(solid);
            try
            {
                // ShellBody: a positive offset grows outside the old faces, a negative one inside.
                solid.ShellBody(removed.Select(i => topology.FaceIds[i]).ToArray(), outward ? thickness : -thickness);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not shell it at " + thickness + " (" + ex.ErrorStatus + "). A wall thicker than the thinnest part "
                    + "of the solid, or rounded faces too tight for it, is the usual reason.");
            }
            return Changed(handle, solid, before, w =>
            {
                w.WriteNumber("thickness", thickness);
                w.WriteBoolean("outward", outward);
                RunDrawing.WriteNumbers(w, "removed_faces", removed);
            });
        }

        /// <summary>Push or pull flat faces of a solid (PRESSPULL on a face / SOLIDEDIT Extrude).</summary>
        public static RunResult PressPull(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var distance = args.Number("distance");
            if (distance == 0 || double.IsNaN(distance)) throw new RunRefusal("The distance cannot be zero: positive pulls the face out, negative pushes it in.");
            var taper = args.Number("taper", 0.0);
            if (Math.Abs(taper) >= Math.PI / 2) throw new RunRefusal("The taper must be less than 90 degrees either way.");
            // Read first: the topology's Brep opens the solid itself, and it must be
            // let go before the solid is opened for write.
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForRead, "a 3D solid");
            var topology = SolidTopology.Of(solid);
            solid.UpgradeOpen();
            var picked = Pick(topology, PartKind.Face, args.Element("faces"));
            var curved = picked.Where(i => topology.Faces[i].Kind != "plane").ToArray();
            if (curved.Length > 0)
                throw new RunRefusal("Face " + string.Join(", ", curved) + " is not flat (" + topology.Faces[curved[0]].Kind
                    + "). Press-pull here moves flat faces only.");
            var before = Volume(solid);
            try
            {
                solid.ExtrudeFaces(picked.Select(i => topology.FaceIds[i]).ToArray(), distance, taper);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not move those faces by " + distance + " (" + ex.ErrorStatus + "). Pushing a face in further than "
                    + "the solid is deep is the usual reason.");
            }
            return Changed(handle, solid, before, w =>
            {
                RunDrawing.WriteNumbers(w, "faces", picked);
                w.WriteNumber("distance", distance);
            });
        }

        /// <summary>A solid from a surface given a thickness (THICKEN). The surface is kept.</summary>
        public static RunResult Thicken(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var thickness = args.Number("thickness");
            if (!(thickness > 0)) throw new RunRefusal("The thickness must be above zero.");
            var bothSides = args.Flag("both_sides", false);
            var surface = RunDrawing.Open<DbSurface>(tr, db, handle, OpenMode.ForRead, "a surface. A flat closed outline is made a solid with autocad_extrude_profile");
            Solid3d solid;
            try
            {
                solid = surface.Thicken(thickness, bothSides);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not thicken it by " + thickness + " (" + ex.ErrorStatus + "). A thickness bigger than the surface's "
                    + "tightest curve is the usual reason.");
            }
            solid.SetDatabaseDefaults(db);
            var owner = (BlockTableRecord)tr.GetObject(surface.OwnerId, OpenMode.ForWrite);
            owner.AppendEntity(solid);
            tr.AddNewlyCreatedDBObject(solid, true);
            return RunResult.Done(w =>
            {
                w.WriteBoolean("created", true);
                w.WriteString("handle", solid.Handle.ToString());
                w.WriteString("surface", handle);
                w.WriteNumber("thickness", thickness);
                w.WriteBoolean("both_sides", bothSides);
                RunDrawing.Style(solid, db, tr, args, w);
                WriteVolume(w, "volume", solid);
            });
        }

        private static int[] Pick(SolidTopology topology, PartKind kind, JsonElement selector)
        {
            var parts = kind == PartKind.Edge ? topology.Edges : topology.Faces;
            var error = SolidPicks.Choose(parts, selector, kind, out var picked, topology.Low, topology.High);
            if (error != null) throw new RunRefusal(error);
            return picked;
        }

        private static bool IsClosed(Curve curve)
        {
            if (curve.Closed) return true;
            try
            {
                return curve.StartPoint.IsEqualTo(curve.EndPoint);
            }
            catch (AcException)
            {
                return false;
            }
        }

        private static RunResult Changed(string handle, Solid3d solid, double before, Action<Utf8JsonWriter> more) => RunResult.Done(w =>
        {
            w.WriteString("handle", handle);
            more(w);
            if (!double.IsNaN(before)) w.WriteNumber("volume_before", Math.Round(before, 6));
            WriteVolume(w, "volume_after", solid);
        });

        private static double Volume(Solid3d solid)
        {
            try
            {
                return solid.MassProperties.Volume;
            }
            catch (AcException)
            {
                return double.NaN;
            }
        }

        private static void WriteVolume(Utf8JsonWriter w, string name, Solid3d solid)
        {
            var volume = Volume(solid);
            if (!double.IsNaN(volume)) w.WriteNumber(name, Math.Round(volume, 6));
        }
    }

    /// <summary>
    /// A solid's faces and edges, numbered in the order the modelling kernel
    /// walks them. The same solid, unchanged, walks the same way, so a number
    /// from the listing picks the same edge in the next call.
    /// </summary>
    internal sealed class SolidTopology
    {
        private const int Samples = 16;
        // Reading the kernel is best effort: the Brep API throws its own exception
        // type, and a part it cannot describe is still listed and still picked by number.

        public List<TopologyPart> Edges { get; } = new List<TopologyPart>();
        public List<SubentityId> EdgeIds { get; } = new List<SubentityId>();
        public List<double> EdgeLengths { get; } = new List<double>();
        public List<Point3d[]> EdgeEnds { get; } = new List<Point3d[]>();
        public List<TopologyPart> Faces { get; } = new List<TopologyPart>();
        public List<SubentityId> FaceIds { get; } = new List<SubentityId>();
        public List<double> FaceAreas { get; } = new List<double>();
        public List<double[]?> FaceNormals { get; } = new List<double[]?>();
        public List<int[]> FaceEdges { get; } = new List<int[]>();
        /// <summary>The solid's box for the words (SolidPicks.Box); null when AutoCAD gave no extents.</summary>
        public double[]? Low { get; private set; }
        public double[]? High { get; private set; }

        public static SolidTopology Of(Solid3d solid)
        {
            var topology = new SolidTopology();
            var numbers = new Dictionary<string, int>();
            using (var brep = OpenBrep(solid))
            {
                foreach (Edge edge in brep.Edges)
                {
                    var id = edge.SubentityPath.SubentId;
                    numbers[Key(id)] = topology.Edges.Count;
                    topology.EdgeIds.Add(id);
                    topology.Add(edge);
                }
                foreach (BrepFace face in brep.Faces)
                {
                    var index = topology.Faces.Count;
                    var edges = new List<int>();
                    try
                    {
                        foreach (BoundaryLoop loop in face.Loops)
                            foreach (Edge edge in loop.Edges)
                                if (numbers.TryGetValue(Key(edge.SubentityPath.SubentId), out var number) && !edges.Contains(number))
                                    edges.Add(number);
                    }
                    catch (System.Exception)
                    {
                        // A loop the kernel cannot walk (a cone's tip, a sphere's pole): the
                        // face is still listed and picked by number.
                    }
                    topology.FaceIds.Add(face.SubentityPath.SubentId);
                    topology.FaceEdges.Add(edges.ToArray());
                    topology.Faces.Add(topology.FacePart(face, index, edges));
                }
            }
            try
            {
                var extents = solid.GeometricExtents;
                // Edges only: they are sampled on the true curves, where a face's kernel box can be loose.
                SolidPicks.Box(topology.Edges,
                    new[] { extents.MinPoint.X, extents.MinPoint.Y, extents.MinPoint.Z },
                    new[] { extents.MaxPoint.X, extents.MaxPoint.Y, extents.MaxPoint.Z }, out var low, out var high);
                topology.Low = low;
                topology.High = high;
            }
            catch (System.Exception)
            {
                // No extents: the words fall back to the box round the parts.
            }
            return topology;
        }

        /// <summary>
        /// A Brep built from the entity alone has no subentity paths: reading
        /// edge.SubentityPath on it throws, so every fillet, chamfer, shell and
        /// listing failed on every solid (cassette and bedroom models,
        /// 2026-11-05). Built from the solid's own path, each edge and face
        /// knows its SubentityId. The caller must have the solid open for read,
        /// not write, and upgrade only after this Brep is disposed.
        /// </summary>
        private static Brep OpenBrep(Solid3d solid)
        {
            if (solid.ObjectId.IsNull) return new Brep(solid);
            var path = new FullSubentityPath(new[] { solid.ObjectId }, new SubentityId(SubentityType.Null, IntPtr.Zero));
            return new Brep(path);
        }

        private static string Key(SubentityId id) => (int)id.Type + ":" + id.IndexPtr.ToInt64();

        private void Add(Edge edge)
        {
            var part = new TopologyPart { Index = Edges.Count, Kind = EdgeKind(edge) };
            var low = new[] { double.MaxValue, double.MaxValue, double.MaxValue };
            var high = new[] { double.MinValue, double.MinValue, double.MinValue };
            Point3d start = Point3d.Origin, end = Point3d.Origin;
            var length = double.NaN;
            try
            {
                // The edge's own bounded copy: an edge's underlying curve can run on for ever.
                using (var curve = edge.GetCurveAsNurb())
                {
                    var interval = curve.GetInterval();
                    double from = interval.LowerBound, to = interval.UpperBound;
                    for (var k = 0; k <= Samples; k++) Grow(low, high, curve.EvaluatePoint(from + (to - from) * k / Samples));
                    start = curve.EvaluatePoint(from);
                    end = curve.EvaluatePoint(to);
                    length = curve.GetLength(from, to, 1e-9);
                }
            }
            catch (System.Exception)
            {
                try
                {
                    start = edge.Vertex1.Point;
                    end = edge.Vertex2.Point;
                    Grow(low, high, start);
                    Grow(low, high, end);
                }
                catch (System.Exception)
                {
                }
            }
            if (low[0] == double.MaxValue)
            {
                low = high = new double[3];
                part.Known = false;
            }
            part.Min = low;
            part.Max = high;
            Edges.Add(part);
            EdgeLengths.Add(length);
            EdgeEnds.Add(new[] { start, end });
        }

        private TopologyPart FacePart(BrepFace face, int index, List<int> edges)
        {
            var part = new TopologyPart { Index = index, Kind = FaceKind(face) };
            var known = edges.Where(e => Edges[e].Known).ToList();
            if (known.Count > 0)
            {
                var low = new[] { double.MaxValue, double.MaxValue, double.MaxValue };
                var high = new[] { double.MinValue, double.MinValue, double.MinValue };
                foreach (var e in known)
                    for (var axis = 0; axis < 3; axis++)
                    {
                        low[axis] = Math.Min(low[axis], Edges[e].Min[axis]);
                        high[axis] = Math.Max(high[axis], Edges[e].Max[axis]);
                    }
                part.Min = low;
                part.Max = high;
            }
            else
            {
                // A face with no edges (a sphere, a torus): the kernel's own box round it.
                try
                {
                    var box = face.BoundBlock;
                    var low = box.GetMinimumPoint();
                    var high = box.GetMaximumPoint();
                    part.Min = new[] { low.X, low.Y, low.Z };
                    part.Max = new[] { high.X, high.Y, high.Z };
                }
                catch (System.Exception)
                {
                    part.Known = false;
                }
            }
            double area;
            try
            {
                area = face.GetArea();
            }
            catch (System.Exception)
            {
                area = double.NaN;
            }
            FaceAreas.Add(area);
            FaceNormals.Add(part.Kind == "plane" ? Normal(face, part) : null);
            return part;
        }

        /// <summary>Which way a flat face looks, for the listing only: picking goes by the box.</summary>
        private static double[]? Normal(BrepFace face, TopologyPart part)
        {
            try
            {
                var middle = new Point3d((part.Min[0] + part.Max[0]) / 2, (part.Min[1] + part.Max[1]) / 2, (part.Min[2] + part.Max[2]) / 2);
                var normal = face.Surface.GetClosestPointTo(middle).GetNormal().GetNormal();
                if (!face.IsOrientToSurface) normal = normal.Negate();
                return new[] { normal.X, normal.Y, normal.Z };
            }
            catch (System.Exception)
            {
                return null;
            }
        }

        private static string EdgeKind(Edge edge)
        {
            try
            {
                if (!(edge.Curve is ExternalCurve3d curve)) return "curve";
                if (curve.IsLineSegment || curve.IsLine) return "line";
                if (curve.IsCircularArc) return edge.Vertex1.Point.IsEqualTo(edge.Vertex2.Point) ? "circle" : "arc";
                if (curve.IsEllipticalArc) return "ellipse";
                if (curve.IsNurbCurve) return "spline";
                return "curve";
            }
            catch (System.Exception)
            {
                return "curve";
            }
        }

        private static string FaceKind(BrepFace face)
        {
            try
            {
                if (!(face.Surface is ExternalBoundedSurface surface)) return "surface";
                if (surface.IsPlane) return "plane";
                if (surface.IsCylinder) return "cylinder";
                if (surface.IsCone) return "cone";
                if (surface.IsSphere) return "sphere";
                if (surface.IsTorus) return "torus";
                if (surface.IsNurbs) return "nurbs";
                return "surface";
            }
            catch (System.Exception)
            {
                return "surface";
            }
        }

        private static void Grow(double[] low, double[] high, Point3d p)
        {
            low[0] = Math.Min(low[0], p.X);
            low[1] = Math.Min(low[1], p.Y);
            low[2] = Math.Min(low[2], p.Z);
            high[0] = Math.Max(high[0], p.X);
            high[1] = Math.Max(high[1], p.Y);
            high[2] = Math.Max(high[2], p.Z);
        }
    }
}
