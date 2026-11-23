"""Cut long AutoLISP into pieces AutoCAD's command line takes whole (#46).

AutoCAD drops command-line text near 3,600 characters without a word (known
limit 3): a ~3,000-character ``defun`` block arrived as nothing, while calls
under 2,000 worked all day. ``autocad_run_lisp`` used to refuse anything over
2,000; now it cuts the code between its top-level forms and runs the pieces in
order. Two rules hold it safe:

- **Never inside a form.** A top-level form is evaluated whole or not at all,
  exactly as if it had been typed on its own. A ``(command ...)`` and its
  answers are always one form.
- **One form too long is refused**, never cut: past ``most`` characters it is
  said plainly, with its number and how it starts.

Comments go and runs of spaces and line breaks become one space, outside
strings only, so what is counted is the code AutoCAD will read, and a ``;``
comment can never swallow the closing brackets on the command line. Strings
are kept exactly as written. Pure text work: tested offline.
"""

from __future__ import annotations

from .lisp import UnsendableText, escape_control, is_control

# A piece is kept under this, like a chunk written by hand ("keep chunks under
# about 700 characters", AGENTS.md). The wrapper adds about 460 more.
CHUNK_CHARS = 700
# One form may stand alone up to this. It was 2,000 until the wrapper grew to about 460
# characters (#157): a form this long plus the wrapper stays no longer than the 2,244
# characters that went before, since a ~2,400-character call answered only after the wait
# (known limit 3).
FORM_MAX_CHARS = 1750

PROGN = "(progn "


class LispTextError(ValueError):
    """The text is not whole AutoLISP forms; the message says what to fix."""


def split_forms(text: str) -> list[str]:
    """The top-level forms of ``text``, each made compact: no comments, single spaces.

    Raises LispTextError for brackets or quotes that do not close, a ``)``
    with nothing open, or anything between forms that is not a form, since
    AutoCAD would sit waiting for the rest and block the connection.
    """
    forms: list[str] = []
    current: list[str] = []
    depth = 0
    i, size = 0, len(text)
    pending_space = False

    def put(piece: str) -> None:
        nonlocal pending_space
        if pending_space and current and current[-1] != "(" and piece != ")":
            current.append(" ")
        pending_space = False
        current.append(piece)

    while i < size:
        char = text[i]
        if char == ";":
            # ;| block comment |;  or  ; to the end of the line
            if text.startswith(";|", i):
                end = text.find("|;", i + 2)
                if end < 0:
                    raise LispTextError(
                        "A ;| comment is never closed with |;. AutoCAD would read the rest "
                        "of the code as the comment."
                    )
                i = end + 2
            else:
                end = text.find("\n", i)
                i = size if end < 0 else end + 1
            pending_space = depth > 0
            continue
        if char.isspace():
            pending_space = depth > 0
            i += 1
            continue
        if char == '"':
            if depth == 0:
                raise LispTextError(_outside(text, i))
            end = _string_end(text, i)
            put(_safe_string(text[i : end + 1]))
            i = end + 1
            continue
        if char == "(":
            if depth == 0:
                current, pending_space = [], False
            put("(")
            depth += 1
            i += 1
            continue
        if char == ")":
            if depth == 0:
                raise LispTextError(
                    f"A ')' at character {i + 1} closes nothing: the brackets do not balance. "
                    "AutoCAD would be left reading a broken expression."
                )
            put(")")
            depth -= 1
            i += 1
            if depth == 0:
                forms.append("".join(current))
            continue
        if depth == 0:
            raise LispTextError(_outside(text, i))
        # an atom or a quote: copied up to the next bracket, space, quote or comment
        start = i
        while i < size and not text[i].isspace() and text[i] not in '()";':
            i += 1
        put(_safe_atom(text[start:i]))

    if depth:
        raise LispTextError(
            f"Unbalanced parentheses: {depth} '(' never closed. AutoCAD would wait for the "
            "rest of the expression and block the connection."
        )
    if not forms:
        raise LispTextError("There is no AutoLISP form in the text: it must have at least one '( ... )'.")
    return forms


def _safe_string(literal: str) -> str:
    """A string literal with its control characters written as AutoLISP escapes (#207).

    Typed into AutoCAD, a raw line break or Esc inside a string would end the
    expression there and have the rest read as new input. A backslash right
    before a control character has no clear meaning and is refused.
    """
    out: list[str] = []
    i = 0
    while i < len(literal):
        char = literal[i]
        if char == "\\" and i + 1 < len(literal):
            if is_control(literal[i + 1]):
                raise LispTextError(
                    "A string holds a backslash right before a line break or other control "
                    "character. Write the escape (backslash and n for a line break) instead."
                )
            out.append(literal[i : i + 2])
            i += 2
            continue
        try:
            out.append(escape_control(char, "code"))
        except UnsendableText as exc:
            raise LispTextError(str(exc)) from None
        i += 1
    return "".join(out)


def _safe_atom(atom: str) -> str:
    """An atom, refused when it holds a control character: nothing outside a string may be one."""
    for char in atom:
        if is_control(char):
            raise LispTextError(
                f"The code holds a control character (code {ord(char)}) outside a string. "
                "Take it out; only strings may hold one, as an escape (backslash and n for a line break)."
            )
    try:
        escape_control(atom, "code")
    except UnsendableText as exc:
        raise LispTextError(str(exc)) from None
    return atom


def _string_end(text: str, start: int) -> int:
    """Where the string opened at ``start`` closes. A backslash escapes the next character."""
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i
        i += 1
    raise LispTextError(
        "Unbalanced double quotes in the expression. AutoCAD would wait for the closing "
        "quote and block the connection."
    )


def _outside(text: str, at: int) -> str:
    seen = text[at : at + 30].split("\n")[0]
    return (
        f"'{seen}' (character {at + 1}) is outside any ( ... ) form. Every piece of the code must "
        "be a whole form, e.g. (setq a 1), not a bare value or a quote between forms."
    )


def chunk_forms(forms: list[str], limit: int = CHUNK_CHARS, most: int = FORM_MAX_CHARS) -> list[str]:
    """Group the forms, in order, into pieces of at most ``limit`` characters.

    Several forms in one piece go inside ``(progn ...)``, so the piece's value
    is that of its last form. A form longer than ``limit`` but no longer than
    ``most`` goes alone. A longer one is refused (LispTextError): it is never
    cut, since half a form is not AutoLISP.
    """
    for number, form in enumerate(forms, start=1):
        if len(form) > most:
            raise LispTextError(
                f"Form {number} of {len(forms)} is {len(form)} characters on its own (it starts "
                f"'{form[:40]}'), and AutoCAD drops command-line text much past {most} without a "
                "word. Split it: define helpers with defun as separate top-level forms, then use them."
            )

    chunks: list[str] = []
    group: list[str] = []

    def size(parts: list[str]) -> int:
        if len(parts) == 1:
            return len(parts[0])
        return len(PROGN) + len(" ".join(parts)) + 1

    def close() -> None:
        if group:
            chunks.append(group[0] if len(group) == 1 else PROGN + " ".join(group) + ")")
            group.clear()

    for form in forms:
        if group and size([*group, form]) > limit:
            close()
        group.append(form)
    close()
    return chunks
