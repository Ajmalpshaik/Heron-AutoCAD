# 10 - Complex geometry, annotation and 3D

Three things that turn a drawing tool into a drafting tool: **a shape from a
few numbers**, **annotation that a drawing office would accept**, and **a 3D
model you can build and then look at**. Decisions: [D-30](DECISIONS.md),
[D-31](DECISIONS.md). Live checks: [NEEDS-CHECKING group E](NEEDS-CHECKING.md).

---

## 1. Simple words, complex geometry

> "A 200 flange, 8 holes on a 160 PCD." "A slot 120 long, 40 wide." "The flat
> pattern for that 200 to 100 reducer." "A 1200 wide stair, 14 risers at 175."

Each of those is a page of construction geometry by hand, and one call here:

```
autocad_make_shape(shape="flange",
                   settings={"outer_diameter": 200, "bolt_count": 8,
                             "pitch_diameter": 160, "hole_diameter": 18, "bore": 100},
                   layer="M-PIPE", centreline_layer="M-PIPE-CNTR")
```

| | Shapes |
|---|---|
| **Plain** | polygon, hexagon (sized across flats, as a spanner reads it), star, slot, rounded_rectangle, spiral, zigzag |
| **Fabrication** | flange, bolt_circle, steel_section (i / h / c / l / t / shs / rhs / chs), gear, **cone_development** - the flat pattern for a reducer |
| **MEP** | elbow (with its centreline), duct_transition, grating |
| **Building** | stair (section or plan), ladder, truss |
| **Furniture** | detail_bubble, section_mark, north_arrow, scale_bar, level_mark, revision_tag |

**How it works, and why it is built this way.** Every shape is a pure function
in [`acad/shapes.py`](../src/autocad_mcp/acad/shapes.py) that returns a list of
operations in exactly the shape `autocad_batch_draw` takes. So the geometry is
tested without AutoCAD, and it is drawn down the one path that is already fast,
already one undo step, and already UCS-aware ([D-30](DECISIONS.md)).

**Arcs stay arcs.** A slot, a rounded corner, an elbow and a flat pattern all
come out as **one polyline with bulges**, not a pile of loose arcs — so they
select, offset and plot as the single object they are. Adding bulges to the
batch is what made that possible.

**`dry_run=true`** hands back the operations instead of drawing them, so you can
look first, or change something and send them yourself.

**Your office block beats all of this.** The furniture shapes exist for the
drawing with no block library to hand; when you have one,
`autocad_insert_block` carries your own line weights and attributes.

### The flat pattern, as a worked example

A frustum rolls out as a ring sector. With a slant length L and radii R1
(bottom) and R2 (top), the sector runs from `L*R2/(R1-R2)` out to
`L*R1/(R1-R2)` and subtends `2*pi*(R1-R2)/L`. The test that matters is not that
the code agrees with itself but that **the arcs are exactly as long as the
girths they have to wrap round**, and that is what `tests/test_shapes.py`
checks, on four different reducers.

A piece so shallow that it opens past about 350 degrees is refused: one
polyline bulge is `tan(sweep/4)`, which has already run away to 33 at 353
degrees. Such a piece is nearer a flat ring than a cone.

---

## 2. Dimensioning a run, not a dimension

`autocad_add_dimension` does one dimension, which is right for one dimension.
A drawing wants a **run**:

```
autocad_dimension_run(points=[[0,0],[3000,0],[7500,0],[12000,0]],
                      mode="chain", axis="horizontal",
                      offset=500, include_overall=true)
```

