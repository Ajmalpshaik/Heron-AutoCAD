"""Does any file this public repository publishes carry a credential?

    python tools/check_secrets.py

The repository is public: a key that reaches GitHub is published to every
clone at once, and deleting it afterwards does not unpublish it. So CI runs
this on every push and pull request, and a finding fails the build.

Two questions, about every file git tracks:

- THE CONTENTS: a known credential shape (Anthropic, OpenAI, GitHub, AWS,
  Google, Slack keys; a private key block; a password or token typed into a
  config line).
- THE NAME: a file named like a credential (.env, *.pem, *.pfx, id_rsa...).

Exit 0 when nothing is found, 1 with one line per finding (the value itself
is never printed), 2 when it could not look (no git). A 2 is never a pass.

A line that must hold a look-alike on purpose (a test, a doc example) says
``heron-secrets: allow`` on the same line. The idea is from Heron AI for
Revit's tools/check-secrets.py; the code is this repository's own.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOW = "heron-secrets: allow"

SHAPES: dict[str, re.Pattern[str]] = {
    "Anthropic API key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI API key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    "password or token in a config line": re.compile(
        r"""(?ix)\b(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b
            \s*[:=]\s*["']([^"'\s$<>{}()]{8,})["']"""
    ),
}

NAMES = re.compile(
    r"(?i)(^|/)(\.env(\..+)?|.*\.(pem|pfx|p12|key|keystore|jks)|id_(rsa|dsa|ecdsa|ed25519)|\.npmrc|\.pypirc|credentials(\.json)?)$"
)
# Shapes that are templates, not credentials.
EXAMPLE_NAMES = re.compile(r"(?i)\.env\.(example|sample|template)$")


def tracked(root: Path) -> list[str] | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True, timeout=60
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [name for name in out.decode("utf-8", "replace").split("\0") if name]


def scan_text(text: str) -> list[tuple[int, str]]:
    """(line number, what) for every credential shape in a file's text."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if ALLOW in line:
            continue
        for what, shape in SHAPES.items():
            if shape.search(line):
                found.append((number, what))
    return found


def scan(root: Path = ROOT, names: list[str] | None = None) -> list[str] | None:
    names = tracked(root) if names is None else names
    if names is None:
        return None
    problems = []
    for name in names:
        posix = name.replace("\\", "/")
        if NAMES.search(posix) and not EXAMPLE_NAMES.search(posix):
            problems.append(f"{posix}: a file named like a credential is tracked; remove it from git")
        path = root / name
        try:
            data = path.read_bytes()
        except OSError:
            continue  # deleted in the working tree but still in the index
        if b"\0" in data[:8192]:
            continue  # binary: icons, fonts, archives
        for number, what in scan_text(data.decode("utf-8", "replace")):
            problems.append(f"{posix}:{number}: looks like a {what}")
    return problems


def main() -> int:
    problems = scan()
    if problems is None:
        print("secrets: could not list the tracked files (is git installed, is this a checkout?)")
        return 2
    for problem in problems:
        print(problem)
    print("secrets: OK" if not problems else f"secrets: {len(problems)} finding(s). Never push a real key.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
