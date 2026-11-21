"""Reading a DXF or DWG file on disk, with AutoCAD closed (#71, D-92).

Read only: the file itself is never written. A DXF is read with ezdxf. A DWG
(and a .dws standards file or a .dwt template, which are DWGs under another
name) is Autodesk's closed format: Heron copies it to a temporary folder and
converts the copy to DXF with the ODA File Converter, when that free program
is installed on this PC. Heron finds it; it never downloads it. Without it the
answer says plainly that a DWG needs AutoCAD or the ODA converter.

What is read is what was last saved: changes not yet saved in AutoCAD are not
in the file, and the answers say so.

Everything returns plain data, so autocad_read_file and the standards check
(tools/standards.py) share it, and the tests make small DXF files with ezdxf
itself. No COM here.
"""

from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.errors import AutocadError
from .units import unit_name

DXF_KINDS = (".dxf",)
DWG_KINDS = (".dwg", ".dws", ".dwt")
MAX_MB = 250  # ezdxf holds the whole file in memory, about ten times its size
CONVERT_SECONDS = 180
ODA_ENV = "HERON_ODA_CONVERTER"
ODA_EXE = "ODAFileConverter.exe"
ODA_VERSION = "ACAD2018"  # the DXF the converter writes: read by every ezdxf
SAVED_ONLY = (
    "This is what the file on disk holds, as it was last saved. Changes not yet saved in "
    "AutoCAD are not in it."
)
# Layers, styles and linetypes every drawing has: never "not in the standard".
ALWAYS_THERE = {
    "layers": {"0", "defpoints"},
    "text_styles": {"standard", "annotative"},
    "dim_styles": {"standard", "annotative"},
    "linetypes": {"bylayer", "byblock", "continuous"},
}


@dataclass
class Opened:
    """A file read into memory: the ezdxf drawing, and how it was read."""

    doc: Any
    file: Path
    read_by: str
    recovered: int = 0  # problems ezdxf's recover mode put right while reading


# ---- finding and running the ODA File Converter -----------------------------


def _version_key(folder_name: str) -> tuple[int, ...]:
    """'ODAFileConverter 25.12.0' -> (25, 12, 0); no number sorts first."""
    return tuple(int(n) for n in re.findall(r"\d+", folder_name)) or (0,)


def _program_folders() -> list[Path]:
    found: list[Path] = []
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable, "").strip()
        if value and Path(value).is_absolute() and Path(value) not in found:
            found.append(Path(value))
    return found


def find_oda_converter() -> Path | None:
    """The ODA File Converter on this PC, or None. Never downloads anything.

    HERON_ODA_CONVERTER, when set, names it and nothing else is looked at.
    Else the newest ODA\\ODAFileConverter*\\ODAFileConverter.exe under Program
    Files (its installer puts the version in the folder name), else one on PATH.
    """
    named = os.environ.get(ODA_ENV, "").strip().strip('"')
    if named:
        path = Path(os.path.expandvars(named))
        return path if path.is_file() else None
    found = [
        exe
        for base in _program_folders()
        if (base / "ODA").is_dir()
        for exe in (base / "ODA").glob(f"ODAFileConverter*/{ODA_EXE}")
        if exe.is_file()
    ]
    if found:
        return max(found, key=lambda exe: _version_key(exe.parent.name))
    on_path = shutil.which("ODAFileConverter")
    return Path(on_path) if on_path else None


def no_dwg_reader(path: Path) -> str:
    """Why a DWG cannot be read here, and the three ways round it, in plain words."""
    named = os.environ.get(ODA_ENV, "").strip()
    where = (
        f"{ODA_ENV} names {named}, and there is no program there"
        if named
        else "it is not under Program Files\\ODA or on PATH"
    )
    return (
        f"Heron cannot read {path.name} with AutoCAD closed: a DWG is Autodesk's closed format, and "
        f"the free ODA File Converter is not installed on this PC ({where}). Heron never downloads "
        "it. Either open the drawing in AutoCAD (the other autocad_* tools read it there), install "
        "the ODA File Converter from the Open Design Alliance, or save the drawing as DXF and read "
        "that. Nothing was read."
    )


def run_program(command: list[str], timeout: float) -> tuple[int, str, str]:
    """Run a program with no window and no input: (exit code, output, errors)."""
    extra: dict[str, Any] = {}
    if os.name == "nt":  # pragma: no cover - Windows only: keep the converter's window hidden
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0  # SW_HIDE
        extra = {"startupinfo": info, "creationflags": subprocess.CREATE_NO_WINDOW}
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            **extra,
        )
    except subprocess.TimeoutExpired:
        raise AutocadError(
            f"The ODA File Converter did not finish in {int(timeout)} s and was stopped. Nothing was read."
        ) from None
    except OSError as exc:
        raise AutocadError(f"The ODA File Converter could not be started ({exc}). Nothing was read.") from None
    return done.returncode, done.stdout or "", done.stderr or ""


