using System;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The padlocks, Ask to Keep and the erase question, in this AutoCAD's
    /// memory only (D-59).
    ///
    /// Every AutoCAD starts with Changes, Publish and Admin off, Ask to Keep
    /// off as before (the owner's choice, 2026-11-21), and the erase question
    /// on (D-50; the owner may turn it off, 2026-11-22). No file is read for them, so no
    /// program that can write a file (an AI chat included) can turn one on. Each
    /// open AutoCAD has its own. Only the plug-in's own windows call TurnOn and
    /// TurnOff, after the modeller's click; the pipe has no request that
    /// reaches them.
    ///
    /// A padlock a Windows policy holds (D-60) reads off, and is put off here
    /// too, so lifting the policy later never turns it back on without a click.
    /// </summary>
    public sealed class HeronPadlocks
    {
        private readonly object _gate = new object();
        private readonly IHeronPolicy _policy;
        private bool _changes;
        private bool _publish;
        private bool _admin;
        private bool _askToKeep;
        private bool _eraseQuestion = true;

        public HeronPadlocks(IHeronPolicy policy)
        {
            _policy = policy;
        }

        /// <summary>What a Windows policy holds off right now. Never throws.</summary>
        public PolicyHolds Holds()
        {
            try
            {
                return _policy.Read() ?? PolicyHolds.None;
            }
            catch (Exception)
            {
                return PolicyHolds.None;
            }
        }

        /// <summary>
        /// The switches the bridge obeys for one call: the file's own settings
        /// (only the banner since D-73) with the padlocks from memory on top.
        /// Whatever padlock values <paramref name="fileSettings"/> carries are
        /// replaced, never used.
        /// </summary>
        public HeronConfig Snapshot(HeronConfig fileSettings)
        {
            var held = Holds();
            lock (_gate)
            {
                Drop(held);
                return new HeronConfig
                {
                    WriteEnabled = _changes,
                    PublishEnabled = _publish,
                    AdminEnabled = _admin,
                    AskBeforeKeeping = _askToKeep,
                    AskBeforeErasing = _eraseQuestion,
                    ActivityBanner = fileSettings.ActivityBanner,
                    Held = held,
                };
            }
        }

        public bool IsOn(Padlock padlock)
        {
            var held = Holds();
            lock (_gate)
            {
                Drop(held);
                return Get(padlock);
            }
        }

        /// <summary>
        /// The modeller clicked to turn it on (for Ask to Keep and the erase
        /// question: to ask again).
        /// False, and nothing changes, when a Windows policy holds it off.
        /// </summary>
        public bool TurnOn(Padlock padlock)
        {
            var held = Holds();
            lock (_gate)
            {
                Drop(held);
                if (held.Holds(padlock)) return false;
                Set(padlock, true);
                return true;
            }
        }

        /// <summary>The modeller clicked to turn it off (for Ask to Keep and the erase question: to stop asking).</summary>
        public void TurnOff(Padlock padlock)
        {
            lock (_gate) Set(padlock, false);
        }

        private void Drop(PolicyHolds held)
        {
            if (held.Changes) _changes = false;
            if (held.Publish) _publish = false;
            if (held.Admin) _admin = false;
        }

        private bool Get(Padlock padlock) => padlock switch
        {
            Padlock.Changes => _changes,
            Padlock.Publish => _publish,
            Padlock.Admin => _admin,
            Padlock.AskToKeep => _askToKeep,
            Padlock.EraseQuestion => _eraseQuestion,
            _ => false,
        };

        private void Set(Padlock padlock, bool on)
        {
            switch (padlock)
            {
                case Padlock.Changes: _changes = on; break;
                case Padlock.Publish: _publish = on; break;
                case Padlock.Admin: _admin = on; break;
                case Padlock.AskToKeep: _askToKeep = on; break;
                case Padlock.EraseQuestion: _eraseQuestion = on; break;
            }
        }
    }
}
