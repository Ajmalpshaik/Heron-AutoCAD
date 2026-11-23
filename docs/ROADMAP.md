# Roadmap

Ideas and known gaps, **not started**. Move an item to [HANDOVER](HANDOVER.md) when work begins and
to [CHANGELOG](../CHANGELOG.md) when it lands. Proving what is built comes first:
[NEEDS-CHECKING](NEEDS-CHECKING.md).

## Plug-in

- [x] A Companion page like Heron's in Revit (drawing, view, selection, activity list). ([#91](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/91)) First page: `autocad_companion`, a file per chat, no server (D-71); live rows Y6 NOT RUN. Editable tables and a dashboard need a local server: a later decision.
- [x] A docked **activity palette** in AutoCAD (today: `autocad_activity` in the chat, D-54) with Zoom per job. ([#92](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/92))
- [x] A **saved-command palette** in AutoCAD (today: `autocad_saved_command` run from the chat, D-55). ([#93](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/93))

## Ideas from Heron AI for Revit, compared on 2026-11-21

Each is a GitHub issue with the `from-heron-revit` label; the issue says what Revit does and what
done looks like here.

- [x] **Padlocks a file cannot switch on** ([#76](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/76), bug) and a Windows policy that holds one off ([#77](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/77)). D-59, D-60, PRs #121 and #140; live rows R1-R9 NOT RUN. Open: whether connect-at-start leaves the file too ([#141](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/141)).
- [x] A chat reopened after a Claude restart keeps its hold ([#78](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/78), bug). D-61, PR #124; live row T1 NOT RUN.
- [x] One plain result line: DONE / NOTHING CHANGED / REFUSED / OUTCOME UNKNOWN ([#79](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/79)). D-62, PR #124; live rows T2-T3 NOT RUN.
- [x] No empty undo step ([#80](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/80)). PR #124 (no undo step when nothing differs) and D-143 (a plug-in operation that touched nothing is aborted, live row AQ17). Open: the server's empty group waits for live row T7 ([#263](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/263), [05 §26](05-known-limits.md)).
- [x] Dry run for any change ([#81](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/81)); before / after values ([#82](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/82)). D-63 and D-62, PR #124; live rows T4-T6 NOT RUN.
- [x] Dialog watch during a job ([#83](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/83)).
- [x] Check lists: NO DATA + coverage ([#84](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/84)), office list + project changes ([#85](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/85)), Excel / HTML report ([#86](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/86)), never "complies" ([#87](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/87)). D-64 and D-65, PR #122; live rows U1-U10 NOT RUN.
- [x] Share the office check list and project changes with the team ([#135](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/135)): an office folder per PC with this PC's copy as the fallback, `autocad_share_checklist` (Publish). D-93; live rows AG9-AG14 NOT RUN.
- [x] "Why can't you do this?" ([#88](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/88)), what failed / was slow ([#89](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/89)), question mode in tool finding ([#90](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/90)).
- [x] AutoCAD ribbon coverage audit ([#94](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/94)); an honest install table ([#95](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/95)).
- [x] From the audit: attribute definitions and ATTSYNC ([#115](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/115), D-82), an Excel range as a linked table and table cell edits ([#117](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/117), D-83), copy between open drawings ([#106](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/106), D-83). Live rows AC1-AC16 NOT RUN.
- [x] ATTSYNC also for inserts nested inside other blocks' definitions ([#156](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/156)): `nested=true`. Live row AC17 NOT RUN.
- [x] Spreadsheet round trip for attributes ([#96](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/96), D-69), check a folder of drawings ([#97](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/97), D-70). Live rows Y1-Y5 NOT RUN.
- Not taken: Heron for Revit's knowledge store, standards answers with citations, HVAC / fire
  calculators and usage counter (AutoCAD has no knowledge store), and its proven-only change gate
  (D-117: AutoCAD keeps NEEDS-CHECKING as a record, not a gate).
- [x] Emergency stop: **Stop Heron now** in the Heron menu, or `HERONSTOP` ([D-51](DECISIONS.md)).
- [x] ~~Sign the add-in DLLs~~ NOT PLANNED: the owner decided against a code-signing certificate ([#164](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/164), [#72](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/72)); `tools/signing.py` stays for if that changes. ([#72](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/72))
- [x] An installer `.exe` for modellers: `tools/make_installer.py` (D-99). ([#73](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/73))
- [ ] Move tools into the plug-in one at a time where it pays off (speed, true transactions), keeping COM as the fallback. ([#74](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/74))
  The entity summary and a layer's extents moved first ([D-114](DECISIONS.md)); the ranked list of
  what comes next, one issue each: [13](13-moving-tools-into-the-plug-in.md).

## Found in the first live checks (2026-10-26)

- [x] A batch still leaves one `Command:` prompt per piece in the history (about 27 for 41 objects).
  Through the plug-in it now goes in pieces up to its `quietLimit` (1,500): 9 pieces instead of 25
  for that batch, offline ([D-98](DECISIONS.md), 2026-11-21; live rows AJ6, AJ7 NOT RUN). ([#45](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/45))
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
- [x] Read the current visual style back (the VPORT table's visual style, through the plug-in), so
  `autocad_set_3d_view` can prove the style took instead of relying on `autocad_preview`. ([#59](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/59)) `visual_style_found` (D-86); live row AE1 NOT RUN.
- [x] `tests/test_geometry.py`: two tests compared lists of point pairs with `pytest.approx`, which
  pytest 9 refuses ("does not support nested data structures"); CI turned red on 2026-10-28 when
  it picked up pytest 9. Now compared as flat coordinate lists, same values and tolerance.

## Found on 2026-10-28 (automation room power and control SLDs, AutoCAD 2027)

- [x] **Change the shape of something already drawn.** `autocad_modify_entity` changes layer,
  colour, text and radius, but not a polyline's vertices or a line's end points. A box drawn too
  tall had to be deleted and drawn again, and a delete needs the modeller's yes each time. Done
  2026-11-21: `autocad_edit_vertex` and `autocad_stretch`, with the trim / extend / fillet / join
  tools ([D-78](DECISIONS.md)); live rows AA11-AA12 NOT RUN. ([#49](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/49))
- [x] Lengthen (by a distance, to a total, by a percent), and a fillet or chamfer between a line and an
  arc: done 2026-11-23, `autocad_lengthen` and `autocad_fillet_chamfer` on lines, arcs and polyline ends
  ([D-144](DECISIONS.md)); live rows BH1-BH11 NOT RUN. ([#154](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/154))
- [ ] `autocad_preview` with `area='extents'` on an A1 schematic drawn at 1:1 showed only the two
  frame rectangles; `area='window'` over the same parts showed everything. Find out why before
  trusting an extents preview of a full sheet. ([#41](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/41))
  2026-11-21: most likely too few pixels for an A1 (about 0.5 mm a pixel), or extents stretched by
  something far off. The answer now says the area plotted and the smallest text that reads, and
  `detail=2` / `3` adds window close-ups ([D-102](DECISIONS.md)). Live row AM1 says which cause it was.
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
- [x] Super hatch with an image, an xref or a wipeout as the tile (Express Tools offers them): `autocad_super_hatch(image= / xref= / wipeout=)` (D-95); live rows AH12-AH14 NOT RUN. ([#57](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/57))
- [x] **3D modelling commands** with no ActiveX call: loft, fillet / chamfer edges, shell,
  press-pull, thicken, and the face and edge listing they pick from - done by the plug-in (D-40,
  2026-10-29). Built and compiled; live rows H1-H9 and H13 NOT RUN, so **not yet proven**.
- [x] Loft to a surface (open outlines), surfaces from curves (PLANESURF, NETWORK) and meshes: `autocad_loft(surface=true)`, `autocad_add_surface`, `autocad_add_mesh` (D-95); live rows AH9-AH11 NOT RUN. ([#58](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/58))
- [x] `autocad_draw_multiline` close with a mitred corner (MLINE's own Close) - by the plug-in's `close_multiline` (D-97). ([#55](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/55)) Live rows AI8-AI9 NOT RUN.
- [x] `autocad_draw_spline` by control points (`method="control_points"`, the plug-in's `add_cv_spline`), and editing a spline's fit points (`autocad_edit_spline`) (D-97). ([#56](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/56)) Live rows AI10-AI13 NOT RUN.

## Asked for on 2026-11-05 (villa model, render)

- [x] **Lights** (point, spot, web, distant) and **materials** made from their settings:
  `autocad_add_light`, `autocad_create_material`, done by the plug-in (D-42). Live rows K1-K12 NOT RUN.
- [x] Save a **3D view** as a named view: `autocad_save_view(from_screen=true)`. Live row K13 NOT RUN.
- [x] A material texture's **real-world size** (a 600 x 600 tile, a 150 plank):
  `autocad_create_material(texture_size=...)` ([D-46](DECISIONS.md)); live row K15.
- [x] List and switch lights (the Lights in Model palette), and turn the sun and DEFAULTLIGHTING
  on and off, from the chat. ([#63](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/63)) `autocad_list_lights`, `autocad_switch_lights` (D-87); live rows AE9-AE13 NOT RUN.

## Asked for on 2026-11-09 (Luxury Suite 2 3D model and its interior drawing set)

- [x] **Camera views**: a perspective camera at an eye point with a lens (24 mm inside a room).
  `-VIEW` saves only the screen; a VIEW record made with entmake restores at 50 mm and DVIEW hangs.
  What worked: `CAMERA cam target _N name _LE 24 _X`, then CAMERADISPLAY 0. ([#60](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/60)) `autocad_add_camera_view`, a view record with perspective and the lens (D-86); live rows AE2-AE4 NOT RUN.
- [x] **Sun date, time and place**: no system variable; the SUN object of the active VPORT
  (group 361) takes 91 = Julian day and 92 = milliseconds after midnight. LATITUDE, LONGITUDE,
  TIMEZONE and SUNSTATUS are plain variables. ([#61](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/61)) `autocad_set_sun` (D-86); live rows AE5-AE8 NOT RUN.
- [x] **Render exposure**: the LOGEXP* variables are gone in 2027; exposure lives only in the
  RENDEREXPOSURE palette. Find whether the render preset or render environment object exposes it. ([#62](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/62)) Found: neither the preset nor the environment object holds it; the documented EXPVALUE / EXPWHITEBALANCE do. `autocad_set_render_exposure` (D-87), known limit 22; live row AE14 NOT RUN.
- [ ] If AE14 shows EXPVALUE / EXPWHITEBALANCE are gone in 2027: set the exposure on the current
  viewport's `PhotographicExposureParameters` (Exposure, WhitePoint) through the plug-in instead,
  after a live check that the renderer reads it (D-87).
- [x] **Quiet results** (D-77, 2026-11-21: `quiet=true`): an `autocad_sequence` of eight `autocad_dimension_run` steps returned about
  15,000 characters of per-dimension detail. A `quiet` option that returns counts and handles only. ([#44](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/44))
- [x] **Sheets by the plug-in** (D-90, 2026-11-21: operations `create_layout`, `add_viewport`; COM the fallback; live rows AF1-AF11 NOT RUN): make layouts and viewports in .NET (Layout + Viewport in the layout's
  block), so neither depends on `doc.PaperSpace`, which threw on 2026-11-09 (known limit 23). ([#64](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/64))

## Server

- [x] Dynamic blocks: read and set properties (`autocad_get/set_dynamic_properties`). Authoring
  parameters and actions has no API; it stays a Block Editor job.
- [x] The Lee Mac ideas: all built ([08](08-lee-mac-study.md)).
- [ ] Left from part 2 of #119 (D-110, D-111): turned grids in `autocad_associative_array`, DWFx in `autocad_export`, coordinate systems in feet in `autocad_geo_location`. After Group AQ passes. ([#216](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/216))
- [x] `autocad_break_at_blocks` for polylines with arcs: bulge arithmetic in Python, each piece keeps its arc (D-97). ([#52](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/52)) Live row AI7 NOT RUN.

- [x] `autocad_batch_draw`: hatch (solid fill), mtext and linear dimension operations (D-96). ([#51](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/51)) Live rows AI4-AI6 NOT RUN.
- [x] A solid fill for the furniture shapes: `filled=true` on section_mark, north_arrow, scale_bar
  and level_mark (D-96). ([#51](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/51)) Off by default until AI4 passes.
- [ ] Hatch **patterns** in `autocad_batch_draw` (ANSI31, AR-CONC): entmake needs each pattern's
  line definitions written out, read from acad.pat. Today the batch fills solid only and
  `autocad_add_hatch` does patterns (D-96).
- [ ] Radial, diametric and angular dimensions in `autocad_batch_draw` (today: linear only; the
  single `autocad_add_dimension` does all of them) (D-96).
- [x] `autocad_make_shape`: a 3D shape group (duct runs, pipe spools): `duct_run`, `pipe_spool` (D-94);
  live rows AH1-AH3 NOT RUN. ([#53](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/53))
- [x] Flatten a 3D solid to 2D views for a shop drawing (AutoCAD's SOLPROF / FLATSHOT):
  `autocad_flatten_views`, by the plug-in (D-95); live rows AH4-AH5 NOT RUN. ([#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54))
- [x] A section plane and a 2D section from a 3D model: `autocad_section_plane`, by the plug-in
  (D-95); live rows AH6-AH8 NOT RUN. ([#109](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/109))
- [x] Hidden (obscured) lines in a flat view, on their own layer, and jogged section lines:
  `hidden_lines` and `jogged` (D-152); live rows AH17-AH21 NOT RUN. ([#171](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/171))
- [x] Multileader, table and dimension **style** creation from `autocad_create_styles`: the
  multileader and table styles by the plug-in since 2026-11-21 (D-104, live group AN NOT RUN).
  ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68))
- [x] Draw an attribute schedule as an AutoCAD table: `autocad_add_table` ([10](10-geometry-annotation-3d.md)).
- [x] Standards check against a reference DWG / DWS, not only a rules file: `autocad_check_standards(reference=...)`. ([#69](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/69), D-92; live rows AG5-AG8 NOT RUN)
- [ ] A layer-standard rule file for Ajmal's own office standard, beside the `ifc` preset in
  `tools/convert.py`. The format, a generic MEP example and the CSV import are built
  (`autocad_layer_standard`, `layer_standard` on the check and the remap; D-120, live group AT NOT
  RUN). **Waiting for Ajmal:** fill the CSV from the office's layer list on his own PC (it never
  goes in this public repository) and import it. ([#70](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/70))
- [x] Read DXF / DWG files without AutoCAD (ezdxf, plus the ODA converter for DWG), read only: `autocad_read_file`. ([#71](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/71), D-92; live rows AG1-AG4 NOT RUN)
- [x] Paper-space layouts and viewports: `autocad_create_layout`, `autocad_page_setup`,
  `autocad_place_title_block`, `autocad_add_viewport` (D-27, [09](09-sheets-and-coordinates.md)).
- [x] `coords="ucs"` on the single-entity `autocad_draw_*` and `autocad_modify_*` tools: points,
  vertex lists, angles and turns converted; a flipped UCS refused for text, blocks and dimensions
  (D-96). ([#50](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/50)) Live rows AI1-AI3 NOT RUN.
- [x] Multileader and table style creation in the plug-in (D-104). A plot style table cannot be
  made: AutoCAD's .NET API has no way to write the file (D-105, a known limit, 05 §34).
  ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68))
- [x] `autocad_add_viewport`: clip a viewport to a polyline, and annotative viewport scales (D-90, 2026-11-21: `clip_outline`, `clip_handle`, `annotation_scale`; live rows AF7, AF8 NOT RUN). ([#65](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/65))
- [x] A sheet-set tool: one call per drawing list (sheet number, title, scale, view) across a whole
  package (D-90, 2026-11-21: `autocad_sheet_set`, one undo step, not built on `autocad_sequence`; live row AF9 NOT RUN). ([#66](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/66))
- [x] Split long `autocad_run_lisp` expressions instead of failing silently (D-76, 2026-11-21: cut between top-level forms; live rows Z2-Z4 NOT RUN). ([#46](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/46))
- [x] From the ADN-DevTech study ([11](11-adn-repos-study.md), D-41, 2026-11-04): multi-sheet PDF
  (`autocad_publish_pdf`), xref tree, drawing report, the command name in the busy message,
  `tools/memory_check.py`, the Plant 3D known limit. Built; group I NOT RUN.
- [x] Multi-sheet PDF of **a folder of drawings**, not only the open one (the publisher takes other
  DWGs; each must be checked for unsaved changes and xrefs first) (D-91, 2026-11-21: `folder` / `drawings`; live rows AF12-AF15 NOT RUN). ([#67](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/67))
- [x] Use the add-in's command tracker for the server's own busy answers too (D-77, 2026-11-21: ping says `command`; live rows Z6-Z9 NOT RUN), not only plug-in
  operations ("Outcome unknown: AutoCAD went busy", rows D8, D33). ([#47](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/47))
- [x] Document events to feed the wrong-drawing guard and a live activity list ([D-98](DECISIONS.md), 2026-11-21: the plug-in records them, the guard and `send_quiet` use them, the docked palette shows them live; the Companion page stays a file written after each job; live rows AJ1-AJ10 NOT RUN). ([#48](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/48))
- [ ] `core/audit.py`: with `%LOCALAPPDATA%` unset, `audit_dir()` resolves to a relative
  `Heron/autocad/audit` in the working directory. Windows always sets it, so this only
  shows up running the code off Windows; worth an explicit fallback anyway. ([#43](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/43))
- [x] `send_command` with an undo-stack command (UNDO, U, REDO, MREDO, OOPS) is sent outside an undo mark (D-76, 2026-11-21: now marked as a write; live row Z1 NOT RUN), so it does not mark "write started" and a busy retry can still re-run it ([D-15](DECISIONS.md)). Every other `send_command` and every `run_lisp` now runs inside `undo_mark`. ([#42](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/42))
- [x] `autocad_dimension_run`: an optional `dim_style` (an existing style name), so a 1:5 detail
  does not have to change DIMSCALE through `autocad_drawing_setup` mid-run (asked 2026-11-18). Not
  built in D-57 because it cannot be proved offline. Traps found: the tool sets every dimension's
  `ScaleFactor` to the drawing's DIMSCALE, which would hide the style's own scale; and making the
  style active for the run, then putting the old one back, wipes DIMSCALE overrides that
  `autocad_drawing_setup` left on the active style. Likely shape: set `StyleName` per dimension and
  skip the `ScaleFactor` write when a style is given; check the size live before trusting it. ([#37](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/37))
  Built 2026-11-21 in that shape ([D-80](DECISIONS.md)); the size in a 1:5 detail is live row AB1, NOT RUN.
- [x] About 70 places turn a COM error into a plain `AutocadError`, and a few `except` blocks take
  any error for "not there" (as `ensure_layer` did until D-57). The message filter now hides short
  busy spells from all of them; a refusal longer than its 3 s still reads as a failure there, not
  as busy. Go through them and let a busy refusal up as it is, as `tables.py` now does. ([#36](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/36))
  Done 2026-11-21 ([D-100](DECISIONS.md)): `raise_if_busy` in about 250 places, about 40 left on purpose with
  their reasons, and `tests/test_busy_sweep.py` so new code cannot bring it back. Live rows AL1-AL7 NOT RUN.

## Repository

- [ ] Tag `v1.6.0` after NEEDS-CHECKING groups A, D, E and F pass - `tools/live_check.py --group all --write` does D, E and F.
- [ ] Later: offer this repository to Heron AI as its AutoCAD adapter when Heron's capability registry is ready ([D-12](DECISIONS.md)). This side's part is ready: the capability manifest and [14](14-heron-ai-adapter.md) ([D-122](DECISIONS.md)); the rest waits for Heron. ([#75](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/75))
- [ ] With a sheet tab active, `autocad_status` and `autocad_add_table(space="paper")` raised a bare
  `Exception occurred` (2026-10-28, row D33). Status is what the gate waits for, so every tool was
  blocked until the Model tab was clicked. Reproduce live, find the call (suspect `doc.PaperSpace`),
  and let status answer in paper space. ([#39](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/39))
  Fixed from the code 2026-11-21 (D-90): status reads each fact on its own and names the ones it
  cannot read, the sheet's count from its block or the plug-in; `space="paper"` falls back to the
  active layout's block. Left open until row AF10 is run live.
- [ ] `autocad_create_layout` answered `Outcome unknown: AutoCAD went busy` on every call although
  the tabs were made (2026-10-28, row D8). Find which step goes busy. ([#40](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/40))
  2026-11-21 (D-90): the plug-in now makes the sheet in one transaction, with no COM after it; over
  COM a busy moment after the layout is added is answered from the drawing read back. Left open
  until rows AF1, AF2 and AF11 are run live: which COM step went busy is still not seen.
