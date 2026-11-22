using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The plug-in's own checks before it makes a spline by control points or
/// edits a spline's fit points (#56, D-97), and the levels of the three new
/// drafting operations. No AutoCAD: AutoCAD taking them is a live row.
/// </summary>
public class SplineCheckTests
{
    private static double[] Points(int count)
    {
        var flat = new double[count * 3];
        for (var i = 0; i < count; i++) flat[i * 3] = i * 100;
        return flat;
    }

    [Fact]
    public void A_clamped_cubic_of_five_points_is_accepted()
    {
        var knots = new double[] { 0, 0, 0, 0, 1, 2, 2, 2, 2 };
        Assert.Null(SplineCheck.ControlProblem(3, Points(5), knots));
    }

    [Fact]
    public void A_closed_cubic_wrapped_round_with_uniform_knots_is_accepted()
    {
        // Four points and the first three again: seven control points, eleven knots.
        var knots = new double[] { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 };
        Assert.Null(SplineCheck.ControlProblem(3, Points(7), knots));
    }

    [Theory]
    [InlineData(0, 5, 6, "degree")]
    [InlineData(11, 12, 24, "degree")]
    [InlineData(3, 3, 7, "at least 4")]
    [InlineData(3, 5, 8, "needs 9 knots")]
    public void A_spline_that_cannot_be_made_says_why(int degree, int count, int knotCount, string why)
    {
        var knots = new double[knotCount];
        for (var i = 0; i < knotCount; i++) knots[i] = i;
        var problem = SplineCheck.ControlProblem(degree, Points(count), knots);
        Assert.NotNull(problem);
        Assert.Contains(why, problem);
    }

    [Fact]
    public void Knots_that_go_down_or_give_no_length_are_refused()
    {
        Assert.Contains("never go down", SplineCheck.ControlProblem(1, Points(2), new double[] { 0, 2, 1, 3 }));
        Assert.Contains("no length", SplineCheck.ControlProblem(1, Points(2), new double[] { 0, 0, 0, 0 }));
        Assert.Contains("x, y, z", SplineCheck.ControlProblem(1, new double[] { 0, 0 }, new double[] { 0, 0, 1, 1 }));
        Assert.Contains("not a number", SplineCheck.ControlProblem(1, new double[] { 0, 0, 0, double.NaN, 0, 0 }, new double[] { 0, 0, 1, 1 }));
    }

    [Fact]
    public void Edits_are_walked_in_order_against_the_count()
    {
        var steps = new[]
        {
            new SplineCheck.Step("set", 0, 1, 1, 0),
            new SplineCheck.Step("insert", 3, 5, 5, 0),   // after the last of three
            new SplineCheck.Step("remove", 1, 0, 0, 0),
        };
        Assert.Null(SplineCheck.StepsProblem(3, steps, false));
    }

    [Fact]
    public void An_edit_off_the_end_or_one_leaving_too_few_is_refused()
    {
        Assert.Contains("there are 3", SplineCheck.StepsProblem(3, new[] { new SplineCheck.Step("set", 3, 0, 0, 0) }, false));
        Assert.Contains("there are 3", SplineCheck.StepsProblem(3, new[] { new SplineCheck.Step("insert", 4, 0, 0, 0) }, false));
        Assert.Contains("needs 2", SplineCheck.StepsProblem(2, new[] { new SplineCheck.Step("remove", 0, 0, 0, 0) }, false));
        Assert.Contains("closed spline needs 3", SplineCheck.StepsProblem(3, new[] { new SplineCheck.Step("remove", 0, 0, 0, 0) }, true));
        Assert.Contains("sets, inserts or removes", SplineCheck.StepsProblem(3, new[] { new SplineCheck.Step("swap", 0, 0, 0, 0) }, false));
    }

    [Fact]
    public void Points_read_back_are_compared_to_a_hair()
    {
        Assert.True(SplineCheck.SamePoints(new[] { 1000.0, 2.0, 0.0 }, new[] { 1000.0000001, 2.0, 0.0 }));
        Assert.False(SplineCheck.SamePoints(new[] { 1000.0, 2.0, 0.0 }, new[] { 1000.1, 2.0, 0.0 }));
        Assert.False(SplineCheck.SamePoints(new[] { 1.0, 2.0, 0.0 }, new[] { 1.0, 2.0 }));
    }

    [Fact]
    public void The_drafting_operations_are_changes()
    {
        foreach (var name in new[] { "close_multiline", "add_cv_spline", "edit_spline_fit_points" })
        {
            Assert.True(PluginOperations.TryLevel(name, out var level), name);
            Assert.Equal(Risk.Change, level);
        }
    }
}
