using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

public class IdentityTests
{
    [Fact]
    public void Token_is_24_random_bytes()
    {
        var a = BridgeIdentity.MintToken();
        var b = BridgeIdentity.MintToken();
        Assert.Equal(24, Convert.FromBase64String(a).Length);
        Assert.NotEqual(a, b);
    }

    [Fact]
    public void Token_compare()
    {
        Assert.True(BridgeIdentity.TokenEquals("abc", "abc"));
        Assert.False(BridgeIdentity.TokenEquals("abc", "abd"));
        Assert.False(BridgeIdentity.TokenEquals("abc", null));
        Assert.False(BridgeIdentity.TokenEquals(null, null));
    }
}

public class ConfigTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "heron-cfg-" + Guid.NewGuid().ToString("N"));
    private string PathOf(string name) => System.IO.Path.Combine(_dir, name);

    public ConfigTests() => Directory.CreateDirectory(_dir);
    public void Dispose() => Directory.Delete(_dir, true);

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("{")]
    [InlineData("[1,2]")]
    [InlineData("{\"write.enabled\": \"yes\"}")]
    public void Unreadable_config_keeps_every_padlock_off(string? content)
    {
        var path = PathOf("heron-autocad.config");
        if (content != null) File.WriteAllText(path, content);
        var config = HeronConfig.Load(path);
        Assert.False(config.WriteEnabled);
        Assert.False(config.PublishEnabled);
        Assert.False(config.AdminEnabled);
        Assert.False(config.AskBeforeKeeping);
        Assert.False(config.AutoConnect);
    }

    [Fact]
    public void Defaults_show_the_banner()
    {
        Assert.True(HeronConfig.Load(PathOf("missing.config")).ActivityBanner);
    }

    [Fact]
    public void Save_and_load_round_trip()
    {
        var path = PathOf("sub/heron-autocad.config");
        var config = HeronConfig.Load(path);
        config.WriteEnabled = true;
        config.AskBeforeKeeping = true;
        config.Save(path);
        var again = HeronConfig.Load(path);
        Assert.True(again.WriteEnabled);
        Assert.True(again.AskBeforeKeeping);
        Assert.False(again.AdminEnabled);
        Assert.Contains("\"write.enabled\": true", File.ReadAllText(path));
    }
}

public class PermissionTests
{
    private static HeronConfig Config(bool write = false, bool publish = false, bool admin = false) =>
        new() { WriteEnabled = write, PublishEnabled = publish, AdminEnabled = admin };

    [Theory]
    [InlineData(Risk.Read)]
    [InlineData(Risk.View)]
    public void Reading_and_viewing_need_no_padlock(Risk risk)
    {
        Assert.Null(Permissions.Refusal(risk, Config()));
    }

    [Fact]
    public void Change_needs_Changes()
    {
        Assert.Equal("Changes", Permissions.Refusal(Risk.Change, Config())!.RefusedBy);
        Assert.Null(Permissions.Refusal(Risk.Change, Config(write: true)));
    }

    [Fact]
    public void Publish_needs_Changes_and_Publish()
    {
        Assert.Equal("Changes", Permissions.Refusal(Risk.Publish, Config(publish: true))!.RefusedBy);
        Assert.Equal("Publish", Permissions.Refusal(Risk.Publish, Config(write: true))!.RefusedBy);
        Assert.Null(Permissions.Refusal(Risk.Publish, Config(write: true, publish: true)));
    }

    [Fact]
    public void Admin_needs_Changes_and_Admin()
    {
        Assert.Equal("Admin", Permissions.Refusal(Risk.Admin, Config(write: true))!.RefusedBy);
        Assert.Null(Permissions.Refusal(Risk.Admin, Config(write: true, admin: true)));
    }

    [Fact]
    public void Refusal_texts_name_the_padlock_and_say_nothing_was_sent()
    {
        var refusal = Permissions.Refusal(Risk.Change, Config())!;
        Assert.Equal(Texts.ChangesOff, refusal.Message);
        Assert.Contains("HERONCHANGES", refusal.Message);
        Assert.EndsWith(Texts.NothingSent, refusal.Message);
        Assert.EndsWith(Texts.NothingSent, Texts.PublishOff);
        Assert.EndsWith(Texts.NothingSent, Texts.AdminOff);
    }
}

