using System;
using Heron.AutoCAD.Bridge;
using Xunit;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>D-125: a tab switch's own viewport changes are not the job's work.</summary>
public class TabSwitchWindowTests
{
    private DateTime _clock = new DateTime(2026, 11, 22, 7, 23, 0, DateTimeKind.Utc);

    private TabSwitchWindow Window() => new TabSwitchWindow(() => _clock);

    [Fact]
    public void A_tab_switch_opens_the_window_and_its_end_closes_it()
    {
        var window = Window();
        Assert.False(window.Open);
        window.WillChange("CTAB");
        Assert.True(window.Open);
        window.Changed("ctab");
        Assert.False(window.Open);
    }

    [Fact]
    public void Other_variables_do_not_open_it()
    {
        var window = Window();
        window.WillChange("CLAYER");
        window.WillChange("TILEMODE");
        window.WillChange(null);
        Assert.False(window.Open);
    }

    [Fact]
    public void Another_variable_changing_does_not_close_it()
    {
        var window = Window();
        window.WillChange("CTAB");
        window.Changed("CVPORT");
        Assert.True(window.Open);
    }

    [Fact]
    public void A_window_whose_end_was_lost_shuts_by_itself()
    {
        // So a lost "CTAB changed" can never hide a real erase for long.
        var window = Window();
        window.WillChange("CTAB");
        _clock += TabSwitchWindow.Longest + TimeSpan.FromMilliseconds(1);
        Assert.False(window.Open);
        _clock += TimeSpan.FromSeconds(1);
        Assert.False(window.Open);
    }

    [Fact]
    public void A_second_switch_starts_the_time_again()
    {
        var window = Window();
        window.WillChange("CTAB");
        _clock += TimeSpan.FromSeconds(4);
        window.WillChange("CTAB");
        _clock += TimeSpan.FromSeconds(4);
        Assert.True(window.Open);
    }
}
