using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// What a multileader style or a table style made by the plug-in holds
    /// (D-104): the words the chat may use and the numbers they come down to.
    /// Pure, so it is tested offline; the add-in only copies a plan onto
    /// AutoCAD's own objects. Every refusal is thrown before AutoCAD is touched.
    /// </summary>
    public static class StylePlans
    {
        /// <summary>
        /// AutoCAD's own arrowheads, by the block name DIMBLK takes. Closed filled
        /// is AutoCAD's default and has no block, so its name is empty.
        /// </summary>
        public static readonly IReadOnlyDictionary<string, string> Arrows = new Dictionary<string, string>
        {
            ["closed_filled"] = "",
            ["closed_blank"] = "_CLOSEDBLANK",
            ["closed"] = "_CLOSED",
            ["dot"] = "_DOT",
            ["architectural_tick"] = "_ARCHTICK",
            ["oblique"] = "_OBLIQUE",
            ["open"] = "_OPEN",
            ["origin_indicator"] = "_ORIGIN",
            ["origin_indicator_2"] = "_ORIGIN2",
            ["right_angle"] = "_OPEN90",
            ["open_30"] = "_OPEN30",
            ["dot_small"] = "_DOTSMALL",
            ["dot_blank"] = "_DOTBLANK",
            ["dot_small_blank"] = "_SMALL",
            ["box"] = "_BOXBLANK",
            ["box_filled"] = "_BOXFILLED",
            ["datum_triangle"] = "_DATUMBLANK",
            ["datum_triangle_filled"] = "_DATUMFILLED",
            ["integral"] = "_INTEGRAL",
            ["none"] = "_NONE",
        };

        /// <summary>
        /// Where a multileader's text sits against the end of its leader, as
        /// AutoCAD's TextAttachmentType numbers it (checked in the 2021 and 2027
        /// reference assemblies). The words follow the Multileader Style
        /// dialog's list, left and right attachment alike.
        /// </summary>
        public static readonly IReadOnlyDictionary<string, int> Attachments = new Dictionary<string, int>
        {
            ["top_of_top_line"] = 0,
            ["middle_of_top_line"] = 1,
            ["middle"] = 2,
            ["middle_of_bottom_line"] = 3,
            ["bottom_of_bottom_line"] = 4,
            ["underline_bottom_line"] = 5,
            ["underline_top_line"] = 6,
            ["bottom_of_top_line"] = 7,
            ["underline_all"] = 8,
        };

        /// <summary>
        /// Ajmal's TLD label: the leader ends under the text (D-24). It is what a
        /// multileader style gets when no attachment is asked for.
        /// </summary>
        public const string TldAttachment = "underline_bottom_line";

        /// <summary>
        /// A table cell's left / centre / right, always in the vertical middle
        /// (D-83): AutoCAD's CellAlignment MiddleLeft, MiddleCenter, MiddleRight.
        /// </summary>
        public static readonly IReadOnlyDictionary<string, int> Alignments = new Dictionary<string, int>
        {
            ["left"] = 4,
            ["centre"] = 5,
            ["center"] = 5,
            ["right"] = 6,
        };

        /// <summary>The words for the three alignments, the way they are reported.</summary>
        public static string AlignmentWord(int alignment) =>
            alignment == 4 ? "middle_left" : alignment == 6 ? "middle_right" : "middle_centre";

        /// <summary>A table style's default cell margin is a third of its text height, as in AutoCAD's own Standard style (0.06 for 0.18 text).</summary>
        public const double MarginPerHeight = 1.0 / 3.0;

        private const string BadNameCharacters = "<>/\\\":;?*|,=`";

        /// <summary>The style name, trimmed, or a refusal naming what AutoCAD would not take.</summary>
        public static string CheckName(string name, string what)
        {
            var clean = (name ?? "").Trim();
            if (clean.Length == 0) throw new RunRefusal("Every " + what + " needs a 'name'.");
            if (clean.Length > 255) throw new RunRefusal("The " + what + " name '" + clean.Substring(0, 40) + "...' is longer than AutoCAD's 255 characters.");
            var bad = clean.Where(c => BadNameCharacters.IndexOf(c) >= 0 || char.IsControl(c)).Distinct().ToArray();
            if (bad.Length > 0)
                throw new RunRefusal("The " + what + " name '" + clean + "' contains " + string.Join(" ", bad.Select(c => c.ToString()))
                    + ", which AutoCAD does not allow. Avoid < > / \\ \" : ; ? * | , = ` in names.");
            return clean;
        }

        /// <summary>
        /// A word the chat gave, the way the lists above spell it: lower case,
        /// spaces and hyphens as underscores ("Underline bottom line" works).
        /// </summary>
        public static string Word(string text) =>
            string.Join("_", (text ?? "").Trim().ToLowerInvariant().Replace('-', ' ').Split(new[] { ' ', '_' }, StringSplitOptions.RemoveEmptyEntries));

        /// <summary>The DIMBLK block name for an arrow word, or for one of the block names themselves ("_DOT").</summary>
        public static string ArrowBlock(string text)
        {
            var word = Word(text);
            if (word.Length == 0) return "";
            if (Arrows.TryGetValue(word, out var block)) return block;
            foreach (var known in Arrows.Values)
                if (known.Length > 0 && string.Equals(known, "_" + word.TrimStart('_'), StringComparison.OrdinalIgnoreCase)) return known;
            throw new RunRefusal("'" + text + "' is not one of AutoCAD's arrowheads. Use one of: " + string.Join(", ", Arrows.Keys) + ".");
        }

        /// <summary>The arrow word for a block name, for the report.</summary>
        public static string ArrowWord(string block)
        {
            foreach (var pair in Arrows)
                if (string.Equals(pair.Value, block ?? "", StringComparison.OrdinalIgnoreCase)) return pair.Key;
            return block ?? "";
        }

        public static int Attachment(string text)
        {
            var word = Word(text);
            if (word.Length == 0) word = TldAttachment;
            if (Attachments.TryGetValue(word, out var value)) return value;
            throw new RunRefusal("'" + text + "' is not a multileader text attachment. Use one of: " + string.Join(", ", Attachments.Keys)
                + ". Ajmal's TLD label is " + TldAttachment + ": the leader ends under the text.");
        }

        public static string AttachmentWord(int value)
        {
            foreach (var pair in Attachments)
                if (pair.Value == value) return pair.Key;
            return value.ToString(CultureInfo.InvariantCulture);
        }

        public static int Alignment(string text, string option)
        {
            var word = Word(text);
            if (word.Length == 0) word = "centre";
            if (Alignments.TryGetValue(word, out var value)) return value;
            throw new RunRefusal("'" + text + "' is not a table alignment for '" + option + "'. Say left, centre or right: Heron keeps a table's text in the vertical middle of each cell.");
        }

        /// <summary>
        /// The scale factor a style is drawn at: 50 for 1:50. A number is the
        /// factor itself, as a dimension style's 'scale' (DIMSCALE) is; text reads
        /// the way the sheet writes it, '1:50' or '2:1'. A bare number below 1 is
        /// refused (D-104): 0.02 could be the 1:50 ratio or a factor of 0.02, and
        /// guessing wrong makes every label fifty times the wrong size.
        /// </summary>
        public static double ScaleFactor(JsonElement value)
        {
            if (value.ValueKind == JsonValueKind.Undefined || value.ValueKind == JsonValueKind.Null) return 1.0;
            if (value.ValueKind == JsonValueKind.Number) return Factor(value.GetDouble(), value.GetRawText());
            if (value.ValueKind != JsonValueKind.String) throw new RunRefusal("'scale' must be a number such as 50, or a scale such as '1:50'.");
            var text = (value.GetString() ?? "").Trim();
            if (text.StartsWith("scale", StringComparison.OrdinalIgnoreCase)) text = text.Substring(5).Trim();
            var parts = text.Split(':');
            if (parts.Length == 2 && Read(parts[0], out var paper) && Read(parts[1], out var real))
            {
                if (!(paper > 0) || !(real > 0)) throw new RunRefusal("The scale '" + text + "' must have both sides above zero.");
                return real / paper;
            }
            if (parts.Length == 1 && Read(text, out var number)) return Factor(number, text);
            throw new RunRefusal("'" + text + "' is not a scale. Write it as on the sheet, e.g. '1:50', or give the factor, e.g. 50.");
        }

        private static double Factor(double number, string written)
        {
            if (!(number > 0) || double.IsInfinity(number)) throw new RunRefusal("'scale' must be above zero.");
            if (number < 1)
                throw new RunRefusal("'" + written + "' could be a ratio or a scale factor. Write the scale as on the sheet: '1:"
                    + (1 / number).ToString("0.###", CultureInfo.InvariantCulture) + "' (a factor of "
                    + (1 / number).ToString("0.###", CultureInfo.InvariantCulture) + "), or '"
                    + (1 / number).ToString("0.###", CultureInfo.InvariantCulture) + ":1' for an enlargement.");
            return number;
        }

        private static bool Read(string text, out double value) =>
            double.TryParse(text.Trim(), NumberStyles.Float, CultureInfo.InvariantCulture, out value);

        /// <summary>A size above zero; a missing one takes the fallback, or is refused when there is none.</summary>
        public static double Size(RunArgs args, string name, double? fallback, string why)
        {
            var element = args.Element(name);
            if (element.ValueKind == JsonValueKind.Undefined || element.ValueKind == JsonValueKind.Null)
            {
                if (fallback.HasValue) return fallback.Value;
                throw new RunRefusal("Give '" + name + "': " + why + ".");
            }
            if (element.ValueKind != JsonValueKind.Number) throw new RunRefusal("'" + name + "' must be a number.");
            var value = element.GetDouble();
            if (!(value > 0) || double.IsInfinity(value)) throw new RunRefusal("'" + name + "' must be above zero.");
            return value;
        }

        /// <summary>A size that may be zero (a gap), or null when it was not given.</summary>
        public static double? Gap(RunArgs args, string name)
        {
            var element = args.Element(name);
            if (element.ValueKind == JsonValueKind.Undefined || element.ValueKind == JsonValueKind.Null) return null;
            if (element.ValueKind != JsonValueKind.Number) throw new RunRefusal("'" + name + "' must be a number.");
            var value = element.GetDouble();
            if (value < 0 || double.IsNaN(value) || double.IsInfinity(value)) throw new RunRefusal("'" + name + "' cannot be below zero.");
            return value;
        }

        public static string AlreadyThere(string what, string name) =>
            "'" + name + "' is already a " + what + " in this drawing. Pass replace=true to update it.";

        public static string NoTextStyle(string name) =>
            "This drawing has no text style called '" + name + "'. Make it first: give it in text_styles in the same autocad_create_styles call.";
    }

    /// <summary>
    /// One multileader style (D-104). Sizes are as they plot; the style's own
    /// scale makes them drawing sizes, the way AutoCAD's Multileader Style dialog
    /// does ("Specify scale"). Text only (MTEXT content), straight leaders.
    /// </summary>
    public sealed class MultileaderStylePlan
    {
        public string Name { get; private set; } = "";
        /// <summary>Empty: the drawing's current text style.</summary>
        public string TextStyle { get; private set; } = "";
        public double TextHeight { get; private set; }
        /// <summary>The DIMBLK block name; empty for closed filled.</summary>
        public string ArrowBlock { get; private set; } = "";
        public double ArrowSize { get; private set; }
        /// <summary>The short horizontal line the leader ends in (AutoCAD's dialog calls it the landing).</summary>
        public bool Dogleg { get; private set; } = true;
        public double DoglegLength { get; private set; }
        /// <summary>Null: AutoCAD's own gap.</summary>
        public double? LandingGap { get; private set; }
        /// <summary>AutoCAD's TextAttachmentType number, left and right alike.</summary>
        public int Attachment { get; private set; }
        public double Scale { get; private set; } = 1.0;
        public bool Current { get; private set; }
        public bool Replace { get; private set; }

        public static MultileaderStylePlan From(RunArgs args)
        {
            var plan = new MultileaderStylePlan
            {
                Name = StylePlans.CheckName(args.Text("name"), "multileader style"),
                TextStyle = args.Text("text_style").Trim(),
                ArrowBlock = StylePlans.ArrowBlock(args.Text("arrow")),
                Dogleg = args.Flag("dogleg", true),
                Attachment = StylePlans.Attachment(args.Text("attachment")),
                Scale = StylePlans.ScaleFactor(args.Element("scale")),
                Current = args.Flag("current", false),
                Replace = args.Flag("replace", false),
            };
            plan.TextHeight = StylePlans.Size(args, "text_height", null, "the text height as it plots, e.g. 2.5");
            // As autocad_add_label draws Ajmal's TLD label: the arrow and the landing as big as the text.
            plan.ArrowSize = StylePlans.Size(args, "arrow_size", plan.TextHeight, "");
            plan.DoglegLength = StylePlans.Size(args, "dogleg_length", plan.TextHeight, "");
            plan.LandingGap = StylePlans.Gap(args, "landing_gap");
            return plan;
        }
    }

    /// <summary>
    /// One table style (D-104). Text heights and margins are given as they plot
    /// and multiplied by the scale, because a table style has no scale of its
    /// own: 2.5 at 1:50 is 125 in the style. Every row keeps its text in the
    /// vertical middle of the cell (D-83).
    /// </summary>
    public sealed class TableStylePlan
    {
        public string Name { get; private set; } = "";
        /// <summary>Empty: the drawing's current text style.</summary>
        public string TextStyle { get; private set; } = "";
        public double Scale { get; private set; } = 1.0;
        /// <summary>In drawing units, the scale applied.</summary>
        public double DataHeight { get; private set; }
        public double HeaderHeight { get; private set; }
        public double TitleHeight { get; private set; }
        public double HorizontalMargin { get; private set; }
        public double VerticalMargin { get; private set; }
        /// <summary>AutoCAD's CellAlignment numbers: 4, 5 or 6, the middle row of the nine.</summary>
        public int DataAlignment { get; private set; }
        public int HeaderAlignment { get; private set; }
        public int TitleAlignment { get; private set; }
        public bool TitleRow { get; private set; } = true;
        public bool HeaderRow { get; private set; } = true;
        public bool Current { get; private set; }
        public bool Replace { get; private set; }

        public static TableStylePlan From(RunArgs args)
        {
            var plan = new TableStylePlan
            {
                Name = StylePlans.CheckName(args.Text("name"), "table style"),
                TextStyle = args.Text("text_style").Trim(),
                Scale = StylePlans.ScaleFactor(args.Element("scale")),
                DataAlignment = StylePlans.Alignment(args.Text("alignment"), "alignment"),
                HeaderAlignment = StylePlans.Alignment(args.Text("header_alignment"), "header_alignment"),
                TitleAlignment = StylePlans.Alignment(args.Text("title_alignment"), "title_alignment"),
                TitleRow = args.Flag("title_row", true),
                HeaderRow = args.Flag("header_row", true),
                Current = args.Flag("current", false),
                Replace = args.Flag("replace", false),
            };
            var data = StylePlans.Size(args, "text_height", null, "the text height as it plots, e.g. 2.5");
            var header = StylePlans.Size(args, "header_text_height", data, "");
            var title = StylePlans.Size(args, "title_text_height", data, "");
            var margin = StylePlans.Gap(args, "margin") ?? data * StylePlans.MarginPerHeight;
            var across = StylePlans.Gap(args, "horizontal_margin") ?? margin;
            var down = StylePlans.Gap(args, "vertical_margin") ?? margin;
            plan.DataHeight = data * plan.Scale;
            plan.HeaderHeight = header * plan.Scale;
            plan.TitleHeight = title * plan.Scale;
            plan.HorizontalMargin = across * plan.Scale;
            plan.VerticalMargin = down * plan.Scale;
            return plan;
        }
    }
}
