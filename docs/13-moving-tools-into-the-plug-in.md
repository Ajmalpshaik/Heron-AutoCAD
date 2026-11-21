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

Live checks: Group AS in [NEEDS-CHECKING](NEEDS-CHECKING.md), all NOT RUN.

## Ranked: what to move next

Ranked by gain first, then by how safe the move is. "Area" is the session area that owns the tool's
file today: a tool is moved only when no running session is changing it.

| Rank | Tool | Why it gains | What it risks | Area |
|---|---|---|---|---|
| 1 | `autocad_count_blocks` | Every block reference: real name, layer, and each dynamic property's name, value and read-only flag; with `include_nested`, every item of every block definition too. Easily the most trips per call of any take-off | Dynamic property values must come back the same type COM gives (distance, flip state, list choice), or the grouping by size splits | Blocks / take-off |
| 2 | `autocad_total_length` | Every curve: type, layer, length, closed, area, several trips each | Length of splines and ellipses must match the server's own calculation to the last digit | Take-off |
| 3 | `autocad_measure(layer=...)` | Same per-object loop as total length, over one layer | Same as rank 2 | Query (this area) |
| 4 | `autocad_count_text` / `autocad_find_text` | Every text and mtext: its contents, layer and position | Mtext contents with formatting codes must be cleaned the same way | Text |
| 5 | `autocad_extract_attributes` | Every block reference and every attribute on it | Attribute order and invisible or constant ones the same as COM | Blocks / standards |
| 6 | `autocad_check_standards` | Every layer and every object checked against the rules | The rules engine stays in Python; only the facts it reads move | Files and standards |
| 7 | `autocad_drawing_report` | A summary of the whole drawing, many collections | Wide answer, many shapes to keep equal | Drawing tools |
| 8 | `autocad_merge_layers` | Moves every object off old layers, inside blocks too: one transaction would make it all-or-nothing | A change: needs the Changes padlock checks and Keep or Discard to see every object | Layers |
| 9 | `autocad_list_layers` | Every layer, about eight properties each; drawings rarely have more than a few hundred layers, so the gain is small | Small | Layers |

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
