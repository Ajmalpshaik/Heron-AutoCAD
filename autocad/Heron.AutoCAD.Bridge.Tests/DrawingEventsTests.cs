using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The plug-in records what happens to the drawings as AutoCAD says it
/// happens (#48, D-98): opened, came to the front, saved (perhaps as a new
/// name), closed. The server's wrong-drawing guard reads it, send_quiet stops
/// input once another drawing came to the front, and the palette shows it.
/// </summary>
public class DrawingEventsTests
{
    private DateTime _now = new(2026, 11, 21, 10, 0, 0);
    private DrawingEvents Log() => new(() => _now);

    [Fact]
    public void Events_are_numbered_in_order_and_follow_the_front()
    {
        var log = Log();
        log.Start(@"C:\a.dwg");
        Assert.Equal(0, log.Seq);
        Assert.Equal(@"C:\a.dwg", log.Active);
        log.DrawingOpened(@"C:\b.dwg");
        log.DrawingActivated(@"C:\b.dwg");
        Assert.Equal(2, log.Seq);
        Assert.Equal(@"C:\b.dwg", log.Active);
        var all = log.Since(0).Events;
        Assert.Equal(new[] { DrawingEvents.Opened, DrawingEvents.Activated }, all.Select(e => e.Kind));
        Assert.Equal(new long[] { 1, 2 }, all.Select(e => e.Seq));
    }

    [Fact]
    public void Before_the_watch_starts_the_front_is_not_known()
    {
        var log = Log();
        Assert.Null(log.Active);
        Assert.Null(log.FrontChangedSince(0));
        Assert.Null(log.Since(0).Active);
    }

    [Fact]
    public void The_drawing_already_in_front_coming_to_the_front_again_is_not_news()
    {
        var log = Log();
        log.Start(@"C:\a.dwg");
        log.DrawingActivated(@"C:\A.DWG");
        Assert.Equal(0, log.Seq);
        Assert.Null(log.FrontChangedSince(0));
    }

    [Fact]
    public void A_save_as_renames_the_drawing_in_front_without_moving_the_front()
    {
        var log = Log();
        log.Start("Drawing1.dwg");
        log.DrawingSaved(@"C:\plan.dwg", "Drawing1.dwg");
        Assert.Equal(@"C:\plan.dwg", log.Active);
        Assert.Null(log.FrontChangedSince(0));
        var saved = Assert.Single(log.Since(0).Events);
        Assert.Equal(DrawingEvents.Saved, saved.Kind);
        Assert.Equal("Drawing1.dwg", saved.Was);
    }

    [Fact]
    public void A_plain_save_has_no_old_name()
    {
        var log = Log();
        log.DrawingSaved(@"C:\plan.dwg", @"C:\PLAN.dwg");
        Assert.Equal("", Assert.Single(log.Since(0).Events).Was);
    }

    [Fact]
    public void Closing_the_drawing_in_front_leaves_none_in_front()
    {
        var log = Log();
        log.Start(@"C:\a.dwg");
        log.DrawingClosed(@"C:\a.dwg");
        Assert.Equal("", log.Active);
        Assert.Equal("", log.FrontChangedSince(0));
    }

    [Fact]
    public void Closing_a_drawing_behind_does_not_move_the_front()
    {
        var log = Log();
        log.Start(@"C:\a.dwg");
        log.DrawingClosed(@"C:\b.dwg");
        Assert.Equal(@"C:\a.dwg", log.Active);
        Assert.Null(log.FrontChangedSince(0));
    }

    [Fact]
    public void Front_changed_since_only_counts_what_came_after()
    {
        var log = Log();
        log.Start(@"C:\a.dwg");
        log.DrawingActivated(@"C:\b.dwg");
        var mark = log.Seq;
        Assert.Null(log.FrontChangedSince(mark));
        log.DrawingActivated(@"C:\c.dwg");
        Assert.Equal(@"C:\c.dwg", log.FrontChangedSince(mark));
    }

    [Fact]
    public void Old_events_drop_off_and_a_reader_who_missed_them_is_told()
    {
        var log = Log();
        for (var i = 0; i < DrawingEvents.MostKept + 5; i++) log.DrawingOpened("d" + i + ".dwg");
        Assert.Equal(DrawingEvents.MostKept, log.Since(0).Events.Count);
        Assert.True(log.Since(0).Lost);
        Assert.True(log.Since(4).Lost);
        Assert.False(log.Since(5).Lost);
        Assert.False(log.Since(log.Seq).Lost);
    }

