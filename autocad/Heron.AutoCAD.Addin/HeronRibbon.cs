using System;
using System.Linq;
using System.Windows.Controls;
using System.Windows.Input;
using Autodesk.Windows;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Tab "Heron", panel "AI Bridge", the same as Heron for Revit (D-44): the
    /// Heron button (orange heron = connected) with Bridge Status under its
    /// arrow, and Settings, the one window that holds the Changes / Admin /
    /// Publish padlocks and Ask to Keep.
    ///
    /// AutoCAD rebuilds its ribbon when the workspace changes, which drops
    /// tabs added by code, so the tab is added again whenever it goes missing.
    /// </summary>
    internal static class HeronRibbon
    {
        public const string TabId = "HERON_AUTOCAD_TAB";

        private static RibbonSplitButton? _split;
        private static RibbonButton? _connect, _status, _free, _settings;

        public static void Init()
        {
            if (ComponentManager.Ribbon != null) Build();
            else ComponentManager.ItemInitialized += OnItemInitialized;
            AcApp.SystemVariableChanged += (s, e) =>
            {
                if (string.Equals(e.Name, "WSCURRENT", StringComparison.OrdinalIgnoreCase)) Build();
            };
        }

        private static void OnItemInitialized(object? sender, RibbonItemEventArgs e)
        {
            if (ComponentManager.Ribbon == null) return;
            ComponentManager.ItemInitialized -= OnItemInitialized;
            Build();
        }

        public static void Build()
        {
            try
            {
                var ribbon = ComponentManager.Ribbon;
                if (ribbon == null || ribbon.Tabs.Any(t => t.Id == TabId)) return;

                var tab = new RibbonTab { Title = "Heron", Id = TabId };
                var source = new RibbonPanelSource { Title = "AI Bridge" };
                tab.Panels.Add(new RibbonPanel { Source = source });

                // Hover texts are one short sentence each, as in Heron for Revit (D-45).
                _connect = Button("Heron", HeronActions.ToggleConnect, "Connect Heron to this AutoCAD. Orange heron: connected. Click again to disconnect.");
                _status = Button("Bridge Status", HeronActions.ShowStatus, "See whether Heron is connected to this AutoCAD.");
                _free = Button("Free this AutoCAD", HeronActions.FreeHold, "Let another chat use this AutoCAD now.");
                _split = new RibbonSplitButton
                {
                    Text = "Heron",
                    ShowText = true,
                    ShowImage = true,
                    Size = RibbonItemSize.Large,
                    Orientation = Orientation.Vertical,
                    IsSplit = true,
                    // The top button's picture IS the connected state; a pick
                    // from the list must never replace it.
                    IsSynchronizedWithCurrentItem = false,
                };
                _split.Items.Add(_connect);
                _split.Items.Add(_status);
                _split.Items.Add(_free);
                _split.Current = _connect;
                source.Items.Add(_split);

                _settings = Button("Settings", HeronActions.ShowSettings, "Turn Heron's switches on or off: Changes, Admin, Publish, Ask to Keep.");
                _settings.LargeImage = IconLoader.Large("Settings");
                _settings.Image = IconLoader.Small("Settings");
                source.Items.Add(_settings);

                ribbon.Tabs.Add(tab);
                Repaint();
            }
            catch (Exception ex)
            {
                HeronLog.Error("Ribbon", ex);
            }
        }

        /// <summary>Make every picture and label match the real state.</summary>
        public static void Repaint()
        {
            if (_connect == null) return;
            var running = HeronApplication.Server?.IsRunning == true;
            Paint(_connect, running, "BridgeConnected", "BridgeDisconnected", "Heron", "Heron");
            if (_split != null)
            {
                _split.Current = _connect;
                _split.LargeImage = _connect.LargeImage;
                _split.Image = _connect.Image;
            }
        }

        private static void Paint(RibbonButton button, bool on, string onIcon, string offIcon, string onText, string offText)
        {
            button.LargeImage = IconLoader.Large(on ? onIcon : offIcon);
            button.Image = IconLoader.Small(on ? onIcon : offIcon);
            button.Text = on ? onText : offText;
        }

        private static RibbonButton Button(string text, Action action, string tip) => new RibbonButton
        {
            Text = text,
            ToolTip = tip,
            ShowText = true,
            ShowImage = true,
            Size = RibbonItemSize.Large,
            Orientation = Orientation.Vertical,
            // The first label names the switch for the click log and the
            // double-click filter; it never changes, unlike the button text.
            CommandHandler = new RibbonCommand(text.Replace(" off", ""), action),
        };

        private static readonly RepeatClickFilter Clicks = new RepeatClickFilter();

        private sealed class RibbonCommand : ICommand
        {
            private readonly Action _action;
            private readonly string _name;

            public RibbonCommand(string name, Action action)
            {
                _name = name;
                _action = action;
            }

            public event EventHandler? CanExecuteChanged
            {
                add { }
                remove { }
            }

            public bool CanExecute(object? parameter) => true;

            public void Execute(object? parameter)
            {
                if (!Clicks.Accept(_name, DateTime.UtcNow))
                {
                    HeronLog.Write("ribbon click: " + _name + " (second click of a double-click, ignored)");
                    return;
                }
                HeronLog.Write("ribbon click: " + _name);
                try
                {
                    _action();
                }
                catch (Exception ex)
                {
                    HeronLog.Error("Ribbon button", ex);
                }
            }
        }
    }
}
