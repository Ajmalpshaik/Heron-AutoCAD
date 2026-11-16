using Autodesk.AutoCAD.ApplicationServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Stops a save, plot or export that starts inside a Heron job while
    /// Publish is off (PublishGuard has the rules). AutoCAD asks for a
    /// document lock before every command; vetoing that request stops the
    /// command before it does anything. Hooked on the main thread.
    /// </summary>
    internal static class PublishVeto
    {
        private static bool _hooked;

        public static void Hook()
        {
            if (_hooked) return;
            AcApp.DocumentManager.DocumentLockModeChanged += OnLockModeChanged;
            _hooked = true;
        }

        public static void Unhook()
        {
            if (!_hooked) return;
            AcApp.DocumentManager.DocumentLockModeChanged -= OnLockModeChanged;
            _hooked = false;
        }

        private static void OnLockModeChanged(object? sender, DocumentLockModeChangedEventArgs e)
        {
            try
            {
                // Cheap checks first: this fires for every lock in every drawing.
                var name = e.GlobalCommandName;
                if (!PublishGuard.Writes(name) || !AcadJobHost.Guard.InJob) return;
                var words = AcadJobHost.Guard.Veto(name, HeronApplication.LoadConfig());
                if (words == null) return;
                e.Veto();
                HeronLog.Write("vetoed " + name + " during a Heron job (Publish off)");
                e.Document?.Editor.WriteMessage("\n" + words + "\n");
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Publish veto", ex);
            }
        }
    }
}
