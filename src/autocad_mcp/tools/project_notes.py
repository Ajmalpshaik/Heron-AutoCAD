"""The modeller's answers, kept per project (D-53). See core/project_notes.py."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from ..core import project_notes
from ..core.connection import get_doc, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta


@mcp.tool(name="autocad_project_notes", **tool_meta("Remember Answers For This Project"))
@tool_errors
async def autocad_project_notes(
    action: Annotated[
        Literal["list", "keep", "forget"],
        Field(description="'list' the notes of this drawing's project, 'keep' one answer, or 'forget' one."),
    ] = "list",
    name: Annotated[
        str | None,
        Field(description="A short name: scale, standard, text_height, client, sheet_size, layer_standard..."),
    ] = None,
    value: Annotated[str | None, Field(description="For keep: the answer exactly as the modeller gave it, e.g. '1:50'.")] = None,
    said: Annotated[
        str | None,
        Field(description="For keep: the modeller's own words, so the next chat can see where it came from."),
    ] = None,
) -> str:
    """Keep the modeller's answers for this project, so the next chat does not ask again.

    A project is the folder the drawing is saved in: every drawing in that
    folder shares the notes, and another folder never sees them.
    autocad_status hands the notes to every chat. Keep ONLY what the modeller
    said: never a value you guessed or worked out. The notes are Heron's own
    file on this PC; nothing is written into the drawing.

    Args:
        action (str): list, keep or forget.
        name (str): the note.
        value (str): for keep.
        said (str): for keep, the modeller's words.

    Returns:
        str: JSON: {"project": str, "notes": {name: {"value", "said", "at"}}}

    Examples:
        - Use when: the modeller answers "the scale is 1:50 for this job" ->
          keep scale = 1:50.
        - Use when: "we use the client's layer standard here" -> keep
          layer_standard.
        - Use when: "what do you remember about this project?" -> list.
        - Don't use when: the value is your own estimate - ask the modeller first.
        - Don't use when: the answer belongs in the drawing (title block text) -
          autocad_set_attributes writes that.

    Error Handling:
        - An unsaved drawing has no project yet: it says to save it first, and
          keeps nothing.
    """

    def work() -> str:
        doc = get_doc()
        return str(doc.FullName) or str(doc.Name)

    drawing = await run(work)
    if action == "list":
        current = project_notes.read(drawing)
        if current is None:
            return dumps({"project": None, "notes": {}, "note": "This drawing is not saved yet: it has no project folder."})
        return dumps(current)
    if not name:
        raise AutocadError(f"'{action}' needs the note's name, e.g. scale.")
    if action == "keep" and not value:
        raise AutocadError("'keep' needs the value the modeller gave.")
    try:
        result: dict[str, Any] = project_notes.write(drawing, name, value if action == "keep" else None, said or "")
    except ValueError as exc:
        raise AutocadError(str(exc)) from None
    return dumps(result)
