# 11 - ADN-DevTech repositories study

On 2026-11-04, Ajmal asked for six Autodesk Developer Network repositories to be read and anything
useful made part of Heron. This page is the record: licence, what was read, what is worth taking,
what was left out and why. **Nothing here is built yet** - every item is on the
[ROADMAP](ROADMAP.md), and per [AGENTS.md](../AGENTS.md) nothing is called working until a PASS
row exists in [NEEDS-CHECKING](NEEDS-CHECKING.md).

## Licences

| Repository | Licence | Use |
|---|---|---|
| [acad-api-skill](https://github.com/ADN-DevTech/acad-api-skill) | MIT | Ideas and facts may be used; credit it |
| [acad-memory-leak-skill](https://github.com/ADN-DevTech/acad-memory-leak-skill) | MIT | Read only; C++ only, not for Heron |
| [AutoCAD-Net-Wizards](https://github.com/ADN-DevTech/AutoCAD-Net-Wizards) | MIT-style (Autodesk, Cyrille Fauvel) | Not needed; a Visual Studio template |
| [autocad-automation-apps](https://github.com/ADN-DevTech/autocad-automation-apps) | No licence file found | **Ideas only, no code copied** |
| [acad-com-events-external-monitor](https://github.com/ADN-DevTech/acad-com-events-external-monitor) | No licence file; README says "demonstration project for educational purposes" | **Ideas only, no code copied** |
| [RevitTrainingMaterial](https://github.com/ADN-DevTech/RevitTrainingMaterial) | MIT (Jeremy Tammik) | Revit training labs, not for this project |

No licence file means no permission to copy. Heron is public and MIT, so anything taken is written
fresh from the AutoCAD API, as with [08](08-lee-mac-study.md). The code that was read has no network
calls, no encoded strings and no credentials; only the cloud scripts (`Setup-DA.ps1`) use APS keys,
and they are not used here.

## Already covered by Heron (nothing to take)

- Three builds from one source, `EnableDynamicLoading`, `ExcludeAssets="runtime"`, x64, no
  `RuntimeIdentifier`: `Heron.AutoCAD.Addin.csproj` already does all of it.
- The `.bundle` in `ApplicationPlugins` with `SeriesMin` / `SeriesMax` per build:
  `tools/build_plugin.py`.
- SECURELOAD: Heron sends LISP as typed expressions and never loads a file
  ([D-21](DECISIONS.md)). The repos' advice to set `SECURELOAD 0` is the thing Heron rejected.
- Xref attach / reload / bind: `src/autocad_mcp/tools/xrefs.py`.
- Text, block and attribute extraction: the take-off tools ([08](08-lee-mac-study.md)).

## Worth taking (on the roadmap)

| # | Idea | From | Why it helps a BIM / MEP modeller |
|---|---|---|---|
| 1 | **Publish a folder of drawings to one multi-sheet PDF** (DSD file + the Publisher, all layouts, one call). Heron plots one layout at a time today. | autocad-automation-apps `BatchPublishApp` | A whole package issued in one go |
| 2 | **Plot through the plot engine in the plug-in** instead of `PlotToFile`, which fails on 2027 ([05 §5](05-known-limits.md#5-pdf-on-autocad-2027)). The API facts are verified for 2027 in the skill: `PlotSettingsValidator.Current` (no constructor), `MatchingPolicy.MatchEnabled`, `BeginPage(PlotPageInfo, PlotInfo, ...)`, `PlotFactory.CreatePublishEngine()`. | acad-api-skill `autocad-api.md` | Removes the layout-first workaround |
| 3 | **Xref tree report**: the whole hierarchy of a drawing (found name, saved path, resolved or not), read only. Heron has attach and manage, but no way to list the tree. | autocad-automation-apps `XrefTraverserApp` (uses `GetHostDwgXrefGraph`) | Finds broken xref paths before issue |
| 4 | **Drawing audit dump**: layers, blocks, styles, units in one read-only call. | autocad-automation-apps `DumpDwgApp` | Quick standards check on a received drawing |
| 5 | **Headless test route** (`accoreconsole` with `/al` and `/isolate`) for checks that do not need the ribbon. The add-in uses WPF and `AcMgd`, so it cannot run there; only a Core-only helper could. | acad-api-skill, automation-apps | Offline proof of read-only helpers |
| 6 | **Autodesk Help MCP server** (`https://developer.api.autodesk.com/knowledge/public/v1/mcp`): lets an agent look up official AutoCAD help while building tools. Dev-time aid, not a Heron feature. Not added to the shipped config. | acad-api-skill | Fewer wrong API guesses |
| 7 | **Document events as a drawing-switch signal** (CommandStarted / Ended, DocumentActivated, LockModeChanged) for the wrong-drawing guard and the activity list. The add-in is already inside AutoCAD, so it can subscribe directly; the repo's separate COM service is not needed. | acad-com-events-external-monitor | Companion page, ROADMAP "Plug-in" |
| 8 | **`AssemblyMappings`** in `PackageContents.xml`: only if a dependent DLL in `Contents/R2x` ever fails to resolve. Documented for Design Automation; not proven for desktop. | automation-apps `SKILLS.md` | Fallback fix, no action now |

## Left out, with the reason

- **Civil 3D and Plant 3D skills, templates** (`civil3d-api.md`, `plant3d-api.md`, `templates/civil`):
  Heron drives plain AutoCAD. Revisit if Plant 3D piping becomes a target.
- **APS Design Automation** (cloud workitems, OSS upload, engine tables, `Setup-DA.ps1`): needs APS
  credentials and cloud billing, and Heron's design is "the modeller's own AutoCAD, behind
  padlocks". Not a fit.
- **acad-memory-leak-skill**: C++ ObjectARX / RealDWG leak hunting with ETW. Heron has no C++.
- **AutoCAD-Net-Wizards**: a Visual Studio project template. Heron is built from its own solution.
- **External COM event monitor**: `regasm` registration with admin rights, a .NET Framework 4.8
  `ServicedComponent`, a second process attached to AutoCAD. That is the opposite of Heron's
  padlock design ([05 §11](05-known-limits.md#11-com-is-still-open-to-other-programs)). Idea 7
  above takes only the event list.
- **RevitTrainingMaterial**: Revit API labs (C# and VB, `.docx` instructions, slides). Useful for
  the Revit tools (Heron AI), not this repository.
- **learnings.md pattern** (append-only log, human promotes): Heron already does this with
  NEEDS-CHECKING and DECISIONS.

## What was read, and what was not

Read in full: every `.md` / `.mdc` in the five AutoCAD repositories except the Civil 3D and
Plant 3D skills (skimmed headings only), the three C# command files in `autocad-automation-apps`,
the plug-in entry of the events monitor, the project template `ClassName.cs`, and the Revit
`README.md` and licence. **Not read:** the Revit lab `.cs` files (about 9,000 lines), the `.docx`
instructions and slides, the C++ and VB sources, and the PowerShell cloud scripts. None of them
bears on the AutoCAD plug-in.
