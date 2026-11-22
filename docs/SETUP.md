# Setup

Step by step, from nothing to Claude drawing in your AutoCAD.

> **Only want to use Heron, not change it?** Follow **[INSTALL.md](INSTALL.md)**: download
> **`HeronAutoCAD-<version>-setup.exe`** from the
> [releases page](https://github.com/Ajmalpshaik/Heron-AutoCAD/releases), check its SHA-256, close
> AutoCAD and Claude, and double-click it. No Python, no .NET SDK, no administrator password: it installs for your
> Windows user only, sets Claude Code and Claude Desktop up, and is removed from **Windows Settings >
> Apps**. The zip with `Install.bat` on the same page does the same by hand. Neither has passed its
> live checks yet ([NEEDS-CHECKING](NEEDS-CHECKING.md) Group AK and Group P).
> [Installing for modellers](#installing-for-modellers-the-setup-program) below says what each changes.
> The rest of this page is for building Heron from its source.

---

## 1. Check you can run this

| Requirement | Why | How to check |
|---|---|---|
| Windows | COM Automation is Windows-only | — |
| Full AutoCAD, 2021 to 2027 | The plug-in is built for those; LT has no ActiveX/COM Automation interface — see below | Help → About |
| Python 3.10+ | Only to build or run from source | `python --version` |

**About AutoCAD LT.** LT 2024+ for Windows does run AutoLISP internally — the
old "LT can't run LISP" line is out of date. But that is LISP running *inside*
LT. This server is an *external* process attaching to AutoCAD over ActiveX/COM,
and Autodesk does not ship ActiveX with LT: there is no `AutoCAD.Application`
COM server to attach to. So the server cannot drive LT at any version, on
Windows or Mac. That is a limitation of LT, not of this project.

Launch AutoCAD normally once before first use. AutoCAD registers its COM
interface on first run, and until it has, nothing can connect to it.

---

## 2. Install

From the project folder:

```bash
uv venv --python 3.11
```

```bash
uv pip install -e .
```

If you do not have `uv`, plain pip works the same way:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\pip install -e .
```

---

## 3. Check the server itself

This lists the tools without touching AutoCAD, so it isolates install problems
from connection problems:

```bash
.venv\Scripts\autocad-mcp.exe --list-tools
```

You should see 199 tools. If this fails, the problem is the install.

---

## 4. Check it can reach AutoCAD

Open AutoCAD with any drawing, then:

```bash
.venv\Scripts\python.exe tools/smoke_test.py
```

This creates its own scratch drawing and exercises every tool in it — it never
touches the drawing you already had open. Expect it to end with every check passed (`N/N checks passed`), then
close the scratch drawing without saving.

If this fails but step 3 passed, the problem is the AutoCAD connection. See
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## 4b. Install the Heron plug-in

Heron AI for AutoCAD needs its plug-in inside AutoCAD; without it every tool says AutoCAD is not
connected. Build it (needs the .NET SDK), close AutoCAD, install, start AutoCAD:

```bash
.venv\Scripts\python.exe tools/build_plugin.py
```

```bash
.venv\Scripts\python.exe tools/install_plugin.py
```

The **Heron** tab appears on the ribbon. Press **Heron** to connect; turn on **Changes** in **Settings** when you want
Heron to draw. What every button does: [06](06-heron-plugin.md).

## 5. Connect Claude

### Claude Code

```bash
claude mcp add autocad -- "<this folder>\.venv\Scripts\autocad-mcp.exe"
```

Confirm it connected:

```bash
claude mcp list
```

### Claude Desktop

1. Open `%APPDATA%\Claude\claude_desktop_config.json`. Create it if it does not
   exist.
2. Add the `autocad` entry — see
   [`examples/claude_desktop_config.json`](../examples/claude_desktop_config.json).
   Note that every backslash in a Windows path must be **doubled** in JSON.
3. **Quit Claude Desktop completely** — right-click its system tray icon and
   choose Quit. Closing the window is not enough; the old process keeps running
   and will not reload the config.
4. Reopen it. The AutoCAD tools appear under the tools icon in the chat box.

---

## 6. First conversation

Ask Claude:

> Check the AutoCAD connection and tell me what's open.

If it reports your drawing name, units and layer count, everything works.

A good habit: always let Claude run `autocad_status` first in a session.
Coordinates are in the drawing's own units, and that call is how Claude learns
whether `5000` means 5 metres or 5 kilometres.

---

## Running over the network

To let Claude on another machine drive AutoCAD on this one:

```bash
.venv\Scripts\autocad-mcp.exe --transport http --host 0.0.0.0 --port 8000
```

The client connects to `http://<this-machine>:8000/mcp`.

There is no authentication and the tools can modify and delete drawing
content. Only do this on a network you trust, and prefer binding to a specific
interface over `0.0.0.0`.

---

## Updating

The install is editable (`-e`), so edits to files under `src/` take effect on
the next server start. After changing anything, restart Claude Desktop or run
`claude mcp restart autocad` so it picks up the new code.

A release that adds a package says so in the CHANGELOG. Install it by name, with
Claude closed so no server runs ([05 §1](05-known-limits.md#1-reinstalling-while-the-server-runs)).
Reading DXF files with AutoCAD closed needs `ezdxf` (D-92):

```bash
.venv\Scripts\python.exe -m pip install ezdxf
```

Reading a DWG with AutoCAD closed also needs the free ODA File Converter from the
Open Design Alliance, installed by hand. Heron finds it under Program Files\ODA
and never downloads it; for another place, set `HERON_ODA_CONVERTER` to its
`.exe` in the MCP settings.

---

## Installing for modellers: the setup program

`HeronAutoCAD-<version>-setup.exe` is built by the release workflow on GitHub's Windows machine
([D-99](DECISIONS.md)). It puts the same files in the same places as the zip's `Install.bat`:

| What | Where |
|---|---|
| The plug-in, for AutoCAD 2021 to 2027 | `%APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle` |
| The server | `%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe` |
| Claude Code (all projects) and Claude Desktop | one `autocad` entry each, written by `Install.ps1 -Connect` ([INSTALL section 5](INSTALL.md#5-connect-claude) says where it looks); each file it changes is kept first as `.heron-backup`, and an `autocad` entry already there is kept |
| Start menu | **Heron AI for AutoCAD** > *Check for a newer Heron* and *Remove Heron AI for AutoCAD* |

- **It stops, and changes nothing, while AutoCAD is open**, or while Claude is using Heron's
  installed server. It checks again just before copying, in case AutoCAD was started meanwhile.
- **Update:** close AutoCAD, run the newer setup. It replaces the whole plug-in folder. It works
  over a zip install too.
- **Go back:** run the older setup from the releases page.
- **Remove:** Windows Settings > Apps > Heron AI for AutoCAD > Uninstall. It takes the `autocad`
  entry out of Claude first, then removes only what it installed (and the earlier version
  `Install.bat` kept). Saved commands, check lists, logs and the audit in
  `%LOCALAPPDATA%\Heron\autocad` stay. The zip's `Uninstall.bat` sends you here when the setup was used.
- A log of each run is in `%TEMP%` (`Setup Log <date>.txt`).

To build it yourself on Windows, after `tools/make_release.py` (needs Inno Setup 6):

```bash
C:\hbuild\v\Scripts\python.exe tools/make_installer.py
```

---

## Code signing

**Heron is not code-signed, by decision.** Ajmal decided on 2026-11-21 not to buy a certificate
([#164](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/164); [#72](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/72)
closed as not planned). Every release says **Not signed**. What a modeller sees, once:

- **Windows SmartScreen** may say *Windows protected your PC* for the setup or `autocad-mcp.exe`:
  choose **More info**, then **Run anyway**. A company antivirus may ask IT to allow the files.
- **AutoCAD** may ask, the first time it loads Heron, whether to load this unsigned plug-in: choose
  to load it **always**, so it does not ask again. Rows AK10 and AK11 record the exact box.

The rest of this section is kept in case the decision changes.

**What is ready.** With a certificate, the release signs Heron's own files with Windows' `signtool`
(SHA-256, time-stamped so the signature outlives the certificate): the add-in DLLs
(`Heron.AutoCAD.Addin.dll`, `Heron.AutoCAD.Bridge.dll` for each AutoCAD build), `autocad-mcp.exe`,
`Install.ps1`, the setup and its uninstaller. Microsoft's own DLLs beside them are signed already.
`tools/signing.py` does it; without a certificate it prints one line and the build goes on, and half
a configuration stops the build instead of shipping unsigned files.

**What to buy.** A code-signing certificate in Ajmal's own name (OV code signing, individual
validation) from a public certificate authority. Since June 2023 these come on a USB token or as
cloud signing, not as a file. Cloud signing can sign on GitHub, but needs the seller's sign-in step
added to `release.yml` once the seller is chosen. A USB token signs only on the PC it is plugged into.
Microsoft's Azure Artifact Signing is open to individuals only in the US and Canada (its quickstart,
checked 2026-11-21).

**Where it goes (a certificate file, `.pfx`).** GitHub > the repository > **Settings > Secrets and
variables > Actions > New repository secret**, two secrets:

| Secret | Holds |
|---|---|
| `HERON_SIGN_PFX_BASE64` | the `.pfx` file as base64 text: `[Convert]::ToBase64String([IO.File]::ReadAllBytes('heron.pfx'))` in PowerShell |
| `HERON_SIGN_PFX_PASSWORD` | the file's password |

**Trying it first, for free, on your own PC.** A test certificate you make yourself shows what
AutoCAD does with a signed plug-in (rows AK10 and AK11) before anything is bought. It is trusted on
that PC only, so never put it in the repository secrets. Make it in PowerShell:

```bash
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=Heron test signing" -CertStoreLocation Cert:\CurrentUser\My
```

```bash
Export-PfxCertificate -Cert $cert -FilePath C:\hbuild\heron-test.pfx -Password (Read-Host -AsSecureString "Password")
```

Then build with it, in the same PowerShell window:

```bash
$env:HERON_SIGN_PFX = 'C:\hbuild\heron-test.pfx'; $env:HERON_SIGN_PASSWORD = Read-Host 'Password'
```

```bash
C:\hbuild\v\Scripts\python.exe tools/make_release.py
```

To make this PC trust it, import the same `.pfx` into
*Trusted Root Certification Authorities* and *Trusted Publishers* for your user (`certmgr.msc`), and
remove it again after the test.
