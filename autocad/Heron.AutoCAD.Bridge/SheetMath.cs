using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.RegularExpressions;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The arithmetic behind a sheet the plug-in makes (Sheets in the add-in,
    /// #64, #65, D-90): which of a plotter's sheet sizes was meant, where a
    /// viewport's view centre is once the view is twisted, the name of a scale,
    /// and whether a clip outline is a shape at all. Pure, so it is tested
    /// offline; the add-in only hands the answers to AutoCAD.
    /// </summary>
    public static class SheetMath
    {
        // Media names look like "ISO_full_bleed_A3_(420.00_x_297.00_MM)".
        private static readonly Regex MediaName = new Regex(@"^(?<label>.*?) ?\((?<w>[\d.]+) x (?<h>[\d.]+) \w+\)$");
        private static readonly HashSet<string> Orientations = new HashSet<string> { "portrait", "landscape" };

        private static string Normal(string name) => Regex.Replace(name ?? "", @"[\s_]+", " ").Trim().ToLowerInvariant();

        /// <summary>
        /// A plotter's canonical media name for a paper size, or null when it has none.
        /// Exact canonical or display names are used as given. Short names such as "A3",
        /// "ANSI D" or "A1 portrait" match on their size words: the landscape sheet unless
        /// "portrait" is asked for, and the full-bleed variant first, because it leaves
        /// no unprintable margin round a PDF. The same rule as the server's _match_media.
        /// </summary>
        public static string? MatchMedia(IList<string> names, string wanted)
        {
            var request = Normal(wanted);
            foreach (var name in names)
                if (Normal(name) == request) return name;

            var words = new HashSet<string>(request.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries));
            var portrait = words.Contains("portrait");
            words.ExceptWith(Orientations);
            if (words.Count == 0) return null;

            string? best = null;
            (int wrongWay, int variant, int index) bestRank = (int.MaxValue, int.MaxValue, int.MaxValue);
            for (var index = 0; index < names.Count; index++)
            {
                var match = MediaName.Match(Normal(names[index]));
                if (!match.Success) continue;
                var label = match.Groups["label"].Value;
                var labelWords = new HashSet<string>(label.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries));
                if (!words.IsSubsetOf(labelWords)) continue;
                if (!double.TryParse(match.Groups["w"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var width)) continue;
                if (!double.TryParse(match.Groups["h"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out var height)) continue;
                var wrongWay = width != height && (width < height) != portrait ? 1 : 0;
                var variant = label.Contains("full bleed") ? 0 : label.Contains("expand") ? 2 : 1;
                var rank = (wrongWay, variant, index);
                if (rank.CompareTo(bestRank) < 0)
                {
                    bestRank = rank;
                    best = names[index];
                }
            }
            return best;
        }

        /// <summary>The distinct sheet sizes on offer, e.g. "ISO A3", "ANSI B", for a refusal.</summary>
        public static List<string> MediaSizes(IEnumerable<string> names)
        {
            var sizes = new List<string>();
            foreach (var name in names)
            {
                var cut = name.IndexOf("_(", StringComparison.Ordinal);
                var label = (cut >= 0 ? name.Substring(0, cut) : name).Replace("_full_bleed", "").Replace("_expand", "").Replace("_", " ");
                if (!sizes.Contains(label)) sizes.Add(label);
            }
            return sizes;
        }

        /// <summary>
        /// Where a plan viewport's view centre is, in its display coordinates, for a
        /// world point to sit in the middle of it. A viewport looking straight down
        /// at the world origin with a twist of t shows the world turned by t, so the
        /// point is turned by t as well (display = rotate(world, +t)).
        /// </summary>
        public static void ViewCentre(double x, double y, double twistDegrees, out double dx, out double dy)
        {
            var t = twistDegrees * Math.PI / 180.0;
            var cos = Math.Cos(t);
            var sin = Math.Sin(t);
            dx = x * cos - y * sin;
            dy = x * sin + y * cos;
        }

        /// <summary>A scale as it goes on the sheet: 0.02 is "1:50", 2 is "2:1".</summary>
        public static string ScaleName(double ratio)
        {
            if (!(ratio > 0) || double.IsInfinity(ratio)) throw new ArgumentOutOfRangeException(nameof(ratio), "A scale must be above zero.");
            return ratio >= 1.0 ? Tidy(ratio) + ":1" : "1:" + Tidy(1.0 / ratio);
        }

        /// <summary>The paper and drawing units of an annotation scale: 1:50 is 1 paper to 50 drawing.</summary>
        public static void ScaleUnits(double ratio, out double paper, out double drawing)
        {
            if (ratio >= 1.0)
            {
                paper = ratio;
                drawing = 1.0;
            }
            else
            {
                paper = 1.0;
                drawing = 1.0 / ratio;
            }
        }

        /// <summary>True when an annotation scale of paper:drawing is the viewport's scale.</summary>
        public static bool SameScale(double paper, double drawing, double ratio) =>
            paper > 0 && drawing > 0 && ratio > 0 && Math.Abs(paper / drawing / ratio - 1.0) < 1e-6;

        private static string Tidy(double number)
        {
            var rounded = Math.Round(number, 4);
            if (Math.Abs(rounded - Math.Round(rounded)) < 1e-9) return Math.Round(rounded).ToString("0", CultureInfo.InvariantCulture);
            return rounded.ToString("0.####", CultureInfo.InvariantCulture);
        }

        /// <summary>
        /// A clip outline from flat paper coordinates [x1, y1, x2, y2, ...], closed:
        /// a last point that repeats the first is dropped. Null and the reason when
        /// it is not a shape (fewer than three corners, no area). The server checks
        /// the outline fully first (acad/sheets.py clip_outline); this is the plug-in's
        /// own guard, so a bad request never reaches AutoCAD.
        /// </summary>
        public static List<(double x, double y)>? Outline(double[] flat, out string? refusal)
        {
            refusal = null;
            if (flat == null || flat.Length < 6 || flat.Length % 2 != 0)
            {
                refusal = "A clip outline needs at least three corners, as [x, y] pairs on the paper.";
                return null;
            }
            var points = new List<(double x, double y)>();
            for (var i = 0; i < flat.Length; i += 2)
            {
                var p = (flat[i], flat[i + 1]);
                if (double.IsNaN(p.Item1) || double.IsNaN(p.Item2) || double.IsInfinity(p.Item1) || double.IsInfinity(p.Item2))
                {
                    refusal = "A clip outline's corners must be numbers.";
                    return null;
                }
                if (points.Count > 0 && Near(points[points.Count - 1], p)) continue;
                points.Add(p);
            }
            if (points.Count > 1 && Near(points[0], points[points.Count - 1])) points.RemoveAt(points.Count - 1);
            if (points.Count < 3)
            {
                refusal = "A clip outline needs at least three different corners.";
                return null;
            }
            if (Math.Abs(Area(points)) < 1e-9)
            {
                refusal = "That clip outline has no area: its corners are on one line.";
                return null;
            }
            return points;
        }

        /// <summary>The signed area of a closed outline (positive when it runs anticlockwise).</summary>
        public static double Area(IList<(double x, double y)> points)
        {
            var sum = 0.0;
            for (var i = 0; i < points.Count; i++)
            {
                var a = points[i];
                var b = points[(i + 1) % points.Count];
                sum += a.x * b.y - b.x * a.y;
            }
            return sum / 2.0;
        }

        /// <summary>The box round an outline: min x, min y, max x, max y.</summary>
        public static (double x1, double y1, double x2, double y2) Bounds(IEnumerable<(double x, double y)> points)
        {
            var list = points.ToList();
            return (list.Min(p => p.x), list.Min(p => p.y), list.Max(p => p.x), list.Max(p => p.y));
        }

        private static bool Near((double x, double y) a, (double x, double y) b) =>
            Math.Abs(a.x - b.x) < 1e-9 && Math.Abs(a.y - b.y) < 1e-9;
    }
}
