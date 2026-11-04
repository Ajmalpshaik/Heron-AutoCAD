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
