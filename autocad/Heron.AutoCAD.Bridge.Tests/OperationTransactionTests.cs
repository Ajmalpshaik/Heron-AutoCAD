using System;
using System.Collections.Generic;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// How a plug-in operation's transaction ends (D-140, issue #80), and a new
/// object AutoCAD posts itself kept inside the transaction (issue #258).
/// </summary>
public class OperationTransactionTests
{
    [Fact]
    public void A_read_is_always_aborted_even_when_it_touched_something()
    {
        var t = new OperationTransaction(Risk.Read);
        Assert.False(t.Commit(workAfter: false));
        t.Object();
        t.Variable();
        Assert.False(t.Commit(workAfter: true));
    }

    [Theory]
    [InlineData(Risk.View)]
    [InlineData(Risk.Change)]
    [InlineData(Risk.Publish)]
    [InlineData(Risk.Admin)]
    public void A_job_that_touched_nothing_is_aborted_so_it_leaves_no_undo_step(Risk level)
    {
        var t = new OperationTransaction(level);
        Assert.True(t.Untouched);
        Assert.False(t.Commit(workAfter: false));
    }

    [Fact]
    public void One_object_opened_for_change_is_enough_to_commit()
    {
        var t = new OperationTransaction(Risk.Change);
        t.Object();
        Assert.False(t.Untouched);
        Assert.True(t.Commit(workAfter: false));
    }

    [Fact]
    public void A_variable_changed_alone_is_committed_the_count_cannot_see_it()
    {
        // A style made current, DIMBLK: no object event, but a change all the same.
        var t = new OperationTransaction(Risk.Change);
        t.Variable();
        Assert.True(t.Commit(workAfter: false));
    }

    [Fact]
    public void Work_left_for_after_the_transaction_keeps_the_commit()
    {
        // A sheet to put on screen or a regen runs only after a commit: never drop it.
        var t = new OperationTransaction(Risk.Change);
        Assert.True(t.Commit(workAfter: true));
    }

    [Fact]
    public void A_posted_object_the_transaction_takes_is_left_alone()
    {
        var steps = new List<string>();
        PostedObject.Post("the geographic location",
            () => steps.Add("post"), () => steps.Add("adopt"), () => steps.Add("takeBack"), (_, _) => steps.Add("log"));
        Assert.Equal(new[] { "post", "adopt" }, steps);
    }

    [Fact]
    public void A_post_that_fails_added_nothing_and_its_error_goes_up_as_it_is()
    {
        var steps = new List<string>();
        var ex = Assert.Throws<InvalidOperationException>(() => PostedObject.Post("the geographic location",
            () => throw new InvalidOperationException("eNoDatabase"),
            () => steps.Add("adopt"), () => steps.Add("takeBack"), (_, _) => steps.Add("log")));
        Assert.Equal("eNoDatabase", ex.Message);
        Assert.Empty(steps);
    }

    [Fact]
    public void An_object_the_transaction_will_not_take_is_taken_off_again_and_refused()
    {
        var steps = new List<string>();
        var refusal = Assert.Throws<RunRefusal>(() => PostedObject.Post("the geographic location",
            () => steps.Add("post"), () => throw new InvalidOperationException("eWasOpenForWrite"),
            () => steps.Add("takeBack"), (what, _) => steps.Add("log: " + what)));
        Assert.Equal(new[] { "post", "log: Handing the geographic location to the transaction", "takeBack" }, steps);
        Assert.Contains("took it off again", refusal.Message);
        // A refusal is answered "Nothing was changed": true, it is gone again.
        Assert.DoesNotContain("may still be", refusal.Message);
    }

    [Fact]
    public void One_that_cannot_be_taken_off_either_never_says_nothing_was_changed()
    {
        var logged = new List<string>();
        var left = Assert.Throws<RunLeftBehind>(() => PostedObject.Post("the geographic location",
            () => { }, () => throw new InvalidOperationException("eWasOpenForWrite"),
            () => throw new InvalidOperationException("eNotOpenForWrite"), (what, _) => logged.Add(what)));
        Assert.Equal(2, logged.Count);
        Assert.Contains("may still be in the drawing", left.Message);
        Assert.DoesNotContain(Texts.NothingChanged, left.Message);
    }
}
