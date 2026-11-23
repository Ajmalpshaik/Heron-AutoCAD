# Installs Heron AI for AutoCAD for the current Windows user. No administrator rights needed.
#   1. the plug-in  -> %APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle
#   2. the server   -> %LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe
#   3. tells Claude Code and Claude Desktop where the server is (existing settings are kept)
# -Uninstall removes all three, after asking. Uninstall.bat runs it that way.
# -Rollback puts back the version this one replaced, after asking. Rollback.bat runs it that way.
# -CheckUpdate says whether a newer release exists. It never installs anything by itself.
# -Connect and -Disconnect only add or remove the "autocad" entry in Claude Code and Claude
#  Desktop, without asking. The setup program (HeronAutoCAD-<version>-setup.exe) copies the
#  files itself and runs these two, so both ways of installing set Claude up the same (D-99).
# -DryRun, with -Connect or -Disconnect, only says what they would change. It changes nothing.
param([switch]$Uninstall, [switch]$Rollback, [switch]$CheckUpdate, [switch]$Connect, [switch]$Disconnect, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$plugins = Join-Path $env:APPDATA 'Autodesk\ApplicationPlugins'
$target = Join-Path $plugins 'HeronAutoCAD.bundle'
$serverDir = Join-Path $env:LOCALAPPDATA 'Heron\autocad'
$server = Join-Path $serverDir 'autocad-mcp.exe'
# Claude Code keeps its "all projects" servers in .claude.json (CLAUDE_CONFIG_DIR moves it).
$claudeJson = Join-Path $(if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { $env:USERPROFILE }) '.claude.json'
# The entry as it is typed into a settings file by hand, and the indent of a report's second line.
$handEntry = '"autocad": {"command": "' + ($server -replace '\\', '\\') + '"}'
$pad = ' ' * 20
# The version an update replaced, kept so Rollback.bat can put it back.
$previous = Join-Path $serverDir 'previous'
$releases = 'https://api.github.com/repos/Ajmalpshaik/Heron-AutoCAD/releases?per_page=10'

# Anything unexpected: say it in plain words, not a PowerShell error.
trap {
    Write-Host ''
    Write-Host "Heron could not finish. Windows said: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Close AutoCAD and Claude, then try again. If it happens again, send this window''s text to whoever gave you Heron.' -ForegroundColor Red
    exit 1
}

# The version a bundle says it is (PackageContents.xml), or '' when it is not there.
function Get-BundleVersion([string]$folder) {
    $file = Join-Path $folder 'PackageContents.xml'
    if (-not (Test-Path $file)) { return '' }
    $found = Select-String -Path $file -Pattern 'AppVersion="([^"]+)"' | Select-Object -First 1
    if ($found) { return $found.Matches[0].Groups[1].Value }
    return 'unknown'
}

# Run from inside the Claude app's own private folder (the Microsoft Store app keeps one), the
# files would land where AutoCAD never looks. Say so instead.
if ($here -match '\\AppData\\Local\\Packages\\') {
    Write-Host 'This folder is inside an app''s private storage, so AutoCAD would never see what it installs.' -ForegroundColor Red
    Write-Host 'Copy the whole folder to your Desktop or Downloads, then double-click Install.bat there. Nothing was changed.' -ForegroundColor Red
    exit 1
}

if ($CheckUpdate) {
    $installed = Get-BundleVersion $target
    Write-Host ('Installed: ' + $(if ($installed) { $installed } else { 'not installed' }))
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        # The 'latest release' address skips pre-releases, and a new Heron version may first come out as one, so the list is read.
        $latest = @(Invoke-RestMethod -Uri $releases -TimeoutSec 15 | Where-Object { -not $_.draft }) | Select-Object -First 1
    } catch {
        $code = 0
        try { $code = [int]$_.Exception.Response.StatusCode } catch { }
        if ($code -eq 404) {
            Write-Host 'No Heron release has been published on GitHub yet, so there is nothing newer. Nothing was changed.' -ForegroundColor Green
        } else {
            Write-Host 'Could not reach GitHub to look for a newer version. Try again later. Nothing was changed.' -ForegroundColor Yellow
        }
        exit 0
    }
    if (-not $latest) {
        Write-Host 'No Heron release has been published on GitHub yet, so there is nothing newer. Nothing was changed.' -ForegroundColor Green
        exit 0
    }
    $newest = ([string]$latest.tag_name).TrimStart('v')
    if ($installed -and [version]($newest -replace '[^0-9.]', '') -le [version]($installed -replace '[^0-9.]', '')) {
        Write-Host "You have the newest version ($installed)." -ForegroundColor Green
    } else {
        Write-Host "A newer version is out: $newest. Download it from:" -ForegroundColor Yellow
        Write-Host "  $($latest.html_url)"
        Write-Host 'Nothing was installed. Close AutoCAD, then run the new HeronAutoCAD-<version>-setup.exe, or unzip the new zip and run its Install.bat.'
    }
    exit 0
}

