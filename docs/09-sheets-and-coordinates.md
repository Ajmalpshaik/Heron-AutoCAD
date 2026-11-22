# 09 - Sheets, coordinates and shop drawings

The three things a draftsman does that a drawing tool on its own cannot: **work in the coordinate
system the modeller set**, **lay a sheet out**, and **turn somebody else's model into an issued
drawing**. Decisions: [D-27](DECISIONS.md), [D-28](DECISIONS.md), [D-29](DECISIONS.md),
[D-90](DECISIONS.md), [D-91](DECISIONS.md).

---

## 1. The UCS: why a line lands in the wrong place

Every coordinate AutoCAD's Automation API takes or returns is a **World** coordinate. The modeller
does not work there. They set a UCS — moved to a grid intersection, turned onto a wall, tilted onto
a sloping roof — and from then on every number they read off the screen is in that system.

So "draw a line from 0,0 to 5000,0" means two different lines, and the drawing gives no hint which
one was used.

| Tool | Level | What it is for |
|---|---|---|
| `autocad_get_ucs` | Read | Is a UCS set? Moved, turned how many degrees, tilted, flipped? What is saved in the drawing? |
| `autocad_set_ucs` | Change | Set it: back to `world`, onto a saved one, to an `origin` and angle, from `3point`, aligned to an `entity`, or flat on the `view`. `save_as` keeps it under a name |
| `autocad_convert_points` | Read | AutoLISP's `trans`: points (and angles) between the UCS and the world, changing nothing |

**Nothing draws blind.** `autocad_status` now reports the UCS on every drawing, and adds a
`ucs_advice` sentence when it is not the world one. The gate already forces `autocad_status` before
any change ([D-19](DECISIONS.md)), so the warning arrives before the first line.

**Drawing in the UCS.** `autocad_batch_draw` takes `coords="ucs"`: every point is converted and
every angle picks up the UCS rotation before a single expression is sent, so a rectangle square to
a turned grid comes out turned. The arithmetic is in
[`acad/coords.py`](../src/autocad_mcp/acad/coords.py), built from `UCSORG`, `UCSXDIR` and `UCSYDIR`,
and tested without AutoCAD.

