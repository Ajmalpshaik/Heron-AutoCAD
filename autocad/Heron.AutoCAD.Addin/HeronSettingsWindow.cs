using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Heron's Settings window (D-44), the same as Heron for Revit's: the four
    /// switches left the ribbon and live here. Per switch: its padlock picture,
    /// its name, one short line, and the state as a button - ON lit (Error for a
    /// padlock, Success for Ask to Keep), OFF quiet.
    ///
    /// It decides nothing. Pressing a state runs the switch's own toggle
    /// (HeronActions.TogglePadlock): the same question on the way to the risky
    /// side, the same file. Then every row is drawn again from the settings read
    /// back, because one answer can change another switch's line.
    /// </summary>
    internal static class HeronSettingsWindow
    {
        public const string Title = "Heron - Settings";
        public const string Note = "Publish and Admin work only while Changes is on.";

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
            var window = HeronUi.NewWindow(Title, 470);
            var rows = new StackPanel();
            var problem = HeronUi.Text("", 12, null, HeronUi.Error);
            problem.Visibility = Visibility.Collapsed;

            void Redraw()
            {
                rows.Children.Clear();
                var config = HeronApplication.LoadConfig();
                for (var i = 0; i < Settings.Length; i++)
                {
                    if (i > 0) rows.Children.Add(new Border { Height = 1, Background = HeronUi.Line });
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

            var body = new StackPanel { Margin = new Thickness(20) };
            body.Children.Add(HeronUi.Text("Settings", 18, FontWeights.SemiBold));
            body.Children.Add(new Border
            {
                BorderBrush = HeronUi.Line,
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(8),
                Padding = new Thickness(12, 2, 12, 2),
                Margin = new Thickness(0, 4, 0, 8),
                Child = rows,
            });
            body.Children.Add(problem);
            body.Children.Add(HeronUi.Text(Note, 12, null, HeronUi.Muted));
            var close = HeronUi.Button("Close", isDefault: true, isCancel: true);
            close.Click += (s, e) => window.Close();
            body.Children.Add(HeronUi.Buttons(close));
            window.Content = body;
            AcApp.ShowModalWindow(AcApp.MainWindow.Handle, window, false);
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

            var words = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            var name = HeronUi.Text(setting.Name, 14, FontWeights.SemiBold);
            name.Margin = new Thickness(0);
            words.Children.Add(name);
            var line = HeronUi.Text(Line(setting.Padlock, on), 12, null, HeronUi.Muted);
            line.Margin = new Thickness(0, 2, 0, 0);
            words.Children.Add(line);

            // THE STATE IS THE BUTTON: lit when on, quiet when off.
            var state = new Button
            {
                Content = new TextBlock { Text = on ? "ON" : "OFF", FontWeight = FontWeights.Bold, FontSize = 12, Foreground = on ? HeronUi.Ink : HeronUi.Muted },
                Width = 64,
                Padding = new Thickness(0, 5, 0, 5),
                Margin = new Thickness(12, 0, 0, 0),
                VerticalAlignment = VerticalAlignment.Center,
                Background = on ? (setting.OnIsSafe ? HeronUi.Success : HeronUi.Error) : HeronUi.OffFill,
                BorderBrush = HeronUi.Line,
                ToolTip = "Click to turn " + setting.Name + (on ? " off" : " on"),
            };
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

        /// <summary>The one short line under a switch's name.</summary>
        private static string Line(Padlock padlock, bool on)
        {
            switch (padlock)
            {
                case Padlock.Changes:
                    return on ? "A chat may draw, move, change and delete. Each change is one undo step." : "Heron can read and look, but not change anything.";
                case Padlock.Publish:
                    return on ? "Heron may save, export and plot." : "Heron may not save, export or plot.";
                case Padlock.Admin:
                    return on ? "Heron may run commands, AutoLISP and system variables." : "No commands, AutoLISP or system-variable changes.";
                default:
                    if (on && HeronApplication.Server?.Protocol?.KeepGrantActive == true)
                        return "Keeping the rest of this job without asking.";
                    return on ? "After each change Heron asks: keep it, or discard it." : "Changes are kept at once, still as one undo step.";
            }
        }
    }
}
