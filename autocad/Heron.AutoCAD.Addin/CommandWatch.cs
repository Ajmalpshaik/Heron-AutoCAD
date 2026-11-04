using System;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.ApplicationServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Follows AutoCAD's command and LISP events in every open drawing, so the
    /// pipe thread can say which command the active drawing is in when a
    /// request has to wait (CommandTracker). Hooked on the main thread.
    /// </summary>
    internal static class CommandWatch
    {
        private const string Lisp = "AutoLISP";
        private static readonly ConditionalWeakTable<Document, CommandTracker> Trackers = new ConditionalWeakTable<Document, CommandTracker>();
        private static volatile CommandTracker? _active;
        private static bool _hooked;

        /// <summary>The command the active drawing is in, or null. Safe from any thread.</summary>
        public static string? Current => _active?.Current;

        public static void Hook()
        {
            if (_hooked) return;
            var manager = AcApp.DocumentManager;
            foreach (Document doc in manager) Attach(doc);
            manager.DocumentCreated += OnCreated;
            manager.DocumentBecameCurrent += OnBecameCurrent;
            var active = manager.MdiActiveDocument;
            _active = active == null ? null : Trackers.GetValue(active, _ => new CommandTracker());
            _hooked = true;
        }

        public static void Unhook()
        {
            if (!_hooked) return;
            var manager = AcApp.DocumentManager;
            manager.DocumentCreated -= OnCreated;
            manager.DocumentBecameCurrent -= OnBecameCurrent;
            foreach (Document doc in manager) Detach(doc);
            _active = null;
            _hooked = false;
        }

        private static void OnCreated(object? sender, DocumentCollectionEventArgs e)
        {
            if (e.Document != null) Attach(e.Document);
        }

        private static void OnBecameCurrent(object? sender, DocumentCollectionEventArgs e)
        {
            _active = e.Document == null ? null : Trackers.GetValue(e.Document, _ => new CommandTracker());
        }

        private static void Attach(Document doc)
        {
            Trackers.GetValue(doc, _ => new CommandTracker());
            doc.CommandWillStart += OnStarted;
            doc.CommandEnded += OnEnded;
            doc.CommandCancelled += OnEnded;
            doc.CommandFailed += OnEnded;
            doc.LispWillStart += OnLispStarted;
            doc.LispEnded += OnLispEnded;
            doc.LispCancelled += OnLispEnded;
        }

        private static void Detach(Document doc)
        {
            try
            {
                doc.CommandWillStart -= OnStarted;
                doc.CommandEnded -= OnEnded;
                doc.CommandCancelled -= OnEnded;
                doc.CommandFailed -= OnEnded;
                doc.LispWillStart -= OnLispStarted;
                doc.LispEnded -= OnLispEnded;
                doc.LispCancelled -= OnLispEnded;
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Stop following commands", ex);
            }
        }

        private static CommandTracker? Of(object? sender) =>
            sender is Document doc ? Trackers.GetValue(doc, _ => new CommandTracker()) : null;

        private static void OnStarted(object? sender, CommandEventArgs e) => Of(sender)?.Started(e.GlobalCommandName);

        private static void OnEnded(object? sender, CommandEventArgs e) => Of(sender)?.Ended(e.GlobalCommandName);

        private static void OnLispStarted(object? sender, LispWillStartEventArgs e) => Of(sender)?.Started(Lisp);

        private static void OnLispEnded(object? sender, EventArgs e) => Of(sender)?.Ended(Lisp);
    }
}
