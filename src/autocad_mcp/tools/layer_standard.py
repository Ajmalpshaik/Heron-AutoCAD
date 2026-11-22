r"""The office layer standard: where it lives, and the tool that loads it (#70, D-120).

The format and the check are acad/layer_standard.py (pure, tested offline).
This module decides which standard a call means, and keeps the office's own
list on this PC, never in the repository:

  a file the modeller names   layer_standard="S:\CAD\layers.csv" on the check or
                              the remap: that file, for that call
  the office standard         %LOCALAPPDATA%\Heron\autocad\standards\office-layers.json,
                              written by action="import" from the CSV the
                              modeller filled (action="template" puts an empty
                              one beside it): layer_standard="office"
  the example                 the generic MEP list that ships with Heron
                              (data/layer-standard-example-mep.csv):
                              layer_standard="example"

"office" with no office standard loaded falls back to the example for a check,
and the check is then not decided (passed: null, D-64): the modeller asked about
the office's standard, which is not there. A remap is refused instead: it would
move objects onto layers nobody chose.

autocad_layer_standard reads and writes only Heron's own folder and the CSV it
is given, never AutoCAD, so it answers with AutoCAD closed (core/gate.py
NO_AUTOCAD_TOOLS) and needs no padlock, as autocad_checklist's own lists do.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import layer_standard as rules
from ..core.errors import AutocadError
from ..core.folders import heron_local
from ..core.registry import dumps, mcp, tool_errors, tool_meta

OFFICE, EXAMPLE = "office", "example"
OFFICE_FILE = "office-layers.json"
TEMPLATE_FILE = "office-layers.csv"
PREVIOUS_FILE = "office-layers.previous.json"
MAX_BYTES = 2_000_000
CHOICE_HELP = (
    "'office' for the office layer standard loaded on this PC (autocad_layer_standard), "
    "'example' for the generic MEP example that ships with Heron, or the full path of a "
    ".csv or .json layer standard"
)


def standards_dir() -> Path:
    return heron_local() / "standards"


def office_file() -> Path:
    return standards_dir() / OFFICE_FILE


def template_file() -> Path:
    return standards_dir() / TEMPLATE_FILE


def _clean(text: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(text).strip().strip('"'))))


def _read(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AutocadError(f"Could not read the layer standard {path}: {exc}") from exc
    if size > MAX_BYTES:
        raise AutocadError(f"{path} is {size // 1000} kB; a layer standard is a list of layers, under {MAX_BYTES // 1_000_000} MB.")
    try:
        return rules.read_file(path)
    except rules.StandardError as exc:
        raise AutocadError(str(exc)) from exc


def _named(text: str) -> Path:
    path = _clean(text)
    if not path.is_absolute():
        raise AutocadError(f"Give the layer standard as {CHOICE_HELP}: '{text}' is none of those.")
    if not path.is_file():
        raise AutocadError(f"There is no layer standard at {path}.")
    return path


def resolve(choice: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(the standard, where it came from) for 'office', 'example' or a path.

    A file the modeller names wins for that call; 'office' is the one loaded on
    this PC, else the example, said plainly (info["fallback"]).
    """
    key = str(choice or "").strip().strip('"').lower()
    if key == OFFICE:
        path = office_file()
        if path.is_file():
            standard = _read(path)
            return standard, {"kind": OFFICE, "file": str(path), "example": standard["example"],
                              "source": f"the office layer standard on this PC ({path})"}  # fmt: skip
        standard = _read(rules.EXAMPLE_FILE)
        return standard, {
            "kind": EXAMPLE, "file": str(rules.EXAMPLE_FILE), "example": True, "fallback": True,
            "source": "the generic MEP example layer standard that ships with Heron, because no office layer standard is loaded on this PC",
        }  # fmt: skip
    if key == EXAMPLE:
        standard = _read(rules.EXAMPLE_FILE)
        return standard, {"kind": EXAMPLE, "file": str(rules.EXAMPLE_FILE), "example": True,
                          "source": "the generic MEP example layer standard that ships with Heron (not an office standard)"}  # fmt: skip
    path = _named(choice)
    standard = _read(path)
    return standard, {"kind": "file", "file": str(path), "example": standard["example"],
                      "source": f"the layer standard {path}"}  # fmt: skip


NOT_LOADED = (
    "No office layer standard is loaded on this PC yet. autocad_layer_standard(action='template') "
    "puts an empty CSV in {folder}; fill it from the office's layer list, then "
    "autocad_layer_standard(action='import')."
)


def not_loaded() -> str:
    return NOT_LOADED.format(folder=standards_dir())


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    spare = path.with_name(path.name + ".tmp")
    spare.write_text(text, encoding="utf-8", newline="\n")
    os.replace(spare, path)


def _show(path: str | None) -> dict[str, Any]:
    if path:
        standard = _read(_named(path))
        return {"file": str(_clean(path)), "checked": "read only: this file was not imported", "readable": True,
                "standard": rules.summary(standard), **_ignored(standard)}  # fmt: skip
    standard, info = resolve(OFFICE)
    answer: dict[str, Any] = {
        "in_force": info["source"],
        "file": info["file"],
        "folder": str(standards_dir()),
        "standard": rules.summary(standard),
        "columns": list(rules.COLUMNS),
    }
    if info.get("fallback"):
        answer["office_standard"] = None
        answer["next"] = not_loaded()
    else:
        answer["office_standard"] = info["file"]
        if standard.get("imported_from"):
            answer["imported_from"] = standard["imported_from"]
            answer["imported_at"] = standard.get("imported_at")
    if template_file().is_file():
        answer["template"] = str(template_file())
    return answer


