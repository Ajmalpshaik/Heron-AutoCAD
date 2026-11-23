namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Every sentence the bridge says to a chat. Kept in one place so the
    /// Python side, the docs and the tests quote the same words.
    /// </summary>
    public static class Texts
    {
        public const string NothingSent = "Nothing was sent to AutoCAD.";

        public const string WrongSession =
            "This chat holds an old or wrong Heron session for this AutoCAD. Press Heron in AutoCAD to connect again. " + NothingSent;

        public const string InUse = "This AutoCAD is in use by another chat. " + NothingSent;

        public const string ChangesOff =
            "Changes is off, so Heron may not change this drawing. To allow it, press Settings on the Heron tab in AutoCAD and turn Changes on (or type HERONCHANGES). " + NothingSent;

        public const string PublishOff =
            "Publish is off, so Heron may not save, export or plot drawings. To allow it, press Settings on the Heron tab in AutoCAD and turn Publish on (or type HERONPUBLISH). " + NothingSent;

        public const string AdminOff =
            "Admin is off, so Heron may not run AutoCAD commands, AutoLISP or system-variable changes. To allow it, press Settings on the Heron tab in AutoCAD and turn Admin on (or type HERONADMIN). " + NothingSent;

        public const string ChangesHeld =
            "Changes is held off by a Windows policy on this PC, so Heron may not change this drawing. Only the PC's administrator can lift it. " + NothingSent;

        public const string PublishHeld =
            "Publish is held off by a Windows policy on this PC, so Heron may not save, export or plot drawings. Only the PC's administrator can lift it. " + NothingSent;

        public const string AdminHeld =
            "Admin is held off by a Windows policy on this PC, so Heron may not run AutoCAD commands, AutoLISP or system-variable changes. Only the PC's administrator can lift it. " + NothingSent;

        public const string UnknownRisk =
            "Heron in AutoCAD did not recognise this tool's level, so it refused it. " + NothingSent;

        public const string NoJob =
            "Heron in AutoCAD only takes drawing input inside a running change job of this chat. " + NothingSent;

        public const string BadRequest = "Heron in AutoCAD could not read the request. " + NothingSent;

        public const string NoRunJob =
            "Heron in AutoCAD only does its own operations inside a running job of this chat, at a level that covers them. " + NothingSent;

        public const string ExpectNeedsAdmin =
            "Only a job that holds the Admin padlock (a command or AutoLISP) may name a button for a box: it can press Yes or OK. " + NothingSent;

        public const string ExpectNotTaken =
            "Heron in AutoCAD would not take that answer: give the box's exact title and one button, once per job. " + NothingSent;

        public static string UnknownOperation(string operation) =>
            "Heron in AutoCAD does not have the operation '" + operation + "'. Update Heron so both sides match. " + NothingSent;

        /// <summary>Ends every failed operation: the plug-in keeps nothing of one that failed.</summary>
        public const string NothingChanged = "Nothing was changed.";

        /// <summary>A new object AutoCAD added itself would not join the job's transaction, and was taken off again (D-143).</summary>
        public static string PostedTakenBack(string what) =>
            "AutoCAD added " + what + " but would not take it into Heron's one-step change, so Heron took it off again. Try once more; if it says this again, use AutoCAD's own command.";

        /// <summary>The same, but taking it off failed too: something may be left, so never "Nothing was changed".</summary>
        public static string PostedLeftBehind(string what) =>
            "AutoCAD added " + what + " but would not take it into Heron's one-step change, and Heron could not take it off again. "
            + "It may still be in the drawing, outside Heron's undo step: check it in AutoCAD, and remove it there if it is not wanted.";

        public const string UnreadableResult =
            "Outcome unknown: Heron in AutoCAD did the operation but could not report what it did. Read the drawing back before trying again.";

        public static string NotStarted(int seconds, string? command = null) =>
            string.IsNullOrWhiteSpace(command)
                ? "AutoCAD did not get to the request within " + seconds + " s: a command or a dialog box may be open. Press Esc in AutoCAD and try again. " + NothingChanged
                : "AutoCAD did not get to the request within " + seconds + " s: it is still in the " + command + " command. Finish it or press Esc in AutoCAD, then try again. " + NothingChanged;

        public static string WrongDrawing(string active, string job) =>
            "The active drawing is " + active + ", not " + job + " where this job began. Switch back to it, or call autocad_status on this one. " + NothingChanged;

        public static string PublishVetoed(string command) =>
            "Heron stopped " + command + ": a Heron job may not save, plot or export while Publish is off. Turn Publish on in Heron's Settings to allow it.";

        public const string Stopped =
            "The modeller stopped Heron in AutoCAD (HERONSTOP). Nothing more is done until they type HERONSTOP again. " + NothingSent;

        /// <summary>
        /// send_quiet, when another drawing came to the front during the job
        /// (#48). Not "nothing was sent": the job may have done work before it.
        /// </summary>
        public static string DrawingChangedInJob(string job, string active) =>
            "The drawing in front changed while this job ran: it began in " + DrawingNames.Short(job) + ", and " +
            (string.IsNullOrEmpty(active) ? "no drawing is in front now" : DrawingNames.Short(active) + " is in front now") +
            ", so Heron typed none of this input. What the job did before it stays. Switch back to " + DrawingNames.Short(job) +
            ", read it back, and call autocad_status before trying again.";

        /// <summary>send_quiet, when AutoCAD did not get to the input in time: abandoned, never typed later.</summary>
        public static string QuietNotStarted(int seconds, string? command) =>
            "AutoCAD did not get to this input within " + seconds + " s" +
            (string.IsNullOrWhiteSpace(command) ? " (a command or a dialog box may be open)" : " (it is still in the " + command + " command)") +
            ", so Heron typed none of it, and never will. What the job did before it stays. Press Esc in AutoCAD, read the drawing back, and try again.";

        /// <summary>send_quiet, when a line is longer than the plug-in types (#45).</summary>
        public static string QuietTooLong(int limit) =>
            "Heron in AutoCAD types drawing input lines of up to " + limit + " characters, and one was longer, so it typed none of them. " + NothingSent;

        public static string UnknownOp(string op) =>
            "Heron in AutoCAD does not know the request '" + op + "'. Update Heron so both sides match. " + NothingSent;
    }
}
