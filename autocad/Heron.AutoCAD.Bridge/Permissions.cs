namespace Heron.AutoCAD.Bridge
{
    public sealed class Refusal
    {
        public Refusal(string refusedBy, string message)
        {
            RefusedBy = refusedBy;
            Message = message;
        }

        public string RefusedBy { get; }
        public string Message { get; }
    }

    /// <summary>
    /// Which padlock a level needs. Changes comes first for everything that
    /// writes: Publish and Admin only widen what Changes already allows. A
    /// padlock a Windows policy holds says so, because the modeller cannot
    /// turn it on (D-60).
    /// </summary>
    public static class Permissions
    {
        public static Refusal? Refusal(Risk risk, HeronConfig config)
        {
            if (risk == Risk.Read || risk == Risk.View) return null;
            if (!config.WriteEnabled) return new Refusal("Changes", config.Held.Changes ? Texts.ChangesHeld : Texts.ChangesOff);
            if (risk == Risk.Publish && !config.PublishEnabled) return new Refusal("Publish", config.Held.Publish ? Texts.PublishHeld : Texts.PublishOff);
            if (risk == Risk.Admin && !config.AdminEnabled) return new Refusal("Admin", config.Held.Admin ? Texts.AdminHeld : Texts.AdminOff);
            return null;
        }
    }
}
