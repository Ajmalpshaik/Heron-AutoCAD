"""Build a ready-to-share release folder and zip: dist/HeronAutoCAD-<version>-win64.zip

    python tools/make_release.py

The zip holds the plug-in bundle, the server as one autocad-mcp.exe (no Python needed on the
target PC), Install.bat and a short READ-ME-FIRST.txt. Run it from a venv that has the project
and PyInstaller installed:

    pip install . pyinstaller
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_plugin  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FILES = Path(__file__).resolve().parent / "release_files"
LAUNCHER = "from autocad_mcp.server import main\nmain()\n"


def build_server_exe(work: Path) -> Path:
    launcher = work / "launch.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm",
            "--name", "autocad-mcp",
            "--distpath", str(work / "exe"), "--workpath", str(work / "w"), "--specpath", str(work / "w"),
            "--exclude-module", "mcp.cli",
            "--hidden-import", "win32com.client", "--hidden-import", "pythoncom",
            "--hidden-import", "pywintypes",
            str(launcher),
        ],
        check=True,
    )
    return work / "exe" / "autocad-mcp.exe"


def main() -> int:
    build_plugin.main()
    name = f"HeronAutoCAD-{build_plugin.VERSION}-win64"
    with tempfile.TemporaryDirectory(prefix="hrel") as tmp:
        exe = build_server_exe(Path(tmp))
        folder = build_plugin.DIST / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        shutil.copytree(build_plugin.DIST / build_plugin.BUNDLE, folder / build_plugin.BUNDLE)
        shutil.copy2(exe, folder / "autocad-mcp.exe")
        for f in FILES.iterdir():
            shutil.copy2(f, folder / f.name)
    archive = shutil.make_archive(str(build_plugin.DIST / name), "zip", build_plugin.DIST, name)
    print(f"Release: {archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
