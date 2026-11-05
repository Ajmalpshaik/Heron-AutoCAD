using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>The DONE card must always close (stuck banner, bedroom model, 2026-11-05).</summary>
public class BannerJobsTests
{
    private static readonly DateTime T0 = new(2026, 11, 5, 12, 0, 0, DateTimeKind.Utc);
    private readonly BannerJobs _jobs = new();

    private static JobInfo Job(string id, string chat = "chat-1") => new() { Job = id, Conversation = chat, Tool = "autocad_x" };

    [Fact]
    public void A_begin_and_its_end_leave_nothing_running()
    {
        _jobs.Begin(Job("j1"), T0);
        Assert.False(_jobs.AllDone(T0));
        _jobs.End("j1");
        Assert.True(_jobs.AllDone(T0));
    }

    [Fact]
    public void An_end_sent_twice_does_not_hide_a_job_still_running()
    {
        _jobs.Begin(Job("j1", "chat-1"), T0);
        _jobs.End("j1");
        _jobs.Begin(Job("j2", "chat-2"), T0);
        _jobs.End("j1");
        Assert.False(_jobs.AllDone(T0));
        Assert.Equal(1, _jobs.InFlight);
    }

    [Fact]
    public void A_lost_end_is_put_right_by_the_next_begin_from_the_same_chat()
    {
        // The camera job hung and its end never came.
        _jobs.Begin(Job("camera"), T0);
        _jobs.Begin(Job("save"), T0);
        _jobs.End("save");
        Assert.True(_jobs.AllDone(T0));
    }

    [Fact]
    public void Another_chat_does_not_clear_a_running_job()
    {
        _jobs.Begin(Job("j1", "chat-1"), T0);
        _jobs.Begin(Job("j2", "chat-2"), T0);
        _jobs.End("j2");
        Assert.False(_jobs.AllDone(T0));
    }

    [Fact]
    public void A_job_older_than_the_stale_limit_no_longer_holds_the_card()
    {
        _jobs.Begin(Job("lost"), T0);
        Assert.False(_jobs.AllDone(T0 + BannerJobs.StaleAfter));
        Assert.True(_jobs.AllDone(T0 + BannerJobs.StaleAfter + TimeSpan.FromSeconds(1)));
    }

    [Fact]
    public void An_end_for_a_job_never_begun_changes_nothing()
    {
        _jobs.End("ghost");
        Assert.True(_jobs.AllDone(T0));
        Assert.Equal(0, _jobs.InFlight);
    }
}
