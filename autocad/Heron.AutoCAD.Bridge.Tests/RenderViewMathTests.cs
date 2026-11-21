using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// A camera's lens and field (#60, D-86): a 24 mm lens inside a room, AutoCAD's
/// default 50 mm, and the view sized so the lens and the field agree.
/// </summary>
public class CameraLensTests
{
    [Theory]
    [InlineData(50.0, 39.598)]
    [InlineData(24.0, 73.740)]
    [InlineData(35.0, 54.432)]
    [InlineData(18.0, 90.0)]
    public void The_field_of_view_is_across_a_36_mm_frame(double lens, double degrees)
    {
        Assert.Equal(degrees, CameraLens.FieldOfViewDegrees(lens), 3);
    }

    [Fact]
    public void A_longer_lens_sees_less()
    {
        Assert.True(CameraLens.FieldOfViewDegrees(85) < CameraLens.FieldOfViewDegrees(50));
        Assert.True(CameraLens.FieldOfViewDegrees(24) > CameraLens.FieldOfViewDegrees(35));
    }

    [Fact]
    public void The_view_is_the_field_at_the_target()
    {
        // 4.8 m from the target through 24 mm: 7.2 m across, and 4:3 makes it 5.4 m high.
        CameraLens.Field(4800, 24, 4.0 / 3.0, out var width, out var height);
        Assert.Equal(7200.0, width, 9);
        Assert.Equal(5400.0, height, 9);
    }

    [Theory]
    [InlineData(double.NaN)]
    [InlineData(0.0)]
    [InlineData(-1.0)]
    [InlineData(100.0)]
    [InlineData(0.1)]
    public void An_aspect_that_cannot_be_a_screen_is_four_to_three(double aspect)
    {
        Assert.Equal(4.0 / 3.0, CameraLens.Aspect(aspect), 12);
    }

    [Fact]
    public void A_wide_screen_keeps_its_shape()
    {
        Assert.Equal(16.0 / 9.0, CameraLens.Aspect(16.0 / 9.0), 12);
    }

    [Theory]
    [InlineData(10.0)]
    [InlineData(24.0)]
    [InlineData(600.0)]
    public void Lenses_from_10_to_600_mm_are_taken(double lens)
    {
        Assert.Null(CameraLens.Check(lens));
    }

    [Theory]
    [InlineData(9.9)]
    [InlineData(0.0)]
    [InlineData(-24.0)]
    [InlineData(601.0)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    public void Other_lenses_are_refused_saying_the_range(double lens)
    {
        Assert.Contains("10-600 mm", CameraLens.Check(lens));
    }
}

/// <summary>The sun's date and time (#61, D-86): only what the chat gave changes.</summary>
public class SunClockTests
{
    private static readonly DateTime Autumn = new DateTime(2026, 9, 21, 15, 0, 0);

    [Fact]
    public void A_date_and_a_time_replace_both()
    {
        Assert.Null(SunClock.Compose(Autumn, 2026, 6, 21, 10, 30, out var when));
        Assert.Equal(new DateTime(2026, 6, 21, 10, 30, 0), when);
    }

    [Fact]
    public void A_time_alone_keeps_the_date()
    {
        Assert.Null(SunClock.Compose(Autumn, null, null, null, 7, 45, out var when));
        Assert.Equal(new DateTime(2026, 9, 21, 7, 45, 0), when);
    }

    [Fact]
    public void A_date_alone_keeps_the_time()
    {
        Assert.Null(SunClock.Compose(Autumn, 2027, 12, 21, null, null, out var when));
        Assert.Equal(new DateTime(2027, 12, 21, 15, 0, 0), when);
    }

    [Fact]
    public void Nothing_given_changes_nothing()
    {
        Assert.Null(SunClock.Compose(Autumn, null, null, null, null, null, out var when));
        Assert.Equal(Autumn, when);
    }

