r"""A layer standard as a rule file: read, checked, turned into remap rules (#70, D-120).

One row per layer: its name (or a wildcard pattern such as ``M-*-IDEN``), the
colour, linetype, lineweight, plot / no plot and description it must have, the
old layer names it replaces, and whether every drawing must have it. The same
rows come as a CSV (the file a modeller fills in Excel from the office list) or
as JSON (what Heron keeps once a CSV is imported). Pure: no AutoCAD here, so it
is all tested offline.

What a check reports, per layer of the drawing:
  listed       the colour, linetype, lineweight, plot and description the row
               gives (a blank cell is not checked)
  a pattern    the first pattern row it matches, the same way
  not listed   against the standard's name pattern when it has one, else
               "not in the layer standard" (flag_extra=False leaves those out)
  required     a required layer this drawing does not have
Layer 0, Defpoints and xref layers (XREF|NAME) are never "not listed": they are
AutoCAD's own, or the xref's to check in the xref drawing.

The remap rules: objects already on a standard layer, or on one a pattern row
covers, stay there and the layer gets the standard's properties; objects on an
old layer a row ``replaces`` move to that row's layer. A pattern row is never a
target.

The example that ships with Heron (data/layer-standard-example-mep.csv) is a
generic MEP list in the discipline-major-minor style. It is an example, never
the office's standard: the office's own list stays on the modeller's PC,
outside this public repository.
"""

from __future__ import annotations

import csv
import fnmatch
import io
import json
import re
from pathlib import Path
from typing import Any

from ..core.registry import ACI_COLORS
from .props import (
    LW_BYBLOCK,
    LW_BYLAYER,
    LW_DEFAULT,
    lineweight_value,
    lineweight_words,
)

FORMAT = 1
EXAMPLE_FILE = Path(__file__).resolve().parents[1] / "data" / "layer-standard-example-mep.csv"
COLUMNS = ("layer", "color", "linetype", "lineweight", "plot", "description", "replaces", "required")
# The header words a modeller may use for each column, lower case.
ALIASES = {
    "layer": "layer", "name": "layer", "layer name": "layer", "layers": "layer",
    "color": "color", "colour": "color", "aci": "color",
    "linetype": "linetype", "line type": "linetype",
    "lineweight": "lineweight", "line weight": "lineweight", "lineweight (mm)": "lineweight",
    "line weight (mm)": "lineweight", "lw": "lineweight",
    "plot": "plot", "plot?": "plot", "plottable": "plot", "plots": "plot",
    "description": "description", "desc": "description",
    "replaces": "replaces", "old names": "replaces", "old layers": "replaces", "old layer names": "replaces",
    "required": "required", "required?": "required", "must have": "required",
}  # fmt: skip
SETTINGS = ("name", "name_pattern", "example")
# What AutoCAD never allows in a layer name; a pattern may add * and ?.
_BAD = set('<>/\\":;?*|,=`')
_WILD = set("*?")
_YES = {"yes", "y", "true", "1", "on", "plot", "plots", "x"}
_NO = {"no", "n", "false", "0", "off", "no plot", "noplot", "not plotted", "-"}
ALWAYS_THERE = {"0", "defpoints"}
COMPARED = "colour, linetype, lineweight, plot / no plot and description, for each layer the standard lists or a pattern row covers"
LEFT_OUT = "Layer 0, Defpoints and xref layers (XREF|NAME) are never reported as not in the standard."
MAX_PROBLEMS = 25
# The finding names a layer standard check gives.
RULES = ("layer_standard_differs", "layer_standard_name", "layer_not_in_layer_standard", "layer_standard_missing")


class StandardError(ValueError):
    """A layer standard that cannot be used; the message says what to put right."""


# ---- reading one row ---------------------------------------------------------


def is_pattern(name: str) -> bool:
    return bool(_WILD & set(name))


def _glob(pattern: str) -> str:
    """A wildcard as fnmatch reads it: * and ? only, a [ is a plain character."""
    return pattern.lower().replace("[", "[[]")


def matches(pattern: str, name: str) -> bool:
    """A layer name against a name or wildcard, case-insensitive, as AutoCAD names are."""
    return fnmatch.fnmatchcase(str(name).lower(), _glob(str(pattern)))


