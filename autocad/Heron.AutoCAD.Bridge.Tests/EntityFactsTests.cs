using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The length and text reads the plug-in does in one go (#195, #197, D-134):
/// what it writes for autocad_total_length, autocad_measure, autocad_count_text
/// and autocad_find_text. Raw facts at full precision, in the order selected;
/// the server keeps only what COM gives for each class and reads them with its
/// COM code. tests/test_plugin_length_text_reads.py holds the server side to this.
/// </summary>
public class EntityFactsTests
{
    private static string Written(System.Action<Utf8JsonWriter> body)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            body(writer);
            writer.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static string Number(double? value) => Written(w =>
    {
        w.WriteStartArray("v");
        FactNumber.Write(w, value);
        w.WriteEndArray();
    });

    [Fact]
    public void A_number_goes_at_full_precision_and_one_that_is_not_finite_is_named_so()
    {
        Assert.Equal("{\"v\":[3000]}", Number(3000.0)); // the server turns it back into 3000.0
        var read = JsonDocument.Parse(Number(1234.5678901234567)).RootElement.GetProperty("v")[0].GetDouble();
        Assert.Equal(1234.5678901234567, read);
        Assert.Equal("{\"v\":[null]}", Number(null));
        // Utf8JsonWriter refuses NaN; the server reads the drawing over COM on this text.
        Assert.Equal("{\"v\":[\"not finite\"]}", Number(double.NaN));
        Assert.Equal("{\"v\":[\"not finite\"]}", Number(double.PositiveInfinity));
    }

    [Fact]
    public void Each_curve_goes_as_class_layer_length_area_closed_and_shape()
    {
        var list = new CurveFactList();
        list.Add(new CurveFact("AcDbLine", "M-Pipe", 3000.0, 0.0, null));
        list.Add(new CurveFact("AcDbPolyline", "M-DUCT", 2500.25, 1000.0, true));
        list.Add(new CurveFact("AcDbHatch", "M-PIPE", null, 5000.0, null));
        Assert.Equal(3, list.Count);
        Assert.Equal(
            "{\"items\":[[\"AcDbLine\",\"M-Pipe\",3000,0,null,null],[\"AcDbPolyline\",\"M-DUCT\",2500.25,1000,true,null],"
            + "[\"AcDbHatch\",\"M-PIPE\",null,5000,null,null]]}",
            Written(list.Write));
    }

    [Fact]
    public void A_spline_and_an_ellipse_go_with_their_definitions_for_the_server_to_measure()
    {
        var plain = new CurveFact("AcDbSpline", "0", null, 12.5, false)
            .Spline(3, false, new[] { 0.0, 0.0, 0.0, 1.5, 2.0, 0.0 }, new[] { 0.0, 0.0, 1.0, 1.0 }, new[] { 9.0 });
        var rational = new CurveFact("AcDbSpline", "0", null, null, true)
            .Spline(2, true, new[] { 0.0, 0.0, 0.0 }, new[] { 0.0, 1.0 }, new[] { 1.0, 0.7071067811865476 });
        var ellipse = new CurveFact("AcDbEllipse", "0", null, 100.0, true).Ellipse(100.0, 50.0, 0.0, 6.283185307179586);
        var list = new CurveFactList();
        list.Add(plain);
        list.Add(rational);
        list.Add(ellipse);
        var items = JsonDocument.Parse(Written(list.Write)).RootElement.GetProperty("items");
        // Weights only for a rational spline, as COM's path reads them.
        Assert.Equal("[\"spline\",3,false,[0,0,0,1.5,2,0],[0,0,1,1],[]]", items[0][5].GetRawText());
        // .NET Framework writes 0.70710678118654757 and .NET 10 0.7071067811865476: the same double read back.
        Assert.Equal("\"spline\",2,true,[0,0,0],[0,1]", string.Join(",", items[1][5].EnumerateArray().Take(5).Select(e => e.GetRawText())));
        Assert.Equal(0.7071067811865476, items[1][5][5][1].GetDouble());
        Assert.Equal("ellipse", items[2][5][0].GetString());
        Assert.Equal(new[] { 100.0, 50.0, 0.0, 6.283185307179586 }, items[2][5].EnumerateArray().Skip(1).Select(e => e.GetDouble()).ToArray());
    }

    [Fact]
    public void With_classes_only_those_are_read_and_without_every_one()
    {
        var curves = new CurveFactList(new[] { "AcDbLine", "AcDbArc" });
        Assert.True(curves.Wanted("AcDbLine"));
        Assert.False(curves.Wanted("AcDbText"));
        Assert.False(curves.Wanted("acdbline")); // COM's ObjectName, case and all
        curves.Add(new CurveFact("AcDbText", "0", null, null, null));
        curves.Add(new CurveFact("AcDbArc", "0", 1.0, 2.0, false));
        Assert.Equal(1, curves.Count);
        var every = new CurveFactList(new string[0]);
        Assert.True(every.Wanted("AcDbText"));
        Assert.True(new CurveFactList(null).Wanted("AcDbHatch"));
    }

    [Fact]
    public void Texts_come_one_group_per_filter_with_formatting_codes_left_in()
    {
        var list = new TextFactList();
        list.Group();
        list.Add("2A", "A-ANNO", "DN50", new[] { 100.0, 200.5, 0.0 }, null, null);
        list.Group();
        list.Add("2B", "A-ANNO", "{\\fArial|b1;ROOM 12}\\PFFL 0.00", new[] { 0.0, 0.0, 0.0 }, null, null);
        list.Group();
        list.Add("2C", "M-EQUIP", null, new[] { 50.0, 60.0, 0.0 }, "*U7", new[]
        {
            new TextAttribute("SIZE", "DN50", false, false),
            new TextAttribute("NOTE", "line one", true, false),
            new TextAttribute("MAKER", "ACME", false, true),
        });
        list.Add("2D", "A-ANNO", null, new[] { 1.0, 2.0, 0.0 }, "ROOM", new TextAttribute[0]);
        list.Group(); // a filter that selected nothing still has its group
        Assert.Equal(4, list.Groups);
        var groups = JsonDocument.Parse(Written(list.Write)).RootElement.GetProperty("groups");
        Assert.Equal(4, groups.GetArrayLength());
        Assert.Equal("[[\"2A\",\"A-ANNO\",\"DN50\",[100,200.5,0],null,null]]", groups[0].GetRawText());
        Assert.Equal("{\\fArial|b1;ROOM 12}\\PFFL 0.00", groups[1][0][2].GetString());
        Assert.Equal(
            "[\"2C\",\"M-EQUIP\",null,[50,60,0],\"*U7\",[[\"SIZE\",\"DN50\",false,false],[\"NOTE\",\"line one\",true,false],"
            + "[\"MAKER\",\"ACME\",false,true]]]",
            groups[2][0].GetRawText());
        Assert.Equal("[]", groups[2][1][5].GetRawText());
        Assert.Equal("[]", groups[3].GetRawText());
    }

    [Fact]
    public void An_object_that_is_not_text_goes_without_text_or_point()
    {
        var list = new TextFactList();
        list.Add("3F", "0", null, null, null, null);
        Assert.Equal("{\"groups\":[[[\"3F\",\"0\",null,null,null,null]]]}", Written(list.Write));
    }

    [Fact]
    public void The_filters_are_read_like_count_entities_filter()
    {
        var filters = TextFactList.ParseFilters(JsonDocument.Parse("[[[0,\"TEXT\"],[8,\"M-*\"]],[[0,\"MTEXT\"]],[]]").RootElement);
        Assert.Equal(3, filters.Count);
        Assert.Equal("M-*", filters[0][1].Text);
        Assert.Empty(filters[2]); // no pairs: everything
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("null")]
    [InlineData("{\"a\":1}")]
    [InlineData("[[[0,\"TEXT\"]],[],[],[],[],[],[],[],[]]")]
    [InlineData("[[[999,\"TEXT\"]]]")]
    public void Filters_that_are_none_too_many_or_unknown_are_refused(string json)
    {
        Assert.Throws<RunRefusal>(() => TextFactList.ParseFilters(JsonDocument.Parse(json).RootElement));
    }

    [Fact]
    public void Both_reads_are_reads()
    {
        foreach (var name in new[] { "entity_lengths", "entity_texts" })
        {
            Assert.True(PluginOperations.TryLevel(name, out var level), name);
            Assert.Equal(Risk.Read, level);
        }
    }

    [Theory]
    [InlineData("entity_lengths", "autocad_total_length")]
    [InlineData("entity_lengths", "autocad_measure")]
    [InlineData("entity_texts", "autocad_count_text")]
    [InlineData("entity_texts", "autocad_find_text")]
    public void A_read_job_may_ask_for_them_with_every_padlock_off(string operation, string tool)
    {
        const string token = "tok";
        var host = new FakeHost { RunAnswer = RunResult.Done(w => { w.WriteStartArray("items"); w.WriteEndArray(); }) };
        var protocol = new BridgeProtocol(host, () => new HeronConfig(), token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();

        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool, risk = "read",
            summary = "Read", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        var reply = Send(new
        {
            op = "run", token, conversation = "chat-a", job = "j1", operation,
            args = new { filter = new object[] { new object[] { 8, "M-*" } }, classes = new[] { "AcDbLine" } },
        });

        Assert.True(reply.GetProperty("ok").GetBoolean());
        var run = Assert.Single(host.Runs);
        Assert.Equal(operation, run.Operation);
        Assert.Equal("[\"AcDbLine\"]", JsonDocument.Parse(run.Args).RootElement.GetProperty("classes").GetRawText());
    }

    [Fact]
    public void A_plug_in_without_them_says_so_in_words_the_server_falls_back_on()
    {
        // Plug-ins 1.8.0 and 1.8.1 have count_entities but not these: tools/_shared.faster_read reads this as "use COM".
        Assert.Contains("does not have the operation 'entity_lengths'", Texts.UnknownOperation("entity_lengths"));
        Assert.Contains("does not have the operation 'entity_texts'", Texts.UnknownOperation("entity_texts"));
    }
}
