using System;
using System.IO;
using System.Text;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The switches the bridge obeys for one call. The padlocks, Ask to Keep and
    /// the erase question come from this AutoCAD's memory (HeronPadlocks, D-59); only connect at
    /// start and the banner come from %APPDATA%\Heron\autocad\heron-autocad.config.
    /// </summary>
    public sealed class HeronConfig
    {
        public bool WriteEnabled { get; set; }
        public bool PublishEnabled { get; set; }
        public bool AdminEnabled { get; set; }
        public bool AskBeforeKeeping { get; set; }
        /// <summary>
        /// The erase question (D-50): ask before keeping what a job erased.
        /// On unless the modeller turned it off in Settings in this AutoCAD.
        /// </summary>
        public bool AskBeforeErasing { get; set; } = true;
        public bool ActivityBanner { get; set; } = true;

        /// <summary>The padlocks a Windows policy holds off (D-60), so a refusal can say so.</summary>
        public PolicyHolds Held { get; set; } = PolicyHolds.None;

        public static string DefaultPath =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Heron", "autocad", "heron-autocad.config");

        /// <summary>
        /// The file's own setting: ui.activityBanner. bridge.autoConnect is
        /// ignored, so no file can make AutoCAD connect at start (D-73).
        /// The padlock lines an older plug-in wrote (write.enabled,
        /// publish.enabled, admin.enabled, write.askBeforeKeeping) are ignored,
        /// so a file can never turn a padlock on (D-59). A file that cannot be
        /// read cleanly gives the default: banner on.
        /// </summary>
        public static HeronConfig Load(string path)
        {
            string text;
            try
            {
                if (!File.Exists(path)) return new HeronConfig();
                text = File.ReadAllText(path, Encoding.UTF8);
            }
            catch (Exception) { return new HeronConfig(); }

            try
            {
                using (var doc = JsonDocument.Parse(text))
                {
                    if (doc.RootElement.ValueKind != JsonValueKind.Object) return new HeronConfig();
                    var read = new HeronConfig();
                    foreach (var property in doc.RootElement.EnumerateObject())
                    {
                        var kind = property.Value.ValueKind;
                        if (kind != JsonValueKind.True && kind != JsonValueKind.False) return new HeronConfig();
                        var on = kind == JsonValueKind.True;
                        switch (property.Name)
                        {
                            case "ui.activityBanner": read.ActivityBanner = on; break;
                        }
                    }
                    return read;
                }
            }
            catch (JsonException) { return new HeronConfig(); }
        }
    }

    internal static class AtomicFile
    {
        /// <summary>Write beside the target, then swap, so a reader never sees half a file.</summary>
        public static void Write(string path, string content)
        {
            var folder = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(folder)) Directory.CreateDirectory(folder);
            var temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            File.WriteAllText(temp, content, new UTF8Encoding(false));
            if (File.Exists(path)) File.Replace(temp, path, null);
            else File.Move(temp, path);
        }
    }
}
