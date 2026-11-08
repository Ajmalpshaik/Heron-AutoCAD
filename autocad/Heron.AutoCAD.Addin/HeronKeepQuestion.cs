using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using S = Heron.AutoCAD.Addin.HeronWindowStyle;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// "Keep what Heron just did?" — asked after a change while Ask to Keep is
    /// on. What changed is already selected and zoomed to. Closing the box or
    /// pressing Esc discards: only a clear "keep" keeps. Drawn in the Heron
    /// window style shared with Heron for Revit (D-45).
    /// </summary>
    internal static class HeronKeepQuestion
    {
        public const string Title = "Keep this change?";
        public const string Headline = "Keep what Heron just did?";

        /// <summary>
        /// The box closes itself as Discard after this, shorter than the server's
        /// own wait, so the answer always reaches the chat that asked.
        /// </summary>
        public static readonly TimeSpan Deadline = TimeSpan.FromMinutes(9);

        private const double CardWidth = 460;

        /// <summary>Main thread only. Returns keep | discard | keep_rest.</summary>
        public static string Ask(string summary, int count)
        {
            var answer = "discard";
            S.Shell? shell = null;
            void Answer(string what)
            {
                answer = what;
                shell!.Close();
            }

            var headline = new TextBlock
            {
                Text = Headline,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 20,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(S.TextPrimary),
                TextWrapping = TextWrapping.Wrap,
            };
            var what = S.Body(summary, S.TextSecondary, 13);
            what.Margin = new Thickness(0, 6, 0, 0);
            var shown = S.Body(
                count > 0 ? (count == 1 ? "The object it made or changed is selected and in view." : count + " objects it made or changed are selected and in view.")
                          : "Look at the drawing before you choose.",
                S.TextMuted, 12);
            shown.Margin = new Thickness(0, 6, 0, 4);

            var keep = Choice("Keep it", "It stays as one undo step.");
            var discard = Choice("Discard it", "Put the drawing back exactly as it was. Nothing is kept.");
            var rest = Choice("Keep, and keep the rest of this job without asking", "Heron stops asking until 10 quiet minutes pass.");
            keep.Click += (s, e) => Answer("keep");
            discard.Click += (s, e) => Answer("discard");
            rest.Click += (s, e) => Answer("keep_rest");
            // The keyboard works too (live, 2026-10-26: only the mouse did):
            // Enter keeps, Esc discards, arrows and Tab move between choices,
            // and the orange border shows which one the keyboard is on.
            keep.IsDefault = true;
            discard.IsCancel = true;

            var choices = new StackPanel { Margin = new Thickness(0, 6, 0, 0) };
            System.Windows.Input.KeyboardNavigation.SetDirectionalNavigation(choices, System.Windows.Input.KeyboardNavigationMode.Cycle);
            choices.Children.Add(keep);
            choices.Children.Add(discard);
            choices.Children.Add(rest);

            var top = new StackPanel { Margin = new Thickness(S.Gutter, 20, S.Gutter, 0) };
            top.Children.Add(headline);
            top.Children.Add(what);
            top.Children.Add(shown);
            top.Children.Add(choices);
            var body = new StackPanel();
            body.Children.Add(top);
            body.Children.Add(S.Footer(S.Body("Esc or closing this window discards.", S.TextMuted, 12)));

            shell = S.Build(Title, CardWidth, body, S.AccentColour, () => Answer("discard"));
            var window = shell.Window;
            var deadline = new System.Windows.Threading.DispatcherTimer { Interval = Deadline };
            deadline.Tick += (s, e) => { deadline.Stop(); Answer("discard"); };
            window.Loaded += (s, e) =>
            {
                deadline.Start();
                // AutoCAD keeps the keyboard unless the box takes it.
                window.Activate();
                keep.Focus();
                System.Windows.Input.Keyboard.Focus(keep);
            };
            window.Closed += (s, e) => deadline.Stop();
            AcApp.ShowModalWindow(AcApp.MainWindow.Handle, window, false);
            return answer;
        }

        private static Button Choice(string text, string note)
        {
            var head = new TextBlock
            {
                Text = text,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 14,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(S.TextPrimary),
                TextWrapping = TextWrapping.Wrap,
            };
            var small = S.Body(note, S.TextSecondary, 12);
            small.Margin = new Thickness(0, 2, 0, 0);
            var words = new StackPanel();
            words.Children.Add(head);
            words.Children.Add(small);
            return S.ChoiceButton(words);
        }
    }
}
