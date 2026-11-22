# tools - scripts you run by hand

| Script | Needs AutoCAD | Does |
|---|---|---|
| `build_plugin.py` | No (needs the .NET SDK) | Builds the plug-in for all three AutoCAD ranges into `dist/HeronAutoCAD.bundle` |
| `install_plugin.py` | **Closed** | Copies the bundle into `%APPDATA%\Autodesk\ApplicationPlugins`; `--uninstall` removes it |
| `make_release.py` | No (needs the .NET SDK and PyInstaller) | Builds `dist/HeronAutoCAD-<version>-win64.zip` and `dist/checksums.txt` (its SHA-256): the bundle, the server as one `autocad-mcp.exe`, and `Install.bat` / `Uninstall.bat` (asks before removing) / `Rollback.bat` (asks before going back) / `CheckForUpdate.bat` (never installs) from `release_files/`, and `capabilities.json` (`export_capabilities.py`). On GitHub, a `v` tag builds and publishes it (`release.yml`). The target PC needs no Python, .NET SDK or admin password |
| `export_capabilities.py` | No | Writes `dist/capabilities.json`: every tool with its padlock, `Use when` lines, inputs, what it needs of the plug-in and its NEEDS-CHECKING proof (PASS / PARTLY / NOT RUN / FAIL / NO ROW), for a registry such as Heron AI's. Same file every time for the same code; every release zip carries it ([14](../docs/14-heron-ai-adapter.md), D-122) |
| `check_secrets.py` | No | No credential in any tracked file (key shapes, private keys, passwords in config lines) or file named like one (.env, *.pem). Runs in CI; exit 2 = could not look, never a pass |
| `check_structure.py` | No | Repository rules (AutoCAD API only in the add-in, every tool has a level, doc links). Runs in CI |
| `smoke_test.py` | Yes, with a drawing open | Live checks against a scratch drawing, then cleans up |
| `live_check.py` | Yes, with Changes on and Ask to Keep off | Measures 198 live rows of `docs/NEEDS-CHECKING.md` (groups D-F, M-Z, AA-AS, RV) in its own scratch drawings and, with `--write`, records the results there; the other 201 rows of those groups get their NOT RUN reason |
| `protocol_check.py` | Yes | Starts the server as Claude does and does the MCP handshake over stdio |
| `memory_check.py` | Yes, Heron connected | Reads acad.exe's Private Bytes over 100 rounds of Heron reads; PASS when the last reading is within 10 % of the first (NEEDS-CHECKING I7) |

```bash
.venv\Scripts\python.exe tools/build_plugin.py
```

```bash
.venv\Scripts\python.exe tools/install_plugin.py
```

```bash
.venv\Scripts\python.exe tools/check_structure.py
```

`make_release.py` must run from a venv with the project and PyInstaller installed, not the
working `.venv` while its server is running ([05 §1](../docs/05-known-limits.md#1-reinstalling-while-the-server-runs)).
Keep the venv on a short path such as `C:\hbuild\v`; a long path breaks `venv`.

```bash
python -m venv C:\hbuild\v
```

```bash
C:\hbuild\v\Scripts\python.exe -m pip install . pyinstaller
```

```bash
C:\hbuild\v\Scripts\python.exe tools/make_release.py
```

`live_check.py` turns the hand-kept register into one command. `--list` shows the rows and
needs nothing running; `--group AA` runs one group, `--group M,O,T` several; `--row E4 --row AA6`
runs named rows; `--write` puts the results, with their evidence, into `docs/NEEDS-CHECKING.md`.

- **The padlocks first.** It reads them from the plug-in before anything else. Changes off: it says
  "Turn Changes on in Settings" and stops; Ask to Keep on: it says "Turn Ask to Keep off" and stops.
  It never switches a padlock itself (D-59, D-118).
- **Admin and Publish.** A row marked `[needs Admin on]` (or Publish on, or off) in `--list` runs
  only when that padlock already is so; otherwise it is said, and the register is left as it was.
  `--list` says what each row needs; run again with the padlocks set that way for those rows.
- **Its own drawings.** It works in new drawings it makes, saved (when a row needs a file) into its
  own folder in `%TEMP%`, and closes them unsaved at the end. Check lists, saved commands and notes a
  row makes are named `lc-...` and deleted by that row.
- **Never PASS by default.** A row the padlocks refuse is NOT RUN with that reason; a NOT RUN reason
  never overwrites a PASS, FAIL or NO MACHINE already in the register.
- **One session.** Run it when no chat is using this AutoCAD.

```bash
.venv\Scripts\python.exe tools/live_check.py --group all --write
```

The live scripts expect the server at `.venv\Scripts\autocad-mcp.exe`. With the plug-in installed,
press **Heron** in AutoCAD first (and turn on Changes for the smoke test), or run them against a
server started with `--no-bridge`.
