using System;
using System.Diagnostics;
using System.IO;
using System.Windows;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    internal enum Padlock { Changes, Publish, Admin, AskToKeep }

    /// <summary>
    /// What the ribbon buttons and the HERON commands do. Main thread only.
    /// Turning a padlock on asks first; turning it off never asks. Ask to
    /// Keep is the other way round: switching the question off is what asks.
    /// </summary>
    internal static class HeronActions
    {
        public static void ToggleConnect()
        {
            var server = HeronApplication.Server;
            if (server == null)
            {
                ShowStatus();
                return;
            }
            try
            {
                if (server.IsRunning)
                {
                    server.Stop();
                    UndoSwitch.Resume();
                    Say("Heron: disconnected. No chat can reach this AutoCAD.");
                    HeronLog.Write("Disconnected.");
                }
                else
                {
                    server.Start();
                    Say("Heron: connected. A chat can now reach this AutoCAD. Changes is " + (HeronApplication.LoadConfig().WriteEnabled ? "ON." : "off."));
                    HeronLog.Write("Connected, pipe " + server.PipeName + ".");
                }
            }
            catch (Exception ex)
            {
                HeronLog.Error("Connect", ex);
                Say("Heron could not connect: " + ex.Message + " Log: " + HeronLog.TodayPath);
            }
            finally
            {
                // The icon follows what really happened, not what was tried.
                HeronRibbon.Repaint();
            }
        }

        public static void ShowStatus()
        {
            var server = HeronApplication.Server;
            var state = HeronApplication.StartError != null || server == null
                ? HeronBridgeState.DidNotStart
                : server.IsRunning ? HeronBridgeState.Connected : HeronBridgeState.NotConnected;
            var action = HeronStatusWindow.Show(state, HeronApplication.LoadConfig(), server,
                HeronApplication.AcadVersion, HeronApplication.AddinVersion, HeronApplication.StartError);
            if (action == "connect" && server != null && !server.IsRunning) ToggleConnect();
            else if (action == "disconnect" && server != null && server.IsRunning) ToggleConnect();
            else if (action == "logs") OpenLogs();
        }

        /// <summary>"Free this AutoCAD": another chat may use it now (D-45). Changes nothing in a drawing.</summary>
        public static void FreeHold()
        {
            var hold = HeronApplication.Server?.Protocol?.Hold;
            var result = hold?.Free() ?? HoldFree.NothingHeld;
            HeronLog.Write("free this AutoCAD: " + result);
            switch (result)
            {
                case HoldFree.Freed:
                    Say("Heron: this AutoCAD is free. Another chat may use it now.");
                    break;
                case HoldFree.Busy:
                    Say("Heron is working for a chat right now. Free it again when the banner says Done.");
                    break;
                default:
                    Say("Heron: no chat is holding this AutoCAD.");
                    break;
            }
        }

        /// <summary>The Settings window: the four switches, as in Heron for Revit (D-44).</summary>
        public static void ShowSettings()
        {
            HeronLog.Write("settings window");
            HeronSettingsWindow.Show();
        }

        public static void TogglePadlock(Padlock padlock)
        {
            HeronLog.Write("toggle padlock: " + padlock);
            var config = HeronApplication.LoadConfig();
            var on = Get(config, padlock);
            var asking = padlock == Padlock.AskToKeep ? on : !on;
            if (asking && !Confirm(padlock, !on)) return;
            Set(config, padlock, !on);
            try
            {
                config.Save(HeronConfig.DefaultPath);
            }
            catch (Exception ex)
            {
                HeronLog.Error("Saving the padlocks", ex);
                Say("Heron could not save the switch: " + ex.Message);
                return;
            }
            if (padlock == Padlock.AskToKeep && on) HeronApplication.Server?.Protocol?.ClearKeepGrant();
            Say("Heron: " + Name(padlock) + " is now " + (!on ? "ON." : "off."));
            HeronRibbon.Repaint();
        }

        private static bool Confirm(Padlock padlock, bool turningOn)
        {
            var question = Question(padlock, HeronApplication.LoadConfig().WriteEnabled);
            var answer = HeronSwitchWindow.Ask(question);
            if (answer.HasValue) return answer.Value;
            // The window could not be shown: ask the same thing plainly, never assume.
            var title = turningOn ? "Heron - turn " + Name(padlock) + " on" : "Heron - turn " + Name(padlock) + " off";
            var plain = question.Headline + "\n\n" + question.What;
            return MessageBox.Show(plain, title, MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No) == MessageBoxResult.Yes;
        }

        /// <summary>The words each switch asks with - Heron for Revit's, in AutoCAD's terms.</summary>
        internal static HeronSwitchQuestion Question(Padlock padlock, bool changesOn)
        {
            string? ChangesOff(string name) => changesOn ? null : "Changes is off - " + name + " needs it on too.";
            switch (padlock)
            {
                case Padlock.Changes:
                    return new HeronSwitchQuestion
                    {
                        Name = "Changes",
                        Icon = "WriteUnlocked",
                        Headline = "Turn Changes on?",
                        What = "Heron can draw, move, change and delete objects when you ask.",
                        Promises = new[] { "Every change is one Ctrl+Z.", "Ask to Keep can show each change first." },
                    };
                case Padlock.Admin:
                    return new HeronSwitchQuestion
                    {
                        Name = "Admin",
                        Icon = "AdminUnlocked",
                        Headline = "Turn Admin on?",
                        What = "Heron can run AutoCAD commands, AutoLISP and system variables.",
                        Caution = "Ctrl+Z may not undo what a command does outside the drawing.",
                        ChangesOff = ChangesOff("Admin"),
                    };
                case Padlock.Publish:
                    return new HeronSwitchQuestion
                    {
                        Name = "Publish",
                        Icon = "PublishUnlocked",
                        Headline = "Turn Publish on?",
                        What = "Heron can save, export and plot drawings.",
                        Caution = "Ctrl+Z can't undo a save, an export or a plot.",
                        ChangesOff = ChangesOff("Publish"),
                    };
                default:
                    return new HeronSwitchQuestion
                    {
                        Name = "Ask to Keep",
                        Icon = "KeepNotAsking",
                        Headline = "Stop asking Keep or Discard?",
                        What = "Changes from a chat are kept at once.",
                        Promises = new[] { "Ctrl+Z still undoes each change." },
                        TurnOn = "Stop asking",
                        Decline = "Keep asking",
                    };
            }
        }

        private static string Name(Padlock padlock) => padlock == Padlock.AskToKeep ? "Ask to Keep" : padlock.ToString();

        private static bool Get(HeronConfig c, Padlock p) => p switch
        {
            Padlock.Changes => c.WriteEnabled,
            Padlock.Publish => c.PublishEnabled,
            Padlock.Admin => c.AdminEnabled,
            _ => c.AskBeforeKeeping,
        };

        private static void Set(HeronConfig c, Padlock p, bool value)
        {
            switch (p)
            {
                case Padlock.Changes: c.WriteEnabled = value; break;
                case Padlock.Publish: c.PublishEnabled = value; break;
                case Padlock.Admin: c.AdminEnabled = value; break;
                default: c.AskBeforeKeeping = value; break;
            }
        }

        private static void OpenLogs()
        {
            try
            {
                Directory.CreateDirectory(HeronLog.Folder);
                Process.Start(new ProcessStartInfo("explorer.exe", "\"" + HeronLog.Folder + "\"") { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                HeronLog.Error("Open log folder", ex);
            }
        }

        public static void Say(string line) =>
            AcApp.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\n" + line + "\n");
    }
}
