using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

public class DialogWatchTests
{
    private static readonly DateTime T0 = new(2026, 11, 21, 9, 0, 0, DateTimeKind.Utc);
    private readonly DialogWatch _watch = new();
    private readonly HashSet<long> _open = new();

    private bool IsOpen(long handle) => _open.Contains(handle);

    private static DialogButton B(int id, string text, bool enabled = true) => new() { Id = id, Text = text, Enabled = enabled };

    private DialogSeen Box(long handle, string title, params DialogButton[] buttons)
    {
        _open.Add(handle);
        return new DialogSeen
        {
            Handle = handle, Title = title, ClassName = "#32770", OwnerDisabled = true, Enabled = true, Buttons = buttons,
        };
    }

    /// <summary>Two looks Settle apart: the second one presses.</summary>
    private DialogPlan? StandsFor(DialogSeen box, DateTime from)
    {
        Assert.Null(_watch.Look(box, IsOpen, from));
        return _watch.Look(box, IsOpen, from + DialogWatch.Settle);
    }

    [Fact]
    public void Outside_a_job_nothing_is_ever_pressed()
    {
        var box = Box(10, "Select File", B(1, "&Open"), B(2, "Cancel"));
        Assert.False(_watch.Watching);
        Assert.Null(StandsFor(box, T0));
        Assert.Null(_watch.Look(box, IsOpen, T0.AddSeconds(5)));
    }

    [Fact]
    public void A_box_that_opens_in_a_job_is_cancelled_after_it_settles_and_named()
    {
        _watch.Begin("j1", new long[0]);
        var box = Box(10, "Select File", B(1, "&Open"), B(2, "Cancel"));
        Assert.Null(_watch.Look(box, IsOpen, T0));
        Assert.Null(_watch.Look(box, IsOpen, T0.AddMilliseconds(100))); // not settled yet
        var plan = _watch.Look(box, IsOpen, T0 + DialogWatch.Settle);
        Assert.NotNull(plan);
        Assert.Equal(DialogPress.Cancel, plan!.Press);
        Assert.Equal(2, plan.ButtonId);
        Assert.True(plan.StandardBox);
        var note = Assert.Single(_watch.Notes("j1"));
        Assert.Equal("Select File", note.Title);
        Assert.Equal("Cancel", note.Pressed);
        Assert.Null(note.Closed);
    }

    [Fact]
    public void A_window_open_before_the_job_is_never_touched()
    {
        var mine = Box(10, "Options", B(1, "OK"), B(2, "Cancel"));
        _watch.Begin("j1", new long[] { 10 });
        Assert.Null(StandsFor(mine, T0));
        Assert.Null(_watch.Look(mine, IsOpen, T0.AddSeconds(10)));
        Assert.Empty(_watch.Notes("j1"));
    }

    [Theory]
    [InlineData("Heron - Keep this change?")]
    [InlineData("Heron - Heron erased objects")]
    [InlineData("Heron AI")]
    public void Heron_own_windows_are_never_touched(string title)
    {
        _watch.Begin("j1", new long[0]);
        Assert.Null(StandsFor(Box(10, title, B(2, "Cancel")), T0));
        Assert.Empty(_watch.Notes("j1"));
    }

    [Fact]
    public void While_Heron_asks_its_own_question_the_watch_is_paused()
    {
        _watch.Begin("j1", new long[0]);
        var box = Box(10, "Untitled", B(2, "Cancel"));
        _watch.Pause();
        Assert.Null(StandsFor(box, T0));
        _watch.Resume();
        Assert.NotNull(StandsFor(box, T0.AddSeconds(1)));
    }

    [Fact]
    public void Only_a_modal_box_that_takes_input_counts()
    {
        _watch.Begin("j1", new long[0]);
        var palette = Box(10, "Properties", B(2, "Cancel"));
        palette.OwnerDisabled = false; // AutoCAD still takes input: not modal
        Assert.Null(StandsFor(palette, T0));
        var under = Box(11, "Outer", B(2, "Cancel"));
        under.Enabled = false; // another box sits on top of it
        Assert.Null(StandsFor(under, T0));
        var banner = Box(12, "Something", B(2, "Cancel"));
        banner.NoActivate = true;
        Assert.Null(StandsFor(banner, T0));
    }

    [Fact]
    public void A_yes_no_box_gets_No_never_Yes()
    {
        var plan = DialogWatch.Choose(Box(10, "AutoCAD", B(6, "&Yes"), B(7, "&No")));
        Assert.Equal(DialogPress.No, plan.Press);
        Assert.Equal(7, plan.ButtonId);
    }

