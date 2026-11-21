using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>A button on a box AutoCAD showed, as the add-in read it.</summary>
    public sealed class DialogButton
    {
        public int Id { get; set; }
        public string Text { get; set; } = "";
        public bool Enabled { get; set; } = true;
    }

    /// <summary>The window in front of AutoCAD at one look, as the add-in read it (no Win32 here).</summary>
    public sealed class DialogSeen
    {
        public long Handle { get; set; }
        public string Title { get; set; } = "";
        public string ClassName { get; set; } = "";
        /// <summary>Is AutoCAD's own main window disabled? That is what makes a box modal.</summary>
        public bool OwnerDisabled { get; set; }
        /// <summary>Can the box itself take input? A box with another box on top of it cannot.</summary>
        public bool Enabled { get; set; } = true;
        /// <summary>A window that never takes focus (Heron's own banner, a tooltip).</summary>
        public bool NoActivate { get; set; }
        public DialogButton[] Buttons { get; set; } = new DialogButton[0];
    }

    /// <summary>How a box is closed. Never OK or Yes, unless the job named that button for that box (#101).</summary>
    public enum DialogPress
    {
        /// <summary>Its Cancel button.</summary>
        Cancel,
        /// <summary>Its No button (a Yes / No box has no Cancel).</summary>
        No,
        /// <summary>No Cancel or No: what Esc does (for a standard box) or its ✕ (for any other).</summary>
        Escape,
        /// <summary>The one button an Admin job named for a box with exactly this title (#101).</summary>
        Named,
    }

    /// <summary>What the add-in is to press, on which box.</summary>
    public sealed class DialogPlan
    {
        public long Handle { get; set; }
        public string Title { get; set; } = "";
        public DialogPress Press { get; set; }
        /// <summary>The button's control id; 0 for Escape.</summary>
        public int ButtonId { get; set; }
        /// <summary>A standard Windows box (#32770): Esc is sent as its Cancel command, not as ✕.</summary>
        public bool StandardBox { get; set; }
        /// <summary>For <see cref="DialogPress.Named"/>: the button's text, as the box shows it.</summary>
        public string ButtonText { get; set; } = "";
    }

    /// <summary>One box Heron answered during a job, for the chat.</summary>
    public sealed class DialogNote
    {
        public string Title { get; set; } = "";
        /// <summary>Cancel | No | Esc | none (too many boxes: left alone).</summary>
        public string Pressed { get; set; } = "";
        /// <summary>True: gone after the press. False: still open. Null: not known yet.</summary>
        public bool? Closed { get; set; }
        /// <summary>The job named this button for this box (#101); every other press is Heron's default.</summary>
        public bool Asked { get; set; }
    }

    /// <summary>
    /// The dialog watch (D-66). While a Heron job runs, a box AutoCAD opens
    /// (a file dialog, "Save changes?", an error message) would stall every
    /// later call until the modeller pressed Esc. The add-in looks four times
    /// a second at the window in front of AutoCAD; this class decides whether
    /// it is a box Heron may close and what to press. Pure, so it is tested
    /// offline; the add-in only reads windows and posts the press.
    ///
    /// Rules: only while a job runs; never a window that was open when the
    /// job began (the modeller's own); never a Heron window; only a modal box
    /// (AutoCAD's main window disabled) that can take input, and only after
    /// it has stood for <see cref="Settle"/> so its buttons exist. Cancel,
    /// else No, else Esc - never OK or Yes. One press per box; after
    /// <see cref="MostPresses"/> boxes in one job Heron stops answering them.
    ///
    /// One exception (#101): an Admin job may name one button for one box it
    /// expects (<see cref="Expect"/>). That button is pressed only on a box
    /// whose title is exactly the one named, only once, only while that job
    /// runs; every other box is still cancelled.
    /// </summary>
    public sealed class DialogWatch
    {
        public static readonly TimeSpan Settle = TimeSpan.FromMilliseconds(400);
        public static readonly TimeSpan GiveUp = TimeSpan.FromSeconds(2);
        public const int MostPresses = 5;
        /// <summary>A job whose end never came stops counting after this, as in the Activity log.</summary>
        public static readonly TimeSpan MostJob = TimeSpan.FromMinutes(20);
        public const int IdCancel = 2;
        public const int IdNo = 7;

        private readonly object _gate = new object();
        private readonly Dictionary<string, List<DialogNote>> _notes = new Dictionary<string, List<DialogNote>>();
        private readonly HashSet<long> _before = new HashSet<long>();
        private readonly Dictionary<long, Pressed> _pressed = new Dictionary<long, Pressed>();
        private readonly Dictionary<string, Expected> _expected = new Dictionary<string, Expected>();
        private readonly Dictionary<string, DateTime> _began = new Dictionary<string, DateTime>();
        private long _seen;
        private DateTime _seenSince;
        private int _paused;
        private int _presses;
        private bool _stoppedAnswering;

        /// <summary>True while a job runs: the add-in looks only then.</summary>
        public bool Watching
        {
            get { lock (_gate) return _notes.Count > 0; }
        }

        /// <summary>
        /// A job began. <paramref name="openNow"/> is every window AutoCAD had
        /// open at that moment: none of them is ever touched.
        /// </summary>
        public void Begin(string job, IEnumerable<long> openNow, DateTime? at = null)
        {
            lock (_gate)
            {
                // One job runs at a time in an AutoCAD (one chat holds it, its calls run one after
                // another), so a job still listed here is one whose end never came: a server
                // stopped mid-job. Its box answer must not outlive it into this job.
                foreach (var earlier in _notes.Keys.Where(k => k != (job ?? "")).ToList()) Forget(earlier);
                if (_notes.Count == 0)
                {
                    _before.Clear();
                    _pressed.Clear();
                    _seen = 0;
                    _presses = 0;
                    _stoppedAnswering = false;
                }
                foreach (var handle in openNow ?? Enumerable.Empty<long>()) _before.Add(handle);
                _notes[job ?? ""] = new List<DialogNote>();
                _began[job ?? ""] = at ?? DateTime.UtcNow;
            }
        }

        public void End(string job)
        {
            lock (_gate) Forget(job ?? "");
        }

        /// <summary>A job is over: its notes, its named answer and its start go. Under the lock.</summary>
        private void Forget(string job)
        {
            _notes.Remove(job);
            _expected.Remove(job);
            _began.Remove(job);
            if (_notes.Count == 0)
            {
                _before.Clear();
                _pressed.Clear();
                _seen = 0;
            }
        }

        /// <summary>
        /// The running job expects one box (#101): press <paramref name="button"/>
        /// on a box whose title is exactly <paramref name="title"/>, once. False
        /// for a job that is not running, a blank title or button, or a second
        /// expectation in the same job (one answer per job). Whether the job may
        /// ask at all (Admin only) is decided by the protocol, not here.
        /// </summary>
        public bool Expect(string job, string title, string button)
        {
            var wanted = (title ?? "").Trim();
            var word = Word(button);
            lock (_gate)
            {
                if (!_notes.ContainsKey(job ?? "") || wanted.Length == 0 || word.Length == 0) return false;
                if (_expected.ContainsKey(job ?? "")) return false;
                _expected[job ?? ""] = new Expected(wanted, word);
                return true;
            }
        }

        /// <summary>Heron's own question is up (Keep or Discard, the erase question): hands off.</summary>
        public void Pause()
        {
            lock (_gate) _paused++;
        }

        public void Resume()
        {
            lock (_gate)
            {
                if (_paused > 0) _paused--;
                _seen = 0;
            }
        }

        /// <summary>The boxes answered during this job so far. Empty for an unknown job.</summary>
        public IReadOnlyList<DialogNote> Notes(string job)
        {
            lock (_gate)
            {
                return _notes.TryGetValue(job ?? "", out var list)
                    ? list.Select(n => new DialogNote { Title = n.Title, Pressed = n.Pressed, Closed = n.Closed, Asked = n.Asked }).ToList()
                    : new List<DialogNote>();
            }
        }

        /// <summary>
        /// One look. <paramref name="front"/> is the window in front of AutoCAD
        /// (null when there is none); <paramref name="isOpen"/> says whether a
        /// window still exists. Returns what to press now, or null. The caller
        /// must press it: the note is already written.
        /// </summary>
        public DialogPlan? Look(DialogSeen? front, Func<long, bool> isOpen, DateTime now)
        {
            lock (_gate)
            {
                Resolve(isOpen, now);
                foreach (var lost in _began.Where(b => now - b.Value > MostJob).Select(b => b.Key).ToList()) Forget(lost);
                if (_notes.Count == 0 || _paused > 0 || front == null || !Counts(front))
                {
                    _seen = 0;
                    return null;
                }
                if (_pressed.ContainsKey(front.Handle)) return null; // one press per box
                if (_seen != front.Handle)
                {
                    _seen = front.Handle;
                    _seenSince = now;
                    return null;
                }
                if (now - _seenSince < Settle) return null;
                _seen = 0;

                if (_presses >= MostPresses)
                {
                    if (!_stoppedAnswering)
                    {
                        _stoppedAnswering = true;
                        Note(new DialogNote { Title = Clean(front.Title), Pressed = "none", Closed = false });
                    }
                    _pressed[front.Handle] = new Pressed(now, null);
                    return null;
                }

                var plan = Answer(front) ?? Choose(front);
                var asked = plan.Press == DialogPress.Named;
                var note = new DialogNote { Title = Clean(front.Title), Pressed = asked ? plan.ButtonText : Name(plan.Press), Asked = asked };
                Note(note);
                _pressed[front.Handle] = new Pressed(now, note);
                _presses++;
                return plan;
            }
        }

        /// <summary>Is this window a box Heron may close? (Not yet: has it stood long enough.)</summary>
        public bool Counts(DialogSeen front)
        {
            lock (_gate)
            {
                if (front.Handle == 0 || !front.OwnerDisabled || !front.Enabled || front.NoActivate) return false;
                if (_before.Contains(front.Handle)) return false;
                return !IsHeronWindow(front.Title);
            }
        }

        /// <summary>Heron's own windows: "Heron - Keep this change?", the banner "Heron AI".</summary>
        public static bool IsHeronWindow(string? title)
        {
            var text = (title ?? "").Trim();
            return text.StartsWith("Heron - ", StringComparison.Ordinal) || text.StartsWith("Heron AI", StringComparison.Ordinal);
        }

        /// <summary>Cancel, else No, else Esc. A Yes or OK button is never chosen.</summary>
        public static DialogPlan Choose(DialogSeen box)
        {
            var standard = string.Equals(box.ClassName, "#32770", StringComparison.Ordinal);
            var buttons = (box.Buttons ?? new DialogButton[0]).Where(b => b != null && b.Enabled).ToList();
            var cancel = buttons.FirstOrDefault(b => b.Id == IdCancel || Word(b.Text) == "cancel");
            if (cancel != null)
                return new DialogPlan { Handle = box.Handle, Title = Clean(box.Title), Press = DialogPress.Cancel, ButtonId = cancel.Id, StandardBox = standard };
            var no = buttons.FirstOrDefault(b => b.Id == IdNo || Word(b.Text) == "no");
            if (no != null)
                return new DialogPlan { Handle = box.Handle, Title = Clean(box.Title), Press = DialogPress.No, ButtonId = no.Id, StandardBox = standard };
            return new DialogPlan { Handle = box.Handle, Title = Clean(box.Title), Press = DialogPress.Escape, ButtonId = 0, StandardBox = standard };
        }

        public static string Name(DialogPress press) =>
            press == DialogPress.Cancel ? "Cancel" : press == DialogPress.No ? "No" : press == DialogPress.Named ? "the named button" : "Esc";

        /// <summary>What the log and the chat call this press: the button's own text for a named one.</summary>
        public static string Label(DialogPlan plan) => plan.Press == DialogPress.Named ? plan.ButtonText : Name(plan.Press);

        /// <summary>
        /// A job's named answer for this box, or null: the title must be exactly
        /// the one named, the button must be on the box and enabled, and each
        /// expectation is used once.
        /// </summary>
        private DialogPlan? Answer(DialogSeen box)
        {
            var title = (box.Title ?? "").Trim();
            foreach (var expected in _expected.Values)
            {
                if (expected.Used || !string.Equals(expected.Title, title, StringComparison.Ordinal)) continue;
                var button = (box.Buttons ?? new DialogButton[0]).FirstOrDefault(b => b != null && b.Enabled && Word(b.Text) == expected.Button);
                if (button == null) return null; // not the box it expected after all: Heron's default
                expected.Used = true;
                return new DialogPlan
                {
                    Handle = box.Handle, Title = Clean(box.Title), Press = DialogPress.Named, ButtonId = button.Id,
                    StandardBox = string.Equals(box.ClassName, "#32770", StringComparison.Ordinal),
                    ButtonText = (button.Text ?? "").Replace("&", "").Trim(),
                };
            }
            return null;
        }

        private void Resolve(Func<long, bool> isOpen, DateTime now)
        {
            foreach (var pair in _pressed)
            {
                var note = pair.Value.Note;
                if (note == null || note.Closed.HasValue) continue;
                bool open;
                try
                {
                    open = isOpen(pair.Key);
                }
                catch (Exception)
                {
                    open = true;
                }
                if (!open) note.Closed = true;
                else if (now - pair.Value.At >= GiveUp) note.Closed = false;
            }
        }

        private void Note(DialogNote note)
        {
            // A box stalls everything, so every running job hears of it.
            foreach (var list in _notes.Values) list.Add(note);
        }

        private static string Word(string? text) =>
            (text ?? "").Replace("&", "").Trim().TrimEnd('.').Trim().ToLowerInvariant();

        private static string Clean(string? title)
        {
            var text = (title ?? "").Trim();
            if (text.Length == 0) return "a box with no title";
            return text.Length > 120 ? text.Substring(0, 120) : text;
        }

        private sealed class Expected
        {
            public Expected(string title, string button)
            {
                Title = title;
                Button = button;
            }

            public string Title { get; }
            public string Button { get; }
            public bool Used { get; set; }
        }

        private sealed class Pressed
        {
            public Pressed(DateTime at, DialogNote? note)
            {
                At = at;
                Note = note;
            }

            public DateTime At { get; }
            public DialogNote? Note { get; }
        }
    }
}
