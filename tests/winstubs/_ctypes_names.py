"""Off Windows only: the ctypes names core/message_filter.py needs at import (tests/winstubs/README.md).

It only adds names ctypes lacks off Windows; it calls nothing. tests/conftest.py
imports it for the test run; sitecustomize.py, for a script a test starts.
"""

from __future__ import annotations

import ctypes

for _name, _value in (("WINFUNCTYPE", ctypes.CFUNCTYPE), ("HRESULT", ctypes.c_long), ("WinDLL", ctypes.CDLL)):
    if not hasattr(ctypes, _name):
        setattr(ctypes, _name, _value)
