using System;
using System.Collections.Generic;
using System.Text;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Shapes;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using S = Heron.AutoCAD.Addin.HeronWindowStyle;

namespace Heron.AutoCAD.Addin
{
    internal enum HeronBridgeState { DidNotStart, NotConnected, Connected }

    /// <summary>
    /// Bridge Status, drawn as Heron for Revit's (D-45): a lamp and the state in
    /// one word, what that means, the Changes card, the session's details in an
    /// inset, and the footer - Copy details on the left, the state's two buttons
    /// on the right. Enter never disconnects: Close is the default when connected.
    /// </summary>
    internal static class HeronStatusWindow
    {
        public const string Title = "Bridge Status";
        private const double CardWidth = 480;

        /// <summary>Main thread only. Returns connect | disconnect | logs | close.</summary>
        public static string Show(HeronBridgeState state, HeronConfig config, BridgeServer? server, string acadVersion, string addinVersion, string? error)
        {
            var action = "close";
            var accent = state == HeronBridgeState.Connected ? S.AccentColour
                : state == HeronBridgeState.DidNotStart ? S.DangerColour : S.QuietColour;

            S.Shell? shell = null;
            void Finish(string what)
            {
                action = what;
                shell!.Close();
            }

            // THE STATE: a lamp, one word, and what it means.
            var lamp = new Ellipse
            {
                Width = 11,
                Height = 11,
                Fill = new SolidColorBrush(accent),
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(0, 0, 11, 0),
                Effect = new DropShadowEffect { BlurRadius = 16, ShadowDepth = 0, Opacity = state == HeronBridgeState.NotConnected ? 0.0 : 0.9, Color = accent },
            };
            string headline, explain;
            switch (state)
            {
                case HeronBridgeState.Connected:
                    headline = "Connected";
                    explain = "A chat can reach this AutoCAD session. Nothing in your drawings changes unless Changes is on.";
                    break;
                case HeronBridgeState.NotConnected:
                    headline = "Not connected";
                    explain = "This AutoCAD is private. No chat can read your drawings or change them until you connect.";
                    break;
                default:
                    headline = "Heron did not start";
                    explain = "The plug-in loaded but could not start, so there is nothing to connect. " + (error ?? "The log that says why is in the folder below.");
                    break;
            }
            var title = new TextBlock
            {
                Text = headline,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 21,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(S.TextPrimary),
                VerticalAlignment = VerticalAlignment.Center,
            };
            var line = new StackPanel { Orientation = Orientation.Horizontal };
            line.Children.Add(lamp);
            line.Children.Add(title);
            var words = S.Body(explain, S.TextSecondary, 13);
            words.Margin = new Thickness(0, 8, 0, 0);
            var top = new StackPanel { Margin = new Thickness(S.Gutter, 20, S.Gutter, 0) };
            top.Children.Add(line);
            top.Children.Add(words);

            var body = new StackPanel();
            body.Children.Add(top);
            if (state != HeronBridgeState.DidNotStart) body.Children.Add(ChangesCard(config.WriteEnabled));

            // THIS SESSION.
            var rows = new List<KeyValuePair<string, string>>();
            if (state == HeronBridgeState.Connected && server != null) rows.Add(new KeyValuePair<string, string>("Pipe", server.PipeName));
            rows.Add(new KeyValuePair<string, string>("Process", System.Diagnostics.Process.GetCurrentProcess().Id.ToString()));
            rows.Add(new KeyValuePair<string, string>("AutoCAD", acadVersion));
            rows.Add(new KeyValuePair<string, string>("Add-in", addinVersion));
            rows.Add(new KeyValuePair<string, string>("Protocol", BridgeProtocol.Version.ToString()));
            var list = new StackPanel();
            foreach (var row in rows)
                if (!string.IsNullOrEmpty(row.Value)) list.Children.Add(DetailRow(row.Key, row.Value));
            var details = new StackPanel { Margin = new Thickness(S.Gutter, 4, S.Gutter, 0) };
            details.Children.Add(S.Caption("THIS SESSION"));
            details.Children.Add(new Border
            {
                Padding = new Thickness(14, 10, 14, 11),
                CornerRadius = new CornerRadius(10),
                Background = new SolidColorBrush(S.InsetColour),
                Margin = new Thickness(0, 7, 0, 0),
                Child = list,
            });
            if (state == HeronBridgeState.Connected && server != null)
            {
                details.Children.Add(S.Caption("ANNOUNCED IN"));
                details.Children.Add(S.PathLine(server.AddressPath));
            }
            if (state == HeronBridgeState.DidNotStart)
            {
                details.Children.Add(S.Caption("LOGS"));
                details.Children.Add(S.PathLine(HeronLog.Folder));
            }
            body.Children.Add(details);

            // THE FOOTER: Copy details and a note on the left, the state's buttons on the right.
            var note = new TextBlock
            {
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 12,
                Foreground = new SolidColorBrush(S.TextMuted),
                VerticalAlignment = VerticalAlignment.Center,
                TextTrimming = TextTrimming.CharacterEllipsis,
                Margin = new Thickness(8, 0, 0, 0),
            };
            var copy = S.FlatButton("Copy details", 12.5);
            copy.Click += (s, e) =>
            {
                var text = new StringBuilder("Heron for AutoCAD - " + headline + Environment.NewLine);
                foreach (var row in rows) text.Append(row.Key).Append(": ").Append(row.Value).Append(Environment.NewLine);
                if (state == HeronBridgeState.Connected && server != null) text.Append("Announced in: ").Append(server.AddressPath).Append(Environment.NewLine);
                if (!string.IsNullOrEmpty(error)) text.Append("Error: ").Append(error).Append(Environment.NewLine);
                try
                {
                    Clipboard.SetText(text.ToString());
                    note.Text = "Copied.";
                }
                catch (Exception ex)
                {
                    note.Text = "Could not copy: " + ex.Message;
                }
            };

            Button primary, secondary;
            switch (state)
            {
                case HeronBridgeState.Connected:
                    primary = S.PrimaryButton("Close", S.AccentColour);
                    primary.Click += (s, e) => Finish("close");
                    secondary = S.GhostButton("Disconnect");
                    secondary.Click += (s, e) => Finish("disconnect");
                    break;
                case HeronBridgeState.NotConnected:
                    primary = S.PrimaryButton("Connect this session", S.AccentColour);
                    primary.Click += (s, e) => Finish("connect");
                    secondary = S.GhostButton("Close");
                    secondary.Click += (s, e) => Finish("close");
                    break;
                default:
                    primary = S.PrimaryButton("Close", S.AccentColour);
                    primary.Click += (s, e) => Finish("close");
                    secondary = S.GhostButton("Open log folder");
                    secondary.Click += (s, e) => Finish("logs");
                    break;
            }
            // As in Revit: Enter presses the lit button - Close when connected, so
            // Enter never disconnects; Connect when not.
            primary.IsDefault = true;
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
            buttons.Children.Add(secondary);
            buttons.Children.Add(primary);
            var left = new DockPanel { LastChildFill = true, VerticalAlignment = VerticalAlignment.Center };
            DockPanel.SetDock(copy, Dock.Left);
            left.Children.Add(copy);
            left.Children.Add(note);
            var footer = new Grid();
            footer.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            footer.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            Grid.SetColumn(left, 0);
            Grid.SetColumn(buttons, 1);
            footer.Children.Add(left);
            footer.Children.Add(buttons);
            body.Children.Add(S.Footer(footer));

            shell = S.Build(Title, CardWidth, body, accent, () => Finish("close"));
            AcApp.ShowModalWindow(AcApp.MainWindow.Handle, shell.Window, false);
            return action;
        }

