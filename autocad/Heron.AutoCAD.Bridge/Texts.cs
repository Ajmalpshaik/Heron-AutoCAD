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

        public const string UnknownRisk =
            "Heron in AutoCAD did not recognise this tool's level, so it refused it. " + NothingSent;

        public const string NoJob =
            "Heron in AutoCAD only takes drawing input inside a running change job of this chat. " + NothingSent;

        public const string BadRequest = "Heron in AutoCAD could not read the request. " + NothingSent;

        public const string NoRunJob =
            "Heron in AutoCAD only does its own operations inside a running job of this chat, at a level that covers them. " + NothingSent;

        public static string UnknownOperation(string operation) =>
            "Heron in AutoCAD does not have the operation '" + operation + "'. Update Heron so both sides match. " + NothingSent;

        /// <summary>Ends every failed operation: the plug-in keeps nothing of one that failed.</summary>
        public const string NothingChanged = "Nothing was changed.";

        public const string UnreadableResult =
            "Outcome unknown: Heron in AutoCAD did the operation but could not report what it did. Read the drawing back before trying again.";

        public static string NotStarted(int seconds, string? command = null) =>
            string.IsNullOrWhiteSpace(command)
                ? "AutoCAD did not get to the request within " + seconds + " s: a command or a dialog box may be open. Press Esc in AutoCAD and try again. " + NothingChanged
                : "AutoCAD did not get to the request within " + seconds + " s: it is still in the " + command + " command. Finish it or press Esc in AutoCAD, then try again. " + NothingChanged;

        public static string WrongDrawing(string active, string job) =>
            "The active drawing is " + active + ", not " + job + " where this job began. Switch back to it, or call autocad_status on this one. " + NothingChanged;

        public static string UnknownOp(string op) =>
            "Heron in AutoCAD does not know the request '" + op + "'. Update Heron so both sides match. " + NothingSent;
    }
}