| Tool | Level | What it does |
|---|---|---|
| `autocad_dimension_run` | Change | A whole run at once: `chain` (AutoCAD's Continue), `baseline` (each back to the first, stepped clear of each other), `overall`, or `ordinate` from a datum. Horizontal, vertical or aligned |
| `autocad_add_centre_marks` | Change | The cross a drawing office expects on every circle and arc, by handle or by layer; `extend` turns it into full centre lines |
| `autocad_add_dimension` | Change | Still there for one dimension: aligned, horizontal, vertical, radial, diametric, angular |
| `autocad_space_dimensions` | Change | DIMSPACE on dimensions already there: a stack moved to an even spacing off a base dimension, or lined up (spacing 0) |
| `autocad_break_dimensions` | Change | DIMBREAK, automatic: a gap wherever another object crosses a dimension; `remove` takes it off |

The points are **put in order along the run** first, which is what a drafter
does without thinking. A baseline set steps each dimension line clear of the
last. An overall goes on a line beyond the rest.

**It checks its own arithmetic.** Every dimension's span is worked out here as
well as measured by AutoCAD, and both numbers come back. When they disagree —
a UCS, an elevation difference — the reply says so, instead of a drawing that
quietly does not add up.

There is no Automation call for a centre mark, so those are drawn as lines.
That is a feature: they land on the layer you ask for and plot the way that
layer does.

**A detail at another scale takes its own style.** `dim_style="DIM-1-5"` draws
the run in that style at the style's own scale. The style is set on each
dimension; the drawing's current style and DIMSCALE are never touched, because
making a style current and putting the old one back wipes the DIMSCALE that
`autocad_drawing_setup` left on it ([D-80](DECISIONS.md), issue #37).

**Spacing a stack that is already drawn.** COM cannot move a rotated
dimension's line without moving its extension line origins too, so the
plug-in reads where each dimension line is and moves it; Heron works out the
spacing. The base stays put; every other dimension keeps its side of it and
its order out from it. A dimension break has no API call at all, so DIMBREAK
is typed, each dimension picked by its handle ([D-80](DECISIONS.md)).

---

## 3. Annotation that needs more than one object

| Tool | Level | What it does |
|---|---|---|
| `autocad_add_multileader` | Change | One note, **as many arrows as it needs** — "4 No. M16 BOLTS" with an arrow to each hole. Text or a block as its content |
| `autocad_add_table` | Change | A schedule as a real AutoCAD table, with a title and headings, not a grid of loose text. Pairs with `autocad_extract_attributes` |
| `autocad_add_revision_cloud` | Change | A cloud round a boundary, a rectangle, or **round an object's own extents** — which is what a revision usually means |

The cloud is the same object AutoCAD's own REVCLOUD makes: one polyline with
bulges. Its arcs come out an even size because the spacing is adjusted to
divide the boundary exactly, so the last arc is never a stub, and the bulge is
**signed from the direction the boundary is traced** so the arcs always bulge
outward. Its rise is a quarter of its chord, which is what REVCLOUD looks like.

**Annotative.** `annotative=true` on `autocad_add_text`, `autocad_add_mtext`,
`autocad_add_dimension`, `autocad_dimension_run` and `autocad_add_multileader`
makes the new object annotative at the drawing's current annotation scale;
`autocad_annotation_scales` adds and removes scales on objects already there,
and `autocad_list_annotation_scales` reads them. Only .NET reaches an object's
scales, so the plug-in does it ([D-81](DECISIONS.md)). Sizes stay in drawing
units at the current scale (125 for 2.5 mm at 1:50); the reply gives the paper
height to check against.

Multileader styles and table styles have **no Automation call to create them**.
Make them in AutoCAD, or bring yours in with `autocad_import_from_drawing`;
both tools name the style plainly when the drawing has not got it.

---

## 4. 3D

| Tool | Level | What it does |
|---|---|---|
| `autocad_add_solid` | Change | box, wedge, cylinder, cone, sphere, torus — **placed by the centre of its base** |
| `autocad_extrude_profile` | Change | A closed 2D profile into a solid: extrude along Z with an optional taper, or revolve about an axis |
| `autocad_solid_boolean` | Change | union, subtract, intersect. A plate with holes is a box minus some cylinders |
| `autocad_solid_properties` | Read | Volume, centroid, bounding box, moments — what a weight take-off and a lifting plan need |
| `autocad_draw_3d_path` | Change | A pipe or cable route as one 3D polyline, or a helix from its radius, turns and rise |
| `autocad_set_3d_view` | **View** | Look from a named direction (top, front, sw_iso …) in a chosen visual style |

**Placement.** AutoCAD's own primitive calls place a solid by the centre of its
**bounding box**, which is halfway up it. That is never where a drafter means,
so these tools take the **base centre** and work the rest out: a 300 high
cylinder at z=0 sits on z=0. Both points come back in the reply.

**Booleans consume.** The first solid stays and is modified; the others are
removed by AutoCAD, exactly as its own UNION, SUBTRACT and INTERSECT behave.
Every handle is checked to be a solid or a region **before anything is
touched**, so a bad handle halfway through cannot leave a mess. The volume
before and after is reported, so a subtract that removed nothing shows itself.

**Scaffolding is cleaned up.** `autocad_extrude_profile` has to make a region
first (AutoCAD's own step). That region was the server's idea, not yours, so it
is removed afterwards; your original curves stay unless you say otherwise,
because they are usually still the 2D section you want on the drawing.

**Looking at it is a View tool.** `autocad_set_3d_view` changes the view
direction and the visual style and nothing else — no object moves — so it sits
at the same level as `autocad_zoom` and needs no padlock
([D-31](DECISIONS.md)). A south-west isometric in the `hidden` style reads like
a shop drawing; `plan` plus `2dwireframe` is back to normal drafting.

```
autocad_set_3d_view(direction="sw_iso", visual_style="hidden")
autocad_preview()                        # now the picture is worth having
```

---

## 5. A worked example: a bracket, dimensioned and issued

```
autocad_status()                                      # units, and the UCS
autocad_make_shape(shape="rounded_rectangle",
                   settings={"width": 200, "height": 120, "radius": 15},
                   layer="S-FRAM")                    # the outline, one object
autocad_make_shape(shape="bolt_circle",
                   settings={"count": 4, "pitch_diameter": 140,
                             "hole_diameter": 14, "origin": [100, 60]},
                   layer="S-FRAM")
autocad_add_centre_marks(layer_filter="S-FRAM", extend=5, layer="G-ANNO-CNTR")
autocad_dimension_run(points=[[0,0],[30,0],[170,0],[200,0]],
                      mode="chain", offset=-40, include_overall=true,
                      layer="G-ANNO-DIMS")
autocad_add_multileader(landing=[260, 100], arrows=[[30,60],[170,60]],
                        text="4 No. 14 DIA HOLES", layer="G-ANNO-TEXT")
autocad_extrude_profile(handles=["<the outline>"], height=12)   # now in 3D
autocad_solid_boolean(operation="subtract", handle="<the solid>",
                      others=["<the hole solids>"])
autocad_solid_properties(handles=["<the solid>"])     # volume for the weight
autocad_set_3d_view(direction="sw_iso", visual_style="hidden")
autocad_preview()
```
