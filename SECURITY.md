# Security

## What Heron can do to your files

While AutoCAD is connected and the padlocks allow it, the tools can create, change and delete
objects in any open drawing, save drawings over existing files, export files, run any AutoCAD command
and evaluate any AutoLISP. Treat a connected chat with Changes, Publish and Admin on as someone
sitting at your AutoCAD.

## What keeps it safe

| Guard | Where |
|---|---|
| AutoCAD starts **disconnected**; until Heron is pressed no chat can find it | `autocad/Heron.AutoCAD.Addin/HeronApplication.cs` |
| The pipe is open to **the current Windows user only**; a new random session token on every connect, compared in constant time | `autocad/Heron.AutoCAD.Bridge/BridgeServer.cs`, `BridgeIdentity.cs` |
| **Padlocks off at every AutoCAD start**, kept in that AutoCAD's memory only, so no file can turn one on; only the modeller's click does (D-59) | `HeronPadlocks.cs`, `Permissions.cs` |
| A Windows policy can hold a padlock off; no chat can lift it (D-60) | `HeronPolicy.cs` |
| Every tool's level is declared in code, never taken from the request | `src/autocad_mcp/core/risk.py` |
| One chat at a time per AutoCAD | `HeronHold.cs` |
| A change to a drawing other than the one Heron last looked at is refused | `src/autocad_mcp/core/gate.py` |
| A write that AutoCAD interrupted is never re-run ("outcome unknown") | `core/connection.py` |
| One undo group per call; optional Keep or Discard | `core/registry.py`, `HeronKeepQuestion.cs` |
| Deletes need `confirm=true` | `tools/modify.py`, `tools/layers.py` |
| Dialog-opening commands refused | `tools/advanced.py` |
| Every call audited, never pruned | `core/audit.py` |

## What does not keep it safe

- **COM is still open to other programs on your PC.** The padlocks bind Heron, not every program
  that can reach AutoCAD's Automation interface.
- `--no-bridge` turns the plug-in checks off. It is for developers only.
- **The HTTP transport has no authentication.** `--transport http --host 0.0.0.0` lets anyone on the
  network reach the server. Prefer stdio, or `--host 127.0.0.1`.
- `autocad_send_command` and `autocad_run_lisp` (Admin) can do anything AutoCAD can do.

## Secrets

This repository holds no keys or passwords and needs none. The session token lives only in the
address file under your own `%LOCALAPPDATA%` and changes on every connect.

## Reporting a problem

Do **not** open a public issue for a security problem. Use GitHub's private vulnerability reporting
(the repository's **Security** tab -> **Report a vulnerability**), or contact the owner directly.
