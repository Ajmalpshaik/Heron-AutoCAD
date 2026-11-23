using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;
using S = Heron.AutoCAD.Addin.HeronWindowStyle;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// "Heron erased N objects: keep them erased, or bring them back?" Asked
    /// after every job that erased something, whether Ask to Keep is on or off
    /// (D-50), because a chat could otherwise approve its own delete. Enter,
    /// Esc, closing the box or no answer in time all bring them back: only a
    /// clear "keep them erased" erases. For a job that replaced objects (join,
    /// explode, a circle trimmed or broken into an arc) the server asks for the
    /// whole-change question instead (D-136): "Keep the change, or undo the
    /// whole change?", whose default undoes the whole job, so the old and the
    /// new shape are never left on top of each other. The words are
    /// <see cref="EraseWords"/>, tested offline. Main thread only. Not shown at all
    /// while the modeller has turned the erase question off in Settings: the
    /// bridge answers "kept, not asked" itself (BridgeProtocol.AskErase).
    /// </summary>
    internal static class HeronEraseQuestion
    {
        public const string Title = "Heron erased objects";
        private const double CardWidth = 460;

        /// <summary>keep_erased | restore (a whole-change question: keep_erased | undo_whole)</summary>
        public static string Ask(string summary, int count, bool whole = false)
        {
            var words = EraseWords.For(count, whole, HeronActions.EraseQuestionName);
            var fallback = whole ? EraseWords.UndoWhole : "restore";
            var answer = fallback;
            S.Shell? shell = null;
            void Answer(string what)
            {
                answer = what;
                shell!.Close();
            }

            var headline = new TextBlock
            {
                Text = words.Headline,
                FontFamily = new FontFamily(S.BodyFont),
                FontSize = 20,
                FontWeight = FontWeights.SemiBold,
                Foreground = new SolidColorBrush(S.TextPrimary),
                TextWrapping = TextWrapping.Wrap,
            };
            var what = S.Body(summary, S.TextSecondary, 13);
            what.Margin = new Thickness(0, 6, 0, 0);
            var note = S.Body(words.Note, S.TextMuted, 12);
            note.Margin = new Thickness(0, 6, 0, 4);

            var back = Choice(words.DefaultChoice, words.DefaultNote);
            var keep = Choice(words.KeepChoice, words.KeepNote);
            back.Click += (s, e) => Answer(fallback);
            keep.Click += (s, e) => Answer("keep_erased");
            back.IsDefault = true;
            back.IsCancel = true;

            var choices = new StackPanel { Margin = new Thickness(0, 6, 0, 0) };
            System.Windows.Input.KeyboardNavigation.SetDirectionalNavigation(choices, System.Windows.Input.KeyboardNavigationMode.Cycle);
            choices.Children.Add(back);
            choices.Children.Add(keep);

            var top = new StackPanel { Margin = new Thickness(S.Gutter, 20, S.Gutter, 0) };
            top.Children.Add(headline);
            top.Children.Add(what);
            top.Children.Add(note);
            top.Children.Add(choices);
            var body = new StackPanel();
            body.Children.Add(top);
            body.Children.Add(S.Footer(S.Body(words.Footer, S.TextMuted, 12)));

            shell = S.Build(Title, CardWidth, body, S.AccentColour, () => Answer(fallback));
            var window = shell.Window;
            var deadline = new System.Windows.Threading.DispatcherTimer { Interval = HeronKeepQuestion.Deadline };
            deadline.Tick += (s, e) => { deadline.Stop(); Answer(fallback); };
            window.Loaded += (s, e) =>
            {
                deadline.Start();
                window.Activate();
                back.Focus();
                System.Windows.Input.Keyboard.Focus(back);
            };
            window.Closed += (s, e) => deadline.Stop();
            AcApp.ShowModalWindow(AcApp.MainWindow.Handle, window, false);
            return answer;
        }

        /// <summary>Un-erase these handles in one transaction. How many came back.</summary>
        public static int Restore(Document doc, string[] handles)
        {
            var restored = 0;
            using (doc.LockDocument())
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                foreach (var text in handles)
                {
                    long value;
                    try
                    {
                        value = Convert.ToInt64(text, 16);
                    }
                    catch (System.Exception ex) when (ex is FormatException || ex is OverflowException || ex is ArgumentException)
                    {
                        continue;
                    }
                    if (!doc.Database.TryGetObjectId(new Handle(value), out var id) || id.IsNull || !id.IsErased) continue;
                    try
                    {
                        var obj = tr.GetObject(id, OpenMode.ForWrite, true);
                        obj.Erase(false);
                        restored++;
                    }
                    catch (Autodesk.AutoCAD.Runtime.Exception ex)
                    {
                        HeronLog.Error("Bring back " + text, ex);
                    }
                }
                tr.Commit();
            }
            return restored;
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
