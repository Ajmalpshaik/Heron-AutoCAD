using System;
using System.Windows;
using System.Windows.Controls;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// "Keep what Heron just did?" — asked after a change while Ask to Keep is
    /// on. What changed is already selected and zoomed to. Closing the box or
    /// pressing Esc discards: only a clear "keep" keeps.
    /// </summary>
    internal static class HeronKeepQuestion
    {
        public const string Title = "Heron - keep this change?";
        public const string Headline = "Keep what Heron just did?";

        /// <summary>
        /// The box closes itself as Discard after this, shorter than the server's
        /// own wait, so the answer always reaches the chat that asked.
        /// </summary>
        public static readonly TimeSpan Deadline = TimeSpan.FromMinutes(9);

        /// <summary>Main thread only. Returns keep | discard | keep_rest.</summary>
        public static string Ask(string summary, int count)
        {
            var answer = "discard";
            var window = HeronUi.NewWindow(Title, 440);
            var body = new StackPanel { Margin = new Thickness(20) };
            body.Children.Add(HeronUi.Text(Headline, 17, FontWeights.SemiBold));
            body.Children.Add(HeronUi.Text(summary, 13));
            body.Children.Add(HeronUi.Text(
                count > 0 ? (count == 1 ? "The object it made or changed is selected and in view." : count + " objects it made or changed are selected and in view.")
                          : "Look at the drawing before you choose.",
                12, null, HeronUi.Muted));

            var keep = Choice("Keep it", "It stays as one undo step.");
            var discard = Choice("Discard it", "Put the drawing back exactly as it was. Nothing is kept.");
            var rest = Choice("Keep, and keep the rest of this job without asking", "Heron stops asking until 10 quiet minutes pass.");
            keep.Click += (s, e) => { answer = "keep"; window.Close(); };
            discard.Click += (s, e) => { answer = "discard"; window.Close(); };
            rest.Click += (s, e) => { answer = "keep_rest"; window.Close(); };
            // The keyboard works too (live, 2026-10-26: only the mouse did):
            // Enter keeps, Esc discards, arrows and Tab move between choices.
            keep.IsDefault = true;
            discard.IsCancel = true;
            System.Windows.Input.KeyboardNavigation.SetDirectionalNavigation(body, System.Windows.Input.KeyboardNavigationMode.Cycle);
            body.Children.Add(keep);
            body.Children.Add(discard);
            body.Children.Add(rest);
            window.Content = body;
            var deadline = new System.Windows.Threading.DispatcherTimer { Interval = Deadline };
            deadline.Tick += (s, e) => { deadline.Stop(); answer = "discard"; window.Close(); };
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
            var words = new StackPanel { Margin = new Thickness(4) };
            var head = HeronUi.Text(text, 13, FontWeights.SemiBold);
            head.Margin = new Thickness(0);
            words.Children.Add(head);
            var small = HeronUi.Text(note, 12, null, HeronUi.Muted);
            small.Margin = new Thickness(0);
            words.Children.Add(small);
            var button = new Button
            {
                Content = words,
                HorizontalContentAlignment = HorizontalAlignment.Left,
                Margin = new Thickness(0, 6, 0, 0),
                Padding = new Thickness(8, 4, 8, 4),
                BorderThickness = new Thickness(1),
            };
            // Show plainly which choice the keyboard is on (live, 2026-10-26: the
            // arrow keys "did nothing" because nothing on screen moved).
            var normal = button.BorderBrush;
            button.GotKeyboardFocus += (s, e) =>
            {
                button.BorderBrush = HeronUi.Accent;
                button.BorderThickness = new Thickness(3);
            };
            button.LostKeyboardFocus += (s, e) =>
            {
                button.BorderBrush = normal;
                button.BorderThickness = new Thickness(1);
            };
            return button;
        }
    }
}
