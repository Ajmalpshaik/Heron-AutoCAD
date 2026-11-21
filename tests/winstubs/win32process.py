"""Stand-in for pywin32's win32process, off Windows only (tests/winstubs/README.md)."""

from __future__ import annotations

from _any import anything


def __getattr__(name: str):
    return anything(name)
