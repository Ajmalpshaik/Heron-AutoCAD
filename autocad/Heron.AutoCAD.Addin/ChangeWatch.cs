using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Feeds AutoCAD's own database events to the job's change count
    /// (JobChanges, D-50): what was really appended, modified and erased,
    /// whoever did it inside the job. Hooked once per drawing on the main
    /// thread; each handler returns at once when no job is counted.
    /// </summary>
    internal static class ChangeWatch
    {
        private static readonly ConditionalWeakTable<Database, object> Hooked = new ConditionalWeakTable<Database, object>();
        private static bool _hooked;

        // AutoCAD's own work while it puts another tab on screen (D-125): the sheets'
        // viewports turned off and on, the paper-space viewport erased and made again.
        private static readonly TabSwitchWindow TabSwitch = new TabSwitchWindow();

        public static void Hook()
        {
            if (_hooked) return;
            var manager = AcApp.DocumentManager;
            foreach (Document doc in manager) Attach(doc.Database);
            manager.DocumentCreated += OnCreated;
            AcApp.SystemVariableChanging += OnVariableWillChange;
            AcApp.SystemVariableChanged += OnVariableChanged;
            _hooked = true;
        }

        public static void Unhook()
        {
            if (!_hooked) return;
            var manager = AcApp.DocumentManager;
            manager.DocumentCreated -= OnCreated;
            AcApp.SystemVariableChanging -= OnVariableWillChange;
            AcApp.SystemVariableChanged -= OnVariableChanged;
            foreach (Document doc in manager) Detach(doc.Database);
            _hooked = false;
        }

        private static void OnCreated(object? sender, DocumentCollectionEventArgs e)
        {
            if (e.Document != null) Attach(e.Document.Database);
        }

        private static void OnVariableWillChange(object? sender, Autodesk.AutoCAD.ApplicationServices.SystemVariableChangingEventArgs e)
        {
            try
            {
                TabSwitch.WillChange(e.Name);
            }
            catch (System.Exception)
            {
            }
        }

        private static void OnVariableChanged(object? sender, Autodesk.AutoCAD.ApplicationServices.SystemVariableChangedEventArgs e)
        {
            try
            {
                TabSwitch.Changed(e.Name);
            }
            catch (System.Exception)
            {
            }
        }

        private static void Attach(Database db)
        {
            if (Hooked.TryGetValue(db, out _)) return;
            Hooked.Add(db, new object());
            db.ObjectAppended += OnAppended;
            db.ObjectModified += OnModified;
            db.ObjectErased += OnErased;
        }

        private static void Detach(Database db)
        {
            try
            {
                db.ObjectAppended -= OnAppended;
                db.ObjectModified -= OnModified;
                db.ObjectErased -= OnErased;
                Hooked.Remove(db);
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Stop counting changes", ex);
            }
        }

        // Entities are the work; a layer, block or style erased (a purge) is
        // work too. Dictionaries, sort tables and the like change on their own.
        private static bool Counts(DBObject obj) => obj is Entity;

        private static bool CountsErased(DBObject obj) => obj is Entity || obj is SymbolTableRecord;

        /// <summary>An entity changed with no Heron change job running: the modeller's own work.</summary>
        private static void Outside(DBObject obj)
        {
            try
            {
                if (obj is Entity) AcadJobHost.Counter.Outside();
            }
            catch (System.Exception)
            {
            }
        }

        private static void OnAppended(object? sender, ObjectEventArgs e)
        {
            if (TabSwitch.Open) return; // AutoCAD switching tabs, not the job (D-125)
            if (!AcadJobHost.Counter.Counting)
            {
                Outside(e.DBObject);
                return;
            }
            try
            {
                if (Counts(e.DBObject)) AcadJobHost.Counter.Appended(e.DBObject.Handle.ToString());
            }
            catch (System.Exception)
            {
                // An object that cannot say its handle is not counted; the job goes on.
            }
        }

        private static void OnModified(object? sender, ObjectEventArgs e)
        {
            if (TabSwitch.Open) return; // AutoCAD switching tabs, not the job (D-125)
            if (!AcadJobHost.Counter.Counting)
            {
                Outside(e.DBObject);
                return;
            }
            try
            {
                if (Counts(e.DBObject)) AcadJobHost.Counter.Modified(e.DBObject.Handle.ToString());
            }
            catch (System.Exception)
            {
            }
        }

        private static void OnErased(object? sender, ObjectErasedEventArgs e)
        {
            if (TabSwitch.Open) return; // AutoCAD switching tabs, not the job (D-125)
            if (!AcadJobHost.Counter.Counting)
            {
                Outside(e.DBObject);
                return;
            }
            try
            {
                if (CountsErased(e.DBObject)) AcadJobHost.Counter.Erased(e.DBObject.Handle.ToString(), e.Erased);
            }
            catch (System.Exception)
            {
            }
        }
    }
}
