"""Drawing settings and styles: the set-up a draftsman does before drawing.

Units and precision, the drawing scale and everything that follows from it
(DIMSCALE, LTSCALE, the annotation scale), object snaps, point style, text
styles, dimension styles. Thirty minutes of clicking through dialogs, in two
calls.

**Why these are CHANGE and not ADMIN.** ``autocad_set_variable`` is ADMIN
because it will set *any* system variable, which is an escape hatch. The tools
here write only from a fixed list kept in this file: drafting settings, and the
DIM variables behind a dimension style. They cannot save a file, run a command
or reach outside that list, so they need the Changes padlock, like drawing a
line does. Every call reports the old value beside the new one, and
``dry_run`` shows the whole plan without writing a thing.

The mapping from plain words to variables is a set of pure functions at the top
of the file, tested without AutoCAD.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from ..acad import sheets as plan
from ..acad.tables import validate_name
from ..acad.units import INSUNITS, rad
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, com_message
from ..core.registry import dumps, mcp, tool_errors, tool_meta, undo_mark
from ..core.variants import double_array
from ._shared import before_after

# ---------------------------------------------------------------------------
# Plain words to system variables (pure: no AutoCAD below this line)
# ---------------------------------------------------------------------------

# OSMODE bits. Values from AutoCAD's own OSMODE documentation; 1024 is the
# geometric centre on current releases (it was "quick" on R14 and earlier).
OSNAPS: dict[str, int] = {
    "endpoint": 1,
    "midpoint": 2,
    "center": 4,
    "centre": 4,
    "node": 8,
    "quadrant": 16,
    "intersection": 32,
    "insertion": 64,
    "perpendicular": 128,
    "tangent": 256,
    "nearest": 512,
    "geometric_center": 1024,
    "apparent_intersection": 2048,
    "extension": 4096,
    "parallel": 8192,
}
# The bit AutoCAD uses to switch every running snap off without losing them.
OSNAP_SUPPRESS = 16384

# PDMODE: the shape, plus 32 for a surrounding circle and 64 for a square.
POINT_STYLES: dict[str, int] = {
    "dot": 0,
    "none": 1,
    "cross": 2,
    "x": 3,
    "tick": 4,
    "circle_dot": 32,
    "circle_cross": 34,
    "circle_x": 35,
    "circle_tick": 36,
    "square_dot": 64,
    "square_cross": 66,
    "square_x": 67,
    "square_circle_x": 99,
}

# LUNITS
LINEAR_FORMATS: dict[str, int] = {
    "scientific": 1,
    "decimal": 2,
    "engineering": 3,
    "architectural": 4,
    "fractional": 5,
}
# AUNITS
ANGLE_FORMATS: dict[str, int] = {
    "decimal": 0,
    "dms": 1,
    "deg_min_sec": 1,
    "grads": 2,
    "radians": 3,
    "surveyor": 4,
}

# The one list these tools may write. Nothing outside it is reachable.
DRAWING_VARIABLES: tuple[str, ...] = (
    "INSUNITS", "MEASUREMENT", "LUNITS", "LUPREC", "AUNITS", "AUPREC",
    "DIMSCALE", "DIMASSOC", "CANNOSCALE", "ANNOALLVISIBLE", "ANNOAUTOSCALE",
    "LTSCALE", "PSLTSCALE", "MSLTSCALE", "CELTSCALE",
    "TEXTSIZE", "OSMODE", "PDMODE", "PDSIZE", "LWDISPLAY", "CELWEIGHT",
    "ATTDIA", "ATTREQ", "LIMMIN", "LIMMAX", "LIMCHECK", "UCSICON", "ELEVATION",
    "THICKNESS", "FILLMODE", "MIRRTEXT", "ANGBASE", "ANGDIR", "SPLFRAME",
)

UNIT_CODES = {name: code for code, name in INSUNITS.items()}
# The spellings a modeller actually types.
UNIT_CODES.update(
    {
        "mm": 4,
        "millimetres": 4,
        "cm": 5,
        "centimetres": 5,
        "m": 6,
        "metres": 6,
        "km": 7,
        "kilometres": 7,
        "in": 1,
        "inch": 1,
        "ft": 2,
        "foot": 2,
    }
)
METRIC_UNITS = {4, 5, 6, 7, 14, 15, 16}


def osnap_bits(names: list[str]) -> int:
    """An OSMODE value from snap names. ['endpoint', 'midpoint'] -> 3.

    ['none'] switches every running snap off.
    """
    wanted = [str(n).strip().lower().replace(" ", "_").replace("-", "_") for n in names]
    if not wanted or wanted == ["none"]:
        return 0
    bits = 0
    unknown = []
    for name in wanted:
        if name == "all":
            bits |= sum(set(OSNAPS.values()))
            continue
        if name in OSNAPS:
            bits |= OSNAPS[name]
        else:
            unknown.append(name)
    if unknown:
        raise ValueError(
            f"not object snaps: {', '.join(unknown)}. Use 'none', 'all', or any of: "
            + ", ".join(sorted(set(OSNAPS) - {"centre"}))
        )
    return bits


def osnap_names(bits: int) -> list[str]:
    """The snap names an OSMODE value stands for, in AutoCAD's own bit order."""
    value = int(bits)
    if value & OSNAP_SUPPRESS:
        return ["suppressed"]
    canonical = {bit: name for name, bit in OSNAPS.items() if name != "centre"}
    return [canonical[bit] for bit in sorted(canonical) if value & bit]


