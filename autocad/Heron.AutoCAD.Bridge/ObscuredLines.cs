using System;
using System.Collections.Generic;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Hidden (obscured) lines for a flat view (#171, D-152). AutoCAD's
    /// GenerateSectionGeometry gives visible and hidden background lines in
    /// one list, so the plug-in asks twice, hidden lines off and then on, and
    /// keeps the difference: a line of the second set that the first set does
    /// not cover is a hidden line. Each line is a list of points along it, in
    /// the view's own 2D (right, up), so a hidden edge straight behind a
    /// visible one counts as covered and is not drawn twice, as a draftsman
    /// draws it. Pure, so it is tested offline.
    /// </summary>
    public static class ObscuredLines
    {
        /// <summary>Points taken along a curved visible line to measure against (a straight one needs only its ends).</summary>
        public const int CoverSamples = 256;

        /// <summary>Points taken along each line of the second set, away from its ends.</summary>
        public const int Probes = 9;

        /// <summary>
        /// How near a point must be to a visible line to be on it: a ten
        /// thousandth of the view's size (0.2 mm on a 2 m spool), so a pipe's
        /// bore a few millimetres inside its wall is still told apart.
        /// </summary>
        public static double Tolerance(double size) => Math.Max(Math.Abs(size) * 1e-4, 1e-6);

        /// <summary>
        /// Where along a line the probes go, as fractions of its length: the
        /// middle of nine equal parts, never an end, because a hidden edge
        /// usually runs from one visible edge to another and its ends touch them.
        /// </summary>
        public static double[] ProbeFractions()
        {
            var fractions = new double[Probes];
            for (var k = 0; k < Probes; k++) fractions[k] = (k + 0.5) / Probes;
            return fractions;
        }

        /// <summary>
        /// For each line drawn with hidden lines on, whether it is a hidden
        /// line: more than half its probes lie off every visible line. A line
        /// with no probes is not hidden (there is nothing to draw).
        /// </summary>
        /// <param name="withHidden">Probe points of each line of the second set (hidden lines on), [x, y].</param>
        /// <param name="visible">Points along each visible line (hidden lines off), [x, y], joined in order.</param>
        /// <param name="tolerance">How near counts as on a visible line.</param>
        public static bool[] Hidden(IList<IList<double[]>> withHidden, IList<IList<double[]>> visible, double tolerance)
        {
            var hidden = new bool[withHidden?.Count ?? 0];
            if (withHidden == null || hidden.Length == 0) return hidden;
            var grid = new SegmentGrid(visible ?? Array.Empty<IList<double[]>>(), Math.Max(tolerance, 1e-12));
            for (var i = 0; i < hidden.Length; i++)
            {
                var probes = withHidden[i];
                if (probes == null || probes.Count == 0) continue;
                var off = 0;
                foreach (var p in probes)
                    if (!grid.Near(p[0], p[1])) off++;
                hidden[i] = off * 2 > probes.Count;
            }
            return hidden;
        }

        /// <summary>The visible lines' segments in square cells, so a point is measured only against those near it.</summary>
        private sealed class SegmentGrid
        {
            private const int MostCellsAcross = 256;
            private readonly List<double[]> _segments = new List<double[]>();
            private readonly Dictionary<long, List<int>> _cells = new Dictionary<long, List<int>>();
            private readonly double _tolerance;
            private readonly double _cell;
            private readonly double _x0;
            private readonly double _y0;

            public SegmentGrid(IList<IList<double[]>> lines, double tolerance)
            {
                _tolerance = tolerance;
                double lowX = double.MaxValue, lowY = double.MaxValue, highX = double.MinValue, highY = double.MinValue;
                foreach (var line in lines)
                {
                    if (line == null) continue;
                    for (var k = 0; k < line.Count; k++)
                    {
                        var a = line[k];
                        lowX = Math.Min(lowX, a[0]);
                        lowY = Math.Min(lowY, a[1]);
                        highX = Math.Max(highX, a[0]);
                        highY = Math.Max(highY, a[1]);
                        // A single point is a segment of no length: a dot still covers what is on it.
                        var b = k + 1 < line.Count ? line[k + 1] : (line.Count == 1 ? a : null);
                        if (b != null) _segments.Add(new[] { a[0], a[1], b[0], b[1] });
                    }
                }
                if (_segments.Count == 0)
                {
                    _cell = 1;
                    return;
                }
                _x0 = lowX;
                _y0 = lowY;
                var span = Math.Max(highX - lowX, highY - lowY);
                // At least twice the tolerance, so a point's own cell and the eight round it hold every segment in reach.
                _cell = Math.Max(span / MostCellsAcross, 2 * tolerance);
                for (var s = 0; s < _segments.Count; s++) Add(s);
            }

            private void Add(int index)
            {
                var g = _segments[index];
                var length = Math.Sqrt((g[2] - g[0]) * (g[2] - g[0]) + (g[3] - g[1]) * (g[3] - g[1]));
                // A long segment goes in piece by piece, so it fills only the cells it passes through.
                var pieces = Math.Max(1, (int)Math.Ceiling(length / _cell));
                var seen = new HashSet<long>();
                for (var p = 0; p < pieces; p++)
                {
                    double t0 = (double)p / pieces, t1 = (double)(p + 1) / pieces;
                    double ax = g[0] + (g[2] - g[0]) * t0, ay = g[1] + (g[3] - g[1]) * t0;
                    double bx = g[0] + (g[2] - g[0]) * t1, by = g[1] + (g[3] - g[1]) * t1;
                    int i0 = Cell(Math.Min(ax, bx), _x0), i1 = Cell(Math.Max(ax, bx), _x0);
                    int j0 = Cell(Math.Min(ay, by), _y0), j1 = Cell(Math.Max(ay, by), _y0);
                    for (var i = i0; i <= i1; i++)
                        for (var j = j0; j <= j1; j++)
                        {
                            var key = Key(i, j);
                            if (!seen.Add(key)) continue;
                            if (!_cells.TryGetValue(key, out var list)) _cells[key] = list = new List<int>();
                            list.Add(index);
                        }
                }
            }

            public bool Near(double x, double y)
            {
                if (_segments.Count == 0) return false;
                int ci = Cell(x, _x0), cj = Cell(y, _y0);
                var limit = _tolerance * _tolerance;
                for (var i = ci - 1; i <= ci + 1; i++)
                    for (var j = cj - 1; j <= cj + 1; j++)
                    {
                        if (!_cells.TryGetValue(Key(i, j), out var list)) continue;
                        foreach (var s in list)
                            if (DistanceSquared(_segments[s], x, y) <= limit) return true;
                    }
                return false;
            }

            private int Cell(double value, double origin) => (int)Math.Floor((value - origin) / _cell);

            private static long Key(int i, int j) => ((long)i << 32) ^ (uint)j;

            private static double DistanceSquared(double[] g, double x, double y)
            {
                double dx = g[2] - g[0], dy = g[3] - g[1];
                var lengthSquared = dx * dx + dy * dy;
                var t = lengthSquared < 1e-300 ? 0 : ((x - g[0]) * dx + (y - g[1]) * dy) / lengthSquared;
                t = Math.Max(0, Math.Min(1, t));
                double px = g[0] + t * dx - x, py = g[1] + t * dy - y;
                return px * px + py * py;
            }
        }
    }
}
