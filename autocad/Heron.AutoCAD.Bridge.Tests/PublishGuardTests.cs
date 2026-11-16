using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>No save, plot or export inside a Heron job while Publish is off.</summary>
public class PublishGuardTests
{
    private DateTime _now = new(2026, 11, 15, 9, 0, 0, DateTimeKind.Utc);
    private readonly PublishGuard _guard;
    private readonly HeronConfig _off = new() { WriteEnabled = true, AdminEnabled = true, PublishEnabled = false };
    private readonly HeronConfig _on = new() { WriteEnabled = true, AdminEnabled = true, PublishEnabled = true };

    public PublishGuardTests()
    {
        _guard = new PublishGuard(() => _now);
    }

    [Theory]
    [InlineData("QSAVE")]
    [InlineData("#QSAVE")]
    [InlineData("_.qsave")]
    [InlineData("-PLOT")]
    [InlineData("SAVEAS")]
    [InlineData("-EXPORT")]
    [InlineData("ETRANSMIT")]
    [InlineData("WBLOCK")]
    public void A_save_plot_or_export_inside_a_job_is_stopped_while_Publish_is_off(string command)
    {
        _guard.Begin("j1", Risk.Admin);
        var words = _guard.Veto(command, _off);
        Assert.NotNull(words);
        Assert.Contains("Publish", words);
    }

    [Fact]
    public void Publish_on_lets_it_run()
    {
        _guard.Begin("j1", Risk.Admin);
        Assert.Null(_guard.Veto("QSAVE", _on));
    }

    [Fact]
    public void The_modellers_own_save_outside_a_job_is_never_touched()
    {
        Assert.Null(_guard.Veto("QSAVE", _off));
        _guard.Begin("j1", Risk.Admin);
        _guard.End("j1");
        _now += PublishGuard.Grace + TimeSpan.FromSeconds(1);
        Assert.Null(_guard.Veto("QSAVE", _off));
    }

    [Fact]
    public void A_command_the_job_typed_that_starts_just_after_its_end_is_still_stopped()
    {
        _guard.Begin("j1", Risk.Admin);
        _guard.End("j1");
        _now += TimeSpan.FromSeconds(1);
        Assert.NotNull(_guard.Veto("QSAVE", _off));
    }

    [Theory]
    [InlineData("LINE")]
    [InlineData("SAVETIME")]
    [InlineData("PLOTSTAMP")]
    [InlineData("")]
    [InlineData(null)]
    public void Other_commands_run(string? command)
    {
        _guard.Begin("j1", Risk.Admin);
        Assert.Null(_guard.Veto(command, _off));
    }

    [Theory]
    [InlineData(Risk.Read)]
    [InlineData(Risk.View)]
    [InlineData(Risk.Publish)]
    public void A_preview_or_a_publish_job_is_never_stopped(Risk risk)
    {
        // autocad_preview plots to a PNG through COM inside a Read job.
        _guard.Begin("j1", risk);
        Assert.Null(_guard.Veto("PLOT", _off));
        _guard.End("j1");
        Assert.Null(_guard.Veto("PLOT", _off));
    }

    [Fact]
    public void A_second_job_ending_does_not_end_the_first()
    {
        _guard.Begin("j1", Risk.Admin);
        _guard.Begin("j2", Risk.Change);
        _guard.End("j2");
        _now += PublishGuard.Grace + TimeSpan.FromSeconds(1);
        Assert.True(_guard.InJob);
    }
}