public class HoldTests
{
    private static readonly DateTime T0 = new(2026, 10, 26, 12, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void Second_chat_is_refused_until_the_first_goes_quiet()
    {
        var hold = new HeronHold();
        Assert.True(hold.TryTake("chat-a", T0));
        Assert.False(hold.TryTake("chat-b", T0.AddMinutes(1)));
        Assert.True(hold.TryTake("chat-a", T0.AddMinutes(2)));
        Assert.False(hold.TryTake("chat-b", T0.AddMinutes(4.9)));
        Assert.True(hold.TryTake("chat-b", T0.AddMinutes(5.1)));
    }

    [Fact]
    public void Release_frees_the_hold()
    {
        var hold = new HeronHold();
        hold.TryTake("chat-a", T0);
        hold.Release("chat-a");
        Assert.True(hold.TryTake("chat-b", T0));
    }

    [Fact]
    public void Free_lets_another_chat_in_at_once_whoever_holds_it()
    {
        var hold = new HeronHold();
        hold.TryTake("chat-a", T0);
        Assert.Equal(HoldFree.Freed, hold.Free());
        Assert.Null(hold.Holder);
        Assert.True(hold.TryTake("chat-b", T0.AddSeconds(1)));
    }

    [Fact]
    public void Free_says_when_nothing_was_held()
    {
        Assert.Equal(HoldFree.NothingHeld, new HeronHold().Free());
    }

    [Fact]
    public void Free_waits_while_an_operation_is_running()
    {
        var hold = new HeronHold();
        hold.TryPin("chat-a", T0);
        Assert.Equal(HoldFree.Busy, hold.Free());
        Assert.Equal("chat-a", hold.Holder);
        hold.Unpin(T0.AddSeconds(5));
        Assert.Equal(HoldFree.Freed, hold.Free());
    }
}

public class FakeHost : IJobHost
{
    public List<JobInfo> Begun { get; } = new();
    public List<JobEnd> Ended { get; } = new();
    public List<KeepRequest> Asked { get; } = new();
    public string Answer { get; set; } = "keep";

    public void Begin(JobInfo job) => Begun.Add(job);
    public void End(JobEnd end) => Ended.Add(end);
    public string AskKeep(KeepRequest request)
    {
        Asked.Add(request);
        return Answer;
    }

    public List<string[]> Quiet { get; } = new();
    public void SendQuiet(string[] lines) => Quiet.Add(lines);

    public List<RunRequest> Runs { get; } = new();
    public RunResult RunAnswer { get; set; } = RunResult.Done(null);
    public Func<RunRequest, RunResult>? OnRun { get; set; }
    public RunResult Run(RunRequest request)
    {
        Runs.Add(request);
        return OnRun != null ? OnRun(request) : RunAnswer;
    }
}

public class ProtocolTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly HeronConfig _config = new();
    private DateTime _now = new(2026, 10, 26, 12, 0, 0, DateTimeKind.Utc);
    private readonly BridgeProtocol _protocol;

