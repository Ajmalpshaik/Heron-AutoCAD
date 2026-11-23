"""autocad_run_lisp answers a LISP error at once, with AutoCAD's own message (#157).

Before, a LISP error was found only when the 10 s wait for the result ran out, and the
answer could only guess ("probably raised a LISP error"). The wrapper now runs the code
inside ``vl-catch-all-apply`` and writes the error message to USERS1 behind a marker;
the server reads it like any result and stops at that piece. Tested offline with
stand-ins for the COM document: what AutoCAD really does with a ``(command ...)`` inside
``vl-catch-all-apply`` is a live row (docs/NEEDS-CHECKING.md, Group AW).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from autocad_mcp.core import answers
from autocad_mcp.tools import advanced
from autocad_mcp.tools.advanced import (
    LISP_CANCELLED_VAR,
    LISP_ERROR_PREFIX,
    LISP_RESULT_VAR,
    lisp_error_in,
    lisp_wrapper,
)

LONG = "\n".join(f"(defun f{i} () (+ {i} " + "1 " * 290 + "))" for i in range(6)) + "\n(f5)"
ERROR = "bad argument type: numberp: nil"


class Doc:
    """Answers each piece like AutoCAD: a value, a LISP error (as the wrapper writes it), or a command left open."""

    def __init__(self, error_at=None, message=ERROR, cancel_at=None, timeout_at=None):
        self.variables = {LISP_RESULT_VAR: "mine", LISP_CANCELLED_VAR: "also mine", "OSMODE": 675, "CMDACTIVE": 0}
        self.sent: list[str] = []
        self.error_at, self.message, self.cancel_at, self.timeout_at = error_at, message, cancel_at, timeout_at
        self.reads = 0

    def GetVariable(self, name):  # noqa: N802 - COM name
        if name == LISP_RESULT_VAR:
            self.reads += 1
        return self.variables[name]

    def SetVariable(self, name, value):  # noqa: N802 - COM name
        self.variables[name] = value

    def SendCommand(self, text):  # noqa: N802 - COM name
        self.sent.append(text)
        number = len(self.sent)
        if number == self.timeout_at:
            return
        self.variables[LISP_CANCELLED_VAR] = "LINE" if number == self.cancel_at else ""
        self.variables[LISP_RESULT_VAR] = (
            LISP_ERROR_PREFIX + self.message if number == self.error_at else f"value {number}"
        )

    def StartUndoMark(self):  # noqa: N802 - COM name
        pass

    def EndUndoMark(self):  # noqa: N802 - COM name
        pass


class Clock:
    now = 0.0
    slept = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


@pytest.fixture
def lisp(monkeypatch):
    holder: dict = {}
    clock = Clock()

    async def run(fn):
        return fn()

    monkeypatch.setattr(advanced, "run", run)
    monkeypatch.setattr(advanced, "time", clock)
    monkeypatch.setattr(advanced, "get_doc", lambda: holder["doc"])
    monkeypatch.setattr(advanced, "require_idle", lambda d: None)

    def call(expression: str, doc: Doc):
        holder["doc"] = doc
        return asyncio.run(advanced.autocad_run_lisp(expression=expression)), doc, clock

    return call


class TestWrapper:
    def test_the_expression_runs_inside_a_catch_all(self):
        text = lisp_wrapper("(+ 1 2)")
        assert "(vl-catch-all-apply (function (lambda () (+ 1 2))) nil)" in text

    def test_the_error_message_is_written_to_the_result_variable_behind_the_marker(self):
        text = lisp_wrapper("(+ 1 2)")
        assert "(vl-catch-all-error-p heron:x)" in text
        assert f'(strcat "{LISP_ERROR_PREFIX}" (substr (vl-catch-all-error-message heron:x)' in text
        assert f'(setvar "{LISP_RESULT_VAR}" heron:r)' in text

    def test_the_cancel_still_comes_before_the_result_is_written_error_or_not(self):
        text = lisp_wrapper("(+ 1 2)")
        assert text.index("(vl-catch-all-apply") < text.index("(command))") < text.index(f'(setvar "{LISP_CANCELLED_VAR}"')
        assert text.index(f'(setvar "{LISP_CANCELLED_VAR}"') < text.index(f'(setvar "{LISP_RESULT_VAR}"')
        assert text.endswith("(princ)\n")

    def test_an_expression_autolisp_cannot_read_never_shows_an_earlier_value(self):
        # the first form clears the result and the left-open command, so if the form that runs the
        # code is never evaluated, the result write fails (a timeout), never the last call's value
        text = lisp_wrapper("(+ 1 2)")
        first, _, _ = text.partition("(princ))")
        assert "heron:r nil" in first and 'heron:c ""' in first
        assert text.index(first) == 0

    def test_the_longest_form_plus_the_wrapper_is_no_longer_than_before_the_catch(self):
        # before #157: 2,000 + 244. A ~2,400-character call answered only after the wait (known limit 3).
        assert advanced.LISP_MAX_CHARS + len(lisp_wrapper("")) <= 2244 + 10

    def test_the_wrapper_is_balanced_and_short(self):
        text = lisp_wrapper('(strcat "a" "b")')
        assert text.count("(") == text.count(")")
        assert len(lisp_wrapper("X")) < 480  # it sits on every piece; AutoCAD drops text near 3,000

    def test_the_marker_is_what_the_reader_looks_for(self):
        assert lisp_error_in(LISP_ERROR_PREFIX + ERROR) == ERROR
        assert lisp_error_in("42") == ""
        assert lisp_error_in("nil") == ""
        assert lisp_error_in(advanced.LISP_SENTINEL) == ""
        assert lisp_error_in(LISP_ERROR_PREFIX) == "(AutoCAD gave no message)"


class TestAnswer:
    def test_a_lisp_error_is_answered_at_once_with_autocads_message(self, lisp):
        text, doc, clock = lisp("(+ 1 nil)", Doc(error_at=1))
        answer = json.loads(text)
        assert answer["lisp_error"] == ERROR
        assert answer["result"] is None
        assert answer["timed_out"] is False
        assert ERROR in answer["note"]
        assert clock.slept == 0.0  # no wait at all: the answer was read on the first look
        assert doc.reads == 2  # the value it saves first, then ONE look: the answer

    def test_it_does_not_say_it_timed_out_or_guess(self, lisp):
        text, _, _ = lisp("(+ 1 nil)", Doc(error_at=1))
        assert "probably" not in json.loads(text)["note"]

    def test_the_modellers_own_variables_are_put_back(self, lisp):
        _, doc, _ = lisp("(+ 1 nil)", Doc(error_at=1))
        assert doc.variables[LISP_RESULT_VAR] == "mine"
        assert doc.variables[LISP_CANCELLED_VAR] == "also mine"
        assert doc.variables["OSMODE"] == 675

    def test_a_plain_value_is_as_before(self, lisp):
        text, _, _ = lisp("(+ 1 2)", Doc())
        answer = json.loads(text)
        assert answer["result"] == "value 1" and answer["timed_out"] is False
        assert "lisp_error" not in answer

    def test_a_result_that_merely_looks_like_an_error_word_is_not_one(self, lisp):
        doc = Doc()
        doc.message = "x"
        text, _, _ = lisp('(princ "error: no")', doc)
        assert "lisp_error" not in json.loads(text)


class TestInPieces:
    def test_an_error_in_piece_three_stops_the_rest_and_says_which(self, lisp):
        text, doc, clock = lisp(LONG, Doc(error_at=3))
        answer = json.loads(text)
        assert len(doc.sent) == 3
        assert answer["lisp_error"] == ERROR
        assert answer["chunks"] == 6
        assert answer["chunks_finished"] == 2  # the piece that failed is not finished
        assert "piece 3 of 6" in answer["note"] and "3 more were not sent" in answer["note"]
        assert "pieces 1 to 2 ran" in answer["note"]
        assert clock.slept == 0.0

    def test_an_error_in_the_first_piece_says_nothing_before_it_ran(self, lisp):
        text, doc, _ = lisp(LONG, Doc(error_at=1))
        answer = json.loads(text)
        assert len(doc.sent) == 1
        assert "nothing before it ran" in answer["note"]

    def test_an_error_in_the_last_piece_says_so(self, lisp):
        text, doc, _ = lisp(LONG, Doc(error_at=6))
        answer = json.loads(text)
        assert len(doc.sent) == 6
        assert "last of 6 pieces" in answer["note"]

    def test_an_error_and_a_command_left_open_report_both(self, lisp):
        text, doc, _ = lisp(LONG, Doc(error_at=2, cancel_at=2))
        answer = json.loads(text)
        assert answer["lisp_error"] == ERROR
        assert answer["cancelled_command"] == "LINE"
        assert "LINE" in answer["note"] and ERROR in answer["note"]
        assert len(doc.sent) == 2

    def test_a_timeout_is_still_a_timeout(self, lisp):
        doc = Doc(timeout_at=2)
        advanced.LISP_POLL_ATTEMPTS, saved = 3, advanced.LISP_POLL_ATTEMPTS
        try:
            text, _, _ = lisp(LONG, doc)
        finally:
            advanced.LISP_POLL_ATTEMPTS = saved
        answer = json.loads(text)
        assert answer["timed_out"] is True and "lisp_error" not in answer
        assert "A LISP error" in answer["note"]

    def test_an_error_message_is_kept_as_it_came(self, lisp):
        message = 'no function definition: "FOO"'
        text, _, _ = lisp("(foo)", Doc(error_at=1, message=message))
        assert json.loads(text)["lisp_error"] == message


class TestFirstLine:
    ZERO = {"added": 0, "modified": 0, "erased": 0}

    def line(self, text, counted, can_count=True):
        return answers.line(answers.Facts(text, ok=True, outcome="done", counted=counted, wrote=True, can_count=can_count))

    def test_a_lisp_error_that_changed_nothing_says_so(self, lisp):
        text, _, _ = lisp("(+ 1 nil)", Doc(error_at=1))
        line = self.line(text, self.ZERO)
        assert line.startswith("NOTHING CHANGED - AutoCAD reported a LISP error")

    def test_a_lisp_error_after_earlier_pieces_changed_things_is_never_done(self, lisp):
        text, _, _ = lisp(LONG, Doc(error_at=3))
        line = self.line(text, {"added": 2, "modified": 0, "erased": 0})
        assert line.startswith("OUTCOME UNKNOWN - AutoCAD reported a LISP error")
        assert "2 added" in line

    def test_a_lisp_error_when_the_plugin_cannot_count_is_never_done(self, lisp):
        text, _, _ = lisp(LONG, Doc(error_at=3))
        line = self.line(text, self.ZERO, can_count=False)
        assert line.startswith("OUTCOME UNKNOWN - AutoCAD reported a LISP error")
