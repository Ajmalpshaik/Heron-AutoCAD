# Project map

**The fastest orientation in this repository**: which folder owns what, where a change starts, and
which source wins when two disagree. For *which document covers what*, use [README.md](README.md).

---

## A. How a request travels

```mermaid
flowchart TD
    U(["<b>The modeller</b><br/><i>draw a 5000 x 3000 rectangle</i>"])
    C["<b>Claude</b> (Code or Desktop)<br/>decides which tool to call"]
    T["<b>src/autocad_mcp/tools/</b><br/>the autocad_* tools"]
    G["<b>core/gate.py</b><br/>level, wrong-drawing guard, audit"]
    B["<b>core/bridge.py</b><br/>finds this AutoCAD's pipe"]
    P["<b>autocad/Heron.AutoCAD.Bridge</b><br/>token, hold, padlocks"]
    H["<b>autocad/Heron.AutoCAD.Addin</b><br/>banner, command line, Keep or Discard"]
    K["<b>core/connection.py</b><br/>one COM worker thread"]
    D(["<b>The open drawing</b><br/>one call = one undo step"])

    U --> C -->|"MCP (stdio)"| T --> G
    G -->|"begin / end / ask_keep"| B -->|"named pipe, this user only"| P --> H
    G -->|"allowed"| K -->|"pywin32 COM"| D
```

## B. Folders

| Folder | Owns | Start a change at |
|---|---|---|
| [`src/autocad_mcp/`](../src/autocad_mcp/README.md) | The MCP server | `tools/<subject>.py` for a tool; `core/gate.py` for the gate |
| [`autocad/`](../autocad/README.md) | The plug-in (C#) | `Heron.AutoCAD.Bridge` for rules, `Heron.AutoCAD.Addin` for what is seen |
| `drawings/` | Earlier drawing packages, **local only, not in git** | |
| [`tools/`](../tools/README.md) | Build, install, smoke test, structure check | |
| [`tests/`](../tests/README.md) | Python tests | `test_gate.py`, `test_bridge.py` |
| [`docs/`](README.md) | All documentation | This file |
| [`examples/`](../examples/README.md) | Claude Desktop config | |
| [`archive/`](../archive/README.md) | Stopped experiments | Do not build on it |
| `dist/` | The built `HeronAutoCAD.bundle` and `capabilities.json`, **not in git** | `tools/build_plugin.py`, `tools/export_capabilities.py` |
| `.github/` | CI, issue and pull-request templates | `workflows/ci.yml` |

## C. Entry points

| What | Command |
|---|---|
| Run the server (stdio, as Claude does) | `.venv\Scripts\autocad-mcp.exe` |
| List tools without AutoCAD | `.venv\Scripts\autocad-mcp.exe --list-tools` |
| Only reading tools | `.venv\Scripts\autocad-mcp.exe --read-only` |
| Build the plug-in bundle | `.venv\Scripts\python.exe tools/build_plugin.py` |
| Install / remove it (AutoCAD closed) | `.venv\Scripts\python.exe tools/install_plugin.py [--uninstall]` |
| Repository rules | `.venv\Scripts\python.exe tools/check_structure.py` |
| The capability manifest for a registry (Heron AI) | `.venv\Scripts\python.exe tools/export_capabilities.py` |
| Build the release zip, then the one-file setup | `.venv\Scripts\python.exe tools/make_release.py`, then `tools/make_installer.py` (Windows; [tools/README](../tools/README.md)) |
| No credential in any tracked file (CI) | `.venv\Scripts\python.exe tools/check_secrets.py` |
| Live smoke test | `.venv\Scripts\python.exe tools/smoke_test.py` |
| Offline tests | `.venv\Scripts\python.exe -m pytest -m "not live"` and `dotnet test autocad/Heron.AutoCAD.Bridge.Tests` |

## D. Configuration files

| File | For |
|---|---|
| [`.mcp.json`](../.mcp.json) | Claude Code: registers the `autocad` server when opened in this folder |
| [`.codex/config.toml`](../.codex/config.toml) | Codex: the same server |
| [`examples/claude_desktop_config.json`](../examples/claude_desktop_config.json) | Claude Desktop |
| [`pyproject.toml`](../pyproject.toml) | Package, dependencies, pytest and ruff |
| [`autocad/Directory.Build.props`](../autocad/Directory.Build.props) | Version and shared C# settings |
| `%APPDATA%\Heron\autocad\heron-autocad.config` | The banner only; the padlocks live in AutoCAD's memory ([D-59](DECISIONS.md)) and AutoCAD never connects at start ([D-73](DECISIONS.md)) |
| [`.claude/settings.json`](../.claude/settings.json), [`.claude/hooks/guard_padlocks.py`](../.claude/hooks/guard_padlocks.py) | Claude Code guard: refuses writing that file or the Heron policy key |

The three MCP configs hold the absolute path of `.venv\Scripts\autocad-mcp.exe`; if the repository
moves, change all three.

## E. Which source wins

1. **The code and the tool output.** `--list-tools` beats any table in these docs.
2. **The tests**, and for anything live, a PASS row in [NEEDS-CHECKING](NEEDS-CHECKING.md).
3. [DECISIONS.md](DECISIONS.md) for *why*.
4. The numbered docs.
5. [HANDOVER.md](HANDOVER.md) last: it is a work note.
