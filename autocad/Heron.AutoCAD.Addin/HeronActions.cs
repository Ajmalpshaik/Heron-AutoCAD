using System;
using System.Diagnostics;
using System.IO;
using System.Windows;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// What the ribbon buttons and the HERON commands do. Main thread only.
    /// Turning a padlock on asks first; turning it off never asks. Ask to
    /// Keep is the other way round: switching the question off is what asks.
    /// The padlocks live in this AutoCAD's memory (D-59): these clicks are the
    /// only way to move one, and a Windows policy can hold one off (D-60).
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
            // A pick from the Heron menu makes it the split button's current
            // item; put the heron back on top.
            HeronRibbon.Repaint();
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
            HeronRibbon.Repaint();
        }

        /// <summary>
        /// The emergency stop (D-51): every chat is refused until the modeller
        /// types HERONSTOP again. A job already running stops at its next
        /// request to the plug-in; what AutoCAD already has queued finishes,
        /// so Esc is pressed for it too.
        /// </summary>
        // Two Ctrl+C characters: AutoCAD's Esc, typed.
        private const string EscEsc = "\x03\x03";

        public static void ToggleStop()
        {
            var protocol = HeronApplication.Server?.Protocol;
            if (protocol == null)
            {
                Say("Heron is not connected, so no chat can reach this AutoCAD. Nothing to stop.");
                return;
            }
            if (protocol.Stopped)
            {
                protocol.Resume();
                HeronLog.Write("stop lifted");
                Say("Heron: the stop is lifted. A chat may work in this AutoCAD again.");
            }
            else
            {
                protocol.Stop();
                HeronLog.Write("STOPPED by the modeller");
                try
                {
                    // Cancel whatever command is running now, as Esc does.
                    AcApp.DocumentManager.MdiActiveDocument?.SendStringToExecute(EscEsc, true, false, false);
                }
                catch (Exception ex)
                {
                    HeronLog.Error("Stop: cancel the running command", ex);
                }
                Say("Heron: STOPPED. No chat can do anything in this AutoCAD until you type HERONSTOP again. "
                    + "Look at the drawing: what was done before the stop is still there (Ctrl+Z undoes it).");
            }
            HeronRibbon.Repaint();
        }

        /// <summary>The Settings window: the five switches, as in Heron for Revit (D-44) plus the erase question (D-50).</summary>
        public static void ShowSettings()
        {
            HeronLog.Write("settings window");
            HeronSettingsWindow.Show();
        }

        public static void TogglePadlock(Padlock padlock)
        {
            HeronLog.Write("toggle padlock: " + padlock);
            var padlocks = HeronApplication.Padlocks;
            var on = padlocks.IsOn(padlock);
            if (!on && padlocks.Holds().Holds(padlock))
            {
                SayHeld(padlock);
                return;
            }
            // A padlock asks on the way on; a question asks on the way off.
            var asking = padlock == Padlock.AskToKeep || padlock == Padlock.EraseQuestion ? on : !on;
            if (asking && !Confirm(padlock, !on)) return;
            if (on) padlocks.TurnOff(padlock);
            else if (!padlocks.TurnOn(padlock))
            {
                // A policy arrived while the question was open.
                SayHeld(padlock);
                HeronRibbon.Repaint();
                return;
            }
            if (padlock == Padlock.AskToKeep && on) HeronApplication.Server?.Protocol?.ClearKeepGrant();
            Say("Heron: " + Name(padlock) + " is now " + (!on ? "ON." : "off."));
            HeronRibbon.Repaint();
        }

        /// <summary>The words for a padlock a Windows policy holds off (D-60).</summary>
        internal const string HeldLine = "A Windows policy on this PC holds this off.";

        private static void SayHeld(Padlock padlock)
        {
            HeronLog.Write("padlock held by policy: " + padlock);
            Say("Heron: " + Name(padlock) + " stays off. " + HeldLine + " Only the PC's administrator can lift it.");
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
                case Padlock.EraseQuestion:
                    return new HeronSwitchQuestion
                    {
                        Name = EraseQuestionName,
                        Icon = "KeepNotAsking",
                        Headline = "Stop asking before keeping erased objects?",
                        What = "Whatever a Heron job erases stays erased at once: objects, and layers, blocks or styles a purge or delete removes.",
                        Promises = new[]
                        {
                            "Ctrl+Z still brings back what a job erased.",
                            "The chat's answer still says how many were erased.",
                            "It asks again the next time AutoCAD starts.",
                        },
                        TurnOn = "Stop asking",
                        Decline = "Keep asking",
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

        /// <summary>The erase question's name in Settings and on the command line (D-50).</summary>
        internal const string EraseQuestionName = "Ask before keeping erased objects";

        private static string Name(Padlock padlock) => padlock switch
        {
            Padlock.AskToKeep => "Ask to Keep",
            Padlock.EraseQuestion => EraseQuestionName,
            _ => padlock.ToString(),
        };

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
