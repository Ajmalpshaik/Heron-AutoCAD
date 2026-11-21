"""Every folder Heron keeps files in is absolute, even with %LOCALAPPDATA% / %APPDATA% unset (#43, #134).

Windows always sets both. Off Windows, or with one empty or relative, a bare
Path("") would put Heron's files in whatever folder the server started in.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from autocad_mcp import palette
from autocad_mcp.core import audit, bridge, diagnose, folders, project_notes
from autocad_mcp.tools import checklists, patterns, saved_commands

ROOT = Path(__file__).resolve().parents[1]


def _install_plugin():
    spec = importlib.util.spec_from_file_location("install_plugin", ROOT / "tools" / "install_plugin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Every folder Heron keeps files in, and its last part.
HERON_FOLDERS = [
    (audit.audit_dir, "audit"),
    (bridge.bridges_dir, "bridges"),
    (project_notes.notes_dir, "projects"),
    (checklists.lists_dir, "checklists"),
    (saved_commands.commands_dir, "commands"),
    (patterns.support_folder, "support"),
    (palette.server_file, "server.json"),
]


@pytest.fixture
def unset(monkeypatch, tmp_path):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home, monkeypatch


@pytest.mark.parametrize("value", [None, "", "  ", "relative/folder"])
def test_local_app_data_falls_back_under_the_home(unset, value):
    home, monkeypatch = unset
    if value is None:
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    else:
        monkeypatch.setenv("LOCALAPPDATA", value)
    assert folders.local_app_data() == home / "AppData" / "Local"
    assert folders.heron_local() == home / "AppData" / "Local" / "Heron" / "autocad"


@pytest.mark.parametrize("value", [None, "", "relative"])
def test_roaming_app_data_falls_back_under_the_home(unset, value):
    home, monkeypatch = unset
    if value is None:
        monkeypatch.delenv("APPDATA", raising=False)
    else:
        monkeypatch.setenv("APPDATA", value)
    assert folders.roaming_app_data() == home / "AppData" / "Roaming"
    assert diagnose.plugins_dir() == home / "AppData" / "Roaming" / "Autodesk" / "ApplicationPlugins"
    assert _install_plugin().plugins_dir() == diagnose.plugins_dir()


def test_a_set_variable_is_used_as_it_is(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "L"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "R"))
    assert folders.local_app_data() == tmp_path / "L"
    assert folders.roaming_app_data() == tmp_path / "R"


@pytest.mark.parametrize("folder,leaf", HERON_FOLDERS)
def test_every_heron_folder_is_absolute_and_under_the_home_when_unset(unset, folder, leaf):
    home, monkeypatch = unset
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    out = folder()
    assert out.is_absolute(), out
    assert out.parts[: len(home.parts) + 4] == (home / "AppData" / "Local" / "Heron" / "autocad").parts
    assert leaf in out.parts


def test_no_module_builds_a_folder_from_the_bare_variable():
    """The trap itself: Path(os.environ.get("LOCALAPPDATA", "")) anywhere in the server."""
    src = ROOT / "src" / "autocad_mcp"
    offenders = [
        str(path.relative_to(ROOT))
        for path in src.rglob("*.py")
        if 'os.environ.get("LOCALAPPDATA"' in path.read_text(encoding="utf-8")
        or 'os.environ.get("APPDATA"' in path.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
