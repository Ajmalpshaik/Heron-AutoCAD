# src/autocad_mcp - the server

The MCP server. Installed as the `autocad-mcp` command (`pyproject.toml` -> `server:main`).

| Folder / file | Owns | Knows about |
|---|---|---|
| `server.py` | Command line: `--transport stdio/http`, `--host`, `--port`, `--list-tools`, `--read-only`, `--no-bridge`, `--run-saved` | everything below |
| `palette.py` | The Heron palette's Run (D-68): one saved command through the gate, and `server.json` so the palette finds the server | `tools`, `core` |
| `tools/` | The MCP tools, resources and prompts, one file per subject (`--list-tools` counts them) | MCP, `acad`, `core` |
| `acad/` | AutoCAD domain: entities, selections, tables, AutoLISP (and cutting long code between its forms, `lisp_forms.py`), units, the UCS transform, sheet arithmetic, the shape library, the 2D edit geometry | `core` only |
| `core/` | COM worker thread and its busy-call message filter, VARIANTs, errors, the FastMCP instance, undo groups, the Heron gate (`gate.py`, `bridge.py`, `risk.py`, `audit.py`), the plain first line (`answers.py`) and quiet answers (`quiet.py`), and where Heron keeps its files (`folders.py`) | pywin32 only |

**The one rule:** imports point down only, `tools` -> `acad` -> `core`.

| Tool file | Tools |
|---|---|
| `tools/document.py` | status, drawings, open, save, switch, export, zoom, variables |
| `tools/draw.py` | the 12 single-entity drawing tools |
| `tools/batch.py` | `autocad_batch_draw` |
| `tools/query.py` | list, get, selection, find text, extents, measure |
| `tools/modify.py` | move, copy, rotate, scale, mirror, offset, array, modify, delete |
| `tools/edit2d.py` | trim / extend, fillet / chamfer, break, join, vertices, stretch, explode, draw order, match properties, groups; the geometry is `acad/edit2d.py` (D-78, D-79) |
| `tools/layers.py` | layers, blocks, styles |
| `tools/layer_states.py` | layer states (by the plug-in), isolate and un-isolate, merge layers |
| `tools/advanced.py` | send command, run LISP, purge, regen, audit |
| `tools/explain.py` | `autocad_why` (why one job cannot run) and `autocad_gaps` (what failed and was slow, from the audit log): both need no AutoCAD (D-67) |
| `tools/standards.py` | standards check (rules, or a reference `.dws` / `.dwg` / `.dxf`, D-92), attribute extraction |
| `tools/files.py` | `autocad_read_file`: a DXF / DWG on disk with AutoCAD closed, read only; needs no AutoCAD (D-92). The reading is `acad/dxf_file.py`, the reference compare `acad/standard_compare.py` |
| `tools/checklist_share.py` | `autocad_share_checklist` (Publish): the office list into the office folder, a project's changes into its folder, never over a teammate's file silently (D-93) |
| `tools/coordinates.py` | the UCS: read it, set it, convert points through it |
| `tools/sheets.py` | layouts, page setup, title blocks, viewports |
| `tools/views.py` | saved views: one named location, plotted and viewported, or the 3D view on screen |
| `tools/settings.py` | drawing settings, text and dimension styles |
| `tools/convert.py` | an import into a shop drawing: remap layers, tidy overrides |
| `tools/sequence.py` | `autocad_sequence`: several tools in one call |
| `tools/shapes.py` | `autocad_make_shape`: 24 named shapes from their dimensions, and two 3D ones (duct run, pipe spool) |
| `acad/shapes3d.py` | The 3D shapes as pieces in their own frames with the matrix that places each: pure, tested offline (D-94) |
| `tools/_solid_pieces.py` | Makes those pieces as solids over COM and checks each landed where it should |
| `tools/dimensions.py` | dimension runs (chain, baseline, ordinate, a named style), centre marks |
| `tools/dimensions_edit.py` | dimensions already drawn: even spacing (DIMSPACE), breaks (DIMBREAK) |
| `tools/annotation_scales.py` | annotative objects and their annotation scales, done by the plug-in |
| `tools/drafting.py` | splines, multilines (MLINE), wipeouts |
| `tools/xrefs.py` | attach an xref; reload, unload, detach, bind; the xref tree with broken paths |
| `tools/patterns.py` | write custom hatch pattern (.pat) and linetype (.lin) files; the text is `acad/patterns.py` |
| `tools/annotate.py` | multileaders, tables, revision clouds |
| `tools/blocks.py` | `autocad_make_block` (with attribute definitions) and `autocad_sync_attributes` (ATTSYNC, by the plug-in) |
| `tools/tables.py` | an Excel range as a linked table, updating linked tables, changing cells of a table |
| `tools/between_drawings.py` | `autocad_copy_from_drawing`: objects from another open drawing into this one |
| `tools/solids.py` | 3D solids, extrude and revolve, booleans, mass properties, 3D views |
| `tools/solid_edits.py` | loft, fillet and chamfer solid edges, shell, press-pull, thicken, and the face and edge list: done by the plug-in (`run`, D-40) |
| `tools/solid_faces.py` | offset, taper, move and delete a solid's faces, imprint, separate: done by the plug-in (D-113) |
| `tools/primitives.py` | a pyramid and a polysolid (a wall along a path): done by the plug-in (D-112) |
| `tools/superhatch.py` | super hatch with a block, an image, an xref or a wipeout, done by the plug-in |
| `tools/sections.py` | flat views of solids (FLATSHOT) and a section plane with its 2D section: done by the plug-in (D-95) |
| `tools/surfaces.py` | planar and network surfaces, meshes: done by the plug-in (D-95) |
| `tools/materials.py` | list, make (done by the plug-in) and apply materials; render |
| `tools/lighting.py` | photometric lights, done by the plug-in |
| `tools/publish.py` | several sheets in one PDF, done by the plug-in's publisher |
| `tools/drawing_report.py` | one read of a whole received drawing: units, layers, blocks, xrefs, styles, sheets, counts |
| `tools/resources.py` | MCP resources and prompts |
| `tools/_shared.py` | option types and helpers shared by the tool files, including the UCS funnel and `in_plugin` (the way to the plug-in's own operations) |

After changing anything here: run the gates ([CONTRIBUTING](../../CONTRIBUTING.md)), then **restart the
server** - a running one keeps the old code. Never reinstall while it runs
([05 §1](../../docs/05-known-limits.md#1-reinstalling-while-the-server-runs)).

Design detail: [docs/02-architecture.md](../../docs/02-architecture.md).
