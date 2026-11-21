using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// What happened to the drawings open in this AutoCAD, recorded as AutoCAD
    /// says it happens (#48, D-98): a drawing opened, came to the front, was
    /// saved (perhaps under a new name) or closed. The add-in feeds it from
    /// AutoCAD's document events on the main thread; the pipe thread reads it,
    /// never waiting for AutoCAD. Three readers:
    ///
    /// - the server's wrong-drawing guard asks for the events since it checked
    ///   a drawing (op <c>drawings</c>), so a drawing closed and opened again,
    ///   or a restart, is seen even when the same name is in front again;
    /// - <c>send_quiet</c> refuses drawing input when another drawing came to
    ///   the front during the job, so a batch never lands in the wrong one;
    /// - the palette's Activity list shows them live (<see cref="Changed"/>).
    ///
    /// Pure, so it is tested offline.
    /// </summary>
    public sealed class DrawingEvents
    {
        /// <summary>Most events kept; the oldest drop off (and a reader asking for them is told so).</summary>
        public const int MostKept = 50;

        public const string Opened = "opened";
        public const string Activated = "activated";
        public const string Saved = "saved";
        public const string Closed = "closed";

        private readonly object _gate = new object();
        private readonly LinkedList<DrawingEvent> _events = new LinkedList<DrawingEvent>();
        private readonly Func<DateTime> _clock;
        private long _seq;
        private long _dropped;
        private long _frontSeq;
        private string _active = "";
        private bool _activeKnown;

        public DrawingEvents() : this(() => DateTime.Now)
        {
        }

        public DrawingEvents(Func<DateTime> clock)
        {
            _clock = clock;
            Epoch = Guid.NewGuid().ToString("N").Substring(0, 12);
        }

        /// <summary>
        /// New for every AutoCAD session: numbers from another session (AutoCAD
        /// restarted, or another AutoCAD) are never compared with these.
        /// </summary>
        public string Epoch { get; }

        /// <summary>Raised after every event recorded, on the thread that recorded it (AutoCAD's main thread).</summary>
        public event Action? Changed;

        /// <summary>The number of the newest event; 0 before any.</summary>
        public long Seq
        {
            get { lock (_gate) return _seq; }
        }

        /// <summary>The drawing in front, as the events say; "" for none, null before the watch started.</summary>
        public string? Active
        {
            get { lock (_gate) return _activeKnown ? _active : null; }
        }

        /// <summary>Where the watch starts from (the drawing in front when it is hooked). Not an event.</summary>
        public void Start(string? active)
        {
            lock (_gate)
            {
                _active = active ?? "";
                _activeKnown = true;
            }
            Changed?.Invoke();
        }

        public void DrawingOpened(string drawing) => Add(Opened, drawing, "");

        /// <summary>A drawing came to the front. The one already in front coming to the front again is not news.</summary>
        public void DrawingActivated(string drawing)
        {
            lock (_gate)
            {
                if (_activeKnown && string.Equals(_active, drawing ?? "", StringComparison.OrdinalIgnoreCase)) return;
            }
            Add(Activated, drawing, "");
        }

        /// <summary>
        /// A drawing was saved. <paramref name="was"/> is the name it had
        /// before, when a Save As gave it a new one; empty otherwise.
        /// </summary>
        public void DrawingSaved(string drawing, string? was)
        {
            var before = string.Equals(was ?? "", drawing ?? "", StringComparison.OrdinalIgnoreCase) ? "" : was ?? "";
            Add(Saved, drawing, before);
        }

        public void DrawingClosed(string drawing) => Add(Closed, drawing, "");

        private void Add(string kind, string? drawing, string was)
        {
            lock (_gate)
            {
                var name = drawing ?? "";
                _seq++;
                _events.AddLast(new DrawingEvent { Seq = _seq, Kind = kind, Drawing = name, Was = was, At = _clock() });
                while (_events.Count > MostKept)
                {
                    _dropped = _events.First!.Value.Seq;
                    _events.RemoveFirst();
                }
                switch (kind)
                {
                    case Activated:
                        _active = name;
                        _activeKnown = true;
                        _frontSeq = _seq;
                        break;
                    case Saved:
                        // Saved under a new name: the same drawing, so not a change of front.
                        if (was.Length > 0 && _activeKnown && string.Equals(_active, was, StringComparison.OrdinalIgnoreCase)) _active = name;
                        break;
                    case Closed:
                        if (_activeKnown && string.Equals(_active, name, StringComparison.OrdinalIgnoreCase))
                        {
                            _active = "";
                            _frontSeq = _seq;
                        }
                        break;
                }
            }
            Changed?.Invoke();
        }

        /// <summary>
        /// The drawing in front now ("" for none) when another one came to the
        /// front, or the one in front was closed, after event <paramref name="seq"/>;
        /// null when the front did not change since (or the watch never started).
        /// </summary>
        public string? FrontChangedSince(long seq)
        {
            lock (_gate) return _activeKnown && _frontSeq > seq ? _active : null;
        }

        /// <summary>Every event after <paramref name="since"/>, oldest first, and whether some dropped off unread.</summary>
        public DrawingHistory Since(long since)
        {
            lock (_gate)
            {
                return new DrawingHistory
                {
                    Epoch = Epoch,
                    Seq = _seq,
                    Active = _activeKnown ? _active : null,
                    Lost = since < _dropped,
                    Events = _events.Where(e => e.Seq > since).Select(e => e.Copy()).ToList(),
                };
            }
        }

        /// <summary>The newest events first, for the palette.</summary>
        public IReadOnlyList<DrawingEvent> Recent(int most)
        {
            lock (_gate) return _events.Reverse().Take(Math.Max(0, most)).Select(e => e.Copy()).ToList();
        }

        /// <summary>
        /// A file AutoCAD writes on its own while saving (the automatic save
        /// .sv$, a backup .bak): not the modeller saving the drawing.
        /// </summary>
        public static bool IsBackupFile(string? fileName)
        {
            var name = (fileName ?? "").Trim();
            if (name.Length == 0) return true;
            var dot = name.LastIndexOf('.');
            var slash = name.LastIndexOfAny(new[] { '\\', '/' });
            if (dot < 0 || dot < slash) return true;
            var extension = name.Substring(dot).ToLowerInvariant();
            return extension != ".dwg" && extension != ".dwt" && extension != ".dws" && extension != ".dxf";
        }
    }

    public sealed class DrawingEvent
    {
        public long Seq { get; set; }
        /// <summary>opened | activated | saved | closed (the constants on <see cref="DrawingEvents"/>).</summary>
        public string Kind { get; set; } = "";
        /// <summary>The drawing's full path when saved, else its name (Drawing1.dwg).</summary>
        public string Drawing { get; set; } = "";
        /// <summary>For a save under a new name: the name it had before. Empty otherwise.</summary>
        public string Was { get; set; } = "";
        public DateTime At { get; set; }

        internal DrawingEvent Copy() => (DrawingEvent)MemberwiseClone();
    }

    public sealed class DrawingHistory
    {
        public string Epoch { get; set; } = "";
        public long Seq { get; set; }
        /// <summary>The drawing in front ("" for none), or null when the watch never started.</summary>
        public string? Active { get; set; }
        /// <summary>Some events after the number asked for dropped off before they were read.</summary>
        public bool Lost { get; set; }
        public IReadOnlyList<DrawingEvent> Events { get; set; } = new List<DrawingEvent>();
    }
}
