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
700 characters.

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

`send_command` and `run_lisp` paths that manage their own undo do not mark "write started", so a busy
retry could repeat them ([D-15](DECISIONS.md)).

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

## 15. A visual style cannot be read back

`autocad_set_3d_view` types the VSCURRENT command ([D-35](DECISIONS.md)); there is no VSCURRENT
system variable and COM has no visual style on a model viewport, so the tool cannot report which
style is current. `autocad_preview` shows it. The answers for 'shaded with edges' and 'shades of
gray' are from the prompt's capital letters and are not yet proven (row E34): if one is not taken,
the tool cancels the command and says so in `not_set`.

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
result means the expression has to be written again, complete.

## 22. Lights, materials and the saved 3D view have their own limits

- `autocad_add_light` and `autocad_create_material` need plug-in **1.4.0** or newer; an older one
  answers that it does not have the operation ([D-42](DECISIONS.md)). With `--no-bridge` they
  cannot run.
- Lights are photometric. They light as asked only with **LIGHTINGUNITS 2**; the tool warns, it
  does not change it. They show in a render, or in the realistic visual style with
  **DEFAULTLIGHTING 0**.
- A light's name is unique in model space only; the same light inside a block repeats with every
  insert, which is what a light block is for.
- A material's texture and bump images take their real size from `texture_size` (plug-in
  **1.4.1**, [D-45](DECISIONS.md)). Without it the image repeats every 1 drawing unit (1 mm in a
  metric drawing) and renders as a flat colour; the result warns. A non-square image's height runs
  along Y and up the walls; how a box mapping lays a face along X is not proven (K15).
- A glowing material glows in its own colour: `glow_kelvin` sets that colour, so it cannot be
  combined with `diffuse_rgb`. A glowing strip lights little around it; add lights for that.
- `autocad_save_view(from_screen=true)` types `-VIEW _Save`, so a name with spaces is refused.
- None of it is proven in AutoCAD yet ([NEEDS-CHECKING group K](NEEDS-CHECKING.md)).
