# 14 - Heron AI for AutoCAD as Heron AI's AutoCAD side

> **Status, 2026-11-22:** this side is ready to be offered; Heron AI's capability registry is not
> built yet, so nothing connects the two. Issue #75 stays open until it is ([D-12](DECISIONS.md),
> [D-122](DECISIONS.md)). **Nothing in Heron AI was changed, and nothing here may change it**
> ([AGENTS.md](../AGENTS.md): copy its ideas, not its files).

Heron AI for Revit is a separate, private repository. D-12 says that when its **capability
registry** is ready (one list of what each platform can do), this repository is offered as its
AutoCAD side. This page says what Heron would need to do that, what this repository now gives it,
what is still missing on Heron's side, and the steps to take when the registry is ready.

## 1. How Heron AI would call AutoCAD

The same way Claude does. Nothing new is needed on this side to be called.

| Piece | What it is | Where it is decided |
|---|---|---|
| **The endpoint** | The MCP server `autocad-mcp`, over stdio. The release installs it at `%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe`. `--transport http` serves this PC only by default and has no login, so never widen it to an open network | [03 Start options](03-tools-reference.md#start-options), [SETUP](SETUP.md) |
| **The gate** | Every tool goes through `core/gate.py`, which asks the Heron plug-in in AutoCAD before and after each call. A call made from Heron AI is guarded exactly as one made from Claude | [D-14](DECISIONS.md), [02](02-architecture.md) |
| **The padlocks** | Changes, Publish and Admin live in AutoCAD's own memory and are turned on only in Heron's Settings window in AutoCAD. Heron AI for Revit does not hold them and cannot turn them on. A refused call is passed on in plain words, never worked round | [D-59](DECISIONS.md), [06](06-heron-plugin.md) |
| **The first call** | `autocad_status`: it gives the drawing units, and the gate refuses every change until it has run on that drawing | [D-19](DECISIONS.md) |
| **Finding a tool** | `autocad://tools` (the whole list) and `autocad://tools/find/{phrase}` (plain words). Neither needs AutoCAD | [03 Resources](03-tools-reference.md#resources-and-prompts) |
| **Only reading** | `--read-only` offers only the Read and View tools | [03 Start options](03-tools-reference.md#start-options) |

So the gate and the padlocks **stay in the AutoCAD plug-in**. Heron AI would be one more caller
of the same server, never a second way into AutoCAD.

## 2. The capability manifest

A registry needs more than the MCP tool list: it needs to know which padlock each tool needs and
which tools have been **proven in a real AutoCAD**. One command writes that into one file:

```bash
python tools/export_capabilities.py
```

It writes `dist/capabilities.json` (`--out` for another place, `--stdout` to print it). It needs no
AutoCAD. `dist/` is not kept in git, so the file is made fresh from the code, and every release zip
carries it as `capabilities.json` (`tools/make_release.py`). For the same code it is the same file,
byte for byte: sorted, no date, no path from the PC that made it.

Each tool's entry:

| Field | What it says | Taken from |
|---|---|---|
| `name`, `title`, `summary` | The tool as Claude sees it | The live registry |
| `use_when`, `dont_use_when` | The tool's own `Use when:` / `Don't use when:` lines | The tool's docstring |
| `inputs` | The JSON schema of its arguments | The live registry |
| `padlock`, `padlocks_needed` | `read`, `view`, `change`, `publish`, `admin`, and the padlocks that level needs (`["Changes", "Publish"]`) | `core/risk.py` |
| `kind` | `read`, `view` (the screen or which drawing is open), or `change` (needs the Changes padlock) | `core/risk.py` |
| `hints` | MCP's read-only, destructive and idempotent hints | The tool's declaration |
| `plugin.role` | `gate`: the plug-in only guards the call and COM does the work. `operations`: the plug-in does some of the work, for some options at least. `when_there`: COM does it, and the plug-in is used when it is there (faster reads, quiet input, a box's button) | The tool's own code |
| `plugin.operations` | The plug-in's own operations the tool asks for, each checked against `PluginOperations.cs` | The tool's own code |
| `plugin.version_needed` | For `operations`: the plug-in built from the same code. Empty for the others: any connected plug-in | `autocad/Directory.Build.props` |
| `plugin.faster_from` | For a read the plug-in does faster: from which plug-in on | `READS_SINCE` in `core/bridge.py`; left out for a read in `NEWER_READS`, whose release is not named yet ([D-127](DECISIONS.md), [D-134](DECISIONS.md), [D-138](DECISIONS.md), [D-145](DECISIONS.md), [D-146](DECISIONS.md)) |
| `plugin.runs_other_tools` | True for `autocad_sequence` and `autocad_saved_command`: what their steps need, they need | The tool's own code |
| `proof.state` | **PASS** (every row naming it passed), **PARTLY** (some did, the rest are not run), **NOT RUN**, **FAIL** (a row failed and was not run again), **NO ROW** (no row names it) | [NEEDS-CHECKING](NEEDS-CHECKING.md) |
| `proof.rows`, `proof.passed_in` | Each row and its state; the AutoCAD versions it passed in | [NEEDS-CHECKING](NEEDS-CHECKING.md) |

The top of the file says which server and plug-in versions it describes, the bridge protocol, every
plug-in operation with its level, the resources, and how many tools are in each proof state.

**What it cannot say, on purpose:**

- **A tool is proven only by a row that names it.** The first rows of group A say "draw a line" in
  words, so `autocad_draw_line` is not counted as proven even though those rows passed. That is
  the safe way round: a tool is never called proven on a guess. The fix is to name the tool in the
  row (`` `autocad_draw_line` ``) when it is next run.
- **Which plug-in release first had each operation is not recorded.** `version_needed` is the
  plug-in built from the same code, which surely has them. An older plug-in refuses an operation it
  does not have, and nothing is sent.
- **A tool that runs other tools** (`autocad_sequence`, `autocad_saved_command`) is listed as
  `gate`; the tools in its steps say what they need.

On 2026-11-22 it listed 199 tools: 5 PASS, 14 PARTLY, 1 FAIL, 150 NOT RUN, 29 NO ROW. Run it for
today's numbers; numbers typed here go stale.

## 3. What is still missing on Heron AI's side

None of this can be done from here; each is for a session working in Heron AI's own repository.

1. **The capability registry itself**, and its format.
2. **A way to start or reach another platform's MCP server** and send it a request: here,
   `autocad-mcp` on the same PC.
3. **A rule for proof states.** For example, offer only PASS and PARTLY tools, or every tool with a
   warning on the unproven ones. That is Heron's choice, made with Ajmal.
4. **Its own padlock words mapped to these levels** (`read`, `view`, `change`, `publish`, `admin`),
   and a plain sentence for the modeller that AutoCAD's padlocks are set in AutoCAD, not in Revit.
5. **Where to find the server** on a PC: the release installs it at
   `%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe`.

## 4. When Heron's registry is ready

1. Read Heron AI's registry format in its own repository, **read only**.
2. Run `tools/export_capabilities.py` and compare its fields with what the registry wants. A field
   the registry needs and the manifest lacks is added here; a field renamed or removed raises
   `manifest_version`.
3. If the registry wants a live answer instead of a file, add an `autocad://capabilities`
   resource that answers with the same manifest. That is new runtime behaviour, so it gets its
   own decision and live rows.
4. In Heron AI's repository, in its own session: add the AutoCAD entry that starts `autocad-mcp`
   and reads the manifest.
5. On a PC with both products, add live rows to [NEEDS-CHECKING](NEEDS-CHECKING.md), NOT RUN until
   run: Heron AI lists the AutoCAD tools from the manifest; a Revit chat calls `autocad_status`;
   a draw with Changes off is refused, naming Changes.
6. Close #75 when Heron AI's registry lists these tools (its "Done when" line).

## 5. What this side will not do

- Edit Heron AI's repository, or copy its files ([AGENTS.md](../AGENTS.md), [D-12](DECISIONS.md)).
- Move the gate or a padlock out of the AutoCAD plug-in, or give Heron AI a way round them
  ([D-14](DECISIONS.md), [D-59](DECISIONS.md)).
- Call a tool proven because the manifest lists it: only a PASS row in
  [NEEDS-CHECKING](NEEDS-CHECKING.md) proves it.
