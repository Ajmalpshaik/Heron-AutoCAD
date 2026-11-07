# autocad - Heron for AutoCAD (the plug-in)

C# solution [`Heron.AutoCAD.sln`](Heron.AutoCAD.sln). What it looks like to the modeller:
[docs/06-heron-plugin.md](../docs/06-heron-plugin.md).

| Project | Job | References AutoCAD? |
|---|---|---|
| `Heron.AutoCAD.Bridge` | Pipe server, session token, address file, padlock rules, one-chat hold, the protocol; the list of the plug-in's own operations and their pure rules (edge and face words, the super hatch tile grid) | **No** - tested offline |
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
| `HeronCommands.cs` | `HERON`, `HERONSTATUS`, `HERONCHANGES`, `HERONPUBLISH`, `HERONADMIN`, `HERONASKTOKEEP` |
| `AcadJobHost.cs` | Bridge -> AutoCAD: banner, command-line line, select and zoom, Keep box, operations |
| `PluginRunner.cs` | The plug-in's own operations ([D-40](../docs/DECISIONS.md)): right drawing, document lock, one transaction, refusals that say "Nothing was changed." |
| `SolidOperations.cs` | Loft, fillet / chamfer edges, shell, press-pull, thicken, and the numbered faces and edges (Brep) |
| `SuperHatch.cs` | A block tiled in a grid, inserted once and clipped to an outline like XCLIP |
| `RenderSetup.cs` | Photometric lights and materials made from their settings ([D-42](../docs/DECISIONS.md)) |
| `IdleQueue.cs` | Gets pipe-thread work onto AutoCAD's main thread through `Application.Idle` |
| `UndoSwitch.cs` | Undo recording off while a read runs, back on after, with safety nets (rules: `Bridge/UndoPause.cs`, [D-34](../docs/DECISIONS.md)) |
| `HeronActivityBanner.cs` | The READING / CHANGING / DONE / STOPPED card, on its own thread |
| `HeronStatusWindow.cs`, `HeronKeepQuestion.cs`, `HeronUi.cs` | The two windows and their shared look |
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
