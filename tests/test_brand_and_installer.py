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
WINDOWS = [
    "HeronBrand.cs", "HeronWindowStyle.cs", "HeronKeepQuestion.cs", "HeronActivityBanner.cs",
    "HeronStatusWindow.cs", "HeronSettingsWindow.cs", "HeronSwitchWindow.cs",
]
RGB = re.compile(r"FromRgb\(\s*0x(\w\w),\s*0x(\w\w),\s*0x(\w\w)\s*\)")


def test_window_colours_are_heron_brand_colours():
    found = []
    for name in WINDOWS:
        text = (ADDIN / name).read_text(encoding="utf-8")
        for match in RGB.finditer(text):
            found.append("".join(match.groups()).upper())
        assert "Colors." not in text and "Brushes.White" not in text, f"{name}: a WPF named colour, not a brand one"
    assert found, "no colours found: the pattern no longer matches HeronBrand.cs"
    assert set(found) <= BRAND, f"not in the Heron brand: {sorted(set(found) - BRAND)}"


def test_windows_put_manrope_first():
    ui = (ADDIN / "HeronBrand.cs").read_text(encoding="utf-8")
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


def test_ribbon_is_heron_and_settings_and_the_padlocks_live_in_settings():
    """D-44: the same layout as Heron for Revit."""
    ribbon = (ADDIN / "HeronRibbon.cs").read_text(encoding="utf-8")
    assert "HeronActions.ShowSettings" in ribbon
    assert "TogglePadlock" not in ribbon, "a padlock is back on the ribbon"
    window = (ADDIN / "HeronSettingsWindow.cs").read_text(encoding="utf-8")
    for padlock in ("Padlock.Changes", "Padlock.Admin", "Padlock.Publish", "Padlock.AskToKeep"):
        assert padlock in window
    assert "HeronActions.TogglePadlock" in window, "Settings must run the same toggle, with its question"
    commands = (ADDIN / "HeronCommands.cs").read_text(encoding="utf-8")
    assert '"HERONSETTINGS"' in commands
    assert (ADDIN / "Resources" / "Settings.png").is_file()


def test_refusals_send_the_modeller_to_settings():
    texts = (ROOT / "autocad" / "Heron.AutoCAD.Bridge" / "Texts.cs").read_text(encoding="utf-8")
    assert "padlock on the Heron tab" not in texts
    assert texts.count("press Settings on the Heron tab") == 3


def test_windows_are_drawn_like_heron_for_revit():
    """D-45: one shared window style, the switch question, Free this AutoCAD, hover texts."""
    for name in ("HeronSettingsWindow.cs", "HeronStatusWindow.cs", "HeronKeepQuestion.cs", "HeronSwitchWindow.cs"):
        assert "S.Build(" in (ADDIN / name).read_text(encoding="utf-8"), f"{name} is not in the Heron window style"
    actions = (ADDIN / "HeronActions.cs").read_text(encoding="utf-8")
    assert "HeronSwitchWindow.Ask(" in actions, "the switches must ask with the Heron question window"
    ribbon = (ADDIN / "HeronRibbon.cs").read_text(encoding="utf-8")
    assert "HeronActions.FreeHold" in ribbon and ribbon.count("ToolTip = tip") == 1
    # AutoCAD runs the top half of a split button only when it is synchronized with
    # its current item; with false the Heron button did nothing (live, 2026-11-08).
    assert "IsSynchronizedWithCurrentItem = true" in ribbon
    for name in ("ShowStatus", "FreeHold"):
        body = actions[actions.index("public static void " + name):]
        body = body[:body.index("\n        }\n")]
        assert "HeronRibbon.Repaint()" in body, f"{name} must put the heron back on top of the split button"
    banner = (ADDIN / "HeronActivityBanner.cs").read_text(encoding="utf-8")
    for part in ("_auraBrush", "_bloomLeft", "_sweep", "DropShadowEffect", "BackEase"):
        assert part in banner, f"the banner lost the status bar design's {part}"
