using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The arithmetic of a flat view and a section plane (D-95): which way each
/// view looks and which way is right on it, where a section plane through
/// the modeller's points runs and which side it looks at, how views are set
/// out so they line up, and how the lines AutoCAD gives back are laid flat.
/// </summary>
public class SectionMathTests
{
    private static void Same(double[] expected, double[] actual)
    {
        Assert.Equal(expected.Length, actual.Length);
        for (var i = 0; i < expected.Length; i++) Assert.Equal(expected[i], actual[i], 9);
    }

    [Theory]
    // Looking from the south with Z up, east is to the right: the Front view.
    [InlineData("front", 1.0, 0.0, 0.0)]
    // From the east, north is to the right.
    [InlineData("right", 0.0, 1.0, 0.0)]
    [InlineData("left", 0.0, -1.0, 0.0)]
    [InlineData("back", -1.0, 0.0, 0.0)]
    // A plan: looking down, north up, east right.
    [InlineData("top", 1.0, 0.0, 0.0)]
    [InlineData("plan", 1.0, 0.0, 0.0)]
    public void Each_view_has_its_right_hand_where_a_draftsman_expects(string view, double x, double y, double z)
    {
        Assert.True(SectionMath.TryView(view, out var forward, out var up));
        Same(new[] { x, y, z }, SectionMath.Right(forward, up));
    }

    [Fact]
    public void No_view_is_mirrored_right_up_and_towards_the_viewer_are_right_handed()
    {
        foreach (var name in SectionMath.ViewNames)
        {
            SectionMath.TryView(name, out var forward, out var up);
            var right = SectionMath.Right(forward, up);
            // right x up = towards the viewer = -forward.
            Same(SectionMath.Scale(forward, -1), SectionMath.Cross(right, up));
        }
    }

    [Fact]
    public void An_unknown_view_is_not_a_view() => Assert.False(SectionMath.TryView("isometric", out _, out _));

    [Fact]
    public void A_flat_views_plane_is_outside_the_solids_on_the_viewers_side()
    {
        SectionMath.TryView("front", out var forward, out _);
        var point = SectionMath.OutsidePoint(new[] { 0.0, 0.0, 0.0 }, new[] { 1000.0, 600.0, 400.0 }, forward);
        // Looking north from the south: the plane is south of the box (y below 0), level with its centre.
        Assert.True(point[1] < 0);
        Assert.Equal(500.0, point[0], 9);
        Assert.Equal(200.0, point[2], 9);
    }

    [Fact]
    public void Two_points_cut_vertically_and_look_to_the_left_of_the_line()
    {
        Assert.Null(SectionMath.Plane(new List<double[]> { new[] { 0.0, 0.0 }, new[] { 10000.0, 0.0 } }, null, out var plane));
        Same(new[] { 1.0, 0.0, 0.0 }, plane.Along);
        Same(new[] { 0.0, 0.0, 1.0 }, plane.Up);
        // Walking east along the line, looking left is looking north.
        Same(new[] { 0.0, 1.0, 0.0 }, plane.Forward);
        // So the section reads left to right from the first point to the second.
        Same(new[] { 1.0, 0.0, 0.0 }, plane.Right);
    }

    [Fact]
    public void Look_towards_turns_the_section_round()
    {
        Assert.Null(SectionMath.Plane(new List<double[]> { new[] { 0.0, 0.0 }, new[] { 10000.0, 0.0 } }, new[] { 500.0, -3000.0 }, out var plane));
        Same(new[] { 0.0, -1.0, 0.0 }, plane.Forward);
        // Looking south, the line runs right to left.
        Same(new[] { -1.0, 0.0, 0.0 }, plane.Right);
    }

    [Fact]
    public void Three_points_at_one_level_are_a_plan_cut_looking_down_with_north_up()
    {
        var points = new List<double[]> { new[] { 0.0, 0.0, 2700.0 }, new[] { 0.0, 1000.0, 2700.0 }, new[] { 1000.0, 0.0, 2700.0 } };
        Assert.Null(SectionMath.Plane(points, null, out var plane));
        Same(new[] { 0.0, 0.0, -1.0 }, plane.Forward);
        Same(new[] { 0.0, 1.0, 0.0 }, plane.Up);
        Same(new[] { 1.0, 0.0, 0.0 }, plane.Right);
        Assert.Equal(2700.0, plane.Origin[2], 9);
    }

    [Fact]
    public void A_sloped_cut_keeps_up_as_near_world_up_as_the_plane_allows()
    {
        var points = new List<double[]> { new[] { 0.0, 0.0, 0.0 }, new[] { 1000.0, 0.0, 0.0 }, new[] { 0.0, 1000.0, 1000.0 } };
        Assert.Null(SectionMath.Plane(points, null, out var plane));
        Assert.True(plane.Up[2] > 0.7);
        Assert.Equal(0.0, SectionMath.Dot(plane.Up, plane.Forward), 9);
        Assert.Equal(0.0, SectionMath.Dot(plane.Right, plane.Forward), 9);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(4)]
    public void Not_two_or_three_points_is_refused(int count)
    {
        var points = Enumerable.Range(0, count).Select(i => new[] { (double)i, i * 2.0 }).ToList();
        Assert.NotNull(SectionMath.Plane(points, null, out _));
    }

