# 03 - Tools reference

The live list, always right: `.venv\Scripts\autocad-mcp.exe --list-tools`. This page groups them and
adds what the one-line descriptions leave out.

**Levels.** Every tool has a level ([`core/risk.py`](../src/autocad_mcp/core/risk.py)) that decides
which padlock it needs in AutoCAD: Read and View need only the connection; Change needs **Changes**;
Publish needs Changes + **Publish**; Admin needs Changes + **Admin** ([06](06-heron-plugin.md)).
The group headings below give the level.

**Rules for every tool**

- Coordinates are in the drawing's own units. Call `autocad_status` first to learn them.
- Angles are **degrees**.
- Entities are identified by their **handle**. Creation and query tools return it; modify tools take it.
- Drawing tools share `layer`, `color`, `linetype` and `space` options. A missing layer is created
  and reported.
- **Coordinates are WORLD coordinates.** `autocad_status` reports the drawing's UCS and warns when
  it is not the world one. `autocad_batch_draw`, `autocad_make_shape`, every `autocad_draw_*` tool,
  text, mtext, dimensions, blocks and the move / copy / rotate / scale / mirror / array tools take
  `coords="ucs"` ([D-96](DECISIONS.md)); for the rest convert first with `autocad_convert_points`
  ([09](09-sheets-and-coordinates.md)). A flipped UCS refuses text, blocks, dimensions, multileaders,
  tables, xrefs and super hatches.
- `autocad_batch_draw` polylines take **`bulges`** (one per vertex, `tan(sweep/4)`, positive
  anticlockwise) so arcs stay part of the object, and text takes **`align`** and `style`.

## Session and files (Read / View; save and export are Publish)

