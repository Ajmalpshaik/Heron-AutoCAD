"""Release polish (#185, #232): this user's AutoCAD only, LF checksums, no .pdb in the bundle.

Nothing here starts AutoCAD or installs anything. The process lists are made up.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
INSTALL_PS1 = TOOLS / "release_files" / "Install.ps1"
POWERSHELL = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(TOOLS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(TOOLS))
    return module


# ---------------------------------------------------------------------------
# #185: only this Windows user's AutoCAD stops Install.ps1
# ---------------------------------------------------------------------------


def _function_text(name: str) -> str:
    text = INSTALL_PS1.read_text(encoding="ascii").replace("\r\n", "\n")
    start = text.index(f"function {name}")
    return text[start : text.index("\n}\n", start) + 3]


needs_powershell = pytest.mark.skipif(
    sys.platform != "win32" or not POWERSHELL.is_file(), reason="Install.ps1 runs in Windows PowerShell 5.1"
)


def _own_autocad(processes: list[dict], me: str = "OFFICE\\ajmal", session: int = 2) -> bool:
    """Run Install.ps1's own Test-OwnAutocad on a made-up process list."""
    script = (
        _function_text("Test-OwnAutocad")
        + "\n$list = @(ConvertFrom-Json $env:FAKE_PROCESSES)\n"
        + f"[Console]::Out.WriteLine((Test-OwnAutocad $list '{me}' {session}))\n"
    )
    done = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", "-"],
        input=script, capture_output=True, text=True, timeout=60,
        env={**os.environ, "FAKE_PROCESSES": json.dumps(processes)},
    )  # fmt: skip
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout.strip() == "True"


@needs_powershell
def test_no_autocad_at_all_does_not_stop_the_install():
    assert _own_autocad([]) is False


@needs_powershell
def test_another_users_autocad_on_a_shared_server_does_not_stop_it():
    other = [{"Owner": "OFFICE\\colleague", "SessionId": 3}, {"Owner": "OFFICE\\other", "SessionId": 4}]
    assert _own_autocad(other) is False


@needs_powershell
def test_my_own_autocad_stops_it_in_this_session_and_in_a_disconnected_one():
    assert _own_autocad([{"Owner": "OFFICE\\ajmal", "SessionId": 2}]) is True
    assert _own_autocad([{"Owner": "OFFICE\\ajmal", "SessionId": 7}]) is True, "session 7 is mine, left running"


@needs_powershell
def test_mine_among_others_still_stops_it_and_the_name_ignores_case():
    mixed = [{"Owner": "OFFICE\\colleague", "SessionId": 3}, {"Owner": "office\\AJMAL", "SessionId": 5}]
    assert _own_autocad(mixed) is True


@needs_powershell
def test_an_owner_windows_will_not_say_counts_only_from_my_own_session():
    assert _own_autocad([{"Owner": "", "SessionId": 2}]) is True
    assert _own_autocad([{"Owner": "", "SessionId": 3}]) is False


@needs_powershell
def test_the_same_name_in_another_domain_is_another_user():
    assert _own_autocad([{"Owner": "OTHERPC\\ajmal", "SessionId": 3}]) is False


def test_install_ps1_asks_for_this_users_autocad_only():
    text = INSTALL_PS1.read_text(encoding="ascii")
    refuse = re.search(r"if \(Test-OwnAutocad [^\n]*\{\r?\n\s*Write-Host 'AutoCAD is open\.", text)
    assert refuse, "the refusal must come from Test-OwnAutocad"
    assert "Get-AutocadProcesses" in refuse.group(0) and "$env:USERDOMAIN" in refuse.group(0)
    assert "GetOwner" in _function_text("Get-AutocadProcesses")
    # When the process list cannot be read it still refuses.
    assert "Get-Process acad" in _function_text("Get-AutocadProcesses")


# ---------------------------------------------------------------------------
# #232: checksums.txt line endings, no .pdb
# ---------------------------------------------------------------------------


def test_checksums_use_lf_so_sha256sum_check_parses_them(tmp_path):
    archive, setup = tmp_path / "HeronAutoCAD-1.8.1-win64.zip", tmp_path / "HeronAutoCAD-1.8.1-setup.exe"
    archive.write_bytes(b"PK zip")
    setup.write_bytes(b"MZ setup")
    raw = _load("make_release").write_checksums(archive, setup).read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    # What `sha256sum -c` reads: "<64 hex>  <name>" per line, the name with no trailing carriage return.
    checked = {}
    for line in raw.decode("ascii").split("\n")[:-1]:
        found = re.fullmatch(r"([0-9a-f]{64})  (\S+)", line)
        assert found, f"sha256sum would reject {line!r}"
        checked[found.group(2)] = found.group(1)
    for f in (archive, setup):
        assert checked[f.name] == hashlib.sha256(f.read_bytes()).hexdigest()


def test_the_bundle_leaves_pdb_files_out(tmp_path):
    build = _load("build_plugin")
    built = {}
    for tfm, *_ in ((t, 0) for t in ("net48", "net8.0-windows", "net10.0-windows")):
        folder = tmp_path / "bin" / tfm
        folder.mkdir(parents=True)
        (folder / build.MODULE).write_bytes(b"MZ")
        (folder / "Heron.AutoCAD.Addin.pdb").write_bytes(b"pdb")
        (folder / "Heron.Bridge.PDB").write_bytes(b"pdb")
        (folder / "Heron.Bridge.dll").write_bytes(b"MZ")
        built[tfm] = folder
    bundle = build.make_bundle(built, tmp_path / "dist")
    files = [p.name for p in bundle.rglob("*") if p.is_file()]
    assert not [n for n in files if n.lower().endswith(".pdb")]
    assert files.count("Heron.Bridge.dll") == 3 and files.count(build.MODULE) == 3


def test_a_release_folder_with_a_pdb_fails_the_build(tmp_path):
    release = _load("make_release")
    (tmp_path / "HeronAutoCAD.bundle" / "Contents" / "R24").mkdir(parents=True)
    (tmp_path / "HeronAutoCAD.bundle" / "Contents" / "R24" / "Heron.AutoCAD.Addin.dll").write_bytes(b"MZ")
    release.check_no_debug_files(tmp_path)  # clean: passes
    (tmp_path / "HeronAutoCAD.bundle" / "Contents" / "R24" / "Heron.AutoCAD.Addin.pdb").write_bytes(b"x")
    with pytest.raises(SystemExit, match=r"R24/Heron\.AutoCAD\.Addin\.pdb"):
        release.check_no_debug_files(tmp_path)


def test_make_release_runs_the_pdb_check_before_it_zips():
    text = (TOOLS / "make_release.py").read_text(encoding="utf-8")
    main = text[text.index("def main()") : text.index("def check_no_debug_files")]
    assert main.index("check_no_debug_files(folder)") < main.index("make_archive")


def test_the_release_check_looks_for_pdb_files_and_crlf_checksums():
    text = (TOOLS / "installer" / "Check-Setup.ps1").read_text(encoding="ascii")
    assert "-Filter '*.pdb'" in text and "no .pdb debug file in the release folder" in text
    assert "no .pdb debug file in the installed plug-in" in text
    assert "checksums.txt has LF line endings" in text