def point_mode(style: str) -> int:
    """A PDMODE value from a point-style name."""
    key = str(style).strip().lower().replace(" ", "_").replace("-", "_")
    if key not in POINT_STYLES:
        raise ValueError(
            f"'{style}' is not a point style. Use one of: {', '.join(sorted(POINT_STYLES))}."
        )
    return POINT_STYLES[key]


def unit_code(units: str | int) -> int:
    """An INSUNITS code from a unit name or a code."""
    if isinstance(units, int) and not isinstance(units, bool):
        if units not in INSUNITS:
            raise ValueError(f"{units} is not an INSUNITS code; they run 0 to 20.")
        return units
    key = str(units).strip().lower()
    if key not in UNIT_CODES:
        raise ValueError(
            f"'{units}' is not a unit this server knows. Use millimeters, centimeters, "
            "meters, inches, feet, or an INSUNITS code 0-20."
        )
    return UNIT_CODES[key]


def plan_settings(wanted: dict[str, Any]) -> dict[str, Any]:
    """The system variables a set of plain-word options comes down to.

    Pure, so the whole translation is checked without AutoCAD: every key of the
    answer is in DRAWING_VARIABLES, and the one place a scale turns into
    DIMSCALE, LTSCALE and CANNOSCALE lives here.

    Raises ValueError, naming the option, for anything it cannot translate.
    """
    out: dict[str, Any] = {}

    if wanted.get("units") is not None:
        code = unit_code(wanted["units"])
        out["INSUNITS"] = code
        # A metric drawing wants the metric linetype and hatch files, which is
        # what MEASUREMENT selects; nothing else here depends on it.
        if wanted.get("metric") is None:
            out["MEASUREMENT"] = 1 if code in METRIC_UNITS else 0
    if wanted.get("metric") is not None:
        out["MEASUREMENT"] = 1 if wanted["metric"] else 0

    if wanted.get("linear_format") is not None:
        key = str(wanted["linear_format"]).strip().lower()
        if key not in LINEAR_FORMATS:
            raise ValueError(
                f"'{wanted['linear_format']}' is not a linear format. Use one of: "
                + ", ".join(sorted(LINEAR_FORMATS))
            )
        out["LUNITS"] = LINEAR_FORMATS[key]
    if wanted.get("linear_precision") is not None:
        out["LUPREC"] = _in_range(wanted["linear_precision"], 0, 8, "linear_precision")
    if wanted.get("angle_format") is not None:
        key = str(wanted["angle_format"]).strip().lower()
        if key not in ANGLE_FORMATS:
            raise ValueError(
                f"'{wanted['angle_format']}' is not an angle format. Use one of: "
                + ", ".join(sorted(ANGLE_FORMATS))
            )
        out["AUNITS"] = ANGLE_FORMATS[key]
    if wanted.get("angle_precision") is not None:
        out["AUPREC"] = _in_range(wanted["angle_precision"], 0, 8, "angle_precision")

    if wanted.get("scale") is not None:
        ratio = plan.parse_typed_scale(wanted["scale"])
        factor = 1.0 / ratio
        out["DIMSCALE"] = factor
        out["CANNOSCALE"] = plan.scale_text(ratio)
        # LTSCALE at the drawing scale factor is the rule of thumb that makes
        # dashes read on the sheet; a drawing already using PSLTSCALE may not
        # want it, hence the switch.
        if wanted.get("ltscale_from_scale", True):
            out["LTSCALE"] = factor
        if wanted.get("paper_text_height") is not None:
            out["TEXTSIZE"] = plan.text_height(wanted["paper_text_height"], ratio)
    elif wanted.get("paper_text_height") is not None:
        raise ValueError("paper_text_height needs the drawing scale as well, e.g. scale='1:50'.")

    for option, variable in (
        ("dimscale", "DIMSCALE"),
        ("ltscale", "LTSCALE"),
        ("celtscale", "CELTSCALE"),
        ("text_size", "TEXTSIZE"),
        ("point_size", "PDSIZE"),
        ("elevation", "ELEVATION"),
        ("thickness", "THICKNESS"),
    ):
        if wanted.get(option) is not None:
            out[variable] = float(wanted[option])

    if wanted.get("psltscale") is not None:
        out["PSLTSCALE"] = 1 if wanted["psltscale"] else 0
    if wanted.get("msltscale") is not None:
        out["MSLTSCALE"] = 1 if wanted["msltscale"] else 0
    if wanted.get("associative_dimensions") is not None:
        out["DIMASSOC"] = 2 if wanted["associative_dimensions"] else 1
    if wanted.get("lineweight_display") is not None:
        out["LWDISPLAY"] = 1 if wanted["lineweight_display"] else 0
    if wanted.get("fill") is not None:
        out["FILLMODE"] = 1 if wanted["fill"] else 0
    if wanted.get("mirror_text") is not None:
        out["MIRRTEXT"] = 1 if wanted["mirror_text"] else 0
    if wanted.get("ucs_icon") is not None:
        out["UCSICON"] = 1 if wanted["ucs_icon"] else 0
    if wanted.get("attribute_dialog") is not None:
        out["ATTDIA"] = 1 if wanted["attribute_dialog"] else 0

    if wanted.get("osnaps") is not None:
        out["OSMODE"] = osnap_bits(list(wanted["osnaps"]))
    if wanted.get("point_style") is not None:
        out["PDMODE"] = point_mode(wanted["point_style"])

    if wanted.get("limits") is not None:
        limits = wanted["limits"]
        if len(limits) != 2 or len(limits[0]) < 2 or len(limits[1]) < 2:
            raise ValueError("limits must be [[min x, min y], [max x, max y]].")
        out["LIMMIN"] = (float(limits[0][0]), float(limits[0][1]))
        out["LIMMAX"] = (float(limits[1][0]), float(limits[1][1]))

    stray = sorted(set(out) - set(DRAWING_VARIABLES))
    if stray:  # pragma: no cover - a guard on this file, not on the caller
        raise ValueError(f"not in the allowed list: {', '.join(stray)}")
    return out


