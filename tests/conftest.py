"""Shared test settings.

The Heron bridge is switched off for every test unless a test turns it back
on: the offline suites exercise tools against fake COM objects and have no
plug-in to ask. tests/test_gate.py turns it on with a fake bridge.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

# pywin32 installs only on Windows. Off Windows, stand-ins let the offline
# suite collect and run (tests/winstubs/README.md, issue #102); on Windows
# they are never used.
WINSTUBS = Path(__file__).resolve().parent / "winstubs"
if importlib.util.find_spec("pythoncom") is None:
    sys.path.insert(0, str(WINSTUBS))
    importlib.import_module("_ctypes_names")  # the ctypes names message_filter.py needs


def script_env() -> dict[str, str]:
    """The environment for a script a test starts: the stand-ins too, where pywin32 is missing."""
    env = dict(os.environ)
    if str(WINSTUBS) in sys.path:
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(WINSTUBS), env.get("PYTHONPATH", "")]))
    return env


@pytest.fixture(autouse=True)
def _bridge_off_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("HERON_AUTOCAD_BRIDGE", "off")
    # Keep audit lines and address files out of the real user profile.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    # And the plug-in folder (%APPDATA%) away from the real profile too (#134).
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    # Never let an offline test reach a real AutoCAD that happens to be open:
    # the gate's own look at AutoCAD reports "none" (tests/test_gate.py fakes it).
    from autocad_mcp.core import gate
    from autocad_mcp.core.errors import AutocadError

    async def no_autocad():
        raise AutocadError("offline test: no AutoCAD")

    monkeypatch.setattr(gate, "_probe", no_autocad)