    [Fact]
    public void Yes_no_cancel_gets_Cancel()
    {
        var plan = DialogWatch.Choose(Box(10, "AutoCAD", B(6, "&Yes"), B(7, "&No"), B(2, "Cancel")));
        Assert.Equal(DialogPress.Cancel, plan.Press);
    }

    [Theory]
    [InlineData(1, "OK")]
    [InlineData(6, "Yes")]
    [InlineData(1, "Save")]
    public void A_box_with_only_OK_or_Yes_gets_Esc_never_its_button(int id, string text)
    {
        var plan = DialogWatch.Choose(Box(10, "AutoCAD Message", B(id, text)));
        Assert.Equal(DialogPress.Escape, plan.Press);
        Assert.Equal(0, plan.ButtonId);
    }

    [Fact]
    public void A_cancel_button_found_by_its_words_and_a_disabled_one_skipped()
    {
        Assert.Equal(DialogPress.Cancel, DialogWatch.Choose(Box(10, "x", B(1, "OK"), B(1002, " &Cancel "))).Press);
        Assert.Equal(DialogPress.No, DialogWatch.Choose(Box(10, "x", B(2, "Cancel", enabled: false), B(7, "No"))).Press);
    }

    [Fact]
    public void A_box_with_no_buttons_we_can_read_gets_Esc_as_its_close()
    {
        var wpf = new DialogSeen { Handle = 10, Title = "Layer States Manager", ClassName = "HwndWrapper[acad;;1]" };
        var plan = DialogWatch.Choose(wpf);
        Assert.Equal(DialogPress.Escape, plan.Press);
        Assert.False(plan.StandardBox);
    }

    [Fact]
    public void One_press_per_box_and_the_note_says_if_it_closed()
    {
        _watch.Begin("j1", new long[0]);
        var box = Box(10, "Select File", B(2, "Cancel"));
        Assert.NotNull(StandsFor(box, T0));
        Assert.Null(StandsFor(box, T0.AddSeconds(1))); // never pressed twice
        _open.Remove(10);
        _watch.Look(null, IsOpen, T0.AddSeconds(1));
        Assert.True(Assert.Single(_watch.Notes("j1")).Closed);
    }

    [Fact]
    public void A_box_still_open_after_the_press_is_reported_as_not_closed()
    {
        _watch.Begin("j1", new long[0]);
        var box = Box(10, "Stubborn", B(2, "Cancel"));
        Assert.NotNull(StandsFor(box, T0));
        _watch.Look(box, IsOpen, T0 + DialogWatch.Settle + DialogWatch.GiveUp);
        Assert.False(Assert.Single(_watch.Notes("j1")).Closed);
    }

    [Fact]
    public void After_too_many_boxes_Heron_stops_answering_and_says_so()
    {
        _watch.Begin("j1", new long[0]);
        var at = T0;
        for (var i = 0; i < DialogWatch.MostPresses; i++)
        {
            Assert.NotNull(StandsFor(Box(100 + i, "Again", B(2, "Cancel")), at));
            at = at.AddSeconds(1);
        }
        Assert.Null(StandsFor(Box(200, "Again", B(2, "Cancel")), at));
        var notes = _watch.Notes("j1");
        Assert.Equal(DialogWatch.MostPresses + 1, notes.Count);
        Assert.Equal("none", notes[notes.Count - 1].Pressed);
    }

    [Fact]
    public void A_new_job_starts_with_no_notes_and_takes_a_new_look_at_what_is_open()
    {
        _watch.Begin("j1", new long[0]);
        Assert.NotNull(StandsFor(Box(10, "First", B(2, "Cancel")), T0));
        _watch.End("j1");
        Assert.False(_watch.Watching);
        Assert.Empty(_watch.Notes("j1"));

        // Left open after j1 (it would not close): open before j2, so left alone.
        _watch.Begin("j2", new long[] { 10 });
        Assert.Null(StandsFor(Box(10, "First", B(2, "Cancel")), T0.AddSeconds(5)));
        Assert.Empty(_watch.Notes("j2"));
    }

    [Fact]
    public void A_box_with_no_title_is_still_named()
    {
        _watch.Begin("j1", new long[0]);
        Assert.NotNull(StandsFor(Box(10, "   ", B(2, "Cancel")), T0));
        Assert.Equal("a box with no title", Assert.Single(_watch.Notes("j1")).Title);
    }
}