    public ProtocolTests() =>
        _protocol = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => _now);

    private JsonElement Send(object request)
    {
        var reply = _protocol.Handle(JsonSerializer.Serialize(request));
        return JsonDocument.Parse(reply).RootElement;
    }

    private static object Begin(string risk, string conversation = "chat-a", string token = Token) => new
    {
        op = "begin", token, client = "pc", conversation, job = "j1",
        tool = "autocad_draw_line", risk, summary = "Draw Line", drawing = @"C:\a.dwg",
    };

    [Fact]
    public void Wrong_token_is_refused()
    {
        var reply = Send(Begin("read", token: "old"));
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal(Texts.WrongSession, reply.GetProperty("message").GetString());
        Assert.Empty(_host.Begun);
    }

    [Fact]
    public void Unknown_op_is_refused()
    {
        var reply = Send(new { op = "explode", token = Token, conversation = "c" });
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.EndsWith(Texts.NothingSent, reply.GetProperty("message").GetString());
    }

    [Fact]
    public void Garbage_line_is_refused_not_thrown()
    {
        var reply = JsonDocument.Parse(_protocol.Handle("not json")).RootElement;
        Assert.False(reply.GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void Read_begins_and_shows_the_banner()
    {
        var reply = Send(Begin("read"));
        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.Equal(Risk.Read, Assert.Single(_host.Begun).Risk);
    }

    [Fact]
    public void Change_with_Changes_off_is_refused_and_names_the_padlock()
    {
        var reply = Send(Begin("change"));
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal("Changes", reply.GetProperty("refusedBy").GetString());
        Assert.Equal(Texts.ChangesOff, reply.GetProperty("message").GetString());
        Assert.Empty(_host.Begun);
    }

    [Fact]
    public void Unknown_risk_is_refused()
    {
        var reply = Send(Begin("whatever"));
        Assert.False(reply.GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void Another_chat_is_refused_with_the_hold_text()
    {
        Send(Begin("read", "chat-a"));
        var reply = Send(Begin("read", "chat-b"));
        Assert.Equal(Texts.InUse, reply.GetProperty("message").GetString());
    }

    [Fact]
    public void End_reaches_the_host()
    {
        Send(Begin("read"));
        var reply = Send(new { op = "end", token = Token, conversation = "chat-a", job = "j1", ok = true, outcome = "done", summary = "Draw Line", ms = 412 });
        Assert.True(reply.GetProperty("ok").GetBoolean());
        var end = Assert.Single(_host.Ended);
        Assert.Equal(412, end.Ms);
        Assert.True(end.Ok);
    }

    private object Ask(string conversation = "chat-a") => new
    {
        op = "ask_keep", token = Token, conversation, job = "j1", summary = "Draw Line", handles = new[] { "2A" },
    };

    [Fact]
    public void Ask_to_keep_off_answers_keep_without_asking()
    {
        Assert.Equal("keep", Send(Ask()).GetProperty("answer").GetString());
        Assert.Empty(_host.Asked);
    }

    [Fact]
    public void Ask_to_keep_on_asks_the_modeller()
    {
        _config.AskBeforeKeeping = true;
        _host.Answer = "discard";
        Assert.Equal("discard", Send(Ask()).GetProperty("answer").GetString());
        Assert.Equal(new[] { "2A" }, Assert.Single(_host.Asked).Handles);
    }

    [Fact]
    public void Keep_rest_of_job_stops_asking_until_ten_quiet_minutes()
    {
        _config.AskBeforeKeeping = true;
        _host.Answer = "keep_rest";
        Send(Ask());
        _now = _now.AddMinutes(9);
        Assert.Equal("keep", Send(Ask()).GetProperty("answer").GetString());
        Assert.Single(_host.Asked);
        _now = _now.AddMinutes(11);
        _host.Answer = "keep";
        Send(Ask());
        Assert.Equal(2, _host.Asked.Count);
    }

    [Fact]
    public void Ping_needs_no_hold()
    {
        Send(Begin("read", "chat-a"));
        var reply = Send(new { op = "ping", token = Token, conversation = "chat-b" });
        Assert.True(reply.GetProperty("ok").GetBoolean());
    }
}

public class ServerTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "heron-srv-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        if (Directory.Exists(_dir)) Directory.Delete(_dir, true);
    }

    [Fact]
    public void Start_publishes_an_address_and_answers_ping_then_Stop_removes_it()
    {
        var server = new BridgeServer(new FakeHost(), () => new HeronConfig(), "26.0", "1.0.0", _dir,
            "heron.autocad.test." + Guid.NewGuid().ToString("N"));
        server.Start();
        Assert.True(server.IsRunning);
        var address = JsonDocument.Parse(File.ReadAllText(server.AddressPath)).RootElement;
        Assert.Equal(server.PipeName, address.GetProperty("pipeName").GetString());
        Assert.Equal(System.Diagnostics.Process.GetCurrentProcess().Id, address.GetProperty("pid").GetInt32());
        Assert.Equal(1, address.GetProperty("protocolVersion").GetInt32());
        var token = address.GetProperty("token").GetString();

        using (var client = new NamedPipeClientStream(".", server.PipeName, PipeDirection.InOut))
        {
            client.Connect(5000);
            var line = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { op = "ping", token, conversation = "c" }) + "\n");
            client.Write(line, 0, line.Length);
            using var reader = new StreamReader(client, Encoding.UTF8);
            var reply = JsonDocument.Parse(reader.ReadLine()!).RootElement;
            Assert.True(reply.GetProperty("ok").GetBoolean());
        }

        server.Stop();
        Assert.False(server.IsRunning);
        Assert.False(File.Exists(server.AddressPath));
    }

    [Fact]
    public void A_new_connect_mints_a_new_token()
    {
        var server = new BridgeServer(new FakeHost(), () => new HeronConfig(), "26.0", "1.0.0", _dir,
            "heron.autocad.test." + Guid.NewGuid().ToString("N"));
        server.Start();
        var first = server.Token;
        server.Stop();
        server.Start();
        Assert.NotEqual(first, server.Token);
        server.Stop();
    }
}

