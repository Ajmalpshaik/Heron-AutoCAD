# Signs a whole build with a throwaway test certificate made on GitHub's machine, then checks
# every file that should carry a signature does (D-99, #72). release.yml runs it on runs started
# by hand, so the signing path is proved before any certificate is bought. Nothing it signs is
# published, and the test certificate goes with the machine.
param([Parameter(Mandatory = $true)] [string]$Dist)
$ErrorActionPreference = 'Stop'
$subject = 'CN=Heron signing dry run'
$script:failures = 0
function Check([bool]$ok, [string]$what) {
    if ($ok) { Write-Output "PASS  $what" } else { Write-Output "FAIL  $what"; $script:failures++ }
}

$bundle = Join-Path $Dist 'HeronAutoCAD.bundle'
$folder = Get-ChildItem $Dist -Directory -Filter 'HeronAutoCAD-*-win64' | Select-Object -First 1
$setup = Get-ChildItem $Dist -Filter 'HeronAutoCAD-*-setup.exe' | Select-Object -First 1
$ours = @(Get-ChildItem (Join-Path $bundle 'Contents') -Recurse -Filter 'Heron.*.dll')
$ours += @(Get-ChildItem (Join-Path $folder.FullName 'HeronAutoCAD.bundle\Contents') -Recurse -Filter 'Heron.*.dll')
$ours += Get-Item (Join-Path $folder.FullName 'autocad-mcp.exe')
$ours += Get-Item (Join-Path $folder.FullName 'Install.ps1')
$ours += $setup
Check ($ours.Count -ge 15) "found $($ours.Count) files that must be signed"
foreach ($f in $ours) {
    $sig = Get-AuthenticodeSignature $f.FullName
    Check ($sig.SignerCertificate -and $sig.SignerCertificate.Subject -eq $subject) "$($f.Name) is signed by the test certificate"
    Check ([bool]$sig.TimeStamperCertificate) "$($f.Name) has a time stamp"
}
# Microsoft's own DLLs keep Microsoft's signature.
foreach ($f in Get-ChildItem (Join-Path $bundle 'Contents') -Recurse -Filter 'System.*.dll') {
    $sig = Get-AuthenticodeSignature $f.FullName
    Check (-not $sig.SignerCertificate -or $sig.SignerCertificate.Subject -ne $subject) "$($f.Name) was left alone"
}
if ($script:failures) { Write-Output "$($script:failures) check(s) FAILED."; exit 1 }
Write-Output 'Signing works end to end with a certificate file. A bought certificate still needs its own live rows (AK9-AK11).'
