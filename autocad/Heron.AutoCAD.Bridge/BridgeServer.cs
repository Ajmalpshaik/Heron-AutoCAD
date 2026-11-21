using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Heron.AutoCAD.Bridge
{
    /// <summary>
    /// The named pipe a chat reaches this AutoCAD through.
    ///
    /// Start = connect: mint a token, open the pipe (current Windows user
    /// only), publish the address file. Stop = disconnect: close the pipe and
    /// delete the file, so no chat can find this AutoCAD any more.
    /// </summary>
    public sealed class BridgeServer : IDisposable
    {
        private const int Listeners = 4;

        private readonly IJobHost _host;
        private readonly Func<HeronConfig> _config;
        private readonly string _acadVersion;
        private readonly string _addinVersion;
        private readonly string _folder;
        private readonly object _gate = new object();
        private CancellationTokenSource? _stop;
        private readonly List<Task> _loops = new List<Task>();

        public BridgeServer(IJobHost host, Func<HeronConfig> config, string acadVersion, string addinVersion,
            string? folder = null, string? pipeName = null)
        {
            _host = host;
            _config = config;
            _acadVersion = acadVersion;
            _addinVersion = addinVersion;
            _folder = folder ?? DefaultFolder;
            PipeName = pipeName ?? "heron.autocad." + ProcessId;
        }

        public static string DefaultFolder => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Heron", "autocad", "bridges");

        private static int ProcessId
        {
            get { using (var me = Process.GetCurrentProcess()) return me.Id; }
        }

        public string PipeName { get; }
        public string AddressPath => Path.Combine(_folder, ProcessId + ".json");
        public string? Token { get; private set; }
        public BridgeProtocol? Protocol { get; private set; }

        /// <summary>Handed to every protocol this server starts: see <see cref="BridgeProtocol.BlockedBy"/>.</summary>
        public Func<string?>? BlockedBy { get; set; }

        /// <summary>Handed to every protocol this server starts: see <see cref="BridgeProtocol.CurrentCommand"/>.</summary>
        public Func<string?>? CurrentCommand { get; set; }
        public DateTime StartedAt { get; private set; }

        public bool IsRunning
        {
            get { lock (_gate) return _stop != null; }
        }

        public void Start()
        {
            lock (_gate)
            {
                if (_stop != null) return;
                Token = BridgeIdentity.MintToken();
                StartedAt = DateTime.UtcNow;
                Protocol = new BridgeProtocol(_host, _config, Token, new HeronHold(), () => DateTime.UtcNow);
                Protocol.Info["acadVersion"] = _acadVersion;
                Protocol.Info["addinVersion"] = _addinVersion;
                Protocol.BlockedBy = BlockedBy;
                Protocol.CurrentCommand = CurrentCommand;
                _stop = new CancellationTokenSource();
                for (var i = 0; i < Listeners; i++)
                {
                    var protocol = Protocol;
                    var token = _stop.Token;
                    _loops.Add(Task.Run(() => Listen(protocol, token)));
                }
                WriteAddress();
            }
        }

        public void Stop()
        {
            CancellationTokenSource? stop;
            lock (_gate)
            {
                stop = _stop;
                _stop = null;
                Token = null;
                Protocol = null;
            }
            if (stop == null) return;
            try
            {
                File.Delete(AddressPath);
            }
            catch (IOException)
            {
            }
            stop.Cancel();
            try
            {
                Task.WaitAll(_loops.ToArray(), TimeSpan.FromSeconds(2));
            }
            catch (AggregateException)
            {
            }
            _loops.Clear();
            stop.Dispose();
        }

        public void Dispose() => Stop();

        private void WriteAddress()
        {
            var json = new StringBuilder();
            json.Append("{\n");
            json.Append("  \"pid\": ").Append(ProcessId).Append(",\n");
            json.Append("  \"pipeName\": \"").Append(PipeName).Append("\",\n");
            json.Append("  \"acadVersion\": \"").Append(_acadVersion).Append("\",\n");
            json.Append("  \"addinVersion\": \"").Append(_addinVersion).Append("\",\n");
            json.Append("  \"protocolVersion\": ").Append(BridgeProtocol.Version).Append(",\n");
            json.Append("  \"token\": \"").Append(Token).Append("\",\n");
            json.Append("  \"startedAt\": \"").Append(StartedAt.ToString("o")).Append("\"\n}\n");
            AtomicFile.Write(AddressPath, json.ToString());
        }

        private NamedPipeServerStream CreatePipe()
        {
            var security = new PipeSecurity();
            var me = WindowsIdentity.GetCurrent().User!;
            security.AddAccessRule(new PipeAccessRule(me,
                PipeAccessRights.ReadWrite | PipeAccessRights.CreateNewInstance, AccessControlType.Allow));
#if NETFRAMEWORK
            return new NamedPipeServerStream(PipeName, PipeDirection.InOut, NamedPipeServerStream.MaxAllowedServerInstances,
                PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 0, 0, security);
#else
            return NamedPipeServerStreamAcl.Create(PipeName, PipeDirection.InOut, NamedPipeServerStream.MaxAllowedServerInstances,
                PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 0, 0, security);
#endif
        }

        private async Task Listen(BridgeProtocol protocol, CancellationToken stop)
        {
            while (!stop.IsCancellationRequested)
            {
                NamedPipeServerStream pipe;
                try
                {
                    pipe = CreatePipe();
                }
                catch (IOException)
                {
                    await Task.Delay(200).ConfigureAwait(false);
                    continue;
                }

                using (pipe)
                {
                    try
                    {
                        await pipe.WaitForConnectionAsync(stop).ConfigureAwait(false);
                        await Serve(pipe, protocol, stop).ConfigureAwait(false);
                    }
                    catch (OperationCanceledException)
                    {
                        return;
                    }
                    catch (IOException)
                    {
                        // The chat went away mid-line; wait for the next one.
                    }
                    catch (ObjectDisposedException)
                    {
                        return;
                    }
                }
            }
        }

        private static async Task Serve(NamedPipeServerStream pipe, BridgeProtocol protocol, CancellationToken stop)
        {
            var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, true);
            var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { NewLine = "\n", AutoFlush = true };
            while (!stop.IsCancellationRequested && pipe.IsConnected)
            {
                var line = await reader.ReadLineAsync().ConfigureAwait(false);
                if (line == null) return;
                var reply = protocol.Handle(line);
                await writer.WriteLineAsync(reply).ConfigureAwait(false);
            }
        }
    }
}
