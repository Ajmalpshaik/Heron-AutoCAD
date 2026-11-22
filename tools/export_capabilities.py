"""The capability manifest a registry such as Heron AI's reads: dist/capabilities.json (D-122).

    python tools/export_capabilities.py
    python tools/export_capabilities.py --out some/other/place.json
    python tools/export_capabilities.py --stdout

Needs no AutoCAD and changes nothing in the repository: it only writes the one file.

Everything in it is worked out from what this repository already holds, so it cannot drift from
the code:

* **The tools** come from the live registry (``mcp.list_tools()``): name, title, summary, the
  ``Use when`` / ``Don't use when`` lines and the input schema, exactly as Claude sees them.
* **The padlock level** of each tool comes from ``core/risk.py``, the one place that owns it.
* **The plug-in each tool needs** comes from reading the tool's own code (Python's ``ast``): a tool
  that reaches ``in_plugin`` / ``plugin_runner`` has the plug-in do part of its work; one that
  reaches only ``faster_read``, ``plugin_read``, the quiet input or a named button uses it when it
  is there; any other tool is only guarded by it. The operation names are checked against the
  plug-in's own list (``PluginOperations.cs``).
* **The proof state** of each tool comes from ``docs/NEEDS-CHECKING.md``: the rows that name the
  tool, and what each one says (PASS, FAIL, NOT RUN, NO MACHINE). A tool no row names is NO ROW.

The file is the same every time for the same code: sorted, no date, no path from this PC.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import importlib.util
import inspect
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PACKAGE = SRC / "autocad_mcp"
REGISTER = ROOT / "docs" / "NEEDS-CHECKING.md"
OPERATIONS = ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "PluginOperations.cs"
PROPS = ROOT / "autocad" / "Directory.Build.props"
OUT = ROOT / "dist" / "capabilities.json"

# Raise this when a field is renamed or removed, so a reader can tell.
MANIFEST_VERSION = 1

# What a tool reaches in its code, and what that says about the plug-in.
DOES_WORK = frozenset({"in_plugin", "plugin_runner"})
WHEN_THERE = frozenset({"faster_read", "plugin_read", "quiet_sender", "quiet_limit", "dialog_expecter", "plugin_version"})
SIGNALS = DOES_WORK | WHEN_THERE
# The gate and the pipe: every tool goes through them, so they say nothing about one tool.
GATE_MODULES = frozenset({"autocad_mcp.core.gate", "autocad_mcp.core.bridge"})
# A tool that looks other tools up by name and runs them: what those need, it needs.
RUNS_TOOLS = "runs other tools"
# Where a table of plug-in operations may live.
TOOL_MODULES = "autocad_mcp.tools."

PROOF_STATES = {
    "PASS": "every row that names the tool passed in a real AutoCAD",
    "PARTLY": "some rows that name the tool passed; the others are not run yet",
    "NOT RUN": "rows name the tool, but none has passed yet",
    "FAIL": "a row that names the tool failed and was not run again since",
    "NO ROW": "no row of the register names the tool: unproven",
}


def _prepare_imports() -> None:
    """The server from this checkout, and off Windows the tests' pywin32 stand-ins (#102)."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    if importlib.util.find_spec("pythoncom") is None:
        sys.path.insert(0, str(ROOT / "tests" / "winstubs"))
        import _ctypes_names  # noqa: F401 - the ctypes names message_filter.py needs


# --------------------------------------------------------------------------
# The plug-in: its version, its operations, and which tools use them
# --------------------------------------------------------------------------


def plugin_version(props: Path = PROPS) -> str:
    """The plug-in version built from this code (autocad/Directory.Build.props owns it)."""
    found = re.search(r"<Version>([^<]+)</Version>", props.read_text(encoding="utf-8"))
    if not found:
        raise SystemExit(f"No <Version> in {props}")
    return found.group(1).strip()


