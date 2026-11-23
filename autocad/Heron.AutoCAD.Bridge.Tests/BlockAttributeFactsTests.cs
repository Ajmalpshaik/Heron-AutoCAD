using System.IO;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The block attribute read the plug-in does in one go (#198, D-138): what it
/// writes for autocad_extract_attributes, autocad_export_attribute_sheet and the
/// reads of autocad_set_attributes and autocad_apply_attribute_sheet. Every
/// selected block reference, in the order selected, with what the server's COM
/// loop reads off it; the server skips and matches them itself.
/// tests/test_plugin_attribute_reads.py holds the server side to this.
/// </summary>
public class BlockAttributeFactsTests
{
    private static string Written(BlockAttributeList list)
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
    public void Each_block_goes_with_its_names_layer_point_layout_and_attributes_in_their_own_order()
    {
        var list = new BlockAttributeList();
        list.Add(new BlockAttributeFact("2A", "*U7", "CAMERA", "E-CCTV", new[] { 100.0, 200.5, 0.0 }, "Model", true, new[]
        {
            new TextAttribute("TAG", "CAM-01", false, false),
            new TextAttribute("TYPE", "DOME", false, false, invisible: true),
            new TextAttribute("TAG", "CAM-01B", false, false),
        }));
        list.Add(new BlockAttributeFact("3A", "TITLEBLOCK", "TITLEBLOCK", "A-TITLE", new[] { 0.0, 0.0, 0.0 }, "E-101", true, new[]
        {
            new TextAttribute("NOTE", "line one", true, false),
            new TextAttribute("MAKER", "ACME", false, true),
        }));
        Assert.Equal(2, list.Count);
        // [tag, text, invisible, constant, multiline]; a whole-number double goes as 100, read back by the server as 100.0.
        Assert.Equal(
            "{\"blocks\":[[\"2A\",\"*U7\",\"CAMERA\",\"E-CCTV\",[100,200.5,0],\"Model\",true,"
            + "[[\"TAG\",\"CAM-01\",false,false,false],[\"TYPE\",\"DOME\",true,false,false],[\"TAG\",\"CAM-01B\",false,false,false]]],"
            + "[\"3A\",\"TITLEBLOCK\",\"TITLEBLOCK\",\"A-TITLE\",[0,0,0],\"E-101\",true,"
            + "[[\"NOTE\",\"line one\",false,false,true],[\"MAKER\",\"ACME\",false,true,false]]]]}",
            Written(list));
    }

    [Fact]
    public void A_block_without_attributes_still_goes_with_whether_its_definition_has_any()
    {
        var list = new BlockAttributeList();
        list.Add(new BlockAttributeFact("2C", "DOOR", "DOOR", "A-DOOR", new[] { 1.0, 2.0, 0.0 }, "Model", false, new TextAttribute[0]));
        list.Add(new BlockAttributeFact("2F", "STAMP", "STAMP", "0", new[] { 1.0, 2.0, 0.0 }, "Model", true, new TextAttribute[0]));
        var blocks = JsonDocument.Parse(Written(list)).RootElement.GetProperty("blocks");
        Assert.Equal("[\"2C\",\"DOOR\",\"DOOR\",\"A-DOOR\",[1,2,0],\"Model\",false,[]]", blocks[0].GetRawText());
        Assert.True(blocks[1][6].GetBoolean()); // the server reads that one over COM (D-138)
    }

    [Fact]
    public void What_the_plugin_could_not_read_goes_as_null_and_a_number_that_is_not_finite_is_named_so()
    {
        var list = new BlockAttributeList();
        list.Add(new BlockAttributeFact("3C", "TB", null, "0", new[] { double.NaN, 0.0, 0.0 }, null, true, null));
        Assert.Equal("{\"blocks\":[[\"3C\",\"TB\",null,\"0\",[\"not finite\",0,0],null,true,null]]}", Written(list));
    }

    [Fact]
    public void Nothing_selected_is_an_empty_list()
    {
        var list = new BlockAttributeList();
        list.Add(null!);
        Assert.Equal(0, list.Count);
        Assert.Equal("{\"blocks\":[]}", Written(list));
    }

    [Fact]
    public void Entity_texts_still_writes_its_attributes_without_the_invisible_flag()
    {
        var texts = new TextFactList();
        texts.Add("2A", "0", null, new[] { 0.0, 0.0, 0.0 }, "B", new[] { new TextAttribute("T", "V", false, false, invisible: true) });
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            texts.Write(writer);
            writer.WriteEndObject();
        }
        Assert.Equal("{\"groups\":[[[\"2A\",\"0\",null,[0,0,0],\"B\",[[\"T\",\"V\",false,false]]]]]}", Encoding.UTF8.GetString(stream.ToArray()));
    }

    [Fact]
    public void It_is_a_read()
    {
        Assert.True(PluginOperations.TryLevel("block_attributes", out var level));
        Assert.Equal(Risk.Read, level);
    }

    [Theory]
    [InlineData("read", "autocad_extract_attributes")]
    [InlineData("publish", "autocad_export_attribute_sheet")]
    [InlineData("change", "autocad_set_attributes")]
    [InlineData("change", "autocad_apply_attribute_sheet")]
    public void Each_tool_s_job_may_ask_for_it(string risk, string tool)
    {
        const string token = "tok";
        // The padlocks each job needs are on at begin (Publish only widens Changes), then turned
        // off: the read inside it is never held by one.
        var config = new HeronConfig { WriteEnabled = risk != "read", PublishEnabled = risk == "publish" };
        var host = new FakeHost { RunAnswer = RunResult.Done(w => { w.WriteStartArray("blocks"); w.WriteEndArray(); }) };
        var protocol = new BridgeProtocol(host, () => config, token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();

        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool, risk,
            summary = "Attributes", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        config.WriteEnabled = false;
        config.PublishEnabled = false;
        var reply = Send(new
        {
            op = "run", token, conversation = "chat-a", job = "j1", operation = "block_attributes",
            args = new { filter = new object[] { new object[] { 0, "INSERT" }, new object[] { 8, "E-*" } } },
        });

        Assert.True(reply.GetProperty("ok").GetBoolean(), reply.GetRawText());
        Assert.Equal("[]", reply.GetProperty("result").GetProperty("blocks").GetRawText());
        var run = Assert.Single(host.Runs);
        Assert.Equal("block_attributes", run.Operation);
        Assert.Equal("[[0,\"INSERT\"],[8,\"E-*\"]]", JsonDocument.Parse(run.Args).RootElement.GetProperty("filter").GetRawText());
    }

    [Fact]
    public void A_plug_in_without_it_says_so_in_words_the_server_falls_back_on()
    {
        // Plug-ins 1.8.0 and 1.8.1, and one built before D-138: tools/_shared.faster_read reads this as "use COM".
        Assert.Contains("does not have the operation 'block_attributes'", Texts.UnknownOperation("block_attributes"));
    }
}
