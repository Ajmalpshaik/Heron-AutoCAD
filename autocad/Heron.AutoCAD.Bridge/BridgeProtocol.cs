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
    /// Ops: ping, info, release, begin, end, ask_keep, send_quiet, run. Every
    /// op needs the session token. begin is where the hold and the padlocks are
    /// checked; send_quiet and run only work inside the job begin allowed.
    /// </summary>
    public sealed class BridgeProtocol
    {
        public const int Version = 1;
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

                try
                {
                    switch (op)
                    {
                        case "ping":
                            return Ok(w => w.WriteNumber("protocolVersion", Version));
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

        private string Begin(JsonElement root, string conversation)
        {
            if (!RiskNames.TryParse(Str(root, "risk"), out var risk)) return Refuse("Level", Texts.UnknownRisk);
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
            };
            lock (_running) _running[job.Job] = new RunningJob(conversation, risk, job.Drawing);
            try
            {
                _host.Begin(job);
            }
            catch (Exception)
            {
                // The banner is something to see, not a gate: a drawing glitch
                // must not stop a job the padlocks allowed.
            }
            return Ok(w => w.WriteBoolean("askToKeep", askToKeep));
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
            var lines = new List<string>();
            if (root.TryGetProperty("lines", out var list) && list.ValueKind == JsonValueKind.Array)
                foreach (var item in list.EnumerateArray())
                    if (item.ValueKind == JsonValueKind.String) lines.Add(item.GetString() ?? "");
            _host.SendQuiet(lines.ToArray());
            return Ok(null);
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

        /// <summary>This chat's running job named in the request, or null.</summary>
        private RunningJob? Running(JsonElement root, string conversation)
        {
            RunningJob? running;
            lock (_running) _running.TryGetValue(Str(root, "job"), out running);
            return running != null && running.Conversation == conversation ? running : null;
        }

        private sealed class RunningJob
        {
            public RunningJob(string conversation, Risk risk, string drawing)
            {
                Conversation = conversation;
                Risk = risk;
                Drawing = drawing;
            }

            public string Conversation { get; }
            public Risk Risk { get; }
            public string Drawing { get; }
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
