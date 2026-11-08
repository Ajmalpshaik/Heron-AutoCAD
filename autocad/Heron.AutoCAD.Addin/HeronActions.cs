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
            string question;
            switch (padlock)
            {
                case Padlock.Changes:
                    question = "Turn Changes on?\n\nWhile Changes is on, a connected chat may draw, move, change and delete objects in your open drawings. Each change is one undo step, and the banner shows whenever Heron is working.";
                    break;
                case Padlock.Publish:
                    question = "Turn Publish on?\n\nA connected chat may then save drawings and export or plot files (Changes must be on too).";
                    break;
                case Padlock.Admin:
                    question = "Turn Admin on?\n\nA connected chat may then run any AutoCAD command, AutoLISP and system-variable change (Changes must be on too). Turn it on only for a job that needs it.";
                    break;
                default:
                    question = "Turn Ask to Keep off?\n\nHeron will keep each change at once, without asking. Each change is still one undo step.";
                    break;
            }
            var title = turningOn ? "Heron - turn " + Name(padlock) + " on" : "Heron - turn " + Name(padlock) + " off";
            return MessageBox.Show(question, title, MessageBoxButton.YesNo, MessageBoxImage.Question, MessageBoxResult.No) == MessageBoxResult.Yes;
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
