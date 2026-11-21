using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// One line of the palette's Activity list: a Heron job, or something that
    /// happened to a drawing (#48). Exactly one of the two is set.
    /// </summary>
    public sealed class PaletteRow
    {
        public ActivityEntry? Job { get; set; }
        public DrawingEvent? Drawing { get; set; }
        public DateTime At => Job?.At ?? Drawing?.At ?? DateTime.MinValue;
    }

    /// <summary>
    /// The Activity list as the palette draws it (#48, D-98): Heron's jobs and
    /// the drawing events in one list, newest first, so a switch to another
    /// drawing shows the moment it happens. The rules live here, tested offline.
    /// </summary>
    public static class PaletteRows
    {
        /// <summary>Most drawing events shown; the jobs stay the list's main content.</summary>
        public const int MostDrawingRows = 15;

        /// <param name="jobs">Newest first, as <see cref="ActivityLog.Entries"/> gives them.</param>
        /// <param name="events">Newest first, as <see cref="DrawingEvents.Recent"/> gives them.</param>
        public static IReadOnlyList<PaletteRow> Merge(IReadOnlyList<ActivityEntry> jobs, IReadOnlyList<DrawingEvent> events, int mostDrawingRows = MostDrawingRows)
        {
            var rows = jobs.Select(job => new PaletteRow { Job = job })
                .Concat(events.Take(Math.Max(0, mostDrawingRows)).Select(e => new PaletteRow { Drawing = e }))
                .ToList();
            // Newest first; at the same moment a job before the drawing event.
            return rows
                .Select((row, index) => (row, index))
                .OrderByDescending(pair => pair.row.At)
                .ThenBy(pair => pair.row.Job != null ? 0 : 1)
                .ThenBy(pair => pair.index)
                .Select(pair => pair.row)
                .ToList();
        }

        /// <summary>
        /// Is this job's drawing the one in front? True when the palette cannot
        /// tell (no drawing events yet), so nothing is marked on a guess.
        /// </summary>
        public static bool InFront(ActivityEntry job, string? active) =>
            active == null || DrawingNames.Same(active, job.Drawing);
    }
}