def _name(text: Any, what: str, wildcards: bool) -> str:
    name = str(text or "").strip()
    if not name:
        raise StandardError(f"{what} is empty")
    if len(name) > 255:
        raise StandardError(f"{what} '{name[:40]}...' is longer than AutoCAD's 255 characters")
    bad = sorted((_BAD - _WILD if wildcards else _BAD) & set(name))
    if bad:
        raise StandardError(f"{what} '{name}' has {' '.join(bad)}, which AutoCAD does not allow in a layer name")
    return name


def _color(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, bool):
        raise StandardError(f"colour '{value}' is not a colour")
    text = str(value).strip().lower()
    if "," in text or text.startswith("rgb"):
        raise StandardError(
            f"colour '{value}' is a true colour; give the AutoCAD Color Index (1 to 255) or a name such as red or cyan"
        )
    if text in ACI_COLORS:
        number = ACI_COLORS[text]
    else:
        try:
            number = int(float(text))
        except (ValueError, OverflowError):
            raise StandardError(
                f"colour '{value}' is not a colour: give the AutoCAD Color Index (1 to 255) or one of "
                + ", ".join(sorted(k for k, v in ACI_COLORS.items() if 1 <= v <= 255))
            ) from None
        if float(text) != number:
            raise StandardError(f"colour '{value}' is not a whole number")
    if not 1 <= number <= 255:
        raise StandardError(f"colour '{value}': a layer's colour is 1 to 255 (ByLayer and ByBlock are for objects)")
    return number