Runner = Callable[[list[str], float], tuple[int, str, str]]


def convert_to_dxf(source: Path, exe: Path, work: Path, runner: Runner | None = None) -> Path:
    """Convert a copy of a DWG to DXF in ``work``. The source is only read, never touched.

    The converter takes folders, not files: the copy goes into work/in (as
    .dwg, which is what a .dws or .dwt is), the DXF comes out in work/out.
    """
    inbox, outbox = work / "in", work / "out"
    inbox.mkdir(parents=True, exist_ok=True)
    outbox.mkdir(parents=True, exist_ok=True)
    copy = inbox / f"{source.stem}.dwg"
    try:
        shutil.copyfile(source, copy)
    except OSError as exc:
        raise AutocadError(f"{source} could not be read ({exc}). Nothing was read.") from None
    arguments = [str(inbox), str(outbox), ODA_VERSION, "DXF", "0", "1", copy.name]
    code, _out, errors = (runner or run_program)([str(exe), *arguments], CONVERT_SECONDS)
    made = outbox / f"{copy.stem}.dxf"
    if not made.is_file():
        said = (errors.strip().splitlines() or [""])[0][:200]
        raise AutocadError(
            f"The ODA File Converter made no DXF of {source.name} (exit code {code}"
            + (f", it said: {said}" if said else "")
            + "). The file may be damaged or newer than this converter: open it in AutoCAD instead. "
            "Nothing was read."
        )
    return made


# ---- opening ----------------------------------------------------------------


def clean_path(text: str) -> Path:
    """A path the modeller typed: quotes, %VARIABLES% and ~ undone."""
    cleaned = os.path.expandvars(os.path.expanduser(str(text).strip().strip('"').strip("'")))
    if not cleaned:
        raise AutocadError("Give the file's full path, e.g. C:\\Jobs\\4355\\M-101.dxf.")
    return Path(cleaned)


def _ezdxf() -> Any:
    try:
        import ezdxf
    except ImportError:
        raise AutocadError(
            "The ezdxf package is not installed in Heron's environment, so files cannot be read with "
            "AutoCAD closed. Stop the Heron server (close Claude), run "
            "'.venv\\Scripts\\python.exe -m pip install -e .' in the Heron folder, then start it again "
            "(docs/05-known-limits.md section 1)."
        ) from None
    return ezdxf


def _size_ok(path: Path) -> None:
    megabytes = path.stat().st_size / 1_000_000
    if megabytes > MAX_MB:
        raise AutocadError(
            f"{path.name} is {megabytes:.0f} MB; Heron reads files up to {MAX_MB} MB with AutoCAD closed. "
            "Open it in AutoCAD instead. Nothing was read."
        )


def _read_dxf(path: Path) -> tuple[Any, int]:
    """(the drawing, problems put right). A damaged file is read in ezdxf's recover mode."""
    ezdxf = _ezdxf()
    try:
        return ezdxf.readfile(str(path)), 0
    except PermissionError:
        raise AutocadError(f"{path} is locked by another program, so it could not be read. Nothing was read.") from None
    except OSError as exc:
        raise AutocadError(f"{path} could not be read ({exc}). Nothing was read.") from None
    except (ezdxf.DXFError, ValueError):  # a broken group or number: try ezdxf's recover mode
        pass
    from ezdxf import recover

    try:
        doc, auditor = recover.readfile(str(path))
    except (OSError, ezdxf.DXFError) as exc:
        raise AutocadError(f"{path.name} is not a DXF file Heron can read ({exc}). Nothing was read.") from None
    return doc, max(1, len(auditor.fixes) + len(auditor.errors))


def open_file(path_text: str, runner: Runner | None = None) -> Opened:
    """Read a .dxf, .dwg, .dws or .dwt into memory. Refuses with the reason in plain words."""
    path = clean_path(path_text)
    if not path.is_absolute():
        raise AutocadError(f"Give the file's full path, with its folder: {path} is not one.")
    if not path.is_file():
        raise AutocadError(f"There is no file at {path}. Nothing was read.")
    kind = path.suffix.lower()
    if kind not in DXF_KINDS + DWG_KINDS:
        raise AutocadError(f"Heron reads .dxf, .dwg, .dws and .dwt files; {path.name} is not one.")
    _size_ok(path)
    if kind in DXF_KINDS:
        doc, recovered = _read_dxf(path)
        return Opened(doc, path, "ezdxf, from the DXF itself", recovered)
    _ezdxf()  # say ezdxf is missing before converting anything
    exe = find_oda_converter()
    if exe is None:
        raise AutocadError(no_dwg_reader(path))
    with tempfile.TemporaryDirectory(prefix="heron-oda-") as work:
        made = convert_to_dxf(path, exe, Path(work), runner)
        _size_ok(made)
        doc, recovered = _read_dxf(made)
    return Opened(doc, path, f"the ODA File Converter ({exe}) made a DXF copy, read by ezdxf", recovered)