# --- Claude (#233, D-126) ------------------------------------------------------------------
# Where an ordinary program (this script, the setup) finds Claude on the real disk:
#  - Claude Code: the "claude" command; %USERPROFILE%\.local\bin\claude.exe, where its own
#    installer puts it; or the copy the Claude desktop app runs in its Code tab, in the app's
#    data folder. Its "all projects" servers are in $claudeJson, which running Claude sessions
#    write all the time, so Heron changes them only through "claude mcp add/remove".
#  - Claude Desktop: claude_desktop_config.json in the app's data folder. The Microsoft Store app
#    keeps it in %LOCALAPPDATA%\Claude-Data\<package>; the older installer in %APPDATA%\Claude;
#    an older Store app in its private copy of %APPDATA%,
#    %LOCALAPPDATA%\Packages\AnthropicPBC.Claude_*\LocalCache\Roaming\Claude.
# An "autocad" entry already there is never replaced, only an entry that starts this server is
# ever removed, every file is saved as .heron-backup before it changes, and Claude Desktop's
# file is left alone while Claude is open (it may save its own copy over the change).

# Windows PowerShell's Get-Content reads a file with no byte-order mark as ANSI, so a settings
# file is read with ReadAllText (UTF-8). $null when it is missing or empty; an error when it is
# not JSON.
function Read-Settings([string]$file) {
    if (-not (Test-Path -LiteralPath $file)) { return $null }
    $raw = [IO.File]::ReadAllText($file)
    if (-not ($raw -and $raw.Trim())) { return $null }
    return ($raw | ConvertFrom-Json)
}

# Windows PowerShell's "utf8" adds a byte-order mark, which Claude Desktop cannot read. Depth 100,
# the most it takes, so the app's own deeper settings are written back whole.
function Save-Settings([string]$file, $cfg) {
    [IO.File]::WriteAllText($file, ($cfg | ConvertTo-Json -Depth 100), (New-Object Text.UTF8Encoding $false))
}

# The "autocad" entry of a Claude Desktop settings object, or $null.
function Get-AutocadEntry($cfg) {
    if ($cfg -and $cfg.PSObject.Properties['mcpServers'] -and $cfg.mcpServers -and $cfg.mcpServers.PSObject.Properties['autocad']) {
        return $cfg.mcpServers.autocad
    }
    return $null
}

# Claude Code's "autocad" entry for all projects, as { command, url }, or $null. Read with .NET's
# own JSON reader: ConvertFrom-Json refuses a file whose keys differ only in case, and
# .claude.json lists project folders, which on Windows can. Nothing here writes the file.
function Get-ClaudeCodeEntry {
    if (-not (Test-Path -LiteralPath $claudeJson)) { return $null }
    $raw = [IO.File]::ReadAllText($claudeJson)
    if (-not ($raw -and $raw.Trim())) { return $null }
    Add-Type -AssemblyName System.Web.Extensions
    $reader = New-Object Web.Script.Serialization.JavaScriptSerializer
    $reader.MaxJsonLength = [int]::MaxValue
    $all = $reader.DeserializeObject($raw)
    if (-not ($all -is [Collections.IDictionary]) -or -not ($all['mcpServers'] -is [Collections.IDictionary])) { return $null }
    $entry = $all['mcpServers']['autocad']
    if ($null -eq $entry) { return $null }
    if (-not ($entry -is [Collections.IDictionary])) { return [pscustomobject]@{ command = $null; url = $null } }
    return [pscustomobject]@{ command = $entry['command']; url = $entry['url'] }
}

