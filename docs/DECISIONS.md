# Decision log

> **Append-only.** A decision that is later reversed gets a **new** entry that supersedes the old one;
> the old one stays, so the reasoning is never lost. Number new entries one above the highest here.

---

## D-134 - Lengths and texts are read by the plug-in in one go, dressed as the COM objects they stand for

**Decided:** 2026-11-23, by session S8 of the 2026-11-23 wave ("Yes, next 10"), on issues #195 and
#197 (ranks 4 and 6 of #74), under D-114. **Status:** in force; tested offline only, live rows NOT RUN
(NEEDS-CHECKING Group BB). `autocad_total_length` and `autocad_measure(layer=...)` ask the plug-in's
new Read operation `entity_lengths`; `autocad_count_text` and `autocad_find_text` ask `entity_texts`.
COM stays the fallback, as D-114 sets out. The rules:
(1) **Raw facts, and the tools' own COM code reads them.** The plug-in sends, per selected object in
the order selected, what it read off the .NET object: for `entity_lengths` the class (COM's
ObjectName), layer, length (`Line.Length`, `Polyline.Length`, `Polyline2d.Length`,
`Polyline3d.Length`, `Arc.Length`, `Circle.Circumference`), area (`Curve.Area`, `Hatch.Area`,
`Region.Area`), closed flag and, for a spline or an ellipse, its definition (NURBS data; radii and
parameters); for `entity_texts`, one group per filter asked for (text, mtext, block references), each
object's handle, layer, text (a text's `TextString`, an mtext's `Contents`, formatting codes left in),
insertion point (`Position` / `Location`), block `Name` (the `*U` name, as COM's Name) and attributes
in the reference's own order. The server turns each row into a stand-in object with COM's property
names (`takeoff.PluginEntity`, `text_tools.PluginText`), and the loops that read COM objects read
these unchanged: `curve_length`, `_area`, `autocad_measure`'s loop, `count_text`'s and `find_text`'s.
So a spline or an ellipse is measured by `geometry.nurbs_length` / `ellipse_length` from the same
numbers either way, and nothing about the answer is built twice.
(2) **Only what COM gives.** .NET gives more than COM: an ellipse is `Closed`, a 3D polyline and a line
have an `Area`. A stand-in has only the properties COM has for its class, from `takeoff.COM_FACTS`,
read off AutoCAD's own type libraries (`axdb24enu.tlb`, `axdb25enu.tlb`, `axdb26enu.tlb` list the
same: a 3D polyline has Length and Closed but no Area; an arc ArcLength and Area; a circle
Circumference and Area, no Length; an ellipse Area only; a spline Area and Closed). Reading any other
raises AttributeError, as COM does, so a full ellipse still has no area in `total_length` and a circle
still adds no length in `measure`. `tests/test_plugin_length_text_reads.py` checks the table against
those type libraries when AutoCAD is installed (skipped in CI).
(3) **Read over COM when not sure.** The whole read goes to COM when an object's class is not in the
table (in `measure`, which reads every class; `total_length` asks for the curve classes only), a
number is not finite (the plug-in writes the text "not finite", since its JSON writer refuses NaN), an
attribute is multiline or constant (not yet shown to read the same, BB rows), a group is missing for a
filter asked for, or anything has the wrong shape. These checks come before the loops, whose broad
`except` would otherwise turn a bad row into a quietly different answer.
(4) **An older plug-in.** As D-127: `entity_lengths` and `entity_texts` join `bridge.NEWER_READS`;
1.8.0 and 1.8.1 say they do not have them and the tools read over COM; the capability manifest names
no "faster from" version for these four tools until the release is named.
`_attribute_refs` (`text_tools.py`) is unchanged: `count_text` has its own loop, and the block-attribute
reads move in #198. Rejected: matching the search text in the plug-in (C#'s lower case is not
Python's `.lower()` for every letter, so a match could be missed); measuring splines and ellipses in
the plug-in (the server's own sum would differ in the last digits); a merged "length" fact (the two
tools read different properties: `total_length` takes Circumference, `measure` does not).

## D-128 - Every busy refusal in the block, table, light and copy tools is proven per tool; `save_view(replace=true)` never deletes a layout's view

