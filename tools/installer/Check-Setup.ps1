# Tries the built setup on GitHub's Windows machine, with no AutoCAD (D-99). release.yml runs it
# after building. It changes the Windows user profile it runs in, so it refuses to run anywhere
# else unless HERON_CHECK_SETUP_HERE=1 is set on a throwaway machine. Never on a modeller's PC.
#
#   1. the zip's Install.ps1 (Windows PowerShell 5.1), as Install.bat runs it
#   2. the setup over that zip install, with a stale file in the old bundle
#   3. the zip's Uninstall.bat route on a setup install: it must send you to Windows Apps
#   4. a stand-in Heron server in another folder (a developer's .venv) must not stop the setup;
#      one in the install folder must. Then the setup and its uninstaller while a stand-in
#      "acad.exe" runs: both must refuse
#   5. the uninstaller: Heron's files and Claude entries go, the modeller's own files stay
# Claude Code is a stand-in claude.cmd that writes down how it was called and writes the entry
# into .claude.json the way "claude mcp add/remove" does; Claude Desktop is a config file with
# one other entry, which must survive, and from step 2 also the Microsoft Store app's data
# folder (#233).
param([Parameter(Mandatory = $true)] [string]$Dist)
$ErrorActionPreference = 'Stop'
if (-not $env:GITHUB_ACTIONS -and -not $env:HERON_CHECK_SETUP_HERE) {
    throw 'This installs and removes Heron in the Windows profile it runs in. It runs on GitHub''s machine; elsewhere set HERON_CHECK_SETUP_HERE=1, on a throwaway machine only.'
}

$setup = Get-ChildItem $Dist -Filter 'HeronAutoCAD-*-setup.exe' | Select-Object -First 1
$zip = Get-ChildItem $Dist -Directory -Filter 'HeronAutoCAD-*-win64' | Select-Object -First 1
if (-not $setup -or -not $zip) { throw "No setup or release folder in $Dist. Build them first." }
$version = $setup.Name -replace '^HeronAutoCAD-(.+)-setup\.exe$', '$1'
$bundle = Join-Path $env:APPDATA 'Autodesk\ApplicationPlugins\HeronAutoCAD.bundle'
$app = Join-Path $env:LOCALAPPDATA 'Heron\autocad'
$server = Join-Path $app 'autocad-mcp.exe'
$desktopCfg = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json'
$storeCfg = Join-Path $env:LOCALAPPDATA 'Claude-Data\anthropicpbc.claude_heroncheck\claude_desktop_config.json'
$claudeJson = Join-Path $env:USERPROFILE '.claude.json'
$menu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Heron AI for AutoCAD'
$appKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{9B2C4D6E-8F10-4A3B-8C5D-7E9F1A2B3C40}_is1'
$winps = Join-Path $env:windir 'System32\WindowsPowerShell\v1.0\powershell.exe'
$work = Join-Path $(if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }) 'heron-check-setup'
$logs = Join-Path $work 'logs'
New-Item -ItemType Directory -Force $logs | Out-Null

$script:failures = 0
function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Output "PASS  $what" } else { Write-Output "FAIL  $what"; $script:failures++ }
}