def plugin_operations(source: Path = OPERATIONS) -> dict[str, str]:
    """The operations the plug-in does itself, and the level each needs, from PluginOperations.cs."""
    found = re.findall(r'\["([a-z_]+)"\]\s*=\s*Risk\.(\w+)', source.read_text(encoding="utf-8"))
    return {name: level.lower() for name, level in found}


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class CodeMap:
    """Every module of the server, parsed once: its functions, its constants and its imports."""

    def __init__(self, package: Path = PACKAGE) -> None:
        self.trees: dict[str, ast.Module] = {}
        for path in sorted(package.rglob("*.py")):
            self.trees[_module_name(path)] = ast.parse(path.read_text(encoding="utf-8"))
        self.functions: dict[str, dict[str, ast.AST]] = {}
        self.constants: dict[str, dict[str, ast.AST]] = {}
        self.imports: dict[str, dict[str, tuple[str, str | None]]] = {}
        for module, tree in self.trees.items():
            self.functions[module] = {
                node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            self.constants[module] = {
                target.id: node.value
                for node in tree.body
                if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
                if isinstance(target, ast.Name)
            }
            self.imports[module] = self._imports(module, tree)

    def _is_package(self, module: str) -> bool:
        return (SRC / Path(*module.split("."))).is_dir()

    def _imports(self, module: str, tree: ast.Module) -> dict[str, tuple[str, str | None]]:
        """Local name -> (module, name), with name None when the local name is a whole module."""
        names: dict[str, tuple[str, str | None]] = {}
        here = module.split(".") if self._is_package(module) else module.split(".")[:-1]
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                base = here[: len(here) - (node.level - 1)] if node.level else []
                source = ".".join(base + ([node.module] if node.module else []))
                for alias in node.names:
                    whole = f"{source}.{alias.name}"
                    local = alias.asname or alias.name
                    names[local] = (whole, None) if whole in self.trees else (source, alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.trees:
                        names[alias.asname or alias.name] = (alias.name, None)
        return names

    def _target(self, module: str, node: ast.AST) -> tuple[str, str] | None:
        """The (module, name) a name or a module.attribute in this module stands for."""
        if isinstance(node, ast.Name):
            if node.id in self.functions[module] or node.id in self.constants[module]:
                return module, node.id
            found = self.imports[module].get(node.id)
            if found and found[1] is not None:
                return found[0], found[1]
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            found = self.imports[module].get(node.value.id)
            if found and found[1] is None:
                return found[0], node.attr
        return None

    def reach(self, module: str, name: str) -> tuple[set[str], set[tuple[str, str]]]:
        """What a function reaches: the plug-in calls among SIGNALS, and every function and constant on the way."""
        signals: set[str] = set()
        seen: set[tuple[str, str]] = set()
        todo = [(module, name)]
        while todo:
            where, what = todo.pop()
            if (where, what) in seen or where not in self.trees or where in GATE_MODULES:
                continue
            node = self.functions[where].get(what) or self.constants[where].get(what)
            if node is None:
                continue
            seen.add((where, what))
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and sub.attr == "_tool_manager":
                    signals.add(RUNS_TOOLS)  # looks a tool up by name: autocad_sequence, saved commands
                target = self._target(where, sub)
                if target is None:
                    continue
                if target[1] in SIGNALS:
                    signals.add(target[1])
                else:
                    todo.append(target)
        return signals, seen

    def operation_names(self, seen: set[tuple[str, str]], known: set[str]) -> list[str]:
        """Plug-in operations named in what a tool reaches.

        Only a string given as a call's first argument (``in_plugin("loft", ...)``,
        ``_solid_op("shell", ...)``) or held in a constant of a tool module the tool reads (a
        table of operations), never a keyword's value: ``action="show"`` is not the plug-in's
        ``show``. The core's constants are left out: ``core/risk.py`` lists tool names, and
        some of those are spelt like operations.
        """
        names: set[str] = set()
        for where, what in seen:
            node = self.functions[where].get(what)
            if node is None:
                if not where.startswith(TOOL_MODULES):
                    continue
                node = self.constants[where].get(what)
                strings = (s.value for s in ast.walk(node) if isinstance(s, ast.Constant))
            else:
                strings = (
                    call.args[0].value
                    for call in ast.walk(node)
                    if isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.Constant)
                )
            names.update(s for s in strings if isinstance(s, str) and s in known)
        return sorted(names)


def plugin_use(code: CodeMap, function: Any, known: set[str], release: str) -> dict[str, Any]:
    """What a tool needs of the plug-in, from its own code."""
    from autocad_mcp.core.bridge import READS_SINCE

    original = inspect.unwrap(function)
    signals, seen = code.reach(original.__module__, original.__name__)
    if signals & DOES_WORK:
        role = "operations"
    elif signals & WHEN_THERE:
        role = "when_there"
    else:
        role = "gate"
    use: dict[str, Any] = {
        "role": role,
        "operations": code.operation_names(seen, known) if role != "gate" else [],
        "version_needed": release if role == "operations" else None,
        "runs_other_tools": RUNS_TOOLS in signals,
    }
    if "faster_read" in signals:
        use["faster_from"] = READS_SINCE
    return use


# --------------------------------------------------------------------------
# The proof: docs/NEEDS-CHECKING.md
# --------------------------------------------------------------------------

_ROW = re.compile(r"^\|\s*(?P<id>[A-Z]{1,3}\d+[a-z]?)\s*\|")
_TOOL = re.compile(r"\bautocad_[a-z0-9_]+")
_VERSION = re.compile(r"AutoCAD (20\d\d)")


def row_state(result: str) -> str | None:
    """PASS, FAIL, NOT RUN, NO MACHINE or UNCLEAR for a result cell; None for a removed row.

    "FAIL then PASS" passed in the end; "FAIL then fixed, re-run NOT RUN" has not been run again,
    so it is NOT RUN. Anything else ("Likely PASS") is UNCLEAR, which never counts as a pass.
    """
    text = re.sub(r"[*_`]", "", result).strip().upper()
    if text.startswith("REMOVED"):
        return None
    if text.startswith("NO MACHINE"):
        return "NO MACHINE"
    if text.startswith("NOT RUN") or text.startswith("FAIL THEN FIXED"):
        return "NOT RUN"
    if text.startswith("FAIL THEN PASS") or text.startswith("PASS"):
        return "PASS"
    if text.startswith("FAIL"):
        return "FAIL"
    return "UNCLEAR"


def register_rows(markdown: str) -> Iterator[dict[str, Any]]:
    """Each register row: its id, state, the tools it names and the AutoCAD versions it passed in."""
    group_versions: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            group_versions = _VERSION.findall(line)
            continue
        match = _ROW.match(line.strip())
        if not match:
            continue
        cells = line.strip().strip("|").split("|")
        state = row_state(cells[-1])
        if state is None:
            continue
        passed_in = (_VERSION.findall(cells[-1]) or group_versions) if state == "PASS" else []
        yield {
            "row": match.group("id"),
            "state": state,
            "tools": sorted(set(_TOOL.findall("|".join(cells[1:-1])))),
            "passed_in": sorted(set(passed_in)),
        }


def proof_by_tool(markdown: str, tools: list[str]) -> dict[str, dict[str, Any]]:
    """Every tool's proof state, from the rows that name it."""
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in tools}
    for row in register_rows(markdown):
        for name in row["tools"]:
            if name in rows:
                rows[name].append(row)
    proof: dict[str, dict[str, Any]] = {}
    for name, found in rows.items():
        states = [row["state"] for row in found]
        if not found:
            state = "NO ROW"
        elif "FAIL" in states:
            state = "FAIL"
        elif all(s == "PASS" for s in states):
            state = "PASS"
        elif "PASS" in states:
            state = "PARTLY"
        else:
            state = "NOT RUN"
        proof[name] = {
            "state": state,
            "rows": [{"row": row["row"], "state": row["state"]} for row in found],
            "passed_in": sorted({v for row in found for v in row["passed_in"]}),
        }
    return proof