public class DialogsOpTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly BridgeProtocol _protocol;

    public DialogsOpTests() =>
        _protocol = new BridgeProtocol(_host, () => new HeronConfig(), Token, new HeronHold(), () => DateTime.UtcNow);

    private JsonElement Send(object request) =>
        JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    [Fact]
    public void Dialogs_names_each_box_for_this_chats_running_job_only()
    {
        _host.Boxes.Add(new DialogNote { Title = "Select File", Pressed = "Cancel", Closed = true });
        _host.Boxes.Add(new DialogNote { Title = "Stubborn", Pressed = "Esc", Closed = null });
        Assert.True(Send(new { op = "begin", token = Token, conversation = "chat-a", job = "j1", tool = "autocad_list_layers", risk = "read", summary = "List Layers", drawing = "a.dwg" }).GetProperty("ok").GetBoolean());

        var other = Send(new { op = "dialogs", token = Token, conversation = "chat-b", job = "j1" });
        Assert.False(other.GetProperty("ok").GetBoolean());

        var reply = Send(new { op = "dialogs", token = Token, conversation = "chat-a", job = "j1" });
        Assert.True(reply.GetProperty("ok").GetBoolean());
        var boxes = reply.GetProperty("dialogs");
        Assert.Equal(2, boxes.GetArrayLength());
        Assert.Equal("Select File", boxes[0].GetProperty("title").GetString());
        Assert.Equal("Cancel", boxes[0].GetProperty("pressed").GetString());
        Assert.True(boxes[0].GetProperty("closed").GetBoolean());
        Assert.Equal(JsonValueKind.Null, boxes[1].GetProperty("closed").ValueKind);
    }

    [Fact]
    public void Dialogs_after_the_job_ended_is_refused()
    {
        Send(new { op = "begin", token = Token, conversation = "chat-a", job = "j1", tool = "autocad_list_layers", risk = "read", summary = "List Layers", drawing = "a.dwg" });
        Send(new { op = "end", token = Token, conversation = "chat-a", job = "j1", ok = true, outcome = "done", summary = "List Layers", ms = 5 });
        Assert.False(Send(new { op = "dialogs", token = Token, conversation = "chat-a", job = "j1" }).GetProperty("ok").GetBoolean());
    }
}

/// <summary>A job names one button for one box it expects (#101).</summary>
public class DialogAnswerTests
{
    private static readonly DateTime T0 = new(2026, 11, 21, 9, 0, 0, DateTimeKind.Utc);
    private readonly DialogWatch _watch = new();
    private readonly HashSet<long> _open = new();

    private bool IsOpen(long handle) => _open.Contains(handle);

    private static DialogButton B(int id, string text) => new() { Id = id, Text = text };

    private DialogSeen Box(long handle, string title, params DialogButton[] buttons)
    {
        _open.Add(handle);
        return new DialogSeen { Handle = handle, Title = title, ClassName = "#32770", OwnerDisabled = true, Enabled = true, Buttons = buttons };
    }

    private DialogPlan? StandsFor(DialogSeen box, DateTime from)
    {
        Assert.Null(_watch.Look(box, IsOpen, from));
        return _watch.Look(box, IsOpen, from + DialogWatch.Settle);
    }

    [Fact]
    public void The_named_button_is_pressed_on_the_box_with_exactly_that_title_and_said()
    {
        _watch.Begin("j1", new long[0]);
        Assert.True(_watch.Expect("j1", "Purge - Confirm Purge", "Yes"));
        var plan = StandsFor(Box(10, "Purge - Confirm Purge", B(6, "&Yes"), B(7, "&No")), T0);
        Assert.Equal(DialogPress.Named, plan!.Press);
        Assert.Equal(6, plan.ButtonId);
        Assert.Equal("Yes", DialogWatch.Label(plan));
        var note = Assert.Single(_watch.Notes("j1"));
        Assert.Equal("Yes", note.Pressed);
        Assert.True(note.Asked);
    }

    [Fact]
    public void Only_once_a_second_box_with_the_same_title_gets_the_default()
    {
        _watch.Begin("j1", new long[0]);
        _watch.Expect("j1", "Purge - Confirm Purge", "Yes");
        Assert.Equal(DialogPress.Named, StandsFor(Box(10, "Purge - Confirm Purge", B(6, "Yes"), B(7, "No")), T0)!.Press);
        var second = StandsFor(Box(11, "Purge - Confirm Purge", B(6, "Yes"), B(7, "No")), T0.AddSeconds(3));
        Assert.Equal(DialogPress.No, second!.Press);
        Assert.False(_watch.Notes("j1")[1].Asked);
    }

