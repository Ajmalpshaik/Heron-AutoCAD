using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using Autodesk.AutoCAD.ApplicationServices;
using Handle = Autodesk.AutoCAD.DatabaseServices.Handle;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using AcPaletteSet = Autodesk.AutoCAD.Windows.PaletteSet;
using AcStyles = Autodesk.AutoCAD.Windows.PaletteSetStyles;
using AcDock = Autodesk.AutoCAD.Windows.DockSides;
using S = Heron.AutoCAD.Addin.HeronWindowStyle;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The Heron palette (D-68): one docked PaletteSet with two tabs, drawn in
    /// Heron's window style (D-45). Activity lists Heron's recent change jobs
    /// with Select, Zoom and Undo where they can act (D-123); Saved commands lists the commands saved in
    /// a chat, fills their inputs and runs one through the server's gate. The
    /// rules are the bridge's (ActivityLog, SavedCommandList, PaletteServer);
    /// this file only shows them and makes the AutoCAD calls. Main thread only.
    /// </summary>
    internal static class HeronPalette
    {
        private static readonly Guid Id = new Guid("8b6f3d52-4f0e-4c1a-9a7e-2d6c5b9e1f30");
        private static AcPaletteSet? _set;

        /// <summary>Open the palette, or close it when it is open (HERONPALETTE, the ribbon).</summary>
        public static void Toggle()
        {
            try
            {
                if (_set == null)
                {
                    _set = new AcPaletteSet("Heron", "HERONPALETTE", Id)
                    {
                        Style = AcStyles.ShowCloseButton | AcStyles.ShowAutoHideButton | AcStyles.ShowPropertiesMenu,
                        DockEnabled = AcDock.Left | AcDock.Right,
                    };
                    _set.AddVisual("Activity", new ActivityTab().Root);
                    _set.AddVisual("Saved commands", new CommandsTab().Root);
                    _set.Visible = true;
                    _set.Dock = AcDock.Right;
                    HeronLog.Write("palette opened");
                    return;
                }
                _set.Visible = !_set.Visible;
            }
            catch (Exception ex)
            {
                HeronLog.Error("Heron palette", ex);
                AcApp.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nHeron: the palette could not open: " + ex.Message + "\n");
            }
            finally
            {
                HeronRibbon.Repaint();
            }
        }

        // ----- shared look -----

        /// <summary>The tab's frame: the top strip, the Ink header with the heron, a status line, then the body.</summary>
        internal static Border Frame(string subtitle, UIElement body, TextBlock status)
        {
            var heron = IconLoader.Sized("BridgeConnected", 64);
            var title = new TextBlock { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(heron != null ? 9 : 0, 0, 0, 0) };
            title.Inlines.Add(new System.Windows.Documents.Run("Heron") { FontSize = 13.5, FontWeight = FontWeights.SemiBold, Foreground = new SolidColorBrush(S.TextPrimary) });
            title.Inlines.Add(new System.Windows.Documents.Run("   " + subtitle) { FontSize = 12.5, Foreground = new SolidColorBrush(S.TextMuted) });
            var bar = new StackPanel { Orientation = Orientation.Horizontal, Height = 46 };
            if (heron != null) bar.Children.Add(new Image { Source = heron, Width = 26, Height = 26, VerticalAlignment = VerticalAlignment.Center });
            bar.Children.Add(title);

            status.Margin = new Thickness(14, 10, 14, 2);
            status.Visibility = Visibility.Collapsed;

            var top = new StackPanel();
            top.Children.Add(new Border { Height = 3, Background = new SolidColorBrush(S.AccentColour) });
            top.Children.Add(new Border { Background = new SolidColorBrush(S.HeaderColour), Padding = new Thickness(14, 0, 14, 0), Child = bar });
            top.Children.Add(status);

            var dock = new DockPanel { LastChildFill = true };
            DockPanel.SetDock(top, Dock.Top);
            dock.Children.Add(top);
            dock.Children.Add(new ScrollViewer
            {
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                Content = body,
            });
            return new Border
            {
                Background = new SolidColorBrush(S.CardColour),
                Child = dock,
                // Typing in a box must reach the box, not AutoCAD's command line.
                Focusable = true,
            };
        }

        internal static void Say(TextBlock status, string text, Color colour)
        {
            status.Text = text;
            status.Foreground = new SolidColorBrush(colour);
            status.Visibility = string.IsNullOrEmpty(text) ? Visibility.Collapsed : Visibility.Visible;
        }

        internal static TextBlock StatusLine() => S.Body("", S.TextSecondary, 12);

        internal static Border Card(UIElement content) => new Border
        {
            Margin = new Thickness(12, 8, 12, 0),
            Padding = new Thickness(12, 9, 12, 9),
            CornerRadius = new CornerRadius(10),
            Background = new SolidColorBrush(S.InsetColour),
            BorderThickness = new Thickness(1),
            BorderBrush = new SolidColorBrush(HeronBrand.At(HeronBrand.Mist, 0x1E)),
            Child = content,
        };

        internal static Button SmallButton(string label)
        {
            var button = S.FlatButton(label, 12);
            button.Margin = new Thickness(0, 0, 4, 0);
            return button;
        }

        internal static TextBox Box(string text) => new TextBox
        {
            Text = text,
            FontFamily = new FontFamily(S.BodyFont),
            FontSize = 12.5,
            Foreground = new SolidColorBrush(S.TextPrimary),
            Background = new SolidColorBrush(S.CardColour),
            CaretBrush = new SolidColorBrush(S.TextPrimary),
            BorderBrush = new SolidColorBrush(HeronBrand.At(HeronBrand.Mist, 0x40)),
            BorderThickness = new Thickness(1),
            Padding = new Thickness(6, 4, 6, 4),
            Margin = new Thickness(0, 4, 0, 0),
        };

        internal static Document? ActiveDocument => AcApp.DocumentManager.MdiActiveDocument;
    }

    /// <summary>
    /// Issue #92: Heron's recent change jobs, newest first, each with Select,
    /// Zoom and Undo where they can act (D-123); with what happened to the drawings between them (#48),
    /// drawn again the moment a drawing opens, comes to the front, is saved or
    /// closes.
    /// </summary>
    internal sealed class ActivityTab
    {
        private readonly StackPanel _rows = new StackPanel { Margin = new Thickness(0, 0, 0, 12) };
        private readonly TextBlock _status = HeronPalette.StatusLine();
        private bool _redrawQueued;

        public ActivityTab()
        {
            Root = HeronPalette.Frame("Activity", _rows, _status);
            // Raised on a pipe thread (jobs) or the main thread (drawings); the
            // list is drawn again on the palette's own thread.
            AcadJobHost.Activity.Changed += QueueRedraw;
            AcadJobHost.Drawings.Changed += QueueRedraw;
            Redraw();
        }

        private void QueueRedraw()
        {
            if (_redrawQueued) return;
            _redrawQueued = true;
            Root.Dispatcher.BeginInvoke(DispatcherPriority.Background, new Action(Redraw));
        }

        public Border Root { get; }

        private ActivityLog Log => AcadJobHost.Activity;

        private void Redraw()
        {
            _redrawQueued = false;
            _rows.Children.Clear();
            var entries = Log.Entries;
            var active = AcadJobHost.Drawings.Active;
            if (active != null)
            {
                var front = S.Body(PaletteTexts.InFront(active), S.TextSecondary, 11.5);
                front.Margin = new Thickness(14, 10, 14, 0);
                _rows.Children.Add(front);
            }
            if (entries.Count == 0)
            {
                var none = S.Body("Nothing yet. Heron's changes in this AutoCAD show here, newest first, from every chat.", S.TextMuted, 12);
                none.Margin = new Thickness(14, 12, 14, 0);
                _rows.Children.Add(none);
            }
            var newest = entries.Count > 0 ? entries[0].Job : null;
            foreach (var row in PaletteRows.Merge(entries, AcadJobHost.Drawings.Recent(PaletteRows.MostDrawingRows)))
                _rows.Children.Add(row.Job != null ? Row(row.Job, active, row.Job.Job == newest) : DrawingRow(row.Drawing!));
        }

        /// <summary>Something that happened to a drawing: one quiet line between the jobs (#48).</summary>
        private static UIElement DrawingRow(DrawingEvent e)
        {
            var line = S.Body(e.At.ToString("HH:mm") + "  ·  " + PaletteTexts.DrawingRow(e), S.TextMuted, 11);
            line.Margin = new Thickness(16, 8, 14, 0);
            return line;
        }

        private UIElement Row(ActivityEntry entry, string? active, bool newest)
        {
            var body = new StackPanel();
            var what = S.Body(entry.Summary, S.TextPrimary, 12.5);
            what.FontWeight = FontWeights.SemiBold;
            body.Children.Add(what);
            var where = PaletteRows.InFront(entry, active) ? "" : "  ·  " + PaletteTexts.NotInFront;
            body.Children.Add(S.Body(entry.At.ToString("HH:mm") + "  ·  " + FileName(entry.Drawing) + where + "  ·  " + entry.State, S.TextMuted, 11));
            body.Children.Add(S.Body(entry.Counts, S.TextSecondary, 11));

            // Only the buttons that can act (D-123): a save or a job that made
            // nothing gets none, so no empty row of buttons either.
            var offer = PaletteRows.Buttons(entry, newest);
            if (offer.Any)
            {
                var buttons = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(-8, 6, 0, 0) };
                if (offer.Select)
                {
                    var select = HeronPalette.SmallButton("Select");
                    select.ToolTip = "Select what this job made or changed.";
                    select.Click += (s, e) => Show(entry.Job, false);
                    buttons.Children.Add(select);
                }
                if (offer.Zoom)
                {
                    var zoom = HeronPalette.SmallButton("Zoom");
                    zoom.ToolTip = "Zoom to what this job made or changed, and select it.";
                    zoom.Click += (s, e) => Show(entry.Job, true);
                    buttons.Children.Add(zoom);
                }
                if (offer.Undo)
                {
                    var undo = HeronPalette.SmallButton("Undo");
                    undo.ToolTip = "Undo this job, only if nothing changed in the drawing since.";
                    undo.Click += (s, e) => Undo(entry.Job);
                    buttons.Children.Add(undo);
                }
                body.Children.Add(buttons);
            }
            return HeronPalette.Card(body);
        }

        private void Show(string job, bool zoom)
        {
            try
            {
                var doc = HeronPalette.ActiveDocument;
                if (doc == null)
                {
                    HeronPalette.Say(_status, PaletteTexts.NoDrawing, S.WarnColour);
                    return;
                }
                var verdict = Log.CanShow(job, doc.Name);
                if (!verdict.Allowed)
                {
                    HeronPalette.Say(_status, verdict.Reason, S.WarnColour);
                    return;
                }
                var missing = new List<string>();
                int found;
                if (zoom)
                {
                    // The palette's zoom is for looking: it should leave no undo
                    // step that would stand between the job and its Undo (D-68).
                    var db = doc.Database;
                    var paused = db.UndoRecording;
                    if (paused) db.DisableUndoRecording(true);
                    try
                    {
                        found = Showing.SelectAndZoom(doc, verdict.Handles, missing);
                    }
                    finally
                    {
                        if (paused && !db.IsDisposed) db.DisableUndoRecording(false);
                    }
                }
                else
                {
                    found = Showing.SelectAndZoom(doc, verdict.Handles, missing, zoom: false);
                }
                var text = found == 0
                    ? "None of what this job made or changed is in the drawing any more."
                    : (zoom ? "Zoomed to " : "Selected ") + found + " object(s)" + (missing.Count > 0 ? "; " + missing.Count + " are gone." : ".");
                HeronPalette.Say(_status, text, found == 0 ? S.WarnColour : S.TextSecondary);
            }
            catch (Exception ex)
            {
                HeronLog.Error("Palette " + (zoom ? "zoom" : "select"), ex);
                HeronPalette.Say(_status, "Heron could not do that: " + ex.Message, S.DangerColour);
            }
        }

        private void Undo(string job)
        {
            try
            {
                var doc = HeronPalette.ActiveDocument;
                if (doc == null)
                {
                    HeronPalette.Say(_status, PaletteTexts.NoDrawing, S.WarnColour);
                    return;
                }
                var control = -1;
                try
                {
                    control = Convert.ToInt32(AcApp.GetSystemVariable("UNDOCTL"));
                }
                catch (Exception)
                {
                    // Cannot tell: the rule treats it as off, never guesses.
                }
                var facts = new UndoFacts { ActiveDrawing = doc.Name, ChangedSince = AcadJobHost.Counter.ChangedSince(job), UndoControl = control };
                var verdict = Log.CanUndo(job, facts);
                if (!verdict.Allowed)
                {
                    HeronPalette.Say(_status, verdict.Reason, S.WarnColour);
                    return;
                }
                HeronLog.Write("palette undo: " + verdict.Summary + " (" + verdict.Command.Trim() + ")");
                PaletteUndo.Start(doc, job, verdict, (text, ok) => HeronPalette.Say(_status, text, ok ? S.SafeColour : S.DangerColour));
            }
            catch (Exception ex)
            {
                HeronLog.Error("Palette undo", ex);
                HeronPalette.Say(_status, "Heron could not undo: " + ex.Message + " Nothing was changed.", S.DangerColour);
            }
        }

        private static string FileName(string drawing)
        {
            var cut = (drawing ?? "").LastIndexOfAny(new[] { '\\', '/' });
            var name = cut >= 0 ? drawing!.Substring(cut + 1) : drawing ?? "";
            return name.Length == 0 ? "no drawing" : name;
        }
    }

    /// <summary>
    /// The palette's Undo: the modeller's button, so no padlock and no chat.
    /// The command is typed into AutoCAD (a palette runs outside any command),
    /// and when UNDO ends Heron checks that what the job made is gone.
    /// </summary>
    internal static class PaletteUndo
    {
        /// <summary>UNDO typed but never started by then (a command or a box in the way): stop waiting.</summary>
        private static readonly TimeSpan StartWait = TimeSpan.FromSeconds(30);

        public static void Start(Document doc, string job, UndoVerdict verdict, Action<string, bool> say)
        {
            var done = false;
            var started = false;
            CommandEventHandler? begun = null;
            CommandEventHandler? ended = null;
            CommandEventHandler? stopped = null;
            var wait = new DispatcherTimer { Interval = StartWait };

            void Unhook()
            {
                AcadJobHost.Activity.UndoWaiting(false);
                wait.Stop();
                doc.CommandWillStart -= begun;
                doc.CommandEnded -= ended;
                doc.CommandCancelled -= stopped;
                doc.CommandFailed -= stopped;
            }

            void Finish(bool ran)
            {
                if (done) return;
                done = true;
                Unhook();
                if (!ran)
                {
                    say(PaletteTexts.UndoDidNotRun, false);
                    return;
                }
                // After UNDO has finished with the drawing, not inside its own event.
                IdleQueue.Post(() =>
                {
                    var left = StillThere(doc, verdict.MustBeGone);
                    HeronLog.Write("palette undo ended, " + left + " object(s) left");
                    if (left > 0)
                    {
                        say(PaletteTexts.UndoLeft(left), false);
                        return;
                    }
                    AcadJobHost.Activity.Undone(job);
                    say(PaletteTexts.Undone(verdict.Summary), true);
                });
            }

            begun = (s, e) => { if (IsUndo(e)) started = true; };
            ended = (s, e) => { if (IsUndo(e)) Finish(true); };
            stopped = (s, e) => { if (IsUndo(e)) Finish(false); };
            wait.Tick += (s, e) =>
            {
                // Still waiting in AutoCAD's queue: never let a later UNDO of the
                // modeller's own be taken for this one.
                if (started) return;
                if (done) return;
                done = true;
                Unhook();
                HeronLog.Write("palette undo: UNDO did not start within " + StartWait.TotalSeconds + " s");
                say(PaletteTexts.UndoDidNotStart, false);
            };
            doc.CommandWillStart += begun;
            doc.CommandEnded += ended;
            doc.CommandCancelled += stopped;
            doc.CommandFailed += stopped;
            wait.Start();
            // From here until UNDO ends, no chat's job may begin (#138).
            AcadJobHost.Activity.UndoWaiting(true);
            doc.SendStringToExecute(verdict.Command, true, false, false);
            try
            {
                // Typed input waits for the drawing to have focus; the palette has it now.
                Autodesk.AutoCAD.Internal.Utils.SetFocusToDwgView();
            }
            catch (Exception ex)
            {
                HeronLog.Error("Give the drawing focus", ex);
            }
        }

        private static bool IsUndo(CommandEventArgs e) =>
            string.Equals(e.GlobalCommandName, "UNDO", StringComparison.OrdinalIgnoreCase);

        private static int StillThere(Document doc, string[] handles)
        {
            if (doc.IsDisposed) return 0;
            var left = 0;
            foreach (var text in handles)
            {
                long value;
                try
                {
                    value = Convert.ToInt64(text, 16);
                }
                catch (Exception ex) when (ex is FormatException || ex is OverflowException || ex is ArgumentException)
                {
                    continue;
                }
                if (doc.Database.TryGetObjectId(new Handle(value), out var id) && !id.IsNull && !id.IsErased) left++;
            }
            return left;
        }
    }

    /// <summary>
    /// Issue #93: the saved commands (D-55), searched, their inputs filled, and
    /// Run through the server's gate (D-68). A command saved in a chat shows
    /// within two seconds: the folder is looked at while the palette is open.
    /// </summary>
    internal sealed class CommandsTab
    {
        private readonly TextBlock _status = HeronPalette.StatusLine();
        private readonly TextBox _search = HeronPalette.Box("");
        private readonly StackPanel _list = new StackPanel();
        private readonly StackPanel _form = new StackPanel();
        private readonly DispatcherTimer _look = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        private List<SavedCommand> _commands = new List<SavedCommand>();
        private string _seen = "";
        private SavedCommand? _picked;
        private readonly Dictionary<string, TextBox> _boxes = new Dictionary<string, TextBox>();
        private Button? _run;
        private bool _running;

        public CommandsTab()
        {
            var body = new StackPanel { Margin = new Thickness(0, 0, 0, 14) };
            var searchRow = new StackPanel { Margin = new Thickness(12, 10, 12, 0) };
            searchRow.Children.Add(S.Caption("SEARCH"));
            _search.TextChanged += (s, e) => DrawList();
            searchRow.Children.Add(_search);
            body.Children.Add(searchRow);
            body.Children.Add(_form);
            body.Children.Add(_list);
            Root = HeronPalette.Frame("Saved commands", body, _status);
            _look.Tick += (s, e) => Look();
            Root.IsVisibleChanged += (s, e) =>
            {
                if (Root.IsVisible)
                {
                    Look();
                    _look.Start();
                }
                else _look.Stop();
            };
            Look();
        }

        public Border Root { get; }

        /// <summary>Read the folder again when a file in it came, went or changed.</summary>
        private void Look()
        {
            try
            {
                var folder = SavedCommandList.DefaultFolder;
                var seen = Directory.Exists(folder)
                    ? string.Join("|", new DirectoryInfo(folder).GetFiles("*.json").Select(f => f.Name + "@" + f.LastWriteTimeUtc.Ticks).OrderBy(x => x))
                    : "";
                if (seen == _seen) return;
                _seen = seen;
                _commands = SavedCommandList.Load(folder);
                if (_picked != null && _commands.All(c => c.Name != _picked.Name)) Pick(null);
                DrawList();
            }
            catch (Exception ex)
            {
                HeronLog.Error("Palette saved commands", ex);
            }
        }

        private void DrawList()
        {
            _list.Children.Clear();
            if (_picked != null) return;
            if (_commands.Count == 0)
            {
                _list.Children.Add(Note(PaletteTexts.NoCommands));
                return;
            }
            var found = SavedCommandList.Search(_commands, _search.Text);
            if (found.Count == 0) _list.Children.Add(Note(PaletteTexts.NoMatch));
            foreach (var command in found)
            {
                var content = new StackPanel();
                var name = S.Body(command.Name, S.TextPrimary, 12.5);
                name.FontWeight = FontWeights.SemiBold;
                content.Children.Add(name);
                if (command.Description.Length > 0) content.Children.Add(S.Body(command.Description, S.TextSecondary, 11.5));
                content.Children.Add(S.Body(command.Inputs.Count + " input(s)  ·  " + command.Steps + " step(s)", S.TextMuted, 11));
                var card = S.ChoiceButton(content);
                card.Margin = new Thickness(12, 8, 12, 0);
                card.Click += (s, e) => Pick(command);
                _list.Children.Add(card);
            }
        }

        private void Pick(SavedCommand? command)
        {
            _picked = command;
            _boxes.Clear();
            _form.Children.Clear();
            _run = null;
            if (command != null)
            {
                var content = new StackPanel();
                var name = S.Body(command.Name, S.TextPrimary, 13.5);
                name.FontWeight = FontWeights.SemiBold;
                content.Children.Add(name);
                if (command.Description.Length > 0) content.Children.Add(S.Body(command.Description, S.TextSecondary, 11.5));
                foreach (var input in command.Inputs)
                {
                    var label = S.Caption(input.Name.Replace('_', ' ').ToUpperInvariant() + (input.HasDefault ? "" : "  *"));
                    content.Children.Add(label);
                    if (input.Description.Length > 0) content.Children.Add(S.Body(input.Description + (input.Hint.Length > 0 ? "  (" + input.Hint + ")" : ""), S.TextMuted, 11));
                    var box = HeronPalette.Box(input.StartText);
                    box.KeyDown += (s, e) => { if (e.Key == Key.Enter) Run(); };
                    _boxes[input.Name] = box;
                    content.Children.Add(box);
                }
                var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 14, 0, 0) };
                var back = S.GhostButton("Back");
                back.Click += (s, e) => Pick(null);
                _run = S.PrimaryButton("Run", S.AccentColour);
                _run.IsEnabled = !_running;
                _run.Click += (s, e) => Run();
                buttons.Children.Add(back);
                buttons.Children.Add(_run);
                content.Children.Add(buttons);
                content.Children.Add(S.Body("Runs through Heron's gate, as from a chat: the Changes padlock, Ask to Keep and Stop Heron now all apply.", S.TextMuted, 10.5));
                _form.Children.Add(HeronPalette.Card(content));
            }
            DrawList();
        }

        private void Run()
        {
            var command = _picked;
            if (command == null) return;
            if (_running)
            {
                HeronPalette.Say(_status, PaletteTexts.AlreadyRunning, S.WarnColour);
                return;
            }
            var typed = _boxes.ToDictionary(pair => pair.Key, pair => pair.Value.Text);
            var filled = SavedCommandList.Fill(command, typed);
            if (!filled.Ok)
            {
                HeronPalette.Say(_status, filled.Message, S.WarnColour);
                return;
            }
            if (HeronApplication.Server?.IsRunning != true)
            {
                HeronPalette.Say(_status, PaletteTexts.NotConnected, S.WarnColour);
                return;
            }
            var python = PaletteServer.FindPython(PaletteServer.DefaultPath, File.Exists, out var problem);
            if (python == null)
            {
                HeronPalette.Say(_status, problem, S.WarnColour);
                return;
            }

            string request;
            try
            {
                Directory.CreateDirectory(PaletteServer.RequestFolder);
                request = Path.Combine(PaletteServer.RequestFolder, "run-" + Guid.NewGuid().ToString("N") + ".json");
                File.WriteAllText(request, SavedCommandList.RunRequest(command, filled.Json), new UTF8Encoding(false));
            }
            catch (Exception ex)
            {
                HeronPalette.Say(_status, "Heron could not write the request: " + ex.Message + " Nothing was sent to AutoCAD.", S.DangerColour);
                return;
            }

            var start = new ProcessStartInfo
            {
                FileName = python,
                Arguments = PaletteServer.Arguments(request, Process.GetCurrentProcess().Id),
                // Never AutoCAD's own working folder (often the project share a DWG was opened
                // from): "python -m" looks there first, so a planted .py would run on Run.
                WorkingDirectory = PaletteServer.RequestFolder,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            PaletteServer.PrepareEnvironment(start.Environment);

            Busy(true);
            HeronPalette.Say(_status, PaletteTexts.Running(command.Name), S.TextSecondary);
            HeronLog.Write("palette run: " + command.Name);
            var dispatcher = Root.Dispatcher;
            // Off the main thread: the server talks to this AutoCAD over COM,
            // which needs AutoCAD free, so nothing here may wait on it.
            Task.Run(() =>
            {
                RunReply reply;
                try
                {
                    using (var process = Process.Start(start)!)
                    {
                        var errors = process.StandardError.ReadToEndAsync();
                        var output = process.StandardOutput.ReadToEnd();
                        process.WaitForExit();
                        reply = PaletteServer.Reply(output, errors.Result, process.ExitCode);
                    }
                }
                catch (Exception ex)
                {
                    reply = new RunReply { Ok = false, Message = "Heron could not start its server: " + ex.Message + " Nothing was sent to AutoCAD." };
                }
                finally
                {
                    try { File.Delete(request); } catch (Exception) { }
                }
                HeronLog.Write("palette run ended: " + (reply.Ok ? "ok" : "not ok") + ", " + reply.Message);
                dispatcher.BeginInvoke(new Action(() =>
                {
                    Busy(false);
                    HeronPalette.Say(_status, reply.Message, reply.Ok ? S.SafeColour : S.DangerColour);
                }));
            });
        }

        private void Busy(bool running)
        {
            _running = running;
            if (_run != null) _run.IsEnabled = !running;
        }

        private static TextBlock Note(string text)
        {
            var note = S.Body(text, S.TextMuted, 12);
            note.Margin = new Thickness(14, 12, 14, 0);
            return note;
        }
    }
}
