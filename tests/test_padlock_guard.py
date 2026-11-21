"""The padlock guard hook for Claude Code in this repository (D-59, D-60).

.claude/hooks/guard_padlocks.py refuses an Edit, Write or shell command that
would write heron-autocad.config or the Heron policy key. These run the hook
as Claude Code does: JSON on stdin, exit 2 to refuse, the reason on stderr.
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
HOOK = ROOT / ".claude" / "hooks" / "guard_padlocks.py"
SETTINGS = ROOT / ".claude" / "settings.json"
CONFIG = r"C:\Users\ajmal\AppData\Roaming\Heron\autocad\heron-autocad.config"


def run(tool: str, **tool_input) -> subprocess.CompletedProcess:
    event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True, timeout=30
    )


def refused(tool: str, **tool_input) -> bool:
    result = run(tool, **tool_input)
    assert result.returncode in (0, 2), result.stderr
    if result.returncode == 2:
        assert "padlock guard refused" in result.stderr
    return result.returncode == 2


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_no_edit_of_the_config_file(tool):
    assert refused(tool, file_path=CONFIG, content='{"write.enabled": true}', new_string="true")
    assert refused(tool, file_path="/home/x/.config/HERON-AUTOCAD.CONFIG", content="{}")


def test_ordinary_files_may_be_edited_even_when_they_name_the_file():
    # The docs and tests of this repository name the file; that is not writing it.
    assert not refused("Edit", file_path=str(ROOT / "docs" / "06-heron-plugin.md"),
                       old_string="a", new_string="heron-autocad.config is ignored")  # fmt: skip
    assert not refused("Write", file_path=str(ROOT / "docs" / "x.md"),
                       content=r"HKLM\SOFTWARE\Policies\Heron\AutoCAD, AllowChanges = 0")  # fmt: skip


def test_no_reg_file_for_the_policy_key():
    content = "Windows Registry Editor Version 5.00\n\n[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Heron\\AutoCAD]\n"
    assert refused("Write", file_path=r"C:\temp\heron.reg", content=content)
    assert not refused("Write", file_path=r"C:\temp\other.reg", content="[HKEY_CURRENT_USER\\Software\\Other]\n")


@pytest.mark.parametrize(
    "command",
    [
        f'echo {{"write.enabled": true}} > "{CONFIG}"',
        'echo x >> "$APPDATA/Heron/autocad/heron-autocad.config"',
        "cp evil.json ~/AppData/Roaming/Heron/autocad/heron-autocad.config",
        "rm heron-autocad.config",
        "sed -i 's/false/true/' heron-autocad.config",
        "Set-Content $env:APPDATA\\Heron\\autocad\\heron-autocad.config '{}'",
        "python -c \"open('heron-autocad.config','w').write('{}')\"",
        "[IO.File]::WriteAllText('heron-autocad.config', '{}')",
        "attrib -r heron-autocad.config",
    ],
)
def test_no_shell_write_to_the_config_file(command):
    assert refused("Bash", command=command)
    assert refused("PowerShell", command=command)


@pytest.mark.parametrize(
    "command",
    [
        r"reg add HKLM\SOFTWARE\Policies\Heron\AutoCAD /v AllowChanges /t REG_DWORD /d 1 /f",
        r"reg.exe delete HKLM\SOFTWARE\Policies\Heron\AutoCAD /f",
        r'reg add "HKLM\\SOFTWARE\\Policies\\Heron\\AutoCAD" /v AllowAdmin /d 1',
        r"Set-ItemProperty -Path HKLM:\SOFTWARE\Policies\Heron\AutoCAD -Name AllowPublish -Value 1",
        r"Remove-Item HKLM:/SOFTWARE/Policies/Heron -Recurse",
        r"python -c \"import winreg; winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, 'SOFTWARE\\Policies\\Heron\\AutoCAD')\"",
    ],
)
def test_no_shell_write_to_the_policy_key(command):
    assert refused("Bash", command=command)


@pytest.mark.parametrize(
    "command",
    [
        "grep -rn heron-autocad.config docs",
        "cat heron-autocad.config 2>/dev/null",
        "type heron-autocad.config 2>&1",
        r"reg query HKLM\SOFTWARE\Policies\Heron\AutoCAD",
        "git log --oneline -5",
        "echo hello > out.txt",
        "python -m pytest -q",
    ],
)
def test_reading_and_everything_else_goes_ahead(command):
    assert not refused("Bash", command=command)


def test_other_tools_and_bad_input_go_ahead():
    assert not refused("Read", file_path=CONFIG)
    result = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, timeout=30)
    assert result.returncode == 0


def test_settings_run_the_guard_before_edits_and_commands():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    (entry,) = settings["hooks"]["PreToolUse"]
    for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "PowerShell"):
        assert tool in entry["matcher"].split("|")
    (hook,) = entry["hooks"]
    assert ".claude/hooks/guard_padlocks.py" in hook["command"]


# On Windows, "bash" on PATH can be WSL's rather than Git Bash's, so this runs off Windows only.
@pytest.mark.skipif(sys.platform == "win32" or shutil.which("bash") is None, reason="needs a plain bash")
def test_the_settings_command_refuses_through_bash():
    # The command exactly as Claude Code runs it, with this repository as the project.
    command = json.loads(SETTINGS.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT))
    for tool_input, code in (({"command": "rm heron-autocad.config"}, 2), ({"command": "ls"}, 0)):
        event = json.dumps({"tool_name": "Bash", "tool_input": tool_input})
        result = subprocess.run(["bash", "-c", command], input=event, capture_output=True, text=True, timeout=60, env=env)
        assert result.returncode == code, result.stderr
