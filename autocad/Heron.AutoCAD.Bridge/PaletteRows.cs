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

        /// <summary>
        /// Which buttons a job's card gets (D-124). A button shows only when it
        /// can act: a save, an export or a job that made and changed nothing has
        /// nothing to select, zoom to or undo, so it gets none. Decided from the
        /// job alone and whether it is Heron's newest, both of which redraw the
        /// list when they change. What can change without a redraw (another
        /// job running, the drawing in front, a change by the modeller since,
        /// UNDOCTL) is still checked on the click by
        /// <see cref="ActivityLog.CanShow"/> and <see cref="ActivityLog.CanUndo"/>,
        /// which say why not.
        /// </summary>
        /// <param name="job">The job, from <see cref="ActivityLog.Entries"/>.</param>
        /// <param name="newest">True for the first of <see cref="ActivityLog.Entries"/>: only Heron's newest change may be undone.</param>
        public static JobButtons Buttons(ActivityEntry job, bool newest)
        {
            // Discarded, or a dry run Heron took back at once (D-63): nothing of it is left.
            if (job.Running || job.Undone || job.Outcome == "discarded" || job.Outcome == ActivityLog.DryRun) return new JobButtons();
            var show = job.ShownHandles.Length > 0;
            var undo = newest
                && job.Tool != ActivityLog.UndoTool
                && job.Risk == Risk.Change
                && job.Ok && job.Outcome == "done"
                && job.Counted && job.Added + job.Modified + job.Erased > 0
                // With no UNDO mark, one step back would undo Heron's zoom instead.
                && (job.Marked || job.ViewsSince == 0)
                // With no UNDO mark, one step back would be the erase question's restore (#244).
                && (job.Marked || !job.BroughtBack);
            return new JobButtons { Select = show, Zoom = show, Undo = undo };
        }
    }

    /// <summary>The buttons a job's card shows in the Activity list (D-124).</summary>
    public sealed class JobButtons
    {
        public bool Select { get; set; }
        public bool Zoom { get; set; }
        public bool Undo { get; set; }
        public bool Any => Select || Zoom || Undo;
    }
}
