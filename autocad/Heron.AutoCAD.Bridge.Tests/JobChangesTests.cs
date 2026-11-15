using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>What a job really did, counted from AutoCAD's events, and the erase question (D-50).</summary>
public class JobChangesTests
{
    private readonly JobChanges _changes = new();

    [Fact]
    public void Added_modified_and_erased_are_counted_for_a_change_job()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.Appended("A1");
        _changes.Appended("A2");
        _changes.Modified("B1");
        _changes.Erased("C1", true);
        var report = _changes.Read("j1")!;
        Assert.Equal(2, report.Added);
        Assert.Equal(1, report.Modified);
        Assert.Equal(1, report.Erased);
        Assert.Equal(new[] { "C1" }, report.ErasedHandles);
    }

    [Theory]
    [InlineData(Risk.Read)]
    [InlineData(Risk.View)]
    public void A_read_or_view_job_is_not_counted(Risk risk)
    {
        _changes.Begin("j1", risk);
        Assert.False(_changes.Counting);
        _changes.Erased("C1", true);
        Assert.Null(_changes.Read("j1"));
    }

    [Fact]
    public void A_scratch_object_made_and_erased_in_the_job_is_neither()
    {
        _changes.Begin("j1", Risk.Admin);
        _changes.Appended("T1");
        _changes.Modified("T1");
        _changes.Erased("T1", true);
        var report = _changes.Read("j1")!;
        Assert.Equal(0, report.Added);
        Assert.Equal(0, report.Modified);
        Assert.Equal(0, report.Erased);
    }

    [Fact]
    public void An_object_brought_back_is_no_longer_erased()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.Erased("C1", true);
        _changes.Erased("C1", false);
        Assert.Equal(0, _changes.Read("j1")!.Erased);
    }

    [Fact]
    public void An_erased_object_is_not_also_counted_as_modified()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.Modified("C1");
        _changes.Erased("C1", true);
        _changes.Modified("C1");
        var report = _changes.Read("j1")!;
        Assert.Equal(0, report.Modified);
        Assert.Equal(1, report.Erased);
    }

    [Fact]
    public void Nothing_is_counted_outside_a_job_and_the_count_stays_readable_after_its_end()
    {
        _changes.Erased("X", true);
        _changes.Begin("j1", Risk.Change);
        _changes.Erased("C1", true);
        _changes.End("j1");
        _changes.Erased("C2", true);
        var report = _changes.Read("j1")!;
        Assert.Equal(new[] { "C1" }, report.AllErasedHandles);
        Assert.Null(_changes.Read("j2"));
    }

    [Fact]
    public void A_big_erase_is_counted_whole_but_named_in_part()
    {
        _changes.Begin("j1", Risk.Admin);
        for (var i = 0; i < 500; i++) _changes.Erased(i.ToString("X"), true);
        var report = _changes.Read("j1")!;
        Assert.Equal(500, report.Erased);
        Assert.Equal(JobChanges.MostHandles, report.ErasedHandles.Length);
        Assert.Equal(500, report.AllErasedHandles.Length);
    }
}

