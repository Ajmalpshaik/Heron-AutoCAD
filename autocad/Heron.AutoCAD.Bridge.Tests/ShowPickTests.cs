using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>Select and Zoom keep only what AutoCAD can select, and say what was left out (#234, D-132).</summary>
public class ShowPickTests
{
    private static ShowLook<int> L(string handle, ShowPlace place, int id = 0) => new(handle, place, id);

    [Theory]
    [InlineData("1A", 0x1A)]
    [InlineData("  2f ", 0x2F)]
    [InlineData("0x1A", 0x1A)]
    [InlineData("7FFFFFFFFFFFFFFF", long.MaxValue)]
    public void Handles_are_read_as_hexadecimal(string text, long expected)
    {
        Assert.True(ShowPick.TryParseHandle(text, out var value));
        Assert.Equal(expected, value);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    [InlineData("XYZ")]
    [InlineData("0")]
    [InlineData("FFFFFFFFFFFFFFFF")] // -1 as a long: no object
    [InlineData("1FFFFFFFFFFFFFFFF")] // too long
    public void Anything_else_is_not_a_handle_and_never_throws(string? text)
    {
        Assert.False(ShowPick.TryParseHandle(text, out var value));
        Assert.Equal(0, value);
    }

    [Fact]
    public void Only_objects_in_the_space_in_front_are_selected_and_the_rest_are_sorted_by_reason()
    {
        // The issue's job: a table style, a multileader style, a layer, lines, and one erased.
        var picked = ShowPick.Sort(new[]
        {
            L("A1", ShowPlace.InSpace, 1),
            L("A2", ShowPlace.NotDrawingObject),
            L("A3", ShowPlace.InSpace, 2),
            L("A4", ShowPlace.NotDrawingObject),
            L("A5", ShowPlace.OtherSpace),
            L("A6", ShowPlace.InsideBlock),
            L("A7", ShowPlace.Gone),
            L("A8", ShowPlace.NotDrawingObject),
        });
        Assert.Equal(new[] { 1, 2 }, picked.Ids);
        Assert.Equal(8, picked.Asked);
        Assert.Equal(new[] { "A2", "A4", "A8" }, picked.NotDrawingObject);
        Assert.Equal(new[] { "A5" }, picked.OtherSpace);
        Assert.Equal(new[] { "A6" }, picked.InsideBlock);
        Assert.Equal(new[] { "A7" }, picked.Gone);
        Assert.Equal(5, picked.NotSelectable);
        Assert.Equal(6, picked.LeftOut);
        Assert.False(picked.TooMany);
    }

    [Fact]
    public void Two_attributes_of_one_block_select_the_block_once()
    {
        var picked = ShowPick.Sort(new[] { L("B1", ShowPlace.InSpace, 7), L("B2", ShowPlace.InSpace, 7), L("B3", ShowPlace.InSpace, 8) });
        Assert.Equal(new[] { 7, 8 }, picked.Ids);
        Assert.Equal(0, picked.LeftOut);
    }

    [Fact]
    public void The_show_answer_gives_each_left_out_handle_its_reason()
    {
        var picked = ShowPick.Sort(new[]
        {
            L("C1", ShowPlace.OtherSpace), L("C2", ShowPlace.InsideBlock), L("C3", ShowPlace.NotDrawingObject), L("C4", ShowPlace.Gone),
        });
        Assert.Equal(
            new[] { ("C1", "other_space"), ("C2", "inside_block"), ("C3", "not_a_drawing_object") },
            picked.NotSelectableWithReason().Select(p => (p.Key, p.Value)));
    }

    [Fact]
    public void All_selectable_says_how_many_and_nothing_else()
    {
        var picked = ShowPick.Sort(new[] { L("1", ShowPlace.InSpace, 1), L("2", ShowPlace.InSpace, 2), L("3", ShowPlace.InSpace, 3) });
        Assert.Equal("Selected 3 objects.", ShowPick.Line(picked, zoom: false, selected: true, zoomed: false));
        Assert.Equal("Zoomed to 3 objects, selected.", ShowPick.Line(picked, zoom: true, selected: true, zoomed: true));
        Assert.Equal(3, ShowPick.SelectedCount(picked, selected: true));
    }

    [Fact]
    public void One_object_is_said_in_the_singular()
    {
        var picked = ShowPick.Sort(new[] { L("1", ShowPlace.InSpace, 1), L("2", ShowPlace.NotDrawingObject) });
        Assert.Equal(
            "Selected 1 object. 1 could not be selected: 1 is not a drawing object (a style, a layer or a definition).",
            ShowPick.Line(picked, zoom: false, selected: true, zoomed: false));
    }

    [Fact]
    public void Some_left_out_still_selects_the_rest_and_says_how_many_and_why()
    {
        var picked = ShowPick.Sort(new[]
        {
            L("1", ShowPlace.InSpace, 1), L("2", ShowPlace.InSpace, 2),
            L("3", ShowPlace.NotDrawingObject), L("4", ShowPlace.NotDrawingObject),
            L("5", ShowPlace.OtherSpace), L("6", ShowPlace.Gone),
        });
        Assert.Equal(
            "Zoomed to 2 objects, selected. 4 could not be selected: 1 is on another layout or the Model tab, " +
            "2 are not drawing objects (a style, a layer or a definition) and 1 is erased or gone.",
            ShowPick.Line(picked, zoom: true, selected: true, zoomed: true));
    }

    [Fact]
    public void None_selectable_says_so_with_the_reasons()
    {
        var picked = ShowPick.Sort(new[] { L("1", ShowPlace.NotDrawingObject), L("2", ShowPlace.NotDrawingObject), L("3", ShowPlace.InsideBlock) });
        Assert.Empty(picked.Ids);
        Assert.Equal(
            "Nothing of this job can be selected here: 1 is inside a block definition and 2 are not drawing objects (a style, a layer or a definition).",
            ShowPick.Line(picked, zoom: true, selected: false, zoomed: false));
        Assert.Equal(0, ShowPick.SelectedCount(picked, selected: false));
    }

    [Fact]
    public void None_selectable_because_they_are_on_another_tab_says_to_switch()
    {
        var picked = ShowPick.Sort(new[] { L("1", ShowPlace.OtherSpace), L("2", ShowPlace.OtherSpace) });
        Assert.Equal(
            "Nothing of this job can be selected here: 2 are on another layout or the Model tab. Switch to the tab they are on and press again.",
            ShowPick.Line(picked, zoom: false, selected: false, zoomed: false));
    }

    [Fact]
    public void All_gone_keeps_the_old_sentence()
    {
        var picked = ShowPick.Sort(new[] { L("1", ShowPlace.Gone), L("2", ShowPlace.Gone) });
        Assert.Equal(PaletteTexts.ShowAllGone, ShowPick.Line(picked, zoom: true, selected: false, zoomed: false));
        Assert.Equal(PaletteTexts.ShowAllGone, ShowPick.Line(ShowPick.Sort(new ShowLook<int>[0]), zoom: false, selected: false, zoomed: false));
    }

    [Fact]
    public void A_selection_AutoCAD_refuses_is_never_called_selected()
    {
        var picked = ShowPick.Sort(new[] { L("1", ShowPlace.InSpace, 1), L("2", ShowPlace.InSpace, 2) });
        Assert.Equal(
            "AutoCAD would not select the 2 objects of this job (the reason is in Heron's log); the view frames them.",
            ShowPick.Line(picked, zoom: true, selected: false, zoomed: true));
        Assert.Equal(
            "AutoCAD would not select the 2 objects of this job (the reason is in Heron's log).",
            ShowPick.Line(picked, zoom: false, selected: false, zoomed: false));
        // The Keep question then says to look, not that they are selected.
        Assert.Equal(0, ShowPick.SelectedCount(picked, selected: false));
    }

    [Fact]
    public void Zoom_with_nothing_to_frame_says_selected_only()
    {
        var picked = ShowPick.Sort(new[] { L("1", ShowPlace.InSpace, 1) });
        Assert.Equal("Selected 1 object, but it has no size Heron can zoom to.", ShowPick.Line(picked, zoom: true, selected: true, zoomed: false));
    }

    [Fact]
    public void Too_many_selects_nothing_and_says_how_to_show_them()
    {
        var picked = ShowPick.TooManyOf<int>(ShowPick.Most + 1);
        Assert.True(picked.TooMany);
        Assert.Empty(picked.Ids);
        Assert.Equal(0, ShowPick.SelectedCount(picked, selected: true));
        Assert.Equal(
            "This job made or changed 501 objects, and Heron selects at most 500 at once. Ask the chat to show them in parts, or by layer.",
            ShowPick.Line(picked, zoom: true, selected: false, zoomed: false));
    }

    [Fact]
    public void The_palette_never_shows_more_than_Heron_selects()
    {
        // ActivityLog keeps at most MostShown handles per job; the show limit is the same number.
        Assert.Equal(JobChanges.MostShown, ShowPick.Most);
    }
}
