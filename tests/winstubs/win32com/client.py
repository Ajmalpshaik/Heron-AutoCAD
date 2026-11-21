"""Stand-in for win32com.client, off Windows only (tests/winstubs/README.md).

There is no AutoCAD to dispatch: Dispatch and GetActiveObject fail the way a
PC without AutoCAD would.
"""

from __future__ import annotations

from typing import Any

from _any import anything


class VARIANT:
    """A typed COM value: keeps its type and value, as tests read them back."""

    def __init__(self, vt: int, value: Any) -> None:
        self.varianttype = vt
        self.value = value

    def __repr__(self) -> str:
        return f"VARIANT({self.varianttype}, {self.value!r})"


class CDispatch:
    pass


def Dispatch(*args: Any, **kwargs: Any) -> Any:  # noqa: N802 - pywin32's own name
    raise OSError("no COM on this machine")


def GetActiveObject(*args: Any, **kwargs: Any) -> Any:  # noqa: N802 - pywin32's own name
    raise OSError("no COM on this machine")


def __getattr__(name: str):
    return anything(name)
