"""Several sheets of the open drawing in one PDF, done by the Heron plug-in.

COM can plot one layout to one file; a multi-sheet PDF needs AutoCAD's
publisher, which only the plug-in can reach (D-40). The idea and the DSD
settings come from Autodesk's BatchPublish sample (docs/11-adn-repos-study.md,
item 1); the code is written fresh.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from pydantic import Field

from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from ._shared import in_plugin


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path.strip().strip('"')))


@mcp.tool(name="autocad_publish_pdf", **tool_meta("Publish Sheets To One PDF"))
@tool_errors
async def autocad_publish_pdf(
    path: Annotated[str, Field(min_length=1, description="Full path of the PDF to write, e.g. 'D:\\\\Issue\\\\M-100 set.pdf'.")],
    layouts: Annotated[
        list[str] | None,
        Field(default=None, description="The layout (sheet) names to include, as autocad_list_layouts shows them. Omit for every sheet, in tab order."),
    ] = None,
    include_model: Annotated[bool, Field(default=False, description="Put the Model tab in as the first page when no layouts are named.")] = False,
    overwrite: Annotated[bool, Field(default=False, description="Replace a PDF already at that path.")] = False,
) -> str:
    """Publish the drawing's sheets to ONE multi-page PDF, in tab order (AutoCAD's PUBLISH).

    Each layout is plotted with its own page setup - paper, scale, plot style
    - as PUBLISH does, and sheets never opened are set up first so they do
    not come out blank. The PDF is made from the drawing as last saved, so
    save first: a drawing with unsaved changes is refused rather than
    published out of date.

    Nothing in the drawing changes. Writes a file, so it needs the Changes and
    Publish padlocks.

    Args:
        path (str): full path of the PDF.
        layouts (Optional[list[str]]): sheets to include; omit for all.
        include_model (bool): add the Model tab first.
        overwrite (bool): replace an existing PDF.

    Returns:
        str: JSON: {"published": true, "path": str, "count": int,
             "sheets": [str]}

    Examples:
        - Use when: "publish all the sheets to one PDF for issue".
        - Use when: "make a PDF set of M-101 to M-104" — layouts=['M-101',
          'M-102', 'M-103', 'M-104'].
        - Use when: "batch plot the layouts into a single PDF".
        - Don't use when: you want one area or one layout fitted to a sheet -
          autocad_export with a .pdf path.
        - Don't use when: you only need a picture to check the drawing -
          autocad_preview.

    Error Handling:
        - A drawing never saved, or with unsaved changes, is refused: save it
          with autocad_save_drawing first.
        - A layout name that is not in the drawing is named, with the ones
          there are.
        - A PDF already at the path is refused unless overwrite=true.
        - Needs the Heron plug-in 1.3.0 or newer in AutoCAD.
    """
    target = os.path.abspath(_expand(path))
    if not target.lower().endswith(".pdf"):
        raise AutocadError(f"'{target}' does not end in .pdf.")
    folder = os.path.dirname(target)
    if not os.path.isdir(folder):
        raise AutocadError(f"The folder '{folder}' does not exist.")
    if os.path.exists(target) and not overwrite:
        raise AutocadError(f"'{target}' is already there. Give another name, or overwrite=true to replace it.")
    names = [name.strip() for name in (layouts or []) if name and name.strip()]

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        args = {
            "path": target,
            "layouts": names or None,
            "include_model": bool(include_model),
            "overwrite": bool(overwrite),
        }
        return in_plugin("publish_pdf", args, "Publishing sheets to one PDF", changes=False)

    result = await run(work)
    if not os.path.isfile(target):
        result["warning"] = (
            f"Heron in AutoCAD said it published, but no file is at '{target}' from here. "
            "Look in AutoCAD's publish log before publishing again."
        )
    return dumps(result)
