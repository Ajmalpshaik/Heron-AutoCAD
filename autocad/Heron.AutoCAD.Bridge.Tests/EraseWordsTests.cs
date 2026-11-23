using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>The erase question's words (D-50), and the whole-change question for replace jobs (D-136).</summary>
public class EraseWordsTests
{
    private const string Setting = "Ask before keeping erased objects";

    [Fact]
    public void The_usual_question_is_word_for_word_as_before()
    {
        // Every tool but the four replace tools keeps exactly this box (D-136).
        var words = EraseWords.For(2, whole: false, Setting);
        Assert.Equal("Heron erased 2 objects.", words.Headline);
        Assert.Equal("Bring them back", words.DefaultChoice);
        Assert.Equal("Every object this job erased comes back as it was. The rest of the job stays.", words.DefaultNote);
        Assert.Equal("Keep them erased", words.KeepChoice);
        Assert.Equal("They stay erased, with the rest of the job.", words.KeepNote);
        Assert.Equal("Nothing is erased for good until you say so.", words.Note);
        Assert.Equal("Esc or closing this window brings them back. To stop this question, turn off \"" + Setting + "\" in Settings.", words.Footer);
        Assert.Equal("Heron erased 1 object.", EraseWords.For(1, false, Setting).Headline);
    }

    [Fact]
    public void The_whole_change_question_asks_keep_the_change_or_undo_the_whole_change()
    {
        var words = EraseWords.For(1, whole: true, Setting);
        Assert.Equal("Keep the change, or undo the whole change?", words.Headline);
        Assert.Equal("Undo the whole change", words.DefaultChoice);
        Assert.Contains("exactly as it was before this job", words.DefaultNote);
        Assert.Contains("Nothing is left doubled", words.DefaultNote);
        Assert.Equal("Keep the change", words.KeepChoice);
        Assert.StartsWith("Heron erased 1 object to make the new shape.", words.Note);
        Assert.StartsWith("Esc or closing this window undoes the whole change.", words.Footer);
        Assert.Contains(Setting, words.Footer);
        Assert.StartsWith("Heron erased 3 objects to make", EraseWords.For(3, true, Setting).Note);
    }

    [Fact]
    public void The_whole_change_question_never_promises_to_bring_only_the_erased_back()
    {
        var words = EraseWords.For(4, whole: true, Setting);
        foreach (var text in new[] { words.Headline, words.DefaultChoice, words.DefaultNote, words.Footer })
            Assert.DoesNotContain("brings them back", text);
    }
}
