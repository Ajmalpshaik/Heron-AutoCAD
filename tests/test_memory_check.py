"""tools/memory_check.py's verdict: flat passes, growth fails (no AutoCAD)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
memory_check = importlib.import_module("memory_check")


def test_flat_memory_passes():
    ok, why = memory_check.verdict([800.0, 815.0, 812.0, 820.0])
    assert ok and why.startswith("Flat")


def test_a_spike_that_comes_back_passes():
    assert memory_check.verdict([800.0, 1100.0, 830.0])[0]


def test_growth_past_ten_percent_fails_and_says_so():
    ok, why = memory_check.verdict([800.0, 850.0, 900.0, 950.0])
    assert not ok and "every reading" in why and "+18.8%" in why


def test_one_reading_is_not_a_result():
    assert not memory_check.verdict([800.0])[0]
