using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The arithmetic behind a section plane and a flat shop-drawing view
    /// (D-95): which way each view looks, where a section plane through the
    /// modeller's points runs and which side it looks at, how the views are set
    /// out on the sheet, and whether the lines AutoCAD gives back lie on the
    /// plane. Pure, so it is tested offline; the plug-in does the AutoCAD part.
    /// </summary>
    public static class SectionMath
    {
        /// <summary>The views, as a drawing office names them.</summary>
        public static readonly string[] ViewNames = { "front", "top", "right", "left", "back", "bottom" };

        /// <summary>
        /// Which way a named view looks (forward, into the screen) and which way
        /// is up on it. Front looks north (+Y) with Z up, as AutoCAD's Front view;
        /// top looks down with north up.
        /// </summary>
        public static bool TryView(string name, out double[] forward, out double[] up)
        {
            forward = up = Array.Empty<double>();
            switch ((name ?? "").Trim().ToLowerInvariant())
            {
                case "front": forward = new[] { 0.0, 1.0, 0.0 }; up = new[] { 0.0, 0.0, 1.0 }; return true;
                case "back": forward = new[] { 0.0, -1.0, 0.0 }; up = new[] { 0.0, 0.0, 1.0 }; return true;
                case "right": forward = new[] { -1.0, 0.0, 0.0 }; up = new[] { 0.0, 0.0, 1.0 }; return true;
                case "left": forward = new[] { 1.0, 0.0, 0.0 }; up = new[] { 0.0, 0.0, 1.0 }; return true;
                case "top": case "plan": forward = new[] { 0.0, 0.0, -1.0 }; up = new[] { 0.0, 1.0, 0.0 }; return true;
                case "bottom": forward = new[] { 0.0, 0.0, 1.0 }; up = new[] { 0.0, -1.0, 0.0 }; return true;
                default: return false;
            }
        }

        /// <summary>The view's right-hand direction: forward x up, so the picture is never mirrored.</summary>
        public static double[] Right(double[] forward, double[] up) => Cross(forward, up);

        /// <summary>
        /// A point for a flat view's plane: outside the objects' box on the
        /// viewer's side, so the plane cuts nothing and everything is seen
        /// beyond it, as FLATSHOT sees it.
        /// </summary>
        public static double[] OutsidePoint(double[] low, double[] high, double[] forward)
        {
            var centre = Centre(low, high);
            var reach = Distance(low, high) / 2.0;
            var margin = Math.Max(reach * 0.1, 1.0);
            return Add(centre, Scale(forward, -(reach + margin)));
        }

        /// <summary>
        /// Where a section plane through the modeller's points runs, and which
        /// way it looks. Two points make a vertical cut along the line between
        /// them seen in plan (a building section); three points make the plane
        /// through all three (a plan cut at a level, a cut on a slope). The
        /// section looks to the left of the line from the first point to the
        /// second unless <paramref name="lookTowards"/> names the side.
        /// </summary>
        public static string? Plane(IList<double[]> points, double[]? lookTowards, out SectionPlane plane)
        {
            plane = new SectionPlane();
            if (points == null || points.Count < 2 || points.Count > 3)
                return "A section plane needs two points (a vertical cut along the line between them, in plan) or three (the plane through them).";
            var p = points.Select(Point).ToArray();
            if (p.Any(q => q == null)) return "Every point must be [x, y] or [x, y, z].";
            double[] along, vertical;
            if (p.Length == 2)
            {
                along = new[] { p[1]![0] - p[0]![0], p[1]![1] - p[0]![1], 0.0 };
                if (Length(along) < 1e-9)
                    return "The two points are one above the other or the same in plan, so they make no line to cut along. Give two points apart in plan, or three for a level cut.";
                vertical = new[] { 0.0, 0.0, 1.0 };
            }
            else
            {
                along = Sub(p[1]!, p[0]!);
                if (Length(along) < 1e-9) return "The first two points are the same, so they make no line to cut along.";
                var third = Sub(p[2]!, p[0]!);
                var normal = Cross(along, third);
                if (Length(normal) < 1e-9 * Math.Max(1.0, Length(along) * Length(third)))
                    return "The three points are in one straight line, so they make no plane. Move the third point off the line.";
                // Square to the line, in the plane, on the third point's side.
                vertical = Sub(third, Scale(Unit(along), Dot(third, Unit(along))));
            }
            along = Unit(along);
            vertical = Unit(vertical);
            var forward = Cross(vertical, along);
            if (p.Length == 3)
            {
                // A level cut looks down unless told otherwise, as a plan does.
                if (forward[2] > 1e-9) forward = Scale(forward, -1);
            }
            if (lookTowards != null)
            {
                var towards = Point(lookTowards);
                if (towards == null) return "look_towards must be [x, y] or [x, y, z].";
                var side = Dot(Sub(towards, p[0]!), forward);
                if (Math.Abs(side) < 1e-9) return "look_towards is on the section plane itself, so it names neither side. Give a point on the side to look at.";
                if (side < 0) forward = Scale(forward, -1);
            }
            // Up on the section: world up as it lies in the plane; on a level cut,
            // north (or south, looking up from below), so a plan reads as a plan.
            var up = vertical;
            if (p.Length == 3)
            {
                var z = new[] { 0.0, 0.0, 1.0 };
                var lifted = Sub(z, Scale(forward, Dot(z, forward)));
                up = Length(lifted) > 1e-6 ? Unit(lifted) : (forward[2] < 0 ? new[] { 0.0, 1.0, 0.0 } : new[] { 0.0, -1.0, 0.0 });
            }
            var right = Right(forward, up);
            plane = new SectionPlane
            {
                Origin = p[0]!,
                Along = along,
                Vertical = vertical,
                Forward = forward,
                Right = right,
                Up = up,
            };
            return null;
        }

        /// <summary>
        /// Where each view's centre goes on the sheet, from the front view's
        /// centre at 0,0, so that views beside each other line up: third angle
        /// puts the top view above the front and the right view on its right;
        /// first angle puts them below and on the left. Each extents is
        /// [minX, minY, maxX, maxY] round the view's own centre.
        /// </summary>
        public static Dictionary<string, double[]> Layout(IDictionary<string, double[]> extents, string projection, double gap)
        {
            var third = !string.Equals((projection ?? "third").Trim(), "first", StringComparison.OrdinalIgnoreCase);
            var front = extents.TryGetValue("front", out var f) ? f : new[] { 0.0, 0.0, 0.0, 0.0 };
            var places = new Dictionary<string, double[]>(StringComparer.OrdinalIgnoreCase);
            if (extents.ContainsKey("front")) places["front"] = new[] { 0.0, 0.0 };
            double[] E(string name) => extents[name];
            // East and west of the front, and above and below it, in projection order.
            var east = front[2];
            var west = front[0];
            var eastViews = third ? new[] { "right", "back" } : new[] { "left", "back" };
            var westViews = third ? new[] { "left" } : new[] { "right" };
            foreach (var name in eastViews)
            {
                if (!extents.ContainsKey(name)) continue;
                var x = east + gap - E(name)[0];
                places[name] = new[] { x, 0.0 };
                east = x + E(name)[2];
            }
            foreach (var name in westViews)
            {
                if (!extents.ContainsKey(name)) continue;
                var x = west - gap - E(name)[2];
                places[name] = new[] { x, 0.0 };
                west = x + E(name)[0];
            }
            var above = third ? "top" : "bottom";
            var below = third ? "bottom" : "top";
            if (extents.ContainsKey(above)) places[above] = new[] { 0.0, front[3] + gap - E(above)[1] };
            if (extents.ContainsKey(below)) places[below] = new[] { 0.0, front[1] - gap - E(below)[3] };
            return places;
        }

        /// <summary>What the lines AutoCAD gave back are lying on, which decides how they are laid flat.</summary>
        public static Lying Where(IEnumerable<double[]> points, double[] origin, double[] normal)
        {
            var list = points.Where(q => q != null && q.Length >= 3).ToList();
            if (list.Count == 0) return Lying.Plane;
            double low = double.MaxValue, high = double.MinValue, size = 0;
            var lowZ = double.MaxValue;
            var highZ = double.MinValue;
            var n = Unit(normal);
            foreach (var q in list)
            {
                var d = Dot(Sub(q, origin), n);
                low = Math.Min(low, d);
                high = Math.Max(high, d);
                lowZ = Math.Min(lowZ, q[2]);
                highZ = Math.Max(highZ, q[2]);
                size = Math.Max(size, Distance(q, list[0]));
            }
            var tolerance = 1e-6 * Math.Max(1.0, size);
            if (Math.Abs(low) <= tolerance && Math.Abs(high) <= tolerance) return Lying.Plane;
            if (highZ - lowZ <= tolerance) return Lying.Flat;
            return Lying.Spread;
        }

        public static double[]? Point(double[] value)
        {
            if (value == null || value.Length < 2 || value.Length > 3 || value.Any(v => double.IsNaN(v) || double.IsInfinity(v))) return null;
            return new[] { value[0], value[1], value.Length == 3 ? value[2] : 0.0 };
        }

        public static double[] Cross(double[] a, double[] b) =>
            new[] { a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] };

        public static double Dot(double[] a, double[] b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

        public static double[] Add(double[] a, double[] b) => new[] { a[0] + b[0], a[1] + b[1], a[2] + b[2] };

        public static double[] Sub(double[] a, double[] b) => new[] { a[0] - b[0], a[1] - b[1], a[2] - b[2] };

        public static double[] Scale(double[] a, double k) => new[] { a[0] * k, a[1] * k, a[2] * k };

        public static double Length(double[] a) => Math.Sqrt(Dot(a, a));

        public static double[] Unit(double[] a)
        {
            var length = Length(a);
            return length < 1e-300 ? new[] { 0.0, 0.0, 0.0 } : Scale(a, 1.0 / length);
        }

        public static double Distance(double[] a, double[] b) => Length(Sub(a, b));

        public static double[] Centre(double[] low, double[] high) =>
            new[] { (low[0] + high[0]) / 2, (low[1] + high[1]) / 2, (low[2] + high[2]) / 2 };
    }

    /// <summary>A section plane: a point on it, the cut line, up on the section, and the way it looks.</summary>
    public sealed class SectionPlane
    {
        public double[] Origin { get; set; } = new double[3];
        /// <summary>Along the cut line, from the first point towards the second.</summary>
        public double[] Along { get; set; } = new double[3];
        /// <summary>The plane's other direction: up for a vertical cut.</summary>
        public double[] Vertical { get; set; } = new double[3];
        /// <summary>The way the section looks: what it shows is on this side of the plane.</summary>
        public double[] Forward { get; set; } = new double[3];
        /// <summary>Right and up on the 2D section, as the viewer sees it.</summary>
        public double[] Right { get; set; } = new double[3];
        public double[] Up { get; set; } = new double[3];
    }

    /// <summary>Where generated section lines lie.</summary>
    public enum Lying
    {
        /// <summary>On the section plane: turned flat into the sheet's XY plane.</summary>
        Plane,
        /// <summary>Already flat in a plan plane elsewhere: moved, not turned.</summary>
        Flat,
        /// <summary>Neither: each curve is projected onto the section plane first.</summary>
        Spread,
    }
}