public class EraseProtocolTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly HeronConfig _config = new() { WriteEnabled = true, AdminEnabled = true };
    private readonly BridgeProtocol _protocol;

    public EraseProtocolTests() =>
        _protocol = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => new DateTime(2026, 11, 15, 9, 0, 0, DateTimeKind.Utc));

    private JsonElement Send(object request) => JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    private void Begin(string risk, string conversation = "chat-a") => Assert.True(Send(new
    {
        op = "begin", token = Token, client = "pc", conversation, job = "j1",
        tool = "autocad_send_command", risk, summary = "Send AutoCAD Command", drawing = @"C:\a.dwg",
    }).GetProperty("ok").GetBoolean());

    [Fact]
    public void Changes_reports_the_count()
    {
        Begin("admin");
        _host.Report = new ChangeReport { Added = 3, Modified = 1, Erased = 2, ErasedHandles = new[] { "A", "B" } };
        var reply = Send(new { op = "changes", token = Token, conversation = "chat-a", job = "j1" });
        Assert.True(reply.GetProperty("counted").GetBoolean());
        Assert.Equal(3, reply.GetProperty("added").GetInt32());
        Assert.Equal(2, reply.GetProperty("erased").GetInt32());
        Assert.Equal(2, reply.GetProperty("erasedHandles").GetArrayLength());
    }

    [Fact]
    public void Another_chat_never_reads_a_jobs_changes()
    {
        Begin("admin");
        var reply = Send(new { op = "changes", token = Token, conversation = "chat-b", job = "j1" });
        Assert.False(reply.GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void An_erase_is_asked_and_anything_but_keep_brings_them_back()
    {
        Begin("change");
        _host.Report = new ChangeReport { Erased = 2, ErasedHandles = new[] { "A", "B" }, AllErasedHandles = new[] { "A", "B" } };
        _host.EraseReply = new EraseAnswer { Answer = "something odd", Restored = 2 };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "Send AutoCAD Command" });
        Assert.Equal("restored", reply.GetProperty("answer").GetString());
        Assert.Equal(2, reply.GetProperty("restored").GetInt32());
        Assert.Equal(new[] { "A", "B" }, _host.EraseAsked[0].Handles);
    }

    [Fact]
    public void Keep_erased_is_kept()
    {
        Begin("change");
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "A" } };
        _host.EraseReply = new EraseAnswer { Answer = "keep_erased" };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x" });
        Assert.Equal("keep_erased", reply.GetProperty("answer").GetString());
        Assert.Equal(0, reply.GetProperty("restored").GetInt32());
    }

    [Fact]
    public void Nothing_erased_asks_nothing()
    {
        Begin("change");
        _host.Report = new ChangeReport { Added = 4 };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x" });
        Assert.Equal("nothing_erased", reply.GetProperty("answer").GetString());
        Assert.Empty(_host.EraseAsked);
    }

    [Fact]
    public void A_read_job_cannot_ask_to_erase()
    {
        Begin("read");
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "A" } };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x" });
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Empty(_host.EraseAsked);
    }
}

/// <summary>The emergency stop (HERONSTOP, D-51).</summary>
public class StopTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly HeronConfig _config = new() { WriteEnabled = true, AdminEnabled = true };
    private readonly BridgeProtocol _protocol;

    public StopTests() =>
        _protocol = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => new DateTime(2026, 11, 15, 9, 0, 0, DateTimeKind.Utc));

    private JsonElement Send(object request) => JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    private JsonElement Begin(string job = "j1") => Send(new
    {
        op = "begin", token = Token, client = "pc", conversation = "chat-a", job,
        tool = "autocad_batch_draw", risk = "change", summary = "Batch", drawing = @"C:\a.dwg",
    });

    [Fact]
    public void A_stop_refuses_new_jobs_until_it_is_lifted()
    {
        _protocol.Stop();
        var reply = Begin();
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal("Stopped", reply.GetProperty("refusedBy").GetString());
        Assert.Empty(_host.Begun);
        _protocol.Resume();
        Assert.True(Begin().GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void A_running_job_stops_at_its_next_request_but_can_still_finish_cleanly()
    {
        Assert.True(Begin().GetProperty("ok").GetBoolean());
        _protocol.Stop();
        var quiet = Send(new { op = "send_quiet", token = Token, conversation = "chat-a", job = "j1", lines = new[] { "(princ)" } });
        Assert.Equal("Stopped", quiet.GetProperty("refusedBy").GetString());
        Assert.Empty(_host.Quiet);
        var run = Send(new { op = "run", token = Token, conversation = "chat-a", job = "j1", operation = "loft", args = new { } });
        Assert.Equal("Stopped", run.GetProperty("refusedBy").GetString());
        // Counting, the erase question and the end still answer.
        Assert.True(Send(new { op = "changes", token = Token, conversation = "chat-a", job = "j1" }).GetProperty("ok").GetBoolean());
        Assert.True(Send(new { op = "end", token = Token, conversation = "chat-a", job = "j1", ok = false, outcome = "failed", summary = "Batch", ms = 5 }).GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void Ping_says_whether_Heron_is_stopped()
    {
        Assert.False(Send(new { op = "ping", token = Token, conversation = "chat-a" }).GetProperty("stopped").GetBoolean());
        _protocol.Stop();
        Assert.True(Send(new { op = "ping", token = Token, conversation = "chat-a" }).GetProperty("stopped").GetBoolean());
    }
}
