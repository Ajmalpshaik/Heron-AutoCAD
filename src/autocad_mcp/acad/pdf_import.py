"""PDF Import (#113, D-106): the parts that need no AutoCAD.

AutoCAD has no API that turns a PDF into objects: not in COM, not in .NET
(Autodesk's answer on its .NET forum, 2019, and nothing since). The command
PDFIMPORT is the only way, and its command-line form asks five questions in a
row. So the tool answers them all in one AutoLISP form, sent through the same
path as autocad_run_lisp: running object snaps off, a command left open
cancelled and named (known limit 21). Nothing is loaded from a file.

The questions, in the order the command line asks them with the File option
and FILEDIA at 0 (Autodesk's help for -PDFIMPORT, and the forms posted on
Autodesk's forums that run it with ``(command "-PDFIMPORT" "FILE" ...)``):

1. Select PDF underlay or [File]  -> ``_File``
2. the PDF file's name            -> the whole path
3. Enter page number or [?]       -> the page
4. Specify insertion point        -> the point, in the current UCS
5. Specify scale factor           -> the scale
6. Specify rotation               -> the angle, in degrees

What comes in is set by three system variables, put back afterwards:
PDFIMPORTFILTER (bits that LEAVE a kind out: 1 vector geometry, 2 TrueType
text, 4 solid fills, 8 raster images) and PDFIMPORTMODE (1 combine into a
block, 2 lineweights, 4 join line and arc segments, 8 fills as hatches). Both
were read from Autodesk's help through a search: the help site itself could
not be opened from the session that wrote this, so the live rows (Group AO)
prove them, NOT RUN until then.
"""

from __future__ import annotations

import math
import os
import re
import zlib
from collections.abc import Sequence

from .lisp import lisp_number, lisp_string

# The releases whose -PDFIMPORT questions are the six above (D-13: 2021 to 2027).
# ACADVER's first two numbers: R24.0 is 2021 ... R26.0 is 2027. A release not
# listed is refused rather than answered blind: an answer to the wrong question
# lands at the next prompt, or at the Command prompt as a command.
RELEASES: dict[tuple[int, int], int] = {
    (24, 0): 2021,
    (24, 1): 2022,
    (24, 2): 2023,
    (24, 3): 2024,
    (25, 0): 2025,
    (25, 1): 2026,
    (26, 0): 2027,
}

# What a modeller can ask for, and the PDFIMPORTFILTER bit that leaves it out.
KINDS: dict[str, int] = {"lines": 1, "text": 2, "hatches": 4}
# Raster images are always left out: AutoCAD writes each one out as a file
# (PDFIMPORTIMAGEPATH), which a Change tool must not do. Attach the PDF as an
# underlay to see its pictures.
NO_IMAGES = 8
# PDFIMPORTMODE bits.
MODE_AS_BLOCK = 1  # off: each object comes in on its own, so it can be counted and moved
MODE_FILLS_AS_HATCHES = 8  # on: a solid fill comes in as a hatch, not a 2D solid

# The largest page a PDF plausibly has, and the biggest scale; past these the
# request is a typo, not a drawing.
MAX_PAGE = 9999
MAX_SCALE = 1e6
# How much of a PDF is read to find its page count: a vendor's catalogue can be
# hundreds of megabytes, and the count is only a courtesy check.
COUNT_READ_LIMIT = 64 * 1024 * 1024

# Entities that belong to another (a polyline's vertices, a block's attributes):
# never counted or moved on their own.
SUB_ENTITIES = ("VERTEX", "SEQEND", "ATTRIB")


def release_year(acadver: str) -> int:
    """The AutoCAD year for an ACADVER such as '26.0s (LMS Tech)'. ValueError when it is not one listed."""
    found = re.match(r"\s*(\d+)\.(\d+)", str(acadver or ""))
    year = RELEASES.get((int(found.group(1)), int(found.group(2)))) if found else None
    if year is None:
        known = f"{min(RELEASES.values())} to {max(RELEASES.values())}"
        raise ValueError(
            f"This AutoCAD (ACADVER {str(acadver).strip() or 'unknown'}) is not one whose PDFIMPORT questions "
            f"Heron knows (AutoCAD {known}). Answering them blind could leave the command open or type an "
            "answer as a command, so nothing was sent. In AutoCAD: Insert > Import > PDF Import."
        )
    return year