# What an entry starts, in a few words.
function Get-EntryText($entry) {
    if ($entry.PSObject.Properties['command'] -and $entry.command) { return [string]$entry.command }
    if ($entry.PSObject.Properties['url'] -and $entry.url) { return [string]$entry.url }
    return 'something other than a program'
}

function Test-StartsHeron($entry) {
    return [bool]($entry -and ((Get-EntryText $entry) -eq $server))
}

# A folder that holds a note ".user-data-left.<package>" is where Claude's data was before the
# app moved it: nothing reads it any more.
function Test-DataLeft([string]$folder) {
    return [bool](Get-ChildItem -LiteralPath $folder -Force -Filter '.user-data-left.*' -ErrorAction SilentlyContinue)
}

# The Claude desktop app's data folders on this PC (above).
function Get-ClaudeAppFolders {
    $roaming = Join-Path $env:APPDATA 'Claude'
    if ((Test-Path -LiteralPath $roaming) -and -not (Test-DataLeft $roaming)) { $roaming }
    Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Claude-Data') -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
    Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'Packages') -Directory -Filter 'AnthropicPBC.Claude_*' -ErrorAction SilentlyContinue | ForEach-Object {
        $copy = Join-Path $_.FullName 'LocalCache\Roaming\Claude'
        if ((Test-Path -LiteralPath $copy) -and -not (Test-DataLeft $copy)) { $copy }
    }
}

# Claude Desktop's settings files: the one in each app folder that has one, and the older
# installer's %APPDATA%\Claude, where the file may not be made yet.
function Get-DesktopConfigs {
    foreach ($folder in @(Get-ClaudeAppFolders)) {
        $file = Join-Path $folder 'claude_desktop_config.json'
        if ((Test-Path -LiteralPath $file) -or $folder -eq (Join-Path $env:APPDATA 'Claude')) { $file }
    }
}

# Claude Code: the "claude" command (never a Windows app alias, which would start an app), then
# the copy its own installer makes, then the newest copy a Claude app runs in its Code tab.
function Find-ClaudeCode {
    $command = Get-Command claude -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notmatch '\\Microsoft\\WindowsApps\\' } | Select-Object -First 1
    if ($command) { return $command.Source }
    $own = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
    if (Test-Path -LiteralPath $own) { return $own }
    $inApp = @(Get-ClaudeAppFolders | ForEach-Object {
            Get-ChildItem -LiteralPath (Join-Path $_ 'claude-code') -Recurse -Filter 'claude.exe' -ErrorAction SilentlyContinue
        }) | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($inApp) { return $inApp.FullName }
    return $null
}

# Claude Desktop holds the "lockfile" in its data folder while it runs.
function Test-ClaudeOpen([string]$folder) {
    $lock = Join-Path $folder 'lockfile'
    if (-not (Test-Path -LiteralPath $lock)) { return $false }
    try { [IO.File]::Open($lock, 'Open', 'Read', 'None').Dispose(); return $false } catch { return $true }
}

