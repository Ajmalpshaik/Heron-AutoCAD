"""Where Heron keeps its files on this PC, never a folder relative to the server.

Windows always sets %LOCALAPPDATA% and %APPDATA%. Off Windows (a cloud runner,
CI), or with one unset, empty or not a full path, the folder is the one Windows
normally points it at under the user's home. A bare ``Path("")`` there would
put Heron's files in whatever folder the server happened to start in
(issues #43, #134).
"""

from __future__ import annotations

import os
from pathlib import Path


def _from(variable: str, *fallback: str) -> Path:
    value = os.environ.get(variable, "").strip()
    if value and Path(value).is_absolute():
        return Path(value)
    return Path.home().joinpath(*fallback)


def local_app_data() -> Path:
    """%LOCALAPPDATA%, else ~/AppData/Local."""
    return _from("LOCALAPPDATA", "AppData", "Local")


def roaming_app_data() -> Path:
    """%APPDATA%, else ~/AppData/Roaming."""
    return _from("APPDATA", "AppData", "Roaming")


def heron_local() -> Path:
    """Heron's own folder for this user: %LOCALAPPDATA%\\Heron\\autocad."""
    return local_app_data() / "Heron" / "autocad"
