"""What every stand-in module answers for a name it does not define: a constant 0 or a no-op."""

from __future__ import annotations

from typing import Any


def anything(name: str) -> Any:
    if name.startswith("__"):
        raise AttributeError(name)
    if name.isupper():
        return 0

    def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    return nothing