def pdf_file(raw: str) -> str:
    """The whole path of an existing PDF; ValueError for a missing file or one that is not a PDF."""
    text = str(raw or "").strip().strip('"').strip()
    if not text:
        raise ValueError("Give the PDF's path.")
    resolved = os.path.abspath(os.path.expandvars(os.path.expanduser(text)))
    if os.path.splitext(resolved)[1].lower() != ".pdf":
        raise ValueError(
            f"'{os.path.basename(resolved)}' is not a .pdf. PDF Import takes a PDF; a .dwg is "
            "autocad_attach_xref or autocad_copy_from_drawing."
        )
    if not os.path.isfile(resolved):
        raise ValueError(f"No file exists at '{resolved}'. Check the path; nothing was sent.")
    try:
        with open(resolved, "rb") as handle:
            head = handle.read(1024)
    except OSError as exc:
        raise ValueError(f"'{resolved}' cannot be read ({exc.strerror or exc}). Nothing was sent.") from exc
    if b"%PDF-" not in head:
        raise ValueError(f"'{os.path.basename(resolved)}' is named .pdf but is not a PDF inside. Nothing was sent.")
    return resolved


def page_count(path: str) -> int | None:
    """How many pages a PDF has, or None when it cannot be told; a courtesy check only.

    The biggest /Count of a /Type /Pages node is the root's, which is the whole
    document's. Newer PDFs keep those nodes in compressed object streams, so the
    Flate streams are opened too. An encrypted PDF, or one too big to read,
    gives None, and AutoCAD answers for itself.
    """
    try:
        if os.path.getsize(path) > COUNT_READ_LIMIT:
            return None
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    if b"/Encrypt" in data:
        return None
    texts = [data]
    for stream in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.DOTALL):
        try:
            texts.append(zlib.decompress(stream.group(1)))
        except zlib.error:
            continue
    counts = [
        int(found.group(1))
        for text in texts
        for node in re.finditer(rb"<<(?:(?!<<|>>).)*?/Type\s*/Pages\b(?:(?!<<|>>).)*?>>", text, re.DOTALL)
        for found in [re.search(rb"/Count\s+(\d+)", node.group(0))]
        if found
    ]
    return max(counts) if counts else None


def filter_value(what: Sequence[str]) -> int:
    """PDFIMPORTFILTER for the kinds asked for; ValueError for none or an unknown kind."""
    asked = {str(kind).strip().lower() for kind in what}
    unknown = sorted(asked - set(KINDS))
    if unknown:
        raise ValueError(f"Unknown kind {', '.join(unknown)}: give lines, text and/or hatches.")
    if not asked:
        raise ValueError("Say what to bring in: lines, text and/or hatches.")
    return NO_IMAGES + sum(bit for kind, bit in KINDS.items() if kind not in asked)


def mode_value(current: int) -> int:
    """PDFIMPORTMODE for the import: the modeller's own lineweight and join choices kept, no block, fills as hatches."""
    return (int(current) & ~MODE_AS_BLOCK) | MODE_FILLS_AS_HATCHES


def check_numbers(page: int, scale: float, rotation: float) -> None:
    """ValueError for a page, scale or rotation no drawing would have."""
    if int(page) < 1 or int(page) > MAX_PAGE:
        raise ValueError(f"page must be 1 or more (the first page is 1), got {page}.")
    if not math.isfinite(float(scale)) or float(scale) <= 0 or float(scale) > MAX_SCALE:
        raise ValueError(f"scale must be above 0 and at most {MAX_SCALE:g}, got {scale}.")
    if not math.isfinite(float(rotation)):
        raise ValueError(f"rotation must be a number of degrees, got {rotation}.")


def command_form(path: str, page: int, ucs_point: Sequence[float], scale: float, ucs_degrees: float) -> str:
    """The -PDFIMPORT call with every answer, as one AutoLISP form.

    The point is a LISP list, not text, so no running snap or comma setting
    can change it; the path is one string, so a space in it is not an Enter.
    The angle is in degrees: the tool sets AUNITS, ANGBASE and ANGDIR to 0
    around the call, so the number means what it says.
    """
    x, y = float(ucs_point[0]), float(ucs_point[1])
    z = float(ucs_point[2]) if len(ucs_point) > 2 else 0.0
    return (
        '(command "_.-PDFIMPORT" "_File" '
        f"{lisp_string(path)} {int(page)} "
        f"(list {lisp_number(x)} {lisp_number(y)} {lisp_number(z)}) "
        f"{lisp_number(scale)} {lisp_number(ucs_degrees % 360.0)})"
    )


# Before the command: the last object in the drawing, so the walk afterwards
# starts at the first one the import made.
MARK_FORM = "(setq heron:pdf0 (entlast))"


