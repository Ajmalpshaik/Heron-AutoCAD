using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// One request line in, one reply line out. No pipes and no AutoCAD here,
    /// so every rule the bridge enforces is tested offline.
    ///
    /// Ops: ping, info, release, begin, end, ask_keep, send_quiet, run, changes,
    /// ask_erase, since_last, dialogs, expect_dialog, drawings. Every
    /// op needs the session token. begin is where the hold and the padlocks are
    /// checked; send_quiet and run only work inside the job begin allowed.
    /// </summary>
    public sealed class BridgeProtocol
    {
        public const int Version = 1;

        /// <summary>
        /// The longest line of drawing input send_quiet types (#45, D-98). Ping
        /// says it, so the server sends a batch in fewer, longer pieces than
        /// over COM (600); a longer line is refused and nothing is typed. Below
        /// the 2,000 characters that worked all day over COM (known limits §3).
        /// </summary>
        public const int QuietLineLimit = 1500;
        public static readonly TimeSpan KeepGrantIdle = TimeSpan.FromMinutes(10);

        private readonly IJobHost _host;
        private readonly Func<HeronConfig> _config;
        private readonly string _token;
        private readonly HeronHold _hold;

        /// <summary>Which chat holds this AutoCAD - for "Free this AutoCAD".</summary>
        public HeronHold Hold => _hold;
        private readonly Func<DateTime> _clock;
        private readonly object _grantGate = new object();
        private string? _grantConversation;
        private readonly Dictionary<string, RunningJob> _running = new Dictionary<string, RunningJob>();
        private DateTime _grantLast;

        public BridgeProtocol(IJobHost host, Func<HeronConfig> config, string token, HeronHold hold, Func<DateTime> clock)
        {
            _host = host;
            _config = config;
            _token = token;
            _hold = hold;
            _clock = clock;
        }

        private volatile bool _stopped;

        /// <summary>
        /// The modeller's emergency stop (HERONSTOP). Sticky until they lift it:
        /// no new job, no drawing input, no plug-in operation and no named button
        /// for a box (expect_dialog, #210) for the job
        /// already running, which stops at its next request. Ending a job,
        /// Keep or Discard and the erase question still answer, so a stopped
        /// job can still be put back. Answered on the pipe thread, never waits
        /// for AutoCAD.
        /// </summary>
        public bool Stopped => _stopped;

        public void Stop() => _stopped = true;

        /// <summary>
        /// Something the modeller is doing in AutoCAD that no new job may start
        /// under: the palette's Undo waiting for AutoCAD to run it (D-68). The
        /// sentence for the chat, or null. Asked at begin only, on the pipe thread.
        /// </summary>
        public Func<string?>? BlockedBy { get; set; }

        /// <summary>
        /// The command the active drawing is in, from the add-in's command
        /// tracker (<see cref="CommandTracker"/>), or null when it is in none.
        /// Read on the pipe thread, never waits for AutoCAD; ping reports it,
        /// so a busy answer from the server can name it (#47). Not set: ping
        /// leaves it out, as an older plug-in does.
        /// </summary>
        public Func<string?>? CurrentCommand { get; set; }

        public void Resume() => _stopped = false;

        /// <summary>
        /// What happened to the drawings in this AutoCAD, from the add-in's
        /// document events (#48): the drawings op reports it, and send_quiet
        /// refuses input once another drawing came to the front during the job.
        /// Not set: the drawings op says it does not know, as before.
        /// </summary>
        public DrawingEvents? Drawings { get; set; }

        /// <summary>Set by the server so info can report it.</summary>
        public Dictionary<string, object> Info { get; } = new Dictionary<string, object>();

        /// <summary>True while a "keep the rest of this job" grant stands (the ribbon shows it).</summary>
        public bool KeepGrantActive
        {
            get
            {
                lock (_grantGate) return _grantConversation != null && _clock() - _grantLast < KeepGrantIdle;
            }
        }

        public void ClearKeepGrant()
        {
            lock (_grantGate) _grantConversation = null;
        }

        public string Handle(string line)
        {
            JsonDocument doc;
            try
            {
                doc = JsonDocument.Parse(line);
            }
            catch (JsonException)
            {
                return Refuse("BadRequest", Texts.BadRequest);
            }

            using (doc)
            {
                var root = doc.RootElement;
                if (root.ValueKind != JsonValueKind.Object) return Refuse("BadRequest", Texts.BadRequest);
                var op = Str(root, "op");
                if (!BridgeIdentity.TokenEquals(_token, Str(root, "token"))) return Refuse("Session", Texts.WrongSession);
                var conversation = Str(root, "conversation");

                if (_stopped && (op == "begin" || op == "send_quiet" || op == "run" || op == "expect_dialog"))
                    return Refuse("Stopped", Texts.Stopped);

                try
                {
                    switch (op)
                    {
                        case "ping":
                            return Ok(w =>
                            {
                                w.WriteNumber("protocolVersion", Version);
                                w.WriteBoolean("stopped", _stopped);
                                WritePadlocks(w, _config());
                                if (CurrentCommand != null) w.WriteString("command", RunningCommand());
                                w.WriteNumber("quietLimit", QuietLineLimit);
                            });
                        case "info":
                            return Ok(w =>
                            {
                                w.WriteNumber("protocolVersion", Version);
                                foreach (var pair in Info) w.WriteString(pair.Key, pair.Value?.ToString());
                            });
                        case "release":
                            _hold.Release(conversation);
                            return Ok(null);
                        case "begin":
                            return Begin(root, conversation);
                        case "end":
                            return End(root, conversation);
                        case "ask_keep":
                            return AskKeep(root, conversation);
                        case "send_quiet":
                            return SendQuiet(root, conversation);
                        case "run":
                            return Run(root, conversation);
                        case "changes":
                            return Changes(root, conversation);
                        case "ask_erase":
                            return AskErase(root, conversation);
                        case "since_last":
                            return SinceLast(root, conversation);
                        case "dialogs":
                            return Dialogs(root, conversation);
                        case "expect_dialog":
                            return ExpectDialog(root, conversation);
                        case "drawings":
                            return DrawingsSince(root);
                        default:
                            return Refuse("BadRequest", Texts.UnknownOp(op));
                    }
                }
                catch (Exception ex)
                {
                    return Refuse("Error", "Heron in AutoCAD hit an error: " + ex.Message + " " + Texts.NothingSent);
                }
            }
        }

        private string? RunningCommand()
        {
            try
            {
                var command = CurrentCommand?.Invoke();
                return string.IsNullOrWhiteSpace(command) ? null : command;
            }
            catch (Exception)
            {
                return null; // a ping always answers; the command is a nicety
            }
        }

        private string Begin(JsonElement root, string conversation)
        {
            if (!RiskNames.TryParse(Str(root, "risk"), out var risk)) return Refuse("Level", Texts.UnknownRisk);
            var blocked = BlockedBy?.Invoke();
            if (blocked != null) return Refuse("Busy", blocked);
            if (!_hold.TryTake(conversation, _clock())) return Refuse("InUse", Texts.InUse);
            var config = _config();
            var refusal = Permissions.Refusal(risk, config);
            if (refusal != null) return Refuse(refusal.RefusedBy, refusal.Message);

            // Told up front, so the server puts an UNDO mark down only for a
            // job that will be asked about, and asks only then.
            bool askToKeep;
            lock (_grantGate)
            {
                var granted = _grantConversation == conversation && _clock() - _grantLast < KeepGrantIdle;
                askToKeep = config.AskBeforeKeeping && !granted;
            }

            var job = new JobInfo
            {
                Job = Str(root, "job"),
                Tool = Str(root, "tool"),
                Risk = risk,
                Summary = Str(root, "summary"),
                Drawing = Str(root, "drawing"),
                Conversation = conversation,
                AskToKeep = askToKeep,
            };
            lock (_running) _running[job.Job] = new RunningJob(conversation, risk, job.Drawing, Drawings?.Seq ?? 0);
            try
            {
                _host.Begin(job);
            }
            catch (Exception)
            {
                // The banner is something to see, not a gate: a drawing glitch
                // must not stop a job the padlocks allowed.
            }
            var seq = Drawings?.Seq;
            return Ok(w =>
            {
                w.WriteBoolean("askToKeep", askToKeep);
                // Where the drawing log stood at begin, so a long job can ask later
                // whether another drawing came to the front since (#165).
                if (seq.HasValue) w.WriteNumber("drawingSeq", seq.Value);
            });
        }

        private string End(JsonElement root, string conversation)
        {
            _hold.TryTake(conversation, _clock());
            var end = new JobEnd
            {
                Job = Str(root, "job"),
                Ok = root.TryGetProperty("ok", out var ok) && ok.ValueKind == JsonValueKind.True,
                Outcome = Str(root, "outcome"),
                Summary = Str(root, "summary"),
                Ms = root.TryGetProperty("ms", out var ms) && ms.ValueKind == JsonValueKind.Number ? ms.GetInt32() : 0,
                // Only a plain true: an older server sends nothing, and gets no UNDO Back (#206).
                Marked = root.TryGetProperty("marked", out var marked) && marked.ValueKind == JsonValueKind.True,
            };
            lock (_running) _running.Remove(end.Job);
            try
            {
                _host.End(end);
            }
            catch (Exception)
            {
            }
            return Ok(null);
        }

        private string AskKeep(JsonElement root, string conversation)
        {
            if (!_config().AskBeforeKeeping) return Answer("keep");
            lock (_grantGate)
            {
                if (_grantConversation == conversation && _clock() - _grantLast < KeepGrantIdle)
                {
                    _grantLast = _clock();
                    return Answer("keep");
                }
                _grantConversation = null;
            }

            var handles = new List<string>();
            if (root.TryGetProperty("handles", out var list) && list.ValueKind == JsonValueKind.Array)
                foreach (var item in list.EnumerateArray())
                    if (item.ValueKind == JsonValueKind.String) handles.Add(item.GetString() ?? "");

            string answer;
            try
            {
                answer = _host.AskKeep(new KeepRequest { Job = Str(root, "job"), Summary = Str(root, "summary"), Handles = handles.ToArray() });
            }
            catch (Exception)
            {
                answer = "discard";
            }
            if (answer != "keep" && answer != "keep_rest") answer = "discard";
            if (answer == "keep_rest")
                lock (_grantGate)
                {
                    _grantConversation = conversation;
                    _grantLast = _clock();
                }
            return Answer(answer);
        }

        /// <summary>
        /// Drawing input with echo off, so a batch does not flood the command
        /// history. Allowed only inside this chat's running job that may change
        /// the drawing: the padlock check at begin already covered it.
        /// </summary>
        private string SendQuiet(JsonElement root, string conversation)
        {
            var running = Running(root, conversation);
            if (running == null || running.Risk == Risk.Read || running.Risk == Risk.View)
                return Refuse("Job", Texts.NoJob);
            // Another drawing came to the front during the job (#48): typing on
            // would put the input in the wrong drawing. Only an event AutoCAD
            // reported since begin counts, so a missed event never refuses. A
            // Save As of the job's drawing is the same drawing: its new name counts.
            var name = Drawings?.CurrentName(running.Drawing, running.FrontSeq) ?? running.Drawing;
            var front = Drawings?.FrontChangedSince(running.FrontSeq);
            if (front != null && !DrawingNames.Same(front, name))
                return Refuse("Drawing", Texts.DrawingChangedInJob(name, front));
            var lines = new List<string>();
            if (root.TryGetProperty("lines", out var list) && list.ValueKind == JsonValueKind.Array)
                foreach (var item in list.EnumerateArray())
                    if (item.ValueKind == JsonValueKind.String) lines.Add(item.GetString() ?? "");
            foreach (var line in lines)
                if (line.Length > QuietLineLimit) return Refuse("TooLong", Texts.QuietTooLong(QuietLineLimit));
            var typed = _host.SendQuiet(lines.ToArray(), name) ?? QuietAnswer.NotKnown("");
            if (typed.RefusedBy != null) return Refuse(typed.RefusedBy, typed.Message);
            // Typed, or it went wrong part way: either way never typed again over COM.
            if (typed.Unknown) return Ok(w => w.WriteBoolean("unknown", true));
            return Ok(null);
        }

        /// <summary>
        /// The drawing events after number <c>since</c> (#48), for the server's
        /// wrong-drawing guard. Read only, answered on the pipe thread. Any chat
        /// with this session's token may ask: a connected chat can already list
        /// the open drawings over COM.
        /// </summary>
        private string DrawingsSince(JsonElement root)
        {
            var log = Drawings;
            if (log == null) return Ok(w => w.WriteBoolean("known", false));
            long since = 0;
            if (root.TryGetProperty("since", out var given) && given.ValueKind == JsonValueKind.Number && given.TryGetInt64(out var number))
                since = Math.Max(0, number);
            var history = log.Since(since);
            return Ok(w =>
            {
                w.WriteBoolean("known", true);
                w.WriteString("epoch", history.Epoch);
                w.WriteNumber("seq", history.Seq);
                if (history.Active == null) w.WriteNull("active");
                else w.WriteString("active", history.Active);
                w.WriteBoolean("lost", history.Lost);
                w.WriteStartArray("events");
                foreach (var e in history.Events)
                {
                    w.WriteStartObject();
                    w.WriteNumber("seq", e.Seq);
                    w.WriteString("kind", e.Kind);
                    w.WriteString("drawing", e.Drawing);
                    if (e.Was.Length > 0) w.WriteString("was", e.Was);
                    w.WriteString("at", e.At.ToString("HH:mm:ss", System.Globalization.CultureInfo.InvariantCulture));
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        /// <summary>
        /// One of the plug-in's own operations (loft, fillet, super hatch...),
        /// which COM has no call for. Only one on the list, only inside this
        /// chat's running job, and only when the job's level covers it: a read
        /// job can list a solid's faces but never fillet them. The padlock is
        /// checked again, and the one-chat hold is pinned while it runs, so a
        /// long one never lets another chat in half way.
        /// </summary>
        private string Run(JsonElement root, string conversation)
        {
            var running = Running(root, conversation);
            if (running == null) return Refuse("Job", Texts.NoRunJob);
            var operation = Str(root, "operation");
            if (!PluginOperations.TryLevel(operation, out var level)) return Refuse("BadRequest", Texts.UnknownOperation(operation));
            if (running.Risk < level) return Refuse("Job", Texts.NoRunJob);
            // Checked again, not only at begin: a padlock turned off since then holds.
            var refusal = Permissions.Refusal(level, _config());
            if (refusal != null) return Refuse(refusal.RefusedBy, refusal.Message);

            var args = root.TryGetProperty("args", out var given) && given.ValueKind == JsonValueKind.Object ? given.GetRawText() : "{}";
            if (!_hold.TryPin(conversation, _clock())) return Refuse("InUse", Texts.InUse);
            RunResult result;
            try
            {
                result = _host.Run(new RunRequest { Job = Str(root, "job"), Operation = operation, Drawing = running.Drawing, Args = args });
            }
            finally
            {
                _hold.Unpin(_clock());
            }
            if (result == null || !result.Ok)
                return Refuse("Operation", string.IsNullOrWhiteSpace(result?.Message) ? Texts.UnreadableResult : result!.Message);

            JsonDocument parsed;
            try
            {
                parsed = JsonDocument.Parse(result.Json);
            }
            catch (JsonException)
            {
                return Refuse("Operation", Texts.UnreadableResult);
            }
            using (parsed)
            {
                if (parsed.RootElement.ValueKind != JsonValueKind.Object) return Refuse("Operation", Texts.UnreadableResult);
                return Ok(w =>
                {
                    w.WritePropertyName("result");
                    parsed.RootElement.WriteTo(w);
                });
            }
        }

        /// <summary>
        /// What the job did, counted by the add-in (D-50). Only this chat's
        /// running job: one chat never reads another's.
        /// </summary>
        private string Changes(JsonElement root, string conversation)
        {
            var running = Running(root, conversation);
            if (running == null) return Refuse("Job", Texts.NoRunJob);
            var report = _host.Changes(Str(root, "job"));
            if (report == null) return Ok(w => w.WriteBoolean("counted", false));
            return Ok(w =>
            {
                w.WriteBoolean("counted", true);
                w.WriteNumber("added", report.Added);
                w.WriteNumber("modified", report.Modified);
                w.WriteNumber("erased", report.Erased);
                w.WriteStartArray("erasedHandles");
                foreach (var handle in report.ErasedHandles) w.WriteStringValue(handle);
                w.WriteEndArray();
            });
        }

        /// <summary>
        /// Anything a job erased is asked about, whatever Ask to Keep says
        /// (D-50): the server cannot let a chat approve its own delete. Only
        /// inside this chat's running job; anything but a clear "keep erased"
        /// brings the objects back. Decided here, not by the server: when the
        /// modeller turned the erase question off in Settings (only their click
        /// can, D-59), they stay erased unasked and the answer says so
        /// ("asked": false), so the chat cannot pass it off as the modeller's yes.
        /// </summary>
        private string AskErase(JsonElement root, string conversation)
        {
            var running = Running(root, conversation);
            if (running == null || running.Risk == Risk.Read || running.Risk == Risk.View) return Refuse("Job", Texts.NoRunJob);
            var report = _host.Changes(Str(root, "job"));
            if (report == null || report.Erased == 0) return Ok(w => { w.WriteString("answer", "nothing_erased"); w.WriteNumber("restored", 0); });
            var config = _config();
            if (!config.AskBeforeErasing)
            {
                return Ok(w =>
                {
                    w.WriteString("answer", "keep_erased");
                    w.WriteBoolean("asked", false);
                    // Who turned it off: the modeller's click, or this PC's administrator key (D-123).
                    w.WriteString("offBy", config.EraseQuestionOffByPolicy ? "policy" : "settings");
                    w.WriteNumber("erased", report.Erased);
                    w.WriteNumber("restored", 0);
                });
            }
            EraseAnswer answer;
            try
            {
                answer = _host.AskErase(new EraseRequest { Job = Str(root, "job"), Summary = Str(root, "summary"), Handles = report.AllErasedHandles });
            }
            catch (Exception ex)
            {
                answer = new EraseAnswer { Answer = "restored", Restored = 0, Message = "Heron in AutoCAD could not ask or put them back: " + ex.Message };
            }
            var said = answer?.Answer == "keep_erased" ? "keep_erased" : "restored";
            return Ok(w =>
            {
                w.WriteString("answer", said);
                w.WriteBoolean("asked", true);
                w.WriteNumber("erased", report.Erased);
                w.WriteNumber("restored", said == "restored" ? answer?.Restored ?? 0 : 0);
                if (!string.IsNullOrEmpty(answer?.Message)) w.WriteString("message", answer!.Message);
            });
        }

        /// <summary>For "undo Heron's last change" (D-54): did the modeller change anything since?</summary>
        private string SinceLast(JsonElement root, string conversation)
        {
            var running = Running(root, conversation);
            if (running == null) return Refuse("Job", Texts.NoRunJob);
            var before = _host.ChangedBefore(Str(root, "job"));
            return Ok(w =>
            {
                w.WriteBoolean("known", before.HasValue);
                w.WriteBoolean("changedSince", before ?? true);
            });
        }

        /// <summary>
        /// The boxes AutoCAD showed during this job that the dialog watch
        /// closed (D-66), so the chat is told. Only this chat's running job.
        /// </summary>
        private string Dialogs(JsonElement root, string conversation)
        {
            var running = Running(root, conversation);
            if (running == null) return Refuse("Job", Texts.NoRunJob);
            var notes = _host.Dialogs(Str(root, "job")) ?? new List<DialogNote>();
            return Ok(w =>
            {
                w.WriteStartArray("dialogs");
                foreach (var note in notes)
                {
                    if (note == null) continue;
                    w.WriteStartObject();
                    w.WriteString("title", note.Title);
                    w.WriteString("pressed", note.Pressed);
                    if (note.Closed.HasValue) w.WriteBoolean("closed", note.Closed.Value);
                    else w.WriteNull("closed");
                    if (note.Asked) w.WriteBoolean("asked", true);
                    w.WriteEndObject();
                }
                w.WriteEndArray();
            });
        }

        /// <summary>
        /// An Admin job of this chat names one button for one box it expects
        /// (#101). Any other level is refused: a named button may be Yes or OK.
        /// </summary>
        private string ExpectDialog(JsonElement root, string conversation)
        {
            var running = Running(root, conversation);
            if (running == null) return Refuse("Job", Texts.NoRunJob);
            if (running.Risk != Risk.Admin) return Refuse("Level", Texts.ExpectNeedsAdmin);
            var title = Str(root, "title");
            var button = Str(root, "button");
            if (string.IsNullOrWhiteSpace(title) || string.IsNullOrWhiteSpace(button)) return Refuse("BadRequest", Texts.ExpectNotTaken);
            bool taken;
            try
            {
                taken = _host.ExpectDialog(Str(root, "job"), title, button);
            }
            catch (Exception)
            {
                taken = false;
            }
            return taken ? Ok(null) : Refuse("Expect", Texts.ExpectNotTaken);
        }

        /// <summary>This chat's running job named in the request, or null.</summary>
        private RunningJob? Running(JsonElement root, string conversation)
        {
            RunningJob? running;
            lock (_running) _running.TryGetValue(Str(root, "job"), out running);
            return running != null && running.Conversation == conversation ? running : null;
        }

        private sealed class RunningJob
        {
            public RunningJob(string conversation, Risk risk, string drawing, long frontSeq)
            {
                Conversation = conversation;
                Risk = risk;
                Drawing = drawing;
                FrontSeq = frontSeq;
            }

            public string Conversation { get; }
            public Risk Risk { get; }
            public string Drawing { get; }
            /// <summary>The newest drawing event when the job began: only what came after counts.</summary>
            public long FrontSeq { get; }
        }

        private static string Str(JsonElement root, string name) =>
            root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";

        private static string Answer(string answer) => Ok(w => w.WriteString("answer", answer));

        private static string Refuse(string refusedBy, string message) => Write(w =>
        {
            w.WriteBoolean("ok", false);
            w.WriteString("refusedBy", refusedBy);
            w.WriteString("message", message);
        });

        /// <summary>
        /// Which padlocks are on and which a Windows policy holds (D-59, D-60),
        /// so a chat can say why a job would be refused before trying it. Read
        /// only: no request can change them.
        /// </summary>
        private static void WritePadlocks(Utf8JsonWriter w, HeronConfig config)
        {
            w.WriteStartObject("padlocks");
            w.WriteBoolean("changes", config.WriteEnabled);
            w.WriteBoolean("publish", config.PublishEnabled);
            w.WriteBoolean("admin", config.AdminEnabled);
            w.WriteBoolean("askToKeep", config.AskBeforeKeeping);
            w.WriteBoolean("eraseQuestion", config.AskBeforeErasing);
            w.WriteEndObject();
            w.WriteStartObject("held");
            w.WriteBoolean("changes", config.Held.Changes);
            w.WriteBoolean("publish", config.Held.Publish);
            w.WriteBoolean("admin", config.Held.Admin);
            w.WriteBoolean("eraseQuestionOff", config.Held.EraseQuestionOff);
            w.WriteEndObject();
        }

        private static string Ok(Action<Utf8JsonWriter>? more) => Write(w =>
        {
            w.WriteBoolean("ok", true);
            more?.Invoke(w);
        });

        private static string Write(Action<Utf8JsonWriter> body)
        {
            using (var stream = new MemoryStream())
            {
                using (var writer = new Utf8JsonWriter(stream))
                {
                    writer.WriteStartObject();
                    body(writer);
                    writer.WriteEndObject();
                }
                return Encoding.UTF8.GetString(stream.ToArray());
            }
        }
    }
}
