using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Feeds AutoCAD's document events to the drawing log (DrawingEvents,
    /// #48, D-98) as they happen: a drawing opened, came to the front, was
    /// saved (a Save As gives it a new name) or is about to close. The server's
    /// wrong-drawing guard, send_quiet and the palette read the log. Hooked on
    /// the main thread; a handler never throws into AutoCAD.
    /// </summary>
    internal static class DrawingWatch
    {
        /// <summary>
        /// The name each open drawing had at its last event, so a Save As can
        /// say the old one. Keyed by the drawing's database in AutoCAD itself,
        /// never by the .NET wrapper object. Main thread only.
        /// </summary>
        private static readonly Dictionary<IntPtr, string> Names = new Dictionary<IntPtr, string>();
        private static bool _hooked;

        private static DrawingEvents Log => AcadJobHost.Drawings;

        public static void Hook()
        {
            if (_hooked) return;
            var manager = AcApp.DocumentManager;
            foreach (Document doc in manager) Attach(doc);
            manager.DocumentCreated += OnCreated;
            manager.DocumentBecameCurrent += OnBecameCurrent;
            manager.DocumentToBeDestroyed += OnToBeDestroyed;
            _hooked = true;
            Log.Start(manager.MdiActiveDocument?.Name ?? "");
        }

        public static void Unhook()
        {
            if (!_hooked) return;
            var manager = AcApp.DocumentManager;
            manager.DocumentCreated -= OnCreated;
            manager.DocumentBecameCurrent -= OnBecameCurrent;
            manager.DocumentToBeDestroyed -= OnToBeDestroyed;
            foreach (Document doc in manager) Detach(doc);
            Names.Clear();
            _hooked = false;
        }

        private static IntPtr Key(Document doc) => doc.Database.UnmanagedObject;

        private static void Attach(Document doc)
        {
            Names[Key(doc)] = doc.Name;
            doc.Database.SaveComplete += OnSaved;
        }

        private static void Detach(Document doc)
        {
            try
            {
                Names.Remove(Key(doc));
                doc.Database.SaveComplete -= OnSaved;
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Stop following a drawing", ex);
            }
        }

        private static void OnCreated(object? sender, DocumentCollectionEventArgs e)
        {
            try
            {
                if (e.Document == null) return;
                Attach(e.Document);
                Log.DrawingOpened(e.Document.Name);
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Drawing opened", ex);
            }
        }

        private static void OnBecameCurrent(object? sender, DocumentCollectionEventArgs e)
        {
            try
            {
                if (e.Document != null) Log.DrawingActivated(e.Document.Name);
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Drawing came to the front", ex);
            }
        }

        private static void OnToBeDestroyed(object? sender, DocumentCollectionEventArgs e)
        {
            try
            {
                if (e.Document == null) return;
                // Saved under a new name as it closed ("Save changes?" for a new
                // drawing): say the Save As before the close, which the idle
                // work after the save would no longer find.
                if (Names.TryGetValue(Key(e.Document), out var was) && !string.Equals(was, e.Document.Name, StringComparison.OrdinalIgnoreCase))
                    Log.DrawingSaved(e.Document.Name, was);
                Log.DrawingClosed(e.Document.Name);
                Detach(e.Document);
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Drawing closed", ex);
            }
        }

        private static void OnSaved(object? sender, DatabaseIOEventArgs e)
        {
            try
            {
                // The automatic save (.sv$) and backups are AutoCAD's own, not the modeller saving.
                if (DrawingEvents.IsBackupFile(e.FileName) || !(sender is Database db)) return;
                var key = db.UnmanagedObject;
                // After the save command ends, when a Save As has given the drawing its new name.
                IdleQueue.Post(() =>
                {
                    var doc = AcApp.DocumentManager.GetDocument(db);
                    // Closed meanwhile: the close already said what it needed.
                    if (doc == null || !Names.TryGetValue(key, out var was)) return;
                    Names[key] = doc.Name;
                    Log.DrawingSaved(doc.Name, was);
                });
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Drawing saved", ex);
            }
        }
    }
}
