using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;
using System.Windows.Threading;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The "Heron is touching your drawing" card, the same one Heron shows in Revit.
    ///
    /// It lives on its own STA thread because AutoCAD's main thread is busy
    /// while a job runs; a banner painted there would freeze exactly when it
    /// matters. It is click-through, never takes focus and has no taskbar entry.
    /// </summary>
    internal sealed class HeronActivityBanner
    {
        public const string ReadingTitle = "Heron AI is reading your drawing";
        public const string ChangingTitle = "Heron AI is changing your drawing";
        public const string DoneTitle = "Heron AI has finished";
        public const string StoppedTitle = "Heron AI stopped";

        private static readonly Color Card = Rgb(0x23, 0x26, 0x29);
        private static readonly Color Reading = Rgb(0x2F, 0x9B, 0xE3);
        private static readonly Color Changing = Rgb(0xF0, 0xA3, 0x2C);
        private static readonly Color Done = Rgb(0x4C, 0xC3, 0x8A);
        private static readonly Color Stopped = Rgb(0xE5, 0x53, 0x4B);
        private static readonly TimeSpan HoldOutcome = TimeSpan.FromMilliseconds(1400);

        private readonly IntPtr _owner;
        private Dispatcher? _dispatcher;
        private Window? _window;
        private TextBlock? _title, _chip, _drawing, _job;
        private Border? _chipBox;
        private Ellipse? _lamp;
        private DispatcherTimer? _clock, _hide;
        private DateTime _started;
        private string _jobText = "";
        // By job name, not a count: a lost end must not hold the DONE card open.
        private readonly BannerJobs _jobs = new BannerJobs();

        public HeronActivityBanner(IntPtr acadWindow)
        {
            _owner = acadWindow;
        }

        public void Begin(JobInfo job)
        {
            _jobs.Begin(job, DateTime.UtcNow);
            var changing = job.Risk != Risk.Read && job.Risk != Risk.View;
            Run(() =>
            {
                _hide?.Stop();
                _started = DateTime.Now;
                _jobText = job.Summary;
                Paint(changing ? ChangingTitle : ReadingTitle, changing ? "CHANGING" : "READING", changing ? Changing : Reading);
                _drawing!.Text = string.IsNullOrEmpty(job.Drawing) ? "No drawing open" : System.IO.Path.GetFileName(job.Drawing);
                Tick();
                Place();
                _window!.Show();
                _clock!.Start();
            });
        }

        public void End(JobEnd end)
        {
            _jobs.End(end.Job);
            Run(() =>
            {
                _clock!.Stop();
                if (end.Ok) Paint(DoneTitle, "DONE", Done);
                else Paint(StoppedTitle, "STOPPED", Stopped);
                _job!.Text = string.IsNullOrEmpty(end.Summary) ? _jobText : end.Summary;
                _hide!.Stop();
                _hide.Start();
            });
        }

        private void Paint(string title, string chip, Color color)
        {
            _title!.Text = title;
            _chip!.Text = chip;
            _chipBox!.Background = new SolidColorBrush(color);
            _lamp!.Fill = new SolidColorBrush(color);
        }

        private void Tick()
        {
            var seconds = (DateTime.Now - _started).TotalSeconds;
            _job!.Text = _jobText + "  ·  " + seconds.ToString("0.0") + " s";
        }

        private void Run(Action action)
        {
            EnsureThread();
            _dispatcher!.BeginInvoke(new Action(() =>
            {
                try
                {
                    action();
                }
                catch (Exception ex)
                {
                    HeronLog.Error("Banner", ex);
                }
            }));
        }

        private void EnsureThread()
        {
            if (_dispatcher != null) return;
            var ready = new ManualResetEventSlim(false);
            var thread = new Thread(() =>
            {
                Build();
                _dispatcher = Dispatcher.CurrentDispatcher;
                ready.Set();
                Dispatcher.Run();
            })
            {
                IsBackground = true,
                Name = "Heron banner",
            };
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
            ready.Wait(TimeSpan.FromSeconds(5));
        }

        private void Build()
        {
            _lamp = new Ellipse { Width = 12, Height = 12, Margin = new Thickness(0, 0, 12, 0), VerticalAlignment = VerticalAlignment.Center };
            var pulse = new DoubleAnimation(1.0, 0.35, TimeSpan.FromMilliseconds(700)) { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever };
            _lamp.BeginAnimation(UIElement.OpacityProperty, pulse);

            _title = Text(15, FontWeights.SemiBold, Colors.White);
            _chip = Text(11, FontWeights.Bold, Colors.White);
            _chipBox = new Border { CornerRadius = new CornerRadius(4), Padding = new Thickness(7, 2, 7, 2), Margin = new Thickness(10, 0, 0, 0), Child = _chip, VerticalAlignment = VerticalAlignment.Center };
            _drawing = Text(12, FontWeights.Normal, Rgb(0xC9, 0xD1, 0xD9));
            _job = Text(12, FontWeights.Normal, Rgb(0x9A, 0xA4, 0xAE));

            var head = new StackPanel { Orientation = Orientation.Horizontal };
            head.Children.Add(_title);
            head.Children.Add(_chipBox);
            var lines = new StackPanel();
            lines.Children.Add(head);
            lines.Children.Add(_drawing);
            lines.Children.Add(_job);
            var row = new StackPanel { Orientation = Orientation.Horizontal };
            row.Children.Add(_lamp);
            row.Children.Add(lines);

            _window = new Window
            {
                Width = 460,
                Height = 98,
                WindowStyle = WindowStyle.None,
                AllowsTransparency = true,
                Background = Brushes.Transparent,
                ResizeMode = ResizeMode.NoResize,
                ShowInTaskbar = false,
                ShowActivated = false,
                Focusable = false,
                Topmost = true,
                Content = new Border
                {
                    Background = new SolidColorBrush(Card),
                    CornerRadius = new CornerRadius(10),
                    Padding = new Thickness(18, 12, 18, 12),
                    Child = row,
                    BorderBrush = new SolidColorBrush(Rgb(0x3A, 0x3F, 0x44)),
                    BorderThickness = new Thickness(1),
                },
            };
            _window.SourceInitialized += (s, e) => MakeClickThrough(new WindowInteropHelper(_window).Handle);

            _clock = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
            _clock.Tick += (s, e) => Tick();
            _hide = new DispatcherTimer { Interval = HoldOutcome };
            _hide.Tick += (s, e) =>
            {
                _hide!.Stop();
                if (_jobs.AllDone(DateTime.UtcNow)) _window!.Hide();
                // A job is still running: look again, so a lost end clears
                // itself after BannerJobs.StaleAfter instead of never.
                else _hide.Start();
            };
        }

        private void Place()
        {
            if (_owner == IntPtr.Zero || !GetWindowRect(_owner, out var rect)) return;
            // Window pixels to WPF units, from AutoCAD's own monitor DPI (the
            // banner is not shown yet, so it has no DPI of its own to ask).
            var dpi = GetDpiForWindow(_owner);
            var scale = dpi > 0 ? 96.0 / dpi : 1.0;
            var left = rect.Left * scale;
            var width = (rect.Right - rect.Left) * scale;
            _window!.Left = left + (width - _window.Width) / 2;
            _window.Top = rect.Top * scale + 110;
        }

        private static TextBlock Text(double size, FontWeight weight, Color color) =>
            new TextBlock { FontSize = size, FontWeight = weight, Foreground = new SolidColorBrush(color), FontFamily = new FontFamily("Segoe UI") };

        private static Color Rgb(byte r, byte g, byte b) => Color.FromRgb(r, g, b);

        private const int GwlExStyle = -20;
        private const int WsExTransparent = 0x20, WsExToolWindow = 0x80, WsExLayered = 0x80000, WsExNoActivate = 0x8000000;

        private static void MakeClickThrough(IntPtr hwnd)
        {
            var style = GetWindowLong(hwnd, GwlExStyle);
            SetWindowLong(hwnd, GwlExStyle, style | WsExTransparent | WsExToolWindow | WsExLayered | WsExNoActivate);
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct Rect
        {
            public int Left, Top, Right, Bottom;
        }

        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);

        [DllImport("user32.dll")]
        private static extern uint GetDpiForWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern int GetWindowLong(IntPtr hwnd, int index);

        [DllImport("user32.dll")]
        private static extern int SetWindowLong(IntPtr hwnd, int index, int value);
    }
}
