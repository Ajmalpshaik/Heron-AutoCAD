# Decision log

> **Append-only.** A decision that is later reversed gets a **new** entry that supersedes the old one;
> the old one stays, so the reasoning is never lost. Number new entries one above the highest here.

---

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
AutoCAD... including material that for rendering". **Status:** in force.

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
