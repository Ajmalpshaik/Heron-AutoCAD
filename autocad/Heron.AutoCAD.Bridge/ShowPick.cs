using System;
using System.Collections.Generic;
using System.Linq;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// Where one of a job's handles stands for Select and Zoom (#234, D-132).
    /// The add-in looks each handle up in the drawing; only
    /// <see cref="InSpace"/> may go to <c>Editor.SetImpliedSelection</c>,
    /// which throws eInvalidInput for anything else.
    /// </summary>
    public enum ShowPlace
    {
        /// <summary>A drawing object in the space in front: it can be selected.</summary>
        InSpace,

        /// <summary>A drawing object on another layout, or on the Model tab while a layout is in front.</summary>
        OtherSpace,

        /// <summary>A drawing object inside a block definition (or part of an object not in this space).</summary>
        InsideBlock,

        /// <summary>Not a drawing object at all: a style, a layer, a block definition, a dictionary.</summary>
        NotDrawingObject,

        /// <summary>Erased, not in the drawing, or not a handle.</summary>
        Gone,
    }

    /// <summary>One handle as the add-in found it, with the id to select when it can be.</summary>
    public readonly struct ShowLook<T>
    {
        public ShowLook(string handle, ShowPlace place, T id)
        {
            Handle = handle ?? "";
            Place = place;
            Id = id;
        }

        public string Handle { get; }
        public ShowPlace Place { get; }

        /// <summary>
        /// What to select. For an attribute or a vertex this is the object it
        /// belongs to (the block reference, the polyline), so it can be the
        /// same id for several handles.
        /// </summary>
        public T Id { get; }
    }

    /// <summary>A job's handles sorted for Select and Zoom: what to select, and what was left out and why.</summary>
    public sealed class ShowPicked<T>
    {
        /// <summary>The ids to select, each once, in the order first seen.</summary>
        public IReadOnlyList<T> Ids { get; internal set; } = new T[0];

        /// <summary>How many handles were asked for.</summary>
        public int Asked { get; internal set; }

        /// <summary>More than <see cref="ShowPick.Most"/>: nothing was looked up or selected.</summary>
        public bool TooMany { get; internal set; }

        public IReadOnlyList<string> Gone { get; internal set; } = new string[0];
        public IReadOnlyList<string> OtherSpace { get; internal set; } = new string[0];
        public IReadOnlyList<string> InsideBlock { get; internal set; } = new string[0];
        public IReadOnlyList<string> NotDrawingObject { get; internal set; } = new string[0];

        /// <summary>Handles that exist but cannot be selected in the space in front.</summary>
        public int NotSelectable => OtherSpace.Count + InsideBlock.Count + NotDrawingObject.Count;

        /// <summary>Every handle that was left out, for any reason.</summary>
        public int LeftOut => Gone.Count + NotSelectable;

        /// <summary>
        /// The handles that exist but were left out, each with its reason as
        /// the show operation answers it: other_space, inside_block,
        /// not_a_drawing_object. Gone handles are the separate not_found list.
        /// </summary>
        public IEnumerable<KeyValuePair<string, string>> NotSelectableWithReason()
        {
            foreach (var h in OtherSpace) yield return new KeyValuePair<string, string>(h, ShowPick.ReasonOtherSpace);
            foreach (var h in InsideBlock) yield return new KeyValuePair<string, string>(h, ShowPick.ReasonInsideBlock);
            foreach (var h in NotDrawingObject) yield return new KeyValuePair<string, string>(h, ShowPick.ReasonNotDrawingObject);
        }
    }

    /// <summary>
    /// The rules of Select and Zoom that need no AutoCAD (#234, D-132): which
    /// handles are selected, which are left out and why, and what the palette
    /// says about it. Tested offline; the add-in only looks each handle up.
    /// </summary>
    public static class ShowPick
    {
        /// <summary>Most objects Heron selects at once.</summary>
        public const int Most = 500;

        public const string ReasonOtherSpace = "other_space";
        public const string ReasonInsideBlock = "inside_block";
        public const string ReasonNotDrawingObject = "not_a_drawing_object";

        /// <summary>
        /// A drawing handle as a number: hexadecimal, spaces trimmed, above
        /// zero (0 is no object). False for anything else, never a throw.
        /// </summary>
        public static bool TryParseHandle(string? text, out long value)
        {
            value = 0;
            var trimmed = (text ?? "").Trim();
            if (trimmed.Length == 0) return false;
            try
            {
                value = Convert.ToInt64(trimmed, 16);
            }
            catch (Exception ex) when (ex is FormatException || ex is OverflowException || ex is ArgumentException)
            {
                value = 0;
                return false;
            }
            if (value > 0) return true;
            value = 0;
            return false;
        }

        /// <summary>The answer when there are too many handles: nothing looked up or selected.</summary>
        public static ShowPicked<T> TooManyOf<T>(int asked) => new ShowPicked<T> { Asked = asked, TooMany = true };

        /// <summary>Sort the looked-up handles: the ids to select (each once) and the rest by reason.</summary>
        public static ShowPicked<T> Sort<T>(IEnumerable<ShowLook<T>> looks)
        {
            var ids = new List<T>();
            var seen = new HashSet<T>();
            var gone = new List<string>();
            var other = new List<string>();
            var inside = new List<string>();
            var notDrawing = new List<string>();
            var asked = 0;
            foreach (var look in looks)
            {
                asked++;
                switch (look.Place)
                {
                    case ShowPlace.InSpace:
                        if (seen.Add(look.Id)) ids.Add(look.Id);
                        break;
                    case ShowPlace.OtherSpace:
                        other.Add(look.Handle);
                        break;
                    case ShowPlace.InsideBlock:
                        inside.Add(look.Handle);
                        break;
                    case ShowPlace.NotDrawingObject:
                        notDrawing.Add(look.Handle);
                        break;
                    default:
                        gone.Add(look.Handle);
                        break;
                }
            }
            return new ShowPicked<T>
            {
                Ids = ids,
                Asked = asked,
                Gone = gone,
                OtherSpace = other,
                InsideBlock = inside,
                NotDrawingObject = notDrawing,
            };
        }

        /// <summary>
        /// What the palette says after Select (zoom false) or Zoom (zoom true).
        /// </summary>
        /// <param name="selected">AutoCAD took the selection (false when it refused it).</param>
        /// <param name="zoomed">The view was zoomed to them (only asked with zoom true).</param>
        public static string Line<T>(ShowPicked<T> picked, bool zoom, bool selected, bool zoomed) =>
            PaletteTexts.Shown(
                picked.TooMany ? picked.Asked : 0,
                picked.Ids.Count,
                zoom,
                selected,
                zoomed,
                picked.Gone.Count,
                picked.OtherSpace.Count,
                picked.InsideBlock.Count,
                picked.NotDrawingObject.Count);

        /// <summary>
        /// How many the Keep question may say are selected and in view: only
        /// what AutoCAD really selected, 0 otherwise (the box then says to look).
        /// </summary>
        public static int SelectedCount<T>(ShowPicked<T> picked, bool selected) =>
            selected && !picked.TooMany ? picked.Ids.Count : 0;

        internal static string Count(int n, string one, string many) => n + " " + (n == 1 ? one : many);

        internal static string Reasons(int gone, int otherSpace, int insideBlock, int notDrawing)
        {
            var parts = new List<string>();
            if (otherSpace > 0) parts.Add(otherSpace + (otherSpace == 1 ? " is" : " are") + " on another layout or the Model tab");
            if (insideBlock > 0) parts.Add(insideBlock + (insideBlock == 1 ? " is" : " are") + " inside a block definition");
            if (notDrawing > 0) parts.Add(notDrawing + (notDrawing == 1 ? " is not a drawing object" : " are not drawing objects") + " (a style, a layer or a definition)");
            if (gone > 0) parts.Add(gone + (gone == 1 ? " is" : " are") + " erased or gone");
            if (parts.Count <= 1) return string.Join("", parts);
            return string.Join(", ", parts.Take(parts.Count - 1)) + " and " + parts[parts.Count - 1];
        }
    }
}