def _in_range(value: Any, low: int, high: int, name: str) -> int:
    number = int(value)
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {number}.")
    return number


# The DIM variables a dimension style option writes. Friendly name -> variable.
DIM_OPTIONS: dict[str, str] = {
    "scale": "DIMSCALE",
    "text_height": "DIMTXT",
    "text_style": "DIMTXSTY",
    "arrow_size": "DIMASZ",
    "arrow_block": "DIMBLK",
    "precision": "DIMDEC",
    "angle_precision": "DIMADEC",
    "units_factor": "DIMLFAC",
    "unit_format": "DIMLUNIT",
    "decimal_separator": "DIMDSEP",
    "suppress_zeros": "DIMZIN",
    "text_gap": "DIMGAP",
    "text_above_line": "DIMTAD",
    "extension_beyond_dim_line": "DIMEXE",
    "extension_line_offset": "DIMEXO",
    "tick_size": "DIMTSZ",
    "text_colour": "DIMCLRT",
    "line_colour": "DIMCLRD",
    "extension_colour": "DIMCLRE",
    "round_to": "DIMRND",
    "text_inside": "DIMTIX",
    "force_line_inside": "DIMTOFL",
}

# The ones AutoCAD holds as whole numbers. SetVariable refuses a decimal for
# them, so 0.0 for DIMDEC fails where 0 lands.
WHOLE_DIM_OPTIONS = frozenset(
    {"precision", "angle_precision", "unit_format", "suppress_zeros",
     "text_colour", "line_colour", "extension_colour"}
)