public class CrossLanguageTests : IDisposable
{
    private readonly string _home = Path.Combine(Path.GetTempPath(), "heron-x-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        if (Directory.Exists(_home)) Directory.Delete(_home, true);
    }

    private static string? RepoPython()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null && !File.Exists(Path.Combine(dir.FullName, "pyproject.toml"))) dir = dir.Parent;
        if (dir == null) return null;
        var python = Path.Combine(dir.FullName, ".venv", "Scripts", "python.exe");
        return File.Exists(python) ? python : null;
    }

    [Fact]
    public void Python_client_and_csharp_server_understand_each_other()
    {
        var python = RepoPython();
        if (python == null) return; // CI without the repo's venv: covered by each side's own tests

        var host = new FakeHost();
        var config = new HeronConfig();
        var folder = Path.Combine(_home, "Heron", "autocad", "bridges");
        var server = new BridgeServer(host, () => config, "26.0", "1.0.0", folder,
            "heron.autocad.test." + Guid.NewGuid().ToString("N"));
        server.Start();
        try
        {
            var script =
                "import os, json\n" +
                "from autocad_mcp.core.bridge import Bridge, BridgeRefused\n" +
                "b = Bridge(int(os.environ['HERON_TEST_PID']))\n" +
                "out = {}\n" +
                "out['read'] = bool(b.begin('autocad_list_layers', 'read', 'List Layers', 'a.dwg'))\n" +
                "try:\n    b.begin('autocad_draw_line', 'change', 'Draw Line', 'a.dwg'); out['change'] = 'allowed'\n" +
                "except BridgeRefused as e:\n    out['change'] = str(e)\n" +
                "b.end('j', True, 'done', 'List Layers', 12)\n" +
                "out['keep'] = b.ask_keep('j', 'Draw Line', ['2A'])\n" +
                "print(json.dumps(out))\n";
            var start = new System.Diagnostics.ProcessStartInfo(python, "-c \"" + script.Replace("\"", "\\\"") + "\"")
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
            };
            start.Environment["LOCALAPPDATA"] = _home;
            start.Environment["HERON_TEST_PID"] = System.Diagnostics.Process.GetCurrentProcess().Id.ToString();
            using var process = System.Diagnostics.Process.Start(start)!;
            var stdout = process.StandardOutput.ReadToEnd();
            var stderr = process.StandardError.ReadToEnd();
            Assert.True(process.WaitForExit(30000));
            Assert.True(process.ExitCode == 0, stderr);

            var result = JsonDocument.Parse(stdout).RootElement;
            Assert.True(result.GetProperty("read").GetBoolean());
            Assert.Equal(Texts.ChangesOff, result.GetProperty("change").GetString());
            Assert.Equal("keep", result.GetProperty("keep").GetString());
            Assert.Equal("autocad_list_layers", Assert.Single(host.Begun).Tool);
            Assert.Equal(12, Assert.Single(host.Ended).Ms);
        }
        finally
        {
            server.Stop();
        }
    }
}

