"""Stand-in for pywin32's pythoncom, off Windows only (tests/winstubs/README.md)."""

from __future__ import annotations

from _any import anything


class com_error(Exception):  # noqa: N801 - pywin32's own name
    """A COM failure: (hresult, text, excepinfo, argerror), as pywin32 gives it."""


VT_EMPTY, VT_I2, VT_I4, VT_R8, VT_BSTR, VT_DISPATCH, VT_BOOL, VT_VARIANT = 0, 2, 3, 5, 8, 9, 11, 12
VT_I1, VT_UI1, VT_ARRAY, VT_BYREF = 16, 17, 8192, 16384
COINIT_APARTMENTTHREADED, COINIT_MULTITHREADED = 2, 0
Empty = None
Missing = object()


def __getattr__(name: str):
    return anything(name)
