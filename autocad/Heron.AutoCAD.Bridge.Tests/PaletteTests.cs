using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>The Activity tab: the list of jobs and when Select, Zoom and Undo may run (D-68, D-54's rule).</summary>
public class ActivityLogTests
{
    private const string Dwg = @"C:\jobs\plant.dwg";
    private readonly ActivityLog _log = new();
    private static readonly DateTime At = new(2026, 11, 21, 9, 0, 0);

    private static UndoFacts Clean() => new() { ActiveDrawing = Dwg, ChangedSince = false, UndoControl = 1 };

    /// <param name="ask">What begin said (Ask to Keep on).</param>
    /// <param name="marked">What the server said at end; by default it marked exactly when it asked.</param>
    private void Job(string job, Risk risk = Risk.Change, bool ask = false, string outcome = "done", bool ok = true,
        int added = 1, string tool = "autocad_draw_line", string drawing = Dwg, bool? marked = null)
    {
        _log.Begin(new JobInfo { Job = job, Tool = tool, Risk = risk, Summary = "Job " + job, Drawing = drawing, AskToKeep = ask }, At);
        var handles = Enumerable.Range(0, added).Select(i => job + "-" + i).ToArray();
        var report = JobChanges.Watches(risk) ? new ChangeReport { Added = added, AddedHandles = handles } : null;
        _log.End(new JobEnd { Job = job, Ok = ok, Outcome = outcome, Summary = "Job " + job, Ms = 400, Marked = marked ?? ask }, report);
    }

    [Fact]
    public void Change_jobs_are_listed_newest_first_and_reads_and_views_are_left_out()
    {
        Job("j1");
        Job("r1", Risk.Read);
        Job("v1", Risk.View);
        Job("j2", Risk.Admin);
        Assert.Equal(new[] { "j2", "j1" }, _log.Entries.Select(e => e.Job));
        Assert.Equal("made 1, changed 0, erased 0", _log.Entries[1].Counts);
    }

    [Fact]
    public void The_list_keeps_the_newest_jobs_only()
    {
        for (var i = 0; i < ActivityLog.MostEntries + 5; i++) Job("j" + i);
        Assert.Equal(ActivityLog.MostEntries, _log.Entries.Count);
        Assert.Equal("j" + (ActivityLog.MostEntries + 4), _log.Entries[0].Job);
    }

    [Fact]
    public void A_job_is_shown_running_until_it_ends_and_nothing_may_be_done_meanwhile()
    {
        Job("j1");
        _log.Begin(new JobInfo { Job = "j2", Tool = "autocad_draw_line", Risk = Risk.Change, Drawing = Dwg }, At);
        Assert.True(_log.Busy);
        Assert.Equal("running", _log.Entries[0].State);
        Assert.Equal(PaletteTexts.Busy, _log.CanShow("j1", Dwg).Reason);
        Assert.Equal(PaletteTexts.Busy, _log.CanUndo("j1", Clean()).Reason);
    }

    [Fact]
    public void Changed_is_raised_on_begin_end_and_undone()
    {
        var raised = 0;
        _log.Changed += () => raised++;
        Job("j1");
        _log.Undone("j1");
        Assert.Equal(3, raised);
    }

    [Fact]
    public void Newest_clean_change_with_nothing_since_may_be_undone_one_step()
    {
        Job("j1", added: 2);
        var verdict = _log.CanUndo("j1", Clean());
        Assert.True(verdict.Allowed, verdict.Reason);
        Assert.False(verdict.Back);
        Assert.Equal("_.UNDO 1 ", verdict.Command);
        Assert.Equal(new[] { "j1-0", "j1-1" }, verdict.MustBeGone);
    }

    [Fact]
    public void With_ask_to_keep_on_the_undo_goes_back_to_the_jobs_mark_even_after_a_zoom()
    {
        Job("j1", ask: true);
        Job("v1", Risk.View);
        var verdict = _log.CanUndo("j1", Clean());
        Assert.True(verdict.Allowed, verdict.Reason);
        Assert.Equal("_.UNDO _Back ", verdict.Command);
    }

    [Fact]
    public void Ask_to_keep_on_but_no_mark_from_the_server_is_one_step_never_back_past_the_job()
    {
        // #206: the server skipped the mark (AutoCAD in a command, or busy), or is older and did not say.
        Job("j1", ask: true, marked: false);
        var verdict = _log.CanUndo("j1", Clean());
        Assert.True(verdict.Allowed, verdict.Reason);
        Assert.False(verdict.Back);
        Assert.Equal("_.UNDO 1 ", verdict.Command);
        Assert.False(_log.Entries[0].Marked);
    }

    [Fact]
    public void Ask_to_keep_on_but_no_mark_and_a_zoom_since_refuses_and_hides_undo()
    {
        Job("j1", ask: true, marked: false);
        Job("v1", Risk.View);
        Assert.Equal(PaletteTexts.UndoViewsSince, _log.CanUndo("j1", Clean()).Reason);
        Assert.False(PaletteRows.Buttons(_log.Entries[0], newest: true).Undo);
    }

    [Fact]
    public void A_mark_the_server_reports_is_back_even_with_ask_to_keep_off_at_begin()
    {
        // The plug-in takes the server's word for the mark; begin's answer does not decide it.
        Job("j1", ask: false, marked: true);
        Assert.Equal("_.UNDO _Back ", _log.CanUndo("j1", Clean()).Command);
    }

    [Fact]
    public void A_mark_said_for_a_raw_command_or_the_undo_tool_is_never_taken()
    {
        Job("a1", Risk.Admin, marked: true);
        Assert.False(_log.Entries[0].Marked);
        Job("u1", tool: ActivityLog.UndoTool, marked: true);
        Assert.False(_log.Entries[0].Marked);
    }

    [Fact]
    public void While_a_job_runs_it_is_not_taken_as_marked()
    {
        _log.Begin(new JobInfo { Job = "j1", Tool = "autocad_draw_line", Risk = Risk.Change, Drawing = Dwg, AskToKeep = true }, At);
        Assert.False(_log.Entries[0].Marked);
    }

    [Fact]
    public void Asked_to_keep_but_not_marked_the_questions_zoom_refuses_one_step_and_hides_undo()
    {
        // D-130: the Keep question zooms to the job; with no mark, UNDO 1 would undo that zoom.
        _log.Begin(new JobInfo { Job = "j1", Tool = "autocad_draw_line", Risk = Risk.Change, Drawing = Dwg, AskToKeep = true }, At);
        _log.ShownForKeep("j1");
        _log.End(new JobEnd { Job = "j1", Ok = true, Outcome = "done", Marked = false }, new ChangeReport { Added = 1, AddedHandles = new[] { "A" } });
        Assert.Equal(PaletteTexts.UndoViewsSince, _log.CanUndo("j1", Clean()).Reason);
        Assert.False(PaletteRows.Buttons(_log.Entries[0], newest: true).Undo);
    }

    [Fact]
    public void Asked_to_keep_and_marked_the_questions_zoom_is_inside_the_mark()
    {
        _log.Begin(new JobInfo { Job = "j1", Tool = "autocad_draw_line", Risk = Risk.Change, Drawing = Dwg, AskToKeep = true }, At);
        _log.ShownForKeep("j1");
        _log.End(new JobEnd { Job = "j1", Ok = true, Outcome = "done", Marked = true }, new ChangeReport { Added = 1, AddedHandles = new[] { "A" } });
        Assert.Equal("_.UNDO _Back ", _log.CanUndo("j1", Clean()).Command);
    }

    [Fact]
    public void After_the_erase_question_brought_objects_back_one_step_is_refused_and_hidden()
    {
        // #244: the restore is an undo step after the job; UNDO 1 would erase them again.
        Job("j1", added: 2);
        _log.BroughtBack("j1");
        Assert.Equal(PaletteTexts.UndoAfterRestore, _log.CanUndo("j1", Clean()).Reason);
        Assert.False(PaletteRows.Buttons(_log.Entries[0], newest: true).Undo);
    }

    [Fact]
    public void After_a_restore_a_real_mark_still_goes_back_past_it_to_the_job()
    {
        Job("j1", ask: true, added: 2);
        _log.BroughtBack("j1");
        var verdict = _log.CanUndo("j1", Clean());
        Assert.True(verdict.Allowed, verdict.Reason);
        Assert.Equal("_.UNDO _Back ", verdict.Command);
    }

    [Fact]
    public void Without_a_mark_a_heron_zoom_since_refuses_because_one_step_would_be_the_zoom()
    {
        Job("j1");
        Job("v1", Risk.View);
        Assert.Equal(PaletteTexts.UndoViewsSince, _log.CanUndo("j1", Clean()).Reason);
    }

    [Fact]
    public void Only_the_newest_change_may_be_undone()
    {
        Job("j1");
        Job("j2");
        var verdict = _log.CanUndo("j1", Clean());
        Assert.False(verdict.Allowed);
        Assert.Equal(PaletteTexts.UndoNotNewest("Job j2"), verdict.Reason);
    }

    [Fact]
    public void A_change_by_the_modeller_since_refuses_and_says_why()
    {
        Job("j1");
        var facts = Clean();
        facts.ChangedSince = true;
        Assert.Equal(PaletteTexts.UndoChangedSince, _log.CanUndo("j1", facts).Reason);
        facts.ChangedSince = null;
        Assert.Equal(PaletteTexts.UndoUnknown, _log.CanUndo("j1", facts).Reason);
    }

    [Fact]
    public void Another_drawing_in_front_refuses_and_names_both()
    {
        Job("j1");
        var facts = Clean();
        facts.ActiveDrawing = @"C:\jobs\other.dwg";
        var reason = _log.CanUndo("j1", facts).Reason;
        Assert.Contains("plant.dwg", reason);
        Assert.Contains("other.dwg", reason);
        Assert.False(_log.CanShow("j1", @"C:\jobs\other.dwg").Allowed);
    }

    [Theory]
    [InlineData(0)]   // undo off
    [InlineData(3)]   // one step only
    [InlineData(-1)]  // could not be read
    public void Undo_off_or_one_step_in_the_drawing_refuses(int undoControl)
    {
        Job("j1", ask: true);
        var facts = Clean();
        facts.UndoControl = undoControl;
        Assert.Equal(PaletteTexts.UndoOff, _log.CanUndo("j1", facts).Reason);
    }

    [Fact]
    public void A_raw_command_or_a_save_is_never_undone_here()
    {
        Job("a1", Risk.Admin);
        Assert.Equal(PaletteTexts.UndoRawCommand, _log.CanUndo("a1", Clean()).Reason);
        Job("p1", Risk.Publish);
        Assert.Equal(PaletteTexts.UndoRawCommand, _log.CanUndo("p1", Clean()).Reason);
    }

    [Fact]
    public void Discarded_failed_and_empty_jobs_are_not_undone()
    {
        Job("d1", outcome: "discarded");
        Assert.Equal(PaletteTexts.UndoDiscarded, _log.CanUndo("d1", Clean()).Reason);
        Job("f1", outcome: "failed", ok: false);
        Assert.Equal(PaletteTexts.UndoNotClean("failed"), _log.CanUndo("f1", Clean()).Reason);
        Job("e1", added: 0);
        Assert.Equal(PaletteTexts.UndoNothing, _log.CanUndo("e1", Clean()).Reason);
    }

    [Fact]
    public void An_undo_job_is_not_undone_again()
    {
        Job("u1", tool: ActivityLog.UndoTool);
        Assert.Equal(PaletteTexts.UndoOfUndo, _log.CanUndo("u1", Clean()).Reason);
    }

    [Fact]
    public void Once_undone_it_is_not_undone_twice_and_not_shown()
    {
        Job("j1");
        _log.Undone("j1");
        Assert.Equal(PaletteTexts.AlreadyUndone, _log.CanUndo("j1", Clean()).Reason);
        Assert.Equal(PaletteTexts.ShowUndone, _log.CanShow("j1", Dwg).Reason);
        Assert.Equal("undone from this palette", _log.Entries[0].State);
    }

    [Fact]
    public void Select_and_zoom_take_what_the_job_made_and_changed_whoever_holds_this_autocad()
    {
        _log.Begin(new JobInfo { Job = "j1", Tool = "t", Risk = Risk.Change, Drawing = Dwg }, At);
        _log.End(new JobEnd { Job = "j1", Ok = true, Outcome = "done" },
            new ChangeReport { Added = 1, Modified = 1, AddedHandles = new[] { "A" }, ModifiedHandles = new[] { "B" } });
        var verdict = _log.CanShow("j1", Dwg);
        Assert.True(verdict.Allowed);
        Assert.Equal(new[] { "A", "B" }, verdict.Handles);
    }

    [Fact]
    public void A_job_that_only_erased_has_nothing_to_show()
    {
        _log.Begin(new JobInfo { Job = "j1", Tool = "t", Risk = Risk.Change, Drawing = Dwg }, At);
        _log.End(new JobEnd { Job = "j1", Ok = true, Outcome = "done" }, new ChangeReport { Erased = 2 });
        Assert.Equal(PaletteTexts.ShowOnlyErased, _log.CanShow("j1", Dwg).Reason);
        Assert.True(_log.CanUndo("j1", Clean()).Allowed);
    }

    [Fact]
    public void A_job_whose_end_never_came_stops_blocking_after_the_longest_job()
    {
        var now = At;
        var log = new ActivityLog(() => now);
        log.Begin(new JobInfo { Job = "j1", Tool = "t", Risk = Risk.Change, Drawing = Dwg }, At);
        Assert.True(log.Busy);
        now = At + ActivityLog.MostJob - TimeSpan.FromSeconds(1);
        Assert.True(log.Busy);
        now = At + ActivityLog.MostJob;
        Assert.False(log.Busy);
        // It never ended, so it is still not something to undo.
        Assert.Equal(PaletteTexts.UndoNotClean(""), log.CanUndo("j1", Clean()).Reason);
    }

    [Fact]
    public void While_the_palettes_undo_waits_no_job_may_begin_and_no_second_undo_starts()
    {
        var now = At;
        var log = new ActivityLog(() => now);
        log.Begin(new JobInfo { Job = "j1", Tool = "t", Risk = Risk.Change, Drawing = Dwg }, At);
        log.End(new JobEnd { Job = "j1", Ok = true, Outcome = "done" }, new ChangeReport { Added = 1, AddedHandles = new[] { "A" } });
        Assert.Null(log.Blocking());
        log.UndoWaiting(true);
        Assert.Equal(PaletteTexts.JobWaitsForUndo, log.Blocking());
        Assert.Equal(PaletteTexts.UndoAlreadyWaiting, log.CanUndo("j1", Clean()).Reason);
        log.UndoWaiting(false);
        Assert.Null(log.Blocking());
        Assert.True(log.CanUndo("j1", Clean()).Allowed);
    }

    // ----- which buttons a card shows (D-124) -----

    private JobButtons ButtonsOf(string job)
    {
        var entries = _log.Entries;
        var entry = entries.Single(e => e.Job == job);
        return PaletteRows.Buttons(entry, entries[0].Job == job);
    }

    private static string Shown(JobButtons b) =>
        (b.Select ? "S" : "-") + (b.Zoom ? "Z" : "-") + (b.Undo ? "U" : "-");

    [Fact]
    public void A_save_that_made_changed_and_erased_nothing_gets_no_buttons()
    {
        // Ajmal's card: "Save Drawing ... done, made 0, changed 0, erased 0".
        Job("s1", Risk.Publish, added: 0, tool: "autocad_save_drawing");
        Assert.Equal("made 0, changed 0, erased 0", _log.Entries[0].Counts);
        Assert.Equal("---", Shown(ButtonsOf("s1")));
        Assert.False(ButtonsOf("s1").Any);
    }

    [Fact]
    public void An_export_or_command_that_made_nothing_gets_no_buttons()
    {
        Job("p1", Risk.Publish, added: 0, tool: "autocad_export");
        Assert.Equal("---", Shown(ButtonsOf("p1")));
        Job("a1", Risk.Admin, added: 0, tool: "autocad_send_command");
        Assert.Equal("---", Shown(ButtonsOf("a1")));
        Job("c1", added: 0);
        Assert.Equal("---", Shown(ButtonsOf("c1")));
    }

    [Fact]
    public void The_newest_change_that_made_something_gets_all_three()
    {
        Job("j1", added: 2);
        Assert.Equal("SZU", Shown(ButtonsOf("j1")));
    }

    [Fact]
    public void An_older_change_keeps_select_and_zoom_but_not_undo()
    {
        Job("j1");
        Job("j2");
        Assert.Equal("SZ-", Shown(ButtonsOf("j1")));
        Assert.Equal("SZU", Shown(ButtonsOf("j2")));
        // A save after a change: the change is no longer Heron's newest.
        Job("s1", Risk.Publish, added: 0);
        Assert.Equal("SZ-", Shown(ButtonsOf("j2")));
    }

    [Fact]
    public void A_command_that_drew_something_can_be_shown_but_never_undone_here()
    {
        Job("a1", Risk.Admin, added: 1);
        Assert.Equal("SZ-", Shown(ButtonsOf("a1")));
    }

    [Fact]
    public void An_erase_only_job_gets_undo_but_nothing_to_select_or_zoom_to()
    {
        _log.Begin(new JobInfo { Job = "e1", Tool = "autocad_delete_entities", Risk = Risk.Change, Drawing = Dwg }, At);
        _log.End(new JobEnd { Job = "e1", Ok = true, Outcome = "done" }, new ChangeReport { Erased = 2 });
        Assert.Equal("--U", Shown(ButtonsOf("e1")));
    }

    [Fact]
    public void Discarded_undone_running_and_undo_jobs_get_no_undo()
    {
        Job("d1", outcome: "discarded");
        Assert.Equal("---", Shown(ButtonsOf("d1")));
        Job("u1", tool: ActivityLog.UndoTool);
        Assert.False(ButtonsOf("u1").Undo);
        Job("j1");
        _log.Undone("j1");
        Assert.Equal("---", Shown(ButtonsOf("j1")));
        _log.Begin(new JobInfo { Job = "r1", Tool = "autocad_draw_line", Risk = Risk.Change, Drawing = Dwg }, At);
        Assert.Equal("---", Shown(ButtonsOf("r1")));
    }

    [Fact]
    public void A_failed_job_that_left_objects_can_be_shown_but_not_undone()
    {
        Job("f1", outcome: "failed", ok: false);
        Assert.Equal("SZ-", Shown(ButtonsOf("f1")));
        Job("n1", outcome: "unknown", ok: false);
        Assert.Equal("SZ-", Shown(ButtonsOf("n1")));
    }

    [Fact]
    public void Without_a_mark_a_heron_zoom_since_hides_undo_and_with_a_mark_it_stays()
    {
        Job("j1");
        Job("v1", Risk.View);
        Assert.Equal("SZ-", Shown(ButtonsOf("j1")));
        Job("k1", ask: true);
        Job("v2", Risk.View);
        Assert.Equal("SZU", Shown(ButtonsOf("k1")));
    }

    [Fact]
    public void A_dry_run_was_taken_back_so_it_gets_no_buttons_and_select_says_why()
    {
        // D-63: the server ends a dry run as "dry_run", with the counts of what it took back.
        Job("t1", outcome: ActivityLog.DryRun, added: 3);
        Assert.Equal("---", Shown(ButtonsOf("t1")));
        Assert.Equal(PaletteTexts.ShowDryRun, _log.CanShow("t1", Dwg).Reason);
        Assert.False(_log.CanUndo("t1", Clean()).Allowed);
        Assert.Equal("dry run, taken back", _log.Entries[0].State);
    }

    [Theory]
    [InlineData("change")]
    [InlineData("save")]
    [InlineData("admin drew")]
    [InlineData("discarded")]
    [InlineData("dry run")]
    [InlineData("failed")]
    [InlineData("unknown")]
    [InlineData("undo tool")]
    [InlineData("made nothing")]
    [InlineData("marked, view since")]
    [InlineData("unmarked, view since")]
    [InlineData("asked, not marked, view since")]
    [InlineData("brought back")]
    [InlineData("marked, brought back")]
    [InlineData("erase only")]
    [InlineData("undone here")]
    [InlineData("not newest")]
    public void A_hidden_button_is_one_the_click_would_refuse_and_an_allowed_click_has_its_button(string scenario)
    {
        // Pin the card's buttons to the click rules, so the two cannot drift apart. Each job is
        // the newest in its own list, so every per-job condition of Undo is compared, not only "newest".
        const string id = "x1";
        switch (scenario)
        {
            case "change": Job(id); break;
            case "save": Job(id, Risk.Publish, added: 0); break;
            case "admin drew": Job(id, Risk.Admin, added: 2); break;
            case "discarded": Job(id, outcome: "discarded"); break;
            case "dry run": Job(id, outcome: ActivityLog.DryRun); break;
            case "failed": Job(id, outcome: "failed", ok: false); break;
            case "unknown": Job(id, outcome: "unknown", ok: false); break;
            case "undo tool": Job(id, tool: ActivityLog.UndoTool); break;
            case "made nothing": Job(id, added: 0); break;
            case "marked, view since": Job(id, ask: true); Job("v1", Risk.View); break;
            case "asked, not marked, view since": Job(id, ask: true, marked: false); Job("v1", Risk.View); break;
            case "brought back": Job(id, added: 2); _log.BroughtBack(id); break;
            case "marked, brought back": Job(id, ask: true, added: 2); _log.BroughtBack(id); break;
            case "unmarked, view since": Job(id); Job("v1", Risk.View); break;
            case "erase only":
                _log.Begin(new JobInfo { Job = id, Tool = "t", Risk = Risk.Change, Drawing = Dwg }, At);
                _log.End(new JobEnd { Job = id, Ok = true, Outcome = "done" }, new ChangeReport { Erased = 2 });
                break;
            case "undone here": Job(id); _log.Undone(id); break;
            case "not newest": Job(id); Job("j2"); break;
        }
        var buttons = ButtonsOf(id);
        var show = _log.CanShow(id, Dwg);
        var undo = _log.CanUndo(id, Clean());
        Assert.True(buttons.Select == show.Allowed, scenario + " select: " + show.Reason);
        Assert.True(buttons.Zoom == show.Allowed, scenario + " zoom: " + show.Reason);
        Assert.True(buttons.Undo == undo.Allowed, scenario + " undo: " + undo.Reason);
    }

    [Fact]
    public void A_palette_undo_never_holds_jobs_off_longer_than_a_minute()
    {
        var now = At;
        var log = new ActivityLog(() => now);
        log.UndoWaiting(true);
        now = At + ActivityLog.MostUndoWait;
        Assert.Null(log.Blocking());
    }

    [Fact]
    public void Begin_is_refused_while_the_palettes_undo_waits_and_nothing_is_taken()
    {
        var host = new FakeHost();
        var config = new HeronConfig { WriteEnabled = true };
        var hold = new HeronHold();
        var blocked = true;
        var protocol = new BridgeProtocol(host, () => config, "tok", hold, () => DateTime.UtcNow)
        {
            BlockedBy = () => blocked ? PaletteTexts.JobWaitsForUndo : null,
        };
        string Begin() => protocol.Handle(JsonSerializer.Serialize(new
        {
            op = "begin", token = "tok", client = "pc", conversation = "c", job = "j1",
            tool = "autocad_draw_line", risk = "change", summary = "Draw Line", drawing = "a.dwg",
        }));
        var refused = JsonDocument.Parse(Begin()).RootElement;
        Assert.False(refused.GetProperty("ok").GetBoolean());
        Assert.Equal("Busy", refused.GetProperty("refusedBy").GetString());
        Assert.EndsWith(Texts.NothingSent, refused.GetProperty("message").GetString());
        Assert.Empty(host.Begun);
        // The hold was not taken, so another chat is not shut out by a refused begin.
        Assert.True(hold.TryTake("other", DateTime.UtcNow));
        hold.Release("other");
        blocked = false;
        Assert.True(JsonDocument.Parse(Begin()).RootElement.GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void An_entry_handed_out_is_a_copy()
    {
        Job("j1");
        _log.Entries[0].Undone = true;
        Assert.False(_log.Entries[0].Undone);
    }
}

/// <summary>What the palette's Undo asks the change count: anything since this job ended?</summary>
public class ChangedSinceTests
{
    private readonly JobChanges _changes = new();

    [Fact]
    public void Nothing_since_the_end_is_false_and_a_change_outside_a_job_is_true()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.End("j1");
        Assert.False(_changes.ChangedSince("j1"));
        _changes.Outside();
        Assert.True(_changes.ChangedSince("j1"));
    }

    [Fact]
    public void A_read_job_in_between_does_not_hide_it()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.End("j1");
        _changes.Begin("r1", Risk.Read);
        _changes.End("r1");
        Assert.False(_changes.ChangedSince("j1"));
    }

    [Fact]
    public void Another_change_job_since_or_the_job_still_running_is_not_known()
    {
        _changes.Begin("j1", Risk.Change);
        Assert.Null(_changes.ChangedSince("j1"));
        _changes.End("j1");
        _changes.Begin("j2", Risk.Change);
        _changes.End("j2");
        Assert.Null(_changes.ChangedSince("j1"));
    }

    [Fact]
    public void The_report_carries_what_was_made_and_changed_for_select_and_zoom()
    {
        _changes.Begin("j1", Risk.Change);
        _changes.Appended("A");
        _changes.Modified("B");
        var report = _changes.Read("j1")!;
        Assert.Equal(new[] { "A" }, report.AddedHandles);
        Assert.Equal(new[] { "B" }, report.ModifiedHandles);
    }

    [Fact]
    public void Begin_tells_the_host_whether_it_will_ask_to_keep()
    {
        var host = new FakeHost();
        var config = new HeronConfig { WriteEnabled = true, AskBeforeKeeping = true };
        var protocol = new BridgeProtocol(host, () => config, "tok", new HeronHold(), () => DateTime.UtcNow);
        protocol.Handle(JsonSerializer.Serialize(new
        {
            op = "begin", token = "tok", client = "pc", conversation = "c", job = "j1",
            tool = "autocad_draw_line", risk = "change", summary = "Draw Line", drawing = "a.dwg",
        }));
        Assert.True(host.Begun.Single().AskToKeep);
    }
}

/// <summary>The Saved commands tab: the files the server keeps (D-55), searched and filled (D-68).</summary>
public class SavedCommandListTests : IDisposable
{
    private readonly string _folder = Path.Combine(Path.GetTempPath(), "heron-palette-" + Guid.NewGuid().ToString("N"));

    // The very shape saved_commands.py writes.
    private const string Plinth = """
        {
          "name": "Plinth",
          "inputs": {
            "width": {"description": "plinth width, mm", "example": 1200},
            "depth": {"description": "plinth depth, mm", "example": 800},
            "layer": {"description": "layer", "default": "S-PLINTH"},
            "level": {"description": "level name", "example": "100"},
            "corner": {"description": "first corner", "example": [0, 0]},
            "filled": {"description": "hatch it", "default": false}
          },
          "steps": [{"tool": "autocad_draw_rectangle", "args": {}}, {"tool": "autocad_zoom", "args": {}}],
          "description": "a plinth under a pump"
        }
        """;

    public SavedCommandListTests() => Directory.CreateDirectory(_folder);

    public void Dispose()
    {
        try { Directory.Delete(_folder, true); } catch (IOException) { }
    }

    private SavedCommand Load() => SavedCommandList.Parse(Plinth)!;

    private static Dictionary<string, string> Typed(params (string, string)[] pairs) => pairs.ToDictionary(p => p.Item1, p => p.Item2);

    [Fact]
    public void A_command_is_read_with_its_inputs_defaults_and_examples()
    {
        var command = Load();
        Assert.Equal("Plinth", command.Name);
        Assert.Equal("a plinth under a pump", command.Description);
        Assert.Equal(2, command.Steps);
        var layer = command.Inputs.Single(i => i.Name == "layer");
        Assert.True(layer.HasDefault);
        Assert.Equal("S-PLINTH", layer.StartText);
        Assert.Equal("e.g. 1200", command.Inputs.Single(i => i.Name == "width").Hint);
    }

    [Fact]
    public void The_folder_is_read_by_name_and_a_broken_file_is_left_out()
    {
        File.WriteAllText(Path.Combine(_folder, "plinth.json"), Plinth);
        File.WriteAllText(Path.Combine(_folder, "a.json"), """{"name": "anchor bolt", "inputs": {}, "steps": []}""");
        File.WriteAllText(Path.Combine(_folder, "broken.json"), "{ not json");
        Assert.Equal(new[] { "anchor bolt", "Plinth" }, SavedCommandList.Load(_folder).Select(c => c.Name));
    }

    [Fact]
    public void A_missing_folder_is_no_commands()
    {
        Assert.Empty(SavedCommandList.Load(Path.Combine(_folder, "none")));
    }

    [Fact]
    public void Search_needs_every_word_in_the_name_description_or_inputs()
    {
        var commands = new[] { Load(), SavedCommandList.Parse("""{"name": "Pipe support", "description": "", "inputs": {}}""")! };
        Assert.Equal(new[] { "Plinth" }, SavedCommandList.Search(commands, "pump PLINTH").Select(c => c.Name));
        Assert.Equal(new[] { "Plinth" }, SavedCommandList.Search(commands, "width").Select(c => c.Name));
        Assert.Equal(2, SavedCommandList.Search(commands, "  ").Count);
        Assert.Empty(SavedCommandList.Search(commands, "duct"));
    }

    [Fact]
    public void Each_value_takes_its_examples_type_and_a_blank_default_is_left_to_the_server()
    {
        var filled = SavedCommandList.Fill(Load(), Typed(("width", "1500"), ("depth", "902.5"), ("layer", ""),
            ("level", "100"), ("corner", "[10, 20]"), ("filled", "yes")));
        Assert.True(filled.Ok, filled.Message);
        var json = JsonDocument.Parse(filled.Json).RootElement;
        Assert.Equal(1500, json.GetProperty("width").GetInt32());
        Assert.Equal(902.5, json.GetProperty("depth").GetDouble());
        Assert.False(json.TryGetProperty("layer", out _));
        Assert.Equal("100", json.GetProperty("level").GetString());
        Assert.Equal(20, json.GetProperty("corner")[1].GetInt32());
        Assert.True(json.GetProperty("filled").GetBoolean());
    }

    [Fact]
    public void A_missing_or_wrong_value_is_named_and_nothing_is_sent()
    {
        var command = Load();
        var all = Typed(("width", "1500"), ("depth", "900"), ("level", "1"), ("corner", "[0,0]"));
        Assert.Equal(PaletteTexts.NeedsValue("width", "plinth width, mm"),
            SavedCommandList.Fill(command, Typed(("depth", "900"), ("level", "1"), ("corner", "[0,0]"))).Message);
        all["width"] = "wide";
        Assert.Equal(PaletteTexts.NeedsNumber("width", "1200"), SavedCommandList.Fill(command, all).Message);
        all["width"] = "1500";
        all["corner"] = "0,0";
        Assert.Equal(PaletteTexts.NeedsList("corner", "[0, 0]"), SavedCommandList.Fill(command, all).Message);
        all["corner"] = "[0,0]";
        all["filled"] = "maybe";
        Assert.Equal(PaletteTexts.NeedsYesNo("filled"), SavedCommandList.Fill(command, all).Message);
    }

    [Fact]
    public void A_number_is_read_the_same_whatever_the_windows_language()
    {
        var saved = System.Globalization.CultureInfo.CurrentCulture;
        try
        {
            System.Globalization.CultureInfo.CurrentCulture = new System.Globalization.CultureInfo("de-DE");
            var filled = SavedCommandList.Fill(Load(), Typed(("width", "1200.5"), ("depth", "1"), ("level", "1"), ("corner", "[0,0]")));
            Assert.Equal(1200.5, JsonDocument.Parse(filled.Json).RootElement.GetProperty("width").GetDouble());
        }
        finally
        {
            System.Globalization.CultureInfo.CurrentCulture = saved;
        }
    }

    [Fact]
    public void The_run_request_is_the_name_and_the_inputs()
    {
        var request = JsonDocument.Parse(SavedCommandList.RunRequest(Load(), """{"width": 1500}""")).RootElement;
        Assert.Equal("Plinth", request.GetProperty("name").GetString());
        Assert.Equal(1500, request.GetProperty("inputs").GetProperty("width").GetInt32());
    }
}

/// <summary>How Run reaches the server: found from server.json, started with quoted arguments, its answer read.</summary>
public class PaletteServerTests : IDisposable
{
    private readonly string _file = Path.Combine(Path.GetTempPath(), "heron-server-" + Guid.NewGuid().ToString("N") + ".json");

    public void Dispose()
    {
        try { File.Delete(_file); } catch (IOException) { }
    }

    [Fact]
    public void The_python_the_server_last_ran_with_is_found()
    {
        File.WriteAllText(_file, """{"python": "C:\\Heron\\.venv\\Scripts\\python.exe", "version": "1.5.0"}""");
        Assert.Equal(@"C:\Heron\.venv\Scripts\python.exe", PaletteServer.FindPython(_file, _ => true, out var problem));
        Assert.Equal("", problem);
    }

    [Fact]
    public void No_file_or_a_python_that_is_gone_says_so()
    {
        Assert.Null(PaletteServer.FindPython(_file, _ => true, out var problem));
        Assert.Equal(PaletteTexts.NoServer, problem);
        File.WriteAllText(_file, """{"python": "C:\\gone\\python.exe"}""");
        Assert.Null(PaletteServer.FindPython(_file, _ => false, out problem));
        Assert.Equal(PaletteTexts.ServerGone, problem);
        File.WriteAllText(_file, "nonsense");
        Assert.Null(PaletteServer.FindPython(_file, _ => true, out problem));
        Assert.Equal(PaletteTexts.NoServer, problem);
    }

    [Theory]
    [InlineData("plain", "plain")]
    [InlineData(@"C:\My Files\run.json", "\"C:\\My Files\\run.json\"")]
    [InlineData("say \"hi\"", "\"say \\\"hi\\\"\"")]
    [InlineData(@"C:\a b\", "\"C:\\a b\\\\\"")]
    [InlineData("", "\"\"")]
    public void Arguments_are_quoted_as_windows_reads_them(string arg, string quoted)
    {
        Assert.Equal(quoted, PaletteServer.Quote(arg));
    }

    [Fact]
    public void The_run_always_has_the_plug_in_checks_on_and_is_never_another_chat()
    {
        var environment = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase)
        {
            ["HERON_AUTOCAD_BRIDGE"] = "off",
            ["heron_conversation_id"] = "a chat's id",
            ["CLAUDE_CODE_SESSION_ID"] = "a host chat",
            ["PATH"] = @"C:\Windows",
        };
        PaletteServer.PrepareEnvironment(environment);
        Assert.Equal("on", environment["HERON_AUTOCAD_BRIDGE"]);
        Assert.False(environment.ContainsKey("HERON_CONVERSATION_ID"));
        Assert.False(environment.ContainsKey("CLAUDE_CODE_SESSION_ID"));
        Assert.Equal("Heron palette", environment["HERON_CLIENT_ID"]);
        Assert.Equal(@"C:\Windows", environment["PATH"]);
    }

    [Fact]
    public void The_runner_is_told_the_request_and_this_autocad()
    {
        Assert.Equal("-m autocad_mcp --run-saved \"C:\\Users\\A B\\r.json\" --acad-pid 4242",
            PaletteServer.Arguments(@"C:\Users\A B\r.json", 4242));
    }

    [Fact]
    public void The_runners_last_json_line_is_its_answer()
    {
        var reply = PaletteServer.Reply("starting\n{\"ok\": true, \"message\": \"Done: 2 of 2 steps.\"}\n", "", 0);
        Assert.True(reply.Ok);
        Assert.Equal("Done: 2 of 2 steps.", reply.Message);
        var refused = PaletteServer.Reply("{\"ok\": false, \"message\": \"Changes is off.\"}", "", 1);
        Assert.False(refused.Ok);
        Assert.Equal("Changes is off.", refused.Message);
    }

    [Fact]
    public void No_readable_answer_says_so_with_the_end_of_the_error()
    {
        var reply = PaletteServer.Reply("", "Traceback...\nModuleNotFoundError: autocad_mcp", 1);
        Assert.False(reply.Ok);
        Assert.StartsWith(PaletteTexts.NoReply, reply.Message);
        Assert.Contains("ModuleNotFoundError", reply.Message);
    }
}
