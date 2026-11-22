# autocad - Heron for AutoCAD (the plug-in)

C# solution [`Heron.AutoCAD.sln`](Heron.AutoCAD.sln). What it looks like to the modeller:
[docs/06-heron-plugin.md](../docs/06-heron-plugin.md).

| Project | Job | References AutoCAD? |
|---|---|---|
| `Heron.AutoCAD.Bridge` | Pipe server, session token, address file, padlock rules, the padlocks in memory and the Windows policy that can hold one off (`HeronPadlocks.cs`, `HeronPolicy.cs`, [D-59, D-60](../docs/DECISIONS.md)), one-chat hold, the protocol; the drawing events log (`DrawingEvents.cs`, [D-98](../docs/DECISIONS.md)); the list of the plug-in's own operations and their pure rules (edge and face words, the super hatch tile grid, the multileader and table style words in `StylePlans.cs`, [D-104](../docs/DECISIONS.md)) | **No** - tested offline |
| `Heron.AutoCAD.Bridge.Tests` | xUnit tests, including the real Python client against the real server | No |
| `Heron.AutoCAD.Addin` | Ribbon, commands, banner, Bridge Status, Keep or Discard, main-thread queue, the plug-in's own operations (3D edits, super hatch) | **Yes - the only one** |

Every project builds three ways: `net48` (AutoCAD 2021-2024), `net8.0-windows` (2025-2026),
`net10.0-windows` (2027). The AutoCAD DLLs come from Autodesk's `AutoCAD.NET` NuGet packages
(24.0.0 / 25.0.1 / 26.0.0) as reference only; AutoCAD supplies them at run time.

| File in the add-in | Owns |
|---|---|
| `HeronApplication.cs` | Load / unload; starts disconnected |
| `HeronActions.cs` | What the buttons and commands do; padlock confirmations |
| `HeronRibbon.cs` | Tab Heron, panel AI Bridge, icons, rebuild on workspace change |
| `HeronCommands.cs` | `HERON`, `HERONSTATUS`, `HERONPALETTE`, `HERONCHANGES`, `HERONPUBLISH`, `HERONADMIN`, `HERONASKTOKEEP` |
| `AcadJobHost.cs` | Bridge -> AutoCAD: banner, command-line line, select and zoom, Keep box, operations |
| `PluginRunner.cs` | The plug-in's own operations ([D-40](../docs/DECISIONS.md)): right drawing, document lock, one transaction, refusals that say "Nothing was changed." |
| `SolidOperations.cs` | Loft, fillet / chamfer edges, shell, press-pull, thicken, and the numbered faces and edges (Brep) |
| `SuperHatch.cs` | A block, an image, an xref or a wipeout tiled in a grid, inserted once and clipped to an outline like XCLIP |
| `Sections.cs` | Flat views of solids (FLATSHOT) and a section plane with its 2D section, both through AutoCAD's Section object (D-95; maths in `Bridge/SectionMath.cs`) |
| `Surfaces.cs` | Loft to a surface, planar and network surfaces, MESH primitives and a mesh made from a solid (D-95) |
| `DrawingStyles.cs` | Multileader and table styles from a `Bridge/StylePlans.cs` plan, read back as AutoCAD holds them (D-104) |
| `LayerStates.cs` | Named layer states: save, restore (with every layer it changed), delete, list (D-81) |
| `DimensionLines.cs` | Where a linear or aligned dimension's line is, and moving it, for even spacing (D-80) |
| `AnnotationScales.cs` | Annotative objects: the drawing's scale list, an object's scales, adding and removing them (D-81) |
| `AssociativeArrays.cs` | ARRAY's associative path, grid and ring array, checked against `Bridge/ArrayPlan.cs` before it is kept (D-110) |
| `GeoLocation.cs` | The drawing's geographic location (GeoLocationData), proved with AutoCAD's own transform; the checks are `Bridge/GeoPlace.cs` (D-111) |
| `RenderSetup.cs` | Photometric lights and materials made from their settings ([D-42](../docs/DECISIONS.md)) |
| `References.cs` | PDF / DWF / DGN underlays attached; an xref, block or underlay clipped; the files a drawing needs for eTransmit, found with AutoCAD's own search ([D-84](../docs/DECISIONS.md), [D-85](../docs/DECISIONS.md)) |
| `Boundary.cs` | BOUNDARY without typing it: `Editor.TraceBoundary`, zoomed to a window, objects counted first ([D-84](../docs/DECISIONS.md)) |
| `IdleQueue.cs` | Gets pipe-thread work onto AutoCAD's main thread through `Application.Idle` |
| `DrawingWatch.cs` | AutoCAD's document events (opened, came to the front, saved, closed) into the drawing events log, as they happen ([D-98](../docs/DECISIONS.md)) |
| `UndoSwitch.cs` | Undo recording off while a read runs, back on after, with safety nets (rules: `Bridge/UndoPause.cs`, [D-34](../docs/DECISIONS.md)) |
| `HeronActivityBanner.cs` | The READING / CHANGING / DONE / STOPPED card, on its own thread |
| `HeronStatusWindow.cs`, `HeronKeepQuestion.cs`, `HeronUi.cs` | The two windows and their shared look |
| `HeronPalette.cs` | The docked Heron palette ([D-68](../docs/DECISIONS.md)): Activity (Select, Zoom, Undo, with the drawing events live, D-98) and Saved commands (Run through the server). Rules: `Bridge/ActivityLog.cs`, `Bridge/PaletteRows.cs`, `Bridge/SavedCommandList.cs`, `Bridge/PaletteServer.cs`, words in `Bridge/PaletteTexts.cs` |
| `Resources/*.png` | Icons copied from Heron AI for Revit |

```bash
dotnet build autocad/Heron.AutoCAD.sln -c Release
```

```bash
dotnet test autocad/Heron.AutoCAD.Bridge.Tests
```

Bundle and install: [`tools/build_plugin.py`](../tools/build_plugin.py),
[`tools/install_plugin.py`](../tools/install_plugin.py).

**Rules:** the AutoCAD API stays in the add-in (`tools/check_structure.py` fails otherwise). Never
touch the AutoCAD API from a pipe thread: queue it through `IdleQueue`, and lock the document for
anything that changes it. Every text the chat sees lives in `Heron.AutoCAD.Bridge/Texts.cs`.