| Tool | Purpose |
|---|---|
| `autocad_status` | Connection check, units, current layer, entity counts |
| `autocad_list_drawings` | Every drawing currently open |
| `autocad_create_drawing` | New drawing, optionally from a template |
| `autocad_open_drawing` | Open a .dwg or .dxf |
| `autocad_save_drawing` | Save, or Save As to a new path |
| `autocad_switch_drawing` | Make another open drawing active |
| `autocad_saved_command` | **Change.** Keep a job that worked as a named command with `{{inputs}}`, and run it again exactly: the same steps through the same gate as `autocad_sequence`, nothing planned again ([D-55](DECISIONS.md)) |
| `autocad_activity` | **Read.** What Heron did in this chat, newest first: tool, drawing, outcome, created handles, what the plug-in counted; and whether its last change can still be undone ([D-54](DECISIONS.md)) |
| `autocad_why` | **Read, needs no AutoCAD.** For one job in plain words: the real reason it cannot run (no tool, nothing connected, a plug-in older than the tool needs, server and plug-in from different releases) and what to do, worst first; names the padlocks the job needs, which it cannot see from outside AutoCAD (D-59) ([D-67](DECISIONS.md)) |
| `autocad_gaps` | **Read, needs no AutoCAD.** The last N days (1-90) of Heron's audit log: calls per tool, failures by plain reason with what to do, the slowest jobs. Drawings by file name only, no contents ([D-67](DECISIONS.md)) |
| `autocad_layer_standard` | **Read, needs no AutoCAD.** The office layer standard: `template` puts an empty CSV (layer, color, linetype, lineweight, plot, description, replaces, required) in `%LOCALAPPDATA%\Heron\autocad\standards\`; `import` loads the filled CSV as the office standard (any problem: nothing imported, each named with its row); `show` says which standard `office` means and what it holds, or reads a named CSV without importing it; `remove` unloads it. Until one is loaded, `office` is the generic MEP example that ships with Heron ([D-120](DECISIONS.md)) |
| `autocad_read_file` | **Read, needs no AutoCAD.** A `.dxf` on disk (with ezdxf), or a `.dwg` / `.dws` / `.dwt` when the free ODA File Converter is installed (found, never downloaded; else a plain refusal): `summary` (version, units, extents, counts, most placed blocks, layouts, xrefs), `layers` with objects per layer, `blocks` with placed / nested counts and attribute tags, `text`, `attributes` (JSON or CSV), `styles`. Never changes the file; reads what was last saved ([D-92](DECISIONS.md)) |
| `autocad_undo_last` | **Change.** Undo Heron's own last change, only when the plug-in saw no change since (the modeller's work is never taken with it), in the same drawing, one level ([D-54](DECISIONS.md)) |
| `autocad_project_notes` | **Read.** Keep the modeller's answers (scale, standard, text heights) for the project (the drawing's folder); `autocad_status` hands them to every chat ([D-53](DECISIONS.md)) |
| `autocad_checklist` | **Read.** The modeller's own check list, saved once and run before issue: PASS / FAIL / NO DATA / NOT RUN per line, a coverage line ("2 of 4 decided, 1 no data, 1 not run"), the failing handles and each line's source; `before issue` ships ready. `project` lays this project's changes (severity, target, on/off only) over the office list. `office_folder` names a shared folder (once per PC) the office lists are read from; when it cannot be reached, this PC's copy is used and the run says so. Every line names the file it came from ([D-52](DECISIONS.md), [D-64](DECISIONS.md), [D-93](DECISIONS.md)) |
| `autocad_share_checklist` | **Publish.** Puts a check list in the office folder (`office_list`), or this project's changes in the drawing's folder as `Heron check list changes.json` (`project_changes`), for the whole team. A different file already there is replaced only with `replace=true`, naming who saved it and when; what was there is kept as `previous` ([D-93](DECISIONS.md)) |
| `autocad_checklist_report` | **Publish.** Runs a check list and saves it as a new `.xlsx` and `.html` next to the drawing; an earlier report is never overwritten (` (2)`, ` (3)`) ([D-65](DECISIONS.md)) |
| `autocad_check_folder` | **View.** Runs a check list over every `.dwg` in a folder (`subfolders` too): each opened read only, checked with its own project's changes, closed unsaved; an open drawing is checked where it is; the modeller's drawing is active again at the end. Verdict and coverage per drawing, worst first; one that will not open is NOT RUN with the reason ([D-70](DECISIONS.md)) |
| `autocad_companion` | **Read.** Opens the Heron Companion page: one HTML file per chat on this PC with the drawing, units, layout, view, selection and this chat's activity, rewritten after every Heron job. No server, no port, no script; it sends nothing to AutoCAD. `stop` ends the updates ([D-71](DECISIONS.md)) |
| `autocad_use_autocad` | **Read.** List the AutoCADs connected to Heron, or pick the one to work in. One connected: used without asking. Two or more: nothing is sent until one is picked ([D-49](DECISIONS.md)) |
| `autocad_export` | PDF, DWF, DXF, WMF, SAT, BMP, EPS, STL. DWF plots like PDF, through `DWF6 ePlot.pc3` ([D-111](DECISIONS.md)). PDF and DWF take `paper_size` (`A3`, `A1 portrait`), `area` (`extents` default, `layout`, `limits`, `display`, `window`, `view`), `corner1`/`corner2`, `view_name` and `scale` |
| `autocad_zoom` | Extents, all, or a window |
| `autocad_show` | **View, done by the plug-in.** Selects the objects given by handle and zooms to them, so "which ones?" is answered in the drawing; `isolate` hides the rest for now (ISOLATEOBJECTS, not saved), `end_isolation` brings it back. At most 500 at once |
| `autocad_publish_pdf` | **Publish, done by the plug-in.** The drawing's sheets in ONE multi-page PDF through AutoCAD's publisher, in tab order, each with its own page setup; `layouts` to choose, `include_model`, `overwrite`. Made from the drawing as last saved: unsaved changes are refused ([D-41](DECISIONS.md)). `folder` (with `recursive`) or `drawings` publishes several drawings into one PDF, drawing by drawing; each must be saved and have its xrefs, or nothing is published ([D-91](DECISIONS.md)) |
| `autocad_get_variable` | Read a system variable |
| `autocad_set_variable` | Write a system variable |

## Drawing (Change)

`autocad_draw_line`, `autocad_draw_polyline`, `autocad_draw_rectangle`, `autocad_draw_circle`,
`autocad_draw_arc`, `autocad_draw_ellipse`, `autocad_draw_point`, `autocad_add_text`,
`autocad_add_mtext`, `autocad_add_dimension`, `autocad_insert_block`, `autocad_add_hatch`

All but `autocad_add_hatch` take `coords="ucs"`: points, vertex lists and angles are read in the
current UCS; a rectangle comes out square to it, a horizontal dimension measures along its X
([D-96](DECISIONS.md)).

`autocad_add_hatch` takes a pattern from acad.pat, or a custom one written by
`autocad_create_hatch_pattern` (it tries acad.pat first, then a NAME.pat on the support path).

`autocad_add_text`, `autocad_add_mtext` and `autocad_add_dimension` take `annotative=true`: the
object is made annotative at the drawing's current annotation scale, by the plug-in
([D-81](DECISIONS.md)). Sizes stay in drawing units at that scale (125 for 2.5 mm at 1:50); the
reply gives the paper height. An annotative dimension is not given the drawing's DIMSCALE.

## Splines, multilines, wipeouts, construction lines, regions, donuts, divide and xrefs (Change)

| Tool | Purpose |
|---|---|
| `autocad_draw_spline` | A smooth curve through fit points (flexible duct, a curved edge). The ends follow the first and last segments unless tangents are given; `closed` closes it smoothly; `coords="ucs"`. `method="control_points"` with `degree` (1-10, 3 default) draws SPLINE's CV method instead, by the plug-in ([D-97](DECISIONS.md)) |
| `autocad_edit_spline` | Move, insert or remove a drawn spline's fit points (SPLINEDIT Fit data), in order, numbered from 0 as `autocad_get_entity` lists them; the handle is kept. By the plug-in, which reads the points back and changes nothing unless they match ([D-97](DECISIONS.md)) |
| `autocad_draw_multiline` | MLINE: a wall or double-line duct in one object. `scale` is the thickness with the STANDARD style; `justification` zero / top / bottom; `style` from the drawing (put back afterwards). `closed` is MLINE's own Close, the last corner mitred, by the plug-in; without it the first point is repeated and `mitred` is false ([D-97](DECISIONS.md)) |
| `autocad_add_wipeout` | Mask an area, from corners or a closed straight-sided polyline (`erase_boundary`); `frames` sets WIPEOUTFRAME. No Automation call exists: it types WIPEOUT with world, unsnapped points (`_non *x,y`), in the current space ([D-38](DECISIONS.md)) |
| `autocad_add_construction_line` | XLINE (endless both ways) or RAY (endless one way, `kind="ray"`) through `base`, towards `through` or at `angle` degrees. COM `AddXline` / `AddRay` ([D-108](DECISIONS.md)) |
| `autocad_add_region` | REGION: closed outlines (closed polylines, circles, ellipses, splines, or lines and arcs meeting end to end) to regions, in the outlines' own space; gives each one's area, perimeter and centre. Outlines stay unless `erase_outlines`. COM `AddRegion` ([D-108](DECISIONS.md)) |
| `autocad_add_donut` | DONUT at one or many `centers`: a closed polyline of two half circles, width = (outside - inside) / 2, run midway; `inside_diameter=0` is a filled dot. Says when FILLMODE is 0 ([D-108](DECISIONS.md)) |
| `autocad_divide_curve` | DIVIDE (`segments`, equal parts; an open run's ends stay free) or MEASURE (`interval` from the start, or `from_end`; the rest at the end), with points or a `block_name` turned to the run (`align`). Lines, polylines, arcs, circles, flat in world plan; in the run's own space. Heron's own maths ([D-108](DECISIONS.md)) |
| `autocad_attach_xref` | XATTACH a .dwg: name from the file, insertion, scale, rotation, `overlay`. A name already in the drawing is refused. `autocad_list_blocks` lists xrefs with their paths |
| `autocad_manage_xref` | `reload`, `unload`, `detach`, `bind` (names kept apart, NAME$0$...) or `insert` (names merged). Detach and both binds need `confirm=true` |
| `autocad_xref_tree` | **Read.** Every xref with the xrefs inside it (8 levels), its saved path, the file found on this PC and `loaded` / `unloaded` / `not found`; `broken` lists the ones that lead nowhere ([11](11-adn-repos-study.md)) |
| `autocad_attach_underlay` | Attach a raster image (PNG, JPG, TIF...) over COM, or a PDF / DWF / DGN underlay by the plug-in: insertion, scale, rotation, `page` (PDF page, DWF sheet, DGN model), layer; `width` sizes an image in drawing units ([D-84](DECISIONS.md)) |
| `autocad_clip_reference` | Clip an xref, a block, an image or an underlay to two corners or a closed polyline (arcs in short steps); `remove=true` takes the clip off. Image over COM, the rest by the plug-in |
| `autocad_import_pdf` | PDF Import: one page of a PDF as lines, text and hatches (`what`), at a point, scale and rotation, everything on `layer` if given; reports what came in (`by_type`, `box`, `layers_added`). No API exists: it types `-PDFIMPORT` with every answer in one form, after checking the release (2021-2027), and cancels a command left asking. Pictures in the PDF are left out ([D-106](DECISIONS.md); live rows AO, NOT RUN) |

## Cleaning up an import, and packing a drawing (Change; eTransmit is Publish)

| Tool | Level | Purpose |
|---|---|---|
| `autocad_overkill` | Change | OVERKILL: doubled and overlapping lines, arcs and circles, zero-length lines, copies of polylines, loose lines lying on a polyline. The first call lists by handle what would go and why, with a `plan_id`; `confirm=true` with that `plan_id` erases and stretches exactly that in one undo step (nothing, if the drawing changed), then Heron's erase question asks the modeller. Polylines are never broken: overlaps on them are listed under `left` ([D-84](DECISIONS.md)) |
| `autocad_trace_boundary` | Change | BOUNDARY / BPOLY round a point, by the plug-in's `Editor.TraceBoundary`, never typed: zooms to a `window` first, counts what is in it (refused over `most_objects`), waits at most `timeout` s. A polyline per loop, or one region with the islands cut out; returns the handle and area |
| `autocad_etransmit` | Publish | eTransmit: the saved drawing with its xrefs (nested too), images, underlays, font files and plot styles in one .zip or folder beside it, with `transmittal report.txt`; what was not found is listed under `missing`. An unsaved drawing is refused; `list_only=true` writes nothing ([D-85](DECISIONS.md)) |

## Custom hatch patterns and linetypes (Publish)

| Tool | Purpose |
|---|---|
| `autocad_create_hatch_pattern` | Writes NAME.pat: `lines` or `cross` at an angle and spacing, optionally dashed, or `custom` families. The folder (Heron's own support folder by default) is put on AutoCAD's support path once, so HATCH and `autocad_add_hatch` find it ([D-39](DECISIONS.md)) |
| `autocad_create_linetype` | Writes NAME.lin and loads it: a plain dash pattern, or a service line with its name in it (---- CHWS ---- CHWS ----), sized as it plots when LTSCALE is the drawing scale factor |

Both check the file text first (AutoCAD's limits: six dashes and 80 characters a hatch line; 12
dashes, 280 characters and a 47-character description for a linetype) and write nothing on `dry_run`.

## Labels (Change)

`autocad_add_label` puts a label on something: MTEXT plus a leader with an arrow. Use it for every label.

| Option | Meaning |
|---|---|
| `kind="leader"` (default) | Ajmal's TLD style (TextLeader_V4.lsp): MTEXT and a LEADER on the text's layer, ending under the text between line 1 and line 2, full width + `extension` x text height each side |
| `shape="L"` / `"angled"` | Square leg from the arrow, or straight to the near end of the text. Use `angled` for a column of labels |
| `kind="mleader"` | One MULTILEADER with the text as its content |

The arrow is sized from DIMSCALE (a leader made over COM ignores the override). Dimensions made by
`autocad_add_dimension` get DIMSCALE the same way.

`autocad_batch_labels` places a whole column of labels in **one call and one undo step**, with the
same TLD geometry. Shared settings (`height`, `shape` - `angled` by default here, `text_align`, `kind`,
`layer`, ...) can be overridden per label. Every label is checked first: a bad one stops the batch
with its index and nothing is drawn. `arrow_scale` sets the arrow size for this view (25 for 1:25)
without touching DIMSCALE, so a sheet with 1:10 and 1:25 views keeps the right arrows. The result
lists any pair of leaders that cross in `crossing` (drafting rule 4).

## Blocks from parts (Change)

`autocad_make_block` turns drawn objects into a named block and puts one insert in their place
(`keep_originals=true` only defines it). Use it for every separate part (fitting, elbow, clamp, plate,
anchor); pipes and runs can stay as lines. More copies: `autocad_insert_block`; mirrored copies:
`autocad_mirror_entities` on the insert. Labels: `text_align="right"` hangs a label from its
top-right corner, for a tidy column left of a detail.

`attributes` on `autocad_make_block` adds attribute definitions (ATTDEF): tag, prompt, default,
position, height, and the flags `invisible`, `constant` (needs a default) and `preset`
([D-82](DECISIONS.md)). Not proven in AutoCAD yet: [NEEDS-CHECKING group AC](NEEDS-CHECKING.md).

| Tool | Level | Purpose |
|---|---|---|
| `autocad_sync_attributes` | Change | ATTSYNC, done by the plug-in: every insert of a block (dynamic copies too) gets the definition's attributes again; values already typed are kept by tag, new tags come with their default, lost ones go. `add_attributes` adds definitions to the block first; `nested=true` also syncs inserts inside other blocks' definitions; `dry_run` says what each insert keeps, gains and loses |
| `autocad_copy_from_drawing` | Change | Copy with Base Point and Paste between **open** drawings: handles from another open drawing into the active one, from `base_point` to `to_point`. The layers, styles and blocks it lacks come along (`brought_in`); names it has stay its own (`already_here`). Neither drawing is switched ([D-83](DECISIONS.md)) |

## Bulk drawing (Change)

`autocad_batch_draw` sends one AutoLISP script that creates many entities inside AutoCAD. Use it for
anything above about ten entities. Every operation is checked in Python first, so a bad batch fails
naming the operation index without touching the drawing. Supports line, polyline, rectangle, circle,
arc, text, point, **mtext** (an attachment point; long text in pieces), **hatch** (a SOLID fill of
its own outline, arcs and holes included: arrowheads, north points, filled symbols) and linear
**dimension** (aligned, horizontal, vertical, rotated; the drawing's DIMSCALE) ([D-96](DECISIONS.md)).
Patterns, and radial, diametric and angular dimensions, stay with `autocad_add_hatch` and
`autocad_add_dimension`. Speeds are in [02](02-architecture.md#why-python-and-autolisp).

## Querying (Read)

| Tool | Purpose |
|---|---|
| `autocad_list_entities` | Filter by type, layer, block or colour; paginated; summary mode (counted by the plug-in in one go, COM for an older one, [D-114](DECISIONS.md)) |
| `autocad_get_entity` | All properties and bounding box of one entity |
| `autocad_get_selection` | What you have selected in AutoCAD right now |
| `autocad_find_text` | Search text, mtext and block attributes (read by the plug-in in one go, COM for an older one, [D-134](DECISIONS.md)) |
| `autocad_get_extents` | Bounding box of the drawing or one layer (a layer measured by the plug-in in one go, COM for an older one, [D-114](DECISIONS.md)) |
| `autocad_measure` | Point-to-point distance, or total length / area of entities or a layer (a layer read by the plug-in in one go, COM for an older one, [D-134](DECISIONS.md)) |
| `autocad_drawing_report` | A received drawing in one read: units, layers (off / frozen / locked), blocks, xrefs, text and dimension styles, linetypes, sheets with their paper, model-space counts by type (up to 50,000; counted by the plug-in in one go, COM for an older one, #193) |

## Modifying (Change)

`autocad_move_entities`, `autocad_copy_entities`, `autocad_rotate_entities`,
`autocad_scale_entities`, `autocad_mirror_entities`, `autocad_offset_entities`,
`autocad_array_entities`, `autocad_modify_entity`, `autocad_delete_entities`

`autocad_array_entities` makes loose copies. For ARRAY's one editable array, or copies along a
path, use `autocad_associative_array` (below).

`autocad_delete_entities` needs `confirm=true`. Without it the tool returns a preview and changes
nothing.

Move, copy, rotate, scale, mirror and array take `coords="ucs"`: a displacement is turned with the
UCS, a base point is moved through it, and a rectangular array's rows follow its axes
([D-96](DECISIONS.md)).

`autocad_modify_entity` also sets **lineweight** (0.25, 0.35 ... mm as AutoCAD lists them, or
ByLayer / ByBlock / Default) and **transparency** (0-90, ByLayer, ByBlock) per object ([D-79](DECISIONS.md)).

## Everyday 2D edits (Change; listing groups is Read)

Worked out in Python and written back by setting each object's own points over COM: nothing is
typed on the command line, so nothing is left waiting for a pick ([D-78](DECISIONS.md),
[D-79](DECISIONS.md)). In plan, on flat lines, arcs, circles and polylines. Each call is one undo
step; an object on a locked layer is refused before anything is written. Not proven in AutoCAD yet
([NEEDS-CHECKING group AA](NEEDS-CHECKING.md); limits in [05 §29](05-known-limits.md#29-the-everyday-2d-edits-have-their-own-limits)).

| Tool | Purpose |
|---|---|
| `autocad_trim_extend` | TRIM back to cutting edges (a point on the part to cut away) or EXTEND to boundaries (both ends when no point is given). Edges count as drawn. A cut circle becomes an arc |
| `autocad_fillet_chamfer` | FILLET (radius; 0 = sharp corner) or CHAMFER (two distances, or a distance and an angle) of two lines, a line and an arc, two arcs, the ends of open polylines, or of one polyline's corners (it stays one polyline). A chamfer to an arc is measured along the arc (D-144) |
| `autocad_lengthen` | LENGTHEN a line, arc or open polyline at one end: by a distance (Delta; negative shortens), to a total length, or by a percent. Arc ends run on round their own circle |
| `autocad_break_curve` | BREAK one object at a point, or take out the part between two points |
| `autocad_join_curves` | JOIN lines, arcs and open polylines end to end into one line, arc or polyline (`gap` to close small gaps); the others are erased |
| `autocad_edit_vertex` | Move a polyline vertex or a line's end; add or remove a polyline vertex (bulges kept) |
| `autocad_stretch` | STRETCH: the points inside a window move; circles, text, blocks and points move whole when their base point is inside; anything else only when wholly inside |
| `autocad_explode` | EXPLODE blocks and polylines; returns the new handles. A block with attributes needs `allow_attribute_loss=true` |
| `autocad_draw_order` | DRAWORDER: front, back, above or under one object (a hatch or wipeout to the back) |
| `autocad_match_properties` | MATCHPROP: layer, colour, linetype, linetype scale, lineweight, transparency, and text or dimension style on request, from one object to others, with before / after |
| `autocad_list_groups` | The drawing's groups and their members (Read) |
| `autocad_group` | Make a named group, add or remove objects, ungroup (the objects stay) |

## Layers and blocks (lists Read, the rest Change)

`autocad_list_layers` (and the saved layer states), `autocad_create_layer`, `autocad_set_layer_state`,
`autocad_set_current_layer`, `autocad_delete_layer` (needs `confirm=true`), `autocad_list_blocks`
(its counts and definitions read by the plug-in in one go, COM for an older one, [D-127](DECISIONS.md)),
`autocad_list_styles`

| Tool | Level | Purpose |
|---|---|---|
| `autocad_layer_states` | Change | Save the layers as a named layer state (what it remembers is up to you), restore one (every layer it changed comes back in `before_after`), or delete one. Done by the plug-in ([D-81](DECISIONS.md)) |
| `autocad_isolate_layers` | Change | LAYISO / LAYUNISO: keep the layers of picked objects (or named layers), every other layer `off`, `freeze` or `lock`. The layers before the first isolate are saved as the HERON-ISOLATE layer state; `unisolate` puts them back, current layer too |
| `autocad_merge_layers` | Change | LAYMERGE: every object on the old layers moves to the new one (model, layouts, block definitions, attributes); an old layer is removed only when nothing is left on it. Needs `confirm=true`; without it, says what would move. Through the plug-in, read in one go and made in one transaction: every object moves or nothing changes; COM for an older one ([D-147](DECISIONS.md)) |

## Escape hatches (Admin; regen is View)

| Tool | Purpose |
|---|---|
| `autocad_send_command` | Any AutoCAD command, such as an add-in's (TRIM and FILLET have their own tools now, above). `expect_box` + `press`: the one button to press on one box the command will ask, every other box still cancelled ([D-74](DECISIONS.md)). An UNDO, U, REDO, MREDO or OOPS is never sent twice by a busy retry ([D-76](DECISIONS.md)) |
| `autocad_run_lisp` | Evaluate AutoLISP **and get the result back**. Long code, or several top-level forms, is cut between the forms into pieces under 700 characters, run in order as one undo step; one form over 1,750 characters is refused ([D-76](DECISIONS.md), [05 §3](05-known-limits.md#3-long-autolisp-fails-silently)). A LISP error is answered at once, with AutoCAD's own message in `lisp_error` and the piece that stopped ([D-129](DECISIONS.md)). `expect_box` + `press` as for send_command |
| `autocad_purge` | Remove unused blocks, layers, linetypes, styles |
| `autocad_regen` | Regenerate the display |
| `autocad_audit` | Check and repair the drawing database |

`autocad_send_command` refuses commands known to open a modal dialog and names the command-line
alternative, because a dialog blocks COM until a person closes it.

## Take-off, text and placement (from the [Lee Mac study](08-lee-mac-study.md); our own code)

| Tool | Level | Purpose |
|---|---|---|
| `autocad_count_blocks` | Read | Count blocks by real name (dynamic too); group by name, layer, visibility or properties; `include_nested` (read by the plug-in in one go, COM for an older one, [D-127](DECISIONS.md)) |
| `autocad_total_length` | Read | Total length per layer or type, area of closed shapes; splines and ellipses measured (read by the plug-in in one go, COM for an older one, [D-134](DECISIONS.md)) |
| `autocad_get_dynamic_properties` | Read | A dynamic block's properties: value, allowed choices, read-only |
| `autocad_count_text` | Read | Count text / tag values (`source`, `tag`, `pattern`), optional `sum_numeric` (read by the plug-in in one go, COM for an older one, [D-134](DECISIONS.md)) |
| `autocad_polyline_info` | Read | Vertices, segments (arcs: centre, radius, sweep), total, area, centroid |
| `autocad_select_connected` | Read | A whole run joined end to end: handles, total length, open ends |
| `autocad_list_layouts` | Read | Layouts in tab order with plotter, paper, object count |
| `autocad_set_dynamic_properties` | Change | Set visibility, size, distance, flip; typed and checked; failures listed |
| `autocad_set_attributes` | Change | Attributes from `values`, `rows` or `csv_path`, matched by `key` (a tag or `layout`); `dry_run` (the blocks read by the plug-in in one go and the changes written in one transaction, all or none, COM for an older one, [D-138](DECISIONS.md), [D-148](DECISIONS.md)) |
| `autocad_export_attribute_sheet` | Publish | Every block's attributes in a new `.xlsx` next to the drawing (one row per block, one column per tag, handle first), with an "As exported" copy; never over an earlier one ([D-69](DECISIONS.md); the blocks read by the plug-in in one go, COM for an older one, [D-138](DECISIONS.md)) |
| `autocad_apply_attribute_sheet` | Change | Reads the edited `.xlsx` (or a `.csv` with a Handle column) and writes only the cells that changed, in one undo step; blanks change nothing; a value the drawing changed since the export is kept; a cell changed in both is a conflict, listed; `dry_run` ([D-69](DECISIONS.md); the blocks read by the plug-in in one go and the changed cells written in one transaction, all or none (a cell AutoCAD will not take then refuses the sheet), COM for an older one, [D-138](DECISIONS.md), [D-148](DECISIONS.md)) |
| `autocad_number_tags` | Change | Prefix + padded number + suffix on blocks (`tag`), texts or new text; sort rows / columns / path |
| `autocad_text_clean` | Change | Strip MText formatting codes; `dry_run` |
| `autocad_find_replace_text` | Change | Find / replace (plain or regex) in text, mtext, attributes, mleaders, dim overrides, tables; `dry_run` |
| `autocad_align_text` | Change | Line up (left, right, centre, top, bottom, middle) or space evenly; the first object stays put |
| `autocad_add_field_label` | Change | Live Length / Area field (sum of several) in new text or an attribute; `factor` for m / m2 |
| `autocad_label_segment_lengths` | Change | Length at each segment's middle; `split_at_layer` splits at crossings |
| `autocad_place_along` | Change | Blocks along a run by `spacing` (equal ends) or `count`; `align` turns them to the run |
| `autocad_place_from_csv` | Change | Blocks at x, y (rotation, block) from a CSV; other columns fill attributes |
| `autocad_break_at_blocks` | Change | Cut lines and polylines through block extents + `gap`. Arcs are cut too and keep their centre and radius; a closed polyline cut once becomes one open run ([D-97](DECISIONS.md)) |
| `autocad_import_from_drawing` | Change | Blocks, layers, linetypes, text / dim styles from a closed DWG; existing names skipped |
| `autocad_manage_layouts` | Change | Order, renumber, rename layouts; copy paper-space objects to other layouts |

## Coordinates and the UCS (Read; setting it is Change)

A rotated or moved UCS is why a line lands somewhere nobody meant. Detail:
[09 §1](09-sheets-and-coordinates.md#1-the-ucs-why-a-line-lands-in-the-wrong-place).

| Tool | Level | Purpose |
|---|---|---|
| `autocad_get_ucs` | Read | Is a UCS set? Origin, axes, rotation in degrees, moved / rotated / tilted / flipped, the saved ones, and what to do about it |
| `autocad_convert_points` | Read | AutoLISP's `trans`: points and angles between the UCS and the world. Changes nothing |
| `autocad_set_ucs` | Change | `world`, `named`, `origin` + angle, `3point`, `entity`, `view`; `save_as` keeps it by name |

## Sheets, title blocks and viewports (Change)

A sheet from nothing in four calls, or one `autocad_sequence`. Detail:
[09 §3](09-sheets-and-coordinates.md#3-laying-out-a-sheet).

| Tool | Purpose |
|---|---|
| `autocad_create_layout` | New sheet: paper size, orientation, plotter, plot style table, optionally copied from another layout (with everything on it, by the plug-in). Returns the frame, the drawing space and where the title block goes. Made by the plug-in in .NET, over COM with an older one; `made_by` says which ([D-90](DECISIONS.md)) |
| `autocad_page_setup` | Page Setup on one sheet or `all_layouts`: plotter, paper, `plot_area`, scale, `monochrome.ctb`, lineweights. Only what you pass is written |
| `autocad_place_title_block` | The title block in the sheet's corner (ISO 5457 bottom-right by default) with its attributes filled; `all_layouts` and `per_layout_attributes` do a whole set |
| `autocad_add_viewport` | A viewport at a real scale (`"1:50"`, or omitted to fit) looking at a point, a window, a saved view or a set of objects; `twist` / `align_to_ucs` for a rotated plan; locked by default. `clip_outline` / `clip_handle` clip it to a shape (plug-in only); `annotation_scale` (default `match`) sets its annotation scale. In the layout's own block by the plug-in ([D-90](DECISIONS.md)) |
| `autocad_sheet_set` | **A drawing list into sheets in one call:** per row (number, title, scale, view) a layout, a viewport at that scale on that view, and the title block filled with number, title and scale. The whole list is checked first; one undo step; `dry_run` shows the plan; `template_layout` copies a sheet for each ([D-90](DECISIONS.md)) |

## Saved locations (Read; saving is Change)

One named area, used for a plot, a viewport and a measurement. Detail:
[09 §2](09-sheets-and-coordinates.md#2-one-location-used-everywhere).

| Tool | Level | Purpose |
|---|---|---|
| `autocad_list_views` | Read | Every saved view with its centre, size and both corners |
| `autocad_save_view` | Change | Name an area, from two corners or from the objects' own extents + `pad` |

## Drawing settings and styles (Change)

| Tool | Purpose |
|---|---|
| `autocad_drawing_setup` | Units, precision, the drawing `scale` (which sets DIMSCALE, the annotation scale and LTSCALE), `paper_text_height`, object snaps, point style, linetype scaling, limits. `dry_run` shows the plan; writes only from a fixed list ([D-28](DECISIONS.md)) |
| `autocad_create_styles` | Text styles (font, height, width factor, oblique) and dimension styles (scale, text height, arrows, precision, or raw `DIM...` variables; the drawing's own DIM variables are put back). Multileader styles (text style, height, arrow, dogleg, landing gap, attachment; Ajmal's TLD label by default) and table styles (text heights, margins, left / centre / right in the vertical middle) made by the plug-in ([D-104](DECISIONS.md)). Not plot style tables: AutoCAD's .NET API cannot write one ([D-105](DECISIONS.md)) |

## An import into a shop drawing (Change)

Both default to `dry_run=true`: read the counts, then run it. Detail:
[09 §5](09-sheets-and-coordinates.md#5-an-ifc-or-revit-export-into-a-shop-drawing).

| Tool | Purpose |
|---|---|
| `autocad_remap_layers` | Rules match `name_like` (layer **or** block name), `source_layer`, `block_name`, `entity_type`, `source_color`, `text_contains`; the target layer is created with its colour, linetype, lineweight, description and plot setting. `preset="ifc"` is a starting point; `rules_path` takes an office standard written as rules; `layer_standard` (`office`, `example` or a `.csv` / `.json`) keeps objects on its layers (and on the layers its pattern rows cover), gives those layers its colour, linetype, lineweight, plot and description, and moves the old names each row `replaces`. A rule may say `keep: true` instead of a target `layer`: what it matches stays where it is. `office` with none loaded is refused ([D-120](DECISIONS.md)) |
| `autocad_tidy_entities` | Colour / linetype / lineweight back to ByLayer, `flatten_z`, `zero_thickness`, `off_layer_0`, `delete_empty` |

## Several tools in one call (Change)

`autocad_sequence` runs a list of steps in order. Every step's arguments are checked against that
tool's own schema **before the first one runs**, so a sequence with a mistake in step four changes
nothing. Steps at the Publish or Admin level, and a sequence inside a sequence, are refused: a
sequence holds the **Changes** padlock only ([D-29](DECISIONS.md)). `stop_on_error` (default true)
and `dry_run`. `quiet=true` gives each step's answer as counts and handles only, without every
point and measurement; errors stay whole ([D-77](DECISIONS.md)). `autocad_batch_draw`,
`autocad_dimension_run` and `autocad_add_centre_marks` take `quiet` too.

## Shapes from a few numbers (Change)

`autocad_make_shape` draws a named shape from its dimensions — 24 flat ones, from
a slot to a reducer's flat pattern, and two 3D ones made as solids along a route.
Detail: [10 §1](10-geometry-annotation-3d.md#1-simple-words-complex-geometry).

| Group | Shapes |
|---|---|
| Plain | polygon, hexagon (across flats), star, slot, rounded_rectangle, spiral, zigzag |
| Fabrication | flange, bolt_circle, steel_section (i/h/c/l/t/shs/rhs/chs), gear, **cone_development** (the flat pattern for a reducer) |
| MEP | elbow (with centreline), duct_transition, grating |
| Building | stair (section or plan), ladder, truss |
| Furniture | detail_bubble, section_mark, north_arrow, scale_bar, level_mark, revision_tag |
| **3D, as solids** | **duct_run** (rectangular or round, a bend at every corner of the route), **pipe_spool** (pipe lengths, elbows, flanges, with each pipe's cut length) ([D-94](DECISIONS.md)) |

Arcs come out as polyline bulges, so a slot or an elbow stays **one object**.
`dry_run=true` returns the geometry instead of drawing it. A 3D shape is one solid per straight,
bend and flange (`join=true` makes one), each checked against the box it should fill.

## Dimensioning and annotation (Change)

| Tool | Purpose |
|---|---|
| `autocad_dimension_run` | A whole run in one call: `chain`, `baseline` (stepped clear of each other), `overall`, `ordinate`. Horizontal, vertical or aligned; the points are put in order first; `include_overall` adds the overall above. Reports both its own arithmetic and AutoCAD's measurement. `dim_style` draws the run in a named style at that style's own scale ([D-80](DECISIONS.md)); `annotative` makes it annotative. `quiet=true`: counts and handles only |
| `autocad_space_dimensions` | DIMSPACE: a stack of parallel dimensions moved to an even spacing off a base dimension (0 lines them up). Only the dimension lines move; the plug-in moves them, Heron works out where. `dry_run` reports the moves |
| `autocad_break_dimensions` | DIMBREAK, automatic: a gap in each dimension wherever another object crosses it; `remove` takes the breaks off. Typed, since no API has a call for it |
| `autocad_annotation_scales` | OBJECTSCALE: make objects annotative (or plain), add or remove annotation scales on them; a 1:N scale the drawing lacks can be added to its list. Done by the plug-in ([D-81](DECISIONS.md)) |
| `autocad_list_annotation_scales` | **Read.** The drawing's scale list, the current one (CANNOSCALE), and which scales each object carries, with its paper height |
| `autocad_add_centre_marks` | The cross on every circle and arc, by handle or by layer; `extend` makes full centre lines |
| `autocad_add_multileader` | One note with **as many arrows as it needs**; text or block content; `annotative` |
| `autocad_add_table` | A schedule as a real AutoCAD table, with title and headings; `text_height` and `text_style` on every row; text in the vertical middle of each cell |
| `autocad_table_from_excel` | An Excel range as a table: a real **Data Link** made by the plug-in, so it can be updated; filled from the sheet with `"linked": false` and the reason when a link cannot be made. Cells Excel only shows as a date or percent are listed, not written ([D-83](DECISIONS.md)) |
| `autocad_update_table_links` | Update linked tables from their sheets (DATALINKUPDATE), keeping the table's formatting |
| `autocad_set_table_cells` | Change cells of a table by address (`B3`) or row / column, counted from 1 at the top-left cell, title and header rows included; old -> new; `grow` adds rows or columns; linked and locked cells are listed and left alone |
| `autocad_add_revision_cloud` | A cloud round a boundary, a rectangle, or an object's own extents. One polyline with bulges, like REVCLOUD |

## 3D (Change; reading is Read, the view is View)

| Tool | Level | Purpose |
|---|---|---|
| `autocad_add_solid` | Change | box, wedge, cylinder, cone, sphere, torus, elliptical_cylinder, elliptical_cone — placed by the centre of its **base**, not its bounding box. Oval shapes take the **overall** sizes, not the half axes |
| `autocad_extrude_profile` | Change | A closed 2D profile into a solid: extrude along Z (with taper), revolve about an axis, or **sweep along a path** — a duct, pipe or tray following a route. The intermediate region is cleaned up |
| `autocad_solid_boolean` | Change | union / subtract / intersect. The others are **consumed**, as AutoCAD's own commands do; every handle is checked first |
| `autocad_solid_properties` | Read | Volume, centroid, bounding box, moments — for a weight take-off |
| `autocad_draw_3d_path` | Change | A pipe or cable route as one 3D polyline, or a helix |
| `autocad_slice_solid` | Change | Cut solids with a plane — a real section through a model. The plane is given the way a drafter says it ("horizontally at 1500"); the three points AutoCAD wants are worked out here |
| `autocad_check_interference` | Change | **Clash check.** Every solid in one set against every solid in another, with the overlap volume so the worst comes first. `create_solids` draws the overlaps. Needs Changes because AutoCAD builds the overlap as a real solid to measure it, even to report |
| `autocad_transform_3d` | Change | move with Z, rotate about **any** axis, mirror in a plane, array up in levels. The flat tools only do XY and Z-axis rotation |
| `autocad_set_3d_view` | View | A named direction (top, front, sw_iso …) and a visual style, typed as the VSCURRENT command, then the style the viewport has read back by the plug-in (`visual_style_found`, a warning when it differs). Changes only what is on screen ([D-31](DECISIONS.md), [D-35](DECISIONS.md), [D-86](DECISIONS.md)) |

`SectionSolid` is deliberately **not** here: no documented ActiveX signature for it could be
found, and guessing one would risk the model ([D-33](DECISIONS.md)). A section plane and a 2D
section come from the plug-in instead: `autocad_section_plane`, below ([D-95](DECISIONS.md)).

## 3D edits and super hatch, done by the plug-in (Change; the listing is Read)

COM has no call for these, so the Heron plug-in (1.2.0 or newer) does them through AutoCAD's .NET
API, each in one transaction: all of it or none ([D-40](DECISIONS.md), [06](06-heron-plugin.md)).
Not proven in AutoCAD yet: [NEEDS-CHECKING group H](NEEDS-CHECKING.md), and group AH for the
flat views, the section plane, surfaces, meshes and the new super hatch tiles.

Edges and faces are picked by a **word** - edges `all`, `vertical`, `horizontal`, `top`, `bottom`;
faces `top`, `bottom`, `front` (towards -Y, what the Front view looks at), `back`, `left`, `right`,
going by the solid's box, and flat faces only - or by **numbers** from the listing, which hold only
until the solid changes.

| Tool | Level | Purpose |
|---|---|---|
| `autocad_list_solid_faces_and_edges` | Read | Numbers each face (kind, area, centre, normal, its edges) and edge (kind, ends, length) |
| `autocad_loft` | Change | LOFT: a solid through closed outlines in order - a rectangle-to-round duct transition, a tapered column. Optional guides or a path, `ruled`, `closed`. `surface=true` makes a surface, and the outlines may be open (a canopy, a roof sheet). The outlines are kept |
| `autocad_fillet_solid_edges` | Change | FILLETEDGE: round edges by a radius |
| `autocad_chamfer_solid_edges` | Change | CHAMFEREDGE: bevel the edges of one face (all of them, or those named), by one or two distances |
| `autocad_shell_solid` | Change | SOLIDEDIT Shell: hollow to a wall thickness, leaving faces open (`remove_faces="top"` for a tank); inside unless `outward` |
| `autocad_press_pull_faces` | Change | Push or pull flat faces by a distance, with an optional taper |
| `autocad_thicken_surface` | Change | THICKEN: a solid from a surface; the surface is kept |
| `autocad_add_pyramid` | Change | PYRAMID: 3 to 32 sides, a point or a flat top, or a hopper; stands on the centre of its base, one side to the front. By the plug-in ([D-112](DECISIONS.md)) |
| `autocad_add_polysolid` | Change | POLYSOLID: a wall of a width and height along a flat path (a curve or points), centred, left, right, inside or outside; the path is kept ([D-112](DECISIONS.md)) |
| `autocad_edit_solid_faces` | Change | SOLIDEDIT faces: offset, taper, move or delete, picked by a word or by number; volume before and after ([D-113](DECISIONS.md)) |
| `autocad_imprint_solid` | Change | SOLIDEDIT Imprint: split a solid's faces along lines or shapes that touch them; the objects are kept, the faces counted after |
| `autocad_separate_solid` | Change | SOLIDEDIT Separate: a solid of pieces that do not touch becomes one solid per piece |
| `autocad_super_hatch` | Change | Express Tools' SUPERHATCH: a block, an **image** (with `image_size`), an **xref** (attached from its .dwg if need be) or a **wipeout** as the tile, in a grid (spacing, origin, angle, scale) inside a closed outline drawn flat in plan, clipped as XCLIP clips. One object; at most 10,000 tiles, 2,000 for images ([D-95](DECISIONS.md)) |
| `autocad_flatten_views` | Change | FLATSHOT / SOLPROF: plan, front and side views (any of front, top, right, left, back, bottom) of solids as 2D linework, hidden lines removed, one block per view, set out third or first angle so they line up. `join` lets a part hide what is behind it. `hidden_lines` also draws the hidden lines dashed on their own layer (HIDDEN) inside each view ([D-152](DECISIONS.md)). The model is not touched |
| `autocad_section_plane` | Change | SECTIONPLANE and Generate Section: a section plane through two points (a vertical cut) or three (any plane; a level cut looks down), kept in the model, and its 2D section (cut outlines, hatch, what is seen beyond) as one block at `insert_at`. `look_towards` picks the side. `jogged` takes a section line's corners in plan: each leg a vertical cut laid beside the last, the jogs not drawn ([D-152](DECISIONS.md)) |
| `autocad_add_surface` | Change | PLANESURF (from closed outlines or regions, or two corners) or SURFNETWORK (through u and v curves). The curves are kept |
| `autocad_add_mesh` | Change | MESH primitives (box, wedge, cylinder, cone, sphere, torus, pyramid) placed by the centre of the base, smoothness 0-4; or a mesh made from a solid, surface or region (MESHSMOOTH), which is kept |

The attribute sync, the Excel table link and update, and the multileader and table styles are
plug-in operations too (`sync_attributes`, `excel_table`, `update_table_links`,
`multileader_style`, `table_style`); their tools are listed with the blocks, the tables and the
settings above. So are a multiline's Close, a spline by control points and a spline's
fit-point edits (`close_multiline`, `add_cv_spline`, `edit_spline_fit_points`), listed with the
drafting tools ([D-97](DECISIONS.md)).

## Materials (Change; listing is Read)

| Tool | Level | Purpose |
|---|---|---|
| `autocad_list_materials` | Read | The materials in this drawing, and how many objects use each. Run it first: only a material already in the drawing can be applied |
| `autocad_apply_material` | Change | Apply one to objects or to a whole layer. Refuses an unknown name **and lists what the drawing does have** |

Three limits worth knowing before you plan around them ([D-33](DECISIONS.md)):

- **No library access.** Automation cannot reach Autodesk's material library, so a material has to
  be brought into the drawing through the Materials Browser first.
- **No density.** A material is appearance only. MASSPROP and `autocad_solid_properties` both work
  as if density were 1, so a weight is volume times a density *you* state. Assigning "Steel" does
  not make anything weigh.
- **No render from Heron.** There is no automation call for rendering; `-render` is the only route,
  it waits on prompts that differ between releases and can stall AutoCAD, and a scripted render has
  been reported to drop objects. So `autocad_render` was removed ([D-87](DECISIONS.md),
  [#158](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/158)): Heron sets the render up (next
  section) and the modeller presses Render. For a picture to look at use `autocad_preview`; for one
  on a sheet use `autocad_export`.

## Setting a render up (Change; the light list is Read)

These tools set the view, the sun, the lights and the exposure; **none of them renders**: the
modeller presses Render ([D-86](DECISIONS.md), [D-87](DECISIONS.md)); Heron has no tool that
renders ([#158](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/158)). The plug-in does the lights, the
camera and the sun's date, which COM has no call for. Not proven in AutoCAD yet:
[NEEDS-CHECKING groups K and AE](NEEDS-CHECKING.md).

| Tool | Level | Purpose |
|---|---|---|
| `autocad_add_light` | Change | A photometric point, spot, web (IES) or distant light: lumens or candela, Kelvin, a spot's cones in degrees ([D-42](DECISIONS.md)) |
| `autocad_create_material` | Change | A material from its settings: colour, texture with its real size, bump, gloss, transparency, glow ([D-42](DECISIONS.md), [D-46](DECISIONS.md)) |
| `autocad_add_camera_view` | Change | A named perspective camera: eye, target and lens (24 mm inside a room), put on screen so Render can be pressed. A view record with perspective on, never DVIEW |
| `autocad_set_sun` | Change | The sun's date and clock time (on the model viewport's sun) and the place (LATITUDE, LONGITUDE, TIMEZONE from a UTC offset), read back with the sun's azimuth and altitude |
| `autocad_list_lights` | Read | Every light, in model space and in light blocks, with on / off, intensity and unit, Kelvin; plus the sun, DEFAULTLIGHTING, LIGHTINGUNITS and the exposure, and why a render may be dark |
| `autocad_switch_lights` | Change | Lights on or off by name or handle, or all; the sun (SUNSTATUS) and default lighting (DEFAULTLIGHTING) on or off. One unknown name switches nothing |
| `autocad_set_render_exposure` | Change | Exposure (EV, -6 to 21, lower is brighter) and White balance (K) as EXPVALUE / EXPWHITEBALANCE; an AutoCAD without them is told to use RENDEREXPOSURE |

## Associative arrays, tiled viewports, hyperlinks, geographic location

Part 2 of the smaller ribbon gaps ([#119](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/119);
[D-110](DECISIONS.md), [D-111](DECISIONS.md)). The array and the location are done by the plug-in,
which COM has no call for; the rest is COM. Not proven in AutoCAD yet:
[NEEDS-CHECKING group AQ](NEEDS-CHECKING.md).

| Tool | Level | Purpose |
|---|---|---|
| `autocad_associative_array` | Change | ARRAY's one editable array: along a path (`count` end to end, or `spacing`; items follow the path), a grid, or a ring. Refused, with nothing changed, if AutoCAD puts the items anywhere but where asked |
| `autocad_tiled_viewports` | View | The Model tab in 1, 2, 3 or 4 tiled viewports (VPORTS), or the tiles read back with what they look like; layouts are refused (`autocad_add_viewport` is for sheets) |
| `autocad_hyperlinks` | Change | A link (a file, a data sheet, a web page, a named view) set on objects, replacing any they had, or removed; before and after per object |
| `autocad_list_hyperlinks` | Read | The links on given objects, or every linked object in the drawing (found by the link's extended data, PE_URL) |
| `autocad_geo_location` | Change | GEOGRAPHICLOCATION: a drawing point at a latitude and longitude, north in degrees clockwise from up; proved with AutoCAD's own transform; the sun's place (LATITUDE, LONGITUDE) follows the site. `action='remove'` takes it off |
| `autocad_get_geo_location` | Read | The location, and whether the sun's place agrees with it |

## Seeing and checking (Read)

| Tool | Purpose |
|---|---|
| `autocad_preview` | Plot the extents, the current view or a window to PNG and return the **picture** to the AI. Use after drawing, before saying it is done. Says the area plotted and the smallest text that reads; `detail=2` or `3` adds close-ups of the same area, for a full sheet whose small text one picture cannot show (D-102). Page setup put back |
| `autocad_check_standards` | Check layers and objects against rules: `layer_name_pattern`, `layers {name: {color, linetype}}`, `forbid_entities_on_layer_0`, `require_bylayer_color`, `require_bylayer_linetype`, `max_findings`. Inline or a JSON file. Or against a `reference` drawing (`.dws`, `.dwt`, `.dwg`, `.dxf`): layers, text styles, dimension styles (name only) and linetypes (name only) missing, different, or not in the standard (`flag_extra`); the answer says what read the reference ([D-92](DECISIONS.md)). Or a `layer_standard` (`office`, `example`, or a `.csv` / `.json` file): each listed layer, or one a pattern row covers, by colour, linetype, lineweight, plot and description; an unlisted layer against its name pattern; its required layers; `office` with none loaded is checked against the example and not decided ([D-120](DECISIONS.md)). `passed` means the rules given were met against the named `source`, never that the drawing complies; `null` when only part of the objects was read ([D-64](DECISIONS.md)). The objects' facts are read by the plug-in in one go, COM for an older one ([D-145](DECISIONS.md)) |
| `autocad_extract_attributes` | Every block reference with attributes as rows (block, handle, layer, insertion, tags), JSON or CSV - for schedules (read by the plug-in in one go, COM for an older one, [D-138](DECISIONS.md)) |

## Resources and prompts

| Resource | Same as |
|---|---|
| `autocad://drawing/status` | `autocad_status` |
| `autocad://drawing/layers` | `autocad_list_layers` |
| `autocad://drawing/blocks` | `autocad_list_blocks` |
| `autocad://drawing/styles` | `autocad_list_styles` |
| `autocad://tools` | **the toolbox index** — not a drawing read, so it needs no AutoCAD |

