using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The pyramid, the polysolid and the face edits (D-112, D-113): the sums the
/// plug-in leans on, checked without AutoCAD.
/// </summary>
public class PyramidMathTests
{
    /// <summary>A pyramid's corners as AutoCAD might make it: about the origin, half way up, turned its own way.</summary>
    private static List<double[]> Made(int sides, double cornerRadius, double topCornerRadius, double height, double firstAngle)
    {
        var points = new List<double[]>();
        for (var k = 0; k < sides; k++)
        {
            var a = firstAngle + 2 * Math.PI * k / sides;
            points.Add(new[] { cornerRadius * Math.Cos(a), cornerRadius * Math.Sin(a), -height / 2 });
        }
        if (topCornerRadius == 0) points.Add(new[] { 0.0, 0.0, height / 2 });
        else
            for (var k = 0; k < sides; k++)
            {
                var a = firstAngle + 2 * Math.PI * k / sides;
                points.Add(new[] { topCornerRadius * Math.Cos(a), topCornerRadius * Math.Sin(a), height / 2 });
            }
        return points;
    }

    [Fact]
    public void A_600_square_base_900_high_is_108_million()
    {
        // Radius 300 to the middle of a side: a 600 x 600 base.
        Assert.Equal(360000.0, PyramidMath.Area(300, 4), 6);
        Assert.Equal(108_000_000.0, PyramidMath.Volume(900, 4, 300, 0), 3);
    }

    [Fact]
    public void A_frustum_adds_the_top_and_the_mean()
    {
        // A1 = 360,000, A2 = 90,000, sqrt(A1 A2) = 180,000: 900/3 x 630,000.
        Assert.Equal(189_000_000.0, PyramidMath.Volume(900, 4, 300, 150), 3);
    }

    [Fact]
    public void A_radius_to_a_corner_becomes_one_to_a_side()
    {
        Assert.Equal(300.0, PyramidMath.ToSide(300 * Math.Sqrt(2), 4, toCorner: true), 9);
        Assert.Equal(300.0, PyramidMath.ToSide(300, 4, toCorner: false), 9);
        Assert.Equal(300 * Math.Sqrt(2), PyramidMath.CornerRadius(300, 4), 9);
        // A hexagon: the side is cos(30) of the corner.
        Assert.Equal(Math.Cos(Math.PI / 6) * 100, PyramidMath.ToSide(100, 6, toCorner: true), 9);
    }

    [Theory]
    [InlineData(2, 300.0, 0.0, 900.0, "3 to 32 sides")]
    [InlineData(33, 300.0, 0.0, 900.0, "3 to 32 sides")]
    [InlineData(4, 300.0, 0.0, 0.0, "height")]
    [InlineData(4, -1.0, 0.0, 900.0, "below zero")]
    [InlineData(4, 0.0, 0.0, 900.0, "needs a base")]
    public void Sizes_that_make_no_pyramid_are_named(int sides, double bottom, double top, double height, string words)
    {
        var error = PyramidMath.Check(sides, bottom, top, height);
        Assert.NotNull(error);
        Assert.Contains(words, error);
    }

    [Fact]
    public void A_hopper_wider_at_the_top_and_a_prism_are_fine()
    {
        Assert.Null(PyramidMath.Check(4, 100, 400, 600));
        Assert.Null(PyramidMath.Check(4, 0, 400, 600));
        Assert.Null(PyramidMath.Check(6, 200, 200, 600));
    }

