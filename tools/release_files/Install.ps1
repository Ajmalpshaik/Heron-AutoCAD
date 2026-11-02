# Installs Heron AI for AutoCAD for the current Windows user. No administrator rights needed.
#   1. the plug-in  -> %APPDATA%\Autodesk\ApplicationPlugins\HeronAutoCAD.bundle
#   2. the server   -> %LOCALAPPDATA%\Heron\autocad\autocad-mcp.exe
#   3. tells Claude Code and Claude Desktop where the server is (existing settings are kept)
param([switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$plugins = Join-Path $env:APPDATA 'Autodesk\ApplicationPlugins'
$target = Join-Path $plugins 'HeronAutoCAD.bundle'
$serverDir = Join-Path $env:LOCALAPPDATA 'Heron\autocad'
$server = Join-Path $serverDir 'autocad-mcp.exe'
$desktopCfg = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'

# Windows PowerShell's "utf8" adds a byte-order mark, which Claude Desktop cannot read.
function Save-Config($cfg) {
    [IO.File]::WriteAllText($desktopCfg, ($cfg | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding $false))
}

if (Get-Process acad -ErrorAction SilentlyContinue) {
    Write-Host 'AutoCAD is running. Close AutoCAD, then run this again. Nothing was changed.' -ForegroundColor Yellow
    exit 1
}

if ($Uninstall) {
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    if (Test-Path $server) { Remove-Item $server -Force }
    if (Get-Command claude -ErrorAction SilentlyContinue) { claude mcp remove autocad 2>$null | Out-Null }
    if (Test-Path $desktopCfg) {
        $cfg = Get-Content $desktopCfg -Raw | ConvertFrom-Json
        if ($cfg.mcpServers -and $cfg.mcpServers.PSObject.Properties['autocad']) {
            $cfg.mcpServers.PSObject.Properties.Remove('autocad')
            Save-Config $cfg
        }
    }
    Write-Host 'Heron AI for AutoCAD removed.' -ForegroundColor Green
    exit 0
}

$bundle = Join-Path $here 'HeronAutoCAD.bundle'
$exe = Join-Path $here 'autocad-mcp.exe'
if (-not ((Test-Path $bundle) -and (Test-Path $exe))) {
    Write-Host 'HeronAutoCAD.bundle and autocad-mcp.exe must be next to this file.' -ForegroundColor Red
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
    claude mcp remove autocad 2>$null | Out-Null
    claude mcp add --scope user autocad -- $server | Out-Null
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
