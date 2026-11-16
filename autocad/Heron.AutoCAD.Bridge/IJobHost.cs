using System;
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
        /// order. Only ever called inside a running job that may change the drawing.
        /// </summary>
        void SendQuiet(string[] lines);

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
        /// clear "keep erased" brings them back.
        /// </summary>
        EraseAnswer AskErase(EraseRequest request);

        /// <summary>
        /// Did anything change in the drawing between Heron's previous change
        /// job and this one's begin (the modeller's own work)? Null when not known.
        /// </summary>
        bool? ChangedBefore(string job);
    }

    public sealed class JobInfo
    {
        public string Job { get; set; } = "";
        public string Tool { get; set; } = "";
        public Risk Risk { get; set; }
        public string Summary { get; set; } = "";
        public string Drawing { get; set; } = "";
        public string Conversation { get; set; } = "";
    }

    public sealed class JobEnd
    {
        public string Job { get; set; } = "";
        public bool Ok { get; set; }
        public string Outcome { get; set; } = "";
        public string Summary { get; set; } = "";
        public int Ms { get; set; }
    }

    public sealed class KeepRequest
    {
        public string Job { get; set; } = "";
        public string Summary { get; set; } = "";
        public string[] Handles { get; set; } = new string[0];
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
