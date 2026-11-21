"""Several sheets in one PDF, done by the Heron plug-in: of the open drawing,
or of a folder or a list of drawings (#67, D-91).

COM can plot one layout to one file; a multi-sheet PDF needs AutoCAD's
publisher, which only the plug-in can reach (D-40). The idea and the DSD
settings come from Autodesk's BatchPublish sample (docs/11-adn-repos-study.md,
item 1); the code is written fresh.

For several drawings the list is made here (acad/publish_files.py): only
.dwg files that are there, each once, a folder sorted the way a drafter reads
it. A drawing of the set open in AutoCAD with unsaved changes is refused here,
over COM, before the plug-in is asked; the plug-in then reads every drawing
for its layouts and refuses one whose xrefs cannot be found.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

from pydantic import Field

from ..acad.publish_files import pdf_drawings, unsaved_among
from ..core.connection import get_app, get_doc, require_idle, run
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
    include_model: Annotated[bool, Field(default=False, description="Put the Model tab in as the first page when no layouts are named (of each drawing, with folder or drawings).")] = False,
    overwrite: Annotated[bool, Field(default=False, description="Replace a PDF already at that path.")] = False,
    folder: Annotated[
        str | None,
        Field(default=None, description="Publish every .dwg in this folder instead of the open drawing, sorted by name the way a drafter reads it (M-2 before M-10). Each must be saved and have its xrefs."),
    ] = None,
    drawings: Annotated[
        list[str] | None,
        Field(default=None, description="Publish these drawings, by full .dwg path, in this order, instead of the open drawing. Each must be saved and have its xrefs."),
    ] = None,
    recursive: Annotated[bool, Field(default=False, description="With folder: take the .dwg files in its sub-folders too.")] = False,
) -> str:
    """Publish sheets to ONE multi-page PDF, in tab order (AutoCAD's PUBLISH): of the open drawing, or of a folder or a list of drawings.

    Each layout is plotted with its own page setup - paper, scale, plot style
    - as PUBLISH does, and sheets never opened are set up first so they do
    not come out blank. The PDF is made from the drawings as last saved, so
    save first: a drawing with unsaved changes is refused rather than
    published out of date.

    With folder or drawings, every drawing's sheets go in, drawing by drawing
    (layouts then picks the same-named sheets from each). Every drawing is
    checked first: one open in AutoCAD with unsaved changes, or one that
    attaches an xref whose file cannot be found, is refused by name and
    nothing is published, so a sheet never comes out with its background
    missing. Unloaded xrefs are left as they are.

    Nothing in any drawing changes. Writes a file, so it needs the Changes and
    Publish padlocks.

    Args:
        path (str): full path of the PDF.
        layouts (Optional[list[str]]): sheets to include; omit for all.
        include_model (bool): add the Model tab first.
        overwrite (bool): replace an existing PDF.
        folder (Optional[str]): a folder of drawings to publish.
        drawings (Optional[list[str]]): drawings to publish, in order.
        recursive (bool): with folder, its sub-folders too.

    Returns:
        str: JSON: {"published": true, "path": str, "count": int,
             "sheets": [str], "drawings": int,
             "pages": [{"drawing": str, "layout": str}]}  # pages and drawings with folder / drawings

    Examples:
        - Use when: "publish all the sheets to one PDF for issue".
        - Use when: "make a PDF set of M-101 to M-104" — layouts=['M-101',
          'M-102', 'M-103', 'M-104'].
        - Use when: "batch plot the layouts into a single PDF".
        - Use when: "one PDF of every drawing in the Issue folder" —
          folder='D:\\Job\\Issue'.
        - Use when: "a PDF set of these five drawings" — drawings=[...].
        - Don't use when: you want one area or one layout fitted to a sheet -
          autocad_export with a .pdf path.
        - Don't use when: you only need a picture to check the drawing -
          autocad_preview.

    Error Handling:
        - A drawing never saved, or with unsaved changes, is refused: save it
          with autocad_save_drawing first.
        - With folder / drawings: a file that is not there, not a .dwg, open
          with unsaved changes, or with an xref that cannot be found, is named,
          and nothing is published.
        - A layout name that is not in the drawing(s) is named.
        - A PDF already at the path is refused unless overwrite=true.
        - Needs the Heron plug-in 1.3.0 or newer in AutoCAD; folder and
          drawings need the plug-in built from #67.
    """
    target = os.path.abspath(_expand(path))
    if not target.lower().endswith(".pdf"):
        raise AutocadError(f"'{target}' does not end in .pdf.")
    pdf_folder = os.path.dirname(target)
    if not os.path.isdir(pdf_folder):
        raise AutocadError(f"The folder '{pdf_folder}' does not exist.")
    if os.path.exists(target) and not overwrite:
        raise AutocadError(f"'{target}' is already there. Give another name, or overwrite=true to replace it.")
    names = [name.strip() for name in (layouts or []) if name and name.strip()]
    files: list[str] | None = None
    if folder or drawings:
        try:
            files = pdf_drawings(folder, drawings, recursive)
        except ValueError as exc:
            raise AutocadError(f"Nothing was published: {exc}.") from None
        if any(os.path.normcase(f) == os.path.normcase(target) for f in files):
            raise AutocadError("The PDF path is one of the drawings.")

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        if files:
            unsaved = unsaved_among(files, _open_drawings())
            if unsaved:
                raise AutocadError(
                    "Nothing was published: "
                    + ", ".join(f"'{name}'" for name in unsaved)
                    + " is open in AutoCAD with unsaved changes, and the PDF is made from the "
                    "saved files. Save them first (autocad_save_drawing), then publish."
                )
        args = {
            "path": target,
            "layouts": names or None,
            "include_model": bool(include_model),
            "overwrite": bool(overwrite),
            "drawings": files,
        }
        return in_plugin("publish_pdf", args, "Publishing sheets to one PDF", changes=False)

    result = await run(work)
    if not os.path.isfile(target):
        result["warning"] = (
            f"Heron in AutoCAD said it published, but no file is at '{target}' from here. "
            "Look in AutoCAD's publish log before publishing again."
        )
    return dumps(result)


def _open_drawings() -> list[tuple[str, bool]]:
    """(full path, saved) for every drawing open in AutoCAD; a read, so a busy AutoCAD is retried."""
    app = get_app()
    found = []
    for index in range(int(app.Documents.Count)):
        item = app.Documents.Item(index)
        name, full = str(item.Name), str(item.FullName)
        found.append((full if full != name else "", bool(item.Saved)))
    return found
