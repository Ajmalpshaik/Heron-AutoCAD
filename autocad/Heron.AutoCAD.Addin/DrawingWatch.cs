using System;
using System.Runtime.CompilerServices;
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
        /// <summary>The name each open drawing had at its last event, so a Save As can say the old one.</summary>
        private static readonly ConditionalWeakTable<Document, NameBox> Names = new ConditionalWeakTable<Document, NameBox>();
        private static bool _hooked;

        private sealed class NameBox
        {
            public string Name = "";
        }

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
            _hooked = false;
        }

        private static void Attach(Document doc)
        {
            Names.GetValue(doc, _ => new NameBox()).Name = doc.Name;
            doc.Database.SaveComplete += OnSaved;
        }

        private static void Detach(Document doc)
        {
            try
            {
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
                // After the save command ends, when a Save As has given the drawing its new name.
                IdleQueue.Post(() =>
                {
                    var doc = AcApp.DocumentManager.GetDocument(db);
                    if (doc == null) return;
                    var box = Names.GetValue(doc, _ => new NameBox());
                    var was = box.Name;
                    box.Name = doc.Name;
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
