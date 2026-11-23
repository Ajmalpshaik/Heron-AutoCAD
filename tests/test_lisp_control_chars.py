"""Text sent to AutoLISP can never end its string, or the expression, early (#207).

Found in the review of PR #186: ``lisp_string`` escaped only backslash and quote, so
a batch text value such as ESC ESC (startapp ...) newline, typed into AutoCAD, could
cancel the half-typed expression (the repo itself relies on ``SendCommand("\\x1b\\x1b")``
cancelling) and have the rest run as new input. Every control character is now written
as an AutoLISP escape, or refused with a plain message. Pure text work, tested offline.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.acad.lisp import (
    build_chunks,
    escape_control,
    lisp_path,
    lisp_string,
    quiet_pieces,
)
from autocad_mcp.acad.lisp_forms import LispTextError, chunk_forms, split_forms
from autocad_mcp.core.errors import AutocadError
from autocad_mcp.tools import advanced, batch


def one_string(literal: str) -> str:
    """Read ``literal`` the way AutoLISP does: from its opening quote to the first unescaped quote.

    Asserts that the quote is the last character, i.e. nothing can follow the string.
    """
    assert literal[0] == '"'
    i = 1
    while literal[i] != '"':
        i += 2 if literal[i] == "\\" else 1
    assert i == len(literal) - 1, f"the string ends early at {i}: {literal!r}"
    return literal[1:i]


def has_raw_control(text: str) -> bool:
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in text)


class TestEachKindOfCharacter:
    def test_newline(self):
        assert lisp_string("a\nb") == '"a\\nb"'

    def test_tab(self):
        assert lisp_string("a\tb") == '"a\\tb"'

    def test_carriage_return(self):
        assert lisp_string("a\rb") == '"a\\rb"'
        assert lisp_string("a\r\nb") == '"a\\r\\nb"'

    def test_quote(self):
        assert lisp_string('5" pipe') == '"5\\" pipe"'

    def test_backslash(self):
        assert lisp_string(r"C:\temp") == '"C:\\\\temp"'

    def test_a_backslash_before_a_quote_cannot_swallow_the_closing_quote(self):
        # text  \"  -> backslash-backslash, backslash-quote: the string still closes where it should
        assert one_string(lisp_string('\\"')) == '\\\\\\"'

    def test_escape_is_written_as_octal(self):
        assert lisp_string("\x1b") == '"\\033"'

    def test_every_other_control_character_is_octal(self):
        for code in range(1, 0x20):
            char = chr(code)
            if char in "\n\r\t":
                continue
            assert lisp_string(char) == f'"\\{code:03o}"', code

    def test_delete_is_octal(self):
        assert lisp_string("\x7f") == '"\\177"'

    def test_a_digit_after_an_octal_escape_cannot_join_it(self):
        # three digits always: \033 then the text "1", never \0331
        assert lisp_string("\x1b1") == '"\\0331"'
        assert lisp_string("\x011") == '"\\0011"'

    def test_unicode_letters_pass_through_unchanged(self):
        for text in ("é ü ß", "ميزان", "മലയാളം", "管道", "Ø16 ± 2 °", "pipe 🔧"):
            assert lisp_string(text) == f'"{text}"'

    def test_the_euro_sign_and_nbsp_are_text_not_controls(self):
        assert lisp_string("€5\u00a0pipe") == '"€5\u00a0pipe"'

    def test_nul_is_refused_with_a_plain_message(self):
        with pytest.raises(AutocadError) as err:
            lisp_string("a\x00b")
        assert "NUL" in str(err.value) and "Nothing was sent" in str(err.value)

    @pytest.mark.parametrize("char", ["\u0080", "\u0085", "\u009f", "\u2028", "\u2029", "\ud800"])
    def test_other_controls_unicode_has_no_escape_for_are_refused(self, char):
        with pytest.raises(AutocadError) as err:
            lisp_string(f"a{char}b")
        assert "cannot be sent to AutoCAD" in str(err.value)
        assert "Nothing was sent" in str(err.value)

    def test_plain_text_is_unchanged(self):
        assert lisp_string("DN100 CHW") == '"DN100 CHW"'
        assert lisp_string("") == '""'


class TestTheInjectionFromTheIssue:
    HOSTILE = '\x1b\x1b(startapp "calc.exe")\n'

    def test_no_raw_control_character_survives(self):
        assert not has_raw_control(lisp_string(self.HOSTILE))

    def test_the_text_stays_one_string(self):
        body = one_string(lisp_string(self.HOSTILE))
        assert body.startswith("\\033\\033(startapp \\\"calc.exe\\\")")
        assert body.endswith("\\n")

    def test_a_quote_closing_the_string_is_escaped_too(self):
        # text that tries to close the string and open a new form
        text = 'x") (startapp "calc.exe") ("'
        assert one_string(lisp_string(text))

    @pytest.mark.parametrize("bad", ["\x1b", "\n", "\r", "\t", "\x03", "\x1b\x1b\n"])
    def test_a_batch_text_op_with_a_control_character_makes_clean_lisp(self, bad):
        pairs = batch._build_text({"position": [0, 0], "text": f"A{bad}B"}, 0)
        assert not has_raw_control(" ".join(pairs))
        # and through the whole batch, in the pieces really typed
        for piece in build_chunks([pairs], True, r"C:\temp\out.txt"):
            assert not has_raw_control(piece)
        for piece in quiet_pieces([pairs], True, r"C:\temp\out.txt", 1500):
            assert not has_raw_control(piece)

    def test_an_mtext_op_with_a_control_character_makes_clean_lisp(self):
        pairs = batch._build_mtext({"position": [0, 0], "text": "line\x1b\x1b\n" * 200}, 0)
        assert not has_raw_control(" ".join(pairs))
        for piece in build_chunks([pairs], True, r"C:\temp\out.txt"):
            assert not has_raw_control(piece)

    def test_a_layer_style_or_override_with_one_is_covered_too(self):
        op = {"position": [0, 0], "text": "x", "layer": "A\x1bB", "style": "S\ntyle"}
        pairs = batch._build_text(op, 0)
        assert not has_raw_control(" ".join(pairs))

    def test_a_batch_text_op_with_nul_is_refused_before_anything_is_built(self):
        with pytest.raises(AutocadError, match="NUL"):
            batch._build_text({"position": [0, 0], "text": "A\x00B"}, 0)


class TestPaths:
    def test_a_normal_path_is_as_before(self):
        assert lisp_path(r"C:\temp\a.lsp") == '"C:/temp/a.lsp"'

    def test_a_quote_or_control_character_in_a_path_is_escaped(self):
        assert lisp_path('C:\\a"b') == '"C:/a\\"b"'
        assert not has_raw_control(lisp_path("C:\\a\x1b\nb"))

    def test_nul_in_a_path_is_refused(self):
        with pytest.raises(AutocadError, match="path"):
            lisp_path("C:\\a\x00b")


class TestEscapeControl:
    def test_it_leaves_backslash_and_quote_to_the_caller(self):
        assert escape_control('a\\"b') == 'a\\"b'

    def test_it_names_what_it_was_given(self):
        with pytest.raises(ValueError, match="The code holds"):
            escape_control("\x00", "code")


class TestTheCodeAutocadRunLispSends:
    """The caller's own expression gets the same guard, inside strings and outside."""

    def test_a_line_break_inside_a_string_is_written_as_an_escape(self):
        (form,) = split_forms('(princ "a\nb")')
        assert form == '(princ "a\\nb")'

    def test_a_tab_and_escape_inside_a_string(self):
        (form,) = split_forms('(princ "a\tb\x1bc")')
        assert form == '(princ "a\\tb\\033c")'

    def test_a_string_with_a_hostile_text_stays_one_string_in_one_piece(self):
        forms = split_forms('(setq a "\x1b\x1b(startapp \\"x\\")\n")')
        assert len(forms) == 1 and not has_raw_control(forms[0])

    def test_a_control_character_outside_a_string_is_refused(self):
        with pytest.raises(LispTextError, match="outside a string"):
            split_forms("(setq a\x1b 1)")

    def test_nul_inside_a_string_is_refused(self):
        with pytest.raises(LispTextError, match="NUL"):
            split_forms('(princ "a\x00b")')

    def test_a_backslash_before_a_line_break_is_refused(self):
        with pytest.raises(LispTextError, match="backslash"):
            split_forms('(princ "a\\\nb")')

    def test_a_normal_escape_in_a_string_is_kept(self):
        (form,) = split_forms('(princ "a\\nb\\\\c\\"d")')
        assert form == '(princ "a\\nb\\\\c\\"d")'

    def test_chunks_sent_by_the_tool_hold_no_raw_control_character(self):
        chunks = chunk_forms(split_forms('(setq a "x\ny")\n(princ a)'))
        assert not any(has_raw_control(c) for c in chunks)


