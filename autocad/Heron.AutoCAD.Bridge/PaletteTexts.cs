namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Every sentence the Heron palette says to the modeller (D-68). Kept in
    /// one place so the docs and the tests quote the same words.
    /// </summary>
    public static class PaletteTexts
    {
        public const string Gone = "That job is no longer in the list.";

        public const string Busy = "Heron is working on a job right now. Wait until it is done, then try again.";

        public static string OtherDrawing(string job, string active) =>
            "This job was in " + Name(job) + ", and the drawing in front is " + Name(active) + ". Switch to " + Name(job) + " first.";

        public const string ShowUndone = "This job was undone, so there is nothing of it to show.";

        public const string ShowDiscarded = "This job was discarded, so there is nothing of it to show.";

        public const string ShowDryRun = "This was a dry run: Heron took it back at once, so there is nothing of it to show.";

        public const string ShowOnlyErased = "This job only erased objects, so there is nothing of it left to show.";

        public const string ShowNothing = "This job made or changed nothing Heron can show.";

        public const string AlreadyUndone = "This job was already undone from this palette.";

        public const string UndoOfUndo = "This job was itself an undo. Use Ctrl+Z if you want it back.";

        public const string UndoRawCommand =
            "This job ran an AutoCAD command, AutoLISP or a save, which Heron cannot undo exactly. Use Ctrl+Z yourself if you are sure.";

        public const string UndoDiscarded = "This job was discarded, so nothing of it is left to undo.";

        public static string UndoNotClean(string outcome) =>
            "This job did not finish cleanly (" + (string.IsNullOrEmpty(outcome) ? "failed" : outcome) +
            "), so Heron cannot say what one undo would take back. Look at the drawing and use Ctrl+Z yourself.";

        public const string UndoNothing = "This job changed nothing, so there is nothing to undo.";

        public static string UndoNotNewest(string newer) =>
            "Heron did more after this job (" + newer + "). Only Heron's newest change can be undone here, so your own work is never taken with it. Use Ctrl+Z for older ones.";

        public const string UndoUnknown =
            "Heron cannot tell whether the drawing changed after this job. Use Ctrl+Z yourself if you are sure.";

        public const string UndoChangedSince =
            "The drawing changed after this job (your own work, or another program), so undoing it could take your work with it. Use Ctrl+Z yourself if you want it gone.";

        public const string UndoOff =
            "UNDO is off in this drawing, or keeps only one step (UNDOCTL), so Heron cannot undo this job exactly. Turn UNDO on (UNDO > All) for next time.";

        public const string UndoViewsSince =
            "Heron zoomed or showed objects after this job, and Heron put no UNDO mark down before it, so one step back would undo the zoom instead. Use Ctrl+Z until it is gone.";

        public const string UndoAfterRestore =
            "Heron brought objects this job erased back after it, and put no UNDO mark down before it, so one step back would erase them again instead of undoing the job. Use Ctrl+Z if you want it gone.";

        public static string Undone(string summary) => "Undone: " + summary + ".";

        public static string UndoLeft(int left) =>
            "The undo ran, but " + left + " object(s) this job made are still there. Look at the drawing before doing anything else.";

        public const string UndoDidNotRun = "The undo did not run (it was cancelled or AutoCAD refused it). Nothing was changed.";

        public const string UndoDidNotStart =
            "AutoCAD did not start the undo within 30 s (a command or a box may be open). Press Esc in AutoCAD and look at the drawing: if the undo still runs later, the job is gone.";

        public const string UndoAlreadyWaiting = "An Undo from this palette is already waiting for AutoCAD. Wait until it is done.";

        /// <summary>Said to a chat whose job would begin while the palette's Undo waits (#138).</summary>
        public const string JobWaitsForUndo =
            "The modeller is undoing a Heron change from the Heron palette right now. Try again in a moment. " + Texts.NothingSent;

        public const string NoDrawing = "No drawing is open.";

        // ----- Drawing events in the Activity list (#48) -----

        /// <summary>Beside a job whose drawing is not the one in front.</summary>
        public const string NotInFront = "not in front";

        /// <summary>The line above the list: which drawing is in front now.</summary>
        public static string InFront(string active) =>
            string.IsNullOrEmpty(active) ? "No drawing is in front." : "In front: " + DrawingNames.Short(active);

        /// <summary>One drawing event, in plain words.</summary>
        public static string DrawingRow(DrawingEvent e)
        {
            var name = DrawingNames.Short(e.Drawing);
            switch (e.Kind)
            {
                case DrawingEvents.Opened: return name + " opened";
                case DrawingEvents.Activated: return name + " came to the front";
                case DrawingEvents.Saved:
                    return e.Was.Length > 0 ? DrawingNames.Short(e.Was) + " saved as " + name : name + " saved";
                case DrawingEvents.Closed: return name + " closed";
                default: return name + " " + e.Kind;
            }
        }

        // ----- Saved commands -----

        public const string NoCommands =
            "No saved commands yet. In a chat, say \"save that as 'pipe support'\" after a job that worked; it shows here at once.";

        public const string NoMatch = "No saved command matches that search.";

        public static string NeedsValue(string input, string description) =>
            "'" + input + "' needs a value" + (string.IsNullOrWhiteSpace(description) ? "." : ": " + description + ".");

        public static string NeedsNumber(string input, string example) =>
            "'" + input + "' needs a number" + (string.IsNullOrEmpty(example) ? "." : ", e.g. " + example + ".");

        public static string NeedsYesNo(string input) => "'" + input + "' needs yes or no.";

        public static string NeedsList(string input, string example) =>
            "'" + input + "' needs a list written as in the example" + (string.IsNullOrEmpty(example) ? "." : ": " + example + ".");

        public const string NoServer =
            "Heron's server has not run on this PC yet, so the palette cannot find it. Start a chat with Heron once, then Run works here.";

        public const string ServerGone =
            "Heron's server is no longer where it last ran (it was moved or removed). Start a chat with Heron once, then try again.";

        public const string NotConnected =
            "AutoCAD is not connected to Heron. Press the Heron button first, then Run.";

        public static string Running(string name) => "Running '" + name + "'. Heron's banner shows the job; answer any question it asks in AutoCAD.";

        public const string AlreadyRunning = "A saved command is already running from this palette. Wait until it is done.";

        public const string NoReply =
            "Heron's server gave no answer the palette could read. Look at the drawing before running it again.";

        private static string Name(string drawing)
        {
            var text = drawing ?? "";
            var cut = text.LastIndexOfAny(new[] { '\\', '/' });
            var name = cut >= 0 ? text.Substring(cut + 1) : text;
            return string.IsNullOrEmpty(name) ? "no drawing" : name;
        }
    }
}
