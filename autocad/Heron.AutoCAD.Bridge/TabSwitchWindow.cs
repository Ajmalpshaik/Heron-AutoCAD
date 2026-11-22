using System;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The moment AutoCAD puts another layout tab on screen (CTAB changing), when it
    /// turns the sheets' viewports off and on and may erase and remake the sheet's own
    /// paper-space viewport (D-125). None of that is the job's work: a run_lisp that only
    /// did (setvar "CTAB" "SAC2-103") came back "8 changed, 1 erased" and asked the
    /// erase question (2026-11-22). The add-in leaves the change count alone while this
    /// window is open.
    ///
    /// Opened by AutoCAD's "CTAB will change" event and closed by "CTAB changed". A
    /// window that never closes (an event lost to an error) shuts by itself after
    /// <see cref="Longest"/>, so a lost event can never hide a real erase for long.
    /// </summary>
    public sealed class TabSwitchWindow
    {
        /// <summary>Longer than any tab switch; short enough that a real erase after it is counted.</summary>
        public static readonly TimeSpan Longest = TimeSpan.FromSeconds(5);

        private readonly object _gate = new object();
        private readonly Func<DateTime> _now;
        private DateTime? _since;

        public TabSwitchWindow(Func<DateTime>? now = null)
        {
            _now = now ?? (() => DateTime.UtcNow);
        }

        /// <summary>True for the system variable that names the tab on screen.</summary>
        public static bool IsTabSwitch(string? variable) =>
            string.Equals((variable ?? "").Trim(), "CTAB", StringComparison.OrdinalIgnoreCase);

        public void WillChange(string? variable)
        {
            if (!IsTabSwitch(variable)) return;
            lock (_gate) _since = _now();
        }

        public void Changed(string? variable)
        {
            if (!IsTabSwitch(variable)) return;
            lock (_gate) _since = null;
        }

        /// <summary>True while a tab switch is under way: what happens now is AutoCAD's own.</summary>
        public bool Open
        {
            get
            {
                lock (_gate)
                {
                    if (_since == null) return false;
                    if (_now() - _since.Value > Longest)
                    {
                        _since = null;
                        return false;
                    }
                    return true;
                }
            }
        }
    }
}
