"""PDF Import (#113, D-106): one page of a vendor's or consultant's PDF as lines in the drawing.

There is no API for it (``acad/pdf_import.py`` says why), so the tool types
``-PDFIMPORT`` with every answer in one AutoLISP form, through the same sender
as autocad_run_lisp (``advanced.send_lisp_pieces``): object snaps off, a
command left open cancelled and named, one undo step. The release is checked
first, the variables it needs are set for the call and put back, and what came
in is counted, boxed and moved onto the layer asked for.
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated, Any, Literal

from pydantic import Field

from ..acad import pdf_import as pdf
from ..acad.coords import as_vec3
from ..acad.tables import validate_name
from ..core.connection import get_doc, require_idle, run
from ..core.errors import AutocadError, is_retryable, raise_if_busy
from ..core.registry import dumps, mcp, tool_errors, tool_meta
from . import advanced
from ._shared import COORDS_OPT, current_ucs

Kind = Literal["lines", "text", "hatches"]

# Set for the call and put back afterwards. FILEDIA 0: the File option asks
# for the name on the command line, not in a box. AUNITS, ANGBASE and ANGDIR 0:
# the rotation typed is plain degrees from east, counter-clockwise.
FIXED_FOR_CALL: dict[str, Any] = {"FILEDIA": 0, "AUNITS": 0, "ANGBASE": 0.0, "ANGDIR": 0}

CANCELLED = (
    "AutoCAD was still asking a question of PDFIMPORT ({command}) when every answer had been given, "
    "so Heron cancelled it: nothing is left open. Nothing should have come in, but look with "
    "autocad_preview and press Ctrl+Z if something did. Usually the page is not in the file{pages}; "
    "otherwise this AutoCAD {year} asks its questions differently (NEEDS-CHECKING AO). "
    "By hand: Insert > Import > PDF Import."
)


def _layer_names(doc: Any) -> list[str]:
    try:
        layers = doc.Layers
        return [str(layers.Item(i).Name) for i in range(int(layers.Count))]
    except BaseException:  # noqa: BLE001 - a courtesy list; never stops the import
        return []


def _space(doc: Any) -> str:
    """Where -PDFIMPORT draws: model space on the Model tab or inside an active viewport, else the sheet."""
    try:
        return "model" if int(doc.ActiveSpace) == 1 or bool(doc.MSpace) else "paper"
    except BaseException:  # noqa: BLE001 - a courtesy field
        return "model"


def _set_for_call(doc: Any, wanted: dict[str, Any]) -> dict[str, Any]:
    """Set each variable that differs; the old values of those changed. Refuses, nothing sent, when one cannot be read."""
    old: dict[str, Any] = {}
    for name in wanted:
        try:
            old[name] = doc.GetVariable(name)
        except BaseException as exc:  # noqa: BLE001
            if is_retryable(exc):
                raise  # busy, not missing: nothing is set yet, so it may be asked again
            raise AutocadError(
                f"This AutoCAD has no {name} (or would not say what it is), so PDF Import cannot be set up. "
                "Nothing was sent."
            ) from exc
    changed: dict[str, Any] = {}
    try:
        for name, value in wanted.items():
            if old[name] != value:
                doc.SetVariable(name, value)
                changed[name] = old[name]
    except BaseException as exc:  # noqa: BLE001
        left = _put_back(doc, changed)
        if not left:
            raise_if_busy(exc)  # all put back: the call may be asked again
        raise AutocadError(f"AutoCAD would not set {name} for the import. Nothing was sent." + _restore_note(left)) from exc
    return changed


def _put_back(doc: Any, changed: dict[str, Any]) -> list[str]:
    """Put each changed variable back; the ones AutoCAD stayed too busy to take."""
    return [f"{name} (it was {value})" for name, value in changed.items() if not advanced._set_patiently(doc, name, value)]


def _restore_note(left: list[str]) -> str:
    return (
        f" AutoCAD stayed too busy to put back {', '.join(left)}: set them back with autocad_set_variable."
        if left else ""
    )


@mcp.tool(name="autocad_import_pdf", **tool_meta("Import A PDF Page As Lines"))
@tool_errors
async def autocad_import_pdf(
    path: Annotated[str, Field(min_length=1, description="The PDF file, the whole path, e.g. 'D:\\Project\\Vendor\\AHU-01 GA.pdf'.")],
    page: Annotated[int, Field(default=1, ge=1, le=pdf.MAX_PAGE, description="Which page, the first is 1.")] = 1,
    insertion: Annotated[list[float], Field(default=[0.0, 0.0, 0.0], min_length=2, max_length=3, description="Where the page's lower-left corner goes, [x, y] or [x, y, z].")] = [0.0, 0.0, 0.0],  # noqa: B006 - pydantic copies it
    scale: Annotated[float, Field(default=1.0, gt=0, le=pdf.MAX_SCALE, description="Scale. At 1 the page comes in at the size AutoCAD gives it from the PDF; a PDF is a printed sheet, so check one known length with autocad_measure and import again with the scale that makes it true")] = 1.0,
    rotation: Annotated[float, Field(default=0.0, description="Rotation in DEGREES counter-clockwise.")] = 0.0,
    layer: Annotated[str | None, Field(default=None, description="Put everything that comes in on this layer, created if missing. Omit to keep the layers AutoCAD gives it (PDFIMPORTLAYERS: the PDF's own layers, or PDF_ layers by type).")] = None,
    what: Annotated[list[Kind], Field(default=["lines", "text", "hatches"], min_length=1, description="What to bring in: 'lines' (all vector geometry: lines, arcs, polylines), 'text' (TrueType text, as text you can edit), 'hatches' (solid fills, as solid hatches). Pictures inside the PDF are never brought in.")] = ["lines", "text", "hatches"],  # noqa: B006 - pydantic copies it
    coords: Annotated[str, COORDS_OPT] = "world",
) -> str:
    """Turn one page of a PDF into real lines, text and hatches in the drawing (PDF Import, -PDFIMPORT).

    For the vendor's general arrangement, the consultant's layout or an old
    drawing only kept as PDF: the page comes in as objects you can snap to,
    trim and dimension, at a point, scale and rotation, on one layer.
    A PDF made by a CAD program comes in as clean lines; a scanned PDF is a
    picture with no lines in it, and nothing comes in.

    No API can do this, so the tool types AutoCAD's own -PDFIMPORT with every
    answer at once, after checking this AutoCAD's release. If AutoCAD still
    asks something, the command is cancelled, never left open. Text drawn
    with SHX fonts comes in as lines (AutoCAD's PDFSHXTEXT turns it back into
    text; not done here). Pictures in the PDF are left out: AutoCAD would
    write each one out as a file.

    It lands in the space you are working in (model, or the sheet). One undo
    step. Look at it with autocad_preview, and check one known length.

    Args:
        path (str): the PDF.
        page (int): page number, 1 for the first.
        insertion (list[float]): where the lower-left corner goes.
        scale (float): scale factor.
        rotation (float): degrees counter-clockwise.
        layer (Optional[str]): one layer for everything; created if missing.
        what (list[str]): 'lines', 'text', 'hatches'.
        coords (str): 'world' or 'ucs' for the point and the angle.

    Returns:
        str: JSON: {"imported": int, "by_type": {type: count}, "box":
             {"min", "max"} | null (world), "layer": str | null,
             "layer_created": bool, "moved_to_layer": int, "layers_added":
             [str], "page": int, "path": str, "release": int, "space": str,
             "note": str}

    Examples:
        - Use when: "bring the AHU vendor drawing in as lines at 0,0" — path
          to the PDF.
        - Use when: "import page 3 of the consultant's PDF onto layer
          M-XREF-PDF" — page=3, layer='M-XREF-PDF'.
        - Use when: "convert this PDF to CAD, just the lines, no text" —
          what=['lines'].
        - Use when: "the PDF is at 1:50, bring it in true size" — scale=50,
          then check one length with autocad_measure.
        - Don't use when: you only need to see the PDF behind your drawing —
          attach it as a PDF underlay (autocad_attach_underlay, or PDFATTACH):
          nothing is copied in and it stays light.
        - Don't use when: the file is a .dwg — autocad_attach_xref or
          autocad_copy_from_drawing.

    Error Handling:
        - A missing file, a file that is not a PDF, or a page past the PDF's
          last page is refused before AutoCAD is asked.
        - An AutoCAD release whose PDFIMPORT questions are not known (not
          2021-2027), or a tilted or flipped UCS, is refused, nothing sent.
        - If AutoCAD is still asking when every answer is given, the command
          is cancelled and the answer says so.
        - A page that brings in nothing (a scan) is said plainly.
    """
    try:
        resolved = pdf.pdf_file(path)
        pdf.check_numbers(page, scale, rotation)
        filter_bits = pdf.filter_value(what)
    except ValueError as exc:
        raise AutocadError(str(exc)) from exc
    pages = await asyncio.to_thread(pdf.page_count, resolved)
    if pages is not None and page > pages:
        raise AutocadError(
            f"'{os.path.basename(resolved)}' has {pages} page{'s' if pages != 1 else ''}; there is no page {page}. "
            "Nothing was sent."
        )
    target = validate_name(layer, "layer") if layer else None

    def work() -> dict[str, Any]:
        doc = get_doc()
        require_idle(doc)
        try:
            year = pdf.release_year(str(doc.GetVariable("ACADVER")))
        except ValueError as exc:
            raise AutocadError(str(exc)) from exc
        ucs = current_ucs(doc)
        if ucs.tilted or ucs.flipped:
            raise AutocadError(
                f"The current UCS is {'tilted out of plan' if ucs.tilted else 'flipped (its Z points down)'}, "
                "and PDF Import lays the page on the UCS plane, so it would land tilted or mirrored. Set a "
                "plan UCS (autocad_set_ucs, or the World UCS) first. Nothing was sent."
            )
        if str(coords).strip().lower() == "ucs":
            ucs_point = list(as_vec3(insertion))
            ucs_degrees = float(rotation)
        else:
            ucs_point = list(ucs.to_ucs(insertion))
            ucs_degrees = float(rotation) - ucs.rotation_degrees
        world_point = list(ucs.to_world(ucs_point))

        try:
            mode = int(doc.GetVariable("PDFIMPORTMODE"))
        except BaseException as exc:  # noqa: BLE001
            if is_retryable(exc):
                raise
            raise AutocadError("This AutoCAD has no PDFIMPORTMODE, so it has no PDF Import. Nothing was sent.") from exc
        wanted = {**FIXED_FOR_CALL, "PDFIMPORTFILTER": filter_bits, "PDFIMPORTMODE": pdf.mode_value(mode)}
        layers_before = _layer_names(doc)

        changed = _set_for_call(doc, wanted)
        forms = pdf.import_forms(resolved, page, ucs_point, scale, ucs_degrees, target)
        try:
            runs, not_put_back = advanced.send_lisp_pieces(doc, forms)
        except AutocadError as exc:
            raise AutocadError(str(exc) + _restore_note(_put_back(doc, changed))) from exc
        except BaseException as exc:  # noqa: BLE001
            left = _put_back(doc, changed)
            if left:
                # Never let the call be asked again now: a second run would read these as his own.
                raise AutocadError(
                    "AutoCAD was too busy to start the import, so nothing was imported." + _restore_note(left)
                ) from exc
            raise
        restore = _restore_note(not_put_back + _put_back(doc, changed))

        by_number = {r["number"]: r for r in runs}
        command = by_number.get(pdf.COMMAND_PIECE)
        if command is None or command["value"] == advanced.LISP_SENTINEL:
            if command is None or not command["sent"]:
                raise AutocadError("AutoCAD stayed busy before PDFIMPORT could be sent, so nothing was imported." + restore)
            raise AutocadError(
                "Outcome unknown: AutoCAD was still busy with PDFIMPORT when the wait ended; a big page can "
                "take a while. Let it finish, then look with autocad_preview. What came in was not counted"
                + (f" or moved onto {target}" if target else "") + "." + restore
            )
        if command["cancelled"]:
            raise AutocadError(
                CANCELLED.format(
                    command=command["cancelled"],
                    pages=f" (it has {pages})" if pages else "",
                    year=year,
                ) + restore
            )

        values = {n: str(r["value"]) for n, r in by_number.items() if r["value"] != advanced.LISP_SENTINEL}
        answer: dict[str, Any] = {
            "path": resolved,
            "page": page,
            "insertion": [round(v, 6) for v in world_point],
            "scale": float(scale),
            "rotation": float(rotation),
            "what": sorted({str(k) for k in what}),
            "release": year,
            "space": _space(doc),
        }
        if pdf.WALK_PIECE not in values:
            answer.update({
                "imported": None,
                "note": "PDFIMPORT finished, but AutoCAD did not let Heron count what came in"
                + (f" or move it onto {target}" if target else "")
                + ". Look with autocad_preview." + restore,
            })
            return answer
        try:
            report = pdf.parse_report(values[pdf.WALK_PIECE], values.get(pdf.BOX_PIECE, ""), values.get(pdf.TYPES_PIECE, ""))
        except ValueError as exc:
            raise AutocadError(f"Outcome unknown: PDFIMPORT finished but {exc}. Look with autocad_preview." + restore) from exc
        added = sorted(n for n in set(_layer_names(doc)) - set(layers_before) if not target or n.upper() != target.upper())
        answer.update({
            "layer_created": bool(target) and target.upper() not in {n.upper() for n in layers_before},
            "imported": report["count"],
            "by_type": report["by_type"],
            "box": report["box"],
            "layer": target,
            "moved_to_layer": report["moved"],
            "layers_added": added,
        })
        if report["count"] == 0:
            answer["note"] = (
                "AutoCAD finished but nothing came in. The page is most likely a scan (a picture, with no "
                "lines in it) or holds only what was left out; attach it as a PDF underlay and trace it. If the "
                "page does have lines, this AutoCAD may ask its PDFIMPORT questions differently (NEEDS-CHECKING "
                "AO): use Insert > Import > PDF Import by hand." + restore
            )
            return answer
        notes = ["Look at it with autocad_preview, and check one known length with autocad_measure."]
        if report["failed"]:
            notes.insert(0, f"{report['failed']} of them would not move onto {target} and kept their own layer.")
        if target and added:
            notes.append(
                f"AutoCAD also made {len(added)} layer{'s' if len(added) != 1 else ''} for the PDF; with everything moved "
                f"onto {target} they are empty and autocad_purge removes them."
            )
        answer["note"] = " ".join(notes) + restore
        return answer

    return dumps(await run(work))