# ---- what is in it ----------------------------------------------------------


def spaces(doc: Any) -> Iterator[tuple[str, Any]]:
    """(layout name, layout): Model first, then the layouts in tab order."""
    for name in doc.layouts.names_in_taborder():
        yield name, doc.layouts.get(name)


def drawn(doc: Any) -> Iterator[tuple[str, Any]]:
    """(layout name, object) for every object in model space and every layout."""
    for name, layout in spaces(doc):
        for entity in layout:
            yield name, entity


def effective_name(insert: Any) -> str:
    """A dynamic block placed as *U12 is named after its definition, as AutoCAD shows it."""
    try:
        from ezdxf import dynblkhelper

        found = dynblkhelper.get_dynamic_block_definition(insert)
    except Exception:  # noqa: BLE001 - an odd block record: keep the name it has
        found = None
    return str(found.name if found is not None else insert.dxf.name)


def _point(vector: Any) -> list[float]:
    return [round(float(v), 6) for v in tuple(vector)[:3]]


def layer_rows(doc: Any) -> list[dict[str, Any]]:
    """The layer table, in the same words as describe_layer gives over COM."""
    rows = []
    for layer in doc.layers:
        row = {
            "name": str(layer.dxf.name),
            "color": abs(int(layer.dxf.color)),
            "linetype": str(layer.dxf.linetype),
            "lineweight": int(layer.dxf.lineweight),
            "on": bool(layer.is_on()),
            "frozen": bool(layer.is_frozen()),
            "locked": bool(layer.is_locked()),
            "plottable": bool(layer.dxf.plot),
        }
        if layer.dxf.hasattr("true_color"):
            row["rgb"] = list(layer.rgb)
        rows.append(row)
    return rows


def text_style_rows(doc: Any) -> list[dict[str, Any]]:
    rows = []
    for style in doc.styles:
        name = str(style.dxf.name)
        if not name or style.is_shape_file:
            continue  # a shape file loaded for a linetype, not a text style
        family = ""
        if style.has_extended_font_data:
            family = str(style.get_extended_font_data()[0] or "")
        rows.append({
            "name": name,
            "font": str(style.dxf.font or ""),
            "bigfont": str(style.dxf.bigfont or ""),
            "family": family,
            "height": float(style.dxf.height),
            "width": float(style.dxf.width),
            "oblique": float(style.dxf.oblique),
        })  # fmt: skip
    return rows


def tables(doc: Any) -> dict[str, list[dict[str, Any]]]:
    """Layers, text styles, dimension styles and linetypes: what a standard is made of."""
    return {
        "layers": layer_rows(doc),
        "text_styles": text_style_rows(doc),
        "dim_styles": [{"name": str(style.dxf.name)} for style in doc.dimstyles],
        "linetypes": [
            {"name": str(lt.dxf.name), "description": str(lt.dxf.get("description", "") or "")}
            for lt in doc.linetypes
        ],
    }


def layer_counts(doc: Any) -> Counter[str]:
    """Objects per layer in model space and the layouts (not inside block definitions)."""
    return Counter(str(entity.dxf.get("layer", "0")) for _space, entity in drawn(doc))


def block_rows(doc: Any) -> list[dict[str, Any]]:
    """Every named block: how many are placed, inside other blocks too, its attribute tags."""
    placed: Counter[str] = Counter()
    for _space, entity in drawn(doc):
        if entity.dxftype() == "INSERT":
            placed[effective_name(entity)] += 1
    nested: Counter[str] = Counter()
    for block in doc.blocks:
        if block.is_any_layout:
            continue
        for entity in block.query("INSERT"):
            nested[effective_name(entity)] += 1
    rows = []
    for block in doc.blocks:
        name = str(block.name)
        if block.is_any_layout or name.startswith("*"):
            continue  # layouts, dimension and hatch blocks, copies of dynamic blocks
        record = block.block_record
        row: dict[str, Any] = {
            "name": name,
            "placed": placed[name],
            "inside_other_blocks": nested[name],
            "attributes": [str(a.dxf.tag) for a in block.attdefs()],
        }
        if record.is_xref:
            row["xref"] = str(block.block.dxf.get("xref_path", "") or "")
        try:
            from ezdxf import dynblkhelper

            if dynblkhelper.is_dynamic_block_definition(record):
                row["dynamic"] = True
        except Exception:  # noqa: BLE001
            pass
        rows.append(row)
    rows.sort(key=lambda r: (-r["placed"], r["name"].lower()))
    return rows


