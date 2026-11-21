using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The Saved commands tab of the Heron palette (D-68): the commands the
    /// server keeps on this PC (D-55), searched, and their inputs filled from
    /// what the modeller typed. Running one is the server's job, through the
    /// same gate as a chat; this only reads the files and builds the request.
    /// No AutoCAD here, so it is tested offline.
    /// </summary>
    public static class SavedCommandList
    {
        /// <summary>Where the server saves them: %LOCALAPPDATA%\Heron\autocad\commands (saved_commands.py).</summary>
        public static string DefaultFolder =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Heron", "autocad", "commands");

        /// <summary>Every readable command in the folder, by name. A file that cannot be read is left out.</summary>
        public static List<SavedCommand> Load(string folder)
        {
            var found = new List<SavedCommand>();
            if (!Directory.Exists(folder)) return found;
            foreach (var path in Directory.GetFiles(folder, "*.json"))
            {
                try
                {
                    var command = Parse(File.ReadAllText(path, Encoding.UTF8));
                    if (command != null) found.Add(command);
                }
                catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
                {
                    // Being written right now, most likely: the next refresh reads it.
                }
            }
            return found.OrderBy(c => c.Name, StringComparer.OrdinalIgnoreCase).ToList();
        }

        /// <summary>One command from its file's text, or null when it is not one.</summary>
        public static SavedCommand? Parse(string json)
        {
            JsonDocument doc;
            try
            {
                doc = JsonDocument.Parse(json);
            }
            catch (JsonException)
            {
                return null;
            }
            using (doc)
            {
                var root = doc.RootElement;
                if (root.ValueKind != JsonValueKind.Object) return null;
                var name = Text(root, "name").Trim();
                if (name.Length == 0) return null;
                var command = new SavedCommand { Name = name, Description = Text(root, "description").Trim() };
                if (root.TryGetProperty("steps", out var steps) && steps.ValueKind == JsonValueKind.Array) command.Steps = steps.GetArrayLength();
                if (root.TryGetProperty("inputs", out var inputs) && inputs.ValueKind == JsonValueKind.Object)
                {
                    foreach (var item in inputs.EnumerateObject())
                    {
                        var input = new SavedInput { Name = item.Name };
                        if (item.Value.ValueKind == JsonValueKind.Object)
                        {
                            input.Description = Text(item.Value, "description");
                            if (item.Value.TryGetProperty("default", out var given))
                            {
                                input.HasDefault = true;
                                input.Default = given.GetRawText();
                            }
                            if (item.Value.TryGetProperty("example", out var example)) input.Example = example.GetRawText();
                        }
                        command.Inputs.Add(input);
                    }
                }
                return command;
            }
        }

        /// <summary>The commands whose name, description or inputs hold every word typed.</summary>
        public static List<SavedCommand> Search(IEnumerable<SavedCommand> commands, string? query)
        {
            var words = (query ?? "").Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            return commands.Where(c =>
            {
                var haystack = (c.Name + " " + c.Description + " " + string.Join(" ", c.Inputs.Select(i => i.Name + " " + i.Description))).ToLowerInvariant();
                return words.All(w => haystack.Contains(w.ToLowerInvariant()));
            }).ToList();
        }

        /// <summary>
        /// The inputs as the server takes them, from what was typed. Each value
        /// takes its example's type (or its default's): a number stays a number,
        /// so "1200" is sent as 1200 and a layer "100" as text. A blank box
        /// with a default is left out, so the server uses the default.
        /// </summary>
        public static FillResult Fill(SavedCommand command, IDictionary<string, string> typed)
        {
            using (var stream = new MemoryStream())
            {
                using (var w = new Utf8JsonWriter(stream))
                {
                    w.WriteStartObject();
                    foreach (var input in command.Inputs)
                    {
                        typed.TryGetValue(input.Name, out var raw);
                        var text = (raw ?? "").Trim();
                        if (text.Length == 0)
                        {
                            if (input.HasDefault) continue;
                            return FillResult.No(PaletteTexts.NeedsValue(input.Name, input.Description));
                        }
                        w.WritePropertyName(input.Name);
                        var problem = WriteValue(w, input, text);
                        if (problem != null) return FillResult.No(problem);
                    }
                    w.WriteEndObject();
                }
                return new FillResult { Ok = true, Json = Encoding.UTF8.GetString(stream.ToArray()) };
            }
        }

        private static string? WriteValue(Utf8JsonWriter w, SavedInput input, string text)
        {
            switch (input.Kind)
            {
                case JsonValueKind.Number:
                    if (!double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out var number) || double.IsNaN(number) || double.IsInfinity(number))
                        return PaletteTexts.NeedsNumber(input.Name, input.Example ?? input.Default ?? "");
                    if (long.TryParse(text, NumberStyles.Integer, CultureInfo.InvariantCulture, out var whole)) w.WriteNumberValue(whole);
                    else w.WriteNumberValue(number);
                    return null;
                case JsonValueKind.True:
                case JsonValueKind.False:
                    var yes = text.ToLowerInvariant();
                    if (yes == "true" || yes == "yes" || yes == "y" || yes == "1") w.WriteBooleanValue(true);
                    else if (yes == "false" || yes == "no" || yes == "n" || yes == "0") w.WriteBooleanValue(false);
                    else return PaletteTexts.NeedsYesNo(input.Name);
                    return null;
                case JsonValueKind.Array:
                case JsonValueKind.Object:
                    try
                    {
                        using (var given = JsonDocument.Parse(text))
                        {
                            if (given.RootElement.ValueKind != input.Kind) return PaletteTexts.NeedsList(input.Name, input.Example ?? input.Default ?? "");
                            given.RootElement.WriteTo(w);
                        }
                    }
                    catch (JsonException)
                    {
                        return PaletteTexts.NeedsList(input.Name, input.Example ?? input.Default ?? "");
                    }
                    return null;
                default:
                    w.WriteStringValue(text);
                    return null;
            }
        }

        /// <summary>The request file the server's runner reads: {"name", "inputs"}.</summary>
        public static string RunRequest(SavedCommand command, string inputsJson)
        {
            using (var inputs = JsonDocument.Parse(inputsJson))
            using (var stream = new MemoryStream())
            {
                using (var w = new Utf8JsonWriter(stream))
                {
                    w.WriteStartObject();
                    w.WriteString("name", command.Name);
                    w.WritePropertyName("inputs");
                    inputs.RootElement.WriteTo(w);
                    w.WriteEndObject();
                }
                return Encoding.UTF8.GetString(stream.ToArray());
            }
        }

        private static string Text(JsonElement root, string name) =>
            root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() ?? "" : "";
    }

    public sealed class SavedCommand
    {
        public string Name { get; set; } = "";
        public string Description { get; set; } = "";
        public int Steps { get; set; }
        public List<SavedInput> Inputs { get; } = new List<SavedInput>();
    }

    public sealed class SavedInput
    {
        public string Name { get; set; } = "";
        public string Description { get; set; } = "";
        public bool HasDefault { get; set; }
        /// <summary>The default as JSON text (a string keeps its quotes), or null.</summary>
        public string? Default { get; set; }
        /// <summary>The example as JSON text, or null.</summary>
        public string? Example { get; set; }

        /// <summary>The type a typed value must have: the example's, else the default's, else text.</summary>
        public JsonValueKind Kind
        {
            get
            {
                var sample = Example ?? Default;
                if (sample == null) return JsonValueKind.String;
                try
                {
                    using (var doc = JsonDocument.Parse(sample)) return doc.RootElement.ValueKind;
                }
                catch (JsonException)
                {
                    return JsonValueKind.String;
                }
            }
        }

        /// <summary>What goes in the box at first: the default, as the modeller would type it.</summary>
        public string StartText => HasDefault ? Plain(Default) : "";

        /// <summary>The grey hint beside the box: "e.g. 1200".</summary>
        public string Hint => Example == null ? "" : "e.g. " + Plain(Example);

        private static string Plain(string? json)
        {
            if (json == null) return "";
            try
            {
                using (var doc = JsonDocument.Parse(json))
                    return doc.RootElement.ValueKind == JsonValueKind.String ? doc.RootElement.GetString() ?? "" : doc.RootElement.GetRawText();
            }
            catch (JsonException)
            {
                return json;
            }
        }
    }

    public sealed class FillResult
    {
        public bool Ok { get; set; }
        public string Message { get; set; } = "";
        /// <summary>The inputs as a JSON object, when Ok.</summary>
        public string Json { get; set; } = "{}";

        public static FillResult No(string message) => new FillResult { Ok = false, Message = message };
    }
}
