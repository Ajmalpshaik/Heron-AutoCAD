"""autocad_insert_block: a .dwg path with forward slashes must reach AutoCAD with backslashes.

Live check 2026-10-26: InsertBlock("C:/.../mechmetric.dwg") failed with "Key not
found"; the same file with backslashes inserted fine.
"""

from __future__ import annotations

import sys

import pytest

from autocad_mcp.tools.draw import dwg_path

needs_windows_paths = pytest.mark.skipif(sys.platform != "win32", reason="Windows path rules (backslashes, drive letters)")


@needs_windows_paths
def test_forward_slashes_become_backslashes(tmp_path):
    drawing = tmp_path / "plain.dwg"
    drawing.write_bytes(b"")
    given = str(drawing).replace("\\", "/")
    assert dwg_path(f'"{given}"') == str(drawing)
    assert "/" not in dwg_path(given)