def matches(value: str, wanted: str | None) -> bool:
    return not wanted or fnmatch.fnmatch(value.lower(), wanted.lower())


def text_rows(doc: Any, layer: str | None = None, contains: str | None = None) -> list[dict[str, Any]]:
    """Every TEXT and MTEXT in model space and the layouts, as plain words."""
    rows = []
    needle = (contains or "").lower()
    for space, entity in drawn(doc):
        kind = entity.dxftype()
        if kind not in ("TEXT", "MTEXT"):
            continue
        on = str(entity.dxf.get("layer", "0"))
        if not matches(on, layer):
            continue
        if kind == "TEXT":
            words, height = str(entity.dxf.text), float(entity.dxf.height)
        else:
            words, height = str(entity.plain_text()), float(entity.dxf.char_height)
        if needle and needle not in words.lower():
            continue
        rows.append({
            "handle": str(entity.dxf.handle),
            "type": kind,
            "text": words,
            "layer": on,
            "height": round(height, 6),
            "at": _point(entity.dxf.insert),
            "space": space,
        })  # fmt: skip
    return rows


def attribute_rows(doc: Any, block_name: str | None = None, layer: str | None = None) -> list[dict[str, Any]]:
    """Every placed block that carries attributes: the same rows autocad_extract_attributes gives."""
    rows = []
    for space, entity in drawn(doc):
        if entity.dxftype() != "INSERT" or not entity.attribs:
            continue
        name = effective_name(entity)
        on = str(entity.dxf.get("layer", "0"))
        if not matches(name, block_name) or not matches(on, layer):
            continue
        rows.append({
            "block": name,
            "handle": str(entity.dxf.handle),
            "layer": on,
            "insertion": _point(entity.dxf.insert),
            "attributes": {str(a.dxf.tag): str(a.dxf.text) for a in entity.attribs},
            "space": space,
        })  # fmt: skip
    return rows


def extents(doc: Any) -> dict[str, Any] | None:
    """The drawing's extents: the file's own header when it holds real values, else worked out."""
    low, high = doc.header.get("$EXTMIN"), doc.header.get("$EXTMAX")
    try:
        if low and high and all(abs(v) < 1e19 for v in (*low, *high)) and all(a <= b for a, b in zip(low, high, strict=False)):
            return {"min": _point(low), "max": _point(high), "from": "the file's header, as AutoCAD last saved it"}
    except TypeError:
        pass
    from ezdxf import bbox

    box = bbox.extents(doc.modelspace(), fast=True)
    if not box.has_data:
        return None
    return {"min": _point(box.extmin), "max": _point(box.extmax), "from": "worked out from the model space objects"}


def _xrefs(opened: Opened) -> list[dict[str, Any]]:
    found = []
    for block in opened.doc.blocks:
        if block.is_any_layout or not block.block_record.is_xref:
            continue
        saved = str(block.block.dxf.get("xref_path", "") or "")
        target = Path(saved) if os.path.isabs(saved) else opened.file.parent / saved
        found.append({"name": str(block.name), "path": saved, "found": bool(saved) and target.is_file()})
    return found


def summary(opened: Opened, top_blocks: int = 20) -> dict[str, Any]:
    """What the file holds, in one look: version, units, extents, counts, the busiest blocks."""
    from ezdxf.lldxf import const

    doc = opened.doc
    by_space: dict[str, Counter[str]] = {}
    for space, entity in drawn(doc):
        by_space.setdefault(space, Counter())[entity.dxftype()] += 1
    model = by_space.get("Model", Counter())
    blocks = block_rows(doc)
    text = sum(counts["TEXT"] + counts["MTEXT"] for counts in by_space.values())
    units = doc.header.get("$INSUNITS", 0)
    answer: dict[str, Any] = {
        "file": str(opened.file),
        "format": f"DXF {const.acad_release.get(doc.dxfversion, doc.dxfversion)} ({doc.dxfversion})",
        "units": unit_name(units),
        "extents": extents(doc),
        "layers": len(doc.layers),
        "objects": {
            "model": sum(model.values()),
            "layouts": {s: sum(c.values()) for s, c in by_space.items() if s != "Model"},
        },
        "model_by_type": dict(model.most_common()),
        "text": text,
        "blocks": len(blocks),
        "most_placed_blocks": [{"name": b["name"], "placed": b["placed"]} for b in blocks if b["placed"]][:top_blocks],
        "layouts": [s for s, _layout in spaces(doc) if s != "Model"],
        "xrefs": _xrefs(opened),
    }
    return answer
