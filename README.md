# Heron AI for AutoCAD

> **Dear Modelers - this is the first release (v1.8.0), for testing, not a finished product.**
>
> This repository is public so the work is open. The first **release (v1.8.0)** is on the
> [releases page](https://github.com/Ajmalpshaik/Heron-AutoCAD/releases). It installs and the
> plug-in loads in AutoCAD 2027, but most tools have not been checked in AutoCAD yet
> ([NEEDS-CHECKING](docs/NEEDS-CHECKING.md)) and the files are not code-signed. Install it only to help test, on drawings you can afford to undo
> ([INSTALL](docs/INSTALL.md)). I will announce it when it is ready for everyday work.
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
| **Heron** | black heron: no chat can see this AutoCAD; orange heron: a chat can reach it. The arrow holds **Bridge Status**, **Heron palette** (recent changes with Select, Zoom and Undo, and your saved commands), **Free this AutoCAD** and **Stop Heron now** |
| **Settings** | one window with the five switches below, each with its padlock picture and an ON / OFF button |

| Switch in Settings | Off (safe) | On |
|---|---|---|
| **Changes** | Heron can only read and look | red ON: Heron may draw, modify and delete |
| **Admin** | no commands or AutoLISP | red ON: Heron may run commands, AutoLISP, system variables |
| **Publish** | Heron may not save or export | red ON: Heron may save, export, plot |
| **Ask to Keep** | changes are kept at once | green ON: after each change, **Keep it / Discard it** |
| **Ask before keeping erased objects** | what a job erases stays erased, no box (until AutoCAD restarts; the PC's administrator can make it start off, [D-123](docs/DECISIONS.md)) | green ON (at every start): after a job erases anything, **Bring them back / Keep them erased** |

While Heron works, Heron for Revit's status bar slides down at the top of AutoCAD: a glass card
saying **"Heron AI · Reading"** or **"Heron AI · Changing"** (orange, with the drawing, the job and the
time), then **Done** (green) or **Needs attention** (red). Every Heron window uses Revit's dark Heron
style. The command line keeps a line such as `Heron: Draw Line. Done in 0.4 s`.

Everything starts **off**, except the erase question, which starts **on**. Turning a padlock on asks
first; turning it off never asks (the two questions the other way round). The same
switches are commands: `HERON`, `HERONSTATUS`, `HERONPALETTE`, `HERONFREE`, `HERONSTOP`, `HERONSETTINGS`, `HERONCHANGES`,
`HERONPUBLISH`, `HERONADMIN`, `HERONASKTOKEEP`, `HERONASKERASE`. Full detail: [docs/06-heron-plugin.md](docs/06-heron-plugin.md).

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

Heron has **199 tools**. The plain-words catalogue of every one, with what to ask in the chat, the
padlock it needs and whether it was ever checked in AutoCAD, is
[docs/TOOL-CATALOGUE.md](docs/TOOL-CATALOGUE.md); the live list is always
`.venv\Scripts\autocad-mcp.exe --list-tools`. Every tool has a level, and the level decides which
padlock it needs:

| Level | Needs | What |
|---|---|---|
| Read | connected | status, list and find, measure, extents, selection, layers, blocks, styles, the UCS, saved locations, **solid volumes and centroids**, preview image, standards check, **check lists before issue**, attribute schedules, lights, groups, annotation scales, **why a job cannot run** |
| View | connected | zoom, regen, switch / open / create drawing, **3D view direction and visual style**, **a check list over a folder of drawings** (opened read only) |
| Change | Changes | draw, text, dimensions, hatch, blocks, batch drawing, move ... array, modify, delete, layers, the UCS, sheets / title blocks / viewports, drawing settings and styles, remap layers / tidy an import, several tools in one call, **24 named shapes**, **dimension runs and centre marks**, **multileaders, tables and revision clouds**, **3D solids, extrude / revolve, booleans**, **trim, extend, fillet, chamfer, break, join, stretch, explode**, layer states and isolate, annotative scales, **Excel tables**, ATTSYNC, the render set-up (camera, sun, lights, exposure; never the render itself) |
| Publish | Changes + Publish | save, export / plot to PDF (whole sheet, a window, or a saved location), **a check list report as Excel and HTML**, attributes to an Excel sheet |
| Admin | Changes + Admin | any command, AutoLISP, system variables, purge, audit |

Every tool with its options: [docs/03-tools-reference.md](docs/03-tools-reference.md) (for the
developer) and the [catalogue](docs/TOOL-CATALOGUE.md) (for the modeller).
Sheets, the UCS and turning an import into a shop drawing:
[docs/09-sheets-and-coordinates.md](docs/09-sheets-and-coordinates.md).
Named shapes, dimension runs, annotation and 3D:
[docs/10-geometry-annotation-3d.md](docs/10-geometry-annotation-3d.md).

## What keeps your drawing safe

- **Invisible until connected.** AutoCAD starts disconnected every time. The pipe answers only your
  Windows user, and each connect makes a new session password.
- **Padlocks off at every AutoCAD start,** kept only in that AutoCAD's memory: no file can turn
  one on, only your click ([D-59](docs/DECISIONS.md)). An office can hold one off with a Windows
  policy ([D-60](docs/DECISIONS.md)).
- **One undo step per call.** Optional **Keep or Discard** after each change.
- **Wrong-drawing guard.** If you switch drawings mid-job, a change is refused until Heron looks again.
- **No double drawing.** If AutoCAD goes busy half-way through a change, Heron does not retry; it
  says "outcome unknown, read the drawing back first".
- **Every call audited** to `%LOCALAPPDATA%\Heron\autocad\audit\`.
- **A check is not a sign-off.** PASS means the checked value is met, against the source named on
  the line. Heron never says a drawing complies: [DISCLAIMER.md](DISCLAIMER.md).

More: [SECURITY.md](SECURITY.md).

## Install (for testing only, see the banner above)

Read the [disclaimer](DISCLAIMER.md) before you install. **Step by step, with the checks and the
warnings to expect: [docs/INSTALL.md](docs/INSTALL.md).** In short: download
`HeronAutoCAD-<version>-setup.exe` (or the zip) and `checksums.txt` from the
[releases page](https://github.com/Ajmalpshaik/Heron-AutoCAD/releases), check the SHA-256, close
AutoCAD and Claude, double-click the setup, then in AutoCAD press **Heron**. No Python, no .NET
SDK, no administrator password.

### What has really been checked

Taken only from the PASS rows in [NEEDS-CHECKING](docs/NEEDS-CHECKING.md). A build is not a check:
a piece is "checked live" only where a row ran in that AutoCAD and passed.

| Piece | State | Where that comes from |
|---|---|---|
| Python server, run from this folder (`.venv`) | **Checked live, AutoCAD 2027 only** | Group A: the PASS rows from A2 to A30 (2026-10-26 / 27) |
| Plug-in for AutoCAD 2027 (.NET 10) | **Checked live** for the rows marked PASS; many later rows not yet | Groups A, J, L: PASS rows 2026-10-26 to 2026-11-08. Groups D to Q are mostly NOT RUN; R to AE (2026-11-21) are all NOT RUN |
| Plug-in for AutoCAD 2025 / 2026 (.NET 8) | **Built, never run**: no PC with that AutoCAD | Group B: NO MACHINE |
| Plug-in for AutoCAD 2021 to 2024 (.NET Framework 4.8) | **Built, never run**: no PC with that AutoCAD | Group C: NO MACHINE |
| Server as one `autocad-mcp.exe` (the release zip) | **Built, not checked live** | No PASS row |
| Installer (`Install.bat`, `Rollback.bat`, `CheckForUpdate.bat`) | **Not checked live**: tried only in a test user folder | Group P: P2-P5 NOT RUN |
| One-file setup (`HeronAutoCAD-<version>-setup.exe`) | **Built and tried on GitHub's Windows machine only** (install, refusals, uninstall; no AutoCAD there) | Group AK: AK1-AK11 NOT RUN |
| Claude Code connection through this folder's `.mcp.json` | **Checked live, AutoCAD 2027** | A2: Claude asked AutoCAD and got the answer |
| Claude Code and Claude Desktop entries written by the installer | **Never run live** | Group P: P2 NOT RUN |
| Plug-in DLLs, `autocad-mcp.exe` and the setup | **Unsigned, by decision** ([#164](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/164)): no certificate is bought | Windows SmartScreen may warn once (More info, Run anyway); AutoCAD may ask once at the first load (load it always). Rows AK10-AK11 NOT RUN |
| Install size on disk | **Not measured** | The zip and the setup are built on Windows only |

### Build it from the source instead (for developers)

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
| **A modeller** | [docs/INSTALL.md](docs/INSTALL.md), [docs/06-heron-plugin.md](docs/06-heron-plugin.md), the [tool catalogue](docs/TOOL-CATALOGUE.md), then [docs/09](docs/09-sheets-and-coordinates.md) and [docs/10](docs/10-geometry-annotation-3d.md) |
| **Changing the code** | [docs/PROJECT-MAP.md](docs/PROJECT-MAP.md), [CONTRIBUTING.md](CONTRIBUTING.md) |
| **An AI agent** | [AGENTS.md](AGENTS.md) |

## Licence

MIT. See [LICENSE](LICENSE). AutoCAD is a trademark of Autodesk, Inc. This project is not affiliated
with Autodesk.