    [Theory]
    [InlineData(2026, 2, 29, "no day 29")]
    [InlineData(2026, 13, 1, "month")]
    [InlineData(1800, 1, 1, "year")]
    public void A_date_that_does_not_exist_is_refused(int year, int month, int day, string words)
    {
        Assert.Contains(words, SunClock.Compose(Autumn, year, month, day, null, null, out var when));
        Assert.Equal(Autumn, when);
    }

    [Fact]
    public void A_leap_day_is_a_day()
    {
        Assert.Null(SunClock.Compose(Autumn, 2028, 2, 29, 12, 0, out _));
    }

    [Theory]
    [InlineData(24, 0, "hour")]
    [InlineData(10, 60, "minute")]
    [InlineData(-1, 0, "hour")]
    public void A_time_that_does_not_exist_is_refused(int hour, int minute, string words)
    {
        Assert.Contains(words, SunClock.Compose(Autumn, null, null, null, hour, minute, out _));
    }

    [Fact]
    public void Half_a_date_or_half_a_time_is_refused()
    {
        Assert.Contains("year, month and day", SunClock.Compose(Autumn, 2026, 6, null, null, null, out _));
        Assert.Contains("hour and minute", SunClock.Compose(Autumn, null, null, null, 10, null, out _));
    }
}

/// <summary>Which lights a switch means (#63, D-87): by handle, else every light of that name.</summary>
public class LightPickTests
{
    private static readonly LightTag[] Lights =
    {
        new LightTag("2A1", "LIVING-DL-01"),
        new LightTag("2A2", "LIVING-DL-02"),
        new LightTag("3F0", "DL"), // inside the DOWNLIGHT block
        new LightTag("4B0", "DL"), // inside the PENDANT block
        new LightTag("2A3", ""),
    };

    [Fact]
    public void A_name_is_matched_whatever_its_case()
    {
        Assert.Null(LightPick.Resolve(Lights, new[] { "living-dl-02" }, out var picked));
        Assert.Equal(new[] { 1 }, picked);
    }

    [Fact]
    public void A_handle_is_matched_first()
    {
        Assert.Null(LightPick.Resolve(Lights, new[] { "3f0" }, out var picked));
        Assert.Equal(new[] { 2 }, picked);
    }

    [Fact]
    public void A_name_in_two_blocks_means_both()
    {
        Assert.Null(LightPick.Resolve(Lights, new[] { "DL" }, out var picked));
        Assert.Equal(new[] { 2, 3 }, picked);
    }

    [Fact]
    public void Each_light_is_picked_once_in_the_drawings_order()
    {
        Assert.Null(LightPick.Resolve(Lights, new[] { "LIVING-DL-02", "2A1", "living-dl-01", " " }, out var picked));
        Assert.Equal(new[] { 0, 1 }, picked);
    }

    [Fact]
    public void One_unknown_name_refuses_them_all_and_lists_what_there_is()
    {
        var why = LightPick.Resolve(Lights, new[] { "LIVING-DL-01", "KITCHEN-DL" }, out var picked);
        Assert.Empty(picked);
        Assert.Contains("'KITCHEN-DL'", why);
        Assert.Contains("LIVING-DL-01, LIVING-DL-02, DL, 2A3", why);
        Assert.Contains("autocad_list_lights", why);
    }

    [Fact]
    public void A_drawing_without_lights_says_so()
    {
        Assert.Contains("no lights", LightPick.Resolve(Array.Empty<LightTag>(), new[] { "DL" }, out _));
    }

    [Fact]
    public void A_long_list_is_cut_short_and_counted()
    {
        var many = Enumerable.Range(1, 25).Select(i => new LightTag(i.ToString("X"), "L" + i)).ToArray();
        var why = LightPick.Available(many);
        Assert.Contains("L20 and 5 more", why);
        Assert.DoesNotContain("L21", why);
    }

    [Fact]
    public void Nothing_asked_is_nothing_picked()
    {
        Assert.Null(LightPick.Resolve(Lights, Array.Empty<string>(), out var picked));
        Assert.Empty(picked);
    }
}