def _ignored(standard: dict[str, Any]) -> dict[str, Any]:
    if not standard.get("ignored_columns"):
        return {}
    return {"ignored_columns": standard["ignored_columns"],
            "ignored_note": "These columns are not part of a layer standard and were not read: " + ", ".join(rules.COLUMNS) + " are."}  # fmt: skip


def _template(replace: bool) -> dict[str, Any]:
    path = template_file()
    if path.is_file() and not replace:
        raise AutocadError(
            f"There is already a CSV to fill at {path}. Open that one, or say replace=true to start "
            "again from an empty one (what it holds is lost). Nothing was written."
        )
    _write(path, rules.template_csv())
    return {
        "template": str(path),
        "columns": list(rules.COLUMNS),
        "example": str(rules.EXAMPLE_FILE),
        "next": (
            "Open the CSV in Excel, put one layer per row under the header (the # lines say what each "
            "column takes; the example file shows a filled one), save it as CSV, then "
            "autocad_layer_standard(action='import')."
        ),
    }


def _import(path: str | None) -> dict[str, Any]:
    source = _named(path) if path else template_file()
    if not path and not source.is_file():
        raise AutocadError(
            f"There is no CSV to import at {source}. Say which file with path=, or make an empty one "
            "with action='template' and fill it first. Nothing was imported."
        )
    standard = _read(source)
    if standard["example"]:
        raise AutocadError(
            f"{source} says it is an example ('# example: yes'), so it is not imported as the office "
            "standard. If it really is the office's list, delete that line and import again. Nothing was imported."
        )
    standard["imported_from"] = str(source)
    standard["imported_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    ignored = _ignored(standard)
    standard.pop("ignored_columns", None)
    target = office_file()
    kept = None
    if target.is_file():
        previous = target.with_name(PREVIOUS_FILE)
        os.replace(target, previous)
        kept = str(previous)
    _write(target, rules.to_json(standard))
    answer = {
        "imported": str(target),
        "imported_from": str(source),
        "standard": rules.summary(standard),
        "next": (
            "autocad_check_standards(layer_standard='office') checks a drawing against it; "
            "autocad_remap_layers(layer_standard='office') moves objects off the old names it replaces."
        ),
        **ignored,
    }
    if kept:
        answer["previous"] = kept
    return answer


def _remove() -> dict[str, Any]:
    target = office_file()
    if not target.is_file():
        return {"removed": None, "note": "No office layer standard was loaded on this PC; nothing changed."}
    previous = target.with_name(PREVIOUS_FILE)
    os.replace(target, previous)
    return {"removed": str(target), "kept_as": str(previous),
            "note": "'office' now means the generic MEP example again, and a check against it is not decided."}  # fmt: skip


@mcp.tool(name="autocad_layer_standard", **tool_meta("Office Layer Standard"))
@tool_errors
async def autocad_layer_standard(
    action: Annotated[
        Literal["show", "template", "import", "remove"],
        Field(description=(
            "show: which layer standard 'office' means on this PC and what it holds (with path: read "
            "that file and say what is wrong with it, importing nothing). template: an empty CSV to "
            "fill, in Heron's standards folder. import: load the filled CSV (or a .json) as the "
            "office standard. remove: unload it, back to the example."
        )),
    ] = "show",
    path: Annotated[
        str | None,
        Field(description="The full path of a .csv or .json layer standard: for show, to read it; for import, the file to load (default: the template CSV)."),
    ] = None,
    replace: Annotated[bool, Field(description="template: start again from an empty CSV even if one is already there.")] = False,
) -> str:
    """Load the office's own layer standard from a CSV, or say which standard is in force.

    A layer standard is one row per layer: name (or a pattern with * and ?),
    colour, linetype, lineweight, plot, description, the old names it replaces,
    and whether every drawing must have it. The office's own list stays on this
    PC, in %LOCALAPPDATA%\\Heron\\autocad\\standards\\, never in Heron's files.
    Until one is imported, 'office' means the generic MEP example that ships
    with Heron, and a check against it is not decided. A CSV with any problem
    imports nothing; the answer lists each problem with its row number.
    Reads and writes only Heron's own folder and the file given: no AutoCAD,
    so it answers with AutoCAD closed, and the drawing is never touched.

    Returns:
        JSON: show {"in_force", "file", "folder", "office_standard", "standard"
        {"name", "example", "counts", "layers"}, "next"}; template {"template",
        "next"}; import {"imported", "imported_from", "standard", "previous"};
        remove {"removed", "kept_as"}.

    Examples:
        - Use when: "set up our office layer standard" or "where do I put our
          layer list" -> action='template', then the modeller fills the CSV.
        - Use when: "I've filled the layer CSV, load it" -> action='import'.
        - Use when: "which layer standard are you using" -> action='show'.
        - Use when: "is my layer CSV right" -> action='show' with path; reads
          it and lists every problem, importing nothing.
        - Don't use when: checking a drawing against the standard -
          autocad_check_standards(layer_standard='office'); putting objects on
          its layers - autocad_remap_layers(layer_standard='office').
        - Don't use when: the standard is an office .dws or template drawing -
          autocad_check_standards(reference=...).
    """
    if action == "template":
        answer = _template(replace)
    elif action == "import":
        answer = _import(path)
    elif action == "remove":
        answer = _remove()
    else:
        answer = _show(path)
    return dumps(answer)
