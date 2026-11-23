# 13 - Moving tools into the plug-in

**What this page owns:** which `autocad_*` tools would gain most from being done by Heron's plug-in
inside AutoCAD instead of over COM, what each move risks, and which session area each tool sits
in. The rule for moving one is [D-114](DECISIONS.md); the umbrella issue is
[#74](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/74).

## Why move a tool at all

Over COM, every property read is a round trip between two programs: the server asks, AutoCAD
answers. Reading one object's layer and type is two trips. A tool that looks at every object in a
big drawing makes tens of thousands of them. Inside AutoCAD the plug-in reads the same objects in
one go, then sends one answer back.

There are three kinds of gain:

| Gain | What it means for the modeller |
|---|---|
| **Fewer round trips** | A read over the whole drawing (counts, take-offs, checks) answers in a moment instead of a long wait |
| **Big drawings** | The COM wait grows with the drawing; the plug-in's grows far less |
| **One transaction** | A change to many objects either all lands or none of it does, so a failure half way never leaves a half-done drawing |

## The rules (D-114, in short)

1. **COM stays.** The tool keeps its COM path, used when the plug-in is older, not in the job, or
   cannot do it. Nothing that worked stops working.
2. **Same answer either way.** The plug-in sends raw facts (class names, layers, unrounded
   numbers); the server builds the answer from either path with the same code. Offline tests run
   the tool both ways over one fake drawing and compare the answers as text.
3. **One tool at a time**, each with its own issue and PR, and never a tool another session is
   changing.
4. **No general "read anything" request.** Each operation is on the plug-in's fixed list
   (`PluginOperations.cs`), at a level the padlocks check.

## Moved

| Tool | Plug-in operation | Before (COM) | Since |
|---|---|---|---|
| `autocad_list_entities(summary_only=true)` | `count_entities` | about three round trips per object in the drawing | plug-in 1.8.0, D-114 |
| `autocad_get_extents(layer=...)` | `entity_extents` | about two round trips per object on the layer | plug-in 1.8.0, D-114 |
| `autocad_drawing_report` (the model space count) | `count_entities` with `space: model` and the same 50,000 cut-off | two round trips per model space object | plug-in 1.8.0, [#193](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/193) |
| `autocad_count_blocks` | `block_references` (with `nested` for `include_nested`); each dynamic property value sent with its type | about 5 per block reference + 3 per dynamic property; with `include_nested`, 2-4 per item of every definition | the release after 1.8.1, [#192](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/192), [D-127](DECISIONS.md) |
| `autocad_list_blocks` | `block_definitions` (with `counts` for `include_counts`) | 2-3 per block reference, about 7 per definition, 2-3 per item inside every definition | the release after 1.8.1, [#194](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/194), [D-127](DECISIONS.md) |
| `autocad_total_length`, `autocad_measure(layer=...)` | `entity_lengths` (with `classes` for the curves `total_length` measures); a spline or an ellipse sent as its definition, measured by the server | about 7-10 per curve; splines and ellipses 4-5 more; `measure` 3-4 per object on the layer | the release after 1.8.1, [#195](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/195), [D-134](DECISIONS.md) |
| `autocad_count_text`, `autocad_find_text` | `entity_texts` (one filter per kind: text, mtext, block references); mtext with its formatting codes | 2 per text; 3 + 2 per attribute per block reference | the release after 1.8.1, [#197](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/197), [D-134](DECISIONS.md) |
| `autocad_extract_attributes`, `autocad_export_attribute_sheet`, the reads of `autocad_set_attributes` and `autocad_apply_attribute_sheet` | `block_attributes` (every block reference on the layer, the server skips and matches); the writes stay COM's, each changed block looked up by its handle | about 7-9 + 2 per attribute, per block reference | the release after 1.8.1, [#198](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/198), [D-138](DECISIONS.md) |
| `autocad_check_standards` (the entity rules) | `entity_properties` (one past `max_entities`; a box only for dimensions, only for the overlap rule); the rules stay in Python, the layers and the reference COM's | 5 per object up to 20,000 (3 now over COM for a layer-0 check), +1 per dimension for the overlap rule | the release after 1.8.1, [#196](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/196), [D-145](DECISIONS.md) |
| `autocad_merge_layers` | `layer_objects` (the objects on the old layers, in the COM read's order), then `merge_layers`: the planned objects moved and the empty old layers purged in **one transaction**, all or none | 2-3 per item of every block definition, 2-3 per attribute, then one write per moved object; a failure half way left part moved | the release after 1.8.1, [#199](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/199), [D-147](DECISIONS.md) |

Live checks: Groups AS, AU, BB, BE, BI and BJ in [NEEDS-CHECKING](NEEDS-CHECKING.md), all NOT RUN.

## Ranked: what to move next

Ranked by gain first, then by how safe the move is. Round trips are counted from the code (an
`Item` call, each property read, each failed try), not timed: the live row of each move times it.
"Area" is the session area that owns the tool's file today: a tool is moved only when no running
session is changing it.

| Rank (issue) | Tool | COM round trips today | What it risks | Area |
|---|---|---|---|---|
| 1 ([#192](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/192)) | ~~`autocad_count_blocks`~~ **moved**, see above | | | |
| 2 ([#193](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/193)) | ~~`autocad_drawing_report`~~ **moved**, see above | | | |
| 3 ([#194](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/194)) | ~~`autocad_list_blocks`~~ **moved**, see above | | | |
| 4 ([#195](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/195)) | ~~`autocad_total_length`, `autocad_measure(layer=...)`~~ **moved**, see above | | | |
| 5 ([#196](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/196)) | ~~`autocad_check_standards` (entity rules)~~ **moved**, see above | | | |
| 6 ([#197](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/197)) | ~~`autocad_count_text`, `autocad_find_text`~~ **moved**, see above | | | |
| 7 ([#198](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/198)) | ~~`autocad_extract_attributes`, `autocad_export_attribute_sheet` and the read half of `autocad_set_attributes` / `autocad_apply_attribute_sheet`~~ **moved**, see above | | | |
| 8 ([#199](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/199)) | ~~`autocad_merge_layers`~~ **moved**, see above | | | |
| 9 ([#200](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/200)) | `autocad_apply_attribute_sheet`, `autocad_set_attributes` (the writes) | 3 + one per attribute per changed cell, up to 10,000 changes | A **change**: one transaction, so a failure half way leaves nothing half-written | Blocks and attributes |

Not ranked, because the gain is small: `autocad_list_layers` (9 per layer; drawings rarely have
more than a few hundred), `autocad_list_styles`, `autocad_xref_tree`, and the single-object draw
and modify tools.

Already in the plug-in for another reason ([D-40](DECISIONS.md)): solid edges and faces, super
hatch, layer states, annotation scales, dimension line spacing, ATTSYNC, Excel tables, lights,
camera views. Multileader, table and plot style creation is tracked as its own issue
([#68](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/68)), in the styles area.

## Not worth moving

| Tool | Why not |
|---|---|
| `autocad_get_extents` for the whole drawing | Already three COM calls (EXTMIN, EXTMAX after a regen) |
| `autocad_list_entities` per-object listing | Paged at 500; the per-type detail (`describe`) is large and would have to match field for field |
| `autocad_batch_draw` | Already one AutoLISP round trip for the whole batch ([02](02-architecture.md)) |
| Single-object draw and modify tools | One object, a few trips: nothing to save |

Each further move has its own issue, linked from [#74](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/74).
