using System;
using System.Collections.Generic;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// No saving, plotting or exporting during a Heron job unless Publish is on.
    ///
    /// The tools that save or export need the Publish padlock, but a command or
    /// AutoLISP job (Admin) can type QSAVE or -PLOT itself, and an office LISP
    /// routine can save inside. Saving over a shared file is the one change
    /// Ctrl+Z cannot take back, so while a Heron job runs, and for a moment
    /// after it (a typed command can start after the job's reply), the
    /// add-in vetoes these commands when Publish is off. The modeller's own
    /// Ctrl+S outside a job is never touched.
    ///
    /// The rules live here so they are tested offline; the add-in only vetoes.
    /// </summary>
    public sealed class PublishGuard
    {
        /// <summary>How long after a job's end a command it typed may still be starting.</summary>
        public static readonly TimeSpan Grace = TimeSpan.FromSeconds(3);

        /// <summary>Commands that write a drawing or a file from it.</summary>
        public static readonly HashSet<string> Commands = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "SAVE", "QSAVE", "SAVEAS", "SAVEALL", "SAVETOWEBMOBILE",
            "PLOT", "PUBLISH", "BATCHPLOT", "EXPORT", "EXPORTPDF", "EXPORTDWF", "EXPORTDWFX",
            "EXPORTLAYOUT", "EXPORTTOAUTOCAD", "ETRANSMIT", "ARCHIVE", "WBLOCK",
            "DXFOUT", "STLOUT", "ACISOUT", "PDFOUT", "JPGOUT", "PNGOUT", "BMPOUT", "TIFOUT", "WMFOUT",
            "3DDWF", "3DPRINT", "SENDTO3DPRINTSERVICE", "IGESEXPORT", "STEPEXPORT",
        };

        private readonly object _gate = new object();
        private readonly Func<DateTime> _clock;
        private readonly HashSet<string> _running = new HashSet<string>();
        private DateTime _lastEnd = DateTime.MinValue;

        public PublishGuard(Func<DateTime> clock)
        {
            _clock = clock;
        }

        /// <summary>
        /// Only Change and Admin jobs are watched: they are the ones that can
        /// type commands. A Read job's preview plots to a picture through COM,
        /// and must never be stopped; a Publish job has Publish on already.
        /// </summary>
        public static bool Watches(Risk risk) => risk == Risk.Change || risk == Risk.Admin;

        public void Begin(string job, Risk risk)
        {
            if (!Watches(risk)) return;
            lock (_gate) _running.Add(job ?? "");
        }

        public void End(string job)
        {
            lock (_gate)
            {
                if (_running.Remove(job ?? "")) _lastEnd = _clock();
            }
        }

        /// <summary>True while a watched job runs, or within <see cref="Grace"/> of the last one ending.</summary>
        public bool InJob
        {
            get
            {
                lock (_gate) return _running.Count > 0 || _clock() - _lastEnd < Grace;
            }
        }

        /// <summary>
        /// The command as AutoCAD names it, without the prefixes a script or
        /// LISP adds: '#QSAVE', '_.QSAVE', '-PLOT' and 'qsave' are all QSAVE / PLOT.
        /// </summary>
        public static string Plain(string? globalCommandName) =>
            (globalCommandName ?? "").Trim().TrimStart('#', '_', '.', '-', '+', '\'').ToUpperInvariant();

        public static bool Writes(string? globalCommandName) => Commands.Contains(Plain(globalCommandName));

        /// <summary>The words for the command line when a command is stopped, or null to let it run.</summary>
        public string? Veto(string? globalCommandName, HeronConfig config)
        {
            if (config.PublishEnabled || !Writes(globalCommandName) || !InJob) return null;
            return Texts.PublishVetoed(Plain(globalCommandName));
        }
    }
}
