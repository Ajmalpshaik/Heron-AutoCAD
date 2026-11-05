using System;
using System.Collections.Generic;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Which command a drawing is in, from AutoCAD's own command events, so a
    /// request AutoCAD never got to can say why ("it is still in the HATCH
    /// command") instead of guessing. A transparent command ('ZOOM inside
    /// LINE) stacks on top of the one it interrupts. Written on AutoCAD's main
    /// thread, read from the pipe thread; pure, so it is tested offline.
    /// Idea: docs/11-adn-repos-study.md, item 9.
    /// </summary>
    public sealed class CommandTracker
    {
        // More than this open at once means an end was missed; start again.
        private const int Deepest = 16;
        private readonly object _gate = new object();
        private readonly List<string> _open = new List<string>();

        public void Started(string? command)
        {
            var name = Clean(command);
            if (name.Length == 0) return;
            lock (_gate)
            {
                if (_open.Count >= Deepest) _open.Clear();
                _open.Add(name);
            }
        }

        /// <summary>Ended, cancelled or failed: the latest one of that name is closed, and any opened after it.</summary>
        public void Ended(string? command)
        {
            var name = Clean(command);
            lock (_gate)
            {
                var at = _open.FindLastIndex(open => string.Equals(open, name, StringComparison.OrdinalIgnoreCase));
                if (at >= 0) _open.RemoveRange(at, _open.Count - at);
                else if (name.Length == 0 && _open.Count > 0) _open.RemoveAt(_open.Count - 1);
            }
        }

        public void Clear()
        {
            lock (_gate) _open.Clear();
        }

        /// <summary>The command running now (the innermost), or null when the drawing is waiting for the user.</summary>
        public string? Current
        {
            get
            {
                lock (_gate) return _open.Count == 0 ? null : _open[_open.Count - 1];
            }
        }

        private static string Clean(string? command) => (command ?? "").Trim().TrimStart('_', '.', '\'', '-').ToUpperInvariant();
    }
}
