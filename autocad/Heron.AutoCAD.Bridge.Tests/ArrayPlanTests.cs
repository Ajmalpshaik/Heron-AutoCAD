using System;
using System.Collections.Generic;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// Associative arrays (D-110): where each item's base point goes, and the
/// check that refuses an array AutoCAD built somewhere other than asked.
/// </summary>
public class ArrayPlanTests
{
    [Fact]
    public void A_grid_starts_at_the_base_point_and_goes_row_by_row()
    {
        Assert.Null(ArrayPlan.Rectangular(new[] { 100.0, 50.0 }, 2, 3, 150, 200, out var points));
        Assert.Equal(6, points.Count);
        Assert.Equal(new[] { 100.0, 50.0 }, points[0]);
        Assert.Equal(new[] { 500.0, 50.0 }, points[2]);
        Assert.Equal(new[] { 100.0, 200.0 }, points[3]);
        Assert.Equal(new[] { 500.0, 200.0 }, points[5]);
    }

    [Fact]
    public void A_negative_spacing_builds_down_and_left()
    {
        Assert.Null(ArrayPlan.Rectangular(new[] { 0.0, 0.0 }, 2, 2, -10, -20, out var points));
        Assert.Equal(new[] { -20.0, -10.0 }, points[3]);
    }

    [Theory]
    [InlineData(1, 1, 10, 10, "1 x 1")]
    [InlineData(2, 1, 0, 10, "row spacing")]
    [InlineData(1, 3, 10, 0, "column spacing")]
    [InlineData(0, 3, 10, 10, "1 or more")]
    [InlineData(101, 100, 10, 10, "at most 10000")]
    public void A_grid_that_makes_no_sense_is_refused(int rows, int columns, double rowSpacing, double columnSpacing, string words)
    {
        var why = ArrayPlan.Rectangular(new[] { 0.0, 0.0 }, rows, columns, rowSpacing, columnSpacing, out var points);
        Assert.NotNull(why);
        Assert.Contains(words, why);
        Assert.Empty(points);
    }

    [Fact]
    public void A_full_ring_spreads_the_items_evenly_from_the_original()
    {
        Assert.Null(ArrayPlan.Polar(new[] { 0.0, 0.0 }, new[] { 100.0, 0.0 }, 4, 2 * Math.PI, true,
            out var step, out var radius, out var start, out var points));
        Assert.Equal(Math.PI / 2, step, 12);
        Assert.Equal(100, radius, 12);
        Assert.Equal(0, start, 12);
        Assert.Equal(4, points.Count);
        Assert.Equal(0, points[1][0], 9);
        Assert.Equal(100, points[1][1], 9);
        Assert.Equal(-100, points[2][0], 9);
    }

    [Fact]
    public void Part_of_a_ring_puts_the_last_item_at_the_end_of_the_angle()
    {
        Assert.Null(ArrayPlan.Polar(new[] { 10.0, 10.0 }, new[] { 10.0, 60.0 }, 3, Math.PI / 2, false,
            out var step, out _, out var start, out var points));
        Assert.Equal(Math.PI / 4, step, 12);
        Assert.Equal(Math.PI / 2, start, 12);
        Assert.Equal(-40, points[2][0], 9);
        Assert.Equal(10, points[2][1], 9);
    }

    [Fact]
    public void Items_that_turn_about_their_own_centre_are_allowed()
    {
        Assert.Null(ArrayPlan.Polar(new[] { 5.0, 5.0 }, new[] { 5.0, 5.0 }, 6, 2 * Math.PI, true, out _, out var radius, out _, out var points));
        Assert.Equal(0, radius);
        Assert.All(points, p => Assert.Equal(new[] { 5.0, 5.0 }, p));
    }

    [Fact]
    public void Items_that_neither_move_nor_turn_are_refused()
    {
        var why = ArrayPlan.Polar(new[] { 5.0, 5.0 }, new[] { 5.0, 5.0 }, 6, 2 * Math.PI, false, out _, out _, out _, out _);
        Assert.Contains("land on the original", why);
    }

    [Theory]
    [InlineData(1, 6.28)]
    [InlineData(4, 0)]
    [InlineData(4, -1)]
    [InlineData(4, 7)]
    public void A_ring_that_makes_no_sense_is_refused(int count, double fill)
    {
        Assert.NotNull(ArrayPlan.Polar(new[] { 0.0, 0.0 }, new[] { 1.0, 0.0 }, count, fill, true, out _, out _, out _, out _));
    }

    [Fact]
    public void Dividing_an_open_path_puts_the_first_and_last_at_the_ends()
    {
        Assert.Null(ArrayPlan.Path(9000, false, 4, 0, out var items, out var step));
        Assert.Equal(4, items);
        Assert.Equal(3000, step, 12);
    }

    [Fact]
    public void Dividing_a_closed_path_spreads_them_all_the_way_round()
    {
        Assert.Null(ArrayPlan.Path(1200, true, 4, 0, out var items, out var step));
        Assert.Equal(4, items);
        Assert.Equal(300, step, 12);
    }

