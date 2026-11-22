"""Install.ps1 -Connect and -Disconnect on made-up Windows profiles (#233, D-126).

Each test builds a folder layout under tmp_path, points APPDATA, LOCALAPPDATA and USERPROFILE
at it and runs the real Install.ps1 in Windows PowerShell 5.1, as the setup does. Claude Code is
a stand-in claude.exe, compiled here with the .NET Framework's own C# compiler: it writes down
how and where it was started, and writes the "autocad" entry the way
`claude mcp add --scope user` does. The real claude.exe and the real Claude app are Group AK in
docs/NEEDS-CHECKING.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_PS1 = ROOT / "tools" / "release_files" / "Install.ps1"
WINDIR = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
POWERSHELL = WINDIR / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
CSC = WINDIR / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
# The Microsoft Store Claude app's package, as its data folder is named.
PACKAGE = "anthropicpbc.claude_fnn82j28hfe8t"

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not POWERSHELL.is_file(), reason="Install.ps1 runs in Windows PowerShell 5.1"
)

FAKE_CLAUDE = r"""
using System;
using System.IO;

static class FakeClaude {
    static int Main(string[] args) {
        string home = Environment.GetEnvironmentVariable("USERPROFILE");
        string exe = System.Reflection.Assembly.GetEntryAssembly().Location;
        File.AppendAllText(Path.Combine(home, "claude-calls.txt"),
            exe + "\t" + Environment.CurrentDirectory + "\t" + string.Join("|", args) + Environment.NewLine);
        string config = Path.Combine(home, ".claude.json");
        if (args.Length >= 2 && args[0] == "mcp" && args[1] == "add") {
            if (File.Exists(config) && File.ReadAllText(config).Contains("\"autocad\"")) {
                Console.Error.WriteLine("MCP server autocad already exists in user config");
                return 1;
            }
            string command = args[args.Length - 1].Replace("\\", "\\\\");
            File.WriteAllText(config, "{\"mcpServers\":{\"autocad\":{\"type\":\"stdio\",\"command\":\"" + command + "\",\"args\":[]}}}");
            Console.WriteLine("Added stdio MCP server autocad to user config");
            return 0;
        }
        if (args.Length >= 2 && args[0] == "mcp" && args[1] == "remove") {
            File.WriteAllText(config, "{\"mcpServers\":{}}");
            Console.WriteLine("Removed MCP server autocad from user config");
            return 0;
        }
        Console.Error.WriteLine("stand-in claude: not a call Heron makes");
        return 2;
    }
}
"""


@pytest.fixture(scope="module")
def fake_claude(tmp_path_factory) -> Path:
    if not CSC.is_file():
        pytest.skip("no .NET Framework C# compiler here to build the stand-in claude.exe")
    folder = tmp_path_factory.mktemp("fake-claude")
    source = folder / "FakeClaude.cs"
    source.write_text(FAKE_CLAUDE, encoding="ascii")
    exe = folder / "claude.exe"
    built = subprocess.run([str(CSC), "/nologo", "/target:exe", f"/out:{exe}", str(source)],
                           capture_output=True, text=True, timeout=120)  # fmt: skip
    assert built.returncode == 0, built.stdout + built.stderr
    return exe


def _autocad_open() -> bool:
    shown = subprocess.run(["tasklist", "/FI", "IMAGENAME eq acad.exe", "/NH"], capture_output=True, text=True)
    return "acad.exe" in shown.stdout.lower()


@pytest.fixture
def no_autocad():
    if _autocad_open():
        pytest.skip("AutoCAD is open on this PC, and Install.ps1 -Connect rightly refuses while it is")


class Profile:
    """A Windows user's folders, made up under one temporary folder."""

    def __init__(self, root: Path):
        self.root = root
        self.roaming, self.local, self.home, self.bin = root / "Roaming", root / "Local", root / "home", root / "bin"
        for folder in (self.roaming, self.local, self.home, self.bin):
            folder.mkdir(parents=True)
        self.server = self.local / "Heron" / "autocad" / "autocad-mcp.exe"
        self.server.parent.mkdir(parents=True)
        self.server.write_bytes(b"MZ")  # never started here
        self.claude_json = self.home / ".claude.json"

    @property
    def calls(self) -> list[list[str]]:
        """Each start of a stand-in claude.exe: [its path, the folder it ran in, its arguments]."""
        log = self.home / "claude-calls.txt"
        if not log.exists():
            return []
        return [line.split("\t") for line in log.read_text(encoding="utf-8").splitlines()]

    def store_app(self, desktop_config: dict | None = None, claude_exe: Path | None = None) -> Path:
        """The Microsoft Store Claude app, as it was found on a real PC (#233)."""
        data = self.local / "Claude-Data" / PACKAGE
        data.mkdir(parents=True)
        config = data / "claude_desktop_config.json"
        config.write_text(json.dumps(desktop_config if desktop_config is not None else {"preferences": {}}), encoding="utf-8")
        # Its private copy of %APPDATA%\Claude, with only the note that the data moved.
        left = self.roaming / "Claude"
        left.mkdir()
        (left / f".user-data-left.{PACKAGE}").write_text("", encoding="ascii")
        if claude_exe:
            inside = data / "claude-code" / "2.1.999" / "0123abcd"
            inside.mkdir(parents=True)
            shutil.copy(claude_exe, inside / "claude.exe")
        return config

    def run(self, *switches: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "PSMODULEPATH", "CLAUDE_CONFIG_DIR")}
        env.update(APPDATA=str(self.roaming), LOCALAPPDATA=str(self.local), USERPROFILE=str(self.home),
                   HOME=str(self.home),
                   PATH=os.pathsep.join([str(self.bin), str(WINDIR / "System32"), str(WINDIR), str(POWERSHELL.parent)]))  # fmt: skip
        return subprocess.run([str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(INSTALL_PS1), *switches],
                              env=env, capture_output=True, text=True, timeout=180, cwd=str(self.root))  # fmt: skip

    def backups(self) -> list[Path]:
        return sorted(self.root.rglob("*.heron-backup"))


