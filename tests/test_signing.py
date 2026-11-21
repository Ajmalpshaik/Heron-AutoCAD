"""Code signing is prepared but needs a certificate Ajmal has not bought (issue #72, D-99).

Without one nothing is signed and the build says so; with one, signtool signs Heron's own
files and the password never reaches a log. Whether AutoCAD's SECURELOAD then stays quiet is
a live row (docs/NEEDS-CHECKING.md Group AK).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
RELEASE_YML = ROOT / ".github" / "workflows" / "release.yml"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(TOOLS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(TOOLS))
    return module


@pytest.fixture()
def signing():
    return _load("signing")


@pytest.fixture()
def cert_env(tmp_path):
    pfx = tmp_path / "heron.pfx"
    pfx.write_bytes(b"not a real certificate")
    signtool = tmp_path / "signtool.exe"
    signtool.write_bytes(b"MZ")
    return {"HERON_SIGN_PFX": str(pfx), "HERON_SIGN_PASSWORD": "s3cret$pw", "HERON_SIGNTOOL": str(signtool)}


def test_without_a_certificate_nothing_is_signed_and_the_build_says_so_once(signing, capsys):
    calls = []
    assert signing.sign([Path("a.dll")], env={}, run=lambda *a, **k: calls.append(a)) is False
    assert signing.sign([Path("b.exe")], env={}, run=lambda *a, **k: calls.append(a)) is False
    assert calls == []
    out = capsys.readouterr().out
    assert out.count("Not signed") == 1 and "Ajmal's decision (#164)" in out and "ask once" in out
    assert signing.inno_sign_tool({}) is None


def test_half_a_configuration_stops_the_build(signing, cert_env):
    with pytest.raises(SystemExit, match="Set both, or neither"):
        signing.certificate({"HERON_SIGN_PFX": cert_env["HERON_SIGN_PFX"]})
    with pytest.raises(SystemExit, match="HERON_SIGN_PASSWORD is set but HERON_SIGN_PFX is not"):
        signing.certificate({"HERON_SIGN_PASSWORD": "x"})
    with pytest.raises(SystemExit, match="ends in a backslash"):
        signing.certificate({**cert_env, "HERON_SIGN_PASSWORD": "pw\\"})
    with pytest.raises(SystemExit, match="not a file"):
        signing.certificate({"HERON_SIGN_PFX": "missing.pfx", "HERON_SIGN_PASSWORD": "x"})


def test_with_a_certificate_signtool_signs_with_sha256_and_a_timestamp(signing, cert_env):
    seen = {}

    def run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0, "Successfully signed", "")

    files = [Path("Contents/R24/Heron.AutoCAD.Addin.dll"), Path("autocad-mcp.exe")]
    assert signing.sign(files, env=cert_env, run=run) is True
    command = seen["command"]
    assert command[:2] == [cert_env["HERON_SIGNTOOL"], "sign"]
    assert command[command.index("/f") + 1] == cert_env["HERON_SIGN_PFX"]
    assert command[command.index("/fd") + 1] == "sha256" and command[command.index("/td") + 1] == "sha256"
    assert command[command.index("/tr") + 1] == signing.TIMESTAMP
    assert command[-2:] == [str(f) for f in files]


def test_a_failed_signing_stops_the_build_without_showing_the_password(signing, cert_env):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", f"SignTool Error: bad password {cert_env['HERON_SIGN_PASSWORD']}")

    with pytest.raises(SystemExit) as stopped:
        signing.sign([Path("a.dll")], env=cert_env, run=run)
    assert cert_env["HERON_SIGN_PASSWORD"] not in str(stopped.value) and "***" in str(stopped.value)


def test_the_setup_sign_tool_quotes_paths_and_escapes_dollars(signing, cert_env, tmp_path):
    odd = tmp_path / "a$b"
    odd.mkdir()
    (odd / "heron.pfx").write_bytes(b"x")
    escaped = signing.inno_sign_tool({**cert_env, "HERON_SIGN_PFX": str(odd / "heron.pfx")})
    assert "$q" + str(odd / "heron.pfx").replace("$", "$$") + "$q" in escaped
    hidden = signing.hide("ISCC: /p s3cret$$pw and s3cret$pw", cert_env)
    assert "s3cret" not in hidden and hidden.count("***") == 2
    command = signing.inno_sign_tool(cert_env)
    assert command.startswith(f"$q{cert_env['HERON_SIGNTOOL']}$q sign ")
    assert "/p $qs3cret$$pw$q" in command, "ISCC reads $ as $f / $q / $p: a $ in the password is doubled"
    assert command.endswith(" $f") and '"' not in command


def test_only_herons_own_dlls_are_signed(tmp_path):
    bundle = tmp_path / "HeronAutoCAD.bundle"
    for folder in ("R24", "R25", "R26"):
        contents = bundle / "Contents" / folder
        contents.mkdir(parents=True)
        for name in ("Heron.AutoCAD.Addin.dll", "Heron.AutoCAD.Bridge.dll", "System.Text.Json.dll"):
            (contents / name).write_bytes(b"MZ")
    own = _load("make_release").own_dlls(bundle)
    assert len(own) == 6 and all(p.name.startswith("Heron.") for p in own)


def test_make_release_signs_the_dlls_the_server_and_install_ps1():
    text = (TOOLS / "make_release.py").read_text(encoding="utf-8")
    main = text[text.index("def main()"):text.index("def write_checksums")]
    assert main.index("signing.sign(own_dlls(") < main.index("copytree"), "sign the DLLs before they are packed"
    assert main.index("signing.sign([exe])") < main.index('copy2(exe, folder / "autocad-mcp.exe")')
    assert main.index('signing.sign([folder / "Install.ps1"])') < main.index("make_archive")


# ---------------------------------------------------------------------------
# release.yml
# ---------------------------------------------------------------------------


def _steps() -> dict[str, str]:
    """Each step of the build job, by its name (or its uses: line). PyYAML is not a dependency."""
    text = RELEASE_YML.read_text(encoding="utf-8")
    build = text[text.index("\n  build:\n"):text.index("\n  signing-dry-run:\n")]
    steps = {}
    for chunk in build.split("\n      - ")[1:]:
        key = chunk.splitlines()[0].split(":", 1)[1].strip()
        steps[key] = chunk
    return steps


def test_signing_needs_both_secrets_and_is_skipped_with_a_note_without_them():
    steps = _steps()
    cert = steps["Code-signing certificate (skipped when the repository has none)"]
    assert "PFX_BASE64: ${{ secrets.HERON_SIGN_PFX_BASE64 }}" in cert
    assert "PFX_PASSWORD: ${{ secrets.HERON_SIGN_PFX_PASSWORD }}" in cert
    assert "::notice title=Not signed::" in cert and "Set both, or neither" in cert
    for name in ("Build the zip", "Build the setup"):
        assert "HERON_SIGN_PFX: ${{ steps.certificate.outputs.pfx }}" in steps[name]
        assert "HERON_SIGN_PASSWORD: ${{ secrets.HERON_SIGN_PFX_PASSWORD }}" in steps[name]
    assert "if: always()" in steps["Remove the certificate file"]
    text = RELEASE_YML.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("if:"):
            assert "secrets." not in line, "secrets cannot be read in an if:"
    assert "echo $env:PFX" not in text and "Write-Output $env:PFX" not in text, "never print a secret"
    # Only the two build steps and the certificate step ever see a signing secret.
    holders = [name for name, step in steps.items() if "HERON_SIGN_PFX" in step and "secrets." in step]
    assert sorted(holders) == ["Build the setup", "Build the zip", "Code-signing certificate (skipped when the repository has none)"]


def test_the_setup_is_built_with_a_pinned_checked_inno_setup_and_published():
    get = (TOOLS / "installer" / "Get-InnoSetup.ps1").read_text(encoding="ascii")
    assert "https://api.nuget.org/v3-flatcontainer/tools.innosetup/6.7.3/tools.innosetup.6.7.3.nupkg" in get
    sha = get.split("$sha256 = '", 1)[1].split("'")[0]
    assert len(sha) == 64 and int(sha, 16) >= 0
    assert get.index("Get-FileHash") < get.index("Expand-Archive") < get.index("Get-AuthenticodeSignature") < get.index("HERON_ISCC=")
    steps = _steps()
    assert "run: ./tools/installer/Get-InnoSetup.ps1" in steps["Get Inno Setup (pinned and checked)"]
    assert "run: python tools/make_installer.py" in steps["Build the setup"]
    names = list(steps)
    assert names.index("Build the zip") < names.index("Build the setup"), "the setup is made from the zip's folder"
    assert "dist/HeronAutoCAD-*-setup.exe" in steps["actions/upload-artifact@v7"]
    assert "dist/HeronAutoCAD-*-setup.exe" in steps["Publish the pre-release"]


def test_a_run_by_hand_proves_signing_with_a_throwaway_certificate():
    text = RELEASE_YML.read_text(encoding="utf-8")
    job = text[text.index("  signing-dry-run:"):]
    assert "if: github.event_name == 'workflow_dispatch'" in job
    assert "gh release" not in job and "upload-artifact" not in job, "nothing signed with a test certificate leaves the machine"
    assert "secrets." not in job, "the dry run never touches the real certificate"
    assert "::add-mask::" in job and "dry$run-" in job
    assert "./tools/installer/Check-Signing.ps1 -Dist dist" in job
    check = (TOOLS / "installer" / "Check-Signing.ps1").read_text(encoding="ascii")
    for part in ("Heron.*.dll", "autocad-mcp.exe", "Install.ps1", "TimeStamperCertificate", "System.*.dll", "exit 1"):
        assert part in check, part
