# Session handover

> **What this file is:** where the last session stopped and what comes next. It is a work note. Where
> it disagrees with the code, the tests, [NEEDS-CHECKING](NEEDS-CHECKING.md) or
> [DECISIONS.md](DECISIONS.md), those win.

## If you are the owner, starting work - say this

> **"Read docs/HANDOVER.md in Heron-AutoCAD and carry on."**

## Latest - 2026-11-22 (the first release prepared; session 2 of 3)

**State today:** plug-in **1.8.0** (bumped from 1.7.0: the tag must equal it, and the server asks for
1.8.0 for the faster reads), server **1.10.1**, **199** tools. New: [INSTALL](INSTALL.md) (for a
modeller), [TOOL-CATALOGUE](TOOL-CATALOGUE.md) (made by `tools/make_tool_catalogue.py`; a test fails
when it is stale: run the script after adding a tool, changing a docstring or a NEEDS-CHECKING row),
the CHANGELOG release section, README / SETUP corrected. One bug fixed: the update check could not
see a pre-release. The first pre-release **v1.8.0** is built by `release.yml` from the merged
commit; the release page, its assets and their SHA-256 are the truth for what was published.
Nothing was run in AutoCAD: every live row stays NOT RUN, signing stays off (#164).

## Earlier - 2026-11-22 (tidy-up before the first release; session 1 of 3)

**State today:** `main` has **no open pull requests**. Server **1.10.1**, plug-in **1.7.0**, **199**
tools. Nothing has been proved live: every live row stays NOT RUN until the owner runs AutoCAD, and
no GitHub release or tag exists yet (the next session prepares the first). All branches that were
merged are deleted, here and on GitHub; only `main` and the long-lived feature branch remain.
Housekeeping done: the second doc numbered 13 is now [15](15-sheets-folders-companion.md);
`tools/check_structure.py` now also fails on two docs with one number, a script missing from
`tools/README.md`, or a script `PROJECT-MAP.md` names that does not exist; ROADMAP ticks the
items whose issues are closed (palettes, dialog watch, "why can't you", ribbon audit, installer;
signing is NOT PLANNED by the owner's choice, #164).

**Waiting for the owner:** #70 (his layer list, rows AT1-AT8), #213 (decide V1/V4/V7), #75 (waits
for Heron AI's registry). **Waiting for a live AutoCAD check:** #39, #40, #41, #80 and every
group of rows in [NEEDS-CHECKING](NEEDS-CHECKING.md). **Next work:** the plug-in moves #192-#200
(ranks of #74), and the follow-ups #189, #190, #206-#210, #185, #212, #216, #218, #222.

## Earlier - 2026-11-22 (the office layer standard, #70, D-120)

`autocad_layer_standard` (new, **199** tools, with the other sessions' work): `template` / `import` / `show` / `remove` for the
office's own layer list as a CSV, kept in `%LOCALAPPDATA%\Heron\autocad\standards\`; `layer_standard`
on `autocad_check_standards` and `autocad_remap_layers` (`office`, `example` or a file path). The
format and the check are `acad/layer_standard.py`; the generic MEP example is
`src/autocad_mcp/data/layer-standard-example-mep.csv`. Tests: `tests/test_layer_standard.py`.
**Next (Ajmal, on this PC):** `autocad_layer_standard(action="template")`, fill the CSV from the
office list, `action="import"`, then live rows **AT1-AT8**. #70 closes when he confirms it matches
his standard.

## Earlier - 2026-11-22 (Heron AI's AutoCAD side: the capability manifest, #75, D-122)

`tools/export_capabilities.py` writes `dist/capabilities.json` from the code: each tool's padlock,
`Use when` lines, inputs, what it needs of the plug-in and its NEEDS-CHECKING proof state. Every
release zip carries it. What Heron AI would need and the steps when its registry is ready:
[14](14-heron-ai-adapter.md). Heron AI itself was not touched. Tests:
`tests/test_export_capabilities.py`. **Next:** nothing on this PC; #75 stays open until Heron AI's
registry is built. When a live row is next run, name its tool in backticks so the manifest counts it.

## Earlier - 2026-11-21 (pyramid, polysolid, solid face edits: #182, #183, #184; D-112, D-113)

Part 3 of #119, branch `claude/solid-edits`. Five new tools done by the plug-in (**198** in all):
`autocad_add_pyramid`, `autocad_add_polysolid`, `autocad_edit_solid_faces` (offset, taper, move,
delete), `autocad_imprint_solid`, `autocad_separate_solid`. Plug-in: `SolidPrimitives.cs` and
`SolidFaceEdits.cs`, eight new operations; pure maths in `Bridge/SolidShapeMath.cs`. Every .NET
call was checked in the AutoCAD.NET package's own reference file, and the add-in compiles for all
three builds. Faces are picked from the Brep built from the solid's own path, as the D-40 fix
found. The pyramid reads back the corners AutoCAD made and turns itself so a side faces the front;
the polysolid is built (offset path, region, extrude) because the API has none. Limits:
[05 §19](05-known-limits.md#19-the-plug-in-operations-3d-edits-super-hatch-have-their-own-limits).
None of it has run in AutoCAD. Versions not bumped (the parent does).

**Next (on this PC):** pull, build and install the plug-in, restart Claude, then live rows AR1-AR13
([NEEDS-CHECKING group AR](NEEDS-CHECKING.md)). The answers the reference could not give: whether
AutoCAD reads the pyramid's radius as its reference says (`remade_to_size`, AR1), and which way a
positive taper leans (AR9).

## Earlier - 2026-11-21 (sheets by the plug-in: #64-#67, #39, #40; D-90, D-91)

One new tool, `autocad_sheet_set` (**193** with the other sessions' work), and three new
plug-in operations (`create_layout`, `add_viewport`, `active_sheet`); `publish_pdf` takes a list
of drawings. `autocad_create_layout` and `autocad_add_viewport` ask the plug-in first and fall back
to COM; viewports clip (`clip_outline`, `clip_handle`) and take an annotation scale; title blocks go
into the layout's own block; `autocad_status` no longer fails on a sheet tab; `autocad_publish_pdf`
takes `folder` / `drawings`. Compiled for all three builds and checked offline only; the plug-in
version is not bumped here (the parent does it). #39 and #40 stay open until their live rows run.

**Next (on this PC, AutoCAD closed):** pull, build and install the plug-in, restart Claude, then live
rows **AF1-AF15, AF17, AF18**. AF9 decides whether the sheet set really is one undo step; AF6 checks the twist sign,
which this PR flipped from the code (the old COM path too); AF10 is row D33 again.

## Earlier - 2026-11-22 (the drawing report's count by the plug-in, #193, rank 2 of #74)

`autocad_drawing_report` counts model space through `count_entities` with `space: model` and the
same 50,000 cut-off; the plug-in walks model space in COM's order and says `"space": "model"`, so a
plug-in built before this (which would count the whole drawing) is not believed and COM counts
instead. Tests: `tests/test_plugin_reads.py::TestDrawingReportCount`, `EntityReadsTests.cs`.
**Next (on this PC):** live rows AS10 and AS11 with AS1-AS9. Next move: rank 1, #192 (count_blocks).

## Earlier - 2026-11-21 (the drawing tools: #50, #51, #52, #55, #56; D-96, D-97)

One new tool (**192** in all, with the other sessions' tools): `autocad_edit_spline`. `coords="ucs"` on the single-entity draw and
modify tools; `mtext`, `hatch` (solid) and `dimension` (linear) in `autocad_batch_draw`; `filled=true`
on four symbol shapes; `autocad_break_at_blocks` cuts arcs; `autocad_draw_multiline(closed=true)`
mitres its last corner; `autocad_draw_spline(method="control_points")`. Three new plug-in
operations (`close_multiline`, `add_cv_spline`, `edit_spline_fit_points`), checked against
Autodesk's reference assemblies and compiled for all three builds; the plug-in version is not
bumped here (the parent does it).

**Next (on this PC, AutoCAD closed):** pull, build and install the plug-in, restart Claude, then
live rows **AI1-AI14**. AI4 decides whether an entmade solid hatch lands (if it does, `filled` could
become the default on the symbol shapes); AI11 says how AutoCAD shows a closed control-point
spline; AI12 says whether `insert` at the count adds after the last fit point.

## Earlier - 2026-11-21 (one-file setup #73, tests import their own src #35, signing prepared #72; D-99)

`tools/make_installer.py` + `tools/installer/HeronAutoCAD.iss` (Inno Setup 6.7.3, pinned) build
`HeronAutoCAD-<version>-setup.exe` in `release.yml`, after the zip, and `tools/installer/Check-Setup.ps1`
installs and removes it on GitHub's Windows machine before anything is published (no AutoCAD
there). Per user, same places as `Install.bat`, refuses while AutoCAD runs, Claude set up by
`Install.ps1 -Connect` / `-Disconnect`. Signing (`tools/signing.py`) runs only with the secrets
`HERON_SIGN_PFX_BASE64` + `HERON_SIGN_PFX_PASSWORD`; none exist, and Ajmal decided not to buy a
certificate (#164; #72 closed not planned), so releases say *Not signed*.
pytest now has `pythonpath = ["src"]`. Versions not bumped (the parent does).

**Next (on this PC):** run Group **AK**. AK10-AK11 record what AutoCAD asks the first time it loads
the unsigned plug-in, and that it asks only once. Keep the zip until AK1-AK8 pass.

## Earlier - 2026-11-21 (tools into the plug-in where it pays off: #74, D-114)

The first two reads moved into the plug-in for speed, with COM kept as the fallback:
`autocad_list_entities(summary_only=true)` (`count_entities`) and `autocad_get_extents(layer=...)`
(`entity_extents`). Same filter, same answer either way (`tests/test_plugin_reads.py` runs each
tool both ways over one fake drawing and compares the text; `EntityReadsTests.cs` for the plug-in
side). The server uses them only with plug-in **1.8.0** or newer (`READS_SINCE` in `core/bridge.py`;
a test fails if the version is bumped to anything between 1.7.0 and that). No new tool, no version
bump. The ranking of what to move next, with each tool's session area:
[13 - Moving tools into the plug-in](13-moving-tools-into-the-plug-in.md); one issue per tool,
linked from #74, which stays open as the umbrella.

**Next (on this PC):** rebuild and reinstall the plug-in, restart AutoCAD and Claude, then live rows
AS1-AS9 against a real project drawing. AS3 is the one that says whether it was worth it: write
both times in the result.

## Earlier - 2026-11-21 (PDF Import, #113, D-106)

One new Change tool, `autocad_import_pdf` (**191** in all, with the other sessions' work): one page of a PDF as lines, text and
hatches, at a point, scale and rotation, on one layer, with a report of what came in. No API exists
(COM or .NET), so it types `-PDFIMPORT` with every answer in one AutoLISP form, through the sender
`autocad_run_lisp` uses (now `advanced.send_lisp_pieces`): snaps off, a command still asking is
cancelled and named, one undo step. It checks the release (2021-2027), the file and the page count
first, and puts back every variable it sets. Server only, no plug-in change. Offline tests:
`tests/test_pdf_import.py`. Limits: [05 §36](05-known-limits.md#36-pdf-import-has-its-own-limits).

**Next (on this PC):** pull, restart Claude (server only), then live rows AO1-AO9. **AO1 first**:
type `-PDFIMPORT` by hand on a two-page and a one-page PDF and write the prompts down. The six
questions were read from Autodesk's help through a search only, and whether a one-page PDF still
asks for the page is not known; if it differs, the fix is `command_form` in `acad/pdf_import.py`.
AO9 says what scale 1 means, so the help can say it plainly.

## Earlier - 2026-11-21 (overkill, boundary, eTransmit, underlays and clips: #112, #104, #118, #114)

Five new tools, built and tested offline only: `autocad_overkill` (geometry in `acad/overkill.py`),
`autocad_trace_boundary` (plug-in `trace_boundary`, `Editor.TraceBoundary`, never the typed
command), `autocad_etransmit` (Publish; plug-in `list_dependencies`, packing in
`acad/transmittal.py`), `autocad_attach_underlay` and `autocad_clip_reference` (plug-in
`attach_underlay`, `clip_reference`; images over COM). The plug-in builds for net48, net8 and net10
here, but nothing has run in AutoCAD: rows AD1-AD12, all NOT RUN. Versions not bumped (the parent
does): the plug-in parts need the release after 1.7.0. D-84, D-85; known limits §35. The ribbon
coverage page (docs/12) now lists Boundary and Overkill as built (NOT RUN live).

## Earlier - 2026-11-21 (a sequence stops at a drawing switch, #165; D-98)

Follow-up to #48 on branch `claude/plugin-events-165`. Plug-in change: `begin` answers
`drawingSeq`. `autocad_sequence` checks between steps (`gate.front_changed_in_job`) and stops
when another drawing came to the front. Tested offline; live row AJ8 NOT RUN. Versions not bumped.

## Earlier - 2026-11-21 (the live-check runner covers the new groups, D-118)

`tools/live_check.py` now measures 198 rows (132 new, in groups M-Z, AA-AP, RV) and names the
reason for the other 201 of its groups. One file per area: `live_check_edits.py` (AA),
`live_check_layers.py` (AB), `live_check_blocks.py` (AC, Y), `live_check_render.py` (AE),
`live_check_drawing.py` (AP, AM), `live_check_mep3d.py` (AH), `live_check_styles.py` (AN, AL), `live_check_ribbon2.py` (AQ), `live_check_cleanup.py` (AD), `live_check_reads.py` (AS, AO), `live_check_heron.py` (M-Z, AG, AJ, RV), sharing `live_common.py`. Offline, `tests/live_fakes.py` plays a good and
a bad recorded answer into each check. Nothing has run in AutoCAD: every row is still NOT RUN.

**Next (on this PC):** pull, restart Claude, press Heron, turn Changes on in Settings (Ask to Keep
off), close every chat using this AutoCAD, then `tools/live_check.py --group all --write`. Then once
more with Admin and Publish on for the rows `--list` marks `[needs ...]`. Open: #213 (V1, V4, V7 need
rewriting). A new group added to NEEDS-CHECKING makes `tests/test_live_check.py` name it until its
rows are a check or a reason.
## Earlier - 2026-11-21 (the smaller ribbon gaps, part 2 of #119, D-110, D-111)

Six new tools (**185** in all), split from #119 into #175, #176, #178, #179, #180:
`autocad_associative_array` (path, grid, ring; plug-in), `autocad_tiled_viewports` (COM, View),
`autocad_hyperlinks` / `autocad_list_hyperlinks` (COM), `autocad_geo_location` /
`autocad_get_geo_location` (plug-in), and DWF in `autocad_export`. The .NET names come from
Autodesk's reference DLLs and the viewport split numbers from Autodesk's interop DLL; what an
array's base point and angles mean, and the form of a geo location's reference point, could not be
read here, so the plug-in checks AutoCAD's result and refuses a wrong one (D-110, D-111).

**Next (on this PC):** build and install the plug-in, restart Claude, then live rows AQ1-AQ13.
AQ4 (ring angles in degrees? centre?), AQ6 (which split is "vertical"), AQ11 (`reference_form`:
grid or lon_lat) are the answers the code could not get. Not built (#216): turned grids, DWFx,
projected coordinate systems in feet.

## Earlier - 2026-11-21 (multileader and table styles by the plug-in, #68, D-104 and D-105)

Branch `claude/styles-plugin`. `autocad_create_styles` takes `multileader_styles` and
`table_styles`; the plug-in makes them (operations `multileader_style`, `table_style`). The
rules (words, defaults, refusals) are in `Heron.AutoCAD.Bridge/StylePlans.cs` with
`StylePlansTests.cs`; the add-in's `DrawingStyles.cs` only copies the plan and reads it back. Server
side: `tests/test_create_styles_plugin.py`. A plot style table cannot be made (D-105, 05 §34). No
new tool, so the tool count is unchanged. The add-in compiled here against the 2021, 2025 and 2027
reference assemblies; nothing ran in AutoCAD.

**Next (on this PC):** pull, rebuild and reinstall the plug-in, restart AutoCAD and Claude, then
rows AN1-AN12. AN1 and AN3 answer what the reference could not: whether the dialog shows the
attachment and the landing switch as set, and whether the DIMBLK round trip for a new arrow leaves
no style override. AN4 says whether one Ctrl+Z takes it all back.

## Earlier - 2026-11-21 (review of the 2026-11-21 merges, PR #186, D-116)

A review of PRs #99 onward. Fixed on PR #186: stale padlock / auto-connect wording (README,
SECURITY, PROJECT-MAP, 06), D-87 and D-67 notes, sequence steps that switch drawing or undo, the
dialog watch's lost jobs, four Excel read / write faults, and three tests that passed for the wrong
reason. Filed, in areas other sessions are changing: #189-#191 and #206-#212. Live rows: Group RV, NOT RUN.

**Next:** the filed issues, highest first: #206 (palette Undo), #207 (batch text escape), #208
(bring-them-back after join / explode), #211 (check list PASS on failed reads).

## Earlier - 2026-11-21 (the smaller draw gaps, part 1 of #119, D-108)

Four new tools (**179** in all) in `tools/draw_extra.py` (#173, #174, #177, #181): `autocad_add_construction_line`
(xline or ray), `autocad_add_region` (closed outlines to regions, with area, perimeter and centre),
`autocad_add_donut` (rings and filled dots, the polyline DONUT makes) and `autocad_divide_curve`
(DIVIDE / MEASURE with points or a block). Maths and tools tested offline in
`tests/test_draw_extra.py`. Server only, no plug-in change. #119 stays open for its parts 2 and 3.

**Next (on this PC):** pull, restart Claude, then live rows AP1-AP10. AP2 (does AddRegion keep the
outline?), AP7 (DIVIDE on a closed object), AP8 (MEASURE on an exact end) and AP9 (blocks turned
when counted from the end) are the answers the code could not get from Autodesk's reference. Not
built: divide along a spline or an ellipse, XLINE's Offset and Bisect.

## Earlier - 2026-11-21 (a preview of a full sheet, D-102)

Issue #41 (an A1 extents preview showed only the frame) worked on offline in `tools/document.py`
only. The cause could not be seen here; the two likely ones are in [D-102](DECISIONS.md): too few
pixels for the sheet (most likely), or extents stretched by something far off. `autocad_preview`
now reports `plotted`, `pixels`, `smallest_clear_text` and a `tip`, and `detail=2` / `3` adds
window close-ups. Tests: `tests/test_preview_extents.py`. Limits: [05 §33](05-known-limits.md#33-one-preview-picture-cannot-show-a-whole-big-sheets-small-text).

**Next (on this PC):** pull, restart Claude (server only), then live rows AM1-AM6 on the A1 SLD.
AM1 names the cause; close #41 only after AM1 and AM2 pass.

## Earlier - 2026-11-21 (a busy AutoCAD is never a false failure, #36, D-100)

Issue #36 built offline. Past the D-57 message filter's 3 s, a refused COM call ("Call was rejected
by callee") now goes up as it is from every tool: `raise_if_busy(exc)` (`core/errors.py`) is the
first line of about 250 `except` blocks in `acad/`, `tools/` and the core. It is narrower than
`is_retryable`: pywin32's "no such member" `AttributeError` still means "not there". About 40 places carry
on through a refusal on purpose (restores, Esc, redraws, the D-58 waits, reads after the plug-in made
something); each is in `ALLOWED` in `tests/test_busy_sweep.py` with its reason. Four shared `_try`
readers (drafting, solids, sheets, dimensions_edit) take `busy_ok=True` for their restore, Esc and
redraw calls. The gate: a busy UNDO mark before an Ask-to-Keep job is refused in words, not "UNDO is
off" later. Tests: `tests/test_busy_refusals.py` (fake COM), `tests/test_busy_sweep.py` (reads the
source; a new `except` that can swallow a busy refusal fails it, with how to fix it).

**Next (on this PC):** pull, restart Claude (server only), then live rows AL1-AL7 with the Options
dialog left open.

## Earlier - 2026-11-21 (3D for MEP: #53, #54, #109, #58, #57; D-94, D-95)

Five issues built offline in one PR. `autocad_make_shape` has a 3D group: `duct_run` and
`pipe_spool`, solids along a route, a bend at every corner, flanges with bolt holes, each pipe's cut
length (pure geometry in `acad/shapes3d.py`, made over COM by `tools/_solid_pieces.py`). Four new
tools done by the plug-in (**175** in all): `autocad_flatten_views` (FLATSHOT / SOLPROF),
`autocad_section_plane` (SECTIONPLANE + 2D section block), `autocad_add_surface` (planar, network),
`autocad_add_mesh`; `autocad_loft(surface=true)`; `autocad_super_hatch` takes an image, an xref or
a wipeout as the tile. Plug-in: `Sections.cs`, `Surfaces.cs`, `SuperHatch.cs`, pure maths in
`Bridge/SectionMath.cs`; every .NET signature was checked against the AutoCAD 2027 reference
assemblies, and the add-in compiles for all three builds. Limits: [05 §32](05-known-limits.md#32-3d-for-mep-duct-runs-spools-flat-views-sections-surfaces-meshes-have-their-own-limits).

**Next (on this PC):** pull, build and install the plug-in, restart Claude, then live rows AH1-AH15
([NEEDS-CHECKING group AH](NEEDS-CHECKING.md)). The answers the reference could not give: which way
AutoCAD revolves a bend (AH3), where GenerateSectionGeometry puts a 2D section's lines
(`laid_flat_from`, AH4 and AH6), which side a section looks at (AH6), and whether XCLIP hides
images inside a block (AH12).

## Earlier - 2026-11-21 (drawing events from the plug-in, fewer batch pieces: #48, #45; D-98)

Branch `claude/plugin-events`. No new tool. **Plug-in change**: `DrawingEvents` (bridge) and
`DrawingWatch` (add-in) record each drawing opened, brought to the front, saved / saved as, closed;
new op `drawings`; `send_quiet` refuses after a switch mid-job and lines over `quietLimit` (1,500,
said in ping). Server: the guard reads the events (`core/drawing_events.py`); the batch goes in
longer pieces through the plug-in (`acad/lisp.py` `quiet_pieces`). The palette's Activity shows
the drawing events live. An independent review found six gaps, all fixed with tests (D-98, last
bullet): a drawing opened since the check, history that dropped off, bare-name matches, the status
mark, `send_quiet` now answering only after AutoCAD got to the input, old names keyed by database.
Built for all three targets and tested offline; none of it has run in AutoCAD. Versions not bumped
(the parent does). Follow-up: #165 (a sequence's COM steps after a mid-job switch).

**Next (on this PC, AutoCAD closed):** pull, build and install the plug-in, restart Claude; live
rows **AJ1-AJ10**. AJ6 first (count the `Command:` prompts for the 41-object batch), then AJ7
(every 1,500-character piece arrives); if one is lost, lower `QUIET_CHUNK_LIMIT`.

## Earlier - 2026-11-21 (files with AutoCAD closed, standards against a reference, shared check lists: #71, #69, #135; D-92, D-93)

Two new tools (**171** with the 2D edits and `autocad_render` removed): `autocad_read_file` (Read, needs no
AutoCAD: a DXF with ezdxf, a DWG / DWS / DWT through the ODA File Converter only when it is
installed) and `autocad_share_checklist` (Publish: the office list into the office folder, a
project's changes into `Heron check list changes.json` in the drawing's folder).
`autocad_check_standards` takes `reference=` (a `.dws`, `.dwt`, `.dwg` or `.dxf`; read by Heron, or
by AutoCAD's ObjectDBX when it is a DWG and the converter is not there). `autocad_checklist` has
`action='office_folder'` and names the file every check came from. The DXF reader is proved
offline on DXF files made by ezdxf; the converter, ObjectDBX on a `.dws` and a real network share
are not. Versions not bumped (the parent does).

**Next (on this PC):** close Claude, `.venv\Scripts\python.exe -m pip install ezdxf`, start
Claude, then live rows **AG1-AG15**. AG3 needs the ODA File Converter installed by hand; AG9-AG13
need a real share and a second PC. If Ajmal wants the office folder set in `.mcp.json` instead, or
roles for who may change the office list, that is a new decision on top of D-93.

## Earlier - 2026-11-21 (the everyday 2D edits, D-78 and D-79)

Issues #103, #49, #105, #111 and #110 built offline in one PR, from the ribbon audit (docs/12).
Eleven new tools in `tools/edit2d.py` (**169** in all, with the other sessions' work): trim /
extend, fillet / chamfer, break, join, edit a vertex, stretch, explode, draw order, match
properties, list groups, group. Lineweight and transparency on `autocad_modify_entity`. The geometry is plain Python in `acad/edit2d.py`
(`tests/test_edit2d_geometry.py`); the tools against fake COM in `tests/test_edit2d_tools.py`.
No typed commands, no plug-in change. Limits: [05 §29](05-known-limits.md#29-the-everyday-2d-edits-have-their-own-limits).

**Next (on this PC):** pull, restart Claude (server only), then live rows AA1-AA19 in a scratch
drawing. AA13 (does COM's Explode leave the original?) and AA14 (draw order in a drawing that has no
table yet) are the two answers the code could not get from Autodesk's reference. Not built:
Lengthen, and a fillet between a line and an arc ([#154](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/154)).

## Earlier - 2026-11-21 (`autocad_render` removed, #158)

Ajmal had the parent session decide #158, and it decided: remove `autocad_render`. His rule is that
Heron never runs the render (`-render` waits on prompts and can stall AutoCAD). Tool, level, preset
and size tables are gone: **158** tools. Docs: D-87 (an added note) and D-33's status, tools
reference, known limits §22, ribbon coverage "Render" row; live row F22 marked removed, F23 now uses
`autocad_run_lisp`; the finder phrase "render this view for the client" now finds
`autocad_add_camera_view` ("Add A Camera View For A Render"). Server only: restart Claude after
pulling.

## Earlier - 2026-11-21 (layers and annotation: #37, #107, #108, #116; D-80, D-81)

Seven new tools (**159** with the block, table and render tools): `autocad_layer_states`, `autocad_isolate_layers`,
`autocad_merge_layers`, `autocad_space_dimensions`, `autocad_break_dimensions`,
`autocad_annotation_scales`, `autocad_list_annotation_scales`; `annotative=true` on `add_text`,
`add_mtext`, `add_dimension`, `dimension_run`, `add_multileader`; `dim_style` on
`dimension_run`; `autocad_list_layers` lists the layer states. Six new plug-in operations
(`layer_state`, `layer_state_names`, `dimension_lines`, `move_dimension_lines`,
`annotation_scales`, `set_annotation_scales`), checked against Autodesk's reference assemblies and
compiled for all three builds; the plug-in version is not bumped here (the parent does it).

**Next (on this PC, AutoCAD closed):** pull, build and install the plug-in, restart Claude, then
live rows **AB1-AB11**. AB1 (the 1:5 style size) and AB9 (what height an annotative text gets)
decide whether the two size rules in D-80 / D-81 hold.

## Earlier - 2026-11-21 (setting a render up from the chat, #59-#63, D-86 / D-87)

Five new tools (**152** with the blocks and tables work merged first) and five new plug-in operations, built and tested offline in one PR:
`autocad_add_camera_view` (a view record with perspective and a lens, never DVIEW),
`autocad_set_sun` (date and time on the model viewport's sun through the plug-in; LATITUDE,
LONGITUDE, TIMEZONE and SUNSTATUS over COM), `autocad_list_lights` and `autocad_switch_lights`
(lights in model space and in light blocks; the sun and DEFAULTLIGHTING), and
`autocad_set_render_exposure` (EXPVALUE / EXPWHITEBALANCE). `autocad_set_3d_view` reads the
visual style back (`visual_style_found`). **None of these tools renders**: Ajmal presses Render;
whether `autocad_render` (Admin) stays is Ajmal's call, issue **#158**. An independent review found
six real problems before merging, all fixed with tests (stale sun on / off, a year refused only
after the place was set, TIMEZONE codes like 9031, a style reading taken as a failure, no warning
for 2D Wireframe, a layout view replaceable). The
add-in compiles for all three builds; versions not bumped (the parent does).
**Next (on this PC, AutoCAD closed):** build and install the plug-in, restart Claude, then live
rows **AE1-AE14**. AE14 decides the exposure route: if 2027 has no EXPVALUE, the ROADMAP item for
the viewport's `PhotographicExposureParameters` is next.

## Earlier - 2026-11-21 (blocks, attributes and tables: #115, #117, #106; D-82, D-83)

Branch `claude/blocks-tables`. Five new tools (**147**): `autocad_sync_attributes` (ATTSYNC),
`autocad_table_from_excel`, `autocad_update_table_links`, `autocad_set_table_cells`,
`autocad_copy_from_drawing`; `autocad_make_block` takes `attributes`. Three new plug-in operations
(`BlockAttributes.cs`, `ExcelTables.cs`): `sync_attributes`, `excel_table`, `update_table_links`.
The .NET calls were checked against Autodesk's reference packages for 2021, 2025 and 2027 and build
for all three with no warning; none has run in AutoCAD. Planning is offline and tested
(`acad/block_attributes.py`, `acad/table_cells.py`, `acad/drawing_copy.py`). Versions not bumped
(the parent session does it).

Merged as PR #155. Follow-up #156 (ATTSYNC for nested inserts, `nested=true`) on the same branch,
restarted from `main`.

**Next (on this PC, AutoCAD closed):** pull, `tools/build_plugin.py` + `tools/install_plugin.py`,
restart Claude; live rows **AC1-AC17**. AC7 first: whether AutoCAD's data link needs Excel
installed, and whether the connection string `file!sheet!range` is read as hoped.

## Earlier - 2026-11-21 (server core 2: #42, #44, #46, #47; D-76, D-77)

Built with offline tests, nothing proven in AutoCAD (NEEDS-CHECKING group Z, all NOT RUN):
- **#42** an UNDO / U / REDO / MREDO / OOPS through `autocad_send_command` is marked as a write
  before it is sent, so a busy retry never sends it twice (OUTCOME UNKNOWN in its own words).
- **#46** `autocad_run_lisp` cuts long code between top-level forms (`acad/lisp_forms.py`) into
  pieces under 700 characters, one undo mark round all of them; a piece that fails stops the rest.
- **#44** `quiet=true` (`core/quiet.py`) on the sequence, batch, dimension-run and centre-mark tools.
- **#47** the plug-in's ping says `command` (its command tracker); the gate asks only after a busy
  ending and names the command and the count so far in the plain line. **Plug-in change**: the
  parent session bumps the plug-in version; until it is installed the answers read as before.

An independent review of the diff found five problems, all fixed with tests (a comment hiding a
save, a busy step mis-read in a sequence, `new_handles` dropped by quiet, a part-way LISP run read
as DONE, and Discard's UNDO Back re-sendable by a busy retry). Next: run Z1-Z10 on AutoCAD 2027. Ideas left: catch a LISP error at once with `vl-catch-all-apply`
instead of waiting out 10 s (D-76 "left out").

## Earlier - 2026-11-21 (review fixes for the new tools, D-75)

An independent review of PRs #124, #143 and #146 found six real problems; all fixed with tests:
Excel's date / time / percent typing written as numbers (now refused, `excel_converted`), a tag
named HANDLE / BLOCK / LAYOUT breaking the sheet, no Block check (now per row, plus "Exported from"),
the folder check able to close an already-open drawing under another path, and three dry-run gaps
(a mark typed into a running command, UNDO Back after nothing was written, a cancelled dry run not
going back). D-75; known limits §27 updated; live row Y7. Server **1.10.1**, plug-in unchanged.

## Earlier - 2026-11-21 (check lists: cut-off reads, one Excel writer, release line endings)

- **PR #136 (merged):** a read cut off at `max_entities` is never a PASS. `title_block_filled` says
  NO DATA, and `autocad_check_standards` says `passed: null`, when nothing was found in the part
  read (D-64). The tool-finding test has four check list phrases (88 of 101 first, 101 of 101 in
  the top three). New issue **#135**: share the office check list and project changes with the
  team. It needs Ajmal's choice of shared folder.
- **PR #147:** release scripts check out with Windows line endings on every machine
  (`.gitattributes`), and the check list report uses `acad/xlsx.py` (one Excel writer).
- Still NOT RUN: live rows U1-U10 (U8 first: Excel opens the report).

## Earlier - 2026-11-21 (the dialog watch can press one named button, #101; plug-in 1.7.0)

`autocad_send_command` / `autocad_run_lisp` take `expect_box` + `press` (D-74). The plug-in's
`DialogWatch` presses that button only on a box with exactly that title, once, in that Admin job;
every other box is still cancelled. New protocol op `expect_dialog`; plug-in **1.7.0**, server
**1.10.0**. Offline: C# `DialogAnswerTests`, `ExpectDialogOpTests`; Python
`tests/test_dialog_answer.py`.

**Next (on this PC, AutoCAD closed):** pull, `tools/build_plugin.py` + `tools/install_plugin.py`
(plug-in 1.7.0), restart Claude. Live rows V7-V8 with the rest (R-Y). Every issue from the
2026-11-21 comparison is now closed except #80 (waits for row T7).

## Earlier - 2026-11-21 (the offline gates run on Linux, #102)

`tests/winstubs` stands in for pywin32 where it is not installed (D-72). On Linux:
`PYTHONPATH=src python -m pytest -m "not live"` gives 2931 passed, 19 skipped (each with its
Windows reason); `tools/check_structure.py` passes; `dotnet test` gives 297 passed, 1 skipped (the
named pipe). A cloud session can now run all four gates instead of saying NOT RUN. Windows CI
still runs every test.

## Earlier - 2026-11-21 (attribute sheets #96, folder check #97, Companion page #91; server 1.9.0)

Built offline in one PR, from Heron AI for Revit's ideas; design in
[docs/15](15-sheets-folders-companion.md). Server **1.9.0** (four new tools, **142**), plug-in
still **1.6.0** (no C# changed): restart Claude after pulling.
- **D-69 (#96):** `autocad_export_attribute_sheet` (Publish) and `autocad_apply_attribute_sheet`
  (Change). The workbook's "As exported" sheet lets the compare keep the drawing's own later
  changes and list conflicts; only changed cells are written, one undo step. `acad/xlsx.py` reads
  and writes `.xlsx` with the standard library.
- **D-70 (#97):** `autocad_check_folder` (View): each drawing read only, checked, closed unsaved.
- **D-71 (#91):** `autocad_companion` (Read): a page file per chat, rewritten by the gate after
  every job. Editable tables (Revit's) would need a local server: not built.

**Next:** live rows Y1-Y6 with the others below. Still open from the comparison: #80 (row T7).

## Earlier - 2026-11-21 (palette follow-up: Run never skips the checks, #138 closed)

A review of the docked palette (D-68) after plug-in 1.6.0 merged found one safety gap and three
robustness gaps, all fixed in PR #137. Plug-in **1.6.0** already carries them if it is
built from `main` after #137; no version change.
- **Safety:** the palette's Run inherited AutoCAD's environment, so a developer's
  `HERON_AUTOCAD_BRIDGE=off` or a chat id there would have reached it. Now forced on and dropped
  (`PaletteServer.PrepareEnvironment`), and the server refuses `--run-saved` with the checks off.
- **#138:** while a palette Undo waits for AutoCAD, the plug-in refuses a new job's begin with
  "try again in a moment" (`BridgeProtocol.BlockedBy`, one minute at most).
- An UNDO AutoCAD has not started in 30 s is given up; a job whose end never came stops blocking
  the palette after 20 minutes.

**Next:** as below, plus live rows X22-X24 (X23: whether zooming inside a layout viewport counts as
a change, which would make Undo refuse there).

## Earlier - 2026-11-21 (autocad_why after D-59, and Heron's folders, #134)

Follow-up to PR #120, server only, no version change.
- **Bug fixed:** since D-59 (padlocks in AutoCAD's memory) `diagnose.report()` has no padlocks,
  so `autocad_why` said every padlock was off. It now names the padlocks a job needs as
  non-blocking reasons (`needs_changes`, `needs_publish`, `needs_admin`) and never claims one
  is off (D-67, last bullet). Live row W2 rewritten to match.
- A `dry_run` refusal (D-63) is audited with the reason word `no_dry_run`.
- **#134:** `core/folders.py` (`local_app_data`, `roaming_app_data`, `heron_local`) is the one
  place that reads `%LOCALAPPDATA%` / `%APPDATA%`; `tests/test_folders.py` fails if a module
  builds a folder from the bare variable again. `tests/conftest.py` now also moves `%APPDATA%`
  to a temp folder.

**Next:** unchanged: build and install plug-in 1.6.0, then the live rows (W included).

## Earlier - 2026-11-21 (the Revit batch is merged: server 1.8.0, plug-in 1.6.0; nothing live yet)

Every PR from the seven cloud sessions is merged into `main`, on Ajmal's word: ribbon audit and
install table (#99), dialog watch (#100), why / gaps / question mode (#120), padlocks in memory
(#121, **Ask to Keep starts off, as before**, Ajmal's choice), check lists (#122), docked palette
(#123), server answers (#124), and their notes (#125, #127, #129-#131). The Claude review check
works again (#126: it lacked the tools the code-review command uses); it still fails now and then
in 2 s at no cost while many cloud sessions run at once, which looks like the account's rate limit,
not the code. Server **1.8.0**, plug-in **1.6.0**, 138 tools. All gates pass on `main` (2,853
offline tests, 290 bridge tests on net48 and net10, ruff, structure).

Still open from the comparison: #80 (waits for live row T7), #91 Companion page, #96 spreadsheet
round trip, #97 folder check, #101 dialog watch named answer.

**Next (on this PC, with AutoCAD closed):** pull the main checkout, `tools/build_plugin.py` +
`tools/install_plugin.py` (plug-in 1.6.0), restart Claude. Then the live rows, none run yet:
R (padlocks), T (server answers), U (check lists), V (dialog watch), W (why / gaps), X (palette),
and the older M-Q. After the restart every padlock is off: turn Changes on in Settings first.

## Earlier - 2026-11-21 (check lists for QA #84-#87 merged, PR #122)

PR #122 was merged by Ajmal after CI `python` and `plugin` passed. Server only, no plug-in change;
restart the server after pulling. 138 tools.
- **D-64 (#84, #85, #87):** check list results are PASS, FAIL, **NO DATA** (could not decide; never a
  PASS) and NOT RUN (switched off for this project), with a coverage line on every run. Office
  lists stay in `%LOCALAPPDATA%\Heron\autocad\checklists`; a project's changes (severity, target,
  on/off only) are kept per project folder in `checklists\projects`. PASS means the checked value
  is met against the named source; no answer says "complies"; [DISCLAIMER.md](../DISCLAIMER.md).
- **D-65 (#86):** `autocad_checklist_report` (Publish) saves a run as `.xlsx` + `.html` next to the
  drawing, numbered ` (2)`, ` (3)`, never overwriting. The workbook is written without openpyxl.
- **One test changed on purpose:** a missing title block is now NO DATA, not NOT RUN.

**Next:** in AutoCAD 2027, run group U rows U1-U10 (all NOT RUN); U8 first (does Excel open the
report without a repair message). The server is now **1.8.0**, which includes these tools.
Possible later: share an office list from a network folder; keep project changes in the project
folder so the team shares them.

## Earlier - 2026-11-21 (docked Heron palette #92-#93 merged, PR #123)

PR #123 was merged on Ajmal's word, after CI `python` and `plugin` passed (`review` was skipped,
#34). Plug-in **and** server change: rebuild and reinstall the plug-in (AutoCAD closed), and
restart the server after pulling.
- **D-68:** `HERONPALETTE`, or Heron (arrow) -> **Heron palette**, opens one docked palette with two
  tabs in Heron's window style. **Activity** lists Heron's change jobs from every chat, newest
  first, with Select, Zoom and Undo; Undo is the modeller's (no padlock) but only by D-54's rule,
  and says why when not. **Saved commands** lists the commands saved in a chat (shown within 2 s),
  fills their inputs and runs one by starting a copy of the server
  (`--run-saved request.json --acad-pid N`), which passes the same gate, hold and padlocks as any
  chat, checks units first and frees the AutoCAD after.
- Rules in the bridge, tested offline: `ActivityLog.cs`, `SavedCommandList.cs`, `PaletteServer.cs`,
  words in `PaletteTexts.cs`. Server side: `src/autocad_mcp/palette.py`; every server now writes
  `%LOCALAPPDATA%\Heron\autocad\server.json` at start, which is how the palette finds it.
- Found on the rebase and fixed before merging: the palette read the D-62 plain line
  (`REFUSED ...`) as success; it now reads the word. The palette run returns before
  `follow_host_chat()`, so it never takes the chat's id (D-61).

**Next:** install the plug-in and, in AutoCAD 2027, run group X rows X1-X20 (all NOT RUN); **X4
first** (whether the palette's Zoom leaves an undo step that would block Undo). The plug-in is
now **1.6.0**, which includes the palette (new command, protocol unchanged).

## Earlier - 2026-11-21 (why / gaps / question mode #88-#90 and #43 merged, PR #120)

PR #120 was merged on Ajmal's word, after CI `python` and `plugin` passed (the `review` check
failed as on every PR, #34). Server only, no plug-in change; restart the server after pulling.
- **D-67 (#88):** `autocad_why` (Read) finds the tool for a job and lists what is in the way,
  worst first, with what to do. The plug-in version a tool needs is read from its own "plug-in
  X or newer" docstring line. Logic in `acad/why.py`, tools in `tools/explain.py`.
- **D-67 (#89):** `autocad_gaps` (Read) sums up the audit log (`core/audit.py` `summary`). The
  gate now writes a `reason` word on a refused or failed call (`audit.reason_of`), never the
  message.
- **Both need no AutoCAD:** the gate runs them like `autocad_use_autocad`, audited but without
  looking at AutoCAD (`gate.NO_AUTOCAD_TOOLS`).
- **D-67 (#90):** `findtool.is_question` / `rank`: a question gets only Read tools as matches;
  the rest go under `would_change_the_drawing`. "does" and "do" are left out on purpose.
- **#43:** `audit_dir()` falls back to `~/AppData/Local/Heron/autocad/audit`. `bridges_dir()` in
  `core/bridge.py` has the same pattern and is not fixed (the plug-in writes that folder).
- PR #125 then set docs/12's tool count to 137; it is 138 on `main` since PR #122.

**Next:** in AutoCAD 2027, run group W rows W1-W8 (all NOT RUN). The server is now **1.8.0**,
which includes these tools.

## Earlier - 2026-11-21 (server answers #78-#82 merged, PR #124)

PR #124 was merged on Ajmal's word, after CI `python` and `plugin` passed (the `review` check
failed as on every PR, #34). Server only, no plug-in change; restart the server after pulling.
- **D-61 (#78):** the server's chat id comes from `HERON_CONVERSATION_ID`, else Claude Code's
  `CLAUDE_CODE_SESSION_ID` (hashed), else a new one, so a resumed chat keeps its hold. Only
  `server.main` follows the host; scripts stay their own chat.
- **D-62 (#79, #82):** every Change / Admin / Publish answer starts with DONE, NOTHING CHANGED,
  REFUSED or OUTCOME UNKNOWN (`core/answers.py`, added by the gate). Scripts drop it with
  `answers.body()`. The modify, attribute, find-replace, dynamic block, layer and variable tools
  add `before_after` (old -> new, first 50) and write only what differs.
- **D-63 (#81):** `dry_run=true` on any Change tool, given by `tool_errors`; Publish, Admin and
  `autocad_undo_last` refuse it.
- **#80 stays open:** the tools above leave no undo step when nothing differs; taking back an
  empty job afterwards waits for live row T7 ([05 §26](05-known-limits.md)).

**Next:** in AutoCAD 2027, run group T rows T1-T7 (all NOT RUN). T7 decides #80. The server is
now **1.8.0** (plug-in still 1.5.0): on this PC, restart Claude after pulling so the new server runs.

## Earlier - 2026-11-21 (every open item is a GitHub issue; seven cloud sessions build the Revit ideas)

Every open [ROADMAP](ROADMAP.md) item became a GitHub issue (#39-#75), and the ROADMAP links each
one. Two items were already built and are ticked: texture size (D-46) and the server version in
status (D-48). Heron AI for Revit was compared again, and what AutoCAD lacks became issues #76-#97
(label `from-heron-revit`, new ROADMAP section). The most important is a bug: **#76, a chat can
switch its own padlocks on by writing `heron-autocad.config`**.

Seven cloud sessions build them, each opening its own PR to `main`, none merged:
padlocks #76-#77 (D-59/60, group R), server answers #78-#82 (D-61-63, group T), check lists
#84-#87 (D-64/65, group U), dialog watch #83 (D-66, group V), why / gaps / question mode #88-#90
and #43 (D-67, group W), docked palettes #92-#93 (D-68, group X), ribbon audit and install table
#94-#95. They leave HANDOVER, CHANGELOG, ROADMAP and versions to the parent, with their lines in
the PR description. Expect tool-count conflicts between them; merge one at a time.

**Trap found:** a cloud session started from a worktree session begins on that session's branch,
so the branch must be pushed first, or the cloud session stops at once with "An API error occurred"
(the details say the branch was not found).

**Next:** review each PR as it arrives; merge on Ajmal's yes, one at a time. Live rows for all of
it stay NOT RUN until AutoCAD.

## Earlier - 2026-11-21 (this PC updated: server 1.7.0, plug-in 1.5.0 installed)

On Ajmal's word, with AutoCAD closed, the main checkout `D:\06_Development\09_Autocad MCP\Autocad MCP`
was fast-forwarded to `main` a29b4a8 (PR #33). `tools/build_plugin.py` built plug-in **1.5.0**
(0 warnings), and `tools/install_plugin.py` replaced the installed 1.4.2 in
`%APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle`. No Python reinstall was needed: only
the version line changed in `pyproject.toml`, and the version is read from `__init__.py`.

The offline tests passed in the main checkout, except `test_structure`, which read the other
sessions' worktrees under `.claude/worktrees` as "AutoCAD API outside the add-in". It now skips
`.claude`, which holds nothing tracked (this PR).

Merged branches were deleted on GitHub and locally. Follow-ups are issues #34-#37.

**Next:**
- Restart Claude, so the server runs 1.7.0.
- Start AutoCAD 2027 and press Heron.
- Run the live rows M1-M8, N1-N8, O1-O7, P1-P5 and Q1-Q5.
- Take `view_only` off the Luxury Suite 3 player's view steps once Q2 passes.

## Earlier - 2026-11-21 (busy-AutoCAD fixes from the Luxury Suite 3 rehearsal, PR #33)

PR #33 (branch `claude/busy-autocad-fixes`, from `main` ef0af45) was merged on Ajmal's word on
2026-11-21. CI `python` and `plugin` passed; the Claude `review` check failed before reviewing,
as on every PR since #28 (its login, not the code). There are two fixes, both found live on
2026-11-18, and no plug-in change.
- **D-57:** a COM message filter on the worker thread (`core/message_filter.py`, ctypes) asks again
  a call AutoCAD turned away, waiting up to 3 s in all per job (reset by the worker for each
  job). The `_with_retry` window is capped at 10 s.
  `ensure_layer` and `ensure_linetype` let a busy refusal up, and `com_message` says "AutoCAD was
  busy".
- **D-58:** `autocad_run_lisp` waits through refused reads, and puts USERS1, USERS2 and OSMODE back
  patiently.

The brief asked for a busy retry in `connection.run`. It was already there (D-02), but it never saw
this refusal. The rehearsal's own log (`rehearsal-2d-run.txt`, s037) shows the exact text from
`ensure_layer`.

The optional `dim_style` for `autocad_dimension_run` was left for the [ROADMAP](ROADMAP.md),
with the traps found. Gates passed offline: ruff, 2,606 offline tests, 202 bridge tests on net48
and on net10, and the structure check. **Live rows Q1-Q5 NOT RUN.**

**Trap for the next session:** in a worktree, run pytest with `PYTHONPATH=src`. The shared venv
imports `autocad_mcp` from the main checkout otherwise, so the tests test the wrong code.

**Next:** this change alone needs no plug-in build, but the main checkout on this PC is still at
PR #26. Pulling it also brings PRs #28-#31, which need plug-in 1.5.0. So, with AutoCAD closed:
pull the main checkout, `tools/build_plugin.py` + `tools/install_plugin.py`, restart Claude.
Then run rows Q1-Q5 (and M, N, O, P), and take `view_only` off the player's view steps once Q2
passes. Follow-ups are GitHub issues, opened on 2026-11-21.

## Earlier - 2026-11-19 (the four PRs are merged; nothing built since)

PRs #28, #29, #30 and #31 were merged into `main` on 2026-11-16, in order; `main` = e776c38,
`ci` and `weekly` green there. No open pull requests. Server **1.7.0**, plug-in **1.5.0**, 135
tools. **Not done on this PC:** the main checkout `D:\06_Development\09_Autocad MCP\Autocad MCP`
was 10 commits behind (still the 1.6.0 server other sessions use), and the installed plug-in is
the old one. Checked before updating it: none of the 277 raw command / AutoLISP steps of the Luxury
Suite 3 player is refused by D-47, and none erases, so D-50 asks nothing during that recording.
**Next:** with AutoCAD closed, pull the main checkout, `tools/build_plugin.py` +
`tools/install_plugin.py`, restart Claude, then the live rows M1-M8, N1-N8, O1-O7, P1-P5. The
Claude review check fails on every PR before reviewing (log hidden; most likely the
`CLAUDE_CODE_OAUTH_TOKEN` login): renew that secret if the review is wanted.

## Earlier - 2026-11-15 (15 ideas adopted from Heron AI for Revit, four stacked PRs)

Studied Heron AI for Revit and built what fits AutoCAD, in four stacked branches / PRs:
**#28** batch 1 (`autocad_show`, save guard D-47, progress notes, `autocad://diagnose` D-48, secret
scan, weekly audit); **#29** batch 2 (`autocad_use_autocad` D-49, change count + erase question
D-50, HERONSTOP D-51); **#30** batch 3 (check lists D-52, project notes D-53, activity + undo last
D-54); **batch 4** (saved commands D-55, installer keep / rollback / update check + release
workflow D-56, and the bundle version now read from `Directory.Build.props`). Server **1.7.0**,
plug-in **1.5.0**, 135 tools. Every gate passes offline; **every live row M1-M8, N1-N8, O1-O7,
P1-P5 is NOT RUN**. The release workflow runs only on a `v` tag, and the tag still waits for
groups A, D, E and F (see the entry below). The Claude review check on #28 failed after 2 s
before reviewing anything (its log hides why; most likely the review login): not a code failure.
**Next:** merge #28 -> #29 -> #30 -> batch 4 in order, build + install with AutoCAD closed, then
the live rows. Left for later ([ROADMAP](ROADMAP.md)): a docked activity palette, and a
saved-command palette in AutoCAD.

## Earlier - 2026-11-09 (fixes found on the Luxury Suite 2 interior set)

Branch `claude/fix-session-bugs-1109`: four fixes found live while building a 3D suite and its
interior drawing set in AutoCAD 2027 - run_lisp length cap and timeout note, status survives a
paper space that throws, viewport fallback through MVIEW, and plug-in **1.4.2** clearing a material's
old image on a colour-only replace. Plus five roadmap items (camera views, sun, exposure, quiet
results, sheets by the plug-in). Known limit 23. **Next:** merge, then live rows K16, S8-S10.

## Earlier - 2026-11-09 (housekeeping check, nothing built)

All three branches above are merged: texture size (#22), the Heron button connects again (#23), the
heron stays on top (#24). `main` CI green; no open pull requests or issues. **No tag and no GitHub
release**: [ROADMAP](ROADMAP.md) holds the tag until NEEDS-CHECKING groups A, D, E and F pass, and
most of D and E are still NOT RUN. Branch `claude/charming-wright-x62eri` is merged and can be
deleted. **Next:** close AutoCAD, `tools/build_plugin.py` + `tools/install_plugin.py`, then
[NEEDS-CHECKING K15](NEEDS-CHECKING.md) and `tools/live_check.py --group all --write`.

## Earlier - 2026-11-08 (texture size for materials)

Branch `claude/charming-wright-x62eri`: `autocad_create_material` takes `texture_size` /
`texture_height` and writes the texture and bump map transform itself ([D-46](DECISIONS.md)),
plug-in **1.4.1**. Found live on the bedroom + bathroom model: 11 library textures rendered flat until
the group-43 matrix was fixed by hand. Offline gates run in the cloud (Linux): see the PR. **Next:**
merge, close AutoCAD, `tools/build_plugin.py` + `tools/install_plugin.py`, then
[NEEDS-CHECKING K15](NEEDS-CHECKING.md).

## Earlier - 2026-11-08 (tidy-and-release round)

Branches tidied to main only (bundle backup in `Documents\Heron backups\2026-11-08-heron-autocad-housekeeping`).
Branch `claude/installer-remove-and-brand-colours`: `Uninstall.bat` that asks first, plain-word
installer refusals, a first-install fix for PowerShell 5.1, and the three Heron windows in the brand
colours ([D-43](DECISIONS.md)): merged as #19. Then branch `claude/ribbon-settings-window-and-brand-icons`:
the ribbon is Heron + Settings, the padlocks in a Settings window, Revit's brand icons ([D-44](DECISIONS.md)).
**Next:** after it merges, close AutoCAD, `tools/build_plugin.py`, `tools/install_plugin.py`, then
`tools/make_release.py` from `C:\hbuild\v` (diff its `autocad_mcp` against `src` first). Owed:
[NEEDS-CHECKING group L](NEEDS-CHECKING.md) L1-L10. Then branch `claude/banner-like-revit`: the
banner, Bridge Status, Settings, Keep and a new switch question all drawn as Heron for Revit's, plus
Free this AutoCAD ([D-45](DECISIONS.md)).

## Earlier - 2026-11-05 (fixes from the cassette and bedroom models)

Five faults met while drawing were fixed offline, on branch `claude/autocad-3d-metal-detailed-be50a3`,
**not committed yet** (check `git status`): the banner's DONE card that never closed (`BannerJobs`),
fillet / chamfer / shell / press-pull / face listing failing on every solid (Brep built from the
entity, now from its FullSubentityPath), `autocad_run_lisp` leaving AutoCAD stuck in a command
(wrapper cancels it, snaps off), `autocad_create_layout` leaving a half-made sheet, and previews on
their side. All gates green (2319 Python, 145 C#, 3 add-in builds). **Next:** close AutoCAD,
`tools/build_plugin.py` + `tools/install_plugin.py`, restart the chat's server, then run
[NEEDS-CHECKING group J](NEEDS-CHECKING.md) J1-J6.

## Where things stand - 2026-10-26

| Area | State | Evidence |
|---|---|---|
| Name and repository | **Heron AI for AutoCAD**, public, `Ajmalpshaik/Heron-AutoCAD` | [D-12](DECISIONS.md) |
| Server tools | **107 tools**, every one gated by the plug-in; 5 resources, a tool search and **7 job prompts** | `pytest -m "not live"` green (1812 tests); `tools/check_structure.py` OK |
| Sheets, UCS, shop drawings | **14 tools, server 1.2.0** (2026-10-26): the UCS, layouts, page setup, title blocks, viewports, saved locations, drawing settings and styles, remap layers, tidy an import, `autocad_sequence`. All the arithmetic and planning is tested offline; **everything COM touches is NOT RUN** | [09](09-sheets-and-coordinates.md), D-27 / D-28 / D-29, [NEEDS-CHECKING group D](NEEDS-CHECKING.md) |
| Geometry, annotation, 3D | **12 tools, server 1.3.0** (2026-10-26): 24 named shapes, dimension runs, centre marks, multileaders, tables, revision clouds, solids, extrude / revolve, booleans, mass properties, 3D paths, 3D views. Plus polyline bulges and text justification in the batch. Geometry tested offline (402 tests); **everything COM touches is NOT RUN** | [10](10-geometry-annotation-3d.md), D-30 / D-31, [NEEDS-CHECKING group E](NEEDS-CHECKING.md) |
| Proving it in AutoCAD | **`tools/live_check.py`** (2026-10-26): one command measures 65 of the 90 live rows in a scratch drawing it makes itself and writes the results here. The other 25 need an eye or depend on the machine and say so. **Not yet run on a real AutoCAD** | `tools/README.md`, [NEEDS-CHECKING](NEEDS-CHECKING.md) header |
| Findability | **Measured, not assumed** (2026-10-26): every tool carries a `Use when` line, `autocad://tools` indexes them and `autocad://tools/find/{phrase}` searches them. 97 real phrases (2026-11-21): 84 put the right tool first, all 97 in the top three; 13 question phrases each get a Read tool first (D-67) | `tests/test_find_tool.py`, D-32, D-67 |
| The rest of 3D | **6 tools, server 1.6.0** (2026-10-26): oval primitives, sweep along a path, slice, clash detection, 3D move/rotate/mirror/array, materials, render. The plane arithmetic is tested offline; **everything COM touches is NOT RUN** | [NEEDS-CHECKING group F](NEEDS-CHECKING.md), D-33 |
| Plug-in (C#) | Ribbon, padlocks, banner, Bridge Status, Keep or Discard, 6 commands. Builds for net48 / net8 / net10 with 0 warnings | `dotnet build`; bridge tests green incl. real Python <-> C# |
| Plug-in live in AutoCAD | **2027: 18 rows PASS on 2026-10-26**, A21 fixed and PASS (D-21), 6 rows still NOT RUN. 2021-2026: no machine | [NEEDS-CHECKING](NEEDS-CHECKING.md) group A |
| Bundle and installer | `tools/build_plugin.py` -> `dist/HeronAutoCAD.bundle`; `tools/install_plugin.py` (refuses while AutoCAD runs) | `tests/test_plugin_bundle.py` |
| CI | Two jobs on Windows: Python (ruff, tests, structure) and plug-in (3 builds + bridge tests) | `.github/workflows/ci.yml` |
| Drawing packages | AHU-01, CCTV 42 sheets, pole enclosure: on this PC only. Their generator scripts were removed ([D-23](DECISIONS.md)) | `drawings/` |

## Next, in order

0. **2026-11-05: lights, materials and a saved 3D view, for the villa model** (plug-in **1.4.0**,
   D-42; 2 new tools, 128 in all): `autocad_add_light` (point, spot, web, distant; lm / cd / lux,
   Kelvin or a colour, cones, IES file, on / off, shadows, name, layer; warns when LIGHTINGUNITS is
   not 2) and `autocad_create_material` (colour, texture image, gloss, reflectivity, transparency,
   refraction, glow in cd/m² with a Kelvin white, bump, metal), both plug-in operations through
   AutoCAD's .NET `Light` and `Material` classes; and `autocad_save_view(from_screen=true)` for a
   3D camera view. A light goes into a block with `autocad_make_block` like any object. Offline
   gates green, the add-in compiles for all three builds; **group K of NEEDS-CHECKING is NOT RUN**.
   To prove: merge, rebuild and reinstall the plug-in with AutoCAD closed, set LIGHTINGUNITS 2,
   then K2 (the spot's cone angles read back as given), K7 (a light block lights every insert) and
   K8 (a made material applies at once) first. The `autocad_preview` 90-degree turn was fixed
   separately the same day (group J, J6).
0. **2026-11-04: from Autodesk's ADN-DevTech samples** (plug-in **1.3.0**, D-41; 3 new tools, 126
   in all): `autocad_xref_tree`, `autocad_drawing_report`, `autocad_publish_pdf` (a plug-in
   operation through AutoCAD's publisher), the command name in the busy message, and
   `tools/memory_check.py`. Offline gates green, the add-in compiles for all three builds; **group
   I of NEEDS-CHECKING is NOT RUN**. To prove: merge, rebuild and reinstall the plug-in with AutoCAD
   closed, then I3 (three sheets, one never opened, one PDF) and I1 (a renamed xref shows as
   broken) first. What was taken and why: [11](11-adn-repos-study.md).
0. **2026-10-29: the plug-in does its own operations** (plug-in **1.2.0**, D-40; 8 new tools, 123
   in all): `autocad_list_solid_faces_and_edges`, `autocad_loft`, `autocad_fillet_solid_edges`,
   `autocad_chamfer_solid_edges`, `autocad_shell_solid`, `autocad_press_pull_faces`,
   `autocad_thicken_surface`, `autocad_super_hatch`. The server asks with the new bridge request
   `run`; the plug-in does the work through the .NET API in one transaction. Bridge rules and the
   Python side are tested offline; the add-in **compiles** for all three AutoCAD builds with 0
   warnings, but **nothing of it has run in AutoCAD**: group H of NEEDS-CHECKING is NOT RUN. To
   prove: merge, stop every `autocad-mcp` server, rebuild and reinstall the plug-in with AutoCAD
   closed, start AutoCAD and a fresh server, then do H1-H13 by hand. H3 (one Ctrl+Z undoes a
   plug-in operation) and H10 (the super hatch clip shows) first: the rest rests on them.
0. **2026-10-28/29: acoustic ceiling set drawn in AutoCAD 2027** (5 A1 sheets, 12 viewports;
   drawing on this PC only, `drawings/ACOUSTIC`). Live results recorded: D12 and D16 PASS; D20
   export of a layout FAIL, fixed in `_plot_pdf` (no `CenterPlot` on a layout plot, keep the
   layout's sheet), re-run NOT RUN; D8 create_layout and the new D33 (status / table with a sheet
   tab active) FAIL, causes not found, on the ROADMAP. Lesson: an AI must not write a `.lsp` and
   load it through `autocad_run_lisp`; that is what brings back the SECURELOAD box (TROUBLESHOOTING
   now says so).
0. **2026-10-28: seven drafting tools built** (spline, multiline, wipeout, attach / manage xref,
   hatch pattern and linetype files; 115 tools). Offline gates green; group G of NEEDS-CHECKING is
   NOT RUN. Do G5 (wipeout lands in world coordinates, unsnapped, under a UCS) and G10 / G11 (the
   custom pattern hatches; the CHWS text sits clear of the dashes) first: those rest on typed
   input and on file formats, not on a documented Automation call. Super hatch and loft / fillet /
   shell / press-pull need the plug-in (ROADMAP).
0. **2026-10-28: five tools that failed live are fixed** (branch `claude/wonderful-fermi-w5otnd`).
   Hit while drawing a chilled water roof pipe support in AutoCAD 2027, and worked round with
   `autocad_run_lisp`: `drawing_setup(scale='1:10')`, a dim style with `text_style`, table text
   height, booleans on real solids, `visual_style='realistic'`. Checking for the same faults found
   three more: `scale=10` read as 10:1 (now refused, D-36), dim-style whole numbers sent as
   decimals, and slice / clash check / `solids_only` materials refusing real solids. The visual
   style is now typed as the VSCURRENT command (D-35). Offline gates green; rows D23, D32, E18, E28
   and E34 are NOT RUN. To prove: merge, stop every `autocad-mcp` server before reinstalling, start
   a fresh one, then `tools/live_check.py --group all --write`. Watch E34's 'shaded with edges' and
   'shades of gray' by hand (known limit 15).
   **A second check of the whole server** (same day, same branch) found seven more: oval solids
   never made (no AutoCAD call), hatch pattern type 0 instead of 1, ordinates measured from the UCS
   origin not the datum (now refused, D-37), directions not turned on a UCS in four 3D / dimension
   tools, point variables sent as plain pairs, the purge text-style answer, and two swapped
   selection codes. Rows E13, F1 and S4-S7 are NOT RUN; E13 and F1 are in `live_check.py`, S4-S7
   are by hand.
0. **2026-10-27: reads leave no undo step** (branch `claude/read-calls-no-undo-step`, D-34). Found in
   A30: a U after list / variable / preview removed nothing. The plug-in now pauses undo recording
   for Read jobs. Offline gates green; live row A31 is NOT RUN: merge, rebuild and install the
   plug-in, then batch, look, and press U once.
0. **2026-10-27: `autocad_batch_labels` built** (one call + one undo step for a label column,
   `arrow_scale`, `crossing` report); offline gates green. Live row A30 is NOT RUN: merge to main,
   restart the server, then draw a 15-label column. Why: a CCTV pole test sheet took ~120 tool calls,
   mostly one label / block / dimension at a time; batch blocks and dimensions are the next candidates.
1. **Run NEEDS-CHECKING groups D, E and F** (90 rows) on AutoCAD 2027. **This is one command
   now, not a day of clicking** — with the Changes padlock on:

   ```bash
   .venv\Scripts\python.exe tools/live_check.py --group all --write
   ```

   It works in a scratch drawing it makes and closes itself, measures 65 of the 90 rows, and
   writes each result and its evidence straight into NEEDS-CHECKING.md. Read the FAIL list
   first: a FAIL there is a defect in a tool, not in the runner, until shown otherwise. The 25
   it cannot measure are written NOT RUN with the reason; `--list` names them.

   From group F, the newest and least proven, start with:
   - **F1** — a 400 x 200 oval duct must measure 400 x 200. If it comes out 800 x 400, the
     half-axis conversion in `tools/solids.py` is inverted.
   - **F5 / F11** — a slice's two halves must add up to the original, and a clash check with
     `create_solids=false` must leave the entity count unchanged.
   - **F15** — a 1000 tall column tipped 90 degrees about X must lie down to 100.

   From group E, five rows matter most:
   - **E4** — measure the two arcs of a cone development. Outer 628.3, inner 314.2. That one
     measurement proves every flat pattern the server will ever draw.
   - **E1 / E36** — a slot must come out as **one** polyline, not a pile of arcs, and a batch text
     must justify. Both rest on the DXF group codes added for the shape library (42, and 72/73/11).
   - **E22** — a box's base must sit on z=0, not half a height below it.
   - **E29** — a boolean with a bad handle must refuse **before** consuming anything.
   - **E13 / E16 / E18 / E26** — `AddDimOrdinate`, `AddLeader`/`AddLeaderLine`, `AddTable` and
     `AddRevolvedSolid` have never been called from this server. Their signatures came from
     Autodesk's reference, not from a run.
   And from group D, these four:
   - **D13** — measure a known 10 m wall on the plot of a 1:100 viewport. It must be 100 mm. This is
     the one thing that proves the viewport maths and the `CustomScale` pin.
   - **D23** — after `autocad_create_styles`, check `DIMSCALE` and `DIMTXT` with SETVAR. The
     drawing's own DIM variables must be back where they were.
   - **D30** — `autocad_sequence` containing `autocad_save_drawing`, and one containing
     `autocad_run_lisp`. Both must be refused. This is the padlock ceiling (D-29) and it must be
     re-run every time a tool is added.
   - **D4 / D15** — the UCS rows: a rotated UCS is the whole reason D-27 exists, and it has only
     been proved by arithmetic so far.
   Fix what fails before building anything else on top.
   **Do this with one command, not by hand:** with Changes on,
   `.venv\Scripts\python.exe tools/live_check.py --group all --write`. It measures 46 of the 67
   rows and writes the evidence into NEEDS-CHECKING itself. Read the FAIL list first - a FAIL
   there is a real defect in a tool, not in the runner, until you have shown otherwise.
2. Choose-which-AutoCAD when several are open ([ROADMAP](ROADMAP.md)).
3. Run the remaining 2027 group A rows (A8e, A15, A16, A19, A20); restart AutoCAD first so the
   double-click fix (D-20) is loaded. Live checks are driven with one server for several calls
   (`HERON_CONVERSATION_ID` keeps one chat id across scripts).
4. Tag `v1.6.0` once groups A, D, E and F pass.
5. Pick from [ROADMAP](ROADMAP.md) — `coords="ucs"` on the single-entity draw tools is the natural
   next step, now the transform and its tests exist; after that, hatch and mtext operations in
   `autocad_batch_draw`, which would give the furniture shapes real filled arrowheads.

## Before you stop

Update the table above, add decisions to [DECISIONS.md](DECISIONS.md), a line to
[CHANGELOG.md](../CHANGELOG.md), run the gates, commit and push.
