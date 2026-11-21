using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// A camera view's lens (D-86). AutoCAD's lens length is in millimetres on a
    /// 35 mm camera (LENSLENGTH, 50 mm by default). Heron works the field of view
    /// out across a 36 mm wide frame, and sizes the saved view to that field at
    /// the target, so the lens and the view's size agree. Pure, so it is tested
    /// offline; which way AutoCAD measures its own Field of view is checked live.
    /// </summary>
    public static class CameraLens
    {
        public const double Shortest = 10.0;
        public const double Longest = 600.0;

        /// <summary>The frame of a 35 mm camera across, in millimetres.</summary>
        public const double FrameWidth = 36.0;

        /// <summary>Null when the lens can be used, else why not.</summary>
        public static string? Check(double lens) =>
            double.IsNaN(lens) || double.IsInfinity(lens) || lens < Shortest || lens > Longest
                ? "The lens must be " + Shortest.ToString("0") + "-" + Longest.ToString("0") + " mm (24 mm is a wide room shot, 50 mm a normal eye)."
                : null;

        /// <summary>The field of view across the picture, in degrees.</summary>
        public static double FieldOfViewDegrees(double lens) => 2.0 * Math.Atan(FrameWidth / 2.0 / lens) * 180.0 / Math.PI;

        /// <summary>The width and height the view sees at the target, this far from the eye.</summary>
        public static void Field(double distance, double lens, double aspect, out double width, out double height)
        {
            width = distance * FrameWidth / lens;
            height = width / Aspect(aspect);
        }

        /// <summary>A usable width-to-height ratio; 4:3 when the one given is not.</summary>
        public static double Aspect(double aspect) =>
            double.IsNaN(aspect) || double.IsInfinity(aspect) || aspect < 0.2 || aspect > 5.0 ? 4.0 / 3.0 : aspect;
    }

    /// <summary>
    /// The sun's date and time (D-86). AutoCAD keeps them on the active
    /// viewport's sun as a date and a clock time at the site; only the parts the
    /// chat gave change. Pure, so it is tested offline.
    /// </summary>
    public static class SunClock
    {
        public const int FirstYear = 1900;
        public const int LastYear = 2200;

        /// <summary>Null and the new date and time, or why not. Year, month and day come together; so do hour and minute.</summary>
        public static string? Compose(DateTime current, int? year, int? month, int? day, int? hour, int? minute, out DateTime result)
        {
            result = current;
            var dated = year.HasValue || month.HasValue || day.HasValue;
            var timed = hour.HasValue || minute.HasValue;
            if (dated && !(year.HasValue && month.HasValue && day.HasValue)) return "A date needs its year, month and day.";
            if (timed && !(hour.HasValue && minute.HasValue)) return "A time needs its hour and minute.";

            var y = year ?? current.Year;
            var mo = month ?? current.Month;
            var d = day ?? current.Day;
            var h = hour ?? current.Hour;
            var mi = minute ?? current.Minute;
            var s = timed ? 0 : current.Second;
            if (y < FirstYear || y > LastYear) return "The year must be " + FirstYear + "-" + LastYear + ".";
            if (mo < 1 || mo > 12) return "The month must be 1-12.";
            if (d < 1 || d > DateTime.DaysInMonth(y, mo)) return y + "-" + mo.ToString("00") + " has no day " + d + ".";
            if (h < 0 || h > 23) return "The hour must be 0-23.";
            if (mi < 0 || mi > 59) return "The minute must be 0-59.";
            result = new DateTime(y, mo, d, h, mi, s, DateTimeKind.Unspecified);
            return null;
        }
    }

    /// <summary>A light the drawing has, as the chat names it.</summary>
    public readonly struct LightTag
    {
        public LightTag(string handle, string name)
        {
            Handle = handle ?? "";
            Name = name ?? "";
        }

        public string Handle { get; }
        public string Name { get; }
    }

    /// <summary>
    /// Which lights the chat means (D-87): a word is the light with that handle,
    /// else every light of that name (a light inside a block definition repeats
    /// in each block, so a name can mean several). Pure, so it is tested offline.
    /// </summary>
    public static class LightPick
    {
        /// <summary>How many names a refusal lists.</summary>
        public const int Listed = 20;

        /// <summary>Null and the indexes picked (each once, in the drawing's order), or why not.</summary>
        public static string? Resolve(IReadOnlyList<LightTag> lights, IEnumerable<string> asked, out List<int> picked)
        {
            picked = new List<int>();
            var chosen = new HashSet<int>();
            var unknown = new List<string>();
            foreach (var raw in asked ?? Enumerable.Empty<string>())
            {
                var word = (raw ?? "").Trim();
                if (word.Length == 0) continue;
                var byHandle = Find(lights, l => string.Equals(l.Handle, word, StringComparison.OrdinalIgnoreCase));
                var found = byHandle.Count > 0 ? byHandle : Find(lights, l => string.Equals(l.Name, word, StringComparison.OrdinalIgnoreCase));
                if (found.Count == 0) unknown.Add(word);
                foreach (var index in found) chosen.Add(index);
            }
            if (unknown.Count > 0)
            {
                picked.Clear();
                return "No light called " + string.Join(", ", unknown.Select(u => "'" + u + "'")) + ". " + Available(lights);
            }
            picked.AddRange(chosen.OrderBy(i => i));
            return null;
        }

        /// <summary>What the drawing does have, for a refusal.</summary>
        public static string Available(IReadOnlyList<LightTag> lights)
        {
            if (lights.Count == 0) return "This drawing has no lights.";
            var names = lights.Select(l => l.Name.Length > 0 ? l.Name : l.Handle)
                .Distinct(StringComparer.OrdinalIgnoreCase).ToList();
            var shown = string.Join(", ", names.Take(Listed));
            return "The lights are: " + shown + (names.Count > Listed ? " and " + (names.Count - Listed) + " more" : "")
                + ". autocad_list_lights gives each one's handle.";
        }

        private static List<int> Find(IReadOnlyList<LightTag> lights, Func<LightTag, bool> match)
        {
            var found = new List<int>();
            for (var i = 0; i < lights.Count; i++)
                if (match(lights[i])) found.Add(i);
            return found;
        }
    }
}
