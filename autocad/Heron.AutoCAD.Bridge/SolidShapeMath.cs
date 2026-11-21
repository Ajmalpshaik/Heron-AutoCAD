using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The sums behind the pyramid (D-112): sizes checked, radii turned from
    /// "to a corner" into "to a side" (what AutoCAD's CreatePyramid takes),
    /// and which way to turn the made pyramid so a side faces the front.
    /// Pure, so every rule is tested offline.
    /// </summary>
    public static class PyramidMath
    {
        public const int FewestSides = 3;
        public const int MostSides = 32;

        /// <summary>Null, or why these sizes make no pyramid. Radii are to the middle of a side.</summary>
        public static string? Check(int sides, double bottom, double top, double height)
        {
            if (sides < FewestSides || sides > MostSides)
                return "A pyramid has " + FewestSides + " to " + MostSides + " sides, as AutoCAD's PYRAMID allows.";
            if (!(height > 0)) return "The height must be above zero.";
            if (!(bottom >= 0) || !(top >= 0) || double.IsInfinity(bottom) || double.IsInfinity(top))
                return "The radii cannot be below zero.";
            if (bottom == 0 && top == 0) return "A pyramid needs a base: give a radius above zero.";
            return null;
        }

        /// <summary>
        /// The radius to the middle of a side (the circle inside the polygon,
        /// what CreatePyramid takes), from one given to a side or to a corner.
        /// </summary>
        public static double ToSide(double radius, int sides, bool toCorner) =>
            toCorner ? radius * Math.Cos(Math.PI / sides) : radius;

        /// <summary>The radius to a corner of a regular polygon whose sides are <paramref name="sideRadius"/> from its centre.</summary>
        public static double CornerRadius(double sideRadius, int sides) => sideRadius / Math.Cos(Math.PI / sides);

        /// <summary>The area of a regular polygon whose sides are <paramref name="sideRadius"/> from its centre.</summary>
        public static double Area(double sideRadius, int sides) => sides * sideRadius * sideRadius * Math.Tan(Math.PI / sides);

        /// <summary>A pyramid's or a frustum's volume: h/3 (A1 + A2 + sqrt(A1 A2)).</summary>
        public static double Volume(double height, int sides, double bottom, double top)
        {
            var a1 = Area(bottom, sides);
            var a2 = Area(top, sides);
            return height / 3.0 * (a1 + a2 + Math.Sqrt(a1 * a2));
        }

        /// <summary>
        /// How far to turn the pyramid about its axis (radians, anticlockwise)
        /// so its corners sit where asked. <paramref name="cornerAngle"/> is
        /// any one corner's angle as AutoCAD made it; <paramref name="rotation"/>
        /// is the turn asked for: 0 puts one side square to the front (facing
        /// -Y, what the Front view looks at), as a box sits. The smallest turn
        /// that gets there, never more than half a side either way.
        /// </summary>
        public static double Turn(double cornerAngle, int sides, double rotation)
        {
            var step = 2 * Math.PI / sides;
            var wanted = -Math.PI / 2 + Math.PI / sides + rotation;
            var turn = (wanted - cornerAngle) % step;
            if (turn < 0) turn += step;
            if (turn > step / 2 + 1e-12) turn -= step;
            return turn;
        }

        /// <summary>
        /// The pyramid's wider end, read from its corners as AutoCAD made it:
        /// the centre of that end, the angle and distance of one corner about
        /// it, and the lowest and highest points. False when there are not
        /// three corners at one level to go by.
        /// </summary>
        public static bool WideEnd(IList<double[]> vertices, out double[] centre, out double cornerAngle, out double cornerRadius,
            out double low, out double high)
        {
            centre = new double[3];
            cornerAngle = cornerRadius = 0;
            low = high = 0;
            var points = vertices.Where(v => v != null && v.Length >= 3).ToList();
            if (points.Count < 3) return false;
            low = points.Min(p => p[2]);
            high = points.Max(p => p[2]);
            var size = points.Max(p => Math.Max(Math.Abs(p[0]), Math.Max(Math.Abs(p[1]), Math.Abs(p[2]))));
            var tolerance = 1e-6 * Math.Max(size, 1.0);

            List<double[]>? best = null;
            double bestRadius = -1;
            foreach (var level in Levels(points, tolerance))
            {
                if (level.Count < FewestSides) continue;
                var cx = level.Average(p => p[0]);
                var cy = level.Average(p => p[1]);
                var radius = level.Average(p => Math.Sqrt((p[0] - cx) * (p[0] - cx) + (p[1] - cy) * (p[1] - cy)));
                if (radius > bestRadius + tolerance)
                {
                    best = level;
                    bestRadius = radius;
                }
            }
            if (best == null || !(bestRadius > tolerance)) return false;
            var x = best.Average(p => p[0]);
            var y = best.Average(p => p[1]);
            centre = new[] { x, y, best[0][2] };
            cornerAngle = Math.Atan2(best[0][1] - y, best[0][0] - x);
            cornerRadius = bestRadius;
            return true;
        }

        private static IEnumerable<List<double[]>> Levels(List<double[]> points, double tolerance)
        {
            var levels = new List<List<double[]>>();
            foreach (var p in points.OrderBy(p => p[2]))
            {
                if (levels.Count > 0 && Math.Abs(levels[levels.Count - 1][0][2] - p[2]) <= tolerance) levels[levels.Count - 1].Add(p);
                else levels.Add(new List<double[]> { p });
            }
            return levels;
        }
    }

    /// <summary>
    /// The sums behind the polysolid (D-112): where the wall's two faces run,
    /// as distances to the left of the path, and which way AutoCAD's offset
    /// went. Pure, so every rule is tested offline.
    /// </summary>
    public static class PolysolidMath
    {
        public static readonly string[] Sides = { "center", "left", "right" };

        /// <summary>
        /// Null and the wall's two faces as distances to the left of the path,
        /// looking along it (negative is to the right), or why it cannot be
        /// made. 'center' puts the path down the middle of the wall; 'left' and
        /// 'right' put the wall on that side of it.
        /// </summary>
        public static string? Faces(double width, double height, string side, out double first, out double second)
        {
            first = second = 0;
            if (!(width > 0) || double.IsInfinity(width)) return "The wall's width must be above zero.";
            if (!(height > 0) || double.IsInfinity(height)) return "The wall's height must be above zero.";
            switch ((side ?? "").Trim().ToLowerInvariant())
            {
                case "":
                case "center":
                case "centre":
                    first = width / 2;
                    second = -width / 2;
                    return null;
                case "left":
                    first = width;
                    second = 0;
                    return null;
                case "right":
                    first = 0;
                    second = -width;
                    return null;
                default:
                    return "'" + side + "' is not a side of the path. Use center, left or right (looking along the path from its start), "
                        + "or inside / outside for a closed path.";
            }
        }

        /// <summary>
        /// 'inside' and 'outside' of a closed path, as 'left' or 'right': on a
        /// path that runs anticlockwise in plan the inside is on its left.
        /// Every other word comes back as it was, for <see cref="Faces"/> to
        /// check. Error is set when 'inside' or 'outside' is asked of an open path.
        /// </summary>
        public static string Resolve(string side, bool closed, bool anticlockwise, out string? error)
        {
            error = null;
            var word = (side ?? "").Trim().ToLowerInvariant();
            if (word == "" || word == "centre") return "center";
            if (word != "inside" && word != "outside") return word;
            if (!closed)
            {
                error = "'" + word + "' needs a closed path, and this one is open. Use center, left or right (looking along the path from its start).";
                return word;
            }
            return (word == "inside") == anticlockwise ? "left" : "right";
        }

        /// <summary>
        /// +1 when a point moved off the path's start by (dx, dy) is to the
        /// left of the way the path heads there (tx, ty), -1 to the right, 0
        /// when it is on the path's own line. In plan, looking down.
        /// </summary>
        public static int LeftOf(double tx, double ty, double dx, double dy)
        {
            var cross = tx * dy - ty * dx;
            var scale = Math.Sqrt(tx * tx + ty * ty) * Math.Sqrt(dx * dx + dy * dy);
            if (!(scale > 0) || Math.Abs(cross) <= 1e-9 * scale) return 0;
            return cross > 0 ? 1 : -1;
        }
    }

    /// <summary>The sums behind the face edits (D-113). Pure, so every rule is tested offline.</summary>
    public static class FaceEditMath
    {
        /// <summary>
        /// Where the taper pivots: the plane square to the draft direction
        /// through the lowest point of the picked faces along it, so their
        /// bottom edges stay put and they lean as they rise, as SOLIDEDIT
        /// Taper does from a base point at the bottom. Given the faces' boxes;
        /// the point is at the middle of the boxes, slid down to that plane.
        /// Null when the direction has no length.
        /// </summary>
        public static double[]? TaperBase(IList<double[]> lows, IList<double[]> highs, double[] direction)
        {
            var unit = Unit(direction);
            if (unit == null || lows.Count == 0 || lows.Count != highs.Count) return null;
            var low = new[] { double.MaxValue, double.MaxValue, double.MaxValue };
            var high = new[] { double.MinValue, double.MinValue, double.MinValue };
            for (var i = 0; i < lows.Count; i++)
                for (var axis = 0; axis < 3; axis++)
                {
                    low[axis] = Math.Min(low[axis], lows[i][axis]);
                    high[axis] = Math.Max(high[axis], highs[i][axis]);
                }
            // The box corner furthest back along the direction sets the plane.
            var lowest = double.MaxValue;
            for (var corner = 0; corner < 8; corner++)
            {
                var x = (corner & 1) == 0 ? low[0] : high[0];
                var y = (corner & 2) == 0 ? low[1] : high[1];
                var z = (corner & 4) == 0 ? low[2] : high[2];
                lowest = Math.Min(lowest, x * unit[0] + y * unit[1] + z * unit[2]);
            }
            var middle = new[] { (low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2 };
            var slide = lowest - (middle[0] * unit[0] + middle[1] * unit[1] + middle[2] * unit[2]);
            return new[] { middle[0] + slide * unit[0], middle[1] + slide * unit[1], middle[2] + slide * unit[2] };
        }

        /// <summary>The direction at length one, or null when it has no length (or is not three numbers).</summary>
        public static double[]? Unit(double[] vector)
        {
            if (vector == null || vector.Length != 3 || vector.Any(v => double.IsNaN(v) || double.IsInfinity(v))) return null;
            var length = Math.Sqrt(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2]);
            if (!(length > 1e-12)) return null;
            return new[] { vector[0] / length, vector[1] / length, vector[2] / length };
        }
    }
}
