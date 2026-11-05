# src/autocad_mcp - the server

The MCP server. Installed as the `autocad-mcp` command (`pyproject.toml` -> `server:main`).

| Folder / file | Owns | Knows about |
|---|---|---|
| `server.py` | Command line: `--transport stdio/http`, `--host`, `--port`, `--list-tools`, `--read-only`, `--no-bridge` | everything below |
| `tools/` | The MCP tools, resources and prompts, one file per subject (`--list-tools` counts them) | MCP, `acad`, `core` |
| `acad/` | AutoCAD domain: entities, selections, tables, AutoLISP, units, the UCS transform, sheet arithmetic, the shape library | `core` only |
| `core/` | COM worker thread, VARIANTs, errors, the FastMCP instance, undo groups, and the Heron gate (`gate.py`, `bridge.py`, `risk.py`, `audit.py`) | pywin32 only |

**The one rule:** imports point down only, `tools` -> `acad` -> `core`.

| Tool file | Tools |
|---|---|
| `tools/document.py` | status, drawings, open, save, switch, export, zoom, variables |
| `tools/draw.py` | the 12 single-entity drawing tools |
| `tools/batch.py` | `autocad_batch_draw` |
| `tools/query.py` | list, get, selection, find text, extents, measure |
| `tools/modify.py` | move, copy, rotate, scale, mirror, offset, array, modify, delete |
| `tools/layers.py` | layers, blocks, styles |
| `tools/advanced.py` | send command, run LISP, purge, regen, audit |
| `tools/standards.py` | standards check, attribute extraction |
| `tools/coordinates.py` | the UCS: read it, set it, convert points through it |
| `tools/sheets.py` | layouts, page setup, title blocks, viewports |
| `tools/views.py` | saved views: one named location, plotted and viewported, or the 3D view on screen |
| `tools/settings.py` | drawing settings, text and dimension styles |
| `tools/convert.py` | an import into a shop drawing: remap layers, tidy overrides |
| `tools/sequence.py` | `autocad_sequence`: several tools in one call |
| `tools/shapes.py` | `autocad_make_shape`: 24 named shapes from their dimensions |
| `tools/dimensions.py` | dimension runs (chain, baseline, ordinate), centre marks |
| `tools/drafting.py` | splines, multilines (MLINE), wipeouts |
| `tools/xrefs.py` | attach an xref; reload, unload, detach, bind; the xref tree with broken paths |
| `tools/patterns.py` | write custom hatch pattern (.pat) and linetype (.lin) files; the text is `acad/patterns.py` |
| `tools/annotate.py` | multileaders, tables, revision clouds |
| `tools/solids.py` | 3D solids, extrude and revolve, booleans, mass properties, 3D views |
| `tools/solid_edits.py` | loft, fillet and chamfer solid edges, shell, press-pull, thicken, and the face and edge list: done by the plug-in (`run`, D-40) |
| `tools/superhatch.py` | super hatch with a block, done by the plug-in |
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
