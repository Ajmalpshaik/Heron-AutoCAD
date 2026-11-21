using System;
using System.Collections.Generic;
using System.Globalization;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The arithmetic of an associative array (AutoCAD's ARRAY, D-110): where
    /// each item's base point goes for a grid, a ring or a run along a path,
    /// and the check that what AutoCAD built is where it was asked to be.
    /// Pure, so it is tested offline; the plug-in does the drawing.
    ///
    /// Points are world [x, y]. Angles are radians, counter-clockwise.
    /// </summary>
    public static class ArrayPlan
    {
        /// <summary>One array holds at most this many items; more would stall AutoCAD.</summary>
        public const int MostItems = 10000;

        private const double FullTurn = 2 * Math.PI;

        /// <summary>Null and each item's base point, row by row from the base point, or why not.</summary>
        public static string? Rectangular(double[] basePoint, int rows, int columns, double rowSpacing, double columnSpacing, out List<double[]> points)
        {
            points = new List<double[]>();
            if (rows < 1 || columns < 1) return "Rows and columns must each be 1 or more.";
            if ((long)rows * columns < 2) return "A 1 x 1 array makes no copies. Give more rows or columns.";
            if ((long)rows * columns > MostItems) return TooMany((long)rows * columns);
            if (rows > 1 && !Usable(rowSpacing)) return "More than one row needs a row spacing other than zero.";
            if (columns > 1 && !Usable(columnSpacing)) return "More than one column needs a column spacing other than zero.";
            for (var r = 0; r < rows; r++)
                for (var c = 0; c < columns; c++)
                    points.Add(new[] { basePoint[0] + c * columnSpacing, basePoint[1] + r * rowSpacing });
            return null;
        }

        /// <summary>
        /// Null and the ring: the angle between items, the radius and start angle
        /// of the base point about the centre, and each item's base point; or why not.
        /// A full turn spreads the items evenly; less puts the first and last at the ends.
        /// </summary>
        public static string? Polar(
            double[] center, double[] basePoint, int count, double fillAngle, bool rotateItems,
            out double step, out double radius, out double startAngle, out List<double[]> points)
        {
            points = new List<double[]>();
            step = radius = startAngle = 0;
            if (count < 2) return "A ring needs 2 items or more, the original included.";
            if (count > MostItems) return TooMany(count);
            if (!(fillAngle > 0) || fillAngle > FullTurn + 1e-9) return "The angle to fill must be more than 0 and at most 360 degrees.";
            var full = fillAngle >= FullTurn - 1e-9;
            step = full ? FullTurn / count : fillAngle / (count - 1);
            double dx = basePoint[0] - center[0], dy = basePoint[1] - center[1];
            radius = Math.Sqrt(dx * dx + dy * dy);
            if (radius < 1e-9 && !rotateItems)
                return "The base point is on the centre and the items do not turn, so every copy would land on the original. "
                    + "Give a centre away from the objects, or let the items turn.";
            startAngle = radius < 1e-9 ? 0 : Math.Atan2(dy, dx);
            for (var i = 0; i < count; i++)
            {
                var a = startAngle + i * step;
                points.Add(new[] { center[0] + radius * Math.Cos(a), center[1] + radius * Math.Sin(a) });
            }
            return null;
        }

        /// <summary>
        /// Null and how many items go along a path and how far apart, or why not.
        /// <paramref name="spacing"/> 0 divides the path into <paramref name="count"/>
        /// (first at the start, last at the end of an open path); a spacing measures
        /// along it, with as many as fit when <paramref name="count"/> is 0.
        /// </summary>
        public static string? Path(double length, bool closed, int count, double spacing, out int items, out double step)
        {
            items = 0;
            step = 0;
            if (!(length > 0) || double.IsInfinity(length)) return "The path has no length.";
            if (spacing < 0 || double.IsNaN(spacing) || double.IsInfinity(spacing)) return "The spacing must be above zero.";
            if (spacing == 0)
            {
                if (count < 2) return "Dividing a path needs 2 items or more, or give a spacing instead.";
                items = count;
                step = closed ? length / count : length / (count - 1);
            }
            else
            {
                var tolerance = length * 1e-9;
                if (spacing > length + tolerance)
                    return "The spacing " + Num(spacing) + " is longer than the path (" + Num(length) + ").";
                var fit = (int)Math.Min(int.MaxValue - 1, Math.Floor(length / spacing + 1e-9)) + (closed ? 0 : 1);
                if (count > 0 && count > fit)
                    return count + " items " + Num(spacing) + " apart need " + Num((count - (closed ? 0 : 1)) * spacing)
                        + " of path; this one is " + Num(length) + " long, so at most " + fit + " fit.";
                items = count > 0 ? count : fit;
                if (items < 2) return "Only one item fits at that spacing. Make the spacing smaller.";
                step = spacing;
            }
            if (items > MostItems) return TooMany(items);
            return null;
        }

        /// <summary>
        /// Null when AutoCAD's array is where it was asked to be, else why not.
        /// Each item's box is the source's box carried to its base point; an item
        /// that turns (a ring that rotates, a run that follows the path) may sit
        /// anywhere within the source's reach of its base point. The array must
        /// stay inside those boxes and reach across them.
        /// </summary>
        public static string? Check(
            double[] actualMin, double[] actualMax, IList<double[]> points,
            double[] sourceMin, double[] sourceMax, double[] basePoint, bool turns)
        {
            if (points.Count == 0) return "The array has no items.";
            double reach = 0;
            foreach (var x in new[] { sourceMin[0], sourceMax[0] })
                foreach (var y in new[] { sourceMin[1], sourceMax[1] })
                    reach = Math.Max(reach, Math.Sqrt((x - basePoint[0]) * (x - basePoint[0]) + (y - basePoint[1]) * (y - basePoint[1])));

            var outerMin = new[] { double.MaxValue, double.MaxValue };
            var outerMax = new[] { double.MinValue, double.MinValue };
            var spanMin = new[] { double.MaxValue, double.MaxValue };
            var spanMax = new[] { double.MinValue, double.MinValue };
            foreach (var p in points)
            {
                for (var k = 0; k < 2; k++)
                {
                    var low = turns ? p[k] - reach : sourceMin[k] + p[k] - basePoint[k];
                    var high = turns ? p[k] + reach : sourceMax[k] + p[k] - basePoint[k];
                    outerMin[k] = Math.Min(outerMin[k], low);
                    outerMax[k] = Math.Max(outerMax[k], high);
                    spanMin[k] = Math.Min(spanMin[k], p[k]);
                    spanMax[k] = Math.Max(spanMax[k], p[k]);
                }
            }

            // A hundredth of the source's size: catches a wrong centre, spacing or
            // start, not the rounding of text extents.
            double sourceSize = Math.Sqrt(Square(sourceMax[0] - sourceMin[0]) + Square(sourceMax[1] - sourceMin[1]));
            double outerSize = Math.Sqrt(Square(outerMax[0] - outerMin[0]) + Square(outerMax[1] - outerMin[1]));
            double tolerance = Math.Max(0.01 * sourceSize + 1e-6 * outerSize, 1e-9);

            var inside = true;
            var reaches = true;
            for (var k = 0; k < 2; k++)
            {
                if (actualMin[k] < outerMin[k] - tolerance || actualMax[k] > outerMax[k] + tolerance) inside = false;
                if (turns)
                {
                    if (actualMax[k] - actualMin[k] < spanMax[k] - spanMin[k] - 2 * reach - tolerance) reaches = false;
                }
                else if (actualMin[k] > outerMin[k] + tolerance || actualMax[k] < outerMax[k] - tolerance)
                {
                    reaches = false;
                }
            }
            if (inside && reaches) return null;
            return "AutoCAD built the array somewhere other than asked: it covers " + Box(actualMin, actualMax)
                + ", where the items should cover " + Box(outerMin, outerMax) + ".";
        }

        private static bool Usable(double value) => value != 0 && !double.IsNaN(value) && !double.IsInfinity(value);

        private static double Square(double value) => value * value;

        private static string TooMany(long items) =>
            "That is " + items.ToString(CultureInfo.InvariantCulture) + " items; one array holds at most " + MostItems + ". Use fewer, or a bigger spacing.";

        private static string Num(double value) => Math.Round(value, 3).ToString("0.###", CultureInfo.InvariantCulture);

        private static string Box(double[] min, double[] max) =>
            "(" + Num(min[0]) + ", " + Num(min[1]) + ") to (" + Num(max[0]) + ", " + Num(max[1]) + ")";
    }
}
