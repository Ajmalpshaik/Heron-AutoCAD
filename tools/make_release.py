"""Build a ready-to-share release folder and zip: dist/HeronAutoCAD-<version>-win64.zip

    python tools/make_release.py

It also writes dist/checksums.txt (the zip's SHA-256). The zip holds the plug-in bundle, the server as one autocad-mcp.exe (no Python needed on the
target PC), Install.bat, a short READ-ME-FIRST.txt and capabilities.json (the tool list a registry reads, D-122). Run it from a venv that has the project
and PyInstaller installed:

    pip install . pyinstaller

The folder the zip is made from stays in dist/; tools/make_installer.py packs the same files
into the one-file setup. With a code-signing certificate named in the environment
(tools/signing.py) Heron's DLLs, autocad-mcp.exe and Install.ps1 are signed before they are
packed; without one the build says "Not signed" and goes on.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_plugin  # noqa: E402
import export_capabilities  # noqa: E402
import signing  # noqa: E402

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


def own_dlls(bundle: Path) -> list[Path]:
    """Heron's own DLLs in every Contents folder; Microsoft's System.*.dll are signed by Microsoft."""
    return sorted((bundle / "Contents").glob("*/Heron.*.dll"))


def main() -> int:
    build_plugin.main()
    signing.sign(own_dlls(build_plugin.DIST / build_plugin.BUNDLE))
    name = f"HeronAutoCAD-{build_plugin.VERSION}-win64"
    with tempfile.TemporaryDirectory(prefix="hrel") as tmp:
        exe = build_server_exe(Path(tmp))
        signing.sign([exe])
        folder = build_plugin.DIST / name
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        shutil.copytree(build_plugin.DIST / build_plugin.BUNDLE, folder / build_plugin.BUNDLE)
        shutil.copy2(exe, folder / "autocad-mcp.exe")
        for f in FILES.iterdir():
            shutil.copy2(f, folder / f.name)
        add_capabilities(folder)
        check_no_debug_files(folder)
        signing.sign([folder / "Install.ps1"])
    archive = shutil.make_archive(str(build_plugin.DIST / name), "zip", build_plugin.DIST, name)
    sums = write_checksums(Path(archive))
    print(f"Release: {archive}")
    print(f"Checksums: {sums}")
    return 0


def check_no_debug_files(folder: Path) -> None:
    """The release ships no .pdb debug file (#232): stop the build if one got in."""
    found = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.suffix.lower() == ".pdb")
    if found:
        raise SystemExit("The release must carry no .pdb debug files, but has: " + ", ".join(found))


def add_capabilities(folder: Path) -> Path:
    """capabilities.json in the release: every tool, its padlock and its proof, for a registry such as Heron AI's (D-122)."""
    return export_capabilities.write(folder / "capabilities.json")


def write_checksums(archive: Path, *more: Path) -> Path:
    """dist/checksums.txt: each download's SHA-256 (the zip, then the setup), so anyone can check it is the one built."""
    import hashlib

    lines = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}\n" for f in (archive, *more)]
    sums = archive.parent / "checksums.txt"
    # LF, not Windows line endings, so `sha256sum -c` works on Linux and macOS too (#232).
    with sums.open("w", encoding="ascii", newline="\n") as out:
        out.write("".join(lines))
    return sums


if __name__ == "__main__":
    sys.exit(main())