    [Theory]
    [InlineData(4, 0.0)]
    [InlineData(4, 0.3)]
    [InlineData(3, 1.0)]
    [InlineData(5, -2.0)]
    [InlineData(6, 0.0)]
    [InlineData(8, 0.1)]
    public void Turned_by_the_answer_one_side_faces_the_front(int sides, double madeAngle)
    {
        var corners = Made(sides, 500, 0, 900, madeAngle);
        Assert.True(PyramidMath.WideEnd(corners, out var centre, out var angle, out var radius, out var low, out var high));
        Assert.Equal(0.0, centre[0], 9);
        Assert.Equal(0.0, centre[1], 9);
        Assert.Equal(500.0, radius, 6);
        Assert.Equal(-450.0, low, 9);
        Assert.Equal(450.0, high, 9);

        var turn = PyramidMath.Turn(angle, sides, 0);
        Assert.True(Math.Abs(turn) <= Math.PI / sides + 1e-9, "never more than half a side");
        // After the turn, the lowest Y of the base is the middle of a side, square to the front.
        var lowestY = corners.Take(sides).Min(p => radius * Math.Sin(Math.Atan2(p[1], p[0]) + turn));
        var sideRadius = radius * Math.Cos(Math.PI / sides);
        var twoLowest = corners.Take(sides).Select(p => radius * Math.Sin(Math.Atan2(p[1], p[0]) + turn)).OrderBy(y => y).Take(2).ToArray();
        Assert.Equal(-sideRadius, twoLowest[0], 6);
        Assert.Equal(-sideRadius, twoLowest[1], 6);
        Assert.Equal(-sideRadius, lowestY, 6);
    }

    [Fact]
    public void A_turn_asked_for_is_added()
    {
        // A square made with a corner at 0: 45 degrees puts a side to the front;
        // asking for 45 more puts a corner there instead.
        Assert.Equal(Math.PI / 4, PyramidMath.Turn(0, 4, 0), 9);
        var corner = PyramidMath.Turn(0, 4, Math.PI / 4);
        Assert.Equal(0.0, Math.Abs(Math.Sin(2 * corner)), 9);
    }

    [Fact]
    public void A_hoppers_wide_end_is_found_at_the_top()
    {
        // Made the usual way (400 at the bottom), then turned over about X:
        // the 400 end is up, the 100 end down.
        var corners = Made(4, 400, 100, 600, 0.2).Select(p => new[] { p[0], -p[1], -p[2] }).ToList();
        Assert.True(PyramidMath.WideEnd(corners, out var centre, out _, out var radius, out var low, out var high));
        Assert.Equal(400.0, radius, 6);
        Assert.Equal(300.0, centre[2], 9);
        Assert.Equal(-300.0, low, 9);
        Assert.Equal(300.0, high, 9);
    }

    [Fact]
    public void Too_few_corners_to_go_by()
    {
        Assert.False(PyramidMath.WideEnd(new List<double[]>(), out _, out _, out _, out _, out _));
        Assert.False(PyramidMath.WideEnd(new List<double[]> { new[] { 0.0, 0, 0 }, new[] { 1.0, 0, 0 } }, out _, out _, out _, out _, out _));
    }
}

public class PolysolidMathTests
{
    [Theory]
    [InlineData("center", 100.0, -100.0)]
    [InlineData("centre", 100.0, -100.0)]
    [InlineData("", 100.0, -100.0)]
    [InlineData("left", 200.0, 0.0)]
    [InlineData("right", 0.0, -200.0)]
    [InlineData("LEFT", 200.0, 0.0)]
    public void The_walls_faces_are_measured_to_the_left_of_the_path(string side, double first, double second)
    {
        Assert.Null(PolysolidMath.Faces(200, 3000, side, out var a, out var b));
        Assert.Equal(first, a, 9);
        Assert.Equal(second, b, 9);
    }

    [Theory]
    [InlineData(0.0, 3000.0, "center", "width")]
    [InlineData(200.0, 0.0, "center", "height")]
    [InlineData(200.0, 3000.0, "middle", "not a side")]
    public void A_wall_that_cannot_be_made_says_why(double width, double height, string side, string words)
    {
        var error = PolysolidMath.Faces(width, height, side, out _, out _);
        Assert.NotNull(error);
        Assert.Contains(words, error);
    }