# The arrow variables read back empty for AutoCAD's own closed-filled arrow,
# and a single period is how that arrow is set again.
DEFAULT_ARROW_VARIABLES = frozenset({"DIMBLK", "DIMBLK1", "DIMBLK2", "DIMLDRBLK"})


def plan_dim_style(options: dict[str, Any]) -> dict[str, Any]:
    """The DIM variables one dimension style's options come down to.

    ``variables`` carries raw DIM names for anything the friendly list does not
    cover; nothing outside the DIM family is accepted, so this stays a
    dimension tool rather than a way into every system variable.
    """
    out: dict[str, Any] = {}
    for option, variable in DIM_OPTIONS.items():
        value = options.get(option)
        if value is None:
            continue
        if option == "text_above_line":
            out[variable] = 1 if value else 0
        elif option in ("text_inside", "force_line_inside"):
            out[variable] = 1 if value else 0
        elif option == "decimal_separator":
            text = str(value)
            if len(text) != 1:
                raise ValueError("decimal_separator must be a single character, e.g. '.' or ','.")
            out[variable] = text
        elif option in ("text_style", "arrow_block"):
            out[variable] = str(value)
        elif option in WHOLE_DIM_OPTIONS:
            number = float(value)
            if not number.is_integer():
                raise ValueError(f"{option} must be a whole number, got {value}.")
            out[variable] = int(number)
        else:
            out[variable] = float(value)

    for name, value in (options.get("variables") or {}).items():
        key = str(name).strip().upper()
        if not key.startswith("DIM"):
            raise ValueError(
                f"'{name}' is not a dimension variable. Only DIM... names belong in "
                "'variables'; use autocad_drawing_setup for the rest of the drawing."
            )
        out[key] = value
    return out


# ---------------------------------------------------------------------------
# The AutoCAD side
# ---------------------------------------------------------------------------


def _read_variable(doc: Any, name: str) -> Any:
    try:
        value = doc.GetVariable(name)
    except BaseException:  # noqa: BLE001 - not every release has every variable
        return None
    # Text first: a string is iterable too, and CANNOSCALE '1:10' or DIMTXSTY
    # 'Standard' must not be taken for a point.
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, int):
        return value
    try:
        return [round(float(v), 6) for v in value]
    except (TypeError, ValueError):
        return str(value)