        /// <summary>The Changes card: ON in Warning, OFF quiet, as in Revit.</summary>
        private static UIElement ChangesCard(bool on)
        {
            var colour = on ? S.WarnColour : S.QuietColour;
            var label = new TextBlock
            {
                Text = "Changes",
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 13,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(S.TextPrimary),
                VerticalAlignment = VerticalAlignment.Center,
            };
            var chip = new Border
            {
                CornerRadius = new CornerRadius(5),
                BorderThickness = new Thickness(1),
                Padding = new Thickness(9, 2, 9, 3),
                HorizontalAlignment = HorizontalAlignment.Right,
                VerticalAlignment = VerticalAlignment.Center,
                BorderBrush = new SolidColorBrush(HeronBrand.At(colour, 0x8C)),
                Background = new SolidColorBrush(HeronBrand.At(colour, on ? (byte)0x22 : (byte)0x14)),
                Child = new TextBlock
                {
                    Text = on ? "ON" : "OFF",
                    FontFamily = new FontFamily(S.BodyFont),
                    FontSize = 11,
                    FontWeight = FontWeights.Bold,
                    Foreground = new SolidColorBrush(colour),
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center,
                },
            };
            var head = new Grid();
            head.Children.Add(label);
            head.Children.Add(chip);
            var explain = S.Body(on
                    ? "Heron may draw, move, change and delete when you ask it to. Every change is one Ctrl+Z, and Ask to Keep in Settings shows each one first when it is on."
                    : "Heron can read this drawing and nothing else. Changes in Settings turns it on.",
                S.TextMuted, 12);
            explain.Margin = new Thickness(0, 5, 0, 0);
            var text = new StackPanel();
            text.Children.Add(head);
            text.Children.Add(explain);
            return new Border
            {
                Margin = new Thickness(S.Gutter, 17, S.Gutter, 0),
                Padding = new Thickness(14, 11, 14, 12),
                CornerRadius = new CornerRadius(10),
                Background = new SolidColorBrush(S.InsetColour),
                BorderThickness = new Thickness(1),
                BorderBrush = new SolidColorBrush(on ? HeronBrand.At(colour, 0x59) : HeronBrand.At(HeronBrand.White, 0x1E)),
                Child = text,
            };
        }

        private static UIElement DetailRow(string label, string value)
        {
            var name = new TextBlock
            {
                Text = label,
                Width = 80,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 12.5,
                Foreground = new SolidColorBrush(S.TextSecondary),
                VerticalAlignment = VerticalAlignment.Center,
            };
            var read = new TextBlock
            {
                Text = value,
                FontFamily = new FontFamily(S.MonoFont),
                FontSize = 12.5,
                Foreground = new SolidColorBrush(S.TextPrimary),
                VerticalAlignment = VerticalAlignment.Center,
                TextTrimming = TextTrimming.CharacterEllipsis,
            };
            var row = new Grid { Margin = new Thickness(0, 4, 0, 4) };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            Grid.SetColumn(name, 0);
            Grid.SetColumn(read, 1);
            row.Children.Add(name);
            row.Children.Add(read);
            return row;
        }
    }
}