    [Fact]
    public void Left_and_right_are_as_you_walk_along_the_path()
    {
        // Heading east (+X): north (+Y) is on the left.
        Assert.Equal(1, PolysolidMath.LeftOf(1, 0, 0, 5));
        Assert.Equal(-1, PolysolidMath.LeftOf(1, 0, 0, -5));
        // Heading north: west is on the left.
        Assert.Equal(1, PolysolidMath.LeftOf(0, 1, -5, 0));
        // Along the path itself, or no heading: cannot tell.
        Assert.Equal(0, PolysolidMath.LeftOf(1, 0, 5, 0));
        Assert.Equal(0, PolysolidMath.LeftOf(0, 0, 0, 5));
    }

    [Theory]
    [InlineData("inside", true, "left")]
    [InlineData("outside", true, "right")]
    [InlineData("inside", false, "right")]
    [InlineData("outside", false, "left")]
    public void Inside_a_closed_path_depends_on_which_way_it_runs(string side, bool anticlockwise, string resolved)
    {
        Assert.Equal(resolved, PolysolidMath.Resolve(side, closed: true, anticlockwise, out var error));
        Assert.Null(error);
    }

    [Fact]
    public void Inside_an_open_path_is_refused()
    {
        PolysolidMath.Resolve("inside", closed: false, anticlockwise: true, out var error);
        Assert.NotNull(error);
        Assert.Contains("closed path", error);
        Assert.Equal("center", PolysolidMath.Resolve("centre", closed: false, anticlockwise: true, out var none));
        Assert.Null(none);
        Assert.Equal("left", PolysolidMath.Resolve("Left", closed: false, anticlockwise: true, out _));
    }
}

public class FaceEditMathTests
{
    [Fact]
    public void A_wall_face_tapers_from_its_bottom_edge()
    {
        // The front face of a 1000 x 600 x 500 box: y = 0, x 0-1000, z 0-500.
        var pivot = FaceEditMath.TaperBase(new List<double[]> { new[] { 0.0, 0, 0 } }, new List<double[]> { new[] { 1000.0, 0, 500 } }, new[] { 0.0, 0, 1 });
        Assert.NotNull(pivot);
        Assert.Equal(new[] { 500.0, 0, 0 }, pivot);
    }

    [Fact]
    public void Tapering_downwards_pivots_at_the_top()
    {
        var pivot = FaceEditMath.TaperBase(new List<double[]> { new[] { 0.0, 0, 0 } }, new List<double[]> { new[] { 1000.0, 0, 500 } }, new[] { 0.0, 0, -2 });
        Assert.Equal(new[] { 500.0, 0, 500 }, pivot);
    }

    [Fact]
    public void Several_faces_share_the_lowest_plane()
    {
        // Two side faces, one starting higher: the plane is at the lower one's bottom.
        var pivot = FaceEditMath.TaperBase(
            new List<double[]> { new[] { 0.0, 0, 100 }, new[] { 0.0, 600, 0 } },
            new List<double[]> { new[] { 1000.0, 0, 500 }, new[] { 1000.0, 600, 500 } },
            new[] { 0.0, 0, 1 });
        Assert.Equal(new[] { 500.0, 300, 0 }, pivot);
    }

    [Fact]
    public void A_direction_with_no_length_gives_nothing()
    {
        Assert.Null(FaceEditMath.TaperBase(new List<double[]> { new[] { 0.0, 0, 0 } }, new List<double[]> { new[] { 1.0, 1, 1 } }, new[] { 0.0, 0, 0 }));
        Assert.Null(FaceEditMath.Unit(new[] { 0.0, 0 }));
        Assert.Null(FaceEditMath.Unit(new[] { double.NaN, 0, 1 }));
        Assert.Equal(new[] { 0.0, 0.6, 0.8 }, FaceEditMath.Unit(new[] { 0.0, 3, 4 }));
    }

    [Fact]
    public void The_new_operations_are_changes()
    {
        foreach (var name in new[] { "add_pyramid", "add_polysolid", "offset_faces", "taper_faces", "move_faces", "delete_faces", "imprint_solid", "separate_solid" })
        {
            Assert.True(PluginOperations.TryLevel(name, out var level), name);
            Assert.Equal(Risk.Change, level);
        }
    }
}
