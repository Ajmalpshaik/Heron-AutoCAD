using System;
using System.Collections.Generic;
using System.Linq;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// Hidden lines as the difference of two line sets (#171, D-151): what AutoCAD
/// gives with hidden lines on, less what it gives with them off. A line the
/// visible set covers is not hidden, even split differently or curved; a line
/// behind a visible one in the view is not drawn twice; a hidden edge whose
/// ends touch visible edges is still hidden.
/// </summary>
public class ObscuredLinesTests
{
    private const double Tol = 0.01;

    private static IList<double[]> Line(double x1, double y1, double x2, double y2, int points = 2)
    {
        var list = new List<double[]>();
        for (var k = 0; k < points; k++)
        {
            var t = points == 1 ? 0.5 : (double)k / (points - 1);
            list.Add(new[] { x1 + (x2 - x1) * t, y1 + (y2 - y1) * t });
        }
        return list;
    }

    private static IList<double[]> Probes(double x1, double y1, double x2, double y2) =>
        ObscuredLines.ProbeFractions().Select(t => new[] { x1 + (x2 - x1) * t, y1 + (y2 - y1) * t }).ToList();

    private static IList<double[]> Arc(double cx, double cy, double r, double from, double to, int points) =>
        Enumerable.Range(0, points).Select(k =>
        {
            var a = from + (to - from) * k / (points - 1);
            return new[] { cx + r * Math.Cos(a), cy + r * Math.Sin(a) };
        }).ToList();

    // A 100 x 50 box seen from the front, with a bore 10 below its top running right through it.
    private static List<IList<double[]>> Outline() => new List<IList<double[]>>
    {
        Line(0, 0, 100, 0), Line(100, 0, 100, 50), Line(100, 50, 0, 50), Line(0, 50, 0, 0),
    };

    [Fact]
    public void The_bore_is_hidden_and_the_outline_is_not()
    {
        var visible = Outline();
        var withHidden = Outline().Select(l => Probes(l[0][0], l[0][1], l[1][0], l[1][1])).ToList();
        withHidden.Add(Probes(0, 40, 100, 40));
        withHidden.Add(Probes(0, 30, 100, 30));
        var hidden = ObscuredLines.Hidden(withHidden, visible, Tol);
        Assert.Equal(new[] { false, false, false, false, true, true }, hidden);
    }

    [Fact]
    public void A_hidden_edge_whose_ends_touch_visible_edges_is_still_hidden()
    {
        // From the left side to the right side: both ends on the outline; the probes are not.
        var hidden = ObscuredLines.Hidden(new List<IList<double[]>> { Probes(0, 25, 100, 25) }, Outline(), Tol);
        Assert.True(hidden[0]);
    }

    [Fact]
    public void A_visible_line_split_differently_is_still_covered()
    {
        // The bottom edge comes back in one piece with hidden lines on, in three with them off.
        var visible = new List<IList<double[]>> { Line(0, 0, 30, 0), Line(30, 0, 70, 0), Line(70, 0, 100, 0) };
        var hidden = ObscuredLines.Hidden(new List<IList<double[]>> { Probes(0, 0, 100, 0) }, visible, Tol);
        Assert.False(hidden[0]);
    }

    [Fact]
    public void A_hidden_edge_straight_behind_a_visible_one_is_not_drawn_twice()
    {
        // Seen square on, the back edge lies on the front edge's line.
        var hidden = ObscuredLines.Hidden(new List<IList<double[]>> { Probes(20, 50, 80, 50) }, Outline(), Tol);
        Assert.False(hidden[0]);
    }

    [Fact]
    public void A_line_mostly_behind_is_hidden_and_mostly_on_a_visible_line_is_not()
    {
        var visible = new List<IList<double[]>> { Line(0, 0, 70, 0) };
        // Seven of nine probes on the visible line: covered.
        Assert.False(ObscuredLines.Hidden(new List<IList<double[]>> { Probes(0, 0, 90, 0) }, visible, Tol)[0]);
        // Two of nine: hidden.
        var shortVisible = new List<IList<double[]>> { Line(0, 0, 20, 0) };
        Assert.True(ObscuredLines.Hidden(new List<IList<double[]>> { Probes(0, 0, 90, 0) }, shortVisible, Tol)[0]);
    }

    [Fact]
    public void A_circle_is_covered_by_its_own_visible_samples_and_a_smaller_one_inside_is_hidden()
    {
        var visible = new List<IList<double[]>> { Arc(0, 0, 500, 0, 2 * Math.PI, ObscuredLines.CoverSamples) };
        // Probes at other angles than the samples, on the same circle.
        var same = ObscuredLines.ProbeFractions().Select(t => new[] { 500 * Math.Cos(2 * Math.PI * t), 500 * Math.Sin(2 * Math.PI * t) })
            .ToList();
        // A bore 3 inside the wall.
        var bore = ObscuredLines.ProbeFractions().Select(t => new[] { 497 * Math.Cos(2 * Math.PI * t), 497 * Math.Sin(2 * Math.PI * t) })
            .ToList();
        var hidden = ObscuredLines.Hidden(new List<IList<double[]>> { same, bore }, visible, ObscuredLines.Tolerance(1000));
        Assert.Equal(new[] { false, true }, hidden);
    }

    [Fact]
    public void With_nothing_visible_everything_is_hidden_and_a_line_with_no_probes_is_not()
    {
        var hidden = ObscuredLines.Hidden(new List<IList<double[]>> { Probes(0, 0, 1, 1), new List<double[]>() },
            new List<IList<double[]>>(), Tol);
        Assert.Equal(new[] { true, false }, hidden);
    }

    [Fact]
    public void Many_lines_are_quick_enough()
    {
        // 3000 visible lines and 3000 to test, as a big skid's view might give.
        var visible = Enumerable.Range(0, 3000).Select(i => Line(i, 0, i, 1000)).ToList();
        var withHidden = Enumerable.Range(0, 3000).Select(i => Probes(i + 0.5, 0, i + 0.5, 1000)).ToList();
        var watch = System.Diagnostics.Stopwatch.StartNew();
        var hidden = ObscuredLines.Hidden(withHidden, visible, Tol);
        Assert.True(hidden.All(h => h));
        Assert.True(watch.Elapsed.TotalSeconds < 10, "took " + watch.Elapsed);
    }

    [Fact]
    public void The_tolerance_is_a_ten_thousandth_of_the_view_and_the_probes_miss_the_ends()
    {
        Assert.Equal(0.2, ObscuredLines.Tolerance(2000), 9);
        Assert.Equal(1e-6, ObscuredLines.Tolerance(0), 12);
        var fractions = ObscuredLines.ProbeFractions();
        Assert.Equal(ObscuredLines.Probes, fractions.Length);
        Assert.True(fractions.Min() > 0 && fractions.Max() < 1);
    }
}