class Doc:
    def __init__(self):
        self.variables = {advanced.LISP_RESULT_VAR: "mine", advanced.LISP_CANCELLED_VAR: "", "OSMODE": 0, "CMDACTIVE": 0}
        self.sent: list[str] = []

    def GetVariable(self, name):  # noqa: N802 - COM name
        return self.variables[name]

    def SetVariable(self, name, value):  # noqa: N802 - COM name
        self.variables[name] = value

    def SendCommand(self, text):  # noqa: N802 - COM name
        self.sent.append(text)
        self.variables[advanced.LISP_RESULT_VAR] = "ok"

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass


def test_autocad_run_lisp_types_only_one_raw_line_break_the_wrappers_own(monkeypatch):
    doc = Doc()

    async def run(fn):
        return fn()

    monkeypatch.setattr(advanced, "run", run)
    monkeypatch.setattr(advanced, "get_doc", lambda: doc)
    monkeypatch.setattr(advanced, "require_idle", lambda d: None)
    answer = asyncio.run(advanced.autocad_run_lisp(expression='(setq a "x\x1by\nz\tw")'))
    assert json.loads(answer)["result"] == "ok"
    (sent,) = doc.sent
    assert sent.endswith("(princ)\n")
    assert not has_raw_control(sent[:-1])