def _same_folder(a: str, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(str(b)))


def _hand_entry(server: Path) -> str:
    return '"autocad": {"command": "' + str(server).replace("\\", "\\\\") + '"}'


def test_store_app_only_connects_its_code_tab_and_its_chat(tmp_path, fake_claude, no_autocad):
    p = Profile(tmp_path)
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": {"j": {"k": {"l": 1}}}}}}}}}}}}
    config = p.store_app({"preferences": deep, "mcpServers": {"other": {"command": "x"}}}, claude_exe=fake_claude)
    before = config.read_bytes()

    done = p.run("-Connect")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "Claude Code:        connected (all projects)" in done.stdout
    assert "Claude Desktop:     connected (restart Claude; old settings saved as .heron-backup)" in done.stdout
    [(exe, ran_in, arguments)] = p.calls
    assert Path(exe).parents[2].name == "claude-code", "the copy the Claude app runs in its Code tab"
    assert _same_folder(ran_in, p.server.parent), "run from Heron's folder, never the caller's project"
    assert arguments.split("|") == ["mcp", "add", "--scope", "user", "autocad", "--", str(p.server)]
    assert json.loads(p.claude_json.read_text(encoding="utf-8"))["mcpServers"]["autocad"]["command"] == str(p.server)
    written = config.read_bytes()
    assert not written.startswith(b"\xef\xbb\xbf"), "Claude Desktop cannot read a byte-order mark"
    after = json.loads(written)
    assert after["mcpServers"] == {"other": {"command": "x"}, "autocad": {"command": str(p.server)}}
    assert after["preferences"] == deep, "the app's own deeper settings come back whole"
    assert (config.parent / "claude_desktop_config.json.heron-backup").read_bytes() == before
    assert [f.name for f in (p.roaming / "Claude").iterdir()] == [f".user-data-left.{PACKAGE}"], (
        "nothing written where the app's data used to be"
    )


def test_claude_code_is_found_on_the_path_then_its_own_folder_then_the_app(tmp_path, fake_claude, no_autocad):
    p = Profile(tmp_path)
    p.store_app(claude_exe=fake_claude)
    on_path = p.bin / "claude.exe"
    own = p.home / ".local" / "bin" / "claude.exe"
    own.parent.mkdir(parents=True)
    for copy in (on_path, own):
        shutil.copy(fake_claude, copy)

    for expected in (on_path, own, None):
        p.claude_json.unlink(missing_ok=True)
        done = p.run("-Connect")
        assert "Claude Code:        connected (all projects)" in done.stdout, done.stdout + done.stderr
        used = Path(p.calls[-1][0])
        if expected is None:
            assert used.parents[2].name == "claude-code"
        else:
            assert used == expected
            expected.unlink()


def test_nothing_found_says_what_to_add_and_where(tmp_path, no_autocad):
    p = Profile(tmp_path)

    done = p.run("-Connect")

    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    entry = _hand_entry(p.server)
    assert lines[0].startswith("Claude Code:        not found, so nothing was added")
    assert entry in lines[1] and ".mcp.json" in lines[1]
    assert lines[2].startswith("Claude Desktop:     not found, so nothing was added")
    assert entry in lines[3] and "claude_desktop_config.json" in lines[3]
    assert "skipped" not in done.stdout
    json.loads("{" + entry + "}")  # what it says to type is JSON
    assert not p.claude_json.exists() and not (p.roaming / "Claude").exists()


