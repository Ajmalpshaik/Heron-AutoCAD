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
| F22 | `autocad_render` to a PNG, preset "Low", with Admin on | Either the file appears, or the result says the command line is waiting. **Rendering from a script is reported to drop objects - compare the image with a render done by hand before trusting it** | NOT RUN |
| F23 | `autocad_sequence` with a step naming `autocad_render` | Refused: Admin is above the sequence ceiling | NOT RUN |

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
| J1 | Banner on. `autocad_run_lisp('(command "_.CAMERA")')` so AutoCAD is left at the camera prompt; when the call fails, press Esc. Then `autocad_zoom(mode="extents")` | The zoom's card shows DONE and **closes about 1.4 s later**; it does not stay on screen | NOT RUN |
| J2 | Ten quick reads in a row (`autocad_status` x10) | Each card closes after its DONE; no card is left showing at the end | NOT RUN |
| J3 | `autocad_add_solid` a 500 x 700 x 160 box, then `autocad_fillet_solid_edges(box, radius=60, edges="all")`; also `autocad_list_solid_faces_and_edges(box)` | The box rounded on every edge, volume down; the listing gives 6 faces and 12 edges. No "BoundaryRepresentation.Exception" | NOT RUN |
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
| S7 | On a UCS turned 23 degrees, with `coords="ucs"`: `autocad_transform_3d` move `[1000,0,0]`, `autocad_slice_solid` `plane="vertical_x"`, `autocad_extrude_profile` revolve about `[1,0,0]`, `autocad_dimension_run` horizontal, `autocad_add_solid` box 1000 x 600 | Each follows the **UCS** X axis (the box's 1000 side runs along it), not the world one. Before 2026-10-28 the points were turned into the world but the directions and the dimension angle were not | NOT RUN |