public class AskToKeepFlagTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly HeronConfig _config = new() { WriteEnabled = true };
    private readonly BridgeProtocol _protocol;

    public AskToKeepFlagTests() =>
        _protocol = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => DateTime.UtcNow);

    private JsonElement Send(object request) => JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    private bool BeginAsks() => Send(new
    {
        op = "begin", token = Token, conversation = "chat-a", job = "j", tool = "autocad_draw_line",
        risk = "change", summary = "Draw Line", drawing = "a.dwg",
    }).GetProperty("askToKeep").GetBoolean();

    [Fact]
    public void Begin_says_no_when_Ask_to_Keep_is_off() => Assert.False(BeginAsks());

    [Fact]
    public void Begin_says_yes_when_Ask_to_Keep_is_on()
    {
        _config.AskBeforeKeeping = true;
        Assert.True(BeginAsks());
    }

    [Fact]
    public void Begin_says_no_while_keep_the_rest_holds()
    {
        _config.AskBeforeKeeping = true;
        _host.Answer = "keep_rest";
        Send(new { op = "ask_keep", token = Token, conversation = "chat-a", job = "j", summary = "s", handles = new[] { "2A" } });
        Assert.False(BeginAsks());
    }
}

public class OneShotWorkTests
{
    [Fact]
    public void Work_that_runs_in_time_gives_its_result()
    {
        var work = new OneShotWork<string>(() => "keep");
        new Thread(work.Run).Start();
        Assert.True(work.Wait(TimeSpan.FromSeconds(5), out var answer));
        Assert.Equal("keep", answer);
    }

    [Fact]
    public void Work_abandoned_before_it_starts_never_runs()
    {
        var ran = false;
        var work = new OneShotWork<string>(() => { ran = true; return "keep"; });
        Assert.False(work.Wait(TimeSpan.FromMilliseconds(50), out _));
        work.Run(); // the main thread gets to it late
        Assert.False(ran);
    }

    [Fact]
    public void Work_that_throws_is_not_a_result()
    {
        var work = new OneShotWork<string>(() => throw new InvalidOperationException("box failed"));
        work.Run();
        Assert.False(work.Wait(TimeSpan.FromSeconds(1), out _));
        Assert.IsType<InvalidOperationException>(work.Error);
    }
}

public class RepeatClickFilterTests
{
    private static readonly DateTime T0 = new(2026, 10, 26, 12, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void Double_click_counts_once()
    {
        var filter = new RepeatClickFilter();
        Assert.True(filter.Accept("Changes", T0));
        Assert.False(filter.Accept("Changes", T0.AddMilliseconds(460)));
    }

    [Fact]
    public void A_slow_double_click_counts_once_too()
    {
        // Measured live on 2026-10-26: 856 ms between the two clicks.
        var filter = new RepeatClickFilter();
        Assert.True(filter.Accept("Admin", T0));
        Assert.False(filter.Accept("Admin", T0.AddMilliseconds(856)));
    }

    [Fact]
    public void A_later_click_counts_again()
    {
        var filter = new RepeatClickFilter();
        filter.Accept("Changes", T0);
        Assert.True(filter.Accept("Changes", T0.AddMilliseconds(2000)));
    }

    [Fact]
    public void Different_buttons_never_block_each_other()
    {
        var filter = new RepeatClickFilter();
        filter.Accept("Changes", T0);
        Assert.True(filter.Accept("Publish", T0.AddMilliseconds(100)));
    }
}

public class QuietSendTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly HeronConfig _config = new() { WriteEnabled = true };
    private readonly BridgeProtocol _protocol;