# Runs Claude Code from Heron's own folder, never the caller's project (whose .mcp.json is not
# Heron's), and returns its exit code; its first line is kept in $script:claudeSaid. Under 'Stop',
# Windows PowerShell 5.1 turns a line on stderr into a failure, so it runs without it.
function Invoke-Claude([string]$cli, [string[]]$arguments) {
    $script:claudeSaid = ''
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $where = if (Test-Path -LiteralPath $serverDir) { $serverDir } else { [IO.Path]::GetTempPath() }
    Push-Location -LiteralPath $where
    try {
        $said = @(& $cli @arguments 2>&1 | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
        $code = $LASTEXITCODE
        if ($said) { $script:claudeSaid = $said[0] }
    } catch {
        $code = -1
        $script:claudeSaid = $_.Exception.Message
    } finally {
        Pop-Location
        $ErrorActionPreference = $old
    }
    return $code
}

function Connect-ClaudeCode {
    $say = 'Claude Code:        '
    try { $entry = Get-ClaudeCodeEntry } catch {
        "${say}could not read $claudeJson, so nothing was changed."
        return
    }
    if ($entry) {
        if (Test-StartsHeron $entry) { "${say}already connected (all projects)" }
        else { "${say}already has an ""autocad"" entry, left as it is: it starts $(Get-EntryText $entry)" }
        return
    }
    $cli = Find-ClaudeCode
    if (-not $cli) {
        "${say}not found, so nothing was added. Once Claude Code or the Claude app is installed, run this again."
        "${pad}Or add by hand, in ""mcpServers"" of a folder's .mcp.json: $handEntry"
        return
    }
    $hadFile = Test-Path -LiteralPath $claudeJson
    if ($DryRun) {
        "${say}would add ""autocad"" for all projects: ""$cli"" mcp add --scope user autocad -- ""$server"""
        if ($hadFile) { "${pad}after saving $claudeJson as .heron-backup" }
        return
    }
    if ($hadFile) { Copy-Item -LiteralPath $claudeJson "$claudeJson.heron-backup" -Force }
    $code = Invoke-Claude $cli @('mcp', 'add', '--scope', 'user', 'autocad', '--', $server)
    $entry = $null
    try { $entry = Get-ClaudeCodeEntry } catch { }
    if (Test-StartsHeron $entry) {
        "${say}connected (all projects$(if ($hadFile) { '; old settings saved as .heron-backup' }))"
    } else {
        "${say}not connected: Claude Code said ""$($script:claudeSaid)"" (code $code)."
        "${pad}Add it by hand: docs\INSTALL.md section 5."
    }
}

function Connect-ClaudeDesktop {
    $say = 'Claude Desktop:     '
    $files = @(Get-DesktopConfigs)
    if (-not $files) {
        "${say}not found, so nothing was added. Once the Claude app is installed, run this again."
        "${pad}Or add by hand, in ""mcpServers"" of its claude_desktop_config.json: $handEntry"
        return
    }
    foreach ($file in $files) {
        $which = if ($files.Count -gt 1) { " $file" } else { '' }
        if (Test-ClaudeOpen (Split-Path $file)) {
            "${say}Claude is open, so its settings file was not changed: $file"
            "${pad}Quit Claude (right-click its icon by the clock, Quit), then run this again."
            continue
        }
        try { $cfg = Read-Settings $file } catch {
            "${say}could not read $file, so it was not changed."
            continue
        }
        $entry = Get-AutocadEntry $cfg
        if ($entry) {
            if (Test-StartsHeron $entry) { "${say}already connected$which" }
            else { "${say}already has an ""autocad"" entry$which, left as it is: it starts $(Get-EntryText $entry)" }
            continue
        }
        $hadFile = Test-Path -LiteralPath $file
        if ($DryRun) {
            "${say}would add ""autocad"" to $file$(if ($hadFile) { ', after saving it as .heron-backup' })"
            continue
        }
        if ($hadFile) { Copy-Item -LiteralPath $file "$file.heron-backup" -Force }
        if (-not $cfg) { $cfg = [pscustomobject]@{} }
        if (-not ($cfg.PSObject.Properties['mcpServers'] -and $cfg.mcpServers)) {
            $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) -Force
        }
        $cfg.mcpServers | Add-Member -NotePropertyName autocad -NotePropertyValue ([pscustomobject]@{ command = $server })
        Save-Settings $file $cfg
        "${say}connected$which (restart Claude$(if ($hadFile) { '; old settings saved as .heron-backup' }))"
    }
}

# Tells Claude Code (all projects) and Claude Desktop where the server is. Returns the lines to
# show, one or two per Claude.
function Connect-Claude {
    Connect-ClaudeCode
    Connect-ClaudeDesktop
}

