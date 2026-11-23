using System.Collections.Generic;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// A jogged section line (#171, D-152): its legs, which are jogs, and where a
/// point on each leg lands on the 2D section. Legs parallel to each other read
/// as one straight section (the jog takes no width); a leg at an angle is
/// turned flat at true size beside the one before; a leg walking back is refused.
/// </summary>
public class JoggedSectionTests
{
    private const double Tol = 1e-6;

    private static double[] P(double x, double y, double z = 0) => new[] { x, y, z };

    private static JoggedSection Make(double[]? look, params double[][] corners)
    {
        var error = JoggedSection.Build(corners, look, out var section);
        Assert.Null(error);
        return section!;
    }

    private static void Same(double[] expected, double[] actual)
    {
        Assert.Equal(expected.Length, actual.Length);
        for (var i = 0; i < expected.Length; i++) Assert.Equal(expected[i], actual[i], 9);
    }

    // An offset section looking north: a leg along y=500, a jog north to y=2500, a leg along y=2500.
    private static JoggedSection Offset() => Make(null, P(-500, 500, 100), P(2000, 500), P(2000, 2500), P(4500, 2500));

    [Fact]
    public void An_offset_section_has_two_legs_drawn_and_one_jog()
    {
        var s = Offset();
        Assert.Equal(3, s.Legs.Count);
        Assert.Equal(new[] { false, true, false }, new[] { s.Legs[0].IsJog, s.Legs[1].IsJog, s.Legs[2].IsJog });
        Assert.Equal(1, s.Jogs);
        // Walk east, look left: north. Right on the section is east.
        Same(P(0, 1, 0), s.Forward);
        Same(P(1, 0, 0), s.Right);
    }

    [Fact]
    public void Every_corner_is_taken_at_the_first_ones_level()
    {
        var s = Offset();
        foreach (var leg in s.Legs)
        {
            Assert.Equal(100.0, leg.Start[2], 9);
            Assert.Equal(100.0, leg.End[2], 9);
        }
    }

    [Fact]
    public void Parallel_legs_land_where_one_straight_projection_puts_them()
    {
        var s = Offset();
        // A point on the far leg 1000 up: east of the first corner by 3500, so x = 3500 as projected.
        var on = P(3000, 2500, 1100);
        Same(new[] { 3500.0, 1000.0 }, s.ToSheet(on, 2));
        // And the near leg the same way.
        Same(new[] { 1000.0, 0.0 }, s.ToSheet(P(500, 500, 100), 0));
        // The jog takes no width: the far leg starts where the near one ends.
        Assert.Equal(s.Legs[0].Offset + s.Legs[0].Length, s.Legs[2].Offset, 9);
    }

    [Fact]
    public void A_line_on_a_leg_is_found_on_that_leg_and_a_corner_line_on_the_drawn_leg()
    {
        var s = Offset();
        Assert.Equal(0, s.LegOf(new List<double[]> { P(0, 500, 0), P(1000, 500, 1000) }, Tol));
        Assert.Equal(2, s.LegOf(new List<double[]> { P(3000, 2500, 0), P(4000, 2500, 0) }, Tol));
        Assert.Equal(1, s.LegOf(new List<double[]> { P(2000, 1000, 0), P(2000, 2000, 0) }, Tol));
        // Up the corner between the first leg and the jog: on both, the drawn leg wins.
        Assert.Equal(0, s.LegOf(new List<double[]> { P(2000, 500, 0), P(2000, 500, 1000) }, Tol));
        // Off every leg.
        Assert.Equal(-1, s.LegOf(new List<double[]> { P(0, 600, 0) }, Tol));
        // On the first leg's line past its end corner, where the next leg has turned off: on no leg.
        Assert.Equal(-1, s.LegOf(new List<double[]> { P(2100, 500, 0) }, Tol));
        // Past the first corner and past the last: the end legs reach on, as a section plane's cut does.
        Assert.Equal(0, s.LegOf(new List<double[]> { P(-5000, 500, 0) }, Tol));
        Assert.Equal(2, s.LegOf(new List<double[]> { P(9000, 2500, 0) }, Tol));
    }

    [Fact]
    public void What_is_seen_beyond_goes_on_the_nearest_leg_in_front_of_it()
    {
        var s = Offset();
        Assert.Equal(0, s.Behind(P(0, 900, 300), Tol));
        Assert.Equal(2, s.Behind(P(3500, 2900, 300), Tol));
        // Between the two legs but over the far one: in front of the cut, not behind it.
        Assert.Equal(-1, s.Behind(P(3500, 1500, 300), Tol));
        // Beyond the first corner the first leg still cuts, so what is behind it there is seen through it.
        Assert.Equal(0, s.Behind(P(-900, 900, 0), Tol));
        // In front of every leg.
        Assert.Equal(-1, s.Behind(P(1000, 0, 0), Tol));
    }

