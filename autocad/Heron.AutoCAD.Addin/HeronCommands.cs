using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(Heron.AutoCAD.Addin.HeronCommands))]

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The ribbon buttons as commands, for anyone who works from the command
    /// line. Session commands: they work with no drawing open and never sit
    /// inside a drawing's undo history.
    /// </summary>
    public sealed class HeronCommands
    {
        [CommandMethod("HERON", CommandFlags.Session)]
        public void Toggle() => HeronActions.ToggleConnect();

        [CommandMethod("HERONSTATUS", CommandFlags.Session)]
        public void Status() => HeronActions.ShowStatus();

        [CommandMethod("HERONFREE", CommandFlags.Session)]
        public void Free() => HeronActions.FreeHold();

        [CommandMethod("HERONSETTINGS", CommandFlags.Session)]
        public void Settings() => HeronActions.ShowSettings();

        [CommandMethod("HERONCHANGES", CommandFlags.Session)]
        public void Changes() => HeronActions.TogglePadlock(Padlock.Changes);

        [CommandMethod("HERONPUBLISH", CommandFlags.Session)]
        public void Publish() => HeronActions.TogglePadlock(Padlock.Publish);

        [CommandMethod("HERONADMIN", CommandFlags.Session)]
        public void Admin() => HeronActions.TogglePadlock(Padlock.Admin);

        [CommandMethod("HERONASKTOKEEP", CommandFlags.Session)]
        public void AskToKeep() => HeronActions.TogglePadlock(Padlock.AskToKeep);
    }
}