def test_an_autocad_entry_already_there_is_never_replaced_or_removed(tmp_path, fake_claude, no_autocad):
    p = Profile(tmp_path)
    dev = r"D:\work\heron\.venv\Scripts\autocad-mcp.exe"
    # Project folders that differ only in case, which Windows PowerShell's ConvertFrom-Json refuses.
    p.claude_json.write_text(json.dumps({"projects": {"C:/Work": {}, "c:/work": {}},
                                         "mcpServers": {"autocad": {"type": "stdio", "command": dev, "args": []}}}),
                             encoding="utf-8")  # fmt: skip
    config = p.store_app({"mcpServers": {"autocad": {"command": dev}}}, claude_exe=fake_claude)
    before = (p.claude_json.read_bytes(), config.read_bytes())

    done = p.run("-Connect")

    assert done.returncode == 0, done.stdout + done.stderr
    assert f'Claude Code:        already has an "autocad" entry, left as it is: it starts {dev}' in done.stdout
    assert f'Claude Desktop:     already has an "autocad" entry, left as it is: it starts {dev}' in done.stdout
    assert p.calls == []
    assert (p.claude_json.read_bytes(), config.read_bytes()) == before
    assert p.backups() == []

    done = p.run("-Disconnect")

    assert done.stdout.count("not this Heron, so it was kept") == 2, done.stdout
    assert p.calls == []
    assert (p.claude_json.read_bytes(), config.read_bytes()) == before


def test_connecting_twice_adds_the_entry_once(tmp_path, fake_claude, no_autocad):
    p = Profile(tmp_path)
    p.store_app(claude_exe=fake_claude)
    p.run("-Connect")

    done = p.run("-Connect")

    assert "Claude Code:        already connected (all projects)" in done.stdout
    assert "Claude Desktop:     already connected" in done.stdout
    assert len(p.calls) == 1


def test_claude_open_leaves_its_settings_file_alone(tmp_path, fake_claude, no_autocad):
    p = Profile(tmp_path)
    config = p.store_app(claude_exe=fake_claude)
    before = config.read_bytes()

    with open(config.parent / "lockfile", "wb"):  # the running app holds this file
        done = p.run("-Connect")

    assert done.returncode == 0, done.stdout + done.stderr
    assert f"Claude Desktop:     Claude is open, so its settings file was not changed: {config}" in done.stdout
    assert "Quit Claude (right-click its icon by the clock, Quit), then run this again." in done.stdout
    assert config.read_bytes() == before
    assert not (config.parent / "claude_desktop_config.json.heron-backup").exists()
    assert "Claude Code:        connected (all projects)" in done.stdout, "Claude Code's own command still works"


def test_a_dry_run_says_what_it_would_change_and_changes_nothing(tmp_path, fake_claude):
    # No AutoCAD check: a dry run changes nothing, so it may run while AutoCAD is open.
    p = Profile(tmp_path)
    config = p.store_app(claude_exe=fake_claude)
    p.claude_json.write_text('{"projects": {}}', encoding="utf-8")
    before = (p.claude_json.read_bytes(), config.read_bytes())

    done = p.run("-Connect", "-DryRun")

    assert done.returncode == 0, done.stdout + done.stderr
    in_app = next((config.parent / "claude-code").rglob("claude.exe"))
    assert done.stdout.splitlines()[0] == "Dry run: nothing is changed."
    assert (f'Claude Code:        would add "autocad" for all projects: "{in_app}" mcp add --scope user autocad -- '
            f'"{p.server}"') in done.stdout  # fmt: skip
    assert f"after saving {p.claude_json} as .heron-backup" in done.stdout
    assert f'Claude Desktop:     would add "autocad" to {config}, after saving it as .heron-backup' in done.stdout
    assert p.calls == []
    assert (p.claude_json.read_bytes(), config.read_bytes()) == before
    assert p.backups() == []


def test_disconnect_takes_out_only_this_herons_entries(tmp_path, fake_claude, no_autocad):
    p = Profile(tmp_path)
    config = p.store_app({"mcpServers": {"other": {"command": "x"}}}, claude_exe=fake_claude)
    p.run("-Connect")
    connected = config.read_bytes()

    done = p.run("-Disconnect")

    assert done.returncode == 0, done.stdout + done.stderr
    assert p.calls[-1][2].split("|") == ["mcp", "remove", "--scope", "user", "autocad"]
    assert 'Claude Code:        "autocad" entry removed' in done.stdout
    assert json.loads(p.claude_json.read_text(encoding="utf-8"))["mcpServers"] == {}
    assert 'Claude Desktop:     "autocad" entry removed' in done.stdout
    assert json.loads(config.read_text(encoding="utf-8"))["mcpServers"] == {"other": {"command": "x"}}
    assert (config.parent / "claude_desktop_config.json.heron-backup").read_bytes() == connected
