# Changelog

Newest first. Dates are when the change was made.

## Unreleased

- **Fixes from the Luxury Suite 2 interior set (2026-11-09, AutoCAD 2027).** `autocad_run_lisp`
  refuses expressions over 2,000 characters (a ~3,000-character one arrived as nothing) and its
  timeout note says the expression may still have run, so count before re-sending.
  `autocad_status` no longer fails whole when `doc.PaperSpace` throws: the count comes from the
  layout's block. `autocad_add_viewport` falls back to MVIEW typed with two corners when
  AddPViewport is refused. Plug-in **1.4.2**: `autocad_create_material(replace=true)` with a colour
  and no texture clears the old image. Known limit 23; live rows K16, S8-S10 NOT RUN.
- **Fix: the heron stays on top after Free this AutoCAD or Bridge Status.** AutoCAD makes a pick
  from the Heron menu the button's current item only after the pick has run, so the heron put back
  inside the pick was overwritten and "Free this AutoCAD" stayed on top; picking Heron to get it
  back disconnected (live, 2026-11-08). The ribbon now watches the button and puts the heron back
  once AutoCAD has finished with the click. Live row L12.
- **Fix: the Heron button connects again.** #21 set the Heron split button to
  `IsSynchronizedWithCurrentItem = false` to copy Revit; AutoCAD then runs the button's own (empty)
  action, so pressing Heron did nothing and only Bridge Status -> Connect worked. Back to `true`;
  Bridge Status and Free this AutoCAD put the heron back on top afterwards. Live row L11.
- **A material's texture gets its real size** ([D-46](docs/DECISIONS.md)); plug-in **1.4.1**.
  `autocad_create_material` takes `texture_size` (the real width of one image tile, in drawing
  units) and `texture_height` for a non-square image. The plug-in writes the texture's and the bump's
  map transform with 1/size on the diagonal, the fix done by hand with entmod on 2026-11-08 (walnut
  at 1000 mm, marble at 2000 mm). Without a size nothing changes, but the result now warns that the
  image repeats every 1 unit; with a size, an older plug-in that ignores it is warned about too.
  Matrix tested offline (`TextureScaleTests.cs`); live row K15 NOT RUN.
- **Every Heron window and the banner as in Heron for Revit** ([D-45](docs/DECISIONS.md)): the
  activity banner is Revit's status bar (glass card, sheen, turning aura, glow, slide in and out;
  "Heron AI · Changing" with the drawing, the job and the time; Done in green, Needs attention in
  red). Bridge Status, Settings, the Keep question and a new switch question ("Turn Changes on?",
  replacing the plain Windows box) share Revit's dark window style. The Heron menu gains **Free this
  AutoCAD** (`HERONFREE`), and the ribbon buttons have Revit's one-line hover texts. Live rows
  L7-L10, NOT RUN.
- **The ribbon and icons match Heron for Revit** ([D-44](docs/DECISIONS.md)): the Heron tab now has
  two buttons, **Heron** (Bridge Status under its arrow) and **Settings**. The Changes, Admin,
  Publish and Ask to Keep padlocks left the ribbon for the Settings window (`HERONSETTINGS`), each
  with its padlock picture and an ON / OFF button. The 10 ribbon icons and the new Settings icon are
  Heron for Revit's brand set of 2026-11-07. The refusals now say "press Settings on the Heron tab".
  Live rows group L, NOT RUN.
