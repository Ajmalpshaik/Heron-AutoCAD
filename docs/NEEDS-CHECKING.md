# Needs checking - what is built but not yet proven in a real AutoCAD

> A build is not a proof, and a passing offline test is not a proof. A row is **PASS** only after it
> was run in the named AutoCAD and gave the result in the last column. Four states, kept apart:
> **PASS**, **FAIL** (with what happened), **NOT RUN**, **NO MACHINE** (no PC with that version yet).
> Put the date and the AutoCAD version in the result.

**Set-up for every row:** build and install the plug-in (`tools/build_plugin.py`, close AutoCAD,
`tools/install_plugin.py`), start AutoCAD, open a scratch drawing, and connect Claude Code in this
folder.

**Many rows run themselves** (groups D, E, F, M to Z, AA to AS, RV; D-118). With AutoCAD open,
Heron pressed, **Changes on in Settings** and Ask to Keep off:

```bash
.venv\Scripts\python.exe tools/live_check.py --group all --write
```

It reads the padlocks first and stops, saying what to do, if Changes is off or Ask to Keep is on; it
never switches one. It works in scratch drawings it makes itself, *measures* each row (a cone
development's arcs against the girths they roll onto, a 1:100 viewport's CustomScale, a trimmed
line's ends, the first line of a change answer) and writes the answer and its evidence into the last
column here. Rows that need an eye, a click in a Heron window, a restart, the registry or a second
AutoCAD are written **NOT RUN** with the reason; `--list` names them. A row marked
`[needs Admin on]` (or Publish on or off) runs only when that padlock already is so; run again
with the padlocks set that way for those rows. A row the padlocks refuse is **NOT RUN** too, never PASS, and a
NOT RUN reason never overwrites a result already written here.

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
| D8 | `autocad_create_layout(name="D-101", paper_size="A1", plot_style_table="monochrome.ctb")`, then the same with the plug-in turned off (`--no-bridge`) and `activate=false` | New tab; Page Setup shows A1, DWG To PDF, monochrome, scale 1:1; the answer has no `warning`, `page_setup.scale` is `1:1` and `plot_style_table` is there; the returned `sheet` frame matches what PAGESETUP shows. Was **FAIL** 2026-10-28, AutoCAD 2027 (26.0s): five A1 tabs AC-101..105 made, but every call answered `Outcome unknown: AutoCAD went busy` (also with `activate=false`). **Cause found in the code (#40, D-141):** the COM page setup set `CustomScale`, which a layout does not have (its scale is `SetCustomScale`), then centred a layout plot, which AutoCAD refuses (D20); pywin32 answers both `Property ... can not be set`, which the retry reads as busy. Both fixed; the plot style table, written after them, never got there before. Re-run NOT RUN | NOT RUN |
| D9 | `autocad_create_layout(copy_from="D-101")` | The copy carries the page setup | NOT RUN |
| D10 | `autocad_page_setup(all_layouts=true, paper_size="A1", plotter="DWG To PDF.pc3", scale="1:1")` | Every tab changes; only the options passed are different afterwards | NOT RUN |
| D11 | `autocad_page_setup` with a plotter and a sheet size AutoCAD does not have | Named in the error, with the sizes that plotter does offer; the sheet is unchanged | NOT RUN |
| D12 | `autocad_place_title_block` with a real A1 title block, `all_layouts=true`, `per_layout_attributes` | One per sheet, bottom-right inside the ISO frame, right attributes per sheet; `replace_existing` does not stack a second | **PASS** 2026-10-28, AutoCAD 2027 (26.0s), with `layouts=[5 sheets]` (not `all_layouts`) and `anchor="paper"`: one title block per sheet at 831,10, all 9 attributes set per sheet, none missing. `replace_existing` not tried |
| D13 | `autocad_add_viewport(scale="1:100", view_name=...)` | Viewport fills the frame clear of the title block; **measure a known 10 m wall on the plot: 100 mm**; the viewport is locked | NOT RUN |
| D14 | `autocad_add_viewport` with no `scale` and a window | The reported scale is a standard one, the area fits, and the measurement matches that scale | NOT RUN |
| D15 | `autocad_add_viewport(align_to_ucs=true)` on the 23 degree UCS | The plan reads upright on the sheet; nothing falls outside the frame; the reported twist matches. **If it comes out turned the wrong way, the sign of the twist in `_aim` (sheets.py) is inverted — flip it and re-run.** The twist follows VIEWTWIST, which is +23 for a plan view of a UCS turned +23, but that has only been reasoned, not measured. **2026-11-21 (D-90): the sign was flipped from the code (it is now 360 - 23 = 337); run AF6** | NOT RUN |
| D16 | `autocad_add_viewport(paper_centre=..., paper_width=..., paper_height=...)` | The viewport is where those numbers say, in paper units | **PASS** 2026-10-28, AutoCAD 2027 (26.0s): 12 viewports at 1:50, 1:20, 1:10, 1:2 and 1:1; each `paper_rect` matched the centre and size asked and the plotted sheets showed them there, locked |
| D17 | After D13, zoom inside the viewport | Refused / no change: the lock held and the scale is still true | NOT RUN |
| D18 | `autocad_save_view` from a window, then `autocad_list_views` | The corners come back the same; `zoom_to` showed the area | NOT RUN |
| D19 | `autocad_export(area="view", view_name=...)` then `autocad_add_viewport(view_name=...)` | The PDF and the viewport show the **same** area | NOT RUN |
| D20 | `autocad_export(area="layout", scale="1:1")` on the D-101 sheet | The PDF is the sheet, title block and all, at full size; the layout's page setup is put back | **FAIL then fixed, re-run NOT RUN** 2026-10-28, AutoCAD 2027 (26.0s): `Outcome unknown: AutoCAD went busy`, no PDF. Two causes found by hand: setting `CenterPlot` on a layout plot raises, and choosing the plotter drops an A1 layout to ANSI A. `_plot_pdf` now skips `CenterPlot` for `area="layout"` and keeps the layout's own sheet when no `paper_size` is given. **A third, found 2026-11-23 (#40, D-141):** the scale was set as `CustomScale`, which a layout does not have; it is now `SetCustomScale`, so the re-run would have stopped there too |
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
| D33 | With a sheet tab active (after creating layouts and a Save As), `autocad_status`, then `autocad_add_table(space="paper")`; then click into the sheet's viewport (MSPACE) and `autocad_status` again | Status answers with `active_space: "paper"`, `active_layout` the tab on screen and nothing in `unreadable`; the table lands on that sheet; in the viewport, `active_space` is still `"paper"` with `viewport_active: true`. Was **FAIL** 2026-10-28, AutoCAD 2027 (26.0s): both raised a bare `Exception occurred`; status worked again once the Model tab was clicked. **Fixed offline (#39, D-141):** the space and tab come from TILEMODE and CTAB, not COM's ActiveSpace / ActiveLayout (which lagged the tab on 2026-11-22, D-125); `space="paper"` and the sheet count use the block of the sheet CTAB names when COM's layout lags or `doc.PaperSpace` throws; a COM error in the gate's first look is an answer, not a bare exception. Which of these AutoCAD hit is not known: re-run NOT RUN | NOT RUN |

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
| N9 | Open **Settings** (added 2026-11-22, [D-123](DECISIONS.md)) | Five switches; the last is **Ask before keeping erased objects**, green **ON**, its line "After a job erases anything: bring it back, or keep it erased?" | NOT RUN |
| N10 | Press its ON button | A question "Stop asking before keeping erased objects?" with **Keep asking** / **Stop asking**; Keep asking leaves it ON. Stop asking: the button shows OFF, the line says it stays erased without asking, the command line says it is now off | NOT RUN |
| N11 | Question OFF, Ask to Keep OFF: `autocad_delete_entities` on one line, `confirm=true` | No erase box; the line stays erased; the answer starts "DONE - 0 added, 0 changed, 1 erased." and its note says it stays erased **without asking** because the erase question is off in Settings. One Ctrl+Z brings it back | NOT RUN |
| N12 | Close and restart AutoCAD, press Heron, open Settings; then repeat N4 | The question is **ON** again; N4's box appears as before | NOT RUN |
| N13 | In an **administrator** command prompt: `reg add HKLM\SOFTWARE\Policies\Heron\AutoCAD /v AskBeforeErasing /t REG_DWORD /d 0 /f`; restart AutoCAD, press Heron, open Settings; then repeat N11 | The question shows **OFF** with "This PC's administrator setting starts it off."; no erase box; the note says it stays erased without asking because of the administrator setting (AskBeforeErasing), not Settings. Changes, Admin and Publish are NOT shown HELD | NOT RUN |
| N14 | With N13's key still set, press the question's button to turn it ON; repeat N4; restart AutoCAD; then `reg delete HKLM\SOFTWARE\Policies\Heron\AutoCAD /v AskBeforeErasing /f` and open Settings again | After the click N4's box appears; after the restart it is OFF again; after the delete it shows **ON** without a restart | NOT RUN |

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

Rows V1, V4, V6 and V7 were rewritten on 2026-11-23 ([D-142](DECISIONS.md), issue #213): Heron
refuses OPEN, CLOSE and PURGE before sending them, so they could never open the box they tested.
The way in is AutoLISP's alert box through `autocad_run_lisp` (Admin on); `tools/live_check.py`
measures them from the tool's answer. The alert box has only OK, so the watch's press is Esc. Still
NOT RUN: no live run yet. What AutoCAD names that box is read from the answer, not assumed.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| V1 | Admin ON, a drawing open: `autocad_run_lisp('(alert "Heron live check")')` (AutoLISP's alert box is a real modal box opened mid-job; `autocad_send_command("_OPEN")` is refused first, [D-142](DECISIONS.md), #213) | Within about 1 s the box closes by itself; the answer has `heron_dialogs` naming it: "AutoCAD showed '<its title>'; Heron closed it with Esc, nothing was kept from that step." (the box has only OK, so Cancel and No do not exist; **never OK, never Yes**); no timeout; the next call works without pressing Esc | NOT RUN |
| V2 | Open AutoCAD's Options dialog yourself and leave it open; then `autocad_list_layers` | Options is **not** closed; the answer is the Q3 "AutoCAD stayed busy" one; no `heron_dialogs` | NOT RUN |
| V3 | Ask to Keep ON: `autocad_draw_line`, then wait at Keep or Discard for 5 s | The Keep or Discard box stays up until you answer it; it is never closed by the watch | NOT RUN |
| V4 | Admin ON: draw a line (it stays unsaved), then the same alert call as V1 (a "Save changes?" box cannot be opened: `autocad_send_command("_CLOSE")` is refused first, D-142) | The box is closed with Esc, never OK or Yes, and named in `heron_dialogs`; the line is still in the drawing and the same drawing is still open | NOT RUN |
| V5 | With no Heron job running, open the Select File dialog yourself (Ctrl+O) and wait 10 s | It stays open: the watch never acts outside a job | NOT RUN |
| V6 | During V1, look at the add-in log (`%LOCALAPPDATA%\Heron\autocad\logs`, today's `addin-<UTC date>.log`) | One line "dialog watch: '<the box's title>' -> Esc" for that call; no error lines | NOT RUN |
| V7 | Plug-in 1.7.0, Admin on. First V1 (it names the alert box's real title); then `autocad_run_lisp('(alert "Heron live check")', expect_box=<that title>, press="OK")`; then the same with a different `expect_box` title ("PURGE's own box" cannot be opened: `autocad_send_command("_PURGE")` is refused first, D-142) | Heron presses OK on that box only and says "AutoCAD showed '<title>'; Heron pressed OK on it, as this call asked (#101)."; with the other title the alert is still closed with Esc. With Admin off the call is refused before anything is sent (turn Admin off by hand to see it; the runner does not) | NOT RUN |
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
| X7 | Two Heron changes; look at the older one's card | The older card shows **Select** and **Zoom** but no **Undo** (only Heron's newest change can be undone, D-124); the newer card shows all three | NOT RUN |
| X8 | While a long chat job runs (a big batch), press Select and Zoom on an older row | Each refused: "Heron is working on a job right now"; the job is not disturbed. No card shows Undo while the job runs (D-124) | NOT RUN |
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
| X25 | While a chat works in a drawing (sequences, some making multileader and table styles, and batch draws), press **Select** and **Zoom** on its Activity rows | The row's objects are selected; Zoom frames them | Fix in PR for #234 ([D-132](DECISIONS.md)), NOT RUN since the fix: run it with Group AZ. Earlier: **FAIL** 2026-11-22, AutoCAD 2027 (26.0s), plug-in 1.8.0, seen in the add-in log: two Select and one Zoom each logged `eInvalidInput` from `Editor.SetImpliedSelection` (`ShowObjects.cs` line 70) and did nothing; the drawing was not changed. Likely cause: every object the job made is passed, not only entities in the current space ([#234](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/234)) |
| X26 | Publish on. Ask the chat to save the drawing (`autocad_save_drawing`), then to export a PDF | Each card reads "made 0, changed 0, erased 0" and has **no** buttons at all: no Select, Zoom or Undo, and no empty gap under the counts (D-124) | NOT RUN |
| X27 | Ask the chat to erase two lines (if Heron asks about the erase, keep them erased) | The card shows **Undo** only, no Select or Zoom; pressing Undo brings the two lines back | NOT RUN |
| X28 | Draw a circle with the chat, then ask it to save; then ask for a line as a dry run (`dry_run=true`) | The circle's card shows **Select** and **Zoom** but no **Undo** (the save is now Heron's newest job); the save's card has no buttons; the dry run's card reads "dry run, taken back" and has no buttons | NOT RUN |
| X21 | AutoCAD 2025 / 2026 and 2021-2024 builds: X1, X2, X4, X13 | As in AutoCAD 2027 | NO MACHINE |

## Group Y - Attribute sheets, folder checks, the Companion page (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-69](DECISIONS.md), [D-70](DECISIONS.md), [D-71](DECISIONS.md),
[15](15-sheets-folders-companion.md)). Built and tested offline only (`tests/test_attribute_sheet.py`,
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
| AB5 | Turn some layers off and freeze one: `autocad_layer_states(action="save", name="COORD")`; change the layers; `action="restore"`; `autocad_list_layers` | LAYERSTATE dialog shows COORD; restore brings back every layer as saved, and `before_after` lists exactly the layers whose on, frozen or locked state changed (a colour, linetype or other setting the state also puts back is not listed: look at one in the Layer Properties Manager); `list_layers` gives COORD in `layer_states`; saving COORD again without overwrite is refused | NOT RUN |
| AB6 | Current layer 0: `autocad_isolate_layers(handles=[a duct])`, then again with a pipe, then `action="unisolate"`; then with `others="lock"` and `others="freeze"` | Only the duct's layer shows and becomes current; the second isolate keeps the first state (`already_isolated`); unisolate puts every layer and current layer 0 back and HERON-ISOLATE is gone from LAYERSTATE; lock mode greys the others and they cannot be picked; freeze works with the current layer moved first; isolating a frozen layer thaws it and makes it current | NOT RUN |
| AB7 | Layers DUCT (locked, objects in model space, on a layout, inside a block definition and one block attribute) and M-DUCT: `autocad_merge_layers(layers=["DUCT"], into="M-DUCT")`, then with `confirm=true` | First call changes nothing and counts drawing / blocks / attributes right. With `confirm=true` the removed layer DUCT counts as one erased object, so Heron's erase box asks first (D-50): choose **Keep them erased** (Enter brings the DUCT layer back). Then every one is on M-DUCT (also inside the block, the attribute too), DUCT is gone from the layer list; one Ctrl+Z brings it all back | NOT RUN |
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
| AE2 | Inside a room: `autocad_add_camera_view(name='LIVING-CAM-1', eye=[<corner>, 1600], target=[<far wall>, 1200], lens=24)` | The screen shows the room in perspective from the corner. In 2D Wireframe the answer warns instead, and AutoCAD may keep PERSPECTIVE 0 there: switching to `visual_style='realistic'` alone may not bring it back, so record PERSPECTIVE after the switch, and if it reads 0, `-VIEW _Restore LIVING-CAM-1` in Realistic shows the view in perspective; VIEW lists LIVING-CAM-1 as a perspective view; Properties of the view: lens 24 mm. Record AutoCAD's Field of view next to the answer's `field_of_view_degrees` (73.74). One Ctrl+Z removes the view | NOT RUN |
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
| AA3 | A closed rectangle 1000 x 500 and a line across it at x=600; trim with a point on its right side. Then a circle r=100 with a line through its centre, trim one half | The rectangle is one open polyline round the left part; the circle is replaced by a half arc with its look, and Heron asks "Keep the change, or undo the whole change?" (D-136, Group BC: answer Keep the change here) | NOT RUN |
| AA4 | Three short lines below a long "main" line; `autocad_trim_extend` extend, no points. Then an arc 0 to 90 degrees and a line beyond its end | Each short line now ends on the main; the arc runs on round its circle to the line; nothing else moved | NOT RUN |
| AA5 | A polyline with a constant width of 20, trimmed; then one whose width tapers (start 0, end 20), trimmed | The first keeps width 20 on every piece; the second is refused ("width changes along it") and nothing changes | NOT RUN |
| AA6 | Two lines meeting at a square corner (not touching). `autocad_fillet_chamfer` fillet, radius=150; then two more with radius=0 | An arc r=150, tangent to both (AutoCAD's own FILLET with the same radius gives the same arc), on the first line's layer; radius 0 gives a sharp corner and no arc | NOT RUN |
| AA7 | Chamfer two lines distance=50, distance2=30; then distance=50, angle=30 | Measured with `autocad_measure`: 50 and 30 back from the corner; the angle method gives 50 and 28.87 on a square corner, matching AutoCAD's CHAMFER Angle | NOT RUN |
| AA8 | A closed polyline 1000 x 500: fillet with radius=50, no vertices | One polyline, 8 vertices; `autocad_polyline_info` area = 500000 - (4 - pi) x 50^2 = 497853.98 | NOT RUN |
| AA9 | `autocad_break_curve` on a line at a point; on a line with second_point; on a circle with two points | Two touching lines; two lines with the gap; the circle is an arc missing the part from the first point anticlockwise to the second | NOT RUN |
| AA10 | Two lines and an arc drawn end to end (the arc in the middle, drawn in any direction): `autocad_join_curves`. Then two lines in one straight line | One polyline with the arc kept as an arc (a bulge), on the first object's layer; the others erased after the modeller answers Keep the change (D-136). The two straight lines become one line | NOT RUN |
| AA11 | A 4-vertex polyline: `autocad_edit_vertex` move vertex 2 by [0, -200]; add a vertex after 0; remove it again. A line: move its end with `near` | Each change as asked, the arcs next to a moved vertex still arcs; a line end goes exactly to to_point | NOT RUN |
| AA12 | A rectangle, a door block on its right side, a hatch half over the right side, a circle far away: `autocad_stretch` with a window round the right side, displacement [600, 0] | Right side of the rectangle 600 longer; the door moved whole; the hatch listed in `skipped` and unmoved; the circle `untouched`. A polyline with different widths per segment, stretched: record whether its widths stay | NOT RUN |
| AA13 | `autocad_explode` on a plain block, then on a block with attributes, then the same with allow_attribute_loss=true | The plain block: its lines are separate objects and the block reference is gone (check it is not left under the pieces), Heron asks "Keep the change, or undo the whole change?" (D-136, Group BC: answer Keep the change here); the attributed one skipped with its values; then exploded with the values listed | NOT RUN |
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
| AC3 | After AC1, insert VALVE TAG three more times, type TAG values V-102..V-104. In the Block Editor add a FLOW attribute and delete SIZE, save. `autocad_sync_attributes(block='VALVE TAG', dry_run=true)`, then without | Dry run: 4 inserts, each keeps its TAG, gains FLOW, loses SIZE; drawing unchanged. Without it, each insert's dropped SIZE counts as an erased object, so Heron's erase box asks first (D-50): choose **Keep them erased** (Enter brings the SIZE attributes back). Then each insert shows its own V-10x still, FLOW with its default, no SIZE (ATTEDIT); one Ctrl+Z undoes it all | NOT RUN |
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
| AC17 | After AC3, make a SKID block holding one VALVE TAG insert, insert SKID twice. Change VALVE TAG's definition again; `autocad_sync_attributes(block='VALVE TAG', nested=true, dry_run=true)`, then without (#156) | The dry run lists the insert inside SKID with `"inside": "SKID"`; after the sync both SKID copies show the nested tag with its new attributes and its typed value kept; without `nested` it is not listed | NOT RUN |

## Group AF - Sheets by the plug-in: layouts, viewports, clip, annotation scale, drawing list, PDF of many drawings (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-90](DECISIONS.md), [D-91](DECISIONS.md); issues #64-#67, #39, #40). Built and
tested offline only (`tests/test_sheets_plugin.py`, `tests/test_sheet_arithmetic.py`,
`SheetMathTests.cs`); the add-in **compiles** for all three AutoCAD builds. Needs the plug-in built
from this change (three new operations, and `publish_pdf` taking drawings) and a server restart.
Use a drawing with saved views of a plan, a title block with DWG_NO / TITLE / SCALE attributes, and a
folder of three small saved drawings, one with an xref. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AF1 | `autocad_create_layout(name="AF-101", paper_size="A1", plot_style_table="monochrome.ctb")` (row D8 again) | Answers at once with `made_by: "plugin"` and no "Outcome unknown"; the AF-101 tab is on screen; Page Setup shows DWG To PDF, ISO full bleed A1, Layout, 1:1, monochrome.ctb; the sheet has **no** viewport of AutoCAD's own; the answer's `frame` matches PAGESETUP; one Ctrl+Z removes the tab | NOT RUN |
| AF2 | Five calls with `activate=false` (AF-102..106) | Five tabs, every answer `created: true`, none busy; the tab on screen does not change | NOT RUN |
| AF3 | `autocad_create_layout(name="AF-107", copy_from="<a sheet with a title block and a viewport>")` | AF-107 has the same title block and viewport (CopyLayout), and its page setup is DWG To PDF A1 | NOT RUN |
| AF4 | `paper_size="A7"`; then `plotter="No Such.pc3"`; then `plot_style_table="none.ctb"` | Each refused in words naming what the plotter does have; no tab is left behind | NOT RUN |
| AF5 | On AF-101: `autocad_add_viewport(view_name="<plan>", scale="1:100", title_block_width=180, layer="G-VPRT")` | `made_by: "plugin"`; Properties: Custom scale 1:100, Display locked Yes, layer G-VPRT; the saved view's centre is in the middle of the viewport; the status bar's annotation scale in it is 1:100; nothing scrolls when you zoom inside | NOT RUN |
| AF6 | On a UCS turned 23 degrees: `autocad_add_viewport(..., align_to_ucs=true)`; then `twist=-23` on a world UCS | Both answers say `twist_degrees: 337`; the plan drawn on the 23 degree grid reads square on the sheet, and the viewport still looks at the same centre. **The sign changed in this PR** (D-90: it was +23, which by the view-centre rule turns the plan 46 degrees off). If it now reads 46 degrees off, the reasoning is wrong: flip it back in `make_viewport` and in `SheetMath.ViewCentre` together, and re-run AF5 too | NOT RUN |
| AF7 | Draw an L-shaped closed polyline on AF-101; `autocad_add_viewport(..., clip_handle="<its handle>")`; then `clip_outline=[[50,50],[250,50],[250,130],[130,130],[130,200],[50,200]]` | Both viewports show the plan only inside the L (as VPCLIP); the second draws the outline on the viewport's layer; Properties: Clipped Yes; one Ctrl+Z removes each viewport with its outline | NOT RUN |
| AF8 | `autocad_add_viewport(..., scale="1:75")` in a drawing whose scale list has no 1:75; an annotative text 2.5 mm in the plan | The answer says `annotation_scale_added: true`; SCALELISTEDIT shows 1:75; the text shows 2.5 mm high on the paper in that viewport | NOT RUN |
| AF9 | `autocad_sheet_set(sheets=[3 rows: one view at 1:100, one view with no scale, one cover], title_block="<block>", title_block_width=180, attributes={"PROJECT": "AF"})`; then one Ctrl+Z; then again with Ask to Keep on and Discard | Three tabs named by number, each with its title block filled (number, title, the fitted scale on the second), viewports at the scales said; **one** Ctrl+Z takes all three sheets back (the plug-in's steps are inside Heron's undo mark); Discard does the same. If Ctrl+Z takes them back one by one, D-90's one-undo-step claim fails | NOT RUN |
| AF10 | With a sheet tab active (rows D33 and S8 again): `autocad_status`, then `autocad_add_table(space="paper", ...)` | Status answers with `active_space: "paper"`, `active_layout` the tab, no `unreadable`; the table lands on the sheet; if `doc.PaperSpace` throws, the table still lands (the layout's block) | NOT RUN |
| AF11 | With the plug-in from before this change: `autocad_create_layout` and `autocad_add_viewport(... clip_outline=...)` | The layout and a plain viewport are made over COM (`made_by: "com"`, `plugin_note` says why); the clipped one is refused with nothing made; a busy moment answers "the sheet is made ... check it" instead of "Outcome unknown" | NOT RUN |
| AF12 | `autocad_publish_pdf(path="<folder>\set.pdf", folder="<folder of 3 saved drawings>")` | One PDF, the drawings in name order (M-2 before M-10), each drawing's sheets in tab order, none blank; `pages` lists them; nothing in any drawing changes | NOT RUN |
| AF13 | Open one of them, change something, do not save; publish the folder again | Refused before anything is plotted, naming that drawing and "unsaved changes"; no PDF written | NOT RUN |
| AF14 | Rename the xref file of one drawing; publish the folder; then unload that xref in the drawing, save, publish | First refused naming the drawing and the xref; second publishes, the sheet without the unloaded xref | NOT RUN |
| AF15 | `drawings=[<C>, <A>]` with C the active, saved drawing | The PDF has C's sheets first, then A's | NOT RUN |
| AF16 | AF1-AF15, AF17 and AF18 on AutoCAD 2025/2026 and 2021-2024 | As those rows | NOT RUN (no PC with those versions yet) |
| AF17 | `autocad_create_layout(name="AF-ANSI", plotter="DWG To PDF.pc3", paper_size="ANSI D")` in a drawing from acad.dwt (inch paper units); then a sheet copied from a template whose page setup plots at 90 degrees | The answer's `paper` is 34 x 22 (inches, not 863.6 x 558.8) and the frame matches PAGESETUP; on the turned sheet the frame is the right way round. If either is 25.4 times too big or swapped, the plug-in's paper read (`SheetMath.PaperInUnits`) is wrong | NOT RUN |
| AF18 | A drawing whose xref has its own xref (nested); rename the nested one's file; publish the folder | Refused naming `<xref>|<nested>`; put the file back and it publishes | NOT RUN |
| AF19 | D-125, the SAC2 set (2026-11-22). **Server restarted, plug-in 1.8.0 still installed:** on a sheet made by `autocad_create_layout`, `autocad_add_viewport(centre=[2000,1000], scale="1:25")`, first with `dry_run=true`, then for real. **Then with a plug-in built from this change:** the same call | 1.8.0: `made_by: "com"`, `plugin_note` names eInvalidInput, the viewport is there at 1:25 and locked. New plug-in: `made_by: "plugin"`, no eInvalidInput in `%LOCALAPPDATA%\Heron\autocad\logs`, Properties shows Custom scale 1:25. If the new plug-in still refuses, the next suspects are `annotation_scale` (try `annotation_scale="none"`) and `locked` (try `locked=false`): record which call passes | NOT RUN |
| AF20 | **Before making any SAC2 PDF:** open Page Setup (PAGESETUP) on SAC2-101 to SAC2-104 and write down Paper size and Drawing orientation; look whether each sheet's white paper is wide or tall | Record it. On 2026-11-22 the plug-in said those sheets plot turned 90 degrees on the 841 x 594 medium. Either way, `autocad_page_setup(layouts=[...], orientation="landscape")` now takes the turn off (0 degrees): do it on one sheet, look that its frame and title block still sit on the paper, then the others. If the paper looked **tall** before, the plug-in's read was right and the COM read (`_paper_of`) must swap a turned sheet: record it for AF21 | NOT RUN |
| AF21 | With this change: `autocad_create_layout(name="AF-201", paper_size="A1", orientation="landscape")` in a drawing from acad.dwt; then `autocad_page_setup(layouts=["AF-201"], orientation="portrait")`; then `orientation="landscape"` | First answer: `plot_rotation` 0 (or `plot_rotation_was: 90` with plug-in 1.8.0), `sheet.orientation` landscape, paper [841, 594], frame [20,10,831,584], no warning; the paper on screen is wide. After portrait: paper [594, 841] and the white paper is tall; after landscape, wide again. **If the paper on screen ever disagrees with the answer, the turn rule is wrong (the plug-in's `SheetMath.PaperInUnits` swaps a turned sheet's sides, the COM `_paper_of` does not; one of them must change): record the medium, the drawing orientation in Page Setup and which way the paper looks** | NOT RUN |
| AF22 | `autocad_create_layout(name="AF-202", paper_size="A1")` (activated), then without touching anything `autocad_preview()` and `autocad_export(format="pdf")` | Both show AF-202, not the sheet before it; if COM was behind, the answers carry `layout_note` naming both sheets | NOT RUN |
| AF23 | On a sheet set with two layouts and viewports: `autocad_run_lisp('(setvar "CTAB" "<the other sheet>")')`, with the new plug-in | NOTHING CHANGED (or 0 erased), and **no** erase question. Then one `run_lisp` that switches the tab **and** `entdel`s a line: the line **is** counted and the erase question comes. Then erase one floating viewport by `run_lisp` (`entdel`) with no tab switch: it is counted too. If the tab switch still says 1 erased, run `(entget (handent "<handle>"))` on the handle the answer names and record what it is (a viewport with `(69 . 1)` is the sheet's own) | NOT RUN |
| AF24 | Draw two polylines on layer M-COND-DET (green, colour ByLayer); `autocad_make_block` them; `autocad_list_entities` inside the block, then `autocad_preview(area="window")` close round it | Both members are still on M-COND-DET, colour ByLayer (green). If one shows grey only in the small preview but green in AutoCAD, it is the preview's thin line, not the block | NOT RUN |

## Group AS - Reads the plug-in does in one go: the entity summary and a layer's extents (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-114](DECISIONS.md), issue #74). Built and tested offline only
(`tests/test_plugin_reads.py` compares the plug-in and COM answers on one fake drawing;
`EntityReadsTests.cs` the plug-in's counting and filter). The plug-in operations `count_entities` and
`entity_extents` build for all three targets but have never run. Needs the plug-in rebuilt and
reinstalled at **1.8.0 or newer** (an older one is read over COM), and the server restarted. "Over
COM" below means the same call to a second server started with `--no-bridge` (developer use: it
reads over COM only); the plug-in's log (`%LOCALAPPDATA%\Heron\autocad\logs`) shows
`operation count_entities` / `operation entity_extents` when the plug-in read it. **Every row below
is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AS1 | A real project drawing with model space and two sheets (title blocks, viewports). `autocad_list_entities(summary_only=true)`, then the same over COM | The log shows `operation count_entities`; `total_matching`, `by_type` and `by_layer` are the same both ways, key order too, paper-space objects (viewports, title blocks) included in both | NOT RUN |
| AS2 | Same drawing: `summary_only=true` with `layer='M-*'`, `layer='m-duct'` (other case), `entity_type='dimension'`, `block_name='<a block>'`, `color='red'`, and a layer that does not exist | Each the same as over COM; the missing layer is a count of 0, not an error | NOT RUN |
| AS3 | A drawing with 20,000 or more objects: time `autocad_list_entities(summary_only=true)` with the plug-in and over COM | Same answer; write both times in the result. Pass: the plug-in is clearly faster | NOT RUN |
| AS4 | `autocad_get_extents(layer=<a layer with lines, text, a block and a 3D solid>)`, then over COM | The log shows `operation entity_extents`; `min`, `max`, `width`, `height`, `center` and `entity_count` are the same to the last digit | NOT RUN |
| AS5 | A layer holding one XLINE and one RAY: `autocad_get_extents(layer=...)` both ways; and a layer with nothing on it | Both: "has 2 object(s), but none with extents"; the empty layer: "has no geometry", as before | NOT RUN |
| AS6 | Draw a line yourself, run AS1 and AS4, then press Ctrl+Z once | The Ctrl+Z takes away **your line**: the reads left no undo step (the plug-in's transaction is aborted; COM's reused selection set adds none) | NOT RUN |
| AS7 | Install plug-in 1.7.0 (or any older one), run AS1 and AS4 | Both answer over COM (no `operation` line in the log), no error, the same answers as with 1.8.0 | NOT RUN |
| AS8 | Select two objects yourself, run AS1, then type SELECT and P (previous) | Note what is selected before and after, with the plug-in and over COM; Pass: the read does not leave AutoCAD's own selection or "previous" set different from what COM leaves | NOT RUN |
| AS9 | Start LINE and leave it waiting for a point; run AS1 | The read answers, or gives the busy answer naming LINE; no error box; LINE is still waiting | NOT RUN |
| AS10 | The AS1 drawing: `autocad_drawing_report()`, then the same over COM (#193) | The log shows `operation count_entities`; `model_space` (`total`, `by_type`, key order too) is the same both ways, and counts model space only (not the sheets' title blocks) | NOT RUN |
| AS11 | A drawing with more than 50,000 objects in model space: `autocad_drawing_report()` both ways, timed | The same `total`, `by_type` and "Only the first 50,000" note both ways; write both times in the result | NOT RUN |

## Group AU - Block counts the plug-in reads in one go: count_blocks and list_blocks (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-127](DECISIONS.md), issues #192 and #194). Built and tested offline only
(`tests/test_plugin_block_reads.py` compares the plug-in and COM answers on one fake drawing;
`BlockTallyTests.cs` what the plug-in writes). The plug-in operations `block_references` and
`block_definitions` build for all three targets but have never run. Needs the plug-in rebuilt and
reinstalled from code that has them (plug-ins 1.8.0 and 1.8.1 do not: they are read over COM), and
the server restarted. "Over COM" means the same call to a second server started with `--no-bridge`,
as in Group AS; the plug-in's log shows `operation block_references` / `operation block_definitions`
when the plug-in read it. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AU1 | A real MEP plan with dynamic valves or diffusers (some changed, so AutoCAD renamed them `*U..`): `autocad_count_blocks()` and `autocad_count_blocks(group_by='name_layer', layer='M-*')`, then the same over COM | The log shows `operation block_references`; `total` and `rows` are the same text both ways; the `*U` copies count under the block's own name | NOT RUN |
| AU2 | Same drawing: `autocad_count_blocks(group_by='name_properties')` and `group_by='name_visibility'`, both ways | The same rows both ways; a whole-number size shows as `50.0` in both (never `50`), a flip state as `0` or `1`, a list choice as its text | NOT RUN |
| AU3 | A drawing with blocks inside blocks (desks inside a room block): `autocad_count_blocks(include_nested=true)` both ways | The same `total` and rows; the nested desks counted once per placed room, in both | NOT RUN |
| AU4 | `autocad_list_blocks()`, `include_unused=true` and `include_counts=false`, both ways, on a drawing with an xref, a block with attributes and a dynamic block | The log shows `operation block_definitions`; the same text both ways: `instances` by real name, the xref's `path`, `attribute_tags` in order, `dynamic` | NOT RUN |
| AU5 | Plug-in 1.8.1 installed (it has no block reads): run AU1 and AU4 | Both answer over COM (no `operation block_...` line in the log), no error, the same answers as with the new plug-in | NOT RUN |
| AU6 | A drawing with 5,000 or more block references: time `autocad_count_blocks(group_by='name_properties')` and `autocad_list_blocks()` with the plug-in and over COM | Same answers; write both times in the result. Pass: the plug-in is clearly faster | NOT RUN |
| AU7 | A MINSERT, a block placed on a sheet (layout) and an xref: `autocad_count_blocks()` and `autocad_list_blocks()` both ways | Each is counted the same both ways (the sheet's block included in both) | NOT RUN |
| AU8 | Draw a line yourself, run AU1 and AU4, then press Ctrl+Z once | The Ctrl+Z takes away **your line**: the reads left no undo step | NOT RUN |

## Group BD - Tool bugs found by the live-check runner (D-137) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-137](DECISIONS.md); issue #218). Built and tested offline only
(`tests/test_preview_extents.py`, `tests/test_tables.py`, `tests/test_attribute_sheet.py`,
`tests/test_drawing_copy.py`, `tests/test_plugin_tools.py`, `tests/test_draw_extra.py`; bridge test
`JobChangesTests.cs`). **Nothing here has run in AutoCAD.** The plug-in changed (the change count): build
and install it, then restart the server. Changes on, Ask to Keep off, the erase question on. A scratch
drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BD1 | A closed outline about 3000 x 2400 and a tile .dwg **not yet attached**: `autocad_super_hatch(boundary=<it>, xref="<the .dwg>", spacing=[20, 20])` (too many tiles), **not** a dry run | REFUSED naming the tile count and the limit; **no** Heron erase box opens in AutoCAD (before this, the xref detached on the refusal counted as an erased object); External References does not list the .dwg; `addin-*.log` shows no erase asked for that job | NOT RUN |
| BD2 | `autocad_create_layer(name="LC-BD2")`, then in a second call `autocad_purge` (or `autocad_delete_layer`) of LC-BD2 | The second call still raises the erase box about the layer: a layer made in an **earlier** job is an erase as before. Choose Keep them erased | NOT RUN |
| BD3 | In `autocad_set_3d_view(direction="sw_iso")`: `autocad_preview(area="window", corner1=[0,0], corner2=[5000,4000], detail=2)`; then again in a plan view of the world UCS | In the iso view: one picture, `detail_skipped` names the plan view, no close-ups. In plan: the window and four close-ups, as AM rows | NOT RUN |
| BD4 | In Excel on a PC whose list separator is `;` (or a CSV typed by hand: `TAG;FLOW;NOTE`, then `F-01;2,5;"kitchen; roof"`): save as CSV, then `autocad_table_from_excel(path=<it>, position=[0,0])` | Three columns, not one: F-01, 2,5 and kitchen; roof in their own cells; the comma in 2,5 kept as typed | NOT RUN |
| BD5 | The AC14 drawings: `autocad_copy_from_drawing(source='pump-room', handles=[<a layer's handle in pump-room.dwg, from autocad_list_layers>], base_point=[0,0])`; then with the skid's handle, `dry_run=true` | The first is refused: the handle is "not a drawn object" (named with its type), nothing copied. The dry run lists `source_objects` with the skid's type (AcDbBlockReference) and layer | NOT RUN |
| BD6 | `autocad_super_hatch(boundary=<it>, block=<a tile block>, layer="L\|PAVE")`, then with a real line break in the layer name | Each refused at once naming the layer name; nothing is made and no layer appears | NOT RUN |

## Group BF - Names refuse control characters (D-139) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-139](DECISIONS.md); issue #249). Built and tested offline only
(`tests/test_offline.py` `TestNameValidation`). **Nothing here has run in AutoCAD.** Server only (restart
the server). Changes on. Use a scratch drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BF1 | `autocad_create_layer(name="A\nB")` (a real line break), then with a real tab and a real Esc | Each is refused at once: "The layer name holds a line break (a tab, an Esc character), which cannot be typed into AutoCAD's command line ... Nothing was typed."; no layer is made | NOT RUN |
| BF2 | `autocad_create_layer(name="A-WALL")`, then `autocad_create_styles` with a text style named `TXT-1` | Both made as before | NOT RUN |

## Group BB - Lengths and texts the plug-in reads in one go: total_length, measure, count_text, find_text (D-134) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-134](DECISIONS.md), issues #195 and #197). Built and tested offline only
(`tests/test_plugin_length_text_reads.py` compares the plug-in and COM answers on one fake drawing;
`EntityFactsTests.cs` what the plug-in writes). The plug-in operations `entity_lengths` and
`entity_texts` have never run. Needs the plug-in rebuilt and reinstalled from code that has them
(plug-ins 1.8.0 and 1.8.1 do not: they are read over COM), and the server restarted. "Both ways" means
the same call to a second server started with `--no-bridge`, as in Groups AS and AU; the plug-in's log
shows `operation entity_lengths` / `operation entity_texts` when the plug-in read it. "The same text"
means the two answers compared character by character. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BB1 | A real MEP plan: `autocad_total_length(layer='M-*')`, `group_by='type'` and `group_by='none'`, both ways | The log shows `operation entity_lengths`; the same text both ways, every length and area **to the last digit** | NOT RUN |
| BB2 | A drawing with a line, an open and a closed polyline, an old-style 2D polyline, an open and a closed 3D polyline, an arc and a circle: `autocad_total_length(group_by='type')` both ways | The same text; the closed 3D polyline has no area in either (COM has no Area for it), the circle's area is in both, the open polyline's area in neither | NOT RUN |
| BB3 | A spline (fit-point and control-point, one rational), a full ellipse and an elliptical arc: `autocad_total_length(group_by='type')` both ways | The same text to the last digit (both measured by the server from the definition); the full ellipse has no area in either | NOT RUN |
| BB4 | A layer holding lines, a circle, an open polyline, an arc, an ellipse, a hatch, text and a block: `autocad_measure(layer=...)` both ways | The same text: `total_length` (no circumference), `total_area` (the open polyline, arc, ellipse and hatch areas in), `counted_length`, `counted_area`, `by_type` in the same order | NOT RUN |
| BB5 | A layer with a surface, a mesh or another class D-134's table does not list: `autocad_measure(layer=...)` with the plug-in | No `operation entity_lengths` answer is used (the log shows the call, the tool reads over COM): the same answer as `--no-bridge` | NOT RUN |
| BB6 | A plan with left- and centre-justified text, mtext with formatting (bold, a font, `\P` line breaks, stacked fractions, a field) and blocks with attributes, one a changed dynamic block: `autocad_find_text(query=...)` for a word in each, both ways, also with `limit=1` and `include_attributes=false` | The log shows `operation entity_texts`; the same text both ways: mtext with its codes, positions (the centred text's too: COM's InsertionPoint against .NET's Position), the `*U` block name, the same first match under `limit=1` | NOT RUN |
| BB7 | Same plan: `autocad_count_text()`, `source='attributes', tag='SIZE'`, `pattern='^DN'`, `normalise=false`, `sum_numeric=true`, both ways | The same text both ways, `sum` included | NOT RUN |
| BB8 | A block with a multiline attribute and one with a constant attribute: `autocad_count_text(source='attributes')` with the plug-in; then check over COM what `GetAttributes` gives for each | With the plug-in the tool reads over COM (D-134 does not trust these yet): the same answer as `--no-bridge`. Write down whether COM's TextString of the multiline attribute matches its .NET `TextString`, and whether a constant attribute is in `GetAttributes` | NOT RUN |
| BB9 | A block whose attribute definitions were deleted from the block after insert (the attributes stay on the reference): `autocad_count_text(source='attributes')` both ways | The same text: COM's `HasAttributes` agrees with the attributes the plug-in found | NOT RUN |
| BB10 | Plug-in 1.8.1 installed (no length or text reads): BB1, BB4, BB6 and BB7, then on a plan with 20,000 texts and 20,000 curves time `autocad_find_text(query='zzz')` and `autocad_total_length()` with the new plug-in and over COM; then draw a line yourself, run them all, press Ctrl+Z once | 1.8.1 answers over COM with no error and the same text; the new plug-in is clearly faster (write both times); the Ctrl+Z takes away **your line** | NOT RUN |

## Group BE - Block attributes the plug-in reads in one go: extract, export sheet, set, apply sheet (D-138) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-138](DECISIONS.md), issue #198). Built and tested offline only
(`tests/test_plugin_attribute_reads.py` compares the plug-in and COM answers on one fake drawing;
`BlockAttributeFactsTests.cs` what the plug-in writes). The plug-in operation `block_attributes` has
never run. Needs the plug-in rebuilt and reinstalled from code that has it (plug-ins 1.8.0 and 1.8.1
do not: they are read over COM), and the server restarted. "Both ways" means the same call to a second
server started with `--no-bridge`, as in Groups AS, AU and BB; the plug-in's log shows
`operation block_attributes` when the plug-in read it. "The same text" means the two answers compared
character by character. Work on a copy of the drawing for the writing rows. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BE1 | A real drawing with title blocks on several layouts and tagged equipment in model space: `autocad_extract_attributes()`, then `output='csv'`, both ways | The log shows `operation block_attributes`; the same text both ways, rows in the same order, insertion points to the last digit | NOT RUN |
| BE2 | Same drawing, with a changed dynamic block (a `*U` copy) and a block whose name has lower-case letters: `autocad_extract_attributes(block_name=...)` with the name in another case, and `layer='E-*'`, both ways | The same text; the dynamic block listed under its real name in both | NOT RUN |
| BE3 | The drawing saved: `autocad_export_attribute_sheet()` both ways | Two workbooks with the same rows on 'Attributes' and 'As exported'; each title block's Layout column names its own sheet, model space blocks say `Model` | NOT RUN |
| BE4 | `autocad_set_attributes(values={'REV': 'B'}, block_name=<the title block>, dry_run=true)`, then without `dry_run`, with the plug-in; the same on a second copy with `--no-bridge` | The log shows `operation block_attributes`; the same text both ways; the dry run changes nothing; the write lands on every sheet and one Ctrl+Z takes all of it back | NOT RUN |
| BE5 | Edit two cells of BE3's workbook in Excel and save: `autocad_apply_attribute_sheet(path=..., dry_run=true)`, then without, both ways (each on its own copy) | The same text both ways; only the two edited cells written, one undo step | NOT RUN |
| BE6 | A block with a multiline attribute and one with a constant attribute: `autocad_extract_attributes()` with the plug-in, then `block_name=` a third block | First: the tool reads over COM (the log shows the call, the answer matches `--no-bridge`). Second: the plug-in's answer is used. Write down whether COM's `GetAttributes` lists the constant attribute and what its `TextString` gives for the multiline one | NOT RUN |
| BE7 | A block whose definition holds only constant attribute definitions, and one whose attribute definitions were deleted after it was inserted (no ATTSYNC): `autocad_extract_attributes()` with the plug-in | The tool reads over COM, the same answer as `--no-bridge`. Write down what COM's `HasAttributes` says for each: does it follow the definition or the attributes on the reference? | NOT RUN |
| BE8 | A block with an invisible attribute: `autocad_extract_attributes()` and `autocad_export_attribute_sheet()` both ways | The invisible attribute is listed both ways, with its value | NOT RUN |
| BE9 | Plug-in 1.8.1 installed (no `block_attributes`): BE1 and BE4; then on a plan with 2,000 tagged blocks time `autocad_extract_attributes()` with the new plug-in and over COM; then draw a line yourself, run BE1, press Ctrl+Z once | 1.8.1 answers over COM with no error and the same text; the new plug-in is clearly faster (write both times); the Ctrl+Z takes away **your line**: the read left no undo step | NOT RUN |
| BE10 | A title block whose attributes hold fields (a sheet number, a date, the file name): `autocad_extract_attributes(block_name=...)` both ways, then `autocad_set_attributes(values={'REV': 'B'}, dry_run=true)` both ways | The same text both ways: .NET's `TextString` of a field attribute matches COM's (the field's shown value), so no field is planned as a change it is not | NOT RUN |

## Group BK - Attribute writes made by the plug-in in one transaction: set attributes, apply sheet (D-148) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-148](DECISIONS.md), issue #200). Built and tested offline only
(`tests/test_plugin_attribute_writes.py` runs both tools both ways over one fake drawing and compares the
answers and the attributes left; `AttributeWritesTests.cs` what the plug-in reads and answers). The
plug-in operation `write_attributes` has never run. Needs the plug-in rebuilt and reinstalled from code
that has it (plug-ins 1.8.0 and 1.8.1 do not: the writes go over COM), and the server restarted. "Both
ways" means the same call on a second copy of the drawing to a second server started with
`--no-bridge`; the plug-in's log shows `operation write_attributes`. Work on copies of a real drawing.
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BK1 | Title blocks on several sheets: `autocad_set_attributes(values={'REV': 'B'}, block_name=<the title block>)` both ways | The log shows `operation write_attributes`; the same text both ways; every sheet's REV is B; one Ctrl+Z takes all of it back | NOT RUN |
| BK2 | The same with Ask to Keep on, both ways | Keep or Discard asks once; write down the count of changed objects both ways (the plug-in's transaction and COM's writes may count the block references differently); Discard takes every cell back | NOT RUN |
| BK3 | Export a sheet (`autocad_export_attribute_sheet`), edit two cells and blank a third in Excel, save: `autocad_apply_attribute_sheet(path=...)` both ways | The same text both ways: only the two edited cells written (D-69), the blank one left; one undo step | NOT RUN |
| BK4 | A title block whose REV attribute is centred or right-aligned: BK1 with a longer value | The new text sits on the same alignment point both ways (the plug-in's `AdjustAlignment` as COM's TextString) | NOT RUN |
| BK5 | A title block whose attribute holds a field (the file name): `autocad_set_attributes` on that tag with the plug-in | The plug-in refuses it as a field and the cells are written over COM (the log shows both); write down what COM's write did to the field | NOT RUN |
| BK6 | A sheet edited on a copy where one block's layer is then locked: `autocad_apply_attribute_sheet(path=...)` with the plug-in, then `--no-bridge` | With the plug-in: the answer says that block would not take the cell and "Nothing was changed"; no attribute changed, no undo step. Over COM: that cell under `failed`, the rest written | NOT RUN |
| BK7 | Plug-in 1.8.1 installed (no `write_attributes`): BK1 and BK3; then on a plan with 2,000 tagged blocks time a 2,000-cell `autocad_set_attributes` with the new plug-in and over COM | 1.8.1 answers over COM with no error and the same text; the new plug-in is clearly faster (write both times) | NOT RUN |

## Group BJ - The layer merge read and made by the plug-in: one transaction, all or none (D-147) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-147](DECISIONS.md), issue #199). Built and tested offline only
(`tests/test_plugin_merge_layers.py` runs the merge both ways over one fake drawing and compares the
answers and the drawings left; `LayerMergeTests.cs` what the plug-in reads and writes). The plug-in
operations `layer_objects` and `merge_layers` have never run. Needs the plug-in rebuilt and reinstalled
from code that has them (plug-ins 1.8.0 and 1.8.1 do not: the merge goes over COM), and the server
restarted. "Both ways" means the same call on a second copy of the drawing to a second server started
with `--no-bridge`; the plug-in's log shows `operation layer_objects` and `operation merge_layers`. Work
on copies of a real drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BJ1 | A real drawing with two layers to merge, holding objects in model space, on a sheet, inside block definitions and as block attributes, one of them locked and current: `autocad_merge_layers(layers=[...], into=...)` (no `confirm`) both ways | The log shows `operation layer_objects`; the same text both ways, the same counts per layer and place | NOT RUN |
| BJ2 | The same with `confirm=true`, Ask to Keep on, both ways | The log shows `operation merge_layers`; the same text both ways; every object on the new layer, the old layers gone, the new layer current. Keep or Discard asks once and counts the same number of changed objects both ways (write both); Discard takes all of it back, the layers too | NOT RUN |
| BJ3 | Merge again on a fresh copy and press Ctrl+Z once | One Ctrl+Z puts every object back on its old layer, the old layers back (the locked one locked) and the old current layer current | NOT RUN |
| BJ4 | An old layer frozen in a sheet's viewport only (VP Freeze), and one named in a layer filter: merge both ways | Write down which layers each way removes and which it keeps: the plug-in asks AutoCAD's purge, COM tries Delete; a kept one is locked again if it was | NOT RUN |
| BJ5 | An object AutoCAD will not move (a proxy object from another application on an old layer, if one can be had): merge with the plug-in, then `--no-bridge` | With the plug-in: the answer says that object would not move and "Nothing was changed"; nothing in the drawing moved, no undo step. Over COM: the object is under `failed`, its layer kept, the rest moved | NOT RUN |
| BJ6 | A block whose attribute definitions were deleted after it was inserted (no ATTSYNC), an attribute on an old layer: merge (no `confirm`) with the plug-in | The read goes to COM (the log shows `layer_objects`, the answer matches `--no-bridge`); write down whether COM's read listed that attribute | NOT RUN |
| BJ7 | Plug-in 1.8.1 installed (no `layer_objects` or `merge_layers`): BJ1 and BJ2; then on a plan with 50 block definitions and 20,000 objects on the old layers, time BJ2 with the new plug-in and over COM | 1.8.1 answers over COM with no error and the same text; the new plug-in is clearly faster (write both times) | NOT RUN |
## Group BI - The standards check's object facts the plug-in reads in one go (D-145) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-145](DECISIONS.md), issue #196). Built and tested offline only
(`tests/test_plugin_standards_reads.py` compares the plug-in and COM answers on one fake drawing;
`PropertyFactsTests.cs` what the plug-in writes). The plug-in operation `entity_properties` has never
run. Needs the plug-in rebuilt and reinstalled from code that has it (plug-ins 1.8.0 and 1.8.1 do not:
they are read over COM), and the server restarted. "Both ways" means the same call to a second server
started with `--no-bridge`, as in Groups AS, AU, BB and BE; the plug-in's log shows
`operation entity_properties` when the plug-in read it. "The same text" means the two answers compared
character by character. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BI1 | A real MEP plan with objects on layer 0, colour and linetype overrides, objects on a sheet and in model space: `autocad_check_standards(rules={'forbid_entities_on_layer_0': true, 'require_bylayer_color': true, 'require_bylayer_linetype': true})` both ways | The log shows `operation entity_properties`; the same text both ways, findings in the same order with the same colour numbers and linetype names | NOT RUN |
| BI2 | One line with a true colour (RGB) and one with a colour-book colour: `autocad_check_standards(rules={'require_bylayer_color': true})`, then `rules={'forbid_entities_on_layer_0': true}`, with the plug-in | First: the check reads over COM (the log shows the call, the answer matches `--no-bridge`). Second: the plug-in's answer is used. Write down what COM's `Color` gives for each of the two lines | NOT RUN |
| BI3 | One of each dimension kind (rotated, aligned, angular, radial, diameter, arc length, ordinate), some drawn on top of each other: `autocad_check_standards(rules={'forbid_overlapping_dimensions': true})` both ways | The same overlaps both ways: .NET's `GeometricExtents` gives each dimension the box COM's `GetBoundingBox` gives | NOT RUN |
| BI4 | The plan of BI1 with more than 50 objects: `autocad_check_standards(rules=..., max_entities=50)` both ways | The same text: "Only the first 50 objects were read", `passed` null, the same 50 objects checked | NOT RUN |
| BI5 | Plug-in 1.8.1 installed (no `entity_properties`): BI1; then on a plan of 20,000 objects time BI1 with the new plug-in and over COM; then draw a line yourself, run BI1, press Ctrl+Z once | 1.8.1 answers over COM with no error and the same text; the new plug-in is clearly faster (write both times); the Ctrl+Z takes away **your line**: the read left no undo step | NOT RUN |

## Group AO - PDF Import: a PDF page as lines (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-106](DECISIONS.md); issue #113). Built and tested offline only
(`tests/test_pdf_import.py`). Server only, no plug-in change: restart the server after pulling.
The six questions and the three variables were read from Autodesk's help **through a search**
(the help site could not be opened from the session that wrote this): AO1 and AO2 prove them.
Use a PDF printed from AutoCAD (two pages, a few lines and some TrueType text) and a scanned
one-page PDF. `autocad_status` first. After each row press **Ctrl+Z once** and check the drawing
is back as it was (one undo step). **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AO1 | Before anything else, type `-PDFIMPORT` by hand with FILEDIA 0 and choose File, and write down every prompt it shows, in order, up to the end; then the same on a **one-page** PDF | Exactly: underlay or [File] / file name / page number / insertion point / scale factor / rotation, and nothing after. If the one-page PDF skips the page prompt, or any prompt differs, this row is **FAIL**: write the prompts here; the fix is in `acad/pdf_import.py` (`command_form`) | NOT RUN |
| AO2 | `(getvar "PDFIMPORTFILTER")`, `(getvar "PDFIMPORTMODE")` before; then `autocad_import_pdf(path=<two-page PDF>, page=2, insertion=[1000,1000], scale=1, layer='M-PDF')` | Page 2 comes in at 1000,1000 on M-PDF (lines, text as MTEXT or TEXT, fills as hatches), `imported`, `by_type` and `box` match what is seen; afterwards both variables, FILEDIA, OSMODE, AUNITS, ANGBASE and ANGDIR are what they were; `Command:` is free; one Ctrl+Z takes all of it away, M-PDF too | NOT RUN |
| AO3 | Same PDF, `what=['lines']`, then `what=['text']` | First: no text, no hatches; second: only text | NOT RUN |
| AO4 | `autocad_import_pdf` with `page=3` on the two-page PDF | Refused before AutoCAD is asked ("has 2 pages"); nothing sent | NOT RUN |
| AO5 | Tick **Import as block** in the PDF Import dialog once (PDFIMPORTMODE then has bit 1), cancel it; run AO2 again | The page comes in as loose objects, not one block, `"release": 2027`; afterwards PDFIMPORTMODE is what it was, bit 1 still on | NOT RUN |
| AO6 | The scanned one-page PDF | Nothing comes in (or only what AutoCAD makes of the picture: nothing, since pictures are left out); the answer says it is most likely a scan; `Command:` is free | NOT RUN |
| AO7 | A UCS turned 30 degrees (`autocad_set_ucs`), `autocad_import_pdf(insertion=[0,5000], rotation=0)` (world) | The page's lower-left corner is at world 0,5000 and its bottom edge runs along world X, not the UCS X | NOT RUN |
| AO8 | `autocad_import_pdf` on a PDF whose name and folder have spaces and an Arabic or accented letter | It comes in; the path is not cut at the space | NOT RUN |
| AO9 | Scale: import a 1:100 A1 PDF of a mm drawing at `scale=1`, measure one known dimension with `autocad_measure`, work out the scale that makes it true, import again with it | Write the scale that was right here (it says how AutoCAD sizes a page at 1), so the tool's help can say it plainly | NOT RUN |
| AO10 | On AutoCAD 2025 or 2026, and on 2021-2024: AO1 and AO2 | Same prompts and result | NO MACHINE |

## Group AP - The smaller draw gaps: construction line and ray, region, donut, divide / measure (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-108](DECISIONS.md); issues #173, #174, #177, #181, part 1 of #119). Built and
tested offline only (`tests/test_draw_extra.py`). Server only, no plug-in change: restart the server
after pulling. Scratch drawing, `autocad_status` first. After each row press **Ctrl+Z once** and
check the drawing is back as it was (one undo step). The COM calls and the DIVIDE / MEASURE rules
were not checked against Autodesk's reference (D-108); each row compares with AutoCAD's own command.
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AP1 | `autocad_add_construction_line(base=[1000,1000], angle=90)`; then `kind='ray'`, `base=[0,0]`, `through=[300,400]`; then the same in paper space with a sheet tab active (`space='paper'`) | A vertical XLINE through 1000,1000 (LIST says Xline, base point 1000,1000, unit direction 0,1); a RAY from 0,0 towards 300,400 only; the paper one on the sheet. `verified: true` each | NOT RUN |
| AP2 | A closed polyline 1000 x 500: `autocad_add_region(handles=[it])` | One region (LIST says Region), area 500000, perimeter 3000, centroid 500,250 (MASSPROP agrees); **the polyline is still there** (record it: does COM's AddRegion keep the outline, whatever DELOBJ says?) | NOT RUN |
| AP3 | Four lines meeting end to end in a square, plus a circle elsewhere: `autocad_add_region(handles=[all five], erase_outlines=true)` | Two regions; the four lines and the circle erased after the modeller chooses Keep the change (the whole-change question, D-140); one Ctrl+Z brings them back and takes the regions away. Then add one loose open line to the handles: **record whether AddRegion ignores it** (Heron erases every outline given, so it goes too). An outline on a locked layer with erase_outlines: refused before any region is made | NOT RUN |
| AP4 | An open polyline; then a text: `autocad_add_region` on each | The polyline: refused with "no region" and AutoCAD's own words, nothing made; the text: refused before AutoCAD is asked | NOT RUN |
| AP5 | `autocad_add_donut(centers=[[0,0],[500,0]], outside_diameter=150, inside_diameter=100)`; then `outside_diameter=30` (a dot) at 1000,0. Beside them, AutoCAD's own DONUT with the same sizes | Rings and a dot that look the same as DONUT's (LIST of each: closed polyline, 2 vertices, constant width 25 and 15); with FILLMODE 0 the answer has the note and they show as outlines | NOT RUN |
| AP6 | A line 0,0 to 1000,0: `autocad_divide_curve(segments=4)`; then AutoCAD's own DIVIDE 4 on a copy | Points at 250, 500, 750 (none on the ends), the same as DIVIDE's; with PDMODE 0 the answer has the point-style note | NOT RUN |
| AP7 | A circle r=100 at 0,0 and a closed rectangle: `autocad_divide_curve(segments=4)` on each; compare DIVIDE 4 on copies | The circle: 4 points at 0, 90, 180, 270 degrees (100,0 first); the rectangle: 4 points, the first on its first vertex. **Record whether DIVIDE on a closed object also puts N points with one on the start**, and where DIVIDE starts on a circle | NOT RUN |
| AP8 | A line 0,0 to 1000,0: `autocad_divide_curve(interval=300)`, then `interval=250`, then `interval=300, from_end=true`; compare MEASURE 300 and 250 picked near the start, and 300 near the end | 300, 600, 900 (left_at_end 100); 250, 500, 750 (left_at_end 0, no point on the end); 700, 400, 100. **Record whether MEASURE puts a point exactly on the end at 250** | NOT RUN |
| AP9 | An L-shaped polyline at elevation 2700 (0,0 -> 600,0 -> 600,600), a block SUPPORT with an arrow along +X: `autocad_divide_curve(interval=500, block_name='SUPPORT', layer='M-SUPPORT')`; then MEASURE Block SUPPORT aligned on a copy | Two supports at 500,0 and 600,400, z 2700, turned 0 and 90 degrees, on M-SUPPORT, matching MEASURE's. With `from_end=true`: record whether MEASURE turns blocks the other way when counted from the far end | NOT RUN |
| AP10 | A line drawn in a UCS tilted out of plan, and a line sloping in Z: `autocad_divide_curve(segments=2)` on each; a polyline in paper space on a sheet | The first two refused plainly, nothing placed; the paper-space one gets its points on that sheet | NOT RUN |
| AP11 | AutoCAD 2025 / 2026 and 2021-2024 builds: AP1, AP2, AP5, AP6 | As in AutoCAD 2027 | NO MACHINE |

## Group AQ - Associative and path arrays, tiled viewports, hyperlinks, DWF, geographic location (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-110](DECISIONS.md), [D-111](DECISIONS.md); issues #175, #176, #178, #179,
#180, part 2 of #119). Built and tested offline only (`tests/test_ribbon_gaps_part2.py`,
`tests/test_export.py`, `Bridge.Tests/ArrayPlanTests.cs`, `GeoPlaceTests.cs`). **New plug-in
operations** (`associative_array`, `geo_location`, `set_geo_location`): build and install the
plug-in, restart the server. Scratch drawing in millimetres, `autocad_status` first. After each
change row press **Ctrl+Z once** and check the drawing is back as it was. The .NET names were read
from Autodesk's reference DLLs and the COM numbers from Autodesk's interop DLL; what they *mean*
(an array's base point and angles, a geo location's reference point) was not, so each row compares
with AutoCAD's own command. AQ15-AQ17 were added on 2026-11-23 ([D-143](DECISIONS.md), #258, #80;
`Bridge.Tests/OperationTransactionTests.cs`): a plug-in change, so build and install the plug-in first.
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AQ1 | A line 0,0 to 9000,0 and a block HANGER at 0,0: `autocad_associative_array(handles=[HANGER], pattern='path', path=the line, spacing=1500)` | One array object (LIST says an associative array / ARRAY); 7 hangers at 0, 1500 ... 9000, each turned along the line; `associative: true`, `items: 7`. Click it: the ARRAY contextual tab opens; stretch the line to 12000: the hangers follow (Measure keeps 1500). One Ctrl+Z: back to the line and one loose hanger | NOT RUN |
| AQ2 | An arc and a polyline with a bend: `pattern='path', count=5` on each, then `align_items=false` | 5 items spread end to end (first and last on the ends), turned with the path; without align, all square. **Record if any answer was refused "somewhere other than asked"**, and what ARRAYPATH puts at the same counts | NOT RUN |
| AQ3 | A 600 x 600 diffuser block: `pattern='rectangular', rows=3, columns=4, row_spacing=1200, column_spacing=1200` | 12 diffusers, the original where it was, the grid growing up and to the right; ARRAYEDIT changes the count and the grid follows. Negative spacings build down and left | NOT RUN |
| AQ4 | A circle r=20 at 100,0: `pattern='polar', count=8, center=[0,0]`; then `fill_angle=90, count=3`; then `rotate_items=false` | 8 circles evenly round 0,0 at radius 100, the first where the original is; then 3 over a quarter (0, 45, 90 degrees). **Record whether AutoCAD read the angles as degrees** (a refusal "somewhere other than asked" means it did not) and whether the centre came out at 0,0 | NOT RUN |
| AQ5 | A line in model space and one on a layout as the objects; a path that is one of the objects; 9 items at 1500 on a 10 m line | Refused plainly before anything is made: "different spaces", "cannot also be one of the objects", "at most 7 fit" | NOT RUN |
| AQ6 | `autocad_tiled_viewports(layout='two_vertical')`, then `'four'`, `'three_right'`, then `'one'`; then no layout | Two side by side, four in a 2 x 2, three with the big one on the right, then one; each starts from the view that was on screen; `arrangement` matches each time, no warning. **Record AutoCAD's own words** for acViewport2Vertical (side by side?) and acViewport3Right. VPORTS > Named shows "Heron" | NOT RUN |
| AQ7 | On a layout tab: `autocad_tiled_viewports(layout='two_vertical')` | Refused, "switch to the Model tab", pointing at autocad_add_viewport; nothing changed. The Changes padlock off makes no difference on the Model tab (a View tool) | NOT RUN |
| AQ8 | A block on the drawing: `autocad_hyperlinks(handles=[it], url='C:\\Temp\\test.pdf', description='Data sheet')`; hover, then Ctrl+click | The hover shows "Data sheet"; Ctrl+click opens the PDF; HYPERLINK on the object shows the same address. Then `url='https://www.autodesk.com'`: the old link is replaced, one link only. One Ctrl+Z takes it back | NOT RUN |
| AQ9 | `autocad_list_hyperlinks()` with three linked objects and many without; then `action='remove'` on one; then list again | Exactly the three, with their links (the PE_URL selection works); after remove, two. An object on a locked layer: in `failed`, the rest done | NOT RUN |
| AQ10 | A sheet with a title block: `autocad_export(path='C:\\Temp\\sheet.dwf', area='layout', scale='1:1')`, Publish padlock on; then with it off | A .dwf that opens in Autodesk Viewer / Design Review and looks like the PDF of the same sheet; the layout's page setup unchanged afterwards (PAGESETUP). Padlock off: refused | NOT RUN |
| AQ11 | Drawing units mm. `autocad_geo_location(latitude=25.29, longitude=51.53, point=[0,0], north_angle=12)` | `located: true`, `reference_form` given (**record which: grid or lon_lat**); GEOGRAPHICLOCATION shows the marker at Doha, north 12 degrees to the right of up; `autocad_get_geo_location` reads 25.29, 51.53 and `agrees: true`; LATITUDE / LONGITUDE read 25.29 / 51.53. GEOMAP AERIAL (signed in): the map sits under the drawing at the right size (a 10 m line is 10 m on the map) | NOT RUN |
| AQ12 | A new drawing never placed: `autocad_geo_location()` with no place; then `autocad_set_sun(latitude=9.93, longitude=76.27)` and `autocad_geo_location(point=[1000,2000])` | First refused, San Francisco named; then the location is Kochi at 1000,2000 and the sun's place did not move (`moved: false`) | NOT RUN |
| AQ13 | INSUNITS 0: `autocad_geo_location(latitude=25.29, longitude=51.53)`; then units mm and `coordinate_system='UTM84-39N'`; then `'NOT-A-SYSTEM'`; then `action='remove'` | No units: refused; UTM84-39N: located at the same place; the unknown code: refused, nothing changed; remove: GEOGRAPHICLOCATION shows no location; one Ctrl+Z brings it back | NOT RUN |
| AQ14 | AutoCAD 2025 / 2026 and 2021-2024 builds: AQ1, AQ4, AQ6, AQ8, AQ11 | As in AutoCAD 2027 | NO MACHINE |
| AQ15 | ([D-143](DECISIONS.md), #258) A drawing in mm with no location: draw a line by hand, then `autocad_geo_location(latitude=25.29, longitude=51.53)`. Press Ctrl+Z once, then once more | `made: true`. The first Ctrl+Z takes the location off (GEOGRAPHICLOCATION shows none; LATITUDE / LONGITUDE back to what they were); the line is still there. The second Ctrl+Z removes the line. **Record if the location needed two Ctrl+Z** | NOT RUN |
| AQ16 | ([D-143](DECISIONS.md), #258) Draw a line with `autocad_draw_line`, then `autocad_tiled_viewports(layout='two_vertical')`; ask "undo your last change" (`autocad_undo_last`), then the palette's Undo on the line's row | The split stays a View job: no padlock asked. Both Undos either remove the line and leave the split, or refuse plainly because a view step came after it; **neither undoes only the split**. Record which. One Ctrl+Z by hand after the split puts back one viewport | NOT RUN |
| AQ17 | ([D-143](DECISIONS.md), #80) Ask to Keep off. Draw a line by hand. Then a plug-in job that has nothing to do and opens no server group: `autocad_update_table_links()` on a drawing with no Excel link. Open the Undo drop-down on the Quick Access toolbar | The plug-in's log says "touched nothing: aborted, no undo step". The list shows the hand-drawn line on top, no blank entry; one Ctrl+Z removes the line. **Record what the list shows on top** | NOT RUN |

## Group AM - A preview of a full sheet: what it covered, and close-ups (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-102](DECISIONS.md), issue #41). Built and tested offline only
(`tests/test_preview_extents.py`); server change only, no plug-in change. Restart the server first.
Use the A1 automation room SLD from 2026-10-28 (or any A1 sheet at 1:1 with 2.5 mm text). AM1 is
the row that says which cause #41 was. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AM1 | On the A1 SLD in Model: `autocad_preview()` (extents). Read `plotted`, `pixels`, `smallest_clear_text`, `tip` | Record all four and whether the picture shows the contents. **Tells the causes apart:** `plotted` about 841 x 594 and `smallest_clear_text` above 2.5 = too few pixels (go to AM2); `plotted` much bigger than the frame = something far off (find it with `autocad_get_extents`, ZOOM E; erase it and repeat); `plotted` right, picture shows the sheet full size and yet nothing but the frames = a third cause in AutoCAD's Extents plot itself (record it, the close-ups in AM2 still work round it) | NOT RUN |
| AM2 | `autocad_preview(detail=2)`, then `detail=3` | 5 then 10 pictures: the overview, then the parts top left first, each with its `part` and corners; the 2.5 mm text reads in the detail=3 parts; parts overlap a little at the seams; `detail_smallest_clear_text` smaller than in AM1 | NOT RUN |
| AM3 | After AM2: PAGESETUP on Model, and BACKGROUNDPLOT | Page setup as before (plotter, paper, area, scale, rotation); BACKGROUNDPLOT as before; one U in AutoCAD undoes nothing of the previews | NOT RUN |
| AM4 | Draw a line at 100000,100000, then `autocad_preview()`; erase it, `autocad_preview()` again | First: `plotted` reaches 100000 and the sheet is small in the picture. Second: record whether `plotted` shrank back to the sheet (the regen refreshed the extents) or still reaches 100000 (stale until ZOOM E; then the code should do more) | NOT RUN |
| AM5 | `autocad_preview(width_px=4000)` and `width_px=640` | Record the `size` and `pixels` AutoCAD chose each time: they are the PNG plotter's biggest and smallest sizes, not yet known here | NOT RUN |
| AM6 | `autocad_set_3d_view(direction='sw_iso')`, `autocad_preview(detail=2)`; then `autocad_preview(area='view', detail=2)` | First: one picture and `detail_skipped` naming the plan view. Second: refused, naming area='extents' or 'window'; nothing plotted | NOT RUN |
| AM7 | D-141 (#41, 2026-11-23). Restart the server. On the A1 SLD in Model: `autocad_preview()` with no `detail`; then `autocad_preview(detail=1)`; then on a small detail drawing (not a sheet) `autocad_preview()` | First: 5 pictures, `detail_added` names the sheet and TEXTSIZE, the 2.5 mm text reads in the four close-ups. Second: one picture and a `tip`. Third: one picture, no `detail_added`. If the first still shows only the frame in the overview, record whether the close-ups show the contents (they are windows, the route that showed everything on 2026-10-28) | NOT RUN |
| AM8 | D-151 (#269, 2026-11-23). Needs the plug-in built from this change; restart the server. In a new drawing with an A1 frame: a line at 100000,100000, erased by hand (ERASE, no ZOOM), then `autocad_preview(detail=1)` | `plotted` is the sheet again, not 100000; `extents_note` says EXTMIN/EXTMAX still reached the erased line and the picture covers what the plug-in measured; the picture shows the sheet full size. With an older plug-in: as AM4 (stale), no error | NOT RUN |

## Group AH - 3D for MEP: duct runs, pipe spools, flat views, sections, surfaces, meshes, super hatch tiles (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-94](DECISIONS.md), [D-95](DECISIONS.md); issues #53, #54, #109, #58,
#57). Built and tested offline only (`tests/test_shapes3d.py`, `tests/test_model_views.py`,
`SectionMathTests.cs`, `RunTests.cs`); the add-in **compiles** for all three AutoCAD builds. AH17-AH21
were added on 2026-11-23 for hidden lines and jogged section lines (#171, [D-152](DECISIONS.md); tested
offline in `ObscuredLinesTests.cs`, `JoggedSectionTests.cs` and `tests/test_model_views.py`). AH1-AH3
are server only (restart the server); the rest need the plug-in built from this change (six new
operations) installed. Changes padlock on, `autocad_status` first, a scratch drawing in mm. After
each row press **Ctrl+Z once** and check the drawing is back as it was. **Every row below is NOT
RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AH1 | `autocad_make_shape(shape="duct_run", settings={"points": [[0,0,3000],[5000,0,3000],[5000,4000,3000],[5000,4000,6000]], "width": 600, "height": 400}, layer="M-DUCT")`, then `autocad_set_3d_view(direction="sw_iso", visual_style="conceptual")` and `autocad_preview` | Five solids on M-DUCT meeting end to end: a level 90° bend (R600) and a bend up (R400), the 600 side level on the first leg; `verified: true`, no warning. `autocad_solid_properties` of the first straight: volume 600 x 400 x 4400 = 1,056,000,000. One Ctrl+Z removes all five | NOT RUN |
| AH2 | `autocad_make_shape(shape="pipe_spool", settings={"points": [[0,0,0],[2000,0,0],[2000,0,1500]], "outside_diameter": 114.3, "wall": 6.02, "flange_diameter": 229, "flange_thickness": 24, "bolt_count": 8, "pitch_diameter": 190.5, "hole_diameter": 19})` | Flange, pipe, elbow, pipe, flange: the flange faces on 0,0,0 and 2000,0,1500; both flanges bored 102.26 and drilled 8 x 19 holes straddling the centrelines; `pipe_cut_lengths` 1804.55 and 1304.55 match DIST across each pipe. Again with `"join": true`: one solid | NOT RUN |
| AH3 | Look at the AH1 and AH2 answers' pieces | Write down whether any bend says `revolved_the_other_way` (AutoCAD's revolve sense, not in its reference). Either way every bend must continue the run, not fold back over the straight | NOT RUN |
| AH4 | Spool from AH2 (not joined): `autocad_flatten_views(handles=[its five handles], insert_at=[4000, 0], layer="M-SHOP")` | Three blocks FLATSHOT-1-FRONT, -TOP, -RIGHT on M-SHOP; plan above the front and the right view to its right, lined up (the pipe's centreline level across front and right); no hidden lines; the model untouched. Record `laid_flat_from` (expected `plane`). Compare with FLATSHOT done by hand on the same spool | NOT RUN |
| AH5 | Two overlapping boxes: `autocad_flatten_views(views=["front"])` with `join=false`, then `join=true` | Without join the back box's lines show through the front one; with join they are hidden, and the line where the two meet on a flush face is gone | NOT RUN |
| AH6 | The AH1 duct run: `autocad_section_plane(points=[[2500,-1000],[2500,5000]], insert_at=[8000, 0], handles=<the five AH1 solids>, layer="M-SECT")` (without `handles` it cuts every solid in model space) | A section plane in the model through x=2500 (SECTIONPLANE's object), and block SECTION-n at 8000,0: the duct's 600 x 400 cut outline, hatched; `cut` 1 of 5 solids (only the first straight crosses x=2500). It looks left of the line: from x=2500 towards -X (`looking` [-1,0,0]), so the bend and the riser (x 4400 to 5300) are behind the plane and **not** drawn: the section is 600 x 400, nothing from the +X side. Record `laid_flat_from` | NOT RUN |
| AH7 | `autocad_section_plane(points=[[0,0,3200],[1000,0,3200],[0,1000,3200]], insert_at=[0,-6000], handles=<the five AH1 solids>, background=false)` | A plan cut at 3200 looking down, north up (`looking` [0,0,-1], `up` [0,1,0]), hatched, nothing beyond. What is cut is the bend up: 600 along X by 565.7 along Y (radius 400, so 200 to 600 round its centre at z 3400). 3200 is the top face of the level legs (z 2800 to 3200), so whether AutoCAD shows them as cut is its call: record it. The riser starts at z 3400 and is not cut | NOT RUN |
| AH8 | `autocad_section_plane` with two points far from every solid, then with `keep_plane=false` | First: refused, "neither cuts nor sees ... Nothing was changed", and no section plane left. Second (through the duct): the block only, no plane in the model | NOT RUN |
| AH9 | Two open arcs at z=0 and z=2000: `autocad_loft(sections=[a, b], surface=true)`; then `autocad_thicken_surface(<it>, thickness=3)` | A lofted surface through both arcs (`area` given), the arcs kept; thickening it makes a 3 mm solid. Without `surface=true` the loft is refused naming surface=true | NOT RUN |
| AH10 | `autocad_add_surface(kind="planar", corners=[[0,0,2700],[3000,2000,2700]])`; then `kind="planar", outlines=[a closed polyline]`; then `kind="network"` with three curves each way crossing | A 3000 x 2000 plane surface at 2700 (area 6,000,000); one over the polyline; one network surface through the six curves. An open outline is refused | NOT RUN |
| AH11 | `autocad_add_mesh(shape="box", base=[0,0,0], length=1000, width=600, height=400, smoothness=2)`; `shape="sphere", radius=300, base=[2000,0,0]`; `from_handle=<an AH1 straight>` | A smoothed mesh box sitting on z=0, centred on 0,0; a mesh sphere centred at 2000,0,0; a mesh of the straight with the solid still there. Record faces / vertices for each | NOT RUN |
| AH12 | An L-shaped closed polyline: `autocad_super_hatch(boundary=<it>, image="<a .jpg on disk>", image_size=[600])` | One block reference (SUPERHATCH-n) holding the image tiled 600 wide, in proportion, showing only inside the outline. Record whether XCLIP clips the images inside the block (the reason for this row); one Ctrl+Z takes it all | NOT RUN |
| AH13 | `autocad_super_hatch(boundary=<it>, xref="<a tile .dwg>")`; then again with the xref's name | The xref attached (External References lists it) and tiled, clipped to the outline; the second call reuses it. Then a refusal case (an outline too big for 10,000 tiles with a .dwg not yet attached): refused and the xref not left attached | NOT RUN |
| AH14 | A 300 x 300 wipeout over some lines: `autocad_super_hatch(boundary=<it>, wipeout=<its handle>, spacing=[600, 600])` | A grid of masks inside the outline hiding the lines under them; the original wipeout untouched | NOT RUN |
| AH15 | Ask to keep on: run AH4, AH6, AH10, AH11 and AH12, answering Discard each time | Each is taken back whole; PURGE finds no FLATSHOT, SECTION or SUPERHATCH block left; no section plane left | NOT RUN |
| AH16 | AH1-AH15 and AH17-AH21 on AutoCAD 2025/2026 and 2021-2024 | As AH1-AH15 and AH17-AH21 | NOT RUN (no PC with those versions yet) |
| AH17 | Hidden lines (#171, [D-152](DECISIONS.md)), on a drawing with no HIDDEN layer: the AH2 spool, `autocad_flatten_views(handles=[its five handles], views=["front"], insert_at=[4000, -3000], hidden_lines=true)` | One block FLATSHOT-n-FRONT the same size as AH4's front (2114.5 x 1614.5); `hidden_lines` above 0 for the front view, `hidden_layer` HIDDEN, `hidden_layer_made` true, and layer HIDDEN now in the drawing with linetype HIDDEN. On screen: the pipe's and flanges' bores dashed inside the outline, nothing dashed on top of a visible line. Compare with FLATSHOT done by hand with "Obscured lines" shown: the same hidden lines | NOT RUN |
| AH18 | After AH17: freeze layer HIDDEN; thaw it. Then `autocad_flatten_views` again with `hidden_lines=true, hidden_layer="M-SHOP-HID"` where M-SHOP-HID already exists with linetype Continuous | Frozen, the dashed lines go and every visible line stays; thawed, they come back. The second answer says `hidden_linetype` HIDDEN and its hidden lines still show dashed on M-SHOP-HID; the layer's own linetype is still Continuous | NOT RUN |
| AH19 | A jogged (offset) section: two 1000 boxes, `autocad_add_solid(shape="box", base=[500,500], length=1000, width=1000, height=1000)` and the same at `base=[3500,2500]`; `autocad_section_plane(points=[[-500,500],[2000,500],[2000,2500],[4500,2500]], jogged=true, background=false, insert_at=[0,-4000], handles=[both])` | `legs` 3, `jogs` 1, `cut` 2, `looking` [0,1,0]; the block 4000 x 1000 at 0,-4000: the two cut squares side by side, 2000 apart, as one straight section (the jog not drawn). Record `laid_flat_from` and any `left_out_on_jogs`. One section plane kept, with its three legs (compare with SECTIONPLANE "Draw section" by hand through the same corners) | NOT RUN |
| AH20 | An angled leg: the AH19 boxes, `autocad_section_plane(points=[[-500,500],[2000,500],[4500,3000]], jogged=true, background=false, insert_at=[0,-7000], handles=[both])` | `legs` 2, `jogs` 0, `cut` 2; the block 4828.4 x 1000: the first box's cut 1000 wide, the second's at true size 707.1 wide (the 45 degree leg crosses it corner to side), laid beside the first leg. Then with `background=true`: record `laid_flat_from` and whether the boxes beyond sit where expected | NOT RUN |
| AH21 | A section line that walks back: `autocad_section_plane(points=[[0,0],[1000,0],[1000,1000],[0,1000]], jogged=true, insert_at=[0,-9000])` | Refused, "walks back across the view ... Make it two sections", "Nothing was changed"; no section plane or block added | NOT RUN |

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

## Group AW - Run LISP: control characters in text, and a LISP error answered at once (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-129](DECISIONS.md); issues #207 and #157). Built and tested offline with COM
stand-ins (`tests/test_lisp_control_chars.py`, `tests/test_run_lisp_errors.py`, `tests/test_pdf_import.py`):
the escaping, the wrapper's text, the answer and its first line. **Nothing here has run in AutoCAD.**
Server only; no plug-in build. Admin on for the `autocad_run_lisp` rows, Changes on for the drawing ones.
Use a scratch drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AW1 | `autocad_run_lisp('(+ 1 nil)')` | Back in about 1 s (not 10 s) with `lisp_error` = AutoCAD's own words (for example `bad argument type: numberp: nil`), `result` null, `timed_out` false; first line NOTHING CHANGED; `Command:` is free and the next call works | NOT RUN |
| AW2 | Five `defun`s of about 600 characters each, then `(car 5)` as the last form, in one call | Back in about 1 s; the note names the piece that stopped (piece 6 of 6 or the one holding `(car 5)`) and says what ran before it; the `defun`s before it exist (`(type f0)`); the first line is not DONE | NOT RUN |
| AW3 | `autocad_run_lisp('(no-such-function 1)')` | `lisp_error` names the missing function; `timed_out` false | NOT RUN |
| AW4 | A complete command inside the new wrapper: `autocad_run_lisp('(command "_.CIRCLE" "0,0" "10")')`, then `(command "_.LINE" "0,0" "10,10" "")` | Each draws its object, `timed_out` false, no `lisp_error`, no `cancelled_command`; one Ctrl+Z takes each away. **If a `(command ...)` inside it behaves differently on 2027 (draws nothing, hangs, or answers an error), stop and record it: this is what the issue warned about** | NOT RUN |
| AW5 | J4 again, on this build: `autocad_run_lisp('(command "_.CAMERA" "0,0,0" "1,1,1")')` with running snaps on | `cancelled_command: "CAMERA"`, AutoCAD free, OSMODE as it was | NOT RUN |
| AW6 | An error with a command left open: `autocad_run_lisp('(progn (command "_.LINE" "0,0") (car 5))')` | `lisp_error` and `cancelled_command: "LINE"` both in the answer, the note says both; AutoCAD free (no prompt left); the next call works | NOT RUN |
| AW7 | An expression AutoLISP may not read although the brackets balance, such as `(setq a '(1 . 2 3))`; run `(+ 1 2)` first so the call before it has a result | Record what comes back: a `lisp_error`, or a timeout. It must **never** be `3` (the call before it) | NOT RUN |
| AW8 | `autocad_run_lisp('(setq *error* (lambda (m) (setq heron-h m)))')`, then `autocad_run_lisp('(car 5)')`, then `autocad_run_lisp('heron-h')` | Record whether the handler ran. Expected: it did not (the catch answers first), and `lisp_error` is given. If a routine of the office depends on its handler, note which | NOT RUN |
| AW9 | A single form of 1,700 characters (`(setq a (list 1 1 1 ...))`), then one of 1,800 | The first runs and answers at once; the second is refused with "split it" before anything is sent | NOT RUN |
| AW10 | `autocad_import_pdf` of a page, as AO2 | Imports as before; the wrapper change did not alter it | NOT RUN |
| AW11 | `autocad_batch_draw` with one text op whose text holds a real ESC, a tab, a newline and `5" pipe`, a backslash and a quote (send it as JSON `"A\u001bB\tC\nD 5\" E\\F"`) | One TEXT object is made holding that text literally, and **nothing else ran** (no program started, no other object made, `Command:` free); look at it with `autocad_get_entity` | NOT RUN |
| AW12 | The same with Malayalam, Arabic and accented text in a text op | The text is drawn as sent (a style with a font that has the letters); record anything that looks changed | NOT RUN |
| AW13 | A text op with a NUL character (JSON `"\u0000"`) and one with U+0085 | Refused before anything is sent, naming the character; nothing drawn | NOT RUN |
| AW14 | `autocad_run_lisp` with a string holding a real line break: `(strlen "a` newline `b")` | `3`, not a stuck prompt | NOT RUN |

## Group AT - The office layer standard: the CSV, the import, the check and the remap (AutoCAD 2027, this PC)

Added on 2026-11-22 ([D-120](DECISIONS.md); issue #70). Built and tested offline
(`tests/test_layer_standard.py`): the format, the shipped example, which file wins, the CSV import,
and the check and remap plans, on plain data and a stand-in drawing. Server only: no plug-in build
is needed. Use a copy of a real MEP drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AT1 | AutoCAD **closed**. `autocad_layer_standard(action="template")`, open the CSV it names in Excel, put 5 of the office's real layers in it, save as **CSV UTF-8**, then `action="import"` | Answers with AutoCAD closed; `office-layers.json` appears in `%LOCALAPPDATA%\Heron\autocad\standards\` with the 5 layers; `action="show"` says the office standard is in force and lists them as typed | NOT RUN |
| AT2 | Save the same CSV from Excel as plain **CSV (Comma delimited)**, with a layer description that has an accent or a degree sign, and import it | Imported; the description reads back the same in `show` | NOT RUN |
| AT3 | Put a wrong colour (`reed`) and a lineweight of `0.33` in two rows, import | Refused; both problems named with the row numbers Excel shows; the office standard from AT1 is unchanged | NOT RUN |
| AT4 | AutoCAD open, a project drawing active. `autocad_check_standards(layer_standard="office")` | `layer_standard.source` names the office file; each finding names a layer that really differs from the CSV (check two by hand in the Layer Properties Manager: colour, linetype, lineweight, plot, description) | NOT RUN |
| AT5 | `autocad_layer_standard(action="remove")`, then AT4 again | `passed` is null; the warning says no office standard is loaded and that it was checked against the generic MEP example | NOT RUN |
| AT6 | Import the AT1 CSV again with a `replaces` cell naming an old layer the drawing has (a consultant's `MECH-DUCT*`, say). `autocad_remap_layers(layer_standard="office")` (dry run), then `dry_run=false` | The dry run moves only objects on the old layers, onto the standard's layer; nothing already on a standard layer, or on one a pattern row covers (an `M-...-IDEN` layer under `M-*-IDEN`), moves; after the run the target layer has the CSV's colour, linetype, lineweight and description, and one undo puts it all back | NOT RUN |
| AT7 | `autocad_remap_layers(layer_standard="office")` with no office standard loaded | Refused before anything is read: no office standard is loaded, nothing was moved | NOT RUN |
| AT8 | `autocad_check_standards(layer_standard="example")` on an MEP drawing | The answer says plainly it is the generic MEP example, not an office's standard | NOT RUN |

## Group AJ - Drawing events from the plug-in, fewer batch pieces (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-98](DECISIONS.md); issues #48, #45). Built and tested offline only
(`DrawingEventsTests.cs`, `tests/test_drawing_events.py`, `tests/test_quiet_pieces.py`). Needs the
plug-in built from this change (its ping says `quietLimit`, it knows the op `drawings`), reinstalled,
and the server restarted. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AJ1 | Connect, open the Heron palette (Activity). Open a second drawing, switch between the two, QSAVE one, Save As the other to a new name, close one | Each shows at once, newest first: "b.dwg opened", "b.dwg came to the front", "a.dwg saved", "Drawing1.dwg saved as plan.dwg", "b.dwg closed"; the "In front:" line follows every switch. The log (`addin-*.log`) shows no error | NOT RUN |
| AJ2 | SAVETIME 1, leave a drawing open for 2 minutes untouched | No "saved" line from the automatic save (.sv$) | NOT RUN |
| AJ3 | `autocad_status` on a.dwg; close a.dwg and open it again; ask Heron to draw a line | REFUSED: "a.dwg was closed at hh:mm:ss and opened again since Heron checked it. Call autocad_status first"; after `autocad_status` the line is drawn | NOT RUN |
| AJ4 | `autocad_status` on an unsaved Drawing1; Save As `C:\...\plan.dwg` by hand; ask Heron to draw a line | The line is drawn in plan.dwg with no new status check (the Save As is followed). With a plug-in built before this change: refused "The active drawing changed from Drawing1.dwg to ..." as before | NOT RUN |
| AJ5 | `autocad_status`; close AutoCAD; start it again with the same drawing; press Heron; ask Heron to draw a line (same chat) | REFUSED: "AutoCAD was started again, or another AutoCAD is in front, since Heron checked a.dwg"; after `autocad_status` it draws | NOT RUN |
| AJ5b | `autocad_status` on a.dwg; Save As a-rev2.dwg; open a.dwg from disk again and keep it in front; ask Heron to draw a line | REFUSED: "a.dwg was opened at hh:mm:ss, after Heron checked a drawing"; after `autocad_status` it draws | NOT RUN |
| AJ6 | `autocad_batch_draw` of the A22 batch (41 objects) with the plug-in connected, then F2 | About 9 `Command:` prompts (it was about 27), all 41 made, no `missing` in the answer, no LISP text in the history. **Write the count down** | NOT RUN |
| AJ7 | `autocad_batch_draw` of 2,000 lines, then of one 800-vertex polyline and 50 texts | `created` = `requested`, no `missing`, `completed` true: every piece up to 1,500 characters arrived. If any is missing, or AutoCAD sits at a `(_>` prompt (a piece cut short), write the batch size and lower `QUIET_CHUNK_LIMIT` | NOT RUN |
| AJ8 | Two drawings open. `autocad_sequence` of 6 `autocad_batch_draw` steps of 500 lines each in a.dwg, each on a new layer; press Ctrl+Tab to b.dwg while it runs | The sequence stops before its next step: hint "The drawing in front changed after step N ... nothing landed in the other drawing" (or, for a switch inside a step, that step's input is refused: "so Heron typed none of this input"); no Heron object and no new layer in b.dwg; a.dwg has the steps before the switch ([#165](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/165)) | NOT RUN |
| AJ9 | With the palette's Activity open, let a chat draw in a.dwg, then switch to b.dwg | The job's row says "not in front" at once; Select answers "switch to a.dwg first" as before | NOT RUN |
| AJ10 | AJ6 with a plug-in built before this change, and once with the bridge off (`--no-bridge`) | The batch works as before in 600-character pieces (about 25 prompts with the old plug-in; the history shows the LISP over COM with the bridge off) | NOT RUN |

## Group AK - The setup program, update, uninstall, signing (Windows, AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-99](DECISIONS.md); issues #73, #72). The setup is built by `release.yml` on
GitHub's Windows machine. Get `HeronAutoCAD-<version>-setup.exe`
from the release (or the workflow run's artifact). For AK1 use a Windows user that never had
Heron and is **not** an administrator. AK12 to AK14 were run on the owner's PC on 2026-11-22 with
the v1.8.0 release; AK1 to AK11 are still NOT RUN. AK13 is NOT RUN again for 1.8.1, which fixes
it (#233); AK15 and AK16 check the same fix on the owner's PC.

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AK1 | Clean user account, AutoCAD and Claude closed: double-click the setup, Next to the end | No administrator (UAC) box at any point; the first page says NOT FINISHED; the last page lists the Claude Code and Claude Desktop lines; the bundle is in `%APPDATA%\Autodesk\ApplicationPlugins`, the server and `Install.ps1` in `%LOCALAPPDATA%\Heron\autocad`; Settings > Apps lists *Heron AI for AutoCAD* with its version and Ajmal PS; the Start menu has *Check for a newer Heron* and *Remove Heron AI for AutoCAD*. `claude mcp list` shows `autocad` at the installed server; AutoCAD starts with the Heron tab and Heron connects | NOT RUN |
| AK2 | AutoCAD open: run the setup. Then close AutoCAD, run it, stop on the *Ready* page, start AutoCAD, press Install | First: refused at once, "AutoCAD is open... Nothing was changed", nothing on disk changed. Second: it stops on the *Preparing to Install* page with the same words, nothing copied | NOT RUN |
| AK3 | Claude Desktop open and connected to the installed Heron: run the setup. Then the same with only a `.venv` dev server running (Claude Code in the source folder) | First: refused, "Claude is using Heron's server... Nothing was changed". Second: not refused (the dev server is somewhere else) | NOT RUN |
| AK4 | With an older version installed by the zip's `Install.bat`: run the new setup | The last page shows the new version; the bundle folder holds only the new files (no file of the old one); `claude mcp list` and the Claude Desktop file still point at `%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe`; AutoCAD loads the new version | NOT RUN |
| AK5 | With the setup's own older version installed: run the next release's setup | Settings > Apps shows one *Heron AI for AutoCAD*, at the new version; AutoCAD loads the new version. Then run the older setup again: it goes back | NOT RUN (needs a second release built with the setup) |
| AK6 | Settings > Apps > Heron AI for AutoCAD > Uninstall, first with AutoCAD open, then closed | Open: refused, "Nothing was removed". Closed: the bundle, the server, `Install.ps1`, `CheckForUpdate.bat`, the Start menu entries and any `previous` folder are gone; `claude mcp list` has no `autocad`; the Claude Desktop file has no `autocad` but keeps every other entry; `commands`, `checklists`, `logs` and `audit` in `%LOCALAPPDATA%\Heron\autocad` are still there | NOT RUN |
| AK7 | After AK1 (setup install): double-click the zip's `Uninstall.bat` | It says Heron was installed with its setup and names Settings > Apps; nothing removed | NOT RUN |
| AK8 | Start menu > Heron AI for AutoCAD > Check for a newer Heron | A window shows the installed version and either "the newest version" or the newer one's link; nothing installed | NOT RUN |
| AK9 | Download the setup from the GitHub release in Edge and run it | Record exactly what Windows shows (SmartScreen *Windows protected your PC* or not, the publisher it names) and what the company antivirus does | NOT RUN |
| AK10 | After AK1, SECURELOAD left at 1 (check with SECURELOAD at the command line): start AutoCAD 2027 | Heron is **unsigned by decision** (#164). Record whether AutoCAD shows a security box for Heron in `%APPDATA%\Autodesk\ApplicationPlugins`, its exact words and buttons; choose to load it always. The Heron tab appears | NOT RUN |
| AK11 | After AK10: close AutoCAD and start it again; then install the next version over it (AK5) and start AutoCAD | No box on the restart: the modeller trusts Heron **once**. After an update, record whether AutoCAD asks again | NOT RUN |
| AK12 | The owner's own Windows user, with a plug-in installed from source (`tools/install_plugin.py`, 1.5.0) and no earlier setup; AutoCAD, Revit and Claude's Heron server from that folder closed. Run the release's setup quietly from PowerShell (`/SILENT /SUPPRESSMSGBOXES /NORESTART /LOG=...`); then compare what landed with the release zip | The bundle in `%APPDATA%\Autodesk\ApplicationPlugins` holds exactly the zip's files, same bytes, nothing of the old one; `autocad-mcp.exe`, `Install.ps1` and `CheckForUpdate.bat` in `%LOCALAPPDATA%\Heron\autocad` are the zip's; Settings > Apps lists *Heron AI for AutoCAD* with its version and Ajmal PS; the Start menu has its two entries; no administrator (UAC) box | **PASS** 2026-11-22, setup 1.8.0 on Windows 11: 59 of 59 bundle files identical, none missing or extra; the old bundle was moved aside, then dropped; server, `Install.ps1` and `CheckForUpdate.bat` identical; Apps entry *Heron AI for AutoCAD* 1.8.0, Ajmal PS; both Start menu entries; no UAC box. Quiet mode, so the wizard pages were not seen, and the file came from `gh release download` (no download mark), so SmartScreen had nothing to check: AK1 and AK9 stay NOT RUN |
| AK13 | A PC where Claude is only the Claude desktop app (its Code tab runs Claude Code inside the app; no `claude` command on the PATH), Claude quit: run the 1.8.1 setup and read its two Claude lines (last page, or the setup log) | `Claude Code: connected (all projects)` and `Claude Desktop: connected (restart Claude ...)`; `%USERPROFILE%\.claude.json` and `%LOCALAPPDATA%\Claude-Data\<package>\claude_desktop_config.json` each have an `autocad` entry that starts `%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe`, with a `.heron-backup` beside each; a new Code tab chat in a folder with no `.mcp.json` lists the AutoCAD tools | **NOT RUN** for 1.8.1, which fixes it ([#233](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/233), [D-126](DECISIONS.md)). Before: FAIL 2026-11-22 with setup 1.8.0: `Claude Code: not found, skipped` and `Claude Desktop: not found, skipped`. No `%APPDATA%\Claude` folder on the disk (the app keeps its settings in `%LOCALAPPDATA%\Claude-Data\...`), so no entry was added anywhere and nothing else changed. A modeller with only the Claude app must add the entry by hand ([INSTALL section 5](INSTALL.md#5-connect-claude), [#233](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/233)) |
| AK14 | After AK12: start AutoCAD 2027 and press Heron; a chat reads, draws, previews and saves in a drawing | The add-in log says `1.8.0 loaded`, then `Connected`; the chat's reads and changes end `done` | **PASS** 2026-11-22, AutoCAD 2027 (26.0s): `Heron for AutoCAD 1.8.0 loaded in AutoCAD 26.0s`, `Connected, pipe heron.autocad.<pid>`; status, a new drawing, 2 batch draws, 5 sequences, 2 previews and 2 saves ended `done` (one more sequence ended `failed` in 30 ms with no reason in the log; the chat's next one was done). That chat used the source server 1.10.1 from `.venv`; the release's own `autocad-mcp.exe` was proven offline only (it starts and lists 199 tools, version 1.10.1). The unsigned-plug-in box (AK10) was not recorded |
| AK15 | The owner's PC (Claude app only, AutoCAD may be open): from a terminal outside the Claude app, `powershell -NoProfile -ExecutionPolicy Bypass -File %LOCALAPPDATA%\Heron\autocad\Install.ps1 -Connect -DryRun` (or the release's copy) | `Dry run: nothing is changed.`, then a line naming the `claude.exe` it would use (the `claude` command, `%USERPROFILE%\.local\bin\claude.exe` or the Claude app's own copy, in that order) and the `claude mcp add --scope user autocad -- ...` it would run, and one for the app's `claude_desktop_config.json` (`would add`, or `Claude is open, ... not changed`); no file changes | **PASS** 2026-11-22, `Install.ps1` from the 1.8.1 change (not yet a release), run from the Terminal panel, AutoCAD closed, the Claude app open: `Dry run: nothing is changed.`; `Claude Code: would add "autocad" for all projects: "%USERPROFILE%\.local\bin\claude.exe" mcp add --scope user autocad -- "%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe"` (this PC has that copy as well as the app's own `claude-code\2.1.325\...\claude.exe`); `Claude Desktop: Claude is open, so its settings file was not changed: %LOCALAPPDATA%\Claude-Data\anthropicpbc.claude_fnn82j28hfe8t\claude_desktop_config.json`. No file changed |
| AK16 | After AK15, with the owner's yes and AutoCAD closed: the same without `-DryRun`, with the Claude app open | `Claude Code: connected (all projects ...)`; `.claude.json.heron-backup` beside `%USERPROFILE%\.claude.json`; `Claude Desktop: Claude is open, so its settings file was not changed`, and that file is unchanged. A new chat in the source folder still starts the `.venv` server (the folder's `.mcp.json` wins); a new chat in another folder lists the AutoCAD tools from `%LOCALAPPDATA%\Heron\autocad` | **PASS** for the Code tab, 2026-11-22, the owner said yes: `Claude Code: connected (all projects; old settings saved as .heron-backup)`; `.claude.json` has `autocad` (stdio, `%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe`) and `.claude.json.heron-backup` beside it has no `mcpServers`; `Claude Desktop: Claude is open, so its settings file was not changed`, and that file has no `autocad` and no backup (the app itself rewrote it a minute later). The app's `claude.exe` 2.1.325, started with the app's own flags (`--setting-sources=user,project,local --permission-mode=auto`) and sent nothing: in the source folder it started only the `.venv` server; in a folder with no `.mcp.json` it started the installed server. Not seen: a chat in the app's window listing the tools. Note: a plain `claude mcp get autocad` or `claude mcp list` in the source folder names the all-projects entry and warns "Conflicting scopes", because the folder's `.mcp.json` was never approved outside the app |

## Group AR - Pyramid, polysolid, offset / taper / move / delete faces, imprint, separate (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-112](DECISIONS.md), [D-113](DECISIONS.md); issues #182, #183, #184, part 3
of #119). Built and tested offline only (`tests/test_solid_shapes_faces.py`,
`SolidShapeMathTests.cs`); the add-in **compiles** for all three AutoCAD builds. Every row needs the
plug-in built from this change (eight new operations) installed. Changes padlock on,
`autocad_status` first, a scratch drawing in mm. After each row press **Ctrl+Z once** and check the
drawing is back as it was. The test box for AR8-AR12 is
`autocad_add_solid(shape="box", base=[0,0], length=1000, width=600, height=500)` (volume
300,000,000), made again before each row. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AR1 | `autocad_add_pyramid(base=[0,0,0], radius=300, height=900)`, then `autocad_preview` in plan and SW iso | A 600 x 600 base sitting on z=0, centred on 0,0, its sides along X and Y (corners at ±300, ±300); the point at 0,0,900; `turned: true`; `volume` = `expected_volume` = 108,000,000. Write down `remade_to_size` (expected false: Autodesk's reference says the radius is to the middle of a side) | NOT RUN |
| AR2 | `autocad_add_pyramid(base=[2000,0,0], sides=6, radius=200, radius_to="corner", top_radius=100, height=500)` | A hexagon with two corners on the X axis (at x 1800 and 2200) and flat sides facing front and back (y ±173.2), a flat hexagon top at z=500 with corners 100 out; `volume` = `expected_volume` (about 30,310,889) | NOT RUN |
| AR3 | `autocad_add_pyramid(base=[0,3000,0], radius=150, top_radius=600, height=900)` (a hopper); then again with `rotation=45` and `coords="ucs"` on a UCS turned 30° | A 300 x 300 bottom on z=0 and a 1200 x 1200 top at z=900, sides along X and Y; the second turned 75° in the world (45 + the UCS's 30), its base at the UCS point | NOT RUN |
| AR4 | `autocad_add_polysolid(points=[[0,0],[5000,0],[5000,3000]], width=200, height=1200)` | An L wall 200 thick centred on the line, 1200 high, with a square outside corner; `volume` 1,920,000,000 (8000 x 200 x 1200) | NOT RUN |
| AR5 | AR4 again with `side="left"`, then with `side="right"` | Left: the wall on the +Y side of the first leg (y 0 to 200) and the -X side of the second (x 4800 to 5000), volume 1,872,000,000. Right: y -200 to 0 and x 5000 to 5200, volume 1,968,000,000 | NOT RUN |
| AR6 | A closed 4000 x 3000 polyline drawn anticlockwise and a second drawn clockwise: `autocad_add_polysolid(path=<each>, side="inside", width=200, height=1200)`, then `side="outside"` | Inside: the wall's outer face on the outline for both, volume 3,168,000,000; outside: its inner face on the outline, volume 3,552,000,000. The polylines kept | NOT RUN |
| AR7 | A polyline with an arc (a bulge) and a circle as paths, `width=200, height=1000`; then a rectangle drawn with PLINE back to its first point without typing C, `side="inside"`; then a polyline with an arc of radius 50 and `width=200` | The walls follow the arc and the circle smoothly (a ring for the circle); the unclosed rectangle makes a ring like a closed one (`closed: true`), the polyline itself left as drawn; the tight arc is refused "turns tighter than the wall is wide ... Nothing was changed" | NOT RUN |
| AR8 | Test box: `autocad_edit_solid_faces(handle, action="offset", faces="top", distance=100)`; then (new box) `action="move", faces="right", by=[200,0,0]` | Offset: 600 high, `volume_after` 360,000,000. Move: 1200 long, 360,000,000 | NOT RUN |
| AR9 | Test box: `autocad_edit_solid_faces(handle, action="taper", faces="front", angle=10)` | The front face leans, its bottom edge still on y=0. Write down whether it leaned **in** (`volume_after` about 277,959,000, smaller) or out (larger): the tool's wording says in, and is fixed to match if not | NOT RUN |
| AR10 | Test box with its vertical edges filleted R50 (`autocad_fillet_solid_edges`); list its faces; `action="delete"` on one fillet face; then `action="delete", faces="top"` on a plain box | That corner is square again, volume up by about 268,000; deleting the top of a box is refused with nothing changed | NOT RUN |
| AR11 | A 400 x 200 rectangle drawn on the test box's top (z=500): `autocad_imprint_solid(handle, objects=[<rectangle>])`; then `autocad_press_pull_faces` on the new face by number, distance 100; then imprint a line 5 m away | Imprint: `faces_after` = `faces_before` + 1 (7), the rectangle kept; the pull raises only the 400 x 200 pad. The far line: `note` says nothing new was imprinted | NOT RUN |
| AR12 | Two test boxes 2000 apart, `autocad_solid_boolean` union into one solid; `autocad_separate_solid(<it>)`; then on a single box | `piece_count` 2, the second piece a new solid on the same layer and colour, the two volumes 300,000,000 each. The single box is refused "one piece already" | NOT RUN |
| AR13 | Ask to keep on: run AR1, AR4, AR8 and AR12, answering Discard each time | Each is taken back whole: no pyramid or wall left, the box its old size, the union one solid again | NOT RUN |
| AR14 | AR1-AR13 on AutoCAD 2025/2026 and 2021-2024 | As AR1-AR13 | NOT RUN (no PC with those versions yet) |

## Group AI - The drawing tools: UCS on every draw and modify tool, batch fills, arc breaks, closed multilines, control-point splines (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-96](DECISIONS.md), [D-97](DECISIONS.md); issues #50, #51, #52, #55, #56).
Built and tested offline only (`tests/test_draw_ucs.py`, `tests/test_batch_fills.py`,
`tests/test_break_arcs.py`, `tests/test_drafting_plugin.py`, and the C# `SplineCheckTests`); the
plug-in operations `close_multiline`, `add_cv_spline` and `edit_spline_fit_points` build for all three
targets but have never run. Needs the plug-in rebuilt and reinstalled, and the server restarted. Set a
plan UCS first for AI1-AI3: `autocad_set_ucs(mode='origin', origin=[1000,500], angle=30)`.
**Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AI1 | On the turned UCS: `autocad_draw_rectangle(corner1=[0,0], corner2=[2000,1000], coords='ucs')`, `autocad_draw_arc(center=[0,0], radius=500, start_angle=0, end_angle=90, coords='ucs')`, `autocad_add_text(text='A', position=[0,1500], rotation=0, coords='ucs')`, `autocad_insert_block(<any block>, position=[3000,0], rotation=0, coords='ucs')`; then PLAN, current UCS | Seen square to the UCS: the rectangle 2000 along its X and 1000 up, the arc a quarter from its X to its Y, the text and block reading along its X. `converted_from_ucs` names the 30 degree UCS. In the world (PLAN World) all four are turned 30 degrees about 1000,500 | NOT RUN |
| AI2 | On the turned UCS: `autocad_add_dimension(dimension_type='horizontal', point1=[0,0], point2=[2000,0], text_position=[1000,-300], coords='ucs')`; `autocad_move_entities(<rectangle>, displacement=[0,1200], coords='ucs')`; `autocad_rotate_entities(<rectangle>, base_point=[0,0], angle=15, coords='ucs')`; `autocad_array_entities(<circle>, rows=2, columns=3, row_spacing=400, column_spacing=600, coords='ucs')` | The dimension reads 2000 along the UCS X, 300 below; the rectangle moves straight up the screen and turns 15 degrees about the UCS origin; the six circles sit on a grid square to the UCS | NOT RUN |
| AI3 | `autocad_set_ucs(mode='origin', origin=[0,0,3000])`, then `autocad_draw_polyline(points=[[0,0],[1000,0],[1000,1000]], coords='ucs')`; LIST it | Elevation 3000. Then a flipped UCS (UCS X, 180): `autocad_add_text(..., coords='ucs')` is refused naming "flipped" and nothing is drawn; `autocad_draw_arc(..., coords='ucs')` draws the arc that looks right in that view | NOT RUN |
| AI4 | `autocad_batch_draw(operations=[{"type":"hatch","points":[[0,0],[100,0],[50,80]],"color":1},{"type":"hatch","points":[[200,0],[300,0]],"bulges":[0,1]},{"type":"hatch","points":[[400,0],[600,0],[600,200],[400,200]],"holes":[[[450,50],[550,50],[500,150]]]}])` | Three solid fills: a red triangle, a filled half-round, a square with an empty triangle in it. `created: 3`, `failed: 0`; LIST says HATCH, pattern SOLID, not associative; one Ctrl+Z takes all three | NOT RUN |
| AI5 | `autocad_batch_draw(operations=[{"type":"mtext","position":[0,0],"text":"NOTE 1\\PNOTE 2","width":2000,"height":250,"attach":"middle_center"},{"type":"mtext","position":[0,-1000],"text":<a 600-character note>,"width":3000}])` | Two MTEXTs: the first two lines centred on 0,0; the second holds the whole 600 characters, wrapped at 3000 | NOT RUN |
| AI6 | With DIMSCALE 50: `autocad_batch_draw(operations=[{"type":"dimension","point1":[0,0],"point2":[5000,0],"text_position":[2500,-800]},{"type":"dimension","dimension_type":"vertical","point1":[0,0],"point2":[300,3000],"text_position":[-800,1500],"text_override":"<> TYP"}])` | An aligned dimension reading 5000, 800 below; a vertical one reading 3000 TYP; both in the current dimension style and sized as DIMSCALE 50 (not tiny); DIMEDIT / grips work on them. Then the same with `coords='ucs'` on the 30 degree UCS and a style with DIMTIH on: the text reads along the UCS's X, not the world's (group 51). Also: was an entmade DIMENSION with no block name (group 2) accepted? | NOT RUN |
| AI7 | A polyline pipe run with a quarter bend (`autocad_batch_draw` polyline with a 0.4142 bulge) and a valve block inserted on the bend; `autocad_break_at_blocks(block_handles=[valve], gap=20)` | The run is cut either side of the valve's box; both pieces still bend on the same arc (LIST: same centre and radius); the valve sits in a clean gap. Then a closed circle-like polyline with a block on it: one open polyline is left, not two | NOT RUN |
| AI8 | `autocad_draw_multiline(points=[[0,0],[4000,0],[4000,3000],[0,3000]], scale=200, closed=true)` | `mitred: true`, no warning; the last corner at 0,0 is mitred like the other three (zoom in: no overlap); LIST says closed; one Ctrl+Z takes it | NOT RUN |
| AI9 | The same with the server on `--no-bridge` | Drawn with the first point repeated; `mitred: false` and the warning says the plug-in is not in the job | NOT RUN |
| AI10 | `autocad_draw_spline(points=[[0,0],[1000,1500],[3000,1500],[4000,0],[5000,800]], method='control_points', degree=3)`; LIST; SPLINEDIT shows the control vertices | One SPLINE, degree 3, 5 control points at those places, starting at 0,0 and ending at 5000,800; the curve touches only the ends; no fit points | NOT RUN |
| AI11 | The same with `closed=true`, then degree 1 and degree 2 | Closed: the curve comes round with no corner at 0,0 (zoom in), LIST says closed (note what it says about periodic). Degree 1: straight lines through the points | NOT RUN |
| AI12 | A fit spline (G1), then `autocad_edit_spline(handle, edits=[{"move":1,"to":[1000,800]},{"insert":4,"point":[4000,0]},{"remove":0}])`; `autocad_get_entity` before and after | Same handle; the fit points are exactly those in `points` (the second moved, one added after the last, the first gone); the curve passes through them; one Ctrl+Z puts it back. **Note whether `insert` at the count added after the last point**, and on a closed fit spline whether `fit_points` lists the first point again at the end | NOT RUN |
| AI13 | `autocad_edit_spline` on the AI10 control-point spline, and with `{"move": 9, ...}` on the G1 spline | Both refused before anything changes: no fit points; point 9 off the end | NOT RUN |
| AI14 | `autocad_make_shape(shape='section_mark', settings={"length":3000,"filled":true})` and `north_arrow`, `scale_bar`, `level_mark` with `filled: true` | Solid arrowheads, a half-filled north point, every other scale-bar division filled, a solid level triangle; each fill exactly inside its outline | NOT RUN |

## Group AN - Multileader and table styles made by the plug-in (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-104](DECISIONS.md), [D-105](DECISIONS.md); issue #68). Built and tested
offline only (`StylePlansTests.cs`, `tests/test_create_styles_plugin.py`; the add-in compiles against
the 2021, 2025 and 2027 reference assemblies). Needs the plug-in built from this change (it knows the
operations `multileader_style` and `table_style`), reinstalled, and the server restarted. Work in a
scratch metric drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AN1 | `autocad_create_styles(multileader_styles=[{"name": "HERON-LABEL-50", "text_height": 2.5, "scale": "1:50", "current": true}])`, then open MLEADERSTYLE | The row says `created: true`, `attachment: underline_bottom_line`, `arrow: closed_filled`, arrow size and dogleg 2.5, `scale: 50`, `current: true`. In the dialog: content Mtext, text height 2.5, left **and** right attachment "Underline bottom line", arrowhead Closed filled 2.5, "Automatically include landing" ticked, landing distance 2.5, "Specify scale" 50, and it is the current style. **Write down the landing gap it shows** (AutoCAD's own default) | NOT RUN |
| AN2 | After AN1, `autocad_add_multileader(landing=[1000,1000], arrows=[[0,0]], text="2 NOS FCU")` (it uses the current style) | The note's text sits on the landing line, the line running under the text (TLD look); text 125 high on screen (2.5 x 50); no `not_set` | NOT RUN |
| AN3 | `autocad_create_styles(text_styles=[{"name": "ROMANS", "font": "romans.shx"}], multileader_styles=[{"name": "TAG-DOT", "text_style": "ROMANS", "text_height": 2.5, "arrow": "dot", "arrow_size": 1.5, "landing_gap": 0.5, "attachment": "middle"}])` in a drawing that has never used the dot arrow | Both made in one call; `arrow_block_added: "_DOT"`; the dialog shows text style ROMANS, arrowhead Dot 1.5, landing gap 0.5, attachment "Middle of multi-line text". **Then SETVAR DIMBLK**: empty (closed filled) as before, and the DIMSTYLE dialog shows **no** "Style overrides" | NOT RUN |
| AN4 | AN3, then Ctrl+Z once | The text style, the multileader style and the `_DOT` block are all gone in one step (one undo mark round COM and the plug-in). **If it takes more than one Ctrl+Z, write how many** | NOT RUN |
| AN5 | `autocad_create_styles(multileader_styles=[{"name": "HERON-LABEL-50", "text_height": 3.5}])` after AN1; then the same with `replace=true` | First: the row says `created: false` and "already ... Pass replace=true", nothing changed. Second: `created: false`, text height 3.5; the dialog shows 3.5 and the scale back at 1 (a replaced style takes the same defaults as a new one) | NOT RUN |
| AN6 | `multileader_styles=[{"name": "BAD", "text_height": 2.5, "text_style": "NOPE"}, {"name": "GOOD", "text_height": 2.5}]` | BAD's row: "no text style called 'NOPE' ... Nothing was changed."; GOOD is made; MLEADERSTYLE lists GOOD, not BAD | NOT RUN |
| AN7 | `autocad_create_styles(table_styles=[{"name": "SCHEDULE-50", "text_height": 2.5, "scale": "1:50", "alignment": "left", "current": true}])`, then open TABLESTYLE | `text_heights` 125 / 125 / 125, `margins` 41.67 both (125 / 3), alignment title and header `middle_centre`, data `middle_left`, `current: true`. In the dialog, for Title, Header and Data: text height 125, alignment Middle Center / Middle Center / **Middle Left**, horizontal and vertical margins 41.67; it is the current table style | NOT RUN |
| AN8 | After AN7, `autocad_add_table(position=[0,0], title="AHU SCHEDULE", headers=["TAG","CFM"], rows=[["AHU-1","2000"]], style="SCHEDULE-50")` | The table takes the style: text 125 high, in the vertical middle of every cell, data left-aligned; `rows_aligned_middle: 3` | NOT RUN |
| AN9 | `table_styles=[{"name": "NO-TITLE", "text_height": 2.5, "title_row": false, "header_row": false}]`, then `autocad_add_table` with that style and rows only | `title_row: false`, `header_row: false`; the dialog's "Title" / "Header" rows show as off (the style's suppress flags); the new table starts with a data row | NOT RUN |
| AN10 | `table_styles=[{"name": "A", "text_height": 2.5, "alignment": "top left"}]`, then `multileader_styles=[{"name": "B", "text_height": 2.5, "scale": 0.02}]`, then `multileader_styles=[{"name": "C", "text_height": 2.5, "arow": "dot"}]` | A's row: "... vertical middle ...", B's: "'0.02' could be a ratio or a scale factor ... '1:50'", C: refused before anything ("arow is not an option"). None of the three is in the drawing | NOT RUN |
| AN11 | With Changes **off**: AN1 again | Refused by the padlock before anything; MLEADERSTYLE unchanged | NOT RUN |
| AN12 | AN1 with a plug-in built before this change | Refused: "Heron in AutoCAD does not have the operation 'multileader_style'. Update Heron ..."; nothing changed. With a text style in the same call: the text style is made and the multileader row carries that message | NOT RUN |
| AN13 | `autocad_add_table(position=[0,0], rows=[["A"]], style="NOPE")`, then `autocad_add_multileader(landing=[500,500], arrows=[[0,0]], text="X", style="NOPE")` | Each refused: "no ... style called 'NOPE' ... Make it with autocad_create_styles ... Nothing was left in the drawing." No empty table or bare leader in model space (`autocad_list_entities`), #191 | NOT RUN |

## Group AX - The palette's Undo and the UNDO mark, answers after a restore (D-130) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-130](DECISIONS.md); issues #206, #209, #244). Built and tested offline only
(bridge tests and Python tests). **Nothing here has run in AutoCAD.** The plug-in changed: build and
install it first. Changes on. Use a scratch drawing with UNDO on (UNDOCTL 5). **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AX1 | Ask to Keep on. Draw a line with Heron and press Keep. Open the Heron palette and press Undo on its card | The line goes; nothing drawn before it goes; `addin-*.log` says `palette undo: ... (_.UNDO _Back)` | NOT RUN |
| AX2 | Ask to Keep on. Draw a circle by hand. Start `LINE` in AutoCAD and leave it at its prompt, then ask Heron to draw a rectangle (if the job runs, press Keep), then finish your LINE | The palette's Undo for the rectangle, if offered, is `_.UNDO 1` in the log, never `_Back`; your circle and your line stay | NOT RUN |
| AX3 | As AX2, but press Discard | The answer says AutoCAD was in a command when the job began, not "UNDO is off (UNDOCTL)" | NOT RUN |
| AX4 | Ask to Keep off. Erase 4 objects with Heron (`autocad_delete_entities`) and answer "bring them back" | First line NOTHING CHANGED, saying all 4 were brought back; `heron_changes` erased 0; `autocad_activity` says erased 0; `autocad_undo_last` says there is nothing to undo | NOT RUN |
| AX5 | Ask to Keep off. A Heron job that erases some objects and adds others (for example an `autocad_sequence` that draws a line and erases two others; not join, explode, trim or break, whose question is "Keep the change, or undo the whole change?" since D-136, Group BC), answer "bring them back", then look at the palette card | First line DONE with erased 0; the card has no Undo button; `autocad_undo_last` says there is nothing to undo; the restored objects stay | NOT RUN |
| AX6 | Ask to Keep on. Draw a line with Heron and Keep. Then ask Heron to move a handle that does not exist (it refuses). Then `autocad_undo_last` | It says there is nothing to undo; the line stays | NOT RUN |
| AX8 | Ask to Keep on. Start `LINE` and leave it at its prompt, ask Heron to move an object, press Keep when asked, then look at the palette card and call `autocad_undo_last` | The card has no Undo button (the question's zoom is the last step); `autocad_undo_last` refuses, naming the zoom | NOT RUN |
| AX7 | After AX3 or any OUTCOME UNKNOWN job, `autocad_gaps` | That job's advice says to look at the drawing (or remove by hand), never "Press Esc, then try again" | NOT RUN |

## Group AZ - Select, Zoom, show and the Keep question: only drawing objects in the space in front (D-132) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-132](DECISIONS.md); issue #234). Built and tested offline only (bridge tests,
`ShowPickTests`). **Nothing here has run in AutoCAD.** The plug-in changed: build and install it first.
Changes on, a chat connected, Heron pressed, the Heron palette open (`HERONPALETTE`). Each row also
passes only if `addin-*.log` has no `eInvalidInput` and no `Palette select:` / `Palette zoom:` error.
Run X3 and X25 in Group X in the same session. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AZ1 | Ask to Keep off. In a drawing with no `_DOT` block yet, one `autocad_sequence` that makes a multileader style with arrow `dot` (`autocad_create_styles`) and draws two lines. Press **Select**, then **Zoom** on its card | Select: the two lines selected; the line under the list says "Selected 2 objects. N could not be selected: N are inside a block definition." (N is the arrow block's parts) Zoom: the view frames the two lines, still selected | NOT RUN |
| AZ2 | In a fresh drawing, ask the chat for a multileader style with arrow `dot_blank` and nothing else. If its card shows Select and Zoom, press each | Nothing selected, nothing zoomed; the line says "Nothing of this job can be selected here: N are inside a block definition."; no error. If the card has no buttons, record that (the job counted no objects) | NOT RUN |
| AZ3 | Draw a circle with the chat on the Model tab. Switch to a layout tab (not inside a viewport) and press **Select** on its card; then double-click inside a viewport and press **Zoom** | On the layout: "Nothing of this job can be selected here: 1 is on another layout or the Model tab. Switch to the tab they are on and press again." Inside the viewport: the circle is selected and the viewport frames it | NOT RUN |
| AZ4 | Ask the chat to set an attribute on a block (`autocad_set_attributes`), then press **Select** on its card | The block reference is selected (one object), not an error | NOT RUN |
| AZ5 | Ask to Keep **on**. In a drawing with no `_OPEN` block, one `autocad_sequence` that makes a multileader style with arrow `open` and draws one line; when the Keep box shows, look, then press **Discard it** | The box **does** appear (before the fix it could be skipped and the job discarded silently); it says "The object it made or changed is selected and in view." with the line selected; Discard removes the line, the style and the arrow block | NOT RUN |
| AZ6 | `autocad_show` with the handles of a line, a layer (from `autocad_list_layers`) and an erased object, then again with `isolate=true` | First: `shown` 1, the layer in `not_selectable` with reason `not_a_drawing_object`, the erased one in `not_found`; the line selected and framed. With isolate: only the line stays on screen; `end_isolation=true` brings the rest back. With only the layer handle and `isolate=true`: `shown` 0, `isolated` false, and no command left waiting at "Select objects" | NOT RUN |

## Group AY - Installer and release polish (D-131) (a shared Windows server, not this PC)

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AY1 | On a shared Windows server (Remote Desktop or Citrix) where a colleague has AutoCAD open in their own session and you have none: run `HeronAutoCAD-<version>-setup.exe`, then `Install.bat` from the zip, then Uninstall | Neither stops with "AutoCAD is open". Both finish. | NOT RUN |
| AY2 | Same server, now open your own AutoCAD, disconnect your Remote Desktop session without closing AutoCAD, sign in again and run the setup and `Install.bat` | Both stop with "AutoCAD is open. Close AutoCAD... Nothing was changed." | NOT RUN |
| AY3 | Download a release's `checksums.txt` and files onto Linux or macOS and run `sha256sum -c checksums.txt` | Each file says `OK` | NOT RUN |

## Group AV - Busy refusals in block, table, light and copy tools; save_view and a sheet's view (D-128) (AutoCAD 2027, this PC)

Added on 2026-11-23 (D-128, issues #189 and #190). Built and tested offline only
(`tests/test_busy_block_table_light_copy.py`, `tests/test_save_view_layout.py`). Server only: restart the
server after pulling; no plug-in build is needed. To keep AutoCAD busy past the message filter's 3 s,
open the Options dialog (OP) and leave it open. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AV1 | A block with 4 inserts that carry attributes. Options dialog open, `autocad_sync_attributes(block=...)` | "AutoCAD stayed busy ... press Esc"; no list of skipped inserts, no "touched"; after closing the dialog the same call syncs all 4 | NOT RUN |
| AV2 | Options dialog open, `autocad_table_from_excel` on a .csv, then `autocad_set_table_cells` on a table | Each says "AutoCAD stayed busy" (nothing written yet); never "DONE" with cells in `not_set` or `refused` | NOT RUN |
| AV3 | Options dialog open, `autocad_set_render_exposure(exposure=7)`, then `autocad_list_lights` | Both say "AutoCAD stayed busy"; never "This AutoCAD did not answer for EXPVALUE" and never a null exposure | NOT RUN |
| AV4 | Two drawings open, Options dialog open, `autocad_copy_from_drawing` for 2 handles that exist | "AutoCAD stayed busy"; never "has nothing with the handle(s)"; nothing copied | NOT RUN |
| AV5 | In a layout tab save a view named DETAIL-A (VIEW, New, in paper space). On the Model tab: `autocad_save_view(name="DETAIL-A", corner1=[0,0], corner2=[100,50], replace=true)`, then the same with `from_screen=true` | Refused both times: "'DETAIL-A' is a view of a layout (a sheet) ... nothing was changed"; `autocad_list_views` still lists DETAIL-A and the sheet's viewport that uses it is unchanged | NOT RUN |
| AV6 | On the Model tab save a view PUMP-AREA, then `autocad_save_view(name="PUMP-AREA", corner1=[0,0], corner2=[100,50], replace=true)`, then the same with `from_screen=true` | Both replace it ("replaced": true). If either is refused ("a view of a layout", or "did not say which tab"), a model view here does not report the Model layout's id as the fix assumed (it may report 0): report exactly what AutoCAD says, do not work round it | NOT RUN |
| AV7 | `autocad_save_view(name="PUMP-AREA", ..., replace=true)` with the Options dialog open | "AutoCAD stayed busy" (or OUTCOME UNKNOWN); the view PUMP-AREA is not left deleted without its replacement | NOT RUN |

## Group RV - Fixes from the review of the 2026-11-21 merges (D-116) (AutoCAD 2027, this PC)

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| RV1 | Admin on. `autocad_send_command` with `expect_box` / `press` on a box that never comes; close the chat (stop the server) before the command ends; then, with no Heron job running, open a box yourself (e.g. OPTIONS) | Heron leaves your box alone; `addin-*.log` shows no "dialog watch" line for it | NOT RUN |
| RV2 | `autocad_export_attribute_sheet`, then in Excel type `0051` and `1:100` over two values, save, `autocad_apply_attribute_sheet` | The attributes read `0051` and `1:100` exactly; nothing listed in `excel_converted` | NOT RUN |
| RV3 | `autocad_sequence` with steps `[autocad_switch_drawing, autocad_draw_line]` | Refused naming step 1; nothing drawn in either drawing | NOT RUN |

## Group AL - A busy AutoCAD past the message filter: never a false failure (AutoCAD 2027, this PC)

Added on 2026-11-21 ([D-100](DECISIONS.md), issue #36). Built and tested offline only
(`tests/test_busy_refusals.py` with fake COM, `tests/test_busy_sweep.py` reading the source).
Server only: restart the server after pulling; no plug-in build is needed. To keep AutoCAD busy
for longer than the filter's 3 s, open the Options dialog (OP) and leave it open, or start a REGEN
of a heavy realistic 3D drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AL1 | Options dialog open. `autocad_list_layers`, `autocad_list_entities`, `autocad_get_entity` on a circle | Within about 15 s each says "AutoCAD stayed busy ... press Esc"; none comes back with layers marked off, an empty list or `null` values; after closing the dialog each works | NOT RUN |
| AL2 | A UCS rotated 30 degrees. Options dialog open, `autocad_add_solid` (a box, `coords='ucs'`); close the dialog part-way through the wait | Either "AutoCAD stayed busy" and no box, or the box drawn square to the rotated UCS; never a box drawn in the world UCS | NOT RUN |
| AL3 | Ask to Keep on. Options dialog open, `autocad_draw_circle` | REFUSED - "AutoCAD stayed busy ... nothing was changed"; no circle; no "Error executing tool"; Heron's Activity says it ended | NOT RUN |
| AL4 | Ask to Keep on. Draw a circle, start a heavy REGEN in another drawing tab as you press Discard | Either "Discarded" with the circle gone, or OUTCOME UNKNOWN saying to look; never "UNDO is off" and never "Discarded" with the circle still there | NOT RUN |
| AL5 | `autocad_create_layer` for a new name while drawing tabs are switched by hand for 10 s (as Q1, held longer) | Either the layer is made or "AutoCAD stayed busy"; never "Could not create layer ... Call was rejected by callee" | NOT RUN |
| AL6 | During a busy spell part-way through a long edit (`autocad_modify_entity` on 50 objects, switch tabs while it runs) | OUTCOME UNKNOWN - look at the drawing; one Ctrl+Z takes it all back, any layers it unlocked locked again | NOT RUN |
| AL7 | `autocad_add_viewport` on a sheet while a REGEN keeps AutoCAD busy | Object snaps (OSMODE) are as they were afterwards, whatever the answer | NOT RUN |
| AL8 | D-149 (#270, 2026-11-23). Restart the server. The runner draws a line straight into model space, then sets `Radius` on it over COM (a property a line does not have) | Within a second or two: `PropertyRefused`, naming `'Radius'` and saying AutoCAD was not busy; never "Outcome unknown", "stayed busy" or "Lost the COM connection" after ten seconds | NOT RUN |
| AL9 | D-149 (#270). Options dialog open. `autocad_modify_entity` on a line, `layer='0'` | As AL1: "AutoCAD stayed busy ... press Esc" (or the change made once the dialog is closed); never "AutoCAD has no property" or "would not set" | NOT RUN |

## Group AD - Overkill, boundary, eTransmit, underlays and clips (AutoCAD 2027, this PC)

Added on 2026-11-21 for issues #112, #104, #118 and #114 (row AD13 on 2026-11-23 for #159, [D-146](DECISIONS.md); AD14, AD15 for #160, [D-150](DECISIONS.md)) ([D-84](DECISIONS.md), [D-85](DECISIONS.md),
[05 §35](05-known-limits.md#35-overkill-boundary-etransmit-underlays-and-clips-have-their-own-limits)).
Built and tested offline only (`tests/test_overkill.py`, `tests/test_cleanup_refs.py`); the plug-in
parts build for all three AutoCAD versions but have never run. Needs the new plug-in installed and
the server restarted. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| AD1 | Open an architect's DWG exported from Revit. `autocad_overkill` (no confirm), then `autocad_show` on three of the listed handles | A list by handle with reasons; the shown ones really lie on the kept line; the drawing is unchanged (nothing in Ctrl+Z, no erase question) | NOT RUN |
| AD2 | Same options with `confirm=true`; answer the erase question "keep them erased"; then Ctrl+Z once | Erased and stretched as listed; one undo step; the question names the count; Ctrl+Z brings every line back as it was. Again answering "bring them back": the erased lines return, the stretched ones stay stretched | NOT RUN |
| AD3 | `autocad_attach_underlay` a PNG with `width=42000`; a PDF with `page='2'`; a DWF without `page`; a DGN | The image is 42000 wide (LIST); page 2 of the PDF shows at the insertion point, scale and rotation asked; DWF and DGN show (write which sheet / model the DWF took); each on the layer asked; one undo step each | NOT RUN |
| AD4 | `autocad_clip_reference` the image to two corners, then `remove=true` | Only the inside of the rectangle shows; the clip comes off and the whole image shows | NOT RUN |
| AD5 | An xref attached at 5000,2000, scale 2, rotation 30. Draw a closed polyline with one arc over part of it; clip the xref to it. Then XCLIP > Generate polyline | The xref shows only inside the polyline; XCLIP's generated outline lies on the drawn one (arc in short steps) | NOT RUN |
| AD6 | A PDF underlay rotated 45, scale 0.5: clip it to a rectangle, then `remove=true` | The clip lies on the rectangle in the world (not shifted, not turned); remove shows the whole sheet | NOT RUN |
| AD7 | On the big plan that hung -BOUNDARY: `autocad_trace_boundary` inside one room with a `window` round it. Time it. Then the same with no window, zoomed to extents | With the window: the outline in a few seconds, area as LIST gives, the view back where it was, no BOUNDARY on the command line. Zoomed out with no window: refused over most_objects, nothing traced. Also write whether a room outside the window but on screen before the zoom changed the result | NOT RUN |
| AD8 | A room with a column inside: trace with `islands=true`, then `make='region'` | Polyline: outline + one island, `net_area` = outline - column. Region: one region with the hole, its area = `net_area` | NOT RUN |
| AD9 | On the big plan, trace with `timeout=1` and a window round the whole floor (raise `most_objects`) | Heron says it stopped waiting after 1 s; when AutoCAD finishes, at most one outline is made; a second call is not run twice | NOT RUN |
| AD10 | A saved drawing with a nested xref, a JPG, a PDF underlay, an SHX text style and a .ctb: `autocad_etransmit`. Unzip it on another PC (or rename the project folder) and open the drawing | The zip holds the drawing, both xrefs, the image, the PDF, the .shx, PlotStyles/x.ctb and the report; on the other PC every xref, image, underlay and font is found from the drawing's folder | NOT RUN |
| AD11 | `autocad_etransmit` on an unsaved drawing; on a saved one with Publish off; with `list_only=true` | Unsaved: refused, "save it first". Publish off: refused naming Publish, no file. list_only: the list, no file written | NOT RUN |
| AD12 | With the 1.7.0 plug-in still installed: attach a PDF, clip an xref, trace a boundary, eTransmit | Each says the plug-in does not have the operation and to update it; nothing changes in the drawing | NOT RUN |
| AD13 | Draw a polyline 0,500 > 0,0 > 1000,0 > 400,0 (its tail goes back along the last segment) and one with a spike part way along (0,0 > 10,0 > 10,5 > 10,0 > 20,0). `autocad_overkill(tidy_polylines=true)`, then the same with `confirm=true` and its `plan_id`; then Ctrl+Z once. Also a polyline whose width changes along it, doubled the same way | Dry run: the first under `rebuild` with segment 2 going, the spike and the varying-width one under `left` with why; nothing changed. Confirm: the same handle now 0,500 > 0,0 > 1000,0 (3 vertices, length 1500), no erase question; the spike one unchanged. Ctrl+Z once brings back all 4 vertices | NOT RUN |
| AD14 | With the new plug-in: a saved drawing with an xref saved as a full path in another folder (one with its own image), a JPG and a PDF underlay saved as full paths. `autocad_etransmit(as_zip=false)`. Open the packed drawing (from the pack folder) and its XREF palette; then the original's | `paths.rewritten` true; in the packed drawing the xref, image and PDF show their bare file name as saved path and load from the pack folder; the packed xref's own image too; the original drawing (and its file date) unchanged, its paths as before; no `heron-etransmit-` folder left in %TEMP%; the DWG version of the packed copy is the original's | NOT RUN |
| AD15 | With the plug-in from before #160 installed: `autocad_etransmit` | The pack is made as before (paths as saved), `paths.rewritten` false with the reason (update the plug-in) | NOT RUN |

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

## Group BA - Typed text refuses control characters; run_lisp's named box on a busy retry; a stopped job and expect_dialog (D-133) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-133](DECISIONS.md); issues #242 and #210). Built and tested offline only
(`tests/test_typed_text.py`, `tests/test_run_lisp_expect_retry.py`, the bridge test
`A_stopped_job_is_refused_a_named_button_for_a_box`). **Nothing here has run in AutoCAD.** BA1 and BA2 are
server only (restart the server). BA4 needs the plug-in built from this change installed. Changes on for
BA1 and BA2, Admin on for BA3 and BA4. Use a scratch drawing. **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BA1 | `autocad_save_view(name="A\nB", from_screen=true)` (a real line break in the name), then the same with a real Esc (`"A\u001bB"`) and a tab | Each is refused at once: "The view name holds a line break (an Esc character, a tab), which cannot be typed into AutoCAD's command line. ... Nothing was typed."; no view is made, no old view is deleted, `Command:` is free | NOT RUN |
| BA2 | `autocad_save_view(name="LIVING-3D", from_screen=true)`, then again with `replace=true` | Saved as before (the name is typed through `-VIEW _Save`); the second call replaces it; Arabic or accented names without spaces also save | NOT RUN |
| BA3 | Make AutoCAD busy (orbit a heavy 3D drawing, or start a long REGEN) and run `autocad_run_lisp('(+ 1 2)', expect_box='AutoCAD Message', press='OK')` several times | Either the result `3`, or "AutoCAD stayed busy ..."; **never** "give the box's exact title and one button, once per job" | NOT RUN |
| BA4 | Run a `autocad_send_command` with `expect_box` on a box that really opens (`_-PURGE _A * _N`, `expect_box='Purge - Confirm Purge'`, `press='Yes'`) and, in the middle of it, type HERONSTOP in AutoCAD; then, with Heron stopped, call anything with `expect_box` | The stopped call is refused with the HERONSTOP sentence, nothing sent; after typing HERONSTOP again, the same call works. If the timing cannot be hit, the plain case (call with `expect_box` while stopped) still must be refused | NOT RUN |

## Group BC - Replace edits undo the whole change; isolate an xref layer; the Keep question's zoom (D-136) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-136](DECISIONS.md); issues #208 and #212, and the D-132 follow-up). Built and
tested offline only (`tests/test_gate.py`, `tests/test_layer_states.py`, `tests/test_edit2d_tools.py`;
bridge tests `EraseWordsTests.cs`, `JobChangesTests.cs`, `BridgeTests.cs`, `PaletteTests.cs`). **Nothing
here has run in AutoCAD.** The plug-in changed: build and install it, then restart the server. Changes on,
**Ask to Keep off** unless a row says otherwise, the erase question on. A scratch drawing with UNDO on
(UNDOCTL 5). "As before the job" means: the same objects, the same handles, nothing doubled (select all
and count, or LIST at the spot). **Every row below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BC1 | Two wall lines A and B end to end: `autocad_join_curves([A, B])`. The box asks; press **Enter** | The box reads "Keep the change, or undo the whole change?", the first choice "Undo the whole change". After Enter: A and B are back as they were (A its old length, B there once, not under a long A); first line NOTHING CHANGED saying Heron undid the whole change; the palette card says discarded with no buttons; `autocad_undo_last` says there is nothing to undo | NOT RUN |
| BC2 | As BC1, but press **Esc**; then again and close the box with its X; then again and leave it until it closes by itself | Each time the drawing is as before the job, as in BC1 | NOT RUN |
| BC3 | As BC1, but press **Keep the change** | One joined line; B stays erased; first line DONE; the note says the modeller chose Keep the change; `autocad_undo_last` then brings A and B back (it goes back to the mark) | NOT RUN |
| BC4 | A plain block: `autocad_explode`, press Enter. Then again, press Keep the change | Enter: the block is back and none of its pieces is left on top of it. Keep: the pieces, no block under them | NOT RUN |
| BC5 | A circle and a line through its centre: `autocad_trim_extend` trim one half, press Enter. Then `autocad_break_curve` on the circle with two points, press Enter | Each time the circle is back and no arc is left on it | NOT RUN |
| BC6 | Turn UNDO off (`UNDO` > Control > None), then `autocad_join_curves` on two lines | REFUSED before anything is sent: it names UNDO off and "Undo the whole change"; the lines are unchanged. Turn UNDO back on (`UNDO` > All) | NOT RUN |
| BC7 | Any other erase: `autocad_delete_entities` on two lines, press Enter | The box is the usual one, word for word: "Heron erased 2 objects.", "Bring them back" first; the two lines come back (D-50 as before) | NOT RUN |
| BC8 | Switch **Ask before keeping erased objects** off in Settings, then `autocad_join_curves` on two lines | No box; the join stays; the note says they stay erased without asking. Switch it back on | NOT RUN |
| BC9 | Ask to Keep **on**: `autocad_join_curves` on two lines, press Discard | The Keep or Discard question asks (not the erase box); after Discard both lines are back as before | NOT RUN |
| BC10 | An xref whose layers include `MECH\|M-DUCT`, with layer 0 current: `autocad_isolate_layers(layers=["MECH\|M-DUCT"])`, then `action='unisolate'` | Only the xref's duct layer is seen; layer 0 stays current (turned off); no error. Unisolate puts every layer back | NOT RUN |
| BC11 | Same xref: `autocad_isolate_layers(layers=["MECH\|M-DUCT"], others="freeze")`, then `autocad_list_layers` | Refused, naming the xref layer and others='off' or 'lock'; nothing changed; no HERON-ISOLATE in the layer states | NOT RUN |
| BC12 | Ask to Keep on. Start `LINE` and leave it at its prompt; ask Heron to make a multileader style only (its arrow block cannot be selected), press Keep if the job runs (as in AX8); finish your LINE, then look at the palette card and call `autocad_undo_last` | `addin-*.log` shows `show: ... left out of the selection` and no zoom; the card's Undo and `autocad_undo_last` do not blame a zoom (they may still refuse for another reason, named) | NOT RUN |
| BC13 | A polyline whose width changes along it (PEDIT > Edit vertex > Width on one segment) and a line across it: `autocad_trim_extend` trim it | Still refused in `failed` with "width changes along it" (#212.3 now lets a retryable read error up; this proves a real varying width is not one). Record which error AutoCAD gave in the add-in or server log if any | NOT RUN |

## Group BG - Replace-shaped edits D-136 did not cover: steps of a sequence, and four more tools (D-140) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-140](DECISIONS.md); issue #255). Built and tested offline only
(`tests/test_gate.py`, `tests/test_sequence.py`, `tests/test_saved_and_release.py`). **Nothing here has
run in AutoCAD.** Server only (restart the server); the plug-in is the one Group BC needs (it has the
"Keep the change, or undo the whole change?" box). Changes on, **Ask to Keep off**, the erase question
on, a scratch drawing with UNDO on (UNDOCTL 5). "As before the job" is as in Group BC. **Every row below
is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BG1 | Two wall lines A and B end to end: `autocad_sequence` with step 1 `autocad_draw_line` (any line C) and step 2 `autocad_join_curves([A, B])`. The box asks; press **Enter** | The box is "Keep the change, or undo the whole change?". After Enter the drawing is as before the sequence: A and B as they were, **and no line C**; first line NOTHING CHANGED saying Heron undid the whole change | NOT RUN |
| BG2 | As BG1, press **Keep the change** | Line C and one joined line; B stays erased; first line DONE; `autocad_undo_last` then takes back the whole sequence (C gone, A and B back) | NOT RUN |
| BG3 | Turn UNDO off (`UNDO` > Control > None), then BG1's sequence. Turn UNDO back on afterwards | REFUSED before anything runs, naming the join step ("its step Join ...") and UNDO off; no line C is drawn | NOT RUN |
| BG4 | Save BG1's steps as a saved command (`autocad_saved_command` save, A and B as inputs), then run it on two new lines and press Enter | As BG1: the whole saved command is undone, nothing doubled | NOT RUN |
| BG5 | Two overlapping boxes: `autocad_solid_boolean(operation='union')`, press Enter. Then a plate and a cylinder through it: `subtract`, press Enter | Each time the two solids are back exactly as they were (the first solid at its old volume, no hole, the second there once, not inside a union) | NOT RUN |
| BG6 | A circle: `autocad_make_block` with its handle (keep_originals left out), press Enter. Then again with `keep_originals=true` | Enter: the circle is back, no insert on it, and no new block in the block list. With keep_originals: no erase box at all | NOT RUN |
| BG7 | A hanger block and a line: `autocad_associative_array(pattern='path', path=<the line>, count=4)`, press Enter | The hanger is back once, no array left on it | NOT RUN |
| BG8 | A closed polyline: `autocad_add_region(erase_outlines=true)`, press Enter. Then `erase_outlines` left out | Enter: the polyline is back and no region on it. Left out: no erase box | NOT RUN |

## Group BH - Lengthen; fillet and chamfer between a line and an arc (D-144) (AutoCAD 2027, this PC)

Added on 2026-11-23 ([D-144](DECISIONS.md); issue #154). Built and tested offline only
(`tests/test_edit2d_geometry.py`, `tests/test_edit2d_tools.py`). **Nothing here has run in AutoCAD.**
Server only (restart the server); no plug-in change. Changes on, **Ask to Keep off**, a scratch
drawing in millimetres. The runner measures BH1 to BH9 (`tools/live_check_lengthen.py`). **Every row
below is NOT RUN.**

| Row | Do | Pass looks like | Result |
|---|---|---|---|
| BH1 | A line 0,0 to 1000,0. `autocad_lengthen` mode=delta, value=500, points=[[900,0]]; then delta -200 with points=[[100,0]] | The line runs 0,0 to 1500,0, then 200,0 to 1500,0; same handle and layer; each call is one Ctrl+Z | NOT RUN |
| BH2 | Two lines 1000 long. `autocad_lengthen` mode=total value=2400 on one; mode=percent value=50, end=start on the other | 0 to 2400; and 500 to 1000 (the start end moved) | NOT RUN |
| BH3 | An arc 0 to 90 degrees, r 500. `autocad_lengthen` delta = 500 x pi / 4; then percent 50 with end=start | The arc keeps its circle and runs 0 to 135 degrees, then 67.5 to 135; `autocad_measure` of its length agrees with the numbers | NOT RUN |
| BH4 | A polyline 0,0 - 1000,0 - 1000,500. `autocad_lengthen` delta -700; then delta +200 with end=start | After the first: 800 long, two vertices (`autocad_polyline_info`); after the second: 1000 long, starting at -200,0 | NOT RUN |
| BH5 | An arc 0 to 90 degrees, r 500 at 0,0 and a line 100,300 to 1500,300. `autocad_fillet_chamfer` fillet, handles=[line, arc], radius=50 | A new arc r 50 centred 550 from the big arc's centre and 50 above the line, on the line's layer; the line starts at the tangent point; the big arc still ends at 90 degrees. Then the same two objects with AutoCAD's own FILLET r 50 (click the line on its right, the arc near its top): the same arc | NOT RUN |
| BH6 | Two arcs: r 500 at 0,0 from 0 to 90 and r 500 at 800,0 from 90 to 180. Fillet r 50 | A new arc r 50 centred 550 from both centres (above their meeting point); both arcs trimmed to the tangent points | NOT RUN |
| BH7 | Two open polylines: 0,0 - 1000,0 - 1000,300 and 1500,900 - 1500,600 - 1300,600. Fillet r 100 | Each polyline still has 3 vertices, ending at 1000,500 and 1100,600; one new arc r 100 at 1100,500 | NOT RUN |
| BH8 | BH5's line and arc: chamfer distance=40, distance2=40 | The chamfer line starts 40 along the line from the corner and ends on the arc 40 along it (the angle method with an arc is refused) | NOT RUN |
| BH9 | Lengthen a closed polyline, a circle, a line by -400 (its whole length), and a line on a locked layer; fillet a circle with a line | Each refused with its reason (closed, not a line / arc / polyline, would vanish, the locked layer named, "two lines ..."); nothing changes and no undo step is opened | NOT RUN |
| BH10 | BH1 to BH5 again with AutoCAD's own LENGTHEN (Delta, Total, Percent) and FILLET typed by hand on the same objects | The same lengths and the same fillet arc; record any difference (the arc end AutoCAD picks when no point is given) | NOT RUN |
| BH11 | AutoCAD 2025 / 2026 and 2021-2024 builds: BH1, BH3, BH5, BH7 | As in AutoCAD 2027 | NO MACHINE |
