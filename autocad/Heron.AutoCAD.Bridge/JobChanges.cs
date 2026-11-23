using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// What a job really did to the drawing, counted from AutoCAD's own
    /// database events, not from what a tool said it did (D-50).
    ///
    /// A raw command, AutoLISP, a purge or a trim can erase work without the
    /// tool knowing. So the add-in reports every object appended, modified and
    /// erased while a Change, Admin or Publish job runs, and this class keeps
    /// the count. An object made and erased inside the same job (a scratch
    /// object) is neither added nor erased. An object an UNDO brings back is
    /// no longer erased. The rules live here so they are tested offline.
    /// </summary>
    public sealed class JobChanges
    {
        /// <summary>Most erased handles reported back by name; the count is always whole.</summary>
        public const int MostHandles = 200;

        /// <summary>Most handles kept per job for the palette's Select and Zoom (D-68): what Heron shows at once.</summary>
        public const int MostShown = 500;

        private readonly object _gate = new object();
        private string? _job;
        private string? _last;
        // Something changed in a drawing while no watched job ran (the modeller,
        // or another program), and whether that happened before the job now
        // running began: what "undo Heron's last change" must know (D-54).
        private bool _outside;
        private bool _before;
        private readonly HashSet<string> _added = new HashSet<string>();
        private readonly HashSet<string> _modified = new HashSet<string>();
        private readonly List<string> _erased = new List<string>();
        private readonly HashSet<string> _erasedSet = new HashSet<string>();

        public static bool Watches(Risk risk) => risk == Risk.Change || risk == Risk.Admin || risk == Risk.Publish;

        /// <summary>True while a watched job runs: the add-in's event handlers return at once otherwise.</summary>
        public bool Counting
        {
            get { lock (_gate) return _job != null; }
        }

        public void Begin(string job, Risk risk)
        {
            lock (_gate)
            {
                if (!Watches(risk))
                {
                    // A read or view job counts nothing and leaves the last count readable.
                    _job = null;
                    return;
                }
                _added.Clear();
                _modified.Clear();
                _erased.Clear();
                _erasedSet.Clear();
                _job = job;
                _last = _job;
                _before = _outside;
                _outside = false;
            }
        }

        /// <summary>Stops counting; what was counted stays readable until the next job begins.</summary>
        public void End(string job)
        {
            lock (_gate)
                if (_job == job) _job = null;
        }

        /// <summary>Something changed while no watched job ran. Cheap: called for every such event.</summary>
        public void Outside()
        {
            lock (_gate) _outside = true;
        }

        /// <summary>
        /// For the job now running: did anything change between the watched job
        /// before it and its own begin? Null when it is not the job being counted.
        /// </summary>
        public bool? ChangedBefore(string job)
        {
            lock (_gate) return _last != null && _last == job ? _before : (bool?)null;
        }

        /// <summary>
        /// For the palette's Undo (D-68): did anything change outside Heron's
        /// jobs since this job, the last one counted, ended? Null when another
        /// job was counted since, or this one is still running.
        /// </summary>
        public bool? ChangedSince(string job)
        {
            lock (_gate) return _last != null && _last == job && _job == null ? _outside : (bool?)null;
        }

        public void Appended(string handle)
        {
            lock (_gate)
                if (_job != null) _added.Add(handle);
        }

        public void Modified(string handle)
        {
            lock (_gate)
                if (_job != null && !_added.Contains(handle) && !_erasedSet.Contains(handle)) _modified.Add(handle);
        }

        /// <param name="erased">True when it was erased, false when an UNDO or un-erase brought it back.</param>
        public void Erased(string handle, bool erased)
        {
            lock (_gate)
            {
                if (_job == null) return;
                if (_added.Contains(handle))
                {
                    // Made in this job: erased is "never made", brought back is "made".
                    if (erased) _added.Remove(handle);
                    return;
                }
                if (erased)
                {
                    _modified.Remove(handle);
                    if (_erasedSet.Add(handle)) _erased.Add(handle);
                }
                else if (_erasedSet.Remove(handle))
                {
                    _erased.Remove(handle);
                }
            }
        }

        /// <summary>The counts so far for this job, or null when it is not the job last counted.</summary>
        public ChangeReport? Read(string job)
        {
            lock (_gate)
            {
                if (_last == null || _last != job) return null;
                return new ChangeReport
                {
                    Added = _added.Count,
                    Modified = _modified.Count,
                    Erased = _erased.Count,
                    ErasedHandles = _erased.Take(MostHandles).ToArray(),
                    AllErasedHandles = _erased.ToArray(),
                    AddedHandles = _added.Take(MostShown).ToArray(),
                    ModifiedHandles = _modified.Take(MostShown).ToArray(),
                };
            }
        }
    }

    public sealed class ChangeReport
    {
        public int Added { get; set; }
        public int Modified { get; set; }
        public int Erased { get; set; }
        /// <summary>At most <see cref="JobChanges.MostHandles"/>, for the chat.</summary>
        public string[] ErasedHandles { get; set; } = new string[0];
        /// <summary>Every erased handle, for putting them back.</summary>
        public string[] AllErasedHandles { get; set; } = new string[0];
        /// <summary>At most <see cref="JobChanges.MostShown"/>, for the palette (D-68).</summary>
        public string[] AddedHandles { get; set; } = new string[0];
        /// <summary>At most <see cref="JobChanges.MostShown"/>, for the palette (D-68).</summary>
        public string[] ModifiedHandles { get; set; } = new string[0];
    }

    public sealed class EraseRequest
    {
        public string Job { get; set; } = "";
        public string Summary { get; set; } = "";
        public string[] Handles { get; set; } = new string[0];
        /// <summary>
        /// The job replaced objects (join, explode, a circle trimmed or broken into
        /// an arc) and the server holds its UNDO mark (D-136): ask "Keep the change
        /// or undo the whole change", and bring nothing back here. The server undoes
        /// the whole job on any answer but a clear keep.
        /// </summary>
        public bool Whole { get; set; }
    }

    public sealed class EraseAnswer
    {
        /// <summary>keep_erased | restored | undo_whole (only for a <see cref="EraseRequest.Whole"/> question)</summary>
        public string Answer { get; set; } = "restored";
        public int Restored { get; set; }
        public string Message { get; set; } = "";
    }
}