- **Installer Remove button and the Heron brand colours** ([D-43](docs/DECISIONS.md), #19):
  `Uninstall.bat` asks before removing anything; installer refusals in plain words; a first install
  no longer stops on Windows PowerShell 5.1 when `claude mcp remove` prints an error. The status
  window, the keep question and the banner use the Heron palette, Manrope first.

- **Lights, materials and a saved 3D view for a render** ([D-42](docs/DECISIONS.md)); plug-in
  **1.4.0**, two new tools, 128 in all (live rows group K, NOT RUN): `autocad_add_light` (a
  photometric point, spot, web or distant light: lumens or candela, Kelvin or a colour, a spot's
  cones, an IES file, on / off, shadows, name, layer; warns when LIGHTINGUNITS is not 2; done by the
  plug-in) and `autocad_create_material` (a named material from its colour, texture image,
  glossiness, reflectivity, transparency and refraction, glow in cd/m² and Kelvin, bump image,
  metal shading; done by the plug-in, and `autocad_apply_material` takes it straight away).
  `autocad_save_view(from_screen=true)` saves the view on screen, 3D angle included. Known limits
  [05 §22](docs/05-known-limits.md#22-lights-materials-and-the-saved-3d-view-have-their-own-limits).
- **The DONE card always closes.** The activity banner counted begins and ends, so one job whose
  end never came (AutoCAD left mid-command and the COM link dropped, 2026-11-05) kept every later
  "Heron AI has finished" card on screen. `BannerJobs` (Bridge, tested offline in
  `BannerJobsTests.cs`) now tracks jobs by name: an end sent twice changes nothing, the next job
  from the same chat clears a lost end, and a job older than 15 minutes no longer holds the card.
  Compiled for all three AutoCAD builds; live rows J1-J2 NOT RUN.
- **Fillet, chamfer, shell, press-pull and the face listing work again.** Every one failed on
  every solid: the Brep was built from the entity, which carries no subentity paths. It is now
  built from the solid's FullSubentityPath; the solid is read first and opened for write after.
  Live row J3 NOT RUN.
- **`autocad_run_lisp` can no longer leave AutoCAD stuck in a command.** A command the
  expression leaves at a prompt is cancelled before the result is written and named in
  `cancelled_command`; running object snaps are off for the call and put back through COM.
  Live row J4 NOT RUN.
- **`autocad_create_layout` never leaves a half-made sheet.** The plotter is retried on a
  freshly fetched layout, and a failed page setup deletes the new layout, so the call can be
  repeated. Live row J5 NOT RUN.
- **`autocad_preview` comes out upright** on a layout set to plot turned 90 degrees; the layout's
  own rotation is put back. Live row J6 NOT RUN.
- **From Autodesk's ADN-DevTech samples** ([D-41](docs/DECISIONS.md), [11](docs/11-adn-repos-study.md));
  plug-in **1.3.0**, three new tools, 126 in all (live rows group I, NOT RUN):
  `autocad_xref_tree` (every xref, nested ones under their parent, loaded / unloaded / not found,
  Read), `autocad_drawing_report` (units, layers off / frozen / locked, blocks, xrefs, styles,
  sheets and model-space counts of a received drawing, Read) and `autocad_publish_pdf` (the
  drawing's sheets in one multi-page PDF through AutoCAD's publisher, done by the plug-in, Publish).
  "AutoCAD did not get to the request" now names the command AutoCAD is in, from its command and
  LISP events. `tools/memory_check.py` measures acad.exe's Private Bytes over 100 rounds of reads.
  Known limits [05 §20](docs/05-known-limits.md#20-the-tools-from-the-adn-devtech-study-have-their-own-limits),
  including Plant 3D objects.
- **Plug-in 1.2.0: the plug-in does what COM has no call for** ([D-40](docs/DECISIONS.md)). A new
  bridge request, `run`, asks it for one operation from a fixed list, only inside this chat's
  running job, on the drawing that job began on, at a level that covers it. Each runs under a
  document lock in one transaction, so a refusal changes nothing. Eight new tools, 123 in all (live
  rows group H, NOT RUN):
  `autocad_list_solid_faces_and_edges` (numbered faces and edges, Read),
  `autocad_loft` (closed outlines in order, guides or a path, ruled, closed),
  `autocad_fillet_solid_edges` and `autocad_chamfer_solid_edges`,
  `autocad_shell_solid` (wall thickness, faces left open),
  `autocad_press_pull_faces` (flat faces by a distance, optional taper),
  `autocad_thicken_surface`, and
  `autocad_super_hatch` (a block tiled in a grid inside a closed outline, clipped like XCLIP, as
  one object). Edges and faces are picked by a word that goes by the solid's box ('top',
  'vertical', 'front') or by number. An older plug-in is told to update; no answer in time is
  "Outcome unknown", never "nothing was sent". An operation checks the padlock again when it starts
  and keeps the one-chat hold while it runs; something made but not read back at once is reported
  as made (`verified: false`), never as an error to retry. The add-in compiles for AutoCAD
  2021-2024, 2025-2026 and 2027 with 0 warnings; none of it has run in AutoCAD yet.
- `autocad_export(area="layout")` wrote no PDF in AutoCAD 2027 (2026-10-28, live row D20): it set
  `CenterPlot`, which AutoCAD refuses on a layout plot, and choosing the DWG To PDF plotter dropped
  an A1 sheet to ANSI A. A layout plot is no longer centred, and with no `paper_size` the layout's
  own sheet is kept. Two tests that failed first. Live re-run NOT RUN.
- `docs/TROUBLESHOOTING.md` no longer says the batch loads a `.lsp` from %TEMP% or tells users to
  set SECURELOAD to 0 (stale since D-21); an "Unsigned Executable File" box never comes from Heron.
- Seven new tools, 115 in all, each with offline tests (live rows group G, NOT RUN):
  `autocad_draw_spline` (fit points, ends along the first and last segments, closed, UCS),
  `autocad_draw_multiline` (MLINE walls and double-line ducts: thickness, justification, style),
  `autocad_add_wipeout` (from corners or a closed polyline; typed, as Automation has none - D-38),
  `autocad_attach_xref` and `autocad_manage_xref` (reload, unload, detach, bind, insert),
  `autocad_create_hatch_pattern` and `autocad_create_linetype` (NAME.pat / NAME.lin written in
  Heron's support folder, including ---- CHWS ---- service lines; Publish level - D-39).
  `autocad_add_hatch` now also hatches with a custom pattern. Super hatch and the 3D commands with
  no Automation call (loft, fillet, shell, press-pull) are on the ROADMAP for the plug-in.
- Fixed five tools that failed live in AutoCAD 2027 on 2026-10-28, each with a test that failed
  first:
  - `autocad_drawing_setup(scale='1:10')` failed `could not convert string to float: ':'`, and a dim
    style with `"text_style"` in `autocad_create_styles` failed the same way on `'S'`. A text value
    read from the drawing (CANNOSCALE `1:10`, DIMTXSTY `Standard`) was split into letters and each
    turned into a number. Text now stays text.
  - `autocad_add_table` text height came back `not_set` and the text was tiny: a table has no
    `TitleTextHeight` properties. Now `SetTextHeight` on the title, header and data rows, and a new
    `text_style` option (`SetTextStyle`).
  - `autocad_solid_boolean` refused real solids (`AcDb3dSolid`). The type table had no entry for a
    3D solid; adding it also fixes `autocad_slice_solid`, `autocad_check_interference` and
    `autocad_apply_material(solids_only=true)`, which had the same fault.
  - `autocad_set_3d_view(visual_style=...)` was refused: VSCURRENT is a command, not a variable. It
    is now typed as the command ([D-35](docs/DECISIONS.md)).
- Found by checking for the same faults elsewhere:
  - `scale=10` read as 10:1 (DIMSCALE 0.1). A bare number above 1 is now refused with "write '1:10'
    or '10:1'" in drawing setup, viewports, page setup, PDF export and the scale bar
    ([D-36](docs/DECISIONS.md)).
  - A dim style's precision, unit format, zero suppression and colours were sent as decimals
    (`0.0`), which AutoCAD refuses for a whole-number variable. Now whole numbers.
  - After a dim style with an `arrow_block`, the drawing's default arrow is put back with `.`, the
    way AutoCAD sets it.
- A second check of the whole server, for the same kinds of fault, found and fixed:
  - `autocad_add_solid` oval shapes (`elliptical_cylinder`, `elliptical_cone`) had no AutoCAD
    call: they fell through to the torus and always failed. Now `AddEllipticalCylinder` /
    `AddEllipticalCone` with half the length and width, made the long way and turned when wider
    than long.
  - `autocad_add_hatch` sent pattern type 0 (user-defined), which AutoCAD refuses for a named
    pattern like ANSI31. Now 1, predefined.
  - `autocad_dimension_run` ordinates: AutoCAD measures from the UCS origin, so a datum elsewhere
    drew wrong values. Now refused before drawing, naming the `autocad_set_ucs` call
    ([D-37](docs/DECISIONS.md)).
  - On a turned UCS with `coords="ucs"`: `autocad_transform_3d` (move, rotate axis, mirror),
    `autocad_slice_solid` (cut direction and the vertical planes), the revolve axis in
    `autocad_extrude_profile`, the angle of `autocad_dimension_run`, and the box, wedge and oval of
    `autocad_add_solid` now follow the UCS; the points were turned, the directions were not.
  - Point variables (`LIMMIN`, `LIMMAX` in drawing setup, any point in `autocad_set_variable`) go
    as an array of doubles; `autocad_set_variable` takes "x,y".
  - `autocad_purge(target="text_styles")` answered `_STyles`, which is not an answer the prompt's
    "textSTyles" takes; now `_ST`.
  - The selection-mode codes for Previous and Last were swapped (not used yet).
  - Live rows E13, F1, S4-S7: NOT RUN.
- Tests: two geometry tests used a nested `pytest.approx`, which pytest 9 refuses, and CI turned
  red when it picked pytest 9 up. Same values and tolerance, compared as flat coordinate lists.
- Live rows D23, D32, E18, E28, E34: NOT RUN.
- New `autocad_batch_labels`: a whole column of TLD labels in one call and one undo step, checked
  before drawing, with `arrow_scale` per view and a `crossing` report. 108 tools. Live check A30.
- Plug-in: a read (list, variable, preview and every other Read tool) no longer leaves an undo step,
  so one Ctrl+Z after Claude looked at the drawing still undoes the last change. Found in live check
  A30; [D-34](docs/DECISIONS.md), live row A31 (NOT RUN).

## 1.6.0 - 2026-10-26 - The rest of 3D, and findability proved

Two things Ajmal asked for: finish the 3D side, and show that the tools can
actually be found fast. 6 new tools, 107 in all. Detail:
[docs/03](docs/03-tools-reference.md), [D-32 / D-33](docs/DECISIONS.md),
[NEEDS-CHECKING group F](docs/NEEDS-CHECKING.md).

### Findability: he was right to doubt it

The index shipped in 1.5.0, but nobody had measured whether it works. Measured
now, on 67 phrases a modeller would really say ("how many metres of DN50 pipe
on this layer", "does the ductwork clash with the steel"):

| | right tool first | in the top three |
|---|---|---|
| First attempt | 36 / 55 | 49 / 55 |
| Now, over 107 tools | **55 / 67** | **67 / 67** |

- **New resource `autocad://tools/find/{phrase}`.** Ask in plain words, get
  the tool, its padlock and why it matched. Needs no AutoCAD.
- **`acad/findtool.py`** scores on the tools' own words: a rare word (DIMSCALE,
  flange) beats a common one (layer, set); a `Don't use when` mention counts
  **against**; and a word we guessed from yours - a plural, a synonym - counts
  less than one you typed. Both weights were picked by sweeping them against
  the 67 phrases, not by taste, and the good region is wide rather than a
  knife edge.
- **It found real documentation gaps**, which is the point: `autocad_drawing_setup`
  never said "DIMSCALE" out loud, so "set DIMSCALE and LTSCALE for 1:50" landed
  on the Admin-level `autocad_set_variable` instead. Now fixed.
- `tests/test_find_tool.py` keeps the 67 phrases as a floor, so a rename or a
  reword that costs findability fails the build.

### The rest of 3D

- **Oval shapes.** `autocad_add_solid` gains `elliptical_cylinder` and
  `elliptical_cone` - an oval duct, a tapered oval stack. They take the
  **overall** sizes; the half-axis conversion is done here, because calling out
  a 400 x 200 duct and getting 800 x 400 is the obvious trap.
- **Sweep.** `autocad_extrude_profile` gains `path_handle`: run a section along
  a route, which is how a duct, a pipe, a cable tray or a handrail is really
  modelled.
- **`autocad_slice_solid`.** Cut a solid with a plane - a real section through a
  model. Given the way a drafter says it ("horizontally at 1500", "on the
  diagonal"), with the three points AutoCAD wants worked out in pure Python and
  tested without AutoCAD.
- **`autocad_check_interference` - clash detection.** Every solid in one set
  against every in another, with the overlap volume so the worst is dealt with
  first, and `create_solids` to draw them. It is **Changes, not Read**, because
  AutoCAD builds the overlap as a real solid to measure it; with the drawing off
  each one is removed again, and row F11 exists to prove that.
- **`autocad_transform_3d`.** Move with Z, rotate about any axis, mirror in a
  plane, array up in levels. The flat modify tools only ever did XY and Z-axis
  rotation.
- **Materials.** `autocad_list_materials` and `autocad_apply_material`.
- **`autocad_render`** drives `-render`, at Admin.

### What 3D cannot do, said out loud (D-33)

Researched before building, because a guessed COM signature can destroy a
model. Three honest limits now documented in the tools themselves:

- **`SectionSolid` is not built.** No parameter list for it exists in any
  reference we could find. `autocad_slice_solid` covers sectioning instead.
- **Materials cannot be created, and carry no density.** There is no automation
  route into Autodesk's library, so an unknown name is refused *with the list of
  what the drawing does have*. And a material is appearance only - MASSPROP
  assumes density 1, so a weight is volume times a density you state.
  Assigning "Steel" does not make anything weigh.
- **Rendering has no automation call.** `-render` is the only route; its prompts
  differ between releases, and script rendering has been reported to drop
  objects. `autocad_render` says both in its own docstring. For a picture to
  look at, `autocad_preview` is instant and needs no padlock.

### Checking

- **NEEDS-CHECKING group F**: 23 new rows, 90 live rows in all.
  `tools/live_check.py --group F` measures 19 of them, including the ones that
  would catch a real error: an oval duct measuring 400 x 200 and not 800 x 400;
  a slice whose two halves add up to the original; a clash check that leaves
  the entity count unchanged; a 1000 tall column that lies down to 100 when
  tipped 90 degrees about X.
- `tests/test_solids_3d.py`: the cutting-plane arithmetic for every named plane
  and seven arbitrary normals, including the vertical case where the helper axis
  has to dodge the normal. 38 tests.
- 1812 offline tests.

## 1.5.0 - 2026-10-26 - 101 tools you can actually find

No new tools. A toolbox nobody can search is worse than a small one, and 47
of the 101 did not say what they were for.

- **Every tool now says when to use it.** All 101 carry an `Examples:`
  section whose bullets are in the words a draftsman would use - *"how many
  metres of DN50 pipe on this layer"*, *"this detail came in at 1:10, make it
  full size"* - and a **`Don't use when:`** naming the better tool where there
  is one (`autocad_count_text` points at `autocad_count_blocks`;
  `autocad_set_variable` points at `autocad_drawing_setup`, which needs only
  the Changes padlock; `autocad_delete_layer` points at freezing instead).
  47 were written for this release; one that was prose became a bullet so the
  index can read it.
- **New resource `autocad://tools`.** The whole toolbox in one place, grouped
  by the padlock it needs, each with its summary and its `Use when` lines. It
  is built from the live registry, so it cannot drift from the code - a tool
  added, renamed or re-levelled appears with no second edit. It touches no
  drawing, so unlike the other four resources it is **not gated**: it answers
  before AutoCAD is open and before Heron is pressed.
- **The server tells connecting AIs to read it**, and to prefer the tool that
  does the whole job in one call - `autocad_batch_draw` over many single
  draws, `autocad_make_shape` over building a standard shape by hand,
  `autocad_dimension_run` over one dimension at a time, `autocad_sequence`
  for a settled list of steps. One call is one undo step for the user.
- **A rule, not a habit.** `tests/test_tool_index.py` fails if any tool lacks
  a `Use when` line, if the index cannot read it, if a wrapped bullet is cut
  off mid-sentence, or if a tool is filed under the wrong padlock. AGENTS.md
  carries it as a Never. 514 new tests; 1627 offline.

### Same five levels as Heron AI's fragments

Checked against `archive/revit_encl/heron_send.py`: Heron AI sends fragments
as `run_fragment_read` / `show` / `write` / `publish` / `admin`. This server's
`core/risk.py` carries exactly those five - READ / VIEW / CHANGE / PUBLISH /
ADMIN, with VIEW being Heron's `show`. The gate is the same idea.

What differs is the unit. A Heron fragment is C# **source sent in at run
time** and compiled by Revit. A tool here is a fixed function already in the
server, with a schema, a level and tests - nothing new can be sent in except
through `autocad_run_lisp`, which is why that one is Admin. So the padlocks
behave the same, and the index above is what makes the fixed set as easy to
reach for as writing a fragment.

## 1.4.0 - 2026-10-26 - The live checks run themselves, and four job prompts

No new tools; still 101. This is the step from "built" and "tested offline"
to **proved in AutoCAD**, plus four prompts that spend the tools in the right
order. Detail: [tools/README.md](tools/README.md),
[docs/03](docs/03-tools-reference.md).

- **`tools/live_check.py`.** One command measures 46 of the 67 live rows in
  [NEEDS-CHECKING](docs/NEEDS-CHECKING.md) and writes the results back with
  their evidence. It works in a scratch drawing it makes and closes itself, so
  the drawing you have open is never touched. `--list`, `--group D|E|all`,
  `--row E4`, `--write`.
- **It measures, it does not merely run.** A cone development's arcs against
  the girths they roll onto (pi x D); a slot's perimeter against 2L + pi x W,
  and that it is one polyline; a 1:100 viewport's `CustomScale` read back off
  the viewport; a solid's base against z=0; the volume a subtract removed
  against pi x r^2 x t; that a sequence with a bad step leaves the entity
  count unchanged; that a bulge becomes a 90-degree arc and centred text is
  centred.
- **The 21 rows it cannot measure say why.** A title block .dwg, the twist
  direction, "the sheet looks right", which sheet sizes a plotter offers,
  which variables a release makes read-only - each is written **NOT RUN** with
  the reason instead of left looking unexamined. A row the padlocks refuse is
  **NOT RUN** too, never PASS.
- **`tools/live_results.py`** replaces only the last cell of a row, keeping
  leading whitespace, the trailing newline and every other cell
  byte-identical, and strips `|` and newlines from the evidence so it cannot
  break the table. Its test runs it against the real register.
- **Four job prompts** in `tools/resources.py`: `make_sheet` (layout, page
  setup, title block, viewport at a scale, saved view), `import_to_shop_drawing`
  (the IFC flow, dry run first, dimensions checked against their geometry),
  `model_part` (profile, extrude or revolve, cut, weigh - and it will not guess
  a density), `shape_from_words` (catalogue, dry run, draw, measure back).
- **Tests that keep both honest.** Every D/E row in the register is either
  measured or given a reason, or the suite fails - so adding a row forces the
  runner to account for it. And every tool a prompt names is checked against
  the registry, so a prompt cannot send the AI after a tool that was renamed.
  52 new tests; 1107 offline.

## 1.3.0 - 2026-10-26 - Complex geometry, annotation and 3D

Server only; the plug-in is unchanged at 1.1.0. 12 new tools, 101 in all.
Everything COM touches is **NOT RUN**: see
[NEEDS-CHECKING group E](docs/NEEDS-CHECKING.md). Detail:
[docs/10](docs/10-geometry-annotation-3d.md).

- **Simple words, complex geometry.** `autocad_make_shape` draws 24 named
  shapes from their dimensions: slot, rounded rectangle, hexagon sized across
  the flats, flange with its bolt circle, steel sections (i/h/c/l/t/shs/rhs/chs),
  elbow with its centreline, duct transition, stair in section or plan, ladder,
  truss, grating, gear, spiral, star, zigzag, and **the flat pattern for a
  reducer** - plus the drafting furniture (detail bubble, section mark, north
  point, scale bar, level mark, revision tag). Each shape is a pure generator
  ([D-30](docs/DECISIONS.md)) drawn through the batch engine, so the geometry is
  tested without AutoCAD, it lands as one undo step, and `coords="ucs"` works
  on all of it. `dry_run` hands back the geometry instead of drawing it.
- **Arcs stay part of their object.** `autocad_batch_draw` polylines now take
  `bulges`, so a slot, a rounded corner, an elbow and a flat pattern are each
  *one* polyline rather than a pile of loose arcs. Text now takes `align` and
  `style`, so a bubble's number sits on its point.
- **Dimension the run, not the dimension.** `autocad_dimension_run` lays out a
  whole run in one call - `chain` (AutoCAD's Continue), `baseline` stepped
  clear of itself, `overall`, or `ordinate` from a datum, on any of the three
  axes. The points are put in order first, and every span is worked out here as
  well as measured by AutoCAD, so a run that does not add up says so.
  `autocad_add_centre_marks` puts the cross on every circle and arc, by handle
  or by layer.
- **Annotation that needs more than one object.** `autocad_add_multileader` is
  one note with as many arrows as it needs, text or block content.
  `autocad_add_table` puts a schedule on the sheet as a real AutoCAD table with
  a title and headings - pair it with `autocad_extract_attributes`.
  `autocad_add_revision_cloud` clouds a boundary, a rectangle or an object's
  own extents as one polyline with bulges, its arc spacing adjusted to divide
  the boundary exactly and its bulge signed so the arcs always face outward.
- **3D.** `autocad_add_solid` (box, wedge, cylinder, cone, sphere, torus),
  placed by the centre of its **base** rather than of its bounding box, which
  is what AutoCAD's own calls do and is never what a drafter means.
  `autocad_extrude_profile` turns a closed 2D profile into a solid by extruding
  (with taper) or revolving, cleaning up the intermediate region afterwards.
  `autocad_solid_boolean` does union, subtract and intersect, checking every
  handle **before** anything is consumed and reporting the volume before and
  after. `autocad_solid_properties` reads volume, centroid, bounding box and
  moments. `autocad_draw_3d_path` draws a pipe route or a helix as one 3D
  polyline. `autocad_set_3d_view` sets a named direction and a visual style and
  needs no padlock, because it changes only what is on screen
  ([D-31](docs/DECISIONS.md)).
- Drafting rules 16-23 added to [docs/07](docs/07-drafting-rules.md) and to the
  server's own instructions.
- 402 more offline tests. The flat pattern is checked the only way that counts:
  its arcs have to be exactly as long as the girths they roll onto. Two real
  faults were found and fixed while writing them - a `color` key that was doing
  double duty as both a filter and a target colour in the layer remapper, and a
  cone-development guard that could never fire while the hazard it was meant to
  catch (a polyline bulge running away near 360 degrees) went unguarded.

## 1.2.0 - 2026-10-26 - Sheets, coordinates and shop drawings

Server only; the plug-in is unchanged at 1.1.0. 14 new tools, 89 in all. Everything COM touches is
**NOT RUN**: see [NEEDS-CHECKING group D](docs/NEEDS-CHECKING.md). Detail:
[docs/09](docs/09-sheets-and-coordinates.md).

- **The UCS, at last.** Every coordinate here is a world coordinate and the modeller's are not, so
  `autocad_status` now reports the drawing's UCS and warns in plain words when it is not the world
  one; `autocad_get_ucs`, `autocad_set_ucs` and `autocad_convert_points` (AutoLISP's `trans`) make
  it workable; and `autocad_batch_draw` takes `coords="ucs"`, converting every point and angle
  before anything is sent — a rectangle square to a turned grid comes out turned. A tilted UCS is
  refused for a flat request rather than guessed ([D-27](docs/DECISIONS.md)).
- **Sheets.** `autocad_create_layout`, `autocad_page_setup` (one sheet or all of them),
  `autocad_place_title_block` (one sheet or all of them, with per-sheet attributes) and
  `autocad_add_viewport`. The viewport's model window is worked out to the viewport's own
  proportions, so 1:50 comes out 1:50; leave the scale out and the largest standard scale that fits
  is chosen; `twist` / `align_to_ucs` makes a rotated plan read upright; and viewports lock by
  default, because an unlocked one gets scrolled and the scale on the title block stops being true.
  Frame to ISO 5457 (20 mm binding edge, 10 elsewhere, title block bottom-right).
- **One location, used everywhere.** `autocad_save_view` and `autocad_list_views` name an area once;
  `autocad_export` gained `area` (`layout`, `window`, `view`, ...) and `scale`, and
  `autocad_add_viewport` takes the same `view_name` — so the area plotted and the area in the
  viewport are the same area.
- **Drawing settings.** `autocad_drawing_setup` takes the scale once and sets DIMSCALE, the
  annotation scale and LTSCALE from it, plus units, precision, snaps, point style and limits;
  `autocad_create_styles` makes text and dimension styles, putting the drawing's own DIM variables
  back afterwards. Both write only from a fixed list in code, which is why they need Changes and not
  Admin ([D-28](docs/DECISIONS.md)), and both report every old value beside its new one.
- **An import into a shop drawing.** `autocad_remap_layers` puts everything on the right layers and
  makes those layers properly (rules match the old layer name *or* the block name, the type, the
  colour or the text; `preset="ifc"` is a starting point, `rules_path` takes an office standard);
  `autocad_tidy_entities` clears the per-object colour / linetype / lineweight overrides that make a
  layer change look like it did nothing, flattens Z, moves geometry off layer 0 and deletes the
  zero-length leftovers. Both default to `dry_run=true`.
- **`autocad_sequence`:** AutoLISP's `progn` as a tool. Several tools in one call, every step's
  arguments checked against that tool's own schema before the first one runs. It refuses Publish and
  Admin steps and a sequence inside a sequence, so it can never spend more than the Changes padlock
  ([D-29](docs/DECISIONS.md)); a test asserts that against every registered Publish and Admin tool
  by name.
- Drafting rules 9-15 added to [docs/07](docs/07-drafting-rules.md) and to the server's own
  instructions, so every AI that connects follows them.
- 286 more offline tests (`tests/test_coords.py`, `test_sheets.py`, `test_settings.py`,
  `test_convert.py`, `test_sequence.py`): all the UCS arithmetic, the sheet arithmetic, the
  plain-words-to-system-variables mapping, the layer and tidy plans, and the sequence's ceiling.

## 1.1.0 - 2026-10-26 - Heron AI for AutoCAD

- The whole Lee Mac study built (D-26): 16 more tools (attributes, numbering, text count / clean /
  replace / align, polyline info, field labels, connected runs, segment labels, place along, place
  from CSV, break at blocks, import from drawing, layouts) and 6 add-ons; 75 tools in all. Live A29.
- Take-off tools from the Lee Mac study (ideas only, our own code, D-26): `autocad_count_blocks`,
  `autocad_total_length`, `autocad_get_dynamic_properties`, `autocad_set_dynamic_properties`.
- Fixes from live check A28: `autocad_list_blocks` counts dynamic copies by real name and skips
  blank names; `.dwg` paths with forward slashes insert; a disconnected COM pointer is retried.
- Drafting rules built in: server instructions + `draw_detail` prompt + docs/07 (D-25).
- New `autocad_make_block`: parts become named blocks in place (D-24). Labels can hang right-aligned.
- New `autocad_add_label`: MTEXT + LEADER in Ajmal's TLD style (L or angled), or a MULTILEADER;
  arrows and dimensions now take DIMSCALE (D-24).

- Removed the `generators/` folder (AHU, CCTV, pole-enclosure scripts); the drawings stay on the PC,
  the scripts in git history at `a443df4` ([D-23](docs/DECISIONS.md)).

- **Live checks on AutoCAD 2027:** 18 rows PASS. From them: units must be checked before any change
  (D-19); a double-click on a padlock counts once (D-20); "press Heron" is said before the units rule;
  `HERON_CONVERSATION_ID` for scripts. Batch drawing no longer loads a file, so AutoCAD's security box is gone (D-21), and its input goes
  through the plug-in with echo off: clean command history and about 8x faster (D-22). The Keep box
  works from the keyboard (focus, blue border, Enter, Esc), and a double-click within 1.5 s counts once.

- **Renamed Heron AI for AutoCAD** ([D-12](docs/DECISIONS.md)); repository `Ajmalpshaik/Heron-AutoCAD`.
- **New plug-in** `autocad/`: ribbon tab Heron / AI Bridge, connect button (lit / dark heron),
  Changes, Publish, Admin and Ask to Keep padlocks, Bridge Status window, READING / CHANGING / DONE /
  STOPPED banner, Keep or Discard, commands `HERON*`. Builds for AutoCAD 2021-2027 ([D-13](docs/DECISIONS.md)).
  **Not yet run live** ([NEEDS-CHECKING](docs/NEEDS-CHECKING.md)).
- **Every tool is gated** by the plug-in: risk level per tool, padlocks, one chat at a time,
  wrong-drawing guard, Keep or Discard, audit log ([D-14](docs/DECISIONS.md)).
- A write AutoCAD interrupts is never re-run: "outcome unknown" instead ([D-15](docs/DECISIONS.md)).
- Created objects are read back by handle (`verified`).
- New tools: `autocad_preview` (PNG back to the AI), `autocad_check_standards`,
  `autocad_extract_attributes`. New resources `autocad://drawing/{status,layers,blocks,styles}` and
  prompts `check_standards`, `draw_from_spec`. New start options `--read-only`, `--no-bridge`.
- `tools/build_plugin.py`, `tools/install_plugin.py`, `tools/check_structure.py`; CI builds the
  plug-in three ways and runs the bridge tests.
- `pyproject.toml` now says `mcp>=2.0` (the code needs 2.x).

## 2026-10-26 - Repository and documentation

- Made the repository public ([D-10](docs/DECISIONS.md)).
- Took the generated drawings out of git, including from all past commits; they stay on the PC only
  ([D-11](docs/DECISIONS.md)).

- Put the project under git and pushed it to a private GitHub repository, `Ajmalpshaik/AutoCAD-MCP`.
- Re-arranged the folders into parts, the way Heron AI is laid out ([D-05](docs/DECISIONS.md)):
  `drawings/source/` -> `generators/`, the AHU outputs -> `drawings/AHU/`, `scripts/` -> `tools/`,
  the stopped Revit enclosure experiment -> `archive/revit_encl/`.
- Generators no longer carry a typed `D:\...` path; all folders come from `generators/paths.py`.
- Wrote the documentation set: AGENTS, CONTRIBUTING, SECURITY, a README per folder, and `docs/`
  (index, project map, overview, architecture, tools reference, generators, known limits, decisions,
  handover, roadmap).
- Added GitHub CI (ruff + offline tests on Windows), issue and pull-request templates.
- Fixed `.codex/config.toml`, which still pointed at the old `D:\Ajmal\AutoCAD APP\...` folder.

## 2026-10-22 - CCTV pole enclosure detail

- `generators/encl_detail.py` and `encl_run.py`: A1 installation detail of the 400x400x120 pole
  enclosure, Type A (1 camera) and Type B (2 cameras). Fibre type still TBC.

## 2026-10-21 - CCTV drawing package

- 42-sheet CCTV package for a sample B1+G+4 building to MOI SSD (Qatar) rules, `generators/cctv_*.py`.

## 2026-10-19 - Local setup repaired, PDF export fixed

- Rebuilt the broken `.venv`; pointed `.mcp.json` at it.
- `autocad_export` PDF works on AutoCAD 2027: configure the layout for the pc3, then plot with the
  path only. Accepts `paper_size` (`A3`, `A1 portrait`). Pinned by `tests/test_export.py`.
- AHU-01 11-sheet package generated, `generators/ahu_*.py`.

## 1.0.0 - 2026-08-25

- First version: 50 tools, COM worker thread, AutoLISP batch drawing, offline and live tests.