@mcp.tool(name="autocad_drawing_setup", **tool_meta("Set Up The Drawing"))
@tool_errors
async def autocad_drawing_setup(
    units: Annotated[str | int | None, Field(default=None, description="Drawing units: 'millimeters', 'meters', 'inches', 'feet', or an INSUNITS code. Also sets MEASUREMENT so metric linetype and hatch files are used.")] = None,
    scale: Annotated[str | float | None, Field(default=None, description="The drawing scale, e.g. '1:50'. Sets DIMSCALE and the annotation scale, and LTSCALE unless you turn that off — the one setting everything else hangs off.")] = None,
    ltscale_from_scale: Annotated[bool, Field(default=True, description="With 'scale', also set LTSCALE to the scale factor so dashes read on the sheet. Turn off for a drawing that relies on PSLTSCALE.")] = True,
    paper_text_height: Annotated[float | None, Field(default=None, gt=0, description="Text height in millimetres as it should plot, e.g. 2.5. With 'scale' this sets TEXTSIZE to the model height (2.5 at 1:50 -> 125).")] = None,
    linear_format: Annotated[str | None, Field(default=None, description="'decimal' (metric), 'architectural' or 'engineering' (feet and inches), 'fractional', 'scientific'.")] = None,
    linear_precision: Annotated[int | None, Field(default=None, ge=0, le=8, description="Decimal places shown for lengths.")] = None,
    angle_format: Annotated[str | None, Field(default=None, description="'decimal', 'dms', 'grads', 'radians' or 'surveyor'.")] = None,
    angle_precision: Annotated[int | None, Field(default=None, ge=0, le=8, description="Decimal places shown for angles.")] = None,
    osnaps: Annotated[list[str] | None, Field(default=None, description="Running object snaps, e.g. ['endpoint','midpoint','intersection','perpendicular']. Use ['none'] for none, ['all'] for all.")] = None,
    point_style: Annotated[str | None, Field(default=None, description="How points are drawn: 'dot', 'cross', 'x', 'tick', 'circle_x', 'square_circle_x', ...")] = None,
    point_size: Annotated[float | None, Field(default=None, description="PDSIZE: point size. Positive is in drawing units, negative is a percentage of the screen.")] = None,
    dimscale: Annotated[float | None, Field(default=None, gt=0, description="DIMSCALE on its own, when it differs from the drawing scale.")] = None,
    ltscale: Annotated[float | None, Field(default=None, gt=0, description="LTSCALE on its own.")] = None,
    psltscale: Annotated[bool | None, Field(default=None, description="Scale linetypes to paper space, so dashes look the same in every viewport.")] = None,
    msltscale: Annotated[bool | None, Field(default=None, description="Scale linetypes in model space by the annotation scale.")] = None,
    associative_dimensions: Annotated[bool | None, Field(default=None, description="Dimensions follow the geometry they measure (DIMASSOC).")] = None,
    lineweight_display: Annotated[bool | None, Field(default=None, description="Show lineweights on screen.")] = None,
    limits: Annotated[list[list[float]] | None, Field(default=None, description="Drawing limits as [[min x, min y], [max x, max y]].")] = None,
    metric: Annotated[bool | None, Field(default=None, description="MEASUREMENT: metric (true) or imperial (false) linetype and hatch files. Normally follows 'units'.")] = None,
    fill: Annotated[bool | None, Field(default=None, description="FILLMODE: show solid fills and wide polylines filled.")] = None,
    mirror_text: Annotated[bool | None, Field(default=None, description="MIRRTEXT: whether mirroring also reverses text. Normally off.")] = None,
    ucs_icon: Annotated[bool | None, Field(default=None, description="Show the UCS icon — worth having on when a UCS is set.")] = None,
    attribute_dialog: Annotated[bool | None, Field(default=None, description="ATTDIA: ask for block attributes in a dialog. Turn off for scripted inserts.")] = None,
    dry_run: Annotated[bool, Field(default=False, description="Report what would change and write nothing.")] = False,
) -> str:
    """Set the drawing up the way a draftsman does before starting: units, scale, snaps, precision.

    Give the drawing scale once and the settings that hang off it follow —
    DIMSCALE, the annotation scale, LTSCALE, and the model text height for a
    paper height. Only the options you pass are touched.

    This writes from a fixed list of drafting system variables and nothing
    else. Every one comes back with its old value beside its new one; dry_run
    shows the whole plan and writes nothing.

    One undo step.

    Args:
        See each option's own description. All are optional.
        dry_run (bool): report the plan, change nothing.

    Returns:
        str: JSON: {
          "dry_run": bool,
          "changed": [{"variable", "from", "to"}],
          "unchanged": [str],
          "failed": [{"variable", "to", "reason"}],
          "osnaps_now": [str],
          "scale": "1:50" | null
        }

    Examples:
        - Use when: starting a drawing — units='millimeters', scale='1:50',
          paper_text_height=2.5, osnaps=['endpoint','midpoint','intersection'].
        - Use when: dimensions come out tiny — the drawing scale was never set.
          One scale sets DIMSCALE, LTSCALE, CANNOSCALE and the text height
          together, so they cannot disagree.
        - Use when: "set DIMSCALE and LTSCALE for 1:50" — scale='1:50' does
          both, and needs only the Changes padlock.
        - Use when: dashed lines look solid — scale sets LTSCALE too.
        - Don't use when: you need a variable outside the drafting list; that
          is autocad_set_variable, which needs the Admin padlock.

    Error Handling:
        - An unknown unit, snap, format or point style is named, with the
          values that are accepted, before anything is written.
        - A variable this AutoCAD will not accept is reported in "failed"; the
          rest of the plan still lands.
    """
    try:
        wanted = plan_settings(
            {
                "units": units, "scale": scale, "ltscale_from_scale": ltscale_from_scale,
                "paper_text_height": paper_text_height, "linear_format": linear_format,
                "linear_precision": linear_precision, "angle_format": angle_format,
                "angle_precision": angle_precision, "osnaps": osnaps,
                "point_style": point_style, "point_size": point_size,
                "dimscale": dimscale, "ltscale": ltscale, "psltscale": psltscale,
                "msltscale": msltscale, "associative_dimensions": associative_dimensions,
                "lineweight_display": lineweight_display, "limits": limits,
                "metric": metric, "fill": fill, "mirror_text": mirror_text,
                "ucs_icon": ucs_icon, "attribute_dialog": attribute_dialog,
            }
        )
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    if not wanted:
        raise AutocadError(
            "Nothing to set. Pass at least one setting — units, scale, osnaps, "
            "linear_precision and so on."
        )

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        changed, unchanged, failed = [], [], []

        def apply() -> None:
            for variable, value in wanted.items():
                before = _read_variable(doc, variable)
                after = list(value) if isinstance(value, tuple) else value
                if _same(before, after):
                    unchanged.append(variable)
                    continue
                if dry_run:
                    changed.append({"variable": variable, "from": before, "to": after})
                    continue
                try:
                    # A point (LIMMIN, LIMMAX) goes as an array of doubles: a plain
                    # Python pair crosses COM as an array of variants.
                    doc.SetVariable(variable, double_array(value) if isinstance(value, tuple) else value)
                except BaseException as exc:  # noqa: BLE001 - one refusal, not the batch
                    failed.append({"variable": variable, "to": after, "reason": com_message(exc)})
                    continue
                changed.append({"variable": variable, "from": before, "to": _read_variable(doc, variable)})

        def nothing_differs() -> bool:
            return all(
                _same(_read_variable(doc, variable), list(value) if isinstance(value, tuple) else value)
                for variable, value in wanted.items()
            )

        if dry_run or nothing_differs():
            apply()  # writes nothing: no undo step, empty or not (D-62)
        else:
            with undo_mark(doc):
                apply()

        result: dict[str, Any] = {
            "dry_run": dry_run,
            "changed": changed,
            "unchanged": sorted(unchanged),
            "failed": failed,
        }
        if not dry_run:
            result.update(before_after([{"variable": row["variable"], "property": "value", "from": row["from"],
                                         "to": row["to"]} for row in changed]))  # fmt: skip
        current = _read_variable(doc, "OSMODE")
        if isinstance(current, int):
            result["osnaps_now"] = osnap_names(current)
        if scale is not None:
            result["scale"] = plan.scale_text(plan.parse_scale(scale))
        return result

    return dumps(await run(work))


