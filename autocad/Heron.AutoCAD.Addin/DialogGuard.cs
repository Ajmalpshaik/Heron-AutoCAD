using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using Heron.AutoCAD.Bridge;

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// The Win32 half of the dialog watch (D-66). While a Heron job runs, a
    /// background timer looks four times a second at the box in front of
    /// AutoCAD's main window (GetLastActivePopup) and hands what it read to
    /// <see cref="DialogWatch"/>, which decides. A press is posted, never
    /// sent, so a hung AutoCAD can never hang this thread, and no call here
    /// sends a message to AutoCAD's windows (InternalGetWindowText, not
    /// GetWindowText). Nothing runs outside a job.
    /// </summary>
    internal static class DialogGuard
    {
        private static readonly TimeSpan Every = TimeSpan.FromMilliseconds(250);
        private static readonly object Gate = new object();
        private static IntPtr _main;
        private static Timer? _timer;
        private static int _looking;

        public static DialogWatch Watch { get; } = new DialogWatch();

        /// <summary>AutoCAD's main window; set once on the main thread at load.</summary>
        public static void Init(IntPtr mainWindow) => _main = mainWindow;

        public static void Begin(string job)
        {
            try
            {
                Watch.Begin(job, OpenWindows());
                lock (Gate)
                {
                    if (_timer == null && _main != IntPtr.Zero) _timer = new Timer(_ => Tick(), null, Every, Every);
                }
            }
            catch (Exception ex)
            {
                // The watch is a help, not a gate: a job never fails because of it.
                HeronLog.Error("Dialog watch begin", ex);
            }
        }

        public static void End(string job)
        {
            Watch.End(job);
            if (Watch.Watching) return;
            lock (Gate)
            {
                _timer?.Dispose();
                _timer = null;
            }
        }

        private static void Tick()
        {
            if (Interlocked.Exchange(ref _looking, 1) == 1) return;
            try
            {
                if (!Watch.Watching) return;
                var plan = Watch.Look(Front(), handle => IsWindow(new IntPtr(handle)), DateTime.UtcNow);
                if (plan != null) Press(plan);
            }
            catch (Exception ex)
            {
                HeronLog.Error("Dialog watch", ex);
            }
            finally
            {
                Interlocked.Exchange(ref _looking, 0);
            }
        }

        /// <summary>The box in front of AutoCAD, or null when AutoCAD shows none.</summary>
        private static DialogSeen? Front()
        {
            if (_main == IntPtr.Zero || !IsWindow(_main)) return null;
            var popup = GetLastActivePopup(_main);
            if (popup == IntPtr.Zero || popup == _main || !IsWindowVisible(popup)) return null;
            if (!SameProcess(popup)) return null;
            var exStyle = GetWindowLong(popup, GwlExStyle);
            return new DialogSeen
            {
                Handle = popup.ToInt64(),
                Title = Text(popup),
                ClassName = ClassOf(popup),
                OwnerDisabled = !IsWindowEnabled(_main),
                Enabled = IsWindowEnabled(popup),
                NoActivate = (exStyle & WsExNoActivate) != 0,
                Buttons = ButtonsOf(popup),
            };
        }

        private static void Press(DialogPlan plan)
        {
            var box = new IntPtr(plan.Handle);
            HeronLog.Write("dialog watch: '" + plan.Title + "' -> " + DialogWatch.Name(plan.Press));
            bool posted;
            if (plan.Press == DialogPress.Escape && !plan.StandardBox)
            {
                // Not a standard box (WPF, WinForms, MFC): its ✕, which they all treat as Cancel.
                posted = PostMessage(box, WmClose, IntPtr.Zero, IntPtr.Zero);
            }
            else
            {
                // Cancel / No by its control id; Esc on a standard box is its Cancel command,
                // exactly what the Esc key sends.
                var id = plan.Press == DialogPress.Escape ? DialogWatch.IdCancel : plan.ButtonId;
                var button = plan.Press == DialogPress.Escape ? IntPtr.Zero : GetDlgItem(box, id);
                posted = PostMessage(box, WmCommand, new IntPtr(id & 0xFFFF), button);
            }
            if (!posted) HeronLog.Write("dialog watch: could not post the press to '" + plan.Title + "'");
        }

        /// <summary>Every visible top-level window of this AutoCAD right now: the job never touches them.</summary>
        private static List<long> OpenWindows()
        {
            var found = new List<long>();
            var pid = (uint)Process.GetCurrentProcess().Id;
            EnumWindows((hwnd, _) =>
            {
                GetWindowThreadProcessId(hwnd, out var owner);
                if (owner == pid && IsWindowVisible(hwnd)) found.Add(hwnd.ToInt64());
                return true;
            }, IntPtr.Zero);
            return found;
        }

        private static DialogButton[] ButtonsOf(IntPtr box)
        {
            var buttons = new List<DialogButton>();
            EnumChildWindows(box, (child, _) =>
            {
                if (buttons.Count < 40 && ClassOf(child) == "Button" && IsWindowVisible(child))
                    buttons.Add(new DialogButton { Id = GetDlgCtrlID(child), Text = Text(child), Enabled = IsWindowEnabled(child) });
                return true;
            }, IntPtr.Zero);
            return buttons.ToArray();
        }

        private static bool SameProcess(IntPtr hwnd)
        {
            GetWindowThreadProcessId(hwnd, out var owner);
            return owner == (uint)Process.GetCurrentProcess().Id;
        }

        private static string Text(IntPtr hwnd)
        {
            var buffer = new StringBuilder(256);
            InternalGetWindowText(hwnd, buffer, buffer.Capacity);
            return buffer.ToString();
        }

        private static string ClassOf(IntPtr hwnd)
        {
            var buffer = new StringBuilder(128);
            GetClassName(hwnd, buffer, buffer.Capacity);
            return buffer.ToString();
        }

        private const int GwlExStyle = -20;
        private const int WsExNoActivate = 0x8000000;
        private const uint WmClose = 0x0010;
        private const uint WmCommand = 0x0111;

        private delegate bool EnumProc(IntPtr hwnd, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool EnumWindows(EnumProc callback, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern bool EnumChildWindows(IntPtr parent, EnumProc callback, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern IntPtr GetLastActivePopup(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern bool IsWindow(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern bool IsWindowEnabled(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);

        [DllImport("user32.dll")]
        private static extern int GetWindowLong(IntPtr hwnd, int index);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int InternalGetWindowText(IntPtr hwnd, StringBuilder text, int max);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetClassName(IntPtr hwnd, StringBuilder name, int max);

        [DllImport("user32.dll")]
        private static extern int GetDlgCtrlID(IntPtr hwnd);

        [DllImport("user32.dll")]
        private static extern IntPtr GetDlgItem(IntPtr dialog, int id);

        [DllImport("user32.dll")]
        private static extern bool PostMessage(IntPtr hwnd, uint msg, IntPtr wParam, IntPtr lParam);
    }
}
