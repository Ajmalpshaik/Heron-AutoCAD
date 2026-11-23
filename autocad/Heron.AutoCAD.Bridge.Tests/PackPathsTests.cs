using System;
using System.Collections.Generic;
using System.IO;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>eTransmit's packed copy points at the files beside it (#160): which path becomes what.</summary>
public class PackPathsTests
{
    private static readonly string[] Pack = { "Ground floor.dwg", "Site.JPG", "Survey.pdf" };
    private static readonly string[] None = Array.Empty<string>();

    [Theory]
    [InlineData(@"C:\Project\Xrefs\Ground floor.dwg", "Ground floor.dwg")]
    [InlineData(@"..\Xrefs\Ground floor.dwg", "Ground floor.dwg")]
    [InlineData("//server/share/site.jpg", "site.jpg")]
    [InlineData("\"Survey.pdf\"", "Survey.pdf")]
    [InlineData("Survey.pdf", "Survey.pdf")]
    [InlineData("", "")]
    [InlineData(null, "")]
    public void The_bare_name_is_what_follows_the_last_slash(string? saved, string bare) =>
        Assert.Equal(bare, PackPaths.BareName(saved));

    [Theory]
    [InlineData(@"C:\Project\Xrefs\Ground floor.dwg", "Ground floor.dwg")]
    [InlineData(@"..\images\site.jpg", "site.jpg")]
    [InlineData(@"\\server\scans\Survey.PDF", "Survey.PDF")]
    public void A_file_in_the_pack_gets_its_bare_name_in_its_own_letters(string saved, string now)
    {
        var choice = PackPaths.Decide(saved, Pack, None);
        Assert.Equal(now, choice.NewPath);
        Assert.False(choice.Already);
    }

    [Fact]
    public void A_file_not_in_the_pack_keeps_its_path_and_says_why()
    {
        var choice = PackPaths.Decide(@"C:\Gone\missing.png", Pack, None);
        Assert.Null(choice.NewPath);
        Assert.Contains("not in the pack", choice.Why);
    }

    [Fact]
    public void A_name_two_files_share_keeps_its_path()
    {
        var choice = PackPaths.Decide(@"D:\Other\Site.jpg", Pack, new[] { "site.jpg" });
        Assert.Null(choice.NewPath);
        Assert.Contains("two different files", choice.Why);
    }

    [Fact]
    public void A_bare_name_already_is_left_as_it_is()
    {
        var choice = PackPaths.Decide("Survey.pdf", Pack, None);
        Assert.Null(choice.NewPath);
        Assert.True(choice.Already);
    }

    [Fact]
    public void No_saved_path_is_kept()
    {
        Assert.Null(PackPaths.Decide("  ", Pack, None).NewPath);
    }

    [Fact]
    public void Only_a_dwg_copy_in_a_pack_folder_is_rewritten()
    {
        var root = Path.GetTempPath();
        var staged = Path.Combine(root, PackPaths.StagingPrefix + "a1b2", "Plan.dwg");
        Assert.Null(PackPaths.Refusal(staged, None));
        Assert.Contains("never another drawing", PackPaths.Refusal(Path.Combine(root, "Project", "Plan.dwg"), None));
        Assert.Contains(".dwg", PackPaths.Refusal(Path.Combine(root, PackPaths.StagingPrefix + "a1b2", "Plan.dxf"), None));
        Assert.Contains("whole path", PackPaths.Refusal("Plan.dwg", None));
        Assert.Contains("whole path", PackPaths.Refusal(null, None));
    }

    [Fact]
    public void A_drawing_open_in_AutoCAD_is_never_rewritten()
    {
        var staged = Path.Combine(Path.GetTempPath(), PackPaths.StagingPrefix + "a1b2", "Plan.dwg");
        var open = new List<string> { "Drawing1.dwg", staged.ToUpperInvariant() };
        Assert.Contains("open in AutoCAD", PackPaths.Refusal(staged, open));
    }
}
