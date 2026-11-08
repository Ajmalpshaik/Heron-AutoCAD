# Installs Heron AI for AutoCAD for the current Windows user. No administrator rights needed.
#   1. the plug-in  -> %APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle
#   2. the server   -> %LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe
#   3. tells Claude Code and Claude Desktop where the server is (existing settings are kept)
# -Uninstall removes all three, after asking. Uninstall.bat runs it that way.
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$plugins = Join-Path $env:APPDATA 'Autodesk\ApplicationPlugins'
$target = Join-Path $plugins 'HeronAutoCAD.bundle'
$serverDir = Join-Path $env:LOCALAPPDATA 'Heron\autocad'
$server = Join-Path $serverDir 'autocad-mcp.exe'
$desktopCfg = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'

# Anything unexpected: say it in plain words, not a PowerShell error.
trap {
    Write-Host ''
    Write-Host "Heron could not finish. Windows said: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Close AutoCAD and Claude, then try again. If it happens again, send this window''s text to whoever gave you Heron.' -ForegroundColor Red
    exit 1
}

# Windows PowerShell's "utf8" adds a byte-order mark, which Claude Desktop cannot read.
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

if (Get-Process acad -ErrorAction SilentlyContinue) {
    Write-Host 'AutoCAD is open. Close AutoCAD, then run this again. Nothing was changed.' -ForegroundColor Yellow
    exit 1
}

if ($Uninstall) {
    $hasClaude = [bool](Get-Command claude -ErrorAction SilentlyContinue)
    $inDesktop = $false
    if (Test-Path $desktopCfg) {
        $cfg = Get-Content $desktopCfg -Raw | ConvertFrom-Json
        $inDesktop = [bool]($cfg.mcpServers -and $cfg.mcpServers.PSObject.Properties['autocad'])
    }
    if (-not ((Test-Path $target) -or (Test-Path $server) -or $inDesktop)) {
        Write-Host 'Heron AI for AutoCAD is not installed for this Windows user. Nothing to remove.' -ForegroundColor Yellow
        exit 0
    }

    Write-Host 'This removes Heron AI for AutoCAD for your Windows user:'
    Write-Host "  - the plug-in   $target"
    Write-Host "  - the server    $server"
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
    if ($hasClaude) { Invoke-Claude @('mcp', 'remove', 'autocad') }
    if ($inDesktop) {
        $cfg.mcpServers.PSObject.Properties.Remove('autocad')
        Save-Config $cfg
    }
    Write-Host 'Heron AI for AutoCAD removed. Restart Claude Desktop if it is open.' -ForegroundColor Green
    exit 0
}

$bundle = Join-Path $here 'HeronAutoCAD.bundle'
$exe = Join-Path $here 'autocad-mcp.exe'
if (-not ((Test-Path $bundle) -and (Test-Path $exe))) {
    Write-Host 'Some of the installer''s files are missing from this folder.' -ForegroundColor Red
    Write-Host 'Unzip the whole zip into one folder first, then double-click Install.bat inside that folder. Nothing was changed.' -ForegroundColor Red
    exit 1
}

# 1. plug-in
New-Item -ItemType Directory -Force $plugins | Out-Null
if (Test-Path $target) { Remove-Item $target -Recurse -Force }
Copy-Item $bundle $target -Recurse
Write-Host "Plug-in installed:  $target"

# 2. server
New-Item -ItemType Directory -Force $serverDir | Out-Null
Copy-Item $exe $server -Force
Write-Host "Server installed:   $server"

# 3. connect Claude
if (Get-Command claude -ErrorAction SilentlyContinue) {
    Invoke-Claude @('mcp', 'remove', 'autocad')
    Invoke-Claude @('mcp', 'add', '--scope', 'user', 'autocad', '--', $server)
    Write-Host 'Claude Code:        connected (all projects)'
} else {
    Write-Host 'Claude Code:        not found, skipped'
}
$desktopDir = Split-Path $desktopCfg
if (Test-Path $desktopDir) {
    if (Test-Path $desktopCfg) {
        Copy-Item $desktopCfg "$desktopCfg.heron-backup" -Force
        $cfg = Get-Content $desktopCfg -Raw | ConvertFrom-Json
    } else {
        $cfg = [pscustomobject]@{}
    }
    if (-not $cfg.PSObject.Properties['mcpServers']) {
        $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
    }
    $entry = [pscustomobject]@{ command = $server }
    if ($cfg.mcpServers.PSObject.Properties['autocad']) { $cfg.mcpServers.autocad = $entry }
    else { $cfg.mcpServers | Add-Member -NotePropertyName autocad -NotePropertyValue $entry }
    Save-Config $cfg
    Write-Host 'Claude Desktop:     connected (restart it; old settings saved as .heron-backup)'
} else {
    Write-Host 'Claude Desktop:     not found, skipped'
}

Write-Host ''
Write-Host 'Done. Start AutoCAD, open the Heron tab and press Heron to connect.' -ForegroundColor Green
Write-Host 'To remove Heron later, double-click Uninstall.bat in this folder.'
