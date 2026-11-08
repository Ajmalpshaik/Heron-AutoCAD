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
| **Heron** (arrow) -> Free this AutoCAD | Lets another chat use this AutoCAD now, whichever chat holds it (not while one of its jobs is running). Changes nothing in a drawing | `HERONFREE` |
| **Settings** | The four switches in one window: per switch its padlock picture, its name, one line, and an ON / OFF button (red ON for a padlock, green ON for Ask to Keep) | `HERONSETTINGS` |

| Switch in Settings | What it does | Command |
|---|---|---|
| **Changes** | Allows drawing, modifying, layers, deleting | `HERONCHANGES` |
| **Admin** | Allows any command, AutoLISP, system variables, purge, audit (needs Changes) | `HERONADMIN` |
| **Publish** | Allows save, Save As, export and plot (needs Changes) | `HERONPUBLISH` |
| **Ask to Keep** | After each change, ask Keep or Discard. Its line says **Keeping the rest of this job** while a "keep the rest" answer holds | `HERONASKTOKEEP` |

- AutoCAD starts **disconnected** every time (unless `bridge.autoConnect` is set). Until you
  connect, a chat can learn only that AutoCAD is running and not connected: `autocad_status` returns
  no drawing name, path or contents, and every other tool is refused.
- **Turning a padlock on asks first; turning it off never asks.** Ask to Keep is the other way round:
  switching the question *off* is what asks.
- Reading and viewing (status, lists, measure, preview, zoom, switch drawing) need no padlock, only
  the connection.
- The padlocks are saved in `%APPDATA%\Heron\autocad\heron-autocad.config` and read fresh on every
  call, so they apply to every open AutoCAD. A file that cannot be read means **every padlock off**.

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
| Ops | `ping`, `info`, `release`, `begin`, `end`, `ask_keep`, `send_quiet` (batch input, echo off, only inside a running change job, [D-22](DECISIONS.md)), `run` (one of the plug-in's own operations, below, [D-40](DECISIONS.md)) |

**Units first ([D-19](DECISIONS.md)).** Nothing is changed in a drawing until Heron has run
`autocad_status` on it, which reports its units. A switch to another drawing needs a new status check
before the next change.

For each tool call the server ([`core/gate.py`](../src/autocad_mcp/core/gate.py)):

1. looks up the AutoCAD process behind COM (from its main window) and reads that AutoCAD's address file;
2. refuses a change if Heron has not checked this drawing's units with `autocad_status` yet, or the active drawing changed since;
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

An older plug-in answers that it does not know `run`; the tool then says to update the plug-in.
If no answer comes within 300 s the result is "Outcome unknown": the operation may still have run.

## 7. Files on disk

| What | Where |
|---|---|
| The plug-in | `%APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle` |
| Padlocks | `%APPDATA%\Heron\autocad\heron-autocad.config` |
| Address files | `%LOCALAPPDATA%\Heron\autocad\bridges\` |
| Add-in log | `%LOCALAPPDATA%\Heron\autocad\logs\addin-YYYYMMDD.log` |
| Audit (server) | `%LOCALAPPDATA%\Heron\autocad\audit\audit-YYYYMM.jsonl` |

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
