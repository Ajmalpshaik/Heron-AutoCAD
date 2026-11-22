using System;
using System.Globalization;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The pure side of the drawing's geographic location (GEOGRAPHICLOCATION,
    /// D-111): which way north is, and the checks that AutoCAD's own transform
    /// puts the drawing point at the place asked, with north where asked.
    /// Tested offline; the plug-in writes the location.
    ///
    /// The north angle is radians from the drawing's +Y (up the screen) to true
    /// north, clockwise, as a compass reads: 0 = north is up.
    /// </summary>
    public static class GeoPlace
    {
        /// <summary>Metres in one degree of latitude, near enough for a 10 % check.</summary>
        public const double MetresPerDegree = 111_320.0;

        /// <summary>How far apart in degrees the point asked and the point read back may be (about 0.1 m).</summary>
        public const double SameDegrees = 1e-6;

        /// <summary>The north check walks this far, in metres, and allows a tenth of it either way.</summary>
        public const double CheckMetres = 100.0;

        public static double[] NorthVector(double northAngle) => new[] { Math.Sin(northAngle), Math.Cos(northAngle) };

        /// <summary>The north angle of a direction in the drawing, 0 to 2 pi.</summary>
        public static double NorthAngle(double x, double y)
        {
            var angle = Math.Atan2(x, y);
            if (angle < 0) angle += 2 * Math.PI;
            return Math.Abs(angle - 2 * Math.PI) < 1e-12 ? 0 : angle;
        }

        /// <summary>Null when the latitude and longitude are a place on Earth, else why not.</summary>
        public static string? Ranges(double latitude, double longitude)
        {
            if (double.IsNaN(latitude) || latitude < -90 || latitude > 90) return "The latitude must be -90 to 90 degrees, north positive.";
            if (double.IsNaN(longitude) || longitude < -180 || longitude > 180) return "The longitude must be -180 to 180 degrees, east positive.";
            if (Math.Abs(latitude) > 85) return "Heron sets a place up to 85 degrees north or south; the Mercator map it uses does not reach the poles.";
            return null;
        }

        /// <summary>Null when AutoCAD reads the point back at the place asked, else why not.</summary>
        public static string? SamePlace(double askedLatitude, double askedLongitude, double readLatitude, double readLongitude)
        {
            if (Math.Abs(readLatitude - askedLatitude) <= SameDegrees && Math.Abs(Wrap(readLongitude - askedLongitude)) <= SameDegrees) return null;
            return "AutoCAD reads the drawing point back at latitude " + Num(readLatitude) + ", longitude " + Num(readLongitude)
                + ", not at " + Num(askedLatitude) + ", " + Num(askedLongitude) + " as asked.";
        }

        /// <summary>
        /// Null when a point <see cref="CheckMetres"/> along the asked north reads
        /// that far north on the ground, within a tenth, else why not. This catches
        /// north the wrong way and the drawing units read wrong.
        /// </summary>
        public static string? NorthCheck(double latitude, double longitude, double aheadLatitude, double aheadLongitude)
        {
            var north = (aheadLatitude - latitude) * MetresPerDegree;
            var east = Wrap(aheadLongitude - longitude) * MetresPerDegree * Math.Cos(latitude * Math.PI / 180);
            var slack = CheckMetres / 10;
            if (Math.Abs(north - CheckMetres) <= slack && Math.Abs(east) <= slack) return null;
            return "A point " + Num(CheckMetres) + " m along the north asked reads " + Num(north) + " m north and " + Num(east)
                + " m east on the ground, so north or the drawing units came out wrong.";
        }

        private static double Wrap(double degrees)
        {
            while (degrees > 180) degrees -= 360;
            while (degrees < -180) degrees += 360;
            return degrees;
        }

        private static string Num(double value) => Math.Round(value, 6).ToString("0.######", CultureInfo.InvariantCulture);
    }
}