    [Fact]
    public void A_leg_at_an_angle_is_turned_flat_at_true_size_beside_the_one_before()
    {
        // East 1000, then north-east 1000 * sqrt 2 (45 degrees): looking north.
        var s = Make(null, P(0, 0), P(1000, 0), P(2000, 1000));
        Assert.False(s.Legs[1].IsJog);
        Assert.Equal(1000.0, s.Legs[1].Offset, 9);
        // Halfway along the angled leg: 1000 + half its true length across.
        var mid = P(1500, 500, 250);
        Same(new[] { 1000.0 + 0.5 * System.Math.Sqrt(2) * 1000, 250.0 }, s.ToSheet(mid, 1));
        // The leg looks square to itself, on the section's side.
        Assert.True(SectionMath.Dot(s.Legs[1].Forward, s.Forward) > 0);
        Assert.Equal(0.0, SectionMath.Dot(s.Legs[1].Forward, s.Legs[1].Along), 9);
    }

    [Fact]
    public void No_leg_is_mirrored_right_up_and_towards_the_viewer_are_right_handed()
    {
        var s = Make(P(0, -10), P(0, 0), P(1000, 0), P(1000, -800), P(3000, -1500));
        foreach (var leg in s.Legs)
            Same(SectionMath.Scale(leg.Forward, -1), SectionMath.Cross(leg.Right, JoggedSection.Up));
    }

    [Fact]
    public void Looking_the_other_way_reads_right_to_left_along_the_walk()
    {
        // Walk east, look south: right on the section is west, so the walk goes leftwards.
        var s = Make(P(0, -100), P(0, 0), P(1000, 0), P(1000, -500), P(3000, -500));
        Same(P(0, -1, 0), s.Forward);
        Same(P(-1, 0, 0), s.Right);
        Same(new[] { -2000.0, 0.0 }, s.ToSheet(P(2000, -500, 0), 2));
        Assert.True(s.Legs[1].IsJog);
    }

    [Fact]
    public void A_nearly_square_jog_counts_as_a_jog_but_two_degrees_off_does_not()
    {
        var half = Make(null, P(0, 0), P(1000, 0), P(1000 + 1000 * System.Math.Tan(0.5 * System.Math.PI / 180), 1000), P(3000, 1000));
        Assert.True(half.Legs[1].IsJog);
        var two = Make(null, P(0, 0), P(1000, 0), P(1000 + 1000 * System.Math.Tan(2 * System.Math.PI / 180), 1000), P(3000, 1000));
        Assert.False(two.Legs[1].IsJog);
    }

    [Theory]
    // A U: east, north, then back west over the first leg as seen.
    [InlineData("walks back", 0, 0, 1000, 0, 1000, 1000, 0, 1000)]
    // Straight back on itself.
    [InlineData("straight back", 0, 0, 1000, 0, 500, 0, 500, 500)]
    // Two corners the same in plan.
    [InlineData("same in plan", 0, 0, 1000, 0, 1000, 0, 2000, 0)]
    public void A_line_that_folds_back_or_repeats_a_corner_is_refused(string words, double x1, double y1, double x2, double y2,
        double x3, double y3, double x4, double y4)
    {
        var corners = new[] { P(x1, y1), P(x2, y2), P(x3, y3), P(x4, y4) };
        var error = JoggedSection.Build(corners, null, out var section);
        Assert.Null(section);
        Assert.Contains(words, error);
    }

    [Fact]
    public void Look_towards_on_the_first_legs_line_is_refused()
    {
        var error = JoggedSection.Build(new[] { P(0, 0), P(1000, 0), P(1000, 500) }, P(5000, 0), out _);
        Assert.Contains("neither side", error);
    }

    [Fact]
    public void One_corner_is_not_a_line()
    {
        Assert.NotNull(JoggedSection.Build(new[] { P(0, 0) }, null, out _));
        Assert.NotNull(JoggedSection.Build(new[] { P(0, 0), new[] { 1.0 } }, null, out _));
    }

    [Fact]
    public void Lines_all_on_legs_are_on_the_plane_all_level_are_flat_otherwise_spread()
    {
        var s = Offset();
        var onLegs = new List<IList<double[]>>
        {
            new List<double[]> { P(0, 500, 0), P(1000, 500, 0) },
            new List<double[]> { P(3000, 2500, 0), P(3000, 2500, 900) },
        };
        Assert.Equal(Lying.Plane, s.Where(onLegs, Tol));
        var level = new List<IList<double[]>>
        {
            new List<double[]> { P(9000, 9000, 0), P(9500, 9000, 0) },
            new List<double[]> { P(9000, 9500, 0) },
        };
        Assert.Equal(Lying.Flat, s.Where(level, Tol));
        var spread = new List<IList<double[]>>
        {
            new List<double[]> { P(0, 500, 0), P(1000, 500, 0) },
            new List<double[]> { P(0, 900, 0), P(0, 900, 800) },
        };
        Assert.Equal(Lying.Spread, s.Where(spread, Tol));
    }
}