# Claude Code: a stand-in that writes down its arguments and keeps .claude.json as claude does.
# Claude Desktop: a config with another entry.
$bin = Join-Path $work 'bin'
New-Item -ItemType Directory -Force $bin | Out-Null
$calls = Join-Path $work 'claude-calls.txt'
$escaped = $server -replace '\\', '\\'
Set-Content (Join-Path $bin 'claude.cmd') @(
    '@echo off',
    "echo %*>>`"$calls`"",
    "if `"%2`"==`"add`" echo {`"mcpServers`":{`"autocad`":{`"type`":`"stdio`",`"command`":`"$escaped`",`"args`":[]}}}>`"$claudeJson`"",
    "if `"%2`"==`"remove`" echo {`"mcpServers`":{}}>`"$claudeJson`""
) -Encoding ascii
$env:PATH = "$bin;$env:PATH"
Remove-Item $claudeJson -Force -ErrorAction SilentlyContinue

function Code-Entry {
    if (-not (Test-Path $claudeJson)) { return $null }
    $cfg = Get-Content $claudeJson -Raw | ConvertFrom-Json
    if ($cfg.mcpServers -and $cfg.mcpServers.PSObject.Properties['autocad']) { return [string]$cfg.mcpServers.autocad.command }
    return $null
}

function Store-Entry([string]$name) {
    $cfg = Get-Content $storeCfg -Raw | ConvertFrom-Json
    if ($cfg.mcpServers -and $cfg.mcpServers.PSObject.Properties[$name]) { return [string]$cfg.mcpServers.$name.command }
    return $null
}
New-Item -ItemType Directory -Force (Split-Path $desktopCfg) | Out-Null
Set-Content $desktopCfg '{"mcpServers":{"other":{"command":"x"}}}' -Encoding ascii
# The modeller's own files, which no uninstall may touch.
New-Item -ItemType Directory -Force (Join-Path $app 'commands') | Out-Null
Set-Content (Join-Path $app 'commands\keep.json') '{}' -Encoding ascii

function Desktop-Entry([string]$name) {
    $cfg = Get-Content $desktopCfg -Raw | ConvertFrom-Json
    if ($cfg.mcpServers.PSObject.Properties[$name]) { return [string]$cfg.mcpServers.$name.command }
    return $null
}

function Run-Setup([string]$name) {
    $log = Join-Path $logs "$name.log"
    $p = Start-Process $setup.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$log`"" -Wait -PassThru
    return $p.ExitCode
}

function Run-Uninstall([string]$name) {
    $unins = Get-ChildItem $app -Filter 'unins*.exe' | Select-Object -First 1
    if (-not $unins) { return -1 }
    $log = Join-Path $logs "$name.log"
    $p = Start-Process $unins.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$log`"" -Wait -PassThru
    # The uninstaller hands the work to a copy of itself in TEMP: give that copy time to finish.
    for ($i = 0; $i -lt 60 -and (Test-Path $appKey); $i++) { Start-Sleep -Seconds 1 }
    Start-Sleep -Seconds 3
    return $p.ExitCode
}

# A stand-in program: ping.exe under another name in a folder, waiting.
function Start-StandIn([string]$dir, [string]$name) {
    New-Item -ItemType Directory -Force (Join-Path $dir 'en-US') | Out-Null
    $fake = Join-Path $dir $name
    Copy-Item (Join-Path $env:windir 'System32\ping.exe') $fake -Force
    $mui = Join-Path $env:windir 'System32\en-US\ping.exe.mui'
    if (Test-Path $mui) { Copy-Item $mui (Join-Path $dir "en-US\$name.mui") -Force }
    $p = Start-Process $fake -ArgumentList '-n', '600', '127.0.0.1' -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    # Out-Host: a line written here would otherwise be returned along with the process.
    Check (-not $p.HasExited) "the stand-in $name in $dir is running" | Out-Host
    return $p
}

Write-Output "Trying HeronAutoCAD $version setup on $([Environment]::OSVersion.VersionString), as $env:USERNAME"

# 1. the zip, as Install.bat runs it
$out = & $winps -NoProfile -ExecutionPolicy Bypass -File (Join-Path $zip.FullName 'Install.ps1') 2>&1 | Out-String
Set-Content (Join-Path $logs 'zip-install.txt') $out
Check ($LASTEXITCODE -eq 0) "zip Install.ps1 finished (exit $LASTEXITCODE)"
Check (Test-Path (Join-Path $bundle 'PackageContents.xml')) 'zip: the plug-in is in ApplicationPlugins'
Check (Test-Path $server) 'zip: the server is in %LOCALAPPDATA%\Heron\autocad'
Check (-not (Get-ChildItem $zip.FullName -Recurse -Filter '*.pdb' -File)) 'zip: no .pdb debug file in the release folder (#232)'
Check (-not (Get-ChildItem $bundle -Recurse -Filter '*.pdb' -File)) 'zip: no .pdb debug file in the installed plug-in (#232)'
$sums = Join-Path $Dist 'checksums.txt'
Check ((Test-Path $sums) -and -not ([IO.File]::ReadAllText($sums).Contains("`r"))) 'checksums.txt has LF line endings (#232)'
Check ((Desktop-Entry 'autocad') -eq $server) 'zip: Claude Desktop points at the server'
Check ((Code-Entry) -eq $server) 'zip: Claude Code points at the server'
Check ($out -match 'Claude Code:\s+connected \(all projects\)') 'zip: it says Claude Code is connected'

# 2. the setup over the zip install, with a file the new version does not have. The Claude
#    settings the zip wrote are wiped first, so what is found after comes from the setup.
#    The Microsoft Store Claude app's data folder is there too now (#233).
$stale = Join-Path $bundle 'Contents\R24\stale-from-old-version.dll'
Set-Content $stale 'old' -Encoding ascii
Set-Content $desktopCfg '{"mcpServers":{"other":{"command":"x"}}}' -Encoding ascii
Remove-Item "$desktopCfg.heron-backup" -Force
Remove-Item $calls -Force
Remove-Item $claudeJson, "$claudeJson.heron-backup" -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force (Split-Path $storeCfg) | Out-Null
Set-Content $storeCfg '{"preferences":{"a":{"b":1}},"mcpServers":{"other":{"command":"y"}}}' -Encoding ascii
$code = Run-Setup 'setup-over-zip'
Check ($code -eq 0) "setup over the zip install finished (exit $code)"
Check (-not (Test-Path $stale)) 'setup: the old bundle was replaced whole (stale file gone)'
Check ((Select-String -Path (Join-Path $bundle 'PackageContents.xml') -Pattern "AppVersion=`"$([regex]::Escape($version))`"" -Quiet)) "setup: the bundle says $version"
foreach ($f in 'autocad-mcp.exe', 'Install.ps1', 'CheckForUpdate.bat') {
    Check (Test-Path (Join-Path $app $f)) "setup: $f is in %LOCALAPPDATA%\Heron\autocad"
}
Check ([bool](Get-ChildItem $app -Filter 'unins*.exe')) 'setup: its uninstaller is there'
Check (-not (Test-Path "$bundle.heron-old")) 'setup: the old plug-in it moved aside is gone'
$listed = & $server --list-tools 2>&1 | Out-String
Check (($LASTEXITCODE -eq 0) -and ($listed -match 'autocad_status')) 'setup: the installed server starts and lists its tools'
$entry = Get-ItemProperty $appKey -ErrorAction SilentlyContinue
Check ($entry -and $entry.DisplayVersion -eq $version -and $entry.Publisher -eq 'Ajmal PS') "setup: Windows Apps lists Heron $version by Ajmal PS"
Check ((Test-Path (Join-Path $menu 'Check for a newer Heron.lnk')) -and (Test-Path (Join-Path $menu 'Remove Heron AI for AutoCAD.lnk'))) 'setup: the two Start menu entries are there'
Check ((Desktop-Entry 'autocad') -eq $server) 'setup: Claude Desktop points at the server'
Check ((Desktop-Entry 'other') -eq 'x') 'setup: the other Claude Desktop entry is kept'
Check (Test-Path "$desktopCfg.heron-backup") 'setup: the old Claude Desktop file is kept as .heron-backup'
Check ((Get-Content $calls -Raw) -match [regex]::Escape("mcp add --scope user autocad -- $server")) 'setup: Claude Code was given the server for all projects'
Check ((Code-Entry) -eq $server) 'setup: Claude Code points at the server'
Check ((Store-Entry 'autocad') -eq $server) 'setup: the Store Claude app points at the server'
Check ((Store-Entry 'other') -eq 'y') 'setup: the Store Claude app''s other entry is kept'
Check (Test-Path "$storeCfg.heron-backup") 'setup: the Store Claude app''s old file is kept as .heron-backup'
Check ((Select-String -Path (Join-Path $logs 'setup-over-zip.log') -Pattern 'Install.ps1 -Connect: Claude Code:\s+connected \(all projects' -Quiet)) 'setup: its log says Claude Code is connected'

# ...and a setup run again leaves the entries as they are, and says so
Remove-Item $calls -Force
$code = Run-Setup 'setup-again'
Check ($code -eq 0) "setup run again finished (exit $code)"
Check (-not (Test-Path $calls)) 'setup again: Claude Code was not called (its entry is already there)'
Check ((Select-String -Path (Join-Path $logs 'setup-again.log') -Pattern 'Claude Code:\s+already connected' -Quiet)) 'setup again: its log says Claude Code is already connected'
Check ((Desktop-Entry 'autocad') -eq $server -and (Store-Entry 'autocad') -eq $server) 'setup again: both Claude Desktop files still point at the server'

# 3. the zip's Uninstall route on a setup install removes nothing
$out = & $winps -NoProfile -ExecutionPolicy Bypass -File (Join-Path $zip.FullName 'Install.ps1') -Uninstall 2>&1 | Out-String
Check (($out -match 'installed with its setup program') -and (Test-Path $server)) 'Uninstall.bat on a setup install sends you to Windows Apps and removes nothing'

# 4. a server in another folder does not stop the setup; the installed server does
$dev = Start-StandIn (Join-Path $work 'dev-venv') 'autocad-mcp.exe'
$code = Run-Setup 'setup-while-dev-server'
Check ($code -eq 0) "setup not stopped by a Heron server running from another folder (exit $code)"
Stop-Process -Id $dev.Id -Force
$real = Join-Path $work 'autocad-mcp.exe.installed'
Move-Item $server $real -Force
$running = Start-StandIn $app 'autocad-mcp.exe'
$code = Run-Setup 'setup-while-server'
Check ($code -eq 1) "setup refused at the start while the installed server runs (exit $code, want 1)"
Stop-Process -Id $running.Id -Force
Start-Sleep -Seconds 1
Move-Item $real $server -Force
Remove-Item (Join-Path $app 'en-US') -Recurse -Force

# ...and the setup and its uninstaller both refuse while AutoCAD runs
$acad = Start-StandIn (Join-Path $work 'fakeacad') 'acad.exe'
# A file an install would remove ([InstallDelete] and the move aside): it must still be there.
$marker = Join-Path $bundle 'marker-setup-must-not-touch.txt'
Set-Content $marker 'x' -Encoding ascii
$code = Run-Setup 'setup-while-acad'
Check ($code -eq 1) "setup refused at the start while acad.exe runs (exit $code, want 1)"
Check ((Test-Path $marker) -and (Test-Path $server)) 'setup while acad.exe runs changed nothing'
$code = Run-Uninstall 'uninstall-while-acad'
Check ((Test-Path $server) -and (Test-Path $appKey) -and (Test-Path $marker)) "uninstall refused while acad.exe runs (exit $code), nothing removed"
Stop-Process -Id $acad.Id -Force
Start-Sleep -Seconds 1
# The marker is not the setup's file, so its uninstaller would rightly leave it (and the folder).
Remove-Item $marker -Force

# 5. uninstall
$previous = Join-Path $app 'previous'
New-Item -ItemType Directory -Force $previous | Out-Null
Set-Content (Join-Path $previous 'kept-by-install-bat.txt') 'old' -Encoding ascii
$removes = @(Get-Content $calls -ErrorAction SilentlyContinue | Where-Object { $_ -match 'mcp remove --scope user autocad' }).Count
$code = Run-Uninstall 'uninstall'
Check ($code -eq 0) "uninstall finished (exit $code)"
Check (-not (Test-Path $bundle)) 'uninstall: the plug-in is gone'
foreach ($f in 'autocad-mcp.exe', 'Install.ps1', 'CheckForUpdate.bat', 'previous') {
    Check (-not (Test-Path (Join-Path $app $f))) "uninstall: $f is gone"
}
Check (-not (Test-Path $appKey)) 'uninstall: Windows Apps no longer lists Heron'
Check (-not (Test-Path $menu)) 'uninstall: the Start menu entries are gone'
Check ($null -eq (Desktop-Entry 'autocad')) 'uninstall: the Claude Desktop entry is gone'
Check ((Desktop-Entry 'other') -eq 'x') 'uninstall: the other Claude Desktop entry is kept'
Check (@(Get-Content $calls -ErrorAction SilentlyContinue | Where-Object { $_ -match 'mcp remove --scope user autocad' }).Count -gt $removes) 'uninstall: Claude Code was told to remove its entry, for all projects only'
Check ($null -eq (Code-Entry)) 'uninstall: the Claude Code entry is gone'
Check ($null -eq (Store-Entry 'autocad') -and (Store-Entry 'other') -eq 'y') 'uninstall: the Store Claude app''s entry is gone, its other entry kept'
Check (Test-Path (Join-Path $app 'commands\keep.json')) 'uninstall: the modeller''s own files are kept'

Write-Output ''
if ($script:failures) {
    Write-Output "$($script:failures) check(s) FAILED. The logs:"
    Get-ChildItem $logs | ForEach-Object { Write-Output "----- $($_.Name)"; Get-Content $_.FullName -Tail 40 }
    exit 1
}
Write-Output 'Every check passed. This is GitHub''s Windows machine with no AutoCAD: Group AK still needs a real PC.'
