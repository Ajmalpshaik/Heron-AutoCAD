"""Write a custom hatch pattern (.pat) or linetype (.lin), and make AutoCAD use it.

The text comes from acad/patterns.py. The files go in Heron's own support folder
(%LOCALAPPDATA%\\Heron\\autocad\\support) unless a folder is given. A hatch
pattern is found by AutoCAD only on the support path, so that folder is added
to it once; a linetype is loaded straight into the drawing from its file.
Both write files, so both are Publish tools.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import patterns as pat
from ..core.connection import get_doc, run
from ..core.errors import AutocadError, com_message
from ..core.folders import heron_local
from ..core.registry import dumps, mcp, tool_errors, tool_meta


def support_folder() -> Path:
    """Heron's folder for the pattern and linetype files it writes."""
    return heron_local() / "support"


def _target(folder: str | None, name: str, ext: str) -> Path:
    # Whole, because the path goes on to AutoCAD, which would read a relative
    # one from its own folder, not the server's.
    base = Path(os.path.expandvars(os.path.expanduser(folder.strip().strip('"')))) if folder else support_folder()
    return (base / f"{name}{ext}").resolve()


def _write(path: Path, content: str, replace: bool) -> None:
    if path.exists() and not replace:
        raise AutocadError(f"'{path}' is already there. Pass replace=true to write over it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="ascii", newline="\r\n" if os.name == "nt" else "\n")


def _find(collection: Any, name: str) -> Any:
    wanted = name.strip().lower()
    for i in range(int(collection.Count)):
        item = collection.Item(i)
        if str(item.Name).strip().lower() == wanted:
            return item
    return None


def _named(collection: Any, name: str) -> bool:
    return _find(collection, name) is not None


def _on_support_path(doc: Any, folder: Path) -> bool:
    """Put folder on AutoCAD's support search path; True when it had to be added."""
    files = doc.Application.Preferences.Files
    current = str(files.SupportPath or "")
    entries = [e.strip().rstrip("\\/").lower() for e in current.split(";") if e.strip()]
    if str(folder).rstrip("\\/").lower() in entries:
        return False
    files.SupportPath = f"{current};{folder}" if current else str(folder)
    return True


@mcp.tool(name="autocad_create_hatch_pattern", **tool_meta("Create A Hatch Pattern File"))
@tool_errors
async def autocad_create_hatch_pattern(
    name: Annotated[str, Field(description="Pattern name, also the file name: letters, digits, '-' or '_', up to 31, e.g. 'CHW-INS'.")],
    preset: Annotated[
        Literal["lines", "cross", "custom"],
        Field(default="lines", description="'lines': one set of parallel lines; 'cross': two sets square to each other; 'custom': give 'families' yourself."),
    ] = "lines",
    angle: Annotated[float, Field(default=45.0, description="lines / cross: angle of the lines in degrees.")] = 45.0,
    spacing: Annotated[float, Field(default=3.0, gt=0, description="lines / cross: distance between the lines, at hatch scale 1 (mm on paper in a metric drawing).")] = 3.0,
    dashes: Annotated[list[float] | None, Field(default=None, description="lines / cross: make the lines dashed, e.g. [3, -1.5] = 3 dash, 1.5 gap. Up to six. Omit for solid lines.")] = None,
    families: Annotated[
        list[dict[str, Any]] | None,
        Field(default=None, description='custom: each family of lines as {"angle": 45, "origin": [0, 0], "offset": [0, 3], "dashes": [3, -1.5]} - offset is [slide along the line, spacing between lines].'),
    ] = None,
    description: Annotated[str, Field(default="", description="A short description shown in AutoCAD's pattern list.")] = "",
    folder: Annotated[str | None, Field(default=None, description="Folder to write NAME.pat into. Omit for Heron's own support folder.")] = None,
    add_to_support_path: Annotated[bool, Field(default=True, description="Add that folder to AutoCAD's support path (once), which is where the HATCH command and autocad_add_hatch look for custom patterns.")] = True,
    replace: Annotated[bool, Field(default=False, description="Write over a pattern file of the same name.")] = False,
    dry_run: Annotated[bool, Field(default=False, description="Show the file text and write nothing.")] = False,
) -> str:
    """Make a custom hatch pattern - a .pat file AutoCAD can hatch with.

    For a hatch acad.pat does not have: an insulation or sleeve pattern, an
    office-standard grid, a dashed fill. One NAME.pat per pattern, which is
    what AutoCAD needs for a custom pattern; then hatch with
    autocad_add_hatch(pattern='NAME').

    Writes a file, so it needs the Publish padlock as well as Changes.

    Args:
        name (str): pattern and file name.
        preset (str): lines, cross or custom.
        angle (float): lines / cross: degrees.
        spacing (float): lines / cross: line spacing at scale 1.
        dashes (Optional[list[float]]): dash, -gap, ... (0 is a dot).
        families (Optional[list[dict]]): custom: the families of lines.
        description (str): shown in AutoCAD's pattern list.
        folder (Optional[str]): where NAME.pat goes.
        add_to_support_path (bool): put that folder on the support path.
        replace (bool): write over an existing file.
        dry_run (bool): show the text, write nothing.

    Returns:
        str: JSON: {"file": str, "file_text": str, "support_path_added": bool,
             "hint": str}

    Examples:
        - Use when: "make a hatch of 45 degree lines 3 apart for the
          insulation" — preset='lines', angle=45, spacing=3.
        - Use when: "a 5 mm square grid hatch" — preset='cross', angle=0,
          spacing=5.
        - Don't use when: the pattern is a standard one (ANSI31, AR-CONC,
          EARTH...) — autocad_add_hatch uses those straight away.

    Error Handling:
        - Spacing 0, more than six dashes, a line over 80 characters or a name
          that cannot be a file name are refused before anything is written.
        - An existing file is not written over without replace=true.
    """
    try:
        clean = pat.check_name(name)
        content = pat.pat_text(clean, description, pat.hatch_families(preset, angle, spacing, dashes, families))
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    path = _target(folder, clean, ".pat")
    hint = (f"Hatch with it: autocad_add_hatch(pattern='{clean}'). Scale it there with 'scale' "
            "(at 1, the spacing is in drawing units).")
    if dry_run:
        return dumps({"dry_run": True, "file": str(path), "file_text": content, "hint": hint})
    _write(path, content, replace)

    added = False
    if add_to_support_path:
        def work() -> bool:
            try:
                return _on_support_path(get_doc(), path.parent)
            except BaseException as exc:  # noqa: BLE001
                raise AutocadError(
                    f"The pattern is written to '{path}', but AutoCAD would not take its folder onto "
                    f"the support path ({com_message(exc)}). Add it in OPTIONS > Files > Support File "
                    "Search Path."
                ) from exc

        added = await run(work)
    return dumps({"file": str(path), "file_text": content, "support_path_added": added, "hint": hint})


@mcp.tool(name="autocad_create_linetype", **tool_meta("Create A Linetype"))
@tool_errors
async def autocad_create_linetype(
    name: Annotated[str, Field(description="Linetype name, also the file name, e.g. 'CHWS'.")],
    text: Annotated[str | None, Field(default=None, description="A service line with its name in it, e.g. 'CHWS' for ---- CHWS ---- CHWS ----. Or give dashes.")] = None,
    dashes: Annotated[list[float] | None, Field(default=None, description="A plain line: dash, -gap, ... e.g. [12, -3] or [12, -3, 0, -3] for dash-dot. Up to 12. Or give text.")] = None,
    dash: Annotated[float, Field(default=12.0, gt=0, description="With text: the dash between the labels, as it plots (mm).")] = 12.0,
    gap: Annotated[float, Field(default=1.5, gt=0, description="With text: the clear space either side of the text.")] = 1.5,
    height: Annotated[float, Field(default=2.5, gt=0, description="With text: the text height as it plots.")] = 2.5,
    text_style: Annotated[str, Field(default="STANDARD", description="With text: a text style already in the drawing.")] = "STANDARD",
    text_width: Annotated[float | None, Field(default=None, gt=0, description="With text: the room the text needs, when the estimate (0.9 x height per letter) is tight or loose.")] = None,
    description: Annotated[str | None, Field(default=None, description="Shown in AutoCAD's linetype list, up to 47 characters. Omit for a sketch of the line.")] = None,
    folder: Annotated[str | None, Field(default=None, description="Folder to write NAME.lin into. Omit for Heron's own support folder.")] = None,
    load: Annotated[bool, Field(default=True, description="Load it into this drawing so it can be used straight away.")] = True,
    replace: Annotated[bool, Field(default=False, description="Write over a linetype file of the same name.")] = False,
    dry_run: Annotated[bool, Field(default=False, description="Show the file text and write nothing.")] = False,
) -> str:
    """Make a linetype - a plain dashed one, or a service line with its name in it.

    ---- CHWS ---- CHWS ---- for chilled water, HWS, CW, GAS, FIRE: the MEP
    convention, as a real linetype the modeller can put on a layer. Writes
    NAME.lin and loads it into the drawing.

    Sizes are as they plot when LTSCALE is the drawing scale factor, which
    autocad_drawing_setup(scale=...) sets.

    Writes a file, so it needs the Publish padlock as well as Changes.

    Args:
        name (str): linetype and file name.
        text (Optional[str]): the label in the line; or
        dashes (Optional[list[float]]): a plain dash pattern.
        dash / gap / height (float): with text: dash, clear space, text height.
        text_style (str): with text: a style in the drawing.
        text_width (Optional[float]): with text: room for the text.
        description (Optional[str]): shown in AutoCAD's list.
        folder (Optional[str]): where NAME.lin goes.
        load (bool): load it into this drawing.
        replace (bool): write over an existing file.
        dry_run (bool): show the text, write nothing.

    Returns:
        str: JSON: {"file": str, "file_text": str, "loaded": bool, "hint": str}

    Examples:
        - Use when: "make a CHWS linetype with the text in the line" —
          text='CHWS'.
        - Use when: "a dash-dot line, 12 dash, 3 gap" — dashes=[12, -3, 0, -3].
        - Don't use when: the linetype exists in acad.lin / acadiso.lin
          (HIDDEN, CENTER, DASHED...) — the draw tools load those themselves.

    Error Handling:
        - Text and dashes together, a quote in the text, a pattern that starts
          with a gap, more than 12 dashes, or a description over 47 characters
          are refused before anything is written.
        - A linetype already in the drawing, or a text style it lacks, is
          refused before the file is written.
    """
    if (text is None) == (dashes is None):
        raise AutocadError("Give either text (a service line with its name in it) or dashes, not both or neither.")
    def build(style_height: float | None = None) -> str:
        if text is not None:
            elements, sketch = pat.text_linetype(
                clean, text, dash, gap, height, text_style, text_width, style_height
            )
        else:
            elements = [float(d) for d in dashes or []]
            sketch = "".join("_" * 3 if d > 0 else ("." if d == 0 else " ") for d in elements)[:47]
        return pat.lin_text(clean, description if description is not None else sketch, elements)

    try:
        clean = pat.check_name(name, "linetype")
        content = build()
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    path = _target(folder, clean, ".lin")
    hint = f"Use it with linetype='{clean}' on a layer or a draw tool."
    if text is not None and not load:
        hint += (" Not loaded, so the text size assumes a style of height 0 (like STANDARD); "
                 "load it to have a fixed-height style's own height allowed for.")
    if dry_run:
        return dumps({"dry_run": True, "file": str(path), "file_text": content, "hint": hint})
    if not load:
        _write(path, content, replace)
        return dumps({"file": str(path), "file_text": content, "loaded": False, "hint": hint})

    def work() -> dict[str, Any]:
        doc = get_doc()
        if _named(doc.Linetypes, clean):
            raise AutocadError(
                f"This drawing already has a linetype called '{clean}'. Give the new one another "
                "name, or reload it in AutoCAD's LINETYPE dialog."
            )
        final = content
        if text is not None:
            style = _find(doc.TextStyles, text_style)
            if style is None:
                raise AutocadError(
                    f"This drawing has no text style called '{text_style}', which the linetype's text "
                    "needs. Use STANDARD, or make the style with autocad_create_styles first."
                )
            # A style with its own height makes S a multiplier, not the height.
            fixed = float(getattr(style, "Height", 0.0) or 0.0)
            if fixed > 0:
                final = build(fixed)
        _write(path, final, replace)
        try:
            doc.Linetypes.Load(clean, str(path))
        except BaseException as exc:  # noqa: BLE001
            raise AutocadError(
                f"The linetype is written to '{path}', but AutoCAD would not load it ({com_message(exc)})."
            ) from exc
        return {"file": str(path), "file_text": final, "loaded": True, "hint": hint}

    return dumps(await run(work))