    [Fact]
    public void Two_points_one_above_the_other_make_no_line_in_plan()
    {
        var error = SectionMath.Plane(new List<double[]> { new[] { 5.0, 5.0, 0.0 }, new[] { 5.0, 5.0, 3000.0 } }, null, out _);
        Assert.Contains("no line", error);
    }

    [Fact]
    public void Three_points_in_a_line_make_no_plane()
    {
        var points = new List<double[]> { new[] { 0.0, 0.0, 0.0 }, new[] { 1.0, 1.0, 1.0 }, new[] { 2.0, 2.0, 2.0 } };
        Assert.Contains("straight line", SectionMath.Plane(points, null, out _));
    }

    [Fact]
    public void A_look_towards_point_on_the_plane_names_no_side()
    {
        var error = SectionMath.Plane(new List<double[]> { new[] { 0.0, 0.0 }, new[] { 10.0, 0.0 } }, new[] { 5.0, 0.0, 100.0 }, out _);
        Assert.Contains("neither side", error);
    }

    [Fact]
    public void Third_angle_puts_the_plan_above_and_the_right_view_on_the_right_lined_up()
    {
        // Front 1000 wide, 400 high; top 1000 x 600; right 600 x 400; all round their own centres.
        var extents = new Dictionary<string, double[]>
        {
            ["front"] = new[] { -500.0, -200.0, 500.0, 200.0 },
            ["top"] = new[] { -500.0, -300.0, 500.0, 300.0 },
            ["right"] = new[] { -300.0, -200.0, 300.0, 200.0 },
        };
        var places = SectionMath.Layout(extents, "third", 100);
        Same(new[] { 0.0, 0.0 }, places["front"]);
        // Above, a gap of 100 between the front's top (200) and the plan's bottom.
        Same(new[] { 0.0, 200.0 + 100.0 + 300.0 }, places["top"]);
        // On the right, level with the front.
        Same(new[] { 500.0 + 100.0 + 300.0, 0.0 }, places["right"]);
    }

    [Fact]
    public void First_angle_puts_the_plan_below_and_the_right_view_on_the_left()
    {
        var extents = new Dictionary<string, double[]>
        {
            ["front"] = new[] { -500.0, -200.0, 500.0, 200.0 },
            ["top"] = new[] { -500.0, -300.0, 500.0, 300.0 },
            ["right"] = new[] { -300.0, -200.0, 300.0, 200.0 },
        };
        var places = SectionMath.Layout(extents, "first", 100);
        Same(new[] { 0.0, -200.0 - 100.0 - 300.0 }, places["top"]);
        Same(new[] { -500.0 - 100.0 - 300.0, 0.0 }, places["right"]);
    }

    [Fact]
    public void The_back_view_goes_beyond_the_right_view_in_third_angle()
    {
        var extents = new Dictionary<string, double[]>
        {
            ["front"] = new[] { -500.0, -200.0, 500.0, 200.0 },
            ["right"] = new[] { -300.0, -200.0, 300.0, 200.0 },
            ["back"] = new[] { -500.0, -200.0, 500.0, 200.0 },
        };
        var places = SectionMath.Layout(extents, "third", 100);
        Same(new[] { 900.0 + 300.0 + 100.0 + 500.0, 0.0 }, places["back"]);
    }

    [Fact]
    public void Without_a_front_view_the_others_are_set_out_from_the_insert_point()
    {
        var extents = new Dictionary<string, double[]> { ["top"] = new[] { -500.0, -300.0, 500.0, 300.0 } };
        var places = SectionMath.Layout(extents, "third", 50);
        Assert.False(places.ContainsKey("front"));
        Same(new[] { 0.0, 350.0 }, places["top"]);
    }

    [Fact]
    public void Lines_on_the_plane_are_turned_flat()
    {
        var points = new[] { new[] { 0.0, -100.0, 0.0 }, new[] { 500.0, -100.0, 400.0 } };
        Assert.Equal(Lying.Plane, SectionMath.Where(points, new[] { 0.0, -100.0, 0.0 }, new[] { 0.0, 1.0, 0.0 }));
    }

    [Fact]
    public void Lines_already_flat_in_plan_somewhere_else_are_only_moved()
    {
        var points = new[] { new[] { 0.0, 0.0, 0.0 }, new[] { 500.0, 300.0, 0.0 } };
        Assert.Equal(Lying.Flat, SectionMath.Where(points, new[] { 0.0, -100.0, 0.0 }, new[] { 0.0, 1.0, 0.0 }));
    }

    [Fact]
    public void Lines_spread_through_space_are_projected_first()
    {
        var points = new[] { new[] { 0.0, 0.0, 0.0 }, new[] { 500.0, 300.0, 200.0 } };
        Assert.Equal(Lying.Spread, SectionMath.Where(points, new[] { 0.0, -100.0, 0.0 }, new[] { 0.0, 1.0, 0.0 }));
    }
}