The four drawing resources call the gated tools, so they are refused the same way while AutoCAD is
not connected.

`autocad://tools` is the one that is not about the drawing: every tool grouped by the padlock it
needs, with its one-line summary and its **`Use when`** lines. It is built from the live registry,
so it cannot drift from the code, and it answers before Heron is pressed. Each tool's own
`Use when:` / `Don't use when:` bullets name the better tool when there is one — which is how over a
hundred tools stay findable. A tool without them fails `tests/test_tool_index.py`.

A prompt is a whole job written out in the right order, so the AI does not have to work out which
of the tools to reach for or what to check afterwards. Pick one in your client and fill in its
arguments.

| Prompt | Arguments | What it walks through |
|---|---|---|
| `check_standards` | `rules_path`, `layer_standard` | Checks the drawing against a layer standard and reports. Changes nothing |
| `draw_from_spec` | `spec` | Draws from a written spec on named layers, then previews it |
| `draw_detail` | `subject`, `scale` | The full drafting checklist: sheet plan, layers, parts as blocks, hatching, labels, dimensions, titles, notes, then look at it |
| `make_sheet` | `sheet_name`, `paper_size`, `scale` | Layout, page setup, title block, viewport at a scale, and a saved view so the same location comes back |
| `import_to_shop_drawing` | `discipline`, `scale` | An IFC or CAD import into a shop drawing: layer audit, remap and tidy (dry run first), styles, details, dimensions, annotation, sheet, PDF |
| `model_part` | `part`, `material` | Profile, extrude or revolve, cut the holes, take the volume and weight off the solid, and the flat pattern if it is rolled |
| `shape_from_words` | `description`, `scale` | Picks the shape from the catalogue, dry-runs it, draws it, then measures it back |

Every tool a prompt names is checked against the registry by `tests/test_drafting_rules.py`, so a
prompt cannot send the AI after a tool that was renamed or never built.

## Start options

| Option | Effect |
|---|---|
| `--read-only` | Only Read and View tools are offered; nothing can change a drawing |
| `--no-bridge` | Developers only: skip the plug-in (no padlocks, banner, Keep or Discard) |
| `--transport http --host --port` | Serve over HTTP (no authentication: trusted networks only) |

For a program that lists tools rather than calls them (Heron AI's capability registry), `tools/export_capabilities.py` writes every tool, its level, inputs, what it needs of the plug-in and its live-check state into `dist/capabilities.json` ([14](14-heron-ai-adapter.md)).
