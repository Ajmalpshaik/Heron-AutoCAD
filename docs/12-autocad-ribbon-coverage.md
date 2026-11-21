# 12 - AutoCAD ribbon coverage: what Heron covers, what is missing

Every panel of AutoCAD's default ribbon, checked against Heron's tools. For each panel: the main
commands, the Heron tool that does the same job, what is missing, whether a program can do it, and
a priority for an **MEP draftsman** (shop drawings, services layouts, sections, schedules, sheets).

Written 2026-11-21 ([issue #94](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/94)). Docs only:
nothing here is built, and nothing here claims any tool works in AutoCAD. What has been proven
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
- **Heron's side:** the tool list in [`core/risk.py`](../src/autocad_mcp/core/risk.py) (138 tools
  on 2026-11-21) and [03 - Tools reference](03-tools-reference.md).
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
| Draw (more) | Construction line, Ray, Region, Donut, Helix, Boundary, Divide, Measure, Revision cloud, Wipeout | **Part**: `add_revision_cloud`, `add_wipeout`, `draw_3d_path` (helix), `place_along` (blocks along a run) | Construction line and ray; region; donut; **Boundary** (a closed outline from what is drawn round a point); Divide / Measure with points | Xline, ray, region, donut: COM. Boundary: .NET (unsure). Divide / Measure with points: own maths | Boundary **medium**; rest low |
| Modify | Move, Copy, Rotate, Mirror, Scale, Offset, Array, Erase | **Yes**: `move_entities`, `copy_entities`, `rotate_entities`, `mirror_entities`, `scale_entities`, `offset_entities`, `array_entities`, `delete_entities` | Path array and **associative** arrays (the ones that stay editable) | Path / associative array: .NET (unsure) | low |
| Modify (edit) | **Trim, Extend, Fillet, Chamfer, Break, Join**, Lengthen, Stretch, Blend curves | **Part**: `break_at_blocks` (straight lines only); Admin only for the rest | Trim, extend, 2D fillet and chamfer, break at a point, join, lengthen, stretch | Trim / extend / break / join: .NET (curve splitting and joining). Fillet / chamfer / lengthen: own maths. Stretch: .NET | **high** ([#49](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/49), [#52](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/52) cover stretch and break; trim / extend / fillet / join are [#103](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/103)) |
| Modify (more) | Explode, Edit Polyline, Edit Spline, Edit Hatch, Draw Order, Reverse, Change Space, Overkill | **Part**: `modify_entity` (layer, colour, linetype, text, height, radius, closed), `tidy_entities` (back to ByLayer) | **Explode**; **Draw order** (wipeout / hatch to the back); polyline vertex and width editing; hatch pattern / scale change; change space; **Overkill** (delete duplicate lines) | Explode, draw order, polyline vertices, hatch pattern: COM. Change space: .NET. Overkill: Typed, or own check over COM | Explode, draw order **high**; Overkill **medium**; rest low |
| Annotation | Text, Mtext, Dimension, Multileader, Table | **Yes**: `add_text`, `add_mtext`, `add_dimension`, `dimension_run`, `add_label`, `batch_labels`, `add_multileader`, `add_table` | - | COM | - |
| Layers | Layer Properties, make current, On / Off, Freeze, Lock, Isolate, Match layer, **Layer States**, Merge, Delete, Copy to new layer | **Part**: `list_layers`, `create_layer`, `set_layer_state` (on, frozen, locked), `set_current_layer`, `delete_layer`, `remap_layers` (moves objects to other layers) | **Layer states** (save and bring back a set of on / off / frozen); **layer isolate** by layer; layer merge | Layer states: COM (LayerStateManager). Isolate, merge: COM (own steps) | **medium** |
| Block | Insert, Create, Edit, Edit Attributes | **Yes**: `insert_block`, `make_block`, `set_attributes`, `extract_attributes`, `set_dynamic_properties` | Edit a block's definition in place (Block Editor); define attributes (ATTDEF); ATTSYNC | Attribute definitions: COM. ATTSYNC: .NET or Typed. Block Editor: No | ATTDEF **medium**; rest low |
| Properties | Match Properties, Colour, Linetype, Lineweight, Transparency, List | **Part**: `modify_entity` (colour, linetype, layer), `get_entity` (List) | **Match properties** from one object to others; lineweight and transparency per object | COM | **medium** |
| Groups | Group, Ungroup, Group Edit, Group selection on / off | **No** | All of it | COM (Groups collection) | **medium** |
| Utilities | Measure (distance, radius, angle, area, volume), Quick Select, Select All, ID Point, QuickCalc | **Yes**: `measure`, `total_length`, `polyline_info`, `solid_properties`, `list_entities` (filters), `get_entity`, `show` (selects) | - (QuickCalc is the AI's own arithmetic) | COM | - |
| Clipboard | Cut, Copy, Copy with Base Point, Paste, Paste as Block | **Part**: `import_from_drawing` (blocks, layers, styles from a **closed** DWG) | **Copy objects from one open drawing to another** | COM (CopyObjects between documents) | **high** |
| View | Base view from model space (Inventor style views) | **No** | Drawing views from a 3D model | .NET (unsure) | low ([#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54) covers flat views) |

### Insert tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Block | Insert, Edit Attribute | **Yes**: `insert_block`, `set_attributes`, `place_from_csv`, `place_along`, `number_tags` | - | COM | - |
| Block Definition | Create Block, Define Attributes, Manage Attributes, Block Editor | **Part**: `make_block` | Define attributes; manage attributes; dynamic block authoring | Attributes: COM. Dynamic block authoring: No | ATTDEF **medium**; rest low |
| Reference | Attach (DWG, image, PDF, DWF, DGN), Clip, Adjust, Underlay Layers, Frames | **Part**: `attach_xref`, `manage_xref`, `xref_tree`, `list_blocks` (paths) | **Attach an image**; **attach a PDF underlay** (consultant backgrounds); DWF / DGN underlays; **clip** an xref, image or underlay; fade / contrast | Image attach, image clip, fade: COM. PDF / DWF / DGN underlay: .NET. Xref clip: .NET (spatial filter) | **high** |
| Point Cloud | Attach, ReCap | **No** | All | .NET, partly (unsure) | low |
| Import | Import, PDF Import | **No** | **PDF Import** (turn a PDF into lines); import of other formats | PDF Import: Typed (`-PDFIMPORT`). Other imports: COM `Import` (WMF, SAT, EPS) | **medium** |
| Data | Field, Update Fields, Hyperlink, OLE Object, Data Link | **Part**: `add_field_label` (length / area fields) | Other fields (sheet number, date, attribute of another block); hyperlinks on objects; **Data Link** (an Excel range as a live table) | Fields: COM (field codes in text). Hyperlink: COM. Data Link: .NET. OLE: No | Data Link **medium**; rest low |
| Linking & Extraction | Extract Data, Download / Upload from source | **Part**: `extract_attributes`, `count_blocks`, `count_text`, `drawing_report` | DATAEXTRACTION's own table and wizard (Heron already reads the same data) | COM (the reads); the wizard: No | low |
| Location | Set Location (geographic) | **No** | Geographic location | .NET (unsure) | low ([#61](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/61) covers the sun's place) |

### Annotate tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Text | Multiline, Single line, Text Style, Find, Check Spelling | **Yes**: `add_text`, `add_mtext`, `create_styles`, `find_text`, `find_replace_text`, `text_clean`, `align_text` | Spell check (the AI can read the text with `find_text` and say what is wrong; no tool does it as a job) | Own (read over COM) | low |
| Dimensions | Linear, Aligned, Angular, Arc Length, Radius, Diameter, Jogged, Ordinate, Quick Dim, Continue, Baseline, Dim Style | **Yes**: `add_dimension` (aligned, horizontal, vertical, radial, diametric, angular), `dimension_run` (chain, baseline, overall, ordinate), `create_styles` | Arc length and jogged radius dimensions | COM | low |
| Dimensions (edit) | Dim Space, Dim Break, Inspect, Jog line, Oblique, Text angle, Update, Override | **Part**: `find_replace_text` (dimension text overrides) | Space dimensions evenly; break a dimension where it crosses; jog line; oblique; re-apply style | Space: own maths over COM. Break, jog line, inspect: Typed (unsure). Oblique, text angle, style: COM | Space, break **medium**; rest low |
| Centerlines | Center Mark, Centerline | **Part**: `add_centre_marks` (plain crosses and lines) | AutoCAD's associative centre mark / centreline objects (they follow the circle) | Typed (unsure) | low |
| Leaders | Multileader, Add / Remove Leader, Align, Collect, Multileader Style | **Part**: `add_label`, `batch_labels` (lined up columns), `add_multileader` | Add / remove an arrow on an existing multileader; align and collect existing ones; **multileader style** | Add / remove arrow: COM. Align: own maths. Collect: Typed. Style: .NET (COM unsure) | Style **medium** ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68)); rest low |
| Tables | Table, Link Data, Extract Data, Table Style | **Part**: `add_table` | **Table style**; link to Excel; edit a cell of an existing table | Cells: COM. Style: .NET (COM unsure). Excel link: .NET | Edit cells **medium**; style [#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68) |
| Markup | Revision Cloud, Wipeout | **Yes**: `add_revision_cloud`, `add_wipeout` | - | COM / Typed ([D-38](DECISIONS.md)) | - |
| Annotation Scaling | Scale list, Add / Delete current scale, Sync scale positions, Annotative | **Part**: `drawing_setup` (the drawing's annotation scale, CANNOSCALE) | **Annotative** text, dimensions and multileaders; add a scale to objects; the scale list | .NET (object scales) | **medium** ([#65](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/65) covers viewports only) |
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
| Model Viewports | Viewport configuration, Named, Join, Restore (tiled model viewports) | **No** | Split model space into tiled viewports | COM (Viewports collection) | low |
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
| Cleanup | Purge, Overkill, Audit | **Part**: `purge`, `audit` (both Admin), `tidy_entities` | Overkill (see Home / Modify) | Typed, or own check over COM | **medium** |

### Output tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Plot | Plot, Page Setup Manager, Plotter Manager, Preview | **Yes**: `export` (PDF), `page_setup`, `preview` | Make or edit a plotter (PC3) file | No (PC3 editing has no API, unsure) | low |
| Export to DWF / PDF | Export PDF, Export DWF, Page Setup Override | **Part**: `export` (PDF, DXF, WMF, SAT, BMP, EPS, STL), `publish_pdf` | DWF / DWFx | COM (plot to the DWF6 ePlot plotter) | low |
| Publish | Publish, Batch Plot, 3D Print, View Details | **Part**: `publish_pdf` (one drawing's sheets) | **Batch plot a folder** of drawings; 3D print | Folder: COM / .NET. 3D print: No | Folder **high** ([#67](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/67)); 3D print low |
| (Application menu) | eTransmit: pack a drawing with its xrefs, fonts and plot styles to send out | **Part**: `xref_tree` (lists what would be packed) | **Make the pack** | COM library for transmittal (unsure) | **medium** |

## 3D Modeling workspace

### Solid tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Primitive | Box, Cylinder, Cone, Sphere, Wedge, Torus, Pyramid, Polysolid | **Part**: `add_solid` (box, wedge, cylinder, cone, sphere, torus, elliptical cylinder and cone) | Pyramid; Polysolid (a wall-like solid along a path) | .NET (unsure for COM) | low |
| Solid | Extrude, Revolve, Sweep, Loft, Presspull | **Yes**: `extrude_profile` (extrude, revolve, sweep), `loft`, `press_pull_faces` | - | COM / .NET | - |
| Boolean | Union, Subtract, Intersect, Interfere | **Yes**: `solid_boolean`, `check_interference` (clash check) | - | COM | - |
| Solid Editing | Slice, Thicken, Shell, Fillet Edge, Chamfer Edge, Imprint, Separate, Check, Extract Edges, Offset / Taper / Move / Delete faces | **Part**: `slice_solid`, `thicken_surface`, `shell_solid`, `fillet_solid_edges`, `chamfer_solid_edges`, `list_solid_faces_and_edges` | Imprint, separate, check, extract edges; offset, taper, move and delete faces | .NET | low |
| Section | Section Plane, Live Section, Generate Section, Flatshot | **No** (`SectionSolid` left out on purpose, [D-33](DECISIONS.md)) | **A section plane and a 2D section from the model**; Flatshot | .NET | **medium** ([#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54) covers Flatshot / SOLPROF; the section plane is [#109](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/109)) |

### Surface tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Create | Network, Loft, Sweep, Planar, Extrude, Revolve, Blend, Patch, Offset | **No** (only `thicken_surface` uses a surface) | All | .NET | low ([#58](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/58)) |
| Edit | Fillet, Trim, Untrim, Extend, Sculpt | **No** | All | .NET | low |
| Control Vertices | Show / hide CVs, Rebuild, Add / remove CVs | **No** | All | .NET | low ([#56](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/56) for splines) |
| Curves / Project Geometry | Spline CV, Extract isolines, Project to UCS / view | **Part**: `draw_spline` (fit points) | Projection onto a surface | .NET | low |
| Analysis | Zebra, Curvature, Draft | **No** | All (screen display) | No | low |

### Mesh tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Primitives | Mesh box, cylinder ...; Revolved, Edge, Ruled, Tabulated surfaces | **No** | All | Old polyface / 3D meshes: COM. Smooth mesh (SubD): .NET | low ([#58](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/58)) |
| Mesh | Smooth more / less, Refine, Crease | **No** | All | .NET | low |
| Mesh Edit | Extrude face, Split, Merge, Close hole, Collapse | **No** | All | .NET | low |
| Convert Mesh | Convert to solid / surface | **No** | Convert a mesh (an imported model) to a solid | .NET | low |

### Visualize tab

| Panel | Main commands | Heron | Missing | Can be done | Priority |
|---|---|---|---|---|---|
| Named Views / Visual Styles | Views, visual style, X-ray, shadows | **Part**: `save_view`, `set_3d_view` | Read the visual style back; X-ray and shadows | COM (system variables) | low ([#59](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/59)) |
| Lights | Point, Spot, Distant, Web light; Default lighting; Exposure | **Part**: `add_light` (point, spot, web, distant) | List and switch lights, default lighting, exposure | COM / .NET | low ([#62](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/62), [#63](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/63)) |
| Sun & Location | Sun status, date, time, location | **No** | All | COM (system variables) / .NET | low ([#61](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/61)) |
| Materials | Materials Browser, Material Editor, Mapping | **Part**: `list_materials`, `apply_material`, `create_material` | Autodesk's material library ([03](03-tools-reference.md#materials-and-rendering-change-listing-is-read-rendering-is-admin)); mapping | Library: No. Mapping: .NET (unsure) | low |
| Camera | Create Camera, Show Cameras | **No** | All | Typed (`CAMERA`) | low ([#60](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/60)) |
| Render | Render, Render presets, Environment | **Part**: `render` (Admin, by typing `-render`) | Presets and environment | Typed only ([03](03-tools-reference.md#materials-and-rendering-change-listing-is-read-rendering-is-admin)) | low |

---

## Top 10 gaps for an MEP draftsman

In order. Gaps that had no issue on 2026-11-21 were filed the same day as [#103](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/103) to [#119](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/119) (label `from-ribbon-audit`).

| # | Gap | Panel | Can be done | Issue |
|---|---|---|---|---|
| 1 | **Trim, extend, 2D fillet and chamfer, break at a point, join** on lines and polylines | Home > Modify | .NET (trim, extend, break, join); own maths (fillet, chamfer) | [#103](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/103); break with arcs is [#52](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/52) |
| 2 | **Change the shape of what is drawn**: stretch, move a vertex or an end point, lengthen | Home > Modify | .NET / COM | [#49](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/49) |
| 3 | **Attach an image or a PDF underlay**, and **clip** an xref, image or underlay (consultant backgrounds) | Insert > Reference | Image: COM. PDF underlay and xref clip: .NET | [#104](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/104) |
| 4 | **Explode** and **draw order** (send a hatch or wipeout to the back) | Home > Modify | COM | [#105](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/105) |
| 5 | **Copy objects from one open drawing to another** (Copy with Base Point / Paste) | Home > Clipboard | COM | [#106](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/106) |
| 6 | **PDF of a folder of drawings** (batch plot) and a sheet list | Output > Publish | COM / .NET | [#67](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/67), [#66](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/66) |
| 7 | **Layer states** (save, bring back), layer isolate and merge | Home > Layers | COM | [#107](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/107) |
| 8 | **Annotative** text, dimensions and multileaders, with their scales | Annotate > Annotation Scaling | .NET | [#108](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/108); viewports are [#65](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/65) |
| 9 | **Section plane and a 2D section** from a 3D services model; Flatshot | Solid > Section | .NET | Flatshot is [#54](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/54); the section plane is [#109](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/109) |
| 10 | **Groups** (make, list, ungroup) and **match properties** | Home > Groups, Properties | COM | [#110](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/110), [#111](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/111) |

Just below the ten: Overkill [#112](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/112), PDF Import [#113](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/113), eTransmit [#114](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/114), multileader
and table styles ([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68)), dimension space
and break [#116](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/116), attribute definitions [#115](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/115), Data Link to Excel [#117](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/117), Boundary [#118](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/118). The low
ones are listed together in [#119](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/119).

## What this page is not

- Not a promise: a gap marked COM or .NET can still turn out harder once the call is tried.
- Not proof: every tool named under **Heron** is built, but most are not yet proven live; see
  [NEEDS-CHECKING](NEEDS-CHECKING.md).
- Not a build plan: the order of work is the owner's, in [ROADMAP](ROADMAP.md).
