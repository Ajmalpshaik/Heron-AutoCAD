"""The Heron windows stay in the brand colours, and the release has a Remove button that asks first."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDIN = ROOT / "autocad" / "Heron.AutoCAD.Addin"
RELEASE = ROOT / "tools" / "release_files"

# The palette of Heron AI docs/brand/README.md (Ink, Mist, Accent, Accent Light, Surface,
# Success, Warning, Error, White, Shadow). A shade is one of these at an opacity.
BRAND = {
    "0F0F10", "F7F5F2", "FD641A", "FF9A5C", "1B1B1F",
    "3ECF8E", "F5A524", "FF5A4E", "FFFFFF", "000000",
}
WINDOWS = ["HeronUi.cs", "HeronKeepQuestion.cs", "HeronActivityBanner.cs", "HeronStatusWindow.cs"]
RGB = re.compile(r"FromRgb\(\s*0x(\w\w),\s*0x(\w\w),\s*0x(\w\w)\s*\)")


def test_window_colours_are_heron_brand_colours():
    found = []
    for name in WINDOWS:
        text = (ADDIN / name).read_text(encoding="utf-8")
        for match in RGB.finditer(text):
            found.append("".join(match.groups()).upper())
        assert "Colors." not in text and "Brushes.White" not in text, f"{name}: a WPF named colour, not a brand one"
    assert found, "no colours found: the pattern no longer matches HeronUi.cs"
    assert set(found) <= BRAND, f"not in the Heron brand: {sorted(set(found) - BRAND)}"


def test_windows_put_manrope_first():
    ui = (ADDIN / "HeronUi.cs").read_text(encoding="utf-8")
    assert 'FontList = "Manrope, Segoe UI"' in ui
    for name in WINDOWS:
        assert 'FontFamily("Segoe UI")' not in (ADDIN / name).read_text(encoding="utf-8"), name


def test_uninstall_bat_sits_beside_install_bat_and_asks_first():
    bat = (RELEASE / "Uninstall.bat").read_text(encoding="ascii")
    assert "Install.ps1" in bat and "-Uninstall" in bat
    script = (RELEASE / "Install.ps1").read_text(encoding="ascii")
    uninstall = script[script.index("if ($Uninstall)"):script.index("$bundle = Join-Path")]
    assert uninstall.index("Read-Host") < uninstall.index("Remove-Item"), "Uninstall must ask before removing"
    assert "Nothing was removed" in uninstall


def test_release_scripts_use_windows_line_endings():
    for path in RELEASE.iterdir():
        data = path.read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n"), f"{path.name}: needs CRLF line endings"
