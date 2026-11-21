# 02 - Architecture

## How a call reaches AutoCAD

```
Claude  --stdio/http-->  MCP server (Python)
                              |
                              |  every call marshalled onto one
                              |  CoInitialize'd worker thread
                              v
                         pywin32 COM
                              |
              +---------------+---------------+
              v                               v
      typed COM operations            AutoLISP scripts
      (one round trip each)           (one round trip total)
              +---------------+---------------+
                              v
                    AutoCAD  -->  your open drawing
```

## The Heron gate

Every tool call passes through `core/gate.py` before any COM work: look at which AutoCAD and which
drawing; refuse a change to a different drawing than last time; ask the plug-in `begin` (connection,
one chat at a time, padlock for the tool's level from `core/risk.py`); run; after a change, `ask_keep`;
`end`; write the audit line. The plug-in side and the protocol: [06](06-heron-plugin.md).

## Layers of the code

```
src/autocad_mcp/
  server.py        entry point and command line
  tools/           the MCP tools, grouped by subject      (knows MCP)
  acad/            AutoCAD domain: entities, selections,   (knows AutoCAD, not MCP)
                   layers, AutoLISP, units
  core/            COM link, VARIANTs, errors, undo group   (knows COM)
```

Dependencies only point **down**: `tools` -> `acad` -> `core`. Nothing in `acad` or `core` imports a
tool, so the AutoCAD logic can be tested and reused without MCP.

| File | Job |
|---|---|
| `core/connection.py` | The worker thread, the retry on "busy", app and document access |
| `core/message_filter.py` | The worker thread's COM message filter: a call AutoCAD turned away is asked again, up to 3 s in all per job (D-57) |
| `core/variants.py` | SAFEARRAY / VARIANT marshalling of points and arrays |
| `core/errors.py` | Turning COM errors into messages that say what to do |
| `core/registry.py` | The shared FastMCP instance, undo grouping, the error wrapper that calls the gate |
| `core/gate.py` | The Heron gate: order of checks, Keep or Discard, audit |
| `core/bridge.py` | Finds this AutoCAD's plug-in pipe and talks to it |
| `core/risk.py` | The level of every tool |
| `core/audit.py` | One JSON line per call |
| `acad/entities.py` | Entity serialisation, handle lookup |
| `acad/selection.py` | DXF filters and selection sets |
| `acad/tables.py` | Layers, linetypes, applying common properties |
| `acad/lisp.py` | AutoLISP generation and getting the result back |
| `acad/units.py` | INSUNITS, degrees and radians |

## Why Python and AutoLISP

AutoLISP is AutoCAD's own language and is faster for bulk work, because it runs inside AutoCAD
instead of across a process boundary. But it cannot be the MCP server: MCP is spoken over stdio or
HTTP to an outside process, and AutoLISP cannot open a socket or answer a client. So the protocol
lives in Python, and each language does the job it wins:

| Job | Uses | Why |
|---|---|---|
| MCP protocol | Python | AutoLISP cannot host it |
| Typed single operations | COM | Real objects and values back, per-field checks |
| Bulk creation | AutoLISP `entmake` | One round trip instead of hundreds, about 9x faster |
| What COM cannot reach | AutoLISP | Xdata, dictionaries, xrecords, custom properties |

AutoCAD's COM interface has no "evaluate and return" call; `SendCommand` is fire-and-forget. Small
results come back through the `USERS1` system variable (`autocad_run_lisp`); large ones are written
to a temp file by the LISP and read by Python (`autocad_batch_draw`). The batch itself is sent as short
expressions, never loaded from a file, so AutoCAD's SECURELOAD never asks ([D-21](DECISIONS.md)).

Measured on AutoCAD 2020, 200 lines:

| Method | Time | Rate |
|---|---:|---:|
| One at a time via `autocad_draw_*` | 20.3 s | 10/s |
| `autocad_batch_draw` | 2.2 s | 93/s |
| `autocad_batch_draw`, `return_handles=false` | 1.2 s | 173/s |

## Two COM facts that shape everything

**COM is apartment-threaded.** Every call must happen on one thread that has called `CoInitialize`.
FastMCP tools run on asyncio's loop, so all COM work is marshalled onto one dedicated worker thread.

**AutoCAD rejects calls while busy.** A modal dialog, a command waiting for input or a regen gives
`RPC_E_CALL_REJECTED`. It is retried for 10 seconds, then reported with *"press Esc in AutoCAD"*,
which is what actually clears it.

## PDF export

`autocad_export` to PDF sets the layout to `DWG To PDF.pc3`, plots extents fitted and centred on the
chosen `paper_size`, plots with the path only, then restores the page setup. Passing the pc3 as the
second argument of `PlotToFile` fails on AutoCAD 2027 ([D-04](DECISIONS.md)).
