using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// A jogged section line (#171, D-150): corners in plan, each leg a
    /// vertical cut, as SECTIONPLANE's "Draw section" makes. How its 2D
    /// section is laid out is the drafting rule for a section on more than
    /// one plane (ISO 128-44): every leg is turned flat beside the one before,
    /// at true size, in the order walked, and a jog (a leg running along the
    /// viewing direction) is not drawn and takes no width. So legs parallel to
    /// each other read as one straight section, exactly as projected, and a
    /// leg at an angle is turned into the drawing plane round its corner.
    /// Pure, so it is tested offline; the plug-in moves each line by its leg.
    /// </summary>
    public sealed class JoggedSection
    {
        /// <summary>A leg within this angle of the viewing direction is a jog.</summary>
        public const double JogDegrees = 1.0;

        /// <summary>At most this many corners.</summary>
        public const int MostCorners = 50;

        private JoggedSection(double[] origin, double[] forward, double[] right, List<SectionLeg> legs)
        {
            Origin = origin;
            Forward = forward;
            Right = right;
            Legs = legs;
        }

        /// <summary>The first corner, at the section line's level.</summary>
        public double[] Origin { get; }

        /// <summary>The way the section looks: square to the first leg, on the side asked.</summary>
        public double[] Forward { get; }

        /// <summary>Right on the 2D section, as the viewer sees it; up is world up.</summary>
        public double[] Right { get; }

        public static double[] Up => new[] { 0.0, 0.0, 1.0 };

        public IReadOnlyList<SectionLeg> Legs { get; }

        public int Jogs => Legs.Count(l => l.IsJog);

        /// <summary>
        /// The section line through the corners. It looks to the left of the
        /// first leg (walk from the first corner to the second, look left)
        /// unless <paramref name="lookTowards"/> names the side. Every corner is
        /// taken at the first one's level. Refused, with why: fewer than two
        /// corners, two the same in plan, a leg turning straight back, a first
        /// leg that is itself along the view, or a leg that walks back across
        /// the view (seen from the side it looks at), which would draw over
        /// itself: make that two sections.
        /// </summary>
        public static string? Build(IList<double[]> corners, double[]? lookTowards, out JoggedSection? section)
        {
            section = null;
            if (corners == null || corners.Count < 2)
                return "A section line needs at least two corners in plan.";
            if (corners.Count > MostCorners) return "A section line takes at most " + MostCorners + " corners.";
            var points = corners.Select(SectionMath.Point).ToList();
            if (points.Any(p => p == null)) return "Every corner must be [x, y] or [x, y, z].";
            var level = points[0]![2];
            var p = points.Select(q => new[] { q![0], q[1], level }).ToList();
            var along = new List<double[]>();
            for (var i = 0; i + 1 < p.Count; i++)
            {
                var d = SectionMath.Sub(p[i + 1], p[i]);
                if (SectionMath.Length(d) < 1e-9)
                    return "Corners " + (i + 1) + " and " + (i + 2) + " are the same in plan, so they make no leg. Take one out.";
                along.Add(SectionMath.Unit(d));
            }
            for (var i = 0; i + 1 < along.Count; i++)
                if (SectionMath.Dot(along[i], along[i + 1]) < -1 + 1e-9)
                    return "The section line turns straight back on itself at corner " + (i + 2) + ". Take that corner out.";

            var up = Up;
            var forward = SectionMath.Cross(up, along[0]);
            if (lookTowards != null)
            {
                var towards = SectionMath.Point(lookTowards);
                if (towards == null) return "look_towards must be [x, y] or [x, y, z].";
                var side = SectionMath.Dot(SectionMath.Sub(towards, p[0]), forward);
                if (Math.Abs(side) < 1e-9)
                    return "look_towards is on the first leg's line, so it names neither side. Give a point on the side to look at.";
                if (side < 0) forward = SectionMath.Scale(forward, -1);
            }
            var right = SectionMath.Right(forward, up);
            var jogSine = Math.Sin(JogDegrees * Math.PI / 180);
            var walk = Math.Sign(SectionMath.Dot(along[0], right));
            var legs = new List<SectionLeg>();
            var x = 0.0;
            for (var i = 0; i < along.Count; i++)
            {
                var across = SectionMath.Dot(along[i], right);
                var length = SectionMath.Distance(p[i], p[i + 1]);
                var isJog = Math.Abs(across) <= jogSine;
                if (!isJog && Math.Sign(across) != walk)
                    return "Leg " + (i + 1) + " walks back across the view, so the section would draw over itself. " +
                           "Make it two sections, or turn that leg so it carries on the way the first goes.";
                // Each leg's own right is its line, the way the first leg goes as seen.
                var legRight = isJog ? right : SectionMath.Scale(along[i], Math.Sign(across));
                legs.Add(new SectionLeg
                {
                    Start = p[i],
                    End = p[i + 1],
                    Along = along[i],
                    Length = length,
                    Right = legRight,
                    Forward = SectionMath.Cross(up, legRight),
                    Offset = x,
                    IsJog = isJog,
                });
                if (!isJog) x += SectionMath.Dot(SectionMath.Sub(p[i + 1], p[i]), legRight);
            }
            // As a section plane's cut does, the first and last legs reach on past their end corners.
            legs[0].OpenStart = true;
            legs[legs.Count - 1].OpenEnd = true;
            section = new JoggedSection(p[0], forward, right, legs);
            return null;
        }

        /// <summary>
        /// The leg whose cut a line lies on: every point of it on that leg's
        /// vertical plane and within its length (the first and last legs reach
        /// on past their end corners). A leg that is drawn wins over
        /// a jog (a line up the corner between them is on both). -1 for none.
        /// </summary>
        public int LegOf(IList<double[]> points, double tolerance)
        {
            if (points == null || points.Count == 0) return -1;
            foreach (var pass in new[] { false, true })
                for (var i = 0; i < Legs.Count; i++)
                {
                    var leg = Legs[i];
                    if (leg.IsJog != pass) continue;
                    if (points.All(q => OnLeg(leg, q, tolerance))) return i;
                }
            return -1;
        }

        /// <summary>
        /// The drawn leg a point is seen beyond (something behind the cut): the
        /// nearest leg in front of it, along that leg's own view, whose length
        /// it falls within. -1 for none: the point is not behind the section.
        /// </summary>
        public int Behind(double[] point, double tolerance)
        {
            var best = -1;
            var nearest = double.MaxValue;
            for (var i = 0; i < Legs.Count; i++)
            {
                var leg = Legs[i];
                if (leg.IsJog) continue;
                var from = SectionMath.Sub(point, leg.Start);
                if (!Within(leg, SectionMath.Dot(from, leg.Along), tolerance)) continue;
                var depth = SectionMath.Dot(from, leg.Forward);
                if (depth < -tolerance || depth >= nearest) continue;
                nearest = depth;
                best = i;
            }
            return best;
        }

        /// <summary>Where a point on (or projected onto) a leg goes on the 2D section: [x, y], round the first corner.</summary>
        public double[] ToSheet(double[] point, int leg)
        {
            var l = Legs[leg];
            var from = SectionMath.Sub(point, l.Start);
            return new[] { l.Offset + SectionMath.Dot(from, l.Right), point[2] - Origin[2] };
        }

        /// <summary>
        /// What the lines AutoCAD gave back are lying on: every one on a leg
        /// (Plane: each is turned flat by its leg), all already flat at one level
        /// (Flat: AutoCAD laid them out itself, so they are only moved), or
        /// neither (Spread: each is put on the leg it lies on or is seen beyond).
        /// </summary>
        public Lying Where(IList<IList<double[]>> lines, double tolerance)
        {
            var all = lines.Where(l => l != null && l.Count > 0).ToList();
            if (all.Count == 0 || all.All(l => LegOf(l, tolerance) >= 0)) return Lying.Plane;
            var low = all.SelectMany(l => l).Min(q => q[2]);
            var high = all.SelectMany(l => l).Max(q => q[2]);
            return high - low <= tolerance ? Lying.Flat : Lying.Spread;
        }

        // Along and Forward are level, so a point's height does not count here.
        private static bool OnLeg(SectionLeg leg, double[] q, double tolerance)
        {
            var from = SectionMath.Sub(q, leg.Start);
            var across = SectionMath.Dot(from, SectionMath.Cross(Up, leg.Along));
            return Math.Abs(across) <= tolerance && Within(leg, SectionMath.Dot(from, leg.Along), tolerance);
        }

        private static bool Within(SectionLeg leg, double t, double tolerance) =>
            (leg.OpenStart || t >= -tolerance) && (leg.OpenEnd || t <= leg.Length + tolerance);
    }

    /// <summary>One leg of a section line: a vertical cut from Start to End, and where it goes on the 2D section.</summary>
    public sealed class SectionLeg
    {
        public double[] Start { get; set; } = new double[3];
        public double[] End { get; set; } = new double[3];
        /// <summary>From Start towards End, level.</summary>
        public double[] Along { get; set; } = new double[3];
        public double Length { get; set; }
        /// <summary>Right on the 2D section for this leg: along it, the way the section reads.</summary>
        public double[] Right { get; set; } = new double[3];
        /// <summary>The way this leg looks: square to it, on the section's side.</summary>
        public double[] Forward { get; set; } = new double[3];
        /// <summary>Where Start goes across the 2D section.</summary>
        public double Offset { get; set; }
        /// <summary>A leg along the viewing direction: not drawn, no width.</summary>
        public bool IsJog { get; set; }
        /// <summary>The first leg: its cut reaches on back past its start corner.</summary>
        public bool OpenStart { get; set; }
        /// <summary>The last leg: its cut reaches on past its end corner.</summary>
        public bool OpenEnd { get; set; }
    }
}
