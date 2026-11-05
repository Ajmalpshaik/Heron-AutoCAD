# Contributing

This is a public, single-owner repository. Ideas and corrections are welcome through an Issue. These
are the house rules for any change, by a person or an AI agent.

## Before you change anything

1. Read [AGENTS.md](AGENTS.md) and [docs/PROJECT-MAP.md](docs/PROJECT-MAP.md).
2. Read the README of the folder you are changing.
3. Check [docs/05-known-limits.md](docs/05-known-limits.md) for the trap you are about to step in.

## Branches and commits

- `main` is always working. Do larger work on a branch: `feature/<name>`, `fix/<name>`, `docs/<name>`.
- One subject per commit. Write the message as what the change does: *"Fit PDF export to A1 paper"*.
- Never commit `.venv/`, drawings, AutoCAD `.bak` / `.dwl` files, or anything
  with a password, key or real client detail in it.
  [.gitignore](.gitignore) covers the usual ones.

## The gates

Run both before every push:

```bash
.venv\Scripts\python.exe -m ruff check .
```

```bash
.venv\Scripts\python.exe -m pytest -m "not live"
```

And for the plug-in and the repository rules:

```bash
dotnet test autocad/Heron.AutoCAD.Bridge.Tests
```

```bash
.venv\Scripts\python.exe tools/check_structure.py
```

The same run on GitHub for every push ([.github/workflows/ci.yml](.github/workflows/ci.yml)).
GitHub has no AutoCAD, so **live tests run only on your PC**, with AutoCAD open:

```bash
.venv\Scripts\python.exe -m pytest -m live
```

```bash
.venv\Scripts\python.exe tools/smoke_test.py
```

## Adding a tool

1. Put it in the matching file in [`src/autocad_mcp/tools/`](src/autocad_mcp/tools/), wearing `@tool_errors` (that is what puts it behind the Heron gate).
1. Give it a level in [`src/autocad_mcp/core/risk.py`](src/autocad_mcp/core/risk.py). Without one, a test and `tools/check_structure.py` fail.
2. Keep the layer rule: `tools` -> `acad` -> `core`, never upward.
3. Add an offline test in [`tests/test_offline.py`](tests/test_offline.py) and, if it changes the
   drawing, a live one in [`tests/test_live.py`](tests/test_live.py).
4. Add it to [docs/03-tools-reference.md](docs/03-tools-reference.md) and the count in the README.
5. Add a line to [CHANGELOG.md](CHANGELOG.md).


## Changing the plug-in

1. Rules and texts go in `autocad/Heron.AutoCAD.Bridge` (testable); only what is seen goes in the add-in.
2. Never touch the AutoCAD API from a pipe thread: use `IdleQueue`, and lock the document to change it.
3. Build all three targets: `dotnet build autocad/Heron.AutoCAD.sln -c Release`.
4. A change to what the modeller sees adds or updates a row in [docs/NEEDS-CHECKING.md](docs/NEEDS-CHECKING.md).

## Looking up the AutoCAD API

Before inventing an API call, look it up: the [.NET Developer's Guide](https://help.autodesk.com/view/OARX/2027/ENU/)
and the ActiveX reference have working examples. An AI agent can search Autodesk's help itself
through Autodesk's public **Help MCP server**, `https://developer.api.autodesk.com/knowledge/public/v1/mcp`
(from the [ADN study](docs/11-adn-repos-study.md), item 6). Add it to your own agent's settings
for development only; it is not part of Heron and Heron's shipped configs do not include it.