def _lineweight(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    if str(value).strip() == str(LW_DEFAULT):
        return LW_DEFAULT  # AutoCAD's own number for Default, as Heron's JSON keeps it
    try:
        code = lineweight_value(value)
    except ValueError as exc:
        raise StandardError(f"lineweight: {exc}") from None
    if code in (LW_BYLAYER, LW_BYBLOCK):
        raise StandardError(f"lineweight '{value}': a layer's lineweight is a weight or Default, not ByLayer or ByBlock")
    return code


def _yes_no(value: Any, what: str) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return None
    if text in _YES:
        return True
    if text in _NO:
        return False
    raise StandardError(f"{what} '{value}' is not yes or no")


def _replaces(value: Any) -> list[str]:
    if value is None:
        return []
    parts = value if isinstance(value, list) else re.split(r"[;,\n]", str(value))
    return [_name(part, "an old name in replaces", wildcards=True) for part in parts if str(part).strip()]


def parse_row(raw: dict[str, Any]) -> dict[str, Any]:
    """One layer row as Heron keeps it. Raises StandardError naming every cell that is wrong."""
    layer = _name(raw.get("layer"), "the layer name", wildcards=True)
    row: dict[str, Any] = {"layer": layer, "pattern": is_pattern(layer)}
    wrong: list[str] = []

    def cell(key: str, read: Any) -> None:
        try:
            value = read(raw.get(key))
        except StandardError as exc:
            wrong.append(str(exc))
            return
        if value is not None and value != "":
            row[key] = value

    cell("color", _color)
    cell("linetype", lambda v: _name(v, "the linetype", wildcards=False) if str(v or "").strip() else None)
    cell("lineweight", _lineweight)
    cell("plot", lambda v: _yes_no(v, "plot"))
    cell("description", lambda v: str(v or "").strip())
    cell("replaces", _replaces)
    cell("required", lambda v: _yes_no(v, "required"))
    row["replaces"] = row.get("replaces") or []
    row["required"] = bool(row.get("required"))
    if row["replaces"] and row["pattern"]:
        wrong.append(f"'{layer}' is a pattern, so nothing can be moved onto it: give replaces on a real layer name")
    if row["required"] and row["pattern"]:
        wrong.append(f"'{layer}' is a pattern, so it cannot be required: name the layer itself")
    if wrong:
        raise StandardError(f"{layer}: " + "; ".join(wrong))
    return row


def _finish(rows: list[tuple[str, dict[str, Any]]], settings: dict[str, Any], problems: list[str], source: str) -> dict[str, Any]:
    """The whole standard, or every problem found at once."""
    seen: dict[str, str] = {}
    for where, row in rows:
        key = row["layer"].lower()
        if key in seen:
            problems.append(f"{where}: '{row['layer']}' is already the layer of {seen[key]}")
        else:
            seen[key] = where
    old_names: dict[str, str] = {}
    for where, row in rows:
        for old in row["replaces"]:
            key = old.lower()
            covering = None if is_pattern(old) else next(
                (other for _, other in rows if other["pattern"] and matches(other["layer"], old)), None)  # fmt: skip
            if key in seen and not is_pattern(old):
                problems.append(f"{where}: '{old}' is a layer of the standard itself ({seen[key]}), so it cannot be an old name too")
            elif covering is not None:
                problems.append(f"{where}: '{old}' is covered by the pattern row {covering['layer']}, so it is a layer of "
                                "the standard and cannot be an old name too")  # fmt: skip
            elif key in old_names:
                problems.append(f"{where}: the old name '{old}' is already replaced by {old_names[key]}")
            else:
                old_names[key] = f"{where} ({row['layer']})"
    pattern = settings.get("name_pattern")
    if pattern:
        try:
            re.compile(str(pattern))
        except re.error as exc:
            problems.append(f"name_pattern '{pattern}' is not a regular expression AutoCAD's names can be read with ({exc})")
    if not rows and not problems:
        problems.append("it holds no layers: one row per layer, under a header row starting with 'layer'")
    if problems:
        shown = problems[:MAX_PROBLEMS]
        more = len(problems) - len(shown)
        raise StandardError(
            f"{source} cannot be used as a layer standard. Put these right and try again:\n- "
            + "\n- ".join(shown)
            + (f"\n- and {more} more" if more else "")
        )
    return {
        "heron_layer_standard": FORMAT,
        "name": str(settings.get("name") or "").strip() or "Layer standard",
        "example": bool(settings.get("example")),
        "name_pattern": str(pattern) if pattern else None,
        "layers": [row for _, row in rows],
    }


# ---- whole files ---------------------------------------------------------------


def _decode(data: bytes) -> str:
    """Excel's 'CSV UTF-8' carries a BOM; its plain 'CSV' is the Windows code page."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _delimiter(text: str) -> str:
    """Comma, or the semicolon or tab Excel writes in some regions, read from the header line."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.lstrip('"').startswith("#"):
            counts = {mark: stripped.count(mark) for mark in (",", ";", "\t")}
            best = max(counts, key=lambda mark: counts[mark])
            return best if counts[best] else ","
    return ","


def _setting(text: str, settings: dict[str, Any], where: str, problems: list[str]) -> None:
    """'# name: ...', '# name_pattern: ...', '# example: yes'. Any other # line is a note."""
    match = re.match(r"#\s*([a-z_ ]+?)\s*:\s*(.*)$", text.strip(), re.IGNORECASE)
    if not match:
        return
    key = match.group(1).strip().lower().replace(" ", "_")
    if key not in SETTINGS:
        return
    value = match.group(2).strip()
    if key == "example":
        try:
            settings[key] = bool(_yes_no(value, "example"))
        except StandardError as exc:
            problems.append(f"{where}: {exc}")
        return
    settings[key] = value


def from_csv(text: str, source: str = "The CSV") -> dict[str, Any]:
    """A layer standard from CSV text: a header row, then one row per layer; # lines are notes."""
    delimiter = _delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header: list[str | None] | None = None
    ignored: list[str] = []
    settings: dict[str, Any] = {}
    rows: list[tuple[str, dict[str, Any]]] = []
    problems: list[str] = []
    for cells in reader:
        where = f"row {reader.line_num}"
        trimmed = list(cells)
        while trimmed and not str(trimmed[-1]).strip():
            trimmed.pop()
        if not trimmed:
            continue
        if str(trimmed[0]).strip().startswith("#"):
            _setting(delimiter.join(trimmed), settings, where, problems)
            continue
        if header is None:
            header = [ALIASES.get(str(cell).strip().lower()) for cell in cells]
            ignored = [str(cell).strip() for cell, key in zip(cells, header, strict=True) if key is None and str(cell).strip()]
            if "layer" not in header:
                problems.append(f"{where}: the header row needs a 'layer' column; the columns are " + ", ".join(COLUMNS))
                break
            continue
        raw = {key: cell for key, cell in zip(header, cells, strict=False) if key}
        try:
            rows.append((where, parse_row(raw)))
        except StandardError as exc:
            problems.append(f"{where}: {exc}")
    standard = _finish(rows, settings, problems, source)
    if ignored:
        standard["ignored_columns"] = ignored
    return standard


def from_json(data: Any, source: str = "The file") -> dict[str, Any]:
    """A layer standard from its JSON form: {"layers": [{"layer": ..., ...}], "name", "name_pattern", "example"}."""
    if isinstance(data, list):
        data = {"layers": data}
    if not isinstance(data, dict) or not isinstance(data.get("layers"), list):
        raise StandardError(f"{source} is not a layer standard: it needs a 'layers' list, one object per layer.")
    version = data.get("heron_layer_standard", FORMAT)
    if version != FORMAT:
        raise StandardError(f"{source} is layer standard format {version}; this Heron reads format {FORMAT}.")
    rows: list[tuple[str, dict[str, Any]]] = []
    problems: list[str] = []
    for i, raw in enumerate(data["layers"], start=1):
        where = f"layer {i}"
        if not isinstance(raw, dict):
            problems.append(f"{where}: {raw!r} is not an object")
            continue
        stray = sorted(set(raw) - set(COLUMNS) - {"pattern"})
        if stray:
            problems.append(f"{where}: unknown keys {', '.join(stray)}; the keys are " + ", ".join(COLUMNS))
            continue
        try:
            rows.append((where, parse_row(raw)))
        except StandardError as exc:
            problems.append(f"{where}: {exc}")
    settings = {key: data.get(key) for key in SETTINGS}
    standard = _finish(rows, settings, problems, source)
    for key in ("imported_from", "imported_at"):
        if data.get(key):
            standard[key] = data[key]
    return standard


def read_file(path: Path) -> dict[str, Any]:
    """A layer standard from a .csv or .json file. Raises StandardError."""
    suffix = path.suffix.lower()
    if suffix not in (".csv", ".json", ".txt"):
        raise StandardError(f"A layer standard is a .csv or a .json file; {path.name} is not one.")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise StandardError(f"Could not read the layer standard {path}: {exc}") from exc
    text = _decode(data)
    if suffix == ".json":
        try:
            loaded = json.loads(text)
        except ValueError as exc:
            raise StandardError(f"{path} is not valid JSON ({exc}).") from exc
        return from_json(loaded, str(path))
    return from_csv(text, str(path))


def to_json(standard: dict[str, Any]) -> str:
    return json.dumps(standard, indent=2, ensure_ascii=False) + "\n"


def template_csv() -> str:
    """The empty CSV a modeller fills from the office list: the header and notes, no layers."""
    lines = [
        "# Heron layer standard. One row per layer, under the header row. Lines starting with # are notes.",
        "# layer: the full layer name, or a pattern with * and ? (M-*-IDEN) to check a group of layers.",
        "# color: AutoCAD Color Index 1 to 255, or red / yellow / green / cyan / blue / magenta / white.",
        "# linetype: Continuous, HIDDEN, DASHED, CENTER ... as in the Linetype Manager.",
        "# lineweight: in mm as AutoCAD lists them (0.18, 0.25, 0.35, 0.50) or Default.",
        "# plot: yes or no.  description: the layer's description, as in the Layer Properties Manager.",
        "# replaces: old layer names this layer takes over, separated by ; (wildcards work: MECH-DUCT*).",
        "# required: yes when every drawing must have this layer. A blank cell is not checked.",
        "# name: My office layer standard",
        "# name_pattern: ",
        "layer,color,linetype,lineweight,plot,description,replaces,required",
    ]
    return "\n".join(lines) + "\n"


# ---- the check ------------------------------------------------------------------


def _row_for(standard: dict[str, Any], name: str) -> dict[str, Any] | None:
    key = name.lower()
    for row in standard["layers"]:
        if not row["pattern"] and row["layer"].lower() == key:
            return row
    for row in standard["layers"]:
        if row["pattern"] and matches(row["layer"], name):
            return row
    return None


def differences(layer: dict[str, Any], row: dict[str, Any]) -> list[str]:
    """What a drawing layer has that its standard row does not. A blank in the row is not checked."""
    found = []
    if "color" in row and layer.get("color") != row["color"]:
        found.append(f"colour {layer.get('color')} here, {row['color']} in the standard")
    if "linetype" in row and str(layer.get("linetype", "")).lower() != row["linetype"].lower():
        found.append(f"linetype {layer.get('linetype')} here, {row['linetype']} in the standard")
    if "lineweight" in row and layer.get("lineweight") != row["lineweight"]:
        found.append(f"lineweight {lineweight_words(layer.get('lineweight'))} here, "
                     f"{lineweight_words(row['lineweight'])} in the standard")  # fmt: skip
    if "plot" in row and bool(layer.get("plottable", True)) != row["plot"]:
        here = "plots" if layer.get("plottable", True) else "does not plot"
        found.append(f"{here} here, {'plots' if row['plot'] else 'does not plot'} in the standard")
    if "description" in row and str(layer.get("description") or "").strip().lower() != row["description"].lower():
        found.append(f"description '{layer.get('description') or ''}' here, '{row['description']}' in the standard")
    return found


def check(layers: list[dict[str, Any]], standard: dict[str, Any], flag_extra: bool = True) -> list[dict[str, Any]]:
    """Every drawing layer against the standard, A-Z, then the required layers it lacks."""
    findings: list[dict[str, Any]] = []
    pattern = re.compile(standard["name_pattern"]) if standard.get("name_pattern") else None
    have = set()
    for layer in sorted(layers, key=lambda item: str(item.get("name", "")).lower()):
        name = str(layer.get("name", ""))
        if not name:
            continue
        have.add(name.lower())
        row = _row_for(standard, name)
        if row is not None:
            found = differences(layer, row)
            if found:
                finding = {"rule": "layer_standard_differs", "layer": name, "detail": "; ".join(found)}
                if row["pattern"]:
                    finding["standard_row"] = row["layer"]
                findings.append(finding)
            continue
        if name.lower() in ALWAYS_THERE or "|" in name:
            continue
        if pattern is not None:
            if not pattern.search(name):
                findings.append({"rule": "layer_standard_name", "layer": name,
                                 "detail": f"not in the layer standard, and its name does not match {pattern.pattern}"})  # fmt: skip
        elif flag_extra:
            findings.append({"rule": "layer_not_in_layer_standard", "layer": name,
                             "detail": "this drawing has this layer; the layer standard does not list it"})  # fmt: skip
    for row in standard["layers"]:
        if row["required"] and row["layer"].lower() not in have:
            findings.append({"rule": "layer_standard_missing", "layer": row["layer"],
                             "detail": "the layer standard needs this layer; this drawing does not have it"})  # fmt: skip
    return findings


# ---- the remap rules ---------------------------------------------------------------

_PROPS = ("color", "linetype", "lineweight", "plot", "description")


def remap_rules(standard: dict[str, Any]) -> list[dict[str, Any]]:
    """autocad_remap_layers' rules from a standard, in the order that keeps standard layers where they are.

    First every standard layer as itself: what is on it stays, and the layer
    gets the standard's properties. Then every pattern row the same way, as a
    keep rule: a layer the pattern covers is a standard layer too, so no old
    name may take what is on it. Then each old name a row replaces, in file
    order. Matched on the layer only, never on a block's name: an old layer
    name is a layer name.
    """
    targets = [row for row in standard["layers"] if not row["pattern"]]
    rules: list[dict[str, Any]] = []
    for row in targets:
        props = {key: row[key] for key in _PROPS if key in row}
        rules.append({"source_layer": row["layer"].replace("[", "[[]"), "layer": row["layer"], **props})
    for row in standard["layers"]:
        if row["pattern"]:
            props = {key: row[key] for key in _PROPS if key in row}
            rules.append({"source_layer": row["layer"].replace("[", "[[]"), "keep": True, **props})
    for row in targets:
        props = {key: row[key] for key in _PROPS if key in row}
        for old in row["replaces"]:
            rules.append({"source_layer": old.replace("[", "[[]"), "layer": row["layer"], **props})
    return rules


def summary(standard: dict[str, Any], limit: int = 200) -> dict[str, Any]:
    """What a standard holds, for a modeller to read back."""
    rows = standard["layers"]
    shown = []
    for row in rows[:limit]:
        item = {key: row[key] for key in ("layer", *_PROPS) if key in row}
        if "lineweight" in item:
            item["lineweight"] = lineweight_words(item["lineweight"])
        if row["replaces"]:
            item["replaces"] = row["replaces"]
        if row["required"]:
            item["required"] = True
        if row["pattern"]:
            item["pattern"] = True
        shown.append(item)
    disciplines: dict[str, int] = {}
    for row in rows:
        if not row["pattern"]:
            head = row["layer"].split("-")[0].upper()
            disciplines[head] = disciplines.get(head, 0) + 1
    return {
        "name": standard["name"],
        "example": standard["example"],
        "name_pattern": standard.get("name_pattern"),
        "counts": {
            "layers": sum(1 for row in rows if not row["pattern"]),
            "patterns": sum(1 for row in rows if row["pattern"]),
            "old_names": sum(len(row["replaces"]) for row in rows),
            "required": sum(1 for row in rows if row["required"]),
            "by_first_letter": dict(sorted(disciplines.items())),
        },
        "layers": shown,
        "truncated": len(rows) > limit,
    }
