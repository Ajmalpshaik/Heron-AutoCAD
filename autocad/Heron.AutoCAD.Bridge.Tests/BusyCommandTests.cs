using System.Text.Json;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Bridge.Tests;

/// <summary>
/// Ping says which command the active drawing is in, from the add-in's command
/// tracker, so a busy answer from the server can name it (#47). It answers on
/// the pipe thread and never waits for AutoCAD.
/// </summary>
public class BusyCommandTests
{
    private const string Token = "tok";

    private static JsonElement Ping(BridgeProtocol protocol) =>
        JsonDocument.Parse(protocol.Handle(JsonSerializer.Serialize(new { op = "ping", token = Token, conversation = "c" }))).RootElement;

    private static BridgeProtocol Protocol(Func<string?>? current) =>
        new BridgeProtocol(new FakeHost(), () => new HeronConfig(), Token, new HeronHold(), () => DateTime.UtcNow)
        {
            CurrentCommand = current,
        };

    [Fact]
    public void Ping_names_the_command_the_tracker_follows()
    {
        var tracker = new CommandTracker();
        var protocol = Protocol(() => tracker.Current);
        tracker.Started("_.HATCH");
        Assert.Equal("HATCH", Ping(protocol).GetProperty("command").GetString());
        tracker.Ended("HATCH");
        Assert.Equal(JsonValueKind.Null, Ping(protocol).GetProperty("command").ValueKind);
    }

    [Fact]
    public void Without_a_tracker_ping_leaves_it_out_as_an_older_plugin_does()
    {
        Assert.False(Ping(Protocol(null)).TryGetProperty("command", out _));
    }

    [Fact]
    public void A_tracker_that_throws_never_stops_the_ping()
    {
        var reply = Ping(Protocol(() => throw new InvalidOperationException("gone")));
        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.Equal(JsonValueKind.Null, reply.GetProperty("command").ValueKind);
    }

    [Fact]
    public void A_blank_command_is_no_command()
    {
        Assert.Equal(JsonValueKind.Null, Ping(Protocol(() => "  ")).GetProperty("command").ValueKind);
    }
}
