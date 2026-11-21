# tools - scripts you run by hand

| Script | Needs AutoCAD | Does |
|---|---|---|
| `build_plugin.py` | No (needs the .NET SDK) | Builds the plug-in for all three AutoCAD ranges into `dist/HeronAutoCAD.bundle` |
| `install_plugin.py` | **Closed** | Copies the bundle into `%APPDATA%\Autodesk\ApplicationPlugins`; `--uninstall` removes it |
| `make_release.py` | No (needs the .NET SDK and PyInstaller) | Builds `dist/HeronAutoCAD-<version>-win64.zip` and `dist/checksums.txt` (its SHA-256): the bundle, the server as one `autocad-mcp.exe`, and `Install.bat` / `Uninstall.bat` (asks before removing) / `Rollback.bat` (asks before going back) / `CheckForUpdate.bat` (never installs) from `release_files/`. On GitHub, a `v` tag builds and publishes it with the setup (`release.yml`). The target PC needs no Python, .NET SDK or admin password |
| `make_installer.py` | No (Windows, after `make_release.py`; needs Inno Setup 6) | Builds `dist/HeronAutoCAD-<version>-setup.exe`, the one-file setup a modeller double-clicks, from `installer/HeronAutoCAD.iss` and `make_release.py`'s release folder; adds it to `dist/checksums.txt`. Per user, no admin; refuses while AutoCAD runs; sets Claude up with `Install.ps1 -Connect`; removed from Windows Settings > Apps ([D-99](../docs/DECISIONS.md)). `release.yml` builds it with a pinned Inno Setup 6.7.3 |
| `installer/Check-Setup.ps1` | No | Installs and removes Heron on GitHub's Windows machine to check the setup (`release.yml` runs it). **Changes the Windows profile it runs in**: it refuses to run anywhere else |
| `signing.py` | No | Signs Heron's DLLs, `autocad-mcp.exe`, `Install.ps1` and the setup when `HERON_SIGN_PFX` and `HERON_SIGN_PASSWORD` name a certificate; otherwise one "Not signed" line. Releases are unsigned by Ajmal's decision ([SETUP, Code signing](../docs/SETUP.md#code-signing), #164); the step stays for if that changes |
| `check_secrets.py` | No | No credential in any tracked file (key shapes, private keys, passwords in config lines) or file named like one (.env, *.pem). Runs in CI; exit 2 = could not look, never a pass |
| `check_structure.py` | No | Repository rules (AutoCAD API only in the add-in, every tool has a level, doc links). Runs in CI |
| `smoke_test.py` | Yes, with a drawing open | Live checks against a scratch drawing, then cleans up |
| `live_check.py` | Yes, with Changes on | Measures 65 of the 90 live rows in `docs/NEEDS-CHECKING.md` in its own scratch drawing and, with `--write`, records the results there |
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

Then, for the one-file setup (Inno Setup 6 installed, or `HERON_ISCC` naming its `ISCC.exe`):

```bash
C:\hbuild\v\Scripts\python.exe tools/make_installer.py
```

`live_check.py` turns the hand-kept register into one command. `--list` shows the rows and
needs nothing running; `--group D`, `--group E` or `--group F` runs one group; `--row E4 --row D13` runs
named rows; `--write` puts the results, with their evidence, into `docs/NEEDS-CHECKING.md`.
A row the padlocks refuse is recorded NOT RUN with that reason, never PASS.

```bash
.venv\Scripts\python.exe tools/live_check.py --group all --write
```

The live scripts expect the server at `.venv\Scripts\autocad-mcp.exe`. With the plug-in installed,
press **Heron** in AutoCAD first (and turn on Changes for the smoke test), or run them against a
server started with `--no-bridge`.
