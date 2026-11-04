using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// What a job looks like inside AutoCAD: the banner from begin, the
    /// command-line line from end, the Keep or Discard box, and the plug-in's
    /// own operations (PluginRunner). Called on pipe threads; anything that
    /// touches AutoCAD goes through IdleQueue.
    /// </summary>
    internal sealed class AcadJobHost : IJobHost
    {
        private const int MostToHighlight = 500;
        // Longer than the box's own deadline (it closes as Discard first), shorter
        // than the server's wait, so a question can never outlive its chat.
        private static readonly TimeSpan KeepWait = HeronKeepQuestion.Deadline + TimeSpan.FromSeconds(30);
        // How long an operation may wait for AutoCAD to be free. Not started by
        // then, it never runs; once started it runs to the end (the server
        // waits longer, and says "outcome unknown" if even that runs out).
        private static readonly TimeSpan RunStartWait = TimeSpan.FromSeconds(30);
        private readonly HeronActivityBanner _banner;
        private readonly Func<HeronConfig> _config;
        // A read leaves no undo step, so one Ctrl+Z still undoes the last change.
        private readonly UndoPause _undo = new UndoPause(UndoSwitch.Pause, UndoSwitch.Resume);

        public AcadJobHost(HeronActivityBanner banner, Func<HeronConfig> config)
        {
            _banner = banner;
            _config = config;
        }

        public void Begin(JobInfo job)
        {
            HeronLog.Write("begin " + job.Tool + " (" + job.Risk + ") on " + job.Drawing);
            _undo.Begin(job);
            if (_config().ActivityBanner) _banner.Begin(job);
        }

        public void End(JobEnd end)
        {
            HeronLog.Write("end " + end.Job + " " + end.Outcome + " " + end.Ms + " ms");
            // Before the reply, so the next job never starts with recording off.
            _undo.End(end.Job);
            _banner.End(end);
            var seconds = (end.Ms / 1000.0).ToString("0.0");
            string line;
            if (end.Outcome == "discarded") line = "Heron: " + end.Summary + ". Discarded, nothing was kept.";
            else if (end.Ok) line = "Heron: " + end.Summary + ". Done in " + seconds + " s";
            else line = "Heron: " + end.Summary + ". Stopped (" + end.Outcome + ") after " + seconds + " s";
            IdleQueue.Post(() => AcApp.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\n" + line + "\n"));
        }

        public string AskKeep(KeepRequest request)
        {
            var asked = IdleQueue.TryInvoke(() =>
            {
                var count = SelectAndZoom(request.Handles);
                return HeronKeepQuestion.Ask(request.Summary, count);
            }, KeepWait, out var answer);
            // No answer in time, or the box failed: only a clear "keep" keeps.
            return asked ? answer : "discard";
        }

        public void SendQuiet(string[] lines)
        {
            HeronLog.Write("quiet input: " + lines.Length + " line(s)");
            // On the main thread, in order. Typed input, not a loaded file, so
            // SECURELOAD does not apply; echoCommand=false keeps the command
            // history clean (live check, 2026-10-26).
            IdleQueue.Post(() =>
            {
                var doc = AcApp.DocumentManager.MdiActiveDocument;
                if (doc == null) return;
                foreach (var line in lines) doc.SendStringToExecute(line + "\n", true, false, false);
            });
        }

        public RunResult Run(RunRequest request)
        {
            var started = IdleQueue.TryInvoke(() => PluginRunner.Run(request), RunStartWait, out var result);
            return started && result != null ? result : RunResult.Failed(Texts.NotStarted((int)RunStartWait.TotalSeconds, CommandWatch.Current));
        }

        /// <summary>Main thread. Select and zoom to what the job made, so the modeller sees it before choosing.</summary>
        private static int SelectAndZoom(string[] handles)
        {
            var doc = AcApp.DocumentManager.MdiActiveDocument;
            if (doc == null || handles.Length == 0 || handles.Length > MostToHighlight) return handles.Length;
            var ids = new List<ObjectId>();
            Extents3d? box = null;
            using (doc.LockDocument())
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                foreach (var text in handles)
                {
                    long value;
                    try
                    {
                        value = Convert.ToInt64(text, 16);
                    }
                    catch (FormatException)
                    {
                        continue;
                    }
                    if (!doc.Database.TryGetObjectId(new Handle(value), out var id) || id.IsErased) continue;
                    ids.Add(id);
                    if (tr.GetObject(id, OpenMode.ForRead) is Entity entity)
                    {
                        try
                        {
                            var e = entity.GeometricExtents;
                            if (box == null) box = e;
                            else
                            {
                                var grow = box.Value;
                                grow.AddExtents(e);
                                box = grow;
                            }
                        }
                        catch (Autodesk.AutoCAD.Runtime.Exception)
                        {
                            // Some objects have no extents; they are still selected.
                        }
                    }
                }
                tr.Commit();
            }
            if (ids.Count == 0) return 0;
            doc.Editor.SetImpliedSelection(ids.ToArray());
            if (box != null) ZoomTo(box.Value);
            return ids.Count;
        }

        private static void ZoomTo(Extents3d box)
        {
            var dx = Math.Max(box.MaxPoint.X - box.MinPoint.X, 1.0) * 0.15;
            var dy = Math.Max(box.MaxPoint.Y - box.MinPoint.Y, 1.0) * 0.15;
            try
            {
                dynamic acad = AcApp.AcadApplication;
                acad.ZoomWindow(
                    new[] { box.MinPoint.X - dx, box.MinPoint.Y - dy, 0.0 },
                    new[] { box.MaxPoint.X + dx, box.MaxPoint.Y + dy, 0.0 });
            }
            catch (Exception ex)
            {
                HeronLog.Error("Zoom to the change", ex);
            }
        }
    }
}