    [Fact]
    public void Every_other_box_is_still_cancelled_and_a_near_title_is_not_enough()
    {
        _watch.Begin("j1", new long[0]);
        _watch.Expect("j1", "Purge - Confirm Purge", "Yes");
        Assert.Equal(DialogPress.Cancel, StandsFor(Box(10, "Select File", B(1, "Open"), B(2, "Cancel")), T0)!.Press);
        Assert.Equal(DialogPress.No, StandsFor(Box(11, "purge - confirm purge", B(6, "Yes"), B(7, "No")), T0.AddSeconds(3))!.Press);
    }

    [Fact]
    public void A_box_without_the_named_button_gets_the_default()
    {
        _watch.Begin("j1", new long[0]);
        _watch.Expect("j1", "AutoCAD Message", "Yes");
        Assert.Equal(DialogPress.Escape, StandsFor(Box(10, "AutoCAD Message", B(1, "OK")), T0)!.Press);
    }

    [Fact]
    public void The_answer_ends_with_its_job_and_is_taken_once_per_job()
    {
        Assert.False(_watch.Expect("j1", "Purge - Confirm Purge", "Yes")); // no such job
        _watch.Begin("j1", new long[0]);
        Assert.False(_watch.Expect("j1", " ", "Yes"));
        Assert.True(_watch.Expect("j1", "Purge - Confirm Purge", "Yes"));
        Assert.False(_watch.Expect("j1", "Other", "OK")); // one answer per job
        _watch.End("j1");
        _watch.Begin("j2", new long[0]);
        Assert.Equal(DialogPress.No, StandsFor(Box(10, "Purge - Confirm Purge", B(6, "Yes"), B(7, "No")), T0)!.Press);
    }
}

public class ExpectDialogOpTests
{
    private const string Token = "tok";
    private readonly FakeHost _host = new();
    private readonly BridgeProtocol _protocol;

    public ExpectDialogOpTests() =>
        _protocol = new BridgeProtocol(_host, () => new HeronConfig { WriteEnabled = true, AdminEnabled = true }, Token, new HeronHold(), () => DateTime.UtcNow);

    private JsonElement Send(object request) =>
        JsonDocument.Parse(_protocol.Handle(JsonSerializer.Serialize(request))).RootElement;

    private void Begin(string job, string tool, string risk) =>
        Assert.True(Send(new { op = "begin", token = Token, conversation = "chat-a", job, tool, risk, summary = tool, drawing = "a.dwg" }).GetProperty("ok").GetBoolean());

    [Fact]
    public void An_admin_job_of_this_chat_may_name_one_button()
    {
        Begin("j1", "autocad_send_command", "admin");
        var reply = Send(new { op = "expect_dialog", token = Token, conversation = "chat-a", job = "j1", title = "Purge - Confirm Purge", button = "Yes" });
        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.Equal(("j1", "Purge - Confirm Purge", "Yes"), Assert.Single(_host.Expected));
    }

    [Fact]
    public void A_change_job_another_chat_or_a_blank_answer_is_refused()
    {
        Begin("j1", "autocad_draw_line", "change");
        var change = Send(new { op = "expect_dialog", token = Token, conversation = "chat-a", job = "j1", title = "X", button = "Yes" });
        Assert.False(change.GetProperty("ok").GetBoolean());
        Assert.Contains("Admin", change.GetProperty("message").GetString());
        Send(new { op = "end", token = Token, conversation = "chat-a", job = "j1", ok = true, outcome = "done", summary = "x", ms = 1 });

        Begin("j2", "autocad_run_lisp", "admin");
        Assert.False(Send(new { op = "expect_dialog", token = Token, conversation = "chat-b", job = "j2", title = "X", button = "Yes" }).GetProperty("ok").GetBoolean());
        Assert.False(Send(new { op = "expect_dialog", token = Token, conversation = "chat-a", job = "j2", title = "X", button = " " }).GetProperty("ok").GetBoolean());
        Assert.Empty(_host.Expected);
    }

    [Fact]
    public void A_named_press_is_reported_as_asked()
    {
        _host.Boxes.Add(new DialogNote { Title = "Purge - Confirm Purge", Pressed = "Yes", Closed = true, Asked = true });
        Begin("j1", "autocad_send_command", "admin");
        var box = Send(new { op = "dialogs", token = Token, conversation = "chat-a", job = "j1" }).GetProperty("dialogs")[0];
        Assert.True(box.GetProperty("asked").GetBoolean());
        Assert.Equal("Yes", box.GetProperty("pressed").GetString());
    }
}
