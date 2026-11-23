using System.IO;
using System.Text;
using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// The attribute cells the plug-in writes in one transaction (#200, D-148):
/// what it reads from the server, its words for each refusal, and what it
/// answers. tests/test_plugin_attribute_writes.py holds the server side to this.
/// </summary>
public class AttributeWritesTests
{
    private static JsonElement Json(object value) => JsonDocument.Parse(JsonSerializer.Serialize(value)).RootElement.Clone();

    [Fact]
    public void The_planned_cells_are_read_in_order()
    {
        var plan = AttributeWritePlan.Parse(Json(new[] { new[] { "3A", "REV", "B" }, new[] { "2A", "TAG", "" } }));
        Assert.Equal(2, plan.Changes.Count);
        Assert.Equal(("3A", "REV", "B"), (plan.Changes[0].Handle, plan.Changes[0].Tag, plan.Changes[0].Text));
        Assert.Equal("", plan.Changes[1].Text); // an empty value is a value: the cell is cleared
    }

    [Theory]
    [InlineData("[]")]
    [InlineData("[[\"3A\",\"REV\"]]")]
    [InlineData("[[\"3A\",\"REV\",5]]")]
    [InlineData("[[\" \",\"REV\",\"B\"]]")]
    [InlineData("[[\"3A\",\"\",\"B\"]]")]
    [InlineData("{}")]
    public void A_change_of_the_wrong_shape_is_refused_before_anything_is_written(string changes)
    {
        Assert.Throws<RunRefusal>(() => AttributeWritePlan.Parse(JsonDocument.Parse(changes).RootElement));
    }

    [Fact]
    public void Too_many_cells_are_handed_back_to_COM()
    {
        var many = new List<AttributeChange>();
        for (var i = 0; i <= AttributeWritePlan.MostChanges; i++) many.Add(new AttributeChange("2A", "T", "v"));
        var refusal = Assert.Throws<RunRefusal>(() => new AttributeWritePlan(many));
        Assert.Contains(AttributeWritePlan.UseCom, refusal.Message);
    }

    [Theory]
    [InlineData("REV", "REV", true)]
    [InlineData("rev", "REV", false)] // as the server's COM loop: str(att.TagString) == tag
    [InlineData(null, "REV", false)]
    public void A_tag_matches_exactly(string? found, string wanted, bool same)
    {
        Assert.Equal(same, AttributeWritePlan.SameTag(found, wanted));
    }

    [Fact]
    public void Each_refusal_says_nothing_was_written_or_hands_the_cells_to_COM()
    {
        Assert.Contains("nothing was written", AttributeWritePlan.Gone("3A"));
        Assert.Contains("no longer has the tag REV", AttributeWritePlan.NoTag("3A", "REV"));
        Assert.Contains("would not take REV (eOnLockedLayer)", AttributeWritePlan.WouldNotTake("3A", "REV", "eOnLockedLayer"));
        Assert.EndsWith(AttributeWritePlan.UseCom, AttributeWritePlan.NotSure("3A", "REV", "a field"));
        Assert.DoesNotContain(AttributeWritePlan.UseCom, AttributeWritePlan.WouldNotTake("3A", "REV", "x"));
    }

    [Fact]
    public void The_answer_counts_the_cells_and_the_attributes_set()
    {
        var plan = new AttributeWritePlan(new[] { new AttributeChange("2D", "TAG", "V-9") });
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            writer.WriteStartObject();
            plan.Write(writer, 2); // the tag twice on one block
            writer.WriteEndObject();
        }
        Assert.Equal("{\"written\":1,\"attributes\":2}", Encoding.UTF8.GetString(stream.ToArray()));
    }

    [Fact]
    public void It_is_a_change_the_changes_padlock_holds()
    {
        Assert.True(PluginOperations.TryLevel("write_attributes", out var level));
        Assert.Equal(Risk.Change, level);
        const string token = "tok";
        var config = new HeronConfig { WriteEnabled = true };
        var host = new FakeHost { RunAnswer = RunResult.Done(w => w.WriteNumber("written", 1)) };
        var protocol = new BridgeProtocol(host, () => config, token, new HeronHold(), () => DateTime.UtcNow);
        JsonElement Send(object request) => JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(request))).RootElement.Clone();
        Assert.True(Send(new
        {
            op = "begin", token, conversation = "chat-a", job = "j1", tool = "autocad_set_attributes", risk = "change",
            summary = "Attributes", drawing = @"C:\Project\M-201.dwg",
        }).GetProperty("ok").GetBoolean());
        var args = new { changes = new[] { new[] { "3A", "REV", "B" } } };
        var reply = Send(new { op = "run", token, conversation = "chat-a", job = "j1", operation = "write_attributes", args });
        Assert.True(reply.GetProperty("ok").GetBoolean(), reply.GetRawText());
        Assert.Single(host.Runs);
        config.WriteEnabled = false;
        reply = Send(new { op = "run", token, conversation = "chat-a", job = "j1", operation = "write_attributes", args });
        Assert.False(reply.GetProperty("ok").GetBoolean());
        Assert.Single(host.Runs); // held by the padlock: never run
    }

    [Fact]
    public void A_plug_in_without_it_says_so_in_words_the_server_falls_back_on()
    {
        Assert.Contains("does not have the operation 'write_attributes'", Texts.UnknownOperation("write_attributes"));
    }
}
