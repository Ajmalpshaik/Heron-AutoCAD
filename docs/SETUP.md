# Setup

Step by step, from nothing to Claude drawing in your AutoCAD.

---

## 1. Check you can run this

| Requirement | Why | How to check |
|---|---|---|
| Windows | COM Automation is Windows-only | — |
| Full AutoCAD, 2015+ | LT has no ActiveX/COM Automation interface — see below | Help → About |
| Python 3.10+ | | `python --version` |

**About AutoCAD LT.** LT 2024+ for Windows does run AutoLISP internally — the
old "LT can't run LISP" line is out of date. But that is LISP running *inside*
LT. This server is an *external* process attaching to AutoCAD over ActiveX/COM,
and Autodesk does not ship ActiveX with LT: there is no `AutoCAD.Application`
COM server to attach to. So the server cannot drive LT at any version, on
Windows or Mac. That is a limitation of LT, not of this project.

Launch AutoCAD normally once before first use. AutoCAD registers its COM
interface on first run, and until it has, nothing can connect to it.

---

## 2. Install

From the project folder:

```bash
uv venv --python 3.11
```

```bash
uv pip install -e .
```

If you do not have `uv`, plain pip works the same way:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\pip install -e .
```

---

## 3. Check the server itself

This lists the tools without touching AutoCAD, so it isolates install problems
from connection problems:

```bash
.venv\Scripts\autocad-mcp.exe --list-tools
```

You should see 126 tools. If this fails, the problem is the install.

---

## 4. Check it can reach AutoCAD

Open AutoCAD with any drawing, then:

```bash
.venv\Scripts\python.exe tools/smoke_test.py
```

This creates its own scratch drawing and exercises every tool in it — it never
touches the drawing you already had open. Expect `55/55 checks passed`, then
close the scratch drawing without saving.

If this fails but step 3 passed, the problem is the AutoCAD connection. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## 4b. Install the Heron plug-in

Heron AI for AutoCAD needs its plug-in inside AutoCAD; without it every tool says AutoCAD is not
connected. Build it (needs the .NET SDK), close AutoCAD, install, start AutoCAD:

```bash
.venv\Scripts\python.exe tools/build_plugin.py
```

```bash
.venv\Scripts\python.exe tools/install_plugin.py
```

The **Heron** tab appears on the ribbon. Press **Heron** to connect; turn on **Changes** when you want
Heron to draw. What every button does: [06](06-heron-plugin.md).

## 5. Connect Claude

### Claude Code

```bash
claude mcp add autocad -- "D:\Ajmal\AutoCAD APP\Autocad MCP\.venv\Scripts\autocad-mcp.exe"
```

Confirm it connected:

```bash
claude mcp list
```

### Claude Desktop

1. Open `%APPDATA%\Claude\claude_desktop_config.json`. Create it if it does not
   exist.
2. Add the `autocad` entry — see
   [`examples/claude_desktop_config.json`](../examples/claude_desktop_config.json).
   Note that every backslash in a Windows path must be **doubled** in JSON.
3. **Quit Claude Desktop completely** — right-click its system tray icon and
   choose Quit. Closing the window is not enough; the old process keeps running
   and will not reload the config.
4. Reopen it. The AutoCAD tools appear under the tools icon in the chat box.

---

## 6. First conversation

Ask Claude:

> Check the AutoCAD connection and tell me what's open.

If it reports your drawing name, units and layer count, everything works.

A good habit: always let Claude run `autocad_status` first in a session.
Coordinates are in the drawing's own units, and that call is how Claude learns
whether `5000` means 5 metres or 5 kilometres.

---

## Running over the network

To let Claude on another machine drive AutoCAD on this one:

```bash
.venv\Scripts\autocad-mcp.exe --transport http --host 0.0.0.0 --port 8000
```

The client connects to `http://<this-machine>:8000/mcp`.

There is no authentication and the tools can modify and delete drawing
content. Only do this on a network you trust, and prefer binding to a specific
interface over `0.0.0.0`.

---

## Updating

The install is editable (`-e`), so edits to files under `src/` take effect on
the next server start. After changing anything, restart Claude Desktop or run
`claude mcp restart autocad` so it picks up the new code.
