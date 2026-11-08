using System.Windows;
using System.Windows.Controls;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    internal enum HeronBridgeState { DidNotStart, NotConnected, Connected }

    /// <summary>
    /// Bridge Status: what Heron can do in this AutoCAD right now. Close is
    /// always the default button, so pressing Enter can never disconnect.
    /// </summary>
    internal static class HeronStatusWindow
    {
        public const string Title = "Heron - Bridge Status";

        /// <summary>Main thread only. Returns connect | disconnect | logs | close.</summary>
        public static string Show(HeronBridgeState state, HeronConfig config, BridgeServer? server, string acadVersion, string addinVersion, string? error)
        {
            var action = "close";
            var window = HeronUi.NewWindow(Title, 480);
            var body = new StackPanel { Margin = new Thickness(20) };

            switch (state)
            {
                case HeronBridgeState.Connected:
                    body.Children.Add(HeronUi.Text("Connected", 18, FontWeights.SemiBold));
                    body.Children.Add(HeronUi.Text("A chat can reach this AutoCAD session. Nothing in your drawings changes unless Changes is on."));
                    break;
                case HeronBridgeState.NotConnected:
                    body.Children.Add(HeronUi.Text("Not connected", 18, FontWeights.SemiBold));
                    body.Children.Add(HeronUi.Text("This AutoCAD is private. No chat can read your drawings or change them until you connect."));
                    break;
                default:
                    body.Children.Add(HeronUi.Text("Heron did not start", 18, FontWeights.SemiBold));
                    body.Children.Add(HeronUi.Text(error ?? "See the log folder for what happened."));
                    break;
            }

            body.Children.Add(HeronUi.Card("Changes", config.WriteEnabled,
                "A connected chat may draw, move, change and delete objects. Each change is one undo step.",
                "Heron can read and look, but not change anything."));
            body.Children.Add(HeronUi.Card("Publish", config.PublishEnabled,
                "Heron may save, export and plot (needs Changes too).",
                "Heron may not save, export or plot."));
            body.Children.Add(HeronUi.Card("Admin", config.AdminEnabled,
                "Heron may run AutoCAD commands, AutoLISP and system variables (needs Changes too).",
                "No commands, AutoLISP or system-variable changes."));
            body.Children.Add(HeronUi.Card("Ask to Keep", config.AskBeforeKeeping,
                "After each change Heron asks: keep it, or discard it.",
                "Changes are kept at once, still as one undo step.", onIsSafe: true));

            var details = new StackPanel { Margin = new Thickness(0, 8, 0, 0) };
            if (state == HeronBridgeState.Connected && server != null)
            {
                details.Children.Add(Row("Pipe", server.PipeName));
                details.Children.Add(Row("Address file", server.AddressPath));
            }
            details.Children.Add(Row("Process", System.Diagnostics.Process.GetCurrentProcess().Id.ToString()));
            details.Children.Add(Row("AutoCAD", acadVersion));
            details.Children.Add(Row("Add-in", addinVersion));
            details.Children.Add(Row("Protocol", BridgeProtocol.Version.ToString()));
            body.Children.Add(details);

            var close = HeronUi.Button("Close", isDefault: true, isCancel: true);
            close.Click += (s, e) => window.Close();
            switch (state)
            {
                case HeronBridgeState.Connected:
                    var disconnect = HeronUi.Button("Disconnect");
                    disconnect.Click += (s, e) => { action = "disconnect"; window.Close(); };
                    body.Children.Add(HeronUi.Buttons(close, disconnect));
                    break;
                case HeronBridgeState.NotConnected:
                    var connect = HeronUi.Button("Connect this session");
                    connect.Click += (s, e) => { action = "connect"; window.Close(); };
                    body.Children.Add(HeronUi.Buttons(connect, close));
                    break;
                default:
                    var logs = HeronUi.Button("Open log folder");
                    logs.Click += (s, e) => { action = "logs"; window.Close(); };
                    body.Children.Add(HeronUi.Buttons(close, logs));
                    break;
            }

            window.Content = body;
            AcApp.ShowModalWindow(AcApp.MainWindow.Handle, window, false);
            return action;
        }

        private static TextBlock Row(string name, string value)
        {
            var text = HeronUi.Text(name + ":  " + value, 11, null, HeronUi.Muted);
            text.Margin = new Thickness(0, 0, 0, 2);
            return text;
        }
    }
}
