"""Heron's padlock guard for Claude Code working in this repository (D-59, D-60).

A PreToolUse hook (.claude/settings.json). It refuses an Edit, Write or shell
command that would write:

- heron-autocad.config, the file where an older plug-in kept the padlocks, or
- the Windows policy key HKLM\\SOFTWARE\\Policies\\Heron\\AutoCAD, which is the
  PC administrator's, not a chat's.

This is the second guard, not the first. Since D-59 the padlocks live in
AutoCAD's memory and no file can turn one on, and HKLM needs administrator
rights. The guard catches the plain ways a chat could try anyway; it cannot
catch every way, so it never replaces the rule in the plug-in.

Reads the hook's JSON on stdin. Exit 2 refuses (the reason goes to Claude on
stderr); exit 0 lets the step go ahead. Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CONFIG = re.compile(r"heron-autocad\.config", re.IGNORECASE)
# Any slashes between the parts: Policies\Heron, Policies\\Heron, Policies/Heron.
POLICY = re.compile(r"policies[\\/]+heron\b", re.IGNORECASE)

# A command that writes, moves, deletes or unlocks a file.
FILE_WRITE = re.compile(
    r"(?<![-=0-9>])>{1,2}(?![>&])(?!\s*(/dev/null|nul\b|\$null))"  # > or >> into a file
    r"|\b(tee|cp|mv|rm|del|erase|copy|move|ren|rename|xcopy|robocopy|truncate|touch|ln|dd"
    r"|attrib|icacls|takeown|chmod|chown|unlink)\b"
    r"|\b(sed|perl)\b[^|;&]*\s-i"
    r"|\b(set|add|clear)-content\b|\bout-file\b"
    r"|\b(new|remove|copy|move|rename|set)-item\b"
    r"|\[(system\.)?io\.file\]::|\bfile\.(write|append|replace|copy|move|delete|create)"
    r"|\bwrite_(text|bytes)\b|\bjson\.dump\b|\.write\(|\bopen\(",
    re.IGNORECASE,
)

# A command that writes or deletes a registry value or key.
REGISTRY_WRITE = re.compile(
    r"\breg(\.exe)?\s+(add|delete|import|copy|restore|load|unload)\b"
    r"|\bregedit\b|\bregini\b"
    r"|\b(set|new|remove|rename|clear|copy|move)-item(property)?\b"
    r"|\.(setvalue|createsubkey|deletevalue|deletesubkey|deletesubkeytree)\b"
    r"|\bwinreg\b",
    re.IGNORECASE,
)

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}

# A file a shell or interpreter runs: written now, it could write a target later (#142).
SCRIPTS = (".ps1", ".psm1", ".bat", ".cmd", ".vbs", ".js", ".py", ".sh")
REPOSITORY = Path(__file__).resolve().parents[2]
# This repository's own tests and this guard name the targets on purpose.
OWN = (REPOSITORY / "tests", REPOSITORY / ".claude" / "hooks")

# Commands whose quoted values are messages (an issue, a commit), not file contents (#142).
MESSAGE_COMMANDS = re.compile(r"^\s*(?:\w+=\S*\s+)*(gh|git)\b")

REFUSED = (
    "Heron's padlock guard refused this step: it would write {what}. "
    "The padlocks are turned on only by the modeller's click in Settings on the Heron tab in "
    "AutoCAD, and only the PC's administrator sets the Heron policy (docs/DECISIONS.md D-59, D-60). "
    "Do not try another way. If you only meant to read or mention it, do that without writing to it."
)


def _texts(tool_input: dict) -> list[str]:
    """Everything an edit would put in the file."""
    texts = [tool_input.get(key) for key in ("content", "new_string", "new_source")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            texts.append(edit.get("new_string"))
    return [text for text in texts if isinstance(text, str)]


def _unquoted(command: str) -> str:
    """The command with what is inside its quotes left out: a message, not a write."""
    out, quote, i = [], None, 0
    while i < len(command):
        char = command[i]
        if quote is None:
            if char in "'\"":
                quote = char
            else:
                out.append(char)
        elif char == "\\" and quote == '"':
            i += 1  # an escaped character inside double quotes stays inside them
        elif char == quote:
            quote = None
        i += 1
    return "".join(out)


def _own(path: str) -> bool:
    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError):
        return False
    return any(folder == resolved or folder in resolved.parents for folder in OWN)


def _writes_a_target(text: str) -> str | None:
    """What a command or script would write, or None."""
    if CONFIG.search(text) and FILE_WRITE.search(text):
        return "heron-autocad.config"
    if POLICY.search(text) and REGISTRY_WRITE.search(text):
        return "the Heron policy key in the Windows registry"
    return None


def refusal(event: dict) -> str | None:
    """Why this step is refused, or None to let it go ahead."""
    tool = event.get("tool_name")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None

    if tool in FILE_TOOLS:
        path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
        name = re.split(r"[\\/]", path)[-1]
        if name.lower() == "heron-autocad.config":
            return REFUSED.format(what="heron-autocad.config")
        if name.lower().endswith(".reg") and any(POLICY.search(text) for text in _texts(tool_input)):
            return REFUSED.format(what="a .reg file for the Heron policy key")
        if name.lower().endswith(SCRIPTS) and not _own(path):
            for text in _texts(tool_input):
                what = _writes_a_target(text)
                if what:
                    return REFUSED.format(what="a script that would write " + what)
        return None

    if tool in SHELL_TOOLS:
        command = tool_input.get("command")
        if not isinstance(command, str):
            return None
        if MESSAGE_COMMANDS.match(command):
            command = _unquoted(command)
        what = _writes_a_target(command)
        if what:
            return REFUSED.format(what=what)
    return None


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(event, dict):
        return 0
    reason = refusal(event)
    if reason is None:
        return 0
    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