    public QuietSendTests() =>
        _protocol = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => DateTime.UtcNow);

    private JsonElement Send(object request) => JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    private void Begin(string risk, string job = "j1", string conversation = "chat-a") => Send(new
    {
        op = "begin", token = Token, conversation, job, tool = "autocad_batch_draw", risk, summary = "Batch", drawing = "a.dwg",
    });

    private JsonElement Quiet(string job = "j1", string conversation = "chat-a") =>
        Send(new { op = "send_quiet", token = Token, conversation, job, lines = new[] { "(progn 1)", "(progn 2)" } });

    [Fact]
    public void Refused_without_a_running_job()
    {
        Assert.False(Quiet().GetProperty("ok").GetBoolean());
        Assert.Empty(_host.Quiet);
    }

    [Fact]
    public void Refused_inside_a_read_job()
    {
        Begin("read");
        Assert.False(Quiet().GetProperty("ok").GetBoolean());
        Assert.Empty(_host.Quiet);
    }

    [Fact]
    public void Delivered_in_order_inside_a_change_job()
    {
        Begin("change");
        Assert.True(Quiet().GetProperty("ok").GetBoolean());
        Assert.Equal(new[] { "(progn 1)", "(progn 2)" }, Assert.Single(_host.Quiet));
    }

    [Fact]
    public void Refused_for_another_chats_job()
    {
        Begin("change");
        Assert.False(Quiet(conversation: "chat-b").GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void Refused_after_the_job_ended()
    {
        Begin("change");
        Send(new { op = "end", token = Token, conversation = "chat-a", job = "j1", ok = true, outcome = "done", summary = "Batch", ms = 5 });
        Assert.False(Quiet().GetProperty("ok").GetBoolean());
    }
}

/// <summary>
/// A drawing's undo history, as far as these tests need it: every write while
/// recording is on is one Ctrl+Z.
/// </summary>
public class FakeUndo
{
    public bool Recording { get; set; } = true;
    public List<string> Steps { get; } = new();
    public int Pauses { get; private set; }
    public int Resumes { get; private set; }

    public void Write(string what)
    {
        if (Recording) Steps.Add(what);
    }

    public bool Pause()
    {
        if (!Recording) return false;
        Recording = false;
        Pauses++;
        return true;
    }

    public void Resume()
    {
        Recording = true;
        Resumes++;
    }
}

public class UndoPauseTests
{
    private readonly FakeUndo _undo = new();
    private readonly UndoPause _pause;

    public UndoPauseTests() => _pause = new UndoPause(_undo.Pause, _undo.Resume);

    private static JobInfo Job(string id, Risk risk) => new() { Job = id, Risk = risk, Tool = "autocad_x" };

    [Fact]
    public void A_read_job_turns_recording_off_and_its_end_turns_it_back_on()
    {
        _pause.Begin(Job("j1", Risk.Read));
        Assert.False(_undo.Recording);
        Assert.Equal("j1", _pause.PausedFor);
        _pause.End("j1");
        Assert.True(_undo.Recording);
        Assert.Null(_pause.PausedFor);
    }

    [Theory]
    [InlineData(Risk.View)]
    [InlineData(Risk.Change)]
    [InlineData(Risk.Publish)]
    [InlineData(Risk.Admin)]
    public void Every_other_job_keeps_recording_on(Risk risk)
    {
        _pause.Begin(Job("j1", risk));
        Assert.True(_undo.Recording);
        Assert.Equal(0, _undo.Pauses);
        _pause.End("j1");
        Assert.Equal(0, _undo.Resumes);
    }

    [Fact]
    public void A_lost_end_is_put_right_by_the_next_begin()
    {
        _pause.Begin(Job("read", Risk.Read));
        // The server died before "end": the next job must not draw unrecorded.
        _pause.Begin(Job("draw", Risk.Change));
        Assert.True(_undo.Recording);
        Assert.Equal(1, _undo.Resumes);
    }

    [Fact]
    public void The_end_of_another_job_does_not_turn_it_back_on()
    {
        _pause.Begin(Job("j2", Risk.Read));
        _pause.End("j1");
        Assert.False(_undo.Recording);
    }

    [Fact]
    public void Undo_the_modeller_turned_off_stays_off()
    {
        // UNDO Control None: nothing was paused, so nothing is turned on.
        _undo.Recording = false;
        _pause.Begin(Job("j1", Risk.Read));
        _pause.End("j1");
        Assert.False(_undo.Recording);
        Assert.Equal(0, _undo.Resumes);
    }

    [Fact]
    public void An_end_sent_twice_resumes_once()
    {
        _pause.Begin(Job("j1", Risk.Read));
        _pause.End("j1");
        _pause.End("j1");
        Assert.Equal(1, _undo.Resumes);
    }

    [Fact]
    public void Two_reads_in_a_row_each_pause_and_resume()
    {
        _pause.Begin(Job("j1", Risk.Read));
        _pause.End("j1");
        _pause.Begin(Job("j2", Risk.Read));
        Assert.False(_undo.Recording);
        _pause.End("j2");
        Assert.True(_undo.Recording);
        Assert.Equal(2, _undo.Pauses);
        Assert.Equal(2, _undo.Resumes);
    }
}

/// <summary>Live check A30, offline: a batch, then Claude looks, then one Ctrl+Z.</summary>
public class ReadLeavesNoUndoStepTests
{
    private const string Token = "tok";
    private readonly FakeUndo _undo = new();
    private readonly HeronConfig _config = new() { WriteEnabled = true };
    private readonly BridgeProtocol _protocol;

    private sealed class PausingHost : IJobHost
    {
        private readonly UndoPause _pause;
        public PausingHost(UndoPause pause) => _pause = pause;
        public void Begin(JobInfo job) => _pause.Begin(job);
        public void End(JobEnd end) => _pause.End(end.Job);
        public string AskKeep(KeepRequest request) => "keep";
        public void SendQuiet(string[] lines) { }
        public RunResult Run(RunRequest request) => RunResult.Done(null);
    }

    public ReadLeavesNoUndoStepTests() =>
        _protocol = new BridgeProtocol(
            new PausingHost(new UndoPause(_undo.Pause, _undo.Resume)), () => _config, Token, new HeronHold(), () => DateTime.UtcNow);

    private bool Send(object request) =>
        JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement.GetProperty("ok").GetBoolean();

    /// <summary>One tool call through begin and end, with the COM writes it makes in between.</summary>
    private void Call(string job, string tool, string risk, params string[] writes)
    {
        Assert.True(Send(new { op = "begin", token = Token, conversation = "chat-a", job, tool, risk, summary = tool, drawing = "a.dwg" }));
        foreach (var write in writes) _undo.Write(write);
        Assert.True(Send(new { op = "end", token = Token, conversation = "chat-a", job, ok = true, outcome = "done", summary = tool, ms = 200 }));
    }

    [Fact]
    public void One_ctrl_z_after_list_variable_and_preview_still_undoes_the_batch()
    {
        Call("j1", "autocad_batch_labels", "change", "15 labels (one undo group)");
        Call("j2", "autocad_list_entities", "read", "scratch selection set");
        Call("j3", "autocad_get_variable", "read");
        // What _plot_png does through COM, each write outside any undo group.
        Call("j4", "autocad_preview", "read",
            "add snapshot page setup", "snapshot CopyFrom", "ConfigName", "CanonicalMediaName",
            "PlotType", "UseStandardScale", "StandardScale", "CenterPlot",
            "layout CopyFrom snapshot", "delete snapshot");

        Assert.Equal("15 labels (one undo group)", _undo.Steps.Last());
        Assert.Single(_undo.Steps);
        Assert.True(_undo.Recording);
    }

    [Fact]
    public void A_change_after_a_read_is_still_its_own_undo_step()
    {
        Call("j1", "autocad_preview", "read", "ConfigName");
        Call("j2", "autocad_draw_line", "change", "line");
        Assert.Equal(new[] { "line" }, _undo.Steps);
    }

    [Fact]
    public void A_refused_begin_pauses_nothing()
    {
        _config.WriteEnabled = false;
        Assert.False(Send(new { op = "begin", token = Token, conversation = "chat-a", job = "j1", tool = "autocad_draw_line", risk = "change", summary = "x", drawing = "a.dwg" }));
        Assert.True(_undo.Recording);
        Assert.Equal(0, _undo.Pauses);
    }
}
