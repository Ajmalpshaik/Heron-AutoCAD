using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The rules behind the plug-in's multileader and table styles (D-104): the
/// words, the defaults (Ajmal's TLD label, text in the vertical middle of a
/// cell) and every refusal, all before AutoCAD is touched.
/// </summary>
public class StylePlansTests
{
    private static MultileaderStylePlan Leader(string json)
    {
        using (var args = RunArgs.Parse(json)) return MultileaderStylePlan.From(args);
    }

    private static TableStylePlan Table(string json)
    {
        using (var args = RunArgs.Parse(json)) return TableStylePlan.From(args);
    }

    private static string Refusal(System.Action make) => Assert.Throws<RunRefusal>(make).Message;

    [Fact]
    public void Both_operations_are_changes()
    {
        foreach (var name in new[] { "multileader_style", "table_style" })
        {
            Assert.True(PluginOperations.TryLevel(name, out var level), name);
            Assert.Equal(Risk.Change, level);
        }
        Assert.False(PluginOperations.TryLevel("plot_style_table", out _));
    }

    [Fact]
    public void A_multileader_style_is_the_TLD_label_unless_asked_otherwise()
    {
        var plan = Leader("{\"name\": \" MEP-LABEL \", \"text_height\": 2.5}");
        Assert.Equal("MEP-LABEL", plan.Name);
        Assert.Equal(2.5, plan.TextHeight);
        // The leader ends under the text, as autocad_add_label draws it: arrow and landing as big as the text.
        Assert.Equal(5, plan.Attachment);
        Assert.Equal("underline_bottom_line", StylePlans.AttachmentWord(plan.Attachment));
        Assert.Equal("", plan.ArrowBlock);
        Assert.Equal(2.5, plan.ArrowSize);
        Assert.True(plan.Dogleg);
        Assert.Equal(2.5, plan.DoglegLength);
        Assert.Null(plan.LandingGap);
        Assert.Equal(1.0, plan.Scale);
        Assert.Equal("", plan.TextStyle);
        Assert.False(plan.Current);
        Assert.False(plan.Replace);
    }

    [Fact]
    public void Every_option_of_a_multileader_style_is_read()
    {
        var plan = Leader("{\"name\": \"TAG-50\", \"text_style\": \"ROMANS\", \"text_height\": 2.5, \"arrow\": \"Dot\", "
            + "\"arrow_size\": 1.5, \"dogleg\": false, \"dogleg_length\": 4, \"landing_gap\": 0, \"attachment\": \"Middle of top line\", "
            + "\"scale\": \"1:50\", \"current\": true, \"replace\": true}");
        Assert.Equal("ROMANS", plan.TextStyle);
        Assert.Equal("_DOT", plan.ArrowBlock);
        Assert.Equal(1.5, plan.ArrowSize);
        Assert.False(plan.Dogleg);
        Assert.Equal(4.0, plan.DoglegLength);
        Assert.Equal(0.0, plan.LandingGap);
        Assert.Equal(1, plan.Attachment);
        Assert.Equal(50.0, plan.Scale);
        Assert.True(plan.Current);
        Assert.True(plan.Replace);
    }

