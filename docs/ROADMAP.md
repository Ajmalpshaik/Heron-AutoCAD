# Roadmap

Ideas and known gaps, **not started**. Move an item to [HANDOVER](HANDOVER.md) when work begins and
to [CHANGELOG](../CHANGELOG.md) when it lands. Proving what is built comes first:
[NEEDS-CHECKING](NEEDS-CHECKING.md).

## Plug-in

- [ ] A Companion page like Heron's in Revit (drawing, view, selection, activity list). ([#91](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/91))
- [ ] A docked **activity palette** in AutoCAD (today: `autocad_activity` in the chat, D-54) with Zoom per job. ([#92](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/92))
- [ ] A **saved-command palette** in AutoCAD (today: `autocad_saved_command` run from the chat, D-55). ([#93](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/93))

## Ideas from Heron AI for Revit, compared on 2026-11-21

Each is a GitHub issue with the `from-heron-revit` label; the issue says what Revit does and what
done looks like here.

- [ ] **Padlocks a file cannot switch on** ([#76](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/76), bug) and a Windows policy that holds one off ([#77](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/77)).
- [ ] A chat reopened after a Claude restart keeps its hold ([#78](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/78), bug).
- [ ] One plain result line: DONE / NOTHING CHANGED / REFUSED / OUTCOME UNKNOWN ([#79](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/79)); no empty undo step ([#80](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/80)).
- [ ] Dry run for any change ([#81](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/81)); before / after values ([#82](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/82)).
- [ ] Dialog watch during a job ([#83](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/83)).
- [ ] Check lists: NO DATA + coverage ([#84](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/84)), office list + project changes ([#85](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/85)), Excel / HTML report ([#86](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/86)), never "complies" ([#87](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/87)).
- [ ] "Why can't you do this?" ([#88](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/88)), what failed / was slow ([#89](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/89)), question mode in tool finding ([#90](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/90)).
- [ ] AutoCAD ribbon coverage audit ([#94](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/94)); an honest install table ([#95](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/95)).
- [ ] Later: spreadsheet round trip for attributes ([#96](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/96)), check a folder of drawings ([#97](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/97)).
- Not taken: Heron for Revit's knowledge store, standards answers with citations, HVAC / fire
  calculators and usage counter (AutoCAD has no knowledge store), and its proven-only change gate
  (D-117: AutoCAD keeps NEEDS-CHECKING as a record, not a gate).
- [x] Emergency stop: **Stop Heron now** in the Heron menu, or `HERONSTOP` ([D-51](DECISIONS.md)).
- [ ] Sign the add-in DLLs, so AutoCAD's SECURELOAD never asks. ([#72](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/72))
- [ ] An installer `.exe` / `.msi` for modellers (today: two Python scripts). ([#73](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/73))
- [ ] Move tools into the plug-in one at a time where it pays off (speed, true transactions), keeping COM as the fallback. ([#74](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/74))

## Found in the first live checks (2026-10-26)

- [ ] A batch still leaves one `Command:` prompt per piece in the history (about 27 for 41 objects).
  Harmless; fewer, larger pieces may be possible through the plug-in (the 600-character limit was
  measured for COM SendCommand). ([#45](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/45))
- [ ] `autocad_preview`: the picture comes out portrait with the drawing at the left edge; fit and
  centre it, landscape when the drawing is wide. Probably fixed with J6 (the preview now plots
  centred at 0 degrees); look at one live before ticking it.
- [x] **Choose which AutoCAD** when several are open: `autocad_use_autocad` ([D-49](DECISIONS.md)); one connected is used whichever COM gives, two need a pick (A15).
- [ ] Remaining live rows: A9 ribbon label, A8e confirmation.
- [x] `autocad_list_blocks` listed blank names and lost changed dynamic copies (`*U` names): now
  counted by real name, blank names skipped, `dynamic` flag added (A28).
- [x] `autocad_insert_block` with a forward-slash .dwg path failed "Key not found": paths are now
  normalised to backslashes (A28).
- [x] "Object invoked has disconnected" (RPC_E_DISCONNECTED) is now treated as a dead pointer:
  re-dispatch and retry. The live export test no longer fails in the full suite.

## Found on 2026-10-28 (chilled water roof pipe support, AutoCAD 2027)

- [x] `autocad_drawing_setup(scale='1:10')`, a dim style with a `text_style`, table text height,
  booleans on real solids and `visual_style='realistic'` all failed live; fixed with tests, re-run
  rows D23, D32, E18, E28, E34 NOT RUN ([D-35](DECISIONS.md), [D-36](DECISIONS.md)).
- [ ] Read the current visual style back (the VPORT table's visual style, through the plug-in), so
  `autocad_set_3d_view` can prove the style took instead of relying on `autocad_preview`. ([#59](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/59))
- [x] `tests/test_geometry.py`: two tests compared lists of point pairs with `pytest.approx`, which
  pytest 9 refuses ("does not support nested data structures"); CI turned red on 2026-10-28 when
  it picked up pytest 9. Now compared as flat coordinate lists, same values and tolerance.

## Found on 2026-10-28 (automation room power and control SLDs, AutoCAD 2027)

- [ ] **Change the shape of something already drawn.** `autocad_modify_entity` changes layer,
  colour, text and radius, but not a polyline's vertices or a line's end points. A box drawn too
  tall had to be deleted and drawn again, and a delete needs the modeller's yes each time. Add
  vertex / end-point editing (or a stretch tool) with offline tests, then a live row. ([#49](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/49))
- [ ] `autocad_preview` with `area='extents'` on an A1 schematic drawn at 1:1 showed only the two
  frame rectangles; `area='window'` over the same parts showed everything. Find out why before
  trusting an extents preview of a full sheet. ([#41](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/41))
- [x] A chat's server keeps the code it started with: `autocad_drawing_setup(scale='1:1')` failed
  with the fault already fixed in a2acf6a, because that server was older than the merge. Done:
  `autocad_status` reports `server_version` and `plugin_version`, and `autocad://diagnose` warns
  when the server's files changed after the chat started it ([D-48](DECISIONS.md)).

## Found on 2026-11-05 (cassette AC and bedroom 3D models, AutoCAD 2027)

- [x] The DONE card stayed on screen after a job whose end was lost: `BannerJobs`, live rows J1-J2.
- [x] `autocad_fillet_solid_edges` failed with "BoundaryRepresentation.Exception ... Nothing was
  changed" on every solid tried, **even a plain 500 x 700 x 160 box** (`edges='all'`, r=60) and
  extruded rounded rectangles (`edges='top'`). Rows H3-H4 are likely to FAIL; find the cause
  before relying on the tool. **Fixed:** the Brep was built from the entity, which has no
  subentity paths (`get_SubentityPath` threw, Heron log); now built from the solid's
  FullSubentityPath, read first and upgraded after. Live row J3.
- [x] `autocad_run_lisp` left AutoCAD inside an interactive command (DVIEW, CAMERA): the plug-in's
  own result write was then typed into that prompt and every later call waited, until the COM
  link dropped. After evaluating, check CMDACTIVE and cancel what the expression left open, and
  say so in the result ([05 §21](05-known-limits.md#21-a-command-left-open-by-autolisp-blocks-everything)).
  **Fixed:** the wrapper cancels it before writing the result and names it in
  `cancelled_command`; running snaps are off for the call. Live row J4.
- [x] `autocad_create_layout` with the default plotter failed ("no plotter called 'DWG To
  PDF.pc3'") but **still created the layout**, so the retry said the name was taken. Create the
  layout only after the plotter is found, or remove it on failure. **Fixed:** the plotter is
  retried on a freshly fetched layout, and a failed page setup deletes the new layout. Live row J5.
- [x] `autocad_preview` of 3D views in the cassette drawing came out turned 90 degrees (the same
  calls in a fresh drawing were upright). Probably the layout's plot rotation; set it for the
  preview and put it back. **Fixed:** the preview plots at 0 degrees; the snapshot restores the
  layout's own rotation. Live row J6.

## Asked for on 2026-10-28, not buildable over COM

- [x] **Super hatch** with a block: `autocad_super_hatch`, done by the plug-in (D-40, 2026-10-29).
  Built and compiled for every version; live rows H10-H12 NOT RUN.
- [ ] Super hatch with an image, an xref or a wipeout as the tile (Express Tools offers them). ([#57](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/57))
- [x] **3D modelling commands** with no ActiveX call: loft, fillet / chamfer edges, shell,
  press-pull, thicken, and the face and edge listing they pick from - done by the plug-in (D-40,
  2026-10-29). Built and compiled; live rows H1-H9 and H13 NOT RUN, so **not yet proven**.
- [ ] Loft to a surface (open outlines), surfaces from curves (PLANESURF, NETWORK) and meshes. ([#58](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/58))
- [ ] `autocad_draw_multiline` close with a mitred corner (MLINE's own Close) - needs the plug-in. ([#55](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/55))
- [ ] `autocad_draw_spline` by control points, and editing a spline's fit points. ([#56](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/56))

## Asked for on 2026-11-05 (villa model, render)

- [x] **Lights** (point, spot, web, distant) and **materials** made from their settings:
  `autocad_add_light`, `autocad_create_material`, done by the plug-in (D-42). Live rows K1-K12 NOT RUN.
- [x] Save a **3D view** as a named view: `autocad_save_view(from_screen=true)`. Live row K13 NOT RUN.
- [x] A material texture's **real-world size** (a 600 x 600 tile, a 150 plank):
  `autocad_create_material(texture_size=...)` ([D-46](DECISIONS.md)); live row K15.
- [ ] List and switch lights (the Lights in Model palette), and turn the sun and DEFAULTLIGHTING
  on and off, from the chat. ([#63](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/63))

## Asked for on 2026-11-09 (Luxury Suite 2 3D model and its interior drawing set)

- [ ] **Camera views**: a perspective camera at an eye point with a lens (24 mm inside a room).
  `-VIEW` saves only the screen; a VIEW record made with entmake restores at 50 mm and DVIEW hangs.
  What worked: `CAMERA cam target _N name _LE 24 _X`, then CAMERADISPLAY 0. ([#60](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/60))
- [ ] **Sun date, time and place**: no system variable; the SUN object of the active VPORT
  (group 361) takes 91 = Julian day and 92 = milliseconds after midnight. LATITUDE, LONGITUDE,
  TIMEZONE and SUNSTATUS are plain variables. ([#61](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/61))
- [ ] **Render exposure**: the LOGEXP* variables are gone in 2027; exposure lives only in the
  RENDEREXPOSURE palette. Find whether the render preset or render environment object exposes it. ([#62](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/62))
- [ ] **Quiet results**: an `autocad_sequence` of eight `autocad_dimension_run` steps returned about
  15,000 characters of per-dimension detail. A `quiet` option that returns counts and handles only. ([#44](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/44))
- [ ] **Sheets by the plug-in**: make layouts and viewports in .NET (Layout + Viewport in the layout's
  block), so neither depends on `doc.PaperSpace`, which threw on 2026-11-09 (known limit 23). ([#64](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/64))

## Server

- [x] Dynamic blocks: read and set properties (`autocad_get/set_dynamic_properties`). Authoring
  parameters and actions has no API; it stays a Block Editor job.
- [x] The Lee Mac ideas: all built ([08](08-lee-mac-study.md)).
- [ ] `autocad_break_at_blocks` for polylines with arcs, through the plug-in's curve splitting. ([#52](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/52))

- [ ] `autocad_batch_draw`: hatch, mtext and dimension operations. Polyline bulges and text
  justification landed with the shape library (D-30); these three are what is left. ([#51](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/51))
- [ ] A hatch or solid fill for the furniture shapes: an arrowhead and a north point come out as
  outlines today, because a batch has no fill. ([#51](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/51))
- [ ] `autocad_make_shape`: a 3D shape group (duct runs, pipe spools) once the solid tools have a
  live check behind them. ([#53](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/53))
- [ ] Flatten a 3D solid to 2D views for a shop drawing (AutoCAD's SOLPROF / FLATSHOT). No
  Automation call, so it needs the plug-in or an Admin command. ([#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54))
- [ ] Multileader, table and dimension **style** creation from `autocad_create_styles`: no
  Automation API for the first two, and a dimension style already works, so this is really
  "bring the office styles in" - `autocad_import_from_drawing` does it today. ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68))
- [x] Draw an attribute schedule as an AutoCAD table: `autocad_add_table` ([10](10-geometry-annotation-3d.md)).
- [ ] Standards check against a reference DWG / DWS, not only a rules file. ([#69](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/69))
- [ ] A layer-standard rule file shipped for Ajmal's own office standard, beside the `ifc` preset
  in `tools/convert.py` (which is a starting point, not a standard). ([#70](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/70))
- [ ] Read DXF / DWG files without AutoCAD (ezdxf, plus the ODA converter for DWG), read only. ([#71](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/71))
- [x] Paper-space layouts and viewports: `autocad_create_layout`, `autocad_page_setup`,
  `autocad_place_title_block`, `autocad_add_viewport` (D-27, [09](09-sheets-and-coordinates.md)).
- [ ] `coords="ucs"` on the single-entity `autocad_draw_*` and `autocad_modify_*` tools. Today only
  `autocad_batch_draw` has it; the rest need each tool's rotation and planar vertex list converted
  too, and no live check behind it yet (D-27). ([#50](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/50))
- [ ] Multileader, table and plot-style-table creation: no Automation API, so today they come in
  with `autocad_import_from_drawing`. Worth moving into the plug-in. ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68))
- [ ] `autocad_add_viewport`: clip a viewport to a polyline, and annotative viewport scales. ([#65](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/65))
- [ ] A sheet-set tool: one call per drawing list (sheet number, title, scale, view) across a whole
  package, on top of `autocad_sequence`. ([#66](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/66))
- [ ] Split long `autocad_run_lisp` expressions instead of failing silently. ([#46](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/46))
- [x] From the ADN-DevTech study ([11](11-adn-repos-study.md), D-41, 2026-11-04): multi-sheet PDF
  (`autocad_publish_pdf`), xref tree, drawing report, the command name in the busy message,
  `tools/memory_check.py`, the Plant 3D known limit. Built; group I NOT RUN.
- [ ] Multi-sheet PDF of **a folder of drawings**, not only the open one (the publisher takes other
  DWGs; each must be checked for unsaved changes and xrefs first). ([#67](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/67))
- [ ] Use the add-in's command tracker for the server's own busy answers too, not only plug-in
  operations ("Outcome unknown: AutoCAD went busy", rows D8, D33). ([#47](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/47))
- [ ] Document events to feed the wrong-drawing guard and a Companion activity list. ([#48](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/48))
- [ ] `core/audit.py`: with `%LOCALAPPDATA%` unset, `audit_dir()` resolves to a relative
  `Heron/autocad/audit` in the working directory. Windows always sets it, so this only
  shows up running the code off Windows; worth an explicit fallback anyway. ([#43](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/43))
- [ ] `send_command` with an undo-stack command (UNDO, U, REDO, MREDO, OOPS) is sent outside an undo mark, so it does not mark "write started" and a busy retry can still re-run it ([D-15](DECISIONS.md)). Every other `send_command` and every `run_lisp` now runs inside `undo_mark`. ([#42](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/42))
- [ ] `autocad_dimension_run`: an optional `dim_style` (an existing style name), so a 1:5 detail
  does not have to change DIMSCALE through `autocad_drawing_setup` mid-run (asked 2026-11-18). Not
  built in D-57 because it cannot be proved offline. Traps found: the tool sets every dimension's
  `ScaleFactor` to the drawing's DIMSCALE, which would hide the style's own scale; and making the
  style active for the run, then putting the old one back, wipes DIMSCALE overrides that
  `autocad_drawing_setup` left on the active style. Likely shape: set `StyleName` per dimension and
  skip the `ScaleFactor` write when a style is given; check the size live before trusting it. ([#37](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/37))
- [ ] About 70 places turn a COM error into a plain `AutocadError`, and a few `except` blocks take
  any error for "not there" (as `ensure_layer` did until D-57). The message filter now hides short
  busy spells from all of them; a refusal longer than its 3 s still reads as a failure there, not
  as busy. Go through them and let a busy refusal up as it is, as `tables.py` now does. ([#36](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/36))

## Repository

- [ ] Tag `v1.6.0` after NEEDS-CHECKING groups A, D, E and F pass - `tools/live_check.py --group all --write` does D, E and F.
- [ ] Later: offer this repository to Heron AI as its AutoCAD adapter when Heron's capability registry is ready ([D-12](DECISIONS.md)). ([#75](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/75))
- [ ] With a sheet tab active, `autocad_status` and `autocad_add_table(space="paper")` raised a bare
  `Exception occurred` (2026-10-28, row D33). Status is what the gate waits for, so every tool was
  blocked until the Model tab was clicked. Reproduce live, find the call (suspect `doc.PaperSpace`),
  and let status answer in paper space. ([#39](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/39))
- [ ] `autocad_create_layout` answered `Outcome unknown: AutoCAD went busy` on every call although
  the tabs were made (2026-10-28, row D8). Find which step goes busy. ([#40](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/40))
