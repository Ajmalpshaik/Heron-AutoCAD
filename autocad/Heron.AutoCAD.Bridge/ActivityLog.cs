using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The Activity tab of the Heron palette (D-68): Heron's recent change
    /// jobs in this AutoCAD, from every chat, newest first, with what the
    /// plug-in counted (D-50). It also decides when the palette may Select,
    /// Zoom and Undo a job. The rule for Undo is D-54's: only Heron's newest
    /// change, only when nothing else changed since. The add-in only asks and
    /// shows; the rules live here, so they are tested offline.
    /// </summary>
    public sealed class ActivityLog
    {
        /// <summary>Most jobs kept; the oldest drop off.</summary>
        public const int MostEntries = 30;

        /// <summary>The tool that is itself an undo: undoing it again would be a redo.</summary>
        public const string UndoTool = "autocad_undo_last";

        /// <summary>The server's outcome for a dry run (D-63): already taken back when it ends.</summary>
        public const string DryRun = "dry_run";

        /// <summary>
        /// A job whose end never came (the pipe broke, the server was killed)
        /// stops counting as running after this; longer than any real job,
        /// Keep or Discard (9 minutes) and an operation (5 minutes) included.
        /// </summary>
        public static readonly TimeSpan MostJob = TimeSpan.FromMinutes(20);

        private readonly object _gate = new object();
        private readonly LinkedList<ActivityEntry> _entries = new LinkedList<ActivityEntry>();
        private readonly Func<DateTime> _clock;
        private string? _running;
        private DateTime _runningSince;
        private bool _undoWaiting;
        private DateTime _undoSince;

        /// <summary>The palette's Undo never holds jobs off longer than this, whatever happens to it.</summary>
        public static readonly TimeSpan MostUndoWait = TimeSpan.FromMinutes(1);

        public ActivityLog() : this(() => DateTime.Now)
        {
        }

        public ActivityLog(Func<DateTime> clock)
        {
            _clock = clock;
        }

        /// <summary>Raised after every change to the list, on the thread that made it (a pipe thread, often).</summary>
        public event Action? Changed;

        /// <summary>True while any Heron job runs in this AutoCAD.</summary>
        public bool Busy
        {
            get { lock (_gate) return RunningLocked; }
        }

        private bool RunningLocked => _running != null && _clock() - _runningSince < MostJob;

        public void Begin(JobInfo job, DateTime at)
        {
            lock (_gate)
            {
                _running = job.Job;
                _runningSince = _clock();
                if (JobChanges.Watches(job.Risk))
                {
                    _entries.AddFirst(new ActivityEntry
                    {
                        Job = job.Job,
                        Tool = job.Tool,
                        Summary = string.IsNullOrWhiteSpace(job.Summary) ? job.Tool : job.Summary,
                        Drawing = job.Drawing,
                        Risk = job.Risk,
                        // Not known until end: the server says whether it really put a mark down (#206).
                        Marked = false,
                        At = at,
                        Running = true,
                    });
                    while (_entries.Count > MostEntries) _entries.RemoveLast();
                }
                else if (job.Risk == Risk.View)
                {
                    // A zoom or a show leaves an undo step of its own (D-54).
                    var newest = _entries.First?.Value;
                    if (newest != null && !newest.Running) newest.ViewsSince++;
                }
            }
            Changed?.Invoke();
        }

        public void End(JobEnd end, ChangeReport? counted)
        {
            lock (_gate)
            {
                if (_running == end.Job) _running = null;
                var entry = Find(end.Job);
                if (entry == null) return;
                entry.Running = false;
                entry.Ok = end.Ok;
                entry.Outcome = string.IsNullOrEmpty(end.Outcome) ? (end.Ok ? "done" : "failed") : end.Outcome;
                entry.Ms = end.Ms;
                // The server's own word, never a guess from Ask to Keep (#206): it skips the
                // mark in a command or on a busy AutoCAD, and UNDO Back would then go past the job.
                entry.Marked = end.Marked && entry.Risk == Risk.Change && entry.Tool != UndoTool;
                if (counted != null)
                {
                    entry.Counted = true;
                    entry.Added = counted.Added;
                    entry.Modified = counted.Modified;
                    entry.Erased = counted.Erased;
                    entry.AddedHandles = counted.AddedHandles.ToArray();
                    entry.ShownHandles = counted.AddedHandles.Concat(counted.ModifiedHandles).Take(JobChanges.MostShown).ToArray();
                }
            }
            Changed?.Invoke();
        }

        /// <summary>A copy of every job kept, newest first.</summary>
        public IReadOnlyList<ActivityEntry> Entries
        {
            get { lock (_gate) return _entries.Select(e => e.Copy()).ToList(); }
        }

        /// <summary>
        /// The palette has typed UNDO and AutoCAD has not finished it: no new
        /// Heron job may begin meanwhile, or the UNDO could land inside it (#138).
        /// </summary>
        public void UndoWaiting(bool waiting)
        {
            lock (_gate)
            {
                _undoWaiting = waiting;
                _undoSince = _clock();
            }
        }

        /// <summary>For the bridge's begin: why a new job must wait, or null.</summary>
        public string? Blocking()
        {
            lock (_gate) return UndoWaitingLocked ? PaletteTexts.JobWaitsForUndo : null;
        }

        private bool UndoWaitingLocked => _undoWaiting && _clock() - _undoSince < MostUndoWait;

        /// <summary>The palette's Undo went through and was checked.</summary>
        public void Undone(string job)
        {
            lock (_gate)
            {
                var entry = Find(job);
                if (entry == null) return;
                entry.Undone = true;
            }
            Changed?.Invoke();
        }

        /// <summary>
        /// The Keep or Discard question selected and zoomed to this job (D-130).
        /// That zoom is an undo step of its own after the job, as a Heron zoom
        /// after it is: with no mark, one step back would undo the zoom.
        /// Only when the zoom really ran (D-136): with nothing selectable, a
        /// selection AutoCAD refused or a zoom that failed, no undo step stands
        /// after the job, and the palette's Undo must not blame one.
        /// </summary>
        public void ShownForKeep(string job, bool zoomed)
        {
            if (!zoomed) return;
            lock (_gate)
            {
                var entry = Find(job);
                if (entry == null) return;
                entry.ViewsSince++;
            }
            Changed?.Invoke();
        }

        /// <summary>
        /// The erase question brought this job's erased objects back, or is about
        /// to (#244). That restore is an undo step of its own after the job, so
        /// one step back would erase them again instead of undoing the job.
        /// </summary>
        public void BroughtBack(string job)
        {
            lock (_gate)
            {
                var entry = Find(job);
                if (entry == null) return;
                entry.BroughtBack = true;
            }
            Changed?.Invoke();
        }

        /// <summary>May the palette select or zoom to what this job made or changed?</summary>
        public ShowVerdict CanShow(string job, string activeDrawing)
        {
            lock (_gate)
            {
                var entry = Find(job);
                if (entry == null) return ShowVerdict.No(PaletteTexts.Gone);
                if (RunningLocked) return ShowVerdict.No(PaletteTexts.Busy);
                if (entry.Undone) return ShowVerdict.No(PaletteTexts.ShowUndone);
                if (entry.Outcome == "discarded") return ShowVerdict.No(PaletteTexts.ShowDiscarded);
                // D-63: a dry run is taken back before it ends; its counts are of objects now gone (D-124).
                if (entry.Outcome == DryRun) return ShowVerdict.No(PaletteTexts.ShowDryRun);
                if (!DrawingNames.Same(activeDrawing, entry.Drawing)) return ShowVerdict.No(PaletteTexts.OtherDrawing(entry.Drawing, activeDrawing));
                if (entry.ShownHandles.Length == 0)
                    return ShowVerdict.No(entry.Erased > 0 ? PaletteTexts.ShowOnlyErased : PaletteTexts.ShowNothing);
                return new ShowVerdict { Allowed = true, Handles = entry.ShownHandles.ToArray() };
            }
        }

        /// <summary>
        /// May the palette undo this job, and how? D-54's rule, for the
        /// modeller: Heron's newest change in this AutoCAD, whichever chat
        /// made it, only when nothing changed since. Otherwise why not, in
        /// plain words.
        /// </summary>
        public UndoVerdict CanUndo(string job, UndoFacts facts)
        {
            lock (_gate)
            {
                var entry = Find(job);
                if (entry == null) return UndoVerdict.No(PaletteTexts.Gone);
                if (RunningLocked) return UndoVerdict.No(PaletteTexts.Busy);
                if (UndoWaitingLocked) return UndoVerdict.No(PaletteTexts.UndoAlreadyWaiting);
                if (entry.Undone) return UndoVerdict.No(PaletteTexts.AlreadyUndone);
                if (entry.Tool == UndoTool) return UndoVerdict.No(PaletteTexts.UndoOfUndo);
                if (entry.Risk != Risk.Change) return UndoVerdict.No(PaletteTexts.UndoRawCommand);
                if (entry.Outcome == "discarded") return UndoVerdict.No(PaletteTexts.UndoDiscarded);
                if (!entry.Ok || entry.Outcome != "done") return UndoVerdict.No(PaletteTexts.UndoNotClean(entry.Outcome));
                if (!entry.Counted || entry.Added + entry.Modified + entry.Erased == 0) return UndoVerdict.No(PaletteTexts.UndoNothing);
                var newest = _entries.First!.Value;
                if (newest.Job != entry.Job) return UndoVerdict.No(PaletteTexts.UndoNotNewest(newest.Summary));
                if (!DrawingNames.Same(facts.ActiveDrawing, entry.Drawing)) return UndoVerdict.No(PaletteTexts.OtherDrawing(entry.Drawing, facts.ActiveDrawing));
                if (facts.ChangedSince == null) return UndoVerdict.No(PaletteTexts.UndoUnknown);
                if (facts.ChangedSince == true) return UndoVerdict.No(PaletteTexts.UndoChangedSince);
                // UNDOCTL bit 1: undo on. Bit 2: only one step kept, so a mark means nothing.
                if (facts.UndoControl < 0 || (facts.UndoControl & 1) == 0 || (facts.UndoControl & 2) != 0)
                    return UndoVerdict.No(PaletteTexts.UndoOff);
                if (!entry.Marked && entry.ViewsSince > 0) return UndoVerdict.No(PaletteTexts.UndoViewsSince);
                if (!entry.Marked && entry.BroughtBack) return UndoVerdict.No(PaletteTexts.UndoAfterRestore);
                return new UndoVerdict
                {
                    Allowed = true,
                    Back = entry.Marked,
                    MustBeGone = entry.AddedHandles.ToArray(),
                    Summary = entry.Summary,
                };
            }
        }

        private ActivityEntry? Find(string job)
        {
            foreach (var entry in _entries)
                if (entry.Job == job) return entry;
            return null;
        }
    }

    public sealed class ActivityEntry
    {
        public string Job { get; set; } = "";
        public string Tool { get; set; } = "";
        public string Summary { get; set; } = "";
        public string Drawing { get; set; } = "";
        public Risk Risk { get; set; }
        /// <summary>The server said at end that it put an UNDO mark down before it (#206); false when it did not say.</summary>
        public bool Marked { get; set; }
        public DateTime At { get; set; }
        public bool Running { get; set; }
        public bool Ok { get; set; }
        /// <summary>done | discarded | dry_run | failed | unknown | cancelled | refused, as the server said at end.</summary>
        public string Outcome { get; set; } = "";
        public int Ms { get; set; }
        /// <summary>The plug-in counted this job's effect (D-50).</summary>
        public bool Counted { get; set; }
        public int Added { get; set; }
        public int Modified { get; set; }
        public int Erased { get; set; }
        /// <summary>What it made: these must be gone after an Undo.</summary>
        public string[] AddedHandles { get; set; } = new string[0];
        /// <summary>What it made or changed, for Select and Zoom.</summary>
        public string[] ShownHandles { get; set; } = new string[0];
        /// <summary>Zooms and shows by Heron since it ended, and the Keep question's zoom: each is an undo step of its own.</summary>
        public int ViewsSince { get; set; }
        /// <summary>The erase question brought its erased objects back: an undo step after the job (#244).</summary>
        public bool BroughtBack { get; set; }
        public bool Undone { get; set; }

        /// <summary>One line, in plain words: "made 3, changed 1, erased 0".</summary>
        public string Counts =>
            !Counted ? "not counted" : "made " + Added + ", changed " + Modified + ", erased " + Erased;

        /// <summary>What became of it, in plain words.</summary>
        public string State
        {
            get
            {
                if (Running) return "running";
                if (Undone) return "undone from this palette";
                switch (Outcome)
                {
                    case "done": return "done";
                    case "discarded": return "discarded";
                    case ActivityLog.DryRun: return "dry run, taken back";
                    case "unknown": return "outcome unknown";
                    case "cancelled": return "cancelled";
                    default: return "stopped (" + Outcome + ")";
                }
            }
        }

        internal ActivityEntry Copy()
        {
            var copy = (ActivityEntry)MemberwiseClone();
            copy.AddedHandles = AddedHandles.ToArray();
            copy.ShownHandles = ShownHandles.ToArray();
            return copy;
        }
    }

    /// <summary>What the add-in reads from AutoCAD for an Undo, so the rule can be tested without it.</summary>
    public sealed class UndoFacts
    {
        /// <summary>The drawing in front now (its full path when saved).</summary>
        public string ActiveDrawing { get; set; } = "";
        /// <summary>From <see cref="JobChanges.ChangedSince"/>: null when not known.</summary>
        public bool? ChangedSince { get; set; }
        /// <summary>The drawing's UNDOCTL, or -1 when it could not be read.</summary>
        public int UndoControl { get; set; } = -1;
    }

    public sealed class UndoVerdict
    {
        public bool Allowed { get; set; }
        /// <summary>Why not, in plain words. Empty when allowed.</summary>
        public string Reason { get; set; } = "";
        /// <summary>True: UNDO Back to the job's mark. False: one step, UNDO 1.</summary>
        public bool Back { get; set; }
        /// <summary>What the job made: after the undo, none of these may still be there.</summary>
        public string[] MustBeGone { get; set; } = new string[0];
        public string Summary { get; set; } = "";

        public static UndoVerdict No(string reason) => new UndoVerdict { Allowed = false, Reason = reason };

        /// <summary>The command line the add-in sends.</summary>
        public string Command => Back ? "_.UNDO _Back " : "_.UNDO 1 ";
    }

    public sealed class ShowVerdict
    {
        public bool Allowed { get; set; }
        public string Reason { get; set; } = "";
        public string[] Handles { get; set; } = new string[0];

        public static ShowVerdict No(string reason) => new ShowVerdict { Allowed = false, Reason = reason };
    }
}
