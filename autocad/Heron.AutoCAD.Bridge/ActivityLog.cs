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

        private readonly object _gate = new object();
        private readonly LinkedList<ActivityEntry> _entries = new LinkedList<ActivityEntry>();
        private string? _running;

        /// <summary>Raised after every change to the list, on the thread that made it (a pipe thread, often).</summary>
        public event Action? Changed;

        /// <summary>True while any Heron job runs in this AutoCAD.</summary>
        public bool Busy
        {
            get { lock (_gate) return _running != null; }
        }

        public void Begin(JobInfo job, DateTime at)
        {
            lock (_gate)
            {
                _running = job.Job;
                if (JobChanges.Watches(job.Risk))
                {
                    _entries.AddFirst(new ActivityEntry
                    {
                        Job = job.Job,
                        Tool = job.Tool,
                        Summary = string.IsNullOrWhiteSpace(job.Summary) ? job.Tool : job.Summary,
                        Drawing = job.Drawing,
                        Risk = job.Risk,
                        // The server puts an UNDO mark down only for a Change job it will ask about.
                        Marked = job.AskToKeep && job.Risk == Risk.Change && job.Tool != UndoTool,
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

        /// <summary>May the palette select or zoom to what this job made or changed?</summary>
        public ShowVerdict CanShow(string job, string activeDrawing)
        {
            lock (_gate)
            {
                var entry = Find(job);
                if (entry == null) return ShowVerdict.No(PaletteTexts.Gone);
                if (_running != null) return ShowVerdict.No(PaletteTexts.Busy);
                if (entry.Undone) return ShowVerdict.No(PaletteTexts.ShowUndone);
                if (entry.Outcome == "discarded") return ShowVerdict.No(PaletteTexts.ShowDiscarded);
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
                if (_running != null) return UndoVerdict.No(PaletteTexts.Busy);
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
        /// <summary>The server put an UNDO mark down before it (Ask to Keep was on).</summary>
        public bool Marked { get; set; }
        public DateTime At { get; set; }
        public bool Running { get; set; }
        public bool Ok { get; set; }
        /// <summary>done | discarded | failed | unknown | cancelled, as the server said at end.</summary>
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
        /// <summary>Zooms and shows by Heron since it ended: each is an undo step of its own.</summary>
        public int ViewsSince { get; set; }
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
