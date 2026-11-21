using System;
using System.Collections.Generic;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// What a spline drawn by control points (#56, D-97) and a fit-point edit
    /// must be before the plug-in hands them to AutoCAD. No AutoCAD here, so it
    /// is tested offline; the server checks the same things first, and this is
    /// the plug-in's own guard against a request it was never meant to get.
    /// </summary>
    public static class SplineCheck
    {
        /// <summary>The highest degree the SPLINE command's control-vertex method offers.</summary>
        public const int MostDegree = 10;

        /// <summary>
        /// Why a control-point spline cannot be made, or null when it can: a
        /// degree from 1 to 10, one more control point than the degree at least,
        /// and a knot vector of control points + degree + 1 values that never
        /// goes down. Every number must be a real number.
        /// </summary>
        public static string? ControlProblem(int degree, double[] points, double[] knots)
        {
            if (degree < 1 || degree > MostDegree) return "The degree must be 1 to " + MostDegree + ".";
            if (points.Length == 0 || points.Length % 3 != 0) return "The control points must come as x, y, z for each point.";
            var count = points.Length / 3;
            if (count < degree + 1) return "A degree " + degree + " spline needs at least " + (degree + 1) + " control points; there are " + count + ".";
            if (knots.Length != count + degree + 1)
                return "A spline of " + count + " control points and degree " + degree + " needs " + (count + degree + 1) + " knots; there are " + knots.Length + ".";
            foreach (var value in points)
                if (double.IsNaN(value) || double.IsInfinity(value)) return "A control point is not a number.";
            for (var i = 0; i < knots.Length; i++)
            {
                if (double.IsNaN(knots[i]) || double.IsInfinity(knots[i])) return "A knot is not a number.";
                if (i > 0 && knots[i] < knots[i - 1]) return "The knots must never go down.";
            }
            if (knots[count] - knots[degree] <= 0) return "The knots give the spline no length.";
            return null;
        }

        /// <summary>
        /// One fit-point edit, as the server sends it: set, insert or remove at
        /// a 0-based index. <see cref="Steps"/> reads them.
        /// </summary>
        public readonly struct Step
        {
            public Step(string kind, int index, double x, double y, double z)
            {
                Kind = kind;
                Index = index;
                X = x;
                Y = y;
                Z = z;
            }

            public string Kind { get; }
            public int Index { get; }
            public double X { get; }
            public double Y { get; }
            public double Z { get; }
        }

        /// <summary>
        /// Walks the edits over a count of fit points and says why one cannot be
        /// done (an index off the end, too few points left), or null when every
        /// one can. Insert takes an index up to the count: the count itself
        /// adds after the last point.
        /// </summary>
        public static string? StepsProblem(int count, IReadOnlyList<Step> steps, bool closed)
        {
            var now = count;
            for (var i = 0; i < steps.Count; i++)
            {
                var step = steps[i];
                switch (step.Kind)
                {
                    case "set":
                        if (step.Index < 0 || step.Index >= now) return "Edit " + i + " moves fit point " + step.Index + ", but there are " + now + ".";
                        break;
                    case "insert":
                        if (step.Index < 0 || step.Index > now) return "Edit " + i + " adds a fit point at " + step.Index + ", but there are " + now + ".";
                        now++;
                        break;
                    case "remove":
                        if (step.Index < 0 || step.Index >= now) return "Edit " + i + " removes fit point " + step.Index + ", but there are " + now + ".";
                        now--;
                        break;
                    default:
                        return "Edit " + i + " is '" + step.Kind + "'; an edit sets, inserts or removes.";
                }
            }
            var least = closed ? 3 : 2;
            if (now < least) return "That leaves " + now + " fit points; a " + (closed ? "closed " : "") + "spline needs " + least + ".";
            return null;
        }

        /// <summary>True when two lists of x, y, z hold the same points to within a hair.</summary>
        public static bool SamePoints(double[] a, double[] b, double tolerance = 1e-6)
        {
            if (a.Length != b.Length) return false;
            for (var i = 0; i < a.Length; i++)
                if (Math.Abs(a[i] - b[i]) > tolerance * Math.Max(1.0, Math.Abs(b[i]))) return false;
            return true;
        }
    }
}
