"""Diagnose Heron and autocad_show (no AutoCAD).

autocad://diagnose answers "why does it not work" from files alone: the
plug-in bundle, the address files the Heron button writes, the padlock file,
and the server's own code against what is on disk. autocad_show hands the
handles to the plug-in, which selects and zooms (only the connection needed).
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

from autocad_mcp.core import diagnose, gate
from autocad_mcp.core.risk import Risk, risk_of
from autocad_mcp.tools import _shared, document


@pytest.fixture
def pc(tmp_path, monkeypatch):
    plugins = tmp_path / "ApplicationPlugins"
    bridges = tmp_path / "bridges"
    config = tmp_path / "heron-autocad.config"  # where an older plug-in kept the padlocks
    package = tmp_path / "package"
    package.mkdir()
    (package / "server.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(diagnose, "_alive", lambda pid: pid == os.getpid())

    def run(**overrides):
        args = {"plugins": plugins, "bridges": bridges, "package": package,
                "loaded_at": time.time() + 60}  # fmt: skip
        args.update(overrides)
        return diagnose.report(**args)

    def install(version="1.4.2"):
        bundle = plugins / "HeronAutoCAD.bundle"
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "PackageContents.xml").write_text(f'<ApplicationPackage AppVersion="{version}" />', encoding="utf-8")

    def connect(pid=None, plugin="1.4.2", protocol=1):
        bridges.mkdir(exist_ok=True)
        pid = pid or os.getpid()
        (bridges / f"{pid}.json").write_text(
            json.dumps({"pid": pid, "acadVersion": "25.1", "addinVersion": plugin, "protocolVersion": protocol,
                        "token": "secret", "startedAt": "2026-11-15T08:00:00Z"}),
            encoding="utf-8",
        )  # fmt: skip

    run.install, run.connect, run.config, run.package = install, connect, config, package
    return run


def _states(report):
    return {check["check"]: check["state"] for check in report["checks"]}


def test_nothing_installed_is_failed_and_says_what_to_do(pc):
    report = pc()
    assert report["health"] == "FAILED"
    assert _states(report)["plug-in installed"] == "FAIL"
    assert any("Install.bat" in step for step in report["to_fix"])


def test_installed_and_connected_is_healthy(pc):
    pc.install()
    pc.connect()
    report = pc()
    assert report["health"] == "HEALTHY", report["to_fix"]
    assert report["autocads_connected"][0]["plugin_version"] == "1.4.2"
    assert "secret" not in json.dumps(report)  # the session token never leaves the file


def test_installed_but_not_connected_says_press_heron(pc):
    pc.install()
    report = pc()
    assert report["health"] == "WARNING"
    assert any("press the Heron button" in step for step in report["to_fix"])


def test_a_closed_autocads_left_over_file_is_not_counted(pc):
    pc.install()
    pc.connect(pid=999_999)
    assert pc()["autocads_connected"] == []


def test_autocad_still_running_the_old_plug_in_says_restart_autocad(pc):
    pc.install("1.5.0")
    pc.connect(plugin="1.4.2")
    report = pc()
    assert _states(report)["AutoCAD runs the installed plug-in"] == "WARN"
    assert any("restart AutoCAD" in step for step in report["to_fix"])


def test_a_protocol_mismatch_fails(pc):
    pc.install()
    pc.connect(protocol=2)
    assert pc()["health"] == "FAILED"


def test_files_newer_than_the_running_server_say_reopen_the_chat(pc):
    pc.install()
    pc.connect()
    report = pc(loaded_at=time.time() - 60)
    assert _states(report)["server up to date"] == "WARN"
    assert any("reopen the chat" in step for step in report["to_fix"])


def test_a_padlock_file_is_not_taken_for_the_padlocks(pc):
    # D-59: the padlocks live in AutoCAD's memory. A file saying "on" is not believed.
    pc.install()
    pc.config.write_text(json.dumps({"write.enabled": True, "admin.enabled": True}), encoding="utf-8")
    report = pc()
    assert "padlocks" not in report
    detail = next(check["detail"] for check in report["checks"] if check["check"] == "padlocks")
    assert "inside each AutoCAD" in detail and "On:" not in detail


# ---------------------------------------------------------------------------
# autocad_show
# ---------------------------------------------------------------------------


@pytest.fixture
def plugin(monkeypatch):
    asked = []

    def runner(operation, args):
        asked.append((operation, args))
        return {"shown": len(args.get("handles", [])), "isolated": args.get("isolate", False), "not_found": []}

    monkeypatch.setattr(_shared, "plugin_runner", lambda: runner)
    monkeypatch.setattr(document, "in_plugin", _shared.in_plugin)

    async def direct(fn):
        return fn()

    monkeypatch.setattr(document, "run", direct)
    return asked


def test_show_needs_only_the_connection():
    assert risk_of("autocad_show") is Risk.VIEW
    assert gate.Risk.VIEW is Risk.VIEW


def test_show_hands_the_handles_to_the_plug_in(plugin):
    result = json.loads(asyncio.run(document.autocad_show(handles=["2A", "2B"], isolate=True)))
    assert plugin == [("show", {"handles": ["2A", "2B"], "isolate": True})]
    assert result == {"shown": 2, "isolated": True, "not_found": []}


def test_end_isolation_needs_no_handles(plugin):
    asyncio.run(document.autocad_show(end_isolation=True))
    assert plugin == [("show", {"end_isolation": True})]


def test_show_without_handles_says_what_to_give(plugin):
    result = asyncio.run(document.autocad_show())
    assert result.startswith("Error: Give the handles to show")
    assert plugin == []
