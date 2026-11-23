using System.IO;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// autocad_merge_layers in the plug-in (#199, D-146): the objects on the old
/// layers it sends (layer_objects), and the merge it makes in one transaction
/// (merge_layers), all of it or none. tests/test_plugin_merge_layers.py holds
/// the server side to this.
/// </summary>
public class LayerMergeTests
{
    private static string Written(System.Action<Utf8JsonWriter> write)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            write(writer);
            writer.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    private static RunArgs Args(object value) => RunArgs.Parse(JsonSerializer.Serialize(value));

    [Fact]
    public void The_objects_go_in_the_order_found_each_with_where_it_is()
    {
        var list = new LayerObjectList(new[] { "DUCT", "Duct-Old" });
        list.Add("2A", "DUCT", LayerObjectList.Drawing);
        list.Add("4A", "Duct-Old", LayerObjectList.Blocks);
        list.Add("3B", "DUCT", LayerObjectList.Attributes);
        Assert.Equal(3, list.Count);
        Assert.Equal(
            "{\"items\":[[\"2A\",\"DUCT\",\"drawing\"],[\"4A\",\"Duct-Old\",\"blocks\"],[\"3B\",\"DUCT\",\"attributes\"]],\"unsure\":false}",
            Written(list.Write));
    }

    [Theory]
    [InlineData("DUCT", true)]
    [InlineData("duct", true)]      // AutoCAD's layer names: the case does not count
    [InlineData("DUCT-OLD", true)]
    [InlineData("M-DUCT", false)]
    [InlineData("", false)]
    [InlineData(null, false)]
    public void Only_objects_on_an_old_layer_are_sent(string? layer, bool old)
    {
        Assert.Equal(old, new LayerObjectList(new[] { "DUCT", "Duct-Old" }).OnOldLayer(layer));
    }

    [Fact]
    public void An_attribute_whose_definition_defines_none_makes_the_read_unsure()
    {
        var list = new LayerObjectList(new[] { "DUCT" });
        list.MarkUnsure();
        Assert.EndsWith(",\"unsure\":true}", Written(list.Write));
    }

    [Fact]
    public void A_place_that_is_not_one_of_the_three_is_a_bug()
    {
        Assert.Throws<System.ArgumentException>(() => new LayerObjectList(new[] { "DUCT" }).Add("2A", "DUCT", "model"));
    }

    [Fact]
    public void A_read_without_layers_is_refused()
    {
        Assert.Throws<RunRefusal>(() => new LayerObjectList(new string[0]));
        Assert.Throws<RunRefusal>(() => new LayerObjectList(new[] { " ", "" }));
        Assert.Throws<RunRefusal>(() => new LayerObjectList(null));
    }

    [Fact]
    public void One_filter_per_old_layer_up_to_a_hundred()
    {
        using var args = Args(new { filters = new[] { new[] { new object[] { 8, "DUCT" } }, new[] { new object[] { 8, "Duct`-Old" } } } });
        var filters = LayerObjectList.ParseFilters(args.Element("filters"));
        Assert.Equal(2, filters.Count);
        Assert.Equal("Duct`-Old", filters[1][0].Text);
        var many = new object[LayerObjectList.MostLayers];
        for (var i = 0; i < many.Length; i++) many[i] = new[] { new object[] { 8, "L" + i } };
        using var most = Args(new { filters = many });
        Assert.Equal(LayerObjectList.MostLayers, LayerObjectList.ParseFilters(most.Element("filters")).Count);
        using var none = Args(new { filters = new object[0] });
        Assert.Throws<RunRefusal>(() => LayerObjectList.ParseFilters(none.Element("filters")));
    }

    [Fact]
    public void The_merge_is_read_from_its_args()
    {
        using var args = Args(new { layers = new[] { "DUCT", "duct", "Duct-Old" }, into = "M-DUCT", handles = new[] { "2A", "4A" } });
        var plan = LayerMergePlan.Parse(args);
        Assert.Equal(new[] { "DUCT", "Duct-Old" }, plan.Layers); // a name twice, once
        Assert.Equal("M-DUCT", plan.Into);
        Assert.Equal(new[] { "2A", "4A" }, plan.Handles);
        Assert.True(plan.IsOld("duct-old"));
        Assert.False(plan.IsOld("M-DUCT"));
    }