def _same(before: Any, after: Any) -> bool:
    """Whether a variable already holds the value asked for."""
    if isinstance(before, list) and isinstance(after, list):
        return len(before) == len(after) and all(
            abs(float(a) - float(b)) < 1e-9 for a, b in zip(before, after, strict=False)
        )
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return abs(float(before) - float(after)) < 1e-9
    return str(before).strip().lower() == str(after).strip().lower()


@mcp.tool(name="autocad_create_styles", **tool_meta("Create Text And Dimension Styles"))
@tool_errors
async def autocad_create_styles(
    text_styles: Annotated[
        list[dict[str, Any]] | None,
        Field(
            default=None,
            description=(
                "Text styles to create or update. Each is an object:\n"
                '{"name": "ROMANS-2.5", "font": "romans.shx", "height": 0, '
                '"width_factor": 0.8, "oblique": 0, "current": true}\n'
                "'font' takes an .shx file name or a Windows typeface such as "
                "'Arial'. 'height' of 0 leaves the height to each piece of "
                "text, which is what a drafter normally wants."
            ),
        ),
    ] = None,
    dim_styles: Annotated[
        list[dict[str, Any]] | None,
        Field(
            default=None,
            description=(
                "Dimension styles to create or update. Each is an object:\n"
                '{"name": "MECH-50", "scale": 50, "text_height": 2.5, '
                '"text_style": "ROMANS-2.5", "arrow_size": 2.5, "precision": 0, '
                '"text_above_line": true, "suppress_zeros": 8, "current": true}\n'
                'Anything not covered goes in "variables": {"DIMTIH": 0}, '
                "which takes DIM... names only."
            ),
        ),
    ] = None,
    replace: Annotated[
        bool,
        Field(default=False, description="Update a style of the same name that already exists, instead of refusing."),
    ] = False,
) -> str:
    """Create the text and dimension styles a drawing needs, with real values.

    A dimension style is built the way AutoCAD's own API requires: the DIM
    variables are set, the style is added, the style copies them off the
    document, and the drawing's variables are then put back — so the style
    holds the settings and the drawing is left as it was.

    Multileader styles have no Automation API, so they are not created here;
    make one in AutoCAD's Multileader Style Manager, or bring one in from your
    standards drawing with autocad_import_from_drawing.

    One undo step.

    Args:
        text_styles (Optional[list[dict]]): styles to create; see the field.
        dim_styles (Optional[list[dict]]): styles to create; see the field.
        replace (bool): update a style of the same name.

    Returns:
        str: JSON: {
          "text_styles": [{"name", "created", "font", "height", "current",
                           "notes": [str]}],
          "dim_styles": [{"name", "created", "variables": {...}, "current",
                          "notes": [str]}]
        }

    Examples:
        - Use when: "make our ROMANS text style and a 1:50 dim style".
        - Use when: dimension text is the wrong size on every sheet.
        - Don't use when: your office standards drawing already has them —
          autocad_import_from_drawing copies them across as they are.

    Error Handling:
        - A style name already in the drawing is refused unless replace=true.
        - A font AutoCAD cannot find is reported against that style; the other
          styles are still made.
        - The drawing's own DIM variables are put back even if a style fails.
    """
    if not text_styles and not dim_styles:
        raise AutocadError("Give text_styles, dim_styles, or both.")
    for entry in list(text_styles or []) + list(dim_styles or []):
        if not isinstance(entry, dict) or not str(entry.get("name", "")).strip():
            raise AutocadError(f"Every style needs a 'name'. Got: {entry!r}")
    plans = []
    for entry in dim_styles or []:
        try:
            plans.append((validate_name(str(entry["name"]), "dimension style"), plan_dim_style(entry), entry))
        except ValueError as exc:
            raise AutocadError(f"Dimension style '{entry.get('name')}': {exc}") from exc

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        result: dict[str, Any] = {"text_styles": [], "dim_styles": []}

        with undo_mark(doc):
            for entry in text_styles or []:
                result["text_styles"].append(_make_text_style(doc, entry, replace))
            for name, variables, entry in plans:
                result["dim_styles"].append(_make_dim_style(doc, name, variables, entry, replace))
        return result

    return dumps(await run(work))


