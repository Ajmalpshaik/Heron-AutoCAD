# Session handover

> **What this file is:** where the last session stopped and what comes next. It is a work note. Where
> it disagrees with the code, the tests, [NEEDS-CHECKING](NEEDS-CHECKING.md) or
> [DECISIONS.md](DECISIONS.md), those win.

## If you are the owner, starting work - say this

> **"Read docs/HANDOVER.md in Heron-AutoCAD and carry on."**

## Latest - 2026-11-09 (fixes found on the Luxury Suite 2 interior set)

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
| Findability | **Measured, not assumed** (2026-10-26): every tool carries a `Use when` line, `autocad://tools` indexes them and `autocad://tools/find/{phrase}` searches them. 67 real phrases: 55 put the right tool first, all 67 in the top three | `tests/test_find_tool.py`, D-32 |
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