    [Theory]
    [InlineData(new[] { "DUCT" }, "")]
    [InlineData(new string[0], "M-DUCT")]
    [InlineData(new[] { "M-DUCT" }, "m-duct")]
    [InlineData(new[] { "0" }, "M-DUCT")]
    public void A_merge_that_cannot_be_is_refused_before_anything_is_touched(string[] layers, string into)
    {
        using var args = Args(new { layers, into, handles = new string[0] });
        Assert.Throws<RunRefusal>(() => LayerMergePlan.Parse(args));
    }

    [Fact]
    public void What_it_did_goes_back_with_the_old_current_layer_and_the_kept_layers_reasons()
    {
        var plan = new LayerMergePlan(new[] { "DUCT", "Duct-Old" }, "M-DUCT", new[] { "2A", "4A", "3B" });
        plan.MadeCurrent("DUCT");
        plan.Removed("DUCT");
        plan.Kept("Duct-Old", "it is still referenced");
        Assert.Equal(
            "{\"moved\":3,\"current\":\"DUCT\",\"removed\":[\"DUCT\"],\"kept\":[[\"Duct-Old\",\"it is still referenced\"]]}",
            Written(plan.Write));
    }

    [Fact]
    public void A_current_layer_that_was_not_merged_goes_as_null()
    {
        var plan = new LayerMergePlan(new[] { "DUCT" }, "M-DUCT", new string[0]);
        plan.Removed("DUCT");
        Assert.Equal("{\"moved\":0,\"current\":null,\"removed\":[\"DUCT\"],\"kept\":[]}", Written(plan.Write));
    }

    [Fact]
    public void One_object_that_will_not_move_is_said_as_nothing_merged()
    {
        var plan = new LayerMergePlan(new[] { "DUCT" }, "M-DUCT", new[] { "2A" });
        var why = plan.WouldNotMove("2A", "eOnLockedLayer");
        Assert.Contains("Object 2A would not move to M-DUCT (eOnLockedLayer)", why);
        Assert.Contains("nothing was merged", why);
        Assert.Contains("not in the drawing any more", LayerMergePlan.Gone("2A"));
    }

    [Fact]
    public void The_read_is_a_read_and_the_merge_a_change()
    {
        Assert.True(PluginOperations.TryLevel("layer_objects", out var read));
        Assert.Equal(Risk.Read, read);
        Assert.True(PluginOperations.TryLevel("merge_layers", out var change));
        Assert.Equal(Risk.Change, change);
    }

    [Fact]
    public void The_merge_needs_the_changes_padlock()
    {
        const string token = "tok";
        var config = new HeronConfig { WriteEnabled = true };
        var host = new FakeHost { RunAnswer = RunResult.Done(w => w.WriteNumber("moved", 0)) };
        var protocol = new BridgeProtocol(host, () => config, token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();

        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool = "autocad_merge_layers", risk = "change",
            summary = "Merge layers", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        config.WriteEnabled = false; // turned off in the middle: the change is held, not run
        var reply = Send(new
        {
            op = "run", token, conversation = "chat-a", job = "j1", operation = "merge_layers",
            args = new { layers = new[] { "DUCT" }, into = "M-DUCT", handles = new[] { "2A" } },
        });
        Assert.False(reply.GetProperty("ok").GetBoolean(), reply.GetRawText());
        Assert.Empty(host.Runs);
    }

    [Fact]
    public void A_plug_in_without_them_says_so_in_words_the_server_falls_back_on()
    {
        Assert.Contains("does not have the operation 'layer_objects'", Texts.UnknownOperation("layer_objects"));
        Assert.Contains("does not have the operation 'merge_layers'", Texts.UnknownOperation("merge_layers"));
    }
}
