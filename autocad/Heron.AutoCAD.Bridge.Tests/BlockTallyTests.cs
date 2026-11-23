using System.IO;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The block reads the plug-in does in one go (#192, #194, D-127): what it
/// writes for autocad_count_blocks and autocad_list_blocks. The server builds
/// the same answer from these as from COM, so names keep their case, the
/// order is AutoCAD's, and every dynamic property value carries its type.
/// tests/test_plugin_block_reads.py holds the server side to this.
/// </summary>
public class BlockTallyTests
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

    private static string Value(object? value, bool failed = false) => Written(w =>
    {
        w.WriteStartArray("v");
        DynamicValue.Write(w, value, failed);
        w.WriteEndArray();
    });

    [Fact]
    public void A_whole_number_distance_goes_as_real_so_the_server_reads_it_back_as_50_point_0()
    {
        // The trap of #192: the number alone is written 50, which Python reads as an int.
        Assert.Equal("{\"v\":[\"real\",50]}", Value(50.0));
        Assert.Equal("{\"v\":[\"real\",1.25]}", Value(1.25));
        var tenth = JsonDocument.Parse(Value(0.1)).RootElement.GetProperty("v")[1].GetDouble();
        Assert.Equal(0.1, tenth); // full precision, not rounded
    }

    [Fact]
    public void A_flip_state_goes_as_int_and_a_list_choice_as_text()
    {
        Assert.Equal("{\"v\":[\"int\",1]}", Value((short)1));
        Assert.Equal("{\"v\":[\"int\",-3]}", Value(-3));
        Assert.Equal("{\"v\":[\"int\",7]}", Value(7L));
        Assert.Equal("{\"v\":[\"text\",\"DN50\"]}", Value("DN50"));
    }

    [Fact]
    public void A_point_goes_as_its_numbers()
    {
        Assert.Equal("{\"v\":[\"point\",[0,2.5,0]]}", Value(new[] { 0.0, 2.5, 0.0 }));
        Assert.Equal("point", DynamicValue.Kind(new[] { 1.0, 2.0 }, false));
    }

    [Fact]
    public void No_value_a_refused_value_and_an_unknown_type_are_named_so()
    {
        Assert.Equal("{\"v\":[\"none\",null]}", Value(null));
        Assert.Equal("{\"v\":[\"error\",null]}", Value(5.0, failed: true));
        // The server reads the drawing over COM when it needs such a value.
        Assert.Equal("{\"v\":[\"other\",\"Boolean\"]}", Value(true));
        Assert.Equal("other", DynamicValue.Kind(double.NaN, false));
        Assert.Equal("other", DynamicValue.Kind(double.PositiveInfinity, false));
        Assert.Equal("other", DynamicValue.Kind(new[] { 0.0, double.NaN }, false));
        Assert.Equal("other", DynamicValue.Kind(new object(), false));
    }

    [Fact]
    public void Every_reference_comes_in_the_order_selected_with_its_properties_in_AutoCADs_order()
    {
        var list = new BlockReferenceList();
        list.Add("GATE VALVE", "M-Pipe", new[]
        {
            new DynamicProperty("Size", false, 50.0),
            new DynamicProperty("Visibility1", false, "Open"),
            new DynamicProperty("Origin", true, new[] { 0.0, 0.0, 0.0 }),
        });
        list.Add("ROOM", "A-AREA", null);
        list.Add("GATE VALVE", "M-Pipe", new[] { new DynamicProperty("Size", false, null, failed: true) });
        Assert.Equal(3, list.Count);
        Assert.Equal(
            "{\"refs\":[[\"GATE VALVE\",\"M-Pipe\",[[\"Size\",false,\"real\",50],[\"Visibility1\",false,\"text\",\"Open\"],"
            + "[\"Origin\",true,\"point\",[0,0,0]]]],[\"ROOM\",\"A-AREA\",[]],[\"GATE VALVE\",\"M-Pipe\",[[\"Size\",false,\"error\",null]]]]}",
            Written(w => list.Write(w, nested: false)));
    }

    [Fact]
    public void Children_come_only_when_asked_for_by_definition_in_the_order_met()
    {
        var list = new BlockReferenceList();
        list.Add("ROOM", "A-AREA", null);
        list.AddChild("ROOM", "DESK", "A-FURN");
        list.AddChild("DESK", "CHAIR", "A-FURN");
        list.AddChild("ROOM", "DESK", "A-Furn");
        Assert.DoesNotContain("children", Written(w => list.Write(w, nested: false)));
        var reply = JsonDocument.Parse(Written(w => list.Write(w, nested: true))).RootElement;
        Assert.Equal(
            "[[\"ROOM\",[[\"DESK\",\"A-FURN\"],[\"DESK\",\"A-Furn\"]]],[\"DESK\",[[\"CHAIR\",\"A-FURN\"]]]]",
            reply.GetProperty("children").GetRawText());
    }

    [Fact]
    public void Nested_with_none_inside_still_says_children()
    {
        // So the server can tell this plug-in honoured "nested".
        Assert.Equal("{\"refs\":[],\"children\":[]}", Written(w => new BlockReferenceList().Write(w, nested: true)));
    }

    [Fact]
    public void Definitions_keep_their_facts_and_counts_go_by_real_name_with_its_case()
    {
        var list = new BlockDefinitionList();
        list.Add("DESK", 4, false, @"ignored", false, new[] { "TAG", "DESK-NO" });
        list.Add("SITE", 12, true, @"C:\Project\Site.dwg", false, null);
        list.Add("GATE VALVE", 2, false, null, true, new string[0]);
        list.Instance("GATE VALVE");
        list.Instance("gate valve");
        list.Instance("GATE VALVE");
        Assert.DoesNotContain("instances", Written(w => list.Write(w, counts: false)));
        var reply = JsonDocument.Parse(Written(w => list.Write(w, counts: true))).RootElement;
        Assert.Equal(
            "[{\"name\":\"DESK\",\"count\":4,\"xref\":false,\"path\":null,\"dynamic\":false,\"tags\":[\"TAG\",\"DESK-NO\"]},"
            + "{\"name\":\"SITE\",\"count\":12,\"xref\":true,\"path\":\"C:\\\\Project\\\\Site.dwg\",\"dynamic\":false,\"tags\":[]},"
            + "{\"name\":\"GATE VALVE\",\"count\":2,\"xref\":false,\"path\":null,\"dynamic\":true,\"tags\":[]}]",
            reply.GetProperty("definitions").GetRawText());
        // The server matches names without case, as it does over COM.
        Assert.Equal("[[\"GATE VALVE\",2],[\"gate valve\",1]]", reply.GetProperty("instances").GetRawText());
    }

    [Theory]
    [InlineData("DESK", true)]
    [InlineData(" ", true)] // blank: the server decides, as it does over COM
    [InlineData("SITE|LAMP", true)]
    [InlineData("*Model_Space", false)]
    [InlineData("*U12", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void Anonymous_and_layout_blocks_are_not_read(string? name, bool listed)
    {
        Assert.Equal(listed, BlockDefinitionList.Listed(name));
    }

    [Fact]
    public void Both_block_reads_are_reads()
    {
        foreach (var name in new[] { "block_references", "block_definitions" })
        {
            Assert.True(PluginOperations.TryLevel(name, out var level), name);
            Assert.Equal(Risk.Read, level);
        }
    }

    [Theory]
    [InlineData("block_references", "autocad_count_blocks")]
    [InlineData("block_definitions", "autocad_list_blocks")]
    public void A_read_job_may_ask_for_them_with_every_padlock_off(string operation, string tool)
    {
        const string token = "tok";
        var host = new FakeHost { RunAnswer = RunResult.Done(w => { w.WriteStartArray("refs"); w.WriteEndArray(); }) };
        var protocol = new BridgeProtocol(host, () => new HeronConfig(), token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();

        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool, risk = "read",
            summary = "Count", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        var reply = Send(new { op = "run", token, conversation = "chat-a", job = "j1", operation, args = new { filter = new object[] { new object[] { 0, "INSERT" } }, nested = true } });

        Assert.True(reply.GetProperty("ok").GetBoolean());
        var run = Assert.Single(host.Runs);
        Assert.Equal(operation, run.Operation);
        Assert.Equal("[[0,\"INSERT\"]]", JsonDocument.Parse(run.Args).RootElement.GetProperty("filter").GetRawText());
    }

    [Fact]
    public void An_operation_this_plug_in_lacks_is_refused_and_the_read_job_still_ends_normally()
    {
        // What 1.8.0 and 1.8.1 do with block_references on every call: the server then reads over COM
        // inside the same job, which must still end as usual.
        const string token = "tok";
        var host = new FakeHost();
        var protocol = new BridgeProtocol(host, () => new HeronConfig(), token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();

        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool = "autocad_count_blocks", risk = "read",
            summary = "Count", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        var reply = Send(new { op = "run", token, conversation = "chat-a", job = "j1", operation = "block_counts_v9", args = new { } });

        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Equal("BadRequest", reply.GetProperty("refusedBy").GetString());
        Assert.Contains("does not have the operation 'block_counts_v9'", reply.GetProperty("message").GetString());
        Assert.Empty(host.Runs);
        Assert.True(Send(new { op = "end", token, conversation = "chat-a", job = "j1", ok = true, outcome = "done", summary = "Count", ms = 5 })
            .GetProperty("ok").GetBoolean());
    }

    [Fact]
    public void A_plug_in_without_them_says_so_in_words_the_server_falls_back_on()
    {
        // Plug-ins 1.8.0 and 1.8.1 have count_entities but not these: tools/_shared.faster_read reads this as "use COM".
        Assert.Contains("does not have the operation 'block_references'", Texts.UnknownOperation("block_references"));
    }
}
