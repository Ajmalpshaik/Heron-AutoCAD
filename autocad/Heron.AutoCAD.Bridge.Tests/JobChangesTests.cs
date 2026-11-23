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
    public void A_whole_change_question_answers_undo_whole_for_anything_but_keep()
    {
        // D-136: a replace job (join, explode, a cut circle). The server undoes the whole job.
        Begin("change");
        _host.Report = new ChangeReport { Erased = 1, ErasedHandles = new[] { "B" }, AllErasedHandles = new[] { "B" } };
        _host.EraseReply = new EraseAnswer { Answer = "something odd", Restored = 1 };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "Join", whole = true });
        Assert.Equal(EraseWords.UndoWhole, reply.GetProperty("answer").GetString());
        Assert.Equal(0, reply.GetProperty("restored").GetInt32());
        Assert.True(_host.EraseAsked[0].Whole);
    }

    [Fact]
    public void A_whole_change_question_still_keeps_on_a_clear_keep()
    {
        Begin("change");
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "B" } };
        _host.EraseReply = new EraseAnswer { Answer = "keep_erased" };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "Join", whole = true });
        Assert.Equal("keep_erased", reply.GetProperty("answer").GetString());
    }

    [Theory]
    [InlineData(false)]
    [InlineData("true")] // only a JSON true counts
    public void Without_whole_the_question_is_the_usual_one(object whole)
    {
        Begin("change");
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "B" } };
        _host.EraseReply = new EraseAnswer { Answer = "restored", Restored = 1 };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x", whole });
        Assert.Equal("restored", reply.GetProperty("answer").GetString());
        Assert.False(_host.EraseAsked[0].Whole);
    }

    [Fact]
    public void A_whole_change_question_that_throws_is_still_undo_whole()
    {
        Begin("change");
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "B" } };
        _host.EraseThrows = true;
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "Join", whole = true });
        Assert.Equal(EraseWords.UndoWhole, reply.GetProperty("answer").GetString());
        Assert.Contains("could not ask", reply.GetProperty("message").GetString());
    }

    [Fact]
    public void With_the_erase_question_off_a_whole_change_is_kept_unasked_too()
    {
        Begin("change");
        _config.AskBeforeErasing = false;
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "B" } };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "Join", whole = true });
        Assert.Equal("keep_erased", reply.GetProperty("answer").GetString());
        Assert.False(reply.GetProperty("asked").GetBoolean());
        Assert.Empty(_host.EraseAsked);
    }

    [Fact]
    public void Keep_erased_is_kept()
    {
        Begin("change");
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "A" } };
        _host.EraseReply = new EraseAnswer { Answer = "keep_erased" };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x" });
        Assert.Equal("keep_erased", reply.GetProperty("answer").GetString());
        Assert.True(reply.GetProperty("asked").GetBoolean());
        Assert.Equal(0, reply.GetProperty("restored").GetInt32());
    }

    [Fact]
    public void With_the_erase_question_off_they_stay_erased_unasked_and_the_answer_says_so()
    {
        Begin("change");
        _config.AskBeforeErasing = false;
        _host.Report = new ChangeReport { Erased = 3, AllErasedHandles = new[] { "A", "B", "C" } };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x" });
        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.Equal("keep_erased", reply.GetProperty("answer").GetString());
        Assert.False(reply.GetProperty("asked").GetBoolean());
        Assert.Equal("settings", reply.GetProperty("offBy").GetString());
        Assert.Equal(3, reply.GetProperty("erased").GetInt32());
        Assert.Equal(0, reply.GetProperty("restored").GetInt32());
        Assert.Empty(_host.EraseAsked); // no box
    }

    [Fact]
    public void Off_by_the_administrator_key_the_answer_says_policy()
    {
        Begin("change");
        _config.AskBeforeErasing = false;
        _config.EraseQuestionOffByPolicy = true;
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "A" } };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x" });
        Assert.Equal("policy", reply.GetProperty("offBy").GetString());
        Assert.Empty(_host.EraseAsked);
    }

    [Fact]
    public void With_the_erase_question_off_a_read_job_still_cannot_ask_to_erase()
    {
        Begin("read");
        _config.AskBeforeErasing = false;
        _host.Report = new ChangeReport { Erased = 1, AllErasedHandles = new[] { "A" } };
        var reply = Send(new { op = "ask_erase", token = Token, conversation = "chat-a", job = "j1", summary = "x" });
        Assert.False(reply.GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void The_erase_question_is_on_unless_turned_off()
    {
        Assert.True(new HeronConfig().AskBeforeErasing);
        Assert.True(HeronConfig.Load(System.IO.Path.Combine(System.IO.Path.GetTempPath(), "no-such-heron.config")).AskBeforeErasing);
    }

    [Fact]
    public void No_file_can_turn_the_erase_question_off()
    {
        // D-59: a chat that can write a file must not approve its own deletes.
        var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "heron-erase-" + Guid.NewGuid().ToString("N") + ".config");
        try
        {
            System.IO.File.WriteAllText(path, "{\"erase.ask\": false, \"eraseQuestion\": false, \"write.askBeforeErasing\": false}");
            Assert.True(HeronConfig.Load(path).AskBeforeErasing);
            Assert.True(new HeronPadlocks(new FakePolicy()).Snapshot(new HeronConfig { AskBeforeErasing = false }).AskBeforeErasing);
        }
        finally
        {
            System.IO.File.Delete(path);
        }
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

    [Fact]
    public void A_stopped_job_is_refused_a_named_button_for_a_box()
    {
        // #210: HERONSTOP also stops expect_dialog, so a stopped job cannot arm the dialog watch.
        Assert.True(Send(new
        {
            op = "begin", token = Token, client = "pc", conversation = "chat-a", job = "j1",
            tool = "autocad_run_lisp", risk = "admin", summary = "Run LISP", drawing = @"C:\a.dwg",
        }).GetProperty("ok").GetBoolean());
        var before = Send(new { op = "expect_dialog", token = Token, conversation = "chat-a", job = "j1", title = "Purge - Confirm Purge", button = "Yes" });
        Assert.True(before.GetProperty("ok").GetBoolean());
        Assert.Single(_host.Expected);
        _protocol.Stop();
        var stopped = Send(new { op = "expect_dialog", token = Token, conversation = "chat-a", job = "j1", title = "Other box", button = "OK" });
        Assert.False(stopped.GetProperty("ok").GetBoolean());
        Assert.Equal("Stopped", stopped.GetProperty("refusedBy").GetString());
        Assert.Single(_host.Expected);
    }
}

/// <summary>Undo Heron's last change only when the modeller changed nothing since (D-54).</summary>
public class ChangedBeforeTests
{
    private readonly JobChanges _changes = new();

    [Fact]
    public void Nothing_between_two_jobs_means_nothing_changed_before()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.End("j1");
        _changes.Begin("j2", Risk.Change);
        Assert.False(_changes.ChangedBefore("j2"));
    }

    [Fact]
    public void The_modellers_own_change_between_jobs_is_seen()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.End("j1");
        _changes.Outside();
        _changes.Begin("j2", Risk.Change);
        Assert.True(_changes.ChangedBefore("j2"));
    }

    [Fact]
    public void A_read_job_between_does_not_hide_the_modellers_change()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.End("j1");
        _changes.Outside();
        _changes.Begin("r1", Risk.Read);
        _changes.End("r1");
        _changes.Begin("j2", Risk.Change);
        Assert.True(_changes.ChangedBefore("j2"));
    }

    [Fact]
    public void Another_job_is_not_known()
    {
        _changes.Begin("j1", Risk.Change);
        Assert.Null(_changes.ChangedBefore("other"));
    }

    [Fact]
    public void Since_last_answers_inside_the_running_job_only()
    {
        var host = new FakeHost { Before = false };
        var config = new HeronConfig { WriteEnabled = true };
        var protocol = new BridgeProtocol(host, () => config, "tok", new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement;
        Send(new { op = "begin", token = "tok", client = "pc", conversation = "c", job = "j2", tool = "autocad_undo_last", risk = "change", summary = "Undo", drawing = "a.dwg" });
        var reply = Send(new { op = "since_last", token = "tok", conversation = "c", job = "j2" });
        Assert.True(reply.GetProperty("known").GetBoolean());
        Assert.False(reply.GetProperty("changedSince").GetBoolean());
        Assert.False(Send(new { op = "since_last", token = "tok", conversation = "other", job = "j2" }).GetProperty("ok").GetBoolean());
    }
}
