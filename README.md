# Heron AI for AutoCAD

> **Dear Modelers - please do not install this yet.**
>
> This repository is public so the work is open, but it is not finished. The plug-in inside AutoCAD
> still has to pass its live checks ([NEEDS-CHECKING](docs/NEEDS-CHECKING.md)). I will announce it
> when it is ready to install.
>
> **Programmers and AI engineers: your thoughts are welcome.** Read the code and share suggestions
> or corrections through an Issue.

**Let a chat work in your AutoCAD - only when you connect it, and only as far as your padlocks allow.**

> The modeller focuses on the drawing. Heron does the AutoCAD work behind it.

Heron AI for AutoCAD is the AutoCAD member of the [Heron AI](https://github.com/Ajmalpshaik/Heron-AI)
family. Same name, same ribbon, same padlocks, same "Heron AI is changing your drawing" banner: a
modeller who knows Heron in Revit knows it here.

---

## What it is

You describe the work in plain language; Claude does it in the AutoCAD you already have open:

```
"Check the connection and tell me what's open."
"Draw a 5000 x 3000 rectangle at the origin on layer A-WALL, in red."
"Check this drawing against our layer standard."
"Make me a camera schedule from the CAM blocks."
"Put sheet E-101 on A1 with our title block, ground floor at 1:100."
"This IFC came in on IfcWall, IfcDuct... make it a shop drawing."
"My UCS is rotated 23 degrees - draw it square to that."
"Draw a 200 flange, 8 holes on a 160 PCD."
"Give me the flat pattern for that 200 to 100 reducer."
"Dimension these grid lines, with the overall above."
"Extrude this outline 200 up and cut the bolt holes out."
"Show me what you drew."
```

Geometry appears live, every change is **one undo step**, and nothing reaches AutoCAD until you
press **Heron** on the ribbon.

## What you see in AutoCAD

Ribbon tab **Heron**, panel **AI Bridge**, laid out as in Heron for Revit:

| Button | What it does |
|---|---|
| **Heron** | black heron: no chat can see this AutoCAD; orange heron: a chat can reach it. The arrow holds **Bridge Status** and **Free this AutoCAD** |
| **Settings** | one window with the four switches below, each with its padlock picture and an ON / OFF button |

| Switch in Settings | Off (safe) | On |
|---|---|---|
| **Changes** | Heron can only read and look | red ON: Heron may draw, modify and delete |
| **Admin** | no commands or AutoLISP | red ON: Heron may run commands, AutoLISP, system variables |
| **Publish** | Heron may not save or export | red ON: Heron may save, export, plot |
| **Ask to Keep** | changes are kept at once | green ON: after each change, **Keep it / Discard it** |

While Heron works, Heron for Revit's status bar slides down at the top of AutoCAD: a glass card
saying **"Heron AI · Reading"** or **"Heron AI · Changing"** (orange, with the drawing, the job and the
time), then **Done** (green) or **Needs attention** (red). Every Heron window uses Revit's dark Heron
style. The command line keeps a line such as `Heron: Draw Line. Done in 0.4 s`.

Everything starts **off**. Turning a padlock on asks first; turning it off never asks. The same
switches are commands: `HERON`, `HERONSTATUS`, `HERONFREE`, `HERONSETTINGS`, `HERONCHANGES`, `HERONPUBLISH`, `HERONADMIN`,
`HERONASKTOKEEP`. Full detail: [docs/06-heron-plugin.md](docs/06-heron-plugin.md).

## Parts

| Part | Responsibility | Folder |
|---|---|---|
| **Heron for AutoCAD** (C#) | The plug-in: ribbon, padlocks, banner, Keep or Discard, the secure pipe | [`autocad/`](autocad/README.md) |
| **Heron MCP for AutoCAD** (Python) | The MCP server: the `autocad_*` tools, done over COM, gated by the plug-in | [`src/autocad_mcp/`](src/autocad_mcp/README.md) |
| **Tools & tests** | Build and install the plug-in, smoke test, structure check, test suites | [`tools/`](tools/README.md), [`tests/`](tests/README.md) |

Documentation is in [`docs/`](docs/README.md); stopped experiments in [`archive/`](archive/README.md).
Drawings stay on the PC that made them; none are in this repository.

---

## What it can do

The live list is always `.venv\Scripts\autocad-mcp.exe --list-tools`. Every tool has a level, and
the level decides which padlock it needs:

| Level | Needs | What |
|---|---|---|
| Read | connected | status, list and find, measure, extents, selection, layers, blocks, styles, the UCS, saved locations, **solid volumes and centroids**, preview image, standards check, attribute schedules |
| View | connected | zoom, regen, switch / open / create drawing, **3D view direction and visual style** |
| Change | Changes | draw, text, dimensions, hatch, blocks, batch drawing, move ... array, modify, delete, layers, the UCS, sheets / title blocks / viewports, drawing settings and styles, remap layers / tidy an import, several tools in one call, **24 named shapes**, **dimension runs and centre marks**, **multileaders, tables and revision clouds**, **3D solids, extrude / revolve, booleans** |
| Publish | Changes + Publish | save, export / plot to PDF (whole sheet, a window, or a saved location) |
| Admin | Changes + Admin | any command, AutoLISP, system variables, purge, audit |

Every tool with its options: [docs/03-tools-reference.md](docs/03-tools-reference.md).
Sheets, the UCS and turning an import into a shop drawing:
[docs/09-sheets-and-coordinates.md](docs/09-sheets-and-coordinates.md).
Named shapes, dimension runs, annotation and 3D:
[docs/10-geometry-annotation-3d.md](docs/10-geometry-annotation-3d.md).

## What keeps your drawing safe

- **Invisible until connected.** AutoCAD starts disconnected every time. The pipe answers only your
  Windows user, and each connect makes a new session password.
- **Padlocks, off by default,** read fresh on every call. A broken settings file means all off.
- **One undo step per call.** Optional **Keep or Discard** after each change.
- **Wrong-drawing guard.** If you switch drawings mid-job, a change is refused until Heron looks again.
- **No double drawing.** If AutoCAD goes busy half-way through a change, Heron does not retry; it
  says "outcome unknown, read the drawing back first".
- **Every call audited** to `%LOCALAPPDATA%\Heron\autocad\audit\`.

More: [SECURITY.md](SECURITY.md).

## Install (for testing only, see the banner above)

Needs Windows, **full AutoCAD 2021 to 2027** (not LT), Python 3.10+, and the .NET SDK to build.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

```bash
.venv\Scripts\python.exe tools/build_plugin.py
```

Close AutoCAD, then:

```bash
.venv\Scripts\python.exe tools/install_plugin.py
```

Start AutoCAD, press **Heron**, and connect Claude Code (this folder's [`.mcp.json`](.mcp.json) does it
when Claude Code opens here). Full steps: [docs/SETUP.md](docs/SETUP.md).

## Where to read next

| You are | Read |
|---|---|
| **The owner** | [docs/HANDOVER.md](docs/HANDOVER.md) and the live checks in [docs/NEEDS-CHECKING.md](docs/NEEDS-CHECKING.md) |
| **A modeller** | [docs/06-heron-plugin.md](docs/06-heron-plugin.md), then [docs/09](docs/09-sheets-and-coordinates.md) and [docs/10](docs/10-geometry-annotation-3d.md) |
| **Changing the code** | [docs/PROJECT-MAP.md](docs/PROJECT-MAP.md), [CONTRIBUTING.md](CONTRIBUTING.md) |
| **An AI agent** | [AGENTS.md](AGENTS.md) |

## Licence

MIT. See [LICENSE](LICENSE). AutoCAD is a trademark of Autodesk, Inc. This project is not affiliated
with Autodesk.
