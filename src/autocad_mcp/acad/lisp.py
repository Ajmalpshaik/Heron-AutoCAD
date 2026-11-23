"""Generating AutoLISP, and getting results back out of it.

Why this exists alongside the COM layer: COM is out-of-process, so every
entity created costs a round trip — one call to create it, then one per
property set. Drawing a few hundred entities that way takes seconds.

AutoLISP's ``entmake`` runs *inside* AutoCAD and writes straight into the
drawing database, skipping both the command overhead and the process boundary.
A whole batch becomes one round trip instead of hundreds.

The awkward part is the return path. AutoCAD's COM interface has no "evaluate
LISP and give me the answer" call — ``SendCommand`` is fire-and-forget. Two
ways around it are used here:

* **Small results** — stash a string in the USERS1 system variable and read it
  back over COM. Capped at what that variable holds. Used by autocad_run_lisp.
* **Large results** — have the LISP write to a temp file and read the file from
  Python. Unlimited, and it survives batches of any size. Used here.

Sending the script has a size problem too: ``SendCommand`` is not reliable with
long strings (expressions near 3,600 characters fail silently). The batch used
to be written to a ``.lsp`` file and pulled in with ``(load ...)``, but AutoCAD's
SECURELOAD then asks "Unsigned Executable File" for every batch, because the
file sits in %TEMP% (live check A21, 2026-10-26). So the batch is now sent as a
series of short expressions (``build_chunks``), each under CHUNK_LIMIT
characters. Nothing is loaded from a file, so SECURELOAD never applies.

Every top-level expression leaves one ``Command:`` prompt in the command
history, even typed with echo off (about 27 for 41 objects, live 2026-10-26,
#45). Through the Heron plug-in the pieces may be longer: its ping says how
long a line it types (``quietLimit``), and ``quiet_pieces`` builds the batch
in pieces up to that (at most QUIET_CHUNK_LIMIT), packing the short set-up
pieces together, so the same batch leaves a few prompts. Over COM the pieces
stay under CHUNK_LIMIT, as measured (D-98).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from ..core.errors import AutocadError

# Group code 5 holds an entity's handle, which is what ties a batch-created
# entity back to the handles the rest of this server speaks in.
DXF_HANDLE = 5

# Marker written for an entmake that returned nil, so a partial batch reports
# which operations failed instead of silently miscounting.
FAILURE_MARKER = "FAIL"

# Written in place of a handle when the caller does not need handles back.
# Reading a handle costs an (entget (entlast)) per entity, which builds the
# entity's whole DXF list just to pull one group code. Measured on AutoCAD
# 2020, 200 lines: 1.2s without handles, 2.2s with — so capture roughly
# doubles the batch. Reading the handles back over COM afterwards instead was
# no faster (2.5s), and entmakex was slower still, so in-LISP capture stays
# the default and this marker covers the opt-out.
SUCCESS_MARKER = "OK"

# Longest expression sent in one SendCommand. Expressions near 3,600 characters
# fail silently; chunks under about 700 were used for the whole CCTV package.
CHUNK_LIMIT = 600

# Longest piece typed through the Heron plug-in's quiet input (#45, D-98), when
# its ping says it takes that much: below the 2,000 characters that worked all
# day over COM (known limits 3), far from the 3,000 that arrived as nothing.
QUIET_CHUNK_LIMIT = 1500


class UnsendableText(ValueError):
    """A character that has no safe way into text sent to AutoCAD; the message says which and what to do."""


# AutoLISP's own short escapes inside a string literal. Every other character
# below 0x20, and DEL, is written as a three-digit octal escape (backslash,
# 0, 3, 3 for Esc): three digits always, so a digit that follows in the text
# can never join the escape.
_SHORT_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _refused_character(char: str) -> str | None:
    """Why ``char`` can never be put in text sent to AutoCAD, or None when it can (#207).

    NUL ends a LISP string. The C1 controls (U+0080 to U+009F, NEL among them),
    the line and paragraph separators (U+2028, U+2029) and a lone surrogate have
    no octal escape (AutoLISP's stop at 0377) and no safe meaning on the command
    line, so they are refused. Every other character, accented letters, Arabic
    and Malayalam included, is sent as it is.
    """
    code = ord(char)
    if code == 0:
        return "a NUL character"
    if 0x80 <= code <= 0x9F or code in (0x2028, 0x2029) or 0xD800 <= code <= 0xDFFF:
        return f"the control character U+{code:04X}"
    return None


def is_control(char: str) -> bool:
    """True for a character typed into AutoCAD as a key press, not as text: below 0x20, or DEL."""
    return ord(char) < 0x20 or ord(char) == 0x7F


def escape_control(text: str, what: str = "text") -> str:
    """``text`` with every control character written as an AutoLISP escape, to sit inside a string literal (#207).

    Typed into AutoCAD, a raw newline is Enter and a raw Esc cancels the
    half-typed expression, so a text value holding one could end its string and
    have what follows read as new input. Newline, return and tab become
    backslash-n, -r and -t; any other character below 0x20, and DEL, becomes a
    three-digit octal escape. Backslash and quote are left to the caller.
    Raises UnsendableText for a character that has no escape.
    """
    out: list[str] = []
    for char in text:
        reason = _refused_character(char)
        if reason:
            raise UnsendableText(f"The {what} holds {reason}, which cannot be sent to AutoCAD. Take it out and try again.")
        if char in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[char])
        elif is_control(char):
            out.append(f"\\{ord(char):03o}")
        else:
            out.append(char)
    return "".join(out)


def _control_name(char: str) -> str:
    """A control character in the words of the person reading the refusal."""
    code = ord(char)
    named = {0x0A: "a line break", 0x0D: "a carriage return", 0x09: "a tab", 0x1B: "an Esc character", 0x00: "a NUL character"}
    return named.get(code) or f"the control character U+{code:04X}"


def refuse_control(text: str, what: str = "text") -> str:
    """``text`` unchanged when it can be typed into AutoCAD's command line, else AutocadError, nothing typed (#242).

    The twin of ``escape_control`` for text that is typed as it is, not put in a
    string literal: a name after ``-VIEW _Save``, a command's option. A raw
    newline there is Enter and a raw Esc cancels the command, so whatever
    follows would be read as new input. Nothing can be escaped on the command
    line, so a control character (below 0x20, DEL, the C1 controls, U+2028 and
    U+2029) is refused in plain words. Accents, Arabic, Malayalam and the rest
    of Unicode pass. One definition of "control": ``is_control`` and
    ``_refused_character`` above, the same as the LISP side.
    """
    for char in text:
        if is_control(char) or _refused_character(char):
            raise AutocadError(
                f"The {what} holds {_control_name(char)}, which cannot be typed into AutoCAD's "
                "command line. Take it out and try again. Nothing was typed."
            )
    return text


def lisp_string(value: str) -> str:
    """Quote a Python string as an AutoLISP string literal.

    Backslashes and double quotes both need escaping, and text destined for a
    drawing routinely contains them — Windows paths, dimension overrides,
    inch marks. Control characters are escaped too (#207): a text value must
    never be able to end its string, or the expression, and have the rest
    typed into AutoCAD as new input. A character with no escape (NUL, the C1
    controls) is refused with a plain message, before anything is sent.
    """
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    try:
        return f'"{escape_control(escaped)}"'
    except UnsendableText as exc:
        raise AutocadError(f"{exc} Nothing was sent.") from None


def lisp_path(path: str) -> str:
    """Quote a filesystem path for AutoLISP.

    AutoLISP accepts forward slashes on Windows and they avoid the escaping
    problem entirely, so backslashes are converted rather than escaped. A
    quote or a control character is escaped as in ``lisp_string`` (#207).
    """
    escaped = str(path).replace(chr(92), "/").replace('"', '\\"')
    try:
        return f'"{escape_control(escaped, "path")}"'
    except UnsendableText as exc:
        raise AutocadError(f"{exc} Nothing was sent.") from None


def lisp_number(value: float) -> str:
    """Format a number as an AutoLISP real.

    Always emits a decimal point: AutoLISP distinguishes integers from reals,
    and a coordinate given as an integer is rejected by some entmake fields.
    """
    number = float(value)
    if not math.isfinite(number):
        raise AutocadError(
            f"{value!r} is not a usable coordinate — it must be a finite number."
        )
    return repr(number)


def lisp_point(coords: Sequence[float]) -> str:
    """Format a coordinate list as an AutoLISP 3D point."""
    if not coords or len(coords) < 2:
        raise AutocadError(
            f"A point needs at least [x, y], got {coords!r}."
        )
    z = coords[2] if len(coords) > 2 else 0.0
    return (
        f"(list {lisp_number(coords[0])} {lisp_number(coords[1])} {lisp_number(z)})"
    )


def dotted(code: int, value: str) -> str:
    """One DXF group-code pair inside an entmake list."""
    return f"(cons {code} {value})"


def entmake(pairs: Sequence[str], capture_handle: bool = True) -> str:
    """Wrap DXF pairs in an entmake that records the outcome.

    ``entmake`` returns the entity list on success and nil on failure, so the
    result is branched on directly: success writes either the new entity's
    handle or a plain marker, failure writes the failure marker. Recording
    every outcome is what lets a partially-failing batch report honestly
    instead of guessing from a count.
    """
    return _entmake_expr(f"(list {' '.join(pairs)})", capture_handle)


def _entmake_expr(entity_list: str, capture_handle: bool) -> str:
    on_success = (
        f"(write-line (cdr (assoc {DXF_HANDLE} (entget (entlast)))) f)"
        if capture_handle
        else f"(write-line {lisp_string(SUCCESS_MARKER)} f)"
    )
    return (
        f"(if (entmake {entity_list})"
        f" {on_success}"
        f" (write-line {lisp_string(FAILURE_MARKER)} f))"
    )


# Defined once per batch. Runs one piece of the batch with the output file as
# ``f``; an error is caught, written to the file as "ERROR ..." and the file is
# closed, so every later piece skips (*heron-f* is nil) and Python reports it.
_HELPER = (
    "(progn (defun heron-run (fn / e) (if *heron-f* (progn"
    " (setq e (vl-catch-all-apply fn (list *heron-f*)))"
    " (if (vl-catch-all-error-p e) (progn"
    ' (write-line (strcat "ERROR " (vl-catch-all-error-message e)) *heron-f*)'
    " (close *heron-f*) (setq *heron-f* nil))))) (princ)) (princ))"
)

# Closes however many undo groups are open: a single vla-EndUndoMark can leave
# a nested group open and quietly break the user's next Ctrl+Z.
_END_UNDO = "(while (= 8 (logand 8 (getvar 'undoctl))) (vla-endundomark *heron-doc*))"


def build_chunks(
    entities: Sequence[Sequence[str]],
    capture_handle: bool,
    output_path: str,
    limit: int = CHUNK_LIMIT,
) -> list[str]:
    """The whole batch as short LISP expressions, sent one SendCommand each.

    1. define ``heron-run`` (catches errors, see _HELPER);
    2. open the output file and start ONE undo group for the whole batch;
    3. the entmakes, as many per expression as fit under ``limit``. An entity
       too long for one expression is built up in ``*heron-p*`` piece by piece;
    4. close the undo group and write DONE.

    Every operation writes one line (handle or marker) to the output file,
    which ``parse_output`` reads, exactly as the old single-file script did.
    """
    start = (
        "(progn (vl-load-com)"
        " (setq *heron-doc* (vla-get-activedocument (vlax-get-acad-object)))"
        f" {_END_UNDO} (vla-startundomark *heron-doc*)"
        f' (setq *heron-f* (open {lisp_path(output_path)} "w")) (princ))'
    )
    finish = (
        f"(progn {_END_UNDO}"
        ' (if *heron-f* (progn (write-line "DONE" *heron-f*) (close *heron-f*)))'
        " (setq *heron-f* nil *heron-doc* nil *heron-p* nil) (princ))"
    )
    chunks = [_HELPER, start]

    def wrap(statements: list[str]) -> str:
        return f"(heron-run (function (lambda (f) {' '.join(statements)})))"

    pending: list[str] = []
    for index, pairs in enumerate(entities):
        statement = _entmake_expr(f"(list {' '.join(pairs)})", capture_handle)
        if len(wrap(pending + [statement])) <= limit:
            pending.append(statement)
            continue
        if pending:
            chunks.append(wrap(pending))
            pending = []
        if len(wrap([statement])) <= limit:
            pending.append(statement)
            continue
        chunks.extend(_built_up(index, list(pairs), capture_handle, limit))
    if pending:
        chunks.append(wrap(pending))
    chunks.append(finish)
    return chunks


def quiet_pieces(
    entities: Sequence[Sequence[str]],
    capture_handle: bool,
    output_path: str,
    plugin_limit: int,
) -> list[str]:
    """The batch in as few pieces as the plug-in's quiet input takes (#45, D-98).

    The same expressions as ``build_chunks``, built up to ``plugin_limit``
    characters (at most QUIET_CHUNK_LIMIT), then every run of pieces before
    the last packed into one ``(progn ...)`` while it fits: each top-level
    expression is one ``Command:`` prompt in the history. The last piece (close
    the undo group, write DONE) always stays on its own, so an error in the
    pieces before it can never leave the undo group open. Order and content
    are exactly those of the separate pieces, so the output file is the same.
    """
    limit = max(CHUNK_LIMIT, min(int(plugin_limit), QUIET_CHUNK_LIMIT))
    chunks = build_chunks(entities, capture_handle, output_path, limit)
    *body, finish = chunks
    return [*pack(body, limit), finish]


def pack(chunks: Sequence[str], limit: int) -> list[str]:
    """Join neighbouring top-level expressions into one ``(progn ... (princ))`` while it fits ``limit``.

    A piece already too long to share stays as it is. Evaluated in order, as
    if typed one after the other, and the whole returns nothing printable.
    """
    packed: list[str] = []
    group: list[str] = []

    def joined(items: list[str]) -> str:
        return items[0] if len(items) == 1 else f"(progn {' '.join(items)} (princ))"

    for chunk in chunks:
        if group and len(joined(group + [chunk])) > limit:
            packed.append(joined(group))
            group = []
        group.append(chunk)
    if group:
        packed.append(joined(group))
    return packed


def _built_up(index: int, pairs: list[str], capture_handle: bool, limit: int) -> list[str]:
    """One entity too long for a single expression, assembled in *heron-p*."""
    # (princ) at the end: the command line prints whatever comes back, and a
    # bare setq would print the whole growing list.
    opener = "(progn (setq *heron-p* (list {})) (princ))"
    adder = "(progn (setq *heron-p* (append *heron-p* (list {}))) (princ))"
    chunks: list[str] = []
    group: list[str] = []
    for pair in pairs:
        if len(adder.format(pair)) > limit:
            raise AutocadError(
                f"Operation {index} holds a single value too long to send to AutoCAD "
                f"(over {limit} characters, usually a very long text). Shorten it, or "
                "use autocad_add_text / autocad_add_mtext for it."
            )
        template = adder if chunks else opener
        if len(template.format(" ".join(group + [pair]))) <= limit:
            group.append(pair)
            continue
        chunks.append(template.format(" ".join(group)))
        group = [pair]
    template = adder if chunks else opener
    chunks.append(template.format(" ".join(group)))
    chunks.append(f"(heron-run (function (lambda (f) {_entmake_expr('*heron-p*', capture_handle)})))")
    return chunks


def parse_output(text: str, expected: int) -> dict[str, Any]:
    """Turn the LISP output file into a result the agent can act on.

    The file holds one line per operation — a handle or a failure marker —
    followed by a DONE sentinel. A missing sentinel means the script died
    partway, which is reported rather than passed off as success.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    error_line = next((line for line in lines if line.startswith("ERROR ")), None)
    completed = "DONE" in lines
    results = [
        line for line in lines if line not in {"DONE"} and not line.startswith("ERROR ")
    ]

    failed = sum(1 for line in results if line == FAILURE_MARKER)
    succeeded = [line for line in results if line != FAILURE_MARKER]
    # When handles were not captured, every success is the plain marker; those
    # are outcomes, not identities, so they must not be reported as handles.
    handles = [line for line in succeeded if line != SUCCESS_MARKER]

    outcome: dict[str, Any] = {
        "created": len(succeeded),
        "failed": failed,
        "requested": expected,
        "handles": handles,
        "completed": completed,
    }
    # Every operation writes one line. Fewer, with DONE written, means a piece
    # never reached AutoCAD's LISP (dropped on the way): never a quiet success.
    missing = expected - len(results) if completed and not error_line else 0
    if missing > 0:
        outcome["missing"] = missing

    if error_line:
        outcome["error"] = error_line[len("ERROR ") :].strip()
        outcome["hint"] = (
            "AutoLISP raised an error partway through the batch. Entities "
            "created before that point are in the drawing; the rest are not."
        )
    elif not completed:
        outcome["hint"] = (
            "The batch script did not run to completion. Check AutoCAD's "
            "command line (F2) for a prompt or error waiting there."
        )
    elif missing > 0:
        outcome["hint"] = (
            f"{missing} operation(s) never reached AutoCAD: a piece of the batch was lost on the "
            "way, so the objects made are fewer than asked. Read the drawing back (the handles "
            "above are what landed) and send only what is missing."
        )
    elif failed:
        outcome["hint"] = (
            "Some operations were rejected by AutoCAD. The usual cause is a "
            "locked or frozen target layer, or degenerate geometry such as a "
            "zero-radius circle."
        )
    return outcome
