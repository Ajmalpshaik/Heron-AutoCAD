"""Stand-in for pywin32's pywintypes, off Windows only (tests/winstubs/README.md)."""

from __future__ import annotations

from _any import anything


class error(Exception):  # noqa: N801 - pywin32's own name
    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self.winerror = args[0] if args else 0


class OVERLAPPED:
    hEvent = None


def __getattr__(name: str):
    return anything(name)