function Disconnect-ClaudeCode {
    $say = 'Claude Code:        '
    try { $entry = Get-ClaudeCodeEntry } catch {
        "${say}could not read $claudeJson, so nothing was removed."
        return
    }
    if (-not $entry) {
        "${say}no ""autocad"" entry, nothing to remove"
        return
    }
    if (-not (Test-StartsHeron $entry)) {
        "${say}its ""autocad"" entry starts $(Get-EntryText $entry), not this Heron, so it was kept."
        return
    }
    $cli = Find-ClaudeCode
    if (-not $cli) {
        "${say}no Claude Code found to take out its ""autocad"" entry: run ""claude mcp remove --scope user autocad"" once it is back."
        return
    }
    if ($DryRun) {
        "${say}would remove ""autocad"": ""$cli"" mcp remove --scope user autocad, after saving $claudeJson as .heron-backup"
        return
    }
    Copy-Item -LiteralPath $claudeJson "$claudeJson.heron-backup" -Force
    $code = Invoke-Claude $cli @('mcp', 'remove', '--scope', 'user', 'autocad')
    $entry = $null
    try { $entry = Get-ClaudeCodeEntry } catch { }
    if (-not $entry) { "${say}""autocad"" entry removed (old settings saved as .heron-backup)" }
    else { "${say}""autocad"" entry not removed: Claude Code said ""$($script:claudeSaid)"" (code $code)." }
}

function Disconnect-ClaudeDesktop {
    $say = 'Claude Desktop:     '
    foreach ($file in @(Get-DesktopConfigs)) {
        try { $cfg = Read-Settings $file } catch {
            "${say}could not read $file, so nothing was removed."
            continue
        }
        $entry = Get-AutocadEntry $cfg
        if (-not $entry) { continue }
        if (-not (Test-StartsHeron $entry)) {
            "${say}the ""autocad"" entry in $file starts $(Get-EntryText $entry), not this Heron, so it was kept."
            continue
        }
        if (Test-ClaudeOpen (Split-Path $file)) {
            "${say}Claude is open, so its ""autocad"" entry was left in $file."
            "${pad}Quit Claude, then take the entry out of that file by hand."
            continue
        }
        if ($DryRun) {
            "${say}would remove ""autocad"" from $file, after saving it as .heron-backup"
            continue
        }
        Copy-Item -LiteralPath $file "$file.heron-backup" -Force
        $cfg.mcpServers.PSObject.Properties.Remove('autocad')
        Save-Settings $file $cfg
        "${say}""autocad"" entry removed from $file (restart Claude; old settings saved as .heron-backup)"
    }
}

# Takes out an "autocad" entry that starts this server, in Claude Code and Claude Desktop.
# Nothing else is touched.
function Disconnect-Claude {
    Disconnect-ClaudeCode
    Disconnect-ClaudeDesktop
}

# True when Claude Code or Claude Desktop has an "autocad" entry that starts this server.
function Test-HeronInClaude {
    try { if (Test-StartsHeron (Get-ClaudeCodeEntry)) { return $true } } catch { }
    foreach ($file in @(Get-DesktopConfigs)) {
        try { if (Test-StartsHeron (Get-AutocadEntry (Read-Settings $file))) { return $true } } catch { }
    }
    return $false
}

# Does one of these acad.exe belong to this Windows user (#185)? Each item has Owner (DOMAIN\user, or ''
# when Windows would not say) and SessionId. Another user's AutoCAD on a shared server cannot touch our
# files, so it does not count; our own AutoCAD in any session of ours does. An owner Windows will not
# say counts only from our own session, which errs on the side of refusing.
function Test-OwnAutocad($processes, [string]$me, [int]$mySession) {
    foreach ($p in @($processes)) {
        if ($p.Owner) {
            if ($p.Owner -ieq $me) { return $true }
        } elseif ([int]$p.SessionId -eq $mySession) { return $true }
    }
    return $false
}