The single-entity tools take it too ([D-96](DECISIONS.md)): every `autocad_draw_*` tool, text,
mtext, dimensions and blocks, and move, copy, rotate, scale, mirror and array. Each converts its
points, its vertex lists and its angles through the same transform. A displacement (move, copy) is
turned but not moved; a turn (rotate, a polar array's fill) is the same amount on any plan UCS. A
rectangle comes out square to the UCS, a horizontal dimension measures along the UCS's own X, and a
rectangular array lays its rows along the UCS's axes (copy by copy, as ARRAY over COM would follow
the world's). A polyline drawn in a UCS moved up or down gets that height as its Elevation.

**A flipped UCS** (its Z pointing down, a mirror of the plan) turns angles the other way: an arc's
ends swap and a bulge changes sign, and `autocad_convert_points` turns angles that way too. Text,
mtext, dimensions, multileaders, tables, blocks, xrefs and super hatches are **refused** on one,
because over COM they would lie on the world plane and read mirrored in that view, where AutoCAD's
own commands would lay them on the UCS's plane.

**A tilted UCS is refused, not guessed.** On a UCS tilted out of the world XY plane a flat `[x, y]`
has no single world answer and an on-screen angle is not a world angle, so `coords="ucs"` says so
and points you at `autocad_convert_points`, which gives all three numbers.

---

## 2. One location, used everywhere

You window a region to plot it. Then you want a viewport on that region. Then a detail bubble on it.
Each time the two corners come out slightly different.

A **named view** is AutoCAD's own answer, and here it is a location you name once:

```
autocad_save_view(name="DETAIL-A", corner1=[...], corner2=[...])   # or handles=[...] + pad
autocad_export(path="...pdf", area="view", view_name="DETAIL-A")   # plot that exact area
autocad_add_viewport(view_name="DETAIL-A", scale="1:20")           # a viewport on that exact area
autocad_list_views()                                              # read the corners back
```

| Tool | Level | Notes |
|---|---|---|
| `autocad_save_view` | Change | From two corners, or from the objects' own extents with `pad`. `coords="ucs"` converts the window first. `zoom_to` shows it |
| `autocad_list_views` | Read | Every saved view with its centre, size and **both corners** |
| `autocad_export` | Publish | `area` is now `extents` (default), `layout`, `limits`, `display`, `window` or `view`, with `scale` |

---

## 3. Laying out a sheet

| Tool | Level | What it does |
|---|---|---|
| `autocad_create_layout` | Change | The sheet: layout, paper size, orientation, plotter, plot style table. Optionally copied from an existing layout. Returns the sheet's arithmetic — frame, drawing space, where the title block goes |
| `autocad_page_setup` | Change | AutoCAD's Page Setup on one sheet or `all_layouts`: plotter, paper, plot area, scale, `monochrome.ctb`, lineweights. Only what you pass is written |
| `autocad_place_title_block` | Change | The title block in the corner of one sheet or every sheet, with its attributes filled — including `per_layout_attributes` for sheet numbers |
| `autocad_add_viewport` | Change | A viewport at a real scale, looking where you say, twisted if the plan is on a slant, clipped to a shape if asked, with its annotation scale, and locked |
| `autocad_sheet_set` | Change | A whole drawing list (number, title, scale, view) made into sheets, viewports and filled title blocks in one call and one undo step ([§8](#8-a-whole-drawing-list-in-one-call)) |

### Made by the plug-in

`autocad_create_layout` and `autocad_add_viewport` are done by Heron's plug-in in .NET
([D-90](DECISIONS.md)): the layout and its page setup in one transaction, the viewport in the
layout's own block. Over COM both went through `doc.PaperSpace`, which threw on a sheet made with
`Layouts.Add`, and the page setup went busy part-way ([05 §23](05-known-limits.md#23-sheets-with-a-heavy-3d-xref-and-a-paper-space-that-will-not-answer)).
The arithmetic is still worked out here, and the plug-in is handed the numbers. With a plug-in older
than this the work is done over COM as before; every answer's `made_by` says which (`plugin` or
`com`). `copy_from` copies a sheet with everything on it when the plug-in does it; COM only copies
its page setup.

A new sheet gets no viewport of AutoCAD's own (LAYOUTCREATEVIEWPORT is off while it first opens):
the viewports are cut by `autocad_add_viewport`, at a real scale.

### Clipped viewports and annotation scale

`clip_outline=[[x, y], ...]` (corners on the paper) or `clip_handle` (a closed polyline, circle,
ellipse, spline or region already on that sheet) clips the viewport the way VPCLIP does; the
viewport takes the box round the outline as its place, so leave `paper_centre` / `paper_width` /
`paper_height` out. An outline is checked first: at least three corners, not crossing itself, with
an area. Clipping needs the plug-in; without it the call is refused and nothing is made.

`annotation_scale="match"` (the default) gives the viewport its own scale as its annotation scale,
adding it to the drawing's scale list if it is missing, so annotative text and dimensions inside
show at their paper size. Give a scale name to use another, or `"none"` to leave it.

### What makes the scale right

The model window handed to AutoCAD is worked out to the viewport's **own proportions**
([`acad/sheets.py`](../src/autocad_mcp/acad/sheets.py)): 180 x 120 mm of paper at 1:50 is exactly
9000 x 6000 drawing units. Nothing is added to make it fit, so 1:50 comes out 1:50. The scale is
then pinned with the viewport's `CustomScale`, because a zoom to a window can only ever land near a
round number.

Leave `scale` out and the **largest standard scale that fits** is chosen and reported — what a
draftsman does when the sheet size is fixed.

### A rotated plan on an upright sheet

`twist` turns the view inside the viewport: the picture turns anticlockwise by it on the sheet
(AutoCAD's view twist). So a wing drawn on a 23 degree grid reads square at `twist=-23` (or 337).
`align_to_ucs=true` works that out from the drawing's current UCS. The area AutoCAD is told to fit
is the upright box around the turned one, so nothing falls outside the frame. The sign is reasoned
from AutoCAD's display-coordinate rule, not yet measured (NEEDS-CHECKING AF6).

### Viewports lock by default

`locked=true` is the default. An unlocked viewport gets scrolled by the next person who zooms inside
it, and the scale printed on the title block stops being true. The lock is set **after** the view is
aimed, because AutoCAD refuses the zoom otherwise.

### Where the sheet's corners are

Paper-space `(0, 0)` is treated as the lower-left of the **printable area**, which is where AutoCAD
puts it for a layout plotted from its own origin. `anchor="paper"` measures from the sheet edge
instead. The frame defaults to **ISO 5457**: 20 mm on the binding (left) edge, 10 mm on the other
three, title block bottom-right. Every tool reports the rectangle it used, and `autocad_preview`
shows the result.

The paper size comes from the layout's own `GetPaperSize`; when a plotter is not configured it is read
out of the canonical media name, which carries the dimensions
(`ISO_full_bleed_A3_(420.00_x_297.00_MM)`).

---

## 4. Drawing settings, and styles

| Tool | Level | What it does |
|---|---|---|
| `autocad_drawing_setup` | Change | Units, precision, the drawing scale and everything that follows from it, object snaps, point style, linetype scaling, limits. `dry_run` shows the plan |
| `autocad_create_styles` | Change | Text, dimension, multileader and table styles with real values |

Give the scale once — `scale="1:50"` — and `DIMSCALE`, the annotation scale and `LTSCALE` follow.
`paper_text_height=2.5` with it sets `TEXTSIZE` to the model height (125 at 1:50).

**Why these are Change and not Admin.** `autocad_set_variable` is Admin because it will set *any*
system variable, which is an escape hatch. These two write only from a fixed list kept in
[`tools/settings.py`](../src/autocad_mcp/tools/settings.py) — drafting settings, and the `DIM`
variables behind a dimension style. They cannot save a file, run a command, or reach outside that
list ([D-28](DECISIONS.md)). Every call reports the old value beside the new one.

A dimension style is built the way AutoCAD's API requires: the `DIM` variables are set, the style is
added, the style copies them off the document, and the drawing's own variables are **put back**.
Multileader and table styles have no Automation API, so Heron's plug-in makes them
([D-104](DECISIONS.md)): a multileader style is Ajmal's TLD label unless asked otherwise, a table
style keeps its text in the vertical middle of each cell. A plot style table is a file the .NET API
cannot write ([D-105](DECISIONS.md)); `autocad_page_setup` sets one that exists.

---

## 5. An IFC or Revit export into a shop drawing

An export lands as geometry, not as a drawing: layers called `IfcWallStandardCase` or nothing but
layer 0; colour, linetype and lineweight set on every single object, so changing a layer appears to
do nothing; a real Z on work that should be flat, so trim and hatch misbehave.

| Tool | Level | What it does |
|---|---|---|
| `autocad_remap_layers` | Change | Puts everything on the right layer, and makes those layers with the colour, linetype, lineweight, description and plot setting they should have |
| `autocad_tidy_entities` | Change | Clears the per-object overrides, flattens to one level, moves geometry off layer 0, deletes the zero-length leftovers |
| `autocad_merge_layers` | Change | When an import came with three names for one layer: everything moves to the one, inside blocks too, and the empty old layers go. Needs `confirm=true` ([D-81](DECISIONS.md)) |

Once the layers are right, **save them as a layer state** (`autocad_layer_states(action="save")`),
so a coordination set-up or the issue set-up comes back in one call; `autocad_isolate_layers` hides
everything but one service while you work on it, and puts it all back after.

**Both default to `dry_run=true`.** Read the counts and `by_rule`, agree them, then run again with
`dry_run=false`.

A rule matches on any of `name_like` (the object's layer **or** its block name — an exporter puts the
element type in one or the other and you rarely know which), `source_layer`, `block_name`,
`entity_type`, `source_color`, `text_contains`. Wildcards work, and `/regex/` between slashes. The
first matching rule wins, so rule order is part of the rules.

> `color` is the **target layer's** colour. To match an object's own colour use `source_color`. A
> rule with nothing to match on is refused, because it would sweep the whole drawing onto one layer.

`preset="ifc"` is a **starting point, not a standard**: it maps the usual IFC and Revit class words
onto AIA-style discipline layers (`A-WALL`, `M-HVAC-DUCT`, `E-CABL-TRAY`, `S-BEAM`...). For an
office standard pass `rules`, or `rules_path` to a JSON file, and prove the result with
`autocad_check_standards`.

```
autocad_remap_layers(preset="ifc", unmatched_layer="X-REVIEW")              # look
autocad_remap_layers(preset="ifc", unmatched_layer="X-REVIEW", dry_run=false, set_bylayer=true)
autocad_tidy_entities(flatten_z=0, off_layer_0="X-REVIEW", dry_run=false)
autocad_check_standards(rules={"require_bylayer_color": true, "forbid_entities_on_layer_0": true})
```

---

## 6. `autocad_sequence`: AutoLISP's `progn`

Setting up a sheet is five calls that only make sense together. `autocad_sequence` takes the list,
**checks every step's arguments against that tool's own schema before the first one runs**, and
reports each step's own answer.

```
autocad_sequence(steps=[
  {"tool": "autocad_create_layout",     "args": {"name": "E-101", "paper_size": "A1"}},
  {"tool": "autocad_place_title_block", "args": {"block": "TTLB-A1", "attributes": {"DWG_NO": "E-101"}}},
  {"tool": "autocad_add_viewport",      "args": {"view_name": "GROUND-FLOOR", "scale": "1:100"}},
])
```

**It cannot raise what you are allowed to do.** The sequence is a Change tool, and it refuses any
step at the Publish or Admin level, and a sequence inside a sequence ([D-29](DECISIONS.md)). So it
can draw, modify and delete exactly as the **Changes** padlock already allows, and it can never save
a file, plot, run a command or evaluate AutoLISP along the way.

Each step keeps its own undo step, so Ctrl+Z backs them out one at a time. With **Ask to Keep** on,
Discard backs out the whole call.

For hundreds of entities use `autocad_batch_draw` instead — it is far faster.

---

## 7. A whole sheet, start to finish

```
autocad_status()                                              # units, and the UCS
autocad_drawing_setup(units="millimeters", scale="1:100", paper_text_height=2.5)
autocad_save_view(name="GROUND-FLOOR", handles=[...], pad=500)
autocad_sequence(steps=[
  {"tool": "autocad_create_layout",     "args": {"name": "A-101", "paper_size": "A1",
                                                 "plot_style_table": "monochrome.ctb",
                                                 "title_block_width": 180}},
  {"tool": "autocad_place_title_block", "args": {"block": "TTLB-A1", "layer": "G-TTLB",
                                                 "attributes": {"DWG_NO": "A-101", "SCALE": "1:100"}}},
  {"tool": "autocad_add_viewport",      "args": {"view_name": "GROUND-FLOOR", "scale": "1:100",
                                                 "title_block_width": 180, "gap": 2,
                                                 "layer": "G-VPRT"}},
])
autocad_preview()                                             # look before saying it is done
autocad_export(path="...A-101.pdf", area="layout", scale="1:1", paper_size="A1")
```

---

## 8. A whole drawing list in one call

`autocad_sheet_set` takes the drawing list a coordinator keeps and makes the sheets:

```
autocad_sheet_set(
  sheets=[
    {"number": "M-101", "title": "GROUND FLOOR HVAC", "scale": "1:100", "view": "GF-HVAC"},
    {"number": "M-102", "title": "FIRST FLOOR HVAC",                  "view": "FF-HVAC"},
    {"number": "M-001", "title": "COVER SHEET"},
  ],
  paper_size="A1", title_block="TTLB-A1", title_block_width=180,
  attributes={"PROJECT": "VILLA 12", "DATE": "2026-11-21", "REV": "P01"},
  viewport_layer="G-VPRT", title_block_layer="G-TTLB",
)
```

For each row: a layout named by the number, set up for plotting; a viewport at the row's scale on
its view, locked, with its annotation scale; the title block in the corner with `DWG_NO`, `TITLE` and
`SCALE` filled (the tags are `number_tag`, `title_tag`, `scale_tag`). A row without a scale gets the
largest standard scale that fits, and that scale goes in its title block. A row without a view gets
a sheet and title block only (a cover or a legend).

- **Checked first, all at once.** A number used twice or already a layout, a scale it cannot read, a
  saved view the drawing does not have, a title block it cannot find: every problem is said and
  nothing is made. `dry_run=true` shows the plan without making anything.
- **One undo step.** One Ctrl+Z, or Discard, takes the whole set back. If AutoCAD refuses a sheet
  part-way, the run stops and the answer lists the sheets made and why.
- **A template sheet.** `template_layout` copies an existing sheet for each new one, title block and
  all, keeping its own paper and plotter unless the call names them; the copy's title block is filled
  in rather than a second one placed.

Save the views first (`autocad_save_view`), then make the set, then `autocad_preview` a sheet, then
`autocad_publish_pdf` to issue them.

## 9. One PDF of many drawings

`autocad_publish_pdf(path=..., folder="D:\Job\Issue")` publishes every drawing in a folder into one
PDF (`recursive=true` for sub-folders), or `drawings=[...]` a list in the order given
([D-91](DECISIONS.md)). Drawings go in name order the way sheets are numbered (M-2 before M-10),
each with its sheets in tab order; `layouts` picks the same-named sheets from every drawing.

Every drawing is checked before anything is plotted: one open in AutoCAD with unsaved changes, or
one that attaches an xref whose file cannot be found, is refused by name, and nothing is published.
An unloaded xref is left as it is; an xref's own xrefs are checked too. Save, repath
(`autocad_manage_xref`) or unload, then publish again. A Heron plug-in older than this is refused
before anything is published (it would publish the open drawing instead).

