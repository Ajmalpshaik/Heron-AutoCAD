using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using S = Heron.AutoCAD.Addin.HeronWindowStyle;

namespace Heron.AutoCAD.Addin
{
    /// <summary>What one switch asks on the way to its risky side.</summary>
    internal sealed class HeronSwitchQuestion
    {
        public string Name { get; set; } = "";
        public string Icon { get; set; } = "";
        public string Headline { get; set; } = "";
        public string What { get; set; } = "";
        /// <summary>Ticks: what still protects the modeller.</summary>
        public string[] Promises { get; set; } = new string[0];
        /// <summary>A warning sign: what Ctrl+Z cannot take back.</summary>
        public string? Caution { get; set; }
        /// <summary>"Changes is off - Admin needs it on too", or null.</summary>
        public string? ChangesOff { get; set; }
        public string TurnOn { get; set; } = "Turn on";
        public string Decline { get; set; } = "Leave off";
    }

    /// <summary>
    /// The question a switch asks before Heron may do more - drawn as Heron for
    /// Revit's switch window (D-45): the padlock picture and the question, a tick
    /// for each promise, a warning sign for each caution, then "Leave off" and a
    /// Warning-coloured "Turn on". Esc, the ✕ and Leave off all say no.
    /// </summary>
    internal static class HeronSwitchWindow
    {
        private const double CardWidth = 460;
        private const int IconSize = 40;

        /// <summary>
        /// TRUE to go ahead, FALSE to leave it, NULL when the window could not
        /// be shown at all - which is not "no", and the caller asks plainly.
        /// </summary>
        public static bool? Ask(HeronSwitchQuestion question)
        {
            try
            {
                var answer = false;
                S.Shell? shell = null;
                void Decide(bool yes)
                {
                    answer = yes;
                    shell!.Close();
                }

                var leave = S.GhostButton(question.Decline);
                leave.IsCancel = true;
                leave.Click += (s, e) => Decide(false);
                var turnOn = S.PrimaryButton(question.TurnOn, S.WarnColour);
                turnOn.Click += (s, e) => Decide(true);
                var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
                buttons.Children.Add(leave);
                buttons.Children.Add(turnOn);

                var body = new StackPanel();
                body.Children.Add(Question(question));
                body.Children.Add(Lines(question));
                body.Children.Add(S.Footer(buttons));
                shell = S.Build(question.Name, CardWidth, body, S.WarnColour, () => Decide(false));
                // Leave off has the keyboard first: Enter never turns a switch on.
                shell.Window.Loaded += (s, e) => leave.Focus();
                HeronLog.Write(question.Name + " window asked.");
                AcApp.ShowModalWindow(AcApp.MainWindow.Handle, shell.Window, false);
                return answer;
            }
            catch (Exception ex)
            {
                HeronLog.Error("The " + question.Name + " window", ex);
                return null;
            }
        }

        private static UIElement Question(HeronSwitchQuestion question)
        {
            var picture = new Image { Width = IconSize, Height = IconSize, Margin = new Thickness(0, 0, 16, 0), VerticalAlignment = VerticalAlignment.Center };
            var icon = IconLoader.Sized(question.Icon, IconSize * 2);
            if (icon != null) picture.Source = icon;
            else picture.Visibility = Visibility.Collapsed;

            var headline = new TextBlock
            {
                Text = question.Headline,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 20,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(S.TextPrimary),
                TextWrapping = TextWrapping.Wrap,
            };
            var what = S.Body(question.What, S.TextSecondary, 13);
            what.Margin = new Thickness(0, 5, 0, 0);
            var words = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            words.Children.Add(headline);
            words.Children.Add(what);

            var row = new Grid { Margin = new Thickness(S.Gutter, 22, S.Gutter, 0) };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Grid.SetColumn(picture, 0);
            Grid.SetColumn(words, 1);
            row.Children.Add(picture);
            row.Children.Add(words);
            return row;
        }

        private static UIElement Lines(HeronSwitchQuestion question)
        {
            var list = new StackPanel { Margin = new Thickness(S.Gutter, 16, S.Gutter, 0) };
            foreach (var promise in question.Promises)
                list.Children.Add(Line("✓", promise, S.SafeColour, S.TextSecondary));
            foreach (var warning in new[] { question.Caution, question.ChangesOff })
            {
                if (string.IsNullOrEmpty(warning)) continue;
                list.Children.Add(Line("⚠", warning!, S.WarnColour, S.WarnColour));
            }
            return list;
        }

        private static UIElement Line(string symbol, string text, Color symbolColour, Color textColour)
        {
            var mark = new TextBlock
            {
                Text = symbol,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 14,
                FontWeight = FontWeights.Bold,
                Foreground = new SolidColorBrush(symbolColour),
                Width = 24,
                VerticalAlignment = VerticalAlignment.Top,
            };
            var words = S.Body(text, textColour, 13);
            var row = new Grid { Margin = new Thickness(0, 3, 0, 3) };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Grid.SetColumn(mark, 0);
            Grid.SetColumn(words, 1);
            row.Children.Add(mark);
            row.Children.Add(words);
            return row;
        }
    }
}
