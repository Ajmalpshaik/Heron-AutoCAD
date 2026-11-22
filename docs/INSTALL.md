# Install Heron AI for AutoCAD

For a modeller who wants to **use** Heron. No Python, no .NET, no administrator password. If you
want to build Heron from its source instead, read [SETUP.md](SETUP.md).

> **This is an early release (v1.8.1), not a finished product.** Heron has never been run in a real AutoCAD as a whole: only some
> pieces passed their live check, in AutoCAD 2027, and nothing at all in AutoCAD 2021 to 2026. The
> files are **not code-signed**. Use it for testing, on drawings you can afford to undo. What was
> really checked, row by row: [NEEDS-CHECKING](NEEDS-CHECKING.md). Every tool and its proof state:
> [TOOL-CATALOGUE](TOOL-CATALOGUE.md).

---

## 1. What you need

| You need | Notes |
|---|---|
| **Windows 64-bit** | Heron talks to AutoCAD through Windows COM, so there is no Mac version. |
| **Full AutoCAD 2021 to 2027** | **Not AutoCAD LT**: LT has no COM, so Heron cannot reach it. Open AutoCAD once before the first install, so it has registered itself. |
| **Claude Code or the Claude Desktop app, signed in** | Heron adds one entry called `autocad` to each one it finds. It looks for the `claude` command and for `%APPDATA%\Claude`. The Claude desktop app may keep its settings elsewhere and run Claude Code inside itself; then the setup finds neither, and you add the entry by hand ([section 5](#5-connect-claude)). |
| Some disk space | The install size is not measured yet: the setup holds the server as one program plus the plug-in. |

Which plug-in build each AutoCAD uses (the bundle holds all three and AutoCAD picks its own):

| AutoCAD | Build | Ever run for real? |
|---|---|---|
| 2021 to 2024 | .NET Framework 4.8 | **No** (no PC with it: NEEDS-CHECKING group C) |
| 2025 and 2026 | .NET 8 | **No** (group B) |
| 2027 | .NET 10 | **Partly**: the rows marked PASS in group A and a few later ones |

---

## 2. Download

1. Open the **[releases page](https://github.com/Ajmalpshaik/Heron-AutoCAD/releases)** and pick the
   newest release. v1.8.1 is marked **Latest**; a later version may first come out marked
   **Pre-release**, for testing.
2. Under **Assets**, download the setup (easiest) or the zip, and `checksums.txt`:

   | File | What it is |
   |---|---|
   | `HeronAutoCAD-<version>-setup.exe` | The one-file setup. Double-click it. It is also removed from Windows Settings > Apps. |
   | `HeronAutoCAD-<version>-win64.zip` | The same files for installing by hand with `Install.bat`. Use the setup **or** the zip, not both. |
   | `checksums.txt` | The SHA-256 of the two files above, to check that your download is the one that was built. |

   (`Source code (zip / tar.gz)` on the same page is the programmers' copy. You do not need it.)

### Check the download (SHA-256)

A SHA-256 is a long fingerprint of a file. If your file gives the same fingerprint as the one in
`checksums.txt`, it is the same file, not a damaged or changed copy. In PowerShell, in the folder you
downloaded to (replace `<version>`):

```powershell
Get-FileHash .\HeronAutoCAD-<version>-setup.exe -Algorithm SHA256
```

```powershell
Get-FileHash .\HeronAutoCAD-<version>-win64.zip -Algorithm SHA256
```

Open `checksums.txt` in Notepad. Each line is `<64 letters and digits>  <file name>`. The letters
and digits next to your file's name must be the same as the `Hash` PowerShell printed (capital or
small letters make no difference). If they differ, delete the download and fetch it again; if they
still differ, do not install it, and open an [Issue](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues).

> The checksum proves the file is intact. It does **not** prove who made it: the files are unsigned.

---

## 3. Install

**Before you start:** close AutoCAD. Quit the Claude Desktop app too (right-click its icon by the
clock, **Quit**) and close Claude Code. The setup stops by itself, and changes nothing, while AutoCAD
is open or while Claude is using Heron's installed server.

### A. With the setup (recommended)

1. Double-click `HeronAutoCAD-<version>-setup.exe`. (Windows may warn first: see
   [section 4](#4-the-warnings-you-will-see-the-files-are-unsigned).)
2. The first page says **NOT FINISHED** and what the setup changes. Press **Next**, then **Install**.
3. The last page lists what it did, for example `Claude Code: connected (all projects)` and
   `Claude Desktop: connected (restart Claude ...)`. Press **Finish**. Any other line says what
   to do; [section 5](#5-connect-claude) explains each. (1.8.0 said `not found, skipped` on a PC
   with only the Claude app: [#233](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/233),
   fixed in 1.8.1.)
4. Start the Claude Desktop app again if you use it.

It writes only for your Windows user:

```
%APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle    the plug-in AutoCAD loads
%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe                 the server Claude starts
Claude Code (all projects) and Claude Desktop                one "autocad" entry each
Start menu > Heron AI for AutoCAD                            "Check for a newer Heron", "Remove ..."
```

Each Claude settings file it changes is first saved next to itself as `<name>.heron-backup`; an `autocad` entry already there is kept as it is.
No registry entry except Windows' own list of installed apps, no service, no firewall rule, no network port.

### B. With the zip

1. Right-click the zip, **Extract All**, and keep the whole folder (for example on your Desktop).
   Do not run it from inside the zip, and not from a folder under `AppData\Local\Packages` (the
   installer refuses that, since AutoCAD would never see the files).
2. Double-click **`Install.bat`** inside the folder. A black window shows the steps:
   `Installing Heron <version>`, `Plug-in installed`, `Server installed`, `Checked`, the Claude lines,
   then `Done`.
3. Start the Claude Desktop app again if you use it.
4. Keep the folder: `Uninstall.bat`, `Rollback.bat` and `CheckForUpdate.bat` are in it.

The zip holds, besides the plug-in bundle and the server: `READ-ME-FIRST.txt` (the same advice as
this page, in short) and `capabilities.json` (a list of the tools for other programs; nothing reads
it today).

---

## 4. The warnings you will see (the files are unsigned)

Heron is **not code-signed**: the owner decided not to buy a certificate
([#164](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/164)). So a warning is normal. It does
not mean the file is bad; it means Windows and AutoCAD cannot tell who made it. These are the
warnings to expect and what to press. **Nobody has watched these boxes on a real PC yet** (rows
AK9 to AK11 are NOT RUN), so the exact words may differ a little from the lines below.

| Where | What it may say | What to press |
|---|---|---|
| **Windows SmartScreen**, when you open the setup (or `autocad-mcp.exe`) | *Windows protected your PC* | **More info**, then **Run anyway** |
| **Your company antivirus or IT policy** | It may block `autocad-mcp.exe` or the setup | Ask your IT team to allow that file. Nothing in Heron needs the internet to run. |
| **AutoCAD**, the first time it loads the plug-in | A security box asking whether to load an unsigned plug-in | Choose to load it **always**, so it does not ask again. AutoCAD may ask once more after an update: that is not yet known. |

Do **not** change `SECURELOAD` or add folders to AutoCAD's Trusted Locations to make a box go away.

---

## 5. Connect Claude

The installer already did it. It adds an entry named `autocad` that starts
`%LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe`, and its last page (or the end of `Install.bat`)
says, for each Claude, what it did:

| It says | What it means, what you do |
|---|---|
| `Claude Code: connected (all projects)` | Claude Code, or the **Code** tab of the Claude app, has the entry for every folder. New chats see it. |
| `Claude Desktop: connected (restart Claude ...)` | The Claude app's chat has the entry. Quit Claude completely (right-click its icon by the clock, **Quit**; closing the window is not enough) and open it again. The AutoCAD tools appear under the tools icon in the chat box. |
| `already connected` | It was set up before. Nothing changed. |
| `already has an "autocad" entry, left as it is: it starts ...` | Something else is already called `autocad` there (a developer's own server, say). Heron never replaces it. Remove it yourself if you want Heron's, then run the setup again. |
| `Claude is open, so its settings file was not changed` | The Claude app rewrites its own settings file while it runs. Quit Claude as above, then run the setup (or `Install.bat`) again; it is safe to run over itself. The Code tab is usually connected already. |
| `not found, so nothing was added` | Neither Claude was found. Install Claude, then run the setup again, or add the entry by hand (below). |

Where it looks (since 1.8.1, [#233](https://github.com/Ajmalpshaik/Heron-AutoCAD/issues/233)):

- **Claude Code:** the `claude` command, then `%USERPROFILE%\.local\bin\claude.exe`, then the copy
  the Claude app runs in its Code tab (`%LOCALAPPDATA%\Claude-Data\...\claude-code\...\claude.exe`).
  It adds the entry with that program's own `claude mcp add --scope user`, because running Claude
  chats write the same settings file (`%USERPROFILE%\.claude.json`). To check, start a new chat
  and ask Claude to check the AutoCAD connection (or, if you have the `claude` command, run
  `claude mcp list`: you should see `autocad`).
- **Claude Desktop (the app's chat):** `claude_desktop_config.json` in the app's data folder:
  `%LOCALAPPDATA%\Claude-Data\<package>` for the Microsoft Store app, `%APPDATA%\Claude` for the
  older installer.
- Each settings file is saved first next to itself as `<name>.heron-backup`. Removing Heron takes
  out only an `autocad` entry that starts Heron's installed server.

**By hand.** The entry is this (`<you>` is your Windows user folder's name):

```json
"autocad": {"command": "C:\\Users\\<you>\\AppData\\Local\\Heron\\autocad\\autocad-mcp.exe"}
```

- For Claude Code in one folder only: a file named `.mcp.json` in that folder holding
  `{"mcpServers": { <the entry> }}`. Start a new chat there; if Claude asks whether to use the
  project's MCP server, allow it. A folder's `.mcp.json` wins over the all-projects entry.
- For the Claude app's chat: with Claude quit, add the entry inside `"mcpServers"` in its
  `claude_desktop_config.json` (keep a copy of the file first).

Nothing reaches AutoCAD yet: Heron is **off until you press its button** (next section).

---

## 6. First use

Start AutoCAD and open a drawing. A new ribbon tab called **Heron** is there, with one panel,
**AI Bridge**. (This is a text sketch of what the code builds, not a screenshot: no picture was taken,
as AutoCAD has not been run for this page.)

```
 Heron tab
 +---------------------- AI Bridge ----------------------+
 |  [ Heron  v ]            [ Settings ]                 |
 |     |                                                 |
 |     +-- Heron              connect / disconnect       |
 |         Bridge Status      is Heron connected?        |
 |         Heron palette      recent changes, saved cmds |
 |         Free this AutoCAD  let another chat in         |
 |         Stop Heron now     stop every chat at once     |
 +-------------------------------------------------------+
```

1. **Press Heron** (or type `HERON` in AutoCAD). The heron goes from black to **orange**: a chat can
   now reach this AutoCAD. Press it again to disconnect. Until you press it, every tool answers that
   AutoCAD is not connected.
2. **Padlocks are all OFF when AutoCAD starts**, every time, on purpose. Press **Settings**: five switches,
   each with an ON / OFF button:

   | Switch | Off (safe) | On |
   |---|---|---|
   | **Changes** | Heron can only read and look | Heron may draw, modify and delete |
   | **Publish** | Heron may not save or export | Heron may save, export, plot |
   | **Admin** | no commands or AutoLISP | Heron may run commands, AutoLISP, system variables |
   | **Ask to Keep** | changes are kept at once | after each change, a box asks **Keep it / Discard it** |
   | **Ask before keeping erased objects** (starts **ON**) | what Heron erases stays erased, no box | after Heron erases anything, a box asks **Bring them back / Keep them erased** |

   Turning a padlock on asks first; turning one off never asks. The two questions are the other way
   round: switching one *off* asks first. Switch on only what you need, for as long as
   you need it. The same switches are the commands `HERONCHANGES`, `HERONPUBLISH`, `HERONADMIN`,
   `HERONASKTOKEEP` and `HERONASKERASE`; `HERONSTOP` stops every chat at once.

   The erase question comes back ON every time AutoCAD starts. To have it start **off** on your PC,
   open a command prompt **as administrator** and run
   `reg add HKLM\SOFTWARE\Policies\Heron\AutoCAD /v AskBeforeErasing /t REG_DWORD /d 0 /f`
   (`reg delete HKLM\SOFTWARE\Policies\Heron\AutoCAD /v AskBeforeErasing /f` undoes it). Only an
   administrator can set this, so no chat can turn the question off by itself.
3. **Ask Claude**, in the chat, for something harmless first:

   > Check the AutoCAD connection and tell me what's open.

   If it names your drawing, its units and its layer count, the connection works. Then ask it to look
   (`List the layers`), and only when you are ready turn **Changes** on and ask it to draw.
4. While Heron works, a card slides down at the top of AutoCAD: **Heron AI - Reading** or **Heron AI -
   Changing**, then **Done** or **Needs attention**. Every change is **one undo step**: one Ctrl+Z takes it back.

What to ask for, tool by tool: [TOOL-CATALOGUE](TOOL-CATALOGUE.md). What each button does:
[06 - the plug-in](06-heron-plugin.md).

---

## 7. If something goes wrong

Start with [TROUBLESHOOTING](TROUBLESHOOTING.md). The three common ones:

- **"AutoCAD is not connected to Heron"**: press **Heron** on the Heron tab. No Heron tab at all: the
  plug-in did not load; close AutoCAD, run the setup again, then read the newest file in
  `%LOCALAPPDATA%\Heron\autocad\logs\`.
- **"Changes is off"**: that is the padlock doing its job; turn it on in **Settings**.
- **The AutoCAD tools are not in Claude**: quit Claude Desktop completely and open it again.

You can also ask Claude `why can't you do this?`: it names the real reason and what to do, even with
AutoCAD closed. A log of each setup run is in `%TEMP%` (`Setup Log <date>.txt`). Send it with any report.

---

## 8. Update

1. Download the newer setup (or zip) and check it ([section 2](#2-download)).
2. Close AutoCAD and Claude, then run it. It replaces the plug-in folder as a whole, so no file of the
   old version is left. It works over a zip install too, and the zip works over a setup install.

**Is a newer one out?** Start menu > **Heron AI for AutoCAD** > **Check for a newer Heron** (or
`CheckForUpdate.bat` from the zip). It shows the installed version and says whether a newer release
exists. It never installs anything by itself.

**Go back.** With the zip: close AutoCAD, double-click `Rollback.bat`. It shows both versions and asks
before going back. With the setup: run the older setup from the releases page (the setup keeps no
copy of the version it replaces).

---

## 9. Uninstall

- **Installed with the setup:** Windows **Settings > Apps > Heron AI for AutoCAD > Uninstall** (or Start
  menu > Heron AI for AutoCAD > Remove Heron AI for AutoCAD). Close AutoCAD first.
- **Installed with the zip:** close AutoCAD, double-click `Uninstall.bat` from the folder. It shows what
  it will remove and asks you to type `Y`.

Either way it takes the `autocad` entry out of Claude Code and Claude Desktop first, then removes only
what it installed. **Your drawings are never touched.** Your saved commands, check lists, logs and
the audit in `%LOCALAPPDATA%\Heron\autocad` stay: delete that folder by hand if you want them gone.

---

## Where to read next

| You want | Read |
|---|---|
| to know what each tool does, and which padlock it needs | [TOOL-CATALOGUE](TOOL-CATALOGUE.md) |
| what the buttons and padlocks do | [06 - the plug-in](06-heron-plugin.md) |
| what is proven and what is not | [NEEDS-CHECKING](NEEDS-CHECKING.md), [DISCLAIMER](../DISCLAIMER.md) |
| to build from source, or run Heron over a network | [SETUP](SETUP.md) |
