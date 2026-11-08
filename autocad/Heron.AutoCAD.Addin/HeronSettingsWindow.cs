using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using S = Heron.AutoCAD.Addin.HeronWindowStyle;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Heron's Settings window (D-44), drawn as Heron for Revit's (D-45): the
    /// four switches, each with its padlock picture, its name, one short line
    /// and the state as its own button - ON lit (Error for a padlock, Success
    /// for Ask to Keep), OFF quiet.
    ///
    /// It decides nothing. Pressing a state runs the switch's own toggle
    /// (HeronActions.TogglePadlock): the same question on the way to the risky
    /// side, the same file. Then every row is drawn again from the settings
    /// read back, because one answer can change another switch's line.
    /// </summary>
    internal static class HeronSettingsWindow
    {
        public const string Title = "Settings";
        public const string Note = "Admin and Publish work only while Changes is on.";

        private const double CardWidth = 470;

        private sealed class Setting
        {
            public Setting(Padlock padlock, string name, string onIcon, string offIcon, bool onIsSafe)
            {
                Padlock = padlock;
                Name = name;
                OnIcon = onIcon;
                OffIcon = offIcon;
                OnIsSafe = onIsSafe;
            }

            public Padlock Padlock { get; }
            public string Name { get; }
            public string OnIcon { get; }
            public string OffIcon { get; }
            public bool OnIsSafe { get; }
        }

        // The same order as Heron for Revit's Settings window.
        private static readonly Setting[] Settings =
        {
            new Setting(Padlock.Changes, "Changes", "WriteUnlocked", "WriteLocked", false),
            new Setting(Padlock.Admin, "Admin", "AdminUnlocked", "AdminLocked", false),
            new Setting(Padlock.Publish, "Publish", "PublishUnlocked", "PublishLocked", false),
            new Setting(Padlock.AskToKeep, "Ask to Keep", "KeepAsking", "KeepNotAsking", true),
        };

        /// <summary>Main thread only. Shows the window until it is closed.</summary>
        public static void Show()
        {
            var rows = new StackPanel();
            var problem = S.Body("", S.DangerColour, 12);
            problem.Margin = new Thickness(S.Gutter + 2, 10, S.Gutter, 0);
            problem.Visibility = Visibility.Collapsed;

            void Redraw()
            {
                rows.Children.Clear();
                var config = HeronApplication.LoadConfig();
                for (var i = 0; i < Settings.Length; i++)
                {
                    if (i > 0) rows.Children.Add(new Border { Height = 1, Background = new SolidColorBrush(HeronBrand.At(HeronBrand.Mist, 0x14)) });
                    rows.Children.Add(Row(Settings[i], config, Press));
                }
            }

            void Press(Setting setting)
            {
                try
                {
                    HeronActions.TogglePadlock(setting.Padlock);
                    problem.Visibility = Visibility.Collapsed;
                }
                catch (Exception ex)
                {
                    HeronLog.Error("Settings " + setting.Name, ex);
                    problem.Text = "Could not change " + setting.Name + ", so it is as it was. " + ex.Message;
                    problem.Visibility = Visibility.Visible;
                }
                Redraw();
            }

            Redraw();

            var card = new Border
            {
                Margin = new Thickness(S.Gutter, 18, S.Gutter, 0),
                Padding = new Thickness(14, 6, 14, 6),
                CornerRadius = new CornerRadius(10),
                Background = new SolidColorBrush(S.InsetColour),
                BorderThickness = new Thickness(1),
                BorderBrush = new SolidColorBrush(HeronBrand.At(HeronBrand.Mist, 0x1E)),
                Child = rows,
            };
            var note = S.Body(Note, S.TextMuted, 12);
            note.Margin = new Thickness(S.Gutter + 2, 12, S.Gutter, 0);

            S.Shell? shell = null;
            var close = S.GhostButton("Close");
            close.IsCancel = true;
            close.Click += (s, e) => shell!.Close();
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            buttons.Children.Add(close);

            var body = new StackPanel();
            body.Children.Add(card);
            body.Children.Add(problem);
            body.Children.Add(note);
            body.Children.Add(S.Footer(buttons));
            shell = S.Build(Title, CardWidth, body, S.AccentColour, () => shell!.Close());
            AcApp.ShowModalWindow(AcApp.MainWindow.Handle, shell.Window, false);
        }

        private static UIElement Row(Setting setting, HeronConfig config, Action<Setting> press)
        {
            var on = setting.Padlock switch
            {
                Padlock.Changes => config.WriteEnabled,
                Padlock.Publish => config.PublishEnabled,
                Padlock.Admin => config.AdminEnabled,
                _ => config.AskBeforeKeeping,
            };

            var picture = new Image { Width = 32, Height = 32, Margin = new Thickness(0, 0, 12, 0), VerticalAlignment = VerticalAlignment.Center };
            var icon = IconLoader.Large(on ? setting.OnIcon : setting.OffIcon);
            if (icon != null) picture.Source = icon;

            var name = new TextBlock
            {
                Text = setting.Name,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 14,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(S.TextPrimary),
            };
            var line = S.Body(Line(setting.Padlock, on), S.TextSecondary, 12);
            line.Margin = new Thickness(0, 2, 0, 0);
            var words = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            words.Children.Add(name);
            words.Children.Add(line);

            // THE STATE IS THE BUTTON. Lit when on - Error for a padlock,
            // Success for Ask to Keep - and quiet when off.
            var state = on ? S.PrimaryButton("ON", setting.OnIsSafe ? S.SafeColour : S.DangerColour) : S.GhostButton("OFF");
            state.Width = 64;
            state.Margin = new Thickness(12, 0, 0, 0);
            state.VerticalAlignment = VerticalAlignment.Center;
            state.ToolTip = "Click to turn " + setting.Name + (on ? " off" : " on");
            state.Click += (s, e) => press(setting);

            var row = new Grid { Margin = new Thickness(0, 10, 0, 10) };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(picture, 0);
            Grid.SetColumn(words, 1);
            Grid.SetColumn(state, 2);
            row.Children.Add(picture);
            row.Children.Add(words);
            row.Children.Add(state);
            return row;
        }

        /// <summary>The one short line under a switch's name: what ON lets happen.</summary>
        private static string Line(Padlock padlock, bool on)
        {
            switch (padlock)
            {
                case Padlock.Changes:
                    return "Heron can draw, move, change and delete when you ask.";
                case Padlock.Admin:
                    return "Heron can run commands, AutoLISP and system variables.";
                case Padlock.Publish:
                    return "Heron can save, export and plot.";
                default:
                    if (on && HeronApplication.Server?.Protocol?.KeepGrantActive == true)
                        return "Keeping the rest of this job without asking.";
                    return "Shows each change first: Keep it or Discard it.";
            }
        }
    }
}
