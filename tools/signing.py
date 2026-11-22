"""Code-signing for the release, only when a certificate is given (issue #72, D-99).

make_release.py and make_installer.py call this. With a certificate it signs Heron's own
files with Windows' signtool: the add-in DLLs (Heron.*.dll in every Contents folder of the
bundle), autocad-mcp.exe, Install.ps1, and the setup with its uninstaller. The DLLs
Microsoft ships beside them (System.*.dll) are signed by Microsoft already.

    HERON_SIGN_PFX        the certificate file (.pfx). release.yml writes it from the
                          repository secret HERON_SIGN_PFX_BASE64
    HERON_SIGN_PASSWORD   its password (repository secret HERON_SIGN_PFX_PASSWORD)
    HERON_SIGN_TIMESTAMP  optional: the time-stamp server (default DigiCert's), so a
                          signature stays good after the certificate expires
    HERON_SIGNTOOL        optional: signtool.exe, when it is not in the Windows SDK folder

Without HERON_SIGN_PFX nothing is signed and the build says so in one line. Ajmal decided on
2026-11-21 not to buy a certificate (#164), so releases are unsigned; this stays ready in case
that changes, and docs/SETUP.md "Code signing" says what one would need. Half a configuration (a file without its password, or a password without a
file) stops the build instead of quietly shipping unsigned files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import NamedTuple

TIMESTAMP = "http://timestamp.digicert.com"
DESCRIPTION = "Heron AI for AutoCAD"
INNO_NAME = "heron"  # the Sign Tool name make_installer.py gives ISCC (/Sheron=...)
NOT_SIGNED = (
    "Not signed: no code-signing certificate was given (HERON_SIGN_PFX). "
    "Heron is released unsigned by Ajmal's decision (#164): Windows SmartScreen may warn about "
    "the setup, and AutoCAD may ask once, the first time it loads Heron, whether to trust it."
)


_told: list[bool] = []


def say_not_signed() -> None:
    """The "Not signed" line, once per build however many times signing is skipped."""
    if not _told:
        _told.append(True)
        print(NOT_SIGNED)


class Certificate(NamedTuple):
    pfx: Path
    password: str
    timestamp: str


def certificate(env: Mapping[str, str] | None = None) -> Certificate | None:
    """The certificate the environment names, or None when it names none."""
    env = os.environ if env is None else env
    pfx = env.get("HERON_SIGN_PFX", "").strip()
    password = env.get("HERON_SIGN_PASSWORD", "")
    if not pfx and not password:
        return None
    if not pfx or not password:
        given, missing = ("HERON_SIGN_PFX", "HERON_SIGN_PASSWORD") if pfx else ("HERON_SIGN_PASSWORD", "HERON_SIGN_PFX")
        raise SystemExit(f"{given} is set but {missing} is not. Set both, or neither. Nothing was signed.")
    if not Path(pfx).is_file():
        raise SystemExit(f"HERON_SIGN_PFX names {pfx}, which is not a file. Nothing was signed.")
    if '"' in password or password.endswith("\\"):
        raise SystemExit(
            "The certificate password has a double quote in it or ends in a backslash, which signtool's"
            " command line cannot carry. Nothing was signed."
        )
    return Certificate(Path(pfx), password, env.get("HERON_SIGN_TIMESTAMP", "").strip() or TIMESTAMP)


def find_signtool(env: Mapping[str, str] | None = None) -> Path:
    """signtool.exe: HERON_SIGNTOOL, else on PATH, else the newest in the Windows 10/11 SDK."""
    env = os.environ if env is None else env
    named = env.get("HERON_SIGNTOOL", "").strip()
    if named:
        return Path(named)
    found = shutil.which("signtool")
    if found:
        return Path(found)
    kits = Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin"
    tools = sorted(kits.glob("10.*/x64/signtool.exe"), key=lambda p: [int(n) for n in p.parent.parent.name.split(".") if n.isdigit()])
    if not tools:
        raise SystemExit("No signtool.exe: install the Windows SDK, or set HERON_SIGNTOOL. Nothing was signed.")
    return tools[-1]


def sign_command(signtool: Path, cert: Certificate, files: Iterable[Path]) -> list[str]:
    return [
        str(signtool), "sign", "/f", str(cert.pfx), "/p", cert.password,
        "/fd", "sha256", "/tr", cert.timestamp, "/td", "sha256", "/d", DESCRIPTION,
        *(str(f) for f in files),
    ]  # fmt: skip


def sign(files: Iterable[Path], env: Mapping[str, str] | None = None, run: Callable = subprocess.run) -> bool:
    """Sign the files when a certificate is given. True when signed, False (and one line) when not."""
    files = list(files)
    cert = certificate(env)
    if cert is None:
        say_not_signed()
        return False
    if not files:
        raise SystemExit("Nothing to sign was found. The build did not make the files it should have.")
    done = run(sign_command(find_signtool(env), cert, files), capture_output=True, text=True, check=False)
    if done.returncode != 0:
        # signtool's own words, never the command: it holds the password.
        raise SystemExit(hide(f"signtool could not sign the files:\n{done.stdout}\n{done.stderr}", env))
    print(f"Signed {len(files)} file(s): " + ", ".join(Path(f).name for f in files))
    return True


def inno_sign_tool(env: Mapping[str, str] | None = None) -> str | None:
    """The command ISCC runs to sign the setup and its uninstaller ($f is the file), or None."""
    cert = certificate(env)
    if cert is None:
        return None

    def plain(text: object) -> str:
        return str(text).replace("$", "$$")  # ISCC reads $ as the start of $f, $q, $p

    return (
        f"$q{plain(find_signtool(env))}$q sign /f $q{plain(cert.pfx)}$q /p $q{plain(cert.password)}$q /fd sha256"
        f" /tr {plain(cert.timestamp)} /td sha256 /d $q{DESCRIPTION}$q $f"
    )


def hide(text: str, env: Mapping[str, str] | None = None) -> str:
    """Text with the certificate password, as typed and as ISCC is given it, replaced by ***."""
    cert = certificate(env)
    if cert is None:
        return text
    return text.replace(cert.password.replace("$", "$$"), "***").replace(cert.password, "***")
