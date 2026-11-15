"""Saved commands (D-55), the installer's update and rollback, and the release build. No AutoCAD."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
from pathlib import Path

import pytest

from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import register_all, saved_commands, sequence

register_all()  # a saved command is checked against the real tools, as a sequence is

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "tools" / "release_files"

BOX = {"tool": "autocad_draw_rectangle", "args": {"corner1": [0, 0], "corner2": ["{{width}}", "{{depth}}"], "layer": "{{layer}}"},
       "label": "plinth {{width}} x {{depth}}"}  # fmt: skip
INPUTS = {
    "width": {"description": "plinth width, mm", "example": 1200},
    "depth": {"description": "plinth depth, mm", "example": 800},
    "layer": {"description": "layer", "default": "S-PLINTH"},
}


def test_fill_keeps_a_whole_inputs_type_and_writes_it_into_text():
    filled = saved_commands.fill([BOX], {"width": 1500, "depth": 900, "layer": "S-X"})[0]
    assert filled["args"]["corner2"] == [1500, 900]
    assert filled["args"]["layer"] == "S-X"
    assert filled["label"] == "plinth 1500 x 900"


def test_a_command_is_saved_listed_shown_run_and_deleted(monkeypatch):
    saved = json.loads(asyncio.run(saved_commands.autocad_saved_command(
        action="save", name="Plinth", steps=[BOX], inputs=INPUTS, description="a plinth under a pump")))  # fmt: skip
    assert saved == {"saved": "Plinth", "inputs": ["depth", "layer", "width"], "steps": 1}
    listed = json.loads(asyncio.run(saved_commands.autocad_saved_command(action="list")))["commands"]
    assert listed[0]["name"] == "Plinth" and listed[0]["description"] == "a plinth under a pump"

    seen = {}

    async def body(steps, stop_on_error, dry_run):
        seen["steps"] = steps
        return json.dumps({"dry_run": dry_run, "ran": 1, "failed": 0, "skipped": 0, "steps": []})

    body.__wrapped__ = body
    monkeypatch.setattr(sequence, "autocad_sequence", body)
    report = json.loads(asyncio.run(saved_commands.autocad_saved_command(action="run", name="plinth", inputs={"width": 2000, "depth": 600})))
    assert report["command"] == "Plinth" and report["inputs"] == {"width": 2000, "depth": 600, "layer": "S-PLINTH"}
    assert seen["steps"][0]["args"]["corner2"] == [2000, 600]
    asyncio.run(saved_commands.autocad_saved_command(action="delete", name="Plinth"))
    assert json.loads(asyncio.run(saved_commands.autocad_saved_command(action="list")))["commands"] == []


@pytest.mark.parametrize(
    "steps, inputs, words",
    [
        ([BOX], {"width": INPUTS["width"], "depth": INPUTS["depth"]}, "not declared"),
        ([BOX], {**INPUTS, "colour": {"example": 1}}, "not used"),
        ([BOX], {**INPUTS, "width": {"description": "no example"}}, "needs an 'example'"),
        ([{"tool": "autocad_save_drawing", "args": {}}], {}, "publish tool"),
        ([{"tool": "autocad_saved_command", "args": {"action": "run", "name": "x"}}], {}, "cannot run another"),
    ],
)
def test_a_wrong_command_is_refused_and_nothing_is_saved(steps, inputs, words):
    result = asyncio.run(saved_commands.autocad_saved_command(action="save", name="bad", steps=steps, inputs=inputs))
    assert result.startswith("Error:") and words in result
    assert not saved_commands._file("bad").exists()


def test_running_with_a_missing_or_unknown_input_runs_nothing():
    asyncio.run(saved_commands.autocad_saved_command(action="save", name="Plinth", steps=[BOX], inputs=INPUTS))
    assert "needs 'width'" in asyncio.run(saved_commands.autocad_saved_command(action="run", name="Plinth", inputs={"depth": 1}))
    assert "no input called height" in asyncio.run(
        saved_commands.autocad_saved_command(action="run", name="Plinth", inputs={"width": 1, "depth": 1, "height": 3}))  # fmt: skip


def test_a_sequence_cannot_hold_a_saved_command():
    with pytest.raises(Exception) as caught:
        sequence.plan_steps([{"tool": "autocad_saved_command", "args": {"action": "list"}}])
    assert "saved command" in str(caught.value)


def test_a_saved_command_holds_the_changes_padlock_like_a_sequence():
    assert risk_of("autocad_saved_command") is Risk.CHANGE is risk_of("autocad_sequence")


# ---------------------------------------------------------------------------
# Installer and release
# ---------------------------------------------------------------------------


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT / "tools"))
    return module


def test_the_bundle_says_the_same_version_as_the_dlls():
    props = (ROOT / "autocad" / "Directory.Build.props").read_text(encoding="utf-8")
    assert _load("build_plugin").VERSION == re.search(r"<Version>([^<]+)</Version>", props).group(1)


def test_checksums_name_the_zip_and_its_sha256(tmp_path):
    archive = tmp_path / "HeronAutoCAD-1.5.0-win64.zip"
    archive.write_bytes(b"PK test")
    sums = _load("make_release").write_checksums(archive).read_text(encoding="ascii")
    import hashlib

    assert sums == f"{hashlib.sha256(b'PK test').hexdigest()}  {archive.name}\n"


def test_an_update_keeps_the_version_it_replaces_and_rollback_asks_first():
    script = (RELEASE / "Install.ps1").read_text(encoding="ascii")
    install = script[script.index("$was = Get-BundleVersion"):]
    assert install.index("$previous") < install.index("Remove-Item $target"), "keep the old one before removing it"
    rollback = script[script.index("if ($Rollback)"):script.index("$bundle = Join-Path")]
    assert rollback.index("Read-Host") < rollback.index("Remove-Item"), "Rollback must ask before replacing"
    assert "Nothing was changed" in rollback


def test_the_update_check_never_installs():
    script = (RELEASE / "Install.ps1").read_text(encoding="ascii")
    check = script[script.index("if ($CheckUpdate)"):script.index("# Windows PowerShell's")]
    assert "Copy-Item" not in check and "Remove-Item" not in check
    assert "Nothing was installed" in check


def test_the_new_bat_files_run_the_one_script():
    assert "-Rollback" in (RELEASE / "Rollback.bat").read_text(encoding="ascii")
    assert "-CheckUpdate" in (RELEASE / "CheckForUpdate.bat").read_text(encoding="ascii")


def test_the_release_workflow_publishes_only_from_a_tag_matching_the_version():
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'tags: ["v*"]' in text and "--prerelease" in text
    publish = text[text.index("Publish the pre-release"):]
    assert "startsWith(github.ref, 'refs/tags/v')" in publish
    assert "build_plugin.VERSION" in text and "checksums.txt" in text
