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

        private readonly object _gate = new object();
        private string? _job;
        private string? _last;
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
                _added.Clear();
                _modified.Clear();
                _erased.Clear();
                _erasedSet.Clear();
                _job = Watches(risk) ? job : null;
                _last = _job;
            }
        }

        /// <summary>Stops counting; what was counted stays readable until the next job begins.</summary>
        public void End(string job)
        {
            lock (_gate)
                if (_job == job) _job = null;
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
    }

    public sealed class EraseRequest
    {
        public string Job { get; set; } = "";
        public string Summary { get; set; } = "";
        public string[] Handles { get; set; } = new string[0];
    }

    public sealed class EraseAnswer
    {
        /// <summary>keep_erased | restored</summary>
        public string Answer { get; set; } = "restored";
        public int Restored { get; set; }
        public string Message { get; set; } = "";
    }
}
