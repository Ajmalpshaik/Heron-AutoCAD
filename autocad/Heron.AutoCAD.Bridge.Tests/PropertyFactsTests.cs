using System.IO;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The entity read autocad_check_standards' rules need, done by the plug-in in
/// one go (#196, D-143): each selected object's handle, class, layer, colour,
/// linetype and, for the classes asked, its box, in the order selected, up to
/// the limit; the rules stay in the server. tests/test_plugin_standards_reads.py
/// holds the server side to this.
/// </summary>
public class PropertyFactsTests
{
    private static string Written(PropertyFactList list)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            list.Write(writer);
            writer.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    [Fact]
    public void Each_object_goes_with_its_handle_class_layer_colour_linetype_and_box()
    {
        var list = new PropertyFactList(0, "Dimension");
        Assert.True(list.Take());
        list.Add(new PropertyFact("2A", "AcDbLine", "0", 256, "ByLayer", null));
        Assert.True(list.Take());
        list.Add(new PropertyFact("2B", "AcDbRotatedDimension", "A-DIMS", 1, "DASHED", new[] { 0.0, -5.5, 100.0, 20.25 }));
        Assert.Equal(
            "{\"entities\":[[\"2A\",\"AcDbLine\",\"0\",256,\"ByLayer\",null],"
            + "[\"2B\",\"AcDbRotatedDimension\",\"A-DIMS\",1,\"DASHED\",[0,-5.5,100,20.25]]],\"total\":2}",
            Written(list));
    }

    [Theory]
    [InlineData(PropertyFact.ByLayer, 256, 256)]
    [InlineData(PropertyFact.ByBlock, 0, 0)]
    [InlineData(PropertyFact.ByAci, 1, 1)]
    [InlineData(PropertyFact.ByAci, 255, 255)]
    public void A_colour_goes_as_COM_numbers_it(int method, int index, int com)
    {
        Assert.Equal(com, PropertyFact.ComColor(method, index));
    }

    [Theory]
    [InlineData(194, 7)]  // a true colour: its COM Color is not looked at yet, so the server reads over COM
    [InlineData(196, 7)]  // by pen
    [InlineData(197, 7)]  // foreground
    [InlineData(200, 7)]  // none
    [InlineData(PropertyFact.ByAci, 0)]
    [InlineData(PropertyFact.ByAci, 256)]
    public void A_colour_that_is_not_an_index_goes_as_null(int method, int index)
    {
        Assert.Null(PropertyFact.ComColor(method, index));
        var list = new PropertyFactList(0, null);
        list.Take();
        list.Add(new PropertyFact("2C", "AcDbCircle", "0", PropertyFact.ComColor(method, index), "ByLayer", null));
        Assert.Equal("{\"entities\":[[\"2C\",\"AcDbCircle\",\"0\",null,\"ByLayer\",null]],\"total\":1}", Written(list));
    }

    [Fact]
    public void Past_the_limit_objects_are_counted_and_not_read()
    {
        var list = new PropertyFactList(2, null);
        Assert.True(list.Take());
        Assert.True(list.Take());
        Assert.False(list.Take());
        Assert.False(list.Take());
        Assert.Equal(4, list.Total);
        Assert.Equal(2, list.Limit);
        Assert.EndsWith(",\"total\":4}", Written(list));
    }

    [Fact]
    public void No_limit_reads_every_one()
    {
        var list = new PropertyFactList(0, null);
        for (var i = 0; i < 1000; i++) Assert.True(list.Take());
        Assert.Equal(1000, list.Total);
    }

    [Theory]
    [InlineData("Dimension", "AcDbRotatedDimension", true)]
    [InlineData("Dimension", "AcDbRadialDimensionLarge", true)]
    [InlineData("Dimension", "AcDbLine", false)]
    [InlineData("Dimension", "acdbaligneddimension", false)]  // as COM's test in the server: the case counts
    [InlineData("", "AcDbRotatedDimension", false)]
    [InlineData(null, "AcDbRotatedDimension", false)]
    public void A_box_is_read_only_for_the_classes_asked(string? boxClasses, string objectClass, bool wanted)
    {
        Assert.Equal(wanted, new PropertyFactList(0, boxClasses).WantsBox(objectClass));
    }

    [Fact]
    public void A_box_corner_that_is_not_finite_is_named_so()
    {
        var list = new PropertyFactList(0, "Dimension");
        list.Take();
        list.Add(new PropertyFact("2D", "AcDbAlignedDimension", "0", 256, "ByLayer", new[] { double.NaN, 0.0, 1.0, 1.0 }));
        Assert.Contains("[\"not finite\",0,1,1]", Written(list));
    }

    [Fact]
    public void Nothing_selected_is_an_empty_list()
    {
        var list = new PropertyFactList(20000, null);
        list.Add(null!);
        Assert.Equal(0, list.Count);
        Assert.Equal("{\"entities\":[],\"total\":0}", Written(list));
    }

    [Fact]
    public void It_is_a_read()
    {
        Assert.True(PluginOperations.TryLevel("entity_properties", out var level));
        Assert.Equal(Risk.Read, level);
    }

    [Fact]
    public void The_check_s_read_job_may_ask_for_it_with_the_padlocks_off()
    {
        const string token = "tok";
        var config = new HeronConfig { WriteEnabled = false, PublishEnabled = false };
        var host = new FakeHost { RunAnswer = RunResult.Done(w => { w.WriteStartArray("entities"); w.WriteEndArray(); w.WriteNumber("total", 0); }) };
        var protocol = new BridgeProtocol(host, () => config, token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();

        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool = "autocad_check_standards", risk = "read",
            summary = "Check standards", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        var reply = Send(new
        {
            op = "run", token, conversation = "chat-a", job = "j1", operation = "entity_properties",
            args = new { filter = new object[0], limit = 20000, box_classes = "Dimension" },
        });

        Assert.True(reply.GetProperty("ok").GetBoolean(), reply.GetRawText());
        Assert.Equal(0, reply.GetProperty("result").GetProperty("total").GetInt32());
        var run = Assert.Single(host.Runs);
        Assert.Equal("entity_properties", run.Operation);
        var args = JsonDocument.Parse(run.Args).RootElement;
        Assert.Equal(20000, args.GetProperty("limit").GetInt32());
        Assert.Equal("Dimension", args.GetProperty("box_classes").GetString());
    }

    [Fact]
    public void A_plug_in_without_it_says_so_in_words_the_server_falls_back_on()
    {
        // Plug-ins 1.8.0 and 1.8.1, and one built before D-143: tools/_shared.faster_read reads this as "use COM".
        Assert.Contains("does not have the operation 'entity_properties'", Texts.UnknownOperation("entity_properties"));
    }
}
