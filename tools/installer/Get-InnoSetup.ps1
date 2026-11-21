# Fetches Inno Setup's compiler for release.yml: the NuGet copy of 6.7.3, pinned (D-99).
# It is used only when its SHA-256 is the pinned one and ISCC.exe carries a valid signature
# from Inno Setup's authors (Pyrsys B.V.). Then HERON_ISCC names it for the next steps.
$ErrorActionPreference = 'Stop'
$url = 'https://api.nuget.org/v3-flatcontainer/tools.innosetup/6.7.3/tools.innosetup.6.7.3.nupkg'
$sha256 = 'F780898E402FF80612CC8D9FCB8C6E02932BD1CB4C900FFDAA31F9341CFB49F4'
$signer = 'Pyrsys B.V.'

$pkg = Join-Path $env:RUNNER_TEMP 'innosetup.zip'
Invoke-WebRequest -Uri $url -OutFile $pkg
$hash = (Get-FileHash $pkg -Algorithm SHA256).Hash
if ($hash -ne $sha256) {
    Write-Output "::error::Inno Setup's download is not the one pinned (SHA-256 $hash). Nothing was built with it."
    exit 1
}
$dir = Join-Path $env:RUNNER_TEMP 'innosetup'
Expand-Archive $pkg $dir -Force
$iscc = Join-Path $dir 'tools\ISCC.exe'
$sig = Get-AuthenticodeSignature $iscc
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch [regex]::Escape($signer)) {
    Write-Output "::error::ISCC.exe is not signed by $signer ($($sig.Status)). Nothing was built with it."
    exit 1
}
[IO.File]::AppendAllText($env:GITHUB_ENV, "HERON_ISCC=$iscc`n")
Write-Output "Inno Setup 6.7.3: $iscc (SHA-256 and signature checked)"
