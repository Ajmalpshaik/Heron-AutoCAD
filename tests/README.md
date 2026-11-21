# tests

| File | Needs AutoCAD | Covers |
|---|---|---|
| `test_offline.py` | No | Tool registration, input checks, LISP generation, VARIANT and unit helpers |
| `test_export.py` | No (fake COM) | The PDF export order that works on AutoCAD 2027 ([D-04](../docs/DECISIONS.md)) |
| `test_heron.py` | No | Risk levels complete, `--read-only`, `autocad_preview` (incl. through the MCP layer) |
| `test_bridge.py` | No (fake plug-in pipe) | Address file, dead-AutoCAD clean-up, token, refusals, hung-pipe timeout |
| `test_answers.py` | No (faked bridge and COM) | The plain first line of every change answer (DONE / NOTHING CHANGED / REFUSED / OUTCOME UNKNOWN), and dry runs |
| `test_before_after.py` | No (fake COM) | Old -> new per object on the modify, attribute, find-replace, dynamic block, layer and variable tools; no undo step when nothing differs |
| `test_gate.py` | No (faked bridge and COM) | Gate order, audit line, wrong-drawing guard, Keep or Discard, no retry after a write began, read-back |
| `test_standards.py` | No | Standards rules, attribute CSV, resources and prompts |
| `test_checklists_qa.py` | No | Check lists: NO DATA, coverage, office and project lists, reports never overwriting, PASS wording (D-64, D-65) |
| `test_plugin_bundle.py` | No | Bundle layout, PackageContents.xml, installer refusing while AutoCAD runs |
| `test_why_and_gaps.py` | No | `autocad_why`, `autocad_gaps`, the audit reason words, the audit folder fallback ([D-67](../docs/DECISIONS.md)) |
| `test_padlock_guard.py` | No | The Claude Code guard hook in `.claude/`: refuses writing `heron-autocad.config` or the Heron policy key ([D-59](../docs/DECISIONS.md)) |
| `test_padlocks_from_plugin.py` | No (faked bridge) | The padlocks read from the connected AutoCAD's ping, not a file; `autocad_why` naming a Windows policy hold ([D-59, D-60](../docs/DECISIONS.md)) |
| `test_structure.py` | No | `tools/check_structure.py` |
| `test_live.py` | **Yes**, marked `live` | Real drawing round trips |
| `conftest.py` | | Switches the bridge off and moves `%LOCALAPPDATA%` to a temp folder for every test |

The C# tests are in [`autocad/Heron.AutoCAD.Bridge.Tests`](../autocad/README.md).

```bash
.venv\Scripts\python.exe -m pytest -m "not live"
```

```bash
dotnet test autocad/Heron.AutoCAD.Bridge.Tests
```

With AutoCAD open: `.venv\Scripts\python.exe -m pytest -m live`. How many tests there are:
`pytest --collect-only -q`. Never edit a test just to make it pass.