**Decided:** 2026-11-23, by session S2 of the 2026-11-23 wave ("Yes, next 10"). **Status:** in force; tested offline only, live rows NOT RUN (NEEDS-CHECKING Group AV). Issues [#189](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/189) and [#190](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/190).

**Busy refusals (#189).** The issue listed `except` blocks in `blocks.py`, `tables.py`, `lighting.py` and
`between_drawings.py` that took AutoCAD's busy refusal for "skip that insert", "this cell was not set",
"this AutoCAD has no EXPVALUE", "no block called X" and "nothing with that handle". Reading the code on
2026-11-23 found D-100 (#36, PR #205) had already put `raise_if_busy(exc)` first in every one of them,
and `tests/test_busy_sweep.py` already fails when one is missing. What was still missing was the proof
per tool, which the issue asked for. So no source change was needed there; `tests/test_busy_block_table_light_copy.py`
runs each tool listed with a stand-in drawing that refuses, through the real retry loop
(`connection._with_retry`):
- `autocad_sync_attributes`: 4 inserts, 2 busy (the issue's stand-in) -> "AutoCAD stayed busy", the plug-in is sent nothing; the same for a nested insert, a holder block, a layer lock read and the block look-up ("no block called" is said only when it is really missing).
- `autocad_table_from_excel` (`fill_table`): a busy cell, title, column width or text height -> OUTCOME UNKNOWN, never `not_set` with the table called done. `autocad_set_table_cells`: a busy cell -> OUTCOME UNKNOWN, never listed as refused.
- `autocad_set_render_exposure` and `autocad_list_lights`: a busy read is "stayed busy", not "This AutoCAD did not answer for EXPVALUE ... Nothing was changed" or a null exposure; a busy read-back or write is OUTCOME UNKNOWN.
- `autocad_copy_from_drawing`: a busy handle, owner, block definition or copy is "stayed busy" / OUTCOME UNKNOWN, never "has nothing with the handle(s)" or a shorter list.
Each class has a control: an error that is NOT busy ("Key not found") keeps the old, harmless fallback.
With `raise_if_busy` made a no-op in the four modules, 18 of the 25 tests fail (the other 7 are the controls).

**`save_view` (#190).** The docstring said a layout's view of that name is refused even with
`replace=true`; the code deleted it (`existing.Delete()`, both the window path and `from_screen`). Now
`_refuse_a_layouts_view` runs before the undo mark: a view is the Model tab's only when its `LayoutId`
equals the Model layout's `ObjectID` (or `ObjectID32`), the same test `RenderView.cs` makes for the
camera view. Otherwise it is refused in plain words and nothing is deleted: "'DETAIL-A' is a view of a
layout (a sheet), not of the model, so replace=true does not replace it and nothing was changed. Give
the new view another name."
- **Three cases.** The view is deleted only when its `LayoutId` equals the Model layout's `ObjectID` (or `ObjectID32`). A different, real id is "a view of a layout (a sheet)". A `LayoutId` of 0, missing or unreadable says "AutoCAD did not say which tab the view belongs to": nothing proves it is a model view, so it is not deleted. A busy refusal on those reads goes up as it is (D-100).
- **What is known and what is not.** The type library of this install (`acax26enu.tlb`, read offline on 2026-11-23) has `IAcadView.LayoutId` and `IAcadLayout.ObjectID`, so the members exist. NOT known: what a Model-tab view reports (the Model layout's id, or 0). The issue's pointer to `RenderView.cs` is loose: that file tests `IsPaperspaceView`, not a layout id. If a model view reports 0, `replace=true` is refused for every view: the failure is a refusal, never a deletion. Live rows AV5-AV7 decide it; if AV6 is refused, the follow-up is a plug-in read of the view's paper-space flag (as `RenderView.cs` reads it), not deleting on a guess.
- Without `replace`, the old "already has a view called" refusal is unchanged.

## D-130 - The palette's Undo takes the server's word on the UNDO mark; the gate's answers follow what the drawing holds

**Decided:** 2026-11-23, by session S4 of the 2026-11-23 wave ("Yes, next 10"). **Status:** in force;
tested offline only (bridge tests in `PaletteTests.cs` and `BridgeTests.cs`; Python tests in
`tests/test_gate.py`, `tests/test_busy_refusals.py`, `tests/test_memory_and_checks.py`,
`tests/test_why_and_gaps.py`), live rows NOT RUN (NEEDS-CHECKING Group AX). Issues
[#206](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/206),
[#209](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/209) and
[#244](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/244). Refines D-54, D-68 and D-124; they
are not rewritten.

- **The mark is the server's word (#206).** `end` carries `marked`: true only when the gate really
  put its UNDO mark down before the job. `ActivityLog` sets `Marked` from it at `end`, and only for a
  Change job that is not itself an undo. It no longer works it out from Ask to Keep at `begin`.
  Ask to Keep on is not enough: the gate puts no mark down when AutoCAD is in a command
  (`CMDACTIVE`), when UNDO is off or keeps one step, or when UNDOCTL cannot be read. `UNDO Back` with
  no mark of the job's own goes back to an earlier mark, and the earlier Heron job and the modeller's
  work go with it. A missing `marked` (an older server) or anything but a JSON `true` is no mark, so
  the palette's Undo is `UNDO 1`. D-68's rule otherwise stands: with no mark, a Heron zoom or show
  since refuses.
- **The Keep question's zoom counts as a zoom since.** A job can now be asked Keep or Discard with no
  mark (AutoCAD was in a command). Before, "asked" always meant Back, which took the question's own
  select-and-zoom with it. That zoom (`Showing.SelectAndZoom`, COM `ZoomWindow`, undo recording on) is
  an undo step after the job. So with no mark, `ActivityLog.ShownForKeep` counts it as a view since,
  and the gate keeps `views_since` 1 for `autocad_undo_last`. Both then refuse one step, as for any
  Heron zoom since.
- **A busy AutoCAD is never "no mark".** `_mark()` lets every retryable error up
  (`errors.is_retryable`, wider than the busy refusal it let up before). The retry loop asks again,
  and an AutoCAD still busy ends the call before anything is sent (D-100). Why there is no mark is
  kept, so a Discard that cannot run says the real reason (in a command, UNDOCTL not readable, UNDO
  off) instead of always "UNDO is off (UNDOCTL)".
- **After the erase question brought objects back (#209.1).** `_ask_erase` returns its answer. The
  objects brought back are taken off the count: `heron_changes`, the activity list and the plain line
  count only what is still erased. A Change job with everything back and nothing else counted is
  NOTHING CHANGED, with a sentence saying so. An Admin job (a raw command) stays DONE with the
  "not counted" wording, because a command can change settings that are not counted. This departs from
  the issue's "NOTHING CHANGED" for that one case. In every other case the line ends with what came
  back: all, some ("1 of the 4"), the plug-in's own message when it could only queue the restore (then
  no count changes, because nothing is back yet), or "none came back: look at the drawing".
- **No one-step undo after a restore (#209.1, #244).** The plug-in brings objects back in its own
  transaction after the job, so the last undo step is the restore. `autocad_undo_last` is given
  nothing to undo after any restore. The palette refuses and hides an unmarked Undo for that job
  (`ActivityLog.BroughtBack`, told by the add-in's `AskErase`). With a real mark, `UNDO Back` goes past
  the restore to the mark and is still offered.
- **An empty mark ends the chat's undo (#209.2).** A Change job that put a mark down and wrote nothing
  leaves `_last_change` empty. Its mark is now the newest, so `UNDO Back` for the older job would stop
  there, undo nothing, and with no new handles to check say "undone".
- **`gaps` advice (#209.3).** `outcome_unknown` and `discard_failed` are matched before
  `autocad_busy`. Their messages often say AutoCAD was busy, and "Press Esc, then try again" is the one
  thing not to do after them.
- No protocol version bump: the new field is optional both ways.

## D-129 - Text sent to AutoLISP has every control character escaped; a LISP error is answered at once

**Decided:** 2026-11-23, by session S3 of the 2026-11-23 wave ("Yes, next 10"). **Status:** in force; both parts tested offline only, live rows NOT RUN (NEEDS-CHECKING Group AW). Issues [#207](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/207) and [#157](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/157).

**Control characters (#207).** `lisp_string` escaped only backslash and quote, and its output is typed
into AutoCAD. A text value holding ESC ESC `(startapp ...)` newline could cancel the half-typed
expression and have the rest read as new input. Now every character below 0x20, and DEL, is written as an
AutoLISP escape: `\n`, `\r`, `\t`, and three-digit octal for the rest (`\033`; three digits always, so a
digit after it cannot join it). NUL, the C1 controls (U+0080 to U+009F), U+2028, U+2029 and a lone
surrogate have no octal escape (AutoLISP's stop at 0377) and no safe meaning on the command line:
they are **refused** with a plain message, nothing sent. All other Unicode (accents, Arabic,
Malayalam, Chinese, emoji) passes through as it did. The fix sits in `lisp_string`, so the batch tools
and `autocad_import_pdf` are covered at once; `lisp_path` got the same guard. The code of
`autocad_run_lisp` itself is guarded the same way in `acad/lisp_forms.py`: a control character inside a
string becomes an escape (a multi-line string in one's own code now works instead of typing Enter into
the command line), one outside a string, or a backslash right before one, is refused.
*Not done:* other tools that type text into the command line through `SendCommand` without
`lisp_string` were not reviewed (see the issue filed for them).

**LISP errors (#157).** The wrapper runs the code inside `vl-catch-all-apply` and writes the error
message to USERS1 behind the marker `~E~ `, in the same place a result goes. Chosen over the issue's
second variable because the server then reads one variable, as before: no extra read or set on a
busy AutoCAD, and every stand-in and busy-retry test keeps its shape. `send_lisp_pieces` stops at that
piece; the answer has `lisp_error` (AutoCAD's words), `result: null`, `timed_out: false`, the piece
number and what ran before it; `chunks_finished` does not count it; the first line is NOTHING CHANGED
when the plug-in counted nothing, else OUTCOME UNKNOWN, never DONE (`core/answers.py`).
`autocad_import_pdf` reads the same marker: an error up to its command is a plain refusal, never read as
an import. The cancel of a command left open, and USERS2, are unchanged and still written before USERS1,
so an error with a command left open reports both. The first form of the wrapper clears `heron:r` and
`heron:c`, so an expression AutoLISP cannot read can no longer hand back the previous call's value.
**One cost, decided:** the wrapper grew from about 244 to about 460 characters, and a ~2,400-character
call is known to answer only after the wait (known limit 3). `FORM_MAX_CHARS` went from 2,000 to 1,750
so the longest text sent stays no longer than before; a form of 1,750 to 2,000 characters is now
refused with "split it" instead of sent.
**Not proven:** a `(command ...)` inside `vl-catch-all-apply` (the issue warned it differs on some
versions) and a routine's own `*error*` handler, which the catch bypasses (NEEDS-CHECKING AW4, AW8).

## D-01 - Python server, AutoLISP for bulk work

**Decided:** 2026-08-25. **Status:** in force.
MCP must be served by an outside process, which AutoLISP cannot be. Python hosts the protocol and
typed single operations over COM; AutoLISP is generated for bulk creation and for what COM cannot
reach. Detail: [02](02-architecture.md#why-python-and-autolisp).

## D-02 - One COM worker thread, retry on busy for 10 s

**Decided:** 2026-08-25. **Status:** in force.
COM is apartment-threaded and AutoCAD rejects calls while busy. All COM work runs on one
`CoInitialize`d thread; `RPC_E_CALL_REJECTED` is retried for 10 s, then reported with "press Esc".

## D-03 - One tool call is one undo group; deletes need `confirm=true`

**Decided:** 2026-08-25. **Status:** in force.
Anything Claude does must be reversible with one Ctrl+Z, and nothing is deleted on a guess.

## D-04 - PDF export configures the layout, then plots with the path only

**Decided:** 2026-10-19. **Status:** in force.
The two-argument `PlotToFile(path, pc3)` fails on AutoCAD 2027. Set the layout to the pc3, extents,
fit and centre, plot with the path alone, restore the page setup. Pinned by `tests/test_export.py`.

## D-05 - Repository laid out in parts, like Heron AI

**Decided:** 2026-10-26, on Ajmal's instruction to "rearrange everything like Heron AI" without
changing Heron itself. **Status:** in force.
Folders: `src/autocad_mcp/` (server), `generators/` (was `drawings/source/`), `drawings/<PACKAGE>/`
(outputs only), `tools/` (was `scripts/`), `tests/`, `docs/`, `archive/`. Root carries README,
AGENTS, CONTRIBUTING, SECURITY, CHANGELOG, LICENSE, as Heron does. `src/` was **not** moved: the
editable install and three MCP configs point at it, and moving it means a reinstall
([05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)).
Heron AI was read for its structure only; nothing in it was changed.

## D-06 - Ruff checks the server, not the generators

**Decided:** 2026-10-26. **Status:** in force.
`generators/` and `archive/` are dense one-project drawing scripts with long data lines; they had 126
style findings and no functional ones. Ruff now excludes them (`pyproject.toml`) so CI guards the
server. Tidying the generators is on the [ROADMAP](ROADMAP.md).

## D-07 - Generator paths come from `generators/paths.py`

**Decided:** 2026-10-26. **Status:** in force.
Five scripts carried a typed `D:\06_Development\...` path. They now import `SERVER`, `AHU_OUT`,
`CCTV_OUT`, `ENCL_OUT` from `paths.py`, worked out from the file's own location, so the repository
runs from any folder or PC.

## D-08 - Revit enclosure experiment archived, not deleted

**Decided:** 2026-10-26. **Status:** in force.
`drawings/revit_encl/` sent raw C# to Revit through Heron's bridge pipe. Ajmal stopped that task on
2026-10-22 and said Heron must be used through its own capabilities. Kept in `archive/revit_encl/`
for reference; never build on it.

## D-09 - Private GitHub repository, generated drawings included

**Decided:** 2026-10-26. **Status:** in force.
`Ajmalpshaik/AutoCAD-MCP`, private. DWG, PDF and PNG outputs are committed (about 10 MB) so the
packages are kept with the code that made them. AutoCAD `.bak` / `.dwl` files and the `.venv` are not.
Visibility superseded by [D-10](#d-10---repository-made-public); keeping drawings in git superseded
by [D-11](#d-11---generated-drawings-are-not-kept-in-git).

## D-10 - Repository made public

**Decided:** 2026-10-26, on Ajmal's instruction "make it public". **Status:** in force. Supersedes the
*private* part of D-09.
Checked before switching: no keys, passwords or e-mail addresses in the files or history; the CCTV
package uses a sample client; the pole-enclosure sheet's client, location and consultant are still
`TBC`. **When those TBCs are filled with a real client's details, think before committing them here:
the repository is public.**

## D-11 - Generated drawings are not kept in git

**Decided:** 2026-10-26, on Ajmal's instruction ("why you keep drawings on this repo?? ... remove
this"). **Status:** in force. Supersedes the *drawings included* part of D-09.
The DWG, PDF, PNG and LISP output can be made again from `generators/`, it was about 10 MB against a
small code base, and the pole-enclosure sheet is real site work that should not be public. The whole
`drawings/` folder is ignored (its README too, since 2026-10-26: an empty-looking folder on GitHub
helped nobody), and the files were **removed from the whole git history**
(rewritten and force-pushed the same day, while the repository was one day old with no other copies).
The files themselves stay on Ajmal's PC.

## D-12 - Heron AI for AutoCAD: same family, separate repository

**Decided:** 2026-10-26, with Ajmal ("Heron AI for AutoCAD", repository renamed `Heron-AutoCAD`).
**Status:** in force.
Heron AI's own decisions defer every non-Revit platform "until Revit works properly", and an AutoCAD
plug-in needs its own C# builds, so it lives here, separate. It carries Heron's name, ribbon, padlocks,
banner and wording so a modeller sees one product. When Heron's capability registry is ready, this
repository is offered as its AutoCAD adapter. Heron AI itself is not changed (its icon PNGs were
copied once, read only).

## D-13 - AutoCAD 2021 to 2027, three builds

**Decided:** 2026-10-26, Ajmal chose "2021 to 2027". **Status:** in force.
`net48` for 2021-2024 (R24), `net8.0-windows` for 2025-2026 (R25), `net10.0-windows` for 2027 (R26),
against Autodesk's `AutoCAD.NET` NuGet packages 24.0.0 / 25.0.1 / 26.0.0, in one `HeronAutoCAD.bundle`.
Only 2027 is on this PC: the other versions stay NO MACHINE in [NEEDS-CHECKING](NEEDS-CHECKING.md)
until someone runs them; the docs never claim them as working before that.

## D-14 - The plug-in guards, COM draws

**Decided:** 2026-10-26, Ajmal chose this over rewriting every tool in C#. **Status:** in force.
The plug-in owns connection, padlocks, banner and Keep or Discard; the Python server keeps its COM
tools and asks the plug-in `begin` / `end` / `ask_keep` around every call, from one place
(`tool_errors` -> `core/gate.py`). Tools can move into the plug-in later, one at a time; since
D-40 the plug-in does the operations COM has no call for.
Known limit: COM stays reachable by other programs; the guard binds Heron, not the whole PC.

## D-15 - A write AutoCAD interrupted is never re-run

**Decided:** 2026-10-26. **Status:** in force.
The busy-retry loop re-ran a whole tool. Once `undo_mark` has started a write, a busy signal now
raises `OutcomeUnknown` ("read the drawing back before retrying") instead, so nothing is drawn twice.
Gap: `send_command` / `run_lisp` paths that manage their own undo do not mark the write; on the
[ROADMAP](ROADMAP.md).

## D-16 - A broken padlock file means padlocks off, banner on

**Decided:** 2026-10-26. **Status:** in force.
An unreadable `heron-autocad.config` turns every padlock off (fail closed) but keeps the activity
banner on, because the banner is what shows the modeller that Heron is working.

## D-131 - Only this Windows user's AutoCAD stops the setup; checksums use LF; the bundle has no .pdb

**Decided:** 2026-11-23, Ajmal's "Yes, next 10"; closes
[#185](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/185) and
[#232](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/232). **Status:** in force; offline tests
(`tests/test_installer_polish.py`, `tests/test_installer.py`) and `Check-Setup.ps1` in `release.yml`;
the live row on a shared server (AY1) NOT RUN.

- **#185.** The "is AutoCAD running" check in `Install.ps1` and in the Inno setup counts an `acad.exe`
  only when its owner (Windows' `Win32_Process.GetOwner`) is the user running the install. It does not
  filter by session: your own AutoCAD left in a disconnected session of yours still holds your plug-in
  files, so it still stops the install. An owner Windows will not say is treated as ours (the setup),
  or as ours only from our own session (`Install.ps1`); a process list that cannot be read at all falls
  back to "any acad.exe", so the check refuses too often rather than too rarely. The server check
  (`autocad-mcp.exe` in Heron's folder) is unchanged.
- **#232.** `checksums.txt` is written with LF line endings, so `sha256sum -c` works off Windows. The
  `.pdb` debug files are left out of the plug-in bundle (`build_plugin.make_bundle`); `make_release.py`
  stops the build if one is in the release folder, and `Check-Setup.ps1` fails if one is in the release
  folder or the installed plug-in, or if `checksums.txt` has a carriage return.
- No version bump: this ships with the next release.

## D-127 - Block counts are read by the plug-in in one go; every dynamic property value carries its type

**Decided:** 2026-11-23, on issues #192 and #194 (ranks 1 and 3 of #74), under D-114. **Status:** in
force. `autocad_count_blocks` asks the plug-in's `block_references` and `autocad_list_blocks` asks
`block_definitions`, both at Read; COM stays the fallback, as D-114 sets out. The rules:
(1) **Raw facts, one builder.** `block_references` sends each selected block reference in the order
selected (the INSERT filter COM selects with), with its real name (COM's EffectiveName: the dynamic
block's own name for a `*U` copy, the reference's name when that is blank), its layer and every
dynamic property in AutoCAD's order as `[name, read_only, kind, value]`; with `nested`, the block
references inside each definition that is neither a layout nor an xref. `block_definitions` sends
each named definition's entity count, xref flag and path, dynamic flag and attribute tags, and with
`counts` the references per real name in their own case. The server picks the visibility state and
the properties counted by (`takeoff.block_ref`), skips and orders the listing
(`layers.block_info`) and matches names without case with the same code as for COM. The plug-in
skips only what the listing never shows anyway: layouts and names starting `*`.
(2) **A value goes with its type.** The plug-in's JSON writes a whole-number double as `50`, which
Python reads as an int while COM gives `50.0`, so a count by size would split in two. Each value is
`real`, `int`, `text`, `point`, `none`, `error` (AutoCAD would not give it) or `other` (a type the
server does not know). The server turns each back into COM's type. A value it needs that is
`other` sends the whole read to COM; an `error` it needs skips that reference, as a failed COM read
does. A value it does not need (read-only, not a visibility state) is never looked at, as over COM.
(3) **An older plug-in.** No new version constant: 1.8.0 and 1.8.1 pass `READS_SINCE` but say they
do not have these operations, and `faster_read` reads that as "use COM" (one wasted pipe call). The
release that carries them is not known yet, so `bridge.NEWER_READS` names them, and the capability
manifest gives these two tools no "faster from" version until the release is named. An answer
without the `children` or `instances` it was asked for, or of the wrong shape, is not used.
Rejected: a reply grouped by identical references (smaller, but its order differs from COM's, so
"same answer" would rest on an argument instead of a test); counting in the plug-in by block name
(`*U` copies and the server's case rules would differ). Live rows: Group AU, all NOT RUN.

## D-126 - The setup finds the Claude app's own Claude Code and settings, and never replaces an entry

**Decided:** 2026-11-22, after AK13 failed with setup 1.8.0 on a PC where Claude is only the
Claude desktop app ([#233](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/233)); Ajmal said
"Yes, fix #233" and ship it as 1.8.1. **Status:** in force; offline tests
(`tests/test_install_connect.py`) and `Check-Setup.ps1` in `release.yml`; on the owner's PC AK15
(dry run) and AK16 (the Code tab connected, his source folder still on its `.venv` server) PASS;
AK13 (a whole setup on a Claude-app-only PC) NOT RUN.

`Install.ps1 -Connect` looked only for a `claude` command and for `%APPDATA%\Claude`. The Microsoft
Store Claude app has neither: its Code tab runs its own `claude.exe` from
`%LOCALAPPDATA%\Claude-Data\<package>\claude-code\<version>\...`, it keeps
`claude_desktop_config.json` in `%LOCALAPPDATA%\Claude-Data\<package>`, and the `%APPDATA%\Claude`
a program inside the app sees is its private copy, holding only a `.user-data-left.<package>` note.
Seen on the owner's PC, from a terminal outside the app, which sees the real disk.

- **Claude Code** is found as the `claude` command (never a Windows app alias), then
  `%USERPROFILE%\.local\bin\claude.exe`, then the newest `claude.exe` under a Claude app data
  folder's `claude-code`. The entry is added with that program's own
  `claude mcp add --scope user autocad -- <server>`, run from Heron's folder, never by editing
  `.claude.json`: running Claude sessions write that file all the time. It is read back after, and
  "connected" is said only when it starts this server.
- **Claude Desktop**: `claude_desktop_config.json` in each app data folder that has one
  (`%LOCALAPPDATA%\Claude-Data\*`, and an older Store app's
  `Packages\AnthropicPBC.Claude_*\LocalCache\Roaming\Claude`), and `%APPDATA%\Claude` as before. A folder with a `.user-data-left.*` note is
  skipped. **While the app holds its `lockfile` (it is open) its file is not written**: the app
  rewrites that file itself. The Code tab is connected anyway, through `claude mcp add`. Written
  with `ConvertTo-Json -Depth 100`, not 10, so the app's deeper settings come back whole.
- **An `autocad` entry already there is never replaced** (1.8.0 replaced it): it is left and named.
  **Only an entry that starts this server is removed** (1.8.0 removed any `autocad`, in every
  scope), so a developer's `.venv` entry survives an uninstall.
- Every file is saved as `<name>.heron-backup` just before it changes, and only then.
- Nothing found: the report gives the exact entry and where it goes, instead of "not found, skipped".
- `-DryRun` with `-Connect` or `-Disconnect` says what would change and changes nothing; it runs
  even with AutoCAD open, since it changes nothing.
- `.claude.json` is read with .NET's `JavaScriptSerializer`: Windows PowerShell's `ConvertFrom-Json`
  refuses keys that differ only in case, which project folders on Windows can be.

Not done: no Start menu entry to connect again (running the setup again does it), and nothing reads
`CLAUDE_CONFIG_DIR` beyond where `.claude.json` is.

## D-125 - Sheets follow the tab on screen and are never left turned; a tab switch is not an erase

**Decided:** 2026-11-22, after the SAC2 split AC set was drawn live (AutoCAD 2027, server 1.10.1,
plug-in 1.8.0). **Status:** in force; live rows AF19-AF24, all NOT RUN. Five things went wrong:

- **Every viewport was refused** "AutoCAD refused it (InvalidInput)". The add-in log named the line:
  `Viewport.StandardScale = CustomScale`, which AutoCAD refuses (custom is what `CustomScale` sets by
  itself). The line is gone. Until a plug-in with that fix is installed, the server makes the
  viewport over COM (row D16's PASS route) when the plug-in's answer is "AutoCAD refused it (" -
  the plug-in aborted, so nothing is made twice. A clipped viewport (plug-in only) and Heron's own
  refusals (padlock, bad layer name, HERONSTOP) are still the answer. The MVIEW + ZOOM xp LISP that
  worked by hand is not built in: it needs Admin and leaves a command open if one prompt is wrong.
- **An A1 landscape sheet read back 594 x 841 with a 90 degree plot.** A new layout kept the
  template's plot rotation while taking the 841 x 594 medium. The medium is already picked the
  right way round, so a new sheet's plot is now **never turned** (`SheetMath.PlotTurned` /
  `plot_turned`: only a medium the plotter offers one way round only is turned), in the plug-in,
  in `autocad_page_setup` (when an orientation is passed) and, for plug-in 1.8.0, by the server
  afterwards over COM; a busy AutoCAD there is a note, never a failure of a sheet already made.
  `orientation` alone now turns the same sheet size round instead of being ignored. A turned sheet
  says so (`plot_turned_note`) and a sheet not the way round asked is warned. **Left open on
  purpose:** for a sheet that *is* turned, the plug-in's read swaps the sides (Autodesk's
  GetMaximumExtents rule) and the COM read does not. The one live fact (841 x 594 on screen at 90
  degrees) agrees with the COM read, so it is not changed blind; AF20 and AF21 decide which side
  is wrong. New sheets are not turned, so both agree on them.
- **The preview plotted SAC2-102 while SAC2-104 was on screen.** COM's `ActiveLayout` had not
  followed the tab the plug-in put up. The preview, the PDF export and every sheet tool with no
  layout named now take the tab from CTAB, and a plot first makes that tab COM's active one (it is
  already on screen, so nothing visible changes) and says so (`layout_note`).
- **A run_lisp that only set CTAB said "8 changed, 1 erased" and asked the erase question.**
  AutoCAD turns viewports off and on, and may erase and remake a sheet's paper-space viewport, as it
  switches tabs. Between AutoCAD's "CTAB changing" and "CTAB changed" events (`TabSwitchWindow`,
  a window that shuts by itself after 5 s) the add-in leaves **viewports** out of the change count;
  every other object is still counted, so a lost event can never hide a real erase of the
  modeller's work. Which object was erased on 2026-11-22 was not logged (the modeller
  kept it erased); AF23 records it. `JobChanges` itself is not changed.
- **`dimension_run` mode='overall' said `"total": 0`.** The total added up chain dimensions only;
  it is now the chain's sum, or else the longest dimension in the run (`run_total`).

The P-trap block whose polyline looked grey was checked: `autocad_make_block` copies the members
as they are and sets only the insert's layer, so it changes no member's colour or layer. A member
on layer 0 or ByBlock takes the insert's layer (the current one when `layer` is not given), and a
thin line in a preview can look grey. AF24 checks it once; nothing was changed for it.

## D-120 - A layer standard is a CSV the office fills on its own PC; Heron ships only a generic example

**Decided:** 2026-11-22, for issue #70. **Status:** in force; live rows Group AT, all NOT RUN. Builds
on D-92 (the reference drawing) and D-64 (a pass says against what).
The owner's office layer standard cannot go into this public repository, and his list is not
available here anyway. So the standard is a **rule file the office fills**, and Heron ships only an
example:
- **The format** (`acad/layer_standard.py`): one row per layer, columns `layer, color, linetype,
  lineweight, plot, description, replaces, required`. A layer is a full name or a pattern with `*`
  and `?` (`M-*-IDEN`: checked, never a target). `replaces` is the old layer names the row takes
  over, separated by `;`. A blank cell is not checked. `# name:`, `# name_pattern:` (a regular
  expression for layers the list does not name) and `# example: yes` are read from `#` lines. The
  same rows as JSON are what Heron keeps once a CSV is imported. Colours are the AutoCAD Color
  Index (1-255) or a name; a true colour is refused in plain words, not guessed.
- **A CSV, because that is what the owner has.** His list is in Excel; Excel saves CSV with a BOM,
  in the Windows code page, or with `;` in some regions: all three read. A CSV with any problem
  imports nothing, and every problem is named with its row number at once.
- **Where it lives, and which wins:** a file the modeller names in the call (`layer_standard=
  "S:\CAD\layers.csv"`), else the office standard imported on this PC
  (`%LOCALAPPDATA%\Heron\autocad\standards\office-layers.json`, the previous one kept beside it),
  else the generic MEP example in `src/autocad_mcp/data/layer-standard-example-mep.csv`.
  `autocad_layer_standard` writes only that folder and reads only the CSV it is given, never
  AutoCAD: it is a Read tool that answers with AutoCAD closed (`NO_AUTOCAD_TOOLS`), as
  `autocad_checklist`'s own lists need no padlock (D-52).
- **`office` with none loaded never passes.** A check falls back to the example so the findings
  are still useful, but `passed` is null unless another rule failed: the modeller asked about his
  office's standard, which is not there (D-64). A **remap** with none loaded is refused: it would
  move objects onto layers nobody chose. `example` must be said by name to remap with it.
- **The example is generic and says so**: mechanical, plumbing, fire and electrical layers in the
  discipline-major-minor style of the US National CAD Standard's layer guidelines, picked for the
  example and not copied from that list; marked `# example: yes`, which `import` refuses, so it can
  never become an office's standard by accident.
- **The remap from a standard**: first every standard layer as itself (what is on it stays, the
  layer gets the standard's colour, linetype, lineweight, plot and description), then every pattern
  row as a **keep** rule (a new remap key, `keep: true` in place of a target `layer`: what it
  matches stays on its own layer, which gets the row's properties), so a layer the check accepts
  through a pattern is never taken by an old name such as `*CHWS*`; then each old name a row
  replaces, in file order, matched on the **layer** only, never a block's name. A plain old name a
  pattern row covers is refused at import, as one that is a standard layer is.
- **Left for later, on a need:** true colours, transparency and plot style names in the standard;
  keeping the standard on a shared office folder as the check lists do (D-93) - for now each PC
  imports the CSV.

## D-122 - Heron AI gets a capability manifest made from the code; its registry is not built yet

**Decided:** 2026-11-22, for issue #75 (D-12). **Status:** in force; no runtime change, no live rows.
D-12 offers this repository to Heron AI for Revit as its AutoCAD side once Heron's capability
registry is ready. That registry does not exist yet, and Heron AI is never edited from here, so
this side does only what it can on its own:
- **A manifest, not a second list.** `tools/export_capabilities.py` writes `dist/capabilities.json`
  from the live registry, `core/risk.py`, the tools' own code and `docs/NEEDS-CHECKING.md`: each
  tool's padlock, kind, `Use when` lines, inputs, what it needs of the plug-in and its proof state.
  Nothing in it is typed by hand, so it cannot drift. It is not kept in git (other sessions add
  tools all day; a committed copy would be stale or a merge conflict on every PR); every release
  zip carries it instead.
- **Proven means a PASS row that names the tool.** A row that says "draw a line" in words does not
  count: the safe way round. PASS / PARTLY / NOT RUN / FAIL / NO ROW, with the rows, so a registry
  can tell proven tools from unproven ones.
- **The plug-in a tool needs is read from its code** (`ast`): reaching `in_plugin` or
  `plugin_runner` means the plug-in does part of the work; reaching only the faster reads, quiet
  input or a named button means it is used when there; anything else is only gated. The operation
  names are checked against `PluginOperations.cs`. Which plug-in release first had each operation
  is not recorded, so `version_needed` is the plug-in built from the same code.
- **The gate and padlocks stay in the AutoCAD plug-in** (D-14, D-59). Heron AI would be one more
  MCP caller of the same server.
- **Fixed on the way:** `autocad_list_materials` only reads but was not marked read-only for MCP
  clients; it is now, and a test keeps every Read tool marked so (except `autocad_project_notes`
  and `autocad_use_autocad`, which keep notes and the chosen AutoCAD).
- **Rejected for now:** an `autocad://capabilities` resource. It would be runtime behaviour, and
  the register it reads is not in an installed server; it comes when Heron's registry asks for a
  live answer. Issue #75 stays open until Heron's registry lists these tools.
  Design and the steps: [14](14-heron-ai-adapter.md).

## D-123 - The erase question can be switched off in Settings; it is on at every AutoCAD start

**Decided:** 2026-11-22 by Ajmal PS. **Status:** in force; amends D-50 (the erase question) and adds a
fifth switch to D-44's Settings window. D-59 stands: nothing is read from or written to a file.
While Claude re-placed labels and dimensions it had just drawn on a split AC detail set, every
delete-and-redraw brought up "Heron erased 2 objects" (D-50). Ajmal asked for a setting so it does not
ask every time.
- **A fifth switch in Settings: "Ask before keeping erased objects"** (`Padlock.EraseQuestion`, and the
  command `HERONASKERASE`). ON (green, as Ask to Keep) asks as before; OFF keeps what a job erases
  without the box. Like Ask to Keep, switching the question **off** is the risky side, so that is what
  asks first ("Stop asking before keeping erased objects?"); switching it back on never asks.
- **In memory only; no file remembers it.** Any file or registry key the modeller's account can
  write, a chat can write too, and a chat that can switch the erase question off approves its own
  deletes, which is exactly what D-50 and D-59 stop.
- **Remembered only through the administrator's key** (Ajmal chose this, 2026-11-22): DWORD
  `AskBeforeErasing` = 0 under `HKLM\SOFTWARE\Policies\Heron\AutoCAD` (D-60's key) starts the erase
  question **off** at every AutoCAD start on that PC. Only an administrator can write HKLM, so a chat
  (which never runs elevated) cannot. It is **not a hold**: the modeller can click it on, and a
  click wins until AutoCAD restarts. Until a click it follows the key as it is now, so setting or
  deleting the value applies at the next job. Any other value, or none, starts it on. Settings says
  "This PC's administrator setting starts it off"; the answer's note names the key (`offBy:
  "policy"` from the plug-in), never Settings.
- **The plug-in decides, not the server.** The server still asks `ask_erase` after every job that
  erased something; `BridgeProtocol.AskErase` reads the switch and, when it is off, answers
  `keep_erased` with `"asked": false` without showing the box. A Read or View job still cannot ask.
- **The answer stays honest (D-62).** The first line still counts what was erased ("DONE - 0 added, 0
  changed, 2 erased."); the note says they stay erased **without asking** because the erase question
  is off in Settings, and never "the modeller chose". `ping` reports the switch (`eraseQuestion`);
  a plug-in of 1.8.0 or older does not send `asked` or `eraseQuestion`, and is read as asking, which
  it always does.
- **Unchanged:** Keep or Discard (Ask to Keep on) still covers an erase; a dry run still takes it all
  back; `autocad_undo_last` still asks nothing. Ctrl+Z still brings back what a job erased.

## D-124 - The Activity palette shows Select, Zoom and Undo only where they can act

**Decided:** 2026-11-22, from Ajmal's report: a "Save Drawing ... done, made 0, changed 0, erased
0" card offered Select, Zoom and Undo. **Status:** in force (built and tested offline; live rows
X26-X28 in [NEEDS-CHECKING group X](NEEDS-CHECKING.md), NOT RUN); refines D-68.
Every finished card used to carry all three buttons, and a press on a save or an export only said
"nothing to show" or "a raw command is never undone here". Now each card gets only the buttons that
can act, decided by `PaletteRows.Buttons` in the bridge (tested offline), and a card with none gets
no button row at all (hidden, not greyed).
- **Select and Zoom** when the job has objects to show (what it made or changed, `ShownHandles`),
  is not running, was not undone from the palette and was not discarded. A failed or "outcome
  unknown" job that left objects keeps them, as `CanShow` already allowed.
- **A dry run gets no buttons.** The server ends it as `dry_run` (D-63) with the counts of what it
  took back, so its handles point at objects already gone. `CanShow` now refuses it too ("This was
  a dry run: Heron took it back at once ..."), and its card reads "dry run, taken back" instead of
  "stopped (dry_run)".
- **Undo** only on Heron's **newest** job, and only when it is a Change job (never a save, export,
  publish, raw command or AutoLISP) that ended `done`, was counted and changed something, is not
  itself an undo, and, with no UNDO mark, has no Heron zoom or show since: exactly the parts of
  D-54's rule in `CanUndo` that depend on the job alone.
- **Still checked on the press, with the reason said:** another job running, an Undo already
  waiting, the job's drawing not in front, a change by the modeller since, and UNDOCTL. They can
  change without the list being drawn again, so hiding on them could show a stale button or hide a
  good one. Every input of the new rule (a job beginning or ending, an Undo) already redraws the list.
- A test pins the two together: for each kind of job, as Heron's newest, a button shows exactly
  when its press, with nothing else in the way, would be allowed.
- **Number:** D-123 went to the erase-question switch, made the same day in a parallel pull request.

## D-113 - Offset, taper, move and delete faces, imprint and separate are plug-in operations; one face tool with an action

**Decided:** 2026-11-21, for issue #184 (part 3 of #119). **Status:** in force (built and tested
offline; live rows in [NEEDS-CHECKING group AR](NEEDS-CHECKING.md), NOT RUN); extends D-40. COM has
none of SOLIDEDIT's face or body options, so each is a listed plug-in operation, Change level, one
transaction: `offset_faces` (`Solid3d.OffsetFaces`), `taper_faces` (`TaperFaces`), `move_faces`
(`TransformFaces` with a plain move), `delete_faces` (`RemoveFaces`), `imprint_solid`
(`ImprintEntity`) and `separate_solid` (`SeparateBody`). Every call was checked in Autodesk's AutoCAD
.NET reference (the AutoCAD.NET package's own documentation file) before it was written, and the
plug-in compiles for all three builds.

- **Faces are picked as the other solid edits pick them**, from the Brep built from the solid's
  FullSubentityPath (the D-40 fix): a word that goes by the solid's box, or the numbers
  `autocad_list_solid_faces_and_edges` gives. The four face edits are **one tool**,
  `autocad_edit_solid_faces`, with an `action`: they take the same solid and the same faces, and
  four more tools of nearly one shape would make the list harder to search. An option the action
  does not take is refused, never quietly ignored.
- **Taper pivots at the bottom of the picked faces** unless a base point is given: the plane square
  to the draft direction (up by default) through their lowest point, so the bottom edges stay where
  they are, as SOLIDEDIT Taper does from a base point at the bottom. Which way a positive angle
  leans is SOLIDEDIT's (in) by intent but not proven for the API: the answer carries the volume
  before and after, and row AR9 settles it. Rotating faces (SOLIDEDIT Face Rotate) is not built:
  it was not in #119; `TransformFaces` takes a rotation, so it is a small step later.
- **Imprint keeps the objects**, as SOLIDEDIT does by default; erasing them goes through Heron's
  own erase, which asks. The tool counts the faces after (a second, read-only call), because an
  object that does not touch the solid imprints nothing and AutoCAD does not say so.
- **Separate** leaves the solid holding one piece and adds the others as new solids with its
  properties (`SetPropertiesFrom`). A solid that is one piece already is refused, nothing changed.

Rejected: typing SOLIDEDIT (it waits for picks on screen, as D-40 found for FILLETEDGE); one
operation that takes any face edit by name (each is listed and checked on its own, as D-40 asks).

## D-112 - A pyramid is AutoCAD's CreatePyramid, turned and placed; a polysolid is built, because the API has none

**Decided:** 2026-11-21, for issues #182 and #183 (part 3 of #119). **Status:** in force (built and
tested offline; live rows in [NEEDS-CHECKING group AR](NEEDS-CHECKING.md), NOT RUN); extends D-40.
Neither PYRAMID nor POLYSOLID has an ActiveX call, so both are plug-in operations (`add_pyramid`,
`add_polysolid`), Change level, one transaction, in their own add-in file (`SolidPrimitives.cs`).

- **Pyramid.** `Solid3d.CreatePyramid(height, sides, radius, topRadius)`. Autodesk's reference says
  the radii are of the circle **inside** the polygon (to the middle of a side) and that the solid is
  made about the origin, half way up. Heron does not lean on the rest: it reads the corners AutoCAD
  made (a Brep of the solid before it is in the drawing: only points are needed), turns the solid
  so one side faces the front (as a box sits, as `autocad_add_solid` places its shapes), and moves
  it so the base point is the centre of its base. If the corners say the radius was read another
  way, it is made again to the size asked for. A hopper (top wider than the base) is made the usual
  way up and turned over. `radius_to='corner'` takes a size across the corners. 3 to 32 sides, as
  PYRAMID allows. The answer gives the volume AutoCAD measured and the one the sizes should give.
- **Polysolid.** Checked in the reference: `Solid3d` has no polysolid call. So Heron builds the
  same solid: the path offset to each face of the wall (`GetOffsetCurvesGivenPlaneNormal`), the two
  joined at the ends (an open path) or one ring inside the other (a closed one), made a region and
  extruded straight up. The path must be flat in plan and is kept (as DELOBJ off). Which way
  AutoCAD's offset goes is read off the path, never assumed: the offset point nearest a point just
  along the path from its start is on its left or its right. `side` is center, left or right (looking
  along the path from its start), or inside / outside of a closed path, worked out from which way
  the path runs. A path that turns tighter than the wall is wide, or crosses itself, is refused.
  Points can stand in for a path; they make a temporary polyline that is never added. A path that
  ends where it starts but is not closed (PLINE back to the first point without C) is closed on a
  copy; the drawing's polyline is left as drawn. Fixes from an independent review: that case, a
  probe for the offset's direction kept small so a small ring cannot fail it, and the open wall's
  ends joined to the nearer ends.
- The sums (pyramid turn and volume, left of a path, inside of a ring) are pure, in
  `Bridge/SolidShapeMath.cs`, and tested offline.

Rejected: typing POLYSOLID (it waits for points or an object picked on screen); a sweep of a
rectangle along the path (corners and arcs come out less predictable than an offset outline, and a
closed path needs its own case anyway).

## D-106 - PDF Import types -PDFIMPORT with every answer in one form, through autocad_run_lisp's sender

**Decided:** 2026-11-21, for issue #113. **Status:** in force; live rows Group AO, all NOT RUN.
`autocad_import_pdf` (Change) brings one page of a PDF in as lines, text and hatches.
- **No API.** Neither COM nor .NET has a PDF import (Autodesk on its .NET forum, 2019; nothing
  since). Attaching an underlay and converting it in the plug-in is no better: it still has to run
  the same command, with more questions (area, then Keep / Detach / Unload). So the command is
  typed, as the ribbon audit said ([12](12-autocad-ribbon-coverage.md)).
- **One form, every answer.** `(command "_.-PDFIMPORT" "_File" <path>)`, then page, point, scale
  and angle, each given only while CMDNAMES still says PDFIMPORT, so a command that ends early
  never gets the rest typed at the Command prompt. The path is one LISP string, so a space in it is not an Enter; the point is a LISP
  list in the current UCS; the angle is degrees, with AUNITS, ANGBASE and ANGDIR set to 0 for the
  call. It goes through `advanced.send_lisp_pieces`, the sender `autocad_run_lisp` now uses too:
  object snaps off, a command still asking is cancelled and named (known limit 21), the pieces
  after it are not sent, one undo step. Nothing is loaded from a file (D-21).
- **Checked first, refused plainly:** a missing file, one not a PDF inside, a page past the last
  (read only from the page tree's root, in the file or its object streams; anything less sure means
  AutoCAD answers), a release not 2021-2027 (ACADVER: an answer to the wrong question lands at the
  next prompt), an AutoCAD with no PDFIMPORTMODE, a tilted or flipped UCS. A busy AutoCAD is asked
  again, never called "no PDF Import"; a setting it was too busy to put back is named, and then the
  call is not asked again (it would read Heron's values as his).
- **What comes in** is set for the call and put back: FILEDIA 0 (the file name on the command
  line), PDFIMPORTFILTER from `what` (bits leave out 1 geometry, 2 TrueType text, 4 fills; 8
  pictures always: AutoCAD writes each picture out as a file, which a Change tool must not do),
  PDFIMPORTMODE with bit 1 (one block) off and bit 8 (fills as hatches) on, his lineweight and join
  bits kept.
- **What came in** is walked in LISP from the object that was last before the command: counted
  by type, boxed, and moved onto `layer` if given (made only after the command finished, so a
  cancelled import leaves no layer). The PDF layers AutoCAD made are named, for a purge.
- **Not proven:** the six questions and the variable bits were read from Autodesk's help through a
  search, because help.autodesk.com could not be opened from this session; whether a one-page PDF
  still asks for the page is the first thing AO1 checks. How big a page comes in at scale 1 is not
  said until AO9 measures it.
- **By hand**, if a row fails: Insert > Import > PDF Import, pick the file and the page, untick
  Specify insertion point on-screen or pick it, set the layers option, OK.

## D-118 - The live-check runner measures the later groups, never moves a padlock, never answers a box

**Decided:** 2026-11-21. **Status:** in force. Adds to the runner's own design (`tools/live_check.py`,
groups D, E and F).
`tools/live_check.py` now also measures the rows of groups M to Z, AA to AP and RV that a script can
judge: a count, a size, a refusal's words, a value read back with another tool. One file per area
(`live_check_edits.py` AA, `live_check_layers.py` AB, `live_check_blocks.py` AC and Y,
`live_check_render.py` AE, `live_check_drawing.py` AP and AM, `live_check_mep3d.py` AH, `live_check_styles.py` AN and AL, `live_check_ribbon2.py` AQ, `live_check_cleanup.py` AD, `live_check_reads.py` AS and AO,
`live_check_heron.py` M to Z, AG, AJ and RV), sharing `live_common.py`.
- **The padlocks come first, and are only read.** Since D-59 every AutoCAD starts with them off. The
  runner reads them from the plug-in before anything else: Changes off stops it with "Turn Changes on
  in Settings", Ask to Keep on stops it too (every change would wait for a click the runner cannot
  give). Nothing is run and nothing is written. It never types HERONCHANGES or anything like it.
- **A row may need Admin or Publish on, or off** (`needs` on the row). When the padlock is not so, the
  row is said as "not run this time: it needs ..." and its result in the register is left alone.
- **A NOT RUN reason never wipes a result written by hand.** It is written only over a row that says
  NOT RUN already; a PASS, a FAIL or NO MACHINE stays (`live_results.kept_by_hand`). Before this, the
  by-eye reasons of D12 and D20 would have overwritten their hand-recorded results.
- **A row that erases is not scripted.** Erasing an object (or a layer: the plug-in counts symbol table
  records) brings up Heron's "keep them erased?" box (D-50), which the runner cannot answer. Such rows,
  and rows needing an eye, a click in a Heron window, a restart, the registry, a second AutoCAD or
  HERONSTOP, are NOT RUN with the reason `--list` prints. A few older D-F rows erase too (a boolean, a
  slice): the run then waits for that box, and the runner says so before it starts.
- **Its own drawings only.** Rows that need a saved drawing save the scratch drawing, or another new
  one, into the runner's own folder in %TEMP%; everything it opened is closed without saving and the
  folder removed at the end. A check list, saved command or project note a row makes has an `lc-`
  name and is deleted by the same row. "By hand" steps (a line the modeller draws, a true colour set
  in Properties) are done straight over COM, outside Heron, and named as such.
- **Offline, every check is judged both ways.** `tests/live_fakes.py` plays recorded answers into each
  check, binding every call's arguments against the real tool, and failing on any call not recorded;
  each new row has a good recording that must PASS and a bad one that must FAIL. That proves the
  judging and the arguments, not AutoCAD.
- **Found on the way:** V1, V4 and V7 send OPEN, CLOSE and PURGE through `autocad_send_command`, which
  refuses all three before sending, so their box can never open ([#213](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/213)).
## D-116 - What the review of the 2026-11-21 merges changed, and what it left to issues

**Decided:** 2026-11-21, review of PRs #99 onward (PR #186). **Status:** in force; adds to D-29, D-66,
D-69 / D-75, which stand. Nothing Ajmal decided changes (D-59, D-60, D-73, #158).
- **A sequence step may not move the work** (D-29): `autocad_switch_drawing`, `open_drawing`,
  `create_drawing`, `check_folder`, `use_autocad` and `undo_last` are refused as steps, before
  anything runs. Inside a sequence the gate checked one drawing and put its UNDO mark there, so a
  later step must land in that drawing; `undo_last` as a step would take back the sequence's own work.
- **The dialog watch forgets a job whose end never came** (D-66, D-74): a new job's begin drops an
  earlier one (one job runs at a time in an AutoCAD), and a job older than 20 minutes stops counting.
  Before, a server stopped mid-job left the watch on outside any job and an Admin job's named
  button armed for later jobs.
- **Excel** (D-69, D-75): an error cell (`#N/A`) is never written; exported data cells are formatted
  as Text, so Excel keeps what the modeller types ("0051", "1:100"); a row is named by its Excel row
  number; a cell reference with no column letter is refused, as D-75 already said.
- **Checks that could pass for the wrong reason:** the tool-finder floors are back at the margin
  their comment states, a tool listed under two levels in `core/risk.py` fails the structure check,
  and the folder-close test now reaches the code it tests.
- **Left to issues, in areas other sessions are changing:** #189-#191 and #206-#212 (the palette
  Undo's guessed mark and the batch text escape first). Live rows: Group RV (NOT RUN).

## D-114 - A read over the whole drawing may move into the plug-in for speed; COM stays the fallback

**Decided:** 2026-11-21, on issue #74 ("move tools into the plug-in one at a time where it pays
off, keeping COM as the fallback"). **Status:** in force; extends D-14 and D-40. D-40 moved a job
into the plug-in only when COM has no call for it. Now a tool may also move when COM can do it but
only one round trip per object: a read over the whole drawing or a layer, and later a change that
needs one transaction. The first two: `autocad_list_entities(summary_only=true)` (plug-in operation
`count_entities`) and `autocad_get_extents(layer=...)` (`entity_extents`), both at Read. The rules:
(1) the plug-in selects with the same DXF filter COM selects with (`acad/selection.filter_pairs`,
all of the drawing as ssget "X" takes it) and hands back raw facts: the class name COM gives as
ObjectName, the layer, unrounded corners. The server builds the answer from either path with the
same code, so it is the same either way; offline tests compare the two as text. (2) COM is kept,
and used when the plug-in is not in the job, is older than `READS_SINCE` (1.8.0, read from its
address file), says it does not have the operation, or could not do the read. A stop, "Outcome
unknown" or another chat's hold is said, never read again over COM. (3) The answer does not say
which path read it, so a chat never acts differently because of it; the plug-in's log names each
operation, for the live check. (4) One tool at a time, each with its own issue and PR, in the order
of [13](13-moving-tools-into-the-plug-in.md), and never a tool another session is changing.
`READS_SINCE` assumes the release that carries these reads is 1.8.0; a test fails if the plug-in
version is bumped to anything between. Rejected: a general "read any property of every object"
request (a second COM in JSON, with nothing to check what it reads), and dropping the COM path (an
older plug-in, or one whose read fails, would lose a tool that worked). Also from this: a layer
holding only rays or construction lines now says it has no extents, on both paths, instead of
answering Infinity.

**Added 2026-11-22 (#193):** `autocad_drawing_report`'s model space count goes the same way:
`count_entities` with `space: model` walks model space in COM's own order with the same cut-off,
and its answer says `"space": "model"`; an answer without it (a plug-in that ignored the option)
is not used, and COM counts instead.

## D-111 - Tiled viewports and hyperlinks are COM; DWF goes the PDF way; the geographic location is the plug-in's and shares the sun's place

**Decided:** 2026-11-21, part 2 of issue #119, split into #176, #178, #179 and #180. **Status:** in
force.
- **Tiled model viewports** (`autocad_tiled_viewports`, #176, a **View** tool: the screen, not the
  drawing, so no Changes padlock). COM: `Viewports.Add("Heron")`, the view on screen copied onto it,
  `Split(n)`, then `ActiveViewport =` it (a split shows only once its viewport is made active).
  The named configuration "Heron" is kept (VPORTS > Named) and replaced the next time; it is not
  deleted after use, as deleting a configuration just made active is untried. The
  `AcViewportSplitType` numbers (two horizontal 0 ... four 8) were read from Autodesk's own interop
  assembly (`Autodesk.AutoCAD.Interop.Common`, AutoCAD 2025), not guessed. The answer reads the
  `*Active` tiles' corners back and `acad/tiles.py` says in words what AutoCAD built; a split that
  came out another way is a warning. Model tab only: on a layout it is refused and points at
  `autocad_add_viewport` (paper space belongs to the sheets tools). First named
  `autocad_model_viewports`: the word "model" then won searches like "show me the model from the
  south west", so it is `autocad_tiled_viewports`.
- **Hyperlinks** (`autocad_hyperlinks` Change, `autocad_list_hyperlinks` Read, #178). COM: each
  object's `Hyperlinks` (`Add(url, description, location)`, `Item`, `Delete`; checked in the same
  interop assembly). One link per object, as HYPERLINK keeps: `set` replaces. The whole-drawing
  listing selects by the hyperlink's extended data (application `PE_URL`, filter code 1001), so it
  is one selection, not one COM call per object; objects inside block definitions are not reached.
- **DWF export** (#179): `autocad_export` with a `.dwf` path, the PDF route (D-04) with
  `DWF6 ePlot.pc3`: plotter set on the layout, `PlotToFile` with the path alone, the page setup put
  back. Still a **Publish** job. Extended rather than a new tool, so "export" stays one tool and the
  plot code one copy. DWFx (another plotter, name not checked) is left out.
- **Geographic location** (`autocad_geo_location` Change, `autocad_get_geo_location` Read, #180):
  .NET `GeoLocationData` in the plug-in (`set_geo_location`, `geo_location`), checked by reflection
  on the reference DLLs for 2021-2027. Default coordinate system WORLD-MERCATOR (grid, metres), as
  Autodesk's ObjectARX sample uses; `HorizontalUnits` = INSUNITS (refused when 0); scale worked out
  at the reference point, so a metre drawn is a metre on the ground there. Whether the reference
  point wants grid metres or longitude / latitude is not documented anywhere this session could
  read, so the plug-in writes grid first, then lon / lat, and keeps the first that **AutoCAD's own
  `TransformToLonLatAlt`** reads back right: the drawing point at the place asked (1e-6 degrees),
  and a point 100 m along the north asked reading 100 m north on the ground (within 10 %, which also
  catches the units). Neither: refused, nothing changed. The answer names the form that worked
  (`reference_form`), for the live check to settle. **One place:** the sun's LATITUDE / LONGITUDE
  (`autocad_set_sun`, D-86) is the place. Without a latitude and longitude the tool takes it, and
  refuses AutoCAD's San Francisco default; with them, the sun's place is moved to the site in the
  same undo step. The sun's date, time and time zone are never touched. North is degrees clockwise
  from up the screen, as a compass reads.
- **Not proved live.** Rows AQ6-AQ14 in [NEEDS-CHECKING](NEEDS-CHECKING.md), all NOT RUN.

## D-110 - Associative and path arrays are a plug-in operation, checked against Heron's own plan before they are kept

**Decided:** 2026-11-21, part 2 of issue #119, split into #175. **Status:** in force.
`autocad_associative_array` (Change), beside `autocad_array_entities`, which keeps making loose COM
copies. COM has no associative array, so the plug-in's `associative_array` does
`AssocArray.CreateArray(sources, VertexRef, parameters)` with `AssocArrayRectangularParameters`,
`AssocArrayPolarParameters` or `AssocArrayPathParameters` (path as an `EdgeRef` of the curve,
Divide for a count, Measure for a spacing), then `AssocManager.EvaluateTopLevelNetwork` so the items
have their places. Every name and signature was read from Autodesk's reference DLLs (AutoCAD.NET
24, 25, 26), not from memory. What the DLLs do **not** say is what the base point means for a ring
and whether the array's angles are degrees; the choices are: base point = the objects' own point
for a grid and a path, the centre for a ring (radius and start angle from the objects' point);
angles in degrees (ObjectARX's own defaults are 15 between items and 90 between axes). So the
plug-in never trusts them blind: `Bridge/ArrayPlan.cs` works out where each item's base point
should go, and after AutoCAD builds the array its extents must lie inside, and reach across, the
items' boxes (exactly for items that do not turn, within the objects' reach for items that turn).
Anything else aborts the transaction: "AutoCAD built the array somewhere other than asked ...
Nothing was changed." Counts: at most 10,000 items; dividing an open path puts the first and last
items at its ends; measuring fits as many as the path holds, or refuses a count that does not fit
and says how many do. Default base point: one block's insertion point, else the path's start
(path) or the objects' middle. Grids run along the world X and Y (no turned grid yet). ARRAY takes
the originals into the array; the answer lists any left loose. Live rows AQ1-AQ5, NOT RUN.

## D-108 - Construction lines, regions, donuts, divide and measure: COM where it has a call, Heron's maths where not

**Decided:** 2026-11-21, part 1 of issue #119 (the smaller ribbon gaps), split into #173, #174,
#177 and #181. **Status:** in force. Four Change tools in a new file, `tools/draw_extra.py`, so the
`autocad_draw_*` tools and the batch are left alone. Not named `autocad_draw_*` for the same reason.
- **Construction line and ray** (`autocad_add_construction_line`, `kind` xline or ray): COM
  `AddXline` / `AddRay`, base point plus a second point. Given an angle, the second point is one
  unit along it. XLINE's own Offset and Bisect options are not built: offset an xline with
  `autocad_offset_entities`, and a bisector is two points the AI can work out.
- **Region** (`autocad_add_region`): COM `AddRegion` on the outlines' own space, one region per
  closed loop. Only lines, arcs, circles, ellipses, splines and polylines are sent; text, blocks and
  the rest are refused before AutoCAD is asked. The outlines **stay** unless `erase_outlines`
  (REGION's DELOBJ is not read: a tool's result should not change with a setting the modeller cannot
  see). With `erase_outlines`, every outline given is erased, and one on a locked layer is refused before anything is made. Holes are cut afterwards with `autocad_solid_boolean` subtract, which already takes regions.
- **Donut** (`autocad_add_donut`): no COM call makes one, so Heron draws the object DONUT makes: a
  closed lightweight polyline of two half-circle arcs (bulge 1 each), constant width
  (outside - inside) / 2, run at radius (outside + inside) / 4. Inside 0 is a filled dot. Many
  centres in one call, as DONUT keeps asking for centres; one undo step. FILLMODE 0 is said, not
  changed.
- **Divide / Measure** (`autocad_divide_curve`): no COM call either. The distances are Heron's maths
  over the run's segments (`acad/geometry.py`, the same reading `autocad_place_along` uses), then
  `AddPoint` or `InsertBlock` at each, in the run's own space. Heron's rules: DIVIDE on an open run
  leaves both ends free (N parts, N - 1 marks); on a closed run the first mark is on its start, so N
  marks. MEASURE starts at the start (or the end, `from_end`), puts no mark exactly on the far end,
  and gives `left_at_end`. A block is turned to the run's own direction (`align`, on by default as
  DIVIDE's "Align block with object? Yes"), not reversed by `from_end`. Lines, polylines, arcs and
  circles only (what `read_path` reads); a sloping line or a run not flat in world plan is refused.
  At most 2,000 marks a call, refused before any position is worked out; a layer name is checked
  before anything is drawn. Splines and ellipses are not built: no tested reading of them as a
  path yet. `autocad_place_along` stays the tool for equal ends.
- **Not checked against Autodesk's reference (D-33).** The help site is blocked from the session
  that built this, and there is no AutoCAD here, so the COM calls (`AddXline`, `AddRay`,
  `AddRegion` and its return, `ConstantWidth`) and the DIVIDE / MEASURE rules above are from
  knowledge. Live rows AP1-AP11 in [NEEDS-CHECKING](NEEDS-CHECKING.md) compare each with AutoCAD's
  own command; all NOT RUN.

## D-105 - A plot style table is not made by Heron: the .NET API cannot write one

**Decided:** 2026-11-21, building issue #68. **Status:** in force (a known limit, [05 §34](05-known-limits.md)).
A plot style table (`.ctb` colour-dependent, `.stb` named) is not part of the drawing: it is a
file in AutoCAD's Plot Styles folder, made in the Plot Style Manager. Autodesk's .NET reference
assemblies for 2021 and 2027 were searched for a way to make or edit one, and there is none: only
`PlotStyleDescriptor` and `PlotStyleNameType` (a plot style's id on an object), the picker
dialog `PlotStyleDialog`, and an event when a layout's table changes. COM has none either. So
`autocad_create_styles` takes no plot style option and says so in its `Don't use when:`; the
modeller makes or copies the `.stb` / `.ctb` in AutoCAD, and `autocad_page_setup(plot_style_table=...)`
sets it on a sheet. **Rejected:** writing the file format ourselves (it is Autodesk's, compressed
and undocumented; a file AutoCAD cannot read would show up only at plot time, and nothing here could
check it), and typing STYLESMANAGER (it opens a window the chat cannot drive).

## D-104 - Multileader and table styles are made by the plug-in; the rules are in the Bridge

**Decided:** 2026-11-21, building issue #68. **Status:** in force; extends D-28 and D-40 (built
and tested offline; live rows AN1-AN12 NOT RUN).
- **Two new plug-in operations**, `multileader_style` and `table_style` (level Change), because
  COM has no call to make either (until now they came in only with `autocad_import_from_drawing`).
  `autocad_create_styles` takes `multileader_styles` and `table_styles` beside its text and
  dimension styles, and stays a Change tool written from a fixed list (D-28): the options are a
  list in `tools/settings.py`, a misspelt one is refused before anything is written, and a test
  holds that list to the options the plug-in reads.
- **The rules are pure code in `Heron.AutoCAD.Bridge/StylePlans.cs`** with their own tests: the
  option words, the defaults and every refusal. The add-in (`DrawingStyles.cs`) only copies a plan
  onto AutoCAD's `MLeaderStyle` / `TableStyle` and reads back what the style then holds. One
  transaction per style: a style AutoCAD refuses is that style's row and nothing of it is kept;
  the others are still made. Text styles come first in the same call (and the same undo mark), so a
  style can use one made with it.
- **A multileader style is Ajmal's TLD label unless asked otherwise (D-24):** MTEXT content,
  straight leaders, the text attached *underline bottom line* on both sides (the leader ends under
  the text), arrow and dogleg (the dialog's "landing") as big as the text, as `autocad_add_label`
  draws them. Sizes are given as they plot and the style's own scale makes them drawing sizes, as
  the Multileader Style dialog does. The dialog's one landing switch is `EnableDogleg` and
  `EnableLanding` together. Arrows are AutoCAD's own by name (`dot`, `architectural_tick`...);
  a block the drawing lacks is made the way AutoCAD's dialogs make it, by naming it in DIMBLK, which
  is put back straight after (the one piece that is not undone if a later step fails, so everything
  else is checked first). An annotative style keeps its own scale (the annotation session's work is
  not touched).
- **A table style keeps text in the vertical middle of every cell (D-83):** title, header and
  data rows take left, centre or right only; top or bottom is refused. A table style has no scale
  of its own, so text heights and margins are given as they plot and multiplied by the scale
  (2.5 at 1:50 is 125). Margins default to a third of the text height, as in AutoCAD's own Standard
  style (0.06 for 0.18 text); header and title heights to the data height.
- **A scale reads as the dimension style's does:** a number is the factor (50 = 1:50), and text the
  way the sheet writes it ('1:50', '2:1'). A bare number below 1 is refused rather than guessed
  (0.02 could be the 1:50 ratio or a factor fifty times too small), the mirror of D-36.
- **Not yet known (live rows):** whether AutoCAD's dialog shows these as set (the attachment
  numbers and the landing switch are from Autodesk's reference, not a run), whether the DIMBLK
  round trip leaves no style override, and whether one Ctrl+Z takes back text styles and plug-in
  styles together. **Rejected:** typing MLEADERSTYLE / TABLESTYLE (each opens a dialog, which typed input
  cannot drive), a COM dictionary `AddObject` of these classes (not proven anywhere), and a general "set any
  property" request (D-40's reason).

## D-102 - A full-sheet preview says what it covered, and can add close-ups

**Decided:** 2026-11-21, for issue #41. **Status:** in force; extends D-04 (the plot route) and
leaves the default preview one picture, as before.
On 2026-10-28 `autocad_preview(area='extents')` of an A1 schematic at 1:1 showed only the two frame
rectangles, while windows over its parts showed everything. The cause could not be seen from here
(no AutoCAD). The two found in the code and in Autodesk's behaviour:
- **Too few pixels for the sheet (most likely).** AutoCAD's PNG plotter has fixed sizes; the
  preview takes the one nearest `width_px` (1600 by default), and the chat app may shrink the
  picture again. Which sizes AutoCAD 2027 offers is not yet known here (row AM5). A whole A1
  (841 mm) fitted into 1600 pixels is about 0.5 mm a pixel: 2.5 mm text and thin lines turn to
  specks while the heavy frame still shows. A window over one part gets the same pixels for less
  paper, which is why windows showed everything.
- **Extents bigger than the sheet.** EXTMIN/EXTMAX grow as things are drawn and shrink only on a
  ZOOM All / Extents, and they count objects on layers that are off, not plotted or on Defpoints.
  A stray or erased object far off makes the sheet small in the picture.

What the code does now: an extents preview regenerates first (as `autocad_get_extents` does) and
the answer says the area plotted (`plotted`), the picture's `pixels` and the smallest text height
that reads (`smallest_clear_text`, 8 pixels a letter), with a `tip` when the drawing's TEXTSIZE is
smaller. **`detail=2` (or 3)** adds 4 (or 9) overlapping close-ups of the same area, plotted as
windows, because windows are the route that showed everything live; each is named (top left ...)
with its corners. Not done: a bigger PNG (the pc3's pixel sizes cannot be changed over COM; a
custom size is a pc3 edit by hand), and plotting the overview as a window (the extents read back
could be staler than AutoCAD's own Extents plot). Close-ups are refused for `area='view'` (no
corners) and skipped, with the reason, in a 3D view or a rotated UCS, where the plan box does not
match the picture. Live rows AM1-AM6 NOT RUN; issue #41 stays open until AM1 says which cause it was.

## D-100 - A busy refusal goes up as it is from every `except`; a source test keeps it so

**Decided:** 2026-11-21, for issue #36. **Status:** in force. Finishes what D-57 began in
`ensure_layer` and `ensure_linetype`.
After the message filter's 3 s (D-57), AutoCAD's refusal ("Call was rejected by callee") still
reached about 300 `except` blocks in the tools that took it for "not there", "use the default",
"skip it", or wrapped it in a plain `AutocadError`. So a busy AutoCAD gave a false failure ("Could
not ..."), or a quiet wrong answer: a layer reported off, the world UCS used instead of his, "UNDO is
off" offered after Discard, an object called gone after an UNDO.
- **One helper, one line per place:** `raise_if_busy(exc)` in `core/errors.py`, first in each such
  `except` (after any clean-up in it). Up at `_with_retry` the refusal is asked again while nothing
  has been written, or becomes "Outcome unknown" once a write began (D-15). Nothing else in those
  blocks changed, so many sessions could edit the same modules at once.
- **What counts as busy (`is_busy`):** the two refusals (RPC_E_CALL_REJECTED,
  RPC_E_SERVERCALL_RETRYLATER), VBA_E_IGNORE (a modal dialog open), or a COM description that says
  "rejected by callee", "busy" or "retry later". It is narrower than `is_retryable` on purpose:
  pywin32's `AttributeError` for a member it cannot resolve is left out, because asking a line for
  its Radius gives the same error, and the tools rightly read that one as "not there".
  RPC_E_SERVERFAULT is left out too: it says the call itself threw.
- **Left as they are, each named with its reason** in `ALLOWED` in `tests/test_busy_sweep.py`:
  putting things back (variables, page setup, locked layers, table redraw, undo groups), presses of
  Esc on the way to the real error, the waits that deliberately read through a busy AutoCAD
  (D-58), reads after the plug-in made something ("do not make it again"), and code with no COM
  call. Raising there would hide the real answer or skip the rest of the clean-up.
- **The gate:** a busy UNDOCTL read before an Ask-to-Keep job is no longer "UNDO is off": if
  AutoCAD stays busy through the retry, the job is refused in words ("AutoCAD stayed busy ... nothing
  was changed") before anything is sent, instead of a bare tool error.
- **The source test:** `tests/test_busy_sweep.py` reads every module in `acad/` and `tools/` and
  the three core modules that call COM. An `except` that can catch a COM error (bare,
  `BaseException`, `Exception`, `com_error`) must call `raise_if_busy` / `is_busy` /
  `is_retryable`, re-raise as it is, or be in `ALLOWED`. One directly in an `async def` is not
  swept: COM runs on the worker thread only, so those reach AutoCAD through `run`, whose retry has
  already answered. New code cannot bring the old way back without the test saying where.
- **What changes for the modeller:** a long busy spell (a dialog left open, a heavy redraw) now
  ends in "AutoCAD stayed busy ... press Esc" or "Outcome unknown, look before retrying", never in
  a made-up failure or a wrong value. Tested offline with fake COM (`tests/test_busy_refusals.py`).
  Not proven in AutoCAD: [NEEDS-CHECKING group AL](NEEDS-CHECKING.md).

## D-99 - One setup program, built with Inno Setup; signing ready behind secrets; tests import their own src

**Decided:** 2026-11-21, for issues #73, #35 and #72 (#72 prepared only). **Status:** in force;
extends D-56. Live rows AK1-AK11 NOT RUN.

**The setup (#73).** `tools/make_installer.py` packs the release folder `make_release.py` leaves in
`dist/` into `HeronAutoCAD-<version>-setup.exe`, with `tools/installer/HeronAutoCAD.iss`.
**Inno Setup, not WiX:** a per-user install is Inno's ordinary case (`PrivilegesRequired=lowest`),
uninstall and update by a fixed AppId are built in, the whole installer is one readable script,
and its Pascal code can refuse while AutoCAD runs and run `Install.ps1`. A per-user MSI in WiX
needs a registry key path for every component and custom actions to run PowerShell, for no gain
here. Inno Setup's licence allows commercial use; its authors ask commercial users to buy a
licence, which a free plug-in does not need. The compiler is **pinned**: 6.7.3 from NuGet
(`Tools.InnoSetup`, which packs the official files), checked in `release.yml` by its SHA-256 and by
the Authenticode signature of its authors (Pyrsys B.V.) on `ISCC.exe`. windows-latest has no Inno
Setup. Inno Setup 7 exists; moving to it is a change of its own.

What the setup does, and why it matches `Install.bat` (D-56):
- **Same places:** the bundle in `%APPDATA%\Autodesk\ApplicationPlugins`, the server in
  `%LOCALAPPDATA%\Heron\autocad`; no folder page. Its AppId is the bundle's UpgradeCode. The
  versions come from `Directory.Build.props` (plug-in and setup) and `autocad_mcp/__init__.py`
  (server) through `/D`; the script refuses to build without them.
- **Refuses** while `acad.exe` runs, or `autocad-mcp.exe` runs from the install folder (a
  developer's `.venv` server elsewhere does not count): at start, again just before copying, and
  when removing. It never closes a program itself (`CloseApplications=no`).
- **Claude** is set up by `Install.ps1 -Connect` and taken out by `Install.ps1 -Disconnect`, the
  same `Connect-Claude` / `Disconnect-Claude` lines `Install.bat` and `Uninstall.bat` run, so the
  two ways can never drift. The last page shows what was set up.
- **Update** is a newer setup over the old one (or over a zip install). It replaces the whole old
  bundle, as `Install.bat` does: just before copying it moves the installed one aside
  (`HeronAutoCAD.bundle.heron-old`, beside it), drops it once the new one is in, and puts it back if
  the install is cut off (cancelled, or a file that would not copy). **Going back** is the older
  setup from the releases page: the setup keeps no `previous` copy. It refuses `/DIR=`, since Claude
  is told the server is in `%LOCALAPPDATA%\Heron\autocad`. **Uninstall** removes only what it installed, plus the `previous`
  copy `Install.bat` kept; saved commands, check lists, logs and the audit stay.
- **The zip and `Install.bat` stay** until Group AK has a live PASS. `Uninstall.bat` now also removes
  the kept earlier version, and sends a setup install to Windows Settings > Apps.

**Signing (#72), prepared, then not bought.** `tools/signing.py` signs Heron's own files with `signtool`
(SHA-256, time-stamped): `Heron.*.dll` in every Contents folder before they are packed,
`autocad-mcp.exe`, `Install.ps1`, and the setup with its uninstaller (Inno's `SignTool`). It runs
only when the repository has **both** secrets `HERON_SIGN_PFX_BASE64` and `HERON_SIGN_PFX_PASSWORD`;
without them the release says *Not signed* (a notice and the run summary) and goes on; one without
the other stops the build. The password never reaches a log. A run started by hand signs a second build with a throwaway test
certificate and checks every signature (`signing-dry-run`, nothing published). **Ajmal decided on
2026-11-21 not to buy a certificate** (#164; #72 closed as not planned): Heron stays unsigned, the
step stays skipped, and a modeller trusts the plug-in once, at its first AutoCAD load (rows AK10,
AK11), and clicks past SmartScreen once. Should that change: since June 2023 public code-signing
certificates come on a token or as cloud signing, so the seller's own step would be added to
`release.yml`; the `.pfx` route also serves a test certificate on a PC of one's own.

**Tests import their own src (#35).** `pyproject.toml` gives pytest `pythonpath = ["src"]`, so a
worktree sharing the main checkout's `.venv` tests its own code, and `tests/conftest.py`'s
`script_env()` puts the same `src` first for scripts a test starts. `tests/test_checkout_import.py`
fails when `autocad_mcp` comes from anywhere else, even with another copy first on `PYTHONPATH`.
`PYTHONPATH=src` in the Linux gate commands is now harmless, not needed.

## D-98 - The plug-in reports drawing events as they happen; a batch goes through it in pieces up to 1,500 characters

**Decided:** 2026-11-21, issues #48 and #45. **Status:** in force (built and tested offline; live
rows AJ1-AJ10 NOT RUN).

- **Drawing events (#48).** The plug-in records AutoCAD's document events as they happen
  (`DrawingEvents`, fed by `DrawingWatch` in the add-in): a drawing *opened*
  (`DocumentCreated`), *came to the front* (`DocumentBecameCurrent`; the one already in front is
  not news), *saved* (`Database.SaveComplete`, read after the command so a Save As gives the old
  name; the automatic save `.sv$` and backups are left out) and *closed*
  (`DocumentToBeDestroyed`). Each event has a number, and the log an epoch that is new for every
  AutoCAD session; 200 are kept. A stdio server has no way in from the plug-in (D-68), so the server
  asks: the new op `drawings {since}` answers the events after that number, read only, on the
  pipe thread.
- **The wrong-drawing guard (D-19) uses them.** `autocad_status` (and `autocad_create_drawing`)
  notes where the log stands; a later change asks for the events since. The checked drawing
  **closed** since (even when the same name is open again: it is a new copy in memory, perhaps
  changed on disk) or **another AutoCAD session** (restarted, or another AutoCAD) is refused with
  "call autocad_status first". A **Save As** of the checked drawing is followed: the same drawing,
  the same units, so no new check. A switch away and back is the same drawing and goes ahead, as
  before. When the plug-in cannot tell (an older one, history dropped off) the guard is exactly
  the name compare it was.
- **Mid-job.** `send_quiet` refuses drawing input once another drawing came to the front (or the
  job's drawing closed) after the job's `begin`, counted only from events AutoCAD reported, so a
  missed event never refuses; the add-in checks the drawing in front again on the main thread
  before typing. That refusal ends the input: the server never types it over COM instead.
- **The palette** redraws its Activity list on every drawing event: a line "In front: plan.dwg",
  the drawing events between the jobs (15 newest), and *not in front* on a job in another drawing.
- **Fewer `Command:` prompts (#45).** Every top-level expression typed leaves one prompt, echo off
  or not. The plug-in's ping now says `quietLimit` (1,500), and `send_quiet` refuses a longer line
  before typing anything. The server builds the batch in pieces up to that (never above
  `QUIET_CHUNK_LIMIT` = 1,500), packs the short set-up pieces into one `(progn ...)`, and keeps
  the last piece (close the undo group, write DONE) on its own, so an error before it never
  leaves the undo group open. Offline, the 41-object batch of the live checks goes from 25 pieces
  to 9. Over COM, from an older plug-in, or when the plug-in refuses, the pieces stay under 600
  (D-21). 1,500 is below the 2,000 characters that worked all day over COM and far from the
  3,000 that arrived as nothing (known limits §3); it is not measured through `SendStringToExecute`
  yet (AJ6, AJ7).
- **Two safety nets found on the way.** A `send_quiet` that went out and got no answer is treated
  as typed: sending it again over COM could draw the batch twice. A batch whose output file has
  DONE but fewer result lines than operations says `missing` with a hint, never a quiet success.
- **After an independent review (same day).** The guard also refuses a drawing *opened* since the
  check when it is the one in front (a Save As, then the old file opened again; a second copy).
  History that dropped off is no longer a reason to ignore the events still there; 200 are kept,
  and every change the guard lets through moves its mark up. Names are compared exactly, so an
  unsaved `Drawing1.dwg` is never taken for `D:\F\Drawing1.dwg`. `autocad_status` takes its mark
  before its work. `send_quiet` now waits (up to 10 s) for AutoCAD to get to the input and answers
  the truth: typed, refused because another drawing is in front (also when the switch came between
  the server's look and `begin`), or not started in time (abandoned, never typed later). A Save As
  of the job's drawing is followed. The add-in keeps the old names by AutoCAD's database, not the
  .NET object, and says a Save As made while closing before the close.
- **Not done:** the Companion page (D-71) is a file the gate rewrites after each job, so it cannot
  update live without a server of its own; the docked palette is the live list.
- **Added after the merge (#165, same day).** `begin` answers `drawingSeq`, where the drawing log
  stood. Between its steps `autocad_sequence` asks the events since (`gate.front_changed_in_job`)
  and stops when another drawing came to the front or the job's drawing closed (a Save As of it is
  the same drawing), like HERONSTOP: the steps before stay, the rest are not run. An older
  plug-in says no number, and the sequence runs on as before.

## D-97 - Arcs are cut in Python; a multiline's Close and control-point splines go through the plug-in

**Decided:** 2026-11-21. **Status:** in force. Issues #52, #55, #56.

**Breaking a polyline with arcs at a block** (`autocad_break_at_blocks`) is plain arithmetic, not
the plug-in's curve splitting. Where an arc crosses the four sides of the block's box is a circle
meeting four lines; each piece keeps the arc's centre and radius by taking the bulge of its own
sweep, tan(sweep / 4), with the arc's sign. Doing it in `acad/geometry.py` means every cut is tested
without AutoCAD (the pieces are rebuilt from their bulges and measured against the arc they came
from), where a .NET `GetSplitCurves` could only be proven live. A closed polyline cut once now comes
out as one open run instead of two pieces meeting at its first vertex - straight ones too.

**MLINE's own Close** has no Automation call: COM's `AddMLine` can only repeat the first point, which
overlaps the last corner. .NET has `Mline.IsClosed`, so `autocad_draw_multiline(closed=true)` draws
the multiline open over COM and asks the plug-in (`close_multiline`) to close it, which mitres the
last corner like the rest. The multiline is drawn by then, so that call never raises (only a busy
AutoCAD goes up, as "Outcome unknown", D-100): if the
plug-in is not in the job or cannot close it, the first point is added again (the old way) and the
answer says `"mitred": false` and why. Drawing it twice to get round an error would be worse.

**A spline by control points** (SPLINE's CV method) has no COM call either (`AddSpline` takes fit
points only), so the plug-in makes it (`add_cv_spline`) with `new Spline(degree, ..., control
points, knots, ...)`. The knots are worked out in Python, where they are tested by evaluating the
curve: clamped for an open spline, so it starts on its first point and ends on its last; for a
closed one the first `degree` points are repeated at the end with even knots all the way, so it
meets itself with no corner. The plug-in checks the same rules again (`SplineCheck`, tested in C#).
That a wrapped, unclamped spline is what AutoCAD shows as closed is the live row AI11's question.

**Editing a spline's fit points** (`autocad_edit_spline`) is done by the plug-in too, because .NET
documents its three calls (`SetFitPointAt`, `InsertFitPointAt`, `RemoveFitPointAt`, 0-based) and COM's
`AddFitPoint` does not say which side of the index it adds. The server reads the points, plans the
edits as steps and works out the points that must be there after; the plug-in runs the steps, reads
the points back and refuses anything else, so a wrong guess about an index changes nothing (its
transaction is aborted). The edits are the drafter's own - move point 2, insert a point as number 3,
remove point 4 - numbered as `autocad_get_entity` now lists them. Fit data cannot be set in one go
(`FitData` has no setter for its points), which is why it is steps.

## D-96 - Every draw and modify tool takes coords='ucs'; a flipped UCS is a mirror; the batch fills

**Decided:** 2026-11-21. **Status:** in force. Issues #50, #51. Extends D-27 and D-30.

**`coords="ucs"` on the single-entity tools.** D-27 kept world coordinates as the contract and gave
`coords="ucs"` to the batch only. Every `autocad_draw_*` tool, text, mtext, dimensions and blocks,
and move, copy, rotate, scale, mirror and array take it now, through the same transform and the
same `ucs_for` (world unless asked; a tilted UCS refused). What each converts is the part that was
missing in D-27: a rectangle's four corners (square to the UCS is not square to the world), a
polyline's vertices and its height (a UCS moved up gives the Elevation), an ellipse's axis, every
angle, a displacement (turned, not moved), a turn (the same amount on any plan UCS). "Horizontal" in
a dimension means the UCS's own X. ARRAY's rectangular rows follow the world's axes over COM, so on
a turned UCS the grid is made copy by copy, each offset worked out in Python. World stays the default,
and a call without `coords` does exactly what it did.

**A flipped UCS is a mirror.** A UCS with its Z pointing down is not tilted, so it passed `ucs_for`,
but anticlockwise in it is clockwise in the world: the batch turned its angles the wrong way. Now
`Ucs.angle_to_world`, `angle_from_world`, `turn_to_world`, `arc_to_world` and `bulge_to_world` say
it once - angles run the other way, an arc's ends swap, a bulge changes sign - and every tool uses
them, `autocad_convert_points` included. Text, mtext, dimensions (and dimension runs), multileaders,
tables, blocks, xrefs and super hatches are **refused** on a flipped UCS: COM puts them on the world
plane, so they would read mirrored in that view, where AutoCAD's own commands put them on the UCS's
plane. Refused, not guessed, as D-27 does for a tilted one.

**Fills, mtext and dimensions in the batch.** D-30 put bulges and text justification into the batch;
hatch, mtext and dimension were left. Now: an **mtext** with its attachment point (long text sent in
the 250-character pieces DXF holds); a **hatch** that is a SOLID fill of its own outline (arcs and
holes included, not associative - a batch operation has no boundary object to follow); and a
**linear dimension** (aligned, horizontal, vertical, rotated) whose line runs through the text point,
in the current dimension style, given the drawing's current DIMSCALE as its own override (0
included, as DIMLINEAR would) - the same reason `autocad_add_dimension` gives it one. Drawn with
`coords="ucs"` on a turned UCS it also carries that UCS as its text direction (DXF group 51,
minus the UCS's angle, as DIMLINEAR writes it), so text kept horizontal reads along the UCS. A text
or mtext with no rotation given turns with the UCS too: left out means 0, which is the UCS's X. The fill is solid only because entmake cannot read a pattern's
lines from acad.pat; patterns, and radial, diametric and angular dimensions, stay with their own
tools (ROADMAP). The geometry - where a dimension line goes, how a loop is written - is plain
arithmetic tested without AutoCAD.

**Filled symbols are opt-in.** `section_mark`, `north_arrow`, `scale_bar` and `level_mark` take
`filled=true`; the default stays the outline until live row AI4 shows an entmade hatch lands, so a
shape that works today cannot start failing on a fill nobody asked for.

## D-95 - Sections, flat views, surfaces, meshes and the new super hatch tiles are plug-in operations

**Decided:** 2026-11-21, for issues #54, #109, #58 and #57. **Status:** in force; extends D-40 and
D-33. None of FLATSHOT, SOLPROF, SECTIONPLANE, PLANESURF, SURFNETWORK, MESH or Express Tools'
image / xref / wipeout SUPERHATCH has an ActiveX call, so each is a listed plug-in operation
(`flat_views`, `section_plane`, `loft_surface`, `planar_surface`, `network_surface`, `add_mesh`,
and `super_hatch` with a `tile_kind`), Change level, one transaction each. Every .NET call was
checked against the AutoCAD 2027 reference assemblies before it was written (the signatures, by
reflection; the plug-in compiles for all three builds).

**One mechanism for a section and a flat view.** Both use AutoCAD's own section object (`Section`)
and `GenerateSectionGeometry`, the call behind "Generate Section / Elevation". A section plane goes
through the modeller's points and is kept; a flat view puts a temporary plane outside the solids'
box on the viewer's side, so it cuts nothing and the 2D "background" it returns is the view with
hidden lines removed, as FLATSHOT draws it. The plane is made with its viewing direction given
explicitly (`Section(points, vertical, viewing)`), so which side is seen is Heron's choice, not
AutoCAD's default. Where each view looks, the third / first angle layout, and where a plane through
two or three points runs (two points: a vertical cut looking left of the line; three: the plane,
a level one looking down with north up) are pure arithmetic in `Bridge/SectionMath.cs`, tested
offline. The 2D lines are laid flat by what they are found to lie on (the plane, already flat, or
neither and then projected), and the answer says which (`laid_flat_from`), because the reference
does not say where GenerateSectionGeometry puts a 2D section's lines; rows AH3 and AH6 settle it.

**What is left out, on purpose.** Hidden (obscured) lines in a flat view: the API gives visible and
hidden lines in one list with no way to tell them apart, so a view shows visible lines only, as
FLATSHOT does by default. Several solids are flattened each on its own unless `join=true`, which
flattens one temporary union of copies: it hides what is behind a part, and loses the line where
two flush faces meet; the modeller chooses. Jogged section lines (more than one segment): later.

**Super hatch tiles.** An image or a wipeout is first made into a small tile block of its own; an
xref is the tile as it is, attached from its `.dwg` if it is not already there. Then the one block
tiling path of D-40 does the rest, so every kind is one object, clipped as XCLIP clips. An xref
this call attached is detached again if the hatch is then refused, because attaching is not only
a database change. Image tiles are capped at 2,000 (raster images are heavy), blocks at 10,000. A
block hatch sends exactly what it sent before, so an older plug-in still does it.

Rejected: typing FLATSHOT (a dialog) or SOLPROF (works only inside a layout viewport and asks
questions); projecting the solid's Brep edges ourselves (no hidden-line removal and no silhouette
lines on a pipe or a cylinder); one "make a surface" operation taking any arguments (each kind is
listed and checked on its own, as D-40 asks).

## D-94 - A 3D shape is pieces in their own frames, made where COM has no doubt and then moved

**Decided:** 2026-11-21, for issue #53. **Status:** in force; extends D-30.
`autocad_make_shape` takes two 3D shapes, `duct_run` and `pipe_spool`. A solid cannot go down the
batch engine, so a 3D shape is generated as a list of **pieces** (straight, bend, flange), each in
its own frame where AutoCAD makes it without any doubt - a box or a cylinder standing on the origin
up +Z, or a profile at the origin revolved round an axis through (radius, 0, 0) along +Y - plus one
4 x 4 matrix that puts it in place. The pieces and their matrices are pure Python
(`acad/shapes3d.py`), so what matters is tested without AutoCAD: each piece ends where the next
begins, each bend leaves the way the next straight runs and is tangent to both legs at
radius x tan(angle / 2), the straights are the legs less the tangent lengths (a spool's cut
lengths), a rectangular duct is carried round its bends without twisting, and every matrix is a
move, never a mirror.

The COM side (`tools/_solid_pieces.py`) uses only calls already in use (AddBox, AddCylinder,
AddRegion, AddRevolvedSolid, Boolean) plus TransformBy with the matrix. Two of its steps check
themselves, because neither convention is in Autodesk's reference: a bend that came out sweeping
backwards (the revolve's sense) is made again the other way, and every piece's box is compared
with the box it should fill, so a piece that landed anywhere else is reported (`verified: false`)
rather than looking finished. A refusal half way takes out every piece already made.

Defaults, said in the tool so nobody is misled: a rectangular bend's centreline radius is the
duct's size in the plane it bends in (R/W = 1), a round duct's 1.5 x D, a spool's elbow 1.5 x the
outside diameter (a long-radius elbow is 1.5 x the nominal size: give `bend_radius` from the
catalogue when it matters). Flanges have no default size; a flange table is the modeller's.
Pieces are separate solids, as they are fabricated, with `join=true` to union them.

Rejected: one sweep along a filleted path (AutoCAD sweeps along a 2D polyline with arcs or a
spline, not a 3D route with bends, and the result could not be checked piece by piece); Rotate3D
and Move instead of TransformBy (two more sign conventions to trust, each failing silently).

## D-93 - The office check lists live in a folder the modeller names; sharing them is its own Publish tool

**Decided:** 2026-11-21, issue #135 (from the brief for this wave: "a folder the modeller names,
e.g. a shared drive, as the office list's home, with the local copy as the fallback, never
overwriting a teammate's file silently"). **Status:** in force. Extends [D-64](#d-64---check-lists-no-data-office-lists-with-project-changes-pass-is-not-complies).

- **Where it is set.** `autocad_checklist(action='office_folder', folder='S:\CAD\Heron')`, once per
  PC, kept in `%LOCALAPPDATA%\Heron\autocad\checklist-office-folder.json`; `folder=''` clears it.
  Not an environment variable in `.mcp.json`: the modeller sets it from the chat, and Heron checks
  the folder answers before keeping it.
- **Reading.** A run takes the list from the office folder first. Each read keeps a copy on this PC
  (`checklists\office-copies\`). When the folder cannot be reached (it is given 10 s, then believed
  unreachable for a minute, so a folder check does not wait per drawing), or its file cannot be
  read, the run says so plainly and uses that copy, naming the date it was read. With no copy, it
  uses this PC's own list of that name, saying so; but if the office folder **has** the list and it
  cannot be read, nothing is run: Heron never runs another list in place of the office's. Saving
  on this PC under a name the office folder has is refused (it would never be used).
- **A project's changes with the project.** `<the drawing's folder>\Heron check list changes.json`
  holds them for everyone who opens a drawing from that folder; it wins over a PC's own changes
  (D-64's store, still used when there is no such file), and a run says when they differ. A file
  there that cannot be read stops the run. Still only severity, target and on/off.
- **Writing is `autocad_share_checklist`, at Publish** (as D-65): it writes outside Heron's own
  folder, where the team reads. A file there that holds something different is replaced only with
  `replace=true`, and the refusal names who saved it (the Windows user), when, and what differs;
  when replaced, what was there is kept in the same file as `previous` (one step back, never
  nested). The file is written beside itself and swapped in only if nobody changed it since it was
  read. **Who may change the office list** is the folder's own Windows permissions: a read-only
  folder is refused, saying so; Heron adds no roles of its own.
- **Every run names its files:** `lists.office` / `office_from`, `lists.project_file` /
  `project_from`, and `file` on every result line.

If Ajmal wants it otherwise (an `.mcp.json` setting for IT to deploy, or roles inside Heron), that
is a new decision; this one is easy to reverse, as nothing else reads the setting.

**Later the same day (an independent review):** a copy is used only if it was read from the office
folder set now (a copy from a folder set before is another office's list), and the warning names
the file it came from; `autocad_check_folder` keeps every run's warning on its line and names the
list it ran (`list`, `warning`); project changes are not shared while the office list cannot be
read (they would be checked against a stand-in and stop every teammate's run); the office and
project folder reads run off the server's main thread.

## D-92 - DXF / DWG files are read with AutoCAD closed (ezdxf, the ODA converter); standards compare with a reference drawing

**Decided:** 2026-11-21, issues #71 and #69. **Status:** in force.

- **`autocad_read_file`** (Read): the summary (DXF version, units, extents, counts, the most
  placed blocks, layouts, xrefs), the layers with objects per layer, the blocks with how many are
  placed and inside other blocks and their attribute tags, every text and mtext, every block's
  attribute values (JSON or CSV), and the text styles, dimension styles and linetypes, of a file on
  disk. It touches no AutoCAD, so the gate lets it through without the plug-in
  (`NO_AUTOCAD_TOOLS`, as `autocad_why`, D-67), audited like every call; `autocad_why` no longer
  says "press Heron" for it. The file is never written; what is read is what was last saved.
- **DXF with `ezdxf`**, now a dependency of the server: every PC installs it once, by name, with
  Claude closed (`.venv\Scripts\python.exe -m pip install ezdxf`,
  [05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)); without it the tool says how,
  and every other tool works as before. A damaged DXF is read in ezdxf's recover mode and the answer says
  so. Files over 250 MB are refused.
- **DWG, DWS and DWT through the ODA File Converter, only when it is installed.** Heron finds it
  (`HERON_ODA_CONVERTER`, else the newest `Program Files\ODA\ODAFileConverter*`, else PATH) and
  never downloads it. It converts a copy in a temporary folder to an R2018 DXF, with no window and
  a 3-minute limit, then reads that. Without it, a DWG is refused saying it needs AutoCAD, the ODA
  converter, or a DXF of it.
- **`autocad_check_standards(reference=...)`** compares the open drawing with a `.dws`, `.dwt`,
  `.dwg` or `.dxf`: layers by colour, linetype, lineweight and plot; text styles by font, big font,
  height, width and oblique; dimension styles and linetypes **by name only** (COM cannot read a
  dimension style's settings without making it current, which would change the drawing). Each
  name is missing, differs (both values said), or not in the standard (`flag_extra=false` leaves
  those out). Xref and anonymous names are left out; layer 0, Defpoints, Standard and ByLayer are
  never missing or extra. The reference is read by Heron's reader where it can (a DXF always; a
  DWG or DWS when the converter is there), else by AutoCAD's own reader (ObjectDBX, not opened on
  screen, or the open drawing itself); the answer says which in `reference.read_by`. PASS wording
  is D-64's: the checked values are met against that file, never "complies". Pure compare in
  `acad/standard_compare.py`.

Known limits: true colours are compared by their colour number; a `.dws` read by ObjectDBX and the
converter on a real DWG are not proven live (Group AG).

**Later the same day (an independent review):** a reference read in recover mode, or one holding
nothing beyond what every drawing has, never gives `passed: true` (it is `null`, with
`reference.warning`); a table AutoCAD cannot read (layers, styles, linetypes) stops the check,
naming it, instead of counting as empty; the converter gets the copy under a plain name of Heron's
own (it reads that argument as a wildcard filter); header extents at the origin are used.

## D-91 - One PDF from many drawings: the list is made in the server, each drawing is checked by the plug-in, and one problem stops the set

**Decided:** 2026-11-21, for issue #67. **Status:** in force; extends D-41 (the multi-sheet PDF of
the open drawing).
`autocad_publish_pdf` takes `folder` (with `recursive`) or `drawings` as well as the open drawing.
- **The list** is made in Python (`acad/publish_files.py`, tested offline): only `.dwg` files, each
  once (paths compared without case, as Windows does), a folder sorted the way a drafter numbers
  sheets (M-2 before M-10), a list kept in the order given. A file that is not there or not a .dwg is
  refused by name, never quietly left out of the set. At most 300 drawings.
- **Unsaved changes** are checked over COM before the plug-in is asked: a drawing of the set open in
  AutoCAD whose `Saved` is false is refused, because the publisher reads the saved file. The plug-in
  checks DBMOD again for the active drawing.
- **Xrefs** are checked by the plug-in, which reads each drawing (the open one's database, else the
  file read-only on the side): a loaded xref whose file is not at its saved path, beside the host, or
  on AutoCAD's own search paths refuses the set, naming the drawing and the xref. An unloaded xref is
  the modeller's choice and is left alone. Nested xrefs are checked through the xref that holds them.
- **One problem stops the whole set**, and every problem is said at once (`PublishPlan.ChooseAcross`,
  bridge tests): a PDF set with one sheet missing its background is worse than no PDF, and fixing
  three drawings in one go beats three tries.
- The pages go drawing by drawing, each in tab order; `layouts` picks the same-named sheets from
  every drawing that has them. The level stays Publish (D-41).
- Found in review (2026-11-21): a plug-in from before this would ignore `drawings` and publish the
  open drawing in their place, so the server first asks it for `active_sheet` (added with this): one
  without it is refused before anything is published, and an answer without `pages` is not taken
  for the set. Nested xrefs are followed from the xref's own file, up to four deep. Page titles are
  made unique, so two `M-101.dwg` in different folders do not share one.
Not proven in AutoCAD: all of it ([NEEDS-CHECKING group AF](NEEDS-CHECKING.md), AF12-AF15, AF18).

## D-90 - Sheets and viewports are made by the plug-in in .NET; COM stays the fallback; a drawing list is one call and one undo step

**Decided:** 2026-11-21, for issues #64, #65, #66, #39 and #40. **Status:** in force; extends D-27 and
D-40; known limit 23 is the reason.
`doc.PaperSpace` threw a bare Automation error on a sheet made with `Layouts.Add` (2026-11-09), took
`autocad_status` and `autocad_add_table(space="paper")` down with it on a sheet tab (2026-10-28, row
D33), and every `autocad_create_layout` answered "Outcome unknown: AutoCAD went busy" although its tab
was made (row D8). So:
- **The plug-in makes the sheet** (`create_layout`, Change): every refusal (name taken, no such
  plotter, sheet size or plot style table, a .ctb in a named-style drawing, copy source missing)
  comes before the layout is made, tried first on a page setup that is not in the drawing, because
  AutoCAD's layout manager is not trusted to take a layout back when a transaction aborts; should the
  page setup still fail, the layout is deleted once the transaction is aborted;
  the page setup is written through `PlotSettingsValidator` in the same transaction; `copy_from`
  copies the layout **with everything on it** (`CopyLayout`), which COM's `CopyFrom` never did (it
  copies the page setup only). The sheet is put on screen only after the commit, and with
  LAYOUTCREATEVIEWPORT off while it first opens, so AutoCAD adds no default viewport of its own:
  Heron cuts its viewports at a real scale.
- **The plug-in makes the viewport** (`add_viewport`, Change) in the layout's own block, from numbers
  the server works out as before (paper place, look-at point, twist, scale): the view centre is the
  look-at point turned by the twist (`SheetMath.ViewCentre`, bridge tests), the scale is
  `CustomScale`, then it is turned on and locked. No zoom, no model space through the viewport.
  The paper it reports is in the layout's paper units and the way round it plots (AutoCAD keeps it
  in millimetres and the media's own orientation).
- **The twist is the view twist** (VIEWTWIST): the picture turns anticlockwise by it, by the same
  rule as the view centre. So `align_to_ucs` on a UCS turned 23 degrees now gives 337 (-23), what
  PLAN leaves on that UCS; before, it gave +23, which by that rule turns the plan 46 degrees off.
  Found in review and reasoned from AutoCAD's display-coordinate rule, not measured: AF6 (and D15).
- **Clip** (`clip_outline` corners, checked here: closed, not crossing itself, with area; or
  `clip_handle`, a closed shape already on that sheet) sets the viewport's non-rectangular clip, as
  VPCLIP does, and the viewport takes the box round the outline as its place. Plug-in only: with an
  older plug-in a clip is refused and nothing is made, rather than a rectangular viewport passed off
  as clipped.
- **Annotation scale** defaults to `match`: the viewport's own scale, added to the drawing's list if
  missing (last, after every refusal, as D-81 does), so annotative text inside it shows at its size.
  Over COM it is tried with CANNOSCALE while in the viewport.
- **COM stays the fallback** for a plug-in without these operations (older, or `--no-bridge`); the
  answer's `made_by` says which made it. Over COM a busy AutoCAD after the layout is added is now
  answered from the drawing read back: the sheet is made, check its page setup (#40), or "Outcome
  unknown" naming the tab to look for.
- **Title blocks** go into `layout.Block`, never `doc.PaperSpace`, and no tab is switched for them;
  `get_space(doc, "paper")` falls back to the active layout's block; `autocad_status` reads each fact
  on its own and names the ones AutoCAD would not give in `unreadable` instead of failing whole, with
  the active sheet's count from its block, else from the plug-in (`active_sheet`, Read) (#39).
- **`autocad_sheet_set`** (#66, Change) makes a drawing list (number, title, scale, view) into
  layouts, viewports and filled title blocks. The whole list is checked first and every problem said
  at once; the run is one undo mark (the plug-in's steps run inside it), so one Ctrl+Z or Discard takes
  the set back. A sheet AutoCAD refuses part-way stops the run and the answer lists what was made,
  rather than undoing by itself; a sheet whose layout was made but whose viewport or title block was
  refused is listed too, as unfinished, so a retry is never told its name is taken. Not built on `autocad_sequence`: the sequence keeps one undo step per
  step (D-29), and a sheet's title block needs its viewport's fitted scale.
Not proven in AutoCAD: all of it ([NEEDS-CHECKING group AF](NEEDS-CHECKING.md), AF1-AF11, AF17). Whether the
plug-in's transactions land in the server's one undo mark is AF9.

## D-87 - Lights are listed and switched by the plug-in; the sun, default lighting and exposure are variables

**Decided:** 2026-11-21, for issues #62 and #63. **Status:** in force; extends D-42, whose "never
change DEFAULTLIGHTING behind the modeller's back" stands: only `autocad_switch_lights` changes it,
when asked in words. **None of these tools renders** (Ajmal's rule): they set lights, sun and
exposure, and Ajmal presses Render. `autocad_render` (Admin, types `-render`) was still on main as
the one exception when this was written; it was removed the same day (#158, the last bullet below).
- **List** (`autocad_list_lights`, plug-in `list_lights`, Read), like the Lights in Model palette:
  every light in model space, then in each block definition (not layouts, not xrefs), with handle,
  name, kind, on or off, intensity and its unit, Kelvin, layer, position, and for a light in a block
  the block's name and its number of inserts. The same answer gives the sun (on, date, time, place,
  and azimuth and altitude as AutoCAD gives them, their unit still to be checked), DEFAULTLIGHTING,
  LIGHTINGUNITS and the exposure, and says why a render may come out dark.
- **Switch** (`autocad_switch_lights`, plug-in `switch_lights`, Change): a light by handle, else
  every light of that name (a light inside a block definition repeats in each block), or all of
  them. One name not found refuses the whole switch and lists the names there are, so nothing is
  half done. A light in a block definition switches in every insert, which is what a light block is
  for. The sun (SUNSTATUS) and default lighting (DEFAULTLIGHTING) are plain variables written over
  COM, default lighting first, so the sun goes on in a viewport that already shows user lighting.
  If AutoCAD still asks its viewport lighting question, the dialog watch (D-66) closes it and names
  it; that is a live row.
- **Exposure** (#62, `autocad_set_render_exposure`, Change): the LOGEXP... variables belonged to
  the old renderer and are gone in 2027. The current renderer's Exposure (EV, -6 to 21, lower is
  brighter) and White balance (1000-20000 K) are documented as the variables EXPVALUE and
  EXPWHITEBALANCE (Autodesk help 2016-2023), so the tool writes those over COM, in the type each
  already holds, and reads them back. If this AutoCAD does not answer for one, nothing changes and
  the answer names the Render Environment & Exposure palette (RENDEREXPOSURE): known limit 22. The
  .NET API also has a per-viewport `PhotographicExposureParameters` (Exposure, WhitePoint), and the
  palette's own data class holds the current viewport's tone settings: that is the route to try if
  the variables turn out gone (ROADMAP), not built now, as which of the two the renderer reads is not
  proven.
- **Added 2026-11-21, `autocad_render` removed (#158):** Ajmal asked the parent session to decide
  ("What is the best thing you can decide that one"), and it decided to remove the tool. His rule is
  that Heron never runs the render; `-render` waits on prompts and can stall AutoCAD, and a scripted
  render has been reported to drop objects; an Admin-only exception would still let a chat hang
  AutoCAD with the Admin padlock on. So the tool, its level and its preset and size tables are gone
  (one tool fewer), and Heron has no tool that renders: it sets the camera, sun, lights and exposure,
  and the modeller presses Render. `autocad_preview` stays for a picture to look at. Live row F22 is
  marked removed; F23 proves the sequence ceiling with `autocad_run_lisp` instead. This supersedes
  D-33's "`autocad_render` drives that".
Not proven in AutoCAD: all of it ([NEEDS-CHECKING group AE](NEEDS-CHECKING.md)).

## D-86 - A camera view is a saved view with perspective and a lens; the sun's date is set on the viewport's sun; the visual style is read back

**Decided:** 2026-11-21, for issues #59, #60 and #61. **Status:** in force; extends D-42 and
replaces D-35's "the style cannot be read back" (D-35's typed VSCURRENT stands).
- **Camera view** (`autocad_add_camera_view`, plug-in `add_camera_view`, Change): one view record
  written through the .NET API with perspective on, the lens set, the target, and the direction from
  the target to the eye (the API's own meaning of ViewDirection), saved under a name and, unless
  told not to, put on screen with `SetCurrentView` (and warned about when the viewport is in 2D
  Wireframe, which draws no perspective). A layout's view of the same name is never replaced. The
  view's width and height are the lens's field at the target, so lens and size agree. The field is
  worked out across a 36 mm frame, as AutoCAD
  calls its lens a 35 mm camera's (50 mm: 39.6 degrees, 24 mm: 73.7 degrees); whether AutoCAD's own
  Field of view reads the same is a live row. No camera glyph is drawn, so CAMERADISPLAY does not
  matter. Rejected: DVIEW (it hangs), `entmake` of a VIEW record (it came back at 50 mm, 2026-11-09),
  typing CAMERA (it worked by hand, but its prompts differ between releases), and `-VIEW` (it keeps
  only what is on screen; `autocad_save_view(from_screen=true)` stays for that).
- **Sun date and time** (`autocad_set_sun`, plug-in `set_sun`, Change): AutoCAD has no variable for
  them; they live on the current model viewport's sun (DXF 91 = Julian day, 92 = ms after midnight).
  The .NET `Sun.DateTime` takes the calendar date and clock time, so the plug-in writes that, only
  the parts given, and makes the sun when the viewport has none. The sun hangs off the viewport
  record, which AutoCAD does not keep up to date as the view moves, so for this one operation the
  plug-in writes the live viewports into the drawing first and gives them back after. The place is
  three plain variables over COM: LATITUDE, LONGITUDE and TIMEZONE, the last as hours x 1000 plus
  minutes from a UTC offset (Qatar 3000, India 5030; read back, a last digit naming one place of
  several, as in 3001 or 9031, keeps its offset). A year outside 1900-2200 is refused before
  anything is written. The answer reads it all back, with the 91 and 92 values Heron expects, so a
  live check can compare them with `(entget)`. Model tab only.
- **Visual style read back** (#59): `autocad_set_3d_view` types VSCURRENT as before, then asks the
  plug-in (`current_view`, a Read operation, allowed inside its View job) which style the viewport
  has: the live view's, else the viewport record's, by its name in the drawing's visual style list.
  A different style from the one asked for is said in `visual_style_warning`, not counted as a
  failure: the record can be behind the screen (an independent review of PR #152), and
  `autocad_preview` is the proof. Without the plug-in the field is null with the reason, and the
  tool still works.
Not proven in AutoCAD: all of it ([NEEDS-CHECKING group AE](NEEDS-CHECKING.md)).

## D-85 - eTransmit is packed by Heron, into one folder, from what AutoCAD itself finds

**Decided:** 2026-11-21, building issue #114. **Status:** in force.
AutoCAD's transmittal COM library (AcETransmit) needs registering and was never tried here, so
`autocad_etransmit` packs the drawing itself. The plug-in lists what the drawing needs (a Read
operation, `list_dependencies`): images, PDF / DWF / DGN underlays and font files of the drawing and
of each loaded xref, and each layout's plot style, every file found with AutoCAD's own search
(`HostApplicationServices.FindFile`: the saved path, the drawing's folder, the support path). Xrefs,
nested too, come from the xref tree the server already reads (D-41's `autocad_xref_tree`). The
server then puts every file in **one folder** (or one zip) beside the drawing and writes a
`transmittal report.txt` of what was packed and what was missing. The saved paths are not
rewritten: AutoCAD finds an xref, image or font by its bare name in the drawing's own folder, as
eTransmit's "Put all files in one folder" relies on. Two different files with one name: the second
is listed as a clash, never renamed silently. Plot styles go in `PlotStyles`. The drawing is packed
as last saved, so a drawing with unsaved changes is refused; nothing is ever written over (a second
pack gets " (2)"). It writes files, so it needs the Publish padlock. Missing files are listed, never
guessed.

## D-84 - Overkill is worked out in Python; boundary, underlays and clips by the plug-in

**Decided:** 2026-11-21, building issues #112, #104 and #118. **Status:** in force; keeps D-03 and
D-50.
- **Overkill** (`autocad_overkill`) reads lines, arcs, circles and polylines over COM and works out
  in plain Python (`acad/overkill.py`, tested offline) what is a copy, what lies inside or overlaps
  on one line or one circle, and what lies on a polyline. The tolerance never adds up from one
  piece to the next: everything erased or merged lies within it of the kept line (or circle), and
  the kept one is only stretched along itself (found in review: a pair-by-pair check could turn a
  curve of short lines into one straight line). The first call lists it by handle with a `plan_id`;
  only `confirm=true` with that `plan_id` erases and stretches, so the confirm does exactly what was
  listed or nothing, in one undo step, and then the plug-in's erase question asks the modeller
  (D-50), as for every erase. The oldest object (lowest handle) is the one kept. A
  polyline is never broken or changed: Heron cannot do that in one safe step, so overlaps on
  polylines are listed, not fixed. Typing OVERKILL was not used: its dialog and prompts cannot be
  shown as a list first.
- **Boundary** (`autocad_trace_boundary`) is the plug-in's `Editor.TraceBoundary`. -BOUNDARY or
  BPOLY typed through AutoLISP or a command is **never** used: on a big plan it hung AutoCAD for
  over 100 s (Ajmal's note). The trace is kept small: with a window AutoCAD zooms there first, the
  objects crossing it are counted (over `most_objects`, 5,000 by default, it is refused untraced),
  and the view is put back after. The server waits at most `timeout` seconds (60 by default) for
  the answer, through a shorter wait on the plug-in call; a trace already running cannot be cut
  short, which the answer says.
- **Underlays and clips:** a raster image is attached and clipped over COM (`AddRaster`,
  `ClipBoundary`); a PDF / DWF / DGN underlay is attached, and an xref, block or underlay clipped,
  by the plug-in, which COM has no call for. An xref clip is XCLIP's spatial filter with the world
  outline taken into the block's own coordinates; an underlay clip is taken into the underlay's.
  Every outline is checked first (`acad/clip.py`): closed, at least three corners, an area, not
  crossing itself, arcs in short steps (1/10,000 of its size).

## D-83 - Excel ranges as linked tables, table cells by address, and copying between open drawings

**Decided:** 2026-11-21, building issues #117 and #106 (ribbon audit, #94). **Status:** in force;
adds to D-40, D-62, D-63 and D-75, which stand.
- **A real Data Link, made by the plug-in.** `autocad_table_from_excel` reads the sheet with
  `acad/xlsx.py` (D-69) first, so the range, the size and the cells Excel only *shows* as a date, a
  time or a percent are known before anything is made. Then the plug-in operation `excel_table`
  adds a `DataLink` (adapter `AcExcel`, connection string `file!sheet!range`, `SkipFormat`) to the
  drawing's Data Link Manager and sets it on a new table with `Cell.SetDataLink`, in one
  transaction. COM has no data-link call; the .NET names were read from Autodesk's reference
  packages for 2021 to 2027 and build without a warning, but have never run in AutoCAD (D-33).
- **When a link cannot be made, the table is filled, and says so.** A `.csv`, `link=false`, no
  plug-in to ask (`--no-bridge`), an older plug-in, or AutoCAD failing to make or read the link
  gives a table filled over COM with the sheet as it is now, `"linked": false` and
  `not_linked_because`. Nothing else falls back: HERONSTOP, a padlock turned off mid-job, or a
  refusal the modeller has to act on (no sheet tab for `space='paper'`, no such table style) stops
  the job, and "Outcome unknown" is never followed by a second table: the first may be there. A cell Excel only shows as a date, a time or a percent is left
  empty in a filled table and listed in `excel_converted` (the D-75 rule), never written as the
  number behind it. A linked table shows the range exactly: no title row is added to it.
- **`autocad_update_table_links`** (plug-in operation `update_table_links`) updates linked tables
  from their sheets in two steps, as DATALINKUPDATE does: each link reads its workbook again
  (`DataLink.Update`; a link keeps a cached copy), then the table takes the new values
  (`Table.UpdateDataLink`, `SkipFormat`). All of them or those named, in one transaction: one that
  cannot be read stops the job and nothing is changed. A table that is not linked is listed.
- **Cells by address.** `autocad_set_table_cells` counts rows and columns from 1 at the table's
  top-left cell, title and header rows included, the way an Excel address does ("B3" = row 3,
  column 2). Only cells whose text really changes are written (a change of case is a change),
  old -> new in `before_after` (D-62). A cell linked to Excel, content-locked, or inside a merged
  cell is listed and left alone. A cell past the end is refused unless `grow=true`.
- **Heron's tables keep their text in the vertical middle of each cell**, keeping the style's
  left / centre / right: per row type on a new table (`autocad_add_table` too, `SetAlignment`),
  per cell on a written cell, every cell on a linked one. Never worth failing a table for.
- **No empty title row.** A new table starts with a merged title row and a header row; with no
  title (or no headings) asked for, the tool sets `TitleSuppressed` (`HeaderSuppressed`) so the
  rows below are not written into one merged cell. Done in `autocad_add_table` too, which before
  wrote its headings into row 0 when there was no title (expected to fail on all but the first
  cell; not seen live, since every live table had a title). These are AutoCAD's older table flags: whether
  they still turn those rows into ordinary rows on today's tables is live row AC13.
- **The copy lands in the drawing Heron checked.** `autocad_copy_from_drawing` copies from
  another open drawing *into the active one*: the gate's wrong-drawing guard, its UNDO mark, Keep or
  Discard and the plug-in's change count all belong to the active drawing, so the change must be
  there. The source is only read; neither drawing is switched by the tool. COM `CopyObjects` with
  the target's space as owner brings the layers, linetypes, styles and blocks the target lacks; a
  name the target has is the target's own (listed in `already_here`). One `CopyObjects` per owner
  (model space, each layout), then a move from the base point. Previews (`dry_run`) write nothing.

## D-82 - Attribute definitions in make_block; ATTSYNC by the plug-in, values kept by tag

**Decided:** 2026-11-21, building issue #115 (ribbon audit, #94). **Status:** in force; adds to
D-25 rule 2 and D-40, which stand.
- **`autocad_make_block(attributes=[...])`** adds attribute definitions with COM
  `AcadBlock.AddAttribute` (height, mode, prompt, point, tag, value). Checked first, the way ATTDEF
  checks: a tag has no space or `!` and is stored in capitals; a tag only once; a constant
  attribute needs a default; constant and preset together are refused (pick one). Flags are
  AutoCAD's AcAttributeMode numbers: invisible 1, constant 2, preset 8. Positions are drawing
  coordinates, like the objects; one left out is stacked under the base point, 1.5 text heights
  apart; the height defaults to TEXTSIZE.
- **ATTSYNC is a plug-in operation** (`sync_attributes`), because COM cannot add an attribute to
  an insert already placed. The server plans it (`acad/block_attributes.py`, offline) and the
  plug-in does it in one transaction, by the same rule: a value already typed is **kept, matched
  by tag** (a tag that appears twice is matched in order); a tag the definition gained comes in
  with its default; a tag it lost, or made constant, goes. A kept attribute goes back to the
  definition's place, height and style (`SetAttributeFromBlock`), except one holding a field or a
  multi-line one, which is left exactly as it was so nothing typed is lost. The attributes kept stay
  where they are in the insert's list and the new ones follow, in the definition's order: Heron
  does not reorder them, and the server's plan says it the same way (a different order alone
  changes no tag).
- **Which inserts:** every insert of the block by its real name in model space and on every sheet
  (a dynamic block's `*U` copies included), or the handles given. An insert on a locked layer is
  left out and listed. Inserts inside other blocks' definitions are reached with `nested=true`
  ([#156](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/156), added the same day): every ordinary block definition is read for them (layouts are
  already covered, xrefs are another drawing's, `*U` copies are AutoCAD's own); off by default
  because it reads every definition and changes every copy of the block that holds them.
- `add_attributes` adds new definitions to an existing block first (positions from its base point,
  as the block is drawn; one with no position is stacked under the lowest attribute the block
  already has, so it never lands on one), then syncs, in the same transaction. The inserts are
  found in the shared scratch selection set: a named set of its own would cost an undo step. A `dry_run` writes nothing and says
  what each insert keeps, gains and loses.

## D-81 - Layer states and annotation scales go through the plug-in; isolate and merge are COM

**Decided:** 2026-11-21, building issues #107 and #108. **Status:** in force.
- **Layer states** (`autocad_layer_states`; listed by `autocad_list_layers`) are saved, restored
  and deleted by the plug-in with .NET's `LayerStateManager` (`layer_state`, `layer_state_names`).
  The issue said COM; COM's manager is reached only through a ProgID with AutoCAD's version in it
  and has no call that lists the states, and its calls could not be checked here, while the .NET
  calls (`SaveLayerState`, `RestoreLayerState`, `GetLayerStateNames`, the `LayerStateMasks`
  numbers) were read out of Autodesk's own reference assemblies for 2021 and 2027 (D-33).
- **Isolate** (`autocad_isolate_layers`) turns the other layers off, frozen or locked over COM,
  after saving the layers as they were as the layer state `HERON-ISOLATE` (on, frozen, locked, and
  the current layer in its description). The kept layers are turned on and thawed first, then one
  is made current if the current layer would be hidden, then the rest are hidden: AutoCAD will not
  make a frozen layer current, nor freeze the current one. Isolating again keeps that first state;
  `unisolate` restores it, puts the current layer back and deletes it; a refused restore puts the
  current layer back as it was, and a plug-in that cannot read the states is said, not taken for
  "nothing isolated". `autocad_layer_states` will not restore
  or save over that name, so the two cannot get mixed up.
- **Merge** (`autocad_merge_layers`) needs `confirm=true`. It moves objects on the old layers in
  model space and every layout (one selection per layer, the name escaped so `-`, `#`, `.` are not
  wildcards, then matched exactly), inside block definitions (not xrefs) and in block attributes.
  An old layer is deleted only when nothing failed to move off it, and is relocked if it is kept.
  Layer 0 and xref layers are refused, as old layers and as the target; the target must already
  exist.
- **Annotative** (`autocad_annotation_scales`, `autocad_list_annotation_scales`, and
  `annotative=true` on `add_text`, `add_mtext`, `add_dimension`, `dimension_run`,
  `add_multileader`): the plug-in uses `DBObject.Annotative`, `AddContext`, `RemoveContext`,
  `HasContext` and the `ACDB_ANNOTATIONSCALES` collection (`annotation_scales`,
  `set_annotation_scales`), all in the reference assemblies. A scale is found by name, else by its
  paper : drawing ratio; a missing 1:N is added to the drawing only when asked, and only after every
  check has passed (the scales to remove are found first, then each object is checked to keep one),
  so a refusal never leaves a new scale in the list. An annotative object keeps at least one scale
  (a removal leaving none is refused, nothing changed). Made annotative
  with no scale given, an object gets the current one. Heights stay in drawing units at the current
  scale, and the reply gives the paper height, so a wrong assumption shows at once (live row AB9).
- **A drawing tool's annotative step never fails the call** once the object is drawn: what did not
  happen comes back as a warning, so the chat does not draw it twice. A dimension that did not become
  annotative is given the drawing's DIMSCALE after all (or keeps its `dim_style`'s scale), so it is
  never left at plain style size. Without the plug-in the tool
  refuses before drawing anything. The object is drawn over COM and made annotative by the plug-in
  inside the same undo mark (live row AB10 proves the one Ctrl+Z).

## D-80 - A dimension run takes a named style per dimension; spacing is Heron's maths, the break is typed

**Decided:** 2026-11-21, building issues #37 and #116. **Status:** in force.
- **`dim_style` on `autocad_dimension_run` (#37).** The name is checked against the drawing's
  dimension styles before anything is drawn (an unknown one is refused, naming those it has), set as
  `StyleName` on each dimension, and the drawing's DIMSCALE is then **not** written over it: the
  style's own scale wins (`scale_to_write`). The style is never made current, because putting the old
  one back afterwards wipes the DIMSCALE override `autocad_drawing_setup` left on it. A dimension
  that will not take the style is deleted and listed in `failed`, not left at the wrong size (and if
  it cannot be deleted either, `failed` says it is still there). An
  annotative run is not given DIMSCALE either. The scale the first dimension took from the style
  comes back as `style_scale`, for live row AB1.
- **Dimension space (#116).** COM has no definition points on a rotated dimension, so it cannot move
  the dimension line without moving the extension line origins. The plug-in reads each dimension's
  direction and line point (`dimension_lines`, Read) and sets `DimLinePoint`
  (`move_dimension_lines`, Change); where each goes is `plan_spacing`, tested offline. The base stays
  put; every other parallel dimension keeps its side and its order out from the base and goes to
  1, 2, 3 ... spacings; 0 lines them up; one not parallel is skipped and named, and so is one whose
  normal is not +Z (its Rotation would be measured from world -X).
- **Dimension break (#116).** Neither COM nor .NET has a call for a break, so DIMBREAK is typed:
  Multiple, each dimension as `(handent "...")` (the handle checked as hex first, so nothing else
  reaches the command line), then Break or Remove. Anything not a dimension, in the other space, or
  on a locked or frozen layer is refused before anything is typed: DIMBREAK drops what it cannot
  pick, and with none left the typed `_B` would start BLOCK at the prompt. A prompt still open is
  cancelled and said. The breaks are not
  read back: the reply says to look with `autocad_preview`.

## D-79 - Explode, draw order, match properties, groups: plain COM, checked first

**Decided:** 2026-11-21, building issues #105, #111 and #110 from the ribbon audit (#94).
**Status:** in force; nothing here is proven in AutoCAD yet (NEEDS-CHECKING group AA).
- **Explode** (`autocad_explode`) calls the object's own `Explode` and returns the new handles.
  Autodesk's reference says it replaces the object, but forum reports say the original can stay;
  so Heron looks for the original afterwards and erases it if it is still there. The erase goes
  through D-50's question. A block with attributes is skipped unless `allow_attribute_loss=true`:
  exploded, an attribute shows its tag, not its value, so the values are listed in the answer.
  MINSERT arrays are refused. Exploding a part breaks drafting rule 2, so the tool says so.
- **Draw order** (`autocad_draw_order`) writes the space's own `ACAD_SORTENTS` table through its
  extension dictionary (`GetObject`, else `AddObject(..., "AcDbSortentsTable")`), with
  `MoveToTop` / `MoveToBottom` / `MoveAbove` / `MoveBelow`, as DRAWORDER does. All the objects (and the
  reference) must be in one space.
- **Match properties** (`autocad_match_properties`) copies named properties: the general six
  (layer, colour, linetype, linetype scale, lineweight, transparency) by default, `text_style` and
  `dim_style` on request or with `all`. Only what differs is written, before / after is listed
  (D-62), and a property the target does not have is skipped and said. A true colour is copied as a
  true colour. **Lineweight and transparency** also go on `autocad_modify_entity`: lineweight in
  millimetres as AutoCAD lists them, or hundredths (5 and up), or ByLayer / ByBlock / Default; a
  value AutoCAD does not have is refused. Transparency 0-90 (AutoCAD's own limit) or ByLayer /
  ByBlock, written to `EntityTransparency`.
- **Groups**: `autocad_list_groups` (Read) and `autocad_group` (Change: make, add, remove, ungroup)
  over the drawing's `Groups` collection. Names follow AutoCAD's symbol rules; a name taken is
  refused (use add); a missing name gets GROUP1, GROUP2 ... Ungroup deletes the group object only;
  Heron then checks every member is still there and says so if not.
- **Added the same day, from the review:** match properties and `autocad_modify_entity` write the
  layer last (moved first onto a locked layer, an object refuses its other properties; the answer
  still lists the layer first); a group whose objects cannot be added is not left behind empty.

## D-78 - Trim, extend, fillet, chamfer, break, join and stretch are worked out in Python

**Decided:** 2026-11-21, building issues #103 and #49. **Status:** in force; nothing here is proven
in AutoCAD yet (NEEDS-CHECKING group AA).
- **The geometry is Heron's own** (`acad/edit2d.py`, plain functions tested without AutoCAD, as
  the shape library is, D-30), not a typed TRIM or FILLET. A typed command waits for picks, and a
  command left waiting blocks everything after it (known limit 21). The tools read each object,
  ask the geometry for the new shape, and write it back by setting the object's own points:
  `StartPoint` / `EndPoint`, `StartAngle` / `EndAngle`, a polyline's `Coordinates` and bulges. Extra
  pieces are `Copy()` of the object, so layer, colour, linetype, extended data and the handle of the
  first piece stay. No plug-in change was needed.
- **In plan, on flat objects.** Everything is worked in world X and Y, as TRIM does with PROJMODE at
  its default. A sloping line, an arc or polyline on a tilted or flipped plane, and a polyline whose
  width changes along it are refused rather than flattened or stripped. One constant width is kept.
- **The rules a draftsman expects.** Trim removes the part pointed at, out to the next edge or to
  the end; edges count as drawn, not as if they ran on (EDGEMODE 0); edges are read once, before
  anything changes. Extend runs a straight end along its line and an arc end round its circle, to
  the nearest boundary ahead, both ends when no point is given. A closed polyline cut twice opens
  there; a circle cut or broken becomes an arc (a new object, so the circle's erase is asked about,
  D-50). Fillet and chamfer work on two lines (each keeps its end farther from the corner, or the
  side of `keep_points`; the new arc or line takes the first line's look; radius 0 is a sharp
  corner) or on one polyline's corners (it stays one polyline: bulges, D-30 rule 17). A corner next
  to an arc, or on a segment too short, is skipped and said. Join makes one line, one arc or one
  polyline, keeping the first object given where it can; a branch or a gap is refused with where.
- **Shape changes for #49**: `autocad_edit_vertex` (move, add, remove a polyline vertex; move a
  line's end) keeps the bulges, as a grip drag does; `autocad_stretch` moves the points inside a
  window, moves a circle, text, block or point whole when its base point is inside, and moves
  anything else only when it is wholly inside, listing the rest. No `Lengthen` yet ([#154](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/154)).
- **Safety:** an object on a locked layer is refused before anything is written, a failed write
  takes back the copies it made, the same object twice is refused, and a call with nothing to do
  opens no undo step (D-62). Each call is one undo step.
- **Added the same day, from an independent review of PR #153:** the copies are written before the
  object itself, so a copy that refuses leaves the object whole; an object's handle is read before
  it is written or erased; a fillet's new arc (or a chamfer's line) is made first and taken away if
  the lines refuse; join keeps a polyline it was given rather than making a new one; one rule for
  "straight" (a bulge under 1e-9, as `geometry.segments` has it) everywhere.

## D-77 - Quiet answers, and a busy answer names the command AutoCAD is in

**Decided:** 2026-11-21, from issues #44 and #47 (rows D8, D33). **Status:** in force; adds to
D-41, D-57 and D-62, which stand.
- **`quiet=true`** on `autocad_sequence`, `autocad_batch_draw`, `autocad_dimension_run` and
  `autocad_add_centre_marks` answers with counts and handles only (`core/quiet.py`). Numbers, words,
  `handle`, `handles` and every `..._handles` list (`new_handles` of a copy or an array) stay; the first 5 of what failed stay; every other list of objects goes and
  `left_out` says how many there were. Its handles are kept as `handles` when the answer had none,
  but never mixed into a `handles` already there (centre marks: the marks, not the circles). An object
  the call created keeps `{"created": true, "handle"}`, so Keep or Discard still finds what to take
  back. In a quiet sequence each step's answer is made quiet; a text answer is cut at 300 characters,
  an error never. Off by default, so every answer reads as before.
- **The plug-in's ping says `command`**: the command its tracker (D-41) sees the active drawing in,
  or null. It is read on the pipe thread, so it answers while AutoCAD is busy. An older plug-in
  leaves it out, and the server then says nothing about the command.
- **The gate asks only when a call ended on a busy AutoCAD**: `connection.busy_count()` goes up when
  the retry loop gives up on a busy AutoCAD (Outcome unknown, or "stayed busy") and when
  `autocad_run_lisp` never got to read its answer. Then the plain line names where AutoCAD is ("it is
  still in the HATCH command", "evaluating AutoLISP", "in no command now, so a redraw or a box held
  it") and what the plug-in counted so far ("after 2 added..." or "counted no drawing object ... so
  far"). Busy before anything was taken is REFUSED, "nothing was changed". A read gets one sentence
  in its answer instead, since a read has no plain line. The busy wording is used only when the
  answer itself says AutoCAD was busy: a sequence whose one step was turned away while the others
  drew is still DONE, "some parts failed".
- **An answer that never heard how the job ended is not DONE.** `autocad_run_lisp` with
  `timed_out: true` now reads OUTCOME UNKNOWN with the count so far; before, its line said DONE.
- **Left out:** a plug-in version bump (the parent session does it) and naming the command in the
  plug-in operations' own "Outcome unknown" (they already say it when AutoCAD never started them).
  Live rows Z5-Z9 NOT RUN.

## D-76 - An undo sent as a command is a write; long AutoLISP goes in pieces cut between forms

**Decided:** 2026-11-21, from issues #42 and #46 (known limits 3, 12, 21). **Status:** in force;
closes the gap D-15 named and replaces the 2,000-character refusal of 2026-11-09 for code of
several forms.
- **UNDO, U, REDO, MREDO and OOPS** through `autocad_send_command` are still sent outside an undo
  mark, but the write is marked just before the send. A busy AutoCAD after that is OUTCOME UNKNOWN
  in its own words ("sent twice, it would undo or redo one step more than asked"), never a second
  send. Busy before the send is still asked again: nothing reached AutoCAD. It also counts as a
  write for the gate, so `autocad_undo_last` no longer undoes past a raw UNDO. **The gate's own
  `UNDO _Back`** (Discard, and the end of a dry run) is marked the same way: a second Back would go
  past Heron's mark into the modeller's earlier work.
- **`autocad_run_lisp` cuts long code between its top-level forms** (`acad/lisp_forms.py`), never
  inside one, into pieces of at most 700 characters; several forms in one piece go inside
  `(progn ...)`. The pieces run in order inside **one undo mark**, each with the wrapper of known
  limit 21. A form up to 2,000 characters may stand alone; one longer is refused, with its number
  and how it starts. At most 12,000 characters and 20 pieces a call.
- **A piece that times out, leaves a command open or is refused stops the rest**, and the answer
  says which piece and what ran before it: a command split over two top-level forms is cancelled
  at the end of its piece, so the next piece would act on a half-done command. Stopped after a
  piece ran, the first line is OUTCOME UNKNOWN, never DONE or "nothing was changed".
- **The save, plot and export check reads the code as it is sent** (no comments), so a `"` inside a
  comment can no longer hide a `(command "_.QSAVE")` after it.
- **What is sent is compact**: comments go and spaces close up, outside strings only, so a `;`
  comment can never swallow the closing brackets on the command line, and the length counted is the
  code AutoCAD reads. Brackets and quotes are checked by reading the code, so `(princ "(")` is no
  longer refused. A busy AutoCAD as a piece is sent is now "Outcome unknown", not "check the LISP
  syntax". `USERS1` and `USERS2` are put back even when AutoCAD refuses the expression.
- **Left out:** catching a LISP error at once (`vl-catch-all-apply`) instead of waiting out the
  10 s; the wrapper stays as it was proven. Live rows Z1-Z4 and Z10 NOT RUN.

## D-75 - What a review of the new tools found, and the rules added

**Decided:** 2026-11-21, after an independent review of the code of PRs #124, #143 and #146.
**Status:** in force; adds to D-63, D-69 and D-70, which stand.
- **Excel's own typing is never written (D-69).** A number cell whose format shows it as a date, a
  time, a fraction or a percent (built-in formats 9-22, 27-36, 45-47, 50-58, or a custom format with
  d, m, y, h, s or %, quoted text left out) is read as `xlsx.Converted` and listed in
  `excel_converted`, not written: "1:100" typed in Excel would otherwise become "0.0694".
- **A tag named HANDLE, BLOCK or LAYOUT** gets " (tag)" after its column heading, and only the first
  column of each of those names is Heron's own. A row with values but no handle is listed.
- **A row is used only when its Block matches** the block that has that handle in this drawing; the
  workbook names the drawing it came from ("Exported from" on Read me), and the answer warns when
  it is applied to another one.
- **The folder check closes only what it opened (D-70):** decided by what AutoCAD had open before
  and after, never by the path alone.
- **Dry runs (D-63):** no UNDO mark is put down while AutoCAD is in a command (the mark would be
  typed into that command, and UNDO Back would then go past the job); a dry run that began no write
  and changed nothing counted sends no UNDO Back; a cancelled dry run still goes back to its mark,
  queued after the work on the COM thread.
- A cell reference with no column letter, a row past 50,000 or a column past Excel's last is a
  plain refusal, not a crash or a runaway list. A named button (D-74) goes to the first box with
  that title, so the field says to avoid a title many boxes share.

## D-74 - A command or expression may name one button for one box it expects

**Decided:** 2026-11-21, from Heron AI for Revit (issue #101, follow-up to D-66). **Status:** in
force. `autocad_send_command` and `autocad_run_lisp` take `expect_box` (the box's exact title) and
`press` (the button's text), both or neither. Before anything is sent, the server asks the plug-in
(`expect_dialog`, plug-in **1.7.0**) inside the running job; the plug-in takes it only from an
**Admin** job of this chat (a named button may be Yes or OK), one per job. `DialogWatch` presses
that button only on a box whose title is exactly the one named (ordinal, trimmed), only once, only
while that job runs, and only when the box has that button enabled; every other box still gets
Cancel, else No, else Esc. The note says `asked`, so the chat reads "Heron pressed Yes on it, as
this call asked", not "closed it". A refusal, or an older plug-in, stops the call before the
command is sent. The decision stays in `DialogWatch.cs`, tested offline.

## D-73 - AutoCAD always starts disconnected; no file can make it connect

**Decided:** 2026-11-21 by Ajmal PS, issue #141 (option 2 of three). **Status:** in force. Replaces
the "`autoConnect` stays a file setting" line of D-59.
`"bridge.autoConnect": true` in `heron-autocad.config` made AutoCAD connect to Heron at start without
the modeller's press of **Heron**. Every padlock was still off, so a chat could change nothing, but it
could read the drawing's name, path and contents without a click, and any program that can write
that file (an AI chat too) could switch it on.
- **Removed.** The plug-in no longer connects at start; the key is ignored like the old padlock
  lines. `HeronConfig` has no `AutoConnect` any more (a bridge test checks it stays gone).
- **Not taken:** keeping it with a warning in the docs (option 1), and allowing it only from the
  administrator's policy key (option 3). It was off on the owner's PC, so nothing changes for him;
  an office that wants it can ask for option 3 later.
- **Live row:** R10 (NOT RUN).
## D-72 - The offline gates run on Linux with pywin32 stand-ins; Windows-only tests skip, saying why

**Decided:** 2026-11-21 (issue #102). **Status:** in force. Cloud sessions run on Linux, where
pywin32 does not install, so three of the four gates could only say NOT RUN. `tests/winstubs/`
holds stand-ins (`pythoncom.com_error` and the `VT_*` numbers, a `VARIANT` that keeps its type and
value, `pywintypes.error`, the `ctypes` names `message_filter.py` needs); `tests/conftest.py` and
`tools/check_structure.py` put them on the path **only** when `pythoncom` cannot be found, so on
Windows and in Windows CI nothing changes. They talk to nothing. The tests that need Windows itself
are marked to skip off Windows with the reason: real named pipes (8 in `test_bridge.py`, and the C#
`[WindowsFact]` server test), the COM message filter on a real thread (5), Windows path rules (5),
CRLF in a Windows checkout (1). The stand-ins are test code, never a dependency of the server.
**Later the same day:** `.gitattributes` now gives `tools/release_files/*` CRLF on every checkout, so
a release built on any machine has Windows line endings, and that one test runs everywhere again.

## D-71 - The Companion page is a file per chat, not a server

**Decided:** 2026-11-21, from Heron AI for Revit's companion page (its docs/40, D-108; issue #91).
**Status:** in force. `autocad_companion` (Read) writes one HTML file per chat in
`%LOCALAPPDATA%\Heron\autocad\companion`; after that the gate rewrites it after every job in
that chat (`core/companion.py`, `gate.companion_state()`), and it reloads itself every 5 s. No
port, no listener, no script (a Content-Security-Policy of `default-src 'none'`), every value
escaped, so there is nothing on the PC to reach. The page shows only what the gate already holds
(activity, the drawing last checked, what `autocad_undo_last` could take back) and what
`autocad_companion` read in its own Read job (drawing, units, layout, view, selection, with the
time): no COM outside a job. Writing it never fails a job. Pages older than 7 days are removed.
Revit's editable tables and dashboard need the page to send things back, so a local server with
a token: left for a decision of its own. Design: [15 §3](15-sheets-folders-companion.md).

## D-70 - A folder of drawings is checked read only, one at a time, as a View tool

**Decided:** 2026-11-21, from Heron AI for Revit (its D-181, accepted there, not built; issue
#97). **Status:** in force. `autocad_check_folder` opens each `.dwg` read only, runs the check
list with that drawing's own project changes (`run_list(..., doc_of=...)`, the same code as
`autocad_checklist`), and closes it unsaved; a drawing already open is checked where it is and
left open; the modeller's drawing is made active again at the end. It changes which drawing is
open, never what is in one, so it is a **View** tool (like `autocad_open_drawing`) and needs no
Changes padlock. A drawing that will not open is NOT RUN with AutoCAD's reason; HERONSTOP leaves
the rest out. Not ObjectDBX: a database opened that way has no selection sets or system
variables, which the checks read. Design: [15 §2](15-sheets-folders-companion.md).

## D-69 - Attributes go to Excel and back; only the cells the modeller changed are written

**Decided:** 2026-11-21, from Heron AI for Revit (its D-182, D-183; issue #96). **Status:** in
force. Two tools, because a tool's padlock is a property of the tool (D-65):
`autocad_export_attribute_sheet` (Publish: it writes a new `.xlsx` next to the drawing, never over
one) and `autocad_apply_attribute_sheet` (Change). The workbook has an **Attributes** sheet to edit
and an **As exported** copy, so the compare (`acad/attribute_sheet.py`, offline) tells the
modeller's edit (written) from a change made in the drawing since (kept) and from both (a
conflict, listed, not written). A blank cell never empties an attribute. Only changed cells are
written, in one undo step, listed old -> new (`before_after`, D-62); nothing to write opens no undo
step. A `.csv` with a Handle column is accepted and compared with the drawing alone. The `.xlsx`
is written and read with the standard library (`acad/xlsx.py`): no new package. Design:
[15 §1](15-sheets-folders-companion.md).

## D-68 - One docked Heron palette: Activity with Undo by D-54's rule, saved commands run by a copy of the server

**Decided:** 2026-11-21, from Heron AI for Revit's Activity and Commands panes (issues #92, #93).
**Status:** in force; supersedes the last sentence of D-55 (a command run with no AI is now copied).
`HERONPALETTE` (or Heron > **Heron palette** on the ribbon) opens one `PaletteSet`, docked right,
with two tabs drawn in Heron's window style (D-45: Surface card, top strip, Ink header with the
heron, Ink insets, brand buttons); the palette's own title bar stays AutoCAD's. The rules live in
the bridge, tested offline (`ActivityLog`, `SavedCommandList`, `PaletteServer`); the add-in only
shows them and makes the AutoCAD calls.

- **Activity** lists Heron's change jobs (Change, Admin, Publish) in this AutoCAD, from every chat,
  newest first, 30 kept, with what the plug-in counted (D-50). Reads and views are left out.
  **Select** and **Zoom** take what the job made or changed (up to 500) and work whichever chat
  holds this AutoCAD, but not while a job runs, and only in the job's drawing. The palette's Zoom
  runs with undo recording off, so it leaves no step between the job and its Undo.
- **Undo** belongs to the modeller, like Ctrl+Z: no padlock, no chat, any chat's job. It uses
  D-54's rule, from what the plug-in itself knows: Heron's newest change job in this AutoCAD, a
  Change job that ended `done` and changed something, not itself an undo, in the drawing in front,
  nothing changed outside Heron's jobs since it ended (`JobChanges.ChangedSince`), UNDO on with more
  than one step (UNDOCTL), and with no UNDO mark (Ask to Keep was off at begin) no Heron zoom or show
  since. With the mark it is `UNDO _Back`, else `UNDO 1`, typed into AutoCAD; when UNDO ends,
  Heron checks that what the job made is gone, as `autocad_undo_last` does. Anything else is
  refused with the reason in plain words. A chat's `autocad_undo_last` stays limited to its own job;
  after a palette Undo it is refused, because the drawing changed since.
- **Saved commands** reads the files the server saves (`%LOCALAPPDATA%\Heron\autocad\commands`,
  D-55) every 2 s while the tab is open, so a command saved in a chat shows without a restart;
  search, fill the inputs (each typed value takes its example's type, a blank with a default is
  left to the server), **Run**. Run does not go round the gate and the plug-in does not replay the
  steps itself: it starts a copy of the server for that one run
  (`python -m autocad_mcp --run-saved request.json --acad-pid <this AutoCAD>`), which is a chat of
  its own to the plug-in. It runs `autocad_status` first (units, D-19), then `autocad_saved_command`
  through the same gate, hold, padlocks, Keep or Discard, erase question and HERONSTOP, prints one
  line `{"ok", "message"}`, and releases the hold so the modeller's chat is not kept out for 3
  minutes. While a chat holds this AutoCAD, Run is refused with "in use by another chat", as for any
  second chat. Every server writes `%LOCALAPPDATA%\Heron\autocad\server.json` (its Python) when it
  starts; that is how the palette finds one, so Run needs Heron to have run once on this PC.
- **Not copied:** a separate Commands pane (one palette with two tabs instead), and asking a
  running chat's server to run it (a stdio server has no way in from the plug-in).
- **Added after the merge (same day):** the palette's run never inherits a way round the gate or
  another chat's id from the environment AutoCAD was started with: `HERON_AUTOCAD_BRIDGE` is forced
  on, `HERON_CONVERSATION_ID` and `CLAUDE_CODE_SESSION_ID` are dropped (`PaletteServer.
  PrepareEnvironment`), and the server refuses `--run-saved` with the checks off. A job whose end
  never came stops counting as running after 20 minutes (`ActivityLog.MostJob`). While a palette Undo
  waits for AutoCAD, the plug-in refuses a new job's begin with a plain "try again" (`BlockedBy`,
  at most one minute), so the UNDO never lands inside a chat's job (#138).

## D-67 - Finding and explaining: why a job cannot run, what failed, a question gets a read tool

**Decided:** 2026-11-21, from the comparison with Heron AI for Revit (issues #88, #89, #90, #43).
**Status:** in force. Adds to D-48 and D-49. The ideas are Revit's `heron_why`, `heron_gaps` and
its question mode; the code is this project's own.

- **`autocad_why`** (Read) takes a job in plain words, finds its tool with the same search as
  `autocad://tools/find`, then lists what is in the way, worst first, each with what to do: no
  tool, a read-only server, the plug-in not installed, nothing connected, two AutoCADs and none
  picked, server and plug-in from different releases, a plug-in older than the tool needs (read
  from the tool's own "plug-in X or newer" line, so it cannot drift), a padlock off, an update the
  chat has not loaded. It says what it cannot see from files: an open command, a locked layer,
  another chat holding AutoCAD.
- **`autocad_gaps`** (Read) sums up the last N days (1-90) of the audit log: calls per tool,
  failures grouped by a plain reason with what to do, the slowest jobs. Drawings by file name
  only; reading the log (`autocad_gaps`, `autocad_why`) is not counted.
- **The audit line gets a `reason` word** when a call is refused or fails, from a fixed list in
  `core/audit.py` (`changes_off`, `not_connected`, `autocad_busy`, ...), worked out from the
  message. Only the word is kept, never the message, because a message can name layers, handles or
  folders. Lines written before this read as `other`.
- **Both tools need no AutoCAD.** The gate runs them like `autocad_use_autocad` (D-49): through
  `guarded`, audited, but without looking at AutoCAD first (`gate.NO_AUTOCAD_TOOLS`). They read
  only Heron's own files. Not a way round the gate: they are Read, touch no drawing, and the set
  is named in one place.
- **A plain question never gets a change tool first.** `autocad://tools/find/{phrase}` treats
  "how many...", "what ...", "which...", "is there..." as a question: the matches are only tools
  that read, and anything else that matched is listed apart under `would_change_the_drawing`.
  "does" and "do" are left out on purpose: "does the ductwork clash" is answered by
  `autocad_check_interference`, which makes solids. Measured on `tests/test_find_tool.py`: 84 of
  97 phrases first (80 before) and 97 of 97 in the top three (96), plus 13 new question phrases.
- **The audit folder never becomes relative** (#43): with `%LOCALAPPDATA%` unset, empty or not a
  full path, it is `~/AppData/Local/Heron/autocad/audit`, where Windows normally points it.
  `bridges_dir()` has the same pattern and is left for its own change.

- **Changed the same day by D-59** (the padlocks moved into AutoCAD's memory): `autocad_why`
  can no longer read them, so it names the padlocks a job needs (`needs_changes`, ...) as
  reasons that do not block, says it cannot see whether they are on, and never claims one is
  off. The refusal itself still names the padlock, and `autocad_gaps` counts it. A `dry_run`
  refusal (D-63) is logged with the reason word `no_dry_run`.
- **Changed again the same day (#140):** the plug-in's `ping` now carries its padlocks, so
  `autocad_why` asks the AutoCAD this chat works in and says which are on; only with no answer
  does it fall back to naming them without guessing (D-59, "Added 2026-11-21, after the merge").

Pinned by `tests/test_why_and_gaps.py` and `tests/test_find_tool.py`. Live rows: Group W.

## D-66 - A box AutoCAD opens during a Heron job is closed with Cancel and named

**Decided:** 2026-11-21, from the comparison with Heron AI for Revit (issue #83). **Status:** in
force; NOT RUN live (NEEDS-CHECKING group V). Adds to D-57 and [05 §24](05-known-limits.md#24-a-busy-autocad-turns-calls-away).
A box AutoCAD opens mid-job (a file dialog from a typed command, "Save changes?", an error message)
stalls every later call until the modeller presses Esc. Heron for Revit answers such a popup with
"no" and tells the chat; this is the same idea, written fresh for AutoCAD.
- **How it looks:** a background timer in the add-in, every 250 ms, only while a job runs, reads
  `GetLastActivePopup` of AutoCAD's main window. Chosen over `SetWinEventHook`: a hook needs a
  message loop on its own thread and fires for every object in the process, while a short poll
  during a job is all that is needed and starts and stops with the job. Nothing it calls sends a
  message to AutoCAD's windows (`InternalGetWindowText`, `PostMessage`), so a hung AutoCAD cannot
  hang it.
- **Which window counts** (`Heron.AutoCAD.Bridge/DialogWatch.cs`, tested offline): only while a job
  runs; only a modal box (AutoCAD's main window disabled) that can take input and has stood for
  400 ms; never a window that was open when the job began (that is the modeller's); never a Heron
  window ("Heron - ..." and the banner) and never while Heron's own Keep or Discard or erase
  question is up.
- **What it presses:** Cancel, else No, else Esc (a standard box gets its Cancel command, any
  other its ✕, which WPF, WinForms and MFC all treat as Cancel). **Never OK, never Yes.** One press
  per box; after 5 boxes in one job Heron stops pressing and says so.
- **What the chat is told:** a new op `dialogs {job}`; the server asks it after every job's work
  and adds `heron_dialogs` to the answer: "AutoCAD showed 'X'; Heron closed it with Cancel,
  nothing was kept from that step." A box still open after 2 s is said too, with "close it, read
  the drawing back". An older plug-in answers "unknown op", which means no boxes.
- **Not done:** a box the modeller opens *themselves* while a job runs cannot be told apart and is
  closed too ([05 §25](05-known-limits.md#25-the-dialog-watch-closes-every-new-box-in-a-job)).

## D-65 - A check list run is saved by its own Publish tool, as new files only

**Decided:** 2026-11-21, from Heron AI for Revit's QA reports (its D-178); issue #86. **Status:** in
force. `autocad_checklist_report` runs a list exactly as `autocad_checklist` does and saves the run
next to the drawing as `<drawing> - checklist <list> - <date>.xlsx` and `.html`. It is a separate
tool, at **Publish**, and not a `report` option on `autocad_checklist`: a tool's padlock is a
property of the tool and is never worked out from what the caller passes (`core/risk.py`), so a
"save" option on a Read tool would have written files with the Publish padlock off. Never
overwrite: when either file of the pair is there, the next number is used (` (2)`, ` (3)`, at most
999), and each file is opened in exclusive-create mode, so a file that appears in between is not
replaced either; if the page cannot be written the workbook just made is removed. An unsaved
drawing has no folder and gets no report. The workbook is written with the standard library (an
`.xlsx` is a zip of XML parts): `openpyxl` was not a dependency, and adding a package means every
PC reinstalls ([05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)) for one sheet of
text. Known limit: one sheet, text and numbers only, no colours in Excel (the HTML page has them).
**Later the same day:** the workbook is now written by `acad/xlsx.py` (D-69's writer), so Heron keeps
one `.xlsx` writer: a Summary sheet and a Check list sheet with its header row frozen; every cell
is text. Still no colours in Excel.

## D-64 - Check lists: NO DATA, office lists with project changes, PASS is not "complies"

**Decided:** 2026-11-21, from Heron AI for Revit's D-165, D-169 and D-179; issues #84, #85, #87.
**Status:** in force. Extends [D-52](#d-52---check-lists-are-the-modellers-sentences-on-a-fixed-catalogue).

- **Four results.** PASS (the checked value is met), FAIL, **NO DATA** (could not decide: what the
  check needs is missing - no such title block, xrefs unreadable, no text to compare, or only part
  of the objects read when nothing wrong was found in that part) and NOT RUN (switched off for this
  project). NO DATA is never counted as a PASS: the verdict is FAIL if anything failed, else NO DATA
  if anything could not be decided, else PASS. Before this, a missing title block was NOT RUN and a
  run capped at `max_entities` could still say PASS. The same holds for title blocks, and for
  `autocad_check_standards`: after a capped read with nothing found, `passed` is `null`, not `true`.
- **Coverage line on every run:** "2 of 4 decided, 1 no data, 1 not run" (decided = PASS + FAIL).
- **Office and project.** The office list is the saved list,
  `%LOCALAPPDATA%\Heron\autocad\checklists\<name>.json`, as in D-52 ('before issue' ships with
  Heron); an office shares one by copying that file to each PC. A project's changes are kept per
  project folder (the folder the drawing is saved in, as for the notes, D-53) in
  `%LOCALAPPDATA%\Heron\autocad\checklists\projects\`, never in the drawing or its folder. A
  change names an office check by its `id` and may set only **severity**, **target** (new values for
  that check's own parameters) and **on**. Adding a check, or changing what one does (its check,
  label, clause, advice, or a parameter it does not have), is refused naming the line: no hidden
  logic in a project. If the office list changes so a project change no longer fits, the run stops
  and says how to set or clear them. Each run names every check it used (`checks_used`) and where
  it came from (office / project), and a changed line says what changed from what.
- **A read that failed is NO DATA too** (later, #211): a dimension whose size or a text whose
  height could not be read makes its check NO DATA unless a failure was found among the rest; the
  block table is read strictly for `xrefs_found`, so a damaged table is NO DATA, never "no xrefs";
  a busy AutoCAD is raised for the retry. `checklists.gather` has its own tests.
- **PASS is not "complies".** PASS means the checked value is met, for what Heron read, against the
  source named on the line (its clause, else the list). `autocad_checklist`,
  `autocad_checklist_report` and `autocad_check_standards` carry the same `pass_means` sentence; no
  answer says a drawing complies; [DISCLAIMER.md](../DISCLAIMER.md) says it in plain words. Heron
  never signs a drawing off.
## D-63 - Any change tool can run as a dry run, inside Heron's UNDO mark

**Decided:** 2026-11-21, from Heron AI for Revit (its D-155). **Status:** in force.
`dry_run=true` on any Change tool runs the job for real inside an UNDO mark (D-18), takes the
plug-in's count, then goes `UNDO _Back` to the mark and checks every object it made is gone, the way
Discard does. The answer is the tool's own answer with `NOTHING CHANGED - a dry run: it would have
made ...` first (D-62); the handles in it no longer exist, and it says so. No Keep or Discard and no
erase question are asked, since nothing is kept; the banner says "Dry run: ...". The gate gives it,
so no tool was edited: `tool_errors` adds the argument to every Change, Publish and Admin tool that
has no `dry_run` of its own, and passes it to the gate, never to the tool. Tools that already had
one keep their meaning: a preview that writes nothing (annotate, convert, dimensions, patterns,
settings, shapes, text tools, sequence, saved commands). Refused before anything is sent: every
Publish and Admin tool (a file written, a command or AutoLISP run cannot be taken back by an UNDO
mark; the argument is there so a dry run is refused, never ignored and run for real), and
`autocad_undo_last`. A dry run needs UNDO on (UNDOCTL), or it is refused and nothing runs. If going
back fails, or a new object is still there, the answer is OUTCOME UNKNOWN, naming them. A dry run
leaves nothing for `autocad_undo_last`, since the undo history moved. A step inside a sequence
cannot be a dry run on its own. Not proven live: that `UNDO _Back` takes back every kind of change
(layers, variables, plug-in operations) as it does objects (rows T4-T5).

## D-62 - Every change answers with one plain line first

**Decided:** 2026-11-21, from Heron AI for Revit (its D-168, and its failure answers).
**Status:** in force. A Change, Admin or Publish job's answer starts with one line: `DONE`,
`NOTHING CHANGED`, `REFUSED` or `OUTCOME UNKNOWN`, a dash, one plain sentence; then a blank line and
the tool's own answer, unchanged. It is added in one place, the gate (`core/answers.py`, called from
`core/gate.py`), so no tool can forget it, and saved-command runs and sequences get it the same way.
The word comes from facts, not from what the tool says it did: the plug-in's count of objects added,
modified and erased (D-50), whether a write began at all, Keep or Discard, and whether Heron's UNDO
mark (D-18) was down. Rules: a padlock or guard refusal is REFUSED (nothing was sent); a tool error
with nothing counted is REFUSED; a tool error after objects changed, or "Outcome unknown", is OUTCOME
UNKNOWN and says whether the UNDO mark is there; a Discard is NOTHING CHANGED; a Change job that
began no write is NOTHING CHANGED. The count is of drawing objects only, so a job that wrote and
counted nothing (a new layer, a variable) is DONE, said carefully, and Admin and Publish jobs are
never NOTHING CHANGED (a save, a command or a variable is not counted). Only with the plug-in on:
with `--no-bridge` there is no count, so there is no line. Reads and views have none. Scripts and
tests that parse answers drop the line with `answers.body()`; steps inside a sequence still see the
tool's own answer, so "Error:" still starts a failed step there.
**Before and after** (from Revit's D-156): `autocad_modify_entity`, `autocad_set_attributes`,
`autocad_find_replace_text`, `autocad_set_dynamic_properties`, `autocad_create_layer`,
`autocad_set_layer_state`, `autocad_set_current_layer`, `autocad_delete_layer`,
`autocad_set_variable` and `autocad_drawing_setup` add `before_after`: one row per value changed,
naming the object (`handle`, or `layer` / `variable`), the `property`, `from` and `to`; the first 50,
then `before_after_more` counts the rest. They read each value first and write only what differs, so
asking for what is already there writes nothing and leaves no undo step; an empty `before_after`
then lets the line say NOTHING CHANGED even for a layer or a variable, which the count cannot see.
**No empty undo step** (issue #80, Revit's D-160): only that part is done. A kept job that changed
nothing is not taken back afterwards, because whether AutoCAD keeps an entry for an empty undo group
or a lone mark is not known; one more `UNDO` would then undo the modeller's own last change. Written
up in [05 §26](05-known-limits.md#26-a-job-that-changed-nothing-may-still-leave-an-undo-step), live
row T7.

## D-61 - A chat reopened after a restart keeps its hold

**Decided:** 2026-11-21, from Heron AI for Revit (its D-188). **Status:** in force.
The plug-in lets one chat at a time into an AutoCAD (the hold). Each server process made a new chat
id, so when the Claude app restarted and reopened the same chat, the new server was a stranger and
its own hold refused it for three minutes. The server now takes its id from, in order:
`HERON_CONVERSATION_ID` (a script or a developer fixes it); then the host's own chat id,
`CLAUDE_CODE_SESSION_ID`, as `sha256("heron-conversation:" + id)`, first 32 hex characters (the
host's id is never sent as it is); then a new random id. The same chat gives the same id; two chats
give two. Only the server itself follows the host (`follow_host_chat()` in `server.main`): a
command-line script such as `tools/live_check.py`, run from a chat's terminal, imports the same
modules but stays its own chat, so it never takes or keeps that chat's hold by accident, and
`tools/protocol_check.py` starts its server without the host's variable. Not proven live: whether
Claude Code passes that variable to MCP servers, and keeps it on a resumed chat (row T1). Without
it, nothing changes: a new id, as before.
## D-60 - A Windows policy can hold a padlock off

**Decided:** 2026-11-21, from issue #77 (the idea of Heron AI for Revit's D-166, layer 3; no files
copied). **Status:** in force.
For an office that installs Heron for many modellers. The plug-in reads
`HKLM\SOFTWARE\Policies\Heron\AutoCAD`, its own key, so an office can set AutoCAD apart from Revit.
DWORD values `AllowChanges`, `AllowPublish`, `AllowAdmin`: **0 holds that padlock off**. The text
"0" counts too, for a value typed as a string by mistake. 1, any other number, no value or no key
leaves the padlock to the modeller.
- **Read fresh on every call**, so a policy pushed while AutoCAD runs applies at once. A padlock it
  holds is also put off in memory: lifting the policy never turns it back on without a click.
- **Shown:** Settings draws the padlock as **HELD**, with "A Windows policy on this PC holds this
  off.", and it cannot be pressed. A chat is told "Changes is held off by a Windows policy on this
  PC ... Only the PC's administrator can lift it." (`Texts.ChangesHeld` and the Publish and Admin
  ones). The refusal stays `refusedBy: "Changes"`, so the server needs no change.
- **A key that cannot be read holds nothing.** Only an administrator can make HKLM unreadable or
  write it, so failing open here gives no program the modeller runs any power. The 64-bit view is
  read, as AutoCAD 2021 and later is 64-bit only.
- **Ask to Keep has no policy.** Not asked for; easy to add the same way.
- **Tested off Windows:** the reading sits behind `IHeronPolicy`; the bridge tests use a fake, and
  the real `WindowsPolicy` is only checked never to throw. Live rows R5-R7 NOT RUN.

## D-59 - The padlocks live in AutoCAD's memory; no file can turn one on

**Decided:** 2026-11-21, from issue #76 (the idea of Heron AI for Revit's D-166; no files copied).
**Status:** in force. Replaces the "saved in a file, read fresh on every call" part of D-16 and
[06](06-heron-plugin.md); the fail-closed rule of D-16 stays for what the file still holds.
The padlocks were saved in `%APPDATA%\Heron\autocad\heron-autocad.config` and read on every call,
so any program that can write a file, an AI chat included, could turn one on without the
modeller's click, skipping "turning a padlock on asks first".
- **In memory only** (`Bridge/HeronPadlocks.cs`). Every AutoCAD starts with Changes, Publish and
  Admin **off**. Nothing is read from or written to a file for them.
- **Ask to Keep starts off, as before** (Ajmal's choice, 2026-11-21), and lives in memory too: no
  file can switch it on or off. A modeller who wants it turns it on in Settings after each AutoCAD
  start.
- **Only the modeller's click moves a switch:** in Settings, or in the same question
  `HERONCHANGES` / `HERONPUBLISH` / `HERONADMIN` open (kept for command-line users; they ask exactly
  as Settings does, and a typed command sent by a program still needs that click). Turning off
  still never asks. The pipe has no request that reaches the padlocks.
- **Each open AutoCAD has its own padlocks.** Before, the file shared them between AutoCADs. Own
  padlocks are the simple answer: what the modeller unlocked is the AutoCAD in front of them.
- **The file keeps** `bridge.autoConnect` and `ui.activityBanner` only. The old padlock lines are
  ignored, never read, and the plug-in no longer writes the file. `autoConnect` stays a file
  setting: it only connects, and with every padlock off a chat can then read but change nothing.
  Since D-73 `autoConnect` is ignored too.
- **`autocad://diagnose`** no longer reads padlocks from the file: it would have reported stale
  lines as on.
- **Added 2026-11-21, after the merge:** `autocad_why` (D-67) still read the padlocks from that
  report, so it said every padlock was off even with Changes on. Now the plug-in's `ping` answer
  carries `padlocks` (changes, publish, admin, askToKeep) and `held` (what a D-60 policy holds),
  read-only; `autocad_why` asks the AutoCAD this chat works in, and a held padlock gets its own
  reason (`admin_held`: ask the PC's administrator) instead of "type HERONADMIN". No answer
  (nothing connected, several and none picked, a plug-in older than 1.6.0) keeps #134's rule: the
  padlocks are named (`needs_changes`...), never guessed, and do not block. Pinned by
  `tests/test_padlocks_from_plugin.py` and the bridge `PadlockTests`.
- **Added 2026-11-21, the guard's two gaps (issue #142):** it now also refuses an Edit or Write of
  a script (`.ps1`, `.bat`, `.cmd`, `.py`, ...) whose content would write either target when run
  later, except in this repository's own `tests/` and `.claude/hooks/`. For `gh` and `git`
  commands it no longer looks inside quoted text (an issue body, a commit message), so mentioning
  the file is not taken for writing it; a redirect outside the quotes is still refused.
- **A guard for Claude Code in this repository:** `.claude/settings.json` runs
  `.claude/hooks/guard_padlocks.py` before every Edit, Write and shell command, and refuses one that
  would write `heron-autocad.config` or the D-60 policy key (exit 2). It catches the plain ways, not
  every way: it is the second guard, the first is that no file can turn a padlock on. If Python
  cannot be found the step goes ahead with a warning, so a fresh clone is never locked out.
  `.gitignore` keeps everything else in `.claude/` (local settings, worktrees) out of git.
- Tested offline: `PadlockTests`, `ConfigTests` (bridge), `tests/test_padlock_guard.py`,
  `tests/test_diagnose.py`. Live rows R1-R4 and R8 NOT RUN.

## D-58 - autocad_run_lisp waits through refused reads; it puts the variables back patiently

**Decided:** 2026-11-20, from the Luxury Suite 3 rehearsal of 2026-11-18. **Status:** in force.
After a layer-off or a `-VIEW _R` of a camera view in a heavy realistic drawing, `autocad_run_lisp`
said "timed out" in 0.2-0.5 s for an expression that had run: the first read of USERS1 that AutoCAD
refused while redrawing ended the wait. Now a refused read is not an answer: the wait goes on to its
bound, `LISP_POLL_ATTEMPTS` reads and `LISP_POLL_ATTEMPTS x LISP_POLL_DELAY` (10 s), whichever comes
first; with the D-57 filter's 3 s for the whole call and the restores, a still-busy AutoCAD gets an
answer in about 15 s at most. If AutoCAD never let one read through, the note says it
stayed busy and the expression probably ran, not "a LISP error". USERS1, USERS2 and OSMODE are put
back with up to `LISP_RESTORE_TRIES` (5) tries each; one still not put back is named in the note,
so his object snaps are never left off without a word. Pinned by `tests/test_busy_autocad_1118.py`.

## D-57 - A call AutoCAD turns away is asked again by a message filter, not by re-running the tool

**Decided:** 2026-11-20, from the same rehearsal. **Status:** in force. Adds to D-02 and keeps D-15.
`autocad_create_layer` stopped with "Could not create layer 'A-ANNO-TTLE': Call was rejected by
callee." while drawing tabs were switched. The tool-level retry of D-02 already existed; it never
saw the refusal. `ensure_layer` read the refused `Layers.Item` as "no such layer" and wrapped the
refused `Layers.Add` in a plain error; and since `undo_mark` had begun, D-15 would have refused a
re-run anyway. A second retry loop in `connection.run` would have changed nothing.
The fix works one COM call at a time. `RPC_E_CALL_REJECTED` and `RPC_E_SERVERCALL_RETRYLATER`
mean AutoCAD turned the call away without carrying it out, so asking for that one call again can
never draw anything twice. `core/message_filter.py` registers a COM message filter on the worker
thread. pywin32 has no `CoRegisterMessageFilter`, so it is a small static ctypes object.
- **The filter's rule:** its `RetryRejectedCall` asks again after 100 ms (250 ms after the first
  second), for those two refusals only. Anything else goes straight back. If Windows refuses the
  filter, Heron works as before.
- **The budget is per job, not per call:** `BUDGET_MS` (3 s) is the most one piece of work on the
  worker waits, in all. The worker resets it as it picks up each job. Many places swallow a
  refused call and go on to the next, so 3 s for each call would have held the only COM thread
  for minutes. Once a job has spent its 3 s, every refusal fails fast, as before.
- **The tool-level window:** `_with_retry` now also stops at `RETRY_WINDOW` (10 s), so its 40
  attempts can never be stretched past that by the filter's waits.
- **The wording:** `com_message` words those two refusals as "AutoCAD was busy and kept turning
  the call away", so the dozens of messages built from it say busy, not broken.
- **The swallowed refusals:** `ensure_layer` and `ensure_linetype` let a busy refusal go up as it
  is, instead of taking it for a missing name.
- **Left out:** the optional `dim_style` input for `autocad_dimension_run`. It cannot be proved
  without AutoCAD, and done wrong it gives wrongly sized dimensions
  ([ROADMAP](ROADMAP.md)). Live rows Q1-Q5 NOT RUN.

## D-56 - The installer keeps the version it replaces; releases are built from a tag

**Decided:** 2026-11-15, from Heron AI for Revit's installer (install-backup, the update check
that never installs, the check after install, the Store-app trap) and its release workflow.
**Status:** in force. `Install.ps1` reads both versions from `PackageContents.xml`, copies the
installed bundle and server to `%LOCALAPPDATA%\Heron\autocad\previous` before replacing them,
puts them back if the copy fails, and checks the version and the server's size afterwards.
`Rollback.bat` shows both versions and asks before swapping back. `CheckForUpdate.bat` asks GitHub
for the latest release and only says so. A folder under `AppData\Local\Packages` is refused,
because files written from an app's private storage never reach AutoCAD. `release.yml` builds on
GitHub's Windows machine from the tagged code, refuses a tag that is not `v` + the version in
`Directory.Build.props`, writes the zip's SHA-256 to `checksums.txt`, and publishes a pre-release.
The bundle's `AppVersion` is read from `Directory.Build.props`, so it can never differ from the
DLLs' version again.

## D-55 - Saved commands are sequences with named inputs

**Decided:** 2026-11-15, from Heron AI for Revit's saved commands (its docs/49). **Status:** in
force. A job worked out once is kept on this PC as the very steps `autocad_sequence` takes, with
`{{input}}` where a value changes; a value that is a whole `{{input}}` keeps its type (a number
stays a number). Saving checks every step as a sequence would, with each input's example, and
refuses an input used but not declared, declared but not used, or without an example. Running
fills the inputs and calls the sequence's own body inside the saved command's one job: the same
gate, Changes padlock, Keep or Discard and HERONSTOP check between steps. A saved command cannot run
another, and a sequence cannot hold one. Heron AI's docked palette that runs a command with no AI
is not copied: the server lives in the chat, so the chat runs it, with one call and no planning.

## D-54 - "Undo Heron's last change" only when nothing else changed since

**Decided:** 2026-11-15, from Heron AI for Revit's undo guard (its D-157). **Status:** in force.
Ctrl+Z undoes whatever came last, which may be the modeller's own work. `autocad_undo_last` undoes
Heron's last change in this chat only when: it is the active drawing; the plug-in saw no entity
added, modified or erased outside Heron's change jobs since (`since_last`, from the same database
events as D-50); and Heron itself did nothing since but read. With Ask to Keep on, the job's UNDO
mark makes it exact (`UNDO _Back`, then the created handles must be gone). With it off there is no
mark (D-18 is kept: no mark unless asking), so it is one `UNDO 1`, refused if Heron zoomed or showed
anything since, because that step would be the zoom. A raw command or a save after the change
leaves nothing to undo this way. One level only. `autocad_activity` lists the chat's jobs (reads
left out) from the gate's own record.

## D-53 - The modeller's answers are kept per project folder

**Decided:** 2026-11-15, from Heron AI for Revit's design basis (its D-33, and its lesson D-113: an
id inherited from the template made new projects reuse another project's answers). **Status:** in
force. A project is the folder a drawing is saved in, which a template cannot carry over; an unsaved
drawing keeps nothing. `autocad_project_notes` keeps a short named answer with the modeller's own
words and the time, in `%LOCALAPPDATA%\Heron\autocad\projects`, never in the drawing.
`autocad_status` hands them to every chat as `project_notes`, and the server instructions say: use
them, ask only what is missing, keep only what the modeller said.

## D-52 - Check lists are the modeller's sentences on a fixed catalogue

**Decided:** 2026-11-15, from Heron AI for Revit's QA checklists (its docs/50). **Status:** in
force. A check list is a named list on this PC; each line is the modeller's own sentence mapped to
one of nine catalogue checks (layer 0, Defpoints, ByLayer colour and linetype, overlapping
dimensions, layer names by pattern, xrefs found, title blocks filled, text heights), with severity,
clause and advice. Running reads the drawing once and changes nothing; each line is PASS, FAIL or
NOT RUN with the reason, never a silent pass. "before issue" ships with Heron. No free-text rules:
a check Heron cannot do is refused when the list is saved, naming the line.

## D-51 - An emergency stop the modeller presses in AutoCAD

**Decided:** 2026-11-15, from Heron AI for Revit's `HeronStop` (a stop message, sticky until
restart). **Status:** in force. **Stop Heron now** in the Heron menu, or `HERONSTOP`, marks the
plug-in stopped: `begin`, `send_quiet` and `run` are refused with "The modeller stopped Heron",
while `end`, Keep or Discard, `changes` and the erase question still answer, so a stopped job can be
put back. The command running now gets Esc. `ping` says `stopped`, and `autocad_sequence` asks
between steps. A refused `send_quiet` used to make the server type the batch over COM itself; for a
stop it now ends the call instead. Sticky until picked again (not until restart: the modeller has
no other way to lift it without closing AutoCAD). Known limit: a batch already handed to AutoCAD's
input queue runs to its end; Esc in AutoCAD is the only way to cut it.

## D-50 - The plug-in counts what a job really did; every erase gets a human yes

**Decided:** 2026-11-15, from Heron AI for Revit's changed-set report and delete question (its
D-142). **Status:** in force; amended by [D-123](#d-123---the-erase-question-can-be-switched-off-in-settings-it-is-on-at-every-autocad-start)
(2026-11-22, Ajmal asked): the modeller may switch the erase question off in Settings until AutoCAD
restarts. The server only knew what a tool said it did, and the delete check
was the chat setting its own `confirm=true`. Now the add-in hooks `ObjectAppended`,
`ObjectModified` and `ObjectErased` on every drawing and counts (`JobChanges`) while a Change, Admin
or Publish job runs: entities added and modified; entities and table records (layers, blocks,
styles) erased. An object made and erased in the same job is neither; one an UNDO brings back is no
longer erased. The server adds the count to the result (`heron_changes`) and, when the job erased
anything and Keep or Discard is not being asked, asks the plug-in to ask the modeller
(`ask_erase`). Anything but a clear "keep them erased" un-erases them in one transaction; if the
box could not be shown in time, they are brought back as soon as AutoCAD is free.

## D-49 - One AutoCAD connected is the one; two need a pick, and Heron never moves on

**Decided:** 2026-11-15, from Heron AI for Revit's session binding (its docs/25). **Status:** in
force; closes A15. `GetActiveObject` gives whichever AutoCAD registered first. Heron now reads the
address files the Heron button writes: one AutoCAD connected is used whatever COM gives; two or more
and none picked refuse every call but `autocad_use_autocad` (which runs without probing a drawing,
like status, and is audited); a picked one that closes or disconnects stops Heron with "never moves
on". A second AutoCAD is reached through one of its open drawings in Windows' Running Object Table,
so an AutoCAD with no saved drawing open cannot be reached, and says so. Picking resets the units
check: the other AutoCAD's drawing may be in other units.

## D-48 - "Diagnose Heron" is a resource that needs no AutoCAD

**Decided:** 2026-11-15, from Heron AI for Revit's `heron_diagnose`. **Status:** in force.
The question after an update is "why does it not work", and the answer is in files: the plug-in
bundle, the address file the Heron button writes, the padlock file, and the server's own code
against what is on disk. So `autocad://diagnose` reads only those, never COM and never a drawing,
and answers with AutoCAD closed. It is a resource, not a tool, because every tool goes through the
gate, which refuses when AutoCAD is not reachable: the one moment a diagnosis is needed most. It
never prints the session token. `autocad_status` carries the server and plug-in versions and says
when the chat still runs code older than its files.

## D-47 - A raw command or AutoLISP may not save, plot or export

**Decided:** 2026-11-15, from Heron AI for Revit's run guard. **Status:** in force.
Saving over a shared drawing is the one change Ctrl+Z cannot take back, and the tools that save or
export need Publish. Admin alone let `autocad_send_command` and `autocad_run_lisp` type QSAVE or
-PLOT. Two layers now: the server refuses a command string or LISP that names one of these commands
(or calls `vla-save`, `vla-saveas`, `vla-plottofile`...) and points at the typed tool; the plug-in
vetoes the same commands (`PublishGuard`) through `DocumentLockModeChanged` while a Change or Admin
job runs and for 3 s after it, when Publish is off. Read, View and Publish jobs are not watched: a
preview plots to a PNG through COM inside a Read job. The modeller's own Ctrl+S outside a job is
never touched. Known gap: an office LISP that saves through ActiveX inside a routine the server
cannot read is not caught by either layer.

## D-46 - A texture's real size is written as the map transform's diagonal

**Decided:** 2026-11-08, after the bedroom + bathroom model: 11 library textures all rendered as a
flat colour until each material's diffuse map matrix was rewritten by hand. **Status:** in force;
replaces D-42's "a texture's real-world size is not set".
AutoCAD keeps a map's size in its 4x4 map transform (the material's 16 DXF group-43 values). A map
made with the identity repeats the image every 1 drawing unit, 1 mm in a metric drawing, which
renders as a flat colour. Setting indices 0, 5 and 10 to 1/size and 15 to 1 was proven by hand that
day (walnut grain at 1000, marble at 2000), so `autocad_create_material(texture_size=...)` writes
exactly that through the .NET API: a new `Gi.Mapper` with AutoCAD's default projection, tiling and
auto-transform and only the transform changed (the API's `Transform` is read-only). The numbers
come from `TextureScale` in the Bridge, so they are tested offline. The bump map takes the same
size, as a photo and its bump image are the same tile. For a non-square image the width goes on X
(index 0) and the height on Y and Z (5 and 10), so on a wall the image's height runs up the wall;
which way a box mapping lays a face along X is **not proven**. Without a size the old behaviour
stays (identity) and the result warns. Plug-in **1.4.1**, as an older plug-in ignores the input;
the server warns when the plug-in's `set` does not list "texture size". Rejected: a default size
(a 600 tile and a 2 m slab need different numbers, and a wrong guess looks right in a preview),
and typing MATERIALMAP (sizes objects, not the material).

## D-45 - Every Heron window and the banner are drawn as Heron for Revit's

**Decided:** 2026-11-08, on Ajmal's word ("what you did for Heron AI in Revit, do the same here - no
difference: the icons, the settings window, the status bar, everything"). **Status:** in force.
`HeronWindowStyle.cs` is a port of Heron for Revit's: Surface card, top strip, Ink header with the
orange heron, ✕, Ink insets, Mist text at 92 / 72 / 55 per cent, flat brand button templates.
Bridge Status, Settings, the Keep question and `HeronSwitchWindow` (the question a padlock asks,
in place of a Windows message box, which stays only as the fallback when the window cannot open) are
built on it with Revit's layouts. The activity banner is Revit's status bar from the designer's
"Heron status bar" design, ported onto AutoCAD's own banner thread and `BannerJobs`. "Free this
AutoCAD" matches Revit's "Free this model" (`HeronHold.Free`, refused while an operation of the
holder runs). Not copied, because AutoCAD has no counterpart: the Companion button and page, and the
Keep question as a Revit TaskDialog (AutoCAD's is a Heron window). The banner stays 110 px below
AutoCAD's top edge so it clears the ribbon.

## D-44 - The padlocks live in a Settings window; the ribbon icons are Heron's brand set

**Decided:** 2026-11-08, on Ajmal's word (in Revit the icons changed and the on/off switches moved
into a window; do the same here). **Status:** in force; follows Heron AI's D-150.
The Heron tab has two buttons: **Heron** (connect, Bridge Status under the arrow) and **Settings**.
The four switches - Changes, Admin, Publish, Ask to Keep, in Revit's order - left the ribbon for
`HeronSettingsWindow`: per switch its padlock picture, its name, one line and the state as an
ON / OFF button. Pressing it runs the same `HeronActions.TogglePadlock` as the old ribbon button, so
the question on the way to the risky side and the settings file are unchanged, and the
`HERONCHANGES`-style commands stay. The cost, accepted as in Revit: the ribbon no longer shows at a
glance whether Changes is on; the banner and Bridge Status still do. The ribbon pictures are copied
from Heron for Revit's `Resources` (brand set of 2026-11-07, plus `Settings.png`); the banner's
on/off stays in the settings file, as no Revit switch matches it.

## D-43 - Heron's windows wear the Heron brand; the release has its own Remove button

**Decided:** 2026-11-08, in the tidy-and-release round Ajmal asked for after the same round on Heron AI.
**Status:** in force.
The status window, the keep question and the activity banner now take every colour from the Heron
palette (Heron AI `docs/brand/README.md`): Mist windows, Ink text, Accent for the focused choice and
the CHANGING chip, Success and Error for DONE and STOPPED, Ink glass at 92 % for the banner as in
Revit. Shades are those colours at an opacity, never new ones; `HeronBrand` in `HeronUi.cs` holds
them and `tests/test_brand_and_installer.py` fails on any other value. Manrope is first in the font
list, with Segoe UI behind it until Manrope ships. A padlock that lets Heron change the drawing
shows ON in Error (the brand's "state to notice"), not green; Ask to Keep, whose ON is the safe side,
shows ON in Success. The release zip gains `Uninstall.bat`, which lists what it removes and asks
before removing anything; refusals say what to do in plain words, and a `claude` error line no
longer stops a first install on Windows PowerShell 5.1.

## D-42 - Lights and materials are made by the plug-in; a 3D view is saved by typing -VIEW

**Decided:** 2026-11-05, for Ajmal's villa model: materials that look like the renders, and real
lights inside light blocks for a night render. **Status:** in force; extends D-40.
`autocad_add_light` and `autocad_create_material` are two more plug-in operations (`add_light`,
`create_material`, at **Changes**; plug-in **1.4.0**). Three routes were weighed. **COM** has no
light object at all, and its material object has only a name and a description: no colour, maps,
gloss or glow. **AutoLISP** could `entmake` a LIGHT, but its group codes are thinly documented and
a material's colour and maps live in nested dictionaries with no LISP call to set them; typing the
LIGHT or MATERIALS commands means answering prompts that change between releases. The **.NET API**
has `Light` and `Material` classes with every setting typed and the same in all three reference
packages (24.0, 25.0, 26.0, checked member by member), so that is the route: one object, every
setting, one transaction, as D-40 does. Lights are made in model space; `autocad_make_block`
copies them into a block like any object (COM `CopyObjects` deep-clones whatever it is given), so
a light block lights every insert. Light names are unique in model space, as AutoCAD's LIGHT
keeps them. A coloured light is a 6500 K lamp behind a filter colour. A material glows in its own
colour (the API has no separate glow colour), so `glow_kelvin` sets the colour to that white.
Only the settings asked for are written, and only their channels switched on, so a replace never
turns on, say, an empty transparency. A texture's mapping is left to inherit (AutoCAD's default,
adjusted with MATERIALMAP): its real-world size is not set, because how the API's mapper
transform reads is not proven. The tool reads LIGHTINGUNITS and warns when it is not 2; it does
not change it. `autocad_save_view(from_screen=true)` types `-VIEW _Save` over COM, as
`autocad_set_3d_view` types VSCURRENT (D-35): COM's `Views.Add` needs the direction, target and
twist written by hand, and a 3D view's numbers are not proven. Rejected: a general "set any
property" request (D-40's reason), and changing LIGHTINGUNITS or DEFAULTLIGHTING behind the
modeller's back.

## D-41 - What was taken from Autodesk's ADN-DevTech samples, and how

**Decided:** 2026-11-04, on Ajmal's "take everything useful from these repositories into Heron".
**Status:** in force. Six ADN-DevTech repositories were read in full; the AutoCAD ones gave five
things, each written fresh (two of the repositories carry no licence, so no code was copied):
`autocad_xref_tree` and `autocad_drawing_report` (reads over COM), `autocad_publish_pdf` (a
plug-in operation, `publish_pdf`, at **Publish**), the command name in "AutoCAD did not get to the
request" (the add-in follows command and LISP events), and `tools/memory_check.py`. The multi-sheet
PDF goes through AutoCAD's publisher, outside a transaction and a document lock (the publisher opens
the sheets itself), and is made from the drawing **as last saved**: a drawing with unsaved changes
is refused rather than published out of date. It never renames or moves the modeller's files, which
the sample does. Rejected: replacing `autocad_export`'s PDF route with the plot engine (the current
route works on 2027 and is pinned by tests; the publisher covers the multi-sheet case), APS Design
Automation (cloud credentials, and not the modeller's own AutoCAD) and an outside COM event
service (needs `regasm` as administrator and works round the padlocks). Detail:
[11](11-adn-repos-study.md).

## D-40 - The plug-in does what COM has no call for, one listed operation at a time

**Decided:** 2026-10-29, on Ajmal's "start the super hatch and 3D tools in the plug-in".
**Status:** in force; extends D-14. Loft, filleting, chamfering, shelling and press-pulling solid
faces and edges, thickening a surface, and Express Tools' SUPERHATCH have no ActiveX call, so the
plug-in does them through AutoCAD's .NET API. The server asks with a new bridge request, `run`,
naming one operation from a fixed list in `Heron.AutoCAD.Bridge/PluginOperations.cs`; anything
else is refused before AutoCAD is touched. `run` is allowed only inside this chat's running job,
on the drawing that job began on, and only when the job's level covers the operation (a Read job
may list a solid's faces, never fillet them): the padlock was already checked at `begin`. The
operation runs on AutoCAD's main thread (through `IdleQueue`) under a document lock in **one
transaction**: it all lands or none of it does, so every refusal can say "Nothing was changed."
No answer in time is "Outcome unknown", never "nothing was sent", because the work may still
have run. Edges and faces are picked by a word that goes by the solid's box ('top', 'vertical',
'front' as in AutoCAD's Front view), never by a face normal, or by the numbers
`autocad_list_solid_faces_and_edges` gives. The super hatch is one block of tiles inserted once and
clipped the way XCLIP clips (a spatial filter), so it moves, erases and undoes as one object.
Everything else stays on COM: a tool moves into the plug-in only when COM cannot do it. Rejected:
typing LOFT / FILLETEDGE / SUPERHATCH as commands (each waits for picks on screen, which typed
input cannot give reliably, and SUPERHATCH is an Express Tools LISP routine that may not be
installed), and a general "run this .NET code" request (it would put the whole API behind the
Changes padlock with nothing to check what it does).

## D-39 - Pattern and linetype files go in Heron's support folder, which goes on the support path

**Decided:** 2026-10-28, with `autocad_create_hatch_pattern` and `autocad_create_linetype`.
**Status:** in force. AutoCAD finds a custom hatch pattern only as its own NAME.pat on the support
search path; Automation has no "hatch from this file". So the files are written to
`%LOCALAPPDATA%\Heron\autocad\support` (or a folder the modeller names), and that folder is added
to `Preferences.Files.SupportPath` once - a change to the AutoCAD profile that stays, reported in
`support_path_added`, and refused with `add_to_support_path=false`. A linetype needs no path: it is
loaded straight from its file with `Linetypes.Load`. Both tools write files, so they sit at
**Publish**, like save and export. Rejected: writing into AutoCAD's own Support folder (Program Files
needs administrator rights and is replaced by an update) and appending to acad.pat / acadiso.lin
(an update overwrites them, and a mistake there breaks every standard pattern).

## D-38 - A wipeout is typed, because Automation cannot make one

**Decided:** 2026-10-28, with `autocad_add_wipeout`. **Status:** in force. There is no AddWipeout:
a wipeout is not among the objects ActiveX can create. So the tool types `_.WIPEOUT` with each
corner as `_non *x,y` - `*` takes the point in world coordinates whatever the UCS or dynamic input
says, `_non` keeps a running snap off it - and a blank line to close. It then checks that the newest
object in the current space is an AcDbWipeout, and if AutoCAD is still asking two seconds later it
cancels with Esc and refuses, so nothing is left half made. It goes over COM `SendCommand`, not the
plug-in's quiet input, because that one is asynchronous and the new object has to be read straight
after. Rejected: entmake from LISP (a wipeout needs its image definition and clip boundary built by
hand, unproven here) and WIPEOUT's Polyline option (it wants the polyline picked at its prompt;
corners typed as points need no pick, so a closed polyline is read for its corners instead).

## D-37 - Ordinates are refused when the datum is not the UCS origin

**Decided:** 2026-10-28, checking the code for faults like the five that failed live. **Status:** in
force. `AddDimOrdinate` takes no origin: AutoCAD measures every ordinate from the current UCS origin,
along the UCS axes. `autocad_dimension_run` promised "the datum to measure from", so with the datum
anywhere else it drew dimensions that read the wrong values (its own measured-versus-expected
check then warned, after the fact). Now an ordinate run whose datum is not the UCS origin - or world
points on a turned UCS - is refused before anything is drawn, naming the
`autocad_set_ucs(mode='origin', origin=[...])` call that fixes it. Rejected: moving the UCS for the
modeller and putting it back, which leaves a named UCS behind and rests on UCS calls not yet proven
live (rows D4, D15); the refusal costs one extra call and cannot draw a wrong number.

## D-36 - A typed scale that is a bare number above 1 is refused, not guessed

**Decided:** 2026-10-28, after `autocad_drawing_setup(scale=10)` in AutoCAD 2027. **Status:** in
force. A bare number has always been a ratio (0.02 = 1:50), so `10` read as **10:1** and set
DIMSCALE 0.1: every dimension ten times too small, with no error. A modeller who types 10 means 1:10
nearly every time, but a detail at 2:1 is real, so the server cannot know. Now every tool that takes
a scale the modeller typed (`autocad_drawing_setup`, `autocad_add_viewport`, `autocad_page_setup`,
`autocad_export`, the scale bar shape) goes through `sheets.parse_typed_scale`, which refuses a bare
number above 1 and asks for '1:10' or '10:1'. Nothing is written first. A bare ratio of 1 or less
(0.02, 1) and every written form ('1:10', '2:1') still read. Inside the server a 2:1 detail travels
as 2.0, so `parse_scale` itself is unchanged. Rejected: reading a bare 10 as 1:10 (a guess that is
wrong for every enlargement, and silent).

## D-35 - The visual style is set with the VSCURRENT command

**Decided:** 2026-10-28, after `autocad_set_3d_view(visual_style="realistic")` came back
`not_set: visual_style (Error setting system variable)` in AutoCAD 2027. **Status:** in force; it
corrects the "written with SetVariable (VSCURRENT)" in D-31, whose level (View) still stands.
VSCURRENT is a **command**, not a system variable: Autodesk documents no VSCURRENT variable, and COM
has no visual style on a model-space viewport. So the tool types `_.VSCURRENT _Realistic` (and so on)
with COM `SendCommand`, from a fixed table of ten answers, and still cannot be talked into anything
else. (Not the plug-in's quiet input: that is taken only inside a Change job, and this is View.) If
AutoCAD is still asking a second later (CMDACTIVE), the option was not taken: the tool cancels with
Esc so the next tool does not find AutoCAD waiting, and says so in `not_set`. The style cannot be read back, so the result no longer carries
`current_visual_style`; `autocad_preview` is the proof. The answers for 'shaded with edges' and
'shades of gray' (`_E`, `_G`) come from the prompt's capital letters, not from a run (row E34).

## D-34 - A read leaves no undo step: the plug-in pauses undo recording

**Decided:** 2026-10-27, after live check A30. **Status:** in force. A U typed after Claude ran
`autocad_list_entities`, `autocad_get_variable` and `autocad_preview` removed nothing; a U straight
after `autocad_batch_labels` removed the batch. Cause, in the source: reads call no command and put
no UNDO mark down, but some write through COM to look. `autocad_preview` adds a page-setup snapshot,
changes about eight layout settings, copies the snapshot back and deletes it; the first list in a
drawing adds the scratch selection set. Each COM write outside an undo group is an undo step of its
own. Now: when a **Read** job begins, the plug-in calls `Database.DisableUndoRecording(true)` on the
active drawing (only if recording was on) and turns it back on at that job's end, before replying,
so the next job never starts unrecorded. Safety nets: the next job's begin, Disconnect, the
modeller starting any command (except PLOT, which a preview may run itself), the drawing closing,
and a 2-minute deadline. The rules are in `Bridge/UndoPause.cs` (tested offline), the switching in
`Addin/UndoSwitch.cs`. **View** jobs (zoom, regen) keep their undo step, as AutoCAD's own ZOOM does.
Rejected: `UNDO _Mark` then `UNDO _Back` around each read (if the mark is missed, Back undoes the
whole session) and `UNDO _Control _None` (wipes the history). Live row A31.

## D-33 - What 3D can and cannot be automated, said out loud

**Decided:** 2026-10-26, on Ajmal's instruction to cover "all kind of 3-D modelling inside
AutoCAD... including material that for rendering". **Status:** in force, except rendering:
`autocad_render` is superseded by [D-87](#d-87---lights-are-listed-and-switched-by-the-plug-in-the-sun-default-lighting-and-exposure-are-variables) (removed 2026-11-21, #158).

Researched before building, because guessing a COM signature wrong can destroy a model. What
was confirmed and built: `AddEllipticalCone`, `AddEllipticalCylinder`,
`AddExtrudedSolidAlongPath` (SWEEP), `SliceSolid`, `CheckInterference`, `Rotate3D`, `Mirror3D`,
and the entity `Material` property.

Three things are **not** built, and that is the decision:

**`SectionSolid` is not built.** AutoCAD's own conceptual docs name it, but no parameter list for
it could be found in any reference. A wrong signature here would mangle a solid, so
`autocad_slice_solid` covers sectioning instead - cut it and look at the face.

**Materials cannot be created.** Every entity has a string `Material` property and setting it
works, but there is no automation route into Autodesk's material library. So `autocad_apply_material`
applies what is already in the drawing and, when a name is not there, **lists what is** and says
the Materials Browser is the way in. It does not pretend to create one.

**A material carries no density**, so it cannot give anything a weight. MASSPROP and
`autocad_solid_properties` both behave as if density were 1. The `model_part` prompt already
multiplies volume by a density the AI must state out loud; assigning "Steel" changes how a solid
looks and nothing else. Both tools say so, because the opposite assumption would put a wrong
weight on a drawing.

**Rendering has no automation call at all.** The only route is the `-render` command, so
`autocad_render` drives that - which is why it is **ADMIN**, the only new tool that is. Its
docstring carries the two real risks: the prompt wording differs between releases so the command
can stall, and script rendering has been reported to drop objects that render correctly by hand.
For a picture to look at, `autocad_preview` is instant and needs no padlock.

**`autocad_check_interference` is CHANGE, not READ**, although it only reports. AutoCAD builds the
overlap as a real solid in order to measure it. With `create_solids` off each one is removed again,
but the drawing was written to, and by D-31 the level belongs to the tool rather than to the call
it happens to make. Row F11 exists to prove the clean-up works.

## D-32 - A tool is not a fragment, but it carries the same five padlocks

**Decided:** 2026-10-26, on Ajmal's question: "these tools, it is same like
fragments in Heron AI - am I right?". **Status:** in force.

Checked, not assumed. `archive/revit_encl/heron_send.py` sends Heron AI's
fragments as five operations - `run_fragment_read`, `run_fragment_show`,
`run_fragment_write`, `run_fragment_publish`, `run_fragment_admin`. This
server's `core/risk.py` carries exactly those five: **READ / VIEW / CHANGE /
PUBLISH / ADMIN**, where VIEW is Heron's `show`. Same five, same order, same
meaning. So the padlock idea is shared, and it should stay shared: if Heron
adds a level, this repo follows.

**The unit of work is not the same.** A Heron fragment is C# **source sent in
at run time**: `heron_send.py` reads a `.cs` file and passes `source`, `needs`,
`values` and `apply`, and Revit compiles and runs it. A tool here is a fixed
function already compiled into the server, with a Pydantic schema, a level and
tests. Nothing new can be sent in - except `autocad_run_lisp`, which is
precisely why that one is ADMIN.

**Which is why findability is the work, not more tools.** A fragment is written
for the job, so it is always exactly right and never has to be found. A fixed
set of 101 has the opposite problem: the right tool exists and nobody can see
it. So every tool carries `Use when:` bullets in a draftsman's own words, with
`Don't use when:` naming the better tool, and `autocad://tools` lists the lot
grouped by padlock, built from the live registry so it cannot go stale.
`tests/test_tool_index.py` makes it a rule rather than a habit.

## D-31 - Looking at a model in 3D is a View tool

**Decided:** 2026-10-26. **Status:** in force.
`autocad_set_3d_view` sets the view direction and the visual style. Nothing in
the drawing moves, nothing is created, nothing is deleted - it changes what is on
screen, which is exactly what the **View** level is for, and the level
`autocad_zoom` and `autocad_regen` already sit at.

The argument against was that the visual style is written with `SetVariable`
(VSCURRENT), and `autocad_set_variable` is ADMIN. But the level is a property of
the *tool*, not of the call it happens to make inside: this tool writes one
named variable from a fixed list of ten style names, and it cannot be talked
into writing anything else. Putting it behind Admin would mean a modeller had to
turn on the most dangerous padlock in the product to look at their own model from
the front, which is backwards.

The viewport's own quirk is handled rather than worked around: a viewport's
changes only take effect once it is made active again, so the tool reassigns
`doc.ActiveViewport` after setting the direction, and says in `not_set` when
that is refused.

## D-30 - A shape is a pure generator, drawn through the batch engine

**Decided:** 2026-10-26. **Status:** in force.
`autocad_make_shape` draws 24 named shapes. Each one could have been a COM
routine of its own. Instead each is a **pure function** in `acad/shapes.py` that
returns a list of operations in exactly the shape `autocad_batch_draw` takes,
and the tool hands that list to the one shared engine (`draw_operations`).

Three things follow, and they are the reason:

* **The geometry is tested without AutoCAD.** A flat pattern is checked by
  measuring whether its arcs are as long as the girths they must roll onto -
  real arithmetic against a real requirement, on a Linux CI runner.
* **It is fast and atomic for free.** One round trip, one undo step, and
  `coords='ucs'` already works, because all of that lives in the engine.
* **Nothing is duplicated.** `autocad_make_shape`, `autocad_add_centre_marks`
  and `autocad_add_revision_cloud` all generate operations and all go through
  the same validation and the same sender.

Two things had to be added to the batch to make it possible, and both are
improvements in their own right: **bulges** on a polyline (DXF group 42), so a
slot, a rounded corner, an elbow and a flat pattern stay *one object* instead of
a pile of loose arcs; and **justification** on text (groups 72, 73 and 11), so a
bubble's number sits on its point.

What the shape library is **not**: an office block library. A block carries the
office's own line weights and its attributes, and is better. The furniture
shapes (bubbles, section marks, north points, scale bars) exist for the drawing
that has no block library to hand, and the tool says so.

The gear says plainly in its own docstring that `show_teeth` draws a
straight-flank representation at the pressure angle and **not** a generated
involute, so nobody cuts a gear from it.

## D-29 - A sequence spends the Changes padlock and nothing more

**Decided:** 2026-10-26. **Status:** in force.
`autocad_sequence` runs several tools in one call. It cannot go back through the gate to do it: the
gate holds an `asyncio` lock for the whole call, so a nested `guarded()` would wait on a lock the
sequence itself is holding. So each step's **undecorated body** is called directly
(`tool.fn.__wrapped__`), which means the sequence, not the gate, is what stands between a step and
the drawing.

Therefore the ceiling is in code and is tested: a sequence refuses any step at the **Publish** or
**Admin** level, and refuses a sequence inside a sequence. It is itself a Change tool, so it can do
exactly what the Changes padlock already allows and can never save, plot, run a command or evaluate
AutoLISP on the way. `tests/test_sequence.py` asserts this against every registered Publish and
Admin tool by name, so a new one is covered the day it is added.

Every step's arguments are validated against that tool's own schema before the first step runs
(the rule `autocad_batch_draw` already follows: a call that cannot be completed changes nothing).
Undo: each step keeps its own undo step, and any group a step leaves open is closed at the end —
the same hazard `autocad_batch_draw` handles in AutoLISP. Whole-call atomicity is the **Ask to
Keep** padlock's job, not this tool's.

## D-28 - Drafting settings are a Change tool, written from a fixed list

**Decided:** 2026-10-26. **Status:** in force.
`autocad_set_variable` is **Admin** because it will set any system variable: an escape hatch, and
rightly gated. But a modeller cannot be asked to turn on the Admin padlock to set the drawing's
units, and setting units is not an escape hatch.

So `autocad_drawing_setup` and `autocad_create_styles` are **Change** tools that write only from a
list kept in `tools/settings.py`: `DRAWING_VARIABLES` for the drawing, and names beginning `DIM`
for a dimension style. The list is in code, not in the request, so nothing a caller writes can widen
it — the same principle as `core/risk.py` itself. A test asserts that everything
`plan_settings` can produce is on the list, and that `plan_dim_style` refuses a name outside the DIM
family.

Both report the old value beside the new one, and `dry_run` shows the whole plan without writing.
`autocad_set_variable` stays Admin for everything else.

## D-27 - Coordinates are world coordinates, and Heron says so

**Decided:** 2026-10-26. **Status:** in force.
Every coordinate AutoCAD's Automation API takes or returns is a **World** coordinate, and `entmake`
writes world coordinates straight into the database. The modeller works in the UCS they set. Two
honest options: convert silently everywhere, or say so and offer the conversion.

Converting silently was rejected: it would have to guess on a tilted UCS, and it would change what
every existing tool means. So:

* world stays the contract for every tool;
* `autocad_status` reports the drawing's UCS and adds a plain `ucs_advice` sentence when it is not
  the world one — and the gate already forces `autocad_status` before any change (D-19), so the warning always
  arrives first;
* `autocad_get_ucs`, `autocad_set_ucs` and `autocad_convert_points` (AutoLISP's `trans`) make it
  workable;
* `autocad_batch_draw` takes `coords="ucs"` and converts every point and angle in Python before a
  single expression is sent, so the conversion is tested without AutoCAD;
* a tilted UCS is **refused** for a flat 2D request rather than guessed, and says to convert the
  points instead.

The transform is built from `UCSORG`, `UCSXDIR` and `UCSYDIR` rather than
`Utility.TranslateCoordinates`: those three are documented, read-only, saved with the drawing, and
the arithmetic from them is pure Python that `tests/test_coords.py` checks without AutoCAD.

The single-entity `autocad_draw_*` tools do not take `coords` yet; adding it means converting each
tool's rotation and its planar vertex lists as well, which has no live check behind it today
([ROADMAP](ROADMAP.md)).

## D-26 - Lee Mac's ideas are rebuilt as Heron tools; his code never enters the repository

**Decided:** 2026-10-26, Ajmal: *"study lee-mac.com word by word ... make it part of this mcp"*.
**Status:** in force.
His terms need written consent to redistribute and forbid commercial use, which this public MIT
repository cannot promise, so no Lee Mac code is copied, translated or bundled. Each idea is written
fresh from the AutoCAD ActiveX reference, tested without AutoCAD, and credited in
[08](08-lee-mac-study.md). First four: count blocks, total length, dynamic block get and set; the rest followed the same
day (every idea on the list, plus add-ons), with the shared geometry in `acad/geometry.py`.

## D-25 - The drafting rules ship inside Heron

**Decided:** 2026-10-26, Ajmal: *"bring that drafting rules also"*, after asking whether anyone who
downloads Heron gets the same neat drawings. **Status:** in force.
The rules lived only in one chat. They are now in the server's instructions (sent to every AI on
connect) and the `draw_detail` prompt, with [07](07-drafting-rules.md) as the readable copy. Lee Mac's
programs are studied for ideas only: his licence allows private/organisation use and forbids
redistribution, and this repository is public, so his code is never copied in; ideas are
re-implemented and credited.

## D-24 - Labels are leaders in Ajmal's TLD style, or multileaders; parts are blocks

**Decided:** 2026-10-26, on Ajmal's instructions after the roof pipe-support detail: labels must be
real leaders ("L shaped, and angled if needed ... multileader also, both options"), following his
`TextLeader_V4.lsp`; and *"elbows and everything should be blocks ... otherwise the manual drawing
person cannot do anything"*. **Status:** in force.
`autocad_add_label` makes MTEXT + LEADER (TLD geometry, `shape` L or angled) or one MLEADER. Leaders and
dimensions made over COM get the drawing's DIMSCALE, which COM does not apply. A "make block from
objects" tool comes next, so details are built from named blocks instead of loose lines.

## D-23 - The generator scripts are removed

**Decided:** 2026-10-26, on Ajmal's instruction: *"Remove all generators, including the folder."*
**Status:** in force. Supersedes D-07 (generator paths) and the generator half of D-06.
The `generators/` folder (AHU, CCTV and pole-enclosure scripts) was project work, not part of Heron,
and normal use never makes such scripts: Heron draws straight into AutoCAD. The drawings they made
stay on Ajmal's PC. The scripts are recoverable from git history, commit `a443df4` (main before removal).

## D-22 - Batch input goes through the plug-in with echo off

**Decided:** 2026-10-26, from the live F2 check. **Status:** in force.
Sent over COM, every batch piece was echoed into the command history. The plug-in now takes the
pieces (`send_quiet`) and types them with `SendStringToExecute(..., echoCommand: false)`. It accepts
them only inside this chat's running CHANGE / PUBLISH / ADMIN job, so it adds no new way in: the
padlock check at `begin` already covered the job. Without the plug-in (or an older one) the server
falls back to COM SendCommand. Each piece also returns nothing printable (`(princ)`). Side effect:
batches run inside AutoCAD and are about 8x faster (0.17 s against 1.4 s for 41 objects).

## D-21 - Batch drawing sends expressions; it never loads a file

**Decided:** 2026-10-26, from live check A21. **Status:** in force.
Loading the batch `.lsp` from `%TEMP%` made AutoCAD's SECURELOAD ask "Unsigned Executable File" on
every batch. The batch is now sent as short expressions (under 600 characters each, `build_chunks`),
like typed input, so no file is loaded. Rejected: adding `%TEMP%` to TRUSTEDPATHS or setting SECURELOAD
to 0 (weakens the modeller's security), writing the file into the trusted plug-in folder (generated
code in a trusted place), and reading the file back with `eval` (sidesteps the security check rather
than respecting it). The old error text that advised setting SECURELOAD to 0 is gone.

## D-20 - A double-click on a ribbon switch counts once

**Decided:** 2026-10-26, from the first live checks. **Status:** in force (built; live row A20 NOT RUN).
The live log showed padlocks flipping on and straight back off within 0.4 s: modellers double-click.
A second click on the same switch within 0.7 s is ignored (`RepeatClickFilter`).

## D-19 - Units are checked before anything is changed in a drawing

**Decided:** 2026-10-26, on Ajmal's instruction during the live checks: *"Whenever you are in one
drawing for the first time, at that time you have to understand the unit."* **Status:** in force.
A CHANGE, PUBLISH or ADMIN call is refused until `autocad_status` (or `autocad_create_drawing`) has run
on that very drawing in this server; switching or opening a drawing does not count, and reading does
not count. The live check showed why: Drawing1 was in inches, Drawing2 in millimetres.
Replaces the looser D-17 re-arming rule.

## D-18 - Discard goes back to an UNDO mark, and only on a clear answer

**Decided:** 2026-10-26, after the final review. **Status:** in force. Supersedes the "UNDO 1" design.
`UNDO 1` undid the plug-in's own zoom, missed layers a batch made, fired on delete previews that wrote
nothing, and fired when the pipe broke. Now: the plug-in says at `begin` whether it will ask; only then
the server puts `UNDO _Mark` down before the work; it asks only when the call really wrote (a write
counter in `core/connection.py`); Discard is `UNDO _Back`, then the created handles must be gone; a
failed question keeps the change and says so; UNDO off (UNDOCTL) means "cannot discard", said plainly.
The Keep box closes itself as Discard after 9 minutes, before the server's 10, and a question the
plug-in gave up on can never pop up later (`OneShotWork`).

## D-17 - Status always answers; resources go through the gate

**Decided:** 2026-10-26. **Status:** in force.
`autocad_status` always answers with `"heron": {connected, message}`, so a chat can always tell the
modeller how to connect. While AutoCAD is not connected it returns only that block, never the
drawing's name, path or contents (changed after the final review); under `--no-bridge` it says
Heron is off. MCP resources call the matching gated tools,
so a resource read is refused and audited exactly like a tool call.