    [Fact]
    public void A_multileader_style_needs_its_text_height_and_sizes_above_zero()
    {
        Assert.Contains("'text_height'", Refusal(() => Leader("{\"name\": \"A\"}")));
        Assert.Contains("above zero", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 0}")));
        Assert.Contains("above zero", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 2.5, \"arrow_size\": -1}")));
        Assert.Contains("must be a number", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": \"2.5\"}")));
        Assert.Contains("below zero", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 2.5, \"landing_gap\": -0.5}")));
    }

    [Theory]
    [InlineData("closed filled", "")]
    [InlineData("", "")]
    [InlineData("dot", "_DOT")]
    [InlineData("_DOT", "_DOT")]
    [InlineData("Architectural tick", "_ARCHTICK")]
    [InlineData("_archtick", "_ARCHTICK")]
    [InlineData("right-angle", "_OPEN90")]
    [InlineData("_OPEN90", "_OPEN90")]
    [InlineData("dot small blank", "_SMALL")]
    [InlineData("none", "_NONE")]
    public void Arrows_are_AutoCADs_own_by_word_or_block_name(string asked, string block)
    {
        Assert.Equal(block, StylePlans.ArrowBlock(asked));
    }

    [Fact]
    public void An_arrow_AutoCAD_has_not_got_is_refused_with_the_list()
    {
        var message = Refusal(() => StylePlans.ArrowBlock("half arrow"));
        Assert.Contains("closed_filled", message);
        Assert.Contains("architectural_tick", message);
        Assert.Equal("dot", StylePlans.ArrowWord("_DOT"));
        Assert.Equal("closed_filled", StylePlans.ArrowWord(""));
    }

    [Fact]
    public void Attachments_follow_the_dialogs_list()
    {
        Assert.Equal(0, StylePlans.Attachment("top of top line"));
        Assert.Equal(2, StylePlans.Attachment("middle"));
        Assert.Equal(4, StylePlans.Attachment("bottom_of_bottom_line"));
        Assert.Equal(5, StylePlans.Attachment("Underline bottom line"));
        Assert.Equal(8, StylePlans.Attachment("underline all"));
        Assert.Equal(5, StylePlans.Attachment(""));
        Assert.Contains("TLD", Refusal(() => StylePlans.Attachment("above")));
    }

    [Theory]
    [InlineData("50", 50.0)]
    [InlineData("1", 1.0)]
    [InlineData("\"1:50\"", 50.0)]
    [InlineData("\"1 : 100\"", 100.0)]
    [InlineData("\"scale 1:20\"", 20.0)]
    [InlineData("\"2:1\"", 0.5)]
    [InlineData("\"25\"", 25.0)]
    [InlineData("null", 1.0)]
    public void A_scale_is_a_factor_or_written_as_on_the_sheet(string written, double factor)
    {
        using (var args = RunArgs.Parse("{\"scale\": " + written + "}"))
            Assert.Equal(factor, StylePlans.ScaleFactor(args.Element("scale")), 12);
        using (var none = RunArgs.Parse("{}"))
            Assert.Equal(1.0, StylePlans.ScaleFactor(none.Element("scale")));
    }

    [Fact]
    public void A_bare_number_below_one_is_refused_not_guessed()
    {
        // D-104, after D-36: 0.02 is the 1:50 ratio or a factor fifty times too small.
        var message = Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 2.5, \"scale\": 0.02}"));
        Assert.Contains("'1:50'", message);
        Assert.Contains("'50:1'", message);
        Assert.Contains("above zero", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 2.5, \"scale\": 0}")));
        Assert.Contains("above zero", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 2.5, \"scale\": \"1:0\"}")));
        Assert.Contains("not a scale", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 2.5, \"scale\": \"half\"}")));
        Assert.Contains("'scale'", Refusal(() => Leader("{\"name\": \"A\", \"text_height\": 2.5, \"scale\": [50]}")));
    }

    [Fact]
    public void A_style_name_AutoCAD_would_not_take_is_refused()
    {
        Assert.Contains("needs a 'name'", Refusal(() => Leader("{\"text_height\": 2.5}")));
        Assert.Contains("needs a 'name'", Refusal(() => Table("{\"name\": \"  \", \"text_height\": 2.5}")));
        var message = Refusal(() => Leader("{\"name\": \"MEP/50\", \"text_height\": 2.5}"));
        Assert.Contains("contains /", message);
        Assert.Contains("255", Refusal(() => StylePlans.CheckName(new string('A', 256), "table style")));
        Assert.Equal("MEP 50", StylePlans.CheckName(" MEP 50 ", "table style"));
    }

    [Fact]
    public void A_table_style_is_sized_for_the_sheet_and_centred_in_the_middle_of_each_cell()
    {
        var plan = Table("{\"name\": \"SCHEDULE-50\", \"text_height\": 2.5, \"scale\": \"1:50\"}");
        Assert.Equal("SCHEDULE-50", plan.Name);
        Assert.Equal(50.0, plan.Scale);
        // 2.5 mm at 1:50 is 125 in the drawing (rule 7); a table style has no scale of its own.
        Assert.Equal(125.0, plan.DataHeight, 9);
        Assert.Equal(125.0, plan.HeaderHeight, 9);
        Assert.Equal(125.0, plan.TitleHeight, 9);
        // A third of the text height, as AutoCAD's own Standard style has it.
        Assert.Equal(125.0 / 3, plan.HorizontalMargin, 9);
        Assert.Equal(125.0 / 3, plan.VerticalMargin, 9);
        Assert.Equal(5, plan.DataAlignment);
        Assert.Equal(5, plan.HeaderAlignment);
        Assert.Equal(5, plan.TitleAlignment);
        Assert.True(plan.TitleRow);
        Assert.True(plan.HeaderRow);
        Assert.Equal("middle_centre", StylePlans.AlignmentWord(plan.DataAlignment));
    }

    [Fact]
    public void Every_option_of_a_table_style_is_read()
    {
        var plan = Table("{\"name\": \"PUMPS\", \"text_style\": \"ROMANS\", \"text_height\": 2.5, \"header_text_height\": 3, "
            + "\"title_text_height\": 3.5, \"margin\": 1, \"vertical_margin\": 0.5, \"alignment\": \"left\", \"header_alignment\": \"Center\", "
            + "\"title_alignment\": \"right\", \"title_row\": false, \"header_row\": false, \"scale\": 10, \"current\": true}");
        Assert.Equal("ROMANS", plan.TextStyle);
        Assert.Equal(25.0, plan.DataHeight, 9);
        Assert.Equal(30.0, plan.HeaderHeight, 9);
        Assert.Equal(35.0, plan.TitleHeight, 9);
        Assert.Equal(10.0, plan.HorizontalMargin, 9);
        Assert.Equal(5.0, plan.VerticalMargin, 9);
        Assert.Equal(4, plan.DataAlignment);
        Assert.Equal(5, plan.HeaderAlignment);
        Assert.Equal(6, plan.TitleAlignment);
        Assert.Equal("middle_left", StylePlans.AlignmentWord(plan.DataAlignment));
        Assert.Equal("middle_right", StylePlans.AlignmentWord(plan.TitleAlignment));
        Assert.False(plan.TitleRow);
        Assert.False(plan.HeaderRow);
        Assert.True(plan.Current);
    }

    [Fact]
    public void A_table_alignment_off_the_middle_is_refused()
    {
        // Ajmal's rule (D-83): text sits in the vertical middle of every cell.
        var message = Refusal(() => Table("{\"name\": \"A\", \"text_height\": 2.5, \"alignment\": \"top left\"}"));
        Assert.Contains("vertical middle", message);
        Assert.Contains("'alignment'", message);
        Assert.Contains("'header_alignment'", Refusal(() => Table("{\"name\": \"A\", \"text_height\": 2.5, \"header_alignment\": \"bottom\"}")));
    }

    [Fact]
    public void A_table_style_needs_its_text_height_and_may_have_no_margin()
    {
        Assert.Contains("'text_height'", Refusal(() => Table("{\"name\": \"A\"}")));
        Assert.Contains("below zero", Refusal(() => Table("{\"name\": \"A\", \"text_height\": 2.5, \"margin\": -1}")));
        var tight = Table("{\"name\": \"A\", \"text_height\": 2.5, \"margin\": 0}");
        Assert.Equal(0.0, tight.HorizontalMargin);
        Assert.Equal(0.0, tight.VerticalMargin);
    }

    [Fact]
    public void The_refusals_say_what_to_do()
    {
        Assert.Contains("replace=true", StylePlans.AlreadyThere("table style", "PUMPS"));
        Assert.Contains("text_styles", StylePlans.NoTextStyle("ROMANS"));
    }
}