def _existing(collection: Any, name: str) -> Any:
    for i in range(int(collection.Count)):
        item = collection.Item(i)
        if str(item.Name).strip().lower() == name.strip().lower():
            return item
    return None


def _make_text_style(doc: Any, entry: dict[str, Any], replace: bool) -> dict[str, Any]:
    """Create or update one text style. Never raises: the row carries the outcome."""
    try:
        name = validate_name(str(entry["name"]), "text style")
    except AutocadError as exc:
        return {"name": entry.get("name"), "created": False, "notes": [str(exc)]}
    notes: list[str] = []
    style = _existing(doc.TextStyles, name)
    if style is not None and not replace:
        return {
            "name": name,
            "created": False,
            "notes": [f"'{name}' is already in this drawing. Pass replace=true to update it."],
        }
    created = style is None
    if created:
        try:
            style = doc.TextStyles.Add(name)
        except BaseException as exc:  # noqa: BLE001
            return {"name": name, "created": False, "notes": [f"AutoCAD would not add it: {com_message(exc)}"]}

    font = str(entry.get("font", "") or "").strip()
    if font:
        # An .shx is a font file; anything else is a Windows typeface, and the
        # docs say to set the file and the typeface together.
        if font.lower().endswith((".shx", ".ttf")):
            try:
                style.fontFile = font
            except BaseException as exc:  # noqa: BLE001
                notes.append(f"the font '{font}' was not accepted ({com_message(exc)}); the style keeps its own")
        else:
            try:
                style.SetFont(font, False, False, 0, 0)
            except BaseException as exc:  # noqa: BLE001
                notes.append(f"the typeface '{font}' was not accepted ({com_message(exc)})")

    for key, prop in (("height", "Height"), ("width_factor", "Width"), ("oblique", "ObliqueAngle")):
        if entry.get(key) is None:
            continue
        value = float(entry[key])
        if key == "oblique":
            value = rad(value) or 0.0
        try:
            setattr(style, prop, value)
        except BaseException as exc:  # noqa: BLE001
            notes.append(f"{key} was not accepted ({com_message(exc)})")

    if entry.get("big_font"):
        try:
            style.BigFontFile = str(entry["big_font"])
        except BaseException as exc:  # noqa: BLE001
            notes.append(f"the big font was not accepted ({com_message(exc)})")

    current = False
    if entry.get("current"):
        try:
            doc.ActiveTextStyle = style
            current = True
        except BaseException as exc:  # noqa: BLE001
            notes.append(f"it could not be made current ({com_message(exc)})")

    row: dict[str, Any] = {
        "name": str(style.Name),
        "created": created,
        "current": current,
        "font": str(_safe(lambda: style.fontFile, "")),
        "height": _safe(lambda: round(float(style.Height), 6), None),
        "width_factor": _safe(lambda: round(float(style.Width), 6), None),
    }
    if notes:
        row["notes"] = notes
    return row


