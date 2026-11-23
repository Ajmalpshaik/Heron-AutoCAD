using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// What the add-in does for a job: the banner, the command-line line and
    /// the Keep or Discard box. The bridge decides; the host only shows.
    /// </summary>
    public interface IJobHost
    {
        void Begin(JobInfo job);
        void End(JobEnd end);

        /// <summary>keep | discard | keep_rest. Called on a pipe thread; may wait for the modeller.</summary>
        string AskKeep(KeepRequest request);

        /// <summary>
        /// Hand lines of AutoLISP to AutoCAD as command input with echo off, in
        /// order. Only ever called inside a running job that may change the
        /// drawing. <paramref name="drawing"/> is the job's drawing, by the
        /// name it has now (a Save As followed): when AutoCAD gets to the lines
        /// and another drawing is in front, none is typed (#48). Called on a
        /// pipe thread; waits for AutoCAD to get to it, so the answer is true.
        /// </summary>
        QuietAnswer SendQuiet(string[] lines, string drawing);

        /// <summary>
        /// Do one of the plug-in's own operations (<see cref="PluginOperations"/>)
        /// on the drawing and say what came of it. Called on a pipe thread, only
        /// inside this chat's running job at a level that covers the operation.
        /// </summary>
        RunResult Run(RunRequest request);

        /// <summary>
        /// What this job did to the drawing so far, counted from AutoCAD's own
        /// events (<see cref="JobChanges"/>). Null when the job was not counted.
        /// </summary>
        ChangeReport? Changes(string job);

        /// <summary>
        /// "This job erased N objects: keep them erased, or bring them back?"
        /// Called on a pipe thread; may wait for the modeller. Anything but a
        /// clear "keep erased" brings them back. With <see cref="EraseRequest.Whole"/>
        /// (a job that replaced objects, D-136) it asks "keep the change, or undo
        /// the whole change", brings nothing back, and answers "undo_whole" for
        /// anything but a clear keep: the server goes back to its UNDO mark.
        /// </summary>
        EraseAnswer AskErase(EraseRequest request);

        /// <summary>
        /// Did anything change in the drawing between Heron's previous change
        /// job and this one's begin (the modeller's own work)? Null when not known.
        /// </summary>
        bool? ChangedBefore(string job);

        /// <summary>
        /// The boxes AutoCAD showed during this job that Heron closed (the
        /// dialog watch, <see cref="DialogWatch"/>, D-66). Empty when none.
        /// </summary>
        IReadOnlyList<DialogNote> Dialogs(string job);

        /// <summary>
        /// The running Admin job expects one box: press <paramref name="button"/>
        /// on a box titled exactly <paramref name="title"/>, once (#101). False
        /// when the watch would not take it.
        /// </summary>
        bool ExpectDialog(string job, string title, string button);
    }

    /// <summary>What became of quiet input: typed, refused (nothing typed), or not known.</summary>
    public sealed class QuietAnswer
    {
        /// <summary>Null when typed, or when it went wrong part way (then <see cref="Unknown"/>).</summary>
        public string? RefusedBy { get; private set; }
        public string Message { get; private set; } = "";
        /// <summary>It went wrong while typing: some lines may be in AutoCAD's input.</summary>
        public bool Unknown { get; private set; }

        public static QuietAnswer Typed { get; } = new QuietAnswer();

        public static QuietAnswer Refused(string refusedBy, string message) => new QuietAnswer { RefusedBy = refusedBy, Message = message };

        public static QuietAnswer NotKnown(string message) => new QuietAnswer { Unknown = true, Message = message };
    }

    public sealed class JobInfo
    {
        public string Job { get; set; } = "";
        public string Tool { get; set; } = "";
        public Risk Risk { get; set; }
        public string Summary { get; set; } = "";
        public string Drawing { get; set; } = "";
        public string Conversation { get; set; } = "";
        /// <summary>What begin answered: the server puts an UNDO mark down before a Change job only then (D-68).</summary>
        public bool AskToKeep { get; set; }
    }

    public sealed class JobEnd
    {
        public string Job { get; set; } = "";
        public bool Ok { get; set; }
        public string Outcome { get; set; } = "";
        public string Summary { get; set; } = "";
        public int Ms { get; set; }
        /// <summary>
        /// The server says it put an UNDO mark down before this job (#206). False
        /// when it said not, or did not say (an older server): never guessed from
        /// Ask to Keep, because the server skips the mark when AutoCAD is in a
        /// command or will not answer, and UNDO Back would then go past the job.
        /// </summary>
        public bool Marked { get; set; }
    }

    public sealed class KeepRequest
    {
        public string Job { get; set; } = "";
        public string Summary { get; set; } = "";
        public string[] Handles { get; set; } = new string[0];
        /// <summary>
        /// Set by the host: the question really zoomed to the job (D-136), an undo
        /// step after it. True until the host says otherwise, so a host that does
        /// not say is taken as having zoomed, the safe side for a one-step undo.
        /// </summary>
        public bool Zoomed { get; set; } = true;
    }

    public sealed class RunRequest
    {
        public string Job { get; set; } = "";
        public string Operation { get; set; } = "";
        /// <summary>The drawing the job began on, as the server saw it.</summary>
        public string Drawing { get; set; } = "";
        /// <summary>The operation's arguments, as a JSON object.</summary>
        public string Args { get; set; } = "{}";
    }

    public sealed class RunResult
    {
        public bool Ok { get; set; }
        /// <summary>Why it failed, in words for the chat. Empty when it worked.</summary>
        public string Message { get; set; } = "";
        /// <summary>What it did, as a JSON object.</summary>
        public string Json { get; set; } = "{}";

        public static RunResult Failed(string message) => new RunResult { Ok = false, Message = message };

        public static RunResult Done(Action<Utf8JsonWriter>? body)
        {
            using (var stream = new MemoryStream())
            {
                using (var writer = new Utf8JsonWriter(stream))
                {
                    writer.WriteStartObject();
                    body?.Invoke(writer);
                    writer.WriteEndObject();
                }
                return new RunResult { Ok = true, Json = Encoding.UTF8.GetString(stream.ToArray()) };
            }
        }
    }
}
