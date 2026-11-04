# 11 - ADN-DevTech repositories study

On 2026-11-04, Ajmal asked for Autodesk Developer Network's AutoCAD sample repositories to be read
and everything useful made part of Heron. This page is the record: licence, what was read, what
was built, what was left out and why. Decision: [D-41](DECISIONS.md). Built items are **NOT RUN**
in AutoCAD until their rows in [NEEDS-CHECKING group I](NEEDS-CHECKING.md) pass.

## Licences

| Repository | Licence | Use |
|---|---|---|
| [acad-api-skill](https://github.com/ADN-DevTech/acad-api-skill) | MIT | Ideas and facts; credited here |
| [acad-memory-leak-skill](https://github.com/ADN-DevTech/acad-memory-leak-skill) | MIT | The measuring method only; its tools are C++ |
| [AutoCAD-Net-Wizards](https://github.com/ADN-DevTech/AutoCAD-Net-Wizards) | MIT-style (Autodesk, Cyrille Fauvel) | Not needed; a Visual Studio template |
| [autocad-automation-apps](https://github.com/ADN-DevTech/autocad-automation-apps) | No licence file | **Ideas only, no code copied** |
| [acad-com-events-external-monitor](https://github.com/ADN-DevTech/acad-com-events-external-monitor) | No licence file; README says "for educational purposes" | **Ideas only, no code copied** |

No licence means no permission to copy. Heron is public and MIT, so everything below is written
fresh from the AutoCAD API, as with [08](08-lee-mac-study.md).

## Built (2026-11-04)

| # | What | Heron now has | From |
|---|---|---|---|
| 1 | **Several sheets in one PDF** | `autocad_publish_pdf`: a plug-in operation through AutoCAD's publisher (a DSD list, `SheetType.MultiPdf`), Publish padlock | `autocad-automation-apps` BatchPublish |
| 3 | **Xref tree with broken paths** | `autocad_xref_tree`: nested xrefs, saved path, file found, loaded / unloaded / not found | XrefTraverser |
| 4 | **Audit of a received drawing** | `autocad_drawing_report`: units, layers off / frozen / locked, blocks, xrefs, styles, sheets, counts | DumpDwg |
| 9 | **Why AutoCAD is busy** | The add-in follows command and LISP events (`CommandWatch`, `CommandTracker`); "did not get to the request" names the command | events monitor |
| 10 | **Memory over a working day** | `tools/memory_check.py`: Private Bytes before and after 100 rounds of reads; pass within 10 % | memory-leak skill |
| 11 | **Plant 3D objects** | Known limit [05 §20](05-known-limits.md#20-the-tools-from-the-adn-devtech-study-have-their-own-limits): LISP cannot change them | `plant3d-api.md` |
| 6 | **Autodesk Help MCP server** | Named in [CONTRIBUTING](../CONTRIBUTING.md) for development; not shipped | `autocad-api.md` |

Kept from BatchPublish, and one thing **not** copied:
- BACKGROUNDPLOT goes to 0 for the run, and Heron puts it back (the sample never does).
- In the DSD, `PromptForDwfName=FALSE` stops the file box; `InitLayouts=TRUE` under
  `[PublishOptions]` sets up never-opened sheets, which otherwise print blank.
- The sample renames the user's drawings to strip spaces and moves the first PDF it finds. Heron
  never renames or moves a modeller's files.

## Not built, with the reason

| # | Idea | Why not (yet) |
|---|---|---|
| 2 | Plot through the plot engine instead of `PlotToFile` | `autocad_export`'s route works on 2027 and is pinned by tests ([D-04](DECISIONS.md)); the publisher already covers several sheets. The verified 2027 signatures are kept here in case: `PlotSettingsValidator.Current`, `MatchingPolicy.MatchEnabled`, `BeginPage(PlotPageInfo, PlotInfo, ...)`, `PlotFactory.CreatePublishEngine()` |
| 5 | Headless tests with `accoreconsole /al ... /isolate` | The add-in uses WPF and `AcMgd`, which accoreconsole cannot load |
| 7 | Document events for the wrong-drawing guard and a Companion page | On the [ROADMAP](ROADMAP.md); the event hooks are now in place (`CommandWatch`) |
| 8 | `AssemblyMappings` in `PackageContents.xml` | Only if a DLL ever fails to resolve; documented for Design Automation, not desktop |
| - | A folder of drawings in one PDF | On the [ROADMAP](ROADMAP.md); this drawing's own sheets first |

## Already covered by Heron (nothing to take)

- Three builds from one source, `EnableDynamicLoading`, `ExcludeAssets="runtime"`, x64, no
  `RuntimeIdentifier`: `Heron.AutoCAD.Addin.csproj`.
- The `.bundle` in `ApplicationPlugins` with `SeriesMin` / `SeriesMax` per build:
  `tools/build_plugin.py`.
- SECURELOAD: Heron sends LISP as typed expressions and never loads a file
  ([D-21](DECISIONS.md)). The samples' advice to set `SECURELOAD 0` is what Heron rejected.
- Xref attach / reload / bind: `autocad_attach_xref`, `autocad_manage_xref`.
- Text extraction (`TextExtract.lsp`): `autocad_count_text`, `autocad_find_text`.
- Command and LISP-function templates from the wizards: the add-in has its own entry point.

## Left out, with the reason

- **Civil 3D and Plant 3D skills and templates:** Heron drives plain AutoCAD. Only the Plant 3D
  limit above was kept.
- **APS Design Automation** (cloud workitems, uploads, engine tables, `Setup-DA.ps1`): needs APS
  credentials and cloud billing; Heron works in the modeller's own AutoCAD, behind padlocks.
- **acad-memory-leak-skill's C++ tools** (ETW traces, WPA, ARX repro): Heron has no C++. Its first,
  no-admin level is item 10.
- **The external COM event monitor itself:** `regasm` as administrator, a .NET Framework 4.8
  `ServicedComponent`, a second process attached to AutoCAD - the opposite of Heron's padlocks
  ([05 §11](05-known-limits.md#11-com-is-still-open-to-other-programs)). Only its event list was used.
- **The learnings.md pattern:** Heron already does this with NEEDS-CHECKING and DECISIONS.

## What was read

In full: every `.md` / `.mdc` in the five repositories (Civil 3D and Plant 3D skills included),
every `.cs` file (the events monitor's add-in, console and sink; XrefTraverser; BatchPublish; the
acad and civil templates; the wizard template) and `TextExtract.lsp`. The PowerShell, batch and
Python scripts were searched for network calls, encoded strings, `eval`, registry writes and file
deletes: only calls to Autodesk's APS cloud (their purpose), a local Ollama test, and deletes of
each script's own temporary output. Nothing hidden. **Not read:** the C++ and VB sources and the
sample drawings; C++ and VB have no place in Heron.
