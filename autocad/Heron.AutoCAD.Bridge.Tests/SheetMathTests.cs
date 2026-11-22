using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The arithmetic behind a sheet the plug-in makes (#64, #65, D-90): the sheet
/// size picked from a plotter's list, the view centre of a twisted viewport, the
/// name of a scale and a clip outline.
/// </summary>
public class SheetMathTests
{
    private static readonly string[] PdfSizes =
    {
        "ISO_expand_A3_(420.00_x_297.00_MM)",
        "ISO_A3_(297.00_x_420.00_MM)",
        "ISO_A3_(420.00_x_297.00_MM)",
        "ISO_full_bleed_A3_(297.00_x_420.00_MM)",
        "ISO_full_bleed_A3_(420.00_x_297.00_MM)",
        "ISO_full_bleed_A1_(841.00_x_594.00_MM)",
        "ANSI_full_bleed_D_(34.00_x_22.00_Inches)",
    };

    [Fact]
    public void A_short_name_picks_the_full_bleed_landscape_sheet()
    {
        Assert.Equal("ISO_full_bleed_A3_(420.00_x_297.00_MM)", SheetMath.MatchMedia(PdfSizes, "A3"));
        Assert.Equal("ISO_full_bleed_A1_(841.00_x_594.00_MM)", SheetMath.MatchMedia(PdfSizes, "a1"));
    }

    [Fact]
    public void Portrait_turns_it_upright()
    {
        Assert.Equal("ISO_full_bleed_A3_(297.00_x_420.00_MM)", SheetMath.MatchMedia(PdfSizes, "A3 portrait"));
    }

    [Fact]
    public void An_exact_name_is_used_as_given_with_or_without_underscores()
    {
        Assert.Equal("ISO_A3_(420.00_x_297.00_MM)", SheetMath.MatchMedia(PdfSizes, "ISO A3 (420.00 x 297.00 MM)"));
        Assert.Equal("ISO_expand_A3_(420.00_x_297.00_MM)", SheetMath.MatchMedia(PdfSizes, "ISO_expand_A3_(420.00_x_297.00_MM)"));
    }

    [Fact]
    public void A_size_the_plotter_does_not_have_is_null()
    {
        Assert.Null(SheetMath.MatchMedia(PdfSizes, "A0"));
        Assert.Null(SheetMath.MatchMedia(PdfSizes, "portrait"));
        Assert.Null(SheetMath.MatchMedia(PdfSizes, ""));
    }

    [Fact]
    public void An_imperial_sheet_matches_on_its_letter()
    {
        Assert.Equal("ANSI_full_bleed_D_(34.00_x_22.00_Inches)", SheetMath.MatchMedia(PdfSizes, "ANSI D"));
    }

    [Fact]
    public void The_sizes_on_offer_are_listed_once_each()
    {
        Assert.Equal(new[] { "ISO A3", "ISO A1", "ANSI D" }, SheetMath.MediaSizes(PdfSizes));
    }

    [Fact]
    public void Without_a_twist_the_view_centre_is_the_world_point()
    {
        SheetMath.ViewCentre(12500, 8000, 0, out var x, out var y);
        Assert.Equal(12500, x, 9);
        Assert.Equal(8000, y, 9);
    }

    [Fact]
    public void A_twisted_view_turns_the_point_with_it()
    {
        // A quarter turn: the world's +X shows as the display's +Y.
        SheetMath.ViewCentre(100, 0, 90, out var x, out var y);
        Assert.Equal(0, x, 9);
        Assert.Equal(100, y, 9);
        SheetMath.ViewCentre(0, 100, 90, out x, out y);
        Assert.Equal(-100, x, 9);
        Assert.Equal(0, y, 9);
    }

    [Fact]
    public void Turning_back_by_the_twist_gives_the_world_point_again()
    {
        SheetMath.ViewCentre(4321.5, -987.25, 23, out var x, out var y);
        SheetMath.ViewCentre(x, y, -23, out var wx, out var wy);
        Assert.Equal(4321.5, wx, 6);
        Assert.Equal(-987.25, wy, 6);
        Assert.Equal(System.Math.Sqrt(4321.5 * 4321.5 + 987.25 * 987.25), System.Math.Sqrt(x * x + y * y), 6);
    }

    [Theory]
    [InlineData(0.02, "1:50")]
    [InlineData(0.01, "1:100")]
    [InlineData(1.0, "1:1")]
    [InlineData(2.0, "2:1")]
    [InlineData(0.4, "1:2.5")]
    [InlineData(1.0 / 1250, "1:1250")]
    public void A_scale_is_named_as_it_goes_on_the_sheet(double ratio, string name)
    {
        Assert.Equal(name, SheetMath.ScaleName(ratio));
    }

    [Fact]
    public void An_annotation_scale_is_one_paper_to_so_many_drawing_units()
    {
        SheetMath.ScaleUnits(0.02, out var paper, out var drawing);
        Assert.Equal(1.0, paper, 9);
        Assert.Equal(50.0, drawing, 9);
        SheetMath.ScaleUnits(5.0, out paper, out drawing);
        Assert.Equal(5.0, paper, 9);
        Assert.Equal(1.0, drawing, 9);
        Assert.True(SheetMath.SameScale(1, 50, 0.02));
        Assert.True(SheetMath.SameScale(2, 100, 0.02));
        Assert.False(SheetMath.SameScale(1, 100, 0.02));
    }

    [Fact]
    public void A_scale_of_nothing_is_refused()
    {
        Assert.Throws<System.ArgumentOutOfRangeException>(() => SheetMath.ScaleName(0));
        Assert.Throws<System.ArgumentOutOfRangeException>(() => SheetMath.ScaleName(-1));
    }

    [Fact]
    public void A_millimetre_sheet_plotted_upright_is_as_AutoCAD_keeps_it()
    {
        SheetMath.PaperInUnits(420, 297, 5, 7.5, 6, 8, 1.0, false, out var sheet, out var margins);
        Assert.Equal(new[] { 420.0, 297.0 }, sheet);
        Assert.Equal(new[] { 5.0, 7.5, 6.0, 8.0 }, margins);
    }

    [Fact]
    public void An_inch_sheet_comes_back_in_inches()
    {
        // ANSI D is kept as 863.6 x 558.8 mm; an inch layout's paper space is 34 x 22.
        SheetMath.PaperInUnits(863.6, 558.8, 6.35, 6.35, 6.35, 6.35, 25.4, false, out var sheet, out var margins);
        Assert.Equal(34.0, sheet[0], 9);
        Assert.Equal(22.0, sheet[1], 9);
        Assert.Equal(0.25, margins[0], 9);
    }

    [Fact]
    public void A_sheet_plotted_at_90_degrees_has_its_sides_swapped()
    {
        SheetMath.PaperInUnits(297, 420, 5, 7.5, 6, 8, 1.0, true, out var sheet, out var margins);
        Assert.Equal(new[] { 420.0, 297.0 }, sheet);
        Assert.Equal(new[] { 7.5, 5.0, 8.0, 6.0 }, margins);
    }

    [Fact]
    public void A_closed_outline_drops_its_repeated_last_corner()
    {
        var points = SheetMath.Outline(new double[] { 0, 0, 100, 0, 100, 50, 0, 50, 0, 0 }, out var refusal);
        Assert.Null(refusal);
        Assert.NotNull(points);
        Assert.Equal(4, points!.Count);
        Assert.Equal(5000, System.Math.Abs(SheetMath.Area(points)), 9);
        Assert.Equal((0.0, 0.0, 100.0, 50.0), SheetMath.Bounds(points));
    }

    [Fact]
    public void An_L_shaped_outline_keeps_every_corner()
    {
        var points = SheetMath.Outline(new double[] { 0, 0, 200, 0, 200, 80, 80, 80, 80, 150, 0, 150 }, out var refusal);
        Assert.Null(refusal);
        Assert.Equal(6, points!.Count);
        Assert.Equal(200 * 80 + 80 * 70, SheetMath.Area(points), 9);
    }

    [Theory]
    [InlineData(new double[] { 0, 0, 10, 0 })]
    [InlineData(new double[] { 0, 0, 10, 0, 10 })]
    [InlineData(new double[] { 0, 0, 10, 10, 20, 20 })]
    [InlineData(new double[] { 5, 5, 5, 5, 5, 5, 5, 5 })]
    public void Something_that_is_not_a_shape_is_refused(double[] flat)
    {
        Assert.Null(SheetMath.Outline(flat, out var refusal));
        Assert.False(string.IsNullOrEmpty(refusal));
    }
}

/// <summary>A PDF made from several drawings (#67, D-91).</summary>
public class PublishAcrossDrawingsTests
{
    private static PublishPlan.Sheet[] Sheets(params string[] names)
    {
        var list = new List<PublishPlan.Sheet> { new PublishPlan.Sheet("Model", 0, true) };
        for (var i = 0; i < names.Length; i++) list.Add(new PublishPlan.Sheet(names[i], i + 1, false));
        return list.ToArray();
    }

    private static readonly string Ground = @"D:\Job\M-100 ground.dwg";
    private static readonly string First = @"D:\Job\M-200 first.dwg";

    [Fact]
    public void Every_sheet_of_every_drawing_in_order()
    {
        var entries = PublishPlan.ChooseAcross(new[]
        {
            new PublishPlan.Drawing(Ground, Sheets("M-101", "M-102")),
            new PublishPlan.Drawing(First, Sheets("M-201")),
        }, Array.Empty<string>(), false, out var refusal);
        Assert.Null(refusal);
        Assert.Equal(new[] { "M-101", "M-102", "M-201" }, entries.Select(e => e.Layout));
        Assert.Equal(new[] { Ground, Ground, First }, entries.Select(e => e.Path));
    }

    [Fact]
    public void Tab_order_wins_over_the_order_AutoCAD_lists_them()
    {
        var sheets = new[] { new PublishPlan.Sheet("M-102", 2, false), new PublishPlan.Sheet("Model", 0, true), new PublishPlan.Sheet("M-101", 1, false) };
        var entries = PublishPlan.ChooseAcross(new[] { new PublishPlan.Drawing(Ground, sheets) }, Array.Empty<string>(), true, out _);
        Assert.Equal(new[] { "Model", "M-101", "M-102" }, entries.Select(e => e.Layout));
    }

    [Fact]
    public void A_drawing_named_twice_is_published_once()
    {
        var entries = PublishPlan.ChooseAcross(new[]
        {
            new PublishPlan.Drawing(Ground, Sheets("M-101")),
            new PublishPlan.Drawing(Ground.ToUpperInvariant(), Sheets("M-101")),
        }, Array.Empty<string>(), false, out _);
        Assert.Single(entries);
    }

    [Fact]
    public void Named_layouts_are_taken_from_every_drawing_that_has_them()
    {
        var entries = PublishPlan.ChooseAcross(new[]
        {
            new PublishPlan.Drawing(Ground, Sheets("M-101", "COVER")),
            new PublishPlan.Drawing(First, Sheets("M-201", "cover")),
        }, new[] { "Cover" }, false, out var refusal);
        Assert.Null(refusal);
        Assert.Equal(new[] { "COVER", "cover" }, entries.Select(e => e.Layout));
    }

    [Fact]
    public void A_name_in_no_drawing_is_refused()
    {
        PublishPlan.ChooseAcross(new[] { new PublishPlan.Drawing(Ground, Sheets("M-101")) }, new[] { "M-999" }, false, out var refusal);
        Assert.Contains("'M-999'", refusal);
    }

    [Fact]
    public void An_unsaved_drawing_is_refused_by_name()
    {
        PublishPlan.ChooseAcross(new[]
        {
            new PublishPlan.Drawing(Ground, Sheets("M-101"), unsaved: true),
            new PublishPlan.Drawing(First, Sheets("M-201")),
        }, Array.Empty<string>(), false, out var refusal);
        Assert.Contains(Ground, refusal);
        Assert.Contains("unsaved", refusal);
        Assert.DoesNotContain(First, refusal);
    }

    [Fact]
    public void A_missing_xref_is_refused_with_its_name()
    {
        PublishPlan.ChooseAcross(new[]
        {
            new PublishPlan.Drawing(First, Sheets("M-201"), missingXrefs: new[] { "ARCH-BASE" }),
        }, Array.Empty<string>(), false, out var refusal);
        Assert.Contains("'ARCH-BASE'", refusal);
        Assert.Contains("autocad_manage_xref", refusal);
    }

    [Fact]
    public void Every_problem_is_said_at_once()
    {
        var entries = PublishPlan.ChooseAcross(new[]
        {
            new PublishPlan.Drawing(Ground, Sheets("M-101"), unsaved: true),
            new PublishPlan.Drawing(First, Sheets("M-201"), missingXrefs: new[] { "ARCH-BASE" }),
            new PublishPlan.Drawing(@"D:\Job\broken.dwg", Sheets(), unreadable: "eBadDwgHeader"),
        }, Array.Empty<string>(), false, out var refusal);
        Assert.Empty(entries);
        Assert.Contains("unsaved", refusal);
        Assert.Contains("ARCH-BASE", refusal);
        Assert.Contains("eBadDwgHeader", refusal);
    }

    private static readonly string Job = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "heron-job");

    [Fact]
    public void An_xref_at_its_full_saved_path_is_found()
    {
        var saved = System.IO.Path.Combine(Job, "xref", "ARCH.dwg");
        Assert.True(PublishPlan.XrefFound(saved, Job, f => f == saved));
    }

    [Fact]
    public void A_relative_xref_is_found_from_the_host_drawings_folder()
    {
        var saved = System.IO.Path.Combine("..", "base", "ARCH.dwg");
        var expected = System.IO.Path.GetFullPath(System.IO.Path.Combine(Job, saved));
        Assert.True(PublishPlan.XrefFound(saved, Job, f => f == expected));
    }

    [Fact]
    public void An_xref_moved_beside_the_host_is_found_by_its_name()
    {
        var beside = System.IO.Path.Combine(Job, "ARCH.dwg");
        Assert.True(PublishPlan.XrefFound(System.IO.Path.Combine(Job, "old", "ARCH.dwg"), Job, f => f == beside));
    }

    [Fact]
    public void An_xref_nowhere_or_with_no_path_is_not_found()
    {
        Assert.False(PublishPlan.XrefFound(System.IO.Path.Combine(Job, "ARCH.dwg"), Job, _ => false));
        Assert.False(PublishPlan.XrefFound("", Job, _ => true));
        Assert.False(PublishPlan.XrefFound(null, Job, _ => true));
    }

    [Fact]
    public void The_found_xref_file_is_given_back_so_its_own_xrefs_can_be_read()
    {
        var beside = System.IO.Path.Combine(Job, "ARCH.dwg");
        Assert.Equal(beside, PublishPlan.XrefPath(System.IO.Path.Combine(Job, "old", "ARCH.dwg"), Job, f => f == beside));
        Assert.Null(PublishPlan.XrefPath("ARCH.dwg", Job, _ => false));
    }

    [Fact]
    public void Page_titles_never_repeat()
    {
        var a = System.IO.Path.Combine(Job, "L1", "M-101.dwg");
        var b = System.IO.Path.Combine(Job, "L2", "M-101.dwg");
        var titles = PublishPlan.Titles(new[]
        {
            new PublishPlan.Entry(a, "SHEET"), new PublishPlan.Entry(b, "SHEET"), new PublishPlan.Entry(b, "OTHER"), new PublishPlan.Entry(a, "sheet"),
        });
        Assert.Equal(new[] { "M-101-SHEET", "M-101-SHEET (2)", "M-101-OTHER", "M-101-sheet (3)" }, titles);
    }

    [Fact]
    public void No_drawings_or_only_model_space_is_refused()
    {
        PublishPlan.ChooseAcross(Array.Empty<PublishPlan.Drawing>(), Array.Empty<string>(), false, out var none);
        Assert.Contains("No drawings", none);
        PublishPlan.ChooseAcross(new[] { new PublishPlan.Drawing(Ground, Sheets()) }, Array.Empty<string>(), false, out var model);
        Assert.Contains("include_model", model);
    }
}