    [Fact]
    public void Each_log_has_its_own_epoch()
    {
        Assert.NotEqual(Log().Epoch, Log().Epoch);
        Assert.Equal(12, Log().Epoch.Length);
    }

    [Fact]
    public void Changed_is_raised_for_every_event()
    {
        var log = Log();
        var raised = 0;
        log.Changed += () => raised++;
        log.Start("a.dwg");
        log.DrawingOpened("b.dwg");
        log.DrawingActivated("b.dwg");
        log.DrawingActivated("b.dwg"); // not news: not raised
        Assert.Equal(3, raised);
    }

    [Fact]
    public void Recent_is_newest_first()
    {
        var log = Log();
        log.DrawingOpened("a.dwg");
        log.DrawingOpened("b.dwg");
        log.DrawingOpened("c.dwg");
        Assert.Equal(new[] { "c.dwg", "b.dwg" }, log.Recent(2).Select(e => e.Drawing));
    }

    [Theory]
    [InlineData(@"C:\plan.dwg", false)]
    [InlineData(@"C:\plan.DWT", false)]
    [InlineData(@"C:\x\plan.dxf", false)]
    [InlineData(@"C:\Temp\plan_1_1_1234.sv$", true)]
    [InlineData(@"C:\x\plan.bak", true)]
    [InlineData(@"C:\x.y\plan", true)]
    [InlineData("", true)]
    [InlineData(null, true)]
    public void Autosave_and_backup_files_are_not_a_save(string? file, bool backup)
    {
        Assert.Equal(backup, DrawingEvents.IsBackupFile(file));
    }
}

public class DrawingsOpTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly HeronConfig _config = new() { WriteEnabled = true };
    private readonly DrawingEvents _log = new(() => new DateTime(2026, 11, 21, 10, 2, 3));
    private readonly BridgeProtocol _protocol;

    public DrawingsOpTests() =>
        _protocol = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => DateTime.UtcNow) { Drawings = _log };

    private JsonElement Send(object request) => JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    private JsonElement Drawings(long? since = null) =>
        since == null
            ? Send(new { op = "drawings", token = Token, conversation = "chat-a" })
            : Send(new { op = "drawings", token = Token, conversation = "chat-a", since });

    [Fact]
    public void Reports_the_events_after_the_number_asked_for()
    {
        _log.Start(@"C:\a.dwg");
        _log.DrawingClosed(@"C:\a.dwg");
        _log.DrawingOpened(@"C:\a.dwg");
        _log.DrawingActivated(@"C:\a.dwg");
        var reply = Drawings(1);
        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.True(reply.GetProperty("known").GetBoolean());
        Assert.Equal(_log.Epoch, reply.GetProperty("epoch").GetString());
        Assert.Equal(3, reply.GetProperty("seq").GetInt64());
        Assert.Equal(@"C:\a.dwg", reply.GetProperty("active").GetString());
        Assert.False(reply.GetProperty("lost").GetBoolean());
        var events = reply.GetProperty("events").EnumerateArray().ToList();
        Assert.Equal(new[] { "opened", "activated" }, events.Select(e => e.GetProperty("kind").GetString()));
        Assert.Equal("10:02:03", events[0].GetProperty("at").GetString());
        Assert.False(events[0].TryGetProperty("was", out _));
    }

    [Fact]
    public void A_save_as_says_the_old_name()
    {
        _log.DrawingSaved(@"C:\plan.dwg", "Drawing1.dwg");
        var saved = Assert.Single(Drawings(0).GetProperty("events").EnumerateArray().ToList());
        Assert.Equal("Drawing1.dwg", saved.GetProperty("was").GetString());
    }

    [Fact]
    public void Without_since_every_kept_event_comes_back()
    {
        _log.DrawingOpened("a.dwg");
        Assert.Single(Drawings().GetProperty("events").EnumerateArray());
    }

    [Fact]
    public void Before_the_watch_starts_the_front_is_null()
    {
        Assert.Equal(JsonValueKind.Null, Drawings(0).GetProperty("active").ValueKind);
    }

    [Fact]
    public void Without_a_log_it_says_it_does_not_know()
    {
        var bare = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => DateTime.UtcNow);
        var reply = JsonDocument.Parse(bare.Handle(JsonSerializer.Serialize(new { op = "drawings", token = Token, conversation = "c" }))).RootElement;
        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.False(reply.GetProperty("known").GetBoolean());
    }

    [Fact]
    public void Needs_the_session_token()
    {
        var reply = Send(new { op = "drawings", token = "old", conversation = "chat-a" });
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal(Texts.WrongSession, reply.GetProperty("message").GetString());
    }

    [Fact]
    public void Answers_while_another_chat_holds_this_autocad()
    {
        Send(new { op = "begin", token = Token, conversation = "chat-b", job = "j9", tool = "autocad_draw_line", risk = "change", summary = "Line", drawing = "a.dwg" });
        Assert.True(Drawings(0).GetProperty("ok").GetBoolean());
    }
}

