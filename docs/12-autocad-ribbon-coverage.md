# 12 - AutoCAD ribbon coverage: what Heron covers, what is missing

Every panel of AutoCAD's default ribbon, checked against Heron's tools. For each panel: the main
commands, the Heron tool that does the same job, what is missing, whether a program can do it, and
a priority for an **MEP draftsman** (shop drawings, services layouts, sections, schedules, sheets).

Written 2026-11-21 ([issue #94](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/94)). Docs only:
nothing here claims any tool works in AutoCAD. **Updated the same day** for the everyday 2D edits
(#103, #49, #105, #111, #110; [D-78](DECISIONS.md), [D-79](DECISIONS.md)): those rows now name the
tools, built and tested offline, NOT RUN live (NEEDS-CHECKING group AA). What has been proven
live is in [NEEDS-CHECKING](NEEDS-CHECKING.md) and nowhere else.

## Source, and how sure this page is

- **Ribbon source:** Autodesk's own online help for AutoCAD 2026, the tab topics ("Home tab",
  "Insert tab", ... "Visualize tab"), at `help.autodesk.com/view/ACD/2026/ENU`. Workspaces:
  **Drafting & Annotation** (Home, Insert, Annotate, Parametric, View, Manage, Output) and
  **3D Modeling** (Solid, Surface, Mesh, Visualize).
- **Be aware:** this session could not open the help site (its network blocks it), and there is no
  AutoCAD here. The panel lists below are AutoCAD's out-of-the-box ribbon as written from
  knowledge, not read off a live ribbon. Panel names and the exact place of a button move a little
  between 2021 and 2027. **Before building from a row, open that panel in AutoCAD 2027 and check.**
- **Heron's side:** the tool list in [`core/risk.py`](../src/autocad_mcp/core/risk.py) (the live
  count is `autocad-mcp.exe --list-tools`) and [03 - Tools reference](03-tools-reference.md).
- **Not audited here:** the Collaborate, Express Tools and Add-ins tabs, the contextual tabs
  (Text Editor, Hatch Editor, Block Editor ...), and the 3D Modeling workspace's own Home tab
  (it repeats Solid, Mesh and Modify).

## How to read the columns

**Heron:** **Yes** = a tool does the job. **Part** = a tool does some of it. **No** = nothing yet.
"Admin only" = only through `autocad_send_command` / `autocad_run_lisp`, which need the Admin
padlock and are not a real tool.

**Can be done** (how a program could do it):

| Word | Means |
|---|---|
| **COM** | AutoCAD's COM / ActiveX API has a call for it. The Python server can do it, as it does today |
| **.NET** | No COM call; only the plug-in's .NET API can do it (as with loft and fillet edge, [D-40](DECISIONS.md)) |
| **Typed** | No API found; only by typing the command line version. Fragile: prompts change between releases |
| **Own maths** | No call does it, but Heron can work out the geometry itself and draw the result over COM |
| **No** | Nothing a program can reach, or it is screen-only and not worth a tool |

"(unsure)" means the API was not checked against Autodesk's reference for this page. Check it
before building, the way [D-33](DECISIONS.md) did: a wrong guess can damage a model.

**Priority** is for an MEP draftsman: **high** = used every day on shop drawings; **medium** =
every project; **low** = rare, or for other trades.

---

## Drafting & Annotation workspace

### Home tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Draw | Line, Polyline, Circle, Arc, Rectangle, Ellipse, Spline, Polygon, Hatch, Point | **Yes**: `draw_line`, `draw_polyline`, `draw_circle`, `draw_arc`, `draw_rectangle`, `draw_ellipse`, `draw_spline`, `draw_point`, `add_hatch`, `make_shape` (polygon), `batch_draw` | - | COM | - |
| Draw (more) | Construction line, Ray, Region, Donut, Helix, Boundary, Divide, Measure, Revision cloud, Wipeout | **Part** (all but Boundary): `add_revision_cloud`, `add_wipeout`, `draw_3d_path` (helix), `place_along` (blocks along a run); since 2026-11-21 `add_construction_line` (xline, ray), `add_region`, `add_donut`, `divide_curve` (DIVIDE / MEASURE with points or a block) ([D-108](DECISIONS.md), #173, #174, #177, #181; live check AP NOT RUN) | **Boundary** (a closed outline from what is drawn round a point); Divide / Measure along a spline or an ellipse | Xline, ray, region: COM. Donut, divide, measure: own maths over COM. Boundary: .NET (unsure) | Boundary **medium**; rest low |
| Modify | Move, Copy, Rotate, Mirror, Scale, Offset, Array, Erase | **Yes**: `move_entities`, `copy_entities`, `rotate_entities`, `mirror_entities`, `scale_entities`, `offset_entities`, `array_entities`, `delete_entities`; since 2026-11-21 `associative_array` (path, grid and ring, editable; NOT RUN live) | Turned grids | Path / associative array: .NET in the plug-in ([D-110](DECISIONS.md)) | Built, NOT RUN ([#175](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/175), group AQ) |
| Modify (edit) | **Trim, Extend, Fillet, Chamfer, Break, Join**, Lengthen, Stretch, Blend curves | **Yes** (2026-11-21, NOT RUN live): `trim_extend`, `fillet_chamfer`, `break_curve`, `join_curves`, `stretch`, `edit_vertex`, `break_at_blocks` | Lengthen; blend curves; fillet between a line and an arc | Built with own maths over COM ([D-78](DECISIONS.md)), not .NET. Lengthen: own maths | Lengthen **medium** ([#154](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/154)); blend low ([#52](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/52) stays for blocks on arcs) |
| Modify (more) | Explode, Edit Polyline, Edit Spline, Edit Hatch, Draw Order, Reverse, Change Space, Overkill | **Part**: `explode`, `draw_order`, `edit_vertex` (2026-11-21, NOT RUN live), `modify_entity` (layer, colour, linetype, lineweight, transparency, text, height, radius, closed), `tidy_entities` (back to ByLayer) | Polyline width editing; hatch pattern / scale change; change space; **Overkill** (delete duplicate lines) | Hatch pattern: COM. Change space: .NET. Overkill: Typed, or own check over COM | Overkill **medium**; rest low |
| Annotation | Text, Mtext, Dimension, Multileader, Table | **Yes**: `add_text`, `add_mtext`, `add_dimension`, `dimension_run`, `add_label`, `batch_labels`, `add_multileader`, `add_table` | - | COM | - |
| Layers | Layer Properties, make current, On / Off, Freeze, Lock, Isolate, Match layer, **Layer States**, Merge, Delete, Copy to new layer | **Part**: `list_layers` (and saved layer states), `create_layer`, `set_layer_state` (on, frozen, locked), `set_current_layer`, `delete_layer`, `remap_layers` (moves objects to other layers); since 2026-11-21 `layer_states`, `isolate_layers`, `merge_layers` (#107; live check AB NOT RUN) | Match layer, copy to new layer | Layer states: .NET in the plug-in (D-81). Isolate, merge: COM (own steps) | low |
| Block | Insert, Create, Edit, Edit Attributes | **Yes**: `insert_block`, `make_block` (with ATTDEF), `sync_attributes` (ATTSYNC), `set_attributes`, `extract_attributes`, `set_dynamic_properties` | Edit a block's definition in place (Block Editor) | Attribute definitions: COM. ATTSYNC: .NET (plug-in). Block Editor: No | Built, NOT RUN ([#115](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/115), group AC); rest low |
| Properties | Match Properties, Colour, Linetype, Lineweight, Transparency, List | **Yes** (2026-11-21, NOT RUN live): `match_properties`, `modify_entity` (now with lineweight and transparency), `get_entity` (List) | - | COM | - |
| Groups | Group, Ungroup, Group Edit, Group selection on / off | **Yes** (2026-11-21, NOT RUN live): `group` (make, add, remove, ungroup), `list_groups` | Group selection on / off (PICKSTYLE) | COM (Groups collection); PICKSTYLE: system variable | low |
| Utilities | Measure (distance, radius, angle, area, volume), Quick Select, Select All, ID Point, QuickCalc | **Yes**: `measure`, `total_length`, `polyline_info`, `solid_properties`, `list_entities` (filters), `get_entity`, `show` (selects) | - (QuickCalc is the AI's own arithmetic) | COM | - |
| Clipboard | Cut, Copy, Copy with Base Point, Paste, Paste as Block | **Part**: `import_from_drawing` (blocks, layers, styles from a **closed** DWG), `copy_from_drawing` (objects from another **open** drawing, at a base point) | The Windows clipboard itself; Paste as Block | COM (CopyObjects between documents) | Built, NOT RUN ([#106](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/106), group AC) |
| View | Base view from model space (Inventor style views) | **No** | Drawing views from a 3D model | .NET (unsure) | low ([#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54) covers flat views) |

### Insert tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Block | Insert, Edit Attribute | **Yes**: `insert_block`, `set_attributes`, `place_from_csv`, `place_along`, `number_tags` | - | COM | - |
| Block Definition | Create Block, Define Attributes, Manage Attributes, Block Editor | **Part**: `make_block` (with attribute definitions), `sync_attributes` (add definitions, then ATTSYNC) | Manage attributes (reorder, edit a definition); dynamic block authoring | Attributes: COM. Dynamic block authoring: No | Built, NOT RUN (group AC); rest low |
| Reference | Attach (DWG, image, PDF, DWF, DGN), Clip, Adjust, Underlay Layers, Frames | **Part**: `attach_xref`, `manage_xref`, `xref_tree`, `list_blocks` (paths); `attach_underlay` (image, PDF, DWF, DGN) and `clip_reference` (xref, image, underlay), built 2026-11-21, NOT RUN live ([#104](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/104)) | Fade / contrast; underlay layers; frames | Image attach, image clip, fade: COM. PDF / DWF / DGN underlay: .NET. Xref clip: .NET (spatial filter) | **high** |
| Point Cloud | Attach, ReCap | **No** | All | .NET, partly (unsure) | low |
| Import | Import, PDF Import | **Part**: `import_pdf` (one PDF page as lines, text and hatches; built 2026-11-21, NOT RUN live, [D-106](DECISIONS.md)) | Import of other formats; a PDF's pictures; SHX text back to text (PDFSHXTEXT) | PDF Import: Typed (`-PDFIMPORT`, no API). Other imports: COM `Import` (WMF, SAT, EPS) | other imports low |
| Data | Field, Update Fields, Hyperlink, OLE Object, Data Link | **Part**: `add_field_label` (length / area fields), `table_from_excel` and `update_table_links` (**Data Link**, by the plug-in); since 2026-11-21 `hyperlinks`, `list_hyperlinks` (NOT RUN live) | Other fields (sheet number, date, attribute of another block) | Fields: COM (field codes in text). Hyperlink: COM. Data Link: .NET (plug-in). OLE: No | Data Link built, NOT RUN ([#117](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/117), group AC); hyperlinks built, NOT RUN ([#178](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/178), group AQ); rest low |
| Linking & Extraction | Extract Data, Download / Upload from source | **Part**: `extract_attributes`, `count_blocks`, `count_text`, `drawing_report` | DATAEXTRACTION's own table and wizard (Heron already reads the same data) | COM (the reads); the wizard: No | low |
| Location | Set Location (geographic) | **Yes** (2026-11-21, NOT RUN live): `geo_location`, `get_geo_location`; the sun's place is the same LATITUDE / LONGITUDE as `set_sun` | Projected systems in feet | .NET in the plug-in ([D-111](DECISIONS.md)) | Built, NOT RUN ([#180](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/180), group AQ) |

### Annotate tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Text | Multiline, Single line, Text Style, Find, Check Spelling | **Yes**: `add_text`, `add_mtext`, `create_styles`, `find_text`, `find_replace_text`, `text_clean`, `align_text` | Spell check (the AI can read the text with `find_text` and say what is wrong; no tool does it as a job) | Own (read over COM) | low |
| Dimensions | Linear, Aligned, Angular, Arc Length, Radius, Diameter, Jogged, Ordinate, Quick Dim, Continue, Baseline, Dim Style | **Yes**: `add_dimension` (aligned, horizontal, vertical, radial, diametric, angular), `dimension_run` (chain, baseline, overall, ordinate), `create_styles` | Arc length and jogged radius dimensions | COM | low |
| Dimensions (edit) | Dim Space, Dim Break, Inspect, Jog line, Oblique, Text angle, Update, Override | **Part**: `find_replace_text` (dimension text overrides); since 2026-11-21 `space_dimensions`, `break_dimensions` (#116; live check AB NOT RUN) | Jog line; oblique; re-apply style | Space: own maths, the plug-in moves the line (COM has no definition points, D-80). Break: typed DIMBREAK. Jog line, inspect: Typed (unsure). Oblique, text angle, style: COM | low |
| Centerlines | Center Mark, Centerline | **Part**: `add_centre_marks` (plain crosses and lines) | AutoCAD's associative centre mark / centreline objects (they follow the circle) | Typed (unsure) | low |
| Leaders | Multileader, Add / Remove Leader, Align, Collect, Multileader Style | **Part**: `add_label`, `batch_labels` (lined up columns), `add_multileader`, `create_styles` (**multileader style**, by the plug-in) | Add / remove an arrow on an existing multileader; align and collect existing ones | Add / remove arrow: COM. Align: own maths. Collect: Typed. Style: .NET (plug-in, [D-104](DECISIONS.md)) | Style built, NOT RUN ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68), group AN); rest low |
| Tables | Table, Link Data, Extract Data, Table Style | **Yes**: `add_table`, `table_from_excel` (link to Excel), `set_table_cells` (edit cells of an existing table), `create_styles` (**table style**, by the plug-in) | - | Cells: COM. Style: .NET (plug-in, [D-104](DECISIONS.md)). Excel link: .NET (plug-in) | Link and cells built, NOT RUN (group AC); style built, NOT RUN ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68), group AN) |
| Markup | Revision Cloud, Wipeout | **Yes**: `add_revision_cloud`, `add_wipeout` | - | COM / Typed ([D-38](DECISIONS.md)) | - |
| Annotation Scaling | Scale list, Add / Delete current scale, Sync scale positions, Annotative | **Part**: `drawing_setup` (the drawing's annotation scale, CANNOSCALE); since 2026-11-21 `annotative` on the text, dimension and multileader tools, `annotation_scales`, `list_annotation_scales` (#108; live check AB NOT RUN) | Sync scale positions | .NET (object scales), in the plug-in (D-81) | low ([#65](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/65) covers viewports only) |
| Markup Import / Assist | Import a marked-up PDF or picture, Assist | **No** | All | No (Autodesk cloud service) | low |

### Parametric tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Geometric | Auto Constrain, Coincident, Parallel, Perpendicular, Horizontal, Vertical, Tangent, Equal, Symmetric, Fix | **No** | All | Typed (GEOMCONSTRAINT on the command line); .NET only in part (unsure) | low |
| Dimensional | Linear, Aligned, Radius, Diameter, Angular constraints, Convert | **No** | All | Typed; .NET in part (unsure) | low |
| Manage | Delete Constraints, Parameters Manager | **No** | All | Typed (unsure) | low |

Constraints matter more to a machine designer than to an MEP draftsman, and Heron draws from
numbers already, so the whole tab is low.

### View tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Viewport Tools | UCS icon, ViewCube, Navigation bar on / off | **Admin only** (`set_variable`) | A plain on / off tool | COM (system variables) | low |
| Model Viewports | Viewport configuration, Named, Join, Restore (tiled model viewports) | **Yes** (2026-11-21, NOT RUN live): `tiled_viewports` (1, 2, 3 or 4) | Join; restoring another named configuration | COM (Viewports collection, [D-111](DECISIONS.md)) | Built, NOT RUN ([#176](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/176), group AQ) |
| Named Views | View Manager, New View | **Yes**: `save_view`, `list_views`, `zoom` | - | COM | - |
| Visual Styles / 3D views | Visual style, view direction | **Yes**: `set_3d_view` | Read the current visual style back | COM | low ([#59](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/59)) |
| Palettes | Tool Palettes, Properties, Sheet Set Manager, DesignCenter, QuickCalc | **Part**: `get_entity` (Properties), `import_from_drawing` (DesignCenter's job) | Palettes themselves are screen windows; sheet sets | Palettes: No. Sheet sets: COM library (unsure) | Sheet sets **medium** ([#66](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/66)) |
| Interface | File tabs, Layout tabs, Tile, Toolbars, User Interface | **Part**: `list_drawings`, `switch_drawing`, `list_layouts` | - (screen layout) | No | - |

### Manage tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Action Recorder | Record, Play | **Yes** in spirit: `saved_command`, `sequence` | - | - | - |
| Customization | User Interface (CUI), Tool Palettes, Edit Aliases | **No** | All | No (and should stay that way: Heron does not change the modeller's AutoCAD set-up) | - |
| Applications | Load Application, Run Script, Visual LISP, VBA | **Admin only**: `run_lisp`, `send_command` | - (deliberately Admin) | Typed | - |
| CAD Standards | Configure, Check, Layer Translator | **Part**: `check_standards` (rules file), `remap_layers` (layer translator's job), `checklist` | Check against a reference DWS / DWG | COM (read both drawings) | **medium** ([#69](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/69)) |
| Cleanup | Purge, Overkill, Audit | **Part**: `purge`, `audit` (both Admin), `tidy_entities`; `overkill` built 2026-11-21, NOT RUN live ([#112](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/112)) | Polyline segments overlapping are listed, not fixed | Typed, or own check over COM | **medium** |

### Output tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Plot | Plot, Page Setup Manager, Plotter Manager, Preview | **Yes**: `export` (PDF), `page_setup`, `preview` | Make or edit a plotter (PC3) file | No (PC3 editing has no API, unsure) | low |
| Export to DWF / PDF | Export PDF, Export DWF, Page Setup Override | **Yes** (DWF 2026-11-21, NOT RUN live): `export` (PDF, DWF, DXF, WMF, SAT, BMP, EPS, STL), `publish_pdf` | DWFx | COM (plot to the DWF6 ePlot plotter, [D-111](DECISIONS.md)) | DWF built, NOT RUN ([#179](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/179), group AQ); DWFx low |
| Publish | Publish, Batch Plot, 3D Print, View Details | **Part**: `publish_pdf` (one drawing's sheets) | **Batch plot a folder** of drawings; 3D print | Folder: COM / .NET. 3D print: No | Folder **high** ([#67](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/67)); 3D print low |
| (Application menu) | eTransmit: pack a drawing with its xrefs, fonts and plot styles to send out | **Part**: `xref_tree`; `etransmit` (zip or folder, report, missing list) built 2026-11-21, NOT RUN live ([#114](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/114)) | Paths inside the packed drawing are not rewritten | COM library for transmittal (unsure) | **medium** |

## 3D Modeling workspace

### Solid tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Primitive | Box, Cylinder, Cone, Sphere, Wedge, Torus, Pyramid, Polysolid | **Part**: `add_solid` (box, wedge, cylinder, cone, sphere, torus, elliptical cylinder and cone) | Pyramid; Polysolid (a wall-like solid along a path) | .NET (unsure for COM) | low |
| Solid | Extrude, Revolve, Sweep, Loft, Presspull | **Yes**: `extrude_profile` (extrude, revolve, sweep), `loft`, `press_pull_faces` | - | COM / .NET | - |
| Boolean | Union, Subtract, Intersect, Interfere | **Yes**: `solid_boolean`, `check_interference` (clash check) | - | COM | - |
| Solid Editing | Slice, Thicken, Shell, Fillet Edge, Chamfer Edge, Imprint, Separate, Check, Extract Edges, Offset / Taper / Move / Delete faces | **Part**: `slice_solid`, `thicken_surface`, `shell_solid`, `fillet_solid_edges`, `chamfer_solid_edges`, `list_solid_faces_and_edges` | Imprint, separate, check, extract edges; offset, taper, move and delete faces | .NET | low |
| Section | Section Plane, Live Section, Generate Section, Flatshot | **Yes** (by the plug-in, [D-95](DECISIONS.md)): `section_plane` (plane + 2D section block), `flatten_views` (Flatshot / SOLPROF); `SectionSolid` still left out ([D-33](DECISIONS.md)) | Live section, jogged section lines, hidden lines in a flat view | .NET | done ([#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54), [#109](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/109)); live rows AH4-AH8 NOT RUN |

### Surface tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Create | Network, Loft, Sweep, Planar, Extrude, Revolve, Blend, Patch, Offset | **Part** (by the plug-in, [D-95](DECISIONS.md)): `add_surface` (planar, network), `loft(surface=true)`; `thicken_surface` | Sweep, extrude and revolve to a surface; blend, patch, offset | .NET | low ([#58](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/58) done) |
| Edit | Fillet, Trim, Untrim, Extend, Sculpt | **No** | All | .NET | low |
| Control Vertices | Show / hide CVs, Rebuild, Add / remove CVs | **No** | All | .NET | low ([#56](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/56) for splines) |
| Curves / Project Geometry | Spline CV, Extract isolines, Project to UCS / view | **Part**: `draw_spline` (fit points) | Projection onto a surface | .NET | low |
| Analysis | Zebra, Curvature, Draft | **No** | All (screen display) | No | low |

### Mesh tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Primitives | Mesh box, cylinder ...; Revolved, Edge, Ruled, Tabulated surfaces | **Part** (by the plug-in, [D-95](DECISIONS.md)): `add_mesh` (box, wedge, cylinder, cone, sphere, torus, pyramid; or from a solid) | Revolved, edge, ruled, tabulated surfaces | Old polyface / 3D meshes: COM. Smooth mesh (SubD): .NET | low ([#58](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/58) done) |
| Mesh | Smooth more / less, Refine, Crease | **No** | All | .NET | low |
| Mesh Edit | Extrude face, Split, Merge, Close hole, Collapse | **No** | All | .NET | low |
| Convert Mesh | Convert to solid / surface | **No** | Convert a mesh (an imported model) to a solid | .NET | low |

### Visualize tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Named Views / Visual Styles | Views, visual style, X-ray, shadows | **Part**: `save_view`, `set_3d_view` (reads the style back, [D-86](DECISIONS.md)) | X-ray and shadows | COM (system variables) | low |
| Lights | Point, Spot, Distant, Web light; Default lighting; Exposure | **Yes**: `add_light`, `list_lights`, `switch_lights` (lights, sun, default lighting), `set_render_exposure` ([D-87](DECISIONS.md)) | Exposure if 2027 has no EXPVALUE (AE14) | COM / .NET | low |
| Sun & Location | Sun status, date, time, location | **Yes**: `set_sun` (date, time, place, on), `list_lights` reads it ([D-86](DECISIONS.md)) | Sky and shadow settings | COM (system variables) / .NET | low |
| Materials | Materials Browser, Material Editor, Mapping | **Part**: `list_materials`, `apply_material`, `create_material` | Autodesk's material library ([03](03-tools-reference.md#materials-change-listing-is-read)); mapping | Library: No. Mapping: .NET (unsure) | low |
| Camera | Create Camera, Show Cameras | **Yes**: `add_camera_view` (a perspective view with a lens, [D-86](DECISIONS.md)) | The camera glyph (not drawn) | .NET | low |
| Render | Render, Render presets, Environment | **No, on purpose**: Heron sets the render up (camera, sun, lights, exposure) and the modeller presses Render; `autocad_render` was removed because `-render` can stall AutoCAD ([D-87](DECISIONS.md), [#158](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/158)) | Presets and environment | Typed only ([03](03-tools-reference.md#materials-change-listing-is-read)) | - |

---

## Top 10 gaps for an MEP draftsman

In order. Gaps that had no issue on 2026-11-21 were filed the same day as [#103](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/103) to [#119](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/119) (label `from-ribbon-audit`).

| # | Gap | Panel | Can be done | Issue |
|---|---|---|---|---|
| 1 | **Trim, extend, 2D fillet and chamfer, break at a point, join** on lines and polylines (built 2026-11-21, NOT RUN live) | Home > Modify | .NET (trim, extend, break, join); own maths (fillet, chamfer) | [#103](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/103); break with arcs is [#52](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/52) |
| 2 | **Change the shape of what is drawn**: stretch, move a vertex or an end point (built 2026-11-21, NOT RUN live), lengthen (not yet) | Home > Modify | .NET / COM | [#49](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/49) |
| 3 | **Attach an image or a PDF underlay**, and **clip** an xref, image or underlay (consultant backgrounds) | Insert > Reference | Image: COM. PDF underlay and xref clip: .NET | [#104](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/104) |
| 4 | **Explode** and **draw order** (send a hatch or wipeout to the back) (built 2026-11-21, NOT RUN live) | Home > Modify | COM | [#105](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/105) |
| 5 | **Copy objects from one open drawing to another** (Copy with Base Point / Paste) | Home > Clipboard | COM | [#106](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/106): built as `autocad_copy_from_drawing`, NOT RUN |
| 6 | **PDF of a folder of drawings** (batch plot) and a sheet list | Output > Publish | COM / .NET | [#67](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/67), [#66](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/66) |
| 7 | **Layer states** (save, bring back), layer isolate and merge | Home > Layers | COM | [#107](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/107) |
| 8 | **Annotative** text, dimensions and multileaders, with their scales | Annotate > Annotation Scaling | .NET | [#108](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/108); viewports are [#65](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/65) |
| 9 | **Section plane and a 2D section** from a 3D services model; Flatshot | Solid > Section | .NET | Flatshot is [#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54); the section plane is [#109](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/109) |
| 10 | **Groups** (make, list, ungroup) and **match properties** (built 2026-11-21, NOT RUN live) | Home > Groups, Properties | COM | [#110](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/110), [#111](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/111) |

Just below the ten: Overkill [#112](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/112), PDF Import [#113](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/113) (built 2026-11-21, NOT RUN live), eTransmit [#114](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/114), multileader
and table styles ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68), built 2026-11-21, NOT RUN live), dimension space
and break [#116](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/116), attribute definitions [#115](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/115), Data Link to Excel [#117](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/117), Boundary [#118](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/118). The low
ones are listed together in [#119](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/119).

## What this page is not

- Not a promise: a gap marked COM or .NET can still turn out harder once the call is tried.
- Not proof: every tool named under **Heron** is built, but most are not yet proven live; see
  [NEEDS-CHECKING](NEEDS-CHECKING.md).
- Not a build plan: the order of work is the owner's, in [ROADMAP](ROADMAP.md).
