# 05 - Known limits and traps

Each one was found the hard way. The fix is written beside it.

## 1. Reinstalling while the server runs

**Never run `pip install -e .` (or `.[dev]`) while any `autocad-mcp` server is running.** The locked
`.venv\Scripts\autocad-mcp.exe` makes pip abort half-way: it deletes `_editable_impl_autocad_mcp.pth`
and leaves a `~utocad_mcp-1.0.0.dist-info` folder, so `import autocad_mcp` fails on the next start.

**Fix:** recreate the `.pth` in `.venv\Lib\site-packages\` (its content is the full path of the `src`
folder, backslashes, no newline) and rename the dist-info folder back. To add another package, install
it by name instead.

## 2. A code change is not live until restart

A server started before an edit keeps running the old code. Restart the Claude session (or
reconnect the MCP server) after changing anything in `src/`.

## 3. Long AutoLISP fails silently

`autocad_run_lisp` expressions near 3,600 characters fail with no error. Keep chunks under about
700 characters. On 2026-11-09 (AutoCAD 2027) a ~3,000-character `defun` block arrived as nothing,
while calls under 2,000 worked all day, so `autocad_run_lisp` refused anything over 2,000. A
~2,400-character call ran but its result came after the 10 s wait and it reported a timeout: the
timeout note says to count what landed before sending it again.

**Since [D-76](DECISIONS.md) (2026-11-21)** the server cuts long code itself, between its top-level
forms, into pieces under 700 characters, run in order as one undo step. What is left:
- **One form over 2,000 characters is still refused**, never cut: make helpers with `defun` as
  separate top-level forms. At most 12,000 characters and 20 pieces a call.
- **A piece that fails stops the rest**, after the pieces before it ran. A LISP error is still found
  only by the 10 s wait running out, so a mistake in piece 5 takes 10 s to report.
- **A command split over two top-level forms** can land in two pieces: the first is cancelled
  ([§21](#21-a-command-left-open-by-autolisp-blocks-everything)) and the rest is not sent. Keep a
  `(command ...)` and all its answers in one form.
- None of it is proven in AutoCAD yet (NEEDS-CHECKING Z2-Z4).

## 4. Two sessions on one AutoCAD

Two Claude sessions driving the same AutoCAD collide: one switching the active drawing breaks the
other's batch. Agree who drives first, and check the active drawing name before each batch.

## 5. PDF on AutoCAD 2027

`Plot.PlotToFile(path, "DWG To PDF.pc3")` raises a bare "Exception occurred" on 2027. Configure the
layout for the pc3 first, then plot with the path only. Fixed in `autocad_export` on 2026-10-19 and
pinned by `tests/test_export.py`. The same route works for `PublishToWeb PNG.pc3`.

## 6. Plot styles on this PC

There is **no `monochrome.ctb`**. Only the custom `TRG *.ctb` tables (`TRG MECH.CTB` and others).

## 7. AutoCAD LT

Not supported at any version: LT ships no COM Automation server ([SETUP](SETUP.md)).

## 8. Run as the same user level

COM cannot connect from a normal process to an AutoCAD running as Administrator. Run both the same way.

## 9. A broken `.venv` after moving PCs or users

A `.venv` built under another Windows user or folder will not start. Rebuild it:
`python -m venv .venv` then `.venv\Scripts\python.exe -m pip install -e ".[dev]"`, and check the
path in `.mcp.json`, `.codex/config.toml` and the Claude Desktop config.

## 10. Live scripts need Heron connected

With the plug-in installed, `tools/smoke_test.py` and `tests/test_live.py` go through the gate like
Claude does: press **Heron** and turn on **Changes** (and **Publish** for PDF
plots) first, or start the server with `--no-bridge` for developer runs.

## 11. COM is still open to other programs

The padlocks stop Heron; they do not stop another program that drives AutoCAD over COM.

## 12. Escape hatches can still be re-run when busy

`send_command` and `run_lisp` paths that manage their own undo did not mark "write started", so a busy
retry could repeat them ([D-15](DECISIONS.md)). **Closed on 2026-11-21 ([D-76](DECISIONS.md)):** an
UNDO, U, REDO, MREDO or OOPS is marked as a write just before it is sent, so a busy signal after it
is OUTCOME UNKNOWN, never a second send; so is the gate's own UNDO Back for Discard. Not proven in
AutoCAD yet (NEEDS-CHECKING Z1, Z10).

## 13. Proven live on AutoCAD 2027 only

The plug-in passed every live check on AutoCAD 2027 (2026-10-26). The 2021-2024 and 2025-2026
builds compile and pass their offline tests, but have not run in those AutoCADs
([NEEDS-CHECKING](NEEDS-CHECKING.md) groups B and C).

## 14. A read's undo pause is not yet proven live

Reads should leave no undo step: the plug-in turns undo recording off for the length of a Read job
([D-34](DECISIONS.md)). Until row A31 passes, a plug-in built before 2026-10-27, or a read that ran
while AutoCAD was mid-command (the pause waits 2 s for AutoCAD to be idle, then goes ahead without
it), can still leave steps: the U then undoes the look, not the change. Press U again, or check the
object count.

## 15. A visual style is read back only through the plug-in

`autocad_set_3d_view` types the VSCURRENT command ([D-35](DECISIONS.md)); there is no VSCURRENT
system variable and COM has no visual style on a model viewport. Since [D-86](DECISIONS.md) the
tool asks Heron's plug-in which style the viewport has and gives it as `visual_style_found`; a
different one from the one asked for is in `not_set`. With `--no-bridge`, or a plug-in older than
this change, it is null with the reason, and `autocad_preview` is still the proof. A different
style from the one asked for is a `visual_style_warning`, not a failure: the reading can come from
the viewport's saved record, which may be behind the screen (`visual_style_found_from` says when).
The answers for
'shaded with edges' and 'shades of gray' are from the prompt's capital letters and are not yet
proven (row E34); AutoCAD's exact style names are row AE1.

## 16. A scale is written as on the sheet

`scale=10` is refused: it could be 1:10 or 10:1 ([D-36](DECISIONS.md)). Write `'1:10'`, or `'10:1'`
for an enlargement. A plain ratio of 1 or less (0.02 for 1:50) still works.

## 17. Ordinates measure from the UCS origin

`autocad_dimension_run(mode="ordinate")` needs the datum at the UCS origin, because that is where
AutoCAD measures ordinates from ([D-37](DECISIONS.md)). A datum elsewhere is refused with the
`autocad_set_ucs(mode="origin", ...)` call that moves it.

## 18. The 2026-10-28 drafting tools have their own limits

- `autocad_add_wipeout` draws where the work is: model space on the Model tab or inside an active
  layout viewport, otherwise the layout, because it types WIPEOUT; its edges are straight only, as
  WIPEOUT's are. A boundary polyline from the other space, or drawn on a flipped or tilted plane, is
  refused - give the corners as points.
- `autocad_draw_multiline` with `closed=true` repeats the first point: Automation has no close for an
  MLINE, so that last corner overlaps rather than being mitred.
- `autocad_create_linetype` sizes the gap for its text from an estimate (0.9 x height per letter for
  STANDARD); a wide font can crowd the dashes - give `text_width`. On a text style with a fixed height
  the text is scaled from that height when the linetype is loaded; written with `load=false` it
  assumes a style of height 0.
- `autocad_create_hatch_pattern` adds its folder to AutoCAD's support path, which stays in the
  profile ([D-39](DECISIONS.md)).
- None of the seven is proven in AutoCAD yet ([NEEDS-CHECKING group G](NEEDS-CHECKING.md)).

## 19. The plug-in operations (3D edits, super hatch) have their own limits

- They need plug-in **1.2.0** or newer in AutoCAD; an older one is told to update, and nothing is
  sent. With the server's `--no-bridge` they cannot run at all ([D-40](DECISIONS.md)).
- Edge and face **numbers** from `autocad_list_solid_faces_and_edges` hold only while the solid is
  unchanged: after a fillet, shell or press-pull the numbers move. List again. The words ('top',
  'vertical', 'front'...) go by the solid's box, so a face on a step half way up is not 'top':
  pick it by number. A face word only ever picks a flat face: a cone's side or a bowl's inside is
  picked by number.
- A chamfer is measured from one face, as AutoCAD's own is: its edges must be on that face.
- Press-pull moves flat faces only. Loft makes solids only: open outlines would make a surface, and
  are refused. Loft and thicken keep their outlines and surfaces (as with DELOBJ off).
- `autocad_super_hatch` fills an outline drawn flat in plan (world XY). Arcs in it are followed in
  short straight steps, as XCLIP stores any boundary: within 1/10,000 of the outline's size for a
  polyline's arcs and a circle (2 mm in a 20 m room), 16 steps per segment of an old-style 2D
  polyline, 128 round a spline. At most 10,000 tiles. The tiles are placed over the outline's whole box and clipped, so a thin L
  shape carries hidden tiles too.
- Whether one Ctrl+Z undoes a plug-in operation as one step is the reason for row H3; until it
  passes, treat that as unproven ([NEEDS-CHECKING group H](NEEDS-CHECKING.md)).
- `autocad_thicken_surface(both_sides=true)`: AutoCAD's API does not say whether the thickness is
  split between the two sides or added to each. Row H9 measures it; until then read the volume it
  reports.
- A plug-in operation keeps the one-chat hold for as long as it runs, and checks the padlock
  again when it starts. It may wait up to 30 s for AutoCAD to be free; a disconnect in those
  seconds does not stop it.
- None of the eight is proven in AutoCAD yet.

## 20. The tools from the ADN-DevTech study have their own limits

- `autocad_publish_pdf` publishes the drawing **as last saved**: save first, or it is refused. It
  publishes this drawing's own sheets only, not a folder of drawings. Each sheet uses its own page
  setup; a sheet whose page setup has no PDF-capable paper comes out on the publisher's default. It
  needs plug-in **1.3.0** or newer ([D-41](DECISIONS.md)).
- `autocad_xref_tree` finds an xref's file the way AutoCAD does first (full path, then from the
  drawing's folder, then the bare name beside it), but not through AutoCAD's support path: an xref
  found only there still reads `loaded`, because AutoCAD itself reports it loaded. Overlay or
  attach is not shown; COM does not say.
- `autocad_drawing_report` counts model space by type up to 50,000 objects, then gives the total.
- The busy message names the command for the plug-in's own operations (super hatch, 3D edits,
  publish), and only when the add-in saw the command start: one already running when Heron loaded,
  or a dialog box, is reported as "a command or a dialog box may be open".
- **Plant 3D drawings:** Plant 3D pipes, valves and equipment are .NET objects that AutoLISP
  `entmod` / `entmake` cannot change, so `autocad_run_lisp` edits on them will not take; Heron's
  COM tools are not proven on them either. Treat them as read-only until checked.
- None of it is proven in AutoCAD yet ([NEEDS-CHECKING group I](NEEDS-CHECKING.md)).


## 21. A command left open by AutoLISP blocks everything

`autocad_run_lisp` returns its value by having AutoCAD evaluate a second expression. If the first
one leaves a command waiting at a prompt (DVIEW, CAMERA, any `(command ...)` missing its last
answer), that second expression is typed into the prompt instead: AutoCAD sits in the command, the
banner shows "Evaluate AutoLISP" counting up, and later calls fail until someone presses Esc
(bedroom model, 2026-11-05). Running object snaps also catch typed points ("Too many objects
selected for INTERSECT").

**Fix:** in one expression, save OSMODE and set it to 0 (or put `"_non"` before each point),
answer every prompt including the exit, then `(while (> (getvar "CMDACTIVE") 0) (command))`, and
put OSMODE back. Never split an interactive command across two calls.

**Since 2026-11-05 the server does both itself** (cancel and snaps off; NEEDS-CHECKING J4, NOT
RUN). The rule still stands: a cancelled command did not finish, so `cancelled_command` in the
result means the expression has to be written again, complete. Long code is sent in pieces
([§3](#3-long-autolisp-fails-silently)): a command is cancelled at the end of its piece and the
pieces after it are not sent, so keep each `(command ...)` whole inside one top-level form.

## 22. Lights, materials, the saved 3D view and the render set-up have their own limits

- `autocad_add_light` and `autocad_create_material` need plug-in **1.4.0** or newer; an older one
  answers that it does not have the operation ([D-42](DECISIONS.md)). With `--no-bridge` they
  cannot run.
- Lights are photometric. They light as asked only with **LIGHTINGUNITS 2**; the tool warns, it
  does not change it. They show in a render, or in the realistic visual style with
  **DEFAULTLIGHTING 0**.
- A light's name is unique in model space only; the same light inside a block repeats with every
  insert, which is what a light block is for.
- A material's texture and bump images take their real size from `texture_size` (plug-in
  **1.4.1**, [D-46](DECISIONS.md)). Without it the image repeats every 1 drawing unit (1 mm in a
  metric drawing) and renders as a flat colour; the result warns. A non-square image's height runs
  along Y and up the walls; how a box mapping lays a face along X is not proven (K15).
- A glowing material glows in its own colour: `glow_kelvin` sets that colour, so it cannot be
  combined with `diffuse_rgb`. A glowing strip lights little around it; add lights for that.
- `autocad_save_view(from_screen=true)` types `-VIEW _Save`, so a name with spaces is refused.
- None of it is proven in AutoCAD yet ([NEEDS-CHECKING group K](NEEDS-CHECKING.md)).
- **None of the set-up tools renders** (Ajmal's rule): the camera, sun, lights and exposure tools
  set the render up, and the modeller presses Render. `autocad_render` (Admin) is the one tool that
  types `-render`; whether it stays is Ajmal's decision ([#158](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/158)).
- `autocad_add_camera_view`, `autocad_set_sun`, `autocad_list_lights` and `autocad_switch_lights`
  need the plug-in built from [D-86](DECISIONS.md) / [D-87](DECISIONS.md); an older one says it does
  not have the operation. The camera view and the sun work on the **Model tab only**. No camera
  glyph is drawn. The field of view Heron gives is across a 36 mm frame; AutoCAD's own Field of view
  may be measured another way (AE2). Perspective does not show in the 2D Wireframe style: the answer
  warns, and `autocad_set_3d_view(visual_style='realistic')` fixes it. `replace=true` moves the view
  only: a camera glyph that AutoCAD's own CAMERA command made for that view stays where it was. A
  layout's (paper space) view is never replaced.
- The sun's **date and time** belong to the current model viewport: another viewport, or a layout
  viewport, has its own sun. LATITUDE, LONGITUDE and TIMEZONE belong to the drawing. A UTC offset is
  turned into the first TIMEZONE code for it (3 is 3000); AutoCAD's other codes for the same offset
  (3001 ...) name other places at the same time. The sun's `azimuth` and `altitude` are as AutoCAD
  gives them; their unit is not proven (AE5).
- Turning the **sun on with default lighting on** may make AutoCAD ask its viewport lighting
  question; the dialog watch closes it with Cancel and names it (AE12). Switch default lighting off
  in the same call (`default_lighting=false`) to avoid it.
- A light is switched by handle or by name; a name inside a light block switches that light in
  every insert of the block. Lights in xrefs are not listed or switched.
- **Exposure** is written to EXPVALUE and EXPWHITEBALANCE, documented for AutoCAD 2016-2023. If an
  AutoCAD does not answer for one, the tool changes nothing and names the Render Environment &
  Exposure palette (RENDEREXPOSURE) instead. Not proven in 2027 (AE14).
- None of the render set-up is proven in AutoCAD yet ([NEEDS-CHECKING group AE](NEEDS-CHECKING.md)).

## 23. Sheets with a heavy 3D xref, and a paper space that will not answer

- With a 5 MB 3D drawing attached as an xref, `autocad_create_layout` came back "went busy" twice
  and the first viewport hung AutoCAD (its regen of every viewport redraws the xref). **Unload a
  heavy xref before sheet work** (`autocad_manage_xref action='unload'`) and reload it for the 3D sheet.
- After that, `doc.PaperSpace` threw a bare Automation error on a sheet made with `Layouts.Add`,
  while `ActiveLayout.Block` still answered. `autocad_status` now reports `paper_space_entities`
  from the layout's block (or null) instead of failing whole, and `autocad_add_viewport` falls back
  to MVIEW typed with the two corners. Both NOT RUN live (NEEDS-CHECKING S8, S9).
- Since [D-90](DECISIONS.md) the plug-in makes sheets and viewports in .NET, in the layout's own
  block, so neither touches `doc.PaperSpace`; title blocks go into `layout.Block`; `space="paper"`
  falls back to the active layout's block; `autocad_status` names a fact it cannot read in
  `unreadable` instead of failing. COM (and MVIEW) is left for a plug-in older than this. Still
  NOT RUN live (NEEDS-CHECKING AF1-AF11). The two places that pick the space themselves (the
  wipeout in `tools/drafting.py`, the dimension edits in `tools/dimensions_edit.py`) use the same
  fallback (#169).
- `create_material(replace=true)` with only `diffuse_rgb` kept the old texture image, which covers
  the colour; from plug-in **1.4.2** the image is cleared (K16, NOT RUN).

## 24. A busy AutoCAD turns calls away

AutoCAD turns a COM call away while it switches drawing tabs, starts a redraw or shows a dialog.
Since [D-57](DECISIONS.md) the server's worker thread asks such a call again before the refusal
reaches a tool, waiting up to 3 s in all for one piece of work. A tool that has written nothing
yet is also re-run for up to 10 s. What is left:
- **Busy for longer than that part-way through a change.** The answer is "Outcome unknown". Read the
  drawing back before trying again ([D-15](DECISIONS.md)).
- **A dialog left open.** The answer is "AutoCAD stayed busy". Close it, press Esc, and try again.
  Since [D-66](DECISIONS.md) a box AutoCAD opens *during* a Heron job is closed by the plug-in
  with Cancel and named in the answer ([§25](#25-the-dialog-watch-closes-every-new-box-in-a-job));
  a box that was already open when the job began is still yours to close.
- **Run LISP.** `autocad_run_lisp` waits through refused reads for its full 10 s ([D-58](DECISIONS.md)).
  A "timed out" that says AutoCAD stayed busy means the expression was sent and probably ran. Its
  first line is OUTCOME UNKNOWN, not DONE, since [D-77](DECISIONS.md).

All three are NOT RUN live (NEEDS-CHECKING group Q).

**Which command AutoCAD is in ([D-77](DECISIONS.md), #47).** A busy answer's first line now names
it ("it is still in the HATCH command"), from the plug-in's command tracker, with what the plug-in
counted so far. It needs the plug-in built from that change; an older one says no command. The
tracker follows AutoCAD's command and LISP events only, so a box opened outside a command reads as
"in no command now". NOT RUN live (NEEDS-CHECKING Z6-Z9).

## 25. The dialog watch closes every new box in a job

Since [D-66](DECISIONS.md) the plug-in closes a modal box AutoCAD opens while a Heron job runs
(Cancel, else No, else Esc; never OK or Yes) and the answer names it (`heron_dialogs`).
- **A box you open yourself while the banner shows a job is closed too.** Heron cannot tell who
  opened it. Wait for the banner to go before opening a dialog.
- **The step that box belonged to did not finish.** "Nothing was kept from that step" means what
  the box asked for (a file to open, a save) did not happen. Read the drawing back before trying
  again.
- **A Yes / No box with no Cancel gets No.** For the rare box where No loses work (for example
  "Save changes?" without a Cancel button), that is what happens. AutoCAD's own close-drawing
  question has Cancel, so it gets Cancel.
- **A box that ignores Cancel and Esc stays open.** The answer says so; close it by hand.
- **A named answer needs the exact title** ([D-74](DECISIONS.md)): the box's title bar, word for
  word, same capitals. A box whose title differs, or that lacks the named button, gets Cancel / No /
  Esc as before. One named answer per call, used once. It presses the button by its control id, so
  a box drawn without Windows buttons (some WPF boxes) is not answered that way.
- **Not proven in AutoCAD yet** ([NEEDS-CHECKING group V](NEEDS-CHECKING.md)).

## 26. A job that changed nothing may still leave an undo step

Heron for Revit takes back a kept job that changed nothing, so its undo list gets no blank entry
(its D-160). In AutoCAD this is only partly done ([D-62](DECISIONS.md), issue #80):
- **Where an empty step could come from.** The plug-in opens no undo group of its own; reads leave
  none at all ([D-34](DECISIONS.md)). The groups come from the server: each change tool opens one
  (`StartUndoMark` / `EndUndoMark`) around its writes, and with Ask to Keep on, or for a dry run, the
  gate puts an `UNDO _Mark` down first ([D-18](DECISIONS.md)).
- **Fixed.** The tools that most often have nothing to do now look first and write only what
  differs: `autocad_modify_entity`, `autocad_set_attributes`, `autocad_find_replace_text`,
  `autocad_set_dynamic_properties`, the layer tools, `autocad_set_variable` and
  `autocad_drawing_setup`. Asked for what is already there, they open no group, and the answer says
  `NOTHING CHANGED`.
- **Not fixed.** Other change tools open their group before they know there is nothing to do, and
  with Ask to Keep on Heron's mark stays in the list for a job that wrote nothing. Whether AutoCAD
  keeps an entry for an empty group, or for a mark with nothing after it, is not known: it has not
  been checked in AutoCAD (NEEDS-CHECKING T7).
- **Why it is not taken back afterwards.** Taking an entry out means one more `UNDO`. If AutoCAD
  kept no entry, that `UNDO` undoes the modeller's own last change instead. And the plug-in counts
  drawing objects only, so "counted nothing" is not proof: a layer or a variable may have changed.
  Until T7 says what AutoCAD does, Heron does not guess.

## 27. Attribute sheets, folder checks and the Companion page have their own limits

From [docs/13](13-sheets-folders-companion.md); all NOT RUN live (NEEDS-CHECKING group Y).
- **A number the modeller types in Excel comes back as Excel shows it.** Typed `1.50` reads `1.5`.
  Cells Heron wrote stay text; only a cell typed over is a number. Type a leading `'` in Excel to
  keep `1.50`.
