# 06 - The Heron plug-in in AutoCAD

What the modeller sees, what each switch allows, and how the plug-in and the server talk. Code:
[`autocad/`](../autocad/README.md). Decision: [D-12 to D-14](DECISIONS.md).

## 1. The ribbon

Tab **Heron**, panel **AI Bridge**: two buttons, the same layout and icons as Heron for Revit
([D-44](DECISIONS.md)).

| Button | What it does | Command |
|---|---|---|
| **Heron** (top half) | Connect, or disconnect. No pop-up when it works: the icon is the answer (orange heron = connected, black = not) | `HERON` |
| **Heron** (arrow) -> Bridge Status | The state, the Changes card, and Connect / Disconnect | `HERONSTATUS` |
| **Heron** (arrow) -> Heron palette | Opens or closes the docked Heron palette: Activity and Saved commands ([section 10](#10-the-heron-palette-plug-in-160-d-68)) | `HERONPALETTE` |
| **Heron** (arrow) -> Stop Heron now | The emergency stop ([D-51](DECISIONS.md)): every chat is refused at once, a running job stops at its next request to the plug-in, and Esc is pressed for the command running now. Sticky until picked again. What AutoCAD already has queued (one batch) still finishes | `HERONSTOP` |
| **Heron** (arrow) -> Free this AutoCAD | Lets another chat use this AutoCAD now, whichever chat holds it (not while one of its jobs is running). Changes nothing in a drawing | `HERONFREE` |
| **Settings** | The four switches in one window: per switch its padlock picture, its name, one line, and an ON / OFF button (red ON for a padlock, green ON for Ask to Keep; HELD when a Windows policy holds it off) | `HERONSETTINGS` |

| Switch in Settings | What it does | Command |
|---|---|---|
| **Changes** | Allows drawing, modifying, layers, deleting | `HERONCHANGES` |
| **Admin** | Allows any command, AutoLISP, system variables, purge, audit (needs Changes) | `HERONADMIN` |
| **Publish** | Allows save, Save As, export and plot (needs Changes) | `HERONPUBLISH` |
| **Ask to Keep** | After each change, ask Keep or Discard. Its line says **Keeping the rest of this job** while a "keep the rest" answer holds | `HERONASKTOKEEP` |

- AutoCAD starts **disconnected** every time; only your press of **Heron** connects it
  ([D-73](DECISIONS.md)). Until you
  connect, a chat can learn only that AutoCAD is running and not connected: `autocad_status` returns
  no drawing name, path or contents, and every other tool is refused.
- **Turning a padlock on asks first; turning it off never asks.** Ask to Keep is the other way round:
  switching the question *off* is what asks.
- Reading and viewing (status, lists, measure, preview, zoom, switch drawing) need no padlock, only
  the connection.
- **The padlocks live only in this AutoCAD's memory** ([D-59](DECISIONS.md)). Every time AutoCAD
  starts, Changes, Admin, Publish and Ask to Keep are **off**. Only your click
  turns one on: in Settings, or in the same question `HERONCHANGES` / `HERONADMIN` /
  `HERONPUBLISH` open. No file can turn one on, so a chat that can write files cannot unlock itself.
- **Each open AutoCAD has its own padlocks.** Turning Changes on in one does not turn it on in another.
- `%APPDATA%\Heron\autocad\heron-autocad.config` now keeps only `ui.activityBanner`. The
  padlock lines an older plug-in wrote there (`write.enabled`, `publish.enabled`, `admin.enabled`,
  `write.askBeforeKeeping`) and `bridge.autoConnect` are **ignored**; you may delete them.
  A file that cannot be read means no connect at start and the banner on.

### A Windows policy can hold a padlock off

For an office that installs Heron for many modellers ([D-60](DECISIONS.md)). The PC's administrator
sets DWORD values under `HKLM\SOFTWARE\Policies\Heron\AutoCAD`:

| Value | 0 means |
|---|---|
| `AllowChanges` | Changes stays off |
| `AllowAdmin` | Admin stays off |
| `AllowPublish` | Publish stays off |

Any other value, or no value, leaves that padlock to the modeller. A held padlock shows **HELD** in
Settings with the line "A Windows policy on this PC holds this off.", and cannot be pressed. A chat
asking for it is told the policy holds it. A policy pushed while AutoCAD runs applies at the next
call and turns that padlock off; when the policy is lifted, the padlock stays off until you turn it
on. Ask to Keep has no policy. Only an administrator can write `HKLM`, so no chat can lift a hold.

### The guard for Claude Code in this repository

`.claude/settings.json` runs `.claude/hooks/guard_padlocks.py` before every edit and shell command
Claude Code makes here. It refuses one that would write `heron-autocad.config` or the policy key.
It is a second guard: the first is that no file can turn a padlock on.

Every Heron window - Bridge Status, Settings, the switch question and Keep or Discard - is drawn in
Heron for Revit's window style ([D-45](DECISIONS.md)): a dark card with a coloured strip on top, a
header with the orange heron and "Heron  *name*", an ✕, and flat brand buttons in a dark footer. Esc
or the ✕ closes, and dragging the header moves it. Turning a padlock on (or Ask to Keep off) asks in
that style first: the padlock picture, "Turn Changes on?", a tick for what still protects you, a
warning sign for what Ctrl+Z cannot take back, then **Leave off** and an amber **Turn on**.

## 2. Bridge Status

| State | Lamp and headline | Says | Buttons |
|---|---|---|---|
| Connected | orange, **Connected** | A chat can reach this AutoCAD session. Nothing in your drawings changes unless Changes is on. | Disconnect, **Close** (default) |
| Not connected | grey, **Not connected** | This AutoCAD is private. No chat can read your drawings or change them until you connect. | Close, **Connect this session** (default) |
| Did not start | red, **Heron did not start** | the error | Open log folder, **Close** (default) |

Below: the Changes card (amber ON, grey OFF), then THIS SESSION (pipe, process, AutoCAD, add-in and
protocol versions), the address file, and **Copy details** in the footer. Enter presses the lit
button, so it never disconnects.

## 3. The activity banner

Heron for Revit's status bar ([D-45](DECISIONS.md)): a smoked-glass card with rounded corners that
slides down near the top of the AutoCAD window the moment a job is accepted. While a job runs it is
orange, with a sheen travelling across it, an aura turning on its rim and a breathing glow.

| Top line | Colour | Second line |
|---|---|---|
| Heron AI  ·  Reading | orange | the drawing  ·  the job, and the time so far beside three dots |
| Heron AI  ·  Changing | orange | the same; the word says whether the drawing is being touched |
| Heron AI  ·  Done | green | the drawing  ·  what was done, and the time it took |
| Heron AI  ·  Needs attention | red | the drawing  ·  why it stopped |

The outcome stays up for 1.4 s, then the card slides away. The card runs on its own thread (it keeps painting while AutoCAD is busy), lets clicks pass through,
and never takes focus. Afterwards the command line keeps a line: `Heron: Draw Line. Done in 0.4 s`.
Switch it off with `"ui.activityBanner": false` in the config file.

## 3a. A box AutoCAD opens during a job

While a Heron job runs, the plug-in watches for a box AutoCAD opens (a file dialog, "Save
changes?", an error message) and closes it the safe way: **Cancel**, else **No**, else **Esc** -
never OK or Yes ([D-66](DECISIONS.md)). The chat is told: "AutoCAD showed 'Select File'; Heron
closed it with Cancel, nothing was kept from that step." It never touches a window that was open
before the job began, a Heron window, or anything outside a job. A box you open yourself while
the banner shows a job is closed too, so wait for the banner to go
([05 §25](05-known-limits.md#25-the-dialog-watch-closes-every-new-box-in-a-job)).

**One named answer (plug-in 1.7.0, [D-74](DECISIONS.md)).** When the modeller has said the answer
to a box a command will ask ("yes, purge them"), `autocad_send_command` or `autocad_run_lisp` can
name it: `expect_box="Purge - Confirm Purge", press="Yes"`. The plug-in presses that button only
on a box with exactly that title, only once, and only in that call; every other box is still
cancelled. The chat is told "Heron pressed Yes on it, as this call asked". Only an Admin job may
do this, because the button may be Yes or OK.

## 4. Keep or Discard

With Ask to Keep on, the plug-in says so when the job begins, and the server puts an **UNDO mark**
down before the work. After a call that really changed something (a delete *preview* is not asked
about), Heron selects and zooms to what it made (up to 500 objects), then asks
**"Keep what Heron just did?"**:

- **Keep it** - it stays as one undo step.
- **Discard it** - UNDO back to the mark puts the drawing (and the view) back. Heron then checks the
  new objects are really gone before telling the chat `Discarded: nothing was kept.`; if they are
  not, or UNDO is off in the drawing (UNDOCTL), it says so instead.
- **Keep, and keep the rest of this job without asking** - no more questions until 10 quiet minutes.

Closing the box, pressing Esc, or no answer within 9 minutes (the box closes itself) all mean
**discard**. If the plug-in cannot be asked at all (the pipe broke), the change is **kept** and the
chat is told so: nothing is ever undone on a guess.

## 5. One chat at a time

"Chat" here means one server connection: in Claude Code each chat starts its own server, so it is
one chat; Claude Desktop and the HTTP transport serve several chats from one server, which then count
as one. A second one is refused with *"This AutoCAD is in use by another chat. Nothing was sent to
AutoCAD."* The hold frees itself after 3 quiet minutes, or when you disconnect.

## 6. How the server and the plug-in talk (protocol 1)

| Piece | Where |
|---|---|
| Pipe | `\\.\pipe\heron.autocad.<AutoCAD pid>`, current Windows user only |
| Address file | `%LOCALAPPDATA%\Heron\autocad\bridges\<pid>.json`: pid, pipe, versions, token, start time. Written on connect, deleted on disconnect; a file whose AutoCAD is gone is deleted by the server |
| Token | 24 random bytes, new on every connect, compared in constant time |
| Message | one JSON line each way: `{op, token, client, conversation, ...}` |
| Ops | `ping` (also says which padlocks are on and which a Windows policy holds, read-only, [D-59](DECISIONS.md); the command AutoCAD is in; `quietLimit`, the longest line `send_quiet` types, [D-98](DECISIONS.md)), `info`, `release`, `begin`, `end`, `ask_keep`, `send_quiet` (batch input, echo off, only inside a running change job, [D-22](DECISIONS.md); refused once another drawing came to the front during the job, or for a line over `quietLimit`), `run` (one of the plug-in's own operations, below, [D-40](DECISIONS.md)), `dialogs` (the boxes the dialog watch closed in this job, [D-66](DECISIONS.md)), `expect_dialog` (an Admin job names one button for one box it expects, [D-74](DECISIONS.md)), `drawings` (the drawing events after a number, read only, section 6b, [D-98](DECISIONS.md)) |

**Units first ([D-19](DECISIONS.md)).** Nothing is changed in a drawing until Heron has run
`autocad_status` on it, which reports its units. A switch to another drawing needs a new status check
before the next change. So does the same drawing closed and opened again, or a restarted AutoCAD;
a Save As of it does not (section 6b).

For each tool call the server ([`core/gate.py`](../src/autocad_mcp/core/gate.py)):

1. looks up the AutoCAD process behind COM (from its main window) and reads that AutoCAD's address file;
2. refuses a change if Heron has not checked this drawing's units with `autocad_status` yet, or the active drawing changed since, or the plug-in's drawing events say it was closed since or AutoCAD was restarted (section 6b);
3. sends `begin {tool, risk, summary, drawing}`: the plug-in checks token, hold and padlock, shows
   the banner and answers whether it will ask Keep or Discard (`askToKeep`), or refuses naming the
   padlock;
4. runs the tool over COM, as one undo group - or, for what COM has no call for, asks the plug-in
   to do it with `run` (section 6a);
5. if `begin` said it will ask and the call wrote something, sends `ask_keep`; on Discard, UNDO back to the mark put down before step 4;
6. sends `end`, and writes the audit line.

Every refusal ends with **"Nothing was sent to AutoCAD."**: refusals happen before anything in the
drawing is read or changed. The one thing Heron does first is look up which AutoCAD and which
drawing is active (for the guard and the audit line).

## 6a. What the plug-in does itself (plug-in 1.2.0)

Loft, solid edges and faces, thicken and super hatch have no COM call, so the plug-in does them
through AutoCAD's .NET API ([D-40](DECISIONS.md)). The server sends
`run {job, operation, args}`; the plug-in:

1. refuses unless `job` is this chat's running job and its level covers the operation (a Read job
   may list a solid's faces and edges, nothing more), and checks the padlock again: one turned
   off since `begin` holds. The one-chat hold stays with this chat while the operation runs;
2. refuses any operation not on its list (`Heron.AutoCAD.Bridge/PluginOperations.cs`);
3. waits up to 30 s for AutoCAD to be free, then on the main thread checks the active drawing is
   the one the job began on;
4. does the operation under a document lock in one transaction, and answers what it did. A
   refusal or an AutoCAD error drops the whole transaction: **"Nothing was changed."**

| Operation | Tool | AutoCAD .NET call |
|---|---|---|
| `solid_topology` (Read) | `autocad_list_solid_faces_and_edges` | Brep faces and edges |
| `loft` | `autocad_loft` | `Solid3d.CreateLoftedSolid` |
| `fillet_edges` | `autocad_fillet_solid_edges` | `Solid3d.FilletEdges` |
| `chamfer_edges` | `autocad_chamfer_solid_edges` | `Solid3d.ChamferEdges` |
| `shell` | `autocad_shell_solid` | `Solid3d.ShellBody` |
| `press_pull` | `autocad_press_pull_faces` | `Solid3d.ExtrudeFaces` |
| `thicken` | `autocad_thicken_surface` | `Surface.Thicken` |
| `super_hatch` | `autocad_super_hatch` | a block of tiles, one reference, a spatial filter (XCLIP) |
| `layer_state_names` (Read) | `autocad_list_layers`, `autocad_isolate_layers` | `LayerStateManager.GetLayerStateNames`, its mask and description ([D-81](DECISIONS.md)) |
| `layer_state` | `autocad_layer_states`, `autocad_isolate_layers` | `LayerStateManager.SaveLayerState` / `RestoreLayerState` / `DeleteLayerState` |
| `dimension_lines` (Read) | `autocad_space_dimensions` | `RotatedDimension` / `AlignedDimension`: direction and `DimLinePoint` ([D-80](DECISIONS.md)) |
| `move_dimension_lines` | `autocad_space_dimensions` | `DimLinePoint`, then `RecomputeDimensionBlock` |
| `annotation_scales` (Read) | `autocad_list_annotation_scales` | the `ACDB_ANNOTATIONSCALES` collection, `Database.Cannoscale`, `DBObject.HasContext` |
| `set_annotation_scales` | `autocad_annotation_scales` and `annotative=true` on the text, dimension and multileader tools | `DBObject.Annotative`, `AddContext`, `RemoveContext` |
| `sync_attributes` | `autocad_sync_attributes` | `AttributeReference.SetAttributeFromBlock`, `AttributeCollection.AppendAttribute` (ATTSYNC, [D-82](DECISIONS.md)) |
| `excel_table` | `autocad_table_from_excel` | `DataLinkManager.AddDataLink`, `Cell.SetDataLink` ([D-83](DECISIONS.md)) |
| `update_table_links` | `autocad_update_table_links` | `Table.UpdateDataLink(SourceToData, SkipFormat)` |
| `count_entities` (Read) | `autocad_list_entities(summary_only=true)` | `Editor.SelectAll` with the same DXF filter COM uses; each object's class and layer ([D-114](DECISIONS.md)) |
| `entity_extents` (Read) | `autocad_get_extents(layer=...)` | `Editor.SelectAll`, `Entity.GeometricExtents` ([D-114](DECISIONS.md)) |

An older plug-in answers that it does not know `run`; the tool then says to update the plug-in.
If no answer comes within 300 s the result is "Outcome unknown": the operation may still have run.

**Reads the plug-in does faster than COM (plug-in 1.8.0, [D-114](DECISIONS.md)).** `count_entities`
and `entity_extents` are not "COM has no call for it": COM can do them, but one round trip per
object. With an older plug-in, or one that cannot do the read, the tool reads over COM instead and
gives the same answer; a stop or "Outcome unknown" is said, not read again. Which tools come next:
[13 - Moving tools into the plug-in](13-moving-tools-into-the-plug-in.md).

## 6b. Drawing events (plug-in, [D-98](DECISIONS.md), #48)

The plug-in writes down what happens to the drawings the moment AutoCAD says it: a drawing
**opened**, **came to the front**, was **saved** (a Save As says the old name too) or **closed**.
AutoCAD's automatic save (`.sv$`) and backups are left out. Each event has a number; the 200 newest
are kept, in this AutoCAD's memory only.

| Who reads them | What for |
|---|---|
| The server, op `drawings {since}` | `autocad_status` notes where the list stands. A later change asks for what came after: the checked drawing **closed** (and perhaps opened again), the drawing in front **opened** since, or **another AutoCAD session** (a restart), means "call autocad_status first"; a **Save As** of it is followed with no new check |
| `send_quiet` | Once another drawing came to the front during the job (or its drawing closed), the batch input is refused and not typed: "The drawing in front changed while this job ran ... so Heron typed none of this input." The server never types it over COM instead. The plug-in waits up to 10 s for AutoCAD to get to the input, checks the drawing in front once more, and only then answers: typed, refused, or not started in time (never typed later) |
| The palette's Activity tab | Drawn again at every event (section 10) |

A plug-in built before this has no `drawings` op: the guard then compares names only, as before.

## 7. Files on disk

| What | Where |
|---|---|
| The plug-in | `%APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle` |
| Padlocks | Nowhere on disk: this AutoCAD's memory only ([D-59](DECISIONS.md)) |
| Connect at start, banner | `%APPDATA%\Heron\autocad\heron-autocad.config` |
| Padlock policy (administrator) | `HKLM\SOFTWARE\Policies\Heron\AutoCAD` ([D-60](DECISIONS.md)) |
| Address files | `%LOCALAPPDATA%\Heron\autocad\bridges\` |
| Add-in log | `%LOCALAPPDATA%\Heron\autocad\logs\addin-YYYYMMDD.log` |
| Audit (server) | `%LOCALAPPDATA%\Heron\autocad\audit\audit-YYYYMM.jsonl` |
| Saved commands (server) | `%LOCALAPPDATA%\Heron\autocad\commands\*.json` |
| Where the server runs from (for the palette) | `%LOCALAPPDATA%\Heron\autocad\server.json` |
| A palette Run's request, deleted after | `%LOCALAPPDATA%\Heron\autocad\palette\` |

## 8. Versions

| AutoCAD | Build | Bundle folder | Proven live? |
|---|---|---|---|
| 2021-2024 | .NET Framework 4.8 | `Contents/R24` | see [NEEDS-CHECKING](NEEDS-CHECKING.md) |
| 2025-2026 | .NET 8 | `Contents/R25` | see [NEEDS-CHECKING](NEEDS-CHECKING.md) |
| 2027 | .NET 10 | `Contents/R26` | see [NEEDS-CHECKING](NEEDS-CHECKING.md) |

## 9. For developers

`--no-bridge` (or `HERON_AUTOCAD_BRIDGE=off`) runs the server without asking the plug-in: no
padlocks, no banner, no Keep or Discard. The wrong-drawing guard and the audit still run.
`autocad_status` then says Heron is off. Never use it for real work.

## What a job really did, and erasures ([D-50](DECISIONS.md))

While a Change, Admin or Publish job runs, the plug-in counts every object appended, modified and
erased from AutoCAD's own database events, whoever did it: a typed tool, a raw command, AutoLISP or
a purge. The count comes back to the chat as `heron_changes`. Anything the job erased is asked about
in a Heron box, **whether Ask to Keep is on or off**: *Bring them back* (Enter, Esc, closing the box
or no answer in 9 minutes) or *Keep them erased*. When Ask to Keep is on, its Keep or Discard
question already covers the erase, so it is not asked twice. A chat can set `confirm=true` by
itself; it cannot answer this box.

## The plain line a change job answers with ([D-62](DECISIONS.md))

Every Change, Admin or Publish answer starts with one line, before anything else:

| Line | Means |
|---|---|
| `DONE - 2 added, 1 changed, 0 erased.` | The job ran and was kept. The numbers are the plug-in's own count above. |
| `NOTHING CHANGED - ...` | The job ran and changed nothing, was a dry run, or the modeller chose Discard. The drawing is as it was. |
| `REFUSED - ...` | Nothing was done: Heron or the plug-in said no before anything was sent, or the tool turned the job down. |
| `OUTCOME UNKNOWN - ...` | It went wrong after a write began, so part of it may be in the drawing. The line says whether Heron's UNDO mark is there to go back to. |

The count is of drawing objects only. A job that made a layer or set a variable wrote something the
count cannot see, so it says `DONE - no drawing object was added, changed or erased (...)`, never
NOTHING CHANGED. With `--no-bridge` there is no count and no line.

## A dry run of any change ([D-63](DECISIONS.md))

`dry_run=true` on any change tool runs the job for real inside Heron's UNDO mark, reports what it
did, then goes back to the mark and checks the new objects are gone. Nothing is asked and nothing is
kept: the answer starts `NOTHING CHANGED - a dry run: it would have made ...`. Tools that had a dry
run of their own keep it (a preview that writes nothing). A save, an export, a publish, a command or
AutoLISP refuses a dry run, because an UNDO mark cannot take back a file or a command. UNDO must be
on in the drawing.

## 10. The Heron palette (plug-in 1.6.0, [D-68](DECISIONS.md))

`HERONPALETTE`, or Heron (arrow) -> **Heron palette**, opens one palette docked on the right with two
tabs, in Heron's window style. Press it again to close it. The palette's own title bar is
AutoCAD's.

### Activity

Heron's recent changes in this AutoCAD, newest first, from every chat (30 kept; reads and zooms are
left out). Each row: what the job was, the time, the drawing, what became of it (done, discarded,
stopped, undone), and what the plug-in counted: *made 3, changed 1, erased 0*.

It updates live with the drawings too ([D-98](DECISIONS.md), section 6b): the top line says
**In front: plan.dwg**, the drawing events sit between the jobs as one quiet line each (*b.dwg
came to the front*, *Drawing1.dwg saved as plan.dwg*, *b.dwg closed*; the 15 newest), and a job
whose drawing is not the one in front says **not in front**.

| Button | What it does | When it says no |
|---|---|---|
| **Select** | Selects what the job made or changed (up to 500) | a job is running; another drawing is in front; the job only erased, was discarded or was undone |
| **Zoom** | The same, and zooms to it. Leaves no undo step of its own | the same |
| **Undo** | Undoes the job: `UNDO Back` to its mark when Ask to Keep was on, else one `UNDO 1`; then checks that what it made is gone | see below |

Select and Zoom work whichever chat holds this AutoCAD. **Undo is yours**, like Ctrl+Z: no padlock is
needed and it works on any chat's job, but only by the D-54 rule, so your own work is never taken
with it. It refuses, and says why, when:

- it is not Heron's newest change here, or a job is running;
- it ran an AutoCAD command, AutoLISP or a save (Admin or Publish), was discarded, did not finish
  cleanly, changed nothing, or was itself an undo;
- the drawing in front is another one;
- anything changed in a drawing outside Heron's jobs since it ended (your own work, or another
  program), or Heron cannot tell;
- UNDO is off or keeps one step only (UNDOCTL);
- Ask to Keep was off for it and Heron zoomed or showed objects since (one step back would undo the
  zoom).

After a palette Undo, a chat's `autocad_undo_last` is refused: the drawing changed since.

### Saved commands

The commands saved in a chat (`autocad_saved_command`, D-55). One saved in a chat shows here within
about 2 seconds, without a restart. Type in **Search** to narrow the list; pick one; fill its inputs
(a starred one has no default and must be filled; the grey hint is the example); press **Run** (or
Enter in a box).

A value takes its example's type: a number box takes a number ("1200", always with a dot for
decimals), a list box takes the list as in the example (`[0, 0]`), a yes/no box takes yes or no. A
wrong value is named and nothing is sent.

**Run goes through Heron's gate, the same as a chat.** The palette starts a copy of Heron's server
for that one run, which comes to the plug-in as a chat of its own: it checks the units with
`autocad_status`, then runs the command with the Changes padlock, Ask to Keep, the erase question and
Stop Heron now all in force, and frees this AutoCAD when done. So:

- Heron must be connected (pressed), and Heron's server must have run once on this PC (any chat): it
  writes where it runs from to `server.json`, which is how the palette finds it.
- While a chat holds this AutoCAD, Run is refused with "in use by another chat"; press
  **Free this AutoCAD**, or wait 3 quiet minutes.
- The answer is one line under the header: *Done: 'plinth', 2 of 2 step(s).*, or the refusal in the
  gate's own words.
- The run always has the plug-in's checks on and is never another chat: the palette sets
  `HERON_AUTOCAD_BRIDGE=on` and drops `HERON_CONVERSATION_ID` and `CLAUDE_CODE_SESSION_ID` from what
  AutoCAD's own environment would pass on, and the server refuses a palette run with the checks off.
- While a palette Undo waits for AutoCAD to run it, no chat's job may begin: the chat is told "The
  modeller is undoing a Heron change from the Heron palette right now. Try again in a moment." (at
  most one minute), so the UNDO can never land inside another job (#138).
- An Undo that AutoCAD has not started within 30 s (a command or a box in the way) is given up, and
  the line says so; a job whose end never reached the plug-in stops blocking Select, Zoom and Undo
  after 20 minutes.
