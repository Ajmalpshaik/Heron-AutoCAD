using System.Runtime.InteropServices;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>A policy the test sets, as an administrator would (D-60).</summary>
public sealed class FakePolicy : IHeronPolicy
{
    public PolicyHolds Holds { get; set; } = PolicyHolds.None;
    public bool Throws { get; set; }
    public int Reads { get; private set; }

    public PolicyHolds Read()
    {
        Reads++;
        if (Throws) throw new InvalidOperationException("registry gone");
        return Holds;
    }
}

/// <summary>The padlocks live in memory, start off, and only a click turns one on (D-59).</summary>
public class PadlockTests
{
    private readonly FakePolicy _policy = new();
    private readonly HeronPadlocks _padlocks;

    public PadlockTests() => _padlocks = new HeronPadlocks(_policy);

    private HeronConfig Now() => _padlocks.Snapshot(new HeronConfig());

    [Fact]
    public void Every_padlock_is_off_when_AutoCAD_starts_and_Ask_to_Keep_is_off()
    {
        var config = Now();
        Assert.False(config.WriteEnabled);
        Assert.False(config.PublishEnabled);
        Assert.False(config.AdminEnabled);
        Assert.False(config.AskBeforeKeeping);
        Assert.False(_padlocks.IsOn(Padlock.Changes));
        Assert.False(_padlocks.IsOn(Padlock.AskToKeep));
    }

    [Fact]
    public void A_click_turns_a_padlock_on_and_another_turns_it_off()
    {
        Assert.True(_padlocks.TurnOn(Padlock.Changes));
        Assert.True(Now().WriteEnabled);
        Assert.False(Now().AdminEnabled);

        _padlocks.TurnOff(Padlock.Changes);
        Assert.False(Now().WriteEnabled);

        _padlocks.TurnOff(Padlock.AskToKeep);
        Assert.False(Now().AskBeforeKeeping);
        Assert.True(_padlocks.TurnOn(Padlock.AskToKeep));
        Assert.True(Now().AskBeforeKeeping);
    }

    [Fact]
    public void The_padlock_values_handed_in_are_never_used()
    {
        // Only the file's own settings pass through a snapshot.
        var fromFile = new HeronConfig
        {
            WriteEnabled = true, PublishEnabled = true, AdminEnabled = true, AskBeforeKeeping = true,
            AutoConnect = true, ActivityBanner = false,
        };
        var config = _padlocks.Snapshot(fromFile);
        Assert.False(config.WriteEnabled);
        Assert.False(config.PublishEnabled);
        Assert.False(config.AdminEnabled);
        Assert.False(config.AskBeforeKeeping);
        Assert.True(config.AutoConnect);
        Assert.False(config.ActivityBanner);
    }

    [Fact]
    public void Each_AutoCAD_has_its_own_padlocks()
    {
        var other = new HeronPadlocks(new NoPolicy());
        _padlocks.TurnOn(Padlock.Changes);
        Assert.False(other.Snapshot(new HeronConfig()).WriteEnabled);
    }

    [Fact]
    public void A_policy_of_0_holds_a_padlock_off_and_the_click_is_refused()
    {
        _policy.Holds = new PolicyHolds(changes: true, publish: false, admin: false);
        Assert.False(_padlocks.TurnOn(Padlock.Changes));
        var config = Now();
        Assert.False(config.WriteEnabled);
        Assert.True(config.Held.Changes);
        Assert.False(config.Held.Publish);

        var refusal = Permissions.Refusal(Risk.Change, config);
        Assert.NotNull(refusal);
        Assert.Equal("Changes", refusal!.RefusedBy);
        Assert.Equal(Texts.ChangesHeld, refusal.Message);

        // The padlocks the policy leaves alone still work.
        Assert.True(_padlocks.TurnOn(Padlock.Publish));
        Assert.True(Now().PublishEnabled);
    }

    [Fact]
    public void A_policy_set_later_turns_the_padlock_off_and_lifting_it_does_not_turn_it_back_on()
    {
        _padlocks.TurnOn(Padlock.Changes);
        _padlocks.TurnOn(Padlock.Admin);
        _policy.Holds = new PolicyHolds(changes: false, publish: false, admin: true);
        Assert.False(Now().AdminEnabled);
        Assert.True(Now().WriteEnabled);

        _policy.Holds = PolicyHolds.None;
        Assert.False(Now().AdminEnabled);
        Assert.False(_padlocks.IsOn(Padlock.Admin));
    }

