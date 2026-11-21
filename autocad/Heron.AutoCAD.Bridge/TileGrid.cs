using System;
using System.Collections.Generic;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Where the tiles of a super hatch go: a grid from an origin, turned by an
    /// angle, with just enough tiles to cover the area's box. The plug-in then
    /// clips the lot to the boundary. Pure, so it is tested offline.
    /// </summary>
    public static class TileGrid
    {
        /// <summary>More than this and AutoCAD would stall; the chat is asked for a bigger spacing.</summary>
        public const int MostTiles = 10000;

        /// <summary>Each image tile is a raster image AutoCAD keeps loaded: fewer of them.</summary>
        public const int MostImageTiles = 2000;

        /// <summary>
        /// Null and each tile's insertion point (world x, y), or why not.
        /// <paramref name="tileMin"/> / <paramref name="tileMax"/> are the tile's
        /// extents from its insertion point, in the grid's own directions.
        /// </summary>
        public static string? Positions(
            double[] areaMin, double[] areaMax, double[] origin, double stepX, double stepY, double angle,
            double[] tileMin, double[] tileMax, out List<double[]> positions, int most = MostTiles)
        {
            positions = new List<double[]>();
            if (!(stepX > 0) || !(stepY > 0)) return "The tile spacing must be above zero both ways.";

            double cos = Math.Cos(angle), sin = Math.Sin(angle);
            double uLow = double.MaxValue, uHigh = double.MinValue, vLow = double.MaxValue, vHigh = double.MinValue;
            foreach (var x in new[] { areaMin[0], areaMax[0] })
                foreach (var y in new[] { areaMin[1], areaMax[1] })
                {
                    double dx = x - origin[0], dy = y - origin[1];
                    double u = dx * cos + dy * sin, v = -dx * sin + dy * cos;
                    uLow = Math.Min(uLow, u);
                    uHigh = Math.Max(uHigh, u);
                    vLow = Math.Min(vLow, v);
                    vHigh = Math.Max(vHigh, v);
                }

            // Tile i covers u from i*step + tileMin to i*step + tileMax; keep the
            // ones that overlap the area, not those that only touch its edge.
            var iLow = Math.Floor(Clean((uLow - tileMax[0]) / stepX)) + 1;
            var iHigh = Math.Ceiling(Clean((uHigh - tileMin[0]) / stepX)) - 1;
            var jLow = Math.Floor(Clean((vLow - tileMax[1]) / stepY)) + 1;
            var jHigh = Math.Ceiling(Clean((vHigh - tileMin[1]) / stepY)) - 1;
            if (iHigh < iLow || jHigh < jLow) return "The tile does not reach the area.";

            var count = (iHigh - iLow + 1) * (jHigh - jLow + 1);
            if (count > most)
                return "Covering this area takes " + count.ToString("0") + " tiles; one super hatch places at most " + most
                    + (most < MostTiles ? " of this kind" : "") + ". Make the spacing or the scale bigger, or hatch a smaller area.";

            for (var j = jLow; j <= jHigh; j++)
                for (var i = iLow; i <= iHigh; i++)
                {
                    double along = i * stepX, across = j * stepY;
                    positions.Add(new[] { origin[0] + along * cos - across * sin, origin[1] + along * sin + across * cos });
                }
            return null;
        }

        public const int MostArcSteps = 256;

        /// <summary>
        /// How many straight steps follow an arc of <paramref name="sweep"/>
        /// radians and <paramref name="radius"/> to within
        /// <paramref name="tolerance"/> (the gap between a step and the arc).
        /// A clip is a polygon, so a big arc needs more steps than a small one.
        /// </summary>
        public static int ArcSteps(double sweep, double radius, double tolerance)
        {
            sweep = Math.Abs(sweep);
            radius = Math.Abs(radius);
            if (!(sweep > 0) || !(radius > 0)) return 4;
            var ratio = tolerance > 0 ? Math.Min(1.0, tolerance / radius) : 1.0;
            var step = 2 * Math.Acos(1 - ratio);
            var steps = step > 0 ? (int)Math.Ceiling(Math.Min(sweep / step, MostArcSteps)) : MostArcSteps;
            return Math.Max(4, Math.Min(MostArcSteps, steps));
        }

        /// <summary>Rounding noise off, so a tile that ends exactly on the edge is not counted twice.</summary>
        private static double Clean(double value) => Math.Round(value, 9);
    }
}