# --------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------


def _strip(line: str, prefix: str) -> str:
    return line[len(prefix):].strip() if line.startswith(prefix) else line.strip()


def _needs(words: str) -> list[str]:
    """The padlocks a level needs, from the ribbon's words: "Changes + Publish" -> [Changes, Publish]."""
    return [] if words.startswith("none") else [w.strip() for w in words.split("+")]


async def _manifest() -> dict[str, Any]:
    from autocad_mcp import __version__
    from autocad_mcp.acad.findtool import split_bullets
    from autocad_mcp.core.bridge import PROTOCOL_VERSION, READS_SINCE, RUN_SINCE
    from autocad_mcp.core.registry import mcp
    from autocad_mcp.core.risk import Risk, risk_of
    from autocad_mcp.tools import register_all
    from autocad_mcp.tools.resources import _PADLOCK, _summary, _use_when

    register_all()
    tools = sorted(await mcp.list_tools(), key=lambda t: t.name)
    release = plugin_version()
    operations = plugin_operations()
    code = CodeMap()
    proof = proof_by_tool(REGISTER.read_text(encoding="utf-8"), [t.name for t in tools])
    kind = {Risk.READ: "read", Risk.VIEW: "view"}

    rows: list[dict[str, Any]] = []
    for tool in tools:
        level = risk_of(tool.name)
        description = tool.description or ""
        use, avoid = split_bullets(_use_when(description))
        hints = tool.annotations
        rows.append({
            "name": tool.name,
            "title": tool.title or "",
            "summary": _summary(description),
            "padlock": level.value,
            "padlocks_needed": _needs(_PADLOCK[level]),
            "kind": kind.get(level, "change"),
            "hints": {
                "read_only": bool(hints and hints.read_only_hint),
                "destructive": bool(hints and hints.destructive_hint),
                "idempotent": bool(hints and hints.idempotent_hint),
            },
            "use_when": [_strip(line, "Use when:") for line in use],
            "dont_use_when": [_strip(line, "Don't use when:") for line in avoid],
            "inputs": tool.input_schema,
            "plugin": plugin_use(code, mcp._tool_manager.get_tool(tool.name).fn, set(operations), release),
            "proof": proof[tool.name],
        })

    resources = [
        {"uri": str(r.uri), "name": r.name, "description": r.description or ""}
        for r in await mcp.list_resources()
    ] + [
        {"uri": r.uri_template, "name": r.name, "description": r.description or ""}
        for r in await mcp.list_resource_templates()
    ]
    counts = {state: sum(1 for row in rows if row["proof"]["state"] == state) for state in PROOF_STATES}
    order = (Risk.READ, Risk.VIEW, Risk.CHANGE, Risk.PUBLISH, Risk.ADMIN)
    return {
        "manifest": "heron-autocad-capabilities",
        "manifest_version": MANIFEST_VERSION,
        "product": "Heron AI for AutoCAD",
        "server": {
            "name": mcp.name,
            "version": __version__,
            "transport": "MCP over stdio (the default); --transport http serves this PC only, without a login",
            "command": "autocad-mcp",
            "read_only_option": "--read-only offers only the read and view tools",
            "resources": sorted(resources, key=lambda r: r["uri"]),
        },
        "plugin": {
            "version": release,
            "bridge_protocol": PROTOCOL_VERSION,
            "operations": operations,
            "operations_since": RUN_SINCE,
            "faster_reads_since": READS_SINCE,
            "note": (
                "Every tool runs only while the Heron plug-in in AutoCAD is connected: the plug-in "
                "holds the padlocks and says yes or no to each call. version_needed is the plug-in "
                "built from the same code; which earlier plug-in first had each operation is not "
                "recorded. An older plug-in refuses an operation it does not have, and nothing is sent."
            ),
        },
        "padlocks": {
            level.value: {"needs": _needs(_PADLOCK[level]), "words": _PADLOCK[level]} for level in order
        },
        "proof": {
            "register": "docs/NEEDS-CHECKING.md",
            "states": PROOF_STATES,
            "counts": counts,
            "note": (
                "Read from the rows that name a tool. A build or an offline test is not a proof: "
                "only a PASS row, run in a real AutoCAD, is."
            ),
        },
        "count": len(rows),
        "tools": rows,
    }


def build() -> dict[str, Any]:
    """The manifest as a dictionary."""
    _prepare_imports()
    return asyncio.run(_manifest())


def render(manifest: dict[str, Any]) -> str:
    """The manifest as text: sorted keys, two-space indent, one newline at the end."""
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(build()))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the capability manifest a registry reads (D-122).")
    parser.add_argument("--out", type=Path, default=OUT, help="Where to write it (default dist/capabilities.json).")
    parser.add_argument("--stdout", action="store_true", help="Print it instead of writing a file.")
    args = parser.parse_args(argv)
    if args.stdout:
        sys.stdout.write(render(build()))
        return 0
    path = write(args.out)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    counts = ", ".join(f"{n} {state}" for state, n in manifest["proof"]["counts"].items())
    print(f"{manifest['count']} tools written to {path} ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