    [Theory]
    [InlineData("publish", "Publish")]
    [InlineData("admin", "Admin")]
    public void A_held_Publish_or_Admin_says_the_policy_holds_it(string risk, string padlock)
    {
        _policy.Holds = new PolicyHolds(changes: false, publish: true, admin: true);
        _padlocks.TurnOn(Padlock.Changes);
        RiskNames.TryParse(risk, out var level);
        var refusal = Permissions.Refusal(level, Now());
        Assert.Equal(padlock, refusal!.RefusedBy);
        Assert.Equal(padlock == "Publish" ? Texts.PublishHeld : Texts.AdminHeld, refusal.Message);
    }

    [Fact]
    public void Ask_to_Keep_has_no_policy()
    {
        _policy.Holds = new PolicyHolds(changes: true, publish: true, admin: true);
        _padlocks.TurnOff(Padlock.AskToKeep);
        Assert.True(_padlocks.TurnOn(Padlock.AskToKeep));
        Assert.False(PolicyHolds.None.Holds(Padlock.AskToKeep));
    }

    [Fact]
    public void A_policy_that_cannot_be_read_holds_nothing_and_breaks_nothing()
    {
        _policy.Throws = true;
        Assert.Same(PolicyHolds.None, _padlocks.Holds());
        Assert.True(_padlocks.TurnOn(Padlock.Changes));
        Assert.True(Now().WriteEnabled);
    }

    [Fact]
    public void The_policy_is_read_fresh_for_every_call()
    {
        Now();
        Now();
        Assert.Equal(2, _policy.Reads);
    }

    [Fact]
    public void A_held_padlock_refuses_the_job_at_begin()
    {
        _policy.Holds = new PolicyHolds(changes: true, publish: false, admin: false);
        var protocol = new BridgeProtocol(new FakeHost(), Now, "tok", new HeronHold(), () => DateTime.UtcNow);
        var reply = JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(new
        {
            op = "begin", token = "tok", client = "pc", conversation = "chat-a", job = "j1",
            tool = "autocad_draw_line", risk = "change", summary = "Draw Line", drawing = @"C:\a.dwg",
        }))).RootElement;
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal("Changes", reply.GetProperty("refusedBy").GetString());
        Assert.Equal(Texts.ChangesHeld, reply.GetProperty("message").GetString());
    }
}

/// <summary>The registry values an administrator may type, and the real reader off Windows.</summary>
public class WindowsPolicyTests
{
    [Theory]
    [InlineData(0, true)]
    [InlineData(1, false)]
    [InlineData(2, false)]
    public void A_DWORD_of_0_holds_and_any_other_number_does_not(int value, bool holds)
    {
        Assert.Equal(holds, WindowsPolicy.Denies(value));
        Assert.Equal(holds, WindowsPolicy.Denies((long)value));
    }

    [Theory]
    [InlineData("0", true)]
    [InlineData(" 0 ", true)]
    [InlineData("1", false)]
    [InlineData("no", false)]
    [InlineData("", false)]
    public void A_text_value_holds_only_when_it_reads_0(string value, bool holds)
    {
        Assert.Equal(holds, WindowsPolicy.Denies(value));
    }

    [Fact]
    public void No_value_holds_nothing()
    {
        Assert.False(WindowsPolicy.Denies(null));
        Assert.False(WindowsPolicy.Denies(new byte[] { 0 }));
    }

    [Fact]
    public void The_key_is_Heron_AutoCAD_under_Policies()
    {
        Assert.Equal(@"SOFTWARE\Policies\Heron\AutoCAD", WindowsPolicy.KeyPath);
        Assert.Equal("AllowChanges", WindowsPolicy.AllowChanges);
        Assert.Equal("AllowPublish", WindowsPolicy.AllowPublish);
        Assert.Equal("AllowAdmin", WindowsPolicy.AllowAdmin);
    }

    [Fact]
    public void The_real_reader_never_throws()
    {
        // On a PC (or CI runner) without the key, and off Windows, it holds nothing.
        var holds = new WindowsPolicy().Read();
        Assert.NotNull(holds);
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows)) Assert.Same(PolicyHolds.None, holds);
    }
}
