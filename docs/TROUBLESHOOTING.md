# Troubleshooting

Every error this server produces is written to say what to do about it. This
page covers the ones with a cause that is not obvious from the message.

---

## "AutoCAD is not connected to Heron"

Press **Heron** on the Heron tab (or type `HERON`). No Heron tab at all: the plug-in is not installed
or did not load; close AutoCAD and run the setup again (or `Install.bat`; from a source checkout,
`tools/install_plugin.py`), then check
`%LOCALAPPDATA%\Heron\autocad\logs\` for the add-in log.

## "Changes is off" / "Publish is off" / "Admin is off"

The padlock named in the message is closed. Press **Settings** on the Heron tab (or type the
command the message names), click its OFF and answer **Turn on**. This is the guard working, not an
error.

**It was on before you restarted AutoCAD.** That is right: every padlock is off each time AutoCAD
starts, and each open AutoCAD has its own ([D-59](DECISIONS.md)). Turn it on again in Settings.

**You set `"write.enabled": true` (or another padlock line) in `heron-autocad.config`.** The file no
longer turns any padlock on; those lines are ignored. Only a click in Settings does.

## "Changes is held off by a Windows policy on this PC"

The PC's administrator set `AllowChanges` (or `AllowAdmin`, `AllowPublish`) to 0 under
`HKLM\SOFTWARE\Policies\Heron\AutoCAD` ([D-60](DECISIONS.md)). Settings shows that padlock as
**HELD** and it cannot be pressed. Only the administrator can change it: ask whoever looks after
the PC. Once they lift it, turn the padlock on in Settings; it does not come back on by itself.

## "Heron's padlock guard refused this step"

Claude Code, working in this repository, tried to write `heron-autocad.config` or the Heron policy
key, and the repository's guard (`.claude/hooks/guard_padlocks.py`) stopped it. Nothing was
written. A chat must never switch a padlock itself; turn it on in Settings. If Claude only meant to
read the file or mention its name, ask it to do that without the writing part.

## "This AutoCAD is in use by another chat"

Another Claude session holds this AutoCAD. Finish there, wait 3 quiet minutes, or press Heron twice
(disconnect, connect) to free it.

## "The active drawing changed from ... to ..."

You switched drawings since Heron last looked. Ask Claude to check the status (or switch to the
drawing you mean); then the change goes through.

## "Outcome unknown"

AutoCAD went busy half-way through a change. Part of it may be drawn: look, press Ctrl+Z once if you
want it gone, then ask again.

## "No running AutoCAD instance was found"

In order of likelihood:

**AutoCAD is not open.** Open it, with a drawing.

**AutoCAD is still loading.** Wait for the drawing area to appear.

**One of the two is running as Administrator and the other is not.** Windows
blocks COM between processes at different elevation levels, in both directions.
Check Task Manager → Details → right-click the columns → add "Elevated". `acad.exe`
and the process running this server must match. Either run both normally
(recommended) or both elevated.

**You have AutoCAD LT.** LT ships without the Automation interface. Nothing can
connect to it — this is a limitation of LT itself.

**AutoCAD has never been run on this machine.** It registers its COM interface
on first launch. Start it once normally.

---

## "AutoCAD stayed busy and never accepted the request"

AutoCAD refuses COM calls while it is not at an idle command prompt. The server
retries for 10 seconds before giving up, so seeing this means something is
genuinely waiting.

Switch to AutoCAD and look at the command line:

- A dialog box open anywhere → close it.
- A command prompting for input (`Specify first point:`) → press **Esc**.
- A grip or editing operation in progress → press **Esc** twice.

The most common cause is a previous `autocad_send_command` whose argument
string was incomplete, leaving the command waiting. That tool reports
`command_active: true` when this happens.

---

## "AutoCAD is in the middle of a command"

Same fix: press Esc in AutoCAD. This is the early-warning version of the
message above — the server checks `CMDACTIVE` before writing, rather than
letting a half-finished command produce confusing results.

---

## "Lost the COM connection to AutoCAD"

The connection worked and then stopped. Usually AutoCAD was closed, crashed, or
showed a drawing-recovery dialog.

Check AutoCAD is still running. The server re-dispatches automatically on the
next call, so once AutoCAD is back there is nothing to restart on this side.

---

## Claude does not show the AutoCAD tools

**Claude Desktop was not fully restarted.** Closing the window leaves the
process running. Quit from the system tray icon, then reopen.

**The path in the config is wrong.** It must point at
`.venv\Scripts\autocad-mcp.exe`, and every backslash must be doubled in JSON:
`"D:\\Ajmal\\AutoCAD APP\\Autocad MCP\\.venv\\Scripts\\autocad-mcp.exe"`.

**The config JSON is malformed.** A trailing comma or missing brace makes
Claude Desktop skip the whole file silently. Paste it into a JSON validator.

**The server itself is broken.** Run `.venv\Scripts\autocad-mcp.exe --list-tools`.
If that errors, fix that first — Claude cannot start a server that will not run.

Running the server directly with no arguments looks like it hangs. That is
correct: a stdio server waits silently for a client on standard input.

---

## The server shows "failed" / "Server disconnected"

That message only means the server exited before the handshake; it never says
why. Run the executable yourself to see the real error:

```bash
"D:\Ajmal\AutoCAD APP\Autocad MCP\.venv\Scripts\autocad-mcp.exe"
```

A working server prints nothing and appears to hang — that is correct, it is
waiting for a client on standard input. Press Ctrl+C. Anything else is the
actual fault, usually a Python traceback naming the module at fault.

**A half-installed package in the virtual environment** is the common cause. An
install interrupted partway leaves a package with some files missing, and the
import fails at startup with `ModuleNotFoundError`. It has happened to
`cryptography`, which the MCP library depends on.

The signature is a package folder whose `.dist-info` has no `RECORD` file. To
find any:

```bash
for d in .venv/Lib/site-packages/*.dist-info; do [ -f "$d/RECORD" ] || echo "CORRUPT: $d"; done
```

Reinstall whatever it names, forcing a clean copy:

```bash
uv pip install --python .venv/Scripts/python.exe --force-reinstall cryptography
```

If uv warns it could not uninstall the old version because `RECORD` is missing,
delete that stale `.dist-info` folder by hand afterwards — two `.dist-info`
folders for one package confuse later installs.

Then confirm the whole path works before going back to Claude:

```bash
.venv\Scripts\python.exe scripts\protocol_check.py
```

Reconnect the server in Claude afterwards. A server that failed at startup
stays failed until it is restarted — it does not retry on its own.

---

## A drawing tool succeeded but nothing appeared

**It is off screen.** Ask Claude to zoom extents (`autocad_zoom`).

**The layer is off, frozen, or the colour matches the background.** Ask Claude
to list the layers and check the state of the one it drew on.

**It is in the other space.** Tools default to model space. If you are looking
at a paper-space layout, either switch to model space or pass `space="paper"`.

**Points specifically.** A point object renders as a single pixel by default.
Set `PDMODE` to 3 or 34 via `autocad_set_variable` to make points visible.

---

## Hatch fails or fills the wrong area

The boundary must be a **closed** shape. An open polyline cannot bound a hatch,
and the tool refuses it by name rather than letting AutoCAD fail obscurely.

Close it with `autocad_modify_entity(handles=[...], closed=true)`, or draw it
with `closed=true` in the first place.

If the hatch appears as a solid smudge, the pattern scale is too small for the
drawing's units. In a millimetre drawing, try `scale=20` or higher.

---

## "That property does not exist on that entity type"

`autocad_modify_entity` reports skipped properties rather than failing the whole
call — asking for a new `radius` across a mixed selection changes the circles
and skips the lines. The `skipped` list in the response says which.

---

## Entity changes are refused

The layer is locked or frozen. Either unlock it with `autocad_set_layer_state`,
or pass `layer_lock_override=true` to `autocad_modify_entity`, which unlocks
the layer for the change and locks it again afterwards.

---

## Ctrl+Z does nothing the first time after Claude reads the drawing

Expected, and not a bug in this server. AutoCAD charges an undo step for
**any** selection operation, and the query tools (`autocad_list_entities`,
`autocad_find_text`, `autocad_measure` by layer, and so on) have to select in
order to filter. That step sits on top of your last real edit.

So after Claude looks at the drawing, the first Ctrl+Z undoes the read — which
looks like nothing happening — and the second undoes your edit.

Measured, so you don't have to take it on faith: `Add()` and `Clear()` on a
selection set are free; `Select()` is what costs the step. Doing the same
filtering through AutoLISP `ssget` costs a step too, so there is no cheaper
route — it is inherent to selecting in AutoCAD, not a consequence of using COM.

What this server does do: reuse one scratch selection set per drawing instead
of creating and deleting one per read, and group each write tool into exactly
one undo step. So a `autocad_batch_draw` of 500 entities is still a single
Ctrl+Z, not 500.

---

## `autocad_batch_draw` produces no output

The batch is sent to AutoCAD as a series of short AutoLISP expressions, as if
typed at the command line ([D-21](DECISIONS.md)). Nothing is written to a file
and nothing is `(load ...)`ed, so AutoCAD's `SECURELOAD` never comes into it.
When a batch draws nothing, look at these instead:

- **AutoCAD is mid-command.** A prompt on the command line swallows the
  expressions. Press Esc in AutoCAD and run the batch again.
- **Heron is not connected, or the Changes padlock is off.** The tool says so
  in its refusal; press Heron on the Heron tab, then turn on Changes in Settings (it is off
  again after every AutoCAD restart).
- **The target layer is locked or frozen.** See the next section.

To confirm LISP evaluation works at all, ask Claude to run `autocad_run_lisp`
with `(getvar "INSUNITS")`. If that returns a number, the LISP route is fine.

### AutoCAD shows "Unsigned Executable File"

Heron never loads a `.lsp` file, so this box does not come from a Heron tool.
It means something loaded a LISP file from an untrusted folder: an office
routine, or an AI that wrote its own `.lsp` and loaded it through
`autocad_run_lisp`. Click **Do Not Load** unless you know the file, and tell the
AI to send its LISP as expressions instead. Do not set `SECURELOAD` to 0 or add
the temp folder to Trusted Locations to make the box go away: that would let
any file there run unasked.

---

## Batch reports `failed` for some operations

`entmake` rejected them. Usual causes, in order:

- **The target layer is locked or frozen.** Unlock it with
  `autocad_set_layer_state`.
- **Degenerate geometry** — a zero radius, or a rectangle whose corners share
  an X or Y value. Most of these are caught in Python first, but not all.
- **A text style or linetype the drawing does not have.**

`created` reflects what actually landed, so a partial batch is reported
honestly rather than counted as a success.

---

## `autocad_run_lisp` returns `timed_out`

The expression never wrote a result. Usually one of:

- A LISP error — a typo, or an undefined function. Check AutoCAD's command line
  (press F2 for the text window) for the actual message.
- The expression is prompting for input. Press Esc in AutoCAD.
- A function needing Visual LISP that `(vl-load-com)` did not cover.

Note that a result of `"nil"` is not a failure. `nil` is LISP's empty value —
the expression ran and evaluated to nothing.

---

## Performance is poor on a large drawing

COM is out-of-process, so every property read is a round trip. On drawings with
tens of thousands of entities:

- Use `summary_only=true` on `autocad_list_entities` before listing anything.
- Filter by `layer` and `entity_type` — the filtering happens inside AutoCAD,
  not in Python.
- Pass `include_geometry=false` when you only need handles.
- Avoid `include_entity_counts=true` on `autocad_list_layers`; it walks every
  layer's contents.

---

## Still stuck

Run the smoke test — it isolates which layer is broken:

```bash
.venv\Scripts\python.exe tools/smoke_test.py
```

It labels each of the 55 checks, so the first failure points straight at the
area with the problem.
