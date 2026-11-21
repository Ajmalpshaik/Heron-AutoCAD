using System;
using System.Collections.Generic;
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

        /// <summary>No save, plot or export inside a job while Publish is off (HeronApplication vetoes).</summary>
        public static PublishGuard Guard { get; } = new PublishGuard(() => DateTime.UtcNow);

        /// <summary>What the running job really did, from AutoCAD's own events (ChangeWatch feeds it).</summary>
        public static JobChanges Counter { get; } = new JobChanges();

        /// <summary>Heron's recent change jobs, for the palette's Activity tab (D-68).</summary>
        public static ActivityLog Activity { get; } = new ActivityLog();

        public void Begin(JobInfo job)
        {
            HeronLog.Write("begin " + job.Tool + " (" + job.Risk + ") on " + job.Drawing);
            Guard.Begin(job.Job, job.Risk);
            Counter.Begin(job.Job, job.Risk);
            _undo.Begin(job);
            // Every window open now is the modeller's: the watch never touches it (D-66).
            DialogGuard.Begin(job.Job);
            Activity.Begin(job, DateTime.Now);
            if (_config().ActivityBanner) _banner.Begin(job);
        }

        public void End(JobEnd end)
        {
            HeronLog.Write("end " + end.Job + " " + end.Outcome + " " + end.Ms + " ms");
            Guard.End(end.Job);
            Counter.End(end.Job);
            DialogGuard.End(end.Job);
            Activity.End(end, Counter.Read(end.Job));
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
            // Heron's own question: the dialog watch keeps its hands off it.
            DialogGuard.Watch.Pause();
            bool asked;
            string answer;
            try
            {
                asked = IdleQueue.TryInvoke(() =>
                {
                    var doc = AcApp.DocumentManager.MdiActiveDocument;
                    var count = doc == null ? request.Handles.Length : Showing.SelectAndZoom(doc, request.Handles);
                    return HeronKeepQuestion.Ask(request.Summary, count);
                }, KeepWait, out answer);
            }
            finally
            {
                DialogGuard.Watch.Resume();
            }
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

        public ChangeReport? Changes(string job) => Counter.Read(job);

        public bool? ChangedBefore(string job) => Counter.ChangedBefore(job);

        public IReadOnlyList<DialogNote> Dialogs(string job) => DialogGuard.Watch.Notes(job);

        public bool ExpectDialog(string job, string title, string button) => DialogGuard.Watch.Expect(job, title, button);

        public EraseAnswer AskErase(EraseRequest request)
        {
            DialogGuard.Watch.Pause();
            bool asked;
            EraseAnswer? answer;
            try
            {
                asked = IdleQueue.TryInvoke(() =>
                {
                    var choice = HeronEraseQuestion.Ask(request.Summary, request.Handles.Length);
                    if (choice == "keep_erased") return new EraseAnswer { Answer = "keep_erased" };
                    var doc = AcApp.DocumentManager.MdiActiveDocument;
                    var back = doc == null ? 0 : HeronEraseQuestion.Restore(doc, request.Handles);
                    HeronLog.Write("brought back " + back + " of " + request.Handles.Length + " erased object(s)");
                    return new EraseAnswer { Answer = "restored", Restored = back };
                }, KeepWait, out answer);
            }
            finally
            {
                DialogGuard.Watch.Resume();
            }
            if (asked && answer != null) return answer;
            // Could not even ask: put them back, on the main thread, as soon as AutoCAD is free.
            IdleQueue.Post(() =>
            {
                var doc = AcApp.DocumentManager.MdiActiveDocument;
                if (doc != null) HeronEraseQuestion.Restore(doc, request.Handles);
            });
            return new EraseAnswer { Answer = "restored", Message = "Heron could not show the question in time, so it is bringing them back." };
        }

        public RunResult Run(RunRequest request)
        {
            var started = IdleQueue.TryInvoke(() => PluginRunner.Run(request), RunStartWait, out var result);
            return started && result != null ? result : RunResult.Failed(Texts.NotStarted((int)RunStartWait.TotalSeconds, CommandWatch.Current));
        }
    }
}
