using System;
using Microsoft.Win32;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The five switches in Settings (D-44). Ask to Keep's and the erase
    /// question's risky side is off (D-50).
    /// </summary>
    public enum Padlock { Changes, Publish, Admin, AskToKeep, EraseQuestion }

    /// <summary>Which padlocks a Windows policy holds off on this PC (D-60).</summary>
    public sealed class PolicyHolds
    {
        public static readonly PolicyHolds None = new PolicyHolds(false, false, false);

        public PolicyHolds(bool changes, bool publish, bool admin, bool eraseQuestionOff = false)
        {
            Changes = changes;
            Publish = publish;
            Admin = admin;
            EraseQuestionOff = eraseQuestionOff;
        }

        public bool Changes { get; }
        public bool Publish { get; }
        public bool Admin { get; }

        /// <summary>
        /// The administrator set the erase question to start off on this PC
        /// (D-123). Not a hold: the modeller can still click it on, and their
        /// click wins until AutoCAD restarts.
        /// </summary>
        public bool EraseQuestionOff { get; }

        /// <summary>Ask to Keep and the erase question have no policy: they are never held.</summary>
        public bool Holds(Padlock padlock) => padlock switch
        {
            Padlock.Changes => Changes,
            Padlock.Publish => Publish,
            Padlock.Admin => Admin,
            _ => false,
        };
    }

    /// <summary>
    /// Where the policy comes from. Behind an interface so every padlock rule
    /// is tested off Windows with a fake; the real one reads the registry.
    /// </summary>
    public interface IHeronPolicy
    {
        PolicyHolds Read();
    }

    /// <summary>
    /// The PC administrator's policy (D-60): HKLM\SOFTWARE\Policies\Heron\AutoCAD,
    /// DWORD values AllowChanges, AllowPublish, AllowAdmin. A value of 0 holds that
    /// padlock off; 1, any other number or no value leaves it to the modeller.
    /// AskBeforeErasing 0 starts the erase question off (D-123): the one way
    /// to remember that choice, since no file the modeller's account can
    /// write (and so no chat) may turn it off.
    /// Only an administrator can write HKLM, so no chat or program the
    /// modeller runs can lift a hold. Read fresh each time, so a policy pushed
    /// while AutoCAD runs applies at once.
    /// </summary>
    public sealed class WindowsPolicy : IHeronPolicy
    {
        public const string KeyPath = @"SOFTWARE\Policies\Heron\AutoCAD";
        public const string AllowChanges = "AllowChanges";
        public const string AllowPublish = "AllowPublish";
        public const string AllowAdmin = "AllowAdmin";
        public const string AskBeforeErasing = "AskBeforeErasing";

        public PolicyHolds Read()
        {
            try
            {
                // AutoCAD 2021 and later is 64-bit only: read the 64-bit view, as an administrator's reg.exe writes it.
                using (var machine = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, RegistryView.Registry64))
                using (var key = machine.OpenSubKey(KeyPath, false))
                {
                    if (key == null) return PolicyHolds.None;
                    return new PolicyHolds(
                        Denies(key.GetValue(AllowChanges)),
                        Denies(key.GetValue(AllowPublish)),
                        Denies(key.GetValue(AllowAdmin)),
                        Denies(key.GetValue(AskBeforeErasing)));
                }
            }
            catch (Exception)
            {
                // No registry (not Windows) or a key nobody may read: no hold.
                // A program without administrator rights cannot cause either.
                return PolicyHolds.None;
            }
        }

        /// <summary>A DWORD (or QWORD) 0 holds; so does the text "0", for a value typed as a string by mistake.</summary>
        internal static bool Denies(object? value) => value switch
        {
            int number => number == 0,
            long number => number == 0,
            string text => text.Trim() == "0",
            _ => false,
        };
    }

    /// <summary>No policy at all: every padlock is the modeller's to turn on.</summary>
    public sealed class NoPolicy : IHeronPolicy
    {
        public PolicyHolds Read() => PolicyHolds.None;
    }
}
