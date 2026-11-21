using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// How the palette's Run reaches Heron's server (D-68). The server lives
    /// with the chat, so the palette starts its own copy for one run:
    /// <c>python -m autocad_mcp --run-saved request.json --acad-pid N</c>. That
    /// copy is a chat of its own to the plug-in: the same gate, hold,
    /// padlocks, Keep or Discard and HERONSTOP as any chat, never round them.
    /// Every server writes where it runs from to server.json when it starts,
    /// which is how the palette finds it. No AutoCAD here.
    /// </summary>
    public static class PaletteServer
    {
        /// <summary>%LOCALAPPDATA%\Heron\autocad\server.json (core/palette.py writes it).</summary>
        public static string DefaultPath =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Heron", "autocad", "server.json");

        /// <summary>The folder the run requests are written to, and deleted from after.</summary>
        public static string RequestFolder =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Heron", "autocad", "palette");

        /// <summary>The Python that last ran Heron's server, or null with why not.</summary>
        public static string? FindPython(string serverFile, Func<string, bool> exists, out string problem)
        {
            problem = "";
            string text;
            try
            {
                text = File.ReadAllText(serverFile, Encoding.UTF8);
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
            {
                problem = PaletteTexts.NoServer;
                return null;
            }
            try
            {
                using (var doc = JsonDocument.Parse(text))
                {
                    var root = doc.RootElement;
                    var python = root.ValueKind == JsonValueKind.Object && root.TryGetProperty("python", out var p) && p.ValueKind == JsonValueKind.String
                        ? p.GetString() ?? ""
                        : "";
                    if (python.Length == 0)
                    {
                        problem = PaletteTexts.NoServer;
                        return null;
                    }
                    if (!exists(python))
                    {
                        problem = PaletteTexts.ServerGone;
                        return null;
                    }
                    return python;
                }
            }
            catch (JsonException)
            {
                problem = PaletteTexts.NoServer;
                return null;
            }
        }

        /// <summary>The runner's arguments, quoted as Windows reads them.</summary>
        public static string Arguments(string requestFile, int acadPid) =>
            Join(new[] { "-m", "autocad_mcp", "--run-saved", requestFile, "--acad-pid", acadPid.ToString() });

        /// <summary>Windows command-line quoting (CommandLineToArgvW rules).</summary>
        public static string Join(IEnumerable<string> args) => string.Join(" ", args.Select(Quote));

        public static string Quote(string arg)
        {
            if (arg.Length > 0 && arg.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return arg;
            var b = new StringBuilder("\"");
            var slashes = 0;
            foreach (var c in arg)
            {
                if (c == '\\')
                {
                    slashes++;
                    continue;
                }
                if (c == '"')
                {
                    b.Append('\\', slashes * 2 + 1);
                    b.Append('"');
                }
                else
                {
                    b.Append('\\', slashes);
                    b.Append(c);
                }
                slashes = 0;
            }
            b.Append('\\', slashes * 2);
            b.Append('"');
            return b.ToString();
        }

        /// <summary>
        /// What the runner printed: its last line is {"ok", "message"}. Anything
        /// else is "no answer", with the end of what it wrote to stderr.
        /// </summary>
        public static RunReply Reply(string stdout, string stderr, int exitCode)
        {
            var lines = (stdout ?? "").Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0).Reverse();
            foreach (var line in lines)
            {
                if (!line.StartsWith("{")) continue;
                try
                {
                    using (var doc = JsonDocument.Parse(line))
                    {
                        var root = doc.RootElement;
                        if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("ok", out var ok)) continue;
                        var message = root.TryGetProperty("message", out var m) && m.ValueKind == JsonValueKind.String ? m.GetString() ?? "" : "";
                        return new RunReply { Ok = ok.ValueKind == JsonValueKind.True, Message = message.Length > 0 ? message : PaletteTexts.NoReply };
                    }
                }
                catch (JsonException)
                {
                }
            }
            var tail = (stderr ?? "").Trim();
            if (tail.Length > 300) tail = "..." + tail.Substring(tail.Length - 300);
            return new RunReply
            {
                Ok = false,
                Message = PaletteTexts.NoReply + " (exit " + exitCode + (tail.Length > 0 ? ": " + tail : "") + ")",
            };
        }
    }

    public sealed class RunReply
    {
        public bool Ok { get; set; }
        public string Message { get; set; } = "";
    }
}
