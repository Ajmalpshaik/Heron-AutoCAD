using System;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>Is the drawing in front of AutoCAD the one a job began on?</summary>
    public static class DrawingNames
    {
        /// <summary>
        /// Full paths must match. A drawing never saved is only a name
        /// (Drawing1.dwg) on one side, so then the names are compared. An empty
        /// job drawing (no drawing was open at begin) never blocks.
        /// </summary>
        public static bool Same(string active, string job)
        {
            if (string.IsNullOrEmpty(job)) return true;
            if (string.Equals(active, job, StringComparison.OrdinalIgnoreCase)) return true;
            var bare = !HasFolder(active) || !HasFolder(job);
            return bare && string.Equals(FileName(active), FileName(job), StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>The file name alone, for a sentence: "Plan.dwg"; "no drawing" for none.</summary>
        public static string Short(string? drawing)
        {
            var name = FileName(drawing ?? "");
            return name.Length == 0 ? "no drawing" : name;
        }

        private static readonly char[] Slashes = { '\\', '/' };

        private static bool HasFolder(string name) => (name ?? "").IndexOfAny(Slashes) >= 0;

        /// <summary>The part after the last slash of either kind, the same on every system.</summary>
        private static string FileName(string name) => (name ?? "").Substring((name ?? "").LastIndexOfAny(Slashes) + 1);
    }
}