- **What Excel turns into a date, a time, a fraction or a percent is not written** ([D-75](DECISIONS.md)).
  `1:100` becomes a time, `05.01` or `1/50` a date, `50%` the number 0.5; the answer lists those
  cells (`excel_converted`) and writes none of them. Type them with a leading `'` (`'1:100`).
- **A row is used only when its Block matches the block with that handle here** ([D-75](DECISIONS.md)).
  A sheet from another drawing is mostly caught that way; the workbook also names the drawing it
  came from, and the answer warns when it is not this one. A CSV names none, so it gets only the
  Block check.
- **A blank cell never empties an attribute.** That is on purpose (Revit's rule): use
  `autocad_set_attributes` to set one to nothing.
- **A CSV has no "As exported" copy**, so a value changed in the drawing since the export is
  overwritten by an older one in the CSV if they differ. Use the `.xlsx`.
- **An attribute tag used twice in one block** is written to both.
- **The folder check never closes a drawing that was open before,** even under another name for
  the same file (a mapped drive and its UNC path); it closes only what it opened itself.
- **The folder check opens each drawing in AutoCAD,** so the office start-up (acaddoc.lsp, a
  missing-font box) runs for each; the dialog watch (D-66) closes a box it shows, and that drawing
  may then be NOT RUN. Xrefs load as usual. It is slower than one drawing: about the time AutoCAD
  takes to open each.
- **The Companion page's view and selection are as of the last `autocad_companion` call**, not
  live: the page says when they were read. The activity list is updated after every job.


## 28. Attributes, Excel tables and the copy between drawings have their own limits

From [D-82](DECISIONS.md) and [D-83](DECISIONS.md); all NOT RUN live (NEEDS-CHECKING group AC).
- **ATTSYNC, the Excel link and its update are done by the plug-in.** A plug-in built before them
  answers that it does not have the operation: rebuild and reinstall it. The Excel table then
  falls back to a filled table and says so; ATTSYNC stops with nothing changed.
- **ATTSYNC reaches inserts in model space and on the sheets,** not inserts nested inside other
  blocks' definitions ([#156](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/156)). An insert on a locked layer is skipped and listed. An attribute holding a
  field, or a multi-line one, keeps its own text, place and size (`kept_as_they_were`).
- **A tag that appears twice in one block is matched in order**: the first definition of it takes
  the first value of it on each insert.
- **ATTSYNC does not reorder an insert's attributes**: the ones kept stay where they were in its
  list, and new ones follow in the definition's order.
- **AutoCAD's data link may need Microsoft Excel on the PC.** Not known until tried (AC7). When the
  link reads nothing, the plug-in refuses it and the tool fills the table from the sheet instead,
  with the reason in `not_linked_because`.
- **A linked table shows the Excel range exactly:** no title row is added (put the title in the
  sheet), and its cells cannot be changed with `autocad_set_table_cells` (change the sheet, then
  `autocad_update_table_links`). A filled table does not update by itself.
- **A filled table leaves out what Excel only shows** as a date, a time, a fraction or a percent
  (listed in `excel_converted`), as the attribute sheet does ([D-75](DECISIONS.md)). Merged cells in
  Excel come in as their top-left value only.
- **A table is at most 500 rows, 40 columns and 5,000 cells** in one call: give a smaller range.
- **Copy from another open drawing lands in the active drawing** (the one checked with
  `autocad_status`). To copy the other way, switch to the target first. A block, layer or style
  name that both drawings have is the target's own: the copies show the target's version.
  Coordinates are world coordinates in each drawing; the copies are moved, not turned or scaled.
