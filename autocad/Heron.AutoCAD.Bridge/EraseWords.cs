namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The words of the erase question (D-50), kept here so they are tested
    /// offline. Two kinds of question:
    /// <list type="bullet">
    /// <item>the usual one, for a job that erased objects: "Bring them back" or
    /// "Keep them erased";</item>
    /// <item>the whole-change one (D-136), for a job that replaced objects (join,
    /// explode, a circle trimmed or broken into an arc) and that Heron put an UNDO
    /// mark down for: "Undo the whole change" or "Keep the change". Bringing back
    /// only the erased object would leave the old and the new shape on top of
    /// each other, so the default undoes the whole job instead.</item>
    /// </list>
    /// The default (Enter, Esc, closing the box, no answer in time) is always
    /// the first choice: nothing is erased for good without a clear keep.
    /// </summary>
    public sealed class EraseWords
    {
        /// <summary>The answer the plug-in gives for a whole-change question that was not a clear keep.</summary>
        public const string UndoWhole = "undo_whole";

        public string Headline { get; private set; } = "";
        public string DefaultChoice { get; private set; } = "";
        public string DefaultNote { get; private set; } = "";
        public string KeepChoice { get; private set; } = "";
        public string KeepNote { get; private set; } = "";
        public string Note { get; private set; } = "";
        public string Footer { get; private set; } = "";

        /// <param name="count">How many objects the job erased.</param>
        /// <param name="whole">The job replaced objects and Heron holds its UNDO mark: ask about the whole change.</param>
        /// <param name="settingName">The Settings switch that stops the question.</param>
        public static EraseWords For(int count, bool whole, string settingName)
        {
            var erased = count == 1 ? "Heron erased 1 object." : "Heron erased " + count + " objects.";
            var stop = " To stop this question, turn off \"" + settingName + "\" in Settings.";
            if (whole)
            {
                return new EraseWords
                {
                    Headline = "Keep the change, or undo the whole change?",
                    DefaultChoice = "Undo the whole change",
                    DefaultNote = "The drawing goes back exactly as it was before this job, the new shape too. Nothing is left doubled.",
                    KeepChoice = "Keep the change",
                    KeepNote = "The new shape stays, and what it replaced stays erased.",
                    Note = erased.TrimEnd('.') + " to make the new shape. Nothing is erased for good until you say so.",
                    Footer = "Esc or closing this window undoes the whole change." + stop,
                };
            }
            return new EraseWords
            {
                Headline = erased,
                DefaultChoice = "Bring them back",
                DefaultNote = "Every object this job erased comes back as it was. The rest of the job stays.",
                KeepChoice = "Keep them erased",
                KeepNote = "They stay erased, with the rest of the job.",
                Note = "Nothing is erased for good until you say so.",
                Footer = "Esc or closing this window brings them back." + stop,
            };
        }
    }
}
