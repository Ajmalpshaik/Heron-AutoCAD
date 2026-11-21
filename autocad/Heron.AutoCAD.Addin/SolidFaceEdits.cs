using System;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The rest of SOLIDEDIT (D-113): offset, taper, move and delete faces,
    /// imprint and separate. Faces are picked as the other solid edits pick
    /// them: a word or the numbers autocad_list_solid_faces_and_edges gives,
    /// from the Brep built from the solid's own path (the D-40 fix). Main
    /// thread, inside PluginRunner's lock and transaction.
    /// </summary>
    internal static class SolidFaceEdits
    {
        private const string Lister = "autocad_list_solid_faces_and_edges";

        /// <summary>Offset faces (SOLIDEDIT Face Offset): positive grows the solid there, negative shrinks it.</summary>
        public static RunResult Offset(Database db, Transaction tr, RunArgs args)
        {
            var distance = args.Number("distance");
            if (distance == 0 || double.IsNaN(distance) || double.IsInfinity(distance))
                throw new RunRefusal("The distance cannot be zero: positive moves the faces out of the solid, negative into it.");
            var edit = Faces(db, tr, args);
            var before = SolidOperations.Volume(edit.Solid);
            try
            {
                edit.Solid.OffsetFaces(edit.Ids, distance);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not offset " + Count(edit.Picked) + " by " + distance + " (" + ex.ErrorStatus + "). Offsetting "
                    + "into the solid further than it is deep, or a hole shrunk past nothing, is the usual reason.");
            }
            return SolidOperations.Changed(edit.Handle, edit.Solid, before, w =>
            {
                RunDrawing.WriteNumbers(w, "faces", edit.Picked);
                w.WriteNumber("distance", distance);
            });
        }

        /// <summary>
        /// Taper faces (SOLIDEDIT Face Taper) about a plane square to the draft
        /// direction: by default up, through the bottom of the picked faces, so
        /// their bottom edges stay where they are.
        /// </summary>
        public static RunResult Taper(Database db, Transaction tr, RunArgs args)
        {
            var angle = args.Number("angle");
            if (angle == 0 || !(Math.Abs(angle) < Math.PI / 2))
                throw new RunRefusal("The taper must be more than 0 and less than 90 degrees either way.");
            var direction = args.Has("direction") ? args.Numbers("direction") : new[] { 0.0, 0.0, 1.0 };
            var unit = FaceEditMath.Unit(direction)
                ?? throw new RunRefusal("The taper's direction must be three numbers [x, y, z] with some length, e.g. [0, 0, 1] for up.");
            var edit = Faces(db, tr, args);
            double[] pivot;
            if (args.Has("base"))
            {
                pivot = args.Numbers("base");
                if (pivot.Length != 3) throw new RunRefusal("The taper's base point must be [x, y, z].");
            }
            else
            {
                var unknown = edit.Picked.Where(i => !edit.Topology.Faces[i].Known).ToArray();
                if (unknown.Length > 0)
                    throw new RunRefusal("Heron could not tell where face " + string.Join(", ", unknown) + " is, so it cannot find the bottom to "
                        + "taper from. Give the base point.");
                pivot = FaceEditMath.TaperBase(edit.Picked.Select(i => edit.Topology.Faces[i].Min).ToList(),
                    edit.Picked.Select(i => edit.Topology.Faces[i].Max).ToList(), unit)
                    ?? throw new RunRefusal("Heron could not work out where to taper from. Give the base point.");
            }
            var before = SolidOperations.Volume(edit.Solid);
            try
            {
                edit.Solid.TaperFaces(edit.Ids, new Point3d(pivot[0], pivot[1], pivot[2]), new Vector3d(unit[0], unit[1], unit[2]), angle);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not taper " + Count(edit.Picked) + " by that angle (" + ex.ErrorStatus + "). A face square to the "
                    + "taper's direction (a top face, tapering up) cannot lean, and a taper that would cross the faces beside it is refused.");
            }
            return SolidOperations.Changed(edit.Handle, edit.Solid, before, w =>
            {
                RunDrawing.WriteNumbers(w, "faces", edit.Picked);
                RunDrawing.WritePoint(w, "base", pivot[0], pivot[1], pivot[2]);
                RunDrawing.WritePoint(w, "direction", unit[0], unit[1], unit[2]);
            });
        }

        /// <summary>Move faces (SOLIDEDIT Face Move): the faces beside them stretch to follow.</summary>
        public static RunResult Move(Database db, Transaction tr, RunArgs args)
        {
            var by = args.Numbers("by");
            if (by.Length != 3 || by.Any(v => double.IsNaN(v) || double.IsInfinity(v)) || FaceEditMath.Unit(by) == null)
                throw new RunRefusal("Give how far to move the faces as [dx, dy, dz], not all zero.");
            var edit = Faces(db, tr, args);
            var before = SolidOperations.Volume(edit.Solid);
            try
            {
                edit.Solid.TransformFaces(edit.Ids, Matrix3d.Displacement(new Vector3d(by[0], by[1], by[2])));
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not move " + Count(edit.Picked) + " that far (" + ex.ErrorStatus + "). Moving a face through "
                    + "another face, or one the faces beside it cannot stretch to follow, is the usual reason.");
            }
            return SolidOperations.Changed(edit.Handle, edit.Solid, before, w =>
            {
                RunDrawing.WriteNumbers(w, "faces", edit.Picked);
                RunDrawing.WritePoint(w, "by", by[0], by[1], by[2]);
            });
        }

        /// <summary>Delete faces (SOLIDEDIT Face Delete): a fillet, a chamfer or a hole goes, and the faces round it grow to close the gap.</summary>
        public static RunResult Delete(Database db, Transaction tr, RunArgs args)
        {
            var edit = Faces(db, tr, args);
            if (edit.Picked.Length >= edit.Topology.Faces.Count)
                throw new RunRefusal("That is every face of the solid: deleting them all leaves nothing. Erase the solid instead.");
            var before = SolidOperations.Volume(edit.Solid);
            try
            {
                edit.Solid.RemoveFaces(edit.Ids);
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not delete " + Count(edit.Picked) + " (" + ex.ErrorStatus + "). A face is deleted only when the "
                    + "faces round it can grow to close the gap: a fillet, a chamfer or a hole, not a box's side.");
            }
            return SolidOperations.Changed(edit.Handle, edit.Solid, before, w => RunDrawing.WriteNumbers(w, "faces", edit.Picked));
        }

        /// <summary>
        /// Imprint objects onto a solid (SOLIDEDIT Body Imprint): where each
        /// one meets the solid's faces, those faces split along it. The objects
        /// are kept, as SOLIDEDIT keeps them unless told to delete them.
        /// </summary>
        public static RunResult Imprint(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var objects = args.Texts("objects");
            if (objects.Length == 0) throw new RunRefusal("Name at least one object to imprint, by handle.");
            // Read first: the topology's Brep opens the solid itself, and it must be
            // let go before the solid is opened for write.
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForRead, "a 3D solid");
            var topology = SolidTopology.Of(solid);
            var marks = objects.Distinct(StringComparer.OrdinalIgnoreCase).Select(h =>
            {
                var mark = RunDrawing.Open<Entity>(tr, db, h, OpenMode.ForRead, "a line, arc, circle, polyline, spline, region or solid");
                if (mark.ObjectId == solid.ObjectId) throw new RunRefusal("A solid cannot be imprinted with itself.");
                if (!(mark is Curve || mark is Region || mark is Solid3d || mark is Body))
                    throw new RunRefusal(h + " is " + RunDrawing.Kind(mark) + ". Imprint takes a line, arc, circle, polyline, spline, region or solid.");
                return (Handle: h, Entity: mark);
            }).ToArray();
            solid.UpgradeOpen();
            foreach (var mark in marks)
            {
                try
                {
                    solid.ImprintEntity(mark.Entity);
                }
                catch (AcException ex)
                {
                    throw new RunRefusal("AutoCAD would not imprint " + mark.Handle + " (" + ex.ErrorStatus + "). It must touch or cross the solid's faces.");
                }
            }
            return RunResult.Done(w =>
            {
                w.WriteString("handle", handle);
                w.WriteStartArray("objects");
                foreach (var mark in marks) w.WriteStringValue(mark.Handle);
                w.WriteEndArray();
                w.WriteNumber("faces_before", topology.Faces.Count);
                w.WriteNumber("edges_before", topology.Edges.Count);
                SolidOperations.WriteVolume(w, "volume", solid);
            });
        }

        /// <summary>
        /// Separate a solid made of pieces that do not touch (SOLIDEDIT Body
        /// Separate): it keeps one piece, and each other piece becomes a new
        /// solid with its layer, colour and the rest.
        /// </summary>
        public static RunResult Separate(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForWrite, "a 3D solid");
            var before = SolidOperations.Volume(solid);
            Solid3d[] pieces;
            try
            {
                pieces = solid.SeparateBody();
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD would not separate it (" + ex.ErrorStatus + ").");
            }
            if (pieces == null || pieces.Length == 0)
                throw new RunRefusal(handle + " is one piece already: there is nothing to separate. A union of solids that touch stays one solid.");
            var owner = (BlockTableRecord)tr.GetObject(solid.OwnerId, OpenMode.ForWrite);
            foreach (var piece in pieces)
            {
                piece.SetPropertiesFrom(solid);
                owner.AppendEntity(piece);
                tr.AddNewlyCreatedDBObject(piece, true);
            }
            return RunResult.Done(w =>
            {
                w.WriteString("handle", handle);
                if (!double.IsNaN(before)) w.WriteNumber("volume_before", Math.Round(before, 6));
                w.WriteNumber("piece_count", pieces.Length + 1);
                w.WriteStartArray("pieces");
                foreach (var piece in new[] { solid }.Concat(pieces))
                {
                    w.WriteStartObject();
                    w.WriteString("handle", piece.Handle.ToString());
                    SolidOperations.WriteVolume(w, "volume", piece);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        private sealed class FaceEdit
        {
            public string Handle = "";
            public Solid3d Solid = null!;
            public SolidTopology Topology = null!;
            public int[] Picked = new int[0];
            public SubentityId[] Ids = new SubentityId[0];
        }

        /// <summary>The solid open for write and the faces picked on it, by word or number.</summary>
        private static FaceEdit Faces(Database db, Transaction tr, RunArgs args)
        {
            var handle = args.Text("handle");
            // Read first: the topology's Brep opens the solid itself, and it must be
            // let go before the solid is opened for write.
            var solid = RunDrawing.Open<Solid3d>(tr, db, handle, OpenMode.ForRead, "a 3D solid");
            var topology = SolidTopology.Of(solid);
            solid.UpgradeOpen();
            if (!args.Has("faces")) throw new RunRefusal("Name the faces: a word ('top', 'front'...) or numbers from " + Lister + ".");
            var picked = SolidOperations.Pick(topology, PartKind.Face, args.Element("faces"));
            return new FaceEdit
            {
                Handle = handle,
                Solid = solid,
                Topology = topology,
                Picked = picked,
                Ids = picked.Select(i => topology.FaceIds[i]).ToArray(),
            };
        }

        private static string Count(int[] faces) => faces.Length == 1 ? "face " + faces[0] : faces.Length + " faces";
    }
}
