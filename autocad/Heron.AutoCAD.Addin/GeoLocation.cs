using System;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Heron.AutoCAD.Bridge;
using AcException = Autodesk.AutoCAD.Runtime.Exception;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The drawing's geographic location (Insert > Location, GEOGRAPHICLOCATION,
    /// D-111): which drawing point is at which latitude and longitude, and which
    /// way north is. COM has no call for it; .NET has GeoLocationData, kept in
    /// model space's extension dictionary.
    ///
    /// Every set is proved with AutoCAD's own transform before the transaction
    /// commits: the drawing point must read back at the place asked, and a
    /// point 100 m along the north asked must read 100 m north on the ground.
    /// The sun's place (LATITUDE, LONGITUDE, autocad_set_sun) stays the server's.
    /// </summary>
    internal static class GeoLocation
    {
        // A world-wide grid in metres, as Autodesk's own ObjectARX sample uses.
        private const string DefaultSystem = "WORLD-MERCATOR";

        public static RunResult Read(Database db, Transaction tr)
        {
            var id = Find(db);
            if (id.IsNull) return RunResult.Done(w => w.WriteBoolean("located", false));
            var geo = (GeoLocationData)tr.GetObject(id, OpenMode.ForRead);
            return RunResult.Done(w =>
            {
                w.WriteBoolean("located", true);
                Write(w, geo);
            });
        }

        public static RunResult Change(Database db, Transaction tr, RunArgs args)
        {
            var action = args.Text("action", "set").Trim().ToLowerInvariant();
            var id = Find(db);
            if (action == "remove")
            {
                if (id.IsNull) throw new RunRefusal("This drawing has no geographic location to remove.");
                var old = (GeoLocationData)tr.GetObject(id, OpenMode.ForWrite);
                var oldSystem = old.CoordinateSystem;
                old.Erase();
                return RunResult.Done(w =>
                {
                    w.WriteBoolean("removed", true);
                    w.WriteString("coordinate_system", oldSystem);
                });
            }
            if (action != "set") throw new RunRefusal("The action must be 'set' or 'remove'.");

            var latitude = args.Number("latitude");
            var longitude = args.Number("longitude");
            var why = GeoPlace.Ranges(latitude, longitude);
            if (why != null) throw new RunRefusal(why);
            var elevation = args.Number("elevation", 0);
            var units = db.Insunits;
            if (units == UnitsValue.Undefined)
                throw new RunRefusal("The drawing has no units (INSUNITS is 0), so a metre on the ground cannot be matched to the drawing. "
                    + "Set the units first with autocad_drawing_setup.");
            var metresPerUnit = UnitsConverter.GetConversionFactor(units, UnitsValue.Meters);
            var at = args.Numbers("point");
            var point = at.Length >= 2 ? new Point3d(at[0], at[1], at.Length > 2 ? at[2] : 0) : Point3d.Origin;
            var northAngle = args.Number("north_angle", 0);
            var north = GeoPlace.NorthVector(northAngle);
            var system = args.Text("coordinate_system").Trim();
            if (system.Length == 0) system = DefaultSystem;

            var made = id.IsNull;
            GeoLocationData geo;
            var inTransaction = true;
            if (made)
            {
                geo = new GeoLocationData { BlockTableRecordId = SymbolUtilityServices.GetBlockModelSpaceId(db) };
                geo.PostToDb();
                try
                {
                    tr.AddNewlyCreatedDBObject(geo, true);
                }
                catch (System.Exception ex) when (ex is AcException || ex is InvalidOperationException)
                {
                    // Posted outside the transaction: a refusal below erases it by hand.
                    inTransaction = false;
                }
            }
            else
            {
                geo = (GeoLocationData)tr.GetObject(id, OpenMode.ForWrite);
            }

            string form;
            try
            {
                form = Place(geo, system, units, metresPerUnit, point, latitude, longitude, elevation, north);
            }
            catch (System.Exception) when (made && !inTransaction)
            {
                try
                {
                    geo.EraseFromDb();
                }
                catch (System.Exception ex)
                {
                    HeronLog.Error("Erasing a half-made geographic location", ex);
                }
                throw;
            }

            return RunResult.Done(w =>
            {
                w.WriteBoolean("located", true);
                w.WriteBoolean("made", made);
                // Which way the reference point was written that AutoCAD read back right (D-111).
                w.WriteString("reference_form", form);
                Write(w, geo);
            });
        }

        /// <summary>
        /// Writes the location and returns which form of reference point AutoCAD
        /// read back right: "grid" (the site in the coordinate system's metres) or
        /// "lon_lat". Throws a refusal when neither does.
        /// </summary>
        private static string Place(
            GeoLocationData geo, string system, UnitsValue units, double metresPerUnit, Point3d point,
            double latitude, double longitude, double elevation, double[] north)
        {
            try
            {
                geo.CoordinateSystem = system;
            }
            catch (AcException ex)
            {
                throw new RunRefusal("AutoCAD does not know the coordinate system '" + system + "' (" + ex.ErrorStatus
                    + "). Leave it out for " + DefaultSystem + ", or give a code from AutoCAD's GEOGRAPHICLOCATION list.");
            }
            geo.TypeOfCoordinates = TypeOfCoordinates.CoordinateTypeGrid;
            geo.UpDirection = Vector3d.ZAxis;
            geo.ScaleFactor = 1.0;

            // The site in the coordinate system's own metres: read through a plain
            // one-to-one location first (both points at 0,0, north up, metres).
            geo.ScaleEstimationMethod = ScaleEstimationMethod.ScaleEstMethodUnity;
            geo.HorizontalUnits = UnitsValue.Meters;
            geo.VerticalUnits = UnitsValue.Meters;
            geo.DesignPoint = Point3d.Origin;
            geo.ReferencePoint = Point3d.Origin;
            geo.NorthDirectionVector = Vector2d.YAxis;
            geo.UpdateTransformationMatrix();
            var grid = geo.TransformFromLonLatAlt(new Point3d(longitude, latitude, elevation));

            var step = GeoPlace.CheckMetres / metresPerUnit;
            var ahead = new Point3d(point.X + north[0] * step, point.Y + north[1] * step, point.Z);
            string? why = null;
            foreach (var form in new[] { "grid", "lon_lat" })
            {
                geo.HorizontalUnits = units;
                geo.VerticalUnits = units;
                geo.DesignPoint = point;
                geo.ReferencePoint = form == "grid" ? grid : new Point3d(longitude, latitude, elevation);
                geo.NorthDirectionVector = new Vector2d(north[0], north[1]);
                // Scale worked out at the site, so a metre drawn is a metre on the ground there.
                geo.ScaleEstimationMethod = ScaleEstimationMethod.ScaleEstMethodReferencePoint;
                geo.UpdateTransformationMatrix();
                var back = geo.TransformToLonLatAlt(point);
                why = GeoPlace.SamePlace(latitude, longitude, back.Y, back.X);
                if (why == null)
                {
                    var there = geo.TransformToLonLatAlt(ahead);
                    why = GeoPlace.NorthCheck(back.Y, back.X, there.Y, there.X);
                }
                if (why == null) return form;
            }
            throw new RunRefusal(why ?? "AutoCAD did not take the location.");
        }

        private static ObjectId Find(Database db)
        {
            try
            {
                return db.GeoDataObject;
            }
            catch (AcException)
            {
                // AutoCAD answers "none" with an error.
                return ObjectId.Null;
            }
        }

        private static void Write(Utf8JsonWriter w, GeoLocationData geo)
        {
            w.WriteString("coordinate_system", geo.CoordinateSystem);
            w.WriteString("type_of_coordinates", geo.TypeOfCoordinates.ToString());
            var design = geo.DesignPoint;
            var reference = geo.ReferencePoint;
            RunDrawing.WritePoint(w, "point", design.X, design.Y, design.Z);
            RunDrawing.WritePoint(w, "reference_point", reference.X, reference.Y, reference.Z);
            var vector = geo.NorthDirectionVector;
            w.WriteNumber("north_angle", Math.Round(GeoPlace.NorthAngle(vector.X, vector.Y), 12));
            w.WriteString("units", geo.HorizontalUnits.ToString());
            w.WriteString("scale_method", geo.ScaleEstimationMethod.ToString());
            try
            {
                var place = geo.TransformToLonLatAlt(design);
                w.WriteNumber("latitude", Math.Round(place.Y, 9));
                w.WriteNumber("longitude", Math.Round(place.X, 9));
                w.WriteNumber("elevation", Math.Round(place.Z, 6));
            }
            catch (AcException ex)
            {
                w.WriteNull("latitude");
                w.WriteNull("longitude");
                w.WriteString("place_note", "AutoCAD could not turn the drawing point into a latitude and longitude (" + ex.ErrorStatus + ").");
            }
        }
    }
}
