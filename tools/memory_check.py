#!/usr/bin/env python3
"""Does AutoCAD's memory keep growing while Heron works? A live check.

Reads acad.exe's Private Bytes, makes N rounds of Heron's read-only calls on
the open drawing (status, layers, extents, drawing report), and reads it again
every 10 rounds. Pass: the last reading is within 10 % of the first, as the
ADN memory-leak skill measures it (docs/11-adn-repos-study.md, item 10). Fail:
it grows round after round - a leak to chase. Changes nothing in the drawing.

    .venv\\Scripts\\python.exe tools/memory_check.py
    .venv\\Scripts\\python.exe tools/memory_check.py --rounds 300

Needs AutoCAD with a drawing open, and Heron connected (reads need no padlock).
Working Set is not used: Windows trims it under pressure, so it hides leaks.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Within this share of the first reading counts as flat.
ALLOWED_GROWTH = 0.10
MB = 1024 * 1024


def verdict(samples: list[float], allowed: float = ALLOWED_GROWTH) -> tuple[bool, str]:
    """PASS or FAIL from Private Bytes readings in MB, first to last, and why."""
    if len(samples) < 2:
        return False, "Fewer than two readings: nothing to compare."
    first, last, peak = samples[0], samples[-1], max(samples)
    growth = (last - first) / first if first > 0 else 0.0
    rising = all(b >= a for a, b in zip(samples[1:], samples[2:], strict=False)) and len(samples) > 3
    text = f"first {first:.1f} MB, peak {peak:.1f} MB, last {last:.1f} MB ({growth:+.1%})"
    if growth <= allowed:
        return True, f"Flat: {text}."
    return False, f"Grows{' every reading' if rising else ''}: {text}. Run again with more rounds to size it."


def private_mb(pid: int) -> float:
    """acad.exe's Private Bytes (PagefileUsage / PrivateUsage) in MB."""

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    query_limited, vm_read = 0x1000, 0x0010
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(query_limited | vm_read, False, pid)
    if not handle:
        raise OSError(f"Cannot open AutoCAD's process {pid} (run as the same user as AutoCAD).")
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise OSError("Windows would not report AutoCAD's memory.")
        return counters.PrivateUsage / MB
    finally:
        kernel.CloseHandle(handle)


async def main(rounds: int) -> int:
    import win32process

    from autocad_mcp.core.connection import get_app, run
    from autocad_mcp.tools import document, drawing_report, layers, query

    pid = await run(lambda: win32process.GetWindowThreadProcessId(int(get_app().HWND))[1])
    calls = (
        lambda: document.autocad_status(),
        lambda: layers.autocad_list_layers(),
        lambda: query.autocad_get_extents(),
        lambda: drawing_report.autocad_drawing_report(count_objects=False),
    )
    samples = [private_mb(pid)]
    print(f"acad.exe {pid}: {samples[0]:.1f} MB before {rounds} rounds of {len(calls)} reads")
    for done in range(1, rounds + 1):
        for make in calls:
            answer = await make()
            if answer.startswith("Error"):
                print(answer)
                return 2
        if done % 10 == 0 or done == rounds:
            samples.append(private_mb(pid))
            print(f"  after {done:4d} rounds: {samples[-1]:.1f} MB")
    ok, why = verdict(samples)
    print(("PASS  " if ok else "FAIL  ") + why)
    print(json.dumps({"rounds": rounds, "samples_mb": [round(s, 1) for s in samples], "pass": ok}))
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=100, help="rounds of reads (default 100)")
    sys.exit(asyncio.run(main(max(1, parser.parse_args().rounds))))
