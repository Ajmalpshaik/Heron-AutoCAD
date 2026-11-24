# Heron AI for AutoCAD - Documentation index

> **Status, 2026-11-24:** the server passes its offline tests and the plug-in builds for AutoCAD
> 2021-2027. **Only AutoCAD 2027 has been checked live**, and only for the rows marked PASS in
> [NEEDS-CHECKING](NEEDS-CHECKING.md) (most of group A, a few rows of D, J and L). The first
> GitHub release (v1.8.0) installs and its plug-in loads in AutoCAD 2027 (v1.8.1 fixed its Claude connection, #233; v1.9.0 carries the fixes and plug-in reads made since, none of them run in AutoCAD yet); most of its tools are not
> yet checked in AutoCAD. AutoCAD
> 2021-2026 have no machine yet (groups B and C). The README's install table says the same per piece.
> Where work stopped: [HANDOVER](HANDOVER.md).
>
> Counts typed on these pages go stale. Derive them: `.venv\Scripts\autocad-mcp.exe --list-tools`
> for tools, `pytest --collect-only -q` and `dotnet test --list-tests` for tests.

## Which document do I read?

| You are | Start with | Then |
|---|---|---|
| **The owner** | [HANDOVER](HANDOVER.md) | [NEEDS-CHECKING](NEEDS-CHECKING.md), [ROADMAP](ROADMAP.md) |
| **A modeller** | [INSTALL](INSTALL.md), then [06 - The Heron plug-in](06-heron-plugin.md) | [TOOL-CATALOGUE](TOOL-CATALOGUE.md) |
| **Changing the code** | [PROJECT-MAP](PROJECT-MAP.md) | [02 - Architecture](02-architecture.md), [CONTRIBUTING](../CONTRIBUTING.md) |
| **An AI agent** | [AGENTS.md](../AGENTS.md) | [PROJECT-MAP](PROJECT-MAP.md) |

## The numbered set

| No. | Document | Owns |
|---|---|---|
| 01 | [Overview and principles](01-overview.md) | What it is for, what it will never do |
| 02 | [Architecture](02-architecture.md) | How a request reaches AutoCAD; the gate; Python vs AutoLISP; COM rules |
| 03 | [Tools reference](03-tools-reference.md) | Every `autocad_*` tool and its level; resources; prompts; start options |
| 05 | [Known limits and traps](05-known-limits.md) | What broke before, and the fix |
| 06 | [The Heron plug-in](06-heron-plugin.md) | Ribbon, padlocks, banner, Keep or Discard, the bridge protocol |
| 07 | [Drafting rules](07-drafting-rules.md) | How every drawing is set out: blocks, TLD labels, aligned views, preview check |
| 08 | [Lee Mac study](08-lee-mac-study.md) | His licence, which ideas became Heron tools, what comes next |
| 10 | [Complex geometry, annotation and 3D](10-geometry-annotation-3d.md) | The shape library, dimension runs, multileaders, tables, revision clouds, solids, booleans, 3D views |
| 11 | [ADN-DevTech repositories study](11-adn-repos-study.md) | Autodesk's AutoCAD sample repositories: licences, what was built from them, what was left out |
| 09 | [Sheets, coordinates and shop drawings](09-sheets-and-coordinates.md) | The UCS, saved locations, layouts, title blocks, viewports, drawing settings, an import into a shop drawing, `autocad_sequence` |
| 12 | [AutoCAD ribbon coverage](12-autocad-ribbon-coverage.md) | Every default ribbon panel: what Heron covers, what is missing, whether COM or .NET can do it, a priority; the top 10 gaps |
| 13 | [Moving tools into the plug-in](13-moving-tools-into-the-plug-in.md) | Which tools gain most from the plug-in (round trips, big reads, one transaction), what each risks, which session area owns it; what moved first ([D-114](DECISIONS.md)) |
| 14 | [Heron AI's AutoCAD side](14-heron-ai-adapter.md) | How Heron AI for Revit would call this server, the capability manifest (`tools/export_capabilities.py`), what Heron still needs, the steps when its registry is ready ([D-122](DECISIONS.md)) |
| 15 | [Attribute sheets, folder checks, the Companion page](15-sheets-folders-companion.md) | Attributes out to Excel and back (only the changed cells), a check list over a folder of drawings read only, and the Companion page beside AutoCAD |

## Registers and working pages

| Page | What it is |
|---|---|
| [NEEDS-CHECKING](NEEDS-CHECKING.md) | Every live check, PASS / FAIL / NOT RUN / NO MACHINE per AutoCAD version |
| [DECISIONS](DECISIONS.md) | Every real choice, with the reason. Append-only |
| [HANDOVER](HANDOVER.md) | Where the last session stopped and what is next |
| [ROADMAP](ROADMAP.md) | Ideas and known gaps, not yet started |
| [INSTALL](INSTALL.md) | For a modeller: download, check, install, connect Claude, first use, update, uninstall |
| [TOOL-CATALOGUE](TOOL-CATALOGUE.md) | Every tool in plain words, grouped by job: what to ask, which padlock, the result, its live-proof state. Made by `tools/make_tool_catalogue.py`; do not edit by hand |
| [SETUP](SETUP.md), [TROUBLESHOOTING](TROUBLESHOOTING.md) | Build from source, and every error with its fix |
| [PROJECT-MAP](PROJECT-MAP.md) | Folders, entry points, which source wins |
| [Design spec](superpowers/specs/2026-10-26-heron-autocad-design.md), [plan](superpowers/plans/2026-10-26-heron-autocad.md) | How Heron for AutoCAD was designed and built |
| [CHANGELOG](../CHANGELOG.md) | What changed, newest first |
