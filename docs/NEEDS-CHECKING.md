# Needs checking - what is built but not yet proven in a real AutoCAD

> A build is not a proof, and a passing offline test is not a proof. A row is **PASS** only after it
> was run in the named AutoCAD and gave the result in the last column. Four states, kept apart:
> **PASS**, **FAIL** (with what happened), **NOT RUN**, **NO MACHINE** (no PC with that version yet).
> Put the date and the AutoCAD version in the result.

**Set-up for every row:** build and install the plug-in (`tools/build_plugin.py`, close AutoCAD,
`tools/install_plugin.py`), start AutoCAD, open a scratch drawing, and connect Claude Code in this
folder.

**Groups D, E and F run themselves.** With AutoCAD open and the Changes padlock on:

```bash
.venv\Scripts\python.exe tools/live_check.py --group all --write
```

It works in a scratch drawing it makes itself, *measures* each row (a cone development's arcs
against the girths they roll onto, a 1:100 viewport's CustomScale, a solid's base against z=0)
and writes the answer and its evidence into the last column here. Most of the 90 rows are
measurable that way. The rest need an eye and are written **NOT RUN** with the reason;
`--list` names them. A row the padlocks refuse is **NOT RUN** too, never PASS.

## Group A - AutoCAD 2027 (this PC)

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| A1 | Start AutoCAD | Tab **Heron**, panel **AI Bridge**, dark heron, four blue padlocks; command line shows nothing alarming; log file written | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): tab, panel, dark heron, four padlocks off |
| A2 | Ask Claude "check the AutoCAD connection" before pressing Heron | Status answers, with `"heron": {"connected": false, ...}` and the press-Heron sentence | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): after Disconnect, status returned only `heron: connected false` + press-Heron sentence, no drawing data |
| A3 | Press **Heron** | Icon lights; command line `Heron: connected...`; `%LOCALAPPDATA%\Heron\autocad\bridges\<pid>.json` exists | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): icon lit/dark follows each click; address file written and removed |
| A4 | "List the layers" | READING banner (blue) appears, then DONE; the layers come back; `Heron: List Layers. Done in ...` | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): reads accepted; begin/end logged |
| A5 | "Draw a line from 0,0 to 1000,0" with Changes **off** | Refused naming **Changes** and HERONCHANGES; nothing drawn; no banner | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): draw and LISP refused naming Changes; drawing still empty; audit `refused` |
| A6 | Click **Changes**, answer Yes, repeat A5 | Red padlock; CHANGING banner (amber); line drawn; one Ctrl+Z removes it | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): asks before turning on; CHANGING banner seen; one U removed the rectangle |
| A7 | Click **Changes** again | Off with no question | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): turned off with no question |
| A8 | Ask to Keep on, Changes on, draw a circle, click **Discard it** | Circle selected and zoomed before the box; after Discard it is gone; chat says `Discarded: nothing was kept.` | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): box with circle selected and zoomed; Keep kept it; Discard removed it |
| A9 | Same, click **Keep, and keep the rest...**, then draw twice more | No more boxes; ribbon reads **Keep: rest of job** (within 15 s) | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): after 'keep the rest', next two draws had no box (61 / 78 ms). Ribbon label not confirmed |
| A8b | Ask to Keep on: draw, Keep; then draw again and Discard | Only the second drawing goes; the first stays; the view returns to where it was | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): earlier kept circle stayed; VIEWSIZE 2080 before and after Discard (view went back) |
| A8c | Ask to Keep on: `autocad_batch_draw` with a new layer, Discard | Objects and the new layer both gone | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): batch objects and its new layer both gone after Discard. See A21 |
| A8d | Ask to Keep on: delete with `confirm=false` (preview) | No Keep box; nothing undone | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): `confirm=false` preview gave no box and undid nothing |
| A8e | Ask to Keep on: draw, then leave the mouse still | The Keep box appears at once, without moving the mouse | **Likely PASS** 2026-10-26: answered 8 s after the draw; not confirmed in words |
| A23 | Keep box: press Enter, and another time Esc | Enter keeps, Esc discards, arrows move between choices | **FAIL then PASS** 2026-10-26: first only the mouse worked and nothing showed the keyboard's place; now the box takes focus, a thick blue border follows the arrow keys, and Enter chose the bordered choice (Discard, removed the circle) |
| A10 | Open a second drawing in the same AutoCAD, make it active, ask to draw | Refused: active drawing changed from A to B; after "check status" the draw works | **FAIL then PASS** 2026-10-26, AutoCAD 2027 (26.0s): a fresh server let the first change through unchecked; fixed (D-19: units checked first); re-run refused before status and after switching, Drawing2 = millimetres, Drawing1 = inches |
| A11 | "Export to PDF" with Publish off, then on | Off: refused naming Publish. On: PDF written | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): on wrote an A3 PDF; off refused naming Publish, no file |
| A12 | "Run the LISP (+ 1 2)" with Admin off, then on | Off: refused naming Admin. On: 3 | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): on returned 3; off refused naming Admin |
| A13 | "Show me the drawing" | `autocad_preview` returns a PNG the chat can see; page setup unchanged (PAGESETUP) | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): PNG received by the chat. Note: portrait, drawing at the left edge (ROADMAP) |
| A14 | Press **Heron** to disconnect, ask anything | Icon dark; address file gone; every tool refused with the press-Heron sentence | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): icon dark, address file gone, tools refused with press-Heron |
| A15 | Two AutoCAD 2027 windows, connect only the second | Claude reaches the one COM attaches to; if that one is not connected, it is refused (no cross-talk) | **PASS** 2026-10-26: COM attached to the first (pid 16068); with the first connected it worked on CCTV_Package.dwg; with only the second (pid 40440) connected, every call was refused 'not connected' and nothing reached either AutoCAD. Limit: the second cannot be chosen yet (ROADMAP) |
| A16 | Second Claude session asks while the first is working | Second refused: in use by another chat; works after 3 quiet minutes | **PASS** 2026-10-26: second chat refused ('in use by another chat', no drawing data) at 1.4 min; let in after 3 quiet minutes (status + layers of CCTV_Package.dwg) |
| A17 | Switch workspace (WSCURRENT) | Heron tab comes back | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): tab still there after a workspace switch |
| A18 | Bridge Status in each state | Wording and buttons as in [06 §2](06-heron-plugin.md#2-bridge-status); Enter = Close | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): wording, padlock cards and versions correct; Disconnect works; Enter closed the window and stayed connected |
| A20 | Double-click a padlock | Acts once (the second click is ignored) | **FAIL then PASS** 2026-10-26: 0.86 s between clicks beat the 0.7 s window; with 1.5 s, a double-click on Ask to Keep acted once (no box) and rapid Admin clicks logged 'second click ... ignored' |
| A22 | `autocad_batch_draw` with the plug-in connected, then F2 | Only `Command:` prompts and `Heron: Batch Draw Geometry. Done in ...`; no LISP text, no coordinates | **PASS** 2026-10-26, AutoCAD 2027 (26.0s): 41 objects in 0.16-0.19 s (was 1.4 s over COM), history clean after two fixes (polyline list, helper name) |
| A21 | `autocad_batch_draw` with SECURELOAD on (default) | No security box | **FAIL then PASS** 2026-10-26, AutoCAD 2027 (26.0s): the old .lsp in %TEMP% raised 'Unsigned Executable File'; after D-21, 40 circles + a 150-point polyline drew in 1.4 s with no box. Command history fills with the LISP text (ROADMAP) |
| A24 | `autocad_add_label`, 13 labels, shape angled, on the roof pipe-support detail | Real LEADERs with arrows under MTEXT, on the text's layer | **FAIL then PASS** 2026-10-26: first drawn as splines without arrows (leader type 1); type 2 gives straight leaders with arrows under the text |
| A25 | `autocad_make_block` on a detail's parts, then insert and mirror copies | Parts become named blocks in place; copies insert; mirror makes the opposite hand | **PASS** 2026-10-26: roof pipe-support detail redrawn with 18 named blocks (anchor plan block x4, gussets mirrored), right-aligned label column, plan under elevation |
| A26 | `autocad_count_blocks` and `autocad_total_length` on valves, nuts, pipe lines, a room and a circle | Counts by name, layer and property values; lengths per layer; area only for closed shapes | **PASS** 2026-10-26 after one fix: an open polyline had reported an area (COM gives one), now closed shapes only |
| A27 | `autocad_get_dynamic_properties` / `autocad_set_dynamic_properties` on the sample "Hex Nut - Metric" | Sizes M3-M14 listed; "m6" sets M6 and the nut redraws; read-only and unknown names reported, not fatal | **PASS** 2026-10-26: count by properties then split M10 / M6 |
| A28 | `autocad_insert_block` with a C:/ forward-slash .dwg path; `autocad_list_blocks` after a dynamic nut is changed to M6 | File inserts; nut still counted 2, marked dynamic, no blank names | **PASS** 2026-10-26 |
| A29 | Every Lee Mac study tool on a test layout: import blocks from a closed DWG, place along, place from CSV, number tags, set attributes, count / total / polyline info / connected, segment and field labels, count / clean / find-replace / align text, break at block, double offset, overlapping dims, layouts | Results match hand checks | **PASS** 2026-10-26 after one fix (total length counted a leader). The field label updated itself from 22.00 m to 18.31 m after the break; the ellipse measured 9688.4 = its perimeter |
| A30 | `autocad_batch_labels`, a column of about 15 labels with `arrow_scale`, then one Ctrl+Z | All labels in one call, arrows at the given scale, `crossing` empty for a tidy column; one Ctrl+Z removes them all | **PASS** 2026-10-27, AutoCAD 2027 (26.0s): 15 labels (h 62.5, layer A30-ANNO) in one call, `arrow_scale` 25.0, `crossing` empty; arrows plot 2.5 x 25 and every leader ends under its text; a batch with label 1 missing its arrow returned `Error: label 1: 'arrow' must be [x, y].` and the count stayed 46; a second 15-label column, then one U, went 76 -> 46 objects, the first column and the pole kept. Note: a U pressed after other Heron calls (list, variable, preview) removed nothing, so those calls look like undo steps of their own |
| A19 | Run a CCTV generator sheet (`python generators/cctv_run.py png 102`) with Changes on | Draws and plots as before the folder move | **PASS** 2026-10-26: CCTV_Package.dwg (23,303 objects) opened, sheet 102 plotted to PNG correctly. Found: generators started their server without the user's environment; now passed through |
| A31 | Build and install the plug-in. Draw a 15-label column with `autocad_batch_labels`; then ask Claude to run `autocad_list_entities`, `autocad_get_variable` (DIMSCALE) and `autocad_preview`; then type U once in AutoCAD | The one U removes the whole label column (object count back to before the batch); the preview still shows the drawing and the page setup is unchanged; the Heron log has `undo paused for a read` and `undo resumed (end)` for each read; a second U undoes the step before the batch, not a read | NOT RUN |

## Group D - Sheets, coordinates and shop drawings (AutoCAD 2027, this PC)

The 14 tools added on 2026-10-26 ([09](09-sheets-and-coordinates.md)). Their arithmetic and their
planning are covered by the offline suites (`tests/test_coords.py`, `test_sheets.py`,
`test_settings.py`, `test_convert.py`, `test_sequence.py`); **everything COM touches is NOT RUN.**
Nothing below may be called working until its row says PASS with a date and a version.

**Set-up:** a scratch drawing in millimetres, Changes on, one piece of geometry in model space.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| D1 | Set a UCS by hand in AutoCAD (`UCS` > 3 point, turned about 23 degrees), then `autocad_status` | Reports `ucs.rotated` true, the rotation in degrees, and a `ucs_advice` sentence | NOT RUN |
| D2 | `autocad_get_ucs` with that UCS set | Origin, axes and rotation match what AutoCAD's `UCSORG` / `UCSXDIR` show; `saved` lists any named UCS | NOT RUN |
| D3 | `autocad_convert_points(points=[[100,0]], into="world")`, then draw a line to that world point | The line lands where 100,0 reads on the modeller's own screen | NOT RUN |
| D4 | `autocad_batch_draw(coords="ucs")` with a rectangle on that turned UCS | The rectangle is square to the UCS grid, not to the world; the drawing's UCS is unchanged | NOT RUN |
| D5 | `autocad_set_ucs(mode="world")`, then `mode="3point"`, then `mode="named"` back | The UCS icon moves and turns each time; one Ctrl+Z per call; `HERON-UCS` is reused, not duplicated | NOT RUN |
| D6 | `autocad_set_ucs(mode="entity")` on a rotated block, and on a block on a tilted plane | Lines up with the block; the tilted one is refused in plain words, not guessed | NOT RUN |
| D7 | Tilt the UCS out of the XY plane, then `autocad_batch_draw(coords="ucs")` | Refused, naming `autocad_convert_points`; nothing drawn | NOT RUN |
| D8 | `autocad_create_layout(name="D-101", paper_size="A1", plot_style_table="monochrome.ctb")` | New tab; Page Setup shows A1, DWG To PDF, monochrome; the returned `sheet` frame matches what PAGESETUP shows | **FAIL** 2026-10-28, AutoCAD 2027 (26.0s): five A1 tabs AC-101..105 were made with DWG To PDF and ISO full bleed A1, but every call answered `Outcome unknown: AutoCAD went busy` (also with `activate=false`); `plot_style_table` not tried (no monochrome.ctb). Cause not found |
| D9 | `autocad_create_layout(copy_from="D-101")` | The copy carries the page setup | NOT RUN |
| D10 | `autocad_page_setup(all_layouts=true, paper_size="A1", plotter="DWG To PDF.pc3", scale="1:1")` | Every tab changes; only the options passed are different afterwards | NOT RUN |
| D11 | `autocad_page_setup` with a plotter and a sheet size AutoCAD does not have | Named in the error, with the sizes that plotter does offer; the sheet is unchanged | NOT RUN |
| D12 | `autocad_place_title_block` with a real A1 title block, `all_layouts=true`, `per_layout_attributes` | One per sheet, bottom-right inside the ISO frame, right attributes per sheet; `replace_existing` does not stack a second | **PASS** 2026-10-28, AutoCAD 2027 (26.0s), with `layouts=[5 sheets]` (not `all_layouts`) and `anchor="paper"`: one title block per sheet at 831,10, all 9 attributes set per sheet, none missing. `replace_existing` not tried |
| D13 | `autocad_add_viewport(scale="1:100", view_name=...)` | Viewport fills the frame clear of the title block; **measure a known 10 m wall on the plot: 100 mm**; the viewport is locked | NOT RUN |
| D14 | `autocad_add_viewport` with no `scale` and a window | The reported scale is a standard one, the area fits, and the measurement matches that scale | NOT RUN |
| D15 | `autocad_add_viewport(align_to_ucs=true)` on the 23 degree UCS | The plan reads upright on the sheet; nothing falls outside the frame; the reported twist matches. **If it comes out turned the wrong way, the sign of the twist in `_aim` (sheets.py) is inverted — flip it and re-run.** The twist follows VIEWTWIST, which is +23 for a plan view of a UCS turned +23, but that has only been reasoned, not measured | NOT RUN |
| D16 | `autocad_add_viewport(paper_centre=..., paper_width=..., paper_height=...)` | The viewport is where those numbers say, in paper units | **PASS** 2026-10-28, AutoCAD 2027 (26.0s): 12 viewports at 1:50, 1:20, 1:10, 1:2 and 1:1; each `paper_rect` matched the centre and size asked and the plotted sheets showed them there, locked |
| D17 | After D13, zoom inside the viewport | Refused / no change: the lock held and the scale is still true | NOT RUN |
| D18 | `autocad_save_view` from a window, then `autocad_list_views` | The corners come back the same; `zoom_to` showed the area | NOT RUN |
| D19 | `autocad_export(area="view", view_name=...)` then `autocad_add_viewport(view_name=...)` | The PDF and the viewport show the **same** area | NOT RUN |
| D20 | `autocad_export(area="layout", scale="1:1")` on the D-101 sheet | The PDF is the sheet, title block and all, at full size; the layout's page setup is put back | **FAIL then fixed, re-run NOT RUN** 2026-10-28, AutoCAD 2027 (26.0s): `Outcome unknown: AutoCAD went busy`, no PDF. Two causes found by hand: setting `CenterPlot` on a layout plot raises, and choosing the plotter drops an A1 layout to ANSI A. `_plot_pdf` now skips `CenterPlot` for `area="layout"` and keeps the layout's own sheet when no `paper_size` is given |
| D21 | `autocad_drawing_setup(units="millimeters", scale="1:50", paper_text_height=2.5, osnaps=[...])` with `dry_run=true`, then false | The dry run writes nothing; the real run sets INSUNITS, DIMSCALE 50, LTSCALE 50, CANNOSCALE 1:50, TEXTSIZE 125, OSMODE; each `from`/`to` matches what SETVAR reports | NOT RUN |
| D22 | `autocad_drawing_setup` on a drawing where one variable is read-only for that release | That one is in `failed`; the rest still land | NOT RUN |
| D23 | `autocad_create_styles` with a text style and a dim style that has a `text_style` and a `precision`, then dimension something | The dim uses the new style at the right size; no notes on the style; **the drawing's own DIM variables are back where they were** (check DIMSCALE, DIMTXT, DIMTXSTY and DIMDEC with SETVAR). On 2026-10-28 a dim style with `"text_style": "ROMANS"` failed outright (`could not convert string to float: 'S'`); fixed, re-run NOT RUN | NOT RUN |
| D24 | `autocad_remap_layers(preset="ifc", dry_run=true)` on a real IFC or Revit export | `counts` and `by_rule` match a hand count of 3 sampled layers; nothing changed | NOT RUN |
| D25 | The same with `dry_run=false, set_bylayer=true` | Objects moved, the layers exist with the right colours, the drawing now plots in those colours; a locked layer appears in `failed` and the rest still land | NOT RUN |
| D26 | `autocad_tidy_entities(flatten_z=0, off_layer_0=..., dry_run=false)` on that import | Z is 0 throughout (check with LIST), layer 0 is empty of geometry, the plan now hatches and trims | NOT RUN |
| D27 | `autocad_sequence` of layout + title block + viewport | All three land in order; each step's own answer comes back; Ctrl+Z backs them out one at a time | NOT RUN |
| D28 | `autocad_sequence` with a bad argument in step 3 | Refused before step 1 runs; **the drawing is untouched** | NOT RUN |
| D29 | `autocad_sequence` with a step that fails at run time (a locked layer) | Steps 1-2 are in the drawing, that step reports the refusal, the rest are skipped, and the hint names the step | NOT RUN |
| D30 | `autocad_sequence` containing `autocad_save_drawing`, and one containing `autocad_run_lisp` | Both refused, naming the level; nothing ran. **This is the padlock ceiling (D-29) and must be re-run whenever a tool is added** | NOT RUN |
| D31 | After the whole set, `autocad_preview` and `autocad_check_standards` | The sheet looks right and the standard passes | NOT RUN |
| D32 | `autocad_drawing_setup(scale="1:10")`, then `autocad_drawing_setup(scale=10)` | The first sets CANNOSCALE 1:10 and DIMSCALE 10 with nothing in `failed`; the second is **refused**, asking for '1:10' or '10:1', and DIMSCALE is still 10. On 2026-10-28 both failed with `could not convert string to float: ':'`; fixed, re-run NOT RUN | NOT RUN |
| D33 | With a sheet tab active (after creating layouts and a Save As), `autocad_status`, then `autocad_add_table(space="paper")` | Status answers with `active_space: "paper"`; the table lands on the sheet. **FAIL** 2026-10-28, AutoCAD 2027 (26.0s): both raised a bare `Exception occurred`; status worked again once the Model tab was clicked, which left the gate blocking every tool until then. Common to both: `doc.PaperSpace` with a layout active. Not reproduced or fixed | NOT RUN |

## Group E - Geometry, annotation and 3D (AutoCAD 2027, this PC)

The 12 tools added on 2026-10-26 ([10](10-geometry-annotation-3d.md)). The
geometry and the layout arithmetic are covered offline (`tests/test_shapes.py`,
`test_dimension_run.py`, `test_annotate.py`, `test_solids.py` - 400 tests);
**every COM call below is NOT RUN.** Four of these methods were matched to
Autodesk's reference but have never been called from this server, and they are
marked.

**Set-up:** a scratch drawing in millimetres, Changes on, DIMSCALE set with
`autocad_drawing_setup(scale="1:10")`.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| E1 | `autocad_make_shape(shape="slot", settings={"length":120,"width":40})` then LIST it | **One** LWPOLYLINE, not a pile of arcs; measure it: 120 long, 40 wide, round both ends | NOT RUN |
| E2 | `shape="rounded_rectangle"` 2400 x 1200 r50 | One polyline, overall size exactly 2400 x 1200, corners truly tangent | NOT RUN |
| E3 | `shape="flange"` 200 OD, 8 holes, 160 PCD, bore 100, with `centreline_layer` | 11 circles; every hole centre 80 from the middle; the pitch circle on its own layer | NOT RUN |
| E4 | `shape="cone_development"` 200 to 100 over 150 | **Measure the two arcs.** Outer must be 628.3 (pi x 200), inner 314.2 (pi x 100). This is the one row that proves a flat pattern | NOT RUN |
| E5 | `shape="stair"` 14 risers at 175, going 280, both `view="section"` and `view="plan"` | Section climbs to 3920 x 2450; plan is 3920 x 1200 with 13 tread lines | NOT RUN |
| E6 | `shape="steel_section"` for i, c, l, t, shs, chs | Each outline is the right depth and width, corners square | NOT RUN |
| E7 | `shape="detail_bubble"` with a sheet, and `shape="revision_tag"` | **The text sits centred on its point, both ways** - this is the DXF 72/73/11 justification working | NOT RUN |
| E8 | `shape="scale_bar"` scale 1:50, length 100 | Bar 100 long on the paper; labels read 0 to 5000 | NOT RUN |
| E9 | `autocad_make_shape(..., coords="ucs")` on a 23 degree UCS | The shape comes out square to the UCS grid, not to the world | NOT RUN |
| E10 | `autocad_make_shape(..., dry_run=true)` | Operations come back, nothing is drawn | NOT RUN |
| E11 | `autocad_dimension_run` chain along 4 grid points, offset 500, `include_overall=true` | 4 dimensions; the three gaps on one line, the overall above; **each "measured" equals its "expected"** | NOT RUN |
| E12 | The same as `mode="baseline"` | Each dimension back to the first point, each on its own line stepped 500 clear | NOT RUN |
| E13 | `mode="ordinate"` with a datum, first with the UCS origin elsewhere, then after `autocad_set_ucs(mode="origin", origin=<datum>)` | **AddDimOrdinate: never called from here before.** The first is **refused** before drawing, naming the `autocad_set_ucs` call; the second gives ordinate dimensions with leaders, each `measured` equal to its `expected` (the distance from the datum). AutoCAD measures ordinates from the UCS origin, so before 2026-10-28 a datum elsewhere drew wrong values; re-run NOT RUN | NOT RUN |
| E14 | `axis="aligned"` on a sloping run | The true length, text offset perpendicular to the run | NOT RUN |
| E15 | `autocad_add_centre_marks(layer_filter=..., extend=...)` | A cross on every circle, centre lines running past, all on the layer asked for; `min_radius` skips the small ones | NOT RUN |
| E16 | `autocad_add_multileader` with **three** arrow points | One MULTILEADER, three leader lines, one note. **AddLeader / AddLeaderLine: never called from here before** | NOT RUN |
| E17 | `autocad_add_multileader(block=...)` | The block is carried at the end of the leader | NOT RUN |
| E18 | `autocad_add_table` with a title, headers and 5 rows, `text_height` and `text_style` | A real TABLE object, editable, title and header rows filled, column widths as asked, text at the height asked on every row and nothing in `not_set`. **AddTable / SetText / SetColumnWidth: never called from here before.** On 2026-10-28 the height came back `not_set: TitleTextHeight, HeaderTextHeight, DataTextHeight` and the text was tiny; now `SetTextHeight` / `SetTextStyle` on all three row types, re-run NOT RUN. Also 2026-10-28 with `space="paper"` on a sheet tab: a bare `Exception occurred` before AddTable was reached (AddTable itself worked through LISP), see D33 | NOT RUN |
| E19 | `autocad_extract_attributes` then `autocad_add_table` with those rows | The schedule appears as a table with one row per block | NOT RUN |
| E20 | `autocad_add_revision_cloud(handle=...)` with a margin | One polyline round the object, arcs bulging **outward**, even size, no stub arc | NOT RUN |
| E21 | The same on a boundary traced clockwise | Arcs still bulge outward, not inward | NOT RUN |
| E22 | `autocad_add_solid` box 2400 x 1200 x 200 at the origin | **The base sits on z=0**, not z=-100. Check with LIST | NOT RUN |
| E23 | `autocad_add_solid` for wedge, cylinder, cone, sphere, torus | Each the right size, base on z=0 where it has one | NOT RUN |
| E24 | `autocad_extrude_profile` on a closed polyline, height 200 | A 3D solid; the intermediate REGION is **gone**; the original polyline is **still there** | NOT RUN |
| E25 | The same with a taper | The sides draw in as it rises | NOT RUN |
| E26 | `autocad_extrude_profile` with `revolve_angle=360` and an axis | A solid of revolution. **AddRevolvedSolid: never called from here before** | NOT RUN |
| E27 | `autocad_extrude_profile` on curves with a gap in them | Refused in plain words, naming what to check; nothing left behind | NOT RUN |
| E28 | `autocad_solid_boolean` subtract: 4 cylinders out of a plate | Holes through the plate; the cylinders gone; **volume_after is less than volume_before**. On 2026-10-28 every real solid was refused (`2E1 is a AcDb3dSolid, not a 3D solid`), and slice, clash check and `solids_only` materials had the same fault; fixed, re-run NOT RUN | NOT RUN |
| E29 | `autocad_solid_boolean` with a handle that is a line | Refused **before anything is consumed** - the other solids must all still be there | NOT RUN |
| E30 | `autocad_solid_boolean` subtract two solids that do not touch | The warning about the volume not changing appears | NOT RUN |
| E31 | `autocad_solid_properties` on that plate | Volume matches 2400x1200x200 less the holes; centroid sensible; bounding box right | NOT RUN |
| E32 | `autocad_draw_3d_path` with helix r100, 3 turns, rise 600 | One 3D polyline; starts at (100,0,0), ends at (100,0,600) | NOT RUN |
| E33 | `autocad_draw_3d_path` with points through a building | One 3D polyline following them | NOT RUN |
| E34 | `autocad_set_3d_view(direction="sw_iso", visual_style="hidden")` then `autocad_preview`; then `visual_style="realistic"` | The model is shown from the south-west with hidden lines, then shaded; nothing in `not_set`; AutoCAD not left at a prompt; **no padlock was needed**. On 2026-10-28 `realistic` came back `not_set: visual_style (Error setting system variable)`: VSCURRENT is a command, not a variable, and is now typed as one. Also try 'shaded with edges' and 'shades of gray': their options (`_E`, `_G`) are from the prompt's capitals, not from a run. Re-run NOT RUN | NOT RUN |
| E35 | `autocad_set_3d_view(direction="top", visual_style="2dwireframe")` | Back to plan and normal drafting | NOT RUN |
| E36 | `autocad_batch_draw` with `bulges` on a polyline and `align` on a text | The arc is part of the polyline; the text is justified. These two are what every shape depends on | NOT RUN |

## Group F - The rest of 3D: oval shapes, sweeps, slices, clashes, materials (AutoCAD 2027, this PC)

`tools/live_check.py --group F` measures most of these. Every COM call named here is one this
server has **never made**: `AddEllipticalCylinder`, `AddEllipticalCone`,
`AddExtrudedSolidAlongPath`, `SliceSolid`, `CheckInterference`, `Rotate3D`, `Mirror3D`, and the
`Material` property. Their signatures came from Autodesk's reference and community examples, not
from a run. `SectionSolid` is deliberately **not** built: no documented signature could be found.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| F1 | `autocad_add_solid(shape="elliptical_cylinder", length=400, width=200, height=2000)` | Bounding box measures 400 x 200 x 2000. **Length and width are overall sizes, not half axes** - if it comes out 800 x 400, drop the `/2.0` in `tools/solids.py`. Before 2026-10-28 there was no AutoCAD call for the oval shapes at all (they fell through to the torus and always failed); re-run NOT RUN | NOT RUN |
| F2 | The same with `shape="elliptical_cone"` | Base 400 x 200, coming to a point 2000 up | NOT RUN |
| F3 | `elliptical_cylinder` with length and width equal | Refused, telling you to use `cylinder` with a radius | NOT RUN |
| F4 | `autocad_extrude_profile(handles=[a 100 dia circle], path_handle=a 3000 long polyline)` | One solid following the route; volume about pi x 50^2 x 3000 | NOT RUN |
| F5 | `autocad_slice_solid(plane="horizontal", through=[0,0,100], keep="both")` on a 200 high box | Two solids; their volumes add up to the original | NOT RUN |
| F6 | The same with `keep="positive"` | One solid, half the volume; nothing else left behind | NOT RUN |
| F7 | `autocad_slice_solid(plane="normal", normal=[1,1,0])` | Cut on the diagonal, the plane facing where you said | NOT RUN |
| F8 | `autocad_slice_solid` on a line | Refused naming it as not a 3D solid; the line is untouched | NOT RUN |
| F9 | `autocad_check_interference` on a duct through a beam | `clashes: 1`, and the overlap volume matches the overlap you can measure | NOT RUN |
| F10 | The same on two solids that do not touch | `clear: true`, `clashes: 0` | NOT RUN |
| F11 | `autocad_check_interference(create_solids=false)` | **The entity count is unchanged.** AutoCAD builds the overlap to measure it; this must clean it up | NOT RUN |
| F12 | `autocad_check_interference(create_solids=true, layer="Z-CLASH")` | The overlaps are drawn on Z-CLASH and can be seen | NOT RUN |
| F13 | `autocad_check_interference(handles=[3 solids])` with no `against` | 3 pairs checked, not 6 or 9 | NOT RUN |
| F14 | `autocad_transform_3d(operation="move", displacement=[0,0,3500])` | Everything 3500 higher; bounding box min z up by 3500 | NOT RUN |
| F15 | `autocad_transform_3d(operation="rotate", axis_direction=[1,0,0], angle=90)` | Tipped about the X axis, not about Z | NOT RUN |
| F16 | `autocad_transform_3d(operation="mirror", plane_point=[0,0,2000], plane_normal=[0,0,1])` | A reflection above, original kept; `new_handles` has one entry | NOT RUN |
| F17 | `autocad_transform_3d(operation="array", levels=5, level_spacing=3600)` | 4 new copies; the top one 14400 up | NOT RUN |
| F18 | `autocad_list_materials` on a drawing with materials in it | Each name, and `in_use` counting the objects carrying it | NOT RUN |
| F19 | `autocad_apply_material(material="NoSuchThing")` | Refused, **listing the materials the drawing does have**, and saying the library cannot be reached from automation | NOT RUN |
| F20 | `autocad_apply_material(material="Steel", layer_filter=...)` then `autocad_set_3d_view(visual_style="realistic")` and `autocad_preview` | The solids look like steel in the picture | NOT RUN |
| F21 | `autocad_apply_material` on a line with `solids_only=true` | Skipped and reported, not silently applied | NOT RUN |
| F22 | `autocad_render` to a PNG, preset "Low", with Admin on | Either the file appears, or the result says the command line is waiting. **Rendering from a script is reported to drop objects - compare the image with a render done by hand before trusting it** | REMOVED 2026-11-21: `autocad_render` is gone ([D-87](DECISIONS.md), #158); nothing to run |
| F23 | `autocad_sequence` with a step naming `autocad_run_lisp` (it named `autocad_render` until that was removed, D-87) | Refused: Admin is above the sequence ceiling | NOT RUN |

## Group G - Splines, multilines, wipeouts, xrefs, pattern and linetype files (AutoCAD 2027, this PC)

The 7 tools added on 2026-10-28. Their arithmetic and the text they send are tested offline
(`tests/test_drafting.py`, `test_xrefs.py`, `test_patterns.py`); **every COM call and typed command
below is NOT RUN**. By hand: Changes on, and Publish for G10-G12.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| G1 | `autocad_draw_spline(points=[[0,0],[1000,500],[2000,0],[3000,800]])`, then LIST | One SPLINE through all four points (fit points, not control points); its ends leave along the first and last segments | NOT RUN |
| G2 | The same with `closed=true`, and one with `coords="ucs"` on a 23 degree UCS | The closed one is closed smoothly (Closed2 accepted, nothing in `not_set`); the UCS one follows the UCS grid | NOT RUN |
| G3 | `autocad_draw_multiline(points=[[0,0],[5000,0],[5000,3000]], scale=200)` | One MLINE, 200 wide, centred on the points; the drawing's CMLSTYLE unchanged afterwards | NOT RUN |
| G4 | The same with `justification="top"`, then `"bottom"`, and `style=` a style the drawing lacks | The lines run to one side, then the other; the missing style is refused naming MLSTYLE, nothing drawn | NOT RUN |
| G5 | `autocad_add_wipeout(points=[[0,0],[1200,0],[1200,450],[0,450]])` over a hatch, with a UCS set and running snaps on; then once from inside an active layout viewport | A WIPEOUT exactly there in world coordinates (not snapped, not shifted by the UCS); the hatch hidden behind it; AutoCAD back at `Command:`. From the viewport it is found in model space, not reported as failed | NOT RUN |
| G6 | `autocad_add_wipeout(boundary_handle=<closed rectangle>, erase_boundary=true, frames="show_no_plot")` | The wipeout takes the rectangle's place; WIPEOUTFRAME reads 2; frames on screen, not on a plot | NOT RUN |
| G7 | `autocad_attach_xref(path=<a .dwg>, insertion=[0,0])`, then `overlay=true` with another name | Both appear in XREF palette as Attach and Overlay, at the origin, named after the file | NOT RUN |
| G8 | Change the referenced file, then `autocad_manage_xref(action="reload")`; then `unload` | The change shows after reload; unload hides it and the palette says Unloaded | NOT RUN |
| G9 | `autocad_manage_xref(action="bind")` without, then with `confirm=true`; another with `action="detach"` | Without confirm nothing changes; bind turns it into a block with NAME$0$ layers; detach removes it and every instance | NOT RUN |
| G10 | `autocad_create_hatch_pattern(name="HX-45", spacing=3)`, then `autocad_add_hatch(pattern="HX-45")` | HX-45.pat in Heron's support folder, the folder once in OPTIONS > Files > Support File Search Path, and the hatch drawn with it (it falls back to the custom pattern type). Note whether AutoCAD refuses the unknown name at AddHatch itself (then the fallback works) or only later at Evaluate (then it does not, and the fallback needs moving) | NOT RUN |
| G11 | `autocad_create_linetype(name="CHWS", text="CHWS")` with `autocad_drawing_setup(scale="1:50")` set, on a long line | ---- CHWS ---- along the line, text upright on it and clear of the dashes, the right size on a 1:50 plot. If the text crowds the dashes, re-run with `text_width` and note the value | NOT RUN |
| G12 | `autocad_create_linetype(name="DD-12", dashes=[12, -3, 0, -3])` | A dash-dot line, 12 dash, 3 gap, dot | NOT RUN |

## Group H - Plug-in operations: loft, solid edges and faces, thicken, super hatch (AutoCAD 2027, this PC)

The 8 tools added on 2026-10-29, done by the plug-in itself through the AutoCAD .NET API (D-40).
The bridge's rules (which job, which level, which operations), the edge and face words and the
tile grid are tested offline (`RunTests.cs`, `tests/test_plugin_tools.py`), and the add-in
**compiles** against AutoCAD 2021-2024, 2025-2026 and 2027; **every row below is NOT RUN**. First
install plug-in **1.2.0** (`tools/build_plugin.py`, close AutoCAD, `tools/install_plugin.py`). By
hand: Changes on. For H3-H8, a box from `autocad_add_solid(shape="box", length=1000, width=600,
height=400)`.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| H1 | With plug-in 1.1.0 still installed, `autocad_fillet_solid_edges(box, radius=50, edges="vertical")` | Refused: "needs Heron's plug-in 1.2.0 or newer ... Nothing was sent"; the box unchanged | NOT RUN |
| H2 | `autocad_list_solid_faces_and_edges(box)` | 6 faces, all `plane`, the top one centred at z=400 with normal [0,0,1]; 12 edges, all `line`, lengths 1000 / 600 / 400. Then one Ctrl+Z undoes the box, not a step the listing left | NOT RUN |
| H3 | `autocad_fillet_solid_edges(box, radius=50, edges="vertical")`, look in Conceptual | The four upright corners rounded, R50; `volume_after` below `volume_before`. **One Ctrl+Z** puts the sharp box back (the plug-in's transaction is one undo step) | NOT RUN |
| H4 | The same with `radius=5000` | Refused: "AutoCAD would not round ... Nothing was changed"; the box unchanged and no undo step added | NOT RUN |
| H5 | `autocad_chamfer_solid_edges(box, face="top", distance=20)` | The four top edges bevelled 20 x 20; the bottom ones sharp | NOT RUN |
| H6 | `autocad_shell_solid(box, thickness=10, remove_faces="top")` | An open-top box, walls and floor 10 thick inside the old outline; volume 1000x600x400 - 980x580x390 = 18,324,000 | NOT RUN |
| H7 | `autocad_press_pull_faces(box, faces="top", distance=150)` | The box 550 tall; volume up by 1000x600x150 = 90,000,000 | NOT RUN |
| H8 | `autocad_loft(sections=[a 600 x 400 rectangle at z=0, a 450 circle at z=500])` | One solid, a rectangle-to-round transition 500 long; both outlines still there | NOT RUN |
| H9 | `autocad_thicken_surface` on a 1000 x 1000 PLANESURF, `thickness=20`; then again with `both_sides=true` | A 20 thick solid (volume 20,000,000); the surface still there. With `both_sides`, write down whether it is 20 thick (split) or 40 (each side), and fix the tool's wording to match | NOT RUN |
| H10 | `autocad_super_hatch(boundary=<an L-shaped closed polyline with one arc corner>, block=<a 600 x 300 rectangle block>)` | One block reference (LIST: SUPERHATCH-1). Tiles show only inside the outline, following the arc; ERASE takes it all; **one Ctrl+Z** takes it away. XCLIPFRAME 1 shows the clip frame | NOT RUN |
| H11 | The same with `angle=45, origin=<the room centre>` | The grid and tiles turned 45 degrees, a tile's base point on the origin | NOT RUN |
| H12 | Ask to keep on: fillet the box, answer Discard; super hatch, answer Discard | The sharp box back; the hatch reference gone, and PURGE finds no SUPERHATCH block left | NOT RUN |
| H13 | Put the box on a locked layer, then fillet it | Refused: "on a locked layer ... Nothing was changed" | NOT RUN |

## Group I - From the ADN-DevTech study: xref tree, drawing report, multi-sheet PDF, busy command (AutoCAD 2027, this PC)

Added on 2026-11-04 ([D-41](DECISIONS.md), [11](11-adn-repos-study.md)). The logic is tested
offline (`tests/test_adn_tools.py`, `tests/test_memory_check.py`, `RunTests.cs`), and the add-in
**compiles** for all three AutoCAD builds; **every row below is NOT RUN**. I3-I6 need plug-in
**1.3.0** installed.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| I1 | `autocad_xref_tree` on a drawing with one xref that holds a nested xref, and one xref whose file was renamed | The nested one listed under its parent, both `loaded`; the renamed one `not found` and in `broken`. Matches the External References palette | NOT RUN |
| I2 | `autocad_drawing_report` on a consultant's drawing | Units, layer counts (off / frozen / locked), blocks, xrefs, styles, sheets with their paper, and model-space counts match LAYER, the palettes and QSELECT by hand | NOT RUN |
| I3 | Changes and Publish on; save; `autocad_publish_pdf(path=...)` on a drawing with 3 sheets, one never opened | One PDF, 3 pages in tab order, each with its own page setup; the never-opened sheet is not blank. BACKGROUNDPLOT reads as before | NOT RUN |
| I4 | Change something, do not save, then `autocad_publish_pdf` | Refused: "unsaved changes ... Save it first"; no PDF | NOT RUN |
| I5 | Publish off, then `autocad_publish_pdf` | Refused by the Publish padlock; no PDF | NOT RUN |
| I6 | Start HATCH and leave its dialog open; from the chat call `autocad_super_hatch` | After 30 s: "it is still in the HATCH command. Finish it or press Esc" | NOT RUN |
| I7 | `tools/memory_check.py --rounds 100` with Heron connected | PASS: the last Private Bytes reading within 10 % of the first. A FAIL is a leak to chase | NOT RUN |
| I8 | `autocad_publish_pdf` and `autocad_drawing_report` on AutoCAD 2025/2026 and 2021-2024 | As I2-I3 | NO MACHINE |

## Group J - Fixes from the cassette and bedroom models: banner, fillet, open commands, layout, preview (AutoCAD 2027, this PC)

Added on 2026-11-05. The rules are tested offline (`BannerJobsTests.cs`, `test_run_lisp_guard.py`,
`test_create_layout_cleanup.py`, the preview tests) and the add-in
**compiles** for all three AutoCAD builds; **every row below is NOT RUN**. Needs the rebuilt
plug-in installed.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| J1 | Banner on. `autocad_run_lisp('(command "_.CAMERA")')` so AutoCAD is left at the camera prompt; when the call fails, press Esc. Then `autocad_zoom(mode="extents")` | The zoom's card shows DONE and **closes about 1.4 s later**; it does not stay on screen | PASS 2026-11-05, AutoCAD 2027: the zoom's card closed by itself after DONE (user's eye). The CAMERA prompt was answered by hand, not Esc; old server code, which J1 does not depend on |
| J2 | Ten quick reads in a row (`autocad_status` x10) | Each card closes after its DONE; no card is left showing at the end | PASS 2026-11-05, AutoCAD 2027: 10 x autocad_status all answered; no card left showing (user's eye) |
| J3 | `autocad_add_solid` a 500 x 700 x 160 box, then `autocad_fillet_solid_edges(box, radius=60, edges="all")`; also `autocad_list_solid_faces_and_edges(box)` | The box rounded on every edge, volume down; the listing gives 6 faces and 12 edges. No "BoundaryRepresentation.Exception" | PASS 2026-11-05, AutoCAD 2027: box 56,000,000 -> 52,086,512.24 after R60 on all 12 edges (formula gives 52,086,512.3); listing 6 faces / 12 edges before, 26 / 48 after; no BoundaryRepresentation error |
| J4 | `autocad_run_lisp('(command "_.CAMERA" "0,0,0" "1,1,1")')` with running snaps on | Returns at once with `cancelled_command: "CAMERA"`; AutoCAD is free (no prompt left), the next call works, OSMODE is as it was | NOT RUN |
| J5 | `autocad_create_layout(name="J5", paper_size="A3")` on this PC | The sheet made with the PDF plotter; if it fails, the error says the layout was not kept and the Layout tabs show no J5 | NOT RUN |
| J6 | On a layout with PlotRotation 90, `autocad_preview` | The picture upright, as on screen; Page Setup still shows 90 afterwards | NOT RUN |

## Group K - Lights, materials and a saved 3D view for a render (AutoCAD 2027, this PC)

Added on 2026-11-05 ([D-42](DECISIONS.md)), for the two-storey villa model. The logic is tested
offline (`tests/test_render_setup.py`, `tests/test_make_block.py`, `RunTests.cs`), and the add-in
**compiles** for all three AutoCAD builds; **every row below is NOT RUN**. K1-K12 need plug-in
**1.4.0** installed. Set LIGHTINGUNITS to 2 first (K4 checks the warning when it is not).

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| K1 | `autocad_add_light(position=[0,0,3000], intensity=1500)` | One point light; LIST shows AcDbLight named Pointlight1; Properties: photometric intensity 1500 cd, lamp colour 3000 K, on, shadows on; one Ctrl+Z removes it | NOT RUN |
| K2 | `autocad_add_light(kind='spot', position=[0,0,3000], intensity=800, intensity_unit='lm', hotspot=40, falloff=60)` | A targeted spot pointing straight down, target just below it; Properties: 800 lm (flux), hotspot **40**, falloff **60**. If it shows 20 / 30 or 80 / 120, the API reads the angle as half or double the cone: record it, the tool needs changing | NOT RUN |
| K3 | `autocad_add_light(kind='distant', position=[0,0,10000], target=[5000,0,0], intensity=50000)` | Properties: 50000 lux; in a realistic view with DEFAULTLIGHTING 0 the faces turned towards +Z and +X are lit (the direction is light travel, from position to target) | NOT RUN |
| K4 | LIGHTINGUNITS 0, then add any light | The light is made, and the reply's `warning` names LIGHTINGUNITS 0 and says to set it to 2 | NOT RUN |
| K5 | `autocad_add_light(kind='web', web_file=<a maker's .ies>, ...)` | Properties: Photometric web shows that file; the web glyph is drawn | NOT RUN |
| K6 | `autocad_add_light(rgb=[0,120,255], ...)` | Properties: lamp colour 6500 K, filter colour 0,120,255; resulting colour blue | NOT RUN |
| K7 | Draw a downlight can, add a spot under it, `autocad_make_block` with both handles; insert 3 more copies; render | The block holds the light (BEDIT shows it); all 4 inserts light the floor in the render; the Lights in Model palette lists them | NOT RUN |
| K8 | `autocad_create_material(name='Laterite', diffuse_rgb=[178,84,52], glossiness=0.1)`, then `autocad_apply_material(material='Laterite', handles=[<a box>])` | The Materials Browser shows Laterite; apply finds it straight away; the box is laterite red in a realistic view | NOT RUN |
| K9 | `autocad_create_material(name='Teak', texture=<a .jpg>)`, apply, realistic view | The wood image shows on the faces (its size is AutoCAD's default mapping; MATERIALMAP adjusts it) | NOT RUN |
| K10 | `autocad_create_material(name='Glass', transparency=0.9, refraction_index=1.5, reflectivity=0.1)`, apply to a pane, render | The pane is see-through in the render | NOT RUN |
| K11 | `autocad_create_material(name='LED Strip', luminance=2000, glow_kelvin=3000)`, apply to a thin box in a cove, night render (sun off) | The strip glows warm white; note whether the glow takes the diffuse colour as D-42 expects | NOT RUN |
| K12 | `autocad_create_material` with a name already there, then again with `replace=true` | Refused the first time; the second changes it, and objects already using it change too | NOT RUN |
| K13 | `autocad_set_3d_view(view='southwest')`, orbit a little, then `autocad_save_view(name='LIVING-3D', from_screen=true)`; zoom away; VIEW, restore LIVING-3D | The 3D angle comes back exactly; `autocad_list_views` shows it with `plan: false` | NOT RUN |
| K14 | K1-K13 on AutoCAD 2025/2026 and 2021-2024 | As K1-K13 | NO MACHINE |
| K16 | Plug-in **1.4.2**. `autocad_create_material(name='Plaster', texture=<library plaster .jpg>, texture_size=2000)`, apply to a box, then `(name='Plaster', diffuse_rgb=[238,232,220], replace=true)` | The box turns plain ivory in the realistic view; the result's `set` lists `texture cleared`. Before 1.4.2 the image stayed and the colour never showed (2026-11-09) | NOT RUN |
| K15 | Plug-in **1.4.1**, a mm drawing. `autocad_create_material(name='Walnut', texture=<Autodesk library walnut .jpg>, texture_size=1000)` and `(name='Marble', texture=<library marble>, texture_size=2000)`; apply each to a box 2000 x 2000 x 2000; realistic view, then a render. Then `(name='Tile', texture=<a tile .jpg>, bump=<same>, texture_size=600, texture_height=300, replace=true)` on the same box | Walnut grain and marble veining show, not flat colour; the result has `texture_size` and no warning; `(dictsearch (cdr (assoc -1 (dictsearch (namedobjdict) "ACAD_MATERIAL"))) "Walnut")` shows the diffuse group-43 diagonal 0.001 / 0.0005 and 1 at the end, as the hand fix of 2026-11-08. For the tile: 600 across, 300 up the side faces; record which way the X-facing faces lay it. Made without `texture_size`, the result warns "texture size not set" | NOT RUN |

## Group L - Ribbon, Settings window, icons and brand colours (AutoCAD 2027, this PC)

Added on 2026-11-08 ([D-43](DECISIONS.md), [D-44](DECISIONS.md)). The add-in **compiles** for all
three AutoCAD builds and the colours are checked offline (`tests/test_brand_and_installer.py`);
**every row below is NOT RUN**.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| L1 | Start AutoCAD, open the Heron tab | Two buttons: **Heron** (black heron) and **Settings** (gear); no padlock buttons | PASS 2026-11-08, AutoCAD 2027 (#20 build): two buttons, Heron and Settings, no padlock buttons (user's eye) |
| L2 | Press **Heron** | The heron turns orange; the arrow shows Bridge Status | PASS 2026-11-08, AutoCAD 2027 (#20 build): the heron turned orange when connected (user's eye) |
| L3 | Press **Settings** | One Mist window: Changes, Admin, Publish, Ask to Keep, each with its padlock picture, one line and OFF | PASS 2026-11-08, AutoCAD 2027, #20 build (then a light window): the four rows with padlock pictures and buttons (user's eye). The dark Heron window from #21 is NOT RUN |
| L4 | In Settings press Changes' OFF, answer Yes | The question comes first; then Changes shows a red ON and the open padlock; the window stays open | NOT RUN |
| L5 | `autocad_draw_line` while Changes is on, then while it is off | On: the banner shows the orange CHANGING chip, then green DONE. Off: the refusal says "press Settings on the Heron tab" | NOT RUN |
| L6 | Bridge Status and the Keep question (Ask to Keep on) | Dark Heron window: orange heron and "Heron  Bridge Status" in the header, the lamp, the Changes card, THIS SESSION, Copy details; the Keep choices as dark cards, the focused one with an orange border | NOT RUN |
| L7 | `autocad_status`, then `autocad_draw_line` with Changes on | The glass card slides down: "Heron AI · Reading" then "Heron AI · Changing", orange, with the sheen, the turning rim and the time counting; then "Heron AI · Done" in green; it slides away about 1.4 s later | NOT RUN |
| L8 | In Settings press Admin's OFF while Changes is off | The Heron switch window: the padlock, "Turn Admin on?", the warning lines (including "Changes is off - Admin needs it on too"), Leave off and an amber Turn on; Esc and Leave off change nothing | NOT RUN |
| L9 | With a chat holding AutoCAD, Heron arrow -> Free this AutoCAD | The command line says it is free; a second chat is then accepted at once | NOT RUN |
| L10 | Hover over Heron, Bridge Status, Free this AutoCAD and Settings | One short sentence each | NOT RUN |
| L11 | Press the top half of **Heron** to connect, again to disconnect; then open Bridge Status from the arrow and close it | Each press connects or disconnects; after Bridge Status the button still shows the heron and still connects | PASS 2026-11-08, AutoCAD 2027, fix build f32d68b: the top half of Heron connects (user's eye). The #21 build had failed it: the top half did nothing |
| L12 | While connected, pick **Free this AutoCAD** from the Heron arrow, then **Bridge Status** and close it | After each, the big button shows the orange heron again within a moment, still connected; no need to press Heron | NOT RUN |

## Group M - Ideas from Heron AI for Revit, batch 1 (AutoCAD 2027, this PC)

Added on 2026-11-15 ([D-47](DECISIONS.md), [D-48](DECISIONS.md)). Built and tested offline
(`tests/test_publish_guard.py`, `tests/test_diagnose.py`, `tests/test_progress.py`,
`PublishGuardTests.cs`); **every row below is NOT RUN**. Install plug-in 1.5.0 first.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| M1 | Draw three circles; ask "show me the circles" (`autocad_show` with their handles), Changes OFF | The three are selected with grips and the view zooms to them; nothing else changes and one Ctrl+Z does not undo a drawing change | NOT RUN |
| M2 | Same circles, `isolate=true`; then `end_isolation=true` | Only the circles stay visible, then everything comes back; saving and reopening shows everything | NOT RUN |
| M3 | Admin ON, Publish OFF: `autocad_send_command("_QSAVE
")` and `autocad_run_lisp('(command "_.QSAVE")')` | Both refused at once with "use autocad_save_drawing"; the file's time on disk is unchanged | NOT RUN |
| M4 | Admin ON, Publish OFF: type `(defun c:HSV () (command "_.QSAVE"))` yourself at the command line, then `autocad_send_command("HSV
")` | The command line says "Heron stopped QSAVE"; the file's time on disk is unchanged | NOT RUN |
| M5 | Right after M4, press Ctrl+S yourself (wait 5 s) | The drawing saves as normal | NOT RUN |
| M6 | Publish OFF: `autocad_preview` | The picture comes back as before: the veto never touches a preview | NOT RUN |
| M7 | `autocad_publish_pdf` of a 10-sheet drawing in Claude Code | "Still working: ..." notes while it runs, if Claude Code shows progress (say if it does not) | NOT RUN |
| M8 | Read `autocad://diagnose` with AutoCAD closed, then open and connected | Closed: WARNING "press the Heron button"; connected: HEALTHY with AutoCAD's version and plug-in 1.5.0 | NOT RUN |

## Group N - Ideas from Heron AI for Revit, batch 2 (AutoCAD 2027, this PC)

Added on 2026-11-15 ([D-49](DECISIONS.md), [D-50](DECISIONS.md), [D-51](DECISIONS.md)). Built and
tested offline (`tests/test_sessions.py`, `tests/test_gate.py`, `JobChangesTests.cs`); **every row
below is NOT RUN**. Plug-in 1.5.0 installed.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| N1 | Open AutoCAD 2027 and a second AutoCAD (any version), each with a saved drawing; press Heron in BOTH; ask for `autocad_status` | Refused: "2 AutoCADs are connected to Heron", both listed by version and process; nothing drawn anywhere | NOT RUN |
| N2 | `autocad_use_autocad(pid=<the second one>)`, then `autocad_status`, then draw a line | Status and the line are in the SECOND AutoCAD, even though COM's first choice is the other one | NOT RUN |
| N3 | Close the AutoCAD picked in N2, then ask to draw a line | Refused with "never moves on"; nothing is drawn in the AutoCAD still open | NOT RUN |
| N4 | Ask to Keep OFF: `autocad_send_command("_ERASE\n_L\n\n")` on a drawing with a line | The Heron box "Heron erased 1 object." appears; press Enter: the line is back. The result has `heron_changes` erased 1 and a note that it was brought back | NOT RUN |
| N5 | Same, but choose "Keep them erased" | The line stays erased; the note says the modeller kept it erased | NOT RUN |
| N6 | Ask to Keep ON: `autocad_delete_entities(..., confirm=true)` | Only Keep or Discard is asked (not the erase box too) | NOT RUN |
| N7 | Start a 20-step `autocad_sequence`; pick **Stop Heron now** after the first steps land | The sequence ends at the next step with "HERONSTOP" in its hint; later steps not drawn; the next call is refused until HERONSTOP is typed again | NOT RUN |
| N8 | `autocad_batch_draw` of 2,000 objects; HERONSTOP while it draws | What AutoCAD had queued may finish (say how much); no second copy is typed over COM; the next call is refused | NOT RUN |

## Group O - Ideas from Heron AI for Revit, batch 3 (AutoCAD 2027, this PC)

Added on 2026-11-15 ([D-52](DECISIONS.md), [D-53](DECISIONS.md), [D-54](DECISIONS.md)). Built and
tested offline (`tests/test_memory_and_checks.py`, `ChangedBeforeTests`); **every row below is NOT
RUN**. Plug-in 1.5.0 installed.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| O1 | In a saved drawing, tell the chat "the scale is 1:50 for this job"; start a NEW chat and call `autocad_status` | The new chat's status has `project_notes` scale 1:50 and it does not ask the scale | NOT RUN |
| O2 | Open a drawing in ANOTHER folder; `autocad_status` | No `project_notes` from the first folder | NOT RUN |
| O3 | `autocad_checklist(action="run", name="before issue")` on a real sheet | Each line PASS / FAIL / NO DATA / NOT RUN ([D-64](DECISIONS.md)); FAIL lines name handles; `autocad_show` of them selects the right objects | NOT RUN |
| O4 | Save a list with your own sentences (title block pattern, text heights); run it | Your sentences come back as the labels; a title block with an empty attribute is named | NOT RUN |
| O5 | Ask to Keep OFF: draw a circle with Heron, then "undo what you just did" (`autocad_undo_last`) | The circle is gone; nothing else changed | NOT RUN |
| O6 | Draw a circle with Heron, then draw a line yourself, then `autocad_undo_last` | Refused: "the drawing changed after Heron's last change"; both stay | NOT RUN |
| O7 | Ask to Keep ON (Keep): draw with Heron, `autocad_zoom`, then `autocad_undo_last` | Undone exactly back to the mark: the drawing is as before Heron's job | NOT RUN |

## Group P - Ideas from Heron AI for Revit, batch 4 (this PC)

Added on 2026-11-15 ([D-55](DECISIONS.md), [D-56](DECISIONS.md)). Built and tested offline
(`tests/test_saved_and_release.py`); the installer's install, update, keep, rollback and update
check were run in a throwaway user folder on this PC (AutoCAD's own check switched off for that
run only). **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| P1 | Draw a plinth with the chat; "save that as plinth with width and depth as inputs"; then "plinth again, 1500 by 900" | The second plinth is the same shape at 1500 x 900, on the same layer, through Keep or Discard as usual | NOT RUN |
| P2 | With 1.4.2 installed, run the 1.5.0 zip's Install.bat (AutoCAD closed) | "Updating Heron from 1.4.2 to 1.5.0", "Earlier version kept", "Checked"; AutoCAD loads 1.5.0 | NOT RUN |
| P3 | Rollback.bat, answer Y; start AutoCAD | Back on 1.4.2; `autocad://diagnose` says plug-in 1.4.2 installed | NOT RUN |
| P4 | CheckForUpdate.bat with and without a newer release on GitHub | Says "newest version" or names the newer one with its page; installs nothing | NOT RUN |
| P5 | Push tag `v1.5.0` | The release workflow publishes a pre-release with the zip and checksums.txt; the zip's SHA-256 matches | NOT RUN |

## Group Q - A busy AutoCAD, from the Luxury Suite 3 rehearsal (AutoCAD 2027, this PC)

Added on 2026-11-20 ([D-57](DECISIONS.md), [D-58](DECISIONS.md)). Built and tested offline
(`tests/test_busy_autocad_1118.py`, which also registers the message filter on a real
Windows thread). Server only: restart the server after pulling; no plug-in build is needed.
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| Q1 | Two drawings open. `autocad_create_layer` 20 times in a row (a short script or the player), switching drawing tabs by hand while it runs | Every layer is made; none says "Call was rejected by callee"; a call that waited takes a few seconds longer at most | NOT RUN |
| Q2 | In a heavy realistic 3D drawing: `autocad_run_lisp` that turns a layer off, then one that restores a camera view with `-VIEW _R`, then `(+ 1 2)` | Each comes back with its result and `timed_out: false`, not "timed out" in half a second | NOT RUN |
| Q3 | Open AutoCAD's Options dialog and leave it open; call `autocad_list_layers` | Within about 15 s: "AutoCAD stayed busy ... press Esc"; the chat does not hang; after closing the dialog the next call works | NOT RUN |
| Q4 | After Q2, `autocad_get_variable` OSMODE, USERS1 and USERS2 | The values from before the call (snaps on as he had them; USERS1 not the pending marker) | NOT RUN |
| Q5 | Luxury Suite 3 player: the 2D rehearsal from `--from s037`, and the 3D steps marked `view_only` with that mark taken off | No stop at the layer steps or the view steps | NOT RUN |

## Group R - Padlocks in memory, the Windows policy, the Claude Code guard (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-59](DECISIONS.md), [D-60](DECISIONS.md), issues #76 and #77). Built and
tested offline (bridge `PadlockTests`, `ConfigTests`; `tests/test_padlock_guard.py`,
`tests/test_diagnose.py`). Needs the new plug-in build: close AutoCAD, `tools/build_plugin.py`,
`tools/install_plugin.py`. R5-R7 need an administrator command prompt; remove the key after.
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| R1 | Turn Changes, Admin, Publish and Ask to Keep on in Settings. Close AutoCAD, start it again, press Settings | Changes, Admin, Publish and Ask to Keep all **OFF** | NOT RUN |
| R2 | AutoCAD closed: edit `%APPDATA%\Heron\autocad\heron-autocad.config` to `{"write.enabled": true, "admin.enabled": true, "publish.enabled": true, "write.askBeforeKeeping": true}`. Start AutoCAD, press Heron, ask the chat to draw a line | Settings shows all four OFF (the file turned none on, Ask to Keep included); the chat is refused "Changes is off" | NOT RUN |
| R9 | Changes ON, Admin OFF; ask the chat "why can't you run this AutoLISP?" (`autocad_why`). Then set `AllowAdmin` 0 (R7) and ask again | First: Changes is not named, Admin is off with HERONADMIN. Second: "a Windows policy on this PC holds it off", ask the administrator | NOT RUN |
| R3 | With AutoCAD open and Changes off, write `"write.enabled": true` into the same file, then ask the chat to draw a line | Still refused "Changes is off"; Settings still OFF | NOT RUN |
| R4 | Two AutoCADs open. Turn Changes on in the first only | The second's Settings still shows Changes OFF, and a chat on it is refused | NOT RUN |
| R5 | `reg add HKLM\SOFTWARE\Policies\Heron\AutoCAD /v AllowChanges /t REG_DWORD /d 0 /f`, then press Settings | Changes shows **HELD** with "A Windows policy on this PC holds this off." and cannot be pressed; `HERONCHANGES` says it stays off; a chat is told "Changes is held off by a Windows policy" | NOT RUN |
| R6 | Changes ON; then run the R5 `reg add` while AutoCAD stays open; ask the chat to draw; then `reg delete HKLM\SOFTWARE\Policies\Heron /f` and press Settings | The draw is refused with the policy words; after the delete Changes shows OFF (not ON) until clicked | NOT RUN |
| R7 | `AllowAdmin` and `AllowPublish` set to 0, Changes on | Admin and Publish show HELD; `autocad_run_lisp` and a save are refused with the policy words; drawing still works | NOT RUN |
| R8 | In Claude Code in this folder on this PC, ask it to set `"write.enabled": true` in the config file (and, separately, to `reg add` the policy key to 1) | Each step is refused "Heron's padlock guard refused this step"; nothing written | NOT RUN |
| R10 | Put `"bridge.autoConnect": true` in `%APPDATA%\Heron\autocad\heron-autocad.config`, then start AutoCAD | Heron is **not** connected until you press Heron; `autocad_status` from a chat says not connected (D-73) | NOT RUN |
## Group T - How a change job answers and what it keeps (this PC)

Added on 2026-11-21 ([D-61](DECISIONS.md), [D-62](DECISIONS.md), [D-63](DECISIONS.md)), from Heron
AI for Revit (issues #78-#82). Built and tested offline only (`tests/test_bridge.py`,
`tests/test_gate.py`, `tests/test_answers.py`). Server only: restart the server after pulling; no
plug-in build is needed. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| T1 | In Claude Code, draw a line (Changes on), quit Claude Code, `claude --resume` the same chat at once, draw again | The second draw is let in at once, not "in use by another chat"; the audit lines of both carry the same `conversation`. A second, new chat at the same time is still refused | NOT RUN |
| T2 | Changes on, Ask to Keep off: draw a line; `autocad_find_replace_text` for a word that is not in the drawing; draw with Changes off; `autocad_create_layer` | Each answer's first line: `DONE - 1 added, 0 changed, 0 erased.`; `NOTHING CHANGED - ...`; `REFUSED - nothing was sent to AutoCAD.`; `DONE - no drawing object ... not counted ...` | NOT RUN |
| T3 | Ask to Keep on: draw a circle and press **Discard it**; then run a saved command (`autocad_saved_command` run) | `NOTHING CHANGED - the modeller chose Discard ...`; the saved command's answer starts with `DONE - ` and its counts | NOT RUN |
| T4 | Ask to Keep off: `autocad_draw_circle(..., dry_run=true)`; then `autocad_modify_entity` on a line with `layer` and `color`, `dry_run=true`; then `autocad_create_layer` `M-TEST` with `dry_run=true` | Each answer starts `NOTHING CHANGED - a dry run`; no circle in the drawing; the line keeps its layer and colour; no layer M-TEST (LAYER); one Ctrl+Z after it undoes the modeller's own last change, not a Heron step | NOT RUN |
| T5 | `autocad_loft` (a plug-in operation) and `autocad_set_current_layer` with `dry_run=true`; then `autocad_save_drawing(dry_run=true)` | The loft is gone and CLAYER is as before; the save is refused `REFUSED - nothing was sent ...`, and the file's date does not change | NOT RUN |
| T6 | `autocad_modify_entity` two lines to layer `M-DUCT` colour red, one already on it; `autocad_set_layer_state` `M-*` off twice; `autocad_set_variable` DIMSCALE 100 (Admin on); `autocad_find_replace_text` REV A -> REV B | Each answer's `before_after` names each object with its old and new value; the line already on M-DUCT is in `already`; the second layer call says `NOTHING CHANGED` and adds no undo step (the UNDO list in the Undo drop-down is one shorter than with two calls) | NOT RUN |
| T7 | Ask to Keep off: draw a line by hand. Then `autocad_align_text` mode `left` on two texts already lined up left (a tool that opens its group first). Open the Undo drop-down on the Quick Access toolbar. Repeat with Ask to Keep on and `autocad_find_replace_text` for a word that is not there | Write down what the list shows on top: the hand-drawn line (no empty Heron step), or a blank "Group" / "Mark" entry. One Ctrl+Z should remove the hand-drawn line; if it does not, the empty step is real (05 §26) | NOT RUN |

## Group V - The dialog watch (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-66](DECISIONS.md), issue #83). Built and tested offline
(`DialogWatchTests.cs`, `tests/test_gate.py`). Needs the new plug-in build and a server restart.
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| V1 | Admin ON: `autocad_send_command("_OPEN\n")` (FILEDIA 1, so the Select File dialog opens) | Within about 1 s the dialog closes by itself; the answer has `heron_dialogs`: "AutoCAD showed 'Select File'; Heron closed it with Cancel, nothing was kept from that step."; no drawing opens; the next call works without pressing Esc | NOT RUN |
| V2 | Open AutoCAD's Options dialog yourself and leave it open; then `autocad_list_layers` | Options is **not** closed; the answer is the Q3 "AutoCAD stayed busy" one; no `heron_dialogs` | NOT RUN |
| V3 | Ask to Keep ON: `autocad_draw_line`, then wait at Keep or Discard for 5 s | The Keep or Discard box stays up until you answer it; it is never closed by the watch | NOT RUN |
| V4 | Admin ON: change something in a drawing, then `autocad_send_command("_CLOSE\n")` | The "Save changes?" box gets **Cancel**, never Yes or No; the drawing stays open with the change; the answer names the box | NOT RUN |
| V5 | With no Heron job running, open the Select File dialog yourself (Ctrl+O) and wait 10 s | It stays open: the watch never acts outside a job | NOT RUN |
| V6 | During V1, look at the add-in log (`%LOCALAPPDATA%\Heron\autocad\logs`) | One line "dialog watch: 'Select File' -> Cancel"; no error lines | NOT RUN |
| V7 | Plug-in 1.7.0, Admin on. Draw two unused layers' worth of nothing; `autocad_send_command(command="_PURGE", expect_box="Purge - Confirm Purge", press="Yes")` (the dialog form; check the box's real title first) | The plug-in presses Yes on that box only; the answer says "Heron pressed Yes on it, as this call asked"; any other box in the same call is still cancelled. With Changes only (Admin off) the call is refused before anything is sent | NOT RUN |
| V8 | Same call with a plug-in older than 1.7.0 | Refused: "needs Heron's plug-in 1.7.0 or newer", nothing sent | NOT RUN |

## Group U - Check lists for QA: NO DATA, office and project lists, reports, wording (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-64](DECISIONS.md), [D-65](DECISIONS.md); issues #84-#87). Built and tested
offline (`tests/test_checklists_qa.py`). Server only: restart the server after pulling; no plug-in
build is needed. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| U1 | A saved sheet with NO title block; `autocad_checklist(action="save", name="sheets", checks=[{check: "title_block_filled", params: {block: "TITLE*"}}, {check: "nothing_on_layer_0"}])`, then run `sheets` | The title block line is **NO DATA** ("no block named TITLE*"), never PASS; the verdict is NO DATA, not PASS; coverage says "1 of 2 decided, 1 no data, 0 not run" | NOT RUN |
| U2 | On a big drawing, run `before issue` with `max_entities=10` | Lines with nothing wrong in the first 10 objects are NO DATA ("only the first 10 objects were read"), not PASS; a line that found a failure is FAIL | NOT RUN |
| U3 | `autocad_checklist(action="project", name="before issue", changes=[{id: "bylayer_colour", severity: "high"}, {id: "xrefs_found", on: false}])`, then run `before issue` | `bylayer_colour` is high and `from: project`; `xrefs_found` is NOT RUN; `checks_used` names all 5 with office / project; coverage ends "1 not run" | NOT RUN |
| U4 | Open a drawing in ANOTHER folder; run `before issue` | Every line `from: office`; no change from U3's folder | NOT RUN |
| U5 | `action="project"` with `changes=[{id: "my_new_check", on: true}]`, then with `[{id: "nothing_on_layer_0", label: "x"}]` | Both refused in plain words ("cannot add one", "may only change severity, target, on"); nothing kept | NOT RUN |
| U6 | Padlocks: Publish OFF. `autocad_checklist_report(name="before issue")` | Refused by the plug-in (Publish padlock); no file written next to the drawing | NOT RUN |
| U7 | Changes + Publish ON. `autocad_checklist_report(name="before issue")` twice | Two pairs next to the drawing: `<drawing> - checklist before-issue - <date>.xlsx` / `.html`, then the same with ` (2)`; the first pair unchanged (same size and time) | NOT RUN |
| U8 | Open U7's `.xlsx` in Excel and the `.html` in a browser | Excel opens it with no repair message; a Summary sheet, and a Check list sheet with one row per check with state, severity, source, from, objects; the HTML shows the same with coloured rows; both carry the coverage line and "PASS means the checked value is met" | NOT RUN |
| U9 | Ask the chat "does this drawing comply?" after a run that passes | The answer gives the verdict and coverage line, says PASS means the checked value is met against the named source, and does not say the drawing complies | NOT RUN |
| U10 | `autocad_check_standards(rules={...})` on a drawing that passes | `passed: true` with `source` and `pass_means`; the chat does not say "complies" | NOT RUN |
## Group W - Finding and explaining: why, gaps, question mode (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-67](DECISIONS.md)). Built and tested offline
(`tests/test_why_and_gaps.py`, `tests/test_find_tool.py`). Server only: restart the server after
pulling; no plug-in build is needed. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| W1 | AutoCAD closed: "why can't you save this as PDF?" (`autocad_why`) | Answers at once, no error: cannot run, first reason "No AutoCAD is connected", what to do says press Heron | NOT RUN |
| W2 | AutoCAD open, Heron pressed, Changes ON, Publish OFF: `autocad_why("save this as PDF")`, then ask for the PDF | `autocad_why` names Changes and Publish as needed and says it cannot see whether they are on (with HERONPUBLISH); the PDF is then refused naming Publish, and `autocad_gaps(days=1)` shows "The Publish padlock was off" | NOT RUN |
| W3 | Same, all padlocks ON: `autocad_why("draw a 200 flange with 8 bolt holes")` | `can_run: true`, tool `autocad_make_shape`, "should run" | NOT RUN |
| W4 | `autocad_why("make me a cup of tea")` | "Heron has no tool for this job" with "do it by hand" | NOT RUN |
| W5 | Turn Changes OFF, ask the chat to draw a line (refused), then `autocad_gaps(days=1)` | `autocad_draw_line` shows 1 refused; the failure reason is "The Changes padlock was off" with HERONCHANGES | NOT RUN |
| W6 | `autocad_gaps(days=30)` after a week of real work | Counts per tool look right; slowest jobs are the ones you remember as slow; drawings by file name only, no folder anywhere in the answer | NOT RUN |
| W7 | Read `autocad://tools/find/is that polyline closed` and `.../how many diffusers on this floor` | First match is a Read tool (`autocad_polyline_info`, `autocad_count_blocks`); no tool needing Changes in `matches` | NOT RUN |
| W8 | Read `autocad://tools/find/is there a clash between the duct and the steel` | `matches` holds only Read tools; `autocad_check_interference` is under `would_change_the_drawing` | NOT RUN |

## Group X - The docked Heron palette: Activity and Saved commands (D-68) (AutoCAD 2027, this PC)

Set-up: Changes on; a chat connected in Claude Code; Heron pressed. `HERONPALETTE` opens it.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| X1 | Type `HERONPALETTE`; then Heron (arrow) > **Heron palette**; then each again | A palette docked right with tabs **Activity** and **Saved commands**, dark Heron card, orange strip, the heron in the header; each press opens or closes it; the heron stays on top of the split button | NOT RUN |
| X2 | Ask the chat to draw three lines, then a circle | Two rows appear at once, newest (the circle) on top, each "made N, changed 0, erased 0" with the time, drawing and "done"; reads (status, list) do not appear | NOT RUN |
| X3 | On the lines row press **Select**, then **Zoom** | Select: the three lines selected, the view unchanged. Zoom: the view frames them, still selected; the line says how many | NOT RUN |
| X4 | Ask to Keep **off**. Draw a circle (Keep not asked), press **Zoom** on it, then **Undo** | The circle is gone; the line says "Undone: ..."; the row reads "undone from this palette". If instead the zoom was undone and the circle stays, the line says objects are still there: record it as FAIL (the palette's zoom left an undo step) | NOT RUN |
| X5 | Ask to Keep **on**. Draw a circle, Keep, then ask the chat to zoom, then **Undo** on the circle | `UNDO _Back`: the circle is gone (and the view goes back to before the job) | NOT RUN |
| X6 | Draw a circle with the chat, then draw a line by hand, then **Undo** on the circle | Refused: "The drawing changed after this job ... Use Ctrl+Z yourself"; nothing undone | NOT RUN |
| X7 | Two Heron changes, then **Undo** on the older one | Refused: "Heron did more after this job (...)"; nothing undone | NOT RUN |
| X8 | While a long chat job runs (a big batch), press Select, Zoom and Undo on an older row | Each refused: "Heron is working on a job right now"; the job is not disturbed | NOT RUN |
| X9 | Chat A holds this AutoCAD (a call less than 3 minutes ago): press **Select** and **Zoom** on its row | Both work (only a running job stops them) | NOT RUN |
| X10 | After X4, ask the chat `autocad_undo_last` | Refused: the drawing changed since; nothing undone | NOT RUN |
| X11 | In the chat: "save that as 'plinth'" with inputs width and depth; watch the Saved commands tab | 'plinth' shows within about 2 s, without a restart; search "plin" finds it | NOT RUN |
| X12 | Pick 'plinth', leave width empty, press Run; then type "wide"; then 1500 | Empty: "'width' needs a value"; "wide": "'width' needs a number, e.g. ..."; nothing sent to AutoCAD either time | NOT RUN |
| X13 | No chat holding AutoCAD (or after Free this AutoCAD). Fill 'plinth' with 1500 / 900, press **Run** | The banner shows the job; the plinth is drawn at those sizes; the line says "Done: 'plinth', N of N step(s)."; a new Activity row; then the chat can use AutoCAD at once (not after 3 minutes) | NOT RUN |
| X14 | Changes **off**, press Run | Refused with the Changes sentence (press Settings ...); nothing drawn | NOT RUN |
| X15 | Ask to Keep on, press Run, answer **Discard it** | Nothing kept; the line says "Discarded: nothing was kept." | NOT RUN |
| X16 | A chat holds this AutoCAD (a call within 3 minutes), press Run | "This AutoCAD is in use by another chat. Nothing was sent to AutoCAD." | NOT RUN |
| X17 | Press **Stop Heron now**, then Run | Refused: the modeller stopped Heron; nothing drawn | NOT RUN |
| X18 | Disconnect Heron, press Run | "AutoCAD is not connected to Heron. Press the Heron button first" | NOT RUN |
| X19 | Rename `%LOCALAPPDATA%\Heron\autocad\server.json`, press Run; put it back | "Heron's server has not run on this PC yet ..."; with it back, Run works. No console window flashes during a run | NOT RUN |
| X20 | Two AutoCADs connected; Run from the second's palette | The command runs in the second AutoCAD, not the first | NOT RUN |
| X22 | Start AutoCAD from a command prompt after `set HERON_AUTOCAD_BRIDGE=off`; Changes **off**; press Run | Refused with the Changes sentence, as in X14: the run still goes through the plug-in's checks | NOT RUN |
| X24 | Start a long `autocad_sequence` from the chat and, in the second before it begins, press **Undo** on the newest row (or type `HERONPALETTE` Undo while the chat is about to call) | The chat's call is refused with "The modeller is undoing a Heron change from the Heron palette right now. Try again in a moment."; the Undo removes only the palette's job; the retried call works | NOT RUN |
| X23 | On a layout, inside a floating viewport: have the chat draw a circle (Ask to Keep off), press **Zoom** on it, then **Undo** | Record what happens. If Undo says "The drawing changed after this job", the viewport's zoom counted as a change (a viewport is an object): note it in 06 section 10 as a known limit. Either way nothing of the modeller's is undone | NOT RUN |
| X21 | AutoCAD 2025 / 2026 and 2021-2024 builds: X1, X2, X4, X13 | As in AutoCAD 2027 | NO MACHINE |

## Group Y - Attribute sheets, folder checks, the Companion page (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-69](DECISIONS.md), [D-70](DECISIONS.md), [D-71](DECISIONS.md),
[13](13-sheets-folders-companion.md)). Built and tested offline only (`tests/test_attribute_sheet.py`,
`tests/test_check_folder.py`, `tests/test_companion.py`). Server only: restart the server after
pulling. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| Y1 | In a saved drawing with camera blocks: `autocad_export_attribute_sheet` with Publish **off**, then on | Off: refused naming Publish, no file. On: `<drawing> - attributes - <date>.xlsx` next to the drawing; Excel opens it with sheets Attributes, As exported, Read me; tags such as `0050` still read `0050` | NOT RUN |
| Y2 | In Excel change two TAG cells, empty one cell, save. `autocad_apply_attribute_sheet` with `dry_run=true`, then without | Dry run: `would_change: 2`, drawing unchanged. Then two attributes change, `before_after` lists both old -> new, the emptied cell is untouched; one Ctrl+Z undoes both | NOT RUN |
| Y3 | After Y1, change one TAG in the drawing by hand, and the same TAG of another block in Excel; then change the first block's TAG in Excel too; apply | The hand change stays (`kept_drawing`) when Excel left it; the cell changed in both is in `conflicts` and not written | NOT RUN |
| Y4 | A folder with 3 drawings, one of them open, one a newer-format or damaged file: `autocad_check_folder` | Each opens read only (title bar says read-only) and closes unsaved; the open one stays open; the bad one is NOT RUN with AutoCAD's reason; the modeller's drawing is active again at the end; no drawing's file date changes | NOT RUN |
| Y5 | During Y4 press HERONSTOP after the first drawing | The rest are not opened; the answer says HERONSTOP; the modeller's drawing is active | NOT RUN |
| Y6 | `autocad_companion`, open the page in a browser; select 3 objects, ask the chat to draw a line, then to refresh the companion page | The page shows the drawing, units, layout, view; within 5 s of the draw a new row "Draw Line ... done +1"; after the refresh the selection reads 3 objects; the browser's dev tools show no script and no request | NOT RUN |
| Y7 | After Y1, type `1:100` in a SCALE cell and a date in a DATE cell in Excel (no leading '), and a value in a row's Block column that is not that block; apply with `dry_run=true` | Those cells are in `excel_converted` and that row in `other_block`; none of them is in `changes`; with `'1:100` typed instead it is written as `1:100` | NOT RUN |

## Group AB - Layers and annotation: layer states, isolate, merge, dimension style, space, break, annotative (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-80](DECISIONS.md), [D-81](DECISIONS.md); issues #37, #107, #108, #116).
Built and tested offline (`tests/test_dim_style_run.py`, `tests/test_dimensions_edit.py`,
`tests/test_layer_states.py`, `tests/test_annotation_scales.py`, `RunTests.cs`); the plug-in
**compiles** against AutoCAD 2021-2024, 2025-2026 and 2027. Six new plug-in operations: build and
install the plug-in (`tools/build_plugin.py`, close AutoCAD, `tools/install_plugin.py`) and restart
the server. Changes on. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AB1 | In a 1:50 drawing (`autocad_drawing_setup(scale="1:50")`) with a dimension style `DIM-1-5` whose DIMSCALE is 5: `autocad_dimension_run(points=[[0,0],[300,0],[750,0]], offset=50, dim_style="DIM-1-5")`, then a run with no style | The styled run's arrows and text are a tenth the size of the plain run's; LIST shows style DIM-1-5 and no DIMSCALE override; `style_scale` is 5; DIMSTYLE afterwards still shows the old current style with its DIMSCALE 50 override; `dim_style="NOPE"` is refused and nothing is drawn | NOT RUN |
| AB2 | Three stacked horizontal dimensions about 200, 450 and 1300 off a base dimension: `autocad_space_dimensions(handles=[base, a, b, c], spacing=400, dry_run=true)`, then without dry_run; then `spacing=0` | Dry run moves nothing; then the dimension lines sit exactly 400, 800, 1200 off the base (measure), extension lines still start on the geometry, text moved with them; one Ctrl+Z puts them back; spacing 0 lines them all up on the base line | NOT RUN |
| AB3 | Same with an aligned stack on a 30-degree slope, and one radius dimension in the list | The aligned ones step out square to the slope; the radius dimension is in `skipped` and has not moved | NOT RUN |
| AB4 | Two dimensions crossed by two pipe lines: `autocad_break_dimensions(handles=[...])`, then `remove=true` | A gap (DIMBREAK size) where each line crosses each dimension; AutoCAD back at `Command:`; move a pipe and the gap follows; `remove` takes the gaps off; a line's handle in the list, or a dimension on a locked layer, is refused and nothing typed | NOT RUN |
| AB5 | Turn some layers off and freeze one: `autocad_layer_states(action="save", name="COORD")`; change the layers; `action="restore"`; `autocad_list_layers` | LAYERSTATE dialog shows COORD; restore brings back every layer as saved and `before_after` lists exactly the layers that changed; `list_layers` gives COORD in `layer_states`; saving COORD again without overwrite is refused | NOT RUN |
| AB6 | Current layer 0: `autocad_isolate_layers(handles=[a duct])`, then again with a pipe, then `action="unisolate"`; then with `others="lock"` and `others="freeze"` | Only the duct's layer shows and becomes current; the second isolate keeps the first state (`already_isolated`); unisolate puts every layer and current layer 0 back and HERON-ISOLATE is gone from LAYERSTATE; lock mode greys the others and they cannot be picked; freeze works with the current layer moved first; isolating a frozen layer thaws it and makes it current | NOT RUN |
| AB7 | Layers DUCT (locked, objects in model space, on a layout, inside a block definition and one block attribute) and M-DUCT: `autocad_merge_layers(layers=["DUCT"], into="M-DUCT")`, then with `confirm=true` | First call changes nothing and counts drawing / blocks / attributes right; then every one is on M-DUCT (also inside the block, the attribute too), DUCT is gone from the layer list; one Ctrl+Z brings it all back | NOT RUN |
| AB8 | Same, but DUCT frozen in one layout viewport (VP freeze) | Either DUCT is removed, or it is kept with AutoCAD's reason; no object is left on it | NOT RUN |
| AB9 | 1:50 drawing: `autocad_add_text(text="NOTE", height=125, annotative=true)`; `autocad_list_annotation_scales(handles=[it])`; then `autocad_annotation_scales(handles=[it], add=["1:100"])` and look in a 1:50 and a 1:100 viewport | The text shows the annotative icon; Properties shows Paper text height 2.5 and Model 125 (if it shows 6250 or 2.5 the height rule in D-81 is wrong: record which); `paper_height` is 2.5; after the add it is 2.5 mm on paper in both viewports | NOT RUN |
| AB10 | `autocad_add_dimension(..., annotative=true)`, `autocad_dimension_run(..., annotative=true)`, `autocad_add_multileader(..., annotative=true)`, then one Ctrl+Z each | Each is annotative at 1:50 (OBJECTSCALE lists 1:50), arrows and text sized from the scale, not doubled by DIMSCALE; one Ctrl+Z removes the object and its annotative state together | NOT RUN |
| AB11 | `autocad_annotation_scales(handles=[it], add=["1:25"])`, then with `add_missing_to_drawing=true`; then `remove=["1:25","1:50","1:100"]` | First is refused (no 1:25); second adds 1:25 to SCALELISTEDIT and to the object (`scales_created`); removing every scale is refused and nothing changes | NOT RUN |

## Group AE - Setting a render up: style read back, camera views, sun, lights, exposure (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-86](DECISIONS.md), [D-87](DECISIONS.md); issues #59-#63). Built and tested
offline only (`tests/test_render_view.py`, `RenderViewMathTests.cs`, `RunTests.cs`); the add-in
**compiles** for all three AutoCAD builds. Needs the plug-in built from this change (five new
operations) and a server restart. **None of these tools renders: in every row Ajmal presses Render.**
Use a model with a room, a few lights and a light block (the villa or Luxury Suite model).
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AE1 | `autocad_set_3d_view(visual_style=...)` once for each of the ten styles; then VSCURRENT Hidden by hand and `autocad_set_3d_view(direction='sw_iso')` | Each answer's `visual_style_found` is the style on screen (record AutoCAD's exact names, e.g. `Realistic`, `Shades of Gray`), with no `visual_style_warning` and no `visual_style_found_from` for a style that took; after the hand change it says `Hidden`. If it lags one style behind, the read needs the viewports written to the drawing first, as `set_sun` does | NOT RUN |
| AE2 | Inside a room: `autocad_add_camera_view(name='LIVING-CAM-1', eye=[<corner>, 1600], target=[<far wall>, 1200], lens=24)` | The screen shows the room in perspective from the corner (in 2D Wireframe the answer warns instead, and perspective shows after `visual_style='realistic'`); VIEW lists LIVING-CAM-1 as a perspective view; Properties of the view: lens 24 mm. Record AutoCAD's Field of view next to the answer's `field_of_view_degrees` (73.74). One Ctrl+Z removes the view | NOT RUN |
| AE3 | After AE2: zoom and orbit away, then VIEW, restore LIVING-CAM-1 | The same perspective comes back at **24 mm** (an `entmake` view came back at 50 mm on 2026-11-09); no DVIEW prompt, nothing hangs | NOT RUN |
| AE4 | `autocad_add_camera_view` with the AE2 name again, then with `replace=true` and a new eye, then a new name with `look_through=false` | First refused naming replace; second moves LIVING-CAM-1; third saves the view and leaves the screen as it was. Ajmal renders LIVING-CAM-1 from the Render window's view list: the picture is the camera's | NOT RUN |
| AE5 | `autocad_set_sun(date='2026-06-21', time='10:00', latitude=25.29, longitude=51.53, utc_offset=3, daylight_saving=false, on=true)` | Sun Properties: 21/06/2026, 10:00, no daylight saving; Geographic Location: 25.29 **N**, 51.53 **E**, UTC+3; `(entget (cdr (assoc 361 (entget (tblobjname "VPORT" "*Active")))))` shows groups 91 and 92 equal to the answer's `dxf` (2461213, 36000000). Record whether `azimuth` / `altitude` are in degrees as Sun Properties shows them. One Ctrl+Z takes back the date, the place and SUNSTATUS together | NOT RUN |
| AE6 | Orbit the view, then `autocad_set_sun(time='16:30')` | Only the time changes (date and place stay); the view on screen does **not** jump back to an older angle; the shadows move in a realistic view with DEFAULTLIGHTING 0 | NOT RUN |
| AE7 | In a new drawing that has never had a sun: `autocad_set_sun(date='2026-12-21', time='09:00')`, then one Ctrl+Z | `sun_made: true`; Sun Properties shows the date and time; one Ctrl+Z takes back the sun's date and any place set in the same call | NOT RUN |
| AE8 | `autocad_set_sun(latitude=9.93, longitude=76.27, utc_offset=5.5)`; then `utc_offset=5.75` | TIMEZONE reads 5030 and Geographic Location shows the India time zone; 5045 is taken as Nepal. If AutoCAD refuses a code, it is in `not_set` | NOT RUN |
| AE9 | `autocad_list_lights` in the villa (lights in model space and in a light block) | The list matches the Lights in Model palette: names, on / off, intensity and unit; the block's lights show its name and the right insert count; the sun part matches Sun Properties; DEFAULTLIGHTING 1 gives the warning | NOT RUN |
| AE10 | `autocad_switch_lights(turn_off=['<a model space light>'])`; then `turn_on=['NO-SUCH-LIGHT', '<that light>']` | The palette shows it off and the room goes darker in a realistic view; one Ctrl+Z switches it back on (the plug-in's switch and the variables are one undo step); the second call is refused listing the light names, and the light stays off | NOT RUN |
| AE11 | `autocad_switch_lights(turn_off=['<the light's name inside the block>'])` | Every insert of the light block goes dark after the answer (it regenerates); BEDIT shows the light off in the definition | NOT RUN |
| AE12 | DEFAULTLIGHTING 1, SUNSTATUS 0: `autocad_switch_lights(sun=true)`; undo; then `autocad_switch_lights(default_lighting=false, sun=true)` | Record whether AutoCAD shows its viewport lighting question in each case, and what the answer says (the dialog watch names a box it closed). In the second, both are set with no question | NOT RUN |
| AE13 | Lock a light's layer, then switch that light | Refused: an object is on a locked layer; nothing switched | NOT RUN |
| AE14 | `autocad_set_render_exposure(exposure=7, white_balance=4500)`, then `autocad_list_lights` | If AutoCAD 2027 has EXPVALUE: the RENDEREXPOSURE palette shows 7 and 4500, and a render Ajmal starts is brighter and cooler than at 8.8 / 6500. If it is refused naming RENDEREXPOSURE: record it, nothing changed, and the ROADMAP's viewport route is next | NOT RUN |
| AE15 | AE1-AE14 on AutoCAD 2025/2026 and 2021-2024 | As AE1-AE14 | NOT RUN (no PC with those versions yet) |

## Group Z - Undo commands, long AutoLISP, quiet answers, busy answers (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-76](DECISIONS.md), [D-77](DECISIONS.md); issues #42, #44, #46, #47). Built
and tested offline only (`tests/test_undo_command_retry.py`, `tests/test_lisp_split.py`,
`tests/test_quiet.py`, `tests/test_busy_answers.py`, `BusyCommandTests.cs`). Z5-Z8 need the plug-in
built from this change (its ping says `command`); restart the server after pulling. **Every row
below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| Z1 | Draw 3 lines with Heron, then `autocad_send_command("_U")` while a heavy regen or a tab switch keeps AutoCAD busy | Either one line is undone, or the answer is OUTCOME UNKNOWN naming U ("sent twice, it would undo or redo one step more"); never two lines undone. `autocad_undo_last` straight after refuses (a raw command came in between) | NOT RUN |
| Z2 | `autocad_run_lisp` with six `defun`s of about 600 characters each (3,600+ in all, with comments and line breaks), then a call of the last one, in one expression | `chunks: 6`, `chunks_finished: 6`, the last form's value back; each function exists afterwards (`(type f0)` is USUBR); the command history shows six pieces, none over about 1,000 characters | NOT RUN |
| Z3 | Z2 again with a typing mistake in the third defun (an undefined function call at top level of that form) | Stops at piece 3: `timed_out` true, "piece 3 of 6", "3 more were not sent"; f0 and f1 exist, f3-f5 do not; one Ctrl+Z takes back the whole call | NOT RUN |
| Z4 | `(command "_LINE" "0,0")` and `(command "100,0" "")` as two top-level forms, padded so they land in two pieces | The first piece is named in `cancelled_command` (LINE), the second is not sent, AutoCAD is back at Command: | NOT RUN |
| Z5 | `autocad_sequence` of eight `autocad_dimension_run` steps (a 5-point grid each, `include_overall`), once without and once with `quiet=true` | Quiet: every step has `count`, `handles`, `left_out: {"dimensions": 5}` and no points; the answer is well under half the size; the dimensions in the drawing are the same both times | NOT RUN |
| Z6 | Start `_HATCH` by hand and leave it at its prompt; ask Heron to draw a line | The answer's first line names the HATCH command ("it is still in the HATCH command") and says nothing was changed, or counts what changed | NOT RUN |
| Z7 | Open a dialog by hand (e.g. OPTIONS) and leave it; ask Heron to read an entity | The answer ends "AutoCAD was busy: it is in no command now, so a redraw or a box held it" (or names OPTIONS, if AutoCAD reports it as a command) | NOT RUN |
| Z8 | `autocad_run_lisp` with `(command "_.DELAY" 15000)` (longer than its 10 s wait) | If it answers `timed_out: true`, the first line is OUTCOME UNKNOWN (not DONE) with what the plug-in counted so far, naming DELAY or AutoLISP when AutoCAD kept the reads away; if the value came back, DONE. Note which one AutoCAD 2027 gives | NOT RUN |
| Z9 | Z6 with a plug-in built before this change | The answer reads as before (no command named) and nothing fails | NOT RUN |
| Z10 | Ask to Keep on; draw a line; while the Keep or Discard box is up, start a heavy regen in another viewport, then press Discard | The line is gone and nothing older is undone; or the answer says "Outcome unknown ... UNDO Back" and the modeller's earlier work is still there. Never two Backs | NOT RUN |

## Group AA - The everyday 2D edits (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-78](DECISIONS.md), [D-79](DECISIONS.md); issues #103, #49, #105, #111,
#110). Built and tested offline only (`tests/test_edit2d_geometry.py`, `tests/test_edit2d_tools.py`).
Server only, no plug-in change: restart the server after pulling. Draw the test objects by hand in
a scratch drawing, `autocad_status` first. After each row press **Ctrl+Z once** and check the drawing
is back as it was (one undo step). **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AA1 | A line 0,0 to 1000,0 and a "wall" line 400,-100 to 400,100. `autocad_trim_extend` trim, edges=[wall], points=[[200, 0]] | The line now runs 400,0 to 1000,0 (same handle, same layer); one Ctrl+Z brings back the full line | NOT RUN |
| AA2 | The same line, two walls at x=300 and x=700, point [500, 0] | Two lines 0-300 and 700-1000; the second has a new handle and the first's layer, colour, linetype and lineweight | NOT RUN |
| AA3 | A closed rectangle 1000 x 500 and a line across it at x=600; trim with a point on its right side. Then a circle r=100 with a line through its centre, trim one half | The rectangle is one open polyline round the left part; the circle is replaced by a half arc with its look, and Heron asks to keep the circle erased (D-50) | NOT RUN |
| AA4 | Three short lines below a long "main" line; `autocad_trim_extend` extend, no points. Then an arc 0 to 90 degrees and a line beyond its end | Each short line now ends on the main; the arc runs on round its circle to the line; nothing else moved | NOT RUN |
| AA5 | A polyline with a constant width of 20, trimmed; then one whose width tapers (start 0, end 20), trimmed | The first keeps width 20 on every piece; the second is refused ("width changes along it") and nothing changes | NOT RUN |
| AA6 | Two lines meeting at a square corner (not touching). `autocad_fillet_chamfer` fillet, radius=150; then two more with radius=0 | An arc r=150, tangent to both (AutoCAD's own FILLET with the same radius gives the same arc), on the first line's layer; radius 0 gives a sharp corner and no arc | NOT RUN |
| AA7 | Chamfer two lines distance=50, distance2=30; then distance=50, angle=30 | Measured with `autocad_measure`: 50 and 30 back from the corner; the angle method gives 50 and 28.87 on a square corner, matching AutoCAD's CHAMFER Angle | NOT RUN |
| AA8 | A closed polyline 1000 x 500: fillet with radius=50, no vertices | One polyline, 8 vertices; `autocad_polyline_info` area = 500000 - (4 - pi) x 50^2 = 497853.98 | NOT RUN |
| AA9 | `autocad_break_curve` on a line at a point; on a line with second_point; on a circle with two points | Two touching lines; two lines with the gap; the circle is an arc missing the part from the first point anticlockwise to the second | NOT RUN |
| AA10 | Two lines and an arc drawn end to end (the arc in the middle, drawn in any direction): `autocad_join_curves`. Then two lines in one straight line | One polyline with the arc kept as an arc (a bulge), on the first object's layer; the others erased after the modeller's yes. The two straight lines become one line | NOT RUN |
| AA11 | A 4-vertex polyline: `autocad_edit_vertex` move vertex 2 by [0, -200]; add a vertex after 0; remove it again. A line: move its end with `near` | Each change as asked, the arcs next to a moved vertex still arcs; a line end goes exactly to to_point | NOT RUN |
| AA12 | A rectangle, a door block on its right side, a hatch half over the right side, a circle far away: `autocad_stretch` with a window round the right side, displacement [600, 0] | Right side of the rectangle 600 longer; the door moved whole; the hatch listed in `skipped` and unmoved; the circle `untouched`. A polyline with different widths per segment, stretched: record whether its widths stay | NOT RUN |
| AA13 | `autocad_explode` on a plain block, then on a block with attributes, then the same with allow_attribute_loss=true | The plain block: its lines are separate objects and the block reference is gone (check it is not left under the pieces), Heron asks to keep it erased; the attributed one skipped with its values; then exploded with the values listed | NOT RUN |
| AA14 | A new drawing (no draw order set): a hatch drawn over lines, `autocad_draw_order` back; then a line above / under the hatch; then the same on a layout | The hatch shows behind the lines at once (or after a regen); AutoCAD's own DRAWORDER agrees afterwards; above / under put the line where asked; on a layout too | NOT RUN |
| AA15 | A line with a true colour (RGB 200,100,50), lineweight 0.35, transparency 40 on layer M-PIPE: `autocad_match_properties` to two lines and a text; then a text's text_style to another text; then a dimension's dim_style | The lines take all six (Properties palette shows the true colour); the text takes the general six, its text style untouched and listed in `skipped`; text and dimension styles copy when asked | NOT RUN |
| AA16 | `autocad_modify_entity` lineweight=0.35, transparency=50 on a line; then lineweight=0.33 | The Properties palette shows 0.35 mm and 50; 0.33 is refused with the list | NOT RUN |
| AA17 | `autocad_group` make PUMP-01 from three objects; `autocad_list_groups` (also a group made by hand with GROUP, and one unnamed); add one, remove one, then ungroup | The GROUP command's list shows PUMP-01 with its members; the list shows all three groups with the unnamed one marked; after ungroup the objects stay and are no longer grouped; Ctrl+Z brings the group back | NOT RUN |
| AA18 | Lock a line's layer and trim it; then trim with dry_run=true | Locked: refused naming the layer, no copy made. Dry run: the answer says what it would cut and the drawing is unchanged after | NOT RUN |
| AA19 | Set a UCS turned 30 degrees; trim with coords='ucs' and the point read off the screen | The part cut is the one at that UCS point | NOT RUN |
| AA20 | AutoCAD 2025 / 2026 and 2021-2024 builds: AA1, AA6, AA10, AA14 | As in AutoCAD 2027 | NO MACHINE |

## Group AC - Blocks, attributes and tables: ATTDEF, ATTSYNC, Excel tables, cell edits, copy between drawings (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-82](DECISIONS.md), [D-83](DECISIONS.md); issues #115, #117, #106). Built
and tested offline only (`tests/test_block_attributes.py`, `tests/test_tables.py`,
`tests/test_drawing_copy.py`); the plug-in operations `sync_attributes`, `excel_table` and
`update_table_links` build for all three targets but have never run. Needs the plug-in rebuilt
and reinstalled, and the server restarted. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AC1 | Draw a circle, `autocad_make_block(name='VALVE TAG', handles=[circle], base_point=<centre>, attributes=[{"tag":"TAG","default":"V-101","position":<centre>,"height":25},{"tag":"SIZE","default":"DN50","invisible":true},{"tag":"MAKE","default":"ACME","constant":true}])` | One insert in place of the circle; BATTMAN lists TAG, SIZE, MAKE with those modes; TAG shows V-101 at the centre; SIZE is hidden (ATTDISP ON shows it under the base point); MAKE shows ACME and is not asked for on INSERT; one Ctrl+Z takes it away | NOT RUN |
| AC2 | `autocad_make_block` with a tag `VALVE TAG`, then with `constant` and no default | Both refused with the reason; no block made (`autocad_list_blocks`) | NOT RUN |
| AC3 | After AC1, insert VALVE TAG three more times, type TAG values V-102..V-104. In the Block Editor add a FLOW attribute and delete SIZE, save. `autocad_sync_attributes(block='VALVE TAG', dry_run=true)`, then without | Dry run: 4 inserts, each keeps its TAG, gains FLOW, loses SIZE; drawing unchanged. Then each insert shows its own V-10x still, FLOW with its default, no SIZE (ATTEDIT); one Ctrl+Z undoes it all | NOT RUN |
| AC4 | A dynamic block with an attribute, three inserts with their grips changed (so they are *U copies). Change the attribute's position in the Block Editor; sync | All three are touched (`touched: 3`), keep their values, and the attribute sits where the definition now has it | NOT RUN |
| AC5 | One insert on a locked layer, one attribute holding a field (Insert Field into the TAG value); sync | The locked one is in `skipped`, not changed; the job still runs for the others; the field attribute keeps its field (`kept_as_they_were: 1`) | NOT RUN |
| AC5b | During AC7, type HERONSTOP while the table is being linked; and `autocad_table_from_excel(space='paper')` with the Model tab active | Neither draws a table over COM: the stop is said, and the Model-tab refusal asks for a sheet tab. Nothing is in the drawing | NOT RUN |
| AC6 | `autocad_sync_attributes(block='PUMP', add_attributes=[{"tag":"MAKE","default":"GRUNDFOS","position":[0,-300],"invisible":true}])`; then add `{"tag":"FLOW"}` with no position | The PUMP definition has MAKE (BATTMAN), every PUMP insert carries it with GRUNDFOS, hidden, 300 below the base point as the block is drawn. FLOW lands under the lowest attribute already there, not on top of one | NOT RUN |
| AC7 | A saved drawing with `pumps.xlsx` beside it (a header row and 5 pumps). `autocad_table_from_excel(path='pumps.xlsx', position=[0,0], cell_range='A1:D6')` | `"linked": true`; a table of 6 rows x 4 columns; DATALINK lists "Heron pumps Sheet1 A1:D6" pointing at the file and range; the cells show what Excel shows; text in the vertical middle of each cell. **Note whether Excel had to be installed** | NOT RUN |
| AC8 | After AC7, change two values in Excel, save, close; `autocad_update_table_links()` | `updated` names the table; the two cells show the **new** values (not the link's cached old ones: the link is read again first, then the table); the alignment is still vertical middle; one Ctrl+Z goes back | NOT RUN |
| AC9 | `autocad_table_from_excel` from a `.csv`, and with `link=false`, `title='PUMP SCHEDULE'` | Both fill a table with `"linked": false` and the reason; the title row is merged across the top; with no title the first row is the sheet's header row (no empty title row) | NOT RUN |
| AC10 | A sheet with a date cell (no leading ') in the range, `link=false` | That cell is empty in the table and listed in `excel_converted` | NOT RUN |
| AC11 | `autocad_set_table_cells(handle=<AC9 table>, cells=[{"cell":"B3","value":"12.5"},{"row":4,"column":2,"value":"8"}], dry_run=true)`, then without; then a cell past the last row with and without `grow=true` | Dry run lists old -> new and changes nothing; then those two cells change (text vertical middle), one Ctrl+Z undoes both; past the end refused, then with grow one row is added and filled | NOT RUN |
| AC12 | `autocad_set_table_cells` on a cell of the AC7 linked table | Refused for that cell: "linked to Excel: change it in the sheet" | NOT RUN |
| AC13 | `autocad_add_table` with a title, headers and rows; then with headers and no title; then rows only | Title, header and data text in the vertical middle of their cells (`rows_aligned_middle: 3`). With no title there is no empty merged row at the top: the headings sit one per cell in row 1 and nothing is in `not_set` (`suppressed: [TitleSuppressed]`); with rows only, the first row is ordinary data, not bold headings. Before this, a table with no title was expected to put the headings into the merged title row (not seen live) | NOT RUN |
| AC14 | Two drawings open: `pump-room.dwg` with a pump skid (a block with a nested motor block on layer E-MOTOR, layer M-EQPT) and `plan.dwg` that has M-EQPT in another colour. In plan.dwg after `autocad_status`: `autocad_copy_from_drawing(source='pump-room', handles=[skid, two pipes], base_point=[0,0], to_point=[5000,2000], dry_run=true)`, then without | Dry run lists E-MOTOR and the blocks as brought in, M-EQPT as already here; nothing copied. Then the skid and pipes appear 5000,2000 away in plan.dwg, the new handles come back, E-MOTOR is a new layer, M-EQPT keeps plan.dwg's colour; plan.dwg stays active and pump-room.dwg is unchanged; one Ctrl+Z in plan.dwg takes them away | NOT RUN |
| AC15 | Same, with a handle from plan.dwg, and with `source='plan'` | Refused before anything is copied: the wrong handle is named; the active drawing as source points at `autocad_copy_entities` | NOT RUN |
| AC16 | Same as AC14 with objects in pump-room.dwg's paper space and `space='paper'` with a sheet tab active in plan.dwg | They land on plan.dwg's sheet | NOT RUN |

## Group AG - Files with AutoCAD closed, standards against a reference drawing, shared check lists (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-92](DECISIONS.md), [D-93](DECISIONS.md); issues #71, #69, #135). Built and
tested offline (`tests/test_read_file.py`, `tests/test_shared_checklists.py`): the DXF reader is
proved there on small DXF files made with ezdxf, and the compare, the refusals and the shared-file
rules on plain data. **Set-up:** close Claude, run `.venv\Scripts\python.exe -m pip install ezdxf`
once (a new dependency, installed by name: [05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)),
start Claude again. Server only: no plug-in build is needed. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AG1 | AutoCAD **closed**. `autocad_read_file(path="<a real project .dxf>")`, then `what="layers"`, `"blocks"`, `"text"`, `"attributes"` | Answers with AutoCAD closed; units, layer names and colours, block counts and title block values match what AutoCAD shows when the file is opened (record two counts side by side). No AutoCAD starts; the file's date is unchanged | NOT RUN |
| AG2 | AutoCAD closed, ODA File Converter **not** installed: `autocad_read_file(path="<a .dwg>")` | Refused in plain words: needs AutoCAD, the ODA File Converter, or a DXF of it; nothing downloaded | NOT RUN |
| AG3 | Install the ODA File Converter (from the Open Design Alliance, by hand). Repeat AG1 on a `.dwg` and on the office `.dws` | `read_by` names the converter's path; layers and block counts match AutoCAD; no converter window flashes up; nothing is left in `%TEMP%\heron-oda-*`; the `.dwg` / `.dws` date is unchanged. Record the converter version and the seconds taken | NOT RUN |
| AG4 | `autocad_read_file` on a DWG with dynamic blocks (valves, doors) and `what="blocks"` | Placed counts are under the dynamic block's own name, not `*U12`; the count matches AutoCAD's BCOUNT / Count palette | NOT RUN |
| AG5 | AutoCAD open, a project drawing active: `autocad_check_standards(reference="<the office .dws>")`, converter **not** installed | `reference.read_by` says AutoCAD's own reader (ObjectDBX); the .dws does not open on screen; the findings name layers and text styles that really differ (check two by hand in the Layer and Style dialogs). AutoCAD's CHECKSTANDARDS on the same pair: record where the two disagree | NOT RUN |
| AG6 | AG5 with the office `.dws` **open** in AutoCAD as well | `read_by` says the drawing is open there; same findings as AG5 | NOT RUN |
| AG7 | AG5 with a `.dxf` saved from the `.dws`, then with `flag_extra=false` | Same findings as AG5 (`read_by` ezdxf); with `flag_extra=false` the "not in standard" lines are gone. A layer with a true colour: record what is said | NOT RUN |
| AG8 | Text styles: a style with a TrueType font (Arial) in both drawings, and one with romans.shx vs simplex.shx | Arial is not reported; the SHX pair is reported as "font ... here, ... in the standard" | NOT RUN |
| AG9 | `autocad_checklist(action="office_folder", folder="<a real network share>")`, then `autocad_share_checklist(share="office_list", name="before issue")` with Publish ON; run `before issue` on a second PC pointed at the same share | The file appears on the share with `saved_by` = this Windows user; the second PC's run says `office_from: office folder` and names the share's file on every line | NOT RUN |
| AG10 | Disconnect the network drive (or unplug), then run `before issue` | Within about 10 s: the run says the office folder could not be reached and that it used this PC's copy, with the date read; the verdict is given | NOT RUN |
| AG11 | Second PC changes the list and shares it with `replace=true`; first PC shares its own different list without replace | First PC is refused, naming the second PC's user and time and what differs; the share's file is unchanged. With `replace=true`, the file holds `previous` with the second PC's list | NOT RUN |
| AG12 | A share where this user has read-only rights: share a list | Refused: "read-only for you"; nothing written | NOT RUN |
| AG13 | `autocad_share_checklist(share="project_changes", name="before issue", changes=[{id: "xrefs_found", on: false}])` in a job folder; open another drawing in the same folder on the second PC and run `before issue` | `Heron check list changes.json` is in the job folder; the second PC's run has `xrefs_found` NOT RUN, `from: project`, naming that file | NOT RUN |
| AG14 | Padlocks: Publish OFF. `autocad_share_checklist(share="office_list")` | Refused by the plug-in (Publish padlock); nothing written to the share | NOT RUN |
| AG15 | `autocad_why(job="read the layers of a DXF file")` with AutoCAD closed | `can_run: true`, the tool `autocad_read_file`, no "press Heron" reason | NOT RUN |

## Group B - AutoCAD 2025 / 2026 (.NET 8 build)

Rows B1-B19 = A1-A19 on AutoCAD 2025 and on 2026, and H1-H13 on each. **NO MACHINE.**

## Group C - AutoCAD 2021 to 2024 (.NET Framework 4.8 build)

Rows C1-C19 = A1-A19 on each of 2021, 2022, 2023, 2024, and H1-H13 on each. **NO MACHINE.** Look first at C1 and C3:
the .NET Framework build loads System.Text.Json and its helpers from the bundle folder (an
AssemblyResolve fallback), so a missing-DLL error would show there, in the add-in log.

## Server items not provable offline

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| S1 | Make AutoCAD busy mid-batch (open a dialog during a large `autocad_batch_draw`) | `Outcome unknown...` and no duplicate geometry | NOT RUN |
| S2 | `autocad_check_standards` on a real project drawing with a rules file | Findings match a manual check of 5 random layers | NOT RUN |
| S3 | `autocad_extract_attributes` on the CCTV package (CAM blocks), CSV | One row per camera, tags as columns | NOT RUN |
| S4 | `autocad_add_hatch` with `pattern="ANSI31"`, then `"AR-CONC"` and `"SOLID"`, round a closed polyline | Each is a real hatch of that pattern (LIST shows the name). Before 2026-10-28 the pattern type sent was 0 (user-defined), which AutoCAD refuses for a named pattern | NOT RUN |
| S5 | `autocad_set_variable(name="LIMMAX", value="42000,29700")` with Admin on; `autocad_drawing_setup(limits=[[0,0],[42000,29700]])` | Both land: LIMMAX reads 42000,29700 in SETVAR. Points now go as an array of doubles; before, the text or a plain pair was sent | NOT RUN |
| S6 | `autocad_purge(target="text_styles")` on a drawing with an unused text style | The style is gone and AutoCAD is back at `Command:`. The answer is now `_ST` (the capitals of "textSTyles"); it was `_STyles` | NOT RUN |
| S8 | A sheet where `(vla-get-PaperSpace (vla-get-ActiveDocument (vlax-get-acad-object)))` throws (seen 2026-11-09 after a viewport hung on a sheet made with Layouts.Add); `autocad_status` | Status answers, `paper_space_entities` from the layout's block (or null), instead of "Exception occurred" | NOT RUN |
| S9 | Same sheet; `autocad_add_viewport(scale='1:25', centre=[...], paper_centre=[338,300], paper_width=560, paper_height=420)` | A viewport is made through MVIEW, aimed and scaled 1:25 and locked, and its handle comes back | NOT RUN |
| S10 | `autocad_run_lisp` with a 2,100-character expression that is one form | Refused at once with "split it", nothing sent to AutoCAD (several forms are cut and sent since D-76: Z2) | NOT RUN |
| S7 | On a UCS turned 23 degrees, with `coords="ucs"`: `autocad_transform_3d` move `[1000,0,0]`, `autocad_slice_solid` `plane="vertical_x"`, `autocad_extrude_profile` revolve about `[1,0,0]`, `autocad_dimension_run` horizontal, `autocad_add_solid` box 1000 x 600 | Each follows the **UCS** X axis (the box's 1000 side runs along it), not the world one. Before 2026-10-28 the points were turned into the world but the directions and the dimension angle were not | NOT RUN |