    [Fact]
    public void Measuring_fits_as_many_as_the_spacing_allows()
    {
        // Hangers every 1500 along a 10 m duct: 0, 1500 ... 9000.
        Assert.Null(ArrayPlan.Path(10000, false, 0, 1500, out var items, out var step));
        Assert.Equal(7, items);
        Assert.Equal(1500, step);
        Assert.Null(ArrayPlan.Path(9000, false, 0, 1500, out items, out _));
        Assert.Equal(7, items);
    }

    [Fact]
    public void Measuring_with_a_count_takes_that_many()
    {
        Assert.Null(ArrayPlan.Path(10000, false, 3, 1500, out var items, out _));
        Assert.Equal(3, items);
    }

    [Fact]
    public void More_than_fit_on_the_path_is_refused_with_the_most_that_fit()
    {
        var why = ArrayPlan.Path(10000, false, 9, 1500, out _, out _);
        Assert.Contains("at most 7 fit", why);
    }

    [Theory]
    [InlineData(0, false, 4, 0, "no length")]
    [InlineData(1000, false, 1, 0, "2 items")]
    [InlineData(1000, false, 0, 2000, "longer than the path")]
    [InlineData(1000, false, 0, -5, "above zero")]
    [InlineData(1000, true, 0, 1000, "Only one")]
    [InlineData(1000, false, 0, 0.01, "at most 10000")]
    public void A_run_that_makes_no_sense_is_refused(double length, bool closed, int count, double spacing, string words)
    {
        Assert.Contains(words, ArrayPlan.Path(length, closed, count, spacing, out _, out _));
    }

    // The source: a 100 x 50 box with its base point at its lower-left corner.
    private static readonly double[] SourceMin = { 0, 0 };
    private static readonly double[] SourceMax = { 100, 50 };
    private static readonly double[] Base = { 0, 0 };

    private static List<double[]> Grid()
    {
        Assert.Null(ArrayPlan.Rectangular(Base, 2, 3, 200, 300, out var points));
        return points;
    }

    [Fact]
    public void A_grid_built_where_asked_passes()
    {
        Assert.Null(ArrayPlan.Check(new[] { 0.0, 0.0 }, new[] { 700.0, 250.0 }, Grid(), SourceMin, SourceMax, Base, false));
    }

    [Fact]
    public void A_grid_built_one_spacing_off_is_refused()
    {
        var why = ArrayPlan.Check(new[] { 300.0, 0.0 }, new[] { 1000.0, 250.0 }, Grid(), SourceMin, SourceMax, Base, false);
        Assert.Contains("somewhere other than asked", why);
        Assert.Contains("(0, 0) to (700, 250)", why);
    }

    [Fact]
    public void A_grid_with_the_spacing_read_wrong_is_refused()
    {
        // Columns 30 apart instead of 300: the right start, far too short.
        Assert.NotNull(ArrayPlan.Check(new[] { 0.0, 0.0 }, new[] { 160.0, 250.0 }, Grid(), SourceMin, SourceMax, Base, false));
    }

    [Fact]
    public void Text_extents_a_hair_out_still_pass()
    {
        Assert.Null(ArrayPlan.Check(new[] { -0.5, 0.2 }, new[] { 700.4, 249.7 }, Grid(), SourceMin, SourceMax, Base, false));
    }

    [Fact]
    public void A_ring_that_turns_is_judged_by_the_reach_of_its_items()
    {
        // A 20 x 20 bolt head at radius 100 about 0,0, its base point at its centre.
        var min = new[] { 90.0, -10.0 };
        var max = new[] { 110.0, 10.0 };
        var basePoint = new[] { 100.0, 0.0 };
        Assert.Null(ArrayPlan.Polar(new[] { 0.0, 0.0 }, basePoint, 8, 2 * Math.PI, true, out _, out _, out _, out var points));
        Assert.Null(ArrayPlan.Check(new[] { -110.0, -110.0 }, new[] { 110.0, 110.0 }, points, min, max, basePoint, true));
        // Built round the bolt instead of round 0,0.
        Assert.NotNull(ArrayPlan.Check(new[] { -10.0, -110.0 }, new[] { 210.0, 110.0 }, points, min, max, basePoint, true));
        // Angles read as degrees where radians were meant: all bunched by the original.
        Assert.NotNull(ArrayPlan.Check(new[] { 89.0, -10.0 }, new[] { 110.0, 25.0 }, points, min, max, basePoint, true));
    }

    [Fact]
    public void A_block_whose_insertion_point_is_off_its_drawing_still_checks()
    {
        // The block's lines sit 500 to the right of its insertion point at 0,0.
        var min = new[] { 500.0, 0.0 };
        var max = new[] { 600.0, 50.0 };
        Assert.Null(ArrayPlan.Rectangular(Base, 1, 3, 0, 1000, out var points));
        Assert.Null(ArrayPlan.Check(new[] { 500.0, 0.0 }, new[] { 2600.0, 50.0 }, points, min, max, Base, false));
    }

    [Fact]
    public void An_empty_plan_is_refused()
    {
        Assert.NotNull(ArrayPlan.Check(new[] { 0.0, 0.0 }, new[] { 1.0, 1.0 }, new List<double[]>(), SourceMin, SourceMax, Base, false));
    }
}