def _safe(getter, default=None):
    try:
        return getter()
    except BaseException:  # noqa: BLE001
        return default


def _make_dim_style(
    doc: Any, name: str, variables: dict[str, Any], entry: dict[str, Any], replace: bool
) -> dict[str, Any]:
    """Create or update one dimension style, putting the drawing's DIM variables back.

    AutoCAD has no "set this style's properties" call. Changing a DIM variable
    makes a drawing override on the *active* style, and ``CopyFrom(document)``
    is what folds those overrides into a style. So: remember, set, add, copy,
    restore.
    """
    notes: list[str] = []
    style = _existing(doc.DimStyles, name)
    if style is not None and not replace:
        return {
            "name": name,
            "created": False,
            "notes": [f"'{name}' is already in this drawing. Pass replace=true to update it."],
        }
    created = style is None

    before = {key: _read_variable(doc, key) for key in variables}
    applied: dict[str, Any] = {}
    try:
        for key, value in variables.items():
            try:
                doc.SetVariable(key, value)
                applied[key] = value
            except BaseException as exc:  # noqa: BLE001
                notes.append(f"{key} was not accepted ({com_message(exc)})")
        if created:
            try:
                style = doc.DimStyles.Add(name)
            except BaseException as exc:  # noqa: BLE001
                return {"name": name, "created": False, "notes": [f"AutoCAD would not add it: {com_message(exc)}"]}
        try:
            style.CopyFrom(doc)
        except BaseException as exc:  # noqa: BLE001
            notes.append(
                f"the settings could not be copied into the style ({com_message(exc)}); it "
                "exists but may hold the drawing's defaults"
            )
    finally:
        # The drawing is left as it was found, whatever happened above.
        for key, value in before.items():
            if value is None:
                continue
            if key in DEFAULT_ARROW_VARIABLES and value == "":
                value = "."
            try:
                doc.SetVariable(key, value)
            except BaseException:  # noqa: BLE001 - reported below if it matters
                notes.append(f"{key} could not be put back to {value}")

    current = False
    if entry.get("current"):
        try:
            doc.ActiveDimStyle = style
            current = True
        except BaseException as exc:  # noqa: BLE001
            notes.append(f"it could not be made current ({com_message(exc)})")

    row: dict[str, Any] = {
        "name": str(_safe(lambda: style.Name, name)),
        "created": created,
        "current": current,
        "variables": applied,
    }
    if notes:
        row["notes"] = notes
    return row
