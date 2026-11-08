using System;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The real-world size of a material's texture and bump image. AutoCAD keeps
    /// a map's size in its 4x4 map transform (DXF group 43 on the material). Left
    /// as the identity, one image tile is 1 drawing unit (1 mm in a metric
    /// drawing), so a wood or stone photo renders as a flat colour. Scaling the
    /// diagonal by 1/size makes one tile that size. Pure, so it is tested offline.
    /// </summary>
    public static class TextureScale
    {
        /// <summary>The biggest tile accepted, in drawing units (1 km in millimetres).</summary>
        public const double Largest = 1_000_000;

        /// <summary>
        /// Null and the 16 values of the map transform, row by row, or why not.
        /// Width runs along X; height along Y and Z (on a wall, up the wall).
        /// Height defaults to the width (a square image).
        /// </summary>
        public static string? Matrix(double width, double? height, out double[] values)
        {
            values = Array.Empty<double>();
            var tall = height ?? width;
            if (!Usable(width) || !Usable(tall))
                return "The texture size must be above zero and at most " + Largest.ToString("0") + " drawing units.";

            values = new double[16];
            values[0] = 1.0 / width;
            values[5] = 1.0 / tall;
            values[10] = 1.0 / tall;
            values[15] = 1.0;
            return null;
        }

        private static bool Usable(double value) =>
            !double.IsNaN(value) && !double.IsInfinity(value) && value > 0 && value <= Largest;
    }
}
