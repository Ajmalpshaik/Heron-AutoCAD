"""Build the one-file setup a modeller double-clicks: dist/HeronAutoCAD-<version>-setup.exe

    python tools/make_installer.py

Issue #73, D-99. Run it on Windows after tools/make_release.py, which leaves the release
folder dist/HeronAutoCAD-<version>-win64/ beside the zip. It packs four things from that
folder with Inno Setup's compiler, ISCC.exe, using tools/installer/HeronAutoCAD.iss:

    HeronAutoCAD.bundle   the plug-in, for every AutoCAD build
    autocad-mcp.exe       the server
    Install.ps1           run by the setup as -Connect and by its uninstaller as -Disconnect
    CheckForUpdate.bat    behind the Start menu's "Check for a newer Heron"

It then writes dist/checksums.txt again, with the zip and the setup in it. The versions are
read from autocad/Directory.Build.props (the plug-in, and the setup's own version) and
src/autocad_mcp/__init__.py (the server); nothing is typed into the script by hand.

ISCC.exe: HERON_ISCC names it (release.yml fetches Inno Setup 6.7.3 and checks it), or an
Inno Setup 6 installed on this PC is found. With a code-signing certificate named in the
environment (tools/signing.py) the setup and its uninstaller are signed too.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import build_plugin  # noqa: E402
import make_release  # noqa: E402
import signing  # noqa: E402

ROOT = TOOLS.parent
SCRIPT = TOOLS / "installer" / "HeronAutoCAD.iss"
SERVER_INIT = ROOT / "src" / "autocad_mcp" / "__init__.py"
SERVER = "autocad-mcp.exe"
# What the setup takes from the release folder: each [Files] Source line of the script.
PACKED = (build_plugin.BUNDLE, SERVER, "Install.ps1", "CheckForUpdate.bat")


def server_version() -> str:
    """The server's version, from the one place that owns it."""
    found = re.search(r'^__version__\s*=\s*"([^"]+)"', SERVER_INIT.read_text(encoding="utf-8"), re.M)
    if not found:
        raise SystemExit(f"No __version__ in {SERVER_INIT}")
    return found.group(1)


def release_folder() -> Path:
    return build_plugin.DIST / f"HeronAutoCAD-{build_plugin.VERSION}-win64"


def setup_name() -> str:
    return f"HeronAutoCAD-{build_plugin.VERSION}-setup"


def missing(folder: Path) -> list[str]:
    """What the setup needs that the release folder does not have, in plain words."""
    problems = [f"{name} is not in {folder}" for name in PACKED if not (folder / name).exists()]
    bundle = folder / build_plugin.BUNDLE
    if bundle.is_dir():
        if not (bundle / "PackageContents.xml").is_file():
            problems.append(f"{bundle} has no PackageContents.xml")
        for _, contents, *_rest, label in build_plugin.SERIES:
            if not (bundle / "Contents" / contents / build_plugin.MODULE).is_file():
                problems.append(f"{bundle} has no Contents/{contents}/{build_plugin.MODULE} ({label})")
    return problems


def defines(folder: Path, out: Path, sign_tool: bool = False) -> dict[str, str]:
    """The values ISCC is given with /D: the script uses these, never typed-in versions."""
    values = {
        "AppVersion": build_plugin.VERSION,
        "ServerVersion": server_version(),
        "ReleaseDir": str(folder),
        "OutputDir": str(out),
        "SetupName": setup_name(),
    }
    if sign_tool:
        values["SignTool"] = signing.INNO_NAME
    return values


def iscc_command(iscc: Path, folder: Path, out: Path, sign_command: str | None = None) -> list[str]:
    command = [str(iscc), "/Q"]
    command += [f"/D{key}={value}" for key, value in defines(folder, out, sign_command is not None).items()]
    if sign_command is not None:
        command.append(f"/S{signing.INNO_NAME}={sign_command}")
    return [*command, str(SCRIPT)]


def find_iscc(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    named = env.get("HERON_ISCC", "").strip()
    if named:
        if not Path(named).is_file():
            raise SystemExit(f"HERON_ISCC names {named}, which is not a file.")
        return Path(named)
    found = shutil.which("ISCC")
    if found:
        return Path(found)
    for base in (env.get("ProgramFiles(x86)", ""), env.get("ProgramFiles", ""), str(Path(env.get("LOCALAPPDATA", "")) / "Programs")):
        candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
        if base and candidate.is_file():
            return candidate
    raise SystemExit("No Inno Setup compiler (ISCC.exe). Install Inno Setup 6 from jrsoftware.org, or set HERON_ISCC to its ISCC.exe.")


def main() -> int:
    folder = release_folder()
    problems = missing(folder)
    if problems:
        print("\n".join(problems))
        raise SystemExit("Run python tools/make_release.py first: the setup is made from its release folder.")
    sign_command = signing.inno_sign_tool()
    if sign_command is None:
        signing.say_not_signed()
    out = build_plugin.DIST
    done = subprocess.run(iscc_command(find_iscc(), folder, out, sign_command), capture_output=True, text=True, check=False)
    if done.returncode != 0:
        report = f"{done.stdout}\n{done.stderr}"
        cert = signing.certificate()
        if cert is not None:
            report = report.replace(cert.password, "***")
        raise SystemExit(f"Inno Setup could not build the setup (exit {done.returncode}):\n{report}")
    setup = out / f"{setup_name()}.exe"
    if not setup.is_file():
        raise SystemExit(f"Inno Setup said it finished, but {setup} is not there.")
    archive = build_plugin.DIST / f"{folder.name}.zip"
    sums = make_release.write_checksums(archive, setup) if archive.is_file() else make_release.write_checksums(setup)
    print(f"Setup: {setup}")
    print(f"Checksums: {sums}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
