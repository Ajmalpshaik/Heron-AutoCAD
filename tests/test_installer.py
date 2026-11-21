"""The one-file setup (issue #73, D-99): what it packs, where it puts it, which versions it says.

Inno Setup runs only on Windows, so the setup itself is built and run by release.yml and
proved live (docs/NEEDS-CHECKING.md Group AK). These tests read the script and the build
script offline.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
ISS = TOOLS / "installer" / "HeronAutoCAD.iss"
INSTALL_PS1 = TOOLS / "release_files" / "Install.ps1"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(TOOLS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(TOOLS))
    return module


@pytest.fixture(scope="module")
def mi():
    return _load("make_installer")


def _script() -> str:
    return ISS.read_text(encoding="ascii")


def _section(name: str) -> list[str]:
    """The lines of one [Section] of the script, without comments or blank lines."""
    lines, inside = [], False
    for line in _script().splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            inside = stripped == f"[{name}]"
            continue
        if inside and stripped and not stripped.startswith(";") and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _setup() -> dict[str, str]:
    return dict(line.split("=", 1) for line in _section("Setup"))


def _entries(section: str) -> list[dict[str, str]]:
    found = []
    for line in _section(section):
        parts = [p.strip() for p in line.split(";") if p.strip()]
        found.append({k.strip(): v.strip().strip('"') for k, v in (p.split(":", 1) for p in parts)})
    return found


def _install_ps1() -> str:
    return INSTALL_PS1.read_text(encoding="ascii")


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def test_the_setup_takes_its_versions_from_the_two_version_files(mi, tmp_path):
    props = (ROOT / "autocad" / "Directory.Build.props").read_text(encoding="utf-8")
    plugin = re.search(r"<Version>([^<]+)</Version>", props).group(1).strip()
    server = re.search(r'__version__ = "([^"]+)"', (ROOT / "src" / "autocad_mcp" / "__init__.py").read_text(encoding="utf-8")).group(1)
    values = mi.defines(tmp_path / "rel", tmp_path / "out")
    assert values["AppVersion"] == plugin
    assert values["ServerVersion"] == server
    assert values["SetupName"] == f"HeronAutoCAD-{plugin}-setup"
    assert mi.release_folder().name == f"HeronAutoCAD-{plugin}-win64"


def test_the_script_types_no_version_of_its_own():
    setup = _setup()
    assert setup["AppVersion"] == "{#AppVersion}"
    assert setup["VersionInfoVersion"] == "{#AppVersion}"
    assert "{#ServerVersion}" in setup["VersionInfoDescription"]
    assert setup["OutputBaseFilename"] == "{#SetupName}"
    for line in _section("Setup") + _section("Files") + _section("Code"):
        assert not re.search(r"\b\d+\.\d+\.\d+\b", line), f"a typed-in version: {line}"
    assert "#error" in _script(), "built by hand without the versions, the script must refuse"


def test_the_setup_is_the_same_product_as_the_bundle(mi):
    # One identity for the life of the product: Windows tells an update from another program by it.
    assert _setup()["AppId"] == "{" + mi.build_plugin.UPGRADE_CODE


# ---------------------------------------------------------------------------
# Files: what it packs and where they go
# ---------------------------------------------------------------------------


def test_the_setup_packs_exactly_what_make_installer_checks_for(mi):
    sources = [e["Source"] for e in _entries("Files")]
    packed = {s.removeprefix("{#ReleaseDir}\\").split("\\")[0] for s in sources}
    assert all(s.startswith("{#ReleaseDir}\\") for s in sources)
    assert packed == set(mi.PACKED)


def test_everything_it_packs_is_in_the_release_folder_make_release_makes(mi):
    made = {mi.build_plugin.BUNDLE, "autocad-mcp.exe"} | {f.name for f in (TOOLS / "release_files").iterdir()}
    assert set(mi.PACKED) <= made


def test_the_setup_installs_where_install_bat_does():
    ps1 = _install_ps1()
    assert "$plugins = Join-Path $env:APPDATA 'Autodesk\\ApplicationPlugins'" in ps1
    assert "$serverDir = Join-Path $env:LOCALAPPDATA 'Heron\\autocad'" in ps1
    assert _setup()["DefaultDirName"] == "{localappdata}\\Heron\\autocad"
    assert _setup()["DisableDirPage"] == "yes" and _setup()["UsePreviousAppDir"] == "no"
    files = {e["Source"].removeprefix("{#ReleaseDir}\\").split("\\")[0]: e["DestDir"] for e in _entries("Files")}
    assert files["HeronAutoCAD.bundle"] == "{userappdata}\\Autodesk\\ApplicationPlugins\\HeronAutoCAD.bundle"
    assert files["autocad-mcp.exe"] == files["Install.ps1"] == files["CheckForUpdate.bat"] == "{app}"


def test_an_update_replaces_the_whole_bundle_as_install_bat_does():
    delete = _entries("InstallDelete")
    assert delete == [{"Type": "filesandordirs", "Name": "{userappdata}\\Autodesk\\ApplicationPlugins\\HeronAutoCAD.bundle"}]


def test_uninstall_keeps_the_modellers_own_files():
    # Saved commands, check lists, logs and the audit live in %LOCALAPPDATA%\Heron\autocad too.
    assert _entries("UninstallDelete") == [{"Type": "filesandordirs", "Name": "{app}\\previous"}]


def test_the_start_menu_has_the_update_check_and_remove():
    icons = {e["Name"].split("\\")[-1]: e["Filename"] for e in _entries("Icons")}
    assert icons == {"Check for a newer Heron": "{app}\\CheckForUpdate.bat", "Remove Heron AI for AutoCAD": "{uninstallexe}"}
    assert "-CheckUpdate" in (TOOLS / "release_files" / "CheckForUpdate.bat").read_text(encoding="ascii")


# ---------------------------------------------------------------------------
# Behaviour: per user, refuses while AutoCAD runs, sets Claude up as Install.bat does
# ---------------------------------------------------------------------------


def test_the_setup_needs_no_administrator():
    setup = _setup()
    assert setup["PrivilegesRequired"] == "lowest"
    assert "PrivilegesRequiredOverridesAllowed" not in setup, "no all-users choice: per user only"
    assert setup["CloseApplications"] == "no", "it refuses instead of closing programs itself"


def _function(name: str) -> str:
    code = _script()[_script().index("[Code]"):]
    start = re.search(rf"^(function|procedure) {name}\b", code, re.M).start()
    end = code.index("\nend;", start)
    return code[start:end]


def test_setup_and_uninstall_refuse_while_autocad_runs():
    assert "IsRunning('acad.exe', '')" in _function("InTheWay")
    assert "IsRunning('autocad-mcp.exe', ServerDir)" in _function("InTheWay")
    for name in ("InitializeSetup", "PrepareToInstall", "InitializeUninstall"):
        assert "InTheWay(" in _function(name), f"{name} must refuse while AutoCAD runs"
    assert "Nothing was changed." in _function("InitializeSetup")
    assert "Nothing was removed." in _function("InitializeUninstall")


def test_the_setup_sets_claude_up_with_install_ps1():
    assert "InstallScript('-Connect')" in _function("CurStepChanged") and "ssPostInstall" in _function("CurStepChanged")
    assert "InstallScript('-Disconnect')" in _function("CurUninstallStepChanged")
    assert "usUninstall" in _function("CurUninstallStepChanged"), "before the files go, while Install.ps1 is still there"
    assert "{sys}\\WindowsPowerShell\\v1.0\\powershell.exe" in _function("PowerShell"), "an absolute path to PowerShell"
    assert "ConnectReport" in _function("CurPageChanged"), "the last page says what was set up"


def test_install_ps1_has_one_way_to_set_claude_up():
    ps1 = _install_ps1()
    assert ps1.count("'mcp', 'add'") == 1, "the setup and Install.bat must share one Connect-Claude"
    assert ps1.count("Connect-Claude |") == 2 and ps1.count("Disconnect-Claude |") == 2
    acad = ps1.index("Get-Process acad")
    for mode in ("if ($Connect)", "if ($Disconnect)"):
        assert acad < ps1.index(mode) < ps1.index("if ($Uninstall)"), f"{mode} must come after the AutoCAD check"
    connect = ps1[ps1.index("if ($Connect)"):ps1.index("if ($Uninstall)")]
    assert "Read-Host" not in connect and "Remove-Item" not in connect


def test_install_bat_uninstall_sends_a_setup_install_to_windows_apps():
    ps1 = _install_ps1()
    uninstall = ps1[ps1.index("if ($Uninstall)"):ps1.index("$bundle = Join-Path")]
    assert uninstall.index("unins*.exe") < uninstall.index("Read-Host")
    assert "Remove-Item $previous" in uninstall, "the kept earlier version goes too"


def test_the_installer_files_are_plain_ascii_with_windows_line_endings():
    for path in (TOOLS / "installer").iterdir():
        data = path.read_bytes()
        data.decode("ascii")
        assert data.count(b"\n") == data.count(b"\r\n"), f"{path.name}: needs CRLF line endings"


# ---------------------------------------------------------------------------
# make_installer.py
# ---------------------------------------------------------------------------


def test_iscc_is_given_the_versions_and_a_sign_tool_only_with_a_certificate(mi, tmp_path):
    plain = mi.iscc_command(Path("ISCC.exe"), tmp_path / "rel", tmp_path / "out")
    assert plain[0] == "ISCC.exe" and plain[-1] == str(mi.SCRIPT)
    assert f"/DAppVersion={mi.build_plugin.VERSION}" in plain and f"/DServerVersion={mi.server_version()}" in plain
    assert not any(a.startswith("/S") or a.startswith("/DSignTool") for a in plain)
    signed = mi.iscc_command(Path("ISCC.exe"), tmp_path / "rel", tmp_path / "out", "signtool sign $f")
    assert "/DSignTool=heron" in signed and "/Sheron=signtool sign $f" in signed
    assert "SignTool={#SignTool}" in _script() and "SignedUninstaller=yes" in _script()


def _fake_release(mi, folder: Path) -> Path:
    built = {}
    for tfm, *_ in mi.build_plugin.SERIES:
        out = folder.parent / "built" / tfm
        out.mkdir(parents=True)
        (out / mi.build_plugin.MODULE).write_bytes(b"MZ")
        built[tfm] = out
    folder.mkdir(parents=True)
    mi.build_plugin.make_bundle(built, folder)
    for name in mi.PACKED[1:]:
        (folder / name).write_bytes(b"x")
    return folder


def test_a_full_release_folder_has_nothing_missing(mi, tmp_path):
    assert mi.missing(_fake_release(mi, tmp_path / "rel")) == []


def test_a_part_release_folder_is_named_in_plain_words(mi, tmp_path):
    folder = _fake_release(mi, tmp_path / "rel")
    (folder / "Install.ps1").unlink()
    (folder / "HeronAutoCAD.bundle" / "Contents" / "R25" / mi.build_plugin.MODULE).unlink()
    problems = mi.missing(folder)
    assert any("Install.ps1" in p for p in problems)
    assert any("R25" in p and "AutoCAD 2025-2026" in p for p in problems)


def test_no_release_folder_says_run_make_release_first(mi, monkeypatch, tmp_path):
    monkeypatch.setattr(mi.build_plugin, "DIST", tmp_path)
    with pytest.raises(SystemExit, match="make_release.py first"):
        mi.main()


def test_a_wrong_iscc_path_is_refused(mi, tmp_path):
    with pytest.raises(SystemExit, match="not a file"):
        mi.find_iscc({"HERON_ISCC": str(tmp_path / "nope.exe")})
    iscc = tmp_path / "ISCC.exe"
    iscc.write_bytes(b"MZ")
    assert mi.find_iscc({"HERON_ISCC": str(iscc)}) == iscc


def test_checksums_list_the_zip_then_the_setup(tmp_path):
    import hashlib

    archive, setup = tmp_path / "HeronAutoCAD-1.7.0-win64.zip", tmp_path / "HeronAutoCAD-1.7.0-setup.exe"
    archive.write_bytes(b"PK zip")
    setup.write_bytes(b"MZ setup")
    sums = _load("make_release").write_checksums(archive, setup).read_text(encoding="ascii")
    assert sums == (
        f"{hashlib.sha256(b'PK zip').hexdigest()}  {archive.name}\n"
        f"{hashlib.sha256(b'MZ setup').hexdigest()}  {setup.name}\n"
    )
