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
param([switch]$Uninstall, [switch]$Rollback, [switch]$CheckUpdate, [switch]$Connect, [switch]$Disconnect)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$plugins = Join-Path $env:APPDATA 'Autodesk\ApplicationPlugins'
$target = Join-Path $plugins 'HeronAutoCAD.bundle'
$serverDir = Join-Path $env:LOCALAPPDATA 'Heron\autocad'
$server = Join-Path $serverDir 'autocad-mcp.exe'
$desktopCfg = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'
# The version an update replaced, kept so Rollback.bat can put it back.
$previous = Join-Path $serverDir 'previous'
$releases = 'https://api.github.com/repos/Ajmalpshaik/Heron-AutoCAD/releases/latest'

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
        $latest = Invoke-RestMethod -Uri $releases -TimeoutSec 15
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

# Windows PowerShell's "utf8" adds a byte-order mark, which Claude Desktop cannot read. Its
# Get-Content reads a file without one as ANSI, so the file is read with ReadAllText (UTF-8).
function Save-Config($cfg) {
    [IO.File]::WriteAllText($desktopCfg, ($cfg | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding $false))
}

# "claude mcp remove" prints an error when there is nothing to remove. Under 'Stop',
# Windows PowerShell 5.1 turns any such line into a failure, so run claude without it.
function Invoke-Claude([string[]]$arguments) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & claude @arguments 2>$null | Out-Null } finally { $ErrorActionPreference = $old }
}

# Tells Claude Code (all projects) and Claude Desktop where the server is. Other settings are
# kept; Claude Desktop's file is saved as .heron-backup first. Returns one line per Claude.
function Connect-Claude {
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        Invoke-Claude @('mcp', 'remove', 'autocad')
        Invoke-Claude @('mcp', 'add', '--scope', 'user', 'autocad', '--', $server)
        'Claude Code:        connected (all projects)'
    } else {
        'Claude Code:        not found, skipped'
    }
    $desktopDir = Split-Path $desktopCfg
    if (-not (Test-Path $desktopDir)) {
        'Claude Desktop:     not found, skipped'
        return
    }
    $cfg = [pscustomobject]@{}
    if (Test-Path $desktopCfg) {
        Copy-Item $desktopCfg "$desktopCfg.heron-backup" -Force
        $raw = [IO.File]::ReadAllText($desktopCfg)
        if ($raw -and $raw.Trim()) { $cfg = $raw | ConvertFrom-Json }
    }
    if (-not $cfg.PSObject.Properties['mcpServers']) {
        $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
    }
    $entry = [pscustomobject]@{ command = $server }
    if ($cfg.mcpServers.PSObject.Properties['autocad']) { $cfg.mcpServers.autocad = $entry }
    else { $cfg.mcpServers | Add-Member -NotePropertyName autocad -NotePropertyValue $entry }
    Save-Config $cfg
    'Claude Desktop:     connected (restart it; old settings saved as .heron-backup)'
}

# Takes the "autocad" entry out of Claude Code and Claude Desktop. Nothing else is touched.
function Disconnect-Claude {
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        Invoke-Claude @('mcp', 'remove', 'autocad')
        'Claude Code:        "autocad" entry removed'
    }
    if (Test-Path $desktopCfg) {
        $raw = [IO.File]::ReadAllText($desktopCfg)
        if ($raw -and $raw.Trim()) {
            $cfg = $raw | ConvertFrom-Json
            if ($cfg.mcpServers -and $cfg.mcpServers.PSObject.Properties['autocad']) {
                $cfg.mcpServers.PSObject.Properties.Remove('autocad')
                Save-Config $cfg
                'Claude Desktop:     "autocad" entry removed (restart it)'
            }
        }
    }
}

if (Get-Process acad -ErrorAction SilentlyContinue) {
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
    $hasClaude = [bool](Get-Command claude -ErrorAction SilentlyContinue)
    $inDesktop = $false
    if (Test-Path $desktopCfg) {
        $raw = [IO.File]::ReadAllText($desktopCfg)
        if ($raw -and $raw.Trim()) {
            $cfg = $raw | ConvertFrom-Json
            $inDesktop = [bool]($cfg.mcpServers -and $cfg.mcpServers.PSObject.Properties['autocad'])
        }
    }
    if (-not ((Test-Path $target) -or (Test-Path $server) -or $inDesktop)) {
        Write-Host 'Heron AI for AutoCAD is not installed for this Windows user. Nothing to remove.' -ForegroundColor Yellow
        exit 0
    }

    Write-Host 'This removes Heron AI for AutoCAD for your Windows user:'
    Write-Host "  - the plug-in   $target"
    Write-Host "  - the server    $server"
    if (Test-Path $previous) { Write-Host "  - the earlier version kept for Rollback.bat   $previous" }
    Write-Host '  - the "autocad" entry in Claude Code and Claude Desktop'
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
    Disconnect-Claude | Out-Null
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
