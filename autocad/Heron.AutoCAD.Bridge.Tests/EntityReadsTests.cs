using System.IO;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// Reads over the whole drawing that the plug-in does in one go instead of a
/// COM round trip per object (D-114): the filter it takes, what it counts and
/// the box it measures. The server turns these into the same answer it gives
/// from COM, so the raw class names and full numbers must come through.
/// </summary>
public class EntityReadsTests
{
    private static JsonElement Written(System.Action<Utf8JsonWriter> body)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            body(writer);
            writer.WriteEndObject();
        }
        return JsonDocument.Parse(Encoding.UTF8.GetString(stream.ToArray())).RootElement.Clone();
    }

    private static JsonElement Json(string text) => JsonDocument.Parse(text).RootElement.Clone();

    [Fact]
    public void Counts_come_by_class_and_by_layer_in_the_order_first_met()
    {
        var tally = new EntityTally();
        tally.Count("AcDbLine", "M-DUCT");
        tally.Count("AcDbRotatedDimension", "A-DIMS");
        tally.Count("AcDbLine", "M-DUCT");
        tally.Count("AcDbAlignedDimension", "M-DUCT");
        var reply = Written(tally.WriteCounts);
        Assert.Equal(4, reply.GetProperty("total").GetInt32());
        Assert.Equal("[[\"AcDbLine\",2],[\"AcDbRotatedDimension\",1],[\"AcDbAlignedDimension\",1]]", reply.GetProperty("by_class").GetRawText());
        Assert.Equal("[[\"M-DUCT\",3],[\"A-DIMS\",1]]", reply.GetProperty("by_layer").GetRawText());
    }

    [Fact]
    public void Layer_names_keep_their_case_as_COM_gives_them()
    {
        var tally = new EntityTally();
        tally.Count("AcDbLine", "M-Duct");
        tally.Count("AcDbLine", "M-Duct");
        Assert.Equal("[[\"M-Duct\",2]]", Written(tally.WriteCounts).GetProperty("by_layer").GetRawText());
    }

    [Fact]
    public void Past_the_cut_off_an_object_is_in_the_total_but_not_counted_by_class()
    {
        // autocad_drawing_report counts the first 50,000 model space objects by type (#193).
        var tally = new EntityTally();
        tally.Count("AcDbLine", "0");
        tally.Skip();
        tally.Skip();
        var reply = Written(tally.WriteCounts);
        Assert.Equal(3, reply.GetProperty("total").GetInt32());
        Assert.Equal("[[\"AcDbLine\",1]]", reply.GetProperty("by_class").GetRawText());
    }

    [Fact]
    public void Nothing_selected_is_a_count_of_none()
    {
        var reply = Written(new EntityTally().WriteCounts);
        Assert.Equal(0, reply.GetProperty("total").GetInt32());
        Assert.Equal(0, reply.GetProperty("by_class").GetArrayLength());
    }

    [Fact]
    public void The_box_goes_round_every_object_with_extents_at_full_precision()
    {
        var tally = new EntityTally();
        tally.Measure(new[] { 0.1234567891234, 5.0, 0.0 }, new[] { 10.0, 20.0, 0.0 });
        tally.Measure(new[] { -3.0, 7.0, -1.0 }, new[] { 4.0, 25.5, 2.0 });
        var reply = Written(tally.WriteBox);
        Assert.Equal(2, reply.GetProperty("total").GetInt32());
        Assert.Equal(2, reply.GetProperty("measured").GetInt32());
        Assert.Equal(-3.0, reply.GetProperty("min")[0].GetDouble());
        Assert.Equal(5.0, reply.GetProperty("min")[1].GetDouble());
        Assert.Equal(-1.0, reply.GetProperty("min")[2].GetDouble());
        Assert.Equal(new[] { 10.0, 25.5, 2.0 }, new[] { reply.GetProperty("max")[0].GetDouble(), reply.GetProperty("max")[1].GetDouble(), reply.GetProperty("max")[2].GetDouble() });

        var one = new EntityTally();
        one.Measure(new[] { 0.1234567891234, 5.0, 0.0 }, new[] { 10.0, 20.0, 0.0 });
        // Not rounded: the server rounds, once, as it does for COM.
        Assert.Equal(0.1234567891234, Written(one.WriteBox).GetProperty("min")[0].GetDouble());
    }

    [Fact]
    public void A_ray_or_a_construction_line_is_counted_but_not_measured()
    {
        var tally = new EntityTally();
        tally.Measure(null, null);
        tally.Measure(new[] { double.NegativeInfinity, 0.0, 0.0 }, new[] { 1.0, 1.0, 0.0 });
        var reply = Written(tally.WriteBox);
        Assert.Equal(2, reply.GetProperty("total").GetInt32());
        Assert.Equal(0, reply.GetProperty("measured").GetInt32());
        Assert.Equal(JsonValueKind.Null, reply.GetProperty("min").ValueKind);
        Assert.Equal(JsonValueKind.Null, reply.GetProperty("max").ValueKind);
    }

    [Fact]
    public void No_filter_selects_everything()
    {
        Assert.Empty(EntityFilter.Parse(default));
        Assert.Empty(EntityFilter.Parse(Json("null")));
        Assert.Empty(EntityFilter.Parse(Json("[]")));
    }

    [Fact]
    public void The_filter_takes_the_type_layer_block_name_and_colour_the_server_sends()
    {
        var pairs = EntityFilter.Parse(Json("[[0, \"INSERT\"], [8, \"M-*\"], [2, \"VALVE`*\"], [62, 1]]"));
        Assert.Equal(4, pairs.Count);
        Assert.Equal((0, "INSERT"), (pairs[0].Code, pairs[0].Text));
        Assert.Equal((8, "M-*"), (pairs[1].Code, pairs[1].Text));
        Assert.Equal((2, "VALVE`*"), (pairs[2].Code, pairs[2].Text));
        Assert.Equal(62, pairs[3].Code);
        Assert.Equal(1, pairs[3].Number);
        Assert.Null(pairs[3].Text);
    }

    [Theory]
    [InlineData("{\"layer\": \"M-*\"}")]
    [InlineData("[[1, \"text\"]]")]
    [InlineData("[[-4, \"<or\"]]")]
    [InlineData("[[8]]")]
    [InlineData("[[8, \"\"]]")]
    [InlineData("[[8, 5]]")]
    [InlineData("[\"8\"]")]
    public void Anything_else_in_the_filter_is_refused(string filter)
    {
        var refusal = Assert.Throws<RunRefusal>(() => EntityFilter.Parse(Json(filter)));
        Assert.Contains("type, layer, block name and colour", refusal.Message);
    }

    [Theory]
    [InlineData("[[62, 257]]")]
    [InlineData("[[62, -1]]")]
    [InlineData("[[62, \"red\"]]")]
    [InlineData("[[62, 1.5]]")]
    public void A_colour_is_a_number_from_0_to_256(string filter)
    {
        var refusal = Assert.Throws<RunRefusal>(() => EntityFilter.Parse(Json(filter)));
        Assert.Contains("0 to 256", refusal.Message);
    }

    [Fact]
    public void Both_reads_are_reads()
    {
        foreach (var name in new[] { "count_entities", "entity_extents" })
        {
            Assert.True(PluginOperations.TryLevel(name, out var level), name);
            Assert.Equal(Risk.Read, level);
        }
    }

    [Theory]
    [InlineData("count_entities")]
    [InlineData("entity_extents")]
    public void A_read_job_may_ask_for_them_with_every_padlock_off(string operation)
    {
        const string token = "tok";
        var host = new FakeHost { RunAnswer = RunResult.Done(w => w.WriteNumber("total", 3)) };
        var protocol = new BridgeProtocol(host, () => new HeronConfig(), token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();

        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool = "autocad_list_entities", risk = "read",
            summary = "List", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        var reply = Send(new { op = "run", token, conversation = "chat-a", job = "j1", operation, args = new { filter = new object[] { new object[] { 8, "M-*" } } } });

        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.Equal(3, reply.GetProperty("result").GetProperty("total").GetInt32());
        var run = Assert.Single(host.Runs);
        Assert.Equal(operation, run.Operation);
        Assert.Equal("[[8,\"M-*\"]]", JsonDocument.Parse(run.Args).RootElement.GetProperty("filter").GetRawText());
    }

    [Fact]
    public void A_plug_in_without_them_says_so_in_words_the_server_falls_back_on()
    {
        // core/bridge.py and tools/_shared.faster_read read this refusal as "read it over COM".
        Assert.Contains("does not have the operation 'count_entities'", Texts.UnknownOperation("count_entities"));
    }
}
