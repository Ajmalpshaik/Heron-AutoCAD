using System;
using System.Windows.Threading;
using Autodesk.AutoCAD.Runtime;
using Heron.AutoCAD.Bridge;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Application;

[assembly: ExtensionApplication(typeof(Heron.AutoCAD.Addin.HeronApplication))]

namespace Heron.AutoCAD.Addin
{
    /// <summary>
    /// Heron AI for AutoCAD, loaded by AutoCAD from HeronAutoCAD.bundle.
    ///
    /// AutoCAD starts disconnected: a session nobody connected is invisible
    /// to every chat. Pressing Heron (or typing HERON) connects it.
    /// </summary>
    public sealed class HeronApplication : IExtensionApplication
    {
        private DispatcherTimer? _refresh;

        internal static BridgeServer? Server { get; private set; }
        internal static string AcadVersion { get; private set; } = "";
        internal static string AddinVersion { get; } = typeof(HeronApplication).Assembly.GetName().Version?.ToString(3) ?? "";
        internal static string? StartError { get; private set; }

        /// <summary>
        /// The padlocks, in this AutoCAD's memory only (D-59): all off at every
        /// start, whatever any file says; a Windows policy can hold one off (D-60).
        /// </summary>
        // Made first thing in Initialize, on the main thread, before the pipe can
        // start and after the static constructor has hooked the DLL resolver.
        internal static HeronPadlocks Padlocks { get; private set; } = null!;

        /// <summary>The padlocks from memory, with the file's connect-at-start and banner settings.</summary>
        internal static HeronConfig LoadConfig() => Padlocks.Snapshot(HeronConfig.Load(HeronConfig.DefaultPath));

        static HeronApplication()
        {
            // AutoCAD 2021-2024 run .NET Framework, where acad.exe carries no
            // binding redirects for System.Text.Json's helpers (System.Memory,
            // Unsafe ...). Resolve any of our own DLLs from this folder by name,
            // whatever version was asked for.
            AppDomain.CurrentDomain.AssemblyResolve += ResolveFromOwnFolder;
        }

        private static System.Reflection.Assembly? ResolveFromOwnFolder(object? sender, ResolveEventArgs args)
        {
            try
            {
                var name = new System.Reflection.AssemblyName(args.Name).Name;
                var folder = System.IO.Path.GetDirectoryName(typeof(HeronApplication).Assembly.Location);
                if (string.IsNullOrEmpty(name) || string.IsNullOrEmpty(folder)) return null;
                var path = System.IO.Path.Combine(folder, name + ".dll");
                return System.IO.File.Exists(path) ? System.Reflection.Assembly.LoadFrom(path) : null;
            }
            catch (System.Exception)
            {
                return null;
            }
        }

        public void Initialize()
        {
            Padlocks = new HeronPadlocks(new WindowsPolicy());
            try
            {
                AcadVersion = Convert.ToString(AcApp.GetSystemVariable("ACADVER")) ?? "";
                var banner = new HeronActivityBanner(AcApp.MainWindow.Handle);
                DialogGuard.Init(AcApp.MainWindow.Handle);
                Server = new BridgeServer(new AcadJobHost(banner, LoadConfig), LoadConfig, AcadVersion, AddinVersion)
                {
                    // No job begins while the palette's Undo waits for AutoCAD (D-68, #138).
                    BlockedBy = AcadJobHost.Activity.Blocking,
                };
                IdleQueue.Hook();
                CommandWatch.Hook();
                PublishVeto.Hook();
                ChangeWatch.Hook();
                HeronRibbon.Init();
                AcApp.QuitWillStart += (s, e) => Server?.Stop();

                // Pick up the "Keep: rest of job" label running out.
                _refresh = new DispatcherTimer { Interval = TimeSpan.FromSeconds(15) };
                _refresh.Tick += (s, e) => HeronRibbon.Repaint();
                _refresh.Start();

                // AutoCAD always starts disconnected: only the modeller's press of
                // Heron connects it. No file can make it connect at start (D-72).
                HeronLog.Write("Heron for AutoCAD " + AddinVersion + " loaded in AutoCAD " + AcadVersion + ".");
            }
            catch (System.Exception ex)
            {
                StartError = "Heron did not start: " + ex.Message;
                HeronLog.Error("Initialize", ex);
            }
        }

        public void Terminate()
        {
            try
            {
                _refresh?.Stop();
                Server?.Stop();
                IdleQueue.Unhook();
                CommandWatch.Unhook();
                PublishVeto.Unhook();
                ChangeWatch.Unhook();
            }
            catch (System.Exception ex)
            {
                HeronLog.Error("Terminate", ex);
            }
        }
    }
}
