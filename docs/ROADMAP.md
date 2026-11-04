# Roadmap

Ideas and known gaps, **not started**. Move an item to [HANDOVER](HANDOVER.md) when work begins and
to [CHANGELOG](../CHANGELOG.md) when it lands. Proving what is built comes first:
[NEEDS-CHECKING](NEEDS-CHECKING.md).

## Plug-in

- [ ] A Companion page like Heron's in Revit (drawing, view, selection, activity list).
- [ ] Emergency stop: a ribbon button that refuses every job until pressed again.
- [ ] Sign the add-in DLLs, so AutoCAD's SECURELOAD never asks.
- [ ] An installer `.exe` / `.msi` for modellers (today: two Python scripts).
- [ ] Move tools into the plug-in one at a time where it pays off (speed, true transactions), keeping COM as the fallback.

## Found in the first live checks (2026-10-26)

- [ ] A batch still leaves one `Command:` prompt per piece in the history (about 27 for 41 objects).
  Harmless; fewer, larger pieces may be possible through the plug-in (the 600-character limit was
  measured for COM SendCommand).
- [ ] `autocad_preview`: the picture comes out portrait with the drawing at the left edge; fit and
  centre it, landscape when the drawing is wide.
- [ ] **Choose which AutoCAD** when several are open (like Heron's `revit_use_session`): today the server always takes the one COM hands it, usually the first started (A15).
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
  `autocad_set_3d_view` can prove the style took instead of relying on `autocad_preview`.
- [x] `tests/test_geometry.py`: two tests compared lists of point pairs with `pytest.approx`, which
  pytest 9 refuses ("does not support nested data structures"); CI turned red on 2026-10-28 when
  it picked up pytest 9. Now compared as flat coordinate lists, same values and tolerance.

## Found on 2026-10-28 (automation room power and control SLDs, AutoCAD 2027)

- [ ] **Change the shape of something already drawn.** `autocad_modify_entity` changes layer,
  colour, text and radius, but not a polyline's vertices or a line's end points. A box drawn too
  tall had to be deleted and drawn again, and a delete needs the modeller's yes each time. Add
  vertex / end-point editing (or a stretch tool) with offline tests, then a live row.
- [ ] `autocad_preview` with `area='extents'` on an A1 schematic drawn at 1:1 showed only the two
  frame rectangles; `area='window'` over the same parts showed everything. Find out why before
  trusting an extents preview of a full sheet.
- [ ] A chat's server keeps the code it started with: `autocad_drawing_setup(scale='1:1')` failed
  with the fault already fixed in a2acf6a, because that server was older than the merge. Have
  `autocad_status` report the server's version or commit so a stale server shows up at once.

## Asked for on 2026-10-28, not buildable over COM

- [x] **Super hatch** with a block: `autocad_super_hatch`, done by the plug-in (D-40, 2026-10-29).
  Built and compiled for every version; live rows H10-H12 NOT RUN.
- [ ] Super hatch with an image, an xref or a wipeout as the tile (Express Tools offers them).
- [x] **3D modelling commands** with no ActiveX call: loft, fillet / chamfer edges, shell,
  press-pull, thicken, and the face and edge listing they pick from - done by the plug-in (D-40,
  2026-10-29). Built and compiled; live rows H1-H9 and H13 NOT RUN, so **not yet proven**.
- [ ] Loft to a surface (open outlines), surfaces from curves (PLANESURF, NETWORK) and meshes.
- [ ] `autocad_draw_multiline` close with a mitred corner (MLINE's own Close) - needs the plug-in.
- [ ] `autocad_draw_spline` by control points, and editing a spline's fit points.

## Server

- [x] Dynamic blocks: read and set properties (`autocad_get/set_dynamic_properties`). Authoring
  parameters and actions has no API; it stays a Block Editor job.
- [x] The Lee Mac ideas: all built ([08](08-lee-mac-study.md)).
- [ ] `autocad_break_at_blocks` for polylines with arcs, through the plug-in's curve splitting.

- [ ] `autocad_batch_draw`: hatch, mtext and dimension operations. Polyline bulges and text
  justification landed with the shape library (D-30); these three are what is left.
- [ ] A hatch or solid fill for the furniture shapes: an arrowhead and a north point come out as
  outlines today, because a batch has no fill.
- [ ] `autocad_make_shape`: a 3D shape group (duct runs, pipe spools) once the solid tools have a
  live check behind them.
- [ ] Flatten a 3D solid to 2D views for a shop drawing (AutoCAD's SOLPROF / FLATSHOT). No
  Automation call, so it needs the plug-in or an Admin command.
- [ ] Multileader, table and dimension **style** creation from `autocad_create_styles`: no
  Automation API for the first two, and a dimension style already works, so this is really
  "bring the office styles in" - `autocad_import_from_drawing` does it today.
- [x] Draw an attribute schedule as an AutoCAD table: `autocad_add_table` ([10](10-geometry-annotation-3d.md)).
- [ ] Standards check against a reference DWG / DWS, not only a rules file.
- [ ] A layer-standard rule file shipped for Ajmal's own office standard, beside the `ifc` preset
  in `tools/convert.py` (which is a starting point, not a standard).
- [ ] Read DXF / DWG files without AutoCAD (ezdxf, plus the ODA converter for DWG), read only.
- [x] Paper-space layouts and viewports: `autocad_create_layout`, `autocad_page_setup`,
  `autocad_place_title_block`, `autocad_add_viewport` (D-27, [09](09-sheets-and-coordinates.md)).
- [ ] `coords="ucs"` on the single-entity `autocad_draw_*` and `autocad_modify_*` tools. Today only
  `autocad_batch_draw` has it; the rest need each tool's rotation and planar vertex list converted
  too, and no live check behind it yet (D-27).
- [ ] Multileader, table and plot-style-table creation: no Automation API, so today they come in
  with `autocad_import_from_drawing`. Worth moving into the plug-in.
- [ ] `autocad_add_viewport`: clip a viewport to a polyline, and annotative viewport scales.
- [ ] A sheet-set tool: one call per drawing list (sheet number, title, scale, view) across a whole
  package, on top of `autocad_sequence`.
- [ ] Split long `autocad_run_lisp` expressions instead of failing silently.
- [ ] From the ADN-DevTech study ([11](11-adn-repos-study.md)), all new code written fresh:
  - **Multi-sheet PDF**: publish every layout of a folder of drawings to one PDF (DSD file and the
    Publisher), as a plug-in operation behind the Publish padlock.
  - **Plot engine in the plug-in** instead of `PlotToFile`, which fails on 2027
    ([05 §5](05-known-limits.md#5-pdf-on-autocad-2027)). Prove on 2027 first, then 2021-2026.
  - **Xref tree report** (read only): found name, saved path, resolved or not, nested levels.
  - **Drawing audit** (read only): layers, blocks, styles and units in one call, for a received DWG.
  - **Document events** in the add-in (command started / ended, drawing activated) to feed the
    wrong-drawing guard and the Companion activity list; no separate COM service.
  - **Busy / idle from lock-mode and command-ended events**, instead of a fixed wait (rows D8, D33).
  - **Memory check**: `acad.exe` Private Bytes before and after 100 Heron calls; pass within 10%.
  - **Known limit**: Plant 3D objects cannot be changed by AutoLISP `entmod` / `entmake`; check
    what COM can do on them before an MEP user relies on it.
- [ ] `core/audit.py`: with `%LOCALAPPDATA%` unset, `audit_dir()` resolves to a relative
  `Heron/autocad/audit` in the working directory. Windows always sets it, so this only
  shows up running the code off Windows; worth an explicit fallback anyway.
- [ ] `send_command` / `run_lisp` that manage their own undo do not mark "write started", so a busy retry can still re-run them ([D-15](DECISIONS.md)).

## Repository

- [ ] Tag `v1.6.0` after NEEDS-CHECKING groups A, D, E and F pass - `tools/live_check.py --group all --write` does D, E and F.
- [ ] Later: offer this repository to Heron AI as its AutoCAD adapter when Heron's capability registry is ready ([D-12](DECISIONS.md)).
- [ ] With a sheet tab active, `autocad_status` and `autocad_add_table(space="paper")` raised a bare
  `Exception occurred` (2026-10-28, row D33). Status is what the gate waits for, so every tool was
  blocked until the Model tab was clicked. Reproduce live, find the call (suspect `doc.PaperSpace`),
  and let status answer in paper space.
- [ ] `autocad_create_layout` answered `Outcome unknown: AutoCAD went busy` on every call although
  the tabs were made (2026-10-28, row D8). Find which step goes busy.
