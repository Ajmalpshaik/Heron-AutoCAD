"""Install or remove Heron for AutoCAD for the current Windows user.

    python tools/install_plugin.py              copy dist/HeronAutoCAD.bundle into AutoCAD's plug-in folder
    python tools/install_plugin.py --uninstall  remove it

The folder is %APPDATA%\\Autodesk\\ApplicationPlugins, which AutoCAD already
trusts, so no AutoCAD security setting is changed. AutoCAD must be closed:
it locks the add-in's DLL while it runs, and it only looks for new plug-ins
when it starts.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_BUNDLE = ROOT / "dist" / "HeronAutoCAD.bundle"


def plugins_dir() -> Path:
    """%APPDATA%\\Autodesk\\ApplicationPlugins; ~/AppData/Roaming when %APPDATA% is unset or relative (#134)."""
    value = os.environ.get("APPDATA", "").strip()
    root = Path(value) if value and Path(value).is_absolute() else Path.home() / "AppData" / "Roaming"
    return root / "Autodesk" / "ApplicationPlugins"


def autocad_running() -> bool:
    found = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq acad.exe", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "acad.exe" in found.stdout.lower()


def _refuse_while_running() -> None:
    if autocad_running():
        raise SystemExit("AutoCAD is running. Close AutoCAD, then run this again. Nothing was changed.")


def install(bundle: Path, target_dir: Path) -> Path:
    _refuse_while_running()
    if not (bundle / "PackageContents.xml").is_file():
        raise SystemExit(f"No bundle at {bundle}. Run python tools/build_plugin.py first.")
    target = target_dir / bundle.name
    if target.exists():
        shutil.rmtree(target)
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle, target)
    return target


def uninstall(target_dir: Path) -> None:
    _refuse_while_running()
    target = target_dir / "HeronAutoCAD.bundle"
    if target.exists():
        shutil.rmtree(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Heron for AutoCAD for this Windows user.")
    parser.add_argument("--uninstall", action="store_true", help="Remove Heron for AutoCAD.")
    args = parser.parse_args()
    if args.uninstall:
        uninstall(plugins_dir())
        print("Heron for AutoCAD removed. It is gone the next time AutoCAD starts.")
    else:
        target = install(DIST_BUNDLE, plugins_dir())
        print(f"Installed to {target}.")
        print("Start AutoCAD: the Heron tab appears on the ribbon. Press Heron to connect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
