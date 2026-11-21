using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The choices behind a multi-sheet PDF (PublishPdf in the add-in): where it
    /// goes, which sheets, and the two PUBLISH settings a DSD file needs. Pure,
    /// so it is tested offline.
    /// </summary>
    public static class PublishPlan
    {
        public sealed class Sheet
        {
            public Sheet(string name, int order, bool model)
            {
                Name = name;
                Order = order;
                Model = model;
            }

            public string Name { get; }
            public int Order { get; }
            public bool Model { get; }
        }

        /// <summary>Null when the PDF can be written at <paramref name="target"/>, or why not.</summary>
        public static string? CheckTarget(string target, bool overwrite, Func<string, bool> fileExists, Func<string, bool> folderExists)
        {
            if (string.IsNullOrWhiteSpace(target)) return "Give the PDF's full path, e.g. D:\\Issue\\A-100 set.pdf.";
            if (!Path.IsPathRooted(target)) return "'" + target + "' is not a full path. Give the drive and folder too.";
            if (!target.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase)) return "'" + target + "' does not end in .pdf.";
            var folder = Path.GetDirectoryName(target) ?? "";
            if (!folderExists(folder)) return "The folder '" + folder + "' does not exist.";
            if (!overwrite && fileExists(target)) return "'" + target + "' is already there. Give another name, or overwrite=true to replace it.";
            return null;
        }

        /// <summary>
        /// The sheets to publish, in tab order. Named ones must all be there
        /// (names are matched without regard to case); none named means every
        /// paper layout, plus Model when asked.
        /// </summary>
        public static List<string> Choose(IEnumerable<Sheet> layouts, string[] wanted, bool includeModel, out string? refusal)
        {
            refusal = null;
            var ordered = layouts.OrderBy(s => s.Model ? -1 : s.Order).ToList();
            var chosen = new List<string>();
            if (wanted.Length == 0)
            {
                chosen.AddRange(ordered.Where(s => !s.Model || includeModel).Select(s => s.Name));
            }
            else
            {
                var missing = new List<string>();
                var picked = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var name in wanted.Select(n => (n ?? "").Trim()).Where(n => n.Length > 0))
                {
                    if (ordered.Any(s => string.Equals(s.Name, name, StringComparison.OrdinalIgnoreCase))) picked.Add(name);
                    else missing.Add(name);
                }
                if (missing.Count > 0)
                {
                    refusal = "This drawing has no layout called " + string.Join(", ", missing.Select(m => "'" + m + "'"))
                        + ". It has: " + string.Join(", ", ordered.Select(s => s.Name)) + ".";
                    return chosen;
                }
                chosen.AddRange(ordered.Where(s => picked.Contains(s.Name)).Select(s => s.Name));
            }
            if (chosen.Count == 0)
                refusal = "This drawing has no paper layouts to publish. Name 'Model', or set include_model=true.";
            return chosen;
        }

        /// <summary>One drawing of a multi-drawing PDF (#67, D-91): what the plug-in found in it.</summary>
        public sealed class Drawing
        {
            public Drawing(string path, IEnumerable<Sheet> sheets, bool unsaved = false, IEnumerable<string>? missingXrefs = null, string? unreadable = null)
            {
                Path = path;
                Sheets = sheets.ToList();
                Unsaved = unsaved;
                MissingXrefs = (missingXrefs ?? Enumerable.Empty<string>()).ToList();
                Unreadable = unreadable;
            }

            public string Path { get; }
            public List<Sheet> Sheets { get; }
            /// <summary>Open in AutoCAD with changes not saved: the PDF would be made from an older file.</summary>
            public bool Unsaved { get; }
            /// <summary>Xrefs it attaches (loaded) whose file cannot be found: their sheets would print without them.</summary>
            public List<string> MissingXrefs { get; }
            /// <summary>Why the file could not be read, or null.</summary>
            public string? Unreadable { get; }
        }

        /// <summary>One page of the PDF: a layout of a drawing.</summary>
        public sealed class Entry
        {
            public Entry(string path, string layout)
            {
                Path = path;
                Layout = layout;
            }

            public string Path { get; }
            public string Layout { get; }
        }

        /// <summary>
        /// The pages of a PDF made from several drawings, drawing by drawing and each in
        /// tab order. Every drawing must be readable, saved and have its xrefs: all that
        /// is wrong is said at once, so the set is fixed in one go. Named layouts are kept
        /// from every drawing that has them, and each name must be in at least one; none
        /// named means every paper layout of every drawing, plus Model when asked.
        /// </summary>
        public static List<Entry> ChooseAcross(IEnumerable<Drawing> drawings, string[] wanted, bool includeModel, out string? refusal)
        {
            refusal = null;
            var entries = new List<Entry>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var list = drawings.Where(d => seen.Add(d.Path ?? "")).ToList();
            if (list.Count == 0)
            {
                refusal = "No drawings to publish. Give drawing paths, or a folder that has .dwg files.";
                return entries;
            }

            var problems = new List<string>();
            foreach (var d in list.Where(d => d.Unreadable != null))
                problems.Add("'" + d.Path + "' could not be read (" + d.Unreadable + ").");
            foreach (var d in list.Where(d => d.Unreadable == null && d.Unsaved))
                problems.Add("'" + d.Path + "' is open in AutoCAD with unsaved changes; save it first (the PDF is made from the saved file).");
            foreach (var d in list.Where(d => d.Unreadable == null && d.MissingXrefs.Count > 0))
                problems.Add("'" + d.Path + "' attaches " + string.Join(", ", d.MissingXrefs.Select(x => "'" + x + "'"))
                    + ", which cannot be found, so its sheets would print without them. Repath or reload them (autocad_manage_xref), or unload the ones not wanted.");

            var names = (wanted ?? new string[0]).Select(n => (n ?? "").Trim()).Where(n => n.Length > 0).ToList();
            var picked = new HashSet<string>(names, StringComparer.OrdinalIgnoreCase);
            if (names.Count > 0)
            {
                var missing = names.Where(n => !list.Any(d => d.Sheets.Any(s => string.Equals(s.Name, n, StringComparison.OrdinalIgnoreCase)))).ToList();
                if (missing.Count > 0)
                    problems.Add("None of the drawings has a layout called " + string.Join(", ", missing.Select(m => "'" + m + "'")) + ".");
            }
            if (problems.Count > 0)
            {
                refusal = string.Join(" ", problems);
                return entries;
            }

            foreach (var d in list)
            {
                var ordered = d.Sheets.OrderBy(s => s.Model ? -1 : s.Order);
                foreach (var sheet in ordered)
                {
                    var take = names.Count > 0 ? picked.Contains(sheet.Name) : !sheet.Model || includeModel;
                    if (take) entries.Add(new Entry(d.Path ?? "", sheet.Name));
                }
            }
            if (entries.Count == 0)
                refusal = "Those drawings have no paper layouts to publish. Name 'Model', or set include_model=true.";
            return entries;
        }

        /// <summary>
        /// True when an xref's saved path leads to a file: the path itself when it is a
        /// full one, else from the host drawing's folder, and the file's own name in the
        /// host's folder either way (AutoCAD looks there too). The add-in asks AutoCAD's
        /// own search (support paths, project paths) for one this does not find.
        /// </summary>
        public static bool XrefFound(string? savedPath, string hostFolder, Func<string, bool> fileExists) =>
            XrefPath(savedPath, hostFolder, fileExists) != null;

        /// <summary>The file an xref's saved path leads to, by the rule of <see cref="XrefFound"/>, or null.</summary>
        public static string? XrefPath(string? savedPath, string hostFolder, Func<string, bool> fileExists)
        {
            var saved = (savedPath ?? "").Trim();
            if (saved.Length == 0) return null;
            var candidates = new List<string>();
            try
            {
                candidates.Add(Path.IsPathRooted(saved) ? saved : Path.GetFullPath(Path.Combine(hostFolder ?? "", saved)));
            }
            catch (Exception ex) when (ex is ArgumentException || ex is NotSupportedException || ex is PathTooLongException)
            {
                // A path Windows cannot even spell is not found; the name alone may still be.
            }
            var name = Path.GetFileName(saved.Replace('\\', Path.DirectorySeparatorChar).Replace('/', Path.DirectorySeparatorChar));
            if (name.Length > 0 && !string.IsNullOrEmpty(hostFolder)) candidates.Add(Path.Combine(hostFolder, name));
            return candidates.FirstOrDefault(fileExists);
        }

        /// <summary>
        /// Page titles for the publisher, one per page and never the same twice: a
        /// drawing's name and the layout's, with a number added when two drawings of
        /// the same name (in different folders) have a layout of the same name.
        /// </summary>
        public static List<string> Titles(IEnumerable<Entry> entries)
        {
            var titles = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var entry in entries)
            {
                var stem = Path.GetFileNameWithoutExtension((entry.Path ?? "").Replace('\\', Path.DirectorySeparatorChar).Replace('/', Path.DirectorySeparatorChar));
                var title = stem + "-" + entry.Layout;
                var unique = title;
                for (var n = 2; !seen.Add(unique); n++) unique = title + " (" + n + ")";
                titles.Add(unique);
            }
            return titles;
        }

        /// <summary>
        /// A DSD file's text with PUBLISH's file box switched off and never-opened
        /// layouts set up before they are plotted (otherwise they print blank).
        /// </summary>
        public static string Quiet(string dsd)
        {
            var text = Regex.Replace(dsd ?? "", "PromptForDwfName\\s*=\\s*TRUE", "PromptForDwfName=FALSE", RegexOptions.IgnoreCase);
            if (Regex.IsMatch(text, "^\\s*InitLayouts\\s*=", RegexOptions.IgnoreCase | RegexOptions.Multiline))
                return Regex.Replace(text, "^(\\s*InitLayouts\\s*=\\s*).*$", "${1}TRUE", RegexOptions.IgnoreCase | RegexOptions.Multiline);
            if (Regex.IsMatch(text, "^\\[PublishOptions\\]\\s*$", RegexOptions.Multiline))
                return Regex.Replace(text, "^\\[PublishOptions\\]\\s*$", "[PublishOptions]\r\nInitLayouts=TRUE", RegexOptions.Multiline);
            return text.TrimEnd() + "\r\n[PublishOptions]\r\nInitLayouts=TRUE\r\n";
        }
    }
}