# Every acad.exe with its owner. When the process list cannot be read, one stand-in per acad.exe
# with no owner, in our own session, so the check still refuses (never a missed AutoCAD).
function Get-AutocadProcesses {
    $mine = [Diagnostics.Process]::GetCurrentProcess().SessionId
    try {
        foreach ($c in @(Get-CimInstance Win32_Process -Filter "Name = 'acad.exe'" -ErrorAction Stop)) {
            $who = ''
            try {
                $o = Invoke-CimMethod -InputObject $c -MethodName GetOwner -ErrorAction Stop
                if ($o.ReturnValue -eq 0 -and $o.User) { $who = $o.Domain + '\' + $o.User }
            } catch { }
            [pscustomobject]@{ Owner = $who; SessionId = [int]$c.SessionId }
        }
    } catch {
        foreach ($g in @(Get-Process acad -ErrorAction SilentlyContinue)) {
            [pscustomobject]@{ Owner = ''; SessionId = $mine }
        }
    }
}

# A dry run only says what -Connect or -Disconnect would change, so AutoCAD may stay open for it.
if ($DryRun) {
    [Console]::Out.WriteLine('Dry run: nothing is changed.')
    if ($Disconnect) { $lines = Disconnect-Claude }
    elseif ($Connect) { $lines = Connect-Claude }
    else { $lines = @('Use -DryRun with -Connect or -Disconnect.') }
    $lines | ForEach-Object { [Console]::Out.WriteLine($_) }
    exit 0
}

if (Test-OwnAutocad @(Get-AutocadProcesses) "$env:USERDOMAIN\$env:USERNAME" ([Diagnostics.Process]::GetCurrentProcess().SessionId)) {
    Write-Host 'AutoCAD is open. Close AutoCAD, then run this again. Nothing was changed.' -ForegroundColor Yellow
    exit 1
}

# Run by the setup program after it copied the files, and by its uninstaller before it removes
# them. It shows these lines on its last page.
if ($Connect) { Connect-Claude | ForEach-Object { [Console]::Out.WriteLine($_) }; exit 0 }
if ($Disconnect) { Disconnect-Claude | ForEach-Object { [Console]::Out.WriteLine($_) }; exit 0 }

if ($Uninstall) {
    # Installed with the setup program: its own uninstaller removes every file it put there.
    if (Get-ChildItem $serverDir -Filter 'unins*.exe' -ErrorAction SilentlyContinue) {
        Write-Host 'Heron was installed with its setup program, so remove it the Windows way:' -ForegroundColor Yellow
        Write-Host '  Windows Settings > Apps, find "Heron AI for AutoCAD", Uninstall' -ForegroundColor Yellow
        Write-Host '  (or Start menu > Heron AI for AutoCAD > Remove Heron AI for AutoCAD). Nothing was removed.' -ForegroundColor Yellow
        exit 0
    }
    if (-not ((Test-Path $target) -or (Test-Path $server) -or (Test-HeronInClaude))) {
        Write-Host 'Heron AI for AutoCAD is not installed for this Windows user. Nothing to remove.' -ForegroundColor Yellow
        exit 0
    }

    Write-Host 'This removes Heron AI for AutoCAD for your Windows user:'
    Write-Host "  - the plug-in   $target"
    Write-Host "  - the server    $server"
    if (Test-Path $previous) { Write-Host "  - the earlier version kept for Rollback.bat   $previous" }
    Write-Host '  - the "autocad" entry in Claude Code and Claude Desktop, where it starts this server'
    Write-Host 'Your drawings and your other Claude settings are not touched.'
    Write-Host ''
    $answer = Read-Host 'Remove Heron? Type Y and press Enter to remove it, or just press Enter to keep it'
    if ($answer -notmatch '^\s*(y|yes)\s*$') {
        Write-Host 'Kept. Nothing was removed.' -ForegroundColor Green
        exit 0
    }

    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    if (Test-Path $server) { Remove-Item $server -Force }
    if (Test-Path $previous) { Remove-Item $previous -Recurse -Force }
    Disconnect-Claude | ForEach-Object { Write-Host $_ }
    Write-Host 'Heron AI for AutoCAD removed. Restart Claude Desktop if it is open.' -ForegroundColor Green
    exit 0
}

if ($Rollback) {
    $oldBundle = Join-Path $previous 'HeronAutoCAD.bundle'
    $oldServer = Join-Path $previous 'autocad-mcp.exe'
    if (-not ((Test-Path $oldBundle) -and (Test-Path $oldServer))) {
        Write-Host 'There is no earlier version kept on this PC to go back to. Nothing was changed.' -ForegroundColor Yellow
        exit 0
    }
    Write-Host ('Installed now:  ' + (Get-BundleVersion $target))
    Write-Host ('Kept earlier:   ' + (Get-BundleVersion $oldBundle))
    $answer = Read-Host 'Go back to the earlier version? Type Y and press Enter, or just press Enter to keep this one'
    if ($answer -notmatch '^\s*(y|yes)\s*$') {
        Write-Host 'Kept. Nothing was changed.' -ForegroundColor Green
        exit 0
    }
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Copy-Item $oldBundle $target -Recurse
    Copy-Item $oldServer $server -Force
    Write-Host ('Back on ' + (Get-BundleVersion $target) + '. Restart Claude Desktop if it is open.') -ForegroundColor Green
    exit 0
}

$bundle = Join-Path $here 'HeronAutoCAD.bundle'
$exe = Join-Path $here 'autocad-mcp.exe'
if (-not ((Test-Path $bundle) -and (Test-Path $exe))) {
    Write-Host 'Some of the installer''s files are missing from this folder.' -ForegroundColor Red
    Write-Host 'Unzip the whole zip into one folder first, then double-click Install.bat inside that folder. Nothing was changed.' -ForegroundColor Red
    exit 1
}

$was = Get-BundleVersion $target
$now = Get-BundleVersion $bundle
if ($was) { Write-Host "Updating Heron from $was to $now." } else { Write-Host "Installing Heron $now." }

# 0. keep what is there now, so Rollback.bat can put it back and a failed copy is undone
New-Item -ItemType Directory -Force $serverDir | Out-Null
if ($was -and (Test-Path $server)) {
    if (Test-Path $previous) { Remove-Item $previous -Recurse -Force }
    New-Item -ItemType Directory -Force $previous | Out-Null
    Copy-Item $target (Join-Path $previous 'HeronAutoCAD.bundle') -Recurse
    Copy-Item $server (Join-Path $previous 'autocad-mcp.exe') -Force
    Write-Host "Earlier version kept: $previous"
}

try {
    # 1. plug-in
    New-Item -ItemType Directory -Force $plugins | Out-Null
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Copy-Item $bundle $target -Recurse
    Write-Host "Plug-in installed:  $target"

    # 2. server
    Copy-Item $exe $server -Force
    Write-Host "Server installed:   $server"
} catch {
    if ($was -and (Test-Path (Join-Path $previous 'HeronAutoCAD.bundle'))) {
        if (Test-Path $target) { Remove-Item $target -Recurse -Force }
        Copy-Item (Join-Path $previous 'HeronAutoCAD.bundle') $target -Recurse
        Copy-Item (Join-Path $previous 'autocad-mcp.exe') $server -Force
        Write-Host "The copy failed, so $was was put back." -ForegroundColor Yellow
    }
    throw
}

# Check what landed is what was meant to land.
if ((Get-BundleVersion $target) -ne $now -or -not (Test-Path $server) -or (Get-Item $server).Length -ne (Get-Item $exe).Length) {
    Write-Host 'The files on disk are not the ones just installed. Run Install.bat again with AutoCAD and Claude closed.' -ForegroundColor Red
    exit 1
}
Write-Host "Checked:            plug-in $now and the server are in place"

# 3. connect Claude
Connect-Claude | ForEach-Object { Write-Host $_ }

Write-Host ''
Write-Host 'Done. Start AutoCAD, open the Heron tab and press Heron to connect.' -ForegroundColor Green
Write-Host 'To remove Heron later, double-click Uninstall.bat in this folder.'
if ($was) { Write-Host 'If this version gives trouble, Rollback.bat puts back the one before.' }
