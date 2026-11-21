# Decision log

> **Append-only.** A decision that is later reversed gets a **new** entry that supersedes the old one;
> the old one stays, so the reasoning is never lost. Number new entries one above the highest here.

---

## D-01 - Python server, AutoLISP for bulk work

**Decided:** 2026-08-25. **Status:** in force.
MCP must be served by an outside process, which AutoLISP cannot be. Python hosts the protocol and
typed single operations over COM; AutoLISP is generated for bulk creation and for what COM cannot
reach. Detail: [02](02-architecture.md#why-python-and-autolisp).

## D-02 - One COM worker thread, retry on busy for 10 s

**Decided:** 2026-08-25. **Status:** in force.
COM is apartment-threaded and AutoCAD rejects calls while busy. All COM work runs on one
`CoInitialize`d thread; `RPC_E_CALL_REJECTED` is retried for 10 s, then reported with "press Esc".

## D-03 - One tool call is one undo group; deletes need `confirm=true`

**Decided:** 2026-08-25. **Status:** in force.
Anything Claude does must be reversible with one Ctrl+Z, and nothing is deleted on a guess.

## D-04 - PDF export configures the layout, then plots with the path only

**Decided:** 2026-10-19. **Status:** in force.
The two-argument `PlotToFile(path, pc3)` fails on AutoCAD 2027. Set the layout to the pc3, extents,
fit and centre, plot with the path alone, restore the page setup. Pinned by `tests/test_export.py`.

## D-05 - Repository laid out in parts, like Heron AI

**Decided:** 2026-10-26, on Ajmal's instruction to "rearrange everything like Heron AI" without
changing Heron itself. **Status:** in force.
Folders: `src/autocad_mcp/` (server), `generators/` (was `drawings/source/`), `drawings/<PACKAGE>/`
(outputs only), `tools/` (was `scripts/`), `tests/`, `docs/`, `archive/`. Root carries README,
AGENTS, CONTRIBUTING, SECURITY, CHANGELOG, LICENSE, as Heron does. `src/` was **not** moved: the
editable install and three MCP configs point at it, and moving it means a reinstall
([05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)).
Heron AI was read for its structure only; nothing in it was changed.

## D-06 - Ruff checks the server, not the generators

**Decided:** 2026-10-26. **Status:** in force.
`generators/` and `archive/` are dense one-project drawing scripts with long data lines; they had 126
style findings and no functional ones. Ruff now excludes them (`pyproject.toml`) so CI guards the
server. Tidying the generators is on the [ROADMAP](ROADMAP.md).

## D-07 - Generator paths come from `generators/paths.py`

**Decided:** 2026-10-26. **Status:** in force.
Five scripts carried a typed `D:\06_Development\...` path. They now import `SERVER`, `AHU_OUT`,
`CCTV_OUT`, `ENCL_OUT` from `paths.py`, worked out from the file's own location, so the repository
runs from any folder or PC.

## D-08 - Revit enclosure experiment archived, not deleted

**Decided:** 2026-10-26. **Status:** in force.
`drawings/revit_encl/` sent raw C# to Revit through Heron's bridge pipe. Ajmal stopped that task on
2026-10-22 and said Heron must be used through its own capabilities. Kept in `archive/revit_encl/`
for reference; never build on it.

## D-09 - Private GitHub repository, generated drawings included

**Decided:** 2026-10-26. **Status:** in force.
`Ajmalpshaik/AutoCAD-MCP`, private. DWG, PDF and PNG outputs are committed (about 10 MB) so the
packages are kept with the code that made them. AutoCAD `.bak` / `.dwl` files and the `.venv` are not.
Visibility superseded by [D-10](#d-10---repository-made-public); keeping drawings in git superseded
by [D-11](#d-11---generated-drawings-are-not-kept-in-git).

## D-10 - Repository made public

**Decided:** 2026-10-26, on Ajmal's instruction "make it public". **Status:** in force. Supersedes the
*private* part of D-09.
Checked before switching: no keys, passwords or e-mail addresses in the files or history; the CCTV
package uses a sample client; the pole-enclosure sheet's client, location and consultant are still
`TBC`. **When those TBCs are filled with a real client's details, think before committing them here:
the repository is public.**

## D-11 - Generated drawings are not kept in git

**Decided:** 2026-10-26, on Ajmal's instruction ("why you keep drawings on this repo?? ... remove
this"). **Status:** in force. Supersedes the *drawings included* part of D-09.
The DWG, PDF, PNG and LISP output can be made again from `generators/`, it was about 10 MB against a
small code base, and the pole-enclosure sheet is real site work that should not be public. The whole
`drawings/` folder is ignored (its README too, since 2026-10-26: an empty-looking folder on GitHub
helped nobody), and the files were **removed from the whole git history**
(rewritten and force-pushed the same day, while the repository was one day old with no other copies).
The files themselves stay on Ajmal's PC.

## D-12 - Heron AI for AutoCAD: same family, separate repository

**Decided:** 2026-10-26, with Ajmal ("Heron AI for AutoCAD", repository renamed `Heron-AutoCAD`).
**Status:** in force.
Heron AI's own decisions defer every non-Revit platform "until Revit works properly", and an AutoCAD
plug-in needs its own C# builds, so it lives here, separate. It carries Heron's name, ribbon, padlocks,
banner and wording so a modeller sees one product. When Heron's capability registry is ready, this
repository is offered as its AutoCAD adapter. Heron AI itself is not changed (its icon PNGs were
copied once, read only).

## D-13 - AutoCAD 2021 to 2027, three builds

**Decided:** 2026-10-26, Ajmal chose "2021 to 2027". **Status:** in force.
`net48` for 2021-2024 (R24), `net8.0-windows` for 2025-2026 (R25), `net10.0-windows` for 2027 (R26),
against Autodesk's `AutoCAD.NET` NuGet packages 24.0.0 / 25.0.1 / 26.0.0, in one `HeronAutoCAD.bundle`.
Only 2027 is on this PC: the other versions stay NO MACHINE in [NEEDS-CHECKING](NEEDS-CHECKING.md)
until someone runs them; the docs never claim them as working before that.

## D-14 - The plug-in guards, COM draws

**Decided:** 2026-10-26, Ajmal chose this over rewriting every tool in C#. **Status:** in force.
The plug-in owns connection, padlocks, banner and Keep or Discard; the Python server keeps its COM
tools and asks the plug-in `begin` / `end` / `ask_keep` around every call, from one place
(`tool_errors` -> `core/gate.py`). Tools can move into the plug-in later, one at a time; since
D-40 the plug-in does the operations COM has no call for.
Known limit: COM stays reachable by other programs; the guard binds Heron, not the whole PC.

## D-15 - A write AutoCAD interrupted is never re-run

**Decided:** 2026-10-26. **Status:** in force.
The busy-retry loop re-ran a whole tool. Once `undo_mark` has started a write, a busy signal now
raises `OutcomeUnknown` ("read the drawing back before retrying") instead, so nothing is drawn twice.
Gap: `send_command` / `run_lisp` paths that manage their own undo do not mark the write; on the
[ROADMAP](ROADMAP.md).

## D-16 - A broken padlock file means padlocks off, banner on

**Decided:** 2026-10-26. **Status:** in force.
An unreadable `heron-autocad.config` turns every padlock off (fail closed) but keeps the activity
banner on, because the banner is what shows the modeller that Heron is working.

## D-116 - What the review of the 2026-11-21 merges changed, and what it left to issues

**Decided:** 2026-11-21, review of PRs #99 onward (PR #186). **Status:** in force; adds to D-29, D-66,
D-69 / D-75, which stand. Nothing Ajmal decided changes (D-59, D-60, D-73, #158).
- **A sequence step may not move the work** (D-29): `autocad_switch_drawing`, `open_drawing`,
  `create_drawing`, `check_folder`, `use_autocad` and `undo_last` are refused as steps, before
  anything runs. Inside a sequence the gate checked one drawing and put its UNDO mark there, so a
  later step must land in that drawing; `undo_last` as a step would take back the sequence's own work.
- **The dialog watch forgets a job whose end never came** (D-66, D-74): a new job's begin drops an
  earlier one (one job runs at a time in an AutoCAD), and a job older than 20 minutes stops counting.
  Before, a server stopped mid-job left the watch on outside any job and an Admin job's named
  button armed for later jobs.
- **Excel** (D-69, D-75): an error cell (`#N/A`) is never written; exported data cells are formatted
  as Text, so Excel keeps what the modeller types ("0051", "1:100"); a row is named by its Excel row
  number; a cell reference with no column letter is refused, as D-75 already said.
- **Checks that could pass for the wrong reason:** the tool-finder floors are back at the margin
  their comment states, a tool listed under two levels in `core/risk.py` fails the structure check,
  and the folder-close test now reaches the code it tests.
- **Left to issues, in areas other sessions are changing:** #189-#191 and #206-#212 (the palette
  Undo's guessed mark and the batch text escape first). Live rows: Group RV (NOT RUN).

## D-108 - Construction lines, regions, donuts, divide and measure: COM where it has a call, Heron's maths where not

**Decided:** 2026-11-21, part 1 of issue #119 (the smaller ribbon gaps), split into #173, #174,
#177 and #181. **Status:** in force. Four Change tools in a new file, `tools/draw_extra.py`, so the
`autocad_draw_*` tools and the batch are left alone. Not named `autocad_draw_*` for the same reason.
- **Construction line and ray** (`autocad_add_construction_line`, `kind` xline or ray): COM
  `AddXline` / `AddRay`, base point plus a second point. Given an angle, the second point is one
  unit along it. XLINE's own Offset and Bisect options are not built: offset an xline with
  `autocad_offset_entities`, and a bisector is two points the AI can work out.
- **Region** (`autocad_add_region`): COM `AddRegion` on the outlines' own space, one region per
  closed loop. Only lines, arcs, circles, ellipses, splines and polylines are sent; text, blocks and
  the rest are refused before AutoCAD is asked. The outlines **stay** unless `erase_outlines`
  (REGION's DELOBJ is not read: a tool's result should not change with a setting the modeller cannot
  see). With `erase_outlines`, every outline given is erased, and one on a locked layer is refused before anything is made. Holes are cut afterwards with `autocad_solid_boolean` subtract, which already takes regions.
- **Donut** (`autocad_add_donut`): no COM call makes one, so Heron draws the object DONUT makes: a
  closed lightweight polyline of two half-circle arcs (bulge 1 each), constant width
  (outside - inside) / 2, run at radius (outside + inside) / 4. Inside 0 is a filled dot. Many
  centres in one call, as DONUT keeps asking for centres; one undo step. FILLMODE 0 is said, not
  changed.
- **Divide / Measure** (`autocad_divide_curve`): no COM call either. The distances are Heron's maths
  over the run's segments (`acad/geometry.py`, the same reading `autocad_place_along` uses), then
  `AddPoint` or `InsertBlock` at each, in the run's own space. Heron's rules: DIVIDE on an open run
  leaves both ends free (N parts, N - 1 marks); on a closed run the first mark is on its start, so N
  marks. MEASURE starts at the start (or the end, `from_end`), puts no mark exactly on the far end,
  and gives `left_at_end`. A block is turned to the run's own direction (`align`, on by default as
  DIVIDE's "Align block with object? Yes"), not reversed by `from_end`. Lines, polylines, arcs and
  circles only (what `read_path` reads); a sloping line or a run not flat in world plan is refused.
  At most 2,000 marks a call, refused before any position is worked out; a layer name is checked
  before anything is drawn. Splines and ellipses are not built: no tested reading of them as a
  path yet. `autocad_place_along` stays the tool for equal ends.
- **Not checked against Autodesk's reference (D-33).** The help site is blocked from the session
  that built this, and there is no AutoCAD here, so the COM calls (`AddXline`, `AddRay`,
  `AddRegion` and its return, `ConstantWidth`) and the DIVIDE / MEASURE rules above are from
  knowledge. Live rows AP1-AP11 in [NEEDS-CHECKING](NEEDS-CHECKING.md) compare each with AutoCAD's
  own command; all NOT RUN.

## D-105 - A plot style table is not made by Heron: the .NET API cannot write one

**Decided:** 2026-11-21, building issue #68. **Status:** in force (a known limit, [05 §34](05-known-limits.md)).
A plot style table (`.ctb` colour-dependent, `.stb` named) is not part of the drawing: it is a
file in AutoCAD's Plot Styles folder, made in the Plot Style Manager. Autodesk's .NET reference
assemblies for 2021 and 2027 were searched for a way to make or edit one, and there is none: only
`PlotStyleDescriptor` and `PlotStyleNameType` (a plot style's id on an object), the picker
dialog `PlotStyleDialog`, and an event when a layout's table changes. COM has none either. So
`autocad_create_styles` takes no plot style option and says so in its `Don't use when:`; the
modeller makes or copies the `.stb` / `.ctb` in AutoCAD, and `autocad_page_setup(plot_style_table=...)`
sets it on a sheet. **Rejected:** writing the file format ourselves (it is Autodesk's, compressed
and undocumented; a file AutoCAD cannot read would show up only at plot time, and nothing here could
check it), and typing STYLESMANAGER (it opens a window the chat cannot drive).

## D-104 - Multileader and table styles are made by the plug-in; the rules are in the Bridge

**Decided:** 2026-11-21, building issue #68. **Status:** in force; extends D-28 and D-40 (built
and tested offline; live rows AN1-AN12 NOT RUN).
- **Two new plug-in operations**, `multileader_style` and `table_style` (level Change), because
  COM has no call to make either (until now they came in only with `autocad_import_from_drawing`).
  `autocad_create_styles` takes `multileader_styles` and `table_styles` beside its text and
  dimension styles, and stays a Change tool written from a fixed list (D-28): the options are a
  list in `tools/settings.py`, a misspelt one is refused before anything is written, and a test
  holds that list to the options the plug-in reads.
- **The rules are pure code in `Heron.AutoCAD.Bridge/StylePlans.cs`** with their own tests: the
  option words, the defaults and every refusal. The add-in (`DrawingStyles.cs`) only copies a plan
  onto AutoCAD's `MLeaderStyle` / `TableStyle` and reads back what the style then holds. One
  transaction per style: a style AutoCAD refuses is that style's row and nothing of it is kept;
  the others are still made. Text styles come first in the same call (and the same undo mark), so a
  style can use one made with it.
- **A multileader style is Ajmal's TLD label unless asked otherwise (D-24):** MTEXT content,
  straight leaders, the text attached *underline bottom line* on both sides (the leader ends under
  the text), arrow and dogleg (the dialog's "landing") as big as the text, as `autocad_add_label`
  draws them. Sizes are given as they plot and the style's own scale makes them drawing sizes, as
  the Multileader Style dialog does. The dialog's one landing switch is `EnableDogleg` and
  `EnableLanding` together. Arrows are AutoCAD's own by name (`dot`, `architectural_tick`...);
  a block the drawing lacks is made the way AutoCAD's dialogs make it, by naming it in DIMBLK, which
  is put back straight after (the one piece that is not undone if a later step fails, so everything
  else is checked first). An annotative style keeps its own scale (the annotation session's work is
  not touched).
- **A table style keeps text in the vertical middle of every cell (D-83):** title, header and
  data rows take left, centre or right only; top or bottom is refused. A table style has no scale
  of its own, so text heights and margins are given as they plot and multiplied by the scale
  (2.5 at 1:50 is 125). Margins default to a third of the text height, as in AutoCAD's own Standard
  style (0.06 for 0.18 text); header and title heights to the data height.
- **A scale reads as the dimension style's does:** a number is the factor (50 = 1:50), and text the
  way the sheet writes it ('1:50', '2:1'). A bare number below 1 is refused rather than guessed
  (0.02 could be the 1:50 ratio or a factor fifty times too small), the mirror of D-36.
- **Not yet known (live rows):** whether AutoCAD's dialog shows these as set (the attachment
  numbers and the landing switch are from Autodesk's reference, not a run), whether the DIMBLK
  round trip leaves no style override, and whether one Ctrl+Z takes back text styles and plug-in
  styles together. **Rejected:** typing MLEADERSTYLE / TABLESTYLE (each opens a dialog, which typed input
  cannot drive), a COM dictionary `AddObject` of these classes (not proven anywhere), and a general "set any
  property" request (D-40's reason).

## D-102 - A full-sheet preview says what it covered, and can add close-ups

**Decided:** 2026-11-21, for issue #41. **Status:** in force; extends D-04 (the plot route) and
leaves the default preview one picture, as before.
On 2026-10-28 `autocad_preview(area='extents')` of an A1 schematic at 1:1 showed only the two frame
rectangles, while windows over its parts showed everything. The cause could not be seen from here
(no AutoCAD). The two found in the code and in Autodesk's behaviour:
- **Too few pixels for the sheet (most likely).** AutoCAD's PNG plotter has fixed sizes; the
  preview takes the one nearest `width_px` (1600 by default), and the chat app may shrink the
  picture again. Which sizes AutoCAD 2027 offers is not yet known here (row AM5). A whole A1
  (841 mm) fitted into 1600 pixels is about 0.5 mm a pixel: 2.5 mm text and thin lines turn to
  specks while the heavy frame still shows. A window over one part gets the same pixels for less
  paper, which is why windows showed everything.
- **Extents bigger than the sheet.** EXTMIN/EXTMAX grow as things are drawn and shrink only on a
  ZOOM All / Extents, and they count objects on layers that are off, not plotted or on Defpoints.
  A stray or erased object far off makes the sheet small in the picture.

What the code does now: an extents preview regenerates first (as `autocad_get_extents` does) and
the answer says the area plotted (`plotted`), the picture's `pixels` and the smallest text height
that reads (`smallest_clear_text`, 8 pixels a letter), with a `tip` when the drawing's TEXTSIZE is
smaller. **`detail=2` (or 3)** adds 4 (or 9) overlapping close-ups of the same area, plotted as
windows, because windows are the route that showed everything live; each is named (top left ...)
with its corners. Not done: a bigger PNG (the pc3's pixel sizes cannot be changed over COM; a
custom size is a pc3 edit by hand), and plotting the overview as a window (the extents read back
could be staler than AutoCAD's own Extents plot). Close-ups are refused for `area='view'` (no
corners) and skipped, with the reason, in a 3D view or a rotated UCS, where the plan box does not
match the picture. Live rows AM1-AM6 NOT RUN; issue #41 stays open until AM1 says which cause it was.

## D-98 - The plug-in reports drawing events as they happen; a batch goes through it in pieces up to 1,500 characters

**Decided:** 2026-11-21, issues #48 and #45. **Status:** in force (built and tested offline; live
rows AJ1-AJ10 NOT RUN).

- **Drawing events (#48).** The plug-in records AutoCAD's document events as they happen
  (`DrawingEvents`, fed by `DrawingWatch` in the add-in): a drawing *opened*
  (`DocumentCreated`), *came to the front* (`DocumentBecameCurrent`; the one already in front is
  not news), *saved* (`Database.SaveComplete`, read after the command so a Save As gives the old
  name; the automatic save `.sv$` and backups are left out) and *closed*
  (`DocumentToBeDestroyed`). Each event has a number, and the log an epoch that is new for every
  AutoCAD session; 200 are kept. A stdio server has no way in from the plug-in (D-68), so the server
  asks: the new op `drawings {since}` answers the events after that number, read only, on the
  pipe thread.
- **The wrong-drawing guard (D-19) uses them.** `autocad_status` (and `autocad_create_drawing`)
  notes where the log stands; a later change asks for the events since. The checked drawing
  **closed** since (even when the same name is open again: it is a new copy in memory, perhaps
  changed on disk) or **another AutoCAD session** (restarted, or another AutoCAD) is refused with
  "call autocad_status first". A **Save As** of the checked drawing is followed: the same drawing,
  the same units, so no new check. A switch away and back is the same drawing and goes ahead, as
  before. When the plug-in cannot tell (an older one, history dropped off) the guard is exactly
  the name compare it was.
- **Mid-job.** `send_quiet` refuses drawing input once another drawing came to the front (or the
  job's drawing closed) after the job's `begin`, counted only from events AutoCAD reported, so a
  missed event never refuses; the add-in checks the drawing in front again on the main thread
  before typing. That refusal ends the input: the server never types it over COM instead.
- **The palette** redraws its Activity list on every drawing event: a line "In front: plan.dwg",
  the drawing events between the jobs (15 newest), and *not in front* on a job in another drawing.
- **Fewer `Command:` prompts (#45).** Every top-level expression typed leaves one prompt, echo off
  or not. The plug-in's ping now says `quietLimit` (1,500), and `send_quiet` refuses a longer line
  before typing anything. The server builds the batch in pieces up to that (never above
  `QUIET_CHUNK_LIMIT` = 1,500), packs the short set-up pieces into one `(progn ...)`, and keeps
  the last piece (close the undo group, write DONE) on its own, so an error before it never
  leaves the undo group open. Offline, the 41-object batch of the live checks goes from 25 pieces
  to 9. Over COM, from an older plug-in, or when the plug-in refuses, the pieces stay under 600
  (D-21). 1,500 is below the 2,000 characters that worked all day over COM and far from the
  3,000 that arrived as nothing (known limits §3); it is not measured through `SendStringToExecute`
  yet (AJ6, AJ7).
- **Two safety nets found on the way.** A `send_quiet` that went out and got no answer is treated
  as typed: sending it again over COM could draw the batch twice. A batch whose output file has
  DONE but fewer result lines than operations says `missing` with a hint, never a quiet success.
- **After an independent review (same day).** The guard also refuses a drawing *opened* since the
  check when it is the one in front (a Save As, then the old file opened again; a second copy).
  History that dropped off is no longer a reason to ignore the events still there; 200 are kept,
  and every change the guard lets through moves its mark up. Names are compared exactly, so an
  unsaved `Drawing1.dwg` is never taken for `D:\F\Drawing1.dwg`. `autocad_status` takes its mark
  before its work. `send_quiet` now waits (up to 10 s) for AutoCAD to get to the input and answers
  the truth: typed, refused because another drawing is in front (also when the switch came between
  the server's look and `begin`), or not started in time (abandoned, never typed later). A Save As
  of the job's drawing is followed. The add-in keeps the old names by AutoCAD's database, not the
  .NET object, and says a Save As made while closing before the close.
- **Not done:** the Companion page (D-71) is a file the gate rewrites after each job, so it cannot
  update live without a server of its own; the docked palette is the live list.

## D-95 - Sections, flat views, surfaces, meshes and the new super hatch tiles are plug-in operations

**Decided:** 2026-11-21, for issues #54, #109, #58 and #57. **Status:** in force; extends D-40 and
D-33. None of FLATSHOT, SOLPROF, SECTIONPLANE, PLANESURF, SURFNETWORK, MESH or Express Tools'
image / xref / wipeout SUPERHATCH has an ActiveX call, so each is a listed plug-in operation
(`flat_views`, `section_plane`, `loft_surface`, `planar_surface`, `network_surface`, `add_mesh`,
and `super_hatch` with a `tile_kind`), Change level, one transaction each. Every .NET call was
checked against the AutoCAD 2027 reference assemblies before it was written (the signatures, by
reflection; the plug-in compiles for all three builds).

**One mechanism for a section and a flat view.** Both use AutoCAD's own section object (`Section`)
and `GenerateSectionGeometry`, the call behind "Generate Section / Elevation". A section plane goes
through the modeller's points and is kept; a flat view puts a temporary plane outside the solids'
box on the viewer's side, so it cuts nothing and the 2D "background" it returns is the view with
hidden lines removed, as FLATSHOT draws it. The plane is made with its viewing direction given
explicitly (`Section(points, vertical, viewing)`), so which side is seen is Heron's choice, not
AutoCAD's default. Where each view looks, the third / first angle layout, and where a plane through
two or three points runs (two points: a vertical cut looking left of the line; three: the plane,
a level one looking down with north up) are pure arithmetic in `Bridge/SectionMath.cs`, tested
offline. The 2D lines are laid flat by what they are found to lie on (the plane, already flat, or
neither and then projected), and the answer says which (`laid_flat_from`), because the reference
does not say where GenerateSectionGeometry puts a 2D section's lines; rows AH3 and AH6 settle it.

**What is left out, on purpose.** Hidden (obscured) lines in a flat view: the API gives visible and
hidden lines in one list with no way to tell them apart, so a view shows visible lines only, as
FLATSHOT does by default. Several solids are flattened each on its own unless `join=true`, which
flattens one temporary union of copies: it hides what is behind a part, and loses the line where
two flush faces meet; the modeller chooses. Jogged section lines (more than one segment): later.

**Super hatch tiles.** An image or a wipeout is first made into a small tile block of its own; an
xref is the tile as it is, attached from its `.dwg` if it is not already there. Then the one block
tiling path of D-40 does the rest, so every kind is one object, clipped as XCLIP clips. An xref
this call attached is detached again if the hatch is then refused, because attaching is not only
a database change. Image tiles are capped at 2,000 (raster images are heavy), blocks at 10,000. A
block hatch sends exactly what it sent before, so an older plug-in still does it.

Rejected: typing FLATSHOT (a dialog) or SOLPROF (works only inside a layout viewport and asks
questions); projecting the solid's Brep edges ourselves (no hidden-line removal and no silhouette
lines on a pipe or a cylinder); one "make a surface" operation taking any arguments (each kind is
listed and checked on its own, as D-40 asks).

## D-94 - A 3D shape is pieces in their own frames, made where COM has no doubt and then moved

**Decided:** 2026-11-21, for issue #53. **Status:** in force; extends D-30.
`autocad_make_shape` takes two 3D shapes, `duct_run` and `pipe_spool`. A solid cannot go down the
batch engine, so a 3D shape is generated as a list of **pieces** (straight, bend, flange), each in
its own frame where AutoCAD makes it without any doubt - a box or a cylinder standing on the origin
up +Z, or a profile at the origin revolved round an axis through (radius, 0, 0) along +Y - plus one
4 x 4 matrix that puts it in place. The pieces and their matrices are pure Python
(`acad/shapes3d.py`), so what matters is tested without AutoCAD: each piece ends where the next
begins, each bend leaves the way the next straight runs and is tangent to both legs at
radius x tan(angle / 2), the straights are the legs less the tangent lengths (a spool's cut
lengths), a rectangular duct is carried round its bends without twisting, and every matrix is a
move, never a mirror.

The COM side (`tools/_solid_pieces.py`) uses only calls already in use (AddBox, AddCylinder,
AddRegion, AddRevolvedSolid, Boolean) plus TransformBy with the matrix. Two of its steps check
themselves, because neither convention is in Autodesk's reference: a bend that came out sweeping
backwards (the revolve's sense) is made again the other way, and every piece's box is compared
with the box it should fill, so a piece that landed anywhere else is reported (`verified: false`)
rather than looking finished. A refusal half way takes out every piece already made.

Defaults, said in the tool so nobody is misled: a rectangular bend's centreline radius is the
duct's size in the plane it bends in (R/W = 1), a round duct's 1.5 x D, a spool's elbow 1.5 x the
outside diameter (a long-radius elbow is 1.5 x the nominal size: give `bend_radius` from the
catalogue when it matters). Flanges have no default size; a flange table is the modeller's.
Pieces are separate solids, as they are fabricated, with `join=true` to union them.

Rejected: one sweep along a filleted path (AutoCAD sweeps along a 2D polyline with arcs or a
spline, not a 3D route with bends, and the result could not be checked piece by piece); Rotate3D
and Move instead of TransformBy (two more sign conventions to trust, each failing silently).

## D-93 - The office check lists live in a folder the modeller names; sharing them is its own Publish tool

**Decided:** 2026-11-21, issue #135 (from the brief for this wave: "a folder the modeller names,
e.g. a shared drive, as the office list's home, with the local copy as the fallback, never
overwriting a teammate's file silently"). **Status:** in force. Extends [D-64](#d-64---check-lists-no-data-office-lists-with-project-changes-pass-is-not-complies).

- **Where it is set.** `autocad_checklist(action='office_folder', folder='S:\CAD\Heron')`, once per
  PC, kept in `%LOCALAPPDATA%\Heron\autocad\checklist-office-folder.json`; `folder=''` clears it.
  Not an environment variable in `.mcp.json`: the modeller sets it from the chat, and Heron checks
  the folder answers before keeping it.
- **Reading.** A run takes the list from the office folder first. Each read keeps a copy on this PC
  (`checklists\office-copies\`). When the folder cannot be reached (it is given 10 s, then believed
  unreachable for a minute, so a folder check does not wait per drawing), or its file cannot be
  read, the run says so plainly and uses that copy, naming the date it was read. With no copy, it
  uses this PC's own list of that name, saying so; but if the office folder **has** the list and it
  cannot be read, nothing is run: Heron never runs another list in place of the office's. Saving
  on this PC under a name the office folder has is refused (it would never be used).
- **A project's changes with the project.** `<the drawing's folder>\Heron check list changes.json`
  holds them for everyone who opens a drawing from that folder; it wins over a PC's own changes
  (D-64's store, still used when there is no such file), and a run says when they differ. A file
  there that cannot be read stops the run. Still only severity, target and on/off.
- **Writing is `autocad_share_checklist`, at Publish** (as D-65): it writes outside Heron's own
  folder, where the team reads. A file there that holds something different is replaced only with
  `replace=true`, and the refusal names who saved it (the Windows user), when, and what differs;
  when replaced, what was there is kept in the same file as `previous` (one step back, never
  nested). The file is written beside itself and swapped in only if nobody changed it since it was
  read. **Who may change the office list** is the folder's own Windows permissions: a read-only
  folder is refused, saying so; Heron adds no roles of its own.
- **Every run names its files:** `lists.office` / `office_from`, `lists.project_file` /
  `project_from`, and `file` on every result line.

If Ajmal wants it otherwise (an `.mcp.json` setting for IT to deploy, or roles inside Heron), that
is a new decision; this one is easy to reverse, as nothing else reads the setting.

**Later the same day (an independent review):** a copy is used only if it was read from the office
folder set now (a copy from a folder set before is another office's list), and the warning names
the file it came from; `autocad_check_folder` keeps every run's warning on its line and names the
list it ran (`list`, `warning`); project changes are not shared while the office list cannot be
read (they would be checked against a stand-in and stop every teammate's run); the office and
project folder reads run off the server's main thread.

## D-92 - DXF / DWG files are read with AutoCAD closed (ezdxf, the ODA converter); standards compare with a reference drawing

**Decided:** 2026-11-21, issues #71 and #69. **Status:** in force.

- **`autocad_read_file`** (Read): the summary (DXF version, units, extents, counts, the most
  placed blocks, layouts, xrefs), the layers with objects per layer, the blocks with how many are
  placed and inside other blocks and their attribute tags, every text and mtext, every block's
  attribute values (JSON or CSV), and the text styles, dimension styles and linetypes, of a file on
  disk. It touches no AutoCAD, so the gate lets it through without the plug-in
  (`NO_AUTOCAD_TOOLS`, as `autocad_why`, D-67), audited like every call; `autocad_why` no longer
  says "press Heron" for it. The file is never written; what is read is what was last saved.
- **DXF with `ezdxf`**, now a dependency of the server: every PC installs it once, by name, with
  Claude closed (`.venv\Scripts\python.exe -m pip install ezdxf`,
  [05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)); without it the tool says how,
  and every other tool works as before. A damaged DXF is read in ezdxf's recover mode and the answer says
  so. Files over 250 MB are refused.
- **DWG, DWS and DWT through the ODA File Converter, only when it is installed.** Heron finds it
  (`HERON_ODA_CONVERTER`, else the newest `Program Files\ODA\ODAFileConverter*`, else PATH) and
  never downloads it. It converts a copy in a temporary folder to an R2018 DXF, with no window and
  a 3-minute limit, then reads that. Without it, a DWG is refused saying it needs AutoCAD, the ODA
  converter, or a DXF of it.
- **`autocad_check_standards(reference=...)`** compares the open drawing with a `.dws`, `.dwt`,
  `.dwg` or `.dxf`: layers by colour, linetype, lineweight and plot; text styles by font, big font,
  height, width and oblique; dimension styles and linetypes **by name only** (COM cannot read a
  dimension style's settings without making it current, which would change the drawing). Each
  name is missing, differs (both values said), or not in the standard (`flag_extra=false` leaves
  those out). Xref and anonymous names are left out; layer 0, Defpoints, Standard and ByLayer are
  never missing or extra. The reference is read by Heron's reader where it can (a DXF always; a
  DWG or DWS when the converter is there), else by AutoCAD's own reader (ObjectDBX, not opened on
  screen, or the open drawing itself); the answer says which in `reference.read_by`. PASS wording
  is D-64's: the checked values are met against that file, never "complies". Pure compare in
  `acad/standard_compare.py`.

Known limits: true colours are compared by their colour number; a `.dws` read by ObjectDBX and the
converter on a real DWG are not proven live (Group AG).

**Later the same day (an independent review):** a reference read in recover mode, or one holding
nothing beyond what every drawing has, never gives `passed: true` (it is `null`, with
`reference.warning`); a table AutoCAD cannot read (layers, styles, linetypes) stops the check,
naming it, instead of counting as empty; the converter gets the copy under a plain name of Heron's
own (it reads that argument as a wildcard filter); header extents at the origin are used.

## D-87 - Lights are listed and switched by the plug-in; the sun, default lighting and exposure are variables

**Decided:** 2026-11-21, for issues #62 and #63. **Status:** in force; extends D-42, whose "never
change DEFAULTLIGHTING behind the modeller's back" stands: only `autocad_switch_lights` changes it,
when asked in words. **None of these tools renders** (Ajmal's rule): they set lights, sun and
exposure, and Ajmal presses Render. `autocad_render` (Admin, types `-render`) was still on main as
the one exception when this was written; it was removed the same day (#158, the last bullet below).
- **List** (`autocad_list_lights`, plug-in `list_lights`, Read), like the Lights in Model palette:
  every light in model space, then in each block definition (not layouts, not xrefs), with handle,
  name, kind, on or off, intensity and its unit, Kelvin, layer, position, and for a light in a block
  the block's name and its number of inserts. The same answer gives the sun (on, date, time, place,
  and azimuth and altitude as AutoCAD gives them, their unit still to be checked), DEFAULTLIGHTING,
  LIGHTINGUNITS and the exposure, and says why a render may come out dark.
- **Switch** (`autocad_switch_lights`, plug-in `switch_lights`, Change): a light by handle, else
  every light of that name (a light inside a block definition repeats in each block), or all of
  them. One name not found refuses the whole switch and lists the names there are, so nothing is
  half done. A light in a block definition switches in every insert, which is what a light block is
  for. The sun (SUNSTATUS) and default lighting (DEFAULTLIGHTING) are plain variables written over
  COM, default lighting first, so the sun goes on in a viewport that already shows user lighting.
  If AutoCAD still asks its viewport lighting question, the dialog watch (D-66) closes it and names
  it; that is a live row.
- **Exposure** (#62, `autocad_set_render_exposure`, Change): the LOGEXP... variables belonged to
  the old renderer and are gone in 2027. The current renderer's Exposure (EV, -6 to 21, lower is
  brighter) and White balance (1000-20000 K) are documented as the variables EXPVALUE and
  EXPWHITEBALANCE (Autodesk help 2016-2023), so the tool writes those over COM, in the type each
  already holds, and reads them back. If this AutoCAD does not answer for one, nothing changes and
  the answer names the Render Environment & Exposure palette (RENDEREXPOSURE): known limit 22. The
  .NET API also has a per-viewport `PhotographicExposureParameters` (Exposure, WhitePoint), and the
  palette's own data class holds the current viewport's tone settings: that is the route to try if
  the variables turn out gone (ROADMAP), not built now, as which of the two the renderer reads is not
  proven.
- **Added 2026-11-21, `autocad_render` removed (#158):** Ajmal asked the parent session to decide
  ("What is the best thing you can decide that one"), and it decided to remove the tool. His rule is
  that Heron never runs the render; `-render` waits on prompts and can stall AutoCAD, and a scripted
  render has been reported to drop objects; an Admin-only exception would still let a chat hang
  AutoCAD with the Admin padlock on. So the tool, its level and its preset and size tables are gone
  (one tool fewer), and Heron has no tool that renders: it sets the camera, sun, lights and exposure,
  and the modeller presses Render. `autocad_preview` stays for a picture to look at. Live row F22 is
  marked removed; F23 proves the sequence ceiling with `autocad_run_lisp` instead. This supersedes
  D-33's "`autocad_render` drives that".
Not proven in AutoCAD: all of it ([NEEDS-CHECKING group AE](NEEDS-CHECKING.md)).

## D-86 - A camera view is a saved view with perspective and a lens; the sun's date is set on the viewport's sun; the visual style is read back

**Decided:** 2026-11-21, for issues #59, #60 and #61. **Status:** in force; extends D-42 and
replaces D-35's "the style cannot be read back" (D-35's typed VSCURRENT stands).
- **Camera view** (`autocad_add_camera_view`, plug-in `add_camera_view`, Change): one view record
  written through the .NET API with perspective on, the lens set, the target, and the direction from
  the target to the eye (the API's own meaning of ViewDirection), saved under a name and, unless
  told not to, put on screen with `SetCurrentView` (and warned about when the viewport is in 2D
  Wireframe, which draws no perspective). A layout's view of the same name is never replaced. The
  view's width and height are the lens's field at the target, so lens and size agree. The field is
  worked out across a 36 mm frame, as AutoCAD
  calls its lens a 35 mm camera's (50 mm: 39.6 degrees, 24 mm: 73.7 degrees); whether AutoCAD's own
  Field of view reads the same is a live row. No camera glyph is drawn, so CAMERADISPLAY does not
  matter. Rejected: DVIEW (it hangs), `entmake` of a VIEW record (it came back at 50 mm, 2026-11-09),
  typing CAMERA (it worked by hand, but its prompts differ between releases), and `-VIEW` (it keeps
  only what is on screen; `autocad_save_view(from_screen=true)` stays for that).
- **Sun date and time** (`autocad_set_sun`, plug-in `set_sun`, Change): AutoCAD has no variable for
  them; they live on the current model viewport's sun (DXF 91 = Julian day, 92 = ms after midnight).
  The .NET `Sun.DateTime` takes the calendar date and clock time, so the plug-in writes that, only
  the parts given, and makes the sun when the viewport has none. The sun hangs off the viewport
  record, which AutoCAD does not keep up to date as the view moves, so for this one operation the
  plug-in writes the live viewports into the drawing first and gives them back after. The place is
  three plain variables over COM: LATITUDE, LONGITUDE and TIMEZONE, the last as hours x 1000 plus
  minutes from a UTC offset (Qatar 3000, India 5030; read back, a last digit naming one place of
  several, as in 3001 or 9031, keeps its offset). A year outside 1900-2200 is refused before
  anything is written. The answer reads it all back, with the 91 and 92 values Heron expects, so a
  live check can compare them with `(entget)`. Model tab only.
- **Visual style read back** (#59): `autocad_set_3d_view` types VSCURRENT as before, then asks the
  plug-in (`current_view`, a Read operation, allowed inside its View job) which style the viewport
  has: the live view's, else the viewport record's, by its name in the drawing's visual style list.
  A different style from the one asked for is said in `visual_style_warning`, not counted as a
  failure: the record can be behind the screen (an independent review of PR #152), and
  `autocad_preview` is the proof. Without the plug-in the field is null with the reason, and the
  tool still works.
Not proven in AutoCAD: all of it ([NEEDS-CHECKING group AE](NEEDS-CHECKING.md)).

## D-83 - Excel ranges as linked tables, table cells by address, and copying between open drawings

**Decided:** 2026-11-21, building issues #117 and #106 (ribbon audit, #94). **Status:** in force;
adds to D-40, D-62, D-63 and D-75, which stand.
- **A real Data Link, made by the plug-in.** `autocad_table_from_excel` reads the sheet with
  `acad/xlsx.py` (D-69) first, so the range, the size and the cells Excel only *shows* as a date, a
  time or a percent are known before anything is made. Then the plug-in operation `excel_table`
  adds a `DataLink` (adapter `AcExcel`, connection string `file!sheet!range`, `SkipFormat`) to the
  drawing's Data Link Manager and sets it on a new table with `Cell.SetDataLink`, in one
  transaction. COM has no data-link call; the .NET names were read from Autodesk's reference
  packages for 2021 to 2027 and build without a warning, but have never run in AutoCAD (D-33).
- **When a link cannot be made, the table is filled, and says so.** A `.csv`, `link=false`, no
  plug-in to ask (`--no-bridge`), an older plug-in, or AutoCAD failing to make or read the link
  gives a table filled over COM with the sheet as it is now, `"linked": false` and
  `not_linked_because`. Nothing else falls back: HERONSTOP, a padlock turned off mid-job, or a
  refusal the modeller has to act on (no sheet tab for `space='paper'`, no such table style) stops
  the job, and "Outcome unknown" is never followed by a second table: the first may be there. A cell Excel only shows as a date, a time or a percent is left
  empty in a filled table and listed in `excel_converted` (the D-75 rule), never written as the
  number behind it. A linked table shows the range exactly: no title row is added to it.
- **`autocad_update_table_links`** (plug-in operation `update_table_links`) updates linked tables
  from their sheets in two steps, as DATALINKUPDATE does: each link reads its workbook again
  (`DataLink.Update`; a link keeps a cached copy), then the table takes the new values
  (`Table.UpdateDataLink`, `SkipFormat`). All of them or those named, in one transaction: one that
  cannot be read stops the job and nothing is changed. A table that is not linked is listed.
- **Cells by address.** `autocad_set_table_cells` counts rows and columns from 1 at the table's
  top-left cell, title and header rows included, the way an Excel address does ("B3" = row 3,
  column 2). Only cells whose text really changes are written (a change of case is a change),
  old -> new in `before_after` (D-62). A cell linked to Excel, content-locked, or inside a merged
  cell is listed and left alone. A cell past the end is refused unless `grow=true`.
- **Heron's tables keep their text in the vertical middle of each cell**, keeping the style's
  left / centre / right: per row type on a new table (`autocad_add_table` too, `SetAlignment`),
  per cell on a written cell, every cell on a linked one. Never worth failing a table for.
- **No empty title row.** A new table starts with a merged title row and a header row; with no
  title (or no headings) asked for, the tool sets `TitleSuppressed` (`HeaderSuppressed`) so the
  rows below are not written into one merged cell. Done in `autocad_add_table` too, which before
  wrote its headings into row 0 when there was no title (expected to fail on all but the first
  cell; not seen live, since every live table had a title). These are AutoCAD's older table flags: whether
  they still turn those rows into ordinary rows on today's tables is live row AC13.
- **The copy lands in the drawing Heron checked.** `autocad_copy_from_drawing` copies from
  another open drawing *into the active one*: the gate's wrong-drawing guard, its UNDO mark, Keep or
  Discard and the plug-in's change count all belong to the active drawing, so the change must be
  there. The source is only read; neither drawing is switched by the tool. COM `CopyObjects` with
  the target's space as owner brings the layers, linetypes, styles and blocks the target lacks; a
  name the target has is the target's own (listed in `already_here`). One `CopyObjects` per owner
  (model space, each layout), then a move from the base point. Previews (`dry_run`) write nothing.

## D-82 - Attribute definitions in make_block; ATTSYNC by the plug-in, values kept by tag

**Decided:** 2026-11-21, building issue #115 (ribbon audit, #94). **Status:** in force; adds to
D-25 rule 2 and D-40, which stand.
- **`autocad_make_block(attributes=[...])`** adds attribute definitions with COM
  `AcadBlock.AddAttribute` (height, mode, prompt, point, tag, value). Checked first, the way ATTDEF
  checks: a tag has no space or `!` and is stored in capitals; a tag only once; a constant
  attribute needs a default; constant and preset together are refused (pick one). Flags are
  AutoCAD's AcAttributeMode numbers: invisible 1, constant 2, preset 8. Positions are drawing
  coordinates, like the objects; one left out is stacked under the base point, 1.5 text heights
  apart; the height defaults to TEXTSIZE.
- **ATTSYNC is a plug-in operation** (`sync_attributes`), because COM cannot add an attribute to
  an insert already placed. The server plans it (`acad/block_attributes.py`, offline) and the
  plug-in does it in one transaction, by the same rule: a value already typed is **kept, matched
  by tag** (a tag that appears twice is matched in order); a tag the definition gained comes in
  with its default; a tag it lost, or made constant, goes. A kept attribute goes back to the
  definition's place, height and style (`SetAttributeFromBlock`), except one holding a field or a
  multi-line one, which is left exactly as it was so nothing typed is lost. The attributes kept stay
  where they are in the insert's list and the new ones follow, in the definition's order: Heron
  does not reorder them, and the server's plan says it the same way (a different order alone
  changes no tag).
- **Which inserts:** every insert of the block by its real name in model space and on every sheet
  (a dynamic block's `*U` copies included), or the handles given. An insert on a locked layer is
  left out and listed. Inserts inside other blocks' definitions are reached with `nested=true`
  ([#156](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/156), added the same day): every ordinary block definition is read for them (layouts are
  already covered, xrefs are another drawing's, `*U` copies are AutoCAD's own); off by default
  because it reads every definition and changes every copy of the block that holds them.
- `add_attributes` adds new definitions to an existing block first (positions from its base point,
  as the block is drawn; one with no position is stacked under the lowest attribute the block
  already has, so it never lands on one), then syncs, in the same transaction. The inserts are
  found in the shared scratch selection set: a named set of its own would cost an undo step. A `dry_run` writes nothing and says
  what each insert keeps, gains and loses.

## D-81 - Layer states and annotation scales go through the plug-in; isolate and merge are COM

**Decided:** 2026-11-21, building issues #107 and #108. **Status:** in force.
- **Layer states** (`autocad_layer_states`; listed by `autocad_list_layers`) are saved, restored
  and deleted by the plug-in with .NET's `LayerStateManager` (`layer_state`, `layer_state_names`).
  The issue said COM; COM's manager is reached only through a ProgID with AutoCAD's version in it
  and has no call that lists the states, and its calls could not be checked here, while the .NET
  calls (`SaveLayerState`, `RestoreLayerState`, `GetLayerStateNames`, the `LayerStateMasks`
  numbers) were read out of Autodesk's own reference assemblies for 2021 and 2027 (D-33).
- **Isolate** (`autocad_isolate_layers`) turns the other layers off, frozen or locked over COM,
  after saving the layers as they were as the layer state `HERON-ISOLATE` (on, frozen, locked, and
  the current layer in its description). The kept layers are turned on and thawed first, then one
  is made current if the current layer would be hidden, then the rest are hidden: AutoCAD will not
  make a frozen layer current, nor freeze the current one. Isolating again keeps that first state;
  `unisolate` restores it, puts the current layer back and deletes it; a refused restore puts the
  current layer back as it was, and a plug-in that cannot read the states is said, not taken for
  "nothing isolated". `autocad_layer_states` will not restore
  or save over that name, so the two cannot get mixed up.
- **Merge** (`autocad_merge_layers`) needs `confirm=true`. It moves objects on the old layers in
  model space and every layout (one selection per layer, the name escaped so `-`, `#`, `.` are not
  wildcards, then matched exactly), inside block definitions (not xrefs) and in block attributes.
  An old layer is deleted only when nothing failed to move off it, and is relocked if it is kept.
  Layer 0 and xref layers are refused, as old layers and as the target; the target must already
  exist.
- **Annotative** (`autocad_annotation_scales`, `autocad_list_annotation_scales`, and
  `annotative=true` on `add_text`, `add_mtext`, `add_dimension`, `dimension_run`,
  `add_multileader`): the plug-in uses `DBObject.Annotative`, `AddContext`, `RemoveContext`,
  `HasContext` and the `ACDB_ANNOTATIONSCALES` collection (`annotation_scales`,
  `set_annotation_scales`), all in the reference assemblies. A scale is found by name, else by its
  paper : drawing ratio; a missing 1:N is added to the drawing only when asked, and only after every
  check has passed (the scales to remove are found first, then each object is checked to keep one),
  so a refusal never leaves a new scale in the list. An annotative object keeps at least one scale
  (a removal leaving none is refused, nothing changed). Made annotative
  with no scale given, an object gets the current one. Heights stay in drawing units at the current
  scale, and the reply gives the paper height, so a wrong assumption shows at once (live row AB9).
- **A drawing tool's annotative step never fails the call** once the object is drawn: what did not
  happen comes back as a warning, so the chat does not draw it twice. A dimension that did not become
  annotative is given the drawing's DIMSCALE after all (or keeps its `dim_style`'s scale), so it is
  never left at plain style size. Without the plug-in the tool
  refuses before drawing anything. The object is drawn over COM and made annotative by the plug-in
  inside the same undo mark (live row AB10 proves the one Ctrl+Z).

## D-80 - A dimension run takes a named style per dimension; spacing is Heron's maths, the break is typed

**Decided:** 2026-11-21, building issues #37 and #116. **Status:** in force.
- **`dim_style` on `autocad_dimension_run` (#37).** The name is checked against the drawing's
  dimension styles before anything is drawn (an unknown one is refused, naming those it has), set as
  `StyleName` on each dimension, and the drawing's DIMSCALE is then **not** written over it: the
  style's own scale wins (`scale_to_write`). The style is never made current, because putting the old
  one back afterwards wipes the DIMSCALE override `autocad_drawing_setup` left on it. A dimension
  that will not take the style is deleted and listed in `failed`, not left at the wrong size (and if
  it cannot be deleted either, `failed` says it is still there). An
  annotative run is not given DIMSCALE either. The scale the first dimension took from the style
  comes back as `style_scale`, for live row AB1.
- **Dimension space (#116).** COM has no definition points on a rotated dimension, so it cannot move
  the dimension line without moving the extension line origins. The plug-in reads each dimension's
  direction and line point (`dimension_lines`, Read) and sets `DimLinePoint`
  (`move_dimension_lines`, Change); where each goes is `plan_spacing`, tested offline. The base stays
  put; every other parallel dimension keeps its side and its order out from the base and goes to
  1, 2, 3 ... spacings; 0 lines them up; one not parallel is skipped and named, and so is one whose
  normal is not +Z (its Rotation would be measured from world -X).
- **Dimension break (#116).** Neither COM nor .NET has a call for a break, so DIMBREAK is typed:
  Multiple, each dimension as `(handent "...")` (the handle checked as hex first, so nothing else
  reaches the command line), then Break or Remove. Anything not a dimension, in the other space, or
  on a locked or frozen layer is refused before anything is typed: DIMBREAK drops what it cannot
  pick, and with none left the typed `_B` would start BLOCK at the prompt. A prompt still open is
  cancelled and said. The breaks are not
  read back: the reply says to look with `autocad_preview`.

## D-79 - Explode, draw order, match properties, groups: plain COM, checked first

**Decided:** 2026-11-21, building issues #105, #111 and #110 from the ribbon audit (#94).
**Status:** in force; nothing here is proven in AutoCAD yet (NEEDS-CHECKING group AA).
- **Explode** (`autocad_explode`) calls the object's own `Explode` and returns the new handles.
  Autodesk's reference says it replaces the object, but forum reports say the original can stay;
  so Heron looks for the original afterwards and erases it if it is still there. The erase goes
  through D-50's question. A block with attributes is skipped unless `allow_attribute_loss=true`:
  exploded, an attribute shows its tag, not its value, so the values are listed in the answer.
  MINSERT arrays are refused. Exploding a part breaks drafting rule 2, so the tool says so.
- **Draw order** (`autocad_draw_order`) writes the space's own `ACAD_SORTENTS` table through its
  extension dictionary (`GetObject`, else `AddObject(..., "AcDbSortentsTable")`), with
  `MoveToTop` / `MoveToBottom` / `MoveAbove` / `MoveBelow`, as DRAWORDER does. All the objects (and the
  reference) must be in one space.
- **Match properties** (`autocad_match_properties`) copies named properties: the general six
  (layer, colour, linetype, linetype scale, lineweight, transparency) by default, `text_style` and
  `dim_style` on request or with `all`. Only what differs is written, before / after is listed
  (D-62), and a property the target does not have is skipped and said. A true colour is copied as a
  true colour. **Lineweight and transparency** also go on `autocad_modify_entity`: lineweight in
  millimetres as AutoCAD lists them, or hundredths (5 and up), or ByLayer / ByBlock / Default; a
  value AutoCAD does not have is refused. Transparency 0-90 (AutoCAD's own limit) or ByLayer /
  ByBlock, written to `EntityTransparency`.
- **Groups**: `autocad_list_groups` (Read) and `autocad_group` (Change: make, add, remove, ungroup)
  over the drawing's `Groups` collection. Names follow AutoCAD's symbol rules; a name taken is
  refused (use add); a missing name gets GROUP1, GROUP2 ... Ungroup deletes the group object only;
  Heron then checks every member is still there and says so if not.
- **Added the same day, from the review:** match properties and `autocad_modify_entity` write the
  layer last (moved first onto a locked layer, an object refuses its other properties; the answer
  still lists the layer first); a group whose objects cannot be added is not left behind empty.

## D-78 - Trim, extend, fillet, chamfer, break, join and stretch are worked out in Python

**Decided:** 2026-11-21, building issues #103 and #49. **Status:** in force; nothing here is proven
in AutoCAD yet (NEEDS-CHECKING group AA).
- **The geometry is Heron's own** (`acad/edit2d.py`, plain functions tested without AutoCAD, as
  the shape library is, D-30), not a typed TRIM or FILLET. A typed command waits for picks, and a
  command left waiting blocks everything after it (known limit 21). The tools read each object,
  ask the geometry for the new shape, and write it back by setting the object's own points:
  `StartPoint` / `EndPoint`, `StartAngle` / `EndAngle`, a polyline's `Coordinates` and bulges. Extra
  pieces are `Copy()` of the object, so layer, colour, linetype, extended data and the handle of the
  first piece stay. No plug-in change was needed.
- **In plan, on flat objects.** Everything is worked in world X and Y, as TRIM does with PROJMODE at
  its default. A sloping line, an arc or polyline on a tilted or flipped plane, and a polyline whose
  width changes along it are refused rather than flattened or stripped. One constant width is kept.
- **The rules a draftsman expects.** Trim removes the part pointed at, out to the next edge or to
  the end; edges count as drawn, not as if they ran on (EDGEMODE 0); edges are read once, before
  anything changes. Extend runs a straight end along its line and an arc end round its circle, to
  the nearest boundary ahead, both ends when no point is given. A closed polyline cut twice opens
  there; a circle cut or broken becomes an arc (a new object, so the circle's erase is asked about,
  D-50). Fillet and chamfer work on two lines (each keeps its end farther from the corner, or the
  side of `keep_points`; the new arc or line takes the first line's look; radius 0 is a sharp
  corner) or on one polyline's corners (it stays one polyline: bulges, D-30 rule 17). A corner next
  to an arc, or on a segment too short, is skipped and said. Join makes one line, one arc or one
  polyline, keeping the first object given where it can; a branch or a gap is refused with where.
- **Shape changes for #49**: `autocad_edit_vertex` (move, add, remove a polyline vertex; move a
  line's end) keeps the bulges, as a grip drag does; `autocad_stretch` moves the points inside a
  window, moves a circle, text, block or point whole when its base point is inside, and moves
  anything else only when it is wholly inside, listing the rest. No `Lengthen` yet ([#154](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/154)).
- **Safety:** an object on a locked layer is refused before anything is written, a failed write
  takes back the copies it made, the same object twice is refused, and a call with nothing to do
  opens no undo step (D-62). Each call is one undo step.
- **Added the same day, from an independent review of PR #153:** the copies are written before the
  object itself, so a copy that refuses leaves the object whole; an object's handle is read before
  it is written or erased; a fillet's new arc (or a chamfer's line) is made first and taken away if
  the lines refuse; join keeps a polyline it was given rather than making a new one; one rule for
  "straight" (a bulge under 1e-9, as `geometry.segments` has it) everywhere.

## D-77 - Quiet answers, and a busy answer names the command AutoCAD is in

**Decided:** 2026-11-21, from issues #44 and #47 (rows D8, D33). **Status:** in force; adds to
D-41, D-57 and D-62, which stand.
- **`quiet=true`** on `autocad_sequence`, `autocad_batch_draw`, `autocad_dimension_run` and
  `autocad_add_centre_marks` answers with counts and handles only (`core/quiet.py`). Numbers, words,
  `handle`, `handles` and every `..._handles` list (`new_handles` of a copy or an array) stay; the first 5 of what failed stay; every other list of objects goes and
  `left_out` says how many there were. Its handles are kept as `handles` when the answer had none,
  but never mixed into a `handles` already there (centre marks: the marks, not the circles). An object
  the call created keeps `{"created": true, "handle"}`, so Keep or Discard still finds what to take
  back. In a quiet sequence each step's answer is made quiet; a text answer is cut at 300 characters,
  an error never. Off by default, so every answer reads as before.
- **The plug-in's ping says `command`**: the command its tracker (D-41) sees the active drawing in,
  or null. It is read on the pipe thread, so it answers while AutoCAD is busy. An older plug-in
  leaves it out, and the server then says nothing about the command.
- **The gate asks only when a call ended on a busy AutoCAD**: `connection.busy_count()` goes up when
  the retry loop gives up on a busy AutoCAD (Outcome unknown, or "stayed busy") and when
  `autocad_run_lisp` never got to read its answer. Then the plain line names where AutoCAD is ("it is
  still in the HATCH command", "evaluating AutoLISP", "in no command now, so a redraw or a box held
  it") and what the plug-in counted so far ("after 2 added..." or "counted no drawing object ... so
  far"). Busy before anything was taken is REFUSED, "nothing was changed". A read gets one sentence
  in its answer instead, since a read has no plain line. The busy wording is used only when the
  answer itself says AutoCAD was busy: a sequence whose one step was turned away while the others
  drew is still DONE, "some parts failed".
- **An answer that never heard how the job ended is not DONE.** `autocad_run_lisp` with
  `timed_out: true` now reads OUTCOME UNKNOWN with the count so far; before, its line said DONE.
- **Left out:** a plug-in version bump (the parent session does it) and naming the command in the
  plug-in operations' own "Outcome unknown" (they already say it when AutoCAD never started them).
  Live rows Z5-Z9 NOT RUN.

## D-76 - An undo sent as a command is a write; long AutoLISP goes in pieces cut between forms

**Decided:** 2026-11-21, from issues #42 and #46 (known limits 3, 12, 21). **Status:** in force;
closes the gap D-15 named and replaces the 2,000-character refusal of 2026-11-09 for code of
several forms.
- **UNDO, U, REDO, MREDO and OOPS** through `autocad_send_command` are still sent outside an undo
  mark, but the write is marked just before the send. A busy AutoCAD after that is OUTCOME UNKNOWN
  in its own words ("sent twice, it would undo or redo one step more than asked"), never a second
  send. Busy before the send is still asked again: nothing reached AutoCAD. It also counts as a
  write for the gate, so `autocad_undo_last` no longer undoes past a raw UNDO. **The gate's own
  `UNDO _Back`** (Discard, and the end of a dry run) is marked the same way: a second Back would go
  past Heron's mark into the modeller's earlier work.
- **`autocad_run_lisp` cuts long code between its top-level forms** (`acad/lisp_forms.py`), never
  inside one, into pieces of at most 700 characters; several forms in one piece go inside
  `(progn ...)`. The pieces run in order inside **one undo mark**, each with the wrapper of known
  limit 21. A form up to 2,000 characters may stand alone; one longer is refused, with its number
  and how it starts. At most 12,000 characters and 20 pieces a call.
- **A piece that times out, leaves a command open or is refused stops the rest**, and the answer
  says which piece and what ran before it: a command split over two top-level forms is cancelled
  at the end of its piece, so the next piece would act on a half-done command. Stopped after a
  piece ran, the first line is OUTCOME UNKNOWN, never DONE or "nothing was changed".
- **The save, plot and export check reads the code as it is sent** (no comments), so a `"` inside a
  comment can no longer hide a `(command "_.QSAVE")` after it.
- **What is sent is compact**: comments go and spaces close up, outside strings only, so a `;`
  comment can never swallow the closing brackets on the command line, and the length counted is the
  code AutoCAD reads. Brackets and quotes are checked by reading the code, so `(princ "(")` is no
  longer refused. A busy AutoCAD as a piece is sent is now "Outcome unknown", not "check the LISP
  syntax". `USERS1` and `USERS2` are put back even when AutoCAD refuses the expression.
- **Left out:** catching a LISP error at once (`vl-catch-all-apply`) instead of waiting out the
  10 s; the wrapper stays as it was proven. Live rows Z1-Z4 and Z10 NOT RUN.

## D-75 - What a review of the new tools found, and the rules added

**Decided:** 2026-11-21, after an independent review of the code of PRs #124, #143 and #146.
**Status:** in force; adds to D-63, D-69 and D-70, which stand.
- **Excel's own typing is never written (D-69).** A number cell whose format shows it as a date, a
  time, a fraction or a percent (built-in formats 9-22, 27-36, 45-47, 50-58, or a custom format with
  d, m, y, h, s or %, quoted text left out) is read as `xlsx.Converted` and listed in
  `excel_converted`, not written: "1:100" typed in Excel would otherwise become "0.0694".
- **A tag named HANDLE, BLOCK or LAYOUT** gets " (tag)" after its column heading, and only the first
  column of each of those names is Heron's own. A row with values but no handle is listed.
- **A row is used only when its Block matches** the block that has that handle in this drawing; the
  workbook names the drawing it came from ("Exported from" on Read me), and the answer warns when
  it is applied to another one.
- **The folder check closes only what it opened (D-70):** decided by what AutoCAD had open before
  and after, never by the path alone.
- **Dry runs (D-63):** no UNDO mark is put down while AutoCAD is in a command (the mark would be
  typed into that command, and UNDO Back would then go past the job); a dry run that began no write
  and changed nothing counted sends no UNDO Back; a cancelled dry run still goes back to its mark,
  queued after the work on the COM thread.
- A cell reference with no column letter, a row past 50,000 or a column past Excel's last is a
  plain refusal, not a crash or a runaway list. A named button (D-74) goes to the first box with
  that title, so the field says to avoid a title many boxes share.

## D-74 - A command or expression may name one button for one box it expects

**Decided:** 2026-11-21, from Heron AI for Revit (issue #101, follow-up to D-66). **Status:** in
force. `autocad_send_command` and `autocad_run_lisp` take `expect_box` (the box's exact title) and
`press` (the button's text), both or neither. Before anything is sent, the server asks the plug-in
(`expect_dialog`, plug-in **1.7.0**) inside the running job; the plug-in takes it only from an
**Admin** job of this chat (a named button may be Yes or OK), one per job. `DialogWatch` presses
that button only on a box whose title is exactly the one named (ordinal, trimmed), only once, only
while that job runs, and only when the box has that button enabled; every other box still gets
Cancel, else No, else Esc. The note says `asked`, so the chat reads "Heron pressed Yes on it, as
this call asked", not "closed it". A refusal, or an older plug-in, stops the call before the
command is sent. The decision stays in `DialogWatch.cs`, tested offline.

## D-73 - AutoCAD always starts disconnected; no file can make it connect

**Decided:** 2026-11-21 by Ajmal PS, issue #141 (option 2 of three). **Status:** in force. Replaces
the "`autoConnect` stays a file setting" line of D-59.
`"bridge.autoConnect": true` in `heron-autocad.config` made AutoCAD connect to Heron at start without
the modeller's press of **Heron**. Every padlock was still off, so a chat could change nothing, but it
could read the drawing's name, path and contents without a click, and any program that can write
that file (an AI chat too) could switch it on.
- **Removed.** The plug-in no longer connects at start; the key is ignored like the old padlock
  lines. `HeronConfig` has no `AutoConnect` any more (a bridge test checks it stays gone).
- **Not taken:** keeping it with a warning in the docs (option 1), and allowing it only from the
  administrator's policy key (option 3). It was off on the owner's PC, so nothing changes for him;
  an office that wants it can ask for option 3 later.
- **Live row:** R10 (NOT RUN).
## D-72 - The offline gates run on Linux with pywin32 stand-ins; Windows-only tests skip, saying why

**Decided:** 2026-11-21 (issue #102). **Status:** in force. Cloud sessions run on Linux, where
pywin32 does not install, so three of the four gates could only say NOT RUN. `tests/winstubs/`
holds stand-ins (`pythoncom.com_error` and the `VT_*` numbers, a `VARIANT` that keeps its type and
value, `pywintypes.error`, the `ctypes` names `message_filter.py` needs); `tests/conftest.py` and
`tools/check_structure.py` put them on the path **only** when `pythoncom` cannot be found, so on
Windows and in Windows CI nothing changes. They talk to nothing. The tests that need Windows itself
are marked to skip off Windows with the reason: real named pipes (8 in `test_bridge.py`, and the C#
`[WindowsFact]` server test), the COM message filter on a real thread (5), Windows path rules (5),
CRLF in a Windows checkout (1). The stand-ins are test code, never a dependency of the server.
**Later the same day:** `.gitattributes` now gives `tools/release_files/*` CRLF on every checkout, so
a release built on any machine has Windows line endings, and that one test runs everywhere again.

## D-71 - The Companion page is a file per chat, not a server

**Decided:** 2026-11-21, from Heron AI for Revit's companion page (its docs/40, D-108; issue #91).
**Status:** in force. `autocad_companion` (Read) writes one HTML file per chat in
`%LOCALAPPDATA%\Heron\autocad\companion`; after that the gate rewrites it after every job in
that chat (`core/companion.py`, `gate.companion_state()`), and it reloads itself every 5 s. No
port, no listener, no script (a Content-Security-Policy of `default-src 'none'`), every value
escaped, so there is nothing on the PC to reach. The page shows only what the gate already holds
(activity, the drawing last checked, what `autocad_undo_last` could take back) and what
`autocad_companion` read in its own Read job (drawing, units, layout, view, selection, with the
time): no COM outside a job. Writing it never fails a job. Pages older than 7 days are removed.
Revit's editable tables and dashboard need the page to send things back, so a local server with
a token: left for a decision of its own. Design: [13 §3](13-sheets-folders-companion.md).

## D-70 - A folder of drawings is checked read only, one at a time, as a View tool

**Decided:** 2026-11-21, from Heron AI for Revit (its D-181, accepted there, not built; issue
#97). **Status:** in force. `autocad_check_folder` opens each `.dwg` read only, runs the check
list with that drawing's own project changes (`run_list(..., doc_of=...)`, the same code as
`autocad_checklist`), and closes it unsaved; a drawing already open is checked where it is and
left open; the modeller's drawing is made active again at the end. It changes which drawing is
open, never what is in one, so it is a **View** tool (like `autocad_open_drawing`) and needs no
Changes padlock. A drawing that will not open is NOT RUN with AutoCAD's reason; HERONSTOP leaves
the rest out. Not ObjectDBX: a database opened that way has no selection sets or system
variables, which the checks read. Design: [13 §2](13-sheets-folders-companion.md).

## D-69 - Attributes go to Excel and back; only the cells the modeller changed are written

**Decided:** 2026-11-21, from Heron AI for Revit (its D-182, D-183; issue #96). **Status:** in
force. Two tools, because a tool's padlock is a property of the tool (D-65):
`autocad_export_attribute_sheet` (Publish: it writes a new `.xlsx` next to the drawing, never over
one) and `autocad_apply_attribute_sheet` (Change). The workbook has an **Attributes** sheet to edit
and an **As exported** copy, so the compare (`acad/attribute_sheet.py`, offline) tells the
modeller's edit (written) from a change made in the drawing since (kept) and from both (a
conflict, listed, not written). A blank cell never empties an attribute. Only changed cells are
written, in one undo step, listed old -> new (`before_after`, D-62); nothing to write opens no undo
step. A `.csv` with a Handle column is accepted and compared with the drawing alone. The `.xlsx`
is written and read with the standard library (`acad/xlsx.py`): no new package. Design:
[13 §1](13-sheets-folders-companion.md).

## D-68 - One docked Heron palette: Activity with Undo by D-54's rule, saved commands run by a copy of the server

**Decided:** 2026-11-21, from Heron AI for Revit's Activity and Commands panes (issues #92, #93).
**Status:** in force; supersedes the last sentence of D-55 (a command run with no AI is now copied).
`HERONPALETTE` (or Heron > **Heron palette** on the ribbon) opens one `PaletteSet`, docked right,
with two tabs drawn in Heron's window style (D-45: Surface card, top strip, Ink header with the
heron, Ink insets, brand buttons); the palette's own title bar stays AutoCAD's. The rules live in
the bridge, tested offline (`ActivityLog`, `SavedCommandList`, `PaletteServer`); the add-in only
shows them and makes the AutoCAD calls.

- **Activity** lists Heron's change jobs (Change, Admin, Publish) in this AutoCAD, from every chat,
  newest first, 30 kept, with what the plug-in counted (D-50). Reads and views are left out.
  **Select** and **Zoom** take what the job made or changed (up to 500) and work whichever chat
  holds this AutoCAD, but not while a job runs, and only in the job's drawing. The palette's Zoom
  runs with undo recording off, so it leaves no step between the job and its Undo.
- **Undo** belongs to the modeller, like Ctrl+Z: no padlock, no chat, any chat's job. It uses
  D-54's rule, from what the plug-in itself knows: Heron's newest change job in this AutoCAD, a
  Change job that ended `done` and changed something, not itself an undo, in the drawing in front,
  nothing changed outside Heron's jobs since it ended (`JobChanges.ChangedSince`), UNDO on with more
  than one step (UNDOCTL), and with no UNDO mark (Ask to Keep was off at begin) no Heron zoom or show
  since. With the mark it is `UNDO _Back`, else `UNDO 1`, typed into AutoCAD; when UNDO ends,
  Heron checks that what the job made is gone, as `autocad_undo_last` does. Anything else is
  refused with the reason in plain words. A chat's `autocad_undo_last` stays limited to its own job;
  after a palette Undo it is refused, because the drawing changed since.
- **Saved commands** reads the files the server saves (`%LOCALAPPDATA%\Heron\autocad\commands`,
  D-55) every 2 s while the tab is open, so a command saved in a chat shows without a restart;
  search, fill the inputs (each typed value takes its example's type, a blank with a default is
  left to the server), **Run**. Run does not go round the gate and the plug-in does not replay the
  steps itself: it starts a copy of the server for that one run
  (`python -m autocad_mcp --run-saved request.json --acad-pid <this AutoCAD>`), which is a chat of
  its own to the plug-in. It runs `autocad_status` first (units, D-19), then `autocad_saved_command`
  through the same gate, hold, padlocks, Keep or Discard, erase question and HERONSTOP, prints one
  line `{"ok", "message"}`, and releases the hold so the modeller's chat is not kept out for 3
  minutes. While a chat holds this AutoCAD, Run is refused with "in use by another chat", as for any
  second chat. Every server writes `%LOCALAPPDATA%\Heron\autocad\server.json` (its Python) when it
  starts; that is how the palette finds one, so Run needs Heron to have run once on this PC.
- **Not copied:** a separate Commands pane (one palette with two tabs instead), and asking a
  running chat's server to run it (a stdio server has no way in from the plug-in).
- **Added after the merge (same day):** the palette's run never inherits a way round the gate or
  another chat's id from the environment AutoCAD was started with: `HERON_AUTOCAD_BRIDGE` is forced
  on, `HERON_CONVERSATION_ID` and `CLAUDE_CODE_SESSION_ID` are dropped (`PaletteServer.
  PrepareEnvironment`), and the server refuses `--run-saved` with the checks off. A job whose end
  never came stops counting as running after 20 minutes (`ActivityLog.MostJob`). While a palette Undo
  waits for AutoCAD, the plug-in refuses a new job's begin with a plain "try again" (`BlockedBy`,
  at most one minute), so the UNDO never lands inside a chat's job (#138).

## D-67 - Finding and explaining: why a job cannot run, what failed, a question gets a read tool

**Decided:** 2026-11-21, from the comparison with Heron AI for Revit (issues #88, #89, #90, #43).
**Status:** in force. Adds to D-48 and D-49. The ideas are Revit's `heron_why`, `heron_gaps` and
its question mode; the code is this project's own.

- **`autocad_why`** (Read) takes a job in plain words, finds its tool with the same search as
  `autocad://tools/find`, then lists what is in the way, worst first, each with what to do: no
  tool, a read-only server, the plug-in not installed, nothing connected, two AutoCADs and none
  picked, server and plug-in from different releases, a plug-in older than the tool needs (read
  from the tool's own "plug-in X or newer" line, so it cannot drift), a padlock off, an update the
  chat has not loaded. It says what it cannot see from files: an open command, a locked layer,
  another chat holding AutoCAD.
- **`autocad_gaps`** (Read) sums up the last N days (1-90) of the audit log: calls per tool,
  failures grouped by a plain reason with what to do, the slowest jobs. Drawings by file name
  only; reading the log (`autocad_gaps`, `autocad_why`) is not counted.
- **The audit line gets a `reason` word** when a call is refused or fails, from a fixed list in
  `core/audit.py` (`changes_off`, `not_connected`, `autocad_busy`, ...), worked out from the
  message. Only the word is kept, never the message, because a message can name layers, handles or
  folders. Lines written before this read as `other`.
- **Both tools need no AutoCAD.** The gate runs them like `autocad_use_autocad` (D-49): through
  `guarded`, audited, but without looking at AutoCAD first (`gate.NO_AUTOCAD_TOOLS`). They read
  only Heron's own files. Not a way round the gate: they are Read, touch no drawing, and the set
  is named in one place.
- **A plain question never gets a change tool first.** `autocad://tools/find/{phrase}` treats
  "how many...", "what ...", "which...", "is there..." as a question: the matches are only tools
  that read, and anything else that matched is listed apart under `would_change_the_drawing`.
  "does" and "do" are left out on purpose: "does the ductwork clash" is answered by
  `autocad_check_interference`, which makes solids. Measured on `tests/test_find_tool.py`: 84 of
  97 phrases first (80 before) and 97 of 97 in the top three (96), plus 13 new question phrases.
- **The audit folder never becomes relative** (#43): with `%LOCALAPPDATA%` unset, empty or not a
  full path, it is `~/AppData/Local/Heron/autocad/audit`, where Windows normally points it.
  `bridges_dir()` has the same pattern and is left for its own change.

- **Changed the same day by D-59** (the padlocks moved into AutoCAD's memory): `autocad_why`
  can no longer read them, so it names the padlocks a job needs (`needs_changes`, ...) as
  reasons that do not block, says it cannot see whether they are on, and never claims one is
  off. The refusal itself still names the padlock, and `autocad_gaps` counts it. A `dry_run`
  refusal (D-63) is logged with the reason word `no_dry_run`.
- **Changed again the same day (#140):** the plug-in's `ping` now carries its padlocks, so
  `autocad_why` asks the AutoCAD this chat works in and says which are on; only with no answer
  does it fall back to naming them without guessing (D-59, "Added 2026-11-21, after the merge").

Pinned by `tests/test_why_and_gaps.py` and `tests/test_find_tool.py`. Live rows: Group W.

## D-66 - A box AutoCAD opens during a Heron job is closed with Cancel and named

**Decided:** 2026-11-21, from the comparison with Heron AI for Revit (issue #83). **Status:** in
force; NOT RUN live (NEEDS-CHECKING group V). Adds to D-57 and [05 §24](05-known-limits.md#24-a-busy-autocad-turns-calls-away).
A box AutoCAD opens mid-job (a file dialog from a typed command, "Save changes?", an error message)
stalls every later call until the modeller presses Esc. Heron for Revit answers such a popup with
"no" and tells the chat; this is the same idea, written fresh for AutoCAD.
- **How it looks:** a background timer in the add-in, every 250 ms, only while a job runs, reads
  `GetLastActivePopup` of AutoCAD's main window. Chosen over `SetWinEventHook`: a hook needs a
  message loop on its own thread and fires for every object in the process, while a short poll
  during a job is all that is needed and starts and stops with the job. Nothing it calls sends a
  message to AutoCAD's windows (`InternalGetWindowText`, `PostMessage`), so a hung AutoCAD cannot
  hang it.
- **Which window counts** (`Heron.AutoCAD.Bridge/DialogWatch.cs`, tested offline): only while a job
  runs; only a modal box (AutoCAD's main window disabled) that can take input and has stood for
  400 ms; never a window that was open when the job began (that is the modeller's); never a Heron
  window ("Heron - ..." and the banner) and never while Heron's own Keep or Discard or erase
  question is up.
- **What it presses:** Cancel, else No, else Esc (a standard box gets its Cancel command, any
  other its ✕, which WPF, WinForms and MFC all treat as Cancel). **Never OK, never Yes.** One press
  per box; after 5 boxes in one job Heron stops pressing and says so.
- **What the chat is told:** a new op `dialogs {job}`; the server asks it after every job's work
  and adds `heron_dialogs` to the answer: "AutoCAD showed 'X'; Heron closed it with Cancel,
  nothing was kept from that step." A box still open after 2 s is said too, with "close it, read
  the drawing back". An older plug-in answers "unknown op", which means no boxes.
- **Not done:** a box the modeller opens *themselves* while a job runs cannot be told apart and is
  closed too ([05 §25](05-known-limits.md#25-the-dialog-watch-closes-every-new-box-in-a-job)).

## D-65 - A check list run is saved by its own Publish tool, as new files only

**Decided:** 2026-11-21, from Heron AI for Revit's QA reports (its D-178); issue #86. **Status:** in
force. `autocad_checklist_report` runs a list exactly as `autocad_checklist` does and saves the run
next to the drawing as `<drawing> - checklist <list> - <date>.xlsx` and `.html`. It is a separate
tool, at **Publish**, and not a `report` option on `autocad_checklist`: a tool's padlock is a
property of the tool and is never worked out from what the caller passes (`core/risk.py`), so a
"save" option on a Read tool would have written files with the Publish padlock off. Never
overwrite: when either file of the pair is there, the next number is used (` (2)`, ` (3)`, at most
999), and each file is opened in exclusive-create mode, so a file that appears in between is not
replaced either; if the page cannot be written the workbook just made is removed. An unsaved
drawing has no folder and gets no report. The workbook is written with the standard library (an
`.xlsx` is a zip of XML parts): `openpyxl` was not a dependency, and adding a package means every
PC reinstalls ([05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)) for one sheet of
text. Known limit: one sheet, text and numbers only, no colours in Excel (the HTML page has them).
**Later the same day:** the workbook is now written by `acad/xlsx.py` (D-69's writer), so Heron keeps
one `.xlsx` writer: a Summary sheet and a Check list sheet with its header row frozen; every cell
is text. Still no colours in Excel.

## D-64 - Check lists: NO DATA, office lists with project changes, PASS is not "complies"

**Decided:** 2026-11-21, from Heron AI for Revit's D-165, D-169 and D-179; issues #84, #85, #87.
**Status:** in force. Extends [D-52](#d-52---check-lists-are-the-modellers-sentences-on-a-fixed-catalogue).

- **Four results.** PASS (the checked value is met), FAIL, **NO DATA** (could not decide: what the
  check needs is missing - no such title block, xrefs unreadable, no text to compare, or only part
  of the objects read when nothing wrong was found in that part) and NOT RUN (switched off for this
  project). NO DATA is never counted as a PASS: the verdict is FAIL if anything failed, else NO DATA
  if anything could not be decided, else PASS. Before this, a missing title block was NOT RUN and a
  run capped at `max_entities` could still say PASS. The same holds for title blocks, and for
  `autocad_check_standards`: after a capped read with nothing found, `passed` is `null`, not `true`.
- **Coverage line on every run:** "2 of 4 decided, 1 no data, 1 not run" (decided = PASS + FAIL).
- **Office and project.** The office list is the saved list,
  `%LOCALAPPDATA%\Heron\autocad\checklists\<name>.json`, as in D-52 ('before issue' ships with
  Heron); an office shares one by copying that file to each PC. A project's changes are kept per
  project folder (the folder the drawing is saved in, as for the notes, D-53) in
  `%LOCALAPPDATA%\Heron\autocad\checklists\projects\`, never in the drawing or its folder. A
  change names an office check by its `id` and may set only **severity**, **target** (new values for
  that check's own parameters) and **on**. Adding a check, or changing what one does (its check,
  label, clause, advice, or a parameter it does not have), is refused naming the line: no hidden
  logic in a project. If the office list changes so a project change no longer fits, the run stops
  and says how to set or clear them. Each run names every check it used (`checks_used`) and where
  it came from (office / project), and a changed line says what changed from what.
- **PASS is not "complies".** PASS means the checked value is met, for what Heron read, against the
  source named on the line (its clause, else the list). `autocad_checklist`,
  `autocad_checklist_report` and `autocad_check_standards` carry the same `pass_means` sentence; no
  answer says a drawing complies; [DISCLAIMER.md](../DISCLAIMER.md) says it in plain words. Heron
  never signs a drawing off.
## D-63 - Any change tool can run as a dry run, inside Heron's UNDO mark

**Decided:** 2026-11-21, from Heron AI for Revit (its D-155). **Status:** in force.
`dry_run=true` on any Change tool runs the job for real inside an UNDO mark (D-18), takes the
plug-in's count, then goes `UNDO _Back` to the mark and checks every object it made is gone, the way
Discard does. The answer is the tool's own answer with `NOTHING CHANGED - a dry run: it would have
made ...` first (D-62); the handles in it no longer exist, and it says so. No Keep or Discard and no
erase question are asked, since nothing is kept; the banner says "Dry run: ...". The gate gives it,
so no tool was edited: `tool_errors` adds the argument to every Change, Publish and Admin tool that
has no `dry_run` of its own, and passes it to the gate, never to the tool. Tools that already had
one keep their meaning: a preview that writes nothing (annotate, convert, dimensions, patterns,
settings, shapes, text tools, sequence, saved commands). Refused before anything is sent: every
Publish and Admin tool (a file written, a command or AutoLISP run cannot be taken back by an UNDO
mark; the argument is there so a dry run is refused, never ignored and run for real), and
`autocad_undo_last`. A dry run needs UNDO on (UNDOCTL), or it is refused and nothing runs. If going
back fails, or a new object is still there, the answer is OUTCOME UNKNOWN, naming them. A dry run
leaves nothing for `autocad_undo_last`, since the undo history moved. A step inside a sequence
cannot be a dry run on its own. Not proven live: that `UNDO _Back` takes back every kind of change
(layers, variables, plug-in operations) as it does objects (rows T4-T5).

## D-62 - Every change answers with one plain line first

**Decided:** 2026-11-21, from Heron AI for Revit (its D-168, and its failure answers).
**Status:** in force. A Change, Admin or Publish job's answer starts with one line: `DONE`,
`NOTHING CHANGED`, `REFUSED` or `OUTCOME UNKNOWN`, a dash, one plain sentence; then a blank line and
the tool's own answer, unchanged. It is added in one place, the gate (`core/answers.py`, called from
`core/gate.py`), so no tool can forget it, and saved-command runs and sequences get it the same way.
The word comes from facts, not from what the tool says it did: the plug-in's count of objects added,
modified and erased (D-50), whether a write began at all, Keep or Discard, and whether Heron's UNDO
mark (D-18) was down. Rules: a padlock or guard refusal is REFUSED (nothing was sent); a tool error
with nothing counted is REFUSED; a tool error after objects changed, or "Outcome unknown", is OUTCOME
UNKNOWN and says whether the UNDO mark is there; a Discard is NOTHING CHANGED; a Change job that
began no write is NOTHING CHANGED. The count is of drawing objects only, so a job that wrote and
counted nothing (a new layer, a variable) is DONE, said carefully, and Admin and Publish jobs are
never NOTHING CHANGED (a save, a command or a variable is not counted). Only with the plug-in on:
with `--no-bridge` there is no count, so there is no line. Reads and views have none. Scripts and
tests that parse answers drop the line with `answers.body()`; steps inside a sequence still see the
tool's own answer, so "Error:" still starts a failed step there.
**Before and after** (from Revit's D-156): `autocad_modify_entity`, `autocad_set_attributes`,
`autocad_find_replace_text`, `autocad_set_dynamic_properties`, `autocad_create_layer`,
`autocad_set_layer_state`, `autocad_set_current_layer`, `autocad_delete_layer`,
`autocad_set_variable` and `autocad_drawing_setup` add `before_after`: one row per value changed,
naming the object (`handle`, or `layer` / `variable`), the `property`, `from` and `to`; the first 50,
then `before_after_more` counts the rest. They read each value first and write only what differs, so
asking for what is already there writes nothing and leaves no undo step; an empty `before_after`
then lets the line say NOTHING CHANGED even for a layer or a variable, which the count cannot see.
**No empty undo step** (issue #80, Revit's D-160): only that part is done. A kept job that changed
nothing is not taken back afterwards, because whether AutoCAD keeps an entry for an empty undo group
or a lone mark is not known; one more `UNDO` would then undo the modeller's own last change. Written
up in [05 §26](05-known-limits.md#26-a-job-that-changed-nothing-may-still-leave-an-undo-step), live
row T7.

## D-61 - A chat reopened after a restart keeps its hold

**Decided:** 2026-11-21, from Heron AI for Revit (its D-188). **Status:** in force.
The plug-in lets one chat at a time into an AutoCAD (the hold). Each server process made a new chat
id, so when the Claude app restarted and reopened the same chat, the new server was a stranger and
its own hold refused it for three minutes. The server now takes its id from, in order:
`HERON_CONVERSATION_ID` (a script or a developer fixes it); then the host's own chat id,
`CLAUDE_CODE_SESSION_ID`, as `sha256("heron-conversation:" + id)`, first 32 hex characters (the
host's id is never sent as it is); then a new random id. The same chat gives the same id; two chats
give two. Only the server itself follows the host (`follow_host_chat()` in `server.main`): a
command-line script such as `tools/live_check.py`, run from a chat's terminal, imports the same
modules but stays its own chat, so it never takes or keeps that chat's hold by accident, and
`tools/protocol_check.py` starts its server without the host's variable. Not proven live: whether
Claude Code passes that variable to MCP servers, and keeps it on a resumed chat (row T1). Without
it, nothing changes: a new id, as before.
## D-60 - A Windows policy can hold a padlock off

**Decided:** 2026-11-21, from issue #77 (the idea of Heron AI for Revit's D-166, layer 3; no files
copied). **Status:** in force.
For an office that installs Heron for many modellers. The plug-in reads
`HKLM\SOFTWARE\Policies\Heron\AutoCAD`, its own key, so an office can set AutoCAD apart from Revit.
DWORD values `AllowChanges`, `AllowPublish`, `AllowAdmin`: **0 holds that padlock off**. The text
"0" counts too, for a value typed as a string by mistake. 1, any other number, no value or no key
leaves the padlock to the modeller.
- **Read fresh on every call**, so a policy pushed while AutoCAD runs applies at once. A padlock it
  holds is also put off in memory: lifting the policy never turns it back on without a click.
- **Shown:** Settings draws the padlock as **HELD**, with "A Windows policy on this PC holds this
  off.", and it cannot be pressed. A chat is told "Changes is held off by a Windows policy on this
  PC ... Only the PC's administrator can lift it." (`Texts.ChangesHeld` and the Publish and Admin
  ones). The refusal stays `refusedBy: "Changes"`, so the server needs no change.
- **A key that cannot be read holds nothing.** Only an administrator can make HKLM unreadable or
  write it, so failing open here gives no program the modeller runs any power. The 64-bit view is
  read, as AutoCAD 2021 and later is 64-bit only.
- **Ask to Keep has no policy.** Not asked for; easy to add the same way.
- **Tested off Windows:** the reading sits behind `IHeronPolicy`; the bridge tests use a fake, and
  the real `WindowsPolicy` is only checked never to throw. Live rows R5-R7 NOT RUN.

## D-59 - The padlocks live in AutoCAD's memory; no file can turn one on

**Decided:** 2026-11-21, from issue #76 (the idea of Heron AI for Revit's D-166; no files copied).
**Status:** in force. Replaces the "saved in a file, read fresh on every call" part of D-16 and
[06](06-heron-plugin.md); the fail-closed rule of D-16 stays for what the file still holds.
The padlocks were saved in `%APPDATA%\Heron\autocad\heron-autocad.config` and read on every call,
so any program that can write a file, an AI chat included, could turn one on without the
modeller's click, skipping "turning a padlock on asks first".
- **In memory only** (`Bridge/HeronPadlocks.cs`). Every AutoCAD starts with Changes, Publish and
  Admin **off**. Nothing is read from or written to a file for them.
- **Ask to Keep starts off, as before** (Ajmal's choice, 2026-11-21), and lives in memory too: no
  file can switch it on or off. A modeller who wants it turns it on in Settings after each AutoCAD
  start.
- **Only the modeller's click moves a switch:** in Settings, or in the same question
  `HERONCHANGES` / `HERONPUBLISH` / `HERONADMIN` open (kept for command-line users; they ask exactly
  as Settings does, and a typed command sent by a program still needs that click). Turning off
  still never asks. The pipe has no request that reaches the padlocks.
- **Each open AutoCAD has its own padlocks.** Before, the file shared them between AutoCADs. Own
  padlocks are the simple answer: what the modeller unlocked is the AutoCAD in front of them.
- **The file keeps** `bridge.autoConnect` and `ui.activityBanner` only. The old padlock lines are
  ignored, never read, and the plug-in no longer writes the file. `autoConnect` stays a file
  setting: it only connects, and with every padlock off a chat can then read but change nothing.
  Since D-73 `autoConnect` is ignored too.
- **`autocad://diagnose`** no longer reads padlocks from the file: it would have reported stale
  lines as on.
- **Added 2026-11-21, after the merge:** `autocad_why` (D-67) still read the padlocks from that
  report, so it said every padlock was off even with Changes on. Now the plug-in's `ping` answer
  carries `padlocks` (changes, publish, admin, askToKeep) and `held` (what a D-60 policy holds),
  read-only; `autocad_why` asks the AutoCAD this chat works in, and a held padlock gets its own
  reason (`admin_held`: ask the PC's administrator) instead of "type HERONADMIN". No answer
  (nothing connected, several and none picked, a plug-in older than 1.6.0) keeps #134's rule: the
  padlocks are named (`needs_changes`...), never guessed, and do not block. Pinned by
  `tests/test_padlocks_from_plugin.py` and the bridge `PadlockTests`.
- **Added 2026-11-21, the guard's two gaps (issue #142):** it now also refuses an Edit or Write of
  a script (`.ps1`, `.bat`, `.cmd`, `.py`, ...) whose content would write either target when run
  later, except in this repository's own `tests/` and `.claude/hooks/`. For `gh` and `git`
  commands it no longer looks inside quoted text (an issue body, a commit message), so mentioning
  the file is not taken for writing it; a redirect outside the quotes is still refused.
- **A guard for Claude Code in this repository:** `.claude/settings.json` runs
  `.claude/hooks/guard_padlocks.py` before every Edit, Write and shell command, and refuses one that
  would write `heron-autocad.config` or the D-60 policy key (exit 2). It catches the plain ways, not
  every way: it is the second guard, the first is that no file can turn a padlock on. If Python
  cannot be found the step goes ahead with a warning, so a fresh clone is never locked out.
  `.gitignore` keeps everything else in `.claude/` (local settings, worktrees) out of git.
- Tested offline: `PadlockTests`, `ConfigTests` (bridge), `tests/test_padlock_guard.py`,
  `tests/test_diagnose.py`. Live rows R1-R4 and R8 NOT RUN.

## D-58 - autocad_run_lisp waits through refused reads; it puts the variables back patiently

**Decided:** 2026-11-20, from the Luxury Suite 3 rehearsal of 2026-11-18. **Status:** in force.
After a layer-off or a `-VIEW _R` of a camera view in a heavy realistic drawing, `autocad_run_lisp`
said "timed out" in 0.2-0.5 s for an expression that had run: the first read of USERS1 that AutoCAD
refused while redrawing ended the wait. Now a refused read is not an answer: the wait goes on to its
bound, `LISP_POLL_ATTEMPTS` reads and `LISP_POLL_ATTEMPTS x LISP_POLL_DELAY` (10 s), whichever comes
first; with the D-57 filter's 3 s for the whole call and the restores, a still-busy AutoCAD gets an
answer in about 15 s at most. If AutoCAD never let one read through, the note says it
stayed busy and the expression probably ran, not "a LISP error". USERS1, USERS2 and OSMODE are put
back with up to `LISP_RESTORE_TRIES` (5) tries each; one still not put back is named in the note,
so his object snaps are never left off without a word. Pinned by `tests/test_busy_autocad_1118.py`.

## D-57 - A call AutoCAD turns away is asked again by a message filter, not by re-running the tool

**Decided:** 2026-11-20, from the same rehearsal. **Status:** in force. Adds to D-02 and keeps D-15.
`autocad_create_layer` stopped with "Could not create layer 'A-ANNO-TTLE': Call was rejected by
callee." while drawing tabs were switched. The tool-level retry of D-02 already existed; it never
saw the refusal. `ensure_layer` read the refused `Layers.Item` as "no such layer" and wrapped the
refused `Layers.Add` in a plain error; and since `undo_mark` had begun, D-15 would have refused a
re-run anyway. A second retry loop in `connection.run` would have changed nothing.
The fix works one COM call at a time. `RPC_E_CALL_REJECTED` and `RPC_E_SERVERCALL_RETRYLATER`
mean AutoCAD turned the call away without carrying it out, so asking for that one call again can
never draw anything twice. `core/message_filter.py` registers a COM message filter on the worker
thread. pywin32 has no `CoRegisterMessageFilter`, so it is a small static ctypes object.
- **The filter's rule:** its `RetryRejectedCall` asks again after 100 ms (250 ms after the first
  second), for those two refusals only. Anything else goes straight back. If Windows refuses the
  filter, Heron works as before.
- **The budget is per job, not per call:** `BUDGET_MS` (3 s) is the most one piece of work on the
  worker waits, in all. The worker resets it as it picks up each job. Many places swallow a
  refused call and go on to the next, so 3 s for each call would have held the only COM thread
  for minutes. Once a job has spent its 3 s, every refusal fails fast, as before.
- **The tool-level window:** `_with_retry` now also stops at `RETRY_WINDOW` (10 s), so its 40
  attempts can never be stretched past that by the filter's waits.
- **The wording:** `com_message` words those two refusals as "AutoCAD was busy and kept turning
  the call away", so the dozens of messages built from it say busy, not broken.
- **The swallowed refusals:** `ensure_layer` and `ensure_linetype` let a busy refusal go up as it
  is, instead of taking it for a missing name.
- **Left out:** the optional `dim_style` input for `autocad_dimension_run`. It cannot be proved
  without AutoCAD, and done wrong it gives wrongly sized dimensions
  ([ROADMAP](ROADMAP.md)). Live rows Q1-Q5 NOT RUN.

## D-56 - The installer keeps the version it replaces; releases are built from a tag

**Decided:** 2026-11-15, from Heron AI for Revit's installer (install-backup, the update check
that never installs, the check after install, the Store-app trap) and its release workflow.
**Status:** in force. `Install.ps1` reads both versions from `PackageContents.xml`, copies the
installed bundle and server to `%LOCALAPPDATA%\Heron\autocad\previous` before replacing them,
puts them back if the copy fails, and checks the version and the server's size afterwards.
`Rollback.bat` shows both versions and asks before swapping back. `CheckForUpdate.bat` asks GitHub
for the latest release and only says so. A folder under `AppData\Local\Packages` is refused,
because files written from an app's private storage never reach AutoCAD. `release.yml` builds on
GitHub's Windows machine from the tagged code, refuses a tag that is not `v` + the version in
`Directory.Build.props`, writes the zip's SHA-256 to `checksums.txt`, and publishes a pre-release.
The bundle's `AppVersion` is read from `Directory.Build.props`, so it can never differ from the
DLLs' version again.

## D-55 - Saved commands are sequences with named inputs

**Decided:** 2026-11-15, from Heron AI for Revit's saved commands (its docs/49). **Status:** in
force. A job worked out once is kept on this PC as the very steps `autocad_sequence` takes, with
`{{input}}` where a value changes; a value that is a whole `{{input}}` keeps its type (a number
stays a number). Saving checks every step as a sequence would, with each input's example, and
refuses an input used but not declared, declared but not used, or without an example. Running
fills the inputs and calls the sequence's own body inside the saved command's one job: the same
gate, Changes padlock, Keep or Discard and HERONSTOP check between steps. A saved command cannot run
another, and a sequence cannot hold one. Heron AI's docked palette that runs a command with no AI
is not copied: the server lives in the chat, so the chat runs it, with one call and no planning.

## D-54 - "Undo Heron's last change" only when nothing else changed since

**Decided:** 2026-11-15, from Heron AI for Revit's undo guard (its D-157). **Status:** in force.
Ctrl+Z undoes whatever came last, which may be the modeller's own work. `autocad_undo_last` undoes
Heron's last change in this chat only when: it is the active drawing; the plug-in saw no entity
added, modified or erased outside Heron's change jobs since (`since_last`, from the same database
events as D-50); and Heron itself did nothing since but read. With Ask to Keep on, the job's UNDO
mark makes it exact (`UNDO _Back`, then the created handles must be gone). With it off there is no
mark (D-18 is kept: no mark unless asking), so it is one `UNDO 1`, refused if Heron zoomed or showed
anything since, because that step would be the zoom. A raw command or a save after the change
leaves nothing to undo this way. One level only. `autocad_activity` lists the chat's jobs (reads
left out) from the gate's own record.

## D-53 - The modeller's answers are kept per project folder

**Decided:** 2026-11-15, from Heron AI for Revit's design basis (its D-33, and its lesson D-113: an
id inherited from the template made new projects reuse another project's answers). **Status:** in
force. A project is the folder a drawing is saved in, which a template cannot carry over; an unsaved
drawing keeps nothing. `autocad_project_notes` keeps a short named answer with the modeller's own
words and the time, in `%LOCALAPPDATA%\Heron\autocad\projects`, never in the drawing.
`autocad_status` hands them to every chat as `project_notes`, and the server instructions say: use
them, ask only what is missing, keep only what the modeller said.

## D-52 - Check lists are the modeller's sentences on a fixed catalogue

**Decided:** 2026-11-15, from Heron AI for Revit's QA checklists (its docs/50). **Status:** in
force. A check list is a named list on this PC; each line is the modeller's own sentence mapped to
one of nine catalogue checks (layer 0, Defpoints, ByLayer colour and linetype, overlapping
dimensions, layer names by pattern, xrefs found, title blocks filled, text heights), with severity,
clause and advice. Running reads the drawing once and changes nothing; each line is PASS, FAIL or
NOT RUN with the reason, never a silent pass. "before issue" ships with Heron. No free-text rules:
a check Heron cannot do is refused when the list is saved, naming the line.

## D-51 - An emergency stop the modeller presses in AutoCAD

**Decided:** 2026-11-15, from Heron AI for Revit's `HeronStop` (a stop message, sticky until
restart). **Status:** in force. **Stop Heron now** in the Heron menu, or `HERONSTOP`, marks the
plug-in stopped: `begin`, `send_quiet` and `run` are refused with "The modeller stopped Heron",
while `end`, Keep or Discard, `changes` and the erase question still answer, so a stopped job can be
put back. The command running now gets Esc. `ping` says `stopped`, and `autocad_sequence` asks
between steps. A refused `send_quiet` used to make the server type the batch over COM itself; for a
stop it now ends the call instead. Sticky until picked again (not until restart: the modeller has
no other way to lift it without closing AutoCAD). Known limit: a batch already handed to AutoCAD's
input queue runs to its end; Esc in AutoCAD is the only way to cut it.

## D-50 - The plug-in counts what a job really did; every erase gets a human yes

**Decided:** 2026-11-15, from Heron AI for Revit's changed-set report and delete question (its
D-142). **Status:** in force. The server only knew what a tool said it did, and the delete check
was the chat setting its own `confirm=true`. Now the add-in hooks `ObjectAppended`,
`ObjectModified` and `ObjectErased` on every drawing and counts (`JobChanges`) while a Change, Admin
or Publish job runs: entities added and modified; entities and table records (layers, blocks,
styles) erased. An object made and erased in the same job is neither; one an UNDO brings back is no
longer erased. The server adds the count to the result (`heron_changes`) and, when the job erased
anything and Keep or Discard is not being asked, asks the plug-in to ask the modeller
(`ask_erase`). Anything but a clear "keep them erased" un-erases them in one transaction; if the
box could not be shown in time, they are brought back as soon as AutoCAD is free.

## D-49 - One AutoCAD connected is the one; two need a pick, and Heron never moves on

**Decided:** 2026-11-15, from Heron AI for Revit's session binding (its docs/25). **Status:** in
force; closes A15. `GetActiveObject` gives whichever AutoCAD registered first. Heron now reads the
address files the Heron button writes: one AutoCAD connected is used whatever COM gives; two or more
and none picked refuse every call but `autocad_use_autocad` (which runs without probing a drawing,
like status, and is audited); a picked one that closes or disconnects stops Heron with "never moves
on". A second AutoCAD is reached through one of its open drawings in Windows' Running Object Table,
so an AutoCAD with no saved drawing open cannot be reached, and says so. Picking resets the units
check: the other AutoCAD's drawing may be in other units.

## D-48 - "Diagnose Heron" is a resource that needs no AutoCAD

**Decided:** 2026-11-15, from Heron AI for Revit's `heron_diagnose`. **Status:** in force.
The question after an update is "why does it not work", and the answer is in files: the plug-in
bundle, the address file the Heron button writes, the padlock file, and the server's own code
against what is on disk. So `autocad://diagnose` reads only those, never COM and never a drawing,
and answers with AutoCAD closed. It is a resource, not a tool, because every tool goes through the
gate, which refuses when AutoCAD is not reachable: the one moment a diagnosis is needed most. It
never prints the session token. `autocad_status` carries the server and plug-in versions and says
when the chat still runs code older than its files.

## D-47 - A raw command or AutoLISP may not save, plot or export

**Decided:** 2026-11-15, from Heron AI for Revit's run guard. **Status:** in force.
Saving over a shared drawing is the one change Ctrl+Z cannot take back, and the tools that save or
export need Publish. Admin alone let `autocad_send_command` and `autocad_run_lisp` type QSAVE or
-PLOT. Two layers now: the server refuses a command string or LISP that names one of these commands
(or calls `vla-save`, `vla-saveas`, `vla-plottofile`...) and points at the typed tool; the plug-in
vetoes the same commands (`PublishGuard`) through `DocumentLockModeChanged` while a Change or Admin
job runs and for 3 s after it, when Publish is off. Read, View and Publish jobs are not watched: a
preview plots to a PNG through COM inside a Read job. The modeller's own Ctrl+S outside a job is
never touched. Known gap: an office LISP that saves through ActiveX inside a routine the server
cannot read is not caught by either layer.

## D-46 - A texture's real size is written as the map transform's diagonal

**Decided:** 2026-11-08, after the bedroom + bathroom model: 11 library textures all rendered as a
flat colour until each material's diffuse map matrix was rewritten by hand. **Status:** in force;
replaces D-42's "a texture's real-world size is not set".
AutoCAD keeps a map's size in its 4x4 map transform (the material's 16 DXF group-43 values). A map
made with the identity repeats the image every 1 drawing unit, 1 mm in a metric drawing, which
renders as a flat colour. Setting indices 0, 5 and 10 to 1/size and 15 to 1 was proven by hand that
day (walnut grain at 1000, marble at 2000), so `autocad_create_material(texture_size=...)` writes
exactly that through the .NET API: a new `Gi.Mapper` with AutoCAD's default projection, tiling and
auto-transform and only the transform changed (the API's `Transform` is read-only). The numbers
come from `TextureScale` in the Bridge, so they are tested offline. The bump map takes the same
size, as a photo and its bump image are the same tile. For a non-square image the width goes on X
(index 0) and the height on Y and Z (5 and 10), so on a wall the image's height runs up the wall;
which way a box mapping lays a face along X is **not proven**. Without a size the old behaviour
stays (identity) and the result warns. Plug-in **1.4.1**, as an older plug-in ignores the input;
the server warns when the plug-in's `set` does not list "texture size". Rejected: a default size
(a 600 tile and a 2 m slab need different numbers, and a wrong guess looks right in a preview),
and typing MATERIALMAP (sizes objects, not the material).

## D-45 - Every Heron window and the banner are drawn as Heron for Revit's

**Decided:** 2026-11-08, on Ajmal's word ("what you did for Heron AI in Revit, do the same here - no
difference: the icons, the settings window, the status bar, everything"). **Status:** in force.
`HeronWindowStyle.cs` is a port of Heron for Revit's: Surface card, top strip, Ink header with the
orange heron, ✕, Ink insets, Mist text at 92 / 72 / 55 per cent, flat brand button templates.
Bridge Status, Settings, the Keep question and `HeronSwitchWindow` (the question a padlock asks,
in place of a Windows message box, which stays only as the fallback when the window cannot open) are
built on it with Revit's layouts. The activity banner is Revit's status bar from the designer's
"Heron status bar" design, ported onto AutoCAD's own banner thread and `BannerJobs`. "Free this
AutoCAD" matches Revit's "Free this model" (`HeronHold.Free`, refused while an operation of the
holder runs). Not copied, because AutoCAD has no counterpart: the Companion button and page, and the
Keep question as a Revit TaskDialog (AutoCAD's is a Heron window). The banner stays 110 px below
AutoCAD's top edge so it clears the ribbon.

## D-44 - The padlocks live in a Settings window; the ribbon icons are Heron's brand set

**Decided:** 2026-11-08, on Ajmal's word (in Revit the icons changed and the on/off switches moved
into a window; do the same here). **Status:** in force; follows Heron AI's D-150.
The Heron tab has two buttons: **Heron** (connect, Bridge Status under the arrow) and **Settings**.
The four switches - Changes, Admin, Publish, Ask to Keep, in Revit's order - left the ribbon for
`HeronSettingsWindow`: per switch its padlock picture, its name, one line and the state as an
ON / OFF button. Pressing it runs the same `HeronActions.TogglePadlock` as the old ribbon button, so
the question on the way to the risky side and the settings file are unchanged, and the
`HERONCHANGES`-style commands stay. The cost, accepted as in Revit: the ribbon no longer shows at a
glance whether Changes is on; the banner and Bridge Status still do. The ribbon pictures are copied
from Heron for Revit's `Resources` (brand set of 2026-11-07, plus `Settings.png`); the banner's
on/off stays in the settings file, as no Revit switch matches it.

## D-43 - Heron's windows wear the Heron brand; the release has its own Remove button

**Decided:** 2026-11-08, in the tidy-and-release round Ajmal asked for after the same round on Heron AI.
**Status:** in force.
The status window, the keep question and the activity banner now take every colour from the Heron
palette (Heron AI `docs/brand/README.md`): Mist windows, Ink text, Accent for the focused choice and
the CHANGING chip, Success and Error for DONE and STOPPED, Ink glass at 92 % for the banner as in
Revit. Shades are those colours at an opacity, never new ones; `HeronBrand` in `HeronUi.cs` holds
them and `tests/test_brand_and_installer.py` fails on any other value. Manrope is first in the font
list, with Segoe UI behind it until Manrope ships. A padlock that lets Heron change the drawing
shows ON in Error (the brand's "state to notice"), not green; Ask to Keep, whose ON is the safe side,
shows ON in Success. The release zip gains `Uninstall.bat`, which lists what it removes and asks
before removing anything; refusals say what to do in plain words, and a `claude` error line no
longer stops a first install on Windows PowerShell 5.1.

## D-42 - Lights and materials are made by the plug-in; a 3D view is saved by typing -VIEW

**Decided:** 2026-11-05, for Ajmal's villa model: materials that look like the renders, and real
lights inside light blocks for a night render. **Status:** in force; extends D-40.
`autocad_add_light` and `autocad_create_material` are two more plug-in operations (`add_light`,
`create_material`, at **Changes**; plug-in **1.4.0**). Three routes were weighed. **COM** has no
light object at all, and its material object has only a name and a description: no colour, maps,
gloss or glow. **AutoLISP** could `entmake` a LIGHT, but its group codes are thinly documented and
a material's colour and maps live in nested dictionaries with no LISP call to set them; typing the
LIGHT or MATERIALS commands means answering prompts that change between releases. The **.NET API**
has `Light` and `Material` classes with every setting typed and the same in all three reference
packages (24.0, 25.0, 26.0, checked member by member), so that is the route: one object, every
setting, one transaction, as D-40 does. Lights are made in model space; `autocad_make_block`
copies them into a block like any object (COM `CopyObjects` deep-clones whatever it is given), so
a light block lights every insert. Light names are unique in model space, as AutoCAD's LIGHT
keeps them. A coloured light is a 6500 K lamp behind a filter colour. A material glows in its own
colour (the API has no separate glow colour), so `glow_kelvin` sets the colour to that white.
Only the settings asked for are written, and only their channels switched on, so a replace never
turns on, say, an empty transparency. A texture's mapping is left to inherit (AutoCAD's default,
adjusted with MATERIALMAP): its real-world size is not set, because how the API's mapper
transform reads is not proven. The tool reads LIGHTINGUNITS and warns when it is not 2; it does
not change it. `autocad_save_view(from_screen=true)` types `-VIEW _Save` over COM, as
`autocad_set_3d_view` types VSCURRENT (D-35): COM's `Views.Add` needs the direction, target and
twist written by hand, and a 3D view's numbers are not proven. Rejected: a general "set any
property" request (D-40's reason), and changing LIGHTINGUNITS or DEFAULTLIGHTING behind the
modeller's back.

## D-41 - What was taken from Autodesk's ADN-DevTech samples, and how

**Decided:** 2026-11-04, on Ajmal's "take everything useful from these repositories into Heron".
**Status:** in force. Six ADN-DevTech repositories were read in full; the AutoCAD ones gave five
things, each written fresh (two of the repositories carry no licence, so no code was copied):
`autocad_xref_tree` and `autocad_drawing_report` (reads over COM), `autocad_publish_pdf` (a
plug-in operation, `publish_pdf`, at **Publish**), the command name in "AutoCAD did not get to the
request" (the add-in follows command and LISP events), and `tools/memory_check.py`. The multi-sheet
PDF goes through AutoCAD's publisher, outside a transaction and a document lock (the publisher opens
the sheets itself), and is made from the drawing **as last saved**: a drawing with unsaved changes
is refused rather than published out of date. It never renames or moves the modeller's files, which
the sample does. Rejected: replacing `autocad_export`'s PDF route with the plot engine (the current
route works on 2027 and is pinned by tests; the publisher covers the multi-sheet case), APS Design
Automation (cloud credentials, and not the modeller's own AutoCAD) and an outside COM event
service (needs `regasm` as administrator and works round the padlocks). Detail:
[11](11-adn-repos-study.md).

## D-40 - The plug-in does what COM has no call for, one listed operation at a time

**Decided:** 2026-10-29, on Ajmal's "start the super hatch and 3D tools in the plug-in".
**Status:** in force; extends D-14. Loft, filleting, chamfering, shelling and press-pulling solid
faces and edges, thickening a surface, and Express Tools' SUPERHATCH have no ActiveX call, so the
plug-in does them through AutoCAD's .NET API. The server asks with a new bridge request, `run`,
naming one operation from a fixed list in `Heron.AutoCAD.Bridge/PluginOperations.cs`; anything
else is refused before AutoCAD is touched. `run` is allowed only inside this chat's running job,
on the drawing that job began on, and only when the job's level covers the operation (a Read job
may list a solid's faces, never fillet them): the padlock was already checked at `begin`. The
operation runs on AutoCAD's main thread (through `IdleQueue`) under a document lock in **one
transaction**: it all lands or none of it does, so every refusal can say "Nothing was changed."
No answer in time is "Outcome unknown", never "nothing was sent", because the work may still
have run. Edges and faces are picked by a word that goes by the solid's box ('top', 'vertical',
'front' as in AutoCAD's Front view), never by a face normal, or by the numbers
`autocad_list_solid_faces_and_edges` gives. The super hatch is one block of tiles inserted once and
clipped the way XCLIP clips (a spatial filter), so it moves, erases and undoes as one object.
Everything else stays on COM: a tool moves into the plug-in only when COM cannot do it. Rejected:
typing LOFT / FILLETEDGE / SUPERHATCH as commands (each waits for picks on screen, which typed
input cannot give reliably, and SUPERHATCH is an Express Tools LISP routine that may not be
installed), and a general "run this .NET code" request (it would put the whole API behind the
Changes padlock with nothing to check what it does).

## D-39 - Pattern and linetype files go in Heron's support folder, which goes on the support path

**Decided:** 2026-10-28, with `autocad_create_hatch_pattern` and `autocad_create_linetype`.
**Status:** in force. AutoCAD finds a custom hatch pattern only as its own NAME.pat on the support
search path; Automation has no "hatch from this file". So the files are written to
`%LOCALAPPDATA%\Heron\autocad\support` (or a folder the modeller names), and that folder is added
to `Preferences.Files.SupportPath` once - a change to the AutoCAD profile that stays, reported in
`support_path_added`, and refused with `add_to_support_path=false`. A linetype needs no path: it is
loaded straight from its file with `Linetypes.Load`. Both tools write files, so they sit at
**Publish**, like save and export. Rejected: writing into AutoCAD's own Support folder (Program Files
needs administrator rights and is replaced by an update) and appending to acad.pat / acadiso.lin
(an update overwrites them, and a mistake there breaks every standard pattern).

## D-38 - A wipeout is typed, because Automation cannot make one

**Decided:** 2026-10-28, with `autocad_add_wipeout`. **Status:** in force. There is no AddWipeout:
a wipeout is not among the objects ActiveX can create. So the tool types `_.WIPEOUT` with each
corner as `_non *x,y` - `*` takes the point in world coordinates whatever the UCS or dynamic input
says, `_non` keeps a running snap off it - and a blank line to close. It then checks that the newest
object in the current space is an AcDbWipeout, and if AutoCAD is still asking two seconds later it
cancels with Esc and refuses, so nothing is left half made. It goes over COM `SendCommand`, not the
plug-in's quiet input, because that one is asynchronous and the new object has to be read straight
after. Rejected: entmake from LISP (a wipeout needs its image definition and clip boundary built by
hand, unproven here) and WIPEOUT's Polyline option (it wants the polyline picked at its prompt;
corners typed as points need no pick, so a closed polyline is read for its corners instead).

## D-37 - Ordinates are refused when the datum is not the UCS origin

**Decided:** 2026-10-28, checking the code for faults like the five that failed live. **Status:** in
force. `AddDimOrdinate` takes no origin: AutoCAD measures every ordinate from the current UCS origin,
along the UCS axes. `autocad_dimension_run` promised "the datum to measure from", so with the datum
anywhere else it drew dimensions that read the wrong values (its own measured-versus-expected
check then warned, after the fact). Now an ordinate run whose datum is not the UCS origin - or world
points on a turned UCS - is refused before anything is drawn, naming the
`autocad_set_ucs(mode='origin', origin=[...])` call that fixes it. Rejected: moving the UCS for the
modeller and putting it back, which leaves a named UCS behind and rests on UCS calls not yet proven
live (rows D4, D15); the refusal costs one extra call and cannot draw a wrong number.

## D-36 - A typed scale that is a bare number above 1 is refused, not guessed

**Decided:** 2026-10-28, after `autocad_drawing_setup(scale=10)` in AutoCAD 2027. **Status:** in
force. A bare number has always been a ratio (0.02 = 1:50), so `10` read as **10:1** and set
DIMSCALE 0.1: every dimension ten times too small, with no error. A modeller who types 10 means 1:10
nearly every time, but a detail at 2:1 is real, so the server cannot know. Now every tool that takes
a scale the modeller typed (`autocad_drawing_setup`, `autocad_add_viewport`, `autocad_page_setup`,
`autocad_export`, the scale bar shape) goes through `sheets.parse_typed_scale`, which refuses a bare
number above 1 and asks for '1:10' or '10:1'. Nothing is written first. A bare ratio of 1 or less
(0.02, 1) and every written form ('1:10', '2:1') still read. Inside the server a 2:1 detail travels
as 2.0, so `parse_scale` itself is unchanged. Rejected: reading a bare 10 as 1:10 (a guess that is
wrong for every enlargement, and silent).

## D-35 - The visual style is set with the VSCURRENT command

**Decided:** 2026-10-28, after `autocad_set_3d_view(visual_style="realistic")` came back
`not_set: visual_style (Error setting system variable)` in AutoCAD 2027. **Status:** in force; it
corrects the "written with SetVariable (VSCURRENT)" in D-31, whose level (View) still stands.
VSCURRENT is a **command**, not a system variable: Autodesk documents no VSCURRENT variable, and COM
has no visual style on a model-space viewport. So the tool types `_.VSCURRENT _Realistic` (and so on)
with COM `SendCommand`, from a fixed table of ten answers, and still cannot be talked into anything
else. (Not the plug-in's quiet input: that is taken only inside a Change job, and this is View.) If
AutoCAD is still asking a second later (CMDACTIVE), the option was not taken: the tool cancels with
Esc so the next tool does not find AutoCAD waiting, and says so in `not_set`. The style cannot be read back, so the result no longer carries
`current_visual_style`; `autocad_preview` is the proof. The answers for 'shaded with edges' and
'shades of gray' (`_E`, `_G`) come from the prompt's capital letters, not from a run (row E34).

## D-34 - A read leaves no undo step: the plug-in pauses undo recording

**Decided:** 2026-10-27, after live check A30. **Status:** in force. A U typed after Claude ran
`autocad_list_entities`, `autocad_get_variable` and `autocad_preview` removed nothing; a U straight
after `autocad_batch_labels` removed the batch. Cause, in the source: reads call no command and put
no UNDO mark down, but some write through COM to look. `autocad_preview` adds a page-setup snapshot,
changes about eight layout settings, copies the snapshot back and deletes it; the first list in a
drawing adds the scratch selection set. Each COM write outside an undo group is an undo step of its
own. Now: when a **Read** job begins, the plug-in calls `Database.DisableUndoRecording(true)` on the
active drawing (only if recording was on) and turns it back on at that job's end, before replying,
so the next job never starts unrecorded. Safety nets: the next job's begin, Disconnect, the
modeller starting any command (except PLOT, which a preview may run itself), the drawing closing,
and a 2-minute deadline. The rules are in `Bridge/UndoPause.cs` (tested offline), the switching in
`Addin/UndoSwitch.cs`. **View** jobs (zoom, regen) keep their undo step, as AutoCAD's own ZOOM does.
Rejected: `UNDO _Mark` then `UNDO _Back` around each read (if the mark is missed, Back undoes the
whole session) and `UNDO _Control _None` (wipes the history). Live row A31.

## D-33 - What 3D can and cannot be automated, said out loud

**Decided:** 2026-10-26, on Ajmal's instruction to cover "all kind of 3-D modelling inside
AutoCAD... including material that for rendering". **Status:** in force, except rendering:
`autocad_render` is superseded by [D-87](#d-87---lights-are-listed-and-switched-by-the-plug-in-the-sun-default-lighting-and-exposure-are-variables) (removed 2026-11-21, #158).

Researched before building, because guessing a COM signature wrong can destroy a model. What
was confirmed and built: `AddEllipticalCone`, `AddEllipticalCylinder`,
`AddExtrudedSolidAlongPath` (SWEEP), `SliceSolid`, `CheckInterference`, `Rotate3D`, `Mirror3D`,
and the entity `Material` property.

Three things are **not** built, and that is the decision:

**`SectionSolid` is not built.** AutoCAD's own conceptual docs name it, but no parameter list for
it could be found in any reference. A wrong signature here would mangle a solid, so
`autocad_slice_solid` covers sectioning instead - cut it and look at the face.

**Materials cannot be created.** Every entity has a string `Material` property and setting it
works, but there is no automation route into Autodesk's material library. So `autocad_apply_material`
applies what is already in the drawing and, when a name is not there, **lists what is** and says
the Materials Browser is the way in. It does not pretend to create one.

**A material carries no density**, so it cannot give anything a weight. MASSPROP and
`autocad_solid_properties` both behave as if density were 1. The `model_part` prompt already
multiplies volume by a density the AI must state out loud; assigning "Steel" changes how a solid
looks and nothing else. Both tools say so, because the opposite assumption would put a wrong
weight on a drawing.

**Rendering has no automation call at all.** The only route is the `-render` command, so
`autocad_render` drives that - which is why it is **ADMIN**, the only new tool that is. Its
docstring carries the two real risks: the prompt wording differs between releases so the command
can stall, and script rendering has been reported to drop objects that render correctly by hand.
For a picture to look at, `autocad_preview` is instant and needs no padlock.

**`autocad_check_interference` is CHANGE, not READ**, although it only reports. AutoCAD builds the
overlap as a real solid in order to measure it. With `create_solids` off each one is removed again,
but the drawing was written to, and by D-31 the level belongs to the tool rather than to the call
it happens to make. Row F11 exists to prove the clean-up works.

## D-32 - A tool is not a fragment, but it carries the same five padlocks

**Decided:** 2026-10-26, on Ajmal's question: "these tools, it is same like
fragments in Heron AI - am I right?". **Status:** in force.

Checked, not assumed. `archive/revit_encl/heron_send.py` sends Heron AI's
fragments as five operations - `run_fragment_read`, `run_fragment_show`,
`run_fragment_write`, `run_fragment_publish`, `run_fragment_admin`. This
server's `core/risk.py` carries exactly those five: **READ / VIEW / CHANGE /
PUBLISH / ADMIN**, where VIEW is Heron's `show`. Same five, same order, same
meaning. So the padlock idea is shared, and it should stay shared: if Heron
adds a level, this repo follows.

**The unit of work is not the same.** A Heron fragment is C# **source sent in
at run time**: `heron_send.py` reads a `.cs` file and passes `source`, `needs`,
`values` and `apply`, and Revit compiles and runs it. A tool here is a fixed
function already compiled into the server, with a Pydantic schema, a level and
tests. Nothing new can be sent in - except `autocad_run_lisp`, which is
precisely why that one is ADMIN.

**Which is why findability is the work, not more tools.** A fragment is written
for the job, so it is always exactly right and never has to be found. A fixed
set of 101 has the opposite problem: the right tool exists and nobody can see
it. So every tool carries `Use when:` bullets in a draftsman's own words, with
`Don't use when:` naming the better tool, and `autocad://tools` lists the lot
grouped by padlock, built from the live registry so it cannot go stale.
`tests/test_tool_index.py` makes it a rule rather than a habit.

## D-31 - Looking at a model in 3D is a View tool

**Decided:** 2026-10-26. **Status:** in force.
`autocad_set_3d_view` sets the view direction and the visual style. Nothing in
the drawing moves, nothing is created, nothing is deleted - it changes what is on
screen, which is exactly what the **View** level is for, and the level
`autocad_zoom` and `autocad_regen` already sit at.

The argument against was that the visual style is written with `SetVariable`
(VSCURRENT), and `autocad_set_variable` is ADMIN. But the level is a property of
the *tool*, not of the call it happens to make inside: this tool writes one
named variable from a fixed list of ten style names, and it cannot be talked
into writing anything else. Putting it behind Admin would mean a modeller had to
turn on the most dangerous padlock in the product to look at their own model from
the front, which is backwards.

The viewport's own quirk is handled rather than worked around: a viewport's
changes only take effect once it is made active again, so the tool reassigns
`doc.ActiveViewport` after setting the direction, and says in `not_set` when
that is refused.

## D-30 - A shape is a pure generator, drawn through the batch engine

**Decided:** 2026-10-26. **Status:** in force.
`autocad_make_shape` draws 24 named shapes. Each one could have been a COM
routine of its own. Instead each is a **pure function** in `acad/shapes.py` that
returns a list of operations in exactly the shape `autocad_batch_draw` takes,
and the tool hands that list to the one shared engine (`draw_operations`).

Three things follow, and they are the reason:

* **The geometry is tested without AutoCAD.** A flat pattern is checked by
  measuring whether its arcs are as long as the girths they must roll onto -
  real arithmetic against a real requirement, on a Linux CI runner.
* **It is fast and atomic for free.** One round trip, one undo step, and
  `coords='ucs'` already works, because all of that lives in the engine.
* **Nothing is duplicated.** `autocad_make_shape`, `autocad_add_centre_marks`
  and `autocad_add_revision_cloud` all generate operations and all go through
  the same validation and the same sender.

Two things had to be added to the batch to make it possible, and both are
improvements in their own right: **bulges** on a polyline (DXF group 42), so a
slot, a rounded corner, an elbow and a flat pattern stay *one object* instead of
a pile of loose arcs; and **justification** on text (groups 72, 73 and 11), so a
bubble's number sits on its point.

What the shape library is **not**: an office block library. A block carries the
office's own line weights and its attributes, and is better. The furniture
shapes (bubbles, section marks, north points, scale bars) exist for the drawing
that has no block library to hand, and the tool says so.

The gear says plainly in its own docstring that `show_teeth` draws a
straight-flank representation at the pressure angle and **not** a generated
involute, so nobody cuts a gear from it.

## D-29 - A sequence spends the Changes padlock and nothing more

**Decided:** 2026-10-26. **Status:** in force.
`autocad_sequence` runs several tools in one call. It cannot go back through the gate to do it: the
gate holds an `asyncio` lock for the whole call, so a nested `guarded()` would wait on a lock the
sequence itself is holding. So each step's **undecorated body** is called directly
(`tool.fn.__wrapped__`), which means the sequence, not the gate, is what stands between a step and
the drawing.

Therefore the ceiling is in code and is tested: a sequence refuses any step at the **Publish** or
**Admin** level, and refuses a sequence inside a sequence. It is itself a Change tool, so it can do
exactly what the Changes padlock already allows and can never save, plot, run a command or evaluate
AutoLISP on the way. `tests/test_sequence.py` asserts this against every registered Publish and
Admin tool by name, so a new one is covered the day it is added.

Every step's arguments are validated against that tool's own schema before the first step runs
(the rule `autocad_batch_draw` already follows: a call that cannot be completed changes nothing).
Undo: each step keeps its own undo step, and any group a step leaves open is closed at the end —
the same hazard `autocad_batch_draw` handles in AutoLISP. Whole-call atomicity is the **Ask to
Keep** padlock's job, not this tool's.

## D-28 - Drafting settings are a Change tool, written from a fixed list

**Decided:** 2026-10-26. **Status:** in force.
`autocad_set_variable` is **Admin** because it will set any system variable: an escape hatch, and
rightly gated. But a modeller cannot be asked to turn on the Admin padlock to set the drawing's
units, and setting units is not an escape hatch.

So `autocad_drawing_setup` and `autocad_create_styles` are **Change** tools that write only from a
list kept in `tools/settings.py`: `DRAWING_VARIABLES` for the drawing, and names beginning `DIM`
for a dimension style. The list is in code, not in the request, so nothing a caller writes can widen
it — the same principle as `core/risk.py` itself. A test asserts that everything
`plan_settings` can produce is on the list, and that `plan_dim_style` refuses a name outside the DIM
family.

Both report the old value beside the new one, and `dry_run` shows the whole plan without writing.
`autocad_set_variable` stays Admin for everything else.

## D-27 - Coordinates are world coordinates, and Heron says so

**Decided:** 2026-10-26. **Status:** in force.
Every coordinate AutoCAD's Automation API takes or returns is a **World** coordinate, and `entmake`
writes world coordinates straight into the database. The modeller works in the UCS they set. Two
honest options: convert silently everywhere, or say so and offer the conversion.

Converting silently was rejected: it would have to guess on a tilted UCS, and it would change what
every existing tool means. So:

* world stays the contract for every tool;
* `autocad_status` reports the drawing's UCS and adds a plain `ucs_advice` sentence when it is not
  the world one — and the gate already forces `autocad_status` before any change (D-19), so the warning always
  arrives first;
* `autocad_get_ucs`, `autocad_set_ucs` and `autocad_convert_points` (AutoLISP's `trans`) make it
  workable;
* `autocad_batch_draw` takes `coords="ucs"` and converts every point and angle in Python before a
  single expression is sent, so the conversion is tested without AutoCAD;
* a tilted UCS is **refused** for a flat 2D request rather than guessed, and says to convert the
  points instead.

The transform is built from `UCSORG`, `UCSXDIR` and `UCSYDIR` rather than
`Utility.TranslateCoordinates`: those three are documented, read-only, saved with the drawing, and
the arithmetic from them is pure Python that `tests/test_coords.py` checks without AutoCAD.

The single-entity `autocad_draw_*` tools do not take `coords` yet; adding it means converting each
tool's rotation and its planar vertex lists as well, which has no live check behind it today
([ROADMAP](ROADMAP.md)).

## D-26 - Lee Mac's ideas are rebuilt as Heron tools; his code never enters the repository

**Decided:** 2026-10-26, Ajmal: *"study lee-mac.com word by word ... make it part of this mcp"*.
**Status:** in force.
His terms need written consent to redistribute and forbid commercial use, which this public MIT
repository cannot promise, so no Lee Mac code is copied, translated or bundled. Each idea is written
fresh from the AutoCAD ActiveX reference, tested without AutoCAD, and credited in
[08](08-lee-mac-study.md). First four: count blocks, total length, dynamic block get and set; the rest followed the same
day (every idea on the list, plus add-ons), with the shared geometry in `acad/geometry.py`.

## D-25 - The drafting rules ship inside Heron

**Decided:** 2026-10-26, Ajmal: *"bring that drafting rules also"*, after asking whether anyone who
downloads Heron gets the same neat drawings. **Status:** in force.
The rules lived only in one chat. They are now in the server's instructions (sent to every AI on
connect) and the `draw_detail` prompt, with [07](07-drafting-rules.md) as the readable copy. Lee Mac's
programs are studied for ideas only: his licence allows private/organisation use and forbids
redistribution, and this repository is public, so his code is never copied in; ideas are
re-implemented and credited.

## D-24 - Labels are leaders in Ajmal's TLD style, or multileaders; parts are blocks

**Decided:** 2026-10-26, on Ajmal's instructions after the roof pipe-support detail: labels must be
real leaders ("L shaped, and angled if needed ... multileader also, both options"), following his
`TextLeader_V4.lsp`; and *"elbows and everything should be blocks ... otherwise the manual drawing
person cannot do anything"*. **Status:** in force.
`autocad_add_label` makes MTEXT + LEADER (TLD geometry, `shape` L or angled) or one MLEADER. Leaders and
dimensions made over COM get the drawing's DIMSCALE, which COM does not apply. A "make block from
objects" tool comes next, so details are built from named blocks instead of loose lines.

## D-23 - The generator scripts are removed

**Decided:** 2026-10-26, on Ajmal's instruction: *"Remove all generators, including the folder."*
**Status:** in force. Supersedes D-07 (generator paths) and the generator half of D-06.
The `generators/` folder (AHU, CCTV and pole-enclosure scripts) was project work, not part of Heron,
and normal use never makes such scripts: Heron draws straight into AutoCAD. The drawings they made
stay on Ajmal's PC. The scripts are recoverable from git history, commit `a443df4` (main before removal).

## D-22 - Batch input goes through the plug-in with echo off

**Decided:** 2026-10-26, from the live F2 check. **Status:** in force.
Sent over COM, every batch piece was echoed into the command history. The plug-in now takes the
pieces (`send_quiet`) and types them with `SendStringToExecute(..., echoCommand: false)`. It accepts
them only inside this chat's running CHANGE / PUBLISH / ADMIN job, so it adds no new way in: the
padlock check at `begin` already covered the job. Without the plug-in (or an older one) the server
falls back to COM SendCommand. Each piece also returns nothing printable (`(princ)`). Side effect:
batches run inside AutoCAD and are about 8x faster (0.17 s against 1.4 s for 41 objects).

## D-21 - Batch drawing sends expressions; it never loads a file

**Decided:** 2026-10-26, from live check A21. **Status:** in force.
Loading the batch `.lsp` from `%TEMP%` made AutoCAD's SECURELOAD ask "Unsigned Executable File" on
every batch. The batch is now sent as short expressions (under 600 characters each, `build_chunks`),
like typed input, so no file is loaded. Rejected: adding `%TEMP%` to TRUSTEDPATHS or setting SECURELOAD
to 0 (weakens the modeller's security), writing the file into the trusted plug-in folder (generated
code in a trusted place), and reading the file back with `eval` (sidesteps the security check rather
than respecting it). The old error text that advised setting SECURELOAD to 0 is gone.

## D-20 - A double-click on a ribbon switch counts once

**Decided:** 2026-10-26, from the first live checks. **Status:** in force (built; live row A20 NOT RUN).
The live log showed padlocks flipping on and straight back off within 0.4 s: modellers double-click.
A second click on the same switch within 0.7 s is ignored (`RepeatClickFilter`).

## D-19 - Units are checked before anything is changed in a drawing

**Decided:** 2026-10-26, on Ajmal's instruction during the live checks: *"Whenever you are in one
drawing for the first time, at that time you have to understand the unit."* **Status:** in force.
A CHANGE, PUBLISH or ADMIN call is refused until `autocad_status` (or `autocad_create_drawing`) has run
on that very drawing in this server; switching or opening a drawing does not count, and reading does
not count. The live check showed why: Drawing1 was in inches, Drawing2 in millimetres.
Replaces the looser D-17 re-arming rule.

## D-18 - Discard goes back to an UNDO mark, and only on a clear answer

**Decided:** 2026-10-26, after the final review. **Status:** in force. Supersedes the "UNDO 1" design.
`UNDO 1` undid the plug-in's own zoom, missed layers a batch made, fired on delete previews that wrote
nothing, and fired when the pipe broke. Now: the plug-in says at `begin` whether it will ask; only then
the server puts `UNDO _Mark` down before the work; it asks only when the call really wrote (a write
counter in `core/connection.py`); Discard is `UNDO _Back`, then the created handles must be gone; a
failed question keeps the change and says so; UNDO off (UNDOCTL) means "cannot discard", said plainly.
The Keep box closes itself as Discard after 9 minutes, before the server's 10, and a question the
plug-in gave up on can never pop up later (`OneShotWork`).

## D-17 - Status always answers; resources go through the gate

**Decided:** 2026-10-26. **Status:** in force.
`autocad_status` always answers with `"heron": {connected, message}`, so a chat can always tell the
modeller how to connect. While AutoCAD is not connected it returns only that block, never the
drawing's name, path or contents (changed after the final review); under `--no-bridge` it says
Heron is off. MCP resources call the matching gated tools,
so a resource read is refused and audited exactly like a tool call.
