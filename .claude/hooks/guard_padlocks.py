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
        return None

    if tool in SHELL_TOOLS:
        command = tool_input.get("command")
        if not isinstance(command, str):
            return None
        if CONFIG.search(command) and FILE_WRITE.search(command):
            return REFUSED.format(what="heron-autocad.config")
        if POLICY.search(command) and REGISTRY_WRITE.search(command):
            return REFUSED.format(what="the Heron policy key in the Windows registry")
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