def add_form() -> str:
    """A helper defined in the drawing's LISP: count one new object by type, move it, widen the box."""
    return (
        "(defun heron:pdfadd (e / o a p q)"
        "(setq heron:n (1+ heron:n) o (vlax-ename->vla-object e)"
        " a (assoc heron:t heron:k)"
        " heron:k (if a (subst (cons heron:t (1+ (cdr a))) a heron:k) (cons (cons heron:t 1) heron:k)))"
        "(if heron:l (if (vl-catch-all-error-p (vl-catch-all-apply 'vla-put-layer (list o heron:l)))"
        " (setq heron:f (1+ heron:f)) (setq heron:m (1+ heron:m))))"
        "(if (not (vl-catch-all-error-p (vl-catch-all-apply 'vla-getboundingbox (list o 'p 'q))))"
        "(setq p (vlax-safearray->list p) q (vlax-safearray->list q)"
        " heron:b (if heron:b (list (min (car heron:b) (car p)) (min (cadr heron:b) (cadr p))"
        " (max (caddr heron:b) (car q)) (max (cadddr heron:b) (cadr q)))"
        " (list (car p) (cadr p) (car q) (cadr q)))))"
        "nil)"
    )


def walk_form(layer: str | None) -> str:
    """Walk every object made after MARK_FORM through heron:pdfadd; its value is 'n=..;moved=..;failed=..'.

    The layer is made here, after the command finished, so a cancelled import
    leaves no new layer behind.
    """
    to = lisp_string(layer) if layer else "nil"
    skip = " ".join(lisp_string(name) for name in SUB_ENTITIES)
    return (
        "(progn"
        f"(setq heron:l {to} heron:n 0 heron:m 0 heron:f 0 heron:k nil heron:b nil"
        " heron:e (if heron:pdf0 (entnext heron:pdf0) (entnext)))"
        "(if (and heron:l (not (tblsearch \"LAYER\" heron:l)))"
        " (vla-add (vla-get-layers (vla-get-activedocument (vlax-get-acad-object))) heron:l))"
        "(while heron:e"
        "(setq heron:t (cdr (assoc 0 (entget heron:e))))"
        f"(if (not (member heron:t (list {skip}))) (heron:pdfadd heron:e))"
        "(setq heron:e (entnext heron:e)))"
        '(strcat "n=" (itoa heron:n) ";moved=" (itoa heron:m) ";failed=" (itoa heron:f)))'
    )


# The box round everything that came in, 'x1,y1,x2,y2' in world units, or ''.
BOX_FORM = (
    '(if heron:b (strcat (rtos (car heron:b) 2 3) "," (rtos (cadr heron:b) 2 3) ","'
    ' (rtos (caddr heron:b) 2 3) "," (rtos (cadddr heron:b) 2 3)) "")'
)
# How many of each type came in, 'LINE=812,MTEXT=40,'.
TYPES_FORM = (
    "(apply (quote strcat) (mapcar (quote (lambda (p) (strcat (car p) \"=\" (itoa (cdr p)) \",\")))"
    " heron:k))"
)


def import_forms(path: str, page: int, ucs_point: Sequence[float], scale: float, ucs_degrees: float,
                 layer: str | None) -> list[str]:
    """Every piece the tool sends, in order. Piece 2 is the command: one left open stops the rest."""
    return [
        MARK_FORM,
        command_form(path, page, ucs_point, scale, ucs_degrees),
        add_form(),
        walk_form(layer),
        BOX_FORM,
        TYPES_FORM,
    ]


# Which piece answers what, by position in import_forms.
COMMAND_PIECE, WALK_PIECE, BOX_PIECE, TYPES_PIECE = 2, 4, 5, 6


def parse_report(walk: str, box: str, types: str) -> dict:
    """The three answers read back as {"count", "moved", "failed", "box", "by_type"}; ValueError when the walk's is not one."""
    found = re.fullmatch(r"n=(\d+);moved=(\d+);failed=(\d+)", str(walk or "").strip())
    if not found:
        raise ValueError(f"the count of what came in did not read back ({str(walk)[:80]!r})")
    corners = None
    try:
        values = [float(v) for v in str(box or "").split(",")] if str(box or "").strip() else []
    except ValueError:
        values = []
    if len(values) == 4:
        corners = {"min": [values[0], values[1]], "max": [values[2], values[3]]}
    by_type: dict[str, int] = {}
    for pair in filter(None, str(types or "").strip().split(",")):
        name, _, count = pair.partition("=")
        if name and count.isdigit():
            by_type[name] = by_type.get(name, 0) + int(count)
    return {
        "count": int(found.group(1)),
        "moved": int(found.group(2)),
        "failed": int(found.group(3)),
        "box": corners,
        "by_type": dict(sorted(by_type.items(), key=lambda item: (-item[1], item[0]))),
    }
