using System;
using System.Collections.Generic;
using System.IO;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// eTransmit's packed copy points at the files beside it (#160, D-149).
    ///
    /// The server copies each drawing it packs into a folder of its own
    /// (<see cref="StagingPrefix"/>...) and the plug-in opens that copy as a
    /// side database, never as a drawing on screen, and sets each xref, image
    /// and underlay path saved in it to the bare file name, when that file is
    /// in the pack. The rules are here so they are tested offline; the add-in
    /// only reads and writes the paths.
    /// </summary>
    public static class PackPaths
    {
        /// <summary>The start of the name of the folder the server packs its copies in.</summary>
        public const string StagingPrefix = "heron-etransmit-";

        /// <summary>The file name at the end of a saved path, whichever slash it uses; "" for none.</summary>
        public static string BareName(string? saved)
        {
            var text = (saved ?? "").Trim().Trim('"').Trim();
            var cut = Math.Max(text.LastIndexOf('\\'), text.LastIndexOf('/'));
            return cut >= 0 ? text.Substring(cut + 1) : text;
        }

        /// <summary>
        /// What a saved path becomes: the bare name when that one file is in
        /// the pack; else null, with the reason the path is kept. Already a
        /// bare name: null with <see cref="PathChoice.Already"/> set.
        /// </summary>
        public static PathChoice Decide(string? saved, ICollection<string> inPack, ICollection<string> clashing)
        {
            var bare = BareName(saved);
            if (bare.Length == 0) return PathChoice.Keep("it has no saved path");
            if (Has(clashing, bare))
                return PathChoice.Keep("two different files called " + bare + " were found; only one is in the pack, so the saved path is kept");
            if (!Has(inPack, bare)) return PathChoice.Keep(bare + " is not in the pack (it was missing when packed)");
            if (string.Equals((saved ?? "").Trim().Trim('"').Trim(), bare, StringComparison.OrdinalIgnoreCase))
                return new PathChoice(null, "already the bare file name", true);
            return new PathChoice(bare, "", false);
        }

        /// <summary>
        /// Why the plug-in will not rewrite this file, or null: it must be a
        /// .dwg in a folder the server made for the pack, and not a drawing
        /// open in AutoCAD (the modeller's drawing is never opened this way).
        /// </summary>
        public static string? Refusal(string? file, IEnumerable<string> openDrawings)
        {
            var path = (file ?? "").Trim();
            if (path.Length == 0 || !Path.IsPathRooted(path)) return "Give the packed copy's whole path.";
            if (!path.EndsWith(".dwg", StringComparison.OrdinalIgnoreCase)) return "Only a packed .dwg copy has its paths rewritten.";
            var folder = Path.GetFileName(Path.GetDirectoryName(path) ?? "") ?? "";
            if (!folder.StartsWith(StagingPrefix, StringComparison.OrdinalIgnoreCase))
                return "Heron only rewrites the paths in a copy it made for a pack (in a '" + StagingPrefix + "...' folder), never another drawing.";
            var full = Normal(path);
            foreach (var open in openDrawings)
                if (!string.IsNullOrEmpty(open) && string.Equals(Normal(open), full, StringComparison.OrdinalIgnoreCase))
                    return "That file is open in AutoCAD; Heron never rewrites an open drawing.";
            return null;
        }

        private static string Normal(string path)
        {
            try
            {
                return Path.GetFullPath(path.Trim());
            }
            catch (Exception)
            {
                return path.Trim();
            }
        }

        private static bool Has(ICollection<string> names, string bare)
        {
            foreach (var name in names)
                if (string.Equals(BareName(name), bare, StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }
    }

    /// <summary>A saved path's new value (null: keep it) and why it is kept.</summary>
    public sealed class PathChoice
    {
        public PathChoice(string? newPath, string why, bool already)
        {
            NewPath = newPath;
            Why = why;
            Already = already;
        }

        public string? NewPath { get; }
        public string Why { get; }
        public bool Already { get; }

        public static PathChoice Keep(string why) => new PathChoice(null, why, false);
    }
}
