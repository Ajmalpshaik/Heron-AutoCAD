using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Which jobs the activity banner is still waiting on, so its DONE card
    /// always closes.
    ///
    /// The banner used to count begins and ends. A job whose end never came
    /// (AutoCAD left mid-command, the COM link dropped) kept the count above
    /// zero for good, and every DONE card after it stayed on screen (bedroom
    /// model, 2026-11-05). Jobs are now tracked by name: an end sent twice
    /// changes nothing, a lost end is put right by the next begin from the
    /// same chat (one chat runs one job at a time, the hold sees to that), and
    /// a job older than <see cref="StaleAfter"/> no longer holds the card open.
    ///
    /// The rules live here so they are tested offline; the banner only shows
    /// and hides.
    /// </summary>
    public sealed class BannerJobs
    {
        /// <summary>Longer than any real job; a begin older than this is a lost end.</summary>
        public static readonly TimeSpan StaleAfter = TimeSpan.FromMinutes(15);

        private readonly object _gate = new object();
        private readonly Dictionary<string, Running> _jobs = new Dictionary<string, Running>();

        private readonly struct Running
        {
            public Running(string conversation, DateTime began)
            {
                Conversation = conversation;
                Began = began;
            }

            public string Conversation { get; }
            public DateTime Began { get; }
        }

        public void Begin(JobInfo job, DateTime now)
        {
            lock (_gate)
            {
                // The same chat cannot have two jobs running: an earlier one
                // still listed lost its end.
                foreach (var lost in _jobs.Where(p => p.Value.Conversation == job.Conversation).Select(p => p.Key).ToList())
                    _jobs.Remove(lost);
                _jobs[job.Job] = new Running(job.Conversation, now);
            }
        }

        public void End(string job)
        {
            lock (_gate) _jobs.Remove(job);
        }

        /// <summary>
        /// True when no job is left running, so the outcome card may close.
        /// Jobs begun longer than <see cref="StaleAfter"/> ago are dropped first.
        /// </summary>
        public bool AllDone(DateTime now)
        {
            lock (_gate)
            {
                foreach (var stale in _jobs.Where(p => now - p.Value.Began > StaleAfter).Select(p => p.Key).ToList())
                    _jobs.Remove(stale);
                return _jobs.Count == 0;
            }
        }

        /// <summary>How many jobs the banner is still waiting on.</summary>
        public int InFlight
        {
            get
            {
                lock (_gate) return _jobs.Count;
            }
        }
    }
}
