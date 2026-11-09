# AGENTS.md - for an AI agent working on Heron AI for AutoCAD

**Read this first. It is short on purpose.** It points at the file that owns each detail instead of
repeating it.

> **Asked to draw something in AutoCAD, rather than change this project? Stop reading here.** Use
> the `autocad_*` MCP tools. Call `autocad_status` first: it gives the drawing units and says
> whether AutoCAD is connected to Heron. If a tool is refused, pass the refusal on in plain words
> (press Heron, turn on the Changes padlock); **never try to get round it**. If no `autocad_` tool is
> listed at all, the server is not running: point at [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
> and stop.

---

## What this project is

**Heron AI for AutoCAD**: a C# plug-in inside AutoCAD (connect button, padlocks, banner) and a Python
MCP server that does the work over COM, but only after asking the plug-in. The owner is a BIM / MEP
modeller, not a developer: explain in plain words and confirm before anything that changes GitHub.

It is a **separate repository from Heron AI for Revit** (`D:\06_Development\03_Heron\Heron Ai`), in
the same family. Never edit Heron from here; copy its ideas, not its files (the icon PNGs were copied
once, read only).

## Reading order

1. This file.
2. [README.md](README.md).
3. [docs/PROJECT-MAP.md](docs/PROJECT-MAP.md): folders, entry points, which source wins.
4. The **README of the folder you are changing**.
5. [docs/05-known-limits.md](docs/05-known-limits.md): the traps already found.
6. [docs/HANDOVER.md](docs/HANDOVER.md), only if you are continuing unfinished work.

## Never

- **Never claim the plug-in works in a version without a PASS row in
  [NEEDS-CHECKING](docs/NEEDS-CHECKING.md).** A build is not a proof; a passing offline test is not
  a proof. Live in that AutoCAD, or it is NOT RUN.
- **Never bypass the gate.** Every tool goes through `tool_errors` -> `core/gate.py`. Never call COM
  from a tool without it, never default a padlock to on, never add a tool without a level in
  `core/risk.py` (a test and `tools/check_structure.py` both fail).
- **Never put `Autodesk.AutoCAD` / `Autodesk.Windows` outside `autocad/Heron.AutoCAD.Addin/`.**
  `tools/check_structure.py` fails the build.
- **Never run `pip install -e .` while an `autocad-mcp` server is running**
  ([05 §1](docs/05-known-limits.md#1-reinstalling-while-the-server-runs)).
- **Never drive AutoCAD from two sessions at once.**
- **Never send an AutoLISP expression near 3,600 characters**; keep chunks under about 700.
  `autocad_run_lisp` refuses anything over 2,000 ([05 §3](docs/05-known-limits.md#3-long-autolisp-fails-silently)).
- **Never draw parts as loose lines or fake a leader**: [07 drafting rules](docs/07-drafting-rules.md).
- **Never copy Lee Mac's code into this public repository**: ideas only, re-implemented and credited ([D-26](docs/DECISIONS.md), [08](docs/08-lee-mac-study.md)).
- **Never draw before `autocad_status` on that drawing.** It gives the units; the gate refuses changes until it has run ([D-19](docs/DECISIONS.md)).
- **Never claim a drawing is right without `autocad_preview`.**
- **Never add a tool without a `Use when:` line.** Every tool carries an `Examples:` section
  whose bullets say, in the words a draftsman would use, when to reach for it — and a
  `Don't use when:` naming the better tool where there is one. `tests/test_tool_index.py`
  fails without it. With over a hundred tools, one that cannot be found does not exist.
- **Never edit a test until it passes.**

## How to work

Inspect before you edit. Make the smallest safe change; record anything else in
[docs/ROADMAP.md](docs/ROADMAP.md). Run the gates before claiming anything:

```bash
.venv\Scripts\python.exe -m ruff check .
```

```bash
.venv\Scripts\python.exe -m pytest -m "not live"
```

```bash
dotnet test autocad/Heron.AutoCAD.Bridge.Tests
```

```bash
.venv\Scripts\python.exe tools/check_structure.py
```

Record a real choice in [docs/DECISIONS.md](docs/DECISIONS.md). Update
[docs/HANDOVER.md](docs/HANDOVER.md) before you stop.
