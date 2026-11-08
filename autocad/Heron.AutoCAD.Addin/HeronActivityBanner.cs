using System;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Shapes;
using System.Windows.Threading;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The "Heron is touching your drawing" card, drawn as Heron for Revit draws
    /// it since 2026-11-07 (D-45): the designer's "Heron status bar" - a smoked
    /// glass card with rounded corners, a hairline rim of white and the state's
    /// colour, the colour washed across it with two soft blooms, a sheen
    /// travelling over it, an aura turning on the rim and a breathing glow while
    /// a job runs, sliding down from above and settling. Two lines: "Heron AI ·
    /// Changing" in the state's colour with three dots and the time, then the
    /// drawing and the job. Reading and changing are both the brand's orange;
    /// the WORD says which. Done is Success, a stop is Error.
    ///
    /// It lives on its own STA thread because AutoCAD's main thread is busy
    /// while a job runs; a banner painted there would freeze exactly when it
    /// matters. It is click-through, never takes focus and has no taskbar entry.
    /// </summary>
    internal sealed class HeronActivityBanner
    {
        public const string ReadingTitle = "Heron AI  ·  Reading";
        public const string ChangingTitle = "Heron AI  ·  Changing";
        public const string DoneTitle = "Heron AI  ·  Done";
        public const string StoppedTitle = "Heron AI  ·  Needs attention";

        private const double BannerWidth = 460;
        private const double BannerHeight = 66;
        private const double GlowPad = 18;
        private const double SweepWidth = 115;

        /// <summary>Below AutoCAD's title bar and ribbon, as before.</summary>
        private const double TopOffset = 110;

        private static readonly TimeSpan HoldOutcome = TimeSpan.FromMilliseconds(1400);
        private static readonly TimeSpan SweepDuration = TimeSpan.FromSeconds(3.2);
        private static readonly TimeSpan ElapsedTick = TimeSpan.FromMilliseconds(100);

        private static readonly Color Ink = HeronBrand.Ink;
        private static readonly Color Mist = HeronBrand.Mist;
        private static readonly Color Accent = HeronBrand.Accent;
        private static readonly Color AccentLight = HeronBrand.AccentLight;
        private static readonly Color Done = HeronBrand.Success;
        private static readonly Color Stopped = HeronBrand.Error;
        private static readonly Color White = HeronBrand.White;

        private readonly IntPtr _owner;
        private Dispatcher? _dispatcher;
        private Window? _window;
        private DispatcherTimer? _clock, _hide;
        // By job name, not a count: a lost end must not hold the DONE card open.
        private readonly BannerJobs _jobs = new BannerJobs();

        private TextBlock? _chipText, _detail, _title;
        private StackPanel? _dots, _eyebrow;
        private Border? _sweep;
        private Canvas? _lane;
        private DoubleAnimation? _travel;
        private TranslateTransform? _cardTransform;
        private ScaleTransform? _cardScale;
        private Grid? _card, _aura;
        private RotateTransform? _auraTurn;
        private LinearGradientBrush? _auraBrush, _rimBrush, _washBrush;
        private RadialGradientBrush? _bloomLeft, _bloomRight;
        private Ellipse? _bloomL, _bloomR;
        private SolidColorBrush? _chipBrush;
        private DropShadowEffect? _glow;
        private bool _pulsing, _live;
        private long _startedTicks;

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
                // One running total for a run of jobs back to back, as in Revit.
                if (!_live) _startedTicks = Stopwatch.GetTimestamp();
                _live = true;
                Paint(changing, job.Summary, DrawingName(job.Drawing));
                Show();
            });
        }

        public void End(JobEnd end)
        {
            _jobs.End(end.Job);
            Run(() =>
            {
                ShowOutcome(end);
                _hide!.Stop();
                _hide.Start();
            });
        }

        // ----- what it says -------------------------------------------------

        private static string DrawingName(string drawing) =>
            string.IsNullOrEmpty(drawing) ? "No drawing open" : System.IO.Path.GetFileName(drawing);

        private static string Message(string drawing, string words) =>
            string.IsNullOrEmpty(drawing) ? words : drawing + "  ·  " + words;

        private void Paint(bool changing, string job, string drawing)
        {
            var eyebrow = changing ? ChangingTitle : ReadingTitle;
            var changed = _chipText!.Text != eyebrow;
            _chipText.Text = eyebrow;
            SetAccent(Accent);

            var message = Message(drawing, string.IsNullOrEmpty(job) ? "Working" : job);
            if (_title!.Text != message)
            {
                _title.Text = message;
                TextIn(_title);
            }
            if (changed)
            {
                TextIn(_eyebrow);
                Bump();
            }

            _dots!.Visibility = Visibility.Visible;
            _detail!.Visibility = Visibility.Visible;
            Tick();
            _clock!.Start();
            _lane!.Visibility = Visibility.Visible;
            _sweep!.BeginAnimation(Canvas.LeftProperty, _travel);
            StartPulse();
        }

        private void ShowOutcome(JobEnd end)
        {
            _clock!.Stop();
            _chipText!.Text = end.Ok ? DoneTitle : StoppedTitle;
            var words = !string.IsNullOrEmpty(end.Summary) ? end.Summary
                : end.Ok ? "Done"
                : !string.IsNullOrEmpty(end.Outcome) ? end.Outcome : "Did not finish";
            var drawing = _title!.Text;
            var cut = drawing.IndexOf("  ·  ", StringComparison.Ordinal);
            _title.Text = Message(cut > 0 ? drawing.Substring(0, cut) : "", words);
            Tick();
            _dots!.Visibility = Visibility.Collapsed;

            SetAccent(end.Ok ? Done : Stopped);
            TextIn(_eyebrow);
            TextIn(_title);
            Bump();
            StopPulse();
            _sweep!.BeginAnimation(Canvas.LeftProperty, null);
            _lane!.Visibility = Visibility.Collapsed;
        }

        private void Tick() => _detail!.Text = Elapsed(ElapsedMs());

        private long ElapsedMs()
        {
            var delta = Stopwatch.GetTimestamp() - _startedTicks;
            return _startedTicks == 0 || delta <= 0 ? 0 : delta * 1000L / Stopwatch.Frequency;
        }

        /// <summary>Tenths of a second once past one, so it is seen moving.</summary>
        private static string Elapsed(long ms) =>
            ms < 1000 ? ms.ToString(CultureInfo.InvariantCulture) + " ms"
                      : (ms / 1000.0).ToString("0.0", CultureInfo.InvariantCulture) + " s";

        // ----- the look (as Heron for Revit) ---------------------------------

        private static Color At(Color colour, byte alpha) => HeronBrand.At(colour, alpha);

        private void SetAccent(Color accent)
        {
            if (_chipBrush!.Color != accent)
                _chipBrush.BeginAnimation(SolidColorBrush.ColorProperty, new ColorAnimation(accent, new Duration(TimeSpan.FromMilliseconds(250))));

            _rimBrush!.GradientStops[0].Color = At(White, 0x8C);
            _rimBrush.GradientStops[1].Color = At(accent, 0xB3);
            _rimBrush.GradientStops[2].Color = At(White, 0x14);
            _rimBrush.GradientStops[3].Color = At(accent, 0x73);

            _washBrush!.GradientStops[0].Color = At(accent, 0x29);
            _washBrush.GradientStops[1].Color = At(accent, 0x0A);
            _washBrush.GradientStops[2].Color = At(accent, 0x14);

            var orange = accent == Accent;
            _bloomLeft!.GradientStops[0].Color = At(accent, orange ? (byte)0x1F : (byte)0x2E);
            _bloomLeft.GradientStops[1].Color = At(accent, 0x00);
            _bloomRight!.GradientStops[0].Color = At(accent, orange ? (byte)0x1A : (byte)0x24);
            _bloomRight.GradientStops[1].Color = orange ? At(Mist, 0x0A) : At(accent, 0x12);
            _bloomRight.GradientStops[2].Color = At(orange ? Mist : accent, 0x00);

            _auraBrush!.GradientStops[0].Color = At(accent, 0xFF);
            _auraBrush.GradientStops[1].Color = orange ? AccentLight : At(accent, 0xB3);
            _auraBrush.GradientStops[2].Color = At(accent, 0x00);
            _auraBrush.GradientStops[3].Color = At(accent, 0xFF);
            _auraBrush.GradientStops[4].Color = At(accent, 0x00);

            _glow!.Color = accent;
        }

        /// <summary>Up 4 px and in, over 350 ms, when what the card says changes.</summary>
        private static void TextIn(UIElement? element)
        {
            if (element == null) return;
            if (!(element.RenderTransform is TranslateTransform shift))
            {
                shift = new TranslateTransform();
                element.RenderTransform = shift;
            }
            var duration = new Duration(TimeSpan.FromMilliseconds(350));
            shift.BeginAnimation(TranslateTransform.YProperty,
                new DoubleAnimation(4, 0, duration) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } });
            element.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, 1, duration));
        }

        /// <summary>A small breath of the card when the state changes: 420 ms.</summary>
        private void Bump()
        {
            var x = new DoubleAnimationUsingKeyFrames { Duration = new Duration(TimeSpan.FromMilliseconds(420)) };
            x.KeyFrames.Add(new LinearDoubleKeyFrame(1.01, KeyTime.FromPercent(0.4)));
            x.KeyFrames.Add(new LinearDoubleKeyFrame(1.0, KeyTime.FromPercent(1.0)));
            var y = new DoubleAnimationUsingKeyFrames { Duration = new Duration(TimeSpan.FromMilliseconds(420)) };
            y.KeyFrames.Add(new LinearDoubleKeyFrame(0.97, KeyTime.FromPercent(0.4)));
            y.KeyFrames.Add(new LinearDoubleKeyFrame(1.005, KeyTime.FromPercent(0.7)));
            y.KeyFrames.Add(new LinearDoubleKeyFrame(1.0, KeyTime.FromPercent(1.0)));
            _cardScale!.BeginAnimation(ScaleTransform.ScaleXProperty, x);
            _cardScale.BeginAnimation(ScaleTransform.ScaleYProperty, y);
        }

        /// <summary>The dots, the aura, the glow and the blooms - started once, not per job.</summary>
        private void StartPulse()
        {
            if (_pulsing) return;
            for (var i = 0; i < _dots!.Children.Count; i++)
            {
                if (!(_dots.Children[i] is FrameworkElement dot)) continue;
                var begin = TimeSpan.FromMilliseconds(150 * i);
                var fade = new DoubleAnimationUsingKeyFrames { Duration = new Duration(TimeSpan.FromMilliseconds(1200)), RepeatBehavior = RepeatBehavior.Forever, BeginTime = begin };
                fade.KeyFrames.Add(new LinearDoubleKeyFrame(0.25, KeyTime.FromPercent(0)));
                fade.KeyFrames.Add(new LinearDoubleKeyFrame(1.0, KeyTime.FromPercent(0.4)));
                fade.KeyFrames.Add(new LinearDoubleKeyFrame(0.25, KeyTime.FromPercent(0.8)));
                fade.KeyFrames.Add(new LinearDoubleKeyFrame(0.25, KeyTime.FromPercent(1.0)));
                dot.BeginAnimation(UIElement.OpacityProperty, fade);
                var lift = new DoubleAnimationUsingKeyFrames { Duration = new Duration(TimeSpan.FromMilliseconds(1200)), RepeatBehavior = RepeatBehavior.Forever, BeginTime = begin };
                lift.KeyFrames.Add(new LinearDoubleKeyFrame(0, KeyTime.FromPercent(0)));
                lift.KeyFrames.Add(new LinearDoubleKeyFrame(-2, KeyTime.FromPercent(0.4)));
                lift.KeyFrames.Add(new LinearDoubleKeyFrame(0, KeyTime.FromPercent(0.8)));
                lift.KeyFrames.Add(new LinearDoubleKeyFrame(0, KeyTime.FromPercent(1.0)));
                if (!(dot.RenderTransform is TranslateTransform shift)) { shift = new TranslateTransform(); dot.RenderTransform = shift; }
                shift.BeginAnimation(TranslateTransform.YProperty, lift);
            }
            _aura!.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(1, new Duration(TimeSpan.FromMilliseconds(500))));
            _auraTurn!.BeginAnimation(RotateTransform.AngleProperty, new DoubleAnimation(0, 360, new Duration(TimeSpan.FromSeconds(6))) { RepeatBehavior = RepeatBehavior.Forever });
            _glow!.BeginAnimation(DropShadowEffect.OpacityProperty, new DoubleAnimation(0.22, 0.34, new Duration(TimeSpan.FromMilliseconds(1200)))
            {
                AutoReverse = true,
                RepeatBehavior = RepeatBehavior.Forever,
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
            });
            Drift(_bloomL, 5, false);
            Drift(_bloomR, 6, true);
            _pulsing = true;
        }

        private static void Drift(Ellipse? bloom, double seconds, bool reverse)
        {
            if (bloom == null) return;
            var half = new Duration(TimeSpan.FromSeconds(seconds / 2));
            var ease = new SineEase { EasingMode = EasingMode.EaseInOut };
            bloom.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(reverse ? 0.6 : 1.0, reverse ? 1.0 : 0.6, half) { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = ease });
            if (!(bloom.RenderTransform is TranslateTransform shift)) { shift = new TranslateTransform(); bloom.RenderTransform = shift; }
            shift.BeginAnimation(TranslateTransform.XProperty, new DoubleAnimation(reverse ? 14 : 0, reverse ? 0 : 14, half) { AutoReverse = true, RepeatBehavior = RepeatBehavior.Forever, EasingFunction = ease });
        }

        /// <summary>Stops them; an outcome is still, with one flash of its colour.</summary>
        private void StopPulse()
        {
            foreach (FrameworkElement dot in _dots!.Children)
            {
                dot.BeginAnimation(UIElement.OpacityProperty, null);
                dot.Opacity = 1.0;
                (dot.RenderTransform as TranslateTransform)?.BeginAnimation(TranslateTransform.YProperty, null);
            }
            _aura!.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(0, new Duration(TimeSpan.FromMilliseconds(500))));
            _auraTurn!.BeginAnimation(RotateTransform.AngleProperty, null);
            _glow!.BeginAnimation(DropShadowEffect.OpacityProperty, new DoubleAnimation(0.65, 0.28, new Duration(TimeSpan.FromMilliseconds(900))) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } });
            foreach (var bloom in new[] { _bloomL!, _bloomR! })
            {
                bloom.BeginAnimation(UIElement.OpacityProperty, null);
                bloom.Opacity = 1.0;
                (bloom.RenderTransform as TranslateTransform)?.BeginAnimation(TranslateTransform.XProperty, null);
            }
            _pulsing = false;
        }

        // ----- the window ---------------------------------------------------

        private void Show()
        {
            if (!_window!.IsVisible)
            {
                Place();
                _cardTransform!.Y = -(BannerHeight + 40);
                _card!.Opacity = 0;
                _window.Show();
            }
            _cardTransform!.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(0, new Duration(TimeSpan.FromMilliseconds(560)))
            {
                EasingFunction = new BackEase { EasingMode = EasingMode.EaseOut, Amplitude = 0.3 },
            });
            _card!.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(1, new Duration(TimeSpan.FromMilliseconds(240))));
        }

        private void SlideAway()
        {
            if (!_window!.IsVisible) return;
            var fade = new DoubleAnimation(0, new Duration(TimeSpan.FromMilliseconds(300))) { BeginTime = TimeSpan.FromMilliseconds(80) };
            fade.Completed += (s, e) =>
            {
                if (!_jobs.AllDone(DateTime.UtcNow)) return;
                _window.Hide();
                _live = false;
            };
            _cardTransform!.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(-(BannerHeight + 40), new Duration(TimeSpan.FromMilliseconds(380)))
            {
                EasingFunction = new CubicEase { EasingMode = EasingMode.EaseIn },
            });
            _card!.BeginAnimation(UIElement.OpacityProperty, fade);
        }

        private void Run(Action action)
        {
            EnsureThread();
            _dispatcher?.BeginInvoke(new Action(() =>
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
                try
                {
                    Build();
                }
                catch (Exception ex)
                {
                    HeronLog.Error("Banner build", ex);
                }
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
            _chipBrush = new SolidColorBrush(Accent);

            // THE TOP LINE: "Heron AI  ·  Changing" in the state's colour, three dots, the time.
            _chipText = Line(11, FontWeights.SemiBold, Accent);
            _chipText.Foreground = _chipBrush;
            _chipText.TextTrimming = TextTrimming.CharacterEllipsis;
            _dots = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(6, 0, 0, 3) };
            for (var i = 0; i < 3; i++)
                _dots.Children.Add(new Ellipse { Width = 3, Height = 3, Margin = new Thickness(0, 0, 2, 0), Fill = _chipBrush });
            _detail = Line(11, FontWeights.SemiBold, At(White, 0x66));
            _detail.Margin = new Thickness(6, 0, 0, 0);
            Typography.SetNumeralAlignment(_detail, FontNumeralAlignment.Tabular);
            _eyebrow = new StackPanel { Orientation = Orientation.Horizontal, Height = 15 };
            _eyebrow.Children.Add(_chipText);
            _eyebrow.Children.Add(_dots);
            _eyebrow.Children.Add(_detail);

            // THE MESSAGE: the drawing, then the job.
            _title = Line(14, FontWeights.SemiBold, Mist);
            _title.Margin = new Thickness(0, 2, 0, 0);
            _title.TextTrimming = TextTrimming.CharacterEllipsis;
            var words = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(18, 0, 14, 0) };
            words.Children.Add(_eyebrow);
            words.Children.Add(_title);

            // THE GLASS: Ink at 92 to 86 per cent.
            var glass = new Border { CornerRadius = new CornerRadius(20), Background = new LinearGradientBrush(At(Ink, 0xEB), At(Ink, 0xDB), 45) };

            // THE WASH and THE BLOOMS.
            _washBrush = new LinearGradientBrush { StartPoint = new Point(0, 0.5), EndPoint = new Point(1, 0.5) };
            _washBrush.GradientStops.Add(new GradientStop(At(Accent, 0x29), 0.0));
            _washBrush.GradientStops.Add(new GradientStop(At(Accent, 0x0A), 0.5));
            _washBrush.GradientStops.Add(new GradientStop(At(Accent, 0x14), 1.0));
            var wash = new Border { Background = _washBrush };
            _bloomLeft = new RadialGradientBrush();
            _bloomLeft.GradientStops.Add(new GradientStop(At(Accent, 0x1F), 0.0));
            _bloomLeft.GradientStops.Add(new GradientStop(At(Accent, 0x00), 1.0));
            _bloomRight = new RadialGradientBrush();
            _bloomRight.GradientStops.Add(new GradientStop(At(Accent, 0x1A), 0.0));
            _bloomRight.GradientStops.Add(new GradientStop(At(Mist, 0x0A), 0.6));
            _bloomRight.GradientStops.Add(new GradientStop(At(Mist, 0x00), 1.0));
            var blooms = new Canvas();
            _bloomL = new Ellipse { Width = 200, Height = 120, Fill = _bloomLeft };
            Canvas.SetLeft(_bloomL, -61.2);
            Canvas.SetTop(_bloomL, -41.2);
            _bloomR = new Ellipse { Width = 220, Height = 120, Fill = _bloomRight };
            Canvas.SetLeft(_bloomR, BannerWidth - 220 + 38.8);
            Canvas.SetTop(_bloomR, 18.8);
            blooms.Children.Add(_bloomL);
            blooms.Children.Add(_bloomR);

            // THE SHEEN while a job runs: an indeterminate sweep, not a percentage.
            var sheen = new LinearGradientBrush { StartPoint = new Point(0, 0.5), EndPoint = new Point(1, 0.5) };
            sheen.GradientStops.Add(new GradientStop(At(White, 0x00), 0.0));
            sheen.GradientStops.Add(new GradientStop(At(White, 0x1F), 0.5));
            sheen.GradientStops.Add(new GradientStop(At(White, 0x00), 1.0));
            _sweep = new Border { Width = SweepWidth, Height = BannerHeight, Background = sheen, RenderTransform = new SkewTransform(-20, 0, SweepWidth / 2, BannerHeight / 2) };
            _lane = new Canvas();
            _lane.Children.Add(_sweep);
            Canvas.SetLeft(_sweep, -1.2 * SweepWidth);

            // THE LINE OF LIGHT along the top edge.
            var highlight = new Border
            {
                Height = 1,
                Margin = new Thickness(20, 0, 20, 0),
                VerticalAlignment = VerticalAlignment.Top,
                Background = new LinearGradientBrush
                {
                    StartPoint = new Point(0, 0.5),
                    EndPoint = new Point(1, 0.5),
                    GradientStops =
                    {
                        new GradientStop(At(White, 0x00), 0.0),
                        new GradientStop(At(White, 0xB3), 0.5),
                        new GradientStop(At(White, 0x00), 1.0),
                    },
                },
            };

            var layers = new Grid { Clip = new RectangleGeometry(new Rect(0, 0, BannerWidth, BannerHeight), 20, 20) };
            layers.Children.Add(glass);
            layers.Children.Add(wash);
            layers.Children.Add(blooms);
            layers.Children.Add(_lane);
            layers.Children.Add(highlight);
            layers.Children.Add(words);

            // THE RIM.
            _rimBrush = new LinearGradientBrush { StartPoint = new Point(0, 0.21), EndPoint = new Point(1, 0.79) };
            _rimBrush.GradientStops.Add(new GradientStop(At(White, 0x8C), 0.0));
            _rimBrush.GradientStops.Add(new GradientStop(At(Accent, 0xB3), 0.35));
            _rimBrush.GradientStops.Add(new GradientStop(At(White, 0x14), 0.6));
            _rimBrush.GradientStops.Add(new GradientStop(At(Accent, 0x73), 1.0));
            var rim = new Border { CornerRadius = new CornerRadius(20), BorderThickness = new Thickness(1.2), BorderBrush = _rimBrush };

            // THE AURA while a job runs: the colour travelling round the rim.
            _auraTurn = new RotateTransform(0, 0.5, 0.5);
            _auraBrush = new LinearGradientBrush { StartPoint = new Point(0, 0), EndPoint = new Point(1, 1), RelativeTransform = _auraTurn };
            _auraBrush.GradientStops.Add(new GradientStop(Accent, 0.0));
            _auraBrush.GradientStops.Add(new GradientStop(AccentLight, 0.12));
            _auraBrush.GradientStops.Add(new GradientStop(At(Accent, 0x00), 0.34));
            _auraBrush.GradientStops.Add(new GradientStop(Accent, 0.62));
            _auraBrush.GradientStops.Add(new GradientStop(At(Accent, 0x00), 0.9));
            var halo = new Border { Margin = new Thickness(-1), CornerRadius = new CornerRadius(21), BorderThickness = new Thickness(3), BorderBrush = _auraBrush, Opacity = 0.3, Effect = new BlurEffect { Radius = 8 } };
            var ring = new Border { CornerRadius = new CornerRadius(20), BorderThickness = new Thickness(1), BorderBrush = _auraBrush };
            _aura = new Grid { Opacity = 0, IsHitTestVisible = false };
            _aura.Children.Add(halo);
            _aura.Children.Add(ring);

            // THE GLOW beneath the card.
            _glow = new DropShadowEffect { Color = Accent, ShadowDepth = 6, Direction = 270, BlurRadius = 26, Opacity = 0.28 };

            _cardTransform = new TranslateTransform();
            _cardScale = new ScaleTransform(1, 1);
            var transforms = new TransformGroup();
            transforms.Children.Add(_cardScale);
            transforms.Children.Add(_cardTransform);
            var body = new Grid { Effect = _glow };
            body.Children.Add(layers);
            body.Children.Add(rim);
            _card = new Grid { Width = BannerWidth, Height = BannerHeight, RenderTransform = transforms, RenderTransformOrigin = new Point(0.5, 0.5) };
            _card.Children.Add(body);
            _card.Children.Add(_aura);

            _travel = new DoubleAnimation
            {
                From = -1.2 * SweepWidth,
                To = 3.2 * SweepWidth,
                Duration = new Duration(SweepDuration),
                RepeatBehavior = RepeatBehavior.Forever,
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
            };
            _travel.Freeze();

            _window = new Window
            {
                Width = BannerWidth + 2 * GlowPad,
                Height = BannerHeight + 2 * GlowPad,
                Content = new Border { Padding = new Thickness(GlowPad), Child = _card },
                WindowStyle = WindowStyle.None,
                AllowsTransparency = true,
                Background = Brushes.Transparent,
                ResizeMode = ResizeMode.NoResize,
                ShowInTaskbar = false,
                ShowActivated = false,
                Focusable = false,
                Topmost = true,
                FontFamily = new FontFamily(HeronBrand.FontList),
                Title = "Heron AI",
            };
            _window.SourceInitialized += (s, e) => MakeClickThrough(new WindowInteropHelper(_window).Handle);

            _clock = new DispatcherTimer { Interval = ElapsedTick };
            _clock.Tick += (s, e) =>
            {
                if (_jobs.AllDone(DateTime.UtcNow)) _clock.Stop();
                else Tick();
            };
            _hide = new DispatcherTimer { Interval = HoldOutcome };
            _hide.Tick += (s, e) =>
            {
                _hide!.Stop();
                if (_jobs.AllDone(DateTime.UtcNow)) SlideAway();
                // A job is still running: look again, so a lost end clears
                // itself after BannerJobs.StaleAfter instead of never.
                else _hide.Start();
            };
        }

        private static TextBlock Line(double size, FontWeight weight, Color colour) => new TextBlock
        {
            FontFamily = new FontFamily(HeronBrand.FontList),
            FontSize = size,
            FontWeight = weight,
            Foreground = new SolidColorBrush(colour),
            Text = string.Empty,
        };

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
            _window.Top = rect.Top * scale + TopOffset - GlowPad;
        }

        private const int GwlExStyle = -20;
        private const int WsExTransparent = 0x20, WsExToolWindow = 0x80, WsExLayered = 0x80000, WsExNoActivate = 0x8000000;

        private static void MakeClickThrough(IntPtr hwnd)
        {
            var style = GetWindowLong(hwnd, GwlExStyle);
            SetWindowLong(hwnd, GwlExStyle, style | WsExTransparent | WsExToolWindow | WsExLayered | WsExNoActivate);
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct NativeRect
        {
            public int Left, Top, Right, Bottom;
        }

        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr hwnd, out NativeRect rect);

        [DllImport("user32.dll")]
        private static extern uint GetDpiForWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern int GetWindowLong(IntPtr hwnd, int index);

        [DllImport("user32.dll")]
        private static extern int SetWindowLong(IntPtr hwnd, int index, int value);
    }
}
