using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The map transform written for texture_size (seen live 2026-11-08: with the
/// identity a walnut photo repeated every 1 mm and rendered flat brown; the
/// diagonal set to 1/size by hand made the grain show).
/// </summary>
public class TextureScaleTests
{
    [Fact]
    public void A_square_tile_puts_one_over_the_size_on_the_diagonal()
    {
        Assert.Null(TextureScale.Matrix(1000, null, out var m));
        Assert.Equal(16, m.Length);
        Assert.Equal(0.001, m[0], 12);
        Assert.Equal(0.001, m[5], 12);
        Assert.Equal(0.001, m[10], 12);
        Assert.Equal(1.0, m[15]);
        for (var i = 0; i < 16; i++)
            if (i != 0 && i != 5 && i != 10 && i != 15) Assert.Equal(0.0, m[i]);
    }

    [Fact]
    public void Marble_at_two_metres()
    {
        Assert.Null(TextureScale.Matrix(2000, 2000, out var m));
        Assert.Equal(0.0005, m[0], 12);
        Assert.Equal(0.0005, m[5], 12);
        Assert.Equal(0.0005, m[10], 12);
    }

    [Fact]
    public void A_non_square_tile_takes_its_height_along_y_and_up_the_wall()
    {
        Assert.Null(TextureScale.Matrix(600, 300, out var m));
        Assert.Equal(1.0 / 600, m[0], 12);
        Assert.Equal(1.0 / 300, m[5], 12);
        Assert.Equal(1.0 / 300, m[10], 12);
        Assert.Equal(1.0, m[15]);
    }

    [Theory]
    [InlineData(0, null)]
    [InlineData(-1, null)]
    [InlineData(1000.0, 0.0)]
    [InlineData(double.NaN, null)]
    [InlineData(double.PositiveInfinity, null)]
    [InlineData(2_000_000, null)]
    [InlineData(1000.0, 2_000_000.0)]
    public void A_size_that_is_not_usable_is_refused(double width, double? height)
    {
        var why = TextureScale.Matrix(width, height, out var m);
        Assert.Contains("above zero", why);
        Assert.Empty(m);
    }
}
