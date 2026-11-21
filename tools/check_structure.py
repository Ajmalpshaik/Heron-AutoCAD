"""The repository rules, checked from disk. CI runs this on every push.

    python tools/check_structure.py

1. The AutoCAD .NET API (Autodesk.AutoCAD / Autodesk.Windows) appears only in
   autocad/Heron.AutoCAD.Addin. The bridge stays testable without AutoCAD.
2. Every registered tool has exactly one risk level (src/autocad_mcp/core/risk.py),
   so no tool can slip past the padlocks.
3. Every relative link in the Markdown docs points at a file that exists.
4. The tool count docs/SETUP.md tells the reader to expect is the real one.

Exit code 0 when all hold, 1 with one line per problem otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _windows_stand_ins() -> None:
    """Off Windows, where pywin32 cannot install: the tests' stand-ins, so the tool rules can be read (#102)."""
    import importlib.util

    if importlib.util.find_spec("pythoncom") is None:
        sys.path.insert(0, str(ROOT / "tests" / "winstubs"))
        import _ctypes_names  # noqa: F401 - the ctypes names message_filter.py needs


_windows_stand_ins()
# .claude holds the padlock guard (settings.json, hooks/, D-59), which has no Markdown,
# C# or tools, and Claude's local folders: in the main checkout other sessions'
# worktrees, whole copies of this repository. Its tracked files are tested by
# tests/test_padlock_guard.py.
SKIP_DIRS = {".venv", ".venv.broken", ".git", "bin", "obj", "dist", ".superpowers", "node_modules", ".pytest_cache", ".ruff_cache", ".claude"}
_API = re.compile(r"\bAutodesk\.(AutoCAD|Windows)\b")
_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _files(root: Path, pattern: str):
    for path in root.rglob(pattern):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts):
            yield path


def autocad_api_outside_addin(root: Path) -> list[str]:
    addin = root / "autocad" / "Heron.AutoCAD.Addin"
    problems = []
    for path in _files(root, "*.cs"):
        if addin in path.parents:
            continue
        if _API.search(path.read_text(encoding="utf-8", errors="replace")):
            problems.append(f"{path.relative_to(root)}: uses the AutoCAD API outside Heron.AutoCAD.Addin")
    return problems


def tools_without_level() -> list[str]:
    sys.path.insert(0, str(ROOT / "src"))
    import asyncio

    from autocad_mcp.core.registry import mcp
    from autocad_mcp.core.risk import _LEVELS, RISK
    from autocad_mcp.tools import register_all

    register_all()
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    # A name under two levels would silently take the later one: two merged PRs can do that.
    levels: dict[str, list[str]] = {}
    for level, listed in _LEVELS.items():
        for name in listed:
            levels.setdefault(name, []).append(level.value)
    twice = [
        f"core/risk.py lists autocad_{name} under {' and '.join(found)}: give it one level"
        for name, found in sorted(levels.items())
        if len(found) > 1
    ]
    return twice + [f"tool {name} has no risk level in core/risk.py" for name in sorted(names - set(RISK))] + [
        f"core/risk.py lists {name}, which is not a registered tool" for name in sorted(set(RISK) - names)
    ]


def broken_links(root: Path) -> list[str]:
    problems = []
    for path in _files(root, "*.md"):
        for match in _LINK.finditer(path.read_text(encoding="utf-8", errors="replace")):
            target = match.group(1)
            if re.match(r"^[a-z]+:", target):
                continue
            if not (path.parent / target).exists():
                problems.append(f"{path.relative_to(root)}: broken link to {target}")
    return problems


def stale_tool_count(root: Path = ROOT) -> list[str]:
    """docs/SETUP.md tells the reader how many tools to expect. It must be true.

    It has gone stale twice - a reader who sees a smaller number than the
    install prints concludes the install is broken, which is the worst kind of
    wrong documentation.
    """
    setup = root / "docs" / "SETUP.md"
    if not setup.exists():
        return []
    sys.path.insert(0, str(root / "src"))
    import asyncio

    from autocad_mcp.core.registry import mcp
    from autocad_mcp.tools import register_all

    register_all()
    real = len(asyncio.run(mcp.list_tools()))
    text = setup.read_text(encoding="utf-8")
    claimed = [int(n) for n in re.findall(r"You should see (\d+) tools", text)]
    return [
        f"docs/SETUP.md says {n} tools; the server registers {real}"
        for n in claimed
        if n != real
    ]


def run_all(root: Path = ROOT) -> list[str]:
    return (
        autocad_api_outside_addin(root)
        + tools_without_level()
        + broken_links(root)
        + stale_tool_count(root)
    )


def main() -> int:
    problems = run_all()
    for line in problems:
        print(line)
    print("structure: OK" if not problems else f"structure: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