/// <summary>Quiet input stops once another drawing came to the front during the job (#48).</summary>
public class QuietDrawingTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly HeronConfig _config = new() { WriteEnabled = true };
    private readonly DrawingEvents _log = new();
    private readonly BridgeProtocol _protocol;

    public QuietDrawingTests()
    {
        _protocol = new BridgeProtocol(_host, () => _config, Token, new HeronHold(), () => DateTime.UtcNow) { Drawings = _log };
        _log.Start(@"C:\a.dwg");
    }

    private JsonElement Send(object request) => JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    private void Begin(string drawing = @"C:\a.dwg") => Send(new
    {
        op = "begin", token = Token, conversation = "chat-a", job = "j1", tool = "autocad_batch_draw", risk = "change", summary = "Batch", drawing,
    });

    private JsonElement Quiet(params string[] lines) =>
        Send(new { op = "send_quiet", token = Token, conversation = "chat-a", job = "j1", lines = lines.Length == 0 ? new[] { "(progn 1)" } : lines });

    [Fact]
    public void Typed_with_the_jobs_drawing_when_nothing_moved()
    {
        Begin();
        Assert.True(Quiet().GetProperty("ok").GetBoolean());
        Assert.Equal(@"C:\a.dwg", Assert.Single(_host.QuietDrawings));
    }

    [Fact]
    public void Refused_once_another_drawing_came_to_the_front_during_the_job()
    {
        Begin();
        _log.DrawingActivated(@"C:\b.dwg");
        var reply = Quiet();
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal("Drawing", reply.GetProperty("refusedBy").GetString());
        Assert.Equal(Texts.DrawingChangedInJob(@"C:\a.dwg", @"C:\b.dwg"), reply.GetProperty("message").GetString());
        Assert.Contains("b.dwg is in front now", reply.GetProperty("message").GetString());
        Assert.Empty(_host.Quiet);
    }

    [Fact]
    public void Refused_once_the_jobs_drawing_was_closed()
    {
        Begin();
        _log.DrawingClosed(@"C:\a.dwg");
        var reply = Quiet();
        Assert.Equal("Drawing", reply.GetProperty("refusedBy").GetString());
        Assert.Contains("no drawing is in front now", reply.GetProperty("message").GetString());
    }

    [Fact]
    public void Back_in_the_jobs_drawing_is_typed()
    {
        Begin();
        _log.DrawingActivated(@"C:\b.dwg");
        _log.DrawingActivated(@"C:\a.dwg");
        Assert.True(Quiet().GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void A_switch_before_the_job_began_does_not_count()
    {
        _log.DrawingActivated(@"C:\b.dwg");
        Begin(@"C:\b.dwg");
        Assert.True(Quiet().GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void A_save_as_during_the_job_is_not_a_switch()
    {
        Begin();
        _log.DrawingSaved(@"C:\renamed.dwg", @"C:\a.dwg");
        Assert.True(Quiet().GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void An_unsaved_drawing_named_bare_matches_its_name()
    {
        _log.Start("Drawing1.dwg");
        Begin("Drawing1.dwg");
        _log.DrawingActivated(@"C:\x\Drawing2.dwg");
        Assert.Equal("Drawing", Quiet().GetProperty("refusedBy").GetString());
    }

    [Fact]
    public void A_line_longer_than_the_plugin_types_is_refused_and_nothing_typed()
    {
        Begin();
        var reply = Quiet("(progn 1)", "(progn " + new string('1', BridgeProtocol.QuietLineLimit) + ")");
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal("TooLong", reply.GetProperty("refusedBy").GetString());
        Assert.EndsWith(Texts.NothingSent, reply.GetProperty("message").GetString());
        Assert.Empty(_host.Quiet);
    }

    [Fact]
    public void A_line_of_exactly_the_limit_is_typed()
    {
        Begin();
        var line = "(progn " + new string('1', BridgeProtocol.QuietLineLimit - 8) + ")";
        Assert.Equal(BridgeProtocol.QuietLineLimit, line.Length);
        Assert.True(Quiet(line).GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void Ping_says_how_long_a_quiet_line_may_be()
    {
        var reply = Send(new { op = "ping", token = Token, conversation = "c" });
        Assert.Equal(BridgeProtocol.QuietLineLimit, reply.GetProperty("quietLimit").GetInt32());
    }
}

public class PaletteRowsTests
{
    private static readonly DateTime T0 = new(2026, 11, 21, 10, 0, 0);

    private static ActivityEntry Job(string id, int minute, string drawing = @"C:\a.dwg") =>
        new() { Job = id, Summary = id, Drawing = drawing, At = T0.AddMinutes(minute) };

    private static DrawingEvent Event(string kind, int minute, string drawing = @"C:\b.dwg", string was = "") =>
        new() { Kind = kind, Drawing = drawing, Was = was, At = T0.AddMinutes(minute) };

    [Fact]
    public void Jobs_and_drawing_events_are_one_list_newest_first()
    {
        var rows = PaletteRows.Merge(
            new[] { Job("j2", 5), Job("j1", 1) },
            new[] { Event(DrawingEvents.Activated, 3) });
        Assert.Equal(new[] { "j2", "event", "j1" }, rows.Select(r => r.Job?.Job ?? "event"));
    }

    [Fact]
    public void At_the_same_moment_the_job_comes_first()
    {
        var rows = PaletteRows.Merge(new[] { Job("j1", 2) }, new[] { Event(DrawingEvents.Saved, 2) });
        Assert.NotNull(rows[0].Job);
    }

    [Fact]
    public void Only_the_newest_drawing_events_are_shown()
    {
        var events = Enumerable.Range(0, 40).Select(i => Event(DrawingEvents.Opened, 100 - i)).ToList();
        var rows = PaletteRows.Merge(new ActivityEntry[0], events);
        Assert.Equal(PaletteRows.MostDrawingRows, rows.Count);
        Assert.Equal(T0.AddMinutes(100), rows[0].At);
    }

    [Fact]
    public void A_job_in_another_drawing_is_not_in_front()
    {
        Assert.True(PaletteRows.InFront(Job("j", 0), @"C:\A.dwg"));
        Assert.False(PaletteRows.InFront(Job("j", 0), @"C:\b.dwg"));
        Assert.False(PaletteRows.InFront(Job("j", 0), ""));
        Assert.True(PaletteRows.InFront(Job("j", 0), null)); // not known: nothing marked on a guess
    }

    [Theory]
    [InlineData(DrawingEvents.Opened, @"C:\x\b.dwg", "", "b.dwg opened")]
    [InlineData(DrawingEvents.Activated, @"C:\x\b.dwg", "", "b.dwg came to the front")]
    [InlineData(DrawingEvents.Saved, @"C:\x\b.dwg", "", "b.dwg saved")]
    [InlineData(DrawingEvents.Saved, @"C:\x\plan.dwg", "Drawing1.dwg", "Drawing1.dwg saved as plan.dwg")]
    [InlineData(DrawingEvents.Closed, "Drawing3.dwg", "", "Drawing3.dwg closed")]
    public void Each_event_reads_in_plain_words(string kind, string drawing, string was, string said)
    {
        Assert.Equal(said, PaletteTexts.DrawingRow(Event(kind, 0, drawing, was)));
    }

    [Fact]
    public void The_line_above_the_list_names_the_drawing_in_front()
    {
        Assert.Equal("In front: plan.dwg", PaletteTexts.InFront(@"C:\x\plan.dwg"));
        Assert.Equal("No drawing is in front.", PaletteTexts.InFront(""));
    }
}
