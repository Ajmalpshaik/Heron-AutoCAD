"""Is Heron set up right on this PC? One report, no AutoCAD needed.

The most common support question after an update is "why does it not work":
the plug-in not installed, AutoCAD still running the old plug-in, the chat
still running the old server, or nobody pressed Heron. Each of those is a
file this module can look at without touching AutoCAD or a drawing, so the
report answers even when AutoCAD is closed (the idea is Heron AI for Revit's
heron_diagnose / heron_health).

Every check is PASS, WARN or FAIL, with what to do in plain words. The
health is the worst of them: HEALTHY, WARNING or FAILED.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from .. import __version__
from .bridge import PROTOCOL_VERSION, _alive, bridges_dir

# When this server's code was loaded. A .py file newer than this means the
# files were updated under a running server: the chat is on the old code.
LOADED_AT = time.time()
_PACKAGE = Path(__file__).resolve().parents[1]
_SLACK = 2.0  # seconds: a file written while the server started is not "newer"

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _check(name: str, state: str, detail: str) -> dict[str, str]:
    return {"check": name, "state": state, "detail": detail}


def changed_since_start(package: Path = _PACKAGE, loaded_at: float | None = None) -> list[str]:
    """The server's own .py files changed after it loaded. Empty for a frozen exe."""
    if getattr(sys, "frozen", False):
        return []
    since = (LOADED_AT if loaded_at is None else loaded_at) + _SLACK
    newer = []
    for path in package.rglob("*.py"):
        try:
            if path.stat().st_mtime > since:
                newer.append(str(path.relative_to(package)))
        except OSError:
            continue
    return sorted(newer)


def plugins_dir() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Autodesk" / "ApplicationPlugins"


def installed_plugin(folder: Path | None = None) -> str | None:
    """The version of the plug-in AutoCAD will load next time it starts, or None."""
    contents = (folder or plugins_dir()) / "HeronAutoCAD.bundle" / "PackageContents.xml"
    try:
        text = contents.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    found = re.search(r'AppVersion="([^"]+)"', text)
    return found.group(1) if found else "unknown"


def connected_autocads(folder: Path | None = None) -> list[dict[str, Any]]:
    """Each AutoCAD whose Heron button is pressed: process, versions, since when."""
    found = []
    for path in sorted((folder or bridges_dir()).glob("*.json")):
        try:
            address = json.loads(path.read_text(encoding="utf-8-sig"))
            pid = int(address.get("pid") or path.stem)
        except (OSError, ValueError):
            continue
        if not _alive(pid):
            continue
        found.append(
            {
                "pid": pid,
                "acad_version": address.get("acadVersion", ""),
                "plugin_version": address.get("addinVersion", ""),
                "protocol_version": address.get("protocolVersion"),
                "connected_since": address.get("startedAt", ""),
            }
        )
    return found


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text)[:3])


def report(
    *,
    plugins: Path | None = None,
    bridges: Path | None = None,
    package: Path = _PACKAGE,
    loaded_at: float | None = None,
) -> dict[str, Any]:
    checks = []

    newer = changed_since_start(package, loaded_at)
    if newer:
        checks.append(_check(
            "server up to date", WARN,
            f"{len(newer)} of Heron's server files changed after this chat started it (e.g. {newer[0]}). "
            "This chat still runs the old code: close and reopen the chat (or restart Claude) to load the update.",
        ))  # fmt: skip
    else:
        checks.append(_check("server up to date", PASS, f"Heron server {__version__}, as loaded."))

    installed = installed_plugin(plugins)
    if installed is None:
        checks.append(_check(
            "plug-in installed", FAIL,
            f"No HeronAutoCAD.bundle in {plugins or plugins_dir()}. Run Install.bat from the Heron "
            "release (AutoCAD closed), then start AutoCAD.",
        ))  # fmt: skip
    else:
        checks.append(_check("plug-in installed", PASS, f"Plug-in {installed} is installed for AutoCAD to load."))

    running = connected_autocads(bridges)
    if not running:
        checks.append(_check(
            "AutoCAD connected", WARN,
            "No AutoCAD is connected to Heron. Start AutoCAD and press the Heron button on the Heron tab "
            "(or type HERON).",
        ))  # fmt: skip
    for acad in running:
        name = f"AutoCAD {acad['acad_version'] or '?'} (process {acad['pid']})"
        checks.append(_check("AutoCAD connected", PASS, f"{name} is connected, plug-in {acad['plugin_version'] or '?'}."))
        if acad["protocol_version"] not in (None, PROTOCOL_VERSION):
            checks.append(_check(
                "server and plug-in match", FAIL,
                f"{name} speaks bridge protocol {acad['protocol_version']}; this server speaks "
                f"{PROTOCOL_VERSION}. Install the server and the plug-in from the same release.",
            ))  # fmt: skip
        if installed and acad["plugin_version"] and _version(installed) > _version(acad["plugin_version"]):
            checks.append(_check(
                "AutoCAD runs the installed plug-in", WARN,
                f"{name} still runs plug-in {acad['plugin_version']}; {installed} is installed. "
                "Close and restart AutoCAD to load it.",
            ))  # fmt: skip

    # D-59: the padlocks live in each AutoCAD's memory, not in a file. The old
    # padlock lines in heron-autocad.config are ignored, so they are not read here.
    checks.append(_check(
        "padlocks", PASS,
        "The padlocks live inside each AutoCAD, not in a file: Changes, Publish and Admin are off "
        "every time AutoCAD starts. Turn one on in Settings on the Heron tab.",
    ))  # fmt: skip

    states = {check["state"] for check in checks}
    health = "FAILED" if FAIL in states else ("WARNING" if WARN in states else "HEALTHY")
    return {
        "health": health,
        "server_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
        "plugin_installed": installed,
        "autocads_connected": running,
        "checks": checks,
        "to_fix": [check["detail"] for check in checks if check["state"] != PASS],
    }
