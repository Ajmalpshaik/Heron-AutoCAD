using System;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The drawing's geographic location (D-111): which way north is, and the two
/// checks that refuse a location AutoCAD would read back wrong.
/// </summary>
public class GeoPlaceTests
{
    [Theory]
    [InlineData(0, 0, 1)]
    [InlineData(90, 1, 0)]
    [InlineData(180, 0, -1)]
    [InlineData(270, -1, 0)]
    public void North_is_measured_clockwise_from_up_the_screen(double degrees, double x, double y)
    {
        var v = GeoPlace.NorthVector(degrees * Math.PI / 180);
        Assert.Equal(x, v[0], 12);
        Assert.Equal(y, v[1], 12);
        Assert.Equal(degrees * Math.PI / 180, GeoPlace.NorthAngle(v[0], v[1]), 9);
    }

    [Fact]
    public void North_fifteen_degrees_right_of_up_points_up_and_right()
    {
        var v = GeoPlace.NorthVector(15 * Math.PI / 180);
        Assert.True(v[0] > 0 && v[1] > 0);
        Assert.Equal(15 * Math.PI / 180, GeoPlace.NorthAngle(v[0], v[1]), 12);
    }

    [Theory]
    [InlineData(25.29, 51.53, null)]
    [InlineData(-33.87, 151.21, null)]
    [InlineData(91, 0, "latitude")]
    [InlineData(0, 181, "longitude")]
    [InlineData(86, 0, "85 degrees")]
    [InlineData(double.NaN, 0, "latitude")]
    public void The_place_must_be_on_the_map(double latitude, double longitude, string? words)
    {
        var why = GeoPlace.Ranges(latitude, longitude);
        if (words == null) Assert.Null(why);
        else Assert.Contains(words, why);
    }

    [Fact]
    public void The_same_place_read_back_passes_and_a_metre_off_does_not()
    {
        Assert.Null(GeoPlace.SamePlace(25.29, 51.53, 25.2900000004, 51.5299999996));
        var why = GeoPlace.SamePlace(25.29, 51.53, 25.29001, 51.53);
        Assert.Contains("25.29001", why);
    }

    [Fact]
    public void Latitude_and_longitude_swapped_are_caught()
    {
        Assert.NotNull(GeoPlace.SamePlace(25.29, 51.53, 51.53, 25.29));
    }

    [Fact]
    public void The_date_line_is_one_place()
    {
        Assert.Null(GeoPlace.SamePlace(-17.7, 180, -17.7, -180));
    }

    [Fact]
    public void A_hundred_metres_north_reads_as_a_hundred_metres_north()
    {
        var lat = 25.29;
        Assert.Null(GeoPlace.NorthCheck(lat, 51.53, lat + 100 / GeoPlace.MetresPerDegree, 51.53));
    }

    [Fact]
    public void North_the_wrong_way_is_caught()
    {
        var lat = 25.29;
        var why = GeoPlace.NorthCheck(lat, 51.53, lat - 100 / GeoPlace.MetresPerDegree, 51.53);
        Assert.Contains("-100", why);
    }

    [Fact]
    public void North_turned_a_right_angle_is_caught()
    {
        var lat = 25.29;
        var east = 100 / (GeoPlace.MetresPerDegree * Math.Cos(lat * Math.PI / 180));
        Assert.NotNull(GeoPlace.NorthCheck(lat, 51.53, lat, 51.53 + east));
    }

    [Theory]
    [InlineData(0.1)] // millimetres read as metres-ish: a tenth of the distance
    [InlineData(1000)] // metres read as millimetres
    [InlineData(1.2)] // a Mercator grid used one-to-one at 34 degrees
    public void The_drawing_units_read_wrong_are_caught(double factor)
    {
        var lat = 25.29;
        Assert.NotNull(GeoPlace.NorthCheck(lat, 51.53, lat + factor * 100 / GeoPlace.MetresPerDegree, 51.53));
    }
}
