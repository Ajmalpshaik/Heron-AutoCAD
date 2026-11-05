"""Build Heron for AutoCAD and lay it out as HeronAutoCAD.bundle.

    python tools/build_plugin.py            build Release, write dist/HeronAutoCAD.bundle

AutoCAD loads a .bundle folder from its ApplicationPlugins folders by itself.
PackageContents.xml inside tells each AutoCAD which build is its own:

    R24.0-R24.3  AutoCAD 2021-2024  Contents/R24  (.NET Framework 4.8)
    R25.0-R25.1  AutoCAD 2025-2026  Contents/R25  (.NET 8)
    R26.0-R26.9  AutoCAD 2027       Contents/R26  (.NET 10)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parents[1]
SOLUTION = ROOT / "autocad" / "Heron.AutoCAD.sln"
ADDIN_BIN = ROOT / "autocad" / "Heron.AutoCAD.Addin" / "bin" / "Release"
DIST = ROOT / "dist"
BUNDLE = "HeronAutoCAD.bundle"
MODULE = "Heron.AutoCAD.Addin.dll"
VERSION = "1.4.0"

# (target framework, Contents folder, SeriesMin, SeriesMax, which AutoCADs)
SERIES = (
    ("net48", "R24", "R24.0", "R24.3", "AutoCAD 2021-2024"),
    ("net8.0-windows", "R25", "R25.0", "R25.1", "AutoCAD 2025-2026"),
    ("net10.0-windows", "R26", "R26.0", "R26.9", "AutoCAD 2027"),
)

# Fixed for the life of the product: AutoCAD uses them to tell an upgrade
# of Heron from a different application.
PRODUCT_CODE = "{6E1F3C2A-5B7D-4E8F-9A10-2C3D4E5F6A71}"
UPGRADE_CODE = "{9B2C4D6E-8F10-4A3B-8C5D-7E9F1A2B3C40}"


def package_contents() -> str:
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="AutoCAD" ProductType="Application"'
        f' Name="Heron AI for AutoCAD" AppVersion="{VERSION}" Author="Ajmal PS"'
        f' Description={quoteattr("Lets a chat work in your AutoCAD only when you connect it, behind padlocks you control.")}'
        f' ProductCode="{PRODUCT_CODE}" UpgradeCode="{UPGRADE_CODE}">',
        '  <CompanyDetails Name="Ajmal PS" />',
        '  <RuntimeRequirements OS="Win64" Platform="AutoCAD*" />',
    ]
    for _, folder, low, high, label in SERIES:
        parts += [
            f'  <Components Description="{label}">',
            f'    <RuntimeRequirements OS="Win64" Platform="AutoCAD*" SeriesMin="{low}" SeriesMax="{high}" />',
            f'    <ComponentEntry AppName="HeronAutoCAD" Version="{VERSION}" ModuleName="./Contents/{folder}/{MODULE}"'
            ' AppDescription="Heron AI for AutoCAD" LoadOnAutoCADStartup="True" />',
            "  </Components>",
        ]
    parts.append("</ApplicationPackage>")
    return "\n".join(parts) + "\n"


def make_bundle(built: dict[str, Path], out: Path) -> Path:
    """Copy each build into its Contents folder and write PackageContents.xml."""
    bundle = out / BUNDLE
    if bundle.exists():
        shutil.rmtree(bundle)
    for tfm, folder, *_ in SERIES:
        source = built[tfm]
        if not (source / MODULE).is_file():
            raise SystemExit(f"{MODULE} is missing for {tfm} in {source}. Build first.")
        shutil.copytree(source, bundle / "Contents" / folder)
    (bundle / "PackageContents.xml").write_text(package_contents(), encoding="utf-8")
    return bundle


def main() -> int:
    subprocess.run(["dotnet", "build", str(SOLUTION), "-c", "Release", "-nologo", "-v", "q"], check=True)
    bundle = make_bundle({tfm: ADDIN_BIN / tfm for tfm, *_ in SERIES}, DIST)
    print(f"Built {bundle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
